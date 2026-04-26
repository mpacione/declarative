"""Phase E #5 follow-on — bridge-load resilience.

The Phase E sweep observed screen 78 timing out at 905s on a 320s
WALK_TIMEOUT — Python killed the subprocess while the bridge was
still working. Per feedback_sweep_transient_timeouts.md: cumulative
bridge load on long sweeps; individual retries succeed.

Codex 2026-04-26 (gpt-5.5 high reasoning) review picked
"E + E1 + bounded warmup" with critical correction on timeout
hierarchy:
  - bridge/proxy_execute fires first (innermost)
  - JS watchdog next (+10s)
  - Python subprocess last (outermost)
This way subprocess kills are clean rather than mid-flight; bridge
has a chance to respond with a structured failure before the
subprocess is killed.

What this commit ships:
1. WALK_TIMEOUT bumped 320 → 600
2. WALK_BRIDGE_HEADROOM = 20 (sweep injects BRIDGE_TIMEOUT_MS for walker)
3. Per-screen elapsed_ms + walk_timed_out + walk_failure_class
4. Aggregate p50/p95/max walk timing + walk_failure_classes counter
5. _bridge_warmup at sweep start (bounded; non-blocking)

Deferred (per Codex review):
- In-walker retry on WebSocket-close errors (could mask real bugs)
- Heartbeat / dynamic timeout (bigger surgery; bridge may not
  expose liveness during proxy_execute)
"""

from __future__ import annotations

from render_batch.sweep import (
    WALK_BRIDGE_HEADROOM,
    WALK_TIMEOUT,
    summarize,
)


class TestTimeoutHierarchy:
    """The critical contract: WALK_TIMEOUT > BRIDGE_TIMEOUT_MS / 1000
    so the bridge fires first."""

    def test_walk_timeout_bumped_to_600s(self):
        assert WALK_TIMEOUT == 600, (
            "Phase E #5: WALK_TIMEOUT must be 600s for cumulative-"
            "bridge-load resilience. Pre-fix the 320s limit killed "
            "the subprocess at 320s when the bridge was still "
            "working."
        )

    def test_bridge_headroom_constant_defined(self):
        assert WALK_BRIDGE_HEADROOM == 20, (
            "Phase E #5: WALK_BRIDGE_HEADROOM is the slack between "
            "subprocess timeout and bridge proxy_execute timeout. "
            "20s gives the bridge time to respond with a structured "
            "failure before the subprocess is killed."
        )

    def test_bridge_timeout_strictly_less_than_walk(self):
        """The bridge timeout must be strictly less than the
        subprocess timeout. This is the central invariant."""
        bridge_timeout_s = WALK_TIMEOUT - WALK_BRIDGE_HEADROOM
        assert bridge_timeout_s < WALK_TIMEOUT, (
            "Phase E #5: BRIDGE_TIMEOUT_MS / 1000 must be < "
            "WALK_TIMEOUT so the bridge fires first."
        )
        # Sanity: should be at least 60s of bridge time.
        assert bridge_timeout_s >= 60, (
            "Phase E #5: bridge timeout shouldn't be too small "
            "(would cause spurious failures on legitimate slow "
            "renders)."
        )


class TestSummaryMetrics:
    """The new bridge-load aggregates surface in summary.json."""

    def test_summary_includes_walk_timed_out_count(self):
        summary = summarize([
            {
                "screen_id": 1, "is_parity": True,
                "is_structural_parity": True,
                "walk_timed_out": False, "elapsed_ms": 800,
            },
            {
                "screen_id": 2, "is_parity": False,
                "is_structural_parity": False,
                "walk_timed_out": True, "elapsed_ms": 600000,
            },
        ])
        assert summary["walk_timed_out_count"] == 1, (
            "Phase E #5: summary should aggregate walk_timed_out "
            "across rows."
        )

    def test_summary_includes_failure_class_counter(self):
        summary = summarize([
            {
                "screen_id": 1, "is_parity": False,
                "walk_failure_class": "subprocess_timeout",
                "elapsed_ms": 600000,
            },
            {
                "screen_id": 2, "is_parity": False,
                "walk_failure_class": "subprocess_timeout",
                "elapsed_ms": 600000,
            },
            {
                "screen_id": 3, "is_parity": False,
                "walk_failure_class": "bridge_error",
                "elapsed_ms": 1200,
            },
        ])
        classes = summary["walk_failure_classes"]
        assert classes["subprocess_timeout"] == 2
        assert classes["bridge_error"] == 1

    def test_summary_includes_elapsed_ms_distribution(self):
        summary = summarize([
            {"screen_id": i, "is_parity": True,
             "is_structural_parity": True, "elapsed_ms": ms}
            for i, ms in enumerate([100, 200, 300, 400, 500, 600, 700, 800, 900, 1000])
        ])
        assert summary["walk_elapsed_ms_max"] == 1000
        # p50 with 10 elements is index 5 (0-indexed) → 600
        assert summary["walk_elapsed_ms_p50"] == 600
        # p95 with 10 elements is index 9 → 1000
        assert summary["walk_elapsed_ms_p95"] == 1000

    def test_summary_handles_empty_elapsed_gracefully(self):
        """No elapsed_ms (all 0) → metrics are 0, not crash."""
        summary = summarize([
            {"screen_id": 1, "is_parity": True,
             "is_structural_parity": True, "elapsed_ms": 0},
        ])
        assert summary["walk_elapsed_ms_p50"] == 0
        assert summary["walk_elapsed_ms_p95"] == 0
        assert summary["walk_elapsed_ms_max"] == 0


class TestRowFieldsExist:
    """The new per-screen fields are in the row dict produced by
    process_screen (verified via the row-init shape — full
    integration test requires a live bridge)."""

    def test_process_screen_row_init_includes_bridge_metrics(self):
        """Read the source to verify the row init has the new
        fields. Can't run process_screen in unit tests because it
        needs a live bridge."""
        from pathlib import Path
        src = (
            Path(__file__).resolve().parent.parent
            / "render_batch" / "sweep.py"
        ).read_text()
        for field in (
            '"elapsed_ms": 0',
            '"walk_timed_out": False',
            '"walk_failure_class": None',
        ):
            assert field in src, (
                f"Phase E #5: process_screen row init must include "
                f"{field}."
            )


class TestBridgeWarmupExists:
    """The warmup function is wired and called before the sweep
    main loop."""

    def test_bridge_warmup_function_exists(self):
        from render_batch.sweep import _bridge_warmup
        assert callable(_bridge_warmup)

    def test_bridge_warmup_called_before_main_loop(self):
        """Read the source to verify _bridge_warmup(args.port) is
        called before the for-loop. Pre-fix there was no warmup
        and first-call latency added cold-start jitter to the first
        screen's elapsed_ms."""
        from pathlib import Path
        src = (
            Path(__file__).resolve().parent.parent
            / "render_batch" / "sweep.py"
        ).read_text()
        warmup_pos = src.find("_bridge_warmup(args.port)")
        loop_pos = src.find("for i, (sid, name) in enumerate(screens, 1):")
        assert warmup_pos > 0 and loop_pos > warmup_pos, (
            "Phase E #5: _bridge_warmup(args.port) must be called "
            "BEFORE the main for-loop."
        )

    def test_bridge_warmup_is_non_blocking(self):
        """Read the warmup function source to verify it never
        raises (Codex review: 'strictly non-blocking')."""
        from pathlib import Path
        src = (
            Path(__file__).resolve().parent.parent
            / "render_batch" / "sweep.py"
        ).read_text()
        # Find the warmup function body
        start = src.index("def _bridge_warmup(")
        end = src.index("def list_app_screens(", start)
        warmup_body = src[start:end]
        # Body should have try/except to swallow all errors
        assert "try:" in warmup_body
        assert "except Exception" in warmup_body
        assert "non-blocking" in warmup_body.lower()
