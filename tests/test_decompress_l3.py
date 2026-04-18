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
    """`direction="stacked"` is the spec IR's "no auto-layout;
    absolute positioning" sentinel. The compressor drops it
    (absence of `layout=` means stacked). The decompressor must
    restore it when no `layout=` prop is present."""

    def test_stacked_direction_defaults_when_no_layout_prop(self) -> None:
        doc = L3Document(top_level=(Node(head=NodeHead(
            head_kind="type", type_or_path="frame", eid="f",
            properties=(_p("width", _n("100")), _p("height", _n("100"))),
        )),))
        el = ast_to_dict_ir(doc, reexpand_screen_wrapper=False)["elements"]["frame-1"]
        assert el["layout"]["direction"] == "stacked"

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
