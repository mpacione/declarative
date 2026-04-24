"""M7.0.a judgment-point tooling — preview the proposed LLM
classification prompt against real Dank nodes, without actually
calling Claude.

Run:
    python3 scripts/preview_llm_classify_prompt.py --screen 181 --n 5

Emits the full prompt text to stdout. Inspect it; decide whether
the shape is right before wiring it into ``dd.classify_llm`` and
running on the full 204 corpus.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dd.classify_rules import is_system_chrome  # noqa: E402

DB_PATH = ROOT / "Dank-EXP-02.declarative.db"


# Structured output schema for the LLM's tool response. Matches
# Decision 10 — Claude tool-use for M7.0 labeling work.
CLASSIFY_TOOL_SCHEMA = {
    "name": "classify_nodes",
    "description": (
        "Return a classification for every node in the batch. "
        "Each classification names the canonical UI component type "
        "the node represents, a confidence score, and a short "
        "reason. Use `container` when the node is a structural "
        "layout frame with no specific component identity. Use "
        "`unsure` when the node's identity cannot be determined "
        "from the provided information — do NOT invent a "
        "classification to avoid this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "integer"},
                        "canonical_type": {"type": "string"},
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "One short sentence explaining the "
                                "signals that led to this classification. "
                                "Evidence-based; no speculation."
                            ),
                        },
                    },
                    "required": [
                        "node_id", "canonical_type",
                        "confidence", "reason",
                    ],
                },
            },
        },
        "required": ["classifications"],
    },
}


def _load_catalog(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT canonical_name, category, behavioral_description "
        "FROM component_type_catalog "
        "ORDER BY category, canonical_name"
    ).fetchall()
    return [
        {"name": r[0], "category": r[1], "description": r[2]}
        for r in rows
    ]


def _format_catalog_for_prompt(catalog: list[dict]) -> str:
    """Group canonical types by category, emit one per line with
    its behavioral description — gives the LLM the vocabulary +
    semantics in a shape it can scan.
    """
    by_cat: dict[str, list[dict]] = {}
    for entry in catalog:
        by_cat.setdefault(entry["category"], []).append(entry)
    lines = []
    for cat in sorted(by_cat.keys()):
        lines.append(f"\n**{cat}**")
        for entry in sorted(by_cat[cat], key=lambda e: e["name"]):
            lines.append(f"- `{entry['name']}` — {entry['description']}")
    lines.append("- `container` — a structural layout frame with no specific component identity.")
    lines.append("- `unsure` — identity cannot be determined from the provided information.")
    return "\n".join(lines)


def _fetch_nodes(
    conn: sqlite3.Connection, screen_id: int, n: int,
) -> list[dict]:
    """Fetch up to N unclassified FRAME/INSTANCE/COMPONENT nodes
    on the given screen, with context needed for the prompt:
    parent classification (if any), sibling count, children-type
    distribution.
    """
    cursor = conn.execute(
        """
        SELECT n.id, n.name, n.node_type, n.depth, n.width, n.height,
               n.y, n.layout_mode, n.parent_id, n.component_key
        FROM nodes n
        LEFT JOIN screen_component_instances sci
          ON sci.node_id = n.id AND sci.screen_id = n.screen_id
        WHERE n.screen_id = ?
          AND n.node_type IN ('FRAME', 'INSTANCE', 'COMPONENT')
          AND n.depth >= 1
          AND sci.id IS NULL
        ORDER BY n.depth, n.sort_order
        """,
        (screen_id,),
    )
    raw = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
    # Mirror production filter: system chrome is excluded before the LLM sees it.
    rows = [r for r in raw if not is_system_chrome(r["name"])][:n]

    # Enrich with parent classification + child content hints.
    for r in rows:
        pid = r["parent_id"]
        if pid is not None:
            pr = conn.execute(
                "SELECT name, node_type, canonical_type "
                "FROM nodes n "
                "LEFT JOIN screen_component_instances sci "
                "  ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
                "WHERE n.id = ?",
                (pid,),
            ).fetchone()
            r["parent_name"] = pr[0] if pr else None
            r["parent_type"] = pr[1] if pr else None
            r["parent_classified_as"] = pr[2] if pr else None
        else:
            r["parent_name"] = r["parent_type"] = r["parent_classified_as"] = None

        children = conn.execute(
            """
            SELECT n.node_type, COUNT(*) as cnt
            FROM nodes n
            WHERE n.parent_id = ?
            GROUP BY n.node_type
            """,
            (r["id"],),
        ).fetchall()
        r["child_type_dist"] = dict(children) if children else {}
        r["total_children"] = sum(c[1] for c in children) if children else 0

        # A sample text child (first in sort_order), if any — the
        # actual rendered content carries strong classification signal
        # (e.g. "Sign in" suggests button; "Welcome back" suggests heading).
        text_child = conn.execute(
            """
            SELECT text_content FROM nodes
            WHERE parent_id = ? AND node_type = 'TEXT'
              AND text_content IS NOT NULL AND text_content != ''
            ORDER BY sort_order LIMIT 1
            """,
            (r["id"],),
        ).fetchone()
        r["sample_text"] = text_child[0] if text_child else None

        # CKR registered name (enables the LLM to see the master
        # component identity even when the node's name was overridden).
        if r.get("component_key"):
            ckr_row = conn.execute(
                "SELECT name FROM component_key_registry "
                "WHERE component_key = ?",
                (r["component_key"],),
            ).fetchone()
            r["ckr_registered_name"] = ckr_row[0] if ckr_row else None
        else:
            r["ckr_registered_name"] = None
    return rows


def _describe_node(node: dict) -> str:
    parts = [
        f"- **node_id={node['id']}**",
        f'name="{node["name"]}"',
        f"type={node['node_type']}",
        f"depth={node['depth']}",
        f"size={int(node.get('width') or 0)}×{int(node.get('height') or 0)}",
    ]
    if node.get("layout_mode"):
        parts.append(f"layout={node['layout_mode']}")
    if node.get("total_children"):
        parts.append(
            f"children={node['total_children']} "
            f"({', '.join(f'{k}:{v}' for k, v in node['child_type_dist'].items())})"
        )
    if node.get("sample_text"):
        t = node["sample_text"][:60]
        parts.append(f'sample_text="{t}"')
    if node.get("parent_classified_as"):
        parts.append(f"parent={node['parent_classified_as']}")
    elif node.get("parent_name"):
        parts.append(f'parent="{node["parent_name"]}"')
    if node.get("component_key"):
        if node.get("ckr_registered_name"):
            parts.append(
                f"component_key=\"{node['ckr_registered_name']}\""
            )
        else:
            parts.append("component_key=(not in CKR)")
    return ", ".join(parts)


def build_prompt(
    conn: sqlite3.Connection, screen_id: int, nodes: list[dict],
) -> str:
    catalog = _load_catalog(conn)
    screen = conn.execute(
        "SELECT name, width, height FROM screens WHERE id = ?",
        (screen_id,),
    ).fetchone()
    sname, swidth, sheight = screen

    skeleton = conn.execute(
        "SELECT skeleton_notation, skeleton_type FROM screen_skeletons "
        "WHERE screen_id = ? LIMIT 1",
        (screen_id,),
    ).fetchone()
    skel_line = (
        f"Screen skeleton: `{skeleton[0]}` ({skeleton[1] or 'untyped'})"
        if skeleton else
        "Screen skeleton: (not yet extracted)"
    )

    catalog_block = _format_catalog_for_prompt(catalog)
    node_descriptions = "\n".join(_describe_node(n) for n in nodes)

    return f"""You are classifying UI nodes from a Figma design file against a fixed catalog of canonical component types. This classification feeds a design-system compiler — accuracy matters, and "unsure" is a valid answer.

## Screen context

Screen: **{sname}** ({int(swidth)}×{int(sheight)})
{skel_line}

## Canonical types (pick exactly one per node)

Use the behavioral description to disambiguate. The UI component that matches the *function* of the node wins, not the one that merely looks similar.
{catalog_block}

## Rules

1. **Pick one canonical type per node** from the list above. `container` and `unsure` are valid choices but prefer a specific type when evidence supports it.
2. **Confidence is calibrated.** 0.95+ = unambiguous (a button labeled "Sign in" with button-shaped layout). 0.8 = strong signal but one ambiguity (could be a card or a dialog). 0.6 = weak signal; verification recommended. Below 0.6 — prefer `unsure` with a reason.
3. **Use parent/sibling context.** A node inside a `bottom_nav` is likely a `navigation_row`, not a button. A node inside a `card` at the top is likely `heading`, not a random text.
4. **Sample text content is a strong signal** — "Sign in" is a button, "Welcome back" is a heading, "Forgot password?" is a link.
5. **Reasons are evidence-based, not speculation.** One sentence, citing the signals (layout, text, parent, size). "Assumed to be a card" is bad; "Vertical auto-layout with image at top, heading, and action row" is good.

## Nodes to classify

{node_descriptions}

Return your classifications via the `classify_nodes` tool. Every node in the batch must appear in the response exactly once."""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--screen", type=int, required=True,
                    help="screens.id to classify nodes from")
    ap.add_argument("--n", type=int, default=5,
                    help="Number of unclassified nodes to sample")
    ap.add_argument("--emit-schema", action="store_true",
                    help="Also emit the tool schema as JSON")
    args = ap.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    nodes = _fetch_nodes(conn, args.screen, args.n)
    if not nodes:
        print(f"No unclassified candidate nodes on screen {args.screen}.", file=sys.stderr)
        return 1

    prompt = build_prompt(conn, args.screen, nodes)
    print(prompt)

    if args.emit_schema:
        print("\n\n---\n## TOOL SCHEMA\n")
        print(json.dumps(CLASSIFY_TOOL_SCHEMA, indent=2))

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
