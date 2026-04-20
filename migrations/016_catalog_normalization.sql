-- Migration 016: Catalog normalization for classifier v2.1
--
-- Adds three columns to `component_type_catalog` that support both
-- (a) the classifier prompts (disambiguation_notes help the model
-- pick between neighbors) and (b) ecosystem alignment (CLAY/ARIA
-- names the vision models were trained on).
--
-- Added columns:
--   clay_equivalent  TEXT  — Google Research CLAY taxonomy name
--                           (25-type mobile UI dataset). NULL when
--                           our type has no CLAY analogue.
--   aria_role        TEXT  — W3C WAI-ARIA widget/document role.
--                           NULL when ARIA has no matching role
--                           (e.g., chrome / layout primitives).
--   disambiguation_notes TEXT — free-text hints the prompt feeds
--                           to the LLM/vision model: "this is
--                           NOT a <neighbor type> because...".
--                           Load-bearing when two catalog entries
--                           look similar (tooltip vs popover vs
--                           toast).
--
-- Non-destructive. Existing rows keep all their current values;
-- new columns default NULL and get populated by the updated
-- seed_catalog routine.
--
-- Run: sqlite3 your.declarative.db < migrations/016_catalog_normalization.sql

ALTER TABLE component_type_catalog ADD COLUMN clay_equivalent TEXT;
ALTER TABLE component_type_catalog ADD COLUMN aria_role TEXT;
ALTER TABLE component_type_catalog ADD COLUMN disambiguation_notes TEXT;
