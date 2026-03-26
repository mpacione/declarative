---
taskId: TASK-036
title: "Write integration tests for extraction-to-clustering pipeline"
wave: wave-3
testFirst: true
testLevel: integration
dependencies: [TASK-007, TASK-034]
produces:
  - tests/test_clustering_integration.py
verify:
  - type: test
    command: 'pytest tests/test_clustering_integration.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-036: Write integration tests for extraction-to-clustering pipeline

## Spec Context

### From Task Decomposition Guide -- Testing Strategy

> **Integration tests** (wave 1+): Test cross-module boundaries using fixture DBs with real pipeline output. No mocks at the seam being tested -- only external dependencies (Figma MCP) are mocked. These catch: schema mismatches between producer/consumer, FK violations, incorrect data shapes flowing across module boundaries.

### From Task Decomposition Guide -- Wave 3 Test Description

> TASK-036: Write integration tests for extraction-to-clustering pipeline -- seed post-extraction fixture DB; run clustering orchestrator; verify tokens reference valid bindings, census views produce expected aggregations, clustering consumes real extraction output correctly.

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `seed_post_extraction(db) -> sqlite3.Connection`
>   - 1 file (id=1, file_key="test_file_key_abc123")
>   - 3 screens (Home, Settings, Buttons and Controls)
>   - 10 nodes across screens
>   - 15 bindings: 5 color, 3 typography, 3 spacing, 2 radius, 2 effect
>   - All bindings: binding_status="unbound", token_id=NULL
>   - 1 extraction_run (status="completed")
> - `make_mock_figma_response(screen_name, node_count) -> list[dict]`

### From dd/cluster.py (produced by TASK-034)

> Exports:
> - `run_clustering(conn, file_id, color_threshold, agent_id) -> dict`
> - `generate_summary(conn, file_id, results) -> dict`
> - `validate_no_orphan_tokens(conn, file_id) -> list[int]`

### From dd/extract.py (produced by TASK-014)

> Exports:
> - `run_inventory(conn, file_key, file_name, frames, ...) -> dict`
> - `process_screen(conn, run_id, screen_id, figma_node_id, raw_response) -> dict`
> - `run_extraction_pipeline(conn, ..., extract_fn, ...) -> dict`

### From schema.sql -- Key views for verification

> ```sql
> CREATE VIEW v_color_census AS
> SELECT ntb.resolved_value, COUNT(*) AS usage_count, COUNT(DISTINCT ntb.node_id) AS node_count,
>        GROUP_CONCAT(DISTINCT ntb.property) AS properties, s.file_id
> FROM node_token_bindings ntb
> JOIN nodes n ON ntb.node_id = n.id JOIN screens s ON n.screen_id = s.id
> WHERE ntb.property LIKE 'fill%' OR ntb.property LIKE 'stroke%'
> GROUP BY ntb.resolved_value, s.file_id ORDER BY usage_count DESC;
>
> CREATE VIEW v_type_census AS
> SELECT n.font_family, n.font_weight, n.font_size,
>        json_extract(n.line_height, '$.value') AS line_height_value,
>        COUNT(*) AS usage_count, s.file_id
> FROM nodes n JOIN screens s ON n.screen_id = s.id
> WHERE n.node_type = 'TEXT' AND n.font_family IS NOT NULL
> GROUP BY n.font_family, n.font_weight, n.font_size, json_extract(n.line_height, '$.value'), s.file_id
> ORDER BY usage_count DESC;
>
> CREATE VIEW v_spacing_census AS
> SELECT ntb.resolved_value, ntb.property, COUNT(*) AS usage_count, s.file_id
> FROM node_token_bindings ntb JOIN nodes n ON ntb.node_id = n.id JOIN screens s ON n.screen_id = s.id
> WHERE ntb.property IN ('padding.top','padding.right','padding.bottom','padding.left','itemSpacing','counterAxisSpacing')
> GROUP BY ntb.resolved_value, ntb.property, s.file_id
> ORDER BY CAST(ntb.resolved_value AS REAL), usage_count DESC;
>
> CREATE VIEW v_curation_progress AS
> SELECT binding_status, COUNT(*) AS binding_count,
>        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM node_token_bindings), 1) AS pct
> FROM node_token_bindings GROUP BY binding_status;
>
> CREATE VIEW v_token_coverage AS
> SELECT t.name AS token_name, t.type AS token_type, t.tier, t.collection_id,
>        COUNT(ntb.id) AS binding_count, COUNT(DISTINCT ntb.node_id) AS node_count,
>        COUNT(DISTINCT n.screen_id) AS screen_count
> FROM tokens t LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
> LEFT JOIN nodes n ON ntb.node_id = n.id
> GROUP BY t.id ORDER BY binding_count DESC;
> ```

### From schema.sql -- token_collections, token_modes, tokens, token_values

> ```sql
> CREATE TABLE IF NOT EXISTS token_collections (
>     id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id),
>     figma_id TEXT, name TEXT NOT NULL, description TEXT, created_at TEXT
> );
> CREATE TABLE IF NOT EXISTS token_modes (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
>     figma_mode_id TEXT, name TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0,
>     UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS tokens (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id),
>     name TEXT NOT NULL, type TEXT NOT NULL, tier TEXT NOT NULL DEFAULT 'extracted',
>     alias_of INTEGER REFERENCES tokens(id), description TEXT, figma_variable_id TEXT,
>     sync_status TEXT NOT NULL DEFAULT 'pending', created_at TEXT, updated_at TEXT,
>     UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS token_values (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, extracted_at TEXT,
>     UNIQUE(token_id, mode_id)
> );
> ```

## Task

Create `tests/test_clustering_integration.py` with integration tests that verify the boundary between extraction output and clustering. These tests seed a DB with real extraction output (via `seed_post_extraction`), run the clustering orchestrator, and verify the resulting DB state. Use `@pytest.mark.integration` on all tests.

### Test Functions

1. **`test_clustering_consumes_extraction_output(db)`**:
   - Call `seed_post_extraction(db)` to set up extraction output.
   - Call `run_clustering(db, file_id=1)`.
   - Verify:
     - `token_collections` table has rows (at least Colors, Typography, Spacing, Radius, Effects)
     - `token_modes` table has rows with is_default=1 for each collection
     - `tokens` table has rows (all tier="extracted")
     - `token_values` table has rows linking to tokens and modes

2. **`test_tokens_reference_valid_bindings(db)`**:
   - Seed + run clustering.
   - Verify FK integrity:
     - Every binding with `token_id IS NOT NULL` references a valid `tokens.id`:
       `SELECT COUNT(*) FROM node_token_bindings WHERE token_id IS NOT NULL AND token_id NOT IN (SELECT id FROM tokens)` = 0
     - Every token has at least 1 binding (no orphans):
       `SELECT t.id FROM tokens t LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id WHERE ntb.id IS NULL` = empty
     - Every `token_values.token_id` references a valid `tokens.id`
     - Every `token_values.mode_id` references a valid `token_modes.id`

3. **`test_census_views_before_and_after_clustering(db)`**:
   - Seed extraction.
   - Query `v_color_census`, `v_type_census`, `v_spacing_census` BEFORE clustering.
   - Verify census views return populated results matching the fixture data.
   - Run clustering.
   - Query `v_curation_progress` AFTER clustering.
   - Verify:
     - "proposed" binding_status has count > 0
     - "unbound" count has decreased (some bindings were assigned tokens)
     - The total binding count hasn't changed (clustering doesn't add or remove bindings)

4. **`test_token_coverage_view_after_clustering(db)`**:
   - Seed + run clustering.
   - Query `v_token_coverage`.
   - Verify:
     - Returns rows with binding_count > 0 for created tokens
     - token_type values include "color", "dimension" (at minimum)
     - All tokens have tier="extracted"

5. **`test_binding_status_transition(db)`**:
   - Seed extraction (all bindings unbound).
   - Verify: all 15 bindings have binding_status="unbound".
   - Run clustering.
   - Count bindings by status.
   - Verify:
     - Some bindings transitioned to "proposed" (count > 0)
     - Proposed bindings have token_id IS NOT NULL
     - Proposed bindings have confidence IS NOT NULL
     - Any remaining "unbound" bindings have token_id IS NULL

6. **`test_collection_and_mode_structure(db)`**:
   - Seed + run clustering.
   - Verify:
     - Each collection has exactly 1 mode with is_default=1
     - Collection names are distinct
     - Every token belongs to a collection that references file_id=1
     - Every token_value references a mode within the token's collection

7. **`test_token_name_uniqueness_across_collections(db)`**:
   - Seed + run clustering.
   - Verify:
     - `SELECT collection_id, name, COUNT(*) FROM tokens GROUP BY collection_id, name HAVING COUNT(*) > 1` returns 0 rows
     - Token names follow DTCG dot-path pattern: match `^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*(\.\d+)?$`

8. **`test_clustering_does_not_modify_extraction_data(db)`**:
   - Seed extraction.
   - Record node count, screen count, file data.
   - Run clustering.
   - Verify:
     - Node count unchanged
     - Screen count unchanged
     - File data unchanged
     - Node properties (fills, strokes, etc.) unchanged
     - Only `node_token_bindings.token_id`, `binding_status`, and `confidence` were modified

## Acceptance Criteria

- [ ] `pytest tests/test_clustering_integration.py -v` passes all tests
- [ ] At least 8 test functions
- [ ] All tests use `@pytest.mark.integration` marker
- [ ] Tests use real DB (in-memory SQLite), not mock DB
- [ ] Tests start from `seed_post_extraction` fixture output (real Wave 1 data)
- [ ] FK integrity verified for all token-related tables
- [ ] Census views tested before and after clustering
- [ ] Binding status transitions verified (unbound -> proposed)
- [ ] Token name uniqueness verified within collections
- [ ] Extraction data not modified by clustering (only binding columns updated)
- [ ] `pytest tests/test_clustering_integration.py -v --tb=short` exits 0

## Notes

- Integration tests verify the BOUNDARY between extraction output and clustering. They run real clustering on real (fixture) extraction data and verify the resulting DB state.
- Import `seed_post_extraction` from `tests.fixtures` for setup.
- Import `run_clustering` from `dd.cluster` for execution.
- The fixture data has 15 bindings. After clustering, most should be "proposed". Some may remain "unbound" if they don't match any clustering rule (e.g., gradient fills, mixed values).
- Use `@pytest.mark.timeout(30)` on all tests as safety.
- The census view tests are important: they prove the views produce correct aggregations from real pipeline data, which the clustering modules depend on.