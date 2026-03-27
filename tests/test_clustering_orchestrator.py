"""Test clustering orchestrator."""

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from dd.cluster import run_clustering, generate_summary, validate_no_orphan_tokens


@pytest.fixture
def clustering_db(temp_db):
    """Seed temp_db with base test data for clustering tests."""
    conn = temp_db

    conn.execute(
        "INSERT INTO files (id, file_key, name) VALUES (1, 'test_key_abc', 'test.fig')"
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, '100:1', 'Screen 1', 375, 812)"
    )
    conn.execute(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
        "VALUES (1, 1, '100:2', 'Frame1', 'FRAME')"
    )
    conn.execute(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
        "VALUES (2, 1, '100:3', 'Rect1', 'RECTANGLE')"
    )

    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status)
        VALUES (1, 'fill.0.color', '#FFFFFF', '#FFFFFF', 'unbound')
    """)
    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status)
        VALUES (2, 'stroke.0.color', '#000000', '#000000', 'unbound')
    """)

    conn.commit()
    yield conn


def test_run_clustering_acquires_and_releases_lock(clustering_db):
    """Test that clustering acquires and releases advisory lock."""
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

        def create_color_collection(conn, file_id, name):
            conn.execute(
                "INSERT OR IGNORE INTO token_collections (id, file_id, name) VALUES (1, ?, ?)",
                (file_id, name),
            )
            conn.execute(
                "INSERT OR IGNORE INTO token_modes (id, collection_id, name, is_default) VALUES (1, 1, 'Default', 1)"
            )
            for i in range(1, 6):
                conn.execute(
                    "INSERT INTO tokens (collection_id, name, type) VALUES (1, ?, 'color')",
                    (f'color.{i}',),
                )
            return (1, 1)

        def create_type_collection(conn, file_id):
            conn.execute(
                "INSERT OR IGNORE INTO token_collections (id, file_id, name) VALUES (2, ?, 'Typography')",
                (file_id,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO token_modes (id, collection_id, name, is_default) VALUES (2, 2, 'Default', 1)"
            )
            for i in range(1, 4):
                conn.execute(
                    "INSERT INTO tokens (collection_id, name, type) VALUES (2, ?, 'dimension')",
                    (f'type.{i}',),
                )
            return (2, 2)

        def create_spacing_collection(conn, file_id):
            conn.execute(
                "INSERT OR IGNORE INTO token_collections (id, file_id, name) VALUES (3, ?, 'Spacing')",
                (file_id,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO token_modes (id, collection_id, name, is_default) VALUES (3, 3, 'Default', 1)"
            )
            for i in range(1, 5):
                conn.execute(
                    "INSERT INTO tokens (collection_id, name, type) VALUES (3, ?, 'dimension')",
                    (f'space.{i}',),
                )
            return (3, 3)

        def create_radius_collection(conn, file_id):
            conn.execute(
                "INSERT OR IGNORE INTO token_collections (id, file_id, name) VALUES (4, ?, 'Radius')",
                (file_id,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO token_modes (id, collection_id, name, is_default) VALUES (4, 4, 'Default', 1)"
            )
            for i in range(1, 4):
                conn.execute(
                    "INSERT INTO tokens (collection_id, name, type) VALUES (4, ?, 'dimension')",
                    (f'radius.{i}',),
                )
            return (4, 4)

        def create_effects_collection(conn, file_id):
            conn.execute(
                "INSERT OR IGNORE INTO token_collections (id, file_id, name) VALUES (5, ?, 'Effects')",
                (file_id,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO token_modes (id, collection_id, name, is_default) VALUES (5, 5, 'Default', 1)"
            )
            for i in range(1, 7):
                conn.execute(
                    "INSERT INTO tokens (collection_id, name, type) VALUES (5, ?, 'color')",
                    (f'shadow.{i}',),
                )
            return (5, 5)

        mock_color_coll.side_effect = create_color_collection
        mock_type_coll.side_effect = create_type_collection
        mock_spacing_coll.side_effect = create_spacing_collection
        mock_radius_coll.side_effect = create_radius_collection
        mock_effects_coll.side_effect = create_effects_collection

        def mock_color_clustering(conn, file_id, coll_id, mode_id, threshold):
            conn.execute("UPDATE node_token_bindings SET token_id = 1, binding_status = 'proposed' WHERE id = 1")
            return {'tokens_created': 5, 'bindings_updated': 10, 'groups': 3}

        mock_colors.side_effect = mock_color_clustering
        mock_type.return_value = {'tokens_created': 3, 'bindings_updated': 8, 'type_scales': 2}
        mock_spacing.return_value = {'tokens_created': 4, 'bindings_updated': 6, 'base_unit': 4, 'notation': 'multiplier'}
        mock_radius.return_value = {'tokens_created': 3, 'bindings_updated': 5}
        mock_effects.return_value = {'tokens_created': 6, 'bindings_updated': 12, 'shadow_groups': 2}

        result = run_clustering(clustering_db, 1)

        cursor = clustering_db.execute("SELECT * FROM extraction_locks WHERE resource = 'clustering'")
        lock = cursor.fetchone()
        assert lock is None, "Lock should be released after clustering"

        assert 'total_tokens' in result
        assert 'total_bindings_updated' in result
        assert result['total_tokens'] == 21  # 5+3+4+3+6
        assert result['total_bindings_updated'] == 41  # 10+8+6+5+12


def test_run_clustering_lock_already_held(clustering_db):
    """Test that clustering fails if lock is already held."""
    expires = datetime.now() + timedelta(minutes=5)
    clustering_db.execute("""
        INSERT INTO extraction_locks (resource, agent_id, expires_at)
        VALUES ('clustering', 'other-agent', ?)
    """, (expires.isoformat(),))
    clustering_db.commit()

    with pytest.raises(RuntimeError, match="clustering lock"):
        run_clustering(clustering_db, 1)


def test_run_clustering_expired_lock(clustering_db):
    """Test that clustering succeeds if lock is expired."""
    expires = datetime.now() - timedelta(minutes=5)
    clustering_db.execute("""
        INSERT INTO extraction_locks (resource, agent_id, expires_at)
        VALUES ('clustering', 'other-agent', ?)
    """, (expires.isoformat(),))
    clustering_db.commit()

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

        mock_summary.return_value = {
            'total_tokens': 5,
            'total_bindings_updated': 10,
            'remaining_unbound': 0,
            'coverage_pct': 100.0,
            'by_type': {},
            'curation_progress': []
        }

        result = run_clustering(clustering_db, 1)
        assert result['total_tokens'] == 5


def test_run_clustering_partial_failure(clustering_db):
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

        mock_color_coll.return_value = (1, 1)
        mock_type_coll.return_value = (2, 2)
        mock_spacing_coll.return_value = (3, 3)
        mock_radius_coll.return_value = (4, 4)
        mock_effects_coll.return_value = (5, 5)

        mock_colors.return_value = {'tokens_created': 5, 'bindings_updated': 10, 'groups': 3}
        mock_type.side_effect = Exception("Typography clustering failed")
        mock_spacing.return_value = {'tokens_created': 4, 'bindings_updated': 6, 'base_unit': 4, 'notation': 'multiplier'}
        mock_radius.return_value = {'tokens_created': 0, 'bindings_updated': 0}
        mock_effects.return_value = {'tokens_created': 0, 'bindings_updated': 0, 'shadow_groups': 0}

        mock_summary.return_value = {
            'total_tokens': 9,
            'total_bindings_updated': 16,
            'remaining_unbound': 0,
            'coverage_pct': 100.0,
            'by_type': {},
            'curation_progress': []
        }

        result = run_clustering(clustering_db, 1)

        assert 'errors' in result
        assert 'Typography' in result['errors'][0]
        assert result['total_tokens'] == 9  # 5+0+4+0+0 (typography failed)

        cursor = clustering_db.execute("SELECT * FROM extraction_locks WHERE resource = 'clustering'")
        assert cursor.fetchone() is None


def test_generate_summary(clustering_db):
    """Test summary generation."""
    clustering_db.execute(
        "INSERT INTO token_collections (id, file_id, name) VALUES (1, 1, 'Colors')"
    )
    clustering_db.execute(
        "INSERT INTO token_collections (id, file_id, name) VALUES (2, 1, 'Typography')"
    )
    clustering_db.execute(
        "INSERT INTO tokens (collection_id, name, type) VALUES (1, 'color.primary', 'color')"
    )
    clustering_db.execute(
        "INSERT INTO tokens (collection_id, name, type) VALUES (1, 'color.secondary', 'color')"
    )
    clustering_db.execute(
        "INSERT INTO tokens (collection_id, name, type) VALUES (2, 'type.body.md', 'dimension')"
    )

    clustering_db.execute(
        "UPDATE node_token_bindings SET binding_status = 'proposed', token_id = 1 WHERE id = 1"
    )
    clustering_db.commit()

    results = {
        'color': {'tokens_created': 2, 'bindings_updated': 1},
        'typography': {'tokens_created': 1, 'bindings_updated': 0},
        'spacing': {'tokens_created': 0, 'bindings_updated': 0},
        'radius': {'tokens_created': 0, 'bindings_updated': 0},
        'effects': {'tokens_created': 0, 'bindings_updated': 0}
    }

    summary = generate_summary(clustering_db, 1, results)

    assert summary['total_tokens'] == 3
    assert summary['total_bindings_updated'] == 1
    assert summary['remaining_unbound'] == 1  # 1 still unbound
    assert summary['coverage_pct'] == 50.0  # 1 of 2 proposed


def test_validate_no_orphan_tokens(clustering_db):
    """Test that orphan tokens are detected and deleted."""
    clustering_db.execute(
        "INSERT INTO token_collections (id, file_id, name) VALUES (1, 1, 'Test')"
    )
    clustering_db.execute(
        "INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (1, 1, 'Default', 1)"
    )

    clustering_db.execute(
        "INSERT INTO tokens (id, collection_id, name, type) VALUES (1, 1, 'test.bound', 'color')"
    )
    clustering_db.execute("UPDATE node_token_bindings SET token_id = 1 WHERE id = 1")

    clustering_db.execute(
        "INSERT INTO tokens (id, collection_id, name, type) VALUES (2, 1, 'test.orphan', 'color')"
    )
    clustering_db.commit()

    orphans = validate_no_orphan_tokens(clustering_db, 1)

    assert len(orphans) == 1
    assert 2 in orphans

    cursor = clustering_db.execute("SELECT * FROM tokens WHERE id = 2")
    assert cursor.fetchone() is None

    cursor = clustering_db.execute("SELECT * FROM tokens WHERE id = 1")
    assert cursor.fetchone() is not None


def test_run_clustering_idempotency(clustering_db):
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

        mock_color_coll.return_value = (1, 1)
        mock_type_coll.return_value = (2, 2)
        mock_spacing_coll.return_value = (3, 3)
        mock_radius_coll.return_value = (4, 4)
        mock_effects_coll.return_value = (5, 5)

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

        result1 = run_clustering(clustering_db, 1)

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

        result2 = run_clustering(clustering_db, 1)

        assert result2['total_tokens'] == 8
        assert result2['total_bindings_updated'] == 0
