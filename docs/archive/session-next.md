# Next Session: Visual Fidelity & Generalizability

## Session Goal

The prompt→Figma pipeline is fully operational (3 hardening sessions, 1,389 tests, 14 new tests in latest session). Generated screens have FILL-width cards, real component instances, text overrides, token rebinding, and a CLI command. This session closes the remaining visual fidelity gaps and proves the system generalizes beyond Dank.

---

## Step 1: Get Up to Speed (DO THIS FIRST)

### Read Memory Files

Read `MEMORY.md` at `/Users/mattpacione/.claude/projects/-Users-mattpacione-declarative-build/memory/MEMORY.md`, then read EVERY memory file it references. Pay special attention to:

- `project_t5_progress.md` — complete build log including all 3 hardening sessions
- `project_pipeline_gap_analysis.md` — ground truth comparison methodology and findings
- `project_phase0_decisions.md` — critical architectural decisions
- `feedback_compare_against_ground_truth.md` — always diff output vs real DB data
- `feedback_reuse_systems.md` — reuse existing machinery before building one-off functions
- `feedback_figma_pages.md` — Pages are organizational, not per-screen

### Read Architecture & Docs

1. **`docs/continuation.md`** — current state (2026-04-04), pipeline diagram, known gaps
2. **`docs/t5-four-layer-architecture.md`** — THE authoritative spec. Read at minimum: Layer 3 (lines 312-440), Layer 4 rendering modes (lines 755-852), RendererConfig (lines 450-510)
3. **`docs/module-reference.md`** — API reference for all modules

### Explore with code-graph-mcp

```
project_map (compact=true)
module_overview path="dd" (compact=true)
```

### Run the Test Suite

```bash
source .venv/bin/activate
python -m pytest tests/ --tb=short  # Expect 1,389 passing
```

---

## Step 2: What Exists Now

### Pipeline Architecture
```
prompt → Claude Haiku (with project vocabulary + archetypes)
    → component list → validate_components() → compose_screen(templates)
    → build_template_visuals() (composition data + figma_ids from registry)
    → generate_figma_script() (Mode 1 instances + Mode 2 frames + FILL width for containers)
    → figma_execute → M dict
    → build_template_rebind_entries() → generate_rebind_script()
    → figma_execute → variables bound
```

### Key Infrastructure Built

| System | What | Status |
|--------|------|--------|
| Component key registry | 122 component_key → figma_node_id mappings | ✅ 80% resolved |
| Child composition | 139 composition entries across 104 templates | ✅ Extracted from 44K parent→child relationships |
| Template sizing modes | layout_sizing_h/v captured | ✅ Cards FILL width via _FILL_WIDTH_TYPES |
| Screen template | #F6F6F6 background from depth-0 nodes | ✅ Applied to generated screens |
| Project vocabulary | Real variant names + keys injected into LLM prompt | ✅ Working |
| Validation layer | Warns about unsupported types, preserves in IR | ✅ Working |
| Composition guard | Only fires when IR element has no explicit children | ✅ Working |
| Variant selection | LLM variant → template → registry → figma_node_id | ✅ Verified end-to-end |
| CLI command | `dd generate-prompt "prompt" --db path.db --out file.js --page Name` | ✅ Working |
| Ground truth comparison | `compare_generated_vs_ground_truth(conn, spec, screen_id)` | ✅ Working |
| Token rebinding | 6/6 entries bound successfully in Figma execution | ✅ Working |

### What's in the DB

```
86,761 nodes (72 columns)
182,871 token bindings
388 tokens with Figma variable IDs
47,292 classified nodes (93.6% coverage)
21 components, 49 slots, 21 a11y contracts
109 templates (23 fields each, 104 with composition data)
122-entry component key registry
14 template types: button, button_group, card, container, drawer, header, heading, icon, image, screen, search_input, slider, tabs, text
36 catalog types with NO templates (toggle, checkbox, radio, navigation_row, text_input, etc.)
```

### Known Gaps from Figma Execution (2026-04-04)

1. **Toggle/checkbox/radio render as empty frames** — no Dank templates exist for these 36 catalog types. But Dank HAS `icon/switch` (3 instances, key `6c70ef57`) and `icon/checkbox-empty` (358 instances, key `23cd5138`) / `icon/checkbox-filled` (198 instances, key `184e56da`) classified under `icon` instead.

2. **Header text override hits wrong node** — `findOne(n => n.type === "TEXT")` grabs the first TEXT child. For `nav/top-nav`, the structure is: `Left` (FRAME), `Center` (FRAME), `Right` (FRAME). The title text should be inside `Center`, not the first TEXT found in `Left`.

3. **119/139 composition children are keyless** — only 20/139 have `component_figma_id`. The rest are container/text types that render as empty frames.

---

## Step 3: What To Do Next (Priority Order)

### 3.1 Smarter Text Overrides (HIGH — fixes visible quality issue)

**Problem**: Mode 1 text override currently does `findOne(n => n.type === "TEXT")` which grabs the FIRST text node. For `nav/top-nav` this overwrites "Workshop" inside the Left frame instead of the title. The real component structure (from DB):

```
nav/top-nav (COMPONENT, 1835:155037)
├── Left (FRAME, 1835:25918)
├── Center (FRAME, 1835:25929)
└── Right (FRAME, 1835:25935)
```

**Investigation needed**:
```sql
-- Find TEXT nodes inside each Mode 1 component by name pattern
SELECT n.name, n.node_type, p.name AS parent_name, n.depth
FROM nodes n
JOIN nodes p ON n.parent_id = p.id
WHERE n.node_type = 'TEXT'
AND p.figma_node_id IN ('1835:25918', '1835:25929', '1835:25935')
ORDER BY n.depth
```

**Approach**: In `generate_figma_script`, for Mode 1 text overrides, change from:
```js
n.findOne(n => n.type === "TEXT")
```
to a strategy that tries specific targeting first:
```js
// Try named slots: "label", "title", "text" — common Figma component patterns
n.findOne(n => n.type === "TEXT" && /label|title|text/i.test(n.name))
// Fall back to largest/most prominent text
|| n.findOne(n => n.type === "TEXT")
```

Or better: query the DB to build a per-component text target map at template extraction time. Store which TEXT child name is the "primary text" for each component template (the one with the longest content / largest font size in the statistical mode).

**Tests**: Write tests for text targeting — verify header targets center text, button targets label text, verify fallback still works for unknown components.

### 3.2 Unsupported Type Fallback — Alias Mapping (HIGH — fixes empty frame problem)

**Problem**: 36/48 catalog types have no templates. The LLM frequently outputs `toggle`, `navigation_row`, `text_input`, `checkbox` — all render as empty 0×0 frames.

**Key insight from DB investigation**: Dank already has components that ARE these things, just classified differently:
- `icon/switch` (key `6c70ef57`, 3 instances) = toggle
- `icon/checkbox-empty` (key `23cd5138`, 358 instances) = checkbox (unchecked)
- `icon/checkbox-filled` (key `184e56da`, 198 instances) = checkbox (checked)
- `container` with icon+text+chevron = navigation_row
- `nav/tabs` (key `542d14a0`, 204 instances) = bottom_nav

**Approach — type alias mapping** (option A from architecture):

Build a `_TYPE_ALIASES` dict in `compose.py` that maps unsupported types to existing template types + preferred variants:

```python
_TYPE_ALIASES: dict[str, dict[str, str]] = {
    "toggle": {"type": "icon", "variant": "icon/switch"},
    "checkbox": {"type": "icon", "variant": "icon/checkbox-empty"},
    "navigation_row": {"type": "container"},
    "bottom_nav": {"type": "tabs", "variant": "nav/tabs"},
    "list_item": {"type": "container"},
}
```

Apply aliases in `validate_components()` — replace unsupported types with their aliases before composition. This reuses existing templates and component instances without building new infrastructure.

**Tests**: Test that `toggle` resolves to `icon/switch` template, that the alias produces a Mode 1 instance, and that unknown types still get warnings.

### 3.3 Non-Dank File Testing (MEDIUM — proves generalizability)

**Problem**: The entire pipeline has only been tested on one Figma file.

**Approach**: Extract a second Figma file. Options:
- Use `figma_get_file_data` on the connected Dank file to find a different page structure
- Use a different Figma file key if available
- Create a minimal test: generate a tiny DB with 5 hand-inserted templates, verify the pipeline produces correct output without Dank data

The minimal test approach is best for now — it doesn't require Figma API access and proves the code is not hard-coded to Dank conventions:

1. Create a test DB with non-Dank templates (different types, different fills, different sizing)
2. Run `generate_from_prompt` against it
3. Verify the output uses the test file's templates, not Dank defaults
4. This can be a pytest integration test

**Tests**: Build a `test_non_dank_pipeline.py` that seeds a fresh DB with custom templates and verifies the full prompt→script pipeline works with them.

---

## Step 4: Key Commands

```bash
source .venv/bin/activate

# Run all tests (1,389 expected)
python -m pytest tests/ --tb=short

# Run integration tests only
python -m pytest tests/ -m integration -v

# CLI: generate from prompt
python -m dd generate-prompt "Build a settings page with toggles" --db Dank-EXP-02.declarative.db --page Generated

# Ground truth comparison
python -c "
from dd.compose import compose_screen, compare_generated_vs_ground_truth
import sqlite3, json
conn = sqlite3.connect('Dank-EXP-02.declarative.db')
spec = compose_screen([{'type': 'header'}, {'type': 'card', 'children': [{'type': 'button'}]}])
report = compare_generated_vs_ground_truth(conn, spec, 184)
print(json.dumps(report, indent=2))
"

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
print(f'Mode 1: {result[\"structure_script\"].count(\"getNodeByIdAsync\")}')
print(f'FILL: {result[\"structure_script\"].count(\"FILL\")}')
print(f'Warnings: {result.get(\"warnings\", [])}')
"

# Execute in Figma (requires Desktop Bridge plugin on port 9227)
# Use figma_execute MCP tool with the structure_script content
```

## Step 5: Branch & Git

- **Branch**: `t5/architecture-vision`
- **Last commit**: `e4e0628` — docs update after quality iteration
- **Tests**: 1,389 passing
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
