---
taskId: TASK-022
title: "Implement component slot inference"
wave: wave-2
testFirst: false
testLevel: unit
dependencies: [TASK-020]
produces:
  - dd/extract_components.py
verify:
  - type: typecheck
    command: 'python -c "from dd.extract_components import infer_slots, insert_slots"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.extract_components import infer_slots; slots = infer_slots([{\"name\": \"Icon\", \"node_type\": \"INSTANCE\", \"sort_order\": 0}, {\"name\": \"Label\", \"node_type\": \"TEXT\", \"sort_order\": 1}]); print(slots); assert len(slots) == 2"'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-022: Implement component slot inference

## Spec Context

### From Technical Design Spec -- Phase 4: Component Extraction

> 6. Populate `component_slots`: analyze the component's direct children to identify named insertion points. A child is a slot if it's a distinct semantic element (not a spacer/divider/background fill).

### From User Requirements Spec -- FR-3.7: Component Model

> FR-3.7.1: Component slots (`component_slots`) define named insertion points with type constraints (icon, text, component, image, any), required/optional flag, default content, and sort order.
> FR-3.7.5: All component model data is extractable where Figma metadata allows (variant properties, instance dimensions) and manually augmentable during curation (slots, a11y, responsive).

### From Technical Design Spec -- Open Design Decisions

> 5. **Component slot inference quality:** Slot detection from component child structure is heuristic. May need manual curation for complex components.

### From schema.sql -- component_slots table

> ```sql
> CREATE TABLE IF NOT EXISTS component_slots (
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
> CREATE INDEX idx_component_slots_component ON component_slots(component_id);
> ```

### From schema.sql -- nodes table (for child data)

> ```sql
> CREATE TABLE IF NOT EXISTS nodes (
>     id              INTEGER PRIMARY KEY,
>     screen_id       INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
>     figma_node_id   TEXT NOT NULL,
>     parent_id       INTEGER REFERENCES nodes(id),
>     name            TEXT NOT NULL,
>     node_type       TEXT NOT NULL,
>     sort_order      INTEGER NOT NULL DEFAULT 0,
>     is_semantic     INTEGER NOT NULL DEFAULT 0,
>     component_id    INTEGER REFERENCES components(id),
>     width           REAL,
>     height          REAL,
>     ...
> );
> ```

### From dd/extract_components.py (produced by TASK-020)

> Exports:
> - `extract_components(conn, file_id, component_nodes) -> list[int]`
> - `insert_component(conn, file_id, component_data) -> int`
> - `infer_category(name) -> str | None`

## Task

Extend `dd/extract_components.py` by adding slot inference and insertion functions. Slots represent named insertion points in a component (e.g., "leading_icon", "label", "trailing_action") that agents use to understand how to compose with the component.

1. **`NON_SLOT_HEURISTICS: set[str]`**:
   - Define names/patterns that indicate non-slot children (structural noise):
     ```python
     NON_SLOT_HEURISTICS = {"background", "bg", "divider", "separator", "spacer", "line", "border", "overlay", "shadow"}
     ```

2. **`infer_slot_type(child: dict) -> str`**:
   - Accept a dict with `node_type` and optionally `name` keys.
   - Return a slot type based on the child's node_type:
     - `"TEXT"` node_type -> `"text"`
     - `"INSTANCE"` node_type -> if name contains "icon" (case-insensitive) -> `"icon"`, else -> `"component"`
     - `"VECTOR"` or `"ELLIPSE"` -> `"icon"`
     - `"RECTANGLE"` with name containing "image" or "photo" or "avatar" (case-insensitive) -> `"image"`
     - Everything else -> `"any"`

3. **`infer_slots(children: list[dict]) -> list[dict]`**:
   - Accept a list of dicts representing the direct children of a component's default variant.
   - Each dict has keys: `name` (str), `node_type` (str), `sort_order` (int), optionally `text_content` (str), `width` (float), `height` (float).
   - Filter out non-slot children: skip any child whose lowercased name matches a value in NON_SLOT_HEURISTICS or starts with a NON_SLOT_HEURISTICS value.
   - For each remaining child:
     - `name`: Convert the child's Figma name to a slot name by converting to snake_case (replace spaces with underscores, lowercase). Example: "Leading Icon" -> "leading_icon".
     - `slot_type`: Call `infer_slot_type(child)`.
     - `is_required`: Default to 1 for TEXT nodes (labels are usually required), 0 for everything else.
     - `default_content`: For TEXT nodes, if `text_content` is present, store as JSON: `json.dumps({"type": "text", "value": text_content})`. For others, None.
     - `sort_order`: Use the child's sort_order.
   - Return a list of slot dicts with keys: `name`, `slot_type`, `is_required`, `default_content`, `sort_order`, `description` (None by default).

4. **`insert_slots(conn, component_id: int, slots: list[dict]) -> list[int]`**:
   - For each slot, UPSERT into `component_slots`: `INSERT INTO component_slots (component_id, name, slot_type, is_required, default_content, sort_order, description) VALUES (...) ON CONFLICT(component_id, name) DO UPDATE SET slot_type=excluded.slot_type, is_required=excluded.is_required, default_content=excluded.default_content, sort_order=excluded.sort_order`.
   - Return list of slot IDs.

5. **`extract_slots_from_nodes(conn, component_id: int, component_figma_node_id: str) -> list[int]`**:
   - Query the `nodes` table to find children of the component's default variant.
   - Strategy: Find nodes where `component_id` references this component (from component_sheet screens), or find nodes whose parent has the component's figma_node_id.
   - Simpler approach for initial implementation: Accept an optional `children` parameter directly (list of child dicts). If provided, use it. If not, query the DB.
   - Call `infer_slots(children)` and then `insert_slots(conn, component_id, slots)`.
   - Return list of slot IDs.

6. **Update `extract_components`**:
   - After inserting the component and its variants, if the component data includes a `children` key (direct children of the default variant or the component set's first variant), call `infer_slots` and `insert_slots`.
   - Update `parse_component_set` and `parse_standalone_component` to include a `children` key in their returned dicts if children data is available in the input.

## Acceptance Criteria

- [ ] `python -c "from dd.extract_components import infer_slots, insert_slots, infer_slot_type, extract_slots_from_nodes"` exits 0
- [ ] `infer_slot_type({"node_type": "TEXT", "name": "Label"})` returns `"text"`
- [ ] `infer_slot_type({"node_type": "INSTANCE", "name": "Leading Icon"})` returns `"icon"`
- [ ] `infer_slot_type({"node_type": "INSTANCE", "name": "Badge"})` returns `"component"`
- [ ] `infer_slots` filters out children named "background", "spacer", "divider"
- [ ] `infer_slots` with 2 valid children returns 2 slot dicts with correct names and types
- [ ] Slot names are snake_case: "Leading Icon" -> "leading_icon"
- [ ] TEXT slots default to `is_required=1`, others default to `is_required=0`
- [ ] TEXT slots with text_content include default_content as JSON
- [ ] `insert_slots` inserts rows and returns integer IDs
- [ ] `insert_slots` with same component_id + name twice is idempotent (UPSERT)
- [ ] Each slot has valid `component_id` FK

## Notes

- Slot inference is heuristic and designed to be "good enough" for initial extraction. Users can manually adjust slots during curation.
- The children data comes from the Figma component node. When extracting a COMPONENT_SET, the default variant's children are used. The agent may need to fetch children data separately if it wasn't included in the initial extraction.
- Non-slot filtering is conservative -- background, spacer, divider, separator elements are common structural elements that shouldn't be exposed as insertion points.
- The `composition_hint` field on the components table can be updated to summarize the slot structure. This is optional for this task but could be set to a JSON summary of slots.