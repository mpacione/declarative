# Next Session: Test & Harden the Prompt→Figma Pipeline

## Setup

Read these files to get up to speed:

1. **Memory**: Read MEMORY.md at `/Users/mattpacione/.claude/projects/-Users-mattpacione-declarative-build/memory/MEMORY.md` and then read each memory file it references.
2. **Continuation**: Read `docs/continuation.md` — has the full pipeline diagram and current state.
3. **Module reference**: Read `docs/module-reference.md` — all module APIs.
4. **Use code-graph-mcp** to familiarize yourself with the codebase before writing anything.

## What Was Built (2026-04-02)

The full prompt→Figma pipeline in one session (18 commits, 1,325 tests):

- **Phase 0-2**: Thin IR — removed visual data from IR, renderer reads DB directly
- **Phase 3**: Semantic tree — 116 elements → 20 with named slots, system chrome filtered
- **Phase 4**: Templates extracted (108 across 13 types), prompt composition, Figma rendering
- **Mode 1**: Real component instances via `getNodeByIdAsync` (header, buttons, tabs)
- **LLM**: Claude Haiku parses natural language → component list, enriched with project patterns
- **Rebinding**: Token variables can be bound to newly created nodes

## What To Do: Testing & Hardening

### 1. End-to-End Pipeline Stress Test

Execute the full pipeline with various prompts via Figma MCP and screenshot results:

```python
from dd.prompt_parser import prompt_to_figma
# Try these prompts:
# "Build a settings page with notification and privacy sections"
# "Create a dashboard with metric cards"
# "Design a profile page with avatar and settings list"
# "Make a chat screen with message bubbles"
# "Build an onboarding flow with steps and illustrations"
```

For each: verify the Figma output looks reasonable, check Mode 1 instances vs Mode 2 frames, verify layout makes sense.

### 2. Token Rebinding Execution

Actually execute the rebind script in Figma after generating a screen:

```python
from dd.rebind_prompt import query_token_variables, build_rebind_entries, generate_rebind_script
# 1. Generate screen → get M dict
# 2. Build rebind entries from token_refs + M
# 3. Execute rebind script
# 4. Verify: are Figma variables actually bound to the nodes?
```

### 3. Edge Cases to Test

- Empty prompt → should produce empty screen
- Prompt with types not in catalog → should gracefully degrade
- Very complex prompt (20+ components) → should not crash
- Prompt for screen type not in Dank (e.g., "map view") → should use available templates
- Multiple executions in sequence → should not leave orphan nodes

### 4. Mode 1 Deep Testing

- Verify all 82 icon component keys work with `getNodeByIdAsync`
- Test button variant selection (large/solid vs small/translucent)
- Test drawer, button_group, image Mode 1 rendering
- Check: do Mode 1 instances respond to variable rebinding?

### 5. Quality Improvements to Consider

- Text overrides on Mode 1 instances (button labels, heading text)
- Better slot filling in compose_screen (use slot definitions from DB)
- CLI command: `dd generate-prompt "your prompt here" --db path.db`
- Figma page management (create named page for each generation, avoid orphans)

## Key Commands

```bash
source .venv/bin/activate

# Run all tests (expect 1,325)
python -m pytest tests/ --tb=short

# Run integration tests only
python -m pytest tests/ -m integration -v

# Quick pipeline test
ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2) python -c "
from dd.prompt_parser import prompt_to_figma
import anthropic, sqlite3
client = anthropic.Anthropic()
conn = sqlite3.connect('Dank-EXP-02.declarative.db')
conn.row_factory = sqlite3.Row
result = prompt_to_figma('Build a settings page', conn, client)
print(result['structure_script'][:500])
"
```

## Branch

`t5/architecture-vision` — pushed to origin with 18 commits from the 2026-04-02 session.
