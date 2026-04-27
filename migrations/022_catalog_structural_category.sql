-- Migration 022: widen component_type_catalog.category CHECK to accept
-- 'structural' (Stage 0.1 of docs/plan-authoring-loop.md).
--
-- The six intent categories (actions / selection / content / navigation
-- / feedback / containment) describe what a *user-facing* component
-- does. Stage 0.1 adds a seventh category, `structural`, for neutral
-- layout primitives — specifically `frame`, the author-supplied
-- container that expresses conceptual grouping without collapsing
-- onto a semantic type like `card`. Without this widening, seed_catalog
-- fails when it tries to INSERT the frame row.
--
-- SQLite CHECK constraints are not alterable in place, so the standard
-- table-rebuild idiom is used: create a new table with the updated
-- constraint, copy rows over, swap in, rebuild indexes.
--
-- Run: sqlite3 your.declarative.db < migrations/022_catalog_structural_category.sql

BEGIN TRANSACTION;

CREATE TABLE component_type_catalog_new (
    id                      INTEGER PRIMARY KEY,
    canonical_name          TEXT NOT NULL UNIQUE,
    aliases                 TEXT,
    category                TEXT NOT NULL CHECK(category IN (
        'actions','selection_and_input','content_and_display',
        'navigation','feedback_and_status','containment_and_overlay',
        'structural'
    )),
    behavioral_description  TEXT,
    prop_definitions        TEXT,
    slot_definitions        TEXT,
    semantic_role           TEXT,
    recognition_heuristics  TEXT,
    related_types           TEXT,
    variant_axes            TEXT,
    clay_equivalent         TEXT,
    aria_role               TEXT,
    disambiguation_notes    TEXT,
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT INTO component_type_catalog_new
SELECT id, canonical_name, aliases, category,
       behavioral_description, prop_definitions, slot_definitions,
       semantic_role, recognition_heuristics, related_types,
       variant_axes, clay_equivalent, aria_role, disambiguation_notes,
       created_at
FROM component_type_catalog;

DROP TABLE component_type_catalog;
ALTER TABLE component_type_catalog_new RENAME TO component_type_catalog;

CREATE INDEX IF NOT EXISTS idx_ctc_category ON component_type_catalog(category);
CREATE INDEX IF NOT EXISTS idx_ctc_semantic_role ON component_type_catalog(semantic_role);

COMMIT;
