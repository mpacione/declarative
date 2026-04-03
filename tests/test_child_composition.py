"""Tests for child composition extraction from classified instances."""

import json
import os
import sqlite3

import pytest

from dd.templates import extract_child_composition, extract_templates, query_templates

DANK_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db")
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)


@pytest.fixture
def dank_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DANK_DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestExtractChildComposition:
    """Verify child composition patterns extracted from classified instances."""

    def test_returns_dict_keyed_by_parent_type(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        result = extract_child_composition(dank_db, file_id)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_button_has_icon_and_text_children(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        result = extract_child_composition(dank_db, file_id)
        assert "button" in result
        child_types = {c["child_type"] for c in result["button"]}
        assert "icon" in child_types
        assert "text" in child_types

    def test_tabs_has_button_children(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        result = extract_child_composition(dank_db, file_id)
        assert "tabs" in result
        child_types = {c["child_type"] for c in result["tabs"]}
        assert "button" in child_types

    def test_header_has_container_children(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        result = extract_child_composition(dank_db, file_id)
        assert "header" in result
        child_types = {c["child_type"] for c in result["header"]}
        assert "container" in child_types

    def test_children_have_count_mode(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        result = extract_child_composition(dank_db, file_id)
        for parent_type, children in result.items():
            for child in children:
                assert "count_mode" in child
                assert child["count_mode"] >= 1

    def test_children_have_component_key_when_available(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        result = extract_child_composition(dank_db, file_id)
        tabs_children = result.get("tabs", [])
        button_child = next((c for c in tabs_children if c["child_type"] == "button"), None)
        assert button_child is not None
        assert button_child.get("component_key") is not None

    def test_children_have_frequency(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        result = extract_child_composition(dank_db, file_id)
        for parent_type, children in result.items():
            for child in children:
                assert "frequency" in child
                assert 0 < child["frequency"] <= 1.0

    def test_filters_low_frequency_children(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        result = extract_child_composition(dank_db, file_id)
        for parent_type, children in result.items():
            for child in children:
                assert child["frequency"] >= 0.1


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestTemplatesWithComposition:
    """Verify extract_templates populates slots with composition data."""

    def test_extract_templates_populates_slots(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        extract_templates(dank_db, file_id)

        has_slots = dank_db.execute(
            "SELECT COUNT(*) FROM component_templates "
            "WHERE slots IS NOT NULL AND slots != 'null'"
        ).fetchone()[0]
        assert has_slots > 0

    def test_query_templates_includes_children_composition(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        extract_templates(dank_db, file_id)
        templates = query_templates(dank_db)

        has_composition = False
        for cat_type, tmpl_list in templates.items():
            for tmpl in tmpl_list:
                if tmpl.get("children_composition"):
                    has_composition = True
                    break
        assert has_composition

    def test_tabs_template_has_button_composition(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        extract_templates(dank_db, file_id)
        templates = query_templates(dank_db)

        tabs_list = templates.get("tabs", [])
        keyed_tabs = [t for t in tabs_list if t.get("component_key")]
        assert len(keyed_tabs) > 0

        tabs_tmpl = keyed_tabs[0]
        composition = tabs_tmpl.get("children_composition", [])
        child_types = {c["child_type"] for c in composition}
        assert "button" in child_types
