# Set-of-Marks bake-off report (visibility-aware)

- Screens: [118, 138, 174, 194, 214, 234, 254, 274, 294, 315]
- Reps (LLM-classified): 273
  - visible_effective: 181
  - ancestor-hidden:   34
  - self-hidden:       58
- Classifications returned: 273
  - Coverage: 100.0%
- Wall time: 80.2s

## Classifications by path

- `som`: 181
- `hidden_pernode`: 34
- `self_hidden_auto`: 58

## Pair agreement (new verdict vs stored PS/CS/LLM)

| Pair | Agreement | Sample |
|---|---:|---:|
| New ↔ LLM | 27.1% | 273 |
| New ↔ Vision PS (stored) | 45.7% | 267 |
| New ↔ Vision CS (stored) | 42.5% | 273 |

## New-verdict confidence distribution

- 0.95+: 98
- 0.85-0.94: 103
- 0.75-0.84: 72
- <0.75: 0

## SoM ↔ Vision PS disagreements

Count: 145 / 273 (53.1% of reps)

| Node | Name | SoM | PS |
|---|---|---|---|
| 118:765 | grabber | grabber | icon |
| 118:673 | Titles | not_ui | container |
| 118:770 | left controls | button_group | container |
| 118:438 | Frame 350 | container | skeleton |
| 118:449 | Frame 266 | card | container |
| 118:672 | Center | select | container |
| 118:794 | Right | button_group | container |
| 118:457 | Frame 267 | card | container |
| 118:716 | Right | button_group | container |
| 118:463 | Frame 268 | card | container |
| 138:8887 | grabber | grabber | icon |
| 138:8795 | Titles | not_ui | container |
| 138:8892 | left controls | button_group | container |
| 138:8665 | Frame 289 | card | button |
| 138:8671 | Frame 289 | card | button |
| 138:8677 | Frame 289 | card | button |
| 138:8683 | Frame 289 | card | button |
| 138:8689 | Frame 289 | card | button |
| 138:8695 | Frame 289 | card | button |
| 138:8701 | Frame 289 | card | button |
| 138:8707 | Frame 289 | card | button |
| 138:8648 | Frame 382 | card | list_item |
| 138:8489 | Frame 350 | container | skeleton |
| 138:8652 | Frame 394 | card | list_item |
| 138:8838 | Right | button_group | container |
| 138:8656 | Frame 395 | card | list_item |
| 138:8660 | Frame 396 | card | list_item |
| 174:19333 | grabber | grabber | icon |
| 174:19241 | Titles | not_ui | container |
| 174:19338 | left controls | button_group | container |
| 174:19120 | Frame 292 | card | list_item |
| 174:18940 | Frame 366 | container | control_point |
| 174:19131 | Frame 293 | card | list_item |
| 174:18937 | canvas | container | image |
| 174:18941 | Frame 361 | control_point | icon_button |
| 174:18942 | Frame 362 | control_point | icon_button |
| 174:18943 | Frame 363 | control_point | icon_button |
| 174:18944 | Frame 364 | control_point | icon_button |
| 174:18945 | Frame 367 | not_ui | icon_button |
| 174:18946 | Frame 372 | not_ui | icon_button |
| 174:18947 | Frame 371 | not_ui | icon_button |
| 174:18948 | Frame 373 | not_ui | icon_button |
| 174:18949 | picker-zoom | not_ui | image |
| 194:24985 | Titles | not_ui | container |
| 194:24963 | wordmark | not_ui | image |
| 194:24923 | Frame 266 | card | container |
| 194:24912 | Frame 350 | sheet | container |
| 194:25076 | address | link | text_input |
| 194:24931 | Frame 267 | card | container |
| 194:24937 | Frame 268 | card | container |
| ... | (95 more) | | |

## Takeaway

SoM strengths are cross-screen vision with shared context; a high SoM↔PS agreement (≥85%) means SoM is ready to replace PS; a moderate agreement (60-85%) plus a confidence lift means SoM is additive as a new source; low agreement (<60%) plus low confidence means the overlay isn't working yet.