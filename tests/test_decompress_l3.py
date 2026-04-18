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
    PropAssign,
    PropGroup,
    SizingValue,
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

    def test_visible_false_emitted(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type",
            type_or_path="frame",
            eid="f",
            properties=(_p("visible", _bool(False)),),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["frame-1"]
        assert el["visible"] is False


class TestDecompressCompRef:
    """CompRef nodes (`-> slash/path`) decompress to Mode-1-eligible
    leaves with the slash-path preserved."""

    def test_compref_marks_mode1_eligible(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="comp-ref",
            type_or_path="nav/top-nav",
            eid="top-nav",
            properties=(_p("width", _n("428")),),
        )),))
        el = ast_to_dict_ir(doc)["elements"]["frame-1"]
        assert el["_mode1_eligible"] is True
        assert el["_master_slash_path"] == "nav/top-nav"
        assert el["type"] == "frame"


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


class TestDecompressReferenceScreens:
    """End-to-end — compress a corpus screen, then decompress. Verify
    the output has the expected shape and key invariants. NOT strict
    byte-equality (provenance trailers, synthetic-wrapper re-expansion,
    and master-subtree inflation are out of scope for Stage 1.5)."""

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
        # Children present (the collapsed screen has the canvas's
        # grandchildren directly).
        assert len(root_el.get("children") or []) > 0

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
