"""Tests for vision cross-validation (T5 Phase 1b, Step 4)."""

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from dd.db import init_db
from dd.catalog import seed_catalog
from dd.classify_vision import cross_validate_vision


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seed_vision_screen(db: sqlite3.Connection) -> None:
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'Home', 428, 926)"
    )
    nodes = [
        (10, 1, "10:100", "nav/top-nav", "INSTANCE", 1, 0),
        (11, 1, "11:200", "artboard", "FRAME", 1, 1),
        (12, 1, "12:300", "button/primary", "INSTANCE", 2, 0),
    ]
    db.executemany(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )
    # Classify: header (formal, conf=1.0), card (llm, conf=0.8), button (formal, conf=1.0)
    db.execute(
        "INSERT INTO screen_component_instances "
        "(id, screen_id, node_id, canonical_type, confidence, classification_source) "
        "VALUES (1, 1, 10, 'header', 1.0, 'formal')"
    )
    db.execute(
        "INSERT INTO screen_component_instances "
        "(id, screen_id, node_id, canonical_type, confidence, classification_source) "
        "VALUES (2, 1, 11, 'card', 0.8, 'llm')"
    )
    db.execute(
        "INSERT INTO screen_component_instances "
        "(id, screen_id, node_id, canonical_type, confidence, classification_source) "
        "VALUES (3, 1, 12, 'button', 1.0, 'formal')"
    )
    db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCrossValidateVision:
    """Verify vision cross-validation flags disagreements."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_vision_screen(conn)
        yield conn
        conn.close()

    def test_sets_vision_agrees_when_match(self, db: sqlite3.Connection):
        mock_client = _make_vision_client({
            "10:100": "header",
            "11:200": "card",
            "12:300": "button",
        })
        mock_fetcher = _make_screenshot_fetcher()

        result = cross_validate_vision(
            db, screen_id=1, file_key="fk",
            client=mock_client, fetch_screenshot=mock_fetcher,
        )

        cursor = db.execute(
            "SELECT vision_type, vision_agrees, flagged_for_review "
            "FROM screen_component_instances WHERE node_id = 11"
        )
        row = cursor.fetchone()
        assert row[0] == "card"
        assert row[1] == 1
        assert row[2] == 0

    def test_flags_disagreement(self, db: sqlite3.Connection):
        mock_client = _make_vision_client({
            "10:100": "header",
            "11:200": "dialog",  # LLM said "card", vision says "dialog"
            "12:300": "button",
        })
        mock_fetcher = _make_screenshot_fetcher()

        cross_validate_vision(
            db, screen_id=1, file_key="fk",
            client=mock_client, fetch_screenshot=mock_fetcher,
        )

        cursor = db.execute(
            "SELECT vision_type, vision_agrees, flagged_for_review "
            "FROM screen_component_instances WHERE node_id = 11"
        )
        row = cursor.fetchone()
        assert row[0] == "dialog"
        assert row[1] == 0
        assert row[2] == 1

    def test_only_validates_low_confidence(self, db: sqlite3.Connection):
        mock_client = _make_vision_client({"11:200": "card"})
        mock_fetcher = _make_screenshot_fetcher()

        result = cross_validate_vision(
            db, screen_id=1, file_key="fk",
            client=mock_client, fetch_screenshot=mock_fetcher,
            confidence_threshold=0.95,
        )

        # Only node 11 (conf=0.8) should be validated, not nodes 10,12 (conf=1.0)
        assert result["validated"] == 1

    def test_returns_summary(self, db: sqlite3.Connection):
        mock_client = _make_vision_client({
            "10:100": "header",
            "11:200": "card",
            "12:300": "button",
        })
        mock_fetcher = _make_screenshot_fetcher()

        result = cross_validate_vision(
            db, screen_id=1, file_key="fk",
            client=mock_client, fetch_screenshot=mock_fetcher,
            confidence_threshold=0.0,
        )

        assert "validated" in result
        assert "agreed" in result
        assert "disagreed" in result

    def test_handles_screenshot_failure(self, db: sqlite3.Connection):
        mock_client = _make_vision_client({"11:200": "card"})
        mock_fetcher = MagicMock(return_value=None)  # screenshot fails

        result = cross_validate_vision(
            db, screen_id=1, file_key="fk",
            client=mock_client, fetch_screenshot=mock_fetcher,
            confidence_threshold=0.0,
        )

        assert result["validated"] == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vision_client(type_map: dict) -> MagicMock:
    """Mock Anthropic client that classifies based on figma_node_id → type mapping."""
    def create_response(**kwargs):
        messages = kwargs.get("messages", [])
        for msg in messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        for fid, ctype in type_map.items():
                            if fid in block["text"]:
                                return MagicMock(
                                    content=[MagicMock(text=json.dumps({"type": ctype, "confidence": 0.9}))]
                                )
        return MagicMock(content=[MagicMock(text=json.dumps({"type": "unknown", "confidence": 0.3}))])

    mock = MagicMock()
    mock.messages.create.side_effect = create_response
    return mock


def _make_screenshot_fetcher() -> MagicMock:
    """Mock screenshot fetcher that returns a dummy PNG bytes."""
    # Minimal 1x1 PNG
    import base64
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    return MagicMock(return_value=tiny_png)
