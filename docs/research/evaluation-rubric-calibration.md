# Evaluation-rubric calibration memo

**Date:** 2026-04-16
**Author:** Research pass on `dd/visual_inspect.py`
**Decision to inform:** do we invest in evaluation infrastructure (multi-dimension rubric, calibrated threshold, human-labelled reference set) before pushing for 8-10 VLM-ok, or is the current single-pass Gemini-3.1-Pro 1-10 rubric good enough for the next iteration?

---

## 1. Executive summary

Our single-score 1-10 gate blocks categorically-empty output well but measures non-broken progress badly. Literature says: (a) 0-5 beats 0-10 for human-LLM alignment, ICC 0.853 vs 0.805 \[2601.03444]; (b) analytic multi-dim rubrics outperform single-score (UICrit, GameUIAgent); (c) single-VLM reliability is fair (GameUIAgent within-VLM ICC=0.555), cross-VLM near-zero (ICC=0.021). Our data agrees: **17/35 scores bin 1-3, 10/35 bin 7-10, only 8 mid-range** — bimodal in a way a 0-5 scale would compress and a 5-dim rubric would spread. **Recommendation: keep current gate for 1-2 more experiments; in parallel run a ~1-hour DIY human calibration on the 48 existing artefacts and prototype a 5-dim 0-5 rubric on saved PNGs.** Don't add a second VLM — cross-VLM ICC≈0 means cost without signal.

---

## 2. Comparative rubric table

| System | Dimensions | Scale | Aggregation | Accept rule | Critic | Human agreement |
|---|---|---|---|---|---|---|
| **Ours** | 1 — "interpretable UI structure" | 1-10 | single | ok≥7, combined with rule (take pessimistic) | Gemini 3.1 Pro | None |
| **UICrit** | 4 — aesthetics, learnability, efficiency, usability | 1-10 / 1-5 Likert / 1-10 | per-dimension | n/a (dataset) | Gemini Pro Vision | IRR among 7 designers not reported; 55% gain from 8-shot visual+task retrieval vs zero-shot |
| **GameUIAgent** | 5 — Layout, Consistency, Readability, Completeness, Aesthetics | 1-10 | mean | θ=7.5 mean; two lowest dims trigger targeted repair | GPT-4o | within-VLM ICC=0.555; cross-VLM ICC=0.021; human correlation **explicitly unestablished** |
| **ReLook** | 4 — spec adherence, spatial fidelity, typography/color, interactive integrity | 0-100 | single joint call | strict non-regressive: accept only if > best-so-far, up to 10 resamples | Qwen2.5-VL-72B train, Gemini-2.5-Pro offline (decoupled to avoid judge overfitting) | Cohen's κ>0.85, >90% agreement on 200 tasks; Spearman ρ=0.87 vs WebDev Arena |
| **Vis. Prompt. Iter. Refine** | — (critique gen, not scoring) | free-text + bboxes | 6-LLM cascade (gen / refine / validate) | iterative until stable | Gemini-1.5-pro + GPT-4o | +50% gap-to-human closure on UICrit metrics |

**We're missing from ReLook:** decoupled train/offline critic, strict non-regressive accept, reported human-κ.
**We're missing from GameUIAgent:** dimension-wise repair signal. "Layout=2, Completeness=8" on 04-dashboard tells the generator *what* to fix; a single 3/10 doesn't.

---

## 3. Existing-data calibration — 48-row analysis across 00c/d/e/f

### 3.1 Score distribution is bimodal (35 scored rows; 1 timeout)

| Bin | Count | Fraction |
|---|---|---|
| 1-3 (broken) | 17 | 48.6% |
| 4-6 (partial) | 8 | 22.9% |
| 7-10 (ok) | 10 | 28.6% |

Only 23% mid-range — the VLM uses 1-10 as a 2-bucket classifier with a smear. This is exactly the "central-tendency avoidance on wide scales with weak anchor definitions" flagged by \[2601.03444] and Autorubric; both recommend 3-5 level scales with behavioural anchors.

### 3.2 Rule-vs-VLM disagreements (25/36 = 69%)

- **Rule sees nodes, VLM sees renders.** 11 rows rule=partial but VLM=broken (04-dashboard all runs; 05/06/07/11) — "unformatted vertical text dump." Rule counts text; VLM recognises it as stray.
- **VLM catches what rules can't.** 04-dashboard: rule=ok (visible_ratio 0.72-0.81) but VLM=broken(2-3). Rule is blind to list/table decomposition.
- **VLM over-charitable on small schemas.** 01-login: VLM=ok(8) all three post-baseline runs; rule=broken (had_render_errors). 3-8 nodes read as complete.
- **Within-VLM instability.** 09-drawer-nav: VLM=ok(7) in 00e, partial(5) in 00f — **same screen, two calls, two verdicts.** Direct evidence of ≥1-2 points of scoring noise.

### 3.3 Non-monotonic drift on identical prompts across runs

| Prompt | 00c | 00d | 00e | 00f |
|---|---|---|---|---|
| 02-profile | 1 | 5 | 7 | 8 |
| 08-explicit | 2 | 2 | 8 | 8 |
| 09-drawer-nav | 1 | 1 | **7** | **5** |
| 11-vague | 2 | 2 | 3 | **8** |
| 12-round-trip | 2 | 2 | 8 | **1** |

02/08 are real improvements. 12 going 8→1 matches a genuine walk-collapse (0 content nodes in 00f), but 09 (7→5) and 11 (3→8) can't be explained by generator change alone — ≥1-2 points of VLM noise.

### 3.4 Takeaways

1. **Gate works for its built purpose.** Broken-rate 100→92→50→50%; VLM caught three cases (04, 06, 11) rules missed. Keep both.
2. **Near the VLM's scale-resolution floor.** 8/35 mid-range — a 0-5 scale folding 1-3→0, 4-5→1, 6-7→2, 8-9→3, 10→4 gives the same verdicts with narrower bins.
3. **Rule signal is orthogonal, not redundant.** Sees structural properties (sizing, paint) VLM can't. Don't collapse to VLM-only.

---

## 4. Gaps and biases

1. **No actionable-dimension signal.** Single 1-10 can't tell 04-dashboard "layout fine, list/table decomposition missing."
2. **Strict framing causes false-negatives.** The "plausible starting point" bar is the *final*-deliverable quality bar, not what a structural gate should ask.
3. **Known over-strictness in-code.** `dd/visual_inspect.py:L43-47` documents threshold relaxation (0.1, 0.8)→(0.2, 0.7) to match Mode-3 output — target is uncertain.
4. **Single-pass VLM.** No self-consistency, logprob weighting, or position-swap. GameUIAgent's 0.555 ICC says one call is fair-at-best.
5. **No human reference.** Never measured whether ≥7 correlates with "designer would accept." Measure next; don't rebuild first.
6. **Threshold 7 is inherited, not calibrated.** GameUIAgent's 7.5 is a *mean across 5 dimensions*, not comparable to our single 7/10.

---

## 5. Recommendation — hold, calibrate, prototype

**Hold the current gate for one more iteration while running two cheap parallel experiments. Don't upgrade the rubric or add a second VLM yet.**

- Dominant bottleneck is generator quality — still at 50% broken. Hour-on-gate is hour-not-on-generator.
- Gate catches failures we care about; its failure modes are now *understood* (§3).
- Rubric machinery on an uncorrelated-with-human VLM beautifies signal on an uncalibrated base.

### Parallel cheap experiments

1. **DIY human calibration, 48 existing artefacts (~1 hr).** Matt rates each PNG 0-5 on Layout / Completeness / Readability. Spearman ρ vs Gemini scores. ρ>0.7 → adequate single-VLM critic. ρ<0.5 → upgrade urgent.
2. **Shadow 5-dim rubric on saved PNGs (~1 hr).** Prompt change only, reuse runner. Store 5-dim alongside 1-10. Don't gate; observe correlation. If stable+actionable, graduate in next experiment.

## 6. Threshold and scale recalibration

- **Move to 0-5 when the rubric graduates.** Anchors: 0=blank, 1=stray text, 2=some structure, 3=recognisable UI, 4=polished, 5=complete.
- **Keep gate at equivalent-of-7 (≥3/5) until calibration data exists.**
- **Don't adopt 0-100 (ReLook's scale)** — worse for subjective alignment per \[2601.03444].
- **Add anchor paragraphs in the prompt.** Today's one-sentence bands are the #1 cheap fix per literature consensus.

## 7. Pairwise vs absolute

Pairwise is more reliable \[evidentlyai; Aman's] — but **answers a different question**. Gate is a blocking check; can't block on "A beats B" without an anchor. ReLook uses pairwise inside the refinement loop, not as entry gate. **Keep absolute at the gate; add pairwise inside experiment memos** — "00g vs 00f: wins 7 / ties 3 / loses 2 across 12 prompts" is sharper and cheaper than another Δmean-score, and sidesteps VLM-scale drift.

## 8. Cross-VLM check

**Don't as a systematic second gate.** Cross-VLM ICC=0.021 — they measure different things. Exception worth ~$5: one-shot Claude Opus 4.5 on the 20 most-ambiguous screens (09, 11, 04). Heavy disagreement with Gemini → scoring is noise and 5-dim upgrade jumps to must-have.

## 9. Formal calibration exercise — if §5 fails

**Scope:** 100 screens (48 existing + 52 next). **Labelling:** Matt + second rater (Claude as pseudo-IRR proxy — limits claims to "consistent with a reasoning system") on 0-5 × 5 dimensions. ~2 hrs. **Stats:** Spearman ρ per dimension (human vs Gemini); Cohen's κ on broken/partial/ok; within-Gemini ICC over 3 repeated calls on 20 ambiguous cases. **Promote 5-dim 0-5 if:** Spearman ρ(overall) ≥0.7 AND dimensions are decorrelated. **Timeline:** ~1 day, after 00g so the set isn't all pre-Mode-3.

## 10. Open questions

1. Does Gemini systematically prefer "styled-but-wrong" over "unstyled-but-correct"? 04-dashboard says no; 01-login says yes. Human pass disambiguates.
2. Once default-sizing bugs are fixed (default_frame_ratio→0), the rule loses most discriminating power and rubric calibration becomes sharper.
3. Is "plausible starting point" the right gate framing at all? It's a final-deliverable bar; the gate should probably ask "distinguishable from null artefact" — much weaker. Worth rewriting.
4. At what generator-quality point does the gate stop mattering? When broken-rate <20% the gate is noise; bottleneck shifts to differential rating. That's when to switch to pairwise-primary + 5-dim analytic.

---

## Sources

- UICrit (UIST'24) — [arxiv 2407.08850](https://arxiv.org/abs/2407.08850), [HTML v2](https://arxiv.org/html/2407.08850v2)
- GameUIAgent — [arxiv 2603.14724](https://arxiv.org/abs/2603.14724), [HTML](https://arxiv.org/html/2603.14724)
- ReLook — [arxiv 2510.11498](https://arxiv.org/abs/2510.11498), [HTML v1](https://arxiv.org/html/2510.11498v1)
- Visual Prompting with Iterative Refinement — [arxiv 2412.16829](https://arxiv.org/abs/2412.16829)
- Grading-Scale Impact on LLM-as-Judge Alignment (0-5 > 0-10) — [arxiv 2601.03444](https://arxiv.org/html/2601.03444v1)
- Autorubric — [arxiv 2603.00077](https://arxiv.org/html/2603.00077v2)
- A Survey on LLM-as-a-Judge — [arxiv 2411.15594](https://arxiv.org/html/2411.15594v6)
- Evidently AI on pairwise vs pointwise — [evidentlyai.com](https://www.evidentlyai.com/llm-guide/llm-as-a-judge)
- Aman's AI Primer on LLM-as-a-Judge — [aman.ai](https://aman.ai/primers/ai/LLM-as-a-judge/)
- Gemini 3.1 Pro vision / WebDev Arena — [whatllm.org](https://whatllm.org/blog/gemini-3-1-pro-preview)
- Claude Opus 4.5 vs Gemini 3 vision — [vertu.com benchmark comparison](https://vertu.com/ai-tools/gemini-3-pro-vision-vs-claude-opus-4-5-complete-benchmark-comparison-2025/)
