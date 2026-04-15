"""Configuration constants and paths for Declarative Design."""

from pathlib import Path

# Database naming convention
DB_SUFFIX = ".declarative.db"

# Paths
SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"
PROJECT_ROOT = Path(__file__).parent.parent
BACKUP_DIR = PROJECT_ROOT / "backups"

# Limits and timeouts
MAX_BACKUPS = 5  # Rotation limit per NFR-9
LOCK_TIMEOUT_MINUTES = 10  # Advisory lock expiry
MAX_TOKENS_PER_CALL = 100  # Figma API limit per C-3
MAX_BINDINGS_PER_SCRIPT = 950  # Rebind script batch size (compact format, fits 50K char limit)
USE_FIGMA_CODE_LIMIT = 50000  # Character limit per C-1