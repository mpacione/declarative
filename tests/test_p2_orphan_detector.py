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


class TestC2OrphansResolvedByP3b:
    """C2 (Phase E) was resolved by P3b. `cluster_stroke_weight` and
    `cluster_paragraph_spacing` are now wired into dd/cluster.py's
    orchestrator (commit after this one). The tests pin the post-P3b
    state — these symbols MUST NOT appear as orphans anymore. If
    they regress (e.g. someone removes the import), this test will
    fail and surface the regression."""

    def test_cluster_stroke_weight_no_longer_orphan(self):
        payload = _run_detector_json()
        orphans = set(payload["orphans"])
        assert "dd.cluster_misc.cluster_stroke_weight" not in orphans, (
            "P3b wired cluster_stroke_weight into dd/cluster.py. "
            "If this fails, the orchestrator import has been removed "
            "or the function has been deleted/renamed."
        )

    def test_cluster_paragraph_spacing_no_longer_orphan(self):
        payload = _run_detector_json()
        orphans = set(payload["orphans"])
        assert "dd.cluster_misc.cluster_paragraph_spacing" not in orphans, (
            "P3b wired cluster_paragraph_spacing into dd/cluster.py. "
            "If this fails, the orchestrator import has been removed "
            "or the function has been deleted/renamed."
        )

    def test_ensure_stroke_weight_collection_referenced(self):
        """The new helper introduced in P3b (cluster_misc.py:
        ensure_stroke_weight_collection) must also be wired."""
        payload = _run_detector_json()
        orphans = set(payload["orphans"])
        assert "dd.cluster_misc.ensure_stroke_weight_collection" not in orphans


class TestADR007StackRemovedByP7:
    """P7 (Phase E Pattern 1 fix) deleted the ADR-007 RenderProtocol+
    Repair stack: dd/render_protocol.py, dd/repair_figma.py,
    dd/repair_agent.py, scripts/repair_demo.py + the 3 test files.

    Pre-P7 these symbols lived in the orphan-detector ALLOWLIST as
    "P7-pending: ADR-007 retire". P7 deletes both the source files
    AND the allowlist entries. These tests assert the post-P7 state:
    the symbols MUST NOT appear in orphans (they don't exist) and
    MUST NOT appear in allowlisted (no need anymore).

    The unified verification channel that ADR-007 introduced is
    STILL LIVE in dd/boundary.py + dd/verify_figma.py + the renderer
    guards — only the unused multi-backend wrapper + the test-only
    repair loop were removed. Codex Phase E review (2026-04-25)
    explicitly cautioned: "Do not mark all ADR-007 docs superseded:
    the unified verification channel is still live in dd/boundary.py,
    dd/verify_figma.py, and renderer guards. Only the
    RenderProtocol+Repair stack is superseded."
    """

    def test_adr007_symbols_no_longer_in_orphans(self):
        payload = _run_detector_json()
        orphans = set(payload["orphans"])
        adr007_symbols = [
            "dd.render_protocol.FigmaRenderer",
            "dd.render_protocol.Renderer",
            "dd.render_protocol.WalkResult",
            "dd.repair_figma.FigmaRepairVerifier",
            "dd.repair_agent.run_repair_loop",
        ]
        for sym in adr007_symbols:
            assert sym not in orphans, (
                f"P7: {sym} should not be in orphans — the module "
                f"was deleted in P7. Either the deletion was reverted "
                f"or the detector is finding it via a stale path."
            )

    def test_adr007_symbols_no_longer_in_allowlist(self):
        payload = _run_detector_json()
        allowlisted = set(payload["allowlisted"])
        adr007_symbols = [
            "dd.render_protocol.FigmaRenderer",
            "dd.render_protocol.Renderer",
            "dd.render_protocol.WalkResult",
            "dd.repair_figma.FigmaRepairVerifier",
            "dd.repair_agent.run_repair_loop",
        ]
        for sym in adr007_symbols:
            assert sym not in allowlisted, (
                f"P7: {sym} should NOT be allowlisted — the module "
                f"was deleted in P7. Allowlist entry is stale."
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


class TestScriptCallersExcluded:
    """P10.1 fix (2026-04-26): scripts/ are production callers,
    not test-equivalent. Symbols used ONLY by scripts/ (no dd/
    caller, no tests/ caller) MUST NOT be flagged as orphans.

    Codex review (gpt-5.5 high reasoning): "Scripts are runtime
    callers. Conflating them with tests creates exactly the
    false-positive class you're fixing."
    """

    def test_script_only_symbol_not_flagged_as_orphan(self):
        """`dd.apply_render.walk_rendered_via_bridge` is used by
        4 scripts (scripts/archive/tier_b_demo.py, swap_demo.py,
        tier_d_eval.py, etc.) AND by tests. Pre-fix it was flagged
        because the detector lumped scripts with tests. Post-fix
        scripts count as production callers; symbol is NOT an orphan."""
        payload = _run_detector_json()
        orphans = set(payload["orphans"])
        # walk_rendered_via_bridge is used by scripts/archive/tier_b_demo.py
        # and other scripts. Should NOT be in orphans post-fix.
        assert (
            "dd.apply_render.walk_rendered_via_bridge"
            not in orphans
        ), (
            "P10.1: walk_rendered_via_bridge is used by 4 scripts; "
            "scripts are production callers, not test-equivalent. "
            "Symbol should not be flagged as orphan."
        )

    def test_script_refs_count_in_summary(self):
        """The detector should expose script_files_scanned and
        script_refs_count separately from test counts so users can
        verify the correct classification."""
        payload = _run_detector_json()
        summary = payload["summary"]
        assert "script_files_scanned" in summary, (
            "P10.1: summary should expose script_files_scanned "
            "separately from test_files_scanned."
        )
        assert "script_refs_count" in summary, (
            "P10.1: summary should expose script_refs_count "
            "separately from test_refs_count."
        )
        assert summary["script_files_scanned"] > 0, (
            "P10.1: scripts/ directory should have scanned files."
        )
