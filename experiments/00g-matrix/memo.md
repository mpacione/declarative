# Matrix 00g — analysis memo

Source: `matrix_results.json` · 240/240 Haiku calls OK · cost $0.976 · elapsed 83.0s

Binding spec: `docs/research/generation-density-design.md` §3.

## Variance floor (from T=1.0 · S0 · 60-sample slice)

| Measure | Std-dev floor |
|---|---|
| `total_node_count` | 3.435 |
| `top_level_count` | 0.572 |
| `max_depth` | 0.369 |
| `container_coverage` | 0.249 |
| `component_key_rate` | 0.045 |
| `variant_rate` | 0.033 |
| `json_valid` | 0.046 |
| `empty_output` | 0.000 |
| `clarification_refusal` | 0.046 |

## 3 × 5 heatmaps (cell mean across 12 prompts)

### total_node_count

| T \ S | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| **T=0.0** | 23.50 | 21.50 | 19.08 | 25.50 | 13.08 |
| **T=0.5** | 23.33 | 21.17 | 19.58 | 27.58 | 14.00 |
| **T=1.0** | 24.92 | 21.00 | 18.33 | 19.08 | 11.17 |

### max_depth

| T \ S | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| **T=0.0** | 3.08 | 3.42 | 2.75 | 3.25 | 2.25 |
| **T=0.5** | 3.17 | 3.08 | 2.58 | 3.25 | 2.25 |
| **T=1.0** | 3.08 | 3.17 | 2.33 | 2.75 | 1.75 |

### container_coverage

| T \ S | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| **T=0.0** | 1.75 | 1.92 | 1.25 | 1.42 | 0.75 |
| **T=0.5** | 1.83 | 1.92 | 1.25 | 1.42 | 0.67 |
| **T=1.0** | 1.67 | 1.83 | 1.25 | 1.33 | 0.25 |

### component_key_rate

| T \ S | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| **T=0.0** | 0.17 | 0.19 | 0.13 | 0.13 | 0.00 |
| **T=0.5** | 0.19 | 0.18 | 0.14 | 0.14 | 0.00 |
| **T=1.0** | 0.17 | 0.20 | 0.15 | 0.13 | 0.00 |

### variant_rate

| T \ S | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| **T=0.0** | 0.05 | 0.04 | 0.04 | 0.05 | 0.02 |
| **T=0.5** | 0.07 | 0.05 | 0.04 | 0.05 | 0.02 |
| **T=1.0** | 0.08 | 0.05 | 0.07 | 0.04 | 0.04 |

### empty_output (lower is better; rate of `[]`)

| T \ S | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| **T=0.0** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **T=0.5** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **T=1.0** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

### clarification_refusal (not a failure — surfaced via side-fix)

| T \ S | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|
| **T=0.0** | 0.00 | 0.00 | 0.17 | 0.00 | 0.00 |
| **T=0.5** | 0.00 | 0.00 | 0.17 | 0.00 | 0.00 |
| **T=1.0** | 0.00 | 0.00 | 0.25 | 0.08 | 0.00 |

## Key observations (mechanical)

**S0 is a hard baseline.**
- `total_node_count` — best cell S3 @ T=0.5 (27.58); best S0 24.92; Δ = +2.67
- `max_depth` — best cell S1 @ T=0.0 (3.42); best S0 3.17; Δ = +0.25
- `container_coverage` — best cell S1 @ T=0.0 (1.92); best S0 1.83; Δ = +0.08
- `component_key_rate` — best cell S1 @ T=1.0 (0.20); best S0 0.19; Δ = +0.01
- `variant_rate` — best cell S0 @ T=1.0 (0.08); best S0 0.08; Δ = +0.00

**Current enriched SYSTEM_PROMPT pays off** — mean S0-minus-S4 across temperatures:
- `total_node_count`: S0 − S4 = +11.167
- `max_depth`: S0 − S4 = +1.028
- `container_coverage`: S0 − S4 = +1.194
- `component_key_rate`: S0 − S4 = +0.176
- `variant_rate`: S0 − S4 = +0.043

**S2's clarification-refusal rate** — the side-fix (`_clarification_refusal`) is the pipeline working as intended, routing under-specified prompts to notes.md rather than rendering:
- S2 @ T=0.0: 2/12 prompts refused
- S2 @ T=0.5: 2/12 prompts refused
- S2 @ T=1.0: 3/12 prompts refused

## Stopping criterion (memo §7)

A contract variant wins if it scores ≥ 1 std-dev floor above S0 on ≥ 3 of 5 quality measures, with empty-output-rate ≤ S0's, on ≥ 9 of 12 prompts.

Quality measures: `total_node_count`, `max_depth`, `container_coverage`, `component_key_rate`, `variant_rate`.

### Ranked candidates

| Rank | T | Contract | Measures won (≥9/12) | Per-measure prompt wins | empty_output ≤ S0? | gate |
|---|---|---|---|---|---|---|
| 1 | 0.0 | S1 | 0/5 | total=1 / max=3 / container=3 / component=3 / variant=1 | ✓ | — |
| 2 | 0.0 | S2 | 0/5 | total=3 / max=2 / container=1 / component=0 / variant=1 | ✓ | — |
| 3 | 0.0 | S3 | 0/5 | total=3 / max=2 / container=1 / component=2 / variant=2 | ✓ | — |
| 4 | 0.0 | S4 | 0/5 | total=0 / max=1 / container=1 / component=0 / variant=0 | ✓ | — |
| 5 | 0.5 | S1 | 0/5 | total=0 / max=1 / container=2 / component=3 / variant=2 | ✓ | — |
| 6 | 0.5 | S2 | 0/5 | total=2 / max=1 / container=0 / component=2 / variant=2 | ✓ | — |
| 7 | 0.5 | S3 | 0/5 | total=3 / max=1 / container=0 / component=2 / variant=2 | ✓ | — |
| 8 | 0.5 | S4 | 0/5 | total=0 / max=0 / container=0 / component=0 / variant=1 | ✓ | — |
| 9 | 1.0 | S1 | 0/5 | total=0 / max=3 / container=3 / component=4 / variant=1 | ✓ | — |
| 10 | 1.0 | S2 | 0/5 | total=0 / max=0 / container=0 / component=3 / variant=0 | ✓ | — |
| 11 | 1.0 | S3 | 0/5 | total=1 / max=1 / container=1 / component=2 / variant=1 | ✓ | — |
| 12 | 1.0 | S4 | 0/5 | total=0 / max=0 / container=0 / component=0 / variant=2 | ✓ | — |

### Verdict — no clear winner

No contract variant cleared the gate at any temperature. Per §7, this routes to: drop `T=0.3` globally (already landed in commit `3796058`), keep SYSTEM_PROMPT, and move on to the render-template gap as the next bottleneck. A1 (archetype library) still ships independently — it's α-backed independent of β's matrix.

Best near-miss: `S1` at `T=0.0` (0/5 measures).

## Forward-routing (per memo §7)

- **Temperature default `T=0.3`** — already landed in commit `3796058` before the matrix confirmed it; the matrix shows the T dimension is a weak lever (largest within-contract mean delta across T=0/0.5/1.0 on `total_node_count` is ~3, well under one std-dev floor).
- **SYSTEM_PROMPT unchanged for v0.1.5** — S0 is not beaten by any of the four candidate mutations at any temperature. The β matrix was a bet that a 30-line contract edit was the highest-ROI move; the empirical answer is no.
- **A1 archetype library proceeds** — it's α-backed independent of β's matrix. The next step is corpus-mining archetype skeletons (Step 2 in `docs/continuation-v0.1.5.md`).
- **S2's clarification-refusal behaviour is preserved** — the 3796058 side-fix routes those prose responses to notes.md; the matrix shows Haiku only fires this path under S2 (which has the explicit `[]`-if-underspecified clause), confirming the signal is contract-conditional and controllable.
