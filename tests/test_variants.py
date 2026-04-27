"""Tests for M7.0.c variant family derivation.

Cover the pure path-parsing (parse_ckr_paths) and the end-to-end
derivation pipeline (derive_variants_from_ckr) with a stub LLM.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from dd.variants import (
    derive_variants_from_ckr,
    parse_ckr_paths,
)


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE files (id INTEGER PRIMARY KEY, file_key TEXT);
        INSERT INTO files (id, file_key) VALUES (1, 'dank');

        CREATE TABLE component_key_registry (
            component_key TEXT PRIMARY KEY,
            figma_node_id TEXT,
            name TEXT,
            instance_count INTEGER
        );

        CREATE TABLE components (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            figma_node_id TEXT NOT NULL,
            name TEXT,
            canonical_type TEXT,
            UNIQUE(file_id, figma_node_id)
        );

        CREATE TABLE component_variants (
            id INTEGER PRIMARY KEY,
            component_id INTEGER NOT NULL REFERENCES components(id),
            figma_node_id TEXT,
            name TEXT,
            properties TEXT,
            UNIQUE(component_id, name)
        );
    """)
    return conn


def _seed_ckr(conn: sqlite3.Connection, name: str, figma_id: str) -> None:
    conn.execute(
        "INSERT INTO component_key_registry "
        "(component_key, figma_node_id, name, instance_count) "
        "VALUES (?, ?, ?, 1)",
        (f"key_{figma_id}", figma_id, name),
    )


def _seed_component(
    conn: sqlite3.Connection, *, figma_id: str, name: str,
    canonical_type: str = "button",
) -> int:
    cur = conn.execute(
        "INSERT INTO components (file_id, figma_node_id, name, "
        " canonical_type) VALUES (1, ?, ?, ?)",
        (figma_id, name, canonical_type),
    )
    return cur.lastrowid


class TestParseCkrPaths:
    def test_empty_input(self):
        assert parse_ckr_paths([]) == {}

    def test_slash_delimited_names_grouped_by_head(self):
        got = parse_ckr_paths([
            "button/large/translucent",
            "button/small/solid",
            "button/small/translucent",
        ])
        assert got == {
            "button": [
                ("large", "translucent"),
                ("small", "solid"),
                ("small", "translucent"),
            ],
        }

    def test_single_segment_becomes_singleton(self):
        got = parse_ckr_paths(["New Folder", "_Key"])
        assert got == {
            "New Folder": [()],
            "_Key": [()],
        }

    def test_mixed_depth_within_family(self):
        """button/white (depth 1) alongside button/large/translucent
        (depth 2) — both belong to the 'button' family.
        """
        got = parse_ckr_paths([
            "button/white",
            "button/large/translucent",
        ])
        assert got == {
            "button": [("white",), ("large", "translucent")],
        }

    def test_preserves_input_order(self):
        """Paths within a family keep their input order so downstream
        LLM calls see consistent samples across runs.
        """
        got = parse_ckr_paths([
            "icon/back", "icon/close", "icon/ai",
        ])
        assert got["icon"] == [("back",), ("close",), ("ai",)]


class TestDeriveVariantsFromCkr:
    def test_button_family_axes_labelled_and_variants_written(self):
        conn = _fresh_db()
        # 3 button variants + 1 singleton + 1 icon variant.
        for full_name, figma_id in [
            ("button/large/translucent", "1:1"),
            ("button/small/solid", "1:2"),
            ("button/small/translucent", "1:3"),
            ("New Folder", "9:9"),
            ("icon/back", "2:1"),
        ]:
            _seed_ckr(conn, full_name, figma_id)
            _seed_component(conn, figma_id=figma_id, name=full_name)

        def stub(prompt: str) -> list[str]:
            # Haiku labels the axis names per family; return canonical
            # names for button (depth 2) vs icon (depth 1).
            if "button" in prompt:
                return ["size", "style"]
            if "icon" in prompt:
                return ["glyph"]
            return ["variant"]

        stats = derive_variants_from_ckr(
            conn, file_id=1, llm_invoker=stub,
        )
        assert stats["variants_inserted"] == 5
        assert stats["families"] == 3  # button, icon, New Folder

        rows = conn.execute(
            "SELECT name, properties FROM component_variants "
            "ORDER BY name"
        ).fetchall()
        props = {
            r[0]: json.loads(r[1] or "{}") for r in rows
        }
        assert props == {
            "New Folder": {},
            "button/large/translucent": {
                "size": "large", "style": "translucent",
            },
            "button/small/solid": {
                "size": "small", "style": "solid",
            },
            "button/small/translucent": {
                "size": "small", "style": "translucent",
            },
            "icon/back": {"glyph": "back"},
        }

    def test_mixed_depth_family_handled_per_depth(self):
        """button/white (depth 1) + button/large/translucent
        (depth 2) → two axis-label LLM calls, each depth independent.
        """
        conn = _fresh_db()
        for full_name, figma_id in [
            ("button/white", "1:1"),
            ("button/large/translucent", "1:2"),
        ]:
            _seed_ckr(conn, full_name, figma_id)
            _seed_component(conn, figma_id=figma_id, name=full_name)

        calls: list[int] = []

        def stub(prompt: str) -> list[str]:
            # Depth inferred from prompt — 1 path at depth 1, 1 at depth 2.
            if "1 axis positions" in prompt:
                calls.append(1)
                return ["style"]
            if "2 axis positions" in prompt:
                calls.append(2)
                return ["size", "style"]
            return []

        derive_variants_from_ckr(conn, file_id=1, llm_invoker=stub)
        assert sorted(calls) == [1, 2]
        rows = conn.execute(
            "SELECT name, properties FROM component_variants "
            "ORDER BY name"
        ).fetchall()
        props = {r[0]: json.loads(r[1]) for r in rows}
        assert props == {
            "button/white": {"style": "white"},
            "button/large/translucent": {
                "size": "large", "style": "translucent",
            },
        }

    def test_skips_when_no_components_row(self):
        """CKR entry without a matching components row (remote-library
        or pre-Step-1 state) → skip the variant insert, count it.
        """
        conn = _fresh_db()
        _seed_ckr(conn, "orphan/x", "5:5")  # no components row
        stats = derive_variants_from_ckr(
            conn, file_id=1, llm_invoker=lambda _p: ["foo"],
        )
        assert stats["variants_inserted"] == 0
        assert stats["skipped_no_components_row"] == 1

    def test_idempotent_on_second_run(self):
        conn = _fresh_db()
        _seed_ckr(conn, "button/small/solid", "1:1")
        _seed_component(conn, figma_id="1:1",
                        name="button/small/solid")
        stub = lambda _p: ["size", "style"]

        first = derive_variants_from_ckr(
            conn, file_id=1, llm_invoker=stub,
        )
        second = derive_variants_from_ckr(
            conn, file_id=1, llm_invoker=stub,
        )
        assert first["variants_inserted"] == 1
        assert second["variants_inserted"] == 0
        assert second["skipped_existing"] == 1
        n = conn.execute(
            "SELECT COUNT(*) FROM component_variants"
        ).fetchone()[0]
        assert n == 1

    def test_malformed_llm_response_falls_back_to_generic_names(self):
        conn = _fresh_db()
        _seed_ckr(conn, "button/small/solid", "1:1")
        _seed_component(conn, figma_id="1:1",
                        name="button/small/solid")

        def stub(_p: str) -> list[str]:
            # Wrong length — should trigger fallback.
            return ["only_one_name"]

        derive_variants_from_ckr(conn, file_id=1, llm_invoker=stub)
        props = json.loads(conn.execute(
            "SELECT properties FROM component_variants"
        ).fetchone()[0])
        assert props == {
            "variant_0": "small", "variant_1": "solid",
        }

    def test_missing_llm_invoker_uses_generic_axis_names(self):
        """Fallback path: llm_invoker=None produces 'variant_N' axes
        instead of semantic ones. Still writes rows.
        """
        conn = _fresh_db()
        _seed_ckr(conn, "button/small/solid", "1:1")
        _seed_component(conn, figma_id="1:1",
                        name="button/small/solid")
        derive_variants_from_ckr(conn, file_id=1, llm_invoker=None)
        props = json.loads(conn.execute(
            "SELECT properties FROM component_variants"
        ).fetchone()[0])
        assert props == {
            "variant_0": "small", "variant_1": "solid",
        }

    def test_singleton_has_empty_properties(self):
        conn = _fresh_db()
        _seed_ckr(conn, "Home Indicator", "8:8")
        _seed_component(
            conn, figma_id="8:8", name="Home Indicator",
            canonical_type="grabber",
        )
        stats = derive_variants_from_ckr(
            conn, file_id=1, llm_invoker=lambda _p: ["ignored"],
        )
        assert stats["singletons"] == 1
        assert stats["variants_inserted"] == 1
        props = json.loads(conn.execute(
            "SELECT properties FROM component_variants"
        ).fetchone()[0])
        assert props == {}
