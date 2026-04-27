-- Migration 020: add authoritative_source to components.
--
-- M7.0.f — sticker-sheet-authoritative tagging. Dank has two
-- dedicated canvases (Frame 429 / Frame 430, screen_type=
-- 'design_canvas') where each component is instantiated in its
-- canonical form. When a component's instances include at least
-- one on a design_canvas screen, we tag `authoritative_source =
-- 'sticker_sheet'` — M7.6 composition should prefer those
-- instances as donors over arbitrary in-context uses.
--
-- Nullable because most projects have no equivalent; on
-- Dank-like projects, tagging is a subset of the component set.
--
-- Run: sqlite3 your.declarative.db < migrations/020_components_authoritative_source.sql

ALTER TABLE components ADD COLUMN authoritative_source TEXT;
