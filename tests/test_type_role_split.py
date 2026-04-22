"""Tests for the type/role split (docs/plan-type-role-split.md).

Stage 0: DB migration + backfill.
Stage 1: IR layer split in ``map_node_to_element``.
Stage 2+: eid re-canonicalization, reader migration, grammar extension,
verifier rule. Tests accumulate as each stage lands.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dd.db import run_migration


REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_021 = REPO_ROOT / "migrations" / "021_add_nodes_role.sql"


class TestStage0Migration:
    def test_migration_021_adds_role_column_to_nodes(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            """
            CREATE TABLE nodes (
                id INTEGER PRIMARY KEY,
                screen_id INTEGER,
                name TEXT,
                node_type TEXT
            );
            """
        )
        conn.commit()

        result = run_migration(conn, str(MIGRATION_021))

        assert result["errors"] == []
        cols = {row[1] for row in conn.execute("PRAGMA table_info(nodes)")}
        assert "role" in cols, (
            f"Migration 021 must add `role` column to nodes; got {cols}"
        )
