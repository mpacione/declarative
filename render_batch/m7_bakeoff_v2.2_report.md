# Classifier v2 bake-off report

- Screens: [150, 151, 152, 153, 154, 155, 156, 157, 158, 159]
- Wall time: 74.8s

## Dedup

- Candidates collected: 195
- Dedup groups: 29
- Candidates-per-group: 6.72x
- LLM inserts: 195
- Vision PS applied: 195
- Vision CS applied: 195

## Pair agreement

| Pair | Agreement |
|---|---:|
| LLM ↔ PS | 42.6% |
| LLM ↔ CS | 49.7% |
| PS ↔ CS | 81.5% |

## Consensus breakdown

- `formal`: 841
- `heuristic`: 542
- `majority`: 102
- `three_way_disagreement`: 14
- `unanimous`: 79
- flagged (unsure/3-way/2-way): 14

## Ground-truth match against user reviews

- User `accept_source` decisions on these screens: 2
- v2 canonical_type matched user's picked source: 2 (100.0%)

## Gate check

- ❌ LLM ↔ PS ≥ 85%: 42.6%
- ✅ User-review match ≥ 70%: 100.0% of 2
