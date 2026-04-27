"""P7 (Phase E Pattern 1 fix) — ADR-007 RenderProtocol+Repair stack
removal regression.

Phase E §7 + Sonnet's Pattern 1 analysis confirmed: ~526 LOC of
test-only code that never went into production. Codex Phase E review
(2026-04-25, gpt-5.5) verified the deletion is safe via:
- code-graph-mcp refs FigmaRenderer → 1 ref (test only)
- code-graph-mcp refs run_repair_loop → 3 refs (1 demo + 2 tests)
- code-graph-mcp refs FigmaRepairVerifier → 1 ref (test only)
- direct import grep + dynamic-string-import scan: no live paths

P7 deletes:
- dd/render_protocol.py (FigmaRenderer, Renderer, RenderArtifact, WalkResult)
- dd/repair_figma.py (FigmaRepairVerifier, build_figma_repair_verifier)
- dd/repair_agent.py (run_repair_loop, RepairReport, RepairOutcome,
  build_llm_proposer, Verifier, LLMProposer)
- scripts/repair_demo.py (M7.5 demo)
- tests/test_render_protocol.py
- tests/test_repair_agent.py
- tests/test_repair_figma.py
- score_render_result adapter from dd/fidelity_score.py + its 2
  callsites in tests/test_fidelity_score.py
- 13 ADR-007 entries from tools/orphan_detector.py:ALLOWLIST

What stays (Codex review explicit caveat):
- dd/boundary.py:RenderReport (the unified verification channel)
- dd/verify_figma.py:FigmaRenderVerifier (the Figma verifier)
- dd/cli.py:_run_verify (the production CLI entry point)
- All renderer F-series guards (font_load_failed, text_set_failed,
  append_child_failed, ...) + P3d's phase2_orphan walker addition

These tests are the regression tripwire — if anyone restores the
deleted modules without restoring the ALLOWLIST entries, the
detector test will fail; if anyone restores ALLOWLIST entries
without restoring the modules, the assertions here will fail.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


class TestADR007FilesRemoved:
    """The literal source files no longer exist on disk."""

    def test_render_protocol_module_deleted(self):
        assert not (REPO / "dd" / "render_protocol.py").exists(), (
            "P7: dd/render_protocol.py must remain deleted. If you "
            "need a render-side multi-backend abstraction, prefer a "
            "TypedDict/Protocol in dd/boundary.py — don't restore "
            "the FigmaRenderer/Renderer ABC stack."
        )

    def test_repair_figma_module_deleted(self):
        assert not (REPO / "dd" / "repair_figma.py").exists()

    def test_repair_agent_module_deleted(self):
        assert not (REPO / "dd" / "repair_agent.py").exists()

    def test_repair_demo_script_deleted(self):
        assert not (REPO / "scripts" / "repair_demo.py").exists()

    def test_render_protocol_test_deleted(self):
        assert not (REPO / "tests" / "test_render_protocol.py").exists()

    def test_repair_figma_test_deleted(self):
        assert not (REPO / "tests" / "test_repair_figma.py").exists()

    def test_repair_agent_test_deleted(self):
        assert not (REPO / "tests" / "test_repair_agent.py").exists()


class TestADR007ImportsFail:
    """Production imports of the deleted symbols must fail with
    ImportError, not silently fall back to a stub."""

    def test_render_protocol_module_unimportable(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("dd.render_protocol")

    def test_repair_figma_module_unimportable(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("dd.repair_figma")

    def test_repair_agent_module_unimportable(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("dd.repair_agent")


class TestUnifiedChannelStillLive:
    """Codex Phase E review explicit caveat: 'Do not mark all ADR-007
    docs superseded: the unified verification channel is still live
    in dd/boundary.py, dd/verify_figma.py, and renderer guards. Only
    the RenderProtocol+Repair stack is superseded.'

    These tests pin the bits of ADR-007 that survived P7."""

    def test_render_report_still_exists(self):
        from dd.boundary import RenderReport
        assert RenderReport is not None

    def test_render_report_has_p1_p4_channels(self):
        """The verification channel that ADR-007 introduced is now
        the multi-channel RenderReport (P1 + P4). Make sure all
        three properties survive any future refactor."""
        from dd.boundary import RenderReport
        for prop in ("is_structural_parity", "is_runtime_clean", "is_parity"):
            assert hasattr(RenderReport, prop), (
                f"P7 caveat: RenderReport.{prop} is the surviving "
                f"surface of ADR-007's unified verification channel. "
                f"Do not remove."
            )

    def test_figma_render_verifier_still_exists(self):
        from dd.verify_figma import FigmaRenderVerifier
        assert FigmaRenderVerifier is not None
        # Construction smoke test — production CLI uses this.
        verifier = FigmaRenderVerifier()
        assert verifier is not None


class TestFidelityScoreAdapterRemoved:
    """The score_render_result adapter that wrapped WalkResult was
    removed — the canonical entry point is `score_fidelity` with
    explicit `walk_eid_map` + `walk_errors` kwargs."""

    def test_score_render_result_no_longer_importable(self):
        import dd.fidelity_score as fs
        assert not hasattr(fs, "score_render_result"), (
            "P7: score_render_result was an adapter to "
            "WalkResult (deleted in P7). Use score_fidelity with "
            "explicit walk_eid_map + walk_errors kwargs instead."
        )

    def test_score_fidelity_still_works(self):
        """Smoke test that the canonical entry point is intact."""
        from dd.fidelity_score import score_fidelity
        report = score_fidelity(
            ir_elements={"s": {"type": "screen"}},
            walk_eid_map={"s": {"type": "FRAME"}},
            walk_errors=[],
        )
        assert report is not None


class TestOrphanDetectorAllowlistCleared:
    """The 13 ADR-007 entries are gone from the allowlist; the
    detector should not see them in either bucket."""

    def test_allowlist_has_no_adr007_entries(self):
        # Re-import to pick up any state, then read ALLOWLIST.
        spec = importlib.util.spec_from_file_location(
            "orphan_detector", REPO / "tools" / "orphan_detector.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        adr007_qualifiers = [
            "dd.render_protocol", "dd.repair_figma", "dd.repair_agent",
        ]
        leftover = [
            sym for sym in module.ALLOWLIST
            if any(q in sym for q in adr007_qualifiers)
        ]
        assert not leftover, (
            f"P7: ALLOWLIST should have no ADR-007 entries left. "
            f"Found: {leftover}"
        )
