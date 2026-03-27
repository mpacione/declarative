"""Tests for binding-token value consistency detection.

detect_binding_mismatches() finds bound bindings whose resolved_value
doesn't match their token's value. This catches stale bindings from
normalization changes, designer edits, or token value modifications.
"""

import json
import sqlite3

import pytest

from tests.fixtures import seed_post_curation


def _seed_primitives_and_semantics(conn):
    """Seed a minimal primitives + semantics setup with alias chain."""
    conn.execute("INSERT INTO files (id, file_key, name, node_count, screen_count) VALUES (1, 'k', 'F', 1, 1)")

    conn.execute("INSERT INTO token_collections (id, file_id, name) VALUES (1, 1, 'Color Primitives')")
    conn.execute("INSERT INTO token_collections (id, file_id, name) VALUES (2, 1, 'Color Semantics')")

    conn.execute("INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (1, 1, 'Default', 1)")
    conn.execute("INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (2, 2, 'Default', 1)")

    conn.execute("INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (10, 1, 'prim.gray.950', 'color', 'curated')")
    conn.execute("INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (10, 1, '\"#000000\"', '#000000')")

    conn.execute("INSERT INTO tokens (id, collection_id, name, type, tier, alias_of) VALUES (20, 2, 'color.shadow.primary', 'color', 'aliased', 10)")

    conn.execute("INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (1, 1, 's1', 'S', 400, 800)")
    conn.execute("INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) VALUES (1, 1, 'n1', 'N', 'RECT')")

    conn.commit()


def _bind(conn, node_id, prop, resolved, token_id):
    conn.execute(
        "INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, token_id, binding_status) "
        "VALUES (?, ?, '{}', ?, ?, 'bound')",
        (node_id, prop, resolved, token_id),
    )
    conn.commit()


class TestDetectBindingMismatches:
    def test_no_mismatches_when_values_match(self, db):
        """Bindings matching their token value should not be flagged."""
        from dd.validate import detect_binding_mismatches

        _seed_primitives_and_semantics(db)
        _bind(db, 1, "fill.0.color", "#000000", 10)

        result = detect_binding_mismatches(db, file_id=1)

        assert result["total"] == 0
        assert result["mismatches"] == []

    def test_detects_mismatch_direct_token(self, db):
        """Binding with different value than its direct token should be flagged."""
        from dd.validate import detect_binding_mismatches

        _seed_primitives_and_semantics(db)
        _bind(db, 1, "fill.0.color", "#0000000D", 10)

        result = detect_binding_mismatches(db, file_id=1)

        assert result["total"] == 1
        assert result["mismatches"][0]["binding_value"] == "#0000000D"
        assert result["mismatches"][0]["token_value"] == "#000000"
        assert result["mismatches"][0]["token_name"] == "prim.gray.950"

    def test_detects_mismatch_through_alias(self, db):
        """Binding via alias should compare against the alias target's value."""
        from dd.validate import detect_binding_mismatches

        _seed_primitives_and_semantics(db)
        _bind(db, 1, "fill.0.color", "#0000000D", 20)  # bound to semantic alias

        result = detect_binding_mismatches(db, file_id=1)

        assert result["total"] == 1
        assert result["mismatches"][0]["token_name"] == "color.shadow.primary"

    def test_filters_by_token_id(self, db):
        """Should filter mismatches to a specific token when token_id provided."""
        from dd.validate import detect_binding_mismatches

        _seed_primitives_and_semantics(db)
        db.execute("INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (11, 1, 'prim.gray.50', 'color', 'curated')")
        db.execute("INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (11, 1, '\"#FFFFFF\"', '#FFFFFF')")
        db.execute("INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) VALUES (2, 1, 'n2', 'N2', 'RECT')")
        _bind(db, 1, "fill.0.color", "#0000000D", 10)
        _bind(db, 2, "fill.0.color", "#FFFFFF80", 11)
        db.commit()

        result = detect_binding_mismatches(db, file_id=1, token_id=10)

        assert result["total"] == 1
        assert result["mismatches"][0]["token_name"] == "prim.gray.950"

    def test_filters_by_screen_id(self, db):
        """Should filter mismatches to a specific screen when screen_id provided."""
        from dd.validate import detect_binding_mismatches

        _seed_primitives_and_semantics(db)
        db.execute("INSERT INTO screens (id, file_id, figma_node_id, name, width, height) VALUES (2, 1, 's2', 'S2', 400, 800)")
        db.execute("INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) VALUES (2, 2, 'n2', 'N2', 'RECT')")
        _bind(db, 1, "fill.0.color", "#0000000D", 10)
        _bind(db, 2, "fill.0.color", "#00000080", 10)
        db.commit()

        result = detect_binding_mismatches(db, file_id=1, screen_id=1)

        assert result["total"] == 1

    def test_ignores_unbound_bindings(self, db):
        """Unbound bindings should not be checked for mismatches."""
        from dd.validate import detect_binding_mismatches

        _seed_primitives_and_semantics(db)
        db.execute(
            "INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status) "
            "VALUES (1, 'fill.0.color', '{}', '#0000000D', 'unbound')"
        )
        db.commit()

        result = detect_binding_mismatches(db, file_id=1)

        assert result["total"] == 0

    def test_non_color_mismatches_detected(self, db):
        """Dimension/typography mismatches should also be detected."""
        from dd.validate import detect_binding_mismatches

        _seed_primitives_and_semantics(db)
        db.execute("INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (30, 1, 'space.s4', 'dimension', 'curated')")
        db.execute("INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (30, 1, '4', '4')")
        _bind(db, 1, "padding.top", "8", 30)
        db.commit()

        result = detect_binding_mismatches(db, file_id=1)

        assert result["total"] == 1
        assert result["mismatches"][0]["token_name"] == "space.s4"


class TestCheckBindingTokenConsistency:
    """Integration with validate.py check pattern."""

    def test_returns_warning_severity(self, db):
        """Mismatches should produce warning-severity issues."""
        from dd.validate import check_binding_token_consistency

        _seed_primitives_and_semantics(db)
        _bind(db, 1, "fill.0.color", "#0000000D", 10)

        issues = check_binding_token_consistency(db, file_id=1)

        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert issues[0]["check_name"] == "binding_token_consistency"

    def test_no_issues_when_consistent(self, db):
        """No issues returned when all bindings match their tokens."""
        from dd.validate import check_binding_token_consistency

        _seed_primitives_and_semantics(db)
        _bind(db, 1, "fill.0.color", "#000000", 10)

        issues = check_binding_token_consistency(db, file_id=1)

        assert len(issues) == 0

    def test_included_in_run_validation(self, db):
        """run_validation should include binding_token_consistency check."""
        from dd.validate import run_validation

        _seed_primitives_and_semantics(db)
        _bind(db, 1, "fill.0.color", "#0000000D", 10)

        result = run_validation(db, file_id=1)

        consistency_issues = [i for i in result["issues"] if i["check_name"] == "binding_token_consistency"]
        assert len(consistency_issues) >= 1


class TestUnbindMismatched:
    def test_sets_status_to_unbound(self, db):
        """unbind_mismatched should set binding_status to 'unbound' for mismatches."""
        from dd.validate import detect_binding_mismatches, unbind_mismatched

        _seed_primitives_and_semantics(db)
        _bind(db, 1, "fill.0.color", "#0000000D", 10)

        mismatches = detect_binding_mismatches(db, file_id=1)
        count = unbind_mismatched(db, file_id=1)

        assert count == 1
        row = db.execute(
            "SELECT binding_status, token_id FROM node_token_bindings WHERE node_id = 1 AND property = 'fill.0.color'"
        ).fetchone()
        assert row["binding_status"] == "unbound"
        assert row["token_id"] is None

    def test_does_not_touch_matching_bindings(self, db):
        """Bindings that match their token should remain bound."""
        from dd.validate import unbind_mismatched

        _seed_primitives_and_semantics(db)
        _bind(db, 1, "fill.0.color", "#000000", 10)

        count = unbind_mismatched(db, file_id=1)

        assert count == 0
        row = db.execute(
            "SELECT binding_status, token_id FROM node_token_bindings WHERE node_id = 1 AND property = 'fill.0.color'"
        ).fetchone()
        assert row["binding_status"] == "bound"
        assert row["token_id"] == 10

    def test_filters_by_token_id(self, db):
        """Should only unbind mismatches for the specified token."""
        from dd.validate import unbind_mismatched

        _seed_primitives_and_semantics(db)
        db.execute("INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (11, 1, 'prim.gray.50', 'color', 'curated')")
        db.execute("INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (11, 1, '\"#FFFFFF\"', '#FFFFFF')")
        db.execute("INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) VALUES (2, 1, 'n2', 'N2', 'RECT')")
        _bind(db, 1, "fill.0.color", "#0000000D", 10)
        _bind(db, 2, "fill.0.color", "#FFFFFF80", 11)
        db.commit()

        count = unbind_mismatched(db, file_id=1, token_id=10)

        assert count == 1
        row1 = db.execute("SELECT binding_status FROM node_token_bindings WHERE node_id = 1").fetchone()
        row2 = db.execute("SELECT binding_status FROM node_token_bindings WHERE node_id = 2").fetchone()
        assert row1["binding_status"] == "unbound"
        assert row2["binding_status"] == "bound"
