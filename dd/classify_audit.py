"""Spot-check audit for M7.0.a three-source classification (Step 8).

Three-source consensus flags disagreements (any_unsure,
three_way_disagreement) for human review via `dd classify-review`.
Unflagged rows — the ones all three sources agreed on — are not
necessarily correct. If LLM + vision PS + vision CS all make the
same mistake (shared training biases, shared prompt weaknesses,
systematic visual misreading), the row gets committed without a
flag.

This module samples N unflagged + unreviewed rows for spot-check
audit. The user confirms, overrides, or skips; every decision lands
in `classification_reviews` with `decision_type='audit'` so the
consensus view knows it's been verified.

Reproducible sampling: a seed makes the audit sample deterministic —
lets a user rerun the audit on the same rows after fixing a
classification upstream, rather than getting a fresh random set
every time.
"""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Callable
from typing import Any

from dd.classify_review import (
    format_figma_deep_link,
    open_local_preview,
    record_review_decision,
)


def fetch_audit_sample(
    conn: sqlite3.Connection,
    *,
    n: int,
    seed: int | None = None,
    screen_id: int | None = None,
) -> list[dict[str, Any]]:
    """Random sample of `n` unflagged + unreviewed rows.

    "Unflagged" = `flagged_for_review = 0`. "Unreviewed" = no row in
    `classification_reviews`. Sampling is deterministic when `seed`
    is set — makes reruns reproducible.

    Returns an empty list if the candidate pool is empty (e.g., after
    an audit pass through all eligible rows).
    """
    params: list[Any] = []
    clauses = [
        "sci.flagged_for_review = 0",
        "NOT EXISTS (SELECT 1 FROM classification_reviews r "
        "            WHERE r.sci_id = sci.id)",
    ]
    if screen_id is not None:
        clauses.append("sci.screen_id = ?")
        params.append(screen_id)

    where = " AND ".join(clauses)
    cursor = conn.execute(
        f"""
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
        ORDER BY sci.id
        """,
        params,
    )
    cols = [d[0] for d in cursor.description]
    pool = [dict(zip(cols, row)) for row in cursor.fetchall()]
    if not pool:
        return []
    rng = random.Random(seed)
    if n >= len(pool):
        sampled = pool
    else:
        sampled = rng.sample(pool, n)
    # Keep a stable order for the TUI walk (ascending sci_id) rather
    # than the shuffle order — easier to refer back to.
    return sorted(sampled, key=lambda r: r["sci_id"])


_PROMPT = (
    "Audit:  [a] accept current  [o] override  [u] unsure  "
    "[s] skip  [q] quit > "
)


def _render_row(
    row: dict[str, Any], file_key: str, output_fn: Callable,
) -> None:
    output_fn("")
    output_fn("=" * 72)
    output_fn(
        f"sci_id={row['sci_id']}  screen={row['screen_id']} "
        f"({row['screen_name']})  node={row['figma_node_id']}  "
        f"name={row['node_name']!r}"
    )
    output_fn(
        f"current canonical_type: {row['canonical_type']!r}  "
        f"(consensus={row['consensus_method']}, "
        f"source={row['classification_source']})"
    )
    output_fn("")
    for label, t, conf, reason in [
        ("LLM", row["llm_type"], row["llm_confidence"], row["llm_reason"]),
        ("PS",  row["vision_ps_type"], row["vision_ps_confidence"],
         row["vision_ps_reason"]),
        ("CS",  row["vision_cs_type"], row["vision_cs_confidence"],
         row["vision_cs_reason"]),
    ]:
        conf_str = f"{conf:.2f}" if conf is not None else "—"
        output_fn(f"  [{label:3}] ({conf_str}) {t!r}")
        if reason:
            output_fn(f"         reason: {reason}")
    output_fn("")
    output_fn(
        f"  Figma:  {format_figma_deep_link(file_key, row['figma_node_id'])}"
    )


def run_audit_tui(
    conn: sqlite3.Connection,
    *,
    n: int,
    file_key: str,
    seed: int | None = None,
    screen_id: int | None = None,
    fetch_screenshot: Callable | None = None,
    input_fn: Callable = input,
    output_fn: Callable = print,
) -> dict[str, int]:
    """Interactive audit loop.

    Every decision writes `classification_reviews` with
    `decision_type='audit'`. `decision_canonical_type` captures the
    human's confirmed type (either the current value on `a` or the
    user's override on `o`); left NULL on `u` / `s`.

    Returns a summary count per action taken.
    """
    rows = fetch_audit_sample(
        conn, n=n, seed=seed, screen_id=screen_id,
    )
    summary: dict[str, int] = {}

    if not rows:
        output_fn("No unflagged, unreviewed rows left to audit.")
        return summary

    for row in rows:
        _render_row(row, file_key, output_fn)

        if fetch_screenshot is not None:
            try:
                png = fetch_screenshot(file_key, row["figma_node_id"])
                if isinstance(png, (bytes, bytearray)):
                    open_local_preview(bytes(png))
            except Exception:
                pass

        decision: str | None = None
        while decision is None:
            raw = input_fn(_PROMPT).strip().lower()
            if raw in ("a", "o", "u", "s", "q"):
                decision = raw
            else:
                output_fn(
                    f"  (unknown choice {raw!r}; expected a/o/u/s/q)"
                )

        if decision == "q":
            break

        if decision == "a":
            notes = input_fn("Notes (enter for none): ").strip() or None
            record_review_decision(
                conn, sci_id=row["sci_id"],
                decision_type="audit",
                decision_canonical_type=row["canonical_type"],
                notes=notes,
            )
            summary["accept"] = summary.get("accept", 0) + 1
            continue

        if decision == "o":
            ctype = input_fn("Override canonical_type: ").strip()
            if not ctype:
                output_fn("  (empty override — recording as skip)")
                record_review_decision(
                    conn, sci_id=row["sci_id"], decision_type="audit",
                )
                summary["skip"] = summary.get("skip", 0) + 1
                continue
            notes = input_fn("Notes (enter for none): ").strip() or None
            record_review_decision(
                conn, sci_id=row["sci_id"],
                decision_type="audit",
                decision_canonical_type=ctype,
                notes=notes,
            )
            summary["override"] = summary.get("override", 0) + 1
            continue

        if decision == "u":
            notes = input_fn("Notes (enter for none): ").strip() or None
            record_review_decision(
                conn, sci_id=row["sci_id"],
                decision_type="audit",
                notes=notes,
            )
            summary["unsure"] = summary.get("unsure", 0) + 1
            continue

        if decision == "s":
            record_review_decision(
                conn, sci_id=row["sci_id"], decision_type="audit",
            )
            summary["skip"] = summary.get("skip", 0) + 1
            continue

    return summary
