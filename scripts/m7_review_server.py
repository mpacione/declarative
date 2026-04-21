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
# Only successful fetches cached; None results are NOT cached so the
# next request retries. This lets a user refresh-and-rescroll to
# recover from Figma rate-limit bursts.
_SCREENSHOT_CACHE: dict[str, bytes] = {}
_CACHE_LOCK = threading.Lock()
# Cap concurrent Figma REST calls so the browser's parallel image
# loader doesn't burst-overrun the 60-req/min rate limit. 3 is
# empirical — enough throughput to keep up with lazy-load scroll
# speed, low enough to avoid 429 storms.
_FETCH_SEMAPHORE = threading.BoundedSemaphore(3)
_FETCHER_INSTANCE: Any = None


def _get_fetcher():
    """Build the Figma fetcher once per process; reuse the underlying
    requests.Session for connection pooling.
    """
    global _FETCHER_INSTANCE
    if _FETCHER_INSTANCE is None:
        from dd.cli import make_figma_screenshot_fetcher
        # scale=4 → 16x source pixels per Figma coord. Tiny 16x16 nodes
        # become 64x64 source pixels, which upscale cleanly instead of
        # turning into a grey blob. Cost: bigger PNGs from Figma, but
        # those are client-side-only (cached in-process).
        _FETCHER_INSTANCE = make_figma_screenshot_fetcher(scale=4)
    return _FETCHER_INSTANCE


def _find_screen_figma_id(figma_node_id: str) -> str | None:
    """Look up the screen ancestor's figma_node_id for fallback.

    Figma REST can't render deep descendant frames (e.g. 16×16
    child nodes inside component masters); it returns null. For
    those, we render the SCREEN instead so the user has SOMETHING
    visual to ground the decision.
    """
    conn = get_connection(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT s.figma_node_id
            FROM nodes n
            JOIN screens s ON s.id = n.screen_id
            WHERE n.figma_node_id = ?
            LIMIT 1
            """,
            (figma_node_id,),
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _get_crop_info(sci_id: int) -> tuple[str, float, float, float, float, float, float, float, str, int, int] | None:
    """Look up crop metadata for a flagged sci row.

    Node x/y are stored in ABSOLUTE Figma canvas coords; to crop
    against the screen image we subtract the screen root node's
    own (x, y) origin.

    Returns (screen_figma_id, node_x_in_screen, node_y_in_screen,
    node_width, node_height, screen_width, screen_height, rotation,
    node_figma_id, visible_self, visible_effective). Returns None
    if row missing / bbox null.

    Visibility bits let the renderer pick the right crop strategy:
    visible_effective=1 → screen-level spotlight crop; self=1 &
    effective=0 → per-node Figma render (ancestor hid it); self=0
    → can't render, caller should show a placeholder.
    """
    conn = get_connection(DB_PATH)
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
    rotation = float(rot) if rot is not None else 0.0
    return (
        fig_id, float(nx) - rx, float(ny) - ry, float(nw),
        float(nh), float(sw), float(sh), rotation,
        node_fig_id or "", int(vis_self or 0), int(vis_eff or 0),
    )


def _crop_to_bbox(
    screen_png: bytes,
    node_x: float, node_y: float, node_width: float, node_height: float,
    screen_width: float, screen_height: float,
    *,
    padding_px: int = 40,
    rotation: float = 0.0,
) -> bytes:
    """Delegate to ``dd.classify_vision_crop.crop_node_with_spotlight``
    so the classifier pipeline and the review UI share one crop
    implementation. When ``rotation`` is non-zero the spotlight draws
    a rotated polygon matching the actual rendered element.
    """
    from dd.classify_vision_crop import crop_node_with_spotlight
    return crop_node_with_spotlight(
        screen_png=screen_png,
        node_x=node_x, node_y=node_y,
        node_width=node_width, node_height=node_height,
        screen_width=screen_width, screen_height=screen_height,
        padding_px=padding_px, rotation=rotation,
    )


_CROP_CACHE: dict[int, bytes] = {}


def _fetch_crop_for_sci(sci_id: int) -> bytes | None:
    """Serve a cropped node image via the screen screenshot + bbox.

    Cheaper than per-node screenshots from Figma (one REST call per
    screen, reused across all that screen's flagged nodes) AND works
    for the 90% of flagged nodes where Figma won't render the node
    directly.
    """
    with _CACHE_LOCK:
        cached = _CROP_CACHE.get(sci_id)
    if cached is not None:
        return cached

    info = _get_crop_info(sci_id)
    if info is None:
        return None
    (fig_id, nx, ny, nw, nh, sw, sh, rotation,
     node_fig_id, vis_self, vis_eff) = info

    # Visibility dispatch:
    # - effective visible: screen-level spotlight crop (existing).
    # - ancestor-hidden (self=1, eff=0): fetch per-node render (Figma
    #   REST renders standalone when only an ancestor is hidden).
    # - self-hidden (self=0): Figma refuses — return a placeholder
    #   PNG so the UI shows "hidden" rather than 404.
    fetcher = _get_fetcher()

    if not vis_self:
        cropped = _hidden_placeholder_png(nw, nh)
        with _CACHE_LOCK:
            _CROP_CACHE[sci_id] = cropped
        return cropped

    if not vis_eff and node_fig_id:
        with _FETCH_SEMAPHORE:
            try:
                per_node = fetcher(FILE_KEY, node_fig_id)
            except Exception:
                per_node = None
        if per_node is None:
            cropped = _hidden_placeholder_png(nw, nh)
        else:
            cropped = per_node
        with _CACHE_LOCK:
            _CROP_CACHE[sci_id] = cropped
        return cropped

    # Fetch the SCREEN's screenshot (cached in _SCREENSHOT_CACHE).
    with _CACHE_LOCK:
        screen_png = _SCREENSHOT_CACHE.get(fig_id)
    if screen_png is None:
        with _FETCH_SEMAPHORE:
            try:
                screen_png = fetcher(FILE_KEY, fig_id)
            except Exception:
                screen_png = None
        if screen_png is None:
            return None
        with _CACHE_LOCK:
            _SCREENSHOT_CACHE[fig_id] = screen_png

    try:
        cropped = _crop_to_bbox(
            screen_png, nx, ny, nw, nh, sw, sh, rotation=rotation,
        )
    except Exception:
        return None

    with _CACHE_LOCK:
        _CROP_CACHE[sci_id] = cropped
    return cropped


def _hidden_placeholder_png(width: float, height: float) -> bytes:
    """Produce a small diagonal-hatched PNG with a '(hidden)' label
    for nodes Figma refuses to render (self-invisible). Lets the UI
    signal the invisibility rather than silently 404 the image.
    """
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


def _fetch_screenshot_cached(figma_node_id: str) -> bytes | None:
    """Fetch + cache a Figma node screenshot. Falls back to the
    parent screen's screenshot when the node itself can't be
    rendered (common for deep child frames). Successful fetches
    cached in-memory; failures NOT cached so a refresh retries.
    """
    with _CACHE_LOCK:
        if figma_node_id in _SCREENSHOT_CACHE:
            return _SCREENSHOT_CACHE[figma_node_id]

    fetcher = _get_fetcher()

    with _FETCH_SEMAPHORE:
        try:
            data = fetcher(FILE_KEY, figma_node_id)
        except Exception:
            data = None

    if data is None:
        # Fall back to the node's screen ancestor.
        screen_fig_id = _find_screen_figma_id(figma_node_id)
        if screen_fig_id:
            # Screen screenshots are cached too; check first.
            with _CACHE_LOCK:
                cached_screen = _SCREENSHOT_CACHE.get(screen_fig_id)
            if cached_screen is not None:
                data = cached_screen
            else:
                with _FETCH_SEMAPHORE:
                    try:
                        data = fetcher(FILE_KEY, screen_fig_id)
                    except Exception:
                        data = None
                if data is not None:
                    with _CACHE_LOCK:
                        _SCREENSHOT_CACHE[screen_fig_id] = data

    if data is not None:
        with _CACHE_LOCK:
            _SCREENSHOT_CACHE[figma_node_id] = data
    return data


def _load_catalog_types(conn: sqlite3.Connection) -> list[str]:
    """Fetch every canonical_name from component_type_catalog + the
    two catch-alls. Used to populate the override-input's <datalist>
    so the reviewer sees existing types as suggestions — prevents
    vocabulary drift (typing `list-row` when `list_item` exists).
    """
    rows = conn.execute(
        "SELECT canonical_name FROM component_type_catalog "
        "ORDER BY canonical_name"
    ).fetchall()
    out = [r[0] for r in rows]
    # Catch-alls that aren't in the catalog table itself.
    for extra in ("container", "unsure"):
        if extra not in out:
            out.append(extra)
    return out


def _load_flagged(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Group flagged rows by (llm_type, ps_type, cs_type, node_name).

    Returns one representative row per group, with two extra fields:
    - `group_sci_ids`: list of ALL sci_ids in the group (for bulk apply).
    - `group_size`: len(group_sci_ids).
    - `group_screens`: sorted list of distinct screen_ids in the group
      (surfaced in the UI so the reviewer can eyeball spread).

    Rows where the node isn't part of any multi-instance pattern still
    appear as singletons (group_size=1).
    """
    raw = fetch_flagged_rows(conn)
    by_key: dict[tuple, list[dict[str, Any]]] = {}
    for r in raw:
        key = (
            r.get("llm_type"),
            r.get("vision_ps_type"),
            r.get("vision_cs_type"),
            r.get("node_name"),
        )
        by_key.setdefault(key, []).append(r)

    grouped: list[dict[str, Any]] = []
    for members in by_key.values():
        # Representative = first row. Copy + enrich.
        rep = dict(members[0])
        rep["group_sci_ids"] = [m["sci_id"] for m in members]
        rep["group_size"] = len(members)
        rep["group_screens"] = sorted({m["screen_id"] for m in members})
        grouped.append(rep)

    # Sort by group_size descending — big groups first so the reviewer
    # tackles high-impact patterns up front.
    grouped.sort(key=lambda r: -r["group_size"])
    return grouped


def _render_index(rows: list[dict[str, Any]], catalog: list[str]) -> str:
    """Render the full interactive HTML page."""
    cards = "\n".join(_render_card(r) for r in rows)
    total = len(rows)
    datalist_options = "\n".join(
        f'<option value="{html.escape(t)}"/>' for t in catalog
    )
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
  .review-card.novel .saved-badge {{ color: #7c3aed; font-size: 12px; }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    background: #fef3c7; color: #92400e; font-size: 11px;
  }}
  .group-badge {{
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    background: #dbeafe; color: #1e40af; font-size: 11px;
    font-weight: 600; margin-left: 4px;
  }}
  .group-screens {{
    font-size: 11px; color: #9ca3af; margin-bottom: 8px;
    font-family: -apple-system-monospace, monospace;
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
<datalist id="catalog-types">
  {datalist_options}
</datalist>
<main id="cards">
  {cards}
</main>
<script>
const total = {total};
let done = 0;

function cardOf(el) {{
  return el.closest ? el.closest('.review-card') : el;
}}
function sciIdsFor(card) {{
  try {{ return JSON.parse(card.dataset.group); }}
  catch (e) {{ return [parseInt(card.dataset.sci, 10)]; }}
}}

function update(card, decisionType, sourceAccepted, canonicalType, notes) {{
  const sciIds = sciIdsFor(card);
  const body = {{sci_ids: sciIds, decision_type: decisionType}};
  if (sourceAccepted) body.source_accepted = sourceAccepted;
  if (canonicalType) body.decision_canonical_type = canonicalType;
  if (notes) body.notes = notes;
  return fetch('/api/review', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body),
  }}).then(r => r.json()).then(res => {{
    if (res.ok) {{
      card.classList.add('done');
      if (res.is_novel) {{
        card.classList.add('novel');
        const badge = card.querySelector('.saved-badge');
        if (badge) {{
          const sim = (res.similar_existing || []).join(', ');
          badge.textContent = '✨ saved (new type' + (sim ? ` — similar: ${{sim}}` : '') + ')';
        }}
      }}
      done += sciIds.length;
      document.getElementById('progress-done').textContent = done;
    }} else {{
      alert('Save failed: ' + (res.error || 'unknown'));
    }}
  }});
}}

function pickSource(el, source, type) {{
  update(cardOf(el), 'accept_source', source, type, null);
}}
function overrideType(el) {{
  const card = cardOf(el);
  const type = card.querySelector('.override-input').value.trim();
  if (!type) {{ alert('Enter a canonical type'); return; }}
  update(card, 'override', null, type, null);
}}
function markUnsure(el) {{ update(cardOf(el), 'unsure', null, null, null); }}
function markNotUi(el) {{ update(cardOf(el), 'override', null, 'not_ui', 'not a UI element'); }}
function skipRow(el)   {{ update(cardOf(el), 'skip', null, null, null); }}

document.addEventListener('keydown', (e) => {{
  if (e.target.tagName === 'INPUT') return;
  const firstOpen = document.querySelector('.review-card:not(.done)');
  if (!firstOpen) return;
  firstOpen.scrollIntoView({{behavior: 'smooth', block: 'start'}});
  if (e.key === '1') firstOpen.querySelector('.source-llm').click();
  if (e.key === '2') firstOpen.querySelector('.source-ps').click();
  if (e.key === '3') firstOpen.querySelector('.source-cs').click();
  if (e.key === 'u') markUnsure(firstOpen);
  if (e.key === 'n') markNotUi(firstOpen);
  if (e.key === 's') skipRow(firstOpen);
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
    group_ids_json = html.escape(json.dumps(row.get("group_sci_ids", [sci])))
    group_size = row.get("group_size", 1)
    group_screens = row.get("group_screens", [row["screen_id"]])
    screens_summary = (
        f"{len(group_screens)} screens: {', '.join(str(s) for s in group_screens[:6])}"
        + (" …" if len(group_screens) > 6 else "")
    )
    group_badge = (
        f'<span class="group-badge">× {group_size} instances</span>'
        if group_size > 1 else ""
    )
    return f"""
<section class="review-card" data-sci="{sci}" data-group='{group_ids_json}'>
  <span class="saved-badge">✓ saved ({group_size})</span>
  <div class="screenshot">
    <img src="/api/crop/{sci}" loading="lazy"
         onerror="this.outerHTML='<div class=\\'no-preview\\'>(no screenshot)</div>'"
         alt="screenshot"/>
  </div>
  <div>
    <div class="meta">
      <span class="badge">{html.escape(row['consensus_method'] or '')}</span>
      {group_badge}
      name=<code>{html.escape(row['node_name'] or '')}</code>
      <a href="{html.escape(deep_link)}">Open in Figma</a>
    </div>
    <div class="group-screens">{html.escape(screens_summary)}</div>
    <div class="sources">
      <div class="source source-llm" onclick="pickSource(this, 'llm', '{html.escape(llm_type)}')">
        <div class="label">LLM</div>
        <div class="type">{html.escape(llm_type)}</div>
        <div class="confidence">confidence: {llm_conf}</div>
        <div class="reason">{llm_reason}</div>
      </div>
      <div class="source source-ps" onclick="pickSource(this, 'vision_ps', '{html.escape(ps_type)}')">
        <div class="label">Vision PS</div>
        <div class="type">{html.escape(ps_type)}</div>
        <div class="confidence">confidence: {ps_conf}</div>
        <div class="reason">{ps_reason}</div>
      </div>
      <div class="source source-cs" onclick="pickSource(this, 'vision_cs', '{html.escape(cs_type)}')">
        <div class="label">Vision CS</div>
        <div class="type">{html.escape(cs_type)}</div>
        <div class="confidence">confidence: {cs_conf}</div>
        <div class="reason">{cs_reason}</div>
      </div>
    </div>
    <div class="actions">
      <input type="text" class="override-input" list="catalog-types"
             placeholder="override type (type to filter catalog)"
             autocomplete="off"/>
      <button onclick="overrideType(this)">Override all {group_size}</button>
      <button onclick="markNotUi(this)" title="Flag as not-UI (press N)">Not UI</button>
      <button onclick="markUnsure(this)">Unsure</button>
      <button onclick="skipRow(this)">Skip</button>
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
            catalog = _load_catalog_types(conn)
            conn.close()
            html_body = _render_index(rows, catalog).encode("utf-8")
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
        if self.path.startswith("/api/crop/"):
            try:
                sci_id = int(self.path[len("/api/crop/"):])
            except ValueError:
                self._send(400, b"bad sci_id", "text/plain")
                return
            data = _fetch_crop_for_sci(sci_id)
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
        # Accept either a single sci_id (legacy) or a list sci_ids
        # (new bulk-apply path for pattern-grouped cards).
        sci_ids = body.get("sci_ids")
        sci_id = body.get("sci_id")
        decision_type = body.get("decision_type")
        source_accepted = body.get("source_accepted")
        canonical_type = body.get("decision_canonical_type")
        notes = body.get("notes")
        if sci_ids is None and isinstance(sci_id, int):
            sci_ids = [sci_id]
        if not isinstance(sci_ids, list) or not all(
            isinstance(x, int) for x in sci_ids
        ):
            self._send_json(400, {
                "ok": False,
                "error": "sci_ids (list[int]) or sci_id (int) required",
            })
            return
        if not isinstance(decision_type, str):
            self._send_json(400, {
                "ok": False, "error": "decision_type (str) required",
            })
            return

        # Vocabulary-drift check: on override, if the typed type isn't
        # in the catalog, check for a close match. Block the save
        # unless the client confirms via `accept_new: true`. Catches
        # `list-row` before it leaks into the DB as a novel duplicate
        # of `list_item`. Pattern: difflib.get_close_matches cutoff
        # 0.7 per the annotation-tooling research (Unilexicon,
        # Smartlogic, PoolParty all use this shape).
        # Vocabulary-drift tracking: novel override types get logged
        # for periodic catalog review. No interruption — the datalist
        # on the input already shows existing types as a pre-emptive
        # suggestion while typing; if the reviewer commits anyway,
        # trust them. Client gets back `is_novel: true` in the
        # response so the UI can mark the card visually.
        is_novel = False
        similar_existing: list[str] = []
        if (
            decision_type == "override"
            and isinstance(canonical_type, str)
        ):
            conn = get_connection(DB_PATH)
            catalog = _load_catalog_types(conn)
            conn.close()
            if canonical_type not in catalog:
                is_novel = True
                import difflib
                similar_existing = difflib.get_close_matches(
                    canonical_type, catalog, n=3, cutoff=0.5,
                )
                try:
                    with open(
                        "render_batch/proposed_types.jsonl", "a",
                    ) as f:
                        f.write(json.dumps({
                            "typed": canonical_type,
                            "sci_ids": sci_ids,
                            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "similar_existing": similar_existing,
                        }) + "\n")
                except Exception:
                    pass

        try:
            conn = get_connection(DB_PATH)
            for sid in sci_ids:
                record_review_decision(
                    conn,
                    sci_id=sid,
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
        self._send_json(200, {
            "ok": True,
            "applied": len(sci_ids),
            "is_novel": is_novel,
            "similar_existing": similar_existing,
        })


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
