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


def _minimal_schema_for_role(conn: sqlite3.Connection) -> None:
    """Minimum schema the Stage 0 tests need: nodes + SCI tables."""
    conn.executescript(
        """
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            name TEXT,
            node_type TEXT
        );
        CREATE TABLE screen_component_instances (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            node_id INTEGER,
            canonical_type TEXT,
            classification_source TEXT,
            consensus_method TEXT
        );
        """
    )
    conn.commit()


class TestStage0Migration:
    def test_migration_021_adds_role_column_to_nodes(self) -> None:
        conn = sqlite3.connect(":memory:")
        _minimal_schema_for_role(conn)

        result = run_migration(conn, str(MIGRATION_021))

        assert result["errors"] == []
        cols = {row[1] for row in conn.execute("PRAGMA table_info(nodes)")}
        assert "role" in cols, (
            f"Migration 021 must add `role` column to nodes; got {cols}"
        )


class TestStage0Backfill:
    def test_backfill_populates_role_from_sci(self) -> None:
        conn = sqlite3.connect(":memory:")
        _minimal_schema_for_role(conn)
        conn.executescript(
            """
            INSERT INTO nodes (id, screen_id, node_type) VALUES
                (1, 10, 'FRAME'),
                (2, 10, 'TEXT'),
                (3, 10, 'RECTANGLE');
            INSERT INTO screen_component_instances
                (id, screen_id, node_id, canonical_type)
            VALUES
                (100, 10, 1, 'card'),
                (101, 10, 2, 'heading');
            """
        )
        conn.commit()
        run_migration(conn, str(MIGRATION_021))

        from dd.db import backfill_nodes_role
        result = backfill_nodes_role(conn)

        roles = dict(conn.execute("SELECT id, role FROM nodes").fetchall())
        assert roles[1] == "card"
        assert roles[2] == "heading"
        assert roles[3] is None, (
            "Unclassified nodes (no SCI row) must stay role=NULL"
        )
        assert result["populated"] == 2

    def test_backfill_is_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        _minimal_schema_for_role(conn)
        conn.executescript(
            """
            INSERT INTO nodes (id, screen_id, node_type) VALUES (1, 10, 'FRAME');
            INSERT INTO screen_component_instances
                (id, screen_id, node_id, canonical_type)
            VALUES (100, 10, 1, 'card');
            """
        )
        conn.commit()
        run_migration(conn, str(MIGRATION_021))

        from dd.db import backfill_nodes_role
        backfill_nodes_role(conn)
        result_2 = backfill_nodes_role(conn)

        role = conn.execute("SELECT role FROM nodes WHERE id=1").fetchone()[0]
        assert role == "card"
        assert result_2["populated"] == 1
