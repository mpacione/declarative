---
taskId: TASK-055
title: "Write e2e test: full pipeline through Figma export"
wave: wave-5
testFirst: true
testLevel: e2e
dependencies: [TASK-007, TASK-052, TASK-045]
produces:
  - tests/test_e2e_figma_export.py
verify:
  - type: test
    command: 'pytest tests/test_e2e_figma_export.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-055: Write e2e test: full pipeline through Figma export

## Spec Context

### From Task Decomposition Guide -- Wave 5 Test Description

> TASK-055: Write e2e test: full pipeline through Figma export -- fixture DB -> extraction -> clustering -> curation -> validation -> Figma payload gen -> verify: payloads are valid JSON, all curated tokens represented, batch count matches ceil(tokens/100), rebind scripts cover all bound property types.

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
> - `writeback_variable_ids(conn, file_id, figma_variables) -> dict`
> - `get_sync_status_summary(conn, file_id) -> dict`
> - `dtcg_to_figma_path(name) -> str`
> - `figma_path_to_dtcg(name) -> str`

### From dd/export_rebind.py (produced by TASK-052)

> Exports:
> - `generate_rebind_scripts(conn, file_id) -> list[str]`
> - `get_rebind_summary(conn, file_id) -> dict`
> - `classify_property(property_path) -> str`

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `make_mock_figma_response(screen_name, node_count) -> list[dict]`

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
> CREATE TABLE IF NOT EXISTS node_token_bindings (
>     id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
>     property TEXT NOT NULL, token_id INTEGER REFERENCES tokens(id),
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, confidence REAL,
>     binding_status TEXT NOT NULL DEFAULT 'unbound', UNIQUE(node_id, property)
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
>        COUNT(ntb.id) AS binding_count, COUNT(DISTINCT ntb.node_id) AS node_count,
>        COUNT(DISTINCT n.screen_id) AS screen_count
> FROM tokens t LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
> LEFT JOIN nodes n ON ntb.node_id = n.id GROUP BY t.id ORDER BY binding_count DESC;
> ```

## Task

Create `tests/test_e2e_figma_export.py` -- the e2e test covering Waves 0-5 (extraction through Figma export payload generation). This test runs the ENTIRE pipeline from extraction through clustering, curation, validation, Figma payload generation, simulated writeback, and rebind script generation. Use `@pytest.mark.e2e` and `@pytest.mark.slow` on all tests.

### Mock Data

Build comprehensive mock data within the test file that exercises the full pipeline. Reuse or adapt the mock data pattern from TASK-045's e2e test but ensure enough variety for all clustering types and all rebind property handler categories.

**Mock frames** (3 screens):
```python
MOCK_FRAMES = [
    {"figma_node_id": "1:1", "name": "Home", "width": 428, "height": 926},
    {"figma_node_id": "1:2", "name": "Profile", "width": 428, "height": 926},
    {"figma_node_id": "1:3", "name": "Components", "width": 1200, "height": 800},
]
```

**Mock extraction responses** -- each screen should generate nodes with:
- Fill colors: 3+ unique colors (#09090B, #18181B, #FFFFFF)
- Stroke colors: at least 1 (#D4D4D8)
- Typography: 2+ unique combos (Inter/600/24px, Inter/400/14px)
- Spacing: 2+ unique values (8, 16) as padding and itemSpacing
- Radius: 2+ unique values (8, 12)
- Effects: 1+ DROP_SHADOW (produces 5 effect bindings)
- Opacity: 1 node with opacity != 1.0

This ensures:
- Color clustering creates tokens
- Typography clustering creates atomic tokens
- Spacing, radius, effect clustering creates tokens
- Rebind scripts cover paint_fill, paint_stroke, effect, padding, direct property types

### Test Functions

1. **`test_e2e_full_pipeline_to_figma_payloads(db)`**:
   - Start with empty schema-initialized DB.
   - Run extraction pipeline with mock data.
   - Run clustering.
   - Run accept_all (curate all tokens, bind all bindings).
   - Run validation. Verify passes.
   - Generate payloads via `generate_variable_payloads_checked`.
   - Verify:
     - Payloads is a non-empty list of dicts
     - Each payload has `collectionName`, `modes`, `tokens` keys
     - `json.dumps(payload)` succeeds for each payload (valid JSON-serializable)
     - Each token in payloads has `name`, `type`, `values` keys

2. **`test_e2e_all_curated_tokens_represented_in_payloads(db)`**:
   - Run full pipeline through payload generation.
   - Count curated tokens in DB: `SELECT COUNT(*) FROM tokens t JOIN token_collections tc ON t.collection_id = tc.id WHERE tc.file_id = 1 AND t.tier IN ('curated', 'aliased') AND t.figma_variable_id IS NULL`.
   - Count tokens across all payloads.
   - Verify: total tokens in payloads == curated tokens in DB.
   - Verify: every curated token name (converted to slash-path) appears in some payload.

3. **`test_e2e_batch_count_matches_ceil(db)`**:
   - Run full pipeline through payload generation.
   - Count curated tokens per collection.
   - For each collection, verify: number of payloads for that collection == ceil(tokens / 100).
   - With the default mock data (probably <100 tokens per collection), expect 1 payload per collection.

4. **`test_e2e_rebind_scripts_cover_bound_property_types(db)`**:
   - Run full pipeline through curation.
   - Simulate Figma export: build mock Figma variables response, writeback IDs.
   - Generate rebind scripts.
   - Verify:
     - Scripts is a non-empty list
     - Collect all property types from the scripts' binding entries via `get_rebind_summary`
     - At least these categories are covered: fill color (paint), spacing (direct/padding), radius (direct)
     - If mock data includes effects: effect category covered
     - Total bindings in scripts == total bound bindings with figma_variable_id in DB

5. **`test_e2e_writeback_and_sync(db)`**:
   - Run full pipeline through payload generation.
   - Build mock Figma response from generated payloads (construct variable IDs matching token names).
   - Call writeback.
   - Verify:
     - All curated tokens now have `figma_variable_id IS NOT NULL`
     - All curated tokens have `sync_status = 'synced'`
     - `get_sync_status_summary` shows `synced` count equal to curated token count
     - Re-generating payloads returns empty list (all already exported)

6. **`test_e2e_fk_integrity_after_full_export(db)`**:
   - Run full pipeline through writeback.
   - Verify FK integrity across the entire chain:
     - files -> screens -> nodes -> bindings -> tokens -> token_values -> token_modes -> token_collections
     - Every `tokens.figma_variable_id` (non-NULL) is a non-empty string
     - Every `node_token_bindings` with `binding_status = 'bound'` and non-NULL token_id references a token that exists
   - Use explicit SQL: `SELECT COUNT(*) FROM node_token_bindings WHERE token_id IS NOT NULL AND token_id NOT IN (SELECT id FROM tokens)` = 0

7. **`test_e2e_pipeline_summary(db)`**:
   - Run full pipeline.
   - Verify pipeline state:
     - `v_curation_progress`: bound percentage > 0
     - `v_export_readiness`: no error-severity issues
     - `v_token_coverage`: all tokens have binding_count > 0
     - Total token count > 0
     - Total binding count > 0

### Helper Function

Create `_build_e2e_mock_data()` returning `(frames, extract_fn)` with rich mock data covering all property types:

```python
def _build_e2e_mock_data():
    """Build mock frames and extraction function for e2e testing."""
    frames = [
        {"figma_node_id": "1:1", "name": "Home", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Profile", "width": 428, "height": 926},
        {"figma_node_id": "1:3", "name": "Components", "width": 1200, "height": 800},
    ]

    home_nodes = [
        # Root frame with fill and spacing
        {"figma_node_id": "10:1", "parent_idx": None, "name": "Home",
         "node_type": "FRAME", "depth": 0, "sort_order": 0,
         "x": 0, "y": 0, "width": 428, "height": 926,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}}]),
         "layout_mode": "VERTICAL", "padding_top": 16, "padding_bottom": 16,
         "padding_left": 16, "padding_right": 16, "item_spacing": 8},
        # Text node
        {"figma_node_id": "10:2", "parent_idx": 0, "name": "Title",
         "node_type": "TEXT", "depth": 1, "sort_order": 0,
         "x": 16, "y": 16, "width": 396, "height": 30,
         "font_family": "Inter", "font_weight": 600, "font_size": 24,
         "line_height": json.dumps({"value": 30, "unit": "PIXELS"}),
         "text_content": "Home"},
        # Rectangle with fill, radius, and shadow
        {"figma_node_id": "10:3", "parent_idx": 0, "name": "Card",
         "node_type": "RECTANGLE", "depth": 1, "sort_order": 1,
         "x": 16, "y": 60, "width": 396, "height": 200,
         "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),
         "corner_radius": "8",
         "effects": json.dumps([{"type": "DROP_SHADOW", "visible": True,
             "color": {"r": 0, "g": 0, "b": 0, "a": 0.1},
             "radius": 6, "offset": {"x": 0, "y": 4}, "spread": -1}])},
        # Another text
        {"figma_node_id": "10:4", "parent_idx": 0, "name": "Body",
         "node_type": "TEXT", "depth": 1, "sort_order": 2,
         "x": 16, "y": 270, "width": 396, "height": 20,
         "font_family": "Inter", "font_weight": 400, "font_size": 14,
         "line_height": json.dumps({"value": 20, "unit": "PIXELS"}),
         "text_content": "Welcome"},
        # Frame with stroke
        {"figma_node_id": "10:5", "parent_idx": 0, "name": "Divider",
         "node_type": "FRAME", "depth": 1, "sort_order": 3,
         "x": 16, "y": 300, "width": 396, "height": 1,
         "strokes": json.dumps([{"type": "SOLID", "color": {"r": 0.831, "g": 0.831, "b": 0.847, "a": 1}}])},
    ]
    # ... similar for Profile and Components screens
```

Also create `_build_mock_figma_response_from_payloads(payloads: list[dict]) -> dict` that constructs a mock `figma_get_variables` response from the generated payloads, assigning sequential variable IDs.

## Acceptance Criteria

- [ ] `pytest tests/test_e2e_figma_export.py -v` passes all tests
- [ ] At least 7 test functions
- [ ] All tests use both `@pytest.mark.e2e` and `@pytest.mark.slow` markers
- [ ] Tests run REAL pipeline functions in sequence: extraction -> clustering -> curation -> validation -> payload gen -> writeback -> rebind scripts
- [ ] Tests start from empty DB (init_db only), execute the full pipeline
- [ ] Mock data produces bindings for color, typography, spacing, radius, and effects
- [ ] Payloads verified as valid JSON-serializable dicts
- [ ] All curated tokens appear in payloads
- [ ] Batch count verified against ceil(tokens/100)
- [ ] Rebind scripts cover all bound property types from the pipeline
- [ ] Writeback correctly sets figma_variable_id and sync_status on all tokens
- [ ] FK integrity verified across the entire table chain after full pipeline
- [ ] Tests complete within 30 seconds (pytest-timeout)
- [ ] `pytest tests/test_e2e_figma_export.py -v --tb=short` exits 0

## Notes

- This is the comprehensive e2e test for Waves 0-5. It builds on the Wave 4 e2e test (TASK-045) by adding payload generation, writeback, and rebind script generation.
- The ONLY mock is the `extract_fn` that simulates Figma MCP responses and the mock Figma variables response for writeback. All Python pipeline code runs for real.
- The mock data must produce enough variety to test all clustering and rebind property types. At minimum: 3 unique colors, 2 type scales, 2 spacing values, 2 radius values, 1 shadow effect.
- The `_build_mock_figma_response_from_payloads` helper avoids duplicating token names between mock data and expected Figma response -- it reads from the generated payloads to build a matching response.
- Use `@pytest.mark.timeout(30)` on all tests. With mock data and in-memory DB, the full pipeline should complete in under 10 seconds.
- Import `json` for JSON serialization/validation of payloads.
- Each test function should run the full pipeline independently (no shared state between tests). Use the `db` fixture for fresh DB per test.