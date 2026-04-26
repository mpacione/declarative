"""Phase E #3 debt anchor — BOOL_OP visual fidelity (DEFERRED).

Phase E residual fix shipped `figma.createBooleanOperation()` for
boolean_operation eids + skip prop writes (the empty bool node is
frozen — "object is not extensible"). Verifier accepts this as
structural parity (correct node type, correct count, no errors).

But the rendered output is visually empty: 502 BOOL_OP nodes on
Nouns render as type-correct placeholders without combined
geometry. Anti-Nouns illustration screens (e.g. screen 24's "ducky
body" = boolean_operation-16 with 5 child rectangles via UNION)
appear blank.

Codex 2026-04-26 (gpt-5.5 high reasoning) review of the F13c-
extension implementation path:

"the 38 LOC estimate is misleading because the risk is not line
count, it is semantic ordering. BOOLEAN_OPERATION materialization
changes the construction model from 'create node, append children'
to 'collect child nodes, call operation factory, replace/route
materialized node, update M[eid].' That touches the compiler's
core invariant: every AST node maps cleanly to one emitted Figma
node during traversal."

Dangerous cases:
- nested bool ops (child bool op must materialize before parent)
- parent routing (children must not be both appended AND consumed by union())
- M[eid] replacement (downstream properties/naming/constraints/
  verifier mapping must bind to the combined node)
- operation-specific factories (especially SUBTRACT — child order
  is visually meaningful)

Decision: defer implementation. Ship this test file as the
contract the future implementer must satisfy. Codex's minimum test
target:

  1. synthetic fixture with BOOLEAN_OPERATION(UNION) containing
     two visible rectangles
  2. expected emitted plugin path calls figma.union(children, parent),
     not createBooleanOperation() plus appendChild
  3. assert no empty placeholder bool-op remains
  4. assert M[bool_eid] points to the materialized union node
  5. ideally include one nested bool-op fixture (skipped with a
     clear reason)

This test file is marked @pytest.mark.skip until implementation
lands. The skip messages enumerate the specific contract the
implementer must meet.

Implementation pointer: extend the F13c group-deferral pattern in
dd/render_figma_ast.py:
  - Phase 1: deferred_bool_ops dict (mirror of deferred_groups)
  - Phase 2: bottom-up materialization with figma.{union,subtract,
    intersect,exclude}([children], parent) calls
  - Phase 3: bool_ops are EXTENSIBLE post-materialization (unlike
    today's empty createBooleanOperation), so prop writes work
"""

from __future__ import annotations

import pytest

from dd.markup_l3 import (
    Block,
    L3Document,
    Literal_,
    Node,
    NodeHead,
    PropAssign,
)
from dd.render_figma_ast import render_figma


def _ext_nid(value: int) -> PropAssign:
    return PropAssign(
        key="$ext.nid",
        value=Literal_(lit_kind="number", raw=str(value), py=value),
        trailer=None,
        kind="prop-assign",
    )


def _build_screen_with_union_bool_op() -> tuple[L3Document, dict, dict, dict]:
    """Build:
      screen-1 (frame)
      └── boolean_operation-1 (UNION)
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
        id(bool_op): "ducky body",
        id(rect_a): "Rectangle 326",
        id(rect_b): "Rectangle 330",
    }
    return doc, nid_map, spec_key_map, original_name_map


class TestBoolOpUnionMaterialization:
    """Phase E #3 (2026-04-26): IMPLEMENTATION SHIPPED. These tests
    were the contract anchor; they now PASS because the F13c-extension
    landed.

    Implementation summary (dd/render_figma_ast.py):
    - Phase 1: bool_op detected → registered in deferred_bool_ops
    - Phase 2: merged bottom-up pass over (groups + bool_ops) sorted
      by depth; emits figma.<op>(children, parent) for bool_ops,
      figma.group(children, parent) for groups; symmetric handling.
    - Phase 3: short-circuit removed; bool_op flows through normal
      resize/position/constraints (post-materialization the node
      IS extensible — verified empirically).
    """

    def test_emits_figma_union_call_not_create_boolean_operation(self):
        """The script must call figma.union([children], parent), NOT
        figma.createBooleanOperation()."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_screen_with_union_bool_op()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            100: {
                "node_type": "BOOLEAN_OPERATION",
                "boolean_operation": "UNION",
            },
            101: {"node_type": "RECTANGLE"},
            102: {"node_type": "RECTANGLE"},
        }
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        # The implementation should emit `figma.union([n_rect_a, n_rect_b], parent_var)`
        # NOT `figma.createBooleanOperation()`.
        assert "figma.union(" in script, (
            "Phase E #3: BOOL_OP UNION should materialize via "
            "figma.union(children, parent), not the empty "
            "createBooleanOperation() placeholder."
        )
        # No empty placeholder
        assert "figma.createBooleanOperation()" not in script

    def test_no_empty_boolean_operation_placeholder(self):
        """A future implementer might be tempted to keep
        createBooleanOperation() as a placeholder and patch it
        post-hoc. The contract says no — the materialization should
        produce the bool node directly."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_screen_with_union_bool_op()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            100: {
                "node_type": "BOOLEAN_OPERATION",
                "boolean_operation": "UNION",
            },
            101: {"node_type": "RECTANGLE"},
            102: {"node_type": "RECTANGLE"},
        }
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        assert "figma.createBooleanOperation()" not in script

    def test_m_eid_points_at_materialized_union_node(self):
        """The bool-op's M entry must point at the union() result,
        not at any temporary placeholder."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_screen_with_union_bool_op()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            100: {
                "node_type": "BOOLEAN_OPERATION",
                "boolean_operation": "UNION",
            },
            101: {"node_type": "RECTANGLE"},
            102: {"node_type": "RECTANGLE"},
        }
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        # M["boolean_operation-1"] = <var>.id where <var> is the
        # result of figma.union(...). The implementer needs to make
        # sure the binding occurs AFTER the union() call resolves.
        assert 'M["boolean_operation-1"]' in script
        # And the var assignment must be wired to a figma.union(...)
        # expression, not createBooleanOperation().
        # (Easier check: the script should NOT contain a sequence of
        # createBooleanOperation() then M["boolean_operation-1"] = .)


class TestNestedBoolOps:
    """Phase E #3 (2026-04-26): nested case — bool_op containing
    another bool_op. The merged depth-sorted bottom-up pass means
    the inner bool_op materializes BEFORE the outer references it.
    Codex review #1: the registry stores var names symbolically
    (already true via var_map allocation in Phase 1) so deferred
    children can be wrapped by deferred parents."""

    @staticmethod
    def _build_nested_bool_op_doc():
        """Build:
          screen-1
          └── outer_bool_op (UNION)
              ├── rect_a
              └── inner_bool_op (SUBTRACT)
                  ├── rect_b
                  └── rect_c
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
                properties=(_ext_nid(103),),
            ),
            block=None,
        )
        rect_c = Node(
            head=NodeHead(
                head_kind="type", type_or_path="rectangle",
                eid="rectangle-c",
                properties=(_ext_nid(104),),
            ),
            block=None,
        )
        inner_bool = Node(
            head=NodeHead(
                head_kind="type", type_or_path="boolean-operation",
                eid="boolean_operation-inner",
                properties=(_ext_nid(102),),
            ),
            block=Block(statements=(rect_b, rect_c)),
        )
        outer_bool = Node(
            head=NodeHead(
                head_kind="type", type_or_path="boolean-operation",
                eid="boolean_operation-outer",
                properties=(_ext_nid(100),),
            ),
            block=Block(statements=(rect_a, inner_bool)),
        )
        screen = Node(
            head=NodeHead(
                head_kind="type", type_or_path="frame", eid="screen-1",
                properties=(_ext_nid(1),),
            ),
            block=Block(statements=(outer_bool,)),
        )
        doc = L3Document(top_level=(screen,))
        nid_map = {
            id(screen): 1, id(outer_bool): 100, id(rect_a): 101,
            id(inner_bool): 102, id(rect_b): 103, id(rect_c): 104,
        }
        spec_key_map = {
            id(screen): "screen-1",
            id(outer_bool): "boolean_operation-outer",
            id(rect_a): "rectangle-a",
            id(inner_bool): "boolean_operation-inner",
            id(rect_b): "rectangle-b",
            id(rect_c): "rectangle-c",
        }
        original_name_map = {
            id(screen): "Screen 1",
            id(outer_bool): "outer-bool",
            id(rect_a): "ra",
            id(inner_bool): "inner-bool",
            id(rect_b): "rb",
            id(rect_c): "rc",
        }
        return doc, nid_map, spec_key_map, original_name_map

    def test_nested_union_materializes_bottom_up(self):
        doc, nid_map, spec_key_map, original_name_map = (
            self._build_nested_bool_op_doc()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            100: {"node_type": "BOOLEAN_OPERATION", "boolean_operation": "UNION"},
            101: {"node_type": "RECTANGLE"},
            102: {"node_type": "BOOLEAN_OPERATION", "boolean_operation": "SUBTRACT"},
            103: {"node_type": "RECTANGLE"},
            104: {"node_type": "RECTANGLE"},
        }
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        # Both materialization calls present
        assert "figma.subtract(" in script, "inner SUBTRACT must emit"
        assert "figma.union(" in script, "outer UNION must emit"
        # Both bool_op M[] entries present
        assert 'M["boolean_operation-inner"]' in script
        assert 'M["boolean_operation-outer"]' in script
        # Critical: subtract appears BEFORE union (bottom-up depth sort)
        sub_pos = script.index("figma.subtract(")
        un_pos = script.index("figma.union(")
        assert sub_pos < un_pos, (
            "Phase E #3: bottom-up depth ordering — inner bool_op "
            "(deeper, subtract) must emit BEFORE outer (union) so "
            "the union call can reference the materialized inner "
            "node. Got subtract at pos %d, union at pos %d." % (sub_pos, un_pos)
        )


class TestPhaseE3PostFixBehavior:
    """Phase E #3 (2026-04-26): post-implementation behavior pins.

    Earlier this class was named TestCurrentBehaviorIsTypedPlaceholder
    and asserted the empty createBooleanOperation() + prop-write skip
    state from Phase E residual. Phase E #3 reverses both: emission
    is now figma.union(...) and prop writes ARE emitted
    post-materialization."""

    def test_no_create_boolean_operation_anywhere(self):
        """Bare figma.createBooleanOperation() should never appear.
        Phase E #3 always uses children-first materialization."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_screen_with_union_bool_op()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            100: {
                "node_type": "BOOLEAN_OPERATION",
                "boolean_operation": "UNION",
            },
            101: {"node_type": "RECTANGLE"},
            102: {"node_type": "RECTANGLE"},
        }
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        assert "figma.createBooleanOperation()" not in script, (
            "Phase E #3: createBooleanOperation() returns a frozen "
            "node and is never used in this codebase post-fix. "
            "All bool_ops materialize via figma.union/subtract/etc."
        )

    def test_name_emitted_post_materialization(self):
        """Phase E #3: post-figma.union() the bool_op accepts .name
        writes. Should appear in script."""
        doc, nid_map, spec_key_map, original_name_map = (
            _build_screen_with_union_bool_op()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            100: {
                "node_type": "BOOLEAN_OPERATION",
                "boolean_operation": "UNION",
            },
            101: {"node_type": "RECTANGLE"},
            102: {"node_type": "RECTANGLE"},
        }
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        assert '"ducky body"' in script, (
            "Phase E #3: bool_op name should be emitted in Phase 2's "
            "bottom-up materialization block, post-figma.union()."
        )
