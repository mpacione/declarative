---
taskId: TASK-070
title: "Implement drift detection (UC-6)"
wave: wave-7
testFirst: false
testLevel: unit
dependencies: [TASK-002]
produces:
  - dd/drift.py
verify:
  - type: typecheck
    command: 'python -c "from dd.drift import detect_drift, compare_token_values, parse_figma_variables_for_drift, generate_drift_report, update_sync_statuses"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_drift.py -v'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-070: Implement drift detection (UC-6)

## Spec Context

### From User Requirements Spec -- UC-6: Detect Drift

> **Actor:** U3
> **Trigger:** Periodic check, or user requests a sync audit.
> **Flow:**
> 1. System re-reads current Figma variable values via `figma_get_variables` or `use_figma`.
> 2. System compares Figma values against DB `token_values.resolved_value` for each token.
> 3. Divergences flagged: token still `pending` (never exported to Figma), token value in Figma differs from DB (`synced` -> `drifted`), token exists in Figma but not DB (`figma_only`), token exists in code but not Figma (`code_only`).
> 4. System produces a drift report: N tokens synced, M drifted, L missing from Figma, K missing from code.
> 5. User chooses resolution: update DB from Figma, update Figma from DB, or flag for manual review.
> **Acceptance:**
> - Drift detection runs without modifying any data (read-only until user confirms resolution).
> - Every token has a current `sync_status` that accurately reflects its state across DB, Figma, and code.
> - Drifted tokens show both the DB value and the Figma value for comparison.
> - Drift report is queryable via `v_drift_report` -- shows token name, DB value, mode, collection, and sync status for all non-synced tokens.

### From User Requirements Spec -- FR-2.6

> FR-2.6: Sync status tracking: `pending` (created in DB, not yet exported), `figma_only` (exists in Figma but no code mapping), `code_only` (exists in code but not Figma), `synced` (DB + Figma + code aligned), `drifted` (values diverge between systems).

### From User Requirements Spec -- FR-5.10

> FR-5.10: Drift report view (`v_drift_report`) -- per-token sync status between DB and Figma, supporting UC-6.

### From schema.sql -- tokens table

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id),
>     name            TEXT NOT NULL,
>     type            TEXT NOT NULL,
>     tier            TEXT NOT NULL DEFAULT 'extracted'
>                     CHECK(tier IN ('extracted', 'curated', 'aliased')),
>     alias_of        INTEGER REFERENCES tokens(id),
>     description     TEXT,
>     figma_variable_id TEXT,
>     sync_status     TEXT NOT NULL DEFAULT 'pending'
>                     CHECK(sync_status IN ('pending', 'figma_only', 'code_only', 'synced', 'drifted')),
>     created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(collection_id, name)
> );
> ```

### From schema.sql -- token_values table

> ```sql
> CREATE TABLE IF NOT EXISTS token_values (
>     id              INTEGER PRIMARY KEY,
>     token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id         INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(token_id, mode_id)
> );
> ```

### From schema.sql -- token_collections, token_modes tables

> ```sql
> CREATE TABLE IF NOT EXISTS token_collections (
>     id              INTEGER PRIMARY KEY,
>     file_id         INTEGER NOT NULL REFERENCES files(id),
>     figma_id        TEXT,
>     name            TEXT NOT NULL,
>     description     TEXT,
>     created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
> );
>
> CREATE TABLE IF NOT EXISTS token_modes (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
>     figma_mode_id   TEXT,
>     name            TEXT NOT NULL,
>     is_default      INTEGER NOT NULL DEFAULT 0,
>     UNIQUE(collection_id, name)
> );
> ```

### From schema.sql -- v_drift_report view

> ```sql
> CREATE VIEW v_drift_report AS
> SELECT
>     t.id AS token_id,
>     t.name AS token_name,
>     t.type,
>     t.sync_status,
>     t.figma_variable_id,
>     tv.resolved_value AS db_value,
>     tm.name AS mode_name,
>     tc.name AS collection_name
> FROM tokens t
> JOIN token_values tv ON tv.token_id = t.id
> JOIN token_modes tm ON tm.id = tv.mode_id
> JOIN token_collections tc ON tc.id = t.collection_id
> WHERE t.sync_status IN ('pending', 'drifted', 'figma_only', 'code_only')
> ORDER BY t.sync_status, tc.name, t.name;
> ```

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

### From dd/types.py (produced by TASK-003)

> Exports:
> - `SyncStatus` enum: PENDING, FIGMA_ONLY, CODE_ONLY, SYNCED, DRIFTED

### From dd/export_figma_vars.py (produced by TASK-050, TASK-051)

> Exports:
> - `figma_path_to_dtcg(figma_name: str) -> str` -- slashes to dots
> - `dtcg_to_figma_path(dtcg_name: str) -> str` -- dots to slashes

## Task

Create `dd/drift.py` implementing drift detection from UC-6. This module compares DB token values against Figma variable values (provided by an agent via MCP) and updates sync_status accordingly. The module does NOT call MCP directly -- it receives Figma data as parameters.

1. **`parse_figma_variables_for_drift(raw_response: dict) -> list[dict]`**:
   - Accept the raw response from `figma_get_variables` MCP call.
   - Parse into a flat list of variable value dicts:
     ```python
     [
         {
             "variable_id": "VariableID:123:456",
             "name": "color/surface/primary",  # Figma slash-path
             "dtcg_name": "color.surface.primary",  # converted to dot-path
             "collection_name": "Colors",
             "values": {"Light": "#09090B", "Dark": "#FAFAFA"},  # mode_name -> value
         },
         ...
     ]
     ```
   - Handle the expected Figma response shape with `collections` containing `variables` and `modes`.
   - Handle alternate shapes gracefully (list of variables, or flat structure).
   - Import and use `figma_path_to_dtcg` from `dd.export_figma_vars` for name conversion.
   - Return the parsed list.

2. **`compare_token_values(conn, file_id: int, figma_variables: list[dict]) -> dict`**:
   - Compare DB token values against Figma variable values.
   - Query all tokens for this file with their values per mode:
     ```sql
     SELECT t.id, t.name, t.type, t.figma_variable_id, t.sync_status,
            tv.resolved_value AS db_value, tm.name AS mode_name,
            tc.name AS collection_name
     FROM tokens t
     JOIN token_collections tc ON t.collection_id = tc.id
     JOIN token_values tv ON tv.token_id = t.id
     JOIN token_modes tm ON tm.id = tv.mode_id
     WHERE tc.file_id = ? AND t.tier IN ('curated', 'aliased')
     ORDER BY t.name, tm.name
     ```
   - Build a lookup from DB tokens by (name, mode_name) -> db_value.
   - Build a lookup from Figma variables by (dtcg_name, mode_name) -> figma_value.
   - For each DB token:
     - If token has no figma_variable_id: status = `"pending"`.
     - If token exists in DB but not in Figma variables: status = `"pending"` (never exported) or `"code_only"` if it has code_mappings.
     - If token exists in both DB and Figma:
       - Compare values per mode. Normalize both values for comparison (strip whitespace, uppercase hex).
       - If all mode values match: status = `"synced"`.
       - If any mode value differs: status = `"drifted"`, record both db_value and figma_value.
   - For each Figma variable not in DB: status = `"figma_only"`.
   - Check code_mappings to determine `"code_only"` status:
     ```sql
     SELECT DISTINCT token_id FROM code_mappings
     WHERE token_id IN (SELECT id FROM tokens t JOIN token_collections tc ON t.collection_id = tc.id WHERE tc.file_id = ?)
     ```
   - Return a structured dict:
     ```python
     {
         "synced": [{"token_id": int, "name": str, ...}, ...],
         "drifted": [{"token_id": int, "name": str, "mode": str, "db_value": str, "figma_value": str}, ...],
         "pending": [{"token_id": int, "name": str}, ...],
         "figma_only": [{"name": str, "variable_id": str, "values": dict}, ...],
         "code_only": [{"token_id": int, "name": str}, ...],
     }
     ```

3. **`normalize_value_for_comparison(value: str, token_type: str) -> str`**:
   - Normalize a value for drift comparison to avoid false positives:
   - Strip whitespace.
   - For colors: uppercase hex, strip leading `#`, normalize 8-digit to 6-digit if alpha is FF.
   - For dimensions: strip trailing `px`, convert to float then back to string to normalize `"16"` vs `"16.0"`.
   - For font families: strip surrounding quotes.
   - Return the normalized string.

4. **`update_sync_statuses(conn, file_id: int, comparison: dict) -> dict`**:
   - Update `tokens.sync_status` based on comparison results.
   - For each token in `synced`: UPDATE sync_status = 'synced'.
   - For each token in `drifted`: UPDATE sync_status = 'drifted'.
   - For each token in `pending`: UPDATE sync_status = 'pending'.
   - For each token in `code_only`: UPDATE sync_status = 'code_only'.
   - `figma_only` tokens are NOT in the DB, so no update needed (they're reported only).
   - Also update `updated_at` timestamp.
   - Return: `{"updated": int, "synced": int, "drifted": int, "pending": int, "code_only": int, "figma_only": int}`.
   - Commit after all updates.

5. **`generate_drift_report(conn, file_id: int) -> dict`**:
   - Query `v_drift_report` for this file (filter by `tc.file_id` via JOIN -- the view doesn't filter by file, so add WHERE clause or query raw tables).
   - Also query overall sync status distribution:
     ```sql
     SELECT t.sync_status, COUNT(*) AS count
     FROM tokens t
     JOIN token_collections tc ON t.collection_id = tc.id
     WHERE tc.file_id = ?
     GROUP BY t.sync_status
     ```
   - Return:
     ```python
     {
         "summary": {"synced": int, "drifted": int, "pending": int, "code_only": int, "figma_only": int},
         "drifted_tokens": [{"token_name": str, "db_value": str, "mode_name": str, "collection_name": str}, ...],
         "pending_tokens": [{"token_name": str, ...}, ...],
     }
     ```

6. **`detect_drift(conn, file_id: int, figma_variables_response: dict) -> dict`**:
   - Main entry point. Combines all steps:
   - Call `parse_figma_variables_for_drift(figma_variables_response)`.
   - Call `compare_token_values(conn, file_id, parsed_variables)`.
   - Call `update_sync_statuses(conn, file_id, comparison)`.
   - Call `generate_drift_report(conn, file_id)`.
   - Return a combined dict:
     ```python
     {
         "comparison": comparison_dict,
         "updates": update_summary,
         "report": drift_report,
     }
     ```

7. **`detect_drift_readonly(conn, file_id: int, figma_variables_response: dict) -> dict`**:
   - Read-only version that does NOT update sync_statuses.
   - Calls `parse_figma_variables_for_drift` and `compare_token_values` only.
   - Returns the comparison dict without modifying any DB data.
   - Per UC-6: "Drift detection runs without modifying any data (read-only until user confirms resolution)."

## Acceptance Criteria

- [ ] `python -c "from dd.drift import detect_drift, detect_drift_readonly, compare_token_values, parse_figma_variables_for_drift, generate_drift_report, update_sync_statuses, normalize_value_for_comparison"` exits 0
- [ ] `normalize_value_for_comparison("#09090B", "color")` == `normalize_value_for_comparison("#09090b", "color")` (case-insensitive hex)
- [ ] `normalize_value_for_comparison("16", "dimension")` == `normalize_value_for_comparison("16.0", "dimension")`
- [ ] `normalize_value_for_comparison('"Inter"', "fontFamily")` == `normalize_value_for_comparison("Inter", "fontFamily")`
- [ ] `parse_figma_variables_for_drift` extracts variable IDs, names, and per-mode values
- [ ] `parse_figma_variables_for_drift` converts Figma slash-paths to DTCG dot-paths
- [ ] `compare_token_values` identifies synced tokens (matching values)
- [ ] `compare_token_values` identifies drifted tokens (differing values) with both db_value and figma_value
- [ ] `compare_token_values` identifies pending tokens (no figma_variable_id)
- [ ] `compare_token_values` identifies figma_only variables (in Figma but not in DB)
- [ ] `update_sync_statuses` updates tokens.sync_status in the DB
- [ ] `detect_drift_readonly` does NOT modify any DB data
- [ ] `detect_drift` calls update_sync_statuses and returns combined result
- [ ] `generate_drift_report` returns summary counts and lists of drifted/pending tokens
- [ ] After `detect_drift`, querying `v_drift_report` returns correct drifted tokens

## Notes

- This module processes Figma data provided by an agent with MCP access. It does NOT call MCP directly. The calling agent calls `figma_get_variables` and passes the response to `detect_drift`.
- The `detect_drift_readonly` function is the default first step per UC-6. The user reviews the drift report, then explicitly confirms whether to update statuses via `detect_drift` or `update_sync_statuses`.
- Value normalization is critical to avoid false drift reports. Hex colors may differ in case (#09090B vs #09090b), dimensions may have trailing .0, font families may have surrounding quotes.
- The `figma_only` category represents variables that exist in Figma but were not created by this pipeline. These could be manually-created Figma variables or variables from another tool.
- Import `figma_path_to_dtcg` from `dd.export_figma_vars` for name conversion. If that module isn't available, implement the simple `name.replace("/", ".")` inline.