---
taskId: TASK-062
title: "Implement W3C DTCG tokens.json export (FR-4.6)"
wave: wave-6
testFirst: true
testLevel: unit
dependencies: [TASK-002]
produces:
  - dd/export_dtcg.py
verify:
  - type: typecheck
    command: 'python -c "from dd.export_dtcg import generate_dtcg_json, generate_dtcg_dict, assemble_composite_typography, assemble_composite_shadow, build_alias_reference"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_export_code.py -k dtcg -v'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-062: Implement W3C DTCG tokens.json export (FR-4.6)

## Spec Context

### From User Requirements Spec -- FR-4.6

> FR-4.6: Generate W3C DTCG v2025.10 `tokens.json` file with full type information, aliases, and multi-mode values.

### From Technical Design Spec -- Key Design Decisions

> **Composite tokens (typography, shadow, border)** are stored as individual atomic tokens in the DB. DTCG composite types are assembled at export time when generating `tokens.json`. This keeps the DB queryable (you can ask "all font sizes" without parsing composite JSON) and avoids a grouping table that adds complexity with no query benefit. The `tokens.json` exporter reconstructs composites by matching token paths: `type.body.md.fontFamily` + `type.body.md.fontSize` + `type.body.md.lineHeight` -> one DTCG `typography` composite.
>
> **DTCG resolver format** (sets + modifiers) is generated at export time from the flat `token_collections` / `token_modes` tables. The DB mirrors Figma's mode model (1 collection = N flat modes) because: (a) Figma is the immediate export target, (b) flat rows are trivially queryable in SQL, (c) the source data being extracted is flat. The `tokens.json` exporter wraps each collection as a set and each non-default mode as a modifier context per W3C v2025.10 spec.

### From User Requirements Spec -- FR-2.4

> FR-2.4: DTCG v2025.10 compatible type system (color, dimension, fontFamily, fontWeight, number, shadow, border, transition, gradient).

### From User Requirements Spec -- FR-2.5

> FR-2.5: Token names follow DTCG dot-path convention (e.g., `color.surface.primary`).

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

## Task

Create `dd/export_dtcg.py` implementing W3C DTCG v2025.10 tokens.json export. This module assembles composite types from atomic tokens at export time, generates the resolver format with sets and modifiers from flat mode tables, and produces alias references using DTCG `{reference}` syntax.

1. **`DTCG_TYPE_MAP: dict[str, str]`**:
   - Map internal token types to DTCG `$type` values:
     ```python
     DTCG_TYPE_MAP = {
         "color": "color",
         "dimension": "dimension",
         "fontFamily": "fontFamily",
         "fontWeight": "fontWeight",
         "number": "number",
         "shadow": "shadow",
         "border": "border",
         "gradient": "gradient",
     }
     ```

2. **`TYPOGRAPHY_FIELDS: list[str]`**:
   - Fields that make up a composite typography token:
     ```python
     TYPOGRAPHY_FIELDS = ["fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing"]
     ```

3. **`SHADOW_FIELDS: list[str]`**:
   - Fields that make up a composite shadow token:
     ```python
     SHADOW_FIELDS = ["color", "radius", "offsetX", "offsetY", "spread"]
     ```

4. **`build_alias_reference(target_name: str) -> str`**:
   - Build a DTCG alias reference string: `{color.surface.primary}`.
   - Return `f"{{{target_name}}}"`.

5. **`format_dtcg_value(resolved_value: str, token_type: str) -> any`**:
   - Format a resolved value for DTCG JSON:
   - `color`: return hex string as-is.
   - `dimension`: return as object `{"value": N, "unit": "px"}` where N is the numeric portion. If value is `"AUTO"`, return `"auto"`.
   - `fontFamily`: return the string value.
   - `fontWeight`: return as integer if possible, else string.
   - `number`: return as float or int.
   - Default: return as string.

6. **`assemble_composite_typography(atomic_tokens: dict[str, dict]) -> dict | None`**:
   - Accept a dict mapping field names to their token data dicts (e.g., `{"fontFamily": {"resolved_value": "Inter", ...}, "fontSize": {"resolved_value": "16", ...}, ...}`).
   - Assemble a DTCG composite typography value:
     ```python
     {
         "$type": "typography",
         "$value": {
             "fontFamily": "Inter",
             "fontSize": {"value": 16, "unit": "px"},
             "fontWeight": 600,
             "lineHeight": {"value": 24, "unit": "px"},
             "letterSpacing": {"value": 0, "unit": "px"},
         }
     }
     ```
   - Return None if no typography fields are present.
   - At minimum, `fontFamily` and `fontSize` must be present to form a valid composite.

7. **`assemble_composite_shadow(atomic_tokens: dict[str, dict]) -> dict | None`**:
   - Accept a dict mapping field names to token data dicts.
   - Assemble a DTCG composite shadow value:
     ```python
     {
         "$type": "shadow",
         "$value": {
             "color": "#0000001A",
             "offsetX": {"value": 0, "unit": "px"},
             "offsetY": {"value": 4, "unit": "px"},
             "blur": {"value": 6, "unit": "px"},
             "spread": {"value": -1, "unit": "px"},
         }
     }
     ```
   - Note: DTCG uses `blur` not `radius` for the shadow blur field. Map `radius` -> `blur`.
   - Return None if insufficient fields.

8. **`query_dtcg_tokens(conn, file_id: int) -> list[dict]`**:
   - Query curated/aliased tokens with resolved values for the default mode:
     ```sql
     SELECT vrt.id, vrt.name, vrt.type, vrt.tier, vrt.alias_target_name,
            vrt.mode_name, vrt.resolved_value, vrt.collection_id
     FROM v_resolved_tokens vrt
     JOIN token_collections tc ON vrt.collection_id = tc.id
     JOIN token_modes tm ON vrt.mode_id = tm.id
     WHERE tc.file_id = ? AND vrt.tier IN ('curated', 'aliased')
     ORDER BY vrt.name
     ```
   - Return list of dicts.

9. **`build_token_tree(tokens: list[dict], default_mode: str) -> dict`**:
   - Convert flat token list into a nested DTCG JSON structure.
   - For each token, split its name by `.` and nest into a dict tree:
     - `color.surface.primary` -> `{"color": {"surface": {"primary": {"$type": "color", "$value": "#09090B"}}}}`
   - For aliased tokens: use `{"$type": "color", "$value": "{color.surface.primary}"}` (alias reference).
   - Detect composite token groups:
     - Look for tokens matching `*.fontFamily`, `*.fontSize`, etc. with a common prefix -> assemble composite typography.
     - Look for tokens matching `*.color`, `*.radius`, `*.offsetX`, etc. with a common shadow prefix -> assemble composite shadow.
   - When composites are assembled, emit BOTH the composite AND the atomic tokens (for backward compatibility).
   - Filter to default mode values for the main token tree.
   - Return the nested dict.

10. **`build_dtcg_with_modes(conn, file_id: int) -> dict`**:
    - Build the full DTCG structure including sets and modifiers for multi-mode support.
    - Structure per W3C v2025.10 resolver format:
      ```json
      {
        "$schema": "https://design-tokens.org/schema.json",
        "color": {
          "surface": {
            "primary": {
              "$type": "color",
              "$value": "#09090B",
              "$extensions": {
                "org.design-tokens.modes": {
                  "dark": "#FAFAFA"
                }
              }
            }
          }
        }
      }
      ```
    - For each collection, the default mode values go in `$value`. Non-default mode values go in `$extensions.org.design-tokens.modes.<mode_name>`.
    - If only one mode (Default), omit the `$extensions` block.
    - Return the complete DTCG dict.

11. **`generate_dtcg_dict(conn, file_id: int) -> dict`**:
    - Main entry point returning the DTCG structure as a Python dict.
    - Calls `build_dtcg_with_modes(conn, file_id)`.

12. **`generate_dtcg_json(conn, file_id: int, indent: int = 2) -> str`**:
    - Calls `generate_dtcg_dict` and serializes to JSON string.
    - Use `json.dumps(dict, indent=indent, ensure_ascii=False)`.
    - Return the JSON string.

13. **`export_dtcg(conn, file_id: int) -> dict`**:
    - Convenience function. Generate DTCG JSON, write code_mappings for each token (target='dtcg', identifier=token DTCG path).
    - Return: `{"json": str, "dict": dict, "mappings_written": int, "token_count": int}`.

## Acceptance Criteria

- [ ] `python -c "from dd.export_dtcg import generate_dtcg_json, generate_dtcg_dict, assemble_composite_typography, assemble_composite_shadow, build_alias_reference, format_dtcg_value, build_token_tree, export_dtcg"` exits 0
- [ ] `build_alias_reference("color.surface.primary")` returns `"{color.surface.primary}"`
- [ ] `format_dtcg_value("#09090B", "color")` returns `"#09090B"`
- [ ] `format_dtcg_value("16", "dimension")` returns `{"value": 16, "unit": "px"}`
- [ ] `format_dtcg_value("600", "fontWeight")` returns `600` (integer)
- [ ] `assemble_composite_typography` with fontFamily + fontSize produces `$type: "typography"` composite
- [ ] `assemble_composite_typography` returns None when fewer than fontFamily + fontSize present
- [ ] `assemble_composite_shadow` maps `radius` field to `blur` in DTCG output
- [ ] `build_token_tree` creates nested dict from flat token names using dot-path splitting
- [ ] Aliased tokens produce `$value` containing `{target.name}` reference syntax
- [ ] `generate_dtcg_json` produces valid JSON (parseable by `json.loads`)
- [ ] Generated JSON contains `$type` and `$value` keys for each token
- [ ] Multi-mode tokens include `$extensions.org.design-tokens.modes` with non-default mode values
- [ ] Single-mode tokens omit the `$extensions` block
- [ ] Composite typography and shadow tokens are assembled from atomic tokens at export time
- [ ] `export_dtcg` writes code_mappings with target='dtcg'

## Notes

- The DTCG spec (v2025.10) is used as the target format. The `$schema` URL may need updating when the spec stabilizes.
- Composite assembly is the core complexity of this module. The exporter must detect groups of atomic tokens that form a composite (e.g., `type.body.md.fontFamily` + `type.body.md.fontSize` -> one typography composite at `type.body.md`). The detection key is a common prefix with different terminal segments matching known composite fields.
- Both composite AND atomic tokens are emitted. The atomic tokens enable granular consumption, while composites enable tools that expect DTCG composite types.
- The `$extensions.org.design-tokens.modes` structure is the proposed W3C approach for multi-mode/theming. If the spec changes, this structure should be updated.
- The `format_dtcg_value` function handles the dimension type by returning an object `{"value": N, "unit": "px"}` per DTCG spec. The `"AUTO"` line-height becomes `"auto"` string.
- Shadow's `radius` field maps to DTCG's `blur` property. This is a naming convention difference between Figma (which uses `radius`) and DTCG (which uses `blur`).