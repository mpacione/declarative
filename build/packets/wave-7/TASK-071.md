---
taskId: TASK-071
title: "Create companion Claude skill"
wave: wave-7
testFirst: false
testLevel: unit
dependencies: [TASK-002]
produces:
  - declarative-design/SKILL.md
verify:
  - type: file_exists
    command: 'python -c "import os; assert os.path.exists(\"declarative-design/SKILL.md\"), \"SKILL.md not found\""'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "content = open(\"declarative-design/SKILL.md\").read(); assert len(content) > 2000, f\"Too short: {len(content)}\"; assert \"v_resolved_tokens\" in content; assert \"v_component_catalog\" in content; assert \"v_curation_progress\" in content; assert \"declarative.db\" in content; print(\"SKILL.md validates OK\")"'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-071: Create companion Claude skill

## Spec Context

### From User Requirements Spec -- FR-6: Companion Skill

> FR-6.1: A companion Claude skill (`declarative-design`) wraps the DB as an MCP-accessible context source. The skill reads from the SQLite DB and provides structured responses to agent queries.
> FR-6.2: The skill exposes commands: `/dd-tokens [type]` (list tokens by type), `/dd-screen <name>` (screen composition), `/dd-component <name>` (component catalog entry with slots, a11y, variants), `/dd-status` (extraction progress + curation progress + export readiness).
> FR-6.3: The skill pre-loads relevant context before any design or code generation task -- the agent doesn't need to know the DB schema.
> FR-6.4: The skill supports selective loading -- it retrieves only the tokens, components, or screens relevant to the current task, not the entire DB.

### From Technical Design Spec -- Companion Skill

> A companion skill (`declarative-design.md`) teaches Claude how to work with the Declarative Design DB. It's installed in `.claude/skills/` and loaded automatically when the agent encounters a `.declarative.db` file or is asked to compose/build using a design system.
>
> **Skill responsibilities:**
> 1. **DB discovery.** On load, find the `.declarative.db` file, run `v_curation_progress` and `v_screen_summary` to understand the system's state, report health.
> 2. **Token resolution.** When composing code or Figma screens, query `v_resolved_tokens` for the correct token value per mode. Never hardcode values that have tokens.
> 3. **Component instantiation.** Query `v_component_catalog` to understand available components, their slots, interaction states, and a11y contracts. Use `composition_hint` for structural guidance.
> 4. **Screen composition.** When asked to "build the settings page," query the DB for the screen's composition tree (query #2 above), then recreate it using real components and real tokens.
> 5. **Curation assistance.** Walk the user through token proposals using `v_token_coverage`, `v_unbound`, and `v_curation_progress`. Offer rename/merge/split suggestions.
> 6. **Export orchestration.** Run validation (Phase 6.5), generate `figma_setup_design_tokens` payloads, execute rebinding scripts, verify via `figma_audit_design_system`.
> 7. **Disconnected mode.** If Figma is not running (Console MCP unavailable), the skill still works for code generation and DB queries -- just not Figma export.
>
> **Skill structure:**
> - System context: DB location, schema version, table overview, view catalog
> - Query patterns: all 10 cookbook queries above
> - MCP tool mapping: which Console MCP / Official MCP tool to use for each operation
> - Constraints: token naming conventions, binding property path format, mode completeness rules
> - Workflows: extraction, clustering, curation, export, drift detection

### From Technical Design Spec -- Agent Cookbook Queries

> **1. Get all color tokens for code generation:**
> ```sql
> SELECT t.name, vrt.resolved_value, vrt.mode_name
> FROM v_resolved_tokens vrt
> JOIN tokens t ON vrt.id = t.id
> WHERE t.type = 'color' AND t.tier IN ('curated', 'aliased')
> ORDER BY t.name, vrt.mode_name;
> ```
>
> **2. Get a screen's full composition tree:**
> ```sql
> SELECT * FROM v_screen_summary WHERE name LIKE '%Settings%';
>
> SELECT n.path, n.name, n.node_type, n.is_semantic,
>        n.layout_mode, n.width, n.height,
>        ntb.property, ntb.resolved_value, t.name AS token_name
> FROM nodes n
> LEFT JOIN node_token_bindings ntb ON ntb.node_id = n.id AND ntb.binding_status = 'bound'
> LEFT JOIN tokens t ON ntb.token_id = t.id
> WHERE n.screen_id = ?
> ORDER BY n.path;
> ```
>
> **3. Get all components with their interaction states:**
> ```sql
> SELECT c.name, c.category, c.composition_hint,
>        va.axis_name, va.axis_values, va.default_value,
>        cs.name AS slot_name, cs.slot_type, cs.is_required,
>        ca.role, ca.min_touch_target
> FROM components c
> LEFT JOIN variant_axes va ON va.component_id = c.id
> LEFT JOIN component_slots cs ON cs.component_id = c.id
> LEFT JOIN component_a11y ca ON ca.component_id = c.id
> WHERE c.file_id = ?
> ORDER BY c.category, c.name, va.axis_name;
> ```
>
> **4. Find all hover states across all components:**
> ```sql
> SELECT c.name AS component_name, cv.name AS variant_name, cv.properties
> FROM variant_dimension_values vdv
> JOIN variant_axes va ON vdv.axis_id = va.id
> JOIN component_variants cv ON vdv.variant_id = cv.id
> JOIN components c ON cv.component_id = c.id
> WHERE va.is_interaction = 1 AND vdv.value = 'hover';
> ```
>
> **5. Get all tokens with usage counts:**
> ```sql
> SELECT * FROM v_token_coverage WHERE binding_count > 0;
> ```
>
> **6. Pipeline status dashboard:**
> ```sql
> SELECT * FROM v_curation_progress;
> ```
>
> **7. All descendants of a container node:**
> ```sql
> SELECT * FROM nodes WHERE path LIKE '0.3.%' AND screen_id = ?
> ORDER BY path;
> ```
>
> **8. Find design inconsistencies:**
> ```sql
> SELECT resolved_value, property, COUNT(*) as usage
> FROM node_token_bindings
> WHERE binding_status = 'unbound'
> GROUP BY resolved_value, property
> HAVING COUNT(*) = 1
> ORDER BY property;
> ```
>
> **9. Drift check:**
> ```sql
> SELECT * FROM v_drift_report;
> ```
>
> **10. Export readiness check:**
> ```sql
> SELECT * FROM v_export_readiness;
> ```

### From User Requirements Spec -- Constraints

> C-8: DB filename convention: `*.declarative.db` (e.g., `dank.declarative.db`). The companion skill auto-discovers files matching this pattern.

### From Architecture.md -- What the DB Stores

> **System** -- tokens, component definitions, patterns. The vocabulary.
> **Compositions** -- screens/views, their component trees, layout rules, token bindings. The sentences.
> **Mappings** -- the rosetta stone between tools.

### From schema.sql -- View catalog (all 15 views)

> Views:
> - `v_color_census` -- unique colors with usage counts
> - `v_type_census` -- unique typography combos
> - `v_spacing_census` -- unique spacing values
> - `v_radius_census` -- unique radius values
> - `v_effect_census` -- unique effect values
> - `v_unbound` -- bindings with no token assigned
> - `v_token_coverage` -- tokens with binding/node/screen counts
> - `v_screen_summary` -- screen metadata with component/instance/autolayout counts
> - `v_resolved_tokens` -- follows alias chain for final value
> - `v_color_census_by_mode` -- post-clustering mode-aware color analysis
> - `v_drift_report` -- non-synced token status
> - `v_curation_progress` -- binding status breakdown
> - `v_interaction_states` -- components with interaction axes
> - `v_component_catalog` -- full component overview
> - `v_export_readiness` -- validation results summary

### From dd/config.py (produced by TASK-001)

> - `DB_SUFFIX = ".declarative.db"`

## Task

Create `declarative-design/SKILL.md` -- the companion Claude skill file that teaches Claude how to work with the Declarative Design database. This is a markdown file installed in `.claude/skills/` that provides system context, query patterns, workflows, and constraints.

The skill file must be comprehensive enough that an agent with ZERO prior context about this project can:
- Discover and connect to the DB
- Understand the token system and component model
- Run all pipeline queries
- Assist with curation
- Orchestrate exports
- Detect drift

### Structure

1. **Header section**: Skill name, version, description, trigger conditions (when to activate).

2. **DB Discovery**: How to find `.declarative.db` files, how to open them with `sqlite3`, initial health check queries (`v_curation_progress`, `v_screen_summary`).

3. **Schema Overview**: Brief description of the 4 table groups (System, Compositions, Mappings, Operations) with the key tables in each. NOT the full CREATE TABLE statements -- just table names, purpose, and key columns.

4. **View Catalog**: All 15 views with their purpose and when to use each. Group by workflow phase.

5. **Query Patterns**: All 10 Agent Cookbook queries from the TDS, labeled by use case. Add practical context: "Use this when the user asks to build a screen" etc.

6. **Token Resolution**: How to resolve tokens including aliases. Explain the `v_resolved_tokens` view. Explain multi-mode values. Rule: "Never hardcode a value that has a token."

7. **Component Catalog**: How to query components, their variants, slots, a11y, and responsive behaviors. Use `v_component_catalog` for overview, join to detail tables for specifics.

8. **Screen Composition**: How to reconstruct a screen's full tree with token bindings. Explain the materialized path system for subtree queries.

9. **Curation Assistance Workflow**: Step-by-step guide for walking users through token curation. Queries for reviewing proposals, low-confidence bindings, orphan values. Available operations (accept, rename, merge, split, reject, alias) with Python function signatures.

10. **Export Orchestration**: Step-by-step guide for each export path:
    - Pre-export validation (check `v_export_readiness`)
    - Figma variables (generate payloads, call `figma_setup_design_tokens`, writeback IDs)
    - Figma rebinding (generate scripts, execute via `figma_execute`)
    - CSS custom properties
    - Tailwind theme config
    - W3C DTCG tokens.json

11. **Drift Detection**: How to run drift detection, interpret the report, and resolve issues. Explain `v_drift_report`.

12. **MCP Tool Mapping**: Which MCP tools to use for each operation:
    - Official MCP: `use_figma` for extraction
    - Console MCP: `figma_setup_design_tokens` for variable creation, `figma_execute` for rebinding, `figma_audit_design_system` for verification

13. **Disconnected Mode**: What works without Figma running (DB queries, code export, curation) vs what requires MCP (extraction, Figma export, drift detection).

14. **Constraints**: Token naming conventions (DTCG dot-path), binding property path format, mode completeness rules, alias depth limit, batch size limits.

15. **Python Module Map**: Brief listing of all `dd/` modules and their public functions, organized by pipeline phase. This helps the agent know which functions to call.

### Writing Style

- Use clear, actionable language aimed at an AI agent, not a human developer.
- Include actual SQL queries the agent can copy-paste.
- Include actual Python function calls with import paths.
- Use markdown headers, code blocks, and lists for structure.
- Keep each section self-contained -- the agent should be able to jump to any section.

## Acceptance Criteria

- [ ] File `declarative-design/SKILL.md` exists
- [ ] File is at least 3000 characters long (comprehensive enough to be useful)
- [ ] File contains all 10 Agent Cookbook SQL queries from the TDS
- [ ] File contains references to all 15 views by name
- [ ] File contains the `v_resolved_tokens` view query pattern for token resolution
- [ ] File contains the `v_component_catalog` view query pattern
- [ ] File contains the `v_curation_progress` view query pattern
- [ ] File contains `.declarative.db` discovery instructions
- [ ] File contains MCP tool mapping (which tool for which operation)
- [ ] File contains disconnected mode guidance
- [ ] File contains curation workflow steps (accept, rename, merge, split, reject, alias)
- [ ] File contains export orchestration steps for all 4 formats
- [ ] File contains drift detection workflow
- [ ] File contains Python module map with import paths
- [ ] File contains constraint listings (naming conventions, batch sizes, alias depth)
- [ ] File is valid markdown (no broken formatting)

## Notes

- This is a documentation task, not a code task. The output is a markdown file, not Python code.
- The skill file is meant to be installed in `.claude/skills/` directory. The agent doesn't need to create that directory -- just the skill file itself.
- The skill should reference real function signatures from the `dd/` modules (e.g., `from dd.curate import accept_token, merge_tokens`). These functions already exist from prior waves.
- The file should be written in present tense, as instructions to an agent that will use it.
- Include a version number matching the project version (0.1.0).
- The directory `declarative-design/` should be created if it doesn't exist.