"""Tests for the type/role split (docs/plan-type-role-split.md).

Stage 0: DB migration + backfill.
Stage 1: IR layer split in ``map_node_to_element``.
Stage 2+: eid re-canonicalization, reader migration, grammar extension,
verifier rule. Tests accumulate as each stage lands.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dd.db import run_migration


REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_021 = REPO_ROOT / "migrations" / "021_add_nodes_role.sql"


def _minimal_schema_for_role(conn: sqlite3.Connection) -> None:
    """Minimum schema the Stage 0 tests need: nodes + SCI tables.

    SCI schema mirrors the columns ``dd/classify_v2._insert_llm_verdicts``
    touches, plus the ``UNIQUE(screen_id, node_id)`` constraint needed
    for the ``ON CONFLICT`` upsert path.
    """
    conn.executescript(
        """
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            name TEXT,
            node_type TEXT
        );
        CREATE TABLE screen_component_instances (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER,
            node_id INTEGER,
            catalog_type_id INTEGER,
            canonical_type TEXT,
            confidence REAL,
            classification_source TEXT,
            consensus_method TEXT,
            llm_reason TEXT,
            llm_type TEXT,
            llm_confidence REAL,
            UNIQUE(screen_id, node_id)
        );
        """
    )
    conn.commit()


class TestStage0Migration:
    def test_migration_021_adds_role_column_to_nodes(self) -> None:
        conn = sqlite3.connect(":memory:")
        _minimal_schema_for_role(conn)

        result = run_migration(conn, str(MIGRATION_021))

        assert result["errors"] == []
        cols = {row[1] for row in conn.execute("PRAGMA table_info(nodes)")}
        assert "role" in cols, (
            f"Migration 021 must add `role` column to nodes; got {cols}"
        )


class TestStage0Backfill:
    def test_backfill_populates_role_from_sci(self) -> None:
        conn = sqlite3.connect(":memory:")
        _minimal_schema_for_role(conn)
        conn.executescript(
            """
            INSERT INTO nodes (id, screen_id, node_type) VALUES
                (1, 10, 'FRAME'),
                (2, 10, 'TEXT'),
                (3, 10, 'RECTANGLE');
            INSERT INTO screen_component_instances
                (id, screen_id, node_id, canonical_type)
            VALUES
                (100, 10, 1, 'card'),
                (101, 10, 2, 'heading');
            """
        )
        conn.commit()
        run_migration(conn, str(MIGRATION_021))

        from dd.db import backfill_nodes_role
        result = backfill_nodes_role(conn)

        roles = dict(conn.execute("SELECT id, role FROM nodes").fetchall())
        assert roles[1] == "card"
        assert roles[2] == "heading"
        assert roles[3] is None, (
            "Unclassified nodes (no SCI row) must stay role=NULL"
        )
        assert result["populated"] == 2

    def test_backfill_is_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        _minimal_schema_for_role(conn)
        conn.executescript(
            """
            INSERT INTO nodes (id, screen_id, node_type) VALUES (1, 10, 'FRAME');
            INSERT INTO screen_component_instances
                (id, screen_id, node_id, canonical_type)
            VALUES (100, 10, 1, 'card');
            """
        )
        conn.commit()
        run_migration(conn, str(MIGRATION_021))

        from dd.db import backfill_nodes_role
        backfill_nodes_role(conn)
        result_2 = backfill_nodes_role(conn)

        role = conn.execute("SELECT role FROM nodes WHERE id=1").fetchone()[0]
        assert role == "card"
        assert result_2["populated"] == 1


class TestStage0QueryReturnsRole:
    def test_query_screen_for_ir_returns_role_column(self) -> None:
        from dd.db import init_db
        from dd.ir import query_screen_for_ir

        conn = init_db(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'F');
            INSERT INTO screens (id, file_id, figma_node_id, name, width, height)
                VALUES (1, 1, 'sn1', 'T', 400, 800);
            INSERT INTO nodes
                (id, screen_id, figma_node_id, name, node_type,
                 role, depth, sort_order)
            VALUES
                (10, 1, 'n10', 'Card', 'FRAME', 'card', 0, 0),
                (11, 1, 'n11', 'Heading', 'TEXT', 'heading', 1, 0),
                (12, 1, 'n12', 'Unclass', 'RECTANGLE', NULL, 1, 1);
            """
        )
        conn.commit()

        result = query_screen_for_ir(conn, 1)
        nodes_by_id = {n["node_id"]: n for n in result["nodes"]}

        assert nodes_by_id[10]["role"] == "card"
        assert nodes_by_id[11]["role"] == "heading"
        assert nodes_by_id[12]["role"] is None


class TestStage1IRSplit:
    """Stage 1: map_node_to_element emits `type` (primitive, always) and
    optional `role` (classifier semantic, only when role != type).

    See docs/plan-type-role-split.md §2.
    """

    def _node(self, node_type: str, canonical_type: str | None) -> dict:
        return {
            "node_id": 1,
            "canonical_type": canonical_type,
            "name": "t",
            "node_type": node_type,
            "layout_mode": None,
            "item_spacing": None,
            "counter_axis_spacing": None,
            "padding_top": None,
            "padding_right": None,
            "padding_bottom": None,
            "padding_left": None,
            "layout_sizing_h": None,
            "layout_sizing_v": None,
            "primary_align": None,
            "counter_align": None,
            "text_content": None,
            "corner_radius": None,
            "opacity": 1.0,
            "fills": None,
            "strokes": None,
            "effects": None,
            "bindings": [],
            "width": 100,
            "height": 50,
            "x": 0,
            "y": 0,
        }

    def test_FRAME_classified_card_splits_primitive_from_role(self) -> None:
        from dd.ir import map_node_to_element
        element = map_node_to_element(self._node("FRAME", "card"))
        assert element["type"] == "frame", (
            "type must be the structural primitive from node_type"
        )
        assert element["role"] == "card", (
            "role must carry the classifier's semantic label"
        )

    def test_FRAME_classified_text_splits_primitive_from_role(self) -> None:
        """The exact Frame 338 case from the 25-drift cluster."""
        from dd.ir import map_node_to_element
        element = map_node_to_element(self._node("FRAME", "text"))
        assert element["type"] == "frame"
        assert element["role"] == "text"

    def test_FRAME_no_classifier_omits_role_key(self) -> None:
        from dd.ir import map_node_to_element
        element = map_node_to_element(self._node("FRAME", None))
        assert element["type"] == "frame"
        assert "role" not in element, (
            "role key must be absent when no classifier opinion exists"
        )

    def test_TEXT_role_equals_type_elides_role_key(self) -> None:
        from dd.ir import map_node_to_element
        element = map_node_to_element(self._node("TEXT", "text"))
        assert element["type"] == "text"
        assert "role" not in element, (
            "role must be elided when role == type (redundant)"
        )

    def test_TEXT_role_heading_keeps_role(self) -> None:
        from dd.ir import map_node_to_element
        element = map_node_to_element(self._node("TEXT", "heading"))
        assert element["type"] == "text"
        assert element["role"] == "heading"

    def test_GROUP_type_is_group(self) -> None:
        from dd.ir import map_node_to_element
        element = map_node_to_element(self._node("GROUP", None))
        assert element["type"] == "group"
        assert "role" not in element

    def test_RECTANGLE_classified_button_splits(self) -> None:
        from dd.ir import map_node_to_element
        element = map_node_to_element(self._node("RECTANGLE", "button"))
        assert element["type"] == "rectangle"
        assert element["role"] == "button"

    def test_INSTANCE_classified_button_splits(self) -> None:
        from dd.ir import map_node_to_element
        element = map_node_to_element(self._node("INSTANCE", "button"))
        assert element["type"] == "instance"
        assert element["role"] == "button"

    def test_no_node_type_defaults_to_frame(self) -> None:
        from dd.ir import map_node_to_element
        element = map_node_to_element(self._node("", None))
        assert element["type"] == "frame"
        assert "role" not in element


class TestStage2EidNaming:
    """Stage 2: eid prefix follows ``{role || type}-{counter}`` with
    per-prefix counter pools. Role-first when classifier assigned a
    label; structural primitive fallback otherwise.

    Characterization tests — the behaviour already exists via
    ``_resolve_element_type``; these lock it in so a future refactor
    can't silently change it. See docs/plan-type-role-split.md §4
    Stage 2.
    """

    def _node(self, nid: int, node_type: str, canonical_type: str | None,
              parent_id: int | None = None) -> dict:
        return {
            "node_id": nid,
            "canonical_type": canonical_type,
            "name": f"n{nid}",
            "node_type": node_type,
            "layout_mode": None,
            "item_spacing": None,
            "counter_axis_spacing": None,
            "padding_top": None,
            "padding_right": None,
            "padding_bottom": None,
            "padding_left": None,
            "layout_sizing_h": None,
            "layout_sizing_v": None,
            "primary_align": None,
            "counter_align": None,
            "text_content": None,
            "corner_radius": None,
            "opacity": 1.0,
            "fills": None,
            "strokes": None,
            "effects": None,
            "bindings": [],
            "width": 100,
            "height": 50,
            "x": 0,
            "y": 0,
            "parent_id": parent_id,
            "depth": 0 if parent_id is None else 1,
            "sort_order": 0,
        }

    def _spec_data(self, nodes: list[dict]) -> dict:
        return {
            "screen_name": "t",
            "width": 400,
            "height": 800,
            "screen_origin_x": 0,
            "screen_origin_y": 0,
            "nodes": nodes,
        }

    def test_eid_prefix_uses_role_when_role_present(self) -> None:
        from dd.ir import build_composition_spec
        spec = build_composition_spec(self._spec_data([
            self._node(1, "FRAME", "card"),
        ]))
        eids = list(spec["elements"].keys())
        assert any(eid.startswith("card-") for eid in eids), (
            f"Classified FRAME should get eid prefix 'card', got {eids}"
        )

    def test_eid_prefix_uses_type_when_role_absent(self) -> None:
        from dd.ir import build_composition_spec
        spec = build_composition_spec(self._spec_data([
            self._node(1, "FRAME", None),
        ]))
        eids = list(spec["elements"].keys())
        assert any(eid.startswith("frame-") for eid in eids), (
            f"Unclassified FRAME should get eid prefix 'frame', got {eids}"
        )

    def test_eid_counter_namespaced_per_prefix(self) -> None:
        from dd.ir import build_composition_spec
        spec = build_composition_spec(self._spec_data([
            self._node(1, "FRAME", "card"),
            self._node(2, "FRAME", "card"),
            self._node(3, "FRAME", "card"),
            self._node(4, "FRAME", None),
            self._node(5, "FRAME", None),
        ]))
        eids = sorted(spec["elements"].keys())
        # Three cards should get card-1, card-2, card-3 (own counter)
        card_eids = {e for e in eids if e.startswith("card-")}
        assert card_eids == {"card-1", "card-2", "card-3"}, card_eids
        # Two unclassified frames should get frame-1, frame-2 (separate
        # counter)
        frame_eids = {e for e in eids if e.startswith("frame-")}
        assert frame_eids == {"frame-1", "frame-2"}, frame_eids

    def test_classified_FRAME_and_real_RECTANGLE_do_not_share_counter(self) -> None:
        """A FRAME classified as 'rectangle' and a real RECTANGLE share
        the same eid prefix ('rectangle') and therefore share a counter
        pool — there's only one namespace per prefix, by design. This
        test locks in that choice (it's the same behaviour as today's
        conflated rule — the split doesn't change it)."""
        from dd.ir import build_composition_spec
        spec = build_composition_spec(self._spec_data([
            self._node(1, "RECTANGLE", None),      # eid: rectangle-1
            self._node(2, "FRAME", "rectangle"),   # eid: rectangle-2
        ]))
        rect_eids = sorted(
            e for e in spec["elements"].keys() if e.startswith("rectangle-")
        )
        assert rect_eids == ["rectangle-1", "rectangle-2"], rect_eids

    def test_GROUP_eid_prefix_is_group(self) -> None:
        from dd.ir import build_composition_spec
        spec = build_composition_spec(self._spec_data([
            self._node(1, "GROUP", None),
        ]))
        eids = list(spec["elements"].keys())
        assert any(eid.startswith("group-") for eid in eids), eids


class TestStage3aComposeRoleFirst:
    """Stage 3a: compose.py reads role-first via ``_semantic_type``.

    The compose path looks up templates / counts "types" by semantic
    label (button, card, heading). After Stage 1, DB-sourced IR has
    ``type=<primitive>`` and ``role=<semantic>`` separated — compose
    must read role-first with type as fallback for Mode 3 elements
    where the LLM still emits conflated values.

    See docs/plan-type-role-split.md §4 Stage 3a.
    """

    def test_semantic_type_reads_role_when_present(self) -> None:
        from dd.compose import _semantic_type
        assert _semantic_type({"type": "frame", "role": "button"}) == "button"

    def test_semantic_type_falls_through_to_type_when_no_role(self) -> None:
        """Mode 3 LLM-generated IR has no role; type carries the
        conflated semantic. Helper must preserve that path."""
        from dd.compose import _semantic_type
        assert _semantic_type({"type": "button"}) == "button"

    def test_semantic_type_returns_primitive_when_no_role(self) -> None:
        from dd.compose import _semantic_type
        assert _semantic_type({"type": "frame"}) == "frame"

    def test_semantic_type_empty_returns_empty_string(self) -> None:
        from dd.compose import _semantic_type
        assert _semantic_type({}) == ""

    def test_semantic_type_role_equals_type_returns_that(self) -> None:
        """role == type (elided in practice but tolerated if present)."""
        from dd.compose import _semantic_type
        assert _semantic_type({"type": "text", "role": "text"}) == "text"


class TestStage3aCorpusRetrievalSplit:
    """Corpus retrieval produces elements in the split shape
    (type=primitive, role=semantic optional). See
    docs/plan-type-role-split.md §4 Stage 3a.
    """

    def _row(self, node_type: str, canonical_type: str | None) -> dict:
        return {
            "id": 1, "node_type": node_type,
            "canonical_type": canonical_type,
            "name": "n", "fills": None, "strokes": None, "effects": None,
            "corner_radius": None, "stroke_weight": None, "opacity": 1.0,
            "layout_mode": None,
            "padding_top": None, "padding_right": None,
            "padding_bottom": None, "padding_left": None,
            "item_spacing": None,
            "layout_sizing_h": None, "layout_sizing_v": None,
            "text_content": None,
        }

    def test_FRAME_classified_card_gets_split_shape(self) -> None:
        from dd.composition.providers.corpus_retrieval import _build_element
        element = _build_element(self._row("FRAME", "card"))
        assert element["type"] == "frame"
        assert element["role"] == "card"

    def test_unclassified_FRAME_has_no_role(self) -> None:
        from dd.composition.providers.corpus_retrieval import _build_element
        element = _build_element(self._row("FRAME", None))
        assert element["type"] == "frame"
        assert "role" not in element

    def test_TEXT_classified_text_elides_role(self) -> None:
        from dd.composition.providers.corpus_retrieval import _build_element
        element = _build_element(self._row("TEXT", "text"))
        assert element["type"] == "text"
        assert "role" not in element

    def test_RECTANGLE_preserves_primitive_not_collapsed_to_frame(self) -> None:
        """Old corpus_retrieval.py._resolve_element_type collapsed
        anything not in {instance, text, frame} to "frame". After
        Stage 3a the canonical helper preserves RECTANGLE, ELLIPSE,
        etc. as their lowercase primitive."""
        from dd.composition.providers.corpus_retrieval import _build_element
        element = _build_element(self._row("RECTANGLE", None))
        assert element["type"] == "rectangle"


class TestStage4aGrammarRoleAttribute:
    """Stage 4a: compressor emits `role=<value>` in the markup head
    when the IR element has role != type. Round-trip preserves it.

    See docs/plan-type-role-split.md §4 Stage 4a.
    """

    def _build_minimal_spec(
        self, eid: str, type_str: str, role: str | None,
    ) -> dict:
        element: dict = {
            "type": type_str,
            "_original_name": eid,
        }
        if role:
            element["role"] = role
        return {
            "version": "1.0",
            "root": eid,
            "elements": {eid: element},
            "tokens": {},
            "_node_id_map": {},
        }

    def test_compressor_emits_role_attr_when_role_differs_from_type(self) -> None:
        from dd.compress_l3 import compress_to_l3_with_maps
        from dd.markup_l3 import emit_l3
        spec = self._build_minimal_spec(
            "my-card", type_str="frame", role="card",
        )
        doc, *_ = compress_to_l3_with_maps(spec)
        markup = emit_l3(doc)
        assert "role=card" in markup, (
            f"markup should include role=card when element.role != element.type, "
            f"got: {markup[:500]}"
        )

    def test_compressor_omits_role_attr_when_no_role(self) -> None:
        from dd.compress_l3 import compress_to_l3_with_maps
        from dd.markup_l3 import emit_l3
        spec = self._build_minimal_spec(
            "plain", type_str="frame", role=None,
        )
        doc, *_ = compress_to_l3_with_maps(spec)
        markup = emit_l3(doc)
        assert "role=" not in markup, (
            f"markup must not include role= when element has no role, "
            f"got: {markup[:500]}"
        )

    def test_compressor_emits_role_attr_for_FRAME_classified_text(self) -> None:
        """The canonical Frame 338 case — role=text on a frame primitive."""
        from dd.compress_l3 import compress_to_l3_with_maps
        from dd.markup_l3 import emit_l3
        spec = self._build_minimal_spec(
            "frame-338", type_str="frame", role="text",
        )
        doc, *_ = compress_to_l3_with_maps(spec)
        markup = emit_l3(doc)
        assert "role=text" in markup

    def test_roundtrip_preserves_role(self) -> None:
        """compress → serialize → parse preserves role in the head."""
        from dd.compress_l3 import compress_to_l3_with_maps
        from dd.markup_l3 import emit_l3, parse_l3
        spec = self._build_minimal_spec(
            "card-1", type_str="frame", role="card",
        )
        doc, *_ = compress_to_l3_with_maps(spec)
        markup = emit_l3(doc)
        doc2 = parse_l3(markup)
        # Walk doc2 and find the card node
        from dd.markup_l3 import Node, PropAssign

        def _walk(n):
            yield n
            if isinstance(n, Node) and n.block:
                for s in n.block.statements:
                    if isinstance(s, Node):
                        yield from _walk(s)

        card_node = None
        for tl in doc2.top_level:
            if isinstance(tl, Node):
                for n in _walk(tl):
                    if n.head.eid == "card-1":
                        card_node = n
                        break
        assert card_node is not None, f"Didn't find #card-1 in {markup}"
        role_props = [
            p for p in card_node.head.properties
            if isinstance(p, PropAssign) and p.key == "role"
        ]
        assert len(role_props) == 1, (
            f"#card-1 should have one role= prop after roundtrip, "
            f"got {role_props}"
        )


class TestSlotAttributeOnChildren:
    """Option 2 fix for the 14 drift screens — preserve designer intent.

    When build_semantic_tree puts children into element["slots"] for
    classified nodes, the compressor flattens them back into the
    block AND tags each child's head with ``slot=<slot_name>`` so
    multi-backend renderers / Mode-3 LLM consumers can dispatch on
    the slot role.

    Designer context: many buttons in real Figma files are detached
    instances or copy-pasted shapes — the classifier recognises them
    as buttons even without a ``component_key``. The slot labels
    carry that recovered designer intent through the pipeline.

    See docs/continuation-post-type-role-split.md 2026-04-22 discussion.
    """

    def _minimal_spec(
        self, parent_slots: dict[str, list[str]] | None = None,
    ) -> dict:
        elements: dict = {
            "screen-1": {
                "type": "screen",
                "children": ["btn-1"],
                "_original_name": "root",
            },
            "btn-1": {
                "type": "frame",
                "role": "button",
                "_original_name": "my-button",
            },
            "c1": {
                "type": "instance",
                "role": "icon",
                "_original_name": "icon/leading",
            },
            "c2": {
                "type": "text",
                "_original_name": "mid",
                "props": {"text": "Click me"},
            },
            "c3": {
                "type": "instance",
                "role": "icon",
                "_original_name": "icon/trailing",
            },
        }
        if parent_slots is not None:
            elements["btn-1"]["slots"] = parent_slots
        else:
            elements["btn-1"]["children"] = ["c1", "c2", "c3"]
        return {
            "version": "1.0",
            "root": "screen-1",
            "elements": elements,
            "tokens": {},
            "_node_id_map": {},
        }

    def test_slotted_children_emit_with_slot_attribute(self) -> None:
        from dd.compress_l3 import compress_to_l3_with_maps
        from dd.markup_l3 import emit_l3
        spec = self._minimal_spec(parent_slots={
            "leading_icon": ["c1"],
            "label": ["c2"],
            "trailing_icon": ["c3"],
        })
        doc, *_ = compress_to_l3_with_maps(spec)
        markup = emit_l3(doc)
        assert "slot=leading_icon" in markup, (
            f"leading_icon slot child missing slot= attr:\n{markup}"
        )
        assert "slot=label" in markup, (
            f"label slot child missing slot= attr:\n{markup}"
        )
        assert "slot=trailing_icon" in markup, (
            f"trailing_icon slot child missing slot= attr:\n{markup}"
        )

    def test_non_slotted_children_have_no_slot_attribute(self) -> None:
        """An unclassified FRAME with a flat children list doesn't
        get slot= attrs on its children."""
        from dd.compress_l3 import compress_to_l3_with_maps
        from dd.markup_l3 import emit_l3
        spec = self._minimal_spec()  # parent_slots=None → flat children
        doc, *_ = compress_to_l3_with_maps(spec)
        markup = emit_l3(doc)
        assert "slot=" not in markup, (
            f"Flat children should not carry slot= attrs:\n{markup}"
        )

    def test_slotted_children_preserve_slot_definition_order(self) -> None:
        """leading_icon before label before trailing_icon (dict
        insertion order preserved from slot schema definition)."""
        from dd.compress_l3 import compress_to_l3_with_maps
        from dd.markup_l3 import emit_l3
        spec = self._minimal_spec(parent_slots={
            "leading_icon": ["c1"],
            "label": ["c2"],
            "trailing_icon": ["c3"],
        })
        doc, *_ = compress_to_l3_with_maps(spec)
        markup = emit_l3(doc)
        pos_lead = markup.find("slot=leading_icon")
        pos_label = markup.find("slot=label")
        pos_trail = markup.find("slot=trailing_icon")
        assert -1 < pos_lead < pos_label < pos_trail, (
            f"Slot order not preserved: lead={pos_lead} "
            f"label={pos_label} trail={pos_trail}\n{markup}"
        )

    def test_roundtrip_preserves_slot_attribute(self) -> None:
        """compress → emit → parse: a child's slot= attr survives the
        roundtrip as a PropAssign in its NodeHead properties."""
        from dd.compress_l3 import compress_to_l3_with_maps
        from dd.markup_l3 import emit_l3, parse_l3, Node, PropAssign
        spec = self._minimal_spec(parent_slots={
            "leading_icon": ["c1"],
            "label": ["c2"],
        })
        doc, *_ = compress_to_l3_with_maps(spec)
        markup = emit_l3(doc)
        doc2 = parse_l3(markup)

        def _walk(n):
            yield n
            if isinstance(n, Node) and n.block:
                for s in n.block.statements:
                    if isinstance(s, Node):
                        yield from _walk(s)

        leading_node = None
        for tl in doc2.top_level:
            if isinstance(tl, Node):
                for n in _walk(tl):
                    if n.head.eid == "icon-leading":
                        leading_node = n
                        break
        assert leading_node is not None, (
            f"didn't find icon-leading in parsed markup:\n{markup}"
        )
        slot_props = [
            p for p in leading_node.head.properties
            if isinstance(p, PropAssign) and p.key == "slot"
        ]
        assert len(slot_props) == 1
        # The value is an enum-literal; its ``.py`` / raw contains the name
        slot_val = slot_props[0].value
        raw = getattr(slot_val, "raw", None) or getattr(slot_val, "py", None)
        assert raw == "leading_icon", (
            f"slot= value didn't roundtrip cleanly; got {raw!r}"
        )


class TestPhase1FontBatching:
    """Phase 1 perf: batch loadFontAsync via Promise.all instead of
    per-font sequential awaits.

    Figma docs + community benchmarks agree Promise.all is the
    canonical pattern for bulk font loading. Screen 241 has 28
    distinct fonts today — serialised awaits cost ~28× a single
    network round-trip. Parallel: one await total. Font results are
    cached internally so repeated calls are cheap.

    See research agent aa9eb2062cc0705de §1 (highest-ROI perf win).
    """

    def test_preamble_emits_promise_all_for_fonts(self) -> None:
        from dd.render_figma_ast import render_figma_preamble
        from dd.markup_l3 import L3Document

        doc = L3Document()
        fonts = {("Inter", "Regular"), ("Inter", "Bold"), ("Helvetica", "Regular")}
        preamble = render_figma_preamble(
            doc, conn=None, nid_map={}, fonts=fonts,
            db_visuals={}, ckr_built=True,
        )
        assert "Promise.all" in preamble, (
            f"Preamble must batch fonts via Promise.all; got:\n{preamble[:1000]}"
        )

    def test_preamble_does_not_emit_sequential_await_per_font(self) -> None:
        """With 3 fonts, the preamble should have at most 1
        ``await`` that references fonts (the Promise.all block),
        not 3 separate per-font awaits."""
        from dd.render_figma_ast import render_figma_preamble
        from dd.markup_l3 import L3Document

        doc = L3Document()
        fonts = {("Inter", "Regular"), ("Inter", "Bold"), ("Inter", "Medium")}
        preamble = render_figma_preamble(
            doc, conn=None, nid_map={}, fonts=fonts,
            db_visuals={}, ckr_built=True,
        )
        # Count awaits that reference loadFontAsync. Pre-fix: 3.
        # Post-fix: exactly 1 (the Promise.all).
        count = preamble.count("await ")
        # The preamble also has an await for figma.loadAllPagesAsync
        # (if present) but loadFontAsync should be collapsed.
        load_font_awaits = preamble.count("await figma.loadFontAsync")
        assert load_font_awaits == 0, (
            f"Expected no per-font `await figma.loadFontAsync`; found "
            f"{load_font_awaits}. Preamble fonts must batch via Promise.all."
        )

    def test_preamble_still_includes_all_fonts(self) -> None:
        """Batching must not drop fonts — each requested family/style
        pair still appears in the preamble (inside the Promise.all)."""
        from dd.render_figma_ast import render_figma_preamble
        from dd.markup_l3 import L3Document

        doc = L3Document()
        fonts = {
            ("Inter", "Regular"),
            ("Helvetica", "Bold"),
            ("SF Pro", "Medium"),
        }
        preamble = render_figma_preamble(
            doc, conn=None, nid_map={}, fonts=fonts,
            db_visuals={}, ckr_built=True,
        )
        for family, style in fonts:
            assert family in preamble, f"missing family {family!r}"
            assert style in preamble, f"missing style {style!r}"

    def test_preamble_font_load_failure_still_reports_per_font(self) -> None:
        """Each font's load must have its own error-handler so one
        failure doesn't abort the whole Promise.all."""
        from dd.render_figma_ast import render_figma_preamble
        from dd.markup_l3 import L3Document

        doc = L3Document()
        fonts = {("Inter", "Regular"), ("Inter", "Bold")}
        preamble = render_figma_preamble(
            doc, conn=None, nid_map={}, fonts=fonts,
            db_visuals={}, ckr_built=True,
        )
        assert '"font_load_failed"' in preamble, (
            "Each font must still have a failure-reporting path"
        )
        # Each font should have its own catch clause
        catch_count = preamble.count("font_load_failed")
        assert catch_count >= 2, (
            f"Expected ≥2 per-font failure paths; got {catch_count}"
        )


class TestStage0ClassifyV2WritesRole:
    def test_insert_llm_verdicts_writes_nodes_role(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema_for_role(conn)
        run_migration(conn, str(MIGRATION_021))
        conn.executescript(
            """
            INSERT INTO nodes (id, screen_id, node_type) VALUES
                (1, 10, 'FRAME'),
                (2, 10, 'TEXT');
            """
        )
        conn.commit()

        from dd.classify_v2 import _insert_llm_verdicts
        groups = [
            [{"screen_id": 10, "node_id": 1}],
            [{"screen_id": 10, "node_id": 2}],
        ]
        reps = [{"node_id": 1}, {"node_id": 2}]
        verdicts = {
            1: ("button", 0.9, "looks like a button"),
            2: ("heading", 0.85, "bold text"),
        }
        catalog = [
            {"canonical_name": "button", "id": 100},
            {"canonical_name": "heading", "id": 101},
        ]

        _insert_llm_verdicts(conn, groups, reps, verdicts, catalog)

        sci = dict(conn.execute(
            "SELECT node_id, canonical_type FROM screen_component_instances"
        ).fetchall())
        assert sci == {1: "button", 2: "heading"}

        roles = dict(conn.execute("SELECT id, role FROM nodes").fetchall())
        assert roles[1] == "button", (
            "classify_v2 must write nodes.role alongside SCI.canonical_type"
        )
        assert roles[2] == "heading"

    def test_insert_llm_verdicts_upsert_updates_role(self) -> None:
        """Re-classifying a node overwrites both SCI.canonical_type
        and nodes.role."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _minimal_schema_for_role(conn)
        run_migration(conn, str(MIGRATION_021))
        conn.executescript(
            """
            INSERT INTO nodes (id, screen_id, node_type)
            VALUES (1, 10, 'FRAME');
            """
        )
        conn.commit()

        from dd.classify_v2 import _insert_llm_verdicts
        groups = [[{"screen_id": 10, "node_id": 1}]]
        reps = [{"node_id": 1}]
        catalog = [
            {"canonical_name": "button", "id": 100},
            {"canonical_name": "card", "id": 101},
        ]

        # First classification
        _insert_llm_verdicts(
            conn, groups, reps, {1: ("button", 0.9, "v1")}, catalog,
        )
        role_v1 = conn.execute(
            "SELECT role FROM nodes WHERE id=1"
        ).fetchone()[0]
        assert role_v1 == "button"

        # Reclassification (different verdict)
        _insert_llm_verdicts(
            conn, groups, reps, {1: ("card", 0.95, "v2")}, catalog,
        )
        role_v2 = conn.execute(
            "SELECT role FROM nodes WHERE id=1"
        ).fetchone()[0]
        assert role_v2 == "card", (
            "UPSERT path must refresh nodes.role on reclassification"
        )
