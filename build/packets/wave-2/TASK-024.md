---
taskId: TASK-024
title: "Integrate component extraction into main pipeline"
wave: wave-2
testFirst: false
testLevel: unit
dependencies: [TASK-014, TASK-020]
produces:
  - dd/extract.py
verify:
  - type: typecheck
    command: 'python -c "from dd.extract import run_component_extraction, run_extraction_pipeline"'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-024: Integrate component extraction into main pipeline

## Spec Context

### From Technical Design Spec -- Phase 4: Component Extraction

> **Tool:** Official MCP `use_figma` targeting component frames.
> **Runs after screen extraction, targeting the "Buttons and Controls" frame and any detected component sets.**

### From Technical Design Spec -- Pipeline Phases Overview

> Phase 1: File Inventory -> Phase 2: Screen Extraction -> Phase 3: Normalization + Bindings -> Phase 4: Component Extraction

### From Technical Design Spec -- MCP Tool Usage Map

> | Phase | Tool | MCP | Cost | Calls |
> |---|---|---|---|---|
> | 4. Component extraction | `use_figma` | Official | Metered | ~5-10 |

### From schema.sql -- screens table (device_class for component sheets)

> ```sql
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
> ```

### From schema.sql -- components table

> ```sql
> CREATE TABLE IF NOT EXISTS components (
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
> ```

### From schema.sql -- nodes table (for component references)

> ```sql
> CREATE TABLE IF NOT EXISTS nodes (
>     ...
>     component_id    INTEGER REFERENCES components(id),
>     ...
> );
> ```

### From dd/extract.py (produced by TASK-014)

> Exports:
> - `run_inventory(conn, file_key, file_name, frames, ...) -> dict`
> - `process_screen(conn, run_id, screen_id, figma_node_id, raw_response) -> dict`
> - `get_next_screen(conn, run_id) -> dict | None`
> - `get_extraction_script(screen_figma_node_id) -> str`
> - `complete_run(conn, run_id) -> dict`
> - `run_extraction_pipeline(conn, file_key, file_name, frames, extract_fn, ...) -> dict`

### From dd/extract_components.py (produced by TASK-020, TASK-021, TASK-022, TASK-023)

> Exports:
> - `extract_components(conn, file_id, component_nodes) -> list[int]`
> - `parse_component_set(component_set_data) -> dict`
> - `parse_standalone_component(component_data) -> dict`
> - `populate_variant_dimension_values(conn, component_id) -> int`
> - `infer_slots(children) -> list[dict]`
> - `insert_slots(conn, component_id, slots) -> list[int]`
> - `infer_a11y(category, name) -> dict`
> - `insert_a11y(conn, component_id, a11y_data) -> int`

### From dd/extract_inventory.py (produced by TASK-010)

> The `classify_screen` function tags frames as `device_class = "component_sheet"` when they match component sheet heuristics.

## Task

Update `dd/extract.py` to integrate component extraction into the main pipeline. After screen extraction completes, the pipeline should identify component_sheet screens and extract component definitions from them.

1. **`get_component_sheets(conn, file_id: int) -> list[dict]`**:
   - Query `screens` where `file_id = ?` AND `device_class = 'component_sheet'`.
   - Return list of dicts with keys: `screen_id`, `figma_node_id`, `name`.

2. **`generate_component_extraction_script(screen_node_id: str) -> str`**:
   - Generate a JavaScript string for `use_figma` that traverses a component_sheet frame and returns all COMPONENT and COMPONENT_SET nodes with their children.
   - The script should:
     - Get the node by ID.
     - Walk its children looking for nodes with type COMPONENT or COMPONENT_SET.
     - For COMPONENT_SET nodes: collect the set's id, name, description, and its children (individual COMPONENT variants) with their ids, names, and direct children (for slot inference).
     - For standalone COMPONENT nodes: collect id, name, description, and direct children.
     - Return an array of component/component_set dicts.
   - The script must be under 50,000 characters.

3. **`parse_component_extraction_response(response: list[dict]) -> list[dict]`**:
   - Accept the raw response from `use_figma` component extraction.
   - Validate and normalize the data.
   - Return a list of component dicts ready for `extract_components`.

4. **`run_component_extraction(conn, file_id: int, component_data: list[dict]) -> dict`**:
   - Accept pre-fetched component data (from MCP call).
   - Call `extract_components(conn, file_id, component_data)` to insert all components.
   - After insertion, link INSTANCE nodes to their components:
     - Query `nodes` where `node_type = 'INSTANCE'` and the node has a `component_figma_id` (stored during screen extraction in a column or extracted from the node's raw data).
     - For each INSTANCE node, look up the component by `figma_node_id` in the `components` table.
     - UPDATE `nodes SET component_id = ? WHERE id = ?` for matching instances.
   - Return a summary dict: `{"component_count": int, "variant_count": int, "instances_linked": int}`.

5. **Update `run_extraction_pipeline`**:
   - After the screen extraction loop and `complete_run`, add a component extraction phase:
     - Get component sheets via `get_component_sheets`.
     - For each component sheet, the caller provides component data via the `extract_fn` callback (or a separate `component_extract_fn` parameter).
     - Call `run_component_extraction` with the fetched data.
   - Add a new optional parameter `component_extract_fn: callable | None = None` to `run_extraction_pipeline`. If provided, it's called for each component sheet's figma_node_id and should return the component data.
   - If `component_extract_fn` is None, skip component extraction (backward compatible).
   - Print progress: `"Extracting components from {sheet_name}..."`.

6. **Handle INSTANCE node linking**:
   - During screen extraction (TASK-011), the JS script captures `component_figma_id` for INSTANCE nodes.
   - The `parse_extraction_response` function in TASK-011 stores this as part of the node data.
   - In `insert_nodes` (TASK-011), this field may not have been stored in the DB since `nodes.component_id` requires a component row to exist (FK).
   - Strategy: Store the raw `component_figma_id` temporarily (e.g., in a separate tracking dict or by inserting it as a non-FK text field). In `run_component_extraction`, resolve these to actual component_id values.
   - Simplest approach: After `extract_components` populates the components table, do a UPDATE JOIN: `UPDATE nodes SET component_id = (SELECT c.id FROM components c WHERE c.figma_node_id = ? AND c.file_id = ?) WHERE nodes.node_type = 'INSTANCE'`. Use the `figma_node_id` match.
   - Since nodes don't store `component_figma_id` directly in a DB column, re-scan node data or use a separate approach. **Practical solution**: During `insert_nodes`, store the `component_figma_id` in an in-memory map (not in DB). Pass this map to `run_component_extraction`. Or: query the extraction response data again.
   - **Recommended approach**: Add a new small function `link_instances_to_components(conn, file_id: int)` that queries nodes + screens for INSTANCE nodes and tries to match them to components via naming conventions or a stored mapping. For now, this can be a best-effort operation that logs unresolved instances.

## Acceptance Criteria

- [ ] `python -c "from dd.extract import run_component_extraction, get_component_sheets, generate_component_extraction_script"` exits 0
- [ ] `get_component_sheets` returns only screens with `device_class = 'component_sheet'`
- [ ] `generate_component_extraction_script` returns a JS string under 50K chars that finds COMPONENT/COMPONENT_SET nodes
- [ ] `run_component_extraction` inserts components and returns a summary dict with component_count
- [ ] `run_extraction_pipeline` with `component_extract_fn` provided calls component extraction after screen extraction
- [ ] `run_extraction_pipeline` without `component_extract_fn` skips component extraction (backward compatible)
- [ ] Component extraction creates rows in `components`, `component_variants`, `variant_axes`, `variant_dimension_values`, `component_slots`, and `component_a11y` tables
- [ ] INSTANCE nodes in screens are linked to their component via `nodes.component_id` when possible

## Notes

- This task integrates TASK-020/021/022/023 into the main pipeline. The component extraction functions from those tasks do the heavy lifting; this task provides the orchestration.
- The INSTANCE-to-component linking is best-effort. Some INSTANCE nodes may reference components not in any component_sheet (e.g., local components defined inline). These will have `component_id = NULL`.
- The `component_extract_fn` callback follows the same pattern as `extract_fn`: the agent provides it, wrapping the MCP call. The builder writes the function signatures; the agent provides the implementations.
- The generated JS script for component extraction is different from the screen extraction script. It specifically looks for COMPONENT and COMPONENT_SET types rather than traversing all visual properties.