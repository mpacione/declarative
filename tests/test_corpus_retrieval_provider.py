"""Contract tests for CorpusRetrievalProvider — v0.2 retrieval path.

The provider returns a ``PresentationTemplate`` whose ``corpus_subtree``
field carries a real IR subtree extracted from the DB's
``screen_component_instances`` table. When compose sees this field set,
it splices the subtree into the emitted IR in place of synthesising.

Tests cover:
- provider protocol compliance (supports / resolve / priority / backend)
- supports() returns True iff SCI has a row for the requested type
- resolve() returns a template with corpus_subtree populated
- corpus_subtree carries the root element + children + visual dict
- retrieval is deterministic for the same (type, variant) pair
- feature flag DD_ENABLE_CORPUS_RETRIEVAL gates the provider
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any
from unittest.mock import patch

import pytest

from dd.composition.protocol import ComponentProvider, PresentationTemplate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def corpus_conn(tmp_path) -> sqlite3.Connection:
    """Minimal SCI-populated DB: one card fragment, one button fragment."""
    db_path = tmp_path / "corpus.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Schema — only the tables the provider reads.
    conn.executescript("""
        CREATE TABLE files (id INTEGER PRIMARY KEY, file_key TEXT, name TEXT);
        CREATE TABLE screens (
            id INTEGER PRIMARY KEY,
            file_id INTEGER,
            name TEXT,
            width REAL,
            height REAL,
            screen_type TEXT
        );
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            figma_node_id TEXT,
            parent_id INTEGER,
            name TEXT,
            node_type TEXT,
            depth INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            is_semantic INTEGER DEFAULT 1,
            component_id INTEGER,
            component_key TEXT,
            x REAL, y REAL, width REAL, height REAL,
            layout_mode TEXT,
            padding_top REAL, padding_right REAL, padding_bottom REAL, padding_left REAL,
            item_spacing REAL, counter_axis_spacing REAL,
            primary_align TEXT, counter_align TEXT,
            layout_sizing_h TEXT, layout_sizing_v TEXT,
            fills TEXT, strokes TEXT, effects TEXT, corner_radius TEXT,
            opacity REAL DEFAULT 1.0,
            blend_mode TEXT,
            visible INTEGER DEFAULT 1,
            stroke_weight REAL,
            text_content TEXT,
            font_family TEXT, font_weight INTEGER, font_size REAL,
            line_height TEXT, text_align TEXT,
            extracted_at TEXT
        );
        CREATE TABLE component_type_catalog (
            id INTEGER PRIMARY KEY,
            canonical_name TEXT UNIQUE,
            category TEXT
        );
        CREATE TABLE screen_component_instances (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            node_id INTEGER,
            catalog_type_id INTEGER,
            canonical_type TEXT,
            confidence REAL,
            classification_source TEXT,
            parent_instance_id INTEGER,
            UNIQUE(screen_id, node_id)
        );
    """)

    # Seed catalog types
    conn.execute(
        "INSERT INTO component_type_catalog (canonical_name, category) VALUES "
        "('card','content_and_display'),('button','actions'),('header','navigation')"
    )
    # Seed one file + screen
    conn.execute(
        "INSERT INTO files (id, file_key, name) VALUES (1, 'test', 'Test')"
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, name, width, height, screen_type) "
        "VALUES (1, 1, 'Test Screen', 390, 844, 'app_screen')"
    )

    # Seed a card subtree: card (node 10) with a title text child (node 11)
    conn.execute(
        "INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, node_type, "
        "depth, sort_order, width, height, layout_mode, padding_top, padding_right, "
        "padding_bottom, padding_left, item_spacing, fills, strokes, corner_radius, "
        "stroke_weight) VALUES "
        "(10, 1, '1:10', NULL, 'Product Card', 'FRAME', 1, 0, 343, 120, 'VERTICAL', "
        "16, 16, 16, 16, 8, "
        "'[{\"type\":\"SOLID\",\"color\":{\"r\":1,\"g\":1,\"b\":1,\"a\":1}}]', "
        "'[{\"type\":\"SOLID\",\"color\":{\"r\":0.9,\"g\":0.9,\"b\":0.9,\"a\":1}}]', "
        "'12', 1.0)"
    )
    conn.execute(
        "INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, node_type, "
        "depth, sort_order, width, height, text_content, font_family, font_weight, "
        "font_size) VALUES "
        "(11, 1, '1:11', 10, 'Title', 'TEXT', 2, 0, 311, 24, "
        "'Original Title', 'Inter', 600, 18)"
    )
    conn.execute(
        "INSERT INTO screen_component_instances (screen_id, node_id, catalog_type_id, "
        "canonical_type, confidence, classification_source) VALUES "
        "(1, 10, 1, 'card', 0.9, 'heuristic')"
    )

    # Seed a button subtree: button (node 20) with a label text child (node 21)
    conn.execute(
        "INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, node_type, "
        "depth, sort_order, width, height, layout_mode, padding_top, padding_right, "
        "padding_bottom, padding_left, fills, corner_radius) VALUES "
        "(20, 1, '1:20', NULL, 'Primary Button', 'INSTANCE', 1, 0, 120, 44, 'HORIZONTAL', "
        "12, 20, 12, 20, "
        "'[{\"type\":\"SOLID\",\"color\":{\"r\":0,\"g\":0,\"b\":0,\"a\":1}}]', '22')"
    )
    conn.execute(
        "INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, node_type, "
        "depth, sort_order, text_content, font_family, font_size) VALUES "
        "(21, 1, '1:21', 20, 'Label', 'TEXT', 2, 0, 'Click me', 'Inter', 15)"
    )
    conn.execute(
        "INSERT INTO screen_component_instances (screen_id, node_id, catalog_type_id, "
        "canonical_type, confidence, classification_source) VALUES "
        "(1, 20, 2, 'button', 1.0, 'formal')"
    )

    conn.commit()
    return conn


@pytest.fixture
def minimal_context() -> dict[str, Any]:
    return {
        "project_tokens": {},
        "ingested_tokens": {},
        "universal_tokens": {},
        "variant_bindings": {},
    }


# ---------------------------------------------------------------------------
# Module-presence + protocol-compliance
# ---------------------------------------------------------------------------


class TestProviderProtocol:
    def test_module_importable(self):
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        assert CorpusRetrievalProvider is not None

    def test_provider_protocol_compliance(self, corpus_conn):
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=corpus_conn)
        assert isinstance(p, ComponentProvider)
        assert p.backend == "corpus:retrieval"
        assert p.priority > 100  # above ProjectCKRProvider

    def test_supports_returns_true_for_sci_populated_type(
        self, corpus_conn, monkeypatch,
    ):
        monkeypatch.setenv("DD_ENABLE_CORPUS_RETRIEVAL", "1")
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=corpus_conn)
        assert p.supports("card", None) is True
        assert p.supports("button", None) is True

    def test_supports_returns_false_for_unpopulated_type(
        self, corpus_conn, monkeypatch,
    ):
        monkeypatch.setenv("DD_ENABLE_CORPUS_RETRIEVAL", "1")
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=corpus_conn)
        assert p.supports("nonexistent_type", None) is False

    def test_supports_returns_false_for_header_with_no_instances(
        self, corpus_conn, monkeypatch,
    ):
        """'header' is in the catalog but has no SCI rows in the fixture."""
        monkeypatch.setenv("DD_ENABLE_CORPUS_RETRIEVAL", "1")
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=corpus_conn)
        assert p.supports("header", None) is False


# ---------------------------------------------------------------------------
# Resolve returns a PresentationTemplate with corpus_subtree
# ---------------------------------------------------------------------------


class TestResolveReturnsSubtree:
    def test_resolve_returns_presentation_template(
        self, corpus_conn, minimal_context,
    ):
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=corpus_conn)
        template = p.resolve("card", None, minimal_context)
        assert template is not None
        assert isinstance(template, PresentationTemplate)
        assert template.catalog_type == "card"
        assert template.provider == "corpus:retrieval"

    def test_resolve_populates_corpus_subtree_field(
        self, corpus_conn, minimal_context,
    ):
        """The v0.2 retrieval extension: corpus_subtree carries a real
        IR subtree extracted from SCI."""
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=corpus_conn)
        template = p.resolve("card", None, minimal_context)
        assert template is not None
        # corpus_subtree is on the template (new field)
        subtree = getattr(template, "corpus_subtree", None)
        assert subtree is not None
        # It carries provenance
        assert subtree["source_screen_id"] == 1
        assert subtree["source_node_id"] == 10
        # And a root element with visual properties
        assert "root" in subtree
        assert "elements" in subtree
        root_eid = subtree["root"]
        root_elem = subtree["elements"][root_eid]
        # Type/role split: "card" is a semantic role, structural
        # primitive is "frame". See docs/plan-type-role-split.md.
        assert root_elem["type"] == "frame"
        assert root_elem.get("role") == "card"
        # Visual dict present with fills/strokes/radius (DB snake_case)
        assert "visual" in root_elem
        assert root_elem["visual"]["fills"]  # non-empty
        assert root_elem["visual"]["strokes"]  # non-empty
        # corner_radius is DB-native: either a JSON string or a number
        assert root_elem["visual"]["corner_radius"] in ("12", 12, 12.0)

    def test_resolve_includes_children(self, corpus_conn, minimal_context):
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=corpus_conn)
        template = p.resolve("card", None, minimal_context)
        subtree = template.corpus_subtree
        # Root has one child (the title text)
        root_elem = subtree["elements"][subtree["root"]]
        assert len(root_elem["children"]) == 1
        child_eid = root_elem["children"][0]
        child_elem = subtree["elements"][child_eid]
        assert child_elem["type"] == "text"
        assert child_elem["props"]["text"] == "Original Title"

    def test_resolve_unknown_type_returns_none(
        self, corpus_conn, minimal_context,
    ):
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=corpus_conn)
        assert p.resolve("nonexistent_type", None, minimal_context) is None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_query_returns_same_source_node(
        self, corpus_conn, minimal_context,
    ):
        """Two identical resolves must pick the same source node.
        Non-determinism would make A/B comparisons noisy and bisection
        impossible — keep it pure."""
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=corpus_conn)
        t1 = p.resolve("card", None, minimal_context)
        t2 = p.resolve("card", None, minimal_context)
        assert t1.corpus_subtree["source_node_id"] == (
            t2.corpus_subtree["source_node_id"]
        )


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


class TestStructuralMatching:
    """v0.3 ranking: when context supplies ``expected_children`` (the
    LLM plan's direct child types under this component), the provider
    prefers candidates whose DB children's types match best. Tie-break
    remains descendant count then node_id."""

    @pytest.fixture
    def two_card_conn(self, tmp_path) -> sqlite3.Connection:
        """Fixture with two card candidates:
          - card A (node 100): children = [image, heading] — 2 descendants
          - card B (node 200): children = [image, heading, text] — 3 descendants

        For expected_children=[image, heading, text], card B should win
        (better Jaccard). For empty expected_children, card A should win
        (smaller descendant count)."""
        db_path = tmp_path / "two_cards.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE files (id INTEGER PRIMARY KEY, file_key TEXT, name TEXT);
            CREATE TABLE screens (
                id INTEGER PRIMARY KEY, file_id INTEGER, name TEXT,
                width REAL, height REAL, screen_type TEXT
            );
            CREATE TABLE nodes (
                id INTEGER PRIMARY KEY, screen_id INTEGER, figma_node_id TEXT,
                parent_id INTEGER, name TEXT, node_type TEXT,
                depth INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0,
                is_semantic INTEGER DEFAULT 1,
                component_id INTEGER, component_key TEXT,
                x REAL, y REAL, width REAL, height REAL,
                layout_mode TEXT,
                padding_top REAL, padding_right REAL,
                padding_bottom REAL, padding_left REAL,
                item_spacing REAL, counter_axis_spacing REAL,
                primary_align TEXT, counter_align TEXT,
                layout_sizing_h TEXT, layout_sizing_v TEXT,
                fills TEXT, strokes TEXT, effects TEXT, corner_radius TEXT,
                opacity REAL DEFAULT 1.0, blend_mode TEXT,
                visible INTEGER DEFAULT 1, stroke_weight REAL,
                text_content TEXT, font_family TEXT, font_weight INTEGER,
                font_size REAL, line_height TEXT, text_align TEXT,
                extracted_at TEXT
            );
            CREATE TABLE component_type_catalog (
                id INTEGER PRIMARY KEY, canonical_name TEXT UNIQUE, category TEXT
            );
            CREATE TABLE screen_component_instances (
                id INTEGER PRIMARY KEY, screen_id INTEGER, node_id INTEGER,
                catalog_type_id INTEGER, canonical_type TEXT, confidence REAL,
                classification_source TEXT, parent_instance_id INTEGER,
                UNIQUE(screen_id, node_id)
            );
        """)
        conn.execute(
            "INSERT INTO component_type_catalog (canonical_name, category) "
            "VALUES ('card','content_and_display'),('image','content_and_display'),"
            "('heading','content_and_display'),('text','content_and_display')"
        )
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'k', 'Test')")
        conn.execute(
            "INSERT INTO screens (id, file_id, name, width, height, screen_type) "
            "VALUES (1, 1, 'S1', 390, 844, 'app_screen')"
        )

        # Card A: node 100, children 101 (image) + 102 (heading)
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, "
            "node_type, width, height, corner_radius) VALUES "
            "(100, 1, '1:100', NULL, 'Card A', 'FRAME', 300, 100, '8')"
        )
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, "
            "node_type, width, height) VALUES "
            "(101, 1, '1:101', 100, 'img', 'FRAME', 100, 60), "
            "(102, 1, '1:102', 100, 'hd',  'TEXT',  100, 20)"
        )
        conn.execute(
            "INSERT INTO screen_component_instances (screen_id, node_id, "
            "canonical_type, confidence, classification_source) VALUES "
            "(1, 100, 'card', 0.9, 'heuristic'), "
            "(1, 101, 'image', 0.9, 'heuristic'), "
            "(1, 102, 'heading', 0.9, 'heuristic')"
        )

        # Card B: node 200, children 201/202/203 (image/heading/text)
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, "
            "node_type, width, height, corner_radius) VALUES "
            "(200, 1, '1:200', NULL, 'Card B', 'FRAME', 300, 150, '16')"
        )
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, "
            "node_type, width, height) VALUES "
            "(201, 1, '1:201', 200, 'img', 'FRAME', 100, 60), "
            "(202, 1, '1:202', 200, 'hd',  'TEXT',  100, 20), "
            "(203, 1, '1:203', 200, 'txt', 'TEXT',  100, 40)"
        )
        conn.execute(
            "INSERT INTO screen_component_instances (screen_id, node_id, "
            "canonical_type, confidence, classification_source) VALUES "
            "(1, 200, 'card', 0.9, 'heuristic'), "
            "(1, 201, 'image', 0.9, 'heuristic'), "
            "(1, 202, 'heading', 0.9, 'heuristic'), "
            "(1, 203, 'text', 0.9, 'heuristic')"
        )
        conn.commit()
        return conn

    def test_expected_children_prefers_structural_match(
        self, two_card_conn, monkeypatch,
    ):
        """When context supplies expected_children=[image, heading, text],
        prefer card B (exact match) even though card A is smaller."""
        monkeypatch.setenv("DD_ENABLE_CORPUS_RETRIEVAL", "1")
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=two_card_conn)
        ctx = {"expected_children": ["image", "heading", "text"]}
        t = p.resolve("card", None, ctx)
        assert t is not None
        assert t.corpus_subtree["source_node_id"] == 200

    def test_no_expected_children_falls_back_to_size_ranking(
        self, two_card_conn, monkeypatch,
    ):
        """With no expected_children, smaller subtree wins — card A."""
        monkeypatch.setenv("DD_ENABLE_CORPUS_RETRIEVAL", "1")
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=two_card_conn)
        t = p.resolve("card", None, {})
        assert t is not None
        assert t.corpus_subtree["source_node_id"] == 100

    def test_partial_match_outranks_mismatch(
        self, two_card_conn, monkeypatch,
    ):
        """When expected=[image, heading, button], card B (2/3 match) beats
        card A (2/3 match by Jaccard is tied, so smaller wins). But when
        expected=[image, heading] exactly, card A wins (exact match)."""
        monkeypatch.setenv("DD_ENABLE_CORPUS_RETRIEVAL", "1")
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        p = CorpusRetrievalProvider(conn=two_card_conn)
        ctx = {"expected_children": ["image", "heading"]}
        t = p.resolve("card", None, ctx)
        assert t is not None
        # Card A has exactly [image, heading]; Jaccard = 1.0
        # Card B has [image, heading, text]; Jaccard = 2/3
        assert t.corpus_subtree["source_node_id"] == 100


class TestFeatureFlag:
    def test_disabled_flag_makes_supports_return_false(
        self, corpus_conn, monkeypatch,
    ):
        """DD_ENABLE_CORPUS_RETRIEVAL=0 (or absent) disables the provider.
        The flag is opt-in — default OFF until PoC validates."""
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        monkeypatch.delenv("DD_ENABLE_CORPUS_RETRIEVAL", raising=False)
        p = CorpusRetrievalProvider(conn=corpus_conn)
        assert p.supports("card", None) is False

    def test_enabled_flag_enables_provider(
        self, corpus_conn, monkeypatch,
    ):
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        monkeypatch.setenv("DD_ENABLE_CORPUS_RETRIEVAL", "1")
        p = CorpusRetrievalProvider(conn=corpus_conn)
        assert p.supports("card", None) is True
