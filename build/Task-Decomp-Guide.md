---
doc: Task-Decomp-Guide
project: Declarative Design
status: draft
version: 0.1.0
created: 2026-03-25
updated: 2026-03-25
---

# Declarative Design -- Task Decomposition Guide

How to break the Declarative Design spec into granular, self-contained coding tasks suitable for agentic execution via Claude Code. This is a build plan for implementing the extraction-to-export pipeline.

For the spec suite this guide decomposes:
- `User Requirements Spec.md` (URS)
- `Technical Design Spec.md` (TDS)
- `Architecture.md`
- `schema.sql` (v0.2)
- `Probe Results.md`
- `Tooling Comparison.md`

---

## 1. Decomposition Principles

- **P1 (Verifiable artifact):** Every task produces files that can be tested via Python import, SQL execution, or command exit code.
- **P2 (Explicit deps):** The `Deps` column in each wave table declares task ID dependencies.
- **P3 (One concern):** Tasks are split along file/module boundaries -- schema != extraction != clustering != export.
- **P4 (Self-contained):** Each task packet inlines all spec content the agent needs. No external file reads.
- **P5 (Idempotent):** DB operations use UPSERT or IF NOT EXISTS guards. Re-running is safe.
- **P6 (Context headroom):** Most tasks fit in standard context. Extraction scripts that inline schema + Figma API patterns may need `contextProfile: full`.

---

## 2. Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Language | Python 3.11+ | Rapid iteration, strong SQLite/JSON support, OKLCH libs available |
| Database | SQLite (WAL mode) | Portable, zero-config, matches NFR-1 |
| MCP interaction | Agent-driven (not scripted) | MCP calls happen in the agent's context, not via subprocess |
| Color science | `coloraide` or manual OKLCH | Perceptual clustering for ΔE calculations |
| Testing | pytest | Standard, fast, good SQLite fixture support |
| Packaging | Single directory, no pip package | Keep it simple -- `dd/` module with `__init__.py` |

---

## 3. Naming Conventions

**Waves:** Sequential integers: `wave-0`, `wave-1`, ... `wave-7`. No decimals, no gaps.

**Task IDs:** Format is `TASK-NNN` where `NNN` is exactly three decimal digits. Must match `^TASK-\d{3}$`.

**ID block allocation:**

| Wave | ID Range | Description |
|------|----------|-------------|
| wave-0 | TASK-001 -- TASK-009 | Project scaffold + DB init + test infra |
| wave-1 | TASK-010 -- TASK-019 | Extraction pipeline (inventory + screens) |
| wave-2 | TASK-020 -- TASK-029 | Component extraction + value normalization |
| wave-3 | TASK-030 -- TASK-039 | Census views + clustering |
| wave-4 | TASK-040 -- TASK-049 | Curation workflow + validation |
| wave-5 | TASK-050 -- TASK-059 | Figma export (variables + rebinding) |
| wave-6 | TASK-060 -- TASK-069 | Code export (CSS, Tailwind, DTCG) |
| wave-7 | TASK-070 -- TASK-079 | Companion skill + drift detection |

**Test task naming convention:** Each wave includes up to 3 test tasks at the end of its block:
- `TASK-XX5` or `TASK-XX6`: unit tests (mock-based, isolated)
- `TASK-XX6` or `TASK-XX7`: integration tests (cross-module, fixture DB, real pipeline seams)
- `TASK-XX7` or `TASK-XX8`: e2e tests (full pipeline through current wave, from wave 3 onward)

**ASCII-only content.** No Unicode symbols in doc content, frontmatter, or filenames.

---

## 4. Verify Defaults

| Waves | testFirst | testLevel | Rationale |
|-------|-----------|-----------|-----------|
| 0 (Scaffold) | `false` | unit | Config, directory structure, DB init -- verify via file_exists + SQL execution. Test infra task (TASK-007) creates shared fixtures. |
| 1 (Extraction) | `false` | unit + integration | MCP-dependent code -- unit tests with mocks, integration tests chain the full extraction pipeline against fixture DB |
| 2 (Components) | `false` | unit + integration | Component extraction consuming real extraction output; integration tests verify FK integrity across extraction + components |
| 3 (Clustering) | `true` | unit + integration + e2e | Pure Python with testable inputs/outputs. First e2e test: extraction -> clustering end-to-end |
| 4 (Curation) | `true` | unit + integration + e2e | DB operations with clear pre/post conditions. E2e covers extraction -> validation gate |
| 5 (Figma export) | `true` | unit + integration + e2e | Output format compliance. E2e covers full pipeline -> Figma payload generation |
| 6 (Code export) | `true` | unit + integration + e2e | Output format compliance. E2e covers full pipeline -> all 4 export formats with cross-format consistency checks |
| 7 (Skill + drift) | `false` | unit + e2e | Markdown skill + drift detection. Final e2e smoke test covers entire pipeline including mode creation and drift |

---

## 5. Task Ordering

Build from the bottom up: schema -> extraction -> normalization -> clustering -> curation -> export -> skill.

Tasks are grouped into waves. Within a wave, tasks can be parallelized unless dependencies say otherwise. Waves execute sequentially.

### Wave 0: Project Scaffold + DB Initialization

| Task | Description | Produces | Deps |
|------|-------------|----------|------|
| TASK-001 | Create project directory structure and Python module | `dd/__init__.py`, `dd/db.py`, `dd/config.py`, `pyproject.toml`, `requirements.txt` | -- |
| TASK-002 | Initialize SQLite DB from schema.sql | `dd/db.py` (get_connection, init_db, backup_db functions) | TASK-001 |
| TASK-003 | Create shared constants and type definitions | `dd/types.py` (DeviceClass enum, BindingStatus enum, Tier enum, SyncStatus enum, property path constants) | TASK-001 |
| TASK-004 | Create color normalization utilities | `dd/color.py` (rgba_to_hex, hex_to_oklch, oklch_delta_e, oklch_invert_lightness) | TASK-001 |
| TASK-005 | Create value normalization module | `dd/normalize.py` (normalize_fill, normalize_stroke, normalize_effect, normalize_typography, normalize_spacing, normalize_radius) | TASK-003, TASK-004 |
| TASK-006 | Write unit tests for color + normalization utilities | `tests/test_color.py`, `tests/test_normalize.py` | TASK-004, TASK-005 |
| TASK-007 | Create shared test infrastructure (conftest, fixture DB builder, mock factories) | `tests/conftest.py`, `tests/fixtures.py` | TASK-002, TASK-003 |

**Wave 0 verify override:** `verify: [{ type: custom, command: 'python -c "import dd"', passWhen: 'exits 0' }]`

**Test infrastructure (TASK-007):** This task creates the foundation all subsequent test tasks depend on:
- `tests/conftest.py`: pytest fixtures for in-memory SQLite DB, schema initialization, cleanup
- `tests/fixtures.py`: factory functions to seed a DB at any pipeline stage (post-extraction, post-clustering, post-curation). Each factory returns a DB connection with deterministic test data. Also includes mock Figma response builders matching use_figma return shapes.

### Wave 1: Extraction Pipeline -- Inventory + Screen Extraction

| Task | Description | Produces | Deps |
|------|-------------|----------|------|
| TASK-010 | Implement file inventory phase (Phase 1 from TDS) | `dd/extract_inventory.py` (populate files, screens, extraction_runs tables; device classification; component sheet detection) | TASK-002, TASK-003 |
| TASK-011 | Implement screen extraction script generator (Phase 2 from TDS) | `dd/extract_screens.py` (generate use_figma JS code for screen traversal; parse response into nodes table rows) | TASK-002, TASK-003 |
| TASK-012 | Implement binding creation from extracted nodes (Phase 3 from TDS) | `dd/extract_bindings.py` (iterate node properties, create node_token_bindings rows with raw_value/resolved_value; effect decomposition into individual binding rows) | TASK-005, TASK-011 |
| TASK-013 | Implement materialized path computation | `dd/paths.py` (compute_paths for a screen's node tree; is_semantic heuristic; update nodes.path and nodes.is_semantic) | TASK-011 |
| TASK-014 | Implement extraction orchestrator with resume support | `dd/extract.py` (main extraction loop: inventory -> per-screen extraction -> normalization -> binding creation -> path computation; resume via screen_extraction_status; progress reporting) | TASK-010, TASK-011, TASK-012, TASK-013 |
| TASK-015 | Write unit tests for extraction with mock Figma data | `tests/test_extraction.py` (mock use_figma responses; verify node counts, binding counts, path computation, device classification, resume behavior) | TASK-014 |
| TASK-016 | Write integration tests for extraction pipeline | `tests/test_extraction_integration.py` (run full inventory -> screen -> binding -> path -> orchestrator chain against fixture DB with mock Figma responses; verify DB state at each stage, foreign key integrity, extraction_runs tracking, resume-after-failure behavior) | TASK-007, TASK-014 |

**Wave 1 verify:** `verify: [{ type: test, command: 'pytest tests/test_extraction.py tests/test_extraction_integration.py -v', passWhen: 'all tests pass' }]`

### Wave 2: Component Extraction + Advanced Normalization

| Task | Description | Produces | Deps |
|------|-------------|----------|------|
| TASK-020 | Implement component extraction (Phase 4 from TDS) | `dd/extract_components.py` (extract component/component_set nodes; populate components, component_variants, variant_axes tables; flag is_interaction axes) | TASK-002, TASK-003 |
| TASK-021 | Implement variant dimension value population | `dd/extract_components.py` (continued -- populate variant_dimension_values linking each variant to its axis positions) | TASK-020 |
| TASK-022 | Implement component slot inference | `dd/extract_components.py` (continued -- analyze component children to populate component_slots; heuristic slot detection) | TASK-020 |
| TASK-023 | Implement component a11y inference | `dd/extract_components.py` (continued -- populate component_a11y; role inference from category; min_touch_target defaults) | TASK-020 |
| TASK-024 | Integrate component extraction into main pipeline | `dd/extract.py` (update orchestrator to call component extraction after screen extraction; handle component_sheet frames) | TASK-014, TASK-020 |
| TASK-025 | Write unit tests for component extraction | `tests/test_components.py` (mock component data; verify variant axes, interaction flags, slot inference, a11y defaults) | TASK-020, TASK-021, TASK-022, TASK-023 |
| TASK-026 | Write integration tests for component + extraction pipeline | `tests/test_components_integration.py` (seed fixture DB with extraction output from TASK-007 fixtures; run component extraction; verify components reference valid nodes, variant_dimension_values FK integrity, component_slots populated from real node children, a11y defaults applied; verify orchestrator chains extraction + components end-to-end) | TASK-007, TASK-024 |

### Wave 3: Census + Clustering

| Task | Description | Produces | Deps |
|------|-------------|----------|------|
| TASK-030 | Implement color clustering (Phase 5 from TDS) | `dd/cluster_colors.py` (query v_color_census; OKLCH conversion; ΔE<2.0 grouping; semantic name proposal based on usage context -- surface/text/accent/border heuristics; write tokens + token_values + update bindings) | TASK-004, TASK-002 |
| TASK-031 | Implement typography clustering | `dd/cluster_typography.py` (query v_type_census; group by font size into scale tiers; propose type.display/body/label names; write tokens + bindings) | TASK-002 |
| TASK-032 | Implement spacing clustering | `dd/cluster_spacing.py` (query v_spacing_census; detect scale pattern -- 4px base; propose space.1 through space.16 names; write tokens + bindings) | TASK-002 |
| TASK-033 | Implement radius + effect clustering | `dd/cluster_misc.py` (query v_radius_census + v_effect_census; propose radius.sm/md/lg and shadow.sm/md/lg names; composite shadow matching; write tokens + bindings) | TASK-002, TASK-004 |
| TASK-034 | Implement clustering orchestrator | `dd/cluster.py` (run all clustering in sequence; create default token_collection + token_mode; summary report: N tokens proposed, M bindings assigned, L flagged) | TASK-030, TASK-031, TASK-032, TASK-033 |
| TASK-035 | Write unit tests for all clustering modules | `tests/test_clustering.py` (fixture DB with known census data; verify token proposals, confidence scores, binding updates, name uniqueness, no orphan tokens) | TASK-034 |
| TASK-036 | Write integration tests for extraction-to-clustering pipeline | `tests/test_clustering_integration.py` (seed post-extraction fixture DB; run clustering orchestrator; verify tokens reference valid bindings, census views produce expected aggregations, clustering consumes real extraction output correctly) | TASK-007, TASK-034 |
| TASK-037 | Write mini-e2e test: extraction through clustering | `tests/test_e2e_extract_cluster.py` (fixture DB -> run full extraction with mock Figma data -> run clustering -> verify: token_values populated, bindings updated with token_id, census views accurate, no orphan bindings; this is the first end-to-end test covering waves 0-3) | TASK-007, TASK-034, TASK-016 |

### Wave 4: Curation Workflow + Pre-Export Validation

| Task | Description | Produces | Deps |
|------|-------------|----------|------|
| TASK-040 | Implement curation operations (accept, rename, merge, split, reject, alias) | `dd/curate.py` (each operation as a function; tier promotion; binding reassignment on merge; alias depth enforcement; DB backup before bulk ops per NFR-9) | TASK-002, TASK-003 |
| TASK-041 | Implement pre-export validation (Phase 6.5 from TDS) | `dd/validate.py` (mode_completeness, name_dtcg_compliant, orphan_tokens, binding_coverage, alias_targets_curated, name_uniqueness, value_format checks; write to export_validations table; return pass/fail) | TASK-002, TASK-003 |
| TASK-042 | Implement curation progress reporting | `dd/status.py` (query v_curation_progress, v_token_coverage, v_unbound, v_export_readiness; format as structured report) | TASK-002 |
| TASK-043 | Write unit tests for curation operations + validation | `tests/test_curation.py`, `tests/test_validation.py` (verify merge reassigns bindings, reject reverts to unbound, alias depth blocked, validation catches all error types) | TASK-040, TASK-041 |
| TASK-044 | Write integration tests for clustering-to-curation pipeline | `tests/test_curation_integration.py` (seed post-clustering fixture DB; run curation ops (accept, merge, split); run validation; verify: merged tokens reassign all bindings, rejected tokens revert bindings to unbound, alias chains resolve, validation gate catches incomplete curation, backup created before bulk ops) | TASK-007, TASK-041 |
| TASK-045 | Write e2e test: extraction through validation gate | `tests/test_e2e_extract_validate.py` (fixture DB -> extraction with mocks -> clustering -> curation (accept all) -> validation -> verify: all 7 validation checks pass, curation_progress view shows 100%, export_readiness view returns ready; this is the pre-export gate e2e) | TASK-007, TASK-041, TASK-037 |

### Wave 5: Figma Export (Variables + Rebinding)

| Task | Description | Produces | Deps |
|------|-------------|----------|------|
| TASK-050 | Implement Figma variable payload generator (Phase 7 from TDS) | `dd/export_figma_vars.py` (query curated tokens; group by collection; batch into <=100 token payloads; DTCG dot-path to Figma slash-path conversion; multi-mode values; output JSON payloads for figma_setup_design_tokens) | TASK-002, TASK-041 |
| TASK-051 | Implement variable ID writeback | `dd/export_figma_vars.py` (continued -- after figma_setup_design_tokens call, query figma_get_variables to get IDs; update tokens.figma_variable_id; update sync_status to synced) | TASK-050 |
| TASK-052 | Implement rebind script generator (Phase 8 from TDS) | `dd/export_rebind.py` (query bound bindings with figma_variable_id; generate self-contained async plugin scripts; batch ~500 bindings/script; cover all property types from TDS binding table: fills, strokes, effects, dimensions, typography, padding, spacing, opacity) | TASK-002 |
| TASK-053 | Write unit tests for export payload generation + rebind scripts | `tests/test_export_figma.py` (verify payload format, batch sizing, name conversion, script syntax, property type coverage) | TASK-050, TASK-052 |
| TASK-054 | Write integration tests for curation-to-Figma-export pipeline | `tests/test_export_figma_integration.py` (seed post-curation fixture DB; run Figma variable payload generator; verify: payloads reference valid curated tokens, batch sizing <= 100, DTCG dot-path to Figma slash-path conversion correct, multi-mode values present, rebind scripts syntactically valid JS) | TASK-007, TASK-052 |
| TASK-055 | Write e2e test: full pipeline through Figma export | `tests/test_e2e_figma_export.py` (fixture DB -> extraction -> clustering -> curation -> validation -> Figma payload gen -> verify: payloads are valid JSON, all curated tokens represented, batch count matches ceil(tokens/100), rebind scripts cover all bound property types) | TASK-007, TASK-052, TASK-045 |

### Wave 6: Code Export (CSS, Tailwind, DTCG)

| Task | Description | Produces | Deps |
|------|-------------|----------|------|
| TASK-060 | Implement CSS custom property export | `dd/export_css.py` (generate :root block with --token-name: value; mode-specific values in [data-theme] selectors or @media queries; write to code_mappings table) | TASK-002 |
| TASK-061 | Implement Tailwind theme config export | `dd/export_tailwind.py` (generate tailwind.config.js theme.extend block; map tokens to Tailwind naming conventions; write to code_mappings table) | TASK-002 |
| TASK-062 | Implement W3C DTCG tokens.json export (FR-4.6) | `dd/export_dtcg.py` (generate W3C DTCG v2025.10 format; assemble composite types from atomic tokens at export time; resolver format with sets + modifiers from flat mode tables; alias references) | TASK-002 |
| TASK-063 | Write unit tests for all code exports | `tests/test_export_code.py` (verify CSS var naming, Tailwind config shape, DTCG schema compliance, composite type assembly, alias resolution in output) | TASK-060, TASK-061, TASK-062 |
| TASK-064 | Write integration tests for curation-to-code-export pipeline | `tests/test_export_code_integration.py` (seed post-curation fixture DB; run all 3 exporters; verify: CSS custom properties parse via regex, Tailwind config is valid JS object, DTCG JSON validates against W3C schema, all curated tokens appear in all 3 outputs, alias references resolve in output) | TASK-007, TASK-062 |
| TASK-065 | Write e2e test: full pipeline through all exports | `tests/test_e2e_full_export.py` (fixture DB -> extraction -> clustering -> curation -> validation -> CSS + Tailwind + DTCG + Figma payloads -> verify: all 4 export formats produced, token counts consistent across formats, round-trip: DTCG JSON re-importable, CSS vars match DTCG values; this is the comprehensive e2e covering waves 0-6) | TASK-007, TASK-062, TASK-055 |

### Wave 7: Companion Skill + Drift Detection

| Task | Description | Produces | Deps |
|------|-------------|----------|------|
| TASK-070 | Implement drift detection (UC-6) | `dd/drift.py` (compare DB token values against Figma via figma_get_variables; update sync_status; produce drift report via v_drift_report) | TASK-002 |
| TASK-071 | Create companion Claude skill | `declarative-design/SKILL.md` (DB discovery, token resolution queries, component catalog queries, screen composition queries, curation assistance workflow, export orchestration, disconnected mode) | TASK-002 |
| TASK-072 | Implement mode creation with value seeding (UC-5 from URS) | `dd/modes.py` (create new mode in collection; copy values from default mode; optional OKLCH lightness inversion for dark mode; scale factor for compact mode) | TASK-004, TASK-002 |
| TASK-073 | Write unit tests for drift detection + mode creation | `tests/test_drift.py`, `tests/test_modes.py` | TASK-070, TASK-072 |
| TASK-074 | Write e2e smoke test: full pipeline including drift + modes | `tests/test_e2e_full.py` (fixture DB -> extraction -> clustering -> curation -> validation -> all exports -> create dark mode (OKLCH inversion) -> simulate drift (modify fixture values) -> run drift detection -> verify: drift report surfaces changed tokens, mode values seeded correctly, full test suite regression via `pytest tests/ -v` as final gate) | TASK-007, TASK-073, TASK-065 |

---

## 6. Module Map

All production code lives under `dd/`. Tests under `tests/`.

```
declarative/                      <- project root
|-- dd/
|   |-- __init__.py
|   |-- config.py                 <- file paths, DB name convention
|   |-- db.py                     <- get_connection, init_db, backup_db
|   |-- types.py                  <- enums, constants, property paths
|   |-- color.py                  <- OKLCH conversion, delta_e, hex normalization
|   |-- normalize.py              <- value normalization per property type
|   |-- extract_inventory.py      <- Phase 1: file + screen inventory
|   |-- extract_screens.py        <- Phase 2: screen node extraction
|   |-- extract_bindings.py       <- Phase 3: binding creation + effect decomposition
|   |-- extract_components.py     <- Phase 4: component model extraction
|   |-- paths.py                  <- materialized path + is_semantic computation
|   |-- extract.py                <- extraction orchestrator (resume, progress)
|   |-- cluster_colors.py         <- OKLCH color clustering
|   |-- cluster_typography.py     <- type scale clustering
|   |-- cluster_spacing.py        <- spacing scale detection
|   |-- cluster_misc.py           <- radius + shadow clustering
|   |-- cluster.py                <- clustering orchestrator
|   |-- curate.py                 <- curation operations (accept/merge/split/reject/alias)
|   |-- validate.py               <- pre-export validation gate
|   |-- status.py                 <- progress + readiness reporting
|   |-- export_figma_vars.py      <- Figma variable payload + ID writeback
|   |-- export_rebind.py          <- rebind plugin script generator
|   |-- export_css.py             <- CSS custom properties export
|   |-- export_tailwind.py        <- Tailwind config export
|   |-- export_dtcg.py            <- W3C DTCG tokens.json export
|   |-- drift.py                  <- drift detection (DB vs Figma)
|   |-- modes.py                  <- mode creation + value seeding
|
|-- tests/
|   |-- conftest.py                          <- shared fixtures (test DB, mock Figma data)
|   |-- fixtures.py                          <- factory functions: seed DB at any pipeline stage
|   |-- test_color.py                        <- unit: color conversion, delta_e
|   |-- test_normalize.py                    <- unit: value normalization
|   |-- test_extraction.py                   <- unit: extraction with mocks
|   |-- test_extraction_integration.py       <- integration: full extraction chain
|   |-- test_components.py                   <- unit: component extraction
|   |-- test_components_integration.py       <- integration: components + extraction
|   |-- test_clustering.py                   <- unit: clustering modules
|   |-- test_clustering_integration.py       <- integration: extraction -> clustering
|   |-- test_e2e_extract_cluster.py          <- e2e: waves 0-3
|   |-- test_curation.py                     <- unit: curation operations
|   |-- test_validation.py                   <- unit: validation checks
|   |-- test_curation_integration.py         <- integration: clustering -> curation
|   |-- test_e2e_extract_validate.py         <- e2e: waves 0-4 (pre-export gate)
|   |-- test_export_figma.py                 <- unit: Figma payload format
|   |-- test_export_figma_integration.py     <- integration: curation -> Figma export
|   |-- test_e2e_figma_export.py             <- e2e: waves 0-5
|   |-- test_export_code.py                  <- unit: CSS, Tailwind, DTCG format
|   |-- test_export_code_integration.py      <- integration: curation -> code export
|   |-- test_e2e_full_export.py              <- e2e: waves 0-6 (all export formats)
|   |-- test_drift.py                        <- unit: drift detection
|   |-- test_modes.py                        <- unit: mode creation
|   |-- test_e2e_full.py                     <- e2e: waves 0-7 (final smoke test)
|
|-- schema.sql                    <- v0.2, copied from project root
|-- declarative-design/
|   |-- SKILL.md                  <- companion Claude skill
|
|-- build/
|   |-- Task-Decomp-Guide.md     <- this file
|   |-- generate-packets.py      <- packet generator (calls Opus)
|   |-- run-wave.sh              <- sequential task runner
|   |-- packets/                  <- generated task packets
|       |-- wave-0/
|       |-- wave-1/
|       |-- ...
```

---

## 7. Critical Path

```
TASK-001 -> TASK-002 -> TASK-003 -> TASK-005 -> TASK-010 -> TASK-011 -> TASK-012 -> TASK-014
                                        |                                               |
                                   TASK-004 -----> TASK-030 (color clustering)          |
                                                                                        v
                              TASK-020..024 (components) ----------> TASK-034 (clustering orchestrator)
                                                                         |
                                                                         v
                                                                    TASK-040..041 (curation + validation)
                                                                         |
                                                          +--------------+--------------+
                                                          v              v              v
                                                    TASK-050..053   TASK-060..063   TASK-070..073
                                                    (Figma export)  (Code export)   (Skill + drift)
```

Minimum viable path to first clustering output: ~17 tasks (waves 0-3).
Minimum viable path to first Figma variable export: ~24 tasks (waves 0-5).
Estimated total: ~43 tasks across 8 waves (30 implementation + 13 test tasks).
Estimated effort: 3-4 days focused agentic execution, or 10-15 manual sessions.

---

## 8. Testing Strategy

Three test levels, applied progressively by wave:

**Unit tests** (every wave): Isolated module tests with mocked dependencies. Fast, deterministic, run in <1s per file. Test individual functions: color conversion accuracy, SQL query correctness, export format compliance.

**Integration tests** (wave 1+): Test cross-module boundaries using fixture DBs with real pipeline output. No mocks at the seam being tested -- only external dependencies (Figma MCP) are mocked. These catch: schema mismatches between producer/consumer, FK violations, incorrect data shapes flowing across module boundaries.

**E2E tests** (wave 3+): Run the full pipeline from extraction through the current wave's final output. Use `tests/fixtures.py` factories to seed initial state, then execute the real pipeline. These catch: emergent failures from module interactions, state accumulation bugs, regression across waves.

**Pytest configuration:**
- Use `pytest-xdist` for parallel execution within a test level (`-n auto`)
- Use `pytest-timeout` with 30s default to catch infinite loops or deadlocks in clustering
- Use `pytest-cov` to track coverage -- target 80%+ on `dd/` module
- Mark tests with `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e` for selective runs
- E2e tests should be marked `@pytest.mark.slow` for optional exclusion during development

**Running tests:**
```
pytest tests/ -v                          # all tests
pytest tests/ -m unit -v                  # unit only
pytest tests/ -m integration -v           # integration only
pytest tests/ -m e2e -v                   # e2e only
pytest tests/ -m "not slow" -v            # skip slow e2e tests
pytest tests/ --cov=dd --cov-report=term  # with coverage
```

**Fixture DB seeding pattern:** The `tests/fixtures.py` module provides factory functions:
- `seed_post_extraction(db)` -- inserts files, screens, nodes, bindings matching mock Figma data
- `seed_post_clustering(db)` -- above + tokens, token_values, updated bindings
- `seed_post_curation(db)` -- above + accepted/merged tokens, all tiers set
- `seed_post_validation(db)` -- above + export_validations rows, all checks passing
Each factory uses deterministic data (fixed node IDs, predictable color values) so assertions are exact, not heuristic.

---

## 9. Notes for Packet Generator

- The spec suite for this project is 4 markdown files + 1 SQL file, all in the project root (Declarative/ folder). The generator should load all of them.
- MCP-dependent tasks (extraction, Figma export, drift detection) produce code that will be CALLED by an agent with MCP access, not executed directly. The builder agent writes Python functions; a separate agent session with MCP tools invokes them. Task packets should make this clear.
- The `schema.sql` file is the single source of truth for all table definitions, views, indexes, and triggers. Every task that touches the DB should inline the relevant CREATE TABLE/VIEW statements from this file.
- `coloraide` is the recommended library for OKLCH. If unavailable, manual conversion formulas are acceptable (sRGB -> linear RGB -> XYZ -> OKLAB -> OKLCH). The task packet should provide the fallback formulas.

---

## 10. Cross-References

- **User Requirements Spec.md**: Use cases UC-1 through UC-8, functional requirements FR-1 through FR-6
- **Technical Design Spec.md**: Pipeline phases 1-8, data model, agent cookbook queries
- **Architecture.md**: System overview, DB storage levels, tool strategy, read/write strategy
- **schema.sql**: 22 tables, 15 views, 27 indexes, 2 triggers
- **Probe Results.md**: Figma file profile, API throughput estimates, constraint discovery
- **Tooling Comparison.md**: Official vs Console MCP capability matrix
