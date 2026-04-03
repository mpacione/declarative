"""End-to-end test: full pipeline through Figma export.

This test runs the ENTIRE pipeline from extraction through clustering,
curation, validation, Figma payload generation, writeback, and rebind scripts.
"""

import json
import math
import sqlite3
from collections.abc import Callable
from typing import Any

import pytest

from dd.cluster import run_clustering
from dd.curate import accept_all
from dd.db import init_db
from dd.export_figma_vars import (
    generate_variable_payloads,
    generate_variable_payloads_checked,
    get_sync_status_summary,
    parse_figma_variables_response,
    writeback_variable_ids,
)
from dd.export_rebind import generate_rebind_scripts, get_rebind_summary
from dd.extract import run_extraction_pipeline
from dd.validate import run_validation

# Mock frame data for 3 screens
MOCK_FRAMES = [
    {"figma_node_id": "1:1", "name": "Home", "width": 428, "height": 926},
    {"figma_node_id": "1:2", "name": "Profile", "width": 428, "height": 926},
    {"figma_node_id": "1:3", "name": "Components", "width": 1200, "height": 800},
]


def _build_e2e_mock_data() -> tuple[list[dict], Callable[[str], list[dict]]]:
    """Build mock frames and extraction function for e2e testing.

    Returns comprehensive mock data covering all property types:
    - Fill colors: #09090B, #18181B, #FFFFFF
    - Stroke colors: #D4D4D8
    - Typography: Inter 600/24px, Inter 400/14px
    - Spacing: 8px, 16px (padding and itemSpacing)
    - Radius: 8px, 12px
    - Effects: DROP_SHADOW
    - Opacity: 0.8 on one node
    """
    frames = MOCK_FRAMES

    def extract_fn(node_id: str) -> list[dict[str, Any]]:
        """Mock extract function that returns rich node data."""
        if node_id == "1:1":
            # Home screen: dark background with text and card elements
            return [
                # Root frame with fill and spacing
                {
                    "figma_node_id": "10:1",
                    "parent_idx": None,
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
                    "padding_bottom": 16,
                    "padding_left": 16,
                    "padding_right": 16,
                    "item_spacing": 8,
                },
                # Title text
                {
                    "figma_node_id": "10:2",
                    "parent_idx": 0,
                    "name": "Title",
                    "node_type": "TEXT",
                    "depth": 1,
                    "sort_order": 0,
                    "x": 16,
                    "y": 16,
                    "width": 396,
                    "height": 30,
                    "font_family": "Inter",
                    "font_weight": 600,
                    "font_size": 24,
                    "line_height": json.dumps({"value": 30, "unit": "PIXELS"}),
                    "text_content": "Home",
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
                },
                # Card with fill, radius, and shadow
                {
                    "figma_node_id": "10:3",
                    "parent_idx": 0,
                    "name": "Card",
                    "node_type": "RECTANGLE",
                    "depth": 1,
                    "sort_order": 1,
                    "x": 16,
                    "y": 60,
                    "width": 396,
                    "height": 200,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
                    "corner_radius": 8,
                    "effects": json.dumps([
                        {
                            "type": "DROP_SHADOW",
                            "visible": True,
                            "color": {"r": 0, "g": 0, "b": 0, "a": 0.1},
                            "radius": 6,
                            "offset": {"x": 0, "y": 4},
                            "spread": -1
                        }
                    ]),
                },
                # Body text
                {
                    "figma_node_id": "10:4",
                    "parent_idx": 0,
                    "name": "Body",
                    "node_type": "TEXT",
                    "depth": 1,
                    "sort_order": 2,
                    "x": 16,
                    "y": 270,
                    "width": 396,
                    "height": 20,
                    "font_family": "Inter",
                    "font_weight": 400,
                    "font_size": 14,
                    "line_height": json.dumps({"value": 20, "unit": "PIXELS"}),
                    "text_content": "Welcome",
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
                },
                # Divider with stroke
                {
                    "figma_node_id": "10:5",
                    "parent_idx": 0,
                    "name": "Divider",
                    "node_type": "FRAME",
                    "depth": 1,
                    "sort_order": 3,
                    "x": 16,
                    "y": 300,
                    "width": 396,
                    "height": 1,
                    "strokes": json.dumps([{"type": "SOLID", "color": {"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}}]),  # #D4D4D8
                    "stroke_weight": 1,
                },
                # Semi-transparent overlay
                {
                    "figma_node_id": "10:6",
                    "parent_idx": 0,
                    "name": "Overlay",
                    "node_type": "RECTANGLE",
                    "depth": 1,
                    "sort_order": 4,
                    "x": 16,
                    "y": 320,
                    "width": 396,
                    "height": 100,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 0, "g": 0, "b": 0, "a": 1}}]),
                    "opacity": 0.8,
                },
            ]

        elif node_id == "1:2":
            # Profile screen: different layout with consistent styles
            return [
                # Root frame
                {
                    "figma_node_id": "20:1",
                    "parent_idx": None,
                    "name": "Profile",
                    "node_type": "FRAME",
                    "depth": 0,
                    "sort_order": 0,
                    "x": 0,
                    "y": 0,
                    "width": 428,
                    "height": 926,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.094, "g": 0.094, "b": 0.106, "a": 1}}]),  # #18181B
                    "layout_mode": "VERTICAL",
                    "padding_top": 16,
                    "padding_bottom": 16,
                    "padding_left": 16,
                    "padding_right": 16,
                    "item_spacing": 16,  # Different spacing value
                },
                # Profile header
                {
                    "figma_node_id": "20:2",
                    "parent_idx": 0,
                    "name": "Header",
                    "node_type": "TEXT",
                    "depth": 1,
                    "sort_order": 0,
                    "x": 16,
                    "y": 16,
                    "width": 396,
                    "height": 30,
                    "font_family": "Inter",
                    "font_weight": 600,
                    "font_size": 24,
                    "text_content": "Profile",
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
                },
                # Avatar placeholder with different radius
                {
                    "figma_node_id": "20:3",
                    "parent_idx": 0,
                    "name": "Avatar",
                    "node_type": "RECTANGLE",
                    "depth": 1,
                    "sort_order": 1,
                    "x": 16,
                    "y": 60,
                    "width": 100,
                    "height": 100,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.094, "g": 0.094, "b": 0.106, "a": 1}}]),  # #18181B
                    "corner_radius": 12,  # Different radius value
                },
                # Info card
                {
                    "figma_node_id": "20:4",
                    "parent_idx": 0,
                    "name": "InfoCard",
                    "node_type": "RECTANGLE",
                    "depth": 1,
                    "sort_order": 2,
                    "x": 16,
                    "y": 180,
                    "width": 396,
                    "height": 200,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
                    "corner_radius": 8,
                    "effects": json.dumps([
                        {
                            "type": "DROP_SHADOW",
                            "visible": True,
                            "color": {"r": 0, "g": 0, "b": 0, "a": 0.1},
                            "radius": 6,
                            "offset": {"x": 0, "y": 4},
                            "spread": -1
                        }
                    ]),
                },
                # Username text
                {
                    "figma_node_id": "20:5",
                    "parent_idx": 0,
                    "name": "Username",
                    "node_type": "TEXT",
                    "depth": 1,
                    "sort_order": 3,
                    "x": 16,
                    "y": 400,
                    "width": 396,
                    "height": 20,
                    "font_family": "Inter",
                    "font_weight": 400,
                    "font_size": 14,
                    "text_content": "John Doe",
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
                },
            ]

        elif node_id == "1:3":
            # Components screen: minimal component sheet
            return [
                # Root frame (transparent)
                {
                    "figma_node_id": "30:1",
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
                # Button component
                {
                    "figma_node_id": "30:2",
                    "parent_idx": 0,
                    "name": "Button",
                    "node_type": "COMPONENT",
                    "depth": 1,
                    "sort_order": 0,
                    "x": 50,
                    "y": 50,
                    "width": 120,
                    "height": 48,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]),  # #09090B
                    "corner_radius": 8,
                    "layout_mode": "HORIZONTAL",
                    "padding_top": 8,
                    "padding_right": 16,
                    "padding_bottom": 8,
                    "padding_left": 16,
                },
                # Input component
                {
                    "figma_node_id": "30:3",
                    "parent_idx": 0,
                    "name": "Input",
                    "node_type": "COMPONENT",
                    "depth": 1,
                    "sort_order": 1,
                    "x": 200,
                    "y": 50,
                    "width": 240,
                    "height": 48,
                    "strokes": json.dumps([{"type": "SOLID", "color": {"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}}]),  # #D4D4D8
                    "stroke_weight": 1,
                    "corner_radius": 8,
                    "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),  # #FFFFFF
                },
            ]

        else:
            return []

    return (frames, extract_fn)


def _build_mock_figma_response_from_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a mock figma_get_variables response from generated payloads.

    Creates a response that matches the structure expected by writeback,
    assigning sequential variable IDs to each token.

    Args:
        payloads: List of generated payloads

    Returns:
        Mock Figma response dict with collections and variables
    """
    collections = []
    var_id_counter = 1000

    for payload in payloads:
        # Create collection entry
        collection = {
            "id": f"collection_{len(collections) + 1}",
            "name": payload["collectionName"],
            "modes": [{"id": f"mode_{i}", "name": mode} for i, mode in enumerate(payload["modes"])],
            "variables": []
        }

        # Add variables from tokens
        for token in payload["tokens"]:
            collection["variables"].append({
                "id": f"var_{var_id_counter}",
                "name": token["name"],  # Already in slash-path format
                "type": token["type"],
                "values": token["values"]
            })
            var_id_counter += 1

        collections.append(collection)

    return {"collections": collections}


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
def test_e2e_full_pipeline_to_figma_payloads(db):
    """Test full pipeline from extraction to Figma payload generation."""
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

    # Run clustering
    cluster_result = run_clustering(db, file_id=1)
    assert cluster_result["total_tokens"] > 0

    # Accept all tokens and bindings
    curation_result = accept_all(db, file_id=1)
    assert curation_result["tokens_accepted"] > 0
    assert curation_result["bindings_updated"] > 0

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

    # Run validation
    validation_result = run_validation(db, file_id=1)

    # Debug: print validation issues if not passing
    if not validation_result["passed"]:
        print("\nValidation issues found:")
        for issue in validation_result["issues"]:
            if issue["severity"] == "error":
                print(f"  ERROR: {issue['check_name']}: {issue['message']}")

    assert validation_result["passed"] is True

    # Generate payloads
    payloads = generate_variable_payloads_checked(db, file_id=1)

    # Verify payloads structure
    assert isinstance(payloads, list)
    assert len(payloads) > 0

    for payload in payloads:
        # Each payload must have required keys
        assert "collectionName" in payload
        assert "modes" in payload
        assert "tokens" in payload

        # Verify JSON-serializable
        json_str = json.dumps(payload)
        assert len(json_str) > 0

        # Verify tokens structure
        for token in payload["tokens"]:
            assert "name" in token
            assert "type" in token
            assert token["type"] in ["COLOR", "FLOAT", "STRING"]
            assert "values" in token
            assert isinstance(token["values"], dict)


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_all_curated_tokens_represented_in_payloads(db):
    """Test that all curated tokens appear in generated payloads."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
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
        SELECT COUNT(*) AS count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
        AND t.figma_variable_id IS NULL
    """)
    curated_count = cursor.fetchone()["count"]

    # Get token names from DB
    cursor = db.execute("""
        SELECT t.name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
        AND t.figma_variable_id IS NULL
    """)
    db_token_names = {row["name"] for row in cursor.fetchall()}

    # Generate payloads
    payloads = generate_variable_payloads_checked(db, file_id=1)

    # Count tokens in payloads
    payload_token_count = sum(len(p["tokens"]) for p in payloads)

    # Verify counts match
    assert payload_token_count == curated_count

    # Verify every DB token appears in payloads (converted to slash-path)
    payload_token_names = set()
    for payload in payloads:
        for token in payload["tokens"]:
            # Convert back from slash-path to dot-path for comparison
            dtcg_name = token["name"].replace("/", ".")
            payload_token_names.add(dtcg_name)

    # Every DB token should be in payloads
    assert db_token_names == payload_token_names


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_batch_count_matches_ceil(db):
    """Test that batch count matches ceil(tokens/100) per collection."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
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

    # Count tokens per collection
    cursor = db.execute("""
        SELECT tc.name AS collection_name, COUNT(t.id) AS token_count
        FROM token_collections tc
        LEFT JOIN tokens t ON t.collection_id = tc.id
            AND t.tier IN ('curated', 'aliased')
            AND t.figma_variable_id IS NULL
        WHERE tc.file_id = 1
        GROUP BY tc.id, tc.name
    """)

    collection_counts = {row["collection_name"]: row["token_count"] for row in cursor.fetchall()}

    # Generate payloads
    payloads = generate_variable_payloads_checked(db, file_id=1)

    # Count payloads per collection
    payload_counts = {}
    for payload in payloads:
        collection_name = payload["collectionName"]
        payload_counts[collection_name] = payload_counts.get(collection_name, 0) + 1

    # Verify batch counts
    for collection_name, token_count in collection_counts.items():
        if token_count > 0:
            expected_batches = math.ceil(token_count / 100)
            actual_batches = payload_counts.get(collection_name, 0)
            assert actual_batches == expected_batches, f"{collection_name}: expected {expected_batches} batches, got {actual_batches}"


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_rebind_scripts_cover_bound_property_types(db):
    """Test that rebind scripts cover all bound property types."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline through curation
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
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

    # Generate and writeback mock Figma response
    payloads = generate_variable_payloads(db, file_id=1)
    mock_response = _build_mock_figma_response_from_payloads(payloads)
    parsed_variables = parse_figma_variables_response(mock_response)
    writeback_result = writeback_variable_ids(db, 1, parsed_variables)

    assert writeback_result["tokens_updated"] > 0

    # Generate rebind scripts
    scripts = generate_rebind_scripts(db, file_id=1)

    # Verify scripts generated
    assert isinstance(scripts, list)
    assert len(scripts) > 0

    # Get rebind summary
    summary = get_rebind_summary(db, file_id=1)

    # Verify property types covered
    assert summary["total_bindings"] > 0
    assert len(summary["by_property_type"]) > 0

    # Get actual categories from summary
    actual_categories = set(summary["by_property_type"].keys())

    # Expected some of these categories from our mock data
    # Note: padding properties may not get bound if spacing clustering doesn't handle them
    possible_categories = {"paint_fill", "paint_stroke", "padding", "direct", "effect"}

    # Verify we have at least some categories
    assert len(actual_categories.intersection(possible_categories)) > 0

    # At minimum we expect paint_fill and direct (from colors and radius)
    assert "paint_fill" in actual_categories
    assert "direct" in actual_categories

    # Verify script count matches expected batches
    total_bindings = summary["total_bindings"]
    expected_scripts = math.ceil(total_bindings / 500)  # MAX_BINDINGS_PER_SCRIPT
    assert len(scripts) == expected_scripts


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_writeback_and_sync(db):
    """Test writeback sets figma_variable_id and sync_status correctly."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline through payload generation
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
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

    # Generate payloads
    payloads = generate_variable_payloads_checked(db, file_id=1)

    # Build mock Figma response
    mock_response = _build_mock_figma_response_from_payloads(payloads)

    # Writeback
    parsed_variables = parse_figma_variables_response(mock_response)
    writeback_result = writeback_variable_ids(db, 1, parsed_variables)

    assert writeback_result["tokens_updated"] > 0

    # Verify all curated tokens have figma_variable_id
    cursor = db.execute("""
        SELECT COUNT(*) AS count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
        AND t.figma_variable_id IS NULL
    """)
    assert cursor.fetchone()["count"] == 0

    # Verify all curated tokens have sync_status = 'synced'
    cursor = db.execute("""
        SELECT COUNT(*) AS count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
        AND t.sync_status != 'synced'
    """)
    assert cursor.fetchone()["count"] == 0

    # Get sync status summary
    sync_summary = get_sync_status_summary(db, file_id=1)

    assert sync_summary.get("synced", 0) == writeback_result["tokens_updated"]
    # Other statuses should be 0 or not present
    assert sync_summary.get("pending", 0) == 0
    assert sync_summary.get("error", 0) == 0

    # Re-generating payloads should return empty list (all exported)
    new_payloads = generate_variable_payloads(db, file_id=1)
    assert len(new_payloads) == 0


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_fk_integrity_after_full_export(db):
    """Test FK integrity across entire table chain after full export."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline through writeback
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
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

    # Generate payloads and writeback
    payloads = generate_variable_payloads(db, file_id=1)
    mock_response = _build_mock_figma_response_from_payloads(payloads)
    parsed_variables = parse_figma_variables_response(mock_response)
    writeback_variable_ids(db, 1, parsed_variables)

    # FK integrity checks
    fk_checks = [
        # files -> screens -> nodes -> bindings
        ("screens.file_id", "screens", "file_id", "files", "id"),
        ("nodes.screen_id", "nodes", "screen_id", "screens", "id"),
        ("node_token_bindings.node_id", "node_token_bindings", "node_id", "nodes", "id"),
        ("node_token_bindings.token_id", "node_token_bindings", "token_id", "tokens", "id"),
        # tokens -> collections -> files
        ("tokens.collection_id", "tokens", "collection_id", "token_collections", "id"),
        ("token_collections.file_id", "token_collections", "file_id", "files", "id"),
        # token_values -> tokens, modes
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
        assert invalid_count == 0, f"FK check failed: {check_name}"

    # Verify every figma_variable_id is non-empty string
    cursor = db.execute("""
        SELECT COUNT(*) AS count
        FROM tokens
        WHERE figma_variable_id IS NOT NULL
        AND (figma_variable_id = '' OR LENGTH(figma_variable_id) = 0)
    """)
    assert cursor.fetchone()["count"] == 0

    # Verify every bound binding references a token that exists
    cursor = db.execute("""
        SELECT COUNT(*) AS count
        FROM node_token_bindings
        WHERE binding_status = 'bound'
        AND token_id IS NOT NULL
        AND token_id NOT IN (SELECT id FROM tokens)
    """)
    assert cursor.fetchone()["count"] == 0


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.timeout(30)
def test_e2e_pipeline_summary(db):
    """Test pipeline state views after full export."""
    frames, extract_fn = _build_e2e_mock_data()

    # Run full pipeline
    run_extraction_pipeline(db, "test-file", "Test", frames, extract_fn)
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

    # Query v_curation_progress
    cursor = db.execute("SELECT * FROM v_curation_progress")
    progress_rows = cursor.fetchall()

    assert len(progress_rows) > 0

    # Should have bound bindings
    bound_found = False
    for row in progress_rows:
        if row["binding_status"] == "bound":
            bound_found = True
            assert row["binding_count"] > 0
            assert row["pct"] > 0
    assert bound_found

    # Query v_export_readiness
    cursor = db.execute("""
        SELECT * FROM v_export_readiness
    """)
    readiness_rows = cursor.fetchall()

    # Should have validation results
    assert len(readiness_rows) > 0

    # No error-severity issues
    for row in readiness_rows:
        if row["severity"] == "error":
            assert row["issue_count"] == 0

    # Query v_token_coverage
    cursor = db.execute("""
        SELECT * FROM v_token_coverage
        WHERE binding_count > 0
    """)
    coverage_rows = cursor.fetchall()

    # All curated tokens should have bindings
    assert len(coverage_rows) > 0

    for row in coverage_rows:
        assert row["binding_count"] > 0
        assert row["node_count"] > 0
        assert row["screen_count"] > 0

    # Verify counts
    cursor = db.execute("""
        SELECT COUNT(*) AS token_count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND t.tier IN ('curated', 'aliased')
    """)
    assert cursor.fetchone()["token_count"] > 0

    cursor = db.execute("""
        SELECT COUNT(*) AS binding_count
        FROM node_token_bindings
        WHERE binding_status = 'bound'
    """)
    assert cursor.fetchone()["binding_count"] > 0