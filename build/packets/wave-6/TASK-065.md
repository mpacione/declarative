---
taskId: TASK-065
title: "Write e2e test: full pipeline through all exports"
wave: wave-6
testFirst: true
testLevel: e2e
dependencies: [TASK-007, TASK-062, TASK-055]
produces:
  - tests/test_e2e_full_export.py
verify:
  - type: test
    command: 'pytest tests/test_e2e_full_export.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-065: Write e2e test: full pipeline through all exports

## Spec Context

### From Task Decomposition Guide -- Wave 6 Test Description

> TASK-065: Write e2e test: full pipeline through all exports -- fixture DB -> extraction -> clustering -> curation -> validation -> CSS + Tailwind + DTCG + Figma payloads -> verify: all 4 export formats produced, token counts consistent across formats, round-trip: DTCG JSON re-importable, CSS vars match DTCG values; this is the comprehensive e2e covering waves 0-6.

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
> - `generate_variable_payloads_checked(conn, file_id) -> list[dict]`

### From dd/export_css.py (produced by TASK-060)

> Exports:
> - `generate_css(conn, file_id: int) -> str`
> - `export_css(conn, file_id: int) -> dict`

### From dd/export_tailwind.py (produced by TASK-061)

> Exports:
> - `generate_tailwind_config(conn, file_id: int) -> str`
> - `generate_tailwind_config_dict(conn, file_id: int) -> dict`
> - `export_tailwind(conn, file_id: int) -> dict`

### From dd/export_dtcg.py (produced by TASK-062)

> Exports:
> - `generate_dtcg_json(conn, file_id: int, indent: int = 2) -> str`
> - `generate_dtcg_dict(conn, file_id: int) -> dict`
> - `export_dtcg(conn, file_id: int) -> dict`

### From dd/export_rebind.py (produced by TASK-052)

> Exports:
> - `generate_rebind_scripts(conn, file_id) -> list[str]`
> - `get_rebind_summary(conn, file_id) -> dict`

### From dd/status.py (produced by TASK-042)

> Exports:
> - `format_status_report(conn, file_id=None) -> str`
> - `get_status_dict(conn, file_id=None) -> dict`

### From schema.sql -- Key tables and views

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id),
>     name TEXT NOT NULL, type TEXT NOT NULL,
>     tier TEXT NOT NULL DEFAULT 'extracted', alias_of INTEGER REFERENCES tokens(id),
>     figma_variable_id TEXT, sync_status TEXT NOT NULL DEFAULT 'pending',
>     ... UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS token_values (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, ... UNIQUE(token_id, mode_id)
> );
> CREATE TABLE IF NOT EXISTS code_mappings (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     target TEXT NOT NULL, identifier TEXT NOT NULL, file_path TEXT, extracted_at TEXT,
>     UNIQUE(token_id, target, identifier)
> );
> CREATE TABLE IF NOT EXISTS node_token_bindings (
>     id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
>     property TEXT NOT NULL, token_id INTEGER REFERENCES tokens(id),
>     binding_status TEXT NOT NULL DEFAULT 'unbound', ... UNIQUE(node_id, property)
> );
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

Create `tests/test_e2e_full_export.py` -- the comprehensive e2e test covering Waves 0-6 (extraction through all export formats). This test runs the ENTIRE pipeline from extraction through clustering, curation, validation, and all 4 export formats (CSS, Tailwind, DTCG, Figma payloads). It verifies cross-format consistency and that the DTCG JSON is re-importable. Use `@pytest.mark.e2e` and `@pytest.mark.slow` on all tests.

### Mock Data

Build comprehensive mock data that exercises all pipeline stages and all export formats. Reuse or adapt the mock data from TASK-055 (Wave 5 e2e), ensuring variety across all token types:

- Fill colors: 3+ unique colors (#09090B, #18181B, #FFFFFF)
- Stroke colors: 1+ (#D4D4D8)
- Typography: 2+ combos (Inter/600/24px with line-height 30, Inter/400/14px with line-height 20)
- Spacing: 2+ values (8, 16 as padding and itemSpacing)
- Radius: 2+ values (8, 12)
- Effects: 1+ DROP_SHADOW (color, radius, offsetX, offsetY, spread)

This ensures all 3 code exporters have diverse token types to process.

### Test Functions

1. **`test_e2e_all_four_export_formats_produced(db)`**:
   - Run full pipeline: extraction -> clustering -> accept_all -> validation -> all exports.
   - Verify all 4 formats produce non-empty output:
     - CSS: `generate_css(db, 1)` returns non-empty string containing `:root`
     - Tailwind: `generate_tailwind_config(db, 1)` returns non-empty string containing `module.exports`
     - DTCG: `generate_dtcg_json(db, 1)` returns non-empty string parseable by `json.loads`
     - Figma: `generate_variable_payloads(db, 1)` returns non-empty list
   - Verify validation passed before exports: `is_export_ready(db)` returns True.

2. **`test_e2e_token_counts_consistent_across_formats(db)`**:
   - Run full pipeline through all exports.
   - Count curated tokens in DB: `SELECT COUNT(*) FROM tokens t JOIN token_collections tc ON t.collection_id = tc.id WHERE tc.file_id = 1 AND t.tier IN ('curated', 'aliased')`.
   - Count in CSS: parse `:root` block, count `--var: value;` lines.
   - Count in DTCG: traverse nested dict, count leaf nodes with `$value`.
   - Count in Figma payloads: sum all tokens across all payloads.
   - Verify: DB count == DTCG count == Figma count.
   - CSS count should be >= DB count (may include alias var() entries).
   - Tailwind count may differ slightly (some token types may not map to Tailwind sections), but all color tokens must be present.

3. **`test_e2e_dtcg_json_round_trip(db)`**:
   - Run full pipeline through DTCG export.
   - Generate DTCG JSON string.
   - Parse with `json.loads` -> dict.
   - Re-serialize with `json.dumps` -> string.
   - Re-parse with `json.loads` -> dict2.
   - Verify dict == dict2 (round-trip fidelity).
   - Verify the parsed dict has proper DTCG structure:
     - Every leaf node has `$type` and `$value`
     - No `$type` values are None or empty
     - No `$value` values are None

4. **`test_e2e_css_vars_match_dtcg_values(db)`**:
   - Run full pipeline through CSS + DTCG export.
   - For each curated color token:
     - Extract value from CSS (parse `--color-surface-primary: #09090B;`)
     - Extract value from DTCG JSON (navigate dict to `color.surface.primary.$value`)
     - Verify they match (both hex strings should be identical).
   - For dimension tokens:
     - CSS value is `16px`, DTCG value is `{"value": 16, "unit": "px"}`.
     - Extract the numeric portion from CSS (`16`) and compare to DTCG value.value (`16`).

5. **`test_e2e_figma_payloads_match_code_exports(db)`**:
   - Run full pipeline through all exports.
   - For each token in Figma payloads:
     - Convert Figma name back to DTCG: `name.replace("/", ".")`
     - Find matching token in DTCG JSON by path
     - Verify the Figma payload value matches the DTCG $value for the default mode.

6. **`test_e2e_code_mappings_complete(db)`**:
   - Run full pipeline, call all 3 code exporters (export_css, export_tailwind, export_dtcg).
   - Query `code_mappings` table.
   - Verify:
     - Rows exist for target='css', target='tailwind', target='dtcg'
     - Every curated token has at least 1 mapping per target
     - All `code_mappings.token_id` references valid `tokens.id`
     - Total mapping count is >= 3 * curated_token_count (at least 1 per target per token)

7. **`test_e2e_full_pipeline_status_report(db)`**:
   - Run full pipeline through all exports.
   - Generate status report via `format_status_report(db, file_id=1)`.
   - Verify report contains:
     - "Curation Progress" with "bound" entries
     - "Export Readiness" with PASS or no errors
   - Generate status dict via `get_status_dict(db, file_id=1)`.
   - Verify:
     - `is_ready` is True
     - `token_count` > 0
     - `curation_progress` has entries

8. **`test_e2e_rebind_scripts_after_figma_export(db)`**:
   - Run full pipeline through Figma payload generation.
   - Simulate writeback: set `figma_variable_id` on all curated tokens.
   - Generate rebind scripts.
   - Verify:
     - At least 1 script generated
     - Each script is a non-empty string
     - Total bindings in scripts matches bound bindings with figma_variable_id in DB
     - `get_rebind_summary` reports total_bindings > 0

### Helper Functions

Create `_build_full_e2e_mock_data()` returning `(frames, extract_fn)`:

```python
def _build_full_e2e_mock_data():
    """Build mock data for comprehensive e2e testing of all export formats."""
    import json

    frames = [
        {"figma_node_id": "1:1", "name": "Home", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Profile", "width": 428, "height": 926},
        {"figma_node_id": "1:3", "name": "Components", "width": 1200, "height": 800},
    ]

    # Home: dark bg, heading text, card with shadow and radius, body text, divider with stroke
    home_nodes = [
        {"figma_node_id": "10:1", "parent_idx": None, "name": "Home",
         "node_type": "FRAME", "depth": 0, "sort_order": 0,
         "x": 0, "y": 0, "width": 428, "height": 926,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]),
         "layout_mode": "VERTICAL", "padding_top": 16, "padding_bottom": 16,
         "padding_left": 16, "padding_right": 16, "item_spacing": 8},
        {"figma_node_id": "10:2", "parent_idx": 0, "name": "Heading",
         "node_type": "TEXT", "depth": 1, "sort_order": 0,
         "x": 16, "y": 16, "width": 396, "height": 30,
         "font_family": "Inter", "font_weight": 600, "font_size": 24,
         "line_height": json.dumps({"value": 30, "unit": "PIXELS"}),
         "text_content": "Home"},
        {"figma_node_id": "10:3", "parent_idx": 0, "name": "Card",
         "node_type": "RECTANGLE", "depth": 1, "sort_order": 1,
         "x": 16, "y": 60, "width": 396, "height": 200,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),
         "corner_radius": "8",
         "effects": json.dumps([{"type": "DROP_SHADOW", "visible": True,
             "color": {"r": 0, "g": 0, "b": 0, "a": 0.1},
             "radius": 6, "offset": {"x": 0, "y": 4}, "spread": -1}])},
        {"figma_node_id": "10:4", "parent_idx": 0, "name": "Body",
         "node_type": "TEXT", "depth": 1, "sort_order": 2,
         "x": 16, "y": 270, "width": 396, "height": 20,
         "font_family": "Inter", "font_weight": 400, "font_size": 14,
         "line_height": json.dumps({"value": 20, "unit": "PIXELS"}),
         "text_content": "Welcome"},
        {"figma_node_id": "10:5", "parent_idx": 0, "name": "Divider",
         "node_type": "FRAME", "depth": 1, "sort_order": 3,
         "x": 16, "y": 300, "width": 396, "height": 1,
         "strokes": json.dumps([{"type": "SOLID", "color": {"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}}])},
    ]

    # Profile: reuses some colors, different radius
    profile_nodes = [
        {"figma_node_id": "20:1", "parent_idx": None, "name": "Profile",
         "node_type": "FRAME", "depth": 0, "sort_order": 0,
         "x": 0, "y": 0, "width": 428, "height": 926,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]),
         "layout_mode": "VERTICAL", "padding_top": 16, "padding_bottom": 16,
         "padding_left": 16, "padding_right": 16, "item_spacing": 16},
        {"figma_node_id": "20:2", "parent_idx": 0, "name": "Username",
         "node_type": "TEXT", "depth": 1, "sort_order": 0,
         "x": 16, "y": 16, "width": 396, "height": 20,
         "font_family": "Inter", "font_weight": 400, "font_size": 14,
         "line_height": json.dumps({"value": 20, "unit": "PIXELS"}),
         "text_content": "john_doe"},
        {"figma_node_id": "20:3", "parent_idx": 0, "name": "Avatar",
         "node_type": "RECTANGLE", "depth": 1, "sort_order": 1,
         "x": 16, "y": 50, "width": 80, "height": 80,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.094, "g": 0.094, "b": 0.106, "a": 1}}]),
         "corner_radius": "12"},
    ]

    # Components: minimal
    comp_nodes = [
        {"figma_node_id": "30:1", "parent_idx": None, "name": "Components",
         "node_type": "FRAME", "depth": 0, "sort_order": 0,
         "x": 0, "y": 0, "width": 1200, "height": 800},
    ]

    responses = {"1:1": home_nodes, "1:2": profile_nodes, "1:3": comp_nodes}

    def extract_fn(node_id):
        return responses.get(node_id, [])

    return frames, extract_fn
```

Also create:
- `_count_css_vars(css_string: str) -> int`: Parse CSS and count `--var: value;` lines in `:root` block.
- `_count_dtcg_leaves(dtcg_dict: dict) -> int`: Recursively count nodes with `$value` key.
- `_extract_css_value(css_string: str, var_name: str) -> str | None`: Extract value for a specific CSS variable.
- `_navigate_dtcg_path(dtcg_dict: dict, path: str) -> dict | None`: Navigate nested dict by dot-path.

## Acceptance Criteria

- [ ] `pytest tests/test_e2e_full_export.py -v` passes all tests
- [ ] At least 8 test functions
- [ ] All tests use both `@pytest.mark.e2e` and `@pytest.mark.slow` markers
- [ ] Tests run REAL pipeline functions in sequence: extraction -> clustering -> curation -> validation -> all 4 exports
- [ ] Tests start from empty DB (init_db only), execute the full pipeline
- [ ] All 4 export formats produce non-empty output
- [ ] Token counts verified consistent across DB, CSS, DTCG, and Figma payloads
- [ ] DTCG JSON round-trip verified (parse -> serialize -> parse produces identical dict)
- [ ] CSS variable values match DTCG values for matching tokens
- [ ] Figma payload values match DTCG values for matching tokens
- [ ] Code mappings populated for all 3 targets (css, tailwind, dtcg)
- [ ] Rebind scripts generated after simulated Figma writeback
- [ ] Status report reflects completed pipeline
- [ ] FK integrity maintained across all tables after full pipeline
- [ ] Tests complete within 30 seconds (pytest-timeout)
- [ ] `pytest tests/test_e2e_full_export.py -v --tb=short` exits 0

## Notes

- This is the most comprehensive e2e test in the project. It covers Waves 0-6: schema init, extraction, normalization, binding, paths, clustering, curation, validation, Figma payloads, CSS export, Tailwind export, DTCG export, code mappings, and rebind scripts.
- The ONLY mock is the `extract_fn` that simulates Figma MCP responses. All Python pipeline code runs for real.
- The cross-format consistency checks are the unique value of this test. They catch bugs where one exporter interprets token values differently from another.
- The DTCG round-trip test verifies that `json.loads(json.dumps(dict))` produces the same structure, which ensures no non-serializable types sneak into the DTCG dict.
- Mock data must produce enough variety for all 5 clustering types AND all rebind property handler categories. The helper function above provides at minimum: 3 fill colors, 1 stroke color, 2 type scales, 2 spacing values, 2 radius values, 1 shadow effect.
- Use `@pytest.mark.timeout(30)` on all tests. The full pipeline with mock data should complete in under 10 seconds.
- Each test should run the full pipeline independently (no shared state). Use the `db` fixture for a fresh DB per test.
- Import `json` for JSON serialization and `re` for CSS parsing.