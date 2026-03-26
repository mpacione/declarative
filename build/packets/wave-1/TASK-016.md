---
taskId: TASK-016
title: "Write integration tests for extraction pipeline"
wave: wave-1
testFirst: false
testLevel: integration
dependencies: [TASK-007, TASK-014]
produces:
  - tests/test_extraction_integration.py
verify:
  - type: test
    command: 'pytest tests/test_extraction_integration.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-016: Write integration tests for extraction pipeline

## Spec Context

### From Task Decomposition Guide -- Testing Strategy

> **Integration tests** (wave 1+): Test cross-module boundaries using fixture DBs with real pipeline output. No mocks at the seam being tested -- only external dependencies (Figma MCP) are mocked. These catch: schema mismatches between producer/consumer, FK violations, incorrect data shapes flowing across module boundaries.

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `seed_post_extraction(db) -> sqlite3.Connection` -- inserts files, screens, nodes, bindings matching mock Figma data
> - `make_mock_figma_response(screen_name: str, node_count: int = 10) -> list[dict]` -- returns mock use_figma response data

### From tests/conftest.py (produced by TASK-007)

> Provides:
> - `db` fixture: in-memory SQLite connection with full schema
> - `db_with_file` fixture: db + one file row inserted

### From dd/extract.py (produced by TASK-014)

> Exports:
> - `run_inventory(conn, file_key, file_name, frames, ...) -> dict`
> - `process_screen(conn, run_id, screen_id, figma_node_id, raw_response) -> dict`
> - `get_next_screen(conn, run_id) -> dict | None`
> - `complete_run(conn, run_id) -> dict`
> - `run_extraction_pipeline(conn, file_key, file_name, frames, extract_fn, ...) -> dict`

### From dd/extract_inventory.py (produced by TASK-010)

> Exports:
> - `populate_file(conn, file_key, name, ...) -> int`
> - `populate_screens(conn, file_id, frames) -> list[int]`
> - `create_extraction_run(conn, file_id, agent_id) -> int`
> - `get_pending_screens(conn, run_id) -> list[dict]`

### From dd/extract_bindings.py (produced by TASK-012)

> Exports:
> - `create_bindings_for_screen(conn, screen_id) -> int`

### From dd/paths.py (produced by TASK-013)

> Exports:
> - `compute_paths_and_semantics(conn, screen_id) -> None`

### From schema.sql -- Key Tables and Views

> ```sql
> CREATE TABLE IF NOT EXISTS files (
>     id INTEGER PRIMARY KEY, file_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, ...
> );
> CREATE TABLE IF NOT EXISTS screens (
>     id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id),
>     figma_node_id TEXT NOT NULL, name TEXT NOT NULL, width REAL NOT NULL, height REAL NOT NULL,
>     device_class TEXT, node_count INTEGER, ...
>     UNIQUE(file_id, figma_node_id)
> );
> CREATE TABLE IF NOT EXISTS nodes (
>     id INTEGER PRIMARY KEY, screen_id INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
>     figma_node_id TEXT NOT NULL, parent_id INTEGER REFERENCES nodes(id),
>     path TEXT, name TEXT NOT NULL, node_type TEXT NOT NULL, ...
>     UNIQUE(screen_id, figma_node_id)
> );
> CREATE TABLE IF NOT EXISTS node_token_bindings (
>     id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
>     property TEXT NOT NULL, token_id INTEGER REFERENCES tokens(id),
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL,
>     confidence REAL, binding_status TEXT NOT NULL DEFAULT 'unbound', ...
>     UNIQUE(node_id, property)
> );
> CREATE TABLE IF NOT EXISTS extraction_runs (
>     id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id), ...
>     status TEXT NOT NULL DEFAULT 'running', ...
> );
> CREATE TABLE IF NOT EXISTS screen_extraction_status (
>     id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES extraction_runs(id) ON DELETE CASCADE,
>     screen_id INTEGER NOT NULL REFERENCES screens(id),
>     status TEXT NOT NULL DEFAULT 'pending', ...
>     UNIQUE(run_id, screen_id)
> );
>
> -- Census views
> CREATE VIEW v_color_census AS
> SELECT ntb.resolved_value, COUNT(*) AS usage_count, COUNT(DISTINCT ntb.node_id) AS node_count,
>        GROUP_CONCAT(DISTINCT ntb.property) AS properties, s.file_id
> FROM node_token_bindings ntb JOIN nodes n ON ntb.node_id = n.id JOIN screens s ON n.screen_id = s.id
> WHERE ntb.property LIKE 'fill%' OR ntb.property LIKE 'stroke%'
> GROUP BY ntb.resolved_value, s.file_id ORDER BY usage_count DESC;
>
> CREATE VIEW v_curation_progress AS
> SELECT binding_status, COUNT(*) AS binding_count,
>        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM node_token_bindings), 1) AS pct
> FROM node_token_bindings GROUP BY binding_status;
> ```

## Task

Create `tests/test_extraction_integration.py` with integration tests that exercise the full extraction pipeline end-to-end, testing the real boundaries between modules (inventory -> screen extraction -> binding creation -> path computation -> orchestrator). Use `@pytest.mark.integration` marker on all tests. Only mock the Figma MCP calls (the `extract_fn` callback).

### Integration Test Design

These tests run the REAL pipeline functions against a REAL in-memory SQLite database. The only mock is the `extract_fn` callback that simulates the MCP call returning node data. This tests:
- FK integrity between files -> screens -> nodes -> bindings
- Data shape correctness flowing from inventory to screen extraction to bindings
- Extraction_runs and screen_extraction_status tracking
- Resume-after-failure behavior
- Census views producing correct aggregations from real pipeline output

### Test Functions

1. **`test_full_pipeline_inventory_to_bindings(db)`**:
   - Build a mock `extract_fn` that returns a realistic node list (10+ nodes with fills, text, effects, spacing).
   - Call `run_extraction_pipeline(conn, "testkey", "Test File", frames, extract_fn)`.
   - Verify:
     - `files` table has 1 row with correct file_key
     - `screens` table has correct number of rows with correct device_class
     - `nodes` table has rows for each screen (sum matches expected)
     - `node_token_bindings` table has rows (at least 1 per node with visual properties)
     - All binding_status values are 'unbound'
     - All bindings have valid node_id (FK check)
     - `extraction_runs` has 1 row with status 'completed'
     - All `screen_extraction_status` rows have status 'completed'

2. **`test_fk_integrity_across_pipeline(db)`**:
   - Run the pipeline with mock data.
   - Verify FK integrity:
     - Every `nodes.screen_id` exists in `screens.id`
     - Every `nodes.parent_id` (non-NULL) exists in `nodes.id` within the same screen
     - Every `node_token_bindings.node_id` exists in `nodes.id`
   - Use explicit SQL queries to check for orphans: `SELECT COUNT(*) FROM nodes WHERE screen_id NOT IN (SELECT id FROM screens)` should be 0.

3. **`test_paths_computed_correctly(db)`**:
   - Run the pipeline with a known tree structure (parent-child relationships).
   - Verify:
     - All nodes have non-NULL `path` values
     - Root nodes have paths matching `^\d+$`
     - Child paths start with parent path prefix
     - Path format matches `^\d+(\.\d+)*$`
   - Verify subtree query works: `SELECT * FROM nodes WHERE path LIKE '<parent_path>.%'` returns correct descendants.

4. **`test_census_views_after_extraction(db)`**:
   - Run the pipeline with nodes that have known color values (e.g., #09090B used 3 times, #FFFFFF used 2 times).
   - Query `v_color_census` and verify:
     - Returns rows with correct resolved_value and usage_count
     - Most-used color has highest usage_count
   - Query `v_curation_progress` and verify:
     - Shows 100% 'unbound' (no tokens assigned yet)
   - Query `v_spacing_census` if spacing bindings exist and verify results.

5. **`test_resume_after_failure(db)`**:
   - Build a mock `extract_fn` that succeeds for screen 1 but raises an Exception for screen 2.
   - Run `run_extraction_pipeline` -- it should complete screen 1, fail screen 2, continue with screen 3.
   - Verify:
     - `extraction_runs.status` is 'failed' (because at least 1 screen failed)
     - Screen 1 status is 'completed' with node_count > 0
     - Screen 2 status is 'failed' with error message
     - Screen 3 status is 'completed' (pipeline continued past failure)
   - Now build a new `extract_fn` that succeeds for all screens.
   - Re-run `run_inventory` (reuse existing run) and then process remaining screens.
   - Verify screen 2 is now 'completed'.

6. **`test_extraction_run_tracking(db)`**:
   - Run the pipeline.
   - Verify `extraction_runs` has correct `total_screens`, `extracted_screens`, timestamps.
   - Verify each `screen_extraction_status` has `node_count` and `binding_count` populated.

7. **`test_is_semantic_flags(db)`**:
   - Run the pipeline with known node types (TEXT, FRAME with layout, FRAME without layout, INSTANCE).
   - Verify:
     - TEXT nodes have is_semantic = 1
     - FRAME with layout_mode has is_semantic = 1
     - Unnamed FRAME ("Frame 1") without layout has is_semantic = 0
     - Named FRAME ("Header") has is_semantic = 1

8. **`test_binding_values_match_nodes(db)`**:
   - Run the pipeline.
   - For several nodes, verify that binding resolved_values match the expected normalization of the node's raw properties.
   - Example: a node with fill color {r:0.035, g:0.035, b:0.043, a:1} should have a binding with resolved_value "#09090B".

### Helper

Create a `_build_mock_frames()` function returning a list of 3 frame dicts (2 iphones + 1 component sheet). Create a `_build_mock_extract_fn(responses: dict)` function that returns a callable mapping screen_figma_node_id to a mock response list.

## Acceptance Criteria

- [ ] `pytest tests/test_extraction_integration.py -v` passes all tests
- [ ] At least 8 test functions
- [ ] All tests use `@pytest.mark.integration` marker
- [ ] Tests use real DB (in-memory SQLite), not mock DB
- [ ] Tests run actual pipeline functions, not just assert on seeded data
- [ ] FK integrity verified via explicit SQL queries
- [ ] Census views queried and verified with expected aggregations
- [ ] Resume-after-failure behavior tested end-to-end
- [ ] No mock of internal module boundaries -- only the MCP extract_fn is mocked
- [ ] `pytest tests/test_extraction_integration.py -v --tb=short` exits 0

## Notes

- Integration tests take slightly longer than unit tests because they run the full pipeline. Use `@pytest.mark.timeout(30)` as a safety net.
- The mock `extract_fn` should return different node lists for different screens to test that bindings are correctly attributed to their screens.
- The resume test is the most complex: it requires simulating a failure mid-pipeline and then restarting. The key behavior is that completed screens are not re-extracted.
- Census views may return no results if the mock data doesn't include the right property types. Make sure the mock responses include fills (for v_color_census) and spacing (for v_spacing_census).
- Import `make_mock_figma_response` from `tests.fixtures` if its shape matches what the pipeline expects, OR build a custom mock in the test file if the fixture shape differs.