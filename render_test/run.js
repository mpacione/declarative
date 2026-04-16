#!/usr/bin/env node
// Execute a generated Figma script via PROXY_EXECUTE WebSocket bridge.
// Usage: node run.js <script.js> [port]

const WebSocket = require('/Users/mattpacione/.npm/_npx/b547afed9fcf6dcb/node_modules/ws');
const fs = require('fs');
const path = require('path');

async function execute(scriptPath, port = 9228) {
  let code = fs.readFileSync(scriptPath, 'utf8');
  // Inject markers for every node creation so we can see where execution stops.
  code = code
    .replace(/^(\/\/ Phase 1:.*)$/m, '$1\n__diag.phase = "phase1"; __save();')
    .replace(/^(\/\/ Phase 2:.*)$/m, '$1\n__diag.phase = "phase2"; __save();')
    .replace(/^(\/\/ Phase 3:.*)$/m, '$1\n__diag.phase = "phase3"; __save();')
    .replace(/^(const (n\d+) = )/gm, '__diag.lastNode = "$2"; __save(); $1')
    .replace(/^return M;\s*$/m, '__diag.phase = "pre-return"; __save(); /* return M; */');
  const id = `run_${Date.now()}`;
  // Ensure we target the "Generated Test" page first, then run the script there.
  // Snapshot existing top-level nodes across all pages before user code runs.
  // getNodeByIdAsync for component masters changes currentPage as a side
  // effect, so auto-appended creations leak to the master's home page.
  // After user code runs, we diff and relocate any orphaned new roots.
  // Safeguard: the ONLY page we're ever allowed to write destructively to
  // is the one named 'Generated Test'. Resolve it by name (never trust
  // figma.currentPage, which figma.getNodeByIdAsync side-effects). If
  // someone renames the page or the lookup fails for any reason, create
  // a fresh one. Never proceed with an ambiguous __page identity.
  const pageSetup = `
await figma.loadAllPagesAsync();
const __OUTPUT_PAGE = 'Generated Test';
let __page = figma.root.children.find(p => p.name === __OUTPUT_PAGE);
if (!__page) {
  __page = figma.createPage();
  __page.name = __OUTPUT_PAGE;
}
await figma.setCurrentPageAsync(__page);
// Hard-assert the identity of our write target before doing anything.
// If this ever trips, the file/page state is unexpected — refuse to run.
if (__page.name !== __OUTPUT_PAGE) {
  throw new Error('refusing to run: resolved page is not ' + __OUTPUT_PAGE);
}
const __before = __page.children.length;
`;
  // Wrap with diagnostic capture: record progress/errors to figma.root.setPluginData
  // since PROXY_EXECUTE strips script return values.
  // The figma-console-mcp plugin wraps msg.code in its own `(async function() {
  // ${msg.code} })()` and awaits the returned Promise. So we must NOT wrap our
  // code in an IIFE here — the plugin's IIFE becomes our async context. If we
  // add our own IIFE, the plugin's function returns immediately without
  // awaiting, and our work runs orphaned.
  const wrapped = `
${pageSetup}
const __diag = { phase: 'start', before: __before };
const __save = () => figma.root.setPluginData('__render_diag', JSON.stringify(__diag));
try {
  __diag.phase = 'user_code';
  __save();
${code}
  // Relocate any of OUR newly-created nodes that leaked to other pages.
  // figma.getNodeByIdAsync side-effects figma.currentPage, and
  // figma.createInstance() on a component whose home page isn't the
  // current one can deposit the new instance on the master's page.
  //
  // Safeguard (vs the prior "not in preIds" heuristic): use M — the
  // id-map the generated script populates as it creates nodes — as
  // the EXPLICIT manifest of what we're allowed to move. If an id
  // isn't in M, we didn't create it and won't touch it.
  let __moved = 0;
  const __ourIds = new Set(Object.values(M));
  for (const __p of figma.root.children) {
    if (__p.id === __page.id) continue;
    for (const __c of [...__p.children]) {
      if (__ourIds.has(__c.id)) { __page.appendChild(__c); __moved++; }
    }
  }
  __diag.phase = 'done';
  __diag.moved = __moved;
  __diag.after = __page.children.length;
  __diag.topLevelNames = __page.children.map(c => c.name);
  // Capture structured errors emitted by Mode 1 null-guards etc.
  // __errors is declared by the generated script's preamble; fall back to
  // empty array when the script doesn't expose it (legacy/test paths).
  try { __diag.errors = (typeof __errors !== 'undefined') ? __errors : []; } catch (_) { __diag.errors = []; }
  __save();
  return { __ok: true, before: __before, after: __page.children.length, moved: __moved, errors: __diag.errors };
} catch (e) {
  __diag.phase = 'error';
  __diag.error = String(e && e.message || e);
  __diag.stack = String(e && e.stack || '');
  __diag.after = __page.children.length;
  __diag.topLevelNames = __page.children.map(c => c.name);
  __save();
  return { __phase: 'script_error', error: String(e && e.message || e), before: __before, after: __page.children.length };
}
`;

  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://localhost:${port}`);
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error('timeout'));
    }, 60000);

    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'PROXY_EXECUTE', id, code: wrapped, timeout: 55000 }));
    });

    ws.on('message', (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.type === 'PROXY_EXECUTE_RESULT' && msg.id === id) {
        clearTimeout(timer);
        ws.close();
        if (msg.error) reject(new Error(msg.error));
        else resolve(msg);
      }
    });

    ws.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

(async () => {
  const scriptPath = process.argv[2];
  const port = parseInt(process.argv[3] || '9228', 10);
  if (!scriptPath) {
    console.error('Usage: node run.js <script.js> [port]');
    process.exit(1);
  }
  const name = path.basename(scriptPath);
  const t0 = Date.now();
  try {
    const result = await execute(scriptPath, port);
    const dt = Date.now() - t0;
    console.log(`[${name}] OK in ${dt}ms:`, JSON.stringify(result));
  } catch (err) {
    const dt = Date.now() - t0;
    console.error(`[${name}] FAIL in ${dt}ms:`, err.message);
    process.exit(1);
  }
})();
