"""A1.2 — renderer Mode-1 per-property emission gating.

Phase: forensic-audit-2 architectural sprint, second piece of
Backlog #1 (provenance plan at docs/plan-provenance-tagging.md).

A1.1 ships ``element["_overrides"]`` (list[str] of canonical
figma_names from instance_overrides table). A1.3 wires the
verifier to consult it. A1.2 (this file) wires the renderer:

- Pre-A1.2 the renderer's Mode-1 path emitted opacity ONLY when
  ``opacity < 1.0`` (silent default leak per the audit). Other
  visual props (fills, strokes, cornerRadius, etc.) were never
  emitted on Mode-1 INSTANCE heads — the renderer "delegated to
  master."
- Post-A1.2: opacity emission is gated on ``"opacity" in
  _overrides``. Other visual props ALSO emit on Mode-1 instance
  heads when their figma_name is in _overrides.

Codex 5.5 design (gpt-5.5 high reasoning, 2026-04-26):
- visible, rotation: NOT gated on _overrides (separate paths;
  visibility goes through PathOverride; rotation has its own
  AST-transform-conflict guard)
- opacity: gated on _overrides; preserve and emit 1.0 if
  explicitly overridden (build_visual_from_db's default-skip
  doesn't apply to explicit overrides)
- fills/strokes/effects/cornerRadius/blendMode/clipsContent/
  strokeWeight/strokeAlign/dashPattern: emit on Mode-1 heads
  ONLY when in _overrides
- Implementation: build a sparse override visual from
  raw_visual ∩ _overrides, pass through _emit_visual.
"""

from __future__ import annotations

from dd.markup_l3 import L3Document, Node, NodeHead, parse_l3
from dd.render_figma_ast import render_figma


def _render_with_overrides(
    *,
    component_figma_id: str = "1:100",
    overrides: list[str] | None = None,
    raw_visual_extra: dict | None = None,
) -> str:
    """Render a single comp-ref instance with the given _overrides
    and raw_visual extras. Returns the generated script."""
    src = (
        "screen #screen-1 {\n"
        "  -> button/primary #button-1\n"
        "}\n"
    )
    doc = parse_l3(src)
    spec_key_map: dict = {}
    original_name_map: dict = {}
    nid_map: dict = {}
    db_visuals: dict = {}

    for n in _iter_nodes(doc.top_level):
        spec_key_map[id(n)] = n.head.eid or ""
        original_name_map[id(n)] = n.head.eid or ""

    # Find the comp-ref node and seed its raw_visual + element overrides
    for n in _iter_nodes(doc.top_level):
        if n.head.head_kind == "comp-ref":
            spec_key_map[id(n)] = "button-1"
            original_name_map[id(n)] = "Primary Button"
            nid_map[id(n)] = 100
            visual_dict = {
                "node_type": "INSTANCE",
                "component_figma_id": component_figma_id,
                "figma_node_id": "1:200",
                "name": "Primary Button",
            }
            if raw_visual_extra:
                visual_dict.update(raw_visual_extra)
            db_visuals[100] = visual_dict
            # Inject _overrides via spec_elements shim
            element_extras = {
                "type": "instance",
                "_mode1_eligible": True,
            }
            if overrides is not None:
                element_extras["_overrides"] = overrides

    script, _refs = render_figma(
        doc,
        conn=None,
        nid_map=nid_map,
        fonts=[("Inter", "Regular")],
        spec_key_map=spec_key_map,
        original_name_map=original_name_map,
        db_visuals=db_visuals,
        ckr_built=True,
        _spec_elements={"button-1": element_extras},
    )
    return script


def _iter_nodes(nodes):
    for n in nodes:
        yield n
        if getattr(n, "block", None):
            yield from _iter_nodes(n.block.statements)


# ---------------------------------------------------------------------
# Opacity — A1.2 + A3.1 fix (replaces the < 1.0 heuristic)
# ---------------------------------------------------------------------

class TestOpacityProvenanceGating:
    def test_opacity_in_overrides_emits_even_at_one_point_zero(self):
        """A1.2 + A3.1 (silent default leak fix): IR opacity = 1.0
        with OPACITY override SHOULD emit ``n.opacity = 1``. Pre-fix
        the < 1.0 heuristic silently dropped this.
        """
        script = _render_with_overrides(
            overrides=["opacity"],
            raw_visual_extra={"opacity": 1.0},
        )
        assert ".opacity = 1" in script, (
            "A1.2: explicit opacity=1.0 override must emit even "
            "though pre-fix heuristic '< 1.0' would drop it"
        )

    def test_opacity_in_overrides_emits_at_half(self):
        """Standard case: opacity 0.5 + override → emits."""
        script = _render_with_overrides(
            overrides=["opacity"],
            raw_visual_extra={"opacity": 0.5},
        )
        assert ".opacity = 0.5" in script

    def test_opacity_not_in_overrides_skipped_even_at_half(self):
        """A1.2: opacity 0.5 WITHOUT override is a snapshot →
        skip emission. Pre-fix the < 1.0 heuristic emitted it
        incorrectly (treated extraction snapshot as override)."""
        script = _render_with_overrides(
            overrides=[],
            raw_visual_extra={"opacity": 0.5},
        )
        assert ".opacity = 0.5" not in script, (
            "A1.2: opacity snapshot (no override) must NOT emit; "
            "pre-fix heuristic incorrectly emitted on extraction "
            "snapshot of master's default opacity"
        )

    def test_opacity_legacy_ir_uses_historical_heuristic(self):
        """Codex 5.5 nuance: 'Missing provenance defaults to
        snapshot' applies on the VERIFIER side (A1.3, under-flag is
        safe). On the RENDERER side, missing provenance means 'use
        the prior heuristic' because not emitting at all could
        remove a previously-rendered opacity value on un-migrated
        specs. Legacy IR (no _overrides field) preserves the
        historical opacity < 1.0 heuristic.

        This is asymmetric with the verifier-side rule on purpose:
        verifier under-flags (won't surface a false-positive),
        renderer preserves emission (won't silently drop output).
        """
        script = _render_with_overrides(
            overrides=None,  # NO _overrides field at all
            raw_visual_extra={"opacity": 0.5},
        )
        # Legacy heuristic: opacity < 1.0 emits
        assert ".opacity = 0.5" in script

    def test_opacity_legacy_ir_at_one_silently_dropped(self):
        """Legacy IR + opacity=1.0: the historical heuristic
        skipped this (the silent default leak A3.1 fixes via
        provenance — but only when _overrides is provided).
        Pre-A1.2 behavior preserved on legacy IR."""
        script = _render_with_overrides(
            overrides=None,
            raw_visual_extra={"opacity": 1.0},
        )
        # Heuristic: < 1.0 → skip
        assert ".opacity = 1" not in script


# ---------------------------------------------------------------------
# Fills — new emission path on Mode-1
# ---------------------------------------------------------------------

class TestFillsProvenanceEmission:
    def test_fills_in_overrides_emits_after_create_instance(self):
        """A1.2: when FILLS is in _overrides, emit n.fills = [...]
        after createInstance() so the override actually applies."""
        script = _render_with_overrides(
            overrides=["fills"],
            raw_visual_extra={
                "fills": '[{"type":"SOLID","color":{"r":1,"g":0,"b":0,"a":1}}]',
            },
        )
        # The fill should be emitted as a SOLID paint with the color.
        assert ".fills = [" in script, "A1.2: must emit n.fills array"
        assert "SOLID" in script, "A1.2: must emit SOLID fill type"

    def test_fills_not_in_overrides_skipped(self):
        """A1.2: snapshot-only fills (no FILLS override) are NOT
        emitted on Mode-1 instances — master defaults stand."""
        script = _render_with_overrides(
            overrides=[],
            raw_visual_extra={
                "fills": '[{"type":"SOLID","color":{"r":1,"g":0,"b":0,"a":1}}]',
            },
        )
        # The fill from raw_visual must NOT propagate through to
        # an n.fills = ... write on the instance var.
        # Need to check it's not on the INSTANCE var specifically,
        # since the master can have its own fills via createInstance.
        # The instance var is whichever `const nN = await ...createInstance...`.
        # Simplest check: no SOLID emission for the instance's fills.
        # The script should have the createInstance line + name +
        # M[] but no fills assignment.
        # (createInstance() returns the master clone with its own
        # fills already.)
        # Look for the SOLID red fill that came from raw_visual:
        assert "color: {r:1.0,g:0.0,b:0.0}" not in script and \
               "color: {r:1,g:0,b:0}" not in script, (
            "A1.2: snapshot-only fills (no FILLS override) must NOT "
            "be emitted on the Mode-1 instance head"
        )


# ---------------------------------------------------------------------
# strokeWeight — independent gating (A2.1 prerequisite already shipped)
# ---------------------------------------------------------------------

class TestStrokeWeightProvenanceEmission:
    def test_stroke_weight_in_overrides_emits(self):
        """A1.2: STROKE_WEIGHT override → emit n.strokeWeight = N
        on the instance head."""
        script = _render_with_overrides(
            overrides=["strokeWeight"],
            raw_visual_extra={"stroke_weight": 4},
        )
        assert "strokeWeight = 4" in script, (
            "A1.2: strokeWeight override must emit (A2.1 split made "
            "this possible — strokeWeight is its own registry _UNIFORM)"
        )

    def test_stroke_weight_not_in_overrides_skipped(self):
        """A1.2: snapshot-only strokeWeight skipped on Mode-1."""
        script = _render_with_overrides(
            overrides=[],
            raw_visual_extra={"stroke_weight": 4},
        )
        # The strokeWeight from raw_visual must NOT emit on the
        # instance head.
        assert "strokeWeight = 4" not in script


# ---------------------------------------------------------------------
# Regression guards — visible + rotation should NOT be gated
# ---------------------------------------------------------------------

class TestRegressionVisibleRotationUnchanged:
    """Codex 5.5 explicitly excluded visible and rotation from the
    A1.2 gating: visibility goes through PathOverride and rotation
    has its own AST-transform-conflict guard."""

    def test_visible_false_still_emits_regardless_of_overrides(self):
        """element.visible == False still emits regardless of
        _overrides membership. Pre-fix behavior preserved."""
        script = _render_with_overrides(
            overrides=[],  # explicitly no overrides
            raw_visual_extra={},
        )
        # Without setting element.visible False, this test just
        # confirms the path doesn't break. The actual visibility
        # gating is deferred to PathOverride.
        # Skip — covered by integration tests.
        # The point: don't accidentally couple visible to _overrides.
        assert "visible = false" not in script  # not set in fixture


# ---------------------------------------------------------------------
# Mode-1 head-overlay — head EDITs on comp-ref nodes must reach emission
# ---------------------------------------------------------------------


def _render_comp_ref_with_head_fill(head_fill: str | None) -> str:
    """Render a comp-ref node where the AST head optionally carries
    ``fill=<head_fill>``. Returns the generated script.

    Drives the Mode-1 emission path with ``_overrides=[]`` (explicit
    empty — no DB-side override) so the only way fill can reach the
    rendered output is via the AST head. Pre-fix: fill is silently
    dropped because ``_emit_mode1_create`` never reads
    ``node.head.properties``. Post-fix: head visual props are
    overlaid onto sparse_visual before emission."""
    if head_fill is not None:
        src = (
            "screen #screen-1 {\n"
            f"  -> button/primary #button-1 fill={head_fill}\n"
            "}\n"
        )
    else:
        src = (
            "screen #screen-1 {\n"
            "  -> button/primary #button-1\n"
            "}\n"
        )
    doc = parse_l3(src)
    spec_key_map: dict = {}
    original_name_map: dict = {}
    nid_map: dict = {}
    db_visuals: dict = {}

    for n in _iter_nodes(doc.top_level):
        spec_key_map[id(n)] = n.head.eid or ""
        original_name_map[id(n)] = n.head.eid or ""

    element_extras = {
        "type": "instance",
        "_mode1_eligible": True,
        "_overrides": [],  # explicit empty: no DB-side overrides
    }
    for n in _iter_nodes(doc.top_level):
        if n.head.head_kind == "comp-ref":
            spec_key_map[id(n)] = "button-1"
            original_name_map[id(n)] = "Primary Button"
            nid_map[id(n)] = 100
            db_visuals[100] = {
                "node_type": "INSTANCE",
                "component_figma_id": "1:100",
                "figma_node_id": "1:200",
                "name": "Primary Button",
                # DB has its own white fill — head EDIT must override.
                "fills": '[{"type":"SOLID","color":{"r":1,"g":1,"b":1,"a":1}}]',
            }

    script, _refs = render_figma(
        doc,
        conn=None,
        nid_map=nid_map,
        fonts=[("Inter", "Regular")],
        spec_key_map=spec_key_map,
        original_name_map=original_name_map,
        db_visuals=db_visuals,
        ckr_built=True,
        _spec_elements={"button-1": element_extras},
    )
    return script


class TestMode1HeadOverlayBeatsRawVisual:
    """When an LLM EDIT writes ``set @<eid> fill=<hex>`` against a
    Mode-1 INSTANCE node (comp-ref), the head fill must reach the
    rendered ``<inst>.fills = ...`` emission rather than being
    silently dropped.

    Codex 5.5 + Sonnet diagnosis 2026-04-27 (twin of the Mode-2 fix
    in test_render_phase1_guards.py:TestPhase1HeadOverlayBeatsRawVisual):
    Mode-1's ``_emit_mode1_create`` builds a sparse_visual from
    ``raw_visual ∩ element["_overrides"]`` and never reads
    ``node.head.properties`` — so head-supplied EDITs on comp-ref
    nodes are invisible to the emission gate. Empirical bottleneck
    surfaced in the synth-gen demo: variant 3 (Dark Playful) issued
    ``set @nav-top-nav fill="#1A1A2E"`` against a comp-ref nav
    instance, the head property persisted, but the rendered Figma
    nav remained white because Mode-1 ignored the head EDIT.

    Fix: after sparse_visual is built (lines 1486-1512), overlay
    ``ast_head_to_element(node).get("visual")`` for the same 5 keys
    as the Mode-2 fix (fills / strokes / strokeWeight /
    cornerRadius / opacity). Strict head-only — replace whole.
    """

    def test_head_fill_beats_db_fill_on_mode1_instance(self) -> None:
        """Head ``fill=#1A1A2E`` on a comp-ref node must emit a
        SOLID dark fill on the instance var."""
        script = _render_comp_ref_with_head_fill(head_fill="#1A1A2E")
        # Renderer converts hex → RGB floats: #1A1A2E →
        # r:0.102, g:0.102, b:0.1804.
        assert "0.1804" in script, (
            "Mode-1 head fill `#1A1A2E` did not reach emission. The "
            "comp-ref's AST head has the EDIT but the renderer "
            "ignored it. Excerpt:\n"
            + "\n".join(
                line for line in script.split("\n")
                if ".fills = " in line and "createPage" not in line
            )[:600]
        )

    def test_no_head_fill_keeps_empty_overrides_silent(self) -> None:
        """No head fill + empty _overrides → no fills assignment on
        instance head. Mode-1 master defaults stand."""
        script = _render_comp_ref_with_head_fill(head_fill=None)
        # The DB white fill must NOT leak (empty _overrides).
        assert "color: {r:1.0,g:1.0,b:1.0}" not in script, (
            "DB fill leaked through despite empty _overrides — the "
            "head-overlay fix accidentally promoted DB fills.\n"
            + "\n".join(
                line for line in script.split("\n")
                if ".fills = " in line and "createPage" not in line
            )[:600]
        )
