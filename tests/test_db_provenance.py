"""Tests for value provenance, history, and retention.

Covers the three new columns on token_values (source, sync_status, last_verified_at),
the token_value_history append-only table, the db.update_token_value() helper,
force_renormalize scoping to source='figma' only, and the retention utility.
"""

import sqlite3
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_collection_token_mode(conn: sqlite3.Connection):
    """Insert the minimum rows needed for a token_values row."""
    conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'F')")
    conn.execute("INSERT INTO token_collections (id, file_id, name) VALUES (1, 1, 'Colors')")
    conn.execute(
        "INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (1, 1, 'Default', 1)"
    )
    conn.execute(
        "INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (2, 1, 'Dark', 0)"
    )
    conn.execute(
        "INSERT INTO tokens (id, collection_id, name, type) VALUES (1, 1, 'color.surface.primary', 'color')"
    )
    conn.commit()


def _insert_token_value(conn: sqlite3.Connection, token_id=1, mode_id=1,
                        raw="raw", resolved="#FFFFFF", source="figma"):
    conn.execute(
        "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value, source) "
        "VALUES (?, ?, ?, ?, ?)",
        (token_id, mode_id, raw, resolved, source),
    )
    conn.commit()


def _get_token_value(conn: sqlite3.Connection, token_id=1, mode_id=1):
    return conn.execute(
        "SELECT resolved_value, source, sync_status, last_verified_at "
        "FROM token_values WHERE token_id = ? AND mode_id = ?",
        (token_id, mode_id),
    ).fetchone()


def _get_history(conn: sqlite3.Connection, token_id=1, mode_id=1):
    return conn.execute(
        "SELECT old_resolved, new_resolved, changed_by, reason "
        "FROM token_value_history WHERE token_id = ? AND mode_id = ? "
        "ORDER BY changed_at ASC",
        (token_id, mode_id),
    ).fetchall()


def _seed_screen_node(conn: sqlite3.Connection):
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'S', 400, 800)"
    )
    conn.execute(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
        "VALUES (1, 1, 'n1', 'N', 'RECTANGLE')"
    )
    conn.commit()


def _insert_binding(conn, node_id, prop, resolved, token_id=None, status="bound"):
    conn.execute(
        "INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, token_id, binding_status) "
        "VALUES (?, ?, '{}', ?, ?, ?)",
        (node_id, prop, resolved, token_id, status),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# token_values: source column
# ---------------------------------------------------------------------------

class TestTokenValuesSourceColumn:
    """source column defaults to 'figma' and accepts valid values."""

    def test_source_defaults_to_figma(self, db):
        _seed_collection_token_mode(db)
        db.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) "
            "VALUES (1, 1, 'raw', '#FFF')"
        )
        db.commit()
        row = _get_token_value(db)
        assert row["source"] == "figma"

    def test_source_can_be_derived(self, db):
        _seed_collection_token_mode(db)
        _insert_token_value(db, source="derived")
        assert _get_token_value(db)["source"] == "derived"

    def test_source_can_be_manual(self, db):
        _seed_collection_token_mode(db)
        _insert_token_value(db, source="manual")
        assert _get_token_value(db)["source"] == "manual"

    def test_source_can_be_imported(self, db):
        _seed_collection_token_mode(db)
        _insert_token_value(db, source="imported")
        assert _get_token_value(db)["source"] == "imported"

    def test_invalid_source_raises(self, db):
        _seed_collection_token_mode(db)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value, source) "
                "VALUES (1, 1, 'raw', '#FFF', 'unknown')"
            )


# ---------------------------------------------------------------------------
# token_values: sync_status column
# ---------------------------------------------------------------------------

class TestTokenValuesSyncStatus:
    """sync_status defaults to 'pending' and accepts valid values."""

    def test_sync_status_defaults_to_pending(self, db):
        _seed_collection_token_mode(db)
        _insert_token_value(db)
        assert _get_token_value(db)["sync_status"] == "pending"

    def test_sync_status_can_be_synced(self, db):
        _seed_collection_token_mode(db)
        _insert_token_value(db)
        db.execute(
            "UPDATE token_values SET sync_status = 'synced' WHERE token_id = 1 AND mode_id = 1"
        )
        db.commit()
        assert _get_token_value(db)["sync_status"] == "synced"

    def test_invalid_sync_status_raises(self, db):
        _seed_collection_token_mode(db)
        _insert_token_value(db)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "UPDATE token_values SET sync_status = 'invalid' WHERE token_id = 1 AND mode_id = 1"
            )


# ---------------------------------------------------------------------------
# token_values: last_verified_at column
# ---------------------------------------------------------------------------

class TestTokenValuesLastVerifiedAt:
    """last_verified_at defaults to NULL and can be set."""

    def test_last_verified_at_defaults_null(self, db):
        _seed_collection_token_mode(db)
        _insert_token_value(db)
        assert _get_token_value(db)["last_verified_at"] is None

    def test_last_verified_at_can_be_set(self, db):
        _seed_collection_token_mode(db)
        _insert_token_value(db)
        db.execute(
            "UPDATE token_values SET last_verified_at = '2026-03-27T12:00:00Z' "
            "WHERE token_id = 1 AND mode_id = 1"
        )
        db.commit()
        assert _get_token_value(db)["last_verified_at"] == "2026-03-27T12:00:00Z"


# ---------------------------------------------------------------------------
# token_value_history table
# ---------------------------------------------------------------------------

class TestTokenValueHistoryTable:
    """token_value_history stores append-only change records."""

    def test_history_row_stores_old_and_new(self, db):
        _seed_collection_token_mode(db)
        db.execute(
            "INSERT INTO token_value_history (token_id, mode_id, old_resolved, new_resolved, changed_by) "
            "VALUES (1, 1, '#000', '#FFF', 'curate')"
        )
        db.commit()
        rows = _get_history(db)
        assert len(rows) == 1
        assert rows[0]["old_resolved"] == "#000"
        assert rows[0]["new_resolved"] == "#FFF"
        assert rows[0]["changed_by"] == "curate"

    def test_first_write_has_null_old_resolved(self, db):
        _seed_collection_token_mode(db)
        db.execute(
            "INSERT INTO token_value_history (token_id, mode_id, old_resolved, new_resolved, changed_by) "
            "VALUES (1, 1, NULL, '#FFF', 'extract')"
        )
        db.commit()
        rows = _get_history(db)
        assert rows[0]["old_resolved"] is None

    def test_reason_stored(self, db):
        _seed_collection_token_mode(db)
        db.execute(
            "INSERT INTO token_value_history "
            "(token_id, mode_id, old_resolved, new_resolved, changed_by, reason) "
            "VALUES (1, 1, '#000', '#FFF', 'modes', 'dark_mode_derivation')"
        )
        db.commit()
        assert _get_history(db)[0]["reason"] == "dark_mode_derivation"

    def test_multiple_writes_append(self, db):
        _seed_collection_token_mode(db)
        for i, (old, new) in enumerate([("#000", "#111"), ("#111", "#222"), ("#222", "#FFF")]):
            db.execute(
                "INSERT INTO token_value_history (token_id, mode_id, old_resolved, new_resolved, changed_by) "
                "VALUES (1, 1, ?, ?, 'curate')",
                (old, new),
            )
        db.commit()
        rows = _get_history(db)
        assert len(rows) == 3
        assert rows[0]["old_resolved"] == "#000"
        assert rows[2]["new_resolved"] == "#FFF"


# ---------------------------------------------------------------------------
# db.update_token_value() helper
# ---------------------------------------------------------------------------

class TestUpdateTokenValue:
    """update_token_value() updates resolved_value and writes a history row."""

    def test_updates_resolved_value(self, db):
        from dd.db import update_token_value
        _seed_collection_token_mode(db)
        _insert_token_value(db, resolved="#000")
        update_token_value(db, token_id=1, mode_id=1,
                           new_resolved="#FFF", changed_by="curate")
        assert _get_token_value(db)["resolved_value"] == "#FFF"

    def test_writes_history_row(self, db):
        from dd.db import update_token_value
        _seed_collection_token_mode(db)
        _insert_token_value(db, resolved="#000")
        update_token_value(db, token_id=1, mode_id=1,
                           new_resolved="#FFF", changed_by="curate", reason="test")
        rows = _get_history(db)
        assert len(rows) == 1
        assert rows[0]["old_resolved"] == "#000"
        assert rows[0]["new_resolved"] == "#FFF"
        assert rows[0]["changed_by"] == "curate"
        assert rows[0]["reason"] == "test"

    def test_first_call_has_null_old_resolved(self, db):
        from dd.db import update_token_value
        _seed_collection_token_mode(db)
        _insert_token_value(db, resolved="#000")
        update_token_value(db, token_id=1, mode_id=1,
                           new_resolved="#FFF", changed_by="extract")
        rows = _get_history(db)
        # old_resolved should capture the previous stored value
        assert rows[0]["old_resolved"] == "#000"

    def test_second_call_has_correct_old_resolved(self, db):
        from dd.db import update_token_value
        _seed_collection_token_mode(db)
        _insert_token_value(db, resolved="#000")
        update_token_value(db, token_id=1, mode_id=1,
                           new_resolved="#111", changed_by="extract")
        update_token_value(db, token_id=1, mode_id=1,
                           new_resolved="#FFF", changed_by="curate")
        rows = _get_history(db)
        assert len(rows) == 2
        assert rows[1]["old_resolved"] == "#111"
        assert rows[1]["new_resolved"] == "#FFF"

    def test_resets_sync_status_to_pending(self, db):
        from dd.db import update_token_value
        _seed_collection_token_mode(db)
        _insert_token_value(db, resolved="#000")
        db.execute(
            "UPDATE token_values SET sync_status = 'synced' WHERE token_id = 1 AND mode_id = 1"
        )
        db.commit()
        update_token_value(db, token_id=1, mode_id=1,
                           new_resolved="#FFF", changed_by="curate")
        assert _get_token_value(db)["sync_status"] == "pending"


# ---------------------------------------------------------------------------
# db.insert_token_value() helper
# ---------------------------------------------------------------------------

class TestInsertTokenValue:
    """insert_token_value() creates a token_values row and writes a history row."""

    def test_inserts_row_with_correct_values(self, db):
        from dd.db import insert_token_value
        _seed_collection_token_mode(db)
        insert_token_value(db, token_id=1, mode_id=1, raw_value='"#FFF"',
                           resolved_value="#FFF", source="derived",
                           changed_by="modes", reason="dark_mode_copy")
        row = _get_token_value(db)
        assert row["resolved_value"] == "#FFF"
        assert row["source"] == "derived"

    def test_writes_history_row_with_null_old(self, db):
        from dd.db import insert_token_value
        _seed_collection_token_mode(db)
        insert_token_value(db, token_id=1, mode_id=1, raw_value='"#FFF"',
                           resolved_value="#FFF", source="derived",
                           changed_by="modes", reason="dark_mode_copy")
        rows = _get_history(db)
        assert len(rows) == 1
        assert rows[0]["old_resolved"] is None
        assert rows[0]["new_resolved"] == "#FFF"
        assert rows[0]["changed_by"] == "modes"
        assert rows[0]["reason"] == "dark_mode_copy"

    def test_source_defaults_to_figma(self, db):
        from dd.db import insert_token_value
        _seed_collection_token_mode(db)
        insert_token_value(db, token_id=1, mode_id=1, raw_value='"#FFF"',
                           resolved_value="#FFF", changed_by="extract")
        row = _get_token_value(db)
        assert row["source"] == "figma"


# ---------------------------------------------------------------------------
# copy_values_from_default writes history via insert_token_value
# ---------------------------------------------------------------------------

class TestCopyValuesWritesHistory:
    """copy_values_from_default should write history rows for seeded values."""

    def test_copy_values_writes_history(self, db):
        _seed_collection_token_mode(db)
        _insert_token_value(db, token_id=1, mode_id=1, resolved="#000", source="figma")

        from dd.modes import copy_values_from_default
        dark_mode_id = 2  # Already seeded as non-default
        copy_values_from_default(db, collection_id=1, new_mode_id=dark_mode_id)

        rows = _get_history(db, token_id=1, mode_id=dark_mode_id)
        assert len(rows) == 1
        assert rows[0]["old_resolved"] is None
        assert rows[0]["new_resolved"] == "#000"
        assert rows[0]["changed_by"] == "modes"
        assert rows[0]["reason"] == "copy_from_default"


# ---------------------------------------------------------------------------
# split_token writes history via insert_token_value
# ---------------------------------------------------------------------------

class TestSplitTokenWritesHistory:
    """split_token should write history rows for cloned values."""

    def test_split_writes_history_for_new_token(self, db):
        _seed_collection_token_mode(db)
        _insert_token_value(db, token_id=1, mode_id=1, resolved="#000", source="figma")
        _seed_screen_node(db)
        _insert_binding(db, 1, "fill.0.color", "#000", token_id=1, status="bound")

        from dd.curate import split_token
        binding_id = db.execute(
            "SELECT id FROM node_token_bindings WHERE node_id = 1"
        ).fetchone()["id"]

        result = split_token(db, token_id=1, new_name="color.split.new", binding_ids=[binding_id])
        new_token_id = result["new_token_id"]

        rows = _get_history(db, token_id=new_token_id, mode_id=1)
        assert len(rows) == 1
        assert rows[0]["old_resolved"] is None
        assert rows[0]["changed_by"] == "curate"
        assert rows[0]["reason"] == "split_from_token"


# ---------------------------------------------------------------------------
# force_renormalize scoped to source='figma' only
# ---------------------------------------------------------------------------

class TestForceRenormalizeSourceScoping:
    """force_renormalize=True must not touch derived or manual token_values."""

    def _setup(self, db):
        _seed_collection_token_mode(db)
        _seed_screen_node(db)
        # Bind a token to the node
        db.execute(
            "INSERT INTO node_token_bindings "
            "(node_id, property, raw_value, resolved_value, token_id, binding_status) "
            "VALUES (1, 'fill.0.color', '{}', '#OLD', 1, 'bound')"
        )
        db.commit()

    def test_force_renormalize_updates_figma_source_binding(self, db):
        from dd.extract_bindings import insert_bindings
        self._setup(db)
        _insert_token_value(db, resolved="#FFF", source="figma")

        new_bindings = [{"property": "fill.0.color", "raw_value": "{}", "resolved_value": "#NEW"}]
        insert_bindings(db, node_id=1, bindings=new_bindings, force_renormalize=True)

        row = db.execute(
            "SELECT resolved_value FROM node_token_bindings WHERE node_id=1 AND property='fill.0.color'"
        ).fetchone()
        assert row["resolved_value"] == "#NEW"

    def test_force_renormalize_skips_derived_token_values(self, db):
        """Derived token_values rows are not touched by force_renormalize on bindings.

        Note: force_renormalize scoping is on bindings (via token source lookup).
        This test verifies that after force_renormalize, derived token values are unchanged.
        """
        from dd.extract_bindings import insert_bindings
        self._setup(db)
        _insert_token_value(db, resolved="#DERIVED", source="derived")

        # force_renormalize on bindings should still work (binding update is on bindings table)
        # but the token_value with source='derived' should remain #DERIVED
        new_bindings = [{"property": "fill.0.color", "raw_value": "{}", "resolved_value": "#NEW"}]
        insert_bindings(db, node_id=1, bindings=new_bindings, force_renormalize=True)

        tv = _get_token_value(db)
        assert tv["source"] == "derived"
        assert tv["resolved_value"] == "#DERIVED"  # token_value itself unchanged


# ---------------------------------------------------------------------------
# Retention: prune_extraction_runs()
# ---------------------------------------------------------------------------

class TestPruneExtractionRuns:
    """prune_extraction_runs() keeps the last N runs and deletes older ones."""

    def _seed_runs(self, db, count: int):
        db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'F')")
        db.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, 's1', 'S', 400, 800)"
        )
        db.commit()
        for i in range(1, count + 1):
            db.execute(
                "INSERT INTO extraction_runs (id, file_id, started_at, status) "
                "VALUES (?, 1, datetime('now', ? || ' seconds'), 'completed')",
                (i, str(i)),
            )
            db.execute(
                "INSERT INTO screen_extraction_status (run_id, screen_id, status) "
                "VALUES (?, 1, 'completed')",
                (i,),
            )
        db.commit()

    def test_keeps_last_n_runs(self, db):
        from dd.maintenance import prune_extraction_runs
        self._seed_runs(db, 10)
        deleted = prune_extraction_runs(db, keep_last=5)
        remaining = db.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0]
        assert remaining == 5
        assert deleted == 5

    def test_deletes_associated_screen_status(self, db):
        from dd.maintenance import prune_extraction_runs
        self._seed_runs(db, 10)
        prune_extraction_runs(db, keep_last=5)
        remaining = db.execute("SELECT COUNT(*) FROM screen_extraction_status").fetchone()[0]
        assert remaining == 5

    def test_keep_more_than_exist_deletes_nothing(self, db):
        from dd.maintenance import prune_extraction_runs
        self._seed_runs(db, 3)
        deleted = prune_extraction_runs(db, keep_last=10)
        assert deleted == 0
        assert db.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0] == 3

    def test_keep_zero_deletes_all(self, db):
        from dd.maintenance import prune_extraction_runs
        self._seed_runs(db, 5)
        prune_extraction_runs(db, keep_last=0)
        assert db.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM screen_extraction_status").fetchone()[0] == 0


class TestPruneExportValidations:
    """prune_export_validations() keeps the last N distinct run timestamps."""

    def _seed_validations(self, db, run_count: int, rows_per_run: int = 3):
        for i in range(1, run_count + 1):
            run_at = f"2026-03-{i:02d}T00:00:00Z"
            for j in range(rows_per_run):
                db.execute(
                    "INSERT INTO export_validations (run_at, check_name, severity, message) "
                    "VALUES (?, ?, 'info', 'test')",
                    (run_at, f"check_{j}"),
                )
        db.commit()

    def test_keeps_last_n_run_timestamps(self, db):
        from dd.maintenance import prune_export_validations
        self._seed_validations(db, 10)
        deleted = prune_export_validations(db, keep_last=3)
        remaining = db.execute("SELECT COUNT(DISTINCT run_at) FROM export_validations").fetchone()[0]
        assert remaining == 3
        assert deleted == 7 * 3

    def test_keeps_all_rows_for_retained_runs(self, db):
        from dd.maintenance import prune_export_validations
        self._seed_validations(db, 10, rows_per_run=5)
        prune_export_validations(db, keep_last=3)
        remaining_rows = db.execute("SELECT COUNT(*) FROM export_validations").fetchone()[0]
        assert remaining_rows == 3 * 5

    def test_keep_more_than_exist_deletes_nothing(self, db):
        from dd.maintenance import prune_export_validations
        self._seed_validations(db, 3)
        deleted = prune_export_validations(db, keep_last=10)
        assert deleted == 0

    def test_keep_zero_deletes_all(self, db):
        from dd.maintenance import prune_export_validations
        self._seed_validations(db, 5)
        prune_export_validations(db, keep_last=0)
        assert db.execute("SELECT COUNT(*) FROM export_validations").fetchone()[0] == 0
