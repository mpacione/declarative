"""Tests for M7.0.b Step 1 — backfill components from CKR.

The backfill is pure SQL so we can exercise every branch against a
minimal in-memory DB: seed the catalog, a file, some nodes, some
instances, some CKR entries, then assert the resulting `components`
rows carry the right category + figma_node_id + name.
"""

from __future__ import annotations

import sqlite3

import pytest

from scripts.m7_backfill_components import (
    backfill_components,
    pick_canonical_category,
)


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE files (id INTEGER PRIMARY KEY, file_key TEXT);

        CREATE TABLE component_type_catalog (
            id INTEGER PRIMARY KEY,
            canonical_name TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL
        );

        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            component_key TEXT
        );

        CREATE TABLE screen_component_instances (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            node_id INTEGER,
            canonical_type TEXT,
            classification_source TEXT
        );

        CREATE TABLE component_key_registry (
            component_key TEXT PRIMARY KEY,
            figma_node_id TEXT,
            name TEXT,
            instance_count INTEGER
        );

        CREATE TABLE components (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            figma_node_id TEXT NOT NULL,
            name TEXT,
            description TEXT,
            category TEXT,
            variant_properties TEXT,
            composition_hint TEXT,
            UNIQUE(file_id, figma_node_id)
        );
    """)
    conn.executemany(
        "INSERT INTO component_type_catalog (canonical_name, category) "
        "VALUES (?, ?)",
        [
            ("button", "actions"),
            ("icon", "content_and_display"),
            ("drawer", "navigation"),
        ],
    )
    conn.execute("INSERT INTO files (id, file_key) VALUES (1, 'dank')")
    return conn


def _add_component(
    conn: sqlite3.Connection, *, key: str, figma_id: str, name: str,
    instance_count: int,
) -> None:
    conn.execute(
        "INSERT INTO component_key_registry "
        "(component_key, figma_node_id, name, instance_count) "
        "VALUES (?, ?, ?, ?)",
        (key, figma_id, name, instance_count),
    )


def _add_instance(
    conn: sqlite3.Connection, *, node_id: int, key: str,
    canonical_type: str,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO nodes (id, screen_id, component_key) "
        "VALUES (?, 1, ?)",
        (node_id, key),
    )
    conn.execute(
        "INSERT INTO screen_component_instances "
        "(screen_id, node_id, canonical_type, classification_source) "
        "VALUES (1, ?, ?, 'llm')",
        (node_id, canonical_type),
    )


class TestPickCanonicalCategory:
    def test_returns_catalog_category_for_single_type(self):
        conn = _fresh_db()
        _add_component(conn, key="K1", figma_id="1:1",
                       name="button/primary", instance_count=5)
        for i, nid in enumerate([10, 11, 12, 13, 14]):
            _add_instance(conn, node_id=nid, key="K1",
                          canonical_type="button")
        assert pick_canonical_category(conn, "K1") == "actions"

    def test_none_when_no_instances(self):
        conn = _fresh_db()
        _add_component(conn, key="orphan", figma_id="9:9",
                       name="unused", instance_count=0)
        assert pick_canonical_category(conn, "orphan") is None

    def test_majority_wins_on_mixed_types(self):
        """10 button instances + 2 icon instances → button's category."""
        conn = _fresh_db()
        _add_component(conn, key="K2", figma_id="2:2",
                       name="mixed", instance_count=12)
        for nid in range(20, 30):
            _add_instance(conn, node_id=nid, key="K2",
                          canonical_type="button")
        for nid in range(30, 32):
            _add_instance(conn, node_id=nid, key="K2",
                          canonical_type="icon")
        assert pick_canonical_category(conn, "K2") == "actions"

    def test_none_when_type_not_in_catalog(self):
        """The winning type isn't in component_type_catalog → None."""
        conn = _fresh_db()
        _add_component(conn, key="K3", figma_id="3:3",
                       name="exotic", instance_count=3)
        _add_instance(conn, node_id=40, key="K3",
                      canonical_type="unregistered_type")
        assert pick_canonical_category(conn, "K3") is None


class TestBackfillComponents:
    def test_populates_one_row_per_ckr_entry(self):
        conn = _fresh_db()
        _add_component(conn, key="A", figma_id="1:1", name="button/A",
                       instance_count=1)
        _add_component(conn, key="B", figma_id="2:2", name="icon/B",
                       instance_count=1)
        _add_instance(conn, node_id=100, key="A", canonical_type="button")
        _add_instance(conn, node_id=200, key="B", canonical_type="icon")

        stats = backfill_components(conn, file_id=1)
        assert stats["inserted"] == 2
        rows = conn.execute(
            "SELECT figma_node_id, name, category "
            "FROM components ORDER BY figma_node_id"
        ).fetchall()
        assert rows == [
            ("1:1", "button/A", "actions"),
            ("2:2", "icon/B", "content_and_display"),
        ]

    def test_orphan_ckr_gets_null_category(self):
        """A CKR entry with zero classified instances is still
        inserted, category=None.
        """
        conn = _fresh_db()
        _add_component(conn, key="orphan", figma_id="9:9",
                       name="stranded", instance_count=0)
        stats = backfill_components(conn, file_id=1)
        assert stats["inserted"] == 1
        assert stats["orphan_no_instances"] == 1
        row = conn.execute(
            "SELECT figma_node_id, name, category FROM components"
        ).fetchone()
        assert row == ("9:9", "stranded", None)

    def test_idempotent_second_run(self):
        conn = _fresh_db()
        _add_component(conn, key="A", figma_id="1:1", name="button/A",
                       instance_count=1)
        _add_instance(conn, node_id=100, key="A", canonical_type="button")

        first = backfill_components(conn, file_id=1)
        second = backfill_components(conn, file_id=1)
        assert first["inserted"] == 1
        assert second["inserted"] == 0
        assert second["skipped_existing"] == 1
        # Still only one row.
        n = conn.execute("SELECT COUNT(*) FROM components").fetchone()[0]
        assert n == 1

    def test_counts_type_not_in_catalog_separately(self):
        conn = _fresh_db()
        _add_component(conn, key="K", figma_id="3:3", name="x",
                       instance_count=1)
        _add_instance(conn, node_id=300, key="K",
                      canonical_type="unregistered_type")
        stats = backfill_components(conn, file_id=1)
        assert stats["inserted"] == 1
        assert stats["orphan_type_not_in_catalog"] == 1
        row = conn.execute("SELECT category FROM components").fetchone()
        assert row == (None,)

    def test_skips_ckr_with_null_figma_id(self):
        """Remote-library components without a resolved figma_node_id
        can't be inserted (NOT NULL constraint) and slots can't be
        derived without the master. Count + skip.
        """
        conn = _fresh_db()
        conn.execute(
            "INSERT INTO component_key_registry "
            "(component_key, figma_node_id, name, instance_count) "
            "VALUES ('remote', NULL, 'remote-only', 0)"
        )
        stats = backfill_components(conn, file_id=1)
        assert stats["inserted"] == 0
        assert stats["skipped_no_figma_id"] == 1
        n = conn.execute("SELECT COUNT(*) FROM components").fetchone()[0]
        assert n == 0

    def test_category_derived_from_majority_vote(self):
        """Multi-instance CKR with mixed classifications → majority
        type's category wins.
        """
        conn = _fresh_db()
        _add_component(conn, key="MIX", figma_id="5:5", name="ambiguous",
                       instance_count=5)
        # 4 drawer classifications, 1 button classification.
        for nid in range(500, 504):
            _add_instance(conn, node_id=nid, key="MIX",
                          canonical_type="drawer")
        _add_instance(conn, node_id=504, key="MIX",
                      canonical_type="button")
        stats = backfill_components(conn, file_id=1)
        assert stats["inserted"] == 1
        row = conn.execute("SELECT category FROM components").fetchone()
        assert row == ("navigation",)
