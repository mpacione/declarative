# Scorer calibration + SoM-based component coverage

**Status:** active; captures decisions + prior-art research driving the
scorer rework.
**Authored:** 2026-04-21 late session (Tier D re-gate + lit review).
**Supersedes context in:** `docs/plan-burndown.md` §Tier C.2 ("scorer
scoped against Tier B's observed failures"). This doc narrows + updates
that scope based on what the re-gate actually surfaced.

## 1. What the re-gate discovered

Running `scripts/m7_tier_d_regate.py` (bridge + screenshot + VLM) on
the canonical 3 Tier-D prompts with `dd/fidelity_score.py` at its
original shape (4 structural dims: coverage / font_readiness /
component_child_consistency / leaf_type_structural + optional VLM):

| Prompt | Struct (old) | Eye / VLM | Reality |
|---|---|---|---|
| subtree (toast) | **10.0 ✓** | 2/10 broken | blank page w/ one `×` icon |
| screen_archetype (login) | 10.0 ✓ | 9/10 ok | coherent Sign In card |
| screen_synthesis (voxel) | 2.0 ✗ | 5-9/10 (varies) | rich but w/ real F2/F3 errors |

**Finding**: the scorer reported `10/10 passed=True` on a visually
empty output. All four structural dims passed trivially (coverage 1/1,
rootedness 1.0, no font errors, no appendChild errors, no
leaf-with-children) on a 2-element tree where the only rendered
content was the close icon.

This is the exact trap `feedback_auto_inspect_before_human_rate.md`
warned about: *"Structural parity is not visual plausibility. Learned
from Wave 1.5 v3: 12/12 'structural success' that was categorically
empty."* The Tier-B inventory (F1-F4) was scoped at **component scale**
where visual defects hide; when Tier D scaled to screen scale the
scorer didn't scale with it.

## 2. Short-term fix landed (commit <TBD>)

Two new rule-based dims in `dd/fidelity_score.py`:

### `canvas_coverage`

Ratio of direct-children's summed bbox area to root's bbox area. A
396×20 toast in a 428×926 screen scores 2.0% — below the 10% pass
threshold. Values clamp: `min(ratio / threshold, 1.0)` so a passing
dim doesn't drag `aggregate_min`.

### `content_richness`

Count of rendered nodes carrying visible content (fills OR strokes
OR characters OR INSTANCE type OR effects > 0) divided by a minimum
threshold (default 3), clamped to 1.0. A 2-node render with nothing
visible fails hard.

**Test posture**: 50/50 `tests/test_fidelity_score.py` green.
**Post-fix re-gate**:
- subtree: 10.0 → **2.0 ✗** (correctly fails)
- login: 10.0 → 10.0 ✓ (unchanged — honest pass)
- voxel: 2.0 → 2.0 ✗ (unchanged — real F2/F3 errors)

## 3. Prior-art lit review — what the literature says about the
rest of the problem

Performed 2026-04-21. Key findings directly relevant to our next
fidelity moves:

### The 1-10 scale is empirically the worst grading scale

**arXiv:2601.03444** (Jan 2026, 6 benchmarks): across LLM-as-judge
setups, **0-5 maximizes human-LLM agreement; 0-10 is consistently
the weakest choice.** Scale-calibration differences dominate over
sampling randomness. Directly explains our observed ±3 Gemini noise
on identical runs (login: 9/10 → 5/10 across two runs; voxel:
5/10 → 9/10).

### Detect-vs-expected is a published pattern with 83% human agreement

**GenEval** (NeurIPS 2023, arXiv:2310.11513) evaluates text-to-image
by detecting expected objects and counting. **83% agreement with
human annotators; interannotator agreement is 88%.** Strongest
conceptual analog to the SoM-coverage idea for UIs.

**Design2Code / WebUIBench / DesignBench** (ACL/NAACL 2025) converges
on the same shape for HTML: **Block-Match** (matched element-area
ratio, penalizing missing + hallucinated blocks) + Text Accuracy +
Position Alignment + CIEDE2000 color + CLIP Similarity. *Five axes,
not one scalar.*

**GEBench** (arXiv:2602.09007, Feb 2026) — closest published cousin:
5-dim VLM-guided metric on 700 GUI generation samples (Goal
Achievement / Interaction Logic / Content Consistency / UI
Plausibility / Visual Quality).

### VLM judges have *bias*, not just noise

**arXiv:2510.08783** (Oct 2025): GPT-4o/Claude/Llama as UI judges show
>75% ±1-point agreement on 7-point scale but *systematic bias* —
"Interesting" underestimated, "Ease of Use" overestimated. Calibration
per-dimension matters; a single scalar hides the bias.

### Vector > scalar; element-wise > holistic

Every serious UI benchmark (GEBench, Design2Code, WebUIBench, UICrit,
Flame-Eval-React) reports a **named tuple** of axes. **arXiv:2509.21227**
shows holistic mean-to-scalar correlates worse with human judgment
than per-axis scores.

### Relevant implementations

| Project | What it does | Useful for us |
|---|---|---|
| **OmniParser** (MSR, arXiv:2408.00203) | YOLO icon detection + captioning + OCR → structured element list | Drop-in alt if SoM proves insufficient; boosts GPT-4V grounding 70.5 → 93.8% |
| **Prometheus-Vision** (ACL 2024) | Open-source judge VLM, 1-5 rubric w/ language feedback | Direct replacement for paid Gemini "rate it" calls |
| **UIClip** (UIST 2024, arXiv:2404.12500) | CLIP-B/32 finetuned on design quality + prompt alignment | Single-scalar sanity dim complementing SoM coverage |
| **VQAScore** (CMU 2024) | P("Yes" | "Does this figure show X?") | Per-component Yes/No probe; beats CLIPScore / ImageReward |
| **UICrit dataset** (UIST 2024) | 3,059 expert critiques, 983 RICO UIs w/ bboxes | Few-shot corpus if we build a learned critic |
| **screenshot-to-code evals** (abi/screenshot-to-code) | Human-rating UI + Python runner over 16 screens | Template for our paired-VLM eval harness |

**Key novelty gap**: SoM-weighted canonical-type-coverage for
design-tool-targeted generation is unpublished. GenEval (natural
images), Design2Code (HTML blocks), OmniParser (agent grounding)
all sit adjacent. Our ~54-type constrained enum over Figma render
output would be a defensible contribution.

## 4. Decisions taken

### D1. Drop 1-10 scale in favor of structured / 0-5 output

Grounded in arXiv:2601.03444. Any remaining VLM-rating dim emits
0-5 with anchored examples + 0-1 normalization for internal use.
Don't retain the 1-10 VLM dim past this change-set unless a
specific caller still needs it.

### D2. Build SoM-component-coverage as the primary semantic fidelity signal

Reuse `dd/classify_vision_som.py` (422 LOC, already shipped in the
M7 classifier-v2 work). Flow:

1. Walk the rendered tree, capture per-eid absolute bboxes (relative
   to the screenshot's origin).
2. Render SoM overlay on the screenshot.
3. Call `classify_screen_som(screen_png, annotations, client,
   catalog, ...)` → `[{mark_id, canonical_type, confidence, reason}]`.
4. Map `mark_id` → IR eid → IR's declared canonical type.
5. Compute precision + recall as **two independent dims** (no mean):
   - `component_precision` = detected types that match expected /
     total detected
   - `component_recall` = detected types that match expected /
     total expected

Pass gate: ≥0.8 on both (matching GenEval / Design2Code practice).

### D3. Walk payload extended to include absolute bboxes

`render_test/walk_ref.js` and `render_test/batch_screenshot.js` both
extended to emit `{x, y, width, height, rotation}` per eid, relative
to the rendered-root's top-left. Additive change; consumers that
only read `width`/`height` unaffected.

Round-trip 204/204 parity must stay green after this change. Verified
via `render_batch/sweep.py` against the Dank Experimental corpus.

### D4. Report as vector, not scalar

Matches every serious UI benchmark (GEBench, Design2Code, UICrit).
`FidelityReport` already has this shape (list of `DimensionScore`);
preserve it. Never average to one number before emitting.

### D5. Measurement before promotion — **executed 2026-04-21**

Ran `scripts/m7_tier_d_variance.py` (3 runs × 3 prompts). Stdev
across runs:

| prompt | struct stdev | SoM-P stdev | SoM-R stdev | **VLM stdev** |
|---|---|---|---|---|
| subtree | 0.00 | 0.00 | 0.00 | **0.58** |
| archetype | 1.07 | 0.11 | 0.11 | **2.08** |
| synthesis | 1.13 | 0.24 | 0.24 | **2.89** |

**VLM is 2-25x noisier than SoM on every prompt.** The lit finding
(arXiv:2601.03444) holds for us; 0-10 VLM ratings are a category
worse than enum-constrained classification. On archetype the VLM
ranged 5-9/10 across identical inputs; SoM-P ranged 0.43-0.62.

**Decision confirmed**: D2 (promote SoM as primary semantic-fidelity
signal) and the implicit follow-through: the 1-10 Gemini rating is
now an opt-in diagnostic comparator in `m7_tier_d_regate`, not a
pass-gate signal. The gate aggregates over structural + SoM dims
only. Kept accessible via `--no-som` / `--no-vlm` flags for
measurement parity.

Full artefacts: `tmp/tier_d_variance/variance_report.md` +
`tmp/tier_d_variance/variance.json`.

### D6. `is_parity` stays as the hard front-door gate

Grounded in ReLook's "zero-reward-for-invalid-render" rule
(arXiv:2510.11498) + `feedback_verifier_blind_to_visual_loss.md`.
Broken render → no fidelity number emitted; scorer returns early.

## 5. Not-doing list

Explicit rejections from the lit review + our own review:

- **Second VLM critic** (cross-family): γ research cited cross-VLM
  ICC=0.021 → near-zero signal at 3× cost. Not doing.
- **0-100 scale**: arXiv:2601.03444 → 0-100 worse than 0-10 worse
  than 0-5. Not doing.
- **Replace SoM with OmniParser**: only if SoM disagreement with
  eye-check exceeds 30%; not on the critical path yet.
- **Learned critic (UIClip-style finetune)**: deferred until we have
  >200 human-rated fidelity samples to train against.
- **Prompt-intent → expected-component-bag via a second LLM call**:
  for now, use the IR's declared types as the expected set. The LLM
  step that built the IR already committed to what's expected.

## 6. Build plan (what ships next)

In order of dependency:

1. **Extend `walk_ref.js` + `batch_screenshot.js`** to emit absolute
   bboxes per eid (relative to rendered-root). Smoke test against a
   fresh 204/204 sweep.
2. **TDD the `score_component_coverage` dim** against a hand-crafted
   fixture (IR with 4 expected types, synthetic SoM response with 3
   matches + 1 miss → precision=1.0, recall=0.75).
3. **Build `score_component_coverage(ir_elements, walk_eid_map,
   screenshot_png, catalog, client)`** that wraps
   `classify_screen_som`. Two dims emitted, not one.
4. **Wire into `score_fidelity`** behind an opt-in kwarg
   (`component_coverage_args`) so offline callers can run without
   spending Claude tokens.
5. **Update `scripts/m7_tier_d_regate.py`** to invoke SoM coverage
   when a Claude client is available, alongside the existing Gemini
   1-10 dim (kept for measurement comparison). **✅ shipped
   `803c3e3`.**
6. **Run measurement**: N=3 runs × 3 prompts, report variance for
   both SoM coverage and Gemini rating. **✅ done; results in §D5
   above.** VLM 2-25x noisier than SoM on every prompt.
7. **Decision on D5**: if SoM wins, retire the 1-10 dim. **✅ SoM
   promoted; 1-10 Gemini dim demoted to opt-in comparator.**

## 6.1 What's next (not shipping this session)

Three natural successor units surfaced during the work:

- ~~**Fix Mode-3 text_input hydration.**~~ **✅ SHIPPED 2026-04-21.**
  SoM surfaced the bug: text_input's `label` slot declared
  `position="top"` (external sibling), but
  `_mode3_synthesise_children` lumped it as an internal child. Plus
  a latent aliasing bug (`placeholder` prop was hijacking the
  `label` slot via alias fallback). Fix in `dd/compose.py`:
  `_mode3_synthesise_children` now returns `dict[position, list[eid]]`,
  `_build_element` wraps in an outer frame when external positions
  have children, `_ALIAS_POSITION_WHITELIST` constrains positional
  aliases. 5 new TDD tests; re-gate on same archetype prompt: SoM-P
  0.43→0.71 (+65% rel), SoM-R 0.30→0.50 (+67% rel), struct 3.0→5.0.
  Visually: label now sits above the input box as intended.
- **Prompt-intent coverage** (this doc §G3, unpublished territory).
  Extract expected components from the PROMPT via a separate LLM
  pass, then SoM-score against prompt-intent (not IR). Would
  formalize intent-fulfillment as a retrieval F1 — currently no
  paper does this end-to-end.
- **Broader SoM application**: the scorer works at screen scale;
  wiring it into the repair loop (Tier E.1) would give the
  verifier-as-agent dim-specific diagnostic hints ("missing
  expected text_input" → repair agent tries re-hydration).

## 7. Cross-references

- `docs/plan-burndown.md` §Tier C.2 (original scope — narrowed by
  this doc)
- `docs/learnings-tier-b-failure-modes.md` (F1-F4 inventory —
  still valid, just insufficient at screen scale)
- `feedback_auto_inspect_before_human_rate.md` (the general
  principle this fix enforces)
- `feedback_som_vs_percrop.md` (SoM > per-crop; validated
  2026-04-21)
- `feedback_som_weight_2.md` (SoM at weight 2 → 60.9% Final↔SoM
  agreement)
- `feedback_verifier_blind_to_visual_loss.md` (the general class
  of problem; this doc is one concrete instance)
- `feedback_vlm_transient_retries.md` (Gemini 30% transient error
  rate; partially explains but doesn't fully cover ±3 variance)

## 8. Sources (lit review, 2026-04-21)

- [Grading Scale Impact on LLM-as-a-Judge (arXiv:2601.03444)](https://arxiv.org/abs/2601.03444)
- [GEBench (arXiv:2602.09007)](https://arxiv.org/abs/2602.09007)
- [WebRenderBench / ALISA (arXiv:2510.04097)](https://arxiv.org/abs/2510.04097)
- [MLLM as a UI Judge (arXiv:2510.08783)](https://arxiv.org/abs/2510.08783)
- [GenEval (NeurIPS 2023)](https://github.com/djghosh13/geneval)
- [Design2Code](https://github.com/NoviScl/Design2Code)
- [DesignBench (arXiv:2506.06251)](https://arxiv.org/abs/2506.06251)
- [WebUIBench (arXiv:2506.07818)](https://arxiv.org/abs/2506.07818)
- [UIClip (arXiv:2404.12500)](https://arxiv.org/html/2404.12500v1)
- [UICrit dataset](https://github.com/google-research-datasets/uicrit)
- [OmniParser (MSR)](https://github.com/microsoft/OmniParser)
- [Prometheus-Vision](https://github.com/prometheus-eval/prometheus-vision)
- [VQAScore / GenAI-Bench](https://linzhiqiu.github.io/papers/vqascore/)
- [ReLook (arXiv:2510.11498)](https://arxiv.org/abs/2510.11498)
- [Set-of-Mark (arXiv:2310.11441)](https://arxiv.org/abs/2310.11441)
- [Evaluating the Evaluators (arXiv:2509.21227)](https://arxiv.org/abs/2509.21227)
- [screenshot-to-code Evaluation.md](https://github.com/abi/screenshot-to-code/blob/main/Evaluation.md)
