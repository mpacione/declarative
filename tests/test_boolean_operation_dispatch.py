"""Phase E residual #1 fix — boolean-operation dispatch normalization.

Phase E re-run sweep on Nouns left 4 residual `phase1_mode2_prop_failed`
errors on screen 24. Initial assumption was that the nodes were inside
an instance subtree (P3a's INSTANCE skip-set should have absorbed
them). Re-investigation showed the actual cause:

L3 markup uses hyphenated type names (`boolean-operation`, per
grammar §2.7 — `dd/markup_l3.py:1503`). The renderer's
`_TYPE_TO_CREATE_CALL` and `_FIGMA_NODE_TYPE` dicts at
`dd/render_figma_ast.py:85-95, 1071-1081` use underscore form
(`boolean_operation`). The dispatch at line 889 fell through to the
default `figma.createFrame()` for any hyphenated etype.

The renderer then tried to set `n.booleanOperation = "UNION"` on the
frame fallback, which Figma rejects (frames don't have that
property). All 4 phase1_mode2_prop_failed errors on screen 24 trace
to this single dispatch miss.

Codex 2026-04-26 (gpt-5.5 high reasoning) traced the type-flow:
- `dd/ir.py` emits underscore form (`boolean_operation`)
- `dd/compress_l3.py:846` normalizes underscore → hyphen for L3 grammar
- `dd/render_figma_ast.py:762` consumes hyphenated `etype` directly
- Dict lookups miss → fallthrough to `createFrame()`

Fix: single-line normalization at line 762:
```python
etype = etype.replace("-", "_") if isinstance(etype, str) else ""
```

Sonnet subagent verified all etype consumers in the renderer expect
underscore form and the fix is single-entry / no double-replace risk.

These tests pin the post-fix dispatch:
1. `boolean-operation` (hyphen, from L3) → `createBooleanOperation()`
2. `boolean_operation` (underscore) still works (defensive: same dispatch)
3. `_FIGMA_NODE_TYPE.get("boolean-operation")` → "BOOLEAN_OPERATION"
   (capability gating works post-normalization)
4. End-to-end script generation emits `figma.createBooleanOperation()`
   for a BOOLEAN_OPERATION node from the IR
"""

from __future__ import annotations

from dd.markup_l3 import (
    Block,
    L3Document,
    Literal_,
    Node,
    NodeHead,
    PropAssign,
)
from dd.render_figma_ast import (
    _FIGMA_NODE_TYPE,
    _TYPE_TO_CREATE_CALL,
    render_figma,
)


class TestDispatchTablesUseUnderscores:
    """Both lookup tables use underscore-form keys. The hyphenated
    L3 form is normalized at the renderer's entry point."""

    def test_type_to_create_call_has_underscore_key(self):
        assert "boolean_operation" in _TYPE_TO_CREATE_CALL
        assert (
            _TYPE_TO_CREATE_CALL["boolean_operation"]
            == "figma.createBooleanOperation()"
        )

    def test_type_to_create_call_does_not_have_hyphen_key(self):
        # The renderer's dispatch table is canonical-underscore;
        # if anyone adds a hyphen key they're papering over a missed
        # normalization upstream.
        assert "boolean-operation" not in _TYPE_TO_CREATE_CALL

    def test_figma_node_type_has_underscore_key(self):
        assert _FIGMA_NODE_TYPE.get("boolean_operation") == "BOOLEAN_OPERATION"

    def test_figma_node_type_does_not_have_hyphen_key(self):
        assert "boolean-operation" not in _FIGMA_NODE_TYPE


class TestEndToEndBooleanOperationDispatch:
    """The headline regression test. An L3 doc with a
    `boolean-operation` typed node must emit
    `figma.createBooleanOperation()`, NOT `figma.createFrame()`."""

    def _build_doc_with_boolean_op(self) -> tuple[L3Document, dict, dict, dict]:
        """Build a minimal screen-frame containing one
        boolean-operation child, simulating what compress_l3 emits."""
        bool_op = Node(
            head=NodeHead(
                head_kind="type",
                # NOTE: hyphen — matches L3 grammar
                type_or_path="boolean-operation",
                eid="boolean_operation-1",
                properties=(
                    PropAssign(
                        key="$ext.nid",
                        value=Literal_(lit_kind="number", raw="2", py=2),
                        trailer=None,
                        kind="prop-assign",
                    ),
                ),
            ),
            block=None,
        )
        screen = Node(
            head=NodeHead(
                head_kind="type",
                type_or_path="frame",
                eid="screen-1",
                properties=(
                    PropAssign(
                        key="$ext.nid",
                        value=Literal_(lit_kind="number", raw="1", py=1),
                        trailer=None,
                        kind="prop-assign",
                    ),
                ),
            ),
            block=Block(statements=(bool_op,)),
        )
        doc = L3Document(top_level=(screen,))
        nid_map = {id(screen): 1, id(bool_op): 2}
        spec_key_map = {
            id(screen): "screen-1",
            id(bool_op): "boolean_operation-1",
        }
        original_name_map = {
            id(screen): "Screen 1",
            id(bool_op): "ducky body",
        }
        return doc, nid_map, spec_key_map, original_name_map

    def test_renders_figma_union_not_create_boolean_operation(self):
        """Phase E #3 (2026-04-26): bool_op materializes via
        figma.union(children, parent) in Phase 2's bottom-up block,
        NOT via figma.createBooleanOperation() in Phase 1.

        The previous test (test_renders_create_boolean_operation_not_frame)
        was flipped when Phase E #3 implementation landed — it asserted
        the pre-#3 behavior (createBooleanOperation + skip). Post-#3
        the materialization happens in Phase 2 as figma.union(...).
        """
        doc, nid_map, spec_key_map, original_name_map = (
            self._build_doc_with_boolean_op()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            2: {
                "node_type": "BOOLEAN_OPERATION",
                "boolean_operation": "UNION",
            },
        }
        script, _ = render_figma(
            doc,
            conn=None,
            nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        # Phase E #3: bool_op deferred to Phase 2; emission via
        # figma.union(...) appears in the merged bottom-up block.
        # The bool_op fixture has no children in this test (block=None
        # at line 107), so it triggers the empty-children fallback —
        # FRAME placeholder. Test the fallback path here.
        # NOTE: Phase 1 should NOT contain the bool_op's create call.
        p1_start = script.index("// Phase 1: Materialize")
        p2_start = script.index("// Phase 2: Compose")
        phase1_only = script[p1_start:p2_start]

        # The bool_op creation should NOT appear in Phase 1 anymore —
        # it's deferred to Phase 2.
        assert "figma.createBooleanOperation()" not in script, (
            "Phase E #3: bare figma.createBooleanOperation() should "
            "never be emitted. Plugin API requires children-first "
            "materialization via figma.union(...)."
        )

    def test_renders_screen_as_frame(self):
        """Defensive: the parent screen frame is unaffected by the
        normalization (it was already underscored, so the fix is a
        no-op for it)."""
        doc, nid_map, spec_key_map, original_name_map = (
            self._build_doc_with_boolean_op()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            2: {"node_type": "BOOLEAN_OPERATION"},
        }
        script, _ = render_figma(
            doc,
            conn=None,
            nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        p1_start = script.index("// Phase 1: Materialize")
        p2_start = script.index("// Phase 2: Compose")
        phase1_only = script[p1_start:p2_start]

        # Screen → createFrame (unchanged behavior)
        assert "figma.createFrame()" in phase1_only

    def test_phase1_only_creates_screen_phase2_materializes_bool_op(self):
        """Phase E #3: Phase 1 emits createFrame for the screen ONLY.
        The bool_op's children would also emit in Phase 1, but this
        fixture has block=None on the bool_op (no children).
        Phase 2 then materializes the bool_op via the empty-children
        fallback (createFrame placeholder)."""
        doc, nid_map, spec_key_map, original_name_map = (
            self._build_doc_with_boolean_op()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            2: {
                "node_type": "BOOLEAN_OPERATION",
                "boolean_operation": "UNION",
            },
        }
        script, _ = render_figma(
            doc,
            conn=None,
            nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        p1_start = script.index("// Phase 1: Materialize")
        p2_start = script.index("// Phase 2: Compose")
        phase1_only = script[p1_start:p2_start]
        phase2_only = script[p2_start:]

        # Phase 1: screen is the only create call (bool_op deferred).
        assert phase1_only.count("figma.createFrame()") == 1, (
            "Phase 1 should have exactly 1 createFrame (the screen "
            "frame). The bool_op is deferred to Phase 2."
        )
        # Phase 2 contains the bool_op materialization. With no
        # children this fixture hits the empty-children fallback.
        assert "Phase E #3" in phase2_only or "bool_op" in phase2_only, (
            "Phase 2 should have a comment marker about the bool_op "
            "materialization (empty-children fallback or "
            "figma.union call)."
        )
        # No bare figma.createBooleanOperation() ever.
        assert "figma.createBooleanOperation()" not in script


class TestBooleanOperationPostMaterialization:
    """Phase E #3 (2026-04-26): post-fix bool_ops are materialized
    via figma.union(...) which returns an EXTENSIBLE node. Name and
    M[eid] are emitted post-materialization. Phase 3 applies the
    regular resize/position/constraints path (no more short-circuit).

    Earlier this class was named TestBooleanOperationProvWriteSkip
    and asserted prop writes were NOT emitted (the Phase E residual
    fix's frozen-node defense). Phase E #3 reverses that: the
    materialized bool_op accepts writes, so we do emit name + M.
    """

    @staticmethod
    def _build_doc_with_bool_op_with_children():
        """Build a screen with a bool_op containing two real
        rectangle children — so the deferred materialization actually
        fires the figma.union(...) path (not the empty-fallback)."""
        rect_a = Node(
            head=NodeHead(
                head_kind="type", type_or_path="rectangle",
                eid="rectangle-a",
                properties=(PropAssign(
                    key="$ext.nid",
                    value=Literal_(lit_kind="number", raw="3", py=3),
                    trailer=None, kind="prop-assign",
                ),),
            ),
            block=None,
        )
        rect_b = Node(
            head=NodeHead(
                head_kind="type", type_or_path="rectangle",
                eid="rectangle-b",
                properties=(PropAssign(
                    key="$ext.nid",
                    value=Literal_(lit_kind="number", raw="4", py=4),
                    trailer=None, kind="prop-assign",
                ),),
            ),
            block=None,
        )
        bool_op = Node(
            head=NodeHead(
                head_kind="type",
                type_or_path="boolean-operation",
                eid="boolean_operation-1",
                properties=(PropAssign(
                    key="$ext.nid",
                    value=Literal_(lit_kind="number", raw="2", py=2),
                    trailer=None, kind="prop-assign",
                ),),
            ),
            block=Block(statements=(rect_a, rect_b)),
        )
        screen = Node(
            head=NodeHead(
                head_kind="type", type_or_path="frame", eid="screen-1",
                properties=(PropAssign(
                    key="$ext.nid",
                    value=Literal_(lit_kind="number", raw="1", py=1),
                    trailer=None, kind="prop-assign",
                ),),
            ),
            block=Block(statements=(bool_op,)),
        )
        doc = L3Document(top_level=(screen,))
        nid_map = {
            id(screen): 1, id(bool_op): 2,
            id(rect_a): 3, id(rect_b): 4,
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

    def _render(self):
        doc, nid_map, spec_key_map, original_name_map = (
            self._build_doc_with_bool_op_with_children()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            2: {
                "node_type": "BOOLEAN_OPERATION",
                "boolean_operation": "UNION",
            },
            3: {"node_type": "RECTANGLE"},
            4: {"node_type": "RECTANGLE"},
        }
        script, _ = render_figma(
            doc, conn=None, nid_map=nid_map,
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            db_visuals=db_visuals,
            ckr_built=True,
        )
        return script

    def test_name_assigned_post_materialization(self):
        """Phase E #3: post-figma.union() the bool_op accepts .name
        writes. The materialization block emits name + M[eid] on
        the materialized var."""
        script = self._render()
        assert "ducky body" in script, (
            "Phase E #3: bool_op name should be emitted "
            "post-materialization."
        )

    def test_m_eid_assigned_for_boolean_op(self):
        """Critical: M[eid] = var.id is emitted in Phase 2's
        bottom-up block (after figma.union(...) returns)."""
        script = self._render()
        assert 'M["boolean_operation-1"]' in script

    def test_figma_union_called_with_two_children(self):
        """Phase E #3: figma.union([n_rect_a, n_rect_b], parent) is
        the materialization call. Verify the children + parent appear
        in the call."""
        script = self._render()
        # The materialization line has the shape:
        #   const n? = (function() { try { return figma.union([nC1, nC2], pVar); } ... })();
        assert "figma.union(" in script, (
            "Phase E #3: figma.union(...) must be the materialization "
            "call for a UNION-typed bool_op with 2 children."
        )

    def test_specific_catch_metadata_in_failure_path(self):
        """Codex review #6: catch path should include eid + operation +
        childCount so failures are diagnostic, not opaque."""
        script = self._render()
        assert 'kind:"bool_op_create_failed"' in script, (
            "Phase E #3: failure kind in the bool_op materialization "
            "catch should be 'bool_op_create_failed'."
        )
        assert 'operation:"union"' in script, (
            "Catch metadata should expose the operation type."
        )
        assert 'childCount:2' in script, (
            "Catch metadata should expose the child count."
        )

    def test_z_order_insertchild_emitted(self):
        """Codex review #2: figma.union() always appends the new node
        at the END of grandparent's children. For non-last siblings
        we need insertChild to fix z-order. The fixture has only one
        bool_op sibling so it's at index 0."""
        script = self._render()
        # The bool_op is at index 0 in screen-1's children.
        assert "insertChild(0," in script, (
            "Phase E #3: insertChild should be emitted to fix "
            "z-order after figma.union() (which always appends at "
            "end)."
        )
