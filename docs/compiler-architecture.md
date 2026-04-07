# Declarative Design Compiler — Architecture Specification

> The authoritative specification for the Declarative Design system.
> Supersedes: t5-four-layer-architecture.md, t5-ir-design.md, t5-architecture-vision.md.

---

## 1. Vision

A design system compiler that translates design artifacts between any source and any target through a multi-level intermediate representation. Like LLVM compiles C/Rust/Swift to x86/ARM/WASM, this system compiles Figma/React/SwiftUI to Figma/React/SwiftUI — bidirectionally, with design token fidelity.

### The Gap This Fills

| System | Design Tools | Code | Layout | Tokens | Bidirectional |
|--------|-------------|------|--------|--------|---------------|
| Mitosis (Builder.io) | No | Yes (web) | No | No | No |
| Airbnb Ghost (SDUI) | No | Yes (proprietary) | Yes | No | No |
| Figma Dev Mode | Yes | One-way export | Partial | Partial | No |
| W3C Design Tokens | No | Values only | No | Yes | N/A |
| **This System** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

---

## 2. Compiler Model

```
FRONTENDS (parsers)              BACKENDS (renderers)
                    ┌──────────────────────┐
Figma extraction ──→│                      │──→ Figma renderer (Plugin API)
React parser ──────→│   Multi-Level IR     │──→ React renderer (JSX + CSS)
SwiftUI parser ────→│                      │──→ SwiftUI renderer
Prompt / LLM ─────→│   L0 ─ L1 ─ L2 ─ L3 │──→ Flutter renderer
Drawing / sketch ──→│                      │──→ HTML renderer
                    └──────────────────────┘
```

**Frontend**: Parses source format into the IR. Language/tool-specific.
**IR**: Multi-level representation carrying both structural truth and semantic annotations.
**Backend**: Renders IR to target format. Platform-specific.

Each frontend fills the levels it can:
- Figma extraction fills L0 + L1 + L2 + L3 (everything)
- React parser fills L1 + L2 (semantic types + tokens, no Figma scene graph)
- LLM/prompt fills L3 only (semantic intent, system compiles down)

Each backend reads from the highest level available and falls back to lower levels for missing data (see Section 5, Progressive Fallback):
- Figma reproduction: L2 → L1 → L0 (tokens first, then components, then raw properties)
- React renderer: L2 → L1 → L0 (tokens as CSS vars, components as JSX, raw values as fallback)
- Cross-platform output: L3 → L2 → L1 (semantic tree, with token and type references)

---

## 3. The Multi-Level IR

Inspired by MLIR (Multi-Level Intermediate Representation, LLVM project). Core principle: **levels coexist, each adds information, none removes it.**

### Level 0 — Scene Graph (Database)

The DB `nodes` table IS Level 0. Not a serialization of L0 — the table itself is the scene graph.

- 72 columns per node
- `parent_id` column defines the tree structure
- `sort_order` defines z-ordering within each parent
- Every visual, layout, font, constraint, and transform property
- Every node type: FRAME, RECTANGLE, TEXT, INSTANCE, GROUP, VECTOR, ELLIPSE, etc.
- `visible`, `clips_content`, `rotation`, `blend_mode`
- `component_key` for INSTANCE nodes (reference to master component)

**86,761 nodes** in the Dank extraction. This is a complete, lossless copy of the Figma file's node tree.

For reproduction, the renderer walks `parent_id` directly. No intermediate transformation needed.

### Level 1 — Classification

The `screen_component_instances` table annotates L0 nodes with semantic types.

```
node 22068 (FRAME "button/toolbar")  →  canonical_type: "button", confidence: 1.0
node 22130 (INSTANCE "nav/top-nav")  →  canonical_type: "header", confidence: 1.0
```

48 canonical types across 6 categories (navigation, input, display, layout, feedback, composite). 93.6% of nodes classified. Unclassified nodes (VECTOR, ELLIPSE, system chrome) retain their L0 data — they're just not annotated.

### Level 2 — Token Bindings

The `node_token_bindings` table maps specific node properties to design tokens.

```
node 22068, property "fill.0.color"  →  token "color.surface.white" = "#FFFFFF"
node 22068, property "padding.top"   →  token "space.lg" = 4.0
node 22068, property "cornerRadius"  →  token "radius.v16" = 16.0
```

182,871 bindings across 388 tokens in 8 collections. This is what makes the design system portable — values become references to a token vocabulary that can be resolved differently per target/theme.

### Level 3 — Semantic Tree

A compact, human/LLM-readable representation of the screen's component structure. ~20 elements per screen (vs ~200 nodes at L0). Format: YAML.

```yaml
screen:
  size: [428, 926]
  layout: absolute
  clips: true

  header:
    component: nav/top-nav
    position: [0, 0]
    text: Settings

  card:
    position: [0, 111]
    layout: vertical
    padding: {space.lg}
    fill: {color.surface.white}

    heading: Notifications
    toggle: Push Notifications
    toggle: Dark Mode

  button:
    component: button/small/solid
    position: [0, 500]
    text: Save
```

L3 is what LLMs produce when generating new screens. It's what crosses platform boundaries (React renderer reads L3, not L0). It references L1 types and L2 tokens by name.

---

## 4. Spatial Encoding

Six distinct mechanisms for positioning and sizing UI elements:

### 4.1 Position

Two mutually exclusive modes per parent:

**Auto-layout**: Parent has `direction: horizontal|vertical`. Children flow in sequence. Position is implicit — determined by order + gap + padding. No coordinates.

**Absolute**: Parent has `layout: absolute` (or no layout mode). Each child has explicit `position: [x, y]` relative to parent's top-left origin (0, 0). Positive x = right, positive y = down. Same convention as CSS, Figma Plugin API, every UI toolkit.

### 4.2 Size

Three modes: `fixed` (pixels), `hug` (shrink to content), `fill` (expand to parent). Plus `min_width`, `max_width`, `min_height`, `max_height` for bounded flex.

### 4.3 Padding

Internal spacing: `{top, right, bottom, left}`. Tokenized when possible: `padding: {space.lg}`.

### 4.4 Gap

Uniform spacing between auto-layout children. Single value on the parent. Figma: `itemSpacing`.

### 4.5 Constraints

For absolutely-positioned children: `constraints: {horizontal, vertical}`. Values: `min` (pin left/top), `max` (pin right/bottom), `center`, `stretch` (pin both), `scale` (proportional). Controls resize behavior.

### 4.6 Z-Order

Document order = stacking order. Last child renders on top. No explicit z-index needed in the IR — ordering in the children array IS the z-order.

---

## 5. Renderer Architecture

Each target platform gets a renderer — a function that reads the IR and produces target-specific output. Different renderers read different levels of the IR, just as different LLVM backends read different levels of the machine IR hierarchy.

### Why the IR Matters (The M×N Problem)

Without the IR, every source→target pair needs its own translator: 5 frontends × 5 backends = 25 translators, each reimplementing analysis logic. With the IR, analysis is written once and stored:

- **Classification** (L1): "This FRAME is a button" — written once by the classification cascade, reused by every renderer
- **Token binding** (L2): "This padding is `{space.lg}`" — written once by the clustering pipeline, reused by every renderer
- **Semantic compression** (L3): "header, card with 2 toggles, save button" — written once, reused by every renderer and LLM

These are compiler passes that operate on the IR. Without it, each renderer independently reimplements component detection, token mapping, and semantic understanding. The IR is where shared analysis lives.

### Progressive Fallback: How Renderers Read the IR

Every renderer starts from the **highest IR level available** for each property and falls back to lower levels when data is missing. L0 is always the safety net — complete and lossless.

```
L3 (semantic intent)     → highest abstraction, used when available
  ↓ fallback
L2 (token bindings)      → design system portability (Figma variables, CSS vars)
  ↓ fallback
L1 (classification)      → component identity (createInstance, <Button>)
  ↓ fallback
L0 (raw DB properties)   → complete, lossless, always available
```

This means renderers never fail — they degrade gracefully from semantic (tokens + components) to literal (raw values + generic elements). A property with a token binding renders as a live Figma variable or CSS custom property. A property without a token binding renders as a hardcoded value from L0. Both are correct — one is more portable.

| Renderer | Reads | Fallback | Output Character |
|----------|-------|----------|------------------|
| **Figma** | L2 → L1 → L0 | Raw DB values | Semantically equivalent design file with live tokens and real components |
| **React** | L2 → L1 → L0 | Hardcoded CSS values | Idiomatic JSX with CSS custom properties, falling back to literals |
| **SwiftUI** | L2 → L1 → L0 | Hardcoded Swift values | Native SwiftUI with token constants, falling back to literals |
| **LLM/Prompt** | L3 → L2 → L1 | Component types | Compact YAML with token refs and semantic types |

### Renderer Value Transforms

The IR stores values in **ground truth format** (lossless from extraction). Each renderer transforms values to its platform's native format at emit time. No transformation is universal — even radians→degrees is only needed by some platforms (Flutter uses radians natively).

The shared `build_visual_from_db` produces a **renderer-agnostic visual dict**: hex colors, numeric font weights, radians for rotation, semantic strings for alignment/sizing. Each renderer applies its own transforms:

- **Figma**: hex→`{r,g,b,a}`, weight→style name `"Semi Bold"`, rad→deg, `"start"`→`"MIN"`
- **React/CSS**: hex→`rgba()`, weight stays numeric, rad→deg, `"start"`→`"flex-start"`
- **SwiftUI**: hex→`Color()`, weight→`.semibold`, rad→either, `"start"`→`.leading`
- **Flutter**: hex→`Color(0xAARRGGBB)`, weight→`FontWeight.w600`, keep rad, `"start"`→`.start`

See `docs/cross-platform-value-formats.md` for the complete reference table.

### Figma Renderer (Reproduction)

The Figma renderer produces a **semantically equivalent design file** — not a flat photocopy of rectangles with hex colors, but a working Figma file with real components, live design token variables, proper naming, and correct hierarchy. It reads all IR levels via progressive fallback.

For each node, walking the L0 `parent_id` tree:

1. **L2 — Token bindings**: For every property on the node, check if a token binding exists in `node_token_bindings`. If yes, the reproduced node gets a live Figma variable binding (not a dead hex value). This makes the reproduced file respond to theme changes, mode switching, and token updates — just like the original.

2. **L1 — Classification**: Is this node classified with a `component_key`?
   - Yes → Mode 1: `getNodeByIdAsync(figma_node_id).createInstance()`. The reproduced node IS a real component instance with proper variant structure, naming, and inherited children. Skip creating child nodes (they come from the component).
   - Apply instance property overrides (text, visibility, variant selection) from the DB.

3. **L0 — Raw properties (fallback)**: For unclassified nodes or properties without token bindings:
   - FRAME → `figma.createFrame()` + apply layout, fills, strokes, effects, constraints from raw DB columns
   - TEXT → `figma.createText()` + apply font, content from raw DB columns
   - RECTANGLE → `figma.createRectangle()` + apply fills from raw DB columns
   - VECTOR, ELLIPSE, GROUP → create appropriate element type from L0 data
   - Sets `visible`, `clipsContent`, `rotation`, `constraints` from raw DB values

4. **Apply visibility and overrides**: Hidden children, instance property overrides, blend modes.

The result is a Figma file that isn't just visually identical to the original — it's structurally equivalent. Components are real components. Tokens are live variables. Naming preserves semantic intent. A designer can open the reproduced file and work with it normally.

### Future Renderers (After Round-Trip Is Proven)

The same progressive fallback model applies to every backend. These are NOT built yet — they come after round-trip fidelity is achieved.

**React**: For each L1-classified component:
- L2 token binding exists? → `color: var(--color-brand)` (CSS custom property)
- No token binding? → Query L0 → `color: #09090B` (hardcoded fallback)
- L1 classification exists? → `<Button variant="primary">` (semantic component)
- No classification? → `<div style={...}>` (generic element with L0 properties)

**SwiftUI**: Same pattern. `canonical_type: "button"` → `Button(.primary)`. Token refs → Swift token constants. Unbound properties → literal values from L0.

**Flutter**: Same pattern. `canonical_type: "button"` → `ElevatedButton()`. Token refs → theme values. Unbound properties → literal values from L0.

No renderer ever encounters "missing data" — L0 is always the complete fallback. The higher levels make the output more portable, more semantic, and more maintainable. L0 ensures correctness.

### The Round-Trip Proves All Levels

The round-trip test (Figma → DB → Figma) validates the full IR stack because the Figma renderer exercises every level via progressive fallback:

- **L2 proven**: Token bindings rebind to Figma variables — the reproduced file has live design tokens
- **L1 proven**: Classified components render via `createInstance()` — the reproduced file has real components
- **L0 proven**: Every node reproduced with correct properties — extraction is lossless

If the round-trip succeeds, every downstream renderer (React, SwiftUI, Flutter) can trust the IR data it reads, because the Figma renderer has already validated L0, L1, and L2 end-to-end. L3 is validated separately (semantic compression is a higher-level concern tested by prompt→screen generation).

---

## 6. Round-Trip: The Foundational Requirement

**Nothing else matters until round-trip works.** No cross-platform renderers, no L3 format spec, no React/SwiftUI backends, no prompt-based generation. The entire compiler model rests on one proof: Figma → DB → Figma produces a visually identical screen.

If we cannot faithfully reproduce a screen from our own database, the data is untrustworthy, the IR is unproven, and every downstream consumer inherits those errors. Round-trip fidelity is the foundation that everything else builds on.

### The Test

Extract screen 184 from the Dank file into the DB. Generate Figma Plugin API JavaScript from the DB. Execute it in Figma. The result must be visually indistinguishable from the original at 1:1 zoom.

### Current Status (2026-04-06)

Round-trip structurally proven on 4 screens (184, 185, 188, 238). The renderer now implements progressive fallback correctly:

- **L0 → L1 → L2 fallback**: All 203+ nodes enter the IR via LEFT JOIN. L1/L2 enrich as annotations, never filter.
- **Mode 1 instances**: Real component instances via `getNodeByIdAsync().createInstance()` with full override application (17 override types, 69,866 total overrides across all screens)
- **Mode 2 frames**: Created from L0 properties with registry-driven visual emission
- **Property registry** (`dd/property_registry.py`): Single source of truth for 48 Figma properties. Extraction, query (51 columns), and renderer all reference it — prevents the "extract but forget to emit" gap pattern.
- **Override types captured**: BOOLEAN (visibility), FILLS, STROKES, EFFECTS, CORNER_RADIUS, INSTANCE_SWAP, WIDTH, HEIGHT, OPACITY, LAYOUT_SIZING_H, ITEM_SPACING, PADDING_LEFT/RIGHT, PRIMARY_ALIGN, STROKE_WEIGHT, STROKE_ALIGN, TEXT
- **Default clearing**: `fills=[]` and `clipsContent=false` explicitly set to override Figma's createFrame() defaults
- **Layout sizing**: Auto-layout containers set own sizing pre-appendChild; non-auto-layout children deferred to post-appendChild
- **Remaining gaps**: Image fills (no byte extraction), PROXY_EXECUTE position reliability (intermittent), font name normalization

### What Must Work

The reproduced file must be a **semantically equivalent design file**, not just a visual match:

1. Every node in the original screen appears in the reproduction (L0 completeness)
2. Parent-child relationships match the original (`parent_id` tree preserved)
3. Properties with token bindings render as live Figma variables (L2 fidelity)
4. Classified components render as real component instances via `createInstance()` (L1 fidelity)
5. Unclassified nodes render from raw L0 properties (progressive fallback)
6. Positions, sizes, and layout properties match
7. Visual properties (fills, strokes, effects, radius, opacity) match
8. Instance property overrides are applied
9. Visibility states match (hidden children stay hidden)
10. The reproduction is visually indistinguishable from the original at 1:1 zoom

### What May Differ

- Figma node IDs (new nodes get new IDs)
- Layer names (may use IR element IDs instead of original names)
- Canvas position (reproduction placed at a different position on the canvas)

### What Comes AFTER Round-Trip (Not Before)

Only once round-trip is proven:
1. Formalize the L3 semantic format (YAML schema)
2. Build additional frontends (React parser, SwiftUI parser)
3. Build additional backends (React renderer, SwiftUI renderer)
4. LLM-based generation (prompt → L3 → target)

---

## 7. Prior Art and Influences

### MLIR (LLVM Project)
Multi-level IR with coexisting dialects. Progressive lowering. Each level adds information, none removes. Our L0-L3 follows this pattern.

### LLVM
Frontend → IR → Backend architecture. One IR, many frontends, many backends. SSA form. Optimization passes. Our compiler model is a direct analogy.

### Mitosis (Builder.io)
Proves one-IR-many-backends for frontend frameworks. JSON AST compiles to React/Vue/Angular/Svelte/Solid/Qwik. Behavioral IR — no visual properties, no tokens, no layout.

### Airbnb Ghost Platform (SDUI)
Component type as contract between server and client. Pointer-based architecture. Pre-formatting principle. Validates our RendererConfig pattern.

### USD (Pixar)
Composition arcs — non-destructive layered overrides. Multiple "opinions" compose with deterministic ordering. Relevant for theming and variant handling.

### W3C Design Tokens (DTCG 2025.10)
Stable specification for design token interchange. Our L2 should align for ecosystem compatibility.

### XGrammar (ICML 2025)
Constrained decoding for LLM structured output. Token-level masking guarantees valid output. Speeds up generation 50%. L3 YAML schema → XGrammar grammar → guaranteed valid IR from LLMs.

---

## 8. File Structure

```
dd/                          # Python source
  property_registry.py       # Single source of truth: 48 properties with emit patterns
  visual.py                  # Shared infrastructure (renderer-agnostic visual dict)
  renderers/
    __init__.py              # Renderer package
    figma.py                 # Figma Plugin API renderer (JS emission)
  generate.py                # Backward-compatible re-exports
  ir.py                      # IR generation, query_screen_visuals, build_composition_spec
  compose.py                 # Prompt composition (compose_screen, build_template_visuals)
  templates.py               # Template extraction (extract_templates, query_templates)
  classify.py                # Classification (L1)
  catalog.py                 # Component type catalog (48 types)
  extract.py                 # Figma extraction orchestrator
  extract_screens.py         # Plugin API extraction JS
  extract_supplement.py      # Supplemental extraction (component keys)
  prompt_parser.py           # LLM prompt parsing (L3 → component list)
  rebind_prompt.py           # Token rebinding for generated screens

schema.sql                   # DB schema (L0 scene graph + L1/L2 tables)
docs/
  compiler-architecture.md   # THIS document — the authoritative spec
  cross-platform-value-formats.md  # Renderer value format reference
  module-reference.md        # Complete API reference
  continuation.md            # Current state and next steps
  research/                  # Research artifacts (Mitosis, Ghost, formats, etc.)
  archive/                   # Superseded documents

tests/                       # 1,657 tests
```

---

## 9. Glossary

| Term | Definition |
|------|-----------|
| **L0** | Level 0 — the DB scene graph. Complete, lossless node tree. |
| **L1** | Level 1 — classification annotations. Semantic types on L0 nodes. |
| **L2** | Level 2 — token binding annotations. Design token refs on properties. |
| **L3** | Level 3 — semantic tree. Compact, human/LLM-readable component tree. |
| **Mode 1** | Component instance rendering via `createInstance()`. Visual tree inherited. |
| **Mode 2** | Frame/shape construction via `createFrame()`. Properties set explicitly. |
| **Frontend** | Parser that reads a source format into the IR. |
| **Backend** | Renderer that writes the IR to a target format. |
| **Progressive lowering** | Transforming high-level IR (L3) to lower-level (L0) by filling in details. |
| **Progressive fallback** | Renderer reads highest IR level available, falls back to lower levels for missing data. L3→L2→L1→L0. |
| **Round-trip** | Source → IR → Source with zero loss. The foundational correctness test. Proves all IR levels. |
| **Design token** | A named, reusable value (color, spacing, font) that can be resolved differently per theme/platform. |
| **Scene graph** | The complete node tree with all visual, layout, and structural properties. |
