"""Prompt→IR composition + template-based rendering (Phase 4b).

Composes a CompositionSpec from a list of component descriptions,
populates visual data from extracted templates, and generates Figma JS.
"""

import json
import sqlite3
from typing import Any

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
    tmpl_list: list[dict[str, Any]] | None,
    variant: str | None = None,
) -> dict[str, Any] | None:
    """Pick the best template from a list, preferring one with a component_key.

    When variant is provided, prefers the template matching that variant name.
    Otherwise prefers the keyed template with the highest instance count (Mode 1).
    Falls back to keyless (Mode 2) if no keyed template exists.
    """
    if not tmpl_list:
        return None

    if variant:
        match = next((t for t in tmpl_list if t.get("variant") == variant), None)
        if match:
            return match

    keyed = [t for t in tmpl_list if t.get("component_key")]
    if keyed:
        return max(keyed, key=lambda t: t.get("instance_count") or 0)
    return tmpl_list[0]


def compose_screen(
    components: list[dict[str, Any]],
    templates: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build a CompositionSpec from a list of component descriptions.

    Each component is a dict with 'type' (required), 'props' (optional),
    and 'children' (optional, recursive). Templates provide layout
    defaults (dimensions, padding, direction) when available.
    """
    type_counters: dict[str, int] = {}
    elements: dict[str, dict[str, Any]] = {}

    def _allocate_id(comp_type: str) -> str:
        type_counters[comp_type] = type_counters.get(comp_type, 0) + 1
        return f"{comp_type}-{type_counters[comp_type]}"

    def _build_element(comp: dict[str, Any]) -> str:
        comp_type = comp["type"]
        eid = _allocate_id(comp_type)

        element: dict[str, Any] = {"type": comp_type}

        variant = comp.get("variant")
        if variant:
            element["variant"] = variant

        layout = _build_layout_from_template(comp_type, templates, variant=variant)
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
    screen_layout: dict[str, Any] = {
        "direction": "vertical",
        "sizing": {"width": 428, "height": 926},
    }

    screen_tmpl = _pick_best_template(templates.get("screen")) if templates else None
    if screen_tmpl:
        w = screen_tmpl.get("width")
        h = screen_tmpl.get("height")
        if w and h:
            screen_layout["sizing"] = {"width": w, "height": h}

    elements[root_id] = {
        "type": "screen",
        "layout": screen_layout,
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
    templates: dict[str, list[dict[str, Any]]] | None = None,
    variant: str | None = None,
) -> dict[str, Any]:
    """Build layout dict from template defaults for a component type."""
    layout: dict[str, Any] = {}

    if not templates or comp_type not in templates:
        layout["direction"] = "vertical"
        return layout

    tmpl = _pick_best_template(templates.get(comp_type), variant=variant)
    if not tmpl:
        layout["direction"] = "vertical"
        return layout

    direction = _DIRECTION_MAP.get(tmpl.get("layout_mode") or "", "stacked")
    layout["direction"] = direction

    sizing_h = tmpl.get("layout_sizing_h")
    sizing_v = tmpl.get("layout_sizing_v")
    width = tmpl.get("width")
    height = tmpl.get("height")
    sizing: dict[str, Any] = {}

    if sizing_h and sizing_h in _SIZING_MAP:
        sizing["width"] = _SIZING_MAP[sizing_h].lower()
    elif width is not None:
        sizing["width"] = width

    if sizing_v and sizing_v in _SIZING_MAP:
        sizing["height"] = _SIZING_MAP[sizing_v].lower()
    elif height is not None:
        sizing["height"] = height

    if sizing:
        layout["sizing"] = sizing

    gap = tmpl.get("item_spacing")
    if gap and gap > 0:
        layout["gap"] = gap

    padding: dict[str, float] = {}
    for side in ("top", "right", "bottom", "left"):
        val = tmpl.get(f"padding_{side}")
        if val and val > 0:
            padding[side] = val
    if padding:
        layout["padding"] = padding

    return layout


def _extract_bound_variables(
    raw_json: str | None,
    property_prefix: str,
) -> list[dict[str, str]]:
    """Extract boundVariables from raw Figma JSON fills/strokes.

    Returns a list of binding dicts with 'property' and 'variable_id'
    suitable for the rebind pipeline.
    """
    if not raw_json:
        return []
    try:
        items = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return []

    bindings: list[dict[str, str]] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        bound_vars = item.get("boundVariables", {})
        for prop_name, var_ref in bound_vars.items():
            if isinstance(var_ref, dict) and var_ref.get("id"):
                bindings.append({
                    "property": f"{property_prefix}.{i}.{prop_name}",
                    "variable_id": var_ref["id"],
                })
    return bindings


def build_template_visuals(
    spec: dict[str, Any],
    templates: dict[str, list[dict[str, Any]]],
) -> dict[int, dict[str, Any]]:
    """Map spec elements to template visual data.

    Assigns synthetic negative node IDs to each element and builds a
    db_visuals-compatible dict from template visual defaults. Mutates
    spec to add _node_id_map. Extracts boundVariables from template
    fills/strokes for token rebinding.
    """
    node_id_map: dict[str, int] = {}
    visuals: dict[int, dict[str, Any]] = {}

    for idx, (eid, element) in enumerate(spec["elements"].items()):
        synthetic_nid = -(idx + 1)
        node_id_map[eid] = synthetic_nid

        comp_type = element.get("type", "")
        variant = element.get("variant")
        tmpl_list = templates.get(comp_type)
        tmpl = _pick_best_template(tmpl_list, variant=variant)

        bindings: list[dict[str, str]] = []
        if tmpl:
            bindings.extend(_extract_bound_variables(tmpl.get("fills"), "fill"))
            bindings.extend(_extract_bound_variables(tmpl.get("strokes"), "stroke"))

        children_composition = tmpl.get("children_composition", []) if tmpl else []
        if children_composition:
            element["_composition"] = children_composition

        visuals[synthetic_nid] = {
            "fills": tmpl.get("fills") if tmpl else None,
            "strokes": tmpl.get("strokes") if tmpl else None,
            "effects": tmpl.get("effects") if tmpl else None,
            "corner_radius": tmpl.get("corner_radius") if tmpl else None,
            "opacity": tmpl.get("opacity") if tmpl else None,
            "stroke_weight": None,
            "component_key": tmpl.get("component_key") if tmpl else None,
            "component_figma_id": tmpl.get("component_figma_id") if tmpl else None,
            "bindings": bindings,
        }

    spec["_node_id_map"] = node_id_map
    return visuals


def collect_template_rebind_entries(
    spec: dict[str, Any],
    visuals: dict[int, dict[str, Any]],
) -> list[dict[str, str]]:
    """Collect variable rebind entries from template boundVariables.

    Returns entries with element_id, property, and variable_id that can
    be used with build_rebind_entries after Figma execution provides the
    M dict (element_id → figma_node_id).
    """
    node_id_map = spec.get("_node_id_map", {})
    eid_by_nid = {nid: eid for eid, nid in node_id_map.items()}

    entries: list[dict[str, str]] = []
    for nid, visual in visuals.items():
        eid = eid_by_nid.get(nid)
        if not eid:
            continue
        for binding in visual.get("bindings", []):
            entries.append({
                "element_id": eid,
                "property": binding["property"],
                "variable_id": binding["variable_id"],
            })
    return entries


def validate_components(
    components: list[dict[str, Any]],
    templates: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate LLM-output components against available templates.

    Returns (components, warnings). Components are passed through unchanged
    (the IR is valid at any completeness). Warnings list types that have
    no template and will render as empty frames.
    """
    available_types = set(templates.keys())
    warnings: list[str] = []

    for comp in components:
        comp_type = comp.get("type", "")
        if comp_type and comp_type not in available_types:
            warnings.append(
                f"Type '{comp_type}' has no template in this project — will render as empty frame"
            )
        for child in comp.get("children", []):
            child_type = child.get("type", "")
            if child_type and child_type not in available_types:
                warnings.append(
                    f"Type '{child_type}' has no template in this project — will render as empty frame"
                )

    return components, warnings


def generate_from_prompt(
    conn: sqlite3.Connection,
    components: list[dict[str, Any]],
    page_name: str | None = None,
) -> dict[str, Any]:
    """Generate Figma JS from a component list using templates.

    Orchestrates: query_templates → validate → compose_screen → build_template_visuals
    → generate_figma_script. Returns dict with structure_script and metadata.
    When page_name is provided, the script creates a new Figma page.
    """
    templates = query_templates(conn)
    components, warnings = validate_components(components, templates)
    spec = compose_screen(components, templates=templates)
    visuals = build_template_visuals(spec, templates)
    script, token_refs = generate_figma_script(spec, db_visuals=visuals, page_name=page_name)
    template_rebind_entries = collect_template_rebind_entries(spec, visuals)

    return {
        "structure_script": script,
        "token_refs": token_refs,
        "template_rebind_entries": template_rebind_entries,
        "element_count": len(spec["elements"]),
        "spec": spec,
        "warnings": warnings,
    }
