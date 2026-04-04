# Continuation: Next Session

## Quick Context

Declarative Design is a **design system compiler** — LLVM for design systems. Multi-level IR (MLIR-inspired) with four levels: L0 (DB scene graph), L1 (classification), L2 (token bindings), L3 (semantic tree). The DB IS the scene graph. The IR annotates it, doesn't replace it.

**Authoritative spec**: `docs/compiler-architecture.md`

## Current State (2026-04-04)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes (72 columns), 182,871 bindings, 388 tokens, 338 screens (204 app screens)
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental) — 374 variables, 8 collections
- **Extraction**: Complete. REST API + Plugin API supplemental.
- **Classification (L1)**: 93.6% coverage (47,292 classified nodes)
- **Token Bindings (L2)**: 182,871 bindings, 388 tokens
- **Tests**: 1,475 passing
- **Branch**: `t5/architecture-vision`

## What Was Built (2026-04-04 Session)

### Rendering Pipeline Fixes (57 new tests)
- clipsContent, rotation, constraints (with REST→Plugin API value mapping)
- Font properties in templates (7 columns, auto-migration)
- Absolute positioning (screen root, x/y from DB, relative to screen origin)
- Visibility overrides (hidden_children query, findOne→visible=false)
- Composed type aliases (toggle/checkbox → horizontal container rows)
- Component resolution (query_screen_visuals JOINs registry → getNodeByIdAsync)
- Unclassified structural nodes (depth-0/1 FRAME/RECTANGLE in IR)

### Architecture Discovery
- **DB IS the scene graph** — 72 columns, parent_id tree, sort_order z-index. Complete and lossless.
- **Renderer was designed to walk DB but walks IR instead** — architecture spec says DB, code does IR. This divergence breaks reproduction.
- **IR tree is lossy by design** — classification-based wiring drops 43% of nodes, rewires parent-child. Correct for semantic abstraction, wrong for reproduction.
- **Multi-level IR design** — MLIR-inspired. L0=DB, L1=classification, L2=tokens, L3=semantic. Each level adds, none removes.
- **Compiler model validated** — Mitosis (behavioral IR), Ghost (SDUI), USD (composition arcs) each solve parts. Nobody combines all with design tool support.

### Research Completed
- Format comparison: 8 formats side-by-side (YAML recommended for now, KDL for future)
- Constrained decoding (XGrammar ICML 2025) guarantees valid structured output
- SDUI architecture briefing (Airbnb, Lyft, Netflix, DoorDash, Spotify)
- KDL deep dive, Mitosis deep dive, compiler primer

## What To Do Next

### Step 1: Verify Extraction Completeness
Confirm that the DB captures everything from Figma with zero loss. Compare a real Figma screen against its DB representation node-by-node. If anything is missing, fix extraction first.

### Step 2: DB-Direct Renderer (Round-Trip)
Build `generate_screen_from_db()` that walks the `parent_id` tree directly, bypassing the IR. Use `query_screen_visuals()` for visual properties. For INSTANCE nodes, use `getNodeByIdAsync`. The test: execute on screen 184, screenshot, compare against original. Must achieve 100% structural + visual fidelity.

### Step 3: MLIR Spec with Diagrams
Expand `docs/compiler-architecture.md` with detailed diagrams showing data flow between levels, examples of each level for the same screen, and the formal schema for L3 (YAML).

### Step 4: L3 Format Definition
Define the YAML schema for Level 3. Extract screen 184 into L3 format. Verify it contains enough information for the React renderer to produce equivalent output.

### Step 5: First Cross-Platform Backend
Build the simplest possible React renderer that reads L1+L2 and produces JSX + CSS with design token CSS custom properties. Verify: same screen, same layout, same tokens — different platform.

## Key Files

| File | Purpose |
|------|---------|
| `docs/compiler-architecture.md` | THE authoritative architecture spec |
| `docs/module-reference.md` | Complete API reference for all modules |
| `dd/ir.py` | IR generation, query_screen_visuals, build_composition_spec |
| `dd/generate.py` | Figma renderer (generate_figma_script, generate_screen) |
| `dd/compose.py` | Prompt composition (compose_screen, validate_components) |
| `dd/templates.py` | Template extraction (extract_templates, query_templates) |
| `schema.sql` | DB schema (L0 scene graph + L1/L2 annotation tables) |

## Environment

```bash
source .venv/bin/activate
python -m pytest tests/ --tb=short          # 1,475 tests
python -m dd generate-prompt "prompt" --db Dank-EXP-02.declarative.db --page Generated
```
