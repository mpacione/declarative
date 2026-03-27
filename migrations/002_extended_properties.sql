-- Migration 002: Extended Node Properties
-- Adds stroke, transform, constraint, typography, and layout columns to nodes.
-- Adds instance_overrides table for component property tracking.
--
-- Run against production DB:
--   sqlite3 Dank-EXP-02.declarative.db < migrations/002_extended_properties.sql
--
-- Safe to run multiple times (ADD COLUMN is idempotent in SQLite if column already exists — will error, but no data loss).

-- Stroke properties
ALTER TABLE nodes ADD COLUMN stroke_weight REAL;
ALTER TABLE nodes ADD COLUMN stroke_top_weight REAL;
ALTER TABLE nodes ADD COLUMN stroke_right_weight REAL;
ALTER TABLE nodes ADD COLUMN stroke_bottom_weight REAL;
ALTER TABLE nodes ADD COLUMN stroke_left_weight REAL;
ALTER TABLE nodes ADD COLUMN stroke_align TEXT;
ALTER TABLE nodes ADD COLUMN stroke_cap TEXT;
ALTER TABLE nodes ADD COLUMN stroke_join TEXT;
ALTER TABLE nodes ADD COLUMN dash_pattern TEXT;

-- Transform
ALTER TABLE nodes ADD COLUMN rotation REAL;
ALTER TABLE nodes ADD COLUMN clips_content INTEGER;

-- Constraints
ALTER TABLE nodes ADD COLUMN constraint_h TEXT;
ALTER TABLE nodes ADD COLUMN constraint_v TEXT;

-- Auto-layout extensions
ALTER TABLE nodes ADD COLUMN layout_wrap TEXT;
ALTER TABLE nodes ADD COLUMN min_width REAL;
ALTER TABLE nodes ADD COLUMN max_width REAL;
ALTER TABLE nodes ADD COLUMN min_height REAL;
ALTER TABLE nodes ADD COLUMN max_height REAL;

-- Typography extensions
ALTER TABLE nodes ADD COLUMN font_style TEXT;
ALTER TABLE nodes ADD COLUMN paragraph_spacing REAL;
ALTER TABLE nodes ADD COLUMN text_align_v TEXT;
ALTER TABLE nodes ADD COLUMN text_decoration TEXT;
ALTER TABLE nodes ADD COLUMN text_case TEXT;

-- Component key for instantiation
ALTER TABLE nodes ADD COLUMN component_key TEXT;

-- Instance overrides table
CREATE TABLE IF NOT EXISTS instance_overrides (
    id              INTEGER PRIMARY KEY,
    node_id         INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    property_type   TEXT NOT NULL,
    property_name   TEXT NOT NULL,
    override_value  TEXT,
    UNIQUE(node_id, property_name)
);
