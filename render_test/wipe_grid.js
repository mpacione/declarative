#!/usr/bin/env node
// One-shot cleanup for the "Option-B-Grid" page — removes every top-
// level child so a fresh `grid_render.py` sweep doesn't stack new
// frames on top of prior ones.
//
// Usage: node wipe_grid.js [port=9228]

const WebSocket = require('ws');

async function run() {
  const port = parseInt(process.argv[2] || '9228', 10);
  // PROXY_EXECUTE strips return values and already wraps this body in
  // an async IIFE — don't add our own wrapper or the plugin's IIFE
  // returns before our work runs. Persist diagnostics via
  // setPluginData so the caller can verify the wipe ran.
  const wrapped = `
await figma.loadAllPagesAsync();
const __page = figma.root.children.find(p => p.name === 'Option-B-Grid');
if (!__page) {
  figma.root.setPluginData('__wipe_diag',
    JSON.stringify({ wiped: 0, note: 'no Option-B-Grid page' }));
} else {
  const n = __page.children.length;
  for (const c of [...__page.children]) { c.remove(); }
  figma.root.setPluginData('__wipe_diag',
    JSON.stringify({ wiped: n, remaining: __page.children.length }));
}
`.trim();

  const ws = new WebSocket('ws://localhost:' + port);
  await new Promise((res, rej) => {
    ws.on('open', res);
    ws.on('error', rej);
  });
  const id = 'wipe-' + Date.now();
  ws.send(JSON.stringify({
    type: 'PROXY_EXECUTE',
    id,
    code: wrapped,
    timeout: 30000,
  }));
  await new Promise((res, rej) => {
    ws.on('message', (msg) => {
      const data = JSON.parse(msg.toString());
      if (data.id === id && data.type === 'PROXY_EXECUTE_RESULT') {
        res(data);
      }
    });
    setTimeout(() => rej(new Error('wipe timeout')), 30000);
  });

  // Read back the diagnostic the wipe persisted via setPluginData.
  const readBack = `
const diag = figma.root.getPluginData('__wipe_diag');
figma.root.setPluginData('__wipe_diag', '');
return diag;
`.trim();
  const id2 = 'wipe-readback-' + Date.now();
  ws.send(JSON.stringify({
    type: 'PROXY_EXECUTE',
    id: id2,
    code: readBack,
    timeout: 10000,
  }));
  await new Promise((res) => setTimeout(res, 500));
  ws.close();
  console.log('wipe submitted; check Figma page.');
}

run().catch(e => { console.error(e); process.exit(1); });
