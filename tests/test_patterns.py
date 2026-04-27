"""Tests for ``dd.patterns`` — M7.0.e rule-of-three pattern extraction."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from dd.patterns import (
    PatternCandidate,
    PatternLabels,
    _STRUCTURAL_PARENT_TYPES,
    collect_subtree_shapes,
    find_repeated_patterns,
    label_pattern_with_llm,
    persist_pattern,
    run_pattern_extraction,
)


def _schema_and_seed(conn: sqlite3.Connection) -> None:
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
        CREATE TABLE screen_component_instances (
            id INTEGER PRIMARY KEY, screen_id INTEGER,
            node_id INTEGER, canonical_type TEXT,
            classification_source TEXT, consensus_method TEXT,
            compositional_role TEXT
        );
        CREATE TABLE patterns (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            recipe TEXT NOT NULL,
            description TEXT,
            source_screens TEXT,
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        );
        """
    )
    # 3 screens, each with the same toolbar shape
    # (drawer, button, button). Also one screen with a different
    # shape (toolbar → [icon]) that should not be picked up as a
    # pattern by itself.
    screens = [
        (1, "Login"), (2, "Settings"), (3, "Profile"), (4, "Feed"),
    ]
    for sid, name in screens:
        conn.execute(
            "INSERT INTO screens (id, file_id, name, screen_type) "
            "VALUES (?, ?, ?, 'app_screen')",
            (sid, "f1", name),
        )
    # For each of screens 1/2/3, build a toolbar with the same
    # canonical-type sequence.
    nid = 100
    sci_id = 200
    for sid in (1, 2, 3):
        # toolbar parent
        toolbar_nid = nid; nid += 1
        conn.execute(
            "INSERT INTO nodes (id, screen_id, parent_id, name, node_type) "
            "VALUES (?, ?, NULL, ?, 'FRAME')",
            (toolbar_nid, sid, "Toolbar"),
        )
        conn.execute(
            "INSERT INTO screen_component_instances "
            "(id, screen_id, node_id, canonical_type, "
            " classification_source, consensus_method) "
            "VALUES (?, ?, ?, 'toolbar', 'llm', 'unanimous')",
            (sci_id, sid, toolbar_nid),
        )
        sci_id += 1
        for idx, cty in enumerate(("drawer", "button", "button")):
            child_nid = nid; nid += 1
            conn.execute(
                "INSERT INTO nodes "
                "(id, screen_id, parent_id, name, node_type) "
                "VALUES (?, ?, ?, ?, 'INSTANCE')",
                (child_nid, sid, toolbar_nid, f"n-{cty}-{idx}"),
            )
            conn.execute(
                "INSERT INTO screen_component_instances "
                "(id, screen_id, node_id, canonical_type, "
                " classification_source, consensus_method) "
                "VALUES (?, ?, ?, ?, 'llm', 'unanimous')",
                (sci_id, sid, child_nid, cty),
            )
            sci_id += 1

    # Screen 4: a lone card with (container,) — only 1 screen, no
    # pattern should emerge.
    card_nid = nid; nid += 1
    conn.execute(
        "INSERT INTO nodes (id, screen_id, parent_id, name, node_type) "
        "VALUES (?, ?, NULL, 'Card', 'FRAME')",
        (card_nid, 4),
    )
    conn.execute(
        "INSERT INTO screen_component_instances "
        "(id, screen_id, node_id, canonical_type, "
        " classification_source, consensus_method) "
        "VALUES (?, ?, ?, 'card', 'llm', 'unanimous')",
        (sci_id, 4, card_nid),
    )
    sci_id += 1
    child_nid = nid; nid += 1
    conn.execute(
        "INSERT INTO nodes (id, screen_id, parent_id, name, node_type) "
        "VALUES (?, ?, ?, 'Content', 'FRAME')",
        (child_nid, 4, card_nid),
    )
    conn.execute(
        "INSERT INTO screen_component_instances "
        "(id, screen_id, node_id, canonical_type, "
        " classification_source, consensus_method) "
        "VALUES (?, ?, ?, 'container', 'llm', 'unanimous')",
        (sci_id, 4, child_nid),
    )
    conn.commit()


class TestCollectSubtreeShapes:
    def test_returns_parent_type_to_child_tuple_mapping(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema_and_seed(conn)
        shapes = collect_subtree_shapes(conn)
        # The toolbar/(drawer,button,button) shape appears on 3
        # screens. The card/(container,) shape appears on 1.
        assert ("toolbar", ("drawer", "button", "button")) in shapes
        assert len(shapes[("toolbar", ("drawer", "button", "button"))]) == 3

    def test_only_includes_structural_parent_types(self) -> None:
        """Frames / containers aren't structural parents — their
        repeating shapes are noise. Only parents with a load-bearing
        canonical_type are candidates."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema_and_seed(conn)
        shapes = collect_subtree_shapes(conn)
        for parent_type, _ in shapes:
            assert parent_type in _STRUCTURAL_PARENT_TYPES


class TestFindRepeatedPatterns:
    def test_respects_min_screens(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema_and_seed(conn)
        shapes = collect_subtree_shapes(conn)
        patterns = find_repeated_patterns(shapes, min_screens=3)
        # Only the (toolbar, (drawer, button, button)) shape should
        # qualify under rule-of-three.
        assert len(patterns) == 1
        p = patterns[0]
        assert isinstance(p, PatternCandidate)
        assert p.parent_type == "toolbar"
        assert p.child_types == ("drawer", "button", "button")
        assert set(p.screen_ids) == {1, 2, 3}

    def test_stricter_threshold_drops_all(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema_and_seed(conn)
        shapes = collect_subtree_shapes(conn)
        assert find_repeated_patterns(shapes, min_screens=4) == []


class TestLabelPatternWithLLM:
    def test_extracts_name_category_description(self) -> None:
        client = MagicMock()
        tool_block = MagicMock(type="tool_use")
        tool_block.name = "emit_pattern_label"
        tool_block.input = {
            "name": "toolbar/drawer-and-two-buttons",
            "category": "nav",
            "description": (
                "A typical app-bar pattern: a menu drawer followed "
                "by two action buttons, used on 3 screens."
            ),
        }
        client.messages.create.return_value = MagicMock(
            content=[tool_block]
        )

        candidate = PatternCandidate(
            parent_type="toolbar",
            child_types=("drawer", "button", "button"),
            screen_ids=[1, 2, 3],
        )
        labels = label_pattern_with_llm(client, candidate)
        assert isinstance(labels, PatternLabels)
        assert labels.name == "toolbar/drawer-and-two-buttons"
        assert labels.category == "nav"
        assert "drawer" in labels.description

    def test_no_tool_call_returns_none(self) -> None:
        client = MagicMock()
        client.messages.create.return_value = MagicMock(content=[])
        candidate = PatternCandidate(
            parent_type="toolbar",
            child_types=("drawer", "button"),
            screen_ids=[1, 2, 3],
        )
        assert label_pattern_with_llm(client, candidate) is None


class TestPersistPattern:
    def test_writes_row_with_recipe_json(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema_and_seed(conn)
        candidate = PatternCandidate(
            parent_type="toolbar",
            child_types=("drawer", "button", "button"),
            screen_ids=[1, 2, 3],
        )
        labels = PatternLabels(
            name="toolbar/drawer-and-two-buttons",
            category="nav",
            description="App-bar w/ menu + 2 actions.",
        )
        persist_pattern(conn, candidate, labels)
        row = conn.execute(
            "SELECT name, category, recipe, description, "
            "source_screens FROM patterns"
        ).fetchone()
        assert row["name"] == "toolbar/drawer-and-two-buttons"
        assert row["category"] == "nav"
        recipe = json.loads(row["recipe"])
        assert recipe["parent_type"] == "toolbar"
        assert recipe["child_sequence"] == [
            "drawer", "button", "button",
        ]
        assert json.loads(row["source_screens"]) == [1, 2, 3]

    def test_duplicate_name_skipped(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema_and_seed(conn)
        candidate = PatternCandidate(
            parent_type="toolbar",
            child_types=("drawer", "button", "button"),
            screen_ids=[1, 2, 3],
        )
        labels = PatternLabels(
            name="toolbar/drawer-and-two-buttons",
            category="nav",
            description="x",
        )
        persist_pattern(conn, candidate, labels)
        # Second persist with same name must not raise; it should
        # be a silent no-op (idempotent).
        persist_pattern(conn, candidate, labels)
        count = conn.execute(
            "SELECT COUNT(*) FROM patterns"
        ).fetchone()[0]
        assert count == 1


class TestRunPatternExtraction:
    def test_end_to_end_persists_labeled_pattern(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema_and_seed(conn)

        client = MagicMock()
        tool_block = MagicMock(type="tool_use")
        tool_block.name = "emit_pattern_label"
        tool_block.input = {
            "name": "toolbar/drawer-and-two-buttons",
            "category": "nav",
            "description": "App-bar pattern.",
        }
        client.messages.create.return_value = MagicMock(
            content=[tool_block]
        )

        summary = run_pattern_extraction(
            conn, client=client, min_screens=3, dry_run=False,
        )
        assert summary.candidates == 1
        assert summary.persisted == 1
        row = conn.execute(
            "SELECT name, category FROM patterns"
        ).fetchone()
        assert row["name"] == "toolbar/drawer-and-two-buttons"
        assert row["category"] == "nav"

    def test_dry_run_persists_nothing(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _schema_and_seed(conn)
        summary = run_pattern_extraction(
            conn, client=None, min_screens=3, dry_run=True,
        )
        assert summary.candidates == 1
        assert summary.persisted == 0
        cnt = conn.execute(
            "SELECT COUNT(*) FROM patterns"
        ).fetchone()[0]
        assert cnt == 0
