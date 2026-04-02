"""Figma generation from CompositionSpec IR (T5 Phase 3).

Takes a CompositionSpec JSON and produces:
  Phase A: A figma_execute script that creates frames/text with auto-layout
  Phase B: Rebind scripts that bind Figma variables to created nodes

Visual data sources:
  - IR path (current): reads element["visual"] from the spec
  - DB path (Phase 1): reads raw visual data from query_screen_visuals(),
    normalizes it, and feeds it to the same _emit_visual pipeline
"""

import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from dd.ir import normalize_fills, normalize_strokes, normalize_effects, normalize_corner_radius


# Text element types that use figma.createText()
_TEXT_TYPES = frozenset({"text", "heading", "link"})

_TOKEN_REF_RE = re.compile(r"^\{(.+)\}$")

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

def hex_to_figma_rgb(hex_str: str) -> Dict[str, float]:
    """Convert hex color string to Figma RGB dict {r, g, b} (0.0-1.0).

    Handles 6-digit (#FF0000) and 8-digit (#FF000080) hex. Alpha is dropped.
    """
    h = hex_str.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return {"r": round(r, 4), "g": round(g, 4), "b": round(b, 4)}


def resolve_style_value(
    value: Any, tokens: Dict[str, Any],
) -> Tuple[Any, Optional[str]]:
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


def collect_fonts(spec: Dict[str, Any]) -> List[Tuple[str, str]]:
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

def build_visual_from_db(node_visual: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize raw DB visual data to the format _emit_visual expects.

    Takes a dict from query_screen_visuals() (raw Figma JSON strings +
    scalar columns + bindings list) and produces the same normalized
    visual dict that the IR's _build_visual() produces.
    """
    bindings = node_visual.get("bindings", [])
    visual: Dict[str, Any] = {}

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


_DIRECTION_MAP = {"horizontal": "HORIZONTAL", "vertical": "VERTICAL"}

_SIZING_MAP = {"fill": "FILL", "hug": "HUG", "fixed": "FIXED"}

_ALIGNMENT_MAP = {
    "start": "MIN", "center": "CENTER", "end": "MAX",
    "stretch": "STRETCH", "space-between": "SPACE_BETWEEN",
}



# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------

def generate_figma_script(
    spec: Dict[str, Any],
    db_visuals: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Tuple[str, List[Tuple[str, str, str]]]:
    """Generate a figma_execute script from a CompositionSpec.

    Returns (js_string, token_refs) where token_refs is a list of
    (element_id, rebind_property, token_name) tuples for Phase B.
    """
    tokens = spec.get("tokens", {})
    elements = spec.get("elements", {})
    root_id = spec.get("root", "")

    fonts = collect_fonts(spec)
    walk_order = _walk_elements(spec)
    all_token_refs: List[Tuple[str, str, str]] = []

    lines: List[str] = []

    # Always load Inter Regular — Figma's default font for createText()
    all_fonts = [("Inter", "Regular")] + [f for f in fonts if f != ("Inter", "Regular")]
    for family, style in all_fonts:
        lines.append(f'await figma.loadFontAsync({{family: "{family}", style: "{style}"}});')

    lines.append("const M = {};")
    lines.append("")

    var_map: Dict[str, str] = {}

    for idx, (eid, element, parent_eid) in enumerate(walk_order):
        var = f"n{idx}"
        var_map[eid] = var
        etype = element.get("type", "")
        is_text = etype in _TEXT_TYPES

        if is_text:
            lines.append(f"const {var} = figma.createText();")
        else:
            lines.append(f"const {var} = figma.createFrame();")

        lines.append(f'{var}.name = "{_escape_js(eid)}";')

        layout = element.get("layout", {})
        layout_lines, layout_refs = _emit_layout(var, eid, layout, tokens)
        lines.extend(layout_lines)
        all_token_refs.extend(layout_refs)

        if db_visuals is not None:
            node_id = spec.get("_node_id_map", {}).get(eid)
            raw_visual = db_visuals.get(node_id, {}) if node_id else {}
            visual = build_visual_from_db(raw_visual)
        else:
            visual = element.get("visual", {})
        visual_lines, visual_refs = _emit_visual(var, eid, visual, tokens)
        lines.extend(visual_lines)
        all_token_refs.extend(visual_refs)

        style = element.get("style", {})
        if is_text:
            _emit_text_props(var, element, style, tokens, lines)

        if parent_eid is not None and parent_eid in var_map:
            parent_var = var_map[parent_eid]
            lines.append(f"{parent_var}.appendChild({var});")

        lines.append(f'M["{_escape_js(eid)}"] = {var}.id;')
        lines.append("")

    if root_id in var_map:
        lines.append(f"figma.currentPage.appendChild({var_map[root_id]});")

    lines.append("return M;")

    return ("\n".join(lines), all_token_refs)


def _walk_elements(spec: Dict[str, Any]) -> List[Tuple[str, Dict, Optional[str]]]:
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
    var: str, eid: str, layout: Dict[str, Any], tokens: Dict[str, Any],
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    lines: List[str] = []
    refs: List[Tuple[str, str, str]] = []

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
            if mapped:
                lines.append(f'{var}.layoutSizing{figma_axis} = "{mapped}";')
        elif isinstance(val, (int, float)) and has_auto_layout:
            lines.append(f'{var}.layoutSizing{figma_axis} = "FIXED";')

    w = sizing.get("width")
    h = sizing.get("height")
    rw = int(w) if isinstance(w, (int, float)) else None
    rh = int(h) if isinstance(h, (int, float)) else None
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

    return (lines, refs)


def _emit_visual(
    var: str, eid: str, visual: Dict[str, Any], tokens: Dict[str, Any],
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    """Emit Figma JS for visual properties (fills, strokes, effects, radius, opacity)."""
    lines: List[str] = []
    refs: List[Tuple[str, str, str]] = []

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

    return (lines, refs)


def _emit_fills(
    var: str, eid: str, fills: List[Dict[str, Any]], tokens: Dict[str, Any],
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    """Emit Figma fills array from IR normalized fills."""
    paints: List[str] = []
    refs: List[Tuple[str, str, str]] = []

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
    var: str, eid: str, strokes: List[Dict[str, Any]], tokens: Dict[str, Any],
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    """Emit Figma strokes array from IR normalized strokes."""
    paints: List[str] = []
    refs: List[Tuple[str, str, str]] = []

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

    lines: List[str] = []
    if paints:
        lines.append(f'{var}.strokes = [{", ".join(paints)}];')
    width = strokes[0].get("width") if strokes else None
    if width is not None:
        lines.append(f"{var}.strokeWeight = {width};")

    return (lines, refs)


def _emit_effects(
    var: str, eid: str, effects: List[Dict[str, Any]], tokens: Dict[str, Any],
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    """Emit Figma effects array from IR normalized effects."""
    effect_objs: List[str] = []
    refs: List[Tuple[str, str, str]] = []

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

    lines: List[str] = []
    if effect_objs:
        lines.append(f'{var}.effects = [{", ".join(effect_objs)}];')

    return (lines, refs)


def _emit_text_props(
    var: str, element: Dict[str, Any], style: Dict[str, Any],
    tokens: Dict[str, Any], lines: List[str],
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

def generate_screen(conn: sqlite3.Connection, screen_id: int) -> Dict[str, Any]:
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
