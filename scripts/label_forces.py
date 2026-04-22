"""M7.0.d forces-labeling runner.

Populates ``screen_component_instances.compositional_role`` for a
subset of load-bearing instances using Claude Haiku tool-use. See
``dd/forces.py`` for the module-level contract.

Cost envelope: ~$0.001-$0.002 per SCI at Haiku pricing, batched
10-20 rows per API call. A 500-row pilot is ~$1.

Usage::

    .venv/bin/python3 -m scripts.label_forces \\
        --db Dank-EXP-02.declarative.db \\
        [--limit 50] [--batch-size 10] [--dry-run]
        [--screen-id 183]
        [--canonical-types button,card]
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
        "--limit", type=int, default=50,
        help="Max SCI rows to label in this run.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=10,
        help="Instances per tool-use API call.",
    )
    parser.add_argument(
        "--canonical-types", default=None,
        help=(
            "Comma-separated canonical_types to scope the labeling "
            "to. Defaults to the built-in targeted set (buttons / "
            "cards / nav / etc. — see dd.forces._TARGETED_TYPES)."
        ),
    )
    parser.add_argument("--screen-id", type=int, default=None)
    parser.add_argument(
        "--dry-run", action="store_true",
        help=(
            "Collect candidates + build contexts but skip the "
            "Anthropic call and the DB write."
        ),
    )
    parser.add_argument(
        "--model", default="claude-haiku-4-5-20251001",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    from dd.db import get_connection
    from dd.forces import run_forces_labeling

    conn = get_connection(args.db)
    try:
        canonical_types = None
        if args.canonical_types:
            canonical_types = [
                t.strip() for t in args.canonical_types.split(",")
                if t.strip()
            ]

        client = None
        if not args.dry_run:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
                return 1
            import anthropic
            client = anthropic.Anthropic()

        summary = run_forces_labeling(
            conn,
            limit=args.limit,
            dry_run=args.dry_run,
            client=client,
            canonical_types=canonical_types,
            screen_id=args.screen_id,
            batch_size=args.batch_size,
            model=args.model,
        )
        print(
            f"candidates={summary.candidates} "
            f"labeled={summary.labeled} "
            f"batches={summary.batches} "
            f"errors={summary.errors}"
        )
        if summary.labeled:
            rows = conn.execute(
                "SELECT id, canonical_type, compositional_role "
                "FROM screen_component_instances "
                "WHERE compositional_role IS NOT NULL "
                "ORDER BY id DESC LIMIT ?",
                (min(args.limit, 10),),
            ).fetchall()
            print("\nSample labels (most recently touched):")
            for r in rows:
                print(
                    f"  sci={r['id']} type={r['canonical_type']:15}"
                    f" role={r['compositional_role']}"
                )
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
