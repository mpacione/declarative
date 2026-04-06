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

## Current State (2026-04-06)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes, 69,866 instance overrides (17 types), 182,871 bindings, 388 tokens, 338 screens
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Tests**: 1,530 passing
- **Branch**: `t5/architecture-vision`
- **Round-trip**: Screens 184, 185, 188, 238 reproduced with structural fidelity
- **Property registry**: `dd/property_registry.py` — single source of truth for 58 Figma properties

### What the Round-Trip Produces
- Real component instances via getNodeByIdAsync (L1 → Mode 1)
- Deep nested instance swaps at any depth (recursive CTE)
- 17 override types: visibility, fills, strokes, effects, corner radius, instance swaps, width, height, opacity, layout sizing, item spacing, padding, primary alignment, stroke weight/align, text
- 12 token variable bindings (L2 → live Figma variables)
- Deferred position + constraints (handles HUG+CENTER recalculation)
- Pre-fetched component node IDs (deduplicated async calls)
- Default clearing: fills=[], clipsContent=false for non-default Figma defaults
- Mode 1 L0 properties: rotation (radians→degrees), opacity, visibility
- blendMode, strokeCap, strokeJoin emission

### Property Registry (dd/property_registry.py)

Single source of truth for all 58 Figma properties. Each property maps:
- Figma Plugin API name → DB column → override field name(s) → value type → override type

Used by:
- **extract_supplement.py**: generates JS override checks from registry (40+ properties checked)
- **ir.py**: `query_screen_visuals()` SELECT built from registry (51 columns)
- **generate.py**: generic override handler dispatches via registry

This prevents the "extract it, forget to query it, forget to emit it" pattern that caused every bug in this session.

## Remaining Issues

### Issue 11: PROXY_EXECUTE Deferred Position Reliability — NOT YET RESOLVED

Generated scripts are structurally correct (zero crash points), but deferred position+constraint lines intermittently fail to apply. Some executions return SUCCESS but all children remain at x=0, y=0. No correlation with script size — 80KB scripts work while 33KB scripts fail.

**Hypothesis**: PROXY_EXECUTE WebSocket might have a timeout or message ordering issue where the script's return value (M object) is sent before all deferred lines complete. Or the Figma plugin runtime has an execution time limit that silently truncates.

**Investigation needed**: Add a canary check at the end of the deferred section (e.g., set a property on the root node) and verify whether it was set. This would confirm whether the deferred section executed.

### Issue 3: Image Fills — NOT YET ADDRESSED

`image 319` (background RECTANGLE) is created but has no image fill. Requires:
1. Plugin API extraction: `figma.getImageByHash(hash).getBytesAsync()`
2. New `image_data` table (hash → bytes)
3. Rendering: `figma.createImage(bytes)`

### Issue 4: Performance

Scripts take ~90-120s due to `findOne` tree searches for each override/swap. Optimizations:
- Filter swaps to only those differing from master defaults
- Batch `findOne` operations
- Direct child indexing instead of tree search

### Issue 12: Font Name Normalization

"Semi Bold" vs "Semibold" varies by font family (Inter uses space, SF Pro doesn't). Currently handled by string replacement in generated scripts. Needs a systematic font style mapping.

## Key Architectural Decisions

1. **Progressive fallback** (L2→L1→L0) — renderers read highest level available
2. **LEFT JOIN on L1** — all nodes enter IR, L1/L2 as annotations
3. **Deferred position + constraints** — set after all children appended
4. **Two-source swaps** — instance_overrides + recursive CTE, deduplicated
5. **Self-overrides** — `:self` marker for overrides targeting the instance itself
6. **Pre-fetch preamble** — deduplicated `getNodeByIdAsync` calls
7. **Override hoisting** — nested Mode 1 overrides transformed and hoisted to ancestor
8. **Default clearing** — fills=[], clipsContent=false to override Figma's createFrame() defaults
9. **Layout sizing deferral** — non-auto-layout children set layoutSizing after appendChild; auto-layout containers set their own before
10. **Radians→degrees** — DB stores radians (REST API), renderer converts
11. **Mode 1 L0 properties** — rotation, opacity, visibility applied after createInstance()
12. **Property registry** — single source of truth for all pipeline layers
13. **Generic override handler** — registry-defined types dispatched automatically
14. **Figma override field aliases** — `primaryAxisSizingMode` ↔ `layoutSizingHorizontal`

## Key Files

| File | Purpose |
|------|---------|
| `dd/property_registry.py` | **Single source of truth** for 58 Figma properties |
| `dd/ir.py` | IR generation, registry-driven query_screen_visuals |
| `dd/generate.py` | Figma renderer with generic override handler |
| `dd/extract_supplement.py` | Registry-driven override extraction |
| `dd/extract_screens.py` | Plugin API node extraction |
| `docs/compiler-architecture.md` | Authoritative architecture spec |
| `schema.sql` | DB schema (72 columns + instance_overrides) |

## Environment

```bash
source .venv/bin/activate
python -m pytest tests/ --tb=short          # 1,530 tests
```

## Reference Screens

| Screen | Name | Figma Node | Nodes | Status |
|--------|------|-----------|-------|--------|
| 184 | iPhone 13 Pro Max - 8 | 2244:146076 | 203 | Near pixel-perfect |
| 185 | iPhone 13 Pro Max - 114 | 2265:102114 | 225 | Good (Share/Save/Export) |
| 188 | iPhone 13 Pro Max - 110 | 2244:146231 | 366 | Gallery grid (no images) |
| 238 | iPhone 13 Pro Max - 79 | 2244:149329 | 417 | Color picker + keyboard |
