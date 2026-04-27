"""Regression test for the self-auto-layout-frame layoutSizing emission gap.

`be8ec97` (burndown Item 1) introduced IR canonicalization for
unrenderable layoutSizing values. The IR-side rule keeps `HUG` for
auto-layout frames regardless of parent context. The renderer
(`dd/renderers/figma.py:1860`) was correctly updated to emit
layoutSizing whenever:

    parent_is_autolayout OR self_is_autolayout_frame OR is_text

But the markup-native renderer (`dd/render_figma_ast.py:1903`) was
left with the older gate that only checked `parent_is_autolayout`. A
self-auto-layout frame whose parent is NOT auto-layout therefore
keeps its IR `HUG` value, but the renderer never emits the
`layoutSizingHorizontal/Vertical = "HUG"` line. Figma defaults the
freshly-resized frame to FIXED, the verifier walks the live render
and reads FIXED, and the IR-vs-rendered diff registers as
`layout_sizing_h_mismatch` / `layout_sizing_v_mismatch`.

Empirical: the `audit/post-revert-sweep-20260427-1040` sweep on the
Dank corpus reported `IR='HUG' rendered='FIXED'` on every screen
that has top-level container/button/card frames. Codex 5.5 +
Sonnet diagnosis 2026-04-27 (high reasoning).

Fix: port the canonical gate from `dd/renderers/figma.py:1860` to
`dd/render_figma_ast.py:1903`. Compute `node_is_autolayout_frame`
once, broaden the condition to match.
"""

from __future__ import annotations

from dd.markup_l3 import parse_l3
from dd.render_figma_ast import render_figma


def _iter_nodes(nodes):
    for n in nodes:
        yield n
        if getattr(n, "block", None):
            yield from _iter_nodes(n.block.statements)


def _render_self_al_under_non_al() -> str:
    """Render a `screen` (no autolayout direction) containing a single
    auto-layout `frame` child. The child has IR `width=hug height=hug`,
    its `_node_id_map` provides a stable nid.

    Pre-fix: `dd/render_figma_ast.py:1903` only emits layoutSizing for
    children whose immediate parent is auto-layout. Since `screen` has
    no `direction`, the gate fails and `layoutSizingHorizontal = "HUG"`
    is never written.

    Post-fix: the gate broadens to also fire when the node itself is
    an auto-layout frame, so the line emits.
    """
    src = (
        "screen #screen-1 {\n"
        "  frame #card-1 width=hug height=hug layout=horizontal gap=8\n"
        "}\n"
    )
    doc = parse_l3(src)
    spec_key_map = {
        id(n): (n.head.eid or "") for n in _iter_nodes(doc.top_level)
    }
    original_name_map = dict(spec_key_map)

    # Spec elements drive the parent-direction / self-direction lookups
    # that the renderer's gate consults. Mirrors what
    # `_compress_to_l3_impl` produces for a real screen.
    spec_elements = {
        "screen-1": {
            "type": "screen",
            "_walk_idx": 0,
            "layout": {},  # no direction → not auto-layout
        },
        "card-1": {
            "type": "frame",
            "_walk_idx": 1,
            "layout": {
                "direction": "horizontal",  # self IS auto-layout
                "sizing": {"width": "hug", "height": "hug"},
                "gap": 8,
            },
        },
    }

    script, _refs = render_figma(
        doc, conn=None, nid_map={},
        fonts=[("Inter", "Regular")],
        spec_key_map=spec_key_map,
        original_name_map=original_name_map,
        _spec_elements=spec_elements,
    )
    return script


class TestSelfAutoLayoutFrameLayoutSizing:
    """When a node is itself an auto-layout frame, the renderer must
    emit layoutSizing even if the parent isn't auto-layout. This
    matches the canonical gate in `dd/renderers/figma.py:1860`."""

    def test_self_al_frame_under_non_al_parent_emits_layout_sizing_horizontal(
        self,
    ) -> None:
        script = _render_self_al_under_non_al()
        # The child auto-layout frame's HUG sizing must reach the
        # rendered script as `layoutSizingHorizontal = "HUG"`.
        assert 'layoutSizingHorizontal = "HUG"' in script, (
            "Self-auto-layout frame under non-auto-layout parent: "
            "HUG horizontal sizing not emitted. Renderer gate is too "
            "narrow.\nScript excerpt:\n"
            + "\n".join(
                line for line in script.split("\n")
                if "layoutSizing" in line or "card-1" in line
            )[:600]
        )

    def test_self_al_frame_under_non_al_parent_emits_layout_sizing_vertical(
        self,
    ) -> None:
        script = _render_self_al_under_non_al()
        assert 'layoutSizingVertical = "HUG"' in script, (
            "Self-auto-layout frame under non-auto-layout parent: "
            "HUG vertical sizing not emitted. Renderer gate is too "
            "narrow.\nScript excerpt:\n"
            + "\n".join(
                line for line in script.split("\n")
                if "layoutSizing" in line or "card-1" in line
            )[:600]
        )

    def test_non_al_node_under_non_al_parent_does_not_emit(self) -> None:
        """Control: a plain rectangle (NOT auto-layout) under a non-AL
        parent should still NOT emit layoutSizing. The fix must not
        accidentally promote leaf-type emission."""
        src = (
            "screen #screen-1 {\n"
            "  rectangle #rect-1 width=100 height=100\n"
            "}\n"
        )
        doc = parse_l3(src)
        spec_key_map = {
            id(n): (n.head.eid or "") for n in _iter_nodes(doc.top_level)
        }
        original_name_map = dict(spec_key_map)
        spec_elements = {
            "screen-1": {
                "type": "screen",
                "_walk_idx": 0,
                "layout": {},
            },
            "rect-1": {
                "type": "rectangle",
                "_walk_idx": 1,
                "layout": {
                    "sizing": {"widthPixels": 100, "heightPixels": 100},
                },
            },
        }
        script, _refs = render_figma(
            doc, conn=None, nid_map={},
            fonts=[("Inter", "Regular")],
            spec_key_map=spec_key_map,
            original_name_map=original_name_map,
            _spec_elements=spec_elements,
        )
        # A leaf rectangle with no auto-layout direction must not emit
        # layoutSizing — the property has no meaning outside auto-layout
        # context.
        assert 'rect-1' in script  # sanity: node was emitted
        # The CHILD must not have layoutSizing applied.
        rect_lines = [
            line for line in script.split("\n")
            if 'rect-1' in line or 'n1.' in line
        ]
        rect_block = "\n".join(rect_lines)
        assert "layoutSizingHorizontal" not in rect_block, (
            "Leaf rectangle under non-AL parent must not emit "
            "layoutSizing.\n" + rect_block[:600]
        )
        assert "layoutSizingVertical" not in rect_block, (
            "Leaf rectangle under non-AL parent must not emit "
            "layoutSizing.\n" + rect_block[:600]
        )
