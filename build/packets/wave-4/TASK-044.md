---
taskId: TASK-044
title: "Write integration tests for clustering-to-curation pipeline"
wave: wave-4
testFirst: true
testLevel: integration
dependencies: [TASK-007, TASK-041]
produces:
  - tests/test_curation_integration.py
verify:
  - type: test
    command: 'pytest tests/test_curation_integration.py -v'
    passWhen: 'all tests pass'
contextProfile: full
---

# TASK-044: Write integration tests for clustering-to-curation pipeline

## Spec Context

### From Task Decomposition Guide -- Wave 4 Test Description

> TASK-044: Write integration tests for clustering-to-curation pipeline -- seed post-clustering fixture DB; run curation ops (accept, merge, split); run validation; verify: merged tokens reassign all bindings, rejected tokens revert bindings to unbound, alias chains resolve, validation gate catches incomplete curation, backup created before bulk ops.

### From Task Decomposition Guide -- Integration Test Requirements

> Integration test tasks (wave 1+) MUST:
> - Import and use fixture factory functions from `tests/fixtures.py`
> - Test the actual boundary between current wave modules and prior wave outputs -- NOT re-mock what the prior wave produces
> - Verify FK integrity, data shape correctness, and state transitions across module boundaries
> - Use real DB connections (in-memory SQLite), not mock DB objects

### From tests/fixtures.py (produced by TASK-007)

> Exports:
> - `seed_post_clustering(db) -> sqlite3.Connection`
>   - 1 file (id=1), 3 screens, 10 nodes, 15 bindings
>   - 1 token_collection "Colors" (id=1), 1 token_mode "Default" (id=1, is_default=1)
>   - 4 color tokens: color.surface.primary (#09090B), color.surface.secondary (#18181B), color.border.default (#D4D4D8), color.text.primary (#FFFFFF) -- all tier="extracted"
>   - 5 color bindings updated: token_id set, binding_status="proposed", confidence=1.0 or 0.95
>   - 1 spacing collection, 1 spacing token space.4 with value "16"
> - `seed_post_curation(db) -> sqlite3.Connection` -- above + tokens curated, bindings bound

### From dd/curate.py (produced by TASK-040)

> Exports:
> - `accept_token(conn, token_id) -> dict`
> - `accept_all(conn, file_id, db_path=None) -> dict`
> - `rename_token(conn, token_id, new_name) -> dict`
> - `merge_tokens(conn, survivor_id, victim_id, db_path=None) -> dict`
> - `split_token(conn, token_id, new_name, binding_ids) -> dict`
> - `reject_token(conn, token_id, db_path=None) -> dict`
> - `create_alias(conn, alias_name, target_token_id, collection_id) -> dict`

### From dd/validate.py (produced by TASK-041)

> Exports:
> - `run_validation(conn, file_id) -> dict`
> - `is_export_ready(conn) -> bool`
> - All individual check functions

### From dd/cluster.py (produced by TASK-034)

> Exports:
> - `run_clustering(conn, file_id, color_threshold, agent_id) -> dict`

### From schema.sql -- Key tables and views

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
> LEFT JOIN nodes n ON ntb.node_id = n.id GROUP BY t.id ORDER BY binding_count DESC;
>
> CREATE VIEW v_export_readiness AS
> SELECT check_name, severity, COUNT(*) AS issue_count, SUM(resolved) AS resolved_count
> FROM export_validations
> WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
> GROUP BY check_name, severity
> ORDER BY CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END;
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

Create `tests/test_curation_integration.py` with integration tests that verify the boundary between clustering output (Wave 3) and curation + validation (Wave 4). Tests seed the DB with real clustering output, run curation operations, then run validation. Use `@pytest.mark.integration` on all tests.

### Test Functions

1. **`test_accept_merge_then_validate(db)`**:
   - Seed post-clustering (tokens are extracted, bindings are proposed).
   - Accept token 1 (promote to curated, bindings to bound).
   - Merge token 3 into token 2 (reassign bindings).
   - Accept token 2 (now with merged bindings).
   - Run validation.
   - Verify:
     - Token 1 has tier='curated', its bindings have status='bound'
     - Token 3 no longer exists in tokens table
     - All of token 3's former bindings now point to token 2
     - Token 2 has tier='curated' with correct binding count
     - Validation passes (no errors) for the curated tokens
     - `v_token_coverage` shows correct binding counts for survivors

2. **`test_reject_reverts_bindings_to_unbound(db)`**:
   - Seed post-clustering.
   - Count proposed bindings for token 1.
   - Reject token 1.
   - Verify:
     - Token 1 no longer exists in tokens table
     - Token 1's former bindings now have token_id=NULL and binding_status='unbound'
     - Total binding count unchanged (bindings still exist, just unbound)
     - `v_curation_progress` reflects the change (more unbound, fewer proposed)

3. **`test_split_preserves_fk_integrity(db)`**:
   - Seed post-clustering.
   - Get binding IDs for token 1.
   - Split token 1, moving 1 binding to new token "color.surface.alt".
   - Verify:
     - New token exists with name "color.surface.alt", tier='extracted'
     - Moved binding now references new token
     - Remaining bindings still reference original token
     - New token has token_values (copied from original)
     - All FKs valid: `SELECT COUNT(*) FROM node_token_bindings WHERE token_id NOT IN (SELECT id FROM tokens) AND token_id IS NOT NULL` = 0

4. **`test_alias_chain_resolves(db)`**:
   - Seed post-curation (tokens curated).
   - Create alias "color.bg" -> token 1 (color.surface.primary).
   - Query `v_resolved_tokens` for the alias.
   - Verify:
     - Alias row exists with tier='aliased'
     - `v_resolved_tokens` resolves the alias to the target's value
     - The alias_target_name matches the target token's name

5. **`test_validation_catches_incomplete_curation(db)`**:
   - Seed post-clustering (tokens still extracted, not curated).
   - DO NOT accept any tokens.
   - Create an alias pointing to an extracted (non-curated) token.
   - Run validation.
   - Verify:
     - `run_validation` returns `{"passed": False}`
     - `alias_targets_curated` check produces error(s)
     - `is_export_ready` returns False
     - `v_export_readiness` view shows the error

6. **`test_validation_passes_after_full_curation(db)`**:
   - Seed post-clustering.
   - Accept all tokens via `accept_all`.
   - Run validation.
   - Verify:
     - `run_validation` returns `{"passed": True}` (or passes -- may have warnings but no errors)
     - `is_export_ready` returns True
     - `export_validations` table has rows from this run
     - No error-severity rows in the latest validation run

7. **`test_merge_then_validate_binding_coverage(db)`**:
   - Seed post-clustering.
   - Accept all tokens.
   - Run validation.
   - Query `v_token_coverage`.
   - Verify:
     - Every token has binding_count > 0 (no orphans after accept_all)
     - binding_coverage check returns info with >0% bound

8. **`test_curation_progress_view_reflects_operations(db)`**:
   - Seed post-clustering.
   - Query `v_curation_progress`: should show proposed > 0, unbound > 0.
   - Accept all tokens.
   - Query `v_curation_progress` again: proposed should be 0, bound should have increased.
   - Reject one token.
   - Query `v_curation_progress` again: unbound should have increased.
   - Verify the view accurately reflects each state change.

9. **`test_validation_mode_completeness_with_new_mode(db)`**:
   - Seed post-curation.
   - Add a second mode "Dark" to the Colors collection: `INSERT INTO token_modes (collection_id, name, is_default) VALUES (1, 'Dark', 0)`.
   - DO NOT add token_values for the Dark mode.
   - Run validation.
   - Verify:
     - `mode_completeness` check produces errors (one per token missing Dark mode value)
     - `run_validation` returns `{"passed": False}`

10. **`test_no_orphan_records_after_curation_sequence(db)`**:
    - Seed post-clustering.
    - Accept token 1, merge 3 into 2, reject 4, accept 2.
    - Verify no orphan records:
      - Every `node_token_bindings.token_id` (non-NULL) exists in `tokens.id`
      - Every `token_values.token_id` exists in `tokens.id`
      - Every `token_values.mode_id` exists in `token_modes.id`

## Acceptance Criteria

- [ ] `pytest tests/test_curation_integration.py -v` passes all tests
- [ ] At least 10 test functions
- [ ] All tests use `@pytest.mark.integration` marker
- [ ] Tests use real DB (in-memory SQLite), not mock DB
- [ ] Tests start from `seed_post_clustering` or `seed_post_curation` fixture output
- [ ] Tests run REAL curation functions (accept, merge, split, reject) on real clustering output
- [ ] Merged tokens verified: all victim bindings reassigned to survivor
- [ ] Rejected tokens verified: bindings reverted to unbound
- [ ] Alias chains verified via `v_resolved_tokens` view
- [ ] Validation gate tested: catches incomplete curation, passes after full curation
- [ ] Mode completeness validation tested with multi-mode scenario
- [ ] FK integrity verified after complex curation sequences
- [ ] `v_curation_progress` view correctly reflects state changes
- [ ] `pytest tests/test_curation_integration.py -v --tb=short` exits 0

## Notes

- Use `@pytest.mark.timeout(30)` on all tests as safety.
- The fixture `seed_post_clustering` provides 5 tokens (4 color + 1 spacing). Curation operations should reference these token IDs directly (1-5) since the fixtures use deterministic IDs.
- The validation tests here focus on the boundary between curation and validation -- they verify that curation operations leave the DB in states that validation correctly identifies as pass/fail.
- The mode completeness test (test 9) is important: it simulates the common scenario of adding a dark mode but forgetting to fill in values, which should block export.
- Import `seed_post_clustering` and `seed_post_curation` from `tests.fixtures`.
- Import curation functions from `dd.curate` and validation functions from `dd.validate`.