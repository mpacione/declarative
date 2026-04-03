# Continuation: Next Session

## Quick Context

Declarative Design is a bi-directional design compiler. Parses UI from any source into an abstract compositional IR, generates to any target with token-bound fidelity. T1-T4 complete (property pipeline). T5 composition layer is now operational — full prompt→Figma pipeline working.

## Current State (2026-04-02)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes (72 columns), 182,871 bindings, 388 tokens, 338 screens (204 app screens)
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental) — 374 variables, 8 collections
- **Extraction**: Complete. REST API + Plugin API supplemental. 60K constraints, 25K component keys populated.
- **Classification**: 93.6% coverage (47,292 classified nodes). Zero missed on app screens.
- **Composition tables**: 21 components, 49 slots, 21 a11y contracts, 108 templates, 8,870 linked instances.
- **Tests**: 1,325 passing (including 200+ integration tests against real Dank DB)
- **Branch**: `t5/architecture-vision`

## Architecture: Four-Layer Model — ALL LAYERS OPERATIONAL

```
Layer 1: EXTRACTION     Source → DB        ✅ Complete (86K nodes, 72 columns)
Layer 2: ANALYSIS        DB → Abstractions  ✅ Complete (48 types, 108 templates, 49 slots)
Layer 3: COMPOSITION     Abstractions → IR   ✅ Complete (thin IR, semantic tree, prompt parsing)
Layer 4: RENDERING       IR + DB/Config → Output  ✅ Complete (Mode 1 instances + Mode 2 frames + token rebinding)
```

Key decisions: thin IR (no visual section), semantic tree (116→20 elements with named slots), renderer reads DB directly for visual detail, Mode 1 component instances via `getNodeByIdAsync`, Mode 2 frame construction from templates, LLM prompt parsing via Claude Haiku, screen pattern enrichment, token variable rebinding.

## Full Pipeline (End-to-End)

```
Natural language prompt ("build me a settings page with toggle sections")
    ↓ dd/prompt_parser.py — Claude Haiku + project screen patterns
Component list [{type: "header"}, {type: "card", children: [...]}, ...]
    ↓ dd/compose.py — compose_screen() + build_template_visuals()
CompositionSpec IR (thin, semantic, with template layout/visuals)
    ↓ dd/generate.py — generate_figma_script(spec, db_visuals)
Figma JS (Mode 1 instances + Mode 2 frames)
    ↓ figma_execute MCP — returns M dict (element_id → figma_node_id)
Rendered screen in Figma
    ↓ dd/rebind_prompt.py — build_rebind_entries() + generate_rebind_script()
Token variable rebind script
    ↓ figma_execute MCP
Variables bound to created nodes
```

## What To Do Next

### Testing & Hardening
- Execute the full pipeline end-to-end with various prompts, verify Figma output quality
- Test Mode 1 rendering with more component types (icons, drawer, button_group)
- Test token rebinding execution in Figma (Phase B)
- Test edge cases: empty prompts, invalid types, very complex screens
- Test on non-Dank Figma files to verify generalizability

### Potential Improvements
- Text overrides on Mode 1 instances (set label text on buttons)
- Mode 1 for icons (82 templates with keys — currently skipped because icons are children)
- Variant selection on Mode 1 instances (select button size/style)
- CLI command: `dd generate-prompt "build me a settings page" --db Dank-EXP-02.declarative.db`
- React/SwiftUI renderers (the IR is platform-agnostic — add new renderers)

## Key Files

| File | Purpose |
|------|---------|
| `docs/t5-four-layer-architecture.md` | THE authoritative architecture spec |
| `docs/module-reference.md` | Complete API reference for all modules |
| `dd/ir.py` | IR generation: `query_screen_visuals`, `_node_id_map`, `build_semantic_tree`, `filter_system_chrome` |
| `dd/generate.py` | Figma renderer: Mode 1 (`getNodeByIdAsync`) + Mode 2 (`createFrame`), `build_visual_from_db` |
| `dd/compose.py` | Prompt composition: `compose_screen`, `build_template_visuals`, `generate_from_prompt` |
| `dd/prompt_parser.py` | LLM parsing: `parse_prompt`, `prompt_to_figma`, `extract_json` |
| `dd/templates.py` | Template extraction: `extract_templates`, `query_templates`, `compute_mode_template` |
| `dd/screen_patterns.py` | Screen archetypes: `extract_screen_archetypes`, `get_archetype_prompt_context` |
| `dd/rebind_prompt.py` | Token rebinding: `build_rebind_entries`, `generate_rebind_script`, `query_token_variables` |
| `dd/export_rebind.py` | Existing rebind infrastructure (compact encoding, 182K bindings) |
| `tests/test_*_integration.py` | 200+ real-DB integration tests across all phases |

## Environment

```bash
source .venv/bin/activate

# Run all tests (1,325 expected)
python -m pytest tests/ --tb=short

# Run integration tests only
python -m pytest tests/ -m integration --tb=short

# Quick pipeline test (requires .env with ANTHROPIC_API_KEY)
ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2) python -c "
from dd.prompt_parser import prompt_to_figma
import anthropic, sqlite3
client = anthropic.Anthropic()
conn = sqlite3.connect('Dank-EXP-02.declarative.db')
conn.row_factory = sqlite3.Row
result = prompt_to_figma('Build a settings page with toggles', conn, client)
print(f'Elements: {result[\"element_count\"]}, Script: {len(result[\"structure_script\"])} chars')
"
```

Figma Desktop Bridge plugin required for execution in Figma.
