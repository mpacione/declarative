# Mode 3 forensic analysis — where A1/A2 output diverges from round-trip

**Status:** diagnostic memo, 2026-04-17.
**Goal:** stop guessing at prompt-layer fixes; classify the actual
visual defects in 00f / 00g / 00h, trace each to a specific pipeline
position, and derive heuristics grounded in the round-trip path that
already renders 204/204 cleanly.

## 1. Why this memo exists

v0.1.5 ran β's matrix (no contract edit beats S0), then shipped A1
archetype-conditioned few-shot (4 → 6 VLM-ok), then tried A2 plan-
then-fill (6 → 4 VLM-ok, regression). Every step was a prompt-layer
experiment. But the pipeline ALREADY renders 204 Dank screens
perfectly — round-trip parity. The gap isn't "LLM isn't structural
enough" — it's that **the structural output the LLM produces doesn't
propagate visual properties the way extracted-from-DB output does.**

## 2. The signal: round-trip vs Mode 3 walk stats

| metric (per-screen) | round-trip sample (n=5) | Mode 3 00g sample (n=5) |
|---|---|---|
| default 100×100 frames | 0 – 7 % | 0 – 17 % |
| frames with visible `fills` | 33 – 42 % | 46 – 83 % ← but mostly `[]` |
| frames with `strokes` | 2 – 45 % | **0 – 8 %** |
| frames with `effects` | 10 – 18 % | **0 % across every Mode 3 prompt** |

**0 % effects, near-0 % strokes.** That's the gap. Round-trip scripts
add shadows, background-blurs, and strokes to cards / containers;
Mode 3 never emits any of them.

Script-level same picture:

| property | round-trip screen 118 | Mode 3 04-dashboard (VLM broken) | Mode 3 01-login (VLM ok) |
|---|---:|---:|---:|
| `resize()` on frames | 100 % | 6 % | 67 % |
| `paddingTop` | 47 % | 6 % | 17 % |
| `effects =` | 32 % | **0 %** | **0 %** |
| `cornerRadius` | 53 % | 31 % | 50 % |
| `itemSpacing` | 63 % | 38 % | 67 % |

Simple prompts with 5-6 frames survive because even a skeletal `fills`
+ auto-layout can communicate a login form. Complex prompts with
16-21 frames (dashboard, paywall, feed) fail because "flat text on
uniform grey" is what 16 frames of `fills=[]` without strokes /
shadows / row separation look like.

## 3. Screenshot defect taxonomy

Working from the 00g artefacts with the most telling VLM verdicts:

### KIND_FLAT_CARD — "cards render as invisible rectangles"

**Where:** 04-dashboard, 06-spa-minimal, 10-onboarding-carousel, all
paywall tiers (05), all meme-feed cards (03).

**Symptom:** VLM sees "text stacked vertically without structure."
Screenshot: no visible card boundary, content bleeds into background,
sections run together.

**Root cause:** `_mode3_synthesise_children()` is the only function
that merges `PresentationTemplate.style` (fill / stroke / radius)
into the parent IR element. It runs ONLY when `comp.get("children")`
is empty AND there's no `component_key`. When the LLM provides
children (which it almost always does on A1 + A2), the parent `card`
element never receives its template's `fill`, `stroke`, `radius`.
Renderer sees no `element.style` to overlay, emits `fills = []`,
frame renders transparent.

Code refs:
- [`dd/compose.py:116`](dd/compose.py:116) — `elif not component_key and not _mode3_disabled()` gate
- [`dd/compose.py:440-451`](dd/compose.py:440) — the merge block
  that only runs inside synthesise_children
- [`dd/renderers/figma.py:1243-1259`](dd/renderers/figma.py:1243) —
  renderer overlay that reads `element.style`, gets `{}`

### KIND_NO_SHADOW — "cards don't pop from background"

**Where:** every card across every Mode 3 prompt.

**Symptom:** even when a card has a fill, it reads as flat with the
background. No sense of layering / elevation.

**Root cause:** The compose merge block above hard-codes the set of
style keys it propagates: `("fill", "fg", "stroke", "radius")`. Not
`"shadow"`, not `"effects"`. PresentationTemplate defines
`"shadow": "{shadow.card}"` but the token never reaches the IR.

Code ref: [`dd/compose.py:449`](dd/compose.py:449) —
`for key in ("fill", "fg", "stroke", "radius"):`

### KIND_EMPTY_IMAGE — "chart / image slots render as blank space"

**Where:** 04-dashboard (chart), 10-onboarding-carousel (slide
illustrations), 03-meme-feed (meme images).

**Symptom:** the chart / image slot is a blank rectangle. VLM reads
the surrounding context but the key visual (chart, illustration) is
just whitespace.

**Root cause:** `image` type falls through to createFrame without
any asset / placeholder. Unlike `_missingComponentPlaceholder` for
Mode-1 component misses (which renders a hatched grey rectangle with
a label — visually reads as "image goes here"), Mode 3 `image` nodes
get no equivalent.

Code ref: [`dd/renderers/figma.py`](dd/renderers/figma.py) —
`_missingComponentPlaceholder` exists and works for components;
Mode-3 `image` type has no such fallback.

### KIND_NO_ROW_SEPARATION — "tables read as text lists"

**Where:** 04-dashboard table, 09-drawer-nav nav list, 05-paywall
feature lists.

**Symptom:** rows of "Date | Description | Amount | Status" (text
labels) followed by "Jan 15, 2024 | Payment received | $2,500.00 |
Completed" (row data) render as flat vertical text. VLM: "a few
unstyled text labels." No sense that it's tabular.

**Root cause:** `list_item` + `table` PresentationTemplates don't
emit stroke / bg-alternation / divider. Round-trip adds `strokes`
to 5-45 % of nodes; Mode 3 adds to 0-8 %.

### KIND_OVERPACKED_VERTICAL — "three columns stacked as one"

**Where:** 05-paywall (3 pricing tiers all stacked vertically),
10-onboarding-carousel (3 slides stacked instead of side-by-side).

**Symptom:** content IS there, but the "carousel" / "3-column
pricing" structure isn't — everything is one long vertical scroll.

**Root cause:** compose forces `direction = vertical` on the screen
root's direct children ([`dd/compose.py:138`](dd/compose.py:138)).
The archetype skeleton for onboarding / paywall has horizontal
sibling structure, but the screen-root auto-layout flattens it.

## 4. VLM scoring pattern (γ-backed, now confirmed)

| VLM verdict | pattern |
|---|---|
| ok (7-8) | recognizable text content (heading + labels + button text) reads as a familiar screen pattern. **Visual fidelity is not required** — 05-paywall VLM-ok has 2 % IR-style coverage, 5 % resize. |
| partial (4-5) | some content + one missing key visual (chart, illustration, card framing). |
| broken (2-3) | text stacked vertically without visual grouping; key visuals entirely missing. |

**Takeaway:** VLM gives credit for recognizable TEXT + one clear
landmark (a button, an icon, an avatar). A login form with 5 frames
where 3 have resize + fills scores ok. A dashboard with 16 frames
where 1 has resize fails — because the landmarks (chart, table rows)
aren't visually differentiable.

## 5. Six heuristics, ranked by effort × impact

### H1 — Always apply template style/layout to the parent

**What:** extract the style/layout merge block from
`_mode3_synthesise_children` into a standalone
`_apply_template_to_parent(comp_type, variant, element)` and call it
from `_build_element` for every element, regardless of children
source.

**Why:** single biggest root cause across KIND_FLAT_CARD, KIND_NO_SHADOW,
and most of KIND_NO_ROW_SEPARATION. A1 / A2 both regressed here
because the LLM supplying children disabled the merge.

**Effort:** ~20 lines + tests. One commit.

**Expected impact:** +2-3 VLM-ok (dashboard, carousel, maybe paywall
moves from flat-text to cards-with-borders).

### H2 — Expand the style-merge allowlist

**What:** compose's merge set is `("fill", "fg", "stroke", "radius")`.
Add `"shadow"`, `"effects"`, `"padding"`, `"gap"`.

**Why:** KIND_NO_SHADOW is a simple dictionary-key fix. PresentationTemplate
already defines these.

**Effort:** 1-line + renderer update to read `element.style.shadow`
+ emit `effects = [{type: "DROP_SHADOW", ...}]`.

**Expected impact:** marginal on its own, but critical when combined
with H1 — without shadow, "applied-template cards" still look flat.

### H3 — Image/media placeholder visual

**What:** when an IR `image` or `vector` type emits without asset
backing, render a hatched placeholder like
`_missingComponentPlaceholder` does for missing COMPONENTS. Light
grey frame, 45° hatch, optional "image" label.

**Why:** KIND_EMPTY_IMAGE. The helper already exists; just extend
the `image` type's render path to use it.

**Effort:** ~15 lines (new `_emptyImagePlaceholder` helper modeled
on the existing one + dispatch).

**Expected impact:** +1 VLM-ok (dashboard chart + carousel
illustrations get visual anchors, readable as intended).

### H4 — Table / list_item row separation

**What:** `table` and `list_item` PresentationTemplates emit a
bottom-stroke or low-opacity divider. Maintain Mode-1 override
precedence (project CKR wins as today).

**Why:** KIND_NO_ROW_SEPARATION. Round-trip screens with tables have
strokes on 45 % of nodes — that's where the difference lands.

**Effort:** template updates in `dd/composition/providers/universal.py`
+ `_UNIVERSAL_MODE3_TOKENS` (new `color.surface.divider` token).

**Expected impact:** +1 VLM-ok (dashboard table becomes legible).

### H5 — Screen-root direction honors archetype when horizontal

**What:** `compose.py:138` hard-forces `direction=vertical` on screen
root's direct children. For archetypes where the skeleton specifies
horizontal sibling layout (onboarding-carousel tier row, paywall
tier row), propagate that to the enclosing frame's auto-layout.

**Why:** KIND_OVERPACKED_VERTICAL. Currently the carousel collapses
3 slides into one vertical stack; same for pricing tiers.

**Effort:** medium. Requires either an archetype-level layout hint
or detecting "sibling-repeating top-level cards" and wrapping them
in a horizontal auto-layout parent.

**Expected impact:** +1-2 VLM-ok (carousel finally reads as a
carousel; paywall reads as tier comparison).

### H6 — Rule-gate structural signature

**What:** the existing `RuleBasedScore` tracks `total_node_count` +
`container_coverage` but doesn't track `strokes_rate` / `effects_rate`.
Add them and calibrate thresholds against the round-trip's stable
signature (strokes 5-45%, effects 10-18%, default100 ~0%).

**Why:** would catch A2's paywall plan-invalid, would have flagged
that A1 had 0% effects from the start. The rule-gate currently
reports "visible_ratio=0.79" which sounds fine but misses "effects=0%
which correlates with broken VLM verdict."

**Effort:** ~40 lines, extends the module added in Commit D.

**Expected impact:** closes the observability gap between "something's
wrong" and "here's which invariant you broke."

## 6. Recommended execution order

Given Week 2 scope should close the VLM-ok gap, and H1 is clearly
the tallest pole:

1. **H1** first — single commit, highest leverage. Re-run 00g with
   H1 only; if it closes ≥ 7 VLM-ok, ship v0.1.5 there.
2. **H2** next — piggybacks on H1 (same file, same tests).
3. **H3** third — orthogonal, targets dashboard / carousel, easy to
   measure impact.
4. **H4** and **H5** as stretch — higher effort, conditional on H1-3
   not already clearing the gate.
5. **H6** in parallel — rule-gate calibration is low-risk and buys
   ongoing observability.

The matrix work from v0.1.5 Week 1 is not wasted: the variance-floor
numbers + structural-density infrastructure still apply. But the
"next engineering dollar" for v0.1.5 is the **renderer-adjacent fix
of H1**, not another round of prompt engineering.

## 7. What this memo does not claim

- A1 was wrong to ship. It still gave +2 VLM-ok over 00f and is the
  default-on baseline. H1 stacks on top of A1.
- A2 is dead. The plan-then-fill architecture is fine; it's just
  that plan-then-fill WITHOUT H1 regressed because fewer nodes went
  through the synthesise_children path. Re-run 00h after H1 lands;
  likely recovers or beats A1.
- The round-trip is ground truth for quality. It's ground truth for
  the *completeness* of what visual properties a screen needs; but
  it comes from DB extraction, so it doesn't tell us what visual
  properties a *well-designed* Mode 3 output should synthesize. H1-5
  should aim for round-trip-like density, not round-trip-fidelity.
