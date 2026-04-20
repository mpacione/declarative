"""Resume a crashed three-source classify run (M7.0.a Step 9 recovery).

The full-corpus three-source run can crash mid-CS due to transient
network errors (Anthropic API connection drops, SSL alerts). LLM and
vision PS phases write per-row, so they're robust to resumes; vision
CS is batched and consensus runs after all batches, so a crash mid-CS
leaves partial CS columns + zero consensus.

This script:
1. Identifies LLM-classified rows whose vision_cs_type is NULL.
2. Groups their screens into CS batches (same logic as the
   orchestrator, via group_screens_by_skeleton_and_device).
3. Runs classify_batch with target_source="llm_missing_cs" so the
   API call only carries unfinished rows (no re-paying for completed
   batches).
4. Runs apply_consensus_to_screen for every screen with LLM rows.

Usage:
    .venv/bin/python3 -m scripts.m7_resume_three_source \
        --db Dank-EXP-02.declarative.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time

from dd.classify import (
    apply_consensus_to_screen,
    apply_vision_cs_results,
)
from dd.classify_vision_batched import (
    classify_batch,
    group_screens_by_skeleton_and_device,
)
from dd.db import get_connection


def _missing_cs_screens(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        """
        SELECT DISTINCT screen_id
        FROM screen_component_instances
        WHERE classification_source = 'llm'
          AND vision_cs_type IS NULL
        ORDER BY screen_id
        """
    ).fetchall()
    return [r[0] for r in rows]


def _all_llm_screens(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        """
        SELECT DISTINCT screen_id
        FROM screen_component_instances
        WHERE classification_source = 'llm'
        ORDER BY screen_id
        """
    ).fetchall()
    return [r[0] for r in rows]


def _file_key(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT file_key FROM files LIMIT 1").fetchone()
    return row[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to .declarative.db")
    parser.add_argument(
        "--max-retries", type=int, default=3,
        help="Per-batch retry count on transient API errors (default 3)",
    )
    parser.add_argument(
        "--retry-delay", type=float, default=10.0,
        help="Seconds between retries (default 10s)",
    )
    args = parser.parse_args(argv)

    # Use get_connection so row_factory is sqlite3.Row — required by
    # dd.catalog.get_catalog and other helpers downstream.
    conn = get_connection(args.db)

    file_key = _file_key(conn)

    missing = _missing_cs_screens(conn)
    print(f"Screens with LLM rows lacking CS: {len(missing)}", flush=True)
    if not missing:
        print("Nothing to resume.", flush=True)
    else:
        # Anthropic + Figma API setup, mirroring _run_classify in cli.py.
        import anthropic
        from dd.cli import make_figma_screenshot_fetcher
        client = anthropic.Anthropic()
        fetch_screenshot = make_figma_screenshot_fetcher()

        # Group missing-CS screens into CS batches by their natural
        # (device_class, skeleton_type) groups.
        batches = group_screens_by_skeleton_and_device(
            conn, missing, target_batch_size=5,
        )
        print(f"Will run {len(batches)} CS batches", flush=True)

        applied = 0
        for i, batch in enumerate(batches, 1):
            attempt = 0
            while attempt < args.max_retries:
                try:
                    cs_results = classify_batch(
                        conn, batch, client, file_key, fetch_screenshot,
                        target_source="llm_missing_cs",
                    )
                    summary = apply_vision_cs_results(conn, cs_results)
                    applied += summary["applied"]
                    print(
                        f"[{i}/{len(batches)}] batch={batch} "
                        f"applied={summary['applied']}",
                        flush=True,
                    )
                    break
                except Exception as e:
                    attempt += 1
                    print(
                        f"[{i}/{len(batches)}] error on attempt {attempt}: "
                        f"{type(e).__name__}: {e}",
                        flush=True,
                    )
                    if attempt >= args.max_retries:
                        print(
                            f"[{i}/{len(batches)}] giving up after "
                            f"{args.max_retries} attempts; continuing",
                            flush=True,
                        )
                    else:
                        time.sleep(args.retry_delay)

        print(f"\nCS resume complete: {applied} rows updated", flush=True)

    # Run consensus across every screen with LLM rows. Cheap (pure DB
    # operation) — no API cost.
    print("\nRunning consensus...", flush=True)
    consensus_total: dict[str, int] = {}
    llm_screens = _all_llm_screens(conn)
    for sid in llm_screens:
        counts = apply_consensus_to_screen(conn, sid)
        for k, v in counts.items():
            consensus_total[k] = consensus_total.get(k, 0) + v
    print("\nConsensus breakdown:", flush=True)
    for method in sorted(consensus_total.keys()):
        print(f"  {method:<28} {consensus_total[method]}", flush=True)

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
