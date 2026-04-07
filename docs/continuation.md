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

## Current State (2026-04-06, Session 3)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes, 69,866 instance overrides (17 types), 182,871 bindings, 388 tokens, 338 screens
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Tests**: 1,621 passing
- **Branch**: `t5/architecture-vision`
- **Round-trip**: 9 screens reproduced (184, 185, 186, 188, 222, 238, 259, 253, 244) — 6 iPhone + 3 iPad
- **Property registry**: `dd/property_registry.py` — 48 scalar properties + JSON arrays (fills/strokes/effects), with per-renderer emit patterns

### What the Round-Trip Produces
- Real component instances via getNodeByIdAsync (L1 → Mode 1)
- Unpublished component fallback: getMainComponentAsync when registry has no figma_node_id
- Deep nested instance swaps at any depth (recursive CTE)
- 17 override types grouped by target (37-44% findOne reduction)
- Gradient fill emission through IR (GRADIENT_LINEAR/RADIAL/ANGULAR/DIAMOND)
- Progressive text fallback: L2 token → L0 DB value for fontSize/fontFamily/fontWeight
- Per-corner radius emission (topLeftRadius, etc.)
- Deferred position + constraints with canary verification
- Font normalization: family-aware style names (SF Pro → "Semibold", Inter → "Semi Bold")
- Table-driven emission: registry defines emit patterns per renderer, `emit_from_registry()` iterates them
- All 48 properties now emitted (was 31, 17 gap closed)
- Text properties: textAlignHorizontal/Vertical, textDecoration, textCase, lineHeight, letterSpacing, paragraphSpacing, fontStyle
- Layout properties: counterAxisSpacing, layoutWrap, layoutPositioning
- Size constraints: minWidth, maxWidth, minHeight, maxHeight
- Visual properties: strokeAlign, dashPattern
- Execution: 0.7-3.9s per screen (warm cache)

### Property Registry — Fully Registry-Driven (COMPLETED Sessions 3-4)

The registry now drives ALL 5 pipeline stages: extraction, query, overrides, visual builder, AND emission. Three emission categories:

- **Template**: `emit={"figma": "{var}.{figma_name} = {value};"}` — uniform format, type-aware via `format_js_value()`
- **Handler**: `emit={"figma": HANDLER}` — dispatched to `_FIGMA_HANDLERS[figma_name]` (fills, strokes, effects, cornerRadius, clipsContent)
- **Deferred**: `emit={}` — emitted in a different pipeline phase (constraints, visible, width/height, layoutSizing, fontName)

`build_visual_from_db` is registry-driven — iterates PROPERTIES, applies `_apply_db_transform` (radians→degrees, int→bool, JSON parse), bundles text into font dict, constraints into constraints dict. No manual property list to maintain.

`_emit_visual` is a single delegation to `emit_from_registry`. Structural tests enforce every property is classified as template/handler/deferred with no gaps.

## Remaining Issues

### Issue 3: Image Fills — NOT YET ADDRESSED

IMAGE fills render as gray rectangles. Requires:
1. Plugin API extraction: `figma.getImageByHash(hash).getBytesAsync()`
2. New `image_data` table (hash → bytes)
3. Rendering: `figma.createImage(bytes)`

65 image fills across 9 target screens.

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
  + emit: { "figma": '{var}.strokeAlign = "{value}";' }
  Used by: extraction ✅, query ✅, overrides ✅, emission ✅
```

Simple properties use string templates with `{var}`/`{value}` placeholders. Complex properties (fills, strokes, effects, cornerRadius, fontName) use `emit={"figma": None}` and are handled by custom emit functions.

The `emit_from_registry(var, visual, renderer="figma")` helper iterates all registry entries, applies matching templates, and returns JS lines. `_emit_visual` delegates to this helper for all simple properties, keeping only `clipsContent` (boolean true/false special case) and complex properties as custom logic.

A structural coverage test (`tests/test_property_registry.py::TestRegistryEmitCoverage`) verifies every registry property has an emit pattern for the "figma" renderer, excluding explicitly deferred properties (constraints, width/height, layoutSizing).

## Key Architectural Decisions

1. **Progressive fallback** (L2→L1→L0) — renderers read highest level available
2. **LEFT JOIN on L1** — all nodes enter IR, L1/L2 as annotations
3. **Deferred position + constraints** — set after all children appended, with canary verification
4. **Override grouping by target** — one findOne per unique child_id, 37-44% reduction
5. **Self-overrides** — `:self` marker for overrides targeting the instance itself
6. **Pre-fetch preamble** — deduplicated `getNodeByIdAsync` calls
7. **Override hoisting** — nested Mode 1 overrides transformed and hoisted to ancestor
8. **Default clearing** — fills=[], clipsContent=false to override Figma's createFrame() defaults
9. **Gradient enrichment** — supplement adds gradientTransform alongside REST API handlePositions. ORDERING: supplement must run AFTER REST extraction. If REST re-runs after supplement, enrichment is lost.
10. **Unpublished component fallback** — component_figma_id → instance figma_node_id + getMainComponentAsync → Mode 2 createFrame
11. **Progressive text fallback** — `_resolve_text_value()`: L2 token → resolved value → L0 DB value
12. **Font normalization** — `normalize_font_style(family, style)`: per-family style names
13. **Table-driven emission** (COMPLETED) — HANDLER sentinel + uniform templates + `format_js_value()` type-aware formatting, `emit_from_registry()` dispatches handlers and applies templates, `build_visual_from_db` is registry-driven, structural tests enforce template/handler/deferred classification

## Key Files

| File | Purpose |
|------|---------|
| `dd/property_registry.py` | **Single source of truth** for 48 Figma properties (emission extension planned) |
| `dd/ir.py` | IR generation, registry-driven query_screen_visuals |
| `dd/generate.py` | Figma renderer — override grouping, gradient emission, text fallback |
| `dd/extract_supplement.py` | Registry-driven override + gradient + textAutoResize extraction |
| `dd/extract_screens.py` | Plugin API node extraction |
| `docs/compiler-architecture.md` | Authoritative architecture spec |
| `schema.sql` | DB schema (72 columns + instance_overrides) |

## Environment

```bash
source .venv/bin/activate
python -m pytest tests/ --tb=short          # 1,573 tests
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
