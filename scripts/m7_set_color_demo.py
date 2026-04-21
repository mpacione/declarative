"""M7.3 S1.3 demo — change a node's fill to a token-ref via Claude.

Fourth LLM-in-loop verb after ``swap`` (M7.2), ``set radius`` (S1.4),
and ``set visible`` (S1.2). Plan §6 constraint 2 — "no raw values in
synthesised IR" — means the emitted statement has shape
``set @X fill={color.foo.bar}``, a TokenRef, not a hex literal.

Dank's token table is empty (``binding_status='unbound'`` on every
row of ``node_token_bindings``), so this demo uses a synthesised
palette — six well-named canonical tokens from Material 3 / HIG
conventions that would reasonably appear in any design-system: ::

    color.brand.primary
    color.brand.secondary
    color.semantic.destructive
    color.surface.elevated
    color.surface.subtle
    color.content.emphasis

The palette is a fixed enum on the tool schema so the LLM can't
invent a token name that won't exist downstream. A real project with
populated tokens would pull its vocabulary from the DB instead.

Pattern matches ``m7_set_radius_demo.py`` / ``m7_set_visibility_demo.py``:

1. Compress a Dank screen to L3.
2. Collect eid-bearing nodes that have a current ``fill`` prop whose
   value is either a hex literal or a TokenRef — those are the ones
   whose fill is concretely known and can be meaningfully flipped.
3. Ask Claude Haiku to pick ONE candidate + one token from the
   synthesised palette.
4. Parse ``set @X fill={color.foo.bar}`` as L3; apply via
   ``dd.markup_l3.apply_edits``.
5. Verify structurally: the target eid's ``fill`` property now equals
   the requested TokenRef path.

Usage::

    .venv/bin/python3 -m scripts.m7_set_color_demo \\
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


# Synthesised palette. Each entry is canonical in Material 3 or Apple
# HIG conventions; the names are generic enough to read sensibly in
# any UI context. Pinned as an enum on the tool schema.
_PALETTE: tuple[str, ...] = (
    "color.brand.primary",
    "color.brand.secondary",
    "color.semantic.destructive",
    "color.surface.elevated",
    "color.surface.subtle",
    "color.content.emphasis",
)


def _build_set_color_tool(
    candidate_eids: list[str], palette: tuple[str, ...],
) -> dict:
    return {
        "name": "emit_set_color",
        "description": (
            "Emit one `set` statement that updates the target "
            "node's `fill` property to a TokenRef from the palette."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_eid": {
                    "type": "string",
                    "enum": candidate_eids,
                    "description": "Target eid (no leading `@`).",
                },
                "new_fill_token": {
                    "type": "string",
                    "enum": list(palette),
                    "description": (
                        "Token path to bind to the node's fill. "
                        "Emitted as `{<path>}` in the edit source."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "One-sentence reason for the pick.",
                },
            },
            "required": [
                "target_eid", "new_fill_token", "rationale",
            ],
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


def _current_fill_description(head) -> str | None:
    """Return a human-readable description of the node's current
    fill: hex literal, TokenRef path, or None when neither is set.
    The TokenRef case is the signal we're flipping one bound token
    for another; the hex case is first-time binding.

    TokenRef exposes ``.path`` (``color.brand.primary``) directly on
    the value object; Literal_ exposes ``.py`` (the decoded string
    like ``#FF0000``).
    """
    for p in getattr(head, "properties", ()) or ():
        if getattr(p, "key", None) != "fill":
            continue
        val = p.value
        if getattr(val, "kind", None) == "token-ref":
            return f"token={val.path}"
        py = getattr(val, "py", None)
        if isinstance(py, str) and py.startswith("#"):
            return f"hex={py}"
        # Could be image / gradient / other — skip as non-flippable
        return None
    return None


def _collect_color_candidates(doc):
    """Eid-bearing nodes with a concrete fill. Only GLOBALLY UNIQUE
    eids are returned — duplicates would fire
    ``KIND_AMBIGUOUS_EREF`` at ``apply_edits`` time (the ``set @X``
    resolution walks by bare eid, not dotted path)."""
    counts: dict[str, int] = {}
    found: list[dict] = []

    def _walk(nodes):
        for n in nodes:
            if hasattr(n, "head") and n.head.eid:
                counts[n.head.eid] = counts.get(n.head.eid, 0) + 1
                descr = _current_fill_description(n.head)
                if descr:
                    found.append({
                        "eid": n.head.eid,
                        "type": n.head.type_or_path,
                        "current_fill": descr,
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

    candidates = _collect_color_candidates(doc)
    if not candidates:
        print(
            "No eid-bearing nodes with a concrete fill (hex or token).",
            file=sys.stderr,
        )
        return 1
    print(f"Fill candidates: {len(candidates)}")
    for c in candidates[:5]:
        print(f"  @{c['eid']}  type={c['type']} "
              f"current_fill={c['current_fill']}")
    print(f"Palette: {len(_PALETTE)} tokens")

    if dry_run:
        chosen = candidates[0]
        # Flip to something that's NOT the current binding — pick
        # the first palette token whose path doesn't match the
        # current's token path (if any).
        current_token = None
        if chosen["current_fill"].startswith("token="):
            current_token = chosen["current_fill"][len("token="):]
        alt = next(
            (t for t in _PALETTE if t != current_token),
            None,
        )
        if alt is None:
            print(
                "Palette only has the current token — nothing to flip to.",
                file=sys.stderr,
            )
            return 1
        out = {
            "target_eid": chosen["eid"],
            "new_fill_token": alt,
            "rationale": "[dry-run] picked first non-matching token",
        }
        print(f"\nDry-run set: {json.dumps(out, indent=2)}")
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
            return 1
        import anthropic
        client = anthropic.Anthropic()
        llm_candidates = candidates[:10]
        tool_schema = _build_set_color_tool(
            [c["eid"] for c in llm_candidates], _PALETTE,
        )
        user_prompt = (
            "### Fill-edit candidates\n"
            + "\n".join(
                f"  - @{c['eid']}  type={c['type']}  "
                f"current_fill={c['current_fill']}"
                for c in llm_candidates
            )
            + "\n\n### Palette\n"
            + "\n".join(f"  - {t}" for t in _PALETTE)
            + "\n\nPick ONE candidate and bind its fill to a token "
            "from the palette. Avoid no-ops: if a candidate is "
            "already bound to a palette token, pick a DIFFERENT one."
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
    new_token = out["new_fill_token"].strip()
    candidate_eids = {c["eid"] for c in candidates}
    if target_eid not in candidate_eids:
        print(f"Rejecting: target_eid {target_eid!r} not in "
              f"candidates.", file=sys.stderr)
        return 1
    if new_token not in _PALETTE:
        print(f"Rejecting: token {new_token!r} not in palette.",
              file=sys.stderr)
        return 1
    current_for_target = next(
        (c["current_fill"] for c in candidates
         if c["eid"] == target_eid),
        None,
    )
    if current_for_target == f"token={new_token}":
        print(
            f"Rejecting: no-op (already bound to {new_token}).",
            file=sys.stderr,
        )
        return 1

    edit_src = f"set @{target_eid} fill={{{new_token}}}\n"
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

    def _find_fill_token(nodes, target):
        for n in nodes:
            if hasattr(n, "head") and n.head.eid == target:
                for p in getattr(n.head, "properties", ()) or ():
                    if getattr(p, "key", None) == "fill":
                        val = p.value
                        if getattr(val, "kind", None) == "token-ref":
                            return val.path
                        return None
            if getattr(n, "block", None):
                sub = _find_fill_token(n.block.statements, target)
                if sub is not None:
                    return sub
        return None

    applied_token = _find_fill_token(applied.top_level, target_eid)
    print(f"\nApplied set at @{target_eid}: "
          f"new fill token = {applied_token!r}")
    if applied_token == new_token:
        print("SUCCESS: structural verify pass — fill token matches.")
        conn.close()
        return 0
    print(f"FAIL: expected {new_token!r}, got {applied_token!r}",
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
