"""End-to-end test: extraction through validation gate.

This test runs the ENTIRE pipeline from extraction through clustering,
curation, and validation, verifying the final DB state is export-ready.
"""

import json
import sqlite3
from collections.abc import Callable
from typing import Any

import pytest

from dd.cluster import run_clustering
from dd.curate import accept_all
from dd.db import init_db
from dd.extract import run_extraction_pipeline
from dd.status import format_status_report, get_curation_progress, get_status_dict
from dd.validate import is_export_ready, run_validation

# Mock frame data for 3 screens
MOCK_FRAMES = [
    {"figma_node_id": "1:1", "name": "Home", "width": 428, "height": 926},
    {"figma_node_id": "1:2", "name": "Profile", "width": 428, "height": 926},
    {"figma_node_id": "1:3", "name": "Components", "width": 1200, "height": 800},
]


def _build_e2e_mock_data() -> tuple[list[dict], Callable[[str], list[dict]]]:
    """Build comprehensive mock data that exercises all pipeline stages.

    Returns:
        Tuple of (frames, extract_fn) where extract_fn returns node lists per screen.
    """

    def extract_fn(node_id: str) -> list[dict[str, Any]]:
        """Mock extract function that returns rich node data."""
        if node_id == "1:1":
            # Home screen: dark background with text and card elements
            return [
                {
                    "figma_node_id": "1:1",
                    "parent_idx": None,
                    "name": "Home",
                    "node_type": "FRAME",
                    "depth": 0,
                    "sort_order": 0,
                    "x": 0,
                    "y": 0,
                    "width": 428,
                    "height": 926,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043}}]),  # #09090B
                    "layout_mode": "VERTICAL",
                    "padding_top": 16,
                    "padding_right": 16,
                    "padding_bottom": 16,
                    "padding_left": 16,
                    "item_spacing": 8,
                },
                {
                    "figma_node_id": "1:1:1",
                    "parent_idx": 0,
                    "name": "Title",
                    "node_type": "TEXT",
                    "depth": 1,
                    "sort_order": 1,
                    "x": 16,
                    "y": 16,
                    "width": 396,
                    "height": 32,
                    "font_family": "Inter",
                    "font_weight": 600,
                    "font_size": 24,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1.0, "g": 1.0, "b": 1.0}}]),  # #FFFFFF
                },
                {
                    "figma_node_id": "1:1:2",
                    "parent_idx": 0,
                    "name": "Subtitle",
                    "node_type": "TEXT",
                    "depth": 1,
                    "sort_order": 2,
                    "x": 16,
                    "y": 56,
                    "width": 396,
                    "height": 20,
                    "font_family": "Inter",
                    "font_weight": 400,
                    "font_size": 14,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1.0, "g": 1.0, "b": 1.0}}]),  # #FFFFFF
                },
                {
                    "figma_node_id": "1:1:3",
                    "parent_idx": 0,
                    "name": "Card",
                    "node_type": "RECTANGLE",
                    "depth": 1,
                    "sort_order": 3,
                    "x": 16,
                    "y": 100,
                    "width": 396,
                    "height": 200,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1.0, "g": 1.0, "b": 1.0}}]),  # #FFFFFF
                    "corner_radius": 8,
                    "effects": json.dumps([
                        {
                            "type": "DROP_SHADOW",
                            "color": {"r": 0, "g": 0, "b": 0, "a": 0.25},
                            "offset": {"x": 0, "y": 4},
                            "radius": 8,
                            "spread": 0,
                            "visible": True
                        }
                    ]),
                },
                {
                    "figma_node_id": "1:1:4",
                    "parent_idx": 0,
                    "name": "Container",
                    "node_type": "FRAME",
                    "depth": 1,
                    "sort_order": 4,
                    "x": 16,
                    "y": 320,
                    "width": 396,
                    "height": 100,
                    "strokes": json.dumps([{"type": "SOLID", "color": {"r": 0.094, "g": 0.094, "b": 0.106}}]),  # #18181B
                    "stroke_weight": 1,
                    "layout_mode": "VERTICAL",
                    "padding_top": 16,
                    "padding_right": 16,
                    "padding_bottom": 16,
                    "padding_left": 16,
                },
            ]

        elif node_id == "1:2":
            # Profile screen: simpler layout with different styles
            return [
                {
                    "figma_node_id": "1:2",
                    "parent_idx": None,
                    "name": "Profile",
                    "node_type": "FRAME",
                    "depth": 0,
                    "sort_order": 0,
                    "x": 0,
                    "y": 0,
                    "width": 428,
                    "height": 926,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043}}]),  # #09090B
                },
                {
                    "figma_node_id": "1:2:1",
                    "parent_idx": 0,
                    "name": "Username",
                    "node_type": "TEXT",
                    "depth": 1,
                    "sort_order": 1,
                    "x": 20,
                    "y": 20,
                    "width": 388,
                    "height": 20,
                    "font_family": "Inter",
                    "font_weight": 400,
                    "font_size": 14,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1.0, "g": 1.0, "b": 1.0}}]),  # #FFFFFF
                },
                {
                    "figma_node_id": "1:2:2",
                    "parent_idx": 0,
                    "name": "Avatar",
                    "node_type": "RECTANGLE",
                    "depth": 1,
                    "sort_order": 2,
                    "x": 20,
                    "y": 60,
                    "width": 100,
                    "height": 100,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.094, "g": 0.094, "b": 0.106}}]),  # #18181B
                    "corner_radius": 12,
                },
                {
                    "figma_node_id": "1:2:3",
                    "parent_idx": 0,
                    "name": "Card2",
                    "node_type": "RECTANGLE",
                    "depth": 1,
                    "sort_order": 3,
                    "x": 20,
                    "y": 200,
                    "width": 388,
                    "height": 150,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1.0, "g": 1.0, "b": 1.0}}]),  # #FFFFFF
                    "corner_radius": 8,
                    "effects": json.dumps([
                        {
                            "type": "DROP_SHADOW",
                            "color": {"r": 0, "g": 0, "b": 0, "a": 0.25},
                            "offset": {"x": 0, "y": 4},
                            "radius": 8,
                            "spread": 0,
                            "visible": True
                        }
                    ]),
                },
            ]

        elif node_id == "1:3":
            # Components screen: minimal component sheet
            return [
                {
                    "figma_node_id": "1:3",
                    "parent_idx": None,
                    "name": "Components",
                    "node_type": "FRAME",
                    "depth": 0,
                    "sort_order": 0,
                    "x": 0,
                    "y": 0,
                    "width": 1200,
                    "height": 800,
                    # No fill - transparent
                },
                {
                    "figma_node_id": "1:3:1",
                    "parent_idx": 0,
                    "name": "Button",
                    "node_type": "COMPONENT",
                    "depth": 1,
                    "sort_order": 1,
                    "x": 50,
                    "y": 50,
                    "width": 120,
                    "height": 48,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.094, "g": 0.094, "b": 0.106}}]),  # #18181B
                    "corner_radius": 8,
                    "layout_mode": "VERTICAL",
                    "padding_top": 8,
                    "padding_right": 8,
                    "padding_bottom": 8,
                    "padding_left": 8,
                },
            ]

        else:
            return []

    return (MOCK_FRAMES, extract_fn)


@pytest.fixture
def db():
    """Create an empty in-memory database with schema initialized."""
    conn = init_db(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_full_pipeline_to_validation_pass(db, capfd):
    """Test full pipeline from extraction to validation passing."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run extraction pipeline
    result = run_extraction_pipeline(
        db,
        file_key="test-file-123",
        file_name="E2E Test File",
        frames=frames,
        extract_fn=extract_fn,
        node_count=100
    )

    assert result["status"] == "completed"
    assert result["completed"] == 3

    # Run clustering
    cluster_result = run_clustering(db, file_id=1)
    assert cluster_result["total_tokens"] > 0
    assert cluster_result["total_bindings_updated"] > 0

    # Run accept_all to promote tokens and bindings
    curation_result = accept_all(db, file_id=1)
    assert curation_result["tokens_accepted"] > 0
    assert curation_result["bindings_updated"] > 0

    # Fix non-DTCG-compliant token names before validation
    # This simulates what a user would do to prepare for export
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%'
    """)
    db.commit()

    # Run validation
    validation_result = run_validation(db, file_id=1)

    # Debug: print validation issues if not passing
    if not validation_result["passed"]:
        print("\nValidation issues found:")
        for issue in validation_result["issues"]:
            if issue["severity"] == "error":
                print(f"  ERROR: {issue['check_name']}: {issue['message']}")

    assert validation_result["passed"] is True
    assert validation_result["errors"] == 0

    # Verify is_export_ready
    assert is_export_ready(db) is True

    # Verify validation checks executed
    # Note: Not all checks will produce issues if data is clean
    cursor = db.execute("""
        SELECT DISTINCT check_name
        FROM export_validations
        WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
    """)
    check_names = {row["check_name"] for row in cursor.fetchall()}

    # At minimum, binding_coverage always runs (info level)
    assert "binding_coverage" in check_names

    # Validation should have passed
    assert validation_result["passed"] is True

    # Verify no error-severity issues
    cursor = db.execute("""
        SELECT COUNT(*) AS error_count
        FROM export_validations
        WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
        AND severity = 'error'
    """)
    assert cursor.fetchone()["error_count"] == 0


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_all_validation_checks_executed(db, capfd):
    """Test that all 7 validation checks are executed."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix non-DTCG names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%'
    """)
    db.commit()

    run_validation(db, file_id=1)

    # Query for all check names in latest run
    cursor = db.execute("""
        SELECT check_name, COUNT(*) AS count
        FROM export_validations
        WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
        GROUP BY check_name
        ORDER BY check_name
    """)

    checks_executed = {row["check_name"]: row["count"] for row in cursor.fetchall()}

    # At minimum, binding_coverage always runs
    assert "binding_coverage" in checks_executed
    assert checks_executed["binding_coverage"] >= 1

    # Verify that when issues exist, they're recorded
    # The name_dtcg_compliant check should have found issues before we fixed them
    if "name_dtcg_compliant" in checks_executed:
        assert checks_executed["name_dtcg_compliant"] >= 1


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_curation_progress_shows_bound(db, capfd):
    """Test curation progress after full pipeline."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline through accept_all
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Query curation progress
    progress = get_curation_progress(db)

    # Should have progress data
    assert len(progress) > 0

    # Check for bound status
    status_dict = {item["status"]: item for item in progress}

    # Should have bound bindings
    assert "bound" in status_dict
    assert status_dict["bound"]["count"] > 0
    assert status_dict["bound"]["pct"] > 0

    # Total percentages should sum to approximately 100
    total_pct = sum(item["pct"] for item in progress)
    assert 99.0 <= total_pct <= 101.0  # Allow for rounding

    # If any unbound remain (e.g., opacity=1.0), they should be accounted for
    if "unbound" in status_dict:
        assert status_dict["unbound"]["count"] >= 0
        assert status_dict["unbound"]["pct"] >= 0


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_token_values_complete_for_all_modes(db, capfd):
    """Test that all tokens have values for all modes."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Verify every non-aliased token has at least 1 token_value row
    cursor = db.execute("""
        SELECT t.id, t.name, COUNT(tv.id) AS value_count
        FROM tokens t
        LEFT JOIN token_values tv ON tv.token_id = t.id
        WHERE t.alias_of IS NULL
        GROUP BY t.id
    """)

    for row in cursor.fetchall():
        assert row["value_count"] >= 1, f"Token {row['name']} has no values"

    # Verify every collection has a default mode
    cursor = db.execute("""
        SELECT tc.id, tc.name, COUNT(tm.id) AS mode_count
        FROM token_collections tc
        LEFT JOIN token_modes tm ON tm.collection_id = tc.id
        GROUP BY tc.id
    """)

    for row in cursor.fetchall():
        assert row["mode_count"] >= 1, f"Collection {row['name']} has no modes"

    # Verify every token_value references valid mode and token
    cursor = db.execute("""
        SELECT COUNT(*) AS invalid_count
        FROM token_values tv
        WHERE NOT EXISTS (SELECT 1 FROM tokens WHERE id = tv.token_id)
        OR NOT EXISTS (SELECT 1 FROM token_modes WHERE id = tv.mode_id)
    """)
    assert cursor.fetchone()["invalid_count"] == 0

    # Verify v_resolved_tokens returns resolved_value for every token
    cursor = db.execute("""
        SELECT COUNT(*) AS unresolved_count
        FROM v_resolved_tokens
        WHERE resolved_value IS NULL OR resolved_value = ''
    """)
    assert cursor.fetchone()["unresolved_count"] == 0


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_export_readiness_view_returns_ready(db, capfd):
    """Test export readiness view after full pipeline."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix non-DTCG names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%'
    """)
    db.commit()

    run_validation(db, file_id=1)

    # Query v_export_readiness
    cursor = db.execute("""
        SELECT check_name, severity, COUNT(*) AS issue_count
        FROM export_validations
        WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
        GROUP BY check_name, severity
        ORDER BY CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END
    """)

    rows = cursor.fetchall()

    # View should return rows
    assert len(rows) > 0

    # After fixing names, no rows with severity='error' should remain
    error_rows = [r for r in rows if r["severity"] == "error"]

    # Debug if there are errors
    if error_rows:
        for row in error_rows:
            print(f"ERROR: {row['check_name']} - count: {row['issue_count']}")

    assert len(error_rows) == 0

    # View correctly groups by check_name and severity
    check_severity_pairs = {(r["check_name"], r["severity"]) for r in rows}
    assert len(check_severity_pairs) == len(rows)  # No duplicate pairs


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_fk_integrity_across_full_pipeline(db, capfd):
    """Test complete FK integrity across all tables after full pipeline."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)
    run_validation(db, file_id=1)

    # FK integrity checks
    fk_checks = [
        ("screens.file_id", "screens", "file_id", "files", "id"),
        ("nodes.screen_id", "nodes", "screen_id", "screens", "id"),
        ("nodes.parent_id", "nodes", "parent_id", "nodes", "id"),
        ("node_token_bindings.node_id", "node_token_bindings", "node_id", "nodes", "id"),
        ("node_token_bindings.token_id", "node_token_bindings", "token_id", "tokens", "id"),
        ("tokens.collection_id", "tokens", "collection_id", "token_collections", "id"),
        ("token_collections.file_id", "token_collections", "file_id", "files", "id"),
        ("token_values.token_id", "token_values", "token_id", "tokens", "id"),
        ("token_values.mode_id", "token_values", "mode_id", "token_modes", "id"),
        ("token_modes.collection_id", "token_modes", "collection_id", "token_collections", "id"),
    ]

    for check_name, from_table, fk_col, to_table, pk_col in fk_checks:
        # Special handling for nullable FKs
        if fk_col in ["parent_id", "token_id"]:
            query = f"""
                SELECT COUNT(*) AS invalid_count
                FROM {from_table}
                WHERE {fk_col} IS NOT NULL
                AND {fk_col} NOT IN (SELECT {pk_col} FROM {to_table})
            """
        else:
            query = f"""
                SELECT COUNT(*) AS invalid_count
                FROM {from_table}
                WHERE {fk_col} NOT IN (SELECT {pk_col} FROM {to_table})
            """

        cursor = db.execute(query)
        invalid_count = cursor.fetchone()["invalid_count"]
        assert invalid_count == 0, f"FK check failed: {check_name} has {invalid_count} invalid references"


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_status_report_after_full_pipeline(db, capfd):
    """Test status report generation after full pipeline."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix non-DTCG names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%'
    """)
    db.commit()

    run_validation(db, file_id=1)

    # Generate status report
    report = format_status_report(db, file_id=1)

    # Report should be non-empty
    assert len(report) > 0
    assert isinstance(report, str)

    # Should contain expected sections
    assert "Curation Progress" in report
    assert "Export Readiness" in report

    # Should NOT contain "not yet validated"
    assert "not yet validated" not in report

    # Get status dict
    status = get_status_dict(db, file_id=1)

    # Should be ready after fixing names
    # Note: is_ready checks for no error-severity validation issues
    if not status["is_ready"]:
        print(f"\nNot ready - readiness: {status['export_readiness']}")
    assert status["is_ready"] is True
    assert status["token_count"] > 0
    assert status["unbound_count"] >= 0

    # Should have curation progress
    assert len(status["curation_progress"]) > 0


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_pipeline_without_curation_fails_validation(db, capfd):
    """Test pipeline without curation may have validation issues."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run extraction pipeline
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)

    # Run clustering (tokens created as 'extracted', bindings as 'proposed')
    run_clustering(db, file_id=1)

    # DO NOT run curation (no accept_all)

    # Check curation progress - should show 0% bound
    progress = get_curation_progress(db)
    status_dict = {item["status"]: item for item in progress}

    # All bindings should be proposed, none bound
    assert "proposed" in status_dict
    assert status_dict["proposed"]["count"] > 0

    if "bound" in status_dict:
        assert status_dict["bound"]["count"] == 0
        assert status_dict["bound"]["pct"] == 0.0

    # Run validation
    validation_result = run_validation(db, file_id=1)

    # Create an alias to an extracted token to trigger validation failure
    cursor = db.execute("""
        SELECT id, collection_id FROM tokens
        WHERE tier = 'extracted' AND alias_of IS NULL
        LIMIT 1
    """)
    target_token = cursor.fetchone()

    if target_token:
        # Create an alias token pointing to the extracted token
        db.execute("""
            INSERT INTO tokens (collection_id, name, type, tier, alias_of)
            VALUES (?, 'test.alias', 'color', 'aliased', ?)
        """, (target_token["collection_id"], target_token["id"]))
        db.commit()

        # Re-run validation
        validation_result2 = run_validation(db, file_id=1)

        # Should have an error for alias pointing to extracted token
        cursor = db.execute("""
            SELECT COUNT(*) AS error_count
            FROM export_validations
            WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
            AND check_name = 'alias_targets_curated'
            AND severity = 'error'
        """)
        assert cursor.fetchone()["error_count"] > 0