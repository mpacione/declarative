-- Migration 004: Classification tables (T5 Phase 1)
--
-- Component instance classification and screen skeletons.
-- Used by the classification cascade to store results.
--
-- Run: sqlite3 your.declarative.db < migrations/004_classification_tables.sql

CREATE TABLE IF NOT EXISTS screen_component_instances (
    id                    INTEGER PRIMARY KEY,
    screen_id             INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
    node_id               INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    catalog_type_id       INTEGER REFERENCES component_type_catalog(id),
    canonical_type        TEXT NOT NULL,
    confidence            REAL NOT NULL DEFAULT 1.0,
    classification_source TEXT NOT NULL CHECK(classification_source IN (
        'formal','heuristic','llm','vision','manual'
    )),
    parent_instance_id    INTEGER REFERENCES screen_component_instances(id),
    slot_name             TEXT,
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(screen_id, node_id)
);

CREATE INDEX IF NOT EXISTS idx_sci_screen ON screen_component_instances(screen_id);
CREATE INDEX IF NOT EXISTS idx_sci_type ON screen_component_instances(canonical_type);

CREATE TABLE IF NOT EXISTS screen_skeletons (
    id                    INTEGER PRIMARY KEY,
    screen_id             INTEGER NOT NULL UNIQUE REFERENCES screens(id) ON DELETE CASCADE,
    skeleton_notation     TEXT NOT NULL,
    skeleton_type         TEXT,
    zone_map              TEXT,
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
