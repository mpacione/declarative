# Classifier v2.1 full-corpus accuracy report

- Wall time: 20.2 min
- Workers: 4

## Dedup

- Candidates: 6622
- Groups: 239
- LLM inserts: 6622
- Vision PS applied: 6516
- Vision CS applied: 6622

## Consensus breakdown

- `any_unsure`: 10
- `formal`: 27724
- `heuristic`: 15324
- `majority`: 3069
- `three_way_disagreement`: 1101
- `two_way_disagreement`: 106
- `unanimous`: 2336

## Accuracy vs user reviews

- **Overall**: 996/1681 = **59.3%**

Per-source match (where user accepted that source):

| Source user picked | Matched | Total | Rate |
|---|---:|---:|---:|
| llm | 215 | 479 | 44.9% |
| vision_ps | 557 | 605 | 92.1% |
| vision_cs | 224 | 597 | 37.5% |

## Review preservation

- Snapshot size: 2845
- Restored: 2845
- Orphaned: 0
