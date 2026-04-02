# Declarative Design Companion Skill

**Version**: 0.4.0
**Skill Name**: declarative-design
**Description**: Agent protocol for extracting, curating, and exporting design tokens from Figma files.
**Activation**: When encountering `*.declarative.db` files, Figma URLs, or requests to work with design systems/tokens.

## Architecture: CLI + Agent

**CLI handles deterministic work.** Extraction, clustering, validation, export — these are mechanical operations that don't need judgment. Run them as shell commands.

**Agent handles judgment work.** Renaming tokens semantically, merging near-duplicates, creating aliases, building dark mode, composing screens — these require understanding design intent.

## CLI Commands (run via Bash)

```bash
# Phase 1: Extract — fetches Figma file via REST API, populates SQLite
python -m dd extract <figma-url-or-key> [--token TOKEN] [--db PATH]

# Phase 2: Cluster — groups raw values into token proposals
python -m dd cluster [--db PATH] [--threshold 2.0]

# Phase 3: Accept — bulk-accept high-confidence proposals
python -m dd accept-all [--db PATH]

# Phase 4: Validate — check DTCG compliance, mode completeness
python -m dd validate [--db PATH]

# Phase 5: Export — generate code artifacts
python -m dd export css|tailwind|dtcg [--db PATH] [--out FILE]

# Phase 6: Push — sync tokens to Figma as variables + rebind nodes
python -m dd push [--db PATH] [--phase variables|rebind|all] [--dry-run]
python -m dd push [--db PATH] --figma-state FILE [--phase variables|rebind|all]
python -m dd push [--db PATH] --writeback --figma-state FILE

# Maintenance
python -m dd maintenance [--db PATH] [--keep-last N] [--dry-run]

# Diagnostics
python -m dd status [--db PATH]
python -m dd curate-report [--db PATH] [--json]
```

The `--db` flag auto-detects if exactly one `*.declarative.db` exists in the current directory.

The `FIGMA_ACCESS_TOKEN` environment variable provides the Figma PAT for extraction.

## Quick Start: New File

When a user provides a Figma URL and wants to tokenize it:

```bash
# 1. Extract everything
python -m dd extract "https://www.figma.com/design/abc123/My-File"

# 2. Cluster into tokens
python -m dd cluster

# 3. Bulk accept (gets to ~100% coverage)
python -m dd accept-all

# 4. Check what needs curation
python -m dd curate-report

# 5. After curation: validate and export
python -m dd validate
python -m dd export css
python -m dd export dtcg
python -m dd export tailwind
```

## Agent Curation Protocol

After `dd accept-all`, run `dd curate-report --json` to get a structured list of issues. The report surfaces 5 categories:

### 1. Numeric Names → Semantic Renaming

Tokens like `color.surface.42` need meaningful names like `color.surface.canvas`.

```python
from dd.curate import rename_token
from dd.db import get_connection

conn = get_connection("file.declarative.db")

# Look at the token's value and usage context to choose a name
rename_token(conn, token_id=123, new_name="color.surface.canvas")
```

**How to decide names:** Query where the token is used, look at node names and screen context, infer semantic meaning from usage patterns. A color used on 200 background frames is likely `color.surface.*`. A color used on 3 error icons is likely `color.feedback.error`.

### 2. Near-Duplicate Colors → Merge

Colors within ΔE < 3 are perceptually similar. The report shows pairs.

```python
from dd.curate import merge_tokens

# Keep the higher-use token, absorb the other
merge_tokens(conn, survivor_id=123, victim_id=456, new_name="color.border.subtle")
```

### 3. Low-Use Tokens → Review

Tokens with ≤5 bindings might be one-offs (design noise) or might be intentional accent colors. Ask the user or check context before deleting.

```python
from dd.curate import reject_token

# Remove a one-off token and unbind its nodes
reject_token(conn, token_id=789, cascade=True)
```

### 4. Fractional Font Sizes → Round

Figma scaling produces values like `36.86px`. These should be rounded to the nearest integer.

```python
from dd.db import update_token_value

# mode_id is the default mode for the token's collection
update_token_value(conn, token_id=123, mode_id=1,
                   new_resolved="37", changed_by="curate",
                   reason="round fractional font size 36.86→37")
```

**All value mutations must go through `update_token_value()`** — never write directly to `token_values`. This ensures every change is recorded in `token_value_history` with `changed_by` and `reason`.

### 5. Semantic Layer → Create Aliases

A mature design system has two layers:
- **Primitives**: `color.surface.42` = `#09090B` (the raw clustered value)
- **Semantic**: `color.canvas` → aliases `color.surface.42` (the meaning)

```python
from dd.curate import create_alias

# Create semantic alias pointing to a primitive
create_alias(conn, alias_name="color.danger", target_token_id=123, collection="semantic")
```

## Curation Operations Reference

All curation functions are in `dd.curate`:

```python
from dd.curate import (
    accept_token,        # Accept a single proposed token
    rename_token,        # Rename to DTCG convention (validates format)
    merge_tokens,        # Combine two tokens (rebinds all nodes)
    split_token,         # Split one token into two (moves specific nodes)
    reject_token,        # Remove a token (optionally unbinds nodes)
    create_alias,        # Create semantic alias → primitive
    create_collection,   # Create new token collection with modes
    convert_to_alias,    # Convert a valued token into an alias of another
    accept_all,          # Bulk accept all proposed tokens
)
```

### Token Name Rules

Names must match: `^[a-z][a-zA-Z0-9]*(\.[a-zA-Z0-9]+)*$`

- Dot-separated segments: `color.surface.primary`
- camelCase allowed for atomic properties: `type.body.md.fontSize`
- No leading digits in segments: `v2xl` not `2xl`

## DB Query Patterns

When making curation decisions, query the DB for context:

### Find where a token is used
```sql
SELECT n.name, s.name as screen_name, ntb.property
FROM node_token_bindings ntb
JOIN nodes n ON ntb.node_id = n.id
JOIN screens s ON n.screen_id = s.id
WHERE ntb.token_id = ?
ORDER BY s.name, n.name
LIMIT 20;
```

### Get all color tokens with values and usage
```sql
SELECT t.name, tv.resolved_value, COUNT(ntb.id) as uses
FROM tokens t
JOIN token_values tv ON t.id = tv.token_id
LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id AND ntb.binding_status = 'bound'
WHERE t.type = 'color'
GROUP BY t.id
ORDER BY uses DESC;
```

### Pipeline health
```sql
SELECT * FROM v_curation_progress;
```

### Export readiness
```sql
SELECT * FROM v_export_readiness;
```

### Screen composition tree
```sql
SELECT n.path, n.name, n.node_type, t.name as token_name, ntb.property
FROM nodes n
LEFT JOIN node_token_bindings ntb ON ntb.node_id = n.id AND ntb.binding_status = 'bound'
LEFT JOIN tokens t ON ntb.token_id = t.id
WHERE n.screen_id = ?
ORDER BY n.path;
```

## Export Paths

### Code Exports (CLI)
```bash
python -m dd export css      # CSS custom properties
python -m dd export tailwind # Tailwind theme config
python -m dd export dtcg     # W3C DTCG tokens.json
```

### Figma Push Pipeline (Agent + MCP)

The `dd push` CLI generates a manifest of MCP actions. The agent executes them.

```bash
# First push (no existing Figma state):
python -m dd push --phase variables --dry-run     # Preview CREATE counts
python -m dd push --phase variables               # Output MCP action specs
# Agent executes actions, saves figma_get_variables response
python -m dd push --writeback --figma-state response.json  # Write back IDs
python -m dd push --phase rebind                  # Output rebind scripts
# Agent executes scripts via figma_execute or PROXY_EXECUTE

# Incremental push (after curation changes):
# Agent: figma_get_variables → save to figma_state.json
python -m dd push --figma-state figma_state.json --dry-run  # Preview diff
python -m dd push --figma-state figma_state.json            # Execute
```

No opacity restoration post-step is needed. Alpha-baked color primitives encode paint opacity directly in the variable value as 8-digit hex (`#RRGGBBAA`).

### Figma Rebinding (Agent + MCP)
```python
from dd.export_rebind import generate_rebind_scripts

scripts = generate_rebind_scripts(conn, file_id=1)
# Execute each script via figma_execute MCP tool (batched at 950 bindings/script)
# No opacity restoration needed — alpha is baked into color variable values
```

### Tokenizable Properties (bindable to Figma variables)

| Category | Properties |
|---|---|
| **Color** | fill.N.color, stroke.N.color, effect.N.color |
| **Shadow** | effect.N.radius, effect.N.offsetX/Y, effect.N.spread |
| **Radius** | cornerRadius, topLeft/topRight/bottomLeft/bottomRightRadius |
| **Spacing** | padding.top/right/bottom/left, itemSpacing, counterAxisSpacing |
| **Typography** | fontSize, fontFamily, fontWeight, fontStyle, lineHeight, letterSpacing, paragraphSpacing |
| **Stroke** | strokeWeight, strokeTopWeight/Right/Bottom/Left |
| **Other** | opacity, visible (BOOLEAN) |

Properties not bindable to variables but stored for Conjure: layout_mode, alignment, sizing, rotation, clipsContent, constraints, strokeAlign/Cap/Join, dashPattern, textDecoration, textCase, textAlignVertical, layoutWrap, min/max dimensions, componentKey.

### Known Figma API Behaviors
- `setBoundVariableForPaint` resets paint opacity to 1.0 — **solved** by alpha-baked colors (opacity encoded in 8-digit hex `#RRGGBBAA` variable value)
- `setBoundVariableForEffect` resets effect color.a to 1.0 — **solved** by alpha-baked colors
- Variable value changes (including alias updates) re-evaluate all bound nodes — **solved** by alpha-baked colors (alpha is part of the value, not a separate paint property)
- Binding `itemSpacing` on `SPACE_BETWEEN` nodes overrides auto gap — compact handler skips these
- No opacity restoration post-step is needed. The `restore_opacities` phase has been removed from the push manifest.

## Disconnected Mode

**Works without Figma:** All DB queries, curation, validation, CSS/Tailwind/DTCG export.

**Requires Figma PAT:** Extraction (`dd extract`).

**Requires Figma MCP:** Variable push, rebinding, drift detection against live file.

## Primitives / Semantics Architecture

Color tokens are split into two layers:

- **Color Primitives**: 45 value-based tokens (`prim.gray.500`, `prim.blue.400`). Raw hex values.
- **Color Semantics**: 52 context-based aliases (`color.surface.searchbar` → `prim.gray.500`). These are what nodes bind to.

Node bindings reference semantic token IDs. Changing a primitive value propagates to all semantics that alias it. In Figma, semantic variables use `createVariableAlias` to reference primitive variables.

Spacing, Radius, Opacity already have 1:1 value:token mappings — they are effectively primitives.

### Alpha-Baked Colors

Paint opacity is encoded directly in color variable values as 8-digit hex (`#RRGGBBAA`). Colors with opacity < 1 produce distinct primitives (e.g., `prim.gray.950.a5` for 5% opacity). This eliminates the need for separate opacity restoration after variable operations. OKLCH transforms and color clustering handle the alpha suffix transparently.

## T5: Compositional Analysis

Classifies what components ARE (not just properties) and generates a platform-agnostic IR.

### CLI Commands

```bash
# Seed catalog (48 canonical UI types)
python -m dd seed-catalog [--db PATH]

# Classify components (formal + heuristic + optional LLM/vision)
python -m dd classify [--db PATH] [--llm] [--vision]

# Generate CompositionSpec IR
python -m dd generate-ir [--db PATH] --screen SCREEN_ID|all
```

### Classification Rules

All rules live in `dd/classify_rules.py` — single file to audit:
- Name patterns (generic Frame/Group detection, Button N normalization)
- System chrome exclusion (iOS status bars, keyboard keys)
- Structural heuristics (header by position, text by font size, container by name)
- Rule application order

### Query Patterns

```sql
-- Component catalog (48 canonical types)
SELECT canonical_name, category, behavioral_description
FROM component_type_catalog ORDER BY category, canonical_name;

-- Classification results for a screen
SELECT sci.canonical_type, sci.confidence, sci.classification_source, n.name
FROM screen_component_instances sci
JOIN nodes n ON sci.node_id = n.id
WHERE sci.screen_id = ? ORDER BY n.sort_order;

-- Screen skeleton
SELECT skeleton_notation, skeleton_type FROM screen_skeletons WHERE screen_id = ?;

-- Classification accuracy summary
SELECT classification_source, COUNT(*), ROUND(AVG(confidence), 2)
FROM screen_component_instances GROUP BY classification_source;

-- Flagged for review (vision disagreements)
SELECT sci.*, n.name FROM screen_component_instances sci
JOIN nodes n ON sci.node_id = n.id
WHERE sci.flagged_for_review = 1;
```

### Conjure (Future)

Composing new screens from prompts using the token/component vocabulary + IR.
