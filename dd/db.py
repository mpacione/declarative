"""Database interface for Declarative Design."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from dd import config


def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Get a database connection with appropriate settings.

    Args:
        db_path: Path to database file or ":memory:" for in-memory DB

    Returns:
        Configured sqlite3.Connection object
    """
    conn = sqlite3.connect(db_path, timeout=30.0)

    # Set WAL mode for file-based DBs (skip for :memory:)
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")

    # Busy timeout: when another connection holds the write lock,
    # wait up to 30s before raising 'database is locked'. Covers
    # multi-threaded servers, concurrent CLI + GUI browsers, long-
    # running ingest jobs. Matches the socket timeout above.
    conn.execute("PRAGMA busy_timeout = 30000")

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    # Enable dict-like row access
    conn.row_factory = sqlite3.Row

    return conn


def init_db(db_path: str) -> sqlite3.Connection:
    """
    Initialize a database with the schema from schema.sql.

    Args:
        db_path: Path to database file or ":memory:" for in-memory DB

    Returns:
        Initialized sqlite3.Connection object
    """
    conn = get_connection(db_path)

    # Check if database is already initialized
    cursor = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
    )
    table_count = cursor.fetchone()[0]

    # If tables already exist, skip initialization
    if table_count > 0:
        return conn

    # Read and execute schema
    schema_path = config.SCHEMA_PATH
    with open(schema_path) as f:
        schema_sql = f.read()

    conn.executescript(schema_sql)

    return conn


def update_token_value(
    conn: sqlite3.Connection,
    token_id: int,
    mode_id: int,
    new_resolved: str,
    changed_by: str,
    reason: str = None,
) -> None:
    """Update a token's resolved_value and write an audit history row.

    This is the single authoritative call site for mutating token values.
    It reads the current resolved_value before overwriting so the history
    row captures old → new. Also resets sync_status to 'pending' since the
    value is no longer confirmed against Figma.

    Args:
        conn: Database connection
        token_id: Token to update
        mode_id: Mode to update
        new_resolved: New resolved_value string
        changed_by: Pipeline stage making the change
            ('extract', 'modes', 'curate', 'manual', 'force_renormalize', 'writeback')
        reason: Optional human-readable context for the change
    """
    row = conn.execute(
        "SELECT resolved_value FROM token_values WHERE token_id = ? AND mode_id = ?",
        (token_id, mode_id),
    ).fetchone()
    old_resolved = row["resolved_value"] if row else None

    conn.execute(
        "UPDATE token_values SET resolved_value = ?, sync_status = 'pending' "
        "WHERE token_id = ? AND mode_id = ?",
        (new_resolved, token_id, mode_id),
    )
    conn.execute(
        "INSERT INTO token_value_history (token_id, mode_id, old_resolved, new_resolved, changed_by, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (token_id, mode_id, old_resolved, new_resolved, changed_by, reason),
    )
    conn.commit()


def insert_token_value(
    conn: sqlite3.Connection,
    token_id: int,
    mode_id: int,
    raw_value: str,
    resolved_value: str,
    changed_by: str,
    reason: str = None,
    source: str = "figma",
) -> None:
    """Insert a new token_values row and write an initial history entry.

    Use this for first-write scenarios (mode seeding, token splitting)
    where no previous value exists.

    Args:
        conn: Database connection
        token_id: Token to insert value for
        mode_id: Mode to insert value for
        raw_value: JSON raw value
        resolved_value: Normalized resolved value
        changed_by: Pipeline stage making the change
        reason: Human-readable context
        source: Value provenance ('figma', 'derived', 'manual', 'imported')
    """
    conn.execute(
        "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value, source) "
        "VALUES (?, ?, ?, ?, ?)",
        (token_id, mode_id, raw_value, resolved_value, source),
    )
    conn.execute(
        "INSERT INTO token_value_history (token_id, mode_id, old_resolved, new_resolved, changed_by, reason) "
        "VALUES (?, ?, NULL, ?, ?, ?)",
        (token_id, mode_id, resolved_value, changed_by, reason),
    )
    conn.commit()


def backup_db(source_path: str) -> str:
    """
    Create a timestamped backup of a database file.

    Args:
        source_path: Path to the source database file

    Returns:
        Path to the created backup, or empty string for :memory: DBs

    Raises:
        FileNotFoundError: If source_path doesn't exist
    """
    # Skip backup for in-memory databases
    if source_path == ":memory:":
        return ""

    source = Path(source_path)

    # Check if source exists
    if not source.exists():
        raise FileNotFoundError(f"Source database not found: {source_path}")

    # Create backup directory if it doesn't exist
    backup_dir = config.BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamped backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = source.stem  # filename without extension
    backup_filename = f"backup_{basename}_{timestamp}.db"
    backup_path = backup_dir / backup_filename

    # Copy the database file
    shutil.copy2(source, backup_path)

    # Rotate backups - keep only MAX_BACKUPS most recent
    # Find all backups for this source database
    backup_pattern = f"backup_{basename}_*.db"
    all_backups = sorted(
        backup_dir.glob(backup_pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True  # Most recent first
    )

    # Delete old backups beyond MAX_BACKUPS
    for old_backup in all_backups[config.MAX_BACKUPS:]:
        old_backup.unlink()

    return str(backup_path)


def run_migration(conn: sqlite3.Connection, migration_path: str) -> dict:
    """Run a migration SQL file, skipping columns that already exist.

    Each ALTER TABLE ADD COLUMN statement is executed individually.
    'duplicate column name' errors are silently skipped (idempotent).

    Returns dict with added, skipped, and error counts.
    """
    with open(migration_path) as f:
        sql = f.read()

    added = 0
    skipped = 0
    errors = []

    for line in sql.split("\n"):
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        try:
            conn.execute(line)
            added += 1
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e) or "duplicate column" in str(e).lower():
                skipped += 1
            else:
                errors.append(str(e))

    conn.commit()
    return {"added": added, "skipped": skipped, "errors": errors}


def classify_screens(conn: sqlite3.Connection) -> dict:
    """Classify screens by type based on dimensions.

    Sets screen_type column: app_screen, component_def, icon_def, design_canvas.
    """
    conn.execute("""
        UPDATE screens SET screen_type = CASE
            WHEN width <= 40 AND height <= 40 THEN 'icon_def'
            WHEN width > 2000 OR height > 2000 THEN 'design_canvas'
            WHEN width >= 350 AND height >= 700 THEN 'app_screen'
            ELSE 'component_def'
        END
    """)
    conn.commit()

    cursor = conn.execute("""
        SELECT screen_type, COUNT(*) FROM screens GROUP BY screen_type ORDER BY COUNT(*) DESC
    """)
    return dict(cursor.fetchall())