"""Figma generation from CompositionSpec IR (T5 Phase 3).

Takes a CompositionSpec JSON and produces:
  Phase A: A figma_execute script that creates frames/text with auto-layout
  Phase B: Rebind scripts that bind Figma variables to created nodes

Visual data source: DB path via query_screen_visuals() → build_visual_from_db()
  → _emit_visual pipeline. The IR does not carry visual data (thin IR).
"""

import re
import sqlite3
from typing import Any

from dd.ir import (
    normalize_corner_radius,
    normalize_effects,
    normalize_fills,
    normalize_strokes,
)

# Text element types that use figma.createText()
_TEXT_TYPES = frozenset({"text", "heading", "link"})

# Container types that should fill parent width in vertical auto-layout.
# These are full-width components that span the screen in real designs.
_FILL_WIDTH_TYPES = frozenset({
    "card", "accordion", "header", "search_input", "tabs",
    "drawer", "sheet", "alert", "empty_state",
})

_TOKEN_REF_RE = re.compile(r"^\{(.+)\}$")

# Node type → Figma creation call for non-FRAME types
_NODE_CREATE_MAP = {
    "rectangle": "figma.createRectangle()",
    "ellipse": "figma.createEllipse()",
    "line": "figma.createLine()",
}

# Node types that cannot be created in Figma — skip silently
_SKIP_NODE_TYPES = frozenset({"vector", "boolean_operation", "group"})

_WEIGHT_TO_STYLE = {
    100: "Thin",
    200: "Extra Light",
    300: "Light",
    400: "Regular",
    500: "Medium",
    600: "Semi Bold",
    700: "Bold",
    800: "Extra Bold",
    900: "Black",
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def hex_to_figma_rgb(hex_str: str) -> dict[str, float]:
    """Convert hex color string to Figma RGB dict {r, g, b} (0.0-1.0).

    Handles 6-digit (#FF0000) and 8-digit (#FF000080) hex. Alpha is dropped.
    """
    h = hex_str.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return {"r": round(r, 4), "g": round(g, 4), "b": round(b, 4)}


def resolve_style_value(
    value: Any, tokens: dict[str, Any],
) -> tuple[Any, str | None]:
    """Resolve a style/layout value that may be a token reference.

    Token refs are strings wrapped in braces: "{color.surface.primary}".
    Returns (resolved_value, token_name) — token_name is None for literals.
    """
    if not isinstance(value, str):
        return (value, None)

    match = _TOKEN_REF_RE.match(value)
    if not match:
        return (value, None)

    token_name = match.group(1)
    resolved = tokens.get(token_name)
    return (resolved, token_name)


def font_weight_to_style(weight: Any) -> str:
    """Convert numeric font weight to Figma style name.

    700 → "Bold", 400 → "Regular", 600 → "Semi Bold" (note the space).
    Handles int, float, and numeric strings like "500".
    """
    if weight is None:
        return "Regular"
    if isinstance(weight, str):
        try:
            weight = int(float(weight))
        except (ValueError, TypeError):
            return weight
    return _WEIGHT_TO_STYLE.get(int(weight), "Regular")


def collect_fonts(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """Collect unique (family, style) pairs from text elements in the spec."""
    seen = set()
    result = []

    tokens = spec.get("tokens", {})

    for element in spec.get("elements", {}).values():
        etype = element.get("type", "")
        if etype not in _TEXT_TYPES:
            continue

        style = element.get("style", {})
        family = style.get("fontFamily", "Inter")
        weight = style.get("fontWeight")

        if isinstance(family, str) and family.startswith("{"):
            resolved_family, _ = resolve_style_value(family, tokens)
            family = resolved_family if resolved_family and isinstance(resolved_family, str) else "Inter"

        family = _normalize_font_family(family)

        if isinstance(weight, str) and weight.startswith("{"):
            resolved_weight, _ = resolve_style_value(weight, tokens)
            weight = resolved_weight

        figma_style = font_weight_to_style(weight)
        key = (family, figma_style)
        if key not in seen:
            seen.add(key)
            result.append(key)

    return result


# ---------------------------------------------------------------------------
# DB → normalized visual (Phase 1: renderer reads DB instead of IR)
# ---------------------------------------------------------------------------

def build_visual_from_db(node_visual: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw DB visual data to the format _emit_visual expects.

    Takes a dict from query_screen_visuals() (raw Figma JSON strings +
    scalar columns + bindings list) and produces the same normalized
    visual dict that the IR's _build_visual() produces.
    """
    bindings = node_visual.get("bindings", [])
    visual: dict[str, Any] = {}

    fills = normalize_fills(node_visual.get("fills"), bindings)
    if fills:
        visual["fills"] = fills

    strokes = normalize_strokes(node_visual.get("strokes"), bindings, node_visual)
    if strokes:
        visual["strokes"] = strokes

    effects = normalize_effects(node_visual.get("effects"), bindings)
    if effects:
        visual["effects"] = effects

    radius = normalize_corner_radius(node_visual.get("corner_radius"))
    if radius is not None:
        visual["cornerRadius"] = radius

    opacity = node_visual.get("opacity")
    if opacity is not None and opacity < 1.0:
        visual["opacity"] = opacity

    clips = node_visual.get("clips_content")
    if clips:
        visual["clipsContent"] = True

    rotation = node_visual.get("rotation")
    if rotation is not None and rotation != 0:
        visual["rotation"] = rotation

    font_data: dict[str, Any] = {}
    for fk in ("font_family", "font_size", "font_weight", "font_style",
               "line_height", "letter_spacing", "text_align"):
        val = node_visual.get(fk)
        if val is not None:
            font_data[fk] = val
    if font_data:
        visual["font"] = font_data

    constraint_h = node_visual.get("constraint_h")
    constraint_v = node_visual.get("constraint_v")
    if constraint_h or constraint_v:
        constraints: dict[str, str] = {}
        if constraint_h:
            constraints["horizontal"] = constraint_h
        if constraint_v:
            constraints["vertical"] = constraint_v
        visual["constraints"] = constraints

    return visual


# ---------------------------------------------------------------------------
# JS helpers
# ---------------------------------------------------------------------------

def _escape_js(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _normalize_font_family(family: str) -> str:
    """Normalize font family names for Figma compatibility.

    Figma uses "Inter" not "Inter Variable" for the variable font.
    """
    if family == "Inter Variable":
        return "Inter"
    return family


_TITLE_NAMES_RE = r"/^(title|label|heading)$/i"
_SUBTITLE_NAMES_RE = r"/^(subtitle|description|caption)$/i"


def _build_text_finder(
    var: str,
    text_target: str | None,
    subtitle: bool = False,
) -> str:
    """Build a JS expression to find the right TEXT node in a Mode 1 instance.

    When text_target is given, searches by exact name. Otherwise uses a
    name-pattern search (Title/Label/Heading) with fallback to any TEXT.
    For subtitles, searches for Subtitle/Description/Caption names.
    """
    if text_target:
        escaped = _escape_js(text_target)
        return (
            f'{var}.findOne(n => n.type === "TEXT" && n.name === "{escaped}")'
            f' || {var}.findOne(n => n.type === "TEXT")'
        )
    if subtitle:
        return (
            f'{var}.findOne(n => n.type === "TEXT" && {_SUBTITLE_NAMES_RE}.test(n.name))'
            f' || {var}.findAll(n => n.type === "TEXT")[1]'
        )
    return (
        f'{var}.findOne(n => n.type === "TEXT" && {_TITLE_NAMES_RE}.test(n.name))'
        f' || {var}.findOne(n => n.type === "TEXT")'
    )


_DIRECTION_MAP = {"horizontal": "HORIZONTAL", "vertical": "VERTICAL"}

_SIZING_MAP = {"fill": "FILL", "hug": "HUG", "fixed": "FIXED"}

_ALIGNMENT_MAP = {
    "start": "MIN", "center": "CENTER", "end": "MAX",
    "stretch": "STRETCH", "space-between": "SPACE_BETWEEN",
}

# REST API → Plugin API constraint mapping.
# REST uses LEFT/RIGHT/TOP/BOTTOM; Plugin uses MIN/MAX/STRETCH.
_CONSTRAINT_MAP = {
    "LEFT": "MIN", "RIGHT": "MAX", "TOP": "MIN", "BOTTOM": "MAX",
    "CENTER": "CENTER", "SCALE": "SCALE",
    "LEFT_RIGHT": "STRETCH", "TOP_BOTTOM": "STRETCH",
    "MIN": "MIN", "MAX": "MAX", "STRETCH": "STRETCH",
}



# ---------------------------------------------------------------------------
# Composition children (Phase C: slot filling)
# ---------------------------------------------------------------------------

def _emit_composition_children(
    parent_var: str,
    parent_eid: str,
    composition: list[dict[str, Any]],
    lines: list[str],
    var_counter: int,
) -> int:
    """Emit Mode 1 instances or Mode 2 frames for composition children.

    For each child in the composition pattern, creates count_mode
    instances (via getNodeByIdAsync for keyed) or frames (for keyless)
    and appends them to the parent. Returns updated var_counter.

    One level deep only — child instances inherit their own subtree.
    """
    for child_spec in composition:
        count = child_spec.get("count_mode", 1)
        figma_id = child_spec.get("component_figma_id")
        comp_key = child_spec.get("component_key")
        child_type = child_spec.get("child_type", "frame")

        for _ in range(count):
            var = f"_c{var_counter}"
            var_counter += 1

            if figma_id:
                lines.append(
                    f'const {var} = (await figma.getNodeByIdAsync("{_escape_js(figma_id)}")).createInstance();'
                )
            elif comp_key:
                lines.append(
                    f'const {var} = (await figma.importComponentByKeyAsync("{_escape_js(comp_key)}")).createInstance();'
                )
            else:
                lines.append(f"const {var} = figma.createFrame();")

            lines.append(f'{var}.name = "{_escape_js(child_type)}-child";')
            lines.append(f"{parent_var}.appendChild({var});")

    return var_counter


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------

def generate_figma_script(
    spec: dict[str, Any],
    db_visuals: dict[int, dict[str, Any]] | None = None,
    page_name: str | None = None,
) -> tuple[str, list[tuple[str, str, str]]]:
    """Generate a figma_execute script from a CompositionSpec.

    When page_name is provided, creates a new Figma page with that name
    and places the screen there instead of on the current page.

    Returns (js_string, token_refs) where token_refs is a list of
    (element_id, rebind_property, token_name) tuples for Phase B.
    """
    tokens = spec.get("tokens", {})
    elements = spec.get("elements", {})
    root_id = spec.get("root", "")

    fonts = collect_fonts(spec)
    walk_order = _walk_elements(spec)
    all_token_refs: list[tuple[str, str, str]] = []

    lines: list[str] = []

    # Always load Inter Regular — Figma's default font for createText()
    all_fonts = [("Inter", "Regular")] + [f for f in fonts if f != ("Inter", "Regular")]
    for family, style in all_fonts:
        lines.append(f'await figma.loadFontAsync({{family: "{family}", style: "{style}"}});')

    lines.append("const M = {};")

    # Pre-fetch all unique Figma node IDs needed for createInstance/swapComponent.
    # Batching into a single preamble avoids redundant async lookups (50→27 calls
    # on screen 184, more on complex screens with deep component nesting).
    needed_node_ids: set[str] = set()
    for _, element, _ in walk_order:
        if db_visuals is not None:
            nid = spec.get("_node_id_map", {}).get(_[0] if isinstance(_, tuple) else "")
        else:
            nid = None
        # Can't easily pre-scan without duplicating mode1 logic — collect from db_visuals
    if db_visuals is not None:
        for nid, vis in db_visuals.items():
            figma_id = vis.get("component_figma_id")
            if figma_id:
                needed_node_ids.add(figma_id)
            for cs in vis.get("child_swaps", []):
                needed_node_ids.add(cs["swap_target_id"])
            for ov in vis.get("instance_overrides", []):
                if ov.get("type") == "INSTANCE_SWAP" and ov.get("value"):
                    needed_node_ids.add(ov["value"])

    if needed_node_ids:
        lines.append("// Pre-fetch component nodes (deduplicated)")
        node_id_vars: dict[str, str] = {}
        for i, nid in enumerate(sorted(needed_node_ids)):
            var_name = f"_p{i}"
            node_id_vars[nid] = var_name
            lines.append(f'const {var_name} = await figma.getNodeByIdAsync("{_escape_js(nid)}");')
    else:
        node_id_vars = {}

    lines.append("")

    var_map: dict[str, str] = {}
    mode1_eids: set = set()
    skipped_eids: set = set()
    absolute_eids: set = set()

    for idx, (eid, element, parent_eid) in enumerate(walk_order):
        # Skip descendants of Mode 1 elements (they come from the instance)
        if parent_eid in mode1_eids or parent_eid in skipped_eids:
            skipped_eids.add(eid)
            continue

        var = f"n{idx}"
        var_map[eid] = var
        etype = element.get("type", "")
        is_text = etype in _TEXT_TYPES

        # Check for component key (Mode 1)
        component_key = None
        if db_visuals is not None:
            node_id = spec.get("_node_id_map", {}).get(eid)
            raw_visual = db_visuals.get(node_id, {}) if node_id else {}
            component_key = raw_visual.get("component_key")

        component_figma_id = raw_visual.get("component_figma_id") if (db_visuals is not None and raw_visual) else None

        if (component_key or component_figma_id) and not is_text:
            # Mode 1: component instance (inherits structure + visuals)
            if component_figma_id:
                node_expr = node_id_vars.get(component_figma_id, f'await figma.getNodeByIdAsync("{_escape_js(component_figma_id)}")')
                lines.append(
                    f'const {var} = ({node_expr}).createInstance();'
                )
            else:
                lines.append(
                    f'const {var} = (await figma.importComponentByKeyAsync("{_escape_js(component_key)}")).createInstance();'
                )
            original_name = element.get("_original_name", eid)
            lines.append(f'{var}.name = "{_escape_js(original_name)}";')

            props = element.get("props", {})
            text_override = props.get("text", "")
            if text_override:
                text_target = props.get("text_target")
                find_expr = _build_text_finder(var, text_target)
                lines.append(
                    f'{{ const _t = {find_expr}; '
                    f'if (_t) {{ await figma.loadFontAsync(_t.fontName); '
                    f'_t.characters = "{_escape_js(text_override)}"; }} }}'
                )

            subtitle_override = props.get("subtitle", "")
            if subtitle_override:
                sub_find = _build_text_finder(var, None, subtitle=True)
                lines.append(
                    f'{{ const _t = {sub_find}; '
                    f'if (_t) {{ await figma.loadFontAsync(_t.fontName); '
                    f'_t.characters = "{_escape_js(subtitle_override)}"; }} }}'
                )

            hidden_children = raw_visual.get("hidden_children", []) if (db_visuals is not None and raw_visual) else []
            for hc in hidden_children:
                hname = _escape_js(hc["name"])
                lines.append(
                    f'{{ const _h = {var}.findOne(n => n.name === "{hname}"); '
                    f"if (_h) _h.visible = false; }}"
                )

            # Instance overrides: replay child node mutations from DB
            inst_overrides = raw_visual.get("instance_overrides", []) if (db_visuals is not None and raw_visual) else []
            for ov in inst_overrides:
                child_id = _escape_js(ov["child_id"])
                ov_type = ov["type"]
                ov_value = ov.get("value", "")

                if ov_type == "TEXT" and ov_value:
                    # Text override: find child by master-relative ID, set characters
                    lines.append(
                        f'{{ const _c = {var}.findOne(n => n.id.endsWith("{child_id}")); '
                        f'if (_c && _c.type === "TEXT") {{ '
                        f'await figma.loadFontAsync(_c.fontName); '
                        f'_c.characters = "{_escape_js(ov_value)}"; }} }}'
                    )
                elif ov_type == "BOOLEAN":
                    # Visibility override: child_id has ":visible" suffix
                    pure_id = child_id.replace(":visible", "")
                    vis_val = "true" if ov_value == "true" else "false"
                    lines.append(
                        f'{{ const _c = {var}.findOne(n => n.id.endsWith("{pure_id}")); '
                        f"if (_c) _c.visible = {vis_val}; }}"
                    )
                elif ov_type == "INSTANCE_SWAP" and ov_value:
                    # Instance swap: find child, swap its component
                    comp_expr = node_id_vars.get(ov_value, f'await figma.getNodeByIdAsync("{_escape_js(ov_value)}")')
                    lines.append(
                        f'{{ const _c = {var}.findOne(n => n.id.endsWith("{child_id}")); '
                        f'if (_c && _c.type === "INSTANCE") {{ '
                        f"const _comp = {comp_expr}; "
                        f"if (_comp) _c.swapComponent(_comp); }} }}"
                    )

            # Child instance swaps: replace nested instances with correct components
            child_swaps = raw_visual.get("child_swaps", []) if (db_visuals is not None and raw_visual) else []
            for cs in child_swaps:
                cs_child_id = _escape_js(cs["child_id"])
                cs_target_id = cs["swap_target_id"]
                comp_expr = node_id_vars.get(cs_target_id, f'await figma.getNodeByIdAsync("{_escape_js(cs_target_id)}")')
                lines.append(
                    f'{{ const _c = {var}.findOne(n => n.id.endsWith("{cs_child_id}")); '
                    f'if (_c && _c.type === "INSTANCE") {{ '
                    f"const _comp = {comp_expr}; "
                    f"if (_comp) _c.swapComponent(_comp); }} }}"
                )

            position = element.get("layout", {}).get("position")
            if position:
                lines.append(f"{var}.x = {position.get('x', 0)};")
                lines.append(f"{var}.y = {position.get('y', 0)};")

            mode1_eids.add(eid)
        else:
            # Mode 2: create from L0 properties
            if etype in _SKIP_NODE_TYPES:
                skipped_eids.add(eid)
                continue

            if is_text:
                lines.append(f"const {var} = figma.createText();")
            elif etype in _NODE_CREATE_MAP:
                lines.append(f"const {var} = {_NODE_CREATE_MAP[etype]};")
            else:
                lines.append(f"const {var} = figma.createFrame();")

            original_name = element.get("_original_name", eid)
            lines.append(f'{var}.name = "{_escape_js(original_name)}";')

            if is_text:
                lines.append(f'{var}.textAutoResize = "WIDTH_AND_HEIGHT";')

            layout = element.get("layout", {})
            layout_lines, layout_refs = _emit_layout(var, eid, layout, tokens)
            lines.extend(layout_lines)
            all_token_refs.extend(layout_refs)

            if db_visuals is not None:
                node_id = spec.get("_node_id_map", {}).get(eid)
                raw_visual = db_visuals.get(node_id, {}) if node_id else {}
                visual = build_visual_from_db(raw_visual)
            else:
                visual = {}
            visual_lines, visual_refs = _emit_visual(var, eid, visual, tokens)
            lines.extend(visual_lines)
            all_token_refs.extend(visual_refs)

            if element.get("visible") is False:
                lines.append(f"{var}.visible = false;")

            style = element.get("style", {})
            if is_text:
                font_data = visual.get("font") or (raw_visual.get("font") if db_visuals is not None else None)
                if font_data:
                    style = dict(style)
                    _FONT_KEY_MAP = {
                        "font_family": "fontFamily",
                        "font_size": "fontSize",
                        "font_weight": "fontWeight",
                    }
                    for db_key, style_key in _FONT_KEY_MAP.items():
                        if db_key in font_data and style_key not in style:
                            style[style_key] = font_data[db_key]
                _emit_text_props(var, element, style, tokens, lines)

            composition = element.get("_composition")
            has_ir_children = bool(element.get("children"))
            if composition and not is_text and not has_ir_children:
                _emit_composition_children(var, eid, composition, lines, idx * 100)

            elem_direction = element.get("layout", {}).get("direction", "")
            if elem_direction == "absolute":
                absolute_eids.add(eid)

        if parent_eid is not None and parent_eid in var_map and parent_eid not in mode1_eids:
            parent_var = var_map[parent_eid]
            lines.append(f"{parent_var}.appendChild({var});")
            parent_direction = spec.get("elements", {}).get(parent_eid, {}).get("layout", {}).get("direction", "")
            parent_is_autolayout = parent_direction in ("horizontal", "vertical")
            if parent_is_autolayout:
                elem_sizing = element.get("layout", {}).get("sizing", {})
                wants_fill = elem_sizing.get("width") == "fill"
                if is_text and eid not in mode1_eids:
                    lines.append(f'{var}.layoutSizingHorizontal = "FILL";')
                elif etype in _FILL_WIDTH_TYPES or wants_fill:
                    lines.append(f'{var}.layoutSizingHorizontal = "FILL";')

        lines.append(f'M["{_escape_js(eid)}"] = {var}.id;')
        lines.append("")

    if root_id in var_map:
        if page_name:
            escaped_name = _escape_js(page_name)
            lines.append(
                f'let _page = figma.root.children.find(p => p.type === "PAGE" && p.name === "{escaped_name}");'
            )
            lines.append(f"if (!_page) {{ _page = figma.createPage(); _page.name = \"{escaped_name}\"; }}")
            lines.append(f"_page.appendChild({var_map[root_id]});")
            lines.append(f"await figma.setCurrentPageAsync(_page);")
        else:
            lines.append(f"figma.currentPage.appendChild({var_map[root_id]});")

    lines.append("return M;")

    return ("\n".join(lines), all_token_refs)


def _walk_elements(spec: dict[str, Any]) -> list[tuple[str, dict, str | None]]:
    """BFS walk from root, returning (element_id, element, parent_id) tuples."""
    elements = spec.get("elements", {})
    root_id = spec.get("root", "")

    if root_id not in elements:
        return []

    result = []
    queue = [(root_id, None)]

    while queue:
        eid, parent_eid = queue.pop(0)
        element = elements.get(eid)
        if element is None:
            continue
        result.append((eid, element, parent_eid))
        for child_id in element.get("children", []):
            queue.append((child_id, eid))

    return result


def _emit_layout(
    var: str, eid: str, layout: dict[str, Any], tokens: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    lines: list[str] = []
    refs: list[tuple[str, str, str]] = []

    direction = layout.get("direction", "")
    figma_dir = _DIRECTION_MAP.get(direction)
    if figma_dir:
        lines.append(f'{var}.layoutMode = "{figma_dir}";')

    gap_val = layout.get("gap")
    if gap_val is not None:
        resolved, token_name = resolve_style_value(gap_val, tokens)
        if resolved is not None:
            lines.append(f"{var}.itemSpacing = {resolved};")
        if token_name:
            refs.append((eid, "itemSpacing", token_name))

    padding = layout.get("padding", {})
    for side in ("top", "right", "bottom", "left"):
        val = padding.get(side)
        if val is not None:
            resolved, token_name = resolve_style_value(val, tokens)
            figma_prop = f"padding{side.capitalize()}"
            if resolved is not None:
                lines.append(f"{var}.{figma_prop} = {resolved};")
            if token_name:
                refs.append((eid, f"padding.{side}", token_name))

    sizing = layout.get("sizing", {})
    has_auto_layout = direction in ("horizontal", "vertical")
    for axis, figma_axis in [("width", "Horizontal"), ("height", "Vertical")]:
        val = sizing.get(axis)
        if val is None:
            continue
        if isinstance(val, str):
            mapped = _SIZING_MAP.get(val)
            # FILL requires parent auto-layout — defer to post-appendChild
            if mapped and mapped != "FILL":
                lines.append(f'{var}.layoutSizing{figma_axis} = "{mapped}";')
        elif isinstance(val, (int, float)) and has_auto_layout:
            lines.append(f'{var}.layoutSizing{figma_axis} = "FIXED";')

    w = sizing.get("width")
    h = sizing.get("height")
    rw = int(w) if isinstance(w, (int, float)) else sizing.get("widthPixels")
    rh = int(h) if isinstance(h, (int, float)) else sizing.get("heightPixels")
    if rw is not None:
        rw = int(rw)
    if rh is not None:
        rh = int(rh)
    if rw is not None or rh is not None:
        lines.append(f"{var}.resize({rw or 1}, {rh or 1});")

    main_align = layout.get("mainAxisAlignment")
    if main_align:
        mapped = _ALIGNMENT_MAP.get(main_align, main_align.upper())
        lines.append(f'{var}.primaryAxisAlignItems = "{mapped}";')

    cross_align = layout.get("crossAxisAlignment")
    if cross_align:
        mapped = _ALIGNMENT_MAP.get(cross_align, cross_align.upper())
        lines.append(f'{var}.counterAxisAlignItems = "{mapped}";')

    position = layout.get("position")
    if position:
        px = position.get("x", 0)
        py = position.get("y", 0)
        lines.append(f"{var}.x = {px};")
        lines.append(f"{var}.y = {py};")

    return (lines, refs)


def _emit_visual(
    var: str, eid: str, visual: dict[str, Any], tokens: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit Figma JS for visual properties (fills, strokes, effects, radius, opacity)."""
    lines: list[str] = []
    refs: list[tuple[str, str, str]] = []

    fills = visual.get("fills", [])
    if fills:
        fill_lines, fill_refs = _emit_fills(var, eid, fills, tokens)
        lines.extend(fill_lines)
        refs.extend(fill_refs)

    strokes = visual.get("strokes", [])
    if strokes:
        stroke_lines, stroke_refs = _emit_strokes(var, eid, strokes, tokens)
        lines.extend(stroke_lines)
        refs.extend(stroke_refs)

    effects = visual.get("effects", [])
    if effects:
        effect_lines, effect_refs = _emit_effects(var, eid, effects, tokens)
        lines.extend(effect_lines)
        refs.extend(effect_refs)

    radius = visual.get("cornerRadius")
    if radius is not None:
        if isinstance(radius, (int, float)):
            lines.append(f"{var}.cornerRadius = {int(radius)};")

    opacity = visual.get("opacity")
    if opacity is not None:
        lines.append(f"{var}.opacity = {opacity};")

    if visual.get("clipsContent"):
        lines.append(f"{var}.clipsContent = true;")

    rotation = visual.get("rotation")
    if rotation is not None:
        lines.append(f"{var}.rotation = {rotation};")

    constraints = visual.get("constraints")
    if constraints:
        parts = []
        if "horizontal" in constraints:
            mapped = _CONSTRAINT_MAP.get(constraints["horizontal"], constraints["horizontal"])
            parts.append(f'horizontal: "{mapped}"')
        if "vertical" in constraints:
            mapped = _CONSTRAINT_MAP.get(constraints["vertical"], constraints["vertical"])
            parts.append(f'vertical: "{mapped}"')
        lines.append(f"{var}.constraints = {{{', '.join(parts)}}};")

    return (lines, refs)


def _emit_fills(
    var: str, eid: str, fills: list[dict[str, Any]], tokens: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit Figma fills array from IR normalized fills."""
    paints: list[str] = []
    refs: list[tuple[str, str, str]] = []

    for i, fill in enumerate(fills):
        fill_type = fill.get("type", "")

        if fill_type == "solid":
            color_val = fill.get("color", "")
            resolved, token_name = resolve_style_value(color_val, tokens)
            if resolved and isinstance(resolved, str) and resolved.startswith("#"):
                rgb = hex_to_figma_rgb(resolved)
                paint = f'{{type: "SOLID", color: {{r:{rgb["r"]},g:{rgb["g"]},b:{rgb["b"]}}}}}'
                opacity = fill.get("opacity")
                if opacity is not None and opacity < 1.0:
                    paint = f'{{type: "SOLID", color: {{r:{rgb["r"]},g:{rgb["g"]},b:{rgb["b"]}}}, opacity: {opacity}}}'
                paints.append(paint)
            if token_name:
                refs.append((eid, f"fill.{i}.color", token_name))

    if paints:
        paints_str = ", ".join(paints)
        return ([f"{var}.fills = [{paints_str}];"], refs)

    return ([], refs)


def _emit_strokes(
    var: str, eid: str, strokes: list[dict[str, Any]], tokens: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit Figma strokes array from IR normalized strokes."""
    paints: list[str] = []
    refs: list[tuple[str, str, str]] = []

    for i, stroke in enumerate(strokes):
        if stroke.get("type") != "solid":
            continue
        color_val = stroke.get("color", "")
        resolved, token_name = resolve_style_value(color_val, tokens)
        if resolved and isinstance(resolved, str) and resolved.startswith("#"):
            rgb = hex_to_figma_rgb(resolved)
            paints.append(f'{{type: "SOLID", color: {{r:{rgb["r"]},g:{rgb["g"]},b:{rgb["b"]}}}}}')
        if token_name:
            refs.append((eid, f"stroke.{i}.color", token_name))

    lines: list[str] = []
    if paints:
        lines.append(f'{var}.strokes = [{", ".join(paints)}];')
    width = strokes[0].get("width") if strokes else None
    if width is not None:
        lines.append(f"{var}.strokeWeight = {width};")

    return (lines, refs)


def _emit_effects(
    var: str, eid: str, effects: list[dict[str, Any]], tokens: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit Figma effects array from IR normalized effects."""
    effect_objs: list[str] = []
    refs: list[tuple[str, str, str]] = []

    for i, effect in enumerate(effects):
        effect_type = effect.get("type", "")

        if effect_type in ("drop-shadow", "inner-shadow"):
            color_val = effect.get("color", "")
            resolved, token_name = resolve_style_value(color_val, tokens)
            offset = effect.get("offset", {"x": 0, "y": 0})
            blur = effect.get("blur", 0)
            spread = effect.get("spread", 0)
            figma_type = "DROP_SHADOW" if effect_type == "drop-shadow" else "INNER_SHADOW"

            if resolved and isinstance(resolved, str) and resolved.startswith("#"):
                rgb = hex_to_figma_rgb(resolved)
                effect_objs.append(
                    f'{{type: "{figma_type}", visible: true, blendMode: "NORMAL", '
                    f'color: {{r:{rgb["r"]},g:{rgb["g"]},b:{rgb["b"]},a:1}}, '
                    f'offset: {{x:{offset["x"]},y:{offset["y"]}}}, '
                    f'radius: {blur}, spread: {spread}}}'
                )
            if token_name:
                refs.append((eid, f"effect.{i}.color", token_name))

        elif effect_type in ("layer-blur", "background-blur"):
            radius = effect.get("radius", 0)
            figma_type = "LAYER_BLUR" if effect_type == "layer-blur" else "BACKGROUND_BLUR"
            effect_objs.append(f'{{type: "{figma_type}", visible: true, radius: {radius}}}')

    lines: list[str] = []
    if effect_objs:
        lines.append(f'{var}.effects = [{", ".join(effect_objs)}];')

    return (lines, refs)


def _emit_text_props(
    var: str, element: dict[str, Any], style: dict[str, Any],
    tokens: dict[str, Any], lines: list[str],
) -> None:
    family = style.get("fontFamily", "Inter")
    if isinstance(family, str) and family.startswith("{"):
        resolved, _ = resolve_style_value(family, tokens)
        family = resolved if resolved and isinstance(resolved, str) else "Inter"
    family = _normalize_font_family(family)
    weight = style.get("fontWeight")
    if isinstance(weight, str) and weight.startswith("{"):
        resolved, _ = resolve_style_value(weight, tokens)
        weight = resolved
    figma_style = font_weight_to_style(weight)
    lines.append(f'{var}.fontName = {{family: "{family}", style: "{figma_style}"}};')

    font_size = style.get("fontSize")
    if font_size is not None:
        if isinstance(font_size, str) and font_size.startswith("{"):
            pass  # token ref, skip direct set
        else:
            lines.append(f"{var}.fontSize = {font_size};")

    text = element.get("props", {}).get("text", "")
    if text:
        lines.append(f'{var}.characters = "{_escape_js(text)}";')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_screen(conn: sqlite3.Connection, screen_id: int) -> dict[str, Any]:
    """Generate a Figma creation manifest for a classified screen.

    Returns dict with:
      structure_script: JS string for figma_execute (Phase A)
      token_refs: list of (element_id, property, token_name) for rebinding
      element_count: number of elements in the spec
    """
    from dd.ir import generate_ir, query_screen_visuals

    ir_result = generate_ir(conn, screen_id)
    spec = ir_result["spec"]
    visuals = query_screen_visuals(conn, screen_id)

    script, token_refs = generate_figma_script(spec, db_visuals=visuals)

    return {
        "structure_script": script,
        "token_refs": token_refs,
        "element_count": ir_result["element_count"],
        "token_count": ir_result["token_count"],
    }
