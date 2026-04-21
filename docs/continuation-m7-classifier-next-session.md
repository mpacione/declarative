# Continuation — M7 classifier improvements, next session

**Written**: 2026-04-20 late-night. Session hand-off for the classifier
improvement track.

---

## Where we landed

**Branch**: `v0.3-integration`
**Head commit**: `ba99dd5` fix(classify): self-hidden = UI — dedup-twin + LLM-text
**Live DB**: `Dank-EXP-02.declarative.db` (backup files
`.pre-v2.1-*.bak.db` still present; safe to delete once confident).

### Pipeline state

- Catalog has **62 canonical types** (55 original + 7 from CLAY/
  Ferret-UI-2 audit: `chip`, `carousel`, `pager_indicator`, `chart`,
  `rating`, `video_player`, `grabber`). Plus `not_ui` sentinel +
  `container` / `unsure` specials.
- **Rule v1 consensus** is the default (rule v2's CS-weighted path
  was over-fit; reverted 2026-04-20). **Rule v3** (per-type calibrated
  weights) is implemented but unused until the review corpus
  accumulates \u2014 run `scripts/m7_calibrate_consensus.py` when ready.
- Constrained decoding enabled on LLM + vision tool schemas
  (`build_classify_tool_schema(catalog)` + vision equivalents). The
  model physically cannot emit an out-of-catalog type.
- Rotation-aware spotlight cropping. 5% proportional bbox inflate.
  Scale-4 Figma screenshots in the review UI (scale-2 in classifier
  to save cost; fine).
- **Visibility-aware crop dispatch** (`dd/classify_v2.py::_build_crop`):
  - visible_effective=1 \u2192 screen-level spotlight (existing)
  - self=1, effective=0 (ancestor-hidden) \u2192 per-node Figma render
  - self=0 (self-hidden) \u2192 `None`, caller falls back to dedup-twin /
    LLM-text / unsure (see `scripts/m7_bakeoff_som.py`'s worker).
- **Set-of-Marks (SoM)** path built but NOT yet shipped into
  `run_classification_v2`. Validated via two bake-off rounds:
  - Round 1: 100% SoM-win on 55 head-to-head adjudications (150-159).
  - Round 2: 135 judgments on screens 118/138/174/194/214/234/254/
    274/294/315. 27% of decisions hit the invisibility problem \u2014
    drove the visibility dispatch work.

### Review-tooling state

- `scripts/m7_review_server.py` (port 8765) \u2014 HTML flag-review UI.
  Visibility-aware crops; the Not UI button uses the `not_ui` catalog
  type.
- `scripts/m7_som_adjudicate.py` (port 8766) \u2014 side-by-side SoM vs
  PS adjudicator. Visibility-aware. JSONL output feeds analysis.
- **Important**: `not_ui` is for **non-UI artifacts** (decorative
  scratch frames, design-tool handles). A hidden dialog is still a
  `dialog`, not `not_ui` \u2014 the auto-not_ui fallback for self-hidden
  nodes was wrong and has been retracted.

---

## What's shipped this session

Eight-item plan, all **done**:

1. \u2705 Crop alignment + inflate padding (commit `a000553`, `f9e32c7`)
   \u2014 Figma reports post-rotation AABB top-left + pre-rotation dims,
   compute AABB via `rotated_aabb_dims`; 5% proportional bbox inflate.
2. \u2705 Taxonomy audit (commit `b44ed4c`) \u2014 7 types from CLAY +
   Ferret-UI-2. Catalog 55 \u2192 62.
3. \u2705 Rule v3 per-type calibrated consensus (commit `d78dc20`) \u2014
   `compute_consensus_v3` + `build_calibrated_weights` +
   `scripts/m7_calibrate_consensus.py`. Uniform defaults = rule v1.
4. \u2705 Anthropic constrained decoding (commit `08d1617`) \u2014
   `build_classify_tool_schema(catalog)` pins an enum on
   `canonical_type` across LLM + 2 vision schemas. Nov 2025 GA.
5. \u2705 Set-of-Marks experimental path (commits `80f61f8`, `f6b7939`)
   \u2014 `dd/classify_vision_som.py`: render_som_overlay +
   classify_screen_som + build_som_tool_schema.
6. \u2705 Visibility-aware crop dispatch (commits `a47ec1d`, `dfdcfd7`,
   `ba99dd5`) \u2014 `_get_unclassified_for_llm` tags each candidate
   with `visible_self` + `visible_effective` via recursive CTE.
   `_build_crop` routes by visibility.
7. \u2705 SoM bake-off with visibility dispatch (commit `dfdcfd7`) \u2014
   splits reps into som / hidden_pernode / self_hidden_* paths.
8. \u2705 Self-hidden classification: dedup-twin \u2192 LLM-text \u2192 unsure
   (commit `ba99dd5`). NOT auto-not_ui.

---

## Where to pick up next session

### Fast follow (deferred from this session)

**F1. Figma Plugin render-toggle for self-hidden nodes** (option 1
from the 2026-04-20 hidden-UI discussion). Implement in the existing
plugin extraction path (`dd/extract_screens.py` already uses
PROXY_EXECUTE):

```js
// Pseudo
const originalVisible = node.visible;
node.visible = true;
try {
  const bytes = await node.exportAsync({format: 'PNG', constraint: {type: 'SCALE', value: 2}});
  return bytes;
} finally {
  node.visible = originalVisible;
}
```

Plumb this as a new fetch path in `_build_crop`'s self-hidden branch.
Right answer long-term because dedup-twin + LLM-text is structural-
signal-only; vision is stronger. ~2-3h including plugin changes +
tests.

**F2. Ship SoM as the primary vision path, retire PS** (from 100%
head-to-head win on the first 55 judgments + strong visibility
dispatch on the second run). Refactor `run_classification_v2` to use
SoM instead of PS. Cost profile is similar (~$8 for 204 screens).

The **catch**: SoM can't see self-hidden nodes on the overlay.
Order of work:
- F1 lands first (plugin render-toggle) so self-hidden has a proper
  render path.
- THEN refactor run_classification_v2 to dispatch visible \u2192 SoM,
  ancestor-hidden \u2192 per-crop on per-node render, self-hidden \u2192
  per-crop on plugin-rendered standalone PNG.
- Full-corpus re-run (~$10-15, ~15 min) to verify.
- Measure accuracy vs user reviews on the new run.

**F3. Bake-off #3 on a third screen set** before full corpus run to
confirm visibility-aware + twin+LLM-text doesn't over-fit to 118-
315. Pick e.g. 1-10, 80-89, 220-229 for diversity.

**F4. Hierarchical two-stage classifier** (item 6 from the 8-item
plan) \u2014 pick super-category from 8 buckets first, then leaf type
from 5-10 within. Compounds with #4 constrained decoding and rule v3
weighted consensus. ~1-2 days refactor; expected +3-5 pts accuracy.

**F5. Visual embedding retrieval** (item 7) \u2014 replace name+parent
few-shot with CLIP/DINOv2 embeddings on crops. ~1 day. Only worth
doing after F2+F4 land.

**F6. OmniParser screenshot-path experiment** (item 8) \u2014 the
screenshot pipeline sketched in `docs/plan-screenshot-pipeline.md`.
Side project; doesn't block Figma work.

### Known-good commands for next session

```bash
# Calibrate rule v3 weights once review corpus is big enough:
.venv/bin/python3 -m scripts.m7_calibrate_consensus \
    --db Dank-EXP-02.declarative.db

# Full-corpus re-run (preserves reviews via snapshot/restore):
.venv/bin/python3 -m scripts.m7_run_v2_1 \
    --db Dank-EXP-02.declarative.db --workers 4

# SoM bake-off on a screen set:
.venv/bin/python3 -m scripts.m7_bakeoff_som \
    --screens 1,2,3,4,5 --workers 4

# Review server (flag queue):
.venv/bin/python3 -m scripts.m7_review_server --port 8765

# SoM adjudicator (needs bake-off JSONL first):
.venv/bin/python3 -m scripts.m7_som_adjudicate \
    --port 8766 \
    --results render_batch/m7_bakeoff_som_results.jsonl
```

### Test baseline

- 361 classify tests green
- 433 classify + catalog tests green
- 16 crop tests (incl. AABB dim + Frame 372 regression)
- 42 consensus tests (v1 + v2 + v3 + calibration)
- 23 Gemini-classifier tests (held for follow-on if Gemini revisited)
- 10 SoM tests

Run via: `.venv/bin/python3 -m pytest tests/ -x -q -k "classify or catalog"`

---

## Key learnings (saved as feedback memories)

1. **Pair agreement is NOT accuracy.** SoM\u2194PS at 62.1% didn't tell
   us who was right until we adjudicated \u2014 turned out SoM was right
   100% of the 55 head-to-head cases. Ground truth via human
   adjudication is the only real measure when rule-v2-style
   optimizations can confirm themselves via the same biased sample.
   (See `feedback_pair_agreement_misleading.md`.)

2. **Effective visibility dominates noise.** 55.7% of classifiable
   nodes are effectively invisible (self or ancestor). 35.2% of
   LLM-classified reps sat on hidden subtrees. 27% of human-
   adjudication judgments hit the invisibility problem. Any UI
   classifier on Figma data must handle this at the candidate-
   collection step, not post-hoc. (See
   `feedback_effective_visibility.md`.)

3. **Figma REST render semantics differ from Plugin API.** REST
   renders ancestor-hidden nodes standalone but refuses self-hidden
   (visible=0) nodes. Plugin write-toggle is the path forward for
   self-hidden. (Enhances `feedback_rest_plugin_coord_convention_
   divergence.md`.)

4. **Self-hidden \u2260 not_ui.** Hidden state variants (error dialogs,
   success toasts) are still UI. Auto-classifying them as `not_ui`
   throws away signal. Use dedup-twin + LLM-text-only as fallbacks.
   (See `feedback_self_hidden_still_ui.md`.)

5. **Set-of-Marks beats per-crop vision** on UI with rich sibling
   context. One screen-level call sees everything; per-crop misses
   the siblings that disambiguate `button_group` from `container`,
   `list_item` from `navigation_row`. WACV 2025 documented +7.45 pts
   on Sonnet-class models; we measured ~100% win rate on 55
   adjudication cases + 45/145 clear wins on the broader set. (See
   `feedback_som_vs_percrop.md`.)

6. **Optimizing a metric that can self-confirm is a trap.** The v2
   consensus rule (CS=2x weight) was optimized on the 266-review
   sample where CS was over-represented. On the broader 980-review
   sample it collapsed to 17.4%. Always split training-signal from
   eval-signal before ratcheting a metric. (See
   `feedback_optimize_on_one_set_validate_on_another.md`.)

---

## Decision log

- **Rule v2 (CS=2x) REVERTED** \u2014 over-fit to biased 266-sample.
  Rule v1 is default; rule v3 (calibrated) available but no weights
  yet.
- **auto_not_ui for self-hidden REVERTED** \u2014 hidden UI is still UI.
- **SoM vs per-crop replacement DEFERRED** \u2014 SoM wins in round-1
  adjudication but we need F1 (plugin render-toggle) before SoM can
  handle all cases.
- **Gemini DEFERRED** \u2014 Flash on 56-value enum was flaky
  (python-genai#950); Anthropic constrained decoding (#4) worked.

---

## Untested-but-committed code

Nothing. All commits ran the relevant test suite before push. 361+
classify tests green at session end.

## Outstanding files worth knowing about

- `render_batch/m7_bakeoff_som_validate_v2_report.md` \u2014 most recent
  bake-off with visibility dispatch.
- `render_batch/m7_bakeoff_som_validate_v2_results.jsonl` \u2014 per-rep
  JSONL for adjudication.
- `render_batch/som_adjudication_validate.jsonl` \u2014 135 judgments
  from round 2 (pre-visibility-fix). Useful for delta analysis.
- `render_batch/som_adjudication.jsonl` \u2014 55 judgments from round 1
  (100% SoM-win).
- `docs/plan-screenshot-pipeline.md` \u2014 screenshot-first pipeline
  sketch (option F6 above).

---

## Starter prompt for next session

> Continue the M7 classifier track. Read
> `docs/continuation-m7-classifier-next-session.md` first. Priority
> is F1 (plugin render-toggle for self-hidden nodes) \u2192 F2 (ship SoM
> as primary vision path) \u2192 F3 (third-set bake-off) \u2192 F4
> (hierarchical two-stage). Everything we did this session is
> committed on `v0.3-integration`; head is `ba99dd5`.
