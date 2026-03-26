---
taskId: TASK-021
title: "Implement variant dimension value population"
wave: wave-2
testFirst: false
testLevel: unit
dependencies: [TASK-020]
produces:
  - dd/extract_components.py
verify:
  - type: typecheck
    command: 'python -c "from dd.extract_components import populate_variant_dimension_values"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.extract_components import populate_variant_dimension_values; print(\"OK\")"'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-021: Implement variant dimension value population

## Spec Context

### From Technical Design Spec -- Phase 4: Component Extraction

> 5. Populate `variant_dimension_values`: link each variant to its position on each axis.

### From User Requirements Spec -- FR-3.6: Interaction States

> FR-3.6.3: Each variant dimension value links a specific variant to its position on each axis, enabling queries like "all large+hover variants."

### From Technical Design Spec -- Agent Cookbook Query #4

> ```sql
> -- Find all hover states across all components:
> SELECT c.name AS component_name, cv.name AS variant_name, cv.properties
> FROM variant_dimension_values vdv
> JOIN variant_axes va ON vdv.axis_id = va.id
> JOIN component_variants cv ON vdv.variant_id = cv.id
> JOIN components c ON cv.component_id = c.id
> WHERE va.is_interaction = 1 AND vdv.value = 'hover';
> ```

### From schema.sql -- variant_dimension_values table

> ```sql
> CREATE TABLE IF NOT EXISTS variant_dimension_values (
>     id              INTEGER PRIMARY KEY,
>     variant_id      INTEGER NOT NULL REFERENCES component_variants(id) ON DELETE CASCADE,
>     axis_id         INTEGER NOT NULL REFERENCES variant_axes(id) ON DELETE CASCADE,
>     value           TEXT NOT NULL,
>     UNIQUE(variant_id, axis_id)
> );
>
> CREATE INDEX idx_variant_dim_values_axis ON variant_dimension_values(axis_id);
> ```

### From schema.sql -- Related tables

> ```sql
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

### From dd/extract_components.py (produced by TASK-020)

> Exports:
> - `extract_components(conn, file_id, component_nodes) -> list[int]` -- inserts components, variants, axes
> - `insert_component(conn, file_id, component_data) -> int`
> - `insert_variants(conn, component_id, variants) -> list[int]`
> - `insert_variant_axes(conn, component_id, axes) -> list[int]`
> - `parse_variant_properties(variant_name) -> dict[str, str]`

## Task

Extend `dd/extract_components.py` by adding a function to populate the `variant_dimension_values` table. This links each variant to its specific value on each axis, enabling cross-component queries like "all hover variants" or "all large+solid variants."

1. **`populate_variant_dimension_values(conn, component_id: int) -> int`**:
   - Query all `component_variants` for the given `component_id`.
   - Query all `variant_axes` for the given `component_id`.
   - For each variant:
     - Parse its `properties` JSON string to get a dict of axis_name -> value (e.g., `{"size": "large", "style": "solid", "state": "default"}`).
     - For each axis: look up the axis_id from the variant_axes query results.
     - Get the variant's value for this axis from the properties dict.
     - UPSERT into `variant_dimension_values`: `INSERT INTO variant_dimension_values (variant_id, axis_id, value) VALUES (?, ?, ?) ON CONFLICT(variant_id, axis_id) DO UPDATE SET value=excluded.value`.
   - Return the total number of dimension values inserted/updated.
   - Commit after all inserts.

2. **Update `extract_components` to call `populate_variant_dimension_values`**:
   - After calling `insert_component`, `insert_variants`, and `insert_variant_axes` for each component, also call `populate_variant_dimension_values(conn, component_id)`.
   - This ensures the full component model is populated in a single pass.

3. **Handle edge cases**:
   - Standalone components (no variants): `populate_variant_dimension_values` should gracefully return 0 when there are no variants or axes.
   - Variants with missing axis values: If a variant's properties dict doesn't include a value for an axis (unlikely but possible with malformed data), skip that axis-variant combination.
   - JSON parsing: The `properties` column in `component_variants` is a JSON string. Use `json.loads` to parse it.

## Acceptance Criteria

- [ ] `python -c "from dd.extract_components import populate_variant_dimension_values"` exits 0
- [ ] `populate_variant_dimension_values` inserts rows linking variants to their axis values
- [ ] For a component with 3 variants and 2 axes, it creates 6 dimension value rows (3 * 2)
- [ ] For a standalone component (no variants), it returns 0
- [ ] UPSERT behavior: calling twice with same data doesn't create duplicates
- [ ] Each `variant_dimension_values` row has a valid `variant_id` FK and `axis_id` FK
- [ ] `extract_components` now calls `populate_variant_dimension_values` automatically
- [ ] The query from the Agent Cookbook (find all hover states) works after population:
      `SELECT vdv.value FROM variant_dimension_values vdv JOIN variant_axes va ON vdv.axis_id = va.id WHERE va.is_interaction = 1 AND vdv.value = 'hover'` returns expected rows

## Notes

- This function operates purely on DB data -- it reads from `component_variants` and `variant_axes` (already populated by TASK-020) and writes to `variant_dimension_values`.
- The `properties` column in `component_variants` was stored as a JSON string by `insert_variants` in TASK-020. Make sure to parse it with `json.loads`.
- The UNIQUE(variant_id, axis_id) constraint ensures one value per variant per axis. This matches the real-world constraint: a variant has exactly one position on each axis.