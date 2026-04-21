"""M7.2 first LLM-in-loop demo — component swap via Claude tool-use.

Demonstrates the end-to-end synthetic-generation loop at the smallest
testable scale:

1. Pick a screen with at least one classified `button` instance.
2. Compress it to L3 (via ``dd.compress_l3``).
3. Build a compact context: screen eid table + target button +
   library catalog (just buttons).
4. Ask Claude (tool-use) to emit a ``swap`` verb changing the
   target button's master to a different one in the library.
5. Parse the emitted swap via ``dd.markup_l3.parse_l3`` and apply
   it to the compressed document via ``dd.markup_l3.apply_edits``.
6. Verify structurally: the target eid's node now has the new
   CompRef path.

This is the `S2.5 component swap` demo from plan-synthetic-gen.md §4.
The LLM is NOT asked to render; it's asked to emit a single edit
statement in the 7-verb grammar. Rendering + Figma-level parity
round-trip can be added as a follow-up (needs plugin bridge).

Usage::

    .venv/bin/python3 -m scripts.m7_swap_demo --db Dank-EXP-02.declarative.db \\
        [--screen-id 183] [--target-eid button-123] [--dry-run]

``--dry-run`` skips the Anthropic API call and emits a hand-written
swap so the pipeline can be smoke-tested without spending tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _build_swap_tool_schema(
    candidate_eids: list[str], master_names: list[str],
) -> dict:
    """Tool schema pinned to the specific candidate eids + library
    master names for THIS run. Enum constraints enforce the LLM
    picks valid values — the demo no longer has to strip a stray
    `@` or catch a typo'd master.
    """
    return {
        "name": "emit_swap_edit",
        "description": (
            "Emit one `swap` statement from the L3 edit grammar. The "
            "swap changes the COMPONENT at the given eid to a "
            "different master from the library catalog."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_eid": {
                    "type": "string",
                    "enum": candidate_eids,
                    "description": (
                        "The eid of the button to swap (no leading "
                        "`@` in the value — choose from the enum)."
                    ),
                },
                "new_master_name": {
                    "type": "string",
                    "enum": master_names,
                    "description": (
                        "The 'name' of the library component to "
                        "swap IN. MUST be a different master than "
                        "the current one."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": (
                        "One-sentence reason for the choice."
                    ),
                },
            },
            "required": [
                "target_eid", "new_master_name", "rationale",
            ],
        },
    }


def _build_system_prompt() -> str:
    return (
        "You are a UI refactor assistant. You receive a compact "
        "description of a screen (its top-level nodes + candidate "
        "button targets) and a library catalog of available button "
        "masters. Your job is to emit ONE `swap` statement via the "
        "`emit_swap_edit` tool, changing a target button's master "
        "to a DIFFERENT master from the catalog. Keep the change "
        "defensible — don't swap a `solid` button for a "
        "`translucent` one unless there's reason."
    )


def _build_user_prompt(
    screen_summary: str,
    target_candidates: list[dict],
    library_json: str,
) -> str:
    candidate_lines = "\n".join(
        f"  - @{c['eid']}  current_master={c['current_master']!r}  "
        f"context={c.get('context', '(none)')}"
        for c in target_candidates
    )
    return (
        f"### Screen summary\n{screen_summary}\n\n"
        f"### Button-swap candidates\n{candidate_lines}\n\n"
        f"### Library catalog (buttons)\n{library_json}\n\n"
        "Pick ONE candidate above and emit a swap changing its "
        "master to a different one from the catalog. Use the "
        "`emit_swap_edit` tool."
    )


def _extract_swap_call(response, tool_name: str) -> dict | None:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != tool_name:
            continue
        inp = getattr(block, "input", None)
        if isinstance(inp, dict):
            return inp
    return None


# SD-3 trust set — same as slot derivation + backfill. NULL keeps
# pre-M7.0.a rows that have a formal / heuristic source but no
# consensus_method populated.
_TRUSTED_CONSENSUS_METHODS = (
    "formal", "heuristic", "unanimous", "two_source_unanimous",
)


def _collect_button_candidates(conn, screen_id, limit=10):
    """Fetch trust-filtered button instances on the screen with their
    sci.id, node_id, current master name (from CKR), and the
    instance's own node name (context).
    """
    trust_placeholders = ",".join("?" * len(_TRUSTED_CONSENSUS_METHODS))
    rows = conn.execute(
        f"""
        SELECT sci.id, sci.node_id, n.name AS inst_name,
               ckr.name AS master_name
        FROM screen_component_instances sci
        JOIN nodes n ON n.id = sci.node_id
        LEFT JOIN component_key_registry ckr
          ON ckr.component_key = n.component_key
        WHERE sci.screen_id = ?
          AND sci.canonical_type = 'button'
          AND ckr.name IS NOT NULL
          AND (
              sci.consensus_method IS NULL
              OR sci.consensus_method IN ({trust_placeholders})
          )
        ORDER BY sci.id LIMIT ?
        """,
        (screen_id, *_TRUSTED_CONSENSUS_METHODS, limit),
    ).fetchall()
    return [
        {
            "sci_id": r[0],
            "node_id": r[1],
            "inst_name": r[2],
            "current_master": r[3],
        }
        for r in rows
    ]


def _count_eids_globally(doc) -> dict[str, int]:
    """Count eid occurrences across the compressed doc. Eids that
    appear more than once would fire ``KIND_EID_AMBIGUOUS`` at
    apply_edits time on bare ``@X`` references — drop them from
    swap-target candidate sets so the LLM never picks one."""
    counts: dict[str, int] = {}

    def _walk(nodes):
        for n in nodes:
            if hasattr(n, "head") and n.head.eid:
                counts[n.head.eid] = counts.get(n.head.eid, 0) + 1
            if getattr(n, "block", None):
                _walk(n.block.statements)

    _walk(doc.top_level)
    return counts


def _find_eid_by_nid(doc, target_node_id: int, nid_map: dict[str, int]) -> str | None:
    """Reverse-look up the compressed L3 eid that maps to the given
    node_id. Returns None if the compressor didn't assign an eid for
    that node (structurally possible when the compressor inlines
    small subtrees).
    """
    for eid, nid in nid_map.items():
        if nid == target_node_id:
            return eid
    return None


def run_demo(
    db_path: str,
    *,
    screen_id: int | None,
    target_eid: str | None,
    dry_run: bool,
    render: bool = False,
    ws_port: int = 9228,
    save_script_path: str | None = None,
    skip_bridge: bool = False,
    bridge_timeout: float = 240.0,
) -> int:
    from dd.apply_render import (
        BridgeError,
        SwapUnresolvedInCKR,
        render_applied_doc,
        walk_rendered_via_bridge,
    )
    from dd.compress_l3 import compress_to_l3_with_maps
    from dd.db import get_connection
    from dd.ir import generate_ir, query_screen_visuals
    from dd.library_catalog import serialize_library, serialize_library_json
    from dd.markup_l3 import apply_edits, parse_l3
    from dd.renderers.figma import collect_fonts
    from dd.verify_figma import FigmaRenderVerifier

    conn = get_connection(db_path)

    # 1. Pick a screen if not supplied.
    if screen_id is None:
        row = conn.execute(
            """
            SELECT s.id FROM screens s
            WHERE s.screen_type = 'app_screen'
              AND EXISTS (SELECT 1 FROM screen_component_instances
                          WHERE screen_id = s.id
                            AND canonical_type = 'button')
            ORDER BY (SELECT COUNT(*) FROM nodes
                      WHERE screen_id = s.id) ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            print("No app_screen with buttons found.", file=sys.stderr)
            return 1
        screen_id = row[0]
    print(f"Screen: {screen_id}")

    # 2. Compress to L3 — four side-car maps (render_applied_doc
    # needs the id(Node)-keyed forms; structural verify only needs
    # the eid→nid bridge, but pulling all four once keeps the render
    # path cheap to reach from --render).
    #
    # When --render is active we match the production generate_screen
    # ingestion: filter_chrome=False keeps the Safari + HomeIndicator
    # system chrome instances, and collapse_wrapper=False keeps the
    # iPhone outer/inner double-frame the verifier expects. Without
    # these, the emitted script differs structurally from the 204/204
    # parity baseline and the rendered walk won't align with the IR.
    ir = generate_ir(
        conn, screen_id,
        semantic=True,
        filter_chrome=False if render else True,
    )
    spec = ir.get("spec") if "spec" in ir else ir
    doc, eid_to_nid, old_nid_map, old_spec_key_map, old_original_name_map = (
        compress_to_l3_with_maps(
            spec, conn, screen_id=screen_id,
            collapse_wrapper=not render,
        )
    )
    # compress returns {eid_str: db_node_id_int}; invert for lookup
    # by node_id.
    nid_to_eid = {v: k for k, v in eid_to_nid.items()}

    # 3. Collect button candidates; match sci.node_id → eid.
    # Drop eids that appear more than once in the compressed doc —
    # bare `@X` resolution inside apply_edits walks every node, so
    # cousin collisions fire KIND_EID_AMBIGUOUS at apply time.
    eid_counts = _count_eids_globally(doc)
    candidates_sci = _collect_button_candidates(conn, screen_id, limit=50)
    candidates: list[dict] = []
    for c in candidates_sci:
        # node_id in sci is the DB nodes.id; nid_to_eid maps that
        # back to the compressed L3 eid.
        eid = nid_to_eid.get(c["node_id"])
        if not eid:
            continue
        if eid_counts.get(eid, 0) != 1:
            continue
        candidates.append({
            "eid": eid,
            "current_master": c["current_master"],
            "context": c["inst_name"],
        })
    if not candidates:
        print("No buttons with a globally-unique L3 eid on this screen.",
              file=sys.stderr)
        return 1
    print(f"Button candidates: {len(candidates)}")
    for c in candidates[:5]:
        print(f"  @{c['eid']} master={c['current_master']} "
              f"context={c['context']}")

    # 4. Library catalog (buttons only).
    library_json = serialize_library_json(
        conn, canonical_types=["button"],
    )
    catalog = serialize_library(conn, canonical_types=["button"])
    master_names = {c["name"] for c in catalog["components"]}
    print(f"Library: {len(master_names)} button masters")

    # Filter candidates to ones whose current master is IN the
    # library (sanity — otherwise the swap target set is wrong).
    candidates = [
        c for c in candidates if c["current_master"] in master_names
    ]
    if not candidates:
        print("No candidates with a library-registered master.",
              file=sys.stderr)
        return 1

    # 5. LLM emits swap via tool-use, OR dry-run returns a hand-
    # written swap.
    if dry_run:
        chosen = candidates[0]
        alt = next(
            (m for m in master_names if m != chosen["current_master"]),
            None,
        )
        if alt is None:
            print("Only one button master in library — nothing to swap TO.",
                  file=sys.stderr)
            return 1
        swap = {
            "target_eid": chosen["eid"],
            "new_master_name": alt,
            "rationale": "[dry-run] picked first alt master",
        }
        print(f"\nDry-run swap: {json.dumps(swap, indent=2)}")
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY not set (check .env).",
                  file=sys.stderr)
            return 1
        import anthropic
        client = anthropic.Anthropic()
        screen_summary = (
            f"screen id={screen_id}, top-level kind="
            f"{doc.top_level[0].head.type_or_path if doc.top_level else '(empty)'}"
        )
        # Restrict the candidate list for the LLM (the prompt would
        # bloat otherwise). First 10 is plenty.
        llm_candidates = candidates[:10]
        user_prompt = _build_user_prompt(
            screen_summary, llm_candidates, library_json,
        )
        tool_schema = _build_swap_tool_schema(
            candidate_eids=[c["eid"] for c in llm_candidates],
            master_names=sorted(master_names),
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=_build_system_prompt(),
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_schema["name"]},
            messages=[{"role": "user", "content": user_prompt}],
        )
        swap = _extract_swap_call(response, tool_schema["name"])
        if swap is None:
            print("LLM did not emit a swap tool call.", file=sys.stderr)
            return 1
        print(f"\nLLM swap: {json.dumps(swap, indent=2)}")

    # 6. Pre-apply validation + build the swap statement. The
    # tool-use enums should keep the LLM honest, but validate
    # defensively — we never want apply_edits silently mutating
    # a node to an out-of-catalog CompRef (structural verify
    # would pass but the rendered output would break).
    target_eid_str = swap["target_eid"].lstrip("@").strip()
    new_master = swap["new_master_name"].strip()
    candidate_eids = {c["eid"] for c in candidates}
    if target_eid_str not in candidate_eids:
        print(
            f"Rejecting swap: target_eid {target_eid_str!r} not in "
            f"candidate set ({sorted(candidate_eids)[:5]}…).",
            file=sys.stderr,
        )
        return 1
    if new_master not in master_names:
        print(
            f"Rejecting swap: new_master {new_master!r} not in "
            f"library catalog.",
            file=sys.stderr,
        )
        return 1
    current_master_for_target = next(
        (c["current_master"] for c in candidates
         if c["eid"] == target_eid_str),
        None,
    )
    if current_master_for_target == new_master:
        print(
            f"Rejecting swap: new_master matches current "
            f"({new_master!r}) — no-op.",
            file=sys.stderr,
        )
        return 1

    # Edit statements live at the top level of an L3 document
    # (grammar §8.6) — no wrapper block.
    edit_doc_src = f"swap @{target_eid_str} with=-> {new_master}\n"
    try:
        edit_doc = parse_l3(edit_doc_src)
    except Exception as e:
        print(f"Failed to parse edit statement: {e}", file=sys.stderr)
        return 1
    edit_stmts = list(edit_doc.edits)
    if not edit_stmts:
        print("No edit statements parsed out of LLM response.",
              file=sys.stderr)
        return 1

    try:
        applied = apply_edits(doc, edit_stmts)
    except Exception as e:
        print(f"apply_edits failed: {e}", file=sys.stderr)
        return 1

    # 7. Verify structurally — find the eid in the applied doc and
    # confirm its head is now the new CompRef path.
    def _find_eid(node_list, target):
        for n in node_list:
            if getattr(n.head, "eid", None) == target:
                return n
            block = getattr(n, "block", None)
            if block is not None:
                sub = _find_eid(
                    [s for s in block.statements if hasattr(s, "head")],
                    target,
                )
                if sub:
                    return sub
        return None

    updated = _find_eid(list(applied.top_level), target_eid_str)
    if updated is None:
        print(f"Could not find @{target_eid_str} in applied doc.",
              file=sys.stderr)
        return 1

    new_path = updated.head.type_or_path
    print(
        f"\nApplied swap at @{target_eid_str}: "
        f"new CompRef path = {new_path!r}"
    )
    if new_path != new_master:
        print(
            f"FAIL: expected {new_master!r}, got {new_path!r}",
            file=sys.stderr,
        )
        conn.close()
        return 1
    print("structural verify PASS — CompRef path matches.")

    # ---------------------------------------------------------------
    # 8. Optional: full render + plugin-bridge walk + is_parity verify.
    #    This is the plan-synthetic-gen.md M7.2 exit bar.
    # ---------------------------------------------------------------
    if not render:
        conn.close()
        return 0

    print("\n--- render pass (M7.2 is_parity gate) ---")
    db_visuals = query_screen_visuals(conn, screen_id)
    fonts = collect_fonts(spec, db_visuals=db_visuals)

    # Build the VERIFY spec independently. The render path wants
    # semantic+chrome IR (to populate Mode-1 library references);
    # the verifier wants the default IR (no orphaned alternative-
    # classification elements). This mirrors how the production
    # sweep decouples them: `dd/renderers/figma.py:generate_screen`
    # uses semantic=True, filter_chrome=False; `dd verify` uses
    # default `generate_ir(conn, screen_id)`. On screen 183 the
    # difference is 204 elements-all-reachable (default) vs 204
    # elements with 162 orphans (semantic) — the orphans would
    # fire spurious KIND_MISSING_CHILD for alt-classification
    # subtrees the renderer never emits.
    from dd.apply_render import adjust_spec_elements_for_edits as _adjust
    verify_ir = generate_ir(conn, screen_id)
    verify_spec = dict(verify_ir["spec"])
    verify_spec["elements"] = _adjust(
        verify_spec.get("elements") or {}, edits=edit_stmts,
    )

    try:
        rendered = render_applied_doc(
            applied_doc=applied,
            original_doc=doc,
            edits=edit_stmts,
            spec=spec,
            conn=conn,
            db_visuals=db_visuals,
            fonts=fonts,
            old_nid_map=old_nid_map,
            old_spec_key_map=old_spec_key_map,
            old_original_name_map=old_original_name_map,
        )
    except SwapUnresolvedInCKR as e:
        print(
            f"render failed: swap references an out-of-catalog "
            f"master — {e}",
            file=sys.stderr,
        )
        conn.close()
        return 1
    except Exception as e:
        print(f"render failed: {e}", file=sys.stderr)
        conn.close()
        return 1

    print(f"render OK — script {len(rendered.script)} chars, "
          f"token_refs={len(rendered.token_refs)}, "
          f"synth_nids={len(rendered.applied_maps.db_visuals_patch)}")

    if save_script_path:
        Path(save_script_path).write_text(rendered.script)
        print(f"saved render script to {save_script_path}")

    # --skip-bridge short-circuits to render-only; the caller runs
    # the walk out-of-band. Useful when the Figma plugin is stuck or
    # the user wants to diff the script offline first.
    if skip_bridge:
        print(
            "\n--skip-bridge set — stopping at render-OK. Run the "
            "walk manually when the bridge is ready:\n"
            f"  node render_test/walk_ref.js {save_script_path or '<script>'} "
            f"<out.json> {ws_port}"
        )
        conn.close()
        return 0

    # Try the plugin bridge. If not reachable, we still succeed at
    # render-level (script generated cleanly), but the plan's
    # is_parity gate requires a live walk. Report clearly.
    try:
        rendered_ref = walk_rendered_via_bridge(
            script=rendered.script,
            ws_port=ws_port,
            timeout=bridge_timeout,
            keep_artifacts=False,
        )
    except BridgeError as e:
        print(
            f"\nBRIDGE UNAVAILABLE — {e}\n"
            "Render-only verification succeeded; save the script "
            "above and walk it manually via `node render_test/"
            f"walk_ref.js <script> <out.json> {ws_port}` to complete "
            "is_parity verify.",
            file=sys.stderr,
        )
        conn.close()
        return 2  # Distinct exit code so callers can see "render ok, bridge unavailable"

    # The rendered-walk keys eid_map on whatever `M[...]` contains,
    # which is spec_key (the spec's element-dict key like
    # ``button-2``), not the user-facing eid. The apply-render
    # output includes the eid → spec_key translation for swap
    # targets; use it to look up the rendered entry.
    target_spec_key = rendered.eid_to_spec_key.get(
        target_eid_str, target_eid_str
    )
    rendered_target = (rendered_ref.get("eid_map") or {}).get(
        target_spec_key, {}
    )
    if not rendered_target:
        print(
            f"FAIL: target @{target_eid_str} (spec_key={target_spec_key}) "
            f"absent from rendered_ref eid_map "
            f"(walker found {len(rendered_ref.get('eid_map') or {})} eids).",
            file=sys.stderr,
        )
        conn.close()
        return 1
    print(
        f"rendered @{target_eid_str} (spec_key={target_spec_key}): "
        f"type={rendered_target.get('type')} "
        f"name={rendered_target.get('name')!r}"
    )

    # Verify against the default-IR spec (adjusted), not the
    # semantic one used for render — see comment at --- render
    # pass --- above.
    report = FigmaRenderVerifier().verify(verify_spec, rendered_ref)
    print(
        f"RenderReport: ir_nodes={report.ir_node_count} "
        f"rendered={report.rendered_node_count} "
        f"is_parity={report.is_parity} "
        f"errors={len(report.errors)}"
    )
    for err in report.errors[:10]:
        print(f"  kind={err.kind} id={err.id} {(err.error or '')[:80]}")
    if len(report.errors) > 10:
        print(f"  ... ({len(report.errors) - 10} more)")

    # Two M7.2 gates: (a) is_parity=True; (b) the resolved component
    # at the swap target rendered as an INSTANCE (not a placeholder
    # wireframe).
    gate_parity = report.is_parity
    gate_instance = rendered_target.get("type") == "INSTANCE"
    if gate_parity and gate_instance:
        print("\nM7.2 SUCCESS: is_parity + resolved-to-INSTANCE")
        conn.close()
        return 0
    if not gate_parity:
        print("\nM7.2 FAIL: is_parity=False", file=sys.stderr)
    if not gate_instance:
        print(
            f"\nM7.2 FAIL: target rendered as "
            f"{rendered_target.get('type')!r}, expected INSTANCE "
            "(renderer likely fell through to a placeholder wireframe)",
            file=sys.stderr,
        )
    conn.close()
    return 1


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument("--screen-id", type=int, default=None)
    parser.add_argument("--target-eid", default=None)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip the Anthropic call; use a hand-picked swap.",
    )
    parser.add_argument(
        "--render", action="store_true",
        help=(
            "After structural verify, also render the applied doc as "
            "a Figma script, walk it via the plugin bridge, and run "
            "FigmaRenderVerifier to gate on is_parity=True + the "
            "swap target rendering as INSTANCE. M7.2 exit bar. "
            "Exit codes: 0 = is_parity pass; 1 = structural or "
            "verify fail; 2 = render OK but bridge unavailable."
        ),
    )
    parser.add_argument(
        "--ws-port", type=int, default=9228,
        help="WebSocket port where the Figma plugin bridge listens.",
    )
    parser.add_argument(
        "--save-script", default=None,
        help=(
            "If set and --render is active, write the generated "
            "Figma JS to this path. Useful when the bridge isn't "
            "reachable and you want to walk manually."
        ),
    )
    parser.add_argument(
        "--skip-bridge", action="store_true",
        help=(
            "Skip the plugin-bridge walk + verify step; only "
            "generate the swap script. Pair with --save-script "
            "for offline inspection."
        ),
    )
    parser.add_argument(
        "--bridge-timeout", type=float, default=240.0,
        help=(
            "Seconds to wait for the plugin bridge to respond. "
            "Bump up to 300–600 for iPad-sized screens when the "
            "Figma plugin is under cumulative load."
        ),
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    return run_demo(
        args.db,
        screen_id=args.screen_id,
        target_eid=args.target_eid,
        dry_run=args.dry_run,
        render=args.render,
        ws_port=args.ws_port,
        save_script_path=args.save_script,
        skip_bridge=args.skip_bridge,
        bridge_timeout=args.bridge_timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
