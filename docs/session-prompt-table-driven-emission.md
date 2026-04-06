# Session Prompt: Table-Driven Emission Refactor

## Context

You are continuing work on Declarative Design, a design system compiler. Read `docs/continuation.md` first — it contains the full project rationale, current state, and remaining issues.

## Step 0: Read Everything First (MANDATORY)

Do NOT write any code until you have read all documentation and explored the codebase. This is a complex multi-layer architecture where changes in one layer cascade to others.

### Memory Files
Read `MEMORY.md` at `/Users/mattpacione/.claude/projects/-Users-mattpacione-declarative-build/memory/MEMORY.md` and then read EVERY file it references. Critical ones for this task:

- `feedback_table_driven_emission.md` — **START HERE**: why the registry must drive emission, the LLVM TableGen pattern, the design
- `feedback_property_registry.md` — why the registry exists, the M×N coverage problem
- `project_reproduction_gap_analysis.md` — the 17 properties extracted but not emitted, root cause analysis
- `project_t5_progress.md` — current state, what's been built, remaining gaps
- `project_ir_purpose.md` — why the IR exists, why you can't bypass it

### Architecture Docs
- `docs/compiler-architecture.md` — THE authoritative spec. Section 5 (Progressive Fallback) is essential
- `docs/continuation.md` — current state, "Planned: Table-Driven Emission" section has the design
- `docs/module-reference.md` — complete API reference for every module
- `docs/learnings.md` — "Table-Driven Emission Is the Architectural Fix" at the bottom

### Codebase Understanding
Use code-graph-mcp (force reindex first: delete `.code-graph/index.db` then run `incremental-index`) to understand:

- `dd/property_registry.py` — the 48-property registry. Read EVERY line. Understand `FigmaProperty` dataclass, the `PROPERTIES` tuple, and all lookup functions
- `dd/generate.py` — the Figma renderer. Understand these functions and how they currently emit properties:
  - `_emit_layout()` — hardcoded layout property list (lines ~880-960)
  - `_emit_visual()` — hardcoded visual property list (lines ~960-1020)
  - `_emit_text_props()` — hardcoded text property list (lines ~1110-1140)
  - `_emit_fills()` / `_emit_strokes()` / `_emit_effects()` — JSON array emitters
  - `build_visual_from_db()` — converts raw DB data to visual dict (lines ~170-250)
  - The Mode 2 creation block in `generate_figma_script()` — where emit functions are called
- `dd/ir.py` — `query_screen_visuals()` which builds the column list from the registry
- `dd/extract_supplement.py` — `_build_override_js_checks()` which generates JS from the registry

### Key Commands
```bash
source .venv/bin/activate
python -m pytest tests/ --tb=short  # 1,573 tests expected
```

## What This Task Is

Refactor the property registry and Figma renderer so that **emission is table-driven**. Currently the registry drives extraction, query, and override handling — but NOT emission. The emit functions (`_emit_layout`, `_emit_visual`, `_emit_text_props`) each maintain independent hardcoded property lists. This caused 17 of 48 properties to be extracted but never emitted.

The fix: extend `FigmaProperty` with per-renderer emit patterns, then replace the hardcoded emit functions with a single registry-driven emitter.

## The 17 Properties Not Currently Emitted

**LAYOUT (3)**: `counterAxisSpacing`, `layoutWrap`, `layoutPositioning`
**TEXT (8)**: `textAlignHorizontal`, `textAlignVertical`, `textDecoration`, `textCase`, `lineHeight`, `letterSpacing`, `paragraphSpacing`, `fontStyle`
**SIZE (4)**: `minWidth`, `maxWidth`, `minHeight`, `maxHeight`
**VISUAL (2)**: `strokeAlign`, `dashPattern`

## Design: How Table-Driven Emission Should Work

### 1. Extend FigmaProperty

Add an `emit` field to `FigmaProperty`. For each renderer (currently only "figma", future: "react", "swift"), define how the property is emitted.

**Simple properties** (most of the 17 gaps) use string templates:
```python
FigmaProperty(
    "textAlignVertical", "text_align_v",
    ("textAlignVertical",), "text", "enum",
    emit={"figma": '{var}.textAlignVertical = "{value}";'},
)
```

**Complex properties** reference custom emit functions:
```python
FigmaProperty(
    "fills", "fills",
    ("fills",), "visual", "json_array",
    emit={"figma": emit_fills_figma},  # function reference
)
```

**Properties that need special handling** (fontName combines family + weight + style, cornerRadius has uniform vs per-corner, lineHeight/letterSpacing are JSON objects in the DB):
```python
FigmaProperty(
    "cornerRadius", "corner_radius",
    ("cornerRadius",), "visual", "number_or_mixed",
    emit={"figma": emit_corner_radius_figma},
)
```

### 2. Replace Hardcoded Emit Functions

Replace `_emit_layout`, `_emit_visual`, `_emit_text_props` with a single function that iterates registry entries:

```python
def _emit_properties(var, eid, visual, tokens, category_filter=None):
    lines = []
    refs = []
    for prop in PROPERTIES:
        if category_filter and prop.category not in category_filter:
            continue
        value = visual.get(prop.db_column) or visual.get(prop.figma_name)
        if value is None:
            continue
        emit_fn = prop.emit.get("figma")
        if emit_fn is None:
            continue
        if isinstance(emit_fn, str):
            # String template
            lines.append(emit_fn.format(var=var, value=value, figma_name=prop.figma_name))
        else:
            # Custom function
            result_lines, result_refs = emit_fn(var, eid, value, tokens)
            lines.extend(result_lines)
            refs.extend(result_refs)
    return lines, refs
```

### 3. Handle Special Cases

Some properties need special emit logic that doesn't fit a simple template:

- **fontName**: combines `font_family` + `font_weight` + `font_style` into `{family, style}` object. Needs `normalize_font_style()` and `font_weight_to_style()`. Consider a custom emit function that reads all three DB columns.
- **cornerRadius**: uniform (single number) vs per-corner (4 properties). Custom function.
- **fills/strokes/effects**: JSON arrays with complex sub-structure. Already have custom emit functions.
- **lineHeight/letterSpacing**: DB stores JSON objects like `{"value": 24, "unit": "PIXELS"}`. Need conversion to Figma format.
- **constraints**: emitted in deferred section, not in main emit. Need `emit_phase` field.
- **position (x, y)**: also deferred. Not in registry (structural).
- **layoutSizing**: emitted differently for auto-layout containers (immediate) vs children (deferred). Needs context.

### 4. Add Structural Coverage Test

```python
def test_every_registry_property_has_emit_pattern():
    for prop in PROPERTIES:
        if prop.category == "constraint":
            continue  # emitted via deferred section
        if prop.figma_name in ("width", "height"):
            continue  # handled via resize()
        assert "figma" in prop.emit, f"{prop.figma_name} has no Figma emit pattern"
```

## Constraints

- **TDD**: Write failing tests first, then implement
- **No regressions**: All 1,573 existing tests must pass throughout
- **Progressive**: Make changes incrementally. Don't replace all emit functions in one step. Start with the simple properties, verify, then tackle complex ones.
- **The IR must be the data path**: Renderers read from the IR (query_screen_visuals output), not bypass it. Progressive fallback (L2→L1→L0) must be preserved.
- **`build_visual_from_db` is the bridge**: It converts raw DB data into the format the emit functions consume. It may need to be updated to pass through more properties.

## Suggested Implementation Order

1. **Read and understand everything** (Step 0 above)
2. **Extend `FigmaProperty`** with an `emit` field (dict of renderer → pattern/function)
3. **Add emit patterns for the 17 missing simple properties** — these are pure string templates
4. **Write a registry-driven emit function** that handles simple template properties
5. **Wire it into the Mode 2 creation block** alongside the existing emit functions (don't replace them yet)
6. **Verify the 17 gaps are closed** — generate screen 222, check that textAlignVertical, counterAxisSpacing, layoutWrap etc. appear in the output
7. **Migrate existing emit logic** for simple properties (strokeCap, strokeJoin, blendMode, etc.) from hardcoded functions into registry templates
8. **Add the structural coverage test**
9. **Tackle complex properties** (fills, fontName, cornerRadius) — move their emit functions into the registry as function references
10. **Execute screens in Figma** and verify visual improvements
11. **Update docs and commit**

## What NOT To Do

- Don't bypass the IR or read raw DB JSON directly in the renderer
- Don't create a separate "emit registry" — extend the existing `FigmaProperty`
- Don't try to handle every edge case upfront — start with the simple majority
- Don't break existing tests — if a test fails, understand why before changing it
- Don't remove `_emit_layout`/`_emit_visual`/`_emit_text_props` until their logic is fully migrated to the registry

## Environment

- Branch: `t5/architecture-vision`
- DB: `Dank-EXP-02.declarative.db`
- Figma file: `drxXOUOdYEBBQ09mrXJeYu`
- PROXY_EXECUTE port: 9227
- Reference screens: 184, 185, 186, 188, 222, 238, 259, 253, 244
