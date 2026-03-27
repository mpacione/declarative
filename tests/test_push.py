"""Tests for dd.push module — MCP action generation and push manifest orchestration."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from dd.cli import main
from dd.db import init_db
from dd.push import convert_value_for_figma, generate_push_manifest, generate_variable_actions
from tests.fixtures import seed_post_curation


class TestConvertValueForFigma:
    """Test convert_value_for_figma produces Figma-native typed values."""

    def test_color_passes_through_as_string(self):
        assert convert_value_for_figma("#FF0000", "COLOR") == "#FF0000"

    def test_color_with_alpha_passes_through(self):
        assert convert_value_for_figma("#FF000080", "COLOR") == "#FF000080"

    def test_float_from_plain_number(self):
        assert convert_value_for_figma("16", "FLOAT") == 16.0

    def test_float_strips_px_suffix(self):
        assert convert_value_for_figma("16px", "FLOAT") == 16.0

    def test_float_handles_decimal(self):
        assert convert_value_for_figma("1.5", "FLOAT") == 1.5

    def test_float_zero(self):
        assert convert_value_for_figma("0", "FLOAT") == 0.0

    def test_float_negative(self):
        assert convert_value_for_figma("-4", "FLOAT") == -4.0

    def test_string_passes_through(self):
        assert convert_value_for_figma("Inter", "STRING") == "Inter"

    def test_string_strips_surrounding_quotes(self):
        assert convert_value_for_figma('"Inter"', "STRING") == "Inter"

    def test_string_strips_single_quotes(self):
        assert convert_value_for_figma("'SF Pro'", "STRING") == "SF Pro"

    def test_boolean_true(self):
        assert convert_value_for_figma("true", "BOOLEAN") is True

    def test_boolean_false(self):
        assert convert_value_for_figma("false", "BOOLEAN") is False

    def test_boolean_numeric_one(self):
        assert convert_value_for_figma("1", "BOOLEAN") is True

    def test_boolean_numeric_zero(self):
        assert convert_value_for_figma("0", "BOOLEAN") is False

    def test_float_opacity_scaled_to_percentage(self):
        """Figma opacity variables use 0-100 scale, not 0-1."""
        assert convert_value_for_figma("0.20", "FLOAT", is_opacity=True) == 20.0

    def test_float_opacity_zero(self):
        assert convert_value_for_figma("0", "FLOAT", is_opacity=True) == 0.0

    def test_float_opacity_one(self):
        assert convert_value_for_figma("1.0", "FLOAT", is_opacity=True) == 100.0

    def test_float_non_opacity_not_scaled(self):
        """Non-opacity FLOAT values should NOT be scaled."""
        assert convert_value_for_figma("0.20", "FLOAT", is_opacity=False) == 0.20


class TestGenerateVariableActionsFirstPush:
    """Test generate_variable_actions with no Figma state (first push — all CREATE)."""

    def test_all_tokens_are_create_when_no_figma_state(self, db):
        """With no Figma state, every curated token should be a CREATE action."""
        seed_post_curation(db)
        result = generate_variable_actions(db, file_id=1, figma_state=None)

        assert result["summary"]["create"] > 0
        assert result["summary"]["update"] == 0
        assert result["summary"]["delete"] == 0
        assert result["summary"]["unchanged"] == 0

    def test_actions_use_setup_design_tokens_for_new_collections(self, db):
        """First push should use figma_setup_design_tokens to create collections."""
        seed_post_curation(db)
        result = generate_variable_actions(db, file_id=1, figma_state=None)

        tools_used = {a["tool"] for a in result["actions"]}
        assert "figma_setup_design_tokens" in tools_used

    def test_actions_contain_collection_name_and_tokens(self, db):
        """Each action payload should have collectionName, modes, and tokens."""
        seed_post_curation(db)
        result = generate_variable_actions(db, file_id=1, figma_state=None)

        for action in result["actions"]:
            if action["tool"] == "figma_setup_design_tokens":
                assert "collectionName" in action["params"]
                assert "modes" in action["params"]
                assert "tokens" in action["params"]
                assert len(action["params"]["tokens"]) > 0
                assert len(action["params"]["tokens"]) <= 100

    def test_token_names_use_figma_slash_paths(self, db):
        """Token names in payloads should use slash-separated Figma paths."""
        seed_post_curation(db)
        result = generate_variable_actions(db, file_id=1, figma_state=None)

        for action in result["actions"]:
            if action["tool"] == "figma_setup_design_tokens":
                for token in action["params"]["tokens"]:
                    assert "." not in token["name"], f"Token name uses dots: {token['name']}"
                    assert "/" in token["name"] or len(token["name"].split("/")) == 1

    def test_summary_counts_match_total_curated_tokens(self, db):
        """Summary create count should equal total curated/aliased tokens."""
        seed_post_curation(db)

        cursor = db.execute("SELECT count(*) as c FROM tokens WHERE tier IN ('curated', 'aliased')")
        total = cursor.fetchone()["c"]

        result = generate_variable_actions(db, file_id=1, figma_state=None)
        assert result["summary"]["create"] == total

    def test_empty_db_produces_no_actions(self, db):
        """DB with no curated tokens should produce empty actions."""
        result = generate_variable_actions(db, file_id=1, figma_state=None)

        assert result["summary"]["create"] == 0
        assert result["actions"] == []


class TestGenerateVariableActionsIncremental:
    """Test generate_variable_actions with Figma state (incremental push)."""

    def _make_figma_state(self, db):
        """Build Figma state matching current DB tokens (all synced)."""
        cursor = db.execute("""
            SELECT t.name, t.type, tc.name AS collection_name,
                   tv.resolved_value, tm.name AS mode_name
            FROM tokens t
            JOIN token_collections tc ON t.collection_id = tc.id
            JOIN token_values tv ON tv.token_id = t.id
            JOIN token_modes tm ON tm.id = tv.mode_id
            WHERE t.tier IN ('curated', 'aliased')
        """)

        collections_dict: dict = {}
        for row in cursor:
            col_name = row["collection_name"]
            if col_name not in collections_dict:
                collections_dict[col_name] = {"name": col_name, "modes": [], "variables": []}

            figma_name = row["name"].replace(".", "/")
            variables = collections_dict[col_name]["variables"]
            existing = next((v for v in variables if v["name"] == figma_name), None)
            if existing is None:
                existing = {
                    "id": f"VariableID:1:{len(variables)}",
                    "name": figma_name,
                    "values": {},
                }
                variables.append(existing)

            existing["values"][row["mode_name"]] = row["resolved_value"]

        for col in collections_dict.values():
            mode_names = set()
            for v in col["variables"]:
                mode_names.update(v["values"].keys())
            col["modes"] = [{"id": f"m:{i}", "name": m} for i, m in enumerate(mode_names)]

        return {"collections": list(collections_dict.values())}

    def _seed_and_set_variable_ids(self, db):
        """Seed post-curation and set figma_variable_id on all tokens."""
        seed_post_curation(db)
        cursor = db.execute("SELECT id FROM tokens WHERE tier IN ('curated', 'aliased')")
        for i, row in enumerate(cursor.fetchall(), start=1):
            db.execute(
                "UPDATE tokens SET figma_variable_id = ? WHERE id = ?",
                (f"VariableID:1:{i}", row["id"]),
            )
        db.commit()

    def test_all_synced_produces_no_actions(self, db):
        """When DB and Figma match exactly, no actions needed."""
        self._seed_and_set_variable_ids(db)
        figma_state = self._make_figma_state(db)

        result = generate_variable_actions(db, file_id=1, figma_state=figma_state)

        assert result["summary"]["unchanged"] > 0
        assert result["summary"]["create"] == 0
        assert result["summary"]["update"] == 0
        assert result["summary"]["delete"] == 0
        assert result["actions"] == []

    def test_new_token_detected_as_create(self, db):
        """Token in DB without figma_variable_id should be CREATE."""
        self._seed_and_set_variable_ids(db)
        figma_state = self._make_figma_state(db)

        # Add a new token without figma_variable_id
        db.execute("""
            INSERT INTO tokens (collection_id, name, type, tier)
            VALUES (1, 'color.new.token', 'color', 'curated')
        """)
        new_token_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        mode_id = db.execute("SELECT id FROM token_modes WHERE collection_id = 1 AND is_default = 1").fetchone()["id"]
        db.execute("""
            INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
            VALUES (?, ?, '{"value": "#FF0000"}', '#FF0000')
        """, (new_token_id, mode_id))
        db.commit()

        result = generate_variable_actions(db, file_id=1, figma_state=figma_state)

        assert result["summary"]["create"] >= 1

    def test_drifted_token_detected_as_update(self, db):
        """Token with changed value should be UPDATE."""
        self._seed_and_set_variable_ids(db)
        figma_state = self._make_figma_state(db)

        # Change a value in DB so it drifts from Figma state
        db.execute("""
            UPDATE token_values SET resolved_value = '#CHANGED'
            WHERE token_id = (SELECT id FROM tokens WHERE tier = 'curated' LIMIT 1)
        """)
        db.commit()

        result = generate_variable_actions(db, file_id=1, figma_state=figma_state)

        assert result["summary"]["update"] >= 1
        update_actions = [a for a in result["actions"] if a["tool"] == "figma_batch_update_variables"]
        assert len(update_actions) > 0

    def test_figma_only_detected_as_delete(self, db):
        """Variable in Figma but not in DB should be DELETE."""
        self._seed_and_set_variable_ids(db)
        figma_state = self._make_figma_state(db)

        # Add extra variable to Figma state that's not in DB
        figma_state["collections"][0]["variables"].append({
            "id": "VariableID:999:999",
            "name": "extra/orphan/variable",
            "values": {"Default": "#AABBCC"},
        })

        result = generate_variable_actions(db, file_id=1, figma_state=figma_state)

        assert result["summary"]["delete"] >= 1
        delete_actions = [a for a in result["actions"] if a["tool"] == "figma_delete_variable"]
        assert len(delete_actions) > 0
        assert delete_actions[0]["params"]["variableId"] == "VariableID:999:999"


class TestGeneratePushManifest:
    """Test generate_push_manifest orchestrator."""

    def _seed_with_variable_ids(self, db):
        seed_post_curation(db)
        cursor = db.execute("SELECT id FROM tokens WHERE tier IN ('curated', 'aliased')")
        for i, row in enumerate(cursor.fetchall(), start=1):
            db.execute(
                "UPDATE tokens SET figma_variable_id = ? WHERE id = ?",
                (f"VariableID:1:{i}", row["id"]),
            )
        db.commit()

    def test_manifest_variables_phase(self, db):
        """Phase 'variables' includes variable actions but no rebind scripts."""
        seed_post_curation(db)
        manifest = generate_push_manifest(db, file_id=1, figma_state_json=None, phase="variables")

        assert "variables" in manifest["phases"]
        assert "rebind" not in manifest["phases"]
        assert manifest["phases"]["variables"]["summary"]["create"] > 0

    def test_manifest_rebind_phase(self, db):
        """Phase 'rebind' includes rebind scripts but no variable actions."""
        self._seed_with_variable_ids(db)
        manifest = generate_push_manifest(db, file_id=1, figma_state_json=None, phase="rebind")

        assert "rebind" in manifest["phases"]
        assert "variables" not in manifest["phases"]
        assert manifest["phases"]["rebind"]["tool"] == "figma_execute"

    def test_manifest_all_phase(self, db):
        """Phase 'all' includes both variables and rebind."""
        seed_post_curation(db)
        manifest = generate_push_manifest(db, file_id=1, figma_state_json=None, phase="all")

        assert "variables" in manifest["phases"]
        assert "rebind" in manifest["phases"]

    def test_manifest_rebind_has_scripts_and_summary(self, db):
        """Rebind phase includes scripts list and summary stats."""
        self._seed_with_variable_ids(db)

        manifest = generate_push_manifest(db, file_id=1, figma_state_json=None, phase="rebind")

        rebind = manifest["phases"]["rebind"]
        assert "scripts" in rebind
        assert "summary" in rebind
        assert rebind["summary"]["total_bindings"] > 0


    def test_manifest_has_no_restore_opacities_phase(self, db):
        """Alpha is baked into color variables — no separate opacity restoration needed."""
        self._seed_with_variable_ids(db)

        manifest = generate_push_manifest(db, file_id=1, figma_state_json=None, phase="all")
        assert "restore_opacities" not in manifest["phases"]


class TestPushCLI:
    """Test dd push CLI subcommand."""

    @pytest.fixture
    def db_file(self):
        """Create a temp DB file seeded with post-curation data."""
        with tempfile.NamedTemporaryFile(suffix=".declarative.db", delete=False) as f:
            db_path = f.name

        conn = init_db(db_path)
        seed_post_curation(conn)
        conn.close()
        yield db_path
        Path(db_path).unlink(missing_ok=True)

    def test_push_dry_run_outputs_summary(self, db_file, capsys):
        """dd push --dry-run should print a summary without action payloads."""
        main(["push", "--db", db_file, "--dry-run"])

        captured = capsys.readouterr()
        assert "create" in captured.out.lower()

    def test_push_variables_outputs_json(self, db_file, capsys):
        """dd push --phase variables should output valid JSON manifest."""
        main(["push", "--db", db_file, "--phase", "variables"])

        captured = capsys.readouterr()
        manifest = json.loads(captured.out)
        assert "phases" in manifest
        assert "variables" in manifest["phases"]

    def test_push_writeback_requires_figma_state(self, db_file):
        """dd push --writeback without --figma-state should error."""
        with pytest.raises(SystemExit):
            main(["push", "--db", db_file, "--writeback"])
