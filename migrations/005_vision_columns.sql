-- Migration 005: Vision cross-validation columns (T5 Phase 1b)
--
-- Adds vision classifier result, agreement flag, and review flag
-- to screen_component_instances for cross-validation workflow.
--
-- Run: sqlite3 your.declarative.db < migrations/005_vision_columns.sql

ALTER TABLE screen_component_instances ADD COLUMN vision_type TEXT;
ALTER TABLE screen_component_instances ADD COLUMN vision_agrees INTEGER;
ALTER TABLE screen_component_instances ADD COLUMN flagged_for_review INTEGER DEFAULT 0;
