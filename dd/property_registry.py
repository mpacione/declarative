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
class FigmaComparatorSpec:
    """Declarative comparator metadata for the Figma backend's verifier.

    Sprint-2 architectural seam (Codex 5.5 sequencing call): registry
    declares ``compare_figma=`` per property; ``dd/verify_figma.py``
    owns the implementation map keyed by ``comparator``. Keeps the
    registry declarative — no verifier-code imports leak into the
    property registry.

    Backend-shaped naming: explicit ``compare_figma`` field +
    ``FigmaComparatorSpec`` class so future backends grow as
    sibling fields/classes (``compare_html``, ``HTMLComparatorSpec``)
    rather than a forced refactor of the existing surface.

    Promotability: if/when backend #2 lands and we see two real
    examples of the comparator-shape, this collapses cleanly to
    ``compare={"figma": ..., "html": ...}`` without re-shaping
    callers.
    """

    comparator: str
    """Implementation id. ``dd/verify_figma.py`` owns the map
    ``{id → callable}``. Keeps registry declarative + serializable."""

    walker_key: str
    """Field name in the rendered tree (per-node dict from
    ``render_test/walk_ref.js``) where the comparator reads the
    rendered value."""

    kind: str
    """``KIND_*`` string from ``dd/boundary.py`` — what error kind
    this comparator emits when it finds drift."""

    tolerance: float | None = None
    """For numeric comparators: absolute tolerance for float
    equality. None means exact equality."""

    skip_when_provenance_absent: bool = True
    """Mirrors A1.3 (``_is_snapshot_skip``): on Mode-1 INSTANCE,
    skip comparison if the property isn't in the head's
    ``_overrides`` side-car (i.e. the IR value is a master-default
    snapshot, not an actual override). Most visual comparators
    want this; bounds/structure comparators set False."""


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
    # Sprint-2: how this property is verified on the Figma backend.
    # ``None`` means the property has no comparator declared today —
    # the coverage harness in tests/test_figma_verifier_coverage.py
    # will require either a spec OR an explicit exemption per the
    # sprint-2 ladder (commits 2-7 wire each existing/new comparator).
    compare_figma: FigmaComparatorSpec | None = None


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
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="paint_list_equality",
                      walker_key="fills",
                      kind="fill_mismatch",
                  )),

    # === VISUAL: Strokes ===
    FigmaProperty("strokes", "strokes", ("strokes",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": HANDLER},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="paint_list_equality",
                      walker_key="strokes",
                      kind="stroke_mismatch",
                  )),
    FigmaProperty("strokeWeight", "stroke_weight", ("strokeWeight",), "visual", "number",
                  emit={"figma": _UNIFORM},
                  token_binding_path="strokeWeight",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="numeric_equality",
                      walker_key="strokeWeight",
                      kind="stroke_weight_mismatch",
                  )),
    FigmaProperty("strokeAlign", "stroke_align", ("strokeAlign",), "visual", "enum",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="enum_equality",
                      walker_key="strokeAlign",
                      kind="stroke_align_mismatch",
                  )),
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
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="list_equality",
                      walker_key="dashPattern",
                      kind="dash_pattern_mismatch",
                  )),

    # === VISUAL: Effects ===
    FigmaProperty("effects", "effects", ("effects",), "visual", "json_array",
                  needs_json=True,
                  emit={"figma": HANDLER},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="effect_count_equality",
                      walker_key="effects",
                      kind="effect_missing",
                  )),

    # === VISUAL: Appearance ===
    FigmaProperty("opacity", "opacity", ("opacity",), "visual", "number",
                  override_type="OPACITY", default_value=1.0,
                  emit={"figma": _UNIFORM},
                  token_binding_path="opacity",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="numeric_equality",
                      walker_key="opacity",
                      kind="opacity_mismatch",
                      tolerance=0.001,
                  )),
    FigmaProperty("blendMode", "blend_mode", ("blendMode",), "visual", "enum",
                  default_value="PASS_THROUGH",
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="enum_equality",
                      walker_key="blendMode",
                      kind="blendmode_mismatch",
                  )),
    # Deferred: handled in main generation loop (element.visible), not _emit_visual
    FigmaProperty("visible", "visible", ("visible",), "visual", "boolean",
                  override_type="BOOLEAN", default_value=True,
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE)),
    FigmaProperty("clipsContent", "clips_content", ("clipsContent",), "visual", "boolean",
                  default_value=True, skip_emit_if_default=False,
                  emit={"figma": HANDLER},
                  capabilities=_figma_caps(_FIGMA_CONTAINERS),
                  compare_figma=FigmaComparatorSpec(
                      comparator="bool_equality",
                      walker_key="clipsContent",
                      kind="clips_content_mismatch",
                  )),
    FigmaProperty("rotation", "rotation", ("rotation",), "visual", "number_radians",
                  default_value=0,
                  emit={"figma": _UNIFORM},
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="numeric_equality",
                      walker_key="rotation",
                      kind="rotation_mismatch",
                  )),
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
                  capabilities=_figma_caps(_FIGMA_CORNER_CAPABLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="corner_radius_equality",
                      walker_key="cornerRadius",
                      kind="cornerradius_mismatch",
                  )),

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
    # Codex 5.5 sprint-2 round-4 call: wire bounds via compare_figma
    # rather than exemption-as-dedicated-path, proving the dispatch
    # model can target non-generic comparators.
    FigmaProperty("width", "width", ("width",), "size", "number",
                  override_type="WIDTH",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="bounds_equality",
                      walker_key="width",
                      kind="bounds_mismatch",
                      skip_when_provenance_absent=False,
                  )),
    FigmaProperty("height", "height", ("height",), "size", "number",
                  override_type="HEIGHT",
                  capabilities=_figma_caps(_FIGMA_ALL_VISIBLE),
                  compare_figma=FigmaComparatorSpec(
                      comparator="bounds_equality",
                      walker_key="height",
                      kind="bounds_mismatch",
                      skip_when_provenance_absent=False,
                  )),
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
    # leadingTrim trims the text node's bounding box to cap-height
    # (or CAP_HEIGHT) when enabled, producing a tighter box than the
    # default "NONE" which includes full line-height padding. Crucial
    # for visually centering text within fixed-height non-auto-layout
    # parents: a Workshop label at Inter 20pt Semi Bold is 15px with
    # CAP_HEIGHT vs 24px with NONE.
    FigmaProperty("leadingTrim", "leading_trim",
                  ("leadingTrim",), "text", "enum",
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
