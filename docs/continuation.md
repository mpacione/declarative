# Continuation: Next Session

## Quick Context

Declarative Design is a CLI + agent system that extracts design tokens from Figma files, curates them, and pushes variables back. The full round-trip is proven working. T1–T4.2 are complete.

## Current State

- **DB**: `Dank-EXP-02.declarative.db` — 388 total tokens (45 color primitives + 52 color semantics + other curated + 26 aliased), 182,871 bound, 22,611 intentionally_unbound, 50 unbound (36 gradients). Validation: 0 errors, 102 warnings (45 expected primitive orphans, 57 binding-token mismatches from Figma scaling)
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Figma variables**: 374 across 8 collections (Color Primitives [66], Color Semantics, Component States+Dark, Typography, Spacing, Effects, Radius, Opacity)
- **Variable IDs**: All written back to DB (`tokens.figma_variable_id`)
- **Rebinding**: DONE — 182,877 bindings (original) + 6,207 alpha-primitive rebinds. 0 errors.
- **Alpha-baked colors**: FULLY COMPLETE. 21 alpha primitives (`prim.{hue}.{shade}.a{N}`) live in Figma. Paint opacity encoded as 8-digit hex in variable values — no opacity restoration step.
- **Tests**: 729 passing
- **Tiers 1–3**: Complete. T4.0–T4.5 complete (arch repair, primitives/semantics, modes, migration, value provenance wiring, maintenance CLI).

## What To Do Next (in order)

### 1. Tier 5 — Conjure

The main event. Compose new screens/components from the token vocabulary. See `docs/action-taxonomy.md` Tier 5 section.

## Key Files

| File | Purpose |
|------|---------|
| `dd/cli.py` | CLI entrypoint — all `python -m dd` commands |
| `dd/push.py` | Push manifest generation (variable actions + rebind) |
| `dd/export_figma_vars.py` | Variable payload generation + writeback |
| `dd/export_rebind.py` | Compact rebind scripts |
| `dd/drift.py` | DB-Figma drift detection and value comparison |
| `dd/modes.py` | Dark mode / theme creation (OKLCH) |
| `dd/curate.py` | All curation operations |
| `dd/db.py` | `update_token_value()` — use this for all value mutations |
| `dd/maintenance.py` | Retention policy functions (not yet wired to CLI) |
| `dd/validate.py` | Validation checks including binding-token consistency |
| `docs/action-taxonomy.md` | Full taxonomy of all curation/conjure actions |
| `docs/tier-progress.md` | Progress tracker for each tier |
| `docs/learnings.md` | Accumulated infrastructure insights |
| `migrations/001_value_provenance.sql` | **Must be run on production DB before any value mutations** |
| `patches/figma-console-mcp-proxy-execute.patch` | PROXY_EXECUTE patch for large script execution |
| `declarative-design/SKILL.md` | Agent protocol v0.4.0 |

## Alpha-Baked Colors (Complete)

Paint opacity is encoded directly in color variable values as 8-digit hex (`#RRGGBBAA`). 21 alpha primitives (`prim.gray.950.a5`, `prim.gray.50.a40`, etc.) live in Figma. The `restore_opacities` phase has been removed from the push manifest entirely. OKLCH inversion and high-contrast transforms preserve alpha suffix correctly.

## PROXY_EXECUTE (For Future Large Script Runs)

For scripts too large for `figma_execute` (>50K chars), use the PROXY_EXECUTE WebSocket bridge:

1. Check port 9224 process is running the patched server: `lsof -i :9224`
2. If server PID predates any patch changes, kill it and restart Claude Desktop
3. Connect to `ws://127.0.0.1:9224`, wait for `SERVER_HELLO`, send `{"type":"PROXY_EXECUTE","id":"x","code":"...","timeout":30000}`
4. Await `PROXY_EXECUTE_RESULT`

See `patches/figma-console-mcp-proxy-execute.patch` and `docs/learnings.md` for full pattern.

## Value Provenance Architecture (T4.0 + T4.3 — Complete)

`token_values` has `source` (`'figma'|'derived'|'manual'|'imported'`), `sync_status`, `last_verified_at`. `token_value_history` is an append-only audit table. Migration applied to prod DB (`source='derived'` on 616 non-default mode rows, `source='figma'` on 310 default rows). All value mutations must go through `db.update_token_value()` — call sites not yet updated (T4.4). See `docs/learnings.md` "Value Provenance & History Architecture".

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
