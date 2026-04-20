# Gemini 2.5 Flash vision bake-off report (v2)

- Screens: [150, 151, 152, 153, 154, 155, 156, 157, 158, 159]
- Reps after skeleton-filter: 171 (skipped 24 skeleton reps)
- Gemini classifications returned: 171
- Anthropic wall time: 0.0s
- Gemini wall time: 297.0s

## Pair agreement (Gemini ↔ Anthropic, single-crop fair)

| Pair | Agreement | Sample |
|---|---:|---:|
| Gemini ↔ LLM (text) | 45.6% | 171 |
| Gemini ↔ Vision PS | 35.7% | 171 |

## Ground-truth match against user reviews

- User `accept_source` decisions on these screens: 2
- Gemini canonical_type matched user's picked source: 0 (0.0%)

## Gemini confidence distribution

- 0.95+: 118
- 0.85-0.94: 48
- 0.75-0.84: 5
- <0.75: 0

## `new_type` proposals (catalog gap signal)

| Proposed label | Count |
|---|---:|
| `artboard` | 1 |
| `drag_handle` | 1 |
| `header_section` | 1 |

### Example nodes

- `158:12026` — artboard → artboard
- `158:12129` — Left → header_section
- `158:12254` — grabber → drag_handle

## Gemini ↔ Anthropic PS disagreements

Count: 110 / 171 (64.3% of reps)

| Node | Name | Gemini | Anthropic PS |
|---|---|---|---|
| 150:10043 | artboard | image | container |
| 150:10098 | Left | header | container |
| 150:10249 | Left | text | container |
| 150:10053 | Frame 350 | image | container |
| 150:10130 | Center | select | container |
| 150:10227 | title and controls | header | container |
| 150:10252 | Right | text | container |
| 150:10131 | Titles | skeleton | heading |
| 150:10143 | wordmark | select | image |
| 151:10368 | Left | tabs | container |
| 151:10514 | Left | text | container |
| 151:10400 | Center | button | container |
| 151:10492 | title and controls | header | container |
| 151:10517 | Right | text | container |
| 151:10444 | Right | icon | button_group |
| 151:10401 | Titles | progress | heading |
| 151:10413 | wordmark | button | image |
| 151:10272 | Frame 266 | skeleton | list_item |
| 151:10280 | Frame 267 | skeleton | list_item |
| 151:10286 | Frame 268 | skeleton | button |
| 152:10626 | Left | tabs | container |
| 152:10746 | grabber | control_point | icon |
| 152:10772 | Left | text | container |
| 152:10658 | Center | button | container |
| 152:10750 | title and controls | header | container |
| 152:10775 | Right | text | container |
| 152:10702 | Right | card | button_group |
| 152:10659 | Titles | badge | heading |
| 152:10610 | Frame 267 | card | list_item |
| 152:10604 | Frame 268 | card | button |
| 153:10785 | artboard | image | container |
| 153:10862 | Left | header | container |
| 153:11013 | Left | text | container |
| 153:10795 | Frame 350 | image | container |
| 153:10894 | Center | select | container |
| 153:10991 | title and controls | header | container |
| 153:11016 | Right | text | container |
| 153:10895 | Titles | text | heading |
| 154:11026 | artboard | image | container |
| 154:11081 | Left | header | container |
| ... | (70 more) | | |

## Decision gate

Add Gemini as a 4th source if at least one holds:
- Gemini ↔ user-review match rate ≥ Anthropic-PS match rate
- Gemini ↔ PS disagreement stays ≥15% AND `new_type` proposals surface real catalog gaps
