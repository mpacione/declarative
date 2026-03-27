# Continuation: Next Session

## Quick Context

Declarative Design is a CLI + agent system that extracts design tokens from Figma files, curates them, and pushes variables back. The full round-trip is proven working. T1–T4.2 are complete.

## Current State

- **DB**: `Dank-EXP-02.declarative.db` — 388 total tokens, 182,871 bound, 22,611 intentionally_unbound, 50 unbound (36 gradients). Validation: 0 errors, 102 warnings (45 expected primitive orphans, 57 scaling mismatches).
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Figma variables**: 374 across 8 collections. All variable IDs written back to DB.
- **Alpha-baked colors**: FULLY COMPLETE. 21 alpha primitives in Figma. Alpha rebinds re-applied across all 3 property classes (fills, effects, strokes).
- **Extended properties**: Schema expanded with 22 new columns (stroke, transform, constraints, layout, typography, component). Migration `002_extended_properties.sql` ready for prod.
- **Tests**: 753 passing
- **Tiers 1–3**: Complete. T4.0–T4.6 complete (arch repair through comprehensive property extraction).

## What To Do Next (in order)

### 1. Apply migration 002 to production DB

```bash
sqlite3 Dank-EXP-02.declarative.db < migrations/002_extended_properties.sql
```

Then re-extract to populate the new columns. Existing data is unaffected (new columns default NULL).

### 2. Re-extract with extended properties

Re-run extraction on the Dank file to populate the 22 new columns (stroke, transform, constraints, layout, typography, component_key). Existing bindings and tokens are preserved.

### 3. Tier 5 — Conjure

The main event. Compose new screens/components from the token vocabulary. See `docs/action-taxonomy.md` Tier 5 section. The extended properties (component_key, instance_overrides, full layout/constraint data) provide everything needed for programmatic screen generation.

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
| `dd/maintenance.py` | Retention policy (wired to CLI via `dd maintenance`) |
| `dd/validate.py` | Validation checks including binding-token consistency |
| `docs/action-taxonomy.md` | Full taxonomy of all curation/conjure actions |
| `docs/tier-progress.md` | Progress tracker for each tier |
| `docs/learnings.md` | Accumulated infrastructure insights |
| `migrations/001_value_provenance.sql` | Value provenance schema (applied to prod) |
| `migrations/002_extended_properties.sql` | **Must be run on production DB before re-extraction** |
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

## Value Provenance Architecture (Complete)

`token_values` has `source` (`'figma'|'derived'|'manual'|'imported'`), `sync_status`, `last_verified_at`. `token_value_history` is an append-only audit table. All value mutations go through `db.update_token_value()` (updates) or `db.insert_token_value()` (first writes). Both write history rows automatically.

## Extended Properties (T4.6 — Complete)

22 new columns on `nodes` table covering stroke, transform, constraints, layout extensions, typography extensions, and component key. `instance_overrides` table for component property tracking. Extraction (REST + Plugin API), normalization (4 new functions), clustering (stroke weight, paragraph spacing), and rebinding (visible + BOOLEAN type) all implemented. See `docs/learnings.md` "Extended Property Extraction".

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
