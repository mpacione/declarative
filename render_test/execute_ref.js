#!/usr/bin/env node
// Execute a generated Figma script via the plugin bridge and write an
// ack JSON. No tree walk — companion to walk_ref.js, used by the
// `dd design --render-to-figma` path where the visible canvas IS the
// output. Walking would cost 30-60s and expose demo runs to walk-class
// failures (hidden subtrees under skipInvisibleInstanceChildren, large
// tree traversal timeouts) for no benefit.
//
// Usage: node execute_ref.js <script.js> <out.json> [port=9228]
//
// Output shape (out.json):
//   { __ok: true, errors: [...], request_id: '<exec_...>' }
//
// `errors` forwards M.__errors from the generated script — the same
// structured failure channel the sweep pipeline consumes. Non-empty
// errors are NOT treated as wrapper failures here (the bridge
// accepted the script), but the caller sees them in the payload.
//
// Unlike walk_ref.js the wrapper does NOT resolve to a fixed
// `__OUTPUT_PAGE` and does NOT clear children: the generated script
// carries its own `page_name`-driven find-or-create-and-append logic
// (see render_figma_ast's root-attach emission at page_name branch).
// Two scripts sharing the same page_name land as siblings on that page —
// that's the side-by-side-demo contract.
const WebSocket = require('ws');
const fs = require('fs');

async function run() {
  const scriptPath = process.argv[2];
  const outPath = process.argv[3];
  const port = parseInt(process.argv[4] || '9228', 10);
  if (!scriptPath || !outPath) {
    console.error('Usage: node execute_ref.js <script.js> <out.json> [port=9228]');
    process.exit(1);
  }

  const userCode = fs.readFileSync(scriptPath, 'utf8');
  // Strip the trailing `return M;` so we can replace it with an ack
  // envelope that surfaces M.__errors to the Python caller. Mirrors
  // walk_ref.js's approach — keeps the generated-script contract
  // stable.
  const body = userCode.replace(/return M;\s*$/, '');

  const wrapped = `
${body}

return {
  __ok: true,
  errors: (typeof M !== 'undefined' && M.__errors) ? M.__errors : [],
};
`;

  return new Promise((resolve, reject) => {
    const ws = new WebSocket('ws://localhost:' + port);
    const id = 'exec_' + Date.now();
    // Mirror walk_ref.js's BRIDGE_TIMEOUT_MS convention so the two
    // wrappers have a single knob when someone's debugging bridge
    // latency. Default 300s; Python subprocess timeout is the hard
    // cap.
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
        if (msg.error) {
          reject(new Error(msg.error));
          return;
        }
        const result = msg.result && msg.result.result;
        if (!result) {
          reject(new Error('no result in ' + JSON.stringify(msg).slice(0, 500)));
          return;
        }
        const ack = {
          __ok: result.__ok !== false,
          errors: result.errors || [],
          request_id: id,
        };
        fs.writeFileSync(outPath, JSON.stringify(ack, null, 2));
        const err_ct = ack.errors.length;
        console.log(
          'wrote ' + outPath + ' — ack ' + (ack.__ok ? 'ok' : 'FAIL')
          + ', ' + err_ct + ' script errors'
        );
        resolve();
      }
    });
    ws.on('error', (e) => { clearTimeout(timer); reject(e); });
  });
}

run().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
