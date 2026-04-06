"""Supplemental extraction for Plugin API-only properties.

Generates compact JS that collects layoutPositioning, componentKey, and Grid
properties for all nodes on a screen. These fields are not available in the
REST API and require the Plugin API (Desktop Bridge).

Output format: {figma_node_id: {lp: "ABSOLUTE", ck: "abc123", gr: 3, gc: 4, ...}}

Usage:
    from dd.extract_supplement import run_supplement
    result = run_supplement(conn, execute_fn)

Where execute_fn(js_string) -> dict executes JS in Figma's plugin context
and returns the result. This can be figma_execute MCP, PROXY_EXECUTE WebSocket,
or any other execution mechanism.
"""

import json
import sqlite3
import time
from collections.abc import Callable
from typing import Any


def generate_supplement_script(screen_node_ids: list[str]) -> str:
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

    // Extract overrides (child node mutations + self-overrides)
    if (node.overrides && node.overrides.length > 0) {{
      const ovs = [];
      for (const ov of node.overrides) {{
        // Self-override: override ID matches the node itself
        const isSelf = ov.id === node.id;
        const child = isSelf ? node : node.findOne(n => n.id === ov.id);
        if (!child) continue;

        const cid = isSelf ? ':self' : (ov.id.includes(';') ? ov.id.substring(ov.id.indexOf(';')) : ov.id);
        const o = {{ cid, f: ov.overriddenFields, t: child.type }};

        if (ov.overriddenFields.includes('characters') && child.type === 'TEXT') {{
          o.chars = child.characters;
        }}
        if (ov.overriddenFields.includes('visible')) {{
          o.vis = child.visible;
        }}
        if (ov.overriddenFields.includes('fills')) {{
          try {{ o.fills = JSON.stringify(child.fills); }} catch (e) {{}}
        }}
        if (ov.overriddenFields.includes('width')) {{
          o.w = child.width;
        }}
        if (ov.overriddenFields.includes('height')) {{
          o.h = child.height;
        }}
        if (ov.overriddenFields.includes('opacity')) {{
          o.op = child.opacity;
        }}
        if (ov.overriddenFields.includes('layoutSizingHorizontal') || ov.overriddenFields.includes('primaryAxisSizingMode')) {{
          o.lsh = child.layoutSizingHorizontal;
        }}
        if (ov.overriddenFields.includes('layoutSizingVertical') || ov.overriddenFields.includes('counterAxisSizingMode')) {{
          o.lsv = child.layoutSizingVertical;
        }}
        if (child.type === 'INSTANCE' && ov.overriddenFields.some(f => f === 'fills' || f === 'fillStyleId')) {{
          // Possible instance swap — check main component
          try {{
            const childMain = await child.getMainComponentAsync();
            if (childMain) o.swapId = childMain.id;
          }} catch (e) {{}}
        }}
        ovs.push(o);
      }}
      if (ovs.length > 0) entry.ov = ovs;
    }}
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


def apply_supplement(conn: sqlite3.Connection, supplement_data: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Apply supplemental data to the nodes table and instance_overrides table.

    Updates layout_positioning, component_key, Grid properties, and
    instance overrides from the compact format returned by the supplement script.
    """
    # Ensure instance_overrides table exists (may not if DB predates schema addition)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS instance_overrides ("
        "id INTEGER PRIMARY KEY, "
        "node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE, "
        "property_type TEXT NOT NULL, "
        "property_name TEXT NOT NULL, "
        "override_value TEXT, "
        "UNIQUE(node_id, property_name))"
    )

    positioning_count = 0
    component_key_count = 0
    grid_count = 0
    override_count = 0

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

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [figma_node_id]
            conn.execute(
                f"UPDATE nodes SET {set_clause} WHERE figma_node_id = ?",
                values,
            )

        # Instance overrides: child node mutations (text, visibility, instance swap)
        if "ov" in fields:
            node_row = conn.execute(
                "SELECT id FROM nodes WHERE figma_node_id = ?", (figma_node_id,)
            ).fetchone()
            if node_row:
                node_id = node_row[0]
                for ov in fields["ov"]:
                    child_id = ov["cid"]
                    child_type = ov.get("t", "UNKNOWN")

                    if "chars" in ov:
                        conn.execute(
                            "INSERT OR REPLACE INTO instance_overrides "
                            "(node_id, property_type, property_name, override_value) "
                            "VALUES (?, 'TEXT', ?, ?)",
                            (node_id, child_id, ov["chars"]),
                        )
                        override_count += 1

                    if "vis" in ov:
                        conn.execute(
                            "INSERT OR REPLACE INTO instance_overrides "
                            "(node_id, property_type, property_name, override_value) "
                            "VALUES (?, 'BOOLEAN', ?, ?)",
                            (node_id, f"{child_id}:visible", json.dumps(ov["vis"])),
                        )
                        override_count += 1

                    if "swapId" in ov:
                        conn.execute(
                            "INSERT OR REPLACE INTO instance_overrides "
                            "(node_id, property_type, property_name, override_value) "
                            "VALUES (?, 'INSTANCE_SWAP', ?, ?)",
                            (node_id, child_id, ov["swapId"]),
                        )
                        override_count += 1

                    if "fills" in ov:
                        conn.execute(
                            "INSERT OR REPLACE INTO instance_overrides "
                            "(node_id, property_type, property_name, override_value) "
                            "VALUES (?, 'FILLS', ?, ?)",
                            (node_id, f"{child_id}:fills", ov["fills"]),
                        )
                        override_count += 1

                    if "w" in ov:
                        conn.execute(
                            "INSERT OR REPLACE INTO instance_overrides "
                            "(node_id, property_type, property_name, override_value) "
                            "VALUES (?, 'WIDTH', ?, ?)",
                            (node_id, f"{child_id}:width", str(ov["w"])),
                        )
                        override_count += 1

                    if "h" in ov:
                        conn.execute(
                            "INSERT OR REPLACE INTO instance_overrides "
                            "(node_id, property_type, property_name, override_value) "
                            "VALUES (?, 'HEIGHT', ?, ?)",
                            (node_id, f"{child_id}:height", str(ov["h"])),
                        )
                        override_count += 1

                    if "op" in ov:
                        conn.execute(
                            "INSERT OR REPLACE INTO instance_overrides "
                            "(node_id, property_type, property_name, override_value) "
                            "VALUES (?, 'OPACITY', ?, ?)",
                            (node_id, f"{child_id}:opacity", str(ov["op"])),
                        )
                        override_count += 1

                    if "lsh" in ov:
                        conn.execute(
                            "INSERT OR REPLACE INTO instance_overrides "
                            "(node_id, property_type, property_name, override_value) "
                            "VALUES (?, 'LAYOUT_SIZING_H', ?, ?)",
                            (node_id, f"{child_id}:layoutSizingH", ov["lsh"]),
                        )
                        override_count += 1

                    if "lsv" in ov:
                        conn.execute(
                            "INSERT OR REPLACE INTO instance_overrides "
                            "(node_id, property_type, property_name, override_value) "
                            "VALUES (?, 'LAYOUT_SIZING_V', ?, ?)",
                            (node_id, f"{child_id}:layoutSizingV", ov["lsv"]),
                        )
                        override_count += 1

    conn.commit()

    return {
        "layout_positioning": positioning_count,
        "component_key": component_key_count,
        "grid": grid_count,
        "overrides": override_count,
        "total_nodes_updated": len(supplement_data),
    }


def run_supplement(
    conn: sqlite3.Connection,
    execute_fn: Callable[[str], dict[str, Any]],
    batch_size: int = 5,
    delay: float = 0.3,
    screen_type: str = "app_screen",
) -> dict[str, Any]:
    """Run supplemental extraction on all screens of the given type.

    Auto-batches screens, retries failed batches at batch_size=1,
    and tracks progress. The execute_fn should accept a JS string
    and return the result dict (or raise on failure).

    Args:
        conn: Database connection
        execute_fn: Callable that executes JS in Figma plugin context.
            Takes a JS string, returns the result dict from evaluation.
            Should raise on execution failure.
        batch_size: Screens per batch (reduced automatically on truncation)
        delay: Seconds between batches
        screen_type: Only process screens of this type

    Returns:
        Summary dict with counts of updated nodes and properties.
    """
    screens = conn.execute(
        "SELECT figma_node_id, name FROM screens WHERE screen_type = ? ORDER BY id",
        (screen_type,),
    ).fetchall()
    screen_ids = [r[0] for r in screens]

    if not screen_ids:
        return {"total_nodes": 0, "component_key": 0, "layout_positioning": 0, "grid": 0, "batches": 0, "failed": 0}

    total_nodes = 0
    total_ck = 0
    total_lp = 0
    total_grid = 0
    batches_run = 0
    failed_screens: list[str] = []

    i = 0
    while i < len(screen_ids):
        batch = screen_ids[i:i + batch_size]
        script = generate_supplement_script(batch)

        try:
            result = execute_fn(script)

            if not isinstance(result, dict):
                raise ValueError(f"Expected dict, got {type(result)}")

            counts = apply_supplement(conn, result)
            total_nodes += counts["total_nodes_updated"]
            total_ck += counts["component_key"]
            total_lp += counts["layout_positioning"]
            total_grid += counts["grid"]
            batches_run += 1
            i += batch_size

        except Exception as e:
            error_msg = str(e)

            if "Unterminated string" in error_msg or "65536" in error_msg or "65533" in error_msg:
                if batch_size > 1 and len(batch) > 1:
                    batch_size = max(1, batch_size // 2)
                    continue

            if len(batch) == 1:
                failed_screens.append(batch[0])
                i += 1
            else:
                for sid in batch:
                    try:
                        single_script = generate_supplement_script([sid])
                        single_result = execute_fn(single_script)
                        if isinstance(single_result, dict):
                            counts = apply_supplement(conn, single_result)
                            total_nodes += counts["total_nodes_updated"]
                            total_ck += counts["component_key"]
                            total_lp += counts["layout_positioning"]
                            total_grid += counts["grid"]
                            batches_run += 1
                    except Exception:
                        failed_screens.append(sid)
                    time.sleep(delay)
                i += len(batch)

        if delay > 0:
            time.sleep(delay)

    return {
        "total_nodes": total_nodes,
        "component_key": total_ck,
        "layout_positioning": total_lp,
        "grid": total_grid,
        "batches": batches_run,
        "failed": len(failed_screens),
        "failed_screens": failed_screens,
    }
