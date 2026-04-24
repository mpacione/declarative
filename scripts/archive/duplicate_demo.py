"""M7.4 S3.5 — duplicate-with-modifications demo.

Per plan §4 S3.5: "clone donor AST, apply edit sequence, verify."
Most common real designer workflow: take an existing screen, make
targeted changes, save as a new variant.

The demo chains the S1+S2 verbs together in a single apply_edits
call. Donor = the compressed L3 for a Dank screen. Edits = a
small curated sequence (Claude Haiku picks the specifics) that
exercises multiple verbs. Verify = every targeted edit landed.

Usage::

    .venv/bin/python3 -m scripts.duplicate_demo \\
        --db Dank-EXP-02.declarative.db [--screen-id 186] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from dd.structural_verbs import (
    collect_parent_candidates,
    collect_removable_candidates,
    extract_tool_call,
    unique_eids,
    verify_appended,
    verify_deleted,
)


def _build_duplicate_tool_schema(
    removable_eids: list[str],
    parent_eids: list[str],
    text_eids: list[str],
) -> dict:
    return {
        "name": "emit_duplicate_plan",
        "description": (
            "Emit a 3-edit plan that duplicates a screen with small "
            "modifications: delete one non-critical node, append a "
            "new text child to a container, rewrite one existing "
            "text. All references must be globally-unique eids "
            "from the supplied enums."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "delete_target_eid": {
                    "type": "string",
                    "enum": removable_eids,
                },
                "append_parent_eid": {
                    "type": "string",
                    "enum": parent_eids,
                },
                "new_child_eid": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9-]{1,38}$",
                },
                "new_child_text": {
                    "type": "string",
                    "minLength": 1, "maxLength": 80,
                },
                "text_target_eid": {
                    "type": "string",
                    "enum": text_eids,
                },
                "new_text": {
                    "type": "string",
                    "minLength": 1, "maxLength": 80,
                },
                "rationale": {"type": "string"},
            },
            "required": [
                "delete_target_eid", "append_parent_eid",
                "new_child_eid", "new_child_text",
                "text_target_eid", "new_text", "rationale",
            ],
        },
    }


def _collect_text_candidates(doc) -> list[dict]:
    """Text-bearing nodes with positional content — same shape as
    m7_set_text_demo's filter."""
    from collections import Counter
    counts: Counter = Counter()
    found: list[dict] = []
    text_types = frozenset({"text", "heading", "link"})

    def go(ns):
        for n in ns:
            if hasattr(n, "head") and n.head.eid:
                counts[n.head.eid] += 1
                if n.head.type_or_path in text_types:
                    pos = n.head.positional
                    if (pos is not None
                            and getattr(pos, "lit_kind", None) == "string"):
                        py = pos.py
                        if isinstance(py, str) and py.strip():
                            found.append({
                                "eid": n.head.eid,
                                "type": n.head.type_or_path,
                                "current_text": py,
                            })
            if getattr(n, "block", None):
                go(n.block.statements)

    go(doc.top_level)
    return [f for f in found if counts[f["eid"]] == 1]


def run_demo(db_path, *, screen_id, dry_run):
    from dd.compress_l3 import compress_to_l3_with_nid_map
    from dd.db import get_connection
    from dd.ir import generate_ir
    from dd.markup_l3 import apply_edits, parse_l3

    conn = get_connection(db_path)
    try:
        if screen_id is None:
            # Prefer a screen that has text content to rewrite.
            row = conn.execute(
                """
                SELECT s.id FROM screens s
                WHERE s.screen_type='app_screen'
                ORDER BY (SELECT COUNT(*) FROM nodes
                          WHERE screen_id=s.id) ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                print("No app_screen found.", file=sys.stderr)
                return 1
            screen_id = row[0]
        print(f"Donor screen: {screen_id}")

        ir = generate_ir(conn, screen_id, semantic=True)
        spec = ir.get("spec") if "spec" in ir else ir
        doc, _ = compress_to_l3_with_nid_map(
            spec, conn, screen_id=screen_id,
        )

        removable = collect_removable_candidates(doc)
        parents = collect_parent_candidates(doc)
        text_candidates = _collect_text_candidates(doc)
        if not removable or not parents or not text_candidates:
            print(
                "Donor doesn't have the three prerequisite "
                "candidate kinds; try a different screen.",
                file=sys.stderr,
            )
            return 1

        if dry_run:
            call = {
                "delete_target_eid": removable[0]["eid"],
                "append_parent_eid": parents[0]["eid"],
                "new_child_eid": "new-note",
                "new_child_text": "Duplicate variant",
                "text_target_eid": text_candidates[0]["eid"],
                "new_text": "Updated title",
                "rationale": "[dry-run] canned 3-edit plan",
            }
        else:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
                return 1
            import anthropic
            client = anthropic.Anthropic()
            schema = _build_duplicate_tool_schema(
                [c["eid"] for c in removable[:20]],
                [p["eid"] for p in parents[:20]],
                [t["eid"] for t in text_candidates[:20]],
            )
            user = (
                "### Removable candidates\n"
                + "\n".join(
                    f"  - @{c['eid']} ({c['type']})"
                    for c in removable[:10]
                ) + "\n"
                "### Parent candidates\n"
                + "\n".join(
                    f"  - @{p['eid']} ({p['type']})"
                    for p in parents[:10]
                ) + "\n"
                "### Text candidates\n"
                + "\n".join(
                    f"  - @{t['eid']} text={t['current_text']!r}"
                    for t in text_candidates[:10]
                ) + "\n\n"
                "Emit a 3-edit duplicate-with-mods plan via "
                "`emit_duplicate_plan`. Keep changes small and "
                "defensible."
            )
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                system=(
                    "You duplicate an existing screen with small "
                    "targeted changes (delete one node, append "
                    "one, rewrite one text). Keep the donor's "
                    "overall shape."
                ),
                tools=[schema],
                tool_choice={
                    "type": "tool", "name": schema["name"],
                },
                messages=[{"role": "user", "content": user}],
            )
            call = extract_tool_call(resp, schema["name"])
            if call is None:
                print("LLM did not emit the plan.", file=sys.stderr)
                return 1
        print(f"\nDuplicate plan: {json.dumps(call, indent=2)}")

        # Compose all three edits in one apply_edits sequence.
        edit_src = (
            f"delete @{call['delete_target_eid']}\n"
            f'append to=@{call["append_parent_eid"]} {{\n'
            f'  text #{call["new_child_eid"]} '
            f'"{call["new_child_text"]}"\n'
            "}\n"
            f'set @{call["text_target_eid"]} '
            f'text="{call["new_text"]}"\n'
        )
        edit_doc = parse_l3(edit_src)
        applied = apply_edits(doc, list(edit_doc.edits))

        ok_del = verify_deleted(applied, call["delete_target_eid"])
        ok_app = verify_appended(
            applied, call["append_parent_eid"], call["new_child_eid"],
        )
        # Verify text rewrite via positional
        ok_text = False
        for n in _walk(applied):
            if (hasattr(n, "head")
                    and n.head.eid == call["text_target_eid"]
                    and n.head.positional is not None
                    and n.head.positional.py == call["new_text"]):
                ok_text = True
                break

        print(
            f"\nVerify: delete={ok_del} append={ok_app} "
            f"text_rewrite={ok_text}"
        )
        if ok_del and ok_app and ok_text:
            print(
                "\nM7.4 S3.5 SUCCESS: all three edits landed in "
                "the duplicated doc."
            )
            return 0
        print("\nM7.4 S3.5 FAIL", file=sys.stderr)
        return 1
    finally:
        conn.close()


def _walk(doc):
    out = []

    def go(ns):
        for n in ns:
            if hasattr(n, "head"):
                out.append(n)
            if getattr(n, "block", None):
                go(n.block.statements)

    go(doc.top_level)
    return out


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument("--screen-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1
    return run_demo(
        args.db, screen_id=args.screen_id, dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
