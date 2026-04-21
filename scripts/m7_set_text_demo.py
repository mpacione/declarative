"""M7.3 S1.1 demo — change a text node's string content via Claude.

Last of the four S1-tier single-node property demos. Plan §4 S1.1.

S1.1 was flagged in plan-synthetic-gen.md §5 as blocked on "extending
``_apply_set_to_node`` to address ``Node.head.positional``." This demo
ships with the grammar fix (see ``dd.markup_l3._apply_set_to_node`` —
S1.1 positional-rewrite carve-out) plus new tests in
``tests/test_edit_grammar.py`` (test_set_text_string_updates_positional,
test_set_text_on_non_text_node_falls_through_to_prop).

Pattern matches the other S1 demos:

1. Compress a Dank screen to L3.
2. Collect eid-bearing text / heading / link nodes with a positional
   string. Current value is shown so the LLM can pick a meaningful
   rephrase (not a no-op).
3. Ask Claude Haiku to pick ONE candidate + emit a new string via
   ``emit_set_text``.
4. Parse ``set @X text="..."`` as L3; apply via
   ``dd.markup_l3.apply_edits`` (which rewrites positional on
   text-bearing types).
5. Verify structurally: the target eid's positional string now
   matches the requested text.

Usage::

    .venv/bin/python3 -m scripts.m7_set_text_demo \\
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


_TEXT_TYPES: frozenset[str] = frozenset({"text", "heading", "link"})


def _build_set_text_tool(candidate_eids: list[str]) -> dict:
    return {
        "name": "emit_set_text",
        "description": (
            "Emit one `set` statement that updates the target text "
            "node's string content. Must change the current string "
            "— do not emit a no-op."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_eid": {
                    "type": "string",
                    "enum": candidate_eids,
                    "description": "Target eid (no leading `@`).",
                },
                "new_text": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 120,
                    "description": (
                        "New string content for the target text "
                        "node. Keep it short; avoid newlines."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "One-sentence reason for the choice.",
                },
            },
            "required": ["target_eid", "new_text", "rationale"],
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


def _collect_text_candidates(doc):
    """Eid-bearing text / heading / link nodes with positional
    strings. Only include eids that are GLOBALLY UNIQUE across the
    compressed doc — duplicates would fire ``KIND_AMBIGUOUS_EREF``
    at apply-time because the ``set @X`` address resolves to more
    than one node."""
    counts: dict[str, int] = {}
    found: list[dict] = []

    def _walk(nodes):
        for n in nodes:
            if hasattr(n, "head") and n.head.eid:
                counts[n.head.eid] = counts.get(n.head.eid, 0) + 1
                if n.head.type_or_path in _TEXT_TYPES:
                    pos = n.head.positional
                    if (
                        pos is not None
                        and getattr(pos, "lit_kind", None) == "string"
                    ):
                        py = pos.py
                        if isinstance(py, str) and py.strip():
                            found.append({
                                "eid": n.head.eid,
                                "type": n.head.type_or_path,
                                "current_text": py,
                            })
            if getattr(n, "block", None):
                _walk(n.block.statements)

    _walk(doc.top_level)
    # Collapse to one row per unique eid; drop ambiguous ones.
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

    candidates = _collect_text_candidates(doc)
    if not candidates:
        print(
            "No eid-bearing text-bearing nodes with positional content.",
            file=sys.stderr,
        )
        return 1
    print(f"Text candidates: {len(candidates)}")
    for c in candidates[:5]:
        snippet = (
            c["current_text"][:40]
            + ("…" if len(c["current_text"]) > 40 else "")
        )
        print(f"  @{c['eid']}  type={c['type']} "
              f"current_text={snippet!r}")

    if dry_run:
        chosen = candidates[0]
        out = {
            "target_eid": chosen["eid"],
            "new_text": f"(dry-run) {chosen['current_text'][:20]}…",
            "rationale": "[dry-run] rephrased first candidate",
        }
        print(f"\nDry-run set: {json.dumps(out, indent=2)}")
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
            return 1
        import anthropic
        client = anthropic.Anthropic()
        llm_candidates = candidates[:10]
        tool_schema = _build_set_text_tool(
            [c["eid"] for c in llm_candidates],
        )
        user_prompt = (
            "### Text-edit candidates\n"
            + "\n".join(
                f"  - @{c['eid']}  type={c['type']}  "
                f"current_text={c['current_text']!r}"
                for c in llm_candidates
            )
            + "\n\nPick ONE text node and emit a `set text=\"...\"` "
            "that REPHRASES it sensibly. Stay in-domain; do not "
            "introduce new concepts. Avoid no-ops."
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
    new_text = out["new_text"]
    candidate_eids = {c["eid"] for c in candidates}
    if target_eid not in candidate_eids:
        print(f"Rejecting: target_eid {target_eid!r} not in "
              f"candidates.", file=sys.stderr)
        return 1
    current_for_target = next(
        (c["current_text"] for c in candidates
         if c["eid"] == target_eid),
        None,
    )
    if current_for_target == new_text:
        print(
            f"Rejecting: no-op (text unchanged).",
            file=sys.stderr,
        )
        return 1

    # Escape double quotes inside the string so the emitted L3
    # statement stays parseable.
    escaped = new_text.replace("\\", "\\\\").replace('"', '\\"')
    edit_src = f'set @{target_eid} text="{escaped}"\n'
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

    def _find_positional_text(nodes, target):
        for n in nodes:
            if hasattr(n, "head") and n.head.eid == target:
                pos = n.head.positional
                if pos is not None:
                    return getattr(pos, "py", None)
            if getattr(n, "block", None):
                sub = _find_positional_text(n.block.statements, target)
                if sub is not None:
                    return sub
        return None

    applied_text = _find_positional_text(applied.top_level, target_eid)
    print(f"\nApplied set at @{target_eid}: "
          f"new positional text = {applied_text!r}")
    if applied_text == new_text:
        print("SUCCESS: structural verify pass — positional matches.")
        conn.close()
        return 0
    print(f"FAIL: expected {new_text!r}, got {applied_text!r}",
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
