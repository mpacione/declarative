"""M2 demo-blocker — `dd.ast_to_element` tests.

The Figma renderer reads node properties only from the
`spec["elements"]` / `db_visuals` dicts, which are keyed on nodes
from the ORIGINAL screen. New nodes created by `append` /
`insert` / `replace` during the authoring loop have no spec
entry and no DB nid, so their subsequent `set @eid prop=value`
edits land on `node.head.properties` where the renderer can't
see them. Result: append-heavy demos render invisible nodes.

This module under test provides the resolver that merges
`head.properties` on top of spec/DB so BOTH original and new
nodes reach the emitters through the same path.

Forward mapping (IR element -> grammar head): see
`dd/compress_l3.py::_spatial_props` and `::_visual_props`.
This module inverts that grammar.
"""

from __future__ import annotations

from dd.markup_l3 import (
    Block,
    L3Document,
    Literal_,
    Node,
    NodeHead,
    PathOverride,
    PropAssign,
    PropGroup,
    SizingValue,
    parse_l3,
)

from dd.ast_to_element import ast_head_to_element, resolve_element


# ---------------------------------------------------------------------------
# Helpers — build minimal Node AST w/ arbitrary head.properties
# ---------------------------------------------------------------------------


def _num(n):
    return Literal_(lit_kind="number", raw=str(n), py=n)


def _enum(s):
    return Literal_(lit_kind="enum", raw=s, py=s)


def _hex(s):
    return Literal_(lit_kind="hex-color", raw=s, py=s)


def _bool(b):
    return Literal_(lit_kind="bool", raw="true" if b else "false", py=b)


def _node_with_props(props):
    """Construct a Node whose head.properties is the given tuple."""
    head = NodeHead(
        head_kind="type",
        type_or_path="frame",
        eid="b",
        properties=tuple(props),
    )
    return Node(head=head)


def _parse_head_props(src):
    """Parse a self-contained L3 snippet and return the first node's
    head.properties. Convenience for tests that want the real parser
    shape rather than hand-rolled literals."""
    doc = parse_l3(src)
    return doc.top_level[0].head.properties


# ---------------------------------------------------------------------------
# Per-property inverse mapping — grammar head -> IR element dict
# ---------------------------------------------------------------------------


class TestAstHeadToElement:
    def test_layout_horizontal(self):
        node = _node_with_props([
            PropAssign(key="layout", value=_enum("horizontal")),
        ])
        elem = ast_head_to_element(node)
        assert elem["layout"]["direction"] == "horizontal"

    def test_layout_vertical(self):
        node = _node_with_props([
            PropAssign(key="layout", value=_enum("vertical")),
        ])
        assert ast_head_to_element(node)["layout"]["direction"] == "vertical"

    def test_padding_propgroup(self):
        padding_group = PropGroup(entries=(
            PropAssign(key="top", value=_num(8)),
            PropAssign(key="right", value=_num(16)),
            PropAssign(key="bottom", value=_num(8)),
            PropAssign(key="left", value=_num(16)),
        ))
        node = _node_with_props([
            PropAssign(key="padding", value=padding_group),
        ])
        elem = ast_head_to_element(node)
        assert elem["layout"]["padding"] == {
            "top": 8, "right": 16, "bottom": 8, "left": 16,
        }

    def test_gap(self):
        node = _node_with_props([PropAssign(key="gap", value=_num(12))])
        assert ast_head_to_element(node)["layout"]["gap"] == 12

    def test_main_axis_start(self):
        node = _node_with_props([
            PropAssign(key="mainAxis", value=_enum("start")),
        ])
        elem = ast_head_to_element(node)
        assert elem["layout"]["mainAxisAlignment"] == "start"

    def test_cross_axis_end(self):
        node = _node_with_props([
            PropAssign(key="crossAxis", value=_enum("end")),
        ])
        elem = ast_head_to_element(node)
        assert elem["layout"]["crossAxisAlignment"] == "end"

    def test_align_center_expands_to_both_axes(self):
        node = _node_with_props([
            PropAssign(key="align", value=_enum("center")),
        ])
        elem = ast_head_to_element(node)
        assert elem["layout"]["mainAxisAlignment"] == "center"
        assert elem["layout"]["crossAxisAlignment"] == "center"

    def test_sizing_semantic(self):
        node = _node_with_props([
            PropAssign(key="width", value=SizingValue(size_kind="fill")),
            PropAssign(key="height", value=SizingValue(size_kind="hug")),
        ])
        sizing = ast_head_to_element(node)["layout"]["sizing"]
        assert sizing["width"] == "fill"
        assert sizing["height"] == "hug"

    def test_sizing_pixels(self):
        node = _node_with_props([
            PropAssign(key="width", value=_num(120)),
            PropAssign(key="height", value=_num(48)),
        ])
        sizing = ast_head_to_element(node)["layout"]["sizing"]
        assert sizing["widthPixels"] == 120
        assert sizing["heightPixels"] == 48

    def test_fill_hex(self):
        node = _node_with_props([
            PropAssign(key="fill", value=_hex("#FF3B30")),
        ])
        elem = ast_head_to_element(node)
        assert elem["visual"]["fills"] == [
            {"type": "solid", "color": "#FF3B30"},
        ]

    def test_stroke_with_weight(self):
        node = _node_with_props([
            PropAssign(key="stroke", value=_hex("#000000")),
            PropAssign(key="stroke-weight", value=_num(2)),
        ])
        elem = ast_head_to_element(node)
        assert elem["visual"]["strokes"] == [
            {"type": "solid", "color": "#000000", "width": 2},
        ]

    def test_stroke_weight_only_no_color(self):
        # stroke-weight without a stroke colour still produces a
        # stroke entry (width-only), matching the forward mapping which
        # emits stroke-weight off strokes[0].width.
        node = _node_with_props([
            PropAssign(key="stroke-weight", value=_num(3)),
        ])
        elem = ast_head_to_element(node)
        strokes = elem.get("visual", {}).get("strokes", [])
        assert len(strokes) == 1
        assert strokes[0]["width"] == 3

    def test_radius(self):
        node = _node_with_props([PropAssign(key="radius", value=_num(8))])
        assert ast_head_to_element(node)["visual"]["cornerRadius"] == 8

    def test_opacity(self):
        node = _node_with_props([
            PropAssign(key="opacity", value=_num(0.5)),
        ])
        assert ast_head_to_element(node)["visual"]["opacity"] == 0.5

    def test_visible_false(self):
        node = _node_with_props([
            PropAssign(key="visible", value=_bool(False)),
        ])
        assert ast_head_to_element(node)["visible"] is False

    def test_empty_head_properties(self):
        node = _node_with_props([])
        assert ast_head_to_element(node) == {}

    def test_unknown_property_silently_skipped(self):
        node = _node_with_props([
            PropAssign(key="weirdo-unknown-prop", value=_num(42)),
            PropAssign(key="layout", value=_enum("horizontal")),
        ])
        elem = ast_head_to_element(node)
        # layout survives; unknown is dropped without raising
        assert elem["layout"]["direction"] == "horizontal"

    def test_ignores_x_y_rotation_mirror(self):
        # Per spec, the renderer already reads these from head.
        # The resolver must not duplicate them into the element dict.
        node = _node_with_props([
            PropAssign(key="x", value=_num(10)),
            PropAssign(key="y", value=_num(20)),
            PropAssign(key="rotation", value=_num(0.5)),
            PropAssign(key="mirror", value=_enum("horizontal")),
        ])
        elem = ast_head_to_element(node)
        assert elem == {}

    def test_path_override_skipped(self):
        # PathOverride has no `.key` — must be silently ignored rather
        # than raising AttributeError.
        po = PathOverride(path=".visible", value=_bool(False))
        node = _node_with_props([
            po,
            PropAssign(key="layout", value=_enum("horizontal")),
        ])
        elem = ast_head_to_element(node)
        assert elem["layout"]["direction"] == "horizontal"

    def test_missing_head_returns_empty(self):
        # A head w/out properties at all (defensive path).
        head = NodeHead(head_kind="type", type_or_path="frame", eid="b")
        node = Node(head=head)
        assert ast_head_to_element(node) == {}


# ---------------------------------------------------------------------------
# resolve_element — precedence merging across head / spec / db
# ---------------------------------------------------------------------------


class TestResolveElement:
    def test_head_only_no_spec_no_db(self):
        node = _node_with_props([
            PropAssign(key="layout", value=_enum("horizontal")),
            PropAssign(key="gap", value=_num(8)),
        ])
        elem = resolve_element(
            node=node,
            spec_elements={},
            spec_key="b",
            db_visuals={},
            nid=None,
            nid_map={},
        )
        assert elem["layout"]["direction"] == "horizontal"
        assert elem["layout"]["gap"] == 8

    def test_spec_only_no_head_no_db(self):
        node = _node_with_props([])
        spec_elements = {
            "b": {
                "layout": {"direction": "vertical", "gap": 16},
                "visual": {"fills": [{"type": "solid", "color": "#FFFFFF"}]},
            }
        }
        elem = resolve_element(
            node=node,
            spec_elements=spec_elements,
            spec_key="b",
            db_visuals={},
            nid=None,
            nid_map={},
        )
        assert elem["layout"]["direction"] == "vertical"
        assert elem["layout"]["gap"] == 16
        assert elem["visual"]["fills"] == [
            {"type": "solid", "color": "#FFFFFF"},
        ]

    def test_head_overrides_spec_for_keys_head_defines(self):
        node = _node_with_props([
            PropAssign(key="layout", value=_enum("horizontal")),
        ])
        spec_elements = {
            "b": {"layout": {"direction": "vertical", "gap": 16}},
        }
        elem = resolve_element(
            node=node,
            spec_elements=spec_elements,
            spec_key="b",
            db_visuals={},
            nid=None,
            nid_map={},
        )
        # head wins for direction
        assert elem["layout"]["direction"] == "horizontal"
        # spec wins for gap (head doesn't mention it)
        assert elem["layout"]["gap"] == 16

    def test_absent_head_keys_do_not_clobber_spec(self):
        # CRITICAL: an ABSENT head.padding must not wipe the present
        # spec["elements"]["b"]["layout"]["padding"].
        node = _node_with_props([
            PropAssign(key="layout", value=_enum("horizontal")),
        ])
        spec_elements = {
            "b": {
                "layout": {
                    "direction": "vertical",
                    "padding": {"top": 8, "right": 16, "bottom": 8, "left": 16},
                },
            },
        }
        elem = resolve_element(
            node=node,
            spec_elements=spec_elements,
            spec_key="b",
            db_visuals={},
            nid=None,
            nid_map={},
        )
        assert elem["layout"]["direction"] == "horizontal"
        assert elem["layout"]["padding"] == {
            "top": 8, "right": 16, "bottom": 8, "left": 16,
        }

    def test_neither_head_nor_spec_mentions_key_no_default(self):
        # Key absent from both -> simply not present in result.
        node = _node_with_props([])
        elem = resolve_element(
            node=node,
            spec_elements={},
            spec_key="b",
            db_visuals={},
            nid=None,
            nid_map={},
        )
        assert "layout" not in elem
        assert "visual" not in elem

    def test_db_visual_flows_through_when_no_head_no_spec(self):
        node = _node_with_props([])
        db_visuals = {
            42: {"fills": [{"type": "solid", "color": "#AAAAAA"}]},
        }
        elem = resolve_element(
            node=node,
            spec_elements={},
            spec_key="b",
            db_visuals=db_visuals,
            nid=42,
            nid_map={id(node): 42},
        )
        # db contributes visual (simple shallow copy into element["visual"]).
        assert elem.get("visual", {}).get("fills") == [
            {"type": "solid", "color": "#AAAAAA"},
        ]

    def test_head_visual_overrides_db_visual_for_mentioned_keys(self):
        node = _node_with_props([
            PropAssign(key="fill", value=_hex("#FF3B30")),
        ])
        db_visuals = {
            42: {
                "fills": [{"type": "solid", "color": "#AAAAAA"}],
                "cornerRadius": 4,
            },
        }
        elem = resolve_element(
            node=node,
            spec_elements={},
            spec_key="b",
            db_visuals=db_visuals,
            nid=42,
            nid_map={id(node): 42},
        )
        # head wins for fills
        assert elem["visual"]["fills"] == [
            {"type": "solid", "color": "#FF3B30"},
        ]
        # db's cornerRadius survives (head didn't mention it)
        assert elem["visual"]["cornerRadius"] == 4

    def test_spec_overrides_db_head_overrides_both(self):
        # Full three-layer precedence.
        node = _node_with_props([
            PropAssign(key="radius", value=_num(12)),
        ])
        spec_elements = {
            "b": {
                "visual": {
                    "cornerRadius": 8,
                    "opacity": 0.75,
                },
            },
        }
        db_visuals = {
            42: {
                "cornerRadius": 4,
                "opacity": 0.5,
                "fills": [{"type": "solid", "color": "#AAAAAA"}],
            },
        }
        elem = resolve_element(
            node=node,
            spec_elements=spec_elements,
            spec_key="b",
            db_visuals=db_visuals,
            nid=42,
            nid_map={id(node): 42},
        )
        # head wins on cornerRadius
        assert elem["visual"]["cornerRadius"] == 12
        # spec wins on opacity (head didn't mention it; spec > db)
        assert elem["visual"]["opacity"] == 0.75
        # db's fills survive (only db mentioned them)
        assert elem["visual"]["fills"] == [
            {"type": "solid", "color": "#AAAAAA"},
        ]

    def test_m2_demo_trace_integration(self):
        # The M2 demo blocker: an appended frame gets a set @b edit,
        # and the resolver has to surface it even though the spec /
        # db have nothing for `b`.
        #
        # Simulate: `frame #b layout=horizontal padding={top=8 right=16
        # bottom=8 left=16} fill=#FF3B30`
        props = _parse_head_props(
            "frame #b layout=horizontal "
            "padding={top=8 right=16 bottom=8 left=16} "
            "fill=#FF3B30"
        )
        head = NodeHead(
            head_kind="type",
            type_or_path="frame",
            eid="b",
            properties=props,
        )
        node = Node(head=head)

        elem = resolve_element(
            node=node,
            spec_elements={},
            spec_key="b",
            db_visuals={},
            nid=None,
            nid_map={},
        )
        assert elem["layout"]["direction"] == "horizontal"
        assert elem["layout"]["padding"] == {
            "top": 8, "right": 16, "bottom": 8, "left": 16,
        }
        assert elem["visual"]["fills"] == [
            {"type": "solid", "color": "#FF3B30"},
        ]
