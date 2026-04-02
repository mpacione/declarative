-- Migration 006: Extraction Completeness (Phase -1)
-- Adds 31 missing columns to nodes table for complete layout/positioning/visual data.
-- 24 columns exist in schema.sql but were missing from older Dank DB.
-- 7 columns are new (layoutPositioning + Grid properties).
--
-- Safe to run multiple times — ALTER TABLE ADD COLUMN is idempotent with IF NOT EXISTS-style error handling.
-- Run on existing DBs before re-extraction.

-- Child positioning within auto-layout parent
ALTER TABLE nodes ADD COLUMN layout_positioning TEXT;

-- Grid layout (layoutMode = 'GRID')
ALTER TABLE nodes ADD COLUMN grid_row_count INTEGER;
ALTER TABLE nodes ADD COLUMN grid_column_count INTEGER;
ALTER TABLE nodes ADD COLUMN grid_row_gap REAL;
ALTER TABLE nodes ADD COLUMN grid_column_gap REAL;
ALTER TABLE nodes ADD COLUMN grid_row_sizes TEXT;
ALTER TABLE nodes ADD COLUMN grid_column_sizes TEXT;

-- Auto-layout extensions (existed in schema.sql, missing from older DBs)
ALTER TABLE nodes ADD COLUMN layout_wrap TEXT;
ALTER TABLE nodes ADD COLUMN min_width REAL;
ALTER TABLE nodes ADD COLUMN max_width REAL;
ALTER TABLE nodes ADD COLUMN min_height REAL;
ALTER TABLE nodes ADD COLUMN max_height REAL;

-- Stroke detail (existed in schema.sql, missing from older DBs)
ALTER TABLE nodes ADD COLUMN stroke_weight REAL;
ALTER TABLE nodes ADD COLUMN stroke_top_weight REAL;
ALTER TABLE nodes ADD COLUMN stroke_right_weight REAL;
ALTER TABLE nodes ADD COLUMN stroke_bottom_weight REAL;
ALTER TABLE nodes ADD COLUMN stroke_left_weight REAL;
ALTER TABLE nodes ADD COLUMN stroke_align TEXT;
ALTER TABLE nodes ADD COLUMN stroke_cap TEXT;
ALTER TABLE nodes ADD COLUMN stroke_join TEXT;
ALTER TABLE nodes ADD COLUMN dash_pattern TEXT;

-- Transform (existed in schema.sql, missing from older DBs)
ALTER TABLE nodes ADD COLUMN rotation REAL;
ALTER TABLE nodes ADD COLUMN clips_content INTEGER;

-- Constraints (existed in schema.sql, missing from older DBs)
ALTER TABLE nodes ADD COLUMN constraint_h TEXT;
ALTER TABLE nodes ADD COLUMN constraint_v TEXT;

-- Typography extensions (existed in schema.sql, missing from older DBs)
ALTER TABLE nodes ADD COLUMN font_style TEXT;
ALTER TABLE nodes ADD COLUMN paragraph_spacing REAL;
ALTER TABLE nodes ADD COLUMN text_align_v TEXT;
ALTER TABLE nodes ADD COLUMN text_decoration TEXT;
ALTER TABLE nodes ADD COLUMN text_case TEXT;

-- Component reference (existed in schema.sql, missing from older DBs)
ALTER TABLE nodes ADD COLUMN component_key TEXT;

-- Screen type classification
ALTER TABLE screens ADD COLUMN screen_type TEXT;
