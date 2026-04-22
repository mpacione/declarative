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
    """Minimum schema the Stage 0 tests need: nodes + SCI tables.

    SCI schema mirrors the columns ``dd/classify_v2._insert_llm_verdicts``
    touches, plus the ``UNIQUE(screen_id, node_id)`` constraint needed
    for the ``ON CONFLICT`` upsert path.
    """
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
            catalog_type_id INTEGER,
            canonical_type TEXT,
            confidence REAL,
            classification_source TEXT,
            consensus_method TEXT,
            llm_reason TEXT,
            llm_type TEXT,
            llm_confidence REAL,
            UNIQUE(screen_id, node_id)
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


class TestStage0QueryReturnsRole:
    def test_query_screen_for_ir_returns_role_column(self) -> None:
        from dd.db import init_db
        from dd.ir import query_screen_for_ir

        conn = init_db(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'F');
            INSERT INTO screens (id, file_id, figma_node_id, name, width, height)
                VALUES (1, 1, 'sn1', 'T', 400, 800);
            INSERT INTO nodes
                (id, screen_id, figma_node_id, name, node_type,
                 role, depth, sort_order)
            VALUES
                (10, 1, 'n10', 'Card', 'FRAME', 'card', 0, 0),
                (11, 1, 'n11', 'Heading', 'TEXT', 'heading', 1, 0),
                (12, 1, 'n12', 'Unclass', 'RECTANGLE', NULL, 1, 1);
            """
        )
        conn.commit()

        result = query_screen_for_ir(conn, 1)
        nodes_by_id = {n["node_id"]: n for n in result["nodes"]}

        assert nodes_by_id[10]["role"] == "card"
        assert nodes_by_id[11]["role"] == "heading"
        assert nodes_by_id[12]["role"] is None


class TestStage0ClassifyV2WritesRole:
    def test_insert_llm_verdicts_writes_nodes_role(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema_for_role(conn)
        run_migration(conn, str(MIGRATION_021))
        conn.executescript(
            """
            INSERT INTO nodes (id, screen_id, node_type) VALUES
                (1, 10, 'FRAME'),
                (2, 10, 'TEXT');
            """
        )
        conn.commit()

        from dd.classify_v2 import _insert_llm_verdicts
        groups = [
            [{"screen_id": 10, "node_id": 1}],
            [{"screen_id": 10, "node_id": 2}],
        ]
        reps = [{"node_id": 1}, {"node_id": 2}]
        verdicts = {
            1: ("button", 0.9, "looks like a button"),
            2: ("heading", 0.85, "bold text"),
        }
        catalog = [
            {"canonical_name": "button", "id": 100},
            {"canonical_name": "heading", "id": 101},
        ]

        _insert_llm_verdicts(conn, groups, reps, verdicts, catalog)

        sci = dict(conn.execute(
            "SELECT node_id, canonical_type FROM screen_component_instances"
        ).fetchall())
        assert sci == {1: "button", 2: "heading"}

        roles = dict(conn.execute("SELECT id, role FROM nodes").fetchall())
        assert roles[1] == "button", (
            "classify_v2 must write nodes.role alongside SCI.canonical_type"
        )
        assert roles[2] == "heading"

    def test_insert_llm_verdicts_upsert_updates_role(self) -> None:
        """Re-classifying a node overwrites both SCI.canonical_type
        and nodes.role."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema_for_role(conn)
        run_migration(conn, str(MIGRATION_021))
        conn.executescript(
            """
            INSERT INTO nodes (id, screen_id, node_type)
            VALUES (1, 10, 'FRAME');
            """
        )
        conn.commit()

        from dd.classify_v2 import _insert_llm_verdicts
        groups = [[{"screen_id": 10, "node_id": 1}]]
        reps = [{"node_id": 1}]
        catalog = [
            {"canonical_name": "button", "id": 100},
            {"canonical_name": "card", "id": 101},
        ]

        # First classification
        _insert_llm_verdicts(
            conn, groups, reps, {1: ("button", 0.9, "v1")}, catalog,
        )
        role_v1 = conn.execute(
            "SELECT role FROM nodes WHERE id=1"
        ).fetchone()[0]
        assert role_v1 == "button"

        # Reclassification (different verdict)
        _insert_llm_verdicts(
            conn, groups, reps, {1: ("card", 0.95, "v2")}, catalog,
        )
        role_v2 = conn.execute(
            "SELECT role FROM nodes WHERE id=1"
        ).fetchone()[0]
        assert role_v2 == "card", (
            "UPSERT path must refresh nodes.role on reclassification"
        )
