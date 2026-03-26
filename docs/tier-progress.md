# Tier Progress Tracker

Tracking round-trip verified curation actions against `Dank (Experimental)`.

**DB**: `Dank-EXP-02.declarative.db`
**Figma file**: `drxXOUOdYEBBQ09mrXJeYu`
**Figma variables**: 296 live (6 collections, includes T2.2 splits)

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

## Tier 3: Generative — not started
## Tier 4: Structural — not started
## Tier 5: Conjure — not started
## Tier 6: Sync — T6.1 complete (296 variables pushed, all round-trip verified)
