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
