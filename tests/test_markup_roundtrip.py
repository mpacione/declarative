"""Priority 0 investigation probe — dd-markup round-trip parity.

Proves whether the `dd` markup dialect can losslessly serialize and re-parse
the existing dict IR. Each passing test documents one grammar feature that
round-trips cleanly. Each failing test is a grammar gap.

THROWAWAY PROTOTYPE — this file lives on branch `v0.3-dd-markup-probe` and
reverts if parity drops below 204/204. Decision record lands in
`docs/decisions/v0.3-canonical-ir.md`.
"""

from __future__ import annotations

import pytest

from dd.markup import parse_dd, serialize_ir


class TestEmptySpec:
    """Phase 0 — can we round-trip a minimal-shape IR (no elements)?"""

    def test_empty_spec_roundtrips(self) -> None:
        spec = {
            "version": "1.0",
            "root": "",
            "elements": {},
            "tokens": {},
            "_node_id_map": {},
        }

        dd_text = serialize_ir(spec)
        parsed = parse_dd(dd_text)

        assert parsed == spec


class TestSingleElement:
    """Phase 1 — one element, primitive-only."""

    def test_single_screen_element(self) -> None:
        spec = {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {
                    "type": "screen",
                    "children": [],
                },
            },
            "tokens": {},
            "_node_id_map": {},
        }

        dd_text = serialize_ir(spec)
        parsed = parse_dd(dd_text)

        assert parsed == spec

    def test_element_with_original_name(self) -> None:
        spec = {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {
                    "type": "screen",
                    "children": [],
                    "_original_name": "Signup Form",
                },
            },
            "tokens": {},
            "_node_id_map": {},
        }

        dd_text = serialize_ir(spec)
        parsed = parse_dd(dd_text)

        assert parsed == spec


class TestNestedElements:
    """Phase 2 — parent/child relationships."""

    def test_parent_with_one_child(self) -> None:
        spec = {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {"type": "screen", "children": ["frame-1"]},
                "frame-1": {"type": "frame", "children": []},
            },
            "tokens": {},
            "_node_id_map": {"screen-1": 100, "frame-1": 101},
        }

        dd_text = serialize_ir(spec)
        parsed = parse_dd(dd_text)

        assert parsed == spec


class TestAxisFields:
    """Phase 3 — layout/visual/style nested dicts on an element."""

    def test_element_with_layout_primitives(self) -> None:
        spec = {
            "version": "1.0",
            "root": "frame-1",
            "elements": {
                "frame-1": {
                    "type": "frame",
                    "children": [],
                    "layout": {
                        "direction": "vertical",
                        "gap": 16,
                        "position": {"x": 0, "y": 100},
                    },
                },
            },
            "tokens": {},
            "_node_id_map": {},
        }

        dd_text = serialize_ir(spec)
        parsed = parse_dd(dd_text)

        assert parsed == spec


@pytest.mark.integration
class TestRealScreen:
    """Phase 4 — real screen from the 204 corpus.

    This is the proof gate for Priority 0: can we serialize and re-parse
    the smallest real IR? Marked integration so it's skippable on quick runs.
    """

    def test_screen_183_roundtrips(self) -> None:
        import sqlite3

        from dd.ir import generate_ir

        conn = sqlite3.connect("Dank-EXP-02.declarative.db")
        result = generate_ir(conn, 183)
        spec = result["spec"]

        dd_text = serialize_ir(spec)
        parsed = parse_dd(dd_text)

        assert parsed == spec, (
            f"Round-trip lost fidelity on screen 183 "
            f"({len(spec['elements'])} elements)"
        )
