"""Structural heuristic classification (T5 Phase 1a, Step 2).

Classifies unclassified nodes using position, layout, and text rules.
Only processes nodes NOT already classified by formal matching.
"""

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from dd.catalog import get_catalog


def classify_heuristics(conn: sqlite3.Connection, screen_id: int) -> Dict[str, Any]:
    """Step 2: Classify remaining nodes using structural heuristics.

    Runs position-based, text-based, and layout-based rules on nodes
    that weren't classified by formal matching. Returns dict with count.
    """
    screen = _get_screen_dimensions(conn, screen_id)
    if screen is None:
        return {"classified": 0}

    screen_width, screen_height = screen

    unclassified = _get_unclassified_nodes(conn, screen_id)
    if not unclassified:
        return {"classified": 0}

    catalog_ids = _build_catalog_id_lookup(conn)
    inserts: List[Tuple] = []

    for node in unclassified:
        result = _apply_rules(node, screen_width, screen_height, conn)
        if result is not None:
            canonical_type, confidence = result
            inserts.append((
                screen_id,
                node["id"],
                catalog_ids.get(canonical_type),
                canonical_type,
                confidence,
                "heuristic",
            ))

    if inserts:
        conn.executemany(
            "INSERT OR IGNORE INTO screen_component_instances "
            "(screen_id, node_id, catalog_type_id, canonical_type, confidence, classification_source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            inserts,
        )
        conn.commit()

    return {"classified": len(inserts)}


def _get_screen_dimensions(conn: sqlite3.Connection, screen_id: int) -> Optional[Tuple[float, float]]:
    cursor = conn.execute(
        "SELECT width, height FROM screens WHERE id = ?", (screen_id,)
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return (row[0], row[1])


def _get_unclassified_nodes(conn: sqlite3.Connection, screen_id: int) -> List[Dict[str, Any]]:
    cursor = conn.execute(
        "SELECT n.id, n.name, n.node_type, n.depth, n.x, n.y, n.width, n.height, "
        "n.layout_mode, n.font_family, n.font_weight, n.font_size, n.text_content, "
        "n.parent_id "
        "FROM nodes n "
        "LEFT JOIN screen_component_instances sci "
        "  ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
        "WHERE n.screen_id = ? AND sci.id IS NULL",
        (screen_id,),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _build_catalog_id_lookup(conn: sqlite3.Connection) -> Dict[str, Optional[int]]:
    catalog = get_catalog(conn)
    return {entry["canonical_name"]: entry["id"] for entry in catalog}


def _apply_rules(
    node: Dict[str, Any],
    screen_width: float,
    screen_height: float,
    conn: sqlite3.Connection,
) -> Optional[Tuple[str, float]]:
    """Apply heuristic rules in priority order. Returns (type, confidence) or None."""
    result = _rule_header(node, screen_width)
    if result:
        return result

    result = _rule_bottom_nav(node, screen_width, screen_height)
    if result:
        return result

    result = _rule_heading_text(node)
    if result:
        return result

    result = _rule_body_text(node)
    if result:
        return result

    return None


# ---------------------------------------------------------------------------
# Individual heuristic rules
# ---------------------------------------------------------------------------

def _rule_header(node: Dict[str, Any], screen_width: float) -> Optional[Tuple[str, float]]:
    """Full-width frame at top of screen with horizontal layout → header."""
    if node["node_type"] != "FRAME":
        return None
    if node["depth"] != 1:
        return None

    y = node.get("y") or 0
    width = node.get("width") or 0
    height = node.get("height") or 0

    is_top = y <= 60
    is_full_width = width >= screen_width * 0.9
    is_short = 30 <= height <= 80

    if is_top and is_full_width and is_short:
        return ("header", 0.85)

    return None


def _rule_bottom_nav(
    node: Dict[str, Any], screen_width: float, screen_height: float
) -> Optional[Tuple[str, float]]:
    """Full-width frame at bottom of screen → bottom_nav."""
    if node["node_type"] != "FRAME":
        return None
    if node["depth"] != 1:
        return None

    y = node.get("y") or 0
    width = node.get("width") or 0
    height = node.get("height") or 0

    is_bottom = (y + height) >= screen_height * 0.9
    is_full_width = width >= screen_width * 0.9
    is_short = 40 <= height <= 100

    if is_bottom and is_full_width and is_short:
        return ("bottom_nav", 0.8)

    return None


def _rule_heading_text(node: Dict[str, Any]) -> Optional[Tuple[str, float]]:
    """TEXT node with large font size and heavy weight → heading."""
    if node["node_type"] != "TEXT":
        return None

    font_size = node.get("font_size")
    font_weight = node.get("font_weight")

    if font_size is None:
        return None

    if font_size >= 18 and (font_weight is not None and font_weight >= 600):
        return ("heading", 0.9)

    return None


def _rule_body_text(node: Dict[str, Any]) -> Optional[Tuple[str, float]]:
    """TEXT node with standard font size → text."""
    if node["node_type"] != "TEXT":
        return None

    font_size = node.get("font_size")
    if font_size is None:
        return None

    if 8 <= font_size < 18:
        return ("text", 0.85)

    return None
