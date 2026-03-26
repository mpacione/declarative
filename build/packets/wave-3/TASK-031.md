---
taskId: TASK-031
title: "Implement typography clustering"
wave: wave-3
testFirst: true
testLevel: unit
dependencies: [TASK-002]
produces:
  - dd/cluster_typography.py
verify:
  - type: typecheck
    command: 'python -c "from dd.cluster_typography import cluster_typography, group_type_scale, propose_type_name"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_clustering.py -k typography -v'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-031: Implement typography clustering

## Spec Context

### From Technical Design Spec -- Phase 5: Clustering + Token Proposal

> **Typography clustering:**
> 1. Query `v_type_census WHERE file_id = ?` -- unique font/weight/size/lineHeight combos.
> 2. Group into scale tiers by font size.
> 3. Propose names: `type.display.lg`, `type.body.md`, `type.label.sm`, etc.
>
> **Output:**
> - New rows in `tokens` (tier = `extracted`).
> - New rows in `token_values` (one per mode -- default mode initially).
> - Updated `node_token_bindings` -- `token_id` set, `binding_status` flipped to `proposed`, `confidence` set.

### From schema.sql -- v_type_census view

> ```sql
> CREATE VIEW v_type_census AS
> SELECT
>     n.font_family,
>     n.font_weight,
>     n.font_size,
>     json_extract(n.line_height, '$.value') AS line_height_value,
>     COUNT(*) AS usage_count,
>     s.file_id
> FROM nodes n
> JOIN screens s ON n.screen_id = s.id
> WHERE n.node_type = 'TEXT' AND n.font_family IS NOT NULL
> GROUP BY n.font_family, n.font_weight, n.font_size, json_extract(n.line_height, '$.value'), s.file_id
> ORDER BY usage_count DESC;
> ```

### From schema.sql -- tokens, token_values, node_token_bindings tables

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id),
>     name            TEXT NOT NULL,
>     type            TEXT NOT NULL,
>     tier            TEXT NOT NULL DEFAULT 'extracted'
>                     CHECK(tier IN ('extracted', 'curated', 'aliased')),
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

### From TDS -- Key Design Decision on Composite Tokens

> **Composite tokens (typography, shadow, border)** are stored as individual atomic tokens in the DB. DTCG composite types are assembled at export time when generating `tokens.json`. This keeps the DB queryable (you can ask "all font sizes" without parsing composite JSON).

### From dd/db.py (produced by TASK-002)

> Exports: `init_db(db_path) -> sqlite3.Connection`

## Task

Create `dd/cluster_typography.py` implementing typography clustering from Phase 5. Typography tokens are stored as individual atomic tokens (fontSize, fontFamily, fontWeight, lineHeight, letterSpacing) per the key design decision -- NOT as composite types.

1. **`query_type_census(conn, file_id: int) -> list[dict]`**:
   - Query `v_type_census WHERE file_id = ?`.
   - Return list of dicts with keys: `font_family`, `font_weight`, `font_size`, `line_height_value`, `usage_count`.
   - Filter out entries with NULL font_size.

2. **`group_type_scale(census: list[dict]) -> list[dict]`**:
   - Group census entries by font_size into scale tiers.
   - Classify each font_size into a semantic category based on size ranges:
     - >= 32: "display"
     - >= 24 and < 32: "heading"
     - >= 16 and < 24: "body"
     - >= 12 and < 16: "label"
     - < 12: "caption"
   - Within each category, sort by font_size descending.
   - Assign size suffixes: "lg", "md", "sm" (or "xl", "lg", "md", "sm", "xs" if more than 3 in a category).
   - Return list of dicts: `{"category": str, "size_suffix": str, "font_family": str, "font_weight": int, "font_size": float, "line_height": float|None, "usage_count": int}`.
   - If multiple entries share the same font_size but differ in weight/family, treat each unique combination as a separate tier entry.

3. **`propose_type_name(category: str, size_suffix: str, existing_names: set[str]) -> str`**:
   - Build DTCG dot-path: `type.{category}.{size_suffix}` (e.g., "type.body.md").
   - If name already exists in `existing_names`, append a numeric suffix ("type.body.md.2").
   - Return the name string.

4. **`cluster_typography(conn, file_id: int, collection_id: int, mode_id: int) -> dict`**:
   - Main entry point.
   - Call `query_type_census(conn, file_id)`.
   - Call `group_type_scale(census)`.
   - For each tier entry, create INDIVIDUAL atomic tokens:
     - `type.{category}.{suffix}.fontSize` -- type="dimension", resolved_value=str(font_size)
     - `type.{category}.{suffix}.fontFamily` -- type="fontFamily", resolved_value=font_family
     - `type.{category}.{suffix}.fontWeight` -- type="fontWeight", resolved_value=str(font_weight)
     - `type.{category}.{suffix}.lineHeight` -- type="dimension", resolved_value=str(line_height) (if not None)
   - INSERT each token into `tokens` (collection_id, name, type, tier="extracted").
   - INSERT each token_value into `token_values` (token_id, mode_id, raw_value, resolved_value).
   - UPDATE `node_token_bindings`: For TEXT nodes matching this font_size/family/weight combo, update the corresponding binding (e.g., `property = 'fontSize'` -> assign the fontSize token, `property = 'fontFamily'` -> assign the fontFamily token).
   - Set `binding_status = 'proposed'`, `confidence = 1.0` (typography matches are exact).
   - Return: `{"tokens_created": int, "bindings_updated": int, "type_scales": int}`.

5. **`ensure_typography_collection(conn, file_id: int) -> tuple[int, int]`**:
   - Create or retrieve "Typography" collection and "Default" mode.
   - Same pattern as `ensure_collection_and_mode` in cluster_colors.
   - Return (collection_id, mode_id).

## Acceptance Criteria

- [ ] `python -c "from dd.cluster_typography import cluster_typography, group_type_scale, propose_type_name, query_type_census, ensure_typography_collection"` exits 0
- [ ] `group_type_scale` classifies font_size=32 as "display", font_size=16 as "body", font_size=12 as "label"
- [ ] `group_type_scale` assigns "lg", "md", "sm" suffixes within a category
- [ ] `propose_type_name("body", "md", set())` returns `"type.body.md"`
- [ ] `propose_type_name` avoids name collisions with existing names
- [ ] `cluster_typography` creates individual atomic tokens (fontSize, fontFamily, fontWeight, lineHeight) not composites
- [ ] `cluster_typography` updates bindings with correct token_id and binding_status="proposed"
- [ ] All tokens have tier="extracted" and correct type (dimension, fontFamily, fontWeight)
- [ ] No orphan tokens -- every created token has at least 1 binding
- [ ] Token names are unique within the collection
- [ ] Typography bindings get confidence=1.0 (exact match)

## Notes

- Typography tokens are stored as INDIVIDUAL atomic tokens per the TDS design decision. The DTCG composite `typography` type is assembled at export time (Wave 6). This means a single type scale tier like "type.body.md" produces 3-4 separate tokens in the DB.
- The binding update logic needs to match TEXT nodes by their font_size + font_family + font_weight combination. Query nodes that match all three, then update their individual property bindings.
- `line_height_value` from the census view uses `json_extract` to pull the numeric value from the JSON `{"value": 24, "unit": "PIXELS"}` format. If the extraction stored lineHeight as `"AUTO"`, it will be NULL in the census.