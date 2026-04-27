"""Integration test for compose_screen + CorpusRetrievalProvider.

Verifies that when the registry contains a CorpusRetrievalProvider that
returns a template with ``corpus_subtree``, compose splices the subtree
into the emitted IR instead of synthesising from hand-authored
templates.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from dd.composition.protocol import PresentationTemplate


@pytest.fixture
def corpus_conn(tmp_path) -> sqlite3.Connection:
    """SCI-populated fixture matching test_corpus_retrieval_provider."""
    from tests.test_corpus_retrieval_provider import corpus_conn as _inner
    # Reuse; pytest fixtures can't be directly called — fall through
    # to inline seed.
    db_path = tmp_path / "corpus.db"
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
        "VALUES ('card','content_and_display')"
    )
    conn.execute(
        "INSERT INTO files (id, file_key, name) VALUES (1, 'k', 'Test')"
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, name, width, height, screen_type) "
        "VALUES (1, 1, 'S', 390, 844, 'app_screen')"
    )
    conn.execute(
        "INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, "
        "node_type, depth, sort_order, width, height, layout_mode, "
        "padding_top, padding_right, padding_bottom, padding_left, "
        "item_spacing, fills, strokes, corner_radius, stroke_weight) "
        "VALUES (10, 1, '1:10', NULL, 'Card', 'FRAME', 1, 0, 343, 120, "
        "'VERTICAL', 16, 16, 16, 16, 8, "
        "'[{\"type\":\"SOLID\",\"color\":{\"r\":1,\"g\":1,\"b\":1,\"a\":1}}]', "
        "'[{\"type\":\"SOLID\",\"color\":{\"r\":0.9,\"g\":0.9,\"b\":0.9,\"a\":1}}]', "
        "'12', 1.0)"
    )
    conn.execute(
        "INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, "
        "node_type, depth, sort_order, width, height, text_content, "
        "font_family, font_weight, font_size) VALUES "
        "(11, 1, '1:11', 10, 'Title', 'TEXT', 2, 0, 311, 24, "
        "'Original Title', 'Inter', 600, 18)"
    )
    conn.execute(
        "INSERT INTO screen_component_instances (screen_id, node_id, "
        "catalog_type_id, canonical_type, confidence, classification_source) "
        "VALUES (1, 10, 1, 'card', 0.9, 'heuristic')"
    )
    conn.commit()
    return conn


class TestComposeSplicesCorpusSubtree:
    """When a CorpusRetrievalProvider is registered at higher priority
    and returns a template with corpus_subtree, compose splices the
    subtree into the emitted spec."""

    def test_spliced_subtree_replaces_synthesis(
        self, corpus_conn, monkeypatch,
    ):
        monkeypatch.setenv("DD_ENABLE_CORPUS_RETRIEVAL", "1")

        from dd.compose import compose_screen
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        from dd.composition.providers.universal import UniversalCatalogProvider
        from dd.composition.registry import ProviderRegistry

        registry = ProviderRegistry(providers=[
            CorpusRetrievalProvider(conn=corpus_conn),
            UniversalCatalogProvider(),
        ])

        components = [{"type": "card", "props": {"title": "Hello"}}]
        spec = compose_screen(components, registry=registry)

        elements = spec["elements"]
        # Type/role split: "card" is a semantic role, structural
        # primitive is "frame". See docs/plan-type-role-split.md.
        card_elems = [
            e for e in elements.values() if e.get("role") == "card"
        ]
        assert len(card_elems) == 1
        card = card_elems[0]
        # The card carries real DB visual properties
        assert "visual" in card
        assert card["visual"]["fills"]  # non-empty
        assert card["visual"]["corner_radius"] in ("12", 12, 12.0)

    def test_spliced_subtree_includes_children(
        self, corpus_conn, monkeypatch,
    ):
        monkeypatch.setenv("DD_ENABLE_CORPUS_RETRIEVAL", "1")

        from dd.compose import compose_screen
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        from dd.composition.providers.universal import UniversalCatalogProvider
        from dd.composition.registry import ProviderRegistry

        registry = ProviderRegistry(providers=[
            CorpusRetrievalProvider(conn=corpus_conn),
            UniversalCatalogProvider(),
        ])
        spec = compose_screen(
            [{"type": "card"}], registry=registry,
        )

        # The card's children include a text child from the corpus.
        # Splice preserves the structural subtree but STRIPS the DB's
        # original text content — no leak of source-screen text into
        # Mode-3 output. When the LLM didn't supply text, the slot
        # ends up empty (caller is expected to fill it downstream).
        elements = spec["elements"]
        # Type/role split: "card" is a semantic role, structural
        # primitive is "frame". See docs/plan-type-role-split.md.
        card_eid = next(
            eid for eid, e in elements.items() if e.get("role") == "card"
        )
        card = elements[card_eid]
        assert len(card.get("children", [])) == 1
        child_eid = card["children"][0]
        child = elements[child_eid]
        # child is a TEXT primitive with no extra role (role == type → elided)
        assert child["type"] == "text"
        assert child.get("props", {}).get("text") == ""  # DB "Original Title" stripped

    def test_flag_off_falls_back_to_synthesis(
        self, corpus_conn, monkeypatch,
    ):
        """When DD_ENABLE_CORPUS_RETRIEVAL is not set, compose uses the
        existing synthesis path (template merge, not subtree splice)."""
        monkeypatch.delenv("DD_ENABLE_CORPUS_RETRIEVAL", raising=False)

        from dd.compose import compose_screen
        from dd.composition.providers.corpus_retrieval import (
            CorpusRetrievalProvider,
        )
        from dd.composition.providers.universal import UniversalCatalogProvider
        from dd.composition.registry import ProviderRegistry

        registry = ProviderRegistry(providers=[
            CorpusRetrievalProvider(conn=corpus_conn),
            UniversalCatalogProvider(),
        ])
        spec = compose_screen([{"type": "card"}], registry=registry)

        # Card element exists (from universal synthesis), but does NOT
        # carry a real corner_radius=12 from the corpus DB.
        elements = spec["elements"]
        card_eid = next(
            (eid for eid, e in elements.items() if e.get("type") == "card"),
            None,
        )
        assert card_eid is not None
        card = elements[card_eid]
        # Universal template emits token refs, not literal corner_radius
        # from the DB. If the corpus path had fired, visual.corner_radius
        # would be the literal "12" / 12.
        if "visual" in card:
            assert card["visual"].get("corner_radius") not in ("12", 12, 12.0)
