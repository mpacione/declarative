# Set-of-Marks bake-off report (visibility-aware)

- Screens: [260, 261, 262, 263, 264, 265, 266, 267, 268, 269]
- Reps (LLM-classified): 317
  - visible_effective: 187
  - ancestor-hidden:   32
  - self-hidden:       98
- Classifications returned: 317
  - Coverage: 100.0%
- Wall time: 79.3s

## Classifications by path

- `som`: 187
- `hidden_pernode`: 32
- `self_hidden_twin`: 0
- `self_hidden_llm_only`: 98
- `self_hidden_unsure`: 0

## Pair agreement (new verdict vs stored PS/CS/LLM)

| Pair | Agreement | Sample |
|---|---:|---:|
| New ↔ LLM | 59.0% | 317 |
| New ↔ Vision PS (stored) | 41.8% | 311 |
| New ↔ Vision CS (stored) | 41.6% | 317 |

## New-verdict confidence distribution

- 0.95+: 43
- 0.85-0.94: 93
- 0.75-0.84: 83
- <0.75: 98

## SoM ↔ Vision PS disagreements

Count: 181 / 317 (57.1% of reps)

| Node | Name | SoM | PS |
|---|---|---|---|
| 260:49055 | grabber | grabber | icon |
| 260:48963 | Titles | text | container |
| 260:49060 | left controls | button_group | container |
| 260:48707 | Frame 366 | control_point | container |
| 260:48706 | text-box | textarea | container |
| 260:48708 | Frame 361 | control_point | icon_button |
| 260:48667 | Frame 366 | image | control_point |
| 260:48777 | Frame 291 | card | button |
| 260:48668 | Frame 361 | container | icon_button |
| 260:48784 | Frame 292 | card | button |
| 260:48710 | Frame 363 | control_point | icon_button |
| 260:48669 | Frame 362 | container | icon_button |
| 260:48791 | Frame 293 | card | button |
| 260:48711 | Frame 364 | control_point | icon_button |
| 260:48670 | Frame 363 | container | icon_button |
| 260:48712 | Frame 338 | sheet | text_input |
| 260:48671 | Frame 364 | container | icon_button |
| 260:48672 | Frame 367 | divider | icon_button |
| 260:48673 | Frame 372 | divider | icon_button |
| 260:48674 | Frame 371 | divider | icon_button |
| 260:48675 | Frame 373 | divider | icon_button |
| 260:48677 | picker-zoom | container | image |
| 261:49371 | Left | image | container |
| 261:49496 | grabber | grabber | icon |
| 261:49404 | Titles | text | container |
| 261:49501 | left controls | button_group | container |
| 261:49095 | details | text | container |
| 261:49148 | Frame 366 | control_point | container |
| 261:49147 | text-box | textarea | container |
| 261:49149 | Frame 361 | control_point | icon_button |
| 261:49108 | Frame 366 | image | control_point |
| 261:49218 | Frame 291 | card | button |
| 261:49109 | Frame 361 | container | icon_button |
| 261:49225 | Frame 292 | card | button |
| 261:49151 | Frame 363 | control_point | icon_button |
| 261:49110 | Frame 362 | container | icon_button |
| 261:49232 | Frame 293 | card | button |
| 261:49152 | Frame 364 | control_point | icon_button |
| 261:49111 | Frame 363 | container | icon_button |
| 261:49153 | Frame 338 | sheet | text_input |
| 261:49112 | Frame 364 | container | icon_button |
| 261:49113 | Frame 367 | divider | icon_button |
| 261:49114 | Frame 372 | divider | icon_button |
| 261:49115 | Frame 371 | divider | icon_button |
| 261:49116 | Frame 373 | divider | icon_button |
| 261:49118 | picker-zoom | container | image |
| 263:49693 | Dictation + Space + Numbers | container | button_group |
| 263:49702 | Emoji and Numbers | container | button_group |
| 264:50264 | grabber | grabber | icon |
| 264:50172 | Titles | text | container |
| ... | (131 more) | | |

## Takeaway

SoM strengths are cross-screen vision with shared context; a high SoM↔PS agreement (≥85%) means SoM is ready to replace PS; a moderate agreement (60-85%) plus a confidence lift means SoM is additive as a new source; low agreement (<60%) plus low confidence means the overlay isn't working yet.