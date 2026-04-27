"""A1.3 — verifier per-prop gating using ``element["_overrides"]``.

Phase: forensic-audit-2 architectural sprint, Backlog #1
implementation (provenance plan at
``docs/plan-provenance-tagging.md``).

Pre-A1.3 the verifier had a NARROW chip-1 suppression: skip
fill_mismatch IFF rendered.type=='INSTANCE' AND IR has no solid
fills AND all IR fills are gradient-* with token-ref colors. That
covered 3 cases on Phase E (screens 24, 25, 44) but doesn't
handle the broader extraction-snapshot-vs-master-default class
where IR has a SOLID stroke and the master has a different
SOLID stroke.

Post-A1.3 (this test file): the verifier consults
``element["_overrides"]`` per prop. When the rendered node is an
INSTANCE AND the prop is NOT in ``_overrides``, the comparison
is skipped (snapshot, not override). The narrow chip-1
suppression is subsumed by the per-property gate and removed.

Codex 5.5 design (gpt-5.5 high reasoning, 2026-04-26):
"Verifier rule: override → enforce rendered match; snapshot on
Mode-1 INSTANCE head → skip paint comparison. Missing provenance
on Mode-1 INSTANCE defaults to snapshot, not override (safer to
under-flag than over-flag false-positives)."
"""

from __future__ import annotations

from dd.boundary import (
    KIND_BLENDMODE_MISMATCH,
    KIND_CORNERRADIUS_MISMATCH,
    KIND_FILL_MISMATCH,
    KIND_OPACITY_MISMATCH,
    KIND_STROKE_MISMATCH,
)
from dd.verify_figma import FigmaRenderVerifier


def _ir(eid: str, *, visual: dict, type_: str = "instance",
        overrides: list[str] | None = None) -> dict:
    el: dict = {"type": type_, "visual": visual}
    if overrides is not None:
        el["_overrides"] = overrides
    return {"elements": {eid: el}}


def _rendered(eid: str, *, type_: str = "INSTANCE", **fields) -> dict:
    entry = {"type": type_, "name": fields.pop("name", "test"), **fields}
    return {"eid_map": {eid: entry}, "errors": []}


# ---------------------------------------------------------------------
# Fill mismatch — provenance gating
# ---------------------------------------------------------------------

class TestFillMismatchProvenanceGating:
    """When IR fills differ from rendered fills on a Mode-1
    INSTANCE head, the verifier should flag iff fills is in
    ``_overrides``."""

    def test_instance_snapshot_skipped(self):
        """No _overrides → IR fills is a snapshot → skip the
        comparison even though IR (snapshot of master defaults)
        differs from rendered (the runtime master defaults)."""
        ir = _ir("e1", visual={
            "fills": [{"type": "solid", "color": "#222529"}],
        }, overrides=[])  # explicitly no overrides
        rendered = _rendered("e1",
            fills=[{"type": "solid", "color": "#FFFFFF"}],
        )
        report = FigmaRenderVerifier().verify(ir, rendered)
        fill_errs = [e for e in report.errors if e.kind == KIND_FILL_MISMATCH]
        assert not fill_errs, (
            "A1.3: IR fills snapshot on INSTANCE head must NOT trigger "
            "fill_mismatch when not in _overrides"
        )

    def test_instance_override_enforced(self):
        """IR fills IS in _overrides → genuine override; verifier
        compares + flags drift."""
        ir = _ir("e1", visual={
            "fills": [{"type": "solid", "color": "#222529"}],
        }, overrides=["fills"])
        rendered = _rendered("e1",
            fills=[{"type": "solid", "color": "#FFFFFF"}],
        )
        report = FigmaRenderVerifier().verify(ir, rendered)
        fill_errs = [e for e in report.errors if e.kind == KIND_FILL_MISMATCH]
        assert len(fill_errs) >= 1, (
            "A1.3: when fills IS in _overrides, the override didn't take "
            "and the verifier MUST flag fill_mismatch"
        )

    def test_non_instance_always_compared(self):
        """Non-INSTANCE nodes (frames, rectangles) don't have the
        snapshot ambiguity — provenance gating doesn't apply, the
        normal comparison fires regardless of _overrides."""
        ir = _ir("e1", visual={
            "fills": [{"type": "solid", "color": "#222529"}],
        }, type_="frame", overrides=[])
        rendered = _rendered("e1", type_="FRAME",
            fills=[{"type": "solid", "color": "#FFFFFF"}],
        )
        report = FigmaRenderVerifier().verify(ir, rendered)
        fill_errs = [e for e in report.errors if e.kind == KIND_FILL_MISMATCH]
        assert len(fill_errs) >= 1, (
            "A1.3: non-INSTANCE nodes get the normal comparison; "
            "_overrides gating is INSTANCE-only"
        )

    def test_instance_no_overrides_field_at_all_skipped(self):
        """When the IR has no _overrides field at all (legacy data),
        default to 'snapshot' (don't flag) — safer to under-flag
        than over-flag."""
        ir = {"elements": {"e1": {
            "type": "instance",
            "visual": {
                "fills": [{"type": "solid", "color": "#222529"}],
            },
            # No _overrides key
        }}}
        rendered = _rendered("e1",
            fills=[{"type": "solid", "color": "#FFFFFF"}],
        )
        report = FigmaRenderVerifier().verify(ir, rendered)
        fill_errs = [e for e in report.errors if e.kind == KIND_FILL_MISMATCH]
        assert not fill_errs, (
            "A1.3: missing _overrides on INSTANCE defaults to snapshot "
            "(per Codex: under-flag is safer than over-flag)"
        )


# ---------------------------------------------------------------------
# Stroke mismatch — same gating
# ---------------------------------------------------------------------

class TestStrokeMismatchProvenanceGating:
    """Stroke comparator gets the same provenance gate. This is
    the headline case: 7 iPhone screens (50-55, 57) had snapshot
    stroke colors flagged as drift pre-A1.3."""

    def test_instance_snapshot_skipped(self):
        ir = _ir("e1", visual={
            "strokes": [{"type": "solid", "color": "#222529"}],
        }, overrides=[])
        rendered = _rendered("e1",
            strokes=[{"type": "solid", "color": "#FFFFFF"}],
        )
        report = FigmaRenderVerifier().verify(ir, rendered)
        stroke_errs = [e for e in report.errors if e.kind == KIND_STROKE_MISMATCH]
        assert not stroke_errs, (
            "A1.3: IR strokes snapshot on INSTANCE head must NOT "
            "trigger stroke_mismatch when not in _overrides"
        )

    def test_instance_override_enforced(self):
        ir = _ir("e1", visual={
            "strokes": [{"type": "solid", "color": "#222529"}],
        }, overrides=["strokes"])
        rendered = _rendered("e1",
            strokes=[{"type": "solid", "color": "#FFFFFF"}],
        )
        report = FigmaRenderVerifier().verify(ir, rendered)
        stroke_errs = [e for e in report.errors if e.kind == KIND_STROKE_MISMATCH]
        assert len(stroke_errs) >= 1


# ---------------------------------------------------------------------
# Other visual-prop comparators get the same gate
# ---------------------------------------------------------------------

class TestOtherCompareratorsProvenanceGating:
    """opacity, blendMode, cornerRadius (the comparators added in
    P1c) all need the same per-prop snapshot guard."""

    def test_opacity_snapshot_skipped_on_instance(self):
        ir = _ir("e1", visual={"opacity": 0.5}, overrides=[])
        rendered = _rendered("e1", opacity=1.0)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_OPACITY_MISMATCH]
        assert not errs

    def test_opacity_override_enforced(self):
        ir = _ir("e1", visual={"opacity": 0.5}, overrides=["opacity"])
        rendered = _rendered("e1", opacity=1.0)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_OPACITY_MISMATCH]
        assert len(errs) == 1

    def test_blend_mode_snapshot_skipped_on_instance(self):
        ir = _ir("e1", visual={"blendMode": "MULTIPLY"}, overrides=[])
        rendered = _rendered("e1", blendMode="NORMAL")
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_BLENDMODE_MISMATCH]
        assert not errs

    def test_corner_radius_snapshot_skipped_on_instance(self):
        ir = _ir("e1", visual={"cornerRadius": 8}, overrides=[])
        rendered = _rendered("e1", cornerRadius=0)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_CORNERRADIUS_MISMATCH]
        assert not errs

    def test_corner_radius_override_enforced(self):
        ir = _ir("e1", visual={"cornerRadius": 8}, overrides=["cornerRadius"])
        rendered = _rendered("e1", cornerRadius=0)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_CORNERRADIUS_MISMATCH]
        assert len(errs) == 1


# ---------------------------------------------------------------------
# Regression: chip-1 case still suppressed
# ---------------------------------------------------------------------

class TestChip1RegressionAfterSubsumed:
    """The narrow chip-1 token-bound gradient suppression at
    verify_figma:353-383 is removed in A1.3 — subsumed by the
    new per-property provenance gate. This test pins that the
    chip-1 case still doesn't flag."""

    def test_chip_1_token_gradient_no_solid_no_error(self):
        """chip-1: INSTANCE head with token-bound gradient IR fills
        + solid rendered fills. Pre-A1.3 the narrow suppression
        skipped this. Post-A1.3 the per-property gate skips it
        because INSTANCE + fills not in _overrides."""
        ir = _ir(
            "chip-1",
            visual={
                "fills": [{
                    "type": "gradient-linear",
                    "stops": [
                        {"color": "{color.surface.14}", "position": 0.0},
                        {"color": "{color.surface.33}", "position": 1.0},
                    ],
                }],
            },
            overrides=[],  # no FILLS override on chip-1
        )
        rendered = _rendered(
            "chip-1",
            name="Chip/Activity Succeeded",
            fills=[{"type": "solid", "color": "#3BC98D"}],
        )
        report = FigmaRenderVerifier().verify(ir, rendered)
        fill_errs = [e for e in report.errors if e.kind == KIND_FILL_MISMATCH]
        assert not fill_errs, (
            "A1.3 regression: chip-1 must still pass post-removal of "
            "the narrow token-gradient suppression."
        )
