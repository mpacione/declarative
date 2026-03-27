# Learnings Log

Accumulated insights from building and testing the curation pipeline. These inform the design of `dd push` and the agent protocol.

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
- **Decision needed**: Store both native type and string in DB? Or just convert at export time?
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
- **SKILL.md updated**: Yes, corrected.

### create_alias() Takes collection_id, Not collection Name
- Need to create or find the collection first, then pass the integer ID.
- **Workflow**: Check if "Semantic" collection exists → create if not → pass ID to `create_alias()`.

### Naming Collisions During Split
- `color.brand.blue` already existed when we tried to split the blue fill bindings into that name.
- **Mitigation**: Always check for existing token names before splitting. Use a unique name or append a disambiguator.

### DTCG Pattern Was Too Strict
- Original: `^[a-z][a-z0-9]*(\.[a-z0-9]+)*$` — rejected camelCase like `fontSize`.
- Fixed: `^[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9]+)*$` — allows camelCase in property suffixes.
- Both `validate.py` and `curate.py` had the old pattern and needed updating.

---

## Extraction

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

## Architecture

### CLI for Deterministic, Agent for Judgment
- Extraction, clustering, validation, export = CLI commands. No judgment needed.
- Renaming, merging, splitting, aliasing, dark mode = Agent operations. Require context and design knowledge.
- **The curation report bridges them**: `dd curate-report --json` gives the agent a structured list of issues to act on.

### The Push Problem
- Every DB change needs to be synced to Figma. Currently this is manual (7+ MCP calls per sync).
- **Target**: `dd push` command that reads DB state, diffs against Figma state, and applies incremental changes.
- **Dependency**: Need to store Figma variable IDs in DB for incremental sync.
- **Discovery**: Working through tiers first to learn all payload types before building the CLI command.

### Curation → Push → Verify Should Be Atomic
- Currently 3 manual steps: modify DB → push to Figma → read back and verify.
- **Target**: `dd push --verify` that does all three.
- Still discovering what "verify" means for each token type (color spot-check vs typography full comparison).

### Color State Derivation Should Use OKLCH, Not HLS
- HLS lighten/darken produces inconsistent visual shifts on saturated colors.
- `#634AFF` darkened 15% via HLS → `#2200FC` (jumps to pure blue, loses purple character).
- OKLCH manipulates perceptual lightness, preserving hue and chroma.
- **Action**: When building T3.1 (dark mode) or any color derivation, use OKLCH (already in the codebase for ΔE clustering).

### Generated Tokens Need a Separate Collection
- Component state tokens (hover, pressed, disabled) live in "Component States" collection, separate from the base "Colors" collection.
- This is the right pattern: primitives in one collection, component-level tokens in another.
- Validates the T4.1 architecture: Primitives → Semantic → Component layers.

---

## Tier 3 Learnings

### OKLCH Inversion Is Too Aggressive for Pastels
- Pure lightness inversion (L → 1-L) sends near-white pastels to near-black.
- `#FFF7B2` (light yellow) → `#000000` (black). Lost all color.
- `#DADADA` (light gray) → `#050505` (near-black). Too extreme for a "muted" surface.
- **Fix needed**: Dampened inversion with floor/ceiling. E.g. `new_L = 0.15 + (1-L) * 0.7` keeps dark mode values in a usable 0.15–0.85 range.
- For production, dark mode values need human review. The auto-derivation is a starting point, not a final answer.

### create_theme() Works Cleanly Across Collections
- Single call creates mode + copies values + applies transform across multiple collections.
- Correctly skips non-color tokens when applying dark transform.
- **Pattern**: Use `create_theme()` for any multi-collection mode operation.

### Two-Mode Figma Collections Work Perfectly
- `figma_setup_design_tokens` accepts multiple modes in one call: `modes: ["Default", "Dark"]`.
- Each token gets values for both modes in the same payload.
- Figma shows the mode switcher in the variable panel immediately.

### Component Token Pattern: Alias, Don't Duplicate
- Component tokens should alias primitives, not duplicate values.
- `comp.buttonLg.radius` → `radius.v10` (alias, single source of truth)
- NOT `comp.buttonLg.radius` = `10` (duplicate value, will drift)
- This means changing the primitive propagates to all component tokens automatically.

### Variables Exist But Aren't Bound to Nodes
- **Critical gap**: We've pushed 308 variables to Figma, but NONE are bound to actual design nodes.
- The variables exist in the panel but the nodes still use hardcoded values.
- **Rebinding** (T6.2 in the taxonomy) is the missing link between "tokens exist" and "tokens are used."
- This is why you can't see changes in the file — the variables are just sitting there unconnected.
- **Priority**: Build rebinding before Tier 5 (Conjure), not after.

### Rebinding Works — But Scale is a Problem
- Single-binding test: 1/1, 0 failures. Multi-binding test: 26/26, 0 failures.
- Property types verified: fill.color, stroke.color, cornerRadius, padding.*, itemSpacing, fontSize, fontFamily, fontWeight.
- Full file: 182,877 bindings → 366 scripts of ~500 bindings each.
- Each script is ~8KB, executes in <1 second via `figma_execute`.
- **Problem**: 366 sequential MCP calls × ~1s each = ~6 minutes minimum. Need batching or parallelization.
- **Approach**: `dd push --rebind` should generate all scripts, execute them in sequence via MCP, report progress.

### Variable ID Writeback is Critical Infrastructure
- Rebinding requires `figma_variable_id` on every token.
- We had 0/308 IDs after pushing — had to fetch them all back via `figma_execute` and map by name.
- **Fixed**: `dd push --writeback --figma-state response.json` handles this as a CLI step.
- The name→ID mapping uses slash-to-dot conversion (`color/surface/white` → `color.surface.white`).

---

## dd push

### Compact Rebind Encoding Reduces Script Count 3x
- Original verbose format: ~110 chars/binding → 500 bindings/script → 366 scripts for 182K bindings.
- Compact format: ~30 chars/binding using property shortcodes (`fontSize`→`fs`, `fill.0.color`→`f0`) and stripped `VariableID:` prefix → 950 bindings/script → 193 scripts.
- `figma_execute` has a hard 50K character limit. Compact encoding is essential for practical batch sizes.

### CLI Generates Manifests, Agent Executes MCP
- The CLI cannot make MCP calls. It outputs structured JSON manifests.
- Agent reads manifest, executes each MCP call, reports progress.
- This separation keeps deterministic logic in the CLI and Figma interaction in the agent.

### Incremental Sync Reuses drift.py
- `compare_token_values()` from `drift.py` already classifies tokens as synced/drifted/pending/figma_only/code_only.
- Push maps these directly: pending/code_only → CREATE, drifted → UPDATE, figma_only → DELETE, synced → no action.
- No duplicate diff logic needed — reuse what exists.

### query_exportable_tokens() Extended Not Replaced
- Added `include_existing=True` parameter instead of writing a new query function.
- Default behavior unchanged (`include_existing=False` filters to `figma_variable_id IS NULL`).
- Avoids parallel query functions that could drift.

### Figma Opacity Variables Use 0-100 Scale, Not 0-1
- Figma's node `opacity` property is 0-1 (e.g. `0.20` = 20%).
- Figma FLOAT variables bound to `opacity` are interpreted as **percentages**: value `20` → node opacity `0.20`.
- Our DB stores the raw Figma node value (0-1 range, e.g. `0.20`).
- When we created variables with `0.20`, Figma interpreted it as 0.2% → node opacity `0.002`.
- **Fix**: Multiply opacity values by 100 when creating/updating Figma variables. `convert_value_for_figma()` handles this based on token name containing "opacity".
- This affected ~1,247 bindings across 4 opacity tokens — elements appeared invisible.

### Compact Handler: Fill Shortcode Collision With Font Shortcodes
- The fill branch `p[0]==='f'&&p.length<=2` matched both `f0` (fill.0.color) and `fs` (fontSize), `ff` (fontFamily), `fw` (fontWeight).
- `fs`/`ff`/`fw` hit `setBoundVariableForPaint` and failed with "paintCopy validation" error.
- **Fix**: Added `!isNaN(p[1])` digit check to the fill branch, matching the pattern already used by the stroke branch.

### PROXY_EXECUTE Patch Enables Direct Script Execution
- Patching the figma-console-mcp WebSocket server with a `PROXY_EXECUTE` handler lets external scripts execute code in the Figma plugin without going through Claude's tool interface.
- Eliminates the 50K char tool parameter bottleneck — can send full 31KB scripts directly.
- 193 scripts × 950 bindings executed in 108 seconds with 200ms inter-script delay.
- Patch is ~30 lines in `websocket-server.js`, saved as `patches/figma-console-mcp-proxy-execute.patch`.
- Won't survive package updates — must be re-applied.

### Rapid Rebinding Can Hang Figma
- First full run (76s, no delay): Figma hung and required force-quit. All 182K node updates arrived faster than the renderer could process.
- Second run (108s, 200ms delay between scripts): No hang, Figma stayed responsive.
- **Rule**: Always add `asyncio.sleep(0.2)` between PROXY_EXECUTE calls. The cost is ~38s extra on 193 scripts — worth it vs a crash.

### Persistent Error Logging via pluginData
- Figma console logs (`console.error`) are lost on crash/restart — useless for diagnosing rebind failures.
- **Fix**: Compact handler writes errors to `figma.root.setPluginData('rebind_errors', JSON.stringify(errors))`.
- Each script reads existing errors, appends its own, writes back — errors accumulate across all scripts.
- Error format: `{n: nodeId, p: propertyCode, r: reason}` where reason is `NODE_NOT_FOUND`, `VAR_NOT_FOUND`, `UNKNOWN_PROP`, or the exception message.
- Companion scripts: `generate_error_read_script()` and `generate_error_clear_script()` for reading/clearing.
- Persists in the Figma document itself — survives crashes, restarts, and session changes.

### Full Rebind Results
- 182,877 bindings, 193 scripts, 0 errors on clean run (after shortcode fix).
- Previous run had 234 errors from font shortcode collision (fs/ff/fw hitting fill paint branch).
- Visual artifacts from first run (solid black brush selector cards, misplaced opacity) resolved by the shortcode fix.
- Residual artifacts from opacity/alpha loss required separate restoration scripts (see below).

### Binding Color Variables Resets Paint/Effect Opacity
- `setBoundVariableForPaint(paint, 'color', variable)` returns a new paint with `opacity: 1.0`, losing the original paint's opacity.
- `setBoundVariableForEffect(effect, 'color', variable)` resets `effect.color.a` to `1.0`, losing the original alpha.
- **Scope**: 5,128 fill opacities, 297 stroke opacities, 9,807 effect color alphas — all reset to 1.0 during rebind.
- **Restoration**: Separate scripts read original values from `nodes.fills`/`nodes.strokes`/`nodes.effects` JSON columns and re-apply.
- **Prevention needed**: The compact rebind handler must preserve paint opacity and effect color alpha. Two approaches:
  1. Include opacity/alpha in the binding data (e.g., `nodeId|f0:0.12|varId`) so the handler restores it after binding.
  2. Have the handler read the current opacity before binding and restore it after.
- Option 2 is safer for re-runs but won't work for first-time binds. Option 1 requires extraction pipeline changes.
- **Note**: Fill-level opacity is a separate concept from node-level opacity. Both exist in the extraction data (`nodes.fills` JSON has `paint.opacity`, `nodes.opacity` has node-level). Only node-level opacity was extracted as a binding.

### Extraction Gaps: Properties Stored But Not Normalized to Bindings
- **Fill/stroke paint opacity**: Stored in `nodes.fills`/`nodes.strokes` JSON but `normalize_fill()`/`normalize_stroke()` only extract color.
- **Effect color alpha**: Stored in `nodes.effects` JSON `color.a` field but `normalize_effect()` only extracts color as hex (discards alpha).
- **Non-tokenizable properties** (auto-layout sizing mode, text alignment, blend mode, visibility) are stored in node columns but correctly NOT extracted as bindings — they're structural, not design tokens.
- **Action**: Add `fill.N.opacity`, `stroke.N.opacity` as binding properties when < 1.0. For effect alpha, include in the color extraction or as separate `effect.N.alpha` binding.

### Binding itemSpacing on SPACE_BETWEEN Nodes Overrides Auto Gap
- Figma's "Auto" gap is `primaryAxisAlignItems: "SPACE_BETWEEN"`. The `itemSpacing` property reports the computed value but the gap is auto-distributed.
- Binding a variable to `itemSpacing` forces a fixed gap, losing the auto behavior. The layout snaps from space-between distribution to fixed spacing.
- **Scope**: 1,408 nodes had SPACE_BETWEEN alignment but got `itemSpacing` bound to a token.
- **Fix**: The rebind handler must skip `itemSpacing` binding when `primaryAxisAlignItems === "SPACE_BETWEEN"`.
- **Restoration**: Unbind `itemSpacing` (`setBoundVariable('itemSpacing', null)`) and reset `primaryAxisAlignItems = 'SPACE_BETWEEN'`.
- **Broader rule**: Before binding any layout property, check if the node uses an auto/distributed mode that the binding would override.
