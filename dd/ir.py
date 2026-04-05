"""CompositionSpec IR generation (T5 Phase 2).

Transforms classified screen data + token bindings into a platform-agnostic
intermediate representation. The IR is a normalized visual intent layer —
every element carries its complete visual description with token refs as
inline annotations where they exist, literal values where they don't.
"""

import json
import sqlite3
from typing import Any

from dd.classify_rules import is_system_chrome
from dd.color import rgba_to_hex

# ---------------------------------------------------------------------------
# Visual property normalization (Figma JSON → IR format)
# ---------------------------------------------------------------------------

_GRADIENT_TYPE_MAP = {
    "GRADIENT_LINEAR": "gradient-linear",
    "GRADIENT_RADIAL": "gradient-radial",
    "GRADIENT_ANGULAR": "gradient-angular",
    "GRADIENT_DIAMOND": "gradient-diamond",
}


def _figma_color_to_hex(color: dict[str, float], paint_opacity: float = 1.0) -> str:
    r, g, b = color.get("r", 0), color.get("g", 0), color.get("b", 0)
    a = color.get("a", 1.0) * paint_opacity
    return rgba_to_hex(r, g, b, a)


def normalize_fills(
    raw_json: str | None, bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize Figma fills JSON to IR fill array.

    Handles SOLID and GRADIENT_* types. Skips invisible fills.
    Token bindings overlay as "{token.name}" where they exist.
    """
    if not raw_json or raw_json == "[]":
        return []

    try:
        fills = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return []

    binding_map = {b["property"]: b.get("token_name") for b in bindings if b.get("token_name")}
    result = []

    for i, fill in enumerate(fills):
        if fill.get("visible") is False:
            continue

        fill_type = fill.get("type", "")
        paint_opacity = fill.get("opacity", 1.0)

        if fill_type == "SOLID":
            color = fill.get("color", {})
            hex_val = _figma_color_to_hex(color, 1.0)
            token = binding_map.get(f"fill.{i}.color")
            entry: dict[str, Any] = {
                "type": "solid",
                "color": f"{{{token}}}" if token else hex_val,
            }
            if paint_opacity < 1.0:
                entry["opacity"] = paint_opacity
            result.append(entry)

        elif fill_type in _GRADIENT_TYPE_MAP:
            stops = []
            for j, stop in enumerate(fill.get("gradientStops", [])):
                stop_color = stop.get("color", {})
                stop_hex = _figma_color_to_hex(stop_color, 1.0)
                stop_token = binding_map.get(f"fill.{i}.gradient.stop.{j}.color")
                stops.append({
                    "color": f"{{{stop_token}}}" if stop_token else stop_hex,
                    "position": stop.get("position", 0.0),
                })
            entry = {
                "type": _GRADIENT_TYPE_MAP[fill_type],
                "stops": stops,
            }
            handle_positions = fill.get("gradientHandlePositions")
            if handle_positions:
                entry["handlePositions"] = handle_positions
            if paint_opacity < 1.0:
                entry["opacity"] = paint_opacity
            result.append(entry)

    return result


def normalize_strokes(
    raw_json: str | None, bindings: list[dict[str, Any]], node: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize Figma strokes JSON to IR stroke array."""
    if not raw_json or raw_json == "[]":
        return []

    try:
        strokes = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return []

    binding_map = {b["property"]: b.get("token_name") for b in bindings if b.get("token_name")}
    result = []

    for i, stroke in enumerate(strokes):
        if stroke.get("visible") is False:
            continue
        if stroke.get("type") != "SOLID":
            continue

        color = stroke.get("color", {})
        hex_val = _figma_color_to_hex(color, 1.0)
        token = binding_map.get(f"stroke.{i}.color")

        entry: dict[str, Any] = {
            "type": "solid",
            "color": f"{{{token}}}" if token else hex_val,
            "width": int(node.get("stroke_weight") or 1),
        }
        align = node.get("stroke_align")
        if align:
            entry["align"] = align.lower()
        result.append(entry)

    return result


def normalize_effects(
    raw_json: str | None, bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize Figma effects JSON to IR effect array."""
    if not raw_json or raw_json == "[]":
        return []

    try:
        effects = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return []

    binding_map = {b["property"]: b.get("token_name") for b in bindings if b.get("token_name")}
    result = []

    for i, effect in enumerate(effects):
        if effect.get("visible") is False:
            continue

        effect_type = effect.get("type", "")

        if effect_type in ("DROP_SHADOW", "INNER_SHADOW"):
            color = effect.get("color", {})
            hex_val = _figma_color_to_hex(color, 1.0)
            token = binding_map.get(f"effect.{i}.color")
            offset = effect.get("offset", {})
            result.append({
                "type": "drop-shadow" if effect_type == "DROP_SHADOW" else "inner-shadow",
                "color": f"{{{token}}}" if token else hex_val,
                "offset": {"x": offset.get("x", 0), "y": offset.get("y", 0)},
                "blur": effect.get("radius", 0),
                "spread": effect.get("spread", 0),
            })

        elif effect_type in ("LAYER_BLUR", "BACKGROUND_BLUR"):
            result.append({
                "type": "layer-blur" if effect_type == "LAYER_BLUR" else "background-blur",
                "radius": effect.get("radius", 0),
            })

    return result


def normalize_corner_radius(
    raw_value: str | int | float | None,
) -> float | dict[str, float] | None:
    """Normalize corner radius to number or per-corner dict."""
    if raw_value is None:
        return None

    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except (json.JSONDecodeError, ValueError):
            try:
                parsed = float(raw_value)
            except ValueError:
                return None
        raw_value = parsed

    if isinstance(raw_value, (int, float)):
        return float(raw_value) if raw_value > 0 else None

    if isinstance(raw_value, dict):
        result = {}
        for key in ("tl", "tr", "bl", "br"):
            val = raw_value.get(key, 0)
            if val > 0:
                result[key] = float(val)
        return result if result else None

    return None


# Typography binding properties → IR style key (visual props handled by _build_visual)
_TYPOGRAPHY_BINDING_MAP = {
    "fontSize": "fontSize",
    "fontFamily": "fontFamily",
    "fontWeight": "fontWeight",
    "lineHeight": "lineHeight",
    "letterSpacing": "letterSpacing",
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


def _build_binding_index(bindings: list[dict[str, Any]]) -> dict[str, str]:
    """Build property → token ref string from bindings list.

    Returns dict mapping Figma property names to "{token.name}" strings
    for bindings that have a token_name set.
    """
    index: dict[str, str] = {}
    for b in bindings:
        if b.get("token_name"):
            index[b["property"]] = f"{{{b['token_name']}}}"
    return index


# Properties that belong in layout, not style
_LAYOUT_BINDING_PROPERTIES = frozenset({
    "padding.top", "padding.right", "padding.bottom", "padding.left",
    "itemSpacing", "counterAxisSpacing",
})


def map_node_to_element(node: dict[str, Any]) -> dict[str, Any]:
    """Convert a classified node dict to an IR element.

    Expects node dict with keys: canonical_type, layout_mode, padding_*,
    item_spacing, layout_sizing_h/v, text_content, corner_radius, opacity,
    and bindings (list of {property, token_name, resolved_value}).
    """
    bindings = node.get("bindings", [])
    binding_index = _build_binding_index(bindings)

    resolved_type = node.get("canonical_type") or node.get("node_type", "frame").lower()

    element: dict[str, Any] = {
        "type": resolved_type,
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

    if node.get("visible") == 0:
        element["visible"] = False

    return element


def _build_layout(node: dict[str, Any], binding_index: dict[str, str]) -> dict[str, Any]:
    layout: dict[str, Any] = {}

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


def _build_padding(node: dict[str, Any], binding_index: dict[str, str]) -> dict[str, Any] | None:
    padding: dict[str, Any] = {}
    for side in ("top", "right", "bottom", "left"):
        token = binding_index.get(f"padding.{side}")
        val = node.get(f"padding_{side}")
        if token:
            padding[side] = token
        elif val and val > 0:
            padding[side] = val

    return padding if padding else None


def _build_sizing(node: dict[str, Any]) -> dict[str, Any] | None:
    """Build sizing dict from node layout sizing modes + pixel dimensions.

    FILL/HUG → store as string (parent/content determines size).
    FIXED or NULL → store pixel value (explicit dimensions needed).
    """
    sizing: dict[str, Any] = {}
    h = node.get("layout_sizing_h")
    v = node.get("layout_sizing_v")
    width = node.get("width")
    height = node.get("height")

    if h in ("FILL", "HUG"):
        sizing["width"] = _SIZING_MAP[h]
    elif width is not None:
        sizing["width"] = width

    if v in ("FILL", "HUG"):
        sizing["height"] = _SIZING_MAP[v]
    elif height is not None:
        sizing["height"] = height

    return sizing if sizing else None


def _build_style(node: dict[str, Any], binding_index: dict[str, str]) -> dict[str, Any]:
    """Build style section — typography bindings only."""
    style: dict[str, Any] = {}

    for binding in node.get("bindings", []):
        prop = binding["property"]
        token_name = binding.get("token_name")
        resolved = binding.get("resolved_value")

        ir_key = _TYPOGRAPHY_BINDING_MAP.get(prop)
        if ir_key is None:
            continue

        if token_name:
            style[ir_key] = f"{{{token_name}}}"
        elif resolved:
            style[ir_key] = resolved

    return style


def _build_props(node: dict[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = {}

    canonical_type = node.get("canonical_type") or node.get("node_type", "").lower()
    text = node.get("text_content")

    if text and canonical_type in _TEXT_PROP_TYPES:
        props["text"] = text

    return props


# ---------------------------------------------------------------------------
# Query layer
# ---------------------------------------------------------------------------

def query_screen_visuals(conn: sqlite3.Connection, screen_id: int) -> dict[int, dict[str, Any]]:
    """Fetch visual properties for all nodes in a screen.

    Returns dict keyed by node_id with fills, strokes, effects,
    corner_radius, opacity, stroke_weight, stroke_align, blend_mode,
    component_key, typography, constraints, and token bindings.

    This is the renderer's DB access path — it provides all the visual
    data needed to render a screen without reading the IR's visual section.
    """
    has_registry = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='component_key_registry'"
    ).fetchone()

    if has_registry:
        cursor = conn.execute(
            "SELECT n.id, n.fills, n.strokes, n.effects, n.corner_radius, n.opacity, "
            "n.stroke_weight, n.stroke_align, n.blend_mode, n.visible, n.clips_content, "
            "n.component_key, n.rotation, n.constraint_h, n.constraint_v, "
            "n.font_family, n.font_weight, n.font_size, n.font_style, n.line_height, "
            "n.letter_spacing, n.text_align, n.text_content, "
            "ckr.figma_node_id as component_figma_id "
            "FROM nodes n "
            "LEFT JOIN component_key_registry ckr ON n.component_key = ckr.component_key "
            "WHERE n.screen_id = ?",
            (screen_id,),
        )
    else:
        cursor = conn.execute(
            "SELECT id, fills, strokes, effects, corner_radius, opacity, "
            "stroke_weight, stroke_align, blend_mode, visible, clips_content, "
            "component_key, rotation, constraint_h, constraint_v, "
            "font_family, font_weight, font_size, font_style, line_height, "
            "letter_spacing, text_align, text_content "
            "FROM nodes WHERE screen_id = ?",
            (screen_id,),
        )
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    if not rows:
        return {}

    node_ids = [row[0] for row in rows]
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        node_dict = dict(zip(columns, row))
        node_id = node_dict.pop("id")
        node_dict["bindings"] = []
        result[node_id] = node_dict

    placeholders = ",".join("?" for _ in node_ids)
    bindings_cursor = conn.execute(
        f"SELECT ntb.node_id, ntb.property, t.name as token_name, ntb.resolved_value "
        f"FROM node_token_bindings ntb "
        f"LEFT JOIN tokens t ON ntb.token_id = t.id "
        f"WHERE ntb.node_id IN ({placeholders}) AND ntb.binding_status = 'bound'",
        node_ids,
    )
    for row in bindings_cursor.fetchall():
        node_id = row[0]
        if node_id in result:
            result[node_id]["bindings"].append({
                "property": row[1],
                "token_name": row[2],
                "resolved_value": row[3],
            })

    instance_ids = [nid for nid, v in result.items() if v.get("component_key")]
    if instance_ids:
        ph = ",".join("?" for _ in instance_ids)
        hidden_cursor = conn.execute(
            f"SELECT root.id as instance_id, c.name "
            f"FROM nodes root "
            f"JOIN nodes p ON p.parent_id = root.id "
            f"JOIN nodes c ON c.parent_id = p.id "
            f"WHERE root.id IN ({ph}) AND c.visible = 0 "
            f"UNION "
            f"SELECT parent_id as instance_id, name "
            f"FROM nodes "
            f"WHERE parent_id IN ({ph}) AND visible = 0",
            instance_ids + instance_ids,
        )
        for row in hidden_cursor.fetchall():
            instance_id = row[0]
            if instance_id in result:
                if "hidden_children" not in result[instance_id]:
                    result[instance_id]["hidden_children"] = []
                result[instance_id]["hidden_children"].append({"name": row[1]})

        # Instance overrides (text, visibility, instance swap from Plugin API)
        has_overrides = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='instance_overrides'"
        ).fetchone()
        if has_overrides:
            override_cursor = conn.execute(
                f"SELECT node_id, property_type, property_name, override_value "
                f"FROM instance_overrides WHERE node_id IN ({ph})",
                instance_ids,
            )
            for row in override_cursor.fetchall():
                node_id = row[0]
                if node_id in result:
                    if "instance_overrides" not in result[node_id]:
                        result[node_id]["instance_overrides"] = []
                    result[node_id]["instance_overrides"].append({
                        "type": row[1],
                        "child_id": row[2],
                        "value": row[3],
                    })

        # Instance child swaps from two sources:
        # 1. instance_overrides INSTANCE_SWAP entries (from Figma's overrides API)
        # 2. Descendant instances with component_keys (from recursive CTE)
        # Source 1 catches swaps that Figma reports on the parent instance.
        # Source 2 catches swaps on nested children that Figma reports on the
        # child instance itself (e.g., icon swaps inside buttons).
        # Deduplicate by child_id to avoid double-swapping.
        swap_child_ids_seen: dict[int, set[str]] = {}

        if has_overrides:
            swap_cursor = conn.execute(
                f"SELECT node_id, property_name, override_value "
                f"FROM instance_overrides "
                f"WHERE node_id IN ({ph}) AND property_type = 'INSTANCE_SWAP'",
                instance_ids,
            )
            for row in swap_cursor.fetchall():
                inst_id = row[0]
                child_id = row[1]
                swap_target_id = row[2]
                if inst_id in result and child_id and swap_target_id:
                    if "child_swaps" not in result[inst_id]:
                        result[inst_id]["child_swaps"] = []
                    result[inst_id]["child_swaps"].append({
                        "child_id": child_id,
                        "swap_target_id": swap_target_id,
                    })
                    if inst_id not in swap_child_ids_seen:
                        swap_child_ids_seen[inst_id] = set()
                    swap_child_ids_seen[inst_id].add(child_id)

        # Source 2: recursive CTE for descendant instances at any depth.
        # Finds ALL INSTANCE descendants within each top-level instance's
        # subtree, deduplicating against Source 1 via swap_child_ids_seen.
        # swapComponent is a no-op when the component already matches.
        if has_registry:
            child_swap_cursor = conn.execute(
                f"WITH RECURSIVE subtree(id, root_id) AS ("
                f"  SELECT id, id as root_id FROM nodes WHERE id IN ({ph}) "
                f"  UNION ALL "
                f"  SELECT n.id, s.root_id FROM nodes n JOIN subtree s ON n.parent_id = s.id"
                f") "
                f"SELECT s.root_id, c.figma_node_id, ckr.figma_node_id as swap_target_id "
                f"FROM nodes c "
                f"JOIN subtree s ON c.id = s.id "
                f"JOIN component_key_registry ckr ON c.component_key = ckr.component_key "
                f"WHERE c.node_type = 'INSTANCE' AND c.component_key IS NOT NULL "
                f"AND c.visible = 1 AND c.id != s.root_id",
                instance_ids,
            )
            for row in child_swap_cursor.fetchall():
                root_inst_id = row[0]
                child_figma_id = row[1]
                swap_target_id = row[2]
                if root_inst_id in result and child_figma_id and swap_target_id and ";" in child_figma_id:
                    master_child_id = child_figma_id[child_figma_id.index(";"):]
                    seen = swap_child_ids_seen.get(root_inst_id, set())
                    if master_child_id not in seen:
                        if "child_swaps" not in result[root_inst_id]:
                            result[root_inst_id]["child_swaps"] = []
                        result[root_inst_id]["child_swaps"].append({
                            "child_id": master_child_id,
                            "swap_target_id": swap_target_id,
                        })

    return result


def query_slot_definitions(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """Fetch slot definitions keyed by component name.

    Returns dict mapping component name to list of slot dicts, each with
    name, slot_type, is_required, sort_order. Used by build_semantic_tree
    to assign children to named slots.
    """
    cursor = conn.execute(
        "SELECT c.name as component_name, cs.name, cs.slot_type, cs.is_required, cs.sort_order "
        "FROM component_slots cs "
        "JOIN components c ON cs.component_id = c.id "
        "ORDER BY c.name, cs.sort_order"
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for row in cursor.fetchall():
        comp_name = row[0]
        if comp_name not in result:
            result[comp_name] = []
        result[comp_name].append({
            "name": row[1],
            "slot_type": row[2],
            "is_required": row[3],
            "sort_order": row[4],
        })
    return result


def filter_system_chrome(
    spec: dict[str, Any], node_names: dict[int, str],
) -> dict[str, Any]:
    """Remove system chrome elements from a CompositionSpec.

    Takes a spec and a mapping of node_id → node name. Removes elements
    whose source node name matches system chrome patterns (iOS/StatusBar,
    HomeIndicator, Safari, keyboards, etc). Does not mutate the input.
    """
    node_id_map = spec.get("_node_id_map", {})
    chrome_eids = set()

    for eid, node_id in node_id_map.items():
        name = node_names.get(node_id, "")
        if is_system_chrome(name):
            chrome_eids.add(eid)

    if not chrome_eids:
        return spec

    new_elements = {}
    for eid, element in spec["elements"].items():
        if eid in chrome_eids:
            continue
        new_element = dict(element)
        if "children" in new_element:
            new_element["children"] = [
                c for c in new_element["children"] if c not in chrome_eids
            ]
        new_elements[eid] = new_element

    new_node_id_map = {
        eid: nid for eid, nid in node_id_map.items() if eid not in chrome_eids
    }

    return {**spec, "elements": new_elements, "_node_id_map": new_node_id_map}


def _assign_children_to_slots(
    children_eids: list[str],
    slot_defs: list[dict[str, Any]],
    node_id_map: dict[str, int],
    node_data: dict[int, dict[str, Any]],
    parent_node_id: int,
) -> dict[str, list[str]]:
    """Assign child element IDs to named slots by spatial position.

    Divides the parent's width into N equal zones (one per slot) and
    assigns each child to the zone its x-coordinate falls into.
    """
    parent_info = node_data.get(parent_node_id, {})
    parent_width = parent_info.get("width", 0)
    num_slots = len(slot_defs)

    if num_slots == 0 or parent_width == 0:
        return {}

    zone_width = parent_width / num_slots
    parent_x = parent_info.get("x", 0)

    slots: dict[str, list[str]] = {s["name"]: [] for s in slot_defs}
    slot_names_ordered = [s["name"] for s in slot_defs]

    for child_eid in children_eids:
        child_node_id = node_id_map.get(child_eid)
        if child_node_id is None:
            continue
        child_info = node_data.get(child_node_id, {})
        child_x = child_info.get("x", 0)
        child_width = child_info.get("width", 0)
        relative_x = (child_x + child_width / 2) - parent_x
        slot_index = min(int(relative_x / zone_width), num_slots - 1)
        slot_index = max(slot_index, 0)
        slots[slot_names_ordered[slot_index]].append(child_eid)

    return slots


def build_semantic_tree(
    spec: dict[str, Any],
    slot_defs: dict[str, list[dict[str, Any]]],
    node_data: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Collapse a flat CompositionSpec into a semantic tree with slots.

    For each element whose component has slot definitions, assigns its
    children to named slots by spatial position. Children are moved from
    the `children` list to a `slots` dict. Elements without slot defs
    keep their `children` list unchanged. Does not mutate the input.
    """
    node_id_map = spec.get("_node_id_map", {})
    new_elements: dict[str, dict[str, Any]] = {}

    component_name_by_eid: dict[str, str] = {}
    for eid, node_id in node_id_map.items():
        info = node_data.get(node_id, {})
        component_name_by_eid[eid] = info.get("name", "")

    for eid, element in spec["elements"].items():
        new_element = dict(element)
        children = element.get("children", [])
        comp_name = component_name_by_eid.get(eid, "")
        defs = slot_defs.get(comp_name)

        if defs and children:
            parent_node_id = node_id_map.get(eid)
            if parent_node_id is not None:
                assigned = _assign_children_to_slots(
                    children, defs, node_id_map, node_data, parent_node_id,
                )
                if assigned:
                    new_element["slots"] = assigned
                    del new_element["children"]

        new_elements[eid] = new_element

    return {**spec, "elements": new_elements}


def query_screen_for_ir(conn: sqlite3.Connection, screen_id: int) -> dict[str, Any]:
    """Fetch all nodes for a screen with L1/L2 annotations where available.

    Uses LEFT JOIN on screen_component_instances so ALL nodes are returned.
    Classified nodes have canonical_type, sci_id, parent_instance_id set.
    Unclassified nodes have those fields as NULL — the renderer uses
    progressive fallback (L2 → L1 → L0) to handle both cases.

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
        "n.text_content, n.corner_radius, n.opacity, n.fills, n.strokes, n.effects, "
        "n.font_family, n.font_weight, n.font_size, "
        "n.parent_id, n.component_key, n.visible, "
        "sci.canonical_type, sci.id as sci_id, sci.parent_instance_id "
        "FROM nodes n "
        "LEFT JOIN screen_component_instances sci ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
        "WHERE n.screen_id = ? "
        "ORDER BY n.depth, n.sort_order",
        (screen_id,),
    )
    columns = [desc[0] for desc in cursor.description]
    all_nodes = [dict(zip(columns, row)) for row in cursor.fetchall()]

    bindings_cursor = conn.execute(
        "SELECT ntb.node_id, ntb.property, t.name as token_name, ntb.resolved_value "
        "FROM node_token_bindings ntb "
        "JOIN nodes n ON ntb.node_id = n.id "
        "LEFT JOIN tokens t ON ntb.token_id = t.id "
        "WHERE n.screen_id = ? AND ntb.binding_status = 'bound'",
        (screen_id,),
    )
    bindings_by_node: dict[int, list[dict[str, Any]]] = {}
    for row in bindings_cursor.fetchall():
        node_id = row[0]
        if node_id not in bindings_by_node:
            bindings_by_node[node_id] = []
        bindings_by_node[node_id].append({
            "property": row[1],
            "token_name": row[2],
            "resolved_value": row[3],
        })

    for node_dict in all_nodes:
        node_dict["bindings"] = bindings_by_node.get(node_dict["node_id"], [])

    tokens_cursor = conn.execute(
        "SELECT DISTINCT t.name, ntb.resolved_value "
        "FROM node_token_bindings ntb "
        "JOIN nodes n ON ntb.node_id = n.id "
        "JOIN tokens t ON ntb.token_id = t.id "
        "WHERE n.screen_id = ? AND ntb.binding_status = 'bound'",
        (screen_id,),
    )
    tokens = {row[0]: row[1] for row in tokens_cursor.fetchall()}

    origin_row = conn.execute(
        "SELECT x, y FROM nodes WHERE screen_id = ? AND depth = 0 LIMIT 1",
        (screen_id,),
    ).fetchone()
    screen_origin_x = origin_row[0] if origin_row else 0
    screen_origin_y = origin_row[1] if origin_row else 0

    return {
        "screen_name": screen_row[0],
        "width": screen_row[1],
        "height": screen_row[2],
        "nodes": all_nodes,
        "tokens": tokens,
        "screen_origin_x": screen_origin_x or 0,
        "screen_origin_y": screen_origin_y or 0,
    }


# ---------------------------------------------------------------------------
# Composition assembly
# ---------------------------------------------------------------------------

def build_composition_spec(data: dict[str, Any]) -> dict[str, Any]:
    """Assemble a CompositionSpec from query results.

    Builds the flat element map, assigns IDs, wires parent→children
    relationships, and collects referenced tokens.
    """
    nodes = data.get("nodes", [])
    if not nodes:
        return {"version": "1.0", "root": "", "elements": {}, "tokens": {}, "_node_id_map": {}}

    type_counters: dict[str, int] = {}
    node_id_to_element_id: dict[int, str] = {}
    sci_id_to_element_id: dict[int, str] = {}
    elements: dict[str, dict[str, Any]] = {}

    for node in nodes:
        resolved_type = node.get("canonical_type") or node.get("node_type", "frame").lower()
        type_counters[resolved_type] = type_counters.get(resolved_type, 0) + 1
        element_id = f"{resolved_type}-{type_counters[resolved_type]}"

        node_id_to_element_id[node["node_id"]] = element_id
        if node.get("sci_id") is not None:
            sci_id_to_element_id[node["sci_id"]] = element_id

        element = map_node_to_element(node)
        if node.get("name"):
            element["_original_name"] = node["name"]
        elements[element_id] = element

    # Wire children: use parent_instance_id (L1 classified→classified) or
    # parent_id (L0 node→node) to build the tree
    children_map: dict[str, list[str]] = {}
    has_parent = set()

    for node in nodes:

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

    # Build node lookup for position data
    node_by_id = {n["node_id"]: n for n in nodes}
    origin_x = data.get("screen_origin_x", 0)
    origin_y = data.get("screen_origin_y", 0)

    # Absolute positioning: children of non-auto-layout parents get explicit x/y.
    # In Figma, children of frames with no layoutMode are absolutely positioned.
    # Auto-layout children (parent has HORIZONTAL/VERTICAL) get position from flow.
    element_id_to_nid = {eid: nid for nid, eid in node_id_to_element_id.items()}

    for node in nodes:
        eid = node_id_to_element_id.get(node["node_id"])
        if eid is None:
            continue

        parent_node_id = node.get("parent_id")
        if parent_node_id is None:
            # Root-level element: position relative to screen origin
            if "layout" not in elements[eid]:
                elements[eid]["layout"] = {}
            elements[eid]["layout"]["position"] = {
                "x": (node.get("x", 0) or 0) - origin_x,
                "y": (node.get("y", 0) or 0) - origin_y,
            }
            continue

        parent_node = node_by_id.get(parent_node_id)
        if parent_node is None:
            continue

        parent_layout_mode = parent_node.get("layout_mode")
        if parent_layout_mode in ("HORIZONTAL", "VERTICAL"):
            continue  # Auto-layout child — position comes from flow

        # Parent has no auto-layout: set position relative to parent origin
        parent_x = parent_node.get("x", 0) or 0
        parent_y = parent_node.get("y", 0) or 0
        node_x = node.get("x", 0) or 0
        node_y = node.get("y", 0) or 0

        if "layout" not in elements[eid]:
            elements[eid]["layout"] = {}
        elements[eid]["layout"]["position"] = {
            "x": node_x - parent_x,
            "y": node_y - parent_y,
        }

    root_id = "screen-1"
    elements[root_id] = {
        "type": "screen",
        "layout": {
            "direction": "absolute",
            "sizing": {"width": data.get("width", 0), "height": data.get("height", 0)},
        },
        "children": root_ids,
    }

    element_id_to_node_id = {eid: nid for nid, eid in node_id_to_element_id.items()}

    return {
        "version": "1.0",
        "root": root_id,
        "elements": elements,
        "tokens": data.get("tokens", {}),
        "_node_id_map": element_id_to_node_id,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_ir(
    conn: sqlite3.Connection, screen_id: int, semantic: bool = False,
) -> dict[str, Any]:
    """Generate CompositionSpec IR for a single screen.

    When semantic=True, collapses the flat element tree into a semantic
    tree with named slots, filters system chrome, and produces ~15-25
    elements instead of ~100+.

    Returns dict with 'spec' (the CompositionSpec dict) and 'json' (serialized).
    """
    import json as json_mod
    data = query_screen_for_ir(conn, screen_id)
    spec = build_composition_spec(data)

    if semantic:
        node_id_map = spec.get("_node_id_map", {})
        node_names = {}
        node_positions = {}
        for eid, nid in node_id_map.items():
            row = conn.execute(
                "SELECT name, x, y, width, height FROM nodes WHERE id = ?", (nid,),
            ).fetchone()
            if row:
                node_names[nid] = row[0]
                node_positions[nid] = {
                    "x": row[1], "y": row[2], "width": row[3], "height": row[4],
                    "name": row[0],
                }

        spec = filter_system_chrome(spec, node_names)

        slot_defs = query_slot_definitions(conn)
        spec = build_semantic_tree(spec, slot_defs, node_positions)

    return {
        "spec": spec,
        "json": json_mod.dumps(spec, indent=2),
        "element_count": len(spec.get("elements", {})),
        "token_count": len(spec.get("tokens", {})),
    }
