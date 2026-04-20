"""Tier 1.5 classification review CLI (M7.0.a Step 6).

Walks rows flagged by three-source consensus (any_unsure or
three_way_disagreement) and asks a human to pick the winner. Every
decision writes to `classification_reviews` — the table is additive
and reversible; a later consensus view will pick the latest review.

Visual references shown per row:
- Figma deep-link (figma:// URL) printed for cmd-click in a
  terminal that supports it. Jumps straight to the node in Figma
  Desktop.
- Local PNG fetched from Figma REST and opened via `open` on macOS
  (skipped silently on other platforms).
- Inline terminal image for iTerm2 / Kitty / Ghostty (detected via
  env vars). Not implemented in v1 — hook is in place.

The module is structured so each piece is independently testable:
`format_figma_deep_link` and `detect_terminal_image_support` are pure
functions; `fetch_flagged_rows` and `record_review_decision` are DB
helpers; `run_review_tui` takes explicit `input_fn` / `output_fn`
callables so test cases drive it with a deterministic input queue.
"""

from __future__ import annotations

import base64
import html
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from typing import Any


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def format_figma_deep_link(file_key: str, figma_node_id: str) -> str:
    """Build a `figma://` URL that opens the given node in Figma
    Desktop. Colons in node IDs are URL-encoded so Figma's parser
    doesn't treat them as path separators.
    """
    if not figma_node_id:
        return f"figma://file/{file_key}"
    encoded = figma_node_id.replace(":", "%3A")
    return f"figma://file/{file_key}?node-id={encoded}"


def detect_terminal_image_support() -> str | None:
    """Return the inline-image protocol name for the current
    terminal, or None if unknown. Detection is a strict env-var
    check — real support varies by version, so callers should treat
    a positive detection as "try this protocol first" rather than a
    guarantee.
    """
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    kitty = os.environ.get("KITTY_WINDOW_ID")
    if kitty:
        return "kitty"
    if "iterm" in term_program:
        return "iterm2"
    if "ghostty" in term_program:
        return "ghostty"
    return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def fetch_flagged_rows(
    conn: sqlite3.Connection,
    *,
    screen_id: int | None = None,
    limit: int | None = None,
    include_reviewed: bool = False,
) -> list[dict[str, Any]]:
    """Return rows that three-source consensus flagged for human
    review, joined with node metadata + all three source verdicts.

    By default filters out rows that already have a row in
    `classification_reviews`. Pass ``include_reviewed=True`` to see
    all flagged rows (e.g., for a re-review pass).
    """
    params: list[Any] = []
    clauses = ["sci.flagged_for_review = 1"]

    if screen_id is not None:
        clauses.append("sci.screen_id = ?")
        params.append(screen_id)

    if not include_reviewed:
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM classification_reviews r "
            "WHERE r.sci_id = sci.id)"
        )

    where = " AND ".join(clauses)
    query = f"""
        SELECT
            sci.id           AS sci_id,
            sci.screen_id    AS screen_id,
            sci.node_id      AS node_id,
            sci.canonical_type AS canonical_type,
            sci.consensus_method AS consensus_method,
            sci.classification_source AS classification_source,
            sci.llm_type     AS llm_type,
            sci.llm_confidence AS llm_confidence,
            sci.llm_reason   AS llm_reason,
            sci.vision_ps_type AS vision_ps_type,
            sci.vision_ps_confidence AS vision_ps_confidence,
            sci.vision_ps_reason AS vision_ps_reason,
            sci.vision_cs_type AS vision_cs_type,
            sci.vision_cs_confidence AS vision_cs_confidence,
            sci.vision_cs_reason AS vision_cs_reason,
            n.figma_node_id  AS figma_node_id,
            n.name           AS node_name,
            n.node_type      AS node_type,
            s.name           AS screen_name
        FROM screen_component_instances sci
        JOIN nodes n ON n.id = sci.node_id
        JOIN screens s ON s.id = sci.screen_id
        WHERE {where}
        ORDER BY sci.screen_id, sci.id
    """
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    cursor = conn.execute(query, params)
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def record_review_decision(
    conn: sqlite3.Connection,
    *,
    sci_id: int,
    decision_type: str,
    decision_canonical_type: str | None = None,
    source_accepted: str | None = None,
    notes: str | None = None,
    decided_by: str = "human",
) -> None:
    """Insert a row into `classification_reviews`.

    The schema CHECK constraint enforces `decision_type` ∈
    {accept_source, override, unsure, skip, audit} and
    `source_accepted` ∈ {llm, vision_ps, vision_cs, formal, heuristic}
    when present.
    """
    conn.execute(
        "INSERT INTO classification_reviews "
        "(sci_id, decision_type, decision_canonical_type, "
        " source_accepted, notes, decided_by) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            sci_id, decision_type, decision_canonical_type,
            source_accepted, notes, decided_by,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Visual-reference helpers
# ---------------------------------------------------------------------------


def open_local_preview(png_bytes: bytes) -> None:
    """Write PNG bytes to a temp file and launch `open` on macOS.
    No-op on other platforms or when bytes are empty. Failures are
    swallowed — the review workflow continues even when the preview
    path has issues.
    """
    if not png_bytes or sys.platform != "darwin":
        return
    try:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False,
        )
        tmp.write(png_bytes)
        tmp.close()
        subprocess.Popen(
            ["open", tmp.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Interactive TUI loop
# ---------------------------------------------------------------------------


_PROMPT = (
    "Pick:  [1] LLM  [2] PS  [3] CS  "
    "[o] override  [u] unsure  [s] skip  [q] quit > "
)


def _render_row(
    row: dict[str, Any], file_key: str, output_fn: Callable,
) -> None:
    """Render one flagged row to stdout — the header, three source
    verdicts, and the visual references.
    """
    output_fn("")
    output_fn("=" * 72)
    output_fn(
        f"sci_id={row['sci_id']}  screen={row['screen_id']} "
        f"({row['screen_name']})  node_id={row['node_id']}  "
        f"figma_id={row['figma_node_id']}"
    )
    output_fn(
        f"name: {row['node_name']!r}  node_type={row['node_type']}  "
        f"consensus={row['consensus_method']}  "
        f"current_type={row['canonical_type']}"
    )
    output_fn("")
    output_fn(
        f"  [1] LLM  ({row['llm_confidence'] or 0:.2f}) "
        f"{row['llm_type']!r}"
    )
    if row.get("llm_reason"):
        output_fn(f"        reason: {row['llm_reason']}")
    output_fn(
        f"  [2] PS   ({row['vision_ps_confidence'] or 0:.2f}) "
        f"{row['vision_ps_type']!r}"
    )
    if row.get("vision_ps_reason"):
        output_fn(f"        reason: {row['vision_ps_reason']}")
    output_fn(
        f"  [3] CS   ({row['vision_cs_confidence'] or 0:.2f}) "
        f"{row['vision_cs_type']!r}"
    )
    if row.get("vision_cs_reason"):
        output_fn(f"        reason: {row['vision_cs_reason']}")
    output_fn("")
    output_fn(
        f"  Figma:  {format_figma_deep_link(file_key, row['figma_node_id'])}"
    )


def run_review_tui(
    conn: sqlite3.Connection,
    *,
    file_key: str,
    screen_id: int | None = None,
    limit: int | None = None,
    fetch_screenshot: Callable | None = None,
    input_fn: Callable = input,
    output_fn: Callable = print,
) -> dict[str, int]:
    """Interactive loop over flagged rows on a screen.

    Returns a summary dict of decisions recorded per decision_type.
    Quitting stops the loop but doesn't roll back prior decisions.
    """
    rows = fetch_flagged_rows(
        conn, screen_id=screen_id, limit=limit,
    )

    summary: dict[str, int] = {}

    if not rows:
        output_fn("No flagged rows to review.")
        return summary

    for row in rows:
        _render_row(row, file_key, output_fn)

        if fetch_screenshot is not None:
            try:
                png = fetch_screenshot(file_key, row["figma_node_id"])
                if isinstance(png, (bytes, bytearray)):
                    open_local_preview(bytes(png))
            except Exception:
                # Visual-reference failures never block the loop.
                pass

        decision: str | None = None
        while decision is None:
            raw = input_fn(_PROMPT).strip().lower()
            if raw in ("1", "2", "3", "o", "u", "s", "q"):
                decision = raw
            else:
                output_fn(
                    f"  (unknown choice {raw!r}; "
                    "expected 1/2/3/o/u/s/q)"
                )

        if decision == "q":
            break

        if decision in ("1", "2", "3"):
            source_map = {
                "1": ("llm", row["llm_type"]),
                "2": ("vision_ps", row["vision_ps_type"]),
                "3": ("vision_cs", row["vision_cs_type"]),
            }
            source, ctype = source_map[decision]
            notes = input_fn("Notes (enter for none): ").strip() or None
            record_review_decision(
                conn, sci_id=row["sci_id"],
                decision_type="accept_source",
                source_accepted=source,
                decision_canonical_type=ctype,
                notes=notes,
            )
            summary["accept_source"] = summary.get("accept_source", 0) + 1
            continue

        if decision == "o":
            ctype = input_fn("Override canonical_type: ").strip()
            if not ctype:
                output_fn("  (empty override — recording as skip)")
                record_review_decision(
                    conn, sci_id=row["sci_id"], decision_type="skip",
                )
                summary["skip"] = summary.get("skip", 0) + 1
                continue
            notes = input_fn("Notes (enter for none): ").strip() or None
            record_review_decision(
                conn, sci_id=row["sci_id"],
                decision_type="override",
                decision_canonical_type=ctype,
                notes=notes,
            )
            summary["override"] = summary.get("override", 0) + 1
            continue

        if decision == "u":
            notes = input_fn("Notes (enter for none): ").strip() or None
            record_review_decision(
                conn, sci_id=row["sci_id"], decision_type="unsure",
                notes=notes,
            )
            summary["unsure"] = summary.get("unsure", 0) + 1
            continue

        if decision == "s":
            record_review_decision(
                conn, sci_id=row["sci_id"], decision_type="skip",
            )
            summary["skip"] = summary.get("skip", 0) + 1
            continue

    return summary


# ---------------------------------------------------------------------------
# HTML companion (static review index)
# ---------------------------------------------------------------------------


_HTML_CSS = """
body { font: 14px/1.5 -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
       background: #f8f9fa; margin: 0; padding: 24px; color: #1f2937; }
h1 { font-size: 20px; margin-bottom: 4px; }
.summary { color: #6b7280; margin-bottom: 24px; }
.review-card { background: white; border: 1px solid #e5e7eb;
               border-radius: 8px; margin-bottom: 16px; padding: 16px;
               display: grid; grid-template-columns: 280px 1fr;
               gap: 16px; align-items: start; }
.review-card img { max-width: 280px; max-height: 280px; border-radius: 4px;
                   background: #f3f4f6; }
.review-card .no-preview { width: 280px; height: 160px; background: #f3f4f6;
                           border-radius: 4px; display: flex;
                           align-items: center; justify-content: center;
                           color: #9ca3af; font-size: 12px; }
.meta { font-size: 12px; color: #6b7280; margin-bottom: 12px; }
.meta code { background: #f3f4f6; padding: 1px 4px; border-radius: 3px; }
.sources { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
           margin: 12px 0; }
.source { border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px;
          background: #fafafa; }
.source .label { font-weight: 600; color: #4b5563; font-size: 11px;
                 text-transform: uppercase; letter-spacing: 0.05em; }
.source .type { font-size: 16px; font-weight: 600; margin: 4px 0; }
.source .confidence { color: #6b7280; font-size: 11px; }
.source .reason { margin-top: 6px; color: #374151; font-size: 12px; }
.actions { margin-top: 8px; font-size: 12px; }
.actions a { color: #2563eb; text-decoration: none; }
.actions a:hover { text-decoration: underline; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
         background: #fef3c7; color: #92400e; font-size: 11px; }
"""


def _source_card(
    label: str,
    ctype: str | None,
    confidence: float | None,
    reason: str | None,
) -> str:
    ctype = ctype if ctype is not None else "—"
    conf = f"{confidence:.2f}" if confidence is not None else "—"
    reason_html = (
        f'<div class="reason">{html.escape(reason)}</div>'
        if reason else ""
    )
    return (
        f'<div class="source">'
        f'<div class="label">{label}</div>'
        f'<div class="type">{html.escape(ctype)}</div>'
        f'<div class="confidence">confidence: {conf}</div>'
        f'{reason_html}'
        f'</div>'
    )


def _preview_block(
    fetch_screenshot: Callable | None,
    file_key: str,
    figma_node_id: str,
) -> str:
    if fetch_screenshot is None:
        return '<div class="no-preview">(preview disabled)</div>'
    try:
        data = fetch_screenshot(file_key, figma_node_id)
    except Exception:
        return '<div class="no-preview">(fetch failed)</div>'
    if not isinstance(data, (bytes, bytearray)):
        return '<div class="no-preview">(no screenshot)</div>'
    b64 = base64.b64encode(bytes(data)).decode("ascii")
    return f'<img src="data:image/png;base64,{b64}" alt="screenshot" />'


def _row_card(
    row: dict[str, Any],
    file_key: str,
    fetch_screenshot: Callable | None,
) -> str:
    preview = _preview_block(
        fetch_screenshot, file_key, row["figma_node_id"]
    )
    sources = (
        _source_card(
            "LLM", row["llm_type"],
            row["llm_confidence"], row["llm_reason"],
        )
        + _source_card(
            "Vision PS", row["vision_ps_type"],
            row["vision_ps_confidence"], row["vision_ps_reason"],
        )
        + _source_card(
            "Vision CS", row["vision_cs_type"],
            row["vision_cs_confidence"], row["vision_cs_reason"],
        )
    )
    deep_link = format_figma_deep_link(file_key, row["figma_node_id"])
    return (
        f'<div class="review-card">'
        f'<div>{preview}</div>'
        f'<div>'
        f'<div class="meta">'
        f'<span class="badge">{html.escape(row["consensus_method"] or "unknown")}</span> '
        f'sci_id=<code>{row["sci_id"]}</code> '
        f'screen=<code>{row["screen_id"]}</code> '
        f'({html.escape(row["screen_name"] or "")}) '
        f'node=<code>{html.escape(row["figma_node_id"])}</code> '
        f'name=<code>{html.escape(row["node_name"] or "")}</code>'
        f'</div>'
        f'<div class="sources">{sources}</div>'
        f'<div class="actions">'
        f'<a href="{html.escape(deep_link)}">Open in Figma Desktop</a>'
        f'</div>'
        f'</div>'
        f'</div>'
    )


def render_review_index_html(
    conn: sqlite3.Connection,
    *,
    file_key: str,
    screen_id: int | None = None,
    limit: int | None = None,
    fetch_screenshot: Callable | None = None,
) -> str:
    """Render an HTML page listing every flagged row as a card with
    screenshot + three-source verdicts + Figma deep-link.

    Self-contained: inline CSS, base64 data URI screenshots, no JS
    dependencies. Caller typically writes the output to
    `render_batch/m7_review_index.html` and opens it in a browser
    while driving the CLI TUI.
    """
    rows = fetch_flagged_rows(
        conn, screen_id=screen_id, limit=limit,
    )
    cards = "\n".join(
        _row_card(r, file_key, fetch_screenshot) for r in rows
    )
    header = (
        f"<h1>M7.0.a classification review index</h1>"
        f'<div class="summary">'
        f'{len(rows)} flagged row(s). '
        f'Drive decisions via <code>dd classify-review</code>; '
        f'this page is the scrollable visual companion.'
        f'</div>'
    )
    return (
        f"<!doctype html>\n"
        f"<html lang=\"en\">\n"
        f"<head>\n"
        f"<meta charset=\"utf-8\" />\n"
        f"<title>M7.0.a review — {html.escape(file_key)}</title>\n"
        f"<style>{_HTML_CSS}</style>\n"
        f"</head>\n"
        f"<body>\n"
        f"{header}\n"
        f"{cards}\n"
        f"</body>\n"
        f"</html>\n"
    )
