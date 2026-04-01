-- Migration 003: Component type catalog (T5 Phase 0)
--
-- Universal vocabulary of ~48 canonical UI component types.
-- Used by classification (Phase 1), IR generation (Phase 2),
-- and all downstream phases.
--
-- Run: sqlite3 your.declarative.db < migrations/003_component_type_catalog.sql

CREATE TABLE IF NOT EXISTS component_type_catalog (
    id                      INTEGER PRIMARY KEY,
    canonical_name          TEXT NOT NULL UNIQUE,
    aliases                 TEXT,
    category                TEXT NOT NULL CHECK(category IN (
        'actions','selection_and_input','content_and_display',
        'navigation','feedback_and_status','containment_and_overlay'
    )),
    behavioral_description  TEXT,
    prop_definitions        TEXT,
    slot_definitions        TEXT,
    semantic_role           TEXT,
    recognition_heuristics  TEXT,
    related_types           TEXT,
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_ctc_category ON component_type_catalog(category);
CREATE INDEX IF NOT EXISTS idx_ctc_semantic_role ON component_type_catalog(semantic_role);
