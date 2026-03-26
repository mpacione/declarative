---
taskId: TASK-051
title: "Implement variable ID writeback"
wave: wave-5
testFirst: true
testLevel: unit
dependencies: [TASK-050]
produces:
  - dd/export_figma_vars.py
verify:
  - type: typecheck
    command: 'python -c "from dd.export_figma_vars import writeback_variable_ids, parse_figma_variables_response"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_export_figma.py -k "writeback or sync_status" -v'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-051: Implement variable ID writeback

## Spec Context

### From Technical Design Spec -- Phase 7: Figma Variable Export

> **Post-creation:** Query `figma_get_variables` to retrieve Figma variable IDs. Write back to `tokens.figma_variable_id`. Update `sync_status` to `synced`.

### From User Requirements Spec -- FR-4.5

> FR-4.5: Write back Figma variable IDs to DB after creation.

### From User Requirements Spec -- FR-2.6

> FR-2.6: Sync status tracking: `pending` (created in DB, not yet exported), `figma_only` (exists in Figma but no code mapping), `code_only` (exists in code but not Figma), `synced` (DB + Figma + code aligned), `drifted` (values diverge between systems).

### From schema.sql -- tokens table (relevant columns)

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

### From schema.sql -- token_collections table

> ```sql
> CREATE TABLE IF NOT EXISTS token_collections (
>     id              INTEGER PRIMARY KEY,
>     file_id         INTEGER NOT NULL REFERENCES files(id),
>     figma_id        TEXT,
>     name            TEXT NOT NULL,
>     description     TEXT,
>     created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
> );
> ```

### From schema.sql -- token_modes table

> ```sql
> CREATE TABLE IF NOT EXISTS token_modes (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
>     figma_mode_id   TEXT,
>     name            TEXT NOT NULL,
>     is_default      INTEGER NOT NULL DEFAULT 0,
>     UNIQUE(collection_id, name)
> );
> ```

### From dd/export_figma_vars.py (produced by TASK-050)

> Exports:
> - `generate_variable_payloads(conn, file_id) -> list[dict]`
> - `dtcg_to_figma_path(dtcg_name) -> str` -- dots to slashes
> - `map_token_type_to_figma(token_type, token_name) -> str`
> - `query_exportable_tokens(conn, file_id) -> list[dict]`

### From dd/types.py (produced by TASK-003)

> Exports:
> - `SyncStatus` enum: PENDING, FIGMA_ONLY, CODE_ONLY, SYNCED, DRIFTED

## Task

Extend `dd/export_figma_vars.py` by adding functions for variable ID writeback after Figma variables have been created. The agent calls `figma_setup_design_tokens` with the generated payloads, then calls `figma_get_variables` to retrieve the created variable IDs, and passes the response to these writeback functions.

1. **`parse_figma_variables_response(response: dict) -> list[dict]`**:
   - Accept the raw response from `figma_get_variables` MCP call.
   - The response structure is expected to contain variable collections with variables.
   - Expected shape (based on Figma API patterns):
     ```python
     {
         "collections": [
             {
                 "id": "VariableCollectionID:xxx",
                 "name": "Colors",
                 "modes": [{"id": "modeId:xxx", "name": "Light"}, ...],
                 "variables": [
                     {
                         "id": "VariableID:123:456",
                         "name": "color/surface/primary",
                         "type": "COLOR",
                         ...
                     },
                     ...
                 ]
             }
         ]
     }
     ```
   - Flatten into a list of dicts: `[{"variable_id": str, "name": str, "collection_name": str, "collection_id": str, "modes": list[dict]}, ...]`.
   - Convert Figma slash-path names back to DTCG dot-path for matching: `color/surface/primary` -> `color.surface.primary`.
   - Handle alternate response shapes gracefully (the exact shape depends on the MCP tool version). If response is a list instead of a dict with "collections", try to adapt.
   - Return the parsed list.

2. **`figma_path_to_dtcg(figma_name: str) -> str`**:
   - Convert Figma slash-path back to DTCG dot-path: `color/surface/primary` -> `color.surface.primary`.
   - Simply replace all `/` with `.`.

3. **`writeback_variable_ids(conn, file_id: int, figma_variables: list[dict]) -> dict`**:
   - Accept the parsed Figma variables list from `parse_figma_variables_response`.
   - For each Figma variable:
     - Convert its name from Figma slash-path to DTCG dot-path via `figma_path_to_dtcg`.
     - Look up the matching token in the DB by name and collection:
       ```sql
       SELECT t.id FROM tokens t
       JOIN token_collections tc ON t.collection_id = tc.id
       WHERE tc.file_id = ? AND t.name = ?
       ```
     - UPDATE `tokens SET figma_variable_id = ?, sync_status = 'synced', updated_at = strftime(...)` WHERE `id = ?`.
   - Also update collection and mode Figma IDs if available:
     - UPDATE `token_collections SET figma_id = ?` WHERE `file_id = ? AND name = ?`.
     - UPDATE `token_modes SET figma_mode_id = ?` WHERE `collection_id = ? AND name = ?`.
   - Return summary dict: `{"tokens_updated": int, "tokens_not_found": int, "collections_updated": int, "modes_updated": int}`.
   - Commit after all updates.

4. **`writeback_variable_ids_from_response(conn, file_id: int, raw_response: dict) -> dict`**:
   - Convenience wrapper that calls `parse_figma_variables_response(raw_response)` then `writeback_variable_ids(conn, file_id, parsed)`.
   - Return the summary dict.

5. **`get_sync_status_summary(conn, file_id: int) -> dict`**:
   - Query sync status distribution for tokens in this file:
     ```sql
     SELECT t.sync_status, COUNT(*) AS count
     FROM tokens t
     JOIN token_collections tc ON t.collection_id = tc.id
     WHERE tc.file_id = ?
     GROUP BY t.sync_status
     ```
   - Return dict mapping status -> count: `{"pending": N, "synced": M, ...}`.

## Acceptance Criteria

- [ ] `python -c "from dd.export_figma_vars import writeback_variable_ids, parse_figma_variables_response, figma_path_to_dtcg, writeback_variable_ids_from_response, get_sync_status_summary"` exits 0
- [ ] `figma_path_to_dtcg("color/surface/primary")` returns `"color.surface.primary"`
- [ ] `figma_path_to_dtcg("space/4")` returns `"space.4"`
- [ ] `parse_figma_variables_response` extracts variable IDs, names, and collection info
- [ ] `writeback_variable_ids` updates `tokens.figma_variable_id` for matching tokens
- [ ] `writeback_variable_ids` updates `tokens.sync_status` to `'synced'`
- [ ] `writeback_variable_ids` updates `token_collections.figma_id` when collection ID available
- [ ] `writeback_variable_ids` updates `token_modes.figma_mode_id` when mode IDs available
- [ ] `writeback_variable_ids` returns count of tokens updated and not-found
- [ ] `get_sync_status_summary` returns correct counts per sync_status
- [ ] After writeback, tokens that were matched have `figma_variable_id IS NOT NULL`
- [ ] Unmatched tokens (not found in Figma response) retain `sync_status = 'pending'`

## Notes

- This module processes responses from MCP calls but does NOT call MCP directly. The agent calls `figma_get_variables` and passes the response to `writeback_variable_ids_from_response`.
- The Figma variable response shape may vary between MCP tool versions. The `parse_figma_variables_response` function should be resilient to minor variations.
- Name matching between Figma and DB uses the slash-to-dot conversion. This assumes the names were generated by `dtcg_to_figma_path` during payload generation (TASK-050).
- Collection and mode Figma IDs are updated for future drift detection (TASK-070) and re-export scenarios.
- The `figma_variable_id` format from Figma is typically `"VariableID:123:456"`.