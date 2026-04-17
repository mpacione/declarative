#!/usr/bin/env node
// Capture a Figma node as PNG bytes via PROXY_EXECUTE WebSocket bridge.
// Usage: node capture.js <figma_node_id> <out_png_path> [port]
// Writes PNG bytes to out_png_path.

const WebSocket = require('ws');
const fs = require('fs');

async function capture(nodeId, port) {
  const id = `cap_${Date.now()}`;
  // exportAsync returns Uint8Array; we base64 it to travel over the JSON bridge.
  // Buffer is not available in the plugin sandbox, so we roll a manual b64 encode.
  // Scale 1 is plenty — the plugin already caps at 1568px longest side.
  const code = `
const node = await figma.getNodeByIdAsync(${JSON.stringify(nodeId)});
if (!node) { throw new Error('node not found: ' + ${JSON.stringify(nodeId)}); }
const bytes = await node.exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: 1 } });
// Convert Uint8Array to a plain JS number array so it travels cleanly
// through structured clone / JSON. Node side will reassemble to Buffer.
// We chunk into bands to avoid string-coercion issues on very large assets.
const arr = Array.from(bytes);
return { __ok: true, bytes: arr, byteLength: bytes.length, nodeName: node.name, width: node.width, height: node.height };
`;
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://localhost:${port}`);
    const timer = setTimeout(() => { ws.close(); reject(new Error('timeout')); }, 60000);
    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'PROXY_EXECUTE', id, code, timeout: 55000 }));
    });
    ws.on('message', (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.type === 'PROXY_EXECUTE_RESULT' && msg.id === id) {
        clearTimeout(timer);
        ws.close();
        if (msg.error) reject(new Error(msg.error));
        else {
          // PROXY_EXECUTE_RESULT shape: { type, id, result: { success, result: <our return> } }
          const outer = msg.result || {};
          const inner = outer.result || outer;
          resolve(inner);
        }
      }
    });
    ws.on('error', (err) => { clearTimeout(timer); reject(err); });
  });
}

(async () => {
  const nodeId = process.argv[2];
  const outPath = process.argv[3];
  const port = parseInt(process.argv[4] || '9231', 10);
  if (!nodeId || !outPath) {
    console.error('Usage: node capture.js <figma_node_id> <out_png_path> [port]');
    process.exit(1);
  }
  const t0 = Date.now();
  try {
    const result = await capture(nodeId, port);
    if (!result || !Array.isArray(result.bytes)) {
      throw new Error('no bytes in result: ' + JSON.stringify(result).slice(0, 200));
    }
    const buf = Buffer.from(result.bytes);
    fs.writeFileSync(outPath, buf);
    const dt = Date.now() - t0;
    console.log(JSON.stringify({ ok: true, node: nodeId, out: outPath, byteLength: buf.length, width: result.width, height: result.height, ms: dt }));
  } catch (err) {
    const dt = Date.now() - t0;
    console.error(JSON.stringify({ ok: false, node: nodeId, error: err.message, ms: dt }));
    process.exit(1);
  }
})();
