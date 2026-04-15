"""Unified property registry for the round-trip pipeline.

Single source of truth for all Figma node properties. Every pipeline layer
references this registry instead of maintaining ad-hoc property lists:

- Extraction (extract_supplement.py): which override fields to capture
- Query (ir.py): which DB columns to SELECT
- Visual builder (generate.py): which properties to read from DB
- Renderer (generate.py): which properties to emit as JS
- Override application (generate.py): which override types to handle

Each property maps:
  Figma Plugin API name → DB column → override field name → value type
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Sentinel: property is emitted by a handler function registered in the renderer.
# The renderer's _FIGMA_HANDLERS dict maps figma_name → callable.
HANDLER = object()


# ---------------------------------------------------------------------------
# Per-backend node-type capability sets
# ---------------------------------------------------------------------------
# Each backend declares the set of its native node types that support a given
# property. Emitters gate on this: if a property's capability set for a backend
# doesn't include the target node type, the emitter skips it silently.
#
# Figma Plugin API node-type groups:
_FIGMA_CONTAINERS = frozenset({"FRAME", "COMPONENT", "INSTANCE", "SECTION"})
_FIGMA_BASIC_SHAPES = frozenset({"RECTANGLE", "ELLIPSE", "POLYGON", "STAR"})
_FIGMA_VECTOR_SHAPES = frozenset({"VECTOR", "BOOLEAN_OPERATION"})
_FIGMA_LINE = frozenset({"LINE"})
_FIGMA_TEXT = frozenset({"TEXT"})
_FIGMA_GROUP = frozenset({"GROUP"})
# Everything that has a visible representation in the renderer's output:
_FIGMA_ALL_VISIBLE = (
    _FIGMA_CONTAINERS
    | _FIGMA_BASIC_SHAPES
    | _FIGMA_VECTOR_SHAPES
    | _FIGMA_LINE
    | _FIGMA_TEXT
    | _FIGMA_GROUP
)
# Shapes + containers that support corner radius:
_FIGMA_CORNER_CAPABLE = _FIGMA_CONTAINERS | _FIGMA_BASIC_SHAPES
# Auto-layout-capable containers (same as _FIGMA_CONTAINERS for emission):
_FIGMA_AUTO_LAYOUT = _FIGMA_CONTAINERS


@dataclass(frozen=True)
class FigmaProperty:
    figma_name: str
    db_column: str | None
    override_fields: tuple[str, ...] = ()
    category: str = "visual"
    value_type: str = "number"
    override_type: str | None = None
    default_value: Any = None
    needs_json: bool = False
    skip_emit_if_default: bool = True
    emit: dict[str, Any] = field(default_factory=dict)
    token_binding_path: str | None = None
    # capabilities[backend_name] → frozenset of native node types that support
    # this property. Empty/missing entry means "not supported on that backend"
    # (fail closed at the output gate; extraction still fails open).
    capabilities: dict[str, frozenset[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Registry definition
# ---------------------------------------------------------------------------

_UNIFORM = "{var}.{figma_name} = {value};"  # type-aware formatting by emit_from_registry


def _figma_caps(node_types: frozenset[str]) -> dict[str, frozenset[str]]:
    """Shorthand: declare Figma-backend capability for a property."""
    return {"figma": node_types}


PROPERTIES: tuple[FigmaProperty, ...] = (
    # === VISUAL: Fills ===
    FigmaProperty("fills", "fills", ("fills",), "visual", "json_array",
                  override_type="FILLS", default_value="[]", needs_json=True,
                  emit={"figma": HANDLER},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),

    # === VISUAL: Strokes ===
    FigmaProperty("strokes", "strokes", ("strokes",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": HANDLER},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("strokeWeight", "stroke_weight", ("strokeWeight",), "visual", "number",
                  emit={"figma": _UNIFORM},
                  token_binding_path="strokeWeight",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("strokeAlign", "stroke_align", ("strokeAlign",), "visual", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("strokeCap", "stroke_cap", ("strokeCap",), "visual", "enum",
                  default_value="NONE",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("strokeJoin", "stroke_join", ("strokeJoin",), "visual", "enum",
                  default_value="MITER",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("dashPattern", "dash_pattern", ("dashPattern",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),

    # === VISUAL: Effects ===
    FigmaProperty("effects", "effects", ("effects",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": HANDLER},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),

    # === VISUAL: Appearance ===
    FigmaProperty("opacity", "opacity", ("opacity",), "visual", "number",
                  override_type="OPACITY", default_value=1.0,
                  emit={"figma": _UNIFORM},
                  token_binding_path="opacity",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("blendMode", "blend_mode", ("blendMode",), "visual", "enum",
                  default_value="PASS_THROUGH",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    # Deferred: handled in main generation loop (element.visible), not _emit_visual
    FigmaProperty("visible", "visible", ("visible",), "visual", "boolean",
                  override_type="BOOLEAN", default_value=True,
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("clipsContent", "clips_content", ("clipsContent",), "visual", "boolean",
                  default_value=True, skip_emit_if_default=False,
                  emit={"figma": HANDLER},
                  capabilities=_figma_caps(_FIGMA_CONTAINERS)),
    FigmaProperty("rotation", "rotation", ("rotation",), "visual", "number_radians",
                  default_value=0,
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("isMask", "is_mask", ("isMask",), "visual", "boolean",
                  default_value=False,
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("cornerSmoothing", "corner_smoothing", ("cornerSmoothing",), "visual", "number",
                  default_value=0,
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_CORNER_CAPABLE)),
    FigmaProperty("booleanOperation", "boolean_operation", ("booleanOperation",), "visual", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(frozenset({"BOOLEAN_OPERATION"}))),
    FigmaProperty("arcData", "arc_data", ("arcData",), "visual", "json",
                  needs_json=True,
                  emit={"figma": HANDLER},
                  capabilities=_figma_caps(frozenset({"ELLIPSE"}))),

    # === VISUAL: Corner Radius ===
    FigmaProperty("cornerRadius", "corner_radius", ("cornerRadius",), "visual",
                  "number_or_mixed",
                  emit={"figma": HANDLER},
                  token_binding_path="cornerRadius",
                  capabilities=_figma_caps(_FIGMA_CORNER_CAPABLE)),

    # === LAYOUT ===
    FigmaProperty("layoutMode", "layout_mode", ("layoutMode",), "layout", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_AUTO_LAYOUT)),
    # Deferred: conditional on parent auto-layout context
    FigmaProperty("layoutSizingHorizontal", "layout_sizing_h",
                  ("layoutSizingHorizontal", "primaryAxisSizingMode"), "layout", "enum",
                  override_type="LAYOUT_SIZING_H",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE - _FIGMA_GROUP - _FIGMA_LINE)),
    FigmaProperty("layoutSizingVertical", "layout_sizing_v",
                  ("layoutSizingVertical", "counterAxisSizingMode"), "layout", "enum",
                  override_type="LAYOUT_SIZING_V",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE - _FIGMA_GROUP - _FIGMA_LINE)),
    FigmaProperty("primaryAxisAlignItems", "primary_align",
                  ("primaryAxisAlignItems",), "layout", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_AUTO_LAYOUT)),
    FigmaProperty("counterAxisAlignItems", "counter_align",
                  ("counterAxisAlignItems",), "layout", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_AUTO_LAYOUT)),
    FigmaProperty("paddingTop", "padding_top", ("paddingTop",), "layout", "number",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_AUTO_LAYOUT)),
    FigmaProperty("paddingRight", "padding_right", ("paddingRight",), "layout", "number",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_AUTO_LAYOUT)),
    FigmaProperty("paddingBottom", "padding_bottom", ("paddingBottom",), "layout", "number",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_AUTO_LAYOUT)),
    FigmaProperty("paddingLeft", "padding_left", ("paddingLeft",), "layout", "number",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_AUTO_LAYOUT)),
    FigmaProperty("itemSpacing", "item_spacing", ("itemSpacing",), "layout", "number",
                  override_type="ITEM_SPACING",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_AUTO_LAYOUT)),
    FigmaProperty("counterAxisSpacing", "counter_axis_spacing",
                  ("counterAxisSpacing",), "layout", "number",
                  emit={"figma": _UNIFORM},
                  token_binding_path="counterAxisSpacing",
                  capabilities=_figma_caps(_FIGMA_AUTO_LAYOUT)),
    FigmaProperty("layoutWrap", "layout_wrap", ("layoutWrap",), "layout", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_AUTO_LAYOUT)),
    FigmaProperty("layoutPositioning", "layout_positioning",
                  ("layoutPositioning",), "layout", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE - _FIGMA_GROUP)),

    # === SIZE ===
    # Deferred: resize() call in main loop
    FigmaProperty("width", "width", ("width",), "size", "number",
                  override_type="WIDTH",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("height", "height", ("height",), "size", "number",
                  override_type="HEIGHT",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("minWidth", "min_width", ("minWidth",), "size", "number",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE - _FIGMA_GROUP - _FIGMA_LINE)),
    FigmaProperty("maxWidth", "max_width", ("maxWidth",), "size", "number",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE - _FIGMA_GROUP - _FIGMA_LINE)),
    FigmaProperty("minHeight", "min_height", ("minHeight",), "size", "number",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE - _FIGMA_GROUP - _FIGMA_LINE)),
    FigmaProperty("maxHeight", "max_height", ("maxHeight",), "size", "number",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE - _FIGMA_GROUP - _FIGMA_LINE)),

    # === TEXT ===
    # Deferred: handled by _emit_text_props (progressive fallback, fontName composition)
    FigmaProperty("characters", "text_content", ("characters",), "text", "string",
                  override_type="TEXT",
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("fontSize", "font_size", ("fontSize",), "text", "number",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("fontFamily", "font_family", ("fontName",), "text", "string",
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("fontWeight", "font_weight", ("fontWeight",), "text", "number",
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("fontStyle", "font_style", (), "text", "string",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("textAlignHorizontal", "text_align",
                  ("textAlignHorizontal",), "text", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("textAlignVertical", "text_align_v",
                  ("textAlignVertical",), "text", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("textAutoResize", "text_auto_resize",
                  ("textAutoResize",), "text", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("textDecoration", "text_decoration",
                  ("textDecoration",), "text", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("textCase", "text_case", ("textCase",), "text", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("lineHeight", "line_height", ("lineHeight",), "text", "json",
                  needs_json=True,
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("letterSpacing", "letter_spacing", ("letterSpacing",), "text", "json",
                  needs_json=True,
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_TEXT)),
    FigmaProperty("paragraphSpacing", "paragraph_spacing",
                  ("paragraphSpacing",), "text", "number",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_TEXT)),

    # === CONSTRAINTS ===
    # Deferred: emitted in post-appendChild section, not main emit block
    FigmaProperty("constraints.horizontal", "constraint_h", (), "constraint", "enum",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE - _FIGMA_GROUP)),
    FigmaProperty("constraints.vertical", "constraint_v", (), "constraint", "enum",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE - _FIGMA_GROUP)),
)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

_BY_DB_COLUMN: dict[str, FigmaProperty] = {
    p.db_column: p for p in PROPERTIES if p.db_column
}

_BY_FIGMA_NAME: dict[str, FigmaProperty] = {
    p.figma_name: p for p in PROPERTIES
}

_BY_OVERRIDE_TYPE: dict[str, FigmaProperty] = {
    p.override_type: p for p in PROPERTIES if p.override_type
}

_OVERRIDE_FIELD_MAP: dict[str, FigmaProperty] = {}
for p in PROPERTIES:
    for field_name in p.override_fields:
        _OVERRIDE_FIELD_MAP[field_name] = p


def by_db_column(column: str) -> FigmaProperty | None:
    return _BY_DB_COLUMN.get(column)


def by_figma_name(name: str) -> FigmaProperty | None:
    return _BY_FIGMA_NAME.get(name)


def by_override_type(override_type: str) -> FigmaProperty | None:
    return _BY_OVERRIDE_TYPE.get(override_type)


def by_override_field(field_name: str) -> FigmaProperty | None:
    return _OVERRIDE_FIELD_MAP.get(field_name)


def overrideable_properties() -> list[FigmaProperty]:
    """Return properties that can appear in Figma's overriddenFields."""
    return [p for p in PROPERTIES if p.override_fields]


def is_capable(figma_name: str, backend: str, node_type: str) -> bool:
    """Check if a property is emittable on a given backend's native node type.

    Returns False for unknown properties, unknown backends, or node types not
    in the property's capability set. Fails closed — emission is the output
    gate where strict legality matters (extraction still fails open per
    feedback_fail_open_not_closed.md).

    This same table serves as the constrained-decoding grammar for synthetic
    IR generation: an LLM proposing `clipsContent` on a RECTANGLE is rejected
    at decode time, not at render time.
    """
    prop = _BY_FIGMA_NAME.get(figma_name)
    if prop is None:
        return False
    caps = prop.capabilities.get(backend)
    if caps is None:
        return False
    return node_type in caps
