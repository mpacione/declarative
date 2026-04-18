#!/usr/bin/env node
// Sequentially re-render each script via walk_ref-style clear+run,
// then export the rendered_root as PNG and write to disk next to the script.
// Usage: node batch_screenshot.js <manifest.json> <port>
//   manifest.json: [{ script_path, out_png_path }, ...]

const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');

function connect(port) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket('ws://localhost:' + port);
    ws.on('open', () => resolve(ws));
    ws.on('error', reject);
  });
}

function send(ws, payload, timeout_ms = 180000) {
  return new Promise((resolve, reject) => {
    const id = payload.id || `sc_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    payload.id = id;
    const timer = setTimeout(() => reject(new Error('timeout on ' + id)), timeout_ms);
    const listener = (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.type === 'PROXY_EXECUTE_RESULT' && msg.id === id) {
        clearTimeout(timer);
        ws.off('message', listener);
        if (msg.error) reject(new Error(msg.error));
        else resolve(msg);
      }
    };
    ws.on('message', listener);
    ws.send(JSON.stringify(payload));
  });
}

async function renderAndCapture(ws, scriptPath, outPng) {
  const userCode = fs.readFileSync(scriptPath, 'utf8').replace(/return M;\s*$/, '');
  const wrapped = `
await figma.loadAllPagesAsync();
let __page = figma.root.children.find(p => p.name === 'Generated Test');
if (!__page) { __page = figma.createPage(); __page.name = 'Generated Test'; }
await figma.setCurrentPageAsync(__page);
for (const c of [...__page.children]) c.remove();

${userCode}

const rootId = M['screen-1'] || (__page.children[0] && __page.children[0].id);
if (!rootId) return { __ok: false, reason: 'no root' };
const rootNode = await figma.getNodeByIdAsync(rootId);
if (!rootNode) return { __ok: false, reason: 'root not found' };
const bytes = await rootNode.exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: 1 } });
const b64 = figma.base64Encode(bytes);
return { __ok: true, rootId, width: rootNode.width, height: rootNode.height, size: bytes.length, b64, errors: M['__errors'] || [] };
`;
  const result = await send(ws, { type: 'PROXY_EXECUTE', code: wrapped, timeout: 170000 });
  const inner = result.result && result.result.result;
  if (!inner || !inner.__ok) {
    console.error('FAIL', scriptPath, inner);
    return { ok: false, reason: inner && inner.reason };
  }
  fs.writeFileSync(outPng, Buffer.from(inner.b64, 'base64'));
  return {
    ok: true,
    rootId: inner.rootId,
    width: inner.width,
    height: inner.height,
    size: inner.size,
    errors: inner.errors,
    out: outPng,
  };
}

async function main() {
  const manifestPath = process.argv[2];
  const port = parseInt(process.argv[3] || '9228', 10);
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const ws = await connect(port);
  const results = [];
  for (const { script_path, out_png_path } of manifest) {
    try {
      const t0 = Date.now();
      const r = await renderAndCapture(ws, script_path, out_png_path);
      const dt = Date.now() - t0;
      r.ms = dt;
      r.script_path = script_path;
      results.push(r);
      console.log(script_path, '->', out_png_path,
        r.ok ? `${r.width}x${r.height} size=${r.size} ms=${dt} errors=${r.errors.length}` : 'FAIL');
    } catch (err) {
      console.error('ERR', script_path, err.message);
      results.push({ ok: false, script_path, error: err.message });
    }
  }
  ws.close();
  const resultsPath = manifestPath.replace(/\.json$/, '.results.json');
  fs.writeFileSync(resultsPath, JSON.stringify(results, null, 2));
  console.log('wrote', resultsPath);
}

main().catch((e) => { console.error('FATAL', e); process.exit(1); });
