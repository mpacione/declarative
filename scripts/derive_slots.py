"""M7.0.b Step 2 — slot derivation per canonical_type.

Runs the cluster + LLM-label + write pipeline for one or more
canonical_types. The plan's initial scope (plan §SD-4) is
``button`` only; other types come after that validates.

Usage::

    .venv/bin/python3 -m scripts.derive_slots \\
        --db Dank-EXP-02.declarative.db \\
        --canonical-type button

    # Multi-type after validation:
    .venv/bin/python3 -m scripts.derive_slots --canonical-type \\
        button,icon_button,button_group

Cost: ~$0.01 per canonical_type (one Haiku call per type).
Idempotent — existing component_slots rows are skipped via the
UNIQUE(component_id, name) constraint.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument(
        "--canonical-type", required=True,
        help=(
            "Comma-separated canonical_types to derive slots for. "
            "Spec recommends starting with 'button' only (SD-4)."
        ),
    )
    parser.add_argument(
        "--file-id", type=int, default=None,
        help="file_id filter (defaults to the single row in `files`).",
    )
    parser.add_argument(
        "--sample-limit", type=int, default=500,
        help=(
            "Cap instances fed to the clusterer. 500 surfaces the "
            "dominant pattern without burning time on bulk types."
        ),
    )
    parser.add_argument(
        "--min-cluster-share", type=float, default=0.5,
        help=(
            "Reject types whose top cluster is below this share. "
            "0.5 = top cluster must be a strict majority."
        ),
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set (check .env).", file=sys.stderr)
        return 1

    from dd.db import get_connection
    from dd.master_slots import (
        derive_slots_for_canonical_type, make_anthropic_invoker,
    )
    import anthropic

    conn = get_connection(args.db)

    file_id = args.file_id
    if file_id is None:
        row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
        if row is None:
            print("No rows in `files` table.", file=sys.stderr)
            return 1
        file_id = row[0]

    client = anthropic.Anthropic()
    invoker = make_anthropic_invoker(client)

    types = [t.strip() for t in args.canonical_type.split(",") if t.strip()]
    for ctype in types:
        stats = derive_slots_for_canonical_type(
            conn, ctype,
            file_id=file_id,
            llm_invoker=invoker,
            sample_limit=args.sample_limit,
            min_cluster_share=args.min_cluster_share,
        )
        print(f"\n=== {ctype} ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
