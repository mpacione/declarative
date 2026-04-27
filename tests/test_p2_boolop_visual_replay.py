"""P2 — bool-op visual replay post-materialization.

Phase: forensic-audit-2 fix sprint, P2. The audit (finding 2,
CONFIRMED via direct source read of dd/render_figma_ast.py:939, 1896)
found that BOOLEAN_OPERATION nodes skip ``_emit_visual`` in the
Phase 1 main loop (``if etype == "boolean_operation": continue``).
The deferred materialization at lines ~1995-2009 emits
``figma.union/subtract/intersect/exclude([children], parent)``
followed only by ``name`` and ``M[]`` and z-order — visual props
(fills, strokes, effects, opacity, rotation, etc.) are never
replayed.

Symptom on the post-rextract Nouns sweep: 10 DRIFT screens with
``boolean_operation-N`` nodes rendered as ``#D9D9D9`` (Figma's
default placeholder grey) where the IR specified the actual color.
The bool_op was created correctly, but no ``n.fills = [...]`` line
ever ran.

Fix: after the figma.union/etc materialization (and after the M
assign), call ``_emit_visual`` with the bool_op's raw_visual to
replay every visual prop that the registry knows about.

The deferred bool_op bucket already carries ``element``, ``var``,
``node``, and ``raw_visual`` — everything the replay needs.
"""

from __future__ import annotations

from dd.markup_l3 import (
    Block, Literal_, L3Document, Node, NodeHead, PropAssign,
)
from dd.render_figma_ast import render_figma


def _ext_nid(value: int) -> PropAssign:
    return PropAssign(
        key="$ext.nid",
        value=Literal_(lit_kind="number", raw=str(value), py=value),
        trailer=None,
        kind="prop-assign",
    )


def _build_bool_op_with_solid_fill():
    """Build:
      screen-1 (frame)
      └── boolean_operation-1 (UNION) with fills=[{type:SOLID, color:#FFD74B}]
          ├── rectangle-a
          └── rectangle-b
    """
    rect_a = Node(
        head=NodeHead(
            head_kind="type", type_or_path="rectangle",
            eid="rectangle-a",
            properties=(_ext_nid(101),),
        ),
        block=None,
    )
    rect_b = Node(
        head=NodeHead(
            head_kind="type", type_or_path="rectangle",
            eid="rectangle-b",
            properties=(_ext_nid(102),),
        ),
        block=None,
    )
    bool_op = Node(
        head=NodeHead(
            head_kind="type", type_or_path="boolean-operation",
            eid="boolean_operation-1",
            properties=(_ext_nid(100),),
        ),
        block=Block(statements=(rect_a, rect_b)),
    )
    screen = Node(
        head=NodeHead(
            head_kind="type", type_or_path="frame",
            eid="screen-1",
            properties=(_ext_nid(1),),
        ),
        block=Block(statements=(bool_op,)),
    )
    doc = L3Document(top_level=(screen,))
    nid_map = {
        id(screen): 1,
        id(bool_op): 100,
        id(rect_a): 101,
        id(rect_b): 102,
    }
    spec_key_map = {
        id(screen): "screen-1",
        id(bool_op): "boolean_operation-1",
        id(rect_a): "rectangle-a",
        id(rect_b): "rectangle-b",
    }
    original_name_map = {
        id(screen): "Screen 1",
        id(bool_op): "filled bool",
        id(rect_a): "Rectangle 1",
        id(rect_b): "Rectangle 2",
    }
    return doc, nid_map, spec_key_map, original_name_map


def _bool_op_db_visuals_with_solid_fill():
    """Build db_visuals where the bool_op carries a solid yellow fill."""
    import json as _json
    return {
        1: {"node_type": "FRAME"},
        100: {
            "node_type": "BOOLEAN_OPERATION",
            "boolean_operation": "UNION",
            "fills": _json.dumps([{
                "type": "SOLID",
                "visible": True,
                "color": {"r": 1.0, "g": 0.843, "b": 0.294, "a": 1.0},
            }]),
        },
        101: {"node_type": "RECTANGLE"},
        102: {"node_type": "RECTANGLE"},
    }


class TestBoolOpVisualReplayFills:
    """The headline fix — bool_ops with solid fills must emit the
    fill assignment after figma.union materialization."""

    def test_solid_fill_emitted_for_bool_op(self):
        """The script must contain a fills assignment for the
        materialized bool_op variable. Pre-fix the fills line was
        never emitted; post-fix it lives between the figma.union
        result assignment and the next bool_op materialization."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_bool_op_with_solid_fill()
        )
        db_visuals = _bool_op_db_visuals_with_solid_fill()
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        # The fill should be emitted as a SOLID paint with the
        # specified color hex. Walking up from the figma.union call,
        # the M["boolean_operation-1"] binding follows; AFTER that,
        # a fills assignment must appear.
        assert "figma.union(" in script
        # The fill color rounded to FFDA4B-ish (RGB 255, 215, 75 ≈
        # the source 1.0, 0.843, 0.294). format_js_value emits as
        # color: {r:1.0, g:0.843..., b:0.294...} — we just check
        # that a SOLID fill is somewhere in the script after
        # materialization.
        assert "fills = [" in script, (
            "P2: bool_op fill must be emitted after figma.union"
        )
        # SOLID type marker
        assert '"SOLID"' in script

    def test_fill_emitted_after_union_materialization(self):
        """Order check: the fill assignment must come AFTER the
        figma.union assignment (otherwise we'd be writing to a
        var that doesn't exist yet)."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_bool_op_with_solid_fill()
        )
        db_visuals = _bool_op_db_visuals_with_solid_fill()
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        union_pos = script.find("figma.union(")
        # The fills assignment for the bool_op must come AFTER union.
        # We can't pin the exact var name without inspecting var_map,
        # so search for any "fills = [" occurrence after union_pos.
        post_union_fill = script.find("fills = [", union_pos)
        assert union_pos > 0 and post_union_fill > union_pos, (
            "P2: fill emission must come after figma.union "
            f"materialization; union at {union_pos}, fills at "
            f"{post_union_fill}"
        )

    def test_no_fill_emitted_for_empty_bool_op(self):
        """Defensive: when the bool_op has no fills in IR, no
        fills assignment is emitted for the bool_op (avoids
        clobbering whatever the materialized node default has)."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_bool_op_with_solid_fill()
        )
        db_visuals = _bool_op_db_visuals_with_solid_fill()
        # Strip the fills from the bool_op
        db_visuals[100]["fills"] = None
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        # The bool_op may emit a default `fills = []` clear (per
        # the existing empty-case behavior at line 1078 of
        # render_figma_ast.py). What MUST NOT appear is the
        # SOLID color.
        assert '"SOLID"' not in script or script.count('"SOLID"') == 0


class TestBoolOpRegressions:
    """Defensive guards — P2 must not regress prior bool_op behavior."""

    def test_union_call_still_present(self):
        """P2 only adds the visual replay; figma.union must still be
        emitted as the materialization primitive."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_bool_op_with_solid_fill()
        )
        db_visuals = _bool_op_db_visuals_with_solid_fill()
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        assert "figma.union(" in script

    def test_m_assign_still_present(self):
        """The M["bool-op-eid"] = var.id binding must still emit."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_bool_op_with_solid_fill()
        )
        db_visuals = _bool_op_db_visuals_with_solid_fill()
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        assert 'M["boolean_operation-1"]' in script

    def test_name_assign_still_present(self):
        """The bool_op's name = "..." assignment must still emit."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_bool_op_with_solid_fill()
        )
        db_visuals = _bool_op_db_visuals_with_solid_fill()
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        assert 'name = "filled bool"' in script
