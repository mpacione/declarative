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

    def test_renders_create_boolean_operation_not_frame(self):
        """Phase E residual #1 — the regression. Pre-fix this
        emitted `figma.createFrame()` for the boolean-op node."""
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
        # Slice to Phase 1 only — the placeholder helper above Phase 1
        # may have its own createFrame calls; we only care about the
        # boolean-op's emission.
        p1_start = script.index("// Phase 1: Materialize")
        p2_start = script.index("// Phase 2: Compose")
        phase1_only = script[p1_start:p2_start]

        assert "figma.createBooleanOperation()" in phase1_only, (
            "Phase E residual #1: boolean-operation eid must dispatch "
            "to figma.createBooleanOperation(), not createFrame(). "
            "Pre-fix the hyphen→underscore mismatch silently fell "
            "through to createFrame and downstream "
            "`booleanOperation = 'UNION'` writes failed.\n"
            f"Phase 1 body (first 1500 chars):\n{phase1_only[:1500]}"
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

    def test_screen_with_boolean_op_has_both_create_calls(self):
        """End-to-end: 1 createFrame (screen) + 1 createBooleanOperation."""
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

        # Exactly 1 createFrame in Phase 1 (the screen).
        assert phase1_only.count("figma.createFrame()") == 1, (
            "Phase 1 should have exactly 1 createFrame (the screen). "
            f"Got {phase1_only.count('figma.createFrame()')}.\n"
            f"Phase 1: {phase1_only[:1200]}"
        )
        # Exactly 1 createBooleanOperation (the bool-op child).
        assert phase1_only.count("figma.createBooleanOperation()") == 1, (
            "Phase 1 should have exactly 1 createBooleanOperation."
        )


class TestBooleanOperationProvWriteSkip:
    """Phase E residual #1 follow-up — empty createBooleanOperation()
    returns a frozen node ("object is not extensible"). The renderer
    must NOT emit prop writes (name/fills/booleanOperation/etc.)
    for boolean_operation nodes — every write would throw.

    Verified empirically against the live bridge: pre-fix the
    boolean_operation node accumulated 8 errors per node (4 in
    Phase 1, 4 in Phase 3). Post-fix: zero errors per node.
    """

    @staticmethod
    def _build_doc_with_boolean_op():
        bool_op = Node(
            head=NodeHead(
                head_kind="type",
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

    def _render(self):
        doc, nid_map, spec_key_map, original_name_map = (
            self._build_doc_with_boolean_op()
        )
        db_visuals = {
            1: {"node_type": "FRAME"},
            2: {
                "node_type": "BOOLEAN_OPERATION",
                "fills": [{"type": "SOLID", "color": "#FFD64B"}],
                "strokeWeight": 1.0,
                "booleanOperation": "UNION",
            },
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

    def test_no_name_assignment_for_boolean_op(self):
        """Pre-fix: `n284.name = "ducky body"` was emitted and threw.
        Post-fix: no .name = ... line for the boolean_op."""
        script = self._render()
        # Find the boolean_op's var. Should be `const n? = figma.createBooleanOperation()`.
        # Then there should NOT be a `.name = "ducky body"` line.
        assert "ducky body" not in script, (
            'Phase E residual #1 follow-up: boolean_op should not '
            'have a `.name = "ducky body"` write — empty bool ops '
            'are frozen ("object is not extensible"). Got "ducky '
            'body" in script.'
        )

    def test_no_fills_assignment_for_boolean_op(self):
        script = self._render()
        # The screen frame may also do `.fills = []` (clear default).
        # We're checking specifically that the boolean_op's var doesn't
        # have a `.fills = ...` line. Easiest check: the test fixture
        # has db_visuals[2].fills = SOLID #FFD64B; a hex of FFD64B
        # would appear in script if it got emitted. Pre-fix it
        # appeared as part of `n284.fills = [{type: "SOLID", color:
        # {r:1.0,g:0.8431,b:0.2941}}]`.
        assert "FFD64B" not in script.upper(), (
            "Phase E residual #1 follow-up: boolean_op fills should "
            "not be emitted (would throw on the empty bool node)."
        )
        # Defensive: also no SOLID color value derived from the hex
        assert "0.8431" not in script, (
            "Phase E residual #1 follow-up: boolean_op fills hex was "
            "expanded to RGB color components — the prop write was "
            "still emitted."
        )

    def test_no_boolean_operation_property_for_boolean_op(self):
        script = self._render()
        # `booleanOperation = "UNION"` is the property write that
        # specifically motivated this fix. Must NOT appear.
        assert 'booleanOperation = "UNION"' not in script, (
            "Phase E residual #1 follow-up: the booleanOperation = "
            "'UNION' write was the smoking-gun bug."
        )

    def test_m_eid_still_assigned_for_boolean_op(self):
        """Critical: M["boolean_operation-1"] = var.id MUST still be
        emitted so the verifier walker can find the node. Skip the
        prop writes, NOT the M assignment."""
        script = self._render()
        assert 'M["boolean_operation-1"]' in script, (
            "Phase E residual #1 follow-up: M[eid] must still be "
            "assigned for boolean_op nodes — without it, the "
            "verifier walker can't reach the node and reports it "
            "as missing_child."
        )

    def test_phase_3_skip_no_resize_for_boolean_op(self):
        """Symmetric Phase 3 short-circuit. The fixture has no IR
        sizing on the bool_op, so no resize would be emitted anyway,
        but the short-circuit also covers constraint emission. The
        live-bridge run confirmed 0 constraint_failed errors."""
        script = self._render()
        # Phase 3 emits resize/x/y/constraints in guarded blocks
        # with `eid:"boolean_operation-1"`. None of those should
        # appear (the short-circuit at Phase 3 catches it before any
        # op is emitted).
        if "// Phase 3" in script:
            p3_start = script.index("// Phase 3")
            phase3 = script[p3_start:]
            assert 'eid:"boolean_operation-1"' not in phase3, (
                "Phase E residual #1 follow-up: Phase 3 must "
                "short-circuit boolean_op nodes (no resize / "
                "position / constraints / visibility emissions). "
                "Found eid:\"boolean_operation-1\" reference in "
                "Phase 3."
            )
