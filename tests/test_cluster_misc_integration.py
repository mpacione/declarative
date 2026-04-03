"""Integration tests for radius and effect clustering."""

import pytest

from dd.cluster_misc import (
    cluster_effects,
    cluster_radius,
    ensure_effects_collection,
    ensure_radius_collection,
)
from dd.db import init_db


@pytest.fixture
def integrated_db():
    """Create an in-memory database with comprehensive test data."""
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'test_key', 'test.fig')")
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, 'screen1', 'Screen 1', 375, 812)"
    )

    # Insert nodes for comprehensive testing
    for i in range(1, 51):
        conn.execute(
            """INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order)
               VALUES (?, 1, ?, ?, 'RECTANGLE', 0, ?)""",
            (i, f"rect{i}", f"Rect {i}", i)
        )

    # Insert radius bindings - mix of values including edge cases
    radius_data = [
        (1, '0'),      # No radius
        (2, '2'),      # Extra small
        (3, '4'),      # Small
        (4, '4'),      # Small duplicate
        (5, '8'),      # Medium
        (6, '8'),      # Medium duplicate
        (7, '8'),      # Medium duplicate
        (8, '16'),     # Large
        (9, '16'),     # Large duplicate
        (10, '9999'),  # Full radius
        (11, '10000'), # Also full radius
    ]

    for node_id, value in radius_data:
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, 'cornerRadius', ?, ?, 'unbound')""",
            (node_id, value, value)
        )

    # Insert complex effect bindings - multiple shadows on same nodes
    # Small shadow on nodes 20-22
    for node_id in [20, 21, 22]:
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.color', '#00000020', '#00000020', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.radius', '2', '2', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.offsetX', '0', '0', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.offsetY', '1', '1', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.spread', '0', '0', 'unbound')", (node_id,))

    # Medium shadow on nodes 23-24
    for node_id in [23, 24]:
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.color', '#00000040', '#00000040', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.radius', '8', '8', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.offsetX', '0', '0', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.offsetY', '4', '4', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.spread', '0', '0', 'unbound')", (node_id,))

    # Large shadow on node 25
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (25, 'effect.0.color', '#00000060', '#00000060', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (25, 'effect.0.radius', '16', '16', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (25, 'effect.0.offsetX', '0', '0', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (25, 'effect.0.offsetY', '8', '8', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (25, 'effect.0.spread', '2', '2', 'unbound')")

    # Node with multiple shadows (effect.0 and effect.1)
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (26, 'effect.0.color', '#00000020', '#00000020', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (26, 'effect.0.radius', '2', '2', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (26, 'effect.0.offsetX', '0', '0', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (26, 'effect.0.offsetY', '1', '1', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (26, 'effect.0.spread', '0', '0', 'unbound')")

    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (26, 'effect.1.color', '#0000FF20', '#0000FF20', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (26, 'effect.1.radius', '4', '4', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (26, 'effect.1.offsetX', '2', '2', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (26, 'effect.1.offsetY', '2', '2', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (26, 'effect.1.spread', '1', '1', 'unbound')")

    conn.commit()
    return conn


def test_integrated_radius_clustering(integrated_db):
    """Test radius clustering with realistic data."""
    collection_id, mode_id = ensure_radius_collection(integrated_db, file_id=1)

    # Check initial state - only cornerRadius properties, not effect.N.radius
    cursor = integrated_db.execute(
        "SELECT COUNT(*) as count FROM node_token_bindings WHERE (property LIKE 'cornerRadius%' OR property LIKE 'topLeftRadius%' OR property LIKE 'topRightRadius%' OR property LIKE 'bottomLeftRadius%' OR property LIKE 'bottomRightRadius%') AND binding_status = 'unbound'"
    )
    initial_count = cursor.fetchone()['count']
    assert initial_count == 11, f"Expected 11 initial radius bindings, got {initial_count}"

    result = cluster_radius(integrated_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Should create tokens for: 2, 4, 8, 16, full (0 and 9999+ grouped)
    assert result['tokens_created'] == 5
    assert result['bindings_updated'] == initial_count

    # Check token names
    cursor = integrated_db.execute(
        "SELECT name FROM tokens WHERE collection_id = ? ORDER BY name",
        (collection_id,)
    )
    names = [row['name'] for row in cursor.fetchall()]

    assert 'radius.full' in names
    assert 'radius.xs' in names  # 2px
    assert 'radius.sm' in names  # 4px
    assert 'radius.md' in names  # 8px
    assert 'radius.lg' in names  # 16px

    # Verify all bindings are proposed
    cursor = integrated_db.execute(
        "SELECT COUNT(*) as count FROM node_token_bindings WHERE binding_status = 'proposed'"
    )
    assert cursor.fetchone()['count'] == 11


def test_integrated_effect_clustering(integrated_db):
    """Test effect clustering with realistic data including multiple shadows per node."""
    collection_id, mode_id = ensure_effects_collection(integrated_db, file_id=1)
    result = cluster_effects(integrated_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Should have 4 unique shadow groups:
    # - Small (2px radius, nodes 20-22 + node 26 effect.0 which is same)
    # - Medium (8px radius, nodes 23-24)
    # - Large (16px radius, node 25)
    # - Blue small (4px radius with blue color, node 26 effect.1)
    assert result['shadow_groups'] == 4
    # 4 shadows x 5 fields per shadow = 20 tokens
    assert result['tokens_created'] == 20

    # Check token structure
    cursor = integrated_db.execute(
        "SELECT name, type FROM tokens WHERE collection_id = ? ORDER BY name",
        (collection_id,)
    )
    tokens = cursor.fetchall()

    # Verify we have complete sets of atomic tokens for each shadow
    shadow_bases = set()
    for token in tokens:
        # Extract base name (e.g., "shadow.sm" from "shadow.sm.color")
        parts = token['name'].rsplit('.', 1)
        if len(parts) == 2:
            shadow_bases.add(parts[0])

    # We should have 4 different shadow bases
    assert len(shadow_bases) == 4

    # Check that each shadow has all 5 fields
    for base in shadow_bases:
        base_tokens = [t for t in tokens if t['name'].startswith(base + '.')]
        assert len(base_tokens) == 5

        # Check token types
        for token in base_tokens:
            if token['name'].endswith('.color'):
                assert token['type'] == 'color'
            else:
                assert token['type'] == 'dimension'


def test_radius_clustering_idempotent(integrated_db):
    """Test that running radius clustering twice doesn't create duplicate tokens."""
    collection_id, mode_id = ensure_radius_collection(integrated_db, file_id=1)

    # First run
    result1 = cluster_radius(integrated_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Reset bindings to unbound
    integrated_db.execute(
        "UPDATE node_token_bindings SET binding_status = 'unbound', token_id = NULL WHERE property LIKE '%Radius%'"
    )
    integrated_db.commit()

    # Second run
    result2 = cluster_radius(integrated_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Second run should not create any new tokens
    assert result2['tokens_created'] == 0

    # Total tokens should be same as after first run
    cursor = integrated_db.execute(
        "SELECT COUNT(*) as count FROM tokens WHERE collection_id = ?",
        (collection_id,)
    )
    # Should have same number of tokens as after first run
    assert cursor.fetchone()['count'] == result1['tokens_created']


def test_collections_are_file_scoped(integrated_db):
    """Test that collections are properly scoped to files."""
    # Create collection for file 1
    collection1_id, mode1_id = ensure_radius_collection(integrated_db, file_id=1)

    # Add a second file
    integrated_db.execute("INSERT INTO files (id, file_key, name) VALUES (2, 'test_key2', 'test2.fig')")

    # Create collection for file 2
    collection2_id, mode2_id = ensure_radius_collection(integrated_db, file_id=2)

    # Collections should be different
    assert collection1_id != collection2_id

    # Each file should have its own Radius collection
    cursor = integrated_db.execute(
        "SELECT COUNT(*) as count FROM token_collections WHERE name = 'Radius'"
    )
    assert cursor.fetchone()['count'] == 2