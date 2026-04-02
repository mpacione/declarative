# Declarative Design

Extract your Figma design system into a portable SQLite database, then export tokens to CSS, Tailwind, DTCG, and back to Figma as variables.

## How It Works

**Extraction is a CLI command. Everything else is conversational via Claude Code.**

Extraction calls the Figma REST API directly — no MCP tools, no agent in the loop, fully deterministic. Clustering, curation, validation, and export are orchestrated by Claude Code using the `dd/` Python library.

```
┌──────────────────────────────────────────────────────────┐
│                     How You Use It                        │
│                                                           │
│   python -m dd extract ──▶ Figma REST API ──▶ SQLite DB  │
│                                                           │
│   You ──▶ Claude Code ──▶ dd/ Python library              │
│              │                    │                        │
│              │  Figma MCP tools   │  SQLite DB             │
│              ▼                    ▼                        │
│          Figma file      .declarative.db                  │
│                                │                          │
│                    ┌───────────┼───────────┐              │
│                    ▼           ▼           ▼              │
│               CSS vars    Tailwind    tokens.json         │
└──────────────────────────────────────────────────────────┘
```

### What you say to Claude vs what happens

| You say | Claude does |
|---------|-------------|
| "Extract my Figma file" | Runs `python -m dd extract` (Figma REST API, stores everything in SQLite) |
| "Cluster the tokens" | Runs color/type/spacing/radius/effect clustering, proposes token names |
| "Accept all tokens" | Promotes extracted tokens to curated tier, marks bindings as bound |
| "Rename `color.fill.0` to `color.surface.primary`" | Updates token name with DTCG validation |
| "Export CSS" | Generates `:root { --color-surface-primary: #fff; }` |
| "Export to Figma" | Creates Figma variable payloads, writes them via MCP |
| "Check for drift" | Compares DB tokens against live Figma variables |
| "What's the status?" | Queries `v_curation_progress` — shows bound%, coverage, readiness |
| "Show me the color tokens" | Queries `v_resolved_tokens WHERE type = 'color'` |
| "Add a dark mode" | Creates new mode, seeds values, inverts colors via OKLCH |

## Quick Start

### 1. Setup

```bash
git clone https://github.com/mpacione/declarative.git
cd declarative

# Create venv + install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify
pytest tests/ -v --tb=short
```

### 2. Open in Claude Code

```bash
cd declarative
claude
```

Claude Code will discover the `declarative-design/SKILL.md` skill and the `dd/` library. Now you can talk to it.

### 3. The Workflow

There are 6 steps. You do them in order. Step 1 is a CLI command. Steps 2-6 are conversational via Claude.

```
Step 1          Step 2          Step 3          Step 4          Step 5          Step 6
EXTRACT         CLUSTER         CURATE          VALIDATE        EXPORT          DRIFT
───────         ───────         ──────          ────────        ──────          ─────
python -m dd    "Cluster the    "Accept all"    "Validate"      "Export CSS"    "Check for
  extract        tokens"        "Rename X"      (auto-runs      "Export to       drift"
                                "Merge A+B"      before          Figma"
CLI + REST       DB-only         DB-only         export)         Figma needs     Figma needs
API (no MCP)                                                     MCP             MCP
```

**Steps 2-4 work offline** — no Figma connection needed. Step 1 uses the Figma REST API directly (no MCP, no Figma Desktop required). Steps 5-6 require Figma MCP tools.

### Step-by-step example

```
You:     python -m dd extract --file-key abc123 --page 0:1
         # Runs in ~5 min, no agent needed

Output:  [Fetches file structure via REST API] → [Batch-fetches screen
         node trees] → [Normalizes 40+ properties per node] →
         [Creates bindings for fills, strokes, typography, spacing, etc.]
         → "Extracted 230 screens, 25,547 nodes, 48,291 bindings."

You:     "Cluster the tokens."

Claude:  [Groups similar colors by OKLCH delta-E] → [Detects type scale] →
         [Finds spacing patterns (4px base)] → [Clusters radius + effects]
         → "Proposed 156 tokens: 42 colors, 18 type, 12 spacing, ..."

You:     "Accept all tokens, then rename color.fill.0 to color.surface.primary."

Claude:  [Promotes all to curated] → [Renames with DTCG validation]
         → "156 tokens accepted, 1 renamed."

You:     "Export CSS and Tailwind."

Claude:  [Validates] → [Generates CSS custom properties] →
         [Generates Tailwind theme config]
         → "Exported 156 tokens to CSS (tokens.css) and Tailwind (tailwind.theme.js)."

You:     "Push the tokens to Figma as variables."

Claude:  [Generates payloads, max 100 tokens each] →
         [Calls figma_setup_design_tokens] → [Writes back variable IDs]
         → "Created 156 Figma variables across 5 collections."

You:     "Check for drift."

Claude:  [Calls figma_get_variables] → [Compares against DB]
         → "All 156 tokens synced. No drift detected."
```

## Three Ways to Interact

### 1. Through Claude Code (primary)

Open the project in Claude Code. The skill file teaches Claude the full workflow. Just describe what you want in natural language.

### 2. Python REPL (for scripting)

```bash
source .venv/bin/activate
python3
```

```python
from dd.db import init_db, get_connection
from dd.config import db_path

# Create a database
path = db_path("my-app")  # → my-app.declarative.db
conn = get_connection(str(path))
init_db(conn, str(path))

# After extraction + clustering (done by Claude or scripts):
from dd.curate import accept_all, rename_token
from dd.validate import run_validation, is_export_ready
from dd.export_css import export_css
from dd.export_tailwind import export_tailwind
from dd.export_dtcg import export_dtcg
from dd.status import format_status_report

accept_all(conn, file_id=1)
rename_token(conn, token_id=42, new_name="color.surface.primary")

run_validation(conn)
if is_export_ready(conn):
    print(export_css(conn))
    print(export_tailwind(conn))
    print(export_dtcg(conn))

print(format_status_report(conn))
```

### 3. Direct SQL queries (for analysis)

```bash
sqlite3 my-app.declarative.db
```

```sql
-- What's the curation status?
SELECT * FROM v_curation_progress;

-- All curated color tokens with their values
SELECT * FROM v_resolved_tokens WHERE type = 'color' ORDER BY name;

-- Component catalog
SELECT * FROM v_component_catalog;

-- Screen composition tree
SELECT path, name, node_type, is_semantic
FROM nodes WHERE screen_id = 1 ORDER BY path;

-- Export readiness
SELECT * FROM v_export_readiness;

-- Drift report
SELECT * FROM v_drift_report;
```

The database has **50+ views** pre-built for common queries. See `schema.sql` for the full list.

## What Requires Figma vs What's Offline

| Operation | Needs Figma? | What it uses |
|-----------|:---:|---|
| Extract screens + nodes | REST API only | `python -m dd extract` (Figma REST API, no MCP needed) |
| Extract components | REST API only | Included in extraction |
| Cluster tokens | No | DB only |
| Curate (accept/rename/merge/split) | No | DB only |
| Validate | No | DB only |
| Check status | No | DB only |
| Export CSS / Tailwind / DTCG | No | DB only |
| Export to Figma variables | Yes | `figma_setup_design_tokens` MCP |
| Rebind nodes to variables | Yes | `figma_execute` MCP |
| Detect drift | Yes | `figma_get_variables` MCP |
| Add dark mode | No | DB only (OKLCH inversion) |
| Query tokens, components, screens | No | DB only |
| Classify screen components (T5) | No (+ optional LLM) | `python -m dd classify` |
| Generate IR (T5) | No | `python -m dd generate-ir` |
| Vision cross-validation (T5) | Yes (Figma + LLM) | `--vision` flag on classify |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Declarative Design                           │
│                                                                     │
│   Figma File                                                        │
│       │                                                             │
│       ▼                                                             │
│   ┌────────┐    ┌──────────┐    ┌─────────┐    ┌───────────────┐   │
│   │Extract │───▶│ Cluster  │───▶│ Curate  │───▶│   Validate    │   │
│   │        │    │          │    │         │    │   Gate        │   │
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

## Database Schema

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

## Running Tests

```bash
source .venv/bin/activate

# All tests
pytest tests/ -v

# By level
pytest tests/ -m unit
pytest tests/ -m integration
pytest tests/ -m e2e

# With coverage
pytest tests/ -v --cov=dd --cov-report=term
```

## Project Structure

```
declarative/
├── dd/                              # Python library (the pipeline)
│   ├── config.py                    # Constants, paths, limits
│   ├── db.py                        # SQLite connection + schema init
│   ├── types.py                     # Enums (DeviceClass, Tier, ComponentCategory, ...)
│   ├── color.py                     # RGBA/hex/OKLCH color math
│   ├── normalize.py                 # Figma props → binding rows
│   ├── paths.py                     # Materialized path computation
│   │
│   ├── figma_api.py                 # Figma REST API client + node conversion
│   ├── cli.py                       # CLI entrypoint (python -m dd)
│   ├── __main__.py                  # Enables python -m dd invocation
│   ├── extract.py                   # Extraction orchestrator (resume support)
│   ├── extract_inventory.py         # File + screen population
│   ├── extract_screens.py           # Node tree parsing + DB insertion
│   ├── extract_bindings.py          # Property → binding creation
│   ├── extract_components.py        # Component/variant/slot/a11y extraction
│   │
│   ├── cluster.py                   # Clustering orchestrator
│   ├── cluster_colors.py            # OKLCH perceptual color grouping
│   ├── cluster_typography.py        # Type scale detection
│   ├── cluster_spacing.py           # Spacing pattern detection (4px/8px base)
│   ├── cluster_misc.py              # Radius + shadow/blur clustering
│   │
│   ├── curate.py                    # accept, rename, merge, split, reject, alias
│   ├── validate.py                  # Pre-export gate (7 checks)
│   ├── status.py                    # Progress + readiness reporting
│   ├── modes.py                     # Dark mode, compact mode, themes
│   ├── drift.py                     # DB ↔ Figma sync detection (library-only)
│   │
│   ├── export_figma_vars.py         # Figma variable payloads (batched)
│   ├── export_rebind.py             # JS scripts to bind nodes → variables
│   ├── export_css.py                # CSS custom properties
│   ├── export_tailwind.py           # Tailwind theme config
│   ├── export_dtcg.py              # W3C DTCG tokens.json
│   │
│   ├── catalog.py                   # T5: 48 canonical component types + seeding
│   ├── classify.py                  # T5: classification orchestrator + formal matching
│   ├── classify_rules.py            # T5: ALL classification rules (single source of truth)
│   ├── classify_heuristics.py       # T5: structural heuristic classification
│   ├── classify_llm.py              # T5: LLM classification via Claude Haiku
│   ├── classify_vision.py           # T5: vision cross-validation (screenshot + re-classify)
│   ├── classify_skeleton.py         # T5: screen skeleton notation extraction
│   └── ir.py                        # T5: CompositionSpec IR generation
│
├── tests/                           # 922 tests
├── docs/                            # T5 research + architecture docs
├── docs/archive/                    # Historical specs (superseded)
├── migrations/                      # Schema evolution (001-005)
├── schema.sql                       # SQLite schema + views
├── declarative-design/SKILL.md      # Companion Claude Code skill
├── .env                             # API keys (gitignored)
└── pyproject.toml                   # Python 3.11+, deps
```

## T5: Compositional Analysis (Experimental)

T5 adds compositional understanding — classifying what components ARE, not just what they look like. This enables IR generation and future code/design generation.

### CLI Commands

```bash
# Seed the universal component type catalog (48 types)
python -m dd seed-catalog --db my-app.declarative.db

# Classify all screen components (formal + heuristic + optional LLM)
python -m dd classify --db my-app.declarative.db
python -m dd classify --db my-app.declarative.db --llm          # + LLM fallback
python -m dd classify --db my-app.declarative.db --llm --vision  # + vision cross-validation

# Generate CompositionSpec IR for a screen
python -m dd generate-ir --db my-app.declarative.db --screen 42
python -m dd generate-ir --db my-app.declarative.db --screen all
```

### Classification Cascade

1. **Formal matching** — INSTANCE/FRAME names matched against 48 canonical types + aliases (confidence: 1.0)
2. **Structural heuristics** — position, font size, layout rules (confidence: 0.7-0.9)
3. **LLM fallback** — Claude Haiku for ambiguous nodes (confidence: 0.7-0.9, requires `ANTHROPIC_API_KEY`)
4. **Vision cross-validation** — screenshot + re-classify to flag disagreements (requires `FIGMA_ACCESS_TOKEN`)

All classification rules live in `dd/classify_rules.py` — single file to audit and tune.

### Current Accuracy

Tested on the Dank file (338 screens, 86,761 nodes): **93.6% adjusted coverage** (47,292 classified of 50,517 classifiable nodes).

## Key Design Decisions

**CLI for extraction, agent for everything else.** Extraction is deterministic (walk tree, store properties) so it runs as a CLI command via the Figma REST API. Curation, export, and conjure require judgment, so they stay conversational via Claude Code.

**SQLite as portable source of truth.** A single `.declarative.db` file. Zero infrastructure. Works offline. 50+ pre-built views for common queries. Agents can query tokens, components, and screens without Figma.

**Wide denormalized node rows.** The `nodes` table has 40+ columns to avoid N+1 JOINs. Materialized paths (`0.3.5.1`) encode tree position for efficient descendant queries via `LIKE '0.3.5.%'`.

**DTCG-compliant naming.** Tokens follow W3C conventions (`color.surface.primary`). Names auto-convert to CSS vars (`--color-surface-primary`), Figma paths (`color/surface/primary`), and Tailwind keys.

**Atomic storage, composite assembly at export.** Typography and shadow tokens are stored as atoms (fontSize, fontFamily, etc.). Composites are assembled at export time for maximum flexibility.

