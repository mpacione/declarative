"""P2 (Phase E Pattern 1 fix) — test-only-import detector.

The detector finds public symbols in `dd/` that are imported BY
tests but never imported by any other `dd/` module — the canonical
shape of canonical-path drift (Pattern 1 from the Phase E triage).

These tests pin the detector's contract:
1. It catches the known orphans (cluster_stroke_weight,
   cluster_paragraph_spacing — C2 cases) so the detector is useful
   from day one.
2. It allowlists the ADR-007 stack (slated for P7 removal) without
   spamming the report.
3. It runs as a script and produces both human and JSON output.
4. The exit code is non-zero when new orphans appear so it can be
   wired into CI as a gate.

Once C2 ships (cluster_stroke_weight + cluster_paragraph_spacing
become wired in dd/cluster.py), the corresponding entries in
`test_known_C2_orphans_flagged_today` should be REMOVED — they're
markers of a present-day bug. If the test starts failing because
those symbols are no longer flagged, that's evidence C2 actually
landed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DETECTOR = REPO / "tools" / "orphan_detector.py"


def _run_detector_json() -> dict:
    """Run the detector with --json; return parsed payload. Detector
    exits 1 when orphans are found, which subprocess.run treats as
    error — but we want the JSON output regardless."""
    result = subprocess.run(
        [".venv/bin/python", str(DETECTOR), "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(result.stdout)


class TestDetectorRuns:
    def test_detector_executes_without_error(self):
        result = subprocess.run(
            [".venv/bin/python", str(DETECTOR)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Exit 0 if no orphans; exit 1 if any. Either is fine for "runs."
        assert result.returncode in (0, 1), (
            f"detector should exit 0 or 1; got {result.returncode}; "
            f"stderr: {result.stderr}"
        )
        # Stdout should mention the scanning summary regardless.
        assert "Orphan detector" in result.stdout
        assert "Scanned:" in result.stdout

    def test_detector_emits_valid_json(self):
        payload = _run_detector_json()
        assert "orphans" in payload
        assert "allowlisted" in payload
        assert "summary" in payload
        assert isinstance(payload["orphans"], dict)
        assert isinstance(payload["allowlisted"], dict)


class TestKnownC2OrphansFlaggedToday:
    """C2 (Phase E): `cluster_stroke_weight` exists at
    dd/cluster_misc.py:948 (commit 45f6b2d) but isn't wired to
    dd/cluster.py's orchestrator. Same for `cluster_paragraph_spacing`.

    These tests pin the present-day state. When C2 ships in P3b,
    UPDATE this file: those entries should be REMOVED, and a new
    test should assert they NO LONGER appear in the orphan list.
    The flip from "flagged" to "not flagged" is the regression
    signal for "did C2 actually land?"
    """

    def test_cluster_stroke_weight_flagged_pre_c2(self):
        payload = _run_detector_json()
        orphans = set(payload["orphans"])
        # Until C2 lands, this should be in the orphan list. After
        # C2 lands and dd/cluster.py imports it, the symbol moves
        # to "referenced by another dd/ module" and drops out of
        # the orphan list — this test will then start failing,
        # which is the signal to rewrite it as a "should NOT be
        # flagged" assertion.
        assert "dd.cluster_misc.cluster_stroke_weight" in orphans, (
            "C2 should still be a present-day orphan. If this test "
            "fails, C2 has landed — update this test to assert the "
            "symbol is NO LONGER an orphan."
        )

    def test_cluster_paragraph_spacing_flagged_pre_c2(self):
        payload = _run_detector_json()
        orphans = set(payload["orphans"])
        assert "dd.cluster_misc.cluster_paragraph_spacing" in orphans, (
            "C2 sibling should still be a present-day orphan. "
            "If this test fails, C2 has landed — flip the assertion."
        )


class TestADR007StackAllowlisted:
    """The ADR-007 RenderProtocol+Repair stack is ~526 LOC of
    test-only architecture (Sonnet's Pattern 1 finding,
    Codex-verified). Slated for removal in P7. Until then the
    allowlist suppresses it from the orphan report so the noise
    doesn't drown out new orphan detections.

    When P7 ships and the stack is deleted, these allowlist entries
    become unreachable (the symbols won't exist anymore) and these
    tests will fail with "symbol not found in either orphans or
    allowlisted." That's the right signal — the allowlist entries
    should also be deleted in P7.
    """

    def test_adr007_symbols_in_allowlist_not_orphans(self):
        payload = _run_detector_json()
        orphans = set(payload["orphans"])
        allowlisted = set(payload["allowlisted"])
        adr007_symbols = [
            "dd.render_protocol.FigmaRenderer",
            "dd.render_protocol.Renderer",
            "dd.render_protocol.WalkResult",
            "dd.repair_figma.FigmaRepairVerifier",
            "dd.repair_agent.run_repair_loop",
        ]
        for sym in adr007_symbols:
            assert sym in allowlisted, (
                f"{sym} should be allowlisted (P7-pending). "
                f"If this fails, either the symbol was deleted (P7 "
                f"shipped) or the allowlist drifted."
            )
            assert sym not in orphans, (
                f"{sym} is allowlisted but ALSO showed up in orphans — "
                "allowlist filter is broken."
            )


class TestDetectorScopesCorrectly:
    """The detector should not flag symbols that ARE used by some
    `dd/` module, even if tests also use them."""

    def test_actively_used_renderer_symbol_not_flagged(self):
        """`generate_figma_script` is used by `dd/cli.py` and
        `dd/compose.py`; tests also import it. Should NOT appear
        in the orphan list."""
        payload = _run_detector_json()
        orphans = set(payload["orphans"])
        assert "dd.renderers.figma.generate_figma_script" not in orphans, (
            "actively-used renderer entry point should not be an orphan"
        )
