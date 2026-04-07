# Continuation: Next Session

## What This Project Is

Declarative Design is a **design system compiler** — the LLVM of design. It compiles design artifacts between any source (Figma, React, SwiftUI, prompts) and any target through a multi-level intermediate representation. Like LLVM compiles C/Rust/Swift to x86/ARM/WASM through one IR, this system compiles Figma/React/SwiftUI to Figma/React/SwiftUI — bidirectionally, with design token fidelity.

The IR has four levels (MLIR-inspired, each adds information, none removes):
- **L0**: DB `nodes` table (72 columns, parent_id tree) — complete lossless scene graph
- **L1**: `screen_component_instances` table — semantic type annotations ("this FRAME is a button")
- **L2**: `node_token_bindings` table — design token references ("this padding is {space.lg}")
- **L3**: Semantic tree — compact YAML (~20 elements per screen, for LLMs and cross-platform)

The IR exists to solve the **M×N problem**: without it, 5 frontends × 5 backends = 25 translators each reimplementing classification, token binding, and semantic understanding. With the IR, analysis is written once (compiler passes) and shared by all renderers.

**Authoritative spec**: `docs/compiler-architecture.md`

## What We're Testing: The Round-Trip

The round-trip (Figma → DB → Figma) is the existential proof that the compiler works. If we can't faithfully reproduce a screen from our own database, the data is untrustworthy and everything downstream inherits those errors.

Every renderer uses **progressive fallback**: read the highest IR level available, fall back to lower levels for missing data. L0 is always the safety net.

## Current State (2026-04-07, Session 5)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes, 69,866 instance overrides (42 types), 182,871 bindings, 388 tokens, 338 screens
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Tests**: 1,657 passing
- **Cross-platform reference**: `docs/cross-platform-value-formats.md` — value formats for Figma, CSS, SwiftUI, Flutter, Android
- **Branch**: `t5/architecture-vision`
- **Round-trip**: 9+ screens reproduced (184, 185, 186, 188, 222, 238, 259, 253, 244, 172, 317) — iPhone + iPad
- **Property registry**: `dd/property_registry.py` — 48 properties with per-renderer emit patterns (HANDLER/template/deferred)
- **textAutoResize**: 12,114 of 13,279 TEXT nodes (91% coverage)
- **gradientTransform**: 2,784 gradient fills (234 remaining on 3 screens)

### What the Round-Trip Produces
- Real component instances via getNodeByIdAsync (L1 → Mode 1)
- Unpublished component fallback: getMainComponentAsync when registry has no figma_node_id
- Deep nested instance swaps at any depth (recursive CTE)
- 42 override types decomposed at query time, grouped by target
- All override types correctly applied including self-targeting (cornerRadius, effects, strokes, padding — previously 33 types silently dropped)
- Gradient fill emission through IR (GRADIENT_LINEAR/RADIAL/ANGULAR/DIAMOND)
- Progressive text fallback: L2 token → L0 DB value for fontSize/fontFamily/fontWeight
- Per-corner radius emission (topLeftRadius, etc.)
- Deferred position + constraints with canary verification, DB-first position fallback
- Font normalization: family-aware style names (SF Pro → "Semibold", Inter → "Semi Bold")
- Registry-driven emission: `emit_from_registry()` dispatches HANDLER + template properties
- Registry-driven `build_visual_from_db`: no manual property list
- All 48 properties emitted, all 42 override types applied
- Text properties: textAlignHorizontal/Vertical, textDecoration, textCase, lineHeight, letterSpacing, paragraphSpacing, fontStyle
- Layout properties: counterAxisSpacing, layoutWrap, layoutPositioning
- Size constraints: minWidth, maxWidth, minHeight, maxHeight
- Visual properties: strokeAlign, dashPattern

### Property Registry — Fully Registry-Driven (COMPLETED Sessions 3-4)

The registry drives ALL pipeline stages: extraction, query, overrides, visual builder, emission, AND override application. Three emission categories:

- **Template**: `emit={"figma": "{var}.{figma_name} = {value};"}` — uniform format, type-aware via `format_js_value()`
- **Handler**: `emit={"figma": HANDLER}` — dispatched to `_FIGMA_HANDLERS[figma_name]` (fills, strokes, effects, cornerRadius, clipsContent)
- **Deferred**: `emit={}` — emitted in a different pipeline phase (constraints, visible, width/height, layoutSizing, fontName)

`build_visual_from_db` is registry-driven — iterates PROPERTIES, applies `_apply_db_transform` (radians→degrees, int→bool, JSON parse). `_emit_visual` is a single delegation to `emit_from_registry`. `_emit_override_op` uses `format_js_value` for generic properties.

### Override Decomposition (COMPLETED Session 4)

Overrides are decomposed at query time in `query_screen_visuals` from composite `{target}{suffix}` to structured `{target, property, value}`. The decomposition uses `override_suffix_for_type()` from `extract_supplement.py` — the same suffix knowledge that created the composite string during extraction. No second suffix map to maintain.

Previously, `_OVERRIDE_SUFFIX_MAP` (7 entries) + a registry fallback failed for 33 of 42 override types when self-targeting. Self-targeting overrides for cornerRadius, effects, strokes, padding, and 29 other types were silently dropped. Now all 42 types are correctly applied.

## Remaining Issues

### Issue 3: Image Fills — NOT YET ADDRESSED

IMAGE fills render as gray rectangles. 877 IMAGE fills across 204 screens, only 17 unique image hashes. For same-file reproduction, `figma.getImageByHash(imageRef)` should work directly since images already exist in the file. For cross-file, requires byte extraction and `figma.createImage(bytes)`.

### 17 Properties Emission Gap — RESOLVED (Session 3)

All 17 properties that were previously extracted but not emitted are now emitted:

**LAYOUT (3)**: `counterAxisSpacing`, `layoutWrap`, `layoutPositioning` — via `build_visual_from_db` + `emit_from_registry`
**TEXT (8)**: `textAlignHorizontal`, `textAlignVertical`, `textDecoration`, `textCase`, `lineHeight`, `letterSpacing`, `paragraphSpacing`, `fontStyle` — via `_emit_text_props` (progressive fallback from db_font)
**SIZE (4)**: `minWidth`, `maxWidth`, `minHeight`, `maxHeight` — via `build_visual_from_db` + `emit_from_registry`
**VISUAL (2)**: `strokeAlign`, `dashPattern` — via `build_visual_from_db` + `emit_from_registry`

The fix has two layers: (1) `build_visual_from_db` now passes through all 17 properties, (2) `_emit_visual` delegates to `emit_from_registry()` which reads emit patterns from the property registry. The structural test in `tests/test_property_registry.py` ensures no future property can be added without an emit pattern.

### Gradient Fills — Mostly Resolved (Session 3)

Full supplement re-extraction via PROXY_EXECUTE (204/204 screens, 0 failures):
- 2,784 nodes now have `gradientTransform` (up from 2,340)
- Only 234 gradient fills remain without gradientTransform (across 3 screens)
- Remaining gaps are likely inherited fills from component instances where the Plugin API doesn't expose gradientTransform on the override

### textAutoResize — Resolved (Session 3)

Full supplement re-extraction captured textAutoResize for 12,114 of 13,279 TEXT nodes (91% coverage, up from 1). The remaining 1,165 are likely inherited TEXT nodes inside component instances.

## Table-Driven Emission — COMPLETED (Session 3)

The property registry now drives ALL 4 pipeline stages:

```
FigmaProperty:
  figma_name → db_column → override_fields → value_type → override_type
  + emit: { "figma": HANDLER } or { "figma": "{var}.{figma_name} = {value};" }
  Used by: extraction ✅, query ✅, overrides ✅, visual builder ✅, emission ✅
```

Three categories: HANDLER (callable dispatch for fills/strokes/effects/cornerRadius/clipsContent), template (uniform `{var}.{figma_name} = {value};` with type-aware `format_js_value`), deferred (empty dict — constraints, visible, width/height, layoutSizing, fontName). `emit_from_registry` dispatches both handlers and templates. `_emit_override_op` reuses `format_js_value` for generic override application.

## Key Architectural Decisions

1. **Progressive fallback** (L2→L1→L0) — renderers read highest level available
2. **LEFT JOIN on L1** — all nodes enter IR, L1/L2 as annotations
3. **Deferred position + constraints** — set after all children appended, with canary verification
4. **Override decomposition at query time** — composite `{target}{suffix}` split into `{target, property, value}` using `override_suffix_for_type()` from the same source that created the composite. No second suffix map. All 42 override types correctly handled.
5. **Self-overrides** — `:self` marker for overrides targeting the instance itself. Decomposition ensures self-targeting overrides group correctly regardless of property type.
6. **Pre-fetch preamble** — deduplicated `getNodeByIdAsync` calls
7. **Override hoisting** — nested Mode 1 overrides transformed and hoisted to ancestor
8. **Default clearing** — fills=[], clipsContent=false to override Figma's createFrame() defaults
9. **Gradient enrichment** — supplement adds gradientTransform alongside REST API handlePositions. ORDERING: supplement must run AFTER REST extraction. If REST re-runs after supplement, enrichment is lost.
10. **Unpublished component fallback** — component_figma_id → instance figma_node_id + getMainComponentAsync → Mode 2 createFrame
11. **Progressive text fallback** — `_resolve_text_value()`: L2 token → resolved value → L0 DB value
12. **Font normalization** — `normalize_font_style(family, style)`: per-family style names
13. **Table-driven emission** (COMPLETED) — HANDLER sentinel + uniform templates + `format_js_value()` type-aware formatting, `emit_from_registry()` dispatches handlers and applies templates, `build_visual_from_db` is registry-driven, structural tests enforce template/handler/deferred classification
14. **Override decomposition at query time** (COMPLETED) — `decompose_override()` splits composite `property_name` into `(target, property)` using `override_suffix_for_type()`. `_emit_override_op` uses `format_js_value` for generic properties. `_OVERRIDE_SUFFIX_MAP` and `_resolve_override_target` deleted.
15. **DB-first position fallback** (COMPLETED) — deferred positioning prefers DB `x`/`y` from `query_screen_visuals` over IR `element.layout.position`

## Key Files

| File | Purpose |
|------|---------|
| `dd/property_registry.py` | **Single source of truth** for 48 properties — HANDLER/template/deferred emit, db_column mapping |
| `dd/ir.py` | IR generation, registry-driven query_screen_visuals, override decomposition |
| `dd/generate.py` | Figma renderer — registry-driven emission, `_resolve_layout_sizing`, `format_js_value`, `hex_to_figma_rgba` |
| `dd/extract_supplement.py` | Registry-driven override extraction, `override_suffix_for_type` |
| `dd/extract_screens.py` | Plugin API node extraction |
| `docs/compiler-architecture.md` | Authoritative architecture spec (includes renderer value transforms) |
| `docs/cross-platform-value-formats.md` | Cross-platform property format reference (Figma, CSS, SwiftUI, Flutter, Android) |
| `schema.sql` | DB schema (72 columns + instance_overrides + figma_node_id index) |

## Environment

```bash
source .venv/bin/activate
python -m pytest tests/ --tb=short          # 1,656 tests
```

## Reference Screens

| Screen | Name | Figma Node | Nodes | Execution | Status |
|--------|------|-----------|-------|-----------|--------|
| 184 | iPhone 13 Pro Max - 8 | 2244:146076 | 203 | 0.7s | Good — fonts, positions, components correct |
| 185 | iPhone 13 Pro Max - 114 | 2265:102114 | 225 | 0.9s | Good — Share/Save/Export panel |
| 186 | iPhone 13 Pro Max - 21 | 2244:146096 | 203 | 0.8s | Good — image placeholder |
| 188 | iPhone 13 Pro Max - 110 | 2244:146231 | 366 | 1.6s | Gallery — wrap layout not emitted, images gray |
| 222 | iPhone 13 Pro Max - 86 | 2244:148249 | 303 | 2.3s | Border Size — text sizes fixed, gradients pending |
| 238 | iPhone 13 Pro Max - 79 | 2244:149329 | 417 | 2.4s | Color picker — wrap layout not emitted |
| 259 | iPad Pro 12.9" - 38 | 2255:76230 | 422 | 2.6s | iPad — unpublished component fallback works |
| 253 | iPad Pro 12.9" - 35 | 2255:73824 | 463 | 3.9s | iPad — text sizes fixed |
| 244 | iPad Pro 12.9" - 40 | 2255:77763 | 624 | 3.0s | iPad — largest screen, keyboard |
