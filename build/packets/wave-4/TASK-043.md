---
taskId: TASK-043
title: "Write unit tests for curation operations + validation"
wave: wave-4
testFirst: true
testLevel: unit
dependencies: [TASK-040, TASK-041]
produces:
  - tests/test_curation.py
  - tests/test_validation.py
verify:
  - type: test
    command: 'pytest tests/test_curation.py tests/test_validation.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-043: Write unit tests for curation operations + validation

## Spec Context

### From dd/curate.py (produced by TASK-040)

> Exports:
> - `accept_token(conn, token_id) -> dict` -- promote tier to curated, bindings to bound
> - `accept_all(conn, file_id, db_path=None) -> dict` -- bulk accept all extracted tokens
> - `rename_token(conn, token_id, new_name) -> dict` -- update token name with DTCG validation
> - `merge_tokens(conn, survivor_id, victim_id, db_path=None) -> dict` -- merge victim into survivor
> - `split_token(conn, token_id, new_name, binding_ids) -> dict` -- create new token, move bindings
> - `reject_token(conn, token_id, db_path=None) -> dict` -- delete token, revert bindings to unbound
> - `create_alias(conn, alias_name, target_token_id, collection_id) -> dict` -- create aliased token

### From dd/validate.py (produced by TASK-041)

> Exports:
> - `run_validation(conn, file_id) -> dict` -- run all checks, write to export_validations, return pass/fail
> - `check_mode_completeness(conn, file_id) -> list[dict]`
> - `check_name_dtcg_compliant(conn, file_id) -> list[dict]`
> - `check_orphan_tokens(conn, file_id) -> list[dict]`
> - `check_binding_coverage(conn, file_id) -> list[dict]`
> - `check_alias_targets_curated(conn, file_id) -> list[dict]`
> - `check_name_uniqueness(conn, file_id) -> list[dict]`
> - `check_value_format(conn, file_id) -> list[dict]`
> - `is_export_ready(conn) -> bool`

### From dd/status.py (produced by TASK-042)

> Exports:
> - `get_curation_progress(conn) -> list[dict]`
> - `get_token_coverage(conn, file_id=None) -> list[dict]`
> - `get_unbound_summary(conn, file_id=None, limit=50) -> list[dict]`
> - `get_export_readiness(conn) -> list[dict]`
> - `format_status_report(conn, file_id=None) -> str`
> - `get_status_dict(conn, file_id=None) -> dict`

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `seed_post_extraction(db)` -- 1 file, 3 screens, 10 nodes, 15 bindings (all unbound)
> - `seed_post_clustering(db)` -- above + 1 collection (Colors), 1 mode (Default), 4 color tokens (extracted), 1 spacing token, bindings updated to proposed
> - `seed_post_curation(db)` -- above + tokens promoted to curated, bindings to bound

### From schema.sql -- Key tables

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id),
>     name TEXT NOT NULL, type TEXT NOT NULL,
>     tier TEXT NOT NULL DEFAULT 'extracted' CHECK(tier IN ('extracted', 'curated', 'aliased')),
>     alias_of INTEGER REFERENCES tokens(id), ...
>     UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS token_values (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, ...
>     UNIQUE(token_id, mode_id)
> );
> CREATE TABLE IF NOT EXISTS node_token_bindings (
>     id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
>     property TEXT NOT NULL, token_id INTEGER REFERENCES tokens(id),
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, confidence REAL,
>     binding_status TEXT NOT NULL DEFAULT 'unbound', UNIQUE(node_id, property)
> );
> CREATE TABLE IF NOT EXISTS export_validations (
>     id INTEGER PRIMARY KEY, run_at TEXT NOT NULL, check_name TEXT NOT NULL,
>     severity TEXT NOT NULL CHECK(severity IN ('error', 'warning', 'info')),
>     message TEXT NOT NULL, affected_ids TEXT, resolved INTEGER NOT NULL DEFAULT 0
> );
> ```

## Task

Create two test files: `tests/test_curation.py` for curation operation tests and status tests, and `tests/test_validation.py` for validation check tests. Use `@pytest.mark.unit` on all tests.

### `tests/test_curation.py`

**Curation operation tests** (at least 20 tests):

1. `test_accept_token(db)`: Seed post-clustering, accept token_id=1. Verify tier='curated', bindings updated to 'bound'.
2. `test_accept_token_nonexistent(db)`: Accept non-existent token raises ValueError.
3. `test_accept_all(db)`: Seed post-clustering, accept_all. Verify all tokens curated, all proposed bindings bound.
4. `test_rename_token_valid(db)`: Seed post-clustering, rename token to "color.background.primary". Verify name changed.
5. `test_rename_token_invalid_name(db)`: Rename to "Invalid Name" raises ValueError.
6. `test_rename_token_uppercase(db)`: Rename to "Color.Surface" raises ValueError.
7. `test_rename_token_duplicate(db)`: Rename to an existing name in same collection raises ValueError.
8. `test_merge_tokens(db)`: Seed post-clustering, merge token 2 into token 1. Verify: all bindings from token 2 now point to token 1, token 2 deleted, token_values for token 2 deleted.
9. `test_merge_tokens_different_collections(db)`: Merge tokens from different collections raises ValueError.
10. `test_merge_tokens_binding_count(db)`: After merge, survivor binding count = original survivor bindings + victim bindings.
11. `test_split_token(db)`: Seed post-clustering, split token 1 by moving 1 binding. Verify: new token created, binding moved, original token retains remaining bindings.
12. `test_split_token_invalid_name(db)`: Split with invalid name raises ValueError.
13. `test_split_token_wrong_bindings(db)`: Split with binding_ids not belonging to the token raises ValueError.
14. `test_split_token_copies_values(db)`: After split, new token has token_values copied from original.
15. `test_reject_token(db)`: Seed post-clustering, reject token 1. Verify: token deleted, bindings reverted to unbound with token_id=NULL.
16. `test_reject_token_nonexistent(db)`: Reject non-existent token raises ValueError.
17. `test_create_alias(db)`: Seed post-curation, create alias "color.bg" -> curated token. Verify: alias created with tier='aliased', alias_of set.
18. `test_create_alias_to_alias_blocked(db)`: Create alias pointing to an alias raises ValueError (or DB trigger fires).
19. `test_create_alias_invalid_name(db)`: Alias with invalid name raises ValueError.
20. `test_create_alias_to_noncurated(db)`: Alias pointing to extracted (not curated) token -- should this be allowed? The spec says alias_targets_curated is a validation check, not an insert-time check. Allow it but validation will flag it.

**Status tests** (at least 5 tests, prefix `test_status_`):

21. `test_status_curation_progress(db)`: Seed post-clustering, get_curation_progress. Verify returns list with proposed and unbound entries.
22. `test_status_curation_progress_empty(db)`: Empty DB returns empty list.
23. `test_status_token_coverage(db)`: Seed post-clustering, get_token_coverage. Verify returns tokens with binding_count > 0.
24. `test_status_format_report(db)`: Seed post-clustering, format_status_report returns non-empty string with "Curation Progress" header.
25. `test_status_dict(db)`: Seed post-clustering, get_status_dict returns dict with all required keys.

### `tests/test_validation.py`

**Validation check tests** (at least 15 tests):

1. `test_check_mode_completeness_pass(db)`: Seed post-curation (all tokens have all mode values), check returns 0 issues.
2. `test_check_mode_completeness_fail(db)`: Seed post-curation, add a second mode but don't add token_values for it. Check returns error issues.
3. `test_check_name_dtcg_valid(db)`: Seed with valid DTCG names. Check returns 0 issues.
4. `test_check_name_dtcg_invalid(db)`: Insert token with name "Invalid Name". Check returns error.
5. `test_check_name_dtcg_allows_numeric(db)`: Name "space.4" is valid. Check returns 0 issues.
6. `test_check_orphan_tokens_none(db)`: Seed post-curation (all tokens have bindings). Check returns 0 warnings.
7. `test_check_orphan_tokens_found(db)`: Insert token with no bindings. Check returns warning.
8. `test_check_binding_coverage(db)`: Seed post-curation. Check returns 1 info result with coverage message.
9. `test_check_alias_targets_curated_pass(db)`: Seed post-curation, create alias pointing to curated token. Check returns 0 errors.
10. `test_check_alias_targets_curated_fail(db)`: Create alias pointing to extracted (not curated) token. Check returns error.
11. `test_check_name_uniqueness_pass(db)`: Seed with unique names. Check returns 0 errors.
12. `test_check_value_format_color_valid(db)`: Token type=color with resolved_value="#09090B". Check returns 0 errors.
13. `test_check_value_format_color_invalid(db)`: Token type=color with resolved_value="not-a-hex". Check returns error.
14. `test_check_value_format_dimension_valid(db)`: Token type=dimension with resolved_value="16". Check returns 0 errors.
15. `test_run_validation_pass(db)`: Seed post-curation (all clean). run_validation returns {"passed": True}.
16. `test_run_validation_fail(db)`: Seed with issues (e.g., bad name). run_validation returns {"passed": False}.
17. `test_run_validation_writes_to_db(db)`: After run_validation, export_validations table has rows.
18. `test_is_export_ready_no_validation(db)`: No validation run yet. is_export_ready returns False.
19. `test_is_export_ready_after_pass(db)`: Run validation on clean data. is_export_ready returns True.
20. `test_is_export_ready_after_fail(db)`: Run validation on data with errors. is_export_ready returns False.

### Helper Functions

Each test file should use the `db` fixture from conftest and call appropriate `seed_*` functions from `tests.fixtures`. For tests that need custom bad data (e.g., invalid token names), insert additional rows after seeding.

## Acceptance Criteria

- [ ] `pytest tests/test_curation.py -v` passes all tests
- [ ] `pytest tests/test_validation.py -v` passes all tests
- [ ] `tests/test_curation.py` has at least 25 test functions (20 curation + 5 status)
- [ ] `tests/test_validation.py` has at least 20 test functions
- [ ] All tests use `@pytest.mark.unit` marker
- [ ] Tests use in-memory SQLite DB via `db` fixture
- [ ] Tests import `seed_post_clustering` and `seed_post_curation` from `tests.fixtures`
- [ ] merge_tokens test verifies all victim bindings reassigned to survivor
- [ ] reject_token test verifies bindings reverted to unbound with token_id=NULL
- [ ] create_alias test verifies alias depth enforcement (direct or via DB trigger)
- [ ] Validation tests verify each of the 7 check types independently
- [ ] run_validation writes results to export_validations table
- [ ] is_export_ready correctly reflects validation state
- [ ] `pytest tests/test_curation.py tests/test_validation.py -v --tb=short` exits 0

## Notes

- Use `seed_post_clustering` for most curation tests (tokens exist in extracted state, bindings are proposed). Use `seed_post_curation` for validation tests and alias tests (tokens are curated).
- For tests that need invalid data, insert it manually after calling the seed function.
- The DB trigger `trg_alias_depth_check` will raise a sqlite3.IntegrityError when attempting to create an alias of an alias. The test should expect either that specific error or a ValueError from the proactive check in `create_alias`.
- The `backup_db` calls in merge/reject/accept_all won't actually backup `:memory:` databases (it returns empty string). This is expected behavior.
- For `test_check_mode_completeness_fail`, you need to add a second mode to a collection without adding corresponding token_values. This simulates the "dark mode added but values not filled in" scenario.