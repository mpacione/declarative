"""Database maintenance utilities for Declarative Design.

Handles retention policies for operations tables that grow with each pipeline
run (extraction_runs, screen_extraction_status, export_validations).
"""

import sqlite3


def prune_extraction_runs(conn: sqlite3.Connection, keep_last: int = 50) -> int:
    """Delete old extraction runs beyond the keep_last most recent.

    Cascades to screen_extraction_status via foreign key ON DELETE CASCADE.
    Keeps the pipeline history manageable across many sync cycles.

    Args:
        conn: Database connection
        keep_last: Number of most recent runs to retain

    Returns:
        Number of runs deleted
    """
    to_delete = conn.execute(
        "SELECT id FROM extraction_runs "
        "ORDER BY started_at DESC "
        "LIMIT -1 OFFSET ?",
        (keep_last,),
    ).fetchall()

    if not to_delete:
        return 0

    ids = [row["id"] for row in to_delete]
    placeholders = ",".join("?" * len(ids))

    conn.execute(
        f"DELETE FROM extraction_runs WHERE id IN ({placeholders})", ids
    )
    conn.commit()

    return len(ids)


def prune_export_validations(conn: sqlite3.Connection, keep_last: int = 50) -> int:
    """Delete old export_validations runs beyond the keep_last most recent.

    Args:
        conn: Database connection
        keep_last: Number of most recent run timestamps to retain

    Returns:
        Number of rows deleted
    """
    cutoff = conn.execute(
        "SELECT run_at FROM export_validations "
        "ORDER BY run_at DESC "
        "LIMIT 1 OFFSET ?",
        (keep_last,),
    ).fetchone()

    if not cutoff:
        return 0

    result = conn.execute(
        "DELETE FROM export_validations WHERE run_at <= ?",
        (cutoff["run_at"],),
    )
    conn.commit()

    return result.rowcount
