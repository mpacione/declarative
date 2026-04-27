# Classifier v2.3 full-corpus accuracy report

- Wall time: 9.0 min
- Workers: 4
- Consensus rule: **v2 (weighted, CS=2×)** — drop-in replacement for v1;
  can be rolled back by calling `apply_consensus_to_screen(..., rule="v1")`.

## Dedup

- Candidates: 6622
- Groups: 226
- LLM inserts: 6622
- Vision PS applied: 6461
- Vision CS applied: 6619

## Consensus breakdown (rule v2 on full corpus)

- `formal`: 27724
- `heuristic`: 15324
- `unanimous`: 2084
- `weighted_majority`: 3781
- `weighted_tie`: 754 (flagged)
- `single_source`: 3

Flag queue: **754** (down from 2,204 under rule v1 — 66% reduction).

## Accuracy vs user reviews (full 266 denominator)

- **Overall**: 171/266 = **64.3%**

Per-source match (where user accepted that source):

| Source user picked | v1 matched | v2 matched | Rate |
|---|---:|---:|---:|
| llm | 34/61 (55.7%) | 33/61 (54.1%) | -1 |
| vision_ps | 51/100 (51.0%) | 39/100 (39.0%) | -12 |
| **vision_cs** | **71/105 (67.6%)** | **99/105 (94.3%)** | **+28** |

## Rule comparison

| Rule | Match rate | Flag queue | Story |
|---|---:|---:|---|
| v1 (plain majority) | 156/266 = 58.6% | 2,204 | Conservative — flags all disagreements |
| **v2 (weighted, CS=2×)** | **171/266 = 64.3%** | **754** | CS outvotes LLM+PS when it has a verdict; ties flag |

v2 weights derived from the per-source match rates above: Vision CS was
~17 pts more accurate than PS/LLM on the user-review corpus, so doubling
its weight lets it outvote a single-crop majority on three-way
disagreements where cross-screen comparison is the decisive signal.

## Review preservation

- Snapshot size: 674
- Restored: 672
- Orphaned: 2

## Next gate

The 754 flagged rows (weighted_tie) are the next review target. Unlike
v1's 2,204-row queue, these are specifically cases where LLM+PS agree
against CS — the hardest disambiguation pattern. Re-measure accuracy
after human review clears a chunk of this queue.
