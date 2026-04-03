# Next Session: Test & Harden the Prompt→Figma Pipeline

## Session Goal

The full prompt→Figma pipeline was built in one marathon session (19 commits, 1,325 tests). It works end-to-end but hasn't been stress-tested. This session is about exercising every path, finding edge cases, fixing bugs, and improving output quality. Think of it as QA + polish.

---

## Step 1: Get Up to Speed (DO THIS FIRST)

Before writing any code, thoroughly familiarize yourself with the codebase. This project is large (40+ modules, 1,325 tests) and the architecture has specific decisions you need to understand.

### Read Memory Files

Read `MEMORY.md` at `/Users/mattpacione/.claude/projects/-Users-mattpacione-declarative-build/memory/MEMORY.md`, then read EVERY memory file it references. Pay special attention to:

- `project_t5_progress.md` — the complete build log of what was implemented and when
- `project_phase0_decisions.md` — critical architectural decisions (no FigmaPlatformContext, no synthetic tokens for rendering, renderer reads DB directly)
- `project_system_overview.md` — the four-layer model
- `feedback_reuse_systems.md` — reuse existing machinery, don't build one-offs
- `feedback_atomic_composable.md` — pipeline functions must be atomic and composable

### Read Architecture & Docs

1. **`docs/continuation.md`** — current state, full pipeline diagram, all key files, environment setup
2. **`docs/t5-four-layer-architecture.md`** — THE authoritative spec (1,640+ lines). Read at least: the four-layer overview (lines 1-25), Layer 3 Composition / What the IR Carries (lines 312-440), Layer 4 Rendering / Two Figma Generation Modes (lines 755-852), and Integration Checkpoints (lines 1400-1490)
3. **`docs/module-reference.md`** — complete API reference for all modules. Focus on the new modules: `dd/compose.py`, `dd/prompt_parser.py`, `dd/templates.py`, `dd/screen_patterns.py`, `dd/rebind_prompt.py`, `dd/generate.py`

### Explore with code-graph-mcp

Use the code-graph-mcp tools extensively BEFORE writing code. This helps you understand what exists so you don't duplicate or conflict with it.

```
# Start here — get the full project architecture
project_map (compact=true)

# Understand the key modules
module_overview path="dd" (compact=true)

# Trace the prompt→Figma pipeline
get_call_graph symbol_name="prompt_to_figma" direction="callees"
get_call_graph symbol_name="generate_from_prompt" direction="callees"
get_call_graph symbol_name="generate_figma_script" direction="callees"

# Before modifying anything, check blast radius
impact_analysis symbol_name="generate_figma_script"
```

---

## Step 2: What Was Built (Context)

### The Project

Declarative Design is a bi-directional design compiler. It parses UI from any source (Figma, React, screenshots, prompts) into an abstract compositional IR, then generates to any target with token-bound fidelity.

### Current Database

`Dank-EXP-02.declarative.db` — extracted from the "Dank (Experimental)" Figma file (`drxXOUOdYEBBQ09mrXJeYu`):
- 86,761 nodes across 72 columns
- 182,871 token bindings (node properties → Figma variables)
- 388 tokens with Figma variable IDs across 8 collections
- 338 screens (204 app screens, 117 icon defs, 14 component defs, 3 design canvases)
- 47,292 classified nodes (93.6% coverage)
- 21 components with 49 slot definitions and 21 a11y contracts
- 108 component templates across 13 catalog types
- 25,860 nodes with component keys (122 unique master components)

### The Pipeline (Built 2026-04-02, 19 commits)

```
Natural language prompt ("build me a settings page with toggle sections")
    ↓
dd/prompt_parser.py — Claude Haiku parses with 48 catalog types + project screen patterns
    ↓
Component list: [{type: "header"}, {type: "card", children: [{type: "toggle"}, ...]}, ...]
    ↓
dd/compose.py — compose_screen() builds IR spec with template layout defaults
    ↓
dd/compose.py — build_template_visuals() maps elements to template fills/strokes/effects
    ↓
dd/generate.py — generate_figma_script(spec, db_visuals)
    Mode 1: getNodeByIdAsync(masterId).createInstance() for keyed components (header, buttons, tabs)
    Mode 2: createFrame() + template visuals for keyless types (card, heading, text)
    ↓
Figma JS script (executed via figma_execute MCP)
    ↓
Returns M dict: {element_id → figma_node_id}
    ↓
dd/rebind_prompt.py — build_rebind_entries(token_refs, M, token_variables) + generate_rebind_script()
    ↓
Compact pipe-delimited rebind script (executed via figma_execute MCP)
    ↓
Token variables bound to created nodes
```

### Phases Completed

| Phase | What | Key Files |
|-------|------|-----------|
| 0 | `_node_id_map` + `query_screen_visuals` — renderer reads DB directly | `dd/ir.py` |
| 1 | `build_visual_from_db` + `db_visuals` param — generator reads DB | `dd/generate.py` |
| 2 | Removed IR visual section — thin IR (type, layout, style, props only) | `dd/ir.py` |
| 3a | Component extraction — 21 components, 49 slots, 21 a11y contracts | `dd/extract_components.py` |
| 3b | Semantic tree — 116→20 elements, named slots, chrome filtering | `dd/ir.py` |
| 4a | Template extraction — 108 templates, statistical mode per type | `dd/templates.py` |
| 4b | Prompt composition — compose_screen + template visuals | `dd/compose.py` |
| Mode 1 | Component instances via getNodeByIdAsync (local components) | `dd/generate.py` |
| LLM | Claude Haiku prompt parsing + project pattern enrichment | `dd/prompt_parser.py`, `dd/screen_patterns.py` |
| Rebind | Token variable binding for prompt-generated screens | `dd/rebind_prompt.py` |

### Key Architectural Decisions

1. **Thin IR**: No visual data in the IR. The renderer reads visual properties from the DB via `query_screen_visuals()` for existing screens, or from templates for prompt-generated screens.
2. **No FigmaPlatformContext**: The renderer queries the DB directly using node IDs. No intermediary cache object.
3. **No synthetic tokens for rendering**: Synthetic tokens are a composition/curation feature, deferred. The renderer doesn't need them.
4. **Mode 1 preferred**: `getNodeByIdAsync(masterId).createInstance()` for local components. `importComponentByKeyAsync` for published library components (untested — Dank components are local/unpublished).
5. **Mode 2 fallback**: `createFrame()` + template structure + visual defaults for types without component keys (card, heading, text, container).
6. **Semantic tree is opt-in**: `generate_ir(semantic=True)` collapses 116→20 elements. Default is flat for backward compatibility.

---

## Step 3: What To Test & Fix

### 3.1 End-to-End Pipeline Stress Test

Execute the full pipeline with various prompts via Figma MCP. Screenshot each result and evaluate quality.

```python
# Setup
from dotenv import load_dotenv
load_dotenv('.env')
import anthropic, sqlite3
from dd.prompt_parser import prompt_to_figma
client = anthropic.Anthropic()
conn = sqlite3.connect('Dank-EXP-02.declarative.db')
conn.row_factory = sqlite3.Row
```

**Prompts to try** (execute each, screenshot, evaluate):
1. "Build a settings page with notification and privacy toggle sections"
2. "Create a dashboard with three metric cards and a header"
3. "Design a profile page with avatar, name, bio, and a settings list"
4. "Make a chat screen with a message input at the bottom"
5. "Build an onboarding flow with a hero image and continue button"
6. "Create an empty state page with an illustration and action button"

For each: check Mode 1 instances look correct, Mode 2 frames have proper fills/padding/radius, text is readable, layout is sensible.

### 3.2 Token Rebinding Execution

The rebind pipeline is built but hasn't been executed in Figma yet. Test it:

```python
from dd.rebind_prompt import query_token_variables, build_rebind_entries, generate_rebind_script

# 1. Generate a screen → execute in Figma → get M dict back
# 2. Build rebind entries: entries = build_rebind_entries(result['token_refs'], M_dict, query_token_variables(conn))
# 3. Generate script: script = generate_rebind_script(entries)
# 4. Execute script via figma_execute
# 5. Inspect nodes in Figma — are variables actually bound?
```

### 3.3 Edge Cases

- **Empty prompt**: `prompt_to_figma("", conn, client)` — should produce empty or minimal screen
- **Invalid types in LLM response**: What if Claude returns a type not in the catalog?
- **Very large prompt**: 20+ component screen — does it render without hitting limits?
- **No templates for a type**: What happens with `compose_screen([{"type": "date_picker"}])`?
- **Multiple sequential executions**: Generate 5 screens in a row — orphan node cleanup?

### 3.4 Mode 1 Deep Testing

- Test all keyed types: header (nav/top-nav), button variants (large/solid, small/translucent), tabs (nav/tabs), drawer, button_group, image (logo/dank)
- Icons: 82 templates with keys but currently skipped as Mode 1 children — test if standalone icons work
- Verify Mode 1 instances respond to token variable rebinding

### 3.5 Quality Improvements to Build

- **Text overrides on Mode 1 instances**: Button labels currently show template default text ("Do the thing"). Need to find the TEXT child and set `.characters`.
- **Better layout for Mode 2 frames**: Card sizing, spacing between cards, scroll container behavior.
- **CLI command**: `dd generate-prompt "your prompt here" --db path.db` for command-line usage.
- **Figma page management**: Create a named page/section for each generation to avoid orphans on the canvas.

---

## Step 4: Key Commands

```bash
source .venv/bin/activate

# Run all 1,325 tests
python -m pytest tests/ --tb=short

# Run integration tests only (200+ tests, requires Dank DB)
python -m pytest tests/ -m integration -v

# Run specific phase tests
python -m pytest tests/test_phase0_integration.py tests/test_phase2_integration.py tests/test_phase3a_integration.py tests/test_phase3b_integration.py tests/test_phase4a_integration.py tests/test_phase4b_integration.py tests/test_mode1_integration.py tests/test_prompt_parser_integration.py tests/test_rebind_integration.py tests/test_semantic_tree_integration.py tests/test_integration_real_db.py tests/test_screen_patterns_integration.py -v

# Quick pipeline smoke test (needs ANTHROPIC_API_KEY in .env)
ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2) python -c "
from dd.prompt_parser import prompt_to_figma
import anthropic, sqlite3
client = anthropic.Anthropic()
conn = sqlite3.connect('Dank-EXP-02.declarative.db')
conn.row_factory = sqlite3.Row
result = prompt_to_figma('Build a settings page with toggles', conn, client)
print(f'Components: {len(result[\"components\"])}, Elements: {result[\"element_count\"]}, Script: {len(result[\"structure_script\"])} chars')
print(f'Mode 1: {result[\"structure_script\"].count(\"getNodeByIdAsync\")}, Mode 2: {result[\"structure_script\"].count(\"createFrame\")}')
"

# Execute generated script in Figma (requires Desktop Bridge plugin running)
# Use figma_execute MCP tool with the structure_script content
```

## Step 5: Branch & Git

- **Branch**: `t5/architecture-vision`
- **Remote**: Pushed to `origin` with 19 commits from the 2026-04-02 session
- **Last commit**: `f2149f2` — ruff + mypy static analysis tooling
- Figma file: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental) — needs Desktop Bridge plugin for execution
