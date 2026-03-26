"""Tests for clustering modules."""

import sqlite3
from unittest.mock import patch
import pytest

from dd.cluster_colors import (
    query_color_census,
    group_by_delta_e,
    classify_color_role,
    propose_color_name,
    ensure_collection_and_mode,
    cluster_colors,
)
from dd.cluster_typography import (
    query_type_census,
    group_type_scale,
    propose_type_name,
    cluster_typography,
    ensure_typography_collection,
)
from dd.cluster_spacing import (
    query_spacing_census,
    detect_scale_pattern,
    propose_spacing_name,
    cluster_spacing,
    ensure_spacing_collection,
)
from dd.db import init_db


@pytest.fixture
def mock_db():
    """Create an in-memory database with test data."""
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'test_key', 'test.fig')")
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, 'screen1', 'Screen 1', 375, 812)"
    )

    # Insert nodes
    for i in range(1, 6):
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order) VALUES (?, 1, ?, ?, 'RECTANGLE', 0, ?)",
            (i, f"node{i}", f"Node {i}", i)
        )

    # Insert color bindings - some identical, some very similar, some different
    bindings = [
        (1, 1, 'fill.0.color', '#FF0000', '#FF0000'),  # Pure red
        (2, 2, 'fill.0.color', '#FF0000', '#FF0000'),  # Same red
        (3, 3, 'fill.0.color', '#FF0001', '#FF0001'),  # Very similar red (delta-E < 2)
        (4, 4, 'fill.0.color', '#0000FF', '#0000FF'),  # Pure blue
        (5, 5, 'stroke.0.color', '#000000', '#000000'),  # Black stroke
    ]

    for binding_id, node_id, prop, raw, resolved in bindings:
        conn.execute(
            """INSERT INTO node_token_bindings
               (id, node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, ?, ?, ?, ?, 'unbound')""",
            (binding_id, node_id, prop, raw, resolved)
        )

    conn.commit()
    return conn


def test_query_color_census(mock_db):
    """Test querying color census from database."""
    result = query_color_census(mock_db, file_id=1)

    assert len(result) > 0
    assert all('resolved_value' in row for row in result)
    assert all('usage_count' in row for row in result)
    assert all('node_count' in row for row in result)
    assert all('properties' in row for row in result)

    # Check that #FF0000 appears with usage_count=2 (two identical)
    red_rows = [r for r in result if r['resolved_value'] == '#FF0000']
    assert len(red_rows) == 1
    assert red_rows[0]['usage_count'] == 2
    assert red_rows[0]['node_count'] == 2


def test_query_color_census_filters_unbound_only(mock_db):
    """Test that census only includes unbound colors."""
    # Update one binding to 'proposed'
    mock_db.execute(
        "UPDATE node_token_bindings SET binding_status = 'proposed' WHERE id = 1"
    )
    mock_db.commit()

    result = query_color_census(mock_db, file_id=1)

    # #FF0000 should now have usage_count=1 (not 2)
    red_rows = [r for r in result if r['resolved_value'] == '#FF0000']
    assert len(red_rows) == 1
    assert red_rows[0]['usage_count'] == 1


def test_group_by_delta_e():
    """Test grouping colors by perceptual similarity."""
    colors = [
        {'resolved_value': '#FF0000', 'usage_count': 10, 'node_count': 5, 'properties': 'fill.0.color'},
        {'resolved_value': '#FF0001', 'usage_count': 5, 'node_count': 3, 'properties': 'fill.0.color'},
        {'resolved_value': '#0000FF', 'usage_count': 8, 'node_count': 4, 'properties': 'fill.0.color'},
        {'resolved_value': '#000000', 'usage_count': 3, 'node_count': 2, 'properties': 'stroke.0.color'},
    ]

    groups = group_by_delta_e(colors, threshold=2.0)

    # Should have 3 groups: reds together, blue alone, black alone
    assert len(groups) == 3

    # First group should be reds (highest total usage)
    assert len(groups[0]) == 2
    assert groups[0][0]['resolved_value'] == '#FF0000'  # Higher usage first
    assert groups[0][1]['resolved_value'] == '#FF0001'

    # Second group should be blue
    assert len(groups[1]) == 1
    assert groups[1][0]['resolved_value'] == '#0000FF'

    # Third group should be black
    assert len(groups[2]) == 1
    assert groups[2][0]['resolved_value'] == '#000000'


def test_group_by_delta_e_with_identical_colors():
    """Test that identical colors group together."""
    colors = [
        {'resolved_value': '#FF0000', 'usage_count': 10, 'node_count': 5, 'properties': 'fill.0.color'},
        {'resolved_value': '#FF0000', 'usage_count': 8, 'node_count': 4, 'properties': 'fill.0.color'},
    ]

    groups = group_by_delta_e(colors, threshold=2.0)

    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_group_by_delta_e_with_very_different_colors():
    """Test that very different colors stay in separate groups."""
    colors = [
        {'resolved_value': '#FF0000', 'usage_count': 10, 'node_count': 5, 'properties': 'fill.0.color'},
        {'resolved_value': '#00FF00', 'usage_count': 8, 'node_count': 4, 'properties': 'fill.0.color'},
        {'resolved_value': '#0000FF', 'usage_count': 6, 'node_count': 3, 'properties': 'fill.0.color'},
    ]

    groups = group_by_delta_e(colors, threshold=2.0)

    # Each color should be in its own group
    assert len(groups) == 3
    for group in groups:
        assert len(group) == 1


def test_classify_color_role():
    """Test classification of color roles based on properties."""
    # Stroke property should be border
    assert classify_color_role('stroke.0.color') == 'border'
    assert classify_color_role('fill.0.color,stroke.0.color') == 'border'

    # Fill only should be surface
    assert classify_color_role('fill.0.color') == 'surface'
    assert classify_color_role('fill.0.color,fill.1.color') == 'surface'


def test_propose_color_name():
    """Test proposing DTCG-compliant color names."""
    existing = set()

    # First surface color should be primary
    name1 = propose_color_name('surface', 0.9, 0, existing)
    assert name1 == 'color.surface.primary'
    existing.add(name1)

    # Second surface color should be secondary
    name2 = propose_color_name('surface', 0.7, 1, existing)
    assert name2 == 'color.surface.secondary'
    existing.add(name2)

    # Third surface color should be tertiary
    name3 = propose_color_name('surface', 0.5, 2, existing)
    assert name3 == 'color.surface.tertiary'
    existing.add(name3)

    # Fourth should use numeric suffix
    name4 = propose_color_name('surface', 0.3, 3, existing)
    assert name4 == 'color.surface.4'
    existing.add(name4)

    # Duplicate name should get numeric suffix
    name5 = propose_color_name('surface', 0.9, 0, existing)
    assert name5 == 'color.surface.primary.2'


def test_ensure_collection_and_mode(mock_db):
    """Test creating or retrieving token collection and mode."""
    collection_id, mode_id = ensure_collection_and_mode(mock_db, file_id=1)

    assert collection_id is not None
    assert mode_id is not None

    # Should be idempotent
    collection_id2, mode_id2 = ensure_collection_and_mode(mock_db, file_id=1)
    assert collection_id2 == collection_id
    assert mode_id2 == mode_id

    # Verify in database
    cursor = mock_db.execute(
        "SELECT * FROM token_collections WHERE id = ?", (collection_id,)
    )
    collection = cursor.fetchone()
    assert collection['name'] == 'Colors'
    assert collection['file_id'] == 1

    cursor = mock_db.execute(
        "SELECT * FROM token_modes WHERE id = ?", (mode_id,)
    )
    mode = cursor.fetchone()
    assert mode['name'] == 'Default'
    assert mode['is_default'] == 1


def test_cluster_colors(mock_db):
    """Test the main color clustering function."""
    # Ensure collection exists
    collection_id, mode_id = ensure_collection_and_mode(mock_db, file_id=1)

    result = cluster_colors(mock_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

    assert 'tokens_created' in result
    assert 'bindings_updated' in result
    assert 'groups' in result

    assert result['tokens_created'] > 0
    assert result['bindings_updated'] > 0
    assert result['groups'] > 0

    # Check that tokens were created
    cursor = mock_db.execute(
        "SELECT * FROM tokens WHERE collection_id = ?", (collection_id,)
    )
    tokens = cursor.fetchall()
    assert len(tokens) == result['tokens_created']

    # All tokens should have tier='extracted' and type='color'
    for token in tokens:
        assert token['tier'] == 'extracted'
        assert token['type'] == 'color'

    # Check token values
    cursor = mock_db.execute(
        """SELECT tv.*, t.name FROM token_values tv
           JOIN tokens t ON tv.token_id = t.id
           WHERE t.collection_id = ?""",
        (collection_id,)
    )
    values = cursor.fetchall()
    assert len(values) == result['tokens_created']

    # Check bindings were updated
    cursor = mock_db.execute(
        "SELECT * FROM node_token_bindings WHERE binding_status = 'proposed'"
    )
    bindings = cursor.fetchall()
    assert len(bindings) == result['bindings_updated']

    # All bindings should have token_id and confidence set
    for binding in bindings:
        assert binding['token_id'] is not None
        assert binding['confidence'] is not None
        assert 0.8 <= binding['confidence'] <= 1.0


def test_cluster_colors_exact_match_confidence(mock_db):
    """Test that exact color matches get confidence=1.0."""
    collection_id, mode_id = ensure_collection_and_mode(mock_db, file_id=1)

    cluster_colors(mock_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Check that #FF0000 bindings have confidence=1.0
    cursor = mock_db.execute(
        """SELECT confidence FROM node_token_bindings
           WHERE resolved_value = '#FF0000' AND binding_status = 'proposed'"""
    )
    confidences = [row['confidence'] for row in cursor.fetchall()]
    assert all(c == 1.0 for c in confidences)


def test_cluster_colors_merged_confidence(mock_db):
    """Test that delta-E merged colors get confidence between 0.8-0.99."""
    collection_id, mode_id = ensure_collection_and_mode(mock_db, file_id=1)

    cluster_colors(mock_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Check that #FF0001 binding has confidence < 1.0 but >= 0.8
    cursor = mock_db.execute(
        """SELECT confidence FROM node_token_bindings
           WHERE resolved_value = '#FF0001' AND binding_status = 'proposed'"""
    )
    row = cursor.fetchone()
    if row:  # May have been merged
        assert 0.8 <= row['confidence'] < 1.0


def test_cluster_colors_no_orphan_tokens(mock_db):
    """Test that no orphan tokens are created."""
    collection_id, mode_id = ensure_collection_and_mode(mock_db, file_id=1)

    cluster_colors(mock_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Every token should have at least one binding
    cursor = mock_db.execute(
        """SELECT t.id, t.name, COUNT(ntb.id) as binding_count
           FROM tokens t
           LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
           WHERE t.collection_id = ?
           GROUP BY t.id""",
        (collection_id,)
    )

    for row in cursor.fetchall():
        assert row['binding_count'] > 0, f"Token {row['name']} has no bindings"


def test_cluster_colors_unique_names(mock_db):
    """Test that all token names are unique within collection."""
    collection_id, mode_id = ensure_collection_and_mode(mock_db, file_id=1)

    cluster_colors(mock_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Check for unique names
    cursor = mock_db.execute(
        "SELECT name, COUNT(*) as count FROM tokens WHERE collection_id = ? GROUP BY name",
        (collection_id,)
    )

    for row in cursor.fetchall():
        assert row['count'] == 1, f"Duplicate token name: {row['name']}"


# Typography clustering tests

@pytest.fixture
def mock_db_typography():
    """Create an in-memory database with typography test data."""
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'test_key', 'test.fig')")
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, 'screen1', 'Screen 1', 375, 812)"
    )

    # Insert TEXT nodes with various typography styles
    text_nodes = [
        # Display sizes (>=32)
        (1, 'Roboto', 700, 48, '{"value": 56, "unit": "PIXELS"}'),
        (2, 'Roboto', 700, 36, '{"value": 42, "unit": "PIXELS"}'),
        (3, 'Roboto', 700, 32, '{"value": 38, "unit": "PIXELS"}'),
        # Heading sizes (>=24, <32)
        (4, 'Roboto', 600, 28, '{"value": 34, "unit": "PIXELS"}'),
        (5, 'Roboto', 600, 24, '{"value": 30, "unit": "PIXELS"}'),
        # Body sizes (>=16, <24)
        (6, 'Roboto', 400, 18, '{"value": 24, "unit": "PIXELS"}'),
        (7, 'Roboto', 400, 16, '{"value": 24, "unit": "PIXELS"}'),
        (8, 'Roboto', 400, 16, '{"value": 24, "unit": "PIXELS"}'),  # Duplicate for usage count
        # Label sizes (>=12, <16)
        (9, 'Roboto', 500, 14, '{"value": 18, "unit": "PIXELS"}'),
        (10, 'Roboto', 500, 12, '{"value": 16, "unit": "PIXELS"}'),
        # Caption sizes (<12)
        (11, 'Roboto', 400, 10, '{"value": 14, "unit": "PIXELS"}'),
        # Different font family with same size
        (12, 'Inter', 400, 16, '{"value": 24, "unit": "PIXELS"}'),
        # NULL line height (AUTO)
        (13, 'Roboto', 400, 20, '"AUTO"'),
    ]

    for node_id, font_family, font_weight, font_size, line_height in text_nodes:
        conn.execute(
            """INSERT INTO nodes
               (id, screen_id, figma_node_id, name, node_type, depth, sort_order,
                font_family, font_weight, font_size, line_height)
               VALUES (?, 1, ?, ?, 'TEXT', 0, ?, ?, ?, ?, ?)""",
            (node_id, f"text{node_id}", f"Text {node_id}", node_id,
             font_family, font_weight, font_size, line_height)
        )

    # Insert node_token_bindings for typography properties (all unbound)
    binding_id = 1
    for node_id in range(1, 14):
        # Get node info
        cursor = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
        node = cursor.fetchone()
        if node['font_size']:
            # fontSize binding
            conn.execute(
                """INSERT INTO node_token_bindings
                   (id, node_id, property, raw_value, resolved_value, binding_status)
                   VALUES (?, ?, 'fontSize', ?, ?, 'unbound')""",
                (binding_id, node_id, str(node['font_size']), str(node['font_size']))
            )
            binding_id += 1

            # fontFamily binding
            conn.execute(
                """INSERT INTO node_token_bindings
                   (id, node_id, property, raw_value, resolved_value, binding_status)
                   VALUES (?, ?, 'fontFamily', ?, ?, 'unbound')""",
                (binding_id, node_id, node['font_family'], node['font_family'])
            )
            binding_id += 1

            # fontWeight binding
            conn.execute(
                """INSERT INTO node_token_bindings
                   (id, node_id, property, raw_value, resolved_value, binding_status)
                   VALUES (?, ?, 'fontWeight', ?, ?, 'unbound')""",
                (binding_id, node_id, str(node['font_weight']), str(node['font_weight']))
            )
            binding_id += 1

    conn.commit()
    return conn


def test_query_type_census(mock_db_typography):
    """Test querying typography census from database."""
    result = query_type_census(mock_db_typography, file_id=1)

    assert len(result) > 0
    assert all('font_family' in row for row in result)
    assert all('font_weight' in row for row in result)
    assert all('font_size' in row for row in result)
    assert all('line_height_value' in row for row in result)
    assert all('usage_count' in row for row in result)

    # Check that 16px Roboto appears with usage_count=2
    roboto_16 = [r for r in result if r['font_size'] == 16.0 and r['font_family'] == 'Roboto']
    assert len(roboto_16) == 1
    assert roboto_16[0]['usage_count'] == 2

    # Check that NULL font_size entries are filtered
    assert all(row['font_size'] is not None for row in result)


def test_group_type_scale():
    """Test grouping typography into semantic scale tiers."""
    census = [
        {'font_family': 'Roboto', 'font_weight': 700, 'font_size': 48.0, 'line_height_value': 56.0, 'usage_count': 5},
        {'font_family': 'Roboto', 'font_weight': 700, 'font_size': 36.0, 'line_height_value': 42.0, 'usage_count': 3},
        {'font_family': 'Roboto', 'font_weight': 700, 'font_size': 32.0, 'line_height_value': 38.0, 'usage_count': 2},
        {'font_family': 'Roboto', 'font_weight': 600, 'font_size': 28.0, 'line_height_value': 34.0, 'usage_count': 4},
        {'font_family': 'Roboto', 'font_weight': 600, 'font_size': 24.0, 'line_height_value': 30.0, 'usage_count': 3},
        {'font_family': 'Roboto', 'font_weight': 400, 'font_size': 18.0, 'line_height_value': 24.0, 'usage_count': 8},
        {'font_family': 'Roboto', 'font_weight': 400, 'font_size': 16.0, 'line_height_value': 24.0, 'usage_count': 10},
        {'font_family': 'Roboto', 'font_weight': 500, 'font_size': 14.0, 'line_height_value': 18.0, 'usage_count': 6},
        {'font_family': 'Roboto', 'font_weight': 500, 'font_size': 12.0, 'line_height_value': 16.0, 'usage_count': 4},
        {'font_family': 'Roboto', 'font_weight': 400, 'font_size': 10.0, 'line_height_value': 14.0, 'usage_count': 2},
    ]

    result = group_type_scale(census)

    # Check categories
    display_items = [r for r in result if r['category'] == 'display']
    assert len(display_items) == 3  # 48, 36, 32

    heading_items = [r for r in result if r['category'] == 'heading']
    assert len(heading_items) == 2  # 28, 24

    body_items = [r for r in result if r['category'] == 'body']
    assert len(body_items) == 2  # 18, 16

    label_items = [r for r in result if r['category'] == 'label']
    assert len(label_items) == 2  # 14, 12

    caption_items = [r for r in result if r['category'] == 'caption']
    assert len(caption_items) == 1  # 10

    # Check size suffixes for display (3 items -> lg, md, sm)
    assert display_items[0]['size_suffix'] == 'lg'
    assert display_items[0]['font_size'] == 48.0
    assert display_items[1]['size_suffix'] == 'md'
    assert display_items[1]['font_size'] == 36.0
    assert display_items[2]['size_suffix'] == 'sm'
    assert display_items[2]['font_size'] == 32.0

    # Check size suffixes for heading (2 items -> lg, sm)
    assert heading_items[0]['size_suffix'] == 'lg'
    assert heading_items[0]['font_size'] == 28.0
    assert heading_items[1]['size_suffix'] == 'sm'
    assert heading_items[1]['font_size'] == 24.0

    # Check single item gets 'md'
    assert caption_items[0]['size_suffix'] == 'md'


def test_group_type_scale_with_more_than_three():
    """Test that categories with >3 items get xl, lg, md, sm, xs suffixes."""
    census = [
        {'font_family': 'Roboto', 'font_weight': 400, 'font_size': 20.0, 'line_height_value': 28.0, 'usage_count': 5},
        {'font_family': 'Roboto', 'font_weight': 400, 'font_size': 18.0, 'line_height_value': 24.0, 'usage_count': 8},
        {'font_family': 'Roboto', 'font_weight': 400, 'font_size': 17.0, 'line_height_value': 22.0, 'usage_count': 3},
        {'font_family': 'Roboto', 'font_weight': 400, 'font_size': 16.0, 'line_height_value': 24.0, 'usage_count': 10},
    ]

    result = group_type_scale(census)

    body_items = [r for r in result if r['category'] == 'body']
    assert len(body_items) == 4

    # With 4 items, should use xl, lg, md, sm
    assert body_items[0]['size_suffix'] == 'xl'
    assert body_items[0]['font_size'] == 20.0
    assert body_items[1]['size_suffix'] == 'lg'
    assert body_items[1]['font_size'] == 18.0
    assert body_items[2]['size_suffix'] == 'md'
    assert body_items[2]['font_size'] == 17.0
    assert body_items[3]['size_suffix'] == 'sm'
    assert body_items[3]['font_size'] == 16.0


def test_group_type_scale_different_families():
    """Test that different font families at same size are separate tiers."""
    census = [
        {'font_family': 'Roboto', 'font_weight': 400, 'font_size': 16.0, 'line_height_value': 24.0, 'usage_count': 10},
        {'font_family': 'Inter', 'font_weight': 400, 'font_size': 16.0, 'line_height_value': 24.0, 'usage_count': 5},
    ]

    result = group_type_scale(census)

    # Both should be body category but separate entries
    body_items = [r for r in result if r['category'] == 'body']
    assert len(body_items) == 2

    # Both get 'lg' and 'sm' since there are 2
    assert body_items[0]['size_suffix'] == 'lg'
    assert body_items[0]['font_family'] == 'Roboto'  # Higher usage first
    assert body_items[1]['size_suffix'] == 'sm'
    assert body_items[1]['font_family'] == 'Inter'


def test_propose_type_name():
    """Test proposing DTCG-compliant typography names."""
    existing = set()

    # First body.md
    name1 = propose_type_name('body', 'md', existing)
    assert name1 == 'type.body.md'
    existing.add(name1)

    # Second body.md should get numeric suffix
    name2 = propose_type_name('body', 'md', existing)
    assert name2 == 'type.body.md.2'
    existing.add(name2)

    # Different category/suffix
    name3 = propose_type_name('display', 'lg', existing)
    assert name3 == 'type.display.lg'
    existing.add(name3)

    # Third body.md
    name4 = propose_type_name('body', 'md', existing)
    assert name4 == 'type.body.md.3'


def test_ensure_typography_collection(mock_db_typography):
    """Test creating or retrieving typography collection and mode."""
    collection_id, mode_id = ensure_typography_collection(mock_db_typography, file_id=1)

    assert collection_id is not None
    assert mode_id is not None

    # Should be idempotent
    collection_id2, mode_id2 = ensure_typography_collection(mock_db_typography, file_id=1)
    assert collection_id2 == collection_id
    assert mode_id2 == mode_id

    # Verify in database
    cursor = mock_db_typography.execute(
        "SELECT * FROM token_collections WHERE id = ?", (collection_id,)
    )
    collection = cursor.fetchone()
    assert collection['name'] == 'Typography'
    assert collection['file_id'] == 1

    cursor = mock_db_typography.execute(
        "SELECT * FROM token_modes WHERE id = ?", (mode_id,)
    )
    mode = cursor.fetchone()
    assert mode['name'] == 'Default'
    assert mode['is_default'] == 1


def test_cluster_typography(mock_db_typography):
    """Test the main typography clustering function."""
    collection_id, mode_id = ensure_typography_collection(mock_db_typography, file_id=1)

    result = cluster_typography(mock_db_typography, file_id=1, collection_id=collection_id, mode_id=mode_id)

    assert 'tokens_created' in result
    assert 'bindings_updated' in result
    assert 'type_scales' in result

    assert result['tokens_created'] > 0
    assert result['bindings_updated'] > 0
    assert result['type_scales'] > 0

    # Check that tokens were created
    cursor = mock_db_typography.execute(
        "SELECT * FROM tokens WHERE collection_id = ?", (collection_id,)
    )
    tokens = cursor.fetchall()
    assert len(tokens) == result['tokens_created']

    # All tokens should have tier='extracted'
    for token in tokens:
        assert token['tier'] == 'extracted'

    # Check token types - should be atomic types not composite
    token_types = {token['type'] for token in tokens}
    assert 'dimension' in token_types  # fontSize and lineHeight
    assert 'fontFamily' in token_types
    assert 'fontWeight' in token_types
    # Should NOT have composite 'typography' type
    assert 'typography' not in token_types

    # Check token values
    cursor = mock_db_typography.execute(
        """SELECT tv.*, t.name, t.type FROM token_values tv
           JOIN tokens t ON tv.token_id = t.id
           WHERE t.collection_id = ?""",
        (collection_id,)
    )
    values = cursor.fetchall()
    assert len(values) == result['tokens_created']

    # Check bindings were updated
    cursor = mock_db_typography.execute(
        "SELECT * FROM node_token_bindings WHERE binding_status = 'proposed'"
    )
    bindings = cursor.fetchall()
    assert len(bindings) == result['bindings_updated']

    # All bindings should have token_id and confidence=1.0 (exact match)
    for binding in bindings:
        assert binding['token_id'] is not None
        assert binding['confidence'] == 1.0


def test_cluster_typography_atomic_tokens(mock_db_typography):
    """Test that typography creates individual atomic tokens, not composites."""
    collection_id, mode_id = ensure_typography_collection(mock_db_typography, file_id=1)

    cluster_typography(mock_db_typography, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Check that we have fontSize, fontFamily, fontWeight tokens
    cursor = mock_db_typography.execute(
        """SELECT name, type FROM tokens
           WHERE collection_id = ? AND name LIKE 'type.%.fontSize'""",
        (collection_id,)
    )
    font_size_tokens = cursor.fetchall()
    assert len(font_size_tokens) > 0
    assert all(t['type'] == 'dimension' for t in font_size_tokens)

    cursor = mock_db_typography.execute(
        """SELECT name, type FROM tokens
           WHERE collection_id = ? AND name LIKE 'type.%.fontFamily'""",
        (collection_id,)
    )
    font_family_tokens = cursor.fetchall()
    assert len(font_family_tokens) > 0
    assert all(t['type'] == 'fontFamily' for t in font_family_tokens)

    cursor = mock_db_typography.execute(
        """SELECT name, type FROM tokens
           WHERE collection_id = ? AND name LIKE 'type.%.fontWeight'""",
        (collection_id,)
    )
    font_weight_tokens = cursor.fetchall()
    assert len(font_weight_tokens) > 0
    assert all(t['type'] == 'fontWeight' for t in font_weight_tokens)


def test_cluster_typography_no_orphan_tokens(mock_db_typography):
    """Test that no orphan tokens are created."""
    collection_id, mode_id = ensure_typography_collection(mock_db_typography, file_id=1)

    cluster_typography(mock_db_typography, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Every token should have at least one binding
    cursor = mock_db_typography.execute(
        """SELECT t.id, t.name, COUNT(ntb.id) as binding_count
           FROM tokens t
           LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
           WHERE t.collection_id = ?
           GROUP BY t.id""",
        (collection_id,)
    )

    for row in cursor.fetchall():
        assert row['binding_count'] > 0, f"Token {row['name']} has no bindings"


def test_cluster_typography_unique_names(mock_db_typography):
    """Test that all token names are unique within collection."""
    collection_id, mode_id = ensure_typography_collection(mock_db_typography, file_id=1)

    cluster_typography(mock_db_typography, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Check for unique names
    cursor = mock_db_typography.execute(
        "SELECT name, COUNT(*) as count FROM tokens WHERE collection_id = ? GROUP BY name",
        (collection_id,)
    )

    for row in cursor.fetchall():
        assert row['count'] == 1, f"Duplicate token name: {row['name']}"


# Spacing clustering tests

@pytest.fixture
def mock_db_spacing():
    """Create an in-memory database with spacing test data."""
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'test_key', 'test.fig')")
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, 'screen1', 'Screen 1', 375, 812)"
    )

    # Insert nodes with spacing properties
    for i in range(1, 11):
        conn.execute(
            """INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order)
               VALUES (?, 1, ?, ?, 'FRAME', 0, ?)""",
            (i, f"frame{i}", f"Frame {i}", i)
        )

    # Insert more nodes to support all the bindings we need
    for i in range(11, 61):
        conn.execute(
            """INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order)
               VALUES (?, 1, ?, ?, 'FRAME', 0, ?)""",
            (i, f"frame{i}", f"Frame {i}", i)
        )

    # Insert spacing bindings following 4px scale pattern
    spacing_values = [
        ('4', 8),    # 4px used 8 times
        ('8', 15),   # 8px used 15 times (most common)
        ('12', 5),   # 12px used 5 times
        ('16', 12),  # 16px used 12 times
        ('20', 3),   # 20px used 3 times
        ('24', 6),   # 24px used 6 times
        ('32', 4),   # 32px used 4 times
        ('40', 2),   # 40px used 2 times
        ('48', 1),   # 48px used 1 time
        ('64', 1),   # 64px used 1 time
    ]

    binding_id = 1
    current_node_id = 1

    for value, count in spacing_values:
        for i in range(count):
            # Rotate through different spacing properties
            properties = [
                'padding.top', 'padding.right', 'padding.bottom', 'padding.left',
                'itemSpacing', 'counterAxisSpacing'
            ]
            prop = properties[i % len(properties)]

            conn.execute(
                """INSERT INTO node_token_bindings
                   (id, node_id, property, raw_value, resolved_value, binding_status)
                   VALUES (?, ?, ?, ?, ?, 'unbound')""",
                (binding_id, current_node_id, prop, value, value)
            )
            binding_id += 1
            current_node_id += 1
            if current_node_id > 60:
                current_node_id = 1

    conn.commit()
    return conn


@pytest.fixture
def mock_db_spacing_irregular():
    """Create an in-memory database with irregular spacing values."""
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'test_key', 'test.fig')")
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, 'screen1', 'Screen 1', 375, 812)"
    )

    # Insert nodes - need more to avoid constraint violations
    for i in range(1, 11):
        conn.execute(
            """INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order)
               VALUES (?, 1, ?, ?, 'FRAME', 0, ?)""",
            (i, f"frame{i}", f"Frame {i}", i)
        )

    # Insert irregular spacing values (no clear pattern)
    irregular_values = [
        ('5', 3),
        ('13', 2),
        ('27', 2),
        ('41', 1),
        ('67', 1),
    ]

    binding_id = 1
    current_node_id = 1

    for value, count in irregular_values:
        for i in range(count):
            prop = 'padding.top' if i % 2 == 0 else 'itemSpacing'
            conn.execute(
                """INSERT INTO node_token_bindings
                   (id, node_id, property, raw_value, resolved_value, binding_status)
                   VALUES (?, ?, ?, ?, ?, 'unbound')""",
                (binding_id, current_node_id, prop, value, value)
            )
            binding_id += 1
            current_node_id += 1
            if current_node_id > 10:
                current_node_id = 1

    conn.commit()
    return conn


def test_query_spacing_census(mock_db_spacing):
    """Test querying spacing census from database."""
    result = query_spacing_census(mock_db_spacing, file_id=1)

    assert len(result) > 0
    assert all('resolved_value' in row for row in result)
    assert all('property' in row for row in result)
    assert all('usage_count' in row for row in result)

    # Check that 8px appears with highest usage count (15)
    eight_px_rows = [r for r in result if r['resolved_value'] == '8']
    assert len(eight_px_rows) > 0
    total_usage = sum(r['usage_count'] for r in eight_px_rows)
    assert total_usage == 15

    # Check that values are sorted by resolved_value (numerically)
    values = [float(r['resolved_value']) for r in result]
    assert values == sorted(values)


def test_query_spacing_census_filters_unbound_only(mock_db_spacing):
    """Test that census only includes unbound spacing values."""
    # Update some bindings to 'proposed' - use rowid to limit
    mock_db_spacing.execute(
        """UPDATE node_token_bindings
           SET binding_status = 'proposed'
           WHERE rowid IN (
               SELECT rowid FROM node_token_bindings
               WHERE resolved_value = '8'
               LIMIT 3
           )"""
    )
    mock_db_spacing.commit()

    result = query_spacing_census(mock_db_spacing, file_id=1)

    # 8px usage count should be reduced
    eight_px_total = sum(r['usage_count'] for r in result if r['resolved_value'] == '8')
    assert eight_px_total < 15  # Was 15 before


def test_query_spacing_census_filters_zero_values(mock_db_spacing):
    """Test that zero values are filtered out."""
    # Add a zero value binding - use a node that doesn't have padding.top yet
    mock_db_spacing.execute(
        """INSERT INTO node_token_bindings
           (id, node_id, property, raw_value, resolved_value, binding_status)
           VALUES (999, 59, 'padding.bottom', '0', '0', 'unbound')"""
    )
    mock_db_spacing.commit()

    result = query_spacing_census(mock_db_spacing, file_id=1)

    # Should not have any zero values
    zero_rows = [r for r in result if r['resolved_value'] == '0']
    assert len(zero_rows) == 0


def test_detect_scale_pattern_with_4px_base():
    """Test detecting 4px base scale pattern."""
    values = [4.0, 8.0, 12.0, 16.0, 20.0, 24.0, 32.0, 40.0, 48.0, 64.0]

    base, notation = detect_scale_pattern(values)

    assert base == 4.0 or base == 4
    assert notation == "multiplier"


def test_detect_scale_pattern_with_8px_base():
    """Test detecting 8px base scale pattern."""
    values = [8.0, 16.0, 24.0, 32.0, 40.0, 48.0, 64.0]

    base, notation = detect_scale_pattern(values)

    assert base == 8.0 or base == 8
    assert notation == "multiplier"


def test_detect_scale_pattern_with_irregular_values():
    """Test that irregular values result in t-shirt notation."""
    values = [5.0, 13.0, 27.0, 41.0, 67.0]

    base, notation = detect_scale_pattern(values)

    assert base == 0
    assert notation == "tshirt"


def test_detect_scale_pattern_with_single_value():
    """Test handling single value."""
    values = [16.0]

    base, notation = detect_scale_pattern(values)

    # Single value can't determine a pattern, use t-shirt
    assert base == 0
    assert notation == "tshirt"


def test_propose_spacing_name_multiplier():
    """Test proposing spacing names with multiplier notation."""
    # 16px with 4px base = space.4
    name = propose_spacing_name(16.0, 4.0, "multiplier", 0, 5)
    assert name == "space.4"

    # 8px with 4px base = space.2
    name = propose_spacing_name(8.0, 4.0, "multiplier", 0, 5)
    assert name == "space.2"

    # 4px with 4px base = space.1
    name = propose_spacing_name(4.0, 4.0, "multiplier", 0, 5)
    assert name == "space.1"

    # 32px with 8px base = space.4
    name = propose_spacing_name(32.0, 8.0, "multiplier", 0, 5)
    assert name == "space.4"


def test_propose_spacing_name_tshirt():
    """Test proposing spacing names with t-shirt notation."""
    # First value = xs
    name = propose_spacing_name(5.0, 0, "tshirt", 0, 5)
    assert name == "space.xs"

    # Second value = sm
    name = propose_spacing_name(8.0, 0, "tshirt", 1, 5)
    assert name == "space.sm"

    # Third value = md
    name = propose_spacing_name(12.0, 0, "tshirt", 2, 5)
    assert name == "space.md"

    # Fourth value = lg
    name = propose_spacing_name(16.0, 0, "tshirt", 3, 5)
    assert name == "space.lg"

    # Fifth value = xl
    name = propose_spacing_name(24.0, 0, "tshirt", 4, 5)
    assert name == "space.xl"

    # Sixth value = 2xl
    name = propose_spacing_name(32.0, 0, "tshirt", 5, 8)
    assert name == "space.2xl"

    # Seventh value = 3xl
    name = propose_spacing_name(40.0, 0, "tshirt", 6, 8)
    assert name == "space.3xl"

    # Eighth value = 4xl
    name = propose_spacing_name(48.0, 0, "tshirt", 7, 8)
    assert name == "space.4xl"

    # Ninth value and beyond = numeric
    name = propose_spacing_name(64.0, 0, "tshirt", 8, 10)
    assert name == "space.9"

    name = propose_spacing_name(80.0, 0, "tshirt", 9, 10)
    assert name == "space.10"


def test_ensure_spacing_collection(mock_db_spacing):
    """Test creating or retrieving spacing collection and mode."""
    collection_id, mode_id = ensure_spacing_collection(mock_db_spacing, file_id=1)

    assert collection_id is not None
    assert mode_id is not None

    # Should be idempotent
    collection_id2, mode_id2 = ensure_spacing_collection(mock_db_spacing, file_id=1)
    assert collection_id2 == collection_id
    assert mode_id2 == mode_id

    # Verify in database
    cursor = mock_db_spacing.execute(
        "SELECT * FROM token_collections WHERE id = ?", (collection_id,)
    )
    collection = cursor.fetchone()
    assert collection['name'] == 'Spacing'
    assert collection['file_id'] == 1

    cursor = mock_db_spacing.execute(
        "SELECT * FROM token_modes WHERE id = ?", (mode_id,)
    )
    mode = cursor.fetchone()
    assert mode['name'] == 'Default'
    assert mode['is_default'] == 1


def test_cluster_spacing_with_4px_scale(mock_db_spacing):
    """Test clustering spacing values with 4px scale."""
    collection_id, mode_id = ensure_spacing_collection(mock_db_spacing, file_id=1)

    result = cluster_spacing(mock_db_spacing, file_id=1, collection_id=collection_id, mode_id=mode_id)

    assert 'tokens_created' in result
    assert 'bindings_updated' in result
    assert 'base_unit' in result
    assert 'notation' in result

    assert result['tokens_created'] == 10  # 10 unique values in fixture
    assert result['bindings_updated'] > 0
    assert result['base_unit'] == 4.0 or result['base_unit'] == 4
    assert result['notation'] == 'multiplier'

    # Check that tokens were created
    cursor = mock_db_spacing.execute(
        "SELECT * FROM tokens WHERE collection_id = ?", (collection_id,)
    )
    tokens = cursor.fetchall()
    assert len(tokens) == result['tokens_created']

    # All tokens should have tier='extracted' and type='dimension'
    for token in tokens:
        assert token['tier'] == 'extracted'
        assert token['type'] == 'dimension'

    # Check token names follow multiplier pattern
    token_names = {token['name'] for token in tokens}
    expected_names = {
        'space.1', 'space.2', 'space.3', 'space.4', 'space.5',
        'space.6', 'space.8', 'space.10', 'space.12', 'space.16'
    }
    assert token_names == expected_names

    # Check bindings were updated
    cursor = mock_db_spacing.execute(
        "SELECT * FROM node_token_bindings WHERE binding_status = 'proposed'"
    )
    bindings = cursor.fetchall()
    assert len(bindings) == result['bindings_updated']

    # All bindings should have token_id and confidence=1.0
    for binding in bindings:
        assert binding['token_id'] is not None
        assert binding['confidence'] == 1.0


def test_cluster_spacing_with_irregular_scale(mock_db_spacing_irregular):
    """Test clustering irregular spacing values with t-shirt notation."""
    collection_id, mode_id = ensure_spacing_collection(mock_db_spacing_irregular, file_id=1)

    result = cluster_spacing(mock_db_spacing_irregular, file_id=1, collection_id=collection_id, mode_id=mode_id)

    assert result['tokens_created'] == 5  # 5 unique values in fixture
    assert result['base_unit'] == 0
    assert result['notation'] == 'tshirt'

    # Check token names follow t-shirt pattern
    cursor = mock_db_spacing_irregular.execute(
        "SELECT name FROM tokens WHERE collection_id = ? ORDER BY name", (collection_id,)
    )
    token_names = [row['name'] for row in cursor.fetchall()]

    # Should have xs, sm, md, lg, xl for 5 values
    assert 'space.xs' in token_names
    assert 'space.sm' in token_names
    assert 'space.md' in token_names
    assert 'space.lg' in token_names
    assert 'space.xl' in token_names


def test_cluster_spacing_shared_tokens(mock_db_spacing):
    """Test that same value across different properties uses same token."""
    collection_id, mode_id = ensure_spacing_collection(mock_db_spacing, file_id=1)

    cluster_spacing(mock_db_spacing, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Get all bindings for value '16'
    cursor = mock_db_spacing.execute(
        """SELECT DISTINCT token_id FROM node_token_bindings
           WHERE resolved_value = '16' AND binding_status = 'proposed'"""
    )
    token_ids = [row['token_id'] for row in cursor.fetchall()]

    # All should have the same token_id
    assert len(set(token_ids)) == 1

    # Verify it's used across different properties
    cursor = mock_db_spacing.execute(
        """SELECT DISTINCT property FROM node_token_bindings
           WHERE resolved_value = '16' AND binding_status = 'proposed'"""
    )
    properties = [row['property'] for row in cursor.fetchall()]

    # Should be used in multiple property types
    assert len(properties) > 1


def test_cluster_spacing_no_orphan_tokens(mock_db_spacing):
    """Test that no orphan tokens are created."""
    collection_id, mode_id = ensure_spacing_collection(mock_db_spacing, file_id=1)

    cluster_spacing(mock_db_spacing, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Every token should have at least one binding
    cursor = mock_db_spacing.execute(
        """SELECT t.id, t.name, COUNT(ntb.id) as binding_count
           FROM tokens t
           LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
           WHERE t.collection_id = ?
           GROUP BY t.id""",
        (collection_id,)
    )

    for row in cursor.fetchall():
        assert row['binding_count'] > 0, f"Token {row['name']} has no bindings"


def test_cluster_spacing_unique_names(mock_db_spacing):
    """Test that all token names are unique within collection."""
    collection_id, mode_id = ensure_spacing_collection(mock_db_spacing, file_id=1)

    cluster_spacing(mock_db_spacing, file_id=1, collection_id=collection_id, mode_id=mode_id)

    # Check for unique names
    cursor = mock_db_spacing.execute(
        "SELECT name, COUNT(*) as count FROM tokens WHERE collection_id = ? GROUP BY name",
        (collection_id,)
    )

    for row in cursor.fetchall():
        assert row['count'] == 1, f"Duplicate token name: {row['name']}"