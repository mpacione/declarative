# Next Session: Pipeline Quality Iteration

## Session Goal

The prompt→Figma pipeline was hardened across two sessions (50 new tests, 5 root cause fixes). Generated screens now have background fills, HUG-sized cards, real component instances, text overrides, and token rebinding. This session is about closing the remaining quality gaps and extending the system to new capabilities.

---

## Step 1: Get Up to Speed (DO THIS FIRST)

### Read Memory Files

Read `MEMORY.md` at `/Users/mattpacione/.claude/projects/-Users-mattpacione-declarative-build/memory/MEMORY.md`, then read EVERY memory file it references. Pay special attention to:

- `project_t5_progress.md` — complete build log including hardening sessions
- `project_pipeline_gap_analysis.md` — ground truth comparison methodology and findings
- `project_phase0_decisions.md` — critical architectural decisions
- `feedback_compare_against_ground_truth.md` — always diff output vs real DB data
- `feedback_figma_pages.md` — Pages are organizational, not per-screen
- `feedback_reuse_systems.md` — reuse existing machinery

### Read Architecture & Docs

1. **`docs/continuation.md`** — current state (2026-04-03), pipeline diagram, all key files
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
python -m pytest tests/ --tb=short  # Expect 1,375 passing
```

---

## Step 2: What Exists Now

### Pipeline Architecture
```
prompt → Claude Haiku (with project vocabulary + archetypes)
    → component list → validate_components() → compose_screen(templates)
    → build_template_visuals() (composition data + figma_ids from registry)
    → generate_figma_script() (Mode 1 instances + Mode 2 frames + composition children)
    → figma_execute → M dict
    → build_template_rebind_entries() → generate_rebind_script()
    → figma_execute → variables bound
```

### Key Infrastructure Built

| System | What | Status |
|--------|------|--------|
| Component key registry | 122 component_key → figma_node_id mappings | ✅ 80% resolved |
| Child composition | 139 composition entries across 104 templates | ✅ Extracted from 44K parent→child relationships |
| Template sizing modes | layout_sizing_h/v captured (HUG/FILL/FIXED) | ✅ Cards use HUG |
| Screen template | #F6F6F6 background from depth-0 nodes | ✅ Applied to generated screens |
| Project vocabulary | Real variant names + keys injected into LLM prompt | ✅ Working |
| Validation layer | Warns about unsupported types, preserves in IR | ✅ Working |
| Composition guard | Only fires when IR element has no explicit children | ✅ Working |

### What's in the DB

```
86,761 nodes (72 columns)
182,871 token bindings
388 tokens with Figma variable IDs
47,292 classified nodes (93.6% coverage)
21 components, 49 slots, 21 a11y contracts
109 templates (23 fields each, 104 with composition data)
122-entry component key registry
```

---

## Step 3: What To Do Next (Priority Order)

### 3.1 Card Width: FILL Not HUG

**Problem:** Cards now use HUG for both axes. But real Dank cards use HUG vertically (wrap content) and FILL horizontally (span the parent width). Currently cards render narrow because they hug their text content width.

**Investigate:** Query the real Dank card instances:
```sql
SELECT layout_sizing_h, layout_sizing_v, COUNT(*)
FROM nodes n JOIN screen_component_instances sci ON sci.node_id = n.id
WHERE sci.canonical_type = 'card'
GROUP BY layout_sizing_h, layout_sizing_v
```

**Fix:** If cards universally use FILL horizontally, the template should reflect that. The `compute_mode_template` already computes the statistical mode — verify it's capturing the right data.

### 3.2 Variant Selection on Mode 1 Instances

**Problem:** The LLM outputs variant names (e.g., `"variant": "button/large/translucent"`), and the template selector picks the right template. But the Figma instance doesn't have its variant properties set — it just uses the master component's defaults.

**Investigate:** Check what variant properties Dank components have:
```sql
SELECT name, variant_properties FROM components WHERE variant_properties IS NOT NULL
```
The `component_variants` table is empty (0 rows). This means `extract_components()` didn't find COMPONENT_SET nodes (Dank uses standalone COMPONENT nodes, not variant sets).

**Fix:** Since Dank components are standalone (not variant sets), variant selection means picking a DIFFERENT component master to instantiate. The `_pick_best_template` + registry already does this — when the LLM says `"variant": "button/large/translucent"`, the template with that variant is selected, and its `component_figma_id` is used for `getNodeByIdAsync`. Verify this works end-to-end.

### 3.3 Composition Children Execution

**Problem:** Composition children were built but the `importComponentByKeyAsync` path timed out during Figma execution. The `getNodeByIdAsync` path works for local components. 20/139 composition children have `component_figma_id` — these should work.

**Test:** Generate a screen where composition children have figma_ids (e.g., tabs with button children), execute in Figma, verify the buttons appear inside the tabs container.

### 3.4 CLI Command

**Build:** `dd generate-prompt "your prompt" --db path.db` that:
1. Loads DB, builds registry, extracts templates
2. Calls prompt_to_figma()
3. Writes the Figma JS to stdout or a file
4. Optionally executes via figma_execute MCP

### 3.5 Ground Truth Comparison Automation

**Build:** A function `compare_generated_vs_ground_truth(conn, generated_spec, reference_screen_id)` that:
1. Takes a generated CompositionSpec and a real screen ID
2. Compares: element count, Mode 1 vs Mode 2 ratio, instance types, visual properties
3. Returns a structured diff report
4. Used for automated quality tracking

### 3.6 Non-Dank File Testing

Test the pipeline on a different Figma file to verify it generalizes. This requires:
1. A second Figma file with its own extraction DB
2. Running the full pipeline: extract → classify → extract_templates → prompt_to_figma
3. Verifying the output uses the second file's components and tokens

---

## Step 4: Key Commands

```bash
source .venv/bin/activate

# Run all tests (1,375 expected)
python -m pytest tests/ --tb=short

# Run integration tests only
python -m pytest tests/ -m integration -v

# Quick pipeline test with all fixes
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
result = prompt_to_figma('Build a settings page with two card sections', conn, client, page_name='Generated')
print(f'Elements: {result[\"element_count\"]}, Warnings: {result.get(\"warnings\", [])}')
print(f'Mode 1: {result[\"structure_script\"].count(\"getNodeByIdAsync\")}')
print(f'HUG: {result[\"structure_script\"].count(\"HUG\")}')
"

# Execute in Figma (requires Desktop Bridge plugin)
# Use figma_execute MCP tool with the structure_script content
```

## Step 5: Branch & Git

- **Branch**: `t5/architecture-vision`
- **Last commit**: `4a4e636` — pipeline hardening root cause fixes
- **Tests**: 1,375 passing
- Figma file: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
