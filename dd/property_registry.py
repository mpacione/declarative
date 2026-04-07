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
    emit: dict[str, str | None] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Registry definition
# ---------------------------------------------------------------------------

PROPERTIES: tuple[FigmaProperty, ...] = (
    # === VISUAL: Fills ===
    # Complex: custom _emit_fills handles SOLID + GRADIENT types
    FigmaProperty("fills", "fills", ("fills",), "visual", "json_array",
                  override_type="FILLS", default_value="[]", needs_json=True,
                  emit={"figma": None}),

    # === VISUAL: Strokes ===
    # Complex: custom _emit_strokes handles paint array + strokeWeight
    FigmaProperty("strokes", "strokes", ("strokes",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": None}),
    FigmaProperty("strokeWeight", "stroke_weight", ("strokeWeight",), "visual", "number",
                  emit={"figma": '{var}.strokeWeight = {value};'}),
    FigmaProperty("strokeAlign", "stroke_align", ("strokeAlign",), "visual", "enum",
                  emit={"figma": '{var}.strokeAlign = "{value}";'}),
    FigmaProperty("strokeCap", "stroke_cap", ("strokeCap",), "visual", "enum",
                  emit={"figma": '{var}.strokeCap = "{value}";'}),
    FigmaProperty("strokeJoin", "stroke_join", ("strokeJoin",), "visual", "enum",
                  emit={"figma": '{var}.strokeJoin = "{value}";'}),
    FigmaProperty("dashPattern", "dash_pattern", ("dashPattern",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": "{var}.dashPattern = {value};"}),

    # === VISUAL: Effects ===
    # Complex: custom _emit_effects handles shadow + blur types
    FigmaProperty("effects", "effects", ("effects",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": None}),

    # === VISUAL: Appearance ===
    FigmaProperty("opacity", "opacity", ("opacity",), "visual", "number",
                  override_type="OPACITY", default_value=1.0,
                  emit={"figma": "{var}.opacity = {value};"}),
    FigmaProperty("blendMode", "blend_mode", ("blendMode",), "visual", "enum",
                  default_value="PASS_THROUGH",
                  emit={"figma": '{var}.blendMode = "{value}";'}),
    FigmaProperty("visible", "visible", ("visible",), "visual", "boolean",
                  override_type="BOOLEAN", default_value=True,
                  emit={"figma": None}),  # Custom: handled in main loop (element.visible check)
    FigmaProperty("clipsContent", "clips_content", ("clipsContent",), "visual", "boolean",
                  default_value=True,
                  emit={"figma": None}),  # Custom: true/false JS booleans + Figma default clearing
    FigmaProperty("rotation", "rotation", ("rotation",), "visual", "number_radians",
                  default_value=0,
                  emit={"figma": "{var}.rotation = {value};"}),

    # === VISUAL: Corner Radius ===
    # Complex: uniform (number) vs per-corner (dict) formats
    FigmaProperty("cornerRadius", "corner_radius", ("cornerRadius",), "visual",
                  "number_or_mixed",
                  emit={"figma": None}),

    # === LAYOUT ===
    FigmaProperty("layoutMode", "layout_mode", ("layoutMode",), "layout", "enum",
                  emit={"figma": '{var}.layoutMode = "{value}";'}),
    FigmaProperty("layoutSizingHorizontal", "layout_sizing_h",
                  ("layoutSizingHorizontal", "primaryAxisSizingMode"), "layout", "enum",
                  override_type="LAYOUT_SIZING_H"),
    FigmaProperty("layoutSizingVertical", "layout_sizing_v",
                  ("layoutSizingVertical", "counterAxisSizingMode"), "layout", "enum",
                  override_type="LAYOUT_SIZING_V"),
    FigmaProperty("primaryAxisAlignItems", "primary_align",
                  ("primaryAxisAlignItems",), "layout", "enum",
                  emit={"figma": '{var}.primaryAxisAlignItems = "{value}";'}),
    FigmaProperty("counterAxisAlignItems", "counter_align",
                  ("counterAxisAlignItems",), "layout", "enum",
                  emit={"figma": '{var}.counterAxisAlignItems = "{value}";'}),
    FigmaProperty("paddingTop", "padding_top", ("paddingTop",), "layout", "number",
                  emit={"figma": "{var}.paddingTop = {value};"}),
    FigmaProperty("paddingRight", "padding_right", ("paddingRight",), "layout", "number",
                  emit={"figma": "{var}.paddingRight = {value};"}),
    FigmaProperty("paddingBottom", "padding_bottom", ("paddingBottom",), "layout", "number",
                  emit={"figma": "{var}.paddingBottom = {value};"}),
    FigmaProperty("paddingLeft", "padding_left", ("paddingLeft",), "layout", "number",
                  emit={"figma": "{var}.paddingLeft = {value};"}),
    FigmaProperty("itemSpacing", "item_spacing", ("itemSpacing",), "layout", "number",
                  override_type="ITEM_SPACING",
                  emit={"figma": "{var}.itemSpacing = {value};"}),
    FigmaProperty("counterAxisSpacing", "counter_axis_spacing",
                  ("counterAxisSpacing",), "layout", "number",
                  emit={"figma": "{var}.counterAxisSpacing = {value};"}),
    FigmaProperty("layoutWrap", "layout_wrap", ("layoutWrap",), "layout", "enum",
                  emit={"figma": '{var}.layoutWrap = "{value}";'}),
    FigmaProperty("layoutPositioning", "layout_positioning",
                  ("layoutPositioning",), "layout", "enum",
                  emit={"figma": '{var}.layoutPositioning = "{value}";'}),

    # === SIZE ===
    FigmaProperty("width", "width", ("width",), "size", "number",
                  override_type="WIDTH"),
    FigmaProperty("height", "height", ("height",), "size", "number",
                  override_type="HEIGHT"),
    FigmaProperty("minWidth", "min_width", ("minWidth",), "size", "number",
                  emit={"figma": "{var}.minWidth = {value};"}),
    FigmaProperty("maxWidth", "max_width", ("maxWidth",), "size", "number",
                  emit={"figma": "{var}.maxWidth = {value};"}),
    FigmaProperty("minHeight", "min_height", ("minHeight",), "size", "number",
                  emit={"figma": "{var}.minHeight = {value};"}),
    FigmaProperty("maxHeight", "max_height", ("maxHeight",), "size", "number",
                  emit={"figma": "{var}.maxHeight = {value};"}),

    # === TEXT ===
    # Complex: characters handled by text content emission
    FigmaProperty("characters", "text_content", ("characters",), "text", "string",
                  override_type="TEXT",
                  emit={"figma": None}),
    FigmaProperty("fontSize", "font_size", ("fontSize",), "text", "number",
                  emit={"figma": "{var}.fontSize = {value};"}),
    # Complex: fontFamily + fontWeight + fontStyle combined into fontName object
    FigmaProperty("fontFamily", "font_family", ("fontName",), "text", "string",
                  emit={"figma": None}),
    FigmaProperty("fontWeight", "font_weight", ("fontWeight",), "text", "number",
                  emit={"figma": None}),
    FigmaProperty("fontStyle", "font_style", (), "text", "string",
                  emit={"figma": '{var}.fontStyle = "{value}";'}),
    FigmaProperty("textAlignHorizontal", "text_align",
                  ("textAlignHorizontal",), "text", "enum",
                  emit={"figma": '{var}.textAlignHorizontal = "{value}";'}),
    FigmaProperty("textAlignVertical", "text_align_v",
                  ("textAlignVertical",), "text", "enum",
                  emit={"figma": '{var}.textAlignVertical = "{value}";'}),
    FigmaProperty("textAutoResize", "text_auto_resize",
                  ("textAutoResize",), "text", "enum",
                  emit={"figma": '{var}.textAutoResize = "{value}";'}),
    FigmaProperty("textDecoration", "text_decoration",
                  ("textDecoration",), "text", "enum",
                  emit={"figma": '{var}.textDecoration = "{value}";'}),
    FigmaProperty("textCase", "text_case", ("textCase",), "text", "enum",
                  emit={"figma": '{var}.textCase = "{value}";'}),
    FigmaProperty("lineHeight", "line_height", ("lineHeight",), "text", "json",
                  needs_json=True,
                  emit={"figma": "{var}.lineHeight = {value};"}),
    FigmaProperty("letterSpacing", "letter_spacing", ("letterSpacing",), "text", "json",
                  needs_json=True,
                  emit={"figma": "{var}.letterSpacing = {value};"}),
    FigmaProperty("paragraphSpacing", "paragraph_spacing",
                  ("paragraphSpacing",), "text", "number",
                  emit={"figma": "{var}.paragraphSpacing = {value};"}),

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


def db_columns_for_visual_query() -> list[str]:
    """Return DB column names needed by query_screen_visuals.

    Includes all columns with visual, layout, size, and text data.
    Excludes structural columns (id, parent_id, sort_order, etc.)
    and columns handled via separate joins (component_key, bindings).
    """
    exclude = {"width", "height", "x", "y"}  # geometry handled via IR sizing
    return [
        p.db_column for p in PROPERTIES
        if p.db_column and p.db_column not in exclude
        and p.category in ("visual", "layout", "text")
    ]


def overrideable_properties() -> list[FigmaProperty]:
    """Return properties that can appear in Figma's overriddenFields."""
    return [p for p in PROPERTIES if p.override_fields]


def override_types() -> list[str]:
    """Return all override_type values defined in the registry."""
    return [p.override_type for p in PROPERTIES if p.override_type]
