"""Clustering orchestrator for Phase 5 of token extraction.

This module orchestrates all clustering modules in sequence:
1. Colors - groups by perceptual similarity (delta-E)
2. Typography - groups font combinations into type scales
3. Spacing - detects spacing patterns (multipliers or t-shirt)
4. Radius - groups corner radius values
5. Effects - groups composite shadows

The orchestrator handles advisory locking, error recovery, and summary reporting.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from dd.cluster_colors import cluster_colors, ensure_collection_and_mode
from dd.cluster_typography import cluster_typography, ensure_typography_collection
from dd.cluster_spacing import cluster_spacing, ensure_spacing_collection
from dd.cluster_misc import cluster_radius, cluster_effects, ensure_radius_collection, ensure_effects_collection


def acquire_clustering_lock(conn: sqlite3.Connection, agent_id: str = "clustering", timeout_minutes: int = 10) -> None:
    """Acquire advisory lock for clustering.

    Args:
        conn: Database connection
        agent_id: Agent identifier
        timeout_minutes: Lock timeout in minutes

    Raises:
        RuntimeError: If lock cannot be acquired
    """
    now = datetime.now()
    expires_at = now + timedelta(minutes=timeout_minutes)

    # Check for existing lock
    cursor = conn.execute("""
        SELECT agent_id, expires_at FROM extraction_locks
        WHERE resource = 'clustering'
    """)
    existing = cursor.fetchone()

    if existing:
        # Check if expired
        existing_expires = datetime.fromisoformat(existing['expires_at'])
        if existing_expires > now:
            raise RuntimeError(
                f"Cannot acquire clustering lock - held by {existing['agent_id']} until {existing['expires_at']}"
            )
        else:
            # Delete expired lock
            conn.execute("DELETE FROM extraction_locks WHERE resource = 'clustering'")

    # Acquire new lock
    conn.execute("""
        INSERT INTO extraction_locks (resource, agent_id, expires_at)
        VALUES ('clustering', ?, ?)
    """, (agent_id, expires_at.isoformat()))
    conn.commit()


def release_clustering_lock(conn: sqlite3.Connection) -> None:
    """Release clustering advisory lock.

    Args:
        conn: Database connection
    """
    conn.execute("DELETE FROM extraction_locks WHERE resource = 'clustering'")
    conn.commit()


def run_clustering(conn: sqlite3.Connection, file_id: int, color_threshold: float = 2.0, agent_id: str = "clustering") -> dict:
    """Run all clustering phases in sequence.

    This is the main entry point for Phase 5 clustering. It:
    1. Acquires an advisory lock
    2. Creates collections and modes for each token type
    3. Runs each clustering module in sequence
    4. Generates a summary report
    5. Cleans up orphan tokens
    6. Releases the lock

    Args:
        conn: Database connection
        file_id: File ID to cluster
        color_threshold: Delta-E threshold for color grouping
        agent_id: Agent identifier for locking

    Returns:
        Dict with clustering summary including total_tokens, total_bindings_updated,
        coverage_pct, by_type breakdown, and any errors
    """
    # Enable row factory for dict-like access
    conn.row_factory = sqlite3.Row

    # Acquire lock
    acquire_clustering_lock(conn, agent_id)

    errors = []
    results_by_type = {}

    try:
        # Create collections and modes
        print("[Clustering] Creating collections and modes...")

        # Colors
        try:
            color_coll_id, color_mode_id = ensure_collection_and_mode(conn, file_id, "Colors")
        except Exception as e:
            errors.append(f"Colors collection: {str(e)}")
            color_coll_id = color_mode_id = None

        # Typography
        try:
            type_coll_id, type_mode_id = ensure_typography_collection(conn, file_id)
        except Exception as e:
            errors.append(f"Typography collection: {str(e)}")
            type_coll_id = type_mode_id = None

        # Spacing
        try:
            spacing_coll_id, spacing_mode_id = ensure_spacing_collection(conn, file_id)
        except Exception as e:
            errors.append(f"Spacing collection: {str(e)}")
            spacing_coll_id = spacing_mode_id = None

        # Radius
        try:
            radius_coll_id, radius_mode_id = ensure_radius_collection(conn, file_id)
        except Exception as e:
            errors.append(f"Radius collection: {str(e)}")
            radius_coll_id = radius_mode_id = None

        # Effects
        try:
            effects_coll_id, effects_mode_id = ensure_effects_collection(conn, file_id)
        except Exception as e:
            errors.append(f"Effects collection: {str(e)}")
            effects_coll_id = effects_mode_id = None

        # Run clustering in sequence

        # 1. Colors
        if color_coll_id is not None:
            try:
                color_result = cluster_colors(conn, file_id, color_coll_id, color_mode_id, color_threshold)
                results_by_type['color'] = color_result
                print(f"[Clustering] Colors: {color_result['tokens_created']} tokens, {color_result['bindings_updated']} bindings")
            except Exception as e:
                errors.append(f"Color clustering: {str(e)}")
                results_by_type['color'] = {'tokens_created': 0, 'bindings_updated': 0}
        else:
            results_by_type['color'] = {'tokens_created': 0, 'bindings_updated': 0}

        # 2. Typography
        if type_coll_id is not None:
            try:
                type_result = cluster_typography(conn, file_id, type_coll_id, type_mode_id)
                results_by_type['typography'] = type_result
                print(f"[Clustering] Typography: {type_result['tokens_created']} tokens, {type_result['bindings_updated']} bindings")
            except Exception as e:
                errors.append(f"Typography clustering: {str(e)}")
                results_by_type['typography'] = {'tokens_created': 0, 'bindings_updated': 0}
        else:
            results_by_type['typography'] = {'tokens_created': 0, 'bindings_updated': 0}

        # 3. Spacing
        if spacing_coll_id is not None:
            try:
                spacing_result = cluster_spacing(conn, file_id, spacing_coll_id, spacing_mode_id)
                results_by_type['spacing'] = spacing_result
                print(f"[Clustering] Spacing: {spacing_result['tokens_created']} tokens, {spacing_result['bindings_updated']} bindings")
            except Exception as e:
                errors.append(f"Spacing clustering: {str(e)}")
                results_by_type['spacing'] = {'tokens_created': 0, 'bindings_updated': 0}
        else:
            results_by_type['spacing'] = {'tokens_created': 0, 'bindings_updated': 0}

        # 4. Radius
        if radius_coll_id is not None:
            try:
                radius_result = cluster_radius(conn, file_id, radius_coll_id, radius_mode_id)
                results_by_type['radius'] = radius_result
                print(f"[Clustering] Radius: {radius_result['tokens_created']} tokens, {radius_result['bindings_updated']} bindings")
            except Exception as e:
                errors.append(f"Radius clustering: {str(e)}")
                results_by_type['radius'] = {'tokens_created': 0, 'bindings_updated': 0}
        else:
            results_by_type['radius'] = {'tokens_created': 0, 'bindings_updated': 0}

        # 5. Effects
        if effects_coll_id is not None:
            try:
                effects_result = cluster_effects(conn, file_id, effects_coll_id, effects_mode_id)
                results_by_type['effects'] = effects_result
                print(f"[Clustering] Effects: {effects_result['tokens_created']} tokens, {effects_result['bindings_updated']} bindings")
            except Exception as e:
                errors.append(f"Effects clustering: {str(e)}")
                results_by_type['effects'] = {'tokens_created': 0, 'bindings_updated': 0}
        else:
            results_by_type['effects'] = {'tokens_created': 0, 'bindings_updated': 0}

        # Generate summary
        summary = generate_summary(conn, file_id, results_by_type)

        # Clean up orphan tokens
        orphans = validate_no_orphan_tokens(conn, file_id)
        if orphans:
            print(f"[Clustering] Cleaned up {len(orphans)} orphan tokens")

        # Add errors to summary if any
        if errors:
            summary['errors'] = errors

        # Print final summary
        print("\n=== Clustering Summary ===")
        print(f"Total tokens proposed: {summary['total_tokens']} across {len(results_by_type)} types")
        print(f"Bindings assigned: {summary['total_bindings_updated']}")
        print(f"Bindings flagged (unbound): {summary['remaining_unbound']}")
        print(f"Coverage: {summary['coverage_pct']:.1f}%")

        if errors:
            print(f"\n{len(errors)} errors encountered:")
            for error in errors:
                print(f"  - {error}")

        return summary

    finally:
        # Always release lock
        release_clustering_lock(conn)


def generate_summary(conn: sqlite3.Connection, file_id: int, results: dict) -> dict:
    """Generate clustering summary report.

    Args:
        conn: Database connection
        file_id: File ID
        results: Dict of results by type

    Returns:
        Summary dict with total_tokens, total_bindings_updated, coverage_pct, etc.
    """
    # Query curation progress
    cursor = conn.execute("SELECT * FROM v_curation_progress")
    curation_progress = [dict(row) for row in cursor.fetchall()]

    # Count total tokens
    cursor = conn.execute("""
        SELECT COUNT(*) as count FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
    """, (file_id,))
    total_tokens = cursor.fetchone()['count']

    # Calculate total bindings updated
    total_bindings_updated = sum(
        r.get('bindings_updated', 0) for r in results.values()
    )

    # Get remaining unbound count
    remaining_unbound = 0
    total_bindings = 0
    proposed_count = 0
    bound_count = 0

    for status in curation_progress:
        if status['binding_status'] == 'unbound':
            remaining_unbound = status['binding_count']
        if status['binding_status'] == 'proposed':
            proposed_count = status['binding_count']
        if status['binding_status'] == 'bound':
            bound_count = status['binding_count']
        total_bindings += status['binding_count']

    # Calculate coverage
    if total_bindings > 0:
        coverage_pct = ((proposed_count + bound_count) / total_bindings) * 100
    else:
        coverage_pct = 0.0

    # Build by_type breakdown
    by_type = {}
    for type_name, type_results in results.items():
        by_type[type_name] = {
            'tokens': type_results.get('tokens_created', 0),
            'bindings': type_results.get('bindings_updated', 0)
        }

    return {
        'total_tokens': total_tokens,
        'total_bindings_updated': total_bindings_updated,
        'remaining_unbound': remaining_unbound,
        'coverage_pct': coverage_pct,
        'by_type': by_type,
        'curation_progress': curation_progress
    }


def validate_no_orphan_tokens(conn: sqlite3.Connection, file_id: int) -> list[int]:
    """Find and delete tokens with zero bindings.

    This cleanup ensures the UC-2 requirement that no token exists without bindings.

    Args:
        conn: Database connection
        file_id: File ID to check

    Returns:
        List of deleted token IDs
    """
    # Find orphan tokens
    cursor = conn.execute("""
        SELECT t.id FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
        WHERE tc.file_id = ? AND ntb.id IS NULL
    """, (file_id,))

    orphan_ids = [row['id'] for row in cursor.fetchall()]

    if orphan_ids:
        # Delete token values first
        placeholders = ','.join('?' * len(orphan_ids))
        conn.execute(
            f"DELETE FROM token_values WHERE token_id IN ({placeholders})",
            orphan_ids
        )

        # Delete tokens
        conn.execute(
            f"DELETE FROM tokens WHERE id IN ({placeholders})",
            orphan_ids
        )

        conn.commit()

    return orphan_ids