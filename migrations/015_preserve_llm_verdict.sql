-- Migration 015: Preserve LLM verdict separately from canonical_type (M7.0.a)
--
-- Plan §5.1.a says `canonical_type` becomes the COMPUTED consensus
-- (not the primary signal). Previously, classify_llm wrote its
-- verdict directly to canonical_type — which meant running consensus
-- destroyed the LLM's original verdict. Rule-v2 iteration
-- (plan §5.1.b Step 12) needs to recompute from raw sources WITHOUT
-- re-classification; that requires the primary verdict preserved.
--
-- This migration adds `llm_type` and `llm_confidence` columns so
-- classify_llm can write to them alongside canonical_type (v1 wiring)
-- or exclusively (future wiring). With all three sources preserved
-- (llm_type, vision_ps_type, vision_cs_type), the consensus rule is a
-- pure function of persisted data.
--
-- Run: sqlite3 your.declarative.db < migrations/015_preserve_llm_verdict.sql
--
-- Idempotent via run_migration's duplicate-column skip.

ALTER TABLE screen_component_instances ADD COLUMN llm_type TEXT;
ALTER TABLE screen_component_instances ADD COLUMN llm_confidence REAL;
