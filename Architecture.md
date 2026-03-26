# Declarative Design — Architecture

Date: 2025-03-25
Status: In progress — post-probe, pre-implementation

## The Problem

Designers cannot work declaratively. Developers say "build me a settings page" and get working code using their project's tokens and components. Designers have no equivalent. Every AI design tool generates generic output disconnected from their actual design system.

The missing piece is persistent, structured design system context that agents can consume before composing.

## Core Use Cases

### A) Conjure — Images/Prompts to Figma Screens
Input: Wireframes, sketches, screenshots, or natural language + design system context
Output: Composed screens in Figma using real components, real variables, real tokens

Design system context can come from: existing Figma library, frontend codebase, reference designs, prebuilt starter (shadcn, Radix, Material), or organic accumulation.

### B) Distill — Frontend Repo to Figma Design System + Screens
Input: Codebase with CSS tokens, React/Vue/Svelte components, optionally Storybook
Output: Figma variable collections + component metadata + optionally composed screens

### C) Export — Figma to Code (lower priority, largely solved)
Handled by Figma MCP get_design_context + Code Connect.

### Key Insight
A and B are the same problem with different inputs. Both require the agent to understand a design system before it can compose.

## Architecture

### The Local DB as Portable Source of Truth

Figma <-> Console MCP <-> DB <-> Coding Agent <-> Codebase
           (free sync)    ^      (any IDE/CI)
                          |
                    The portable
                    source of truth

The DB serves a different audience than Console MCP. Console MCP is the Figma read/write layer. The DB is the universal design system interface that any tool can consume — including coding agents that do not have Figma running.

### What the DB Stores — Three Levels

**System** — tokens, component definitions, patterns. The vocabulary.
- Tokens: colors, spacing, typography, radius, shadows, opacity
- Components: name, props, variant dimensions, composition hints
- Patterns: layout recipes (nav/sidebar, card/pricing, form/settings)

**Compositions** — screens/views, their component trees, layout rules, token bindings. The sentences.
- Screen inventory with component nesting (parent-child)
- Layout structure (flex direction, gaps, alignment, padding)
- Token bindings per node (which token applies where)
- This tells a coding agent what to build, not just what to build with

**Mappings** — the rosetta stone between tools.
- Figma variable ID <-> CSS custom property <-> Tailwind class <-> React component <-> route

### Tool Strategy

Console MCP (primary, free, unlimited):
- figma_setup_design_tokens (atomic token system creation)
- batch variable CRUD
- audit / lint
- figma_execute
- real-time awareness
- dedicated node tools

Official MCP (selective, metered):
- use_figma (sync traversal for bulk reads)
- get_design_context (code generation)
- Code Connect
- generate_figma_design (web page capture)

### Read/Write Strategy

Import (Figma to DB): Pay once per sync. Extract everything, store locally. Uses Figma REST API directly via CLI (`python -m dd extract`) — no MCP tools needed, no agent in the loop.

Work (DB only): Free. All analysis, clustering, token creation, pattern extraction, drift detection, composition planning against local SQLite.

Export to Figma (DB to Figma): Console MCP figma_setup_design_tokens (atomic, 100 tokens/call). For rebinding: generate plugin script, paste into Figma console (zero MCP calls).

Export to Code (DB to Codebase): Agent reads tokens, components, compositions from SQLite. No Figma calls needed.

## Schema Design Principles

1. SQLite for storage. Portable, zero-config, queryable.
2. Selective loading. Agent requests just color tokens, one component, or drifted items.
3. W3C DTCG v2025.10 compatible token format.
4. Token tiers reflect maturity: extracted vs curated vs aliased (not primitive/semantic/component yet).
5. Alias resolution via self-referential FK (alias_of -> token.id) plus denormalized resolved_value.
6. Compositions store instance references, components store definitions.
7. extracted_at timestamps on everything for freshness tracking.
8. Multi-file support via files table with file_key FK.

## Open Schema Questions

1. Token values: separate token_values table (per-mode rows) vs JSON column?
2. How deep to store composition tree? Full nesting or collapsed to meaningful containers?
3. Store raw Figma RGBA (0-1 floats) or normalized hex/DTCG format?
4. Tokens in code but not Figma: sync_status enum or separate tables?
5. Patterns table structure: how to represent composition recipes?

## Next Steps

1. Draft CREATE TABLE statements informed by probe data shapes
2. Build extraction pipeline: iterate screens via use_figma, pipe to SQLite
3. Run extraction on full Dank file (~230 screens, ~230 calls, ~15 min)
4. Cluster extracted values, propose token taxonomy
5. Create variables via figma_setup_design_tokens (1-3 calls)
6. Generate rebind plugin script, test on subset, run on full file
