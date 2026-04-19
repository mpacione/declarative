"""Tests for LLM classification (T5 Phase 1b, Step 3).

M7.0.a rewrote `classify_llm` to use Claude tool-use for structured
output and a richer prompt (catalog with behavioral descriptions,
parent/sibling context, CKR-registered master name). Tests here
exercise both the new shape and the preserved legacy text-parse
entry point.
"""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dd.catalog import seed_catalog
from dd.classify_llm import (
    CLASSIFY_TOOL_SCHEMA,
    _extract_classifications_from_response,
    build_classification_prompt,
    classify_llm,
    parse_classification_response,
)
from dd.db import init_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_unclassified_node(
    node_id: int = 1,
    name: str = "artboard",
    width: float = 428,
    height: float = 800,
    layout_mode: str | None = "VERTICAL",
    total_children: int = 3,
    parent_classified_as: str | None = None,
    sample_text: str | None = None,
    ckr_registered_name: str | None = None,
) -> dict:
    return {
        "node_id": node_id,
        "name": name,
        "node_type": "FRAME",
        "depth": 1,
        "width": width,
        "height": height,
        "layout_mode": layout_mode,
        "total_children": total_children,
        "child_type_dist": {"FRAME": total_children} if total_children else {},
        "sample_text": sample_text,
        "parent_classified_as": parent_classified_as,
        "component_key": None,
        "ckr_registered_name": ckr_registered_name,
        "y": 56,
    }


def _make_catalog() -> list[dict]:
    """Seed a tiny catalog (matching the production shape) for prompt tests."""
    return [
        {"id": 1, "canonical_name": "button", "category": "actions",
         "behavioral_description": "Primary interactive control that triggers an action."},
        {"id": 2, "canonical_name": "card", "category": "content_and_display",
         "behavioral_description": "A bounded container grouping related content."},
        {"id": 3, "canonical_name": "header", "category": "navigation",
         "behavioral_description": "Top bar with title and actions."},
        {"id": 4, "canonical_name": "dialog", "category": "containment_and_overlay",
         "behavioral_description": "Focused overlay requiring user attention."},
    ]


def _mock_tool_response(classifications: list[dict]) -> SimpleNamespace:
    """Build a mock Claude response carrying a tool_use content block."""
    tool_block = SimpleNamespace(
        type="tool_use",
        name="classify_nodes",
        input={"classifications": classifications},
    )
    return SimpleNamespace(content=[tool_block])


def _make_mock_client(classifications: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.messages.create.return_value = _mock_tool_response(classifications)
    return mock


# ---------------------------------------------------------------------------
# Prompt builder tests
# ---------------------------------------------------------------------------

class TestBuildClassificationPrompt:
    """Verify the prompt covers the canonical vocabulary, the node
    descriptions, the confidence-calibration rule, and the
    tool-invocation instruction.
    """

    def test_includes_canonical_types_with_descriptions(self):
        prompt = build_classification_prompt(
            nodes=[_make_unclassified_node(name="artboard")],
            catalog=_make_catalog(),
            screen_name="Home", screen_width=428, screen_height=926,
        )
        assert "button" in prompt
        assert "card" in prompt
        assert "header" in prompt
        # behavioral_description must appear so the LLM can
        # disambiguate visually-similar types.
        assert "Primary interactive control" in prompt

    def test_includes_container_and_unsure_options(self):
        prompt = build_classification_prompt(
            nodes=[_make_unclassified_node()], catalog=_make_catalog(),
            screen_name="X", screen_width=400, screen_height=800,
        )
        assert "`container`" in prompt
        assert "`unsure`" in prompt

    def test_includes_node_description(self):
        prompt = build_classification_prompt(
            nodes=[_make_unclassified_node(
                name="artboard", width=428, height=800,
                layout_mode="VERTICAL", total_children=5,
            )],
            catalog=_make_catalog(),
            screen_name="Home", screen_width=428, screen_height=926,
        )
        assert "artboard" in prompt
        assert "428" in prompt
        assert "VERTICAL" in prompt

    def test_includes_screen_context(self):
        prompt = build_classification_prompt(
            nodes=[_make_unclassified_node()],
            catalog=_make_catalog(),
            screen_name="Login Screen", screen_width=375, screen_height=812,
            skeleton_notation="stack(header, content, footer)",
            skeleton_type="settings",
        )
        assert "Login Screen" in prompt
        assert "stack(header, content, footer)" in prompt
        assert "settings" in prompt

    def test_handles_multiple_nodes(self):
        prompt = build_classification_prompt(
            nodes=[
                _make_unclassified_node(name="artboard", node_id=1),
                _make_unclassified_node(name="Overlay", node_id=2),
            ],
            catalog=_make_catalog(),
            screen_name="X", screen_width=400, screen_height=800,
        )
        assert "artboard" in prompt
        assert "Overlay" in prompt

    def test_surfaces_parent_classification_and_sample_text(self):
        prompt = build_classification_prompt(
            nodes=[_make_unclassified_node(
                parent_classified_as="header",
                sample_text="Sign in",
            )],
            catalog=_make_catalog(),
            screen_name="X", screen_width=400, screen_height=800,
        )
        assert "parent=header" in prompt
        assert 'sample_text="Sign in"' in prompt

    def test_requests_tool_invocation(self):
        prompt = build_classification_prompt(
            nodes=[_make_unclassified_node()],
            catalog=_make_catalog(),
            screen_name="X", screen_width=400, screen_height=800,
        )
        # Tool-use path: prompt directs the LLM to invoke the tool,
        # never to emit free text.
        assert "classify_nodes" in prompt


# ---------------------------------------------------------------------------
# Tool-use response extraction
# ---------------------------------------------------------------------------

class TestExtractClassificationsFromResponse:
    def test_extracts_tool_use_classifications(self):
        response = _mock_tool_response([
            {"node_id": 1, "canonical_type": "card",
             "confidence": 0.85, "reason": "Vertical auto-layout with heading + image + actions"},
        ])
        results = _extract_classifications_from_response(response)
        assert len(results) == 1
        assert results[0]["canonical_type"] == "card"

    def test_returns_empty_when_no_tool_use_block(self):
        response = SimpleNamespace(content=[
            SimpleNamespace(type="text", text="I don't know"),
        ])
        assert _extract_classifications_from_response(response) == []

    def test_returns_empty_for_wrong_tool_name(self):
        response = SimpleNamespace(content=[
            SimpleNamespace(
                type="tool_use", name="not_classify_nodes",
                input={"classifications": [{"node_id": 1}]},
            ),
        ])
        assert _extract_classifications_from_response(response) == []

    def test_returns_empty_when_input_malformed(self):
        response = SimpleNamespace(content=[
            SimpleNamespace(
                type="tool_use", name="classify_nodes",
                input={"not_classifications": []},
            ),
        ])
        assert _extract_classifications_from_response(response) == []


# ---------------------------------------------------------------------------
# Legacy text-parse shim (preserved for old callers)
# ---------------------------------------------------------------------------

class TestParseClassificationResponse:
    """Legacy text-parse path — kept for callers that haven't
    migrated to tool-use yet. Not exercised by ``classify_llm`` after
    M7.0.a.
    """

    def test_parses_valid_json(self):
        response = json.dumps([
            {"node_id": 1, "type": "card", "confidence": 0.85}
        ])
        results = parse_classification_response(response)
        assert len(results) == 1
        assert results[0]["type"] == "card"
        assert results[0]["confidence"] == 0.85

    def test_handles_json_in_markdown_block(self):
        response = "```json\n" + json.dumps([
            {"node_id": 1, "type": "dialog", "confidence": 0.9}
        ]) + "\n```"
        results = parse_classification_response(response)
        assert len(results) == 1
        assert results[0]["type"] == "dialog"

    def test_returns_empty_for_malformed(self):
        results = parse_classification_response("I don't know what this is")
        assert results == []

    def test_defaults_confidence(self):
        response = json.dumps([{"node_id": 1, "type": "card"}])
        results = parse_classification_response(response)
        assert results[0]["confidence"] == 0.7


# ---------------------------------------------------------------------------
# End-to-end classify_llm tests (mocked tool-use responses)
# ---------------------------------------------------------------------------

def _seed_llm_screen(db: sqlite3.Connection) -> None:
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'Home', 428, 926)"
    )
    nodes = [
        (10, 1, "n10", "artboard", "FRAME", 1, 0, 56, 400, 800, "VERTICAL"),
        (11, 1, "n11", "Overlay", "FRAME", 1, 1, 100, 350, 500, None),
    ]
    db.executemany(
        "INSERT INTO nodes "
        "(id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
        " y, width, height, layout_mode) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )
    db.commit()


class TestClassifyLLM:
    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_llm_screen(conn)
        yield conn
        conn.close()

    def test_inserts_llm_classifications(self, db: sqlite3.Connection):
        mock_client = _make_mock_client([
            {"node_id": 10, "canonical_type": "card",
             "confidence": 0.85, "reason": "Bounded container with image + heading + actions"},
            {"node_id": 11, "canonical_type": "dialog",
             "confidence": 0.8, "reason": "Overlay container with focus-grabbing styling"},
        ])
        result = classify_llm(db, screen_id=1, client=mock_client)
        assert result["classified"] == 2

        row = db.execute(
            "SELECT canonical_type, classification_source, confidence "
            "FROM screen_component_instances WHERE node_id = 10"
        ).fetchone()
        assert row[0] == "card"
        assert row[1] == "llm"
        assert row[2] == 0.85

    def test_skips_already_classified(self, db: sqlite3.Connection):
        db.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, "
            " classification_source) "
            "VALUES (1, 10, 'card', 1.0, 'formal')"
        )
        db.commit()
        mock_client = _make_mock_client([
            {"node_id": 11, "canonical_type": "dialog",
             "confidence": 0.8, "reason": "Overlay container"},
        ])
        result = classify_llm(db, screen_id=1, client=mock_client)
        assert result["classified"] == 1

    def test_handles_no_unclassified(self, db: sqlite3.Connection):
        db.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, "
            " classification_source) "
            "VALUES (1, 10, 'card', 1.0, 'formal')"
        )
        db.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, "
            " classification_source) "
            "VALUES (1, 11, 'dialog', 1.0, 'formal')"
        )
        db.commit()
        mock_client = _make_mock_client([])
        result = classify_llm(db, screen_id=1, client=mock_client)
        assert result["classified"] == 0

    def test_unsure_classifications_are_recorded(self, db: sqlite3.Connection):
        """A well-behaved LLM emits `unsure` instead of inventing a
        classification when the evidence is weak. We record the
        `unsure` entry with the model's confidence so the vision
        pass (or a human) can pick it up."""
        mock_client = _make_mock_client([
            {"node_id": 10, "canonical_type": "unsure",
             "confidence": 0.3, "reason": "Generic frame name, no child text"},
            {"node_id": 11, "canonical_type": "dialog",
             "confidence": 0.8, "reason": "Overlay"},
        ])
        result = classify_llm(db, screen_id=1, client=mock_client)
        assert result["classified"] == 2
        row = db.execute(
            "SELECT canonical_type, confidence FROM screen_component_instances "
            "WHERE node_id = 10"
        ).fetchone()
        assert row[0] == "unsure"
        assert row[1] == 0.3

    def test_invented_types_not_in_catalog_are_skipped(
        self, db: sqlite3.Connection,
    ):
        """LLM shouldn't be able to bypass the closed vocabulary,
        but if it tries, we skip the entry rather than insert a
        non-canonical type.
        """
        mock_client = _make_mock_client([
            {"node_id": 10, "canonical_type": "NOT_A_REAL_TYPE",
             "confidence": 0.9, "reason": "Made up"},
            {"node_id": 11, "canonical_type": "dialog",
             "confidence": 0.8, "reason": "Overlay"},
        ])
        result = classify_llm(db, screen_id=1, client=mock_client)
        # Only node 11 got classified; node 10's invented type was dropped.
        assert result["classified"] == 1

    def test_missing_tool_use_response_produces_zero(
        self, db: sqlite3.Connection,
    ):
        """When the model returns a free-text response with no
        tool_use block, we record zero classifications — no regex
        rescue paths.
        """
        mock_client = MagicMock()
        mock_client.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Sorry, I can't help.")]
        )
        result = classify_llm(db, screen_id=1, client=mock_client)
        assert result["classified"] == 0
