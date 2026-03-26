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