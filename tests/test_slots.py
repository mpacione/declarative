"""Tests for M7.0.b Step 2 — slot derivation.

The clustering logic is pure (a Counter over child-type tuples); the
LLM is parameterised via ``llm_invoker`` so tests can pass a stub
that returns canned slot descriptors. Together these cover the
derive_slots_for_canonical_type pipeline end-to-end without any
Anthropic API cost.
"""

from __future__ import annotations

import sqlite3

import pytest

from dd.master_slots import (
    cluster_children,
    derive_slots_for_canonical_type,
    dominant_cluster,
)


def _fresh_db() -> sqlite3.Connection:
    """Minimal schema covering the tables m7_slots touches."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE files (id INTEGER PRIMARY KEY, file_key TEXT);
        INSERT INTO files (id, file_key) VALUES (1, 'dank');

        CREATE TABLE component_type_catalog (
            id INTEGER PRIMARY KEY,
            canonical_name TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL
        );
        INSERT INTO component_type_catalog (canonical_name, category)
          VALUES ('button', 'actions'),
                 ('icon_button', 'actions');

        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER,
            screen_id INTEGER,
            node_type TEXT,
            name TEXT,
            text_content TEXT,
            sort_order INTEGER DEFAULT 0,
            component_key TEXT,
            figma_node_id TEXT
        );

        CREATE TABLE screen_component_instances (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            node_id INTEGER,
            canonical_type TEXT,
            classification_source TEXT,
            consensus_method TEXT
        );

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
            component_id INTEGER NOT NULL REFERENCES components(id)
              ON DELETE CASCADE,
            name TEXT NOT NULL,
            slot_type TEXT,
            is_required INTEGER NOT NULL DEFAULT 0,
            default_content TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            description TEXT,
            UNIQUE(component_id, name)
        );
    """)
    return conn


def _add_button(
    conn: sqlite3.Connection, node_id: int,
    *, shape: tuple[str, ...] = ("INSTANCE", "TEXT", "INSTANCE"),
    label_text: str = "Continue", consensus_method: str = "formal",
    canonical_type: str = "button",
) -> None:
    """Seed one classified button instance with children matching
    the given shape.
    """
    conn.execute(
        "INSERT INTO nodes (id, screen_id, node_type, name) "
        "VALUES (?, 1, 'INSTANCE', ?)",
        (node_id, "button/x"),
    )
    for i, ntype in enumerate(shape):
        kid_id = node_id * 100 + i
        text = label_text if ntype == "TEXT" else ""
        kname = {
            "INSTANCE": f"icon/x{i}",
            "TEXT": "label",
        }.get(ntype, f"child_{i}")
        conn.execute(
            "INSERT INTO nodes (id, parent_id, screen_id, node_type, "
            " name, text_content, sort_order) "
            "VALUES (?, ?, 1, ?, ?, ?, ?)",
            (kid_id, node_id, ntype, kname, text, i),
        )
    conn.execute(
        "INSERT INTO screen_component_instances "
        "(screen_id, node_id, canonical_type, classification_source, "
        " consensus_method) VALUES (1, ?, ?, 'llm', ?)",
        (node_id, canonical_type, consensus_method),
    )


def _add_master(
    conn: sqlite3.Connection, *, component_id: int, figma_id: str,
    name: str, canonical_type: str,
) -> None:
    conn.execute(
        "INSERT INTO components (id, file_id, figma_node_id, name, "
        " canonical_type) VALUES (?, 1, ?, ?, ?)",
        (component_id, figma_id, name, canonical_type),
    )


class TestClusterChildren:
    def test_empty_input_returns_empty_counter(self):
        conn = _fresh_db()
        assert cluster_children(conn, []) == {}

    def test_identical_shapes_cluster_together(self):
        """INSTANCE children with no component_key register as
        COMPONENT; TEXT stays TEXT.
        """
        conn = _fresh_db()
        for nid in (10, 11, 12):
            _add_button(conn, nid, shape=("INSTANCE", "TEXT", "INSTANCE"))
        counts = cluster_children(conn, [10, 11, 12])
        assert counts == {("COMPONENT", "TEXT", "COMPONENT"): 3}

    def test_different_shapes_land_in_different_clusters(self):
        conn = _fresh_db()
        _add_button(conn, 20, shape=("INSTANCE", "TEXT", "INSTANCE"))
        _add_button(conn, 21, shape=("TEXT",))
        _add_button(conn, 22, shape=("INSTANCE", "TEXT"))
        counts = cluster_children(conn, [20, 21, 22])
        assert counts[("COMPONENT", "TEXT", "COMPONENT")] == 1
        assert counts[("TEXT",)] == 1
        assert counts[("COMPONENT", "TEXT")] == 1

    def test_icon_component_keys_cluster_as_ICON(self):
        """When a child INSTANCE has a component_key pointing at a
        component whose canonical_type is 'icon', the cluster
        distinguishes it from a generic COMPONENT child.
        """
        conn = _fresh_db()
        # Seed an icon master node + its component_key linkage.
        conn.execute(
            "INSERT INTO nodes (id, screen_id, node_type, "
            "figma_node_id, component_key, name) "
            "VALUES (9001, 1, 'COMPONENT', '99:99', 'ICONKEY', 'icon/x')"
        )
        conn.execute(
            "INSERT INTO components (file_id, figma_node_id, name, "
            "canonical_type) VALUES (1, '99:99', 'icon/x', 'icon')"
        )
        # Button with an icon-typed INSTANCE at position 0.
        conn.execute(
            "INSERT INTO nodes (id, screen_id, node_type, name) "
            "VALUES (30, 1, 'INSTANCE', 'button/x')"
        )
        conn.execute(
            "INSERT INTO nodes (id, parent_id, screen_id, node_type, "
            "name, component_key, sort_order) "
            "VALUES (3000, 30, 1, 'INSTANCE', 'icon/back', "
            "'ICONKEY', 0)"
        )
        conn.execute(
            "INSERT INTO nodes (id, parent_id, screen_id, node_type, "
            "name, text_content, sort_order) "
            "VALUES (3001, 30, 1, 'TEXT', 'label', 'Continue', 1)"
        )
        counts = cluster_children(conn, [30])
        assert counts == {("ICON", "TEXT"): 1}


class TestDominantCluster:
    def test_returns_top_shape_above_threshold(self):
        from collections import Counter
        c = Counter({
            ("INSTANCE", "TEXT", "INSTANCE"): 418,
            ("TEXT",): 33,
        })
        assert dominant_cluster(c, min_share=0.5) == (
            "INSTANCE", "TEXT", "INSTANCE"
        )

    def test_returns_none_when_top_below_threshold(self):
        from collections import Counter
        # No cluster is a majority.
        c = Counter({("A",): 40, ("B",): 35, ("C",): 25})
        assert dominant_cluster(c, min_share=0.5) is None

    def test_returns_none_on_empty_counter(self):
        from collections import Counter
        assert dominant_cluster(Counter()) is None


class TestDeriveSlotsForCanonicalType:
    def test_writes_slot_rows_for_every_master(self):
        """Three button masters + a stub LLM returning a 3-slot
        descriptor → 9 rows in component_slots.
        """
        conn = _fresh_db()
        # Three masters.
        for mid, fid, fname in (
            (101, "5749:82453", "button/small/solid"),
            (102, "5749:82457", "button/large/translucent"),
            (103, "5749:82461", "button/small/translucent"),
        ):
            _add_master(
                conn, component_id=mid, figma_id=fid,
                name=fname, canonical_type="button",
            )
        # Trusted button instances.
        for nid in range(500, 520):
            _add_button(conn, nid)

        def stub(_prompt: str) -> list[dict]:
            return [
                {"position": 0, "name": "leading_icon",
                 "is_required": False,
                 "description": "Optional icon before the label"},
                {"position": 1, "name": "label",
                 "is_required": True,
                 "description": "The button's text label"},
                {"position": 2, "name": "trailing_icon",
                 "is_required": False,
                 "description": "Optional icon after the label"},
            ]

        stats = derive_slots_for_canonical_type(
            conn, "button", file_id=1, llm_invoker=stub,
        )
        assert stats["masters"] == 3
        assert stats["slots_inserted"] == 9
        rows = conn.execute(
            "SELECT component_id, name, slot_type, is_required, "
            "       sort_order FROM component_slots ORDER BY "
            "component_id, sort_order"
        ).fetchall()
        assert len(rows) == 9
        # Each master has (leading_icon, label, trailing_icon).
        # is_required comes from the LLM's semantic judgment:
        # leading_icon/trailing_icon optional, label required.
        for start in (0, 3, 6):
            chunk = rows[start:start + 3]
            names = [r[1] for r in chunk]
            assert names == ["leading_icon", "label", "trailing_icon"]
            # Without icon-typed component_keys these classify as
            # COMPONENT, not ICON.
            assert [r[2] for r in chunk] == [
                "component", "text", "component",
            ]
            # LLM stub said required=[False, True, False].
            assert [r[3] for r in chunk] == [0, 1, 0]

    def test_is_required_reports_llm_vs_data_mismatches(self):
        """LLM's is_required claim is persisted (semantic judgment);
        data cross-check lives in stats.is_required_mismatches.
        """
        conn = _fresh_db()
        _add_master(conn, component_id=1000, figma_id="mx:1", name="b",
                    canonical_type="button")
        for nid in range(1500, 1505):
            _add_button(conn, nid)  # every instance has 3 kids

        def stub(_p: str):
            return [
                {"position": 0, "name": "leading_icon",
                 "is_required": False, "description": "d"},
                {"position": 1, "name": "label",
                 "is_required": False, "description": "d"},
                {"position": 2, "name": "trailing_icon",
                 "is_required": False, "description": "d"},
            ]
        stats = derive_slots_for_canonical_type(
            conn, "button", file_id=1, llm_invoker=stub,
        )
        # LLM said false for every position → persist false.
        req = [r[0] for r in conn.execute(
            "SELECT is_required FROM component_slots "
            "ORDER BY sort_order"
        ).fetchall()]
        assert req == [0, 0, 0]
        # Data says every position is filled (5/5 have 3 kids), so
        # the LLM's "optional" claim mismatches data at 3 positions.
        assert len(stats["is_required_mismatches"]) == 3

    def test_out_of_bounds_llm_positions_counted(self):
        """LLM returning position=5 for a 3-slot shape is tallied in
        stats; only in-range positions produce slot rows.
        """
        conn = _fresh_db()
        _add_master(conn, component_id=1100, figma_id="mx:2", name="b",
                    canonical_type="button")
        for nid in range(1600, 1605):
            _add_button(conn, nid)

        def stub(_p: str):
            return [
                {"position": 0, "name": "leading_icon",
                 "is_required": True, "description": "d"},
                {"position": 1, "name": "label",
                 "is_required": True, "description": "d"},
                {"position": 2, "name": "trailing_icon",
                 "is_required": True, "description": "d"},
                {"position": 5, "name": "phantom",
                 "is_required": True, "description": "d"},
            ]
        stats = derive_slots_for_canonical_type(
            conn, "button", file_id=1, llm_invoker=stub,
        )
        assert stats["slots_inserted"] == 3
        assert stats["llm_out_of_bounds_entries"] == 1

    def test_rejects_type_with_no_dominant_cluster(self):
        """When the top cluster is < min_cluster_share, skip the
        LLM call entirely.
        """
        conn = _fresh_db()
        _add_master(conn, component_id=200, figma_id="1:1",
                    name="x", canonical_type="button")
        # 2 of each shape → flat distribution.
        for i, shape in enumerate([
            ("INSTANCE", "TEXT", "INSTANCE"),
            ("INSTANCE", "TEXT", "INSTANCE"),
            ("TEXT",), ("TEXT",),
            ("INSTANCE",), ("INSTANCE",),
        ]):
            _add_button(conn, 600 + i, shape=shape)

        def stub(prompt):
            raise AssertionError("llm should not be called")

        stats = derive_slots_for_canonical_type(
            conn, "button", file_id=1, llm_invoker=stub,
            min_cluster_share=0.5,
        )
        assert stats["slots_inserted"] == 0
        assert "no dominant cluster" in stats.get("error", "")

    def test_skips_untrusted_instances_in_clustering(self):
        """Untrusted weighted_tie / weighted_majority instances don't
        feed into the clusterer.
        """
        conn = _fresh_db()
        _add_master(conn, component_id=300, figma_id="2:2",
                    name="b", canonical_type="button")
        # 5 trusted instances with shape A.
        for nid in range(700, 705):
            _add_button(conn, nid, shape=("INSTANCE", "TEXT", "INSTANCE"))
        # 100 untrusted instances with shape B — should NOT
        # dominate.
        for nid in range(800, 900):
            _add_button(conn, nid, shape=("TEXT",),
                        consensus_method="weighted_tie")

        def stub(_prompt):
            return [
                {"position": 0, "name": "leading_icon",
                 "is_required": False, "description": "d"},
                {"position": 1, "name": "label",
                 "is_required": True, "description": "d"},
                {"position": 2, "name": "trailing_icon",
                 "is_required": False, "description": "d"},
            ]
        stats = derive_slots_for_canonical_type(
            conn, "button", file_id=1, llm_invoker=stub,
        )
        # Trusted cluster wins despite being outnumbered 5-to-100 in
        # the raw data. Shape uses semantic classes (COMPONENT for
        # INSTANCE without icon-typed component_key).
        assert stats["dominant_shape"] == (
            "COMPONENT", "TEXT", "COMPONENT"
        )
        assert stats["slots_inserted"] == 3

    def test_idempotent_on_second_run(self):
        conn = _fresh_db()
        _add_master(conn, component_id=400, figma_id="3:3",
                    name="b", canonical_type="button")
        for nid in range(900, 905):
            _add_button(conn, nid)

        def stub(_prompt):
            return [
                {"position": 0, "name": "leading_icon",
                 "is_required": False, "description": "d"},
                {"position": 1, "name": "label",
                 "is_required": True, "description": "d"},
                {"position": 2, "name": "trailing_icon",
                 "is_required": False, "description": "d"},
            ]
        first = derive_slots_for_canonical_type(
            conn, "button", file_id=1, llm_invoker=stub,
        )
        second = derive_slots_for_canonical_type(
            conn, "button", file_id=1, llm_invoker=stub,
        )
        assert first["slots_inserted"] == 3
        assert second["slots_inserted"] == 0  # UNIQUE collision
        n = conn.execute(
            "SELECT COUNT(*) FROM component_slots"
        ).fetchone()[0]
        assert n == 3

    def test_returns_no_trusted_instances_error(self):
        conn = _fresh_db()
        _add_master(conn, component_id=500, figma_id="4:4",
                    name="b", canonical_type="button")
        stats = derive_slots_for_canonical_type(
            conn, "button", file_id=1, llm_invoker=lambda _p: [],
        )
        assert stats["slots_inserted"] == 0
        assert "no trusted" in stats["error"]

    def test_llm_empty_response_handled_gracefully(self):
        conn = _fresh_db()
        _add_master(conn, component_id=600, figma_id="5:5",
                    name="b", canonical_type="button")
        for nid in range(1000, 1005):
            _add_button(conn, nid)
        stats = derive_slots_for_canonical_type(
            conn, "button", file_id=1, llm_invoker=lambda _p: [],
        )
        assert stats["slots_inserted"] == 0
        assert "no slots" in stats["error"]

    def test_leaf_canonical_type_emits_no_slots(self):
        """Leaf types (no children — e.g. icon, grabber) cluster to
        the empty shape. Return cleanly, don't burn an LLM call.
        """
        conn = _fresh_db()
        conn.execute(
            "INSERT INTO component_type_catalog (canonical_name, category) "
            "VALUES ('icon', 'content_and_display')"
        )
        _add_master(conn, component_id=2000, figma_id="i:1",
                    name="icon/x", canonical_type="icon")
        # Three childless instances.
        for nid in range(2000, 2003):
            conn.execute(
                "INSERT INTO nodes (id, screen_id, node_type, name) "
                "VALUES (?, 1, 'VECTOR', 'icon-leaf')",
                (nid,),
            )
            conn.execute(
                "INSERT INTO screen_component_instances "
                "(screen_id, node_id, canonical_type, "
                " classification_source, consensus_method) "
                "VALUES (1, ?, 'icon', 'llm', 'formal')",
                (nid,),
            )

        def stub(_p: str):
            raise AssertionError("llm should not be called for leaves")
        stats = derive_slots_for_canonical_type(
            conn, "icon", file_id=1, llm_invoker=stub,
        )
        assert stats["slots_inserted"] == 0
        assert stats["dominant_shape"] == ()
        assert "leaf canonical_type" in stats.get("note", "")

    def test_llm_requires_invoker(self):
        conn = _fresh_db()
        _add_master(conn, component_id=700, figma_id="6:6",
                    name="b", canonical_type="button")
        for nid in range(1100, 1105):
            _add_button(conn, nid)
        with pytest.raises(ValueError, match="llm_invoker"):
            derive_slots_for_canonical_type(
                conn, "button", file_id=1, llm_invoker=None,
            )
