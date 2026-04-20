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

from dd.classify_consensus import compute_consensus_v1, compute_consensus_v2


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
