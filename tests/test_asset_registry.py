"""Tests for the asset registry schema and operations."""

import sqlite3

import pytest

from dd.db import init_db


class TestAssetRegistrySchema:
    """Verify assets and node_asset_refs tables exist and enforce constraints."""

    def test_assets_table_exists(self):
        conn = init_db(":memory:")
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='assets'"
        )
        assert cursor.fetchone() is not None

    def test_asset_insert_and_select(self):
        conn = init_db(":memory:")
        conn.execute(
            "INSERT INTO assets (hash, kind, source_format, content_type) "
            "VALUES ('abc123', 'raster', 'png', 'image/png')"
        )
        row = conn.execute("SELECT hash, kind FROM assets WHERE hash='abc123'").fetchone()
        assert row["hash"] == "abc123"
        assert row["kind"] == "raster"

    def test_asset_hash_unique_constraint(self):
        conn = init_db(":memory:")
        conn.execute(
            "INSERT INTO assets (hash, kind) VALUES ('dup', 'raster')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO assets (hash, kind) VALUES ('dup', 'svg_path')"
            )

    def test_asset_kind_check_constraint(self):
        conn = init_db(":memory:")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO assets (hash, kind) VALUES ('x', 'invalid_kind')"
            )

    def test_node_asset_refs_table_exists(self):
        conn = init_db(":memory:")
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='node_asset_refs'"
        )
        assert cursor.fetchone() is not None

    def test_node_asset_ref_insert(self):
        conn = init_db(":memory:")
        # Set up prerequisite data
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order) "
            "VALUES (1, '1:1', 'Image', 'RECTANGLE', 1, 0)"
        )
        conn.execute(
            "INSERT INTO assets (hash, kind) VALUES ('img_hash', 'raster')"
        )
        conn.execute(
            "INSERT INTO node_asset_refs (node_id, asset_hash, role) "
            "VALUES (1, 'img_hash', 'fill')"
        )
        row = conn.execute(
            "SELECT node_id, asset_hash, role FROM node_asset_refs WHERE node_id=1"
        ).fetchone()
        assert row["node_id"] == 1
        assert row["asset_hash"] == "img_hash"
        assert row["role"] == "fill"

    def test_node_asset_ref_cascade_delete(self):
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order) "
            "VALUES (1, '1:1', 'Img', 'RECTANGLE', 1, 0)"
        )
        conn.execute("INSERT INTO assets (hash, kind) VALUES ('h1', 'raster')")
        conn.execute(
            "INSERT INTO node_asset_refs (node_id, asset_hash, role) VALUES (1, 'h1', 'fill')"
        )
        conn.execute("DELETE FROM nodes WHERE id=1")
        count = conn.execute("SELECT COUNT(*) FROM node_asset_refs").fetchone()[0]
        assert count == 0

    def test_role_check_constraint(self):
        conn = init_db(":memory:")
        conn.execute("INSERT INTO assets (hash, kind) VALUES ('h1', 'raster')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO node_asset_refs (node_id, asset_hash, role) "
                "VALUES (1, 'h1', 'bad_role')"
            )
