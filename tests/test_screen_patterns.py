"""Tests for screen pattern extraction and archetype matching."""

import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.db import init_db
from dd.screen_patterns import extract_screen_archetypes, get_archetype_prompt_context


class TestExtractScreenArchetypes:
    """Verify archetype extraction from classified screens."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
        for i in range(1, 6):
            conn.execute(
                "INSERT INTO screens (id, file_id, figma_node_id, name, width, height, screen_type) "
                f"VALUES ({i}, 1, 's{i}', 'Screen {i}', 428, 926, 'app_screen')"
            )
            # Root nodes
            conn.execute(
                f"INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, x, y, width, height) "
                f"VALUES ({i*100}, {i}, 'h{i}', 'header', 'INSTANCE', 1, 0, 0, 0, 428, 56)"
            )
            conn.execute(
                f"INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, x, y, width, height) "
                f"VALUES ({i*100+1}, {i}, 'c{i}', 'card', 'FRAME', 1, 1, 0, 56, 428, 400)"
            )
            conn.execute(
                f"INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, x, y, width, height) "
                f"VALUES ({i*100+2}, {i}, 'b{i}', 'button', 'INSTANCE', 1, 2, 0, 460, 200, 48)"
            )
            # Classifications
            conn.execute(
                f"INSERT INTO screen_component_instances (screen_id, node_id, canonical_type, confidence, classification_source) "
                f"VALUES ({i}, {i*100}, 'header', 1.0, 'formal')"
            )
            conn.execute(
                f"INSERT INTO screen_component_instances (screen_id, node_id, canonical_type, confidence, classification_source) "
                f"VALUES ({i}, {i*100+1}, 'card', 1.0, 'formal')"
            )
            conn.execute(
                f"INSERT INTO screen_component_instances (screen_id, node_id, canonical_type, confidence, classification_source) "
                f"VALUES ({i}, {i*100+2}, 'button', 1.0, 'formal')"
            )
        conn.commit()
        yield conn
        conn.close()

    def test_returns_list_of_archetypes(self, db):
        archetypes = extract_screen_archetypes(db, file_id=1)
        assert isinstance(archetypes, list)
        assert len(archetypes) >= 1

    def test_archetype_has_required_fields(self, db):
        archetypes = extract_screen_archetypes(db, file_id=1)
        arch = archetypes[0]
        assert "signature" in arch
        assert "screen_count" in arch
        assert "component_types" in arch

    def test_dominant_archetype_has_all_three_types(self, db):
        archetypes = extract_screen_archetypes(db, file_id=1)
        dominant = archetypes[0]
        assert "header" in dominant["component_types"]
        assert "card" in dominant["component_types"]
        assert "button" in dominant["component_types"]

    def test_screen_count_correct(self, db):
        archetypes = extract_screen_archetypes(db, file_id=1)
        dominant = archetypes[0]
        assert dominant["screen_count"] == 5


class TestGetArchetypePromptContext:
    """Verify archetype context generation for LLM prompt enhancement."""

    def test_returns_string(self):
        archetypes = [
            {"signature": "button, card, header", "screen_count": 155, "component_types": ["button", "card", "header"]},
            {"signature": "button, header", "screen_count": 19, "component_types": ["button", "header"]},
        ]
        context = get_archetype_prompt_context(archetypes)
        assert isinstance(context, str)
        assert len(context) > 50

    def test_contains_archetype_info(self):
        archetypes = [
            {"signature": "button, card, header", "screen_count": 155, "component_types": ["button", "card", "header"]},
        ]
        context = get_archetype_prompt_context(archetypes)
        assert "button" in context
        assert "card" in context
        assert "header" in context
        assert "155" in context

    def test_empty_archetypes_returns_empty(self):
        context = get_archetype_prompt_context([])
        assert context == ""
