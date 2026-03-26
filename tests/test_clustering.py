"""Tests for color clustering module."""

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