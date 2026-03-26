---
taskId: TASK-010
title: "Implement file inventory phase (Phase 1)"
wave: wave-1
testFirst: false
testLevel: unit
dependencies: [TASK-002, TASK-003]
produces:
  - dd/extract_inventory.py
verify:
  - type: typecheck
    command: 'python -c "from dd.extract_inventory import populate_file, populate_screens, create_extraction_run, classify_screen"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.db import init_db; from dd.extract_inventory import populate_file; conn = init_db(\":memory:\"); fid = populate_file(conn, \"abc123\", \"Test File\", 100, 5); assert fid == 1; print(\"OK\")"'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-010: Implement file inventory phase (Phase 1)

## Spec Context

### From Technical Design Spec -- Phase 1: File Inventory

> **Tool:** Official MCP `get_metadata` or Console MCP `figma_get_file_data` (depth 1).
> **Purpose:** Enumerate all top-level frames (screens) on the target page without extracting properties.
> **Output:** Populated `files`, `screens`, and `extraction_runs` tables.
>
> ```
> Input:  file_key = "drxXOUOdYEBBQ09mrXJeYu", page = "1312:136189"
> Output: ~230 rows in screens table with figma_node_id, name, width, height, device_class
>         1 row in extraction_runs with status = 'running'
>         ~230 rows in screen_extraction_status with status = 'pending'
> ```
>
> **Device classification logic:**
> | Width | Height | device_class |
> |-------|--------|-------------|
> | 428   | 926    | iphone      |
> | 834   | 1194   | ipad_11     |
> | 1536  | 1152   | ipad_13     |
> | other | other  | unknown     |
>
> **Component sheet detection heuristics** (frames that are NOT screens):
> 1. Name contains "Buttons", "Controls", "Components", "Modals", "Popups", "Icons", "Website", or "Assets" (case-insensitive).
> 2. Dimensions don't match any known device class AND frame contains component definitions (node type = COMPONENT or COMPONENT_SET).
> 3. Frame contains no INSTANCE nodes (it's a definition sheet, not a composed screen).
>
> Frames matching any heuristic are tagged `device_class = component_sheet` and extracted separately for component definitions in Phase 4.

### From User Requirements Spec -- FR-1.6, FR-1.9

> FR-1.6: Classify screens by device class based on dimensions (iPhone 428x926, iPad 11" 834x1194, iPad 12.9" 1536x1152).
> FR-1.9: Extraction is resumable. If interrupted mid-run, re-running resumes from the last incomplete screen without re-extracting completed screens. Tracked via `extraction_runs` and `screen_extraction_status` tables.

### From User Requirements Spec -- NFR-4, NFR-5, NFR-6

> NFR-4: Idempotency -- Re-running extraction on the same file produces identical DB state (UPSERT semantics on all tables).
> NFR-5: Freshness tracking -- Every row carries `extracted_at` timestamp.
> NFR-6: Multi-file -- Schema supports multiple source files from day one via `files` table.

### From schema.sql -- Relevant Tables

> ```sql
> CREATE TABLE IF NOT EXISTS files (
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
> CREATE TABLE IF NOT EXISTS screens (
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
> CREATE TABLE IF NOT EXISTS extraction_runs (
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
> CREATE TABLE IF NOT EXISTS screen_extraction_status (
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
> ```

### From dd/types.py (produced by TASK-003)

> Exports:
> - `DeviceClass` enum with IPHONE, IPAD_11, IPAD_13, WEB, COMPONENT_SHEET, UNKNOWN
> - `classify_device(width: float, height: float) -> DeviceClass`
> - `is_component_sheet_name(name: str) -> bool`
> - `COMPONENT_SHEET_KEYWORDS: list[str]`
> - `RunStatus` enum with RUNNING, COMPLETED, FAILED, CANCELLED
> - `ScreenExtractionStatus` enum with PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED

### From dd/db.py (produced by TASK-002)

> Exports:
> - `get_connection(db_path: str) -> sqlite3.Connection`
> - `init_db(db_path: str) -> sqlite3.Connection`

## Task

Create `dd/extract_inventory.py` implementing Phase 1 of the extraction pipeline. This module receives data that an agent with MCP access has already fetched from Figma -- it does NOT call MCP directly. The functions accept parsed data as parameters.

1. **`populate_file(conn, file_key: str, name: str, node_count: int | None = None, screen_count: int | None = None, last_modified: str | None = None, metadata: str | None = None) -> int`**:
   - UPSERT into the `files` table using `INSERT ... ON CONFLICT(file_key) DO UPDATE SET name=excluded.name, last_modified=excluded.last_modified, node_count=excluded.node_count, screen_count=excluded.screen_count, metadata=excluded.metadata, extracted_at=strftime(...)`.
   - Return the `id` of the file row.
   - After upsert, query `SELECT id FROM files WHERE file_key = ?` to get the id.

2. **`classify_screen(name: str, width: float, height: float, has_components: bool = False, has_instances: bool = True) -> str`**:
   - Apply component sheet detection heuristics in order:
     a. If `is_component_sheet_name(name)` returns True, return `DeviceClass.COMPONENT_SHEET.value`.
     b. If device class from `classify_device(width, height)` is UNKNOWN AND `has_components` is True, return `DeviceClass.COMPONENT_SHEET.value`.
     c. If `has_instances` is False (no INSTANCE nodes means it's a definition sheet), AND device class is UNKNOWN, return `DeviceClass.COMPONENT_SHEET.value`.
     d. Otherwise return `classify_device(width, height).value`.
   - This function is pure (no DB access) and used by `populate_screens`.

3. **`populate_screens(conn, file_id: int, frames: list[dict]) -> list[int]`**:
   - `frames` is a list of dicts, each with keys: `figma_node_id` (str), `name` (str), `width` (float), `height` (float), and optionally `has_components` (bool), `has_instances` (bool).
   - For each frame, call `classify_screen` to determine device_class.
   - UPSERT into `screens` using `INSERT ... ON CONFLICT(file_id, figma_node_id) DO UPDATE SET name=excluded.name, width=excluded.width, height=excluded.height, device_class=excluded.device_class, extracted_at=strftime(...)`.
   - Return list of screen IDs (query after each upsert).
   - Commit after all inserts.

4. **`create_extraction_run(conn, file_id: int, agent_id: str | None = None) -> int`**:
   - Query total screen count from `screens` where `file_id = ?`.
   - INSERT into `extraction_runs` with `status='running'`, `total_screens` = count.
   - For each screen in this file, INSERT into `screen_extraction_status` with `status='pending'`.
   - Return the `run_id`.

5. **`get_pending_screens(conn, run_id: int) -> list[dict]`**:
   - Query `screen_extraction_status ses JOIN screens s ON ses.screen_id = s.id` where `ses.run_id = ?` AND `ses.status = 'pending'`.
   - Also return screens where `status = 'failed'` (for retry).
   - Also skip screens where `status = 'in_progress'` AND `started_at` is less than 10 minutes ago (another agent owns it).
   - Return list of dicts with keys: `screen_id`, `figma_node_id`, `name`, `device_class`, `status_id` (the screen_extraction_status.id).

All functions should `import sqlite3` and use parameterized queries for safety. Import `classify_device` and `is_component_sheet_name` from `dd.types`.

## Acceptance Criteria

- [ ] `python -c "from dd.extract_inventory import populate_file, populate_screens, create_extraction_run, classify_screen, get_pending_screens"` exits 0
- [ ] `populate_file` inserts a new file and returns its integer id
- [ ] `populate_file` called twice with same file_key updates in place (UPSERT), returns same id
- [ ] `classify_screen("Buttons and Controls", 1200, 800)` returns `"component_sheet"`
- [ ] `classify_screen("Home", 428, 926)` returns `"iphone"`
- [ ] `classify_screen("Unknown Frame", 999, 999, has_components=True)` returns `"component_sheet"`
- [ ] `classify_screen("Unknown Frame", 999, 999, has_components=False, has_instances=True)` returns `"unknown"`
- [ ] `populate_screens` inserts screens and returns list of integer ids
- [ ] `populate_screens` is idempotent -- calling twice with same data doesn't duplicate rows
- [ ] `create_extraction_run` creates run + screen_extraction_status rows for all screens
- [ ] `get_pending_screens` returns screens with status pending or failed
- [ ] All DB operations use parameterized queries (no string concatenation of values)

## Notes

- This module processes data already fetched from Figma. The calling agent fetches file metadata via MCP and passes the parsed frame list to `populate_screens`. The module never calls MCP directly.
- The `has_components` and `has_instances` flags in `frames` dicts are optional because the inventory phase may not have deep node info. The first heuristic (name-based) is the most reliable at this stage.
- UPSERT uses SQLite's `INSERT ... ON CONFLICT ... DO UPDATE` syntax which requires the conflicting column(s) to have a UNIQUE constraint (which they do in the schema).