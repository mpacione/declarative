---
taskId: TASK-053
title: "Write unit tests for export payload generation + rebind scripts"
wave: wave-5
testFirst: true
testLevel: unit
dependencies: [TASK-050, TASK-052]
produces:
  - tests/test_export_figma.py
verify:
  - type: test
    command: 'pytest tests/test_export_figma.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-053: Write unit tests for export payload generation + rebind scripts

## Spec Context

### From dd/export_figma_vars.py (produced by TASK-050, TASK-051)

> Exports:
> - `DTCG_TO_FIGMA_TYPE: dict[str, str]`
> - `dtcg_to_figma_path(dtcg_name: str) -> str` -- dots to slashes
> - `figma_path_to_dtcg(figma_name: str) -> str` -- slashes to dots
> - `map_token_type_to_figma(token_type: str, token_name: str) -> str`
> - `query_exportable_tokens(conn, file_id: int) -> list[dict]`
> - `generate_variable_payloads(conn, file_id: int) -> list[dict]`
> - `generate_variable_payloads_checked(conn, file_id: int) -> list[dict]`
> - `get_mode_names_for_collection(conn, collection_id: int) -> list[str]`
> - `parse_figma_variables_response(response: dict) -> list[dict]`
> - `writeback_variable_ids(conn, file_id: int, figma_variables: list[dict]) -> dict`
> - `writeback_variable_ids_from_response(conn, file_id: int, raw_response: dict) -> dict`
> - `get_sync_status_summary(conn, file_id: int) -> dict`

### From dd/export_rebind.py (produced by TASK-052)

> Exports:
> - `PROPERTY_HANDLERS: dict[str, str]`
> - `classify_property(property_path: str) -> str`
> - `query_bindable_entries(conn, file_id: int) -> list[dict]`
> - `generate_single_script(entries: list[dict]) -> str`
> - `generate_rebind_scripts(conn, file_id: int) -> list[str]`
> - `get_rebind_summary(conn, file_id: int) -> dict`

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `seed_post_curation(db) -> sqlite3.Connection`
>   - 1 file (id=1), 3 screens, 10 nodes, 15 bindings
>   - 1 token_collection "Colors" (id=1), 1 token_mode "Default" (id=1)
>   - 4 color tokens curated, 1 spacing token curated
>   - Bindings updated to binding_status="bound"
> - `seed_post_validation(db) -> sqlite3.Connection`
>   - Above + export_validations rows (all passing)

### From dd/config.py (produced by TASK-001)

> `MAX_TOKENS_PER_CALL = 100`
> `MAX_BINDINGS_PER_SCRIPT = 500`

### From dd/db.py (produced by TASK-002)

> `init_db(db_path) -> sqlite3.Connection`

## Task

Create `tests/test_export_figma.py` with comprehensive unit tests for both the Figma variable payload generator and the rebind script generator. Use `@pytest.mark.unit` on all tests.

### Test Groups

**1. Name conversion tests** (at least 6 tests):

- `test_dtcg_to_figma_path_basic`: `color.surface.primary` -> `color/surface/primary`
- `test_dtcg_to_figma_path_single`: `color` -> `color`
- `test_dtcg_to_figma_path_numeric`: `space.4` -> `space/4`
- `test_dtcg_to_figma_path_deep`: `type.body.md.fontSize` -> `type/body/md/fontSize`
- `test_figma_path_to_dtcg_basic`: `color/surface/primary` -> `color.surface.primary`
- `test_figma_path_to_dtcg_roundtrip`: Converting to Figma then back produces the original name.

**2. Type mapping tests** (at least 6 tests):

- `test_type_mapping_color`: `("color", "color.surface.primary")` -> `"COLOR"`
- `test_type_mapping_dimension`: `("dimension", "space.4")` -> `"FLOAT"`
- `test_type_mapping_font_family`: `("fontFamily", "type.body.md.fontFamily")` -> `"STRING"`
- `test_type_mapping_font_weight`: `("fontWeight", "type.body.md.fontWeight")` -> `"FLOAT"`
- `test_type_mapping_shadow_color_by_name`: `("dimension", "shadow.sm.color")` -> `"COLOR"` (name override)
- `test_type_mapping_font_style`: `("fontStyle", "type.body.md.fontStyle")` -> `"STRING"`

**3. Payload generation tests** (at least 8 tests, using DB):

- `test_payload_format(db)`: Seed post-curation, generate payloads. Verify each payload has `collectionName`, `modes`, `tokens` keys.
- `test_payload_token_names_use_slashes(db)`: Verify all token names in payloads use `/` not `.`.
- `test_payload_token_types_are_figma_types(db)`: Verify all types are one of COLOR, FLOAT, STRING.
- `test_payload_batch_size(db)`: Insert 150 curated tokens, generate payloads. Verify at least 2 payloads, each with <=100 tokens.
- `test_payload_modes_match_collection(db)`: Verify payload's modes list matches the collection's modes from DB.
- `test_payload_values_per_mode(db)`: Verify each token in payload has values dict with keys matching modes list.
- `test_payload_only_curated_tokens(db)`: Seed with mix of extracted and curated tokens. Verify payloads only include curated/aliased tokens.
- `test_payload_skips_already_exported(db)`: Set figma_variable_id on a token. Verify it's excluded from payloads.

**4. Validation gate tests** (at least 3 tests):

- `test_checked_payload_passes_when_valid(db)`: Seed post-validation, generate_variable_payloads_checked succeeds.
- `test_checked_payload_blocks_on_errors(db)`: Seed post-curation but don't run validation. Verify generate_variable_payloads_checked raises RuntimeError.
- `test_checked_payload_blocks_with_error_validations(db)`: Seed and insert an error-severity validation. Verify raises RuntimeError.

**5. Writeback tests** (at least 5 tests):

- `test_writeback_updates_variable_id(db)`: Seed post-curation, generate mock Figma response, call writeback. Verify tokens have figma_variable_id set.
- `test_writeback_updates_sync_status(db)`: After writeback, verify tokens have sync_status='synced'.
- `test_writeback_unmatched_tokens(db)`: Include a Figma variable with a name that doesn't match any DB token. Verify tokens_not_found count.
- `test_writeback_collection_id(db)`: Verify token_collections.figma_id updated.
- `test_sync_status_summary(db)`: After writeback, verify get_sync_status_summary returns correct counts.

**6. Property classification tests** (at least 10 tests):

- `test_classify_fill_color`: `"fill.0.color"` -> `"paint_fill"`
- `test_classify_fill_index`: `"fill.2.color"` -> `"paint_fill"`
- `test_classify_stroke_color`: `"stroke.0.color"` -> `"paint_stroke"`
- `test_classify_effect_color`: `"effect.0.color"` -> `"effect"`
- `test_classify_effect_radius`: `"effect.0.radius"` -> `"effect"`
- `test_classify_effect_offset`: `"effect.1.offsetX"` -> `"effect"`
- `test_classify_padding`: `"padding.top"` -> `"padding"`
- `test_classify_font_size`: `"fontSize"` -> `"direct"`
- `test_classify_corner_radius`: `"cornerRadius"` -> `"direct"`
- `test_classify_unknown`: `"fill.0.gradient"` -> `"unknown"`

**7. Rebind script generation tests** (at least 6 tests):

- `test_script_is_async_iife`: Generated script starts with `(async () =>` and ends with `})();`.
- `test_script_contains_bindings_array`: Script contains `const bindings = [`.
- `test_script_handles_fill_property`: Script contains `setBoundVariableForPaint` when fill bindings present.
- `test_script_handles_effect_property`: Script contains `setBoundVariableForEffect` when effect bindings present.
- `test_script_handles_padding_conversion`: Script converts `padding.top` to `paddingTop`.
- `test_script_handles_direct_property`: Script contains `setBoundVariable` for fontSize etc.
- `test_script_syntax_valid`: Script has balanced braces, no obvious syntax errors.

**8. Rebind batch tests** (at least 3 tests, using DB):

- `test_rebind_batching(db)`: Seed post-curation, set figma_variable_ids on tokens. Generate scripts. Verify each script has at most 500 bindings.
- `test_rebind_scripts_cover_all_bound(db)`: All bound bindings with figma_variable_id appear in scripts.
- `test_rebind_summary(db)`: get_rebind_summary returns correct total_bindings and property type breakdown.

### Helper Functions

- `_seed_with_figma_ids(db)`: Call `seed_post_curation(db)`, then UPDATE tokens to set `figma_variable_id = 'VariableID:1:N'` for each token. This simulates the state after successful writeback.
- `_make_mock_figma_response(token_names: list[str])`: Build a mock `figma_get_variables` response dict matching the expected shape.
- `_seed_many_tokens(db, count: int)`: Seed post-curation then insert additional curated tokens to test batching.

## Acceptance Criteria

- [ ] `pytest tests/test_export_figma.py -v` passes all tests
- [ ] At least 47 test functions across the 8 groups
- [ ] All tests use `@pytest.mark.unit` marker
- [ ] Tests use in-memory SQLite DB via `db` fixture
- [ ] Name conversion tests verify roundtrip (dot -> slash -> dot)
- [ ] Type mapping tests cover COLOR, FLOAT, STRING, and the shadow.color name override
- [ ] Payload tests verify format, batch sizing, and content correctness
- [ ] Validation gate tests verify blocking behavior
- [ ] Writeback tests verify figma_variable_id and sync_status updates
- [ ] Property classification tests cover all handler categories (paint_fill, paint_stroke, effect, padding, direct, unknown)
- [ ] Rebind script tests verify JS structure and property dispatch logic
- [ ] Batch tests verify 500-binding limit
- [ ] `pytest tests/test_export_figma.py -v --tb=short` exits 0

## Notes

- Use `seed_post_curation` from `tests.fixtures` for most tests (tokens are curated, bindings are bound).
- For writeback tests, build a mock `figma_get_variables` response that matches the expected shape.
- For batch size tests, insert enough tokens/bindings to exceed the batch limits (100 for payloads, 500 for rebind scripts).
- The rebind script JS doesn't need to be executed -- just verify its structure and content via string assertions.
- Use `json.loads()` to verify payloads are valid JSON-serializable dicts.
- Mark all tests with `@pytest.mark.unit` and use `@pytest.mark.timeout(10)` on DB tests.