-- Migration 013: Three-source classification (M7.0.a)
--
-- Extends `screen_component_instances` with per-source verdicts so a
-- consensus rule can compute `canonical_type` from persisted raw
-- signals. Decision 2026-04-19 (plan-synthetic-gen.md §5.1.a): all
-- three sources (LLM text + vision per-screen + vision cross-screen)
-- are kept permanently; consensus is a *computed* value, never the
-- primary signal. Rule v2 iteration does NOT require re-classification
-- — the persisted columns are the source of truth.
--
-- Also creates `classification_reviews`: one row per human decision,
-- additive + reversible. Decisions override the computed consensus
-- via a downstream view (added in a later step). Each review carries
-- the decision_type (accept_source / override / unsure / skip), which
-- source was accepted when applicable, the final canonical_type the
-- human picked, and free-text notes.
--
-- Run: sqlite3 your.declarative.db < migrations/013_three_source_classification.sql
--
-- Idempotent: ALTER ... ADD COLUMN skips "duplicate column" errors via
-- `dd.db.run_migration`; CREATE TABLE IF NOT EXISTS / CREATE INDEX
-- IF NOT EXISTS on the new table.

ALTER TABLE screen_component_instances ADD COLUMN vision_ps_type TEXT;
ALTER TABLE screen_component_instances ADD COLUMN vision_ps_confidence REAL;
ALTER TABLE screen_component_instances ADD COLUMN vision_ps_reason TEXT;
ALTER TABLE screen_component_instances ADD COLUMN vision_cs_type TEXT;
ALTER TABLE screen_component_instances ADD COLUMN vision_cs_confidence REAL;
ALTER TABLE screen_component_instances ADD COLUMN vision_cs_reason TEXT;
ALTER TABLE screen_component_instances ADD COLUMN vision_cs_evidence_json TEXT;
ALTER TABLE screen_component_instances ADD COLUMN consensus_method TEXT;

CREATE TABLE IF NOT EXISTS classification_reviews (
    id                      INTEGER PRIMARY KEY,
    sci_id                  INTEGER NOT NULL REFERENCES screen_component_instances(id) ON DELETE CASCADE,
    decided_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    decided_by              TEXT NOT NULL DEFAULT 'human',
    decision_type           TEXT NOT NULL CHECK(decision_type IN (
        'accept_source', 'override', 'unsure', 'skip', 'audit'
    )),
    decision_canonical_type TEXT,
    source_accepted         TEXT CHECK(source_accepted IN (
        'llm', 'vision_ps', 'vision_cs', 'formal', 'heuristic'
    )),
    notes                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_reviews_sci ON classification_reviews(sci_id);
