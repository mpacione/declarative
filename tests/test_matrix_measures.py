"""Tests for the v0.1.5 matrix runner structural measures.

Covers ``dd.composition.matrix_measures.compute_measures``, the pure
function the 00g-matrix driver uses to reduce one Haiku response to
eight structural dependent variables per the density-design memo §3.2.
"""

from __future__ import annotations

import json

import pytest

from dd.composition.matrix_measures import (
    CONTAINER_TYPES,
    MatrixMeasures,
    compute_measures,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

def _raw_json(components: list[dict]) -> str:
    """Serialize a component list the way Haiku would return it."""
    return json.dumps(components)


EMPTY_RESPONSE = "[]"

LOGIN_COMPONENTS = [
    {"type": "header", "props": {"text": "Login"}},
    {"type": "text_input", "props": {"label": "Email"}},
    {"type": "text_input", "props": {"label": "Password"}},
    {"type": "button", "variant": "primary", "props": {"text": "Sign in"}},
]

DEEP_NESTED = [
    {"type": "header", "props": {"text": "Feed"}, "children": [
        {"type": "icon", "component_key": "icon/back"},
    ]},
    {"type": "list", "children": [
        {"type": "list_item", "children": [
            {"type": "text", "props": {"text": "Item 1"}},
            {"type": "button_group", "children": [
                {"type": "button", "props": {"text": "A"}},
                {"type": "button", "props": {"text": "B"}},
            ]},
        ]},
        {"type": "list_item", "children": [
            {"type": "text", "props": {"text": "Item 2"}},
        ]},
    ]},
]


# --------------------------------------------------------------------------- #
# compute_measures — happy paths                                              #
# --------------------------------------------------------------------------- #

class TestCounts:
    def test_total_node_count_counts_all_nodes_in_tree(self):
        m = compute_measures(_raw_json(DEEP_NESTED), DEEP_NESTED)
        # header + icon + list + list_item1 + text + button_group + 2 buttons + list_item2 + text = 10
        assert m.total_node_count == 10

    def test_top_level_count_is_array_length(self):
        m = compute_measures(_raw_json(LOGIN_COMPONENTS), LOGIN_COMPONENTS)
        assert m.top_level_count == 4

    def test_max_depth_counts_deepest_nesting(self):
        # header -> icon = depth 2. list -> list_item -> button_group -> button = depth 4.
        m = compute_measures(_raw_json(DEEP_NESTED), DEEP_NESTED)
        assert m.max_depth == 4

    def test_max_depth_flat_list_is_one(self):
        m = compute_measures(_raw_json(LOGIN_COMPONENTS), LOGIN_COMPONENTS)
        assert m.max_depth == 1

    def test_empty_list_counts_are_zero(self):
        m = compute_measures(EMPTY_RESPONSE, [])
        assert m.total_node_count == 0
        assert m.top_level_count == 0
        assert m.max_depth == 0


class TestContainerCoverage:
    def test_container_set_matches_density_memo(self):
        # Density memo §3.2 measure 4: list, button_group, pagination,
        # toggle_group, header, table.
        assert set(CONTAINER_TYPES) == {
            "list", "button_group", "pagination",
            "toggle_group", "header", "table",
        }

    def test_container_coverage_counts_distinct_emitted_containers(self):
        components = [
            {"type": "header", "children": [{"type": "text", "props": {"text": "H"}}]},
            {"type": "list", "children": [{"type": "list_item", "children": [
                {"type": "text", "props": {"text": "x"}},
            ]}]},
            {"type": "button_group", "children": [
                {"type": "button", "props": {"text": "a"}},
            ]},
        ]
        m = compute_measures(_raw_json(components), components)
        assert m.container_coverage == 3

    def test_empty_container_does_not_count(self):
        """Per memo: 'did we emit with non-empty children?'"""
        components = [
            {"type": "list", "children": []},
            {"type": "header"},
        ]
        m = compute_measures(_raw_json(components), components)
        assert m.container_coverage == 0

    def test_container_coverage_deduplicates_same_type(self):
        """Score is 0-6 (one per container type), not a raw count."""
        components = [
            {"type": "header", "children": [{"type": "text", "props": {"text": "H"}}]},
            {"type": "list", "children": [
                {"type": "list_item", "children": [
                    {"type": "text", "props": {"text": "a"}},
                ]},
            ]},
            {"type": "list", "children": [
                {"type": "list_item", "children": [
                    {"type": "text", "props": {"text": "b"}},
                ]},
            ]},
        ]
        m = compute_measures(_raw_json(components), components)
        # 2 distinct container types emitted (header, list), not 3
        assert m.container_coverage == 2

    def test_nested_container_counts(self):
        """button_group nested inside list_item should still be detected."""
        m = compute_measures(_raw_json(DEEP_NESTED), DEEP_NESTED)
        # header (non-empty), list, button_group = 3
        assert m.container_coverage == 3


class TestRates:
    def test_component_key_rate_counts_nodes_with_key(self):
        components = [
            {"type": "icon", "component_key": "icon/back"},
            {"type": "icon", "component_key": "icon/close"},
            {"type": "text", "props": {"text": "hi"}},
        ]
        m = compute_measures(_raw_json(components), components)
        assert m.component_key_rate == pytest.approx(2 / 3)

    def test_variant_rate_counts_nodes_with_variant(self):
        components = [
            {"type": "button", "variant": "primary"},
            {"type": "button", "variant": "secondary"},
            {"type": "text", "props": {"text": "hi"}},
            {"type": "icon"},
        ]
        m = compute_measures(_raw_json(components), components)
        assert m.variant_rate == pytest.approx(2 / 4)

    def test_rates_zero_when_empty(self):
        m = compute_measures(EMPTY_RESPONSE, [])
        assert m.component_key_rate == 0.0
        assert m.variant_rate == 0.0


# --------------------------------------------------------------------------- #
# JSON validity + empty/clarification-refusal                                 #
# --------------------------------------------------------------------------- #

class TestJsonValidity:
    def test_valid_json_array_is_valid(self):
        m = compute_measures('[{"type": "button"}]', [{"type": "button"}])
        assert m.json_valid == 1

    def test_markdown_wrapped_json_is_valid(self):
        raw = '```json\n[{"type": "button"}]\n```'
        m = compute_measures(raw, [{"type": "button"}])
        assert m.json_valid == 1

    def test_empty_array_is_valid(self):
        m = compute_measures("[]", [])
        assert m.json_valid == 1

    def test_prose_is_invalid(self):
        raw = (
            "I don't have a reference image or description of "
            "'iPhone 13 Pro Max - 109'. Could you share a screenshot?"
        )
        m = compute_measures(raw, {"_clarification_refusal": raw.strip()})
        assert m.json_valid == 0

    def test_short_noise_is_invalid(self):
        m = compute_measures("oops", [])
        assert m.json_valid == 0


class TestRefusalAndEmpty:
    def test_empty_output_flag_on_empty_array(self):
        m = compute_measures("[]", [])
        assert m.empty_output == 1
        assert m.clarification_refusal == 0

    def test_clarification_refusal_flag(self):
        """Clarification refusal is categorically better than an empty
        array; the memo §Week 1 notes it is NOT counted as empty-output."""
        prose = (
            "I don't have a reference image for 'iPhone 13 Pro Max - 109'."
            " Could you describe the screen?"
        )
        result = {"_clarification_refusal": prose}
        m = compute_measures(prose, result)
        assert m.clarification_refusal == 1
        assert m.empty_output == 0

    def test_populated_output_neither_empty_nor_refusal(self):
        m = compute_measures(_raw_json(LOGIN_COMPONENTS), LOGIN_COMPONENTS)
        assert m.empty_output == 0
        assert m.clarification_refusal == 0


class TestSerialization:
    def test_to_dict_includes_all_measures(self):
        m = compute_measures(_raw_json(LOGIN_COMPONENTS), LOGIN_COMPONENTS)
        d = m.to_dict()
        assert set(d.keys()) == {
            "total_node_count",
            "top_level_count",
            "max_depth",
            "container_coverage",
            "component_key_rate",
            "variant_rate",
            "json_valid",
            "empty_output",
            "clarification_refusal",
        }
