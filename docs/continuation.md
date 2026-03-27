# Continuation: Next Session

## Quick Context

Declarative Design is a CLI + agent system that extracts design tokens from Figma files, curates them, and pushes variables back. The full round-trip is proven working. T1–T4.2 are complete.

## Current State

- **DB**: `Dank-EXP-02.declarative.db` — 499 total tokens (66 color primitives [45 base + 21 alpha] + 52 color semantics + other curated + 26 aliased), 182,877 bound, 22,605 intentionally_unbound, 100% coverage
- **Figma file**: `drxXOUOdYEBBQ09mrXJeYu` (Dank Experimental)
- **Figma variables**: 374 across 8 collections (Color Primitives [66], Color Semantics, Component States+Dark, Typography, Spacing, Effects, Radius, Opacity)
- **Variable IDs**: All written back to DB (`tokens.figma_variable_id`)
- **Rebinding**: DONE — 182,877 bindings (original) + 6,207 alpha-primitive rebinds. 0 errors.
- **Alpha-baked colors**: FULLY COMPLETE. 21 alpha primitives (`prim.{hue}.{shade}.a{N}`) live in Figma. Paint opacity encoded as 8-digit hex in variable values — no opacity restoration step.
- **Tests**: 703 passing (as of T4.0 — recount after migration)
- **Tiers 1–3**: Complete. T4.0 (arch repair) done. T4.1 (primitives/semantics split) done. T4.2 (modes + alpha-baked) done.

## What To Do Next (in order)

### 1. Run Value Provenance Migration (T4.3 — do first)

The schema changes from T4.0 exist in code (`migrations/001_value_provenance.sql`, `dd/db.py`) but have NOT yet been applied to the production DB. Every future value mutation will fail without this.

```bash
source build/.venv/bin/activate
sqlite3 Dank-EXP-02.declarative.db < migrations/001_value_provenance.sql
```

Then run the data migration (already in the migration file, but verify):
```sql
UPDATE token_values SET source = 'derived'
WHERE mode_id NOT IN (SELECT id FROM token_modes WHERE is_default = 1);
```

Then re-run tests to confirm the schema is live and everything still passes.

### 2. Wire `update_token_value()` into call sites (T4.4)

`db.update_token_value(conn, token_id, mode_id, new_resolved, changed_by, reason)` exists but the existing value-mutation call sites in these files still write directly to `token_values`:

- `dd/curate.py` — all direct `UPDATE token_values` calls
- `dd/modes.py` — `copy_values_from_default()` and `apply_oklch_inversion()` writes
- `dd/export_figma_vars.py` — writeback after push

Replace each with `update_token_value()` so the history table is populated. Run tests after each file.

### 3. `dd maintenance` CLI command (T4.5)

`dd/maintenance.py` has `prune_extraction_runs(conn, keep_last=50)` and `prune_export_validations(conn, keep_last=50)`. Wire them into `dd/cli.py` as `dd maintenance [--dry-run]`.

### 4. Tier 5 — Conjure

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

## Value Provenance Architecture (T4.0 — Done in Code, Migration Pending)

`token_values` now has (after migration): `source` (`'figma'|'derived'|'manual'|'imported'`), `sync_status`, `last_verified_at`. `token_value_history` is an append-only audit table. All value mutations must go through `db.update_token_value()`. See `docs/learnings.md` "Value Provenance & History Architecture".

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
