"""M7.3 S1.4 demo — change a node's corner radius via Claude tool-use.

Sibling to ``m7_swap_demo.py`` using the ``set`` verb instead of
``swap``. Plan §4 S1 tier demos single-node property edits. Text
(S1.1) is blocked on compressor-side positional handling; radius
is a clean property-level target that exercises the set verb's
current capability.

1. Compress a Dank screen to L3.
2. Collect (eid, current_radius) for every eid-bearing node whose
   head has a scalar ``radius`` PropAssign.
3. Ask Claude Haiku to pick ONE candidate and emit a new scalar
   via the ``emit_set_radius`` tool.
4. Parse ``set @X radius=N`` as L3, apply via
   ``dd.markup_l3.apply_edits``.
5. Verify structurally: the target eid's ``radius`` now holds the
   new value.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _build_set_radius_tool(candidate_eids: list[str]) -> dict:
    return {
        "name": "emit_set_radius",
        "description": (
            "Emit one `set` statement that updates the `radius` "
            "property of the target node."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_eid": {
                    "type": "string",
                    "enum": candidate_eids,
                    "description": "Target eid (no leading `@`).",
                },
                "new_radius": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 128,
                    "description": (
                        "New radius in px. Prefer common scale "
                        "steps: 0 / 4 / 8 / 12 / 16 / 24 / 32."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "One-sentence reason.",
                },
            },
            "required": ["target_eid", "new_radius", "rationale"],
        },
    }


def _extract_set_call(response, tool_name: str) -> dict | None:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != tool_name:
            continue
        inp = getattr(block, "input", None)
        if isinstance(inp, dict):
            return inp
    return None


def _collect_radius_candidates(doc):
    """Scalar-radius PropAssign candidates, keyed by eid."""
    out: list[dict] = []

    def _walk(nodes):
        for n in nodes:
            if not hasattr(n, "head"):
                continue
            if n.head.eid:
                for p in getattr(n.head, "properties", ()) or ():
                    if getattr(p, "key", None) != "radius":
                        continue
                    val = getattr(p.value, "py", None)
                    if isinstance(val, (int, float)):
                        out.append({
                            "eid": n.head.eid,
                            "type": n.head.type_or_path,
                            "current": val,
                        })
                    break
            if getattr(n, "block", None):
                _walk(n.block.statements)

    _walk(doc.top_level)
    return out


def run_demo(
    db_path: str,
    *,
    screen_id: int | None,
    dry_run: bool,
) -> int:
    from dd.db import get_connection
    from dd.ir import generate_ir
    from dd.compress_l3 import compress_to_l3_with_nid_map
    from dd.markup_l3 import apply_edits, parse_l3

    conn = get_connection(db_path)

    if screen_id is None:
        row = conn.execute(
            """
            SELECT s.id FROM screens s
            WHERE s.screen_type='app_screen'
            ORDER BY (SELECT COUNT(*) FROM nodes WHERE screen_id=s.id) ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            print("No app_screen found.", file=sys.stderr)
            return 1
        screen_id = row[0]
    print(f"Screen: {screen_id}")

    ir = generate_ir(conn, screen_id, semantic=True)
    spec = ir.get("spec") if "spec" in ir else ir
    doc, _eid_to_nid = compress_to_l3_with_nid_map(
        spec, conn, screen_id=screen_id,
    )

    candidates = _collect_radius_candidates(doc)
    seen: set[str] = set()
    unique = []
    for c in candidates:
        if c["eid"] in seen:
            continue
        seen.add(c["eid"])
        unique.append(c)
    candidates = unique

    if not candidates:
        print("No eid-bearing nodes with a scalar radius.",
              file=sys.stderr)
        return 1

    print(f"Radius candidates: {len(candidates)}")
    for c in candidates[:5]:
        print(f"  @{c['eid']}  type={c['type']} "
              f"current={c['current']}")

    if dry_run:
        chosen = candidates[0]
        new_radius = 0 if chosen["current"] != 0 else 16
        out = {
            "target_eid": chosen["eid"],
            "new_radius": new_radius,
            "rationale": "[dry-run] flipped radius",
        }
        print(f"\nDry-run set: {json.dumps(out, indent=2)}")
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
            return 1
        import anthropic
        client = anthropic.Anthropic()
        llm_candidates = candidates[:10]
        tool_schema = _build_set_radius_tool(
            [c["eid"] for c in llm_candidates],
        )
        user_prompt = (
            "### Radius-edit candidates\n"
            + "\n".join(
                f"  - @{c['eid']}  type={c['type']}  "
                f"current={c['current']}"
                for c in llm_candidates
            )
            + "\n\nPick ONE candidate and emit a `set` statement "
            "with a new radius. Prefer scale steps "
            "(0/4/8/12/16/24/32). Keep the change defensible."
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_schema["name"]},
            messages=[{"role": "user", "content": user_prompt}],
        )
        out = _extract_set_call(response, tool_schema["name"])
        if out is None:
            print("LLM did not emit a set tool call.", file=sys.stderr)
            return 1
        print(f"\nLLM set: {json.dumps(out, indent=2)}")

    target_eid = out["target_eid"].lstrip("@").strip()
    new_radius = out["new_radius"]
    candidate_eids = {c["eid"] for c in candidates}
    if target_eid not in candidate_eids:
        print(f"Rejecting: target_eid {target_eid!r} not in "
              f"candidates.", file=sys.stderr)
        return 1
    current_for_target = next(
        (c["current"] for c in candidates if c["eid"] == target_eid),
        None,
    )
    if current_for_target == new_radius:
        print(f"Rejecting: no-op (current={current_for_target}).",
              file=sys.stderr)
        return 1

    edit_src = f"set @{target_eid} radius={new_radius}\n"
    try:
        edit_doc = parse_l3(edit_src)
    except Exception as e:
        print(f"Failed to parse set statement: {e}", file=sys.stderr)
        return 1
    stmts = list(edit_doc.edits)
    if not stmts:
        print("No edits parsed.", file=sys.stderr)
        return 1

    try:
        applied = apply_edits(doc, stmts)
    except Exception as e:
        print(f"apply_edits failed: {e}", file=sys.stderr)
        return 1

    def _find_radius(nodes, target):
        for n in nodes:
            if hasattr(n, "head") and n.head.eid == target:
                for p in getattr(n.head, "properties", ()) or ():
                    if getattr(p, "key", None) == "radius":
                        return getattr(p.value, "py", None)
            if getattr(n, "block", None):
                sub = _find_radius(n.block.statements, target)
                if sub is not None:
                    return sub
        return None

    applied_value = _find_radius(applied.top_level, target_eid)
    print(f"\nApplied set at @{target_eid}: "
          f"new radius = {applied_value!r}")
    if applied_value == new_radius:
        print("SUCCESS: structural verify pass — radius matches.")
        conn.close()
        return 0
    print(f"FAIL: expected {new_radius}, got {applied_value!r}",
          file=sys.stderr)
    conn.close()
    return 1


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument("--screen-id", type=int, default=None)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip the Anthropic call; use a hand-picked set.",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    return run_demo(
        args.db, screen_id=args.screen_id, dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
