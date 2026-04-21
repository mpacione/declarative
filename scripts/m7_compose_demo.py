"""M7.6 S4 composition demo — compose a subtree into a donor screen.

Focuses on S4.2 per plan §4: "Compose a subtree into an existing
screen." The LLM receives a donor doc (compressed L3), a target
parent eid, a natural-language prompt, and the universal catalog
of appendable types. It emits one `append` statement whose block
contains multiple nested nodes — the "composed subtree."

Structural exit bar (per plan §4 S4): "produced unit renders
without hard failures; structural verify passes." We don't render
in this demo; the structural check confirms that the LLM-emitted
block parses, applies cleanly, and lands under the target parent
with the expected number of new children.

VLM fidelity (the v0.2 ≥0.728 baseline) is deferred — it needs a
render + screenshot + scorer path that's out of M7.6's initial
scope.

Out of scope for M7.6's first shipment:
- S4.1 compose-a-component (needs `define` grammar confirmation)
- S4.3 compose-a-screen-from-archetype (needs archetype+skeleton
  integration)
- S4.4 compose-a-screen-from-empty (pure SYNTHESIS)
- S4.5/S4.6 variant composition

Usage::

    .venv/bin/python3 -m scripts.m7_compose_demo \\
        --db Dank-EXP-02.declarative.db \\
        --prompt "add a confirmation toast with icon + message + dismiss" \\
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
    collect_parent_candidates,
    extract_tool_call,
)


_APPENDABLE_TYPES = (
    "frame", "text", "heading", "rectangle", "ellipse",
    "card", "container",
)


def _build_compose_tool_schema(
    parent_eids: list[str],
    types: tuple[str, ...] = _APPENDABLE_TYPES,
) -> dict:
    """Schema for one `append` whose block may contain multiple
    typed nodes, each with its own eid + optional text."""
    return {
        "name": "emit_compose_subtree",
        "description": (
            "Emit a single `append to=@parent { ... }` statement "
            "whose block contains 2-6 child nodes. The block may "
            "nest (a frame containing a heading + text)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "parent_eid": {
                    "type": "string", "enum": parent_eids,
                },
                "nodes": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": list(types),
                            },
                            "eid": {
                                "type": "string",
                                "pattern": "^[a-z][a-z0-9-]{1,38}$",
                            },
                            "text": {
                                "type": "string",
                                "maxLength": 120,
                                "description": (
                                    "Visible text. Required for "
                                    "text / heading; ignored for "
                                    "non-text types."
                                ),
                            },
                        },
                        "required": ["type", "eid"],
                    },
                },
                "rationale": {"type": "string"},
            },
            "required": ["parent_eid", "nodes", "rationale"],
        },
    }


def _compose_block_source(nodes: list[dict]) -> str:
    """Render the node list as an L3 block body (indented 2
    spaces). Only a single flat level is supported in this
    shipment — multi-level nesting would need a recursive
    schema."""
    lines = []
    for n in nodes:
        t = n["type"]
        e = n["eid"]
        tx = n.get("text", "")
        if t in ("text", "heading", "link") and tx:
            tx_esc = tx.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'  {t} #{e} "{tx_esc}"')
        else:
            lines.append(f"  {t} #{e}")
    return "\n".join(lines)


def _append_source(parent_eid: str, nodes: list[dict]) -> str:
    body = _compose_block_source(nodes)
    return f"append to=@{parent_eid} {{\n{body}\n}}\n"


def run_demo(db_path, *, screen_id, dry_run, prompt, model):
    from dd.compress_l3 import compress_to_l3_with_nid_map
    from dd.db import get_connection
    from dd.ir import generate_ir
    from dd.markup_l3 import apply_edits, parse_l3

    conn = get_connection(db_path)
    try:
        if screen_id is None:
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

        parents = collect_parent_candidates(doc)[:20]
        if not parents:
            print("No parent candidates.", file=sys.stderr)
            return 1
        print(f"Parent candidates: {len(parents)}")

        if dry_run:
            chosen = parents[0]
            call = {
                "parent_eid": chosen["eid"],
                "nodes": [
                    {
                        "type": "heading", "eid": "toast-title",
                        "text": "Uploaded",
                    },
                    {
                        "type": "text", "eid": "toast-message",
                        "text": "File saved successfully.",
                    },
                    {
                        "type": "rectangle", "eid": "toast-spacer",
                    },
                ],
                "rationale": "[dry-run] canned 3-node toast",
            }
        else:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print(
                    "ANTHROPIC_API_KEY not set.", file=sys.stderr,
                )
                return 1
            import anthropic
            client = anthropic.Anthropic()
            schema = _build_compose_tool_schema(
                [p["eid"] for p in parents],
            )
            user = (
                "### Parent candidates (pick one)\n"
                + "\n".join(
                    f"  - @{p['eid']} ({p['type']} "
                    f"children={p['child_count']})"
                    for p in parents
                )
                + f"\n\n### Prompt\n{prompt}\n\n"
                "Emit one `append` whose block composes a 2-6 "
                "node subtree that answers the prompt. Keep eids "
                "globally unique and kebab-case."
            )
            resp = client.messages.create(
                model=model,
                max_tokens=1200,
                system=(
                    "You compose small UI subtrees from a prompt. "
                    "Use only the supplied parent eids + "
                    "appendable types. Never invent eids that "
                    "might already exist on the donor."
                ),
                tools=[schema],
                tool_choice={
                    "type": "tool", "name": schema["name"],
                },
                messages=[{"role": "user", "content": user}],
            )
            call = extract_tool_call(resp, schema["name"])
            if call is None:
                print(
                    "LLM did not emit tool call.", file=sys.stderr,
                )
                return 1
        print(f"\nCompose call: {json.dumps(call, indent=2)}")

        src = _append_source(call["parent_eid"], call["nodes"])
        print(f"\nEdit source:\n{src}")

        try:
            edit_doc = parse_l3(src)
            applied = apply_edits(doc, list(edit_doc.edits))
        except Exception as e:
            print(f"parse/apply failed: {e}", file=sys.stderr)
            return 1

        # Structural verify: every requested child eid lives under
        # the parent after apply.
        want_eids = [n["eid"] for n in call["nodes"]]
        found: list[str] = []
        for node in _walk(applied):
            if (hasattr(node, "head")
                    and node.head.eid == call["parent_eid"]):
                block = getattr(node, "block", None)
                if block is not None:
                    for s in block.statements:
                        if (hasattr(s, "head")
                                and s.head.eid in want_eids):
                            found.append(s.head.eid)
                break

        missing = [e for e in want_eids if e not in found]
        print(
            f"\nStructural verify: requested={len(want_eids)} "
            f"landed={len(found)} missing={len(missing)}"
        )
        if missing:
            print(f"  missing eids: {missing}", file=sys.stderr)
            return 1

        # Additional structural checks (plan §4 S4 gate):
        # - every type in the composed subtree is a known
        #   grammar type (i.e., apply_edits didn't silently drop
        #   anything). apply_edits would have raised otherwise.
        # - if a token ref was used, it resolves. For M7.6 we
        #   don't emit token refs, so skip.

        print("\nM7.6 S4.2 SUCCESS: subtree composed + structural "
              "verify pass.")
        return 0
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
    parser.add_argument(
        "--prompt", default=(
            "Add a confirmation toast with a heading, a descriptive "
            "message, and a dismiss target."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--model", default="claude-haiku-4-5-20251001",
    )
    args = parser.parse_args(argv)
    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1
    return run_demo(
        args.db,
        screen_id=args.screen_id,
        dry_run=args.dry_run,
        prompt=args.prompt,
        model=args.model,
    )


if __name__ == "__main__":
    sys.exit(main())
