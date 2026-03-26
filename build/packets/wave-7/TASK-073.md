---
taskId: TASK-073
title: "Write unit tests for drift detection + mode creation"
wave: wave-7
testFirst: false
testLevel: unit
dependencies: [TASK-070, TASK-072]
produces:
  - tests/test_drift.py
  - tests/test_modes.py
verify:
  - type: test
    command: 'pytest tests/test_drift.py tests/test_modes.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-073: Write unit tests for drift detection + mode creation

## Spec Context

### From dd/drift.py (produced by TASK-070)

> Exports:
> - `detect_drift(conn, file_id, figma_variables_response) -> dict` -- full drift detection with status updates
> - `detect_drift_readonly(conn, file_id, figma_variables_response) -> dict` -- read-only comparison
> - `compare_token_values(conn, file_id, figma_variables) -> dict` -- compare DB vs Figma values
> - `parse_figma_variables_for_drift(raw_response) -> list[dict]` -- parse MCP response
> - `generate_drift_report(conn, file_id) -> dict` -- query v_drift_report
> - `update_sync_statuses(conn, file_id, comparison) -> dict` -- update tokens.sync_status
> - `normalize_value_for_comparison(value, token_type) -> str` -- normalize for comparison

### From dd/modes.py (produced by TASK-072)

> Exports:
> - `create_mode(conn, collection_id, mode_name) -> int` -- insert new mode
> - `copy_values_from_default(conn, collection_id, new_mode_id) -> int` -- copy token_values
> - `apply_oklch_inversion(conn, collection_id, mode_id) -> int` -- invert color lightness
> - `apply_scale_factor(conn, collection_id, mode_id, factor) -> int` -- scale dimension values
> - `create_dark_mode(conn, collection_id, mode_name) -> dict` -- convenience dark mode
> - `create_compact_mode(conn, collection_id, factor, mode_name) -> dict` -- convenience compact mode
> - `create_theme(conn, file_id, theme_name, collection_ids, transform, factor) -> dict` -- multi-collection theme
> - `oklch_to_hex(L, C, h) -> str` -- OKLCH to hex conversion

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `seed_post_curation(db) -> sqlite3.Connection`
>   - 1 file (id=1), 3 screens, 10 nodes, 15 bindings
>   - 1 token_collection "Colors" (id=1), 1 token_mode "Default" (id=1, is_default=1)
>   - 4 color tokens curated: color.surface.primary (#09090B), color.surface.secondary (#18181B), color.border.default (#D4D4D8), color.text.primary (#FFFFFF)
>   - 1 spacing collection, 1 spacing token curated: space.4 ("16")
>   - All tokens have sync_status='pending'
> - `seed_post_validation(db) -> sqlite3.Connection` -- above + export_validations

### From schema.sql -- Key tables

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id),
>     name TEXT NOT NULL, type TEXT NOT NULL,
>     tier TEXT NOT NULL DEFAULT 'extracted' CHECK(tier IN ('extracted', 'curated', 'aliased')),
>     alias_of INTEGER REFERENCES tokens(id), figma_variable_id TEXT,
>     sync_status TEXT NOT NULL DEFAULT 'pending'
>     CHECK(sync_status IN ('pending', 'figma_only', 'code_only', 'synced', 'drifted')),
>     ... UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS token_values (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, ...
>     UNIQUE(token_id, mode_id)
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
> ```

### From dd/color.py (produced by TASK-004)

> Exports:
> - `hex_to_oklch(hex_color: str) -> tuple[float, float, float]`
> - `oklch_invert_lightness(L, C, h) -> tuple[float, float, float]`

## Task

Create two test files: `tests/test_drift.py` for drift detection tests and `tests/test_modes.py` for mode creation tests. Use `@pytest.mark.unit` on all tests.

### `tests/test_drift.py` -- at least 18 tests

**Value normalization tests** (at least 5):

1. `test_normalize_color_case_insensitive`: `normalize_value_for_comparison("#09090B", "color")` == `normalize_value_for_comparison("#09090b", "color")`
2. `test_normalize_dimension_trailing_zero`: `normalize_value_for_comparison("16", "dimension")` == `normalize_value_for_comparison("16.0", "dimension")`
3. `test_normalize_font_family_quotes`: `normalize_value_for_comparison('"Inter"', "fontFamily")` == `normalize_value_for_comparison("Inter", "fontFamily")`
4. `test_normalize_color_8digit_to_6digit`: `normalize_value_for_comparison("#09090BFF", "color")` == `normalize_value_for_comparison("#09090B", "color")` (alpha=FF means opaque)
5. `test_normalize_whitespace`: `normalize_value_for_comparison("  16  ", "dimension")` == `normalize_value_for_comparison("16", "dimension")`

**Parse Figma response tests** (at least 3):

6. `test_parse_figma_response_basic`: Parse a mock `figma_get_variables` response with 1 collection, 1 mode, 2 variables. Verify list of dicts with correct dtcg_name, variable_id, values.
7. `test_parse_figma_response_multimode`: Parse response with 2 modes. Verify values dict has entries for both modes.
8. `test_parse_figma_response_empty`: Parse empty/minimal response. Returns empty list without error.

**Comparison tests** (at least 5, using DB):

9. `test_compare_all_synced(db)`: Seed post-curation, set figma_variable_id on all tokens. Build mock Figma response with matching values. `compare_token_values` returns all tokens in "synced".
10. `test_compare_drifted(db)`: Seed post-curation, set figma_variable_id on tokens. Build mock response with ONE changed value. Verify that token appears in "drifted" with both db_value and figma_value.
11. `test_compare_pending(db)`: Seed post-curation (no figma_variable_id). `compare_token_values` returns all tokens in "pending".
12. `test_compare_figma_only(db)`: Build mock response with a variable not in DB. Verify it appears in "figma_only".
13. `test_compare_mixed_statuses(db)`: Some tokens synced, some drifted, some pending. Verify each category populated correctly.

**Update sync status tests** (at least 3, using DB):

14. `test_update_sync_synced(db)`: Update with synced comparison. Verify tokens.sync_status = 'synced' in DB.
15. `test_update_sync_drifted(db)`: Update with drifted comparison. Verify tokens.sync_status = 'drifted'.
16. `test_update_returns_counts(db)`: Verify update_sync_statuses returns correct counts per status.

**Full drift detection tests** (at least 2, using DB):

17. `test_detect_drift_readonly_no_update(db)`: Seed, call detect_drift_readonly. Verify DB sync_status NOT modified (still 'pending').
18. `test_detect_drift_updates_db(db)`: Seed, set figma_variable_id, call detect_drift with matching values. Verify DB updated to 'synced'.

**Drift report test** (at least 1):

19. `test_generate_drift_report(db)`: Seed with mix of statuses (pending, synced, drifted). Verify report summary counts are correct. Verify drifted_tokens list is non-empty.

### `tests/test_modes.py` -- at least 15 tests

**Mode creation tests** (at least 3):

1. `test_create_mode_basic(db)`: Seed post-curation. Create "Dark" mode. Verify row in token_modes with is_default=0.
2. `test_create_mode_duplicate_raises(db)`: Create mode, then try to create same name again. Verify ValueError.
3. `test_create_mode_returns_id(db)`: Verify create_mode returns a positive integer ID.

**Copy values tests** (at least 4):

4. `test_copy_values_from_default(db)`: Seed post-curation (4 color tokens + 1 spacing token, all with Default mode values). Create Dark mode. Copy values. Verify 4 new token_values rows for Dark mode (skipping aliased if any). Verify values match Default mode values.
5. `test_copy_values_no_default_raises(db)`: Create a collection with no default mode. Call copy_values_from_default. Verify ValueError.
6. `test_copy_values_skips_aliased(db)`: Add an aliased token to the collection. Copy values. Verify aliased token has no value for new mode.
7. `test_copy_values_count(db)`: Verify return count matches number of non-aliased tokens in collection.

**OKLCH inversion tests** (at least 4):

8. `test_oklch_to_hex_white`: `oklch_to_hex(1.0, 0.0, 0.0)` produces value close to `#FFFFFF` (within 2 in each channel).
9. `test_oklch_to_hex_black`: `oklch_to_hex(0.0, 0.0, 0.0)` produces value close to `#000000`.
10. `test_apply_oklch_inversion_inverts_colors(db)`: Seed post-curation, create Dark mode, copy values, apply inversion. Verify color values changed. Verify dark color (#09090B, low lightness) becomes light, and white (#FFFFFF, high lightness) becomes dark.
11. `test_apply_oklch_inversion_only_colors(db)`: Seed with spacing tokens in same collection. Verify spacing values are NOT affected by oklch_inversion.

**Scale factor tests** (at least 2):

12. `test_apply_scale_factor(db)`: Seed with spacing token (value "16"). Create mode, copy values, apply factor=0.5. Verify new value is "8".
13. `test_apply_scale_factor_skips_auto(db)`: Insert a dimension token with value "AUTO". Apply scale factor. Verify value remains "AUTO".

**Convenience function tests** (at least 2):

14. `test_create_dark_mode_full(db)`: Seed post-curation. Call create_dark_mode on Colors collection. Verify: mode created, values copied, colors inverted. Verify return dict has mode_id, values_copied, values_inverted.
15. `test_create_theme_multi_collection(db)`: Seed post-curation (has Colors and Spacing collections). Call create_theme with transform="dark". Verify modes created in BOTH collections. Verify colors inverted in Colors collection, values copied (unmodified) in Spacing collection.

### Helper Functions

- `_build_mock_figma_response(tokens: list[dict], modify: dict | None = None) -> dict`: Build a mock `figma_get_variables` response from a list of token dicts. Optionally modify specific values to simulate drift.
- `_set_figma_variable_ids(db, file_id: int)`: UPDATE all curated tokens to have `figma_variable_id = 'VariableID:1:N'`.

## Acceptance Criteria

- [ ] `pytest tests/test_drift.py -v` passes all tests
- [ ] `pytest tests/test_modes.py -v` passes all tests
- [ ] `tests/test_drift.py` has at least 18 test functions
- [ ] `tests/test_modes.py` has at least 15 test functions
- [ ] All tests use `@pytest.mark.unit` marker
- [ ] Tests use in-memory SQLite DB via `db` fixture
- [ ] Tests import `seed_post_curation` from `tests.fixtures` for DB setup
- [ ] Drift tests verify value normalization (case, whitespace, quotes, trailing zeros)
- [ ] Drift tests verify comparison output for synced, drifted, pending, figma_only categories
- [ ] Drift tests verify `detect_drift_readonly` does NOT modify DB
- [ ] Drift tests verify `detect_drift` DOES update sync_status
- [ ] Mode tests verify mode creation, value copying, OKLCH inversion, and scale factor
- [ ] Mode tests verify `create_dark_mode` and `create_theme` convenience functions
- [ ] Mode tests verify inverted colors are valid hex and meaningfully different from originals
- [ ] Mode tests verify scale factor applied to dimension values, not color values
- [ ] `pytest tests/test_drift.py tests/test_modes.py -v --tb=short` exits 0

## Notes

- Use `seed_post_curation` from `tests.fixtures` as the base for most tests. This provides 4 color tokens and 1 spacing token with Default mode values.
- For drift detection tests, you need to simulate the Figma response. Build helper functions that construct the expected response shape.
- For drift comparison tests, set `figma_variable_id` on tokens first (via UPDATE) to simulate tokens that have been exported to Figma.
- The OKLCH inversion test should verify that colors changed meaningfully, not just that they're different. A dark color (low L) should become lighter (high L) and vice versa.
- The `oklch_to_hex` test values may not be exact #FFFFFF and #000000 due to floating point math. Use approximate comparison: each channel within 2 of expected.
- For the multi-collection theme test, the fixture `seed_post_curation` creates both a Colors and Spacing collection.
- Use `@pytest.mark.timeout(10)` on all tests.