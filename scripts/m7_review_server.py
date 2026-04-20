"""Interactive HTML review server for M7.0.a classification flags.

Single-file stdlib HTTP server. Renders all flagged rows as cards
with embedded screenshots (lazy-loaded from Figma REST), LLM / PS /
CS verdicts, and click-through decision buttons. Decisions POST to
`/api/review` and write to `classification_reviews`.

Usage:

    .venv/bin/python3 -m scripts.m7_review_server [--port 8765]
    # Open http://localhost:8765 in a browser.

Ctrl-C to stop. Decisions are persisted as you go; stop/resume
anytime. Reviewed rows drop out of the page on next reload.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dd.classify_review import (
    fetch_flagged_rows,
    format_figma_deep_link,
    record_review_decision,
)
from dd.db import get_connection


DB_PATH: str = ""  # set in main()
FILE_KEY: str = ""  # set in main()
_SCREENSHOT_CACHE: dict[str, bytes | None] = {}
_CACHE_LOCK = threading.Lock()


def _fetch_screenshot_cached(figma_node_id: str) -> bytes | None:
    """Fetch + cache a Figma node screenshot. Returns None on failure;
    the placeholder image is shown client-side via onerror.
    """
    with _CACHE_LOCK:
        if figma_node_id in _SCREENSHOT_CACHE:
            return _SCREENSHOT_CACHE[figma_node_id]

    # Import here so the server module stays importable even when
    # Figma credentials aren't set (the reviewer can still click
    # through verdicts without screenshots).
    from dd.cli import make_figma_screenshot_fetcher
    try:
        fetcher = make_figma_screenshot_fetcher()
        data = fetcher(FILE_KEY, figma_node_id)
    except Exception:
        data = None

    with _CACHE_LOCK:
        _SCREENSHOT_CACHE[figma_node_id] = data
    return data


def _load_flagged(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return fetch_flagged_rows(conn)


def _render_index(rows: list[dict[str, Any]]) -> str:
    """Render the full interactive HTML page."""
    cards = "\n".join(_render_card(r) for r in rows)
    total = len(rows)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>M7.0.a review — {html.escape(FILE_KEY)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
    background: #f8f9fa; margin: 0; padding: 0; color: #1f2937;
  }}
  header {{
    position: sticky; top: 0; background: white; padding: 12px 24px;
    border-bottom: 1px solid #e5e7eb; z-index: 10;
    display: flex; justify-content: space-between; align-items: center;
  }}
  header h1 {{ font-size: 16px; margin: 0; }}
  .progress {{
    font-size: 13px; color: #6b7280;
  }}
  .progress b {{ color: #111827; }}
  main {{ padding: 16px 24px; max-width: 1400px; margin: 0 auto; }}
  .review-card {{
    background: white; border: 1px solid #e5e7eb; border-radius: 8px;
    margin-bottom: 16px; padding: 16px;
    display: grid; grid-template-columns: 360px 1fr;
    gap: 16px; align-items: start; position: relative;
    transition: opacity 0.3s;
  }}
  .review-card.done {{ opacity: 0.3; pointer-events: none; }}
  .review-card .screenshot img {{
    max-width: 360px; max-height: 360px; border-radius: 4px;
    background: #f3f4f6; display: block;
  }}
  .review-card .no-preview {{
    width: 360px; height: 180px; background: #f3f4f6;
    border-radius: 4px; display: flex; align-items: center;
    justify-content: center; color: #9ca3af; font-size: 12px;
  }}
  .meta {{ font-size: 12px; color: #6b7280; margin-bottom: 8px; }}
  .meta code {{
    background: #f3f4f6; padding: 1px 4px; border-radius: 3px;
  }}
  .meta a {{ color: #2563eb; text-decoration: none; margin-left: 8px; }}
  .sources {{
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 8px; margin: 12px 0;
  }}
  .source {{
    border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px;
    background: #fafafa; cursor: pointer;
    transition: all 0.15s;
  }}
  .source:hover {{ background: #eff6ff; border-color: #2563eb; }}
  .source.selected {{
    background: #dbeafe; border-color: #2563eb; border-width: 2px;
    padding: 9px;
  }}
  .source .label {{
    font-weight: 600; color: #4b5563; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.05em;
  }}
  .source .type {{ font-size: 16px; font-weight: 600; margin: 4px 0; }}
  .source .confidence {{ color: #6b7280; font-size: 11px; }}
  .source .reason {{ margin-top: 6px; color: #374151; font-size: 12px; }}
  .actions {{
    margin-top: 8px; font-size: 13px; display: flex; gap: 6px;
    flex-wrap: wrap;
  }}
  .actions button {{
    padding: 6px 12px; border: 1px solid #d1d5db;
    background: white; border-radius: 4px; cursor: pointer;
    font: inherit; color: #374151;
  }}
  .actions button:hover {{ background: #f3f4f6; }}
  .actions button.primary {{
    background: #2563eb; color: white; border-color: #2563eb;
  }}
  .actions button.primary:hover {{ background: #1d4ed8; }}
  .actions input[type=text] {{
    padding: 6px 8px; border: 1px solid #d1d5db; border-radius: 4px;
    font: inherit; width: 180px;
  }}
  .saved-badge {{
    display: none; position: absolute; top: 8px; right: 12px;
    color: #16a34a; font-weight: 600; font-size: 13px;
  }}
  .review-card.done .saved-badge {{ display: inline; }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    background: #fef3c7; color: #92400e; font-size: 11px;
  }}
</style>
</head>
<body>
<header>
  <h1>M7.0.a review — flagged rows</h1>
  <div class="progress">
    <span id="progress-done">0</span> / <b id="progress-total">{total}</b> reviewed
  </div>
</header>
<main id="cards">
  {cards}
</main>
<script>
const total = {total};
let done = 0;

function update(sciId, decisionType, sourceAccepted, canonicalType, notes) {{
  const body = {{sci_id: sciId, decision_type: decisionType}};
  if (sourceAccepted) body.source_accepted = sourceAccepted;
  if (canonicalType) body.decision_canonical_type = canonicalType;
  if (notes) body.notes = notes;
  return fetch('/api/review', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body),
  }}).then(r => r.json()).then(res => {{
    if (res.ok) {{
      const card = document.querySelector(`[data-sci="${{sciId}}"]`);
      card.classList.add('done');
      done += 1;
      document.getElementById('progress-done').textContent = done;
    }} else {{
      alert('Save failed: ' + (res.error || 'unknown'));
    }}
  }});
}}

function pickSource(sciId, source, type) {{
  update(sciId, 'accept_source', source, type, null);
}}

function overrideType(sciId) {{
  const card = document.querySelector(`[data-sci="${{sciId}}"]`);
  const input = card.querySelector('.override-input');
  const type = input.value.trim();
  if (!type) {{ alert('Enter a canonical type'); return; }}
  update(sciId, 'override', null, type, null);
}}

function markUnsure(sciId) {{ update(sciId, 'unsure', null, null, null); }}
function skipRow(sciId)   {{ update(sciId, 'skip', null, null, null); }}

document.addEventListener('keydown', (e) => {{
  if (e.target.tagName === 'INPUT') return;
  const firstOpen = document.querySelector('.review-card:not(.done)');
  if (!firstOpen) return;
  const sciId = firstOpen.dataset.sci;
  firstOpen.scrollIntoView({{behavior: 'smooth', block: 'start'}});
  if (e.key === '1') firstOpen.querySelector('.source-llm').click();
  if (e.key === '2') firstOpen.querySelector('.source-ps').click();
  if (e.key === '3') firstOpen.querySelector('.source-cs').click();
  if (e.key === 'u') markUnsure(sciId);
  if (e.key === 's') skipRow(sciId);
}});
</script>
</body>
</html>
"""


def _render_card(row: dict[str, Any]) -> str:
    sci = row["sci_id"]
    fig_id = row["figma_node_id"]
    llm_type = row["llm_type"] or "—"
    ps_type = row["vision_ps_type"] or "—"
    cs_type = row["vision_cs_type"] or "—"
    llm_conf = f"{row['llm_confidence'] or 0:.2f}"
    ps_conf = f"{row['vision_ps_confidence'] or 0:.2f}"
    cs_conf = f"{row['vision_cs_confidence'] or 0:.2f}"
    llm_reason = html.escape(row["llm_reason"] or "")
    ps_reason = html.escape(row["vision_ps_reason"] or "")
    cs_reason = html.escape(row["vision_cs_reason"] or "")
    deep_link = format_figma_deep_link(FILE_KEY, fig_id)
    return f"""
<section class="review-card" data-sci="{sci}">
  <span class="saved-badge">✓ saved</span>
  <div class="screenshot">
    <img src="/api/screenshot/{html.escape(fig_id)}" loading="lazy"
         onerror="this.outerHTML='<div class=\\'no-preview\\'>(no screenshot)</div>'"
         alt="screenshot"/>
  </div>
  <div>
    <div class="meta">
      <span class="badge">{html.escape(row['consensus_method'] or '')}</span>
      sci_id=<code>{sci}</code>
      screen=<code>{row['screen_id']}</code> ({html.escape(row['screen_name'] or '')})
      node=<code>{html.escape(fig_id)}</code>
      name=<code>{html.escape(row['node_name'] or '')}</code>
      <a href="{html.escape(deep_link)}">Open in Figma</a>
    </div>
    <div class="sources">
      <div class="source source-llm" onclick="pickSource({sci}, 'llm', '{html.escape(llm_type)}')">
        <div class="label">LLM</div>
        <div class="type">{html.escape(llm_type)}</div>
        <div class="confidence">confidence: {llm_conf}</div>
        <div class="reason">{llm_reason}</div>
      </div>
      <div class="source source-ps" onclick="pickSource({sci}, 'vision_ps', '{html.escape(ps_type)}')">
        <div class="label">Vision PS</div>
        <div class="type">{html.escape(ps_type)}</div>
        <div class="confidence">confidence: {ps_conf}</div>
        <div class="reason">{ps_reason}</div>
      </div>
      <div class="source source-cs" onclick="pickSource({sci}, 'vision_cs', '{html.escape(cs_type)}')">
        <div class="label">Vision CS</div>
        <div class="type">{html.escape(cs_type)}</div>
        <div class="confidence">confidence: {cs_conf}</div>
        <div class="reason">{cs_reason}</div>
      </div>
    </div>
    <div class="actions">
      <input type="text" class="override-input" placeholder="override type (e.g. heading)"/>
      <button onclick="overrideType({sci})">Override</button>
      <button onclick="markUnsure({sci})">Unsure</button>
      <button onclick="skipRow({sci})">Skip</button>
    </div>
  </div>
</section>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quieter logs — only on error.
        if "400" in args[1] or "500" in args[1] if len(args) > 1 else False:
            super().log_message(format, *args)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):  # noqa: N802
        if self.path == "/":
            conn = get_connection(DB_PATH)
            rows = _load_flagged(conn)
            conn.close()
            html_body = _render_index(rows).encode("utf-8")
            self._send(200, html_body, "text/html; charset=utf-8")
            return
        if self.path.startswith("/api/screenshot/"):
            fig_id = self.path[len("/api/screenshot/"):]
            # URL-decode %3A etc.
            from urllib.parse import unquote
            fig_id = unquote(fig_id)
            data = _fetch_screenshot_cached(fig_id)
            if data is None:
                self._send(404, b"not found", "text/plain")
                return
            self._send(200, data, "image/png")
            return
        if self.path == "/api/progress":
            conn = get_connection(DB_PATH)
            total = conn.execute(
                "SELECT COUNT(*) FROM screen_component_instances "
                "WHERE flagged_for_review = 1"
            ).fetchone()[0]
            reviewed = conn.execute(
                "SELECT COUNT(DISTINCT sci_id) FROM classification_reviews"
            ).fetchone()[0]
            conn.close()
            self._send_json(200, {
                "total_flagged": total,
                "reviewed": reviewed,
                "remaining": total - reviewed,
            })
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        if self.path != "/api/review":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "bad json"})
            return
        sci_id = body.get("sci_id")
        decision_type = body.get("decision_type")
        source_accepted = body.get("source_accepted")
        canonical_type = body.get("decision_canonical_type")
        notes = body.get("notes")
        if not isinstance(sci_id, int) or not isinstance(decision_type, str):
            self._send_json(400, {
                "ok": False,
                "error": "sci_id (int) and decision_type (str) required",
            })
            return
        try:
            conn = get_connection(DB_PATH)
            record_review_decision(
                conn,
                sci_id=sci_id,
                decision_type=decision_type,
                source_accepted=source_accepted,
                decision_canonical_type=canonical_type,
                notes=notes,
            )
            conn.close()
        except sqlite3.IntegrityError as e:
            self._send_json(400, {"ok": False, "error": str(e)})
            return
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"ok": False, "error": str(e)})
            return
        self._send_json(200, {"ok": True})


def main(argv: list[str] | None = None) -> int:
    global DB_PATH, FILE_KEY

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default="Dank-EXP-02.declarative.db",
        help="Path to .declarative.db",
    )
    parser.add_argument(
        "--port", type=int, default=8765,
        help="HTTP port (default 8765)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Bind host (default 127.0.0.1 — localhost only)",
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="Don't auto-open the browser",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"Error: Database not found: {args.db}", file=sys.stderr)
        return 1

    DB_PATH = args.db
    conn = get_connection(DB_PATH)
    file_row = conn.execute("SELECT file_key FROM files LIMIT 1").fetchone()
    conn.close()
    if file_row is None:
        print("Error: No file row in DB.", file=sys.stderr)
        return 1
    FILE_KEY = file_row[0]

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"\nReview server running: {url}")
    print("Press Ctrl-C to stop. Decisions persist as you click.\n")

    if not args.no_open:
        import subprocess
        time.sleep(0.3)  # give server a tick to start
        try:
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
