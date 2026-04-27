"""Item 1 — IR-side canonicalization of unrenderable layoutSizing.

Per docs/plan-burndown-13-items.md item 1 + Codex round-12 architectural
fork: when the source DB has ``layout_sizing_h='HUG'`` (or 'FILL') but
the parent context can't honor that semantic, the IR should NOT carry
the enum value. Instead, canonicalize to numeric pixels — what Figma
will actually render.

Sprint 2 C11 cross-corpus sweep surfaced 2,992 IR='HUG' rendered='FIXED'
mismatches across 311 screens. Root cause: the source Figma file has
HUG set on nodes whose parent isn't auto-layout. Figma's UI lets you
do that, but the rendered result is always FIXED (the property is a
no-op visually outside auto-layout context). The IR was carrying the
unrenderable intent; this fix canonicalizes it.

Codex round-12 validity rules (from current Plugin API docs):
  - ``FILL`` is valid ONLY when parent is auto-layout
  - ``HUG`` is valid for: text nodes, auto-layout frames (regardless
    of parent)
  - Otherwise → canonicalize to numeric pixels in IR

This is item 1 of the 13-item burn-down. Closes the dominant DRIFT
class observed in Sprint 2 C11 results.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def base_data():
    """Minimum data shape for build_composition_spec — screen meta +
    nodes + tokens. Tests fill in nodes per scenario."""
    return {
        "screen_id": 1,
        "screen_name": "test",
        "screen_type": "app_screen",
        "screen_origin_x": 0,
        "screen_origin_y": 0,
        "width": 100,
        "height": 100,
        "tokens": {},
        "nodes": [],
    }


def _node(**kwargs):
    """Build a minimal node dict with sensible defaults."""
    return {
        "node_id": kwargs.get("node_id", 1),
        "parent_id": kwargs.get("parent_id"),
        "figma_node_id": kwargs.get("figma_node_id", f"f-{kwargs.get('node_id', 1)}"),
        "canonical_type": kwargs.get("canonical_type"),
        "node_type": kwargs.get("node_type", "FRAME"),
        "name": kwargs.get("name", "test"),
        "depth": kwargs.get("depth", 0),
        "sort_order": kwargs.get("sort_order", 0),
        "width": kwargs.get("width", 100),
        "height": kwargs.get("height", 100),
        "layout_mode": kwargs.get("layout_mode"),
        "layout_sizing_h": kwargs.get("layout_sizing_h"),
        "layout_sizing_v": kwargs.get("layout_sizing_v"),
        "bindings": kwargs.get("bindings", []),
    }


# ---------------------------------------------------------------------
# Item 1 — Codex round-12 canonicalization rules
# ---------------------------------------------------------------------


class TestFillRequiresAutolayoutParent:
    """``FILL`` is valid ONLY when parent is auto-layout."""

    def test_fill_kept_under_horizontal_autolayout_parent(self, base_data):
        """FILL is valid when parent has layout_mode='HORIZONTAL'."""
        from dd.ir import build_composition_spec

        base_data["nodes"] = [
            _node(node_id=1, layout_mode="HORIZONTAL", node_type="FRAME"),
            _node(node_id=2, parent_id=1,
                  layout_sizing_h="FILL", node_type="FRAME"),
        ]
        spec = build_composition_spec(base_data)

        # Find child element
        child = next(
            el for el in spec["elements"].values()
            if el.get("_original_name") == "test" and el.get("type") == "frame"
            and el is not list(spec["elements"].values())[0]
        )
        sizing = child.get("layout", {}).get("sizing", {})
        assert sizing.get("width") == "fill", (
            f"FILL under auto-layout parent should be preserved; got {sizing}"
        )

    def test_fill_canonicalized_under_non_autolayout_parent(self, base_data):
        """FILL is invalid when parent is NOT auto-layout — canonicalize
        to numeric pixels."""
        from dd.ir import build_composition_spec

        base_data["nodes"] = [
            # Parent: NO layout_mode (not auto-layout)
            _node(node_id=1, layout_mode=None, node_type="FRAME"),
            _node(node_id=2, parent_id=1,
                  layout_sizing_h="FILL", width=200, node_type="FRAME"),
        ]
        spec = build_composition_spec(base_data)

        child = next(
            el for eid, el in spec["elements"].items()
            if el.get("type") == "frame" and eid != "frame-1"
        )
        sizing = child.get("layout", {}).get("sizing", {})
        # FILL canonicalized → numeric
        assert sizing.get("width") != "fill", (
            f"FILL under non-auto-layout parent should canonicalize to "
            f"numeric, not stay 'fill'; got {sizing}"
        )
        # Numeric value preserved
        assert sizing.get("width") == 200


class TestHugRules:
    """``HUG`` is valid for: text nodes, auto-layout frames
    (regardless of parent)."""

    def test_hug_kept_on_text_node_under_non_autolayout_parent(self, base_data):
        """Text nodes can HUG regardless of parent context."""
        from dd.ir import build_composition_spec

        base_data["nodes"] = [
            _node(node_id=1, layout_mode=None, node_type="FRAME"),
            _node(node_id=2, parent_id=1,
                  layout_sizing_h="HUG",
                  node_type="TEXT", canonical_type="text"),
        ]
        spec = build_composition_spec(base_data)

        text = next(
            el for el in spec["elements"].values()
            if el.get("type") == "text"
        )
        sizing = text.get("layout", {}).get("sizing", {})
        assert sizing.get("width") == "hug", (
            f"HUG on text node should be preserved; got {sizing}"
        )

    def test_hug_kept_on_autolayout_frame_under_non_autolayout_parent(self, base_data):
        """An auto-layout frame can HUG its own children regardless of
        what its parent is."""
        from dd.ir import build_composition_spec

        base_data["nodes"] = [
            # Outer parent: NOT auto-layout
            _node(node_id=1, layout_mode=None, node_type="FRAME"),
            # Inner: IS auto-layout (HORIZONTAL), AND has HUG
            _node(node_id=2, parent_id=1,
                  layout_mode="HORIZONTAL",  # makes it an auto-layout frame
                  layout_sizing_h="HUG", node_type="FRAME"),
        ]
        spec = build_composition_spec(base_data)

        # The inner auto-layout frame is the one with direction=horizontal
        inner = next(
            el for el in spec["elements"].values()
            if el.get("layout", {}).get("direction") == "horizontal"
        )
        sizing = inner.get("layout", {}).get("sizing", {})
        assert sizing.get("width") == "hug", (
            f"HUG on auto-layout frame (regardless of parent) should be "
            f"preserved; got {sizing}"
        )

    def test_hug_canonicalized_on_rectangle_under_non_autolayout_parent(
        self, base_data,
    ):
        """A non-text, non-auto-layout-frame node (e.g. RECTANGLE) with
        HUG and non-auto-layout parent — HUG is unrenderable, must
        canonicalize."""
        from dd.ir import build_composition_spec

        base_data["nodes"] = [
            _node(node_id=1, layout_mode=None, node_type="FRAME"),
            _node(node_id=2, parent_id=1,
                  layout_sizing_h="HUG", width=150,
                  node_type="RECTANGLE", canonical_type="rectangle"),
        ]
        spec = build_composition_spec(base_data)

        rect = next(
            el for el in spec["elements"].values()
            if el.get("type") == "rectangle"
        )
        sizing = rect.get("layout", {}).get("sizing", {})
        assert sizing.get("width") != "hug", (
            f"HUG on RECTANGLE under non-auto-layout parent should "
            f"canonicalize; got {sizing}"
        )
        assert sizing.get("width") == 150


class TestVerticalAxisSameRules:
    """The same rules apply to layout_sizing_v / sizing.height."""

    def test_fill_v_canonicalized_under_non_autolayout_parent(self, base_data):
        from dd.ir import build_composition_spec

        base_data["nodes"] = [
            _node(node_id=1, layout_mode=None, node_type="FRAME"),
            _node(node_id=2, parent_id=1,
                  layout_sizing_v="FILL", height=300, node_type="FRAME"),
        ]
        spec = build_composition_spec(base_data)
        child = next(
            el for eid, el in spec["elements"].items()
            if el.get("type") == "frame" and eid != "frame-1"
        )
        sizing = child.get("layout", {}).get("sizing", {})
        assert sizing.get("height") != "fill"
        assert sizing.get("height") == 300

    def test_hug_v_kept_on_autolayout_frame(self, base_data):
        from dd.ir import build_composition_spec

        base_data["nodes"] = [
            _node(node_id=1, layout_mode=None, node_type="FRAME"),
            _node(node_id=2, parent_id=1,
                  layout_mode="VERTICAL",
                  layout_sizing_v="HUG", node_type="FRAME"),
        ]
        spec = build_composition_spec(base_data)
        inner = next(
            el for el in spec["elements"].values()
            if el.get("layout", {}).get("direction") == "vertical"
        )
        sizing = inner.get("layout", {}).get("sizing", {})
        assert sizing.get("height") == "hug"


class TestRootElementFillCanonicalization:
    """Root elements (no parent) — FILL/HUG are unrenderable. The
    "screen root" frame doesn't have a parent_is_autolayout context."""

    def test_root_fill_canonicalized_to_numeric(self, base_data):
        from dd.ir import build_composition_spec

        base_data["nodes"] = [
            # Root with FILL — no parent
            _node(node_id=1, layout_sizing_h="FILL", width=375,
                  node_type="FRAME"),
        ]
        spec = build_composition_spec(base_data)
        root = next(iter(spec["elements"].values()))
        sizing = root.get("layout", {}).get("sizing", {})
        assert sizing.get("width") != "fill", (
            f"FILL on root element (no parent) should canonicalize; "
            f"got {sizing}"
        )
        assert sizing.get("width") == 375

    def test_root_hug_kept_on_autolayout_frame(self, base_data):
        """Root frame is auto-layout — HUG is valid (the frame hugs
        its own content)."""
        from dd.ir import build_composition_spec

        base_data["nodes"] = [
            _node(node_id=1, layout_mode="VERTICAL",
                  layout_sizing_h="HUG", node_type="FRAME"),
        ]
        spec = build_composition_spec(base_data)
        root = next(iter(spec["elements"].values()))
        sizing = root.get("layout", {}).get("sizing", {})
        assert sizing.get("width") == "hug"


# ---------------------------------------------------------------------
# Item 1 — renderer-side defense (Codex round-13 follow-up):
# _resolve_one_axis must validate DB values against parent context.
# ---------------------------------------------------------------------


class TestResolveOneAxisValidatesDbValues:
    """Per Codex round-13: when DB says HUG but parent isn't auto-layout
    AND node isn't text/auto-layout-frame, the DB value is invalid.
    Renderer must fall through to IR rather than emitting the invalid
    enum.

    Sprint 2 C11 sweep showed even with IR canonicalization, the
    renderer path was emitting HUG from DB, causing 2,992 mismatches."""

    def test_db_hug_passes_when_parent_autolayout_and_node_text(self):
        """Valid case: DB HUG, parent auto-layout, node text → keep DB value."""
        from dd.visual import _resolve_one_axis

        result = _resolve_one_axis(
            db_value="HUG",
            text_override=None,
            ir_value="hug",
            is_text=True,
            etype="text",
            is_horizontal=True,
            parent_is_autolayout=True,
            node_is_autolayout_frame=False,
        )
        assert result == "HUG"

    def test_db_hug_passes_when_node_is_autolayout_frame(self):
        """Valid case: DB HUG, node is auto-layout frame (regardless of parent)."""
        from dd.visual import _resolve_one_axis

        result = _resolve_one_axis(
            db_value="HUG",
            text_override=None,
            ir_value="hug",
            is_text=False,
            etype="frame",
            is_horizontal=True,
            parent_is_autolayout=False,
            node_is_autolayout_frame=True,
        )
        assert result == "HUG"

    def test_db_hug_invalid_falls_through_to_ir(self):
        """The bug case: DB HUG, parent NOT auto-layout, node NOT text
        nor auto-layout-frame. DB value invalid; fall through to IR."""
        from dd.visual import _resolve_one_axis

        result = _resolve_one_axis(
            db_value="HUG",
            text_override=None,
            ir_value=200,  # IR has been canonicalized to numeric
            is_text=False,
            etype="rectangle",
            is_horizontal=True,
            parent_is_autolayout=False,
            node_is_autolayout_frame=False,
        )
        assert result == "fixed", (
            f"DB HUG invalid in context; should fall through to IR "
            f"numeric → 'fixed'; got {result!r}"
        )

    def test_db_fill_invalid_when_parent_not_autolayout(self):
        """DB FILL is invalid when parent isn't auto-layout."""
        from dd.visual import _resolve_one_axis

        result = _resolve_one_axis(
            db_value="FILL",
            text_override=None,
            ir_value=300,
            is_text=False,
            etype="frame",
            is_horizontal=True,
            parent_is_autolayout=False,
            node_is_autolayout_frame=False,
        )
        assert result == "fixed"

    def test_db_fill_valid_when_parent_autolayout(self):
        """DB FILL is valid when parent IS auto-layout."""
        from dd.visual import _resolve_one_axis

        result = _resolve_one_axis(
            db_value="FILL",
            text_override=None,
            ir_value="fill",
            is_text=False,
            etype="frame",
            is_horizontal=True,
            parent_is_autolayout=True,
            node_is_autolayout_frame=False,
        )
        assert result == "FILL"

    def test_db_fixed_unaffected(self):
        """DB FIXED is always valid (no auto-layout context required)."""
        from dd.visual import _resolve_one_axis

        result = _resolve_one_axis(
            db_value="FIXED",
            text_override=None,
            ir_value=100,
            is_text=False,
            etype="rectangle",
            is_horizontal=True,
            parent_is_autolayout=False,
            node_is_autolayout_frame=False,
        )
        assert result == "FIXED"

    def test_no_db_value_uses_ir(self):
        """When DB has no value, fall through to IR sizing as before."""
        from dd.visual import _resolve_one_axis

        result = _resolve_one_axis(
            db_value=None,
            text_override=None,
            ir_value="hug",
            is_text=False,
            etype="frame",
            is_horizontal=True,
            parent_is_autolayout=True,
            node_is_autolayout_frame=False,
        )
        # When DB absent, return IR as-is (item 1 IR canonicalization
        # is already responsible for guarding IR validity)
        assert result == "hug"
