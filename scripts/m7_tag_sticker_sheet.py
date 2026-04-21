"""M7.0.f sticker-sheet tagging runner.

Finds every design_canvas screen, collects the distinct INSTANCE
component_keys on them, and tags the corresponding `components`
rows with `authoritative_source = 'sticker_sheet'`. No LLM required.

Usage::

    .venv/bin/python3 -m scripts.m7_tag_sticker_sheet \\
        --db Dank-EXP-02.declarative.db \\
        [--screen-types design_canvas,sticker_sheet]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument(
        "--screen-types", default=None,
        help=(
            "Comma-separated screen_type values to treat as "
            "sticker sheets. Default: design_canvas."
        ),
    )
    parser.add_argument(
        "--source-label", default="sticker_sheet",
        help="Value to write into authoritative_source.",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    from dd.db import get_connection
    from dd.sticker_sheet import tag_authoritative_components

    conn = get_connection(args.db)
    try:
        types = None
        if args.screen_types:
            types = [
                t.strip() for t in args.screen_types.split(",")
                if t.strip()
            ]
        summary = tag_authoritative_components(
            conn, screen_types=types, source_label=args.source_label,
        )
        print(
            f"sticker_sheet_screens={summary.sticker_sheet_screens} "
            f"candidate_keys={summary.candidate_keys} "
            f"tagged={summary.tagged} "
            f"already_tagged={summary.already_tagged} "
            f"unknown_component_keys={summary.unknown_component_keys}"
        )
        if summary.tagged:
            # `components.component_key` may or may not exist
            # depending on schema era; query what we know.
            has_ck = any(
                row[1] == "component_key" for row in conn.execute(
                    "PRAGMA table_info(components)"
                ).fetchall()
            )
            col_list = (
                "component_key, name, category, canonical_type"
                if has_ck
                else "figma_node_id, name, category, canonical_type"
            )
            rows = conn.execute(
                f"SELECT {col_list} FROM components "
                "WHERE authoritative_source = ? "
                "ORDER BY canonical_type, name LIMIT 20",
                (args.source_label,),
            ).fetchall()
            print("\nSample tagged components (first 20):")
            for r in rows:
                print(
                    f"  [{r['canonical_type'] or '?':15}] "
                    f"{r['name']:40s} ({r['category']})"
                )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
