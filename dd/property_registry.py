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

import enum
from dataclasses import dataclass, field, replace
from typing import Any


# Sentinel: property is emitted by a handler function registered in the renderer.
# The renderer's _FIGMA_HANDLERS dict maps figma_name → callable.
HANDLER = object()


# ---------------------------------------------------------------------------
# Sprint 2 — Station disposition vocabulary
# ---------------------------------------------------------------------------
# Per docs/plan-sprint-2-station-parity.md §4 (Codex 5.5 round-5
# locked decision): every figma-emittable property has a known
# disposition at every pipeline station. The registry is the
# single source of truth; generated artifacts (walker manifest)
# derive from it.
#
# C4 ships only the schema + safe defaults; C5 wires real values
# per property; C6+ derives the walker manifest; C10 wires
# verifier dispatch.

class StationDisposition(enum.Enum):
    # ===  Station 2 — Renderer (dd/renderers/figma.py) ===
    EMIT_HANDLER = "emit_handler"
    """Custom Python emit function registered in _FIGMA_HANDLERS."""

    EMIT_UNIFORM = "emit_uniform"
    """Emitted via the _UNIFORM template ``{var}.{figma_name} = {value};``."""

    EMIT_DEFERRED = "emit_deferred"
    """Capability gate or context (e.g. parent auto-layout) skips emission."""

    NOT_EMITTABLE = "not_emittable"
    """Capability table excludes this property from all node types."""

    # ===  Station 3 — Walker (render_test/walk_ref.js) ===
    CAPTURED = "captured"
    """Walker reads this property from Figma DOM and includes in walk output."""

    NOT_CAPTURED_SUPPORTED = "not_captured_supported"
    """Walker COULD read but doesn't today (Sprint 3+ work item)."""

    NOT_CAPTURED_UNSUPPORTED = "not_captured_unsupported"
    """Figma Plugin API doesn't expose this property; walker cannot capture."""

    DEDICATED_PATH = "dedicated_path"
    """Captured via top-level rendered-tree fields (e.g. width/height
    at entry root), not via figma_name lookup. Equivalent to
    captured for verifier purposes but routes differently."""

    # ===  Station 4 — Verifier (dd/verify_figma.py) ===
    COMPARE_DISPATCH = "compare_dispatch"
    """Compared via the registry's compare_figma metadata (Sprint-2 dispatch)."""

    COMPARE_DEDICATED = "compare_dedicated"
    """Compared via a dedicated KIND_* path (e.g. KIND_BOUNDS_MISMATCH,
    KIND_MASK_MISMATCH). Equivalent to compared for ship gate purposes."""

    EXEMPT_REASON = "exempt_reason"
    """Documented exemption with reason code; verifier intentionally
    skips comparison. Reason captured separately in test exemption table."""


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
    # Sprint 2 — per-station disposition (see StationDisposition above
    # and docs/plan-sprint-2-station-parity.md). C4 sets safe defaults
    # (NOT_EMITTABLE / NOT_CAPTURED_SUPPORTED / EXEMPT_REASON) so this
    # commit is no-op for every existing property; C5 inventories real
    # values per property.
    station_2: StationDisposition = StationDisposition.NOT_EMITTABLE
    station_3: StationDisposition = StationDisposition.NOT_CAPTURED_SUPPORTED
    station_4: StationDisposition = StationDisposition.EXEMPT_REASON


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
# Sprint 2 C5 — station inventory
# ---------------------------------------------------------------------------
# Per docs/plan-sprint-2-station-parity.md §3 (station model) and §10 R4
# (Codex's inventory-churn risk mitigation: "C5 may use conservative
# dispositions with explicit TODO reasons").
#
# Dispositions are declared as one table per station and applied by
# replacing each FigmaProperty in PROPERTIES with a dispositioned copy.
# Single source of truth: this file. Generated artifacts (e.g. walker
# manifest in C6) read from the dispositioned PROPERTIES tuple.
#
# Audit basis (2026-04-27):
#   Station 2: emit={...} contents in PROPERTIES declarations above
#   Station 3: render_test/walk_ref.js entry.* assignments (lines 185-326)
#   Station 4: dd/verify_figma.py kind=KIND_* paths (lines 213-715)

_STATION_2_INVENTORY: dict[str, StationDisposition] = {
    # === EMIT_HANDLER — custom Python emit fn ===
    "fills": StationDisposition.EMIT_HANDLER,
    "strokes": StationDisposition.EMIT_HANDLER,
    "effects": StationDisposition.EMIT_HANDLER,
    "clipsContent": StationDisposition.EMIT_HANDLER,
    "arcData": StationDisposition.EMIT_HANDLER,
    "cornerRadius": StationDisposition.EMIT_HANDLER,
    # === EMIT_UNIFORM — _UNIFORM template ===
    "strokeWeight": StationDisposition.EMIT_UNIFORM,
    "strokeAlign": StationDisposition.EMIT_UNIFORM,
    "strokeCap": StationDisposition.EMIT_UNIFORM,
    "strokeJoin": StationDisposition.EMIT_UNIFORM,
    "dashPattern": StationDisposition.EMIT_UNIFORM,
    "opacity": StationDisposition.EMIT_UNIFORM,
    "blendMode": StationDisposition.EMIT_UNIFORM,
    "rotation": StationDisposition.EMIT_UNIFORM,
    "isMask": StationDisposition.EMIT_UNIFORM,
    "cornerSmoothing": StationDisposition.EMIT_UNIFORM,
    "booleanOperation": StationDisposition.EMIT_UNIFORM,
    "layoutMode": StationDisposition.EMIT_UNIFORM,
    "primaryAxisAlignItems": StationDisposition.EMIT_UNIFORM,
    "counterAxisAlignItems": StationDisposition.EMIT_UNIFORM,
    "paddingTop": StationDisposition.EMIT_UNIFORM,
    "paddingRight": StationDisposition.EMIT_UNIFORM,
    "paddingBottom": StationDisposition.EMIT_UNIFORM,
    "paddingLeft": StationDisposition.EMIT_UNIFORM,
    "itemSpacing": StationDisposition.EMIT_UNIFORM,
    "counterAxisSpacing": StationDisposition.EMIT_UNIFORM,
    "layoutWrap": StationDisposition.EMIT_UNIFORM,
    "layoutPositioning": StationDisposition.EMIT_UNIFORM,
    "minWidth": StationDisposition.EMIT_UNIFORM,
    "maxWidth": StationDisposition.EMIT_UNIFORM,
    "minHeight": StationDisposition.EMIT_UNIFORM,
    "maxHeight": StationDisposition.EMIT_UNIFORM,
    "fontSize": StationDisposition.EMIT_UNIFORM,
    "fontStyle": StationDisposition.EMIT_UNIFORM,
    "textAlignHorizontal": StationDisposition.EMIT_UNIFORM,
    "textAlignVertical": StationDisposition.EMIT_UNIFORM,
    "textAutoResize": StationDisposition.EMIT_UNIFORM,
    "textDecoration": StationDisposition.EMIT_UNIFORM,
    "textCase": StationDisposition.EMIT_UNIFORM,
    "lineHeight": StationDisposition.EMIT_UNIFORM,
    "letterSpacing": StationDisposition.EMIT_UNIFORM,
    "paragraphSpacing": StationDisposition.EMIT_UNIFORM,
    "leadingTrim": StationDisposition.EMIT_UNIFORM,
    # === EMIT_DEFERRED — handled outside _emit_visual ===
    "visible": StationDisposition.EMIT_DEFERRED,
    "layoutSizingHorizontal": StationDisposition.EMIT_DEFERRED,
    "layoutSizingVertical": StationDisposition.EMIT_DEFERRED,
    "width": StationDisposition.EMIT_DEFERRED,
    "height": StationDisposition.EMIT_DEFERRED,
    "characters": StationDisposition.EMIT_DEFERRED,
    "fontFamily": StationDisposition.EMIT_DEFERRED,
    "fontWeight": StationDisposition.EMIT_DEFERRED,
    "constraints.horizontal": StationDisposition.EMIT_DEFERRED,
    "constraints.vertical": StationDisposition.EMIT_DEFERRED,
}

_STATION_3_INVENTORY: dict[str, StationDisposition] = {
    # === DEDICATED_PATH — top-level entry fields ===
    "width": StationDisposition.DEDICATED_PATH,
    "height": StationDisposition.DEDICATED_PATH,
    "rotation": StationDisposition.DEDICATED_PATH,
    # === CAPTURED — explicit entry.<figma_name> assignment ===
    "fills": StationDisposition.CAPTURED,
    "strokes": StationDisposition.CAPTURED,
    "strokeWeight": StationDisposition.CAPTURED,
    "strokeAlign": StationDisposition.CAPTURED,
    "dashPattern": StationDisposition.CAPTURED,
    "opacity": StationDisposition.CAPTURED,
    "blendMode": StationDisposition.CAPTURED,
    "isMask": StationDisposition.CAPTURED,
    "cornerRadius": StationDisposition.CAPTURED,
    "clipsContent": StationDisposition.CAPTURED,
    "characters": StationDisposition.CAPTURED,
    "textAutoResize": StationDisposition.CAPTURED,
    "effects": StationDisposition.CAPTURED,  # captured as effectCount (count only)
    # === NOT_CAPTURED_SUPPORTED — walker COULD but doesn't (Sprint 3+) ===
    "strokeCap": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "strokeJoin": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "cornerSmoothing": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "booleanOperation": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "arcData": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "visible": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "layoutSizingHorizontal": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "layoutSizingVertical": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "layoutMode": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "primaryAxisAlignItems": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "counterAxisAlignItems": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "paddingTop": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "paddingRight": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "paddingBottom": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "paddingLeft": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "itemSpacing": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "counterAxisSpacing": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "layoutWrap": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "layoutPositioning": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "minWidth": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "maxWidth": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "minHeight": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "maxHeight": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "fontFamily": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "fontWeight": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "fontSize": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "fontStyle": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "textAlignHorizontal": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "textAlignVertical": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "textDecoration": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "textCase": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "lineHeight": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "letterSpacing": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "paragraphSpacing": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "leadingTrim": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "constraints.horizontal": StationDisposition.NOT_CAPTURED_SUPPORTED,
    "constraints.vertical": StationDisposition.NOT_CAPTURED_SUPPORTED,
}

_STATION_4_INVENTORY: dict[str, StationDisposition] = {
    # === COMPARE_DEDICATED — explicit KIND_* dedicated path ===
    "width": StationDisposition.COMPARE_DEDICATED,  # KIND_BOUNDS_MISMATCH
    "height": StationDisposition.COMPARE_DEDICATED,  # KIND_BOUNDS_MISMATCH
    "fills": StationDisposition.COMPARE_DEDICATED,
    "strokes": StationDisposition.COMPARE_DEDICATED,
    "strokeWeight": StationDisposition.COMPARE_DEDICATED,
    "strokeAlign": StationDisposition.COMPARE_DEDICATED,
    "dashPattern": StationDisposition.COMPARE_DEDICATED,
    "opacity": StationDisposition.COMPARE_DEDICATED,
    "blendMode": StationDisposition.COMPARE_DEDICATED,
    "rotation": StationDisposition.COMPARE_DEDICATED,
    "isMask": StationDisposition.COMPARE_DEDICATED,
    "cornerRadius": StationDisposition.COMPARE_DEDICATED,
    "clipsContent": StationDisposition.COMPARE_DEDICATED,
    "effects": StationDisposition.COMPARE_DEDICATED,
    # === EXEMPT_REASON — no comparator today ===
    # Sprint 2 graduates 3 of these to COMPARE_DISPATCH via C10:
    # characters, layoutSizingHorizontal, layoutSizingVertical.
    # All others stay until their family sprint.
    "characters": StationDisposition.EXEMPT_REASON,
    "layoutSizingHorizontal": StationDisposition.EXEMPT_REASON,
    "layoutSizingVertical": StationDisposition.EXEMPT_REASON,
    "strokeCap": StationDisposition.EXEMPT_REASON,
    "strokeJoin": StationDisposition.EXEMPT_REASON,
    "cornerSmoothing": StationDisposition.EXEMPT_REASON,
    "booleanOperation": StationDisposition.EXEMPT_REASON,
    "arcData": StationDisposition.EXEMPT_REASON,
    "visible": StationDisposition.EXEMPT_REASON,
    "layoutMode": StationDisposition.EXEMPT_REASON,
    "primaryAxisAlignItems": StationDisposition.EXEMPT_REASON,
    "counterAxisAlignItems": StationDisposition.EXEMPT_REASON,
    "paddingTop": StationDisposition.EXEMPT_REASON,
    "paddingRight": StationDisposition.EXEMPT_REASON,
    "paddingBottom": StationDisposition.EXEMPT_REASON,
    "paddingLeft": StationDisposition.EXEMPT_REASON,
    "itemSpacing": StationDisposition.EXEMPT_REASON,
    "counterAxisSpacing": StationDisposition.EXEMPT_REASON,
    "layoutWrap": StationDisposition.EXEMPT_REASON,
    "layoutPositioning": StationDisposition.EXEMPT_REASON,
    "minWidth": StationDisposition.EXEMPT_REASON,
    "maxWidth": StationDisposition.EXEMPT_REASON,
    "minHeight": StationDisposition.EXEMPT_REASON,
    "maxHeight": StationDisposition.EXEMPT_REASON,
    "fontFamily": StationDisposition.EXEMPT_REASON,
    "fontWeight": StationDisposition.EXEMPT_REASON,
    "fontSize": StationDisposition.EXEMPT_REASON,
    "fontStyle": StationDisposition.EXEMPT_REASON,
    "textAlignHorizontal": StationDisposition.EXEMPT_REASON,
    "textAlignVertical": StationDisposition.EXEMPT_REASON,
    "textAutoResize": StationDisposition.EXEMPT_REASON,
    "textDecoration": StationDisposition.EXEMPT_REASON,
    "textCase": StationDisposition.EXEMPT_REASON,
    "lineHeight": StationDisposition.EXEMPT_REASON,
    "letterSpacing": StationDisposition.EXEMPT_REASON,
    "paragraphSpacing": StationDisposition.EXEMPT_REASON,
    "leadingTrim": StationDisposition.EXEMPT_REASON,
    "constraints.horizontal": StationDisposition.EXEMPT_REASON,
    "constraints.vertical": StationDisposition.EXEMPT_REASON,
}


def _apply_inventory(
    properties: tuple[FigmaProperty, ...],
) -> tuple[FigmaProperty, ...]:
    """Replace each property with a dispositioned copy. The
    inventories are exhaustive — every property must appear in
    every inventory (a test asserts this). Construction-time
    failure if a property is missing from any inventory."""
    out: list[FigmaProperty] = []
    for p in properties:
        s2 = _STATION_2_INVENTORY.get(p.figma_name)
        s3 = _STATION_3_INVENTORY.get(p.figma_name)
        s4 = _STATION_4_INVENTORY.get(p.figma_name)
        if s2 is None or s3 is None or s4 is None:
            missing = []
            if s2 is None:
                missing.append("station_2")
            if s3 is None:
                missing.append("station_3")
            if s4 is None:
                missing.append("station_4")
            raise RuntimeError(
                f"Sprint 2 C5 inventory missing {missing} for "
                f"property {p.figma_name!r}. Add disposition to the "
                f"corresponding _STATION_N_INVENTORY dict."
            )
        out.append(replace(p, station_2=s2, station_3=s3, station_4=s4))
    return tuple(out)


# Apply inventory to PROPERTIES — fixed-point dispositioned tuple.
# Downstream code reads PROPERTIES as before; the dispositions are
# now populated rather than defaulted.
PROPERTIES = _apply_inventory(PROPERTIES)


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
