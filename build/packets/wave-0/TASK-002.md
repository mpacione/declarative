---
taskId: TASK-002
title: "Initialize SQLite DB from schema.sql"
wave: wave-0
testFirst: false
testLevel: unit
dependencies: [TASK-001]
produces:
  - dd/db.py
verify:
  - type: typecheck
    command: 'python -c "from dd.db import get_connection, init_db, backup_db"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.db import init_db; conn = init_db(\":memory:\"); cur = conn.execute(\"SELECT name FROM sqlite_master WHERE type=''table'' ORDER BY name\"); tables = [r[0] for r in cur.fetchall()]; print(tables); assert len(tables) >= 20"'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-002: Initialize SQLite DB from schema.sql

## Spec Context

### From Architecture.md -- DB as Portable Source of Truth

> The DB serves a different audience than Console MCP. Console MCP is the Figma read/write layer. The DB is the universal design system interface that any tool can consume -- including coding agents that do not have Figma running.
>
> SQLite for storage. Portable, zero-config, queryable.

### From User Requirements Spec -- Non-Functional Requirements

> - NFR-1: **Portability** -- SQLite single-file DB. No server, no Docker, no cloud dependency. Copy the .db file and you have the entire design system.
> - NFR-4: **Idempotency** -- Re-running extraction on the same file produces identical DB state (UPSERT semantics on all tables).
> - NFR-9: **Backup before destructive ops** -- Before any bulk curation operation (merge, reject, re-extract), the system creates a timestamped DB snapshot (SQLite `VACUUM INTO` or file copy). Snapshots are rotatable (keep last 5).

### From schema.sql -- Full Schema

> ```sql
> PRAGMA journal_mode = WAL;
> PRAGMA foreign_keys = ON;
>
> CREATE TABLE files (
>     id              INTEGER PRIMARY KEY,
>     file_key        TEXT NOT NULL UNIQUE,
>     name            TEXT NOT NULL,
>     last_modified   TEXT,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     node_count      INTEGER,
>     screen_count    INTEGER,
>     metadata        TEXT
> );
>
> CREATE TABLE token_collections (
>     id              INTEGER PRIMARY KEY,
>     file_id         INTEGER NOT NULL REFERENCES files(id),
>     figma_id        TEXT,
>     name            TEXT NOT NULL,
>     description     TEXT,
>     created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
> );
>
> CREATE TABLE token_modes (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
>     figma_mode_id   TEXT,
>     name            TEXT NOT NULL,
>     is_default      INTEGER NOT NULL DEFAULT 0,
>     UNIQUE(collection_id, name)
> );
>
> CREATE TABLE tokens (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id),
>     name            TEXT NOT NULL,
>     type            TEXT NOT NULL,
>     tier            TEXT NOT NULL DEFAULT 'extracted'
>                     CHECK(tier IN ('extracted', 'curated', 'aliased')),
>     alias_of        INTEGER REFERENCES tokens(id),
>     description     TEXT,
>     figma_variable_id TEXT,
>     sync_status     TEXT NOT NULL DEFAULT 'pending'
>                     CHECK(sync_status IN ('pending', 'figma_only', 'code_only', 'synced', 'drifted')),
>     created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(collection_id, name)
> );
>
> CREATE TRIGGER trg_alias_depth_check
> BEFORE INSERT ON tokens
> WHEN NEW.alias_of IS NOT NULL
> BEGIN
>     SELECT RAISE(ABORT, 'Alias target must not itself be an alias (max depth 1)')
>     WHERE (SELECT alias_of FROM tokens WHERE id = NEW.alias_of) IS NOT NULL;
> END;
>
> CREATE TRIGGER trg_alias_depth_check_update
> BEFORE UPDATE OF alias_of ON tokens
> WHEN NEW.alias_of IS NOT NULL
> BEGIN
>     SELECT RAISE(ABORT, 'Alias target must not itself be an alias (max depth 1)')
>     WHERE (SELECT alias_of FROM tokens WHERE id = NEW.alias_of) IS NOT NULL;
> END;
>
> CREATE TABLE token_values (
>     id              INTEGER PRIMARY KEY,
>     token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id         INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(token_id, mode_id)
> );
>
> CREATE TABLE components (
>     id              INTEGER PRIMARY KEY,
>     file_id         INTEGER NOT NULL REFERENCES files(id),
>     figma_node_id   TEXT NOT NULL,
>     name            TEXT NOT NULL,
>     description     TEXT,
>     category        TEXT,
>     variant_properties TEXT,
>     composition_hint TEXT,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(file_id, figma_node_id)
> );
>
> CREATE TABLE component_variants (
>     id              INTEGER PRIMARY KEY,
>     component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     figma_node_id   TEXT NOT NULL,
>     name            TEXT NOT NULL,
>     properties      TEXT NOT NULL,
>     UNIQUE(component_id, figma_node_id)
> );
>
> CREATE TABLE variant_axes (
>     id              INTEGER PRIMARY KEY,
>     component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     axis_name       TEXT NOT NULL,
>     axis_values     TEXT NOT NULL,
>     is_interaction  INTEGER NOT NULL DEFAULT 0,
>     default_value   TEXT,
>     UNIQUE(component_id, axis_name)
> );
>
> CREATE TABLE variant_dimension_values (
>     id              INTEGER PRIMARY KEY,
>     variant_id      INTEGER NOT NULL REFERENCES component_variants(id) ON DELETE CASCADE,
>     axis_id         INTEGER NOT NULL REFERENCES variant_axes(id) ON DELETE CASCADE,
>     value           TEXT NOT NULL,
>     UNIQUE(variant_id, axis_id)
> );
>
> CREATE TABLE component_slots (
>     id              INTEGER PRIMARY KEY,
>     component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     name            TEXT NOT NULL,
>     slot_type       TEXT,
>     is_required     INTEGER NOT NULL DEFAULT 0,
>     default_content TEXT,
>     sort_order      INTEGER NOT NULL DEFAULT 0,
>     description     TEXT,
>     UNIQUE(component_id, name)
> );
>
> CREATE TABLE component_a11y (
>     id              INTEGER PRIMARY KEY,
>     component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     role            TEXT,
>     required_label  INTEGER NOT NULL DEFAULT 0,
>     focus_order     INTEGER,
>     min_touch_target REAL,
>     keyboard_shortcut TEXT,
>     aria_properties TEXT,
>     notes           TEXT,
>     UNIQUE(component_id)
> );
>
> CREATE TABLE component_responsive (
>     id              INTEGER PRIMARY KEY,
>     component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     breakpoint      TEXT,
>     layout_change   TEXT,
>     visibility      TEXT,
>     slot_changes    TEXT,
>     notes           TEXT,
>     UNIQUE(component_id, breakpoint)
> );
>
> CREATE TABLE patterns (
>     id              INTEGER PRIMARY KEY,
>     name            TEXT NOT NULL UNIQUE,
>     category        TEXT NOT NULL,
>     recipe          TEXT NOT NULL,
>     description     TEXT,
>     source_screens  TEXT,
>     created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
> );
>
> CREATE TABLE screens (
>     id              INTEGER PRIMARY KEY,
>     file_id         INTEGER NOT NULL REFERENCES files(id),
>     figma_node_id   TEXT NOT NULL,
>     name            TEXT NOT NULL,
>     width           REAL NOT NULL,
>     height          REAL NOT NULL,
>     device_class    TEXT,
>     node_count      INTEGER,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(file_id, figma_node_id)
> );
>
> CREATE TABLE nodes (
>     id              INTEGER PRIMARY KEY,
>     screen_id       INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
>     figma_node_id   TEXT NOT NULL,
>     parent_id       INTEGER REFERENCES nodes(id),
>     path            TEXT,
>     name            TEXT NOT NULL,
>     node_type       TEXT NOT NULL,
>     depth           INTEGER NOT NULL DEFAULT 0,
>     sort_order      INTEGER NOT NULL DEFAULT 0,
>     is_semantic     INTEGER NOT NULL DEFAULT 0,
>     component_id    INTEGER REFERENCES components(id),
>     x               REAL,
>     y               REAL,
>     width           REAL,
>     height          REAL,
>     layout_mode     TEXT,
>     padding_top     REAL,
>     padding_right   REAL,
>     padding_bottom  REAL,
>     padding_left    REAL,
>     item_spacing    REAL,
>     counter_axis_spacing REAL,
>     primary_align   TEXT,
>     counter_align   TEXT,
>     layout_sizing_h TEXT,
>     layout_sizing_v TEXT,
>     fills           TEXT,
>     strokes         TEXT,
>     effects         TEXT,
>     corner_radius   TEXT,
>     opacity         REAL DEFAULT 1.0,
>     blend_mode      TEXT DEFAULT 'NORMAL',
>     visible         INTEGER NOT NULL DEFAULT 1,
>     font_family     TEXT,
>     font_weight     INTEGER,
>     font_size       REAL,
>     line_height     TEXT,
>     letter_spacing  TEXT,
>     text_align      TEXT,
>     text_content    TEXT,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(screen_id, figma_node_id)
> );
>
> CREATE TABLE node_token_bindings (
>     id              INTEGER PRIMARY KEY,
>     node_id         INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
>     property        TEXT NOT NULL,
>     token_id        INTEGER REFERENCES tokens(id),
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     confidence      REAL,
>     binding_status  TEXT NOT NULL DEFAULT 'unbound'
>                     CHECK(binding_status IN ('unbound', 'proposed', 'bound', 'overridden')),
>     UNIQUE(node_id, property)
> );
>
> CREATE TABLE code_mappings (
>     id              INTEGER PRIMARY KEY,
>     token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     target          TEXT NOT NULL,
>     identifier      TEXT NOT NULL,
>     file_path       TEXT,
>     extracted_at    TEXT,
>     UNIQUE(token_id, target, identifier)
> );
>
> CREATE TABLE route_mappings (
>     id              INTEGER PRIMARY KEY,
>     screen_id       INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
>     route           TEXT NOT NULL,
>     platform        TEXT NOT NULL DEFAULT 'web',
>     component_path  TEXT,
>     UNIQUE(screen_id, route, platform)
> );
>
> CREATE TABLE extraction_runs (
>     id              INTEGER PRIMARY KEY,
>     file_id         INTEGER NOT NULL REFERENCES files(id),
>     started_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     completed_at    TEXT,
>     agent_id        TEXT,
>     total_screens   INTEGER,
>     extracted_screens INTEGER DEFAULT 0,
>     status          TEXT NOT NULL DEFAULT 'running'
>                     CHECK(status IN ('running', 'completed', 'failed', 'cancelled'))
> );
>
> CREATE TABLE screen_extraction_status (
>     id              INTEGER PRIMARY KEY,
>     run_id          INTEGER NOT NULL REFERENCES extraction_runs(id) ON DELETE CASCADE,
>     screen_id       INTEGER NOT NULL REFERENCES screens(id),
>     status          TEXT NOT NULL DEFAULT 'pending'
>                     CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped')),
>     started_at      TEXT,
>     completed_at    TEXT,
>     node_count      INTEGER,
>     binding_count   INTEGER,
>     error           TEXT,
>     UNIQUE(run_id, screen_id)
> );
>
> CREATE TABLE extraction_locks (
>     id              INTEGER PRIMARY KEY,
>     resource        TEXT NOT NULL UNIQUE,
>     agent_id        TEXT NOT NULL,
>     acquired_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     expires_at      TEXT NOT NULL
> );
>
> CREATE TABLE export_validations (
>     id              INTEGER PRIMARY KEY,
>     run_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     check_name      TEXT NOT NULL,
>     severity        TEXT NOT NULL CHECK(severity IN ('error', 'warning', 'info')),
>     message         TEXT NOT NULL,
>     affected_ids    TEXT,
>     resolved        INTEGER NOT NULL DEFAULT 0
> );
> ```
>
> Plus all indexes and views defined in schema.sql (27 indexes, 15 views).

### From dd/config.py (produced by TASK-001)

> `dd/config.py` exports:
> - `DB_SUFFIX = ".declarative.db"`
> - `SCHEMA_PATH` -- `pathlib.Path` pointing to `schema.sql` at project root
> - `PROJECT_ROOT` -- `pathlib.Path` of the project root
> - `BACKUP_DIR` -- `PROJECT_ROOT / "backups"`
> - `MAX_BACKUPS = 5`
> - `db_path(name: str) -> pathlib.Path` -- returns `PROJECT_ROOT / f"{name}{DB_SUFFIX}"`

## Task

Implement `dd/db.py` with three functions: `get_connection`, `init_db`, and `backup_db`. This module is the sole interface for database access throughout the project.

1. **`get_connection(db_path: str) -> sqlite3.Connection`**:
   - Accept a database path string. The special value `":memory:"` creates an in-memory DB.
   - Set `PRAGMA journal_mode = WAL` (skip for `:memory:`).
   - Set `PRAGMA foreign_keys = ON`.
   - Set `conn.row_factory = sqlite3.Row` for dict-like access.
   - Return the connection.

2. **`init_db(db_path: str) -> sqlite3.Connection`**:
   - Call `get_connection(db_path)` to get a connection.
   - Read `schema.sql` from the path defined in `dd.config.SCHEMA_PATH`.
   - Execute the entire schema SQL via `conn.executescript(sql)`.
   - **Important:** The `PRAGMA journal_mode = WAL` line in schema.sql won't work inside `executescript` for `:memory:` databases -- that's fine, the PRAGMA is already set by `get_connection`. The `executescript` call handles all CREATE TABLE/VIEW/INDEX/TRIGGER statements.
   - Return the connection.
   - Must be idempotent: calling `init_db` on an already-initialized DB should not error (all tables use `CREATE TABLE` which will fail if table exists -- so use `CREATE TABLE IF NOT EXISTS` in the schema, OR catch the error gracefully). **Preferred approach:** wrap the `executescript` in a check: query `sqlite_master` for any table first; if tables already exist, skip the schema execution and just return the connection.

3. **`backup_db(source_path: str) -> str`**:
   - Create the `BACKUP_DIR` if it doesn't exist.
   - Generate a timestamped filename: `backup_{basename}_{YYYYMMDD_HHMMSS}.db` where `basename` is the source filename without extension.
   - Copy the source DB file using `shutil.copy2`.
   - Rotate backups: list all backups matching the pattern for this source, sort by timestamp descending, delete any beyond `MAX_BACKUPS`.
   - Return the path of the created backup.
   - Raise `FileNotFoundError` if source_path doesn't exist.
   - Skip backup (return empty string) if source_path is `":memory:"`.

4. **Ensure schema.sql is present.** The full schema SQL (all 22 tables, 15 views, 27 indexes, 2 triggers) must exist at the path `dd/config.SCHEMA_PATH`. If the file already exists from the spec documents, leave it as-is. If not, create it with the complete schema from the Spec Context above. **Use `CREATE TABLE IF NOT EXISTS`** for all table definitions to ensure idempotency.

## Acceptance Criteria

- [ ] `python -c "from dd.db import get_connection, init_db, backup_db"` exits 0
- [ ] `python -c "from dd.db import init_db; conn = init_db(':memory:'); cur = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\"); tables = [r[0] for r in cur.fetchall()]; print(len(tables)); assert len(tables) >= 20"` exits 0
- [ ] `python -c "from dd.db import init_db; conn = init_db(':memory:'); cur = conn.execute(\"SELECT name FROM sqlite_master WHERE type='view' ORDER BY name\"); views = [r[0] for r in cur.fetchall()]; print(len(views)); assert len(views) >= 14"` exits 0
- [ ] `python -c "from dd.db import init_db; conn = init_db(':memory:'); conn.execute(\"PRAGMA foreign_keys\"); assert conn.execute(\"PRAGMA foreign_keys\").fetchone()[0] == 1"` exits 0
- [ ] `python -c "from dd.db import init_db; c1 = init_db(':memory:'); c2 = init_db(':memory:'); print('idempotent OK')"` exits 0
- [ ] Calling `init_db` twice on the same in-memory connection (by storing it) does not raise an error
- [ ] `backup_db` returns empty string for `":memory:"` source
- [ ] `schema.sql` exists at the project root and contains CREATE TABLE statements for at least: files, tokens, nodes, screens, node_token_bindings

## Notes

- The schema.sql file may already exist from the spec documents. If it does, modify it to use `CREATE TABLE IF NOT EXISTS` instead of `CREATE TABLE` (and `CREATE VIEW IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE TRIGGER IF NOT EXISTS`) for idempotency. If `CREATE TRIGGER IF NOT EXISTS` is not supported by the SQLite version, wrap triggers in a check or use `DROP TRIGGER IF EXISTS` before `CREATE TRIGGER`.
- The `executescript` method does not return row results, so PRAGMAs in the script are executed but their results are silently discarded. This is expected.
- SQLite's `CREATE TRIGGER IF NOT EXISTS` was added in SQLite 3.38.0. If you need to support older versions, use `DROP TRIGGER IF EXISTS trg_name; CREATE TRIGGER trg_name ...` pattern.