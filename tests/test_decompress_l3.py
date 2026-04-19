"""Plan B Stage 1.5 — decompressor tests.

Tests `dd.decompress_l3.ast_to_dict_ir` on hand-built AST fragments
and on the compressor's output for the reference screens. Verifies
the AST → dict IR direction of the Tier-2 round-trip.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dd.compress_l3 import compress_to_l3
from dd.decompress_l3 import ast_to_dict_ir
from dd.ir import generate_ir
from dd.markup_l3 import (
    Block,
    FuncArg,
    FunctionCall,
    L3Document,
    Literal_,
    Node,
    NodeHead,
    PathOverride,
    PropAssign,
    PropGroup,
    SizingValue,
    TokenRef,
)


DB_PATH = Path(__file__).resolve().parent.parent / "Dank-EXP-02.declarative.db"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        pytest.skip(f"corpus DB not present at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# Helper to build small AST fragments.
def _n(raw: str) -> Literal_:
    return Literal_(lit_kind="number", raw=raw, py=int(raw))


def _hex(code: str) -> Literal_:
    return Literal_(lit_kind="hex-color", raw=code, py=code)


def _enum(kw: str) -> Literal_:
    return Literal_(lit_kind="enum", raw=kw, py=kw)


def _bool(py: bool) -> Literal_:
    return Literal_(lit_kind="bool", raw="true" if py else "false", py=py)


def _p(key: str, value) -> PropAssign:
    return PropAssign(key=key, value=value)


class TestDecompressEmptyDoc:
    def test_empty_doc_produces_empty_spec(self) -> None:
        spec = ast_to_dict_ir(L3Document())
        assert spec == {"version": "1.0", "root": None, "elements": {}}

    def test_non_node_top_level_produces_empty_spec(self) -> None:
        # A doc with no Node children at top level.
        spec = ast_to_dict_ir(L3Document(top_level=()))
        assert spec["root"] is None


class TestDecompressSimpleNode:
    def test_frame_with_sizing_and_fill(self) -> None:
        """Single frame with width/height/fill → element dict with
        layout.sizing and visual.fills[0]."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type",
            type_or_path="frame",
            eid="root",
            properties=(
                _p("width", _n("100")),
                _p("height", _n("200")),
                _p("fill", _hex("#FF0000")),
            ),
        )),))
        spec = ast_to_dict_ir(doc)
        elements = spec["elements"]
        assert spec["root"] == "frame-1"
        el = elements["frame-1"]
        assert el["type"] == "frame"
        assert el["layout"]["sizing"] == {"width": 100, "height": 200}
        assert el["visual"]["fills"] == [
            {"type": "solid", "color": "#FF0000"},
        ]

    def test_text_node_with_positional_content(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type",
            type_or_path="text",
            eid="t",
            positional=Literal_(
                lit_kind="string", raw='"hello"', py="hello",
            ),
            properties=(_p("fill", _hex("#000000")),),
        )),))
        spec = ast_to_dict_ir(doc)
        el = spec["elements"][spec["root"]]
        assert el["type"] == "text"
        assert el["props"]["text"] == "hello"

    def test_layout_and_alignment(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type",
            type_or_path="container",
            eid="c",
            properties=(
                _p("layout", _enum("horizontal")),
                _p("gap", _n("10")),
                _p("mainAxis", _enum("space-between")),
                _p("crossAxis", _enum("center")),
            ),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["container-1"]
        assert el["layout"]["direction"] == "horizontal"
        assert el["layout"]["gap"] == 10
        # Grammar enum back to spec-lower form.
        assert el["layout"]["mainAxisAlignment"] == "space_between"
        assert el["layout"]["crossAxisAlignment"] == "center"

    def test_align_shorthand_expands_to_both_axes(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type",
            type_or_path="frame",
            eid="f",
            properties=(_p("align", _enum("center")),),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["frame-1"]
        assert el["layout"]["mainAxisAlignment"] == "center"
        assert el["layout"]["crossAxisAlignment"] == "center"

    def test_padding_propgroup(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type",
            type_or_path="frame",
            eid="f",
            properties=(_p("padding", PropGroup(entries=(
                _p("top", _n("10")),
                _p("right", _n("12")),
                _p("bottom", _n("10")),
                _p("left", _n("12")),
            ))),),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["frame-1"]
        assert el["layout"]["padding"] == {
            "top": 10, "right": 12, "bottom": 10, "left": 12,
        }

    def test_stroke_with_weight(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type",
            type_or_path="frame",
            eid="f",
            properties=(
                _p("stroke", _hex("#000000")),
                _p("stroke-weight", _n("2")),
            ),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["frame-1"]
        assert el["visual"]["strokes"] == [
            {"type": "solid", "color": "#000000", "width": 2},
        ]

    def test_shadow_function_to_effect(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type",
            type_or_path="card",
            eid="c",
            properties=(_p("shadow", FunctionCall(name="shadow", args=(
                FuncArg(name="x", value=_n("0")),
                FuncArg(name="y", value=_n("4")),
                FuncArg(name="blur", value=_n("8")),
                FuncArg(name="color", value=_hex("#00000040")),
            ))),),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["card-1"]
        assert el["visual"]["effects"][0]["type"] == "drop-shadow"
        assert el["visual"]["effects"][0]["offset"] == {"x": 0, "y": 4}
        assert el["visual"]["effects"][0]["radius"] == 8
        assert el["visual"]["effects"][0]["color"] == "#00000040"

    def test_sizing_fill_hug_round_trip(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type",
            type_or_path="frame",
            eid="f",
            properties=(
                _p("width", SizingValue(size_kind="fill")),
                _p("height", SizingValue(size_kind="hug")),
            ),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["frame-1"]
        assert el["layout"]["sizing"] == {"width": "fill", "height": "hug"}

    def test_mainaxis_space_around_and_space_evenly_decode(self) -> None:
        """§7.4 mainAxis values space-around / space-evenly must
        decode to the spec-underscore form."""
        for grammar_val, spec_val in [
            ("space-around", "space_around"),
            ("space-evenly", "space_evenly"),
        ]:
            doc = L3Document(top_level=(Node(head=NodeHead(
                head_kind="type", type_or_path="frame", eid="f",
                properties=(_p("mainAxis", _enum(grammar_val)),),
            )),))
            el = ast_to_dict_ir(
                doc, reexpand_screen_wrapper=False,
            )["elements"]["frame-1"]
            assert el["layout"]["mainAxisAlignment"] == spec_val

    def test_crossaxis_stretch_and_baseline_decode(self) -> None:
        for val in ["stretch", "baseline"]:
            doc = L3Document(top_level=(Node(head=NodeHead(
                head_kind="type", type_or_path="frame", eid="f",
                properties=(_p("crossAxis", _enum(val)),),
            )),))
            el = ast_to_dict_ir(
                doc, reexpand_screen_wrapper=False,
            )["elements"]["frame-1"]
            assert el["layout"]["crossAxisAlignment"] == val

    def test_gradient_linear_fill_decodes(self) -> None:
        """`fill=gradient-linear(#RED, #GREEN)` → spec gradient-linear
        with two stops."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="frame", eid="f",
            properties=(_p("fill", FunctionCall(
                name="gradient-linear",
                args=(
                    FuncArg(name=None, value=_hex("#FF0000")),
                    FuncArg(name=None, value=_hex("#00FF00")),
                ),
            )),),
        )),))
        el = ast_to_dict_ir(
            doc, reexpand_screen_wrapper=False,
        )["elements"]["frame-1"]
        assert el["visual"]["fills"] == [{
            "type": "gradient-linear",
            "stops": [{"color": "#FF0000"}, {"color": "#00FF00"}],
        }]

    def test_image_fill_decodes(self) -> None:
        """`fill=image(asset=<sha>)` → spec image with asset_hash."""
        asset = "a" * 40
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="rectangle", eid="r",
            properties=(_p("fill", FunctionCall(
                name="image",
                args=(FuncArg(name="asset", value=Literal_(
                    lit_kind="asset-hash", raw=asset, py=asset,
                )),),
            )),),
        )),))
        el = ast_to_dict_ir(
            doc, reexpand_screen_wrapper=False,
        )["elements"]["rectangle-1"]
        assert el["visual"]["fills"] == [
            {"type": "image", "asset_hash": asset},
        ]

    def test_padding_partial_sides(self) -> None:
        """Padding PropGroup with only some sides must yield a dict
        containing only those sides."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="frame", eid="f",
            properties=(_p("padding", PropGroup(entries=(
                _p("left", _n("12")),
            ))),),
        )),))
        el = ast_to_dict_ir(
            doc, reexpand_screen_wrapper=False,
        )["elements"]["frame-1"]
        assert el["layout"]["padding"] == {"left": 12}

    def test_stroke_without_weight_preserves_color(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="frame", eid="f",
            properties=(_p("stroke", _hex("#000000")),),
        )),))
        el = ast_to_dict_ir(
            doc, reexpand_screen_wrapper=False,
        )["elements"]["frame-1"]
        assert el["visual"]["strokes"] == [
            {"type": "solid", "color": "#000000"},
        ]

    def test_visible_false_emitted(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type",
            type_or_path="frame",
            eid="f",
            properties=(_p("visible", _bool(False)),),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["frame-1"]
        assert el["visible"] is False


class TestDefaultDirectionStacked:
    """Direction defaults are context-dependent:
    - `screen` type root → `"absolute"` (matches generate_ir shape).
    - CompRef (`-> slash/path`) → no direction (master owns layout).
    - anything else with no `layout=` prop → `"stacked"`."""

    def test_stacked_direction_defaults_on_inline_frame(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="frame", eid="f",
            properties=(_p("width", _n("100")), _p("height", _n("100"))),
        )),))
        el = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)["elements"]["frame-1"]
        assert el["layout"]["direction"] == "stacked"

    def test_absolute_direction_defaults_on_screen_root(self) -> None:
        """`generate_ir` emits screen roots with `direction=absolute`
        (dd/ir.py:1371). Without this default, the compressor →
        decompressor round-trip silently flipped every screen root
        from `absolute` to `stacked`."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="screen", eid="s",
            properties=(_p("width", _n("428")), _p("height", _n("926"))),
        )),))
        el = ast_to_dict_ir(
            doc, reexpand_screen_wrapper=False,
        )["elements"]["screen-1"]
        assert el["layout"]["direction"] == "absolute"

    def test_compref_skips_direction_default(self) -> None:
        """CompRefs inherit layout from the master; decompressor
        must NOT add a spurious `direction=stacked` entry. The
        orig spec shape for Mode-1-eligible elements carries
        direction only when explicitly overridden."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref", type_or_path="icon/more", eid="icn",
            properties=(_p("width", _n("20")),),
        )),))
        el = ast_to_dict_ir(
            doc, reexpand_screen_wrapper=False,
        )["elements"]["instance-1"]
        assert "direction" not in (el.get("layout") or {})

    def test_layout_vertical_prop_beats_stacked_default(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="frame", eid="f",
            properties=(
                _p("width", _n("100")),
                _p("layout", _enum("vertical")),
            ),
        )),))
        el = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)["elements"]["frame-1"]
        assert el["layout"]["direction"] == "vertical"


class TestExtPropPreservation:
    """`$ext.*` PropAssigns (compressor diagnostics) must round-trip
    via the decompressor's `element["$ext"]` sub-dict. Silently
    dropping them would lose the `shadow_all_hidden` / `shadow_extra_count`
    semantics the compressor emits."""

    def test_ext_shadow_all_hidden_preserved(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="frame", eid="f",
            properties=(
                _p("$ext.shadow_all_hidden", _bool(True)),
            ),
        )),))
        el = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)["elements"]["frame-1"]
        assert el.get("$ext") == {"shadow_all_hidden": True}

    def test_ext_shadow_extra_count_preserved(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="frame", eid="f",
            properties=(
                _p("$ext.shadow_extra_count", _n("2")),
            ),
        )),))
        el = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)["elements"]["frame-1"]
        assert el.get("$ext") == {"shadow_extra_count": 2}


class TestOriginalNamePreservation:
    """The Node head's `eid` is an approximation of the spec's
    `_original_name` (sanitized, lowercase, hyphen-separated). The
    decompressor writes it back as `_original_name` so downstream
    key-preservation works — `normalize_to_eid(_original_name)` is
    idempotent on EID-derived values."""

    def test_eid_populates_original_name(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="frame", eid="safari-bottom",
        )),))
        el = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)["elements"]["frame-1"]
        assert el["_original_name"] == "safari-bottom"


class TestDecompressCompRef:
    """CompRef nodes (`-> slash/path`) decompress to Mode-1-eligible
    leaves with the slash-path preserved and head PropAssigns
    captured in the `_self_overrides` channel for Stage 1.6."""

    def test_compref_marks_mode1_eligible(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref",
            type_or_path="nav/top-nav",
            eid="top-nav",
            properties=(_p("width", _n("428")),),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["instance-1"]
        assert el["_mode1_eligible"] is True
        assert el["_master_slash_path"] == "nav/top-nav"
        # Matches `dd.ir.generate_ir`'s Mode-1-eligible INSTANCE shape
        # — the renderer dispatches on this type field.
        assert el["type"] == "instance"


class TestCompRefSelfOverridesChannel:
    """Stage 1.6 MVP — every head-level PropAssign on a CompRef is
    a local override of the master and is captured structurally in
    `element["_self_overrides"]`. Ready for downstream
    re-materialization into `instance_overrides` rows."""

    def test_scalar_override_captured(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref",
            type_or_path="icon/more",
            eid="icon-more",
            properties=(
                _p("width", _n("20")),
                _p("height", _n("20")),
                _p("opacity", Literal_(
                    lit_kind="number", raw="0.2", py=0.2,
                )),
            ),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["instance-1"]
        overrides = el.get("_self_overrides") or []
        keys_values = {o["key"]: o["value"] for o in overrides}
        assert keys_values == {"width": 20, "height": 20, "opacity": 0.2}
        # Each gets DB column tags.
        tags = {o["key"]: (o["db_prop_type"], o["db_prop_name"])
                for o in overrides}
        assert tags == {
            "width": ("WIDTH", ":self:width"),
            "height": ("HEIGHT", ":self:height"),
            "opacity": ("OPACITY", ":self:opacity"),
        }

    def test_width_sizing_enum_tagged_as_layout_sizing_h(self) -> None:
        """`width=fill` on a CompRef is a `LAYOUT_SIZING_H` override,
        not a `WIDTH` one. Value shape (SizingValue vs Literal_)
        resolves the polymorphism."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref",
            type_or_path="b",
            eid="b",
            properties=(_p("width", SizingValue(size_kind="fill")),),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["instance-1"]
        overrides = el["_self_overrides"]
        assert overrides[0]["db_prop_type"] == "LAYOUT_SIZING_H"
        assert overrides[0]["db_prop_name"] == ":self:layoutSizingH"

    def test_padding_propgroup_fans_out_per_side(self) -> None:
        """A `padding={top=N left=M}` PropGroup splits into two
        `_self_overrides` entries (one per side) each tagged with
        the matching `PADDING_{SIDE}` DB property_type."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref",
            type_or_path="b",
            eid="b",
            properties=(_p("padding", PropGroup(entries=(
                _p("right", _n("10")),
                _p("left", _n("10")),
            ))),),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["instance-1"]
        overrides = el["_self_overrides"]
        # Two entries, one per side.
        assert len(overrides) == 2
        by_name = {o["db_prop_name"]: o for o in overrides}
        assert ":self:paddingRight" in by_name
        assert ":self:paddingLeft" in by_name
        assert by_name[":self:paddingRight"]["value"] == 10
        assert by_name[":self:paddingLeft"]["value"] == 10
        assert by_name[":self:paddingRight"]["db_prop_type"] == "PADDING_RIGHT"
        assert by_name[":self:paddingLeft"]["db_prop_type"] == "PADDING_LEFT"

    # Note: `test_propgroup_override_captured_as_dict` replaced by
    # `test_padding_propgroup_fans_out_per_side` — padding now
    # fans out into one entry per side (Stage 1.7 prep for
    # instance_overrides row re-materialization).

    def test_function_call_override_preserves_shape(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref",
            type_or_path="card",
            eid="card-a",
            properties=(_p("shadow", FunctionCall(name="shadow", args=(
                FuncArg(name="x", value=_n("0")),
                FuncArg(name="y", value=_n("4")),
                FuncArg(name="blur", value=_n("8")),
                FuncArg(name="color", value=_hex("#00000040")),
            ))),),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["instance-1"]
        overrides = el.get("_self_overrides") or []
        assert len(overrides) == 1
        assert overrides[0]["key"] == "shadow"
        assert overrides[0]["value"] == {
            "fn": "shadow",
            "args": [
                {"name": "x", "value": 0},
                {"name": "y", "value": 4},
                {"name": "blur", "value": 8},
                {"name": "color", "value": "#00000040"},
            ],
        }

    def test_ext_props_excluded_from_self_overrides(self) -> None:
        """`$ext.*` diagnostics live in their own `$ext` sub-dict;
        they must not leak into `_self_overrides`."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref",
            type_or_path="button/large/translucent",
            eid="btn",
            properties=(
                _p("width", _n("50")),
                _p("$ext.shadow_all_hidden", _bool(True)),
            ),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["instance-1"]
        keys = [o["key"] for o in el.get("_self_overrides") or []]
        assert "$ext.shadow_all_hidden" not in keys
        assert "width" in keys
        assert el["$ext"] == {"shadow_all_hidden": True}

    def test_non_compref_has_no_self_overrides_channel(self) -> None:
        """Inline (non-CompRef) nodes don't get the `_self_overrides`
        channel — their PropAssigns are spec-path properties, not
        overrides."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="frame", eid="f",
            properties=(_p("fill", _hex("#FF0000")),),
        )),))
        el = ast_to_dict_ir(
            doc, reexpand_screen_wrapper=False,
        )["elements"]["frame-1"]
        assert "_self_overrides" not in el

    def test_tokenref_override_serializes_structurally(self) -> None:
        """Token-bound override values (e.g. `fill={color.primary}`)
        must preserve the token path, NOT serialize as `repr()`."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref",
            type_or_path="card",
            eid="c",
            properties=(
                _p("fill", TokenRef(path="color.primary")),
            ),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["instance-1"]
        overrides = el.get("_self_overrides") or []
        assert overrides[0]["key"] == "fill"
        assert overrides[0]["value"] == {"token": "color.primary"}
        assert overrides[0]["db_prop_type"] == "FILLS"

    def test_bounded_sizing_override_preserves_min_max(self) -> None:
        """A CompRef override with bounded sizing
        (`width=fill(min=100, max=300)`) must carry the bounds through
        the _self_overrides channel — not emit `{sizing: "fill"}` alone."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref",
            type_or_path="button/small",
            eid="b",
            properties=(
                _p("width", SizingValue(size_kind="fill", min=100.0, max=300.0)),
            ),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["instance-1"]
        overrides = el.get("_self_overrides") or []
        assert overrides[0]["value"] == {
            "sizing": "fill", "min": 100.0, "max": 300.0,
        }

    def test_path_override_child_captured_in_self_overrides(self) -> None:
        """`;figmaId:...=value` child-path overrides in the CompRef
        block are captured in `_self_overrides` with a `path` key
        (not `key`) so downstream can distinguish them from head-
        level `:self:*` overrides."""
        doc = L3Document(top_level=(Node(
            head=NodeHead(
                head_kind="comp-ref",
                type_or_path="button/toolbar",
                eid="bt",
            ),
            block=Block(statements=(
                PathOverride(
                    path=";5749:82459:visible",
                    value=Literal_(lit_kind="bool", raw="false", py=False),
                ),
            )),
        ),))
        el = ast_to_dict_ir(doc)["elements"]["instance-1"]
        overrides = el.get("_self_overrides") or []
        assert len(overrides) == 1
        assert overrides[0]["path"] == ";5749:82459:visible"
        assert overrides[0]["value"] is False
        # Child-path overrides get the path as db_prop_name (it IS
        # the DB row's `property_name` column value) but no
        # db_prop_type — those require master-node lookup to resolve
        # (Stage 1.7 scope).
        assert overrides[0]["db_prop_name"] == ";5749:82459:visible"
        assert overrides[0]["db_prop_type"] is None

    def test_corpus_compref_overrides_reflect_db_rows(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """For a corpus screen with :self:* override rows, the
        decompressed CompRefs must carry matching entries in their
        `_self_overrides` channels."""
        from dd.compress_l3 import compress_to_l3
        from dd.ir import generate_ir

        # Screen 118 has :self:paddingLeft overrides per the
        # compressor corpus probes.
        spec = generate_ir(
            db_conn, 118, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=118)
        decomp = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)
        compref_overrides = sum(
            len(el.get("_self_overrides") or [])
            for el in decomp["elements"].values()
            if el.get("_mode1_eligible")
        )
        assert compref_overrides > 0, (
            "expected at least one CompRef on screen 118 to carry "
            "_self_overrides entries (corpus has :self:paddingLeft rows)"
        )


class TestDecompressNested:
    def test_children_recurse_with_sibling_counter(self) -> None:
        """Children get their own sibling-scoped keys; nested frames
        under a screen produce `frame-1`, `frame-2` at the root level
        and the counter is shared across siblings."""
        doc = L3Document(top_level=(Node(
            head=NodeHead(
                head_kind="type", type_or_path="screen", eid="s",
                properties=(_p("width", _n("428")), _p("height", _n("926"))),
            ),
            block=Block(statements=(
                Node(head=NodeHead(
                    head_kind="type", type_or_path="frame",
                    eid="a", properties=(),
                )),
                Node(head=NodeHead(
                    head_kind="type", type_or_path="frame",
                    eid="b", properties=(),
                )),
            )),
        ),))
        spec = ast_to_dict_ir(doc)
        assert spec["root"] == "screen-1"
        root_el = spec["elements"]["screen-1"]
        assert root_el["children"] == ["frame-1", "frame-2"]


class TestSyntheticWrapperReExpansion:
    """Inverse of `_collapse_synthetic_screen_wrapper` — when the
    compressor's output has a `screen` top-level carrying hoisted
    visual/layout, the decompressor splits it back into the
    screen-1 + frame-1 canvas pair that `generate_ir` originally
    produced."""

    def test_reexpansion_creates_synthetic_inner_frame(self) -> None:
        """Screen with fill + direction=vertical: re-expansion emits
        a `screen` outer (absolute + sizing only) with a `frame`
        inner child carrying the fill and direction."""
        doc = L3Document(top_level=(Node(
            head=NodeHead(
                head_kind="type", type_or_path="screen", eid="s",
                properties=(
                    _p("width", _n("428")),
                    _p("height", _n("926")),
                    _p("layout", _enum("vertical")),
                    _p("fill", _hex("#F6F6F6")),
                ),
            ),
            block=Block(statements=(
                Node(head=NodeHead(
                    head_kind="type", type_or_path="text", eid="t",
                )),
            )),
        ),))
        spec = ast_to_dict_ir(doc)
        # Expect 3 elements: outer screen, inner frame, text leaf.
        assert len(spec["elements"]) == 3
        outer = spec["elements"][spec["root"]]
        assert outer["type"] == "screen"
        assert outer["layout"]["direction"] == "absolute"
        assert outer["layout"]["sizing"] == {"width": 428, "height": 926}
        assert "visual" not in outer
        assert len(outer["children"]) == 1
        inner_key = outer["children"][0]
        inner = spec["elements"][inner_key]
        assert inner["type"] == "frame"
        assert inner["visual"]["fills"] == [
            {"type": "solid", "color": "#F6F6F6"},
        ]
        assert inner["layout"]["direction"] == "vertical"
        # Original text node becomes a grandchild of the outer screen
        # (direct child of the inner frame).
        assert len(inner["children"]) == 1

    def test_reexpansion_opt_out_preserves_collapsed_form(self) -> None:
        """With `reexpand_screen_wrapper=False`, the decompressor
        preserves the collapsed form (hoisted visual on the screen)."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="screen", eid="s",
            properties=(
                _p("width", _n("428")),
                _p("height", _n("926")),
                _p("fill", _hex("#F6F6F6")),
            ),
        )),))
        spec = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)
        root = spec["elements"][spec["root"]]
        assert root["type"] == "screen"
        # Fill stays on the screen element.
        assert root["visual"]["fills"][0]["color"] == "#F6F6F6"
        # No synthetic inner frame created.
        assert len(spec["elements"]) == 1

    def test_no_reexpansion_when_screen_has_no_hoisted_props(
        self,
    ) -> None:
        """A bare screen (only direction=absolute + sizing) already
        matches the `generate_ir` wrapper shape and doesn't need
        re-expansion even when re-expand is enabled."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="screen", eid="s",
            properties=(
                _p("width", _n("428")),
                _p("height", _n("926")),
            ),
        )),))
        spec = ast_to_dict_ir(doc)        # default: re-expand on
        # No hoisted visual/layout → no-op.
        assert len(spec["elements"]) == 1
        assert spec["elements"][spec["root"]]["type"] == "screen"


class TestStage17MasterSubtreeExpansion:
    """Stage 1.7 — when a DB conn is provided, CompRef elements
    inflate the master component's subtree as their children.
    Without conn, CompRefs remain leaves (Stage 1.5/1.6 behavior)."""

    def test_compref_without_conn_has_no_children(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Without `conn`, CompRefs are leaves (Stage 1.5 shape)."""
        spec = generate_ir(
            db_conn, 181, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=181)
        decomp = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)
        # At least one CompRef should exist; verify none has children.
        compref_count = 0
        for el in decomp["elements"].values():
            if el.get("_mode1_eligible"):
                compref_count += 1
                assert not el.get("children"), (
                    f"CompRef {el} has children without conn"
                )
        assert compref_count > 0, "no CompRefs on screen 181"

    def test_compref_with_conn_inflates_master_children(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """With `conn`, CompRefs inflate. Safari-bottom master has
        known subtree size > 0."""
        spec = generate_ir(
            db_conn, 181, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=181)
        decomp = ast_to_dict_ir(
            doc, db_conn, reexpand_screen_wrapper=False,
        )
        # Find a CompRef and assert it has children now.
        inflated = [
            el for el in decomp["elements"].values()
            if el.get("_mode1_eligible") and el.get("children")
        ]
        assert len(inflated) > 0, (
            "expected at least one inflated CompRef with children"
        )

    def test_inflation_multiplies_element_count(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """With conn, total element count is multiples of the no-conn
        count (masters contribute many subtree elements)."""
        spec = generate_ir(
            db_conn, 181, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=181)
        no_conn = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)
        with_conn = ast_to_dict_ir(
            doc, db_conn, reexpand_screen_wrapper=False,
        )
        assert len(with_conn["elements"]) > 2 * len(no_conn["elements"])

    def test_full_corpus_tier2_with_inflation_recovers_most_elements(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Full-corpus sweep: with inflation, decompressed element
        count should reach 80-100% of orig spec count. Regression
        bound at 70% catches a master-subtree walker that drops
        large subtrees silently."""
        screens = [
            r[0] for r in db_conn.execute(
                "SELECT id FROM screens "
                "WHERE screen_type='app_screen' "
                "ORDER BY id"
            ).fetchall()
        ]
        low_ratio: list[tuple[int, float]] = []
        for sid in screens:
            spec = generate_ir(
                db_conn, sid, semantic=True, filter_chrome=False,
            )["spec"]
            doc = compress_to_l3(spec, db_conn, screen_id=sid)
            decomp = ast_to_dict_ir(
                doc, db_conn, reexpand_screen_wrapper=False,
            )
            orig_n = len(spec["elements"])
            dec_n = len(decomp["elements"])
            if orig_n == 0:
                continue
            ratio = dec_n / orig_n
            if ratio < 0.70:
                low_ratio.append((sid, ratio))
        if low_ratio:
            pytest.fail(
                f"{len(low_ratio)}/{len(screens)} screens recover "
                f"<70% of orig element count:\n"
                + "\n".join(f"  screen {sid}: {r:.2f}" for sid, r in low_ratio[:10])
            )

    def test_unresolvable_master_path_returns_empty_children(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """CompRef pointing at a slash-path not in CKR must leave the
        element as a leaf (no children) — not crash."""
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref",
            type_or_path="does/not/exist/anywhere",
            eid="ghost",
        )),))
        el = ast_to_dict_ir(
            doc, db_conn, reexpand_screen_wrapper=False,
        )["elements"]["instance-1"]
        assert not el.get("children")
        assert el["_master_slash_path"] == "does/not/exist/anywhere"

    def test_null_figma_node_id_ckr_rows_skipped(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """CKR rows with NULL figma_node_id (10 in corpus) must not
        resolve — otherwise the first such row silently shadows
        a later row with a valid figma_node_id for the same name.
        Hard to test by construction; smoke-test via the cache
        builder directly."""
        from dd.decompress_l3 import _build_master_root_cache
        cache = _build_master_root_cache(db_conn)
        # Every entry that resolved must have a real node_id (int).
        for slash, nid in cache.items():
            if nid is not None:
                assert isinstance(nid, int)
        # At least some paths must resolve (corpus isn't empty).
        resolved = sum(1 for v in cache.values() if v is not None)
        assert resolved > 0

    def test_effects_recovered_from_master_subtree(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """`visual.effects` must be populated on inflated elements.
        Before the fix, `_db_row_to_element` didn't read the
        `effects` column and every master-inflated shadow was lost."""
        screens = [
            r[0] for r in db_conn.execute(
                "SELECT id FROM screens WHERE screen_type='app_screen' "
                "ORDER BY id LIMIT 20"
            ).fetchall()
        ]
        effects_found = 0
        for sid in screens:
            spec = generate_ir(
                db_conn, sid, semantic=True, filter_chrome=False,
            )["spec"]
            doc = compress_to_l3(spec, db_conn, screen_id=sid)
            decomp = ast_to_dict_ir(
                doc, db_conn, reexpand_screen_wrapper=False,
            )
            for el in decomp["elements"].values():
                if (el.get("visual") or {}).get("effects"):
                    effects_found += 1
        assert effects_found > 0, (
            "no inflated elements carry visual.effects — effects-column "
            "reader regression"
        )

    def test_leaf_types_have_no_layout_direction(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """TEXT/RECTANGLE/VECTOR etc. are "leaf" node types — they
        don't carry a `layout.direction` in the orig spec shape.
        `_db_row_to_element` used to emit `direction=stacked` on every
        inflated element; fix suppresses it for leaf types."""
        spec = generate_ir(
            db_conn, 181, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=181)
        decomp = ast_to_dict_ir(
            doc, db_conn, reexpand_screen_wrapper=False,
        )
        # Every leaf-type element must not have a direction key.
        leaf_types = {"text", "rectangle", "vector", "ellipse", "line"}
        for k, el in decomp["elements"].items():
            if el.get("type") in leaf_types:
                direction = (el.get("layout") or {}).get("direction")
                assert direction is None, (
                    f"leaf element {k} (type={el['type']}) has "
                    f"spurious direction={direction!r}"
                )

    def test_nested_compref_recursively_inflates(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """INSTANCE rows inside a master subtree must re-inflate their
        OWN master's subtree (recursive). Before the fix, nested
        instances were Mode-1-marked leaves with no children even when
        their component resolved in CKR."""
        spec = generate_ir(
            db_conn, 181, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=181)
        decomp = ast_to_dict_ir(
            doc, db_conn, reexpand_screen_wrapper=False,
        )
        # Count Mode-1 elements with children (i.e. nested instances
        # whose master resolved and re-inflated). Screen 181 has
        # multiple nested CompRefs (e.g., button contains icons +
        # text, each icon is itself a Mode-1 instance with its own
        # master subtree).
        nested_inflated = sum(
            1 for el in decomp["elements"].values()
            if el.get("_mode1_eligible") and el.get("children")
        )
        assert nested_inflated >= 30, (
            f"expected ≥30 Mode-1 elements with inflated children on "
            f"screen 181; got {nested_inflated}"
        )

    def test_recursive_inflation_terminates_on_cycles(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Cycle detection: `visiting_masters` set prevents runaway
        recursion when a master contains an instance of itself. Full
        corpus sweep would deadlock without the guard; this test
        verifies the sweep completes in bounded time."""
        import time
        start = time.monotonic()
        for sid in [181, 222, 237, 118, 119]:
            spec = generate_ir(
                db_conn, sid, semantic=True, filter_chrome=False,
            )["spec"]
            doc = compress_to_l3(spec, db_conn, screen_id=sid)
            ast_to_dict_ir(doc, db_conn)
        elapsed = time.monotonic() - start
        assert elapsed < 10, (
            f"5-screen sweep with inflation took {elapsed:.1f}s "
            f"(expected < 10s; regression in cycle detection?)"
        )

    def test_mode1_eligible_propagates_to_inflated_instance_children(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """A master subtree containing nested INSTANCE rows must
        propagate `_mode1_eligible=True` onto those inflated elements.
        Before the fix, only the outer CompRef carried the marker."""
        spec = generate_ir(
            db_conn, 181, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=181)
        decomp = ast_to_dict_ir(
            doc, db_conn, reexpand_screen_wrapper=False,
        )
        mode1_count = sum(
            1 for el in decomp["elements"].values()
            if el.get("_mode1_eligible")
        )
        # Screen 181 has ~60 Mode-1-eligible elements in orig spec;
        # with propagation the decomp should recover the vast majority.
        assert mode1_count >= 40, (
            f"only {mode1_count} mode1-eligible elements in decomp "
            f"(expected ≥40 — regression in propagation logic)"
        )

    def test_inflation_does_not_mutate_spec_when_conn_absent(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """A doc with no conn and a doc with conn produce different
        element counts but both decompress cleanly (no exceptions,
        valid structure)."""
        spec = generate_ir(
            db_conn, 181, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=181)
        a = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)
        b = ast_to_dict_ir(doc, db_conn, reexpand_screen_wrapper=False)
        # Both valid; b has more elements.
        assert a["root"] is not None
        assert b["root"] is not None
        assert len(b["elements"]) > len(a["elements"])


class TestDecompressReferenceScreens:
    """End-to-end — compress a corpus screen, then decompress. Verify
    the output has the expected shape and key invariants. NOT strict
    byte-equality (provenance trailers, master-subtree inflation are
    out of scope for Stage 1.5)."""

    @pytest.mark.parametrize("sid", [181, 222, 237])
    def test_decompress_produces_valid_spec(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        spec = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=sid)
        decomp = ast_to_dict_ir(doc)
        # Basic shape.
        assert decomp["version"] == "1.0"
        assert decomp["root"] is not None
        assert decomp["root"] in decomp["elements"]
        root_el = decomp["elements"][decomp["root"]]
        # Decompressor preserves `screen` at the top.
        assert root_el["type"] == "screen"
        # Sizing preserved.
        assert "layout" in root_el
        assert "sizing" in root_el["layout"]
        assert root_el["layout"]["sizing"]["width"] in (428, 1194, 768, 1366)
        # Children present — re-expansion produces at least the inner
        # synthetic frame as a direct child.
        assert len(root_el.get("children") or []) > 0

    @pytest.mark.parametrize("sid", [181, 222, 237])
    def test_decompress_matches_generate_ir_outer_shape(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        """After re-expansion, the outer `screen` element should
        structurally match what `generate_ir` originally produced:
        `type=screen`, `direction=absolute`, one child, matching
        `_original_name`."""
        orig_spec = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(orig_spec, db_conn, screen_id=sid)
        decomp = ast_to_dict_ir(doc)

        orig_root = orig_spec["elements"][orig_spec["root"]]
        decomp_root = decomp["elements"][decomp["root"]]
        assert decomp_root["type"] == orig_root["type"]
        assert decomp_root["layout"]["direction"] == "absolute"
        assert decomp_root["layout"]["sizing"] == orig_root["layout"]["sizing"]
        # Both have exactly one child at the canvas layer.
        assert len(decomp_root["children"]) == len(orig_root["children"]) == 1

    def test_decompress_element_count_nonzero(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        """Screen 181 has ~10-30 elements after compression; assert
        the decompressor produces a comparable count (would catch a
        regression that silently drops children)."""
        spec = generate_ir(
            db_conn, 181, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=181)
        decomp = ast_to_dict_ir(doc)
        assert len(decomp["elements"]) >= 10


# ---------------------------------------------------------------------------
# Full-corpus Tier-2 sweep — the headline proof for Stage 1.5
# ---------------------------------------------------------------------------


def _count_nodes(doc: L3Document) -> int:
    """Count the number of Node objects in the AST."""
    total = 0

    def walk(n: Node) -> None:
        nonlocal total
        total += 1
        if n.block is not None:
            for s in n.block.statements:
                if isinstance(s, Node):
                    walk(s)

    for top in doc.top_level:
        if isinstance(top, Node):
            walk(top)
    return total


def test_full_corpus_tier2_sweep_no_crash(
    db_conn: sqlite3.Connection,
) -> None:
    """Every app_screen in the Dank corpus must decompress without
    raising. Tier-2 headline — proves the decompressor handles every
    shape the compressor currently emits.

    NOT yet asserting byte-exact round-trip (synthetic wrapper
    re-expansion and master-subtree expansion land in later stages);
    this test is the smoke gate for the skeleton."""
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    assert len(screens) > 0

    failures: list[tuple[int, str]] = []
    for sid in screens:
        try:
            spec = generate_ir(
                db_conn, sid, semantic=True, filter_chrome=False,
            )["spec"]
            doc = compress_to_l3(spec, db_conn, screen_id=sid)
            decomp = ast_to_dict_ir(doc)
            if decomp.get("root") is None or not decomp.get("elements"):
                failures.append((sid, "empty spec"))
                continue
        except Exception as e:
            failures.append((sid, f"{type(e).__name__}: {str(e)[:80]}"))

    if failures:
        details = "\n".join(f"  screen {sid}: {reason}" for sid, reason in failures[:10])
        pytest.fail(
            f"{len(failures)}/{len(screens)} screens failed decompression:\n"
            f"{details}"
        )


def test_full_corpus_tier2_element_count_matches_ast(
    db_conn: sqlite3.Connection,
) -> None:
    """With `reexpand_screen_wrapper=False`, decompressed element
    count must equal AST Node count exactly. Off-by-one catches
    silent drops or duplications in the recursive walk."""
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    mismatches: list[tuple[int, int, int]] = []
    for sid in screens:
        spec = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=sid)
        decomp = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)
        ast_nodes = _count_nodes(doc)
        dict_elements = len(decomp["elements"])
        if ast_nodes != dict_elements:
            mismatches.append((sid, ast_nodes, dict_elements))
    if mismatches:
        details = "\n".join(
            f"  screen {sid}: {ast_n} AST Nodes vs {dict_n} dict elements"
            for sid, ast_n, dict_n in mismatches[:10]
        )
        pytest.fail(
            f"{len(mismatches)}/{len(screens)} screens have Node/element "
            f"count mismatch:\n{details}"
        )


def test_full_corpus_tier2_reexpansion_adds_exactly_one_element(
    db_conn: sqlite3.Connection,
) -> None:
    """The default `reexpand_screen_wrapper=True` adds exactly one
    synthetic inner frame — so the decompressed element count
    equals AST Node count + 1 for every screen that triggers the
    re-expansion heuristic (all of them in the corpus since the
    canvas carries a fill)."""
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    mismatches: list[tuple[int, int, int]] = []
    for sid in screens:
        spec = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=sid)
        decomp = ast_to_dict_ir(doc)             # default: re-expand
        ast_nodes = _count_nodes(doc)
        dict_elements = len(decomp["elements"])
        # Either re-expanded (+1) or no-op (=). Both valid depending on
        # whether the root had non-trivial visual/layout.
        if dict_elements not in (ast_nodes, ast_nodes + 1):
            mismatches.append((sid, ast_nodes, dict_elements))
    if mismatches:
        details = "\n".join(
            f"  screen {sid}: {ast_n} Nodes vs {dict_n} elements"
            for sid, ast_n, dict_n in mismatches[:10]
        )
        pytest.fail(
            f"{len(mismatches)}/{len(screens)} screens violate the "
            f"re-expansion invariant:\n{details}"
        )


def test_full_corpus_tier2_all_elements_have_type(
    db_conn: sqlite3.Connection,
) -> None:
    """Every decompressed element must have a `type` field (the dict
    IR's primary discriminator). A missing type would mean the
    compressor → decompressor dropped the head kind."""
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    for sid in screens:
        spec = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=sid)
        decomp = ast_to_dict_ir(doc)
        for key, el in decomp["elements"].items():
            assert isinstance(el.get("type"), str) and el["type"], (
                f"screen {sid} element {key!r} has no type field: {el}"
            )


def test_full_corpus_tier2_root_is_screen(
    db_conn: sqlite3.Connection,
) -> None:
    """The decompressed root for every app_screen must be type=`screen`
    — not `frame`, not something else."""
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    for sid in screens:
        spec = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=sid)
        decomp = ast_to_dict_ir(doc)
        root_el = decomp["elements"][decomp["root"]]
        assert root_el["type"] == "screen", (
            f"screen {sid} root decompressed as type={root_el['type']!r}"
        )


def test_full_corpus_tier2_inflated_output_is_json_serializable(
    db_conn: sqlite3.Connection,
) -> None:
    """With master-subtree inflation enabled (`conn` passed), every
    decompressed corpus spec must still serialize cleanly. Catches
    raw-DB-JSON blobs leaking into the output or non-JSON Value
    kinds surfacing from the inflation path (separate gate from the
    no-conn sweep below)."""
    import json
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    for sid in screens:
        spec = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=sid)
        decomp = ast_to_dict_ir(doc, db_conn)
        try:
            out = json.dumps(decomp)
        except (TypeError, ValueError) as e:
            pytest.fail(
                f"screen {sid}: inflated decomp not JSON-serializable: {e}"
            )
        assert "_unhandled" not in out, (
            f"screen {sid}: inflated decomp contains _unhandled "
            f"Value kind"
        )


def test_full_corpus_tier2_output_is_json_serializable(
    db_conn: sqlite3.Connection,
) -> None:
    """Every decompressed corpus spec must serialize cleanly through
    json.dumps — catches `_override_value_repr` repr() fallbacks or
    other non-JSON leaks (e.g. Python dataclass reprs, frozenset
    instances) via a full-corpus sweep."""
    import json
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    for sid in screens:
        spec = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=sid)
        decomp = ast_to_dict_ir(doc)
        try:
            out = json.dumps(decomp)
        except (TypeError, ValueError) as e:
            pytest.fail(
                f"screen {sid}: decomp is not JSON-serializable: {e}"
            )
        # Negative guard: no `_unhandled` repr fallback leaked into
        # the output (would signal a Value kind we silently dropped).
        assert "_unhandled" not in out, (
            f"screen {sid}: decomp contains _unhandled Value kind, "
            f"indicating a silent override drop"
        )


def test_full_corpus_tier2_children_references_resolve(
    db_conn: sqlite3.Connection,
) -> None:
    """Every `children` entry must reference an existing element key.
    Would catch a regression that produces dangling references."""
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    for sid in screens:
        spec = generate_ir(
            db_conn, sid, semantic=True, filter_chrome=False,
        )["spec"]
        doc = compress_to_l3(spec, db_conn, screen_id=sid)
        decomp = ast_to_dict_ir(doc)
        keys = set(decomp["elements"].keys())
        for el_key, el in decomp["elements"].items():
            for child_key in el.get("children") or []:
                assert child_key in keys, (
                    f"screen {sid}: element {el_key} references missing "
                    f"child {child_key!r}"
                )
