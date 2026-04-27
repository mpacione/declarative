"""P3a (Phase E N1 fix) — Mode-1 INSTANCE descendants must be SKIPPED
in Phase 1, Phase 2, and Phase 3 of the AST renderer.

Phase E §7 screen 24 produced **130+ `append_child_failed`** errors:
"Cannot move node into INSTANCE." Sonnet + Codex independently
diagnosed: the AST renderer (`dd/render_figma_ast.py`) lacks the
`mode1_eids` skip-set that the OLD path (`dd/renderers/figma.py:1267,
1306, 1479, 1757`) maintains. When Mode-1 `createInstance()` succeeds,
the renderer continues walking the IR descendants, tries to
`appendChild` them into the new INSTANCE, and Figma rejects.

This is also a Pattern 1 (canonical-path drift) instance: feature in
the old path was lost when canonical was ported. P2's orphan detector
caught a similar shape (`cluster_stroke_weight`).

P3a port:
- `mode1_node_ids: set[int]` — keyed on `id(node)` per AST renderer
  identity contract (Codex 2026-04-25)
- `skipped_node_ids: set[int]` — transitively-skipped descendants
- `absorbed_node_ids = mode1 | skipped` threaded into Phase 2 + Phase 3
- Phase 1: parent-in-set → add self to skipped + continue (descend
  through nested INSTANCE absorption)
- Phase 2 appendChild: id(node) in absorbed → continue (BEFORE
  leaf-type and group-deferral checks; Mode-1 absorption takes
  precedence)
- Phase 3 resize/position: id(node) in absorbed → continue (key on
  node, not parent — direct-parent check would miss grandchildren)

Caveat (Codex sharpest catch): `mode1_ok=True` means "Mode-1 IIFE
emitted," not "real createInstance succeeded at runtime." If the
master is unavailable, the IIFE returns `_missingComponentPlaceholder`.
Skipping descendants matches OLD-path behavior — placeholder render
gets no children. Alternative (conditionally append at runtime when
var IS the placeholder) is a bigger design choice deferred to a
future cycle.
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
from dd.render_figma_ast import render_figma


def _make_doc(root_node: Node) -> L3Document:
    """Wrap a single-root node tree in an L3Document for render_figma."""
    return L3Document(top_level=(root_node,))


def _ext_nid(value: int) -> PropAssign:
    """Construct a `$ext.nid=N` PropAssign so the AST node maps to a
    DB row id (renderer reads this for db_visuals lookups)."""
    return PropAssign(
        key="$ext.nid",
        value=Literal_(lit_kind="number", raw=str(value), py=value),
        trailer=None,
        kind="prop-assign",
    )


def _build_simple_screen() -> Node:
    """A screen with a Mode-1 INSTANCE containing nested descendants:

        screen-1 (frame, root)
        └── instance-1 (comp-ref, will Mode-1)
            ├── child-frame (frame)  ← should be SKIPPED (absorbed)
            │   └── grandchild-text (text)  ← should be SKIPPED (transitive)
            └── child-text (text)    ← should be SKIPPED (absorbed)

    The `instance-1` has $ext.nid pointing at a DB node so Mode-1
    emission runs.
    """
    grandchild = Node(
        head=NodeHead(
            head_kind="type",
            type_or_path="text",
            eid="grandchild-text",
            properties=(_ext_nid(104),),
        ),
        block=None,
    )
    child_frame = Node(
        head=NodeHead(
            head_kind="type",
            type_or_path="frame",
            eid="child-frame",
            properties=(_ext_nid(102),),
        ),
        block=Block(statements=(grandchild,)),
    )
    child_text = Node(
        head=NodeHead(
            head_kind="type",
            type_or_path="text",
            eid="child-text",
            properties=(_ext_nid(103),),
        ),
        block=None,
    )
    instance = Node(
        head=NodeHead(
            head_kind="comp-ref",
            type_or_path="cards/example",
            eid="instance-1",
            properties=(_ext_nid(101),),
        ),
        block=Block(statements=(child_frame, child_text)),
    )
    screen = Node(
        head=NodeHead(
            head_kind="type",
            type_or_path="frame",
            eid="screen-1",
            properties=(_ext_nid(100),),
        ),
        block=Block(statements=(instance,)),
    )
    return screen


# --- minimal nid_map / spec_key_map / db_visuals helpers ----


def _build_render_inputs(root: Node):
    """Walk the tree; build the dict shapes render_figma expects."""
    nid_map: dict[int, int] = {}
    spec_key_map: dict[int, str] = {}
    original_name_map: dict[int, str] = {}

    def walk(n: Node):
        # Pull $ext.nid out of the head's properties
        for p in n.head.properties:
            if (
                isinstance(p, PropAssign)
                and p.key == "$ext.nid"
                and isinstance(p.value, Literal_)
            ):
                nid_map[id(n)] = int(p.value.py)
        spec_key_map[id(n)] = n.head.eid or ""
        original_name_map[id(n)] = n.head.eid or "unnamed"
        if n.block:
            for stmt in n.block.statements:
                if isinstance(stmt, Node):
                    walk(stmt)

    walk(root)
    return nid_map, spec_key_map, original_name_map


def _render(root: Node, db_visuals: dict[int, dict]) -> str:
    """Render the doc end-to-end and return the script string."""
    nid_map, spec_key_map, original_name_map = _build_render_inputs(root)
    doc = _make_doc(root)
    script, _refs = render_figma(
        doc,
        conn=None,
        nid_map=nid_map,
        fonts=[("Inter", "Regular")],
        spec_key_map=spec_key_map,
        original_name_map=original_name_map,
        db_visuals=db_visuals,
        ckr_built=True,
    )
    return script


class TestPhase1SkipsAbsorbedDescendants:
    """When a Mode-1 instance materializes, Phase 1 should NOT emit
    `figma.createX()` for any of its descendants."""

    def test_mode1_descendants_get_no_create_call(self):
        screen = _build_simple_screen()
        # Mode-1 emission requires a db_visual with component_key (or
        # component_figma_id) for the instance node (nid=101).
        db_visuals = {
            100: {"node_type": "FRAME"},  # screen
            101: {
                "node_type": "INSTANCE",
                "component_key": "abc123" * 6 + "abcd",  # 40 hex chars
                "figma_node_id": "999:1",
                "component_figma_id": "999:1",
            },
            102: {"node_type": "FRAME"},  # child-frame (should NOT create)
            103: {"node_type": "TEXT"},   # child-text (should NOT create)
            104: {"node_type": "TEXT"},   # grandchild-text (should NOT create)
        }
        script = _render(screen, db_visuals)

        # Phase 1 emits a comment + per-node create lines AFTER it.
        # Helpers above (e.g. _missingComponentPlaceholder) include
        # their own createFrame/createLine/createText for the
        # placeholder block — those don't count toward our assertion.
        # Slice from the Phase 1 marker to the Phase 2 marker.
        p1_start = script.index("// Phase 1: Materialize")
        p2_start = script.index("// Phase 2: Compose")
        phase1_only = script[p1_start:p2_start]

        # Mode-1 instance emits an async IIFE (`const n? = await (async ...)`).
        # The screen emits `figma.createFrame()`. The absorbed descendants
        # (child-frame, child-text, grandchild-text) MUST NOT have their
        # own create calls in Phase 1.
        create_frame_count = phase1_only.count("figma.createFrame()")
        create_text_count = phase1_only.count("figma.createText()")
        assert create_frame_count == 1, (
            "Phase 1 should emit exactly 1 createFrame (the screen). "
            "Mode-1 absorbed `child-frame` should NOT create. "
            f"Got {create_frame_count} createFrame() calls in Phase 1.\n"
            f"Phase 1 body:\n{phase1_only[:1500]}"
        )
        assert create_text_count == 0, (
            "Phase 1 should emit 0 createText calls (both text nodes "
            "are inside the Mode-1 instance and should be absorbed). "
            f"Got {create_text_count} createText() calls in Phase 1."
        )


class TestPhase2SkipsAppendChildIntoInstance:
    """The headline N1 bug: Phase 2's appendChild loop must NOT emit
    `parent.appendChild(child)` for nodes inside a Mode-1 INSTANCE
    subtree. Figma's Plugin API rejects with 'Cannot move node into
    INSTANCE.'"""

    def test_no_appendchild_for_mode1_descendants(self):
        screen = _build_simple_screen()
        db_visuals = {
            100: {"node_type": "FRAME"},
            101: {
                "node_type": "INSTANCE",
                "component_key": "f" * 40,
                "figma_node_id": "999:1",
                "component_figma_id": "999:1",
            },
            102: {"node_type": "FRAME"},
            103: {"node_type": "TEXT"},
            104: {"node_type": "TEXT"},
        }
        script = _render(screen, db_visuals)

        # appendChild should NOT mention any of the Mode-1 descendants.
        # The script's eid markers (M["..."] = ...id) are the canonical
        # way to find which nodes were materialized. None of the
        # absorbed descendants should have an M[...] entry.
        assert 'M["child-frame"]' not in script, (
            "child-frame is inside Mode-1 INSTANCE — Phase 1 should "
            "not have created it AND Phase 2 should not have written "
            "M[\"child-frame\"]. Got it in the script."
        )
        assert 'M["child-text"]' not in script, (
            "child-text is inside Mode-1 INSTANCE — should be absorbed."
        )
        assert 'M["grandchild-text"]' not in script, (
            "grandchild-text is a TRANSITIVE descendant inside the "
            "Mode-1 INSTANCE — must also be skipped (direct-parent-only "
            "check would miss it; the codex spec specifically called "
            "this out)."
        )

    def test_screen_root_appendchild_still_emitted(self):
        """The screen-root and its DIRECT instance child should still
        appear in Phase 2 — only the descendants ARE absorbed."""
        screen = _build_simple_screen()
        db_visuals = {
            100: {"node_type": "FRAME"},
            101: {
                "node_type": "INSTANCE",
                "component_key": "f" * 40,
                "figma_node_id": "999:1",
                "component_figma_id": "999:1",
            },
            102: {"node_type": "FRAME"},
            103: {"node_type": "TEXT"},
            104: {"node_type": "TEXT"},
        }
        script = _render(screen, db_visuals)

        # The screen and the instance (its direct child) MUST still
        # be in the script — only the instance's descendants are
        # absorbed.
        assert 'M["screen-1"]' in script, (
            "screen-1 is the root; should be created"
        )
        assert 'M["instance-1"]' in script, (
            "instance-1 is the Mode-1 head itself; should still be "
            "created (the descendants below it are absorbed, not the "
            "instance itself)"
        )

    def test_mode1_head_phase2_appendchild_into_screen_emitted(self):
        """Phase E re-run regression test (2026-04-26): the Mode-1
        instance head MUST be appendChild'd into its own parent
        (screen-1) in Phase 2. Pre-fix the Phase 2 guard checked
        `id(node) in absorbed_node_ids`, which silently dropped the
        head's appendChild because the head IS in `mode1_node_ids`
        (added at Phase 1 line 836 after successful mode-1 emission).
        The instance then floated as a page-level orphan; the verifier
        reported `missing_child` for every top-level instance on
        screen 1 of the post-fix sweep (parity_ratio collapsed from
        1.0 to 0.5375). Codex 2026-04-26 confirmed: skip on
        `id(parent) in absorbed_node_ids`, not `id(node)`."""
        screen = _build_simple_screen()
        db_visuals = {
            100: {"node_type": "FRAME"},
            101: {
                "node_type": "INSTANCE",
                "component_key": "f" * 40,
                "figma_node_id": "999:1",
                "component_figma_id": "999:1",
            },
            102: {"node_type": "FRAME"},
            103: {"node_type": "TEXT"},
            104: {"node_type": "TEXT"},
        }
        script = _render(screen, db_visuals)
        # Slice to Phase 2 only — Phase 1 doesn't emit appendChild;
        # any Phase-1 helper code (placeholder block) is above the
        # Phase 2 marker.
        p2_start = script.index("// Phase 2: Compose")
        # Phase 3 may not exist if there are no Phase-3 props; find
        # the next phase marker or the end of the script.
        p3_idx = script.find("// Phase 3", p2_start)
        end_idx = script.find("// END", p2_start)
        next_marker = min(
            x for x in (p3_idx, end_idx, len(script)) if x >= 0
        ) if any(x >= 0 for x in (p3_idx, end_idx)) else len(script)
        phase2_only = script[p2_start:next_marker]

        # The instance head's appendChild must be present. The var
        # name comes from var_map (e.g. n1.appendChild(n2) where n2
        # is the instance). We assert by spec_key — the eid string
        # must appear in an appendChild error-handler entry, which
        # is what the renderer emits for guarded appendChild calls.
        assert 'eid:"instance-1"' in phase2_only, (
            "Phase E re-run regression: Phase 2 must emit an "
            "appendChild for the Mode-1 head (instance-1) so it "
            "lands inside the screen frame instead of floating as a "
            "page-level orphan. Pre-fix this was silently dropped.\n"
            f"Phase 2 body (first 1500 chars):\n{phase2_only[:1500]}"
        )

    def test_mode1_head_phase3_props_emitted(self):
        """Phase E re-run regression test (2026-04-26): the Mode-1
        instance head MUST get Phase 3 resize/position/constraints
        applied. Top-level instances carry explicit IR layout
        (x/y/width/height/constraints) that the verifier expects to
        see on the rendered tree. Pre-fix the Phase 3 guard also
        checked `id(node) in absorbed_node_ids` and dropped the head's
        ops, leaving the instance at default size + position."""
        screen = _build_simple_screen()
        db_visuals = {
            100: {"node_type": "FRAME"},
            101: {
                "node_type": "INSTANCE",
                "component_key": "f" * 40,
                "figma_node_id": "999:1",
                "component_figma_id": "999:1",
                # Phase 3 props that should land on the instance head
                "x": 0.0, "y": 810.0,
                "width": 390.0, "height": 34.0,
            },
            102: {"node_type": "FRAME"},
            103: {"node_type": "TEXT"},
            104: {"node_type": "TEXT"},
        }
        script = _render(screen, db_visuals)
        # Phase 3 emits `n?.resize(...)`, `n?.x = ...`, `n?.y = ...`
        # in guarded blocks with `eid:"instance-1"` for the
        # instance head. Just check the eid appears in any kind of
        # phase-3 op.
        # Phase 3 starts after Phase 2; find the marker.
        if "// Phase 3" in script:
            p3_start = script.index("// Phase 3")
            phase3 = script[p3_start:]
            # Any of resize/position/constraint should mention
            # eid:"instance-1" if the head's props were emitted.
            assert (
                'eid:"instance-1", kind:"resize_failed"' in phase3
                or 'eid:"instance-1", kind:"position_failed"' in phase3
            ), (
                "Phase E re-run regression: Phase 3 must emit "
                "resize/position for the Mode-1 head (instance-1) "
                "so the rendered instance has the IR's explicit "
                "layout. Pre-fix this was silently dropped.\n"
                f"Phase 3 body (first 1500 chars):\n{phase3[:1500]}"
            )


class TestTransitiveSkipping:
    """Codex sharp-edge catch: direct-parent-only check would miss
    grandchildren. The fix relies on Phase 1's transitive
    `skipped_node_ids` population: when a node's parent is in
    `mode1_node_ids` or `skipped_node_ids`, the node itself is
    added to `skipped_node_ids`. By induction every descendant of a
    Mode-1 head ends up in `skipped_node_ids`, so the parent-in-set
    check at Phase 2/3 catches grandchildren correctly (their
    parent IS in skipped_node_ids).

    Pre-2026-04-26 the Phase 2/3 guards checked node-in-set, which
    appeared more direct but silently dropped the Mode-1 head's
    own ops. The 2026-04-26 fix moved both guards to parent-in-set;
    transitive coverage still works because `skipped_node_ids`
    is populated transitively in Phase 1."""

    def test_grandchild_of_instance_is_absorbed(self):
        """Build:

            screen
            └── instance (Mode-1)
                └── child-frame
                    └── grandchild-text  ← MUST be skipped

        With parent-in-set: grandchild-text's parent is child-frame.
        child-frame's parent is instance (in mode1_node_ids), so
        Phase 1 puts child-frame in skipped_node_ids. Then
        grandchild-text's parent (child-frame) IS in skipped_node_ids
        → grandchild-text is also added to skipped_node_ids. Phase 2's
        parent-in-set check on grandchild-text sees its parent
        (child-frame) in absorbed_node_ids → skip. Correct.
        """
        screen = _build_simple_screen()
        db_visuals = {
            100: {"node_type": "FRAME"},
            101: {
                "node_type": "INSTANCE",
                "component_key": "f" * 40,
                "figma_node_id": "999:1",
                "component_figma_id": "999:1",
            },
            102: {"node_type": "FRAME"},
            103: {"node_type": "TEXT"},
            104: {"node_type": "TEXT"},
        }
        script = _render(screen, db_visuals)
        # The grandchild's eid must NOT be in the script.
        assert 'M["grandchild-text"]' not in script
        # Defensive: no createText in Phase 1 (the placeholder helper
        # block above Phase 1 includes its own createText for the
        # missing-component wireframe; we slice to Phase 1 only).
        p1_start = script.index("// Phase 1: Materialize")
        p2_start = script.index("// Phase 2: Compose")
        phase1_only = script[p1_start:p2_start]
        assert "createText" not in phase1_only


class TestNonInstanceUnaffected:
    """Sanity: non-Mode-1 trees must STILL render normally. P3a is a
    surgical guard, not a behavior change for the common case."""

    def test_plain_frame_tree_renders_all_nodes(self):
        """A frame tree with NO Mode-1 instances: every node should
        still create + appendChild + M[...]= as before."""
        text_a = Node(
            head=NodeHead(
                head_kind="type", type_or_path="text", eid="text-a",
                properties=(_ext_nid(202),),
            ),
            block=None,
        )
        frame_b = Node(
            head=NodeHead(
                head_kind="type", type_or_path="frame", eid="frame-b",
                properties=(_ext_nid(203),),
            ),
            block=None,
        )
        screen = Node(
            head=NodeHead(
                head_kind="type", type_or_path="frame", eid="screen-2",
                properties=(_ext_nid(200),),
            ),
            block=Block(statements=(text_a, frame_b)),
        )
        db_visuals = {
            200: {"node_type": "FRAME"},
            202: {"node_type": "TEXT"},
            203: {"node_type": "FRAME"},
        }
        script = _render(screen, db_visuals)
        # All three should be created.
        assert 'M["screen-2"]' in script
        assert 'M["text-a"]' in script
        assert 'M["frame-b"]' in script
        # 2 createFrame (screen + frame-b), 1 createText (text-a)
        assert script.count("figma.createFrame()") == 2
        assert script.count("figma.createText()") == 1
