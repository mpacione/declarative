"""M7.0.e pattern-extraction runner.

Scans ``screen_component_instances`` for structural subtree shapes
that repeat across ≥N distinct screens (rule-of-three by default),
asks Claude Haiku to label each with a canonical name / category /
description, and persists to the ``patterns`` table.

Usage::

    .venv/bin/python3 -m scripts.extract_patterns \\
        --db Dank-EXP-02.declarative.db \\
        [--min-screens 3] [--max-patterns 20] [--dry-run]
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
        "--min-screens", type=int, default=3,
        help="Rule-of-N threshold (default 3).",
    )
    parser.add_argument(
        "--max-patterns", type=int, default=None,
        help="Cap total labeled patterns per run.",
    )
    parser.add_argument(
        "--parent-types", default=None,
        help=(
            "Comma-separated parent canonical_types to scope "
            "extraction to. Default: all structural types."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--model", default="claude-haiku-4-5-20251001",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    from dd.db import get_connection
    from dd.patterns import run_pattern_extraction

    conn = get_connection(args.db)
    try:
        parent_types = None
        if args.parent_types:
            parent_types = [
                t.strip() for t in args.parent_types.split(",")
                if t.strip()
            ]

        client = None
        if not args.dry_run:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
                return 1
            import anthropic
            client = anthropic.Anthropic()

        summary = run_pattern_extraction(
            conn,
            client=client,
            min_screens=args.min_screens,
            max_patterns=args.max_patterns,
            dry_run=args.dry_run,
            parent_types=parent_types,
            model=args.model,
        )
        print(
            f"candidates={summary.candidates} "
            f"persisted={summary.persisted} "
            f"skipped_duplicate={summary.skipped_duplicate} "
            f"llm_missing={summary.llm_missing}"
        )
        if summary.persisted:
            rows = conn.execute(
                "SELECT name, category, description FROM patterns "
                "ORDER BY id DESC LIMIT 20"
            ).fetchall()
            print("\nRecently persisted patterns:")
            for r in rows:
                desc = r["description"][:80] + (
                    "…" if len(r["description"]) > 80 else ""
                )
                print(
                    f"  [{r['category']:8}] {r['name']:50} — {desc}"
                )
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
