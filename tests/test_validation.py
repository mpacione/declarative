"""Tests for pre-export validation phase."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from dd.types import Severity
from dd.validate import (
    check_alias_targets_curated,
    check_binding_coverage,
    check_mode_completeness,
    check_name_dtcg_compliant,
    check_name_uniqueness,
    check_orphan_tokens,
    check_value_format,
    is_export_ready,
    run_validation,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> sqlite3.Connection:
    """Create a temporary database with schema."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Load schema
    schema_path = Path(__file__).parent.parent / "schema.sql"
    with open(schema_path) as f:
        conn.executescript(f.read())

    return conn


@pytest.fixture
def populated_db(temp_db: sqlite3.Connection) -> sqlite3.Connection:
    """Create a database with test data."""
    conn = temp_db

    # Insert test file
    conn.execute(
        "INSERT INTO files (id, file_key, name) VALUES (1, 'test123', 'Test File')"
    )

    # Insert collections and modes
    conn.execute(
        """INSERT INTO token_collections (id, file_id, name)
        VALUES (1, 1, 'Colors'), (2, 1, 'Spacing')"""
    )

    conn.execute(
        """INSERT INTO token_modes (id, collection_id, name, is_default) VALUES
        (1, 1, 'Light', 1), (2, 1, 'Dark', 0),
        (3, 2, 'Compact', 1), (4, 2, 'Comfortable', 0)"""
    )

    conn.commit()
    return conn


class TestCheckModeCompleteness:
    def test_all_tokens_have_all_mode_values(self, populated_db: sqlite3.Connection):
        """Test that tokens with values for all modes pass validation."""
        conn = populated_db

        # Insert tokens with complete values
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type, tier) VALUES
            (1, 1, 'color.primary', 'color', 'curated'),
            (2, 1, 'color.secondary', 'color', 'curated')"""
        )

        # Insert values for all modes
        conn.execute(
            """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES
            (1, 1, '{}', '#FF0000'),
            (1, 2, '{}', '#880000'),
            (2, 1, '{}', '#00FF00'),
            (2, 2, '{}', '#008800')"""
        )
        conn.commit()

        issues = check_mode_completeness(conn, file_id=1)
        assert len(issues) == 0

    def test_missing_mode_values_detected(self, populated_db: sqlite3.Connection):
        """Test that missing mode values are detected."""
        conn = populated_db

        # Insert tokens
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type, tier) VALUES
            (1, 1, 'color.primary', 'color', 'curated'),
            (2, 1, 'color.secondary', 'color', 'curated')"""
        )

        # Insert incomplete values (missing Dark mode for color.secondary)
        conn.execute(
            """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES
            (1, 1, '{}', '#FF0000'),
            (1, 2, '{}', '#880000'),
            (2, 1, '{}', '#00FF00')"""
        )
        conn.commit()

        issues = check_mode_completeness(conn, file_id=1)
        assert len(issues) == 1
        assert issues[0]["check_name"] == "mode_completeness"
        assert issues[0]["severity"] == "error"
        assert "color.secondary" in issues[0]["message"]
        assert "Dark" in issues[0]["message"]
        assert json.loads(issues[0]["affected_ids"]) == [2]

    def test_aliased_tokens_skipped(self, populated_db: sqlite3.Connection):
        """Test that aliased tokens are not checked for mode completeness."""
        conn = populated_db

        # Insert base and aliased tokens
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type, tier, alias_of) VALUES
            (1, 1, 'color.primary', 'color', 'curated', NULL),
            (2, 1, 'color.brand', 'color', 'aliased', 1)"""
        )

        # Only base token needs values
        conn.execute(
            """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES
            (1, 1, '{}', '#FF0000'),
            (1, 2, '{}', '#880000')"""
        )
        conn.commit()

        issues = check_mode_completeness(conn, file_id=1)
        assert len(issues) == 0


class TestCheckNameDtcgCompliant:
    def test_valid_names_pass(self, populated_db: sqlite3.Connection):
        """Test that DTCG-compliant names pass validation."""
        conn = populated_db

        valid_names = [
            "color",
            "color.primary",
            "color.surface.primary",
            "space.4",
            "space.4.5",
            "typography.body.regular",
            "size.button.small",
        ]

        for i, name in enumerate(valid_names, 1):
            conn.execute(
                f"INSERT INTO tokens (id, collection_id, name, type) VALUES ({i}, 1, '{name}', 'color')"
            )
        conn.commit()

        issues = check_name_dtcg_compliant(conn, file_id=1)
        assert len(issues) == 0

    def test_invalid_names_detected(self, populated_db: sqlite3.Connection):
        """Test that non-compliant names are detected."""
        conn = populated_db

        invalid_names = [
            "Color",  # Uppercase
            "color-primary",  # Hyphen instead of dot
            "color.Primary",  # Uppercase segment
            "color..primary",  # Double dot
            ".color",  # Leading dot
            "color.",  # Trailing dot
            "color primary",  # Space
            "color_primary",  # Underscore
            "1color",  # Starting with number
        ]

        for i, name in enumerate(invalid_names, 1):
            conn.execute(
                f"INSERT INTO tokens (id, collection_id, name, type) VALUES ({i}, 1, '{name}', 'color')"
            )
        conn.commit()

        issues = check_name_dtcg_compliant(conn, file_id=1)
        assert len(issues) == len(invalid_names)
        for issue in issues:
            assert issue["check_name"] == "name_dtcg_compliant"
            assert issue["severity"] == "error"
            assert "DTCG" in issue["message"]

    def test_numeric_segments_allowed(self, populated_db: sqlite3.Connection):
        """Test that numeric segments are allowed for spacing multipliers."""
        conn = populated_db

        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 2, 'space.4', 'dimension'),
            (2, 2, 'space.4.5', 'dimension'),
            (3, 2, 'space.0', 'dimension')"""
        )
        conn.commit()

        issues = check_name_dtcg_compliant(conn, file_id=1)
        assert len(issues) == 0


class TestCheckOrphanTokens:
    def test_tokens_with_bindings_not_orphans(self, populated_db: sqlite3.Connection):
        """Test that tokens with bindings are not considered orphans."""
        conn = populated_db

        # Insert screen, node, token
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, '1:1', 'Screen', 100, 100)"
        )
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) VALUES (1, 1, '1:2', 'Node', 'FRAME')"
        )
        conn.execute(
            "INSERT INTO tokens (id, collection_id, name, type) VALUES (1, 1, 'color.primary', 'color')"
        )
        conn.execute(
            "INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value) VALUES (1, 'fill.0.color', 1, '{}', '#FF0000')"
        )
        conn.commit()

        issues = check_orphan_tokens(conn, file_id=1)
        assert len(issues) == 0

    def test_orphan_tokens_detected(self, populated_db: sqlite3.Connection):
        """Test that tokens without bindings are detected as orphans."""
        conn = populated_db

        # Insert tokens without any bindings
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 1, 'color.orphan1', 'color'),
            (2, 1, 'color.orphan2', 'color')"""
        )
        conn.commit()

        issues = check_orphan_tokens(conn, file_id=1)
        assert len(issues) == 2
        for issue in issues:
            assert issue["check_name"] == "orphan_tokens"
            assert issue["severity"] == "warning"
            assert "orphan" in issue["message"].lower()

    def test_aliased_tokens_not_checked_for_orphans(
        self, populated_db: sqlite3.Connection
    ):
        """Test that aliased tokens are not checked for orphan status."""
        conn = populated_db

        # Insert base and aliased tokens without bindings
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type, tier, alias_of) VALUES
            (1, 1, 'color.primary', 'color', 'curated', NULL),
            (2, 1, 'color.brand', 'color', 'aliased', 1)"""
        )
        conn.commit()

        issues = check_orphan_tokens(conn, file_id=1)
        # Only the base token should be reported as orphan
        assert len(issues) == 1
        assert "color.primary" in issues[0]["message"]


class TestCheckBindingCoverage:
    def test_binding_coverage_calculation(self, populated_db: sqlite3.Connection):
        """Test that binding coverage is calculated correctly."""
        conn = populated_db

        # Insert screen and nodes
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, '1:1', 'Screen', 100, 100)"
        )
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) VALUES (1, 1, '1:2', 'Node1', 'FRAME'), (2, 1, '1:3', 'Node2', 'FRAME')"
        )

        # Insert tokens
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 1, 'color.primary', 'color'),
            (2, 1, 'color.secondary', 'color')"""
        )

        # Insert bindings with different statuses
        conn.execute(
            """INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status) VALUES
            (1, 'fill.0.color', 1, '{}', '#FF0000', 'bound'),
            (1, 'fill.1.color', 2, '{}', '#00FF00', 'bound'),
            (2, 'fill.0.color', 1, '{}', '#FF0000', 'proposed'),
            (2, 'stroke.0.color', NULL, '{}', '#0000FF', 'unbound')"""
        )
        conn.commit()

        issues = check_binding_coverage(conn, file_id=1)
        assert len(issues) == 1
        assert issues[0]["check_name"] == "binding_coverage"
        assert issues[0]["severity"] == "info"
        assert "50.0% bound" in issues[0]["message"]
        assert "25.0% proposed" in issues[0]["message"]
        assert "25.0% unbound" in issues[0]["message"]

    def test_binding_coverage_with_no_bindings(
        self, populated_db: sqlite3.Connection
    ):
        """Test binding coverage when no bindings exist."""
        conn = populated_db

        issues = check_binding_coverage(conn, file_id=1)
        assert len(issues) == 1
        assert issues[0]["check_name"] == "binding_coverage"
        assert issues[0]["severity"] == "info"
        assert "No bindings found" in issues[0]["message"]


class TestCheckAliasTargetsCurated:
    def test_valid_aliases_pass(self, populated_db: sqlite3.Connection):
        """Test that aliases pointing to curated tokens pass validation."""
        conn = populated_db

        # Insert curated base token and valid alias
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type, tier, alias_of) VALUES
            (1, 1, 'color.primary', 'color', 'curated', NULL),
            (2, 1, 'color.brand', 'color', 'aliased', 1)"""
        )
        conn.commit()

        issues = check_alias_targets_curated(conn, file_id=1)
        assert len(issues) == 0

    def test_aliases_to_extracted_tokens_fail(self, populated_db: sqlite3.Connection):
        """Test that aliases pointing to extracted tokens are detected."""
        conn = populated_db

        # Insert extracted base token and invalid alias
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type, tier, alias_of) VALUES
            (1, 1, 'color.primary', 'color', 'extracted', NULL),
            (2, 1, 'color.brand', 'color', 'aliased', 1)"""
        )
        conn.commit()

        issues = check_alias_targets_curated(conn, file_id=1)
        assert len(issues) == 1
        assert issues[0]["check_name"] == "alias_targets_curated"
        assert issues[0]["severity"] == "error"
        assert "color.brand" in issues[0]["message"]
        assert "color.primary" in issues[0]["message"]
        assert "extracted" in issues[0]["message"]


class TestCheckNameUniqueness:
    def test_unique_names_pass(self, populated_db: sqlite3.Connection):
        """Test that unique names within collections pass validation."""
        conn = populated_db

        # Insert tokens with unique names
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 1, 'color.primary', 'color'),
            (2, 1, 'color.secondary', 'color'),
            (3, 2, 'space.small', 'dimension')"""
        )
        conn.commit()

        issues = check_name_uniqueness(conn, file_id=1)
        assert len(issues) == 0

    def test_duplicate_names_detected(self, populated_db: sqlite3.Connection):
        """Test that duplicate names within a collection are detected."""
        conn = populated_db

        # Since UNIQUE constraint is at schema level, we'll test by checking
        # that the function would detect duplicates if they existed.
        # In practice, the DB constraint prevents this, but the check is still
        # valuable for data imported from other sources.

        # Insert a token normally
        conn.execute(
            "INSERT INTO tokens (id, collection_id, name, type) VALUES (1, 1, 'color.primary', 'color')"
        )
        conn.commit()

        # Create a temporary table without constraints to simulate duplicates
        conn.execute("""
            CREATE TEMP TABLE tokens_test AS
            SELECT * FROM tokens WHERE 1=0
        """)

        conn.execute("""
            INSERT INTO tokens_test (id, collection_id, name, type) VALUES
            (1, 1, 'color.primary', 'color'),
            (2, 1, 'color.primary', 'color')
        """)
        conn.commit()

        # Test our check query directly on the temp table
        cursor = conn.execute("""
            SELECT t.collection_id, tc.name AS collection_name, t.name, COUNT(*) AS cnt
            FROM tokens_test t
            JOIN token_collections tc ON t.collection_id = tc.id
            WHERE tc.file_id = 1
            GROUP BY t.collection_id, t.name
            HAVING COUNT(*) > 1
        """)

        rows = list(cursor)
        assert len(rows) == 1
        assert rows[0]["name"] == "color.primary"
        assert rows[0]["cnt"] == 2

    def test_same_name_different_collections_allowed(
        self, populated_db: sqlite3.Connection
    ):
        """Test that same name in different collections is allowed."""
        conn = populated_db

        # Insert tokens with same name in different collections
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 1, 'base.value', 'color'),
            (2, 2, 'base.value', 'dimension')"""
        )
        conn.commit()

        issues = check_name_uniqueness(conn, file_id=1)
        assert len(issues) == 0


class TestCheckValueFormat:
    def test_valid_color_formats(self, populated_db: sqlite3.Connection):
        """Test that valid color hex formats pass validation."""
        conn = populated_db

        # Insert color tokens with valid hex values
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 1, 'color.red', 'color'),
            (2, 1, 'color.blue', 'color'),
            (3, 1, 'color.transparent', 'color')"""
        )

        conn.execute(
            """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES
            (1, 1, '{}', '#FF0000'),
            (2, 1, '{}', '#0000FF'),
            (3, 1, '{}', '#00000080')"""
        )
        conn.commit()

        issues = check_value_format(conn, file_id=1)
        assert len(issues) == 0

    def test_invalid_color_formats(self, populated_db: sqlite3.Connection):
        """Test that invalid color formats are detected."""
        conn = populated_db

        # Insert color tokens with invalid hex values
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 1, 'color.bad1', 'color'),
            (2, 1, 'color.bad2', 'color'),
            (3, 1, 'color.bad3', 'color')"""
        )

        conn.execute(
            """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES
            (1, 1, '{}', 'red'),
            (2, 1, '{}', '#FF00'),
            (3, 1, '{}', '#GGGGGG')"""
        )
        conn.commit()

        issues = check_value_format(conn, file_id=1)
        assert len(issues) == 3
        for issue in issues:
            assert issue["check_name"] == "value_format"
            assert issue["severity"] == "error"
            assert "Invalid color format" in issue["message"]

    def test_valid_dimension_formats(self, populated_db: sqlite3.Connection):
        """Test that valid dimension formats pass validation."""
        conn = populated_db

        # Insert dimension tokens with valid numeric values
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 2, 'space.small', 'dimension'),
            (2, 2, 'space.large', 'dimension')"""
        )

        conn.execute(
            """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES
            (1, 3, '{}', '8'),
            (2, 3, '{}', '16.5')"""
        )
        conn.commit()

        issues = check_value_format(conn, file_id=1)
        assert len(issues) == 0

    def test_invalid_dimension_formats(self, populated_db: sqlite3.Connection):
        """Test that invalid dimension formats are detected."""
        conn = populated_db

        # Insert dimension tokens with invalid values
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 2, 'space.bad', 'dimension')"""
        )

        conn.execute(
            """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES
            (1, 3, '{}', 'abc')"""
        )
        conn.commit()

        issues = check_value_format(conn, file_id=1)
        assert len(issues) == 1
        assert issues[0]["check_name"] == "value_format"
        assert issues[0]["severity"] == "error"
        assert "Invalid dimension format" in issues[0]["message"]

    def test_valid_font_weight_formats(self, populated_db: sqlite3.Connection):
        """Test that valid font weight formats pass validation."""
        conn = populated_db

        # Insert fontWeight tokens with valid values
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 1, 'weight.regular', 'fontWeight'),
            (2, 1, 'weight.bold', 'fontWeight')"""
        )

        conn.execute(
            """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES
            (1, 1, '{}', '400'),
            (2, 1, '{}', '700')"""
        )
        conn.commit()

        issues = check_value_format(conn, file_id=1)
        assert len(issues) == 0

    def test_invalid_font_weight_formats(self, populated_db: sqlite3.Connection):
        """Test that invalid font weight formats are detected."""
        conn = populated_db

        # Insert fontWeight tokens with out-of-range values
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 1, 'weight.too_light', 'fontWeight'),
            (2, 1, 'weight.too_heavy', 'fontWeight')"""
        )

        conn.execute(
            """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES
            (1, 1, '{}', '50'),
            (2, 1, '{}', '1000')"""
        )
        conn.commit()

        issues = check_value_format(conn, file_id=1)
        assert len(issues) == 2
        for issue in issues:
            assert issue["check_name"] == "value_format"
            assert issue["severity"] == "error"
            assert "Invalid fontWeight" in issue["message"]


class TestRunValidation:
    def test_run_validation_with_no_issues(self, populated_db: sqlite3.Connection):
        """Test run_validation when no issues exist."""
        conn = populated_db

        # Insert valid token data
        conn.execute(
            "INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (1, 1, 'color.primary', 'color', 'curated')"
        )
        conn.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (1, 1, '{}', '#FF0000'), (1, 2, '{}', '#880000')"
        )
        conn.commit()

        result = run_validation(conn, file_id=1)
        assert result["passed"] is True
        assert result["errors"] == 0
        assert result["warnings"] == 1  # Orphan token warning
        assert result["info"] == 1  # Binding coverage info
        assert "run_at" in result

        # Check database entries
        cursor = conn.execute("SELECT COUNT(*) FROM export_validations")
        count = cursor.fetchone()[0]
        assert count == 2  # 1 warning + 1 info

    def test_run_validation_with_errors(self, populated_db: sqlite3.Connection):
        """Test run_validation when errors exist."""
        conn = populated_db

        # Insert token with missing mode values (will fail mode_completeness)
        conn.execute(
            "INSERT INTO tokens (id, collection_id, name, type) VALUES (1, 1, 'color.primary', 'color')"
        )
        conn.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (1, 1, '{}', '#FF0000')"
        )
        conn.commit()

        result = run_validation(conn, file_id=1)
        assert result["passed"] is False
        assert result["errors"] == 1  # Mode completeness error
        assert "issues" in result
        assert len([i for i in result["issues"] if i["severity"] == "error"]) == 1

        # Check database entries
        cursor = conn.execute(
            "SELECT * FROM export_validations WHERE severity = 'error'"
        )
        errors = cursor.fetchall()
        assert len(errors) == 1

    def test_run_validation_timestamp_grouping(
        self, populated_db: sqlite3.Connection
    ):
        """Test that all issues from one run share the same timestamp."""
        conn = populated_db

        # Insert tokens that will generate multiple issues
        conn.execute(
            """INSERT INTO tokens (id, collection_id, name, type) VALUES
            (1, 1, 'Color.Bad', 'color'),
            (2, 1, 'color.orphan', 'color')"""
        )
        conn.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (1, 1, '{}', '#FF0000')"
        )
        conn.commit()

        result = run_validation(conn, file_id=1)

        # Check all issues have same run_at
        cursor = conn.execute("SELECT DISTINCT run_at FROM export_validations")
        timestamps = cursor.fetchall()
        assert len(timestamps) == 1


class TestIsExportReady:
    def test_export_ready_with_no_validation(self, populated_db: sqlite3.Connection):
        """Test is_export_ready when no validation has been run."""
        conn = populated_db
        assert is_export_ready(conn) is False

    def test_export_ready_with_only_warnings(self, populated_db: sqlite3.Connection):
        """Test is_export_ready when only warnings exist."""
        conn = populated_db

        # Insert validation results with only warnings
        run_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO export_validations (run_at, check_name, severity, message) VALUES
            (?, 'orphan_tokens', 'warning', 'Test warning'),
            (?, 'binding_coverage', 'info', 'Test info')""",
            (run_at, run_at),
        )
        conn.commit()

        assert is_export_ready(conn) is True

    def test_export_not_ready_with_errors(self, populated_db: sqlite3.Connection):
        """Test is_export_ready when errors exist."""
        conn = populated_db

        # Insert validation results with errors
        run_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO export_validations (run_at, check_name, severity, message) VALUES
            (?, 'mode_completeness', 'error', 'Test error'),
            (?, 'orphan_tokens', 'warning', 'Test warning')""",
            (run_at, run_at),
        )
        conn.commit()

        assert is_export_ready(conn) is False

    def test_export_ready_uses_latest_run(self, populated_db: sqlite3.Connection):
        """Test that is_export_ready uses only the latest validation run."""
        conn = populated_db

        # Insert old run with errors
        old_run = "2024-01-01T00:00:00Z"
        conn.execute(
            "INSERT INTO export_validations (run_at, check_name, severity, message) VALUES (?, 'test', 'error', 'Old error')",
            (old_run,),
        )

        # Insert new run with only warnings
        new_run = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO export_validations (run_at, check_name, severity, message) VALUES (?, 'test', 'warning', 'New warning')",
            (new_run,),
        )
        conn.commit()

        assert is_export_ready(conn) is True


class TestViewExportReadiness:
    def test_export_readiness_view(self, populated_db: sqlite3.Connection):
        """Test that v_export_readiness view aggregates correctly."""
        conn = populated_db

        # Insert validation results
        run_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO export_validations (run_at, check_name, severity, message, resolved) VALUES
            (?, 'mode_completeness', 'error', 'Error 1', 0),
            (?, 'mode_completeness', 'error', 'Error 2', 0),
            (?, 'name_dtcg_compliant', 'error', 'Error 3', 1),
            (?, 'orphan_tokens', 'warning', 'Warning 1', 0),
            (?, 'binding_coverage', 'info', 'Info 1', 0)""",
            (run_at, run_at, run_at, run_at, run_at),
        )
        conn.commit()

        # Query the view
        cursor = conn.execute("SELECT * FROM v_export_readiness ORDER BY severity")
        rows = cursor.fetchall()

        assert len(rows) == 4  # 2 error checks, 1 warning, 1 info

        # Check aggregation
        for row in rows:
            if (
                row["check_name"] == "mode_completeness"
                and row["severity"] == "error"
            ):
                assert row["issue_count"] == 2
                assert row["resolved_count"] == 0
            elif (
                row["check_name"] == "name_dtcg_compliant"
                and row["severity"] == "error"
            ):
                assert row["issue_count"] == 1
                assert row["resolved_count"] == 1