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

Each backend reads the levels it needs:
- Figma reproduction reads L0 (full scene graph, pixel-perfect)
- React renderer reads L1 + L2 (semantic types + tokens)
- Cross-platform output reads L3 (semantic tree)

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

Each target platform gets a renderer — a function that reads the IR and produces target-specific output.

### Figma Renderer (Reproduction)

Walks L0 (DB `parent_id` tree) directly. For each node:
- INSTANCE with `component_key` → `getNodeByIdAsync(figma_node_id).createInstance()`
- FRAME → `figma.createFrame()` + apply layout, fills, strokes, effects, constraints
- TEXT → `figma.createText()` + apply font, content
- RECTANGLE → `figma.createRectangle()` + apply fills
- Sets `visible`, `clipsContent`, `rotation`, `constraints` from DB
- Applies instance property overrides via `setProperties()`
- Applies visibility overrides on instance children

### React Renderer (Code Generation)

Reads L1 (classification) + L2 (tokens). For each semantic element:
- `direction: horizontal` → `display: flex; flex-direction: row`
- `padding: {space.lg}` → `padding: var(--space-lg)`
- `type: button, variant: primary` → `<Button variant="primary">`
- `sizing: {width: fill}` → `flex: 1` or `width: 100%`
- Token references become CSS custom properties

### SwiftUI Renderer (Future)

Same IR, different output:
- `direction: horizontal` → `HStack`
- `padding: {space.lg}` → `.padding(SpacingTokens.lg)`
- `type: button` → `Button`

---

## 6. Round-Trip Verification

The foundational test: **Figma → DB → IR → Figma** produces a visually identical screen.

### Current Status

Screen 184 (Dank meme editor, 203 nodes, 428×926):
- Extraction: Complete (all 203 nodes in DB with 72 columns each)
- L0 → Figma: Structurally broken — renderer walks IR tree instead of DB tree
- Root cause: `generate_screen()` calls `generate_ir()` which builds a classification-based tree

### What Must Work

1. Every node in the original screen appears in the reproduction
2. Parent-child relationships match the original
3. Positions, sizes, and layout properties match
4. Visual properties (fills, strokes, effects, radius, opacity) match
5. Component instances are created from the correct master components
6. Instance property overrides are applied
7. Visibility states match (hidden children stay hidden)
8. The reproduction is visually indistinguishable from the original at 1:1 zoom

### What May Differ

- Figma node IDs (new nodes get new IDs)
- Layer names (may use IR element IDs instead of original names)
- Canvas position (reproduction placed at a different position on the canvas)

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
  ir.py                      # IR generation, query_screen_visuals, build_composition_spec
  generate.py                # Figma renderer (generate_figma_script, generate_screen)
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
  module-reference.md        # Complete API reference
  continuation.md            # Current state and next steps
  research/                  # Research artifacts (Mitosis, Ghost, formats, etc.)
  archive/                   # Superseded documents

tests/                       # 1,475 tests
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
| **Round-trip** | Source → IR → Source with zero loss. The foundational correctness test. |
| **Design token** | A named, reusable value (color, spacing, font) that can be resolved differently per theme/platform. |
| **Scene graph** | The complete node tree with all visual, layout, and structural properties. |
