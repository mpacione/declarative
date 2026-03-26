---
taskId: TASK-074
title: "Write e2e smoke test: full pipeline including drift + modes"
wave: wave-7
testFirst: false
testLevel: e2e
dependencies: [TASK-007, TASK-073, TASK-065]
produces:
  - tests/test_e2e_full.py
verify:
  - type: test
    command: 'pytest tests/test_e2e_full.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-074: Write e2e smoke test: full pipeline including drift + modes

## Spec Context

### From Task Decomposition Guide -- Wave 7 Test Description

> TASK-074: Write e2e smoke test: full pipeline including drift + modes -- fixture DB -> extraction -> clustering -> curation -> validation -> all exports -> create dark mode (OKLCH inversion) -> simulate drift (modify fixture values) -> run drift detection -> verify: drift report surfaces changed tokens, mode values seeded correctly, full test suite regression via `pytest tests/ -v` as final gate.

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

### From dd/validate.py (produced by TASK-041)

> Exports:
> - `run_validation(conn, file_id) -> dict`
> - `is_export_ready(conn) -> bool`

### From dd/export_figma_vars.py (produced by TASK-050, TASK-051)

> Exports:
> - `generate_variable_payloads(conn, file_id) -> list[dict]`
> - `dtcg_to_figma_path(name) -> str`
> - `figma_path_to_dtcg(name) -> str`

### From dd/export_css.py (produced by TASK-060)

> Exports:
> - `generate_css(conn, file_id) -> str`
> - `export_css(conn, file_id) -> dict`

### From dd/export_tailwind.py (produced by TASK-061)

> Exports:
> - `generate_tailwind_config(conn, file_id) -> str`
> - `export_tailwind(conn, file_id) -> dict`

### From dd/export_dtcg.py (produced by TASK-062)

> Exports:
> - `generate_dtcg_json(conn, file_id) -> str`
> - `generate_dtcg_dict(conn, file_id) -> dict`
> - `export_dtcg(conn, file_id) -> dict`

### From dd/export_rebind.py (produced by TASK-052)

> Exports:
> - `generate_rebind_scripts(conn, file_id) -> list[str]`

### From dd/modes.py (produced by TASK-072)

> Exports:
> - `create_mode(conn, collection_id, mode_name) -> int`
> - `copy_values_from_default(conn, collection_id, new_mode_id) -> int`
> - `apply_oklch_inversion(conn, collection_id, mode_id) -> int`
> - `create_dark_mode(conn, collection_id, mode_name) -> dict`
> - `create_theme(conn, file_id, theme_name, collection_ids, transform, factor) -> dict`

### From dd/drift.py (produced by TASK-070)

> Exports:
> - `detect_drift(conn, file_id, figma_variables_response) -> dict`
> - `detect_drift_readonly(conn, file_id, figma_variables_response) -> dict`
> - `compare_token_values(conn, file_id, figma_variables) -> dict`
> - `parse_figma_variables_for_drift(raw_response) -> list[dict]`
> - `generate_drift_report(conn, file_id) -> dict`

### From dd/status.py (produced by TASK-042)

> Exports:
> - `format_status_report(conn, file_id) -> str`
> - `get_status_dict(conn, file_id) -> dict`

### From schema.sql -- Key tables and views

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id),
>     name TEXT NOT NULL, type TEXT NOT NULL,
>     tier TEXT NOT NULL DEFAULT 'extracted', alias_of INTEGER REFERENCES tokens(id),
>     figma_variable_id TEXT,
>     sync_status TEXT NOT NULL DEFAULT 'pending', ... UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS token_values (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, ... UNIQUE(token_id, mode_id)
> );
> CREATE TABLE IF NOT EXISTS token_modes (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
>     figma_mode_id TEXT, name TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0,
>     UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS token_collections (
>     id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id),
>     figma_id TEXT, name TEXT NOT NULL, ...
> );
> CREATE TABLE IF NOT EXISTS code_mappings (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     target TEXT NOT NULL, identifier TEXT NOT NULL, file_path TEXT,
>     UNIQUE(token_id, target, identifier)
> );
>
> CREATE VIEW v_drift_report AS
> SELECT t.id AS token_id, t.name AS token_name, t.type, t.sync_status,
>        t.figma_variable_id, tv.resolved_value AS db_value,
>        tm.name AS mode_name, tc.name AS collection_name
> FROM tokens t
> JOIN token_values tv ON tv.token_id = t.id
> JOIN token_modes tm ON tm.id = tv.mode_id
> JOIN token_collections tc ON tc.id = t.collection_id
> WHERE t.sync_status IN ('pending', 'drifted', 'figma_only', 'code_only')
> ORDER BY t.sync_status, tc.name, t.name;
>
> CREATE VIEW v_curation_progress AS
> SELECT binding_status, COUNT(*) AS binding_count,
>        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM node_token_bindings), 1) AS pct
> FROM node_token_bindings GROUP BY binding_status;
>
> CREATE VIEW v_export_readiness AS
> SELECT check_name, severity, COUNT(*) AS issue_count, SUM(resolved) AS resolved_count
> FROM export_validations
> WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
> GROUP BY check_name, severity;
>
> CREATE VIEW v_token_coverage AS
> SELECT t.name AS token_name, t.type AS token_type, t.tier, t.collection_id,
>        COUNT(ntb.id) AS binding_count
> FROM tokens t LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
> GROUP BY t.id ORDER BY binding_count DESC;
> ```

## Task

Create `tests/test_e2e_full.py` -- the final e2e smoke test covering the entire pipeline (Waves 0-7). This test runs the COMPLETE pipeline from extraction through clustering, curation, validation, all exports, dark mode creation with OKLCH inversion, simulated drift detection, and verifies the final DB state. This is the comprehensive regression gate for the entire project. Use `@pytest.mark.e2e` and `@pytest.mark.slow` on all tests.

### Mock Data

Build comprehensive mock data that exercises the full pipeline. Reuse the mock data pattern from TASK-065 (Wave 6 e2e) with at least:
- 3 screens (2 iPhone + 1 component sheet)
- Fill colors: 3+ unique colors (#09090B, #18181B, #FFFFFF)
- Stroke color: 1+ (#D4D4D8)
- Typography: 2+ combos (Inter/600/24px, Inter/400/14px)
- Spacing: 2+ values (8, 16)
- Radius: 2+ values (8, 12)
- Effects: 1+ DROP_SHADOW
- Enough nodes per screen to generate meaningful bindings (5+ nodes each)

### Test Functions

1. **`test_e2e_full_pipeline_smoke(db)`**:
   - Run the COMPLETE pipeline end-to-end:
     a. **Extraction**: `run_extraction_pipeline(db, "e2e_key", "E2E File", frames, extract_fn)`
     b. **Clustering**: `run_clustering(db, file_id=1)`
     c. **Curation**: `accept_all(db, file_id=1)`
     d. **Validation**: `run_validation(db, file_id=1)` -- verify passes
     e. **CSS export**: `export_css(db, file_id=1)` -- verify non-empty CSS
     f. **Tailwind export**: `export_tailwind(db, file_id=1)` -- verify non-empty config
     g. **DTCG export**: `export_dtcg(db, file_id=1)` -- verify valid JSON
     h. **Figma payloads**: `generate_variable_payloads(db, file_id=1)` -- verify non-empty list
   - Verify final state:
     - `is_export_ready(db)` returns True
     - Tokens exist in DB with tier='curated'
     - Bindings have binding_status='bound'
     - Code mappings exist for css, tailwind, dtcg targets
     - All exports produce non-empty output

2. **`test_e2e_dark_mode_creation_and_export(db)`**:
   - Run full pipeline through curation (extraction -> clustering -> accept_all).
   - Find the Colors collection ID: `SELECT id FROM token_collections WHERE file_id = 1 AND name = 'Colors'` (or whatever name the clustering created).
   - Create dark mode: `create_dark_mode(db, collection_id)`.
   - Verify dark mode:
     - New mode exists in `token_modes` with name='Dark', is_default=0
     - Every non-aliased color token has a token_value for the Dark mode
     - Dark mode values are different from Default mode values (OKLCH inversion changed them)
     - Dark mode color for a dark color (like #09090B, low lightness) should be lighter
     - Dark mode color for white (#FFFFFF, high lightness) should be darker
   - Run validation again: verify passes (mode_completeness should pass since Dark values were created for all tokens).
   - Generate CSS: verify output contains `[data-theme="Dark"]` block with Dark mode values.
   - Generate DTCG JSON: verify output contains `$extensions` with Dark mode values.
   - Generate Figma payloads: verify payloads include both Default and Dark modes.

3. **`test_e2e_drift_detection_synced(db)`**:
   - Run full pipeline through Figma payload generation.
   - Simulate export: set `figma_variable_id` on all curated tokens.
   - Build a mock Figma response that matches all DB token values exactly.
   - Run `detect_drift(db, file_id=1, mock_response)`.
   - Verify:
     - All tokens marked as 'synced' in DB
     - Drift report shows 0 drifted tokens
     - `v_drift_report` returns 0 rows (all synced, view filters on non-synced)

4. **`test_e2e_drift_detection_drifted(db)`**:
   - Run full pipeline through Figma payload generation.
   - Simulate export: set `figma_variable_id` on all curated tokens.
   - Build a mock Figma response with MODIFIED values for 2 tokens (change the hex color to simulate someone editing in Figma).
   - Run `detect_drift(db, file_id=1, mock_response)`.
   - Verify:
     - 2 tokens marked as 'drifted' in DB
     - Remaining tokens marked as 'synced'
     - Drift report shows exactly 2 drifted tokens
     - Each drifted token entry includes both db_value and figma_value
     - `v_drift_report` returns rows for drifted tokens

5. **`test_e2e_mode_values_seeded_correctly(db)`**:
   - Run full pipeline through curation.
   - Create dark mode on Colors collection.
   - Create compact mode on Spacing collection (if exists) with factor=0.75.
   - Verify:
     - Dark mode color values: each is a valid hex string, different from Default values
     - Compact mode spacing values: each is 75% of the Default value (e.g., 16 -> 12)
     - Mode values are independent: modifying a Dark value doesn't change Default
   - Verify independence by reading Default values, updating a Dark value manually, re-reading Default to confirm unchanged.

6. **`test_e2e_full_pipeline_fk_integrity(db)`**:
   - Run the COMPLETE pipeline (extraction -> clustering -> curation -> validation -> all exports -> dark mode -> drift).
   - Verify FK integrity across ALL tables:
     - files -> screens -> nodes -> node_token_bindings -> tokens -> token_values -> token_modes -> token_collections
     - code_mappings -> tokens
     - export_validations (no FK but check run_at consistency)
     - extraction_runs -> files, screen_extraction_status -> extraction_runs + screens
   - Use explicit SQL for each check:
     ```sql
     SELECT COUNT(*) FROM nodes WHERE screen_id NOT IN (SELECT id FROM screens)
     SELECT COUNT(*) FROM node_token_bindings WHERE node_id NOT IN (SELECT id FROM nodes)
     SELECT COUNT(*) FROM node_token_bindings WHERE token_id IS NOT NULL AND token_id NOT IN (SELECT id FROM tokens)
     SELECT COUNT(*) FROM token_values WHERE token_id NOT IN (SELECT id FROM tokens)
     SELECT COUNT(*) FROM token_values WHERE mode_id NOT IN (SELECT id FROM token_modes)
     SELECT COUNT(*) FROM tokens WHERE collection_id NOT IN (SELECT id FROM token_collections)
     SELECT COUNT(*) FROM token_modes WHERE collection_id NOT IN (SELECT id FROM token_collections)
     SELECT COUNT(*) FROM code_mappings WHERE token_id NOT IN (SELECT id FROM tokens)
     ```
   - All must return 0.

7. **`test_e2e_final_status_report(db)`**:
   - Run full pipeline including dark mode and drift detection (all synced).
   - Generate status report via `format_status_report(db, file_id=1)`.
   - Verify report is a non-empty string containing:
     - "Curation Progress" section
     - "bound" with a count > 0
     - "Export Readiness" section
   - Generate status dict via `get_status_dict(db, file_id=1)`.
   - Verify:
     - `is_ready` is True
     - `token_count` > 0
     - `curation_progress` contains entries for 'bound'

8. **`test_e2e_multimode_export_consistency(db)`**:
   - Run full pipeline through curation.
   - Create dark mode on color collection.
   - Generate all exports.
   - Verify multi-mode consistency:
     - CSS has both `:root` (Default) and `[data-theme="Dark"]` blocks
     - DTCG JSON has `$extensions.org.design-tokens.modes.Dark` for color tokens
     - Figma payloads have `modes: ["Default", "Dark"]` for color collection
     - Default mode values in CSS match Default mode values in DTCG
     - Dark mode values in CSS `[data-theme="Dark"]` block match DTCG extensions
   - For non-color collections (spacing, radius), verify:
     - Only Default mode values present (no Dark mode was added to these)

### Helper Functions

Create within the test file:

- `_build_e2e_mock_data()`: Returns `(frames, extract_fn)` with rich mock data covering all property types. Same pattern as TASK-065 helper.
- `_simulate_figma_export(db, file_id)`: Sets `figma_variable_id` on all curated tokens. Returns a mock Figma response dict with matching values.
- `_build_drifted_figma_response(db, file_id, drift_tokens: dict)`: Builds a mock Figma response where specified tokens have different values. `drift_tokens` maps token_name -> modified_value.
- `_count_css_vars_in_block(css: str, block_selector: str) -> int`: Count CSS variables within a specific block (`:root` or `[data-theme="Dark"]`).
- `_navigate_dtcg_path(dtcg_dict: dict, path: str) -> dict | None`: Navigate nested DTCG dict by dot-path.

## Acceptance Criteria

- [ ] `pytest tests/test_e2e_full.py -v` passes all tests
- [ ] At least 8 test functions
- [ ] All tests use both `@pytest.mark.e2e` and `@pytest.mark.slow` markers
- [ ] Tests run the REAL full pipeline: extraction -> clustering -> curation -> validation -> all 4 exports -> dark mode -> drift detection
- [ ] Tests start from empty DB (init_db only), execute the COMPLETE pipeline
- [ ] Full pipeline smoke test verifies all stages produce output
- [ ] Dark mode test verifies OKLCH inversion produces lighter versions of dark colors and darker versions of light colors
- [ ] Drift detection test verifies synced state with matching values
- [ ] Drift detection test verifies drifted state with modified values, showing both db_value and figma_value
- [ ] Mode values seeded correctly: dark mode colors inverted, compact spacing scaled
- [ ] FK integrity verified across ALL tables after full pipeline execution
- [ ] Multi-mode export consistency: CSS, DTCG, and Figma payloads agree on mode values
- [ ] Status report generated with expected sections
- [ ] Tests complete within 30 seconds (pytest-timeout)
- [ ] `pytest tests/test_e2e_full.py -v --tb=short` exits 0
- [ ] This test serves as the final regression gate: if it passes, the entire pipeline is functional

## Notes

- This is the FINAL and most comprehensive e2e test in the project. It covers ALL 8 waves (0-7) and validates the entire pipeline from raw Figma data to exports, mode creation, and drift detection.
- The ONLY mock is the `extract_fn` that simulates Figma MCP responses and the mock Figma variables response for drift detection. All Python pipeline code runs for real.
- The dark mode test should verify that OKLCH inversion actually changes values meaningfully. A dark color like #09090B (L~0.15) should invert to something with L~0.85 (light). White #FFFFFF (L~1.0) should invert to near-black.
- The drift detection tests simulate what happens in production: tokens are exported to Figma (simulated by setting figma_variable_id), then someone edits a value in Figma (simulated by a modified mock response), and drift detection catches the change.
- Each test function should run the full pipeline independently using the `db` fixture for a fresh DB. This means each test takes a few seconds but ensures complete isolation.
- Use `@pytest.mark.timeout(30)` on all tests. The full pipeline with mock data should complete in under 15 seconds per test.
- This test file imports from nearly every `dd/` module. Ensure all imports are at the top of the file for clarity.