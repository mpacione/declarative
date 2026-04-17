"""Tests for Mode 3 dual fidelity scorer.

Covers ``dd.diagnostics.fidelity``:

- **render fidelity**: for each IR element of a type with a
  PresentationTemplate, what fraction of the template's declared
  visual properties (fill / stroke / radius / shadow / padding) were
  emitted on the node in the generated Figma script?

- **prompt fidelity**: for each classified archetype, what fraction
  of the skeleton's node-type bag is present in the LLM's component
  list?

Both return 0.0-1.0 per element / per prompt, with aggregates.
"""

from __future__ import annotations

import pytest

from dd.diagnostics.fidelity import (
    expected_visual_props_for_type,
    prompt_fidelity,
    render_fidelity_from_script,
    type_bag,
)


# --------------------------------------------------------------------------- #
# expected_visual_props_for_type                                              #
# --------------------------------------------------------------------------- #

class TestExpectedVisualProps:
    def test_card_expects_fill_stroke_radius(self):
        props = expected_visual_props_for_type("card")
        assert "fill" in props
        assert "stroke" in props
        assert "radius" in props

    def test_card_expects_padding(self):
        props = expected_visual_props_for_type("card")
        assert "padding" in props

    def test_button_expects_fill_and_padding(self):
        """Button template has fill + padding."""
        props = expected_visual_props_for_type("button")
        assert "fill" in props
        assert "padding" in props

    def test_unknown_type_returns_empty(self):
        assert expected_visual_props_for_type("holographic_widget") == set()

    def test_text_expects_no_visual_frame_props(self):
        """TEXT nodes shouldn't expect fill/stroke/radius — those are
        frame properties. Text gets fg (fill color for characters)."""
        props = expected_visual_props_for_type("text")
        # Text shouldn't require a container fill/stroke/radius
        assert "radius" not in props
        assert "stroke" not in props


# --------------------------------------------------------------------------- #
# render_fidelity_from_script                                                 #
# --------------------------------------------------------------------------- #

SCRIPT_CARD_WITH_ALL = """
const n2 = figma.createFrame();
n2.name = "card-1";
n2.resize(400, 200);
n2.fills = [{type: "SOLID", color: {r:1,g:1,b:1}}];
n2.strokes = [{type: "SOLID", color: {r:0.8,g:0.8,b:0.8}}];
n2.cornerRadius = 12;
n2.paddingTop = 16;
n2.paddingBottom = 16;
n2.paddingLeft = 16;
n2.paddingRight = 16;
n2.effects = [{type: "DROP_SHADOW", radius: 4}];
M["card-1"] = n2.id;
"""

SCRIPT_CARD_EMPTY = """
const n3 = figma.createFrame();
n3.name = "card-2";
n3.fills = [];
n3.clipsContent = false;
M["card-2"] = n3.id;
"""


class TestRenderFidelityFromScript:
    def test_card_with_all_properties_is_1_0(self):
        ir = {"elements": {"card-1": {"type": "card"}}}
        score = render_fidelity_from_script(ir, SCRIPT_CARD_WITH_ALL)
        per_type = score.by_type
        assert per_type["card"]["coverage"] == pytest.approx(1.0)

    def test_empty_card_is_0(self):
        """card-2 has fills=[] (empty list counts as no fill) and no
        stroke / radius / padding / shadow — coverage 0."""
        ir = {"elements": {"card-2": {"type": "card"}}}
        score = render_fidelity_from_script(ir, SCRIPT_CARD_EMPTY)
        per_type = score.by_type
        assert per_type["card"]["coverage"] == pytest.approx(0.0)

    def test_partial_card(self):
        """Card with fill + radius, missing stroke, padding, shadow."""
        script = """
const n4 = figma.createFrame();
n4.name = "card-3";
n4.fills = [{type: "SOLID", color: {r:1,g:1,b:1}}];
n4.cornerRadius = 12;
M["card-3"] = n4.id;
"""
        ir = {"elements": {"card-3": {"type": "card"}}}
        score = render_fidelity_from_script(ir, script)
        coverage = score.by_type["card"]["coverage"]
        # 2 of 5 expected props → 0.4
        assert 0.3 < coverage < 0.6

    def test_aggregate_across_multiple_types(self):
        ir = {"elements": {
            "card-1": {"type": "card"},
            "card-2": {"type": "card"},
        }}
        combined = SCRIPT_CARD_WITH_ALL + SCRIPT_CARD_EMPTY
        score = render_fidelity_from_script(ir, combined)
        # aggregate should be between 0 (empty) and 1 (full)
        assert 0 < score.overall < 1
        # card type has 2 elements: 1 at 1.0 and 1 at 0.0 = mean 0.5
        assert score.by_type["card"]["coverage"] == pytest.approx(0.5)
        assert score.by_type["card"]["n_elements"] == 2

    def test_ignores_types_without_templates(self):
        """Unknown types in IR don't affect the score."""
        ir = {"elements": {
            "card-1": {"type": "card"},
            "weird-1": {"type": "holographic_widget"},
        }}
        score = render_fidelity_from_script(ir, SCRIPT_CARD_WITH_ALL)
        # only card is scored; holographic_widget has no template
        assert "card" in score.by_type
        assert "holographic_widget" not in score.by_type


# --------------------------------------------------------------------------- #
# prompt_fidelity                                                             #
# --------------------------------------------------------------------------- #

DASHBOARD_SKELETON = [
    {"type": "header", "children": [
        {"type": "text"}, {"type": "icon_button"},
    ]},
    {"type": "tabs", "children": [
        {"type": "text"}, {"type": "text"}, {"type": "text"},
    ]},
    {"type": "card", "children": [
        {"type": "heading"}, {"type": "text"}, {"type": "image"},
    ]},
    {"type": "card", "children": [
        {"type": "heading"},
        {"type": "table", "children": [
            {"type": "text"}, {"type": "text"},
            {"type": "list_item"}, {"type": "list_item"}, {"type": "list_item"},
        ]},
    ]},
]


class TestPromptFidelity:
    def test_identical_output_is_1_0(self):
        score = prompt_fidelity(DASHBOARD_SKELETON, DASHBOARD_SKELETON)
        assert score == pytest.approx(1.0)

    def test_missing_types_reduces_score(self):
        """LLM dropped the image node from a card."""
        broken = [
            {"type": "header", "children": [{"type": "text"}, {"type": "icon_button"}]},
            {"type": "tabs", "children": [{"type": "text"}, {"type": "text"}, {"type": "text"}]},
            {"type": "card", "children": [
                {"type": "heading"}, {"type": "text"},  # missing image
            ]},
            {"type": "card", "children": [
                {"type": "heading"},
                {"type": "table", "children": [
                    {"type": "text"}, {"type": "text"},
                    {"type": "list_item"}, {"type": "list_item"}, {"type": "list_item"},
                ]},
            ]},
        ]
        score = prompt_fidelity(DASHBOARD_SKELETON, broken)
        assert 0.8 < score < 1.0

    def test_empty_output_is_0(self):
        assert prompt_fidelity(DASHBOARD_SKELETON, []) == pytest.approx(0.0)

    def test_extra_types_do_not_boost_above_1(self):
        """LLM added random extra types; coverage stays bounded at 1.0."""
        fat = DASHBOARD_SKELETON + [
            {"type": "button"}, {"type": "avatar"}, {"type": "link"},
        ]
        assert prompt_fidelity(DASHBOARD_SKELETON, fat) == pytest.approx(1.0)

    def test_none_skeleton_returns_1_0(self):
        """If classifier returned no archetype, prompt fidelity isn't
        defined — return 1.0 (nothing expected, can't fail)."""
        assert prompt_fidelity(None, [{"type": "text"}]) == pytest.approx(1.0)


class TestTypeBag:
    def test_flattens_tree_into_counter(self):
        bag = type_bag([
            {"type": "card", "children": [
                {"type": "text"}, {"type": "text"}, {"type": "button"},
            ]},
        ])
        assert bag["card"] == 1
        assert bag["text"] == 2
        assert bag["button"] == 1

    def test_empty_input(self):
        assert type_bag([]) == {}
