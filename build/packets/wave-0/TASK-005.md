---
taskId: TASK-005
title: "Create value normalization module"
wave: wave-0
testFirst: false
testLevel: unit
dependencies: [TASK-003, TASK-004]
produces:
  - dd/normalize.py
verify:
  - type: typecheck
    command: 'python -c "from dd.normalize import normalize_fill, normalize_stroke, normalize_effect, normalize_typography, normalize_spacing, normalize_radius"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.normalize import normalize_fill; result = normalize_fill([{\"type\":\"SOLID\",\"color\":{\"r\":0.035,\"g\":0.035,\"b\":0.043,\"a\":1}}]); print(result); assert len(result) == 1 and result[0][\"property\"] == \"fill.0.color\" and result[0][\"resolved_value\"] == \"#09090B\""'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-005: Create value normalization module

## Spec Context

### From Technical Design Spec -- Phase 3: Value Normalization + Binding Creation

> For every node property that represents a design value:
>
> | Property path | Raw value example | Resolved value |
> |---|---|---|
> | `fill.0.color` | `{"r":0.035,"g":0.035,"b":0.043,"a":1}` | `#09090B` |
> | `fill.0.color` (with opacity) | `{"r":1,"g":1,"b":1,"a":0.5}` | `#FFFFFF80` |
> | `stroke.0.color` | `{"r":0.831,"g":0.831,"b":0.847,"a":1}` | `#D4D4D8` |
> | `cornerRadius` | `8` | `8` |
> | `fontSize` | `16` | `16` |
> | `fontFamily` | `"Inter"` | `Inter` |
> | `fontWeight` | `600` | `600` |
> | `lineHeight` | `{"value":24,"unit":"PIXELS"}` | `24` |
> | `letterSpacing` | `{"value":-0.5,"unit":"PIXELS"}` | `-0.5` |
> | `padding.top` | `16` | `16` |
> | `itemSpacing` | `8` | `8` |
> | `opacity` | `0.5` | `0.5` |
> | `effect.0.color` | `{"r":0,"g":0,"b":0,"a":0.1}` | `#0000001A` |
> | `effect.0.radius` | `6` | `6` |
> | `effect.0.offsetX` | `0` | `0` |
> | `effect.0.offsetY` | `4` | `4` |
> | `effect.0.spread` | `-1` | `-1` |
>
> **Effect decomposition:** Each effect property gets its own binding row. A single DROP_SHADOW produces 5 bindings: `effect.0.color`, `effect.0.radius`, `effect.0.offsetX`, `effect.0.offsetY`, `effect.0.spread`. This maps 1:1 to Figma's `setBoundVariableForEffect` API which binds each field independently.
>
> **Gradient handling:** Store as `fill.0.gradient` with stops array in raw_value. Resolved value is a CSS `linear-gradient()` or `radial-gradient()` string. Gradient color stops cannot be bound to variables in Figma -- stored for code export only.
>
> **Mixed fills:** Figma supports multiple fills per node. Each gets its own binding row: `fill.0.color`, `fill.1.color`, etc.

### From Technical Design Spec -- Mixed text styles

> Figma TEXT nodes can have mixed styles (different fonts/sizes within one text box). `use_figma` returns `figma.mixed` for these. Store as `"MIXED"` in raw_value, skip binding creation. Flag for manual review.

### From dd/types.py (produced by TASK-003)

> Exports: `FILL_COLOR_PATTERN`, `STROKE_COLOR_PATTERN`, `EFFECT_FIELD_PATTERN`, `PADDING_PROPERTIES`, `SPACING_PROPERTIES`, `TYPOGRAPHY_PROPERTIES`, `DIMENSION_PROPERTIES`

### From dd/color.py (produced by TASK-004)

> Exports: `rgba_to_hex(r, g, b, a)` -- converts Figma RGBA 0-1 floats to hex string.

## Task

Create `dd/normalize.py` with functions that convert raw Figma property values into normalized binding rows. Each function takes a raw Figma value and returns a list of dicts, where each dict represents one `node_token_bindings` row with keys: `property` (str), `raw_value` (str, JSON), `resolved_value` (str).

1. **`normalize_fill(fills: list[dict]) -> list[dict]`**:
   - Input: Figma fills array (e.g., `[{"type": "SOLID", "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}, "visible": true}]`)
   - For each fill at index `i`:
     - Skip if `fill.get("visible") == False` (Figma uses explicit False, not falsy).
     - If `fill["type"] == "SOLID"`: extract color dict, call `rgba_to_hex`, produce `{"property": f"fill.{i}.color", "raw_value": json.dumps(fill["color"]), "resolved_value": hex_string}`.
     - If `fill["type"]` is `"GRADIENT_LINEAR"`, `"GRADIENT_RADIAL"`, `"GRADIENT_ANGULAR"`, or `"GRADIENT_DIAMOND"`: store as `{"property": f"fill.{i}.gradient", "raw_value": json.dumps(fill), "resolved_value": "gradient"}`. Don't try to resolve gradient values -- they can't be variable-bound.
     - Skip `IMAGE` fill types entirely.
   - Return list of binding dicts.

2. **`normalize_stroke(strokes: list[dict]) -> list[dict]`**:
   - Same pattern as fills but property is `stroke.{i}.color`.
   - Only handle `SOLID` strokes. Skip gradients/images.

3. **`normalize_effect(effects: list[dict]) -> list[dict]`**:
   - Input: Figma effects array (e.g., `[{"type": "DROP_SHADOW", "visible": true, "color": {"r":0,"g":0,"b":0,"a":0.1}, "radius": 6, "offset": {"x": 0, "y": 4}, "spread": -1}]`)
   - For each effect at index `i`:
     - Skip if `effect.get("visible") == False`.
     - Only process `DROP_SHADOW`, `INNER_SHADOW`, and `LAYER_BLUR` types.
     - For `DROP_SHADOW` and `INNER_SHADOW`, produce 5 bindings:
       - `effect.{i}.color` -> `rgba_to_hex(color.r, color.g, color.b, color.a)`
       - `effect.{i}.radius` -> `str(effect["radius"])`
       - `effect.{i}.offsetX` -> `str(effect["offset"]["x"])`
       - `effect.{i}.offsetY` -> `str(effect["offset"]["y"])`
       - `effect.{i}.spread` -> `str(effect.get("spread", 0))`
     - For `LAYER_BLUR`, produce 1 binding: `effect.{i}.radius` -> `str(effect["radius"])`.
     - Raw values: for color, store the color dict as JSON; for numeric fields, store the number as JSON string.

4. **`normalize_typography(node: dict) -> list[dict]`**:
   - Input: A dict with keys from Figma TEXT node properties: `font_family`, `font_weight`, `font_size`, `line_height`, `letter_spacing`.
   - For each property that is not None and is not `"MIXED"`:
     - `fontSize`: `{"property": "fontSize", "raw_value": json.dumps(value), "resolved_value": str(value)}`
     - `fontFamily`: `{"property": "fontFamily", "raw_value": json.dumps(value), "resolved_value": str(value)}`
     - `fontWeight`: `{"property": "fontWeight", "raw_value": json.dumps(value), "resolved_value": str(value)}`
     - `lineHeight`: If dict with `{"value": N, "unit": "PIXELS"}`, resolved is `str(N)`. If `{"unit": "AUTO"}`, resolved is `"AUTO"`. If raw number, resolved is `str(value)`. Store the original dict/value as raw_value JSON.
     - `letterSpacing`: Same pattern as lineHeight -- extract numeric value from dict.
   - Skip any property where the value is `"MIXED"` (mixed text styles).

5. **`normalize_spacing(node: dict) -> list[dict]`**:
   - Input: dict with keys `padding_top`, `padding_right`, `padding_bottom`, `padding_left`, `item_spacing`, `counter_axis_spacing`.
   - For each non-None property:
     - Map `padding_top` -> property `"padding.top"`, `padding_right` -> `"padding.right"`, etc.
     - Map `item_spacing` -> `"itemSpacing"`, `counter_axis_spacing` -> `"counterAxisSpacing"`.
     - `resolved_value`: `str(value)`.
     - `raw_value`: `json.dumps(value)`.
   - Skip values that are 0 (zero spacing is default, not worth binding).

6. **`normalize_radius(corner_radius) -> list[dict]`**:
   - Input: either a number (uniform radius) or a JSON string/dict with per-corner values `{"tl":8,"tr":8,"bl":0,"br":0}`.
   - If a single number and > 0: produce `{"property": "cornerRadius", "raw_value": json.dumps(value), "resolved_value": str(value)}`.
   - If a dict with per-corner values: produce up to 4 bindings (`topLeftRadius`, `topRightRadius`, `bottomLeftRadius`, `bottomRightRadius`) for non-zero values.
   - If 0 or None, return empty list.

All functions must use `import json` for `raw_value` serialization and import `rgba_to_hex` from `dd.color`.

## Acceptance Criteria

- [ ] `python -c "from dd.normalize import normalize_fill, normalize_stroke, normalize_effect, normalize_typography, normalize_spacing, normalize_radius"` exits 0
- [ ] `normalize_fill([{"type":"SOLID","color":{"r":0.035,"g":0.035,"b":0.043,"a":1}}])` returns `[{"property":"fill.0.color","raw_value":..., "resolved_value":"#09090B"}]`
- [ ] `normalize_fill([{"type":"SOLID","color":{"r":1,"g":1,"b":1,"a":0.5}}])` produces resolved_value `"#FFFFFF80"`
- [ ] `normalize_fill([{"type":"GRADIENT_LINEAR","gradientStops":[...]}])` produces property `"fill.0.gradient"`
- [ ] `normalize_fill([{"type":"SOLID","color":{"r":1,"g":0,"b":0,"a":1},"visible":False}])` returns empty list (invisible fill skipped)
- [ ] `normalize_effect([{"type":"DROP_SHADOW","visible":True,"color":{"r":0,"g":0,"b":0,"a":0.1},"radius":6,"offset":{"x":0,"y":4},"spread":-1}])` returns exactly 5 binding dicts
- [ ] `normalize_typography({"font_family":"Inter","font_weight":600,"font_size":16,"line_height":{"value":24,"unit":"PIXELS"},"letter_spacing":{"value":-0.5,"unit":"PIXELS"}})` returns 5 binding dicts with correct resolved values
- [ ] `normalize_typography({"font_family":"MIXED","font_weight":"MIXED","font_size":16,"line_height":None,"letter_spacing":None})` returns only 1 binding (fontSize), skipping MIXED and None
- [ ] `normalize_spacing({"padding_top":16,"padding_right":16,"padding_bottom":16,"padding_left":16,"item_spacing":8,"counter_axis_spacing":None})` returns 5 bindings (4 padding + itemSpacing)
- [ ] `normalize_spacing({"padding_top":0,"padding_right":0,"padding_bottom":0,"padding_left":0,"item_spacing":0,"counter_axis_spacing":None})` returns empty list (zero values skipped)
- [ ] `normalize_radius(8)` returns 1 binding with property `"cornerRadius"`
- [ ] `normalize_radius({"tl":8,"tr":8,"bl":0,"br":0})` returns 2 bindings (only non-zero corners)
- [ ] `normalize_radius(0)` returns empty list
- [ ] All returned dicts have exactly 3 keys: `"property"`, `"raw_value"`, `"resolved_value"`

## Notes

- The `raw_value` field must always be a JSON-serialized string (via `json.dumps`), even for simple numbers. This ensures consistent format in the database.
- `resolved_value` is always a string -- numbers are converted with `str()`.
- The `visible` field check: Figma fills/effects have an explicit `visible` boolean. If the key is missing, treat as visible (True). Only skip when explicitly `False`.
- For `lineHeight` with `"unit": "AUTO"`, the resolved value is the string `"AUTO"` -- this special case needs handling during clustering (it won't match a numeric value).