---
taskId: TASK-026
title: "Write integration tests for component + extraction pipeline"
wave: wave-2
testFirst: false
testLevel: integration
dependencies: [TASK-007, TASK-024]
produces:
  - tests/test_components_integration.py
verify:
  - type: test
    command: 'pytest tests/test_components_integration.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-026: Write integration tests for component + extraction pipeline

## Spec Context

### From Task Decomposition Guide -- Testing Strategy

> **Integration tests** (wave 1+): Test cross-module boundaries using fixture DBs with real pipeline output. No mocks at the seam being tested -- only external dependencies (Figma MCP) are mocked. These catch: schema mismatches between producer/consumer, FK violations, incorrect data shapes flowing across module boundaries.

### From Task Decomposition Guide -- Wave 2 Test Description

> TASK-026: Write integration tests for component + extraction pipeline -- seed fixture DB with extraction output from TASK-007 fixtures; run component extraction; verify components reference valid nodes, variant_dimension_values FK integrity, component_slots populated from real node children, a11y defaults applied; verify orchestrator chains extraction + components end-to-end.

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `seed_post_extraction(db) -> sqlite3.Connection` -- inserts files (id=1), screens (3 screens: Home, Settings, Buttons and Controls), nodes (10 nodes), bindings (15 bindings), extraction_run
> - `make_mock_figma_response(screen_name: str, node_count: int = 10) -> list[dict]`
>
> Screen 3 in seed_post_extraction is: (id=3, file_id=1, figma_node_id="100:3", name="Buttons and Controls", width=1200, height=800, device_class="component_sheet", node_count=5)
> Screen 3 has 2 nodes: (1 root FRAME, 1 COMPONENT)

### From tests/conftest.py (produced by TASK-007)

> Provides:
> - `db` fixture: in-memory SQLite connection with full schema
> - `db_with_file` fixture: db + one file row

### From dd/extract.py (produced by TASK-014, updated by TASK-024)

> Exports:
> - `run_inventory(conn, file_key, file_name, frames, ...) -> dict`
> - `process_screen(conn, run_id, screen_id, figma_node_id, raw_response) -> dict`
> - `run_extraction_pipeline(conn, ..., component_extract_fn=None) -> dict`
> - `run_component_extraction(conn, file_id, component_data) -> dict`
> - `get_component_sheets(conn, file_id) -> list[dict]`

### From dd/extract_components.py (produced by TASK-020 through TASK-023)

> Exports:
> - `extract_components(conn, file_id, component_nodes) -> list[int]`
> - `populate_variant_dimension_values(conn, component_id) -> int`
> - `infer_slots(children) -> list[dict]`
> - `insert_slots(conn, component_id, slots) -> list[int]`
> - `infer_a11y(category, name) -> dict`
> - `insert_a11y(conn, component_id, a11y_data) -> int`

### From schema.sql -- Key tables and views

> ```sql
> CREATE TABLE IF NOT EXISTS components (
>     id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id),
>     figma_node_id TEXT NOT NULL, name TEXT NOT NULL, description TEXT,
>     category TEXT, variant_properties TEXT, composition_hint TEXT,
>     extracted_at TEXT, UNIQUE(file_id, figma_node_id)
> );
>
> CREATE TABLE IF NOT EXISTS component_variants (
>     id INTEGER PRIMARY KEY, component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     figma_node_id TEXT NOT NULL, name TEXT NOT NULL, properties TEXT NOT NULL,
>     UNIQUE(component_id, figma_node_id)
> );
>
> CREATE TABLE IF NOT EXISTS variant_axes (
>     id INTEGER PRIMARY KEY, component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     axis_name TEXT NOT NULL, axis_values TEXT NOT NULL,
>     is_interaction INTEGER NOT NULL DEFAULT 0, default_value TEXT,
>     UNIQUE(component_id, axis_name)
> );
>
> CREATE TABLE IF NOT EXISTS variant_dimension_values (
>     id INTEGER PRIMARY KEY, variant_id INTEGER NOT NULL REFERENCES component_variants(id) ON DELETE CASCADE,
>     axis_id INTEGER NOT NULL REFERENCES variant_axes(id) ON DELETE CASCADE,
>     value TEXT NOT NULL, UNIQUE(variant_id, axis_id)
> );
>
> CREATE TABLE IF NOT EXISTS component_slots (
>     id INTEGER PRIMARY KEY, component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     name TEXT NOT NULL, slot_type TEXT, is_required INTEGER NOT NULL DEFAULT 0,
>     default_content TEXT, sort_order INTEGER NOT NULL DEFAULT 0, description TEXT,
>     UNIQUE(component_id, name)
> );
>
> CREATE TABLE IF NOT EXISTS component_a11y (
>     id INTEGER PRIMARY KEY, component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     role TEXT, required_label INTEGER NOT NULL DEFAULT 0, focus_order INTEGER,
>     min_touch_target REAL, keyboard_shortcut TEXT, aria_properties TEXT, notes TEXT,
>     UNIQUE(component_id)
> );
>
> CREATE TABLE IF NOT EXISTS nodes (
>     ... component_id INTEGER REFERENCES components(id), ...
> );
>
> -- Views
> CREATE VIEW v_component_catalog AS
> SELECT c.id, c.name, c.category, c.description, c.composition_hint,
>     COUNT(DISTINCT cv.id) AS variant_count, COUNT(DISTINCT cs.id) AS slot_count,
>     ca.role AS a11y_role, ca.min_touch_target,
>     GROUP_CONCAT(DISTINCT va.axis_name) AS axes
> FROM components c
> LEFT JOIN component_variants cv ON cv.component_id = c.id
> LEFT JOIN component_slots cs ON cs.component_id = c.id
> LEFT JOIN component_a11y ca ON ca.component_id = c.id
> LEFT JOIN variant_axes va ON va.component_id = c.id
> GROUP BY c.id ORDER BY c.category, c.name;
>
> CREATE VIEW v_interaction_states AS
> SELECT c.name AS component_name, c.category, va.axis_name, va.axis_values,
>     va.default_value, COUNT(DISTINCT cv.id) AS variant_count
> FROM variant_axes va
> JOIN components c ON va.component_id = c.id
> LEFT JOIN variant_dimension_values vdv ON vdv.axis_id = va.id
> LEFT JOIN component_variants cv ON vdv.variant_id = cv.id
> WHERE va.is_interaction = 1
> GROUP BY va.id ORDER BY c.name, va.axis_name;
> ```

## Task

Create `tests/test_components_integration.py` with integration tests that exercise the component extraction pipeline against real extraction output. Use `@pytest.mark.integration` marker on all tests. Only mock the Figma MCP calls.

### Integration Test Design

These tests verify the boundary between the extraction pipeline (Wave 1) and the component extraction pipeline (Wave 2). They use `seed_post_extraction` from the fixtures to set up realistic extraction output, then run component extraction on top of it. This catches FK violations, data shape mismatches, and ensures the full component model is correctly populated from extraction output.

### Test Functions

1. **`test_component_extraction_on_extraction_output(db)`**:
   - Call `seed_post_extraction(db)` to set up extraction output.
   - Build mock component data matching what `use_figma` would return for the "Buttons and Controls" component sheet:
     ```python
     component_data = [
         {"id": "500:1", "name": "button", "type": "COMPONENT_SET",
          "children": [
              {"id": "500:2", "name": "size=large, style=solid, state=default",
               "type": "COMPONENT", "width": 200, "height": 48,
               "children": [
                   {"name": "Icon", "node_type": "INSTANCE", "sort_order": 0},
                   {"name": "Label", "node_type": "TEXT", "sort_order": 1, "text_content": "Submit"}
               ]},
              {"id": "500:3", "name": "size=large, style=solid, state=hover",
               "type": "COMPONENT", "width": 200, "height": 48, "children": []},
              {"id": "500:4", "name": "size=small, style=solid, state=default",
               "type": "COMPONENT", "width": 120, "height": 36, "children": []}
          ]},
         {"id": "600:1", "name": "nav/tabs", "type": "COMPONENT"}
     ]
     ```
   - Call `extract_components(db, file_id=1, component_nodes=component_data)`.
   - Verify:
     - `components` table has 2 rows (button + nav/tabs)
     - `component_variants` has 3 rows (for the button COMPONENT_SET)
     - `variant_axes` has 3 rows (size, style, state)
     - All component `file_id` values reference the existing file in `files` table

2. **`test_variant_dimension_values_fk_integrity(db)`**:
   - Seed extraction + run component extraction.
   - Query `variant_dimension_values`:
     - Every `variant_id` must exist in `component_variants.id`
     - Every `axis_id` must exist in `variant_axes.id`
   - Verify with explicit SQL: `SELECT COUNT(*) FROM variant_dimension_values WHERE variant_id NOT IN (SELECT id FROM component_variants)` should be 0.
   - Verify correct count: 3 variants * 3 axes = 9 dimension values.

3. **`test_interaction_states_view(db)`**:
   - Seed extraction + run component extraction.
   - Query `v_interaction_states`.
   - Verify:
     - At least 1 row for the "state" axis of the button component
     - `is_interaction = 1` for the state axis
     - Default value is "default"

4. **`test_component_slots_populated(db)`**:
   - Seed extraction + run component extraction with children data for the default variant.
   - Query `component_slots` for the button component.
   - Verify:
     - At least 2 slots (Icon + Label) if children were provided
     - Slot types are correct ("icon" for Icon, "text" for Label)
     - `component_id` FK is valid
     - Sort order preserved

5. **`test_a11y_defaults_applied(db)`**:
   - Seed extraction + run component extraction.
   - Query `component_a11y` for each component.
   - Verify:
     - Button component: role="button", required_label=1, min_touch_target=44.0
     - Nav component: role="navigation", min_touch_target=44.0
     - Every component in `components` table has a matching row in `component_a11y`

6. **`test_component_catalog_view(db)`**:
   - Seed extraction + run component extraction.
   - Query `v_component_catalog`.
   - Verify:
     - Returns rows with correct variant_count, slot_count, a11y_role
     - Button component has variant_count=3, a11y_role="button"
     - Nav/tabs has variant_count=0 (standalone), a11y_role="navigation"

7. **`test_orchestrator_chains_extraction_and_components(db)`**:
   - Build mock frames and extract_fn for screen extraction.
   - Build mock component_extract_fn for component extraction.
   - Call `run_extraction_pipeline(db, ..., component_extract_fn=component_extract_fn)`.
   - Verify the full chain:
     - `files`, `screens`, `nodes`, `node_token_bindings` populated (from screen extraction)
     - `components`, `component_variants`, `variant_axes` populated (from component extraction)
     - Component sheets identified and processed
     - `extraction_runs.status` is "completed"

8. **`test_no_orphan_component_records(db)`**:
   - Seed extraction + run component extraction.
   - Verify no orphans:
     - Every `component_variants.component_id` exists in `components.id`
     - Every `variant_axes.component_id` exists in `components.id`
     - Every `component_slots.component_id` exists in `components.id`
     - Every `component_a11y.component_id` exists in `components.id`
   - Use SQL: `SELECT COUNT(*) FROM component_variants WHERE component_id NOT IN (SELECT id FROM components)` should be 0 for each table.

### Helper Functions

Create helper functions within the test file:
- `_make_component_data()` -> list of component dicts (COMPONENT_SET + standalone)
- `_make_mock_frames()` -> list of frame dicts for inventory (2 iPhones + 1 component_sheet)
- `_make_screen_extract_fn()` -> callable returning mock node data per screen

## Acceptance Criteria

- [ ] `pytest tests/test_components_integration.py -v` passes all tests
- [ ] At least 8 test functions
- [ ] All tests use `@pytest.mark.integration` marker
- [ ] Tests use real DB (in-memory SQLite), not mock DB
- [ ] Tests start from `seed_post_extraction` fixture output (real Wave 1 data)
- [ ] FK integrity verified via explicit SQL queries for all component tables
- [ ] `v_component_catalog` and `v_interaction_states` views queried and verified
- [ ] Component slots and a11y defaults verified from real component extraction
- [ ] Orchestrator end-to-end test chains screen extraction + component extraction
- [ ] No orphan records across any component-related table
- [ ] `pytest tests/test_components_integration.py -v --tb=short` exits 0

## Notes

- Integration tests take longer than unit tests. Use `@pytest.mark.timeout(30)` as a safety net.
- Import `seed_post_extraction` from `tests.fixtures` to set up the base extraction state.
- The mock component data should be richer than unit test mocks -- include multiple component types, multiple variants, children for slot inference.
- The orchestrator test (test 7) is the most comprehensive -- it runs both screen extraction and component extraction through the real `run_extraction_pipeline` function. This requires both `extract_fn` and `component_extract_fn` mocks.
- For the INSTANCE-to-component linking test, you may need to include INSTANCE nodes in the mock screen extraction data that reference the component's figma_node_id.