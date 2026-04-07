# Cross-Platform Value Formats — Renderer Transformation Reference

> How each UI platform represents design properties. Used to determine what belongs in the IR (ground truth) vs what belongs in each renderer (platform-specific transformation).

## Principle

The IR stores **ground truth** values — the format closest to lossless extraction. Each renderer transforms from IR format to its native format. No transformation is "universal" except JSON string parsing and integer→boolean conversion.

## Property Reference

### Rotation

| Platform | Unit | Example |
|---|---|---|
| **IR (DB)** | **radians** (from REST API) | `1.5708` |
| Figma Plugin API | degrees | `node.rotation = 90` |
| CSS | deg, rad, turn (all accepted) | `transform: rotate(90deg)` |
| SwiftUI | Angle type (either) | `.rotationEffect(.degrees(90))` |
| Flutter | **radians** | `Transform.rotate(angle: 1.5708)` |
| Android XML | degrees | `android:rotation="90"` |
| HTML Canvas | **radians** | `ctx.rotate(1.5708)` |

**IR stores radians.** Flutter and Canvas use radians natively — no conversion needed. Figma, CSS, Android convert to degrees. SwiftUI accepts either.

### Color

| Platform | Format | Alpha position | Example |
|---|---|---|---|
| **IR (DB)** | **hex #RRGGBBAA** | last 2 digits | `#FF000080` |
| Figma Plugin API | {r,g,b} 0-1 floats + paint opacity | separate field | `{r:1, g:0, b:0}` + `opacity: 0.5` |
| CSS | hex, rgb(), rgba(), hsl() | last param | `rgba(255, 0, 0, 0.5)` |
| SwiftUI | Color(red:green:blue:opacity:) 0-1 | named param | `Color(red: 1, green: 0, blue: 0, opacity: 0.5)` |
| Flutter | packed int 0xAARRGGBB | **first** 2 digits | `Color(0x80FF0000)` |
| Android XML | #AARRGGBB hex | **first** 2 digits | `#80FF0000` |

**IR stores hex with alpha last.** Every platform needs different conversion. Flutter and Android put alpha first (byte-swapped from IR).

### Font Weight

| Platform | Format | Example |
|---|---|---|
| **IR (DB)** | **numeric 400-900** | `600` |
| Figma Plugin API | style name string | `"Semi Bold"` |
| CSS | numeric | `font-weight: 600` |
| SwiftUI | Weight enum | `.fontWeight(.semibold)` |
| Flutter | FontWeight constant | `FontWeight.w600` |
| Android XML | numeric | `android:fontWeight="600"` |

**IR stores numeric.** Only Figma needs weight→style-name conversion. CSS, Flutter, Android use numeric directly. SwiftUI maps to enum.

### Font Family

| Platform | Format | Variable font name |
|---|---|---|
| **IR (DB)** | **raw extracted name** | `"Inter Variable"` |
| Figma Plugin API | base name | `"Inter"` (not "Inter Variable") |
| CSS | font-family string | `"Inter"` (variable font registers as base name) |
| SwiftUI | Font.custom() string | `"Inter"` |
| Flutter | fontFamily string | `"Inter"` |

**IR stores raw extracted name for lossless round-trip.** Most renderers normalize `"Inter Variable"` → `"Inter"`. Figma Plugin API is specific: `loadFontAsync` requires exact registered name.

### Font Style (Figma-specific)

| Platform | Format | Example |
|---|---|---|
| **IR (DB)** | **raw style string or None** | `"Italic"` |
| Figma Plugin API | combined in fontName.style | `"Semi Bold Italic"` |
| CSS | separate `font-style: italic` | `font-style: italic` |
| SwiftUI | `.italic()` modifier | `.italic()` |
| Flutter | `fontStyle: FontStyle.italic` | separate enum |

**Figma is unique** in combining weight + style into one string (`"Semi Bold Italic"`). Every other platform separates weight and style.

### Layout Sizing

| Concept | IR | Figma | CSS | SwiftUI | Flutter | Android |
|---|---|---|---|---|---|---|
| Expand to parent | `"fill"` | `"FILL"` | `flex: 1` | `.frame(maxWidth: .infinity)` | `Expanded()` | `match_parent` |
| Shrink to content | `"hug"` | `"HUG"` | `width: auto` | default | default | `wrap_content` |
| Fixed pixels | numeric | `"FIXED"` + resize() | `width: Npx` | `.frame(width: N)` | `SizedBox(width: N)` | `Ndp` |

**IR stores semantic strings + pixel values.** Every platform has completely different syntax.

### Alignment

| Concept | IR | Figma | CSS | SwiftUI | Flutter |
|---|---|---|---|---|---|
| Start | `"start"` | `"MIN"` | `flex-start` | `.leading` | `.start` |
| Center | `"center"` | `"CENTER"` | `center` | `.center` | `.center` |
| End | `"end"` | `"MAX"` | `flex-end` | `.trailing` | `.end` |
| Space between | `"space-between"` | `"SPACE_BETWEEN"` | `space-between` | Spacers | `.spaceBetween` |

**IR stores semantic strings.** Each renderer maps to its own keywords.

### Line Height

| Platform | Format | Example | Notes |
|---|---|---|---|
| **IR (DB)** | **{value, unit} JSON** | `{"value": 24, "unit": "PIXELS"}` | |
| Figma Plugin API | same object format | `{value: 24, unit: "PIXELS"}` | Also supports `{unit: "AUTO"}` |
| CSS | unitless multiplier or px | `line-height: 1.5` or `24px` | Unitless preferred |
| SwiftUI | `.lineSpacing(N)` | `.lineSpacing(8)` | **Extra** spacing only, not total! |
| Flutter | height multiplier | `TextStyle(height: 1.5)` | Multiplier of fontSize |
| Android | absolute sp | `android:lineHeight="24sp"` | Also has `lineSpacingMultiplier` |

**IR stores {value, unit} object.** SwiftUI is a gotcha — `lineSpacing` is additive, not absolute.

### Letter Spacing

| Platform | Format | Example |
|---|---|---|
| **IR (DB)** | **{value, unit} JSON** | `{"value": 0.5, "unit": "PIXELS"}` |
| Figma Plugin API | same object format | `{value: 0.5, unit: "PIXELS"}` |
| CSS | px or em | `letter-spacing: 0.5px` |
| SwiftUI | points | `.tracking(0.5)` |
| Flutter | logical pixels | `letterSpacing: 0.5` |
| Android | **em** (relative to font size) | `android:letterSpacing="0.03"` |

**IR stores {value, unit} object.** Android is the oddball — uses em, not pixels.

### Constraints

| Platform | Concept | Format |
|---|---|---|
| **IR (DB)** | **REST API names** | `"LEFT"`, `"RIGHT"`, `"CENTER"`, `"LEFT_RIGHT"`, `"SCALE"` |
| Figma Plugin API | constraint types | `"MIN"`, `"MAX"`, `"CENTER"`, `"STRETCH"`, `"SCALE"` |
| CSS | absolute positioning | `position: absolute; left: 0; right: 0` |
| SwiftUI | no equivalent | alignment + frame modifiers |
| Flutter | Positioned in Stack | `Positioned(left: 0, right: 0)` |
| Android | ConstraintLayout | `constraintStart_toStartOf="parent"` |

**Each platform has a fundamentally different constraint model.** IR stores Figma REST API names; renderers translate to their own system.

### Visibility

| Platform | Hidden (no space) | Hidden (keeps space) |
|---|---|---|
| **IR (DB)** | **boolean false** | N/A |
| Figma Plugin API | `visible = false` | N/A |
| CSS | `display: none` | `visibility: hidden` |
| SwiftUI | conditional `if` | `.hidden()` |
| Flutter | `Visibility(visible: false)` | `Opacity(opacity: 0)` |
| Android | `visibility="gone"` | `visibility="invisible"` |

**IR stores boolean.** Android has three states; CSS splits across two properties.

## Summary: What Belongs Where

| Layer | What it stores | Format principle |
|---|---|---|
| **DB (L0)** | Raw extracted values | Lossless from source (REST API format) |
| **IR** | Ground truth values | Parsed JSON, int→bool. No renderer-specific transforms. |
| **Visual dict** | Renderer-agnostic properties | figma_name keys, raw values (hex colors, numeric weights, radians) |
| **Renderer** | Platform-specific output | Each renderer transforms from visual dict to its native format |

### Transforms that belong in each renderer (NOT in shared code)

| Transform | Figma | React/CSS | SwiftUI | Flutter |
|---|---|---|---|---|
| Rotation unit | rad→deg | rad→deg (or keep) | either | keep rad |
| Color format | hex→{r,g,b,a} | hex→rgba() | hex→Color() | hex→0xAARRGGBB |
| Font weight | numeric→style name | keep numeric | numeric→enum | keep numeric |
| Font family | normalize variable→base | normalize | normalize | normalize |
| Font style | combine into fontName.style | separate property | modifier | separate property |
| Alignment | "start"→"MIN" | "start"→"flex-start" | "start"→".leading" | "start"→".start" |
| Sizing | "fill"→"FILL" | "fill"→flex:1 | "fill"→.infinity | "fill"→Expanded |
| Line height | keep {value,unit} | convert to CSS | compute extra spacing | compute multiplier |
| Constraints | LEFT→MIN | LEFT→left:0 | custom layout | Positioned |
| Visibility | bool→JS true/false | bool→display:none | bool→if/else | bool→Visibility |
