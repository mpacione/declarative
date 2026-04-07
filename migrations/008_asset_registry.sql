-- Migration 008: Asset Registry
-- Adds content-addressed asset store for images, vectors, and icons.
-- Safe to run multiple times — CREATE TABLE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS assets (
    id              INTEGER PRIMARY KEY,
    hash            TEXT NOT NULL UNIQUE,
    kind            TEXT NOT NULL CHECK(kind IN ('svg_path', 'svg_doc', 'raster')),
    bytes           BLOB,
    source_format   TEXT,
    content_type    TEXT,
    intrinsic_width  INTEGER,
    intrinsic_height INTEGER,
    metadata        TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_assets_hash ON assets(hash);

CREATE TABLE IF NOT EXISTS node_asset_refs (
    id              INTEGER PRIMARY KEY,
    node_id         INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    asset_hash      TEXT NOT NULL REFERENCES assets(hash),
    role            TEXT NOT NULL CHECK(role IN ('fill', 'icon', 'illustration', 'background', 'mask')),
    scale_mode      TEXT CHECK(scale_mode IN ('fill', 'fit', 'crop', 'tile')),
    fill_index      INTEGER,
    UNIQUE(node_id, role, fill_index)
);

CREATE INDEX IF NOT EXISTS idx_node_asset_refs_node ON node_asset_refs(node_id);
CREATE INDEX IF NOT EXISTS idx_node_asset_refs_hash ON node_asset_refs(asset_hash);
