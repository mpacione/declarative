"""P1c — verifier comparators for the 5 newly-tracked visual props.

Phase: forensic-audit-2 fix sprint, P1c. The audit found that the
verifier was blind to drift on opacity, blendMode, rotation, isMask,
and cornerRadius — the renderer emitted them via the registry-driven
path, but no `KIND_*_MISMATCH` comparator existed in
``dd/verify_figma.py``. The walker (P1b) now captures these from the
rendered side; the verifier-side IR (P1a) carries them. This is the
final piece — the comparators that flip silent drift into explicit
verifier errors with the matching `KIND_*` from `dd/boundary.py`.

Pattern: each prop class gets two tests — "match → no error" (regression
guard) and "drift → KIND_X_MISMATCH" (the new signal). For numeric props
(opacity, rotation) we also test the tolerance boundary so float jitter
doesn't trip false positives.
"""

from __future__ import annotations

from dd.boundary import (
    KIND_BLENDMODE_MISMATCH,
    KIND_CORNERRADIUS_MISMATCH,
    KIND_MASK_MISMATCH,
    KIND_OPACITY_MISMATCH,
    KIND_ROTATION_MISMATCH,
)
from dd.verify_figma import FigmaRenderVerifier


def _ir(eid: str, visual: dict, *, type_: str = "frame") -> dict:
    return {
        "elements": {
            eid: {
                "type": type_,
                "visual": visual,
            }
        }
    }


def _rendered(eid: str, **fields) -> dict:
    return {
        "eid_map": {
            eid: {
                "type": fields.pop("type", "FRAME"),
                "name": fields.pop("name", "test"),
                **fields,
            }
        },
        "errors": [],
    }


# -----------------------------------------------------------------------
# Opacity
# -----------------------------------------------------------------------

class TestOpacityMismatch:
    def test_match_no_error(self):
        ir = _ir("e1", {"opacity": 0.5})
        rendered = _rendered("e1", opacity=0.5)
        report = FigmaRenderVerifier().verify(ir, rendered)
        opacity_errs = [e for e in report.errors if e.kind == KIND_OPACITY_MISMATCH]
        assert not opacity_errs, f"matching opacity must not flag: {opacity_errs}"

    def test_drift_emits_kind(self):
        ir = _ir("e1", {"opacity": 0.5})
        rendered = _rendered("e1", opacity=1.0)
        report = FigmaRenderVerifier().verify(ir, rendered)
        opacity_errs = [e for e in report.errors if e.kind == KIND_OPACITY_MISMATCH]
        assert len(opacity_errs) == 1, opacity_errs
        assert opacity_errs[0].id == "e1"
        ctx = opacity_errs[0].context or {}
        assert ctx.get("ir_opacity") == 0.5
        assert ctx.get("rendered_opacity") == 1.0

    def test_within_tolerance_no_error(self):
        """Float jitter under 1e-3 is not a real drift."""
        ir = _ir("e1", {"opacity": 0.5})
        rendered = _rendered("e1", opacity=0.5005)
        report = FigmaRenderVerifier().verify(ir, rendered)
        opacity_errs = [e for e in report.errors if e.kind == KIND_OPACITY_MISMATCH]
        assert not opacity_errs

    def test_ir_missing_no_error(self):
        """When IR omits opacity (default 1.0 skip-emitted), the
        comparator should not flag drift on the rendered side."""
        ir = _ir("e1", {})
        rendered = _rendered("e1", opacity=1.0)
        report = FigmaRenderVerifier().verify(ir, rendered)
        opacity_errs = [e for e in report.errors if e.kind == KIND_OPACITY_MISMATCH]
        assert not opacity_errs


# -----------------------------------------------------------------------
# Blend Mode
# -----------------------------------------------------------------------

class TestBlendModeMismatch:
    def test_match_no_error(self):
        ir = _ir("e1", {"blendMode": "MULTIPLY"})
        rendered = _rendered("e1", blendMode="MULTIPLY")
        report = FigmaRenderVerifier().verify(ir, rendered)
        bm_errs = [e for e in report.errors if e.kind == KIND_BLENDMODE_MISMATCH]
        assert not bm_errs

    def test_drift_emits_kind(self):
        ir = _ir("e1", {"blendMode": "MULTIPLY"})
        rendered = _rendered("e1", blendMode="NORMAL")
        report = FigmaRenderVerifier().verify(ir, rendered)
        bm_errs = [e for e in report.errors if e.kind == KIND_BLENDMODE_MISMATCH]
        assert len(bm_errs) == 1
        ctx = bm_errs[0].context or {}
        assert ctx.get("ir_blend_mode") == "MULTIPLY"
        assert ctx.get("rendered_blend_mode") == "NORMAL"

    def test_ir_missing_no_error(self):
        ir = _ir("e1", {})
        rendered = _rendered("e1", blendMode="NORMAL")
        report = FigmaRenderVerifier().verify(ir, rendered)
        bm_errs = [e for e in report.errors if e.kind == KIND_BLENDMODE_MISMATCH]
        assert not bm_errs


# -----------------------------------------------------------------------
# Rotation
# -----------------------------------------------------------------------

class TestRotationMismatch:
    def test_match_no_error(self):
        # Same rotation in radians (90 degrees)
        ir = _ir("e1", {"rotation": 1.5707963267948966})
        rendered = _rendered("e1", rotation=1.5707963267948966)
        report = FigmaRenderVerifier().verify(ir, rendered)
        rot_errs = [e for e in report.errors if e.kind == KIND_ROTATION_MISMATCH]
        assert not rot_errs

    def test_drift_emits_kind(self):
        # IR says 90deg, rendered says 0
        ir = _ir("e1", {"rotation": 1.5707963267948966})
        rendered = _rendered("e1", rotation=0.0)
        report = FigmaRenderVerifier().verify(ir, rendered)
        rot_errs = [e for e in report.errors if e.kind == KIND_ROTATION_MISMATCH]
        assert len(rot_errs) == 1
        ctx = rot_errs[0].context or {}
        assert abs(ctx.get("ir_rotation") - 1.5707963267948966) < 1e-9
        assert ctx.get("rendered_rotation") == 0.0

    def test_within_tolerance_no_error(self):
        """1e-3 rad tolerance — about 0.06° — covers float jitter
        from the deg→rad conversion in the walker."""
        ir = _ir("e1", {"rotation": 1.5707963267948966})
        rendered = _rendered("e1", rotation=1.5707963267948966 + 5e-4)
        report = FigmaRenderVerifier().verify(ir, rendered)
        rot_errs = [e for e in report.errors if e.kind == KIND_ROTATION_MISMATCH]
        assert not rot_errs


# -----------------------------------------------------------------------
# isMask
# -----------------------------------------------------------------------

class TestMaskMismatch:
    def test_match_no_error(self):
        ir = _ir("e1", {"isMask": True})
        rendered = _rendered("e1", isMask=True)
        report = FigmaRenderVerifier().verify(ir, rendered)
        mask_errs = [e for e in report.errors if e.kind == KIND_MASK_MISMATCH]
        assert not mask_errs

    def test_drift_emits_kind_when_ir_true_rendered_false(self):
        """A mask that wasn't applied leaks the underlying content."""
        ir = _ir("e1", {"isMask": True})
        rendered = _rendered("e1", isMask=False)
        report = FigmaRenderVerifier().verify(ir, rendered)
        mask_errs = [e for e in report.errors if e.kind == KIND_MASK_MISMATCH]
        assert len(mask_errs) == 1

    def test_drift_emits_kind_when_ir_false_rendered_true(self):
        """Spuriously masked content is also flagged."""
        ir = _ir("e1", {"isMask": False})
        rendered = _rendered("e1", isMask=True)
        report = FigmaRenderVerifier().verify(ir, rendered)
        mask_errs = [e for e in report.errors if e.kind == KIND_MASK_MISMATCH]
        assert len(mask_errs) == 1

    def test_ir_missing_no_error(self):
        ir = _ir("e1", {})
        rendered = _rendered("e1", isMask=False)
        report = FigmaRenderVerifier().verify(ir, rendered)
        mask_errs = [e for e in report.errors if e.kind == KIND_MASK_MISMATCH]
        assert not mask_errs


# -----------------------------------------------------------------------
# Corner Radius
# -----------------------------------------------------------------------

class TestCornerRadiusMismatch:
    def test_uniform_match_no_error(self):
        ir = _ir("e1", {"cornerRadius": 8})
        rendered = _rendered("e1", cornerRadius=8)
        report = FigmaRenderVerifier().verify(ir, rendered)
        cr_errs = [e for e in report.errors if e.kind == KIND_CORNERRADIUS_MISMATCH]
        assert not cr_errs

    def test_uniform_drift_emits_kind(self):
        ir = _ir("e1", {"cornerRadius": 8})
        rendered = _rendered("e1", cornerRadius=0)
        report = FigmaRenderVerifier().verify(ir, rendered)
        cr_errs = [e for e in report.errors if e.kind == KIND_CORNERRADIUS_MISMATCH]
        assert len(cr_errs) == 1
        ctx = cr_errs[0].context or {}
        assert ctx.get("ir_corner_radius") == 8
        assert ctx.get("rendered_corner_radius") == 0

    def test_uniform_within_tolerance_no_error(self):
        """Sub-pixel differences (e.g. 8 vs 7.999) are not real drift."""
        ir = _ir("e1", {"cornerRadius": 8})
        rendered = _rendered("e1", cornerRadius=7.9995)
        report = FigmaRenderVerifier().verify(ir, rendered)
        cr_errs = [e for e in report.errors if e.kind == KIND_CORNERRADIUS_MISMATCH]
        assert not cr_errs

    def test_ir_missing_no_error(self):
        ir = _ir("e1", {})
        rendered = _rendered("e1", cornerRadius=0)
        report = FigmaRenderVerifier().verify(ir, rendered)
        cr_errs = [e for e in report.errors if e.kind == KIND_CORNERRADIUS_MISMATCH]
        assert not cr_errs

    def test_mixed_radius_compares_per_corner(self):
        """When the renderer reports cornerRadiusMixed=true, the IR's
        cornerRadius dict (per-corner) is compared corner-by-corner.

        Until a per-corner IR shape lands, mixed-vs-uniform is a soft
        skip — flagged only when the IR has a clear per-corner shape
        that differs."""
        # IR uniform 8, rendered mixed all-8 → no error.
        ir = _ir("e1", {"cornerRadius": 8})
        rendered = _rendered(
            "e1",
            cornerRadiusMixed=True,
            topLeftRadius=8,
            topRightRadius=8,
            bottomRightRadius=8,
            bottomLeftRadius=8,
        )
        report = FigmaRenderVerifier().verify(ir, rendered)
        cr_errs = [e for e in report.errors if e.kind == KIND_CORNERRADIUS_MISMATCH]
        assert not cr_errs

    def test_mixed_radius_drift_emits_kind(self):
        """IR uniform 8, rendered has mismatched per-corner radii."""
        ir = _ir("e1", {"cornerRadius": 8})
        rendered = _rendered(
            "e1",
            cornerRadiusMixed=True,
            topLeftRadius=8,
            topRightRadius=0,  # drift here
            bottomRightRadius=8,
            bottomLeftRadius=8,
        )
        report = FigmaRenderVerifier().verify(ir, rendered)
        cr_errs = [e for e in report.errors if e.kind == KIND_CORNERRADIUS_MISMATCH]
        assert len(cr_errs) == 1
