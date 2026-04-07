"""Asset extraction: image hashes and vector geometry from the DB."""

import json
import sqlite3


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
