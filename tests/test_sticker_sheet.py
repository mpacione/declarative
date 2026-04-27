"""Tests for ``dd.sticker_sheet`` — M7.0.f authoritative-source tagging.

Rule: a component is sticker-sheet authoritative when at least one
of its INSTANCE uses appears on a screen whose ``screen_type`` is
``design_canvas`` (or another caller-supplied set). The tagging is
idempotent; the plan lets the sticker sheet override M7.0.b/c
heuristics, but the reconciliation (e.g. which slots win) is
deferred — this shipment just persists the tag.
"""

from __future__ import annotations

import sqlite3

import pytest

from dd.sticker_sheet import (
    StickerSheetSummary,
    find_sticker_sheet_screens,
    tag_authoritative_components,
)


def _schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE screens (
            id INTEGER PRIMARY KEY, file_id TEXT, name TEXT,
            screen_type TEXT
        );
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY, screen_id INTEGER,
            parent_id INTEGER, name TEXT, node_type TEXT,
            component_key TEXT
        );
        CREATE TABLE components (
            id INTEGER PRIMARY KEY, component_key TEXT UNIQUE,
            name TEXT, category TEXT, canonical_type TEXT,
            authoritative_source TEXT
        );
        """
    )


def _seed_dank_mini(conn: sqlite3.Connection) -> None:
    """Two app screens + one design-canvas screen. The component
    `button/primary` has instances on ALL three; the component
    `card/hero` has instances only on the app screens.
    """
    conn.executescript(
        """
        INSERT INTO screens (id, file_id, name, screen_type) VALUES
            (1, 'f', 'Login', 'app_screen'),
            (2, 'f', 'Settings', 'app_screen'),
            (3, 'f', 'Frame 429', 'design_canvas');
        INSERT INTO components
            (id, component_key, name, category, canonical_type)
        VALUES
            (10, 'ck-btn', 'button/primary', 'actions', 'button'),
            (11, 'ck-card', 'card/hero', 'containers', 'card');
        INSERT INTO nodes
            (id, screen_id, parent_id, name, node_type, component_key)
        VALUES
            -- app-screen uses
            (100, 1, NULL, 'b-1', 'INSTANCE', 'ck-btn'),
            (101, 2, NULL, 'b-2', 'INSTANCE', 'ck-btn'),
            (102, 1, NULL, 'c-1', 'INSTANCE', 'ck-card'),
            (103, 2, NULL, 'c-2', 'INSTANCE', 'ck-card'),
            -- sticker-sheet use (of button only)
            (200, 3, NULL, 'b-sticker', 'INSTANCE', 'ck-btn');
        """
    )
    conn.commit()


class TestFindStickerSheetScreens:
    def test_default_uses_design_canvas_screen_type(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema(conn); _seed_dank_mini(conn)
        screens = find_sticker_sheet_screens(conn)
        assert [s["id"] for s in screens] == [3]

    def test_custom_screen_types_accepted(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema(conn); _seed_dank_mini(conn)
        # Override: treat both app_screen AND design_canvas as
        # sticker sheets (nonsensical but tests that the kwarg
        # works).
        screens = find_sticker_sheet_screens(
            conn, screen_types=["app_screen", "design_canvas"],
        )
        assert sorted([s["id"] for s in screens]) == [1, 2, 3]

    def test_returns_empty_when_no_matches(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema(conn); _seed_dank_mini(conn)
        screens = find_sticker_sheet_screens(
            conn, screen_types=["design_system"],
        )
        assert screens == []


class TestTagAuthoritativeComponents:
    def test_tags_components_with_instances_on_sticker_sheets(
        self,
    ) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema(conn); _seed_dank_mini(conn)

        summary = tag_authoritative_components(conn)
        assert isinstance(summary, StickerSheetSummary)
        assert summary.sticker_sheet_screens == 1
        # Only `ck-btn` has a sticker-sheet instance.
        row = conn.execute(
            "SELECT component_key, authoritative_source FROM components "
            "ORDER BY id"
        ).fetchall()
        mapped = {r["component_key"]: r["authoritative_source"] for r in row}
        assert mapped["ck-btn"] == "sticker_sheet"
        assert mapped["ck-card"] is None
        assert summary.tagged == 1

    def test_idempotent_second_run(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema(conn); _seed_dank_mini(conn)
        tag_authoritative_components(conn)
        summary2 = tag_authoritative_components(conn)
        # Re-tagging the same component is a no-op.
        assert summary2.tagged == 0
        assert summary2.already_tagged == 1

    def test_skips_components_not_in_registry(self) -> None:
        """A sticker-sheet instance whose component_key has no
        `components` row (remote-library or orphan) is skipped
        silently — can't tag what isn't there."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema(conn); _seed_dank_mini(conn)
        conn.execute(
            "INSERT INTO nodes (id, screen_id, parent_id, name, "
            "node_type, component_key) "
            "VALUES (999, 3, NULL, 'orphan', 'INSTANCE', 'ck-orphan')"
        )
        conn.commit()
        summary = tag_authoritative_components(conn)
        # Only ck-btn gets tagged; ck-orphan is skipped.
        assert summary.tagged == 1
        assert summary.unknown_component_keys == 1

    def test_no_sticker_sheet_is_a_clean_noop(self) -> None:
        """Per plan §5.1: 'Skipped silently on projects without a
        sticker sheet.'"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema(conn); _seed_dank_mini(conn)
        # Remove the design_canvas screen.
        conn.execute("DELETE FROM screens WHERE id = 3")
        conn.execute("DELETE FROM nodes WHERE screen_id = 3")
        conn.commit()
        summary = tag_authoritative_components(conn)
        assert summary.sticker_sheet_screens == 0
        assert summary.tagged == 0
