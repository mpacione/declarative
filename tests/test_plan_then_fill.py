"""Tests for the v0.1.5 Week 2 A2 plan-then-fill orchestrator.

Covers ``dd.composition.plan``:
- ``validate_plan`` — plan-shape validator (pure).
- ``plan_diff`` — compare plan expectations vs fill output.
- ``plan_then_fill`` — two-stage Haiku orchestrator (mock client).

Feature flag: ``DD_ENABLE_PLAN_THEN_FILL=1`` gates the plan path;
default is no-op passthrough so A1 behaviour holds until 00h confirms
the uplift.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from dd.composition.plan import (
    PlanValidationError,
    plan_diff,
    plan_then_fill,
    validate_plan,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

VALID_PLAN = [
    {"type": "header", "id": "hdr", "children": [
        {"type": "icon_button", "id": "back"},
        {"type": "text", "id": "title"},
    ]},
    {"type": "list", "id": "feed", "children": [
        {"type": "card", "id": "card_tpl", "count_hint": 4},
    ]},
]


def _plan_response(tree) -> str:
    """Serialise a plan as Haiku would return it — bare JSON array."""
    return json.dumps(tree)


def _fill_response(components) -> str:
    return json.dumps(components)


def _mock_client(plan_text: str, fill_text: str) -> MagicMock:
    client = MagicMock()
    # plan call first, then fill
    plan_msg = MagicMock()
    plan_msg.content = [MagicMock(text=plan_text)]
    fill_msg = MagicMock()
    fill_msg.content = [MagicMock(text=fill_text)]
    client.messages.create.side_effect = [plan_msg, fill_msg]
    return client


# --------------------------------------------------------------------------- #
# validate_plan                                                               #
# --------------------------------------------------------------------------- #

class TestValidatePlan:
    def test_accepts_valid_plan(self):
        # Should not raise
        validate_plan(VALID_PLAN)

    def test_rejects_non_list(self):
        with pytest.raises(PlanValidationError):
            validate_plan({"type": "header"})

    def test_rejects_node_without_type(self):
        with pytest.raises(PlanValidationError, match="missing 'type'"):
            validate_plan([{"id": "hdr"}])

    def test_rejects_unknown_catalog_type(self):
        with pytest.raises(PlanValidationError, match="unknown type"):
            validate_plan([{"type": "holographic_widget", "id": "h"}])

    def test_rejects_node_without_id(self):
        with pytest.raises(PlanValidationError, match="missing 'id'"):
            validate_plan([{"type": "header"}])

    def test_rejects_duplicate_ids(self):
        plan = [
            {"type": "header", "id": "same"},
            {"type": "card", "id": "same"},
        ]
        with pytest.raises(PlanValidationError, match="duplicate id"):
            validate_plan(plan)

    def test_rejects_invalid_count_hint(self):
        plan = [{"type": "list", "id": "l", "children": [
            {"type": "card", "id": "c", "count_hint": 0},
        ]}]
        with pytest.raises(PlanValidationError, match="count_hint"):
            validate_plan(plan)

    def test_rejects_non_int_count_hint(self):
        plan = [{"type": "list", "id": "l", "children": [
            {"type": "card", "id": "c", "count_hint": "four"},
        ]}]
        with pytest.raises(PlanValidationError, match="count_hint"):
            validate_plan(plan)

    def test_allows_missing_count_hint(self):
        """Implicit count_hint=1 for non-repeated children."""
        plan = [{"type": "header", "id": "h", "children": [
            {"type": "text", "id": "title"},
        ]}]
        validate_plan(plan)  # no raise

    def test_allows_nested_containers(self):
        plan = [
            {"type": "drawer", "id": "d", "children": [
                {"type": "list", "id": "l", "children": [
                    {"type": "navigation_row", "id": "nav", "count_hint": 6},
                ]},
            ]},
        ]
        validate_plan(plan)

    # ──── Stage 0.1 — `frame` neutral wrapper in composition vocabulary ────

    def test_accepts_frame_as_neutral_wrapper(self):
        """Stage 0.1: `frame` is the neutral structural primitive the LLM
        can use for sections / containers / wrappers without flattening
        to `card`. It's a grammar TypeKeyword (spec §2.7) and must be a
        valid planner type so the planner can emit it without the
        validator rejecting it as 'unknown catalog type'."""
        plan = [{
            "type": "frame",
            "id": "product-showcase-section",
            "children": [
                {"type": "heading", "id": "section-title"},
                {"type": "card", "id": "feature-card", "count_hint": 3},
            ],
        }]
        validate_plan(plan)  # no raise


class TestPlannerSystemPrompt:
    """Stage 0.1 + 0.2 — shape checks on the planner's system prompt.

    These are contract tests on the prompt *string* — they fail when the
    LLM-visible vocabulary doesn't match what the validator accepts, or
    when the known-bad coercion rules regress."""

    @staticmethod
    def _planner_prompt() -> str:
        from dd.composition.plan import _build_plan_system
        return _build_plan_system()

    def test_advertises_frame_as_neutral_wrapper(self):
        assert "frame" in self._planner_prompt()

    def test_no_section_to_card_coercion(self):
        """Stage 0.2: delete `section / wrapper → card` coercion.
        Coercion rules harmed composition by forcing every designer-
        intuitive grouping onto `card` (Defect B)."""
        prompt = self._planner_prompt().lower()
        assert "section / wrapper" not in prompt
        assert "→ use `card`" not in prompt
        assert "use `card`" not in prompt or "wrapper" not in prompt.split("use `card`")[0].rsplit("\n", 1)[-1]

    def test_no_footer_to_card_coercion(self):
        assert "footer → use `card`" not in self._planner_prompt().lower()

    def test_no_carousel_to_list_of_card_coercion(self):
        assert "carousel" not in self._planner_prompt().lower() or (
            "use `list`" not in self._planner_prompt().lower()
        )

    def test_no_hero_to_card_coercion(self):
        prompt = self._planner_prompt().lower()
        # The specific line "a hero → use `card` with …" is the
        # fingerprint of the old coercion block.
        assert "a hero → use" not in prompt


class TestSystemPromptVocabulary:
    """Stage 0.1 — the top-level SYSTEM_PROMPT (used by the A1 single-
    call composition path) must also advertise `frame`. Otherwise the
    non-plan-then-fill path still lacks a neutral wrapper."""

    def test_system_prompt_advertises_frame(self):
        from dd.prompt_parser import SYSTEM_PROMPT
        assert "frame" in SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# Stage 0.3 — flat named-node plan contract                                   #
# --------------------------------------------------------------------------- #

class TestValidateFlatPlan:
    """Stage 0.3: new output contract is a flat table of named nodes
    addressed by parent_eid. Every node has an explicit eid; nesting
    relationships are explicit via parent_eid; LLM-intended order is
    explicit via ``order``. Downstream addressing (edit grammar,
    drift check, session log) relies on every node carrying its own
    eid from day one.
    """

    def test_accepts_flat_plan_with_root(self):
        from dd.composition.plan import validate_flat_plan
        plan = {"nodes": [
            {"eid": "hdr", "type": "header", "parent_eid": None, "order": 0},
            {"eid": "back", "type": "icon_button", "parent_eid": "hdr", "order": 0},
            {"eid": "title", "type": "text", "parent_eid": "hdr", "order": 1},
        ]}
        validate_flat_plan(plan)  # no raise

    def test_accepts_frame_as_neutral_wrapper(self):
        from dd.composition.plan import validate_flat_plan
        plan = {"nodes": [
            {"eid": "screen-root", "type": "frame", "parent_eid": None, "order": 0},
            {"eid": "product-showcase-section", "type": "frame", "parent_eid": "screen-root", "order": 1},
            {"eid": "section-title", "type": "heading", "parent_eid": "product-showcase-section", "order": 0},
            {"eid": "feature-card", "type": "card", "parent_eid": "product-showcase-section", "order": 1, "repeat": 3},
        ]}
        validate_flat_plan(plan)  # no raise

    def test_rejects_non_dict_root(self):
        from dd.composition.plan import PlanValidationError, validate_flat_plan
        with pytest.raises(PlanValidationError, match="object"):
            validate_flat_plan([{"eid": "x", "type": "card", "parent_eid": None, "order": 0}])

    def test_rejects_missing_nodes_key(self):
        from dd.composition.plan import PlanValidationError, validate_flat_plan
        with pytest.raises(PlanValidationError, match="'nodes'"):
            validate_flat_plan({"components": []})

    def test_rejects_missing_eid(self):
        from dd.composition.plan import PlanValidationError, validate_flat_plan
        with pytest.raises(PlanValidationError, match="missing 'eid'"):
            validate_flat_plan({"nodes": [
                {"type": "card", "parent_eid": None, "order": 0},
            ]})

    def test_rejects_missing_type(self):
        from dd.composition.plan import PlanValidationError, validate_flat_plan
        with pytest.raises(PlanValidationError, match="missing 'type'"):
            validate_flat_plan({"nodes": [
                {"eid": "x", "parent_eid": None, "order": 0},
            ]})

    def test_rejects_unknown_type(self):
        from dd.composition.plan import PlanValidationError, validate_flat_plan
        with pytest.raises(PlanValidationError, match="unknown type"):
            validate_flat_plan({"nodes": [
                {"eid": "x", "type": "holographic_widget", "parent_eid": None, "order": 0},
            ]})

    def test_rejects_duplicate_eids(self):
        from dd.composition.plan import PlanValidationError, validate_flat_plan
        with pytest.raises(PlanValidationError, match="duplicate"):
            validate_flat_plan({"nodes": [
                {"eid": "same", "type": "card", "parent_eid": None, "order": 0},
                {"eid": "same", "type": "card", "parent_eid": None, "order": 1},
            ]})

    def test_rejects_dangling_parent_eid(self):
        from dd.composition.plan import PlanValidationError, validate_flat_plan
        with pytest.raises(PlanValidationError, match="parent_eid"):
            validate_flat_plan({"nodes": [
                {"eid": "child", "type": "card", "parent_eid": "ghost", "order": 0},
            ]})

    def test_rejects_invalid_repeat(self):
        from dd.composition.plan import PlanValidationError, validate_flat_plan
        with pytest.raises(PlanValidationError, match="repeat"):
            validate_flat_plan({"nodes": [
                {"eid": "x", "type": "card", "parent_eid": None, "order": 0, "repeat": 0},
            ]})

    def test_rejects_non_int_order(self):
        from dd.composition.plan import PlanValidationError, validate_flat_plan
        with pytest.raises(PlanValidationError, match="order"):
            validate_flat_plan({"nodes": [
                {"eid": "x", "type": "card", "parent_eid": None, "order": "first"},
            ]})


class TestFlatPlanToTree:
    """Stage 0.3: flat-row plans convert to the tree shape that the
    fill prompt + compose_screen consume. ``repeat: N`` expands
    deterministically to ``eid__1``, ``eid__2`` ... siblings at the
    adapter layer so compose sees a concrete tree with no repeat
    semantics to interpret.
    """

    def test_single_root_produces_tree(self):
        from dd.composition.plan import flat_plan_to_tree
        plan = {"nodes": [
            {"eid": "hdr", "type": "header", "parent_eid": None, "order": 0},
        ]}
        tree = flat_plan_to_tree(plan)
        assert tree == [{"type": "header", "id": "hdr"}]

    def test_two_roots_preserve_order(self):
        from dd.composition.plan import flat_plan_to_tree
        plan = {"nodes": [
            {"eid": "second", "type": "card", "parent_eid": None, "order": 1},
            {"eid": "first", "type": "header", "parent_eid": None, "order": 0},
        ]}
        tree = flat_plan_to_tree(plan)
        assert [n["id"] for n in tree] == ["first", "second"]

    def test_nested_children_by_parent_eid(self):
        from dd.composition.plan import flat_plan_to_tree
        plan = {"nodes": [
            {"eid": "hdr", "type": "header", "parent_eid": None, "order": 0},
            {"eid": "title", "type": "text", "parent_eid": "hdr", "order": 0},
            {"eid": "back", "type": "icon_button", "parent_eid": "hdr", "order": 1},
        ]}
        tree = flat_plan_to_tree(plan)
        assert tree[0]["id"] == "hdr"
        # Preserve ORDER for children (first = title at order 0)
        assert [c["id"] for c in tree[0]["children"]] == ["title", "back"]

    def test_repeat_expands_to_numbered_siblings(self):
        from dd.composition.plan import flat_plan_to_tree
        plan = {"nodes": [
            {"eid": "section", "type": "frame", "parent_eid": None, "order": 0},
            {"eid": "feature-card", "type": "card", "parent_eid": "section", "order": 0, "repeat": 3},
        ]}
        tree = flat_plan_to_tree(plan)
        section = tree[0]
        assert [c["id"] for c in section["children"]] == [
            "feature-card__1", "feature-card__2", "feature-card__3",
        ]
        # Every expanded sibling carries the same TYPE
        assert {c["type"] for c in section["children"]} == {"card"}

    def test_repeat_one_emits_original_eid(self):
        """repeat=1 is the same as no repeat — the original eid is the
        only survivor."""
        from dd.composition.plan import flat_plan_to_tree
        plan = {"nodes": [
            {"eid": "parent", "type": "frame", "parent_eid": None, "order": 0},
            {"eid": "only-child", "type": "text", "parent_eid": "parent", "order": 0, "repeat": 1},
        ]}
        tree = flat_plan_to_tree(plan)
        assert tree[0]["children"][0]["id"] == "only-child"

    def test_multiple_parents_preserve_membership(self):
        from dd.composition.plan import flat_plan_to_tree
        plan = {"nodes": [
            {"eid": "a", "type": "frame", "parent_eid": None, "order": 0},
            {"eid": "b", "type": "frame", "parent_eid": None, "order": 1},
            {"eid": "a-child", "type": "text", "parent_eid": "a", "order": 0},
            {"eid": "b-child", "type": "text", "parent_eid": "b", "order": 0},
        ]}
        tree = flat_plan_to_tree(plan)
        a = next(n for n in tree if n["id"] == "a")
        b = next(n for n in tree if n["id"] == "b")
        assert [c["id"] for c in a["children"]] == ["a-child"]
        assert [c["id"] for c in b["children"]] == ["b-child"]


class TestFlatPlanSystemPrompt:
    """Stage 0.7: the new planner system prompt. Contract spelled out
    explicitly so the LLM can't drift into the old nested-tree shape
    without failing validation."""

    @staticmethod
    def _flat_prompt() -> str:
        from dd.composition.plan import _build_flat_plan_system
        return _build_flat_plan_system()

    def test_advertises_flat_nodes_array(self):
        prompt = self._flat_prompt()
        assert "nodes" in prompt
        assert "parent_eid" in prompt

    def test_advertises_eid_as_open_vocabulary(self):
        prompt = self._flat_prompt()
        # eid must appear; so must some phrasing that conveys it's
        # invented by the LLM (not an enum)
        assert "eid" in prompt

    def test_advertises_type_as_closed_vocabulary(self):
        prompt = self._flat_prompt()
        # Catalog types must be listed
        assert "frame" in prompt
        assert "card" in prompt

    def test_advertises_repeat(self):
        prompt = self._flat_prompt()
        assert "repeat" in prompt

    def test_no_nested_children_example(self):
        """The new prompt must NOT advertise the old `children` nested-
        array shape. Otherwise the LLM is free to drift back."""
        prompt = self._flat_prompt()
        # Specific fingerprint: the old example's `"children":` JSON
        # key. The new contract uses parent_eid, never nested children.
        assert '"children":' not in prompt


class TestPlanThenFillAcceptsFlatShape:
    """Stage 0.3/0.7 orchestrator acceptance: plan_then_fill now
    drives the flat-plan contract by default. The planner LLM is
    asked for a flat `{"nodes": [...]}` response; plan_then_fill
    adapts that to the tree form for the fill prompt + downstream
    compose.
    """

    def test_plan_then_fill_routes_flat_plan_through_adapter(self):
        flat_plan = {"nodes": [
            {"eid": "hdr", "type": "header", "parent_eid": None, "order": 0},
            {"eid": "feed", "type": "list", "parent_eid": None, "order": 1},
            {"eid": "post", "type": "card", "parent_eid": "feed", "order": 0, "repeat": 4},
        ]}
        fill_components = [
            {"type": "header", "children": [{"type": "text"}]},
            {"type": "list", "children": [
                {"type": "card"}, {"type": "card"},
                {"type": "card"}, {"type": "card"},
            ]},
        ]
        client = _mock_client(
            _plan_response(flat_plan),
            _fill_response(fill_components),
        )
        result = plan_then_fill("a home feed", client)
        assert result.get("components") == fill_components
        # The adapter exposes the ORIGINAL flat plan so downstream
        # drift check can compare against the LLM's own intent.
        assert result.get("plan") == flat_plan

    def test_plan_then_fill_still_accepts_legacy_tree_shape(self):
        """Legacy nested-tree plans stay working — Stage 0 is Option C
        (narrow, backwards-compat). Stage 1 will delete this path."""
        legacy_plan = [
            {"type": "header", "id": "hdr", "children": [
                {"type": "text", "id": "title"},
            ]},
        ]
        fill_components = [{"type": "header", "children": [{"type": "text"}]}]
        client = _mock_client(
            _plan_response(legacy_plan),
            _fill_response(fill_components),
        )
        result = plan_then_fill("anything", client)
        assert result.get("components") == fill_components
        assert result.get("plan") == legacy_plan


# --------------------------------------------------------------------------- #
# plan_diff                                                                   #
# --------------------------------------------------------------------------- #

class TestPlanDiff:
    def test_no_diff_when_fill_matches_plan(self):
        fill = [
            {"type": "header", "children": [
                {"type": "icon_button"},
                {"type": "text", "props": {"text": "Feed"}},
            ]},
            {"type": "list", "children": [
                {"type": "card"},
                {"type": "card"},
                {"type": "card"},
                {"type": "card"},
            ]},
        ]
        diff = plan_diff(VALID_PLAN, fill)
        assert diff.has_drift is False

    def test_detects_missing_top_level_node(self):
        fill = [
            # header missing entirely
            {"type": "list", "children": [{"type": "card"}] * 4},
        ]
        diff = plan_diff(VALID_PLAN, fill)
        assert diff.has_drift is True
        assert any("header" in m for m in diff.missing_types)

    def test_detects_undercount_on_count_hint(self):
        fill = [
            {"type": "header", "children": [
                {"type": "icon_button"},
                {"type": "text"},
            ]},
            {"type": "list", "children": [
                {"type": "card"},
                {"type": "card"},
                # Only 2 instead of 4
            ]},
        ]
        diff = plan_diff(VALID_PLAN, fill)
        assert diff.has_drift is True
        # Expected 4 cards, got 2 — shortfall of 2
        assert any(
            "card" in msg and "2" in msg
            for msg in diff.undercount
        )

    def test_no_drift_when_fill_exceeds_count_hint(self):
        """Overshooting count_hint is fine — LLM emitted more than the
        minimum. We only flag undercounts."""
        fill = [
            {"type": "header", "children": [
                {"type": "icon_button"},
                {"type": "text"},
            ]},
            {"type": "list", "children": [{"type": "card"}] * 6},
        ]
        diff = plan_diff(VALID_PLAN, fill)
        assert diff.has_drift is False

    def test_ignores_extra_leaf_nodes(self):
        """Fill adding extra leaves in a container is not drift."""
        fill = [
            {"type": "header", "children": [
                {"type": "icon_button"},
                {"type": "text"},
                {"type": "icon_button"},  # extra trailing button
            ]},
            {"type": "list", "children": [{"type": "card"}] * 4},
        ]
        diff = plan_diff(VALID_PLAN, fill)
        assert diff.has_drift is False


# --------------------------------------------------------------------------- #
# plan_then_fill                                                              #
# --------------------------------------------------------------------------- #

class TestPlanThenFillOrchestrator:
    def test_calls_plan_then_fill_in_order(self):
        fill_components = [
            {"type": "header", "children": [
                {"type": "icon_button"},
                {"type": "text", "props": {"text": "Home"}},
            ]},
            {"type": "list", "children": [{"type": "card"}] * 4},
        ]
        client = _mock_client(
            _plan_response(VALID_PLAN),
            _fill_response(fill_components),
        )
        result = plan_then_fill("a home feed", client)
        assert client.messages.create.call_count == 2
        assert result["components"] == fill_components
        assert result["plan"] == VALID_PLAN

    def test_retries_on_plan_diff(self):
        """When the fill undercounts the plan, one retry fires with the
        pinned plan restated. The retry's output is the final result."""
        bad_fill = [
            {"type": "header", "children": [
                {"type": "icon_button"},
                {"type": "text"},
            ]},
            {"type": "list", "children": [{"type": "card"}] * 2},  # undercount
        ]
        good_fill = [
            {"type": "header", "children": [
                {"type": "icon_button"},
                {"type": "text"},
            ]},
            {"type": "list", "children": [{"type": "card"}] * 4},
        ]
        client = MagicMock()
        # plan, fill1 (bad), fill2 (good)
        for text in [_plan_response(VALID_PLAN),
                     _fill_response(bad_fill),
                     _fill_response(good_fill)]:
            pass
        client.messages.create.side_effect = [
            MagicMock(content=[MagicMock(text=_plan_response(VALID_PLAN))]),
            MagicMock(content=[MagicMock(text=_fill_response(bad_fill))]),
            MagicMock(content=[MagicMock(text=_fill_response(good_fill))]),
        ]
        result = plan_then_fill("a home feed", client)
        assert client.messages.create.call_count == 3
        assert result["components"] == good_fill
        assert result["retried"] is True

    def test_invalid_plan_raises_structured_error(self):
        """Plan validation failure produces ``KIND_PLAN_INVALID``, not
        a silent error."""
        client = _mock_client(
            _plan_response([{"type": "holographic_widget", "id": "h"}]),
            _fill_response([]),
        )
        result = plan_then_fill("a home feed", client)
        assert result.get("kind") == "KIND_PLAN_INVALID"
        # Fill should NOT have been called
        assert client.messages.create.call_count == 1

    def test_fill_drift_twice_surfaces_plan_invalid(self):
        """If both fills undercount, surface KIND_PLAN_INVALID — do
        not keep retrying."""
        bad_fill = [
            {"type": "list", "children": [{"type": "card"}] * 1},
        ]
        tiny_plan = [
            {"type": "list", "id": "l", "children": [
                {"type": "card", "id": "c", "count_hint": 4},
            ]},
        ]
        client = MagicMock()
        client.messages.create.side_effect = [
            MagicMock(content=[MagicMock(text=_plan_response(tiny_plan))]),
            MagicMock(content=[MagicMock(text=_fill_response(bad_fill))]),
            MagicMock(content=[MagicMock(text=_fill_response(bad_fill))]),
        ]
        result = plan_then_fill("a tight list", client)
        assert result.get("kind") == "KIND_PLAN_INVALID"
        # Should have tried plan + 2 fills, then given up.
        assert client.messages.create.call_count == 3

    def test_empty_prompt_returns_empty(self):
        client = MagicMock()
        result = plan_then_fill("", client)
        assert result["components"] == []
        client.messages.create.assert_not_called()

    def test_plan_clarification_refusal_preserved(self):
        """If the PLAN LLM returns a clarification-refusal prose (≥100
        chars of non-JSON), surface it via the same
        ``_clarification_refusal`` contract as the A1 path."""
        client = MagicMock()
        refusal = (
            "I don't have enough context to plan this screen. "
            "Could you describe the specific UI elements you want?"
        )
        client.messages.create.side_effect = [
            MagicMock(content=[MagicMock(text=refusal)]),
        ]
        result = plan_then_fill("build something", client)
        assert "_clarification_refusal" in result
        # Fill not called
        assert client.messages.create.call_count == 1
