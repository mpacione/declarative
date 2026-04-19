"""Figma Plugin API renderer.

Generates Figma Plugin API JavaScript from CompositionSpec + DB visuals.
Platform-specific: all value transforms, JS emission, font handling,
and color conversion for the Figma Plugin API live here.

Shared infrastructure (renderer-agnostic) lives in dd.visual:
  build_visual_from_db, resolve_style_value, _resolve_layout_sizing

See docs/cross-platform-value-formats.md for how this renderer's
transforms compare to other platforms (React, SwiftUI, Flutter).
"""

from __future__ import annotations

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


# The Missing-Component wireframe placeholder helper — injected into the
# preamble when any Phase 1 node emits a `_missingComponentPlaceholder`
# call (i.e. Mode 1 fell back for at least one INSTANCE).
#
# Shared between the dict-IR renderer (`generate_figma_script` below) and
# the markup-native renderer (`dd.render_figma_ast.render_figma_preamble`)
# so both paths emit byte-identical placeholder blocks. At M6 cutover the
# dict-IR path is deleted and this constant relocates to
# `dd.render_figma_ast`.
MISSING_COMPONENT_PLACEHOLDER_BLOCK = (
    "// Missing-component wireframe placeholder: emitted when a Mode 1\n"
    "// createInstance falls back (deleted/unpublished/stripped component).\n"
    "// Architectural-style diagonal hatching inside a bordered frame.\n"
    "//\n"
    "// Design notes:\n"
    "// - Hatch: parallel 45° lines, ~12px apart, mid-grey. This is the\n"
    "//   standard convention in architectural/engineering drawings for\n"
    "//   'unfilled / to be specified' regions. Reads clearly as a\n"
    "//   placeholder at any aspect ratio, scales nicely.\n"
    "// - Mid-grey (0.5) on strokes/text so the wireframe stays visible\n"
    "//   even if downstream DB overrides clobber the frame fill.\n"
    "// - Hatch is skipped when the frame is tiny (< 40x40) — pattern\n"
    "//   just looks like noise at icon sizes.\n"
    "// - Name label appears only when the frame is >= 64x32.\n"
    "// - setPluginData('__ph','1') marks the returned frame so the\n"
    "//   caller can gate subsequent visual-property writes (the DB's\n"
    "//   overrides for the real component shouldn't be applied to the\n"
    "//   placeholder).\n"
    "const _MIN_LABEL_W = 64, _MIN_LABEL_H = 32;\n"
    "const _MIN_HATCH = 40;\n"
    "const _HATCH_STRIDE = 12;\n"
    "function _missingComponentPlaceholder(name, w, h, eid) {\n"
    "  __errors.push({kind:\"component_missing\", eid, name, w, h});\n"
    "  const f = figma.createFrame();\n"
    "  f.resize(w || 24, h || 24);\n"
    "  f.fills = [];\n"
    "  f.strokes = [{type:\"SOLID\", color:{r:0.5,g:0.5,b:0.5}}];\n"
    "  f.strokeWeight = 1;\n"
    "  f.clipsContent = true;\n"
    "  try { f.setPluginData('__ph', '1'); } catch (__e) {}\n"
    "  const actualW = f.width, actualH = f.height;\n"
    "  // Diagonal hatch pattern, clipped by frame bounds.\n"
    "  // Skipped at tiny sizes (icon-sized placeholders look like noise).\n"
    "  if (actualW >= _MIN_HATCH && actualH >= _MIN_HATCH) {\n"
    "    const total = actualW + actualH;\n"
    "    const lineLen = total * 1.5;  // long enough to always span the frame at 45°\n"
    "    for (let offset = -actualH; offset <= actualW + actualH; offset += _HATCH_STRIDE) {\n"
    "      const ln = figma.createLine();\n"
    "      // Subtle opacity so stacked placeholders (e.g. overlay over\n"
    "      // modal over background) don't compound into an opaque\n"
    "      // mesh. 15% reads as 'placeholder texture' without\n"
    "      // competing with any real content that overlays it.\n"
    "      ln.strokes = [{type:\"SOLID\", color:{r:0.5,g:0.5,b:0.5}, opacity:0.15}];\n"
    "      ln.strokeWeight = 1;\n"
    "      ln.resize(lineLen, 0);\n"
    "      // Plugin API rotation: +45 is visually CCW (up-right).\n"
    "      // Line starts at (offset, actualH) on or below the frame's\n"
    "      // bottom edge and goes up-right, clipped to the frame.\n"
    "      ln.rotation = 45;\n"
    "      ln.x = offset;\n"
    "      ln.y = actualH;\n"
    "      f.appendChild(ln);\n"
    "    }\n"
    "  }\n"
    "  if (actualW >= _MIN_LABEL_W && actualH >= _MIN_LABEL_H && name) {\n"
    "    try {\n"
    "      const t = figma.createText();\n"
    "      t.fontName = {family:\"Inter\", style:\"Regular\"};\n"
    "      t.fontSize = 10;\n"
    "      t.characters = String(name);\n"
    "      t.x = 4; t.y = 4;\n"
    "      t.fills = [{type:\"SOLID\", color:{r:0.5,g:0.5,b:0.5}}];\n"
    "      f.appendChild(t);\n"
    "    } catch (__e) {}\n"
    "  }\n"
    "  return f;\n"
    "}\n"
    "// Helper to gate a setter on whether the target is a placeholder.\n"
    "// Used to prevent DB visual overrides (fills/strokes/effects) from\n"
    "// clobbering the placeholder's wireframe appearance.\n"
    "function _isPh(n) { try { return n.getPluginData('__ph') === '1'; } catch (__e) { return false; } }"
)

# Container types that should fill parent width in vertical auto-layout.
# These are full-width components that span the screen in real designs.

# Node type → Figma creation call for non-FRAME types
_NODE_CREATE_MAP = {
    "rectangle": "figma.createRectangle()",
    "ellipse": "figma.createEllipse()",
    "line": "figma.createLine()",
    "vector": "figma.createVector()",
    "boolean_operation": "figma.createBooleanOperation()",
}

# Vector-capable node types that can have SVG path data from the asset pipeline
_VECTOR_TYPES = frozenset({"vector", "boolean_operation"})

# Element types whose underlying Figma node type does NOT support
# auto-layout. Setting `layoutMode`, `itemSpacing`, `padding*`,
# `primaryAxisAlignItems`, or `counterAxisAlignItems` on these is
# rejected by the Plugin API with "object is not extensible".
#
# Composition: anything that maps to createText() (_TEXT_TYPES: text,
# heading, link) plus the createRectangle / createEllipse / createLine /
# createVector / createBooleanOperation / createGroup shape types
# plus image / icon (which compose may not wrap in a frame — treated
# leaf to be safe; a Mode-1 INSTANCE for `icon` has its own etype
# path). Gate emission accordingly in _emit_layout, and via the
# capability registry in emit_from_registry for other callers.
_LEAF_TYPES = _TEXT_TYPES | frozenset({
    "rectangle", "ellipse", "line", "vector", "boolean_operation",
    "group", "star", "polygon", "image",
})

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
_SEMIBOLD_CAMEL = frozenset({"Baskerville", "Inter Variable"})


def normalize_font_style(family: str, style: str) -> str:
    """Normalize font style name for a specific font family.

    Different font families use different naming for the same weight:
    - Inter: "Semi Bold" (space)
    - SF Pro Text/Display/Pro: "Semibold" (no space)
    - Baskerville: "SemiBold" (camelCase)

    Handles both directions: weight-derived "Semi Bold" → family form,
    and DB-extracted "SemiBold" (from a different family) → target form.
    """
    # Canonicalize all semibold variants to "Semi Bold" first
    canonical = style.replace("SemiBold", "Semi Bold").replace("Semibold", "Semi Bold")
    if "Semi Bold" not in canonical:
        return style
    if family in _SEMIBOLD_NO_SPACE:
        return canonical.replace("Semi Bold", "Semibold")
    if family in _SEMIBOLD_CAMEL:
        return canonical.replace("Semi Bold", "SemiBold")
    return canonical


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

        if db_font_style:
            figma_style = normalize_font_style(family, db_font_style)
        else:
            figma_style = normalize_font_style(family, font_weight_to_style(weight))

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
        value_js = _escape_js(value)
        # When the swap target is missing, we can't replace the child
        # with a placeholder — swap targets usually live inside an
        # instance (e.g. icon slot inside a button instance), and the
        # Plugin API forbids insertChild into an instance's descendants.
        # Instead, record the miss in __errors so the verification
        # channel attributes the gap per-eid. The child stays as the
        # master's default — at least it renders something, and the
        # structured error channel makes the drift visible.
        return (
            f'if ({target_var}.type === "INSTANCE") {{ '
            f'const _comp = {comp_expr}; '
            f'if (_comp) {{ {target_var}.swapComponent(_comp); }} '
            f'else {{ __errors.push({{kind:"component_missing", '
            f'eid:"swap:{value_js}", name:{target_var}.name, '
            f'w:{target_var}.width, h:{target_var}.height, '
            f'note:"swap target unavailable; kept master default"}}); }} '
            f'}}'
        )
    if prop_name == "width":
        h_ref = f"{parent_var}.height" if is_self else f"{target_var}.height"
        op = f"{target_var}.resize({value}, {h_ref});"
        return _gate_if_not_placeholder(op, target_var) if is_self else op
    if prop_name == "height":
        w_ref = f"{parent_var}.width" if is_self else f"{target_var}.width"
        op = f"{target_var}.resize({w_ref}, {value});"
        return _gate_if_not_placeholder(op, target_var) if is_self else op
    if prop_name in ("layoutSizingHorizontal", "layoutSizingVertical") and is_self:
        deferred_lines.append(
            _gate_if_not_placeholder(
                f'{target_var}.{prop_name} = {format_js_value(value, "enum")};',
                target_var,
            )
        )
        return ""

    from dd.property_registry import by_figma_name
    prop = by_figma_name(prop_name)
    if prop:
        formatted = format_js_value(value, prop.value_type)
        op = f"{target_var}.{prop.figma_name} = {formatted};"
        # Gate self-target writes on runtime placeholder check. When the
        # instance fell back to our wireframe placeholder (missing source
        # component), these DB-sourced visual properties would otherwise
        # clobber the wireframe (e.g. a black `.fills` over the X diagonals
        # turns the placeholder into a giant black box).
        return _gate_if_not_placeholder(op, target_var) if is_self else op
    return ""


def _gate_if_not_placeholder(op: str, var: str) -> str:
    """Wrap a JS statement so it only runs when `var` is NOT a placeholder.

    Uses the runtime `_isPh(node)` helper (emitted in the preamble alongside
    `_missingComponentPlaceholder`). If the node has pluginData '__ph'='1',
    it's a wireframe placeholder from the Mode 1 fallback path, and we
    should not apply the DB's visual properties to it.
    """
    return f"if (!_isPh({var})) {{ {op} }}"


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


# OpenType feature -> Unicode glyph substitutions.
# Figma's Plugin API doesn't let us apply per-range OpenType features, so
# we substitute at the character level for well-known patterns. Each entry
# is (feature_name, source_char) -> target_unicode_char. Inter's SUPS
# feature renders "0" and "o" as the degree symbol — the most common case
# in this codebase's meme-creator UI (-25°, 270°, etc.).
_OPENTYPE_SUBSTITUTIONS: dict[tuple[str, str], str] = {
    ("SUPS", "0"): "\u00b0",  # degree (most common in this file)
    ("SUPS", "o"): "\u00b0",
}


def _apply_opentype_substitution(text: str, segments: list[dict]) -> str:
    """Substitute characters in `text` per Unicode glyph mappings keyed by
    (OpenType feature, source character). Segments are {s, e, f: {feature: bool}}
    objects from Plugin API getStyledTextSegments(['openTypeFeatures']).

    Used because Figma's Plugin API has getRangeOpenTypeFeatures but NO
    setter — per-range features cannot be re-applied programmatically.
    """
    if not segments:
        return text
    chars = list(text)
    for seg in segments:
        start = seg.get("s", 0)
        end = seg.get("e", 0)
        features = seg.get("f") or {}
        if not (features and 0 <= start < end <= len(chars)):
            continue
        for feat_name, feat_on in features.items():
            if not feat_on:
                continue
            for i in range(start, end):
                sub = _OPENTYPE_SUBSTITUTIONS.get((feat_name, chars[i]))
                if sub:
                    chars[i] = sub
    return "".join(chars)


def _guarded_op(op: str, eid: str, kind: str) -> str:
    """Wrap a single JS statement in an inline try/catch that pushes a
    structured entry to __errors on throw.

    ADR-007 Position 2: per-operation granularity. One bad node produces
    one entry; neighbors still run. Replaces the legacy coarse-grained
    Phase 3 try/catch + M["__canary"] pattern.

    Multi-statement strings (e.g. brace blocks built by the override
    emitter) are accepted as-is — callers are responsible for ensuring
    the wrapped body is a valid expression list.
    """
    eid_lit = _escape_js(eid)
    # Normalize trailing whitespace/semicolon so the guard body doesn't
    # emit `...;;`
    body = op.rstrip()
    if body.endswith(";"):
        body = body[:-1]
    return (
        f"try {{ {body}; }} "
        f'catch (__e) {{ __errors.push({{eid:"{eid_lit}", '
        f'kind:"{kind}", '
        f'error: String(__e && __e.message || __e)}}); }}'
    )


def _normalize_font_family(family: str) -> str:
    """Normalize font family names for Figma compatibility.

    Historically this normalized "Inter Variable" → "Inter" on the
    assumption they're interchangeable. They are not — Inter and
    Inter Variable have slightly different glyph metrics (~1px drift
    on some characters). For a "Medium" label at 17pt in an 86px-wide
    FIXED parent (inner 66px), the 1px overflow caused a 2-line wrap.
    Preserve the source family verbatim; font availability is the
    responsibility of the Figma environment's font loader.
    """
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


def _emit_arc_data_figma(
    var: str, eid: str, value: Any, tokens: dict[str, Any],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit arcData as a JS object with startingAngle, endingAngle, innerRadius."""
    if not isinstance(value, dict):
        return [], []
    parts = []
    for key in ("startingAngle", "endingAngle", "innerRadius"):
        if key in value:
            parts.append(f"{key}: {value[key]}")
    if not parts:
        return [], []
    return [f"{var}.arcData = {{{', '.join(parts)}}};"], []


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
        "arcData": _emit_arc_data_figma,
    })


# IR node-type → Figma Plugin API native node type.
# Used at the emission gate so the capability table (which is declared in
# Figma Plugin API terms) can decide whether a property is legal on a given
# node. Anything not in the map is treated as a container (FRAME).
_IR_TO_FIGMA_TYPE: dict[str, str] = {
    "rectangle": "RECTANGLE",
    "ellipse": "ELLIPSE",
    "line": "LINE",
    "vector": "VECTOR",
    "boolean_operation": "BOOLEAN_OPERATION",
    "text": "TEXT",
    "heading": "TEXT",
    "link": "TEXT",
    "frame": "FRAME",
    "container": "FRAME",
    "screen": "FRAME",
    "section": "FRAME",
    "component": "COMPONENT",
    "instance": "INSTANCE",
    "group": "GROUP",
}


def ir_to_figma_type(ir_type: str) -> str:
    """Map an IR node type string to its Figma Plugin API native type.

    Defaults unknown IR types to "FRAME" — anything container-like in the IR
    becomes a frame in Figma, which is the most permissive capability set
    and matches how the generator falls back when emitting unknown types.
    """
    return _IR_TO_FIGMA_TYPE.get(ir_type, "FRAME")


def emit_from_registry(
    var: str,
    eid: str,
    visual: dict[str, Any],
    tokens: dict[str, Any],
    renderer: str = "figma",
    node_type: str | None = None,
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit properties from the visual dict, driven by the registry.

    Three emit categories:
    - HANDLER sentinel → dispatch to _FIGMA_HANDLERS[figma_name]
    - String template → type-aware formatting via format_js_value
    - Empty/missing emit dict → deferred, skip

    When `node_type` is provided (the Figma Plugin API native type like
    "FRAME", "RECTANGLE", "TEXT"), each property is gated through
    is_capable() before emission. Properties whose capability set excludes
    this node_type are silently skipped — this is the output gate that
    prevents "object is not extensible" runtime errors. Omit node_type
    for permissive emission (used by existing callers and unit tests).

    Returns (lines, token_refs).
    """
    from dd.property_registry import PROPERTIES, HANDLER, is_capable

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

        # Capability gate: if the caller told us the native node type, the
        # registry's capability set is authoritative. Skip silently on
        # mismatch — the same table acts as constrained-decoding grammar
        # for synthetic generation.
        if node_type is not None and not is_capable(
            prop.figma_name, renderer, node_type,
        ):
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
    ckr_built: bool = True,
) -> tuple[str, list[tuple[str, str, str]]]:
    """Generate a figma_execute script from a CompositionSpec.

    Uses three-phase rendering to eliminate Figma Plugin API ordering bugs:

      Phase 1 (Materialize): Create all nodes, set intrinsic properties
        (fills, strokes, effects, font, fontSize, resize for FIXED dims).
        No appendChild — nodes exist independently.

      Phase 2 (Compose): Wire tree (appendChild), set layoutSizing.
        All nodes have dimensions, so auto-layout resolves correctly.
        HUG parents compute width from FIXED children before FILL children
        need to know their container width.

      Phase 3 (Hydrate): Set text characters, position, constraints.
        Text reflows at correct container widths. Position set after all
        children are attached and sized.

    This ordering eliminates the vertical text bug where FILL text children
    appended to HUG parents before FIXED siblings establish width, causing
    text to wrap at ~0px. See compiler-architecture.md.

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

    preamble: list[str] = []

    # Structured error channel — Mode 1 null-guards push structured entries here
    # when a referenced component node can't be resolved (deleted, unpublished,
    # never existed). The runtime harness (render_test/run.js) reads this to
    # distinguish "script aborted on exception" from "script finished with
    # recoverable errors". Downstream verification loops diff the errors array
    # against the IR to fail closed on missing-component regressions.
    #
    # Declared BEFORE the font-load block so the per-font guards have
    # somewhere to push. See TestGuardedFontLoading.
    preamble.append("const __errors = [];")

    # Guarded font loading (ADR-007 Position 2). A single unavailable
    # font — trial/unlicensed fonts like "ABC Diatype Mono Medium
    # Unlicensed Trial" that the Plugin API can't load — must not abort
    # the script. One rejection in the preamble kills every downstream
    # node creation. Each load is wrapped in a try/catch that pushes
    # `{kind:"font_load_failed", family, style, error}` and continues.
    # Unrelated text nodes still render; text nodes using the failed
    # font surface as `text_set_failed` entries at Phase 3 (the existing
    # per-op guards handle that). See tests: TestGuardedFontLoading.
    # Always load Inter Regular — Figma's default font for createText()
    all_fonts = [("Inter", "Regular")] + [f for f in fonts if f != ("Inter", "Regular")]
    for family, style in all_fonts:
        family_js = _escape_js(family)
        style_js = _escape_js(style)
        preamble.append(
            "await (async () => { try { "
            f"await figma.loadFontAsync({{family: \"{family_js}\", style: \"{style_js}\"}}); "
            "} catch (__e) { "
            f"__errors.push({{kind:\"font_load_failed\", family:\"{family_js}\", style:\"{style_js}\", "
            "error: String(__e && __e.message || __e)}); } })();"
        )

    preamble.append("const M = {};")
    # ADR-007 Position 1: if CKR wasn't built for this DB, every INSTANCE
    # downstream will degrade to Mode 2. Push one structured entry so the
    # root cause is visible in the error channel even before the
    # extract-side auto-build has propagated to every deployment.
    if not ckr_built:
        preamble.append(
            '__errors.push({kind:"ckr_unbuilt", '
            'error:"component_key_registry empty or missing — '
            'Mode 1 will degrade to Mode 2 for every INSTANCE node"});'
        )
    # Explicit state harness: capture the harness-pinned currentPage BEFORE any
    # prefetch. figma.getNodeByIdAsync() side-effects figma.currentPage (it
    # flips to the page that hosts the resolved node), so downstream reads of
    # figma.currentPage would leak nodes to the wrong page. We bind _rootPage
    # here and use it everywhere downstream — the script never reads ambient
    # state once prefetch has started. See feedback_figma_api_quirks.md.
    preamble.append("const _rootPage = figma.currentPage;")

    # Placeholder helper is emitted lazily — only when a call site
    # references `_missingComponentPlaceholder` somewhere in the output.
    # Reserve a slot in the preamble so we can inject it later without
    # re-walking and without polluting scripts that never use Mode 1.
    placeholder_slot_index = len(preamble)
    preamble.append("")  # filled at end if _missingComponentPlaceholder appears

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
        preamble.append("// Pre-fetch component nodes (deduplicated, null-safe)")
        # Each lookup is wrapped so a transient Figma backend failure (network
        # timeout "Unable to establish connection") or a deleted component
        # produces a null + structured error instead of aborting the script.
        # Downstream Mode 1 null-guards already handle null component refs.
        node_id_vars: dict[str, str] = {}
        for i, nid in enumerate(sorted(needed_node_ids)):
            var_name = f"_p{i}"
            node_id_vars[nid] = var_name
            id_lit = _escape_js(nid)
            preamble.append(
                f'const {var_name} = await (async () => {{ '
                f'try {{ return await figma.getNodeByIdAsync("{id_lit}"); }} '
                f'catch (__e) {{ __errors.push({{kind:"prefetch_failed", id:"{id_lit}", error: String(__e && __e.message || __e)}}); return null; }} '
                f'}})();'
            )
    else:
        node_id_vars = {}

    preamble.append("")

    # Three output phases
    phase1_lines: list[str] = []  # Materialize: create nodes + intrinsic properties
    phase2_lines: list[str] = []  # Compose: appendChild + layoutSizing
    phase3_lines: list[str] = []  # Hydrate: text.characters + position + constraints

    var_map: dict[str, str] = {}
    mode1_eids: set = set()
    skipped_eids: set = set()
    absolute_eids: set = set()
    # Deferred GROUP creation: children are created first, then grouped.
    # Maps group_eid → {"parent_eid": str, "children_vars": [str], "element": dict}
    group_deferred: dict[str, dict] = {}
    # Text characters collected from Phase 1 walk. These are emitted in
    # Phase 2 immediately after appendChild and BEFORE layoutSizing so
    # HUG text siblings have real content widths when FILL children
    # evaluate their share of remaining space. See
    # test_fill_text_characters_set_before_layoutsizing.
    # Tuple: (var, escaped_text, eid) — eid carried through for the
    # per-op guard (ADR-007 Session B) attribution.
    text_characters: list[tuple[str, str, str]] = []
    # Lookup by eid so the Phase 2 loop can emit characters as it walks.
    text_by_eid: dict[str, tuple[str, str]] = {}
    # Deferred textAutoResize mode (e.g. "HEIGHT"). Emitted in Phase 2
    # AFTER characters + layoutSizing so text sizes to content first,
    # then layoutSizing sets the final width, then HEIGHT locks it.
    # See comment in Phase 1 text branch for the defect this avoids.
    text_autoresize_deferred: dict[str, str] = {}
    # Deferred relativeTransform (for ANY non-identity 2x2 — mirrors AND
    # rotations). Must be set AFTER appendChild:
    # (a) The translation component is parent-relative; Figma recomputes
    #     it on appendChild to preserve world-space position.
    # (b) Setting .rotation + .x + .y on the Plugin API writes the
    #     transform's translation column, NOT the AABB corner. The DB
    #     stores parent-relative coords assuming identity-rotation parents,
    #     which is wrong for any rotated ancestor chain.
    # Emitting the full matrix after wiring sidesteps both.
    deferred_transform_by_eid: dict[str, tuple[str, list]] = {}

    # -----------------------------------------------------------------------
    # Phase 1: Materialize — create all nodes with intrinsic properties
    # -----------------------------------------------------------------------
    phase1_lines.append("// Phase 1: Materialize — create nodes, set intrinsic properties")

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

        db_node_type = raw_visual.get("node_type") if (db_visuals is not None and raw_visual) else None
        is_db_instance = db_node_type == "INSTANCE"

        # Mode 1 fallback chain:
        #   1. component_figma_id (from registry) → getNodeByIdAsync → createInstance
        #   2. instance figma_node_id (from DB, INSTANCE node) → getMainComponentAsync → createInstance
        #      (handles unpublished/local components that importComponentByKeyAsync rejects;
        #       also covers fresh DBs where CKR hasn't been built yet)
        #   3. Fall through to Mode 2 (createFrame) if no usable ID
        #
        # ADR-007 Session A: the gate now also reaches path 2 when only
        # `instance_figma_node_id` + `node_type='INSTANCE'` are populated.
        # Before Session A, the `elif instance_figma_node_id:` branch at
        # ~line 851 was unreachable because the gate required component_key
        # or component_figma_id.
        use_mode1 = (
            (component_key or component_figma_id
             or (is_db_instance and instance_figma_node_id))
            and not is_text
        )
        if use_mode1:
            # Mode 1 null-safety contract: every createInstance() call sits
            # behind an async guard that records missing-node failures in
            # __errors and falls back to a wireframe placeholder. This
            # prevents one deleted/unpublished component from aborting the
            # entire script with "cannot read property 'x' of null", AND
            # makes the missing component visually obvious (black-stroked
            # frame with X diagonals at the instance's dimensions) instead
            # of a blank white frame that looks like intended output.
            eid_lit = _escape_js(eid)
            # Dimensions for the placeholder — pull from IR sizing if known
            sizing = element.get("layout", {}).get("sizing", {})
            pw = sizing.get("widthPixels") or sizing.get("width")
            ph = sizing.get("heightPixels") or sizing.get("height")
            pw_js = pw if isinstance(pw, (int, float)) else 24
            ph_js = ph if isinstance(ph, (int, float)) else 24
            name_for_placeholder = element.get("_original_name", eid)
            name_lit = _escape_js(name_for_placeholder)
            fallback_js = (
                f'_missingComponentPlaceholder("{name_lit}", {pw_js}, {ph_js}, "{eid_lit}")'
            )
            if component_figma_id:
                node_expr = node_id_vars.get(
                    component_figma_id,
                    f'await figma.getNodeByIdAsync("{_escape_js(component_figma_id)}")',
                )
                id_lit = _escape_js(component_figma_id)
                phase1_lines.append(
                    f'const {var} = await (async () => {{ '
                    f'const __src = {node_expr}; '
                    f'if (!__src) {{ __errors.push({{eid:"{eid_lit}", kind:"missing_component_node", id:"{id_lit}"}}); return {fallback_js}; }} '
                    f'try {{ return __src.createInstance(); }} '
                    f'catch (__e) {{ __errors.push({{eid:"{eid_lit}", kind:"create_instance_failed", id:"{id_lit}", error: String(__e && __e.message || __e)}}); return {fallback_js}; }} '
                    f'}})();'
                )
            elif instance_figma_node_id:
                id_lit = _escape_js(instance_figma_node_id)
                phase1_lines.append(
                    f'const {var} = await (async () => {{ '
                    f'const __src = await figma.getNodeByIdAsync("{id_lit}"); '
                    f'if (!__src) {{ __errors.push({{eid:"{eid_lit}", kind:"missing_instance_node", id:"{id_lit}"}}); return {fallback_js}; }} '
                    f'if (typeof __src.getMainComponentAsync !== "function") {{ __errors.push({{eid:"{eid_lit}", kind:"not_an_instance", id:"{id_lit}"}}); return {fallback_js}; }} '
                    f'const __master = await __src.getMainComponentAsync(); '
                    f'if (!__master) {{ __errors.push({{eid:"{eid_lit}", kind:"no_main_component", id:"{id_lit}"}}); return {fallback_js}; }} '
                    f'try {{ return __master.createInstance(); }} '
                    f'catch (__e) {{ __errors.push({{eid:"{eid_lit}", kind:"create_instance_failed", id:"{id_lit}", error: String(__e && __e.message || __e)}}); return {fallback_js}; }} '
                    f'}})();'
                )
            else:
                use_mode1 = False

        if use_mode1:
            original_name = element.get("_original_name", eid)
            phase1_lines.append(f'{var}.name = "{_escape_js(original_name)}";')

            props = element.get("props", {})
            text_override = props.get("text", "")
            if text_override:
                text_target = props.get("text_target")
                find_expr = _build_text_finder(var, text_target)
                # Mode 1 text overrides go to Phase 1 — the instance already
                # has correct layout structure from the master component.
                phase1_lines.append(
                    f'{{ const _t = {find_expr}; '
                    f'if (_t) {{ await figma.loadFontAsync(_t.fontName); '
                    f'_t.characters = "{_escape_js(text_override)}"; }} }}'
                )

            subtitle_override = props.get("subtitle", "")
            if subtitle_override:
                sub_find = _build_text_finder(var, None, subtitle=True)
                phase1_lines.append(
                    f'{{ const _t = {sub_find}; '
                    f'if (_t) {{ await figma.loadFontAsync(_t.fontName); '
                    f'_t.characters = "{_escape_js(subtitle_override)}"; }} }}'
                )

            hidden_children = raw_visual.get("hidden_children", []) if (db_visuals is not None and raw_visual) else []
            for hc in hidden_children:
                hname = _escape_js(hc["name"])
                phase1_lines.append(
                    f'{{ const _h = {var}.findOne(n => n.name === "{hname}"); '
                    f"if (_h) _h.visible = false; }}"
                )

            # Instance overrides via override tree. The tree encodes
            # dependency ordering: pre-order traversal ensures swaps
            # happen before property overrides on swapped descendants.
            override_tree = raw_visual.get("override_tree") if (db_visuals is not None and raw_visual) else None
            if override_tree:
                _emit_override_tree(override_tree, var, node_id_vars, phase1_lines, phase3_lines)

            # L0 visual properties on the instance itself (rotation, opacity).
            # These differ from the master's defaults but aren't captured as
            # instance_overrides — they're direct properties on the DB node.
            if db_visuals is not None and raw_visual:
                inst_rotation = raw_visual.get("rotation")
                if inst_rotation is not None and inst_rotation != 0:
                    phase1_lines.append(f"{var}.rotation = {-math.degrees(inst_rotation)};")
                inst_opacity = raw_visual.get("opacity")
                if inst_opacity is not None and inst_opacity < 1.0:
                    phase1_lines.append(f"{var}.opacity = {inst_opacity};")

            # Instance's own visibility (e.g., hidden keyboard overlay)
            if element.get("visible") is False:
                phase1_lines.append(f"{var}.visible = false;")

            mode1_eids.add(eid)
        else:
            # Mode 2: create from L0 properties

            # ADR-007 Position 1: silent INSTANCE→FRAME substitution is a
            # codegen-time degradation. If the DB says this node is an
            # INSTANCE but we reached Mode 2, record a structured
            # __errors entry so the loss is visible in the error channel.
            # Without this push, a fresh DB without CKR + supplement
            # silently turns every component instance into an empty
            # createFrame() (see screen 175 case study in ADR-007).
            if is_db_instance:
                eid_lit = _escape_js(eid)
                reason_parts: list[str] = []
                if not component_key:
                    reason_parts.append("no component_key")
                if not component_figma_id:
                    reason_parts.append("no component_figma_id")
                if not instance_figma_node_id:
                    reason_parts.append("no instance_figma_node_id")
                reason = _escape_js(", ".join(reason_parts) or "unknown")
                phase1_lines.append(
                    f'__errors.push({{eid:"{eid_lit}", '
                    f'kind:"degraded_to_mode2", reason:"{reason}"}});'
                )

            # GROUP: defer creation — figma.group() requires children to exist first.
            # Children will be appended to the grandparent temporarily, then
            # wrapped into a GROUP in Phase 2.
            if etype == "group":
                group_deferred[eid] = {
                    "parent_eid": parent_eid,
                    "children_vars": [],
                    "element": element,
                }
                continue

            # Check for asset-backed vector data (SVG paths)
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

            if is_text:
                phase1_lines.append(f"const {var} = figma.createText();")
            elif etype in _NODE_CREATE_MAP:
                phase1_lines.append(f"const {var} = {_NODE_CREATE_MAP[etype]};")
            else:
                phase1_lines.append(f"const {var} = figma.createFrame();")

            original_name = element.get("_original_name", eid)
            phase1_lines.append(f'{var}.name = "{_escape_js(original_name)}";')

            text_resize_for_layout: str | None = None
            if is_text:
                # Determine the DB's desired final textAutoResize mode.
                # Emission is DEFERRED to Phase 2 (after appendChild +
                # characters + layoutSizing) because setting HEIGHT
                # mode while the text is still empty locks the width
                # at 0, and subsequent .characters would wrap at 0
                # regardless of later layoutSizing. By holding at the
                # default WIDTH_AND_HEIGHT through Phase 1, characters
                # set the content-driven width before any locking
                # happens.
                text_resize = "WIDTH_AND_HEIGHT"
                if db_visuals is not None:
                    node_id = spec.get("_node_id_map", {}).get(eid)
                    text_visual = db_visuals.get(node_id, {}) if node_id else {}
                    stored = text_visual.get("text_auto_resize")
                    if stored:
                        text_resize = stored
                text_resize_for_layout = text_resize
                # Remember the DB value for Phase 2 to apply after
                # characters + layoutSizing.
                if text_resize != "WIDTH_AND_HEIGHT":
                    text_autoresize_deferred[eid] = text_resize

            layout = element.get("layout", {})
            layout_lines, layout_refs = _emit_layout(
                var, eid, layout, tokens,
                text_auto_resize=text_resize_for_layout,
                etype=etype,
            )
            phase1_lines.extend(layout_lines)
            all_token_refs.extend(layout_refs)

            if db_visuals is not None:
                node_id = spec.get("_node_id_map", {}).get(eid)
                raw_visual = db_visuals.get(node_id, {}) if node_id else {}
                visual = build_visual_from_db(raw_visual)
            else:
                raw_visual = {}
                visual = {}

            # ADR-008 Mode-3: overlay IR `element.style` fill / stroke /
            # radius into `visual` when the DB path produced no visual
            # for this eid. Synthetic IR elements never have a DB node
            # id, so without this overlay their template-supplied fills
            # are silently dropped and the frame renders with the
            # default `fills = []` clearing below.
            # Text nodes also get the overlay — text color in Figma is
            # expressed as a fills paint.
            ir_style = element.get("style", {}) or {}
            fill_ref = ir_style.get("fill")
            if fill_ref and not visual.get("fills"):
                resolved, _tok = resolve_style_value(fill_ref, tokens)
                if isinstance(resolved, str) and resolved.startswith("#"):
                    visual["fills"] = [{"type": "solid", "color": resolved}]
            if not is_text:
                stroke_ref = ir_style.get("stroke")
                if stroke_ref and not visual.get("strokes"):
                    resolved, _tok = resolve_style_value(stroke_ref, tokens)
                    if isinstance(resolved, str) and resolved.startswith("#"):
                        visual["strokes"] = [{"type": "solid", "color": resolved}]
                radius_ref = ir_style.get("radius")
                if radius_ref is not None and "cornerRadius" not in visual:
                    resolved, _tok = resolve_style_value(radius_ref, tokens)
                    if isinstance(resolved, (int, float)):
                        visual["cornerRadius"] = resolved
                # ADR-008 v0.1.5 H2: shadow overlay. PresentationTemplate
                # expresses shadow as an elevation number (`{shadow.card}`
                # → e.g. 2); we synthesize a drop-shadow at that y-offset
                # + 2× blur at 10 % opacity. An elevation of 0 skips —
                # some templates declare the token but the resolved
                # value is 0 (e.g. flat paywall cards).
                shadow_ref = ir_style.get("shadow")
                if shadow_ref is not None and "effects" not in visual:
                    resolved, _tok = resolve_style_value(shadow_ref, tokens)
                    if isinstance(resolved, (int, float)) and resolved > 0:
                        elev = int(resolved)
                        visual["effects"] = [{
                            "type": "drop-shadow",
                            "color": "#0000001A",
                            "offset": {"x": 0, "y": elev},
                            "blur": elev * 2,
                            "spread": 0,
                        }]

            # Transform detection: when relative_transform is available
            # and its 2x2 submatrix is non-identity (any rotation OR
            # mirror), defer relativeTransform emission to Phase 3.
            # Covers both:
            #   - Mirrors (det = -1): .rotation can't represent them
            #   - Pure rotations (det = +1, 2x2 ≠ identity): .rotation +
            #     .x/.y is ambiguous about pivot and produces wrong AABB
            # See deferred_transform_by_eid declaration for full details.
            rt_json = raw_visual.get("relative_transform")
            if rt_json:
                rt = json.loads(rt_json) if isinstance(rt_json, str) else rt_json
                if isinstance(rt, list) and len(rt) == 2:
                    # 2x2 is identity iff [a,b,c,d] ≈ [1,0,0,1]
                    m00, m01 = rt[0][0], rt[0][1]
                    m10, m11 = rt[1][0], rt[1][1]
                    is_identity = (
                        abs(m00 - 1) < 1e-9 and abs(m01) < 1e-9
                        and abs(m10) < 1e-9 and abs(m11 - 1) < 1e-9
                    )
                    if not is_identity:
                        visual.pop("rotation", None)
                        deferred_transform_by_eid[eid] = (var, rt)

            figma_type = ir_to_figma_type(etype)
            visual_lines, visual_refs = _emit_visual(
                var, eid, visual, tokens, node_type=figma_type,
            )
            phase1_lines.extend(visual_lines)
            all_token_refs.extend(visual_refs)

            # Emit vector paths for asset-backed vector nodes
            if has_vector_asset:
                _emit_vector_paths(var, raw_visual, phase1_lines)

            # Clear default fills on nodes that should be transparent.
            # All Figma creation calls (createFrame, createRectangle,
            # createEllipse, createVector, etc.) produce a default white fill.
            # If the DB has no visible fills, the original was transparent.
            if not is_text and not visual.get("fills"):
                phase1_lines.append(f"{var}.fills = [];")

            # Clear default strokes on path-based nodes (VECTOR, LINE).
            # figma.createVector() and figma.createLine() ship with a
            # default 1px black SOLID stroke so newly-created nodes are
            # visible. When the DB has no visible strokes, the original
            # was stroke-less — emit strokes=[] to match. Symmetric with
            # the fills=[] clearing above. Bounded shapes (RECTANGLE,
            # ELLIPSE, etc.) default to strokes=[] already, no clearing
            # needed there.
            if figma_type in ("VECTOR", "LINE") and not visual.get("strokes"):
                phase1_lines.append(f"{var}.strokes = [];")

            # Clear default clipsContent on frames. createFrame() defaults
            # to clipsContent=true. When the DB has no value (NULL), emit
            # clipsContent=false as the safer default — unexpected clipping
            # is more visually destructive than missing clipping.
            #
            # Gate through the registry's capability table: clipsContent is
            # only legal on container types (FRAME/COMPONENT/INSTANCE/SECTION).
            # is_capable() is the single source of truth — no ad-hoc gates.
            from dd.property_registry import is_capable as _is_capable
            if (
                _is_capable("clipsContent", "figma", figma_type)
                and not visual.get("clipsContent")
            ):
                phase1_lines.append(f"{var}.clipsContent = false;")

            if element.get("visible") is False:
                phase1_lines.append(f"{var}.visible = false;")

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
                _emit_text_props(var, element, style, tokens, phase1_lines, db_font=db_font, eid=eid)

                # Collect text characters for Phase 3 (Hydrate).
                # Text content is set after appendChild so it reflows
                # at the correct container width.
                text_content = element.get("props", {}).get("text", "")
                if text_content:
                    escaped = _escape_js(text_content)
                    text_characters.append((var, escaped, eid))
                    text_by_eid[eid] = (var, escaped)

            composition = element.get("_composition")
            has_ir_children = bool(element.get("children"))
            if composition and not is_text and not has_ir_children:
                _emit_composition_children(var, eid, composition, phase1_lines, idx * 100)

            elem_direction = element.get("layout", {}).get("direction", "")
            if elem_direction == "absolute":
                absolute_eids.add(eid)

        phase1_lines.append(f'M["{_escape_js(eid)}"] = {var}.id;')
        phase1_lines.append("")

    # -----------------------------------------------------------------------
    # Phase 2: Compose — wire tree (appendChild), set layoutSizing
    # -----------------------------------------------------------------------
    phase2_lines.append("")
    phase2_lines.append("// Phase 2: Compose — wire tree, set layoutSizing")
    phase2_lines.append("await new Promise(r => setTimeout(r, 0));")
    phase2_lines.append("")

    for _idx, (eid, element, parent_eid) in enumerate(walk_order):
        if eid in skipped_eids or eid in group_deferred:
            continue
        if eid not in var_map:
            continue

        var = var_map[eid]
        etype = element.get("type", "")
        is_text = etype in _TEXT_TYPES

        # Resolve parent: if parent is a deferred GROUP, append to grandparent
        resolved_parent_eid = parent_eid
        while resolved_parent_eid in group_deferred:
            # Track this child for the deferred group
            group_deferred[resolved_parent_eid]["children_vars"].append(var)
            resolved_parent_eid = group_deferred[resolved_parent_eid]["parent_eid"]

        if resolved_parent_eid is None or resolved_parent_eid not in var_map or resolved_parent_eid in mode1_eids:
            continue

        # Guard against LEAF_TYPE_APPEND: Mode 3 composition can produce
        # parent-child pairs where the parent is a Figma leaf (TEXT, LINE,
        # RECTANGLE, etc.) that has no `.appendChild` method. Emitting
        # `parent.appendChild(child)` then throws "not a function" which
        # aborts the whole Phase 2 before `_rootPage.appendChild(n0)` lands,
        # ORPHANING the entire tree and making walk_ref see only the root.
        # Observed on 00i breadth test: 12-signup-form + 13-password-reset +
        # 14-2fa-verify all flip to rule-gate broken via this path, and the
        # empty-text_input visual defect is downstream (orphaned tree).
        # Fix: skip the append silently and record a diagnostic so the
        # caller can audit. The round-trip path never hits this because its
        # IR is DB-extracted where leaf types don't have children.
        parent_etype = spec.get("elements", {}).get(resolved_parent_eid, {}).get("type", "")
        if parent_etype in _LEAF_TYPES:
            phase2_lines.append(
                f'// leaf_type_append skipped: parent={resolved_parent_eid!r} '
                f'({parent_etype!r}) cannot accept child {eid!r} ({etype!r})'
            )
            phase2_lines.append(
                f'__errors.push({{kind:"leaf_type_append_skipped", '
                f'parent_eid:"{_escape_js(resolved_parent_eid)}", '
                f'parent_type:"{parent_etype}", child_eid:"{_escape_js(eid)}", '
                f'child_type:"{etype}"}});'
            )
            continue

        parent_var = var_map[resolved_parent_eid]
        phase2_lines.append(f"{parent_var}.appendChild({var});")

        # ADR-007 follow-up: emit text .characters BEFORE layoutSizing.
        # A later FILL sibling evaluating its share of remaining space
        # needs HUG text siblings to have their real content widths.
        # Leaving .characters to Phase 3 made HUG siblings measure as
        # 0 wide at layoutSizing time, causing FILL to lock the width
        # incorrectly and wrap to "M/o/r/e"-style columns.
        if eid in text_by_eid:
            _var, _text = text_by_eid[eid]
            # OpenType feature substitution: Figma's Plugin API has
            # getRangeOpenTypeFeatures but NO setRangeOpenTypeFeatures —
            # per-range features can't be applied programmatically. For
            # specific well-known substitutions (e.g. SUPS "0" renders as
            # degree symbol in Inter), we replace the underlying character
            # with the Unicode equivalent so the visual matches without
            # needing the OpenType feature.
            if db_visuals is not None:
                _nid = spec.get("_node_id_map", {}).get(eid)
                _nv = db_visuals.get(_nid, {}) if _nid else {}
                ot_json = _nv.get("opentype_features")
                if ot_json:
                    ot_segs = json.loads(ot_json) if isinstance(ot_json, str) else ot_json
                    if isinstance(ot_segs, list):
                        _text = _apply_opentype_substitution(_text, ot_segs)
            phase2_lines.append(_guarded_op(
                f'{_var}.characters = "{_text}";',
                eid, "text_set_failed",
            ))

        parent_direction = spec.get("elements", {}).get(resolved_parent_eid, {}).get("layout", {}).get("direction", "")
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
                phase2_lines.append(f'{var}.layoutSizingHorizontal = "{figma_h}";')
            if sizing_v:
                figma_v = _SIZING_MAP.get(sizing_v, sizing_v.upper())
                phase2_lines.append(f'{var}.layoutSizingVertical = "{figma_v}";')
            # Now that the text has content + layoutSizing-determined
            # width, apply the DB's textAutoResize mode (e.g. "HEIGHT")
            # to lock the width. Doing this earlier would have locked
            # at 0 before .characters = ... ran.
            if eid in text_autoresize_deferred:
                mode = text_autoresize_deferred[eid]
                phase2_lines.append(f'{var}.textAutoResize = "{mode}";')
        else:
            # Non-auto-layout parent: use pixel dimensions for resize
            # and position. layoutSizing is irrelevant here — the node's
            # size comes from explicit dimensions, not parent negotiation.
            elem_sizing = element.get("layout", {}).get("sizing", {})
            pw = elem_sizing.get("widthPixels")
            ph = elem_sizing.get("heightPixels")
            if pw is not None and ph is not None:
                phase3_lines.append(_guarded_op(
                    f"{var}.resize({round(pw, 2)}, {round(ph, 2)});", eid, "resize_failed",
                ))
            elif pw is not None:
                phase3_lines.append(_guarded_op(
                    f"{var}.resize({round(pw, 2)}, {var}.height);", eid, "resize_failed",
                ))
            elif ph is not None:
                phase3_lines.append(_guarded_op(
                    f"{var}.resize({var}.width, {round(ph, 2)});", eid, "resize_failed",
                ))
            # Skip .x/.y when a full relativeTransform will be emitted
            # below — the matrix includes translation, and scalar .x/.y
            # setters write the SAME translation column, which is then
            # overwritten. Emit one or the other, never both.
            position = element.get("layout", {}).get("position")
            if position and eid not in deferred_transform_by_eid:
                phase3_lines.append(_guarded_op(
                    f"{var}.x = {position.get('x', 0)};", eid, "position_failed",
                ))
                phase3_lines.append(_guarded_op(
                    f"{var}.y = {position.get('y', 0)};", eid, "position_failed",
                ))

        # Deferred transforms: emit relativeTransform AFTER appendChild and
        # (suppressed) position. Covers both mirrors and pure rotations.
        # The Plugin API's relativeTransform is parent-relative; setting
        # it here ensures the parent is already wired so the translation
        # component isn't recomputed. Replaces scalar rotation + x/y
        # emission which is broken for rotated nodes.
        if eid in deferred_transform_by_eid:
            _var, _rt = deferred_transform_by_eid[eid]
            phase3_lines.append(_guarded_op(
                f"{_var}.relativeTransform = "
                f"[[{_rt[0][0]},{_rt[0][1]},{_rt[0][2]}],"
                f"[{_rt[1][0]},{_rt[1][1]},{_rt[1][2]}]];",
                eid, "position_failed",
            ))

        # Constraints deferred to Phase 3 (after position)
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
                phase3_lines.append(_guarded_op(
                    f"{var}.constraints = {{{', '.join(parts)}}};",
                    eid, "constraint_failed",
                ))

    # Root element → page
    if root_id in var_map:
        if page_name:
            escaped_name = _escape_js(page_name)
            phase2_lines.append(
                f'let _page = figma.root.children.find(p => p.type === "PAGE" && p.name === "{escaped_name}");'
            )
            phase2_lines.append(f"if (!_page) {{ _page = figma.createPage(); _page.name = \"{escaped_name}\"; }}")
            phase2_lines.append(f"_page.appendChild({var_map[root_id]});")
            phase2_lines.append(f"await figma.setCurrentPageAsync(_page);")
        else:
            phase2_lines.append(f"_rootPage.appendChild({var_map[root_id]});")

        if canvas_position is not None:
            cx, cy = canvas_position
            phase2_lines.append(f"{var_map[root_id]}.x = {cx};")
            phase2_lines.append(f"{var_map[root_id]}.y = {cy};")

    # Emit deferred GROUP creation — inner groups first (reverse BFS order)
    for group_eid in reversed(list(group_deferred)):
        ginfo = group_deferred[group_eid]
        children_vars = ginfo["children_vars"]
        gp_eid = ginfo["parent_eid"]
        while gp_eid in group_deferred:
            gp_eid = group_deferred[gp_eid]["parent_eid"]
        gp_var = var_map.get(gp_eid, var_map.get(root_id, "_rootPage"))
        group_element = ginfo["element"]
        original_name = group_element.get("_original_name", group_eid)
        gvar = f"g{group_eid.replace('-', '_')}"

        if children_vars:
            children_str = ", ".join(children_vars)
            phase2_lines.append(f"const {gvar} = figma.group([{children_str}], {gp_var});")
        else:
            # Empty group — create a frame as placeholder (can't group zero nodes)
            phase2_lines.append(f"const {gvar} = figma.createFrame();")
            phase2_lines.append(f"{gp_var}.appendChild({gvar});")

        # Z-order: figma.group() always appends the new group at the END
        # of its parent's children. For groups that aren't the last
        # sibling (common: illustration groups sitting mid-stack under
        # overlays/chrome), this moves them on top of everything. Fix:
        # insertChild the group at its intended sort_order. We compute
        # this from the parent element's children list in the IR.
        gp_element = spec.get("elements", {}).get(gp_eid)
        if gp_element is not None:
            gp_children = gp_element.get("children") or []
            if group_eid in gp_children:
                target_idx = gp_children.index(group_eid)
                if target_idx != len(gp_children) - 1:
                    phase2_lines.append(_guarded_op(
                        f"{gp_var}.insertChild({target_idx}, {gvar});",
                        group_eid, "position_failed",
                    ))

        phase2_lines.append(f'{gvar}.name = "{_escape_js(original_name)}";')
        var_map[group_eid] = gvar
        phase2_lines.append(f'M["{_escape_js(group_eid)}"] = {gvar}.id;')

        # Group position + constraints deferred to Phase 3
        position = group_element.get("layout", {}).get("position")
        if position:
            phase3_lines.append(_guarded_op(
                f"{gvar}.x = {position.get('x', 0)};", group_eid, "position_failed",
            ))
            phase3_lines.append(_guarded_op(
                f"{gvar}.y = {position.get('y', 0)};", group_eid, "position_failed",
            ))
        if db_visuals is not None:
            node_id = spec.get("_node_id_map", {}).get(group_eid)
            constraint_visual = db_visuals.get(node_id, {}) if node_id else {}
            c_h = constraint_visual.get("constraint_h")
            c_v = constraint_visual.get("constraint_v")
            # ADR-001 capability gate: GROUP does not support .constraints
            # in the Figma Plugin API. Without this gate, emission throws
            # "object is not extensible" at runtime and Session B's
            # micro-guard records a spurious constraint_failed entry on
            # every render. The property_registry's capability set for
            # constraint_h/v already excludes GROUP — consult it here too.
            from dd.property_registry import is_capable
            allow_constraints = is_capable("constraint_h", "figma", "GROUP")
            if (c_h or c_v) and allow_constraints:
                parts = []
                if c_h:
                    mapped = _CONSTRAINT_MAP.get(c_h, c_h)
                    parts.append(f'horizontal: "{mapped}"')
                if c_v:
                    mapped = _CONSTRAINT_MAP.get(c_v, c_v)
                    parts.append(f'vertical: "{mapped}"')
                phase3_lines.append(_guarded_op(
                    f"{gvar}.constraints = {{{', '.join(parts)}}};",
                    group_eid, "constraint_failed",
                ))

        phase2_lines.append("")

    # -----------------------------------------------------------------------
    # Phase 3: Hydrate — dimensions, position, text content
    # -----------------------------------------------------------------------
    hydrate_ops: list[str] = []

    # Resize + position first: non-auto-layout children get their pixel
    # dimensions here. This must precede text characters because FILL text
    # descendants need ancestor widths established before content is set.
    # Without this ordering, textAutoResize=HEIGHT wraps at 0px width.
    hydrate_ops.extend(phase3_lines)

    # Text characters are now emitted in Phase 2 (after appendChild,
    # before layoutSizing) so HUG siblings have real content widths
    # when FILL children resolve. No Phase 3 emission needed; the
    # Phase 3 block only holds deferred position/constraint ops.

    # ADR-007 outer guard: script-level throws (e.g. Plugin API rejecting
    # an illegal property on a node type that doesn't accept it) bypass
    # the per-op micro-guards entirely and reach the runtime harness as
    # a raw exception — producing zero KIND_* entries despite a failed
    # render. Wrap Phases 1-3 in one try/catch so script-level throws
    # capture into __errors as `render_thrown` before we return the
    # partially-built M. The catch DOES NOT re-raise — the harness uses
    # __errors to distinguish "clean run" from "lossy run"; a raw
    # exception would lose everything __errors had accumulated.
    #
    # Scoping: const declarations in Phase 1 bind inside the try block,
    # but Phases 2 and 3 reference them, so all three phases must live
    # in the SAME try. Indentation is kept flat — valid JS, matches the
    # rest of the generator's output style.
    lines: list[str] = list(preamble)
    lines.append("")
    lines.append("try {")
    lines.extend(phase1_lines)
    lines.extend(phase2_lines)

    if hydrate_ops:
        lines.append("")
        lines.append("// Phase 3: Hydrate — text content, position, constraints")
        lines.append("await new Promise(r => setTimeout(r, 0));")
        lines.append("")
        # ADR-007 Session B: each op carries its own inline try/catch
        # (see _guarded_op). The inner per-op guards catch per-property
        # failures; the outer try catches script-level throws that bypass
        # those guards (e.g. unsupported property setters, syntax-level
        # issues in emitted JS).
        for op in hydrate_ops:
            lines.append(op)

    lines.append("} catch (__thrown) {")
    lines.append(
        '  __errors.push({kind: "render_thrown", '
        'error: String(__thrown && __thrown.message || __thrown), '
        'stack: (__thrown && __thrown.stack) ? '
        'String(__thrown.stack).split("\\n").slice(0, 6).join(" | ") : null});'
    )
    lines.append("}")

    # Expose structured error channel on the return payload so the harness
    # can distinguish "script finished with recoverable errors" from a raw
    # exception. Empty array means clean run.
    lines.append('M["__errors"] = __errors;')
    lines.append("return M;")

    # Inject the missing-component placeholder helper only if any emitted
    # code path actually references it. This keeps scripts without Mode 1
    # or instance_swap emissions free of the helper's "rotation" and
    # "appendChild" keywords that static tests search for.
    uses_placeholder = any("_missingComponentPlaceholder" in ln for ln in lines)
    if uses_placeholder:
        preamble[placeholder_slot_index] = MISSING_COMPONENT_PLACEHOLDER_BLOCK
        # Rebuild the combined script with the updated preamble
        lines = preamble + lines[len(preamble):]

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
    text_auto_resize: str | None = None,
    etype: str | None = None,
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit layout-related JS for a node.

    ``text_auto_resize`` carries the DB's textAutoResize for TEXT nodes
    so we can skip `resize()` when the node is in WIDTH_AND_HEIGHT mode
    — in that mode content determines size, and calling `resize()` has
    the Plugin API side effect of flipping autoResize to HEIGHT,
    locking the width and causing subsequent `.characters` to wrap at
    the locked width.

    ``etype`` is the element's type (e.g. "text", "frame", "card",
    "rectangle"). When it maps to a leaf Figma node type (TEXT,
    RECTANGLE, ELLIPSE, VECTOR, LINE, BOOLEAN_OPERATION, GROUP), the
    auto-layout-only properties (layoutMode, itemSpacing, padding*,
    primaryAxisAlign*, counterAxisAlign*) are skipped entirely —
    setting them is rejected by the Plugin API with "object is not
    extensible". The resize() path still runs for leaf types since
    width/height are universally supported.

    When etype is None (legacy callers) we emit all properties; extracted
    IR never has layout.direction set on leaf nodes so this preserves
    existing behaviour for the extraction path. Synthetic-generation
    callers must pass etype to get the gate.
    """
    lines: list[str] = []
    refs: list[tuple[str, str, str]] = []

    is_leaf = etype in _LEAF_TYPES if etype is not None else False

    if not is_leaf:
        direction = layout.get("direction", "")
        figma_dir = _DIRECTION_MAP.get(direction)
        if figma_dir:
            lines.append(f'{var}.layoutMode = "{figma_dir}";')

        wrap = layout.get("wrap")
        if wrap and wrap != "NO_WRAP":
            lines.append(f'{var}.layoutWrap = "{wrap}";')

        gap_val = layout.get("gap")
        if gap_val is not None:
            resolved, token_name = resolve_style_value(gap_val, tokens)
            if resolved is not None:
                lines.append(f"{var}.itemSpacing = {resolved};")
            if token_name:
                refs.append((eid, "itemSpacing", token_name))

        cas_val = layout.get("counterAxisGap")
        if cas_val is not None:
            resolved, token_name = resolve_style_value(cas_val, tokens)
            if resolved is not None:
                lines.append(f"{var}.counterAxisSpacing = {resolved};")
            if token_name:
                refs.append((eid, "counterAxisSpacing", token_name))

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
    # layoutSizing is NOT emitted here. It's a parent-context-dependent
    # property (like CSS flex-grow) — only meaningful when the node's parent
    # has auto-layout. The renderer emits it post-appendChild when parent
    # context is known. See feedback_sizing_emit_at_lowering.md.

    w = sizing.get("width")
    h = sizing.get("height")
    # Always emit resize() with ground-truth pixel dimensions — even for
    # semantic sizing (HUG/FILL). The pixel dims act as a SEED:
    # - For HUG: if Figma's HUG recompute triggers, it overrides the seed.
    #   If it doesn't (e.g. empty or only-invisible children), the seed
    #   preserves the source dimensions instead of the createFrame() default.
    # - For FILL: parent-context sizing will override once layoutSizing
    #   is applied post-appendChild, but the seed prevents mid-render
    #   width=0 artifacts.
    # - For pixel: this is the only source of truth, no override needed.
    # Architecturally: the IR's widthPixels/heightPixels ARE the ground
    # truth dimensions. Semantic sizing is a layout hint, not a size source.
    rw = round(w, 2) if isinstance(w, (int, float)) else None
    rh = round(h, 2) if isinstance(h, (int, float)) else None
    # Fall back to widthPixels/heightPixels when width/height is semantic
    if rw is None:
        pw = sizing.get("widthPixels")
        if isinstance(pw, (int, float)):
            rw = round(pw, 2)
    if rh is None:
        ph = sizing.get("heightPixels")
        if isinstance(ph, (int, float)):
            rh = round(ph, 2)
    # Text-node guard: in WIDTH_AND_HEIGHT auto-resize mode, the node's
    # size is derived from content. Calling resize() has the Plugin API
    # side effect of flipping autoResize to HEIGHT, which locks the
    # width; the subsequent Phase 3 `.characters = ...` then wraps at
    # that locked width, producing visible "Commun / ity" multiline
    # breakage. Skip resize entirely when the DB says WIDTH_AND_HEIGHT.
    if text_auto_resize == "WIDTH_AND_HEIGHT":
        rw = None
        rh = None
    if rw is not None and rh is not None:
        lines.append(f"{var}.resize({rw}, {rh});")
    elif rw is not None:
        lines.append(f"{var}.resize({rw}, {var}.height);")
    elif rh is not None:
        lines.append(f"{var}.resize({var}.width, {rh});")

    if not is_leaf:
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
    node_type: str | None = None,
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Emit Figma JS for all visual properties, driven by the registry.

    Delegates entirely to emit_from_registry which dispatches HANDLER
    properties (fills, strokes, effects, cornerRadius, clipsContent) to
    their handler functions and formats template properties via
    format_js_value.

    When `node_type` is provided, emission is gated through the registry's
    capability table — properties not supported on that node type are
    silently skipped. This prevents 'object is not extensible' runtime
    errors from layout / clipsContent / text properties landing on wrong
    native node types.
    """
    return emit_from_registry(
        var, eid, visual, tokens, renderer="figma", node_type=node_type,
    )


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
    """Emit vectorPaths assignment from asset ref SVG data.

    Priority: structured `svg_paths` (array of {windingRule, data})
    over legacy `svg_data` (concatenated string, single winding).
    Structured form preserves per-path windingRule — critical for
    windingRule="NONE" stroke-only vectors whose fill would otherwise
    render as a filled polygon of the expanded-stroke outline.
    """
    asset_refs = raw_visual.get("_asset_refs", [])
    structured_paths: list[dict[str, Any]] = []
    legacy_svg_data: list[str] = []

    for ref in asset_refs:
        if ref.get("kind") not in ("svg_path", "svg_doc"):
            continue
        sp = ref.get("svg_paths")
        if isinstance(sp, list) and sp:
            structured_paths.extend(sp)
        elif ref.get("svg_data"):
            legacy_svg_data.append(ref["svg_data"])

    if structured_paths:
        # Preserve per-path windingRule. "NONE" is a first-class value
        # meaning "this path has no fillable regions" — the Figma Plugin
        # API respects it and won't fill the path even if fills are set.
        path_entries = ", ".join(
            f'{{windingRule: "{p.get("windingRule", "NONZERO")}", '
            f'data: "{_escape_js(p.get("data", ""))}"}}'
            for p in structured_paths
        )
        lines.append(f"{var}.vectorPaths = [{path_entries}];")
    elif legacy_svg_data:
        # Backward compat for pre-supplement data: single winding assumed
        path_entries = ", ".join(
            f'{{windingRule: "NONZERO", data: "{_escape_js(p)}"}}'
            for p in legacy_svg_data
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
                # No Plugin API transform — REST handlePositions can't be
                # converted reliably. Skip the gradient entirely rather
                # than emitting a wrong matrix. Supplement extraction
                # populates the correct transform from the Plugin API.
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
                image_transform = fill.get("imageTransform")
                # REST API uses STRETCH; Plugin API needs CROP when
                # imageTransform is present (crop/zoom), FILL otherwise
                if scale_mode == "STRETCH":
                    scale_mode = "CROP" if image_transform else "FILL"
                opacity = fill.get("opacity")
                opacity_str = f', opacity: {opacity}' if opacity is not None and opacity < 1.0 else ""
                transform_str = ""
                if image_transform:
                    r0 = image_transform[0]
                    r1 = image_transform[1]
                    transform_str = f", imageTransform: [[{r0[0]},{r0[1]},{r0[2]}],[{r1[0]},{r1[1]},{r1[2]}]]"
                paints.append(
                    f'{{type: "IMAGE", scaleMode: "{scale_mode}", '
                    f'imageHash: "{_escape_js(asset_hash)}"{transform_str}{opacity_str}}}'
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
    eid: str = "",
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
    db_font_style = db_font.get("font_style")
    if db_font_style:
        figma_style = normalize_font_style(family, db_font_style)
    else:
        figma_style = normalize_font_style(family, font_weight_to_style(weight))

    # Guard the fontName assignment. When an upstream loadFontAsync
    # failed (e.g. unlicensed trial font), this setter throws with
    # "Cannot use unloaded font" and — if unguarded — aborts Phase 1.
    # One bad text node shouldn't kill the whole render. The
    # font_load_failed entry from the preamble guard carries the family
    # and style; this per-op guard carries the eid so the specific
    # text node is attributable. See TestGuardedFontLoading +
    # feedback_text_layout_invariants.md.
    fontname_stmt = f'{var}.fontName = {{family: "{family}", style: "{figma_style}"}};'
    if eid:
        lines.append(_guarded_op(fontname_stmt, eid, "text_set_failed"))
    else:
        lines.append(fontname_stmt)

    font_size = _resolve_text_value(
        style.get("fontSize"), db_font.get("font_size"), tokens,
    )
    if font_size is not None:
        lines.append(f"{var}.fontSize = {font_size};")

    # Note: text .characters is NOT emitted here. It's set in Phase 3
    # (Hydrate) after the node is appended to its container, so text
    # reflows at the correct container width. See three-phase rendering
    # in compiler-architecture.md.

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

    # leadingTrim controls whether the text bounding box includes full
    # line-height padding (NONE, default) or trims to cap-height
    # (CAP_HEIGHT). Source files use CAP_HEIGHT for tight vertical
    # layout inside fixed-height non-auto-layout parents. Without
    # emitting this, the text's box is ~1.6x taller than the source's,
    # and positions extracted from DB (computed against the tighter
    # box) land the text visually top-aligned instead of centered.
    # Skip emission when "NONE" (Figma's default — redundant).
    leading_trim = db_font.get("leading_trim")
    if leading_trim and leading_trim != "NONE":
        lines.append(f'{var}.leadingTrim = "{leading_trim}";')

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

def generate_screen(
    conn: sqlite3.Connection, screen_id: int,
    *, canvas_position: Optional[tuple[float, float]] = None,
) -> dict[str, Any]:
    """Generate a Figma creation manifest for a classified screen.

    Post-M6 canonical path: dict-IR spec → markup-native Option B
    walker (``dd.render_figma_ast.render_figma``). The Option A
    decompressor branch (``via_markup=True``) and the ``--via-markup``
    CLI flag were deleted at M6 per
    ``docs/decisions/v0.3-option-b-cutover.md``; the 204/204 parity
    sweep at M4 validated the walker against every Dank screen.

    The spec-building step (``generate_ir``) remains as internal
    plumbing through M6(b); it feeds both the compressor
    (``compress_to_l3_with_maps``) and the ``_spec_elements`` shim
    inside ``render_figma``. M6(b) eliminates both by rewriting
    ``derive_markup`` to consume the DB directly and migrating the
    renderer's intrinsic-property emission AST-native.

    Returns dict with:
      structure_script: JS string for figma_execute (Phase A — creates nodes)
      token_refs: list of (element_id, property, token_name) for rebinding
      token_variables: dict mapping token_name → figma_variable_id
      element_count: number of elements in the spec
    """
    from dd.ir import generate_ir, query_screen_visuals
    from dd.rebind_prompt import query_token_variables

    # Semantic IR with system chrome preserved — per
    # feedback_system_chrome_is_design.md.
    ir_result = generate_ir(
        conn, screen_id, semantic=True, filter_chrome=False,
    )
    spec = ir_result["spec"]
    visuals = query_screen_visuals(conn, screen_id)

    # ADR-007 Session A: surface "CKR was not built" as a structured
    # entry in the script preamble so the root cause of downstream
    # Mode 2 degradations is visible in `__errors`.
    ckr_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='component_key_registry'"
    ).fetchone()
    if ckr_exists:
        ckr_row = conn.execute(
            "SELECT COUNT(*) FROM component_key_registry"
        ).fetchone()
        ckr_built = bool(ckr_row and ckr_row[0] > 0)
    else:
        ckr_built = False

    # Markup-native Option B walker. Render path keeps the
    # synthetic screen wrapper — Figma's native canvas has a
    # screen-1/frame-1 double-frame shape that the baseline renderer
    # preserved and the verifier expects. ``collapse_wrapper=False``
    # matches M4 pixel-parity against baseline;
    # ``collapse_wrapper=True`` is for grammar + round-trip tests
    # only.
    from dd.compress_l3 import compress_to_l3_with_maps
    from dd.render_figma_ast import render_figma
    doc, _eid_nid, nid_map, spec_key_map, original_name_map = (
        compress_to_l3_with_maps(
            spec, conn, screen_id=screen_id,
            collapse_wrapper=False,
        )
    )
    fonts = collect_fonts(spec, db_visuals=visuals)
    script, token_refs = render_figma(
        doc, conn, nid_map,
        fonts=fonts,
        spec_key_map=spec_key_map,
        original_name_map=original_name_map,
        db_visuals=visuals, ckr_built=ckr_built,
        canvas_position=canvas_position,
        _spec_elements=spec["elements"],
        _spec_tokens=spec.get("tokens", {}),
    )

    return {
        "structure_script": script,
        "token_refs": token_refs,
        "token_variables": query_token_variables(conn),
        "element_count": len(spec.get("elements", {})),
        "token_count": ir_result["token_count"],
    }


def validate_render_readiness(
    spec: dict[str, Any],
    db_visuals: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Check for data gaps that will affect render quality.

    Returns a list of warning dicts, each with:
      code: machine-readable warning type
      severity: "info" | "warning" | "error"
      element_id: which element is affected
      message: human-readable description
    """
    warnings: list[dict[str, Any]] = []
    elements = spec.get("elements", {})
    node_id_map = spec.get("_node_id_map", {})

    for eid, element in elements.items():
        etype = element.get("type", "")
        nid = node_id_map.get(eid)
        nv = db_visuals.get(nid, {}) if db_visuals and nid else {}

        # EMPTY_VECTOR: vector/boolean_operation without path data
        if etype in ("vector", "boolean_operation"):
            asset_refs = nv.get("_asset_refs", [])
            has_geometry = any(r.get("svg_data") for r in asset_refs)
            if not has_geometry:
                warnings.append({
                    "code": "EMPTY_VECTOR",
                    "severity": "warning",
                    "element_id": eid,
                    "message": f"{etype} '{eid}' has no path geometry — will render as invisible empty node",
                })

        # MISSING_SIZING_MODE: auto-layout child with no explicit sizing
        parent_eid = None
        for pid, pel in elements.items():
            if eid in pel.get("children", []):
                parent_eid = pid
                break
        if parent_eid:
            parent_direction = elements.get(parent_eid, {}).get("layout", {}).get("direction", "")
            if parent_direction in ("horizontal", "vertical"):
                sizing_h = nv.get("layout_sizing_h")
                sizing_v = nv.get("layout_sizing_v")
                ir_sizing = element.get("layout", {}).get("sizing", {})
                if sizing_h is None and isinstance(ir_sizing.get("width"), (int, float)):
                    warnings.append({
                        "code": "MISSING_SIZING_MODE",
                        "severity": "info",
                        "element_id": eid,
                        "message": f"'{eid}' in auto-layout has no sizing mode — defaulting to FILL",
                    })
                if sizing_v is None and isinstance(ir_sizing.get("height"), (int, float)):
                    warnings.append({
                        "code": "MISSING_SIZING_MODE",
                        "severity": "info",
                        "element_id": eid,
                        "message": f"'{eid}' in auto-layout has no vertical sizing mode — defaulting to FILL",
                    })

    return warnings


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
