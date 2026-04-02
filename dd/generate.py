"""Figma generation from CompositionSpec IR (T5 Phase 3).

Takes a CompositionSpec JSON and produces:
  Phase A: A figma_execute script that creates frames/text with auto-layout
  Phase B: Rebind scripts that bind Figma variables to created nodes
"""

import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


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
    """
    if weight is None:
        return "Regular"
    if isinstance(weight, str):
        return weight
    return _WEIGHT_TO_STYLE.get(int(weight), "Regular")


def collect_fonts(spec: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Collect unique (family, style) pairs from text elements in the spec."""
    seen = set()
    result = []

    for element in spec.get("elements", {}).values():
        etype = element.get("type", "")
        if etype not in _TEXT_TYPES:
            continue

        style = element.get("style", {})
        family = style.get("fontFamily", "Inter")
        weight = style.get("fontWeight")

        if isinstance(family, str) and family.startswith("{"):
            family = "Inter"

        figma_style = font_weight_to_style(weight)
        key = (family, figma_style)
        if key not in seen:
            seen.add(key)
            result.append(key)

    return result


# ---------------------------------------------------------------------------
# JS helpers
# ---------------------------------------------------------------------------

def _escape_js(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


_DIRECTION_MAP = {"horizontal": "HORIZONTAL", "vertical": "VERTICAL"}

_SIZING_MAP = {"fill": "FILL", "hug": "HUG", "fixed": "FIXED"}

_ALIGNMENT_MAP = {
    "start": "MIN", "center": "CENTER", "end": "MAX",
    "stretch": "STRETCH", "space-between": "SPACE_BETWEEN",
}

_IR_STYLE_TO_REBIND = {
    "backgroundColor": "fill.0.color",
    "borderColor": "stroke.0.color",
    "borderRadius": "cornerRadius",
    "opacity": "opacity",
    "fontSize": "fontSize",
    "fontFamily": "fontFamily",
    "fontWeight": "fontWeight",
    "lineHeight": "lineHeight",
    "letterSpacing": "letterSpacing",
}

_IR_LAYOUT_TO_REBIND = {
    "gap": "itemSpacing",
    "padding.top": "padding.top",
    "padding.right": "padding.right",
    "padding.bottom": "padding.bottom",
    "padding.left": "padding.left",
}


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------

def generate_figma_script(
    spec: Dict[str, Any],
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
    lines.append("(async () => {")

    for family, style in fonts:
        lines.append(f'  await figma.loadFontAsync({{family: "{family}", style: "{style}"}});')

    lines.append("  const M = {};")
    lines.append("")

    var_map: Dict[str, str] = {}

    for idx, (eid, element, parent_eid) in enumerate(walk_order):
        var = f"n{idx}"
        var_map[eid] = var
        etype = element.get("type", "")
        is_text = etype in _TEXT_TYPES

        if is_text:
            lines.append(f"  const {var} = figma.createText();")
        else:
            lines.append(f"  const {var} = figma.createFrame();")

        lines.append(f'  {var}.name = "{_escape_js(eid)}";')

        layout = element.get("layout", {})
        layout_lines, layout_refs = _emit_layout(var, eid, layout, tokens)
        lines.extend(layout_lines)
        all_token_refs.extend(layout_refs)

        style = element.get("style", {})
        style_lines, style_refs = _emit_style(var, eid, style, tokens, is_text)
        lines.extend(style_lines)
        all_token_refs.extend(style_refs)

        if is_text:
            _emit_text_props(var, element, style, lines)

        if parent_eid is not None and parent_eid in var_map:
            parent_var = var_map[parent_eid]
            lines.append(f"  {parent_var}.appendChild({var});")

        lines.append(f'  M["{_escape_js(eid)}"] = {var}.id;')
        lines.append("")

    if root_id in var_map:
        lines.append(f"  figma.currentPage.appendChild({var_map[root_id]});")

    lines.append("  return M;")
    lines.append("})();")

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
        lines.append(f'  {var}.layoutMode = "{figma_dir}";')

    gap_val = layout.get("gap")
    if gap_val is not None:
        resolved, token_name = resolve_style_value(gap_val, tokens)
        if resolved is not None:
            lines.append(f"  {var}.itemSpacing = {resolved};")
        if token_name:
            refs.append((eid, "itemSpacing", token_name))

    padding = layout.get("padding", {})
    for side in ("top", "right", "bottom", "left"):
        val = padding.get(side)
        if val is not None:
            resolved, token_name = resolve_style_value(val, tokens)
            figma_prop = f"padding{side.capitalize()}"
            if resolved is not None:
                lines.append(f"  {var}.{figma_prop} = {resolved};")
            if token_name:
                refs.append((eid, f"padding.{side}", token_name))

    sizing = layout.get("sizing", {})
    for axis, figma_axis in [("width", "Horizontal"), ("height", "Vertical")]:
        val = sizing.get(axis)
        if val is None:
            continue
        if isinstance(val, str):
            mapped = _SIZING_MAP.get(val)
            if mapped:
                lines.append(f'  {var}.layoutSizing{figma_axis} = "{mapped}";')
        elif isinstance(val, (int, float)):
            pass  # handled by resize below

    w = sizing.get("width")
    h = sizing.get("height")
    if isinstance(w, (int, float)) and isinstance(h, (int, float)):
        lines.append(f"  {var}.resize({int(w)}, {int(h)});")

    main_align = layout.get("mainAxisAlignment")
    if main_align:
        mapped = _ALIGNMENT_MAP.get(main_align, main_align.upper())
        lines.append(f'  {var}.primaryAxisAlignItems = "{mapped}";')

    cross_align = layout.get("crossAxisAlignment")
    if cross_align:
        mapped = _ALIGNMENT_MAP.get(cross_align, cross_align.upper())
        lines.append(f'  {var}.counterAxisAlignItems = "{mapped}";')

    return (lines, refs)


def _emit_style(
    var: str, eid: str, style: Dict[str, Any], tokens: Dict[str, Any], is_text: bool,
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    lines: List[str] = []
    refs: List[Tuple[str, str, str]] = []

    bg = style.get("backgroundColor")
    if bg is not None:
        resolved, token_name = resolve_style_value(bg, tokens)
        if resolved and isinstance(resolved, str) and resolved.startswith("#"):
            rgb = hex_to_figma_rgb(resolved)
            lines.append(f'  {var}.fills = [{{type: "SOLID", color: {{r:{rgb["r"]},g:{rgb["g"]},b:{rgb["b"]}}}}}];')
        if token_name:
            refs.append((eid, "fill.0.color", token_name))

    radius = style.get("borderRadius")
    if radius is not None:
        resolved, token_name = resolve_style_value(radius, tokens)
        if resolved is not None:
            lines.append(f"  {var}.cornerRadius = {resolved};")
        if token_name:
            refs.append((eid, "cornerRadius", token_name))

    opacity = style.get("opacity")
    if opacity is not None:
        resolved, token_name = resolve_style_value(opacity, tokens)
        if resolved is not None:
            lines.append(f"  {var}.opacity = {resolved};")
        if token_name:
            refs.append((eid, "opacity", token_name))

    return (lines, refs)


def _emit_text_props(
    var: str, element: Dict[str, Any], style: Dict[str, Any], lines: List[str],
) -> None:
    family = style.get("fontFamily", "Inter")
    if isinstance(family, str) and family.startswith("{"):
        family = "Inter"
    weight = style.get("fontWeight")
    figma_style = font_weight_to_style(weight)
    lines.append(f'  {var}.fontName = {{family: "{family}", style: "{figma_style}"}};')

    font_size = style.get("fontSize")
    if font_size is not None:
        if isinstance(font_size, str) and font_size.startswith("{"):
            pass  # token ref, skip direct set
        else:
            lines.append(f"  {var}.fontSize = {font_size};")

    text = element.get("props", {}).get("text", "")
    if text:
        lines.append(f'  {var}.characters = "{_escape_js(text)}";')


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
    from dd.ir import generate_ir

    ir_result = generate_ir(conn, screen_id)
    spec = ir_result["spec"]

    script, token_refs = generate_figma_script(spec)

    return {
        "structure_script": script,
        "token_refs": token_refs,
        "element_count": ir_result["element_count"],
        "token_count": ir_result["token_count"],
    }
