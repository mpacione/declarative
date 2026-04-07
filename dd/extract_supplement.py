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

from dd.property_registry import PROPERTIES, by_db_column, by_figma_name, overrideable_properties


def _build_override_js_checks() -> str:
    """Generate JS code that extracts all overrideable properties.

    Driven by the property registry — no ad-hoc field checks.
    Each property with override_fields gets a check in the JS loop.
    """
    lines = []
    seen_fields: set[str] = set()

    for prop in overrideable_properties():
        figma_name = prop.figma_name
        short_key = prop.db_column or figma_name

        # Build the overriddenFields condition
        field_checks = []
        for field_name in prop.override_fields:
            if field_name not in seen_fields:
                field_checks.append(f"ov.overriddenFields.includes('{field_name}')")
                seen_fields.add(field_name)
            else:
                field_checks.append(f"ov.overriddenFields.includes('{field_name}')")

        if not field_checks:
            continue

        condition = " || ".join(field_checks)

        # Determine how to read the value
        if prop.value_type == "json_array":
            read_expr = f"JSON.stringify(child.{figma_name})"
            guard = f"try {{ o.{short_key} = {read_expr}; }} catch (e) {{}}"
        elif prop.value_type == "boolean":
            read_expr = f"child.{figma_name}"
            guard = f"o.{short_key} = {read_expr};"
        elif prop.figma_name == "characters":
            # Text requires type check
            read_expr = f"child.characters"
            guard = f"if (child.type === 'TEXT') o.{short_key} = {read_expr};"
        elif prop.figma_name == "fontFamily":
            # fontName is an object {family, style}
            read_expr = "child.fontName"
            guard = f"if (child.fontName && child.fontName !== figma.mixed) o.font_family = child.fontName.family;"
        else:
            read_expr = f"child.{figma_name}"
            guard = f"o.{short_key} = {read_expr};"

        lines.append(f"        if ({condition}) {{ {guard} }}")

    return "\n".join(lines)


def generate_supplement_script(screen_node_ids: list[str]) -> str:
    """Generate JS to collect Plugin API-only properties for multiple screens.

    Uses getNodeByIdAsync and walks the tree collecting only the fields
    that the REST API doesn't provide: layoutPositioning, mainComponent.key,
    and Grid layout properties. Override extraction is driven by the
    property registry for comprehensive coverage.
    """
    ids_json = json.dumps(screen_node_ids)
    override_checks = _build_override_js_checks()

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

    // Extract overrides — registry-driven, checks all overrideable properties
    if (node.overrides && node.overrides.length > 0) {{
      const ovs = [];
      for (const ov of node.overrides) {{
        const isSelf = ov.id === node.id;
        const child = isSelf ? node : node.findOne(n => n.id === ov.id);
        if (!child) continue;

        const cid = isSelf ? ':self' : (ov.id.includes(';') ? ov.id.substring(ov.id.indexOf(';')) : ov.id);
        const o = {{ cid, f: ov.overriddenFields, t: child.type }};

{override_checks}

        // Instance swap detection
        if (child.type === 'INSTANCE' && ov.overriddenFields.some(f => f === 'fills' || f === 'fillStyleId')) {{
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

  // Gradient enrichment: capture gradientTransform from Plugin API fills.
  // The REST API stores gradientHandlePositions (3 points). The Plugin API
  // provides gradientTransform (2x3 matrix). Both representations are needed:
  // different renderers prefer different formats. The supplement ENRICHES the
  // existing fills column — it preserves REST API fields while adding Plugin
  // API fields. ORDERING: supplement must run AFTER REST extraction.
  // If REST extraction re-runs after supplement, the enrichment is lost.
  if (node.fills && node.fills.length > 0) {{
    const gts = [];
    for (let i = 0; i < node.fills.length; i++) {{
      const f = node.fills[i];
      if (f.gradientTransform) {{
        gts.push({{ fillIndex: i, gradientTransform: f.gradientTransform }});
      }}
    }}
    if (gts.length > 0) entry.gt = gts;
  }}

  // textAutoResize: Plugin API-only field for TEXT nodes.
  // The REST API does not return this field. Without it, the renderer
  // defaults to WIDTH_AND_HEIGHT which causes text to resize incorrectly.
  if (node.type === 'TEXT' && node.textAutoResize) {{
    entry.tar = node.textAutoResize;
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


# Mapping from compact override keys → (property_type, property_name_suffix)
# Built from registry: db_column → override_type
_OVERRIDE_KEY_MAP: dict[str, tuple[str, str]] = {}
for _prop in PROPERTIES:
    if _prop.override_type and _prop.db_column:
        # Special cases for existing naming conventions
        if _prop.override_type == "TEXT":
            _OVERRIDE_KEY_MAP["text_content"] = ("TEXT", "")
        elif _prop.override_type == "BOOLEAN":
            _OVERRIDE_KEY_MAP["visible"] = ("BOOLEAN", ":visible")
        elif _prop.override_type == "FILLS":
            _OVERRIDE_KEY_MAP["fills"] = ("FILLS", ":fills")
        elif _prop.override_type == "WIDTH":
            _OVERRIDE_KEY_MAP["width"] = ("WIDTH", ":width")
        elif _prop.override_type == "HEIGHT":
            _OVERRIDE_KEY_MAP["height"] = ("HEIGHT", ":height")
        elif _prop.override_type == "OPACITY":
            _OVERRIDE_KEY_MAP["opacity"] = ("OPACITY", ":opacity")
        elif _prop.override_type == "LAYOUT_SIZING_H":
            _OVERRIDE_KEY_MAP["layout_sizing_h"] = ("LAYOUT_SIZING_H", ":layoutSizingH")
        elif _prop.override_type == "LAYOUT_SIZING_V":
            _OVERRIDE_KEY_MAP["layout_sizing_v"] = ("LAYOUT_SIZING_V", ":layoutSizingV")
        elif _prop.override_type == "ITEM_SPACING":
            _OVERRIDE_KEY_MAP["item_spacing"] = ("ITEM_SPACING", ":itemSpacing")
        else:
            # Generic: use db_column as key, override_type as type
            suffix = f":{_prop.figma_name}"
            _OVERRIDE_KEY_MAP[_prop.db_column] = (_prop.override_type, suffix)

# Also register properties without explicit override_type but with override_fields
# These use a generic pattern: db_column → (db_column.upper(), :figmaName)
for _prop in PROPERTIES:
    if _prop.override_fields and _prop.db_column and _prop.db_column not in _OVERRIDE_KEY_MAP:
        _OVERRIDE_KEY_MAP[_prop.db_column] = (
            _prop.db_column.upper(),
            f":{_prop.figma_name}",
        )


# Reverse mapping: property_type → (suffix, figma_name)
# Built from _OVERRIDE_KEY_MAP for use by query-time decomposition.
_TYPE_TO_SUFFIX: dict[str, tuple[str, str]] = {}
for _db_col, (_ov_type, _suffix) in _OVERRIDE_KEY_MAP.items():
    # Find the figma_name for this db_column
    _prop = by_db_column(_db_col) if _db_col != "text_content" else by_figma_name("characters")
    _figma = _prop.figma_name if _prop else _db_col
    _TYPE_TO_SUFFIX[_ov_type] = (_suffix, _figma)
# INSTANCE_SWAP is special — no suffix, not from registry
_TYPE_TO_SUFFIX["INSTANCE_SWAP"] = ("", "instance_swap")


def override_suffix_for_type(property_type: str) -> tuple[str, str]:
    """Return (suffix, figma_property_name) for a given override type.

    Uses the same data source as extraction (_OVERRIDE_KEY_MAP) —
    no second list to maintain.
    """
    return _TYPE_TO_SUFFIX.get(property_type, ("", property_type))


def apply_supplement(conn: sqlite3.Connection, supplement_data: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Apply supplemental data to the nodes table and instance_overrides table.

    Updates layout_positioning, component_key, Grid properties, and
    instance overrides from the compact format returned by the supplement script.
    Registry-driven: stores any override property the registry defines.
    """
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

        # textAutoResize: Plugin API-only field for TEXT nodes.
        # REST API does not return this. Stored as text_auto_resize column.
        if "tar" in fields:
            updates["text_auto_resize"] = fields["tar"]

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [figma_node_id]
            conn.execute(
                f"UPDATE nodes SET {set_clause} WHERE figma_node_id = ?",
                values,
            )

        # Gradient enrichment: merge Plugin API gradientTransform into existing
        # fills JSON. This ENRICHES — it preserves all existing fields (including
        # REST API gradientHandlePositions) and adds gradientTransform alongside.
        # ORDERING: This must run after REST extraction. If REST extraction
        # re-runs after supplement, the enrichment is lost and supplement must
        # re-run to restore it.
        if "gt" in fields:
            row = conn.execute(
                "SELECT fills FROM nodes WHERE figma_node_id = ?",
                (figma_node_id,),
            ).fetchone()
            if row and row[0]:
                try:
                    existing_fills = json.loads(row[0])
                    for gt_entry in fields["gt"]:
                        idx = gt_entry["fillIndex"]
                        if 0 <= idx < len(existing_fills):
                            existing_fills[idx]["gradientTransform"] = gt_entry["gradientTransform"]
                    conn.execute(
                        "UPDATE nodes SET fills = ? WHERE figma_node_id = ?",
                        (json.dumps(existing_fills), figma_node_id),
                    )
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

        # Instance overrides — registry-driven storage
        if "ov" in fields:
            node_row = conn.execute(
                "SELECT id FROM nodes WHERE figma_node_id = ?", (figma_node_id,)
            ).fetchone()
            if node_row:
                node_id = node_row[0]
                for ov in fields["ov"]:
                    child_id = ov["cid"]

                    # Instance swap (special — not a property override)
                    if "swapId" in ov:
                        conn.execute(
                            "INSERT OR REPLACE INTO instance_overrides "
                            "(node_id, property_type, property_name, override_value) "
                            "VALUES (?, 'INSTANCE_SWAP', ?, ?)",
                            (node_id, child_id, ov["swapId"]),
                        )
                        override_count += 1

                    # Registry-driven: store any property the registry defines
                    for db_col, (prop_type, suffix) in _OVERRIDE_KEY_MAP.items():
                        if db_col in ov:
                            value = ov[db_col]
                            if isinstance(value, bool):
                                value = json.dumps(value)
                            elif not isinstance(value, str):
                                value = str(value)
                            prop_name = f"{child_id}{suffix}" if suffix else child_id
                            conn.execute(
                                "INSERT OR REPLACE INTO instance_overrides "
                                "(node_id, property_type, property_name, override_value) "
                                "VALUES (?, ?, ?, ?)",
                                (node_id, prop_type, prop_name, value),
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
