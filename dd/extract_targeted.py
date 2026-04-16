"""Targeted re-extraction for specific properties.

Generates compact JS that walks all nodes on a set of screens and collects
only the specified properties. Used when new columns are added to the schema
after initial extraction — avoids full re-extraction.

Usage:
    python -m dd.extract_targeted --db Dank-EXP-02.declarative.db --port 9223
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from typing import Any


def generate_targeted_script(screen_node_ids: list[str]) -> str:
    """Generate JS to collect is_mask, boolean_operation, corner_smoothing, arc_data."""
    ids_json = json.dumps(screen_node_ids)

    return f'''
const screenIds = {ids_json};
const result = {{}};

async function walkNode(node) {{
  const entry = {{}};

  if ('isMask' in node && node.isMask) {{
    entry.m = 1;
  }}

  if (node.type === 'BOOLEAN_OPERATION' && node.booleanOperation) {{
    entry.bo = node.booleanOperation;
  }}

  if ('cornerSmoothing' in node && node.cornerSmoothing > 0) {{
    entry.cs = node.cornerSmoothing;
  }}

  if (node.type === 'ELLIPSE' && node.arcData) {{
    entry.ad = node.arcData;
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


def generate_vector_geometry_script(screen_node_ids: list[str]) -> str:
    """Generate JS to collect fillGeometry and strokeGeometry from vector-type nodes."""
    ids_json = json.dumps(screen_node_ids)

    return f'''
const screenIds = {ids_json};
const result = {{}};
const VECTOR_TYPES = new Set(['VECTOR','BOOLEAN_OPERATION','ELLIPSE','LINE','STAR','REGULAR_POLYGON']);

function safeRead(node, prop) {{
  try {{ const v = node[prop]; return v === undefined ? undefined : v; }}
  catch(e) {{ return undefined; }}
}}

async function walkNode(node) {{
  if (VECTOR_TYPES.has(node.type)) {{
    const entry = {{}};
    const fg = safeRead(node, 'fillGeometry');
    if (fg?.length) entry.fg = fg;
    const sg = safeRead(node, 'strokeGeometry');
    if (sg?.length) entry.sg = sg;
    if (Object.keys(entry).length > 0) {{
      result[node.id] = entry;
    }}
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


def generate_sizing_script(screen_node_ids: list[str]) -> str:
    """Generate JS to collect layoutSizingH/V, textAutoResize, and text properties.

    These properties were missed by the original extraction due to the
    'prop in node' bug (non-enumerable properties). safeRead captures them.
    """
    ids_json = json.dumps(screen_node_ids)

    return f'''
const screenIds = {ids_json};
const result = {{}};

function safeRead(node, prop) {{
  try {{ const v = node[prop]; return v === undefined ? undefined : v; }}
  catch(e) {{ return undefined; }}
}}

function safeReadNoMixed(node, prop) {{
  const v = safeRead(node, prop);
  return v === figma.mixed ? undefined : v;
}}

async function walkNode(node) {{
  const entry = {{}};

  // Layout sizing — always readable for nodes inside auto-layout parents
  const lsh = safeRead(node, 'layoutSizingHorizontal');
  if (lsh !== undefined) entry.lsh = lsh;
  const lsv = safeRead(node, 'layoutSizingVertical');
  if (lsv !== undefined) entry.lsv = lsv;

  // Text properties that were missed
  if (node.type === 'TEXT') {{
    const tar = safeRead(node, 'textAutoResize');
    if (tar !== undefined) entry.tar = tar;
    const fs = safeReadNoMixed(node, 'fontName');
    if (fs && fs.style) entry.fst = fs.style;
    const tc = safeReadNoMixed(node, 'textCase');
    if (tc !== undefined && tc !== 'ORIGINAL') entry.tc = tc;
    const td = safeReadNoMixed(node, 'textDecoration');
    if (td !== undefined && td !== 'NONE') entry.td = td;
    const ps = safeReadNoMixed(node, 'paragraphSpacing');
    if (ps !== undefined && ps > 0) entry.ps = ps;
  }}

  // Layout wrap
  const lw = safeRead(node, 'layoutWrap');
  if (lw !== undefined) entry.lw = lw;

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


def apply_sizing(conn: sqlite3.Connection, data: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Apply sizing/text re-extraction results to the nodes table."""
    counts: dict[str, int] = {
        "layout_sizing_h": 0, "layout_sizing_v": 0, "text_auto_resize": 0,
        "font_style": 0, "text_case": 0, "text_decoration": 0,
        "paragraph_spacing": 0, "layout_wrap": 0, "total_nodes_updated": 0,
    }

    field_map = {
        "lsh": "layout_sizing_h",
        "lsv": "layout_sizing_v",
        "tar": "text_auto_resize",
        "fst": "font_style",
        "tc": "text_case",
        "td": "text_decoration",
        "ps": "paragraph_spacing",
        "lw": "layout_wrap",
    }

    for figma_node_id, fields in data.items():
        updates: dict[str, Any] = {}

        for short_key, db_col in field_map.items():
            if short_key in fields:
                updates[db_col] = fields[short_key]
                counts[db_col] = counts.get(db_col, 0) + 1

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [figma_node_id]
            conn.execute(
                f"UPDATE nodes SET {set_clause} WHERE figma_node_id = ?",
                values,
            )
            counts["total_nodes_updated"] += 1

    conn.commit()
    return counts


def apply_vector_geometry(conn: sqlite3.Connection, data: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Apply vector geometry extraction results to the nodes table."""
    fill_count = 0
    stroke_count = 0

    for figma_node_id, fields in data.items():
        updates: dict[str, Any] = {}

        if "fg" in fields:
            updates["fill_geometry"] = json.dumps(fields["fg"])
            fill_count += 1

        if "sg" in fields:
            updates["stroke_geometry"] = json.dumps(fields["sg"])
            stroke_count += 1

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [figma_node_id]
            conn.execute(
                f"UPDATE nodes SET {set_clause} WHERE figma_node_id = ?",
                values,
            )

    conn.commit()

    return {
        "fill_geometry": fill_count,
        "stroke_geometry": stroke_count,
        "total_nodes_updated": len(data),
    }


def apply_targeted(conn: sqlite3.Connection, data: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Apply targeted extraction results to the nodes table."""
    mask_count = 0
    boolean_op_count = 0
    corner_smooth_count = 0
    arc_data_count = 0

    for figma_node_id, fields in data.items():
        updates: dict[str, Any] = {}

        if "m" in fields:
            updates["is_mask"] = fields["m"]
            mask_count += 1

        if "bo" in fields:
            updates["boolean_operation"] = fields["bo"]
            boolean_op_count += 1

        if "cs" in fields:
            updates["corner_smoothing"] = fields["cs"]
            corner_smooth_count += 1

        if "ad" in fields:
            ad = fields["ad"]
            updates["arc_data"] = json.dumps(ad) if isinstance(ad, dict) else str(ad)
            arc_data_count += 1

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [figma_node_id]
            conn.execute(
                f"UPDATE nodes SET {set_clause} WHERE figma_node_id = ?",
                values,
            )

    conn.commit()

    return {
        "is_mask": mask_count,
        "boolean_operation": boolean_op_count,
        "corner_smoothing": corner_smooth_count,
        "arc_data": arc_data_count,
        "total_nodes_updated": len(data),
    }


def generate_transforms_script(screen_node_ids: list[str]) -> str:
    """Generate JS to collect Plugin API ground truth:
    - relativeTransform (2x3 matrix, encodes rotation + mirror + position)
    - local width/height (Plugin API returns local dims; REST returns AABB)
    - styledTextSegments with OpenType features

    The local width/height and relativeTransform together are sufficient
    to reconstruct any node's layout — the REST API's absoluteBoundingBox
    (stored in width/height columns during initial extraction) is wrong
    for any node inside a rotated ancestor chain.
    """
    ids_json = json.dumps(screen_node_ids)

    return f'''
const screenIds = {ids_json};
const result = {{}};

function safeRead(node, prop) {{
  try {{ const v = node[prop]; return v === undefined ? undefined : v; }}
  catch(e) {{ return undefined; }}
}}

async function walkNode(node) {{
  const entry = {{}};

  // Local width/height from Plugin API. node.width/height are LOCAL
  // dimensions (what the user drew). REST API's absoluteBoundingBox
  // is the world-axis projection of a rotated rect, which inflates
  // dimensions when the node sits inside a rotated ancestor.
  const w = safeRead(node, 'width');
  const h = safeRead(node, 'height');
  if (typeof w === 'number') entry.w = w;
  if (typeof h === 'number') entry.h = h;

  // relativeTransform encodes rotation + mirror + parent-relative position.
  // Capture for every node so the renderer can use it uniformly rather
  // than reconstructing from scalar rotation + x/y.
  const rt = safeRead(node, 'relativeTransform');
  if (rt && rt[0] && rt[1]) {{
    entry.rt = [[rt[0][0], rt[0][1], rt[0][2]], [rt[1][0], rt[1][1], rt[1][2]]];
  }}

  // OpenType features per styled text segment
  if (node.type === 'TEXT') {{
    try {{
      const segs = node.getStyledTextSegments(['openTypeFeatures']);
      const otSegs = [];
      for (const seg of segs) {{
        const feats = seg.openTypeFeatures;
        if (feats && Object.keys(feats).length > 0) {{
          otSegs.push({{ s: seg.start, e: seg.end, f: feats }});
        }}
      }}
      if (otSegs.length > 0) entry.ot = otSegs;
    }} catch(e) {{}}
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


def apply_transforms(conn: sqlite3.Connection, data: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Apply relativeTransform, local width/height, and OpenType features
    to the nodes table. Overwrites width/height with Plugin API local
    values (the REST-extracted absoluteBoundingBox values are wrong for
    nodes inside rotated ancestors)."""
    rt_count = 0
    ot_count = 0
    wh_count = 0

    for figma_node_id, fields in data.items():
        updates: dict[str, Any] = {}

        if "rt" in fields:
            updates["relative_transform"] = json.dumps(fields["rt"])
            rt_count += 1

        if "ot" in fields:
            updates["opentype_features"] = json.dumps(fields["ot"])
            ot_count += 1

        # Overwrite width/height with Plugin API local values.
        # The initial REST extraction stored absoluteBoundingBox here,
        # which is wrong for rotated-subtree nodes.
        if "w" in fields:
            updates["width"] = fields["w"]
        if "h" in fields:
            updates["height"] = fields["h"]
        if "w" in fields or "h" in fields:
            wh_count += 1

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [figma_node_id]
            conn.execute(
                f"UPDATE nodes SET {set_clause} WHERE figma_node_id = ?",
                values,
            )

    conn.commit()

    return {
        "relative_transform": rt_count,
        "opentype_features": ot_count,
        "width_height": wh_count,
        "total_nodes_updated": max(rt_count, ot_count, wh_count),
    }


def run_targeted(
    conn: sqlite3.Connection,
    execute_fn: Any,
    batch_size: int = 10,
    delay: float = 0.3,
    mode: str = "properties",
) -> dict[str, Any]:
    """Run targeted extraction on all app_screen screens.

    mode: "properties" for is_mask/boolean_operation/etc.,
          "vector-geometry" for fillGeometry/strokeGeometry.
    """
    screens = conn.execute(
        "SELECT figma_node_id, name FROM screens WHERE screen_type = 'app_screen' ORDER BY id",
    ).fetchall()
    screen_ids = [r[0] for r in screens]

    if not screen_ids:
        return {"total_nodes": 0, "batches": 0, "failed": 0}

    if mode == "vector-geometry":
        script_fn = generate_vector_geometry_script
        apply_fn = apply_vector_geometry
        totals: dict[str, int] = {"fill_geometry": 0, "stroke_geometry": 0, "total_nodes_updated": 0}
    elif mode == "sizing":
        script_fn = generate_sizing_script
        apply_fn = apply_sizing
        totals = {
            "layout_sizing_h": 0, "layout_sizing_v": 0, "text_auto_resize": 0,
            "font_style": 0, "text_case": 0, "text_decoration": 0,
            "paragraph_spacing": 0, "layout_wrap": 0, "total_nodes_updated": 0,
        }
    elif mode == "transforms":
        script_fn = generate_transforms_script
        apply_fn = apply_transforms
        totals = {"relative_transform": 0, "opentype_features": 0, "width_height": 0, "total_nodes_updated": 0}
    else:
        script_fn = generate_targeted_script
        apply_fn = apply_targeted
        totals = {"is_mask": 0, "boolean_operation": 0, "corner_smoothing": 0, "arc_data": 0, "total_nodes_updated": 0}

    batches_run = 0
    failed_screens: list[str] = []

    i = 0
    while i < len(screen_ids):
        batch = screen_ids[i:i + batch_size]
        script = script_fn(batch)

        try:
            result = execute_fn(script)

            if not isinstance(result, dict):
                raise ValueError(f"Expected dict, got {type(result)}")

            counts = apply_fn(conn, result)
            for key in totals:
                totals[key] += counts.get(key, 0)
            batches_run += 1
            print(f"  Batch {batches_run}: {len(batch)} screens, {counts['total_nodes_updated']} nodes")
            i += len(batch)

        except Exception as e:
            error_msg = str(e)
            print(f"  Batch failed: {error_msg[:100]}")

            if "Unterminated string" in error_msg or "65536" in error_msg:
                if batch_size > 1:
                    batch_size = max(1, batch_size // 2)
                    print(f"  Reducing batch size to {batch_size}")
                    continue

            if len(batch) == 1:
                failed_screens.append(batch[0])
                i += 1
            else:
                for j, sid in enumerate(batch):
                    try:
                        single_script = script_fn([sid])
                        single_result = execute_fn(single_script)
                        if isinstance(single_result, dict):
                            counts = apply_fn(conn, single_result)
                            for key in totals:
                                totals[key] += counts.get(key, 0)
                            batches_run += 1
                    except Exception:
                        failed_screens.append(sid)
                    time.sleep(delay)
                i += len(batch)

        if delay > 0:
            time.sleep(delay)

    return {
        **totals,
        "batches": batches_run,
        "failed": len(failed_screens),
        "failed_screens": failed_screens,
        "screens_processed": len(screen_ids),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Targeted property re-extraction")
    parser.add_argument("--db", required=True, help="Path to .declarative.db")
    parser.add_argument("--port", type=int, default=9223, help="WebSocket port")
    parser.add_argument("--batch", type=int, default=10, help="Screens per batch")
    parser.add_argument("--mode", choices=["properties", "vector-geometry", "sizing"], default="properties",
                        help="Extraction mode: properties (is_mask etc.), vector-geometry, or sizing (layoutSizingH/V, textAutoResize, etc.)")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    def make_execute_fn(port: int):
        """Create an execute function using PROXY_EXECUTE WebSocket."""
        import subprocess
        import os

        node_path = os.environ.get(
            "NODE_PATH",
            os.path.expanduser("~/.npm/_npx/b547afed9fcf6dcb/node_modules"),
        )

        def execute(code: str) -> dict:
            runner_js = f'''
const WebSocket = require('ws');
const code = {json.dumps(code)};

const ws = new WebSocket('ws://[::1]:{port}');
const timeout = setTimeout(() => {{ process.stderr.write('Timeout'); process.exit(1); }}, 60000);

ws.on('open', () => {{
  ws.send(JSON.stringify({{ type: 'PROXY_EXECUTE', id: 'targeted', code, timeout: 55000 }}));
}});

ws.on('message', (data) => {{
  const msg = JSON.parse(data);
  if (msg.type === 'PROXY_EXECUTE_RESULT' && msg.id === 'targeted') {{
    clearTimeout(timeout);
    ws.close();
    if (msg.error) {{
      process.stderr.write(msg.error);
      process.exit(1);
    }}
    process.stdout.write(JSON.stringify(msg.result));
  }}
}});

ws.on('error', (err) => {{
  process.stderr.write(err.message);
  process.exit(1);
}});
'''
            result = subprocess.run(
                ["node", "-e", runner_js],
                capture_output=True,
                text=True,
                timeout=65,
                env={**os.environ, "NODE_PATH": node_path},
            )

            if result.returncode != 0:
                raise RuntimeError(f"Node execution failed: {result.stderr[:200]}")

            raw = json.loads(result.stdout)

            # PROXY_EXECUTE wraps in {success: true, result: <actual>}
            if isinstance(raw, dict) and "success" in raw and "result" in raw:
                raw = raw["result"]

            return raw

        return execute

    execute_fn = make_execute_fn(args.port)

    print(f"Starting {args.mode} extraction on {args.db}")
    print(f"WebSocket port: {args.port}, batch size: {args.batch}")

    summary = run_targeted(conn, execute_fn, batch_size=args.batch, mode=args.mode)

    print(f"\n=== Summary ===")
    print(f"Screens processed: {summary['screens_processed']}")
    print(f"Total nodes updated: {summary['total_nodes_updated']}")
    if args.mode == "vector-geometry":
        print(f"  fill_geometry: {summary['fill_geometry']}")
        print(f"  stroke_geometry: {summary['stroke_geometry']}")
    elif args.mode == "sizing":
        print(f"  layout_sizing_h: {summary['layout_sizing_h']}")
        print(f"  layout_sizing_v: {summary['layout_sizing_v']}")
        print(f"  text_auto_resize: {summary['text_auto_resize']}")
        print(f"  font_style: {summary['font_style']}")
        print(f"  text_case: {summary['text_case']}")
        print(f"  text_decoration: {summary['text_decoration']}")
        print(f"  paragraph_spacing: {summary['paragraph_spacing']}")
        print(f"  layout_wrap: {summary['layout_wrap']}")
    else:
        print(f"  is_mask: {summary['is_mask']}")
        print(f"  boolean_operation: {summary['boolean_operation']}")
        print(f"  corner_smoothing: {summary['corner_smoothing']}")
        print(f"  arc_data: {summary['arc_data']}")
    print(f"Batches: {summary['batches']}")
    print(f"Failed screens: {summary['failed']}")

    if args.mode == "vector-geometry" and summary["total_nodes_updated"] > 0:
        from dd.extract_assets import process_vector_geometry
        print(f"\nPost-processing: converting geometry to content-addressed assets...")
        asset_count = process_vector_geometry(conn)
        print(f"  Created/linked {asset_count} vector assets")

    conn.close()
