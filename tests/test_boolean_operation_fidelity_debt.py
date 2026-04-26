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


@pytest.mark.skip(
    reason=(
        "Phase E #3 deferred. Implementation requires F13c-extension "
        "to BOOL_OP — touches child materialization + node mapping "
        "semantics, not a property addition. See module docstring."
    ),
)
class TestBoolOpUnionMaterialization:
    """The contract a future implementer must satisfy."""

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


@pytest.mark.skip(
    reason=(
        "Phase E #3 nested case. Even harder: child bool-op must "
        "materialize before parent UNION. Implementer should target "
        "this case once flat case works."
    ),
)
class TestNestedBoolOps:
    """Nested case: BOOL_OP containing another BOOL_OP. The inner
    must materialize first (bottom-up), then the outer can union
    over the inner's result."""

    def test_nested_union_materializes_bottom_up(self):
        # Synthetic: outer UNION(rect_a, inner SUBTRACT(rect_b, rect_c))
        pytest.skip("contract-only; implementation pending Phase E #3")


class TestCurrentBehaviorIsTypedPlaceholder:
    """Pin the CURRENT behavior so the debt is visible. These tests
    PASS today; they're meant to fail when the implementation lands
    (or to be inverted to expect the new behavior)."""

    def test_current_emits_create_boolean_operation(self):
        """As of Phase E residual fix: BOOL_OP eids dispatch to
        figma.createBooleanOperation() (not figma.union()). When
        Phase E #3 implementation lands, this test should fail and
        be inverted to expect figma.union()."""
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
        # Today's state: createBooleanOperation() IS emitted.
        assert "figma.createBooleanOperation()" in script, (
            "When this test fails, the Phase E #3 implementation "
            "has landed — invert the assertion to expect "
            "figma.union(...) instead."
        )

    def test_current_skips_prop_writes_on_bool_op(self):
        """Today's BOOL_OP path emits no name/fills/etc writes
        (the frozen-node skip from Phase E residual). When #3
        lands, the materialized bool op is extensible and prop
        writes should fire."""
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
        # Today: no .name = "ducky body" line for the bool_op.
        assert '"ducky body"' not in script, (
            "If this fails, the Phase E #3 implementation lands and "
            "prop writes are emitted on the materialized bool op. "
            "Update the test or invert the assertion."
        )
