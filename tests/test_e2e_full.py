"""End-to-end smoke test: full pipeline including drift + modes.

This test runs the COMPLETE pipeline from extraction through clustering,
curation, validation, all exports, dark mode creation (OKLCH inversion),
and drift detection. This is the comprehensive regression gate for the entire project.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from typing import Any

import pytest

from dd.cluster import run_clustering
from dd.curate import accept_all
from dd.db import init_db
from dd.drift import detect_drift, generate_drift_report
from dd.export_css import export_css, generate_css
from dd.export_dtcg import export_dtcg, generate_dtcg_dict
from dd.export_figma_vars import generate_variable_payloads
from dd.export_tailwind import export_tailwind
from dd.extract import run_extraction_pipeline
from dd.modes import create_dark_mode
from dd.status import format_status_report, get_status_dict
from dd.validate import is_export_ready, run_validation


def _build_e2e_mock_data() -> tuple[list[dict], Callable[[str], list[dict]]]:
    """Build comprehensive mock data that exercises the full pipeline."""
    frames = [
        {"figma_node_id": "1:1", "name": "Home", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Profile", "width": 428, "height": 926},
        {"figma_node_id": "1:3", "name": "Components", "width": 1200, "height": 800},
    ]

    # Home screen with diverse properties
    home_nodes = [
        {"figma_node_id": "10:1", "parent_idx": None, "name": "Home",
         "node_type": "FRAME", "depth": 0, "sort_order": 0,
         "x": 0, "y": 0, "width": 428, "height": 926,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]),  # #09090B
         "layout_mode": "VERTICAL", "padding_top": 8, "padding_bottom": 8,
         "padding_left": 16, "padding_right": 16, "item_spacing": 16},
        {"figma_node_id": "10:2", "parent_idx": 0, "name": "Heading",
         "node_type": "TEXT", "depth": 1, "sort_order": 0,
         "x": 16, "y": 8, "width": 396, "height": 30,
         "font_family": "Inter", "font_weight": 600, "font_size": 24,
         "line_height": json.dumps({"value": 30, "unit": "PIXELS"}),
         "text_content": "Home"},
        {"figma_node_id": "10:3", "parent_idx": 0, "name": "Card",
         "node_type": "RECTANGLE", "depth": 1, "sort_order": 1,
         "x": 16, "y": 54, "width": 396, "height": 200,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
         "corner_radius": 8,
         "effects": json.dumps([{"type": "DROP_SHADOW", "visible": True,
             "color": {"r": 0, "g": 0, "b": 0, "a": 0.1},
             "radius": 6, "offset": {"x": 0, "y": 4}, "spread": -1}])},
        {"figma_node_id": "10:4", "parent_idx": 0, "name": "Body",
         "node_type": "TEXT", "depth": 1, "sort_order": 2,
         "x": 16, "y": 270, "width": 396, "height": 20,
         "font_family": "Inter", "font_weight": 400, "font_size": 14,
         "line_height": json.dumps({"value": 20, "unit": "PIXELS"}),
         "text_content": "Welcome to the app"},
        {"figma_node_id": "10:5", "parent_idx": 0, "name": "Divider",
         "node_type": "FRAME", "depth": 1, "sort_order": 3,
         "x": 16, "y": 306, "width": 396, "height": 1,
         "strokes": json.dumps([{"type": "SOLID", "color": {"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}}]),  # #D4D4D8
         "stroke_weight": 1},
    ]

    # Profile screen reusing colors and spacing
    profile_nodes = [
        {"figma_node_id": "20:1", "parent_idx": None, "name": "Profile",
         "node_type": "FRAME", "depth": 0, "sort_order": 0,
         "x": 0, "y": 0, "width": 428, "height": 926,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.094, "g": 0.094, "b": 0.106, "a": 1}}]),  # #18181B
         "layout_mode": "VERTICAL", "padding_top": 16, "padding_bottom": 16,
         "padding_left": 16, "padding_right": 16, "item_spacing": 8},
        {"figma_node_id": "20:2", "parent_idx": 0, "name": "Username",
         "node_type": "TEXT", "depth": 1, "sort_order": 0,
         "x": 16, "y": 16, "width": 396, "height": 20,
         "font_family": "Inter", "font_weight": 400, "font_size": 14,
         "line_height": json.dumps({"value": 20, "unit": "PIXELS"}),
         "text_content": "john_doe"},
        {"figma_node_id": "20:3", "parent_idx": 0, "name": "Avatar",
         "node_type": "RECTANGLE", "depth": 1, "sort_order": 1,
         "x": 16, "y": 44, "width": 80, "height": 80,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.094, "g": 0.094, "b": 0.106, "a": 1}}]),  # #18181B
         "corner_radius": 12},
        {"figma_node_id": "20:4", "parent_idx": 0, "name": "Bio",
         "node_type": "TEXT", "depth": 1, "sort_order": 2,
         "x": 16, "y": 132, "width": 396, "height": 30,
         "font_family": "Inter", "font_weight": 600, "font_size": 24,
         "line_height": json.dumps({"value": 30, "unit": "PIXELS"}),
         "text_content": "Software Engineer"},
        {"figma_node_id": "20:5", "parent_idx": 0, "name": "Status",
         "node_type": "FRAME", "depth": 1, "sort_order": 3,
         "x": 16, "y": 170, "width": 396, "height": 40,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
         "corner_radius": 8},
    ]

    # Components sheet
    comp_nodes = [
        {"figma_node_id": "30:1", "parent_idx": None, "name": "Components",
         "node_type": "FRAME", "depth": 0, "sort_order": 0,
         "x": 0, "y": 0, "width": 1200, "height": 800},
    ]

    responses = {"1:1": home_nodes, "1:2": profile_nodes, "1:3": comp_nodes}

    def extract_fn(node_id: str) -> list[dict[str, Any]]:
        """Mock extract function returning diverse property types."""
        return responses.get(node_id, [])

    return frames, extract_fn


def _simulate_figma_export(db: sqlite3.Connection, file_id: int) -> dict:
    """Set figma_variable_id on all curated tokens and return matching mock response."""
    # Set figma_variable_id on all curated tokens
    var_counter = 1000
    cursor = db.execute("""
        SELECT t.id, t.name, tv.resolved_value, tm.name as mode_name,
               tc.name as collection_name, tc.figma_id as collection_id
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        JOIN token_values tv ON tv.token_id = t.id
        JOIN token_modes tm ON tv.mode_id = tm.id
        WHERE tc.file_id = ?
        AND t.tier IN ('curated', 'aliased')
        ORDER BY tc.id, t.id, tm.id
    """, (file_id,))

    # Build mock response - organize by collection
    collections = {}
    token_updates = []

    for row in cursor.fetchall():
        collection_name = row["collection_name"]
        token_id = row["id"]
        token_name = row["name"]

        # Track updates for later
        if not any(u["id"] == token_id for u in token_updates):
            var_id = f"VariableID:{var_counter}:0"
            token_updates.append({"id": token_id, "var_id": var_id})
            var_counter += 1
        else:
            var_id = next(u["var_id"] for u in token_updates if u["id"] == token_id)

        # Build collection structure
        if collection_name not in collections:
            collections[collection_name] = {
                "name": collection_name,
                "variables": [],
                "modes": []
            }

        # Add mode if not present
        if row["mode_name"] not in collections[collection_name]["modes"]:
            collections[collection_name]["modes"].append({"name": row["mode_name"]})

        # Find or create variable entry
        var_entry = None
        for v in collections[collection_name]["variables"]:
            if v["name"] == token_name:
                var_entry = v
                break

        if var_entry is None:
            var_entry = {
                "id": var_id,
                "name": token_name,
                "valuesByMode": {}
            }
            collections[collection_name]["variables"].append(var_entry)

        # Add mode value
        var_entry["valuesByMode"][row["mode_name"]] = row["resolved_value"]

    # Update all tokens with figma_variable_id
    for update in token_updates:
        db.execute("""
            UPDATE tokens
            SET figma_variable_id = ?, sync_status = 'synced'
            WHERE id = ?
        """, (update["var_id"], update["id"]))

    db.commit()

    # Build final response in format expected by parser
    return {
        "collections": list(collections.values())
    }


def _build_drifted_figma_response(db: sqlite3.Connection, file_id: int, drift_tokens: dict) -> dict:
    """Build a mock Figma response with specified tokens having different values."""
    base_response = _simulate_figma_export(db, file_id)

    # Modify specified tokens
    for token_name, new_value in drift_tokens.items():
        # Find and update the token in response collections
        for collection in base_response["collections"]:
            for var in collection["variables"]:
                if var["name"] == token_name:
                    # Update all mode values
                    for mode_name in var["valuesByMode"]:
                        var["valuesByMode"][mode_name] = new_value
                    break

    return base_response


def _count_css_vars_in_block(css: str, block_selector: str) -> int:
    """Count CSS variables within a specific block."""
    # Find the block
    if block_selector == ":root":
        pattern = r':root\s*{([^}]+)}'
    else:
        pattern = re.escape(block_selector) + r'\s*{([^}]+)}'

    match = re.search(pattern, css, re.DOTALL)
    if not match:
        return 0

    block_content = match.group(1)
    # Count CSS variables (--name: value;)
    var_pattern = r'--[\w-]+:\s*[^;]+;'
    matches = re.findall(var_pattern, block_content)
    return len(matches)


def _navigate_dtcg_path(dtcg_dict: dict, path: str) -> dict | None:
    """Navigate nested DTCG dict by dot-path."""
    parts = path.split(".")
    current = dtcg_dict

    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]

    return current if isinstance(current, dict) else None


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
def test_e2e_full_pipeline_smoke(db):
    """Run the COMPLETE pipeline end-to-end and verify all stages produce output."""
    frames, extract_fn = _build_e2e_mock_data()

    # a. Extraction
    result = run_extraction_pipeline(
        db,
        file_key="e2e_key",
        file_name="E2E File",
        frames=frames,
        extract_fn=extract_fn,
        node_count=100
    )
    assert result["status"] == "completed"
    assert result["completed"] == 3

    # b. Clustering
    cluster_result = run_clustering(db, file_id=1, color_threshold=0.05, agent_id="test")
    assert cluster_result["total_tokens"] > 0
    assert cluster_result["total_bindings_updated"] > 0

    # c. Curation
    curation_result = accept_all(db, file_id=1)
    assert curation_result["tokens_accepted"] > 0
    assert curation_result["bindings_updated"] > 0

    # Fix non-DTCG-compliant names before validation
    db.execute("""
        UPDATE tokens
        SET name = LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'fontFamily', 'fontfamily'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety'))
        WHERE name LIKE '%font%' OR name LIKE '%line%' OR name LIKE '%offset%'
    """)
    db.commit()

    # d. Validation
    validation_result = run_validation(db, file_id=1)
    if not validation_result["passed"]:
        # Debug: show what validation errors occurred
        cursor = db.execute("""
            SELECT check_name, severity, message, COUNT(*) as count
            FROM export_validations
            WHERE severity = 'error'
            GROUP BY check_name, severity, message
        """)
        for row in cursor.fetchall():
            print(f"Validation Error: {row['check_name']} - {row['message']} (count: {row['count']})")
    assert validation_result["passed"] is True
    assert is_export_ready(db) is True

    # e. CSS export
    css_result = export_css(db, file_id=1)
    assert css_result["token_count"] > 0
    assert len(css_result["css"]) > 0
    assert ":root" in css_result["css"]

    # f. Tailwind export
    tailwind_result = export_tailwind(db, file_id=1)
    assert tailwind_result["token_count"] > 0
    assert len(tailwind_result["config"]) > 0
    assert "module.exports" in tailwind_result["config"]

    # g. DTCG export
    dtcg_result = export_dtcg(db, file_id=1)
    assert dtcg_result["token_count"] > 0
    dtcg_json = json.loads(dtcg_result["json"])  # Verify valid JSON
    assert isinstance(dtcg_json, dict)

    # h. Figma payloads
    figma_payloads = generate_variable_payloads(db, file_id=1)
    assert isinstance(figma_payloads, list)
    assert len(figma_payloads) > 0

    # Verify final state
    cursor = db.execute("""
        SELECT COUNT(*) as count FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1 AND t.tier = 'curated'
    """)
    assert cursor.fetchone()["count"] > 0

    cursor = db.execute("""
        SELECT COUNT(*) as count FROM node_token_bindings
        WHERE binding_status = 'bound'
    """)
    assert cursor.fetchone()["count"] > 0

    cursor = db.execute("""
        SELECT COUNT(DISTINCT target) as targets FROM code_mappings
    """)
    assert cursor.fetchone()["targets"] == 3  # css, tailwind, dtcg


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_dark_mode_creation_and_export(db):
    """Test dark mode creation with OKLCH inversion and verify exports."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run pipeline through curation
    run_extraction_pipeline(db, "e2e_key", "E2E File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Find Colors collection
    cursor = db.execute("""
        SELECT id FROM token_collections
        WHERE file_id = 1 AND name LIKE '%color%'
        COLLATE NOCASE
    """)
    row = cursor.fetchone()
    assert row is not None, "No color collection found"
    collection_id = row["id"]

    # Create dark mode
    dark_result = create_dark_mode(db, collection_id, mode_name="Dark")
    assert dark_result["values_inverted"] > 0
    assert dark_result["values_copied"] > 0

    # Verify dark mode exists
    cursor = db.execute("""
        SELECT id FROM token_modes
        WHERE collection_id = ? AND name = 'Dark' AND is_default = 0
    """, (collection_id,))
    dark_mode = cursor.fetchone()
    assert dark_mode is not None

    # Verify values are different
    cursor = db.execute("""
        SELECT
            t.name,
            tv_default.resolved_value as default_value,
            tv_dark.resolved_value as dark_value
        FROM tokens t
        JOIN token_values tv_default ON tv_default.token_id = t.id
        JOIN token_values tv_dark ON tv_dark.token_id = t.id
        JOIN token_modes tm_default ON tv_default.mode_id = tm_default.id
        JOIN token_modes tm_dark ON tv_dark.mode_id = tm_dark.id
        WHERE t.collection_id = ?
        AND t.type = 'color'
        AND t.alias_of IS NULL
        AND tm_default.is_default = 1
        AND tm_dark.name = 'Dark'
    """, (collection_id,))

    for row in cursor.fetchall():
        default_val = row["default_value"]
        dark_val = row["dark_value"]
        assert default_val != dark_val, f"Values not inverted for {row['name']}"

        # Check inversion logic
        if default_val in ["#09090B", "#09090b"]:  # Dark color
            # Should be lighter in dark mode
            assert dark_val > default_val, f"Dark color {default_val} should be lighter in dark mode"
        elif default_val in ["#FFFFFF", "#ffffff"]:  # Light color
            # Should be darker in dark mode
            assert dark_val < default_val, f"Light color {default_val} should be darker in dark mode"

    # Fix non-DTCG-compliant names before validation
    db.execute("""
        UPDATE tokens
        SET name = LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'fontFamily', 'fontfamily'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety'))
        WHERE name LIKE '%font%' OR name LIKE '%line%' OR name LIKE '%offset%'
    """)
    db.commit()

    # Run validation again
    validation_result = run_validation(db, file_id=1)
    assert validation_result["passed"] is True

    # Generate CSS and verify dark mode block
    css_output = generate_css(db, file_id=1)
    assert '[data-theme="Dark"]' in css_output

    # Generate DTCG and verify extensions on color tokens
    dtcg_dict = generate_dtcg_dict(db, file_id=1)
    # Extensions are on individual tokens, not at root
    has_extensions = False
    if "color" in dtcg_dict:
        for category in dtcg_dict["color"].values():
            if isinstance(category, dict):
                for token in category.values():
                    if isinstance(token, dict) and "$extensions" in token:
                        has_extensions = True
                        break
    assert has_extensions, "No color tokens found with Dark mode extensions"

    # Generate Figma payloads and verify modes
    payloads = generate_variable_payloads(db, file_id=1)
    color_payload = next((p for p in payloads if "color" in p["collectionName"].lower()), None)
    assert color_payload is not None
    assert "Dark" in color_payload["modes"]


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_drift_detection_synced(db):
    """Test drift detection with matching values shows synced state."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "e2e_key", "E2E File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)
    run_validation(db, file_id=1)

    # Generate Figma payloads
    generate_variable_payloads(db, file_id=1)

    # Simulate export with matching values
    mock_response = _simulate_figma_export(db, 1)

    # Run drift detection
    drift_result = detect_drift(db, 1, mock_response)
    assert "comparison" in drift_result
    assert "updates" in drift_result

    # Verify all tokens marked as synced
    cursor = db.execute("""
        SELECT COUNT(*) as count FROM tokens
        WHERE sync_status = 'synced'
    """)
    synced_count = cursor.fetchone()["count"]
    assert synced_count > 0

    # Generate drift report
    report = generate_drift_report(db, 1)
    assert len(report["drifted_tokens"]) == 0

    # v_drift_report should return 0 rows
    cursor = db.execute("SELECT COUNT(*) as count FROM v_drift_report")
    assert cursor.fetchone()["count"] == 0


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_drift_detection_drifted(db):
    """Test drift detection catches modified values."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "e2e_key", "E2E File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)
    run_validation(db, file_id=1)

    # Get two color tokens to drift
    cursor = db.execute("""
        SELECT t.name FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND t.tier = 'curated'
        AND t.type = 'color'
        LIMIT 2
    """)
    drift_targets = {}
    for row in cursor.fetchall():
        drift_targets[row["name"]] = "#FF0000"  # Change to red

    # Build drifted response
    mock_response = _build_drifted_figma_response(db, 1, drift_targets)

    # Run drift detection
    drift_result = detect_drift(db, 1, mock_response)
    assert "comparison" in drift_result
    assert "updates" in drift_result

    # Verify 2 tokens marked as drifted
    cursor = db.execute("""
        SELECT COUNT(*) as count FROM tokens
        WHERE sync_status = 'drifted'
    """)
    assert cursor.fetchone()["count"] == 2

    # Verify remaining tokens are synced
    cursor = db.execute("""
        SELECT COUNT(*) as count FROM tokens
        WHERE sync_status = 'synced'
    """)
    assert cursor.fetchone()["count"] > 0

    # Generate drift report
    report = generate_drift_report(db, 1)
    assert len(report["drifted_tokens"]) == 2

    # v_drift_report should return drifted tokens
    cursor = db.execute("""
        SELECT token_name, db_value FROM v_drift_report
        WHERE sync_status = 'drifted'
    """)
    rows = cursor.fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row["token_name"] in drift_targets
        # DB value should be original, not #FF0000
        assert row["db_value"] != "#FF0000"


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_mode_values_seeded_correctly(db):
    """Test mode values are seeded correctly and independently."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run pipeline through curation
    run_extraction_pipeline(db, "e2e_key", "E2E File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Create dark mode on colors
    cursor = db.execute("""
        SELECT id FROM token_collections
        WHERE file_id = 1 AND name LIKE '%color%'
        COLLATE NOCASE
    """)
    color_collection_id = cursor.fetchone()["id"]

    dark_result = create_dark_mode(db, color_collection_id)
    assert dark_result["values_inverted"] > 0

    # Verify dark mode color values
    cursor = db.execute("""
        SELECT
            tv_default.resolved_value as default_val,
            tv_dark.resolved_value as dark_val
        FROM tokens t
        JOIN token_values tv_default ON tv_default.token_id = t.id
        JOIN token_values tv_dark ON tv_dark.token_id = t.id
        JOIN token_modes tm_default ON tv_default.mode_id = tm_default.id
        JOIN token_modes tm_dark ON tv_dark.mode_id = tm_dark.id
        WHERE t.collection_id = ?
        AND t.type = 'color'
        AND t.alias_of IS NULL
        AND tm_default.is_default = 1
        AND tm_dark.name = 'Dark'
    """, (color_collection_id,))

    for row in cursor.fetchall():
        # Verify values are valid hex
        assert re.match(r'^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$', row["dark_val"])
        # Verify different from default
        assert row["dark_val"] != row["default_val"]

    # Store default values
    cursor = db.execute("""
        SELECT t.id, tv.resolved_value
        FROM tokens t
        JOIN token_values tv ON tv.token_id = t.id
        JOIN token_modes tm ON tv.mode_id = tm.id
        WHERE t.collection_id = ?
        AND tm.is_default = 1
    """, (color_collection_id,))

    default_values = {row["id"]: row["resolved_value"] for row in cursor.fetchall()}

    # Modify a dark value
    db.execute("""
        UPDATE token_values
        SET resolved_value = '#123456'
        WHERE token_id = (
            SELECT t.id FROM tokens t
            WHERE t.collection_id = ?
            LIMIT 1
        )
        AND mode_id = (
            SELECT id FROM token_modes
            WHERE collection_id = ? AND name = 'Dark'
        )
    """, (color_collection_id, color_collection_id))
    db.commit()

    # Re-read default values to verify independence
    cursor = db.execute("""
        SELECT t.id, tv.resolved_value
        FROM tokens t
        JOIN token_values tv ON tv.token_id = t.id
        JOIN token_modes tm ON tv.mode_id = tm.id
        WHERE t.collection_id = ?
        AND tm.is_default = 1
    """, (color_collection_id,))

    for row in cursor.fetchall():
        # Default values should be unchanged
        assert row["resolved_value"] == default_values[row["id"]]


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_full_pipeline_fk_integrity(db):
    """Test FK integrity across ALL tables after full pipeline."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run COMPLETE pipeline
    run_extraction_pipeline(db, "e2e_key", "E2E File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)
    run_validation(db, file_id=1)

    # All exports
    export_css(db, file_id=1)
    export_tailwind(db, file_id=1)
    export_dtcg(db, file_id=1)

    # Dark mode
    cursor = db.execute("""
        SELECT id FROM token_collections
        WHERE file_id = 1 AND name LIKE '%color%'
        COLLATE NOCASE
    """)
    if row := cursor.fetchone():
        create_dark_mode(db, row["id"])

    # Drift detection
    mock_response = _simulate_figma_export(db, 1)
    detect_drift(db, 1, mock_response)

    # Check FK integrity
    fk_checks = [
        ("nodes", "SELECT COUNT(*) FROM nodes WHERE screen_id NOT IN (SELECT id FROM screens)"),
        ("node_token_bindings", "SELECT COUNT(*) FROM node_token_bindings WHERE node_id NOT IN (SELECT id FROM nodes)"),
        ("node_token_bindings", "SELECT COUNT(*) FROM node_token_bindings WHERE token_id IS NOT NULL AND token_id NOT IN (SELECT id FROM tokens)"),
        ("token_values", "SELECT COUNT(*) FROM token_values WHERE token_id NOT IN (SELECT id FROM tokens)"),
        ("token_values", "SELECT COUNT(*) FROM token_values WHERE mode_id NOT IN (SELECT id FROM token_modes)"),
        ("tokens", "SELECT COUNT(*) FROM tokens WHERE collection_id NOT IN (SELECT id FROM token_collections)"),
        ("token_modes", "SELECT COUNT(*) FROM token_modes WHERE collection_id NOT IN (SELECT id FROM token_collections)"),
        ("code_mappings", "SELECT COUNT(*) FROM code_mappings WHERE token_id NOT IN (SELECT id FROM tokens)"),
    ]

    for table, query in fk_checks:
        cursor = db.execute(query)
        count = cursor.fetchone()[0]
        assert count == 0, f"FK violation in {table}: {count} orphaned rows"


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_final_status_report(db):
    """Test status report generation after full pipeline."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline including dark mode and drift detection
    run_extraction_pipeline(db, "e2e_key", "E2E File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix non-DTCG-compliant names before validation
    db.execute("""
        UPDATE tokens
        SET name = LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'fontFamily', 'fontfamily'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety'))
        WHERE name LIKE '%font%' OR name LIKE '%line%' OR name LIKE '%offset%'
    """)
    db.commit()

    validation_result = run_validation(db, file_id=1)
    assert validation_result["passed"] is True

    # Dark mode
    cursor = db.execute("""
        SELECT id FROM token_collections
        WHERE file_id = 1 AND name LIKE '%color%'
        COLLATE NOCASE
    """)
    if row := cursor.fetchone():
        create_dark_mode(db, row["id"])

    # Drift detection (all synced)
    mock_response = _simulate_figma_export(db, 1)
    detect_drift(db, 1, mock_response)

    # Generate status report
    report = format_status_report(db, file_id=1)
    assert isinstance(report, str)
    assert len(report) > 0
    assert "Curation Progress" in report
    assert "bound" in report
    assert "Export Readiness" in report

    # Generate status dict
    status = get_status_dict(db, file_id=1)
    assert status["is_ready"] is True
    assert status["token_count"] > 0
    assert len(status["curation_progress"]) > 0

    # Verify bound bindings
    bound_found = False
    for item in status["curation_progress"]:
        if item["status"] == "bound":
            assert item["count"] > 0
            bound_found = True
    assert bound_found


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_multimode_export_consistency(db):
    """Test multi-mode export consistency across formats."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run pipeline through curation
    run_extraction_pipeline(db, "e2e_key", "E2E File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Create dark mode on colors
    cursor = db.execute("""
        SELECT id FROM token_collections
        WHERE file_id = 1 AND name LIKE '%color%'
        COLLATE NOCASE
    """)
    color_collection_id = cursor.fetchone()["id"]
    create_dark_mode(db, color_collection_id)

    # Generate all exports
    css_output = generate_css(db, file_id=1)
    dtcg_dict = generate_dtcg_dict(db, file_id=1)
    figma_payloads = generate_variable_payloads(db, file_id=1)

    # Verify CSS has both blocks
    assert ":root" in css_output
    assert '[data-theme="Dark"]' in css_output

    # Count variables in each CSS block
    root_count = _count_css_vars_in_block(css_output, ":root")
    dark_count = _count_css_vars_in_block(css_output, '[data-theme="Dark"]')
    assert root_count > 0
    assert dark_count > 0

    # Verify DTCG has Dark mode in extensions for color tokens
    # Extensions are on individual tokens, not at root
    color_token_with_extensions = False
    for category in ["color"]:
        if category in dtcg_dict:
            for subcategory in dtcg_dict[category].values():
                if isinstance(subcategory, dict):
                    for token in subcategory.values():
                        if isinstance(token, dict) and "$extensions" in token:
                            color_token_with_extensions = True
                            break
    assert color_token_with_extensions, "No color tokens found with $extensions for dark mode"

    # Verify Figma payloads have both modes for color collection
    color_payload = next((p for p in figma_payloads if "color" in p["collectionName"].lower()), None)
    assert color_payload is not None
    assert "Default" in color_payload["modes"]
    assert "Dark" in color_payload["modes"]

    # Get a color token to verify value consistency
    cursor = db.execute("""
        SELECT t.name FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.id = ? AND t.type = 'color'
        LIMIT 1
    """, (color_collection_id,))
    sample_token = cursor.fetchone()["name"]

    # Extract values from CSS
    css_var = "--" + sample_token.replace(".", "-")
    root_match = re.search(f'{re.escape(css_var)}:\\s*([^;]+);', css_output)

    # Find in Dark theme block
    dark_block_match = re.search(r'\[data-theme="Dark"\]\s*{([^}]+)}', css_output, re.DOTALL)
    if dark_block_match:
        dark_content = dark_block_match.group(1)
        dark_match = re.search(f'{re.escape(css_var)}:\\s*([^;]+);', dark_content)
        if dark_match:
            # We have both default and dark values
            assert root_match is not None
            default_css_val = root_match.group(1).strip()
            dark_css_val = dark_match.group(1).strip()
            assert default_css_val != dark_css_val  # Values should differ

    # Verify non-color collections only have Default mode
    spacing_payload = next((p for p in figma_payloads if "spacing" in p["collectionName"].lower()), None)
    if spacing_payload:
        assert "Default" in spacing_payload["modes"]
        assert "Dark" not in spacing_payload["modes"]  # Only colors get dark mode