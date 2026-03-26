---
taskId: TASK-015
title: "Write unit tests for extraction with mock Figma data"
wave: wave-1
testFirst: false
testLevel: unit
dependencies: [TASK-014]
produces:
  - tests/test_extraction.py
verify:
  - type: test
    command: 'pytest tests/test_extraction.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-015: Write unit tests for extraction with mock Figma data

## Spec Context

### From dd/extract_inventory.py (produced by TASK-010)

> Exports:
> - `populate_file(conn, file_key, name, ...) -> int` -- UPSERT file
> - `populate_screens(conn, file_id, frames: list[dict]) -> list[int]` -- UPSERT screens
> - `create_extraction_run(conn, file_id, agent_id) -> int` -- create run
> - `classify_screen(name, width, height, has_components, has_instances) -> str` -- classify device
> - `get_pending_screens(conn, run_id) -> list[dict]` -- get pending screens

### From dd/extract_screens.py (produced by TASK-011)

> Exports:
> - `generate_extraction_script(screen_node_id: str) -> str` -- JS for use_figma
> - `parse_extraction_response(response: list[dict]) -> list[dict]` -- clean raw response
> - `compute_is_semantic(nodes: list[dict]) -> list[dict]` -- apply semantic rules
> - `insert_nodes(conn, screen_id, nodes: list[dict]) -> list[int]` -- UPSERT nodes
> - `update_screen_status(conn, run_id, screen_id, status, ...)` -- update status

### From dd/extract_bindings.py (produced by TASK-012)

> Exports:
> - `create_bindings_for_node(node_row: dict) -> list[dict]` -- create binding dicts for one node
> - `insert_bindings(conn, node_id, bindings: list[dict]) -> int` -- insert bindings
> - `create_bindings_for_screen(conn, screen_id) -> int` -- create all bindings for a screen

### From dd/paths.py (produced by TASK-013)

> Exports:
> - `compute_paths(conn, screen_id) -> None`
> - `compute_is_semantic(conn, screen_id) -> None` (DB-level version)
> - `compute_paths_and_semantics(conn, screen_id) -> None`

### From dd/extract.py (produced by TASK-014)

> Exports:
> - `run_inventory(conn, file_key, file_name, frames, ...) -> dict`
> - `process_screen(conn, run_id, screen_id, figma_node_id, raw_response) -> dict`
> - `get_next_screen(conn, run_id) -> dict | None`
> - `get_extraction_script(screen_figma_node_id) -> str`
> - `complete_run(conn, run_id) -> dict`
> - `run_extraction_pipeline(conn, file_key, file_name, frames, extract_fn, ...) -> dict`

### Mock Figma Response Shape

> The `use_figma` call returns a list of node dicts. A typical response for a screen with 5 nodes:
> ```python
> [
>     {"figma_node_id": "100:1", "parent_idx": None, "name": "Home", "node_type": "FRAME",
>      "depth": 0, "sort_order": 0, "x": 0, "y": 0, "width": 428, "height": 926,
>      "fills": "[{\"type\":\"SOLID\",\"color\":{\"r\":0.035,\"g\":0.035,\"b\":0.043,\"a\":1}}]",
>      "layout_mode": "VERTICAL", "padding_top": 16, "padding_bottom": 16,
>      "padding_left": 16, "padding_right": 16, "item_spacing": 8},
>     {"figma_node_id": "100:2", "parent_idx": 0, "name": "Header", "node_type": "FRAME",
>      "depth": 1, "sort_order": 0, "x": 0, "y": 0, "width": 396, "height": 44,
>      "layout_mode": "HORIZONTAL", "item_spacing": 12},
>     {"figma_node_id": "100:3", "parent_idx": 1, "name": "Title", "node_type": "TEXT",
>      "depth": 2, "sort_order": 0, "x": 0, "y": 0, "width": 200, "height": 24,
>      "font_family": "Inter", "font_weight": 600, "font_size": 16,
>      "line_height": "{\"value\":24,\"unit\":\"PIXELS\"}", "text_content": "Home"},
>     {"figma_node_id": "100:4", "parent_idx": 0, "name": "Card", "node_type": "FRAME",
>      "depth": 1, "sort_order": 1, "x": 0, "y": 60, "width": 396, "height": 200,
>      "fills": "[{\"type\":\"SOLID\",\"color\":{\"r\":0.094,\"g\":0.094,\"b\":0.106,\"a\":1}}]",
>      "corner_radius": "8",
>      "effects": "[{\"type\":\"DROP_SHADOW\",\"visible\":true,\"color\":{\"r\":0,\"g\":0,\"b\":0,\"a\":0.1},\"radius\":6,\"offset\":{\"x\":0,\"y\":4},\"spread\":-1}]"},
>     {"figma_node_id": "100:5", "parent_idx": 3, "name": "Card Label", "node_type": "TEXT",
>      "depth": 2, "sort_order": 0, "x": 16, "y": 16, "width": 100, "height": 20,
>      "font_family": "Inter", "font_weight": 400, "font_size": 14,
>      "line_height": "{\"value\":20,\"unit\":\"PIXELS\"}", "text_content": "Settings"}
> ]
> ```

### From dd/db.py (produced by TASK-002)

> Exports: `init_db(db_path) -> sqlite3.Connection`

## Task

Create `tests/test_extraction.py` with comprehensive unit tests for the extraction pipeline modules. Use `@pytest.mark.unit` marker on all tests. Each test should create an in-memory DB via `init_db(":memory:")` (or use the `db` fixture from conftest).

### Test Groups

1. **Inventory tests** (at least 6 tests):
   - `test_populate_file_creates_row`: Insert a file, verify it exists in DB with correct data.
   - `test_populate_file_upsert`: Insert same file_key twice, verify only 1 row exists with updated data.
   - `test_classify_screen_iphone`: width=428, height=926 -> "iphone"
   - `test_classify_screen_component_sheet_by_name`: "Buttons and Controls" -> "component_sheet"
   - `test_classify_screen_component_sheet_by_content`: unknown dims + has_components=True -> "component_sheet"
   - `test_populate_screens_creates_rows`: Insert 3 frames, verify 3 rows in screens with correct device_class.
   - `test_create_extraction_run`: Create run, verify run row + screen_extraction_status rows exist.
   - `test_get_pending_screens`: Create run, verify pending screens returned, complete one, verify it's excluded.

2. **Screen extraction tests** (at least 5 tests):
   - `test_generate_extraction_script_format`: Verify script contains function, node ID, return statement, under 50K chars.
   - `test_parse_extraction_response_basic`: Pass the 5-node mock response, verify all nodes parsed with correct types.
   - `test_parse_extraction_response_converts_visible`: Boolean `true`/`false` -> int 1/0.
   - `test_compute_is_semantic_text_node`: TEXT nodes marked semantic.
   - `test_compute_is_semantic_named_frame`: Frame named "MyWidget" is semantic; "Frame 1" is not.
   - `test_compute_is_semantic_bottom_up`: Parent with 2+ semantic children promoted.
   - `test_insert_nodes_parent_resolution`: Insert 5-node tree, verify parent_id chain is correct.
   - `test_insert_nodes_upsert`: Insert same nodes twice, verify no duplicates.

3. **Binding tests** (at least 5 tests):
   - `test_create_bindings_for_node_with_fill`: Node with solid fill -> 1 color binding.
   - `test_create_bindings_for_node_with_effect`: Node with DROP_SHADOW -> 5 effect bindings.
   - `test_create_bindings_for_node_text`: TEXT node -> typography bindings (fontSize, fontFamily, etc.).
   - `test_create_bindings_for_node_spacing`: Node with padding and itemSpacing -> spacing bindings.
   - `test_create_bindings_for_node_empty`: Node with no visual properties -> 0 bindings.
   - `test_insert_bindings_preserves_bound`: Insert binding, mark as 'bound', re-insert -> bound binding preserved.

4. **Path computation tests** (at least 4 tests):
   - `test_compute_paths_root_node`: Single root gets path "0".
   - `test_compute_paths_tree`: 5-node tree gets correct hierarchical paths.
   - `test_compute_is_semantic_db`: Verify DB-level is_semantic computation matches expectations.
   - `test_compute_paths_and_semantics`: Convenience function runs both.

5. **Orchestrator tests** (at least 4 tests):
   - `test_run_inventory`: Full inventory setup returns correct dict.
   - `test_process_screen`: Process a mock response, verify nodes + bindings + paths in DB.
   - `test_resume_support`: Create run, complete 1 screen, call get_next_screen, verify it returns the next uncompleted screen.
   - `test_complete_run_all_completed`: All screens completed -> run status "completed".
   - `test_complete_run_with_failures`: Some screens failed -> run status "failed".

### Helper function

Create a `_make_mock_response(node_count=5)` helper inside the test file that returns the mock response shape from the Spec Context above. Use this across multiple tests.

## Acceptance Criteria

- [ ] `pytest tests/test_extraction.py -v` passes all tests
- [ ] At least 24 test functions total across the 5 groups
- [ ] All tests use `@pytest.mark.unit` marker
- [ ] Tests use in-memory SQLite DB (no file I/O)
- [ ] All assertions are specific (exact values, counts, statuses -- not just "doesn't crash")
- [ ] `test_insert_bindings_preserves_bound` verifies re-extraction safety
- [ ] `test_resume_support` verifies skip-completed behavior
- [ ] Mock Figma response includes at least: fills, effects, typography, spacing, corner_radius
- [ ] `pytest tests/test_extraction.py -v --tb=short` exits 0

## Notes

- These are unit tests. Each test creates its own DB or uses the `db` fixture. No cross-test state.
- The mock response helper should be reusable across tests but defined in the test file (not imported from fixtures.py which has a different data shape).
- For `test_process_screen`, you need to first set up the inventory (file + screens + run) before calling process_screen, since it depends on screen_id and run_id existing.
- The binding preservation test is critical -- it validates NFR-8 (non-destructive re-extraction).