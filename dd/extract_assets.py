"""Asset extraction: image hashes and vector geometry from the DB."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from abc import ABC, abstractmethod
from typing import Any


def extract_image_hashes_from_db(conn: sqlite3.Connection) -> set[str]:
    """Return unique image hashes found in node fills across the entire DB."""
    rows = conn.execute("SELECT fills FROM nodes WHERE fills IS NOT NULL").fetchall()
    hashes: set[str] = set()
    for row in rows:
        fills = json.loads(row["fills"])
        for fill in fills:
            if fill.get("type") == "IMAGE":
                image_hash = fill.get("imageHash")
                if image_hash:
                    hashes.add(image_hash)
    return hashes


def store_asset(
    conn: sqlite3.Connection,
    *,
    hash: str,
    kind: str,
    source_format: str | None = None,
    content_type: str | None = None,
) -> None:
    """Insert an asset into the registry, ignoring duplicates."""
    conn.execute(
        "INSERT OR IGNORE INTO assets (hash, kind, source_format, content_type) "
        "VALUES (?, ?, ?, ?)",
        (hash, kind, source_format, content_type),
    )


def link_node_asset(
    conn: sqlite3.Connection,
    *,
    node_id: int,
    asset_hash: str,
    role: str,
    fill_index: int | None = None,
) -> None:
    """Link a node to an asset via the node_asset_refs junction table."""
    conn.execute(
        "INSERT INTO node_asset_refs (node_id, asset_hash, role, fill_index) "
        "VALUES (?, ?, ?, ?)",
        (node_id, asset_hash, role, fill_index),
    )


def _hash_svg_paths(paths: list[dict]) -> tuple[str, str]:
    """Hash SVG path data and return (content_hash, combined_svg_data)."""
    combined = ";".join(
        f"{p.get('windingRule', 'NONZERO')}:{p.get('path', '')}"
        for p in paths
    )
    content_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
    svg_data = ";".join(p.get("path", "") for p in paths)
    return content_hash, svg_data


def process_vector_geometry(conn: sqlite3.Connection) -> int:
    """Process fill_geometry/stroke_geometry from nodes into content-addressed assets.

    Reads vector geometry JSON from nodes, hashes path data, stores as svg_path
    assets, and links nodes via node_asset_refs.

    Returns the number of nodes processed.
    """
    has_columns = {row[1] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}
    if "fill_geometry" not in has_columns:
        return 0

    rows = conn.execute(
        "SELECT id, fill_geometry, stroke_geometry FROM nodes "
        "WHERE fill_geometry IS NOT NULL OR stroke_geometry IS NOT NULL"
    ).fetchall()

    processed = 0
    for row in rows:
        node_id = row["id"]
        all_paths: list[dict] = []

        fg = row["fill_geometry"]
        if fg:
            all_paths.extend(json.loads(fg))

        sg = row["stroke_geometry"]
        if sg:
            all_paths.extend(json.loads(sg))

        if not all_paths:
            continue

        content_hash, svg_data = _hash_svg_paths(all_paths)

        store_asset(conn, hash=content_hash, kind="svg_path")
        conn.execute(
            "UPDATE assets SET metadata = ? WHERE hash = ? AND metadata IS NULL",
            (json.dumps({"svg_data": svg_data}), content_hash),
        )

        conn.execute(
            "INSERT OR IGNORE INTO node_asset_refs (node_id, asset_hash, role) "
            "VALUES (?, ?, 'icon')",
            (node_id, content_hash),
        )
        processed += 1

    conn.commit()
    return processed


class AssetResolver(ABC):
    """Abstract interface for resolving assets by hash.

    Backends (SQLite, cloud storage, CDN) implement this contract so
    renderers can resolve assets without coupling to storage details.
    """

    @abstractmethod
    def resolve(self, asset_hash: str) -> dict[str, Any] | None:
        """Resolve a single asset by hash. Returns None if not found."""

    def resolve_batch(self, asset_hashes: list[str]) -> dict[str, dict[str, Any]]:
        """Resolve multiple assets. Returns dict keyed by hash (missing keys omitted)."""
        results: dict[str, dict[str, Any]] = {}
        for h in asset_hashes:
            asset = self.resolve(h)
            if asset is not None:
                results[h] = asset
        return results


class SqliteAssetResolver(AssetResolver):
    """Resolve assets from the local SQLite database."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def resolve(self, asset_hash: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT hash, kind, source_format, content_type, metadata "
            "FROM assets WHERE hash = ?",
            (asset_hash,),
        ).fetchone()
        if row is None:
            return None

        result: dict[str, Any] = {
            "hash": row["hash"],
            "kind": row["kind"],
        }
        if row["source_format"]:
            result["source_format"] = row["source_format"]
        if row["content_type"]:
            result["content_type"] = row["content_type"]

        metadata_json = row["metadata"]
        if metadata_json:
            metadata = json.loads(metadata_json)
            svg_data = metadata.get("svg_data")
            if svg_data:
                result["svg_data"] = svg_data

        return result
