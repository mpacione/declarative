---
taskId: TASK-006
title: "Write unit tests for color + normalization utilities"
wave: wave-0
testFirst: false
testLevel: unit
dependencies: [TASK-004, TASK-005]
produces:
  - tests/test_color.py
  - tests/test_normalize.py
verify:
  - type: test
    command: 'pytest tests/test_color.py tests/test_normalize.py -v'
    passWhen: 'all tests pass'
contextProfile: standard
---

# TASK-006: Write unit tests for color + normalization utilities

## Spec Context

### From dd/color.py (produced by TASK-004)

> Exports:
> - `rgba_to_hex(r: float, g: float, b: float, a: float = 1.0) -> str` -- Figma RGBA 0-1 to hex
> - `hex_to_oklch(hex_color: str) -> tuple[float, float, float]` -- hex to (L, C, h)
> - `oklch_delta_e(color1: tuple, color2: tuple) -> float` -- perceptual distance
> - `oklch_invert_lightness(L: float, C: float, h: float) -> tuple[float, float, float]` -- dark mode inversion

### From dd/normalize.py (produced by TASK-005)

> Exports:
> - `normalize_fill(fills: list[dict]) -> list[dict]` -- Figma fills to binding rows
> - `normalize_stroke(strokes: list[dict]) -> list[dict]` -- Figma strokes to binding rows
> - `normalize_effect(effects: list[dict]) -> list[dict]` -- effect decomposition into 5 binding rows per shadow
> - `normalize_typography(node: dict) -> list[dict]` -- text properties to binding rows
> - `normalize_spacing(node: dict) -> list[dict]` -- spacing properties to binding rows
> - `normalize_radius(corner_radius) -> list[dict]` -- radius to binding rows
>
> Each function returns list of dicts with keys: `property`, `raw_value`, `resolved_value`.

### From Technical Design Spec -- known color values from probe

> - Zinc 950: `{"r":0.035,"g":0.035,"b":0.043,"a":1}` -> `#09090B`
> - Zinc 300: `{"r":0.831,"g":0.831,"b":0.847,"a":1}` -> `#D4D4D8`
> - Pure white half-opacity: `{"r":1,"g":1,"b":1,"a":0.5}` -> `#FFFFFF80`
> - Shadow black: `{"r":0,"g":0,"b":0,"a":0.1}` -> `#0000001A`

## Task

Create comprehensive unit tests for the color and normalization modules. Use `@pytest.mark.unit` decorator on all tests.

### `tests/test_color.py`

Write tests for all four public functions in `dd/color.py`:

1. **`rgba_to_hex` tests** (at least 8 test cases):
   - Known Figma colors: Zinc 950 (0.035, 0.035, 0.043, 1.0) -> `#09090B`
   - Known Figma colors: Zinc 300 (0.831, 0.831, 0.847, 1.0) -> `#D4D4D8`
   - Pure white: (1.0, 1.0, 1.0, 1.0) -> `#FFFFFF`
   - Pure black: (0.0, 0.0, 0.0, 1.0) -> `#000000`
   - White with alpha: (1.0, 1.0, 1.0, 0.5) -> `#FFFFFF80`
   - Black with low alpha: (0.0, 0.0, 0.0, 0.1) -> `#0000001A`
   - Input clamping: (-0.1, 1.5, 0.5, 1.0) -> `#00FF80`
   - Full red: (1.0, 0.0, 0.0, 1.0) -> `#FF0000`

2. **`hex_to_oklch` tests** (at least 5 test cases):
   - White (#FFFFFF): L close to 1.0, C close to 0.0
   - Black (#000000): L close to 0.0, C close to 0.0
   - Pure red (#FF0000): L > 0.5, C > 0.1, h roughly 29 degrees (+-10)
   - A gray (#808080): L around 0.6, C close to 0.0
   - Short hex format (#F00): same result as #FF0000

3. **`oklch_delta_e` tests** (at least 4 test cases):
   - Identical colors: delta_e == 0.0
   - Very similar colors (#09090B vs #0A0A0B): delta_e < 2.0
   - Very different colors (#FF0000 vs #0000FF): delta_e > 2.0
   - Black vs white: delta_e > 0.5

4. **`oklch_invert_lightness` tests** (at least 3 test cases):
   - Invert L=0.2: new L=0.8
   - Invert L=0.0: new L=1.0
   - Chroma clamping: C=0.5 -> C=0.4

### `tests/test_normalize.py`

Write tests for all six public functions in `dd/normalize.py`:

5. **`normalize_fill` tests** (at least 6 test cases):
   - Single solid fill produces 1 binding with correct property path and hex value
   - Two solid fills produce 2 bindings: `fill.0.color` and `fill.1.color`
   - Gradient fill produces binding with property `fill.0.gradient`
   - Invisible fill (visible=False) produces 0 bindings
   - IMAGE fill type produces 0 bindings
   - Empty list input produces 0 bindings
   - Mixed visible + invisible fills: only visible fills produce bindings

6. **`normalize_stroke` tests** (at least 3 test cases):
   - Single solid stroke produces 1 binding with `stroke.0.color`
   - Invisible stroke is skipped
   - Multiple strokes indexed correctly

7. **`normalize_effect` tests** (at least 4 test cases):
   - DROP_SHADOW produces exactly 5 bindings (color, radius, offsetX, offsetY, spread)
   - INNER_SHADOW also produces 5 bindings
   - LAYER_BLUR produces exactly 1 binding (radius only)
   - Invisible effect is skipped
   - Two effects indexed as `effect.0.*` and `effect.1.*`

8. **`normalize_typography` tests** (at least 4 test cases):
   - Full text node (all properties) produces 5 bindings
   - MIXED values are skipped
   - None values are skipped
   - lineHeight with `{"unit": "AUTO"}` produces resolved_value `"AUTO"`
   - lineHeight with `{"value": 24, "unit": "PIXELS"}` produces resolved_value `"24"`

9. **`normalize_spacing` tests** (at least 3 test cases):
   - Full spacing node produces correct number of non-zero bindings
   - Zero values are skipped
   - None values are skipped
   - Property mapping is correct (padding_top -> padding.top, item_spacing -> itemSpacing)

10. **`normalize_radius` tests** (at least 4 test cases):
    - Single number > 0 produces 1 binding with property `cornerRadius`
    - Dict with mixed values produces bindings only for non-zero corners
    - Zero radius returns empty list
    - None returns empty list

Every test should verify all 3 keys in the returned dicts: `property`, `raw_value`, `resolved_value`. Use `import json` to verify `raw_value` is valid JSON by parsing it.

Add a `import pytest` and mark each test function with `@pytest.mark.unit`. Set `pytestmark = pytest.mark.unit` at module level for convenience.

Add `@pytest.mark.timeout(10)` at module level to prevent any test from hanging.

## Acceptance Criteria

- [ ] `pytest tests/test_color.py -v` passes all tests
- [ ] `pytest tests/test_normalize.py -v` passes all tests
- [ ] `tests/test_color.py` contains at least 20 test cases across the 4 function groups
- [ ] `tests/test_normalize.py` contains at least 24 test cases across the 6 function groups
- [ ] All tests have `@pytest.mark.unit` marker (either per-function or via `pytestmark`)
- [ ] Every test asserts on specific expected values, not just "doesn't crash"
- [ ] `raw_value` is verified as valid JSON in normalization tests (via `json.loads`)
- [ ] `pytest tests/test_color.py tests/test_normalize.py -v --tb=short` exits 0

## Notes

- These are pure unit tests. No database, no fixtures, no file I/O.
- Use parametrize where appropriate for the rgba_to_hex and similar repetitive tests.
- The delta_e tests use approximate comparisons (`< 2.0`, `> 2.0`) not exact values, since the math may vary slightly between coloraide and manual implementations.
- All test files should be importable as Python modules (no syntax errors even when not run via pytest).