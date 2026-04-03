"""Tests for token rebinding on prompt-generated screens."""

import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.db import init_db
from dd.rebind_prompt import build_rebind_entries, generate_rebind_script


class TestBuildRebindEntries:
    """Verify rebind entry construction from token_refs + node_id_map."""

    def test_maps_element_ids_to_figma_node_ids(self):
        token_refs = [("button-1", "fill.0.color", "color.primary")]
        figma_node_map = {"button-1": "5520:157252"}
        token_variables = {"color.primary": "VariableID:123:456"}

        entries = build_rebind_entries(token_refs, figma_node_map, token_variables)
        assert len(entries) == 1
        assert entries[0]["node_id"] == "5520:157252"
        assert entries[0]["property"] == "fill.0.color"
        assert entries[0]["variable_id"] == "VariableID:123:456"

    def test_skips_missing_element_ids(self):
        token_refs = [("missing-1", "fill.0.color", "color.primary")]
        figma_node_map = {}
        token_variables = {"color.primary": "VariableID:123:456"}

        entries = build_rebind_entries(token_refs, figma_node_map, token_variables)
        assert entries == []

    def test_skips_missing_token_variables(self):
        token_refs = [("button-1", "fill.0.color", "missing.token")]
        figma_node_map = {"button-1": "5520:157252"}
        token_variables = {}

        entries = build_rebind_entries(token_refs, figma_node_map, token_variables)
        assert entries == []

    def test_handles_multiple_refs(self):
        token_refs = [
            ("button-1", "fill.0.color", "color.primary"),
            ("button-1", "cornerRadius", "radius.md"),
            ("card-1", "fill.0.color", "color.surface"),
        ]
        figma_node_map = {"button-1": "100:1", "card-1": "100:2"}
        token_variables = {
            "color.primary": "VariableID:1:1",
            "radius.md": "VariableID:2:2",
            "color.surface": "VariableID:3:3",
        }

        entries = build_rebind_entries(token_refs, figma_node_map, token_variables)
        assert len(entries) == 3

    def test_handles_padding_refs(self):
        token_refs = [("card-1", "padding.top", "space.md")]
        figma_node_map = {"card-1": "100:1"}
        token_variables = {"space.md": "VariableID:4:4"}

        entries = build_rebind_entries(token_refs, figma_node_map, token_variables)
        assert len(entries) == 1
        assert entries[0]["property"] == "padding.top"


class TestGenerateRebindScript:
    """Verify rebind script generation from entries."""

    def test_produces_executable_script(self):
        entries = [
            {"node_id": "100:1", "property": "fill.0.color", "variable_id": "VariableID:1:1"},
        ]
        script = generate_rebind_script(entries)
        assert "async" in script
        assert "100:1" in script
        assert "1:1" in script

    def test_empty_entries_produces_noop_script(self):
        script = generate_rebind_script([])
        assert "async" in script
        assert "Rebound" in script

    def test_multiple_entries_in_one_script(self):
        entries = [
            {"node_id": "100:1", "property": "fill.0.color", "variable_id": "VariableID:1:1"},
            {"node_id": "100:2", "property": "cornerRadius", "variable_id": "VariableID:2:2"},
        ]
        script = generate_rebind_script(entries)
        assert "100:1" in script
        assert "100:2" in script


class TestQueryTokenVariables:
    """Verify token variable ID lookup from DB."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
        conn.execute("INSERT INTO token_collections (id, file_id, name) VALUES (1, 1, 'Colors')")
        conn.execute("INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (1, 1, 'Default', 1)")
        conn.execute(
            "INSERT INTO tokens (id, collection_id, name, type, figma_variable_id) "
            "VALUES (1, 1, 'color.primary', 'color', 'VariableID:123:456')"
        )
        conn.execute(
            "INSERT INTO tokens (id, collection_id, name, type, figma_variable_id) "
            "VALUES (2, 1, 'space.md', 'number', 'VariableID:789:012')"
        )
        conn.execute(
            "INSERT INTO tokens (id, collection_id, name, type) "
            "VALUES (3, 1, 'color.unlinked', 'color')"
        )
        conn.commit()
        yield conn
        conn.close()

    def test_returns_token_to_variable_map(self, db):
        from dd.rebind_prompt import query_token_variables
        result = query_token_variables(db)
        assert result["color.primary"] == "VariableID:123:456"
        assert result["space.md"] == "VariableID:789:012"

    def test_excludes_tokens_without_variable_id(self, db):
        from dd.rebind_prompt import query_token_variables
        result = query_token_variables(db)
        assert "color.unlinked" not in result
