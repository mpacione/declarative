-- Migration 017: SoM verdict columns on screen_component_instances.
--
-- Set-of-Marks is the visual classification path added 2026-04-20 as
-- an experimental bake-off source; after multiple adjudication rounds
-- (276-285, 286-295, 160-189) it consistently wins 62-69% of
-- disagreements against vision_ps / vision_cs and is now persisted
-- as a fourth per-source verdict alongside LLM + PS + CS.
--
-- Same shape as the vision_ps_* / vision_cs_* columns (migration 013):
-- type + confidence + reason. No evidence_json — SoM does its
-- reasoning in-prompt; the reason string is the full rationale.
--
-- Run: sqlite3 your.declarative.db < migrations/017_som_verdict_columns.sql
--
-- Idempotent via `dd.db.run_migration`; ALTER TABLE ADD COLUMN skips
-- "duplicate column" errors.

ALTER TABLE screen_component_instances ADD COLUMN vision_som_type TEXT;
ALTER TABLE screen_component_instances ADD COLUMN vision_som_confidence REAL;
ALTER TABLE screen_component_instances ADD COLUMN vision_som_reason TEXT;
