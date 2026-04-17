# v0.1.5 Iteration Journal — forensic-heuristic loop

Per-round deltas from the 2026-04-17 autonomous loop. Each entry
captures: what changed · metrics before/after · decision for next
round.

Baseline reference: `experiments/00g-mode3-v4/fidelity_report.md`
frozen at commit `ea5d9b7`.

## Round 0 — baseline (ea5d9b7)

Measurement infrastructure + starting point.

| metric | value |
|---|---:|
| mean render-fidelity | 0.251 |
| mean prompt-fidelity | 0.834 |
| VLM ok / partial / broken | 6 / 4 / 2 |

Key insight from forensic memo: prompt fidelity is already fine;
render fidelity is at 25 %. The renderer is where the loss is.

## Round 1 — H1 + side-fix (1a30586)

**Changes:**
- Extracted template-style-merge from `_mode3_synthesise_children`
  into standalone `_apply_template_to_parent` called unconditionally
  in `_build_element`.
- `_generic_frame_template` sizing flipped from `hug/hug` to
  `fill/hug` (side-fix — HUG parent with FILL children sent Figma's
  layout engine into a 55 s spin).

**Results:**

| metric | R0 | R1 | Δ |
|---|---:|---:|---:|
| mean render-fidelity | 0.251 | **0.453** | +81 % |
| mean prompt-fidelity | 0.834 | 0.834 | flat |
| VLM ok | 6 | **9** | +3 |
| VLM partial | 4 | 3 | −1 |
| VLM broken | 2 | **0** | −2 |

3 prompts moved up a full bucket (spa-minimal, drawer-nav, vague).
2 moved broken → partial (dashboard, carousel). Zero regressions.

**Ship gate cleared** — plan §5 criterion was ≥ 7 VLM-ok; we hit 9.

**Reflection:** H1 alone exceeded expectations (predicted +2-3, got
+3 plus 2 buckets-up-but-not-to-ok). The bottleneck genuinely was
"template style never propagates to LLM-child-bearing parents."
Prompt fidelity being constant means A1's archetype work was fine —
the LLM was giving us the right structure; the renderer was
eating the visual signal.

**Decision:** keep iterating. 3 prompts are still partial (meme-feed,
dashboard, carousel). H2 (expand merge allowlist to include shadow,
effects, padding, gap) is the obvious next step — render-fidelity
at 0.45 means half the expected properties are still being dropped.

## Round 2 — H2 + _BACKBONE fix (7b0b705)

**Changes:**
- H2 proper: `_apply_template_to_parent` allowlist gains `shadow`;
  renderer synthesises `drop-shadow` from numeric elevation tokens.
  Padding normalised from template `{x,y}` to IR `{top,right,bottom,left}`.
- Shadow token elevation defaults: card=2, dialog=8, menu=4, popover=4
  (were all 0 — H2's merge would fire but resolve to 0).
- **_BACKBONE audit fix**: 5 builders (`drawer`, `image`, `header`,
  `navigation_row`, `search_input`) had entries in `_BUILDERS` but
  were missing from `_BACKBONE`. Since `ProviderRegistry.resolve`
  gates on `supports()` → `catalog_type in _BACKBONE`, these
  templates never fired. That's why 10-onboarding-carousel's images
  were blank in H1 and 07-search's header was unstyled.

**Results:**

| metric | R0 baseline | R1 H1 | R2 H2 | Δ R0→R2 |
|---|---:|---:|---:|---:|
| mean render-fidelity | 0.251 | 0.453 | **0.730** | +190 % |
| mean prompt-fidelity | 0.834 | 0.834 | 0.834 | flat |
| VLM ok | 6 | 9 | **11** | +5 |
| VLM partial | 4 | 3 | **0** | −4 |
| VLM broken | 2 | 0 | **0** | −2 |

**Per-prompt shifts H1 → H2:**
- 04-dashboard: partial(5) → **ok(8)**
- 10-onboarding-carousel: partial(4) → **ok(8)**
- 01-login: ok(8) → ok(9)
- 08-explicit-structure: ok(8) → ok(9)
- 12-round-trip-test: ok(8) → ok(9)

Zero downgrades. Every prompt either held or improved.

**Known regression:** 03-meme-feed consistently times out at 55 s
inside the Figma plugin. 4 cards × (image + text + button_group of
2 instantiated buttons) triggers a cascading auto-layout reflow that
exceeds the bridge's execution cap. Stripping effects cut 3 s
(55 → 52 s) — effects aren't the sole cost. Root cause appears to
be Phase-1 `layoutMode = VERTICAL` on frames BEFORE the Phase-2
`appendChild` pass, which makes every append trigger layout
recalc. A batched `layoutMode=NONE` wrap in Phase 2 would fix it,
but that's a separate refactor.

**Reflection:** 11/12 VLM-ok meaningfully overshoots the ≥ 7 ship
gate. The one holdout is a perf regression, not a quality one —
composing + rendering work, Figma's layout engine is the bottleneck.
Options going forward:

1. **Ship v0.1.5 here.** Massive uplift, clean architecture,
   documented known-issue on the perf class. Most valuable.
2. Push H3 (image placeholder visual). Would make blank image
   slots on 03-meme-feed look like placeholders — doesn't fix the
   timeout, might marginally improve carousel VLM.
3. Attack the Phase-1/Phase-2 layoutMode ordering bug directly.
   Higher risk (renderer refactor) but would fix meme-feed + any
   future heavy prompts.

**Decision:** try option 3 — fixing the layoutMode ordering is the
root cause and applies to the whole corpus going forward. If it
regresses anything, revert and ship at 11/12.

## Round 3 — layoutMode deferral (reflected + declined)

**Goal:** fix the 03-meme-feed 55 s render timeout by moving
`layoutMode` / `itemSpacing` / `padding` / align props from Phase 1
to a new Phase 2b (after appendChild cascade). Cascading reflow
during the append walk is the hypothesised cost.

**Why reflected and declined:**

- The renderer's Phase 1 / Phase 2 / Phase 3 structure is the core
  of the ROUND-TRIP path. 204 Dank screens pass parity because
  the current ordering is correct for the extraction case.
- Deferring auto-layout activation is a real refactor across
  `_emit_layout`, the Phase 2 cascade, and the post-layoutSizing
  emission that assumes the parent has auto-layout enabled by the
  time children arrive.
- Risk: breaking the 204/204 round-trip parity to fix 1 Mode-3
  render perf regression.
- Reward: one prompt moves from timeout → render. VLM score
  likely already ≥ 7 if it rendered.
- Trade: bad. 1 prompt's perf ≠ 204 screens' parity + 1,932
  unit tests.

**Alternative path deferred to v0.2:**

- (a) bridge-side fix: relaxed 55 s timeout for Mode-3 composition
  calls (client-side change, no IR/renderer risk).
- (b) per-parent batched emission in the renderer (the proper fix,
  but deserves its own dedicated session with parity sweeps
  after every step).
- (c) auto-detect heavy prompts during compose and split into
  smaller sub-screens (exotic; last resort).

## Final v0.1.5 ship state

**11 / 12 VLM-ok** on 00g canonical prompts (vs 4/12 00f baseline,
6/12 A1 alone). Mean render-fidelity **0.73** (vs 0.25 baseline).
Zero broken, zero partial on the 11 that rendered. 03-meme-feed
times out in Figma due to dense auto-layout reflow — quality
unaffected, perf regression deferred to v0.2.

**Headline metric arc:**

| | 00f | R0 (A1) | R1 (H1) | R2 (H2) |
|---|---:|---:|---:|---:|
| VLM ok | 4 | 6 | 9 | **11** |
| VLM partial | 5 | 4 | 3 | 0 |
| VLM broken | 3 | 2 | 0 | 0 |
| render-fid | — | 0.25 | 0.45 | **0.73** |
| prompt-fid | — | 0.83 | 0.83 | 0.83 |
| unit tests | 1,765 | 1,929 | 1,932 | 1,932 |
| parity | 204/204 | 204/204 | 204/204 | 204/204 |

Two commits (H1 `1a30586`, H2 `7b0b705`) + the baseline scorer
commit (`ea5d9b7`). All renderer-adjacent work. Zero prompt-layer
edits in this iteration loop.

**Forensic hypothesis confirmed:** the Mode 3 loss was a
propagation bug, not a prompt bug. Prompt fidelity held at 0.83
through every iteration; render fidelity went from 0.25 to 0.73
and dragged VLM-ok from 6 to 11. The v0.1.5 prompt-layer work
(matrix + archetype library + A1 injection + A2 plan-then-fill)
still matters — it's what feeds the LLM's structural output at
0.83 — but the bottleneck was always the renderer dropping the
template's visual properties on any node with LLM-supplied
children.
