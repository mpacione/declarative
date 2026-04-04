# Continuation: Next Session

## Quick Context

Declarative Design is a bi-directional design compiler. Parses UI from any source into an abstract compositional IR, generates to any target with token-bound fidelity. T1-T4 complete (property pipeline). T5 composition layer is operational with full prompt→Figma pipeline. Three hardening sessions completed (2026-04-03/04): pipeline stress-testing, root cause fixes, quality iteration with FILL width, CLI command, ground truth comparison, and Figma execution verification.

## Current State (2026-04-04)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes (72 columns), 182,871 bindings, 388 tokens, 338 screens (204 app screens)
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental) — 374 variables, 8 collections
- **Extraction**: Complete. REST API + Plugin API supplemental.
- **Classification**: 93.6% coverage (47,292 classified nodes).
- **Composition tables**: 21 components, 49 slots, 21 a11y contracts, 109 templates (with sizing modes + child composition + screen template), 122-entry component key registry
- **Tests**: 1,389 passing (including 200+ integration tests against real Dank DB)
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

### Known Gaps
- Toggle/radio/checkbox types have no Dank templates — render as empty frames
- Header text override targets first TEXT child (may not be the right one in complex headers)
- Composition children fire but most are keyless (119/139 use container/text types)
- No non-Dank file testing yet

## What To Do Next

### High-Value Improvements
1. **Non-Dank file testing** — Verify generalizability on a second Figma file
2. **Toggle/radio/checkbox mapping** — Either find Dank components that match or provide visual fallbacks
3. **Smarter text overrides** — Target specific TEXT nodes by name/role instead of first findOne
4. **React/SwiftUI renderers** — The IR is platform-agnostic. New renderers read the same IR + a ReactRendererConfig/SwiftUIRendererConfig.
5. **Synthetic tokens** — The architecture spec describes synthetic tokens for unbound visual values.

### Quality Improvements
- Header text override should target title text, not first text node
- Composition children ordering within containers
- Multiple text overrides per component (title + subtitle)
- Empty frame fallback visuals for unsupported types

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
