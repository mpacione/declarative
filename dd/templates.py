"""Component template extraction from classified instances (Phase 4a).

Extracts the most common structure + visual defaults per catalog type
from the DB. Templates are used by the renderer for Mode 1 (instance
path via componentKey) and Mode 2 (frame construction from structure).
"""

import sqlite3
from collections import Counter
from typing import Any, Dict, List, Optional


_TEMPLATE_FIELDS = [
    "layout_mode", "width", "height",
    "padding_top", "padding_right", "padding_bottom", "padding_left",
    "item_spacing", "primary_align", "counter_align",
    "corner_radius", "fills", "strokes", "effects", "opacity",
]


def _mode_value(values: List[Any]) -> Any:
    """Return the most common value in a list (statistical mode)."""
    if not values:
        return None
    counter = Counter(
        tuple(v) if isinstance(v, list) else v
        for v in values
    )
    return counter.most_common(1)[0][0]


def compute_mode_template(instances: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute the mode (most common value) for each field across instances.

    Returns a template dict with structure + visual fields, instance_count,
    and representative_node_id (first instance matching the mode values).
    """
    if not instances:
        return {}

    template: Dict[str, Any] = {"instance_count": len(instances)}

    for field in _TEMPLATE_FIELDS:
        values = [inst.get(field) for inst in instances if field in inst]
        template[field] = _mode_value(values) if values else None

    node_ids = [inst.get("node_id") for inst in instances if inst.get("node_id")]
    mode_width = template.get("width")
    mode_height = template.get("height")

    representative = node_ids[0] if node_ids else None
    for inst in instances:
        if inst.get("width") == mode_width and inst.get("height") == mode_height:
            representative = inst.get("node_id", representative)
            break

    template["representative_node_id"] = representative
    return template


def extract_templates(conn: sqlite3.Connection, file_id: int) -> int:
    """Extract component templates from classified instances.

    Groups instances by catalog_type and component_key, computes mode
    templates, and inserts into the component_templates table.

    Returns the number of templates created.
    """
    conn.execute("DELETE FROM component_templates")

    cursor = conn.execute(
        "SELECT DISTINCT sci.canonical_type "
        "FROM screen_component_instances sci "
        "JOIN nodes n ON sci.node_id = n.id "
        "JOIN screens s ON n.screen_id = s.id "
        "WHERE s.file_id = ? AND s.screen_type = 'app_screen'",
        (file_id,),
    )
    catalog_types = [row[0] for row in cursor.fetchall()]

    template_count = 0

    for catalog_type in catalog_types:
        instances = _query_instances(conn, file_id, catalog_type)
        if not instances:
            continue

        keyed = [i for i in instances if i.get("component_key")]
        unkeyed = [i for i in instances if not i.get("component_key")]

        if keyed:
            groups: Dict[str, List[Dict]] = {}
            for inst in keyed:
                key = inst["component_key"]
                if key not in groups:
                    groups[key] = []
                groups[key].append(inst)

            for component_key, group in groups.items():
                template = compute_mode_template(group)
                variant = _variant_from_key(group)
                _insert_template(conn, catalog_type, variant, component_key, template)
                template_count += 1

        if unkeyed:
            template = compute_mode_template(unkeyed)
            _insert_template(conn, catalog_type, None, None, template)
            template_count += 1

    conn.commit()
    return template_count


def query_templates(conn: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch all templates keyed by catalog_type.

    Returns dict mapping catalog_type to list of template dicts.
    """
    cursor = conn.execute(
        "SELECT ct.catalog_type, ct.variant, ct.component_key, ct.representative_node_id, "
        "ct.instance_count, ct.layout_mode, ct.width, ct.height, "
        "ct.padding_top, ct.padding_right, ct.padding_bottom, ct.padding_left, "
        "ct.item_spacing, ct.primary_align, ct.counter_align, ct.corner_radius, "
        "ct.fills, ct.strokes, ct.effects, ct.opacity, ct.slots, "
        "c.figma_node_id as component_figma_id "
        "FROM component_templates ct "
        "LEFT JOIN components c ON ct.variant = c.name "
        "ORDER BY ct.catalog_type, ct.variant"
    )
    columns = [desc[0] for desc in cursor.description]
    result: Dict[str, List[Dict[str, Any]]] = {}

    for row in cursor.fetchall():
        entry = dict(zip(columns, row))
        cat_type = entry["catalog_type"]
        if cat_type not in result:
            result[cat_type] = []
        result[cat_type].append(entry)

    return result


def _query_instances(
    conn: sqlite3.Connection, file_id: int, catalog_type: str,
) -> List[Dict[str, Any]]:
    """Fetch all instances of a catalog type with structure + visual props."""
    cursor = conn.execute(
        "SELECT n.id as node_id, n.name, n.component_key, "
        "n.layout_mode, n.width, n.height, "
        "n.padding_top, n.padding_right, n.padding_bottom, n.padding_left, "
        "n.item_spacing, n.primary_align, n.counter_align, "
        "n.corner_radius, n.fills, n.strokes, n.effects, n.opacity "
        "FROM nodes n "
        "JOIN screen_component_instances sci ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
        "JOIN screens s ON n.screen_id = s.id "
        "WHERE s.file_id = ? AND s.screen_type = 'app_screen' "
        "AND sci.canonical_type = ?",
        (file_id, catalog_type),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _variant_from_key(group: List[Dict[str, Any]]) -> str:
    """Derive a variant name from the most common node name in a group."""
    names = [inst.get("name", "") for inst in group]
    if not names:
        return "default"
    counter = Counter(names)
    return counter.most_common(1)[0][0]


def _insert_template(
    conn: sqlite3.Connection,
    catalog_type: str,
    variant: Optional[str],
    component_key: Optional[str],
    template: Dict[str, Any],
) -> None:
    """Insert or replace a template row."""
    conn.execute(
        "INSERT OR REPLACE INTO component_templates "
        "(catalog_type, variant, component_key, representative_node_id, instance_count, "
        "layout_mode, width, height, padding_top, padding_right, padding_bottom, padding_left, "
        "item_spacing, primary_align, counter_align, corner_radius, "
        "fills, strokes, effects, opacity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            catalog_type, variant, component_key,
            template.get("representative_node_id"),
            template.get("instance_count"),
            template.get("layout_mode"),
            template.get("width"), template.get("height"),
            template.get("padding_top"), template.get("padding_right"),
            template.get("padding_bottom"), template.get("padding_left"),
            template.get("item_spacing"),
            template.get("primary_align"), template.get("counter_align"),
            template.get("corner_radius"),
            template.get("fills"), template.get("strokes"),
            template.get("effects"), template.get("opacity"),
        ),
    )
