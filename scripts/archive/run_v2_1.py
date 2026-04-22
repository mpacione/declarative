"""Full-corpus classifier v2.1 run with reviews preserved.

Problem: classification_reviews has ON DELETE CASCADE on sci_id.
Truncating sci + re-classifying destroys the 359 human-reviewed
decisions. This script threads them through:

  1. Snapshot classification_reviews → in-memory backup with
     screen_id + node_id (not sci_id) so we can re-link to new rows.
  2. Truncate sci + skeletons.
  3. Run v2.1 with --classifier-v2 + workers=4.
  4. Re-insert reviews, binding each to the NEW sci.id matched by
     (screen_id, node_id).

Also generates a post-run comparison report: how often does v2.1's
consensus match the user's `accept_source` decisions? That's the
real accuracy signal the pair-agreement bake-off couldn't measure.

Usage:

    .venv/bin/python3 -m scripts.run_v2_1 \
        --db Dank-EXP-02.declarative.db \
        [--workers 4] [--since 150 --limit 10]
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path


def _snapshot_reviews(
    conn: sqlite3.Connection,
) -> list[dict]:
    """Read every classification_reviews row joined with its sci's
    (screen_id, node_id) so we can rebind after re-classification.
    """
    rows = conn.execute(
        """
        SELECT
            r.decided_at, r.decided_by, r.decision_type,
            r.decision_canonical_type, r.source_accepted, r.notes,
            sci.screen_id, sci.node_id
        FROM classification_reviews r
        JOIN screen_component_instances sci ON sci.id = r.sci_id
        """
    ).fetchall()
    cols = [
        "decided_at", "decided_by", "decision_type",
        "decision_canonical_type", "source_accepted", "notes",
        "screen_id", "node_id",
    ]
    return [dict(zip(cols, r)) for r in rows]


def _restore_reviews(
    conn: sqlite3.Connection,
    snapshot: list[dict],
) -> tuple[int, int]:
    """Re-insert reviews, resolving sci_id by (screen_id, node_id).
    Returns (restored, orphaned) — orphans are reviews whose node
    no longer has an sci row (rare; usually nodes filtered out by
    v2's improved candidate selection).
    """
    restored = 0
    orphaned = 0
    for r in snapshot:
        row = conn.execute(
            "SELECT id FROM screen_component_instances "
            "WHERE screen_id = ? AND node_id = ?",
            (r["screen_id"], r["node_id"]),
        ).fetchone()
        if row is None:
            orphaned += 1
            continue
        conn.execute(
            "INSERT INTO classification_reviews "
            "(sci_id, decided_at, decided_by, decision_type, "
            " decision_canonical_type, source_accepted, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                row[0], r["decided_at"], r["decided_by"],
                r["decision_type"], r["decision_canonical_type"],
                r["source_accepted"], r["notes"],
            ),
        )
        restored += 1
    conn.commit()
    return (restored, orphaned)


def _accuracy_vs_reviews(
    conn: sqlite3.Connection,
) -> tuple[int, int, dict[str, tuple[int, int]]]:
    """For each `accept_source` review row, check whether v2.1's
    canonical_type matches the source the user picked.

    Returns (matches, total, per_source_match_map).
    """
    rows = conn.execute(
        """
        SELECT
            r.source_accepted, sci.canonical_type,
            sci.llm_type, sci.vision_ps_type, sci.vision_cs_type
        FROM classification_reviews r
        JOIN screen_component_instances sci ON sci.id = r.sci_id
        WHERE r.decision_type = 'accept_source'
        """
    ).fetchall()
    matches = 0
    total = 0
    per_source: dict[str, tuple[int, int]] = {
        "llm": (0, 0),
        "vision_ps": (0, 0),
        "vision_cs": (0, 0),
    }
    for src, canonical, llm, ps, cs in rows:
        total += 1
        picked = {"llm": llm, "vision_ps": ps, "vision_cs": cs}.get(src)
        is_match = canonical == picked
        if is_match:
            matches += 1
        m, t = per_source.get(src, (0, 0))
        per_source[src] = (m + (1 if is_match else 0), t + 1)
    return matches, total, per_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default="Dank-EXP-02.declarative.db",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--since", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--out",
        default="render_batch/m7_v2_1_accuracy_report.md",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    # Step 0: whole-DB backup before ANY mutation. Snapshot lives in
    # Python memory, so if the process dies mid-run the 674 reviews
    # die with it. `cp` before truncate is cheap insurance.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = Path(args.db).with_suffix(f".pre-v2.1-{ts}.bak.db")
    shutil.copy2(args.db, backup)
    for suffix in ("-wal", "-shm"):
        src = Path(args.db + suffix)
        if src.exists():
            shutil.copy2(src, str(backup) + suffix)
    print(f"[0/5] backed up DB → {backup}", flush=True)

    from dd.db import get_connection
    conn = get_connection(args.db)

    # Step 1: snapshot reviews.
    snapshot = _snapshot_reviews(conn)
    print(
        f"[1/5] snapshotted {len(snapshot)} reviews",
        flush=True,
    )

    # Step 2: truncate sci + skeletons (reviews CASCADE-drop).
    before_sci = conn.execute(
        "SELECT COUNT(*) FROM screen_component_instances"
    ).fetchone()[0]
    conn.execute("DELETE FROM screen_component_instances")
    conn.execute("DELETE FROM screen_skeletons")
    conn.commit()
    print(
        f"[2/5] truncated {before_sci} sci rows "
        f"(reviews also dropped via CASCADE — will restore from snapshot)",
        flush=True,
    )

    # Step 3: classify via v2.1.
    import anthropic
    from dd.cli import make_figma_screenshot_fetcher
    from dd.classify_v2 import run_classification_v2
    client = anthropic.Anthropic()
    fetch_screenshot = make_figma_screenshot_fetcher(scale=2)

    file_row = conn.execute(
        "SELECT id FROM files LIMIT 1"
    ).fetchone()
    if file_row is None:
        print("No file in DB.", file=sys.stderr)
        return 1
    file_id = file_row[0]
    file_key = conn.execute(
        "SELECT file_key FROM files WHERE id = ?",
        (file_id,),
    ).fetchone()[0]

    start = time.time()
    summary = run_classification_v2(
        conn, file_id, client, file_key, fetch_screenshot,
        since_screen_id=args.since, limit=args.limit,
        workers=args.workers,
    )
    elapsed = time.time() - start
    print(
        f"[3/5] v2.1 run complete in {elapsed / 60.0:.1f} min",
        flush=True,
    )
    for k in (
        "dedup_candidates", "dedup_groups",
        "llm_inserts", "vision_ps_applied",
        "vision_cs_applied", "skeletons_generated",
    ):
        print(f"    {k}: {summary.get(k)}")

    # Step 4: restore reviews.
    restored, orphaned = _restore_reviews(conn, snapshot)
    print(
        f"[4/5] restored {restored} reviews "
        f"({orphaned} orphaned — nodes filtered out by v2)",
        flush=True,
    )

    # Step 5: accuracy report.
    matches, total, per_source = _accuracy_vs_reviews(conn)
    overall_pct = (matches / total * 100.0) if total else 0.0
    print(f"[5/5] accuracy vs user reviews:", flush=True)
    print(
        f"    overall: {matches}/{total} = {overall_pct:.1f}%",
        flush=True,
    )
    for src, (m, t) in per_source.items():
        pct = (m / t * 100.0) if t else 0.0
        print(f"    {src}: {m}/{t} = {pct:.1f}%", flush=True)

    # Emit markdown report.
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Classifier v2.1 full-corpus accuracy report",
        "",
        f"- Wall time: {elapsed / 60.0:.1f} min",
        f"- Workers: {args.workers}",
        "",
        "## Dedup",
        "",
        f"- Candidates: {summary.get('dedup_candidates')}",
        f"- Groups: {summary.get('dedup_groups')}",
        f"- LLM inserts: {summary.get('llm_inserts')}",
        f"- Vision PS applied: {summary.get('vision_ps_applied')}",
        f"- Vision CS applied: {summary.get('vision_cs_applied')}",
        "",
        "## Consensus breakdown",
        "",
    ]
    consensus = summary.get("consensus") or {}
    for method in sorted(consensus.keys()):
        lines.append(f"- `{method}`: {consensus[method]}")
    lines.append("")

    lines.append("## Accuracy vs user reviews")
    lines.append("")
    lines.append(
        f"- **Overall**: {matches}/{total} = **{overall_pct:.1f}%**"
    )
    lines.append("")
    lines.append("Per-source match (where user accepted that source):")
    lines.append("")
    lines.append("| Source user picked | Matched | Total | Rate |")
    lines.append("|---|---:|---:|---:|")
    for src, (m, t) in per_source.items():
        pct = (m / t * 100.0) if t else 0.0
        lines.append(f"| {src} | {m} | {t} | {pct:.1f}% |")
    lines.append("")

    lines.append("## Review preservation")
    lines.append("")
    lines.append(f"- Snapshot size: {len(snapshot)}")
    lines.append(f"- Restored: {restored}")
    lines.append(f"- Orphaned: {orphaned}")
    lines.append("")

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote report: {args.out}", flush=True)

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
