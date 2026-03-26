# Verify Pipeline — Real Figma File

Paste this entire prompt into Claude Code to run the full Declarative Design pipeline against a real Figma file.

Replace `FILE_KEY` and `FILE_NAME` below with your actual Figma file details.

---

## Instructions for Claude

Run the Declarative Design pipeline end-to-end against a real Figma file. Follow these steps exactly, in order. Report results after each step.

### Configuration

```
FILE_KEY = "REPLACE_WITH_YOUR_FIGMA_FILE_KEY"
FILE_NAME = "REPLACE_WITH_YOUR_FILE_NAME"
DB_NAME = "REPLACE_WITH_SHORT_NAME"
```

Extract the file key from your Figma URL: `https://figma.com/design/<FILE_KEY>/...`

### Prerequisites

Before starting, verify:
1. The Figma MCP tools are available (figma_get_file_data, use_figma, figma_get_variables, figma_setup_design_tokens)
2. The venv is activated: `source build/.venv/bin/activate`
3. The dd package imports: `python3 -c "from dd.db import init_db"`

---

### Step 1: Initialize the database

```python
import sys
sys.path.insert(0, '.')

from dd.db import init_db
from dd.config import db_path

DB_PATH = str(db_path(DB_NAME))
conn = init_db(DB_PATH)

# Verify schema loaded
cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
table_count = cursor.fetchone()[0]
print(f"Database initialized at {DB_PATH} with {table_count} tables")
```

Report: DB path and table count.

---

### Step 2: Get file structure from Figma

Use the Figma MCP to get the file's top-level frames:

```python
# Call figma_get_file_data or get_metadata MCP tool for the file
# Extract the list of top-level frames (pages → frames)
```

You need to build a `frames` list in this format:

```python
frames = [
    {"id": "123:456", "name": "Home", "type": "FRAME"},
    {"id": "123:789", "name": "Settings", "type": "FRAME"},
    # ... one entry per top-level frame in the file
]
```

Use `figma_get_file_data` with `depth=1` and `verbosity="summary"` to get node IDs and names.
Filter to FRAME and COMPONENT type nodes at the top level of each page.

Report: Number of frames found, their names.

---

### Step 3: Run extraction

```python
from dd.extract import run_extraction_pipeline

def extract_fn(js_script):
    """Callback that executes a JS script in Figma via MCP and returns the result."""
    # Call use_figma MCP tool with:
    #   fileKey = FILE_KEY
    #   code = js_script
    #   description = "Extract node tree"
    # Return the result (should be a list of node dicts)
    result = <call use_figma here>
    return result

def component_extract_fn(js_script):
    """Same as extract_fn but for component extraction."""
    result = <call use_figma here>
    return result

summary = run_extraction_pipeline(
    conn=conn,
    file_key=FILE_KEY,
    file_name=FILE_NAME,
    frames=frames,
    extract_fn=extract_fn,
    component_extract_fn=component_extract_fn,
)

print(f"Extraction complete: {summary}")
```

Report: Total screens, nodes extracted, bindings created, components found.

---

### Step 4: Verify extraction with queries

```python
# Screen count
screens = conn.execute("SELECT COUNT(*) as c FROM screens").fetchone()
print(f"Screens: {screens['c']}")

# Node count
nodes = conn.execute("SELECT COUNT(*) as c FROM nodes").fetchone()
print(f"Nodes: {nodes['c']}")

# Binding count
bindings = conn.execute("SELECT COUNT(*) as c FROM node_token_bindings").fetchone()
print(f"Bindings: {bindings['c']}")

# Component count
components = conn.execute("SELECT COUNT(*) as c FROM components").fetchone()
print(f"Components: {components['c']}")

# Sample of what was extracted
print("\n--- Sample screens ---")
for row in conn.execute("SELECT name, device_class FROM screens LIMIT 10"):
    print(f"  {row['name']} ({row['device_class']})")

print("\n--- Binding property distribution ---")
for row in conn.execute("""
    SELECT property, COUNT(*) as cnt
    FROM node_token_bindings
    GROUP BY property ORDER BY cnt DESC LIMIT 15
"""):
    print(f"  {row['property']}: {row['cnt']}")
```

Report: Counts and property distribution.

---

### Step 5: Run clustering

```python
from dd.cluster import run_clustering

cluster_summary = run_clustering(conn, file_id=1)
print(f"Clustering complete: {cluster_summary}")

# Check what was proposed
print("\n--- Tokens by collection ---")
for row in conn.execute("""
    SELECT tc.name as collection, COUNT(*) as cnt
    FROM tokens t
    JOIN token_collections tc ON t.collection_id = tc.id
    GROUP BY tc.name ORDER BY cnt DESC
"""):
    print(f"  {row['collection']}: {row['cnt']} tokens")

# Sample token names
print("\n--- Sample proposed tokens ---")
for row in conn.execute("SELECT name, type, tier FROM tokens LIMIT 20"):
    print(f"  {row['name']} ({row['type']}, {row['tier']})")
```

Report: Token counts by collection, sample names.

---

### Step 6: Curate — accept all tokens

```python
from dd.curate import accept_all

accept_result = accept_all(conn, file_id=1)
print(f"Accepted: {accept_result}")

# Verify curation progress
progress = conn.execute("SELECT * FROM v_curation_progress").fetchone()
print(f"\nCuration progress:")
print(f"  Total bindings: {progress['total_bindings']}")
print(f"  Bound: {progress['bound_count']} ({progress['bound_pct']:.1f}%)")
print(f"  Proposed: {progress['proposed_count']}")
print(f"  Unbound: {progress['unbound_count']}")
```

Report: Acceptance counts and curation percentages.

---

### Step 7: Validate

```python
from dd.validate import run_validation, is_export_ready

passed = run_validation(conn)
ready = is_export_ready(conn)

print(f"Validation passed: {passed}")
print(f"Export ready: {ready}")

# Show any issues
if not passed:
    for row in conn.execute("""
        SELECT check_name, severity, message
        FROM export_validations
        WHERE severity = 'error'
        ORDER BY check_name
        LIMIT 20
    """):
        print(f"  [{row['severity']}] {row['check_name']}: {row['message']}")
```

If validation fails with naming errors, fix them:

```python
from dd.curate import rename_token
# Rename any tokens with invalid DTCG names
# e.g., rename_token(conn, token_id=X, new_name="color.surface.primary")
```

Report: Pass/fail, any issues found, whether export-ready.

---

### Step 8: Export to code

```python
from dd.export_css import export_css
from dd.export_tailwind import export_tailwind
from dd.export_dtcg import export_dtcg

css = export_css(conn)
tailwind = export_tailwind(conn)
dtcg = export_dtcg(conn)

# Write to files
from pathlib import Path

output_dir = Path("exports")
output_dir.mkdir(exist_ok=True)

(output_dir / "tokens.css").write_text(css)
(output_dir / "tailwind.theme.js").write_text(tailwind)
(output_dir / "tokens.json").write_text(dtcg)

print(f"CSS: {len(css)} chars → exports/tokens.css")
print(f"Tailwind: {len(tailwind)} chars → exports/tailwind.theme.js")
print(f"DTCG: {len(dtcg)} chars → exports/tokens.json")

# Show a sample of the CSS output
print("\n--- CSS preview (first 500 chars) ---")
print(css[:500])
```

Report: File sizes, preview of CSS output.

---

### Step 9: Export to Figma (optional — creates real Figma variables)

**This step writes to your Figma file.** Only proceed if you want real variables created.

```python
from dd.export_figma_vars import generate_variable_payloads_checked

payloads = generate_variable_payloads_checked(conn, file_id=1)
print(f"Generated {len(payloads)} payload batch(es)")

for i, payload in enumerate(payloads):
    print(f"  Batch {i+1}: {payload['collectionName']} — "
          f"{len(payload['modes'])} mode(s), {len(payload['tokens'])} tokens")

# Execute each payload via MCP
for payload in payloads:
    # Call figma_setup_design_tokens MCP tool with:
    #   collectionName = payload["collectionName"]
    #   modes = payload["modes"]
    #   tokens = payload["tokens"]
    pass  # Replace with actual MCP call

# After creating variables, write back the Figma variable IDs
from dd.export_figma_vars import writeback_variable_ids_from_response

# Call figma_get_variables MCP tool to get the created variables
# figma_response = <call figma_get_variables here>
# writeback = writeback_variable_ids_from_response(conn, file_id=1, raw_response=figma_response)
# print(f"Writeback: {writeback}")
```

Report: Payload batch counts, collection names, variable counts.

---

### Step 10: Status report

```python
from dd.status import format_status_report, get_status_dict

report = format_status_report(conn)
print(report)

status = get_status_dict(conn)
print(f"\nReady for export: {status.get('ready', False)}")
```

Report: Full status output.

---

### Step 11: Drift detection (optional — only after Step 9)

```python
from dd.drift import detect_drift

# Call figma_get_variables MCP tool
# figma_response = <call figma_get_variables here>
# result = detect_drift(conn, file_id=1, figma_variables_response=figma_response)
# print(result["report"])
```

Report: Synced/drifted/pending counts.

---

## Expected Results

After a successful run you should see:
- Screens extracted with device classification (mobile/tablet/desktop/component_sheet)
- Hundreds to thousands of nodes with 40+ properties each
- Bindings for fills, strokes, typography, spacing, radius, effects, opacity
- Clustered tokens for colors, type scale, spacing scale, radius, shadows
- 80%+ binding coverage after accept_all
- Valid CSS, Tailwind, and DTCG exports
- Figma variables created (if Step 9 was run)

## Troubleshooting

**"No pending screens"** — Extraction already ran. Delete the DB and start over, or check `extraction_runs` table.

**Validation fails with naming errors** — Clustering may produce camelCase names. Rename them: `rename_token(conn, token_id=X, new_name="lower.case.name")`

**"RuntimeError: validation has errors"** on export — Run step 7 to see what's wrong, fix it, then re-export.

**use_figma returns empty list** — The extraction script may have timed out. Check that the Figma file is open and the MCP bridge is connected.
