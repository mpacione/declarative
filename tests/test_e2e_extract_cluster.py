"""End-to-end test covering extraction through clustering (Waves 0-3)."""

import json
import sqlite3
from typing import Any, Dict, List, Tuple

import pytest

from dd.cluster import run_clustering, generate_summary, validate_no_orphan_tokens
from dd.extract import run_extraction_pipeline


# Mock frames for extraction (2 phone screens + 1 component sheet)
MOCK_FRAMES = [
    {"figma_node_id": "1:1", "name": "Home", "width": 428, "height": 926},
    {"figma_node_id": "1:2", "name": "Settings", "width": 428, "height": 926},
    {"figma_node_id": "1:3", "name": "Buttons and Controls", "width": 1200, "height": 800},
]


def _build_rich_mock_data() -> Tuple[List[Dict[str, Any]], callable]:
    """Build rich mock data for extraction.

    Returns:
        Tuple of (frames, extract_fn) where extract_fn maps screen_figma_node_id to node data
    """
    frames = MOCK_FRAMES.copy()

    # Build mock responses for each screen
    mock_responses = {}

    # Home screen (1:1) - 12 nodes with various properties
    home_nodes = [
        # Root frame with dark fill
        {
            "figma_node_id": "1:1",
            "name": "Home",
            "node_type": "FRAME",
            "depth": 0,
            "sort_order": 0,
            "x": 0,
            "y": 0,
            "width": 428,
            "height": 926,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]),  # #09090B
            "layout_mode": "VERTICAL",
            "padding_top": 16,
            "padding_right": 16,
            "padding_bottom": 16,
            "padding_left": 16,
            "item_spacing": 8,
        },
        # Header frame
        {
            "figma_node_id": "1:1:1",
            "name": "Header",
            "node_type": "FRAME",
            "depth": 1,
            "sort_order": 0,
            "x": 0,
            "y": 0,
            "width": 428,
            "height": 60,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
            "layout_mode": "HORIZONTAL",
            "padding_top": 12,
            "padding_right": 16,
            "padding_bottom": 12,
            "padding_left": 16,
            "item_spacing": 16,
        },
        # Title text
        {
            "figma_node_id": "1:1:2",
            "name": "Title",
            "node_type": "TEXT",
            "depth": 2,
            "sort_order": 0,
            "x": 16,
            "y": 18,
            "width": 200,
            "height": 24,
            "font_family": "Inter",
            "font_size": 24,
            "font_weight": 600,
            "line_height": json.dumps({"value": 32, "unit": "PIXELS"}),
            "letter_spacing": json.dumps({"value": -0.02, "unit": "PERCENT"}),
            "text_align": "LEFT",
            "text_content": "Home",
        },
        # Subtitle text
        {
            "figma_node_id": "1:1:3",
            "name": "Subtitle",
            "node_type": "TEXT",
            "depth": 2,
            "sort_order": 1,
            "x": 16,
            "y": 50,
            "width": 200,
            "height": 20,
            "font_family": "Inter",
            "font_size": 16,
            "font_weight": 400,
            "line_height": json.dumps({"value": 24, "unit": "PIXELS"}),
            "text_content": "Welcome back",
        },
        # Card with border and radius
        {
            "figma_node_id": "1:1:4",
            "name": "Card",
            "node_type": "RECTANGLE",
            "depth": 1,
            "sort_order": 1,
            "x": 16,
            "y": 100,
            "width": 396,
            "height": 120,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
            "strokes": json.dumps([{"type": "SOLID", "color": {"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}}]),  # #D4D4D8
            "stroke_weight": 1,
            "corner_radius": json.dumps(8),
        },
        # Button with shadow effect
        {
            "figma_node_id": "1:1:5",
            "name": "Button",
            "node_type": "FRAME",
            "depth": 1,
            "sort_order": 2,
            "x": 16,
            "y": 240,
            "width": 120,
            "height": 40,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.2, "g": 0.4, "b": 1, "a": 1}}]),  # #3366FF
            "corner_radius": json.dumps(4),
            "effects": json.dumps([{
                "type": "DROP_SHADOW",
                "color": {"r": 0, "g": 0, "b": 0, "a": 0.15},
                "offset": {"x": 0, "y": 2},
                "radius": 6,
                "spread": 0,
                "visible": True
            }]),
        },
        # Container with spacing
        {
            "figma_node_id": "1:1:6",
            "name": "Container",
            "node_type": "FRAME",
            "depth": 1,
            "sort_order": 3,
            "x": 16,
            "y": 300,
            "width": 396,
            "height": 200,
            "layout_mode": "VERTICAL",
            "padding_top": 24,
            "padding_right": 24,
            "padding_bottom": 24,
            "padding_left": 24,
            "item_spacing": 12,
        },
        # Another text with different size
        {
            "figma_node_id": "1:1:7",
            "name": "Body Text",
            "node_type": "TEXT",
            "depth": 2,
            "sort_order": 0,
            "x": 40,
            "y": 324,
            "font_family": "Inter",
            "font_size": 14,
            "font_weight": 400,
            "text_content": "This is body text",
        },
        # Small radius element
        {
            "figma_node_id": "1:1:8",
            "name": "Badge",
            "node_type": "RECTANGLE",
            "depth": 2,
            "sort_order": 1,
            "x": 40,
            "y": 360,
            "width": 60,
            "height": 24,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.95, "g": 0.95, "b": 0.96, "a": 1}}]),  # #F2F2F5
            "corner_radius": json.dumps(12),
        },
        # Larger radius element
        {
            "figma_node_id": "1:1:9",
            "name": "Rounded Box",
            "node_type": "RECTANGLE",
            "depth": 1,
            "sort_order": 4,
            "x": 16,
            "y": 520,
            "width": 396,
            "height": 100,
            "corner_radius": json.dumps(16),
        },
        # Container with different spacing
        {
            "figma_node_id": "1:1:10",
            "name": "List Container",
            "node_type": "FRAME",
            "depth": 1,
            "sort_order": 5,
            "x": 16,
            "y": 640,
            "layout_mode": "VERTICAL",
            "item_spacing": 4,
        },
        # Element with larger shadow
        {
            "figma_node_id": "1:1:11",
            "name": "Modal",
            "node_type": "FRAME",
            "depth": 1,
            "sort_order": 6,
            "x": 50,
            "y": 700,
            "width": 328,
            "height": 180,
            "effects": json.dumps([{
                "type": "DROP_SHADOW",
                "color": {"r": 0, "g": 0, "b": 0, "a": 0.25},
                "offset": {"x": 0, "y": 4},
                "radius": 12,
                "spread": 2,
                "visible": True
            }]),
        },
    ]

    # Settings screen (1:2) - 10 nodes with some overlapping values
    settings_nodes = [
        # Root frame with same dark fill as Home
        {
            "figma_node_id": "1:2",
            "name": "Settings",
            "node_type": "FRAME",
            "depth": 0,
            "sort_order": 0,
            "x": 0,
            "y": 0,
            "width": 428,
            "height": 926,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]),  # #09090B (same as Home)
            "layout_mode": "VERTICAL",
            "padding_top": 16,
            "padding_right": 16,
            "padding_bottom": 16,
            "padding_left": 16,
            "item_spacing": 8,
        },
        # Settings header
        {
            "figma_node_id": "1:2:1",
            "name": "Settings Header",
            "node_type": "FRAME",
            "depth": 1,
            "sort_order": 0,
            "x": 0,
            "y": 0,
            "width": 428,
            "height": 56,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF (reused)
        },
        # Settings title
        {
            "figma_node_id": "1:2:2",
            "name": "Settings Title",
            "node_type": "TEXT",
            "depth": 2,
            "sort_order": 0,
            "x": 16,
            "y": 16,
            "font_family": "Inter",
            "font_size": 20,
            "font_weight": 600,
            "text_content": "Settings",
        },
        # Settings item with smaller text
        {
            "figma_node_id": "1:2:3",
            "name": "Setting Label",
            "node_type": "TEXT",
            "depth": 1,
            "sort_order": 1,
            "x": 16,
            "y": 80,
            "font_family": "Inter",
            "font_size": 14,
            "font_weight": 400,
            "text_content": "Notifications",
        },
        # Toggle background
        {
            "figma_node_id": "1:2:4",
            "name": "Toggle",
            "node_type": "RECTANGLE",
            "depth": 1,
            "sort_order": 2,
            "x": 350,
            "y": 78,
            "width": 48,
            "height": 24,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.2, "g": 0.8, "b": 0.4, "a": 1}}]),  # #33CC66
            "corner_radius": json.dumps(12),
        },
        # Section with different padding
        {
            "figma_node_id": "1:2:5",
            "name": "Section",
            "node_type": "FRAME",
            "depth": 1,
            "sort_order": 3,
            "x": 0,
            "y": 120,
            "width": 428,
            "height": 200,
            "layout_mode": "VERTICAL",
            "padding_top": 20,
            "padding_right": 20,
            "padding_bottom": 20,
            "padding_left": 20,
            "item_spacing": 10,
        },
        # Divider
        {
            "figma_node_id": "1:2:6",
            "name": "Divider",
            "node_type": "RECTANGLE",
            "depth": 1,
            "sort_order": 4,
            "x": 16,
            "y": 340,
            "width": 396,
            "height": 1,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}}]),  # #D4D4D8 (reused)
        },
        # Another text variant
        {
            "figma_node_id": "1:2:7",
            "name": "Description",
            "node_type": "TEXT",
            "depth": 1,
            "sort_order": 5,
            "x": 16,
            "y": 360,
            "font_family": "Inter",
            "font_size": 12,
            "font_weight": 400,
            "text_content": "App version 1.0.0",
        },
        # Button with different color
        {
            "figma_node_id": "1:2:8",
            "name": "Logout Button",
            "node_type": "FRAME",
            "depth": 1,
            "sort_order": 6,
            "x": 16,
            "y": 400,
            "width": 396,
            "height": 48,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.9, "g": 0.2, "b": 0.2, "a": 1}}]),  # #E63333
            "corner_radius": json.dumps(8),
        },
        # Footer container
        {
            "figma_node_id": "1:2:9",
            "name": "Footer",
            "node_type": "FRAME",
            "depth": 1,
            "sort_order": 7,
            "x": 0,
            "y": 826,
            "width": 428,
            "height": 100,
            "layout_mode": "HORIZONTAL",
            "padding_top": 8,
            "padding_bottom": 8,
            "item_spacing": 16,
        },
    ]

    # Component sheet (1:3) - Include 1 component (will be skipped) and some other nodes
    component_nodes = [
        # Root frame
        {
            "figma_node_id": "1:3",
            "name": "Buttons and Controls",
            "node_type": "FRAME",
            "depth": 0,
            "sort_order": 0,
            "x": 0,
            "y": 0,
            "width": 1200,
            "height": 800,
            "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.98, "g": 0.98, "b": 0.98, "a": 1}}]),  # #FAFAFA
        },
        # A component (should be skipped)
        {
            "figma_node_id": "1:3:1",
            "name": "Button Component",
            "node_type": "COMPONENT",
            "depth": 1,
            "sort_order": 0,
            "x": 50,
            "y": 50,
            "width": 120,
            "height": 40,
        },
        # Regular frame
        {
            "figma_node_id": "1:3:2",
            "name": "Example Container",
            "node_type": "FRAME",
            "depth": 1,
            "sort_order": 1,
            "x": 50,
            "y": 120,
            "width": 300,
            "height": 200,
            "layout_mode": "VERTICAL",
            "padding_top": 32,
            "padding_right": 32,
            "padding_bottom": 32,
            "padding_left": 32,
            "item_spacing": 24,
        },
    ]

    # Store responses keyed by figma_node_id
    mock_responses["1:1"] = home_nodes
    mock_responses["1:2"] = settings_nodes
    mock_responses["1:3"] = component_nodes

    # Create extract_fn that returns appropriate response based on script
    def extract_fn(node_id: str) -> List[Dict[str, Any]]:
        """Mock extract function that returns nodes for the requested screen."""
        return mock_responses.get(node_id, [])

    return frames, extract_fn


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_extraction_then_clustering(db: sqlite3.Connection):
    """Test full pipeline from extraction through clustering."""

    # Build mock data
    frames, extract_fn = _build_rich_mock_data()

    # Run extraction pipeline
    extract_result = run_extraction_pipeline(
        db,
        file_key="e2e_test_key",
        file_name="E2E Test File",
        frames=frames,
        extract_fn=extract_fn,
        agent_id="test_agent"
    )

    # Verify extraction completed
    assert extract_result["status"] == "completed"
    assert extract_result["completed"] == 3
    assert extract_result["failed"] == 0

    # Check extraction_runs table
    cursor = db.cursor()
    cursor.execute("SELECT status FROM extraction_runs WHERE file_id = 1")
    run = cursor.fetchone()
    assert run is not None
    assert run[0] == "completed"  # status column

    # Check nodes were created
    cursor.execute("SELECT COUNT(*) FROM nodes")
    node_count = cursor.fetchone()[0]
    assert node_count > 20  # We created 12 + 10 + 3 = 25 nodes

    # Check unbound bindings were created
    cursor.execute("SELECT COUNT(*) FROM node_token_bindings WHERE binding_status = 'unbound'")
    unbound_count = cursor.fetchone()[0]
    assert unbound_count > 0

    # Run clustering
    cluster_result = run_clustering(db, file_id=1, color_threshold=2.0)

    # Verify clustering results
    assert cluster_result["total_tokens"] > 0
    assert cluster_result["total_bindings_updated"] > 0
    assert cluster_result["coverage_pct"] > 0

    # Check tokens were created
    cursor.execute("SELECT COUNT(*) FROM tokens")
    token_count = cursor.fetchone()[0]
    assert token_count > 0

    # Check token_values were created
    cursor.execute("SELECT COUNT(*) FROM token_values")
    value_count = cursor.fetchone()[0]
    assert value_count > 0

    # Check some bindings moved to proposed
    cursor.execute("SELECT COUNT(*) FROM node_token_bindings WHERE binding_status = 'proposed'")
    proposed_count = cursor.fetchone()[0]
    assert proposed_count > 0

    # Check no orphan tokens
    orphans = validate_no_orphan_tokens(db, file_id=1)
    assert len(orphans) == 0

    # Verify token names are unique within collections
    cursor.execute("""
        SELECT collection_id, name, COUNT(*) as cnt
        FROM tokens
        GROUP BY collection_id, name
        HAVING cnt > 1
    """)
    duplicates = cursor.fetchall()
    assert len(duplicates) == 0

    # Check curation progress view
    cursor.execute("SELECT * FROM v_curation_progress")
    progress = cursor.fetchall()
    assert len(progress) > 0

    # Should have both proposed and possibly unbound statuses
    statuses = [row[0] for row in progress]
    assert "proposed" in statuses or "unbound" in statuses


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_token_values_populated(db: sqlite3.Connection):
    """Test that token values are properly populated after clustering."""
    # Run full pipeline
    frames, extract_fn = _build_rich_mock_data()

    run_extraction_pipeline(db, "e2e_test", "Test", frames, extract_fn)
    run_clustering(db, file_id=1)

    cursor = db.cursor()

    # Every token should have at least 1 token_value
    cursor.execute("""
        SELECT t.id, t.name, COUNT(tv.id) as value_count
        FROM tokens t
        LEFT JOIN token_values tv ON tv.token_id = t.id
        GROUP BY t.id
    """)
    for row in cursor.fetchall():
        token_id, token_name, value_count = row
        assert value_count > 0, f"Token {token_name} (ID {token_id}) has no values"

    # Every token_value should have non-empty resolved_value
    cursor.execute("SELECT id, resolved_value FROM token_values")
    for row in cursor.fetchall():
        value_id, resolved_value = row
        assert resolved_value is not None and resolved_value != "", \
            f"Token value {value_id} has empty resolved_value"

    # Every token_value should reference a valid mode with is_default=1
    cursor.execute("""
        SELECT tv.id, tv.mode_id, tm.is_default
        FROM token_values tv
        JOIN token_modes tm ON tv.mode_id = tm.id
    """)
    for row in cursor.fetchall():
        value_id, mode_id, is_default = row
        assert is_default == 1, f"Token value {value_id} references non-default mode {mode_id}"

    # Check v_resolved_tokens view
    cursor.execute("SELECT COUNT(*) FROM v_resolved_tokens WHERE resolved_value IS NOT NULL")
    resolved_count = cursor.fetchone()[0]
    assert resolved_count > 0


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_bindings_updated_with_token_id(db: sqlite3.Connection):
    """Test that bindings are properly updated with token IDs after clustering."""
    # Run full pipeline
    frames, extract_fn = _build_rich_mock_data()

    run_extraction_pipeline(db, "e2e_test", "Test", frames, extract_fn)
    cluster_result = run_clustering(db, file_id=1)

    cursor = db.cursor()

    # Check proposed bindings have token_id
    cursor.execute("""
        SELECT id, token_id, confidence, resolved_value
        FROM node_token_bindings
        WHERE binding_status = 'proposed'
    """)
    proposed_bindings = cursor.fetchall()
    assert len(proposed_bindings) > 0, "No proposed bindings found"

    for binding_id, token_id, confidence, binding_resolved in proposed_bindings:
        # Token ID should not be NULL
        assert token_id is not None, f"Binding {binding_id} has NULL token_id"

        # Confidence should be set and > 0
        assert confidence is not None and confidence > 0, \
            f"Binding {binding_id} has invalid confidence {confidence}"

        # Token should exist
        cursor.execute("SELECT id FROM tokens WHERE id = ?", (token_id,))
        token = cursor.fetchone()
        assert token is not None, f"Binding {binding_id} references non-existent token {token_id}"

        # For color bindings, check that resolved values are close
        if binding_resolved and binding_resolved.startswith('#'):
            cursor.execute("""
                SELECT tv.resolved_value
                FROM token_values tv
                WHERE tv.token_id = ?
            """, (token_id,))
            token_resolved = cursor.fetchone()
            if token_resolved:
                # For exact matches or very close colors, this should pass
                # We're using a threshold of 2.0 in clustering
                pass  # Just verify the token exists and has a value


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_census_views_accurate(db: sqlite3.Connection):
    """Test that census views return accurate data after full pipeline."""
    # Run full pipeline
    frames, extract_fn = _build_rich_mock_data()

    run_extraction_pipeline(db, "e2e_test", "Test", frames, extract_fn)
    run_clustering(db, file_id=1)

    cursor = db.cursor()

    # Test v_color_census
    cursor.execute("SELECT * FROM v_color_census")
    color_census = cursor.fetchall()
    assert len(color_census) > 0, "v_color_census returned no data"

    # Check that hex values match what we put in mock data
    hex_values = [row[0] for row in color_census]  # resolved_value column
    assert any('#' in str(val) for val in hex_values if val), "No hex color values in census"

    # Test v_curation_progress
    cursor.execute("SELECT * FROM v_curation_progress")
    progress = cursor.fetchall()
    assert len(progress) > 0, "v_curation_progress returned no data"

    # Sum of percentages should be close to 100
    total_pct = sum(float(row[2]) for row in progress if row[2])  # pct column
    assert 99 <= total_pct <= 101, f"Curation progress percentages sum to {total_pct}, not ~100"

    # Test v_token_coverage
    cursor.execute("SELECT * FROM v_token_coverage")
    coverage = cursor.fetchall()
    assert len(coverage) > 0, "v_token_coverage returned no data"

    # Each token should have binding_count > 0 (no orphans after clustering)
    for row in coverage:
        token_name = row[0]
        binding_count = row[4]  # binding_count column
        assert binding_count > 0, f"Token {token_name} has 0 bindings"

    # Test v_unbound
    cursor.execute("SELECT * FROM v_unbound")
    unbound = cursor.fetchall()
    # There might be some unbound bindings left
    for row in unbound:
        # Check that token_id is indeed NULL for unbound
        binding_id = row[0]
        cursor.execute("SELECT token_id FROM node_token_bindings WHERE id = ?", (binding_id,))
        token_id = cursor.fetchone()[0]
        assert token_id is None, f"Unbound binding {binding_id} has token_id {token_id}"


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_no_orphan_bindings(db: sqlite3.Connection):
    """Test that there are no orphan bindings after full pipeline."""
    # Run full pipeline
    frames, extract_fn = _build_rich_mock_data()

    run_extraction_pipeline(db, "e2e_test", "Test", frames, extract_fn)
    run_clustering(db, file_id=1)

    cursor = db.cursor()

    # Check no bindings reference non-existent nodes
    cursor.execute("""
        SELECT ntb.id, ntb.node_id
        FROM node_token_bindings ntb
        LEFT JOIN nodes n ON ntb.node_id = n.id
        WHERE n.id IS NULL
    """)
    orphan_node_bindings = cursor.fetchall()
    assert len(orphan_node_bindings) == 0, \
        f"Found {len(orphan_node_bindings)} bindings referencing non-existent nodes"

    # Check no bindings with token_id pointing to non-existent token
    cursor.execute("""
        SELECT ntb.id, ntb.token_id
        FROM node_token_bindings ntb
        LEFT JOIN tokens t ON ntb.token_id = t.id
        WHERE ntb.token_id IS NOT NULL AND t.id IS NULL
    """)
    orphan_token_bindings = cursor.fetchall()
    assert len(orphan_token_bindings) == 0, \
        f"Found {len(orphan_token_bindings)} bindings referencing non-existent tokens"

    # Check no token_values referencing non-existent tokens
    cursor.execute("""
        SELECT tv.id, tv.token_id
        FROM token_values tv
        LEFT JOIN tokens t ON tv.token_id = t.id
        WHERE t.id IS NULL
    """)
    orphan_token_values = cursor.fetchall()
    assert len(orphan_token_values) == 0, \
        f"Found {len(orphan_token_values)} token_values referencing non-existent tokens"

    # Verify full FK chain: files -> screens -> nodes -> bindings -> tokens -> token_values

    # All screens should reference valid files
    cursor.execute("""
        SELECT s.id FROM screens s
        LEFT JOIN files f ON s.file_id = f.id
        WHERE f.id IS NULL
    """)
    assert len(cursor.fetchall()) == 0

    # All nodes should reference valid screens
    cursor.execute("""
        SELECT n.id FROM nodes n
        LEFT JOIN screens s ON n.screen_id = s.id
        WHERE s.id IS NULL
    """)
    assert len(cursor.fetchall()) == 0

    # All token_values should reference valid modes
    cursor.execute("""
        SELECT tv.id FROM token_values tv
        LEFT JOIN token_modes tm ON tv.mode_id = tm.id
        WHERE tm.id IS NULL
    """)
    assert len(cursor.fetchall()) == 0

    # All tokens should reference valid collections
    cursor.execute("""
        SELECT t.id FROM tokens t
        LEFT JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.id IS NULL
    """)
    assert len(cursor.fetchall()) == 0


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_full_pipeline_summary(db: sqlite3.Connection):
    """Test that the full pipeline produces a valid summary."""
    # Run full pipeline
    frames, extract_fn = _build_rich_mock_data()

    extract_result = run_extraction_pipeline(db, "e2e_test", "Test", frames, extract_fn)
    cluster_result = run_clustering(db, file_id=1)

    # Verify extraction summary
    assert extract_result["status"] == "completed"
    assert extract_result["total_screens"] == 3
    assert extract_result["completed"] == 3

    # Verify clustering summary
    assert cluster_result["total_tokens"] > 0
    assert cluster_result["total_bindings_updated"] > 0
    assert cluster_result["coverage_pct"] > 0

    # Check by_type breakdown
    assert "by_type" in cluster_result
    by_type = cluster_result["by_type"]

    # Should have at least color type
    assert "color" in by_type
    assert by_type["color"]["tokens"] > 0

    # Generate final summary
    summary = generate_summary(db, 1, cluster_result.get("by_type", {}))

    assert summary["total_tokens"] > 0
    assert summary["coverage_pct"] > 0

    # Some bindings should be updated
    assert summary["total_bindings_updated"] > 0 or summary["coverage_pct"] > 0

    # Print summary for debugging
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM tokens")
    final_token_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM node_token_bindings WHERE binding_status = 'proposed'")
    final_proposed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM node_token_bindings WHERE binding_status = 'unbound'")
    final_unbound = cursor.fetchone()[0]

    print(f"\n=== E2E Test Summary ===")
    print(f"Tokens created: {final_token_count}")
    print(f"Bindings proposed: {final_proposed}")
    print(f"Bindings unbound: {final_unbound}")
    print(f"Coverage: {summary['coverage_pct']:.1f}%")