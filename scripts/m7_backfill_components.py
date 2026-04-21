"""Backfill the ``components`` table from the Component Key Registry.

M7.0.b Step 1 — before slot / variant definitions can hang off components,
the table needs rows for every Figma master component referenced in the
corpus. Populates one ``components`` row per CKR entry, with:

- ``file_id`` — from ``files`` (Dank has exactly one)
- ``figma_node_id`` — the master's node id (from CKR)
- ``name`` — CKR.name
- ``category`` — majority-voted from the master's instance
  classifications, mapped through ``component_type_catalog.category``.
  ``None`` when the CKR entry has no classified instances (orphan).

Idempotent: INSERT OR IGNORE on (file_id, figma_node_id). Running the
script twice is safe; existing rows aren't clobbered.

Usage::

    .venv/bin/python3 -m scripts.m7_backfill_components \\
        --db Dank-EXP-02.declarative.db

Cost: zero (pure SQL).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional


def _category_for_type(
    conn: sqlite3.Connection, canonical_type: str,
) -> Optional[str]:
    """Look up a canonical_type's category in component_type_catalog."""
    row = conn.execute(
        "SELECT category FROM component_type_catalog WHERE canonical_name = ?",
        (canonical_type,),
    ).fetchone()
    return row[0] if row else None


def pick_canonical_category(
    conn: sqlite3.Connection, component_key: str,
) -> Optional[str]:
    """Return the catalog category for the CKR entry, by majority-
    voting canonical_type across every classified instance that links
    to the master via ``nodes.component_key``.

    Returns ``None`` when the CKR entry has no classified instances,
    or when the winning canonical_type isn't in the catalog. Ties broken
    by instance count then alphabetical.
    """
    row = conn.execute(
        """
        SELECT sci.canonical_type, COUNT(*) AS n
        FROM nodes n
        JOIN screen_component_instances sci
          ON sci.node_id = n.id
        WHERE n.component_key = ?
          AND sci.canonical_type IS NOT NULL
        GROUP BY sci.canonical_type
        ORDER BY n DESC, sci.canonical_type ASC
        LIMIT 1
        """,
        (component_key,),
    ).fetchone()
    if row is None:
        return None
    return _category_for_type(conn, row[0])


def backfill_components(
    conn: sqlite3.Connection, *, file_id: int,
) -> dict[str, int]:
    """Populate ``components`` from ``component_key_registry``.

    Returns a stats dict: ``inserted`` + ``skipped_existing`` +
    ``orphan_no_instances`` + ``orphan_type_not_in_catalog``.
    """
    ckr_rows = conn.execute(
        "SELECT component_key, figma_node_id, name "
        "FROM component_key_registry"
    ).fetchall()

    inserted = 0
    skipped_existing = 0
    skipped_no_figma_id = 0
    orphan_no_instances = 0
    orphan_type_not_in_catalog = 0

    for component_key, figma_node_id, name in ckr_rows:
        if not figma_node_id:
            # CKR entry for a remote-library component whose master node
            # isn't present in this file. components.figma_node_id is
            # NOT NULL; can't write a row, and slots can't be derived
            # without the master anyway. Count + skip.
            skipped_no_figma_id += 1
            continue
        # Check whether a components row already exists for this
        # file/master pair. INSERT OR IGNORE handles this too but
        # we want to count skipped vs inserted accurately.
        existing = conn.execute(
            "SELECT 1 FROM components "
            "WHERE file_id = ? AND figma_node_id = ?",
            (file_id, figma_node_id),
        ).fetchone()
        if existing:
            skipped_existing += 1
            continue

        # Pick category via majority classification. First find the
        # winning canonical_type; if it has no instances, orphan.
        winner = conn.execute(
            """
            SELECT sci.canonical_type, COUNT(*) AS n
            FROM nodes n
            JOIN screen_component_instances sci
              ON sci.node_id = n.id
            WHERE n.component_key = ?
              AND sci.canonical_type IS NOT NULL
            GROUP BY sci.canonical_type
            ORDER BY n DESC, sci.canonical_type ASC
            LIMIT 1
            """,
            (component_key,),
        ).fetchone()
        if winner is None:
            orphan_no_instances += 1
            category = None
        else:
            canonical_type = winner[0]
            category = _category_for_type(conn, canonical_type)
            if category is None:
                orphan_type_not_in_catalog += 1

        conn.execute(
            "INSERT INTO components "
            "(file_id, figma_node_id, name, category) "
            "VALUES (?, ?, ?, ?)",
            (file_id, figma_node_id, name, category),
        )
        inserted += 1

    conn.commit()
    return {
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "skipped_no_figma_id": skipped_no_figma_id,
        "orphan_no_instances": orphan_no_instances,
        "orphan_type_not_in_catalog": orphan_type_not_in_catalog,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="Dank-EXP-02.declarative.db")
    parser.add_argument(
        "--file-id", type=int, default=None,
        help=(
            "file_id for the components rows (default: the single "
            "row from the `files` table)."
        ),
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1

    from dd.db import get_connection
    conn = get_connection(args.db)

    file_id = args.file_id
    if file_id is None:
        row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
        if row is None:
            print("No rows in `files` table; pass --file-id.",
                  file=sys.stderr)
            return 1
        file_id = row[0]

    stats = backfill_components(conn, file_id=file_id)
    total_ckr = conn.execute(
        "SELECT COUNT(*) FROM component_key_registry"
    ).fetchone()[0]
    total_components = conn.execute(
        "SELECT COUNT(*) FROM components WHERE file_id = ?",
        (file_id,),
    ).fetchone()[0]
    conn.close()

    print(f"M7.0.b Step 1: components backfill complete.")
    print(f"  CKR rows read:             {total_ckr}")
    print(f"  components rows inserted:  {stats['inserted']}")
    print(f"  components rows skipped:   {stats['skipped_existing']} "
          "(already present)")
    print(f"  skipped (no figma_node_id):{stats['skipped_no_figma_id']} "
          "(remote-library masters)")
    print(f"  orphan (no instances):     {stats['orphan_no_instances']}")
    print(f"  orphan (type not in cat):  {stats['orphan_type_not_in_catalog']}")
    print(f"  components table total:    {total_components}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
