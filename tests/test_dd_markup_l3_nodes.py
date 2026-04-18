"""Stage 1.2 slice D–I — full-node parser tests.

Unconditional tests (no pytest.mark.skip) for the parser's Node, Block,
Define, Value-form, and Trailer productions. Runs against the shipped
parser in `dd/markup_l3.py`.

Emitter-dependent tests live elsewhere (pending Stage 1.3/1.4).
Semantic-check tests (`KIND_AMBIGUOUS_PARAM`, etc.) live in
`test_dd_markup_l3.py` behind a module-level skip until those slices
ship.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dd.markup_l3 import (
    Block,
    ComponentRefValue,
    Define,
    FunctionCall,
    Literal_,
    Node,
    NodeHead,
    NodeTrailer,
    PathOverride,
    PatternRefValue,
    PropAssign,
    PropGroup,
    SizingValue,
    SlotFill,
    SlotPlaceholder,
    TokenRef,
    ValueTrailer,
    parse_l3,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "markup"


# ---------------------------------------------------------------------------
# Happy-path fixture parsing — all three reference fixtures must parse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", [
    "01-login-welcome", "02-card-sheet", "03-keyboard-sheet",
])
def test_fixture_parses(slug: str) -> None:
    """Every hand-authored fixture under tests/fixtures/markup/ parses cleanly."""
    source = (FIXTURE_DIR / f"{slug}.dd").read_text()
    doc = parse_l3(source, source_path=slug)
    assert doc is not None
    assert len(doc.top_level) > 0, f"{slug} produced zero top-level items"


def test_fixture_01_has_expected_structure() -> None:
    """Fixture 01 exposes a Define + a screen Node, both well-formed."""
    source = (FIXTURE_DIR / "01-login-welcome.dd").read_text()
    doc = parse_l3(source)

    assert doc.namespace == "dank.reference.screen-181"
    assert len(doc.tokens) == 3                # brand gradient stops + gradient

    assert len(doc.top_level) == 2
    define, screen = doc.top_level

    # Define
    assert isinstance(define, Define)
    assert define.name == "option-row"
    assert len(define.params) == 3             # title + cta_label + slot cta
    param_kinds = [p.param_kind for p in define.params]
    assert "scalar" in param_kinds
    assert "slot" in param_kinds

    # Screen
    assert isinstance(screen, Node)
    assert screen.head.head_kind == "type"
    assert screen.head.type_or_path == "screen"
    assert screen.head.eid == "login-welcome"
    assert screen.head.trailer is not None
    assert screen.head.trailer.kind == "extracted"
    assert screen.block is not None


def test_fixture_02_has_two_defines() -> None:
    """Fixture 02 has preset-tile and card-section defines + screen."""
    source = (FIXTURE_DIR / "02-card-sheet.dd").read_text()
    doc = parse_l3(source)

    define_names = [tl.name for tl in doc.top_level if isinstance(tl, Define)]
    assert "preset-tile" in define_names
    assert "card-section" in define_names

    screens = [tl for tl in doc.top_level if isinstance(tl, Node)]
    assert len(screens) == 1
    assert screens[0].head.eid == "card-sheet"


def test_fixture_03_uses_cross_file_import() -> None:
    """Fixture 03 imports sheet22 alias and uses it extensively."""
    source = (FIXTURE_DIR / "03-keyboard-sheet.dd").read_text()
    doc = parse_l3(source)

    assert any(u.alias == "sheet22" and u.is_relative for u in doc.uses)
    # No KIND_UNUSED_IMPORT — sheet22 is referenced via scope aliases.
    unused = [w for w in doc.warnings if w.kind == "KIND_UNUSED_IMPORT"]
    assert not unused


# ---------------------------------------------------------------------------
# Value forms
# ---------------------------------------------------------------------------


class TestValueForms:
    def test_function_call_gradient_linear(self) -> None:
        doc = parse_l3(
            'tokens { color.accent = gradient-linear(#D9FF40, #9EFF85) }'
        )
        v = doc.tokens[0].value
        assert isinstance(v, FunctionCall)
        assert v.name == "gradient-linear"
        assert len(v.args) == 2
        assert v.args[0].name is None          # positional
        assert v.args[0].value.lit_kind == "hex-color"

    def test_function_call_keyword_arg(self) -> None:
        doc = parse_l3(
            'tokens { img.bg = image(asset=79b6dbeb4ccba396c2fc87649fce708791aeab02) }'
        )
        v = doc.tokens[0].value
        assert isinstance(v, FunctionCall)
        assert v.name == "image"
        assert v.args[0].name == "asset"
        assert v.args[0].value.lit_kind == "asset-hash"

    def test_prop_group(self) -> None:
        doc = parse_l3(
            'screen #s { padding={top=8 right=12 bottom=8 left=12} }'
        )
        pad = doc.top_level[0].block.statements[0]
        assert isinstance(pad, PropAssign)
        assert isinstance(pad.value, PropGroup)
        keys = [e.key for e in pad.value.entries]
        assert keys == ["top", "right", "bottom", "left"]

    def test_sizing_bare(self) -> None:
        doc = parse_l3('screen #s { width=fill height=hug }')
        stmts = doc.top_level[0].block.statements
        w, h = stmts[0], stmts[1]
        assert isinstance(w.value, SizingValue)
        assert w.value.size_kind == "fill"
        assert h.value.size_kind == "hug"

    def test_sizing_bounded(self) -> None:
        doc = parse_l3('screen #s { width=fill(min=320, max=480) }')
        w = doc.top_level[0].block.statements[0]
        assert isinstance(w.value, SizingValue)
        assert w.value.size_kind == "fill"
        assert w.value.min == 320.0
        assert w.value.max == 480.0

    def test_token_ref_in_value_position(self) -> None:
        doc = parse_l3('screen #s { fill={color.surface.default} }')
        stmt = doc.top_level[0].block.statements[0]
        assert isinstance(stmt.value, TokenRef)
        assert stmt.value.path == "color.surface.default"

    def test_enum_literal(self) -> None:
        doc = parse_l3('screen #s { layout=vertical align=center }')
        stmts = doc.top_level[0].block.statements
        assert stmts[0].value.lit_kind == "enum"
        assert stmts[0].value.py == "vertical"
        assert stmts[1].value.lit_kind == "enum"

    def test_comp_ref_as_value(self) -> None:
        """`slot cta = -> button/small/solid(label=x)` — CompRef as slot default."""
        source = """
        define o(slot cta = -> button/small/solid(label="Go")) {
          frame #body { {cta} }
        }
        """.strip()
        doc = parse_l3(source)
        define = doc.top_level[0]
        cta_param = [p for p in define.params if p.name == "cta"][0]
        assert isinstance(cta_param.default, Node)
        assert cta_param.default.head.head_kind == "comp-ref"
        assert cta_param.default.head.type_or_path == "button/small/solid"
        assert len(cta_param.default.head.override_args) == 1


# ---------------------------------------------------------------------------
# Node heads — type, comp-ref, pattern-ref, positional, trailers
# ---------------------------------------------------------------------------


class TestNodeHeads:
    def test_type_node_with_eid(self) -> None:
        doc = parse_l3('screen #login {}'.replace("{}", '{ width=1 }'))
        screen = doc.top_level[0]
        assert screen.head.type_or_path == "screen"
        assert screen.head.eid == "login"

    def test_comp_ref_with_eid_and_props(self) -> None:
        doc = parse_l3('screen #s { -> nav/top-nav #top x=0 y=0 }')
        ref = doc.top_level[0].block.statements[0]
        assert ref.head.head_kind == "comp-ref"
        assert ref.head.type_or_path == "nav/top-nav"
        assert ref.head.eid == "top"

    def test_pattern_ref_with_scope_alias(self) -> None:
        doc = parse_l3('screen #s { & sheet22::card-section #sec heading="x" }')
        ref = doc.top_level[0].block.statements[0]
        assert ref.head.head_kind == "pattern-ref"
        assert ref.head.scope_alias == "sheet22"
        assert ref.head.type_or_path == "card-section"

    def test_positional_string_on_text_node(self) -> None:
        doc = parse_l3('screen #s { text "hello" color={color.text.default} }')
        text = doc.top_level[0].block.statements[0]
        assert text.head.positional is not None
        assert text.head.positional.lit_kind == "string"
        assert text.head.positional.py == "hello"

    def test_positional_multiline_string(self) -> None:
        src = (
            'screen #s { text \n'
            '  """line one\n'
            '  line two"""\n'
            '  color={color.text.default}\n'
            '}'
        )
        doc = parse_l3(src)
        text = doc.top_level[0].block.statements[0]
        assert text.head.positional is not None
        assert text.head.positional.lit_kind == "string"

    def test_node_trailer_on_head(self) -> None:
        doc = parse_l3('screen #s (extracted src=181) { width=1 }')
        screen = doc.top_level[0]
        assert screen.head.trailer is not None
        assert screen.head.trailer.kind == "extracted"
        attrs = dict(screen.head.trailer.attrs)
        assert "src" in attrs

    def test_value_trailer_on_property(self) -> None:
        doc = parse_l3(
            'screen #s { fill=#F8F8F8 #[user-edited reason="brand"] }'
        )
        fill = doc.top_level[0].block.statements[0]
        assert isinstance(fill, PropAssign)
        assert fill.trailer is not None
        assert fill.trailer.kind == "user-edited"

    def test_value_trailer_on_continuation_line(self) -> None:
        """The real fixture has the trailer on a subsequent line."""
        src = (
            'screen #s {\n'
            '  rectangle #bg\n'
            '      fill=#F8F8F8\n'
            '        #[extracted src="node:21616"]\n'
            '      visible=false\n'
            '}'
        )
        doc = parse_l3(src)
        rect = doc.top_level[0].block.statements[0]
        fill = [p for p in rect.head.properties
                if isinstance(p, PropAssign) and p.key == "fill"][0]
        assert fill.trailer is not None
        assert fill.trailer.kind == "extracted"


# ---------------------------------------------------------------------------
# Block statements — nodes, slot-fills, slot-placeholders, overrides
# ---------------------------------------------------------------------------


class TestBlockStatements:
    def test_slot_placeholder(self) -> None:
        src = """
        define o(slot cta) { frame #h { {cta} } }
        """.strip()
        doc = parse_l3(src)
        frame = doc.top_level[0].body.statements[0]
        placeholder = frame.block.statements[0]
        assert isinstance(placeholder, SlotPlaceholder)
        assert placeholder.name == "cta"

    def test_slot_fill_with_node_rhs(self) -> None:
        """Inside a pattern-ref Block, `body = frame ...` is a SlotFill."""
        src = """
        define row(slot body) { frame #r { {body} } }
        screen #s { & row #r1 { body = frame #x fill=#FFFFFF } }
        """.strip()
        doc = parse_l3(src)
        screen = [t for t in doc.top_level if isinstance(t, Node)][0]
        ref = screen.block.statements[0]
        stmt = ref.block.statements[0]
        assert isinstance(stmt, SlotFill)
        assert stmt.slot_name == "body"
        assert isinstance(stmt.node, Node)

    def test_path_override_dotted_key(self) -> None:
        doc = parse_l3(
            'screen #s { & row #r1 title="x" container.gap=8 }'
        )
        ref = doc.top_level[0].block.statements[0]
        overrides = [p for p in ref.head.properties if isinstance(p, PathOverride)]
        assert len(overrides) == 1
        assert overrides[0].path == "container.gap"

    def test_prop_assign_with_type_keyword_as_key(self) -> None:
        """`text="Done"` inside a CompRef block is a PropAssign where
        `text` is the key (Figma instance override), not a text node."""
        doc = parse_l3(
            'screen #s { -> button/small/solid #done { text="Done" } }'
        )
        ref = doc.top_level[0].block.statements[0]
        stmt = ref.block.statements[0]
        assert isinstance(stmt, PropAssign)
        assert stmt.key == "text"
        assert stmt.value.lit_kind == "string"
        assert stmt.value.py == "Done"


# ---------------------------------------------------------------------------
# Defines — three parametrization primitives
# ---------------------------------------------------------------------------


class TestDefines:
    def test_scalar_param_with_default(self) -> None:
        src = 'define f(title: text = "x") { frame #b }'
        doc = parse_l3(src)
        p = doc.top_level[0].params[0]
        assert p.param_kind == "scalar"
        assert p.name == "title"
        assert p.type_hint == "text"
        assert p.default.lit_kind == "string"

    def test_slot_param_with_node_default(self) -> None:
        src = 'define f(slot body = frame #default) { frame #b { {body} } }'
        doc = parse_l3(src)
        p = doc.top_level[0].params[0]
        assert p.param_kind == "slot"
        assert isinstance(p.default, Node)

    def test_slot_param_no_default(self) -> None:
        src = 'define f(slot body) { frame #b { {body} } }'
        doc = parse_l3(src)
        p = doc.top_level[0].params[0]
        assert p.param_kind == "slot"
        assert p.default is None


# ---------------------------------------------------------------------------
# $ext extension metadata
# ---------------------------------------------------------------------------


def test_ext_metadata_at_node_level() -> None:
    doc = parse_l3(
        'screen #s { $ext.figma_page = "Home" $ext.dank.tag = "v1" }'
    )
    stmts = doc.top_level[0].block.statements
    keys = [s.key for s in stmts if isinstance(s, PropAssign)]
    assert "$ext.figma_page" in keys
    assert "$ext.dank.tag" in keys


# ---------------------------------------------------------------------------
# Warning surface — KIND_UNUSED_IMPORT
# ---------------------------------------------------------------------------


def test_unused_import_emits_warning() -> None:
    """Unused `use` alias produces a non-fatal warning per §6.2."""
    doc = parse_l3(
        'namespace x\n'
        'use "./never-used" as nope\n'
        'screen #s { width=1 }'
    )
    kinds = [w.kind for w in doc.warnings]
    assert "KIND_UNUSED_IMPORT" in kinds
