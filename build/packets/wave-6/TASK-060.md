---
taskId: TASK-060
title: "Implement CSS custom property export"
wave: wave-6
testFirst: true
testLevel: unit
dependencies: [TASK-002]
produces:
  - dd/export_css.py
verify:
  - type: typecheck
    command: 'python -c "from dd.export_css import generate_css, generate_css_for_collection, token_name_to_css_var, write_code_mappings"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_export_code.py -k css -v'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-060: Implement CSS custom property export

## Spec Context

### From User Requirements Spec -- FR-4.3

> FR-4.3: Generate CSS custom property declarations from token values, with mode-specific values in media queries or data-attribute selectors.

### From User Requirements Spec -- UC-4: Export to Code

> Agent queries DB for relevant tokens, resolving aliases via `alias_of` chain.
> Agent queries `code_mappings` to translate token names to target format (CSS custom properties, Tailwind classes, Swift constants).
> DTCG-format `tokens.json` export is available alongside CSS/Tailwind for toolchain interop.

### From User Requirements Spec -- FR-5.11.2

> FR-5.11.2: Code mappings (`code_mappings`) link tokens to their representation in each target system (CSS custom properties, Tailwind classes, Swift constants). One row per token per target per identifier.

### From Technical Design Spec -- Key Design Decision

> **Composite tokens (typography, shadow, border)** are stored as individual atomic tokens in the DB. DTCG composite types are assembled at export time when generating `tokens.json`. This keeps the DB queryable.

### From schema.sql -- v_resolved_tokens view

> ```sql
> CREATE VIEW v_resolved_tokens AS
> SELECT
>     t.id,
>     t.name,
>     t.type,
>     t.tier,
>     t.collection_id,
>     t.sync_status,
>     t.figma_variable_id,
>     CASE
>         WHEN t.alias_of IS NOT NULL THEN target.name
>         ELSE NULL
>     END AS alias_target_name,
>     tv.mode_id,
>     tm.name AS mode_name,
>     COALESCE(target_tv.resolved_value, tv.resolved_value) AS resolved_value,
>     COALESCE(target_tv.raw_value, tv.raw_value) AS raw_value
> FROM tokens t
> LEFT JOIN tokens target ON t.alias_of = target.id
> LEFT JOIN token_values tv ON tv.token_id = t.id
> LEFT JOIN token_values target_tv ON target_tv.token_id = target.id AND target_tv.mode_id = tv.mode_id
> LEFT JOIN token_modes tm ON tm.id = tv.mode_id;
> ```

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

### From dd/db.py (produced by TASK-002)

> Exports:
> - `get_connection(db_path: str) -> sqlite3.Connection`
> - `init_db(db_path: str) -> sqlite3.Connection`

## Task

Create `dd/export_css.py` implementing CSS custom property export from curated tokens. This module queries curated tokens from the DB, generates `:root` blocks with CSS custom properties, handles multi-mode values via `[data-theme]` attribute selectors, and writes to the `code_mappings` table.

1. **`token_name_to_css_var(token_name: str) -> str`**:
   - Convert a DTCG dot-path token name to a CSS custom property name.
   - Replace dots with hyphens, prepend `--`: `color.surface.primary` -> `--color-surface-primary`.
   - Return the CSS variable name string.

2. **`format_css_value(resolved_value: str, token_type: str) -> str`**:
   - Format a resolved_value for CSS output based on token type.
   - `color`: return as-is (already hex like `#09090B`). If 8-digit hex, convert to `rgba()` for browser compat: `#RRGGBBAA` -> `rgba(R, G, B, A/255)`.
   - `dimension`: append `px` if the value is a plain number without a unit: `"16"` -> `"16px"`, `"AUTO"` -> `"auto"`.
   - `fontFamily`: wrap in quotes if not already quoted: `Inter` -> `"Inter"`.
   - `fontWeight`: return as-is (numeric value like `"600"`).
   - `number`: return as-is.
   - Everything else: return as-is.

3. **`query_css_tokens(conn, file_id: int) -> list[dict]`**:
   - Query curated/aliased tokens with their resolved values per mode:
     ```sql
     SELECT vrt.id, vrt.name, vrt.type, vrt.tier, vrt.collection_id,
            vrt.alias_target_name, vrt.mode_id, vrt.mode_name, vrt.resolved_value
     FROM v_resolved_tokens vrt
     JOIN token_collections tc ON vrt.collection_id = tc.id
     WHERE tc.file_id = ? AND vrt.tier IN ('curated', 'aliased')
     ORDER BY vrt.name, vrt.mode_name
     ```
   - Return list of dicts with all columns.

4. **`generate_css_for_collection(tokens: list[dict], default_mode_name: str) -> str`**:
   - Accept a list of token dicts (all from the same collection, all modes included).
   - Group tokens by mode_name.
   - Build a `:root` block with default mode values:
     ```css
     :root {
       --color-surface-primary: #09090B;
       --color-surface-secondary: #18181B;
       ...
     }
     ```
   - For each non-default mode, build a `[data-theme="<mode_name>"]` block:
     ```css
     [data-theme="dark"] {
       --color-surface-primary: #FAFAFA;
       --color-surface-secondary: #F4F4F5;
       ...
     }
     ```
   - For aliased tokens, emit `--alias-name: var(--target-name);` using the `alias_target_name` field.
   - Return the complete CSS string.

5. **`generate_css(conn, file_id: int) -> str`**:
   - Main entry point.
   - Call `query_css_tokens(conn, file_id)`.
   - Determine default mode per collection: query `token_modes WHERE is_default = 1`.
   - Group tokens by collection_id.
   - For each collection, call `generate_css_for_collection`.
   - Add a header comment: `/* Generated by Declarative Design */\n/* File: <file_name> */\n\n`.
   - Concatenate all collection outputs with newlines.
   - Return the full CSS string.

6. **`write_code_mappings(conn, file_id: int) -> int`**:
   - For each curated/aliased token in the file:
     - Compute the CSS variable name via `token_name_to_css_var`.
     - UPSERT into `code_mappings`: `INSERT INTO code_mappings (token_id, target, identifier, file_path) VALUES (?, 'css', ?, 'tokens.css') ON CONFLICT(token_id, target, identifier) DO UPDATE SET file_path = excluded.file_path`.
   - Return count of mappings written.
   - Commit after all inserts.

7. **`export_css(conn, file_id: int) -> dict`**:
   - Convenience function that calls `generate_css` and `write_code_mappings`.
   - Return: `{"css": str, "mappings_written": int, "token_count": int}`.

## Acceptance Criteria

- [ ] `python -c "from dd.export_css import generate_css, generate_css_for_collection, token_name_to_css_var, format_css_value, write_code_mappings, export_css, query_css_tokens"` exits 0
- [ ] `token_name_to_css_var("color.surface.primary")` returns `"--color-surface-primary"`
- [ ] `token_name_to_css_var("space.4")` returns `"--space-4"`
- [ ] `token_name_to_css_var("type.body.md.fontSize")` returns `"--type-body-md-fontSize"`
- [ ] `format_css_value("#09090B", "color")` returns `"#09090B"`
- [ ] `format_css_value("16", "dimension")` returns `"16px"`
- [ ] `format_css_value("Inter", "fontFamily")` returns `'"Inter"'`
- [ ] `format_css_value("600", "fontWeight")` returns `"600"`
- [ ] `generate_css` produces a string containing `:root {` and CSS custom properties
- [ ] Multi-mode tokens produce `[data-theme="<mode>"]` blocks for non-default modes
- [ ] Aliased tokens produce `var(--target-name)` references
- [ ] `write_code_mappings` inserts rows into `code_mappings` with target='css'
- [ ] `write_code_mappings` is idempotent (UPSERT)
- [ ] Generated CSS contains a header comment
- [ ] All CSS variable names use only lowercase letters, digits, and hyphens (no dots or uppercase)

## Notes

- The CSS output should be human-readable with proper indentation (2-space indent inside blocks).
- Alias tokens in CSS use `var(--target-name)` which provides native CSS alias behavior -- the alias automatically resolves when the target value changes.
- The `format_css_value` function handles the `AUTO` line-height case by converting to lowercase `auto`.
- 8-digit hex colors (#RRGGBBAA) have limited browser support. Converting to `rgba()` improves compatibility. However, for simplicity in v1, returning the hex as-is is acceptable since modern browsers support it.
- The `code_mappings` table enables agents to query "what CSS variable corresponds to this token?" without regenerating the CSS.