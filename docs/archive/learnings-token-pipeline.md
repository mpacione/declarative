# Learnings Log — Token Pipeline (T1-T4)

> Archived 2026-04-08. These learnings cover the token pipeline work (Tiers 1-4) which is complete.
> Active learnings (extraction, round-trip, renderer) remain in `docs/learnings.md`.

---

## Figma Push

### Delete + Recreate vs Incremental Sync
- **Current approach**: Delete all collections, recreate from DB. Works but loses Figma variable IDs.
- **Target approach**: Incremental sync — update existing variables, create new ones, delete removed ones.
- **Blocker**: We don't write back Figma variable IDs to the DB after creation. Need `writeback_variable_ids()`.
- **Risk with delete/recreate**: If any Figma nodes are bound to variables, deleting the variable breaks the binding. Incremental sync preserves bindings.

### Batching
- `figma_setup_design_tokens` creates a collection + up to 100 tokens in one call.
- `figma_batch_create_variables` adds tokens to an existing collection (also 100 max).
- Typography (164 tokens) requires 2 calls: first 100 via `setup_design_tokens`, remaining 64 via `batch_create_variables` using the collection ID from the first call.
- **Automation need**: The `dd push` CLI command must auto-batch and handle this split transparently.

### Duplicate Collections
- If you call `figma_setup_design_tokens` with a collection name that already exists, it creates a SECOND collection with the same name. No upsert behavior.
- **Mitigation**: Always check for existing collections and delete or reuse them before creating.

### Type Conversion
- DB stores all values as strings. Figma needs actual numbers for FLOAT, strings for STRING.
- Opacity was stored as STRING type in DB but Figma needs FLOAT. The export layer must handle this.
- **Current approach**: Convert at export time. Works but fragile — easy to miss a type.

### Async Plugin API
- `figma_execute` with async code returns `undefined` because the promise isn't awaited at the top level.
- **Workaround**: Use `console.log("PREFIX:" + JSON.stringify(data))` then parse from `figma_get_console_logs`.
- **Better approach**: Use dedicated MCP tools (`figma_setup_design_tokens`, `figma_batch_create_variables`, `figma_batch_update_variables`) which handle async properly and return structured data.
- **Rule**: Never use `figma_execute` for async operations when a dedicated tool exists.

---

## Curation Operations

### split_token() Doesn't Inherit Tier
- When splitting a token, the new token gets `tier='extracted'` instead of inheriting the parent's `tier='curated'`.
- **Workaround**: Manually update tier after split.
- **Fix needed**: `split_token()` should copy the parent token's tier to the new token.

### split_token() Takes binding_ids, Not node_ids
- The SKILL.md documented `node_ids` but the actual API uses `binding_ids`.
- **Reason**: A node can have multiple bindings (fill + stroke), and you might want to split only the fill binding.

### create_alias() Takes collection_id, Not collection Name
- Need to create or find the collection first, then pass the integer ID.
- **Workflow**: Check if "Semantic" collection exists → create if not → pass ID to `create_alias()`.

### Naming Collisions During Split
- `color.brand.blue` already existed when we tried to split the blue fill bindings into that name.
- **Mitigation**: Always check for existing token names before splitting. Use a unique name or append a disambiguator.

### DTCG Pattern Was Too Strict
- Original: `^[a-z][a-z0-9]*(\.[a-z0-9]+)*$` — rejected camelCase like `fontSize`.
- Fixed: `^[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9]+)*$` — allows camelCase in property suffixes.

---

## Extraction (Bulk)

### REST API Extraction is Fast and Reliable
- 338 screens, 86K nodes, 205K bindings in 135 seconds via CLI.
- Batches of 10 screens per API call. Rate limiting handled with exponential backoff.
- Zero failures on the Dank (Experimental) file.

### Color Clustering Crashed on Gradients
- `fill.0.gradient` bindings have `resolved_value='gradient'` which can't be parsed as hex.
- **Fix**: Filter the SQL query to only `fill.%.color` and `stroke.%.color` patterns, and require `resolved_value LIKE '#%'`.

### Fractional Values From Figma Scaling
- Figma produces values like `36.85981369018555px` when frames are scaled.
- These need rounding during curation (T1.1), not extraction — extraction should capture exactly what Figma reports.

---

## Tier 3 Learnings

### OKLCH Inversion Is Too Aggressive for Pastels
- Pure lightness inversion (L → 1-L) sends near-white pastels to near-black.
- **Fix needed**: Dampened inversion with floor/ceiling. E.g. `new_L = 0.15 + (1-L) * 0.7` keeps dark mode values in a usable 0.15–0.85 range.

### create_theme() Works Cleanly Across Collections
- Single call creates mode + copies values + applies transform across multiple collections.
- **Pattern**: Use `create_theme()` for any multi-collection mode operation.

### Two-Mode Figma Collections Work Perfectly
- `figma_setup_design_tokens` accepts multiple modes in one call: `modes: ["Default", "Dark"]`.

### Component Token Pattern: Alias, Don't Duplicate
- Component tokens should alias primitives, not duplicate values.
- `comp.buttonLg.radius` → `radius.v10` (alias, single source of truth)

### Variables Exist But Aren't Bound to Nodes
- Rebinding (T6.2) is the missing link between "tokens exist" and "tokens are used."
- **Priority**: Build rebinding before Tier 5 (Conjure), not after.

### Rebinding Works — But Scale is a Problem
- Full file: 182,877 bindings → 193 scripts of ~950 bindings each.
- Each script is ~8KB, executes in <1 second.

### Variable ID Writeback is Critical Infrastructure
- Rebinding requires `figma_variable_id` on every token.
- `dd push --writeback --figma-state response.json` handles this.

---

## dd push

### Compact Rebind Encoding Reduces Script Count 3x
- Compact format: ~30 chars/binding using property shortcodes → 950 bindings/script → 193 scripts.

### CLI Generates Manifests, Agent Executes MCP
- CLI outputs structured JSON manifests; agent reads and executes MCP calls.

### Incremental Sync Reuses drift.py
- `compare_token_values()` classifies tokens as synced/drifted/pending/figma_only/code_only.
- Push maps directly: pending/code_only → CREATE, drifted → UPDATE, figma_only → DELETE.

### Figma Opacity Variables Use 0-100 Scale, Not 0-1
- `convert_value_for_figma()` multiplies opacity values by 100.

### Compact Handler: Fill Shortcode Collision With Font Shortcodes
- Added `!isNaN(p[1])` digit check to the fill branch.

### PROXY_EXECUTE Patch Enables Direct Script Execution
- Patch is ~30 lines in `websocket-server.js`, saved as `patches/figma-console-mcp-proxy-execute.patch`.
- Won't survive package updates — must be re-applied.

### setBoundVariableForEffect Fails on Deeply Nested Instance Children
- 3+ levels of instance nesting (`node.id` has 2+ semicolons) → mark `intentionally_unbound`.

### PROXY_EXECUTE: Patch Activation Requires Killing the Stale Process
- `lsof -i :9224` to find PID → `kill <PID>` → restart Claude Desktop.

### PROXY_EXECUTE: Sequential Execution Pattern
- One WebSocket connection per script. Set `timeout` to 30000ms. Outer timeout = `timeout + 5000`.

### Rapid Rebinding Can Hang Figma
- Always add 200ms delay between PROXY_EXECUTE calls.

### Persistent Error Logging via pluginData
- Compact handler writes errors to `figma.root.setPluginData('rebind_errors', ...)`.

### Full Rebind Results
- 182,877 bindings, 193 scripts, 0 errors on clean run.

### Binding Color Variables Resets Paint/Effect Opacity
- **SOLVED**: Alpha-baked color primitives encode alpha directly in 8-digit hex (`#RRGGBBAA`).

### Extraction Gaps: Properties Stored But Not Normalized to Bindings
- Fill/stroke paint opacity now baked into color hex. Non-tokenizable properties correctly NOT extracted as bindings.

### Binding itemSpacing on SPACE_BETWEEN Nodes Overrides Auto Gap
- Rebind handler must skip `itemSpacing` when `primaryAxisAlignItems === "SPACE_BETWEEN"`.

### Variable Value Changes Also Reset Paint Opacities
- **SOLVED**: Alpha-baked color primitives. `restore_opacities` phase removed from push manifest.

### Test Schemas Must Use Real Schema
- All test files now use `init_db(":memory:")` from `dd/db.py`.
- **Rule**: Never define custom `CREATE TABLE` statements in test files.

---

## Value Provenance & History Architecture

### The Four Structural Gaps
All edge cases traced to: stored normalization without provenance, sync state too coarse, no value history, unbounded operations tables.

### The Fix
Three columns added to `token_values`: `source`, `sync_status`, `last_verified_at`. New `token_value_history` table. New `db.update_token_value()` helper.

### Migration Heuristic
```sql
UPDATE token_values SET source = 'derived'
WHERE mode_id NOT IN (SELECT id FROM token_modes WHERE is_default = 1);
```

---

## Alpha-Baked Color Architecture

### The Problem
Figma's `setBoundVariableForPaint` and `setBoundVariableForEffect` reset paint opacity to 1.0. Any variable value change triggers the same loss.

### The Solution
Encode alpha directly into the color variable as 8-digit hex (`#RRGGBBAA`).

### Implementation (Steps 1-7 complete)
1. `color.py`: `hex_to_rgba()`, alpha-aware `hex_to_oklch()`
2. `normalize.py`: paint-level opacity as alpha channel
3. `modes.py`: alpha suffix preserved through OKLCH transforms
4. `drift.py`: 8-digit hex treated as distinct from 6-digit
5. `cluster_colors.py`: different alphas never cluster together
6. `export_rebind.py`: no manual opacity preservation needed
7. `push.py`: `restore_opacities` phase removed

### Binding-Token Consistency Detection
Three composable functions in `validate.py`: `detect_binding_mismatches`, `unbind_mismatched`, `check_binding_token_consistency`. Type-aware comparison via `normalize_value_for_comparison`.

### Design Decisions
- Paint opacity vs color.a: `paint.opacity` is authoritative
- Alpha naming: `.aN` suffix (e.g., `prim.gray.950.a5`)
- Clustering: different alphas are distinct values
- Type-aware comparison reuses `drift.py`

---

## Extended Property Extraction (T4.6)

### Three Categories of Properties
1. **Tokenizable**: fills, strokes, effects, cornerRadius, padding, spacing, font properties, opacity, strokeWeight, visible
2. **Stored but not tokenizable**: layout_mode, alignment, sizing modes, rotation, clipsContent, constraints, strokeAlign/Cap/Join, dashPattern, text properties, layoutWrap, min/max dimensions, componentKey
3. **Structural**: parent_id, path, depth, sort_order, component references, instance overrides

### Gradient Stop Decomposition
Individual color bindings per stop (`fill.0.gradient.stop.0.color`). Stop colors ARE tokenizable.

### IMAGE Fill Storage
`fill.N.image` bindings with `resolved_value='image'`. Marked `intentionally_unbound`.

### Generic Clustering Pattern
`_cluster_simple_dimension()` for any single-property dimension clustering.

### Instance Overrides Table + component_key Column
Critical for Conjure screen generation.
