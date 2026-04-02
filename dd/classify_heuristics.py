"""Structural heuristic classification (T5 Phase 1a, Step 2).

Classifies unclassified nodes using position, layout, and text rules.
Only processes nodes NOT already classified by formal matching.

All rules are defined in dd/classify_rules.py.
"""

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from dd.catalog import get_catalog
from dd.classify_rules import apply_heuristic_rules


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
        result = apply_heuristic_rules(node, screen_width, screen_height)
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
        "n.parent_id, n.fills, n.strokes, n.effects "
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
