-- Migration 001: Value Provenance & History
-- Adds source, sync_status, last_verified_at to token_values.
-- Adds token_value_history append-only table.
--
-- Run against production DB:
--   sqlite3 Dank-EXP-02.declarative.db < migrations/001_value_provenance.sql
--
-- Safe to run multiple times (uses IF NOT EXISTS / ADD COLUMN with defaults).

-- Add provenance columns to token_values
ALTER TABLE token_values ADD COLUMN source TEXT NOT NULL DEFAULT 'figma'
    CHECK(source IN ('figma', 'derived', 'manual', 'imported'));

ALTER TABLE token_values ADD COLUMN sync_status TEXT NOT NULL DEFAULT 'pending'
    CHECK(sync_status IN ('pending', 'synced', 'drifted', 'figma_only', 'code_only'));

ALTER TABLE token_values ADD COLUMN last_verified_at TEXT;

-- Classify existing rows: non-default-mode values were produced by modes.py
-- (dark mode OKLCH inversion, compact scaling, high-contrast).
-- Default-mode values stay 'figma'.
UPDATE token_values
SET source = 'derived'
WHERE mode_id NOT IN (SELECT id FROM token_modes WHERE is_default = 1);

-- Create append-only history table
CREATE TABLE IF NOT EXISTS token_value_history (
    id              INTEGER PRIMARY KEY,
    token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
    mode_id         INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
    old_resolved    TEXT,
    new_resolved    TEXT NOT NULL,
    changed_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    changed_by      TEXT NOT NULL,
    reason          TEXT
);

CREATE INDEX IF NOT EXISTS idx_tvh_token_mode ON token_value_history(token_id, mode_id);
CREATE INDEX IF NOT EXISTS idx_tvh_changed_at ON token_value_history(changed_at);
