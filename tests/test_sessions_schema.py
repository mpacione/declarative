"""Stage 3.1 — migration 023 schema + ULID helper.

Per Codex+Sonnet 2026-04-23 unanimous pick: Option 3 (Hybrid) + B
(keep move_log). Three tables:

- ``design_sessions`` — one row per `dd design --brief "..."` call.
  ULID PK so Stage 4 can share variant URLs externally.
- ``variants`` — branchable tree of design states. parent_id is
  nullable + self-references variants(id), so LATERAL/branch falls
  out of resume-from-non-leaf semantics for free.
- ``move_log`` — chronological NAME / DRILL / CLIMB / EDIT entries.
  Keeps NAME (description payload) + CLIMB (focus_goal payload)
  which variants can't represent. MoveLogEntry.to_dict() shape
  (Stage 2, fd5c5c5) round-trips into rows here directly.

This file pins the schema. Stage 3.2 wires the persistence layer.
"""

from __future__ import annotations

import sqlite3

import pytest

from dd.db import init_db


@pytest.fixture
def db() -> sqlite3.Connection:
    """Fresh in-memory DB with full schema applied."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


# --------------------------------------------------------------------------- #
# design_sessions                                                             #
# --------------------------------------------------------------------------- #

class TestDesignSessionsTable:
    def test_table_exists(self, db: sqlite3.Connection):
        row = db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='design_sessions'"
        ).fetchone()
        assert row is not None

    def test_required_columns(self, db: sqlite3.Connection):
        cols = {r["name"]: r for r in db.execute(
            "PRAGMA table_info(design_sessions)"
        ).fetchall()}
        # ULID PK as TEXT.
        assert cols["id"]["type"] == "TEXT"
        assert cols["id"]["pk"] == 1
        # The brief is the user's natural-language input.
        assert cols["brief"]["notnull"] == 1
        # Status enum drives ls / show filtering.
        assert "status" in cols
        # Created at for ordering.
        assert "created_at" in cols

    def test_status_check_constraint(self, db: sqlite3.Connection):
        db.execute(
            "INSERT INTO design_sessions (id, brief, status) "
            "VALUES ('s1', 'a screen', 'open')"
        )
        # Closed and archived also accepted (per plan §3.1).
        db.execute(
            "INSERT INTO design_sessions (id, brief, status) "
            "VALUES ('s2', 'another', 'closed')"
        )
        db.execute(
            "INSERT INTO design_sessions (id, brief, status) "
            "VALUES ('s3', 'archived one', 'archived')"
        )
        # Unknown status rejected by CHECK.
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO design_sessions (id, brief, status) "
                "VALUES ('s4', 'bogus', 'invented_state')"
            )

    def test_brief_is_required(self, db: sqlite3.Connection):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO design_sessions (id, status) "
                "VALUES ('sx', 'open')"
            )


# --------------------------------------------------------------------------- #
# variants                                                                    #
# --------------------------------------------------------------------------- #

class TestVariantsTable:
    def test_table_exists(self, db: sqlite3.Connection):
        row = db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='variants'"
        ).fetchone()
        assert row is not None

    def test_required_columns(self, db: sqlite3.Connection):
        cols = {r["name"]: r for r in db.execute(
            "PRAGMA table_info(variants)"
        ).fetchall()}
        # ULID PK.
        assert cols["id"]["type"] == "TEXT"
        assert cols["id"]["pk"] == 1
        # FK to design_sessions.
        assert "session_id" in cols
        # parent_id nullable + self-FK for LATERAL/branch.
        assert "parent_id" in cols
        assert cols["parent_id"]["notnull"] == 0
        # The primitive that birthed this variant.
        assert "primitive" in cols
        # Snapshot fields per Option 3: gzipped TEXT, no sibling
        # session_blobs table.
        assert "markup_blob" in cols
        # Edit script that birthed this variant from parent.
        assert "edit_script" in cols
        # Deferred score (A2) — nullable JSON.
        assert "scores" in cols
        # Frontier / pruned / promoted status from plan §3.1.
        assert "status" in cols
        # Agent rationale.
        assert "notes" in cols
        # Timestamps.
        assert "created_at" in cols

    def test_session_id_fk_enforced(self, db: sqlite3.Connection):
        db.execute("PRAGMA foreign_keys = ON")
        # Insert without parent session FAILS.
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO variants (id, session_id, primitive) "
                "VALUES ('v1', 'no-such-session', 'NAME')"
            )

    def test_parent_id_self_fk(self, db: sqlite3.Connection):
        db.execute("PRAGMA foreign_keys = ON")
        db.execute(
            "INSERT INTO design_sessions (id, brief, status) "
            "VALUES ('s1', 'x', 'open')"
        )
        # Root variant: parent_id NULL.
        db.execute(
            "INSERT INTO variants (id, session_id, primitive) "
            "VALUES ('v1', 's1', 'NAME')"
        )
        # Child variant references parent.
        db.execute(
            "INSERT INTO variants "
            "(id, session_id, parent_id, primitive) "
            "VALUES ('v2', 's1', 'v1', 'EDIT')"
        )
        # Bogus parent_id rejected.
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO variants "
                "(id, session_id, parent_id, primitive) "
                "VALUES ('v3', 's1', 'no-such-parent', 'EDIT')"
            )

    def test_status_check_constraint(self, db: sqlite3.Connection):
        db.execute(
            "INSERT INTO design_sessions (id, brief, status) "
            "VALUES ('s1', 'x', 'open')"
        )
        for s in ("open", "pruned", "promoted", "frontier"):
            db.execute(
                "INSERT INTO variants (id, session_id, primitive, status) "
                f"VALUES ('v_{s}', 's1', 'EDIT', '{s}')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO variants (id, session_id, primitive, status) "
                "VALUES ('v_bogus', 's1', 'EDIT', 'invented_state')"
            )


# --------------------------------------------------------------------------- #
# move_log                                                                    #
# --------------------------------------------------------------------------- #

class TestMoveLogTable:
    def test_table_exists(self, db: sqlite3.Connection):
        row = db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='move_log'"
        ).fetchone()
        assert row is not None

    def test_required_columns(self, db: sqlite3.Connection):
        cols = {r["name"]: r for r in db.execute(
            "PRAGMA table_info(move_log)"
        ).fetchall()}
        # Plan §3.1 uses INTEGER PRIMARY KEY AUTOINCREMENT for log id.
        assert cols["id"]["pk"] == 1
        assert "session_id" in cols
        assert "variant_id" in cols
        assert "primitive" in cols
        # Payload carries NAME's description / DRILL's focus_goal —
        # the fields variants alone can't represent (Codex+Sonnet's
        # B argument 2026-04-23).
        assert "payload" in cols
        assert "created_at" in cols

    def test_round_trips_movelogentry_dict(self, db: sqlite3.Connection):
        """The Stage-2 MoveLogEntry shape (fd5c5c5) round-trips into
        a move_log row. Stage 3 honors that promise."""
        import json

        from dd.focus import MoveLogEntry
        db.execute("PRAGMA foreign_keys = ON")
        db.execute(
            "INSERT INTO design_sessions (id, brief, status) "
            "VALUES ('s1', 'x', 'open')"
        )
        db.execute(
            "INSERT INTO variants (id, session_id, primitive) "
            "VALUES ('v1', 's1', 'DRILL')"
        )
        entry = MoveLogEntry(
            primitive="DRILL",
            scope_eid="features-section",
            payload={"focus_goal": "tighten layout"},
            rationale="user wants denser",
        )
        d = entry.to_dict()
        db.execute(
            "INSERT INTO move_log "
            "(session_id, variant_id, primitive, payload) "
            "VALUES (?, ?, ?, ?)",
            ("s1", "v1", d["primitive"], json.dumps(d)),
        )
        row = db.execute(
            "SELECT primitive, payload FROM move_log"
        ).fetchone()
        # Primitive matches; payload deserializes back to dict-shape.
        assert row["primitive"] == "DRILL"
        loaded = json.loads(row["payload"])
        assert loaded["scope_eid"] == "features-section"
        assert loaded["payload"] == {"focus_goal": "tighten layout"}
        assert loaded["rationale"] == "user wants denser"


# --------------------------------------------------------------------------- #
# ULID helper                                                                 #
# --------------------------------------------------------------------------- #

class TestUlidHelper:
    """Per Codex+Sonnet 2026-04-23 + audit: roll-your-own ULID,
    no python-ulid dep added. ~10-LOC Crockford-encoded
    time_ns + secrets.token_bytes(10)."""

    def test_returns_26_char_string(self):
        from dd.ulid import ulid
        u = ulid()
        assert isinstance(u, str)
        assert len(u) == 26

    def test_uses_crockford_alphabet(self):
        from dd.ulid import ulid
        # Crockford base32: 0-9 + A-Z minus I/L/O/U.
        crockford = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        u = ulid()
        assert set(u).issubset(crockford), (
            f"ULID {u!r} contains non-Crockford chars: "
            f"{set(u) - crockford}"
        )

    def test_lexicographically_sortable_by_time(self):
        """ULIDs generated later sort after earlier ones lexically.
        This is the property that makes them useful as PKs over
        random UUIDs — sortable in SQL ORDER BY without a created_at
        column."""
        import time

        from dd.ulid import ulid
        u1 = ulid()
        time.sleep(0.002)
        u2 = ulid()
        assert u1 < u2

    def test_collision_resistant(self):
        from dd.ulid import ulid
        # 1000 ULIDs in a tight loop should all be unique.
        out = {ulid() for _ in range(1000)}
        assert len(out) == 1000


# --------------------------------------------------------------------------- #
# schema.sql parity                                                           #
# --------------------------------------------------------------------------- #

class TestSchemaSqlMirrorsMigration:
    """Per Stage 0.1 pattern: schema.sql is the rebuild-from-zero
    source; migrations/023 is the patch for existing DBs. The two
    must declare equivalent shapes (modulo DEFAULT timestamp form)."""

    def test_schema_sql_has_all_three_tables(self):
        import re
        from pathlib import Path
        sql = Path(
            "/Users/mattpacione/declarative-build/schema.sql"
        ).read_text()
        for table in ("design_sessions", "variants", "move_log"):
            assert re.search(
                rf"CREATE TABLE IF NOT EXISTS {table}\b", sql
            ), f"schema.sql missing CREATE TABLE for {table}"
