"""Test clustering orchestrator."""

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from dd.cluster import run_clustering, generate_summary, validate_no_orphan_tokens


@pytest.fixture
def test_db():
    """Create test database with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create tables
    conn.executescript("""
        CREATE TABLE files (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE screens (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );

        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER NOT NULL,
            node_type TEXT,
            font_size REAL,
            font_family TEXT,
            font_weight INTEGER,
            FOREIGN KEY (screen_id) REFERENCES screens(id)
        );

        CREATE TABLE node_token_bindings (
            id INTEGER PRIMARY KEY,
            node_id INTEGER NOT NULL,
            property TEXT NOT NULL,
            resolved_value TEXT,
            token_id INTEGER,
            binding_status TEXT DEFAULT 'unbound',
            confidence REAL,
            FOREIGN KEY (node_id) REFERENCES nodes(id),
            FOREIGN KEY (token_id) REFERENCES tokens(id)
        );

        CREATE TABLE token_collections (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (file_id) REFERENCES files(id),
            UNIQUE(file_id, name)
        );

        CREATE TABLE token_modes (
            id INTEGER PRIMARY KEY,
            collection_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            is_default BOOLEAN DEFAULT 0,
            FOREIGN KEY (collection_id) REFERENCES token_collections(id),
            UNIQUE(collection_id, name)
        );

        CREATE TABLE tokens (
            id INTEGER PRIMARY KEY,
            collection_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            tier TEXT DEFAULT 'custom',
            FOREIGN KEY (collection_id) REFERENCES token_collections(id)
        );

        CREATE TABLE token_values (
            id INTEGER PRIMARY KEY,
            token_id INTEGER NOT NULL,
            mode_id INTEGER NOT NULL,
            raw_value TEXT,
            resolved_value TEXT,
            FOREIGN KEY (token_id) REFERENCES tokens(id),
            FOREIGN KEY (mode_id) REFERENCES token_modes(id)
        );

        CREATE TABLE extraction_locks (
            id INTEGER PRIMARY KEY,
            resource TEXT NOT NULL UNIQUE,
            agent_id TEXT NOT NULL,
            acquired_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            expires_at TEXT NOT NULL
        );

        CREATE VIEW v_curation_progress AS
        SELECT
            binding_status,
            COUNT(*) AS binding_count,
            ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM node_token_bindings), 1) AS pct
        FROM node_token_bindings
        GROUP BY binding_status
        ORDER BY
            CASE binding_status
                WHEN 'bound' THEN 1
                WHEN 'proposed' THEN 2
                WHEN 'overridden' THEN 3
                WHEN 'unbound' THEN 4
            END;
    """)

    # Insert test data
    conn.execute("INSERT INTO files (id, name) VALUES (1, 'test.fig')")
    conn.execute("INSERT INTO screens (id, file_id, name) VALUES (1, 1, 'Screen 1')")
    conn.execute("INSERT INTO nodes (id, screen_id, node_type) VALUES (1, 1, 'FRAME')")
    conn.execute("INSERT INTO nodes (id, screen_id, node_type) VALUES (2, 1, 'RECTANGLE')")

    # Add some unbound bindings
    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, resolved_value, binding_status)
        VALUES (1, 'fill.0.color', '#FFFFFF', 'unbound')
    """)
    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, resolved_value, binding_status)
        VALUES (2, 'stroke.0.color', '#000000', 'unbound')
    """)

    conn.commit()
    yield conn
    conn.close()


def test_run_clustering_acquires_and_releases_lock(test_db):
    """Test that clustering acquires and releases advisory lock."""
    # Mock all clustering functions to succeed
    with patch('dd.cluster.cluster_colors') as mock_colors, \
         patch('dd.cluster.cluster_typography') as mock_type, \
         patch('dd.cluster.cluster_spacing') as mock_spacing, \
         patch('dd.cluster.cluster_radius') as mock_radius, \
         patch('dd.cluster.cluster_effects') as mock_effects, \
         patch('dd.cluster.ensure_collection_and_mode') as mock_color_coll, \
         patch('dd.cluster.ensure_typography_collection') as mock_type_coll, \
         patch('dd.cluster.ensure_spacing_collection') as mock_spacing_coll, \
         patch('dd.cluster.ensure_radius_collection') as mock_radius_coll, \
         patch('dd.cluster.ensure_effects_collection') as mock_effects_coll:

        # Setup mocks - also create collections in DB for token count
        def create_color_collection(conn, file_id, name):
            conn.execute("INSERT OR IGNORE INTO token_collections (id, file_id, name) VALUES (1, ?, ?)", (file_id, name))
            conn.execute("INSERT OR IGNORE INTO token_modes (id, collection_id, name, is_default) VALUES (1, 1, 'Default', 1)")
            # Create 5 tokens
            for i in range(1, 6):
                conn.execute("INSERT INTO tokens (collection_id, name, type) VALUES (1, ?, 'color')", (f'color.{i}',))
            return (1, 1)

        def create_type_collection(conn, file_id):
            conn.execute("INSERT OR IGNORE INTO token_collections (id, file_id, name) VALUES (2, ?, 'Typography')", (file_id,))
            conn.execute("INSERT OR IGNORE INTO token_modes (id, collection_id, name, is_default) VALUES (2, 2, 'Default', 1)")
            # Create 3 tokens
            for i in range(1, 4):
                conn.execute("INSERT INTO tokens (collection_id, name, type) VALUES (2, ?, 'dimension')", (f'type.{i}',))
            return (2, 2)

        def create_spacing_collection(conn, file_id):
            conn.execute("INSERT OR IGNORE INTO token_collections (id, file_id, name) VALUES (3, ?, 'Spacing')", (file_id,))
            conn.execute("INSERT OR IGNORE INTO token_modes (id, collection_id, name, is_default) VALUES (3, 3, 'Default', 1)")
            # Create 4 tokens
            for i in range(1, 5):
                conn.execute("INSERT INTO tokens (collection_id, name, type) VALUES (3, ?, 'dimension')", (f'space.{i}',))
            return (3, 3)

        def create_radius_collection(conn, file_id):
            conn.execute("INSERT OR IGNORE INTO token_collections (id, file_id, name) VALUES (4, ?, 'Radius')", (file_id,))
            conn.execute("INSERT OR IGNORE INTO token_modes (id, collection_id, name, is_default) VALUES (4, 4, 'Default', 1)")
            # Create 3 tokens
            for i in range(1, 4):
                conn.execute("INSERT INTO tokens (collection_id, name, type) VALUES (4, ?, 'dimension')", (f'radius.{i}',))
            return (4, 4)

        def create_effects_collection(conn, file_id):
            conn.execute("INSERT OR IGNORE INTO token_collections (id, file_id, name) VALUES (5, ?, 'Effects')", (file_id,))
            conn.execute("INSERT OR IGNORE INTO token_modes (id, collection_id, name, is_default) VALUES (5, 5, 'Default', 1)")
            # Create 6 tokens
            for i in range(1, 7):
                conn.execute("INSERT INTO tokens (collection_id, name, type) VALUES (5, ?, 'color')", (f'shadow.{i}',))
            return (5, 5)

        mock_color_coll.side_effect = create_color_collection
        mock_type_coll.side_effect = create_type_collection
        mock_spacing_coll.side_effect = create_spacing_collection
        mock_radius_coll.side_effect = create_radius_collection
        mock_effects_coll.side_effect = create_effects_collection

        # Mock clustering to also update bindings so tokens aren't orphans
        def mock_color_clustering(conn, file_id, coll_id, mode_id, threshold):
            # Update bindings to prevent orphans
            conn.execute("UPDATE node_token_bindings SET token_id = 1, binding_status = 'proposed' WHERE id = 1")
            return {'tokens_created': 5, 'bindings_updated': 10, 'groups': 3}

        mock_colors.side_effect = mock_color_clustering
        mock_type.return_value = {'tokens_created': 3, 'bindings_updated': 8, 'type_scales': 2}
        mock_spacing.return_value = {'tokens_created': 4, 'bindings_updated': 6, 'base_unit': 4, 'notation': 'multiplier'}
        mock_radius.return_value = {'tokens_created': 3, 'bindings_updated': 5}
        mock_effects.return_value = {'tokens_created': 6, 'bindings_updated': 12, 'shadow_groups': 2}

        # Run clustering
        result = run_clustering(test_db, 1)

        # Check lock was acquired and released
        cursor = test_db.execute("SELECT * FROM extraction_locks WHERE resource = 'clustering'")
        lock = cursor.fetchone()
        assert lock is None, "Lock should be released after clustering"

        # Check summary
        assert 'total_tokens' in result
        assert 'total_bindings_updated' in result
        assert result['total_tokens'] == 21  # 5+3+4+3+6
        assert result['total_bindings_updated'] == 41  # 10+8+6+5+12


def test_run_clustering_lock_already_held(test_db):
    """Test that clustering fails if lock is already held."""
    # Insert an existing lock
    expires = datetime.now() + timedelta(minutes=5)
    test_db.execute("""
        INSERT INTO extraction_locks (resource, agent_id, expires_at)
        VALUES ('clustering', 'other-agent', ?)
    """, (expires.isoformat(),))
    test_db.commit()

    # Try to run clustering
    with pytest.raises(RuntimeError, match="clustering lock"):
        run_clustering(test_db, 1)


def test_run_clustering_expired_lock(test_db):
    """Test that clustering succeeds if lock is expired."""
    # Insert an expired lock
    expires = datetime.now() - timedelta(minutes=5)
    test_db.execute("""
        INSERT INTO extraction_locks (resource, agent_id, expires_at)
        VALUES ('clustering', 'other-agent', ?)
    """, (expires.isoformat(),))
    test_db.commit()

    # Mock clustering functions
    with patch('dd.cluster.cluster_colors') as mock_colors, \
         patch('dd.cluster.cluster_typography') as mock_type, \
         patch('dd.cluster.cluster_spacing') as mock_spacing, \
         patch('dd.cluster.cluster_radius') as mock_radius, \
         patch('dd.cluster.cluster_effects') as mock_effects, \
         patch('dd.cluster.ensure_collection_and_mode') as mock_color_coll, \
         patch('dd.cluster.ensure_typography_collection') as mock_type_coll, \
         patch('dd.cluster.ensure_spacing_collection') as mock_spacing_coll, \
         patch('dd.cluster.ensure_radius_collection') as mock_radius_coll, \
         patch('dd.cluster.ensure_effects_collection') as mock_effects_coll, \
         patch('dd.cluster.generate_summary') as mock_summary:

        # Setup mocks
        mock_color_coll.return_value = (1, 1)
        mock_type_coll.return_value = (2, 2)
        mock_spacing_coll.return_value = (3, 3)
        mock_radius_coll.return_value = (4, 4)
        mock_effects_coll.return_value = (5, 5)

        mock_colors.return_value = {'tokens_created': 5, 'bindings_updated': 10, 'groups': 3}
        mock_type.return_value = {'tokens_created': 0, 'bindings_updated': 0, 'type_scales': 0}
        mock_spacing.return_value = {'tokens_created': 0, 'bindings_updated': 0, 'base_unit': 0, 'notation': 'none'}
        mock_radius.return_value = {'tokens_created': 0, 'bindings_updated': 0}
        mock_effects.return_value = {'tokens_created': 0, 'bindings_updated': 0, 'shadow_groups': 0}

        # Mock summary to return expected results
        mock_summary.return_value = {
            'total_tokens': 5,
            'total_bindings_updated': 10,
            'remaining_unbound': 0,
            'coverage_pct': 100.0,
            'by_type': {},
            'curation_progress': []
        }

        # Should succeed - expired lock is deleted
        result = run_clustering(test_db, 1)
        assert result['total_tokens'] == 5


def test_run_clustering_partial_failure(test_db):
    """Test that clustering continues if one module fails."""
    with patch('dd.cluster.cluster_colors') as mock_colors, \
         patch('dd.cluster.cluster_typography') as mock_type, \
         patch('dd.cluster.cluster_spacing') as mock_spacing, \
         patch('dd.cluster.cluster_radius') as mock_radius, \
         patch('dd.cluster.cluster_effects') as mock_effects, \
         patch('dd.cluster.ensure_collection_and_mode') as mock_color_coll, \
         patch('dd.cluster.ensure_typography_collection') as mock_type_coll, \
         patch('dd.cluster.ensure_spacing_collection') as mock_spacing_coll, \
         patch('dd.cluster.ensure_radius_collection') as mock_radius_coll, \
         patch('dd.cluster.ensure_effects_collection') as mock_effects_coll, \
         patch('dd.cluster.generate_summary') as mock_summary:

        # Setup mocks
        mock_color_coll.return_value = (1, 1)
        mock_type_coll.return_value = (2, 2)
        mock_spacing_coll.return_value = (3, 3)
        mock_radius_coll.return_value = (4, 4)
        mock_effects_coll.return_value = (5, 5)

        mock_colors.return_value = {'tokens_created': 5, 'bindings_updated': 10, 'groups': 3}
        mock_type.side_effect = Exception("Typography clustering failed")  # This fails
        mock_spacing.return_value = {'tokens_created': 4, 'bindings_updated': 6, 'base_unit': 4, 'notation': 'multiplier'}
        mock_radius.return_value = {'tokens_created': 0, 'bindings_updated': 0}
        mock_effects.return_value = {'tokens_created': 0, 'bindings_updated': 0, 'shadow_groups': 0}

        # Mock summary
        mock_summary.return_value = {
            'total_tokens': 9,
            'total_bindings_updated': 16,
            'remaining_unbound': 0,
            'coverage_pct': 100.0,
            'by_type': {},
            'curation_progress': []
        }

        # Run clustering
        result = run_clustering(test_db, 1)

        # Should have partial results
        assert 'errors' in result
        assert 'Typography' in result['errors'][0]
        assert result['total_tokens'] == 9  # 5+0+4+0+0 (typography failed)

        # Lock should be released
        cursor = test_db.execute("SELECT * FROM extraction_locks WHERE resource = 'clustering'")
        assert cursor.fetchone() is None


def test_generate_summary(test_db):
    """Test summary generation."""
    # Create test data
    test_db.execute("INSERT INTO token_collections (id, file_id, name) VALUES (1, 1, 'Colors')")
    test_db.execute("INSERT INTO token_collections (id, file_id, name) VALUES (2, 1, 'Typography')")
    test_db.execute("INSERT INTO tokens (collection_id, name, type) VALUES (1, 'color.primary', 'color')")
    test_db.execute("INSERT INTO tokens (collection_id, name, type) VALUES (1, 'color.secondary', 'color')")
    test_db.execute("INSERT INTO tokens (collection_id, name, type) VALUES (2, 'type.body.md', 'dimension')")

    # Update some bindings
    test_db.execute("UPDATE node_token_bindings SET binding_status = 'proposed', token_id = 1 WHERE id = 1")
    test_db.commit()

    results = {
        'color': {'tokens_created': 2, 'bindings_updated': 1},
        'typography': {'tokens_created': 1, 'bindings_updated': 0},
        'spacing': {'tokens_created': 0, 'bindings_updated': 0},
        'radius': {'tokens_created': 0, 'bindings_updated': 0},
        'effects': {'tokens_created': 0, 'bindings_updated': 0}
    }

    summary = generate_summary(test_db, 1, results)

    assert summary['total_tokens'] == 3
    assert summary['total_bindings_updated'] == 1
    assert summary['remaining_unbound'] == 1  # 1 still unbound
    assert summary['coverage_pct'] == 50.0  # 1 of 2 proposed


def test_validate_no_orphan_tokens(test_db):
    """Test that orphan tokens are detected and deleted."""
    # Create a collection
    test_db.execute("INSERT INTO token_collections (id, file_id, name) VALUES (1, 1, 'Test')")
    test_db.execute("INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (1, 1, 'Default', 1)")

    # Create a token with bindings
    test_db.execute("INSERT INTO tokens (id, collection_id, name, type) VALUES (1, 1, 'test.bound', 'color')")
    test_db.execute("UPDATE node_token_bindings SET token_id = 1 WHERE id = 1")

    # Create an orphan token (no bindings)
    test_db.execute("INSERT INTO tokens (id, collection_id, name, type) VALUES (2, 1, 'test.orphan', 'color')")
    test_db.commit()

    # Validate
    orphans = validate_no_orphan_tokens(test_db, 1)

    assert len(orphans) == 1
    assert 2 in orphans

    # Check orphan was deleted
    cursor = test_db.execute("SELECT * FROM tokens WHERE id = 2")
    assert cursor.fetchone() is None

    # Check bound token still exists
    cursor = test_db.execute("SELECT * FROM tokens WHERE id = 1")
    assert cursor.fetchone() is not None


def test_run_clustering_idempotency(test_db):
    """Test that run_clustering is idempotent."""
    with patch('dd.cluster.cluster_colors') as mock_colors, \
         patch('dd.cluster.cluster_typography') as mock_type, \
         patch('dd.cluster.cluster_spacing') as mock_spacing, \
         patch('dd.cluster.cluster_radius') as mock_radius, \
         patch('dd.cluster.cluster_effects') as mock_effects, \
         patch('dd.cluster.ensure_collection_and_mode') as mock_color_coll, \
         patch('dd.cluster.ensure_typography_collection') as mock_type_coll, \
         patch('dd.cluster.ensure_spacing_collection') as mock_spacing_coll, \
         patch('dd.cluster.ensure_radius_collection') as mock_radius_coll, \
         patch('dd.cluster.ensure_effects_collection') as mock_effects_coll, \
         patch('dd.cluster.generate_summary') as mock_summary:

        # Setup mocks
        mock_color_coll.return_value = (1, 1)
        mock_type_coll.return_value = (2, 2)
        mock_spacing_coll.return_value = (3, 3)
        mock_radius_coll.return_value = (4, 4)
        mock_effects_coll.return_value = (5, 5)

        # First run
        mock_colors.return_value = {'tokens_created': 5, 'bindings_updated': 10, 'groups': 3}
        mock_type.return_value = {'tokens_created': 3, 'bindings_updated': 8, 'type_scales': 2}
        mock_spacing.return_value = {'tokens_created': 0, 'bindings_updated': 0, 'base_unit': 0, 'notation': 'none'}
        mock_radius.return_value = {'tokens_created': 0, 'bindings_updated': 0}
        mock_effects.return_value = {'tokens_created': 0, 'bindings_updated': 0, 'shadow_groups': 0}

        mock_summary.return_value = {
            'total_tokens': 8,
            'total_bindings_updated': 18,
            'remaining_unbound': 0,
            'coverage_pct': 100.0,
            'by_type': {},
            'curation_progress': []
        }

        result1 = run_clustering(test_db, 1)

        # Second run - should skip already-proposed bindings
        mock_colors.return_value = {'tokens_created': 0, 'bindings_updated': 0, 'groups': 0}
        mock_type.return_value = {'tokens_created': 0, 'bindings_updated': 0, 'type_scales': 0}

        mock_summary.return_value = {
            'total_tokens': 8,
            'total_bindings_updated': 0,
            'remaining_unbound': 0,
            'coverage_pct': 100.0,
            'by_type': {},
            'curation_progress': []
        }

        result2 = run_clustering(test_db, 1)

        # Second run should create no new tokens/bindings
        assert result2['total_tokens'] == 8  # Same as first run (counting actual DB)
        assert result2['total_bindings_updated'] == 0