"""Tests for LLM classification (T5 Phase 1b, Step 3)."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from dd.catalog import seed_catalog
from dd.classify_llm import (
    build_classification_prompt,
    classify_llm,
    parse_classification_response,
)
from dd.db import init_db

# ---------------------------------------------------------------------------
# Step 2: Prompt builder tests
# ---------------------------------------------------------------------------

class TestBuildClassificationPrompt:
    """Verify prompt construction for LLM classification."""

    def test_includes_canonical_types(self):
        nodes = [_make_unclassified_node(name="artboard")]
        catalog_types = ["button", "card", "header", "dialog"]
        prompt = build_classification_prompt(nodes, catalog_types)
        assert "button" in prompt
        assert "card" in prompt
        assert "header" in prompt

    def test_includes_node_description(self):
        nodes = [_make_unclassified_node(
            name="artboard", width=428, height=800,
            layout_mode="VERTICAL", child_count=5,
        )]
        prompt = build_classification_prompt(nodes, ["card", "dialog"])
        assert "artboard" in prompt
        assert "428" in prompt
        assert "VERTICAL" in prompt

    def test_includes_container_option(self):
        nodes = [_make_unclassified_node(name="content")]
        prompt = build_classification_prompt(nodes, ["button"])
        assert "container" in prompt

    def test_handles_multiple_nodes(self):
        nodes = [
            _make_unclassified_node(name="artboard", node_id=1),
            _make_unclassified_node(name="Overlay", node_id=2),
        ]
        prompt = build_classification_prompt(nodes, ["dialog", "card"])
        assert "artboard" in prompt
        assert "Overlay" in prompt

    def test_requests_json_response(self):
        nodes = [_make_unclassified_node()]
        prompt = build_classification_prompt(nodes, ["button"])
        assert "JSON" in prompt or "json" in prompt


# ---------------------------------------------------------------------------
# Step 3: Response parser tests
# ---------------------------------------------------------------------------

class TestParseClassificationResponse:
    """Verify parsing of LLM classification responses."""

    def test_parses_valid_json(self):
        response = json.dumps([
            {"node_id": 1, "type": "card", "confidence": 0.85}
        ])
        results = parse_classification_response(response)
        assert len(results) == 1
        assert results[0]["type"] == "card"
        assert results[0]["confidence"] == 0.85

    def test_parses_container_type(self):
        response = json.dumps([
            {"node_id": 1, "type": "container", "confidence": 0.7}
        ])
        results = parse_classification_response(response)
        assert results[0]["type"] == "container"

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

    def test_skips_entries_without_type(self):
        response = json.dumps([
            {"node_id": 1, "type": "card", "confidence": 0.8},
            {"node_id": 2, "confidence": 0.5},
        ])
        results = parse_classification_response(response)
        assert len(results) == 1

    def test_defaults_confidence(self):
        response = json.dumps([
            {"node_id": 1, "type": "card"}
        ])
        results = parse_classification_response(response)
        assert results[0]["confidence"] == 0.7  # default for LLM


# ---------------------------------------------------------------------------
# Step 4: LLM classification function tests
# ---------------------------------------------------------------------------

def _seed_llm_screen(db: sqlite3.Connection) -> None:
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'Home', 428, 926)"
    )
    nodes = [
        (10, 1, "f1", "artboard", "FRAME", 1, 0, 0, 56, 428, 800, "VERTICAL"),
        (11, 1, "f2", "Overlay", "FRAME", 1, 1, 0, 0, 428, 926, None),
    ]
    db.executemany(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
        "x, y, width, height, layout_mode) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )
    db.commit()


class TestClassifyLLM:
    """Verify classify_llm() with mocked API client."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_llm_screen(conn)
        yield conn
        conn.close()

    def test_inserts_llm_classifications(self, db: sqlite3.Connection):
        mock_client = _make_mock_client([
            {"node_id": 10, "type": "card", "confidence": 0.85},
            {"node_id": 11, "type": "dialog", "confidence": 0.8},
        ])

        result = classify_llm(db, screen_id=1, client=mock_client)
        assert result["classified"] == 2

        cursor = db.execute(
            "SELECT canonical_type, classification_source, confidence "
            "FROM screen_component_instances WHERE node_id = 10"
        )
        row = cursor.fetchone()
        assert row[0] == "card"
        assert row[1] == "llm"
        assert row[2] == 0.85

    def test_skips_already_classified(self, db: sqlite3.Connection):
        db.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, classification_source) "
            "VALUES (1, 10, 'card', 1.0, 'formal')"
        )
        db.commit()

        mock_client = _make_mock_client([
            {"node_id": 11, "type": "dialog", "confidence": 0.8},
        ])

        result = classify_llm(db, screen_id=1, client=mock_client)
        assert result["classified"] == 1

    def test_handles_no_unclassified(self, db: sqlite3.Connection):
        db.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, classification_source) "
            "VALUES (1, 10, 'card', 1.0, 'formal')"
        )
        db.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, classification_source) "
            "VALUES (1, 11, 'dialog', 1.0, 'formal')"
        )
        db.commit()

        mock_client = _make_mock_client([])
        result = classify_llm(db, screen_id=1, client=mock_client)
        assert result["classified"] == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_unclassified_node(
    node_id: int = 1,
    name: str = "artboard",
    width: float = 428,
    height: float = 800,
    layout_mode: str | None = "VERTICAL",
    child_count: int = 3,
) -> dict:
    return {
        "node_id": node_id,
        "name": name,
        "node_type": "FRAME",
        "depth": 1,
        "width": width,
        "height": height,
        "layout_mode": layout_mode,
        "child_count": child_count,
        "screen_name": "Home",
        "screen_width": 428,
        "screen_height": 926,
        "y": 56,
    }


def _make_mock_client(classifications: list) -> MagicMock:
    mock = MagicMock()
    mock.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps(classifications))]
    )
    return mock
