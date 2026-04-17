"""Tests for the v0.1.5 matrix SYSTEM_PROMPT contract variants.

Covers ``dd.composition.matrix_contracts.build_contract_prompt``, which
builds the 5 SYSTEM_PROMPT variants (S0/S1/S2/S3/S4) described in the
density-design memo §3.1.

Invariants shared across every variant:
- catalog type list is present (the LLM must know what to emit)
- the user-prompt vocabulary is project-specific, never baked in here

Per-variant:
- S0 — current SYSTEM_PROMPT + archetype + vocab (baseline)
- S1 — adds the <plan> preamble
- S2 — adds min-count + clarify-as-empty instruction
- S3 — adds three worked examples
- S4 — minimal control: catalog types only, no hints, no vocab
"""

from __future__ import annotations

import pytest

from dd.composition.matrix_contracts import (
    CONTRACT_IDS,
    build_contract_prompt,
)

FIXTURE_ARCHETYPE = (
    "Common screen archetypes in this project:\n"
    "- login: header + text_input x2 + button\n"
)
FIXTURE_VOCAB = (
    "This project has these specific component variants:\n"
    "  button: primary (42 instances), secondary (12 instances)\n"
)


# --------------------------------------------------------------------------- #
# Contract registry                                                           #
# --------------------------------------------------------------------------- #

class TestContractIds:
    def test_five_variants_exist(self):
        assert CONTRACT_IDS == ("S0", "S1", "S2", "S3", "S4")


# --------------------------------------------------------------------------- #
# S0 — baseline                                                               #
# --------------------------------------------------------------------------- #

class TestS0Baseline:
    def test_s0_includes_catalog_types(self):
        p = build_contract_prompt("S0", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "button_group" in p
        assert "text_input" in p

    def test_s0_includes_container_hints(self):
        p = build_contract_prompt("S0", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "Container types" in p

    def test_s0_includes_archetype_and_vocab(self):
        p = build_contract_prompt("S0", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "login: header" in p
        assert "button: primary" in p

    def test_s0_does_not_include_s1_plan_preamble(self):
        p = build_contract_prompt("S0", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "<plan>" not in p


# --------------------------------------------------------------------------- #
# S1 — plan-first                                                             #
# --------------------------------------------------------------------------- #

class TestS1PlanFirst:
    def test_s1_includes_plan_tag_instruction(self):
        p = build_contract_prompt("S1", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "<plan>" in p
        assert "</plan>" in p

    def test_s1_keeps_s0_baseline_content(self):
        p = build_contract_prompt("S1", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "Container types" in p
        assert "login: header" in p


# --------------------------------------------------------------------------- #
# S2 — min-count + clarify-as-empty                                           #
# --------------------------------------------------------------------------- #

class TestS2MinCountClarify:
    def test_s2_includes_min_children_instruction(self):
        p = build_contract_prompt("S2", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "at least 4" in p

    def test_s2_includes_do_not_invent(self):
        p = build_contract_prompt("S2", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "do NOT invent" in p or "DO NOT invent" in p

    def test_s2_keeps_s0_baseline_content(self):
        p = build_contract_prompt("S2", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "Container types" in p
        assert "button: primary" in p


# --------------------------------------------------------------------------- #
# S3 — few-shot rich                                                          #
# --------------------------------------------------------------------------- #

class TestS3FewShot:
    def test_s3_includes_three_worked_examples(self):
        p = build_contract_prompt("S3", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        # Three distinct example headers; case-insensitive for safety.
        lower = p.lower()
        assert lower.count("example ") >= 3 or lower.count("### example") >= 3

    def test_s3_examples_cover_dashboard_feed_carousel(self):
        """Memo §3.1: examples are dashboard / meme-feed / onboarding-
        carousel — the three prompts whose 00e/f outputs actually looked
        right."""
        p = build_contract_prompt("S3", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB).lower()
        assert "dashboard" in p
        assert "feed" in p
        assert "onboarding" in p or "carousel" in p

    def test_s3_keeps_s0_baseline_content(self):
        p = build_contract_prompt("S3", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "Container types" in p


# --------------------------------------------------------------------------- #
# S4 — minimal control                                                        #
# --------------------------------------------------------------------------- #

class TestS4Minimal:
    def test_s4_still_lists_catalog_types(self):
        p = build_contract_prompt("S4", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "button" in p
        assert "text_input" in p

    def test_s4_has_no_container_hints(self):
        p = build_contract_prompt("S4", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "Container types" not in p

    def test_s4_has_no_archetype_or_vocab(self):
        """S4 is the control: measures what the current enriched
        contract is actually buying on top of the bare catalog."""
        p = build_contract_prompt("S4", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "login: header" not in p
        assert "button: primary" not in p

    def test_s4_output_format_still_requested(self):
        p = build_contract_prompt("S4", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "JSON array" in p


# --------------------------------------------------------------------------- #
# Cross-cutting                                                               #
# --------------------------------------------------------------------------- #

class TestCrossCutting:
    @pytest.mark.parametrize("cid", ["S0", "S1", "S2", "S3", "S4"])
    def test_every_variant_lists_catalog_types(self, cid):
        """All five variants must surface the catalog types — the whole
        matrix is invalid if the LLM doesn't know what it can emit."""
        p = build_contract_prompt(cid, archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)
        assert "button" in p
        assert "text" in p

    def test_unknown_variant_raises(self):
        with pytest.raises(ValueError):
            build_contract_prompt("S5", archetype=FIXTURE_ARCHETYPE, vocab=FIXTURE_VOCAB)

    def test_empty_archetype_and_vocab_is_allowed(self):
        """A fresh project may not have either; the contracts still build."""
        p = build_contract_prompt("S0", archetype="", vocab="")
        assert "button" in p
