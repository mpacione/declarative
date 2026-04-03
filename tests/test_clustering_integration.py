"""Integration tests for extraction-to-clustering pipeline.

Tests verify the boundary between extraction output and clustering by running
real clustering on real fixture extraction data and verifying the resulting DB state.
"""

import re
import sqlite3

import pytest

from dd.cluster import run_clustering
from tests.fixtures import seed_post_extraction


@pytest.fixture
def db():
    """Create in-memory SQLite database with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Load schema
    with open("schema.sql") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)

    return conn


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_clustering_consumes_extraction_output(db):
    """Test that clustering successfully consumes extraction output and creates tokens."""
    # Seed with extraction output
    seed_post_extraction(db)

    # Run clustering
    results = run_clustering(db, file_id=1)

    # Verify token_collections table has rows
    cursor = db.execute("SELECT * FROM token_collections WHERE file_id = 1")
    collections = cursor.fetchall()
    assert len(collections) >= 5  # Colors, Typography, Spacing, Radius, Effects

    collection_names = {row['name'] for row in collections}
    assert "Colors" in collection_names
    assert "Typography" in collection_names
    assert "Spacing" in collection_names
    assert "Radius" in collection_names
    assert "Effects" in collection_names

    # Verify token_modes table has rows with is_default=1 for each collection
    for collection in collections:
        cursor = db.execute(
            "SELECT * FROM token_modes WHERE collection_id = ? AND is_default = 1",
            (collection['id'],)
        )
        default_mode = cursor.fetchone()
        assert default_mode is not None, f"Collection {collection['name']} missing default mode"

    # Verify tokens table has rows (all tier="extracted")
    cursor = db.execute("""
        SELECT t.*, tc.name as collection_name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
    """)
    tokens = cursor.fetchall()
    assert len(tokens) > 0, "No tokens created"

    for token in tokens:
        assert token['tier'] == "extracted", f"Token {token['name']} has tier {token['tier']}, expected 'extracted'"

    # Verify token_values table has rows linking to tokens and modes
    cursor = db.execute("""
        SELECT tv.*, t.name as token_name, tm.name as mode_name
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        JOIN token_modes tm ON tv.mode_id = tm.id
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
    """)
    token_values = cursor.fetchall()
    assert len(token_values) > 0, "No token values created"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_tokens_reference_valid_bindings(db):
    """Test FK integrity between tokens and bindings."""
    # Seed and run clustering
    seed_post_extraction(db)
    run_clustering(db, file_id=1)

    # Verify every binding with token_id IS NOT NULL references a valid tokens.id
    cursor = db.execute("""
        SELECT COUNT(*) as count
        FROM node_token_bindings
        WHERE token_id IS NOT NULL
        AND token_id NOT IN (SELECT id FROM tokens)
    """)
    orphan_bindings = cursor.fetchone()['count']
    assert orphan_bindings == 0, "Found bindings referencing non-existent tokens"

    # Verify every token has at least 1 binding (no orphans)
    cursor = db.execute("""
        SELECT t.id, t.name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
        AND NOT EXISTS (
            SELECT 1 FROM node_token_bindings ntb WHERE ntb.token_id = t.id
        )
    """)
    orphan_tokens = cursor.fetchall()
    assert len(orphan_tokens) == 0, f"Found orphan tokens: {[t['name'] for t in orphan_tokens]}"

    # Verify every token_values.token_id references a valid tokens.id
    cursor = db.execute("""
        SELECT COUNT(*) as count
        FROM token_values tv
        WHERE tv.token_id NOT IN (SELECT id FROM tokens)
    """)
    orphan_values = cursor.fetchone()['count']
    assert orphan_values == 0, "Found token values referencing non-existent tokens"

    # Verify every token_values.mode_id references a valid token_modes.id
    cursor = db.execute("""
        SELECT COUNT(*) as count
        FROM token_values tv
        WHERE tv.mode_id NOT IN (SELECT id FROM token_modes)
    """)
    invalid_modes = cursor.fetchone()['count']
    assert invalid_modes == 0, "Found token values referencing non-existent modes"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_census_views_before_and_after_clustering(db):
    """Test that census views produce correct results before and after clustering."""
    # Seed extraction
    seed_post_extraction(db)

    # Query census views BEFORE clustering
    cursor = db.execute("SELECT * FROM v_color_census")
    color_census_before = cursor.fetchall()
    assert len(color_census_before) > 0, "Color census should have data from extraction"

    cursor = db.execute("SELECT * FROM v_type_census")
    type_census_before = cursor.fetchall()
    assert len(type_census_before) > 0, "Type census should have data from extraction"

    cursor = db.execute("SELECT * FROM v_spacing_census")
    spacing_census_before = cursor.fetchall()
    assert len(spacing_census_before) > 0, "Spacing census should have data from extraction"

    # Verify the census data matches fixture
    # We have 5 color bindings with values: #09090B (2x), #FFFFFF, #D4D4D8, #18181B
    color_values = {row['resolved_value'] for row in color_census_before}
    assert "#09090B" in color_values
    assert "#FFFFFF" in color_values
    assert "#D4D4D8" in color_values
    assert "#18181B" in color_values

    # Run clustering
    run_clustering(db, file_id=1)

    # Query v_curation_progress AFTER clustering
    cursor = db.execute("SELECT * FROM v_curation_progress")
    curation_progress = {row['binding_status']: row['binding_count'] for row in cursor.fetchall()}

    # Verify curation progress
    assert "proposed" in curation_progress, "Should have proposed bindings"
    assert curation_progress["proposed"] > 0, "Proposed binding count should be > 0"

    # Verify that unbound count decreased
    initial_bindings = 15  # From fixture
    total_bindings = sum(curation_progress.values())
    assert total_bindings == initial_bindings, f"Total bindings changed from {initial_bindings} to {total_bindings}"

    # Some bindings should have moved from unbound to proposed
    if "unbound" in curation_progress:
        assert curation_progress["unbound"] < initial_bindings, "Some bindings should have been assigned tokens"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_token_coverage_view_after_clustering(db):
    """Test that token coverage view returns correct data after clustering."""
    # Seed and run clustering
    seed_post_extraction(db)
    run_clustering(db, file_id=1)

    # Query v_token_coverage
    cursor = db.execute("SELECT * FROM v_token_coverage")
    token_coverage = cursor.fetchall()

    # Verify we have tokens with coverage
    assert len(token_coverage) > 0, "Token coverage view should return data"

    # Verify tokens have bindings
    tokens_with_bindings = [row for row in token_coverage if row['binding_count'] > 0]
    assert len(tokens_with_bindings) > 0, "Some tokens should have bindings"

    # Verify token types
    token_types = {row['token_type'] for row in token_coverage}
    assert "color" in token_types or "dimension" in token_types, "Should have color or dimension tokens"

    # Verify all tokens have tier="extracted"
    for row in token_coverage:
        assert row['tier'] == "extracted", f"Token {row['token_name']} has tier {row['tier']}"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_binding_status_transition(db):
    """Test that bindings transition from unbound to proposed during clustering."""
    # Seed extraction (all bindings unbound)
    seed_post_extraction(db)

    # Verify initial state: all bindings are unbound
    cursor = db.execute("SELECT binding_status, COUNT(*) as count FROM node_token_bindings GROUP BY binding_status")
    initial_status = {row['binding_status']: row['count'] for row in cursor.fetchall()}
    assert initial_status.get('unbound', 0) == 15, "All 15 bindings should start as unbound"
    assert initial_status.get('proposed', 0) == 0, "No bindings should be proposed initially"

    # Run clustering
    run_clustering(db, file_id=1)

    # Count bindings by status after clustering
    cursor = db.execute("SELECT binding_status, COUNT(*) as count FROM node_token_bindings GROUP BY binding_status")
    final_status = {row['binding_status']: row['count'] for row in cursor.fetchall()}

    # Verify transitions
    assert final_status.get('proposed', 0) > 0, "Some bindings should be proposed"

    # Verify proposed bindings have token_id and confidence
    cursor = db.execute("""
        SELECT * FROM node_token_bindings
        WHERE binding_status = 'proposed'
    """)
    proposed_bindings = cursor.fetchall()

    for binding in proposed_bindings:
        assert binding['token_id'] is not None, f"Proposed binding {binding['id']} missing token_id"
        assert binding['confidence'] is not None, f"Proposed binding {binding['id']} missing confidence"
        assert 0 <= binding['confidence'] <= 1, f"Invalid confidence {binding['confidence']}"

    # Verify remaining unbound bindings have no token_id
    cursor = db.execute("""
        SELECT * FROM node_token_bindings
        WHERE binding_status = 'unbound'
    """)
    unbound_bindings = cursor.fetchall()

    for binding in unbound_bindings:
        assert binding['token_id'] is None, f"Unbound binding {binding['id']} has token_id"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_collection_and_mode_structure(db):
    """Test that collections and modes are properly structured."""
    # Seed and run clustering
    seed_post_extraction(db)
    run_clustering(db, file_id=1)

    # Verify each collection has exactly 1 mode with is_default=1
    cursor = db.execute("""
        SELECT tc.id, tc.name, COUNT(tm.id) as mode_count,
               SUM(CASE WHEN tm.is_default = 1 THEN 1 ELSE 0 END) as default_count
        FROM token_collections tc
        LEFT JOIN token_modes tm ON tm.collection_id = tc.id
        WHERE tc.file_id = 1
        GROUP BY tc.id
    """)

    for collection in cursor.fetchall():
        assert collection['mode_count'] >= 1, f"Collection {collection['name']} has no modes"
        assert collection['default_count'] == 1, f"Collection {collection['name']} needs exactly 1 default mode"

    # Verify collection names are distinct
    cursor = db.execute("""
        SELECT name, COUNT(*) as count
        FROM token_collections
        WHERE file_id = 1
        GROUP BY name
        HAVING COUNT(*) > 1
    """)
    duplicate_collections = cursor.fetchall()
    assert len(duplicate_collections) == 0, f"Duplicate collection names: {[r['name'] for r in duplicate_collections]}"

    # Verify every token belongs to a collection that references file_id=1
    cursor = db.execute("""
        SELECT t.id, t.name, tc.file_id
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id != 1
    """)
    wrong_file_tokens = cursor.fetchall()
    assert len(wrong_file_tokens) == 0, f"Tokens in wrong file: {[t['name'] for t in wrong_file_tokens]}"

    # Verify every token_value references a mode within the token's collection
    cursor = db.execute("""
        SELECT tv.id, t.name as token_name, tm.collection_id as mode_collection, t.collection_id as token_collection
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        JOIN token_modes tm ON tv.mode_id = tm.id
        WHERE tm.collection_id != t.collection_id
    """)
    mismatched_modes = cursor.fetchall()
    assert len(mismatched_modes) == 0, "Token values reference modes from wrong collections"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_token_name_uniqueness_across_collections(db):
    """Test that token names are unique within collections and follow DTCG pattern."""
    # Seed and run clustering
    seed_post_extraction(db)
    run_clustering(db, file_id=1)

    # Verify uniqueness within collections
    cursor = db.execute("""
        SELECT collection_id, name, COUNT(*) as count
        FROM tokens
        GROUP BY collection_id, name
        HAVING COUNT(*) > 1
    """)
    duplicates = cursor.fetchall()
    assert len(duplicates) == 0, f"Duplicate token names: {[(r['collection_id'], r['name']) for r in duplicates]}"

    # Verify token names follow DTCG dot-path pattern
    cursor = db.execute("SELECT id, name FROM tokens")
    tokens = cursor.fetchall()

    # DTCG pattern: letters/numbers (allowing camelCase), dots as separators, optional trailing number
    # This allows both: color.primary and type.body.lg.fontFamily
    dtcg_pattern = re.compile(r'^[a-zA-Z][a-zA-Z0-9]*(\.[a-zA-Z][a-zA-Z0-9]*)*(\.\d+)?$')

    invalid_names = []
    for token in tokens:
        if not dtcg_pattern.match(token['name']):
            invalid_names.append(token['name'])

    assert len(invalid_names) == 0, f"Invalid DTCG token names: {invalid_names}"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_clustering_does_not_modify_extraction_data(db):
    """Test that clustering only modifies binding columns, not extraction data."""
    # Seed extraction
    seed_post_extraction(db)

    # Record initial state
    cursor = db.execute("SELECT COUNT(*) as count FROM nodes")
    initial_node_count = cursor.fetchone()['count']

    cursor = db.execute("SELECT COUNT(*) as count FROM screens")
    initial_screen_count = cursor.fetchone()['count']

    cursor = db.execute("SELECT * FROM files WHERE id = 1")
    initial_file = dict(cursor.fetchone())

    # Sample node properties
    cursor = db.execute("SELECT * FROM nodes WHERE id = 1")
    initial_node = dict(cursor.fetchone())

    # Run clustering
    run_clustering(db, file_id=1)

    # Verify node count unchanged
    cursor = db.execute("SELECT COUNT(*) as count FROM nodes")
    final_node_count = cursor.fetchone()['count']
    assert final_node_count == initial_node_count, "Node count changed"

    # Verify screen count unchanged
    cursor = db.execute("SELECT COUNT(*) as count FROM screens")
    final_screen_count = cursor.fetchone()['count']
    assert final_screen_count == initial_screen_count, "Screen count changed"

    # Verify file data unchanged
    cursor = db.execute("SELECT * FROM files WHERE id = 1")
    final_file = dict(cursor.fetchone())
    assert final_file == initial_file, "File data changed"

    # Verify node properties unchanged (except potential binding updates)
    cursor = db.execute("SELECT * FROM nodes WHERE id = 1")
    final_node = dict(cursor.fetchone())

    # Check all non-binding columns remain the same
    for key in initial_node:
        assert initial_node[key] == final_node[key], f"Node property {key} changed"

    # Verify only binding columns were modified
    cursor = db.execute("""
        SELECT id, node_id, property, raw_value, resolved_value
        FROM node_token_bindings
    """)
    bindings = cursor.fetchall()

    # These columns should not change: id, node_id, property, raw_value, resolved_value
    # Only token_id, binding_status, and confidence should be modified
    assert len(bindings) == 15, "Number of bindings changed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])