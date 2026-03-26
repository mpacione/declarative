# Tier Progress Tracker

Tracking round-trip verified curation actions against `Dank (Experimental)`.

**DB**: `Dank-EXP-02.declarative.db`
**Figma file**: `drxXOUOdYEBBQ09mrXJeYu`
**Figma variables**: 298 pushed (6 collections), all verified via read-back

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

### T1.2 — Rename Numeric Segments
- **Status**: PENDING
- **Scope**: 175 tokens with numeric segments (e.g. `color.surface.42`)
- **Approach**: Query usage context per token, infer semantic name

### T1.3 — Merge Near-Duplicate Colors
- **Status**: PENDING
- **Scope**: 2 pairs (ΔE < 3): `#DADADA`↔`#D1D3D9`, `#FFFFFF`↔`#F6F6F6`

### T1.4 — Delete Noise Tokens
- **Status**: PENDING
- **Scope**: ~50 tokens with ≤5 bindings

### T1.5 — Normalize Spacing Scale
- **Status**: PENDING
- **Scope**: 29 spacing tokens, arbitrary values (1-966px)

---

## Tier 2: Semantic — not started
## Tier 3: Generative — not started
## Tier 4: Structural — not started
## Tier 5: Conjure — not started
## Tier 6: Sync — T6.1 complete (push), read-back verified
