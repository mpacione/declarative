---
taskId: TASK-020
title: "Implement component extraction (Phase 4)"
wave: wave-2
testFirst: false
testLevel: unit
dependencies: [TASK-002, TASK-003]
produces:
  - dd/extract_components.py
verify:
  - type: typecheck
    command: 'python -c "from dd.extract_components import extract_components, parse_component_set, insert_component, insert_variants, insert_variant_axes"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.extract_components import parse_component_set; result = parse_component_set({\"id\": \"1:1\", \"name\": \"button\", \"type\": \"COMPONENT_SET\", \"children\": [{\"id\": \"1:2\", \"name\": \"size=large, style=solid\", \"type\": \"COMPONENT\", \"width\": 200, \"height\": 48}]}); print(result); assert result[\"name\"] == \"button\""'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-020: Implement component extraction (Phase 4)

## Spec Context

### From Technical Design Spec -- Phase 4: Component Extraction

> **Tool:** Official MCP `use_figma` targeting component frames.
> **Runs after screen extraction, targeting the "Buttons and Controls" frame and any detected component sets.**
>
> For each component/component set:
> 1. Extract name, variant properties (axes like size, style, state).
> 2. Extract each variant's node ID and property combination.
> 3. Generate a structured `composition_hint` -- an ordered list of slots with defaults, layout direction, spacing token, padding tokens.
> 4. Populate `variant_axes` table: normalize the JSON variant properties into structured rows. Flag axes where all values match known interaction states (default, hover, focus, pressed, disabled, selected, loading) as `is_interaction = 1`.
> 5. Populate `variant_dimension_values`: link each variant to its position on each axis.
> 6. Populate `component_slots`: analyze the component's direct children to identify named insertion points.
> 7. Populate `component_a11y`: infer role from component category and name.
> 8. Populate `component_responsive`: analyze variant axes for breakpoint-related properties.
>
> Stored in `components`, `component_variants`, `variant_axes`, `variant_dimension_values`, `component_slots`, `component_a11y`, and `component_responsive` tables.

### From Technical Design Spec -- Component sheet detection heuristics

> **Component sheet detection heuristics** (frames that are NOT screens):
> 1. Name contains "Buttons", "Controls", "Components", "Modals", "Popups", "Icons", "Website", or "Assets" (case-insensitive).
> 2. Dimensions don't match any known device class AND frame contains component definitions (node type = COMPONENT or COMPONENT_SET).
> 3. Frame contains no INSTANCE nodes (it's a definition sheet, not a composed screen).
>
> Frames matching any heuristic are tagged `device_class = component_sheet`.

### From User Requirements Spec -- FR-3.6: Interaction States

> FR-3.6.1: Variant axes marked `is_interaction = 1` represent interaction states (hover, focus, disabled, pressed, selected, loading).
> FR-3.6.2: Interaction state variants are queryable across all components via `v_interaction_states` view.
> FR-3.6.3: Each variant dimension value links a specific variant to its position on each axis.
> FR-3.6.4: Default values are recorded per axis -- the baseline variant an agent should use when no state is specified.

### From schema.sql -- Component Tables

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
>
> CREATE TABLE IF NOT EXISTS component_variants (
>     id              INTEGER PRIMARY KEY,
>     component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     figma_node_id   TEXT NOT NULL,
>     name            TEXT NOT NULL,
>     properties      TEXT NOT NULL,
>     UNIQUE(component_id, figma_node_id)
> );
>
> CREATE TABLE IF NOT EXISTS variant_axes (
>     id              INTEGER PRIMARY KEY,
>     component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
>     axis_name       TEXT NOT NULL,
>     axis_values     TEXT NOT NULL,
>     is_interaction  INTEGER NOT NULL DEFAULT 0,
>     default_value   TEXT,
>     UNIQUE(component_id, axis_name)
> );
> ```

### From dd/types.py (produced by TASK-003)

> Exports:
> - `DeviceClass` enum with COMPONENT_SHEET
> - `is_component_sheet_name(name: str) -> bool`
> - `COMPONENT_SHEET_KEYWORDS: list[str]`

### From dd/db.py (produced by TASK-002)

> Exports:
> - `get_connection(db_path: str) -> sqlite3.Connection`
> - `init_db(db_path: str) -> sqlite3.Connection`

## Task

Create `dd/extract_components.py` implementing the core component extraction logic from Phase 4. This module parses component/component_set data that an agent has fetched via MCP, structures it, and writes to the DB. It does NOT call MCP directly.

1. **`INTERACTION_STATE_VALUES: frozenset[str]`**:
   - Define: `frozenset({"default", "hover", "focus", "pressed", "disabled", "selected", "loading"})`
   - Used to detect interaction axes.

2. **`CATEGORY_KEYWORDS: dict[str, list[str]]`**:
   - Map component category to name keywords for auto-categorization:
     ```python
     {"button": ["button", "btn"], "input": ["input", "text field", "textfield", "search"],
      "nav": ["nav", "tab", "menu", "sidebar"], "card": ["card"],
      "modal": ["modal", "dialog", "popup", "popover", "sheet"],
      "icon": ["icon"], "layout": ["layout", "container", "stack"],
      "chrome": ["status bar", "home indicator", "chrome"]}
     ```

3. **`infer_category(name: str) -> str | None`**:
   - Check component name (lowercased) against CATEGORY_KEYWORDS.
   - Return the first matching category, or None if no match.

4. **`parse_variant_properties(variant_name: str) -> dict[str, str]`**:
   - Parse a Figma variant name like `"size=large, style=solid, state=default"` into `{"size": "large", "style": "solid", "state": "default"}`.
   - Split on `, ` (comma-space), then split each part on `=`.
   - Handle edge cases: extra whitespace, missing `=` (skip that part).

5. **`detect_interaction_axis(axis_name: str, axis_values: list[str]) -> bool`**:
   - Return True if the axis_name is "state" (case-insensitive) OR if ALL values in axis_values are members of INTERACTION_STATE_VALUES (case-insensitive comparison).
   - This flags axes like state=[default, hover, focus, pressed, disabled].

6. **`parse_component_set(component_set_data: dict) -> dict`**:
   - Accept a dict representing a COMPONENT_SET node from Figma with keys: `id`, `name`, `type`, `children` (list of COMPONENT nodes), optionally `description`.
   - Extract the component set's name and figma_node_id.
   - For each child COMPONENT: parse its variant name via `parse_variant_properties`, store its figma_node_id and properties.
   - Collect all unique axes: for each parsed variant, collect the set of keys. For each axis, collect all observed values across variants.
   - Determine `default_value` per axis: the most common value, or the one labeled "default" if it exists.
   - Infer category via `infer_category(name)`.
   - Return a structured dict:
     ```python
     {"figma_node_id": str, "name": str, "description": str | None,
      "category": str | None,
      "variant_properties": json_str_of_axis_names,
      "variants": [{"figma_node_id": str, "name": str, "properties": dict}],
      "axes": [{"axis_name": str, "axis_values": list[str], "is_interaction": bool, "default_value": str | None}]}
     ```

7. **`parse_standalone_component(component_data: dict) -> dict`**:
   - Accept a dict for a standalone COMPONENT (not part of a COMPONENT_SET).
   - No variant properties, no axes.
   - Return: `{"figma_node_id": str, "name": str, "description": str | None, "category": str | None, "variant_properties": None, "variants": [], "axes": []}`.

8. **`insert_component(conn, file_id: int, component_data: dict) -> int`**:
   - UPSERT into `components` table: `INSERT INTO components (file_id, figma_node_id, name, description, category, variant_properties) VALUES (...) ON CONFLICT(file_id, figma_node_id) DO UPDATE SET name=excluded.name, description=excluded.description, category=excluded.category, variant_properties=excluded.variant_properties, extracted_at=strftime(...)`.
   - Return the component id.

9. **`insert_variants(conn, component_id: int, variants: list[dict]) -> list[int]`**:
   - For each variant, UPSERT into `component_variants`: `INSERT ... ON CONFLICT(component_id, figma_node_id) DO UPDATE SET name=excluded.name, properties=excluded.properties`.
   - `properties` is JSON-serialized dict.
   - Return list of variant IDs.

10. **`insert_variant_axes(conn, component_id: int, axes: list[dict]) -> list[int]`**:
    - For each axis, UPSERT into `variant_axes`: `INSERT ... ON CONFLICT(component_id, axis_name) DO UPDATE SET axis_values=excluded.axis_values, is_interaction=excluded.is_interaction, default_value=excluded.default_value`.
    - `axis_values` is a JSON-serialized list of strings.
    - Return list of axis IDs.

11. **`extract_components(conn, file_id: int, component_nodes: list[dict]) -> list[int]`**:
    - High-level function that processes a list of raw component/component_set nodes from Figma.
    - For each node: if `type == "COMPONENT_SET"`, call `parse_component_set`; if `type == "COMPONENT"` (standalone), call `parse_standalone_component`.
    - Call `insert_component`, `insert_variants`, `insert_variant_axes` for each.
    - Return list of component IDs inserted.
    - Commit after all inserts.

## Acceptance Criteria

- [ ] `python -c "from dd.extract_components import extract_components, parse_component_set, parse_standalone_component, insert_component, insert_variants, insert_variant_axes, parse_variant_properties, detect_interaction_axis, infer_category"` exits 0
- [ ] `parse_variant_properties("size=large, style=solid, state=default")` returns `{"size": "large", "style": "solid", "state": "default"}`
- [ ] `parse_variant_properties("size=large")` returns `{"size": "large"}`
- [ ] `detect_interaction_axis("state", ["default", "hover", "focus"])` returns True
- [ ] `detect_interaction_axis("size", ["small", "medium", "large"])` returns False
- [ ] `infer_category("button/large")` returns "button"
- [ ] `infer_category("SomeRandomName")` returns None
- [ ] `parse_component_set` with a component set containing 3 variants returns correct axes and variant list
- [ ] `parse_standalone_component` returns empty variants and axes lists
- [ ] `insert_component` inserts a row and returns an integer ID
- [ ] `insert_component` with same file_id + figma_node_id twice is idempotent (UPSERT)
- [ ] `insert_variants` inserts variant rows linked to component_id
- [ ] `insert_variant_axes` inserts axis rows with correct is_interaction flag
- [ ] `extract_components` processes a mix of COMPONENT_SET and standalone COMPONENT nodes

## Notes

- This module processes data already fetched from Figma. The calling agent fetches component frame data via MCP and passes the parsed node list to `extract_components`.
- The `composition_hint` field in `components` will be populated by TASK-022 (slot inference). For now, `insert_component` should set it to None.
- Variant name parsing follows Figma's convention: `"axis1=value1, axis2=value2"`. This is consistent across all Figma component sets.
- The `variant_dimension_values` table is populated by TASK-021, not this task. This task only handles `components`, `component_variants`, and `variant_axes`.