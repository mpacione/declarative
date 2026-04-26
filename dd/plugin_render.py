"""Figma Plugin render-toggle: render a screen with specific self-
hidden nodes temporarily made visible.

Self-hidden nodes (``visible=0``) can't be fetched via Figma REST's
``/images`` endpoint — the response is empty. But the Plugin API can
flip ``node.visible`` at runtime, and ``exportAsync`` respects the
live value. This module wraps that flow:

1. Resolve the screen node by its figma_node_id.
2. For each target hidden node: resolve it, walk its parent chain up
   to the screen, record originally-hidden nodes.
3. Flip all recorded nodes to visible=true.
4. exportAsync the screen root at the requested scale.
5. Restore every flipped node in a ``finally`` block, even if export
   fails.
6. Return the rendered PNG bytes (may contain transparent regions
   where the now-visible node has alpha — pair with the checkerboard
   compositor for adjudication).

Uses the same subprocess + Node.js WebSocket pattern as
``dd/cli.py:execute_via_ws`` and ``dd/extract_targeted.py``.
Returns ``None`` on any error (connection refused, plugin down,
Node missing, script failure) so callers can fall back cleanly
to the dedup-twin / LLM-text ladder.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from typing import Optional


# Tokens that indicate a transient bridge / connection failure —
# worth a single retry. Anything else is permanent and we return
# None so the fallback cascade takes over.
_TRANSIENT_ERROR_SUBSTRINGS = (
    "establish connection",
    "ECONNREFUSED",
    "WebSocket",
    "timeout",
    "EPIPE",
)


def _is_transient(err: Optional[str]) -> bool:
    if not err:
        return False
    s = err.lower()
    return any(t.lower() in s for t in _TRANSIENT_ERROR_SUBSTRINGS)


_DEFAULT_PORT = 9227
_DEFAULT_SCALE = 2
_DEFAULT_TIMEOUT_S = 90

# Per-node thumbnail batch defaults. Smaller scale than the screen-level
# render because the VLM only needs ~256-512 px per cluster member.
_THUMBNAIL_DEFAULT_SCALE = 2
_THUMBNAIL_DEFAULT_TIMEOUT_S = 60


def _build_render_script(
    screen_figma_id: str,
    hidden_node_figma_ids: list[str],
    scale: int,
) -> str:
    """Build the plugin-side JS that toggles visibility, exports the
    screen, and restores. Pure — can be tested by inspecting the
    resulting string.
    """
    ids_json = json.dumps(hidden_node_figma_ids)
    screen_id_json = json.dumps(screen_figma_id)
    return f"""
await figma.loadAllPagesAsync();
const screenNode = await figma.getNodeByIdAsync({screen_id_json});
if (!screenNode) {{
  return {{ __ok: false, reason: 'screen not found' }};
}}

// Collect nodes to toggle: each target + every ancestor up to the
// screen root (exclusive). Record originals so we can restore.
const toRestore = [];
const targetIds = {ids_json};
for (const nid of targetIds) {{
  let node = await figma.getNodeByIdAsync(nid);
  while (node && node.id !== screenNode.id) {{
    if ('visible' in node && node.visible === false) {{
      toRestore.push(node);
      node.visible = true;
    }}
    node = node.parent;
  }}
}}

try {{
  const bytes = await screenNode.exportAsync({{
    format: 'PNG',
    constraint: {{ type: 'SCALE', value: {scale} }},
  }});
  const b64 = figma.base64Encode(bytes);
  return {{
    __ok: true,
    b64: b64,
    width: screenNode.width,
    height: screenNode.height,
    toggled: toRestore.length,
  }};
}} finally {{
  for (const node of toRestore) {{
    try {{ node.visible = false; }} catch (e) {{ /* best-effort */ }}
  }}
}}
""".strip()


def _build_node_thumbnails_script(
    figma_node_ids: list[str], scale: int,
) -> str:
    """Build the plugin-side JS that exports each requested node as a
    PNG, with a visibility toggle on the ancestor chain so hidden
    descendants of an instance subtree still render.

    Returns a JS expression returning ``{__ok: true, thumbnails: {fid: b64}}``.
    Missing nodes (resolution failed, export failed) are simply absent
    from the thumbnails dict; the Python side fills None at those
    positions.

    Same restore-in-finally contract as ``_build_render_script`` —
    every flipped visibility is restored even if export fails.
    """
    ids_json = json.dumps(figma_node_ids)
    return f"""
await figma.loadAllPagesAsync();
const targetIds = {ids_json};
const thumbnails = {{}};
const toRestore = [];

try {{
  for (const tid of targetIds) {{
    const target = await figma.getNodeByIdAsync(tid);
    if (!target) continue;

    // Walk up the parent chain making every hidden ancestor visible
    // so the export shows the target node itself.
    let cursor = target;
    while (cursor && cursor.type !== 'PAGE' && cursor.type !== 'DOCUMENT') {{
      if ('visible' in cursor && cursor.visible === false) {{
        toRestore.push(cursor);
        cursor.visible = true;
      }}
      cursor = cursor.parent;
    }}

    try {{
      const bytes = await target.exportAsync({{
        format: 'PNG',
        constraint: {{ type: 'SCALE', value: {scale} }},
      }});
      thumbnails[tid] = figma.base64Encode(bytes);
    }} catch (e) {{
      // Per-node export failed (e.g. zero-size target). Skip
      // it — the Python side will record None for this id.
    }}
  }}
  return {{ __ok: true, thumbnails: thumbnails }};
}} finally {{
  for (const node of toRestore) {{
    try {{ node.visible = false; }} catch (e) {{ /* best-effort */ }}
  }}
}}
""".strip()


def _run_node_subprocess(
    plugin_code: str, *, port: int, timeout_s: int,
) -> dict:
    """Shell out to Node.js to send PROXY_EXECUTE over WebSocket.
    Returns the parsed message dict. Raises ``RuntimeError`` on
    subprocess / connection errors.
    """
    runner = f"""
const WebSocket = require('ws');
const code = {json.dumps(plugin_code)};
const ws = new WebSocket('ws://localhost:{port}');
const timer = setTimeout(() => {{
  process.stderr.write('timeout'); process.exit(1);
}}, {timeout_s * 1000});
ws.on('open', () => {{
  ws.send(JSON.stringify({{
    type: 'PROXY_EXECUTE', id: 'hidden_render', code,
    timeout: {max(timeout_s - 5, 10) * 1000},
  }}));
}});
ws.on('message', (data) => {{
  const msg = JSON.parse(data);
  if (msg.type === 'PROXY_EXECUTE_RESULT' && msg.id === 'hidden_render') {{
    clearTimeout(timer);
    process.stdout.write(JSON.stringify(msg), () => {{
      ws.close(); process.exit(0);
    }});
  }}
}});
ws.on('error', (err) => {{
  process.stderr.write(err.message); process.exit(1);
}});
"""
    env = {**os.environ}
    result = subprocess.run(
        ["node", "-e", runner],
        capture_output=True, text=True,
        timeout=timeout_s + 10, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"node subprocess failed: {result.stderr[:200]}"
        )
    return json.loads(result.stdout or "{}")


def render_screen_with_visible_nodes(
    *,
    screen_figma_id: str,
    hidden_node_figma_ids: list[str],
    scale: int = _DEFAULT_SCALE,
    port: int = _DEFAULT_PORT,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> Optional[bytes]:
    """Render the screen with each hidden node (and its ancestor
    chain) temporarily flipped visible=true.

    Returns PNG bytes on success. Returns ``None`` on any failure
    so callers can cleanly fall back to the non-plugin path —
    connection refused (plugin off), Node binary missing, plugin
    reports ``__ok=false``, subprocess times out, invalid JSON.

    On a plugin-side error (bridge is up but no Figma file is
    connected, node not found, etc.) the specific reason is
    attached to the returned object as ``last_error`` on the
    function — a best-effort breadcrumb for callers that want to
    surface a human-readable hint.
    """
    plugin_code = _build_render_script(
        screen_figma_id, hidden_node_figma_ids, scale,
    )

    def _once() -> tuple[Optional[dict], Optional[str]]:
        try:
            return _run_node_subprocess(
                plugin_code, port=port, timeout_s=timeout_s,
            ), None
        except (RuntimeError, FileNotFoundError, subprocess.TimeoutExpired,
                json.JSONDecodeError) as e:
            return None, str(e)

    msg, exc_err = _once()
    # A successful subprocess can still return a bridge-level error
    # payload (e.g. "Unable to establish connection ..."). Detect
    # and retry those once with a short backoff.
    bridge_err = (msg or {}).get("error") if isinstance(msg, dict) else None
    retryable = _is_transient(exc_err) or _is_transient(bridge_err)
    if msg is None and not retryable:
        render_screen_with_visible_nodes.last_error = exc_err  # type: ignore[attr-defined]
        return None
    if retryable:
        time.sleep(3)
        msg, exc_err = _once()
        if msg is None:
            render_screen_with_visible_nodes.last_error = exc_err  # type: ignore[attr-defined]
            return None

    # Bridge-level error (no file connected, disconnected, …).
    top_err = msg.get("error") if isinstance(msg, dict) else None
    if top_err:
        render_screen_with_visible_nodes.last_error = str(top_err)  # type: ignore[attr-defined]
        return None

    # PROXY_EXECUTE wraps in {success, result}; inner result is our
    # {__ok, b64, ...} payload.
    inner = msg.get("result", {})
    if isinstance(inner, dict) and inner.get("success") is False:
        render_screen_with_visible_nodes.last_error = str(  # type: ignore[attr-defined]
            inner.get("error") or "plugin execution failed"
        )
        return None
    result = inner.get("result", inner) if isinstance(inner, dict) else None
    if not isinstance(result, dict) or not result.get("__ok"):
        render_screen_with_visible_nodes.last_error = str(  # type: ignore[attr-defined]
            (result or {}).get("reason")
            or (result or {}).get("error")
            or "plugin returned no ok payload"
        )
        return None

    b64 = result.get("b64")
    if not isinstance(b64, str):
        render_screen_with_visible_nodes.last_error = "no b64 in result"  # type: ignore[attr-defined]
        return None
    try:
        data = base64.b64decode(b64)
    except (ValueError, TypeError) as e:
        render_screen_with_visible_nodes.last_error = str(e)  # type: ignore[attr-defined]
        return None
    render_screen_with_visible_nodes.last_error = None  # type: ignore[attr-defined]
    return data


# Exposed so callers can peek at the most recent failure reason
# without having to thread it through the return type.
render_screen_with_visible_nodes.last_error = None  # type: ignore[attr-defined]


def render_node_thumbnails(
    *,
    figma_node_ids: list[str],
    scale: int = _THUMBNAIL_DEFAULT_SCALE,
    port: int = _DEFAULT_PORT,
    timeout_s: int = _THUMBNAIL_DEFAULT_TIMEOUT_S,
) -> list[Optional[bytes]]:
    """Render PNG thumbnails for each requested node.

    Used by the VLM image_provider in cluster_variants — the model
    needs to see cluster members, and the bridge is the only path
    that can render hidden / nested-instance nodes reliably.

    Returns a list parallel to ``figma_node_ids``: PNG bytes per
    node, or None where rendering failed (node missing, export
    failed, subprocess error). Position is preserved so callers
    can correlate with their original input order.

    Empty input → empty output, no subprocess call.
    Total subprocess failure → all-None list of length matching input.
    Per-node failure → that index becomes None.
    """
    if not figma_node_ids:
        return []

    plugin_code = _build_node_thumbnails_script(figma_node_ids, scale)

    def _once() -> tuple[Optional[dict], Optional[str]]:
        try:
            return _run_node_subprocess(
                plugin_code, port=port, timeout_s=timeout_s,
            ), None
        except (RuntimeError, FileNotFoundError, subprocess.TimeoutExpired,
                json.JSONDecodeError) as e:
            return None, str(e)

    msg, exc_err = _once()
    bridge_err = (msg or {}).get("error") if isinstance(msg, dict) else None
    retryable = _is_transient(exc_err) or _is_transient(bridge_err)
    if msg is None and not retryable:
        render_node_thumbnails.last_error = exc_err  # type: ignore[attr-defined]
        return [None] * len(figma_node_ids)
    if retryable:
        time.sleep(3)
        msg, exc_err = _once()
        if msg is None:
            render_node_thumbnails.last_error = exc_err  # type: ignore[attr-defined]
            return [None] * len(figma_node_ids)

    top_err = msg.get("error") if isinstance(msg, dict) else None
    if top_err:
        render_node_thumbnails.last_error = str(top_err)  # type: ignore[attr-defined]
        return [None] * len(figma_node_ids)

    inner = msg.get("result", {})
    if isinstance(inner, dict) and inner.get("success") is False:
        render_node_thumbnails.last_error = str(  # type: ignore[attr-defined]
            inner.get("error") or "plugin execution failed"
        )
        return [None] * len(figma_node_ids)
    result = inner.get("result", inner) if isinstance(inner, dict) else None
    if not isinstance(result, dict) or not result.get("__ok"):
        render_node_thumbnails.last_error = str(  # type: ignore[attr-defined]
            (result or {}).get("reason")
            or (result or {}).get("error")
            or "plugin returned no ok payload"
        )
        return [None] * len(figma_node_ids)

    thumbnails = result.get("thumbnails")
    if not isinstance(thumbnails, dict):
        render_node_thumbnails.last_error = "no thumbnails dict in result"  # type: ignore[attr-defined]
        return [None] * len(figma_node_ids)

    out: list[Optional[bytes]] = []
    for fid in figma_node_ids:
        b64 = thumbnails.get(fid)
        if not isinstance(b64, str):
            out.append(None)
            continue
        try:
            out.append(base64.b64decode(b64))
        except (ValueError, TypeError):
            out.append(None)

    render_node_thumbnails.last_error = None  # type: ignore[attr-defined]
    return out


render_node_thumbnails.last_error = None  # type: ignore[attr-defined]
