# Classifier v2.1 full-corpus accuracy report

- Wall time: 9.1 min
- Workers: 4

## Dedup

- Candidates: 6622
- Groups: 226
- LLM inserts: 6622
- Vision PS applied: 6458
- Vision CS applied: 6619

## Consensus breakdown

- `formal`: 27724
- `heuristic`: 15324
- `majority`: 1980
- `single_source`: 3
- `three_way_disagreement`: 2106
- `two_way_disagreement`: 161
- `unanimous`: 2372

## Accuracy vs user reviews

- **Overall**: 693/980 = **70.7%**

Per-source match (where user accepted that source):

| Source user picked | Matched | Total | Rate |
|---|---:|---:|---:|
| llm | 435 | 479 | 90.8% |
| vision_ps | 220 | 274 | 80.3% |
| vision_cs | 38 | 227 | 16.7% |

## Review preservation

- Snapshot size: 1399
- Restored: 1399
- Orphaned: 0
