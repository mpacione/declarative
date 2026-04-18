# Markup fixtures — Plan A.3 + A.4 reference screens

Hand-authored `.dd` fixture files and L0+L1+L2 state summaries for three Dank
Experimental reference screens. Produced during Plan A.3/A.4 of the v0.3
foundation work. See `docs/plan-v0.3.md` for scope.

## Purpose

These fixtures are **normative**. They are the ground truth that the dd markup
grammar (`docs/spec-dd-markup-grammar.md`) is designed to express. If the grammar
says one thing and a fixture says another, the grammar is wrong — iterate it.

Each fixture exercises a different axis-density profile and a different slice
of the grammar surface:

| File | Screen id | Density profile | What it exercises |
|------|-----------|-----------------|-------------------|
| `01-login-welcome.dd` | 181 | Full axes, no tokens | Component refs, gradients, repeated structural frames, raw literals (pre-Stage-3) |
| `02-card-sheet.dd`    | 222 | Full axes + card `define` | First `define` pattern, slot fills, overlay + sheet composition |
| `03-keyboard-sheet.dd`| 237 | Full axes + density variance | Heading-heavy sheet, keyboard overlay, extends screen 222 (states of same flow) |

## Selection rationale

Picked from 204 iPhone/iPad app screens on 2026-04-18 using:

```sql
SELECT s.id, s.name,
  (SELECT COUNT(*) FROM nodes n WHERE n.screen_id=s.id)               AS l0,
  (SELECT COUNT(*) FROM screen_component_instances sci
                       WHERE sci.screen_id=s.id)                      AS l1,
  (SELECT COUNT(DISTINCT sci.canonical_type)
     FROM screen_component_instances sci WHERE sci.screen_id=s.id)    AS n_types
  FROM screens s WHERE s.screen_type='app_screen' AND device_class='iphone';
```

### Screen 181 — "iPhone 13 Pro Max - 119" (simple)

- 207 L0 nodes · 96 L1 classified · **8 distinct canonical types** · 0 L2 bound (DB has no accepted tokens yet)
- Structure: 57 component instances, most of which are icons; three vertical
  content containers; a large translucent CTA button with the Dank brand
  gradient (`#D9FF40→#9EFF85`).
- Why simple: the lowest L1 count among iPhone screens AND the fewest
  distinct canonical types. Good for exercising the base of the grammar
  without introducing card/define patterns.

### Screen 222 — "iPhone 13 Pro Max - 87" (medium)

- 303 L0 nodes · 157 L1 classified · **10 distinct canonical types**
  (introduces `card` and `slider`) · 0 L2 bound
- Structure: meme-editor card-sheet state. `Overlay` + `button/toolbar` ×2 +
  `card/sheet/success` + system chrome. First screen that exercises card as
  a first-class canonical type.
- Why medium: ~50% more content than 181, introduces new canonical types
  (card, slider), and sets up the 222↔237 delta (state pair) that exercises
  small-edit grammar later.

### Screen 237 — "iPhone 13 Pro Max - 79" (complex)

- 417 L0 nodes · 181 L1 classified · **9 distinct canonical types** ·
  0 L2 bound
- Structure: meme-editor keyboard-sheet state. Superset of 222's structure
  with `ios/alpha-keyboard` and ~34 headings (vs 8 in 222). System chrome
  includes the software keyboard (design content, not filter target — per
  `feedback_system_chrome_is_design`).
- Why complex: largest L0/L1 counts in the iPhone corpus at this complexity
  profile, and the 222↔237 pairing exercises state-variant expression.
  Heading-dense content tests text-node emission.

## Files per screen

- `NN-slug.l0-summary.md` — human-readable dump of L0+L1+L2 state for the
  screen. Generated via the script shown in Plan A.3 commit message; not
  re-generated on the fly. Frozen reference for authoring fixtures.
- `NN-slug.dd` — hand-authored dd markup fixture. Normative — the grammar
  spec must parse this.
- (future) `NN-slug.invalid-*.dd` — three or more invalid variations per
  fixture that the grammar must reject. Required per S2 deliverable (4).

## Token vocabulary for fixtures

The Dank DB has **zero accepted tokens** as of 2026-04-18 (all 293,183
`node_token_bindings` rows are `binding_status='unbound'`). Fixtures are
authored as they SHOULD appear post-Stage-3 — with synthetic tokens drawn
from `_UNIVERSAL_MODE3_TOKENS` (shadcn-flavored defaults in `dd/compose.py`).

Raw literals MAY appear in fixtures where no plausible universal-token
alias exists (e.g. the Dank brand gradient `#D9FF40 → #9EFF85`). Per Tier 0
§3.3, this invariant is temporarily waived between Stage 1 and Stage 3;
Stage 3 closes it by defining synthetic tokens for every raw cluster.

## What to read next

- `../../docs/requirements.md` — Tier 0 overall requirements
- `../../docs/requirements-v0.3.md` — Tier 1 v0.3 scope
- `../../docs/spec-dd-markup-grammar.md` — the grammar these fixtures are normative for
- `../../docs/spec-l0-l3-relationship.md` — how these fixtures derive from the DB state
