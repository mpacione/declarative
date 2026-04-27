"""Phase E #5 fix — CKR figma_node_id coverage check.

Phase E audit found CKR.figma_node_id at 1/179 on Nouns
(downstream-harmless but quietly under-populates sticker-sheet
tagging + variant derivation). Audit priority #6: "Document and
defer."

Codex 2026-04-26 (gpt-5.5 high reasoning) advised: defer the
extraction-pipeline fix; add a non-failing audit warning that
surfaces the gap. This test pins the warning's threshold logic:
- 0 rows: skip (no CKR yet)
- 0 missing: skip (clean state)
- >= 50% missing: WARNING
- 1-49% missing: INFO

Without this check the gap is invisible to dd validate.
"""

from __future__ import annotations

import sqlite3

from dd import db as dd_db
from dd.validate import check_ckr_figma_node_id_coverage


def _make_db_with_ckr(rows: list[tuple[str, str | None, str]]) -> sqlite3.Connection:
    """Build a fresh in-memory DB and seed CKR with the given rows.
    Each row is (component_key, figma_node_id, name).

    CKR is created on-demand (not in schema.sql); mirror the shape
    from dd/templates.py:80-86.
    """
    conn = dd_db.init_db(":memory:")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS component_key_registry ("
        "component_key TEXT PRIMARY KEY, "
        "figma_node_id TEXT, "
        "name TEXT NOT NULL, "
        "instance_count INTEGER)"
    )
    for ck, fid, name in rows:
        conn.execute(
            "INSERT INTO component_key_registry "
            "(component_key, figma_node_id, name, instance_count) "
            "VALUES (?, ?, ?, 1)",
            (ck, fid, name),
        )
    conn.commit()
    return conn


class TestCkrCoverageThresholds:
    """The threshold logic Codex specified."""

    def test_empty_ckr_yields_no_issue(self):
        conn = _make_db_with_ckr([])
        issues = check_ckr_figma_node_id_coverage(conn, file_id=1)
        assert issues == [], (
            "Empty CKR → no issue (the user hasn't built a registry yet)."
        )

    def test_fully_populated_yields_no_issue(self):
        conn = _make_db_with_ckr([
            ("ck1", "1:1", "Comp1"),
            ("ck2", "1:2", "Comp2"),
            ("ck3", "1:3", "Comp3"),
        ])
        issues = check_ckr_figma_node_id_coverage(conn, file_id=1)
        assert issues == [], (
            "Fully populated CKR (3/3 figma_node_id) → no issue."
        )

    def test_partial_coverage_below_50pct_is_info(self):
        # 4 rows, 3 populated, 1 missing → 25% missing → INFO
        conn = _make_db_with_ckr([
            ("ck1", "1:1", "Comp1"),
            ("ck2", "1:2", "Comp2"),
            ("ck3", "1:3", "Comp3"),
            ("ck4", None, "Comp4"),
        ])
        issues = check_ckr_figma_node_id_coverage(conn, file_id=1)
        assert len(issues) == 1
        assert issues[0]["severity"] == "info"
        assert "1 missing" in issues[0]["message"]
        assert "25.0%" in issues[0]["message"]

    def test_partial_coverage_above_50pct_is_warning(self):
        # 4 rows, 1 populated, 3 missing → 75% missing → WARNING
        conn = _make_db_with_ckr([
            ("ck1", "1:1", "Comp1"),
            ("ck2", None, "Comp2"),
            ("ck3", None, "Comp3"),
            ("ck4", None, "Comp4"),
        ])
        issues = check_ckr_figma_node_id_coverage(conn, file_id=1)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "75.0%" in issues[0]["message"]

    def test_all_missing_is_warning(self):
        # 3 rows, 0 populated → 100% missing → WARNING
        conn = _make_db_with_ckr([
            ("ck1", None, "Comp1"),
            ("ck2", None, "Comp2"),
            ("ck3", None, "Comp3"),
        ])
        issues = check_ckr_figma_node_id_coverage(conn, file_id=1)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "100.0%" in issues[0]["message"]

    def test_exactly_50pct_is_warning(self):
        """Boundary: exactly 50% missing should be WARNING (>= 50)."""
        conn = _make_db_with_ckr([
            ("ck1", "1:1", "Comp1"),
            ("ck2", None, "Comp2"),
        ])
        issues = check_ckr_figma_node_id_coverage(conn, file_id=1)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"


class TestCkrCheckGracefulOnMissingTable:
    """Defensive: if `component_key_registry` table doesn't exist
    (older schemas), the check returns no issues."""

    def test_no_table_yields_no_issue(self):
        conn = dd_db.init_db(":memory:")
        # Drop the CKR table to simulate older schema
        conn.execute("DROP TABLE IF EXISTS component_key_registry")
        conn.commit()
        issues = check_ckr_figma_node_id_coverage(conn, file_id=1)
        assert issues == [], (
            "Missing CKR table → no issue (graceful no-op, not an error)."
        )


class TestCkrCheckIntegratesIntoRunValidation:
    """The check runs as part of `dd validate` (run_validation)
    and surfaces in the export_validations table."""

    def test_check_appears_in_run_validation(self):
        from dd.validate import run_validation
        conn = _make_db_with_ckr([
            ("ck1", None, "Comp1"),
            ("ck2", None, "Comp2"),
            ("ck3", None, "Comp3"),
        ])
        # Add a file row so file_id=1 is valid for other checks
        conn.execute(
            "INSERT INTO files (id, file_key, name) "
            "VALUES (1, 'test', 'test.fig')"
        )
        conn.commit()
        result = run_validation(conn, file_id=1)
        ckr_issues = [
            i for i in result["issues"]
            if i["check_name"] == "ckr_figma_node_id_coverage"
        ]
        assert len(ckr_issues) == 1, (
            "run_validation must include the CKR coverage check. "
            "Pre-fix the gap was invisible to `dd validate`."
        )
        assert ckr_issues[0]["severity"] == "warning"
