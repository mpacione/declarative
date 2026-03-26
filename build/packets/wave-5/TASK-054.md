---
taskId: TASK-054
title: "Write integration tests for curation-to-Figma-export pipeline"
wave: wave-5
testFirst: true
testLevel: integration
dependencies: [TASK-007, TASK-052]
produces:
  - tests/test_export_figma_integration.py
verify:
  - type: test
    command: 'pytest tests/test_export_figma_integration.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-054: Write integration tests for curation-to-Figma-export pipeline

## Spec Context

### From Task Decomposition Guide -- Wave 5 Test Description

> TASK-054: Write integration tests for curation-to-Figma-export pipeline -- seed post-curation fixture DB; run Figma variable payload generator; verify: payloads reference valid curated tokens, batch sizing <= 100, DTCG dot-path to Figma slash-path conversion correct, multi-mode values present, rebind scripts syntactically valid JS.

### From Task Decomposition Guide -- Integration Test Requirements

> Integration test tasks (wave 1+) MUST:
> - Import and use fixture factory functions from `tests/fixtures.py`
> - Test the actual boundary between current wave modules and prior wave outputs -- NOT re-mock what the prior wave produces
> - Verify FK integrity, data shape correctness, and state transitions across module boundaries
> - Use real DB connections (in-memory SQLite), not mock DB objects

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `seed_post_curation(db) -> sqlite3.Connection`
>   - 1 file (id=1), 3 screens, 10 nodes, 15 bindings
>   - 1 token_collection "Colors" (id=1), 1 token_mode "Default" (id=1, is_default=1)
>   - 4 color tokens curated: color.surface.primary (#09090B), color.surface.secondary (#18181B), color.border.default (#D4D4D8), color.text.primary (#FFFFFF)
>   - 1 spacing token curated: space.4 ("16")
>   - Bindings updated to binding_status="bound"
> - `seed_post_validation(db) -> sqlite3.Connection`
>   - Above + export_validations rows (all passing)

### From dd/export_figma_vars.py (produced by TASK-050, TASK-051)

> Exports:
> - `generate_variable_payloads(conn, file_id) -> list[dict]`
> - `generate_variable_payloads_checked(conn, file_id) -> list[dict]`
> - `query_exportable_tokens(conn, file_id) -> list[dict]`
> - `dtcg_to_figma_path(dtcg_name) -> str`
> - `writeback_variable_ids(conn, file_id, figma_variables) -> dict`
> - `get_sync_status_summary(conn, file_id) -> dict`

### From dd/export_rebind.py (produced by TASK-052)

> Exports:
> - `generate_rebind_scripts(conn, file_id) -> list[str]`
> - `query_bindable_entries(conn, file_id) -> list[dict]`
> - `get_rebind_summary(conn, file_id) -> dict`
> - `classify_property(property_path) -> str`

### From dd/validate.py (produced by TASK-041)

> Exports:
> - `run_validation(conn, file_id) -> dict`
> - `is_export_ready(conn) -> bool`

### From dd/curate.py (produced by TASK-040)

> Exports:
> - `accept_all(conn, file_id, db_path=None) -> dict`
> - `create_alias(conn, alias_name, target_token_id, collection_id) -> dict`

### From schema.sql -- Key tables

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id),
>     name TEXT NOT NULL, type TEXT NOT NULL,
>     tier TEXT NOT NULL DEFAULT 'extracted' CHECK(tier IN ('extracted', 'curated', 'aliased')),
>     alias_of INTEGER REFERENCES tokens(id), figma_variable_id TEXT,
>     sync_status TEXT NOT NULL DEFAULT 'pending', ... UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS token_values (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, ... UNIQUE(token_id, mode_id)
> );
> CREATE TABLE IF NOT EXISTS token_collections (
>     id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id),
>     figma_id TEXT, name TEXT NOT NULL, ...
> );
> CREATE TABLE IF NOT EXISTS token_modes (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
>     figma_mode_id TEXT, name TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0,
>     UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS node_token_bindings (
>     id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
>     property TEXT NOT NULL, token_id INTEGER REFERENCES tokens(id),
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, confidence REAL,
>     binding_status TEXT NOT NULL DEFAULT 'unbound', UNIQUE(node_id, property)
> );
> ```

## Task

Create `tests/test_export_figma_integration.py` with integration tests that verify the boundary between curation output (Wave 4) and Figma export (Wave 5). Tests seed the DB with real curation output, generate export payloads and rebind scripts, and verify correctness. Use `@pytest.mark.integration` on all tests.

### Test Functions

1. **`test_payloads_reference_valid_curated_tokens(db)`**:
   - Seed post-curation.
   - Generate payloads via `generate_variable_payloads(db, file_id=1)`.
   - For each token in each payload:
     - Convert Figma name back to DTCG: `name.replace("/", ".")`
     - Verify the DTCG name exists in the `tokens` table with `tier IN ('curated', 'aliased')`
     - Verify the token's `collection_id` matches a collection whose name equals the payload's `collectionName`
   - Verify no payload references a non-existent or extracted-tier token.

2. **`test_payload_batch_sizing(db)`**:
   - Seed post-curation.
   - Insert 120 additional curated tokens (to exceed the 100-per-call limit):
     - INSERT 120 tokens into the Colors collection with names `color.test.N` and corresponding token_values.
   - Generate payloads.
   - Verify:
     - At least 2 payloads generated for the Colors collection
     - Each payload's `tokens` list has at most 100 entries
     - Total tokens across all payloads for Colors == 4 (original) + 120 (added) = 124

3. **`test_dtcg_to_figma_path_in_payloads(db)`**:
   - Seed post-curation.
   - Generate payloads.
   - Verify:
     - Every token name in payloads uses `/` not `.` as separator
     - `color/surface/primary` appears (not `color.surface.primary`)
     - Names don't contain consecutive slashes or leading/trailing slashes

4. **`test_multi_mode_values_in_payloads(db)`**:
   - Seed post-curation.
   - Add a second mode "Dark" to the Colors collection with token_values for all 4 color tokens.
   - Generate payloads.
   - Verify:
     - Payload's `modes` list contains both "Default" and "Dark"
     - Each token's `values` dict has keys for both "Default" and "Dark"
     - Values are non-empty strings

5. **`test_rebind_scripts_syntactically_valid(db)`**:
   - Seed post-curation.
   - Set `figma_variable_id` on all tokens (simulate successful export).
   - Generate rebind scripts via `generate_rebind_scripts(db, file_id=1)`.
   - For each script:
     - Verify it's a non-empty string
     - Verify it starts with `(async () =>`
     - Verify it contains `figma.getNodeByIdAsync`
     - Verify it contains `figma.variables.getVariableByIdAsync`
     - Verify it ends with `})();`
     - Verify balanced braces: count of `{` equals count of `}`
     - Verify balanced parentheses: count of `(` equals count of `)`

6. **`test_rebind_scripts_cover_all_property_types(db)`**:
   - Seed post-curation (fixture has color, spacing, radius, effect bindings).
   - Set `figma_variable_id` on all tokens.
   - Generate rebind scripts.
   - Collect all properties from all scripts (parse the bindings array).
   - Verify coverage of property handler categories:
     - At least one `fill.*.color` binding (paint_fill)
     - At least one spacing binding like `padding.*` or `itemSpacing` (padding/direct)
   - Use `get_rebind_summary` to verify property type distribution.

7. **`test_writeback_after_payload_generation(db)`**:
   - Seed post-curation.
   - Generate payloads.
   - Build mock Figma response matching the tokens in the payloads:
     ```python
     mock_response = {
         "collections": [{
             "id": "VC:1",
             "name": "Colors",
             "modes": [{"id": "M:1", "name": "Default"}],
             "variables": [
                 {"id": "V:1:1", "name": "color/surface/primary", "type": "COLOR"},
                 {"id": "V:1:2", "name": "color/surface/secondary", "type": "COLOR"},
                 ...
             ]
         }]
     }
     ```
   - Call `writeback_variable_ids(db, file_id=1, parsed_response)`.
   - Verify:
     - Tokens now have `figma_variable_id` set (IS NOT NULL)
     - Tokens have `sync_status = 'synced'`
     - `token_collections.figma_id` is set
     - `get_sync_status_summary` shows synced count > 0
   - Re-generate payloads: should return empty list (all tokens now have figma_variable_id).

8. **`test_aliased_tokens_in_payloads(db)`**:
   - Seed post-curation.
   - Create alias "color.bg" -> token 1 (color.surface.primary). Add token_value for alias.
   - Generate payloads.
   - Verify:
     - Alias token "color/bg" appears in payload
     - Alias token's values match the target token's resolved values (from v_resolved_tokens)

9. **`test_export_pipeline_end_to_end_from_curation(db)`**:
   - Seed post-curation.
   - Run validation via `run_validation(db, file_id=1)`. Verify passes.
   - Generate payloads via `generate_variable_payloads_checked`. Verify no error.
   - Build mock Figma response matching all tokens.
   - Writeback variable IDs. Verify all synced.
   - Generate rebind scripts. Verify non-empty list.
   - Verify final state:
     - All curated tokens have figma_variable_id
     - All curated tokens have sync_status='synced'
     - Rebind scripts reference valid variable IDs
     - `get_rebind_summary` matches expected binding counts

## Acceptance Criteria

- [ ] `pytest tests/test_export_figma_integration.py -v` passes all tests
- [ ] At least 9 test functions
- [ ] All tests use `@pytest.mark.integration` marker
- [ ] Tests use real DB (in-memory SQLite), not mock DB
- [ ] Tests start from `seed_post_curation` fixture output (real Wave 4 data)
- [ ] Payload tests verify token references, batch sizing, and name conversion against real DB data
- [ ] Multi-mode test adds a second mode and verifies both modes appear in payloads
- [ ] Rebind script tests verify JS structure and balanced syntax
- [ ] Property type coverage verified across all handler categories
- [ ] Writeback test verifies figma_variable_id and sync_status updates
- [ ] End-to-end test chains validation -> payload gen -> writeback -> rebind scripts
- [ ] Aliased tokens correctly resolved in payloads
- [ ] `pytest tests/test_export_figma_integration.py -v --tb=short` exits 0

## Notes

- Use `@pytest.mark.timeout(30)` on all tests.
- Import `seed_post_curation` and `seed_post_validation` from `tests.fixtures`.
- The mock Figma response for writeback tests should match the token names from the fixture data (color.surface.primary, color.surface.secondary, color.border.default, color.text.primary, space.4).
- For the batch sizing test, you need to manually INSERT additional tokens beyond what the fixture provides. Use a loop to insert 120 tokens with unique names.
- The rebind script syntax check (balanced braces) is a simple but effective test for JS validity. No need for a full JS parser.
- The multi-mode test requires inserting a second mode and corresponding token_values manually, since the fixture only has a single "Default" mode.