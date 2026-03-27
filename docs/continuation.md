# Continuation: Next Session

## Quick Context

Declarative Design is a CLI + agent system that extracts design tokens from Figma files, curates them, and pushes variables back. The full round-trip is proven working. Primitives/semantics split is done for colors.

## Current State

- **DB**: `Dank-EXP-02.declarative.db` — 379 tokens (45 color primitives + 52 color semantics + 282 other curated + 26 aliased), 182K bindings
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Figma variables**: 353 across 8 collections (Color Primitives, Color Semantics+Dark, Component States+Dark, Typography, Spacing, Effects, Radius, Opacity)
- **Variable IDs**: All written back to DB (`tokens.figma_variable_id`)
- **Rebinding**: DONE — 182,877 bindings, 0 errors
- **Alpha-baked colors**: Steps 1-6 complete. Paint opacity is now encoded in color values as 8-digit hex (`#RRGGBBAA`). The `restore_opacities` phase has been removed from the push manifest. Steps 7-9 (re-extract, re-cluster, push) pending.
- **Tests**: 656 passing
- **Tiers 1-3**: Complete. T4.1 (Primitives/Semantics split) complete. T4.2 modes done in DB (alpha-baked colors steps 1-6 done, steps 7-9 pending). T4.3-T4.5 pending. T5 (Conjure) pending.

## What To Do Next (in order)

### 1. Alpha-Baked Colors — Steps 7-9 (immediate)

Complete the alpha-baked color pipeline. All code changes are done (Steps 1-6, 656 tests). The remaining steps use existing CLI commands on existing DB data:

1. **Re-extract bindings**: Run `extract_bindings` on all screens to regenerate `node_token_bindings` with alpha-inclusive `resolved_value`. This uses the existing `nodes.fills`/`strokes`/`effects` JSON columns — no Figma API call needed.
2. **Re-cluster**: Run `dd cluster` to create ~29 new alpha-baked primitives (e.g., `prim.gray.950.a5`, `prim.gray.950.a25`). Colors at different alphas will now be distinct clusters.
3. **Push and rebind**: Push new alpha-baked primitives to Figma as variables. Rebind affected nodes to the new tokens. Test mode switching — opacity should now persist through mode changes since it is encoded in the variable value.

### 2. Tier 4.3-T4.5 — Structural

- T4.3: Restructure naming convention
- T4.4: Re-cluster with different parameters
- T4.5: Import external token set (Radix, shadcn, Material)

### 3. Tier 5 — Conjure

The main event. Compose new screens/components from the token vocabulary.
See `docs/action-taxonomy.md` Tier 5 section.

## Key Files

| File | Purpose |
|------|---------|
| `dd/cli.py` | CLI entrypoint — all `python -m dd` commands including `push` |
| `dd/push.py` | Push manifest generation (variable actions + rebind + opacity restore) |
| `dd/export_figma_vars.py` | Variable payload generation + writeback |
| `dd/export_rebind.py` | Compact rebind scripts + opacity restoration scripts |
| `dd/drift.py` | DB-Figma drift detection and value comparison |
| `dd/figma_api.py` | REST API client + node tree conversion |
| `dd/modes.py` | Dark mode / theme creation (OKLCH) |
| `dd/curate.py` | All curation operations (rename, merge, split, alias, create_collection, convert_to_alias) |
| `dd/curate_report.py` | Generates structured curation report |
| `docs/action-taxonomy.md` | Full taxonomy of all curation/conjure actions |
| `docs/tier-progress.md` | Progress tracker for each tier |
| `docs/learnings.md` | Accumulated infrastructure insights |
| `declarative-design/SKILL.md` | Agent protocol v0.4.0 (CLI + curation + push + alpha-baked colors) |

## Alpha-Baked Colors

Paint opacity is now encoded directly in color variable values as 8-digit hex (`#RRGGBBAA`). This eliminates the previous `restore_opacities` post-step entirely. Figma reads the alpha from the color value itself, so opacity persists through variable re-evaluation, mode switching, and alias updates. See `docs/learnings.md` "Alpha-Baked Color Architecture" section for full details.

## Environment

```bash
source build/.venv/bin/activate
export FIGMA_ACCESS_TOKEN="<your-figma-pat>"

# Quick health check
python -m dd status --db Dank-EXP-02.declarative.db

# Run tests
python -m pytest tests/ --tb=short
```

Figma Desktop Bridge plugin must be running for MCP rebinding operations.
PROXY_EXECUTE patch on figma-console-mcp WebSocket server enables direct script execution (see `patches/` directory).
