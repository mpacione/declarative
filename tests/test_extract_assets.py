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


class TestProcessVectorGeometry:
    """Verify extracting vector geometry from nodes into content-addressed assets."""

    def test_creates_assets_from_fill_geometry(self):
        from dd.extract_assets import process_vector_geometry
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order, fill_geometry) "
            "VALUES (1, '1:1', 'Arrow', 'VECTOR', 1, 0, ?)",
            (json.dumps([{"path": "M 0 0 L 24 12 L 0 24 Z", "windingRule": "NONZERO"}]),)
        )
        count = process_vector_geometry(conn)
        assert count == 1

        asset = conn.execute("SELECT hash, kind, metadata FROM assets").fetchone()
        assert asset["kind"] == "svg_path"
        metadata = json.loads(asset["metadata"])
        assert "M 0 0 L 24 12 L 0 24 Z" in metadata["svg_data"]

        ref = conn.execute("SELECT asset_hash, role FROM node_asset_refs WHERE node_id=1").fetchone()
        assert ref["role"] == "icon"
        assert ref["asset_hash"] == asset["hash"]

    def test_creates_assets_from_stroke_geometry(self):
        from dd.extract_assets import process_vector_geometry
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order, stroke_geometry) "
            "VALUES (1, '1:1', 'Outline', 'VECTOR', 1, 0, ?)",
            (json.dumps([{"path": "M 1 1 L 23 1 L 23 23 Z", "windingRule": "EVENODD"}]),)
        )
        count = process_vector_geometry(conn)
        assert count == 1

        ref = conn.execute("SELECT role FROM node_asset_refs WHERE node_id=1").fetchone()
        assert ref["role"] == "icon"

    def test_skips_nodes_without_geometry(self):
        from dd.extract_assets import process_vector_geometry
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
        count = process_vector_geometry(conn)
        assert count == 0

    def test_identical_paths_share_asset(self):
        from dd.extract_assets import process_vector_geometry
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        path_json = json.dumps([{"path": "M 0 0 L 10 10", "windingRule": "NONZERO"}])
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order, fill_geometry) "
            "VALUES (1, '1:1', 'Icon1', 'VECTOR', 1, 0, ?)",
            (path_json,)
        )
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, sort_order, fill_geometry) "
            "VALUES (1, '1:2', 'Icon2', 'VECTOR', 1, 1, ?)",
            (path_json,)
        )
        count = process_vector_geometry(conn)
        assert count == 2

        asset_count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        assert asset_count == 1

        ref_count = conn.execute("SELECT COUNT(*) FROM node_asset_refs").fetchone()[0]
        assert ref_count == 2

    def test_processes_figma_api_key_data_not_path(self):
        """Figma Plugin API returns fillGeometry / strokeGeometry as
        arrays of objects with key `data`, NOT `path` (verified by
        inspecting `node.fillGeometry[0]`). process_vector_geometry
        must read `data` or svg_data will silently become "" across
        every vector node — hash collisions collapse all 26,050+
        VECTORs to a single empty asset, and the renderer emits no
        paths.

        Regression guard for the 2026-04-15 chapter's re-extract
        incident."""
        from dd.extract_assets import process_vector_geometry
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        # The Figma Plugin API shape: {data, windingRule}
        # (verified on Dank screen 175 vector id 21358).
        figma_shape = json.dumps([
            {"data": "M11.6667 16.0001 L0.999999 16.0001", "windingRule": "NONZERO"},
        ])
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, "
            "depth, sort_order, fill_geometry) "
            "VALUES (1, '1:1', 'Arrow', 'VECTOR', 1, 0, ?)",
            (figma_shape,),
        )
        count = process_vector_geometry(conn)
        assert count == 1

        asset = conn.execute("SELECT hash, metadata FROM assets").fetchone()
        metadata = json.loads(asset["metadata"])
        assert metadata["svg_data"], (
            "svg_data must be non-empty when the Figma API returned "
            "path data under key 'data'"
        )
        # After normalization, coordinates keep their values; only the
        # letter-to-digit boundary gets a space inserted.
        assert "11.6667 16.0001" in metadata["svg_data"], (
            "svg_data must contain the original path coordinates, not an "
            "empty placeholder"
        )

    def test_normalizes_compact_svg_commands_for_figma_parser(self):
        """Figma's vectorPaths parser rejects compact SVG shorthand
        like `M160.757 118.403` with "Invalid command at M160.757".
        The Plugin API's own `node.fillGeometry` returns exactly that
        shorthand. process_vector_geometry must normalize so the
        stored svg_data has a space after each command letter."""
        from dd.extract_assets import process_vector_geometry
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        # Real Plugin-API output is compact: no space after M/L/C/Z.
        compact_path = json.dumps([
            {"data": "M160.757 118.403L7.39424 118.403Z", "windingRule": "NONZERO"},
        ])
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, "
            "depth, sort_order, fill_geometry) "
            "VALUES (1, '1:1', 'Frame', 'VECTOR', 1, 0, ?)",
            (compact_path,),
        )
        count = process_vector_geometry(conn)
        assert count == 1
        asset = conn.execute("SELECT metadata FROM assets").fetchone()
        metadata = json.loads(asset["metadata"])
        svg = metadata["svg_data"]
        # Every command letter M/L/C/Z followed by a digit/minus/period
        # must have a space between them after normalization.
        assert "M 160.757" in svg
        assert "L 7.39424" in svg
        # No compact form should survive
        assert "M160" not in svg
        assert "L7." not in svg

    def test_distinct_paths_get_distinct_content_hashes_figma_shape(self):
        """Content addressing must work with the real Figma shape.
        Two nodes with different path data → two different hashes,
        even when the key is 'data' (not 'path')."""
        from dd.extract_assets import process_vector_geometry
        conn = init_db(":memory:")
        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height) "
            "VALUES (1, '1:0', 'Screen', 375, 812)"
        )
        path_a = json.dumps([{"data": "M 0 0 L 10 10", "windingRule": "NONZERO"}])
        path_b = json.dumps([{"data": "M 5 5 L 15 15", "windingRule": "NONZERO"}])
        for fig, path in [("1:1", path_a), ("1:2", path_b)]:
            conn.execute(
                "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, "
                "depth, sort_order, fill_geometry) "
                "VALUES (1, ?, 'Icon', 'VECTOR', 1, 0, ?)",
                (fig, path),
            )
        count = process_vector_geometry(conn)
        assert count == 2
        distinct_hashes = conn.execute(
            "SELECT COUNT(DISTINCT hash) FROM assets"
        ).fetchone()[0]
        assert distinct_hashes == 2, (
            f"expected 2 distinct content hashes for 2 distinct paths, "
            f"got {distinct_hashes} (hash collision — paths treated as "
            f"identical, likely because they're being read as empty)"
        )


class TestAssetResolver:
    """Verify the abstract AssetResolver contract and SQLite implementation."""

    def test_sqlite_resolver_resolves_raster_asset(self):
        from dd.extract_assets import SqliteAssetResolver, store_asset
        conn = init_db(":memory:")
        store_asset(conn, hash="img123", kind="raster", content_type="image/png")
        resolver = SqliteAssetResolver(conn)
        asset = resolver.resolve("img123")
        assert asset is not None
        assert asset["hash"] == "img123"
        assert asset["kind"] == "raster"
        assert asset["content_type"] == "image/png"

    def test_sqlite_resolver_resolves_svg_path_with_metadata(self):
        from dd.extract_assets import SqliteAssetResolver, store_asset
        conn = init_db(":memory:")
        store_asset(conn, hash="vec456", kind="svg_path")
        conn.execute(
            "UPDATE assets SET metadata = ? WHERE hash = 'vec456'",
            (json.dumps({"svg_data": "M 0 0 L 10 10"}),),
        )
        resolver = SqliteAssetResolver(conn)
        asset = resolver.resolve("vec456")
        assert asset is not None
        assert asset["kind"] == "svg_path"
        assert asset["svg_data"] == "M 0 0 L 10 10"

    def test_sqlite_resolver_returns_none_for_missing(self):
        from dd.extract_assets import SqliteAssetResolver
        conn = init_db(":memory:")
        resolver = SqliteAssetResolver(conn)
        assert resolver.resolve("nonexistent") is None

    def test_sqlite_resolver_resolve_batch(self):
        from dd.extract_assets import SqliteAssetResolver, store_asset
        conn = init_db(":memory:")
        store_asset(conn, hash="a1", kind="raster")
        store_asset(conn, hash="a2", kind="svg_path")
        resolver = SqliteAssetResolver(conn)
        results = resolver.resolve_batch(["a1", "a2", "missing"])
        assert "a1" in results
        assert "a2" in results
        assert "missing" not in results


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
