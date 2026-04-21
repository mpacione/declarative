"""M7.0.c — variant family derivation CLI.

Walks the Component Key Registry, parses slash-delimited naming
patterns (``button/large/translucent``) into axis tuples, asks
Claude Haiku to label each family's axes, and writes one
``component_variants`` row per master with ``properties`` JSON
capturing the axis → value map.

Usage::

    .venv/bin/python3 -m scripts.m7_derive_variants \\
        --db Dank-EXP-02.declarative.db

    # Offline / no-API-cost: uses generic 'variant_N' axis names.
    .venv/bin/python3 -m scripts.m7_derive_variants --offline

Cost: ~$0.01 per family with >=1 uniform-depth group. Dank has
~10 families; typical run ≤ $0.10.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument(
        "--file-id", type=int, default=None,
        help="file_id filter; defaults to the single row in files.",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help=(
            "Skip the Anthropic call; axes default to 'variant_N' "
            "fallback names. Useful for CI / dry runs."
        ),
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    from dd.db import get_connection
    from dd.m7_variants import (
        derive_variants_from_ckr, make_anthropic_axis_invoker,
    )

    conn = get_connection(args.db)
    file_id = args.file_id
    if file_id is None:
        row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
        if row is None:
            print("No rows in `files` table.", file=sys.stderr)
            return 1
        file_id = row[0]

    invoker = None
    if not args.offline:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "ANTHROPIC_API_KEY not set (check .env); "
                "re-run with --offline to use fallback axis names.",
                file=sys.stderr,
            )
            return 1
        import anthropic
        client = anthropic.Anthropic()
        invoker = make_anthropic_axis_invoker(client)

    stats = derive_variants_from_ckr(
        conn, file_id=file_id, llm_invoker=invoker,
    )
    print("M7.0.c: variant derivation complete.")
    print(f"  families:                     {stats['families']}")
    print(f"  variants inserted:            {stats['variants_inserted']}")
    print(f"  skipped (existing):           {stats['skipped_existing']}")
    print(f"  skipped (no components row):  {stats['skipped_no_components_row']}")
    print(f"  singletons:                   {stats['singletons']}")
    print()
    print("Per-family axis labels:")
    for family, s in sorted(stats["per_family"].items()):
        axis_keys = [k for k in s if k.startswith("axis_names_d")]
        for k in sorted(axis_keys):
            depth = k.removeprefix("axis_names_d")
            print(f"  {family:20s} depth={depth}  "
                  f"axes={s[k]}  rows={s['rows_written']}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
