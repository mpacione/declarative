"""M7.4 S2 tier LLM-in-loop demo — delete / append / insert / move.

One script, four verbs. Pattern matches the S1-tier demos:
compress → collect candidates → Claude Haiku picks via tool-use →
parse as L3 → apply → structurally verify the tree changed as
expected.

Usage::

    .venv/bin/python3 -m scripts.m7_structural_edit_demo \\
        --db Dank-EXP-02.declarative.db \\
        --verb delete \\
        [--screen-id 183] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from dd.structural_verbs import (
    build_append_tool_schema,
    build_delete_tool_schema,
    build_insert_tool_schema,
    build_move_tool_schema,
    collect_insert_candidates,
    collect_move_candidates,
    collect_parent_candidates,
    collect_removable_candidates,
    extract_tool_call,
    verify_appended,
    verify_deleted,
    verify_inserted,
    verify_moved,
)


def _pick_screen(conn) -> int:
    row = conn.execute(
        """
        SELECT s.id FROM screens s
        WHERE s.screen_type = 'app_screen'
        ORDER BY (SELECT COUNT(*) FROM nodes WHERE screen_id = s.id) ASC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        print("No app_screen found.", file=sys.stderr)
        return 1
    return row[0]


def _call_llm(client, schema, system, user, model):
    resp = client.messages.create(
        model=model, max_tokens=512,
        system=system,
        tools=[schema],
        tool_choice={"type": "tool", "name": schema["name"]},
        messages=[{"role": "user", "content": user}],
    )
    return extract_tool_call(resp, schema["name"])


def _run_delete(doc, client, dry_run, model):
    cands = collect_removable_candidates(doc)
    if not cands:
        return None, "no removable candidates"
    schema = build_delete_tool_schema([c["eid"] for c in cands[:20]])
    rendered = "\n".join(
        f"  - @{c['eid']} (type={c['type']} parent={c['parent_eid']})"
        for c in cands[:20]
    )
    user = (
        f"### Deletable candidates (max 20)\n{rendered}\n\n"
        "Pick one and emit `delete @X` via `emit_delete_edit`."
    )
    if dry_run:
        chosen = cands[0]
        call = {
            "target_eid": chosen["eid"],
            "rationale": "[dry-run] deleted first candidate",
        }
    else:
        call = _call_llm(
            client, schema,
            "You remove a non-critical node from the screen.",
            user, model,
        )
    if not call:
        return None, "LLM did not emit tool call"
    src = f"delete @{call['target_eid']}\n"
    return call, src


def _run_append(doc, client, dry_run, model):
    cands = collect_parent_candidates(doc)
    if not cands:
        return None, "no parent candidates"
    schema = build_append_tool_schema(
        [c["eid"] for c in cands[:20]]
    )
    rendered = "\n".join(
        f"  - @{c['eid']} (type={c['type']} children={c['child_count']})"
        for c in cands[:20]
    )
    user = (
        f"### Parent candidates (max 20)\n{rendered}\n\n"
        "Append one new child via `emit_append_edit`. Pick "
        "a globally-unique kebab-case child_eid (no @)."
    )
    if dry_run:
        chosen = cands[0]
        call = {
            "parent_eid": chosen["eid"],
            "child_type": "text",
            "child_eid": "dry-run-child",
            "child_text": "dry-run text",
            "rationale": "[dry-run] appended first candidate",
        }
    else:
        call = _call_llm(
            client, schema,
            "You append a new text/heading/frame to a parent node.",
            user, model,
        )
    if not call:
        return None, "LLM did not emit tool call"
    ctype = call["child_type"]
    ceid = call["child_eid"]
    src = (
        f'append to=@{call["parent_eid"]} {{\n'
        f'  {ctype} #{ceid} "{call["child_text"]}"\n'
        "}\n"
    )
    return call, src


def _run_insert(doc, client, dry_run, model):
    pairs = collect_insert_candidates(doc)
    if not pairs:
        return None, "no insert pairs"
    pairs = pairs[:20]
    schema = build_insert_tool_schema(pairs)
    rendered = "\n".join(
        f"  - [{i}] parent=@{p['parent_eid']} ({p['parent_type']}) "
        f"anchor=@{p['anchor_eid']} ({p['anchor_type']})"
        for i, p in enumerate(pairs)
    )
    user = (
        f"### Parent+anchor pairs\n{rendered}\n\n"
        "Insert a new sibling after the anchor via "
        "`emit_insert_edit`."
    )
    if dry_run:
        call = {
            "pair_index": 0,
            "child_type": "text",
            "child_eid": "dry-run-insert",
            "child_text": "inserted text",
            "rationale": "[dry-run] inserted after first anchor",
        }
    else:
        call = _call_llm(
            client, schema,
            "You insert a new sibling into an existing block.",
            user, model,
        )
    if not call:
        return None, "LLM did not emit tool call"
    pair = pairs[call["pair_index"]]
    ctype = call["child_type"]
    ceid = call["child_eid"]
    src = (
        f'insert into=@{pair["parent_eid"]} '
        f'after=@{pair["anchor_eid"]} {{\n'
        f'  {ctype} #{ceid} "{call["child_text"]}"\n'
        "}\n"
    )
    return {**call, "_pair": pair}, src


def _run_move(doc, client, dry_run, model):
    pairs = collect_move_candidates(doc)
    if not pairs:
        return None, "no move pairs"
    pairs = pairs[:20]
    schema = build_move_tool_schema(pairs)
    rendered = "\n".join(
        f"  - [{i}] move @{p['target_eid']} ({p['target_type']}) "
        f"to @{p['dest_eid']} ({p['dest_type']})"
        for i, p in enumerate(pairs)
    )
    user = (
        f"### Move pairs\n{rendered}\n\n"
        "Relocate the target into the destination."
    )
    if dry_run:
        call = {
            "pair_index": 0, "position": "last",
            "rationale": "[dry-run] moved first pair",
        }
    else:
        call = _call_llm(
            client, schema,
            "You relocate a node to a different parent.",
            user, model,
        )
    if not call:
        return None, "LLM did not emit tool call"
    pair = pairs[call["pair_index"]]
    src = (
        f"move @{pair['target_eid']} to=@{pair['dest_eid']} "
        f"position={call['position']}\n"
    )
    return {**call, "_pair": pair}, src


_VERB_RUNNERS = {
    "delete": _run_delete,
    "append": _run_append,
    "insert": _run_insert,
    "move": _run_move,
}


def _verify(verb: str, applied, call: dict) -> bool:
    if verb == "delete":
        return verify_deleted(applied, call["target_eid"])
    if verb == "append":
        return verify_appended(
            applied, call["parent_eid"], call["child_eid"],
        )
    if verb == "insert":
        pair = call["_pair"]
        return verify_inserted(
            applied, pair["parent_eid"], pair["anchor_eid"],
            call["child_eid"],
        )
    if verb == "move":
        pair = call["_pair"]
        return verify_moved(
            applied, pair["target_eid"], pair["dest_eid"],
            call["position"],
        )
    return False


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument("--screen-id", type=int, default=None)
    parser.add_argument(
        "--verb", choices=list(_VERB_RUNNERS),
        required=True,
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--model", default="claude-haiku-4-5-20251001",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    from dd.compress_l3 import compress_to_l3_with_nid_map
    from dd.db import get_connection
    from dd.ir import generate_ir
    from dd.markup_l3 import apply_edits, parse_l3

    conn = get_connection(args.db)
    try:
        screen_id = args.screen_id or _pick_screen(conn)
        if not isinstance(screen_id, int):
            return 1
        print(f"Screen: {screen_id}  verb: {args.verb}")

        ir = generate_ir(conn, screen_id, semantic=True)
        spec = ir.get("spec") if "spec" in ir else ir
        doc, _ = compress_to_l3_with_nid_map(
            spec, conn, screen_id=screen_id,
        )

        client = None
        if not args.dry_run:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
                return 1
            import anthropic
            client = anthropic.Anthropic()

        runner = _VERB_RUNNERS[args.verb]
        call, edit_src = runner(doc, client, args.dry_run, args.model)
        if call is None:
            print(f"Demo aborted: {edit_src}", file=sys.stderr)
            return 1
        print(f"\nEdit source:\n{edit_src}")
        print(
            f"Tool call: {json.dumps({k:v for k,v in call.items() if not k.startswith('_')}, indent=2)}"
        )

        edit_doc = parse_l3(edit_src)
        applied = apply_edits(doc, list(edit_doc.edits))

        ok = _verify(args.verb, applied, call)
        if ok:
            print(
                f"\nSUCCESS: structural verify pass — {args.verb} "
                "landed as expected."
            )
            return 0
        print(
            f"\nFAIL: structural verify — {args.verb} did not land.",
            file=sys.stderr,
        )
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
