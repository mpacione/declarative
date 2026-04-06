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
- **Tests**: 1,530 passing
- **Branch**: `t5/architecture-vision`
- **Round-trip**: Screen 184 near pixel-perfect reproduction achieved; screen 185 (iPhone 13 Pro Max - 114) also reproduced successfully

### What the Round-Trip Produces (Screen 184)
- 11 real component instances via getNodeByIdAsync (L1 → Mode 1)
- 44 deep nested instance swaps at any depth (recursive CTE)
- 109 instance overrides: 40 visibility, 27 fills, 24 instance swaps, 6 width, 6 height, 5 text, 1 opacity
- 12 token variable bindings (L2 → live Figma variables)
- Deferred position + constraints (handles HUG+CENTER recalculation)
- Pre-fetched component node IDs (31 deduplicated async calls)
- Original Figma layer names preserved

## Remaining Issues

### Issue 1: Green Dot Size Difference (Minor) — INVESTIGATED

The `logo/dank` component's green ellipse renders at a slightly smaller size in the reproduction than the original.

**Finding**: The logo/dank master is 104×24 (logo + wordmark). On screen 184, the wordmark is hidden via visibility override (`;1835:155173;2281:131869:visible = false`), and logo/dank uses HUG sizing, so it shrinks to 24×24. The Ellipse 55 inside is 18×18 in both the DB extraction and likely the master. There are NO missing width/height overrides for logo or its children — the size difference may be caused by Figma's layout recalculation when HUG content changes after wordmark visibility is toggled. This is a layout timing issue in the generated script, not a data gap.

### Issue 2: Extraction Depth for Overrides — FIXED

**What was found**: 73 Mode 1 instances on screen 184, of which 62 are nested inside other Mode 1 instances. 15 nested instances had overrides in the DB. However, Figma's `node.overrides` API on the top-level instance already reports cascaded overrides for deeply nested children — so all 38 overrides on nav/top-nav already included the nested data.

**What was fixed**: Added `_hoist_descendant_overrides()` to `query_screen_visuals()` in `dd/ir.py`. This function:
1. Walks the parent chain for each Mode 1 instance to find its nearest Mode 1 ancestor
2. Transforms `:self` references on nested instances to master-relative paths (e.g., `:self:visible` on button `;2036:002` becomes `;2036:002:visible`)
3. Hoists non-self paths unchanged (they're already master-relative)
4. Deduplicates against existing ancestor overrides to avoid double-applying

This ensures correctness even when Figma's overrides API doesn't report nested overrides at the top level (future screens, different component structures). 7 new tests in `TestDescendantOverrideHoisting`.

### Issue 5: Text Auto Resize Not Extracted — FIXED

**Root cause**: The `textAutoResize` property (NONE, HEIGHT, WIDTH_AND_HEIGHT, TRUNCATE) was never extracted from Figma or stored in the DB. The renderer hardcoded `WIDTH_AND_HEIGHT` for all text nodes. This caused:
- Text boxes that should have fixed width (e.g., "Meme-00001" field title above canvas) to auto-shrink
- Text within auto-layout parents to not respect their intended sizing mode
- Layout breakage in Frame 358 (the header row above the canvas area)

**Fix**:
1. Added `text_auto_resize` column to `schema.sql`
2. Extract `node.textAutoResize` in Plugin API script (`extract_screens.py`)
3. Added to field cleaning and DB insert column lists
4. `query_screen_visuals()` includes `text_auto_resize` with backwards compatibility (detects column existence via PRAGMA)
5. `generate.py` reads stored value, falls back to `WIDTH_AND_HEIGHT` when NULL
6. 6 new tests in `TestTextAutoResize` + `TestQueryScreenVisuals`

**Note**: Existing DB needs re-extraction to populate the column. Until then, existing behavior is preserved (defaults to WIDTH_AND_HEIGHT).

### Issue 6: Mixed-Dimension Resize — FIXED

**Root cause**: `_emit_layout()` emitted `resize({rw or 1}, {rh or 1})`. When one dimension was HUG/FILL (no pixel value), `None or 1` forced the other dimension to 1px. Frame 358 got `resize(394, 1)` — height crushed to 1px.

**Fix**: Use `{var}.height` or `{var}.width` to preserve the current dimension when only one axis has a pixel value.

### Issue 7: Default Fill Leak — FIXED

**Root cause**: `figma.createFrame()` creates frames with a default white fill. The DB stores `fills = None` for transparent frames. The renderer treated NULL as "don't touch" — leaving the default white fill visible.

**Fix**: For non-text Mode 2 frames with no fills in the DB, explicitly emit `fills = []` to clear the default.

### Issue 8: Layout Sizing Not Extracted for Auto-Layout Children — FIXED

**Root cause**: `layoutSizingHorizontal`/`layoutSizingVertical` were only read inside the `if (node.layoutMode)` block. TEXT nodes and other auto-layout children that don't have their own layoutMode never got their sizing captured. The renderer hardcoded `FILL` for all text in auto-layout.

**Fix**:
1. Read `layoutSizingH/V` for ALL nodes in `extract_screens.py` (not just auto-layout containers)
2. Added `layout_sizing_h/v` to `query_screen_visuals()` SELECT
3. Renderer reads DB value; falls back to FILL only when NULL
4. `layoutSizing` must be set AFTER `appendChild` (setting before throws — node must be child of auto-layout)
5. Override extraction checks `primaryAxisSizingMode` (Figma's override field name differs from the property name)

### Issue 9: Mode 1 L0 Visual Properties Not Applied — FIXED

**Root cause**: Mode 1 instances only applied override mutations on children. The instance node ITSELF could have L0 property differences from the master (rotation, opacity) that weren't applied.

**Fix**: After `createInstance()`, apply `rotation` (converting radians→degrees) and `opacity` from the DB when they differ from defaults.

### Issue 10: Rotation Unit Mismatch — FIXED

**Root cause**: DB stores rotation in radians (from REST API). Figma Plugin API uses degrees. The renderer emitted radians directly.

**Fix**: `build_visual_from_db()` converts radians to degrees via `math.degrees()`.

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
7. **Override hoisting** — `_hoist_descendant_overrides()` transforms :self→master-relative, deduplicates, hoists to ancestor
8. **Text auto resize from DB** — stored per-node, renderer reads it instead of hardcoding WIDTH_AND_HEIGHT
9. **Default fill clearing** — Mode 2 frames with no DB fills get `fills = []` to clear Figma's default white
10. **Layout sizing after appendChild** — `layoutSizing` only valid on auto-layout children, must be set post-append
11. **Radians→degrees** — DB stores radians (REST API), renderer converts via `math.degrees()`
12. **Mode 1 L0 properties** — rotation + opacity applied directly to instance after createInstance()
13. **Property registry** — `dd/property_registry.py` defines all 58 Figma properties; extraction, query, and renderer reference it
14. **Generic override handler** — registry-defined override types dispatched automatically, no ad-hoc if/elif needed

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
