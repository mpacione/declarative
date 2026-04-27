-- Migration 014: Rename classification_reason → llm_reason (M7.0.a)
--
-- The `classification_reason` column was introduced in migration 011
-- to hold the LLM text stage's one-sentence evidence. With the
-- three-source architecture landing (migration 013 adds per-source
-- vision_ps_reason + vision_cs_reason columns), keeping the name
-- `classification_reason` is ambiguous — it suggests a generic
-- "reason for the final classification," but the column has only
-- ever carried the LLM text stage's reason. Rename to make the
-- ownership unambiguous. Data is preserved: SQLite ≥ 3.25 supports
-- ALTER TABLE ... RENAME COLUMN in-place.
--
-- Run: sqlite3 your.declarative.db < migrations/014_rename_classification_reason.sql
--
-- Non-idempotent at the statement level; the migration will error on
-- re-apply ("no such column: classification_reason"). This is
-- acceptable — migrations are one-shot.

ALTER TABLE screen_component_instances
    RENAME COLUMN classification_reason TO llm_reason;
