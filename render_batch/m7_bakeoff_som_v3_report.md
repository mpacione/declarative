# Set-of-Marks bake-off report

- Screens: [150, 151, 152, 153, 154, 155, 156, 157, 158, 159]
- Reps (LLM-classified): 195
- SoM classifications returned: 195
  - Coverage: 100.0%
- Wall time: 73.4s

## Pair agreement

| Pair | Agreement | Sample |
|---|---:|---:|
| SoM ↔ LLM | 48.2% | 195 |
| SoM ↔ Vision PS | 71.3% | 195 |
| SoM ↔ Vision CS | 71.8% | 195 |

## SoM confidence distribution

- 0.95+: 42
- 0.85-0.94: 94
- 0.75-0.84: 58
- <0.75: 1

## SoM ↔ Vision PS disagreements

Count: 56 / 195 (28.7% of reps)

| Node | Name | SoM | PS |
|---|---|---|---|
| 150:10223 | grabber | grabber | icon |
| 150:10228 | left controls | button_group | container |
| 150:10053 | Frame 350 | container | skeleton |
| 150:10174 | Right | button_group | container |
| 151:10488 | grabber | grabber | icon |
| 151:10493 | left controls | button_group | container |
| 151:10272 | Frame 266 | card | container |
| 151:10400 | Center | tabs | container |
| 151:10517 | Right | button_group | container |
| 151:10280 | Frame 267 | card | container |
| 151:10286 | Frame 268 | card | container |
| 152:10746 | grabber | grabber | icon |
| 152:10751 | left controls | button_group | container |
| 152:10658 | Center | tabs | container |
| 152:10775 | Right | button_group | container |
| 152:10604 | Frame 268 | card | container |
| 152:10610 | Frame 267 | card | container |
| 153:10987 | grabber | grabber | icon |
| 153:10992 | left controls | button_group | container |
| 153:10795 | Frame 350 | container | skeleton |
| 153:10938 | Right | button_group | container |
| 154:11206 | grabber | grabber | icon |
| 154:11211 | left controls | button_group | container |
| 154:11235 | Right | not_ui | container |
| 154:11157 | Right | button_group | container |
| 155:11463 | grabber | grabber | icon |
| 155:11468 | left controls | button_group | container |
| 155:11309 | Frame 266 | card | container |
| 155:11317 | Frame 267 | card | container |
| 155:11323 | Frame 268 | card | container |
| 156:11720 | grabber | grabber | icon |
| 156:11725 | left controls | button_group | container |
| 156:11566 | Frame 266 | card | container |
| 156:11574 | Frame 267 | card | container |
| 156:11580 | Frame 268 | card | container |
| 157:11987 | grabber | grabber | icon |
| 157:11992 | left controls | button_group | container |
| 157:11841 | Frame 275 | card | list_item |
| 157:12016 | Right | button_group | container |
| 157:11847 | Frame 276 | card | dialog |
| 158:12254 | grabber | grabber | icon |
| 158:12259 | left controls | button_group | container |
| 158:12108 | Frame 275 | card | list_item |
| 158:12036 | Frame 350 | container | skeleton |
| 158:12114 | Frame 276 | card | dialog |
| 159:12586 | grabber | grabber | icon |
| 159:12591 | left controls | button_group | container |
| 159:12373 | Frame 271 | list_item | navigation_row |
| 159:12409 | Frame 289 | container | button |
| 159:12420 | Frame 289 | container | button |
| ... | (6 more) | | |

## Takeaway

SoM strengths are cross-screen vision with shared context; a high SoM↔PS agreement (≥85%) means SoM is ready to replace PS; a moderate agreement (60-85%) plus a confidence lift means SoM is additive as a new source; low agreement (<60%) plus low confidence means the overlay isn't working yet.