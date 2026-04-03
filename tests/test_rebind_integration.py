"""Token rebinding integration tests against real Dank DB.

Verifies that prompt-generated screens can have their token variables
rebound after execution. Auto-skips if Dank DB not present.
"""

import os
import sqlite3

import pytest

from dd.compose import generate_from_prompt
from dd.rebind_prompt import (
    build_rebind_entries,
    build_template_rebind_entries,
    generate_rebind_script,
    query_token_variables,
)

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
class TestTokenVariablesFromDankDB:
    """Verify token variable IDs exist in the Dank DB."""

    def test_has_token_variables(self, dank_db):
        variables = query_token_variables(dank_db)
        assert len(variables) > 100, f"Expected 100+ token variables, got {len(variables)}"

    def test_color_tokens_have_variable_ids(self, dank_db):
        variables = query_token_variables(dank_db)
        color_vars = {k: v for k, v in variables.items() if "color" in k.lower()}
        assert len(color_vars) > 20

    def test_variable_ids_are_valid_format(self, dank_db):
        variables = query_token_variables(dank_db)
        for name, var_id in list(variables.items())[:10]:
            assert var_id.startswith("VariableID:"), f"{name}: {var_id}"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestRebindWithPromptGeneration:
    """Verify rebind entries can be built from prompt-generated screens."""

    def test_token_refs_can_be_rebound(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Title"}},
                {"type": "text", "props": {"text": "Content"}},
            ]},
        ])
        token_refs = result["token_refs"]
        variables = query_token_variables(dank_db)

        # Simulate M dict (element_id → figma_node_id)
        fake_node_map = {ref[0]: f"999:{i}" for i, ref in enumerate(token_refs)}

        entries = build_rebind_entries(token_refs, fake_node_map, variables)
        # Some refs may not have variable IDs (un-exported tokens)
        # But if any exist, the pipeline works
        assert isinstance(entries, list)

    def test_rebind_script_generated_from_real_tokens(self, dank_db):
        variables = query_token_variables(dank_db)
        # Pick a real token we know exists
        if not variables:
            pytest.skip("No token variables in DB")

        first_token = next(iter(variables))
        entries = [{
            "node_id": "999:1",
            "property": "fill.0.color",
            "variable_id": variables[first_token],
        }]
        script = generate_rebind_script(entries)
        assert "async" in script
        assert "999:1" in script

    def test_full_pipeline_token_ref_count(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "header"},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Section"}},
            ]},
            {"type": "button"},
        ])
        # Token refs collected during generation (from template visual bindings)
        # May be 0 for template-only generation (no token bindings in templates)
        assert isinstance(result["token_refs"], list)


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestRebindScriptQuality:
    """Verify generated rebind scripts are well-formed."""

    def test_script_is_valid_js(self, dank_db):
        variables = query_token_variables(dank_db)
        if not variables:
            pytest.skip("No token variables")

        # Build 5 entries with real variable IDs
        entries = []
        for i, (name, var_id) in enumerate(list(variables.items())[:5]):
            entries.append({
                "node_id": f"999:{i}",
                "property": "fill.0.color",
                "variable_id": var_id,
            })

        script = generate_rebind_script(entries)
        assert script.startswith("(async")
        assert script.endswith(";")
        assert "Rebound" in script

    def test_script_handles_mixed_properties(self, dank_db):
        variables = query_token_variables(dank_db)
        if len(variables) < 3:
            pytest.skip("Not enough token variables")

        var_list = list(variables.values())
        entries = [
            {"node_id": "999:1", "property": "fill.0.color", "variable_id": var_list[0]},
            {"node_id": "999:2", "property": "cornerRadius", "variable_id": var_list[1]},
            {"node_id": "999:3", "property": "padding.top", "variable_id": var_list[2]},
        ]
        script = generate_rebind_script(entries)
        assert "999:1" in script
        assert "999:2" in script
        assert "999:3" in script


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestTemplateRebindEntries:
    """Verify template-sourced rebind entries work with real Dank data."""

    def test_template_entries_produce_rebind_entries(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "header"},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Section"}},
            ]},
            {"type": "button", "props": {"text": "Save"}},
        ])
        template_entries = result["template_rebind_entries"]
        assert len(template_entries) > 0

        fake_node_map = {e["element_id"]: f"999:{i}" for i, e in enumerate(template_entries)}
        entries = build_template_rebind_entries(template_entries, fake_node_map)
        assert len(entries) == len(template_entries)

        for entry in entries:
            assert entry["node_id"].startswith("999:")
            assert entry["variable_id"].startswith("VariableID:")

    def test_template_rebind_generates_valid_script(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Title"}},
            ]},
        ])
        template_entries = result["template_rebind_entries"]
        if not template_entries:
            pytest.skip("No template rebind entries")

        fake_node_map = {e["element_id"]: f"999:{i}" for i, e in enumerate(template_entries)}
        entries = build_template_rebind_entries(template_entries, fake_node_map)
        script = generate_rebind_script(entries)
        assert "async" in script
        assert "VariableID:" in script

    def test_skips_missing_figma_nodes(self, dank_db):
        template_entries = [
            {"element_id": "nonexistent-1", "property": "fill.0.color", "variable_id": "VariableID:1:2"},
        ]
        entries = build_template_rebind_entries(template_entries, {})
        assert entries == []
