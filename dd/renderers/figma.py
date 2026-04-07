"""Figma Plugin API renderer.

Generates Figma Plugin API JavaScript from CompositionSpec + DB visuals.
Platform-specific: all value transforms, JS emission, font handling,
and color conversion for the Figma Plugin API live here.

Shared infrastructure (renderer-agnostic) lives in dd.visual:
  build_visual_from_db, resolve_style_value, _resolve_layout_sizing

See docs/cross-platform-value-formats.md for how this renderer's
transforms compare to other platforms (React, SwiftUI, Flutter).
"""

import json
import math
import re
import sqlite3
from typing import Any

from dd.visual import (
    build_visual_from_db,
    resolve_style_value,
    _resolve_layout_sizing,
)


# Text element types that use figma.createText()
_TEXT_TYPES = frozenset({"text", "heading", "link"})

# Container types that should fill parent width in vertical auto-layout.
# These are full-width components that span the screen in real designs.

# Node type → Figma creation call for non-FRAME types
_NODE_CREATE_MAP = {
    "rectangle": "figma.createRectangle()",
    "ellipse": "figma.createEllipse()",
    "line": "figma.createLine()",
}

# Node types that cannot be created in Figma — skip silently (unless asset-backed)
_SKIP_NODE_TYPES = frozenset({"vector", "boolean_operation", "group"})

# Vector-capable node types that can be rendered when they have asset data
_VECTOR_TYPES = frozenset({"vector", "boolean_operation"})

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
# Figma renderer — platform-specific value transforms
# ---------------------------------------------------------------------------
# These functions convert from the renderer-agnostic visual dict format
# to Figma Plugin API native format. Other renderers (React, SwiftUI,
# Flutter) would have their own format_{lang}_value, color converters,
# font mappers, etc. See docs/cross-platform-value-formats.md.
#
# Figma-specific transforms:
#   hex_to_figma_rgba     — hex string → {r,g,b,a} floats
#   font_weight_to_style  — numeric 600 → "Semi Bold"
#   normalize_font_style  — per-family Figma style naming
#   _normalize_font_family — "Inter Variable" → "Inter"
#   collect_fonts         — Figma loadFontAsync preamble
#   format_js_value       — Python → JS literal (radians → degrees here)
#   _CONSTRAINT_MAP       — REST API → Plugin API constraint names
#   _ALIGNMENT_MAP        — semantic → Figma enum
#   _SIZING_MAP           — semantic → Figma enum
# ---------------------------------------------------------------------------

def hex_to_figma_rgba(hex_str: str) -> dict[str, float]:
    """Convert hex color string to Figma RGBA dict {r, g, b, a} (0.0-1.0).

    Handles 6-digit (#FF0000 → a=1.0) and 8-digit (#FF000080 → a from last 2 digits).
    """
    h = hex_str.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    a = int(h[6:8], 16) / 255.0 if len(h) >= 8 else 1.0
    return {"r": round(r, 4), "g": round(g, 4), "b": round(b, 4), "a": round(a, 4)}



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


# Font families where "Semi Bold" should be "Semibold" (no space)
_SEMIBOLD_NO_SPACE = frozenset({"SF Pro", "SF Pro Text", "SF Pro Display"})

# Font families where "Semi Bold" should be "SemiBold" (camelCase)
_SEMIBOLD_CAMEL = frozenset({"Baskerville"})


def normalize_font_style(family: str, style: str) -> str:
    """Normalize font style name for a specific font family.

    Different font families use different naming for the same weight:
    - Inter: "Semi Bold" (space)
    - SF Pro Text/Display/Pro: "Semibold" (no space)
    - Baskerville: "SemiBold" (camelCase)
    """
    if "Semi Bold" not in style:
        return style
    if family in _SEMIBOLD_NO_SPACE:
        return style.replace("Semi Bold", "Semibold")
    if family in _SEMIBOLD_CAMEL:
        return style.replace("Semi Bold", "SemiBold")
    return style


def collect_fonts(
    spec: dict[str, Any],
    db_visuals: dict[int, dict[str, Any]] | None = None,
) -> list[tuple[str, str]]:
    """Collect unique (family, style) pairs for Figma Plugin API font loading.

    Figma-renderer-specific: applies font family normalization ("Inter Variable"
    → "Inter") and weight→style conversion (600 → "Semi Bold"). Other renderers
    use different font formats (CSS: numeric weight, SwiftUI: enum).

    Reads from IR style (L2) with DB font data (L0) fallback.
    Incorporates font_style (Italic/Oblique) from DB when present.
    """
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []

    tokens = spec.get("tokens", {})
    node_id_map = spec.get("_node_id_map", {})

    for eid, element in spec.get("elements", {}).items():
        etype = element.get("type", "")
        if etype not in _TEXT_TYPES:
            continue

        style = element.get("style", {})
        family = style.get("fontFamily", "Inter")
        weight = style.get("fontWeight")

        if isinstance(family, str) and family.startswith("{"):
            resolved_family, _ = resolve_style_value(family, tokens)
            family = resolved_family if resolved_family and isinstance(resolved_family, str) else "Inter"

        # DB fallback for family and weight
        db_font_style = None
        if db_visuals is not None:
            nid = node_id_map.get(eid)
            if nid:
                nv = db_visuals.get(nid, {})
                font = nv.get("font") or nv
                if not family or family == "Inter":
                    db_fam = font.get("font_family")
                    if db_fam:
                        family = db_fam
                if weight is None:
                    weight = font.get("font_weight")
                db_font_style = font.get("font_style")

        family = _normalize_font_family(family)

        if isinstance(weight, str) and weight.startswith("{"):
            resolved_weight, _ = resolve_style_value(weight, tokens)
            weight = resolved_weight

        figma_style = normalize_font_style(family, font_weight_to_style(weight))

        if db_font_style and db_font_style != "Regular":
            if "Italic" not in figma_style and "Oblique" not in figma_style:
                figma_style = f"{figma_style} {db_font_style}"

        key = (family, figma_style)
        if key not in seen:
            seen.add(key)
            result.append(key)

    return result


# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Override grouping helpers
# ---------------------------------------------------------------------------

def _emit_override_op(
    ov: dict[str, Any],
    target_var: str,
    node_id_vars: dict[str, str],
    parent_var: str,
    deferred_lines: list[str],
) -> str:
    """Emit JS for a single override operation on target_var.

    Overrides use decomposed format: {target, property, value}.
    Most properties use registry-driven format_js_value. Special cases:
    - characters: needs font loading
    - instance_swap: needs swapComponent
    - width/height: needs resize() with both dimensions
    - layoutSizing on :self: must be deferred
    """
    prop_name = ov["property"]
    value = ov.get("value", "")
    is_self = (target_var == parent_var)

    if not value:
        return ""

    if prop_name == "characters":
        return (
            f'if ({target_var}.type === "TEXT") {{ '
            f'await figma.loadFontAsync({target_var}.fontName); '
            f'{target_var}.characters = "{_escape_js(value)}"; }}'
        )
    if prop_name == "instance_swap":
        comp_expr = node_id_vars.get(value, f'await figma.getNodeByIdAsync("{_escape_js(value)}")')
        return (
            f'if ({target_var}.type === "INSTANCE") {{ '
            f"const _comp = {comp_expr}; "
            f"if (_comp) {target_var}.swapComponent(_comp); }}"
        )
    if prop_name == "width":
        h_ref = f"{parent_var}.height" if is_self else f"{target_var}.height"
        return f"{target_var}.resize({value}, {h_ref});"
    if prop_name == "height":
        w_ref = f"{parent_var}.width" if is_self else f"{target_var}.width"
        return f"{target_var}.resize({w_ref}, {value});"
    if prop_name in ("layoutSizingHorizontal", "layoutSizingVertical") and is_self:
        deferred_lines.append(f'{target_var}.{prop_name} = {format_js_value(value, "enum")};')
        return ""

    from dd.property_registry import by_figma_name
    prop = by_figma_name(prop_name)
    if prop:
        formatted = format_js_value(value, prop.value_type)
        return f"{target_var}.{prop.figma_name} = {formatted};"
    return ""


def _collect_swap_targets_from_tree(
    node: dict[str, Any] | None,
    targets: set[str],
) -> None:
    """Walk override tree and collect all swap target IDs for pre-fetching."""
    if node is None:
        return
    swap = node.get("swap")
    if swap:
        targets.add(swap)
    for child in node.get("children", []):
        _collect_swap_targets_from_tree(child, targets)


def _emit_override_tree(
    node: dict[str, Any],
    instance_var: str,
    node_id_vars: dict[str, str],
    lines: list[str],
    deferred_lines: list[str],
) -> None:
    """Walk override tree in pre-order, emitting JS mutations.

    Pre-order traversal ensures swaps happen before property overrides
    on descendants of the swapped subtree. At each tree node:
    1. Emit swap (if any) — creates the new subtree
    2. Emit property overrides — modifies the (possibly swapped) node
    3. Recurse into children — deeper overrides after parent mutations
    """
    target = node["target"]
    swap = node.get("swap")
    properties = node.get("properties", [])

    if target == ":self":
        # Self swap
        if swap:
            ov = {"property": "instance_swap", "value": swap}
            op = _emit_override_op(ov, instance_var, node_id_vars, instance_var, deferred_lines)
            if op:
                lines.append(op)
        # Self property overrides — apply directly to instance variable
        for prop in properties:
            op = _emit_override_op(prop, instance_var, node_id_vars, instance_var, deferred_lines)
            if op:
                lines.append(op)
    else:
        # Child target — find the node, then apply swap + properties
        esc_target = _escape_js(target)
        find_expr = f'{instance_var}.findOne(n => n.id.endsWith("{esc_target}"))'

        # Collect all operations (swap first, then properties)
        ops: list[str] = []
        if swap:
            ov = {"property": "instance_swap", "value": swap}
            op = _emit_override_op(ov, "_c", node_id_vars, instance_var, deferred_lines)
            if op:
                ops.append(op)
        for prop in properties:
            op = _emit_override_op(prop, "_c", node_id_vars, instance_var, deferred_lines)
            if op:
                ops.append(op)

        if ops:
            if len(ops) == 1:
                lines.append(
                    f'{{ const _c = {find_expr}; '
                    f"if (_c) {{ {ops[0]} }} }}"
                )
            else:
                lines.append(
                    f'{{ const _c = {find_expr}; if (_c) {{'
                )
                for op in ops:
                    lines.append(f"  {op}")
                lines.append("} }")

    # Recurse into children (guaranteed to come after parent)
    for child in node.get("children", []):
        _emit_override_tree(child, instance_var, node_id_vars, lines, deferred_lines)


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


def format_js_value(value: Any, value_type: str) -> str:
    """Format a Python value as a JS literal based on the property's value_type.

    Centralizes type-aware formatting so templates don't embed quoting.
    """
    if value_type == "boolean":
        if isinstance(value, str):
            return "true" if value.lower() in ("true", "1") else "false"
        return "true" if value else "false"
    if value_type in ("enum", "string"):
        return f'"{_escape_js(str(value))}"'
    if value_type in ("json", "json_array"):
        return json.dumps(value) if not isinstance(value, str) else value
    if value_type == "number_radians":
        return str(-math.degrees(value))
    # number, number_or_mixed
    return str(value)


# Corner key → Figma Plugin API property name
_CORNER_MAP = {
    "tl": "topLeftRadius", "tr": "topRightRadius",
    "bl": "bottomLeftRadius", "br": "bottomRightRadius",
}


def _emit_corner_radius_figma(
    var: str, eid: str, value: Any, tokens: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit cornerRadius — uniform (number) or per-corner (dict)."""
    lines: list[str] = []
    if isinstance(value, (int, float)):
        lines.append(f"{var}.cornerRadius = {int(value)};")
    elif isinstance(value, dict):
        for corner_key, figma_prop in _CORNER_MAP.items():
            lines.append(f"{var}.{figma_prop} = {value.get(corner_key, 0)};")
    return lines, []


def _emit_clips_content_figma(
    var: str, eid: str, value: Any, tokens: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit clipsContent with JS boolean literals (not Python True/False)."""
    if value is True:
        return [f"{var}.clipsContent = true;"], []
    if value is False:
        return [f"{var}.clipsContent = false;"], []
    return [], []


# Handler dispatch: figma_name → callable(var, eid, value, tokens) → (lines, refs)
# Registered here to avoid circular imports (handlers defined in this file,
# registry in property_registry.py).
_FIGMA_HANDLERS: dict[str, Any] = {}


def _register_figma_handlers() -> None:
    """Register handler functions for HANDLER-sentinel properties."""
    if _FIGMA_HANDLERS:
        return  # already registered
    _FIGMA_HANDLERS.update({
        "fills": _emit_fills,
        "strokes": _emit_strokes,
        "effects": _emit_effects,
        "cornerRadius": _emit_corner_radius_figma,
        "clipsContent": _emit_clips_content_figma,
    })


def emit_from_registry(
    var: str,
    eid: str,
    visual: dict[str, Any],
    tokens: dict[str, Any],
    renderer: str = "figma",
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit properties from the visual dict, driven by the registry.

    Three emit categories:
    - HANDLER sentinel → dispatch to _FIGMA_HANDLERS[figma_name]
    - String template → type-aware formatting via format_js_value
    - Empty/missing emit dict → deferred, skip

    Returns (lines, token_refs).
    """
    from dd.property_registry import PROPERTIES, HANDLER

    _register_figma_handlers()

    lines: list[str] = []
    refs: list[tuple[str, str, str]] = []
    token_refs_map = visual.get("_token_refs", {})

    for prop in PROPERTIES:
        spec = prop.emit.get(renderer)
        if spec is None:
            continue

        value = visual.get(prop.figma_name)
        if value is None:
            continue

        if spec is HANDLER:
            handler = _FIGMA_HANDLERS.get(prop.figma_name)
            if handler:
                out_lines, out_refs = handler(var, eid, value, tokens)
                lines.extend(out_lines)
                refs.extend(out_refs)
        elif isinstance(spec, str):
            formatted = format_js_value(value, prop.value_type)
            line = spec.format(var=var, value=formatted, figma_name=prop.figma_name)
            lines.append(line)

        # Collect token refs from registry-driven binding resolution
        if prop.figma_name in token_refs_map:
            refs.append((eid, prop.figma_name, token_refs_map[prop.figma_name]))

    return lines, refs




_DIRECTION_MAP = {"horizontal": "HORIZONTAL", "vertical": "VERTICAL"}

# Semantic sizing → Figma Plugin API enum (renderer-specific uppercase)
_SIZING_MAP = {"fill": "FILL", "hug": "HUG", "fixed": "FIXED"}


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

def calculate_canvas_layout(
    screen_sizes: list[tuple[float, float]],
    gap: float = 80,
) -> list[tuple[float, float]]:
    """Calculate canvas positions for multiple screens in a horizontal row.

    Returns list of (x, y) positions, one per screen.
    """
    positions: list[tuple[float, float]] = []
    x = 0.0
    for i, (w, _h) in enumerate(screen_sizes):
        positions.append((x, 0.0))
        x += w + gap
    return positions


def generate_figma_script(
    spec: dict[str, Any],
    db_visuals: dict[int, dict[str, Any]] | None = None,
    page_name: str | None = None,
    canvas_position: tuple[float, float] | None = None,
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

    fonts = collect_fonts(spec, db_visuals=db_visuals)
    walk_order = _walk_elements(spec)
    all_token_refs: list[tuple[str, str, str]] = []

    lines: list[str] = []

    # Always load Inter Regular — Figma's default font for createText()
    all_fonts = [("Inter", "Regular")] + [f for f in fonts if f != ("Inter", "Regular")]
    for family, style in all_fonts:
        lines.append(f'await figma.loadFontAsync({{family: "{family}", style: "{style}"}});')

    lines.append("const M = {};")

    # Position + constraints are deferred to after ALL children are appended.
    # Figma recalculates position when children are added to HUG/auto-layout
    # frames with CENTER constraints, so x/y must be set last.
    deferred_lines: list[str] = []

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
            _collect_swap_targets_from_tree(vis.get("override_tree"), needed_node_ids)

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

        instance_figma_node_id = raw_visual.get("figma_node_id") if (db_visuals is not None and raw_visual) else None

        # Mode 1 fallback chain:
        #   1. component_figma_id (from registry) → getNodeByIdAsync → createInstance
        #   2. instance figma_node_id (from DB) → getMainComponentAsync → createInstance
        #      (handles unpublished/local components that importComponentByKeyAsync rejects)
        #   3. Fall through to Mode 2 (createFrame) if no usable ID
        use_mode1 = (component_key or component_figma_id) and not is_text
        if use_mode1:
            if component_figma_id:
                node_expr = node_id_vars.get(component_figma_id, f'await figma.getNodeByIdAsync("{_escape_js(component_figma_id)}")')
                lines.append(
                    f'const {var} = ({node_expr}).createInstance();'
                )
            elif instance_figma_node_id:
                lines.append(
                    f'const {var} = (await (await figma.getNodeByIdAsync("{_escape_js(instance_figma_node_id)}")).getMainComponentAsync()).createInstance();'
                )
            else:
                use_mode1 = False

        if use_mode1:
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

            # Instance overrides via override tree. The tree encodes
            # dependency ordering: pre-order traversal ensures swaps
            # happen before property overrides on swapped descendants.
            override_tree = raw_visual.get("override_tree") if (db_visuals is not None and raw_visual) else None
            if override_tree:
                _emit_override_tree(override_tree, var, node_id_vars, lines, deferred_lines)

            # L0 visual properties on the instance itself (rotation, opacity).
            # These differ from the master's defaults but aren't captured as
            # instance_overrides — they're direct properties on the DB node.
            if db_visuals is not None and raw_visual:
                inst_rotation = raw_visual.get("rotation")
                if inst_rotation is not None and inst_rotation != 0:
                    lines.append(f"{var}.rotation = {-math.degrees(inst_rotation)};")
                inst_opacity = raw_visual.get("opacity")
                if inst_opacity is not None and inst_opacity < 1.0:
                    lines.append(f"{var}.opacity = {inst_opacity};")

            # Instance's own visibility (e.g., hidden keyboard overlay)
            if element.get("visible") is False:
                lines.append(f"{var}.visible = false;")

            # Position set after appendChild (see post-appendChild block below)

            mode1_eids.add(eid)
        else:
            # Mode 2: create from L0 properties
            # Check for asset-backed vector nodes before skipping
            has_vector_asset = False
            if etype in _VECTOR_TYPES and db_visuals is not None:
                node_id = spec.get("_node_id_map", {}).get(eid)
                if node_id:
                    visual_data = db_visuals.get(node_id, {})
                    asset_refs = visual_data.get("_asset_refs", [])
                    has_vector_asset = any(
                        ref.get("kind") in ("svg_path", "svg_doc")
                        for ref in asset_refs
                    )

            if etype in _SKIP_NODE_TYPES and not has_vector_asset:
                skipped_eids.add(eid)
                continue

            if has_vector_asset:
                lines.append(f"const {var} = figma.createVector();")
            elif is_text:
                lines.append(f"const {var} = figma.createText();")
            elif etype in _NODE_CREATE_MAP:
                lines.append(f"const {var} = {_NODE_CREATE_MAP[etype]};")
            else:
                lines.append(f"const {var} = figma.createFrame();")

            original_name = element.get("_original_name", eid)
            lines.append(f'{var}.name = "{_escape_js(original_name)}";')

            if is_text:
                text_resize = "WIDTH_AND_HEIGHT"
                if db_visuals is not None:
                    node_id = spec.get("_node_id_map", {}).get(eid)
                    text_visual = db_visuals.get(node_id, {}) if node_id else {}
                    stored = text_visual.get("text_auto_resize")
                    if stored:
                        text_resize = stored
                lines.append(f'{var}.textAutoResize = "{text_resize}";')

            layout = element.get("layout", {})
            layout_lines, layout_refs = _emit_layout(var, eid, layout, tokens)
            lines.extend(layout_lines)
            all_token_refs.extend(layout_refs)

            if db_visuals is not None:
                node_id = spec.get("_node_id_map", {}).get(eid)
                raw_visual = db_visuals.get(node_id, {}) if node_id else {}
                visual = build_visual_from_db(raw_visual)
            else:
                raw_visual = {}
                visual = {}
            visual_lines, visual_refs = _emit_visual(var, eid, visual, tokens)
            lines.extend(visual_lines)
            all_token_refs.extend(visual_refs)

            # Emit vector paths for asset-backed vector nodes
            if has_vector_asset:
                _emit_vector_paths(var, raw_visual, lines)

            # Clear default white fill on frames that should be transparent.
            # figma.createFrame() gets a default white fill; if the DB has no
            # fills (NULL or []), the original was transparent — clear it.
            if not is_text and not visual.get("fills") and etype not in _NODE_CREATE_MAP:
                lines.append(f"{var}.fills = [];")

            if element.get("visible") is False:
                lines.append(f"{var}.visible = false;")

            style = element.get("style", {})
            if is_text:
                # DB font data used as L0 fallback in _emit_text_props.
                # Progressive fallback: IR style (L2 tokens) → DB values (L0).
                # We pass db_font separately so _emit_text_props can fall back
                # per-property when a token ref can't be resolved.
                # Sources (checked in order):
                #   1. visual["font"] — from build_visual_from_db (flat DB columns)
                #   2. raw_visual["font"] — pre-built font dict (test fixtures)
                #   3. raw_visual — flat keys from query_screen_visuals
                db_font: dict[str, Any] = (
                    visual.get("font")
                    or (raw_visual.get("font") if raw_visual else None)
                    or (raw_visual if raw_visual else None)
                    or {}
                )
                _emit_text_props(var, element, style, tokens, lines, db_font=db_font)

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
                db_sizing_h = None
                db_sizing_v = None
                text_auto_resize = None
                if db_visuals is not None:
                    nid = spec.get("_node_id_map", {}).get(eid)
                    if nid:
                        nv = db_visuals.get(nid, {})
                        db_sizing_h = nv.get("layout_sizing_h")
                        db_sizing_v = nv.get("layout_sizing_v")
                        text_auto_resize = nv.get("text_auto_resize")
                sizing_h, sizing_v = _resolve_layout_sizing(
                    elem_sizing, db_sizing_h, db_sizing_v,
                    text_auto_resize, is_text, etype,
                )
                if sizing_h:
                    figma_h = _SIZING_MAP.get(sizing_h, sizing_h.upper())
                    lines.append(f'{var}.layoutSizingHorizontal = "{figma_h}";')
                if sizing_v:
                    figma_v = _SIZING_MAP.get(sizing_v, sizing_v.upper())
                    lines.append(f'{var}.layoutSizingVertical = "{figma_v}";')
            else:
                # Position deferred — Figma recalculates position when
                # children are added to HUG frames with CENTER constraints.
                # Position comes from the IR (parent-relative coordinates).
                # DB stores absolute canvas coordinates — NOT usable directly.
                # The IR converts absolute → parent-relative at build time
                # (see compiler-architecture.md Section 4.1: Spatial Encoding).
                position = element.get("layout", {}).get("position")
                if position:
                    deferred_lines.append(f"{var}.x = {position.get('x', 0)};")
                    deferred_lines.append(f"{var}.y = {position.get('y', 0)};")

            # Constraints also deferred (after position)
            if db_visuals is not None:
                node_id = spec.get("_node_id_map", {}).get(eid)
                constraint_visual = db_visuals.get(node_id, {}) if node_id else {}
                c_h = constraint_visual.get("constraint_h")
                c_v = constraint_visual.get("constraint_v")
                if c_h or c_v:
                    parts = []
                    if c_h:
                        mapped = _CONSTRAINT_MAP.get(c_h, c_h)
                        parts.append(f'horizontal: "{mapped}"')
                    if c_v:
                        mapped = _CONSTRAINT_MAP.get(c_v, c_v)
                        parts.append(f'vertical: "{mapped}"')
                    deferred_lines.append(f"{var}.constraints = {{{', '.join(parts)}}};")

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

        if canvas_position is not None:
            cx, cy = canvas_position
            lines.append(f"{var_map[root_id]}.x = {cx};")
            lines.append(f"{var_map[root_id]}.y = {cy};")

    # Emit deferred position + constraints (after all children are appended)
    if deferred_lines:
        lines.append("")
        lines.append("// Yield to Figma's event loop before deferred positioning")
        lines.append("await new Promise(r => setTimeout(r, 0));")
        lines.append("")
        lines.append("// Position + constraints (deferred until all children appended)")
        lines.append("try {")
        for dl in deferred_lines:
            lines.append(f"  {dl}")
        lines.append('  M["__canary"] = "deferred_ok";')
        lines.append("} catch (_e) {")
        lines.append('  M["__canary"] = "deferred_error: " + _e.message;')
        lines.append("}")

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
    # Auto-layout containers CAN set their own layoutSizing before appendChild
    # (they define their own auto-layout context). Non-auto-layout children
    # (text, rectangles, non-layout frames) must defer to post-appendChild.
    if has_auto_layout:
        for axis, figma_axis in [("width", "Horizontal"), ("height", "Vertical")]:
            val = sizing.get(axis)
            if val is None:
                continue
            if isinstance(val, str):
                mapped = _SIZING_MAP.get(val)
                if mapped and mapped != "FILL":
                    lines.append(f'{var}.layoutSizing{figma_axis} = "{mapped}";')
            elif isinstance(val, (int, float)):
                lines.append(f'{var}.layoutSizing{figma_axis} = "FIXED";')

    w = sizing.get("width")
    h = sizing.get("height")
    rw = int(w) if isinstance(w, (int, float)) else sizing.get("widthPixels")
    rh = int(h) if isinstance(h, (int, float)) else sizing.get("heightPixels")
    if rw is not None:
        rw = int(rw)
    if rh is not None:
        rh = int(rh)
    if rw is not None and rh is not None:
        lines.append(f"{var}.resize({rw}, {rh});")
    elif rw is not None:
        lines.append(f"{var}.resize({rw}, {var}.height);")
    elif rh is not None:
        lines.append(f"{var}.resize({var}.width, {rh});")

    main_align = layout.get("mainAxisAlignment")
    if main_align:
        mapped = _ALIGNMENT_MAP.get(main_align, main_align.upper())
        lines.append(f'{var}.primaryAxisAlignItems = "{mapped}";')

    cross_align = layout.get("crossAxisAlignment")
    if cross_align:
        mapped = _ALIGNMENT_MAP.get(cross_align, cross_align.upper())
        lines.append(f'{var}.counterAxisAlignItems = "{mapped}";')

    # Position is NOT emitted here — it must be set AFTER appendChild
    # because Figma interprets x/y as parent-relative only when the
    # child is attached. See the post-appendChild block in the main loop.

    return (lines, refs)


def _emit_visual(
    var: str, eid: str, visual: dict[str, Any], tokens: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit Figma JS for all visual properties, driven by the registry.

    Delegates entirely to emit_from_registry which dispatches HANDLER
    properties (fills, strokes, effects, cornerRadius, clipsContent) to
    their handler functions and formats template properties via
    format_js_value.
    """
    return emit_from_registry(var, eid, visual, tokens, renderer="figma")


# IR gradient type → Figma Plugin API type
_GRADIENT_EMIT_MAP = {
    "gradient-linear": "GRADIENT_LINEAR",
    "gradient-radial": "GRADIENT_RADIAL",
    "gradient-angular": "GRADIENT_ANGULAR",
    "gradient-diamond": "GRADIENT_DIAMOND",
}


def _emit_vector_paths(
    var: str, raw_visual: dict[str, Any], lines: list[str]
) -> None:
    """Emit vectorPaths assignment from asset ref SVG data."""
    asset_refs = raw_visual.get("_asset_refs", [])
    svg_paths = [
        ref["svg_data"]
        for ref in asset_refs
        if ref.get("kind") in ("svg_path", "svg_doc") and ref.get("svg_data")
    ]
    if svg_paths:
        path_entries = ", ".join(
            f'{{windingRule: "NONZERO", data: "{_escape_js(p)}"}}'
            for p in svg_paths
        )
        lines.append(f"{var}.vectorPaths = [{path_entries}];")


def _emit_fills(
    var: str, eid: str, fills: list[dict[str, Any]], tokens: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit Figma fills array from IR normalized fills.

    Handles SOLID and GRADIENT_* types. Gradient emission requires
    gradientTransform (Plugin API format) — stored by supplement extraction.
    If gradientTransform is missing, the gradient is skipped (REST API
    handlePositions cannot be used directly by the Plugin API).
    """
    paints: list[str] = []
    refs: list[tuple[str, str, str]] = []

    for i, fill in enumerate(fills):
        fill_type = fill.get("type", "")

        if fill_type == "solid":
            color_val = fill.get("color", "")
            resolved, token_name = resolve_style_value(color_val, tokens)
            if resolved and isinstance(resolved, str) and resolved.startswith("#"):
                rgb = hex_to_figma_rgba(resolved)
                paint = f'{{type: "SOLID", color: {{r:{rgb["r"]},g:{rgb["g"]},b:{rgb["b"]}}}}}'
                opacity = fill.get("opacity")
                if opacity is not None and opacity < 1.0:
                    paint = f'{{type: "SOLID", color: {{r:{rgb["r"]},g:{rgb["g"]},b:{rgb["b"]}}}, opacity: {opacity}}}'
                paints.append(paint)
            if token_name:
                refs.append((eid, f"fill.{i}.color", token_name))

        elif fill_type in _GRADIENT_EMIT_MAP:
            gradient_transform = fill.get("gradientTransform")
            if not gradient_transform:
                continue
            figma_type = _GRADIENT_EMIT_MAP[fill_type]
            stops = fill.get("stops", [])
            stop_strs = []
            for j, stop in enumerate(stops):
                color_val = stop.get("color", "#000000")
                resolved, token_name = resolve_style_value(color_val, tokens)
                if resolved and isinstance(resolved, str) and resolved.startswith("#"):
                    rgb = hex_to_figma_rgba(resolved)
                    stop_strs.append(
                        f'{{color: {{r:{rgb["r"]},g:{rgb["g"]},b:{rgb["b"]},a:{rgb["a"]}}}, position: {stop.get("position", 0)}}}'
                    )
                if token_name:
                    refs.append((eid, f"fill.{i}.gradient.stop.{j}.color", token_name))

            if stop_strs:
                gt = gradient_transform
                opacity = fill.get("opacity")
                opacity_str = f", opacity: {opacity}" if opacity is not None and opacity < 1.0 else ""
                paints.append(
                    f'{{type: "{figma_type}", '
                    f'gradientTransform: [[{gt[0][0]},{gt[0][1]},{gt[0][2]}],[{gt[1][0]},{gt[1][1]},{gt[1][2]}]], '
                    f'gradientStops: [{", ".join(stop_strs)}]'
                    f'{opacity_str}}}'
                )

        elif fill_type == "image":
            asset_hash = fill.get("asset_hash")
            if asset_hash:
                scale_mode = fill.get("scaleMode", "fill").upper()
                opacity = fill.get("opacity")
                opacity_str = f', opacity: {opacity}' if opacity is not None and opacity < 1.0 else ""
                paints.append(
                    f'{{type: "IMAGE", scaleMode: "{scale_mode}", '
                    f'imageHash: "{_escape_js(asset_hash)}"{opacity_str}}}'
                )

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
            rgb = hex_to_figma_rgba(resolved)
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
                rgb = hex_to_figma_rgba(resolved)
                effect_objs.append(
                    f'{{type: "{figma_type}", visible: true, blendMode: "NORMAL", '
                    f'color: {{r:{rgb["r"]},g:{rgb["g"]},b:{rgb["b"]},a:{rgb["a"]}}}, '
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


def _resolve_text_value(
    style_val: Any, db_val: Any, tokens: dict[str, Any],
) -> Any:
    """Resolve a text style value using progressive fallback: L2 → L0.

    If the IR style has a literal value, use it. If it has a token ref,
    try to resolve it from the tokens dict. If the token can't be resolved,
    fall back to the DB value (L0). This ensures renderers never silently
    drop properties when token bindings exist but aren't resolvable yet.
    """
    if style_val is None:
        return db_val
    if isinstance(style_val, str) and style_val.startswith("{"):
        resolved, _ = resolve_style_value(style_val, tokens)
        if resolved is not None:
            return resolved
        return db_val
    return style_val


def _emit_text_props(
    var: str, element: dict[str, Any], style: dict[str, Any],
    tokens: dict[str, Any], lines: list[str],
    db_font: dict[str, Any] | None = None,
) -> None:
    """Emit text properties with progressive fallback (L2 token → L0 DB).

    db_font: raw DB font data (font_family, font_size, font_weight, etc.)
    used as L0 fallback when IR style token refs can't be resolved.
    """
    if db_font is None:
        db_font = {}

    family = _resolve_text_value(
        style.get("fontFamily"), db_font.get("font_family", "Inter"), tokens,
    )
    if not isinstance(family, str):
        family = "Inter"
    family = _normalize_font_family(family)

    weight = _resolve_text_value(
        style.get("fontWeight"), db_font.get("font_weight"), tokens,
    )
    figma_style = normalize_font_style(family, font_weight_to_style(weight))

    db_font_style = db_font.get("font_style")
    if db_font_style and db_font_style != "Regular":
        if "Italic" not in figma_style and "Oblique" not in figma_style:
            figma_style = f"{figma_style} {db_font_style}"

    lines.append(f'{var}.fontName = {{family: "{family}", style: "{figma_style}"}};')

    font_size = _resolve_text_value(
        style.get("fontSize"), db_font.get("font_size"), tokens,
    )
    if font_size is not None:
        lines.append(f"{var}.fontSize = {font_size};")

    text = element.get("props", {}).get("text", "")
    if text:
        lines.append(f'{var}.characters = "{_escape_js(text)}";')

    text_align_h = db_font.get("text_align")
    if text_align_h:
        lines.append(f'{var}.textAlignHorizontal = "{text_align_h}";')

    text_align_v = db_font.get("text_align_v")
    if text_align_v:
        lines.append(f'{var}.textAlignVertical = "{text_align_v}";')

    text_decoration = db_font.get("text_decoration")
    if text_decoration:
        lines.append(f'{var}.textDecoration = "{text_decoration}";')

    text_case = db_font.get("text_case")
    if text_case:
        lines.append(f'{var}.textCase = "{text_case}";')

    line_height = db_font.get("line_height")
    if line_height is not None:
        if isinstance(line_height, str):
            try:
                lh = json.loads(line_height)
            except (ValueError, TypeError):
                lh = None
        else:
            lh = line_height
        if isinstance(lh, dict) and "value" in lh:
            unit = lh.get("unit", "PIXELS")
            lines.append(f'{var}.lineHeight = {{value: {lh["value"]}, unit: "{unit}"}};')

    letter_spacing = db_font.get("letter_spacing")
    if letter_spacing is not None:
        if isinstance(letter_spacing, str):
            try:
                ls = json.loads(letter_spacing)
            except (ValueError, TypeError):
                ls = None
        else:
            ls = letter_spacing
        if isinstance(ls, dict) and "value" in ls:
            unit = ls.get("unit", "PIXELS")
            lines.append(f'{var}.letterSpacing = {{value: {ls["value"]}, unit: "{unit}"}};')

    paragraph_spacing = db_font.get("paragraph_spacing")
    if paragraph_spacing is not None:
        lines.append(f"{var}.paragraphSpacing = {paragraph_spacing};")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_screen(conn: sqlite3.Connection, screen_id: int) -> dict[str, Any]:
    """Generate a Figma creation manifest for a classified screen.

    Returns dict with:
      structure_script: JS string for figma_execute (Phase A — creates nodes)
      token_refs: list of (element_id, property, token_name) for rebinding
      token_variables: dict mapping token_name → figma_variable_id
      element_count: number of elements in the spec
    """
    from dd.ir import generate_ir, query_screen_visuals
    from dd.rebind_prompt import query_token_variables

    ir_result = generate_ir(conn, screen_id)
    spec = ir_result["spec"]
    visuals = query_screen_visuals(conn, screen_id)

    script, token_refs = generate_figma_script(spec, db_visuals=visuals)

    return {
        "structure_script": script,
        "token_refs": token_refs,
        "token_variables": query_token_variables(conn),
        "element_count": ir_result["element_count"],
        "token_count": ir_result["token_count"],
    }


def build_rebind_script_from_result(
    result: dict[str, Any],
    figma_node_map: dict[str, str],
) -> str:
    """Build a token rebind script from generate_screen result + Figma node map.

    Call this after executing structure_script in Figma. Pass the M dict
    (element_id → figma_node_id) returned by the structure script as
    figma_node_map.

    Returns a JS string that binds Figma variables to the created nodes.
    Returns empty string if no rebindable entries.
    """
    from dd.rebind_prompt import build_rebind_entries, generate_rebind_script

    token_refs = result.get("token_refs", [])
    token_variables = result.get("token_variables", {})

    entries = build_rebind_entries(token_refs, figma_node_map, token_variables)
    if not entries:
        return ""

    return generate_rebind_script(entries)
