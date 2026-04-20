"""LLM classification for ambiguous nodes (T5 Phase 1b, Step 3).

Uses Claude Haiku with tool-use (structured output) to classify nodes
that formal matching and heuristics couldn't resolve. The prompt
embeds the full canonical-type catalog (with behavioral descriptions
grouped by category) plus per-node context (parent classification,
child-type distribution, sample text, CKR-registered name when the
node has a component_key).

M7.0.a uses this stage as the primary judgment-based classifier for
the ~7K unclassified FRAME/INSTANCE/COMPONENT nodes that the formal
+ heuristic stages cannot resolve.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from dd.catalog import get_catalog
from dd.classify_rules import is_system_chrome


_LLM_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_LLM_CONFIDENCE = 0.7


# Tool schema for structured classification output. Claude is
# required (via tool_choice) to emit a JSON object matching this
# schema — no free-text parsing, no regex rescue paths.
CLASSIFY_TOOL_SCHEMA = {
    "name": "classify_nodes",
    "description": (
        "Return a classification for every node in the batch. Each "
        "entry names the canonical UI component type the node "
        "represents, a calibrated confidence (0.0-1.0), and a one-"
        "sentence evidence-based reason. Use `container` when the "
        "node is a structural layout frame with no specific "
        "component identity. Use `unsure` when the node's identity "
        "cannot be determined from the provided information — do "
        "NOT invent a classification to avoid this answer."
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
                                "One short sentence citing the signals "
                                "that led to this classification "
                                "(layout, text, parent, size, etc.). "
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


def _format_catalog_for_prompt(catalog: list[dict[str, Any]]) -> str:
    """Render the catalog by category with one line per type.

    Grouping by category makes the ~55-line block scannable for the
    LLM. The behavioral_description column (seeded in
    ``dd.catalog``) provides the semantic hint that disambiguates
    visually-similar types (button vs. icon_button, card vs.
    dialog, etc.).
    """
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for entry in catalog:
        by_cat.setdefault(entry["category"], []).append(entry)
    lines: list[str] = []
    for cat in sorted(by_cat.keys()):
        lines.append(f"\n**{cat}**")
        for entry in sorted(by_cat[cat], key=lambda e: e["canonical_name"]):
            desc = entry.get("behavioral_description") or "(no description)"
            lines.append(f"- `{entry['canonical_name']}` — {desc}")
    lines.append(
        "- `container` — a structural layout frame with no specific "
        "component identity."
    )
    lines.append(
        "- `unsure` — identity cannot be determined from the provided "
        "information."
    )
    return "\n".join(lines)


def _describe_node(node: dict[str, Any]) -> str:
    parts = [
        f"- **node_id={node['node_id']}**",
        f'name="{node["name"]}"',
        f"type={node['node_type']}",
        f"depth={node.get('depth', '?')}",
        f"size={int(node.get('width') or 0)}×{int(node.get('height') or 0)}",
    ]
    if node.get("layout_mode"):
        parts.append(f"layout={node['layout_mode']}")
    total_children = node.get("total_children")
    if total_children:
        dist = node.get("child_type_dist") or {}
        parts.append(
            f"children={total_children} "
            f"({', '.join(f'{k}:{v}' for k, v in dist.items())})"
        )
    if node.get("sample_text"):
        t = str(node["sample_text"])[:60]
        parts.append(f'sample_text="{t}"')
    if node.get("parent_classified_as"):
        parts.append(f"parent={node['parent_classified_as']}")
    elif node.get("parent_name"):
        parts.append(f'parent="{node["parent_name"]}"')
    if node.get("component_key"):
        if node.get("ckr_registered_name"):
            parts.append(f'component_key="{node["ckr_registered_name"]}"')
        else:
            parts.append("component_key=(not in CKR)")
    return ", ".join(parts)


def build_classification_prompt(
    nodes: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    screen_name: str,
    screen_width: float,
    screen_height: float,
    skeleton_notation: str | None = None,
    skeleton_type: str | None = None,
) -> str:
    """Render the full classification prompt.

    Compose: role framing + screen context + catalog with
    descriptions + classification rules + per-node block. The LLM
    is instructed to emit results via the ``classify_nodes`` tool —
    free-text responses are rejected at the tool-use layer.
    """
    skel_line = (
        f"Screen skeleton: `{skeleton_notation}` "
        f"({skeleton_type or 'untyped'})"
        if skeleton_notation else
        "Screen skeleton: (not yet extracted)"
    )
    catalog_block = _format_catalog_for_prompt(catalog)
    node_descriptions = "\n".join(_describe_node(n) for n in nodes)

    return f"""You are classifying UI nodes from a Figma design file against a fixed catalog of canonical component types. This classification feeds a design-system compiler — accuracy matters, and "unsure" is a valid answer.

## Screen context

Screen: **{screen_name}** ({int(screen_width)}×{int(screen_height)})
{skel_line}

## Canonical types (pick exactly one per node)

Use the behavioral description to disambiguate. The UI component that matches the *function* of the node wins, not the one that merely looks similar.
{catalog_block}

## Rules

1. **Pick one canonical type per node.** `container` and `unsure` are valid but prefer a specific type when evidence supports it.

2. **Confidence is calibrated.**
   - **0.95+** — unambiguous. "Button labeled 'Sign in' with button-shaped layout."
   - **0.85–0.94** — strong signal + minor alternative. "Probably a card; could be a list_item tile."
   - **0.75–0.84** — real evidence + plausible alternative. Use the specific type at this band.
   - **Below 0.75** — **prefer `unsure`** with a reason rather than a low-confidence specific type. Hedging with "container at 0.70" loses more information than an honest `unsure`.

3. **Don't regress to `container` when a specific type has evidence.** `container` is for *truly generic layout frames with no identity signals* — no sample_text, no distinctive children, no known pattern. If the node has ANY specific signal (distinctive name like `grabber` / `address` / `wordmark`, characteristic children like 3 ellipses = dots/grabber, sample text, known layout pattern), classify it specifically. A `button_group` is more useful downstream than a `container` with 3 button children.

4. **Use parent/sibling context.** A node inside a `bottom_nav` is likely a `navigation_row`, not a button. A text-only node inside a `card` at the top is likely `heading`. A row of identical button-like instances is `button_group`, not `container`.

5. **Sample text is a strong signal.** "Sign in" → button. "Welcome back" → heading. "Forgot password?" → link. URL-like text (`chads.wtf`) → search_input or text depending on context.

6. **Empty-frame grid pattern.** Multiple identical frames (same size, same parent, no children, no sample_text) arranged in a grid → `skeleton` (loading placeholder). Rare to be `image` unless the frame carries an actual image fill.

7. **Decorative-child pattern.** A small frame with N identical decorative children (3 ellipses, 2 chevrons, 4 dots) in a tight layout is typically a single semantic icon/glyph (`icon`), not a `container` of N independent things.

8. **Reasons are evidence-based, not speculation.** One sentence, citing the signals (layout, text, parent, size, child pattern). "Assumed to be a card" is bad; "Vertical auto-layout with image at top, heading, and action row" is good. "Structural grouping of controls" is a weak reason — if the children are all buttons, say `button_group` and cite why.

## Nodes to classify

{node_descriptions}

Return your classifications via the `classify_nodes` tool. Every node in the batch must appear in the response exactly once."""


def _extract_classifications_from_response(response: Any) -> list[dict[str, Any]]:
    """Extract the ``classifications`` array from a Claude tool-use
    response. Returns an empty list when the expected tool_use
    block is missing — caller logs + skips the batch, never
    invents data to paper over a malformed reply.
    """
    if response is None or not getattr(response, "content", None):
        return []
    for block in response.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != CLASSIFY_TOOL_SCHEMA["name"]:
            continue
        inp = getattr(block, "input", None)
        if isinstance(inp, dict):
            classifications = inp.get("classifications")
            if isinstance(classifications, list):
                return [c for c in classifications if isinstance(c, dict)]
        return []
    return []


def _get_unclassified_for_llm(
    conn: sqlite3.Connection, screen_id: int,
) -> list[dict[str, Any]]:
    """Fetch unclassified FRAME/INSTANCE/COMPONENT nodes at depth
    ≥1 on the given screen, enriched with the context the LLM
    prompt needs: parent classification (if any), sibling/child
    distribution, sample text, and the CKR-registered master name
    when the node has a ``component_key``.
    """
    screen = conn.execute(
        "SELECT name, width, height FROM screens WHERE id = ?",
        (screen_id,),
    ).fetchone()
    if screen is None:
        return []

    # Full-screen filter (classifier v2): nodes at >=95% of the
    # screen's viewport in BOTH dimensions are canvas/root
    # containers, not classifiable UI components. They waste API
    # calls and confuse the model. Size threshold is expressed in
    # the SQL so the DB skips them before we materialise rows.
    screen_w, screen_h = screen[1] or 0, screen[2] or 0
    cursor = conn.execute(
        """
        SELECT n.id AS node_id, n.name, n.node_type, n.depth,
               n.width, n.height, n.y, n.layout_mode,
               n.parent_id, n.component_key
        FROM nodes n
        LEFT JOIN screen_component_instances sci
          ON sci.node_id = n.id AND sci.screen_id = n.screen_id
        WHERE n.screen_id = ?
          AND n.node_type IN ('FRAME', 'INSTANCE', 'COMPONENT')
          AND n.depth >= 1
          AND sci.id IS NULL
          AND NOT (
            COALESCE(n.width, 0) >= ? * 0.95
            AND COALESCE(n.height, 0) >= ? * 0.95
          )
        ORDER BY n.depth, n.sort_order
        """,
        (screen_id, screen_w, screen_h),
    )
    columns = [desc[0] for desc in cursor.description]
    raw = [dict(zip(columns, row)) for row in cursor.fetchall()]

    # Filter system chrome (iOS status bar, Safari chrome, keyboard
    # keys, etc. — handled as design content but classified to
    # `container` / skipped at the renderer layer, not here).
    candidates = [r for r in raw if not is_system_chrome(r["name"])]

    # Enrich each candidate with parent classification + child
    # distribution + sample text + CKR-registered name.
    for r in candidates:
        pid = r.get("parent_id")
        if pid is not None:
            pr = conn.execute(
                "SELECT n.name, n.node_type, sci.canonical_type "
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
            "SELECT node_type, COUNT(*) FROM nodes "
            "WHERE parent_id = ? GROUP BY node_type",
            (r["node_id"],),
        ).fetchall()
        r["child_type_dist"] = {k: v for k, v in children}
        r["total_children"] = sum(v for _, v in children)

        text_child = conn.execute(
            "SELECT text_content FROM nodes "
            "WHERE parent_id = ? AND node_type = 'TEXT' "
            "AND text_content IS NOT NULL AND text_content != '' "
            "ORDER BY sort_order LIMIT 1",
            (r["node_id"],),
        ).fetchone()
        r["sample_text"] = text_child[0] if text_child else None

        ck = r.get("component_key")
        if ck:
            ckr_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='component_key_registry'"
            ).fetchone()
            if ckr_exists:
                ckr = conn.execute(
                    "SELECT name FROM component_key_registry "
                    "WHERE component_key = ?",
                    (ck,),
                ).fetchone()
                r["ckr_registered_name"] = ckr[0] if ckr else None
            else:
                r["ckr_registered_name"] = None
        else:
            r["ckr_registered_name"] = None

    return candidates


def classify_llm(
    conn: sqlite3.Connection,
    screen_id: int,
    client: Any,
) -> dict[str, Any]:
    """Classify unclassified nodes on one screen using Claude
    Haiku with tool-use structured output.

    Batches all unclassified candidates on the screen into one
    call. Inserts results with ``classification_source='llm'``.
    Missing tool_use blocks in the response → zero classifications
    for the batch (logged by caller).
    """
    candidates = _get_unclassified_for_llm(conn, screen_id)
    if not candidates:
        return {"classified": 0}

    catalog = get_catalog(conn)
    screen = conn.execute(
        "SELECT name, width, height FROM screens WHERE id = ?",
        (screen_id,),
    ).fetchone()
    skeleton = conn.execute(
        "SELECT skeleton_notation, skeleton_type FROM screen_skeletons "
        "WHERE screen_id = ? LIMIT 1",
        (screen_id,),
    ).fetchone()
    skel_notation = skeleton[0] if skeleton else None
    skel_type = skeleton[1] if skeleton else None

    prompt = build_classification_prompt(
        nodes=candidates,
        catalog=catalog,
        screen_name=screen[0],
        screen_width=screen[1] or 0,
        screen_height=screen[2] or 0,
        skeleton_notation=skel_notation,
        skeleton_type=skel_type,
    )

    response = client.messages.create(
        model=_LLM_MODEL,
        max_tokens=4096,
        tools=[CLASSIFY_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": CLASSIFY_TOOL_SCHEMA["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    results = _extract_classifications_from_response(response)

    node_id_set = {n["node_id"] for n in candidates}
    catalog_id_lookup = {e["canonical_name"]: e["id"] for e in catalog}

    inserts: list[tuple[Any, ...]] = []
    for r in results:
        nid = r.get("node_id")
        ctype = r.get("canonical_type")
        confidence = r.get("confidence", _DEFAULT_LLM_CONFIDENCE)
        reason = r.get("reason")
        if nid not in node_id_set:
            continue
        if not isinstance(ctype, str):
            continue
        if ctype == "container":
            catalog_id = None
        elif ctype == "unsure":
            # `unsure` classifications are recorded but with low
            # confidence + `unsure` as the canonical_type — lets
            # downstream vision / human passes pick them up.
            catalog_id = None
        else:
            catalog_id = catalog_id_lookup.get(ctype)
            if catalog_id is None:
                # Model invented a type not in the catalog —
                # skip rather than corrupt the data.
                continue
        inserts.append((
            screen_id, nid, catalog_id, ctype,
            float(confidence), "llm",
            reason if isinstance(reason, str) else None,
            # Preserve the LLM's primary verdict in llm_type +
            # llm_confidence (migration 015). Consensus rewrites
            # canonical_type; rule-v2 iteration reads llm_type.
            ctype, float(confidence),
        ))

    if inserts:
        conn.executemany(
            "INSERT OR IGNORE INTO screen_component_instances "
            "(screen_id, node_id, catalog_type_id, canonical_type, "
            " confidence, classification_source, llm_reason, "
            " llm_type, llm_confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            inserts,
        )
        conn.commit()

    return {"classified": len(inserts)}


# Back-compat shims: callers importing the old helpers continue to
# work until M7.0.a lands and old test fixtures are retired.
def parse_classification_response(response_text: str) -> list[dict[str, Any]]:
    """Legacy text-parse entrypoint, preserved for test compatibility.

    Accepts JSON arrays wrapped in optional code fences. Prefer the
    tool-use path (``_extract_classifications_from_response``) for
    new callers.
    """
    import re as _re
    text = response_text.strip()
    m = _re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, _re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        if "type" not in entry or "node_id" not in entry:
            continue
        out.append({
            "node_id": entry["node_id"],
            "type": entry["type"],
            "confidence": entry.get("confidence", _DEFAULT_LLM_CONFIDENCE),
        })
    return out
