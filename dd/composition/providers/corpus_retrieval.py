"""Corpus retrieval provider (v0.2) — priority 150, backend ``corpus:retrieval``.

Retrieves real IR subtrees from the round-trip-clean DB corpus
(``screen_component_instances`` populated by ``dd.classify``). Each
resolve() call returns a :class:`PresentationTemplate` whose
``corpus_subtree`` field carries the full subtree — root element +
children + visual dict + layout. Compose splices the subtree into the
emitted IR instead of synthesising from hand-authored templates.

Rationale: 204 screens × ~100 nodes = ~20K round-trip-validated IR
fragments. Hand-authored catalog templates (``UniversalCatalogProvider``)
are intrinsically sparser than real extracted IR — their render-fidelity
ceiling in the 00g experiment tops out at ~0.75. Retrieval bypasses that
ceiling by reusing the ground truth.

Gated behind ``DD_ENABLE_CORPUS_RETRIEVAL=1``: default OFF until PoC
validation on 00g/00i confirms the ceiling lift is real.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Any, ClassVar

from dd.composition.protocol import PresentationTemplate


# Per-type ceiling on retrieved-subtree descendant count. Leaf types
# (text, icon, image, heading, link) must stay shallow — a "text"
# slot filled with a 50-node decorative illustration is a
# structural-intent violation. Containers (card, header, list) allow
# more but still cap well below full-screen size to protect against
# carousel-scale subtrees being spliced for a single-slot request.
_MAX_DESCENDANTS_BY_TYPE: dict[str, int] = {
    # Leaves — near-zero descendants expected
    "text": 2,
    "heading": 2,
    "icon": 2,
    "image": 3,
    "link": 3,
    "badge": 3,
    "divider": 0,
    # Atoms with small fixed internal structure
    "button": 4,
    "icon_button": 4,
    "avatar": 3,
    # Containers — meaningful internal structure
    "card": 15,
    "list_item": 10,
    "text_input": 5,
    "search_input": 5,
    "select": 6,
    "tabs": 10,
    "header": 15,
    "navigation_row": 15,
    "drawer": 20,
    "bottom_nav": 15,
    "button_group": 10,
    "pagination": 10,
    "list": 40,
}
_DEFAULT_MAX_DESCENDANTS = 15


@dataclass(frozen=True)
class CorpusRetrievalProvider:
    """Provider that retrieves real IR subtrees from SCI.

    ``conn`` is a sqlite3 connection to the extracted-corpus DB (must
    have ``screen_component_instances`` populated via ``dd classify``).
    The provider is read-only — it never mutates the DB.
    """

    backend: ClassVar[str] = "corpus:retrieval"
    priority: ClassVar[int] = 150

    conn: sqlite3.Connection

    def supports(self, catalog_type: str, variant: str | None) -> bool:
        """True iff corpus retrieval is enabled AND SCI has >= 1 row for
        this canonical_type.

        Variant is ignored in v0.2 PoC — variant-aware retrieval (ranking
        by variant axis match) is a follow-on once the base hypothesis
        is validated.
        """
        if os.environ.get("DD_ENABLE_CORPUS_RETRIEVAL") != "1":
            return False
        cur = self.conn.execute(
            "SELECT 1 FROM screen_component_instances "
            "WHERE canonical_type = ? LIMIT 1",
            (catalog_type,),
        )
        return cur.fetchone() is not None

    def resolve(
        self,
        catalog_type: str,
        variant: str | None,
        context: dict[str, Any],
    ) -> PresentationTemplate | None:
        """Pick a representative SCI instance and materialise its subtree.

        PoC selection strategy (v0.2):
        1. Filter to mobile-sized app screens (300–500 px wide).
        2. Bound the subtree size per catalog type — leaf types like
           ``text`` / ``icon`` / ``image`` / ``link`` get pulled when
           the node has ≤ 2 descendants; containers like ``card`` /
           ``header`` allow more but still cap at 20 to avoid
           pulling carousel-scale subtrees into a "card" slot.
        3. Among qualifying candidates, prefer the smallest subtree
           (fewer descendants = less risk of over-splicing), tie-break
           by MIN(node_id) so A/B is deterministic.

        v0.3 replaces this with structural-match ranking against the
        LLM plan's child-type set.
        """
        max_descendants = _MAX_DESCENDANTS_BY_TYPE.get(
            catalog_type, _DEFAULT_MAX_DESCENDANTS,
        )
        # Candidate pool: SCI rows on mobile-sized app screens. We
        # score each candidate by descendant count via a Python-side
        # walk to avoid a correlated CTE-per-row SQL pattern (and to
        # work against test fixtures without the ``nodes.path``
        # materialised column).
        candidates = self.conn.execute(
            """
            SELECT sci.screen_id, sci.node_id
            FROM screen_component_instances sci
            JOIN screens s ON s.id = sci.screen_id
            WHERE sci.canonical_type = ?
              AND s.screen_type = 'app_screen'
              AND s.width BETWEEN 300 AND 500
            ORDER BY sci.node_id ASC
            LIMIT 200
            """,
            (catalog_type,),
        ).fetchall()
        if not candidates:
            return None

        best: tuple[int, int, int] | None = None  # (desc_count, screen_id, node_id)
        for cand in candidates:
            sid = cand[0] if not isinstance(cand, sqlite3.Row) else cand["screen_id"]
            nid = cand[1] if not isinstance(cand, sqlite3.Row) else cand["node_id"]
            desc = _count_descendants(self.conn, screen_id=sid, root_node_id=nid)
            if desc > max_descendants:
                continue
            key = (desc, nid)
            if best is None or key < (best[0], best[2]):
                best = (desc, sid, nid)
                # Smallest possible match (0 descendants) short-circuits
                if desc == 0:
                    break
        if best is None:
            return None
        _, screen_id, node_id = best

        subtree = _extract_subtree(self.conn, screen_id=screen_id, root_node_id=node_id)
        if subtree is None:
            return None

        return PresentationTemplate(
            catalog_type=catalog_type,
            variant=variant,
            provider=self.backend,
            corpus_subtree=subtree,
        )


def _extract_subtree(
    conn: sqlite3.Connection,
    *,
    screen_id: int,
    root_node_id: int,
) -> dict[str, Any] | None:
    """Walk the DB from ``root_node_id`` down, producing an IR-shaped
    subtree dict.

    Shape:
        {
          "source_screen_id": int,
          "source_node_id": int,
          "root": str (element id of the root),
          "elements": {eid: {type, visual, layout, props, children}},
        }
    """
    rows = _fetch_subtree_rows(conn, screen_id=screen_id, root_node_id=root_node_id)
    if not rows:
        return None

    by_node_id = {r["id"]: dict(r) for r in rows}

    type_counters: dict[str, int] = {}
    node_to_eid: dict[int, str] = {}

    elements: dict[str, dict[str, Any]] = {}
    for r in rows:
        etype = _resolve_element_type(r)
        type_counters[etype] = type_counters.get(etype, 0) + 1
        eid = f"{etype}-{type_counters[etype]}"
        node_to_eid[r["id"]] = eid
        elements[eid] = _build_element(r, etype)

    for r in rows:
        eid = node_to_eid[r["id"]]
        parent_id = r.get("parent_id")
        if parent_id is None or parent_id not in node_to_eid:
            continue
        parent_eid = node_to_eid[parent_id]
        elements[parent_eid].setdefault("children", []).append(eid)

    root_eid = node_to_eid[root_node_id]
    return {
        "source_screen_id": screen_id,
        "source_node_id": root_node_id,
        "root": root_eid,
        "elements": elements,
    }


def _count_descendants(
    conn: sqlite3.Connection,
    *,
    screen_id: int,
    root_node_id: int,
) -> int:
    """Return the number of nodes strictly under ``root_node_id``.

    Used as a size-fit score when ranking SCI candidates: smaller =
    safer PoC splice. Works against fixtures that lack the
    materialised ``nodes.path`` column.
    """
    cur = conn.execute(
        """
        WITH RECURSIVE sub(id) AS (
            SELECT id FROM nodes WHERE parent_id = ?
            UNION ALL
            SELECT n.id FROM nodes n
            JOIN sub s ON n.parent_id = s.id
            WHERE n.screen_id = ?
        )
        SELECT COUNT(*) FROM sub
        """,
        (root_node_id, screen_id),
    )
    return int(cur.fetchone()[0])


def _fetch_subtree_rows(
    conn: sqlite3.Connection,
    *,
    screen_id: int,
    root_node_id: int,
) -> list[dict[str, Any]]:
    """Fetch nodes under ``root_node_id`` using a recursive CTE.

    Returns list of dicts keyed by column name. Order: root first,
    then depth-first by (depth, sort_order) — the renderer-compatible
    walk order.
    """
    query = """
        WITH RECURSIVE subtree(id) AS (
            SELECT id FROM nodes WHERE id = ?
            UNION ALL
            SELECT n.id FROM nodes n
            JOIN subtree s ON n.parent_id = s.id
            WHERE n.screen_id = ?
        )
        SELECT n.id, n.parent_id, n.name, n.node_type,
               n.depth, n.sort_order, n.component_key,
               n.width, n.height, n.x, n.y,
               n.layout_mode, n.padding_top, n.padding_right,
               n.padding_bottom, n.padding_left, n.item_spacing,
               n.primary_align, n.counter_align,
               n.layout_sizing_h, n.layout_sizing_v,
               n.fills, n.strokes, n.effects, n.corner_radius,
               n.opacity, n.stroke_weight,
               n.text_content, n.font_family, n.font_weight, n.font_size,
               n.text_align, n.line_height,
               sci.canonical_type
        FROM nodes n
        JOIN subtree s ON s.id = n.id
        LEFT JOIN screen_component_instances sci
               ON sci.node_id = n.id AND sci.screen_id = n.screen_id
        WHERE n.screen_id = ?
        ORDER BY n.depth, n.sort_order
    """
    cur = conn.execute(query, (root_node_id, screen_id, screen_id))
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _resolve_element_type(row: dict[str, Any]) -> str:
    """Prefer canonical_type (SCI); fall back to lowered node_type."""
    ct = row.get("canonical_type")
    if ct:
        return ct
    nt = (row.get("node_type") or "frame").lower()
    if nt == "instance":
        return "instance"
    if nt == "text":
        return "text"
    return "frame"


def _build_element(row: dict[str, Any], etype: str) -> dict[str, Any]:
    """Assemble the element dict: type + visual + layout + props.

    ``visual`` uses DB snake_case keys (fills/strokes/effects/
    corner_radius/stroke_weight/opacity) so ``build_template_visuals``
    can consume it directly as a ``db_visuals`` entry — same shape as
    ``query_screen_visuals`` produces for round-trip. Values are
    pre-parsed lists/numbers, but ``normalize_fills``/``normalize_strokes``
    tolerate both JSON strings and already-parsed lists.
    """
    element: dict[str, Any] = {"type": etype}

    visual: dict[str, Any] = {}
    fills = _parse_json(row.get("fills"))
    if fills:
        visual["fills"] = fills
    strokes = _parse_json(row.get("strokes"))
    if strokes:
        visual["strokes"] = strokes
    effects = _parse_json(row.get("effects"))
    if effects:
        visual["effects"] = effects
    if row.get("corner_radius") is not None:
        visual["corner_radius"] = row["corner_radius"]
    if row.get("stroke_weight") is not None:
        visual["stroke_weight"] = row["stroke_weight"]
    if row.get("opacity") is not None and row["opacity"] != 1.0:
        visual["opacity"] = row["opacity"]
    if visual:
        element["visual"] = visual
        element["_corpus_source_node_id"] = row["id"]

    layout: dict[str, Any] = {}
    if row.get("layout_mode"):
        layout["direction"] = row["layout_mode"].lower()
    padding = _build_padding(row)
    if padding:
        layout["padding"] = padding
    if row.get("item_spacing") is not None:
        layout["gap"] = row["item_spacing"]
    sizing = _build_sizing(row)
    if sizing:
        layout["sizing"] = sizing
    if layout:
        element["layout"] = layout

    props: dict[str, Any] = {}
    if row.get("text_content"):
        props["text"] = row["text_content"]
    if row.get("name"):
        element["_original_name"] = row["name"]
    if props:
        element["props"] = props

    if row.get("component_key"):
        element["component_key"] = row["component_key"]

    return element


def _parse_json(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _parse_corner_radius(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    return parsed


def _build_padding(row: dict[str, Any]) -> dict[str, Any] | None:
    keys = ("padding_top", "padding_right", "padding_bottom", "padding_left")
    values = {k: row.get(k) for k in keys}
    if all(v is None for v in values.values()):
        return None
    return {
        "top": values["padding_top"] or 0,
        "right": values["padding_right"] or 0,
        "bottom": values["padding_bottom"] or 0,
        "left": values["padding_left"] or 0,
    }


def _build_sizing(row: dict[str, Any]) -> dict[str, Any] | None:
    h = row.get("layout_sizing_h")
    v = row.get("layout_sizing_v")
    if h is None and v is None:
        return None
    out = {}
    if h is not None:
        out["width"] = h.lower() if isinstance(h, str) else h
    if v is not None:
        out["height"] = v.lower() if isinstance(v, str) else v
    return out
