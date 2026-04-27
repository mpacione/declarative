"""Tests for `dd classify-audit` spot-check (M7.0.a Step 8).

The audit loop samples `N` unflagged + unreviewed rows (three-source
consensus thought these were confident — our goal is to catch
systematic drift where all three sources were wrong together) and
asks a human to confirm or override. Every decision writes a
`classification_reviews` row with `decision_type='audit'`.
"""

from __future__ import annotations

import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.classify_audit import fetch_audit_sample, run_audit_tui
from dd.db import init_db


def _seed_unflagged_row(
    db: sqlite3.Connection,
    *,
    sci_id: int = 1,
    screen_id: int = 1,
    node_id: int = 10,
    figma_node_id: str | None = None,
    canonical_type: str = "button",
    consensus_method: str = "unanimous",
    classification_source: str = "llm",
    llm_type: str = "button",
) -> None:
    if figma_node_id is None:
        figma_node_id = f"{node_id}:1"
    db.execute(
        "INSERT OR IGNORE INTO files (id, file_key, name) "
        "VALUES (1, 'fk', 'F')"
    )
    db.execute(
        "INSERT OR IGNORE INTO screens "
        "(id, file_id, figma_node_id, name, width, height) "
        "VALUES (?, 1, ?, 'S', 428, 926)",
        (screen_id, f"s{screen_id}:0"),
    )
    db.execute(
        "INSERT OR IGNORE INTO nodes "
        "(id, screen_id, figma_node_id, name, node_type, depth, sort_order) "
        "VALUES (?, ?, ?, ?, 'FRAME', 1, 0)",
        (node_id, screen_id, figma_node_id, f"node-{node_id}"),
    )
    db.execute(
        "INSERT INTO screen_component_instances "
        "(id, screen_id, node_id, canonical_type, confidence, "
        " classification_source, consensus_method, flagged_for_review, "
        " llm_type) "
        "VALUES (?, ?, ?, ?, 0.9, ?, ?, 0, ?)",
        (
            sci_id, screen_id, node_id, canonical_type,
            classification_source, consensus_method, llm_type,
        ),
    )
    db.commit()


class TestFetchAuditSample:
    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        for i in range(10):
            _seed_unflagged_row(
                conn, sci_id=i + 1, node_id=10 + i,
            )
        yield conn
        conn.close()

    def test_samples_n_rows(self, db: sqlite3.Connection):
        sample = fetch_audit_sample(db, n=3, seed=42)
        assert len(sample) == 3

    def test_only_unflagged_rows(self, db: sqlite3.Connection):
        db.execute(
            "UPDATE screen_component_instances SET flagged_for_review = 1 "
            "WHERE id = 1"
        )
        db.commit()
        sample = fetch_audit_sample(db, n=10, seed=42)
        assert 1 not in [r["sci_id"] for r in sample]

    def test_excludes_already_reviewed(self, db: sqlite3.Connection):
        db.execute(
            "INSERT INTO classification_reviews "
            "(sci_id, decision_type) VALUES (1, 'audit')"
        )
        db.commit()
        sample = fetch_audit_sample(db, n=10, seed=42)
        assert 1 not in [r["sci_id"] for r in sample]

    def test_seeded_sample_is_deterministic(
        self, db: sqlite3.Connection,
    ) -> None:
        """Seed makes sampling reproducible — lets the user rerun an
        audit without getting a fresh random set.
        """
        s1 = fetch_audit_sample(db, n=5, seed=123)
        s2 = fetch_audit_sample(db, n=5, seed=123)
        assert [r["sci_id"] for r in s1] == [r["sci_id"] for r in s2]

    def test_samples_fewer_when_pool_smaller_than_n(
        self, db: sqlite3.Connection,
    ) -> None:
        for i in range(1, 11):
            db.execute(
                "UPDATE screen_component_instances "
                "SET flagged_for_review = 1 WHERE id = ?",
                (i,),
            )
        db.commit()
        sample = fetch_audit_sample(db, n=5, seed=42)
        assert sample == []


class TestRunAuditTUI:
    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        _seed_unflagged_row(conn, sci_id=1, node_id=10)
        _seed_unflagged_row(conn, sci_id=2, node_id=11)
        yield conn
        conn.close()

    def _drive(self, db, inputs, n=2):
        input_queue = list(inputs)
        outputs: list[str] = []

        def input_fn(prompt=""):
            outputs.append(prompt)
            return input_queue.pop(0)

        def output_fn(*args, **kwargs):
            outputs.append(" ".join(str(a) for a in args))

        return run_audit_tui(
            db, n=n, file_key="fk",
            seed=42,
            input_fn=input_fn, output_fn=output_fn,
        )

    def test_accept_records_audit_with_current_type(
        self, db: sqlite3.Connection,
    ) -> None:
        # 2 rows; accept both.
        self._drive(db, ["a", "", "a", ""])
        rows = db.execute(
            "SELECT decision_type, decision_canonical_type "
            "FROM classification_reviews ORDER BY sci_id"
        ).fetchall()
        assert len(rows) == 2
        for row in rows:
            assert row[0] == "audit"
            assert row[1] == "button"  # seeded current type

    def test_override_records_audit_with_new_type(
        self, db: sqlite3.Connection,
    ) -> None:
        self._drive(db, ["o", "card", "", "q"])
        row = db.execute(
            "SELECT decision_type, decision_canonical_type "
            "FROM classification_reviews LIMIT 1"
        ).fetchone()
        assert row[0] == "audit"
        assert row[1] == "card"

    def test_skip_records_audit_without_type(
        self, db: sqlite3.Connection,
    ) -> None:
        self._drive(db, ["s", "q"])
        row = db.execute(
            "SELECT decision_type, decision_canonical_type "
            "FROM classification_reviews LIMIT 1"
        ).fetchone()
        assert row[0] == "audit"
        assert row[1] is None

    def test_quit_before_decision(self, db: sqlite3.Connection):
        self._drive(db, ["q"])
        row = db.execute(
            "SELECT COUNT(*) FROM classification_reviews"
        ).fetchone()
        assert row[0] == 0

    def test_invalid_choice_reprompts(self, db: sqlite3.Connection):
        self._drive(db, ["x", "s", "q"])
        row = db.execute(
            "SELECT COUNT(*) FROM classification_reviews"
        ).fetchone()
        assert row[0] == 1
