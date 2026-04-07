"""Shared visual infrastructure (renderer-agnostic).

Produces a renderer-agnostic visual dict from DB data. Any renderer
(Figma, React, SwiftUI, Flutter) imports from here and applies its
own platform-specific transforms at emit time.

Visual dict format:
  - Colors: hex strings (#RRGGBBAA)
  - Font weights: numeric (400-900)
  - Rotation: radians (ground truth from DB)
  - Booleans: Python bool
  - JSON: parsed objects
  - Alignment/sizing: semantic strings ("fill"/"hug"/"start"/"center")

See docs/cross-platform-value-formats.md for how each platform
converts from this format to its native representation.
"""

import json
import re
from typing import Any

from dd.ir import (
    normalize_corner_radius,
    normalize_effects,
    normalize_fills,
    normalize_strokes,
)


# ---------------------------------------------------------------------------
# Token reference resolution
# ---------------------------------------------------------------------------

_TOKEN_REF_RE = re.compile(r"^\{(.+)\}$")


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


# ---------------------------------------------------------------------------
# DB → renderer-agnostic visual dict
# ---------------------------------------------------------------------------

# Properties requiring custom normalization (need bindings or multi-column input)
_COMPLEX_NORMALIZE = frozenset({"fills", "strokes", "effects", "cornerRadius"})


def _apply_db_transform(value: Any, prop: Any) -> Any:
    """Apply universal DB-to-visual transforms based on value_type.

    Only universal transforms here (all renderers need these):
    - int→bool: DB stores 0/1, all renderers need booleans
    - JSON parse: DB stores JSON as text, all renderers need objects

    Renderer-specific transforms (e.g., radians→degrees for Figma,
    hex→rgba for Figma, weight→style name for Figma) happen at emit
    time in each renderer's format_value function.
    """
    if prop.value_type == "boolean":
        return bool(value)
    if prop.needs_json and isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if parsed else None
        except (json.JSONDecodeError, TypeError):
            return None
    return value


def build_visual_from_db(node_visual: dict[str, Any]) -> dict[str, Any]:
    """Produce a renderer-agnostic visual dict from raw DB data.

    Registry-driven: iterates PROPERTIES to map db_column → figma_name,
    applies universal transforms via _apply_db_transform, bundles text
    into font dict, constraints into constraints dict.

    The output is renderer-agnostic:
    - Colors as hex strings (renderers convert to their native format)
    - Font weights as numbers (renderers convert to style names/enums)
    - Rotation in radians (renderers convert to degrees if needed)
    """
    from dd.property_registry import PROPERTIES

    bindings = node_visual.get("bindings", [])
    visual: dict[str, Any] = {}
    font_data: dict[str, Any] = {}
    token_refs: dict[str, str] = {}

    # Build binding lookup: property path → token name
    binding_map = {
        b["property"]: b["token_name"]
        for b in bindings
        if b.get("token_name")
    }

    # Complex properties: custom normalization (need bindings or multi-column input)
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

    # Token binding for cornerRadius (complex-normalized, check separately)
    cr_token = binding_map.get("cornerRadius")
    if cr_token:
        token_refs["cornerRadius"] = cr_token

    # Registry-driven: all other properties
    for prop in PROPERTIES:
        if not prop.db_column:
            continue
        if prop.figma_name in _COMPLEX_NORMALIZE:
            continue

        value = node_visual.get(prop.db_column)
        if value is None:
            continue

        value = _apply_db_transform(value, prop)
        if value is None:
            continue

        # Check for token binding via registry-declared path
        has_binding = False
        if prop.token_binding_path:
            token_name = binding_map.get(prop.token_binding_path)
            if token_name:
                token_refs[prop.figma_name] = token_name
                has_binding = True

        # Don't skip default values when a token binding exists
        if prop.skip_emit_if_default and value == prop.default_value and not has_binding:
            continue

        if prop.category == "text":
            font_data[prop.db_column] = value
            continue

        if prop.category == "constraint":
            key = prop.figma_name.split(".")[-1]
            visual.setdefault("constraints", {})[key] = value
            continue

        visual[prop.figma_name] = value

    if font_data:
        visual["font"] = font_data

    if token_refs:
        visual["_token_refs"] = token_refs

    return visual


# ---------------------------------------------------------------------------
# Layout sizing resolution (pure function)
# ---------------------------------------------------------------------------

# Container types that should fill parent width in vertical auto-layout.
_FILL_WIDTH_TYPES = frozenset({
    "card", "accordion", "header", "search_input", "tabs",
    "drawer", "sheet", "alert", "empty_state",
})

# textAutoResize → (default sizingH, default sizingV)
# Values are semantic ("fill"/"hug") — renderers map to their own format.
# None means "don't override — fall through to IR/heuristic sizing"
_TEXT_AUTO_RESIZE_SIZING: dict[str, tuple[str | None, str | None]] = {
    "WIDTH_AND_HEIGHT": ("hug", "hug"),
    "HEIGHT":           ("fill", "hug"),
    "NONE":             (None, None),
    "TRUNCATE":         (None, None),
}


def _resolve_layout_sizing(
    elem_sizing: dict[str, Any],
    db_sizing_h: str | None,
    db_sizing_v: str | None,
    text_auto_resize: str | None,
    is_text: bool,
    etype: str,
) -> tuple[str | None, str | None]:
    """Determine layoutSizing for an auto-layout child.

    Pure function — no side effects, no DB lookups, no emission.
    Priority per axis: DB > text reconciliation > IR sizing > type heuristic.

    Returns (horizontal, vertical) as semantic lowercase strings
    ("fill", "hug", "fixed"), DB-native uppercase ("FILL", "HUG", "FIXED"),
    or None to skip. Renderers map to their platform's format.
    """
    h = _resolve_one_axis(
        db_value=db_sizing_h,
        text_override=_TEXT_AUTO_RESIZE_SIZING.get(text_auto_resize, (None, None))[0] if text_auto_resize else None,
        ir_value=elem_sizing.get("width"),
        is_text=is_text,
        etype=etype,
        is_horizontal=True,
    )
    v = _resolve_one_axis(
        db_value=db_sizing_v,
        text_override=_TEXT_AUTO_RESIZE_SIZING.get(text_auto_resize, (None, None))[1] if text_auto_resize else None,
        ir_value=elem_sizing.get("height"),
        is_text=is_text,
        etype=etype,
        is_horizontal=False,
    )
    return h, v


def _resolve_one_axis(
    db_value: str | None,
    text_override: str | None,
    ir_value: Any,
    is_text: bool,
    etype: str,
    is_horizontal: bool,
) -> str | None:
    """Resolve layoutSizing for one axis.

    Returns semantic lowercase ("fill", "hug", "fixed"), DB-native
    uppercase ("FILL", "HUG"), or None. Renderers map to platform format.
    """
    if db_value:
        return db_value
    if text_override:
        return text_override
    if isinstance(ir_value, str) and ir_value in ("fill", "hug", "fixed"):
        return ir_value
    if isinstance(ir_value, (int, float)):
        return "fixed"
    if is_text and is_horizontal:
        return "fill"
    if is_horizontal and etype in _FILL_WIDTH_TYPES:
        return "fill"
    return None
