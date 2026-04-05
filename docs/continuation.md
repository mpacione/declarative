# Continuation: Next Session

## Quick Context

Declarative Design is a **design system compiler** — LLVM for design systems. Multi-level IR (MLIR-inspired) with four levels: L0 (DB scene graph), L1 (classification), L2 (token bindings), L3 (semantic tree). The DB IS the scene graph. The IR annotates it, doesn't replace it.

**Authoritative spec**: `docs/compiler-architecture.md`

## Current State (2026-04-05)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes (72 columns), 182,871 bindings, 388 tokens, 338 screens
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Tests**: 1,502 passing
- **Branch**: `t5/architecture-vision`
- **Round-trip**: Screen 184 successfully reproduced (structural fidelity achieved, visual polish remaining)

## What Was Built (2026-04-05 Session)

### Round-Trip Progressive Fallback (L2→L1→L0)
The renderer now walks ALL nodes via LEFT JOIN on L1 classification, with progressive fallback:
- **L2**: Token variable bindings (12 applied on screen 184)
- **L1**: Component instances via getNodeByIdAsync (11 Mode 1 instances)
- **L0**: Raw properties for unclassified nodes (createFrame/Rectangle/Text)

### Key Changes
- `query_screen_for_ir()`: LEFT JOIN replaces INNER JOIN — all nodes returned with L1/L2 as annotations
- `build_composition_spec()`: Type fallback (canonical_type → node_type.lower()), original names, absolute positioning for non-auto-layout parents, visibility from L0
- `generate_figma_script()`: Node type dispatch (createRectangle/Ellipse, skip vector/group), recursive mode1 skip, pre-fetch preamble for deduplication, deferred position + constraints (after all children appended)
- `extract_supplement.py`: Override extraction (text, visibility, instance swaps from Figma's overrides API)
- `query_screen_visuals()`: Instance overrides + recursive CTE for deep child swaps at any depth, deduplicated

### Architecture Refinement
- **Progressive fallback model** documented in compiler-architecture.md
- **IR exists for M×N problem** — shared analysis, not bypassed for round-trip
- **Deferred position + constraints** — Figma recalculates position when children added to HUG frames with CENTER constraints

## What To Do Next

### Remaining Round-Trip Gap: Nested Visual Property Overrides

The structural round-trip is proven. Remaining visual differences are **fill/size/opacity overrides on deeply nested elements** within component instances:

1. **Share button green background** — fill override on nested button not captured
2. **Toolbar button visible backgrounds** — fill opacity override not applied
3. **Green dot size** — size difference in logo/dank component
4. **Header text spacing** — padding/spacing override within nav/top-nav

**Root cause (confirmed via investigation)**: Two issues in the extraction:

1. **Self-overrides dropped**: Figma's `overrides` API can report overrides on the INSTANCE node ITSELF (not just children). When the override ID matches the node's own ID, `findOne` returns null (it only searches children). The override is silently dropped. Example: toolbar buttons have `{id: "2244:146079", overriddenFields: ["fills", "height", "width"]}` where the fill should be `visible: false` (transparent).

2. **Visual field values not read**: Even for child overrides, the extraction only reads values for `characters` and `visible` fields. It does NOT read fills, width, height, or opacity values — even though `overriddenFields` lists them.

**Fix** (in existing code):
1. In `extract_supplement.py` extraction JS: check `ov.id === node.id` for self-overrides, read values from node directly
2. For ALL override entries: read `child.fills` (JSON), `child.width/height`, `child.opacity` when those fields appear in `overriddenFields`
3. Store as new property_type entries in `instance_overrides`: "FILLS", "WIDTH", "HEIGHT", "OPACITY"
4. In `generate.py`: after createInstance(), apply self-fill overrides, size overrides, opacity overrides

### After Visual Fidelity
- Image fill reproduction (getBytesAsync → createImage)
- L3 semantic format (YAML schema)
- Additional frontends/backends

## Key Files

| File | Purpose |
|------|---------|
| `docs/compiler-architecture.md` | THE authoritative architecture spec |
| `docs/module-reference.md` | Complete API reference for all modules |
| `dd/ir.py` | IR generation, query_screen_visuals, build_composition_spec |
| `dd/generate.py` | Figma renderer (generate_figma_script, generate_screen, build_rebind_script_from_result) |
| `dd/extract_supplement.py` | Plugin API supplemental extraction (component keys + overrides) |
| `dd/rebind_prompt.py` | Token variable rebinding (L2) |
| `schema.sql` | DB schema (L0 scene graph + L1/L2 annotation tables) |

## Environment

```bash
source .venv/bin/activate
python -m pytest tests/ --tb=short          # 1,502 tests
```
