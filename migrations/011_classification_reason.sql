-- Migration 011: Classification reason column (M7.0.a)
--
-- Adds a free-text column capturing the LLM's one-sentence reason
-- for each classification. The M7.0.a LLM + vision stages emit a
-- `reason` field via tool-use; this column persists it so a
-- spot-check / quality audit can read the evidence the model
-- cited, not just the verdict. Alexander's force-resolution
-- principle: every pattern application carries the problem it
-- resolved, not just the solution.
--
-- Also adds `vision_reason` alongside `vision_type`/`vision_agrees`
-- so the vision pass's evidence is queryable too.
--
-- Run: sqlite3 your.declarative.db < migrations/011_classification_reason.sql

ALTER TABLE screen_component_instances ADD COLUMN classification_reason TEXT;
ALTER TABLE screen_component_instances ADD COLUMN vision_reason TEXT;
