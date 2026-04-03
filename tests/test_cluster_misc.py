"""Tests for radius and effect clustering."""

import sqlite3

import pytest

from dd.db import init_db


@pytest.fixture
def mock_db_radius():
    """Create an in-memory database with radius test data."""
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'test_key', 'test.fig')")
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, 'screen1', 'Screen 1', 375, 812)"
    )

    # Insert nodes
    for i in range(1, 21):
        conn.execute(
            """INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order)
               VALUES (?, 1, ?, ?, 'RECTANGLE', 0, ?)""",
            (i, f"rect{i}", f"Rect {i}", i)
        )

    # Insert radius bindings - various values
    radius_values = [
        ('0', 2),    # 0px - no radius
        ('4', 5),    # 4px - small radius
        ('8', 8),    # 8px - medium radius
        ('12', 4),   # 12px - larger radius
        ('9999', 1), # Full radius (pill shape)
    ]

    binding_id = 1
    node_id = 1

    for value, count in radius_values:
        for i in range(count):
            conn.execute(
                """INSERT INTO node_token_bindings
                   (id, node_id, property, raw_value, resolved_value, binding_status)
                   VALUES (?, ?, 'cornerRadius', ?, ?, 'unbound')""",
                (binding_id, node_id, value, value)
            )
            binding_id += 1
            node_id += 1

    conn.commit()
    return conn


@pytest.fixture
def mock_db_effects():
    """Create an in-memory database with effect test data."""
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'test_key', 'test.fig')")
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, 'screen1', 'Screen 1', 375, 812)"
    )

    # Insert nodes
    for i in range(1, 11):
        conn.execute(
            """INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order)
               VALUES (?, 1, ?, ?, 'RECTANGLE', 0, ?)""",
            (i, f"rect{i}", f"Rect {i}", i)
        )

    # Insert effect bindings - 3 different shadow composites
    # Shadow 1: Small shadow (used on nodes 1-3)
    for node_id in [1, 2, 3]:
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.color', '#00000020', '#00000020', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.radius', '4', '4', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.offsetX', '0', '0', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.offsetY', '2', '2', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.spread', '0', '0', 'unbound')", (node_id,))

    # Shadow 2: Medium shadow (used on nodes 4-5)
    for node_id in [4, 5]:
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.color', '#00000040', '#00000040', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.radius', '8', '8', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.offsetX', '0', '0', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.offsetY', '4', '4', 'unbound')", (node_id,))
        conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, 'effect.0.spread', '0', '0', 'unbound')", (node_id,))

    # Shadow 3: Large shadow (used on node 6)
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (6, 'effect.0.color', '#00000060', '#00000060', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (6, 'effect.0.radius', '16', '16', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (6, 'effect.0.offsetX', '0', '0', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (6, 'effect.0.offsetY', '8', '8', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (6, 'effect.0.spread', '2', '2', 'unbound')")

    # Similar color shadow (should merge with small shadow)
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (7, 'effect.0.color', '#00000021', '#00000021', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (7, 'effect.0.radius', '4', '4', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (7, 'effect.0.offsetX', '0', '0', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (7, 'effect.0.offsetY', '2', '2', 'unbound')")
    conn.execute("INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (7, 'effect.0.spread', '0', '0', 'unbound')")

    conn.commit()
    return conn


def test_propose_radius_name():
    """Test proposing radius token names."""
    from dd.cluster_misc import propose_radius_name

    # Small radius (first of 3, no full)
    assert propose_radius_name(4, 0, 3, has_full=False) == "radius.sm"

    # Medium radius (second of 3, no full)
    assert propose_radius_name(8, 1, 3, has_full=False) == "radius.md"

    # Large radius (third of 3, no full)
    assert propose_radius_name(12, 2, 3, has_full=False) == "radius.lg"

    # Full radius (pill shape) - always returns full regardless of has_full
    assert propose_radius_name(9999, 3, 4, has_full=True) == "radius.full"

    # Zero radius (no radius) - maps to full
    assert propose_radius_name(0, 0, 2, has_full=True) == "radius.full"

    # With 4 values including full (so 3 normal values)
    assert propose_radius_name(4, 0, 4, has_full=True) == "radius.sm"
    assert propose_radius_name(8, 1, 4, has_full=True) == "radius.md"
    assert propose_radius_name(12, 2, 4, has_full=True) == "radius.lg"
    assert propose_radius_name(99999, 3, 4, has_full=True) == "radius.full"

    # With 4 values, no full
    assert propose_radius_name(2, 0, 4, has_full=False) == "radius.xs"
    assert propose_radius_name(4, 1, 4, has_full=False) == "radius.sm"
    assert propose_radius_name(8, 2, 4, has_full=False) == "radius.md"
    assert propose_radius_name(12, 3, 4, has_full=False) == "radius.lg"

    # With 5 values, no full
    assert propose_radius_name(2, 0, 5, has_full=False) == "radius.xs"
    assert propose_radius_name(4, 1, 5, has_full=False) == "radius.sm"
    assert propose_radius_name(8, 2, 5, has_full=False) == "radius.md"
    assert propose_radius_name(12, 3, 5, has_full=False) == "radius.lg"
    assert propose_radius_name(16, 4, 5, has_full=False) == "radius.xl"

    # With 6+ values, no full
    assert propose_radius_name(1, 0, 6, has_full=False) == "radius.xs"
    assert propose_radius_name(2, 1, 6, has_full=False) == "radius.sm"
    assert propose_radius_name(4, 2, 6, has_full=False) == "radius.md"
    assert propose_radius_name(8, 3, 6, has_full=False) == "radius.lg"
    assert propose_radius_name(12, 4, 6, has_full=False) == "radius.xl"
    assert propose_radius_name(16, 5, 6, has_full=False) == "radius.2xl"
    assert propose_radius_name(24, 6, 7, has_full=False) == "radius.3xl"


def test_propose_effect_name():
    """Test proposing effect/shadow token names."""
    from dd.cluster_misc import propose_effect_name

    # Basic 3 shadows
    assert propose_effect_name(0, 3) == "shadow.sm"
    assert propose_effect_name(1, 3) == "shadow.md"
    assert propose_effect_name(2, 3) == "shadow.lg"

    # With 4+ shadows
    assert propose_effect_name(0, 4) == "shadow.xs"
    assert propose_effect_name(1, 4) == "shadow.sm"
    assert propose_effect_name(2, 4) == "shadow.md"
    assert propose_effect_name(3, 4) == "shadow.lg"

    # With 5+ shadows
    assert propose_effect_name(4, 5) == "shadow.xl"
    assert propose_effect_name(5, 6) == "shadow.2xl"


def test_query_radius_census(mock_db_radius):
    """Test querying radius census from database."""
    from dd.cluster_misc import query_radius_census

    result = query_radius_census(mock_db_radius, file_id=1)

    assert len(result) > 0
    assert all('resolved_value' in row for row in result)
    assert all('usage_count' in row for row in result)

    # Check that values are sorted by resolved_value (numerically)
    values = [float(r['resolved_value']) for r in result]
    assert values == sorted(values)

    # Check specific counts
    four_px = [r for r in result if r['resolved_value'] == '4']
    assert len(four_px) == 1
    assert four_px[0]['usage_count'] == 5


def test_query_effect_census(mock_db_effects):
    """Test querying effect census from database."""
    from dd.cluster_misc import query_effect_census

    result = query_effect_census(mock_db_effects, file_id=1)

    assert len(result) > 0
    assert all('resolved_value' in row for row in result)
    assert all('property' in row for row in result)
    assert all('usage_count' in row for row in result)

    # Should have multiple effect properties
    properties = {r['property'] for r in result}
    assert 'effect.0.color' in properties
    assert 'effect.0.radius' in properties
    assert 'effect.0.offsetX' in properties
    assert 'effect.0.offsetY' in properties


def test_group_effects_by_composite(mock_db_effects):
    """Test grouping effect bindings into composite shadows."""
    from dd.cluster_misc import group_effects_by_composite

    # Need to get effect bindings first
    census = []
    conn = mock_db_effects
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        """SELECT node_id, property, resolved_value
           FROM node_token_bindings
           WHERE property LIKE 'effect%' AND binding_status = 'unbound'
           ORDER BY node_id, property"""
    )

    effects_by_node = {}
    for row in cursor:
        node_id = row['node_id']
        if node_id not in effects_by_node:
            effects_by_node[node_id] = {}

        # Parse effect index from property (e.g., 'effect.0.color' -> '0')
        parts = row['property'].split('.')
        if len(parts) >= 3:
            effect_idx = parts[1]
            field = parts[2]

            if effect_idx not in effects_by_node[node_id]:
                effects_by_node[node_id][effect_idx] = {}

            effects_by_node[node_id][effect_idx][field] = row['resolved_value']

    composites = group_effects_by_composite(conn, 1)

    # Should have 3 main shadow groups (small, medium, large)
    # The similar color shadow should merge with small
    assert len(composites) == 3

    # Check that composites have all required fields
    for comp in composites:
        assert 'color' in comp
        assert 'radius' in comp
        assert 'offsetX' in comp
        assert 'offsetY' in comp
        assert 'spread' in comp
        assert 'usage_count' in comp
        assert 'node_ids' in comp

    # Sort by radius to get small, medium, large
    composites.sort(key=lambda x: float(x['radius']))

    # Small shadow should have 4 uses (3 original + 1 similar)
    assert composites[0]['radius'] == '4'
    assert composites[0]['usage_count'] == 4

    # Medium shadow
    assert composites[1]['radius'] == '8'
    assert composites[1]['usage_count'] == 2

    # Large shadow
    assert composites[2]['radius'] == '16'
    assert composites[2]['usage_count'] == 1


def test_cluster_radius(mock_db_radius):
    """Test the main radius clustering function."""
    from dd.cluster_misc import cluster_radius, ensure_radius_collection

    collection_id, mode_id = ensure_radius_collection(mock_db_radius, file_id=1)
    result = cluster_radius(mock_db_radius, file_id=1, collection_id=collection_id, mode_id=mode_id)

    assert 'tokens_created' in result
    assert 'bindings_updated' in result

    # Should create 4 tokens (0, 4, 8, 12, 9999 -> but 0 and 9999 both map to 'full')
    assert result['tokens_created'] == 4  # sm, md, lg, full
    assert result['bindings_updated'] == 20  # All 20 bindings

    # Check tokens were created
    cursor = mock_db_radius.execute(
        "SELECT * FROM tokens WHERE collection_id = ?", (collection_id,)
    )
    tokens = cursor.fetchall()
    assert len(tokens) == 4

    # All tokens should have type='dimension' and tier='extracted'
    for token in tokens:
        assert token['type'] == 'dimension'
        assert token['tier'] == 'extracted'

    # Check token names
    token_names = {token['name'] for token in tokens}
    assert 'radius.sm' in token_names
    assert 'radius.md' in token_names
    assert 'radius.lg' in token_names
    assert 'radius.full' in token_names

    # Check bindings were updated
    cursor = mock_db_radius.execute(
        "SELECT * FROM node_token_bindings WHERE binding_status = 'proposed'"
    )
    bindings = cursor.fetchall()
    assert len(bindings) == 20

    # All should have confidence=1.0 (exact match)
    for binding in bindings:
        assert binding['confidence'] == 1.0


def test_cluster_effects(mock_db_effects):
    """Test the main effect clustering function."""
    from dd.cluster_misc import cluster_effects, ensure_effects_collection

    collection_id, mode_id = ensure_effects_collection(mock_db_effects, file_id=1)
    result = cluster_effects(mock_db_effects, file_id=1, collection_id=collection_id, mode_id=mode_id)

    assert 'tokens_created' in result
    assert 'bindings_updated' in result
    assert 'shadow_groups' in result

    # 3 shadow groups x 5 fields per shadow = 15 tokens
    assert result['tokens_created'] == 15
    assert result['shadow_groups'] == 3

    # Check tokens were created
    cursor = mock_db_effects.execute(
        "SELECT * FROM tokens WHERE collection_id = ? ORDER BY name", (collection_id,)
    )
    tokens = cursor.fetchall()
    assert len(tokens) == 15

    # Check we have all the expected atomic tokens
    token_names = [token['name'] for token in tokens]

    # Small shadow tokens
    assert 'shadow.sm.color' in token_names
    assert 'shadow.sm.radius' in token_names
    assert 'shadow.sm.offsetX' in token_names
    assert 'shadow.sm.offsetY' in token_names
    assert 'shadow.sm.spread' in token_names

    # Medium shadow tokens
    assert 'shadow.md.color' in token_names
    assert 'shadow.md.radius' in token_names

    # Large shadow tokens
    assert 'shadow.lg.color' in token_names
    assert 'shadow.lg.radius' in token_names

    # Check token types
    for token in tokens:
        if '.color' in token['name']:
            assert token['type'] == 'color'
        else:
            assert token['type'] == 'dimension'

        assert token['tier'] == 'extracted'

    # Check bindings - the similar color should have lower confidence
    cursor = mock_db_effects.execute(
        """SELECT * FROM node_token_bindings
           WHERE binding_status = 'proposed' AND node_id = 7
           AND property = 'effect.0.color'"""
    )
    similar_binding = cursor.fetchone()
    assert similar_binding is not None
    assert 0.8 <= similar_binding['confidence'] < 1.0  # Merged with lower confidence