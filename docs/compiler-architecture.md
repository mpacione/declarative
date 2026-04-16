# Declarative Design Compiler — Architecture Specification

> The authoritative technical specification. For a higher-level
> introduction aimed at new readers, start with the
> [repo README](../README.md). For what's coming next, see
> [`roadmap.md`](roadmap.md).
>
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

- 77 columns per node
- `parent_id` column defines the tree structure
- `sort_order` defines z-ordering within each parent
- Every visual, layout, font, constraint, and transform property
- Every node type: FRAME, RECTANGLE, TEXT, INSTANCE, GROUP, VECTOR, ELLIPSE, etc.
- `visible`, `clips_content`, `rotation`, `blend_mode`, `is_mask`, `corner_smoothing`, `boolean_operation`, `arc_data`
- `fill_geometry`, `stroke_geometry` for derived vector outlines
- `vector_paths` for authoring-primitive vector data (windingRule-aware)
- `relative_transform` for parent-local 2×3 affine (encodes rotation, mirror, translation in one value)
- `opentype_features` for styled text-segment feature maps
- `component_key` for INSTANCE nodes (reference to master component)
- **Content-addressed asset registry**: `assets` table (hash, kind, metadata) + `node_asset_refs` junction table linking nodes to raster images, SVG vectors, and icons. Deduplicates shared geometry (Dank: 26,050 node references → 253 unique SVG paths).

**86,766 nodes** in the Dank (Experimental) extraction. This is a complete, lossless copy of the Figma file's node tree.

For reproduction, the renderer walks `parent_id` directly. No intermediate transformation needed.

### Level 1 — Classification

The `screen_component_instances` table annotates L0 nodes with semantic types.

```
node 22068 (FRAME "button/toolbar")  →  canonical_type: "button", confidence: 1.0
node 22130 (INSTANCE "nav/top-nav")  →  canonical_type: "header", confidence: 1.0
```

48 canonical types across 6 categories (navigation, input, display, layout, feedback, composite). Classification cascade uses catalog-matched rules with optional LLM and vision-model fallbacks for ambiguous nodes. Unclassified nodes (VECTOR, ELLIPSE, system chrome) retain their L0 data — they're just not annotated.

### Level 2 — Token Bindings

The `node_token_bindings` table maps specific node properties to design tokens.

```
node 22068, property "fill.0.color"  →  token "color.surface.white" = "#FFFFFF"
node 22068, property "padding.top"   →  token "space.lg" = 4.0
node 22068, property "cornerRadius"  →  token "radius.v16" = 16.0
```

293,183 node-property bindings on Dank. Before curation these carry raw property values with `token_id = NULL`; after clustering + curation they carry token references. This is what makes the design system portable — values become references to a token vocabulary that can be resolved differently per target/theme.

The pipeline for producing L2 is described in §6 below.

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

#### Three-Phase Rendering

The Figma Plugin API has implicit ordering constraints that require careful emit sequencing. Rather than scattering workarounds throughout a single-pass loop, the renderer uses three clean phases:

```
Phase 1: MATERIALIZE — Create every node, set intrinsic properties
         (fills, strokes, effects, font, fontSize, cornerRadius,
          dimensions via resize, textAutoResize)
         Every node starts as a standalone entity with correct
         intrinsic size. No tree wiring yet.

Phase 2: COMPOSE — Wire the tree (appendChild), set layoutSizing.
         Auto-layout resolves here because all nodes have
         intrinsic dimensions as starting points. FIXED children
         establish parent HUG widths before FILL children expand.

Phase 3: HYDRATE — Two sub-steps in strict order:
         (a) resize/position on non-auto-layout children
             (establishes pixel dimensions for FILL descendants)
         (b) text characters (loadFontAsync + characters)
             (text reflows at correct container widths)
         This ordering ensures FILL text descendants have
         ancestor widths established before content is set.
```

**Why three phases?** Each phase has a single responsibility and the boundaries eliminate an entire class of Figma Plugin API ordering bugs:

- `resize()` in Phase 1 gives every frame a starting dimension (no zero-width containers)
- `appendChild` + `layoutSizing` in Phase 2 lets auto-layout resolve with all children present
- Text in Phase 3 flows into containers with established widths (no vertical single-char wrapping)

**Platform-specific by design.** A React renderer would only need Phase 1+2 (CSS reflows text automatically). A SwiftUI renderer might have its own phase structure. The IR doesn't change — each backend owns its emit ordering.

#### Progressive Fallback per Node

For each node, walking the L0 `parent_id` tree:

1. **L2 — Token bindings**: For every property on the node, check if a token binding exists in `node_token_bindings`. If yes, the reproduced node gets a live Figma variable binding (not a dead hex value). This makes the reproduced file respond to theme changes, mode switching, and token updates — just like the original.

2. **L1 — Classification**: Is this node classified with a `component_key`?
   - Yes → Mode 1: `getNodeByIdAsync(figma_node_id).createInstance()`. The reproduced node IS a real component instance with proper variant structure, naming, and inherited children. Skip creating child nodes (they come from the component).
   - Apply instance property overrides (text, visibility, variant selection) from the DB.

3. **L0 — Raw properties (fallback)**: For unclassified nodes or properties without token bindings:
   - FRAME → `figma.createFrame()` + apply layout, fills, strokes, effects, constraints from raw DB columns
   - TEXT → `figma.createText()` + apply font, content from raw DB columns
   - RECTANGLE → `figma.createRectangle()` + apply fills from raw DB columns
   - VECTOR/BOOLEAN_OPERATION → check `_asset_refs` for SVG path data; if present, `figma.createVector()` + `vectorPaths`; if not, skip (graceful degradation)
   - IMAGE fills → emit `{type: "IMAGE", scaleMode, imageHash}` paint entries
   - Sets `visible`, `clipsContent`, `rotation`, `constraints` from raw DB values

4. **Apply visibility and overrides**: Hidden children, instance property overrides, blend modes.

#### Architectural Principle: IR Stays Pure, Renderer Owns Platform Constraints

The IR stores sizing intent (`fill`/`hug`/`fixed`) unconditionally on every node, along with pixel dimensions. `layoutSizing` is a parent-context-dependent property (like CSS `flex-grow`) — it only applies when the node's parent has auto-layout. The IR stores it as ground truth; the renderer decides **when** and **whether** to emit it based on parent context at composition time (Phase 2).

This follows the universal pattern across LLVM (legalization), Flutter (constraints down, sizes up), Compose (`weight()` inert outside `Row`/`Column`), and CSS (`flex-grow` ignored without `display:flex`). Store intent on the node, resolve in parent context at emit time.

#### Tree Structure: DB `parent_id` as Single Source of Truth

The tree structure for rendering always comes from the DB `parent_id` chain — the exact node tree as extracted from Figma. The `screen_component_instances` (SCI) table provides **classification** (element type, component key) but never overrides tree structure. SCI `parent_instance_id` is used for classification context, not for parent-child wiring.

This separation prevents skip-level wiring bugs where SCI parent chains bypass intermediate INSTANCE nodes that lack SCI entries (e.g., keyboard containers), causing their children to be flattened under the wrong parent.

### Override Tree

Instance overrides are stored in the visual dict as a nested `override_tree` rather than flat lists. The tree structure encodes dependency ordering: swaps appear as parent nodes, property overrides on swapped children appear as descendants. This nesting is semantic — it reflects the component slot tree, not renderer-specific concerns.

**Why a tree?** A flat list of overrides cannot express ordering dependencies. When an instance swap replaces a child subtree, any property overrides targeting nodes inside that child must be applied AFTER the swap. A flat `OrderedDict` grouped by insertion order gets this wrong when swaps and property overrides interleave. The tree makes the dependency explicit: pre-order traversal naturally produces correct imperative ordering (swap first, then override descendants). Declarative renderers can map the tree directly to nested props.

Built by `build_override_tree()` in `dd/ir.py`, consumed by all renderers. The Figma renderer walks it via `_emit_override_tree()` (recursive pre-order).

### Synthetic Node Filtering

Figma inserts implementation artifact nodes with parenthesized names — `(Auto Layout spacer)`, `(Adjust Auto Layout Spacing)`. These are platform internals, not design content. They are filtered at the composition spec boundary (`build_composition_spec` in `dd/ir.py`) so all renderers benefit. L0 stays lossless — the nodes remain in the DB, only excluded from the spec output.

**System chrome is NOT synthetic.** iOS status bars, keyboards, Safari chrome are design content placed intentionally by designers. A keyboard on a login screen communicates "this is the typing state." Filtering it would make the design incomplete. Only platform IMPLEMENTATION artifacts (Figma internal spacers) are synthetic.

Detection: `is_synthetic_node(name)` in `dd/classify_rules.py`. Filtering includes transitive closure — children of synthetic nodes are also excluded.

### Asset Registry

Non-property design data (raster images, SVG vector paths, icons) stored in a content-addressed `assets` table. Nodes reference assets via `node_asset_refs` junction table with role classification (fill, icon, illustration, background, mask).

- **Raster assets**: Keyed by Figma `imageHash`. Emitted as IMAGE paint entries.
- **Vector assets**: SVG path data from `fillGeometry`/`strokeGeometry`. Hashed via SHA-256 for deduplication. Emitted as `vectorPaths` assignments.
- **Resolution**: `AssetResolver` ABC decouples renderers from storage. `SqliteAssetResolver` reads from the local DB. Future backends (cloud, CDN) implement the same interface.

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

## 6. Token Pipeline

L2 (token bindings) is produced by a dedicated sub-pipeline that runs
between extraction and rendering. It has five stages:

```
  extract   →   cluster   →   curate   →   bind   →   push
   (L0)          (L2 proposals)            (L2)         (back to source)
```

### 6.1 Extract

During ingest every assignable property is written as a row in
`node_token_bindings` with `token_id = NULL` and a literal value. A
4px padding on node 22068 becomes a row `{node_id: 22068, property:
"padding.top", raw_value: "4", token_id: null}`. These are the raw
observations the clustering pass consumes.

### 6.2 Cluster

`dd cluster` walks the raw-binding table and proposes tokens. Five
clusterers run, each with its own policy:

| Clusterer | Input | Output |
|---|---|---|
| `cluster_colors` | `fills` / `strokes` hex values | Proposals for `color.*` tokens, grouped by semantic role (surface, text, accent, border) |
| `cluster_spacing` | `padding`, `item_spacing`, `counter_axis_spacing` | Proposals for `space.*` tokens with canonical names (xs, sm, md, lg, xl, v8, v12, v16, ...) |
| `cluster_typography` | `font_family`, `font_size`, `font_weight`, `line_height`, `letter_spacing` | Proposals for `typography.*` token compounds |
| `cluster_radius` + `cluster_effect` + `cluster_misc` | `corner_radius`, `effects`, opacity, stroke weight | Proposals for `radius.*`, `elevation.*`, `opacity.*` tokens |

Clusterers are conservative — they propose, they don't commit. Each
proposal carries a `confidence`, a `source_binding_count`, and a
canonical name derived from value (e.g., `color.accent.green.v97` for
a specific green hex).

Materialised views (`v_color_census`, `v_spacing_census`,
`v_effect_census`, etc.) summarise raw value frequencies per property
category — useful for operator review and for the clusterers
themselves to detect modes / variants.

### 6.3 Curate

Clusterer proposals go through a curation step. `dd curate-report`
surfaces issues:

- Multiple near-duplicate proposals (rename / merge candidates)
- Proposals with low source-binding count (likely outliers)
- Cross-collection naming collisions
- Gaps vs. the expected token palette for the design system category

`dd accept-all` is the bulk-accept path for trusted extractions. For
production usage the operator (designer or design-system engineer)
reviews the report and accepts / renames / merges / rejects
interactively. Accepted tokens become rows in `tokens` +
`token_values` + (if multi-mode) `token_modes`.

### 6.4 Bind

With tokens in place, `dd validate` (and the implicit bind pass that
runs inside every pipeline step that touches bindings) matches raw
values in `node_token_bindings` back to accepted tokens and writes
the `token_id` column. After this pass, L2 is populated: every
property whose value matches an accepted token is a reference rather
than a literal.

The renderer's progressive fallback picks up the reference
automatically — a node property with a non-null `token_id` emits as
a live variable binding in Figma, a `var(--name)` in CSS, a theme
reference in SwiftUI, and so on.

### 6.5 Push

`dd push` completes the round-trip on the token layer itself. It
emits a two-phase manifest:

1. **Variables phase.** Create each accepted token as a Figma
   variable, with the correct collection and mode structure. The
   push script writes to Figma via the Plugin API and returns a
   mapping `{token_name → figma_variable_id}`.
2. **Rebind phase.** For every L2-bound node in the generated screen,
   bind the property to the newly-created variable by id. After push,
   the Figma file has live variables and live bindings.

The two-phase approach matters because Figma's variable system
requires ids to be known before rebinds can be issued, and ids only
exist after the variable-creation call succeeds. Splitting keeps
both phases idempotent and survives Figma state being partially
stale from prior runs (`--writeback` reconciles ids).

### 6.6 Why this pipeline is shared, not duplicated per renderer

The result is that every renderer reads token-annotated IR — they
don't each re-implement clustering. React emits `var(--color-accent)`;
SwiftUI emits `.accentColor`; Figma emits a live variable binding.
Same token graph, same bindings, different native syntax. This is
the M × N → M + N property of the IR applied to the token layer.

---

## 7. Round-Trip: The Foundational Requirement

**Nothing else matters until round-trip works.** No cross-platform renderers, no L3 format spec, no React/SwiftUI backends, no prompt-based generation. The entire compiler model rests on one proof: Figma → DB → Figma produces a visually identical screen.

If we cannot faithfully reproduce a screen from our own database, the data is untrustworthy, the IR is unproven, and every downstream consumer inherits those errors. Round-trip fidelity is the foundation that everything else builds on.

### The Test

Extract screen 184 from the Dank file into the DB. Generate Figma Plugin API JavaScript from the DB. Execute it in Figma. The result must be visually indistinguishable from the original at 1:1 zoom.

### Current Status (2026-04-16)

**Full-corpus round-trip parity: 204 / 204 app screens at `is_parity = True`** on Dank (Experimental). Zero structural drift, zero visual drift, zero structured errors, zero walk failures, zero generate failures. 449s to sweep the entire corpus (2.2 s / screen average). The sweep is reproducible: `python3 render_batch/sweep.py --port N`.

The renderer implements progressive fallback with three-phase emit architecture:

- **L0 → L1 → L2 fallback**: All nodes enter the IR via LEFT JOIN. L1/L2 enrich as annotations, never filter.
- **Mode 1 instances**: Real component instances via prefetched `getNodeByIdAsync()` handles + `createInstance()`, with full override application. 17 override types, 57K+ override rows emitted per full run. Missing-master resolution emits a wireframe placeholder (visible grey-bordered frame with 45° architectural hatch) rather than silent blank.
- **Mode 2 frames**: Created from L0 properties with registry-driven visual emission.
- **Property registry** (`dd/property_registry.py`): Single source of truth for every Figma property. Extraction, query, renderer, and capability gating all reference it.
- **Capability-gated emission** (ADR-001): Every property has a per-backend capability table. `is_capable()` is the single source of truth at every emit site, and doubles as a constrained-decoding grammar for synthetic IR generation.
- **Null-safe Mode 1** (ADR-002): Every `createInstance()` is null-guarded; per-op micro-guards wrap every runtime write so a single property failure pushes a `KIND_*` structured error rather than aborting the render.
- **Explicit state harness** (ADR-003): Generated scripts capture host state (page, manifest, error channel) into locals at entry. Never read ambient globals after prefetch begins.
- **Unified verification channel** (ADR-007): Three verification positions — codegen degradation at generate time, runtime micro-guards at render time, `RenderVerifier` walking the rendered subtree post-render — all write into the same structured `__errors` / `RenderReport` surface with per-node granularity. `is_parity = True` is the gating contract for "round-trip successful."
- **Default clearing**: `fills=[]` and `clipsContent=false` explicitly set to override Figma's `createFrame()` defaults.
- **Layout sizing**: Ground-truth from DB extraction (~80 K nodes with explicit sizing). No heuristic inference. Pixel dimensions default to FIXED. Emitted at lowering time (post-appendChild) when parent context is known.
- **Font style**: Ground-truth from DB (`fontName.style`), normalized per family (Inter "Semi Bold", SF Pro "Semibold", Baskerville "SemiBold").
- **Three-phase renderer**: Materialize → Compose → Hydrate. Phase 3 internal ordering: resize/position before `text.characters` so FILL text descendants reflow at correct ancestor widths.
- **DB parent chain**: Tree structure from `parent_id` only; SCI used for classification only. Eliminates skip-level wiring where SCI `parent_instance_id` jumped over unclassified INSTANCE nodes.
- **Destructive-op safeguards**: Render harness resolves output page by name (never trusts `figma.currentPage`, which `getNodeByIdAsync` side-effects). Cross-page relocate uses an explicit id manifest, not a snapshot-diff heuristic.

### Verification ≠ happy path

The 204 / 204 claim is the product of the unified verification channel
(ADR-007), not "the render didn't throw." Every failure mode has a
named `KIND_*`:

- **Codegen-time:** `KIND_DEGRADED_TO_MODE2` (a Mode 1 lookup fell through), `KIND_CKR_UNBUILT`, `KIND_OPENTYPE_UNSUPPORTED`, `KIND_GRADIENT_TRANSFORM_MISSING`, `KIND_COMPONENT_MISSING`.
- **Runtime (per-op micro-guards):** `text_set_failed`, `resize_failed`, `position_failed`, `constraint_failed`, `fills_set_failed`, plus every property write gets its own guard that pushes `{eid, kind, error}` into `__errors`.
- **Post-render (`RenderVerifier`):** `KIND_BOUNDS_MISMATCH` (text wrapped when it shouldn't have), `KIND_FILL_MISMATCH` (rendered SOLID color differs from IR), `KIND_STROKE_MISMATCH`, `KIND_EFFECT_MISSING`, `KIND_MISSING_ASSET` (vector with no fill/stroke geometry).

`is_parity` requires all three channels empty for every node in the IR. The 204 / 204 sweep means 204 screens × ~90 nodes/screen ≈ 18,000 per-node parity checks passed simultaneously.

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

## 8. Prior Art and Influences

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

## 9. File Structure

```
dd/                          # Python source
  property_registry.py       # Single source of truth for every Figma property
                             #   (emit pattern, capability gate, override type)
  boundary.py                # ADR-006: IngestAdapter + ResourceProbe protocols,
                             #   StructuredError, IngestResult, FreshnessReport
  visual.py                  # Renderer-agnostic visual dict (build_visual_from_db)
  ir.py                      # IR generation, query_screen_visuals,
                             #   build_composition_spec, override tree
  renderers/
    figma.py                 # Figma Plugin API renderer (three-phase JS emission)
  verify_figma.py            # ADR-007: RenderVerifier, RenderReport, per-node
                             #   parity check against rendered subtree walk

  # Extraction
  extract.py                 # Figma extraction orchestrator
  ingest_figma.py            # ADR-006 Figma adapter (FigmaIngestAdapter,
                             #   FigmaResourceProbe); optional parallel fetch
  figma_api.py               # REST client with 429 retry + jitter; REST
                             #   components-map → component_key at ingest
  extract_screens.py         # Per-screen processing, node-tree conversion
  extract_supplement.py      # Legacy Plugin-API pass (supplement); kept for
                             #   incremental re-extraction
  extract_targeted.py        # Legacy targeted passes (properties | sizing |
                             #   transforms | vector-geometry); kept for
                             #   incremental re-extraction
  extract_plugin.py          # Unified Plugin-API pass (supplement + targeted
                             #   in two slices: light + heavy). Post-processes
                             #   via process_vector_geometry.
  extract_assets.py          # Content-addressed asset store; SVG paths, raster

  # Analysis
  classify.py                # Classification cascade (L1)
  classify_rules.py          # Catalog-matched rules
  classify_heuristics.py     # Heuristic match
  classify_llm.py            # LLM fallback
  classify_vision.py         # Vision-model fallback (screenshot-based)
  classify_skeleton.py       # Structural-skeleton match
  catalog.py                 # Component type catalog (48 types)
  templates.py               # Master-component template extraction;
                             #   component_key_registry build
  cluster.py + cluster_*.py  # Token clustering (colors, spacing, typography,
                             #   radius, effects, misc)
  color.py                   # Color math (hex ↔ rgba ↔ oklch)

  # Token egress
  curate.py + curate_report.py  # Token proposal review
  export_*.py                # Token export (CSS, DTCG, Figma variables)
  export_rebind.py           # Two-phase push manifest generator
  rebind_prompt.py           # Token rebinding for generated screens

  # Generation
  prompt_parser.py           # Prompt → component list (L3 ingress)
  compose.py                 # Compose screen from component list

  # Infrastructure
  _timing.py                 # StageTimer, JSONL longitudinal log
                             #   at ~/.cache/dd/extract_timings.jsonl
  cli.py                     # dd entry point (every subcommand)
  db.py                      # Connection, init, migration runner

migrations/
  001..010_*.sql             # Additive schema migrations

schema.sql                   # Base DB schema (L0 scene graph + L1/L2 tables
                             #   + asset registry + token pipeline tables)

render_test/                 # Script runner + walker harness
  run.js                     # Executes a generated script on the bridge
  walk_ref.js                # Runs script + walks rendered subtree →
                             #   rendered-ref JSON for dd verify

render_batch/
  sweep.py                   # Corpus driver: per-screen generate → walk →
                             #   verify → aggregate. Writes summary.json.

README.md                    # High-level introduction (start here)
docs/
  compiler-architecture.md   # THIS document — technical spec
  architecture-decisions.md  # ADRs 001..007 + chapter history (pt 1..pt 6)
  module-reference.md        # Per-module inventory + public API
  cross-platform-value-formats.md  # Per-renderer value transforms
  extract-performance.md     # Measured pipeline timings
  roadmap.md                 # What's next
  research/                  # Research notes
  archive/                   # Superseded documents

tests/                       # 1,979 tests
```

---

## 10. Glossary

| Term | Definition |
|------|-----------|
| **L0** | Level 0 — the DB scene graph. Complete, lossless node tree. 77 columns, ~87 K rows on the test corpus. |
| **L1** | Level 1 — classification annotations. Semantic types on L0 nodes via `screen_component_instances`. |
| **L2** | Level 2 — token binding annotations. Design-token refs on properties via `node_token_bindings`. |
| **L3** | Level 3 — semantic tree. Compact, human/LLM-readable component tree. Target format for synthetic generation. |
| **Mode 1** | Component instance rendering via a prefetched `getNodeByIdAsync` handle + `createInstance()`. Visual tree inherited from the master. Cheapest when the design system has real masters. |
| **Mode 2** | Frame/shape construction via `createFrame()` + explicit property setters. Fallback when the instance-to-master lookup fails. |
| **CKR** | Component-key registry. SQLite table mapping a Figma component's persistent `key` (stable across file edits) to a live `figma_node_id` (may change). Mode 1 lookup table. |
| **Frontend** / **Extractor** | A pass that reads a source format into the IR. Currently: Figma. |
| **Backend** / **Renderer** | A pass that writes the IR to a target format. Currently: Figma. Planned: React, SwiftUI, Flutter. |
| **Progressive lowering** | Transforming high-level IR (L3) to lower-level (L0) by filling in details. |
| **Progressive fallback** | Renderer reads the highest IR level available for each property and falls back to lower levels for missing data. L3 → L2 → L1 → L0. |
| **Three-phase emit** | Renderer architecture: **Materialise** (every node created as a standalone entity), **Compose** (tree wired via appendChild), **Hydrate** (resize/position, then text characters). Works around Figma Plugin API ordering constraints structurally. |
| **Round-trip** | Source → IR → Source with zero loss. The foundational correctness test. Proves all IR levels. |
| **`is_parity`** | Output of the post-render verifier. `True` iff every node in the IR has a matching node in the rendered subtree with matching structural and visual properties, and zero structured errors were recorded anywhere in the pipeline. Gating criterion for "round-trip successful." |
| **`KIND_*`** | Vocabulary of structured error types (`KIND_COMPONENT_MISSING`, `KIND_MODE1_DEGRADED`, `KIND_BOUNDS_MISMATCH`, ...). Every failure mode in the pipeline has exactly one kind. Populates `__errors` arrays at codegen / runtime / post-render. |
| **`RenderReport`** | Per-screen verifier output: `{backend, ir_node_count, rendered_node_count, is_parity, parity_ratio, errors[]}`. Produced by `dd verify`. |
| **Design token** | A named, reusable value (color, spacing, font) that can be resolved differently per theme / platform. |
| **Scene graph** | The complete node tree with all visual, layout, and structural properties. |
| **Boundary contract** | ADR-006. Every external-system edge (ingest from Figma, resource-freshness probe, eventually synthetic-IR validation) runs through an adapter that converts failures into structured entries rather than crashes. |
| **Capability gate** | ADR-001. Per-backend capability table on every property. `is_capable()` answers "can this backend express this property on this node type?" at every emit site. Doubles as a constrained-decoding grammar for synthetic generation. |
| **Component key** | Figma's stable persistent identifier for a component (alphanumeric, survives edits / renames). As of pt 6 this is populated at REST-ingest time from the response's `components` map — no Plugin-API round-trip needed. |
| **Unified Plugin pass** | `dd extract-plugin` — the pt 6 consolidation of 5 legacy Plugin-API passes (supplement, properties, sizing, transforms, vector-geometry) into 2 slices (light + heavy) on one walker. 2.25× faster than the old pipeline. |
| **Placeholder** | Wireframe (grey-bordered frame with 45° architectural hatch + name label) emitted when a component reference can't resolve to a master at render time. Visible to human review rather than silent blank. Gated via `setPluginData('__ph', '1')` so downstream overrides don't clobber it. |
