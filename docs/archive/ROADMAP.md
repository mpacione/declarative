# Declarative Design — Roadmap

> Last updated: 2026-03-26

## Current State

Full pipeline works end-to-end: extract → cluster → curate → push → rebind.
- REST API extraction: 83s for 338 screens, 86,761 nodes
- Clustering: 339 tokens, 100% binding coverage (205,482 bindings)
- Curation: Tiers 1-3 complete (308 curated + 26 aliased tokens)
- Export: CSS, Tailwind, DTCG JSON, Figma variables (308 across 7 collections)
- Push: `dd push` CLI generates manifests for agent MCP execution
- Rebinding: 193 compact scripts, execution in progress
- Tests: 609 passing

## Phase 1: CLI — DONE

All commands wired and tested:

```
dd extract <figma-url>          # REST API → SQLite
dd cluster [--threshold 2.0]    # Propose tokens from bindings
dd status                       # Show coverage, token counts, unbound
dd accept-all                   # Accept all proposed tokens
dd validate                     # Check DTCG compliance, export readiness
dd export css|tailwind|dtcg     # Write token files
dd curate-report [--json]       # Structured curation issues for agent
dd push [--phase variables|rebind|all] [--figma-state FILE] [--dry-run]  # Figma sync
```

## Phase 2: Agent Curation Protocol — DONE (Tiers 1-3)

- [x] CLI for deterministic, agent for judgment
- [x] `dd curate-report --json` bridges CLI → agent
- [x] Curation operations: rename, merge, split, alias, reject
- [x] Dark mode derivation (OKLCH)
- [x] Component token generation
- [x] `dd push` for Figma variable sync + rebinding
- [ ] Tier 4: Structural (split primitives/semantics, add modes)
- [ ] Tier 5: Conjure (compose screens/components from token vocabulary)

## Phase 3: Dashboard UX

Local web UI so designers don't need CLI or prompting knowledge:
- Pipeline progress visualization
- Token review cards (color swatches, type previews, spacing bars)
- One-button happy path (Extract → Review → Export)
- System health panel (API rate limits, DB status, event log)

### Open questions
- Figma plugin vs localhost web app vs desktop app?
- How much curation control do designers actually want?
- Does the dashboard replace the agent or complement it?
