# Continuation — v0.2 entry point (post-breadth-test + Round-5 forensic)

> Supersedes `docs/continuation-v0.2.md`. v0.1.5 shipped at
> R3 (`f16dfc0`) and hardened with Fix #1 (`a54a3ed`); breadth test
> (00i-breadth-v1, commit `9e05bf0`) confirmed the pipeline
> generalises.

## State summary (read this first)

**Commits on main (latest first):**
```
4bfe393  docs(iteration): Round 5 journal + re-verification
a54a3ed  fix(renderer): leaf-parent appendChild gate + soft-error filter (Fix #1)
9e05bf0  feat(experiments/00i-breadth-v1): 20-prompt generalisation test
3543e4a  docs(iteration): R4 H7 attempted + reverted
f16dfc0  feat(universal): R3 — strip container fill from _generic_frame_template
ef1a2e8  docs(v0.1.5): iteration journal + ship-state reflection
7b0b705  feat(compose+renderer): H2 shadow overlay + _BACKBONE allowlist fix
1a30586  feat(compose): H1 always-apply template style + list/tabs/slider container fix
ea5d9b7  feat(diagnostics): dual fidelity scorer + 00g pre-H1 baseline
22e592e  docs(forensic): Mode 3 visual gap root-cause analysis + 6 heuristics
7038062  docs: v0.2 continuation (now superseded)
```

**Verified state:**
- 1,932 unit tests green
- 204 / 204 round-trip parity clean (33 s sweep)
- Canonical 00g: 12 / 12 VLM-ok at R3, fidelity 0.75 (most recent
  re-run had 11 / 12 rendered due to T=0.3 variance on
  12-round-trip-test — quality unchanged)
- Breadth 00i: 20 / 20 rendered, fidelity 0.72 (within 3 % of
  canonical → architecture generalises)
- VLM currently 429-throttled (Gemini rate-limit from heavy use);
  fidelity scorer is the reliable signal

**Rollback flags:**
- `DD_DISABLE_ARCHETYPE_LIBRARY=1` — A1 archetype library off
- `DD_ENABLE_PLAN_THEN_FILL=1` — A2 plan-then-fill on (default off)

## What was fixed this session

5 rounds of renderer-side forensic work on top of v0.1.5 ship:

| round | commit | change | VLM-ok | render-fid |
|---|---|---|---:|---:|
| R0 baseline | ea5d9b7 | fidelity scorer, pre-H1 | 6/12 | 0.25 |
| R1 H1 | 1a30586 | always-apply template style + generic fill/hug | 9/12 | 0.45 |
| R2 H2 | 7b0b705 | shadow overlay + `_BACKBONE` allowlist | 11/12 | 0.73 |
| **R3** | **f16dfc0** | **strip container fill from generic template** | **12/12** | **0.75** |
| R4 H7 | 3543e4a | attempted + reverted (image stroke → cascade) | — | — |
| Breadth | 9e05bf0 | 20 new prompts across 8 domains | — | 0.72 |
| **R5 Fix #1** | **a54a3ed** | **leaf-parent appendChild gate** | — | — |

## Deferred fixes (prioritised)

All from the 5-subagent parallel forensic; root causes diagnosed,
fixes specified.

### 1. Fix #4 — "×" icon fallback (HIGH visible impact)

**Symptom**: "×" glyph appears next to buttons across almost every
screen (meme-feed, shopping-cart, dashboard, etc.), reading as
"cancel/close."

**Root cause**: NOT a text fallback. The "×" is baked into Dank's
`button/large/translucent` component design; Mode 1 `createInstance`
inherits all the component's children including that X sub-icon.
LLM keeps suggesting that component because it's the highest-
instance-count button in Dank's CKR.

**Fix options (pick one):**
- (a) After `createInstance`, walk the new instance's children and
  remove the baked-in X icon specifically. Needs a child-pruning
  post-pass in the renderer.
- (b) Rank CKR suggestions by "cleanness" — prefer buttons without
  baked icon sub-children. Requires extending
  `dd/prompt_parser.py::build_project_vocabulary` to filter/rerank.
- (c) Edit Dank's `button/large/translucent` component to remove
  the baked X. Source-side fix; cleanest if Dank is the "system
  of record" for UI components. Needs Figma write access.

**Starter artefacts:**
- `dd/component_key_registry.py` (the CKR structure)
- `experiments/00i-breadth-v1/artefacts/01-shopping-cart/screenshot.png`
  (see "Proceed to Checkout ×")
- `render_test/run.js` has the createInstance path; investigate
  whether post-`createInstance` child manipulation is feasible.

**Expected impact**: every button stops showing "×", perceived
quality jump across 60 %+ of prompts.

### 2. Fix #5 — Horizontal layout for 4-column comparison etc.

**Symptom**: `03-pricing-compare` asked for a 4-column pricing
comparison; LLM emitted a `table` with ~20 text cells as children
in reading order. `dd/compose.py:147` forces screen-root direction
to vertical, so cells stack in one long list.

**Root cause**: `_generic_frame_template` for `table` has no
column-aware layout. No propagation of archetype-level horizontal
intent.

**Fix options:**
- (a) `table` gets a `column_count` prop; renderer emits a
  horizontal auto-layout with internal wrap-every-N logic. Needs
  template + renderer changes.
- (b) Detect ≥ 2 identical-type siblings at top level → infer
  horizontal direction. Crude but catches paywall-tier / carousel
  cases. Starter: `dd/compose.py:171` where we force
  `direction: vertical`.
- (c) Archetype skeleton JSON gets a top-level `layout_direction`
  hint; propagate through compose. Same shape as skeleton-level
  padding.

**Starter artefacts:**
- `experiments/00i-breadth-v1/artefacts/03-pricing-compare/{ir,script,screenshot}.json/png`
- `dd/compose.py:134-195` — screen-root wiring
- `dd/archetype_library/skeletons/paywall.json` — shows current
  skeleton format (no layout hint)

**Expected impact**: pricing-compare and onboarding-carousel
finally render with correct spatial layout. Moderate visible
impact on specific archetypes.

### 3. Fix #3 — Image placeholder visual polish

**Symptom**: `image` components render as solid light-blue
rectangles — reads as "unfilled paint" rather than "photo goes
here."

**Root cause (after H7 revert)**: we explicitly keep solid fill
(no stroke) to avoid the paint cascade H7 discovered. The fill
IS painting; it's just visually generic.

**Fix**: Mirror `_missingComponentPlaceholder` — a helper
`_imagePlaceholder(var, w, h)` that sets `fills = []` + adds
3-4 hatched LINE children at 45°. Line children don't paint-
cascade like strokes on frames do (proven — the missing-
component placeholder uses this pattern and hits no timeouts
on round-trip).

**Starter:**
- `dd/renderers/figma.py:1732+` — `_missingComponentPlaceholder`
  definition and preamble wiring (lazy emit when referenced)
- Subagent 3's earlier proposal (see `iteration-journal.md` R5)
- `dd/composition/providers/universal.py::_image_template` —
  remove `fill`, let the helper own the visual

**Expected impact**: low-moderate. Images stop looking plain
but it's polish, not a real defect.

### 4. 03-meme-feed Figma perf (Phase-2 layoutMode deferral)

**Symptom**: 4 cards × (image + text + button_group w/ 2
createInstance) = 55 s render timeout inside Figma. We hit this
at R2 and R3; the list-container-fill fix (R3) dropped mean
render time but this specific prompt is at the edge of the
bridge's 55 s execution cap.

**Root cause (hypothesis)**: Phase 1 sets `layoutMode = "VERTICAL"`
on every frame BEFORE Phase 2's `appendChild` cascade. Each append
triggers auto-layout recalc on an already-configured parent —
O(N²) cost for deeply-nested screens.

**Fix**: move `layoutMode` / `counterAxisAlignItems` / related
trigger-props from Phase 1 emission to a new Phase 2b that runs
AFTER all `appendChild`s land.

**Why deferred**: touches the core round-trip code path. 204/204
parity is load-bearing. Needs a dedicated session with parity
sweeps after every small change.

**Starter**:
- `dd/renderers/figma.py::_emit_layout` (line ~1812) currently
  emits auto-layout props
- Phase 1 / 2 / 3 markers in `generate_figma_script` (~line 944)
- The R3 notes in `docs/research/iteration-journal.md` Round 3

### 5. Second-project portability test

**Question**: does the pipeline work on a non-Dank Figma file?
The universal catalog provider doesn't depend on Dank data, but
the CKR and component_templates do. Dank is the only project
with 204 screens extracted.

**Action**:
- Pick a second Figma file (ideally with a design system + several
  screens)
- Extract via `dd extract` to a new SQLite DB
- Seed the component_key_registry
- Run `experiments/00g-mode3-v4/run_parse_compose.py` pointing at
  the new DB
- Measure fidelity, VLM, classifier routing
- If fidelity is within 5 % of Dank's 0.75, we've validated
  generalisation beyond one project

**Why important**: the whole "Dank specificity vs universal
architecture" question is unproven. Fix #4 especially depends on
Dank-specific button component baking; a second-project test
would show whether that's just-Dank or systemic.

## Current defect class taxonomy (v0.1.5 post-R5)

- **Resolved:**
  - KIND_FLAT_CARD (H1)
  - KIND_NO_SHADOW (H2)
  - KIND_NO_ROW_SEPARATION (H2 indirectly)
  - KIND_INVISIBLE_CONTAINER (R3 — container fills stripped)
  - KIND_LEAF_TYPE_APPEND (Fix #1 — renderer gate + soft-error
    filter)
  - KIND_TEXT_INPUT_EMPTY (subsumed by Fix #1)

- **Deferred:**
  - KIND_BAKED_ICON_INHERIT (Fix #4 — Dank component "×")
  - KIND_OVERPACKED_VERTICAL (Fix #5 — horizontal layout)
  - KIND_IMAGE_PLACEHOLDER_FLAT (Fix #3 — hatched helper)
  - KIND_RENDER_PERF_CASCADE (meme-feed — Phase 2 layoutMode)

## Useful commands

```bash
# State check
cd /Users/mattpacione/declarative-build
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

# Unit tests
python3 -m pytest tests/ -q --ignore=tests/test_child_composition.py \
  --ignore=tests/test_semantic_tree_integration.py \
  --ignore=tests/test_prompt_parser_integration.py \
  --ignore=tests/test_phase4b_integration.py \
  --ignore=tests/test_rebind_integration.py \
  --ignore=tests/test_screen_patterns_integration.py -m "not integration"

# Round-trip parity (always run after renderer changes)
python3 render_batch/sweep.py --port 9231 --skip-existing

# Re-run 00g canonical
PYTHONPATH=$(pwd) python3 experiments/00g-mode3-v4/run_parse_compose.py
PYTHONPATH=$(pwd) python3 experiments/00g-mode3-v4/run_render_walk.py
# + screenshot manifest + VLM as usual

# Re-run 00i breadth
PYTHONPATH=$(pwd) python3 experiments/00i-breadth-v1/run_experiment.py

# Score fidelity (prompt + render)
PYTHONPATH=$(pwd) python3 experiments/_lib/score_experiment.py \
  experiments/00g-mode3-v4
PYTHONPATH=$(pwd) python3 experiments/_lib/score_experiment.py \
  experiments/00i-breadth-v1

# VLM sanity gate (run 2-3× to stabilise; Gemini is flaky at Tier 1)
python3 -m dd inspect-experiment experiments/00g-mode3-v4 --vlm
```

## Guardrails (carried forward)

- **204/204 parity is load-bearing** — re-verify after any
  renderer/extractor/IR change
- **Unit tests ≥ 1,932 green** — don't delete tests, add new ones
  for new behavior (TDD)
- **Soft-error kinds don't flip rule gate** — use
  `_SOFT_ERROR_KINDS` pattern in `visual_inspect.py` when adding
  new structured diagnostics that aren't hard failures
- **Cross-reference Mode 3 walks against round-trip walks** before
  blaming the prompt layer — the round-trip is the fidelity oracle
- **Fidelity scorer** is the reliable metric when VLM is down
  (which happens; Gemini is flaky)

## Methodology tools worth keeping

- `dd/diagnostics/fidelity.py` — prompt + render fidelity scorer
  (primary signal when VLM is throttled)
- `experiments/_lib/score_experiment.py` — reusable scoring driver
  for any 00x-style experiment dir
- T1..T8 script-ablation pattern (see `iteration-journal.md`
  Round 3) — strip one property class at a time from a failing
  script, re-run through bridge, bisect the slow property
- Parallel-subagent forensic pattern — see
  `feedback_parallel_subagent_forensic.md`

## Session-kickoff checklist

```bash
# Verify nothing regressed since f16dfc0 + a54a3ed
git log --oneline -5
# Expected: 4bfe393 a54a3ed 9e05bf0 3543e4a f16dfc0

# Parity
python3 render_batch/sweep.py --port 9231 --skip-existing
# Expected: 0 generate_failed, 0 walk_failed, ~30 s

# Tests
python3 -m pytest tests/ -q [same excludes as above]
# Expected: 1,932 passed

# Sanity on existing artefacts
PYTHONPATH=$(pwd) python3 experiments/_lib/score_experiment.py \
  experiments/00g-mode3-v4
# Expected: mean render-fidelity ≥ 0.72
```

## Pick a starting move

1. **Fix #4** (baked-"×" icon inheritance) — biggest visible
   quality jump. Investigate post-createInstance child pruning or
   CKR reranking. Moderate risk.
2. **Fix #5** (horizontal layout) — targeted at specific
   archetypes. Start with option (c) archetype-skeleton
   `layout_direction` hint — smallest change. Low risk.
3. **Fix #3** (image placeholder) — pure cosmetic. Lowest risk;
   write the `_imagePlaceholder` helper mirroring
   `_missingComponentPlaceholder`.
4. **Second-project test** — port pipeline to a non-Dank file.
   High informational value; no code risk.
5. **Phase-2 layoutMode deferral** — only if 03-meme-feed perf
   specifically matters; high risk, dedicated session needed.

The forensic memo + iteration journal + this continuation doc
cover the full context. Subagents for any fresh defect class
investigation have a proven pattern.
