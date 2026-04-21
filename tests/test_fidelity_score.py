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
    build_som_annotations,
    compute_coverage_from_types,
    score_canvas_coverage,
    score_component_child_consistency,
    score_component_coverage,
    score_content_richness,
    score_coverage,
    score_fidelity,
    score_font_readiness,
    score_leaf_type_structural,
    score_render_result,
    score_rootedness,
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

    def test_post_guard_append_child_failed_with_instance_fails(
        self,
    ) -> None:
        """After commits b95d3bc + b26ddf7, per-op guards catch
        appendChild failures as `kind: 'append_child_failed'`
        rather than `render_thrown`. The dim must recognise both
        shapes — the defect class (leaf-under-INSTANCE, or Mode-1-
        parent-with-children) is the same."""
        d = score_component_child_consistency([{
            "kind": "append_child_failed",
            "eid": "icon_button-1",
            "error": (
                "in appendChild: Cannot move node. "
                "New parent is an instance or is inside of an instance"
            ),
        }])
        assert d.passed is False
        assert "icon_button-1" in d.diagnostic

    def test_append_child_failed_without_instance_passes(self) -> None:
        """Not every append_child_failed is F2 — only ones where
        the Figma error mentions 'instance'. Other appendChild
        failures (malformed node, etc.) don't hit this dim."""
        d = score_component_child_consistency([{
            "kind": "append_child_failed",
            "eid": "some-node",
            "error": "in appendChild: node is null",
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


class TestScoreCanvasCoverage:
    """Canvas coverage dim: fraction of root's bbox covered by
    direct-child bboxes. Catches the visually-blank render the
    structural dims can't see (e.g. 20-px-tall toast in a 926-px
    screen scoring 10/10 on structural alone).

    Scoped to the Tier D re-gate subtree failure (2026-04-21)."""

    def test_full_coverage_passes(self) -> None:
        walk = {
            "screen-1": {"type": "FRAME", "width": 400, "height": 800},
            "card-1": {"type": "FRAME", "width": 400, "height": 800},
        }
        ir = {"screen-1": {"children": ["card-1"]}, "card-1": {}}
        d = score_canvas_coverage("screen-1", ir, walk)
        assert d.value == 1.0
        assert d.passed is True

    def test_subtree_tiny_toast_fails(self) -> None:
        """Reproduce the Tier-D subtree case: 396x20 toast in a
        428x926 screen = 2% coverage. Under the clamped scale,
        value = 0.02/0.10 threshold = 0.20 — dramatic fail."""
        walk = {
            "screen-1": {"type": "FRAME", "width": 428, "height": 926},
            "toast-1": {"type": "FRAME", "width": 396, "height": 20},
        }
        ir = {"screen-1": {"children": ["toast-1"]}, "toast-1": {}}
        d = score_canvas_coverage("screen-1", ir, walk)
        assert d.value < 0.30  # well below pass-band
        assert d.passed is False
        assert "sparse" in d.diagnostic.lower() or "below" in d.diagnostic.lower()

    def test_partial_coverage_at_threshold(self) -> None:
        """One card covering ~25% of the screen passes and scores
        full credit (ratio >= threshold → value clamped to 1.0).
        The raw ratio lives in the diagnostic for inspection."""
        walk = {
            "screen-1": {"type": "FRAME", "width": 400, "height": 800},
            "card-1": {"type": "FRAME", "width": 400, "height": 200},
        }
        ir = {"screen-1": {"children": ["card-1"]}, "card-1": {}}
        d = score_canvas_coverage("screen-1", ir, walk)
        assert d.value == 1.0
        assert d.passed is True
        assert "25" in d.diagnostic  # raw ratio surfaced

    def test_missing_root_skipped(self) -> None:
        """No root_eid → dim skipped (rootedness covers this case)."""
        d = score_canvas_coverage(None, {}, {})
        assert d.value == 1.0
        assert d.passed is True

    def test_root_without_dimensions_skipped(self) -> None:
        walk = {"screen-1": {"type": "FRAME"}}  # no width/height
        ir = {"screen-1": {}}
        d = score_canvas_coverage("screen-1", ir, walk)
        assert d.value == 1.0
        assert d.passed is True

    def test_threshold_configurable(self) -> None:
        """Caller can tune the threshold. Default 0.10 is for screen
        roots; subtrees may want stricter."""
        walk = {
            "screen-1": {"type": "FRAME", "width": 400, "height": 800},
            "card-1": {"type": "FRAME", "width": 400, "height": 60},  # 7.5%
        }
        ir = {"screen-1": {"children": ["card-1"]}, "card-1": {}}
        assert score_canvas_coverage(
            "screen-1", ir, walk, threshold=0.05,
        ).passed is True
        assert score_canvas_coverage(
            "screen-1", ir, walk, threshold=0.10,
        ).passed is False


class TestScoreContentRichness:
    """Content richness: count of rendered nodes that carry some
    visible content. A node is 'visible' if it has fills, characters,
    INSTANCE type (paints from master), or non-zero effects.

    Catches trivial outputs (2-3 nodes, nothing to see) that pass
    the structural dims trivially."""

    def test_rich_render_passes(self) -> None:
        walk = {
            "a": {"type": "FRAME", "fills": [{"type": "solid"}]},
            "b": {"type": "TEXT", "characters": "Hello"},
            "c": {"type": "INSTANCE"},
            "d": {"type": "FRAME", "effectCount": 1},
        }
        d = score_content_richness(walk)
        assert d.value == 1.0
        assert d.passed is True

    def test_subtree_only_two_visible_fails(self) -> None:
        """Reproduce Tier-D subtree: screen bg + icon instance,
        toast frame has nothing. Must fail."""
        walk = {
            "screen-1": {"type": "FRAME", "fills": [{"type": "solid"}]},
            "toast-1": {"type": "FRAME", "effectCount": 0},  # nothing visible
            "icon_button-1": {"type": "INSTANCE"},
        }
        d = score_content_richness(walk)
        # 2 visible out of min 3 → 0.67 → under 0.7 pass threshold
        assert d.value < 0.7
        assert d.passed is False

    def test_empty_walk_skipped(self) -> None:
        """Empty walk is coverage/rootedness's concern, not ours."""
        d = score_content_richness({})
        assert d.value == 1.0
        assert d.passed is True
        assert "skip" in d.diagnostic.lower()

    def test_strokes_count_as_visible(self) -> None:
        walk = {
            "a": {"type": "FRAME", "strokes": [{"type": "solid"}]},
            "b": {"type": "FRAME", "strokes": [{"type": "solid"}]},
            "c": {"type": "FRAME", "strokes": [{"type": "solid"}]},
        }
        d = score_content_richness(walk)
        assert d.value == 1.0

    def test_nodes_without_any_visible_signal_fail(self) -> None:
        walk = {
            "a": {"type": "FRAME"},
            "b": {"type": "FRAME"},
            "c": {"type": "FRAME"},
        }
        d = score_content_richness(walk)
        assert d.value == 0.0
        assert d.passed is False
        assert "0" in d.diagnostic

    def test_min_visible_configurable(self) -> None:
        walk = {"a": {"type": "INSTANCE"}, "b": {"type": "INSTANCE"}}
        # Default min_visible=3 → 2/3 → fail
        assert score_content_richness(walk).passed is False
        # Caller relaxes to 2 → 2/2 → pass
        assert score_content_richness(walk, min_visible=2).passed is True


class TestBuildSomAnnotations:
    """Build SoM annotations from IR + walk payload. The annotations
    format matches classify_vision_som's render_som_overlay:
    {id, x, y, w, h, rotation}. id == integer sequential mark index.
    """

    def test_builds_annotations_from_walk_bboxes(self) -> None:
        ir = {
            "screen-1": {"type": "screen"},
            "card-1": {"type": "card"},
            "button-1": {"type": "button"},
        }
        walk = {
            "screen-1": {"x": 0, "y": 0, "width": 400, "height": 800, "rotation": 0},
            "card-1": {"x": 10, "y": 20, "width": 380, "height": 200, "rotation": 0},
            "button-1": {"x": 150, "y": 160, "width": 100, "height": 40, "rotation": 0},
        }
        anns, id_to_eid = build_som_annotations(ir, walk)
        # screen excluded by default (root, not a semantic component)
        assert len(anns) == 2
        assert all(
            set(a.keys()) >= {"id", "x", "y", "w", "h", "rotation"}
            for a in anns
        )
        # id_to_eid maps mark integer → IR eid
        assert {id_to_eid[a["id"]] for a in anns} == {"card-1", "button-1"}

    def test_missing_bbox_fields_default_to_zero(self) -> None:
        """Walks without x/y (pre-change payloads) should not crash —
        annotations fall back to 0. Callers can detect and skip."""
        ir = {"card-1": {"type": "card"}}
        walk = {"card-1": {"width": 100, "height": 50}}
        anns, _ = build_som_annotations(ir, walk)
        assert len(anns) == 1
        assert anns[0]["x"] == 0
        assert anns[0]["y"] == 0
        assert anns[0]["w"] == 100
        assert anns[0]["h"] == 50

    def test_exclude_types_filters_annotations(self) -> None:
        ir = {
            "screen-1": {"type": "screen"},
            "frame-1": {"type": "frame"},
            "button-1": {"type": "button"},
        }
        walk = {
            "screen-1": {"x": 0, "y": 0, "width": 400, "height": 800},
            "frame-1": {"x": 0, "y": 0, "width": 100, "height": 50},
            "button-1": {"x": 10, "y": 20, "width": 80, "height": 30},
        }
        anns, id_to_eid = build_som_annotations(
            ir, walk, exclude_types=frozenset({"screen", "frame"}),
        )
        assert len(anns) == 1
        assert id_to_eid[anns[0]["id"]] == "button-1"

    def test_unrendered_elements_skipped(self) -> None:
        """IR elements absent from the walk (Phase-2 orphan, leaf parent
        violation, etc.) can't be marked. Skip them cleanly."""
        ir = {
            "card-1": {"type": "card"},
            "orphan-1": {"type": "button"},
        }
        walk = {
            "card-1": {"x": 0, "y": 0, "width": 100, "height": 50},
            # no orphan-1 in walk
        }
        anns, id_to_eid = build_som_annotations(ir, walk)
        assert len(anns) == 1
        assert id_to_eid[anns[0]["id"]] == "card-1"


class TestComputeCoverageFromTypes:
    """Pure bag-match over expected/detected canonical types."""

    def test_perfect_match(self) -> None:
        precision, recall, info = compute_coverage_from_types(
            expected=["button", "text_input", "link"],
            detected=["button", "text_input", "link"],
        )
        assert precision == 1.0
        assert recall == 1.0

    def test_missing_one_reduces_recall_only(self) -> None:
        precision, recall, info = compute_coverage_from_types(
            expected=["button", "text_input", "link"],
            detected=["button", "text_input"],
        )
        assert precision == 1.0  # both detected match
        assert recall == pytest.approx(2 / 3)

    def test_hallucinated_extra_reduces_precision_only(self) -> None:
        precision, recall, info = compute_coverage_from_types(
            expected=["button", "link"],
            detected=["button", "link", "text_input"],
        )
        assert precision == pytest.approx(2 / 3)
        assert recall == 1.0

    def test_duplicate_types_bag_matched(self) -> None:
        """Login has 2 text_inputs; if SoM sees only 1, recall
        should reflect that (bag-match, not set-match)."""
        precision, recall, info = compute_coverage_from_types(
            expected=["text_input", "text_input", "button"],
            detected=["text_input", "button"],
        )
        # 2 matches (1 text_input + 1 button) out of 2 detected + 3 expected
        assert precision == 1.0
        assert recall == pytest.approx(2 / 3)

    def test_unsure_and_container_excluded_from_detected(self) -> None:
        """SoM's sentinel classifications should not count as detection
        (they signal unknown), else precision gets gamed."""
        precision, recall, info = compute_coverage_from_types(
            expected=["button", "link"],
            detected=["button", "unsure", "container"],
        )
        # After exclude: detected = [button] → precision 1/1, recall 1/2
        assert precision == 1.0
        assert recall == 0.5

    def test_empty_expected_is_noop(self) -> None:
        precision, recall, info = compute_coverage_from_types(
            expected=[], detected=["button"],
        )
        # no expectation → recall undefined; return 1.0 skip
        assert recall == 1.0
        # detected has stuff but nothing to match → precision 0
        assert precision == 0.0

    def test_info_exposes_match_counts(self) -> None:
        _, _, info = compute_coverage_from_types(
            expected=["button", "link", "text_input"],
            detected=["button", "link"],
        )
        assert info["matches"] == 2
        assert info["expected_count"] == 3
        assert info["detected_count"] == 2
        assert "missing" in info
        assert info["missing"].get("text_input") == 1


class TestScoreComponentCoverage:
    """Top-level dim: emits two DimensionScore (precision + recall)
    from IR + SoM classifications + walk bboxes."""

    def test_perfect_match_both_dims_pass(self) -> None:
        ir = {
            "screen-1": {"type": "screen"},
            "button-1": {"type": "button"},
            "text-1": {"type": "text"},
        }
        walk = {
            "screen-1": {"x": 0, "y": 0, "width": 400, "height": 800},
            "button-1": {"x": 10, "y": 10, "width": 100, "height": 40},
            "text-1": {"x": 10, "y": 60, "width": 100, "height": 20},
        }
        # Simulate SoM classifications; mark_id sequential from
        # build_som_annotations' ordering.
        anns, id_to_eid = build_som_annotations(ir, walk)
        classifications = [
            {"mark_id": anns[0]["id"], "canonical_type":
             ir[id_to_eid[anns[0]["id"]]]["type"], "confidence": 0.9},
            {"mark_id": anns[1]["id"], "canonical_type":
             ir[id_to_eid[anns[1]["id"]]]["type"], "confidence": 0.9},
        ]
        prec, rec = score_component_coverage(
            ir_elements=ir,
            walk_eid_map=walk,
            classifications=classifications,
        )
        assert prec.value == 1.0 and prec.passed is True
        assert rec.value == 1.0 and rec.passed is True
        assert prec.name == "component_precision"
        assert rec.name == "component_recall"

    def test_mismatch_reduces_precision_and_recall(self) -> None:
        ir = {
            "screen-1": {"type": "screen"},
            "button-1": {"type": "button"},
            "link-1": {"type": "link"},
        }
        walk = {
            "screen-1": {"x": 0, "y": 0, "width": 400, "height": 800},
            "button-1": {"x": 10, "y": 10, "width": 100, "height": 40},
            "link-1": {"x": 10, "y": 60, "width": 100, "height": 20},
        }
        anns, id_to_eid = build_som_annotations(ir, walk)
        # Both SoM calls misfire: button → text_input, link → unsure.
        # Expected bag: [button, link]. Detected bag (after unsure-
        # filter): [text_input]. Matches: 0.
        classifications = [
            {"mark_id": a["id"], "canonical_type": "text_input"
             if id_to_eid[a["id"]] == "button-1" else "unsure",
             "confidence": 0.5}
            for a in anns
        ]
        prec, rec = score_component_coverage(
            ir_elements=ir,
            walk_eid_map=walk,
            classifications=classifications,
        )
        assert prec.passed is False
        assert rec.passed is False

    def test_no_expected_types_is_graceful(self) -> None:
        """IR with only a screen root → nothing to match. Both dims
        pass-through (1.0) rather than /0."""
        ir = {"screen-1": {"type": "screen"}}
        walk = {"screen-1": {"x": 0, "y": 0, "width": 400, "height": 800}}
        prec, rec = score_component_coverage(
            ir_elements=ir,
            walk_eid_map=walk,
            classifications=[],
        )
        assert prec.value == 1.0 and prec.passed is True
        assert rec.value == 1.0 and rec.passed is True
        assert "skip" in prec.diagnostic.lower()


class TestScoreFidelityAggregate:
    def test_all_green(self) -> None:
        """Green when structural AND visual content are present."""
        ir = {
            "screen-1": {"type": "screen", "children": ["c"]},
            "c": {"type": "card"},
        }
        walk = {
            "screen-1": {
                "type": "FRAME", "width": 400, "height": 800,
                "fills": [{"type": "solid"}],
            },
            # Card fully covers the screen — content_richness +
            # canvas_coverage both hit 1.0.
            "c": {
                "type": "FRAME", "width": 400, "height": 800,
                "fills": [{"type": "solid"}],
                "characters": "title text",
            },
        }
        # Add 2 more visible nodes so content_richness passes
        # (default min_visible=3).
        walk["ic-1"] = {"type": "INSTANCE"}
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
            "coverage", "rootedness", "font_readiness",
            "component_child_consistency", "leaf_type_structural",
            "canvas_coverage", "content_richness",
        }


class TestScoreRootedness:
    """Rootedness dim: the rendered tree must be attached to the
    page. Catches the 'flat hierarchy' failure mode where Phase 2
    aborts and createFrame-auto-parented nodes stay at page root."""

    def test_root_in_walk_and_no_errors_passes(self) -> None:
        walk_map = {"screen-1": {"type": "FRAME"}}
        d = score_rootedness("screen-1", walk_map, [])
        assert d.passed is True
        assert d.value == 1.0

    def test_root_missing_from_walk_fails_hard(self) -> None:
        """If the walker couldn't find the root eid, nothing ever
        got parented — score cap 0.1."""
        d = score_rootedness("screen-1", {}, [])
        assert d.passed is False
        assert d.value <= 0.2
        assert "missing from rendered walk" in d.diagnostic

    def test_root_append_failed_error_fails(self) -> None:
        """The critical failure mode: _rootPage.appendChild throws,
        tree orphaned. Score 0.4 (worse than imperfect but not as
        catastrophic as missing entirely — some of the subtree may
        still render via auto-parenting)."""
        walk_map = {"screen-1": {"type": "FRAME"}}
        errs = [{"kind": "root_append_failed", "error": "..."}]
        d = score_rootedness("screen-1", walk_map, errs)
        assert d.passed is False
        assert d.value <= 0.5
        assert "root_append_failed" in d.diagnostic

    def test_append_child_failed_also_fails(self) -> None:
        """Any cascading appendChild error signals broken nesting —
        even if the root itself attached, interior wiring dropped."""
        walk_map = {"screen-1": {"type": "FRAME"}}
        errs = [{"kind": "append_child_failed", "error": "..."}]
        d = score_rootedness("screen-1", walk_map, errs)
        assert d.passed is False
        assert "append_child_failed" in d.diagnostic

    def test_no_root_eid_passes_through(self) -> None:
        """Caller didn't provide a root to check against — don't
        false-positive block the gate."""
        d = score_rootedness(None, {"anything": {}}, [])
        assert d.passed is True
        assert d.value == 1.0
        assert "no root_eid" in d.diagnostic

    def test_integrated_into_score_fidelity(self) -> None:
        """score_fidelity auto-infers root_eid from ir_elements
        when the caller doesn't supply it."""
        # Case A: root present in walk, no errors → all dims pass
        ir = {
            "screen-1": {"type": "screen", "children": ["btn"]},
            "btn": {"type": "button"},
        }
        walk = {"screen-1": {"type": "FRAME"}, "btn": {"type": "INSTANCE"}}
        report = score_fidelity(
            ir_elements=ir, walk_eid_map=walk, walk_errors=[],
        )
        root_dim = next(d for d in report.dimensions if d.name == "rootedness")
        assert root_dim.passed is True

        # Case B: append_child_failed fires → rootedness dim fails
        report2 = score_fidelity(
            ir_elements=ir, walk_eid_map=walk,
            walk_errors=[{
                "kind": "append_child_failed", "error": "...",
            }],
        )
        root_dim2 = next(
            d for d in report2.dimensions if d.name == "rootedness"
        )
        assert root_dim2.passed is False


class TestScoreRenderResult:
    """Adapter: scorer ingests a WalkResult directly (multi-backend
    contract)."""

    def test_adapts_walk_result_to_fidelity_report(self) -> None:
        from dd.render_protocol import WalkResult
        # Realistic walk: nodes with visible content + dimensions so
        # canvas_coverage and content_richness both pass.
        walk = WalkResult(
            ok=True,
            eid_map={
                "s": {
                    "type": "FRAME", "width": 400, "height": 800,
                    "fills": [{"type": "solid"}],
                },
                "b": {
                    "type": "FRAME", "width": 400, "height": 800,
                    "fills": [{"type": "solid"}],
                    "characters": "body",
                },
                "ic-1": {"type": "INSTANCE"},
            },
            errors=[],
            raw={},
        )
        ir = {
            "s": {"type": "screen", "children": ["b", "ic-1"]},
            "b": {"type": "card"},
            "ic-1": {"type": "icon"},
        }
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
