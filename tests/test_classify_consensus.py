"""Tests for the three-source consensus computation (M7.0.a).

Rule v1 per plan-synthetic-gen.md §5.1.a:

    if all three agree           → commit, consensus_method = "unanimous"
    elif any source is `unsure`  → `unsure`, "any_unsure"
    elif 2/3 agree               → commit majority, "majority"
    else (all differ)            → `unsure`, "three_way_disagreement"

Rule v1 is maximally conservative — `any_unsure` intentionally wins
over `majority` so a high-confidence LLM + cross-screen agreement
with an `unsure` per-screen still gets flagged. Rule v2 (ratcheted in
after the full-corpus run) will add bias-aware overrides. Resolution
recomputes from persisted raw verdicts — no re-classification needed.

Extended branches cover degraded-input cases (one or two sources
available, or all missing). These are sensible fallbacks, NOT part of
the plan's rule-v1 spec.
"""

from __future__ import annotations

import pytest

from dd.classify_consensus import (
    build_calibrated_weights,
    compute_consensus_v1,
    compute_consensus_v2,
    compute_consensus_v3,
)


class TestConsensusV1ThreeSources:
    """All three sources present — the canonical rule-v1 branches."""

    def test_all_three_agree_commits_unanimous(self):
        assert compute_consensus_v1("button", "button", "button") == (
            "button", "unanimous", False,
        )

    def test_container_unanimous_commits(self):
        # `container` is a valid canonical type; unanimous means
        # unanimous — even on container. Rule v1 does NOT downgrade
        # container to unsure; that's a rule-v2 override.
        assert compute_consensus_v1(
            "container", "container", "container"
        ) == (
            "container", "unanimous", False,
        )

    def test_any_unsure_flags_even_if_others_agree(self):
        # Rule v1: any_unsure wins over majority. LLM=button +
        # CS=button would be 2/3 majority, but PS=unsure forces the
        # answer to unsure + any_unsure (flagged).
        assert compute_consensus_v1("button", "unsure", "button") == (
            "unsure", "any_unsure", True,
        )

    def test_all_three_unsure_still_any_unsure(self):
        assert compute_consensus_v1("unsure", "unsure", "unsure") == (
            "unsure", "any_unsure", True,
        )

    def test_two_of_three_agree_majority_commits(self):
        # No source is unsure; 2/3 agreement commits majority.
        assert compute_consensus_v1(
            "button", "button", "container"
        ) == (
            "button", "majority", False,
        )

    def test_majority_on_different_pairs(self):
        # Majority regardless of which pair agrees.
        assert compute_consensus_v1("card", "button", "button") == (
            "button", "majority", False,
        )
        assert compute_consensus_v1("button", "card", "button") == (
            "button", "majority", False,
        )

    def test_all_three_differ_three_way_disagreement(self):
        assert compute_consensus_v1(
            "button", "card", "container"
        ) == (
            "unsure", "three_way_disagreement", True,
        )


class TestConsensusV1DegradedInput:
    """Fewer than three sources available (e.g., vision stage failed
    or hasn't run yet). Rule v1 degrades gracefully rather than
    blowing up. These branches are NOT part of the plan's spec, but
    must have a deterministic answer.
    """

    def test_all_three_none_flagged_no_sources(self):
        assert compute_consensus_v1(None, None, None) == (
            None, "no_sources", True,
        )

    def test_single_source_passes_through(self):
        # Only LLM set.
        assert compute_consensus_v1("button", None, None) == (
            "button", "single_source", False,
        )
        # Only PS set.
        assert compute_consensus_v1(None, "button", None) == (
            "button", "single_source", False,
        )
        # Only CS set.
        assert compute_consensus_v1(None, None, "button") == (
            "button", "single_source", False,
        )

    def test_single_source_unsure_flagged(self):
        assert compute_consensus_v1("unsure", None, None) == (
            "unsure", "single_source", True,
        )

    def test_two_sources_agree_commits(self):
        assert compute_consensus_v1("button", "button", None) == (
            "button", "two_source_unanimous", False,
        )
        assert compute_consensus_v1("button", None, "button") == (
            "button", "two_source_unanimous", False,
        )
        assert compute_consensus_v1(None, "button", "button") == (
            "button", "two_source_unanimous", False,
        )

    def test_two_sources_disagree_flagged(self):
        assert compute_consensus_v1("button", "card", None) == (
            "unsure", "two_way_disagreement", True,
        )

    def test_two_sources_any_unsure_flagged(self):
        # Consistent with 3-source any_unsure rule.
        assert compute_consensus_v1("button", "unsure", None) == (
            "unsure", "any_unsure", True,
        )
        assert compute_consensus_v1("unsure", None, "button") == (
            "unsure", "any_unsure", True,
        )


class TestConsensusV2Weighted:
    """Rule v2 — CS gets 2x weight (empirical: 67.6% match rate vs
    55.7%/51.0% for LLM/PS on the full-corpus review corpus).
    """

    def test_all_three_agree_still_unanimous(self):
        assert compute_consensus_v2("button", "button", "button") == (
            "button", "unanimous", False,
        )

    def test_llm_ps_agree_cs_dissents_flags_tie(self):
        # LLM(1) + PS(1) = 2, CS(2) = 2 → tie → flag.
        # This is the signature behavior change: v1 picks majority
        # (LLM+PS=button), v2 flags the disagreement because CS's
        # weight matches the pair.
        assert compute_consensus_v2("button", "button", "card") == (
            "unsure", "weighted_tie", True,
        )

    def test_cs_outvotes_single_dissent_llm(self):
        # LLM=a(1), PS=b(1), CS=b(2) → b wins 3-1.
        assert compute_consensus_v2("button", "card", "card") == (
            "card", "weighted_majority", False,
        )

    def test_cs_outvotes_three_way_disagree(self):
        # LLM=a(1), PS=b(1), CS=c(2) → c wins 2-1-1. This is where
        # rule v2 recovers 51 flagged cases from v1's
        # three_way_disagreement bucket.
        assert compute_consensus_v2(
            "button", "card", "list_item",
        ) == (
            "list_item", "weighted_majority", False,
        )

    def test_any_unsure_flags_even_when_pair_matches(self):
        # Rule v1 semantics preserved — unsure short-circuits.
        assert compute_consensus_v2("unsure", "button", "button") == (
            "unsure", "any_unsure", True,
        )

    def test_llm_cs_agree_ps_dissents_wins_3_1(self):
        # LLM=a(1), CS=a(2), PS=b(1) → a wins 3-1.
        assert compute_consensus_v2("button", "card", "button") == (
            "button", "weighted_majority", False,
        )

    def test_ps_cs_agree_llm_dissents_wins_3_1(self):
        # PS=a(1), CS=a(2), LLM=b(1) → a wins 3-1.
        assert compute_consensus_v2("card", "button", "button") == (
            "button", "weighted_majority", False,
        )

    def test_two_sources_cs_alone_is_single_source(self):
        assert compute_consensus_v2(None, None, "button") == (
            "button", "single_source", False,
        )

    def test_two_sources_both_present_and_agree(self):
        assert compute_consensus_v2(None, "button", "button") == (
            "button", "two_source_unanimous", False,
        )

    def test_two_sources_cs_wins_against_one(self):
        # Only PS and CS. PS=a(1), CS=b(2) → b wins 2-1.
        assert compute_consensus_v2(None, "card", "button") == (
            "button", "weighted_majority", False,
        )

    def test_two_sources_llm_loses_to_cs(self):
        # LLM=a(1), CS=b(2) → b wins 2-1.
        assert compute_consensus_v2("card", None, "button") == (
            "button", "weighted_majority", False,
        )

    def test_two_sources_llm_and_ps_tie_if_disagree(self):
        # LLM=a(1), PS=b(1), no CS → 1-1 → tie → flag.
        assert compute_consensus_v2("card", "button", None) == (
            "unsure", "weighted_tie", True,
        )

    def test_no_sources_flag_no_sources(self):
        assert compute_consensus_v2(None, None, None) == (
            None, "no_sources", True,
        )

    def test_single_unsure_source_flags(self):
        assert compute_consensus_v2("unsure", None, None) == (
            "unsure", "single_source", True,
        )


class TestConsensusV3Calibrated:
    """Rule v3 — per-type weighted consensus derived from review data.

    Each (source, predicted_type) pair has a calibrated weight based on
    historical acceptance rate. Voting sums the weights; winner commits
    if strictly above runner-up AND the winning share exceeds a
    minimum-confidence threshold.
    """

    def test_uniform_weights_behaves_like_v1_unanimous(self):
        """With uniform weights (all 1.0), v3 on 3 agreeing sources
        should commit unanimous — same as v1.
        """
        weights = {}  # empty → uniform default
        assert compute_consensus_v3(
            "button", "button", "button", weights=weights,
        ) == ("button", "unanimous", False)

    def test_uniform_weights_two_of_three_majority_commits(self):
        weights = {}
        # LLM=button, PS=button, CS=container. 2/3 → button wins.
        assert compute_consensus_v3(
            "button", "button", "container", weights=weights,
        ) == ("button", "calibrated_majority", False)

    def test_high_weight_source_can_overrule_majority(self):
        """This is the whole point of v3: a source with very high
        historical accuracy for a type should outvote a pair with
        low weight for their type.
        """
        weights = {
            ("llm", "container"): 0.3,       # LLM usually wrong on container
            ("vision_ps", "container"): 0.3,
            ("vision_cs", "list_item"): 0.95,  # CS is typically right on list_item
        }
        # LLM+PS say container (low weight each), CS says list_item (high).
        # Weighted: container = 0.6, list_item = 0.95 → list_item wins.
        assert compute_consensus_v3(
            "container", "container", "list_item", weights=weights,
        ) == ("list_item", "calibrated_majority", False)

    def test_low_weight_source_cant_overrule_high_pair(self):
        """If the "outvoted" source has a higher individual weight than
        either of the pair, but the pair's COMBINED weight exceeds it,
        the pair still wins. That's v3's protection against single-
        source overconfidence."""
        weights = {
            ("llm", "button"): 0.5,
            ("vision_ps", "button"): 0.5,
            ("vision_cs", "card"): 0.7,
        }
        # LLM+PS = button (0.5+0.5=1.0). CS = card (0.7). button wins.
        assert compute_consensus_v3(
            "button", "button", "card", weights=weights,
        ) == ("button", "calibrated_majority", False)

    def test_any_unsure_short_circuits(self):
        # v3 preserves "any unsure → flag" semantics from v1/v2.
        weights = {("llm", "button"): 0.9, ("vision_cs", "button"): 0.95}
        assert compute_consensus_v3(
            "button", "unsure", "button", weights=weights,
        ) == ("unsure", "any_unsure", True)

    def test_three_way_disagreement_picks_highest_weighted(self):
        """All three differ. v3 picks the source with the highest
        weight for its verdict — no flag unless confidence is below
        a threshold.
        """
        weights = {
            ("llm", "container"): 0.4,
            ("vision_ps", "button"): 0.6,
            ("vision_cs", "list_item"): 0.85,
        }
        # 3 different types, weights 0.4 / 0.6 / 0.85 → list_item wins.
        assert compute_consensus_v3(
            "container", "button", "list_item", weights=weights,
        ) == ("list_item", "calibrated_majority", False)

    def test_tied_top_weights_flag_as_tie(self):
        weights = {
            ("llm", "button"): 0.5,
            ("vision_ps", "card"): 0.5,
        }
        # 2 sources (CS absent), tied weights → flag.
        assert compute_consensus_v3(
            "button", "card", None, weights=weights,
        ) == ("unsure", "calibrated_tie", True)

    def test_missing_weight_uses_uniform_default(self):
        """Untrained (source, type) pairs get a default weight of 0.5
        so v3 degrades gracefully to something close to uniform for
        novel types.
        """
        weights = {}  # no entries at all
        # 3 different types with default 0.5 each — 3-way tie.
        out = compute_consensus_v3(
            "a", "b", "c", weights=weights,
        )
        # All equal → tie → flag.
        assert out[2] is True  # flagged
        assert out[1] == "calibrated_tie"

    def test_no_sources_flags_no_sources(self):
        assert compute_consensus_v3(
            None, None, None, weights={},
        ) == (None, "no_sources", True)

    def test_single_source_passes_through(self):
        weights = {("vision_cs", "button"): 0.9}
        assert compute_consensus_v3(
            None, None, "button", weights=weights,
        ) == ("button", "single_source", False)


class TestBuildCalibratedWeights:
    """``build_calibrated_weights`` takes review history and produces
    a (source, type) → weight dict. Weight is P(user accepted this
    source | source predicted type T), with Laplace smoothing so
    low-sample types don't swing to extremes.
    """

    def test_empty_reviews_returns_empty_dict(self):
        """No reviews → no calibration data → empty weights. Callers
        should fall back to uniform defaults.
        """
        weights = build_calibrated_weights(reviews=[])
        assert weights == {}

    def test_perfect_source_gets_weight_one(self):
        """When the user accepted LLM every time LLM predicted button,
        LLM's weight for button should be close to 1.0 (with some
        smoothing pull toward 0.5 for small-sample types).
        """
        reviews = [
            {"source_accepted": "llm", "llm_type": "button",
             "vision_ps_type": "card", "vision_cs_type": "card"},
        ] * 20  # 20 confirmations
        weights = build_calibrated_weights(reviews=reviews)
        # 20/20 acceptances — smoothing pulls slightly below 1.0.
        assert weights[("llm", "button")] > 0.9

    def test_unused_source_on_type_yields_low_weight(self):
        """If the user always rejected LLM's button verdict (picked
        another source), LLM's weight for button → near 0.
        """
        reviews = [
            {"source_accepted": "vision_ps", "llm_type": "button",
             "vision_ps_type": "card", "vision_cs_type": "card"},
        ] * 20
        weights = build_calibrated_weights(reviews=reviews)
        # 0/20 acceptance for LLM's "button" — smoothed, should be low.
        assert weights[("llm", "button")] < 0.2

    def test_smoothing_protects_low_sample_types(self):
        """A (source, type) seen only once should get a weight near
        0.5, not 0.0 or 1.0, regardless of that single outcome.
        """
        reviews = [
            {"source_accepted": "llm", "llm_type": "rare_type",
             "vision_ps_type": "other", "vision_cs_type": "other"},
        ]
        weights = build_calibrated_weights(reviews=reviews)
        # 1/1 accepted but smoothing keeps it near 0.5.
        assert 0.4 < weights[("llm", "rare_type")] < 0.85

    def test_ignores_non_accept_source_reviews(self):
        """Only `accept_source` reviews contribute to weight. `override`,
        `unsure`, `skip` don't tell us about source accuracy.
        """
        reviews = [
            {"source_accepted": "llm", "llm_type": "button",
             "vision_ps_type": "button", "vision_cs_type": "button",
             "decision_type": "skip"},
        ] * 10
        weights = build_calibrated_weights(reviews=reviews)
        assert ("llm", "button") not in weights
