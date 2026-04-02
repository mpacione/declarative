"""Tests for screen extraction script generator."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import pytest

from dd.db import init_db
from dd.extract_screens import (
    compute_is_semantic,
    generate_extraction_script,
    insert_nodes,
    parse_extraction_response,
    update_screen_status,
)


def test_generate_extraction_script_basic():
    script = generate_extraction_script("100:1")
    assert "100:1" in script
    assert len(script) < 50000
    assert "function extractScreen(screenId)" in script
    assert 'return extractScreen("100:1");' in script


def test_generate_extraction_script_contains_expected_elements():
    script = generate_extraction_script("2219:235687")
    assert "figma.getNodeById" in script or "getNodeById" in script
    assert "function walk(node, parentIdx, depth)" in script
    assert "fills" in script
    assert "strokes" in script
    assert "effects" in script
    assert "cornerRadius" in script
    assert "layoutMode" in script
    assert "fontName" in script
    assert "characters" in script


def test_parse_extraction_response_minimal():
    response = [
        {
            "figma_node_id": "1:1",
            "name": "Frame 1",
            "node_type": "FRAME",
            "parent_idx": None,
            "depth": 0,
            "sort_order": 0,
        }
    ]
    parsed = parse_extraction_response(response)
    assert len(parsed) == 1
    assert parsed[0]["figma_node_id"] == "1:1"
    assert parsed[0]["name"] == "Frame 1"
    assert parsed[0]["node_type"] == "FRAME"
    assert parsed[0]["depth"] == 0
    assert parsed[0]["sort_order"] == 0


def test_parse_extraction_response_with_visual_properties():
    response = [
        {
            "figma_node_id": "1:2",
            "name": "Rectangle",
            "node_type": "RECTANGLE",
            "x": 10.5,
            "y": 20.0,
            "width": 100.0,
            "height": 50.0,
            "fills": [{"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0, "a": 1}}],
            "strokes": [],
            "visible": True,
            "opacity": 0.8,
            "corner_radius": 8,
        }
    ]
    parsed = parse_extraction_response(response)
    assert parsed[0]["x"] == 10.5
    assert parsed[0]["y"] == 20.0
    assert parsed[0]["width"] == 100.0
    assert parsed[0]["height"] == 50.0
    assert parsed[0]["visible"] == 1  # Converted from boolean
    assert parsed[0]["opacity"] == 0.8
    assert parsed[0]["corner_radius"] == "8"  # Converted to string
    assert isinstance(parsed[0]["fills"], str)  # JSON string
    assert isinstance(parsed[0]["strokes"], str)  # JSON string


def test_parse_extraction_response_mixed_corner_radius():
    response = [
        {
            "figma_node_id": "1:3",
            "name": "Rounded",
            "node_type": "RECTANGLE",
            "corner_radius": {"tl": 8, "tr": 8, "bl": 0, "br": 0},
        }
    ]
    parsed = parse_extraction_response(response)
    corner_radius = parsed[0]["corner_radius"]
    assert isinstance(corner_radius, str)
    cr_obj = json.loads(corner_radius)
    assert cr_obj["tl"] == 8
    assert cr_obj["tr"] == 8
    assert cr_obj["bl"] == 0
    assert cr_obj["br"] == 0


def test_parse_extraction_response_text_node():
    response = [
        {
            "figma_node_id": "1:4",
            "name": "Label",
            "node_type": "TEXT",
            "font_family": "Inter",
            "font_weight": 500,
            "font_size": 16.0,
            "line_height": {"value": 24, "unit": "PIXELS"},
            "letter_spacing": {"value": 0, "unit": "PIXELS"},
            "text_align": "LEFT",
            "text_content": "Hello World",
        }
    ]
    parsed = parse_extraction_response(response)
    assert parsed[0]["font_family"] == "Inter"
    assert parsed[0]["font_weight"] == 500
    assert parsed[0]["font_size"] == 16.0
    assert isinstance(parsed[0]["line_height"], str)
    assert isinstance(parsed[0]["letter_spacing"], str)
    assert parsed[0]["text_align"] == "LEFT"
    assert parsed[0]["text_content"] == "Hello World"


def test_extraction_script_captures_layout_positioning():
    script = generate_extraction_script("1:1")
    assert "layoutPositioning" in script


def test_extraction_script_captures_grid_properties():
    script = generate_extraction_script("1:1")
    assert "gridRowCount" in script
    assert "gridColumnCount" in script


def test_parse_layout_positioning():
    response = [
        {
            "figma_node_id": "1:5",
            "name": "Floating Badge",
            "node_type": "FRAME",
            "layout_positioning": "ABSOLUTE",
        }
    ]
    parsed = parse_extraction_response(response)
    assert parsed[0]["layout_positioning"] == "ABSOLUTE"


def test_parse_grid_properties():
    response = [
        {
            "figma_node_id": "1:6",
            "name": "Grid Container",
            "node_type": "FRAME",
            "layout_mode": "GRID",
            "grid_row_count": 3,
            "grid_column_count": 4,
            "grid_row_gap": 16.0,
            "grid_column_gap": 12.0,
            "grid_row_sizes": [{"type": "FIXED", "value": 100}, {"type": "FILL", "value": 1}],
            "grid_column_sizes": [{"type": "FIXED", "value": 200}],
        }
    ]
    parsed = parse_extraction_response(response)
    assert parsed[0]["grid_row_count"] == 3
    assert parsed[0]["grid_column_count"] == 4
    assert parsed[0]["grid_row_gap"] == 16.0
    assert parsed[0]["grid_column_gap"] == 12.0
    assert isinstance(parsed[0]["grid_row_sizes"], str)
    assert isinstance(parsed[0]["grid_column_sizes"], str)


def test_insert_nodes_with_layout_positioning():
    conn = init_db(":memory:")
    conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test File')")
    conn.execute("INSERT INTO screens (file_id, figma_node_id, name, width, height) VALUES (1, '1:0', 'Screen', 375, 667)")

    nodes = [
        {
            "figma_node_id": "1:7",
            "name": "Absolute Child",
            "node_type": "FRAME",
            "parent_idx": None,
            "depth": 0,
            "sort_order": 0,
            "is_semantic": 0,
            "layout_positioning": "ABSOLUTE",
        },
    ]
    node_ids = insert_nodes(conn, 1, nodes)
    assert len(node_ids) == 1

    row = conn.execute("SELECT layout_positioning FROM nodes WHERE id = ?", (node_ids[0],)).fetchone()
    assert row[0] == "ABSOLUTE"


def test_insert_nodes_with_grid_properties():
    conn = init_db(":memory:")
    conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test File')")
    conn.execute("INSERT INTO screens (file_id, figma_node_id, name, width, height) VALUES (1, '1:0', 'Screen', 375, 667)")

    nodes = [
        {
            "figma_node_id": "1:8",
            "name": "Grid Frame",
            "node_type": "FRAME",
            "parent_idx": None,
            "depth": 0,
            "sort_order": 0,
            "is_semantic": 1,
            "layout_mode": "GRID",
            "grid_row_count": 2,
            "grid_column_count": 3,
            "grid_row_gap": 8.0,
            "grid_column_gap": 8.0,
            "grid_row_sizes": json.dumps([{"type": "FIXED", "value": 100}]),
            "grid_column_sizes": json.dumps([{"type": "FILL", "value": 1}]),
        },
    ]
    node_ids = insert_nodes(conn, 1, nodes)
    assert len(node_ids) == 1

    row = conn.execute(
        "SELECT layout_mode, grid_row_count, grid_column_count, grid_row_gap, grid_column_gap FROM nodes WHERE id = ?",
        (node_ids[0],),
    ).fetchone()
    assert row[0] == "GRID"
    assert row[1] == 2
    assert row[2] == 3
    assert row[3] == 8.0
    assert row[4] == 8.0


def test_compute_is_semantic_text_node():
    nodes = [
        {"node_type": "TEXT", "name": "Label", "parent_idx": None}
    ]
    result = compute_is_semantic(nodes)
    assert result[0]["is_semantic"] == 1


def test_compute_is_semantic_instance_node():
    nodes = [
        {"node_type": "INSTANCE", "name": "Button Instance", "parent_idx": None}
    ]
    result = compute_is_semantic(nodes)
    assert result[0]["is_semantic"] == 1


def test_compute_is_semantic_component_node():
    nodes = [
        {"node_type": "COMPONENT", "name": "Button Component", "parent_idx": None}
    ]
    result = compute_is_semantic(nodes)
    assert result[0]["is_semantic"] == 1


def test_compute_is_semantic_frame_with_layout():
    nodes = [
        {"node_type": "FRAME", "name": "Container", "layout_mode": "HORIZONTAL", "parent_idx": None}
    ]
    result = compute_is_semantic(nodes)
    assert result[0]["is_semantic"] == 1


def test_compute_is_semantic_user_named_node():
    nodes = [
        {"node_type": "FRAME", "name": "Navigation Bar", "parent_idx": None},
        {"node_type": "FRAME", "name": "Frame 123", "parent_idx": None},
        {"node_type": "GROUP", "name": "Group 456", "parent_idx": None},
        {"node_type": "RECTANGLE", "name": "Rectangle 789", "parent_idx": None},
        {"node_type": "VECTOR", "name": "Vector 012", "parent_idx": None},
        {"node_type": "FRAME", "name": "Custom Container", "parent_idx": None},
    ]
    result = compute_is_semantic(nodes)
    assert result[0]["is_semantic"] == 1  # "Navigation Bar" - user-named
    assert result[1]["is_semantic"] == 0  # "Frame 123" - default name
    assert result[2]["is_semantic"] == 0  # "Group 456" - default name
    assert result[3]["is_semantic"] == 0  # "Rectangle 789" - default name
    assert result[4]["is_semantic"] == 0  # "Vector 012" - default name
    assert result[5]["is_semantic"] == 1  # "Custom Container" - user-named


def test_compute_is_semantic_parent_with_semantic_children():
    nodes = [
        {"node_type": "FRAME", "name": "Frame 1", "parent_idx": None},  # idx 0
        {"node_type": "TEXT", "name": "Label 1", "parent_idx": 0},      # idx 1 - semantic
        {"node_type": "RECTANGLE", "name": "Rectangle 1", "parent_idx": 0},  # idx 2
    ]
    result = compute_is_semantic(nodes)
    assert result[1]["is_semantic"] == 1  # Text node is semantic
    assert result[2]["is_semantic"] == 0  # Rectangle is not semantic
    assert result[0]["is_semantic"] == 1  # Parent has 2+ children with 1+ semantic


def test_compute_is_semantic_nested_hierarchy():
    nodes = [
        {"node_type": "FRAME", "name": "Frame 1", "parent_idx": None},  # idx 0
        {"node_type": "FRAME", "name": "Frame 2", "parent_idx": 0},     # idx 1
        {"node_type": "TEXT", "name": "Label", "parent_idx": 1},        # idx 2 - semantic
        {"node_type": "RECTANGLE", "name": "Rectangle 1", "parent_idx": 1},    # idx 3
    ]
    result = compute_is_semantic(nodes)
    assert result[2]["is_semantic"] == 1  # Text is semantic
    assert result[3]["is_semantic"] == 0  # Rectangle is not semantic
    assert result[1]["is_semantic"] == 1  # Frame 2 has 2+ children with 1 semantic
    assert result[0]["is_semantic"] == 0  # Frame 1 has only 1 child (Frame 2), not 2+


def test_insert_nodes_basic():
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test File')")
    conn.execute("INSERT INTO screens (file_id, figma_node_id, name, width, height) VALUES (1, '1:0', 'Screen', 375, 667)")

    nodes = [
        {
            "figma_node_id": "1:1",
            "name": "Root Frame",
            "node_type": "FRAME",
            "parent_idx": None,
            "depth": 0,
            "sort_order": 0,
            "is_semantic": 1,
            "x": 0, "y": 0, "width": 375, "height": 667,
        },
        {
            "figma_node_id": "1:2",
            "name": "Child Text",
            "node_type": "TEXT",
            "parent_idx": 0,
            "depth": 1,
            "sort_order": 0,
            "is_semantic": 1,
            "text_content": "Hello",
            "font_family": "Inter",
            "font_size": 16,
        },
    ]

    node_ids = insert_nodes(conn, 1, nodes)
    assert len(node_ids) == 2

    # Verify insertions
    cursor = conn.execute("SELECT figma_node_id, parent_id, name, node_type FROM nodes ORDER BY id")
    rows = cursor.fetchall()
    assert len(rows) == 2
    assert tuple(rows[0]) == ("1:1", None, "Root Frame", "FRAME")
    assert rows[1]["figma_node_id"] == "1:2"
    assert rows[1]["parent_id"] == node_ids[0]  # Parent ID should be first node's ID
    assert rows[1]["name"] == "Child Text"
    assert rows[1]["node_type"] == "TEXT"

    conn.close()


def test_insert_nodes_upsert():
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test File')")
    conn.execute("INSERT INTO screens (file_id, figma_node_id, name, width, height) VALUES (1, '1:0', 'Screen', 375, 667)")

    nodes = [
        {
            "figma_node_id": "1:1",
            "name": "Frame",
            "node_type": "FRAME",
            "parent_idx": None,
            "depth": 0,
            "sort_order": 0,
            "is_semantic": 0,
        }
    ]

    # First insert
    node_ids1 = insert_nodes(conn, 1, nodes)

    # Update with different data
    nodes[0]["name"] = "Updated Frame"
    nodes[0]["is_semantic"] = 1

    # Second insert (should update)
    node_ids2 = insert_nodes(conn, 1, nodes)

    # Should return same IDs
    assert node_ids1 == node_ids2

    # Verify update
    cursor = conn.execute("SELECT name, is_semantic FROM nodes WHERE figma_node_id = '1:1'")
    row = cursor.fetchone()
    assert tuple(row) == ("Updated Frame", 1)

    # Verify no duplicates
    cursor = conn.execute("SELECT COUNT(*) FROM nodes")
    assert cursor.fetchone()[0] == 1

    conn.close()


def test_parse_extraction_response_component_instance():
    response = [
        {
            "figma_node_id": "1:5",
            "name": "Button Instance",
            "node_type": "INSTANCE",
            "component_figma_id": "100:1",
            "parent_idx": None,
        }
    ]
    parsed = parse_extraction_response(response)
    assert parsed[0]["component_figma_id"] == "100:1"
    assert parsed[0]["node_type"] == "INSTANCE"


def test_generate_extraction_script_handles_corner_radius():
    script = generate_extraction_script("123:456")
    assert "figma.mixed" in script
    assert "topLeftRadius" in script
    assert "topRightRadius" in script
    assert "bottomLeftRadius" in script
    assert "bottomRightRadius" in script


def test_parse_extraction_response_auto_layout():
    response = [
        {
            "figma_node_id": "1:6",
            "name": "Auto Layout Frame",
            "node_type": "FRAME",
            "layout_mode": "HORIZONTAL",
            "padding_top": 8,
            "padding_right": 12,
            "padding_bottom": 8,
            "padding_left": 12,
            "item_spacing": 16,
            "counter_axis_spacing": 0,
            "primary_align": "CENTER",
            "counter_align": "MIN",
            "layout_sizing_h": "HUG",
            "layout_sizing_v": "FIXED",
        }
    ]
    parsed = parse_extraction_response(response)
    assert parsed[0]["layout_mode"] == "HORIZONTAL"
    assert parsed[0]["padding_top"] == 8.0
    assert parsed[0]["padding_right"] == 12.0
    assert parsed[0]["item_spacing"] == 16.0
    assert parsed[0]["primary_align"] == "CENTER"
    assert parsed[0]["layout_sizing_h"] == "HUG"


def test_update_screen_status():
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test File')")
    conn.execute("INSERT INTO extraction_runs (file_id, status) VALUES (1, 'running')")
    conn.execute("INSERT INTO screens (file_id, figma_node_id, name, width, height) VALUES (1, '1:0', 'Screen', 375, 667)")
    conn.execute("INSERT INTO screen_extraction_status (run_id, screen_id, status) VALUES (1, 1, 'pending')")

    # Update to in_progress
    update_screen_status(conn, 1, 1, "in_progress")
    cursor = conn.execute("SELECT status, started_at FROM screen_extraction_status WHERE run_id = 1 AND screen_id = 1")
    row = cursor.fetchone()
    assert row[0] == "in_progress"
    assert row[1] is not None  # started_at should be set

    # Update to completed with counts
    update_screen_status(conn, 1, 1, "completed", node_count=50, binding_count=25)
    cursor = conn.execute("SELECT status, completed_at, node_count, binding_count FROM screen_extraction_status WHERE run_id = 1 AND screen_id = 1")
    row = cursor.fetchone()
    assert row[0] == "completed"
    assert row[1] is not None  # completed_at should be set
    assert row[2] == 50
    assert row[3] == 25

    # Update to failed with error
    update_screen_status(conn, 1, 1, "failed", error="Connection timeout")
    cursor = conn.execute("SELECT status, error FROM screen_extraction_status WHERE run_id = 1 AND screen_id = 1")
    row = cursor.fetchone()
    assert row[0] == "failed"
    assert row[1] == "Connection timeout"

    conn.close()