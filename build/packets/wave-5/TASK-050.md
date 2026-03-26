---
taskId: TASK-050
title: "Implement Figma variable payload generator (Phase 7)"
wave: wave-5
testFirst: true
testLevel: unit
dependencies: [TASK-002, TASK-041]
produces:
  - dd/export_figma_vars.py
verify:
  - type: typecheck
    command: 'python -c "from dd.export_figma_vars import generate_variable_payloads, dtcg_to_figma_path, map_token_type_to_figma, ensure_collection_and_mode, query_exportable_tokens"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_export_figma.py -k "payload or batch or name_conversion or type_mapping" -v'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-050: Implement Figma variable payload generator (Phase 7)

## Spec Context

### From Technical Design Spec -- Phase 7: Figma Variable Export

> **Tool:** Console MCP `figma_setup_design_tokens`.
>
> **Payload generation:**
> 1. Run pre-export validation (Phase 6.5). Abort if errors.
> 2. Query all tokens where `tier IN ('curated', 'aliased')` and `figma_variable_id IS NULL`.
> 3. Group by collection.
> 4. Generate payloads of <=100 tokens per call, including all modes.
>
> ```json
> {
>   "collectionName": "Colors",
>   "modes": ["Light", "Dark"],
>   "tokens": [
>     {
>       "name": "color/surface/primary",
>       "type": "COLOR",
>       "values": { "Light": "#09090B", "Dark": "#FAFAFA" }
>     },
>     {
>       "name": "color/surface/secondary",
>       "type": "COLOR",
>       "values": { "Light": "#18181B", "Dark": "#F4F4F5" }
>     }
>   ]
> }
> ```
>
> **DTCG-to-Figma name mapping:** Dots become slashes (`color.surface.primary` -> `color/surface/primary`) because Figma uses `/` for variable group hierarchy.
>
> **Post-creation:** Query `figma_get_variables` to retrieve Figma variable IDs. Write back to `tokens.figma_variable_id`. Update `sync_status` to `synced`.

### From User Requirements Spec -- FR-4.1

> FR-4.1: Generate `figma_setup_design_tokens` payloads (<=100 tokens/call) with all modes included.

### From User Requirements Spec -- FR-4.5

> FR-4.5: Write back Figma variable IDs to DB after creation.

### From User Requirements Spec -- UC-3: Export to Figma

> - Pre-export validation gate passes before any Figma write: `v_export_readiness` shows 0 errors.
> - Export is blocked if validation gate has error-severity issues. Warnings are logged but don't block.

### From User Requirements Spec -- Constraints

> C-3: Console MCP `figma_setup_design_tokens`: 100 tokens per call.

### From Technical Design Spec -- Phase 8: Node Rebinding -- Figma Plugin API coverage

> | Property path | API method | Variable type |
> |---|---|---|
> | `fill.N.color` | `setBoundVariableForPaint` | COLOR |
> | `stroke.N.color` | `setBoundVariableForPaint` | COLOR |
> | `effect.N.color` | `setBoundVariableForEffect` | COLOR |
> | `effect.N.radius` | `setBoundVariableForEffect` | FLOAT |
> | `effect.N.offsetX` | `setBoundVariableForEffect` | FLOAT |
> | `effect.N.offsetY` | `setBoundVariableForEffect` | FLOAT |
> | `effect.N.spread` | `setBoundVariableForEffect` | FLOAT |
> | `cornerRadius`, etc. | `setBoundVariable` | FLOAT |
> | `paddingTop/Right/Bottom/Left` | `setBoundVariable` | FLOAT |
> | `itemSpacing`, `counterAxisSpacing` | `setBoundVariable` | FLOAT |
> | `opacity` | `setBoundVariable` | FLOAT |
> | `fontSize` | `setBoundVariable` | FLOAT |
> | `fontFamily` | `setBoundVariable` | STRING |
> | `fontWeight` | `setBoundVariable` | FLOAT |
> | `fontStyle` | `setBoundVariable` | STRING |
> | `lineHeight` | `setBoundVariable` | FLOAT |
> | `letterSpacing` | `setBoundVariable` | FLOAT |
> | `paragraphSpacing` | `setBoundVariable` | FLOAT |
> | `strokeWeight`, etc. | `setBoundVariable` | FLOAT |

### From schema.sql -- tokens, token_values, token_collections, token_modes tables

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
>
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
>
> CREATE TABLE IF NOT EXISTS token_values (
>     id              INTEGER PRIMARY KEY,
>     token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id         INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(token_id, mode_id)
> );
>
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

### From dd/validate.py (produced by TASK-041)

> Exports:
> - `run_validation(conn, file_id) -> dict`
> - `is_export_ready(conn) -> bool`

### From dd/types.py (produced by TASK-003)

> Exports:
> - `DTCGType` enum: COLOR, DIMENSION, FONT_FAMILY, FONT_WEIGHT, NUMBER, SHADOW, BORDER, TRANSITION, GRADIENT
> - `SyncStatus` enum: PENDING, FIGMA_ONLY, CODE_ONLY, SYNCED, DRIFTED

### From dd/config.py (produced by TASK-001)

> Exports:
> - `MAX_TOKENS_PER_CALL = 100`

## Task

Create `dd/export_figma_vars.py` implementing the Figma variable payload generator from Phase 7 of the TDS. This module generates JSON payloads for `figma_setup_design_tokens` and handles post-creation ID writeback. The actual MCP calls are made by a separate agent -- this module only produces payloads and processes responses.

1. **`DTCG_TO_FIGMA_TYPE: dict[str, str]`**:
   - Map DTCG token types to Figma variable types:
     ```python
     DTCG_TO_FIGMA_TYPE = {
         "color": "COLOR",
         "dimension": "FLOAT",
         "fontFamily": "STRING",
         "fontWeight": "FLOAT",
         "fontStyle": "STRING",
         "number": "FLOAT",
         "shadow": "FLOAT",   # individual shadow fields are FLOAT except color
         "border": "FLOAT",
         "gradient": "COLOR",
     }
     ```
   - Note: shadow.*.color tokens should map to "COLOR", not "FLOAT". Handle this as a special case.

2. **`dtcg_to_figma_path(dtcg_name: str) -> str`**:
   - Convert DTCG dot-path to Figma slash-path: `color.surface.primary` -> `color/surface/primary`.
   - Simply replace all `.` with `/`.
   - Return the converted string.

3. **`map_token_type_to_figma(token_type: str, token_name: str) -> str`**:
   - Determine Figma variable type from DTCG type and token name.
   - If token_type is "color", return "COLOR".
   - If token_name ends with ".color" (e.g., "shadow.sm.color"), return "COLOR" regardless of type.
   - If token_type is "fontFamily" or "fontStyle", return "STRING".
   - Otherwise return "FLOAT".

4. **`query_exportable_tokens(conn, file_id: int) -> list[dict]`**:
   - Query tokens that are ready for Figma export:
     ```sql
     SELECT t.id, t.name, t.type, t.tier, t.collection_id,
            tc.name AS collection_name,
            t.figma_variable_id, t.alias_of
     FROM tokens t
     JOIN token_collections tc ON t.collection_id = tc.id
     WHERE tc.file_id = ?
       AND t.tier IN ('curated', 'aliased')
       AND t.figma_variable_id IS NULL
     ORDER BY tc.name, t.name
     ```
   - For each token, also query its token_values across all modes:
     ```sql
     SELECT tv.resolved_value, tm.name AS mode_name
     FROM token_values tv
     JOIN token_modes tm ON tv.mode_id = tm.id
     WHERE tv.token_id = ?
     ORDER BY tm.is_default DESC, tm.name
     ```
   - Return list of dicts with keys: `id`, `name`, `type`, `tier`, `collection_id`, `collection_name`, `alias_of`, `values` (dict mapping mode_name -> resolved_value).
   - Skip aliased tokens that don't have their own values (they reference the target's values). Aliased tokens should use the alias target's values.

5. **`generate_variable_payloads(conn, file_id: int) -> list[dict]`**:
   - Main entry point for generating payloads.
   - Call `query_exportable_tokens(conn, file_id)`.
   - Group tokens by `collection_name`.
   - For each collection, get the list of mode names from `token_modes`.
   - Batch into payloads of <= `MAX_TOKENS_PER_CALL` (100) tokens each.
   - Each payload is a dict:
     ```python
     {
         "collectionName": str,  # collection name
         "modes": list[str],     # mode names
         "tokens": [
             {
                 "name": str,    # Figma slash-path
                 "type": str,    # Figma variable type (COLOR, FLOAT, STRING)
                 "values": dict  # mode_name -> resolved_value
             },
             ...
         ]
     }
     ```
   - For aliased tokens: include them in the payload but set their values to be the alias target's resolved values (from `v_resolved_tokens` or by querying the target token's values directly).
   - Convert token names: `dtcg_to_figma_path(token.name)`.
   - Convert token types: `map_token_type_to_figma(token.type, token.name)`.
   - Return list of payload dicts.

6. **`generate_variable_payloads_checked(conn, file_id: int) -> list[dict]`**:
   - Wrapper that checks `is_export_ready(conn)` first.
   - If not ready, raise `RuntimeError("Export blocked: validation errors exist. Run validation first.")`.
   - Otherwise call and return `generate_variable_payloads(conn, file_id)`.

7. **`get_mode_names_for_collection(conn, collection_id: int) -> list[str]`**:
   - Query `token_modes WHERE collection_id = ?` ordered by `is_default DESC, name ASC`.
   - Return list of mode name strings. Default mode comes first.

## Acceptance Criteria

- [ ] `python -c "from dd.export_figma_vars import generate_variable_payloads, dtcg_to_figma_path, map_token_type_to_figma, query_exportable_tokens, generate_variable_payloads_checked, get_mode_names_for_collection"` exits 0
- [ ] `dtcg_to_figma_path("color.surface.primary")` returns `"color/surface/primary"`
- [ ] `dtcg_to_figma_path("space.4")` returns `"space/4"`
- [ ] `map_token_type_to_figma("color", "color.surface.primary")` returns `"COLOR"`
- [ ] `map_token_type_to_figma("dimension", "space.4")` returns `"FLOAT"`
- [ ] `map_token_type_to_figma("fontFamily", "type.body.md.fontFamily")` returns `"STRING"`
- [ ] `map_token_type_to_figma("dimension", "shadow.sm.color")` returns `"COLOR"` (name-based override)
- [ ] `generate_variable_payloads` returns list of dicts with collectionName, modes, tokens keys
- [ ] Each payload's tokens list has at most 100 entries
- [ ] Token names in payloads use slash-path format (no dots)
- [ ] Token types in payloads are Figma types (COLOR, FLOAT, STRING)
- [ ] Each token's values dict has keys matching the modes list
- [ ] `generate_variable_payloads_checked` raises RuntimeError when validation has errors
- [ ] `query_exportable_tokens` only returns curated/aliased tokens with no figma_variable_id
- [ ] Aliased tokens resolve to their target's values in the payload

## Notes

- This module generates payloads but does NOT call MCP. A separate agent session with Console MCP access will call `figma_setup_design_tokens` with these payloads.
- The ID writeback function (TASK-051) handles the post-creation step of storing Figma variable IDs.
- Aliased tokens in Figma: Figma's variable system supports aliases natively. However, for simplicity in v1, we export alias tokens with their resolved values (the target's values), not as Figma aliases. True Figma alias support can be added later.
- The `shadow.sm.color` token has DTCG type "color" already from clustering, but if for some reason it has type "dimension", the name-based override catches it. The `map_token_type_to_figma` function handles both cases.
- The payloads must be valid JSON. All values should be strings (hex for colors, numeric strings for dimensions).