---
taskId: TASK-045
title: "Write e2e test: extraction through validation gate"
wave: wave-4
testFirst: true
testLevel: e2e
dependencies: [TASK-007, TASK-041, TASK-037]
produces:
  - tests/test_e2e_extract_validate.py
verify:
  - type: test
    command: 'pytest tests/test_e2e_extract_validate.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-045: Write e2e test: extraction through validation gate

## Spec Context

### From Task Decomposition Guide -- Wave 4 Test Description

> TASK-045: Write e2e test: extraction through validation gate -- fixture DB -> extraction with mocks -> clustering -> curation (accept all) -> validation -> verify: all 7 validation checks pass, curation_progress view shows 100%, export_readiness view returns ready; this is the pre-export gate e2e.

### From Task Decomposition Guide -- E2E Test Requirements

> E2E test tasks (wave 3+) MUST:
> - Run the real pipeline functions in sequence, not just assert on pre-seeded state
> - Start from `seed_post_extraction()` fixture at minimum, execute forward through current wave
> - Assert on final observable state (DB contents, export file contents) not intermediate calls
> - Be marked with both @pytest.mark.e2e and @pytest.mark.slow

### From dd/extract.py (produced by TASK-014)

> Exports:
> - `run_extraction_pipeline(conn, file_key, file_name, frames, extract_fn, ...) -> dict`

### From dd/cluster.py (produced by TASK-034)

> Exports:
> - `run_clustering(conn, file_id, color_threshold, agent_id) -> dict`

### From dd/curate.py (produced by TASK-040)

> Exports:
> - `accept_all(conn, file_id, db_path=None) -> dict`
> - `accept_token(conn, token_id) -> dict`
> - `rename_token(conn, token_id, new_name) -> dict`

### From dd/validate.py (produced by TASK-041)

> Exports:
> - `run_validation(conn, file_id) -> dict`
> - `is_export_ready(conn) -> bool`

### From dd/status.py (produced by TASK-042)

> Exports:
> - `get_curation_progress(conn) -> list[dict]`
> - `get_status_dict(conn, file_id=None) -> dict`
> - `format_status_report(conn, file_id=None) -> str`

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `make_mock_figma_response(screen_name, node_count) -> list[dict]`

### From schema.sql -- Key views

> ```sql
> CREATE VIEW v_curation_progress AS
> SELECT binding_status, COUNT(*) AS binding_count,
>        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM node_token_bindings), 1) AS pct
> FROM node_token_bindings GROUP BY binding_status;
>
> CREATE VIEW v_export_readiness AS
> SELECT check_name, severity, COUNT(*) AS issue_count, SUM(resolved) AS resolved_count
> FROM export_validations
> WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
> GROUP BY check_name, severity
> ORDER BY CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END;
>
> CREATE VIEW v_token_coverage AS
> SELECT t.name AS token_name, t.type AS token_type, t.tier, t.collection_id,
>        COUNT(ntb.id) AS binding_count, COUNT(DISTINCT ntb.node_id) AS node_count,
>        COUNT(DISTINCT n.screen_id) AS screen_count
> FROM tokens t LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
> LEFT JOIN nodes n ON ntb.node_id = n.id GROUP BY t.id ORDER BY binding_count DESC;
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
> ```

### From schema.sql -- All relevant tables

> ```sql
> CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, file_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, ...);
> CREATE TABLE IF NOT EXISTS screens (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id), ...);
> CREATE TABLE IF NOT EXISTS nodes (id INTEGER PRIMARY KEY, screen_id INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE, ...);
> CREATE TABLE IF NOT EXISTS node_token_bindings (id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE, ...);
> CREATE TABLE IF NOT EXISTS token_collections (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id), ...);
> CREATE TABLE IF NOT EXISTS token_modes (id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE, ...);
> CREATE TABLE IF NOT EXISTS tokens (id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id), ...);
> CREATE TABLE IF NOT EXISTS token_values (id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE, ...);
> CREATE TABLE IF NOT EXISTS export_validations (id INTEGER PRIMARY KEY, run_at TEXT NOT NULL, check_name TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL, affected_ids TEXT, resolved INTEGER NOT NULL DEFAULT 0);
> CREATE TABLE IF NOT EXISTS extraction_runs (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id), ...);
> ```

## Task

Create `tests/test_e2e_extract_validate.py` -- the pre-export gate e2e test covering Waves 0-4 (extraction through validation). This test runs the ENTIRE pipeline from extraction through clustering, curation, and validation, verifying the final DB state is export-ready. Use `@pytest.mark.e2e` and `@pytest.mark.slow` on all tests.

### Mock Data

Build comprehensive mock data within the test file that exercises all pipeline stages:

**Mock frames** (3 screens):
```python
MOCK_FRAMES = [
    {"figma_node_id": "1:1", "name": "Home", "width": 428, "height": 926},
    {"figma_node_id": "1:2", "name": "Profile", "width": 428, "height": 926},
    {"figma_node_id": "1:3", "name": "Components", "width": 1200, "height": 800},
]
```

**Mock extraction responses** -- each screen should generate nodes with enough visual properties to produce bindings for all 5 clustering types:
- Fill colors: at least 3 unique colors (#09090B, #18181B, #FFFFFF) used across multiple nodes
- Typography: at least 2 unique type combos (Inter/600/24px, Inter/400/14px)
- Spacing: at least 2 unique values (8, 16) used as padding and itemSpacing
- Radius: at least 2 unique values (8, 12)
- Effects: at least 1 DROP_SHADOW (producing 5 bindings)

### Test Functions

1. **`test_e2e_full_pipeline_to_validation_pass(db)`**:
   - Start with empty schema-initialized DB.
   - Run extraction pipeline with mock data.
   - Run clustering.
   - Run accept_all (promote all tokens to curated, all bindings to bound).
   - Run validation.
   - Verify final state:
     - `run_validation` returns `{"passed": True}`
     - `is_export_ready` returns True
     - All 7 validation checks executed (rows in export_validations)
     - No error-severity rows in export_validations
     - `v_export_readiness` view shows no errors

2. **`test_e2e_all_validation_checks_executed(db)`**:
   - Run full pipeline (extraction -> clustering -> accept_all -> validation).
   - Query export_validations for the latest run_at.
   - Verify all 7 check names are present: mode_completeness, name_dtcg_compliant, orphan_tokens, binding_coverage, alias_targets_curated, name_uniqueness, value_format.
   - Each check produced at least 1 row (even if it's just info-level for binding_coverage).

3. **`test_e2e_curation_progress_shows_bound(db)`**:
   - Run full pipeline through accept_all.
   - Query `v_curation_progress`.
   - Verify:
     - 'bound' status has binding_count > 0
     - 'bound' pct > 0
     - If any bindings remain unbound (e.g., opacity=1.0 was skipped, or gradient fills), they're accounted for
     - Total percentage across all statuses sums to approximately 100%

4. **`test_e2e_token_values_complete_for_all_modes(db)`**:
   - Run full pipeline.
   - Verify:
     - Every non-aliased token has at least 1 token_value row
     - Every token's collection has a default mode
     - Every token_value references a valid mode and token
     - `v_resolved_tokens` returns resolved_value for every token

5. **`test_e2e_export_readiness_view_returns_ready(db)`**:
   - Run full pipeline.
   - Query `v_export_readiness`.
   - Verify:
     - View returns rows (validation has been run)
     - No rows with severity='error' (or if error rows exist, they're resolved)
     - The view correctly groups by check_name and severity

6. **`test_e2e_fk_integrity_across_full_pipeline(db)`**:
   - Run full pipeline.
   - Verify complete FK integrity chain:
     - Every `screens.file_id` exists in `files.id`
     - Every `nodes.screen_id` exists in `screens.id`
     - Every `nodes.parent_id` (non-NULL) exists in `nodes.id`
     - Every `node_token_bindings.node_id` exists in `nodes.id`
     - Every `node_token_bindings.token_id` (non-NULL) exists in `tokens.id`
     - Every `tokens.collection_id` exists in `token_collections.id`
     - Every `token_collections.file_id` exists in `files.id`
     - Every `token_values.token_id` exists in `tokens.id`
     - Every `token_values.mode_id` exists in `token_modes.id`
     - Every `token_modes.collection_id` exists in `token_collections.id`
   - Use explicit SQL for each check: `SELECT COUNT(*) FROM X WHERE fk_col NOT IN (SELECT id FROM Y)` should all be 0.

7. **`test_e2e_status_report_after_full_pipeline(db)`**:
   - Run full pipeline.
   - Call `format_status_report(db, file_id=1)`.
   - Verify:
     - Report is a non-empty string
     - Contains "Curation Progress" section
     - Contains "Export Readiness" section
     - Does NOT contain "not yet validated" (since validation was run)
   - Call `get_status_dict(db, file_id=1)`.
   - Verify:
     - `is_ready` is True
     - `token_count` > 0
     - `unbound_count` >= 0

8. **`test_e2e_pipeline_without_curation_fails_validation(db)`**:
   - Run extraction pipeline.
   - Run clustering (tokens created as 'extracted', bindings as 'proposed').
   - DO NOT run curation (no accept_all).
   - Run validation.
   - Verify:
     - Validation may pass if there are no alias issues (extracted tokens are valid).
     - But if we then create an alias to an extracted token, validation should flag it.
   - Alternatively, verify `v_curation_progress` shows 0% bound (all still proposed).
   - The point: the pipeline state after clustering is valid for exploration but NOT for export if aliases reference extracted tokens.

### Helper Function

Create `_build_e2e_mock_data()` that returns `(frames, extract_fn)`. The extract_fn returns node lists per screen with:
- Screen "Home": root FRAME (dark fill #09090B, padding 16, itemSpacing 8), 2 TEXT children (Inter 600 24px, Inter 400 14px), 1 RECTANGLE (fill #FFFFFF, radius 8, DROP_SHADOW), 1 FRAME with stroke (#18181B)
- Screen "Profile": root FRAME (fill #09090B), 1 TEXT (Inter 400 14px), 1 RECTANGLE (fill #18181B, radius 12)
- Screen "Components": root FRAME (no fill), 1 COMPONENT child (minimal)

Ensure at least 20 total bindings across all screens to give clustering meaningful data.

## Acceptance Criteria

- [ ] `pytest tests/test_e2e_extract_validate.py -v` passes all tests
- [ ] At least 8 test functions
- [ ] All tests use both `@pytest.mark.e2e` and `@pytest.mark.slow` markers
- [ ] Tests run REAL pipeline functions in sequence: extraction -> clustering -> curation -> validation
- [ ] Tests start from empty DB (init_db only), execute the full pipeline
- [ ] Mock data is rich enough to produce bindings for all 5 clustering types (color, typography, spacing, radius, effects)
- [ ] Final state: all 7 validation checks executed and reported
- [ ] Final state: `is_export_ready` returns True after full curation
- [ ] Final state: `v_curation_progress` shows bound bindings
- [ ] Final state: complete FK integrity across all tables
- [ ] Status report generated and contains expected sections
- [ ] Tests complete within 30 seconds (pytest-timeout)
- [ ] `pytest tests/test_e2e_extract_validate.py -v --tb=short` exits 0

## Notes

- This is the pre-export gate e2e test. It proves that the entire pipeline from raw Figma data to export-readiness works end-to-end.
- The mock extract_fn is the ONLY mock. All Python pipeline code runs for real: extraction, normalization, binding creation, path computation, clustering, curation, and validation.
- The mock data must produce enough variety to exercise all 5 clustering modules. A minimum of 20 bindings across 3+ screens with 3+ unique colors, 2+ type scales, 2+ spacing values, 2+ radius values, and 1+ shadow effect.
- Each mock node dict must include all keys that the extraction pipeline expects: `figma_node_id`, `parent_idx`, `name`, `node_type`, `depth`, `sort_order`, `x`, `y`, `width`, `height`, and visual properties as appropriate.
- The e2e test that includes "no curation" (test 8) demonstrates the pipeline's progression: extraction -> clustering produces a valid but un-curated state, and curation is needed before export.
- Use `@pytest.mark.timeout(30)` on all tests. With mock data and in-memory DB, the full pipeline should complete in under 5 seconds.