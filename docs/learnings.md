# Learnings Log

Active insights for the compiler and round-trip renderer. Token pipeline learnings (T1-T4) archived to `docs/archive/learnings-token-pipeline.md`.

---

## Extraction Pipeline

### Two-Path Extraction is Necessary

The Figma REST API and Plugin API return different property sets. `componentKey`, `layoutPositioning`, and Grid properties are Plugin API-only. A single extraction command can't get everything.

**Solution**: Two-step workflow. Step 1 (`dd extract`) uses the REST API — fast, reliable, batches 10 screens per HTTP request, gets ~90% of properties. Step 2 (`dd extract-supplement`) uses the Plugin API via Desktop Bridge — targeted, compact, gets only the fields REST can't.

**Why not Plugin API for everything?** The Plugin API requires Figma Desktop open with the bridge plugin active. It has a ~64KB response limit per call. It's slower. The REST API is more reliable for bulk extraction.

### Figma's Async API is Now Required

`figma.getNodeById` (sync) fails with "Cannot call with documentAccess: dynamic-page." Use `figma.getNodeByIdAsync` instead. Same for `node.mainComponent` → `node.getMainComponentAsync()`.

### Response Truncation at 64KB

The PROXY_EXECUTE WebSocket truncates responses at ~64KB. Auto-batching with truncation detection: start at batch_size=5, halve on truncation, fall back to batch_size=1. `run_supplement()` handles this automatically.

### Screen Classification Matters

Not all "screens" are app screens. `screen_type` column classifies by dimensions: `app_screen` (≥350×≥700), `icon_def` (≤40×40), `design_canvas` (>2000), `component_def` (everything else). Only `app_screen` enters the rendering pipeline.

---

## Architecture

### CLI for Deterministic, Agent for Judgment

Extraction, clustering, validation, export = CLI commands. Renaming, merging, splitting, aliasing = Agent operations. The curation report bridges them.

### Color State Derivation Should Use OKLCH, Not HLS

HLS lighten/darken produces inconsistent visual shifts. OKLCH manipulates perceptual lightness, preserving hue and chroma.

### Generated Tokens Need a Separate Collection

Component state tokens live in a separate collection from base primitives. Primitives → Semantic → Component layers.

---

## T5 Compositional Analysis

### IR Design: Visual Intent, Not Token Transport

The IR must carry complete visual properties for every element. Token refs are annotations, not the primary data source. Many Figma files have zero tokenized values — the IR must work without any tokens.

### Figma Frames Are Visual Elements

In Figma, a frame IS the visual element. "Frame 359" with a gradient fill and corner radius is a styled card, not a structural container. 64% of generic-named frames have fills, strokes, or corner radius. `rule_generic_frame_container()` must check for visual properties before classifying.

### Component Instances Across Platforms

The IR stores canonical type + props. Each platform renderer resolves to native components independently. Figma → `importComponentByKeyAsync(key)`. React → `<Icon name="arrow-left" />`. SwiftUI → `Image(systemName: "chevron.left")`.

### figma_execute Async Model

Use top-level `await`, not `(async () => {...})()`. The MCP `figma_execute` tool provides its own async context.

### Token Alias Resolution

Use `ntb.resolved_value` from `node_token_bindings` directly, not `token_values`. Aliased tokens don't have their own `token_values` rows.

### Classification Accuracy

Formal matching: 55%. Heuristics: 37%. LLM (Claude Haiku): 7%. Final: 93.6% adjusted coverage.

---

## Round-Trip Renderer (2026-04-06)

### Selective Property Propagation — The Systemic Pattern

Every bug followed the same pattern: a property was handled at some pipeline layers but missed at others. Fix: `dd/property_registry.py` — a single authoritative list that all layers reference.

### Figma Default Leak Pattern

`figma.createFrame()` creates frames with `clipsContent=true` and a white fill. The renderer must EXPLICITLY set `fills=[]` and `clipsContent=false` when the DB value differs.

### layoutSizing Requires Parent Context — But Not Always

Auto-layout containers CAN set their own layoutSizing before appendChild. Non-auto-layout children must defer to post-appendChild.

### Figma Override Field Name Aliases

`overriddenFields` uses different names: `primaryAxisSizingMode` → `layoutSizingHorizontal`, `counterAxisSizingMode` → `layoutSizingVertical`. The property registry stores both.

### Rotation: REST API = Radians, Plugin API = Degrees

REST API: radians (-π to π). Plugin API: degrees (-180 to 180). Renderer converts via `math.degrees()` with sign negation.

### Mode 1 Instances Need L0 Properties

After `createInstance()`, the instance inherits master defaults. L0 properties (rotation, opacity, visibility) must be applied directly — they're not "overrides" in Figma's sense.

### PROXY_EXECUTE Reliability — ROOT CAUSED

Not a reliability bug — timeout. Scripts take >120s due to `findOne` tree searches. With override grouping (37-44% findOne reduction), execution drops to 0.7-3.9s. Cold-start pays ~170s; warm cache: 0.7s.

### Font Style Naming

`normalize_font_style(family, style)` maps per-family: SF Pro → "Semibold", Baskerville → "SemiBold", Inter → "Semi Bold". Verified against `figma.listAvailableFontsAsync()`.

### Override Decomposition at Query Time

Override `property_name` is composite `{target}{suffix}`. Decompose at query time using `override_suffix_for_type()` from the same code that created the composite. Key lesson: when a pipeline stage encodes information, the stage that decodes it must use the same encoding knowledge. A hardcoded second map will always drift.

### Gradient Fill Emission Requires Two Data Formats

REST API: `gradientHandlePositions` (3 points). Plugin API: `gradientTransform` (2x3 matrix). Store BOTH. **ORDERING RISK**: supplement must run AFTER REST extraction.

### Token Refs Without L0 Fallback

`_resolve_text_value()` implements progressive fallback: L2 (resolved token) → L0 (DB value). Previously, missing tokens caused properties to be skipped entirely.

### Per-Corner Radius Was Silently Dropped

`normalize_corner_radius` returns a dict for asymmetric corners but emission only handled scalars. Now emits `topLeftRadius`, `topRightRadius`, etc.

### Unpublished Components Need Fallback Chain

`importComponentByKeyAsync` only works for published components. Fallback: component_figma_id → instance figma_node_id + `getMainComponentAsync()` → Mode 2 createFrame.

### Registry-Driven Emission — The Architectural Fix

Three emission categories: Template (uniform format, type-aware via `format_js_value()`), Handler (dispatch dict), Deferred (empty dict). `build_visual_from_db` is registry-driven. Structural tests enforce classification.

Key lesson: naive Python string formatting for JS emission produces invalid code (Python `True` vs JS `true`). The formatter must be type-aware.

### Alpha Channel Lost at the Final Mile

`hex_to_figma_rgb()` dropped alpha from 8-digit hex. Data was correct through the entire pipeline — only lost in the last conversion step. Lesson: when round-trip produces wrong output, check the final mile first.

### textAutoResize and layoutSizing Are Interdependent

`_TEXT_AUTO_RESIZE_SIZING` lookup table + `_resolve_layout_sizing` pure function. `WIDTH_AND_HEIGHT` → HUG/HUG, `HEIGHT` → FILL/HUG.

### Inter Variable vs Inter — Subtle Font Width Difference

"Inter Variable" renders slightly narrower than "Inter" at the same weight. Known minor fidelity gap.

### No Value Transform Is Universal

Every value transform is platform-specific. IR stores ground truth (radians, hex, numeric weight, {value, unit}). Each renderer transforms to native format. See `docs/cross-platform-value-formats.md`.

### getNodeByIdAsync Works with Instance-Prefixed IDs (Undocumented)

O(1) lookup for instance children. Undocumented — recorded as future optimization, not adopted for stability.

---

## Renderer Architecture (Session 8)

### Ground-Truth Sizing Replaces Heuristic Inference

The `parent_is_autolayout` heuristic caused 17K+ nodes to stretch incorrectly. Re-extraction gave 95% coverage (79,833 nodes). Pixel dimensions default to FIXED. Lesson: extract ground truth, don't infer from context.

### layoutSizing Is a Parent-Context-Dependent Property

Matches universal pattern: LLVM (legalization), Flutter (`flex` inert unless parent is `RenderFlex`), CSS (`flex-grow` ignored without `display:flex`). Store intent in IR; emit at lowering time when parent context is known.

### Figma Plugin API: FILL Children Before HUG Width = Zero-Width Text

Root cause of vertical text. Fix: three-phase rendering where text characters are set in Phase 3 after tree composition in Phase 2.

### Three-Phase Rendering Eliminates Ordering Bugs Structurally

Materialize (create nodes, intrinsic properties) → Compose (appendChild, layoutSizing) → Hydrate (text characters, position). Platform-specific by design.

### Phase 3 Internal Ordering: Resize Before Characters

Resize/position must precede text `.characters` assignment. FILL text descendants need ancestor widths established before content is set.

### clipsContent Default: False When DB Has NULL

Unexpected clipping is more destructive than missing clipping. Same "fail open" principle as default fills clearing.

### Font Style: Ground-Truth with Per-Family Normalization

`normalize_font_style` canonicalizes all semibold variants to "Semi Bold" first, then maps to family-specific form. Bidirectional.

### SCI Parent Wiring Bypasses Unclassified INSTANCE Nodes

Tree structure always from DB `parent_id`, SCI for classification only. Eliminates skip-level wiring.
