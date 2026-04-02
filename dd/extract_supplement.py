"""Supplemental extraction for Plugin API-only properties.

Generates compact JS that collects layoutPositioning, componentKey, and Grid
properties for all nodes on a screen. These fields are not available in the
REST API and require the Plugin API (Desktop Bridge).

Output format: {figma_node_id: {lp: "ABSOLUTE", ck: "abc123", gr: 3, gc: 4, ...}}
"""

import json
import sqlite3
from typing import Any, Dict, List


def generate_supplement_script(screen_node_ids: List[str]) -> str:
    """Generate JS to collect Plugin API-only properties for multiple screens.

    Uses getNodeByIdAsync and walks the tree collecting only the fields
    that the REST API doesn't provide: layoutPositioning, mainComponent.key,
    and Grid layout properties.
    """
    ids_json = json.dumps(screen_node_ids)

    return f'''
const screenIds = {ids_json};
const result = {{}};

async function walkNode(node) {{
  const entry = {{}};

  if ('layoutPositioning' in node && node.layoutPositioning !== 'AUTO') {{
    entry.lp = node.layoutPositioning;
  }}

  if (node.type === 'INSTANCE') {{
    try {{
      const main = await node.getMainComponentAsync();
      if (main) entry.ck = main.key;
    }} catch (e) {{}}
  }}

  if (node.layoutMode === 'GRID') {{
    if ('gridRowCount' in node) entry.gr = node.gridRowCount;
    if ('gridColumnCount' in node) entry.gc = node.gridColumnCount;
    if ('gridRowGap' in node) entry.grg = node.gridRowGap;
    if ('gridColumnGap' in node) entry.gcg = node.gridColumnGap;
    if ('gridRowSizes' in node) entry.grs = node.gridRowSizes;
    if ('gridColumnSizes' in node) entry.gcs = node.gridColumnSizes;
  }}

  if (Object.keys(entry).length > 0) {{
    result[node.id] = entry;
  }}

  if ('children' in node) {{
    for (const child of node.children) {{
      await walkNode(child);
    }}
  }}
}}

for (const sid of screenIds) {{
  const screen = await figma.getNodeByIdAsync(sid);
  if (screen) {{
    await walkNode(screen);
  }}
}}

return result;
'''


def apply_supplement(conn: sqlite3.Connection, supplement_data: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    """Apply supplemental data to the nodes table.

    Updates layout_positioning, component_key, and Grid properties from
    the compact format returned by the supplement script.
    """
    positioning_count = 0
    component_key_count = 0
    grid_count = 0

    for figma_node_id, fields in supplement_data.items():
        updates = {}

        if "lp" in fields:
            updates["layout_positioning"] = fields["lp"]
            positioning_count += 1

        if "ck" in fields:
            updates["component_key"] = fields["ck"]
            component_key_count += 1

        if "gr" in fields:
            updates["grid_row_count"] = fields["gr"]
            grid_count += 1
        if "gc" in fields:
            updates["grid_column_count"] = fields["gc"]
        if "grg" in fields:
            updates["grid_row_gap"] = fields["grg"]
        if "gcg" in fields:
            updates["grid_column_gap"] = fields["gcg"]
        if "grs" in fields:
            updates["grid_row_sizes"] = json.dumps(fields["grs"]) if isinstance(fields["grs"], list) else fields["grs"]
        if "gcs" in fields:
            updates["grid_column_sizes"] = json.dumps(fields["gcs"]) if isinstance(fields["gcs"], list) else fields["gcs"]

        if not updates:
            continue

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [figma_node_id]

        conn.execute(
            f"UPDATE nodes SET {set_clause} WHERE figma_node_id = ?",
            values,
        )

    conn.commit()

    return {
        "layout_positioning": positioning_count,
        "component_key": component_key_count,
        "grid": grid_count,
        "total_nodes_updated": len(supplement_data),
    }
