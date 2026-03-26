---
taskId: TASK-072
title: "Implement mode creation with value seeding (UC-5)"
wave: wave-7
testFirst: false
testLevel: unit
dependencies: [TASK-004, TASK-002]
produces:
  - dd/modes.py
verify:
  - type: typecheck
    command: 'python -c "from dd.modes import create_mode, copy_values_from_default, apply_oklch_inversion, apply_scale_factor"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_modes.py -v'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-072: Implement mode creation with value seeding (UC-5)

## Spec Context

### From User Requirements Spec -- UC-5: Add Theme

> **Actor:** U1
> **Trigger:** User wants to add a theme (Dark, Compact, Brand B, High Contrast, etc.) to an existing curated token system.
> **Flow:**
> 1. User creates a new mode in the target collection(s) (e.g., "Dark" mode in the "Colors" collection, "Compact" mode in "Spacing").
> 2. System copies all curated token values from the default mode as starting points for the new mode.
> 3. User modifies mode-specific values -- either manually, via conversation with an agent, or via heuristic transforms (OKLCH lightness inversion for dark, scale factor for compact, brand color mapping for Brand B).
> 4. System validates mode completeness: every token in each affected collection has a value for every mode.
> 5. On export, `figma_setup_design_tokens` includes all modes in the payload.
> **Acceptance:**
> - Every token in each affected collection has exactly N values (one per mode).
> - Mode-specific values are independent -- changing Dark doesn't affect Light.
> - Adding a mode does not require re-extraction or re-binding -- it's a DB + Figma variable operation only.
> - Theme can span multiple collections (colors + effects + spacing) in a single operation.
> - A theme can include non-color properties: shadow intensity, border width, spacing scale, opacity values.

### From User Requirements Spec -- FR-2.8

> FR-2.8: Mode creation with value seeding. When adding a new mode, existing token values from the default mode are copied as starting points. Optional heuristic transforms (lightness inversion for dark mode, scale factor for compact mode) can be applied.

### From Technical Design Spec -- Phase 5: Multi-mode clustering

> When a user adds Dark mode later:
> a. System copies all curated token values from Default mode into the new Dark mode.
> b. System optionally applies a heuristic transform as a starting point -- for colors, invert lightness in OKLCH space (L -> 1-L), clamp chroma. This is a rough scaffold, not a solution. Real dark modes require curated adjustments.
> c. For spacing, radius, and typography: no transform by default (typically mode-independent). If density modes are needed, a scale factor can be applied.
> d. User reviews and adjusts all mode-specific values before export.

### From schema.sql -- token_modes table

> ```sql
> CREATE TABLE IF NOT EXISTS token_modes (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
>     figma_mode_id   TEXT,
>     name            TEXT NOT NULL,
>     is_default      INTEGER NOT NULL DEFAULT 0,
>     UNIQUE(collection_id, name)
> );
> ```

### From schema.sql -- token_values table

> ```sql
> CREATE TABLE IF NOT EXISTS token_values (
>     id              INTEGER PRIMARY KEY,
>     token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
>     mode_id         INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(token_id, mode_id)
> );
> ```

### From schema.sql -- tokens, token_collections tables

> ```sql
> CREATE TABLE IF NOT EXISTS tokens (
>     id              INTEGER PRIMARY KEY,
>     collection_id   INTEGER NOT NULL REFERENCES token_collections(id),
>     name            TEXT NOT NULL,
>     type            TEXT NOT NULL,
>     tier            TEXT NOT NULL DEFAULT 'extracted'
>                     CHECK(tier IN ('extracted', 'curated', 'aliased')),
>     alias_of        INTEGER REFERENCES tokens(id),
>     ...
>     UNIQUE(collection_id, name)
> );
>
> CREATE TABLE IF NOT EXISTS token_collections (
>     id              INTEGER PRIMARY KEY,
>     file_id         INTEGER NOT NULL REFERENCES files(id),
>     figma_id        TEXT,
>     name            TEXT NOT NULL,
>     ...
> );
> ```

### From dd/color.py (produced by TASK-004)

> Exports:
> - `hex_to_oklch(hex_color: str) -> tuple[float, float, float]` -- hex to (L, C, h)
> - `oklch_invert_lightness(L: float, C: float, h: float) -> tuple[float, float, float]` -- invert lightness, clamp chroma
> - `rgba_to_hex(r: float, g: float, b: float, a: float = 1.0) -> str`

### OKLCH Manual Conversion Formulas (for reverse conversion OKLCH -> hex)

> **OKLAB to XYZ (D65):**
> Reverse of the forward conversion. Given L, a, b (from OKLCH: a = C*cos(h_rad), b = C*sin(h_rad)):
>   l = L + 0.3963377774 * a + 0.2158037573 * b
>   m = L - 0.1055613458 * a - 0.0638541728 * b
>   s = L - 0.0894841775 * a - 1.2914855480 * b
>
>   l_ = l*l*l
>   m_ = m*m*m
>   s_ = s*s*s
>
>   X =  1.2270138511 * l_ - 0.5577999807 * m_ + 0.2812561490 * s_
>   Y = -0.0405801784 * l_ + 1.1122568696 * m_ - 0.0716766787 * s_
>   Z = -0.0763812845 * l_ - 0.4214819784 * m_ + 1.5861632204 * s_
>
> **XYZ to Linear RGB:**
>   R =  3.2404541621 * X - 1.5371385940 * Y - 0.4985314096 * Z
>   G = -0.9692660305 * X + 1.8760108454 * Y + 0.0415560175 * Z
>   B =  0.0556434310 * X - 0.2040259135 * Y + 1.0572251882 * Z
>
> **Linear RGB to sRGB:**
> For each channel c:
>   if c <= 0.0031308: srgb = 12.92 * c
>   else: srgb = 1.055 * c^(1/2.4) - 0.055
>
> Clamp each channel to [0, 1] before converting to 0-255 int.

### From dd/db.py (produced by TASK-002)

> Exports:
> - `get_connection(db_path: str) -> sqlite3.Connection`
> - `init_db(db_path: str) -> sqlite3.Connection`

## Task

Create `dd/modes.py` implementing mode creation with value seeding from UC-5. This module creates new modes in collections, copies values from the default mode, and optionally applies heuristic transforms (OKLCH lightness inversion for dark mode, scale factor for compact mode).

1. **`create_mode(conn, collection_id: int, mode_name: str) -> int`**:
   - INSERT into `token_modes` (collection_id, name=mode_name, is_default=0).
   - Raise `ValueError` if a mode with that name already exists in the collection (UNIQUE constraint).
   - Return the new mode_id.
   - Commit.

2. **`copy_values_from_default(conn, collection_id: int, new_mode_id: int) -> int`**:
   - Find the default mode for this collection: `SELECT id FROM token_modes WHERE collection_id = ? AND is_default = 1`.
   - If no default mode exists, raise `ValueError("No default mode found for collection")`.
   - Copy all token_values from the default mode to the new mode:
     ```sql
     INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
     SELECT tv.token_id, ?, tv.raw_value, tv.resolved_value
     FROM token_values tv
     JOIN tokens t ON tv.token_id = t.id
     WHERE tv.mode_id = ? AND t.collection_id = ? AND t.alias_of IS NULL
     ```
   - Use the new_mode_id for mode_id, default_mode_id for the source.
   - Skip aliased tokens (they reference the target's values).
   - Return the count of values copied.
   - Commit.

3. **`apply_oklch_inversion(conn, collection_id: int, mode_id: int) -> int`**:
   - For all color tokens in the collection with values in the given mode:
     - Query: `SELECT tv.id, tv.resolved_value, t.type FROM token_values tv JOIN tokens t ON tv.token_id = t.id WHERE tv.mode_id = ? AND t.collection_id = ? AND t.type = 'color'`
     - For each color value:
       - Convert hex to OKLCH via `hex_to_oklch`.
       - Invert lightness via `oklch_invert_lightness`.
       - Convert back to hex:
         - Try `coloraide` first:
           ```python
           try:
               from coloraide import Color
               c = Color('oklch', [new_L, new_C, h])
               c.fit('srgb')
               hex_val = c.convert('srgb').to_string(hex=True).upper()
           except ImportError:
               # manual conversion fallback
           ```
         - Manual fallback: OKLCH -> OKLAB -> XYZ -> Linear RGB -> sRGB -> hex using the formulas in Spec Context above.
       - UPDATE `token_values SET resolved_value = ?, raw_value = ? WHERE id = ?`.
   - Return count of values inverted.
   - Commit.

4. **`oklch_to_hex(L: float, C: float, h: float) -> str`**:
   - Internal helper to convert OKLCH back to hex string.
   - Try coloraide first, fall back to manual math.
   - Manual conversion pipeline:
     a. OKLCH to OKLAB: `a = C * cos(h_rad)`, `b = C * sin(h_rad)` where `h_rad = h * pi / 180`.
     b. OKLAB to LMS (cube): Use the inverse matrix from spec context.
     c. LMS cube to LMS: Cube each component.
     d. LMS to XYZ: Use the inverse matrix.
     e. XYZ to Linear RGB: Use the inverse matrix.
     f. Linear RGB to sRGB: Apply gamma.
     g. Clamp to [0, 1], convert to [0, 255], format as uppercase hex.
   - Return hex string like `#RRGGBB`.

5. **`apply_scale_factor(conn, collection_id: int, mode_id: int, factor: float) -> int`**:
   - For all dimension tokens in the collection with values in the given mode:
     - Query: `SELECT tv.id, tv.resolved_value, t.type FROM token_values tv JOIN tokens t ON tv.token_id = t.id WHERE tv.mode_id = ? AND t.collection_id = ? AND t.type = 'dimension'`
     - For each dimension value:
       - Parse the numeric value: `float(resolved_value)`.
       - Apply scale: `new_value = round(float(resolved_value) * factor)`.
       - UPDATE `token_values SET resolved_value = str(new_value), raw_value = json.dumps(new_value) WHERE id = ?`.
   - Skip non-numeric values (e.g., "AUTO").
   - Return count of values scaled.
   - Commit.

6. **`create_dark_mode(conn, collection_id: int, mode_name: str = "Dark") -> dict`**:
   - Convenience function combining create_mode, copy_values_from_default, and apply_oklch_inversion.
   - Call `create_mode(conn, collection_id, mode_name)` -> new_mode_id.
   - Call `copy_values_from_default(conn, collection_id, new_mode_id)` -> values_copied.
   - Call `apply_oklch_inversion(conn, collection_id, new_mode_id)` -> values_inverted.
   - Return: `{"mode_id": new_mode_id, "mode_name": mode_name, "values_copied": values_copied, "values_inverted": values_inverted}`.

7. **`create_compact_mode(conn, collection_id: int, factor: float = 0.875, mode_name: str = "Compact") -> dict`**:
   - Convenience function for compact/density mode.
   - Create mode, copy values, apply scale factor.
   - Return: `{"mode_id": new_mode_id, "mode_name": mode_name, "values_copied": values_copied, "values_scaled": values_scaled}`.

8. **`create_theme(conn, file_id: int, theme_name: str, collection_ids: list[int] | None = None, transform: str | None = None, factor: float = 1.0) -> dict`**:
   - High-level function to create a theme spanning multiple collections.
   - If `collection_ids` is None, apply to ALL collections for this file.
   - For each collection:
     - Create mode with `theme_name`.
     - Copy values from default.
     - If `transform == "dark"`: apply OKLCH inversion on color collections.
     - If `transform == "compact"`: apply scale factor on dimension collections.
     - If `transform` is None: just copy values (no transform).
   - Return: `{"theme_name": str, "collections_updated": int, "total_values_copied": int, "total_values_transformed": int}`.

## Acceptance Criteria

- [ ] `python -c "from dd.modes import create_mode, copy_values_from_default, apply_oklch_inversion, apply_scale_factor, create_dark_mode, create_compact_mode, create_theme, oklch_to_hex"` exits 0
- [ ] `create_mode` inserts a new mode row and returns its integer ID
- [ ] `create_mode` raises ValueError if mode name already exists in collection
- [ ] `copy_values_from_default` copies all token_values from the default mode to the new mode
- [ ] `copy_values_from_default` skips aliased tokens
- [ ] `copy_values_from_default` raises ValueError if no default mode exists
- [ ] `apply_oklch_inversion` inverts lightness of color token values in the specified mode
- [ ] `apply_oklch_inversion` only affects tokens with type='color'
- [ ] `oklch_to_hex` produces valid 6-digit hex strings (format #RRGGBB, uppercase)
- [ ] `oklch_to_hex(1.0, 0.0, 0.0)` produces a value close to `#FFFFFF` (white)
- [ ] `oklch_to_hex(0.0, 0.0, 0.0)` produces a value close to `#000000` (black)
- [ ] `apply_scale_factor` multiplies dimension values by the given factor
- [ ] `apply_scale_factor` skips non-numeric values like "AUTO"
- [ ] `create_dark_mode` creates mode, copies values, and inverts colors in one call
- [ ] `create_compact_mode` creates mode, copies values, and scales dimensions in one call
- [ ] `create_theme` handles multiple collections in a single operation
- [ ] After mode creation, every non-aliased token in the collection has a value for the new mode
- [ ] New mode values are independent from default mode values (modifying one doesn't affect the other)

## Notes

- The OKLCH inversion is a rough starting point for dark mode, not a polished solution. The TDS explicitly states: "Real dark modes require curated adjustments for shadows, elevation, borders, and contrast ratios."
- The `coloraide` library is preferred for OKLCH-to-hex conversion. The manual fallback formulas are provided in the spec context above. Both paths must produce valid hex output.
- The `oklch_to_hex` function may produce colors outside sRGB gamut after inversion. Clamp RGB channels to [0, 1] before converting to hex. If using coloraide, call `.fit('srgb')` to bring out-of-gamut colors into range.
- Scale factor for compact mode: 0.875 (7/8) reduces dimensions by 12.5%. Common alternatives: 0.75 (75%), 0.5 (50% for very dense). The user should adjust via the `factor` parameter.
- The `create_theme` function determines which transform to apply based on the collection content (colors get inversion, dimensions get scaling). If a collection has both color and dimension tokens, both transforms apply.