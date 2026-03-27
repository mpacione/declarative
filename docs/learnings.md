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

### setBoundVariableForEffect Fails on Deeply Nested Instance Children
- `figma.variables.setBoundVariableForEffect(effect, 'color', variable)` throws when the target node's effect is inherited from a component at 3+ levels of instance nesting (e.g. `I123:456;789:012;107:925`).
- The effect is owned by the innermost component definition; Figma doesn't allow overriding it as an instance property at that depth.
- **Symptom**: Compact handler logs `{n, p: 'e0c'}` failure — no changes applied to `nd.effects`.
- **Fix**: Mark these bindings `intentionally_unbound` in the DB. The shadow still renders from the component definition; it just can't be tokenized at this nesting depth.
- **Detection**: Count semicolons in `node.id` — 2+ semicolons means 3+ levels deep. All 6 failures were `_KeyContainer` nodes inside a keyboard component.
- **Rule**: Before rebinding `effect.N.color`, check instance depth. If `node.id` contains 2+ semicolons and the effect is not an override, skip it and log as `intentionally_unbound`.

### PROXY_EXECUTE: Patch Activation Requires Killing the Stale Process
- The figma-console-mcp node server is a long-running process. Restarting Claude Desktop spawns a new process only if the old one is dead.
- If the server (port 9224) was started before the patch was applied, the patched file is on disk but the running process in memory uses the old code. PROXY_EXECUTE messages silently time out.
- **Fix**: `lsof -i :9224` to find PID → `kill <PID>` → restart Claude Desktop. Verify PID changed.
- **Symptom**: PROXY_EXECUTE sends but `PROXY_EXECUTE_RESULT` never arrives (8s timeout). If `SERVER_HELLO` arrives, the socket is live — it's definitely the stale process, not a network issue.

### PROXY_EXECUTE: Sequential Execution Pattern
- Best executed as a Node.js script that opens a new WebSocket per script, waits for `PROXY_EXECUTE_RESULT`, then closes and opens the next.
- One connection per script (not a persistent connection) avoids interleaved responses and makes error attribution unambiguous.
- Pattern:
  ```js
  for (const script of scripts) {
    const ws = new WebSocket('ws://127.0.0.1:9224');
    ws.on('message', msg => {
      if (JSON.parse(msg).type === 'SERVER_HELLO')
        ws.send(JSON.stringify({ type:'PROXY_EXECUTE', id:script, code, timeout:30000 }));
      if (JSON.parse(msg).type === 'PROXY_EXECUTE_RESULT')
        resolve(msg); ws.close();
    });
  }
  ```
- Set `timeout` to 30000ms for large scripts; the outer Node.js timeout should be `timeout + 5000`.

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
- **SOLVED**: Alpha-baked color primitives. Instead of storing opacity as a separate paint property, the alpha is encoded directly into the color variable value as 8-digit hex (`#RRGGBBAA`). When Figma evaluates the variable, it reads the alpha from the color itself. No separate opacity restoration needed.
- **Note**: Fill-level opacity is a separate concept from node-level opacity. Both exist in the extraction data (`nodes.fills` JSON has `paint.opacity`, `nodes.opacity` has node-level). Only node-level opacity was extracted as a binding. Alpha-baked colors handle the fill/stroke/effect paint-level opacity; node-level opacity remains a separate binding.

### Extraction Gaps: Properties Stored But Not Normalized to Bindings
- **Fill/stroke paint opacity**: Now baked into the color hex as 8-digit `#RRGGBBAA`. `normalize_fill()` and `normalize_stroke()` use paint-level opacity (not `color.a`) as the alpha channel in `rgba_to_hex()`.
- **Effect color alpha**: Now baked into the effect color hex as 8-digit `#RRGGBBAA` via `normalize_effect()`.
- **Non-tokenizable properties** (auto-layout sizing mode, text alignment, blend mode, visibility) are stored in node columns but correctly NOT extracted as bindings — they're structural, not design tokens.
- **No longer needed**: Separate `fill.N.opacity`, `stroke.N.opacity`, `effect.N.alpha` bindings are unnecessary since alpha is part of the color value itself.

### Binding itemSpacing on SPACE_BETWEEN Nodes Overrides Auto Gap
- Figma's "Auto" gap is `primaryAxisAlignItems: "SPACE_BETWEEN"`. The `itemSpacing` property reports the computed value but the gap is auto-distributed.
- Binding a variable to `itemSpacing` forces a fixed gap, losing the auto behavior. The layout snaps from space-between distribution to fixed spacing.
- **Scope**: 1,408 nodes had SPACE_BETWEEN alignment but got `itemSpacing` bound to a token.
- **Fix**: The rebind handler must skip `itemSpacing` binding when `primaryAxisAlignItems === "SPACE_BETWEEN"`.
- **Restoration**: Unbind `itemSpacing` (`setBoundVariable('itemSpacing', null)`) and reset `primaryAxisAlignItems = 'SPACE_BETWEEN'`.
- **Broader rule**: Before binding any layout property, check if the node uses an auto/distributed mode that the binding would override.

### Variable Value Changes Also Reset Paint Opacities
- Changing a variable's value (e.g., from raw hex to variable alias via `setValueForMode`) causes Figma to re-evaluate all bound nodes.
- This re-evaluation resets paint opacities on those nodes to 1.0 — the same bug as `setBoundVariableForPaint`.
- **Scope**: T4.1 alias update (52 variables × `setValueForMode`) reset 4,831 fill opacities and 9,807 effect alphas that we had previously restored.
- **Implication**: The compact handler opacity fix only protects during rebinding. ANY Figma variable modification (value change, alias update, mode creation) can trigger this.
- **SOLVED**: Alpha-baked color primitives (see below). Paint opacity is encoded directly in the color variable as 8-digit hex (`#RRGGBBAA`), so Figma cannot lose it during re-evaluation. The `restore_opacities` phase has been removed from the push manifest.

### Test Schemas Must Use Real Schema
- Three test files defined custom minimal schemas (missing columns, triggers, constraints). These diverged from `schema.sql` over time, causing false passes.
- **Fix**: All test files now use `init_db(":memory:")` from `dd/db.py` which loads the full `schema.sql`.
- **Rule**: Never define custom `CREATE TABLE` statements in test files. Always use the conftest `temp_db`/`db` fixtures. If a test needs specific data, insert it into the real schema's tables.

---

## Value Provenance & History Architecture

### The Four Structural Gaps

All edge cases in the pipeline (force_renormalize, binding mismatches, false positives, opacity loss) trace to four structural gaps in `token_values`:

**Gap 1 — Stored normalization without provenance**
`resolved_value` is computed at write time and stored as a dumb string. When normalization rules change, every stored value silently becomes wrong with no way to detect staleness or know whether a value is re-extractable (figma), recomputable (derived), or must be preserved (manual). Every workaround in the alpha-baked colors work was a symptom of this missing `source` column.

**Gap 2 — Sync state too coarse and misplaced**
`tokens.sync_status` is one field shared across all mode values. Per-mode sync state and push confirmation timestamps (`last_verified_at`) are invisible.

**Gap 3 — No value history**
Every write overwrites in place. No audit trail, no rollback. Fatal for frontend code sync and T5 Conjure where the vocabulary must be stable and trustworthy.

**Gap 4 — Unbounded operations tables**
`screen_extraction_status` grows at N_runs × N_screens. No retention policy.

### The Fix: token_values Provenance + History

Three columns added to `token_values`:
- `source TEXT` — `'figma' | 'derived' | 'manual' | 'imported'`
- `sync_status TEXT` — per-value (not per-token)
- `last_verified_at TEXT` — when last confirmed against Figma

New `token_value_history` table — append-only record of every change, with `changed_by` and `reason`.

New `db.update_token_value()` helper — single call site pattern for all value mutations, ensures history is always written.

`force_renormalize` becomes scoped: only applies to `source='figma'` values. Derived values are recomputed by re-running `modes.py`, not renormalized from stale raw_value.

### Design Decision: Fix Root, Not Symptoms

The architectural lesson: `force_renormalize`, `detect_binding_mismatches`, `unbind_mismatched` are all correct at what they do, but they patch consequences. The root cause is that normalization has no version/source metadata. With `source` on `token_values`, these tools become narrower and more correct (only operate on `source='figma'` values that haven't been re-extracted yet).

### Migration Heuristic

Modes-derived values are always in non-default modes. One-time migration:
```sql
UPDATE token_values SET source = 'derived'
WHERE mode_id NOT IN (SELECT id FROM token_modes WHERE is_default = 1);
```

## Alpha-Baked Color Architecture

### The Problem: Figma Loses Paint Opacity on Variable Re-evaluation

Figma's `setBoundVariableForPaint` and `setBoundVariableForEffect` reset paint opacity and effect `color.a` to 1.0. Worse, any variable value change (alias update, mode creation) re-evaluates all bound nodes, triggering the same opacity loss. This meant 5,128 fill opacities, 297 stroke opacities, and 9,807 effect alphas were wiped every time variables were modified.

The previous workaround was a mandatory `restore_opacities` post-step after every push, reading original opacities from DB JSON columns and generating restoration scripts. This was fragile and slow.

### The Solution: Bake Alpha Into the Color Value

Instead of treating paint opacity as a separate property, encode it directly into the color variable as 8-digit hex (`#RRGGBBAA`). Figma reads the alpha channel from the color value itself, so there is nothing to lose during re-evaluation.

### Implementation (Steps 1-6 complete, 656 tests passing)

1. **`color.py`**: Added `hex_to_rgba()` helper. Updated `hex_to_oklch()` to strip alpha suffix before OKLCH conversion (OKLCH operates on RGB only).
2. **`normalize.py`**: `normalize_fill()` and `normalize_stroke()` now use paint-level opacity (not `color.a`) as the alpha channel in `rgba_to_hex()`, producing `#RRGGBBAA` when opacity < 1.
3. **`modes.py`**: `apply_oklch_inversion()` and `apply_high_contrast()` preserve alpha suffix through transforms. The alpha is stripped before OKLCH manipulation and re-appended after.
4. **`drift.py`**: Removed FF-alpha stripping. 8-digit hex (e.g., `#09090B0D`) is now a distinct value from 6-digit hex (`#09090B`). This is correct because they represent different visual appearances.
5. **`cluster_colors.py`**: Colors at different alphas no longer cluster together. `#09090B` at 100% opacity and `#09090B` at 5% opacity are perceptually different and must be separate primitives.
6. **`export_rebind.py`**: Removed manual opacity preservation from the compact handler. The alpha is in the variable value, so the handler does not need to save/restore it.
7. **`push.py`**: Removed the `restore_opacities` phase from the push manifest. No longer needed.

### Step 7 — force_renormalize

The existing `insert_bindings()` protects bound bindings from overwrite (Step 1: UPSERT only touches `unbound`; Step 2: marks `bound` as `overridden` if value changed). Neither behavior is correct for normalization changes — we need to update the value while preserving `binding_status = 'bound'`.

**Solution**: Added `force_renormalize=True` parameter to `insert_bindings()` and threaded through `create_bindings_for_screen()`. When set, Step 2 updates `raw_value`/`resolved_value` without changing `binding_status`. This is a permanent pipeline capability, not a one-off: any future normalization change (not just alpha-baking) can use the same flag.

### Binding-Token Consistency Detection

After renormalization, bound bindings have updated values (e.g., `#0000000D`) but still point to tokens with old values (`#000000`). The system had no way to detect or resolve this internal mismatch.

**Problem scope**: This isn't alpha-specific. The same mismatch occurs when:
1. Normalization rules change (alpha-baking, format changes)
2. A designer manually edits nodes in Figma and you re-extract
3. An agent edits a token's value during curation

**Solution**: Three composable functions in `validate.py`:
- `detect_binding_mismatches(conn, file_id, token_id=None, screen_id=None)` — finds all bound bindings where `resolved_value` doesn't match token value. Uses type-aware normalization (reuses `drift.py`'s `normalize_value_for_comparison`) to avoid false positives from format differences (`10` vs `10.0`). Resolves alias chains.
- `unbind_mismatched(conn, file_id, token_id=None, screen_id=None)` — sets mismatched bindings to `unbound` + clears `token_id`, so they re-enter the clustering pipeline.
- `check_binding_token_consistency(conn, file_id)` — validation check #8, returns warning-severity issues grouped by token.

All three accept optional `token_id`/`screen_id` filters for atomic operations. The functions compose: validate calls detect for reporting, cluster can call unbind before clustering, agent can call detect for a single token.

A `v_binding_mismatches` view in `schema.sql` provides the same detection as an always-available SQL query for dashboards and `dd status`.

**Key insight**: the normalization comparison must be type-aware. Raw SQL `!=` produces 87K false positives (dimension `10` vs `10.0`, lineHeight JSON vs number). Using `normalize_value_for_comparison` from `drift.py` reduces to ~20K genuine mismatches. Remaining categories beyond alpha: lineHeight JSON format, actual value drift, and floating point noise — pre-existing issues to address separately.

### Pending Steps (continued)

- Run `create_bindings_for_screen(force_renormalize=True)` across all screens to propagate alpha-inclusive values to bound bindings.
- Run `unbind_mismatched()` to release alpha-mismatched bindings for re-clustering.
- Run `dd cluster` to create new alpha-baked primitives. Colors at different alphas cluster separately.
- Curate, derive mode values, push, and rebind through existing pipeline.
- Push new alpha-baked primitives to Figma as variables, rebind affected nodes, test mode switching.

### Design Decisions

- **Paint opacity vs color.a**: Figma paints have both `paint.opacity` and `paint.color.a`. The extraction uses `paint.opacity` as the authoritative alpha source, not `color.a`. This matches Figma's visual rendering behavior.
- **Alpha naming convention**: Alpha-baked primitives use `.aN` suffix where N is the opacity percentage (e.g., `prim.gray.950.a5` for 5% opacity).
- **Clustering**: Colors at different alphas are treated as distinct values. `#09090B` and `#09090B0D` will never cluster together, even though the RGB components are identical.
- **Pipeline composability**: Mismatch detection, unbinding, and clustering are separate atomic functions that compose rather than a monolithic "reconcile" step. Each can operate on 1 or N items via optional filters. This supports just-in-time incremental processing.
- **Type-aware comparison**: Reuses `drift.py`'s `normalize_value_for_comparison` to avoid false positives. The SQL view (`v_binding_mismatches`) does raw comparison for dashboards; the Python function does normalized comparison for pipeline decisions.
- **Alpha rebinds get overwritten by subsequent variable updates**: Any Figma variable operation (alias updates, mode creation, value changes) re-evaluates all bound nodes and can reset paint opacity to 1.0. Alpha-baked colors survive this because the alpha is in the variable value, BUT if the alpha rebind was applied before a later non-alpha rebind or variable update that touched the same node, the alpha binding can be lost (replaced by the non-alpha semantic variable). The full alpha rebind pass must run LAST, after all other variable operations, and must cover ALL THREE property classes:
  - `fill.N.color` → `setBoundVariableForPaint` on `node.fills` (4,831 bindings, 4,723 ok, 108 gradient fails)
  - `effect.N.color` → `setBoundVariableForEffect` on `node.effects` (1,144 bindings, 1,144 ok)
  - `stroke.N.color` → `setBoundVariableForPaint` on `node.strokes` (297 bindings, 267 ok)
  Missing any property class leaves those bindings with alpha=1.0. The original targeted fill-only pass missed effects and strokes entirely.
- **normalize_value_for_comparison improvements**: JSON dimension objects (`{"value":24,"unit":"PIXELS"}`) are now extracted to scalars. Figma float32 noise (e.g., `10.000000149`) rounds to nearest integer if difference < 0.001. This eliminated ~2,700 false positive mismatches in binding-token consistency checks.
