# Set-of-Marks bake-off report

- Screens: [150, 151, 152, 153, 154, 155, 156, 157, 158, 159]
- Reps (LLM-classified): 195
- SoM classifications returned: 195
  - Coverage: 100.0%
- Wall time: 72.0s

## Pair agreement

| Pair | Agreement | Sample |
|---|---:|---:|
| SoM ↔ LLM | 49.7% | 195 |
| SoM ↔ Vision PS | 77.4% | 195 |
| SoM ↔ Vision CS | 73.8% | 195 |

## SoM confidence distribution

- 0.95+: 31
- 0.85-0.94: 114
- 0.75-0.84: 48
- <0.75: 2

## SoM ↔ Vision PS disagreements

Count: 44 / 195 (22.6% of reps)

| Node | Name | SoM | PS |
|---|---|---|---|
| 150:10043 | artboard | card | container |
| 150:10223 | grabber | grabber | icon |
| 150:10241 | right controls | container | button_group |
| 151:10488 | grabber | grabber | icon |
| 151:10492 | title and controls | container | header |
| 151:10506 | right controls | container | button_group |
| 152:10746 | grabber | grabber | icon |
| 152:10658 | Center | tabs | container |
| 152:10604 | Frame 268 | card | container |
| 152:10610 | Frame 267 | card | container |
| 152:10764 | right controls | container | button_group |
| 153:10987 | grabber | grabber | icon |
| 153:11005 | right controls | container | button_group |
| 154:11026 | artboard | card | container |
| 154:11206 | grabber | grabber | icon |
| 154:11224 | right controls | container | button_group |
| 155:11463 | grabber | grabber | icon |
| 155:11309 | Frame 266 | card | container |
| 155:11467 | title and controls | container | header |
| 155:11317 | Frame 267 | card | container |
| 155:11481 | right controls | container | button_group |
| 155:11323 | Frame 268 | card | container |
| 156:11720 | grabber | grabber | icon |
| 156:11566 | Frame 266 | card | container |
| 156:11574 | Frame 267 | card | container |
| 156:11580 | Frame 268 | card | container |
| 157:11987 | grabber | grabber | icon |
| 157:11841 | Frame 275 | card | list_item |
| 157:11847 | Frame 276 | card | dialog |
| 157:12005 | right controls | container | button_group |
| 158:12254 | grabber | grabber | icon |
| 158:12108 | Frame 275 | card | list_item |
| 158:12114 | Frame 276 | card | dialog |
| 158:12272 | right controls | container | button_group |
| 159:12586 | grabber | grabber | icon |
| 159:12373 | Frame 271 | list_item | navigation_row |
| 159:12409 | Frame 289 | container | button |
| 159:12420 | Frame 289 | container | button |
| 159:12431 | Frame 289 | container | button |
| 159:12381 | Frame 274 | list_item | navigation_row |
| 159:12604 | right controls | container | button_group |
| 159:12389 | Frame 271 | list_item | navigation_row |
| 159:12397 | Frame 271 | list_item | navigation_row |
| 159:12408 | Frame 276 | list_item | navigation_row |

## Takeaway

SoM strengths are cross-screen vision with shared context; a high SoM↔PS agreement (≥85%) means SoM is ready to replace PS; a moderate agreement (60-85%) plus a confidence lift means SoM is additive as a new source; low agreement (<60%) plus low confidence means the overlay isn't working yet.