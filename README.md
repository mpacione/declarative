# Declarative Design

A Python pipeline that extracts design system knowledge from Figma into a local SQLite database, then exports it to code (CSS, Tailwind, DTCG) and back to Figma as variables. The portable DB becomes a queryable source of truth that AI agents can use without a live Figma connection.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Declarative Design                          │
│                                                                     │
│   Figma File                                                        │
│       │                                                             │
│       ▼                                                             │
│   ┌────────┐    ┌──────────┐    ┌─────────┐    ┌───────────────┐   │
│   │Extract │───▶│ Cluster  │───▶│ Curate  │───▶│   Validate    │   │
│   │UC-1    │    │ UC-2a    │    │ UC-2b   │    │   Gate        │   │
│   └────────┘    └──────────┘    └─────────┘    └───────┬───────┘   │
│       │              │               │                  │           │
│       ▼              ▼               ▼                  ▼           │
│   ┌────────────────────────────────────────────────────────────┐   │
│   │              SQLite Database (.declarative.db)              │   │
│   │  screens ─ nodes ─ bindings ─ tokens ─ components          │   │
│   │  50+ views for census, coverage, readiness, drift          │   │
│   └────────────────────────────────────────────────────────────┘   │
│                  │                    │                  │           │
│                  ▼                    ▼                  ▼           │
│          ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│          │ Figma Export  │   │ Code Export   │   │ Drift Detect │   │
│          │ UC-3          │   │ UC-4          │   │ UC-6         │   │
│          │ Variables +   │   │ CSS, Tailwind │   │ DB vs Figma  │   │
│          │ Rebinding     │   │ DTCG tokens   │   │ sync check   │   │
│          └──────────────┘   └──────────────┘   └──────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Pipeline Phases

```
Phase 1        Phase 2         Phase 3         Phase 4          Phase 5
Inventory      Screen Walk     Normalize       Components       Cluster
─────────      ───────────     ─────────       ──────────       ───────
files          node trees      fills →         COMPONENT_SET    colors
screens        40+ props       bindings        variants         typography
device class   per node        hex, px         axes, slots      spacing
                               values          a11y hints       radius, effects

     │               │              │               │               │
     └───────────────┴──────────────┴───────────────┴───────────────┘
                                    │
                              ┌─────▼─────┐
                              │   SQLite   │
                              │     DB     │
                              └─────┬─────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                       │
        Phase 6               Phase 6.5               Phase 7
        Curate                Validate                Export
        ──────                ────────                ──────
        accept/reject         mode completeness       Figma variables
        rename/merge          DTCG naming             CSS custom props
        split/alias           orphan check            Tailwind config
        accept_all            value format            DTCG tokens.json
                              alias targets           rebind scripts
```

## Token Lifecycle

```
                    ┌──────────┐
                    │ Extracted │  Clustering output, auto-proposed
                    └─────┬────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌──────────┐ ┌────────┐ ┌──────────┐
        │ Accepted │ │Renamed │ │ Rejected │  Curation operations
        │ (curated)│ │(curated│ │ (deleted)│
        └────┬─────┘ └───┬────┘ └──────────┘
             │            │
             ▼            ▼
        ┌────────────────────┐
        │   Curated Tokens   │  Ready for export
        └─────────┬──────────┘
                  │
        ┌─────────┼──────────────┐
        ▼         ▼              ▼
   ┌─────────┐ ┌──────────┐ ┌────────┐
   │  Merge  │ │  Split   │ │ Alias  │  Advanced operations
   │ (dedup) │ │ (refine) │ │ (ref)  │
   └─────────┘ └──────────┘ └────────┘
```

## Binding Status Flow

```
  unbound ──── clustering ────▶ proposed ──── accept ────▶ bound
     ▲                             │                        │
     │                             │                        │
     └────── reject ───────────────┘                        │
     └────── re-extract (value changed) ────────────────────┘
                                                    (overridden)
```

## Database Schema (simplified)

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────────────┐
│  files   │────▶│ screens  │────▶│  nodes   │────▶│ node_token_      │
│          │     │          │     │ (40+ col)│     │ bindings         │
└──────────┘     └──────────┘     └──────────┘     └────────┬─────────┘
                                                            │
┌──────────────┐  ┌──────────┐  ┌──────────┐               │
│ token_       │  │ token_   │  │ tokens   │◀──────────────┘
│ collections  │─▶│ modes    │─▶│          │
└──────────────┘  └──────────┘  └────┬─────┘
                                     │
                                     ▼
                               ┌──────────┐
                               │ token_   │
                               │ values   │
                               └──────────┘

┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ components   │─▶│ component_   │  │ variant_     │  │ component_   │
│              │  │ variants     │  │ axes         │  │ slots        │
└──────┬───────┘  └──────────────┘  └──────────────┘  └──────────────┘
       │
       ▼
┌──────────────┐
│ component_   │
│ a11y         │
└──────────────┘
```

## Prerequisites

- **Python 3.11+**
- **Git**
- **Claude CLI** (for wave-based build execution)
- **coloraide** (installed automatically, used for OKLCH color operations)

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/mpacione/declarative.git
cd declarative

# 2. Run the init script (creates venv, installs dependencies, verifies specs)
bash build/init.sh

# 3. Activate the virtual environment
source build/.venv/bin/activate

# 4. Verify everything works
pytest tests/ -v --tb=short
```

The init script handles:
- Creating a Python virtual environment at `build/.venv`
- Installing all dependencies (`coloraide`, `pytest`, `pytest-xdist`, `pytest-timeout`, `pytest-cov`)
- Creating `dd/` and `tests/` directories with `__init__.py` files
- Verifying all spec files are present

## Usage

### Initialize a Database

```python
from dd.db import init_db, get_connection
from dd.config import db_path

# Create a new database for your Figma file
path = db_path("my-design-system")  # -> my-design-system.declarative.db
conn = get_connection(str(path))
init_db(conn, str(path))
```

### Run Extraction (requires Figma MCP)

```python
from dd.extract import run_extraction_pipeline

# With a Figma MCP callback that calls use_figma
summary = run_extraction_pipeline(
    conn=conn,
    file_key="your_figma_file_key",
    file_name="My Design System",
    screens_data=[...],          # From figma_get_file_data
    extract_fn=my_mcp_callback,  # Calls use_figma with generated scripts
)
```

### Run Clustering

```python
from dd.cluster import run_clustering

summary = run_clustering(conn, file_id=1)
# Creates tokens for colors, typography, spacing, radius, effects
```

### Curate Tokens

```python
from dd.curate import accept_token, rename_token, merge_tokens, reject_token

# Accept a proposed token
accept_token(conn, token_id=42)

# Rename to follow DTCG conventions
rename_token(conn, token_id=42, new_name="color.surface.primary")

# Merge duplicate tokens
merge_tokens(conn, survivor_id=42, victim_id=43)

# Bulk accept everything
from dd.curate import accept_all
accept_all(conn, file_id=1)
```

### Validate Before Export

```python
from dd.validate import run_validation, is_export_ready

passed = run_validation(conn)
if is_export_ready(conn):
    print("Ready to export!")
```

### Export to Code

```python
from dd.export_css import export_css
from dd.export_tailwind import export_tailwind
from dd.export_dtcg import export_dtcg

# CSS custom properties
css_output = export_css(conn)      # :root { --color-surface-primary: #fff; }

# Tailwind theme config
tw_output = export_tailwind(conn)  # module.exports = { theme: { extend: { ... } } }

# W3C DTCG tokens.json
dtcg_output = export_dtcg(conn)    # { "color": { "surface": { "$type": "color", ... } } }
```

### Export to Figma (requires MCP)

```python
from dd.export_figma_vars import generate_variable_payloads_checked

# Generate payloads for figma_setup_design_tokens
payloads = generate_variable_payloads_checked(conn, file_id=1)
# Each payload has: collectionName, modes, tokens (max 100 per batch)
```

### Detect Drift

```python
from dd.drift import detect_drift, detect_drift_readonly

# Read-only check (doesn't modify DB)
comparison = detect_drift_readonly(conn, file_id=1, figma_response=response)

# Full check with DB updates
result = detect_drift(conn, file_id=1, figma_response=response)
print(result["report"])
```

### Check Status

```python
from dd.status import format_status_report

report = format_status_report(conn)
print(report)
# Curation Progress: 85% bound, 10% proposed, 5% unbound
# Export Readiness: PASS (7/7 checks)
```

## Running Tests

```bash
# All tests
pytest tests/ -v

# By test level
pytest tests/ -m unit           # Fast unit tests (~400)
pytest tests/ -m integration    # Cross-module boundary tests (~60)
pytest tests/ -m e2e            # Full pipeline end-to-end tests (~30)

# With coverage
pytest tests/ -v --cov=dd --cov-report=term

# Specific module
pytest tests/test_clustering.py -v
pytest tests/test_export_code.py -v
```

## Project Structure

```
declarative/
├── dd/                              # Production code
│   ├── __init__.py                  # Package (v0.1.0)
│   ├── config.py                    # Constants and paths
│   ├── db.py                        # SQLite connection + init
│   ├── types.py                     # Enums and constants
│   ├── color.py                     # RGBA/hex/OKLCH utilities
│   ├── normalize.py                 # Figma props → binding rows
│   ├── paths.py                     # Materialized path computation
│   │
│   ├── extract.py                   # Extraction orchestrator
│   ├── extract_inventory.py         # File + screen population
│   ├── extract_screens.py           # Node tree extraction
│   ├── extract_bindings.py          # Property → binding creation
│   ├── extract_components.py        # Component/variant extraction
│   │
│   ├── cluster.py                   # Clustering orchestrator
│   ├── cluster_colors.py            # Perceptual color grouping
│   ├── cluster_typography.py        # Type scale detection
│   ├── cluster_spacing.py           # Spacing pattern detection
│   ├── cluster_misc.py              # Radius + effect clustering
│   │
│   ├── curate.py                    # Token curation operations
│   ├── validate.py                  # Pre-export validation gate
│   ├── status.py                    # Progress reporting
│   ├── modes.py                     # Multi-mode management
│   ├── drift.py                     # Figma ↔ DB sync detection
│   │
│   ├── export_figma_vars.py         # Figma variable payloads
│   ├── export_rebind.py             # Node rebinding scripts
│   ├── export_css.py                # CSS custom properties
│   ├── export_tailwind.py           # Tailwind theme config
│   └── export_dtcg.py              # W3C DTCG tokens.json
│
├── tests/                           # 505 tests (unit + integration + e2e)
├── schema.sql                       # SQLite schema (50+ views)
├── declarative-design/SKILL.md      # Companion AI skill
├── build/                           # Wave-based build system
│   ├── init.sh                      # One-time setup
│   ├── run-wave.sh                  # Task execution runner
│   ├── generate-packets.py          # Task packet generator
│   └── packets/                     # Pre-generated task packets (wave-0 to wave-7)
│
├── Architecture.md                  # System design
├── Technical Design Spec.md         # Detailed specifications
├── User Requirements Spec.md        # Use cases (UC-1 through UC-6)
├── Probe Results.md                 # Figma data shape validation
├── Tooling Comparison.md            # Why SQLite + Console MCP
├── pyproject.toml                   # Project metadata
└── requirements.txt                 # Python dependencies
```

## Key Design Decisions

**SQLite as the portable source of truth** — A single `.declarative.db` file with zero infrastructure. Agents can query tokens, components, and screens without Figma running. The 50+ views provide pre-built analytics for census, coverage, readiness, and drift.

**Wide denormalized node rows** — The `nodes` table has 40+ columns to avoid N+1 JOINs when querying full screen trees. Materialized paths (`0.3.5.1`) encode tree position for efficient descendant queries.

**DTCG-compliant token naming** — All tokens follow W3C Design Token Community Group conventions (`color.surface.primary`, `space.4`). Dot-path names convert to CSS vars (`--color-surface-primary`), Figma paths (`color/surface/primary`), and Tailwind keys automatically.

**Atomic token storage, composite assembly at export** — Typography and shadow tokens are stored as individual atoms (fontSize, fontFamily, etc.). Composite DTCG types are assembled at export time, giving maximum flexibility for code generation.

**Offline-first** — Everything except extraction and Figma export works without a Figma connection. Curation, validation, code export, and all queries run against the local DB.

## Build System

The project was built using an autonomous wave-based pipeline. Each wave feeds task packets to Claude CLI, auto-committing after each successful task.

```bash
# Validate all task packets
source build/.venv/bin/activate
python3 build/generate-packets.py --validate

# Run a specific wave
./build/run-wave.sh 0              # Run all tasks in wave 0
./build/run-wave.sh 3 TASK-033     # Resume wave 3 from a specific task

# Dry run (shows what would execute)
DRY_RUN=1 ./build/run-wave.sh 0
```

| Wave | Tasks | What it builds |
|------|-------|----------------|
| 0 | 7 | Project scaffold, DB init, test infrastructure |
| 1 | 7 | Extraction pipeline (inventory + screens) |
| 2 | 7 | Component extraction + normalization |
| 3 | 8 | Census views + clustering |
| 4 | 6 | Curation workflow + validation |
| 5 | 6 | Figma export (variables + rebinding) |
| 6 | 6 | Code export (CSS, Tailwind, DTCG) |
| 7 | 5 | Companion skill + drift detection |

**Total: 52 tasks, 505 tests, 89% code coverage**
