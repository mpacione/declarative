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

## Current State (2026-04-06, Session 2)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes, 69,866 instance overrides (17 types), 182,871 bindings, 388 tokens, 338 screens
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Tests**: 1,573 passing
- **Branch**: `t5/architecture-vision`
- **Round-trip**: 9 screens reproduced (184, 185, 186, 188, 222, 238, 259, 253, 244) — 6 iPhone + 3 iPad
- **Property registry**: `dd/property_registry.py` — 48 scalar properties + JSON arrays (fills/strokes/effects)

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
- Execution: 0.7-3.9s per screen (warm cache)

### Property Registry — Current Limitation

The registry currently drives extraction, query, and override dispatch — but **NOT emission**. The emit functions (`_emit_layout`, `_emit_visual`, `_emit_text_props`) each maintain their own hardcoded property lists that don't reference the registry. This is why 17 of 48 properties are extracted but never emitted.

**Next step**: Extend the registry to drive emission (table-driven code generation). See "Planned: Table-Driven Emission" below.

## Remaining Issues

### Issue 3: Image Fills — NOT YET ADDRESSED

IMAGE fills render as gray rectangles. Requires:
1. Plugin API extraction: `figma.getImageByHash(hash).getBytesAsync()`
2. New `image_data` table (hash → bytes)
3. Rendering: `figma.createImage(bytes)`

65 image fills across 9 target screens.

### 17 Properties Extracted But Not Emitted

Cross-reference analysis identified 17 properties that flow through extraction → DB → query but are never emitted by the Figma renderer:

**LAYOUT (3)**: `counterAxisSpacing`, `layoutWrap`, `layoutPositioning`
**TEXT (8)**: `textAlignHorizontal`, `textAlignVertical`, `textDecoration`, `textCase`, `lineHeight`, `letterSpacing`, `paragraphSpacing`, `fontStyle`
**SIZE (4)**: `minWidth`, `maxWidth`, `minHeight`, `maxHeight`
**VISUAL (2)**: `strokeAlign`, `dashPattern`

Root cause: Each emit function independently decides which properties to handle. The registry prevents gaps at the extraction/query/override layers but has no connection to the emission layer.

**Fix**: Table-driven emission — extend the registry with emit patterns so the renderer reads from the table instead of maintaining ad-hoc lists.

### Gradient Fills — Partially Resolved

The emit code handles gradients, and supplement extraction captures `gradientTransform`. However:
- 2,338 nodes now have `gradientTransform` in the DB (after supplement re-run)
- 29 screens failed supplement extraction (complex screens hitting Plugin API limits)
- Gradient fills on those 29 screens remain without `gradientTransform`

### textAutoResize — Extraction Gap

Supplement extraction now captures `textAutoResize` from Plugin API. But the DB has not been fully re-extracted — most TEXT nodes still have NULL. Requires supplement re-run.

## Planned: Table-Driven Emission (Next Session)

The property registry should drive ALL pipeline stages, including emission. Currently it drives 3 of 4:

```
FigmaProperty today:
  figma_name → db_column → override_fields → value_type → override_type
  Used by: extraction ✅, query ✅, overrides ✅, emission ❌
```

The plan (inspired by LLVM TableGen):

```
FigmaProperty extended:
  figma_name → db_column → override_fields → value_type → override_type
  + emit: { "figma": pattern_or_fn, "react": pattern_or_fn, "swift": pattern_or_fn }
```

For simple properties (most of the 17 gaps), the emit pattern is a string template:
```python
emit={"figma": '{var}.{figma_name} = "{value}";'}
```

For complex properties (fills, fontName, cornerRadius), the emit field references a custom function:
```python
emit={"figma": emit_fills_figma}
```

Benefits:
- Adding a property → all renderers automatically emit it
- Adding a renderer → it reads all existing properties from the table
- No M×N gap possible — the table IS the source of truth
- Cross-reference test verifies every property has an emit pattern for every registered renderer

This is the architectural equivalent of LLVM's TableGen: instruction descriptions defined once, backends generated from them.

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
13. **Table-driven emission** (PLANNED) — registry defines emit patterns per renderer, eliminates hardcoded property lists

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
