"""M7.3 S1.2 demo — toggle a node's visibility via Claude tool-use.

Third LLM-in-loop verb after ``swap`` (M7.2) and ``set radius``
(M7.3 S1.4). ``set visible=false`` is the smallest-possible structural
edit — boolean scalar, no token refs, no spatial reasoning.

Pattern matches ``m7_set_radius_demo.py``:

1. Compress a Dank screen to L3.
2. Collect every eid-bearing node with a sensible visibility-flip
   target (non-screen, non-chrome). Current-visible state noted for
   the LLM so it doesn't pick a no-op.
3. Ask Claude Haiku to pick ONE candidate + emit the new boolean via
   ``emit_set_visibility``.
4. Parse ``set @X visible=<bool>`` as L3; apply via
   ``dd.markup_l3.apply_edits``.
5. Verify structurally: the target eid's ``visible`` property now
   equals the requested value.

Usage::

    .venv/bin/python3 -m scripts.m7_set_visibility_demo \\
        --db Dank-EXP-02.declarative.db \\
        [--screen-id 183] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _build_set_visibility_tool(candidate_eids: list[str]) -> dict:
    return {
        "name": "emit_set_visibility",
        "description": (
            "Emit one `set` statement that flips the target node's "
            "`visible` property. Must change the CURRENT value — do "
            "not emit a no-op."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_eid": {
                    "type": "string",
                    "enum": candidate_eids,
                    "description": "Target eid (no leading `@`).",
                },
                "new_visible": {
                    "type": "boolean",
                    "description": (
                        "Desired visibility. Must differ from the "
                        "candidate's current_visible value."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "One-sentence reason.",
                },
            },
            "required": ["target_eid", "new_visible", "rationale"],
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


_SKIP_TYPES = frozenset({"screen"})


def _collect_visibility_candidates(doc):
    """Eid-bearing non-screen nodes safe to flip.

    Current visibility defaults to True when the compressor doesn't
    emit a `visible` prop (grammar §4.2 default), else the prop's
    Boolean py value. Only GLOBALLY UNIQUE eids are returned —
    duplicates would fire ``KIND_AMBIGUOUS_EREF`` at apply-time
    because bare ``@X`` resolution walks every node, not a
    dotted path."""
    counts: dict[str, int] = {}
    found: list[dict] = []

    def _current_visible(head):
        for p in getattr(head, "properties", ()) or ():
            if getattr(p, "key", None) == "visible":
                val = getattr(p.value, "py", None)
                if isinstance(val, bool):
                    return val
        return True

    def _walk(nodes):
        for n in nodes:
            if hasattr(n, "head") and n.head.eid:
                counts[n.head.eid] = counts.get(n.head.eid, 0) + 1
                if n.head.type_or_path not in _SKIP_TYPES:
                    found.append({
                        "eid": n.head.eid,
                        "type": n.head.type_or_path,
                        "current_visible": _current_visible(n.head),
                    })
            if getattr(n, "block", None):
                _walk(n.block.statements)

    _walk(doc.top_level)
    dedup: dict[str, dict] = {}
    for row in found:
        if counts.get(row["eid"], 0) != 1:
            continue
        if row["eid"] in dedup:
            continue
        dedup[row["eid"]] = row
    return list(dedup.values())


def run_demo(
    db_path: str,
    *,
    screen_id: int | None,
    dry_run: bool,
) -> int:
    from dd.compress_l3 import compress_to_l3_with_nid_map
    from dd.db import get_connection
    from dd.ir import generate_ir
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
    doc, _ = compress_to_l3_with_nid_map(
        spec, conn, screen_id=screen_id,
    )

    candidates = _collect_visibility_candidates(doc)
    if not candidates:
        print("No eid-bearing non-screen nodes.", file=sys.stderr)
        return 1
    print(f"Visibility candidates: {len(candidates)}")
    for c in candidates[:5]:
        print(f"  @{c['eid']}  type={c['type']} "
              f"current_visible={c['current_visible']}")

    if dry_run:
        chosen = candidates[0]
        out = {
            "target_eid": chosen["eid"],
            "new_visible": not chosen["current_visible"],
            "rationale": "[dry-run] flipped visibility",
        }
        print(f"\nDry-run set: {json.dumps(out, indent=2)}")
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
            return 1
        import anthropic
        client = anthropic.Anthropic()
        llm_candidates = candidates[:10]
        tool_schema = _build_set_visibility_tool(
            [c["eid"] for c in llm_candidates],
        )
        user_prompt = (
            "### Visibility-edit candidates\n"
            + "\n".join(
                f"  - @{c['eid']}  type={c['type']}  "
                f"current_visible={c['current_visible']}"
                for c in llm_candidates
            )
            + "\n\nPick ONE candidate and emit a `set visible=...` "
            "that CHANGES its current state (no-ops rejected)."
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
    new_visible = bool(out["new_visible"])
    candidate_eids = {c["eid"] for c in candidates}
    if target_eid not in candidate_eids:
        print(f"Rejecting: target_eid {target_eid!r} not in "
              f"candidates.", file=sys.stderr)
        return 1
    current_for_target = next(
        (c["current_visible"] for c in candidates
         if c["eid"] == target_eid),
        None,
    )
    if current_for_target == new_visible:
        print(
            f"Rejecting: no-op (current_visible={current_for_target}).",
            file=sys.stderr,
        )
        return 1

    edit_src = f"set @{target_eid} visible={str(new_visible).lower()}\n"
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

    def _find_visible(nodes, target):
        for n in nodes:
            if hasattr(n, "head") and n.head.eid == target:
                for p in getattr(n.head, "properties", ()) or ():
                    if getattr(p, "key", None) == "visible":
                        return getattr(p.value, "py", None)
            if getattr(n, "block", None):
                sub = _find_visible(n.block.statements, target)
                if sub is not None:
                    return sub
        return None

    applied_value = _find_visible(applied.top_level, target_eid)
    print(f"\nApplied set at @{target_eid}: "
          f"new visible = {applied_value!r}")
    if applied_value == new_visible:
        print("SUCCESS: structural verify pass — visible matches.")
        conn.close()
        return 0
    print(f"FAIL: expected {new_visible}, got {applied_value!r}",
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
