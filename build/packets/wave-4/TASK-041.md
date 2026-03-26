---
taskId: TASK-041
title: "Implement pre-export validation (Phase 6.5)"
wave: wave-4
testFirst: true
testLevel: unit
dependencies: [TASK-002, TASK-003]
produces:
  - dd/validate.py
verify:
  - type: typecheck
    command: 'python -c "from dd.validate import run_validation, check_mode_completeness, check_name_dtcg_compliant, check_orphan_tokens, check_binding_coverage, check_alias_targets_curated, check_name_uniqueness, check_value_format"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_validation.py -v'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-041: Implement pre-export validation (Phase 6.5)

## Spec Context

### From Technical Design Spec -- Phase 6.5: Pre-Export Validation

> **Tool:** Local Python, no MCP calls.
> **Runs between curation (Phase 6) and Figma export (Phase 7). Blocks export if errors exist.**
>
> Validation checks written to `export_validations` table:
>
> | Check | Severity | Rule |
> |---|---|---|
> | `mode_completeness` | error | Every token in a collection has a value for every mode in that collection |
> | `name_dtcg_compliant` | error | Token names match `^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*$` pattern |
> | `orphan_tokens` | warning | No tokens with 0 bindings (created but never assigned) |
> | `binding_coverage` | info | Report: N% of bindings are bound, M% proposed, K% unbound |
> | `alias_targets_curated` | error | Every alias points to a token with `tier = curated` (not extracted) |
> | `name_uniqueness` | error | No duplicate token names within a collection |
> | `value_format` | error | All `resolved_value` entries match expected format for their token type |
>
> Export proceeds only if zero `severity = 'error'` rows exist in the latest validation run. Warnings are logged. The `v_export_readiness` view shows the summary.

### From User Requirements Spec -- UC-3: Export to Figma

> - Pre-export validation gate passes before any Figma write: `v_export_readiness` shows 0 errors.
> - Export is blocked if validation gate has error-severity issues. Warnings are logged but don't block.

### From schema.sql -- export_validations table

> ```sql
> CREATE TABLE IF NOT EXISTS export_validations (
>     id              INTEGER PRIMARY KEY,
>     run_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     check_name      TEXT NOT NULL,
>     severity        TEXT NOT NULL CHECK(severity IN ('error', 'warning', 'info')),
>     message         TEXT NOT NULL,
>     affected_ids    TEXT,
>     resolved        INTEGER NOT NULL DEFAULT 0
> );
> ```

### From schema.sql -- v_export_readiness view

> ```sql
> CREATE VIEW v_export_readiness AS
> SELECT
>     check_name,
>     severity,
>     COUNT(*) AS issue_count,
>     SUM(resolved) AS resolved_count
> FROM export_validations
> WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
> GROUP BY check_name, severity
> ORDER BY
>     CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END;
> ```

### From schema.sql -- tokens, token_values, token_collections, token_modes, node_token_bindings

> ```sql
> CREATE TABLE IF NOT EXISTS token_collections (
>     id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id),
>     figma_id TEXT, name TEXT NOT NULL, description TEXT, created_at TEXT
> );
> CREATE TABLE IF NOT EXISTS token_modes (
>     id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
>     figma_mode_id TEXT, name TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0,
>     UNIQUE(collection_id, name)
> );
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
> ```

### From schema.sql -- v_curation_progress view

> ```sql
> CREATE VIEW v_curation_progress AS
> SELECT
>     binding_status,
>     COUNT(*) AS binding_count,
>     ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM node_token_bindings), 1) AS pct
> FROM node_token_bindings
> GROUP BY binding_status
> ORDER BY CASE binding_status WHEN 'bound' THEN 1 WHEN 'proposed' THEN 2
>          WHEN 'overridden' THEN 3 WHEN 'unbound' THEN 4 END;
> ```

### From dd/types.py (produced by TASK-003)

> Exports:
> - `Severity` enum: ERROR, WARNING, INFO
> - `DTCGType` enum: COLOR, DIMENSION, FONT_FAMILY, FONT_WEIGHT, NUMBER, SHADOW, BORDER, TRANSITION, GRADIENT

## Task

Create `dd/validate.py` implementing the pre-export validation gate from Phase 6.5. Each check is a standalone function that returns a list of validation issue dicts. The main `run_validation` function runs all checks, writes results to `export_validations`, and returns pass/fail.

1. **`check_mode_completeness(conn, file_id: int) -> list[dict]`**:
   - For each token in collections belonging to `file_id`, check that a `token_values` row exists for every mode in that token's collection.
   - Query: for each collection, get all mode_ids. For each token in the collection, check if all mode_ids have a corresponding token_values row.
   - SQL approach:
     ```sql
     SELECT t.id AS token_id, t.name, tc.name AS collection_name, tm.name AS mode_name
     FROM tokens t
     JOIN token_collections tc ON t.collection_id = tc.id
     CROSS JOIN token_modes tm ON tm.collection_id = tc.id
     LEFT JOIN token_values tv ON tv.token_id = t.id AND tv.mode_id = tm.id
     WHERE tc.file_id = ? AND tv.id IS NULL AND t.alias_of IS NULL
     ```
   - For each missing value, return: `{"check_name": "mode_completeness", "severity": "error", "message": f"Token '{name}' in collection '{collection_name}' missing value for mode '{mode_name}'", "affected_ids": json.dumps([token_id])}`.

2. **`check_name_dtcg_compliant(conn, file_id: int) -> list[dict]`**:
   - Query all tokens in collections for this file_id.
   - Check each name against pattern `^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*$`.
   - Also allow numeric segments for spacing multipliers: `^[a-z][a-z0-9]*(\.[a-z0-9]+)*$` (e.g., "space.4" is valid).
   - Return error for each non-compliant name.

3. **`check_orphan_tokens(conn, file_id: int) -> list[dict]`**:
   - Query tokens with zero bindings:
     ```sql
     SELECT t.id, t.name FROM tokens t
     JOIN token_collections tc ON t.collection_id = tc.id
     LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
     WHERE tc.file_id = ? AND ntb.id IS NULL AND t.alias_of IS NULL
     ```
   - Return warning for each orphan.

4. **`check_binding_coverage(conn, file_id: int) -> list[dict]`**:
   - Query `v_curation_progress` (or compute directly).
   - Build an info message: "Binding coverage: N% bound, M% proposed, K% unbound".
   - Return a single info-level result.

5. **`check_alias_targets_curated(conn, file_id: int) -> list[dict]`**:
   - Query aliased tokens whose target is not curated:
     ```sql
     SELECT t.id, t.name, target.name AS target_name, target.tier AS target_tier
     FROM tokens t
     JOIN tokens target ON t.alias_of = target.id
     JOIN token_collections tc ON t.collection_id = tc.id
     WHERE tc.file_id = ? AND t.tier = 'aliased' AND target.tier != 'curated'
     ```
   - Return error for each invalid alias.

6. **`check_name_uniqueness(conn, file_id: int) -> list[dict]`**:
   - Query for duplicate names within a collection:
     ```sql
     SELECT t.collection_id, t.name, COUNT(*) AS cnt
     FROM tokens t
     JOIN token_collections tc ON t.collection_id = tc.id
     WHERE tc.file_id = ?
     GROUP BY t.collection_id, t.name
     HAVING COUNT(*) > 1
     ```
   - Return error for each duplicate. The UNIQUE constraint should prevent this, but check anyway for robustness.

7. **`check_value_format(conn, file_id: int) -> list[dict]`**:
   - Query all token_values with their token type.
   - Validate resolved_value format per type:
     - `color`: must match `^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$`
     - `dimension`: must be a valid number (int or float)
     - `fontFamily`: must be a non-empty string
     - `fontWeight`: must be a valid number (100-900 range)
     - `number`: must be a valid number
   - Return error for each invalid value.

8. **`run_validation(conn, file_id: int) -> dict`**:
   - Run all 7 checks in sequence.
   - Generate a `run_at` timestamp (ISO 8601 UTC).
   - INSERT each issue into `export_validations` with the shared `run_at`.
   - Count errors, warnings, info.
   - Determine pass/fail: pass if 0 errors.
   - Return: `{"passed": bool, "errors": int, "warnings": int, "info": int, "run_at": str, "issues": list[dict]}`.

9. **`is_export_ready(conn) -> bool`**:
   - Query `v_export_readiness`.
   - Return True if no rows with severity='error' exist (or if no validation has been run -- in which case return False to force running validation first).
   - Specifically: check if any validation has been run (any rows in export_validations). If not, return False. If yes, check if the latest run has any error-severity issues.

## Acceptance Criteria

- [ ] `python -c "from dd.validate import run_validation, check_mode_completeness, check_name_dtcg_compliant, check_orphan_tokens, check_binding_coverage, check_alias_targets_curated, check_name_uniqueness, check_value_format, is_export_ready"` exits 0
- [ ] `check_mode_completeness` finds tokens missing mode values and returns error-severity issues
- [ ] `check_name_dtcg_compliant` catches names like "Invalid Name" or "UPPERCASE"
- [ ] `check_name_dtcg_compliant` accepts names like "color.surface.primary" and "space.4"
- [ ] `check_orphan_tokens` finds tokens with zero bindings and returns warning-severity issues
- [ ] `check_binding_coverage` returns a single info-severity result with coverage percentages
- [ ] `check_alias_targets_curated` finds aliases pointing to non-curated targets
- [ ] `check_name_uniqueness` detects duplicate names within a collection
- [ ] `check_value_format` validates color hex format, numeric dimensions, fontWeight range
- [ ] `run_validation` writes all issues to `export_validations` table
- [ ] `run_validation` returns `{"passed": True}` when no errors exist
- [ ] `run_validation` returns `{"passed": False}` when errors exist
- [ ] `is_export_ready` returns True when latest validation has no errors
- [ ] `is_export_ready` returns False when no validation has been run
- [ ] `v_export_readiness` view returns correct aggregation after run_validation

## Notes

- Each check function is independent and testable in isolation.
- The `run_at` timestamp groups validation results from the same run. The `v_export_readiness` view uses `MAX(run_at)` to only show the latest run.
- The DTCG name pattern allows segments starting with digits for spacing multipliers (e.g., "space.4"). Use the more permissive regex: `^[a-z][a-z0-9]*(\.[a-z0-9]+)*$`.
- `check_mode_completeness` skips aliased tokens (they don't have their own values; they reference the target's values).
- The `affected_ids` column stores a JSON array of token/binding IDs for diagnostic purposes.