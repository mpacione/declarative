"""Unified Plugin-API extraction pass.

Consolidates the five separate walks (supplement + four targeted modes)
into a single tree traversal that collects every Plugin-API-only field
in one WebSocket round-trip per batch.

Performance story (pt 6):
- 5 passes, 5 WebSockets, 5 Node subprocesses per batch  →  1 of each.
- ~5x redundant tree traversal inside the plugin  →  1.
- getMainComponentAsync per INSTANCE eliminated (handled by REST
  components map at ingest; see dd/figma_api.py:_add_component_reference).

The walker still supports an opt-in ``collect_component_key`` flag for
the rare case where the REST map didn't populate the key (e.g. detached
remote instance from a library the current user doesn't have access to).

This module does NOT delete ``extract_supplement.py`` or
``extract_targeted.py``. Those remain callable for incremental
re-extraction after a schema change — their narrower scope avoids
re-fetching data you don't need to refresh.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from dd.extract_supplement import (
    _build_override_js_checks,
    apply_supplement,
    _OVERRIDE_KEY_MAP,
)
from dd.extract_targeted import (
    apply_sizing,
    apply_targeted,
    apply_transforms,
    apply_vector_geometry,
)


# Slice categories. "light" = small per-node payload (flags, small strings).
# "heavy" = large per-node payload (relativeTransform for every node,
# vectorPaths and geometries for vector types). Splitting these prevents
# hitting the ~64KB PROXY_EXECUTE result-buffer limit on moderate-sized
# screens when everything goes through a single walker.
SLICE_LIGHT = "light"
SLICE_HEAVY = "heavy"
SLICE_ALL = "all"


def generate_plugin_script(
    screen_node_ids: list[str],
    *,
    collect_component_key: bool = False,
    slice: str = SLICE_ALL,
) -> str:
    """Generate a single JS walker that collects every Plugin-only field.

    The returned object has shape::

        {
          "<figma_node_id>": {
            # supplement slice
            lp, ck, gr, gc, grg, gcg, grs, gcs, gt, ov, tar,

            # properties slice
            m, bo, cs, ad,

            # sizing slice
            lsh, lsv, fst, tc, td, ps, lw,

            # transforms slice
            w, h, rt, vp, ot,

            # vector-geometry slice
            fg, sg,
          },
          ...
        }

    Keys are namespace-scoped to their former pass so existing ``apply_*``
    functions can be reused unchanged — the output is a superset of what
    each pass used to emit, and the dispatchers just pick the keys they
    recognize.

    ``collect_component_key``: when True, fall back to
    ``getMainComponentAsync()`` per INSTANCE. Default False because REST
    now populates ``component_key`` at ingest time (100% parity verified
    on Dank Experimental).
    """
    ids_json = json.dumps(screen_node_ids)
    override_checks = _build_override_js_checks()
    ck_block = (
        """
    try {
      const main = await node.getMainComponentAsync();
      if (main) entry.ck = main.key;
    } catch (e) {}
"""
        if collect_component_key
        else ""
    )

    want_light = slice in (SLICE_LIGHT, SLICE_ALL)
    want_heavy = slice in (SLICE_HEAVY, SLICE_ALL)

    # Each block is a self-contained JS fragment that reads from `node` and
    # writes into `entry`. We compose the body based on the requested slice
    # so that "light" and "heavy" runs fit under the PROXY_EXECUTE result
    # buffer on moderate-sized screens.
    light_block = """
  // ---- sizing slice (layoutSizingH/V + typography extras) ----------------
  const lsh = safeRead(node, 'layoutSizingHorizontal');
  if (lsh !== undefined) entry.lsh = lsh;
  const lsv = safeRead(node, 'layoutSizingVertical');
  if (lsv !== undefined) entry.lsv = lsv;
  const lw = safeRead(node, 'layoutWrap');
  if (lw !== undefined) entry.lw = lw;

  // ---- supplement slice: layoutPositioning, Grid -------------------------
  const lp = safeRead(node, 'layoutPositioning');
  if (lp !== undefined && lp !== 'AUTO') entry.lp = lp;

  if (safeRead(node, 'layoutMode') === 'GRID') {
    const gr = safeRead(node, 'gridRowCount');    if (gr !== undefined) entry.gr = gr;
    const gc = safeRead(node, 'gridColumnCount'); if (gc !== undefined) entry.gc = gc;
    const grg = safeRead(node, 'gridRowGap');     if (grg !== undefined) entry.grg = grg;
    const gcg = safeRead(node, 'gridColumnGap');  if (gcg !== undefined) entry.gcg = gcg;
    const grs = safeRead(node, 'gridRowSizes');   if (grs !== undefined) entry.grs = grs;
    const gcs = safeRead(node, 'gridColumnSizes');if (gcs !== undefined) entry.gcs = gcs;
  }

  // ---- properties slice: mask, boolean op, corner smoothing, arc data ----
  if (safeRead(node, 'isMask')) entry.m = 1;
  const bo = safeRead(node, 'booleanOperation');
  if (node.type === 'BOOLEAN_OPERATION' && bo) entry.bo = bo;
  const cs = safeRead(node, 'cornerSmoothing');
  if (typeof cs === 'number' && cs > 0) entry.cs = cs;
  const ad = safeRead(node, 'arcData');
  if (node.type === 'ELLIPSE' && ad) entry.ad = ad;

  // ---- text slice (typography extras + textAutoResize) -------------------
  if (node.type === 'TEXT') {
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
  }

  // ---- supplement slice: instance component_key + overrides --------------
  if (node.type === 'INSTANCE') {
%CK_BLOCK%
    if (node.overrides && node.overrides.length > 0) {
      const ovs = [];
      for (const ov of node.overrides) {
        const isSelf = ov.id === node.id;
        const child = isSelf ? node : node.findOne(n => n.id === ov.id);
        if (!child) continue;

        const cid = isSelf ? ':self' : (ov.id.includes(';') ? ov.id.substring(ov.id.indexOf(';')) : ov.id);
        const o = { cid, f: ov.overriddenFields, t: child.type };

%OVERRIDE_CHECKS%

        if (child.type === 'INSTANCE' && ov.overriddenFields.some(f => f === 'fills' || f === 'fillStyleId')) {
          try {
            const childMain = await child.getMainComponentAsync();
            if (childMain) o.swapId = childMain.id;
          } catch (e) {}
        }
        ovs.push(o);
      }
      if (ovs.length > 0) entry.ov = ovs;
    }
  }

  // ---- supplement slice: gradientTransform enrichment --------------------
  const fills = safeRead(node, 'fills');
  if (fills && fills.length > 0) {
    const gts = [];
    for (let i = 0; i < fills.length; i++) {
      const f = fills[i];
      if (f && f.gradientTransform) {
        gts.push({ fillIndex: i, gradientTransform: f.gradientTransform });
      }
    }
    if (gts.length > 0) entry.gt = gts;
  }
""".replace("%CK_BLOCK%", ck_block).replace("%OVERRIDE_CHECKS%", override_checks)

    heavy_block = """
  // ---- transforms slice: local w/h, relativeTransform, vectorPaths -------
  const w = safeRead(node, 'width');
  const h = safeRead(node, 'height');
  if (typeof w === 'number') entry.w = w;
  if (typeof h === 'number') entry.h = h;

  const rt = safeRead(node, 'relativeTransform');
  if (rt && rt[0] && rt[1]) {
    entry.rt = [[rt[0][0], rt[0][1], rt[0][2]], [rt[1][0], rt[1][1], rt[1][2]]];
  }

  if (VECTOR_TYPES.has(node.type)) {
    const vp = safeRead(node, 'vectorPaths');
    if (vp && Array.isArray(vp) && vp.length > 0) {
      entry.vp = vp.map(p => ({
        windingRule: p.windingRule || 'NONZERO',
        data: p.data || ''
      }));
    }
    // vector-geometry slice: fill/stroke geometry
    const fg = safeRead(node, 'fillGeometry');
    if (fg && fg.length) entry.fg = fg;
    const sg = safeRead(node, 'strokeGeometry');
    if (sg && sg.length) entry.sg = sg;
  }

  // OpenType features per styled text segment (heavy because per-char)
  if (node.type === 'TEXT') {
    try {
      const segs = node.getStyledTextSegments(['openTypeFeatures']);
      const otSegs = [];
      for (const seg of segs) {
        const feats = seg.openTypeFeatures;
        if (feats && Object.keys(feats).length > 0) {
          otSegs.push({ s: seg.start, e: seg.end, f: feats });
        }
      }
      if (otSegs.length > 0) entry.ot = otSegs;
    } catch(e) {}
  }
"""

    selected_body = ""
    if want_light:
        selected_body += light_block
    if want_heavy:
        selected_body += heavy_block

    # Compose the full JS. selected_body is already valid JS (no f-string
    # interpolation needed), so we concatenate rather than f-string to
    # avoid brace-escape explosions.
    preamble = f"""
const screenIds = {ids_json};
const result = {{}};
const VECTOR_TYPES = new Set(
  ['VECTOR','BOOLEAN_OPERATION','ELLIPSE','LINE','STAR','REGULAR_POLYGON','POLYGON']
);

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
"""

    postamble = """
  if (Object.keys(entry).length > 0) {
    result[node.id] = entry;
  }

  if ('children' in node) {
    for (const child of node.children) {
      await walkNode(child);
    }
  }
}

for (const sid of screenIds) {
  const screen = await figma.getNodeByIdAsync(sid);
  if (screen) {
    await walkNode(screen);
  }
}

return result;
"""

    return preamble + selected_body + postamble


def apply_plugin(
    conn: sqlite3.Connection,
    data: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Dispatch unified-walker results to their target columns/tables.

    Reuses the existing apply_* functions so each field set lands in
    the same column via the same code path as the single-pass
    counterparts. The unified walker's extra keys on each node are
    ignored by each dispatcher.
    """
    supplement_counts = apply_supplement(conn, data)
    targeted_counts = apply_targeted(conn, data)
    sizing_counts = apply_sizing(conn, data)
    transforms_counts = apply_transforms(conn, data)
    vector_counts = apply_vector_geometry(conn, data)

    return {
        # supplement fields
        "layout_positioning": supplement_counts["layout_positioning"],
        "component_key": supplement_counts["component_key"],
        "grid": supplement_counts["grid"],
        "overrides": supplement_counts["overrides"],
        # properties fields
        "is_mask": targeted_counts["is_mask"],
        "boolean_operation": targeted_counts["boolean_operation"],
        "corner_smoothing": targeted_counts["corner_smoothing"],
        "arc_data": targeted_counts["arc_data"],
        # sizing fields
        "layout_sizing_h": sizing_counts["layout_sizing_h"],
        "layout_sizing_v": sizing_counts["layout_sizing_v"],
        "text_auto_resize": sizing_counts["text_auto_resize"],
        "font_style": sizing_counts["font_style"],
        "text_case": sizing_counts["text_case"],
        "text_decoration": sizing_counts["text_decoration"],
        "paragraph_spacing": sizing_counts["paragraph_spacing"],
        "layout_wrap": sizing_counts["layout_wrap"],
        # transforms fields
        "relative_transform": transforms_counts["relative_transform"],
        "opentype_features": transforms_counts["opentype_features"],
        "width_height": transforms_counts["width_height"],
        "vector_paths": transforms_counts["vector_paths"],
        # vector-geometry fields
        "fill_geometry": vector_counts["fill_geometry"],
        "stroke_geometry": vector_counts["stroke_geometry"],
        # combined
        "total_nodes_touched": len(data),
    }


def _run_one_slice(
    conn: sqlite3.Connection,
    screen_ids: list[str],
    execute_fn: Callable[[str], dict[str, Any]],
    *,
    slice: str,
    collect_component_key: bool,
    initial_batch_size: int,
    delay: float,
) -> tuple[dict[str, int], list[str], int]:
    """Run one slice (light or heavy) across all screens.

    Returns (counts, failed_screens, batches_run).
    Auto-halves batch_size on script-size truncation.
    """
    totals: dict[str, int] = {}
    failed: list[str] = []
    batches = 0

    i = 0
    current_batch = initial_batch_size
    while i < len(screen_ids):
        batch = screen_ids[i : i + current_batch]
        script = generate_plugin_script(
            batch,
            collect_component_key=collect_component_key,
            slice=slice,
        )

        try:
            result = execute_fn(script)
            if not isinstance(result, dict):
                raise ValueError(f"Expected dict, got {type(result)}")
            counts = apply_plugin(conn, result)
            for k, v in counts.items():
                if isinstance(v, int):
                    totals[k] = totals.get(k, 0) + v
            batches += 1
            i += current_batch
        except Exception as e:
            error_msg = str(e)
            if (
                "Unterminated string" in error_msg
                or "65536" in error_msg
                or "65533" in error_msg
            ):
                if current_batch > 1 and len(batch) > 1:
                    current_batch = max(1, current_batch // 2)
                    continue
            if len(batch) == 1:
                failed.append(batch[0])
                i += 1
            else:
                # Try screen-by-screen for this batch.
                for sid in batch:
                    try:
                        single_script = generate_plugin_script(
                            [sid],
                            collect_component_key=collect_component_key,
                            slice=slice,
                        )
                        single_result = execute_fn(single_script)
                        if isinstance(single_result, dict):
                            counts = apply_plugin(conn, single_result)
                            for k, v in counts.items():
                                if isinstance(v, int):
                                    totals[k] = totals.get(k, 0) + v
                        batches += 1
                    except Exception:
                        failed.append(sid)
                i += current_batch

        time.sleep(delay)

    return totals, failed, batches


def run_plugin_extract(
    conn: sqlite3.Connection,
    execute_fn: Callable[[str], dict[str, Any]],
    *,
    batch_size: int = 10,
    delay: float = 0.3,
    screen_type: str = "app_screen",
    collect_component_key: bool = False,
) -> dict[str, Any]:
    """Run the unified Plugin-API extraction on all screens of the given type.

    Two-slice replacement for the old extract-supplement + 4x
    extract-targeted sequence:

    - **light** slice: layout flags, grid, overrides, mask/bool/arc,
      typography strings, gradient enrichment. Small per-node payload.
    - **heavy** slice: relativeTransform (emitted for every node),
      vectorPaths, fillGeometry/strokeGeometry, OpenType segments.
      Large per-node payload.

    Running both in one walk exceeds Figma's ~64KB PROXY_EXECUTE result
    buffer on moderate-sized screens. Splitting makes each slice's
    per-batch response fit comfortably, while still cutting 5 passes
    down to 2 — a ~2.5x win over the old pipeline and a 10x win on
    subprocess startup + WebSocket handshakes.

    Auto-batches, halves batch-size on script-size truncation, and
    records each per-batch failure as a structured entry rather than
    crashing.
    """
    screens = conn.execute(
        "SELECT figma_node_id, name FROM screens WHERE screen_type = ? ORDER BY id",
        (screen_type,),
    ).fetchall()
    screen_ids = [r[0] for r in screens]

    counter_keys = [
        "layout_positioning", "component_key", "grid", "overrides",
        "is_mask", "boolean_operation", "corner_smoothing", "arc_data",
        "layout_sizing_h", "layout_sizing_v", "text_auto_resize",
        "font_style", "text_case", "text_decoration",
        "paragraph_spacing", "layout_wrap",
        "relative_transform", "opentype_features", "width_height",
        "vector_paths", "fill_geometry", "stroke_geometry",
        "total_nodes_touched",
    ]
    totals: dict[str, Any] = {k: 0 for k in counter_keys}
    totals["batches"] = 0
    totals["failed"] = 0
    totals["failed_screens"] = []

    if not screen_ids:
        return totals

    # Light slice first — its overrides / gradient enrichment code depends
    # on node.fills which ordering-wise stays stable across both passes
    # (both are read-only). Running light first keeps single-slice runs
    # (e.g. for quick re-sync after a schema migration) useful even if
    # heavy is skipped.
    light_totals, light_failed, light_batches = _run_one_slice(
        conn, screen_ids, execute_fn,
        slice=SLICE_LIGHT,
        collect_component_key=collect_component_key,
        initial_batch_size=batch_size,
        delay=delay,
    )
    for k, v in light_totals.items():
        totals[k] = totals.get(k, 0) + (v if isinstance(v, int) else 0)
    totals["batches"] += light_batches

    # Heavy slice uses a smaller initial batch because per-node payload
    # is much larger (full relativeTransform, vectorPaths, geometries).
    heavy_batch = max(1, batch_size // 2)
    heavy_totals, heavy_failed, heavy_batches = _run_one_slice(
        conn, screen_ids, execute_fn,
        slice=SLICE_HEAVY,
        collect_component_key=False,  # not meaningful for heavy slice
        initial_batch_size=heavy_batch,
        delay=delay,
    )
    for k, v in heavy_totals.items():
        totals[k] = totals.get(k, 0) + (v if isinstance(v, int) else 0)
    totals["batches"] += heavy_batches

    all_failed = list(set(light_failed) | set(heavy_failed))
    totals["failed"] = len(all_failed)
    totals["failed_screens"] = all_failed

    # Post-processing: the heavy slice populated fill_geometry /
    # stroke_geometry / vector_paths on nodes, but the renderer reads
    # vectors via the content-addressed asset store (node_asset_refs ->
    # assets). Without this step, node_asset_refs stays empty and every
    # VECTOR node renders as KIND_MISSING_ASSET at verify time.
    # The old extract_targeted --mode vector-geometry called this at the
    # end of its CLI handler; the unified pass owns both collection and
    # post-processing.
    try:
        from dd.extract_assets import process_vector_geometry
        asset_count = process_vector_geometry(conn)
        totals["vector_assets_built"] = asset_count
    except Exception as exc:
        # Don't fail the whole run — record but keep going.
        totals["vector_assets_built"] = 0
        totals["vector_assets_error"] = str(exc)

    return totals
