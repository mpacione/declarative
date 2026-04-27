# Gemini 2.5 Flash vision bake-off report (v2)

- Screens: [150, 151, 152, 153, 154, 155, 156, 157, 158, 159]
- Reps after skeleton-filter: 171 (skipped 24 skeleton reps)
- Gemini classifications returned: 171
- Anthropic wall time: 0.0s
- Gemini wall time: 265.3s

## Pair agreement (Gemini ↔ Anthropic, single-crop fair)

| Pair | Agreement | Sample |
|---|---:|---:|
| Gemini ↔ LLM (text) | 43.3% | 171 |
| Gemini ↔ Vision PS | 35.1% | 171 |

## Ground-truth match against user reviews

- User `accept_source` decisions on these screens: 2
- Gemini canonical_type matched user's picked source: 0 (0.0%)

## Gemini confidence distribution

- 0.95+: 110
- 0.85-0.94: 60
- 0.75-0.84: 1
- <0.75: 0

## `new_type` proposals (catalog gap signal)

| Proposed label | Count |
|---|---:|
| `status_bar` | 1 |

### Example nodes

- `158:12283` — Right → status_bar

## Gemini ↔ Anthropic PS disagreements

Count: 111 / 171 (64.9% of reps)

| Node | Name | Gemini | Anthropic PS |
|---|---|---|---|
| 150:10043 | artboard | image | container |
| 150:10098 | Left | header | container |
| 150:10249 | Left | text | container |
| 150:10053 | Frame 350 | image | container |
| 150:10130 | Center | select | container |
| 150:10227 | title and controls | header | container |
| 150:10252 | Right | text | container |
| 150:10131 | Titles | text_input | heading |
| 150:10143 | wordmark | select | image |
| 151:10368 | Left | header | container |
| 151:10514 | Left | text | container |
| 151:10400 | Center | button | container |
| 151:10492 | title and controls | header | container |
| 151:10517 | Right | text | container |
| 151:10444 | Right | icon_button | button_group |
| 151:10401 | Titles | toggle | heading |
| 151:10272 | Frame 266 | skeleton | list_item |
| 151:10280 | Frame 267 | skeleton | list_item |
| 151:10286 | Frame 268 | skeleton | button |
| 152:10626 | Left | navigation_row | container |
| 152:10772 | Left | text | container |
| 152:10658 | Center | button | container |
| 152:10750 | title and controls | header | container |
| 152:10775 | Right | icon | container |
| 152:10702 | Right | avatar | button_group |
| 152:10659 | Titles | progress | heading |
| 152:10751 | left controls | navigation_row | button_group |
| 152:10610 | Frame 267 | card | list_item |
| 152:10604 | Frame 268 | card | button |
| 153:10785 | artboard | image | container |
| 153:10862 | Left | navigation_row | container |
| 153:11013 | Left | text | container |
| 153:10795 | Frame 350 | card | container |
| 153:10894 | Center | select | container |
| 153:10991 | title and controls | header | container |
| 153:11016 | Right | icon | container |
| 153:10895 | Titles | skeleton | heading |
| 153:10992 | left controls | navigation_row | button_group |
| 153:10907 | wordmark | select | image |
| 154:11026 | artboard | image | container |
| ... | (71 more) | | |

## Decision gate

Add Gemini as a 4th source if at least one holds:
- Gemini ↔ user-review match rate ≥ Anthropic-PS match rate
- Gemini ↔ PS disagreement stays ≥15% AND `new_type` proposals surface real catalog gaps
