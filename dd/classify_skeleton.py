"""Screen skeleton extraction (T5 Phase 1a).

Generates compact skeleton notation from classified component instances.
Notation format: stack(header, scroll(content), bottom_nav)
"""

import sqlite3
from typing import Any, Dict, List, Optional


def extract_skeleton(conn: sqlite3.Connection, screen_id: int) -> Optional[Dict[str, Any]]:
    """Generate skeleton notation for a screen from its classified instances.

    Groups depth-1 classified components into header/content/footer zones
    by y-position. Persists to screen_skeletons table (upserts).
    Returns dict with notation, or None if screen doesn't exist.
    """
    screen = _get_screen(conn, screen_id)
    if screen is None:
        return None

    screen_height = screen["height"]
    zones = _build_zones(conn, screen_id, screen_height)
    notation = _zones_to_notation(zones)
    skeleton_type = _infer_skeleton_type(zones)

    conn.execute(
        "INSERT INTO screen_skeletons (screen_id, skeleton_notation, skeleton_type) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(screen_id) DO UPDATE SET "
        "skeleton_notation = excluded.skeleton_notation, "
        "skeleton_type = excluded.skeleton_type",
        (screen_id, notation, skeleton_type),
    )
    conn.commit()

    return {"notation": notation, "skeleton_type": skeleton_type}


def _get_screen(conn: sqlite3.Connection, screen_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.execute(
        "SELECT id, width, height FROM screens WHERE id = ?", (screen_id,)
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {"id": row[0], "width": row[1], "height": row[2]}


def _build_zones(
    conn: sqlite3.Connection, screen_id: int, screen_height: float
) -> Dict[str, List[str]]:
    """Partition depth-1 nodes into header/content/footer zones by y-position."""
    cursor = conn.execute(
        "SELECT n.y, n.height, COALESCE(sci.canonical_type, 'content') as ctype "
        "FROM nodes n "
        "LEFT JOIN screen_component_instances sci "
        "  ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
        "WHERE n.screen_id = ? AND n.depth = 1 "
        "ORDER BY n.y ASC",
        (screen_id,),
    )
    rows = cursor.fetchall()

    zones: Dict[str, List[str]] = {"header": [], "content": [], "footer": []}

    for y, height, ctype in rows:
        y = y or 0
        height = height or 0
        bottom = y + height

        if ctype in ("header", "bottom_nav"):
            if ctype == "header":
                zones["header"].append(ctype)
            else:
                zones["footer"].append(ctype)
        elif bottom <= screen_height * 0.15:
            zones["header"].append(ctype)
        elif y >= screen_height * 0.85:
            zones["footer"].append(ctype)
        else:
            zones["content"].append(ctype)

    return zones


def _zones_to_notation(zones: Dict[str, List[str]]) -> str:
    """Convert zones dict to compact skeleton notation."""
    parts: List[str] = []

    for ctype in zones["header"]:
        parts.append(ctype)

    content_items = zones["content"]
    if content_items:
        if len(content_items) == 1:
            parts.append(f"scroll({content_items[0]})")
        else:
            inner = ", ".join(content_items)
            parts.append(f"scroll({inner})")
    else:
        parts.append("scroll(content)")

    for ctype in zones["footer"]:
        parts.append(ctype)

    return f"stack({', '.join(parts)})"


def _infer_skeleton_type(zones: Dict[str, List[str]]) -> Optional[str]:
    """Infer a screen archetype from the zone composition."""
    has_header = len(zones["header"]) > 0
    has_footer = len(zones["footer"]) > 0
    content_types = set(zones["content"])

    if has_header and has_footer:
        return "standard"
    if has_header and not has_footer:
        return "headerless_nav"
    if not has_header and not has_footer:
        return "fullscreen"
    return "standard"
