-- Migration 007: Layout Defaults Backfill
-- The REST API omits fields with default values. This migration backfills
-- known defaults for layout properties that were stored as NULL.
--
-- Safe to run multiple times — only updates NULL values.

-- layoutWrap defaults to NO_WRAP for auto-layout containers
UPDATE nodes SET layout_wrap = 'NO_WRAP'
WHERE layout_mode IS NOT NULL AND layout_wrap IS NULL;
