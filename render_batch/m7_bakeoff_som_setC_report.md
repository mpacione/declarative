# Set-of-Marks bake-off report (visibility-aware)

- Screens: [200, 201, 202, 203, 204, 205, 206, 207, 208, 209]
- Reps (LLM-classified): 208
  - visible_effective: 114
  - ancestor-hidden:   10
  - self-hidden:       84
- Classifications returned: 208
  - Coverage: 100.0%
- Wall time: 56.2s

## Classifications by path

- `som`: 114
- `hidden_pernode`: 10
- `self_hidden_twin`: 10
- `self_hidden_llm_only`: 74
- `self_hidden_unsure`: 0

## Pair agreement (new verdict vs stored PS/CS/LLM)

| Pair | Agreement | Sample |
|---|---:|---:|
| New ↔ LLM | 56.7% | 208 |
| New ↔ Vision PS (stored) | 25.6% | 195 |
| New ↔ Vision CS (stored) | 24.5% | 208 |

## New-verdict confidence distribution

- 0.95+: 20
- 0.85-0.94: 76
- 0.75-0.84: 38
- <0.75: 74

## SoM ↔ Vision PS disagreements

Count: 145 / 208 (69.7% of reps)

| Node | Name | SoM | PS |
|---|---|---|---|
| 200:26732 | Titles | text | container |
| 200:26634 | Frame 289 | image | button |
| 200:26640 | Frame 289 | image | button |
| 200:26646 | Frame 289 | image | button |
| 200:26652 | Frame 289 | image | button |
| 200:26658 | Frame 289 | image | button |
| 200:26664 | Frame 289 | image | button |
| 200:26670 | Frame 289 | image | button |
| 200:26676 | Frame 289 | image | button |
| 200:26617 | Frame 382 | container | list_item |
| 200:26621 | Frame 394 | card | list_item |
| 200:26823 | address | link | text_input |
| 200:26616 | Frame 396 | card | container |
| 200:26625 | Frame 395 | card | list_item |
| 200:26629 | Frame 396 | card | list_item |
| 201:26991 | Titles | text | container |
| 201:27082 | address | link | text_input |
| 201:26860 | Frame 366 | image | icon_button |
| 201:26857 | Frame 350 | container | image |
| 201:27034 | Right | button_group | container |
| 201:26861 | Frame 361 | control_point | icon_button |
| 201:26862 | Frame 362 | control_point | icon_button |
| 201:26863 | Frame 363 | control_point | icon_button |
| 201:26864 | Frame 364 | control_point | icon_button |
| 201:26865 | Frame 367 | control_point | icon_button |
| 201:26866 | Frame 372 | control_point | icon_button |
| 201:26867 | Frame 371 | control_point | icon_button |
| 201:26868 | Frame 373 | control_point | icon_button |
| 202:27292 | Titles | text | container |
| 202:27383 | address | link | text_input |
| 202:27116 | Frame 350 | container | image |
| 202:27335 | Right | button_group | container |
| 202:27120 | Frame 366 | image | icon_button |
| 202:27121 | Frame 361 | icon | icon_button |
| 202:27122 | Frame 362 | icon | icon_button |
| 202:27123 | Frame 363 | icon | icon_button |
| 202:27124 | Frame 364 | icon | icon_button |
| 202:27125 | Frame 367 | divider | icon_button |
| 202:27126 | Frame 372 | divider | icon_button |
| 202:27127 | Frame 371 | divider | icon_button |
| 202:27128 | Frame 373 | divider | icon_button |
| 203:27628 | Titles | text | container |
| 203:27719 | address | link | text_input |
| 203:27417 | Frame 350 | container | image |
| 203:27671 | Right | button_group | container |
| 203:27421 | Frame 366 | image | icon_button |
| 203:27422 | Frame 361 | icon | icon_button |
| 203:27423 | Frame 362 | icon | icon_button |
| 203:27424 | Frame 363 | icon | icon_button |
| 203:27425 | Frame 364 | icon | icon_button |
| ... | (95 more) | | |

## Takeaway

SoM strengths are cross-screen vision with shared context; a high SoM↔PS agreement (≥85%) means SoM is ready to replace PS; a moderate agreement (60-85%) plus a confidence lift means SoM is additive as a new source; low agreement (<60%) plus low confidence means the overlay isn't working yet.