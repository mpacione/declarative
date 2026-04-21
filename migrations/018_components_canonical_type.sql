-- Migration 018: add canonical_type to components.
--
-- M7.0.b Step 2 (slot derivation) clusters by canonical_type, not
-- by category. Three catalog types sit in the `actions` category
-- (button, icon_button, button_group, fab, eyedropper, toolbar) and
-- have distinct slot vocabularies, so slot-derivation needs the
-- finer-grained type for the FK filter.
--
-- Backfilled by `scripts/m7_backfill_components.py`. Nullable because
-- remote-library and orphan CKR entries have no instances to vote
-- a canonical_type from.
--
-- Run: sqlite3 your.declarative.db < migrations/018_components_canonical_type.sql

ALTER TABLE components ADD COLUMN canonical_type TEXT;
