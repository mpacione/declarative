"""Test fixtures and factory functions for database seeding."""

import json
import sqlite3
from typing import Any


def seed_post_extraction(db: sqlite3.Connection) -> sqlite3.Connection:
    """
    Seed DB with data as if extraction phase completed.
    Includes files, screens, nodes, and unbound bindings.
    """
    # Insert file
    db.execute(
        "INSERT INTO files (id, file_key, name, node_count, screen_count) VALUES (?, ?, ?, ?, ?)",
        (1, "test_file_key_abc123", "Test Design File", 23, 3)
    )

    # Insert screens
    screens = [
        (1, 1, "100:1", "Home", 428, 926, "iphone", 10),
        (2, 1, "100:2", "Settings", 428, 926, "iphone", 8),
        (3, 1, "100:3", "Buttons and Controls", 1200, 800, "component_sheet", 5)
    ]
    db.executemany(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height, device_class, node_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        screens
    )

    # Insert nodes
    # Screen 1: 5 nodes
    nodes_screen1 = [
        # id, screen_id, figma_node_id, parent_id, path, name, node_type, depth, sort_order, is_semantic,
        # x, y, width, height, layout_mode, padding_top, padding_right, padding_bottom, padding_left,
        # item_spacing, counter_axis_spacing, primary_align, counter_align, layout_sizing_h, layout_sizing_v,
        # fills, strokes, effects, corner_radius, font_family, font_weight, font_size, line_height,
        # letter_spacing, text_align, text_content
        (1, 1, "200:1", None, "1", "Container", "FRAME", 0, 0, 1,
         0, 0, 428, 926, "VERTICAL", 16, 16, 16, 16,
         8, None, "MIN", "MIN", "FILL", "FILL",
         json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]), None, None, None,
         None, None, None, None, None, None, None),
        (2, 1, "200:2", 1, "1.1", "Header", "FRAME", 1, 0, 1,
         0, 40, 428, 60, "HORIZONTAL", 12, 12, 12, 12,
         16, None, "SPACE_BETWEEN", "CENTER", "FILL", "HUG",
         json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]), None, None, None,
         None, None, None, None, None, None, None),
        (3, 1, "200:3", 1, "1.2", "Content", "FRAME", 1, 1, 1,
         0, 100, 428, 766, None, None, None, None, None,
         None, None, None, None, None, None,
         json.dumps([{"type": "SOLID", "color": {"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}}]), None, None, None,
         None, None, None, None, None, None, None),
        (4, 1, "200:4", 2, "1.1.1", "Title", "TEXT", 2, 0, 1,
         12, 20, None, None, None, None, None, None, None,
         None, None, None, None, None, None,
         None, None, None, None,
         "Inter", 600, 16, json.dumps({"value": 24, "unit": "PIXELS"}), json.dumps({"value": 0, "unit": "PIXELS"}), "LEFT", "Home Screen"),
        (5, 1, "200:5", 3, "1.2.1", "Card", "RECTANGLE", 2, 0, 0,
         20, 120, 388, 100, None, None, None, None, None,
         None, None, None, None, None, None,
         json.dumps([{"type": "SOLID", "color": {"r": 0.094, "g": 0.094, "b": 0.106, "a": 1}}]), None, None, json.dumps(8),
         None, None, None, None, None, None, None),
    ]

    # Screen 2: 3 nodes
    nodes_screen2 = [
        (6, 2, "200:6", None, "1", "Settings Container", "FRAME", 0, 0, 1,
         0, 0, 428, 926, "VERTICAL", 16, 16, 16, 16,
         8, None, "MIN", "MIN", "FILL", "FILL",
         json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]), None, None, None,
         None, None, None, None, None, None, None),
        (7, 2, "200:7", 6, "1.1", "Settings Title", "TEXT", 1, 0, 1,
         16, 16, None, None, None, None, None, None, None,
         None, None, None, None, None, None,
         None, None, None, None,
         "Inter", 600, 16, None, None, "LEFT", "Settings"),
        (8, 2, "200:8", 6, "1.2", "Button Instance", "INSTANCE", 1, 1, 1,
         16, 100, 120, 40, None, None, None, None, None,
         None, None, None, None, None, None,
         None, None, None, None,
         None, None, None, None, None, None, None),
    ]

    # Screen 3: 2 nodes
    nodes_screen3 = [
        (9, 3, "200:9", None, "1", "Component Sheet", "FRAME", 0, 0, 1,
         0, 0, 1200, 800, None, None, None, None, None,
         None, None, None, None, None, None,
         json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]), None, None, None,
         None, None, None, None, None, None, None),
        (10, 3, "200:10", 9, "1.1", "Button Component", "COMPONENT", 1, 0, 1,
         50, 50, 120, 40, None, None, None, None, None,
         None, None, None, None, None, None,
         json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]), None, json.dumps([{"type": "DROP_SHADOW", "color": {"r": 0, "g": 0, "b": 0, "a": 0.1}, "offset": {"x": 0, "y": 2}, "radius": 6}]), json.dumps(12),
         None, None, None, None, None, None, None),
    ]

    # Insert all nodes
    for node_data in nodes_screen1:
        db.execute(
            """INSERT INTO nodes (
                id, screen_id, figma_node_id, parent_id, path, name, node_type, depth, sort_order, is_semantic,
                x, y, width, height, layout_mode, padding_top, padding_right, padding_bottom, padding_left,
                item_spacing, counter_axis_spacing, primary_align, counter_align, layout_sizing_h, layout_sizing_v,
                fills, strokes, effects, corner_radius, font_family, font_weight, font_size, line_height,
                letter_spacing, text_align, text_content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            node_data
        )

    for node_data in nodes_screen2:
        db.execute(
            """INSERT INTO nodes (
                id, screen_id, figma_node_id, parent_id, path, name, node_type, depth, sort_order, is_semantic,
                x, y, width, height, layout_mode, padding_top, padding_right, padding_bottom, padding_left,
                item_spacing, counter_axis_spacing, primary_align, counter_align, layout_sizing_h, layout_sizing_v,
                fills, strokes, effects, corner_radius, font_family, font_weight, font_size, line_height,
                letter_spacing, text_align, text_content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            node_data
        )

    for node_data in nodes_screen3:
        db.execute(
            """INSERT INTO nodes (
                id, screen_id, figma_node_id, parent_id, path, name, node_type, depth, sort_order, is_semantic,
                x, y, width, height, layout_mode, padding_top, padding_right, padding_bottom, padding_left,
                item_spacing, counter_axis_spacing, primary_align, counter_align, layout_sizing_h, layout_sizing_v,
                fills, strokes, effects, corner_radius, font_family, font_weight, font_size, line_height,
                letter_spacing, text_align, text_content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            node_data
        )

    # Insert bindings (15 total)
    bindings = [
        # Color bindings (5)
        (1, 2, "fill.0.color", None, json.dumps({"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}), "#09090B", None, "unbound"),
        (2, 1, "fill.0.color", None, json.dumps({"r": 1, "g": 1, "b": 1, "a": 1}), "#FFFFFF", None, "unbound"),
        (3, 3, "fill.0.color", None, json.dumps({"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}), "#D4D4D8", None, "unbound"),
        (4, 5, "fill.0.color", None, json.dumps({"r": 0.094, "g": 0.094, "b": 0.106, "a": 1}), "#18181B", None, "unbound"),
        (5, 6, "fill.0.color", None, json.dumps({"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}), "#09090B", None, "unbound"),
        # Typography bindings (3)
        (6, 4, "fontSize", None, "16", "16", None, "unbound"),
        (7, 4, "fontFamily", None, "Inter", "Inter", None, "unbound"),
        (8, 4, "fontWeight", None, "600", "600", None, "unbound"),
        # Spacing bindings (3)
        (9, 1, "padding.top", None, "16", "16", None, "unbound"),
        (10, 1, "padding.bottom", None, "16", "16", None, "unbound"),
        (11, 1, "itemSpacing", None, "8", "8", None, "unbound"),
        # Radius bindings (2)
        (12, 5, "cornerRadius", None, "8", "8", None, "unbound"),
        (13, 10, "cornerRadius", None, "12", "12", None, "unbound"),
        # Effect bindings (2)
        (14, 10, "effect.0.color", None, json.dumps({"r": 0, "g": 0, "b": 0, "a": 0.1}), "#0000001A", None, "unbound"),
        (15, 10, "effect.0.radius", None, "6", "6", None, "unbound"),
    ]

    db.executemany(
        """INSERT INTO node_token_bindings (
            id, node_id, property, token_id, raw_value, resolved_value, confidence, binding_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        bindings
    )

    # Insert extraction run
    db.execute(
        """INSERT INTO extraction_runs (
            id, file_id, agent_id, total_screens, extracted_screens, status, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
        (1, 1, "test_agent", 3, 3, "completed")
    )

    # Insert screen extraction status
    screen_status = [
        (1, 1, 1, "completed", 10, 5),
        (2, 1, 2, "completed", 8, 3),
        (3, 1, 3, "completed", 5, 2)
    ]
    db.executemany(
        """INSERT INTO screen_extraction_status (
            id, run_id, screen_id, status, node_count, binding_count
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        screen_status
    )

    db.commit()
    return db


def seed_post_clustering(db: sqlite3.Connection) -> sqlite3.Connection:
    """
    Seed DB with data as if clustering phase completed.
    Builds on extraction data, adds tokens and proposed bindings.
    """
    # First seed with extraction data
    seed_post_extraction(db)

    # Insert color collection
    db.execute(
        "INSERT INTO token_collections (id, file_id, name) VALUES (?, ?, ?)",
        (1, 1, "Colors")
    )

    # Insert default mode
    db.execute(
        "INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (?, ?, ?, ?)",
        (1, 1, "Default", 1)
    )

    # Insert color tokens
    color_tokens = [
        (1, 1, "color.surface.primary", "color", "extracted"),
        (2, 1, "color.surface.secondary", "color", "extracted"),
        (3, 1, "color.border.default", "color", "extracted"),
        (4, 1, "color.text.primary", "color", "extracted"),
    ]
    db.executemany(
        "INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (?, ?, ?, ?, ?)",
        color_tokens
    )

    # Insert color token values
    color_values = [
        (1, 1, 1, json.dumps({"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}), "#09090B"),
        (2, 2, 1, json.dumps({"r": 0.094, "g": 0.094, "b": 0.106, "a": 1}), "#18181B"),
        (3, 3, 1, json.dumps({"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}), "#D4D4D8"),
        (4, 4, 1, json.dumps({"r": 1, "g": 1, "b": 1, "a": 1}), "#FFFFFF"),
    ]
    db.executemany(
        "INSERT INTO token_values (id, token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?, ?)",
        color_values
    )

    # Update color bindings to proposed with token_ids
    binding_updates = [
        (1, "proposed", 1.0, 1),  # #09090B -> color.surface.primary
        (1, "proposed", 1.0, 5),  # #09090B -> color.surface.primary (duplicate)
        (4, "proposed", 0.95, 2),  # #FFFFFF -> color.text.primary
        (3, "proposed", 0.95, 3),  # #D4D4D8 -> color.border.default
        (2, "proposed", 1.0, 4),  # #18181B -> color.surface.secondary
    ]
    for token_id, status, confidence, binding_id in binding_updates:
        db.execute(
            "UPDATE node_token_bindings SET token_id = ?, binding_status = ?, confidence = ? WHERE id = ?",
            (token_id, status, confidence, binding_id)
        )

    # Insert spacing collection
    db.execute(
        "INSERT INTO token_collections (id, file_id, name) VALUES (?, ?, ?)",
        (2, 1, "Spacing")
    )

    # Insert spacing mode
    db.execute(
        "INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (?, ?, ?, ?)",
        (2, 2, "Default", 1)
    )

    # Insert spacing token
    db.execute(
        "INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (?, ?, ?, ?, ?)",
        (5, 2, "space.4", "dimension", "extracted")
    )

    # Insert spacing value
    db.execute(
        "INSERT INTO token_values (id, token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?, ?)",
        (5, 5, 2, json.dumps({"value": 16, "unit": "px"}), "16")
    )

    db.commit()
    return db


def seed_post_curation(db: sqlite3.Connection) -> sqlite3.Connection:
    """
    Seed DB with data as if curation phase completed.
    Builds on clustering data, promotes tokens to curated and bindings to bound.
    """
    # First seed with clustering data
    seed_post_clustering(db)

    # Update tokens to curated tier
    db.execute(
        "UPDATE tokens SET tier = ? WHERE id IN (?, ?, ?, ?, ?)",
        ("curated", 1, 2, 3, 4, 5)
    )

    # Update bindings to bound status
    db.execute(
        "UPDATE node_token_bindings SET binding_status = ? WHERE binding_status = ?",
        ("bound", "proposed")
    )

    db.commit()
    return db


def seed_post_validation(db: sqlite3.Connection) -> sqlite3.Connection:
    """
    Seed DB with data as if validation phase completed.
    Builds on curation data, adds export validation rows.
    """
    # First seed with curation data
    seed_post_curation(db)

    # Insert validation rows (all passing)
    validations = [
        (1, "mode_completeness", "info", "All tokens have all mode values", None, 0),
        (2, "name_dtcg_compliant", "info", "All names valid", None, 0),
        (3, "orphan_tokens", "info", "No orphan tokens", None, 0),
        (4, "name_uniqueness", "info", "All names unique", None, 0),
    ]
    db.executemany(
        """INSERT INTO export_validations (
            id, check_name, severity, message, affected_ids, resolved
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        validations
    )

    db.commit()
    return db


def seed_with_catalog(db: sqlite3.Connection) -> sqlite3.Connection:
    """Seed DB with the universal component type catalog (T5 Phase 0)."""
    from dd.catalog import seed_catalog
    seed_catalog(db)
    return db


def make_mock_figma_response(screen_name: str, node_count: int = 10) -> list[dict[str, Any]]:
    """
    Generate mock Figma extraction response data.
    Returns a list of dicts matching the shape from use_figma screen extraction.
    """
    nodes = []

    # Root frame
    root = {
        "figma_node_id": f"{hash(screen_name) % 1000}:1",
        "name": f"{screen_name} Container",
        "node_type": "FRAME",
        "depth": 0,
        "sort_order": 0,
        "x": 0,
        "y": 0,
        "width": 428,
        "height": 926,
        "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),
        "layout_mode": "VERTICAL",
        "padding_top": 16,
        "padding_right": 16,
        "padding_bottom": 16,
        "padding_left": 16,
        "item_spacing": 8,
    }
    nodes.append(root)

    # Generate child nodes
    node_types = ["FRAME", "TEXT", "RECTANGLE", "INSTANCE", "VECTOR"]
    for i in range(1, min(node_count, 10)):
        node = {
            "figma_node_id": f"{hash(screen_name) % 1000}:{i + 1}",
            "name": f"Node {i}",
            "node_type": node_types[i % len(node_types)],
            "depth": 1,
            "sort_order": i,
            "x": 20,
            "y": 20 + (i * 50),
            "width": 200,
            "height": 40,
        }

        # Add type-specific properties
        if node["node_type"] == "TEXT":
            node.update({
                "font_family": "Inter",
                "font_size": 16,
                "font_weight": 400 if i % 2 == 0 else 600,
                "line_height": json.dumps({"value": 24, "unit": "PIXELS"}),
                "text_content": f"Text content {i}"
            })
        elif node["node_type"] in ["FRAME", "RECTANGLE"]:
            node["fills"] = json.dumps([{
                "type": "SOLID",
                "color": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1}
            }])

        nodes.append(node)

    return nodes