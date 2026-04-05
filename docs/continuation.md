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

The round-trip (Figma → DB → Figma) is the existential proof that the compiler works. If we can't faithfully reproduce a screen from our own database, the data is untrustworthy and everything downstream inherits those errors. It's like LLVM's lit tests — if `clang foo.c -o foo && ./foo` doesn't produce correct output, nothing else matters.

The round-trip must produce a **semantically equivalent design file** — not a flat photocopy of rectangles with hex colors, but a working Figma file with:
- Real component instances (not generic frames)
- Live design token variables (not dead hex values)
- Correct naming, hierarchy, and z-order
- Visual fidelity at 1:1 zoom

Every renderer uses **progressive fallback**: read the highest IR level available, fall back to lower levels for missing data. L0 is always the safety net.

```
L2 (token bindings)  → Figma variables (live, themeable)
  ↓ fallback
L1 (classification)  → createInstance() (real components)
  ↓ fallback
L0 (raw DB values)   → createFrame/Rectangle/Text with literals
```

## Current State (2026-04-05)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes (72 columns), 182,871 bindings, 388 tokens, 338 screens
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Tests**: 1,504 passing
- **Branch**: `t5/architecture-vision`
- **Round-trip**: Screen 184 near pixel-perfect reproduction achieved

### What the Round-Trip Produces (Screen 184)
- 11 real component instances via getNodeByIdAsync (L1 → Mode 1)
- 44 deep nested instance swaps at any depth (recursive CTE)
- 109 instance overrides: 40 visibility, 27 fills, 24 instance swaps, 6 width, 6 height, 5 text, 1 opacity
- 12 token variable bindings (L2 → live Figma variables)
- Deferred position + constraints (handles HUG+CENTER recalculation)
- Pre-fetched component node IDs (31 deduplicated async calls)
- Original Figma layer names preserved

## Remaining Issues

### Issue 1: Green Dot Size Difference (Minor)

The `logo/dank` component's green ellipse renders at a slightly smaller size in the reproduction than the original.

**Clues**: The logo/dank is a Mode 1 instance (createInstance from master). Its internal `Ellipse 55` has a gradient fill that renders correctly (green color matches). The size difference suggests a width/height override on a deeply nested element within logo/dank that our extraction doesn't reach. The `node.overrides` API on nav/top-nav reports overrides on logo/dank's visibility (`visible: true`) but may not report size changes within the logo's subtree. Check if logo/dank itself has `overrides` that include size changes on its children.

### Issue 2: Extraction Depth for Overrides

Currently, override extraction reads `node.overrides` on each INSTANCE node during the tree walk. This captures overrides that Figma reports at each instance level. But there may be override cascading — a top-level instance (nav/top-nav) has overrides that include changes to its grandchildren (buttons), and those buttons themselves have overrides on their own children (icons).

The current extraction walks the FULL tree and captures overrides at each level. But the `instance_overrides` table associates overrides with the node_id of the INSTANCE they were read from. During rendering, only top-level Mode 1 instances get their overrides applied — overrides read from depth-3 button instances (which are inside nav/top-nav and skipped by Mode 1 child skipping) are captured in the DB but never applied.

**Clue**: Check if overrides exist in `instance_overrides` for nodes that are descendants of Mode 1 instances (depth 3+). If so, the rendering needs to apply overrides from ALL ancestor instances in the chain, not just the top-level one.

### Issue 3: Image Fills (Not Yet Addressed)

`image 319` (the background RECTANGLE) is created but has no image fill. The image bytes were never extracted. This requires:
1. During Plugin API extraction: `figma.getImageByHash(hash).getBytesAsync()` for each IMAGE fill
2. Store in a new `image_data` table (hash → bytes)
3. During rendering: `figma.createImage(bytes)` to recreate the image

### Issue 4: Performance

The round-trip script takes ~90-120s to execute via PROXY_EXECUTE due to 44 `swapComponent` calls, each doing a `findOne` tree search. Many of these swaps are no-ops (component already matches master default). Potential optimizations:
- Filter swaps to only those that actually differ from master defaults (requires knowing master's child component keys)
- Batch `findOne` operations
- Use direct child indexing instead of tree search when the child is a direct child

## Key Architectural Decisions (Reference)

1. **Progressive fallback** (L2→L1→L0) — renderers read highest level available, fall back
2. **LEFT JOIN on L1** — `query_screen_for_ir()` returns ALL nodes, L1/L2 as annotations
3. **Deferred position + constraints** — emitted at END of script after all children appended (Figma recalculates position when children added to HUG frames with CENTER constraints)
4. **Two-source swaps** — Source 1: `instance_overrides` INSTANCE_SWAP entries + Source 2: recursive CTE for descendant instances, deduplicated
5. **Self-overrides** — override ID can match the instance itself (not just children). Use `:self` marker.
6. **Pre-fetch preamble** — deduplicated `getNodeByIdAsync` calls at top of generated script

## Key Files

| File | Purpose |
|------|---------|
| `docs/compiler-architecture.md` | THE authoritative architecture spec |
| `dd/ir.py` | IR generation, query_screen_visuals, build_composition_spec |
| `dd/generate.py` | Figma renderer (generate_figma_script, generate_screen, build_rebind_script_from_result) |
| `dd/extract_supplement.py` | Plugin API supplemental extraction (component keys + overrides) |
| `dd/rebind_prompt.py` | Token variable rebinding (L2) |
| `schema.sql` | DB schema (L0 scene graph + L1/L2 annotation tables) |
| `tests/test_ir.py` | IR generation tests (96 tests) |
| `tests/test_generate.py` | Figma renderer tests (134 tests) |

## Environment

```bash
source .venv/bin/activate
python -m pytest tests/ --tb=short          # 1,504 tests
```

## Reference Screen

- **Screen 184**: "iPhone 13 Pro Max - 8" in the Dank file
- **Figma node ID**: `2244:146076`
- **Size**: 428×926, 203 nodes
- **DB**: `Dank-EXP-02.declarative.db`
- **Figma file key**: `drxXOUOdYEBBQ09mrXJeYu`
