"""Tests for dd.library_catalog — LLM tool-context serialiser.

Covers the filter knobs (canonical_types, file_id, include_slots),
the shape guarantees (comp_ref, slots in sort_order), and the edge
cases (empty filter, components with no slots, nullable fields).
"""

from __future__ import annotations

import sqlite3

import pytest

from dd.library_catalog import (
    serialize_library,
    serialize_library_json,
)


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE files (id INTEGER PRIMARY KEY, file_key TEXT);
        INSERT INTO files (id, file_key) VALUES (1, 'dank');

        CREATE TABLE components (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            figma_node_id TEXT NOT NULL,
            name TEXT,
            category TEXT,
            canonical_type TEXT,
            UNIQUE(file_id, figma_node_id)
        );

        CREATE TABLE component_slots (
            id INTEGER PRIMARY KEY,
            component_id INTEGER NOT NULL REFERENCES components(id),
            name TEXT NOT NULL,
            slot_type TEXT,
            is_required INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            description TEXT,
            UNIQUE(component_id, name)
        );
    """)
    return conn


def _seed_button(conn: sqlite3.Connection) -> int:
    """One button master + 3 standard slots."""
    conn.execute(
        "INSERT INTO components (id, file_id, figma_node_id, name, "
        " category, canonical_type) "
        "VALUES (10, 1, '1:1', 'button/small/solid', 'actions', 'button')"
    )
    for i, (name, stype, req, desc) in enumerate([
        ("leading_icon", "component", 0, "Optional leading icon"),
        ("label", "text", 1, "Button text label"),
        ("trailing_icon", "component", 0, "Optional trailing icon"),
    ]):
        conn.execute(
            "INSERT INTO component_slots (component_id, name, slot_type, "
            " is_required, sort_order, description) "
            "VALUES (10, ?, ?, ?, ?, ?)",
            (name, stype, req, i, desc),
        )
    return 10


def _seed_icon(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO components (id, file_id, figma_node_id, name, "
        " category, canonical_type) "
        "VALUES (20, 1, '2:2', 'icon/back', 'content_and_display', 'icon')"
    )
    return 20


class TestSerializeLibrary:
    def test_returns_all_components_by_default(self):
        conn = _fresh_db()
        _seed_button(conn)
        _seed_icon(conn)
        catalog = serialize_library(conn)
        assert catalog["total_components"] == 2
        names = {c["name"] for c in catalog["components"]}
        assert names == {"button/small/solid", "icon/back"}

    def test_filters_by_canonical_type(self):
        conn = _fresh_db()
        _seed_button(conn)
        _seed_icon(conn)
        catalog = serialize_library(conn, canonical_types=["button"])
        assert catalog["total_components"] == 1
        assert catalog["components"][0]["canonical_type"] == "button"

    def test_empty_canonical_types_list_returns_empty(self):
        """Explicit empty filter returns no components (useful guard
        for code that might compute types dynamically).
        """
        conn = _fresh_db()
        _seed_button(conn)
        catalog = serialize_library(conn, canonical_types=[])
        assert catalog == {"total_components": 0, "components": []}

    def test_filter_by_file_id(self):
        conn = _fresh_db()
        conn.execute(
            "INSERT INTO files (id, file_key) VALUES (2, 'other')"
        )
        _seed_button(conn)  # file_id=1
        conn.execute(
            "INSERT INTO components (file_id, figma_node_id, name, "
            " canonical_type) VALUES (2, '3:3', 'foreign', 'button')"
        )
        c1 = serialize_library(conn, file_id=1)
        c2 = serialize_library(conn, file_id=2)
        assert c1["total_components"] == 1
        assert c2["total_components"] == 1
        assert c1["components"][0]["name"] == "button/small/solid"
        assert c2["components"][0]["name"] == "foreign"

    def test_comp_ref_matches_l3_syntax(self):
        """``-> button/small/solid`` is the literal LLM must emit
        in a swap verb.
        """
        conn = _fresh_db()
        _seed_button(conn)
        catalog = serialize_library(conn)
        assert catalog["components"][0]["comp_ref"] == (
            "-> button/small/solid"
        )

    def test_slots_in_sort_order(self):
        conn = _fresh_db()
        _seed_button(conn)
        catalog = serialize_library(conn)
        slots = catalog["components"][0]["slots"]
        assert [s["name"] for s in slots] == [
            "leading_icon", "label", "trailing_icon",
        ]
        assert slots[1]["is_required"] is True
        assert slots[0]["is_required"] is False

    def test_include_slots_false_skips_slot_lookup(self):
        conn = _fresh_db()
        _seed_button(conn)
        catalog = serialize_library(conn, include_slots=False)
        assert "slots" not in catalog["components"][0]

    def test_excludes_null_canonical_type(self):
        """Orphan components (NULL canonical_type from Step 1 when
        no trusted instances) are filtered out — the LLM can't
        reason about them.
        """
        conn = _fresh_db()
        conn.execute(
            "INSERT INTO components (file_id, figma_node_id, name) "
            "VALUES (1, '9:9', 'orphan')"
        )
        _seed_button(conn)
        catalog = serialize_library(conn)
        assert catalog["total_components"] == 1
        assert catalog["components"][0]["name"] == "button/small/solid"

    def test_component_with_no_slots_serialises_empty_list(self):
        """Leaf types (icons) have no slots — the list is empty,
        not absent.
        """
        conn = _fresh_db()
        _seed_icon(conn)
        catalog = serialize_library(conn)
        assert catalog["components"][0]["slots"] == []

    def test_ordered_by_canonical_type_then_name(self):
        """Stable ordering lets the LLM reference the catalog by
        index if needed.
        """
        conn = _fresh_db()
        _seed_button(conn)
        _seed_icon(conn)
        # Add another button to check intra-type ordering.
        conn.execute(
            "INSERT INTO components (id, file_id, figma_node_id, name, "
            " canonical_type) "
            "VALUES (11, 1, '1:2', 'button/large/solid', 'button')"
        )
        names = [
            c["name"] for c in serialize_library(conn)["components"]
        ]
        # canonical_type ordering: button before icon; within button,
        # alphabetical.
        assert names == [
            "button/large/solid", "button/small/solid", "icon/back",
        ]


class TestSerializeLibraryJson:
    def test_returns_valid_json(self):
        import json as _j
        conn = _fresh_db()
        _seed_button(conn)
        s = serialize_library_json(conn)
        parsed = _j.loads(s)
        assert parsed["total_components"] == 1
        assert parsed["components"][0]["name"] == "button/small/solid"

    def test_forwards_filter_kwargs(self):
        import json as _j
        conn = _fresh_db()
        _seed_button(conn)
        _seed_icon(conn)
        s = serialize_library_json(conn, canonical_types=["icon"])
        parsed = _j.loads(s)
        assert parsed["total_components"] == 1
        assert parsed["components"][0]["canonical_type"] == "icon"
