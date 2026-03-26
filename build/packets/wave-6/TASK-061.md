---
taskId: TASK-061
title: "Implement Tailwind theme config export"
wave: wave-6
testFirst: true
testLevel: unit
dependencies: [TASK-002]
produces:
  - dd/export_tailwind.py
verify:
  - type: typecheck
    command: 'python -c "from dd.export_tailwind import generate_tailwind_config, token_name_to_tailwind_key, map_token_to_tailwind_section, write_tailwind_mappings"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_export_code.py -k tailwind -v'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-061: Implement Tailwind theme config export

## Spec Context

### From User Requirements Spec -- FR-4.4

> FR-4.4: Generate Tailwind theme config from token values.

### From User Requirements Spec -- UC-4: Export to Code

> Agent queries `code_mappings` to translate token names to target format (CSS custom properties, Tailwind classes, Swift constants).

### From schema.sql -- v_resolved_tokens view

> ```sql
> CREATE VIEW v_resolved_tokens AS
> SELECT
>     t.id, t.name, t.type, t.tier, t.collection_id, t.sync_status, t.figma_variable_id,
>     CASE WHEN t.alias_of IS NOT NULL THEN target.name ELSE NULL END AS alias_target_name,
>     tv.mode_id, tm.name AS mode_name,
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
>     alias_of INTEGER REFERENCES tokens(id), description TEXT, figma_variable_id TEXT,
>     sync_status TEXT NOT NULL DEFAULT 'pending', created_at TEXT, updated_at TEXT,
>     UNIQUE(collection_id, name)
> );
> CREATE TABLE IF NOT EXISTS token_values (
>     id INTEGER PRIMARY KEY, token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value TEXT NOT NULL, resolved_value TEXT NOT NULL, extracted_at TEXT,
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

> Exports: `init_db(db_path) -> sqlite3.Connection`

## Task

Create `dd/export_tailwind.py` implementing Tailwind theme configuration export from curated tokens. This module generates a `tailwind.config.js` theme.extend block, maps tokens to Tailwind naming conventions, and writes to the `code_mappings` table.

1. **`TAILWIND_SECTION_MAP: dict[str, str]`**:
   - Map token type prefixes to Tailwind theme sections:
     ```python
     TAILWIND_SECTION_MAP = {
         "color.surface": "colors",
         "color.text": "colors",
         "color.border": "colors",
         "color.accent": "colors",
         "color": "colors",
         "space": "spacing",
         "radius": "borderRadius",
         "shadow": "boxShadow",
         "type": "fontSize",  # simplified; individual properties below
         "opacity": "opacity",
     }
     ```

2. **`map_token_to_tailwind_section(token_name: str, token_type: str) -> str`**:
   - Determine which Tailwind theme section a token belongs to.
   - Match by longest prefix first from TAILWIND_SECTION_MAP.
   - For typography tokens: map by the final segment:
     - `*.fontSize` -> `"fontSize"`
     - `*.fontFamily` -> `"fontFamily"`
     - `*.fontWeight` -> `"fontWeight"`
     - `*.lineHeight` -> `"lineHeight"`
     - `*.letterSpacing` -> `"letterSpacing"`
   - Default fallback: `"extend"` for unknown types.

3. **`token_name_to_tailwind_key(token_name: str, section: str) -> str`**:
   - Convert a DTCG token name to a Tailwind config key.
   - Strip the section prefix to avoid redundancy:
     - For colors: `color.surface.primary` -> key `"surface-primary"` (strip `color.`)
     - For spacing: `space.4` -> key `"4"` (strip `space.`)
     - For radius: `radius.md` -> key `"md"` (strip `radius.`)
     - For shadow: `shadow.sm` -> key `"sm"` (strip `shadow.` -- note: shadow composites assembled below)
     - For typography: `type.body.md.fontSize` -> key `"body-md"` (strip `type.` and `.fontSize`)
   - Replace dots with hyphens in the remaining path.
   - Return the key string.

4. **`format_tailwind_value(resolved_value: str, token_type: str) -> str`**:
   - Format a resolved value for Tailwind config:
   - `color`: return hex string as-is (e.g., `"#09090B"`).
   - `dimension`: append `"px"` if plain number: `"16"` -> `"16px"`, `"0.5"` -> `"0.5px"`.
   - `fontFamily`: wrap in array string: `"Inter"` -> `"['Inter', sans-serif]"`.
   - `fontWeight`: return as-is (numeric string).
   - `number`: return as-is.
   - Default: return as-is.

5. **`generate_tailwind_config(conn, file_id: int) -> str`**:
   - Main entry point.
   - Query curated/aliased tokens from `v_resolved_tokens` for the default mode.
   - Group tokens by Tailwind section via `map_token_to_tailwind_section`.
   - For each section, build a nested JS object:
     ```javascript
     module.exports = {
       theme: {
         extend: {
           colors: {
             'surface-primary': '#09090B',
             'surface-secondary': '#18181B',
             'border-default': '#D4D4D8',
             'text-primary': '#FFFFFF',
           },
           spacing: {
             '4': '16px',
             '2': '8px',
           },
           borderRadius: {
             'sm': '8px',
             'md': '12px',
           },
           fontSize: {
             'body-md': '16px',
             'display-lg': '24px',
           },
           // ... other sections
         },
       },
     };
     ```
   - Use JSON-like formatting with single quotes for JS string literals.
   - Add a header comment: `/** Generated by Declarative Design */\n`.
   - For aliased tokens, use the resolved value (not a CSS var reference, since Tailwind config needs literal values).
   - Return the complete JS config string.

6. **`generate_tailwind_config_dict(conn, file_id: int) -> dict`**:
   - Same logic as `generate_tailwind_config` but returns a Python dict representing the `theme.extend` object.
   - Structure: `{"colors": {"surface-primary": "#09090B", ...}, "spacing": {"4": "16px", ...}, ...}`.
   - This is useful for programmatic consumption and testing.

7. **`write_tailwind_mappings(conn, file_id: int) -> int`**:
   - For each curated/aliased token:
     - Determine Tailwind section and key.
     - Build the Tailwind class identifier: `{section_prefix}-{key}` (e.g., `bg-surface-primary`, `text-surface-primary`, `p-4`, `rounded-md`, `text-body-md`).
     - For color tokens, create multiple mapping entries for common Tailwind utilities: `bg-{key}`, `text-{key}`, `border-{key}`.
     - For spacing: `p-{key}`, `m-{key}`, `gap-{key}`.
     - For radius: `rounded-{key}`.
     - For fontSize: `text-{key}`.
   - UPSERT into `code_mappings` with `target = 'tailwind'`.
   - Return count of mappings written.

8. **`export_tailwind(conn, file_id: int) -> dict`**:
   - Convenience function calling `generate_tailwind_config` and `write_tailwind_mappings`.
   - Return: `{"config": str, "config_dict": dict, "mappings_written": int, "token_count": int}`.

## Acceptance Criteria

- [ ] `python -c "from dd.export_tailwind import generate_tailwind_config, generate_tailwind_config_dict, token_name_to_tailwind_key, map_token_to_tailwind_section, format_tailwind_value, write_tailwind_mappings, export_tailwind"` exits 0
- [ ] `map_token_to_tailwind_section("color.surface.primary", "color")` returns `"colors"`
- [ ] `map_token_to_tailwind_section("space.4", "dimension")` returns `"spacing"`
- [ ] `map_token_to_tailwind_section("radius.md", "dimension")` returns `"borderRadius"`
- [ ] `map_token_to_tailwind_section("type.body.md.fontSize", "dimension")` returns `"fontSize"`
- [ ] `token_name_to_tailwind_key("color.surface.primary", "colors")` returns `"surface-primary"`
- [ ] `token_name_to_tailwind_key("space.4", "spacing")` returns `"4"`
- [ ] `token_name_to_tailwind_key("radius.md", "borderRadius")` returns `"md"`
- [ ] `format_tailwind_value("#09090B", "color")` returns `"#09090B"`
- [ ] `format_tailwind_value("16", "dimension")` returns `"16px"`
- [ ] `generate_tailwind_config` produces a string containing `module.exports` and `theme`
- [ ] `generate_tailwind_config_dict` returns a dict with section keys like `colors`, `spacing`
- [ ] `write_tailwind_mappings` inserts rows into `code_mappings` with target='tailwind'
- [ ] `write_tailwind_mappings` is idempotent (UPSERT)
- [ ] Generated config contains properly nested JS object structure

## Notes

- Tailwind config uses literal values, not CSS variable references. Even aliased tokens get their resolved values in the config.
- The Tailwind section mapping is heuristic. Tokens that don't match a known prefix go into the `extend` section as-is.
- For shadow tokens, individual atomic shadow fields (shadow.sm.color, shadow.sm.radius, etc.) would ideally be composed into a single Tailwind `boxShadow` string like `"0 4px 6px -1px rgba(0,0,0,0.1)"`. For v1, export individual shadow field tokens; composite assembly can be added later or handled at DTCG export time.
- The multiple mapping entries for color tokens (bg-, text-, border-) reflect Tailwind's utility class pattern where the same color can be used as background, text, or border color.
- The generated JS uses `module.exports` for CommonJS compatibility. ESM `export default` can be added later.