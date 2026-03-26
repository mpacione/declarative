---
taskId: TASK-014
title: "Implement extraction orchestrator with resume support"
wave: wave-1
testFirst: false
testLevel: unit
dependencies: [TASK-010, TASK-011, TASK-012, TASK-013]
produces:
  - dd/extract.py
verify:
  - type: typecheck
    command: 'python -c "from dd.extract import run_inventory, run_screen_extraction, run_extraction_pipeline"'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-014: Implement extraction orchestrator with resume support

## Spec Context

### From Technical Design Spec -- Phase 2: Extraction run coordination

> 1. Before extracting, check `screen_extraction_status` for this run.
> 2. Skip screens with `status = 'completed'` (resume support).
> 3. Skip screens with `status = 'in_progress'` and `started_at` < 10 min ago (another agent owns it).
> 4. Set `status = 'in_progress'` before calling `use_figma`.
> 5. Set `status = 'completed'` after successful DB write. Update `node_count`, `binding_count`.
> 6. Set `status = 'failed'` with `error` message on failure.

### From Technical Design Spec -- Error handling

> - Screen-level checkpointing via `screen_extraction_status`. If extraction fails on screen 147, resume picks up from 147.
> - `extracted_at` timestamps enable freshness comparison -- stale screens can be re-extracted selectively.
> - Idempotent writes -- re-extracting a screen UPSERTs all rows.

### From User Requirements Spec -- FR-1.9, NFR-7

> FR-1.9: Extraction is resumable. If interrupted mid-run, re-running resumes from the last incomplete screen without re-extracting completed screens.
> NFR-7: Observability -- Extraction pipeline reports progress per-screen (N/total, elapsed, ETA).

### From schema.sql -- Operations tables

> ```sql
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

### From dd/extract_inventory.py (produced by TASK-010)

> Exports:
> - `populate_file(conn, file_key, name, ...) -> int` -- UPSERT file, return id
> - `populate_screens(conn, file_id, frames: list[dict]) -> list[int]` -- UPSERT screens, return ids
> - `create_extraction_run(conn, file_id, agent_id) -> int` -- create run + pending statuses
> - `get_pending_screens(conn, run_id) -> list[dict]` -- get screens to process

### From dd/extract_screens.py (produced by TASK-011)

> Exports:
> - `generate_extraction_script(screen_node_id: str) -> str` -- JS for use_figma
> - `parse_extraction_response(response: list[dict]) -> list[dict]` -- clean raw response
> - `compute_is_semantic(nodes: list[dict]) -> list[dict]` -- apply semantic rules
> - `insert_nodes(conn, screen_id, nodes: list[dict]) -> list[int]` -- UPSERT nodes
> - `update_screen_status(conn, run_id, screen_id, status, ...)` -- update extraction status

### From dd/extract_bindings.py (produced by TASK-012)

> Exports:
> - `create_bindings_for_screen(conn, screen_id) -> int` -- create bindings for all nodes in screen

### From dd/paths.py (produced by TASK-013)

> Exports:
> - `compute_paths_and_semantics(conn, screen_id) -> None` -- compute paths + is_semantic

## Task

Create `dd/extract.py` -- the main extraction orchestrator that coordinates the full pipeline: inventory, screen extraction, binding creation, and path computation. This module provides functions that an agent with MCP access calls step-by-step, passing MCP responses as parameters. It does NOT call MCP directly.

1. **`run_inventory(conn, file_key: str, file_name: str, frames: list[dict], node_count: int | None = None, agent_id: str | None = None) -> dict`**:
   - Call `populate_file(conn, file_key, file_name, node_count, len(frames))` to UPSERT the file.
   - Call `populate_screens(conn, file_id, frames)` to UPSERT all screens.
   - Call `create_extraction_run(conn, file_id, agent_id)` to create the run.
   - Return a dict: `{"file_id": int, "run_id": int, "screen_count": int, "pending_screens": list[dict]}` where `pending_screens` comes from `get_pending_screens`.

2. **`process_screen(conn, run_id: int, screen_id: int, figma_node_id: str, raw_response: list[dict]) -> dict`**:
   - This is the core per-screen function. The calling agent has already called `use_figma` with the script from `generate_extraction_script` and passes the raw response here.
   - Mark screen as `in_progress` via `update_screen_status`.
   - Call `parse_extraction_response(raw_response)` to clean the data.
   - Call `compute_is_semantic(parsed_nodes)` to set semantic flags.
   - Call `insert_nodes(conn, screen_id, nodes)` to write to DB.
   - Call `compute_paths_and_semantics(conn, screen_id)` to compute paths and update is_semantic in DB.
   - Call `create_bindings_for_screen(conn, screen_id)` to create bindings.
   - Mark screen as `completed` with node_count and binding_count.
   - Update `extraction_runs.extracted_screens` by incrementing.
   - Return a dict: `{"screen_id": int, "node_count": int, "binding_count": int, "status": "completed"}`.
   - If any step raises an exception, catch it, mark screen as `failed` with error message, re-raise or return error dict.

3. **`get_next_screen(conn, run_id: int) -> dict | None`**:
   - Call `get_pending_screens(conn, run_id)`.
   - Return the first screen dict, or None if no screens remain.
   - This is what the calling agent uses to determine the next screen to extract.

4. **`get_extraction_script(screen_figma_node_id: str) -> str`**:
   - Thin wrapper around `generate_extraction_script`.
   - Provided for convenience so the agent only needs to import `dd.extract`.

5. **`complete_run(conn, run_id: int) -> dict`**:
   - Query `screen_extraction_status` to count completed, failed, skipped screens.
   - If all screens are completed: update `extraction_runs.status = 'completed'`, set `completed_at`.
   - If any screens failed: update `extraction_runs.status = 'failed'`.
   - Return a summary dict: `{"run_id": int, "status": str, "total_screens": int, "completed": int, "failed": int, "skipped": int}`.

6. **`run_extraction_pipeline(conn, file_key: str, file_name: str, frames: list[dict], extract_fn: callable, node_count: int | None = None, agent_id: str | None = None) -> dict`**:
   - High-level convenience function that runs the full pipeline.
   - Calls `run_inventory` to set up.
   - Loops through screens: for each pending screen, calls `extract_fn(screen_figma_node_id)` to get the raw response (this is a callback the agent provides that wraps the MCP call), then calls `process_screen`.
   - Reports progress to stdout: `f"Screen {i}/{total}: {screen_name} - {node_count} nodes, {binding_count} bindings"`.
   - Calls `complete_run` at the end.
   - Returns the summary dict from `complete_run`.
   - **Resume support**: If `run_inventory` is called on a file that already has an active (running) extraction_run, reuse that run instead of creating a new one. Check for existing runs with `status = 'running'` for this file_id.

7. **Progress reporting**: Import `time` module. Track `start_time` at pipeline start. For each screen, compute elapsed time and estimated remaining time. Print progress to stdout:
   ```
   [N/TOTAL] Screen "name" (device_class) - X nodes, Y bindings - elapsed: Xs, ETA: Ys
   ```

## Acceptance Criteria

- [ ] `python -c "from dd.extract import run_inventory, process_screen, get_next_screen, get_extraction_script, complete_run, run_extraction_pipeline"` exits 0
- [ ] `run_inventory` creates file, screens, extraction_run, and returns dict with file_id, run_id, screen_count
- [ ] `process_screen` takes raw MCP response and writes nodes + bindings + paths to DB
- [ ] `process_screen` marks screen as completed with correct node_count and binding_count
- [ ] `process_screen` marks screen as failed with error message if an exception occurs
- [ ] `get_next_screen` returns None when no pending screens remain
- [ ] `complete_run` sets extraction_runs.status to completed when all screens done
- [ ] `complete_run` sets extraction_runs.status to failed when any screen failed
- [ ] `run_extraction_pipeline` runs the full loop using the extract_fn callback
- [ ] Resume support: calling run_inventory on same file reuses existing running run
- [ ] Progress output is printed to stdout during pipeline execution

## Notes

- This module is the coordination layer. It imports and calls functions from `dd/extract_inventory.py`, `dd/extract_screens.py`, `dd/extract_bindings.py`, and `dd/paths.py`.
- The `extract_fn` callback in `run_extraction_pipeline` abstracts the MCP call. In tests, this will be a mock. In production, the agent provides a function that calls `use_figma` and returns the result.
- Resume support requires checking for existing running runs. If found, reuse the run_id and `get_pending_screens` will automatically skip completed screens.
- Error handling is critical: a single screen failure should not abort the entire pipeline. The orchestrator continues with remaining screens and reports failures at the end.
- The `compute_is_semantic` in `extract_screens.py` computes semantic flags on the in-memory node list before insertion. The `compute_paths_and_semantics` in `paths.py` then updates them in the DB (including the bottom-up rule 4 which needs the full tree). Both are needed because the in-memory version handles rules 1-3 efficiently during parse, and the DB version handles rule 4 with the complete parent-child relationships.