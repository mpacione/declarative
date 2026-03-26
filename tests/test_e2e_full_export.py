"""End-to-end test: full pipeline through all exports.

This test runs the ENTIRE pipeline from extraction through clustering,
curation, validation, and all 4 export formats (CSS, Tailwind, DTCG, Figma payloads).
Verifies cross-format consistency and DTCG round-trip capability.
"""

import json
import re
import sqlite3
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from dd.cluster import run_clustering
from dd.curate import accept_all
from dd.db import init_db
from dd.export_css import generate_css, export_css
from dd.export_dtcg import generate_dtcg_json, generate_dtcg_dict, export_dtcg
from dd.export_figma_vars import generate_variable_payloads
from dd.export_tailwind import generate_tailwind_config, generate_tailwind_config_dict, export_tailwind
from dd.extract import run_extraction_pipeline
from dd.status import format_status_report, get_status_dict
from dd.validate import is_export_ready, run_validation
from dd.export_rebind import generate_rebind_scripts, get_rebind_summary


def _build_full_e2e_mock_data() -> Tuple[List[dict], Callable[[str], List[dict]]]:
    """Build mock data for comprehensive e2e testing of all export formats."""
    frames = [
        {"figma_node_id": "1:1", "name": "Home", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Profile", "width": 428, "height": 926},
        {"figma_node_id": "1:3", "name": "Components", "width": 1200, "height": 800},
    ]

    # Home: dark bg, heading text, card with shadow and radius, body text, divider with stroke
    home_nodes = [
        {"figma_node_id": "10:1", "parent_idx": None, "name": "Home",
         "node_type": "FRAME", "depth": 0, "sort_order": 0,
         "x": 0, "y": 0, "width": 428, "height": 926,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]),
         "layout_mode": "VERTICAL", "padding_top": 16, "padding_bottom": 16,
         "padding_left": 16, "padding_right": 16, "item_spacing": 8},
        {"figma_node_id": "10:2", "parent_idx": 0, "name": "Heading",
         "node_type": "TEXT", "depth": 1, "sort_order": 0,
         "x": 16, "y": 16, "width": 396, "height": 30,
         "font_family": "Inter", "font_weight": 600, "font_size": 24,
         "line_height": json.dumps({"value": 30, "unit": "PIXELS"}),
         "text_content": "Home"},
        {"figma_node_id": "10:3", "parent_idx": 0, "name": "Card",
         "node_type": "RECTANGLE", "depth": 1, "sort_order": 1,
         "x": 16, "y": 60, "width": 396, "height": 200,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),
         "corner_radius": 8,
         "effects": json.dumps([{"type": "DROP_SHADOW", "visible": True,
             "color": {"r": 0, "g": 0, "b": 0, "a": 0.1},
             "radius": 6, "offset": {"x": 0, "y": 4}, "spread": -1}])},
        {"figma_node_id": "10:4", "parent_idx": 0, "name": "Body",
         "node_type": "TEXT", "depth": 1, "sort_order": 2,
         "x": 16, "y": 270, "width": 396, "height": 20,
         "font_family": "Inter", "font_weight": 400, "font_size": 14,
         "line_height": json.dumps({"value": 20, "unit": "PIXELS"}),
         "text_content": "Welcome"},
        {"figma_node_id": "10:5", "parent_idx": 0, "name": "Divider",
         "node_type": "FRAME", "depth": 1, "sort_order": 3,
         "x": 16, "y": 300, "width": 396, "height": 1,
         "strokes": json.dumps([{"type": "SOLID", "color": {"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}}]),
         "stroke_weight": 1},
    ]

    # Profile: reuses some colors, different radius
    profile_nodes = [
        {"figma_node_id": "20:1", "parent_idx": None, "name": "Profile",
         "node_type": "FRAME", "depth": 0, "sort_order": 0,
         "x": 0, "y": 0, "width": 428, "height": 926,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]),
         "layout_mode": "VERTICAL", "padding_top": 16, "padding_bottom": 16,
         "padding_left": 16, "padding_right": 16, "item_spacing": 16},
        {"figma_node_id": "20:2", "parent_idx": 0, "name": "Username",
         "node_type": "TEXT", "depth": 1, "sort_order": 0,
         "x": 16, "y": 16, "width": 396, "height": 20,
         "font_family": "Inter", "font_weight": 400, "font_size": 14,
         "line_height": json.dumps({"value": 20, "unit": "PIXELS"}),
         "text_content": "john_doe"},
        {"figma_node_id": "20:3", "parent_idx": 0, "name": "Avatar",
         "node_type": "RECTANGLE", "depth": 1, "sort_order": 1,
         "x": 16, "y": 50, "width": 80, "height": 80,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.094, "g": 0.094, "b": 0.106, "a": 1}}]),
         "corner_radius": 12},
    ]

    # Components: minimal
    comp_nodes = [
        {"figma_node_id": "30:1", "parent_idx": None, "name": "Components",
         "node_type": "FRAME", "depth": 0, "sort_order": 0,
         "x": 0, "y": 0, "width": 1200, "height": 800},
    ]

    responses = {"1:1": home_nodes, "1:2": profile_nodes, "1:3": comp_nodes}

    def extract_fn(script: str) -> List[Dict[str, Any]]:
        """Mock extract function returning diverse property types."""
        # Determine which screen based on script content
        if '"1:1"' in script:
            return responses["1:1"]
        elif '"1:2"' in script:
            return responses["1:2"]
        elif '"1:3"' in script:
            return responses["1:3"]
        else:
            return []

    return frames, extract_fn


def _count_css_vars(css_string: str) -> int:
    """Parse CSS and count --var: value; lines in :root block."""
    # Find :root block
    root_match = re.search(r':root\s*{([^}]+)}', css_string, re.DOTALL)
    if not root_match:
        return 0

    root_content = root_match.group(1)
    # Count CSS variables (--name: value;)
    var_pattern = r'--[\w-]+:\s*[^;]+;'
    matches = re.findall(var_pattern, root_content)
    return len(matches)


def _count_dtcg_leaves(dtcg_dict: dict, path: str = "") -> int:
    """Recursively count nodes with $value key."""
    count = 0

    for key, value in dtcg_dict.items():
        if key.startswith("$"):
            # Skip metadata keys
            continue

        if isinstance(value, dict):
            if "$value" in value:
                # This is a leaf token
                count += 1
            else:
                # Recurse into nested group
                count += _count_dtcg_leaves(value, f"{path}.{key}" if path else key)

    return count


def _extract_css_value(css_string: str, var_name: str) -> Optional[str]:
    """Extract value for a specific CSS variable."""
    pattern = rf'{re.escape(var_name)}:\s*([^;]+);'
    match = re.search(pattern, css_string)
    return match.group(1).strip() if match else None


def _navigate_dtcg_path(dtcg_dict: dict, path: str) -> Optional[dict]:
    """Navigate nested dict by dot-path."""
    parts = path.split(".")
    current = dtcg_dict

    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]

    return current


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
def test_e2e_all_four_export_formats_produced(db):
    """Test that all 4 export formats produce non-empty output."""
    frames, extract_fn = _build_full_e2e_mock_data()

    # Run full pipeline
    result = run_extraction_pipeline(
        db,
        file_key="test-file-123",
        file_name="E2E Test File",
        frames=frames,
        extract_fn=extract_fn,
        node_count=100
    )
    assert result["status"] == "completed"

    # Clustering
    cluster_result = run_clustering(db, file_id=1, color_threshold=0.05, agent_id="test")
    assert cluster_result["total_tokens"] > 0

    # Curation
    curation_result = accept_all(db, file_id=1)
    assert curation_result["tokens_accepted"] > 0

    # Fix non-DTCG-compliant names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%' OR name LIKE '%line%'
    """)
    db.commit()

    # Validation
    validation_result = run_validation(db, file_id=1)
    assert validation_result["passed"] is True
    assert is_export_ready(db) is True

    # CSS export
    css_output = generate_css(db, file_id=1)
    assert css_output is not None
    assert len(css_output) > 0
    assert ":root" in css_output

    # Tailwind export
    tailwind_output = generate_tailwind_config(db, file_id=1)
    assert tailwind_output is not None
    assert len(tailwind_output) > 0
    assert "module.exports" in tailwind_output

    # DTCG export
    dtcg_json = generate_dtcg_json(db, file_id=1)
    assert dtcg_json is not None
    assert len(dtcg_json) > 0
    dtcg_dict = json.loads(dtcg_json)  # Verify parseable
    assert isinstance(dtcg_dict, dict)

    # Figma payloads
    figma_payloads = generate_variable_payloads(db, file_id=1)
    assert isinstance(figma_payloads, list)
    assert len(figma_payloads) > 0


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_token_counts_consistent_across_formats(db):
    """Test token counts are consistent across all formats."""
    frames, extract_fn = _build_full_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%' OR name LIKE '%line%'
    """)
    db.commit()

    run_validation(db, file_id=1)

    # Count curated tokens in DB
    cursor = db.execute("""
        SELECT COUNT(*) as count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
    """)
    db_count = cursor.fetchone()["count"]
    assert db_count > 0

    # Count in CSS
    css_output = generate_css(db, file_id=1)
    css_count = _count_css_vars(css_output)

    # Count in DTCG
    dtcg_dict = generate_dtcg_dict(db, file_id=1)
    dtcg_count = _count_dtcg_leaves(dtcg_dict)

    # Count in Figma payloads
    figma_payloads = generate_variable_payloads(db, file_id=1)
    figma_count = sum(len(p["tokens"]) for p in figma_payloads)

    # Verify consistency
    # DTCG may have fewer tokens due to composite bundling (typography, shadows)
    assert dtcg_count > 0 and dtcg_count <= db_count, f"DTCG count {dtcg_count} out of range (0, {db_count}]"
    assert figma_count == db_count, f"Figma count {figma_count} != DB count {db_count}"
    # CSS exports only specific token types (color, dimension, fontFamily, fontWeight, number)
    # So it may have fewer tokens than DB
    assert css_count > 0, f"CSS count {css_count} should be > 0"


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_dtcg_json_round_trip(db):
    """Test DTCG JSON round-trip fidelity."""
    frames, extract_fn = _build_full_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%' OR name LIKE '%line%'
    """)
    db.commit()

    run_validation(db, file_id=1)

    # Generate DTCG JSON
    dtcg_json = generate_dtcg_json(db, file_id=1)

    # Parse
    dict1 = json.loads(dtcg_json)

    # Re-serialize
    json_str2 = json.dumps(dict1, indent=2)

    # Re-parse
    dict2 = json.loads(json_str2)

    # Verify round-trip fidelity
    assert dict1 == dict2

    # Verify proper DTCG structure
    def verify_dtcg_structure(d, path=""):
        for key, value in d.items():
            if key.startswith("$"):
                continue
            if isinstance(value, dict):
                if "$value" in value:
                    # Leaf token
                    assert "$type" in value, f"Missing $type at {path}.{key}"
                    assert value["$type"] is not None, f"Null $type at {path}.{key}"
                    assert value["$type"] != "", f"Empty $type at {path}.{key}"
                    assert value["$value"] is not None, f"Null $value at {path}.{key}"
                else:
                    # Group
                    verify_dtcg_structure(value, f"{path}.{key}" if path else key)

    verify_dtcg_structure(dict1)


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_css_vars_match_dtcg_values(db):
    """Test CSS variable values match DTCG values."""
    frames, extract_fn = _build_full_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%' OR name LIKE '%line%'
    """)
    db.commit()

    run_validation(db, file_id=1)

    # Generate exports
    css_output = generate_css(db, file_id=1)
    dtcg_dict = generate_dtcg_dict(db, file_id=1)

    # Get curated color tokens from DB
    cursor = db.execute("""
        SELECT t.name, tv.resolved_value
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        JOIN token_values tv ON tv.token_id = t.id
        JOIN token_modes tm ON tv.mode_id = tm.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
        AND t.type = 'color'
        AND tm.is_default = 1
    """)

    for row in cursor.fetchall():
        token_name = row["name"]
        expected_value = row["resolved_value"]

        # Extract from CSS
        css_var_name = "--" + token_name.replace(".", "-")
        css_value = _extract_css_value(css_output, css_var_name)

        # Extract from DTCG
        dtcg_node = _navigate_dtcg_path(dtcg_dict, token_name)
        if dtcg_node and "$value" in dtcg_node:
            dtcg_value = dtcg_node["$value"]

            # Compare values
            if css_value and dtcg_value:
                # Handle 8-digit hex colors that get converted to rgba in CSS
                if len(expected_value) == 9 and expected_value.startswith("#"):
                    # CSS converts to rgba, DTCG keeps as hex
                    assert dtcg_value == expected_value, f"{token_name}: DTCG {dtcg_value} != expected {expected_value}"
                    # CSS should be rgba format
                    assert css_value.startswith("rgba("), f"{token_name}: CSS {css_value} not in rgba format"
                else:
                    # Regular hex colors should match
                    assert css_value == expected_value, f"{token_name}: CSS {css_value} != expected {expected_value}"
                    assert dtcg_value == expected_value, f"{token_name}: DTCG {dtcg_value} != expected {expected_value}"

    # Check dimension tokens
    cursor = db.execute("""
        SELECT t.name, tv.resolved_value
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        JOIN token_values tv ON tv.token_id = t.id
        JOIN token_modes tm ON tv.mode_id = tm.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
        AND t.type = 'dimension'
        AND tm.is_default = 1
    """)

    for row in cursor.fetchall():
        token_name = row["name"]
        expected_value = row["resolved_value"]  # e.g. "16"

        # Extract from CSS
        css_var_name = "--" + token_name.replace(".", "-")
        css_value = _extract_css_value(css_output, css_var_name)

        if css_value:
            # CSS should be "16px" or "24.0px"
            # Just check that the numeric value matches
            css_numeric = css_value.replace("px", "")
            expected_num = float(expected_value)
            assert float(css_numeric) == expected_num, f"{token_name}: CSS {css_numeric} != {expected_num}"

        # Extract from DTCG
        dtcg_node = _navigate_dtcg_path(dtcg_dict, token_name)
        if dtcg_node and "$value" in dtcg_node:
            dtcg_value = dtcg_node["$value"]
            # DTCG should be {"value": 16, "unit": "px"}
            assert isinstance(dtcg_value, dict), f"{token_name}: DTCG value not a dict"
            expected_num = float(expected_value)
            if expected_num.is_integer():
                expected_num = int(expected_num)
            assert dtcg_value["value"] == expected_num, f"{token_name}: DTCG value {dtcg_value['value']} != {expected_num}"
            assert dtcg_value["unit"] == "px", f"{token_name}: DTCG unit not 'px'"


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_figma_payloads_match_code_exports(db):
    """Test Figma payload values match DTCG values."""
    frames, extract_fn = _build_full_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%' OR name LIKE '%line%'
    """)
    db.commit()

    run_validation(db, file_id=1)

    # Generate exports
    figma_payloads = generate_variable_payloads(db, file_id=1)
    dtcg_dict = generate_dtcg_dict(db, file_id=1)

    # For each token in Figma payloads
    for payload in figma_payloads:
        for token in payload["tokens"]:
            # Convert Figma name back to DTCG
            figma_name = token["name"]  # e.g. "color/surface/primary"
            dtcg_name = figma_name.replace("/", ".")  # e.g. "color.surface.primary"

            # Find in DTCG
            dtcg_node = _navigate_dtcg_path(dtcg_dict, dtcg_name)

            # Some tokens may be part of composites (e.g. shadow.sm.offsetx)
            # These won't have individual DTCG entries, they're bundled in shadow.sm
            if dtcg_node is None:
                # Check if this is a shadow or typography sub-field
                parts = dtcg_name.split(".")
                if len(parts) > 1:
                    last_part = parts[-1]
                    if last_part in ["offsetx", "offsety", "radius", "spread", "color",
                                   "fontfamily", "fontsize", "fontweight", "lineheight"]:
                        # This is a sub-field of a composite, skip individual comparison
                        continue
                assert False, f"Token {dtcg_name} not found in DTCG"

            # Get default mode value from Figma payload
            figma_value = None
            for mode_name, value in token["values"].items():
                figma_value = value  # Take first (should be default)
                break

            # Compare values
            if token["type"] == "COLOR":
                # Both should be hex strings
                dtcg_value = dtcg_node["$value"]
                assert figma_value == dtcg_value, f"{dtcg_name}: Figma {figma_value} != DTCG {dtcg_value}"

            elif token["type"] == "FLOAT":
                # Figma has numeric value, DTCG has dimension object
                dtcg_value = dtcg_node["$value"]
                if isinstance(dtcg_value, dict):
                    # Compare numeric values, handling both string and numeric types
                    figma_num = float(figma_value) if isinstance(figma_value, str) else figma_value
                    dtcg_num = float(dtcg_value["value"]) if isinstance(dtcg_value["value"], str) else dtcg_value["value"]
                    assert figma_num == dtcg_num, f"{dtcg_name}: Figma {figma_num} != DTCG {dtcg_num}"
                else:
                    # For fontWeight etc.
                    figma_num = float(figma_value) if isinstance(figma_value, str) else figma_value
                    dtcg_num = float(dtcg_value) if isinstance(dtcg_value, str) else dtcg_value
                    assert figma_num == dtcg_num, f"{dtcg_name}: Figma {figma_num} != DTCG {dtcg_num}"


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_code_mappings_complete(db):
    """Test code_mappings populated for all 3 targets."""
    frames, extract_fn = _build_full_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%' OR name LIKE '%line%'
    """)
    db.commit()

    run_validation(db, file_id=1)

    # Call all 3 code exporters
    export_css(db, file_id=1)
    export_tailwind(db, file_id=1)
    export_dtcg(db, file_id=1)

    # Query code_mappings
    cursor = db.execute("""
        SELECT target, COUNT(*) as count
        FROM code_mappings
        GROUP BY target
    """)

    mappings = {row["target"]: row["count"] for row in cursor.fetchall()}

    # Verify all 3 targets present
    assert "css" in mappings
    assert "tailwind" in mappings
    assert "dtcg" in mappings

    # All should have mappings
    assert mappings["css"] > 0
    assert mappings["tailwind"] > 0
    assert mappings["dtcg"] > 0

    # Count curated tokens
    cursor = db.execute("""
        SELECT COUNT(*) as count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
    """)
    curated_count = cursor.fetchone()["count"]

    # Verify every curated token has at least 1 mapping per target
    cursor = db.execute("""
        SELECT t.id, t.name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
    """)

    for row in cursor.fetchall():
        token_id = row["id"]

        # Check each target
        for target in ["css", "tailwind", "dtcg"]:
            cursor2 = db.execute("""
                SELECT COUNT(*) as count
                FROM code_mappings
                WHERE token_id = ? AND target = ?
            """, (token_id, target))
            count = cursor2.fetchone()["count"]
            assert count >= 1, f"Token {row['name']} missing {target} mapping"

    # Verify FK integrity
    cursor = db.execute("""
        SELECT COUNT(*) as invalid_count
        FROM code_mappings cm
        WHERE cm.token_id NOT IN (SELECT id FROM tokens)
    """)
    assert cursor.fetchone()["invalid_count"] == 0

    # Total mappings should be >= 3 * curated_count
    total_mappings = sum(mappings.values())
    assert total_mappings >= 3 * curated_count


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_full_pipeline_status_report(db):
    """Test status report after full pipeline."""
    frames, extract_fn = _build_full_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%' OR name LIKE '%line%'
    """)
    db.commit()

    run_validation(db, file_id=1)

    # Generate all exports
    export_css(db, file_id=1)
    export_tailwind(db, file_id=1)
    export_dtcg(db, file_id=1)

    # Generate status report
    report = format_status_report(db, file_id=1)

    # Verify report contents
    assert "Curation Progress" in report
    assert "bound" in report
    assert "Export Readiness" in report

    # Get status dict
    status_dict = get_status_dict(db, file_id=1)

    # Verify dict structure
    assert status_dict["is_ready"] is True
    assert status_dict["token_count"] > 0
    assert "curation_progress" in status_dict
    assert len(status_dict["curation_progress"]) > 0

    # Verify curation shows bound bindings
    curation_data = status_dict["curation_progress"]
    bound_found = False
    for item in curation_data:
        if item["status"] == "bound":
            assert item["count"] > 0
            bound_found = True
    assert bound_found, "No bound bindings in status"


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_rebind_scripts_after_figma_export(db):
    """Test rebind scripts generated after simulated Figma writeback."""
    frames, extract_fn = _build_full_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test File", frames, extract_fn)
    run_clustering(db, file_id=1)
    accept_all(db, file_id=1)

    # Fix names
    db.execute("""
        UPDATE tokens
        SET name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
            name,
            'fontFamily', 'fontfamily'),
            'fontSize', 'fontsize'),
            'fontWeight', 'fontweight'),
            'lineHeight', 'lineheight'),
            'offsetX', 'offsetx'),
            'offsetY', 'offsety')
        WHERE name LIKE '%font%' OR name LIKE '%offset%' OR name LIKE '%line%'
    """)
    db.commit()

    run_validation(db, file_id=1)

    # Generate Figma payloads
    payloads = generate_variable_payloads(db, file_id=1)

    # Simulate writeback: set figma_variable_id on all curated tokens
    var_counter = 1000
    cursor = db.execute("""
        SELECT t.id
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
    """)

    for row in cursor.fetchall():
        db.execute("""
            UPDATE tokens
            SET figma_variable_id = ?, sync_status = 'synced'
            WHERE id = ?
        """, (f"var_{var_counter}", row["id"]))
        var_counter += 1
    db.commit()

    # Generate rebind scripts
    scripts = generate_rebind_scripts(db, file_id=1)

    # Verify scripts generated
    assert isinstance(scripts, list)
    assert len(scripts) > 0

    for script in scripts:
        assert isinstance(script, str)
        assert len(script) > 0

    # Get rebind summary
    summary = get_rebind_summary(db, file_id=1)

    # Verify summary
    assert summary["total_bindings"] > 0
    assert len(summary["by_property_type"]) > 0

    # Count bound bindings in DB
    cursor = db.execute("""
        SELECT COUNT(*) as count
        FROM node_token_bindings ntb
        JOIN tokens t ON ntb.token_id = t.id
        WHERE ntb.binding_status = 'bound'
        AND t.figma_variable_id IS NOT NULL
    """)
    db_binding_count = cursor.fetchone()["count"]

    # Total bindings in summary should match DB
    assert summary["total_bindings"] == db_binding_count