---
taskId: TASK-004
title: "Create color normalization utilities"
wave: wave-0
testFirst: false
testLevel: unit
dependencies: [TASK-001]
produces:
  - dd/color.py
verify:
  - type: typecheck
    command: 'python -c "from dd.color import rgba_to_hex, hex_to_oklch, oklch_delta_e, oklch_invert_lightness"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.color import rgba_to_hex; assert rgba_to_hex(0.035, 0.035, 0.043, 1.0) == \"#09090B\""'
    passWhen: 'exits 0'
contextProfile: standard
---

# TASK-004: Create color normalization utilities

## Spec Context

### From Technical Design Spec -- Phase 3: Value Normalization

> **Color normalization:** RGBA 0-1 floats -> 8-digit hex (with alpha) or 6-digit hex (if alpha = 1). Use round(component * 255) for each channel.
>
> | Property path | Raw value example | Resolved value |
> |---|---|---|
> | `fill.0.color` | `{"r":0.035,"g":0.035,"b":0.043,"a":1}` | `#09090B` |
> | `fill.0.color` (with opacity) | `{"r":1,"g":1,"b":1,"a":0.5}` | `#FFFFFF80` |
> | `effect.0.color` | `{"r":0,"g":0,"b":0,"a":0.1}` | `#0000001A` |

### From Technical Design Spec -- Phase 5: Clustering

> **Color clustering:**
> 1. Query `v_color_census WHERE file_id = ?` -- all unique hex values with usage counts.
> 2. Convert to OKLCH for perceptual clustering.
> 3. Group colors within delta-E < 2.0 (imperceptible difference). Merge to the most-used value.

### From Technical Design Spec -- Multi-mode clustering

> For colors, invert lightness in OKLCH space (L -> 1-L), clamp chroma. This is a rough scaffold, not a solution.

### From Architecture.md -- Technology Stack

> | Color science | `coloraide` or manual OKLCH | Perceptual clustering for delta-E calculations |

### OKLCH Manual Conversion Formulas (Fallback)

> **sRGB to Linear RGB:**
> For each channel c in [r, g, b]:
>   if c <= 0.04045: linear = c / 12.92
>   else: linear = ((c + 0.055) / 1.055) ^ 2.4
>
> **Linear RGB to XYZ (D65):**
>   X = 0.4124564 * R + 0.3575761 * G + 0.1804375 * B
>   Y = 0.2126729 * R + 0.7151522 * G + 0.0721750 * B
>   Z = 0.0193339 * R + 0.0658762 * G + 0.7827228 * B
>
> **XYZ to OKLAB:**
>   l_ = 0.8189330101 * X + 0.3618667424 * Y - 0.1288597137 * Z
>   m_ = 0.0329845436 * X + 0.9293118715 * Y + 0.0361456387 * Z
>   s_ = 0.0482003018 * X + 0.2643662691 * Y + 0.6338517070 * Z
>
>   l = cbrt(l_)
>   m = cbrt(m_)
>   s = cbrt(s_)
>
>   L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
>   a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
>   b = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
>
> **OKLAB to OKLCH:**
>   L = L (lightness, 0 to ~1)
>   C = sqrt(a^2 + b^2) (chroma)
>   h = atan2(b, a) in degrees (hue, 0-360)

## Task

Create `dd/color.py` with four public functions for color conversion and comparison. This module is used by the normalization pipeline (TASK-005) and by clustering (wave 3).

1. **`rgba_to_hex(r: float, g: float, b: float, a: float = 1.0) -> str`**:
   - Convert Figma RGBA 0-1 floats to hex string.
   - Clamp each component to [0.0, 1.0] before conversion.
   - Convert each channel: `round(component * 255)`.
   - If `a == 1.0` (exactly), return 6-digit hex: `#RRGGBB` (uppercase).
   - If `a < 1.0`, return 8-digit hex: `#RRGGBBAA` (uppercase).
   - Format each byte as 2-digit uppercase hex with zero-padding.

2. **`hex_to_oklch(hex_color: str) -> tuple[float, float, float]`**:
   - Parse a hex color string (`#RGB`, `#RRGGBB`, or `#RRGGBBAA` -- ignore the alpha channel for OKLCH).
   - Try to use `coloraide` library first:
     ```python
     try:
         from coloraide import Color
         c = Color(hex_color)
         oklch = c.convert("oklch")
         return (oklch['lightness'], oklch['chroma'], oklch['hue'] or 0.0)
     except ImportError:
         # fall back to manual conversion
     ```
   - **Manual fallback**: Implement the sRGB -> Linear RGB -> XYZ D65 -> OKLAB -> OKLCH pipeline from the formulas above.
   - Return `(L, C, h)` where L is lightness (0-1 range), C is chroma (0-0.4 typical), h is hue in degrees (0-360). For achromatic colors (C near 0), set h to 0.0.
   - Use `math.cbrt` (Python 3.11+) for cube root. If not available, use `x ** (1/3)` with sign handling for negative values: `math.copysign(abs(x) ** (1/3), x)`.

3. **`oklch_delta_e(color1: tuple[float, float, float], color2: tuple[float, float, float]) -> float`**:
   - Compute the Euclidean distance in OKLCH space between two `(L, C, h)` tuples.
   - Convert hue to radians for the calculation.
   - Formula: `sqrt((L1-L2)^2 + (C1-C2)^2 + 4*C1*C2*sin((h1-h2)/2)^2)` -- this is the standard OKLCH delta-E using the hue-aware term.
   - Simpler alternative if the above is too complex: use Euclidean in OKLAB space (convert both OKLCH back to OKLAB: `a = C*cos(h_rad)`, `b = C*sin(h_rad)`, then `sqrt(dL^2 + da^2 + db^2)`). This is more robust for achromatic colors.
   - **Use the OKLAB Euclidean approach** (simpler, more robust).
   - Return a float >= 0.0. Values < 2.0 are considered imperceptible.

4. **`oklch_invert_lightness(L: float, C: float, h: float) -> tuple[float, float, float]`**:
   - Invert lightness: `new_L = 1.0 - L`.
   - Clamp chroma: `new_C = min(C, 0.4)` (prevent out-of-gamut after inversion).
   - Keep hue unchanged.
   - Return `(new_L, new_C, h)`.

5. **Internal helper `_hex_to_rgb(hex_color: str) -> tuple[float, float, float]`**:
   - Parse hex string to (r, g, b) as 0-1 floats.
   - Handle `#RGB` (expand each nibble: `#F0A` -> `#FF00AA`), `#RRGGBB`, and `#RRGGBBAA` (ignore alpha).
   - Strip leading `#` if present.

## Acceptance Criteria

- [ ] `python -c "from dd.color import rgba_to_hex, hex_to_oklch, oklch_delta_e, oklch_invert_lightness"` exits 0
- [ ] `python -c "from dd.color import rgba_to_hex; assert rgba_to_hex(0.035, 0.035, 0.043, 1.0) == '#09090B'"` exits 0
- [ ] `python -c "from dd.color import rgba_to_hex; assert rgba_to_hex(1.0, 1.0, 1.0, 0.5) == '#FFFFFF80'"` exits 0
- [ ] `python -c "from dd.color import rgba_to_hex; assert rgba_to_hex(0.0, 0.0, 0.0, 0.1) == '#0000001A'"` exits 0
- [ ] `python -c "from dd.color import rgba_to_hex; assert rgba_to_hex(0.831, 0.831, 0.847, 1.0) == '#D4D4D8'"` exits 0
- [ ] `python -c "from dd.color import hex_to_oklch; L, C, h = hex_to_oklch('#FFFFFF'); assert abs(L - 1.0) < 0.01"` exits 0
- [ ] `python -c "from dd.color import hex_to_oklch; L, C, h = hex_to_oklch('#000000'); assert abs(L) < 0.01"` exits 0
- [ ] `python -c "from dd.color import hex_to_oklch, oklch_delta_e; c1 = hex_to_oklch('#09090B'); c2 = hex_to_oklch('#0A0A0B'); d = oklch_delta_e(c1, c2); assert d < 2.0, f'delta_e={d}'"` exits 0
- [ ] `python -c "from dd.color import hex_to_oklch, oklch_delta_e; c1 = hex_to_oklch('#FF0000'); c2 = hex_to_oklch('#0000FF'); d = oklch_delta_e(c1, c2); assert d > 2.0"` exits 0
- [ ] `python -c "from dd.color import oklch_invert_lightness; L, C, h = oklch_invert_lightness(0.2, 0.1, 180.0); assert abs(L - 0.8) < 0.001"` exits 0
- [ ] `python -c "from dd.color import rgba_to_hex; assert rgba_to_hex(-0.1, 1.5, 0.5, 1.0) == '#00FF80'"` exits 0 (clamping test)

## Notes

- The `coloraide` library may not be installed. The manual fallback MUST work correctly for all test cases. Test the manual path even if coloraide is available by running the internal `_srgb_to_oklch` (or equivalent) function directly.
- `math.cbrt` is available in Python 3.11+. Since we require Python 3.11+, it's safe to use.
- For achromatic colors (black, white, grays), chroma will be near 0 and hue is meaningless. Set hue to 0.0 in this case (when C < 0.001).
- The hex output must be uppercase (`#09090B` not `#09090b`).
- Clamping inputs to [0.0, 1.0] handles edge cases where Figma might report values slightly outside range.