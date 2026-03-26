# Continuation: Next Session

## Quick Context

Declarative Design is a CLI + agent system that extracts design tokens from Figma files, curates them, and pushes variables back. The full round-trip is proven working.

## Current State

- **DB**: `Dank-EXP-02.declarative.db` — 334 tokens (308 curated + 26 aliased), 182K bindings
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Figma variables**: 308 across 7 collections (Colors+Dark, Component States+Dark, Typography, Spacing, Effects, Radius, Opacity)
- **Variable IDs**: All 308 written back to DB (`tokens.figma_variable_id`)
- **Rebinding**: 27/182,877 done (proof of concept). Script generation works, execution works.
- **Tests**: 545 passing
- **Tiers 1-3**: Complete. Tier 4 (Structural) and Tier 5 (Conjure) pending.

## What To Do Next (in order)

### 1. Full Rebind (~6 min)

Run all 366 rebinding batches so the Figma file shows variable bindings on all nodes.

```python
from dd.db import get_connection
from dd.export_rebind import generate_rebind_scripts

conn = get_connection("Dank-EXP-02.declarative.db")
scripts = generate_rebind_scripts(conn, file_id=1)
# Execute each script via figma_execute MCP tool (batches of ~500 bindings, ~8KB each)
# Each takes <1s. 366 scripts total.
```

After rebinding, verify visually: select nodes in Figma, check that properties show variable indicators.

### 2. Build `dd push` CLI Command

Automates: create/update variables → write back IDs → generate rebind scripts → execute → verify.

Key learnings to incorporate (see `docs/learnings.md`):
- Batch typography into 100-token chunks for `figma_setup_design_tokens`
- Use `figma_batch_create_variables` for overflow
- Write back variable IDs immediately after creation
- Rebind in batches of 50 bindings (~8KB scripts)
- Check for duplicate collections before creating
- Convert DB string values to Figma native types (FLOAT/STRING/COLOR)

### 3. Tier 4 — Structural

- T4.1: Split Primitives and Semantics into separate collections
- T4.2: Add modes (compact, high-contrast)
- See `docs/action-taxonomy.md` for full list

### 4. Tier 5 — Conjure

The main event. Compose new screens/components from the token vocabulary.
See `docs/action-taxonomy.md` Tier 5 section.

## Key Files

| File | Purpose |
|------|---------|
| `dd/cli.py` | CLI entrypoint — all `python -m dd` commands |
| `dd/figma_api.py` | REST API client + node tree conversion |
| `dd/export_rebind.py` | Rebinding script generation |
| `dd/modes.py` | Dark mode / theme creation (OKLCH) |
| `dd/curate.py` | All curation operations (rename, merge, split, alias) |
| `dd/curate_report.py` | Generates structured curation report |
| `docs/action-taxonomy.md` | Full taxonomy of all curation/conjure actions |
| `docs/tier-progress.md` | Progress tracker for each tier |
| `docs/learnings.md` | Accumulated infrastructure insights |
| `declarative-design/SKILL.md` | Agent protocol (CLI + curation) |

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
