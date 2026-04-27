"""A5 — verifier comparators for already-carried-but-not-compared
visual props.

The architectural audit at audit/architectural-flow-matrix-20260426.md
identified Pattern G: "Verifier comparator gaps for already-carried
IR props." After P1 closed comparators for opacity/blendMode/rotation/
isMask/cornerRadius, several visual props remain carried in the IR
but never compared by the verifier:

- strokeWeight (registry-driven via _UNIFORM)
- strokeAlign (registry-driven)
- dashPattern (registry-driven, JSON array)
- clipsContent (handler-driven)

Drift on any of these surfaces as a silent ``is_parity: True`` even
though the rendered node visibly differs from the IR.

A5 ships:
1. New KIND_* constants in dd/boundary.py:
   - KIND_STROKE_WEIGHT_MISMATCH
   - KIND_STROKE_ALIGN_MISMATCH
   - KIND_DASH_PATTERN_MISMATCH
   - KIND_CLIPS_CONTENT_MISMATCH
2. New comparators in dd/verify_figma.py with the same A1.3
   provenance gate (snapshot vs override)
3. Walker capture for the rendered side (extends walk_ref.js)

This test file pins the contract before implementation.
"""

from __future__ import annotations

from dd.boundary import (
    KIND_CLIPS_CONTENT_MISMATCH,
    KIND_DASH_PATTERN_MISMATCH,
    KIND_STROKE_ALIGN_MISMATCH,
    KIND_STROKE_WEIGHT_MISMATCH,
)
from dd.verify_figma import FigmaRenderVerifier


def _ir(eid: str, *, visual: dict, type_: str = "rectangle",
        overrides: list[str] | None = None) -> dict:
    el: dict = {"type": type_, "visual": visual}
    if overrides is not None:
        el["_overrides"] = overrides
    return {"elements": {eid: el}}


def _rendered(eid: str, *, type_: str = "RECTANGLE", **fields) -> dict:
    entry = {"type": type_, "name": fields.pop("name", "test"), **fields}
    return {"eid_map": {eid: entry}, "errors": []}


# ---------------------------------------------------------------------
# strokeWeight
# ---------------------------------------------------------------------

class TestStrokeWeightComparator:
    def test_match_no_error(self):
        ir = _ir("e1", visual={"strokeWeight": 2})
        rendered = _rendered("e1", strokeWeight=2)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_STROKE_WEIGHT_MISMATCH]
        assert not errs

    def test_drift_emits_kind(self):
        ir = _ir("e1", visual={"strokeWeight": 2})
        rendered = _rendered("e1", strokeWeight=4)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_STROKE_WEIGHT_MISMATCH]
        assert len(errs) == 1
        ctx = errs[0].context or {}
        assert ctx.get("ir_stroke_weight") == 2
        assert ctx.get("rendered_stroke_weight") == 4

    def test_within_tolerance_no_error(self):
        """Sub-pixel stroke weight differences are not real drift."""
        ir = _ir("e1", visual={"strokeWeight": 2})
        rendered = _rendered("e1", strokeWeight=1.9995)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_STROKE_WEIGHT_MISMATCH]
        assert not errs

    def test_instance_snapshot_skipped(self):
        """A1.3 provenance gate applies."""
        ir = _ir("e1", visual={"strokeWeight": 2}, type_="instance",
                 overrides=[])
        rendered = _rendered("e1", type_="INSTANCE", strokeWeight=4)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_STROKE_WEIGHT_MISMATCH]
        assert not errs

    def test_instance_override_enforced(self):
        ir = _ir("e1", visual={"strokeWeight": 2}, type_="instance",
                 overrides=["strokeWeight"])
        rendered = _rendered("e1", type_="INSTANCE", strokeWeight=4)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_STROKE_WEIGHT_MISMATCH]
        assert len(errs) == 1


# ---------------------------------------------------------------------
# strokeAlign
# ---------------------------------------------------------------------

class TestStrokeAlignComparator:
    def test_match_no_error(self):
        ir = _ir("e1", visual={"strokeAlign": "INSIDE"})
        rendered = _rendered("e1", strokeAlign="INSIDE")
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_STROKE_ALIGN_MISMATCH]
        assert not errs

    def test_drift_emits_kind(self):
        ir = _ir("e1", visual={"strokeAlign": "INSIDE"})
        rendered = _rendered("e1", strokeAlign="CENTER")
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_STROKE_ALIGN_MISMATCH]
        assert len(errs) == 1

    def test_instance_snapshot_skipped(self):
        ir = _ir("e1", visual={"strokeAlign": "INSIDE"}, type_="instance",
                 overrides=[])
        rendered = _rendered("e1", type_="INSTANCE", strokeAlign="CENTER")
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_STROKE_ALIGN_MISMATCH]
        assert not errs


# ---------------------------------------------------------------------
# dashPattern
# ---------------------------------------------------------------------

class TestDashPatternComparator:
    def test_match_no_error(self):
        ir = _ir("e1", visual={"dashPattern": [4, 2]})
        rendered = _rendered("e1", dashPattern=[4, 2])
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_DASH_PATTERN_MISMATCH]
        assert not errs

    def test_drift_emits_kind(self):
        ir = _ir("e1", visual={"dashPattern": [4, 2]})
        rendered = _rendered("e1", dashPattern=[8, 4])
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_DASH_PATTERN_MISMATCH]
        assert len(errs) == 1

    def test_empty_array_no_error(self):
        """Empty dash pattern (solid stroke) — both sides empty
        should not flag."""
        ir = _ir("e1", visual={"dashPattern": []})
        rendered = _rendered("e1", dashPattern=[])
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_DASH_PATTERN_MISMATCH]
        assert not errs

    def test_instance_snapshot_skipped(self):
        ir = _ir("e1", visual={"dashPattern": [4, 2]}, type_="instance",
                 overrides=[])
        rendered = _rendered("e1", type_="INSTANCE", dashPattern=[8, 4])
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_DASH_PATTERN_MISMATCH]
        assert not errs


# ---------------------------------------------------------------------
# clipsContent
# ---------------------------------------------------------------------

class TestClipsContentComparator:
    def test_match_no_error(self):
        ir = _ir("e1", visual={"clipsContent": True}, type_="frame")
        rendered = _rendered("e1", type_="FRAME", clipsContent=True)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_CLIPS_CONTENT_MISMATCH]
        assert not errs

    def test_drift_emits_kind(self):
        """IR says clip, rendered doesn't (or vice versa) — visible
        leak / hide of overflowing children."""
        ir = _ir("e1", visual={"clipsContent": True}, type_="frame")
        rendered = _rendered("e1", type_="FRAME", clipsContent=False)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_CLIPS_CONTENT_MISMATCH]
        assert len(errs) == 1

    def test_drift_other_direction_emits_kind(self):
        ir = _ir("e1", visual={"clipsContent": False}, type_="frame")
        rendered = _rendered("e1", type_="FRAME", clipsContent=True)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_CLIPS_CONTENT_MISMATCH]
        assert len(errs) == 1

    def test_instance_snapshot_skipped(self):
        ir = _ir("e1", visual={"clipsContent": True}, type_="instance",
                 overrides=[])
        rendered = _rendered("e1", type_="INSTANCE", clipsContent=False)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_CLIPS_CONTENT_MISMATCH]
        assert not errs

    def test_instance_override_enforced(self):
        ir = _ir("e1", visual={"clipsContent": True}, type_="instance",
                 overrides=["clipsContent"])
        rendered = _rendered("e1", type_="INSTANCE", clipsContent=False)
        report = FigmaRenderVerifier().verify(ir, rendered)
        errs = [e for e in report.errors if e.kind == KIND_CLIPS_CONTENT_MISMATCH]
        assert len(errs) == 1
