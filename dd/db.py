"""Database interface for Declarative Design."""

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

from dd import config


def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Get a database connection with appropriate settings.

    Args:
        db_path: Path to database file or ":memory:" for in-memory DB

    Returns:
        Configured sqlite3.Connection object
    """
    conn = sqlite3.connect(db_path)

    # Set WAL mode for file-based DBs (skip for :memory:)
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")

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
    with open(schema_path, 'r') as f:
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