#!/usr/bin/env node
// Execute a generated Figma script, then walk the rendered subtree by eid
// and write a rendered-ref JSON payload for `dd verify --rendered-ref`.
//
// Usage: node walk_ref.js <script.js> <output.json> [port=9228]
//
// The output has shape:
//   {
//     __ok: true,
//     errors: [...],
//     rendered_root: "<figma-node-id>",
//     rendered_root_width, rendered_root_height,
//     eid_map: {
//       "<eid>": {
//         type: "<FIGMA_TYPE>",
//         name, width, height,
//         x, y,                              // post-rotation AABB TL, relative to root TL
//         rotation,                          // radians (0 for non-rotated)
//         characters, textAutoResize,        // TEXT only
//         fillGeometryCount, strokeGeometryCount,  // VECTOR / BOOLEAN_OPERATION
//       }
//     }
//   }
//
// x / y / rotation were added 2026-04-21 to support SoM-based
// component-coverage fidelity scoring (docs/research/scorer-calibration
// -and-som-fidelity.md). `dd/classify_vision_som.py`'s annotations
// format expects: {id, x, y, w, h, rotation} where x/y are post-rotation
// AABB TL relative to the screenshot's origin (which is the rendered
// root's TL for the screenshot we export). rotation is radians.
//
// Additive change only — existing consumers reading width/height/fills
// are unaffected; the new fields are present but ignored by them.

// Resolve `ws` via Node module resolution (see package.json).
const WebSocket = require('ws');
const fs = require('fs');

async function run() {
  const scriptPath = process.argv[2];
  const outPath = process.argv[3];
  const port = parseInt(process.argv[4] || '9228', 10);
  if (!scriptPath || !outPath) {
    console.error('Usage: node walk_ref.js <script.js> <output.json> [port=9228]');
    process.exit(1);
  }

  const userCode = fs.readFileSync(scriptPath, 'utf8');
  // Strip the trailing `return M;` — we'll insert our own return that
  // wraps M in a structured payload with the walk result.
  const body = userCode.replace(/return M;\s*$/, '');

  const wrapped = `
// Safeguard: resolve __page by NAME (never trust figma.currentPage —
// figma.getNodeByIdAsync side-effects it). Hard-assert identity before
// any destructive operation. If this ever trips, the file state is
// unexpected — refuse to run rather than risk clearing a source page.
const __OUTPUT_PAGE = 'Generated Test';
await figma.loadAllPagesAsync();
let __page = figma.root.children.find(p => p.name === __OUTPUT_PAGE);
if (!__page) { __page = figma.createPage(); __page.name = __OUTPUT_PAGE; }
await figma.setCurrentPageAsync(__page);
if (__page.name !== __OUTPUT_PAGE) {
  throw new Error('refusing to clear: resolved page is not ' + __OUTPUT_PAGE);
}
for (const c of [...__page.children]) c.remove();

${body}

// Invert M so we can walk the rendered subtree keyed by eid.
const idToEid = {};
for (const k of Object.keys(M)) {
  if (k === '__errors' || k === '__canary' || k === '__perf') continue;
  idToEid[M[k]] = k;
}

// Find the rendered root — first screen-eid in M, falling back to the
// first top-level child on the page.
const rootId = M['screen-1'] || (__page.children[0] && __page.children[0].id);
const rootNode = rootId ? await figma.getNodeByIdAsync(rootId) : null;

// Capture the root's absolute bounding box so per-node x/y can be
// emitted relative to it. exportAsync renders a PNG whose origin is
// the root's TL, so screenshot-relative coords == root-relative coords.
const rootAbs = rootNode && rootNode.absoluteBoundingBox
  ? rootNode.absoluteBoundingBox
  : null;

const eid_map = {};
if (rootNode) {
  const stack = [rootNode];
  while (stack.length) {
    const n = stack.pop();
    const eid = idToEid[n.id];
    if (eid) {
      const entry = {
        type: n.type,
        name: n.name,
        width: n.width,
        height: n.height,
      };
      // Post-rotation AABB TL relative to the root's TL. When either
      // absoluteBoundingBox is null (unusual — detached node), we fall
      // back to 0,0 so downstream consumers don't see NaN, but flag via
      // the diagnostic channel for auditability.
      try {
        const ab = n.absoluteBoundingBox;
        if (ab && rootAbs) {
          entry.x = ab.x - rootAbs.x;
          entry.y = ab.y - rootAbs.y;
        } else {
          entry.x = 0;
          entry.y = 0;
        }
      } catch (_) {
        entry.x = 0;
        entry.y = 0;
      }
      // Figma's node.rotation is in degrees; classify_vision_som
      // render_som_overlay wants radians. Convert here so downstream
      // consumers do not need to know the Figma-specific unit.
      try {
        const deg = (typeof n.rotation === 'number') ? n.rotation : 0;
        entry.rotation = deg * Math.PI / 180;
      } catch (_) {
        entry.rotation = 0;
      }
      if (n.type === 'TEXT') {
        entry.characters = n.characters || '';
        entry.textAutoResize = n.textAutoResize;
      }
      if (n.type === 'VECTOR' || n.type === 'BOOLEAN_OPERATION') {
        // fillGeometry / strokeGeometry are arrays of path objects. A
        // VECTOR with no paths renders as an invisible rectangle (the
        // fill/stroke still exists but has nothing to draw against).
        // Attribute those nodes so the verifier can flag them with
        // KIND_MISSING_ASSET.
        try {
          entry.fillGeometryCount = (n.fillGeometry || []).length;
        } catch (_) { entry.fillGeometryCount = 0; }
        try {
          entry.strokeGeometryCount = (n.strokeGeometry || []).length;
        } catch (_) { entry.strokeGeometryCount = 0; }
      }
      // Capture SOLID fills/strokes for KIND_FILL_MISMATCH /
      // KIND_STROKE_MISMATCH verification. Normalized to the same shape
      // as the IR: [{type, color}]. Only SOLID for now.
      const toHex = (v) => Math.round(Math.min(1, Math.max(0, v)) * 255)
        .toString(16).padStart(2, '0').toUpperCase();
      const normalizeSolids = (paints) => {
        if (!Array.isArray(paints)) return null;
        const out = [];
        for (const p of paints) {
          if (p.visible === false) continue;
          if (p.type === 'SOLID' && p.color) {
            out.push({ type: 'solid', color: '#' + toHex(p.color.r) + toHex(p.color.g) + toHex(p.color.b) });
          }
        }
        return out.length > 0 ? out : null;
      };
      try { const f = normalizeSolids(n.fills); if (f) entry.fills = f; } catch (_) {}
      try { const s = normalizeSolids(n.strokes); if (s) entry.strokes = s; } catch (_) {}
      // Effect count for KIND_EFFECT_MISSING — just the count, not full data.
      try {
        const fx = n.effects;
        if (Array.isArray(fx)) {
          entry.effectCount = fx.filter(e => e.visible !== false).length;
        }
      } catch (_) {}
      eid_map[eid] = entry;
    }
    if ('children' in n) for (const c of n.children) stack.push(c);
  }
}

return {
  __ok: true,
  errors: M['__errors'] || [],
  perf: M['__perf'] || null,
  rendered_root: rootId,
  rendered_root_width: rootNode ? rootNode.width : 0,
  rendered_root_height: rootNode ? rootNode.height : 0,
  eid_map,
};
`;

  return new Promise((resolve, reject) => {
    const ws = new WebSocket('ws://localhost:' + port);
    const id = 'walk_' + Date.now();
    // Timeout is configurable via BRIDGE_TIMEOUT_MS env var (applies
    // to both the PROXY_EXECUTE server-side timeout sent to the
    // Figma plugin AND the WebSocket client-side watchdog). Default
    // raised 170000 → 300000 on 2026-04-22 after confirming (via
    // Figma plugin-sandbox research) that Figma itself enforces NO
    // hard timeout on plugin scripts — the old 170s figure was the
    // Desktop Bridge wrapper's limit, not Figma's. Under heavy plugin
    // load (iPad-sized screens + slot-inlined children post Option 2
    // type/role + slot-flatten fix) renders legitimately need
    // 200-300s; raising the default is safe because the bridge still
    // enforces per-screen retry on true hangs, and sweep.py's
    // subprocess timeout (320s) stays a strict upper bound.
    const proxyTimeoutMs = parseInt(process.env.BRIDGE_TIMEOUT_MS || '300000', 10);
    const watchdogMs = proxyTimeoutMs + 10000;
    const timer = setTimeout(() => { ws.close(); reject(new Error('timeout')); }, watchdogMs);
    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'PROXY_EXECUTE', id, code: wrapped, timeout: proxyTimeoutMs }));
    });
    ws.on('message', (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.type === 'PROXY_EXECUTE_RESULT' && msg.id === id) {
        clearTimeout(timer);
        ws.close();
        if (msg.error) reject(new Error(msg.error));
        else {
          const result = msg.result && msg.result.result;
          if (!result) {
            reject(new Error('no result in ' + JSON.stringify(msg).slice(0, 500)));
            return;
          }
          fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
          const err_ct = (result.errors || []).length;
          const eid_ct = Object.keys(result.eid_map || {}).length;
          const vec_missing = Object.values(result.eid_map || {}).filter(
            e => (e.type === 'VECTOR' || e.type === 'BOOLEAN_OPERATION')
              && e.fillGeometryCount === 0 && e.strokeGeometryCount === 0
          ).length;
          console.log(
            'wrote ' + outPath + ' — ' + eid_ct + ' eids, '
            + err_ct + ' errors, ' + vec_missing + ' missing vector assets'
          );
          resolve();
        }
      }
    });
    ws.on('error', (e) => { clearTimeout(timer); reject(e); });
  });
}

run().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
