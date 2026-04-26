"""Phase E #2 fix — CKR.figma_node_id populated from
nodes.component_figma_id (instance-resolved master id).

Pre-fix `dd/templates.py::build_component_key_registry` resolved
CKR.figma_node_id by joining instance names against
`nodes WHERE node_type='COMPONENT'`. On Nouns the Components page
isn't walked by `extract_top_level_frames` (pages[0] only), so 0
COMPONENT nodes existed and 178/179 CKR rows had figma_node_id
NULL. Downstream consumers (variants.py, sticker_sheet.py, the
new project_tokens overlay) under-populated.

Codex 2026-04-26 (gpt-5.5 high reasoning) review:
"the cheapest correct fix: the current code already discovers the
authoritative mapping at extraction time via getMainComponentAsync()'s
main.id... use key lookup as fallback, not primary path."

Phase E #2 implementation:
1. Migration 024 adds `nodes.component_figma_id TEXT` column.
2. dd/extract_screens.py:_STRUCTURAL_INSERT_COLUMNS includes the
   new column so the INSERT path forwards it (fixes the
   feedback_extract_whitelist_drift.md class).
3. dd/templates.py:build_component_key_registry now PRIMARILY
   reads nodes.component_figma_id; legacy name-based fallbacks
   stay for backwards compat.

These tests pin the post-fix state.
"""

from __future__ import annotations

import sqlite3

from dd import db as dd_db
from dd.templates import build_component_key_registry


def _seed_instance(
    conn: sqlite3.Connection,
    *,
    figma_node_id: str,
    name: str,
    component_key: str,
    component_figma_id: str | None,
) -> int:
    """Insert one INSTANCE node and return its id."""
    cur = conn.execute(
        "INSERT INTO nodes "
        "(screen_id, figma_node_id, name, node_type, "
        "component_key, component_figma_id) "
        "VALUES (1, ?, ?, 'INSTANCE', ?, ?)",
        (figma_node_id, name, component_key, component_figma_id),
    )
    return cur.lastrowid


def _make_db_with_instances(rows: list[dict]) -> sqlite3.Connection:
    """Build a fresh DB with N INSTANCE nodes per row spec.

    Each row is a dict with: figma_node_id, name, component_key,
    component_figma_id (optional, None to simulate older DBs).
    """
    conn = dd_db.init_db(":memory:")
    conn.execute(
        "INSERT INTO files (id, file_key, name) "
        "VALUES (1, 'test', 'test.fig')"
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, "
        "width, height) "
        "VALUES (1, 1, '1:1', 'Screen 1', 375, 812)"
    )
    for row in rows:
        _seed_instance(
            conn,
            figma_node_id=row["figma_node_id"],
            name=row["name"],
            component_key=row["component_key"],
            component_figma_id=row.get("component_figma_id"),
        )
    conn.commit()
    return conn


class TestNodesHasComponentFigmaIdColumn:
    """Schema migration 024 lands the column."""

    def test_column_exists_in_fresh_db(self):
        conn = dd_db.init_db(":memory:")
        cursor = conn.execute("PRAGMA table_info(nodes)")
        cols = {row[1] for row in cursor}
        assert "component_figma_id" in cols, (
            "Phase E #2: schema.sql should include "
            "nodes.component_figma_id (lands the migration in fresh DBs)."
        )


class TestPrimaryPathInstanceResolved:
    """The headline fix — CKR.figma_node_id resolves from
    nodes.component_figma_id when present (no name-matching
    needed)."""

    def test_single_instance_populates_ckr_figma_node_id(self):
        conn = _make_db_with_instances([
            {
                "figma_node_id": "10:1",
                "name": "Button/Primary",
                "component_key": "abc123",
                "component_figma_id": "999:1",  # the master's node id
            },
        ])
        build_component_key_registry(conn)
        row = conn.execute(
            "SELECT component_key, figma_node_id, name "
            "FROM component_key_registry WHERE component_key = ?",
            ("abc123",),
        ).fetchone()
        assert row is not None
        assert row[1] == "999:1", (
            "Phase E #2: CKR.figma_node_id should be populated from "
            "nodes.component_figma_id (the instance-resolved master id), "
            f"not via name-matching. Got: {row[1]}"
        )

    def test_primary_path_works_without_component_node(self):
        """No COMPONENT row in nodes; legacy fallbacks would have left
        figma_node_id NULL. Post-fix the primary path picks up the
        master id from the INSTANCE's component_figma_id."""
        conn = _make_db_with_instances([
            {
                "figma_node_id": "10:1",
                "name": "Card/Default",
                "component_key": "key_card",
                "component_figma_id": "999:42",
            },
        ])
        # Verify there's NO COMPONENT row (the legacy fallback would
        # have nothing to find).
        cursor = conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE node_type = 'COMPONENT'"
        )
        assert cursor.fetchone()[0] == 0
        build_component_key_registry(conn)
        row = conn.execute(
            "SELECT figma_node_id FROM component_key_registry "
            "WHERE component_key = ?", ("key_card",),
        ).fetchone()
        assert row[0] == "999:42", (
            "Phase E #2 headline: CKR populated even with 0 COMPONENT "
            "nodes in nodes table. Pre-fix this was the Nouns gap."
        )

    def test_multiple_instances_same_key_dedupe_to_one_master(self):
        """When N INSTANCE rows share a component_key, we get ONE
        CKR row pointing at the same master figma_node_id."""
        conn = _make_db_with_instances([
            {
                "figma_node_id": "10:1",
                "name": "Button/Primary",
                "component_key": "abc",
                "component_figma_id": "999:1",
            },
            {
                "figma_node_id": "10:2",
                "name": "Button/Primary",
                "component_key": "abc",
                "component_figma_id": "999:1",
            },
            {
                "figma_node_id": "10:3",
                "name": "Button/Primary",
                "component_key": "abc",
                "component_figma_id": "999:1",
            },
        ])
        build_component_key_registry(conn)
        # Exactly 1 CKR row
        n_rows = conn.execute(
            "SELECT COUNT(*) FROM component_key_registry "
            "WHERE component_key = ?", ("abc",),
        ).fetchone()[0]
        assert n_rows == 1
        row = conn.execute(
            "SELECT figma_node_id, instance_count "
            "FROM component_key_registry WHERE component_key = ?",
            ("abc",),
        ).fetchone()
        assert row[0] == "999:1"
        assert row[1] == 3, (
            "instance_count should still aggregate (3 INSTANCE rows)."
        )


class TestLegacyFallback:
    """When component_figma_id is NULL (older DBs / pre-migration data),
    the legacy name-based fallback still works."""

    def test_falls_back_to_name_match_on_null_master_fid(self):
        """component_figma_id is NULL on the INSTANCE; fallback to
        COMPONENT-name match should still populate CKR."""
        conn = _make_db_with_instances([
            {
                "figma_node_id": "10:1",
                "name": "Button/Primary",
                "component_key": "old_ck",
                "component_figma_id": None,  # legacy / pre-migration
            },
        ])
        # Add a COMPONENT row matching the instance name (the legacy
        # fallback path).
        conn.execute(
            "INSERT INTO nodes "
            "(screen_id, figma_node_id, name, node_type) "
            "VALUES (1, '88:1', 'Button/Primary', 'COMPONENT')"
        )
        conn.commit()
        build_component_key_registry(conn)
        row = conn.execute(
            "SELECT figma_node_id FROM component_key_registry "
            "WHERE component_key = ?", ("old_ck",),
        ).fetchone()
        assert row[0] == "88:1", (
            "Legacy fallback (name match against COMPONENT nodes) "
            "should still work for older DBs without "
            "component_figma_id populated."
        )

    def test_no_master_no_name_match_yields_null(self):
        """Defensive: when neither the new path nor the legacy path
        finds a master, CKR.figma_node_id is NULL (the gap that
        Phase E #5's audit warning surfaces)."""
        conn = _make_db_with_instances([
            {
                "figma_node_id": "10:1",
                "name": "Unknown/Comp",
                "component_key": "lonely",
                "component_figma_id": None,
            },
        ])
        build_component_key_registry(conn)
        row = conn.execute(
            "SELECT figma_node_id FROM component_key_registry "
            "WHERE component_key = ?", ("lonely",),
        ).fetchone()
        assert row[0] is None


class TestNewPathBeatsLegacy:
    """When BOTH paths could resolve, the new path (component_figma_id)
    wins. This guards against silent regressions if someone added a
    COMPONENT row matching by name and assumed the legacy path would
    fire."""

    def test_component_figma_id_preferred_over_name_match(self):
        conn = _make_db_with_instances([
            {
                "figma_node_id": "10:1",
                "name": "Button/Primary",
                "component_key": "ck",
                "component_figma_id": "999:NEW",  # the new path's answer
            },
        ])
        # Also add a name-matching COMPONENT row (legacy path's answer
        # would be 88:LEGACY).
        conn.execute(
            "INSERT INTO nodes "
            "(screen_id, figma_node_id, name, node_type) "
            "VALUES (1, '88:LEGACY', 'Button/Primary', 'COMPONENT')"
        )
        conn.commit()
        build_component_key_registry(conn)
        row = conn.execute(
            "SELECT figma_node_id FROM component_key_registry "
            "WHERE component_key = ?", ("ck",),
        ).fetchone()
        assert row[0] == "999:NEW", (
            "Phase E #2: the new instance-resolved path should win "
            "over the legacy name-match path. Got the legacy answer "
            "instead — primary path is broken."
        )


class TestExtractScreensIncludesNewColumn:
    """The INSERT-side whitelist forwards component_figma_id (so
    extraction populates the column going forward)."""

    def test_structural_insert_columns_includes_component_figma_id(self):
        from dd.extract_screens import _STRUCTURAL_INSERT_COLUMNS
        assert "component_figma_id" in _STRUCTURAL_INSERT_COLUMNS, (
            "Phase E #2: _STRUCTURAL_INSERT_COLUMNS must include "
            "component_figma_id so insert_nodes forwards it. Without "
            "this the plugin's getMainComponentAsync().id capture is "
            "silently dropped at INSERT time."
        )

    def test_insert_node_columns_includes_component_figma_id(self):
        from dd.extract_screens import INSERT_NODE_COLUMNS
        assert "component_figma_id" in INSERT_NODE_COLUMNS
