# Declarative Design — User Requirements Spec

Status: Draft v0.2
Date: 2025-03-25

## Problem

Designers cannot work declaratively. A developer says "build me a settings page" and gets working code grounded in their project's tokens and components. A designer gets generic output disconnected from their actual design system. The gap is persistent, structured design system context that AI agents can consume before composing.

This system closes that gap by extracting, structuring, and serving design system knowledge from existing Figma files (and eventually codebases) into a portable local database that any agent — Figma-connected or not — can query.

## Users

**U1 — Designer (Matt, initially sole user)**
Works in Figma. Wants to go from a hardcoded file with ~230 screens and zero variables to a tokenized, composable design system — without manually creating hundreds of variables and rebinding thousands of nodes. Future state: conjures new screens from prompts grounded in real system context.

**U2 — Coding Agent (Claude, Cursor, Copilot, any LLM)**
Receives a task like "build the settings page." Needs to know: what components exist, what tokens to use, what the screen layout looks like, what route it maps to. Reads directly from the DB — no Figma running, no MCP calls, no rate limits.

**U3 — Design System Maintainer (future)**
Monitors drift between Figma and code. Gets alerted when a token is used in code but missing in Figma (or vice versa). Runs audits, tracks coverage, manages the curation lifecycle.

## Use Cases

### UC-1: Extract — Figma File to Structured DB
**Actor:** U1
**Trigger:** User points the pipeline at a Figma file/page.
**Flow:**
1. Pipeline reads file metadata (node count, screen inventory, component list).
2. Pipeline classifies top-level frames as screens (by device dimensions) or component sheets (by name heuristics + non-standard dimensions).
3. Pipeline iterates all screens, extracting every node's visual properties, layout rules, and component references.
4. Raw values are stored in the DB with full fidelity (RGBA floats, font objects, effect arrays).
5. Normalized values (hex, px, font shorthand) are computed and stored alongside for querying.
6. Every extracted value gets a `node_token_bindings` row with `binding_status = unbound`.
7. Nodes are flagged `is_semantic = 1` when they represent meaningful containers (named components, auto-layout frames with children, text nodes) vs. structural noise (unnamed groups, single-child wrappers).
8. Progress is reported per-screen (screen N/230, node count, elapsed time, ETA).
**Acceptance:**
- `screens` table contains rows for all top-level frames, classified by `device_class`. Count matches Figma canvas.
- `nodes` table contains ≥95% of all nodes in the file (verified by comparing `SUM(node_count)` from screens table against Figma's reported 25,547).
- Every node with a fill, stroke, effect, corner radius, font property, or layout property has corresponding `node_token_bindings` rows.
- Census views (`v_color_census`, `v_type_census`, `v_spacing_census`, `v_radius_census`, `v_effect_census`) return populated results with plausible value distributions (no single value >80% share unless the file genuinely uses it).
- `raw_value` round-trips losslessly: converting resolved_value back to the raw format matches the original (verified on 50 random bindings).
- Extraction completes in <20 minutes for the Dank file (~230 screens, ~25K nodes).
- Extraction is resumable: if interrupted at screen 147, re-running picks up at 147 without re-extracting 1-146.

### UC-2: Cluster — Propose Token Taxonomy
**Actor:** U1
**Trigger:** Extraction complete.
**Flow:**
1. System queries census views to surface unique values ranked by usage frequency.
2. System groups near-identical values (e.g., `#09090B` and `#0A0A0B` within OKLCH ΔE threshold).
3. System proposes token names following DTCG path conventions (e.g., `color.surface.primary`), using context heuristics (node type, property role, area covered) to assign semantic categories.
4. Proposed tokens are created with `tier = extracted`, bindings flipped to `binding_status = proposed`, each scored with a `confidence` value.
5. User reviews proposals — accepts, renames, merges, splits, or rejects.
6. Accepted tokens promoted to `tier = curated`.
**Acceptance:**
- ≥90% of `unbound` bindings are assigned a proposed token (remaining 10% are legitimate one-offs or design inconsistencies).
- Each proposed token has a `confidence` score. Exact color matches = 1.0, ΔE-merged = 0.8-0.99.
- Proposed token names are unique within their collection and follow DTCG dot-path conventions.
- The system produces a clear summary: N tokens proposed across K types, M bindings assigned, L bindings flagged for review.
- User can complete curation review (accept/rename/merge/reject all proposals) in <30 minutes for a ~230 screen file.
- No token is created with 0 bindings (orphan tokens).

### UC-3: Export to Figma — Create Variables + Rebind
**Actor:** U1
**Trigger:** Curation complete.
**Flow:**
1. System generates `figma_setup_design_tokens` calls from curated tokens (up to 100 tokens/call), including all modes per collection.
2. Variables created in Figma. Figma variable IDs written back to `tokens.figma_variable_id`.
3. System generates rebind plugin script(s) that map `node_token_bindings` to Figma `setBoundVariableForPaint` / `setBoundVariableForEffect` / `setBoundVariable` calls, covering all property types (fills, strokes, effects, corner radius, font properties, spacing, opacity).
4. System executes scripts via Console MCP `figma_execute` (automated) or user pastes into Figma console (manual fallback).
5. Bindings flipped to `binding_status = bound`.
**Acceptance:**
- All curated tokens exist as Figma variables in the correct collections with correct mode values. Verified by querying `figma_get_variables` and comparing against DB.
- Every `node_token_bindings` row with `binding_status = bound` has a corresponding Figma variable binding on the target node. Verified by spot-checking 20 random nodes via `use_figma`.
- Visual diff shows zero regressions: same pixels rendered, different implementation (hardcoded → variable-bound). Verified by screenshot comparison of 10 representative screens before/after rebinding.
- Figma audit score (`figma_audit_design_system`) jumps from 0 tokens to >80% token coverage.
- Rebinding completes in <30 minutes for the full file (automation, not manual paste).
- Pre-export validation gate passes before any Figma write: `v_export_readiness` shows 0 errors. Checks include: orphan tokens (no bindings), mode completeness (every token has every mode), alias cycles, missing `resolved_value`, and unresolved alias targets.
- Export is blocked if validation gate has error-severity issues. Warnings are logged but don't block.

### UC-4: Export to Code — DB to Frontend Tokens
**Actor:** U2
**Trigger:** Coding agent receives a build task.
**Flow:**
1. Agent queries DB for relevant tokens (e.g., all color tokens, all spacing tokens), resolving aliases via `alias_of` chain.
2. Agent queries DB for target screen's composition tree (nodes, layout, component refs, token bindings).
3. Agent queries `code_mappings` to translate token names to target format (CSS custom properties, Tailwind classes, Swift constants).
4. Agent generates code using real token values and real component structure.
**Acceptance:**
- Agent can retrieve all tokens for a given type in a single query (no N+1 queries).
- Agent can retrieve a full screen composition (nodes + bindings + component refs) in ≤3 queries.
- Generated code uses token references (CSS vars, Tailwind classes) for every property that has a `bound` binding in the DB. Zero hardcoded values for tokenized properties.
- Alias tokens resolve to their target's value without the agent needing to manually traverse the chain (handled by a view or query pattern).
- DTCG-format `tokens.json` export is available alongside CSS/Tailwind for toolchain interop.

### UC-5: Add Theme — Extend Token System with a New Mode/Collection
**Actor:** U1
**Trigger:** User wants to add a theme (Dark, Compact, Brand B, High Contrast, etc.) to an existing curated token system. A theme is a collection of mode-specific values applied to the same token set — fills, strokes, effects, spacing, typography properties, opacity — not limited to color lightness inversion.
**Flow:**
1. User creates a new mode in the target collection(s) (e.g., "Dark" mode in the "Colors" collection, "Compact" mode in "Spacing"). A theme may span multiple collections.
2. System copies all curated token values from the default mode as starting points for the new mode.
3. User modifies mode-specific values — either manually, via conversation with an agent, or via heuristic transforms (OKLCH lightness inversion for dark, scale factor for compact, brand color mapping for Brand B).
4. System validates mode completeness: every token in each affected collection has a value for every mode. Validated via `v_export_readiness` check `mode_completeness`.
5. Mode-specific census views (`v_color_census_by_mode`) and clustering can be run independently — the system proposes shared tokens with mode-specific values or mode-unique tokens as warranted.
6. On export, `figma_setup_design_tokens` includes all modes in the payload. Figma creates variable collections with mode switching built in.
**Acceptance:**
- Every token in each affected collection has exactly N values (one per mode). No partial mode coverage. Verified by `SELECT * FROM v_export_readiness WHERE check_name = 'mode_completeness'` returning 0 errors.
- Mode-specific values are independent — changing Dark doesn't affect Light.
- Census views and clustering can be run per-mode (`v_color_census_by_mode` returns correct filtered results).
- Figma export creates variables with correct per-mode values. Switching modes in Figma renders the expected values on all bound nodes.
- Adding a mode does not require re-extraction or re-binding — it's a DB + Figma variable operation only.
- Theme can span multiple collections (colors + effects + spacing) in a single operation.
- A theme can include non-color properties: shadow intensity, border width, spacing scale, opacity values.

### UC-6: Detect Drift — Monitor Figma/Code/DB Divergence
**Actor:** U3
**Trigger:** Periodic check, or user requests a sync audit.
**Flow:**
1. System re-reads current Figma variable values via `figma_get_variables` or `use_figma`.
2. System compares Figma values against DB `token_values.resolved_value` for each token.
3. Divergences flagged: token still `pending` (never exported to Figma), token value in Figma differs from DB (`synced` → `drifted`), token exists in Figma but not DB (`figma_only`), token exists in code but not Figma (`code_only`).
4. System produces a drift report: N tokens synced, M drifted, L missing from Figma, K missing from code.
5. User chooses resolution: update DB from Figma, update Figma from DB, or flag for manual review.
**Acceptance:**
- Drift detection runs without modifying any data (read-only until user confirms resolution).
- Every token has a current `sync_status` that accurately reflects its state across DB, Figma, and code.
- Drifted tokens show both the DB value and the Figma value for comparison.
- Drift report is queryable via `v_drift_report` — shows token name, DB value, mode, collection, and sync status for all non-synced tokens.

### UC-7: Conjure — Prompt to Figma Screen (future)
**Actor:** U1
**Trigger:** User describes a screen in natural language or provides a wireframe/screenshot.
**Flow:**
1. Agent queries DB for available components, tokens, and relevant patterns.
2. Agent composes a screen using real components and real tokens.
3. Agent creates the screen in Figma via Console MCP, binding variables to every property.
**Acceptance:**
- Generated screen uses only tokens and components from the design system. No hardcoded values.
- Every fill, stroke, effect, spacing, and typography property is variable-bound.
- Component instances reference existing components (not detached copies).

### UC-8: Distill — Codebase to Design System (future)
**Actor:** U1
**Trigger:** User points the pipeline at a frontend repo.
**Flow:**
1. Pipeline parses CSS custom properties, Tailwind config, component files.
2. Tokens extracted and stored with `sync_status = code_only`.
3. Components extracted with prop definitions, variant axes.
4. User curates, then exports to Figma via UC-3.
**Acceptance:**
- Tokens and components from code are represented in the DB with enough fidelity to generate Figma variables and inform screen composition.
- Code-origin tokens are tagged `sync_status = code_only` and can be filtered/queried independently.
- `code_mappings` table links each code-origin token back to its source file path and identifier.

## Functional Requirements

### FR-1: Extraction
- FR-1.1: Extract all visual properties from all node types (FRAME, TEXT, RECTANGLE, INSTANCE, VECTOR, ELLIPSE, GROUP).
- FR-1.2: Preserve full Figma fidelity in `raw_value` (RGBA 0-1 floats, font objects, gradient stops, effect arrays).
- FR-1.3: Compute normalized `resolved_value` for every raw value (hex for colors, px for dimensions, font shorthand for typography).
- FR-1.4: Extract complete auto-layout properties (direction, padding 4-sided, item spacing, counter-axis spacing, alignment, sizing mode).
- FR-1.5: Extract component instance references, linking to component definitions.
- FR-1.6: Classify screens by device class based on dimensions (iPhone 428×926, iPad 11" 834×1194, iPad 12.9" 1536×1152).
- FR-1.7: Support incremental re-extraction (only screens modified since `extracted_at`).
- FR-1.8: Extract from a single page within a multi-page file.
- FR-1.9: Extraction is resumable. If interrupted mid-run, re-running resumes from the last incomplete screen without re-extracting completed screens. Tracked via `extraction_runs` and `screen_extraction_status` tables.

### FR-2: Token Management
- FR-2.1: Three-tier lifecycle: `extracted` → `curated` → `aliased`.
- FR-2.2: Alias resolution via self-referential FK with denormalized `resolved_value`. A `v_resolved_tokens` view follows the alias chain and returns the final resolved value for any token.
- FR-2.3: Multi-mode support (Light/Dark, Compact/Comfortable) per token collection. Every token in a collection must have a value for every mode in that collection (enforced at application level, validated before export).
- FR-2.4: DTCG v2025.10 compatible type system (color, dimension, fontFamily, fontWeight, number, shadow, border, transition, gradient).
- FR-2.5: Token names follow DTCG dot-path convention (e.g., `color.surface.primary`).
- FR-2.6: Sync status tracking: `pending` (created in DB, not yet exported), `figma_only` (exists in Figma but no code mapping), `code_only` (exists in code but not Figma), `synced` (DB + Figma + code aligned), `drifted` (values diverge between systems).
- FR-2.7: Mode-aware clustering. Census queries can filter by mode. Clustering can propose different tokens per mode or shared tokens with mode-specific values.
- FR-2.8: Mode creation with value seeding. When adding a new mode, existing token values from the default mode are copied as starting points. Optional heuristic transforms (lightness inversion for dark mode, scale factor for compact mode) can be applied.

### FR-3: Composition Storage
- FR-3.1: Full node tree per screen with parent-child relationships.
- FR-3.2: Semantic flagging to distinguish meaningful containers from Figma structural noise.
- FR-3.3: Token bindings per node per property, with dot-path property addressing (`fill.0.color`, `effect.0.color`, `effect.0.radius`, `padding.top`, `fontSize`, etc.).
- FR-3.4: Binding lifecycle: `unbound` → `proposed` → `bound` → `overridden`.
- FR-3.5: Component instance references linking to component definitions with variant properties.

### FR-3.6: Interaction States
- FR-3.6.1: Variant axes marked `is_interaction = 1` represent interaction states (hover, focus, disabled, pressed, selected, loading).
- FR-3.6.2: Interaction state variants are queryable across all components via `v_interaction_states` view — "show me every component that has a hover state."
- FR-3.6.3: Each variant dimension value links a specific variant to its position on each axis, enabling queries like "all large+hover variants."
- FR-3.6.4: Default values are recorded per axis — the baseline variant an agent should use when no state is specified.

### FR-3.7: Component Model
- FR-3.7.1: Component slots (`component_slots`) define named insertion points with type constraints (icon, text, component, image, any), required/optional flag, default content, and sort order.
- FR-3.7.2: Accessibility contracts (`component_a11y`) capture per-component: ARIA role, required label flag, focus order, minimum touch target (44px iOS / 48px Android), keyboard shortcut, and freeform a11y notes.
- FR-3.7.3: Responsive behaviors (`component_responsive`) capture per-breakpoint layout changes, visibility rules, and slot-level overrides (e.g., trailing action hidden on mobile).
- FR-3.7.4: Component catalog view (`v_component_catalog`) provides a single-query overview: variant count, slot count, a11y role, touch target, axes — everything an agent needs to decide which component to use.
- FR-3.7.5: All component model data is extractable where Figma metadata allows (variant properties, instance dimensions) and manually augmentable during curation (slots, a11y, responsive).

### FR-4: Export
- FR-4.1: Generate `figma_setup_design_tokens` payloads (≤100 tokens/call) with all modes included.
- FR-4.2: Generate rebind plugin scripts executable in Figma console, covering all bindable property types: fills, strokes, effects (shadows), corner radius, font size, font family, font weight, line height, letter spacing, padding (4-sided), item spacing, counter-axis spacing, opacity.
- FR-4.3: Generate CSS custom property declarations from token values, with mode-specific values in media queries or data-attribute selectors.
- FR-4.4: Generate Tailwind theme config from token values.
- FR-4.5: Write back Figma variable IDs to DB after creation.
- FR-4.6: Generate W3C DTCG v2025.10 `tokens.json` file with full type information, aliases, and multi-mode values.
- FR-4.7: Rebind scripts must handle all property types in the binding table. Any property path in `node_token_bindings` that has a corresponding Figma binding API must be covered.

### FR-5: Query Interface
- FR-5.1: Census views for colors, typography, spacing, radius, and effects — ranked by usage count.
- FR-5.2: Unbound binding worklist view.
- FR-5.3: Token coverage view (bindings per token, nodes per token, screens per token).
- FR-5.4: Screen composition summary (component count, instance count, auto-layout count).
- FR-5.5: Selective loading — agent can request just color tokens, one component, or drifted items.
- FR-5.6: Interaction state view (`v_interaction_states`) — all interaction axes across all components with variant counts and default values.
- FR-5.7: Component catalog view (`v_component_catalog`) — full component overview with variant count, slot count, a11y role, touch target, and axes. Single-query agent consumption.
- FR-5.8: Export readiness view (`v_export_readiness`) — aggregated pre-export validation results grouped by check name and severity. Agents and users can gate export on zero errors.
- FR-5.9: Curation progress view (`v_curation_progress`) — aggregate breakdown of unbound/proposed/bound/overridden bindings as counts and percentages for tracking overall workflow completion.
- FR-5.10: Drift report view (`v_drift_report`) — per-token sync status between DB and Figma, supporting UC-6.

### FR-5.11: Route and Code Mappings
- FR-5.11.1: Route mappings (`route_mappings`) link app routes to Figma screens per platform (web, iOS, Android). Populated manually or via codebase scan (UC-8). Enables "build me the /settings page" → agent resolves the correct screen.
- FR-5.11.2: Code mappings (`code_mappings`) link tokens to their representation in each target system (CSS custom properties, Tailwind classes, Swift constants). One row per token per target per identifier.

### FR-5.12: Composition Patterns (future)
- FR-5.12.1: Patterns (`patterns`) are reusable structural recipes (nav sidebar, pricing card, settings form) derived from screen analysis. Populated during curation, not extraction. Used by Conjure agents (UC-7) to compose screens from known templates.

### FR-6: Companion Skill
- FR-6.1: A companion Claude skill (`declarative-design`) wraps the DB as an MCP-accessible context source. The skill reads from the SQLite DB and provides structured responses to agent queries.
- FR-6.2: The skill exposes commands: `/dd-tokens [type]` (list tokens by type), `/dd-screen <name>` (screen composition), `/dd-component <name>` (component catalog entry with slots, a11y, variants), `/dd-status` (extraction progress + curation progress + export readiness).
- FR-6.3: The skill pre-loads relevant context before any design or code generation task — the agent doesn't need to know the DB schema.
- FR-6.4: The skill supports selective loading — it retrieves only the tokens, components, or screens relevant to the current task, not the entire DB.

## Non-Functional Requirements

- NFR-1: **Portability** — SQLite single-file DB. No server, no Docker, no cloud dependency. Copy the .db file and you have the entire design system.
- NFR-2: **Performance** — Full extraction of 230 screens in <20 minutes (bounded by Figma MCP round-trip, not DB writes).
- NFR-3: **Cost** — Extraction uses metered Official MCP (one-time cost). All subsequent work (clustering, curation, code export) is zero-cost against local DB. Figma export uses free Console MCP or zero-cost plugin scripts.
- NFR-4: **Idempotency** — Re-running extraction on the same file produces identical DB state (UPSERT semantics on all tables).
- NFR-5: **Freshness tracking** — Every row carries `extracted_at` timestamp. Stale data is identifiable.
- NFR-6: **Multi-file** — Schema supports multiple source files from day one via `files` table.
- NFR-7: **Observability** — Extraction pipeline reports progress per-screen (N/total, elapsed, ETA). Clustering reports summary stats. All phases log to stdout with structured output (parseable for future UI integration).
- NFR-8: **Non-destructive re-extraction** — Re-extracting a file preserves all curation work. Curated tokens, bound bindings, and manually set `is_semantic` flags survive re-extraction. New/changed nodes are added/updated; deleted nodes are flagged, not removed. Bindings for unchanged nodes retain their `binding_status`.
- NFR-9: **Backup before destructive ops** — Before any bulk curation operation (merge, reject, re-extract), the system creates a timestamped DB snapshot (SQLite `VACUUM INTO` or file copy). Snapshots are rotatable (keep last 5).
- NFR-10: **Parallel agent support** — Multiple agents can operate on the DB concurrently via advisory locks (`extraction_locks` table). Locks are resource-level (file, collection, screen), auto-expire after 10 minutes, and use cooperative checking (agents check before writing, back off on conflict). No external lock manager required — SQLite WAL mode + advisory locks table.

## Constraints

- C-1: Official Figma MCP `use_figma` code field limit: 50,000 characters per call.
- C-2: Official Figma MCP `use_figma` return payload: uncapped but ~37K observed per 200-node screen.
- C-3: Console MCP `figma_setup_design_tokens`: 100 tokens per call.
- C-4: Console MCP `figma_execute` requires async Plugin API — cannot do sync traversal.
- C-5: Instance nodes are opaque in tree reads — internals not expanded without explicit traversal.
- C-6: Figma file has 0 published library assets — `figma_get_design_system_kit` returns nothing.
- C-7: W3C DTCG v2025.10 token format as the canonical type system.
- C-8: DB filename convention: `*.declarative.db` (e.g., `dank.declarative.db`). The companion skill auto-discovers files matching this pattern.

## Success Criteria

1. **Extraction completeness:** DB contains ≥95% of visual property values present in the Figma file. Verified by spot-checking 10 random screens against Figma inspect panel.
2. **Token coverage:** After curation, ≥90% of `node_token_bindings` have `binding_status` of `proposed` or `bound`.
3. **Round-trip fidelity:** After rebinding, a visual diff of the Figma file shows zero regressions (same pixels, different implementation).
4. **Agent consumability:** A coding agent with no prior context can query the DB and produce a correct screen implementation using real tokens and components. Tested by giving Claude the DB + a screen name and evaluating output.
5. **Time to value:** From raw Figma file to curated token system in <2 hours (extraction + clustering + curation review).
