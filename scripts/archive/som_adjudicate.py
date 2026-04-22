"""HTML adjudicator for SoM vs Vision-PS disagreements.

Reads the SoM bake-off's per-rep JSONL + the live DB, shows each
disagreement as a card with:
  - Node crop (reused from the review server's spotlight pipeline)
  - SoM verdict + confidence + reason
  - PS verdict + confidence + reason
  - Buttons: [SoM ✓] [PS ✓] [Both wrong → override] [Equivalent] [Skip]

Saves judgments to a JSONL file. Ctrl-C when done; the script prints
a summary showing who won more often + per-type win rates.

Usage::

    # After running m7_bakeoff_som.py with --jsonl-out:
    .venv/bin/python3 -m scripts.som_adjudicate \\
        --db Dank-EXP-02.declarative.db \\
        --results render_batch/m7_bakeoff_som_results.jsonl \\
        [--port 8766] \\
        [--judgments-out render_batch/som_adjudication.jsonl]
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import sqlite3
import sys
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


DB_PATH: str = ""
FILE_KEY: str = ""
JUDGMENTS_PATH: str = ""
_DISAGREEMENTS: list[dict[str, Any]] = []
_JUDGMENTS_LOCK = threading.Lock()
_CROP_CACHE: dict[int, bytes] = {}
_CROP_LOCK = threading.Lock()
_FETCHER = None
_FETCH_SEM = threading.BoundedSemaphore(3)


def _load_disagreements(
    results_path: str, conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Join bake-off results with DB-side reason columns for PS."""
    out: list[dict[str, Any]] = []
    with open(results_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if not r.get("som_type") or not r.get("vision_ps_type"):
                continue
            if r["som_type"] == r["vision_ps_type"]:
                continue
            ps_row = conn.execute(
                "SELECT vision_ps_confidence, vision_ps_reason "
                "FROM screen_component_instances WHERE id = ?",
                (r["sci_id"],),
            ).fetchone()
            r["vision_ps_confidence"] = ps_row[0] if ps_row else None
            r["vision_ps_reason"] = ps_row[1] if ps_row else None
            out.append(r)
    return out


def _fetch_and_crop(sci_id: int) -> bytes | None:
    """Spotlight crop for a given sci row. Mirrors the review server
    pipeline (rotation-aware, scale=4 screenshots, 800px upscale).
    """
    global _FETCHER
    with _CROP_LOCK:
        if sci_id in _CROP_CACHE:
            return _CROP_CACHE[sci_id]
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    try:
        row = conn.execute(
            """
            WITH RECURSIVE invisible_subtree(id) AS (
                SELECT id FROM nodes
                WHERE screen_id = (SELECT screen_id FROM screen_component_instances WHERE id = ?)
                  AND COALESCE(visible, 1) = 0
                UNION ALL
                SELECT n.id FROM nodes n
                JOIN invisible_subtree inv ON n.parent_id = inv.id
            )
            SELECT s.figma_node_id, s.width, s.height,
                   n.x, n.y, n.width, n.height, n.rotation,
                   root.x AS root_x, root.y AS root_y,
                   n.figma_node_id AS node_figma_id,
                   COALESCE(n.visible, 1) AS visible_self,
                   CASE WHEN n.id IN (SELECT id FROM invisible_subtree)
                        THEN 0 ELSE 1 END AS visible_effective
            FROM screen_component_instances sci
            JOIN nodes n ON n.id = sci.node_id
            JOIN screens s ON s.id = sci.screen_id
            LEFT JOIN nodes root
              ON root.screen_id = s.id AND root.parent_id IS NULL
            WHERE sci.id = ?
            """,
            (sci_id, sci_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    (fig_id, sw, sh, nx, ny, nw, nh, rot, rx, ry,
     node_fig_id, vis_self, vis_eff) = row
    if None in (fig_id, sw, sh, nx, ny, nw, nh):
        return None
    rx = float(rx) if rx is not None else 0.0
    ry = float(ry) if ry is not None else 0.0

    if _FETCHER is None:
        from dd.cli import make_figma_screenshot_fetcher
        _FETCHER = make_figma_screenshot_fetcher(scale=4)

    # Visibility dispatch — same strategy as the classifier path:
    # screen-crop for visible; per-node render for ancestor-hidden;
    # plugin render-toggle for self-hidden (with a placeholder as
    # last-resort fallback when the plugin bridge is unavailable).
    if not vis_self:
        out: bytes | None = None
        if node_fig_id:
            try:
                from dd.checkerboard import composite_on_checkerboard
                from dd.classify_vision_crop import crop_node_with_spotlight
                from dd.plugin_render import render_screen_with_visible_nodes
                toggled = render_screen_with_visible_nodes(
                    screen_figma_id=fig_id,
                    hidden_node_figma_ids=[node_fig_id],
                    scale=2,
                )
                if toggled is not None:
                    composited = composite_on_checkerboard(toggled)
                    out = crop_node_with_spotlight(
                        screen_png=composited,
                        node_x=float(nx) - rx, node_y=float(ny) - ry,
                        node_width=float(nw), node_height=float(nh),
                        screen_width=float(sw), screen_height=float(sh),
                        rotation=float(rot) if rot else 0.0,
                    )
            except Exception:
                out = None
        if out is None:
            out = _hidden_placeholder_png(float(nw), float(nh))
        with _CROP_LOCK:
            _CROP_CACHE[sci_id] = out
        return out

    if not vis_eff and node_fig_id:
        with _FETCH_SEM:
            try:
                out = _FETCHER(FILE_KEY, node_fig_id)
            except Exception:
                out = None
        if out is None:
            out = _hidden_placeholder_png(float(nw), float(nh))
        with _CROP_LOCK:
            _CROP_CACHE[sci_id] = out
        return out

    with _FETCH_SEM:
        try:
            screen_png = _FETCHER(FILE_KEY, fig_id)
        except Exception:
            screen_png = None
    if screen_png is None:
        return None

    from dd.classify_vision_crop import crop_node_with_spotlight
    try:
        out = crop_node_with_spotlight(
            screen_png=screen_png,
            node_x=float(nx) - rx, node_y=float(ny) - ry,
            node_width=float(nw), node_height=float(nh),
            screen_width=float(sw), screen_height=float(sh),
            rotation=float(rot) if rot else 0.0,
        )
    except Exception:
        return None
    with _CROP_LOCK:
        _CROP_CACHE[sci_id] = out
    return out


def _hidden_placeholder_png(width: float, height: float) -> bytes:
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont
    w = max(240, int(width) if width else 240)
    h = max(160, int(height) if height else 160)
    img = Image.new("RGB", (w, h), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    for i in range(-h, w, 14):
        draw.line([(i, 0), (i + h, h)], fill=(220, 220, 220), width=2)
    text = "hidden node\n(visible=0 in Figma)"
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", max(13, w // 20),
        )
    except (OSError, IOError):
        font = ImageFont.load_default()
    draw.multiline_text(
        (w // 2, h // 2), text, fill=(90, 90, 90), font=font,
        anchor="mm", align="center",
    )
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _already_judged_sci_ids() -> set[int]:
    """Read the judgments JSONL and return sci_ids already resolved
    so a refresh doesn't re-surface them.
    """
    out: set[int] = set()
    if not Path(JUDGMENTS_PATH).exists():
        return out
    with open(JUDGMENTS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                sid = r.get("sci_id")
                if isinstance(sid, int):
                    out.add(sid)
            except Exception:
                continue
    return out


def _record_judgment(record: dict[str, Any]) -> None:
    record["decided_at"] = time.time()
    with _JUDGMENTS_LOCK:
        with open(JUDGMENTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def _render_page() -> str:
    judged = _already_judged_sci_ids()
    pending = [d for d in _DISAGREEMENTS if d["sci_id"] not in judged]
    cards = "\n".join(_render_card(d) for d in pending)
    summary = _summary_stats(judged)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>SoM vs PS adjudication</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font: 14px/1.5 -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; background: #f8f9fa; margin: 0; padding: 0; color: #1f2937; }}
  header {{ position: sticky; top: 0; background: white; padding: 12px 24px; border-bottom: 1px solid #e5e7eb; z-index: 10; }}
  h1 {{ margin: 0; font-size: 16px; }}
  .count {{ color: #6b7280; font-weight: normal; margin-left: 8px; }}
  main {{ padding: 24px; max-width: 1200px; margin: 0 auto; }}
  .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; margin-bottom: 16px; display: grid; grid-template-columns: 360px 1fr; gap: 20px; }}
  .card.done {{ opacity: 0.35; }}
  .crop {{ border-radius: 6px; overflow: hidden; border: 1px solid #e5e7eb; background: #000; }}
  .crop img {{ display: block; width: 100%; height: auto; }}
  .meta {{ color: #6b7280; font-size: 13px; margin-bottom: 8px; }}
  .badge {{ background: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
  .verdicts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 14px 0; }}
  .verdict {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }}
  .verdict.som {{ background: #fef2f2; border-color: #fecaca; }}
  .verdict.ps {{ background: #eff6ff; border-color: #bfdbfe; }}
  .label {{ font-size: 11px; font-weight: 700; letter-spacing: 0.06em; color: #6b7280; margin-bottom: 6px; }}
  .type {{ font-size: 18px; font-weight: 700; margin-bottom: 4px; }}
  .conf {{ font-size: 12px; color: #6b7280; margin-bottom: 8px; }}
  .reason {{ font-size: 13px; color: #374151; }}
  .actions {{ display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }}
  button {{ padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; background: white; cursor: pointer; font-size: 14px; }}
  button:hover {{ background: #f3f4f6; }}
  button.primary {{ background: #1f2937; color: white; border-color: #1f2937; }}
  button.primary:hover {{ background: #111827; }}
  input.override {{ padding: 7px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; width: 200px; }}
  .summary {{ background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px 20px; margin-bottom: 16px; }}
  .summary-row {{ display: flex; gap: 24px; font-size: 14px; }}
  .summary-row strong {{ color: #1f2937; }}
</style>
</head>
<body>
<header>
  <h1>SoM vs PS adjudication <span class="count">({len(pending)} pending / {len(judged)} judged of {len(_DISAGREEMENTS)})</span></h1>
</header>
<main>
  {summary}
  {cards}
</main>
<script>
let done = {len(judged)};
function cardOf(el) {{ return el.closest('.card'); }}
function judge(el, winner, overrideType = null) {{
  const card = cardOf(el);
  const sciId = parseInt(card.dataset.sci, 10);
  const body = {{ sci_id: sciId, winner: winner }};
  if (overrideType) body.override_type = overrideType;
  fetch('/api/judge', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(body),
  }}).then(r => r.json()).then(res => {{
    if (res.ok) {{
      card.classList.add('done');
      done++;
    }} else alert('save failed: ' + (res.error || 'unknown'));
  }});
}}
function override(el) {{
  const card = cardOf(el);
  const typ = card.querySelector('.override').value.trim();
  if (!typ) return alert('enter a canonical type');
  judge(el, 'override', typ);
}}
document.addEventListener('keydown', (e) => {{
  if (e.target.tagName === 'INPUT') return;
  const first = document.querySelector('.card:not(.done)');
  if (!first) return;
  first.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  if (e.key === 's') judge(first.querySelector('button'), 'som');
  if (e.key === 'p') judge(first.querySelector('button'), 'ps');
  if (e.key === 'e') judge(first.querySelector('button'), 'equivalent');
  if (e.key === 'k') judge(first.querySelector('button'), 'skip');
}});
</script>
</body>
</html>"""


def _summary_stats(judged_ids: set[int]) -> str:
    if not judged_ids or not Path(JUDGMENTS_PATH).exists():
        return ""
    counts: Counter[str] = Counter()
    with open(JUDGMENTS_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                counts[r.get("winner", "?")] += 1
            except Exception:
                continue
    total = sum(counts.values())
    if total == 0:
        return ""
    parts = [
        f"<strong>{counts.get('som', 0)}</strong> SoM",
        f"<strong>{counts.get('ps', 0)}</strong> PS",
        f"<strong>{counts.get('equivalent', 0)}</strong> equivalent",
        f"<strong>{counts.get('override', 0)}</strong> override",
        f"<strong>{counts.get('skip', 0)}</strong> skip",
    ]
    return (
        f'<div class="summary"><div class="summary-row">'
        f'Judged {total}: ' + ' · '.join(parts) +
        f'</div></div>'
    )


def _render_card(d: dict[str, Any]) -> str:
    name = html.escape(str(d.get("name") or "?"))
    screen_id = d["screen_id"]
    node_id = d["node_id"]
    sci_id = d["sci_id"]
    parent = html.escape(str(d.get("parent_classified_as") or "—"))
    som_type = html.escape(str(d.get("som_type") or "—"))
    som_conf = f"{float(d.get('som_confidence') or 0):.2f}"
    som_reason = html.escape(str(d.get("som_reason") or ""))
    ps_type = html.escape(str(d.get("vision_ps_type") or "—"))
    ps_conf = f"{float(d.get('vision_ps_confidence') or 0):.2f}"
    ps_reason = html.escape(str(d.get("vision_ps_reason") or ""))
    return f"""
<section class="card" data-sci="{sci_id}">
  <div class="crop">
    <img src="/api/crop/{sci_id}" alt="crop" loading="lazy"/>
  </div>
  <div>
    <div class="meta">
      <span class="badge">disagree</span>
      screen=<code>{screen_id}</code>
      node=<code>{node_id}</code>
      name=<code>{name}</code>
      parent=<code>{parent}</code>
    </div>
    <div class="verdicts">
      <div class="verdict som">
        <div class="label">SoM (full-screen)</div>
        <div class="type">{som_type}</div>
        <div class="conf">confidence: {som_conf}</div>
        <div class="reason">{som_reason}</div>
      </div>
      <div class="verdict ps">
        <div class="label">Vision PS (per-crop)</div>
        <div class="type">{ps_type}</div>
        <div class="conf">confidence: {ps_conf}</div>
        <div class="reason">{ps_reason}</div>
      </div>
    </div>
    <div class="actions">
      <button class="primary" onclick="judge(this, 'som')">SoM ✓ (S)</button>
      <button class="primary" onclick="judge(this, 'ps')">PS ✓ (P)</button>
      <button onclick="judge(this, 'equivalent')">Equivalent (E)</button>
      <input class="override" type="text" placeholder="override: type a canonical_type"/>
      <button onclick="override(this)">Override</button>
      <button onclick="judge(this, 'skip')">Skip (K)</button>
    </div>
  </div>
</section>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # quiet logs
        if len(args) > 1 and ("400" in args[1] or "500" in args[1]):
            sys.stderr.write("%s - %s\n" % (self.address_string(),
                                            format % args))

    def do_GET(self):
        if self.path == "/":
            body = _render_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/api/crop/"):
            try:
                sci_id = int(self.path.rsplit("/", 1)[-1])
            except ValueError:
                self.send_error(400, "bad sci_id")
                return
            png = _fetch_and_crop(sci_id)
            if png is None:
                self.send_error(404, "crop unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            # Crops can change between sessions (e.g. plugin path
            # toggled on for a previously-placeholder sci); disable
            # the browser cache so stale placeholders don't persist.
            self.send_header(
                "Cache-Control", "no-store, no-cache, must-revalidate",
            )
            self.end_headers()
            self.wfile.write(png)
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/api/judge":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self.send_error(400, "bad json")
            return
        sci_id = body.get("sci_id")
        winner = body.get("winner")
        if not isinstance(sci_id, int) or winner not in (
            "som", "ps", "equivalent", "override", "skip",
        ):
            self._json({"ok": False, "error": "bad payload"}, 400)
            return
        record = {"sci_id": sci_id, "winner": winner}
        if winner == "override":
            record["override_type"] = body.get("override_type")
        _record_judgment(record)
        self._json({"ok": True}, 200)

    def _json(self, payload, code):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument(
        "--results", default="render_batch/m7_bakeoff_som_results.jsonl",
    )
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--judgments-out",
        default="render_batch/som_adjudication.jsonl",
    )
    args = parser.parse_args(argv)

    global DB_PATH, FILE_KEY, JUDGMENTS_PATH, _DISAGREEMENTS
    DB_PATH = args.db
    JUDGMENTS_PATH = args.judgments_out
    Path(JUDGMENTS_PATH).parent.mkdir(parents=True, exist_ok=True)

    if not Path(args.results).exists():
        print(
            f"Results JSONL not found: {args.results}\n"
            f"Run scripts/bakeoff_som.py first (with --jsonl-out).",
            file=sys.stderr,
        )
        return 1

    from dd.db import get_connection
    conn = get_connection(args.db)
    file_row = conn.execute(
        "SELECT file_key FROM files LIMIT 1"
    ).fetchone()
    FILE_KEY = file_row[0] if file_row else ""
    _DISAGREEMENTS = _load_disagreements(args.results, conn)
    conn.close()

    print(
        f"Loaded {len(_DISAGREEMENTS)} SoM↔PS disagreements "
        f"from {args.results}.",
        flush=True,
    )
    print(f"Judgments append to: {JUDGMENTS_PATH}", flush=True)
    print(
        f"Open http://localhost:{args.port}/ in a browser. "
        f"Ctrl-C to stop.",
        flush=True,
    )

    server = ThreadingHTTPServer(("127.0.0.1", args.port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _print_summary()
    return 0


def _print_summary() -> None:
    if not Path(JUDGMENTS_PATH).exists():
        return
    counts: Counter[str] = Counter()
    with open(JUDGMENTS_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                counts[r.get("winner", "?")] += 1
            except Exception:
                continue
    total = sum(counts.values())
    if total == 0:
        return
    print(f"\nJudged {total} disagreements:")
    for k in ("som", "ps", "equivalent", "override", "skip"):
        n = counts.get(k, 0)
        pct = n / total * 100
        print(f"  {k:<12} {n:>4} ({pct:.1f}%)")
    som_vs_ps_total = counts.get("som", 0) + counts.get("ps", 0)
    if som_vs_ps_total:
        som_win = counts.get("som", 0) / som_vs_ps_total * 100
        print(
            f"\nOn direct SoM-vs-PS decisions: "
            f"SoM wins {som_win:.1f}% "
            f"({counts.get('som', 0)} / {som_vs_ps_total})"
        )


if __name__ == "__main__":
    sys.exit(main())
