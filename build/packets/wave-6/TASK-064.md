---
taskId: TASK-064
title: "Write integration tests for curation-to-code-export pipeline"
wave: wave-6
testFirst: true
testLevel: integration
dependencies: [TASK-007, TASK-062]
produces:
  - tests/test_export_code_integration.py
verify:
  - type: test
    command: 'pytest tests/test_export_code_integration.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-064: Write integration tests for curation-to-code-export pipeline

## Spec Context

### From Task Decomposition Guide -- Wave 6 Test Description

> TASK-064: Write integration tests for curation-to-code-export pipeline -- seed post-curation fixture DB; run all 3 exporters; verify: CSS custom properties parse via regex, Tailwind config is valid JS object, DTCG JSON validates against W3C schema, all curated tokens appear in all 3 outputs, alias references resolve in output.

### From Task Decomposition Guide -- Integration Test Requirements

> Integration test tasks (wave 1+) MUST:
> - Import and use fixture factory functions from `tests/fixtures.py`
> - Test the actual boundary between current wave modules and prior wave outputs
> - Verify FK integrity, data shape correctness, and state transitions across module boundaries
> - Use real DB connections (in-memory SQLite), not mock DB objects

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `seed_post_curation(db) -> sqlite3.Connection`
>   - 1 file (id=1), 3 screens, 10 nodes, 15 bindings
>   - 1 token_collection "Colors" (id=1), 1 token_mode "Default" (id=1, is_default=1)
>   - 4 color tokens curated: color.surface.primary (#09090B), color.surface.secondary (#18181B), color.border.default (#D4D4D8), color.text.primary (#FFFFFF)
>   - 1 spacing collection, 1 spacing token curated: space.4 ("16")
>   - Bindings: binding_status="bound"
> - `seed_post_validation(db) -> sqlite3.Connection` -- above + export_validations rows

### From dd/export_css.py (produced by TASK-060)

> Exports:
> - `generate_css(conn, file_id: int) -> str`
> - `export_css(conn, file_id: int) -> dict`
> - `write_code_mappings(conn, file_id: int) -> int`
> - `token_name_to_css_var(token_name: str) -> str`

### From dd/export_tailwind.py (produced by TASK-061)

> Exports:
> - `generate_tailwind_config(conn, file_id: int) -> str`
> - `generate_tailwind_config_dict(conn, file_id: int) -> dict`
> - `export_tailwind(conn, file_id: int) -> dict`
> - `write_tailwind_mappings(conn, file_id: int) -> int`

### From dd/export_dtcg.py (produced by TASK-062)

> Exports:
> - `generate_dtcg_json(conn, file_id: int, indent: int = 2) -> str`
> - `generate_dtcg_dict(conn, file_id: int) -> dict`
> - `export_dtcg(conn, file_id: int) -> dict`

### From dd/curate.py (produced by TASK-040)

> Exports:
> - `create_alias(conn, alias_name, target_token_id, collection_id) -> dict`

### From schema.sql -- code_mappings table

> ```sql
> CREATE TABLE IF NOT EXISTS code_mappings (
>     id              INTEGER PRIMARY KEY,
>     token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     target          TEXT NOT NULL,
>     identifier      TEXT NOT NULL,
>     file_path       TEXT,
>     extracted_at    TEXT,
>     UNIQUE(token_id, target, identifier)
> );
> ```

### From schema.sql -- tokens, token_values, token_collections, token_modes, v_resolved_tokens

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id),
>     name TEXT NOT NULL, type TEXT NOT NULL,
>     tier TEXT NOT NULL DEFAULT 'extracted' CHECK(tier IN ('extracted', 'curated', 'aliased')),
>     alias_of INTEGER REFERENCES tokens(id), ... UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS token_values (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, ... UNIQUE(token_id, mode_id)
> );
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

## Task

Create `tests/test_export_code_integration.py` with integration tests that verify the boundary between curation output (Wave 4) and code export (Wave 6). Tests seed the DB with real curation output, run all 3 exporters, and verify outputs are structurally correct and consistent with each other. Use `@pytest.mark.integration` on all tests.

### Test Functions

1. **`test_css_custom_properties_parse(db)`**:
   - Seed post-curation.
   - Call `generate_css(db, file_id=1)`.
   - Verify CSS structure via regex:
     - Contains `:root {` block
     - Each CSS custom property matches pattern `\s*--[a-z][a-z0-9-]*:\s*.+;`
     - All 4 color tokens + 1 spacing token appear as CSS variables
     - Values are non-empty
   - Parse each `--var-name: value;` line and verify the var name maps back to a valid token via `token_name_to_css_var`.

2. **`test_tailwind_config_valid_structure(db)`**:
   - Seed post-curation.
   - Call `generate_tailwind_config_dict(db, file_id=1)`.
   - Verify dict structure:
     - Has `colors` key with at least 4 entries
     - Has `spacing` key with at least 1 entry
     - All values are strings (hex for colors, px-suffixed for dimensions)
   - Call `generate_tailwind_config(db, file_id=1)`.
   - Verify string:
     - Contains `module.exports`
     - Contains `theme:`
     - Contains `extend:`

3. **`test_dtcg_json_validates(db)`**:
   - Seed post-curation.
   - Call `generate_dtcg_json(db, file_id=1)`.
   - Parse with `json.loads` -- must succeed.
   - Verify structure of parsed dict:
     - Top-level keys are token group names (e.g., `color`, `space`)
     - Leaf token nodes have `$type` and `$value` keys
     - `$type` values are valid DTCG types: color, dimension, fontFamily, fontWeight, number, shadow
     - Color `$value` entries match hex pattern `^#[0-9A-Fa-f]{6,8}$`
   - Verify total leaf token count matches curated token count in DB.

4. **`test_all_curated_tokens_in_all_outputs(db)`**:
   - Seed post-curation.
   - Get curated token names from DB: `SELECT name FROM tokens t JOIN token_collections tc ON t.collection_id = tc.id WHERE tc.file_id = 1 AND t.tier IN ('curated', 'aliased')`.
   - For each token name:
     - Verify it appears in CSS output (as `--{name.replace('.', '-')}`)
     - Verify it appears in Tailwind config dict (by checking relevant section keys)
     - Verify it appears in DTCG JSON (by traversing the nested dict along dot-path segments)
   - Ensure zero tokens are missing from any output.

5. **`test_alias_references_resolve_in_all_outputs(db)`**:
   - Seed post-curation.
   - Create an alias: `create_alias(db, "color.bg", target_token_id=1, collection_id=1)`.
   - Add a token_value for the alias (copy from target).
   - Generate all 3 outputs.
   - Verify alias handling:
     - CSS: alias appears as `--color-bg: var(--color-surface-primary);`
     - Tailwind: alias has its resolved value (not a reference)
     - DTCG: alias uses `{color.surface.primary}` reference syntax in `$value`

6. **`test_code_mappings_populated_for_all_targets(db)`**:
   - Seed post-curation.
   - Run all 3 exporters: `export_css`, `export_tailwind`, `export_dtcg`.
   - Query `code_mappings`:
     - Verify rows exist with target='css', target='tailwind', target='dtcg'
     - Every curated token has at least 1 mapping per target
     - `identifier` values are non-empty strings
     - FK integrity: every `code_mappings.token_id` exists in `tokens.id`

7. **`test_multi_mode_consistency_across_exports(db)`**:
   - Seed post-curation.
   - Add "Dark" mode to Colors collection with inverted values for all 4 color tokens.
   - Generate all 3 outputs.
   - Verify multi-mode handling:
     - CSS: contains `[data-theme="Dark"]` block with all 4 color vars
     - Tailwind: config uses default mode values (Tailwind doesn't natively handle modes)
     - DTCG: tokens have `$extensions.org.design-tokens.modes.Dark` with correct values
   - Verify Dark mode values in CSS match Dark mode values in DTCG extensions.

8. **`test_export_consistency_token_count(db)`**:
   - Seed post-curation.
   - Count tokens from each exporter:
     - CSS: count distinct CSS variables in the `:root` block
     - Tailwind: count total keys across all sections in config dict
     - DTCG: count leaf nodes with `$value` in the JSON dict
   - Verify counts are equal (or explain differences -- e.g., Tailwind may have fewer if some types don't map to a section).
   - At minimum, all 3 outputs should have the same curated color tokens.

9. **`test_value_consistency_across_formats(db)`**:
   - Seed post-curation.
   - For each curated color token:
     - Extract its value from CSS output (parse `--var-name: value;`)
     - Extract its value from Tailwind config dict
     - Extract its value from DTCG dict (`$value`)
   - Verify all 3 sources agree on the hex color value (e.g., `#09090B` in all 3).

## Acceptance Criteria

- [ ] `pytest tests/test_export_code_integration.py -v` passes all tests
- [ ] At least 9 test functions
- [ ] All tests use `@pytest.mark.integration` marker
- [ ] Tests use real DB (in-memory SQLite), not mock DB
- [ ] Tests start from `seed_post_curation` fixture output (real Wave 4 data)
- [ ] CSS output verified via regex parsing of custom properties
- [ ] Tailwind config verified as valid dict structure with expected sections
- [ ] DTCG JSON verified as parseable and structurally correct with $type/$value
- [ ] All curated tokens appear in all 3 outputs (cross-format coverage)
- [ ] Alias references verified in all 3 formats (var(), literal, {ref})
- [ ] Code mappings verified for all 3 targets with FK integrity
- [ ] Multi-mode values consistent between CSS and DTCG
- [ ] Token values consistent across all 3 formats
- [ ] `pytest tests/test_export_code_integration.py -v --tb=short` exits 0

## Notes

- Use `@pytest.mark.timeout(30)` on all tests.
- Import `seed_post_curation` from `tests.fixtures` for setup.
- The cross-format consistency tests are key to this integration suite -- they verify that all 3 exporters read from the same DB state and produce agreeing outputs.
- For the alias test, you need to INSERT an alias token and its token_value manually. The `create_alias` function from `dd.curate` creates the token but you may need to add token_values separately.
- The multi-mode test requires manually inserting a "Dark" mode and corresponding token_values.
- Tailwind doesn't handle multi-mode natively. The integration test should verify that Tailwind uses default mode values while CSS and DTCG handle all modes.
- For DTCG leaf node counting, traverse the nested dict recursively: a node is a leaf if it has a `$value` key.