"""Classifier v2 bake-off — 10-screen validation before full-corpus run.

Runs v2 on the original bake-off screen set (150-159) on a COPY of
the Dank DB so the live DB + user's 666 reviews stay intact. Reports:

- v2 API-call count vs candidate count (dedup ratio).
- v2 pair-agreement rates (LLM↔PS, LLM↔CS, PS↔CS).
- v2 match rate against the user's `accept_source` review decisions
  on the same 10 screens.

Gate criteria for committing to a full re-run (from
`docs/plan-classifier-v2.md` §3c):
- v2 LLM↔PS agreement ≥ 85%
- v2 match against user reviews ≥ 70%
- API cost ≤ 60% of v1 per-screen

Usage:

    .venv/bin/python3 -m scripts.bakeoff_v2 \
        --db Dank-EXP-02.declarative.db \
        [--out render_batch/m7_bakeoff_v2_report.md]
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path


DEFAULT_SCREEN_IDS = list(range(150, 160))


def _copy_db(src: str, dest: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        src_path = Path(src + suffix)
        dest_path = Path(dest + suffix)
        if src_path.exists():
            shutil.copy2(src_path, dest_path)
        elif dest_path.exists():
            dest_path.unlink()


def _truncate_sci_and_skeletons(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM screen_component_instances")
    conn.execute("DELETE FROM screen_skeletons")
    conn.commit()


def _fetch_v2_results(
    conn: sqlite3.Connection, screen_ids: list[int],
) -> list[dict]:
    placeholders = ",".join("?" * len(screen_ids))
    rows = conn.execute(
        f"""
        SELECT sci.id AS sci_id, sci.screen_id, sci.node_id,
               sci.llm_type, sci.vision_ps_type, sci.vision_cs_type,
               sci.canonical_type, sci.consensus_method,
               sci.flagged_for_review
        FROM screen_component_instances sci
        WHERE sci.screen_id IN ({placeholders})
          AND sci.classification_source = 'llm'
        """,
        screen_ids,
    ).fetchall()
    cols = ["sci_id", "screen_id", "node_id",
            "llm_type", "vision_ps_type", "vision_cs_type",
            "canonical_type", "consensus_method", "flagged"]
    return [dict(zip(cols, r)) for r in rows]


def _fetch_user_reviews(
    live_conn: sqlite3.Connection, screen_ids: list[int],
) -> dict[tuple[int, int], dict]:
    """Return `{(screen_id, node_id): review_dict}` for reviews on
    the target screens. Live DB only.
    """
    placeholders = ",".join("?" * len(screen_ids))
    rows = live_conn.execute(
        f"""
        SELECT sci.screen_id, sci.node_id,
               r.decision_type, r.source_accepted,
               r.decision_canonical_type
        FROM classification_reviews r
        JOIN screen_component_instances sci ON sci.id = r.sci_id
        WHERE sci.screen_id IN ({placeholders})
        """,
        screen_ids,
    ).fetchall()
    out: dict[tuple[int, int], dict] = {}
    for r in rows:
        out[(r[0], r[1])] = {
            "decision_type": r[2],
            "source_accepted": r[3],
            "decision_canonical_type": r[4],
        }
    return out


def _agreement(pair: list[tuple[str | None, str | None]]) -> float:
    """Fraction of pairs where both sides are non-null AND match."""
    valid = [(a, b) for a, b in pair if a and b]
    if not valid:
        return 0.0
    return sum(1 for a, b in valid if a == b) / len(valid)


def _match_user_reviews(
    v2_rows: list[dict],
    reviews: dict[tuple[int, int], dict],
) -> tuple[int, int]:
    """For each v2 row with a user review of type 'accept_source',
    check whether v2's consensus canonical_type matches the source
    the user picked. Returns (match_count, total_accept_source).
    """
    matches = 0
    total = 0
    for row in v2_rows:
        review = reviews.get((row["screen_id"], row["node_id"]))
        if review is None:
            continue
        if review["decision_type"] != "accept_source":
            continue
        total += 1
        picked = review["source_accepted"]
        v2_picked_type = {
            "llm": row.get("llm_type"),
            "vision_ps": row.get("vision_ps_type"),
            "vision_cs": row.get("vision_cs_type"),
        }.get(picked)
        if row.get("canonical_type") == v2_picked_type:
            matches += 1
    return matches, total


def _render_report(
    screen_ids: list[int],
    v2_rows: list[dict],
    reviews: dict[tuple[int, int], dict],
    summary: dict,
    elapsed_s: float,
) -> str:
    pair_llm_ps = [
        (r["llm_type"], r["vision_ps_type"]) for r in v2_rows
    ]
    pair_llm_cs = [
        (r["llm_type"], r["vision_cs_type"]) for r in v2_rows
    ]
    pair_ps_cs = [
        (r["vision_ps_type"], r["vision_cs_type"]) for r in v2_rows
    ]
    a_llm_ps = _agreement(pair_llm_ps)
    a_llm_cs = _agreement(pair_llm_cs)
    a_ps_cs = _agreement(pair_ps_cs)

    matches, total = _match_user_reviews(v2_rows, reviews)
    match_pct = (matches / total * 100.0) if total else 0.0

    consensus = summary.get("consensus") or {}
    flagged = sum(
        consensus.get(k, 0)
        for k in ("any_unsure", "three_way_disagreement",
                  "two_way_disagreement")
    )

    lines: list[str] = []
    lines.append("# Classifier v2 bake-off report")
    lines.append("")
    lines.append(f"- Screens: {screen_ids}")
    lines.append(f"- Wall time: {elapsed_s:.1f}s")
    lines.append("")
    lines.append("## Dedup")
    lines.append("")
    lines.append(
        f"- Candidates collected: {summary.get('dedup_candidates', 0)}"
    )
    lines.append(
        f"- Dedup groups: {summary.get('dedup_groups', 0)}"
    )
    if summary.get("dedup_candidates", 0) and summary.get("dedup_groups", 0):
        ratio = summary["dedup_candidates"] / summary["dedup_groups"]
        lines.append(f"- Candidates-per-group: {ratio:.2f}x")
    lines.append(f"- LLM inserts: {summary.get('llm_inserts', 0)}")
    lines.append(f"- Vision PS applied: {summary.get('vision_ps_applied', 0)}")
    lines.append(f"- Vision CS applied: {summary.get('vision_cs_applied', 0)}")
    lines.append("")

    lines.append("## Pair agreement")
    lines.append("")
    lines.append("| Pair | Agreement |")
    lines.append("|---|---:|")
    lines.append(f"| LLM ↔ PS | {a_llm_ps*100:.1f}% |")
    lines.append(f"| LLM ↔ CS | {a_llm_cs*100:.1f}% |")
    lines.append(f"| PS ↔ CS | {a_ps_cs*100:.1f}% |")
    lines.append("")

    lines.append("## Consensus breakdown")
    lines.append("")
    for method in sorted(consensus.keys()):
        lines.append(f"- `{method}`: {consensus[method]}")
    lines.append(f"- flagged (unsure/3-way/2-way): {flagged}")
    lines.append("")

    lines.append("## Ground-truth match against user reviews")
    lines.append("")
    if total:
        lines.append(
            f"- User `accept_source` decisions on these screens: {total}"
        )
        lines.append(
            f"- v2 canonical_type matched user's picked source: "
            f"{matches} ({match_pct:.1f}%)"
        )
    else:
        lines.append(
            "- No user `accept_source` decisions on these screens. "
            "No ground-truth validation possible."
        )
    lines.append("")

    lines.append("## Gate check")
    lines.append("")
    gates = [
        ("LLM ↔ PS ≥ 85%", a_llm_ps >= 0.85,
         f"{a_llm_ps*100:.1f}%"),
        ("User-review match ≥ 70%", match_pct >= 70.0 if total else None,
         f"{match_pct:.1f}% of {total}" if total else "n/a"),
    ]
    for name, pass_, value in gates:
        mark = "✅" if pass_ is True else ("❌" if pass_ is False else "—")
        lines.append(f"- {mark} {name}: {value}")
    lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default="Dank-EXP-02.declarative.db",
        help="Path to the live .declarative.db (read-only here).",
    )
    parser.add_argument(
        "--out", default="render_batch/m7_bakeoff_v2_report.md",
    )
    parser.add_argument(
        "--screens", type=str, default=None,
        help=(
            "Comma-separated screen IDs. Default: 150-159 (original "
            "bake-off set)."
        ),
    )
    parser.add_argument(
        "--copy-path", default="/tmp/dank_v2_bakeoff.db",
        help=(
            "Where to materialise the DB copy. Defaults to /tmp so "
            "the live DB is never mutated."
        ),
    )
    args = parser.parse_args(argv)

    screen_ids = (
        [int(s) for s in args.screens.split(",")]
        if args.screens else DEFAULT_SCREEN_IDS
    )

    live_db = args.db
    work_db = args.copy_path
    print(f"Copying {live_db} → {work_db}...", flush=True)
    _copy_db(live_db, work_db)
    print("Copy complete.", flush=True)

    # Truncate classifications on the COPY; v2 will repopulate for
    # the target screens.
    from dd.db import get_connection
    work_conn = get_connection(work_db)
    _truncate_sci_and_skeletons(work_conn)
    work_conn.close()

    # Load file_key from live DB.
    live_conn = get_connection(live_db)
    file_row = live_conn.execute(
        "SELECT id, file_key FROM files LIMIT 1"
    ).fetchone()
    if file_row is None:
        print("Error: no file in live DB.", file=sys.stderr)
        return 1
    file_id, file_key = file_row[0], file_row[1]
    reviews = _fetch_user_reviews(live_conn, screen_ids)
    live_conn.close()
    print(
        f"Loaded {len(reviews)} user reviews for these screens.",
        flush=True,
    )

    # Run v2 on the work copy.
    import anthropic
    from dd.cli import make_figma_screenshot_fetcher
    from dd.classify_v2 import run_classification_v2

    client = anthropic.Anthropic()
    # v2.1: scale=2 Figma fetches so small-node crops have 4x
    # source pixels. See docs/plan-classifier-v2.1.md Phase D.
    fetch_screenshot = make_figma_screenshot_fetcher(scale=2)

    work_conn = get_connection(work_db)
    start = time.time()
    # --since + --limit lets run_classification_v2 target the 10 screens.
    # We pass the full file_id; the function filters by screen range.
    summary = run_classification_v2(
        work_conn, file_id, client, file_key, fetch_screenshot,
        since_screen_id=min(screen_ids),
        limit=len(screen_ids),
    )
    elapsed = time.time() - start
    print(f"v2 run complete in {elapsed:.1f}s.", flush=True)

    v2_rows = _fetch_v2_results(work_conn, screen_ids)
    work_conn.close()

    report = _render_report(
        screen_ids, v2_rows, reviews, summary, elapsed,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nWrote report: {out_path}", flush=True)
    print("\n" + report, flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
