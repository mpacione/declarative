-- Migration 023: design_sessions / variants / move_log tables for
-- Stage 3 of docs/plan-authoring-loop.md.
--
-- Per Codex+Sonnet 2026-04-23 unanimous picks: Option 3 (Hybrid) +
-- B (keep move_log). Three tables:
--
-- - ``design_sessions`` — one row per ``dd design --brief "..."``
--   call. ULID PK so Stage 4 can share variant URLs externally
--   without exposing autoincrement counts.
--
-- - ``variants`` — branchable tree of design states. parent_id is
--   nullable + self-references variants(id), so LATERAL/branch
--   semantics fall out of resume-from-non-leaf for free. Snapshot
--   stored as gzipped TEXT in ``markup_blob`` per Option 3 (no
--   sibling session_blobs table; the Codex consultation noted
--   content-addressed dedup isn't justified at 10 iters/session).
--
-- - ``move_log`` — chronological NAME / DRILL / CLIMB / EDIT
--   entries. Keeps NAME (description payload) + CLIMB
--   (focus_goal payload) which variants can't represent — both
--   Codex and Sonnet (2026-04-23) flagged dropping this table as
--   silently truncating the Stage-2-promised reasoning trail.
--
-- Run: sqlite3 your.declarative.db < migrations/023_design_sessions.sql
--
-- Idempotent: tables use IF NOT EXISTS guards. Re-applying is safe.

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS design_sessions (
    id          TEXT PRIMARY KEY,
    brief       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open' CHECK(status IN (
        'open', 'closed', 'archived'
    )),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_design_sessions_status
    ON design_sessions(status);
CREATE INDEX IF NOT EXISTS idx_design_sessions_created_at
    ON design_sessions(created_at);

CREATE TABLE IF NOT EXISTS variants (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES design_sessions(id),
    parent_id    TEXT REFERENCES variants(id),
    primitive    TEXT,                  -- NAME / DRILL / CLIMB / EDIT / LATERAL
    edit_script  TEXT,                  -- the edit-grammar source that birthed this variant
    markup_blob  TEXT,                  -- gzipped + base64 L3 markup snapshot (per Option 3)
    scores       TEXT,                  -- nullable JSON; populated by `dd design score` (deferred per A2)
    status       TEXT DEFAULT 'open' CHECK(status IN (
        'open', 'pruned', 'promoted', 'frontier'
    )),
    notes        TEXT,                  -- agent rationale (from ProposeEditsResult.rationale)
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_variants_session_id
    ON variants(session_id);
CREATE INDEX IF NOT EXISTS idx_variants_parent_id
    ON variants(parent_id);
CREATE INDEX IF NOT EXISTS idx_variants_status
    ON variants(status);

CREATE TABLE IF NOT EXISTS move_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES design_sessions(id),
    variant_id   TEXT REFERENCES variants(id),
    primitive    TEXT NOT NULL,
    payload      TEXT,                  -- JSON of the full MoveLogEntry.to_dict()
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_move_log_session_id
    ON move_log(session_id);
CREATE INDEX IF NOT EXISTS idx_move_log_variant_id
    ON move_log(variant_id);
CREATE INDEX IF NOT EXISTS idx_move_log_created_at
    ON move_log(created_at);

COMMIT;
