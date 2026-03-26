# Declarative Design — Roadmap

> Last updated: 2026-03-26 (session: v0.2.0-cli-rest)

## Current State

Pipeline works end-to-end when called from Python functions directly:
- REST API extraction: 83s for 338 screens, 86,761 nodes
- Clustering: 339 tokens, 100% binding coverage (205,482 bindings)
- Export: CSS custom properties, Tailwind theme, DTCG JSON
- Tests: 545 passing

## Phase 1: CLI (current priority)

Make `python -m dd` the real entry point. One command per pipeline stage:

```
dd extract <figma-url>          # REST API → SQLite
dd cluster [--threshold 2.0]    # Propose tokens from bindings
dd status                       # Show coverage, token counts, unbound
dd accept-all                   # Accept all proposed tokens
dd validate                     # Check DTCG compliance, export readiness
dd export css|tailwind|dtcg     # Write token files
```

### What exists
- `dd/cli.py` — scaffolded but not tested end-to-end
- `dd/figma_api.py` — REST API client, works in isolation
- All pipeline functions exist and are tested individually

### What needs building
- [ ] Wire CLI commands to actual pipeline functions
- [ ] FIGMA_ACCESS_TOKEN handling (env var, .env file, or prompt)
- [ ] Progress output during extraction (screen count, ETA)
- [ ] Error handling and recovery (resume interrupted extraction)
- [ ] End-to-end test: `dd extract <url> && dd cluster && dd export css`

## Phase 2: Agent Curation Protocol

The CLI handles deterministic operations. The agent (Claude Code) handles
creative/curation work by calling CLI commands and reading the DB:

- Rename tokens to semantic names (e.g., `color.surface.n10` → `color.accent.lime`)
- Merge near-duplicate tokens (ΔE < threshold)
- Generate dark mode from light mode tokens
- Conjure: natural-language design system modifications
- Push curated tokens back to Figma as variables

### What needs designing
- [ ] Which operations are CLI commands vs agent-only?
- [ ] How does the agent read DB state? (CLI `dd status --json`?)
- [ ] Conjure skill prompt template
- [ ] MCP tools for Figma variable push-back

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
