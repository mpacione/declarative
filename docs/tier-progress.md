# Tier Progress Tracker

Tracking round-trip verified curation actions against `Dank (Experimental)`.

**DB**: `Dank-EXP-02.declarative.db`
**Figma file**: `drxXOUOdYEBBQ09mrXJeYu`
**Figma variables**: 353 live (8 collections: Color Primitives, Color Semantics, Component States+Dark, Typography, Spacing, Effects, Radius, Opacity)
**DB tokens**: 379 total (45 color primitives + 52 color semantics + 282 other curated + 26 aliased)
**Tests**: 641 passing

## Verification Pattern

Every action follows this round-trip:
1. `curate-report --json` identifies the issue
2. Action modifies DB
3. DB state verified (query)
4. Push to Figma via MCP (`batch_update_variables` / `setup_design_tokens`)
5. Read back from Figma via plugin API
6. Compare DB value to Figma value

---

## Tier 1: Cleanup

### T1.1 — Round Fractional Font Sizes
- **Status**: DONE
- **Scope**: 19 fractional fontSize tokens (e.g. `36.86px` → `37px`)
- **DB verify**: 0 remaining fractional values
- **Figma verify**: `type/display/md/fontSize` = 37 (was 36.86) — match confirmed
- **Actions**: 19 `token_values` updated, 19 Figma variables updated

### T1.3 — Merge Near-Duplicate Colors
- **Status**: DONE
- **Scope**: 1 pair merged (ΔE 2.3: `#DADADA`↔`#D1D3D9`), 1 pair skipped (intentionally different roles: border vs surface)
- **DB verify**: `color.surface.15` deleted, `color.surface.12` now 387 bindings (was 376 + 11)
- **Figma verify**: `color/surface/15` variable deleted, `color/surface/12` = `#DADADA` confirmed
- **Actions**: 1 merge, 1 Figma variable deleted

### T1.4 — Delete Noise Tokens
- **Status**: DONE
- **Scope**: 8 single-use tokens deleted (6 shadow outliers, 2 spacing outliers)
- **DB verify**: All 8 tokens removed, bindings reverted to unbound
- **Figma verify**: 8 Figma variables deleted
- **Deleted tokens**: `shadow.10.radius`, `shadow.11.radius`, `shadow.xl.*` (4), `space.12`, `space.28`

### T1.2 — Rename Numeric Segments
- **Status**: DEFERRED → Tier 2
- **Reason**: Requires contextual judgment (querying where tokens are used to determine semantic names). Not purely mechanical.
- **Scope**: 175 tokens with numeric segments

### T1.5 — Normalize Spacing Scale
- **Status**: DEFERRED → Tier 2
- **Reason**: Requires design decision about target scale. Current scale has natural clustering around 4px grid but many outliers need judgment calls.
- **Scope**: 27 spacing tokens (was 29, minus 2 deleted noise)

---

## Tier 2: Semantic

### T2.1 — Context-Based Renaming
- **Status**: DONE
- **Scope**: 175 numeric tokens renamed to semantic names (0 remaining)
- **Colors (39)**: Usage-context analysis → role-based names (e.g. `color.surface.42` → `color.surface.ink`, `color.surface.29` → `color.brand.accent`)
- **Opacity (4)**: Value-based → descriptive (`opacity.20` → `opacity.faint`)
- **Radius (14)**: Numeric → value-prefixed (`radius.10` → `radius.v9`)
- **Spacing (19)**: Numeric → value-prefixed (`space.10` → `space.v10`)
- **Typography (94)**: Numeric → font+size+weight descriptors (`type.body.11` → `type.body.s18`, collisions disambiguated with weight: `type.body.inter17w400`)
- **DB verify**: 0 remaining numeric-segment tokens
- **Figma verify**: 289 variables across 6 collections, all names match DB

### T2.2 — Split Overloaded Tokens
- **Status**: DONE
- **Scope**: 5 color tokens split by role (fill vs stroke vs effect)
- **Splits**:
  - `color.border.black` (#000000) → `color.text.primary` (4,394 TEXT fills), `color.icon.primary` (2,269 VECTOR fills), `color.shadow.primary` (1,079 effects), `color.surface.black` (4,220 frame fills), `color.border.black` (24,535 strokes)
  - `color.border.primary` (#FFFFFF) → `color.surface.white` (4,929 fills), `color.border.primary` (3,374 strokes)
  - `color.border.tertiary` (#047AFF) → `color.brand.link` (964 fills), `color.border.accent` (1,989 strokes)
  - `color.border.secondary` (#FF0000) → `color.feedback.danger` (769 fills), `color.border.error` (51 strokes)
- **DB verify**: All new tokens have correct binding counts, old tokens retain stroke-only bindings
- **Figma verify**: 296 variables across 6 collections, all match DB
- **Bug found**: `split_token()` doesn't inherit parent's tier — new tokens come in as `extracted`, must manually set to `curated`

### T2.3 — Create Semantic Aliases
- **Status**: DONE
- **Scope**: 8 semantic aliases created in new "Semantic" collection
- **Aliases**: `color.danger` → `color.feedback.danger`, `color.warning` → `color.feedback.warning`, `color.error` → `color.feedback.error`, `color.link` → `color.brand.link`, `color.accent` → `color.brand.accent`, `color.canvas` → `color.surface.ink`, `color.card` → `color.surface.primary`, `color.muted` → `color.surface.muted`
- **DB verify**: `alias_of` column correctly set, `v_resolved_tokens` follows chain
- **Figma verify**: Not pushed — aliases are a semantic layer for code consumers, not Figma variables

### T2.4 — Group Spacing Into T-Shirt Sizes
- **Status**: DONE
- **Scope**: 19 numeric spacing tokens renamed to `space.s{value}` pattern (e.g. `space.v10` → `space.s10`)
- **Convention**: xs–4xl (1–8px) kept as t-shirt sizes, 9px+ use `s{N}` prefix since t-shirt sizes break down past 4xl
- **DB verify**: All 27 spacing tokens consistently named
- **Figma verify**: Spacing collection recreated with 27 variables, all match

### T2.5 — Categorize Colors By Role
- **Status**: DONE (completed as part of T2.1 — colors now have role prefixes: surface, border, brand, text, icon, palette, feedback, effect)

### T2.6 — Identify Interactive States
- **Status**: DONE (generated, not extracted)
- **Scope**: 12 button state tokens created from approximated values (lighten/darken via HLS)
- **Approach**: File lacks variant architecture, so we generated states from the primary button color (#634AFF brand.accent):
  - Primary: default, hover (+12% lightness), pressed (-15% lightness), disabled (same + opacity)
  - Secondary: default (#FFF), hover (-5%), pressed (-10%), disabled (same + opacity)
  - Border states for both variants
- **DB verify**: 12 new tokens in Semantic collection, all tier='curated'
- **Figma verify**: "Component States" collection with 12 variables, all values match DB exactly
- **Learning**: HLS lighten/darken produces visually inconsistent shifts on saturated colors. Should use OKLCH for perceptually uniform state derivation.

---

## Tier 2: Complete
All T2 actions done. 308 Figma variables across 7 collections, 8 semantic aliases, 316 total DB tokens.

---

## Tier 3: Generative

### T3.1 — Derive Dark Mode
- **Status**: DONE
- **Scope**: 64 dark mode color values derived via OKLCH lightness inversion
- **Approach**: Used `create_theme(transform="dark")` from `dd/modes.py`. Inverts OKLCH lightness for all color tokens.
- **Collections affected**: Colors (52 tokens), Component States (12 tokens) — both now have Default + Dark modes
- **DB verify**: 64 dark mode values in `token_values`, all color tokens have 2 modes
- **Figma verify**: 308 variables, Colors and Component States collections show Default + Dark modes. Spot check: `color/text/primary` Dark = #FFFFFF (was #000000) — correct.
- **Learning**: OKLCH inversion too aggressive for pastel/near-white colors (yellow #FFE500 → #030200 near-black). Needs dampened inversion with floor clamps for production. Infrastructure works perfectly though.

### T3.3 — Create Missing Scale Steps
- **Status**: N/A
- **Reason**: Spacing has complete 1-32px coverage on 4px grid. Radius has complete 0-28px coverage. No meaningful gaps to fill.

### T3.4 — Generate Component Tokens
- **Status**: DONE
- **Scope**: 18 component token aliases for 4 top components
- **Components**: button/large/translucent (5 tokens), button/small/translucent (4), button/toolbar (4), ios/safari-nav (5)
- **Pattern**: `comp.{componentName}.{property}` → aliases primitive token (e.g. `comp.buttonLg.radius` → `radius.v10`)
- **DB verify**: 26 total aliased tokens (8 semantic + 18 component)
## Tier 3: Complete
Dark mode derived, component tokens created. 308 Figma variables (2 collections with Dark mode), 334 total DB tokens (308 curated + 26 aliased).

---

## Tier 4: Structural

### T4.1 — Split Primitives and Semantics (Colors)
- **Status**: DONE
- **Scope**: 52 color tokens split into Primitives (45 value-based) + Semantics (52 aliases)
- **Primitives**: 45 tokens named by hue family + shade (`prim.gray.500`, `prim.blue.400`, etc.), 9 hue families, 2 modes (Default + Dark)
- **Semantics**: 52 existing color tokens converted to aliases of primitives. Names unchanged (`color.surface.searchbar` → `prim.gray.500`)
- **Figma**: "Color Primitives" collection (45 variables), "Colors" collection variables updated to alias primitives via `createVariableAlias`
- **Re-pointed aliases**: 14 Semantic collection aliases re-pointed from color tokens directly to primitives (prevents depth-2 chains)
- **Bindings**: 58,073 bindings unchanged (reference semantic token IDs, not affected by alias conversion)
- **DB collections**: Colors renamed to "Color Semantics", new "Color Primitives" collection added (now 8 collections total)
- **New functions**: `create_collection()`, `convert_to_alias()` in `dd/curate.py`

### T4.2 — Add Modes (Dark, Compact, High Contrast)
- **Status**: DONE (DB), Figma push pending
- **Dark mode completed**: Added to Effects (26), Opacity (4), Radius (23), Spacing (27), Typography (164). Non-color values copied as-is.
- **Compact mode**: Applied to Effects, Radius, Spacing, Typography with 0.875 scale factor. Dimension values scaled, non-dimensions copied.
- **High Contrast mode**: New `apply_high_contrast()` function. Pushes light colors lighter (L > 0.5 → L×1.2+0.1), dark colors darker (L < 0.5 → L×0.6). Applied to Color Primitives (45) and Semantic/Component States (12).
- **Mode coverage**: 8 collections × 2-3 modes each. Color Semantics has no values (aliases). Opacity has no Compact (not applicable).

### T4.3–T4.5 — not started

---

## Tier 5: Conjure — not started
## Tier 6: Sync

### T6.1 — Push Variables to Figma
- **Status**: DONE
- **Scope**: 308 variables across 7 collections (Colors+Dark, Component States+Dark, Typography, Spacing, Effects, Radius, Opacity)

### T6.2 — Write Back Variable IDs
- **Status**: DONE
- **Scope**: 308/308 tokens mapped to Figma variable IDs via name matching

### T6.3 — Rebind Nodes to Variables
- **Status**: DONE
- **Scope**: 182,877 bindings across 193 compact scripts (~950 bindings each), 0 errors
- **Execution**: 108 seconds via PROXY_EXECUTE with 200ms inter-script delay
- **Property types**: fill.color, stroke.color, effect.color/radius/offset/spread, cornerRadius, padding.*, itemSpacing, fontSize, fontFamily, fontWeight, opacity, strokeWeight
- **Error persistence**: Errors written to `figma.root.pluginData('rebind_errors')` — survives crashes
- **Post-rebind restorations**: 5,128 fill opacities, 297 stroke opacities, 9,807 effect color alphas, 1,408 auto-spacing nodes
- **Handler fixes committed**: preserves paint opacity, effect alpha, skips itemSpacing on SPACE_BETWEEN nodes

### T6.4 — `dd push` CLI Command
- **Status**: DONE
- **Scope**: CLI command generating structured JSON manifests for agent-executed MCP calls
- **Phases**: `--phase variables` (create/update/delete Figma variables), `--phase rebind` (generate rebind scripts), `--phase all` (both)
- **Incremental sync**: Diffs DB vs Figma state via `--figma-state`, classifies tokens as CREATE/UPDATE/DELETE/UNCHANGED
- **Writeback**: `--writeback --figma-state` applies variable ID writeback after agent executes CREATE actions
- **Dry run**: `--dry-run` shows summary counts without generating action payloads
- **Compact rebind encoding**: Property shortcodes (e.g. `fontSize`→`fs`, `fill.0.color`→`f0`) reduce script size ~60%, fitting ~950 bindings per 50K char script
- **Opacity restoration**: `generate_opacity_restore_scripts()` runs as mandatory post-step after every push. Restores fill/stroke paint opacity and effect color alpha from DB source of truth.
- **Real DB**: 379 tokens → 8+ MCP calls (batched at 100), 182,877 bindings → 193 rebind scripts
