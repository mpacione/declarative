"""Phase E #5 fix — walker surfaces bridge-reported failures verbatim.

Pre-fix render_test/walk_ref.js:326-330 read `msg.result.result` and
rejected with `"no result in {...}"` whenever the bridge reported
`{success: false, error: "..."}` — masking the real cause behind
an opaque envelope dump.

Phase E sweep recorded screen 78 fail at 905s with the message:
  FAIL=walk exit=1: FAIL: no result in {"type":"PROXY_EXECUTE_RESULT",
  "id":"walk_1777186498837","result":{"success":false,"erro

The actual bridge error was truncated and never reached Python's
log / sweep summary.

Codex 2026-04-26 (gpt-5.5 high reasoning) review:
"Ship only the walker error-surfacing fix in this cycle. It is
low-risk, directly improves the next failure, and does not change
timeout semantics or mask regressions."

The fix at render_test/walk_ref.js:316-348 extracts `envelope.error`
from `msg.result.error` so Python sees the real cause (plugin
sandbox eval timeout, WebSocket closed, proxy_execute timeout from
Figma's side, etc.).

These tests pin the contract by inspecting the walker source for
the parse pattern. Direct JS execution requires a live bridge
which isn't available in unit tests.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WALK_REF_JS = REPO / "render_test" / "walk_ref.js"


class TestWalkerErrorSurfacing:
    """The walker's PROXY_EXECUTE_RESULT handler must extract
    bridge-reported errors verbatim."""

    def test_walker_extracts_envelope_error(self):
        """Pin the parse pattern: when msg.result.success is false
        OR msg.result.error is set, the walker should reject with
        the real error message, not 'no result in ...'."""
        src = WALK_REF_JS.read_text()
        assert "envelope.success === false" in src, (
            "Phase E #5: walk_ref.js must check envelope.success "
            "to surface bridge-reported failures verbatim."
        )
        assert "envelope.error" in src, (
            "Phase E #5: walk_ref.js must extract envelope.error "
            "(the real bridge-side error message) before falling "
            "back to 'bridge execution failed'."
        )

    def test_walker_no_longer_swallows_success_false(self):
        """The pre-fix pattern read msg.result.result without
        checking success. Verify the new pattern reads success
        FIRST."""
        src = WALK_REF_JS.read_text()
        # The new code path checks success/error before reading
        # envelope.result. The position matters: if envelope.success
        # check is AFTER the result access, the same swallowing bug
        # could resurface.
        success_pos = src.find("envelope.success === false")
        result_access_pos = src.find("envelope.result", success_pos)
        assert success_pos > 0 and result_access_pos > success_pos, (
            "Phase E #5: the success/error check must run BEFORE "
            "reading envelope.result. Pre-fix the access happened "
            "first and bridge errors got swallowed."
        )

    def test_walker_preserves_no_result_fallback(self):
        """Defensive: when the bridge returns success=true but
        with no result payload, the original 'no result in' message
        is still emitted (covers an unexpected envelope shape)."""
        src = WALK_REF_JS.read_text()
        assert "'no result in '" in src, (
            "Phase E #5: keep the 'no result in' fallback for the "
            "case where envelope.success is true but no payload "
            "exists. Drop only the swallowed-error path."
        )


class TestWalkerVisualPropCapture:
    """P1b (forensic-audit-2 findings 8-12): the walker must capture
    every visual property the verifier compares. Pre-fix only rotation
    was captured among the 5 audit-flagged props; opacity/blendMode/
    isMask/cornerRadius drift was invisible because the walker simply
    didn't measure them on the rendered side.

    These tests pin the source pattern; direct JS execution requires
    a live bridge.
    """

    def test_walker_captures_opacity(self):
        src = WALK_REF_JS.read_text()
        assert "entry.opacity = n.opacity" in src, (
            "P1b: walker must capture node.opacity for verifier comparison"
        )

    def test_walker_captures_blend_mode(self):
        src = WALK_REF_JS.read_text()
        assert "entry.blendMode = n.blendMode" in src, (
            "P1b: walker must capture node.blendMode"
        )

    def test_walker_captures_is_mask(self):
        src = WALK_REF_JS.read_text()
        assert "entry.isMask = n.isMask" in src, (
            "P1b: walker must capture node.isMask"
        )

    def test_walker_captures_corner_radius_uniform(self):
        """Uniform cornerRadius is a number; capture as entry.cornerRadius."""
        src = WALK_REF_JS.read_text()
        assert "entry.cornerRadius = n.cornerRadius" in src, (
            "P1b: walker must capture uniform numeric cornerRadius"
        )

    def test_walker_captures_corner_radius_mixed(self):
        """When cornerRadius is figma.Mixed (per-corner radii),
        capture each side as topLeftRadius / topRightRadius / etc.
        and flag cornerRadiusMixed=true so the verifier can compare
        per-corner instead of uniform-vs-uniform."""
        src = WALK_REF_JS.read_text()
        assert "cornerRadiusMixed" in src, (
            "P1b: walker must flag the mixed-radius case"
        )
        for corner in ("topLeftRadius", "topRightRadius",
                       "bottomRightRadius", "bottomLeftRadius"):
            assert corner in src, (
                f"P1b: walker must capture per-corner radius {corner}"
            )
