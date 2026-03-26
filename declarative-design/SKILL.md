# Declarative Design Companion Skill

**Version**: 0.1.0
**Skill Name**: declarative-design
**Description**: AI assistant for working with Declarative Design databases - extracting, curating, and exporting design tokens and component systems.
**Activation**: When encountering `*.declarative.db` files or when asked to work with design systems, tokens, or component libraries.

## DB Discovery

To find and connect to a Declarative Design database:

```python
import sqlite3
import os
from pathlib import Path

# Find DB files matching pattern
db_files = list(Path('.').glob('**/*.declarative.db'))
if not db_files:
    print("No Declarative Design DB found")
    exit(1)

# Connect to the first DB found
db_path = str(db_files[0])
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Initial health check
cursor = conn.execute("SELECT * FROM v_curation_progress")
progress = cursor.fetchone()
print(f"DB: {db_path}")
print(f"Extraction: {progress['total_nodes']} nodes, {progress['total_screens']} screens")
print(f"Curation: {progress['bound_pct']:.1f}% bound, {progress['curated_pct']:.1f}% curated")

# Get screen overview
cursor = conn.execute("SELECT * FROM v_screen_summary ORDER BY name")
for screen in cursor:
    print(f"  {screen['name']}: {screen['component_count']} components")
```

## Schema Overview

The database is organized into 4 table groups:

### System Tables (Design vocabulary)
- `files` - Figma file metadata (file_key, name, url, extraction timestamps)
- `tokens` - Design tokens (name, type, tier, collection, mode values)
- `token_values` - Per-mode token values (token_id, mode_name, value)
- `components` - Component definitions (name, category, key, node_id)
- `component_variants` - Variant combinations (component_id, name, properties)
- `variant_axes` - Variant dimensions (component_id, axis_name, values, is_interaction)
- `component_slots` - Component properties (slot_name, slot_type, is_required)
- `component_a11y` - Accessibility metadata (role, min_touch_target, keyboard_nav)

### Composition Tables (How things are assembled)
- `screens` - Top-level screens/pages (name, node_id, file_id)
- `nodes` - Full node tree (path, name, node_type, layout_mode, dimensions)
- `node_token_bindings` - Token-to-node associations (node_id, token_id, property, binding_status)

### Mapping Tables (Cross-tool references)
- `figma_variables` - Figma variable IDs for round-tripping
- `code_mappings` - Framework-specific component names

### Operation Tables (Pipeline state)
- `extraction_log` - Extraction history with timestamps
- `curation_log` - Curation operation audit trail
- `validation_results` - Export readiness checks
- `export_log` - Export operation history

## View Catalog

Views are organized by workflow phase:

### Extraction Phase
- `v_color_census` - Unique colors with usage counts (pre-clustering)
- `v_type_census` - Unique typography combinations (pre-clustering)
- `v_spacing_census` - Unique spacing values (pre-clustering)
- `v_radius_census` - Unique border radius values
- `v_effect_census` - Unique shadow/blur effects

### Clustering Phase
- `v_color_census_by_mode` - Mode-aware color analysis (post-clustering)
- `v_unbound` - Bindings without assigned tokens (curation candidates)
- `v_token_coverage` - Tokens with binding/node/screen usage metrics

### Curation Phase
- `v_curation_progress` - Overall binding status breakdown (key health metric)
- `v_resolved_tokens` - Follows alias chains to final values

### Component Analysis
- `v_component_catalog` - Full component overview with slots/a11y/variants
- `v_interaction_states` - Components with hover/focus/active/disabled states
- `v_screen_summary` - Screen metadata with composition metrics

### Export Phase
- `v_export_readiness` - Validation results summary (pre-export check)
- `v_drift_report` - Tokens out of sync with Figma

## Query Patterns

### 1. Get all color tokens for code generation
Use when generating CSS, Tailwind config, or component styles:

```sql
SELECT t.name, vrt.resolved_value, vrt.mode_name
FROM v_resolved_tokens vrt
JOIN tokens t ON vrt.id = t.id
WHERE t.type = 'color' AND t.tier IN ('curated', 'aliased')
ORDER BY t.name, vrt.mode_name;
```

### 2. Get a screen's full composition tree
Use when rebuilding a specific screen or page:

```sql
-- First get screen metadata
SELECT * FROM v_screen_summary WHERE name LIKE '%Settings%';

-- Then get full tree with bindings
SELECT n.path, n.name, n.node_type, n.is_semantic,
       n.layout_mode, n.width, n.height,
       ntb.property, ntb.resolved_value, t.name AS token_name
FROM nodes n
LEFT JOIN node_token_bindings ntb ON ntb.node_id = n.id AND ntb.binding_status = 'bound'
LEFT JOIN tokens t ON ntb.token_id = t.id
WHERE n.screen_id = ?
ORDER BY n.path;
```

### 3. Get all components with their interaction states
Use when instantiating components or building component docs:

```sql
SELECT c.name, c.category, c.composition_hint,
       va.axis_name, va.axis_values, va.default_value,
       cs.name AS slot_name, cs.slot_type, cs.is_required,
       ca.role, ca.min_touch_target
FROM components c
LEFT JOIN variant_axes va ON va.component_id = c.id
LEFT JOIN component_slots cs ON cs.component_id = c.id
LEFT JOIN component_a11y ca ON ca.component_id = c.id
WHERE c.file_id = ?
ORDER BY c.category, c.name, va.axis_name;
```

### 4. Find all hover states across all components
Use when applying consistent hover behavior:

```sql
SELECT c.name AS component_name, cv.name AS variant_name, cv.properties
FROM variant_dimension_values vdv
JOIN variant_axes va ON vdv.axis_id = va.id
JOIN component_variants cv ON vdv.variant_id = cv.id
JOIN components c ON cv.component_id = c.id
WHERE va.is_interaction = 1 AND vdv.value = 'hover';
```

### 5. Get all tokens with usage counts
Use to identify most/least used tokens:

```sql
SELECT * FROM v_token_coverage WHERE binding_count > 0;
```

### 6. Pipeline status dashboard
Use for overall system health check:

```sql
SELECT * FROM v_curation_progress;
```

### 7. All descendants of a container node
Use to query subtrees (materialized path pattern):

```sql
SELECT * FROM nodes WHERE path LIKE '0.3.%' AND screen_id = ?
ORDER BY path;
```

### 8. Find design inconsistencies
Use to identify one-off values that should be tokens:

```sql
SELECT resolved_value, property, COUNT(*) as usage
FROM node_token_bindings
WHERE binding_status = 'unbound'
GROUP BY resolved_value, property
HAVING COUNT(*) = 1
ORDER BY property;
```

### 9. Drift check
Use after Figma changes to detect out-of-sync tokens:

```sql
SELECT * FROM v_drift_report;
```

### 10. Export readiness check
Use before any export operation:

```sql
SELECT * FROM v_export_readiness;
```

## Token Resolution

Tokens can reference other tokens via aliases. Always use `v_resolved_tokens` to get final values:

```sql
-- Get resolved value following alias chain
SELECT id, name, type, mode_name, resolved_value
FROM v_resolved_tokens
WHERE name = 'color.button.primary.bg';

-- Get all tokens for a specific mode
SELECT * FROM v_resolved_tokens
WHERE mode_name = 'dark'
ORDER BY type, name;
```

**Rule**: Never hardcode a value that has a token. Always query for the token value.

Multi-mode example:
```sql
-- A button background might have different values per mode
SELECT mode_name, resolved_value
FROM v_resolved_tokens
WHERE name = 'color.button.primary.bg'
ORDER BY mode_name;
-- Returns: light=#0066CC, dark=#4488FF
```

## Component Catalog

Query components and their capabilities:

```sql
-- Overview of all components
SELECT * FROM v_component_catalog
ORDER BY category, name;

-- Detailed component with variants
SELECT c.name, c.category, c.composition_hint,
       cv.name as variant_name, cv.properties
FROM components c
LEFT JOIN component_variants cv ON c.id = cv.component_id
WHERE c.name = 'Button';

-- Component slots (props)
SELECT cs.name, cs.slot_type, cs.is_required, cs.default_value
FROM component_slots cs
JOIN components c ON cs.component_id = c.id
WHERE c.name = 'Card';

-- Component accessibility
SELECT ca.role, ca.label_required, ca.min_touch_target,
       ca.keyboard_nav, ca.contrast_ratio
FROM component_a11y ca
JOIN components c ON ca.component_id = c.id
WHERE c.name = 'Button';
```

Use `composition_hint` field for structural guidance when instantiating components.

## Screen Composition

To reconstruct a screen with proper token bindings:

```python
import sqlite3

def reconstruct_screen(conn: sqlite3.Connection, screen_name: str):
    # Get screen ID
    cursor = conn.execute(
        "SELECT id, name FROM screens WHERE name LIKE ?",
        (f'%{screen_name}%',)
    )
    screen = cursor.fetchone()

    # Get full node tree
    cursor = conn.execute("""
        SELECT n.path, n.name, n.node_type, n.is_semantic,
               n.layout_mode, n.layout_align, n.layout_gap,
               n.padding_top, n.padding_right, n.padding_bottom, n.padding_left,
               n.width, n.height, n.min_width, n.max_width,
               ntb.property, t.name AS token_name, vrt.resolved_value
        FROM nodes n
        LEFT JOIN node_token_bindings ntb ON n.id = ntb.node_id
        LEFT JOIN tokens t ON ntb.token_id = t.id
        LEFT JOIN v_resolved_tokens vrt ON t.id = vrt.id AND vrt.mode_name = 'light'
        WHERE n.screen_id = ?
        ORDER BY n.path
    """, (screen['id'],))

    # Build tree structure using path
    tree = {}
    for node in cursor:
        path = node['path']
        tree[path] = {
            'name': node['name'],
            'type': node['node_type'],
            'layout': node['layout_mode'],
            'tokens': {}
        }
        if node['token_name']:
            tree[path]['tokens'][node['property']] = {
                'token': node['token_name'],
                'value': node['resolved_value']
            }

    return tree
```

Materialized paths (e.g., '0.1.2.3') represent tree position. To get all children of node '0.1':
```sql
SELECT * FROM nodes WHERE path LIKE '0.1.%' AND screen_id = ?;
```

## Curation Assistance Workflow

Walk users through token curation step-by-step:

### Step 1: Review extraction status
```sql
SELECT * FROM v_curation_progress;
```

### Step 2: Review proposed tokens (clustering output)
```sql
-- Low confidence bindings needing review
SELECT ntb.id, n.name as node_name, ntb.property,
       ntb.resolved_value, t.name as proposed_token,
       ntb.confidence_score
FROM node_token_bindings ntb
JOIN nodes n ON ntb.node_id = n.id
LEFT JOIN tokens t ON ntb.token_id = t.id
WHERE ntb.binding_status = 'proposed'
  AND ntb.confidence_score < 0.8
ORDER BY ntb.confidence_score;
```

### Step 3: Review orphan values
```sql
-- Values that didn't match any token
SELECT * FROM v_unbound
ORDER BY property, resolved_value;
```

### Available curation operations:

```python
from dd.curate import (
    accept_token,      # Accept proposed token binding
    rename_token,      # Rename to DTCG convention
    merge_tokens,      # Combine similar tokens
    split_token,       # Split multi-use token
    reject_token,      # Remove incorrect token
    create_alias,      # Create token alias
    accept_all        # Bulk accept high-confidence
)

# Accept a proposed binding
result = accept_token(conn, token_id=123)

# Rename to proper DTCG format
result = rename_token(conn, token_id=123, new_name="color.background.primary")

# Merge duplicate tokens
result = merge_tokens(
    conn,
    survivor_id=123,  # Token to keep
    victim_id=456,    # Token to merge into survivor
    new_name="color.text.primary"  # Optional rename
)

# Split overloaded token
result = split_token(
    conn,
    token_id=123,
    new_name="color.border.default",
    node_ids=[45, 67, 89]  # Nodes to rebind to new token
)

# Reject incorrect proposal
result = reject_token(
    conn,
    token_id=123,
    cascade=True  # Also unbind from nodes
)

# Create semantic alias
result = create_alias(
    conn,
    alias_name="color.danger",
    target_token_id=123,
    collection="semantic"
)

# Bulk accept high-confidence proposals
from dd.curate import accept_all
result = accept_all(conn, file_id=1)
```

## Export Orchestration

### Pre-Export Validation

Always check readiness first:

```sql
SELECT * FROM v_export_readiness;
```

If validation fails, check specific issues:
```python
from dd.validate import validate_export
report = validate_export(conn)
for check, status in report['checks'].items():
    if not status['passed']:
        print(f"❌ {check}: {status['message']}")
```

### Export Path 1: Figma Variables

Generate and push design tokens to Figma:

```python
from dd.export_figma_vars import export_figma_variables

# Generate payload for figma_setup_design_tokens
payload = export_figma_variables(conn, file_id=1)

# Use Console MCP to create in Figma
# Tool: figma_setup_design_tokens
# Input: payload['collections'][0]

# Write back the created IDs
from dd.export_figma_vars import write_back_variable_ids
write_back_variable_ids(conn, created_variables)
```

### Export Path 2: Figma Rebinding

Update existing Figma file with new token bindings:

```python
from dd.export_rebind import generate_rebinding_script

# Generate rebinding script
script = generate_rebinding_script(conn, file_id=1)

# Execute via Console MCP
# Tool: figma_execute
# Input: { "code": script }

# Verify with audit
# Tool: figma_audit_design_system
```

### Export Path 3: CSS Custom Properties

```python
from dd.export_css import export_css

# Generate CSS with custom properties
css_output = export_css(conn, file_id=1)

# Write to file
with open('tokens.css', 'w') as f:
    f.write(css_output)
```

### Export Path 4: Tailwind Config

```python
from dd.export_tailwind import export_tailwind_config

# Generate Tailwind theme extension
config = export_tailwind_config(conn, file_id=1)

# Write to file
with open('tailwind.tokens.js', 'w') as f:
    f.write(config)
```

### Export Path 5: W3C DTCG Format

```python
from dd.export_dtcg import export_dtcg

# Generate tokens.json
tokens_json = export_dtcg(conn, file_id=1)

# Write to file
import json
with open('tokens.json', 'w') as f:
    json.dump(tokens_json, f, indent=2)
```

## Drift Detection

Detect when Figma has changed since last extraction:

```python
from dd.drift import detect_drift

# Run drift detection
drift_report = detect_drift(conn)

# Review in DB
cursor = conn.execute("SELECT * FROM v_drift_report")
for issue in cursor:
    print(f"{issue['status']}: {issue['token_name']} - {issue['message']}")

# Re-extract if needed
from dd.extract import extract_all
if drift_report['has_drift']:
    print("Re-extracting from Figma...")
    extract_all(figma_file_url, output_db_path)
```

Resolution options:
- **Re-extract**: Pull fresh data from Figma (destructive to curation work)
- **Force push**: Overwrite Figma with DB values (authoritative DB)
- **Reconcile**: Manually review and merge changes

## MCP Tool Mapping

### Official Figma MCP (`@figma/mcp`)
- `use_figma` - Primary extraction tool for all Figma data

### Figma Console MCP (`figma-console`)
- `figma_setup_design_tokens` - Create variable collections with tokens
- `figma_batch_create_variables` - Bulk variable creation (faster)
- `figma_batch_update_variables` - Bulk variable updates (faster)
- `figma_execute` - Run rebinding scripts
- `figma_get_variables` - Read existing variables for drift detection
- `figma_audit_design_system` - Verify export success
- `figma_get_styles` - Extract legacy styles if needed

### No MCP Required (DB operations)
- All query operations
- Curation operations
- CSS/Tailwind/DTCG export
- Validation checks

## Disconnected Mode

### Works without Figma connection:
- Database queries (all views and tables)
- Token curation operations
- CSS export
- Tailwind export
- DTCG tokens.json export
- Validation checks
- Progress monitoring

### Requires Figma MCP connection:
- Initial extraction (`use_figma`)
- Figma variable creation (`figma_setup_design_tokens`)
- Rebinding script execution (`figma_execute`)
- Drift detection against live file (`figma_get_variables`)
- Design system audit (`figma_audit_design_system`)
- Re-extraction after changes

## Constraints

### Token Naming Conventions
- **Format**: DTCG dot-notation (`color.background.primary`)
- **Regex**: `^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*$`
- **Reserved prefixes**: `color.`, `typography.`, `spacing.`, `radius.`, `effect.`
- **Semantic layer**: `semantic.` prefix for aliases

### Binding Property Paths
- **Format**: Figma property paths (`fills[0].color`, `effects[0].radius`)
- **Supported properties**: fills, strokes, effects, spacing, typography, width, height

### Mode Completeness Rules
- All tokens in a collection must have values for all modes
- Cannot have partial mode coverage
- Default mode must always have a value

### Limits
- **Alias depth**: Maximum 3 levels of aliasing
- **Batch size**: 100 tokens per figma_batch_create_variables call
- **Variable name length**: 64 characters max
- **Collection name length**: 40 characters max

## Python Module Map

### Extraction Phase
```python
from dd.extract import extract_all  # Full pipeline
from dd.extract_inventory import extract_design_inventory  # Tokens/styles
from dd.extract_components import extract_components  # Component library
from dd.extract_screens import extract_screens  # Screen compositions
from dd.extract_bindings import extract_token_bindings  # Node-token links
```

### Clustering Phase
```python
from dd.cluster import cluster_all  # Run all clustering
from dd.cluster_colors import cluster_colors  # Color clustering
from dd.cluster_typography import cluster_typography  # Type clustering
from dd.cluster_spacing import cluster_spacing  # Spacing clustering
from dd.cluster_misc import cluster_misc  # Radius/effects clustering
```

### Curation Phase
```python
from dd.curate import (
    accept_token,
    rename_token,
    merge_tokens,
    split_token,
    reject_token,
    create_alias,
    accept_all
)
```

### Export Phase
```python
from dd.export_figma_vars import export_figma_variables, write_back_variable_ids
from dd.export_rebind import generate_rebinding_script
from dd.export_css import export_css
from dd.export_tailwind import export_tailwind_config
from dd.export_dtcg import export_dtcg
```

### Utilities
```python
from dd.db import ensure_schema, get_or_create_file
from dd.validate import validate_export
from dd.drift import detect_drift
from dd.status import print_status
from dd.paths import parse_property_path
from dd.normalize import normalize_token_name
```

## Quick Start Workflow

1. **Discover DB**: Find `*.declarative.db` file
2. **Check health**: Run `v_curation_progress` query
3. **If low curation %**: Run curation workflow
4. **If high curation %**: Check `v_export_readiness`
5. **If export ready**: Choose export format and run
6. **If not ready**: Review validation failures
7. **For code generation**: Query `v_resolved_tokens` and `v_component_catalog`
8. **For screen building**: Query screen composition tree
9. **After Figma changes**: Run drift detection

## Common Patterns

### Generate component with proper tokens
```python
# Get component definition
component = conn.execute("""
    SELECT * FROM v_component_catalog WHERE name = 'Button'
""").fetchone()

# Get token values for current mode
tokens = conn.execute("""
    SELECT name, resolved_value
    FROM v_resolved_tokens
    WHERE name LIKE 'color.button.%' AND mode_name = 'light'
""").fetchall()

# Generate code with tokens, not hardcoded values
```

### Build screen from composition
```python
# Get screen structure
nodes = conn.execute("""
    SELECT n.*, t.name as token_name, vrt.resolved_value
    FROM nodes n
    LEFT JOIN node_token_bindings ntb ON n.id = ntb.node_id
    LEFT JOIN tokens t ON ntb.token_id = t.id
    LEFT JOIN v_resolved_tokens vrt ON t.id = vrt.id
    WHERE n.screen_id = ? AND vrt.mode_name = ?
    ORDER BY n.path
""", (screen_id, mode)).fetchall()

# Reconstruct tree using paths
```

### Check token usage
```python
# Find unused tokens (candidates for deletion)
unused = conn.execute("""
    SELECT * FROM v_token_coverage
    WHERE binding_count = 0 AND tier = 'curated'
""").fetchall()

# Find most used tokens (core system tokens)
popular = conn.execute("""
    SELECT * FROM v_token_coverage
    ORDER BY binding_count DESC LIMIT 20
""").fetchall()
```

## Error Handling

Common issues and solutions:

- **No DB found**: Create DB via extraction pipeline first
- **Low curation %**: Run clustering, then curation workflow
- **Export validation failed**: Check specific validation rules, fix issues
- **Drift detected**: Re-extract or force push depending on authoritative source
- **Token name invalid**: Must match DTCG regex pattern
- **Alias loop**: Check alias chain depth, max 3 levels
- **Mode mismatch**: Ensure all tokens have all mode values

## Version History

- **0.1.0**: Initial companion skill for Declarative Design DB