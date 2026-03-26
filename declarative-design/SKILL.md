# Declarative Design Companion Skill

**Version**: 0.2.0
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
# Update the token value directly
conn.execute(
    "UPDATE token_values SET resolved_value = ?, raw_value = ? WHERE token_id = ?",
    ("37", "37", token_id)
)
conn.commit()
```

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
    accept_token,      # Accept a single proposed token
    rename_token,      # Rename to DTCG convention (validates format)
    merge_tokens,      # Combine two tokens (rebinds all nodes)
    split_token,       # Split one token into two (moves specific nodes)
    reject_token,      # Remove a token (optionally unbinds nodes)
    create_alias,      # Create semantic alias → primitive
    accept_all,        # Bulk accept all proposed tokens
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

### Figma Variable Push (Agent + MCP)
```python
from dd.export_figma_vars import export_figma_variables

payload = export_figma_variables(conn, file_id=1)
# Then use figma_setup_design_tokens MCP tool with payload
```

### Figma Rebinding (Agent + MCP)
```python
from dd.export_rebind import generate_rebinding_script

script = generate_rebinding_script(conn, file_id=1)
# Then use figma_execute MCP tool with script
```

## Disconnected Mode

**Works without Figma:** All DB queries, curation, validation, CSS/Tailwind/DTCG export.

**Requires Figma PAT:** Extraction (`dd extract`).

**Requires Figma MCP:** Variable push, rebinding, drift detection against live file.

## Conjure (Future)

Composing new screens from prompts using the token/component vocabulary in the DB. The agent queries components, tokens, and screen patterns from the DB, then uses Figma MCP tools to compose the screen using real tokens — no hardcoded values.

```sql
-- Get available components
SELECT * FROM v_component_catalog ORDER BY category, name;

-- Get tokens for a specific mode
SELECT t.name, tv.resolved_value
FROM tokens t
JOIN token_values tv ON t.id = tv.token_id
JOIN token_modes tm ON tv.mode_id = tm.id
WHERE tm.name = 'light' AND t.tier IN ('curated', 'aliased')
ORDER BY t.type, t.name;
```
