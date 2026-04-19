#!/usr/bin/env node
// Execute a generated Figma script and LEAVE the rendered frames on a
// dedicated "Option-B-Grid" page for visual inspection — distinct from
// `walk_ref.js` which wipes the page every run.
//
// The script is expected to carry its own `canvas_position` (x/y
// assignments on the root frame), so multiple invocations produce a
// grid of side-by-side screens on the same page.
//
// Usage: node grid_exec.js <script.js> <out.json> [port=9228]
// `out.json` is a tiny success/failure receipt — no eid_map walk.

const WebSocket = require('ws');
const fs = require('fs');

async function run() {
  const scriptPath = process.argv[2];
  const outPath = process.argv[3];
  const port = parseInt(process.argv[4] || '9228', 10);
  if (!scriptPath || !outPath) {
    console.error('Usage: node grid_exec.js <script.js> <out.json> [port=9228]');
    process.exit(1);
  }

  const userCode = fs.readFileSync(scriptPath, 'utf8');
  // Strip the trailing `return M;` — we substitute our own receipt return.
  const body = userCode.replace(/return M;\s*$/, '');

  const wrapped = `
// Persist the grid on a dedicated page named "Option-B-Grid" — NEVER
// wipe children, and NEVER mutate the user's active page. Create the
// page if it doesn't exist.
const __GRID_PAGE = 'Option-B-Grid';
await figma.loadAllPagesAsync();
let __page = figma.root.children.find(p => p.name === __GRID_PAGE);
if (!__page) { __page = figma.createPage(); __page.name = __GRID_PAGE; }
await figma.setCurrentPageAsync(__page);
if (__page.name !== __GRID_PAGE) {
  throw new Error('refusing to render: resolved page is not ' + __GRID_PAGE);
}

${body}

// Receipt: count top-level children + error channel snapshot.
const childCount = __page.children.length;
return {
  __ok: true,
  page_name: __page.name,
  rendered_root: (M && M['screen-1']) || null,
  top_level_children: childCount,
  errors: (M && M['__errors']) || [],
};
`;

  return new Promise((resolve, reject) => {
    const ws = new WebSocket('ws://localhost:' + port);
    const id = 'grid_' + Date.now();
    const timer = setTimeout(() => { ws.close(); reject(new Error('timeout')); }, 180000);
    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'PROXY_EXECUTE', id, code: wrapped, timeout: 170000 }));
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
          } else {
            fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
            resolve();
          }
        }
      }
    });
    ws.on('error', (err) => { clearTimeout(timer); reject(err); });
  });
}

run().then(() => process.exit(0)).catch((err) => {
  console.error('FAIL:', err.message || err);
  process.exit(1);
});
