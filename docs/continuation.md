# Continuation: Next Session

## Quick Context

Declarative Design is a bi-directional design compiler. Parses UI from any source into an abstract compositional IR, generates to any target with token-bound fidelity. T1-T4 complete (property pipeline). T5 composition layer is operational with full prompt→Figma pipeline. Two hardening sessions completed (2026-04-03): pipeline stress-testing, root cause fixes, ground truth comparison methodology established.

## Current State (2026-04-03)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes (72 columns), 182,871 bindings, 388 tokens, 338 screens (204 app screens)
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental) — 374 variables, 8 collections
- **Extraction**: Complete. REST API + Plugin API supplemental.
- **Classification**: 93.6% coverage (47,292 classified nodes).
- **Composition tables**: 21 components, 49 slots, 21 a11y contracts, 109 templates (with sizing modes + child composition + screen template), 122-entry component key registry
- **Tests**: 1,375 passing (including 200+ integration tests against real Dank DB)
- **Branch**: `t5/architecture-vision`

## Architecture: Four-Layer Model — ALL LAYERS OPERATIONAL

```
Layer 1: EXTRACTION     Source → DB        ✅ Complete (86K nodes, 72 columns)
Layer 2: ANALYSIS        DB → Abstractions  ✅ Complete + Hardened (48 types, 109 templates, 49 slots, key registry)
Layer 3: COMPOSITION     Abstractions → IR   ✅ Complete + Hardened (thin IR, prompt parsing, project vocabulary, validation)
Layer 4: RENDERING       IR + DB/Config → Output  ✅ Complete + Hardened (Mode 1 + Mode 2 + composition children + token rebinding)
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
    ↓ figma_execute MCP — returns M dict (element_id → figma_node_id)
Rendered screen in Figma (with background, HUG sizing, real component instances)
    ↓ dd/rebind_prompt.py — build_template_rebind_entries() + generate_rebind_script()
Token variable rebind script
    ↓ figma_execute MCP
Variables bound to created nodes
```

## What Was Done (2026-04-03 Sessions)

### Session 1: Pipeline Stress Testing
- Smoke-tested 6 varied prompts (settings, dashboard, profile, chat, onboarding, empty state)
- Fixed: empty prompt crash (guard in parse_prompt)
- Fixed: text nodes wrapping at 40px (textAutoResize + layoutSizingHorizontal=FILL after appendChild)
- Added: template boundVariable extraction for token rebinding (5 entries per typical screen)
- Added: Mode 1 text overrides (findOne TEXT, loadFont, set .characters)
- Added: page_name parameter for Figma page management
- Executed in Figma: settings page + profile page rendered successfully
- Token rebinding executed: 5/5 entries bound to real Figma variables

### Session 2: Root Cause Analysis & System Fixes
Ground truth comparison against real screen 184 revealed 5 gaps → 5 root causes → all data flow problems:

| Root Cause | Problem | Fix |
|-----------|---------|-----|
| A: Fractured component identity | Two tables (components + templates) with broken JOIN | component_key_registry (122 entries, 80% resolved) |
| B: Incomplete template fields | _TEMPLATE_FIELDS missed layout_sizing_h/v | Expanded to 23 fields, cards now HUG |
| C: Screen frames invisible | extract_templates skipped depth-0 nodes | Screen template with #F6F6F6 background |
| D: LLM outputs unsupported types | 35/48 catalog types have 0 Dank instances | validate_components() warns but preserves (graceful degradation) |
| E: Dual child systems uncoordinated | Composition children + IR children both fire | Guard: composition only when no IR children |

## What To Do Next

### High-Value Improvements
1. **Variant selection on Mode 1 instances** — LLM outputs variant name, renderer sets variant properties on the instance. Currently the best template is selected but variant props aren't set on the Figma instance.
2. **Composition children with figma_id** — 20/139 composition children have figma_node_id. The remaining 119 are keyless types (container, text). For keyed types, the registry resolves 80%. Could improve by searching instance subtrees for component masters.
3. **CLI command** — `dd generate-prompt "your prompt" --db path.db` for command-line usage without Python scripting.
4. **React/SwiftUI renderers** — The IR is platform-agnostic. New renderers read the same IR + a ReactRendererConfig/SwiftUIRendererConfig.
5. **Synthetic tokens** — The architecture spec describes synthetic tokens for unbound visual values. Deferred but important for full token coverage.

### Quality Improvements
- Cards should use FILL width (not HUG) since they typically span the screen
- Navigation rows and toggles need either (a) classification to map them to real Dank components or (b) a default library with basic visual implementations
- Multiple button variants (large/translucent vs small/solid) should be selectable based on context
- Composition children ordering within containers

### Testing Improvements
- Test on non-Dank Figma files to verify generalizability
- Automated ground truth comparison (generate → diff against real screen node counts)
- CI integration tests

## Key Files

| File | Purpose |
|------|---------|
| `docs/t5-four-layer-architecture.md` | THE authoritative architecture spec |
| `docs/module-reference.md` | Complete API reference for all modules |
| `dd/ir.py` | IR generation: `query_screen_visuals`, `_node_id_map`, `build_semantic_tree` |
| `dd/generate.py` | Figma renderer: Mode 1 + Mode 2 + `_emit_composition_children` |
| `dd/compose.py` | Prompt composition: `compose_screen`, `build_template_visuals`, `validate_components`, `generate_from_prompt` |
| `dd/prompt_parser.py` | LLM parsing: `parse_prompt`, `prompt_to_figma`, `build_project_vocabulary` |
| `dd/templates.py` | Template extraction: `extract_templates`, `extract_child_composition`, `build_component_key_registry`, `query_templates` |
| `dd/screen_patterns.py` | Screen archetypes: `extract_screen_archetypes`, `get_archetype_prompt_context` |
| `dd/rebind_prompt.py` | Token rebinding: `build_template_rebind_entries`, `generate_rebind_script` |
| `schema.sql` | DB schema — component_templates (31 cols), component_key_registry |

## Environment

```bash
source .venv/bin/activate

# Run all tests (1,375 expected)
python -m pytest tests/ --tb=short

# Run integration tests only
python -m pytest tests/ -m integration --tb=short

# Quick pipeline test (requires .env with ANTHROPIC_API_KEY)
python -c "
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
