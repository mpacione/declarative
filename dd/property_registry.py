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

from dataclasses import dataclass, field
from typing import Any


# Sentinel: property is emitted by a handler function registered in the renderer.
# The renderer's _FIGMA_HANDLERS dict maps figma_name → callable.
HANDLER = object()


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


# ---------------------------------------------------------------------------
# Registry definition
# ---------------------------------------------------------------------------

_UNIFORM = "{var}.{figma_name} = {value};"  # type-aware formatting by emit_from_registry

PROPERTIES: tuple[FigmaProperty, ...] = (
    # === VISUAL: Fills ===
    FigmaProperty("fills", "fills", ("fills",), "visual", "json_array",
                  override_type="FILLS", default_value="[]", needs_json=True,
                  emit={"figma": HANDLER}),

    # === VISUAL: Strokes ===
    FigmaProperty("strokes", "strokes", ("strokes",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": HANDLER}),
    FigmaProperty("strokeWeight", "stroke_weight", ("strokeWeight",), "visual", "number",
                  emit={"figma": _UNIFORM},
                  token_binding_path="strokeWeight"),
    FigmaProperty("strokeAlign", "stroke_align", ("strokeAlign",), "visual", "enum",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("strokeCap", "stroke_cap", ("strokeCap",), "visual", "enum",
                  default_value="NONE",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("strokeJoin", "stroke_join", ("strokeJoin",), "visual", "enum",
                  default_value="MITER",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("dashPattern", "dash_pattern", ("dashPattern",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": _UNIFORM}),

    # === VISUAL: Effects ===
    FigmaProperty("effects", "effects", ("effects",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": HANDLER}),

    # === VISUAL: Appearance ===
    FigmaProperty("opacity", "opacity", ("opacity",), "visual", "number",
                  override_type="OPACITY", default_value=1.0,
                  emit={"figma": _UNIFORM},
                  token_binding_path="opacity"),
    FigmaProperty("blendMode", "blend_mode", ("blendMode",), "visual", "enum",
                  default_value="PASS_THROUGH",
                  emit={"figma": _UNIFORM}),
    # Deferred: handled in main generation loop (element.visible), not _emit_visual
    FigmaProperty("visible", "visible", ("visible",), "visual", "boolean",
                  override_type="BOOLEAN", default_value=True),
    FigmaProperty("clipsContent", "clips_content", ("clipsContent",), "visual", "boolean",
                  default_value=True, skip_emit_if_default=False,
                  emit={"figma": HANDLER}),
    FigmaProperty("rotation", "rotation", ("rotation",), "visual", "number_radians",
                  default_value=0,
                  emit={"figma": _UNIFORM}),
    FigmaProperty("isMask", "is_mask", ("isMask",), "visual", "boolean",
                  default_value=False,
                  emit={"figma": _UNIFORM}),
    FigmaProperty("cornerSmoothing", "corner_smoothing", ("cornerSmoothing",), "visual", "number",
                  default_value=0,
                  emit={"figma": _UNIFORM}),
    FigmaProperty("booleanOperation", "boolean_operation", ("booleanOperation",), "visual", "enum",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("arcData", "arc_data", ("arcData",), "visual", "json",
                  needs_json=True,
                  emit={"figma": HANDLER}),

    # === VISUAL: Corner Radius ===
    FigmaProperty("cornerRadius", "corner_radius", ("cornerRadius",), "visual",
                  "number_or_mixed",
                  emit={"figma": HANDLER},
                  token_binding_path="cornerRadius"),

    # === LAYOUT ===
    FigmaProperty("layoutMode", "layout_mode", ("layoutMode",), "layout", "enum",
                  emit={"figma": _UNIFORM}),
    # Deferred: conditional on parent auto-layout context
    FigmaProperty("layoutSizingHorizontal", "layout_sizing_h",
                  ("layoutSizingHorizontal", "primaryAxisSizingMode"), "layout", "enum",
                  override_type="LAYOUT_SIZING_H"),
    FigmaProperty("layoutSizingVertical", "layout_sizing_v",
                  ("layoutSizingVertical", "counterAxisSizingMode"), "layout", "enum",
                  override_type="LAYOUT_SIZING_V"),
    FigmaProperty("primaryAxisAlignItems", "primary_align",
                  ("primaryAxisAlignItems",), "layout", "enum",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("counterAxisAlignItems", "counter_align",
                  ("counterAxisAlignItems",), "layout", "enum",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("paddingTop", "padding_top", ("paddingTop",), "layout", "number",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("paddingRight", "padding_right", ("paddingRight",), "layout", "number",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("paddingBottom", "padding_bottom", ("paddingBottom",), "layout", "number",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("paddingLeft", "padding_left", ("paddingLeft",), "layout", "number",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("itemSpacing", "item_spacing", ("itemSpacing",), "layout", "number",
                  override_type="ITEM_SPACING",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("counterAxisSpacing", "counter_axis_spacing",
                  ("counterAxisSpacing",), "layout", "number",
                  emit={"figma": _UNIFORM},
                  token_binding_path="counterAxisSpacing"),
    FigmaProperty("layoutWrap", "layout_wrap", ("layoutWrap",), "layout", "enum",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("layoutPositioning", "layout_positioning",
                  ("layoutPositioning",), "layout", "enum",
                  emit={"figma": _UNIFORM}),

    # === SIZE ===
    # Deferred: resize() call in main loop
    FigmaProperty("width", "width", ("width",), "size", "number",
                  override_type="WIDTH"),
    FigmaProperty("height", "height", ("height",), "size", "number",
                  override_type="HEIGHT"),
    FigmaProperty("minWidth", "min_width", ("minWidth",), "size", "number",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("maxWidth", "max_width", ("maxWidth",), "size", "number",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("minHeight", "min_height", ("minHeight",), "size", "number",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("maxHeight", "max_height", ("maxHeight",), "size", "number",
                  emit={"figma": _UNIFORM}),

    # === TEXT ===
    # Deferred: handled by _emit_text_props (progressive fallback, fontName composition)
    FigmaProperty("characters", "text_content", ("characters",), "text", "string",
                  override_type="TEXT"),
    FigmaProperty("fontSize", "font_size", ("fontSize",), "text", "number",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("fontFamily", "font_family", ("fontName",), "text", "string"),
    FigmaProperty("fontWeight", "font_weight", ("fontWeight",), "text", "number"),
    FigmaProperty("fontStyle", "font_style", (), "text", "string",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("textAlignHorizontal", "text_align",
                  ("textAlignHorizontal",), "text", "enum",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("textAlignVertical", "text_align_v",
                  ("textAlignVertical",), "text", "enum",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("textAutoResize", "text_auto_resize",
                  ("textAutoResize",), "text", "enum",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("textDecoration", "text_decoration",
                  ("textDecoration",), "text", "enum",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("textCase", "text_case", ("textCase",), "text", "enum",
                  emit={"figma": _UNIFORM}),
    FigmaProperty("lineHeight", "line_height", ("lineHeight",), "text", "json",
                  needs_json=True,
                  emit={"figma": _UNIFORM}),
    FigmaProperty("letterSpacing", "letter_spacing", ("letterSpacing",), "text", "json",
                  needs_json=True,
                  emit={"figma": _UNIFORM}),
    FigmaProperty("paragraphSpacing", "paragraph_spacing",
                  ("paragraphSpacing",), "text", "number",
                  emit={"figma": _UNIFORM}),

    # === CONSTRAINTS ===
    # Deferred: emitted in post-appendChild section, not main emit block
    FigmaProperty("constraints.horizontal", "constraint_h", (), "constraint", "enum"),
    FigmaProperty("constraints.vertical", "constraint_v", (), "constraint", "enum"),
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
