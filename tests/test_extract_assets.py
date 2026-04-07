"""Tests for asset extraction (image hashes and vector geometry)."""

import json
import sqlite3

import pytest

from dd.db import init_db
from dd.ir import query_screen_visuals


class TestExtractImageHashes:
    """Verify extraction of unique image hashes from node fills."""

    def test_extract_unique_hashes_from_fills(self):
        from dd.extract_assets import extract_image_hashes_from_db
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order, fills) "
            "VALUES (1, '1:1', 'Bg', 'RECTANGLE', 1, 0, ?)",
            (json.dumps([{"type": "IMAGE", "imageHash": "abc123", "scaleMode": "FILL"}]),)
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order, fills) "
            "VALUES (1, '1:2', 'Photo', 'RECTANGLE', 1, 1, ?)",
            (json.dumps([{"type": "IMAGE", "imageHash": "abc123", "scaleMode": "FIT"},
                         {"type": "IMAGE", "imageHash": "xyz789", "scaleMode": "FILL"}]),)
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order, fills) "
            "VALUES (1, '1:3', 'Solid', 'RECTANGLE', 1, 2, ?)",
            (json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0, "a": 1}}]),)
        )
        hashes = extract_image_hashes_from_db(conn)
        assert hashes == {"abc123", "xyz789"}

    def test_no_image_fills_returns_empty(self):
        from dd.extract_assets import extract_image_hashes_from_db
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order, fills) "
            "VALUES (1, '1:1', 'Box', 'RECTANGLE', 1, 0, ?)",
            (json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0, "a": 1}}]),)
        )
        hashes = extract_image_hashes_from_db(conn)
        assert hashes == set()

    def test_skips_null_fills(self):
        from dd.extract_assets import extract_image_hashes_from_db
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order) "
            "VALUES (1, '1:1', 'Box', 'RECTANGLE', 1, 0)"
        )
        hashes = extract_image_hashes_from_db(conn)
        assert hashes == set()


class TestStoreAsset:
    """Verify storing assets into the registry."""

    def test_store_raster_asset(self):
        from dd.extract_assets import store_asset
        conn = init_db(":memory:")
        store_asset(conn, hash="abc123", kind="raster",
                    source_format="png", content_type="image/png")
        row = conn.execute("SELECT hash, kind FROM assets WHERE hash='abc123'").fetchone()
        assert row["hash"] == "abc123"
        assert row["kind"] == "raster"

    def test_store_duplicate_hash_is_idempotent(self):
        from dd.extract_assets import store_asset
        conn = init_db(":memory:")
        store_asset(conn, hash="abc", kind="raster")
        store_asset(conn, hash="abc", kind="raster")
        count = conn.execute("SELECT COUNT(*) FROM assets WHERE hash='abc'").fetchone()[0]
        assert count == 1


class TestLinkNodeAsset:
    """Verify linking nodes to assets."""

    def test_link_image_fill(self):
        from dd.extract_assets import store_asset, link_node_asset
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
        store_asset(conn, hash="h1", kind="raster")
        link_node_asset(conn, node_id=1, asset_hash="h1", role="fill", fill_index=0)
        row = conn.execute(
            "SELECT asset_hash, role, fill_index FROM node_asset_refs WHERE node_id=1"
        ).fetchone()
        assert row["asset_hash"] == "h1"
        assert row["role"] == "fill"
        assert row["fill_index"] == 0


class TestAssetRefsInVisuals:
    """Verify asset refs are surfaced through query_screen_visuals."""

    def test_asset_refs_populated_in_visuals(self):
        from dd.extract_assets import store_asset, link_node_asset
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order) "
            "VALUES (1, '1:1', 'Icon', 'VECTOR', 1, 0)"
        )
        store_asset(conn, hash="vec1", kind="svg_path")
        # Store svg_data as metadata JSON
        conn.execute(
            "UPDATE assets SET metadata = ? WHERE hash = 'vec1'",
            (json.dumps({"svg_data": "M 0 0 L 10 10"}),),
        )
        link_node_asset(conn, node_id=1, asset_hash="vec1", role="icon")
        visuals = query_screen_visuals(conn, screen_id=1)
        node_visual = visuals[1]
        assert "_asset_refs" in node_visual
        refs = node_visual["_asset_refs"]
        assert len(refs) == 1
        assert refs[0]["asset_hash"] == "vec1"
        assert refs[0]["kind"] == "svg_path"
        assert refs[0]["svg_data"] == "M 0 0 L 10 10"

    def test_no_asset_refs_when_none_linked(self):
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order) "
            "VALUES (1, '1:1', 'Box', 'RECTANGLE', 1, 0)"
        )
        visuals = query_screen_visuals(conn, screen_id=1)
        assert "_asset_refs" not in visuals[1]
