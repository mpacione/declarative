"""Curation progress and export readiness reporting."""

from __future__ import annotations

import sqlite3
from collections import Counter


def get_curation_progress(conn: sqlite3.Connection) -> list[dict]:
    """
    Query curation progress from v_curation_progress view.

    Returns:
        List of dicts with status, count, and pct keys.
        Empty list if no bindings exist.
    """
    cursor = conn.execute("""
        SELECT binding_status, COUNT(*) AS binding_count
        FROM node_token_bindings
        GROUP BY binding_status
    """)

    rows = cursor.fetchall()
    if not rows:
        return []

    # Calculate total for percentages
    total = sum(row['binding_count'] for row in rows)
    if total == 0:
        return []

    result = []
    for row in rows:
        result.append({
            'status': row['binding_status'],
            'count': row['binding_count'],
            'pct': round(100.0 * row['binding_count'] / total, 1)
        })

    # Sort by the order specified in the view
    order = {'bound': 1, 'proposed': 2, 'overridden': 3, 'unbound': 4}
    result.sort(key=lambda x: order.get(x['status'], 5))

    return result


def get_token_coverage(conn: sqlite3.Connection, file_id: int | None = None) -> list[dict]:
    """
    Query token coverage from v_token_coverage view.

    Args:
        conn: Database connection
        file_id: Optional file ID to filter by

    Returns:
        List of dicts with token_name, token_type, tier, binding_count, node_count, screen_count.
        Sorted by binding_count descending.
    """
    if file_id is not None:
        query = """
            SELECT
                t.name AS token_name,
                t.type AS token_type,
                t.tier,
                COUNT(ntb.id) AS binding_count,
                COUNT(DISTINCT ntb.node_id) AS node_count,
                COUNT(DISTINCT n.screen_id) AS screen_count
            FROM tokens t
            JOIN token_collections tc ON t.collection_id = tc.id
            LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
            LEFT JOIN nodes n ON ntb.node_id = n.id
            WHERE tc.file_id = ?
            GROUP BY t.id
            ORDER BY binding_count DESC
        """
        cursor = conn.execute(query, (file_id,))
    else:
        query = """
            SELECT
                t.name AS token_name,
                t.type AS token_type,
                t.tier,
                COUNT(ntb.id) AS binding_count,
                COUNT(DISTINCT ntb.node_id) AS node_count,
                COUNT(DISTINCT n.screen_id) AS screen_count
            FROM tokens t
            LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
            LEFT JOIN nodes n ON ntb.node_id = n.id
            GROUP BY t.id
            ORDER BY binding_count DESC
        """
        cursor = conn.execute(query)

    result = []
    for row in cursor:
        result.append({
            'token_name': row['token_name'],
            'token_type': row['token_type'],
            'tier': row['tier'],
            'binding_count': row['binding_count'],
            'node_count': row['node_count'],
            'screen_count': row['screen_count']
        })

    return result


def get_unbound_summary(conn: sqlite3.Connection, file_id: int | None = None, limit: int = 50) -> list[dict]:
    """
    Query unbound bindings from v_unbound view.

    Args:
        conn: Database connection
        file_id: Optional file ID to filter by
        limit: Maximum rows to return

    Returns:
        List of dicts with binding_id, screen_name, node_name, node_type, property, resolved_value.
    """
    if file_id is not None:
        query = """
            SELECT
                ntb.id AS binding_id,
                s.name AS screen_name,
                n.name AS node_name,
                n.node_type,
                ntb.property,
                ntb.resolved_value
            FROM node_token_bindings ntb
            JOIN nodes n ON ntb.node_id = n.id
            JOIN screens s ON n.screen_id = s.id
            WHERE ntb.token_id IS NULL AND s.file_id = ?
            ORDER BY ntb.resolved_value
            LIMIT ?
        """
        cursor = conn.execute(query, (file_id, limit))
    else:
        query = """
            SELECT
                ntb.id AS binding_id,
                s.name AS screen_name,
                n.name AS node_name,
                n.node_type,
                ntb.property,
                ntb.resolved_value
            FROM node_token_bindings ntb
            JOIN nodes n ON ntb.node_id = n.id
            JOIN screens s ON n.screen_id = s.id
            WHERE ntb.token_id IS NULL
            ORDER BY ntb.resolved_value
            LIMIT ?
        """
        cursor = conn.execute(query, (limit,))

    result = []
    for row in cursor:
        result.append({
            'binding_id': row['binding_id'],
            'screen_name': row['screen_name'],
            'node_name': row['node_name'],
            'node_type': row['node_type'],
            'property': row['property'],
            'resolved_value': row['resolved_value']
        })

    return result


def get_export_readiness(conn: sqlite3.Connection) -> list[dict]:
    """
    Query export readiness from v_export_readiness view.

    Returns:
        List of dicts with check_name, severity, issue_count, resolved_count.
        Empty list if no validation has been run.
    """
    cursor = conn.execute("""
        SELECT
            check_name,
            severity,
            COUNT(*) AS issue_count,
            SUM(resolved) AS resolved_count
        FROM export_validations
        WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
        GROUP BY check_name, severity
        ORDER BY
            CASE severity
                WHEN 'error' THEN 1
                WHEN 'warning' THEN 2
                ELSE 3
            END
    """)

    result = []
    for row in cursor:
        result.append({
            'check_name': row['check_name'],
            'severity': row['severity'],
            'issue_count': row['issue_count'],
            'resolved_count': row['resolved_count'] or 0
        })

    return result


def format_status_report(conn: sqlite3.Connection, file_id: int | None = None) -> str:
    """
    Build a human-readable text report combining all status queries.

    Args:
        conn: Database connection
        file_id: Optional file ID to filter by

    Returns:
        Formatted string report
    """
    lines = []

    # Curation Progress
    lines.append("=== Curation Progress ===")
    progress = get_curation_progress(conn)
    if progress:
        for item in progress:
            lines.append(f"{item['status']:12} {item['count']} bindings ({item['pct']}%)")
    else:
        lines.append("No bindings found")

    lines.append("")

    # Token Coverage
    lines.append("=== Token Coverage ===")
    coverage = get_token_coverage(conn, file_id)
    lines.append(f"Total tokens: {len(coverage)}")

    if coverage:
        lines.append("Top tokens by usage:")
        for token in coverage[:5]:  # Top 5
            if token['binding_count'] > 0:
                lines.append(
                    f"  {token['token_name']:30} ({token['token_type']:<10}) - "
                    f"{token['binding_count']} bindings across {token['screen_count']} screens"
                )

    lines.append("")

    # Unbound Bindings
    lines.append("=== Unbound Bindings ===")
    unbound = get_unbound_summary(conn, file_id)
    lines.append(f"{len(unbound)} bindings remain unbound")

    if unbound:
        # Count occurrences of each value
        value_counts = Counter(b['resolved_value'] for b in unbound)
        top_values = value_counts.most_common(5)
        if top_values:
            value_str = ", ".join(f"{val} ({count}x)" for val, count in top_values)
            lines.append(f"Top values: {value_str}")

    lines.append("")

    # Export Readiness
    lines.append("=== Export Readiness ===")
    readiness = get_export_readiness(conn)

    if not readiness:
        lines.append("[not yet validated]")
    else:
        # Count errors and warnings
        errors = sum(r['issue_count'] for r in readiness if r['severity'] == 'error')
        warnings = sum(r['issue_count'] for r in readiness if r['severity'] == 'warning')

        if errors == 0 and warnings == 0:
            lines.append("PASS: Ready for export")
        else:
            lines.append(f"PASS: {errors} errors, {warnings} warnings")

            # List issues by severity
            if errors > 0:
                lines.append("Errors:")
                for r in readiness:
                    if r['severity'] == 'error':
                        lines.append(f"  {r['check_name']}: {r['issue_count']} issues")

            if warnings > 0:
                lines.append("Warnings:")
                for r in readiness:
                    if r['severity'] == 'warning':
                        lines.append(f"  {r['check_name']}: {r['issue_count']} issues")

    return "\n".join(lines)


def get_status_dict(conn: sqlite3.Connection, file_id: int | None = None) -> dict:
    """
    Return a structured dict combining all status data.

    Args:
        conn: Database connection
        file_id: Optional file ID to filter by

    Returns:
        Dict with curation_progress, token_count, token_coverage (top 10),
        unbound_count, export_readiness, and is_ready flag.
    """
    progress = get_curation_progress(conn)
    coverage = get_token_coverage(conn, file_id)
    unbound = get_unbound_summary(conn, file_id)
    readiness = get_export_readiness(conn)

    # Determine if ready for export
    if not readiness:
        is_ready = False  # No validation run
    else:
        # Ready if no error-severity issues
        error_count = sum(r['issue_count'] for r in readiness if r['severity'] == 'error')
        is_ready = error_count == 0

    return {
        'curation_progress': progress,
        'token_count': len(coverage),
        'token_coverage': coverage[:10],  # Top 10 only
        'unbound_count': len(unbound),
        'export_readiness': readiness,
        'is_ready': is_ready
    }