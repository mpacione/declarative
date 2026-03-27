"""Tests for clustering of extended properties (stroke weight, paragraph spacing)."""

import sqlite3
import pytest

from dd.db import init_db


def _seed_file_screen_nodes(conn, node_count=10):
    conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'k', 'F')")
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'S', 400, 800)"
    )
    for i in range(1, node_count + 1):
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
            "VALUES (?, 1, ?, ?, 'RECTANGLE')",
            (i, f"n{i}", f"N{i}"),
        )
    conn.commit()


def _add_bindings(conn, bindings):
    for bid, node_id, prop, val in bindings:
        conn.execute(
            "INSERT INTO node_token_bindings (id, node_id, property, raw_value, resolved_value, binding_status) "
            "VALUES (?, ?, ?, ?, ?, 'unbound')",
            (bid, node_id, prop, val, val),
        )
    conn.commit()


def _ensure_collection(conn, name="StrokeWeight"):
    conn.execute(
        "INSERT INTO token_collections (id, file_id, name) VALUES (100, 1, ?)", (name,)
    )
    conn.execute(
        "INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (100, 100, 'Default', 1)"
    )
    conn.commit()
    return 100, 100


class TestClusterStrokeWeight:
    def test_creates_tokens_for_unique_values(self, db):
        from dd.cluster_misc import cluster_stroke_weight

        _seed_file_screen_nodes(db, 6)
        _add_bindings(db, [
            (1, 1, "strokeWeight", "1"),
            (2, 2, "strokeWeight", "1"),
            (3, 3, "strokeWeight", "2"),
            (4, 4, "strokeWeight", "2"),
            (5, 5, "strokeWeight", "2"),
            (6, 6, "strokeWeight", "3"),
        ])
        coll_id, mode_id = _ensure_collection(db)

        result = cluster_stroke_weight(db, 1, coll_id, mode_id)

        assert result["tokens_created"] == 3
        assert result["bindings_updated"] == 6

    def test_updates_bindings_to_proposed(self, db):
        from dd.cluster_misc import cluster_stroke_weight

        _seed_file_screen_nodes(db, 3)
        _add_bindings(db, [
            (1, 1, "strokeWeight", "1"),
            (2, 2, "strokeWeight", "2"),
            (3, 3, "strokeWeight", "2"),
        ])
        coll_id, mode_id = _ensure_collection(db)

        cluster_stroke_weight(db, 1, coll_id, mode_id)

        proposed = db.execute(
            "SELECT COUNT(*) FROM node_token_bindings WHERE binding_status = 'proposed'"
        ).fetchone()[0]
        assert proposed == 3

    def test_skips_zero_weight(self, db):
        from dd.cluster_misc import cluster_stroke_weight

        _seed_file_screen_nodes(db, 2)
        _add_bindings(db, [
            (1, 1, "strokeWeight", "0"),
            (2, 2, "strokeWeight", "1"),
        ])
        coll_id, mode_id = _ensure_collection(db)

        result = cluster_stroke_weight(db, 1, coll_id, mode_id)

        assert result["tokens_created"] == 1


class TestClusterParagraphSpacing:
    def test_creates_tokens(self, db):
        from dd.cluster_misc import cluster_paragraph_spacing

        _seed_file_screen_nodes(db, 3)
        _add_bindings(db, [
            (1, 1, "paragraphSpacing", "8"),
            (2, 2, "paragraphSpacing", "16"),
            (3, 3, "paragraphSpacing", "16"),
        ])
        coll_id, mode_id = _ensure_collection(db, "Spacing")

        result = cluster_paragraph_spacing(db, 1, coll_id, mode_id)

        assert result["tokens_created"] == 2
        assert result["bindings_updated"] == 3
