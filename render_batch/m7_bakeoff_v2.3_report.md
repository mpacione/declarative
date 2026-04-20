# Classifier v2 bake-off report

- Screens: [150, 151, 152, 153, 154, 155, 156, 157, 158, 159]
- Wall time: 73.7s

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
| LLM ↔ PS | 61.0% |
| LLM ↔ CS | 56.4% |
| PS ↔ CS | 83.1% |

## Consensus breakdown

- `formal`: 841
- `heuristic`: 542
- `majority`: 85
- `three_way_disagreement`: 8
- `unanimous`: 102
- flagged (unsure/3-way/2-way): 8

## Ground-truth match against user reviews

- User `accept_source` decisions on these screens: 2
- v2 canonical_type matched user's picked source: 2 (100.0%)

## Gate check

- ❌ LLM ↔ PS ≥ 85%: 61.0%
- ✅ User-review match ≥ 70%: 100.0% of 2
