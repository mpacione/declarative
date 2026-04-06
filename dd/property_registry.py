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


# ---------------------------------------------------------------------------
# Registry definition
# ---------------------------------------------------------------------------

PROPERTIES: tuple[FigmaProperty, ...] = (
    # === VISUAL: Fills ===
    FigmaProperty("fills", "fills", ("fills",), "visual", "json_array",
                  override_type="FILLS", default_value="[]", needs_json=True),

    # === VISUAL: Strokes ===
    FigmaProperty("strokes", "strokes", ("strokes",), "visual", "json_array",
                  needs_json=True),
    FigmaProperty("strokeWeight", "stroke_weight", ("strokeWeight",), "visual", "number"),
    FigmaProperty("strokeAlign", "stroke_align", ("strokeAlign",), "visual", "enum"),
    FigmaProperty("strokeCap", "stroke_cap", ("strokeCap",), "visual", "enum"),
    FigmaProperty("strokeJoin", "stroke_join", ("strokeJoin",), "visual", "enum"),
    FigmaProperty("dashPattern", "dash_pattern", ("dashPattern",), "visual", "json_array",
                  needs_json=True),

    # === VISUAL: Effects ===
    FigmaProperty("effects", "effects", ("effects",), "visual", "json_array",
                  needs_json=True),

    # === VISUAL: Appearance ===
    FigmaProperty("opacity", "opacity", ("opacity",), "visual", "number",
                  override_type="OPACITY", default_value=1.0),
    FigmaProperty("blendMode", "blend_mode", ("blendMode",), "visual", "enum",
                  default_value="PASS_THROUGH"),
    FigmaProperty("visible", "visible", ("visible",), "visual", "boolean",
                  override_type="BOOLEAN", default_value=True),
    FigmaProperty("clipsContent", "clips_content", ("clipsContent",), "visual", "boolean",
                  default_value=True),
    FigmaProperty("rotation", "rotation", ("rotation",), "visual", "number_radians",
                  default_value=0),

    # === VISUAL: Corner Radius ===
    FigmaProperty("cornerRadius", "corner_radius", ("cornerRadius",), "visual",
                  "number_or_mixed"),

    # === LAYOUT ===
    FigmaProperty("layoutMode", "layout_mode", ("layoutMode",), "layout", "enum"),
    FigmaProperty("layoutSizingHorizontal", "layout_sizing_h",
                  ("layoutSizingHorizontal", "primaryAxisSizingMode"), "layout", "enum",
                  override_type="LAYOUT_SIZING_H"),
    FigmaProperty("layoutSizingVertical", "layout_sizing_v",
                  ("layoutSizingVertical", "counterAxisSizingMode"), "layout", "enum",
                  override_type="LAYOUT_SIZING_V"),
    FigmaProperty("primaryAxisAlignItems", "primary_align",
                  ("primaryAxisAlignItems",), "layout", "enum"),
    FigmaProperty("counterAxisAlignItems", "counter_align",
                  ("counterAxisAlignItems",), "layout", "enum"),
    FigmaProperty("paddingTop", "padding_top", ("paddingTop",), "layout", "number"),
    FigmaProperty("paddingRight", "padding_right", ("paddingRight",), "layout", "number"),
    FigmaProperty("paddingBottom", "padding_bottom", ("paddingBottom",), "layout", "number"),
    FigmaProperty("paddingLeft", "padding_left", ("paddingLeft",), "layout", "number"),
    FigmaProperty("itemSpacing", "item_spacing", ("itemSpacing",), "layout", "number",
                  override_type="ITEM_SPACING"),
    FigmaProperty("counterAxisSpacing", "counter_axis_spacing",
                  ("counterAxisSpacing",), "layout", "number"),
    FigmaProperty("layoutWrap", "layout_wrap", ("layoutWrap",), "layout", "enum"),
    FigmaProperty("layoutPositioning", "layout_positioning",
                  ("layoutPositioning",), "layout", "enum"),

    # === SIZE ===
    FigmaProperty("width", "width", ("width",), "size", "number",
                  override_type="WIDTH"),
    FigmaProperty("height", "height", ("height",), "size", "number",
                  override_type="HEIGHT"),
    FigmaProperty("minWidth", "min_width", ("minWidth",), "size", "number"),
    FigmaProperty("maxWidth", "max_width", ("maxWidth",), "size", "number"),
    FigmaProperty("minHeight", "min_height", ("minHeight",), "size", "number"),
    FigmaProperty("maxHeight", "max_height", ("maxHeight",), "size", "number"),

    # === TEXT ===
    FigmaProperty("characters", "text_content", ("characters",), "text", "string",
                  override_type="TEXT"),
    FigmaProperty("fontSize", "font_size", ("fontSize",), "text", "number"),
    FigmaProperty("fontFamily", "font_family", ("fontName",), "text", "string"),
    FigmaProperty("fontWeight", "font_weight", ("fontWeight",), "text", "number"),
    FigmaProperty("fontStyle", "font_style", (), "text", "string"),
    FigmaProperty("textAlignHorizontal", "text_align",
                  ("textAlignHorizontal",), "text", "enum"),
    FigmaProperty("textAlignVertical", "text_align_v",
                  ("textAlignVertical",), "text", "enum"),
    FigmaProperty("textAutoResize", "text_auto_resize",
                  ("textAutoResize",), "text", "enum"),
    FigmaProperty("textDecoration", "text_decoration",
                  ("textDecoration",), "text", "enum"),
    FigmaProperty("textCase", "text_case", ("textCase",), "text", "enum"),
    FigmaProperty("lineHeight", "line_height", ("lineHeight",), "text", "json",
                  needs_json=True),
    FigmaProperty("letterSpacing", "letter_spacing", ("letterSpacing",), "text", "json",
                  needs_json=True),
    FigmaProperty("paragraphSpacing", "paragraph_spacing",
                  ("paragraphSpacing",), "text", "number"),

    # === CONSTRAINTS ===
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
