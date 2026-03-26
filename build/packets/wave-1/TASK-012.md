---
taskId: TASK-012
title: "Implement binding creation from extracted nodes"
wave: wave-1
testFirst: false
testLevel: unit
dependencies: [TASK-005, TASK-011]
produces:
  - dd/extract_bindings.py
verify:
  - type: typecheck
    command: 'python -c "from dd.extract_bindings import create_bindings_for_node, create_bindings_for_screen"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.extract_bindings import create_bindings_for_node; bindings = create_bindings_for_node({\"fills\": \"[{\\\"type\\\":\\\"SOLID\\\",\\\"color\\\":{\\\"r\\\":0.035,\\\"g\\\":0.035,\\\"b\\\":0.043,\\\"a\\\":1}}]\", \"font_size\": 16, \"corner_radius\": \"8\"}); print(len(bindings)); assert len(bindings) >= 2"'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-012: Implement binding creation from extracted nodes

## Spec Context

### From Technical Design Spec -- Phase 3: Value Normalization + Binding Creation

> **Tool:** Local Python, no MCP calls.
> **Runs immediately after each screen extraction, before the next `use_figma` call.**
>
> For every node property that represents a design value:
>
> | Property path | Raw value example | Resolved value |
> |---|---|---|
> | `fill.0.color` | `{"r":0.035,"g":0.035,"b":0.043,"a":1}` | `#09090B` |
> | `stroke.0.color` | `{"r":0.831,"g":0.831,"b":0.847,"a":1}` | `#D4D4D8` |
> | `cornerRadius` | `8` | `8` |
> | `fontSize` | `16` | `16` |
> | `fontFamily` | `"Inter"` | `Inter` |
> | `padding.top` | `16` | `16` |
> | `itemSpacing` | `8` | `8` |
> | `opacity` | `0.5` | `0.5` |
> | `effect.0.color` | `{"r":0,"g":0,"b":0,"a":0.1}` | `#0000001A` |
> | `effect.0.radius` | `6` | `6` |
>
> **Effect decomposition:** Each effect property gets its own binding row. A single DROP_SHADOW produces 5 bindings.
>
> **Mixed fills:** Figma supports multiple fills per node. Each gets its own binding row.
>
> Each property produces one row in `node_token_bindings` with `token_id = NULL`, `binding_status = 'unbound'`.

### From Technical Design Spec -- Re-extraction data preservation

> **Bindings:** For a re-extracted node, only bindings with `binding_status = 'unbound'` are overwritten. Bindings with status `proposed`, `bound`, or `overridden` are preserved. If a node's property value changed AND has a bound token, the binding is flipped to `binding_status = 'overridden'` and the new raw/resolved values are written, but `token_id` is kept.

### From schema.sql -- node_token_bindings table

> ```sql
> CREATE TABLE IF NOT EXISTS node_token_bindings (
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
> ```

### From dd/normalize.py (produced by TASK-005)

> Exports:
> - `normalize_fill(fills: list[dict]) -> list[dict]` -- returns binding dicts with property, raw_value, resolved_value
> - `normalize_stroke(strokes: list[dict]) -> list[dict]`
> - `normalize_effect(effects: list[dict]) -> list[dict]`
> - `normalize_typography(node: dict) -> list[dict]`
> - `normalize_spacing(node: dict) -> list[dict]`
> - `normalize_radius(corner_radius) -> list[dict]`

## Task

Create `dd/extract_bindings.py` that creates `node_token_bindings` rows from extracted node data. This module bridges the raw node data from `dd/extract_screens.py` with the normalization functions from `dd/normalize.py`.

1. **`create_bindings_for_node(node_row: dict) -> list[dict]`**:
   - Accept a single node dict (as stored in the DB or as returned by `parse_extraction_response`).
   - The dict may have keys: `fills`, `strokes`, `effects`, `corner_radius`, `font_family`, `font_weight`, `font_size`, `line_height`, `letter_spacing`, `padding_top`, `padding_right`, `padding_bottom`, `padding_left`, `item_spacing`, `counter_axis_spacing`, `opacity`.
   - For `fills`: If present and not None, parse from JSON string if it's a string, then call `normalize_fill`. Handle case where fills is already a list of dicts.
   - For `strokes`: Same pattern, call `normalize_stroke`.
   - For `effects`: Same pattern, call `normalize_effect`.
   - For typography: Assemble a dict from the node's text properties and call `normalize_typography`. Only do this if `font_size` is not None (indicates it's a TEXT node).
   - For spacing: Assemble a dict from padding and spacing properties, call `normalize_spacing`. Only do this if any spacing property is not None.
   - For radius: Parse `corner_radius` (may be JSON string, number, or dict), call `normalize_radius`.
   - For `opacity`: If present and not None and not 1.0, create a binding: `{"property": "opacity", "raw_value": json.dumps(value), "resolved_value": str(value)}`.
   - Return the combined list of all binding dicts.

2. **`insert_bindings(conn, node_id: int, bindings: list[dict]) -> int`**:
   - Insert each binding into `node_token_bindings` with the given `node_id`.
   - Use UPSERT: `INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) VALUES (?, ?, ?, ?, 'unbound') ON CONFLICT(node_id, property) DO UPDATE SET raw_value=excluded.raw_value, resolved_value=excluded.resolved_value WHERE binding_status = 'unbound'`.
   - **Re-extraction safety**: The `WHERE binding_status = 'unbound'` clause in the ON CONFLICT ensures that only unbound bindings are overwritten. Proposed/bound/overridden bindings are preserved.
   - For bound bindings where the value changed: detect this by checking if the existing `resolved_value` differs from the new one AND `binding_status` is in ('proposed', 'bound'). If so, update the raw/resolved values and set `binding_status = 'overridden'`.
   - Implementation: Use a two-step approach -- first try the UPSERT (which only updates unbound). Then do a second UPDATE for value-changed bound bindings.
   - Return the count of bindings inserted/updated.

3. **`create_bindings_for_screen(conn, screen_id: int) -> int`**:
   - Query all nodes for the given screen_id from the `nodes` table.
   - For each node, call `create_bindings_for_node` with the node's data.
   - Call `insert_bindings` for each node's bindings.
   - Return total binding count.

All functions should import from `dd.normalize` for normalization and `json` for parsing.

## Acceptance Criteria

- [ ] `python -c "from dd.extract_bindings import create_bindings_for_node, create_bindings_for_screen, insert_bindings"` exits 0
- [ ] `create_bindings_for_node` with a node that has a solid fill produces at least 1 binding with property `fill.0.color`
- [ ] `create_bindings_for_node` with a TEXT node (font_size=16) produces a `fontSize` binding
- [ ] `create_bindings_for_node` with a DROP_SHADOW effect produces 5 effect bindings
- [ ] `create_bindings_for_node` with opacity=0.5 produces an `opacity` binding
- [ ] `create_bindings_for_node` with opacity=1.0 produces NO opacity binding
- [ ] `create_bindings_for_node` with all None values returns empty list
- [ ] `insert_bindings` inserts binding rows into the DB and returns count
- [ ] `insert_bindings` called twice for same node+property with unbound status updates the value
- [ ] `insert_bindings` does NOT overwrite a binding that has binding_status='bound'
- [ ] `create_bindings_for_screen` processes all nodes in a screen and returns total binding count
- [ ] All binding dicts have keys: `property`, `raw_value`, `resolved_value`

## Notes

- Node data coming from the DB will have `fills`, `strokes`, `effects` as JSON strings. Data coming directly from `parse_extraction_response` may have them as strings or objects. The function should handle both by checking `isinstance(value, str)` and parsing with `json.loads` if needed.
- The `corner_radius` field has multiple formats: a plain number (uniform), a JSON string of a number, or a JSON object with per-corner values. Handle all three.
- The opacity binding is only created when opacity != 1.0 because 1.0 is the default and not worth tokenizing.
- The re-extraction safety logic in `insert_bindings` preserves curation work. This is critical for NFR-8.