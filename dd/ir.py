"""CompositionSpec IR generation (T5 Phase 2).

Transforms classified screen data + token bindings into a platform-agnostic
intermediate representation (flat element map with token references).
"""

import sqlite3
from typing import Any, Dict, List, Optional


# Property mapping: Figma binding property → IR style key
_BINDING_PROPERTY_MAP = {
    "fill.0.color": "backgroundColor",
    "fill.1.color": "backgroundColor2",
    "stroke.0.color": "borderColor",
    "fontSize": "fontSize",
    "fontFamily": "fontFamily",
    "fontWeight": "fontWeight",
    "lineHeight": "lineHeight",
    "letterSpacing": "letterSpacing",
    "cornerRadius": "borderRadius",
    "padding.top": "paddingTop",
    "padding.right": "paddingRight",
    "padding.bottom": "paddingBottom",
    "padding.left": "paddingLeft",
    "itemSpacing": "gap",
    "opacity": "opacity",
}

# Types where text_content maps to props.text
_TEXT_PROP_TYPES = frozenset({"text", "heading", "link", "badge"})

# Layout direction mapping
_DIRECTION_MAP = {
    "HORIZONTAL": "horizontal",
    "VERTICAL": "vertical",
}

# Sizing mapping
_SIZING_MAP = {
    "FILL": "fill",
    "HUG": "hug",
    "FIXED": "fixed",
}


def _build_binding_index(bindings: List[Dict[str, Any]]) -> Dict[str, str]:
    """Build property → token ref string from bindings list.

    Returns dict mapping Figma property names to "{token.name}" strings
    for bindings that have a token_name set.
    """
    index: Dict[str, str] = {}
    for b in bindings:
        if b.get("token_name"):
            index[b["property"]] = f"{{{b['token_name']}}}"
    return index


# Properties that belong in layout, not style
_LAYOUT_BINDING_PROPERTIES = frozenset({
    "padding.top", "padding.right", "padding.bottom", "padding.left",
    "itemSpacing", "counterAxisSpacing",
})


def map_node_to_element(node: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a classified node dict to an IR element.

    Expects node dict with keys: canonical_type, layout_mode, padding_*,
    item_spacing, layout_sizing_h/v, text_content, corner_radius, opacity,
    and bindings (list of {property, token_name, resolved_value}).
    """
    binding_index = _build_binding_index(node.get("bindings", []))

    element: Dict[str, Any] = {
        "type": node["canonical_type"],
    }

    layout = _build_layout(node, binding_index)
    if layout:
        element["layout"] = layout

    style = _build_style(node, binding_index)
    if style:
        element["style"] = style

    props = _build_props(node)
    if props:
        element["props"] = props

    return element


def _build_layout(node: Dict[str, Any], binding_index: Dict[str, str]) -> Dict[str, Any]:
    layout: Dict[str, Any] = {}

    direction = _DIRECTION_MAP.get(node.get("layout_mode") or "", "stacked")
    layout["direction"] = direction

    gap_token = binding_index.get("itemSpacing")
    gap = node.get("item_spacing")
    if gap_token:
        layout["gap"] = gap_token
    elif gap and gap > 0:
        layout["gap"] = gap

    padding = _build_padding(node, binding_index)
    if padding:
        layout["padding"] = padding

    sizing = _build_sizing(node)
    if sizing:
        layout["sizing"] = sizing

    align = node.get("primary_align")
    if align:
        layout["mainAxisAlignment"] = align.lower()

    cross = node.get("counter_align")
    if cross:
        layout["crossAxisAlignment"] = cross.lower()

    return layout


def _build_padding(node: Dict[str, Any], binding_index: Dict[str, str]) -> Optional[Dict[str, Any]]:
    padding: Dict[str, Any] = {}
    for side in ("top", "right", "bottom", "left"):
        token = binding_index.get(f"padding.{side}")
        val = node.get(f"padding_{side}")
        if token:
            padding[side] = token
        elif val and val > 0:
            padding[side] = val

    return padding if padding else None


def _build_sizing(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sizing: Dict[str, Any] = {}
    h = node.get("layout_sizing_h")
    v = node.get("layout_sizing_v")

    if h:
        sizing["width"] = _SIZING_MAP.get(h, h.lower())
    if v:
        sizing["height"] = _SIZING_MAP.get(v, v.lower())

    return sizing if sizing else None


def _build_style(node: Dict[str, Any], binding_index: Dict[str, str]) -> Dict[str, Any]:
    style: Dict[str, Any] = {}

    for binding in node.get("bindings", []):
        prop = binding["property"]
        token_name = binding.get("token_name")
        resolved = binding.get("resolved_value")

        # Layout properties (padding, gap) are handled in _build_layout
        if prop in _LAYOUT_BINDING_PROPERTIES:
            continue

        ir_key = _BINDING_PROPERTY_MAP.get(prop)
        if ir_key is None:
            continue

        if token_name:
            style[ir_key] = f"{{{token_name}}}"
        elif resolved:
            style[ir_key] = resolved

    radius = node.get("corner_radius")
    if radius and "borderRadius" not in style:
        try:
            style["borderRadius"] = int(float(radius))
        except (ValueError, TypeError):
            pass

    opacity = node.get("opacity")
    if opacity is not None and opacity < 1.0:
        style["opacity"] = opacity

    return style


def _build_props(node: Dict[str, Any]) -> Dict[str, Any]:
    props: Dict[str, Any] = {}

    canonical_type = node.get("canonical_type", "")
    text = node.get("text_content")

    if text and canonical_type in _TEXT_PROP_TYPES:
        props["text"] = text

    return props


# ---------------------------------------------------------------------------
# Query layer
# ---------------------------------------------------------------------------

def query_screen_for_ir(conn: sqlite3.Connection, screen_id: int) -> Dict[str, Any]:
    """Fetch all classified nodes, bindings, and tokens for a screen.

    Returns dict with screen metadata and a list of node dicts,
    each containing its bindings grouped in-memory.
    """
    screen_row = conn.execute(
        "SELECT name, width, height FROM screens WHERE id = ?",
        (screen_id,),
    ).fetchone()
    if screen_row is None:
        return {"screen_name": "", "width": 0, "height": 0, "nodes": []}

    cursor = conn.execute(
        "SELECT n.id as node_id, n.name, n.node_type, n.depth, n.sort_order, "
        "n.x, n.y, n.width, n.height, "
        "n.layout_mode, n.padding_top, n.padding_right, n.padding_bottom, n.padding_left, "
        "n.item_spacing, n.counter_axis_spacing, "
        "n.layout_sizing_h, n.layout_sizing_v, n.primary_align, n.counter_align, "
        "n.text_content, n.corner_radius, n.opacity, n.fills, "
        "n.font_family, n.font_weight, n.font_size, "
        "n.parent_id, "
        "sci.canonical_type, sci.id as sci_id, sci.parent_instance_id "
        "FROM nodes n "
        "JOIN screen_component_instances sci ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
        "WHERE n.screen_id = ? "
        "ORDER BY n.depth, n.sort_order",
        (screen_id,),
    )
    columns = [desc[0] for desc in cursor.description]
    raw_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    bindings_cursor = conn.execute(
        "SELECT ntb.node_id, ntb.property, t.name as token_name, ntb.resolved_value "
        "FROM node_token_bindings ntb "
        "JOIN nodes n ON ntb.node_id = n.id "
        "LEFT JOIN tokens t ON ntb.token_id = t.id "
        "WHERE n.screen_id = ? AND ntb.binding_status = 'bound'",
        (screen_id,),
    )
    bindings_by_node: Dict[int, List[Dict[str, Any]]] = {}
    for row in bindings_cursor.fetchall():
        node_id = row[0]
        if node_id not in bindings_by_node:
            bindings_by_node[node_id] = []
        bindings_by_node[node_id].append({
            "property": row[1],
            "token_name": row[2],
            "resolved_value": row[3],
        })

    for node_dict in raw_rows:
        node_dict["bindings"] = bindings_by_node.get(node_dict["node_id"], [])

    # Find unclassified parent FRAMEs that should become containers
    classified_node_ids = {n["node_id"] for n in raw_rows}
    parent_node_ids = set()
    for n in raw_rows:
        cursor = conn.execute("SELECT parent_id FROM nodes WHERE id = ?", (n["node_id"],))
        row = cursor.fetchone()
        if row and row[0] and row[0] not in classified_node_ids:
            parent_node_ids.add(row[0])

    container_nodes = []
    if parent_node_ids:
        placeholders = ",".join("?" for _ in parent_node_ids)
        cursor = conn.execute(
            f"SELECT id as node_id, name, 'FRAME' as node_type, depth, sort_order, "
            f"x, y, width, height, layout_mode, "
            f"padding_top, padding_right, padding_bottom, padding_left, "
            f"item_spacing, counter_axis_spacing, "
            f"layout_sizing_h, layout_sizing_v, primary_align, counter_align, "
            f"NULL as text_content, corner_radius, opacity, fills, "
            f"NULL as font_family, NULL as font_weight, NULL as font_size, "
            f"'container' as canonical_type, NULL as sci_id, NULL as parent_instance_id, "
            f"parent_id "
            f"FROM nodes WHERE id IN ({placeholders}) AND node_type = 'FRAME'",
            list(parent_node_ids),
        )
        columns = [desc[0] for desc in cursor.description]
        for row in cursor.fetchall():
            d = dict(zip(columns, row))
            d["bindings"] = bindings_by_node.get(d["node_id"], [])
            d["_is_container"] = True
            container_nodes.append(d)

    all_nodes = container_nodes + raw_rows

    tokens_cursor = conn.execute(
        "SELECT DISTINCT t.name, tv.resolved_value "
        "FROM node_token_bindings ntb "
        "JOIN nodes n ON ntb.node_id = n.id "
        "JOIN tokens t ON ntb.token_id = t.id "
        "JOIN token_values tv ON tv.token_id = t.id "
        "JOIN token_modes tm ON tv.mode_id = tm.id AND tm.is_default = 1 "
        "WHERE n.screen_id = ? AND ntb.binding_status = 'bound'",
        (screen_id,),
    )
    tokens = {row[0]: row[1] for row in tokens_cursor.fetchall()}

    return {
        "screen_name": screen_row[0],
        "width": screen_row[1],
        "height": screen_row[2],
        "nodes": all_nodes,
        "tokens": tokens,
    }


# ---------------------------------------------------------------------------
# Composition assembly
# ---------------------------------------------------------------------------

def build_composition_spec(data: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble a CompositionSpec from query results.

    Builds the flat element map, assigns IDs, wires parent→children
    relationships, and collects referenced tokens.
    """
    nodes = data.get("nodes", [])
    if not nodes:
        return {"version": "1.0", "root": "", "elements": {}, "tokens": {}}

    type_counters: Dict[str, int] = {}
    node_id_to_element_id: Dict[int, str] = {}
    sci_id_to_element_id: Dict[int, str] = {}
    elements: Dict[str, Dict[str, Any]] = {}

    for node in nodes:
        canonical = node["canonical_type"]
        type_counters[canonical] = type_counters.get(canonical, 0) + 1
        element_id = f"{canonical}-{type_counters[canonical]}"

        node_id_to_element_id[node["node_id"]] = element_id
        if node.get("sci_id") is not None:
            sci_id_to_element_id[node["sci_id"]] = element_id

        element = map_node_to_element(node)
        elements[element_id] = element

    # Wire children: use parent_instance_id (classified→classified) or
    # parent_id (classified→container) to build the tree
    children_map: Dict[str, List[str]] = {}
    has_parent = set()

    for node in nodes:
        if node.get("_is_container"):
            continue

        element_id = node_id_to_element_id[node["node_id"]]
        parent_sci_id = node.get("parent_instance_id")
        parent_node_id = node.get("parent_id")

        parent_element_id = None
        if parent_sci_id is not None and parent_sci_id in sci_id_to_element_id:
            parent_element_id = sci_id_to_element_id[parent_sci_id]
        elif parent_node_id is not None and parent_node_id in node_id_to_element_id:
            parent_element_id = node_id_to_element_id[parent_node_id]

        if parent_element_id is not None:
            if parent_element_id not in children_map:
                children_map[parent_element_id] = []
            children_map[parent_element_id].append(element_id)
            has_parent.add(element_id)

    for parent_eid, child_ids in children_map.items():
        elements[parent_eid]["children"] = child_ids

    # Root elements: containers + classified nodes that have no parent
    root_ids = [
        node_id_to_element_id[n["node_id"]]
        for n in nodes
        if node_id_to_element_id[n["node_id"]] not in has_parent
    ]

    root_id = "screen-1"
    elements[root_id] = {
        "type": "screen",
        "layout": {
            "direction": "vertical",
            "sizing": {"width": data.get("width", 0), "height": data.get("height", 0)},
        },
        "children": root_ids,
    }

    return {
        "version": "1.0",
        "root": root_id,
        "elements": elements,
        "tokens": data.get("tokens", {}),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_ir(conn: sqlite3.Connection, screen_id: int) -> Dict[str, Any]:
    """Generate CompositionSpec IR for a single screen.

    Returns dict with 'spec' (the CompositionSpec dict) and 'json' (serialized).
    """
    import json
    data = query_screen_for_ir(conn, screen_id)
    spec = build_composition_spec(data)
    return {
        "spec": spec,
        "json": json.dumps(spec, indent=2),
        "element_count": len(spec.get("elements", {})),
        "token_count": len(spec.get("tokens", {})),
    }
