"""Tests for component key registry — unified component_key → figma_node_id lookup."""

import json
import os
import sqlite3

import pytest

from dd.templates import build_component_key_registry, extract_child_composition, extract_templates, query_templates

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
class TestBuildComponentKeyRegistry:
    """Verify component key registry is built from nodes table."""

    def test_creates_registry_table(self, dank_db):
        build_component_key_registry(dank_db)
        count = dank_db.execute("SELECT COUNT(*) FROM component_key_registry").fetchone()[0]
        assert count > 0

    def test_covers_majority_of_keys(self, dank_db):
        build_component_key_registry(dank_db)
        registry_count = dank_db.execute("SELECT COUNT(*) FROM component_key_registry").fetchone()[0]
        total_keys = dank_db.execute(
            "SELECT COUNT(DISTINCT component_key) FROM nodes WHERE component_key IS NOT NULL"
        ).fetchone()[0]
        coverage = registry_count / total_keys
        assert coverage >= 0.75, f"Registry covers {coverage:.0%} of keys, expected >= 75%"

    def test_button_large_translucent_resolved(self, dank_db):
        build_component_key_registry(dank_db)
        row = dank_db.execute(
            "SELECT figma_node_id, name FROM component_key_registry WHERE name = 'button/large/translucent'"
        ).fetchone()
        assert row is not None
        assert row["figma_node_id"] is not None

    def test_icon_back_resolved(self, dank_db):
        build_component_key_registry(dank_db)
        row = dank_db.execute(
            "SELECT figma_node_id FROM component_key_registry WHERE name = 'icon/back'"
        ).fetchone()
        assert row is not None

    def test_registry_has_instance_counts(self, dank_db):
        build_component_key_registry(dank_db)
        row = dank_db.execute(
            "SELECT instance_count FROM component_key_registry ORDER BY instance_count DESC LIMIT 1"
        ).fetchone()
        assert row["instance_count"] > 100


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestCompositionUsesRegistry:
    """Verify extract_child_composition uses registry for figma_id resolution."""

    def test_composition_children_have_figma_id(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        build_component_key_registry(dank_db)
        composition = extract_child_composition(dank_db, file_id)

        resolved = 0
        total_keyed = 0
        for parent_type, children in composition.items():
            for child in children:
                if child.get("component_key"):
                    total_keyed += 1
                    if child.get("component_figma_id"):
                        resolved += 1

        assert total_keyed > 0
        coverage = resolved / total_keyed
        assert coverage >= 0.5, f"Only {coverage:.0%} of keyed children resolved figma_id"

    def test_templates_have_figma_id_after_extraction(self, dank_db):
        file_id = dank_db.execute("SELECT id FROM files LIMIT 1").fetchone()[0]
        build_component_key_registry(dank_db)
        extract_templates(dank_db, file_id)
        templates = query_templates(dank_db)

        keyed_with_figma = 0
        keyed_total = 0
        for cat_type, tmpl_list in templates.items():
            for tmpl in tmpl_list:
                if tmpl.get("component_key"):
                    keyed_total += 1
                    if tmpl.get("component_figma_id"):
                        keyed_with_figma += 1

        assert keyed_total > 0
        coverage = keyed_with_figma / keyed_total
        assert coverage >= 0.15, f"Only {coverage:.0%} of keyed templates have figma_id"
