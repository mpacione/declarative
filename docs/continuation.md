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

### Architecture Discovery & Refinement
- **DB IS L0** — The `nodes` table with 72 columns IS Level 0 of the IR. Not a separate data structure — the table itself is the scene graph. L1, L2, L3 are annotations stored in separate tables that enrich L0.
- **Progressive fallback model** — Renderers read from the highest IR level available and fall back to lower levels: L2 (tokens) → L1 (classification) → L0 (raw values). L0 is always the safety net. This applies to ALL renderers, not just Figma.
- **Round-trip proves the full stack** — The Figma renderer exercises L2 (token variable binding), L1 (component createInstance), and L0 (raw property application) via progressive fallback. Success validates all levels.
- **The IR exists for the M×N problem** — Without the IR, 5 frontends × 5 backends = 25 translators each reimplementing classification, token binding, and semantic compression. With the IR, analysis is written once and shared.
- **Current break is a query/wiring bug, not an architecture bug** — `query_screen_for_ir()` INNER JOINs on L1 classification (dropping unclassified nodes). Fix: LEFT JOIN L1/L2 as annotations on the L0 tree.
- **Compiler model validated** — Mitosis (behavioral IR), Ghost (SDUI), USD (composition arcs) each solve parts. Nobody combines all with design tool support.

### Research Completed
- Format comparison: 8 formats side-by-side (YAML recommended for now, KDL for future)
- Constrained decoding (XGrammar ICML 2025) guarantees valid structured output
- SDUI architecture briefing (Airbnb, Lyft, Netflix, DoorDash, Spotify)
- KDL deep dive, Mitosis deep dive, compiler primer

## What To Do Next

### THE ONLY PRIORITY: Round-Trip Fidelity

Nothing else matters until a screen goes Figma → DB → Figma and comes back as a **semantically equivalent design file** — with live token variables, real component instances, proper naming, and visual fidelity. Not a flat photocopy of rectangles with hex colors.

### Architectural Principle: Progressive Fallback

The round-trip renderer uses **all IR levels** via progressive fallback (see `compiler-architecture.md` Section 5):

```
L2 (token bindings)  → Figma variables (live, themeable)
  ↓ fallback
L1 (classification)  → createInstance() (real components with variants)
  ↓ fallback
L0 (raw DB values)   → createFrame/Rectangle/Text with literal values
```

Every property reads from the highest level available. L0 is the safety net — complete and lossless. The result is a working Figma file, not a dead screenshot.

### The Fix: What to Change in Existing Code

The rendering building blocks work: `build_visual_from_db()`, `_emit_visual()`, `_emit_layout()`, `_emit_fills/strokes/effects()`. The break is in how the tree walk is sourced.

**Root cause**: `generate_screen()` → `generate_ir()` → `query_screen_for_ir()` INNER JOINs on `screen_component_instances`, dropping 89/203 nodes. Then `build_composition_spec()` wires the tree via `parent_instance_id` (L1) instead of `parent_id` (L0). The renderer walks this lossy IR tree.

**What needs to change** (in existing modules, no new modules):

1. **`query_screen_for_ir()` in `dd/ir.py`**: Must fetch ALL nodes for the screen (L0 complete tree), not just classified ones. L1 classification and L2 bindings are LEFT JOINed as annotations — present when available, NULL when not. The query result carries all levels in one pass.

2. **`build_composition_spec()` in `dd/ir.py`**: Must wire the tree via `parent_id` (L0 structure), not `parent_instance_id` (L1 relationship). Every node gets an element in the spec. INSTANCE nodes with children in the DB get those children skipped in the walk (they're inherited from createInstance).

3. **`generate_figma_script()` in `dd/generate.py`**: For each element in the walk:
   - Check L2: does this node have token bindings? → collect for variable rebinding
   - Check L1: does this node have a component_key? → Mode 1 createInstance
   - Fallback L0: create from raw properties → Mode 2 createFrame/Rectangle/Text

4. **Token rebinding**: After structure creation, bind Figma variables using L2 data. This already exists in `dd/rebind_prompt.py` and `dd/export_rebind.py` — reuse it.

### Steps

**Step 1: Verify extraction completeness.** Compare screen 184 node-by-node against live Figma data. If anything is missing, fix extraction first.

**Step 2: Fix the query and tree assembly.** Modify `query_screen_for_ir()` to LEFT JOIN L1/L2 instead of INNER JOIN. Fix `build_composition_spec()` to wire via `parent_id`. Fix `generate_figma_script()` to implement progressive fallback (L2 → L1 → L0).

**Step 3: Execute and iterate.** Run on screen 184. Screenshot. Compare against original. Find gaps. Fix. Repeat.

**Only after round-trip is proven:** L3 format definition, additional frontends/backends, prompt-based generation.

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
