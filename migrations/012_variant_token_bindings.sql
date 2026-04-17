-- Migration 012: variant_token_binding (ADR-008 PR #1 main)
--
-- Stores the output of the Stream-B variant inducer: per
-- (catalog_type, variant, slot) → token_id bindings learned from the
-- corpus via clustering + Gemini 3.1 Pro VLM labelling.
--
-- Consumed by ProjectCKRProvider during Mode-3 resolution to attach
-- project-native presentation values to synthesised subtrees.
--
-- Run: sqlite3 your.declarative.db < migrations/012_variant_token_bindings.sql
--
-- Idempotent: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS variant_token_binding (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_type    TEXT NOT NULL,
    variant         TEXT NOT NULL,
    slot            TEXT NOT NULL,
    token_id        INTEGER REFERENCES tokens(id),
    literal_value   TEXT,
    confidence      REAL NOT NULL DEFAULT 0.0,
    source          TEXT NOT NULL CHECK(source IN (
        'cluster','vlm','screen_context','user'
    )),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(catalog_type, variant, slot)
);

CREATE INDEX IF NOT EXISTS idx_vtb_catalog_type ON variant_token_binding(catalog_type);
CREATE INDEX IF NOT EXISTS idx_vtb_catalog_variant ON variant_token_binding(catalog_type, variant);
