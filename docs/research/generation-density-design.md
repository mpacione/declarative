# Generation-Density Experiment Design

**Status:** design memo, not yet executed.
**Author:** synthesis from 00c/00d/00e/00f artefacts (2026-04-16).
**Decision it informs:** is the next bottleneck sampling/temperature or prompt-contract — and which single intervention most plausibly gets us to 8–10 VLM-ok on the 12 canonical prompts?

---

## 1. Executive summary

Re-reading the four existing runs shows the "sparsity / variance / no-nesting" narrative is only partly right. Outputs are largely structurally fine when the prompt is specific — 04-dashboard, 05-paywall, 03-meme-feed all emit cards / lists / button_groups with depth 2–3 in 00d/e/f. The real failures are (a) **contract non-determinism on under-specified prompts** (12-round-trip-test emits 7 / 6 / 6 / 0 components across runs, with 00f producing an *English clarification request* rather than JSON); (b) **row-shape drift on tables** within the same model/prompt; (c) **render-template misses dominate warnings** regardless of generation quality. I recommend a **3×5×12 matrix + 60-sample variance slice (240 Haiku calls, ~$0.70, ~8 min sequential / ~2 min parallel)** that varies temperature × system-prompt contract, captures structural metrics only, and reserves VLM for a 60-call confirmation pass on the winning cell. My prior: the dominant lever is the prompt contract (plan-first + minimum-count-per-archetype + explicit "`[]` when under-specified"), not temperature.

---

## 2. Observed patterns across 00c–00f

### 2.1 Component counts per prompt per run (total nodes incl. nested / max depth)

| prompt                  | 00c     | 00d   | 00e   | 00f   | std-dev (total) |
|-------------------------|---------|-------|-------|-------|-----------------|
| 01-login                | 7/1     | 13/1  | 9/1   | 10/1  | 2.2             |
| 02-profile-settings     | 13/1    | 14/1  | 14/1  | 14/1  | 0.4             |
| 03-meme-feed            | 26/2    | 17/3  | 23/3  | 18/3  | 3.7             |
| 04-dashboard            | 13/2    | 24/2  | 32/3  | 33/3  | 8.2             |
| 05-paywall              | 38/2    | 41/3  | 48/3  | 48/3  | 4.4             |
| 06-spa-minimal          | 23/2    | 19/3  | 20/3  | 23/3  | 1.9             |
| 07-search               | 17/2    | 28/3  | 29/3  | 28/3  | 4.9             |
| 08-explicit-structure   | 8/1     | 11/1  | 11/1  | 11/1  | 1.3             |
| 09-drawer-nav           | 8/1     | 7/1   | 22/3  | 22/3  | 7.3             |
| 10-onboarding-carousel  | 14/1    | 19/1  | 21/1  | 21/1  | 2.9             |
| 11-vague                | 24/2    | 37/2  | 24/3  | 33/3  | 5.6             |
| 12-round-trip-test      | 26/2    | 24/3  | 29/1  | **0/0** | 11.8          |

### 2.2 What the numbers actually say

- **Density isn't uniformly low.** 7/12 prompts emit ≥ 20 nodes with depth ≥ 2 in at least 3 of 4 runs. 05-paywall hit 48 twice. The "sparsity" story applies to 01/02/08/09/10, which are either small screens or under-specified.
- **Nesting does happen** when the prompt implies repetition: 03-meme-feed wraps cards inside a `list` in 00d/e/f (depth 3). Container hints are firing for `list` / `button_group` / `header`, but *inconsistently* for `table`.
- **12 is the anomaly.** Four semantically different screens from the same 20-char prompt (MacBook spec / iOS Messages / iPhone spec / refusal). That is **contract under-specification**, not temperature.
- **Row-shape drift.** 04-dashboard yields: flat-string list_items (00c), 15-cell grid (00d), 4 header texts + 4 list_item rows w/ badges (00e/f). Same prompt, same model. Current contract says `table (children = column headers + row cells)` — "row cell" is ambiguous.
- **Warnings are render-layer.** 33/33 warnings on 04-dashboard are `Type 'X' has no template`. No LLM-side tuning fixes that.

All 48 observed responses parsed cleanly when non-empty; no mid-array truncation. Max observed output was 743 tokens on `max_tokens=2048`. **max_tokens is not the bottleneck.**

---

## 3. Experimental design

### 3.1 Dimensions

Only two vary; everything else held constant (model = Haiku 4.5, max_tokens = 2048, enriched system prompt incl. archetype + CKR vocab).

**D1 — Temperature (3 levels):** `0.0, 0.5, 1.0`. Dropped 0.3/0.7 mid-points — we need signal, not a gradient.

**D2 — System-prompt contract (5 variants):**

- **S0 current:** today's SYSTEM_PROMPT.
- **S1 plan-first:** prepend "First, write a one-line plan inside `<plan>…</plan>` listing top-level regions. Then emit the JSON array." Parser already strips non-JSON.
- **S2 min-count + clarify-as-empty:** add "If the prompt implies a list/feed/table/carousel/specs screen, emit at least 4 child items. If the prompt is under-specified (missing a referenced image/screen ID), emit `[]` — do NOT invent a different screen."
- **S3 few-shot rich:** S0 + 3 worked examples (dashboard with chart + table, meme-feed list-of-cards, onboarding-carousel) drawn from the best 00e/f outputs.
- **S4 minimal:** catalog types only, no container hints, no CKR. Control — measures what the current contract is actually buying.

3 × 5 = 15 cells × 12 prompts × 1 sample = **180 calls**. Plus a **variance slice** (T=1.0, S0, 12 prompts × 5 samples = 60 calls) to quantify current-production non-determinism. Total: **240 Haiku calls**.

### 3.2 Dependent measures (per sample, structural only)

1. Total node count (tree).
2. Top-level count.
3. Max depth.
4. **Container-emission score:** for each of `list, button_group, pagination, toggle_group, header, table`, did we emit with non-empty `children`? Sum (0–6).
5. `component_key` rate (nodes with key / total).
6. `variant` declaration rate.
7. JSON-validity (0/1). Capture raw length + detect English-explanation-instead-of-JSON.
8. Empty-output rate (`[]`).

**VLM is deferred** — every output renders as mostly-empty frames due to template gap, so VLM is currently a noisy instrument for the generation question. Run VLM only on the winning cell afterward (60 calls).

### 3.3 Variance slice

T=1.0, S0, 12 prompts × 5 samples = 60 calls. Measure: within-cell std-dev of total count per prompt, and Jaccard similarity of component-type bags across the 5 samples. Quantifies what we currently only have anecdotally.

---

## 4. Cost + wall-clock

Measured from 00f: enriched system prompt ~1,535 tokens, user prompt ~17 tokens, output avg 403 / max 743 tokens. Haiku 4.5 = **$1/MTok input, $5/MTok output**; 5-min prompt cache read = $0.10/MTok (system prompt amortises across a run). Gemini 3.1 Pro Preview VLM = **$2/MTok in, $12/MTok out** → ~$0.016/call.

- Per Haiku call uncached: **$0.00357**. Cache-hit: **$0.00219**.

| Matrix | Haiku calls | Haiku $ | VLM calls | VLM $ | Total $ | Wall-clock (seq) |
|---|---|---|---|---|---|---|
| Minimal (T=0/1 × S0/S2 × 12 × 2) | 96 | $0.34 | 0 | $0 | $0.34 | ~3 min |
| **Recommended** (3T×5S×12×1 + 60-sample variance slice) | 240 | $0.70 | 60 (on winner) | $0.96 | **$1.66** | ~8 min Haiku + ~8 min VLM = **~16 min** |
| Maximal (3×5×12×3 + VLM on all) | 540 | $1.80 | 540 | $8.64 | $10.44 | ~90 min |

All three fit ≤$20 / ≤1 hour. With 10-way parallelism the recommended matrix finishes Haiku in ~2 min, VLM in ~1 min.

---

## 5. Hypotheses

- **H1 — Temperature is not the dominant lever.** Within-cell std-dev will drop 1.0→0.0, but between-contract variance will exceed between-temperature variance. Falsified if S0 @ T=0.0 alone hits ≥ 4 of 5 structural measures' targets on 12/12 prompts.
- **H2 — Plan-first (S1) raises depth but not total count.** S1 increases max-depth on 03/04/07 by ≥ 1 level, top-level count flat. Falsified if depth deltas < 0.5.
- **H3 — Min-count-plus-clarify (S2) fixes 12-round-trip-test class.** Empty-output rate on 12 drops to 0 via explicit `[]` return; list-item counts rise on feed/table prompts. Falsified if S2 still yields semantic hallucination on 12.
- **H4 — max_tokens not the bottleneck.** Already confirmed in §2; restated for completeness. Zero truncation expected.
- **H5 — Few-shot (S3) beats others on density but at higher variance on prompts unlike the examples.** Falsified if S3 totals statistically indistinguishable from S0 on prompts dissimilar to the examples.

---

## 6. Analysis plan

For each cell: mean + std-dev of each structural measure. Visualise as a 3×5 heatmap per measure. One-way ANOVA across 5 contract variants at each temperature; Cohen's d for effect size (n=12 per cell is low-power, so effect size is the load-bearing stat, not p). Variance slice: ranked-dot plot of per-prompt within-cell std-dev. After picking a winner, run VLM on its 60 samples and compute Pearson correlation between structural-density-score and VLM-ok — tells us whether density predicts visual quality or if the two are decoupled by the render-template gap.

---

## 7. Stopping / interpretation rubric

- **Clear winner:** a contract variant scores ≥ 1 std-dev above S0 on ≥ 3 of 5 measures, with empty-output-rate ≤ S0, on ≥ 9 of 12 prompts. Ship.
- **No clear winner:** drop to T=0.3 globally (cheap), keep SYSTEM unchanged, move on to render-template gap (the real blocker).
- **Temperature dominates:** pin T=0.3, keep SYSTEM, move on.
- **Pathological:** S2 still yields hallucination on 12 — move under-specification detection outside the LLM (rule-based pre-check).

---

## 8. Adjacent one-off diagnostic (done)

Examined `llm_raw_response.txt` for 12-round-trip-test across all four runs:

- 00c: 2,781 chars, 7 components, iPhone spec-page hallucination.
- 00d: 1,822 chars, 6 components — **iOS Messages screen**, not a spec page.
- 00e: 2,044 chars, 7 components, different spec page (Face ID / 5G toggles).
- 00f: **388 chars, prose refusal.** "I don't have a reference image or description of 'iPhone 13 Pro Max - 109'…" `extract_json` returned `[]`.

**The 00f behaviour is categorically better than 00d's silent hallucination** — the model detected under-specification and asked for clarification. Our pipeline treated that as failure. This is a **pipeline-contract bug**, not a generation regression. Recommended side-fix (independent of this experiment): when `extract_json` returns `[]` and the response has > 100 chars of non-JSON prose, surface it as `clarification_refusal` in `notes.md` and skip rendering rather than emit a blank frame.

No output across 48 observed responses was truncated. max_tokens is not the bottleneck. The "variance" story is a **contract-under-specification** story.

---

## 9. Recommendation

Run the **Recommended matrix (240 Haiku calls + 60-sample VLM confirmation on winner, $1.66, ~16 min sequential / ~5 min parallel).** It separates temperature from contract with 3×5 cells, pins down current production variance with the fixed-cell slice, and confirms the winner survives VLM without paying $8.64 per cell.

My prior, given the diagnostic: the winner will be **S2 at T≈0.3** — a ~30-line change to SYSTEM_PROMPT + setting `temperature=0.3` in `parse_prompt`. Parlay bet: H1 (temperature non-dominant) and H3 (S2 fixes 12) both land. If either fails, the result is equally valuable — it tells us the next engineering dollar should go to the render-template gap, not prompt engineering.
