"""Prompt→IR composition + template-based rendering (Phase 4b).

Composes a CompositionSpec from a list of component descriptions,
populates visual data from extracted templates, and generates Figma JS.
"""

import sqlite3
from typing import Any, Dict, List, Optional

from dd.generate import generate_figma_script
from dd.templates import query_templates


_DIRECTION_MAP = {
    "HORIZONTAL": "horizontal",
    "VERTICAL": "vertical",
}

_SIZING_MAP = {
    "FILL": "fill",
    "HUG": "hug",
    "FIXED": "fixed",
}


def _pick_best_template(
    tmpl_list: Optional[List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """Pick the best template from a list, preferring one with a component_key.

    Prefers the keyed template with the highest instance count (Mode 1).
    Falls back to keyless (Mode 2) if no keyed template exists.
    """
    if not tmpl_list:
        return None
    keyed = [t for t in tmpl_list if t.get("component_key")]
    if keyed:
        return max(keyed, key=lambda t: t.get("instance_count") or 0)
    return tmpl_list[0]


def compose_screen(
    components: List[Dict[str, Any]],
    templates: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Build a CompositionSpec from a list of component descriptions.

    Each component is a dict with 'type' (required), 'props' (optional),
    and 'children' (optional, recursive). Templates provide layout
    defaults (dimensions, padding, direction) when available.
    """
    type_counters: Dict[str, int] = {}
    elements: Dict[str, Dict[str, Any]] = {}

    def _allocate_id(comp_type: str) -> str:
        type_counters[comp_type] = type_counters.get(comp_type, 0) + 1
        return f"{comp_type}-{type_counters[comp_type]}"

    def _build_element(comp: Dict[str, Any]) -> str:
        comp_type = comp["type"]
        eid = _allocate_id(comp_type)

        element: Dict[str, Any] = {"type": comp_type}

        layout = _build_layout_from_template(comp_type, templates)
        if layout:
            element["layout"] = layout

        props = comp.get("props")
        if props:
            element["props"] = dict(props)

        children = comp.get("children", [])
        if children:
            child_ids = [_build_element(child) for child in children]
            element["children"] = child_ids

        elements[eid] = element
        return eid

    root_child_ids = [_build_element(comp) for comp in components]

    root_id = "screen-1"
    elements[root_id] = {
        "type": "screen",
        "layout": {
            "direction": "vertical",
            "sizing": {"width": 428, "height": 926},
        },
        "children": root_child_ids,
    }

    return {
        "version": "1.0",
        "root": root_id,
        "elements": elements,
        "tokens": {},
        "_node_id_map": {},
    }


def _build_layout_from_template(
    comp_type: str,
    templates: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Build layout dict from template defaults for a component type."""
    layout: Dict[str, Any] = {}

    if not templates or comp_type not in templates:
        layout["direction"] = "vertical"
        return layout

    tmpl = _pick_best_template(templates.get(comp_type))
    if not tmpl:
        layout["direction"] = "vertical"
        return layout

    direction = _DIRECTION_MAP.get(tmpl.get("layout_mode") or "", "stacked")
    layout["direction"] = direction

    width = tmpl.get("width")
    height = tmpl.get("height")
    sizing: Dict[str, Any] = {}
    if width is not None:
        sizing["width"] = width
    if height is not None:
        sizing["height"] = height
    if sizing:
        layout["sizing"] = sizing

    gap = tmpl.get("item_spacing")
    if gap and gap > 0:
        layout["gap"] = gap

    padding: Dict[str, float] = {}
    for side in ("top", "right", "bottom", "left"):
        val = tmpl.get(f"padding_{side}")
        if val and val > 0:
            padding[side] = val
    if padding:
        layout["padding"] = padding

    return layout


def build_template_visuals(
    spec: Dict[str, Any],
    templates: Dict[str, List[Dict[str, Any]]],
) -> Dict[int, Dict[str, Any]]:
    """Map spec elements to template visual data.

    Assigns synthetic negative node IDs to each element and builds a
    db_visuals-compatible dict from template visual defaults. Mutates
    spec to add _node_id_map.
    """
    node_id_map: Dict[str, int] = {}
    visuals: Dict[int, Dict[str, Any]] = {}

    for idx, (eid, element) in enumerate(spec["elements"].items()):
        synthetic_nid = -(idx + 1)
        node_id_map[eid] = synthetic_nid

        comp_type = element.get("type", "")
        tmpl_list = templates.get(comp_type)
        tmpl = _pick_best_template(tmpl_list)

        visuals[synthetic_nid] = {
            "fills": tmpl.get("fills") if tmpl else None,
            "strokes": tmpl.get("strokes") if tmpl else None,
            "effects": tmpl.get("effects") if tmpl else None,
            "corner_radius": tmpl.get("corner_radius") if tmpl else None,
            "opacity": tmpl.get("opacity") if tmpl else None,
            "stroke_weight": None,
            "component_key": tmpl.get("component_key") if tmpl else None,
            "component_figma_id": tmpl.get("component_figma_id") if tmpl else None,
            "bindings": [],
        }

    spec["_node_id_map"] = node_id_map
    return visuals


def generate_from_prompt(
    conn: sqlite3.Connection,
    components: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate Figma JS from a component list using templates.

    Orchestrates: query_templates → compose_screen → build_template_visuals
    → generate_figma_script. Returns dict with structure_script and metadata.
    """
    templates = query_templates(conn)
    spec = compose_screen(components, templates=templates)
    visuals = build_template_visuals(spec, templates)
    script, token_refs = generate_figma_script(spec, db_visuals=visuals)

    return {
        "structure_script": script,
        "token_refs": token_refs,
        "element_count": len(spec["elements"]),
        "spec": spec,
    }
