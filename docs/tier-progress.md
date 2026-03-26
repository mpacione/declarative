# Tier Progress Tracker

Tracking round-trip verified curation actions against `Dank (Experimental)`.

**DB**: `Dank-EXP-02.declarative.db`
**Figma file**: `drxXOUOdYEBBQ09mrXJeYu`
**Figma variables**: 289 live (started at 298, minus 9 deleted/merged)

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

## Tier 2: Semantic — ready to start

Next actions:
- T2.1: Context-based renaming of 175 numeric tokens
- T2.4: Group spacing into t-shirt sizes
- T2.5: Categorize colors by role

## Tier 3: Generative — not started
## Tier 4: Structural — not started
## Tier 5: Conjure — not started
## Tier 6: Sync — T6.1 complete (298 variables pushed, read-back verified)
