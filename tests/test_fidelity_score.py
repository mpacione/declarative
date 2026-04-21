"""Tests for ``dd.fidelity_score`` — Tier C.2 scorer.

Each dimension is unit-tested on synthetic inputs drawn from
`docs/learnings-tier-b-failure-modes.md`. Happy paths + the
specific failure shapes observed in Tier B.
"""

from __future__ import annotations

import pytest

from unittest.mock import MagicMock

from dd.fidelity_score import (
    DimensionScore,
    FidelityReport,
    LEAF_TYPES,
    score_component_child_consistency,
    score_coverage,
    score_fidelity,
    score_font_readiness,
    score_leaf_type_structural,
    score_render_result,
    vlm_score_via_gemini,
)


class TestScoreCoverage:
    def test_full_coverage_passes(self) -> None:
        ir = {"screen-1": {"type": "screen", "children": ["b"]}, "b": {"type": "button"}}
        walk = {"screen-1": {"type": "FRAME"}, "b": {"type": "FRAME"}}
        d = score_coverage(ir, walk)
        assert d.value == 1.0
        assert d.passed is True

    def test_missing_elements_fail(self) -> None:
        ir = {
            "screen-1": {"type": "screen", "children": ["a", "b", "c"]},
            "a": {"type": "text"},
            "b": {"type": "text"},
            "c": {"type": "text"},
        }
        walk = {"screen-1": {"type": "FRAME"}, "a": {"type": "TEXT"}}
        d = score_coverage(ir, walk)
        assert d.value == pytest.approx(0.5)  # 2 of 4
        assert d.passed is False
        assert "missing" in d.diagnostic

    def test_mode1_instance_absorbs_descendants(self) -> None:
        """INSTANCE-rendered parent → its spec-side children are
        absorbed, not counted against coverage."""
        ir = {
            "screen-1": {"type": "screen", "children": ["btn"]},
            "btn": {"type": "button", "children": ["btn-icon", "btn-label"]},
            "btn-icon": {"type": "icon"},
            "btn-label": {"type": "text"},
        }
        walk = {
            "screen-1": {"type": "FRAME"},
            "btn": {"type": "INSTANCE"},
        }
        d = score_coverage(ir, walk)
        # Expected: 2 non-absorbed (screen-1 + btn), both rendered.
        assert d.value == 1.0
        assert d.passed is True

    def test_threshold_respected(self) -> None:
        ir = {
            "screen-1": {"type": "screen", "children": ["a", "b", "c"]},
            "a": {"type": "text"}, "b": {"type": "text"}, "c": {"type": "text"},
        }
        walk = {
            "screen-1": {"type": "FRAME"},
            "a": {"type": "TEXT"}, "b": {"type": "TEXT"}, "c": {"type": "TEXT"},
        }
        # 4/4 = 1.0, passes any threshold
        assert score_coverage(ir, walk).passed is True
        # Drop one, ratio = 0.75, fails default (0.8)
        drop = dict(walk); del drop["c"]
        assert score_coverage(ir, drop, threshold=0.8).passed is False
        # Same 0.75 passes with looser threshold
        assert score_coverage(ir, drop, threshold=0.5).passed is True


class TestScoreFontReadiness:
    def test_no_errors_passes(self) -> None:
        d = score_font_readiness([])
        assert d.passed is True
        assert d.value == 1.0

    def test_other_errors_ignored(self) -> None:
        d = score_font_readiness([
            {"kind": "render_thrown", "error": "x"},
        ])
        assert d.passed is True

    def test_text_set_failed_fails_hard(self) -> None:
        d = score_font_readiness([{
            "kind": "text_set_failed",
            "error": (
                'in set_fontName: Cannot use unloaded font "Inter Semi Bold". '
                'Please call figma.loadFontAsync...'
            ),
        }])
        assert d.passed is False
        assert d.value <= 0.5
        assert "Inter Semi Bold" in d.diagnostic


class TestScoreComponentChildConsistency:
    def test_no_errors_passes(self) -> None:
        d = score_component_child_consistency([])
        assert d.passed is True

    def test_f2_appendchild_into_instance_fails(self) -> None:
        d = score_component_child_consistency([{
            "kind": "render_thrown",
            "error": (
                "in appendChild: Cannot move node. "
                "New parent is an instance or is inside of an instance"
            ),
        }])
        assert d.passed is False
        assert d.value <= 0.3
        assert "appendChild" in d.diagnostic

    def test_unrelated_render_thrown_passes(self) -> None:
        d = score_component_child_consistency([{
            "kind": "render_thrown",
            "error": "some other error",
        }])
        assert d.passed is True


class TestScoreLeafTypeStructural:
    def test_no_violations_passes(self) -> None:
        ir = {
            "s": {"type": "screen", "children": ["c"]},
            "c": {"type": "card", "children": ["h", "b"]},
            "h": {"type": "heading"},
            "b": {"type": "button"},
        }
        d = score_leaf_type_structural(ir)
        assert d.passed is True

    def test_button_with_children_fails(self) -> None:
        """Button is a LEAF in catalog (Mode-1 INSTANCE). A child
        under it is an F4 structural error — the root cause of F2."""
        ir = {
            "btn": {
                "type": "button",
                "children": ["label", "icon"],
            },
        }
        d = score_leaf_type_structural(ir)
        assert d.passed is False
        assert "btn" in d.diagnostic

    def test_leaf_types_coverage(self) -> None:
        """All the catalog leaves should be flagged when given
        children."""
        for lt in ("text", "icon", "button", "switch", "chip"):
            ir = {"x": {"type": lt, "children": ["y"]}}
            d = score_leaf_type_structural(ir)
            assert d.passed is False, f"Expected {lt} to fail with children"


class TestScoreFidelityAggregate:
    def test_all_green(self) -> None:
        ir = {"screen-1": {"type": "screen", "children": ["c"]}, "c": {"type": "card"}}
        walk = {"screen-1": {"type": "FRAME"}, "c": {"type": "FRAME"}}
        report = score_fidelity(
            ir_elements=ir, walk_eid_map=walk, walk_errors=[],
        )
        assert report.all_passed is True
        assert report.aggregate_min == 1.0
        assert report.to_ten() == 10.0

    def test_tier_b_prompt3_scored(self) -> None:
        """Reproduce the Tier-B prompt 3 failure mode: IR has 7,
        rendered has 3, one appendChild-into-instance fires,
        cascading abort. Must score low."""
        ir = {
            "screen-1": {"type": "screen", "children": ["card"]},
            "card": {"type": "card", "children": ["row"]},
            "row": {"type": "frame", "children": ["label", "desc", "toggle"]},
            "label": {"type": "text"},
            "desc": {"type": "text"},
            "toggle": {
                "type": "switch",  # LEAF in our table
                "children": ["handle"],  # F4 violation
            },
            "handle": {"type": "ellipse"},
        }
        walk = {
            "screen-1": {"type": "FRAME"},
            "card": {"type": "FRAME"},
            "row": {"type": "FRAME"},
        }
        errors = [{
            "kind": "render_thrown",
            "error": (
                "in appendChild: Cannot move node. "
                "New parent is an instance or is inside of an instance"
            ),
        }]
        report = score_fidelity(
            ir_elements=ir, walk_eid_map=walk, walk_errors=errors,
        )
        assert report.all_passed is False
        # Min is floored by F2 (component_child_consistency = 0.2)
        assert report.aggregate_min <= 0.3
        # At least 3 of 4 dims fail for this tier-B replay
        failed = [d for d in report.dimensions if not d.passed]
        assert len(failed) >= 3

    def test_partial_failure_reports_all_dims(self) -> None:
        """Verify each dimension ships its diagnostic regardless
        of outcome."""
        report = score_fidelity(
            ir_elements={"s": {"type": "screen"}},
            walk_eid_map={"s": {"type": "FRAME"}},
            walk_errors=[{
                "kind": "text_set_failed",
                "error": 'font "Inter Bold" not loaded',
            }],
        )
        names = {d.name for d in report.dimensions}
        assert names == {
            "coverage", "font_readiness",
            "component_child_consistency", "leaf_type_structural",
        }


class TestScoreRenderResult:
    """Adapter: scorer ingests a WalkResult directly (multi-backend
    contract)."""

    def test_adapts_walk_result_to_fidelity_report(self) -> None:
        from dd.render_protocol import WalkResult
        walk = WalkResult(
            ok=True,
            eid_map={"s": {"type": "FRAME"}, "b": {"type": "FRAME"}},
            errors=[],
            raw={},
        )
        ir = {"s": {"type": "screen", "children": ["b"]}, "b": {"type": "card"}}
        report = score_render_result(ir, walk)
        assert isinstance(report, FidelityReport)
        assert report.all_passed is True

    def test_adapts_walk_result_with_errors(self) -> None:
        from dd.render_protocol import WalkResult
        walk = WalkResult(
            ok=True,
            eid_map={"s": {"type": "FRAME"}},
            errors=[{
                "kind": "render_thrown",
                "error": (
                    "in appendChild: Cannot move node. "
                    "New parent is an instance or is inside of an instance"
                ),
            }],
            raw={},
        )
        ir = {"s": {"type": "screen"}}
        report = score_render_result(ir, walk)
        # F2 fires → component_child_consistency fails
        assert any(
            not d.passed and d.name == "component_child_consistency"
            for d in report.dimensions
        )


class TestVLMScorer:
    """Mock-client coverage for vlm_score_via_gemini. Keeps real
    Gemini out of the test suite."""

    def _mock_client(self, text: str):
        client = MagicMock()
        response = MagicMock()
        response.text = text
        client.generate_content.return_value = response
        return client

    def test_parses_plain_integer(self) -> None:
        client = self._mock_client("8")
        d = vlm_score_via_gemini(
            client, screenshot_png=b"x", prompt="p",
        )
        assert d.passed is True
        assert d.value == pytest.approx(0.8)
        assert "Gemini: 8/10" in d.diagnostic

    def test_parses_score_with_punctuation(self) -> None:
        """Old split()/isdigit() path would have missed this —
        new \\b regex catches it."""
        client = self._mock_client("The render scores 7.")
        d = vlm_score_via_gemini(
            client, screenshot_png=b"x", prompt="p",
        )
        assert d.value == pytest.approx(0.7)

    def test_parses_10(self) -> None:
        client = self._mock_client("10/10")
        d = vlm_score_via_gemini(
            client, screenshot_png=b"x", prompt="p",
        )
        assert d.value == pytest.approx(1.0)

    def test_low_score_fails(self) -> None:
        client = self._mock_client("4")
        d = vlm_score_via_gemini(
            client, screenshot_png=b"x", prompt="p",
        )
        assert d.passed is False

    def test_retries_then_succeeds(self) -> None:
        client = MagicMock()
        call_count = {"n": 0}

        def fake_generate(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("transient blip")
            resp = MagicMock()
            resp.text = "9"
            return resp

        client.generate_content.side_effect = fake_generate
        d = vlm_score_via_gemini(
            client, screenshot_png=b"x", prompt="p", retries=3,
        )
        assert d.passed is True
        assert d.value == pytest.approx(0.9)

    def test_all_retries_fail_returns_diagnostic(self) -> None:
        client = MagicMock()
        client.generate_content.side_effect = RuntimeError("always broken")
        d = vlm_score_via_gemini(
            client, screenshot_png=b"x", prompt="p", retries=2,
        )
        assert d.passed is False
        assert d.value == 0.0
        assert "always broken" in d.diagnostic

    def test_no_integer_in_response_fails(self) -> None:
        client = self._mock_client("I cannot rate this.")
        d = vlm_score_via_gemini(
            client, screenshot_png=b"x", prompt="p", retries=1,
        )
        assert d.passed is False


class TestEdgeCases:
    def test_empty_ir_and_empty_walk_passes(self) -> None:
        """No work is trivially perfect work."""
        report = score_fidelity(
            ir_elements={}, walk_eid_map={}, walk_errors=[],
        )
        assert report.aggregate_min == 1.0
        assert report.all_passed is True

    def test_ir_element_missing_type_field(self) -> None:
        """A spec element without `type` shouldn't crash any
        dimension. Defensive against pathological inputs."""
        ir = {"mystery": {"children": ["x"]}}
        walk = {"mystery": {"type": "FRAME"}}
        report = score_fidelity(
            ir_elements=ir, walk_eid_map=walk, walk_errors=[],
        )
        assert report  # no crash

    def test_circular_ir_children_does_not_infinite_loop(self) -> None:
        """Tolerate a corrupt IR where children reference each
        other. Absorbed-set guard should prevent infinite
        recursion."""
        ir = {
            "a": {"type": "frame", "children": ["b"]},
            "b": {"type": "frame", "children": ["a"]},
        }
        walk = {"a": {"type": "FRAME"}, "b": {"type": "FRAME"}}
        # Must return (not hang).
        report = score_fidelity(
            ir_elements=ir, walk_eid_map=walk, walk_errors=[],
        )
        # Coverage = 2 of 2 reachable + non-absorbed
        cov = next(d for d in report.dimensions if d.name == "coverage")
        assert cov.value == 1.0


class TestFidelityReportAggregations:
    def test_min_is_conservative(self) -> None:
        r = FidelityReport(dimensions=[
            DimensionScore(name="a", value=0.9, passed=True, diagnostic=""),
            DimensionScore(name="b", value=0.3, passed=False, diagnostic=""),
        ])
        assert r.aggregate_min == 0.3
        assert r.aggregate_mean == 0.6
        assert r.to_ten(mode="min") == 3.0
        assert r.to_ten(mode="mean") == 6.0
        assert r.all_passed is False

    def test_vlm_dim_included_in_aggregation(self) -> None:
        r = FidelityReport(
            dimensions=[
                DimensionScore(name="a", value=1.0, passed=True, diagnostic=""),
            ],
            vlm_dimension=DimensionScore(
                name="vlm_semantic", value=0.4, passed=False,
                diagnostic="",
            ),
        )
        assert r.aggregate_min == 0.4
        assert r.all_passed is False
