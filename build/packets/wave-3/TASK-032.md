---
taskId: TASK-032
title: "Implement spacing clustering"
wave: wave-3
testFirst: true
testLevel: unit
dependencies: [TASK-002]
produces:
  - dd/cluster_spacing.py
verify:
  - type: typecheck
    command: 'python -c "from dd.cluster_spacing import cluster_spacing, detect_scale_pattern, propose_spacing_name"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_clustering.py -k spacing -v'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-032: Implement spacing clustering

## Spec Context

### From Technical Design Spec -- Phase 5: Clustering + Token Proposal

> **Spacing clustering:**
> 1. Query `v_spacing_census WHERE file_id = ?` -- unique values by property.
> 2. Identify scale pattern (likely 4px base: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64).
> 3. Propose names: `space.1` through `space.16` (multiplier notation) or `space.xs` through `space.4xl` (t-shirt notation).

### From schema.sql -- v_spacing_census view

> ```sql
> CREATE VIEW v_spacing_census AS
> SELECT
>     ntb.resolved_value,
>     ntb.property,
>     COUNT(*) AS usage_count,
>     s.file_id
> FROM node_token_bindings ntb
> JOIN nodes n ON ntb.node_id = n.id
> JOIN screens s ON n.screen_id = s.id
> WHERE ntb.property IN ('padding.top','padding.right','padding.bottom','padding.left','itemSpacing','counterAxisSpacing')
> GROUP BY ntb.resolved_value, ntb.property, s.file_id
> ORDER BY CAST(ntb.resolved_value AS REAL), usage_count DESC;
> ```

### From schema.sql -- tokens, token_values, node_token_bindings tables

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id),
>     name            TEXT NOT NULL,
>     type            TEXT NOT NULL,
>     tier            TEXT NOT NULL DEFAULT 'extracted',
>     ...
>     UNIQUE(collection_id, name)
> );
>
> CREATE TABLE IF NOT EXISTS token_values (
>     id              INTEGER PRIMARY KEY,
>     token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id         INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     ...
>     UNIQUE(token_id, mode_id)
> );
>
> CREATE TABLE IF NOT EXISTS node_token_bindings (
>     id              INTEGER PRIMARY KEY,
>     node_id         INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
>     property        TEXT NOT NULL,
>     token_id        INTEGER REFERENCES tokens(id),
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     confidence      REAL,
>     binding_status  TEXT NOT NULL DEFAULT 'unbound',
>     UNIQUE(node_id, property)
> );
> ```

### From dd/db.py (produced by TASK-002)

> Exports: `init_db(db_path) -> sqlite3.Connection`

## Task

Create `dd/cluster_spacing.py` implementing spacing clustering from Phase 5. This module detects the spacing scale pattern, proposes token names, and writes tokens + updates bindings.

1. **`query_spacing_census(conn, file_id: int) -> list[dict]`**:
   - Query spacing bindings directly (not the view, to also filter by binding_status):
     ```sql
     SELECT ntb.resolved_value, ntb.property, COUNT(*) AS usage_count
     FROM node_token_bindings ntb
     JOIN nodes n ON ntb.node_id = n.id
     JOIN screens s ON n.screen_id = s.id
     WHERE ntb.property IN ('padding.top','padding.right','padding.bottom','padding.left',
                            'itemSpacing','counterAxisSpacing')
       AND ntb.binding_status = 'unbound'
       AND s.file_id = ?
     GROUP BY ntb.resolved_value, ntb.property
     ORDER BY CAST(ntb.resolved_value AS REAL)
     ```
   - Return list of dicts: `{"resolved_value": str, "property": str, "usage_count": int}`.
   - Filter out entries where resolved_value is "0" or empty.

2. **`detect_scale_pattern(values: list[float]) -> tuple[float, str]`**:
   - Accept a sorted list of unique spacing values (as floats).
   - Try to detect a common base unit:
     - Compute GCD of all values (or approximate GCD for floats: round to nearest int first).
     - Common bases: 4 (most common in modern design), 8, 2.
   - If a clear base is detected (GCD divides all values evenly or nearly):
     - Return `(base, "multiplier")` -- use multiplier notation: `space.1`, `space.2`, etc.
   - If no clear base:
     - Return `(0, "tshirt")` -- use t-shirt notation: `space.xs`, `space.sm`, `space.md`, etc.

3. **`propose_spacing_name(value: float, base: float, notation: str, index: int, total: int) -> str`**:
   - If `notation == "multiplier"` and base > 0:
     - multiplier = round(value / base)
     - Return `f"space.{multiplier}"` (e.g., "space.1" for 4px, "space.2" for 8px, "space.4" for 16px).
   - If `notation == "tshirt"`:
     - Map index to t-shirt sizes: ["xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl"]
     - If more values than labels, use numeric: "space.9", "space.10", etc.
     - Return `f"space.{size_label}"`.

4. **`cluster_spacing(conn, file_id: int, collection_id: int, mode_id: int) -> dict`**:
   - Main entry point.
   - Call `query_spacing_census(conn, file_id)`.
   - Extract unique values: collect all unique `resolved_value` entries (across all property types), convert to floats, sort.
   - Call `detect_scale_pattern(unique_values)`.
   - For each unique value, propose a token name.
   - Create ONE token per unique value (shared across padding.top, padding.left, itemSpacing, etc. since the value is the same):
     - INSERT into `tokens` (collection_id, name, type="dimension", tier="extracted").
     - INSERT into `token_values` (token_id, mode_id, raw_value=JSON, resolved_value=str(value)).
   - UPDATE all `node_token_bindings` where `resolved_value = str(value)` AND property is a spacing property AND binding_status='unbound': SET token_id, binding_status='proposed', confidence=1.0.
   - Return: `{"tokens_created": int, "bindings_updated": int, "base_unit": float, "notation": str}`.

5. **`ensure_spacing_collection(conn, file_id: int) -> tuple[int, int]`**:
   - Create or retrieve "Spacing" collection and "Default" mode.
   - Return (collection_id, mode_id).

## Acceptance Criteria

- [ ] `python -c "from dd.cluster_spacing import cluster_spacing, detect_scale_pattern, propose_spacing_name, query_spacing_census, ensure_spacing_collection"` exits 0
- [ ] `detect_scale_pattern([4, 8, 12, 16, 24, 32])` returns `(4, "multiplier")` or `(4.0, "multiplier")`
- [ ] `detect_scale_pattern([5, 13, 27, 41])` returns `(0, "tshirt")` (no clear base)
- [ ] `propose_spacing_name(16, 4, "multiplier", 0, 5)` returns `"space.4"`
- [ ] `propose_spacing_name(8, 0, "tshirt", 1, 5)` returns `"space.sm"`
- [ ] `cluster_spacing` creates tokens with type="dimension" and tier="extracted"
- [ ] `cluster_spacing` creates one token per unique spacing value (not per property)
- [ ] `cluster_spacing` updates bindings across all spacing property types (padding.*, itemSpacing, counterAxisSpacing)
- [ ] All bindings updated to binding_status="proposed" with confidence=1.0
- [ ] No orphan tokens created
- [ ] Token names are unique within collection

## Notes

- Spacing tokens are shared across property types. A value of 16px used as `padding.top`, `padding.left`, and `itemSpacing` all map to the same `space.4` token. This is intentional -- the semantic meaning is the spacing value, not the property it's applied to.
- The GCD detection for scale base is approximate. Real-world design files may have values that don't perfectly divide (e.g., 4, 8, 12, 16, 20, 24, 32, 40, 48, 64 has base 4). Use integer rounding.
- Zero-value spacing is skipped (it was already filtered out during extraction by normalize_spacing in TASK-005).