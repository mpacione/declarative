# Continuation: Next Session

## Quick Context

Declarative Design is a CLI + agent system that extracts design tokens from Figma files, curates them, and pushes variables back. The full round-trip is proven working.

## Current State

- **DB**: `Dank-EXP-02.declarative.db` — 334 tokens (308 curated + 26 aliased), 182K bindings
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Figma variables**: 308 across 7 collections (Colors+Dark, Component States+Dark, Typography, Spacing, Effects, Radius, Opacity)
- **Variable IDs**: All 308 written back to DB (`tokens.figma_variable_id`)
- **Rebinding**: IN PROGRESS — 193 compact scripts generated, execution underway
- **Tests**: 609 passing
- **Tiers 1-3**: Complete. Tier 4 (Structural) and Tier 5 (Conjure) pending.
- **`dd push`**: DONE — CLI command generating structured JSON manifests for agent MCP execution

## What To Do Next (in order)

### 1. Complete Rebind Execution

Execute remaining rebind scripts via `figma_execute` MCP tool:

```bash
# Generate rebind manifest
python -m dd push --db Dank-EXP-02.declarative.db --phase rebind --out /tmp/rebind.json

# Agent reads manifest and executes each script via figma_execute
# 193 scripts, ~950 bindings each, <1s per script
```

After rebinding, verify visually: select nodes in Figma, check that properties show variable indicators.

### 2. Tier 4 — Structural

- T4.1: Split Primitives and Semantics into separate collections
- T4.2: Add modes (compact, high-contrast)
- See `docs/action-taxonomy.md` for full list
- Use `dd push` to verify each action: curate → `dd push --dry-run` → `dd push` → agent executes → verify

### 3. Tier 5 — Conjure

The main event. Compose new screens/components from the token vocabulary.
See `docs/action-taxonomy.md` Tier 5 section.

## Key Files

| File | Purpose |
|------|---------|
| `dd/cli.py` | CLI entrypoint — all `python -m dd` commands including `push` |
| `dd/push.py` | Push manifest generation (variable actions + rebind orchestration) |
| `dd/export_figma_vars.py` | Variable payload generation + writeback |
| `dd/export_rebind.py` | Compact rebind script generation |
| `dd/drift.py` | DB↔Figma drift detection and value comparison |
| `dd/figma_api.py` | REST API client + node tree conversion |
| `dd/modes.py` | Dark mode / theme creation (OKLCH) |
| `dd/curate.py` | All curation operations (rename, merge, split, alias) |
| `dd/curate_report.py` | Generates structured curation report |
| `docs/action-taxonomy.md` | Full taxonomy of all curation/conjure actions |
| `docs/tier-progress.md` | Progress tracker for each tier |
| `docs/learnings.md` | Accumulated infrastructure insights |
| `declarative-design/SKILL.md` | Agent protocol (CLI + curation) |

## `dd push` Usage

```bash
# First push (no existing Figma state):
python -m dd push --db Dank-EXP-02.declarative.db --dry-run
python -m dd push --db Dank-EXP-02.declarative.db --phase variables
# Agent executes MCP actions from manifest
# Agent: figma_get_variables → save response
python -m dd push --db Dank-EXP-02.declarative.db --writeback --figma-state response.json
python -m dd push --db Dank-EXP-02.declarative.db --phase rebind
# Agent executes rebind scripts via figma_execute

# Incremental push (after curation changes):
# Agent: figma_get_variables → save to figma_state.json
python -m dd push --db Dank-EXP-02.declarative.db --figma-state figma_state.json --dry-run
python -m dd push --db Dank-EXP-02.declarative.db --figma-state figma_state.json --phase variables
# Agent executes actions, then rebind phase
```

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
