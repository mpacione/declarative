# Set-of-Marks bake-off report

- Screens: [150, 151, 152, 153, 154, 155, 156, 157, 158, 159]
- Reps (LLM-classified): 195
- SoM classifications returned: 195
  - Coverage: 100.0%
- Wall time: 72.0s

## Pair agreement

| Pair | Agreement | Sample |
|---|---:|---:|
| SoM ↔ LLM | 42.6% | 195 |
| SoM ↔ Vision PS | 62.1% | 195 |
| SoM ↔ Vision CS | 66.7% | 195 |

## SoM confidence distribution

- 0.95+: 0
- 0.85-0.94: 64
- 0.75-0.84: 124
- <0.75: 7

## SoM ↔ Vision PS disagreements

Count: 74 / 195 (37.9% of reps)

| Node | Name | SoM | PS |
|---|---|---|---|
| 150:10223 | grabber | grabber | icon |
| 150:10228 | left controls | button_group | container |
| 150:10143 | wordmark | button | image |
| 150:10053 | Frame 350 | container | skeleton |
| 150:10130 | Center | combobox | container |
| 150:10252 | Right | not_ui | container |
| 150:10174 | Right | button_group | container |
| 151:10488 | grabber | grabber | icon |
| 151:10309 | Frame 350 | image | skeleton |
| 151:10320 | Frame 350 | image | skeleton |
| 151:10331 | Frame 350 | image | skeleton |
| 151:10400 | Center | tabs | container |
| 151:10310 | Frame 351 | image | skeleton |
| 151:10321 | Frame 351 | image | skeleton |
| 151:10332 | Frame 351 | image | skeleton |
| 151:10506 | right controls | container | button_group |
| 151:10311 | Frame 352 | image | skeleton |
| 151:10322 | Frame 352 | image | skeleton |
| 151:10333 | Frame 352 | image | skeleton |
| 151:10312 | Frame 353 | image | skeleton |
| 151:10323 | Frame 353 | image | skeleton |
| 151:10334 | Frame 353 | image | skeleton |
| 152:10746 | grabber | grabber | icon |
| 152:10772 | Left | icon_button | container |
| 152:10658 | Center | tabs | container |
| 152:10604 | Frame 268 | card | container |
| 152:10610 | Frame 267 | card | container |
| 152:10764 | right controls | container | button_group |
| 153:10987 | grabber | container | icon |
| 153:10795 | Frame 350 | container | skeleton |
| 153:11016 | Right | not_ui | container |
| 153:11005 | right controls | container | button_group |
| 154:11026 | artboard | card | container |
| 154:11206 | grabber | grabber | icon |
| 154:11126 | wordmark | button | image |
| 154:11036 | Frame 350 | container | skeleton |
| 154:11224 | right controls | container | button_group |
| 155:11463 | grabber | grabber | icon |
| 155:11383 | wordmark | button | image |
| 155:11255 | Frame 350 | container | skeleton |
| 155:11309 | Frame 266 | card | container |
| 155:11317 | Frame 267 | card | container |
| 155:11481 | right controls | container | button_group |
| 155:11323 | Frame 268 | card | container |
| 156:11720 | grabber | grabber | icon |
| 156:11640 | wordmark | button | image |
| 156:11512 | Frame 350 | container | skeleton |
| 156:11566 | Frame 266 | card | container |
| 156:11627 | Center | combobox | container |
| 156:11574 | Frame 267 | card | container |
| ... | (24 more) | | |

## Takeaway

SoM strengths are cross-screen vision with shared context; a high SoM↔PS agreement (≥85%) means SoM is ready to replace PS; a moderate agreement (60-85%) plus a confidence lift means SoM is additive as a new source; low agreement (<60%) plus low confidence means the overlay isn't working yet.