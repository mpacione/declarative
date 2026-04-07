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

## Current State (2026-04-07, Session 7)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes (74 columns), 69,866 instance overrides (42 types), 182,871 bindings, 388 tokens, 338 screens
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Tests**: 1,747 passing
- **Cross-platform reference**: `docs/cross-platform-value-formats.md` — value formats for Figma, CSS, SwiftUI, Flutter, Android
- **Branch**: `compiler/multi-backend-architecture`
- **Round-trip**: 11+ screens reproduced (184, 185, 186, 188, 222, 238, 259, 253, 244, 172, 317) — iPhone + iPad
- **Property registry**: `dd/property_registry.py` — 48 properties with per-renderer emit patterns (HANDLER/template/deferred) + `token_binding_path` for binding awareness
- **Asset registry**: `dd/extract_assets.py` — content-addressed store for raster + SVG assets, `AssetResolver` ABC
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

## Session 6 Fixes (2026-04-07) — Visual Fidelity Stress Test

Four root causes identified and resolved:

### Issue D: Rotation Sign + AABB Dimensions — RESOLVED (`243507b`)
REST API provides rotation in radians; Plugin API expects degrees with opposite sign. Fixed `format_js_value()` to negate: `-math.degrees(value)`. Also fixed Mode 1 instance rotation path. Added `_reconstruct_logical_dimensions()` to convert axis-aligned bounding box back to pre-rotation dimensions via trigonometric inversion.

### Issue B: Layout Sizing Extraction — RESOLVED (`405bf0f`)
`layoutSizingH`/`layoutSizingV` were gated behind `layoutMode != NONE`, dropping sizing for children of auto-layout parents that don't have their own layout. Moved extraction before the early return. Added `layoutWrap` default to `NO_WRAP` when REST API omits it. Migration `007_layout_defaults_backfill.sql`.

### Issue A: Token Binding Resolution — RESOLVED (`e83d3fc`)
Registry-driven approach: added `token_binding_path` field to `FigmaProperty`. `build_visual_from_db()` populates `_token_refs` sidecar dict from bindings. `emit_from_registry()` collects refs for variable rebinding. Anti-fragile: new properties get binding support by adding one field.

### Issue C: Asset Registry — RESOLVED (`3db082b` + `594e2ee` + `d4944e0`)
Full content-addressed asset pipeline:
- **Schema**: `assets` + `node_asset_refs` tables (migration 008)
- **IR**: IMAGE branch in `normalize_fills()`, `_asset_refs` in `query_screen_visuals()`
- **Extraction**: `fillGeometry`/`strokeGeometry` from both REST + Plugin APIs (migration 009)
- **Processing**: `process_vector_geometry()` hashes SVG paths, stores as `svg_path` assets
- **Rendering**: VECTOR/BOOLEAN_OPERATION render via `createVector()` + `vectorPaths`; IMAGE fills emit `imageHash` paint
- **Abstraction**: `AssetResolver` ABC with `SqliteAssetResolver` implementation

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
15. **Position from IR** (COMPLETED) — deferred positioning reads parent-relative coordinates from IR (DB stores absolute canvas coordinates). See compiler-architecture.md Section 4.1.
16. **Renderer architecture split** (COMPLETED) — `dd/generate.py` split into `dd/visual.py` (shared, 210 lines) + `dd/renderers/figma.py` (Figma-specific, 1,294 lines) + re-export wrapper. LLVM/Mitosis/Style Dictionary pattern: shared IR → per-target backend.
17. **Override tree** (COMPLETED) — Flat `instance_overrides` + `child_swaps` replaced with nested `override_tree` in visual dict. Tree nesting encodes dependency ordering (swaps before descendant overrides). Pre-order traversal gives correct imperative ordering. Override dependencies are semantic, owned by the IR.
18. **System chrome is design content** (COMPLETED) — Keyboards, status bars, Safari chrome are intentional design content. Only platform implementation artifacts (Figma internal spacers with parenthesized names) are synthetic and filtered.

## Key Files

| File | Purpose |
|------|---------|
| `dd/property_registry.py` | **Single source of truth** for 48 properties — HANDLER/template/deferred emit, db_column mapping, token_binding_path |
| `dd/visual.py` | **Shared infrastructure** (renderer-agnostic) — `build_visual_from_db`, `_resolve_layout_sizing`, `resolve_style_value`, `_token_refs` sidecar |
| `dd/renderers/figma.py` | **Figma renderer** — JS emission, `hex_to_figma_rgba`, `font_weight_to_style`, `format_js_value`, `emit_from_registry`, vector/image rendering |
| `dd/extract_assets.py` | **Asset pipeline** — image hash extraction, asset CRUD, vector geometry processing, `AssetResolver` ABC + `SqliteAssetResolver` |
| `dd/generate.py` | Backward-compatible re-exports (thin wrapper — import from `dd.visual` or `dd.renderers.figma` directly) |
| `dd/ir.py` | IR generation, registry-driven query_screen_visuals (incl. _asset_refs), override decomposition |
| `dd/figma_api.py` | REST API extraction — node conversion, AABB→logical dimension reconstruction, fillGeometry/strokeGeometry |
| `dd/extract_supplement.py` | Registry-driven override extraction, `override_suffix_for_type` |
| `dd/extract_screens.py` | Plugin API node extraction (incl. vector geometry) |
| `docs/compiler-architecture.md` | Authoritative architecture spec (includes renderer value transforms) |
| `docs/cross-platform-value-formats.md` | Cross-platform property format reference (Figma, CSS, SwiftUI, Flutter, Android) |
| `schema.sql` | DB schema (74 columns + instance_overrides + assets + node_asset_refs) |

## Environment

```bash
source .venv/bin/activate
python -m pytest tests/ --tb=short          # 1,747 tests
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

## Session 7 — Visual Fidelity Stress Test Batch 2 (2026-04-07)

### Screen Naming Fix
Root frame in generated scripts now uses actual screen name (e.g., "iPhone 13 Pro Max - 79") instead of "screen-1". Fixed by propagating `screen_name` from `query_screen_for_ir` data through `build_composition_spec` as `_original_name` on the root screen element. The renderer already reads `_original_name` — no renderer changes needed.

### Rendered Screens
10 screens rendered on "Round-Trip Stress Test" page via PROXY_EXECUTE (port 9230):
- Batch 1: 184, 185, 186, 150, 118
- Batch 2: 238 (color picker), 237, 232, 244 (iPad, 624 nodes), 209

### Three Systemic Issues Identified

**Issue 1: Masked Images Not Rendering (Frame 413, Screen 209)**
Root cause: `isMask` not part of the pipeline. Not extracted, not stored, not emitted. GROUP nodes unconditionally skipped via `_SKIP_NODE_TYPES`. Mask groups and all their children (mask shape + masked content) are discarded entirely.

**Issue 2: Auto Layout Spacer Visible (Frame 275, Screen 209)**
Root cause: 132 Figma-internal nodes (`(Auto Layout spacer)`, `(Adjust Auto Layout Spacing)`) extracted and rendered as real rectangles. `createRectangle()` applies default grey fill. No filtering at any pipeline stage catches parenthesized-name internal nodes.

**Issue 3: Vector Icon Wrong Color in Toolbar (Screen 209)**
Root cause: Override ordering bug. Instance swap on a child icon emitted AFTER strokes override on the icon's nested vector. `swapComponent()` replaces the subtree, destroying the overridden vector. New icon gets default colors. Caused by `instance_overrides` (from DB) being grouped before `child_swaps` (appended after) in an `OrderedDict` with insertion-order iteration.

### Fix 2: Synthetic Node Filtering — COMPLETE
New `is_synthetic_node(name)` in `dd/classify_rules.py` detects parenthesized Figma internal names: `(Auto Layout spacer)`, `(Adjust Auto Layout Spacing)`. `build_composition_spec()` in `dd/ir.py` filters synthetic nodes and their children (transitive closure). 132 nodes affected (66 spacers + 66 spacing adjusters). L0 stays lossless — nodes remain in DB, filtering at IR spec boundary only.

**Key distinction**: System chrome (iOS status bars, keyboards, Safari chrome) is **design content**, NOT synthetic. Designers place these intentionally. Only platform IMPLEMENTATION artifacts (Figma internal spacers) are synthetic. `is_synthetic_node()` must NOT match system chrome patterns.

### Fix 1: Override Tree — COMPLETE
New `build_override_tree(instance_overrides, child_swaps)` in `dd/ir.py` converts flat override lists + child_swaps into a nested tree structure. Tree nesting encodes dependency ordering — swaps before descendant property overrides. `query_screen_visuals()` builds the tree after hoisting, stores as `override_tree` in visual dict. Old `instance_overrides` and `child_swaps` keys replaced by single `override_tree`.

New `_emit_override_tree()` in `dd/renderers/figma.py`: recursive pre-order walk. New `_collect_swap_targets_from_tree()` for pre-fetch preamble. Pre-order traversal = correct ordering for imperative renderers; direct mapping for declarative renderers. Override dependencies are semantic (component slot tree), not renderer-specific — the IR owns the nesting structure.

### Fix 3: L0 Completeness — REMAINING
Phase A: Mask support (is_mask column, extract from both APIs, emit in renderer, stop unconditionally skipping GROUPs). Phase B: Missing properties (booleanOperation, cornerSmoothing, arcData). Phase C: Structural completeness test against canonical Figma property list.

### Test Count: 1,747 passing
