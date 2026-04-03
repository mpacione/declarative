# Continuation: Next Session

## Quick Context

Declarative Design is a bi-directional design compiler. Parses UI from any source into an abstract compositional IR, generates to any target with token-bound fidelity. T1-T4 complete (property pipeline). T5 in progress (composition layer).

## Current State (2026-04-02)

- **DB**: `Dank-EXP-02.declarative.db` — 86,761 nodes (72 columns), 182,871 bindings, 388 tokens, 338 screens (204 app screens)
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental) — 374 variables, 8 collections
- **Extraction**: Complete. REST API + Plugin API supplemental. 60K constraints, 25K component keys populated.
- **Classification**: 93.6% coverage (47,292 classified nodes). Zero missed on app screens.
- **Tests**: 1,217 passing
- **Branch**: `t5/architecture-vision`

## Architecture: Four-Layer Model

See `docs/t5-four-layer-architecture.md` (1,640+ lines, fully steelmanned):

```
Layer 1: EXTRACTION     Source → DB        "Record everything"
Layer 2: ANALYSIS        DB → Abstractions  "Understand what's there"
Layer 3: COMPOSITION     Abstractions → IR   "Describe what to build"
Layer 4: RENDERING       IR + DB/Config → Output  "Build it concretely"
```

Key decisions: thin IR (no visual section), semantic tree (116→20 elements with named slots), renderer reads DB directly for visual detail, instance-first Figma rendering, default library fallback. Synthetic tokens deferred to composition layer.

## What To Do Next

### Phase 4b: Prompt→IR composition + template-based rendering
Compose IR from natural language prompts using the extracted templates and screen patterns. Render to Figma using Mode 1 (componentKey instances) and Mode 2 (frame construction from templates). End-to-end prompt→Figma screen.

### Before Phase 1, consider:
- Run `extract_components()` on Dank file to populate the 6 empty composition tables
- This gives slot definitions, variant axes, and a11y contracts — useful for Phase 3 (semantic tree)

## Extraction Workflow

```bash
# Step 1: REST API — fast, reliable, ~90% of properties
python -m dd extract drxXOUOdYEBBQ09mrXJeYu --db Dank-EXP-02.declarative.db

# Step 2: Plugin API — componentKey, layoutPositioning, Grid (requires Desktop Bridge)
python -m dd extract-supplement --db Dank-EXP-02.declarative.db --port 9227

# Migration (already applied to Dank DB, needed for new DBs from older schemas)
# sqlite3 <db> < migrations/006_extraction_completeness.sql
```

## Key Files

| File | Purpose |
|------|---------|
| `docs/t5-four-layer-architecture.md` | THE authoritative architecture spec |
| `docs/module-reference.md` | Complete API reference for all 38 modules |
| `docs/learnings.md` | Accumulated insights (extraction, pipeline, architecture) |
| `.claude/plans/dynamic-watching-rose.md` | Phase 0 implementation plan (completed) |
| `dd/ir.py` | IR generation + `query_screen_visuals()` + `_node_id_map` (Phase 0 additions) |
| `dd/generate.py` | Figma renderer (now reads DB visual via `build_visual_from_db` + `db_visuals` param) |
| `dd/extract_supplement.py` | Plugin API supplemental extraction (componentKey, layoutPositioning, Grid) |
| `dd/extract_components.py` | Component discovery (built, not run on Dank — needed for Phase 3) |
| `tests/test_phase0_integration.py` | Integration tests against real Dank DB for Phase 0 |
| `tests/test_phase1_integration.py` | Parity tests: IR vs DB visual paths on real Dank DB |

## Environment

```bash
source .venv/bin/activate

# Quick health check
python -m dd status --db Dank-EXP-02.declarative.db

# Run tests
python -m pytest tests/ --tb=short

# 1017 tests should pass
```

Figma Desktop Bridge plugin required for Plugin API extraction and Figma generation.
PROXY_EXECUTE patch on figma-console-mcp WebSocket server enables large script execution.
