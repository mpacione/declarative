---
taskId: TASK-037
title: "Write mini-e2e test: extraction through clustering"
wave: wave-3
testFirst: true
testLevel: e2e
dependencies: [TASK-007, TASK-034, TASK-016]
produces:
  - tests/test_e2e_extract_cluster.py
verify:
  - type: test
    command: 'pytest tests/test_e2e_extract_cluster.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-037: Write mini-e2e test: extraction through clustering

## Spec Context

### From Task Decomposition Guide -- Wave 3 Test Description

> TASK-037: Write mini-e2e test: extraction through clustering -- fixture DB -> run full extraction with mock Figma data -> run clustering -> verify: token_values populated, bindings updated with token_id, census views accurate, no orphan bindings; this is the first end-to-end test covering waves 0-3.

### From Task Decomposition Guide -- E2E Test Requirements

> E2E test tasks (wave 3+) MUST:
> - Run the real pipeline functions in sequence, not just assert on pre-seeded state
> - Start from `seed_post_extraction()` fixture at minimum, execute forward through current wave
> - Assert on final observable state (DB contents, export file contents) not intermediate calls
> - Be marked with both @pytest.mark.e2e and @pytest.mark.slow

### From Task Decomposition Guide -- Testing Strategy

> **E2E tests** (wave 3+): Run the full pipeline from extraction through the current wave's final output. Use `tests/fixtures.py` factories to seed initial state, then execute the real pipeline. These catch: emergent failures from module interactions, state accumulation bugs, regression across waves.

### From dd/extract.py (produced by TASK-014)

> Exports:
> - `run_inventory(conn, file_key, file_name, frames, ...) -> dict`
> - `process_screen(conn, run_id, screen_id, figma_node_id, raw_response) -> dict`
> - `run_extraction_pipeline(conn, file_key, file_name, frames, extract_fn, ...) -> dict`
> - `complete_run(conn, run_id) -> dict`

### From dd/cluster.py (produced by TASK-034)

> Exports:
> - `run_clustering(conn, file_id, color_threshold, agent_id) -> dict`
> - `generate_summary(conn, file_id, results) -> dict`
> - `validate_no_orphan_tokens(conn, file_id) -> list[int]`

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `make_mock_figma_response(screen_name, node_count) -> list[dict]`

### From schema.sql -- All relevant views

> ```sql
> CREATE VIEW v_color_census AS
> SELECT ntb.resolved_value, COUNT(*) AS usage_count, COUNT(DISTINCT ntb.node_id) AS node_count,
>        GROUP_CONCAT(DISTINCT ntb.property) AS properties, s.file_id
> FROM node_token_bindings ntb JOIN nodes n ON ntb.node_id = n.id JOIN screens s ON n.screen_id = s.id
> WHERE ntb.property LIKE 'fill%' OR ntb.property LIKE 'stroke%'
> GROUP BY ntb.resolved_value, s.file_id ORDER BY usage_count DESC;
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
>
> CREATE VIEW v_resolved_tokens AS
> SELECT t.id, t.name, t.type, t.tier, t.collection_id, t.sync_status, t.figma_variable_id,
>        CASE WHEN t.alias_of IS NOT NULL THEN target.name ELSE NULL END AS alias_target_name,
>        tv.mode_id, tm.name AS mode_name,
>        COALESCE(target_tv.resolved_value, tv.resolved_value) AS resolved_value,
>        COALESCE(target_tv.raw_value, tv.raw_value) AS raw_value
> FROM tokens t LEFT JOIN tokens target ON t.alias_of = target.id
> LEFT JOIN token_values tv ON tv.token_id = t.id
> LEFT JOIN token_values target_tv ON target_tv.token_id = target.id AND target_tv.mode_id = tv.mode_id
> LEFT JOIN token_modes tm ON tm.id = tv.mode_id;
>
> CREATE VIEW v_unbound AS
> SELECT ntb.id AS binding_id, s.name AS screen_name, s.file_id,
>        n.name AS node_name, n.node_type, ntb.property, ntb.resolved_value
> FROM node_token_bindings ntb JOIN nodes n ON ntb.node_id = n.id JOIN screens s ON n.screen_id = s.id
> WHERE ntb.token_id IS NULL ORDER BY ntb.resolved_value;
> ```

### From schema.sql -- Key tables

> ```sql
> CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, file_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, ...);
> CREATE TABLE IF NOT EXISTS screens (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id), ...);
> CREATE TABLE IF NOT EXISTS nodes (id INTEGER PRIMARY KEY, screen_id INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE, ...);
> CREATE TABLE IF NOT EXISTS node_token_bindings (id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE, ...);
> CREATE TABLE IF NOT EXISTS tokens (id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id), ...);
> CREATE TABLE IF NOT EXISTS token_values (id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE, ...);
> CREATE TABLE IF NOT EXISTS token_collections (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id), ...);
> CREATE TABLE IF NOT EXISTS token_modes (id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE, ...);
> CREATE TABLE IF NOT EXISTS extraction_runs (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id), ...);
> ```

## Task

Create `tests/test_e2e_extract_cluster.py` -- the first end-to-end test covering Waves 0-3 (extraction through clustering). This test runs the REAL pipeline functions in sequence (not just asserts on seeded data) and verifies the final observable DB state. Use `@pytest.mark.e2e` and `@pytest.mark.slow` on all tests.

### Test Strategy

The e2e test should:
1. Start with an empty DB (initialized schema only).
2. Run the extraction pipeline with rich mock Figma data (enough nodes and visual properties to exercise all clustering types).
3. Run the clustering orchestrator.
4. Assert on the final DB state: tokens, values, bindings, census views.

### Mock Data

Create a comprehensive mock data set within the test file:

**Mock frames** (3 frames representing 2 phone screens + 1 component sheet):
```python
MOCK_FRAMES = [
    {"figma_node_id": "1:1", "name": "Home", "width": 428, "height": 926},
    {"figma_node_id": "1:2", "name": "Settings", "width": 428, "height": 926},
    {"figma_node_id": "1:3", "name": "Buttons and Controls", "width": 1200, "height": 800},
]
```

**Mock extraction responses** per screen (10-15 nodes each with fills, text, effects, spacing, radius):
- Home screen: Root FRAME with dark fill (#09090B), 2 TEXT children (Inter 16px, Inter 24px), 1 RECTANGLE with border (#D4D4D8) and radius 8, 1 FRAME with padding and spacing
- Settings screen: Similar structure with some overlapping colors (#09090B again, #FFFFFF) and different typography (Inter 14px)
- Component sheet: 1 root FRAME, 1 COMPONENT (skip for this test)

Each mock node must include enough properties to generate bindings: fills, strokes, effects, typography, spacing, and radius values.

### Test Functions

1. **`test_e2e_extraction_then_clustering(db)`**:
   - Build mock frames and extract_fn.
   - Call `run_extraction_pipeline(db, "e2e_test_key", "E2E Test File", MOCK_FRAMES, extract_fn)`.
   - Verify extraction completed:
     - `extraction_runs` has status="completed"
     - `nodes` table has rows
     - `node_token_bindings` has rows, all unbound
   - Call `run_clustering(db, file_id=1)`.
   - Verify final state:
     - `tokens` table has rows (at least color, spacing, radius tokens)
     - `token_values` table has rows matching tokens
     - Some bindings transitioned from "unbound" to "proposed"
     - No orphan tokens (every token has >= 1 binding)
     - Token names are unique within each collection
     - `v_curation_progress` shows both "proposed" and possibly "unbound" statuses

2. **`test_e2e_token_values_populated(db)`**:
   - Run full pipeline (extraction + clustering).
   - Verify `token_values`:
     - Every token has at least 1 token_value row
     - Every token_value has a non-empty resolved_value
     - Every token_value references a valid mode_id (with is_default=1)
     - `v_resolved_tokens` returns rows with resolved_value populated

3. **`test_e2e_bindings_updated_with_token_id(db)`**:
   - Run full pipeline.
   - Verify proposed bindings:
     - Proposed bindings have token_id IS NOT NULL
     - Proposed bindings have confidence IS NOT NULL and > 0
     - Every token_id in bindings exists in `tokens.id`
     - Binding resolved_value matches (or is within delta_e of) the token's resolved_value

4. **`test_e2e_census_views_accurate(db)`**:
   - Run full pipeline.
   - Query each census view and verify it returns accurate data:
     - `v_color_census`: returns hex values that match the mock fill/stroke data
     - `v_curation_progress`: percentages sum to ~100%
     - `v_token_coverage`: each token has binding_count > 0
     - `v_unbound`: returns only bindings with token_id IS NULL

5. **`test_e2e_no_orphan_bindings(db)`**:
   - Run full pipeline.
   - Verify:
     - No `node_token_bindings` rows reference a non-existent `nodes.id`
     - No `node_token_bindings` rows with token_id pointing to non-existent token
     - No `token_values` rows with token_id pointing to non-existent token
     - Full FK integrity across the chain: files -> screens -> nodes -> bindings -> tokens -> token_values

6. **`test_e2e_full_pipeline_summary(db)`**:
   - Run full pipeline.
   - Call `generate_summary(db, file_id=1, ...)` or extract summary from `run_clustering` return value.
   - Verify summary:
     - total_tokens > 0
     - total_bindings_updated > 0
     - coverage_pct > 0 (some bindings were assigned)
     - by_type dict has keys for at least "color"

### Helper Function

Create `_build_rich_mock_data()` that returns `(frames, extract_fn)` where extract_fn is a callable that returns appropriate mock node data for each screen_figma_node_id. The mock data must include:
- At least 2 unique fill colors (for color clustering to group/separate)
- At least 1 typography combination (for typography clustering)
- At least 2 unique spacing values (for spacing pattern detection)
- At least 1 radius value (for radius clustering)
- At least 1 DROP_SHADOW effect (for effect clustering, producing 5 bindings)

## Acceptance Criteria

- [ ] `pytest tests/test_e2e_extract_cluster.py -v` passes all tests
- [ ] At least 6 test functions
- [ ] All tests use both `@pytest.mark.e2e` and `@pytest.mark.slow` markers
- [ ] Tests run REAL pipeline functions (run_extraction_pipeline, run_clustering), not just assert on seeded data
- [ ] Tests start from empty DB (init_db only), not pre-seeded state
- [ ] Mock data is rich enough to exercise all 5 clustering types
- [ ] Final state assertions cover: tokens, token_values, bindings, census views, FK integrity
- [ ] No orphan tokens or invalid FK references in final state
- [ ] Coverage_pct > 0 in the summary (some bindings assigned)
- [ ] `pytest tests/test_e2e_extract_cluster.py -v --tb=short` exits 0
- [ ] Tests complete within 30 seconds (pytest-timeout)

## Notes

- This is the FIRST e2e test in the project. It covers Waves 0-3: schema initialization, extraction, normalization, binding creation, path computation, and clustering.
- The mock extract_fn simulates what an agent with MCP access would do: it takes a screen_figma_node_id and returns a list of node dicts. This is the ONLY mock -- all other pipeline functions run for real.
- The mock data should be realistic but minimal. Don't create 200 nodes per screen -- 10-15 is enough to test all code paths.
- The test needs to handle the fact that `run_extraction_pipeline` expects frames with `figma_node_id` keys and the extract_fn maps those to responses.
- Use `@pytest.mark.timeout(30)` on all tests. The full pipeline should complete in seconds with mock data.
- Import from both `dd.extract` and `dd.cluster` -- these are the two main entry points being tested end-to-end.