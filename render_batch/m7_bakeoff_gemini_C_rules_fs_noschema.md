# Gemini 2.5 Flash vision bake-off report (v2)

- Screens: [150, 151, 152, 153, 154, 155, 156, 157, 158, 159]
- Reps after skeleton-filter: 171 (skipped 24 skeleton reps)
- Gemini classifications returned: 171
- Anthropic wall time: 0.0s
- Gemini wall time: 328.7s

## Pair agreement (Gemini ↔ Anthropic, single-crop fair)

| Pair | Agreement | Sample |
|---|---:|---:|
| Gemini ↔ LLM (text) | 38.0% | 171 |
| Gemini ↔ Vision PS | 45.0% | 171 |

## Ground-truth match against user reviews

- User `accept_source` decisions on these screens: 2
- Gemini canonical_type matched user's picked source: 1 (50.0%)

## Gemini confidence distribution

- 0.95+: 117
- 0.85-0.94: 49
- 0.75-0.84: 4
- <0.75: 1

## `new_type` proposals (catalog gap signal)

| Proposed label | Count |
|---|---:|
| `drag_handle` | 1 |
| `grab_handle` | 1 |

### Example nodes

- `150:10223` — grabber → grab_handle
- `154:11206` — grabber → drag_handle

## Gemini ↔ Anthropic PS disagreements

Count: 94 / 171 (55.0% of reps)

| Node | Name | Gemini | Anthropic PS |
|---|---|---|---|
| 150:10223 | grabber | new_type | icon |
| 150:10249 | Left | text | container |
| 150:10130 | Center | button | container |
| 150:10227 | title and controls | header | container |
| 150:10131 | Titles | container | heading |
| 150:10143 | wordmark | select | image |
| 151:10368 | Left | tabs | container |
| 151:10488 | grabber | icon_button | icon |
| 151:10514 | Left | text | container |
| 151:10400 | Center | button_group | container |
| 151:10492 | title and controls | header | container |
| 151:10444 | Right | icon_button | button_group |
| 151:10401 | Titles | skeleton | heading |
| 151:10413 | wordmark | navigation_row | image |
| 151:10272 | Frame 266 | container | list_item |
| 151:10280 | Frame 267 | container | list_item |
| 151:10286 | Frame 268 | container | button |
| 152:10626 | Left | navigation_row | container |
| 152:10746 | grabber | icon_button | icon |
| 152:10772 | Left | text | container |
| 152:10658 | Center | button | container |
| 152:10750 | title and controls | header | container |
| 152:10702 | Right | icon_button | button_group |
| 152:10659 | Titles | unsure | heading |
| 152:10610 | Frame 267 | card | list_item |
| 152:10604 | Frame 268 | card | button |
| 153:10987 | grabber | icon_button | icon |
| 153:11013 | Left | text | container |
| 153:10795 | Frame 350 | sheet | container |
| 153:10894 | Center | select | container |
| 153:10991 | title and controls | header | container |
| 153:10895 | Titles | skeleton | heading |
| 153:10907 | wordmark | select | image |
| 154:11206 | grabber | new_type | icon |
| 154:11232 | Left | text | container |
| 154:11036 | Frame 350 | image | container |
| 154:11113 | Center | select | container |
| 154:11210 | title and controls | header | container |
| 154:11114 | Titles | container | heading |
| 154:11126 | wordmark | select | image |
| ... | (54 more) | | |

## Decision gate

Add Gemini as a 4th source if at least one holds:
- Gemini ↔ user-review match rate ≥ Anthropic-PS match rate
- Gemini ↔ PS disagreement stays ≥15% AND `new_type` proposals surface real catalog gaps
