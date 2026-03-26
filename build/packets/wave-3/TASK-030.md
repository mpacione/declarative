---
taskId: TASK-030
title: "Implement color clustering (Phase 5)"
wave: wave-3
testFirst: true
testLevel: unit
dependencies: [TASK-004, TASK-002]
produces:
  - dd/cluster_colors.py
verify:
  - type: typecheck
    command: 'python -c "from dd.cluster_colors import cluster_colors, group_by_delta_e, propose_color_name"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_clustering.py::test_color_clustering -v --no-header 2>/dev/null || pytest tests/test_clustering.py -k color -v'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-030: Implement color clustering (Phase 5)

## Spec Context

### From Technical Design Spec -- Phase 5: Clustering + Token Proposal

> **Color clustering:**
> 1. Query `v_color_census WHERE file_id = ?` -- all unique hex values with usage counts.
> 2. Convert to OKLCH for perceptual clustering.
> 3. Group colors within delta-E < 2.0 (imperceptible difference). Merge to the most-used value.
> 4. For each cluster, propose a DTCG name based on heuristics:
>    - Usage on large fills -> `color.surface.*`
>    - Usage on text -> `color.text.*`
>    - Usage on small accents/icons -> `color.accent.*`
>    - Usage on borders/strokes -> `color.border.*`
> 5. Rank by lightness within each group for `.primary`, `.secondary`, `.tertiary` naming.
>
> **Output:**
> - New rows in `tokens` (tier = `extracted`).
> - New rows in `token_values` (one per mode -- default mode initially).
> - Updated `node_token_bindings` -- `token_id` set, `binding_status` flipped to `proposed`, `confidence` set (1.0 for exact match, 0.8-0.99 for delta-E-merged).

### From User Requirements Spec -- UC-2: Cluster

> - System queries census views to surface unique values ranked by usage frequency.
> - System groups near-identical values (e.g., `#09090B` and `#0A0A0B` within OKLCH delta-E threshold).
> - System proposes token names following DTCG path conventions.
> - Proposed tokens are created with `tier = extracted`, bindings flipped to `binding_status = proposed`, each scored with a `confidence` value.
> - Each proposed token has a `confidence` score. Exact color matches = 1.0, delta-E-merged = 0.8-0.99.
> - Proposed token names are unique within their collection and follow DTCG dot-path conventions.
> - No token is created with 0 bindings (orphan tokens).

### From schema.sql -- v_color_census view

> ```sql
> CREATE VIEW v_color_census AS
> SELECT
>     ntb.resolved_value,
>     COUNT(*) AS usage_count,
>     COUNT(DISTINCT ntb.node_id) AS node_count,
>     GROUP_CONCAT(DISTINCT ntb.property) AS properties,
>     s.file_id
> FROM node_token_bindings ntb
> JOIN nodes n ON ntb.node_id = n.id
> JOIN screens s ON n.screen_id = s.id
> WHERE ntb.property LIKE 'fill%' OR ntb.property LIKE 'stroke%'
> GROUP BY ntb.resolved_value, s.file_id
> ORDER BY usage_count DESC;
> ```

### From schema.sql -- tokens, token_values, token_collections, token_modes tables

> ```sql
> CREATE TABLE IF NOT EXISTS token_collections (
>     id              INTEGER PRIMARY KEY,
>     file_id         INTEGER NOT NULL REFERENCES files(id),
>     figma_id        TEXT,
>     name            TEXT NOT NULL,
>     description     TEXT,
>     created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
> );
>
> CREATE TABLE IF NOT EXISTS token_modes (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
>     figma_mode_id   TEXT,
>     name            TEXT NOT NULL,
>     is_default      INTEGER NOT NULL DEFAULT 0,
>     UNIQUE(collection_id, name)
> );
>
> CREATE TABLE IF NOT EXISTS tokens (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id),
>     name            TEXT NOT NULL,
>     type            TEXT NOT NULL,
>     tier            TEXT NOT NULL DEFAULT 'extracted'
>                     CHECK(tier IN ('extracted', 'curated', 'aliased')),
>     alias_of        INTEGER REFERENCES tokens(id),
>     description     TEXT,
>     figma_variable_id TEXT,
>     sync_status     TEXT NOT NULL DEFAULT 'pending'
>                     CHECK(sync_status IN ('pending', 'figma_only', 'code_only', 'synced', 'drifted')),
>     created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(collection_id, name)
> );
>
> CREATE TABLE IF NOT EXISTS token_values (
>     id              INTEGER PRIMARY KEY,
>     token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id         INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
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
>     binding_status  TEXT NOT NULL DEFAULT 'unbound'
>                     CHECK(binding_status IN ('unbound', 'proposed', 'bound', 'overridden')),
>     UNIQUE(node_id, property)
> );
> ```

### From dd/color.py (produced by TASK-004)

> Exports:
> - `rgba_to_hex(r, g, b, a) -> str`
> - `hex_to_oklch(hex_color: str) -> tuple[float, float, float]`
> - `oklch_delta_e(color1: tuple, color2: tuple) -> float`

### From dd/db.py (produced by TASK-002)

> Exports:
> - `get_connection(db_path: str) -> sqlite3.Connection`
> - `init_db(db_path: str) -> sqlite3.Connection`

## Task

Create `dd/cluster_colors.py` implementing color clustering from Phase 5 of the TDS. This module queries the color census, groups colors by perceptual similarity, proposes semantic token names, and writes tokens + updates bindings.

1. **`query_color_census(conn, file_id: int) -> list[dict]`**:
   - Query `v_color_census WHERE file_id = ?`.
   - Return list of dicts with keys: `resolved_value`, `usage_count`, `node_count`, `properties`.
   - Filter out entries where `resolved_value` is None or empty.
   - Only include bindings with `binding_status = 'unbound'` (avoid re-clustering already proposed/bound colors). To do this, modify the query to add a subquery or JOIN that checks binding_status. Since the view doesn't filter by status, query the raw tables directly:
     ```sql
     SELECT ntb.resolved_value, COUNT(*) AS usage_count,
            COUNT(DISTINCT ntb.node_id) AS node_count,
            GROUP_CONCAT(DISTINCT ntb.property) AS properties
     FROM node_token_bindings ntb
     JOIN nodes n ON ntb.node_id = n.id
     JOIN screens s ON n.screen_id = s.id
     WHERE (ntb.property LIKE 'fill%' OR ntb.property LIKE 'stroke%')
       AND ntb.binding_status = 'unbound'
       AND s.file_id = ?
     GROUP BY ntb.resolved_value
     ORDER BY usage_count DESC
     ```

2. **`group_by_delta_e(colors: list[dict], threshold: float = 2.0) -> list[list[dict]]`**:
   - Accept list of color census dicts (each has `resolved_value`, `usage_count`, etc.).
   - Convert each `resolved_value` hex to OKLCH via `hex_to_oklch`.
   - Group colors: iterate in usage_count descending order. For each color, check if it belongs to an existing group (delta_e to the group's representative < threshold). If yes, add to that group. If no, start a new group.
   - The group representative is the most-used color in the group.
   - Return list of groups, where each group is a list of color dicts. Groups are sorted by total usage (sum of usage_counts) descending.

3. **`classify_color_role(properties: str) -> str`**:
   - Accept the `properties` string from the census (comma-separated list like "fill.0.color,stroke.0.color").
   - Heuristic:
     - If contains any `stroke` property -> "border"
     - If contains only `fill` properties -> check further (default to "surface")
   - This is a simplified heuristic. The full heuristic would also check node types (TEXT nodes -> "text"), but that requires extra joins. For now, return one of: "surface", "text", "border", "accent".
   - For a more nuanced approach, accept an optional `node_types` parameter (comma-separated) and:
     - If TEXT is the dominant node_type -> "text"
     - If stroke properties dominate -> "border"
     - Default -> "surface"

4. **`propose_color_name(role: str, lightness: float, index: int, existing_names: set[str]) -> str`**:
   - Build a name following DTCG dot-path: `color.{role}.{suffix}`.
   - Determine suffix by lightness ranking within the role:
     - Use ordinal names: "primary", "secondary", "tertiary", then "4", "5", etc. for more.
   - If the proposed name already exists in `existing_names`, append a numeric suffix.
   - Return the name string (e.g., "color.surface.primary").

5. **`cluster_colors(conn, file_id: int, collection_id: int, mode_id: int, threshold: float = 2.0) -> dict`**:
   - Main entry point.
   - Call `query_color_census(conn, file_id)`.
   - Call `group_by_delta_e(census, threshold)`.
   - For each group:
     - Determine the representative color (highest usage_count in group).
     - Classify the role via `classify_color_role`.
     - Convert representative to OKLCH for lightness-based naming.
   - Sort groups within each role by lightness (L value) descending for surface/border, ascending for text.
   - Propose names via `propose_color_name`.
   - For each proposed token:
     - INSERT into `tokens` (collection_id, name, type="color", tier="extracted").
     - INSERT into `token_values` (token_id, mode_id, raw_value=JSON of RGBA, resolved_value=hex).
     - UPDATE `node_token_bindings` for all bindings in the group: SET `token_id`, `binding_status = 'proposed'`, `confidence` (1.0 for exact hex match, scaled by delta_e for merged colors: `max(0.8, 1.0 - delta_e / 10.0)`).
   - Return summary dict: `{"tokens_created": int, "bindings_updated": int, "groups": int}`.

6. **`ensure_collection_and_mode(conn, file_id: int, collection_name: str = "Colors") -> tuple[int, int]`**:
   - Helper that creates or retrieves the token collection and default mode.
   - INSERT OR IGNORE into `token_collections` (file_id, name=collection_name).
   - Query to get collection_id.
   - INSERT OR IGNORE into `token_modes` (collection_id, name="Default", is_default=1).
   - Query to get mode_id.
   - Return (collection_id, mode_id).

## Acceptance Criteria

- [ ] `python -c "from dd.cluster_colors import cluster_colors, group_by_delta_e, propose_color_name, query_color_census, classify_color_role, ensure_collection_and_mode"` exits 0
- [ ] `group_by_delta_e` groups colors within delta_e < 2.0 together
- [ ] `group_by_delta_e` with two identical colors produces 1 group
- [ ] `group_by_delta_e` with very different colors produces separate groups
- [ ] `propose_color_name("surface", 0.9, 0, set())` returns `"color.surface.primary"`
- [ ] `propose_color_name` with existing name in set appends numeric suffix
- [ ] `classify_color_role` with stroke property returns "border"
- [ ] `cluster_colors` creates tokens in the `tokens` table with tier="extracted" and type="color"
- [ ] `cluster_colors` creates token_values with resolved_value matching the representative hex
- [ ] `cluster_colors` updates bindings to binding_status="proposed" with token_id set
- [ ] `cluster_colors` sets confidence=1.0 for exact matches, 0.8-0.99 for delta-E merged
- [ ] No orphan tokens created (every token has at least one binding)
- [ ] Token names are unique within the collection
- [ ] `ensure_collection_and_mode` is idempotent -- calling twice returns same IDs

## Notes

- This module is pure Python with DB operations -- no MCP calls. It reads from census views and writes to token/binding tables.
- The color role classification is heuristic and intentionally simple. The user refines names during curation (Phase 6).
- The `raw_value` in `token_values` should be the Figma-format RGBA JSON (e.g., `{"r":0.035,"g":0.035,"b":0.043,"a":1}`). Since we only have hex at this point, reconstruct approximate RGBA from the hex or store the hex as raw_value. Storing hex as raw_value is acceptable since extraction stored the original RGBA in the binding's raw_value.
- Import `hex_to_oklch` and `oklch_delta_e` from `dd.color`.