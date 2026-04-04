# Continuation: Next Session

## Quick Context

Declarative Design is a bi-directional design compiler. Parses UI from any source into an abstract compositional IR, generates to any target with token-bound fidelity. T1-T4 complete (property pipeline). T5 composition layer is operational with full prompt→Figma pipeline. Three hardening sessions completed (2026-04-03/04): pipeline stress-testing, root cause fixes, quality iteration with FILL width, CLI command, ground truth comparison, and Figma execution verification.

## Current State (2026-04-04)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes (72 columns), 182,871 bindings, 388 tokens, 338 screens (204 app screens)
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental) — 374 variables, 8 collections
- **Extraction**: Complete. REST API + Plugin API supplemental.
- **Classification**: 93.6% coverage (47,292 classified nodes).
- **Composition tables**: 21 components, 49 slots, 21 a11y contracts, 109 templates (with sizing modes + child composition + screen template), 122-entry component key registry
- **Tests**: 1,475 passing (including 200+ integration tests against real Dank DB)
- **Branch**: `t5/architecture-vision`

## Architecture: Four-Layer Model — ALL LAYERS OPERATIONAL

```
Layer 1: EXTRACTION     Source → DB        ✅ Complete (86K nodes, 72 columns)
Layer 2: ANALYSIS        DB → Abstractions  ✅ Complete + Hardened (48 types, 109 templates, 49 slots, key registry)
Layer 3: COMPOSITION     Abstractions → IR   ✅ Complete + Hardened (thin IR, prompt parsing, project vocabulary, validation)
Layer 4: RENDERING       IR + DB/Config → Output  ✅ Complete + Hardened (Mode 1 + Mode 2 + composition children + token rebinding + FILL width)
```

## Full Pipeline (End-to-End)

```
Natural language prompt ("build me a settings page with toggle sections")
    ↓ dd/prompt_parser.py — Claude Haiku + project vocabulary + screen archetypes
Component list [{type: "header"}, {type: "card", children: [...]}, ...]
    ↓ dd/compose.py — validate_components() + compose_screen() + build_template_visuals()
CompositionSpec IR (thin, semantic, with template layout/visuals/composition)
    ↓ dd/generate.py — generate_figma_script(spec, db_visuals)
       Mode 1: getNodeByIdAsync(figma_id).createInstance() for keyed components
       Mode 2: createFrame() + template visuals + composition children for keyless types
       Container types (card, accordion, header, tabs) → FILL width automatically
    ↓ figma_execute MCP — returns M dict (element_id → figma_node_id)
Rendered screen in Figma (with background, FILL-width cards, real component instances)
    ↓ dd/rebind_prompt.py — build_template_rebind_entries() + generate_rebind_script()
Token variable rebind script
    ↓ figma_execute MCP
Variables bound to created nodes
```

## What Was Done (2026-04-04 Session)

### Quality Iteration Session
- **Card width fix**: Container types (card, accordion, header, tabs, drawer, sheet, alert, empty_state) now get `layoutSizingHorizontal="FILL"` after appendChild. Both Mode 1 instances and Mode 2 frames. 4 tests.
- **Variant selection verified**: End-to-end flow confirmed — LLM variant names → `_pick_best_template` → registry → `figma_node_id`. button/large/translucent, button/small/solid, nav/top-nav all resolve correctly.
- **CLI command**: `dd generate-prompt "your prompt" --db path.db --out file.js --page Generated`. Orchestrates the full pipeline. 4 tests.
- **Ground truth comparison**: `compare_generated_vs_ground_truth(conn, spec, screen_id)` returns structured diff report: element counts, type distributions, Mode 1/2 ratio, missing/extra types. 6 tests.
- **Figma execution verified**: Settings page with header (Mode 1), cards (Mode 2 + FILL), buttons (Mode 1 + text overrides), tabs (Mode 1). Token rebinding: 6/6 entries bound successfully.

### Visual Fidelity & Generalizability Session (2026-04-03)
- **Smart text overrides**: Mode 1 text override now searches for TEXT nodes named Title/Label/Heading first via `_build_text_finder()`, then falls back to any TEXT. Supports `text_target` prop for explicit name-based targeting and `subtitle` prop for secondary text override. 3 tests.
- **Type alias mapping**: `resolve_type_aliases()` maps 9 unsupported types to existing templates: toggle→icon/switch, checkbox→icon/checkbox-empty, radio→icon/checkbox-empty, navigation_row→button/large/translucent, icon_button→button/small/translucent, select→button/small/solid, segmented_control→nav/tabs, plus radio_group and toggle_group. `validate_components()` now resolves aliases before validation. 10 tests.
- **Generalizability proven**: 16-test suite creates a synthetic "ShopUI Kit" e-commerce project with different component names (nav-bar, product-card, primary-btn, ghost-btn, search-field), different dimensions (iPhone 15 Pro Max 430×932), and different layout patterns — verifies template query, composition, rendering (Mode 1 + Mode 2), type alias resolution, and end-to-end pipeline all work on non-Dank data.
- **Tests**: 1,418 passing (29 new tests added).

### Rendering Pipeline Fixes (2026-04-04)
- **Phase 1 — Additive visual properties**: `build_visual_from_db` + `_emit_visual` now handle clipsContent, rotation, constraints. Constraint values mapped from REST API (LEFT/TOP) to Plugin API (MIN/MAX/STRETCH). 14 tests.
- **Phase 2 — Font properties in templates**: 7 font columns added to component_templates schema + `_TEMPLATE_FIELDS`. Template pipeline extracts font_family/size/weight/style/line_height/letter_spacing/text_align. Composition wires font data through to renderer. Auto-migration for existing DBs. 12 tests.
- **Phase 3 — Absolute positioning**: Screen root uses `direction: "absolute"`, children get computed x/y positions. FILL width guarded to auto-layout parents only. IR path (`build_composition_spec`) uses relative positions from screen origin. Pixel dimensions stored alongside sizing modes via `widthPixels`/`heightPixels`. 13+ tests.
- **Phase 4 — Visibility overrides**: `query_screen_visuals` builds `hidden_children` lists (depth 1-2) for Mode 1 instances. Renderer emits `findOne → visible = false`. 5 tests.
- **Phase 6 — Composed type aliases**: Toggle/checkbox/radio expand into horizontal container rows (label + icon) instead of bare icons. `_COMPOSED_ALIASES` dict with `layout_direction` and `layout_sizing` overrides. 3+ tests.
- **A1 — Component resolution fix**: `query_screen_visuals` now JOINs `component_key_registry` to get `figma_node_id`. Renderer prefers `getNodeByIdAsync` (local components) over `importComponentByKeyAsync` (published libraries). Screen 184: 31 getNodeByIdAsync, 1 importComponentByKeyAsync. 2 tests.
- **A2 — Unclassified structural nodes**: `query_screen_for_ir` includes depth-0/1 unclassified FRAME/RECTANGLE/GROUP nodes (not system chrome INSTANCE). 2 tests.
- **Tests**: 1,475 passing (57 new).

### Known Gaps — IR Tree Fidelity
The fundamental blocker for screen reproduction is the IR tree structure. Testing `generate_screen(184)` in Figma revealed:
- **IR tree doesn't match real parent-child relationships**: The IR uses classification-based wiring (`parent_instance_id`, `parent_id`) which doesn't preserve the actual Figma node tree. Elements end up attached to the wrong parent (synthetic screen-1 root instead of the real depth-0 frame).
- **Orphaned nodes**: Classified nodes whose parents aren't in the IR get created but never appended — they float as invisible orphans.
- **Instance property overrides not extracted**: The `instance_overrides` table exists but is empty. Buttons show wrong icons because we don't capture what the designer changed from the master component.
- **Image fills not reproducible**: RECTANGLE nodes with IMAGE fills store `imageRef` but not image bytes.

### Critical Finding: The DB IS the Scene Graph
Deep audit revealed the DB nodes table (72 columns, parent_id tree, sort_order z-index) is already a complete, lossless scene graph. The IR was designed to walk the DB (architecture spec lines 836-839) but actually walks a lossy classification-based tree. `generate_screen()` calls `generate_ir()` when it shouldn't need to — the renderer should walk the DB directly.

### Multi-Level IR Design (MLIR-Inspired)
Designed a non-lossy IR architecture inspired by MLIR compiler dialects:
- **Level 0**: Full scene graph (the DB itself in tree form). For Figma reproduction.
- **Level 1**: Classification annotations on nodes. For semantic understanding.
- **Level 2**: Token binding annotations on properties. For design system portability.
- **Level 3**: Semantic tree (~20 elements with slots). For cross-platform output AND LLM generation.

Each level adds information, none removes it. Different consumers read different levels.

### Spatial Encoding (6 mechanisms identified)
1. **Position**: auto-layout (implicit) or absolute (parent-relative x,y, origin top-left 0,0)
2. **Size**: fixed/hug/fill + min/max bounds
3. **Padding**: {top, right, bottom, left} — tokenized
4. **Gap**: uniform spacing between auto-layout children
5. **Constraints**: anchoring for absolute children (min/center/max/stretch/scale)
6. **Z-order**: document order = stacking order

## What To Do Next (Priority Order)

### Priority 1: DB-Direct Renderer for Screen Reproduction
Build a `generate_screen_from_db()` that walks the DB node tree (parent_id) directly, bypassing the IR entirely. Use `query_screen_visuals()` for visual properties. This is the fastest path to faithful screen reproduction and validates the scene graph approach.

### Priority 2: Define Level 3 Format Specification
Design the human/LLM-readable semantic format. YAML-like, ~20 elements per screen, component types + nesting + token refs. Extract 204 Dank screens to Level 3 as training data.

### Priority 3: Instance Property Overrides
Extract `componentProperties` from INSTANCE nodes via Plugin API. Populate `instance_overrides` table. Renderer emits `setProperties()`.

### Priority 4: Cross-Platform Renderers
Once Level 3 spec is defined and reproduction works, build React and SwiftUI renderers that read Level 1+2+3.

## Key Files

| File | Purpose |
|------|---------|
| `docs/t5-four-layer-architecture.md` | THE authoritative architecture spec |
| `docs/module-reference.md` | Complete API reference for all modules |
| `dd/ir.py` | IR generation: `query_screen_visuals`, `_node_id_map`, `build_semantic_tree` |
| `dd/generate.py` | Figma renderer: Mode 1 + Mode 2 + `_emit_composition_children` + FILL width |
| `dd/compose.py` | Prompt composition: `compose_screen`, `build_template_visuals`, `validate_components`, `generate_from_prompt`, `compare_generated_vs_ground_truth` |
| `dd/prompt_parser.py` | LLM parsing: `parse_prompt`, `prompt_to_figma`, `build_project_vocabulary` |
| `dd/templates.py` | Template extraction: `extract_templates`, `extract_child_composition`, `build_component_key_registry`, `query_templates` |
| `dd/cli.py` | CLI: `generate-prompt` command for end-to-end prompt→Figma |
| `dd/rebind_prompt.py` | Token rebinding: `build_template_rebind_entries`, `generate_rebind_script` |
| `schema.sql` | DB schema — component_templates (31 cols), component_key_registry |

## Environment

```bash
source .venv/bin/activate

# Run all tests (1,389 expected)
python -m pytest tests/ --tb=short

# Run integration tests only
python -m pytest tests/ -m integration --tb=short

# CLI: generate from prompt
python -m dd generate-prompt "Build a settings page with toggles" --db Dank-EXP-02.declarative.db --page Generated

# Quick pipeline test (requires .env with ANTHROPIC_API_KEY)
python -c "
from dotenv import load_dotenv; load_dotenv('.env', override=True)
from dd.prompt_parser import prompt_to_figma
from dd.templates import build_component_key_registry, extract_templates
import anthropic, sqlite3
client = anthropic.Anthropic()
conn = sqlite3.connect('Dank-EXP-02.declarative.db')
conn.row_factory = sqlite3.Row
file_id = conn.execute('SELECT id FROM files LIMIT 1').fetchone()[0]
build_component_key_registry(conn)
extract_templates(conn, file_id)
result = prompt_to_figma('Build a settings page with toggles', conn, client, page_name='Generated')
print(f'Elements: {result[\"element_count\"]}, Script: {len(result[\"structure_script\"])} chars')
print(f'Warnings: {result.get(\"warnings\", [])}')
"
```

Figma Desktop Bridge plugin required for execution in Figma.
