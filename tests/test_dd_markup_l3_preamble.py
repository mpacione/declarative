"""Plan B Stage 1.2 slice A+B+C — preamble parser tests.

Targets the first implemented slice of the L3 grammar: namespace
declaration + use imports + tokens block. Runs (not skipped) because
the implementation in `dd/markup_l3.py` is partially shipped.

Full node-body / define / pattern-ref tests remain skipped in
`tests/test_dd_markup_l3.py` until subsequent Stage 1.2 slices ship.
"""

from __future__ import annotations

import pytest

from dd.markup_l3 import (
    DDMarkupLexError,
    DDMarkupParseError,
    L3Document,
    Literal_,
    TokenAssign,
    TokenRef,
    UseDecl,
    parse_l3,
    tokenize,
)


# ---------------------------------------------------------------------------
# Lexer — §2 of grammar spec
# ---------------------------------------------------------------------------


class TestLexer:
    def test_empty_source(self) -> None:
        toks = tokenize("")
        assert len(toks) == 1
        assert toks[0].type == "EOF"

    def test_line_and_col_tracking(self) -> None:
        toks = tokenize("namespace\nx.y")
        kw = toks[0]
        assert kw.value == "namespace"
        assert kw.line == 1
        assert kw.col == 1
        ident = toks[2]                  # after EOL
        assert ident.value == "x"
        assert ident.line == 2
        assert ident.col == 1

    def test_bare_cr_rejected(self) -> None:
        with pytest.raises(DDMarkupLexError):
            tokenize("namespace\rx")     # bare \r without \n

    def test_crlf_accepted(self) -> None:
        toks = tokenize("namespace\r\nx")
        types = [t.type for t in toks]
        assert "EOL" in types

    def test_line_comment_skipped(self) -> None:
        toks = tokenize("// a comment\nnamespace x")
        kw = next(t for t in toks if t.type == "IDENT")
        assert kw.value == "namespace"

    def test_block_comment_skipped(self) -> None:
        toks = tokenize("/* a block\n   comment */namespace x")
        kw = next(t for t in toks if t.type == "IDENT")
        assert kw.value == "namespace"

    def test_unterminated_block_comment(self) -> None:
        with pytest.raises(DDMarkupLexError):
            tokenize("/* never closed")

    def test_hex_color_6_digit(self) -> None:
        toks = tokenize("#F6F6F6")
        assert toks[0].type == "HEX_COLOR"
        assert toks[0].value == "#F6F6F6"

    def test_hex_color_8_digit_with_alpha(self) -> None:
        toks = tokenize("#0000004D")
        assert toks[0].type == "HEX_COLOR"
        assert toks[0].value == "#0000004D"

    def test_hex_color_starting_with_digit(self) -> None:
        """Regression: `#9EFF85` must not fragment as `HASH + NUMBER(9E) + IDENT`."""
        toks = tokenize("#9EFF85")
        assert toks[0].type == "HEX_COLOR"
        assert toks[0].value == "#9EFF85"

    def test_eid_after_hash(self) -> None:
        """`#form-card` is HASH + IDENT, not HEX_COLOR — the IDENT is 9 chars, not 6/8."""
        toks = tokenize("#form-card")
        assert toks[0].type == "HASH"
        assert toks[1].type == "IDENT"
        assert toks[1].value == "form-card"

    def test_value_trailer_open_compound(self) -> None:
        """`#[` is a single compound token, distinguishing from `#eid`."""
        toks = tokenize("#[kind]")
        assert toks[0].type == "VALUE_TRAILER_OPEN"
        assert toks[0].value == "#["

    def test_asset_hash_40_hex(self) -> None:
        toks = tokenize("ab12cd34ef5678901234567890abcdef01234567")
        assert toks[0].type == "ASSET_HASH"

    def test_scope_operator(self) -> None:
        toks = tokenize("sheet22::card-section")
        assert toks[0].type == "IDENT"
        assert toks[0].value == "sheet22"
        assert toks[1].type == "SCOPE"
        assert toks[1].value == "::"
        assert toks[2].value == "card-section"

    def test_arrow_compound(self) -> None:
        toks = tokenize("-> nav/top-nav")
        assert toks[0].type == "ARROW"
        assert toks[0].value == "->"

    def test_string_escapes(self) -> None:
        toks = tokenize(r'"hello\nworld"')
        assert toks[0].type == "STRING"

    def test_unterminated_string(self) -> None:
        with pytest.raises(DDMarkupLexError):
            tokenize('"never closed')

    def test_newline_in_single_quoted_rejected(self) -> None:
        with pytest.raises(DDMarkupLexError):
            tokenize('"line\nbreak"')

    def test_triple_quoted_multiline(self) -> None:
        src = '"""hello\nworld"""'
        toks = tokenize(src)
        assert toks[0].type == "STRING"
        assert toks[0].value == src

    def test_scientific_number(self) -> None:
        toks = tokenize("1.5e-3")
        assert toks[0].type == "NUMBER"
        assert toks[0].value == "1.5e-3"

    def test_number_followed_by_hex_letter(self) -> None:
        """Regression: `9E` not consumed as invalid exponent when no digits follow."""
        toks = tokenize("9EFF")          # as bare idents in an IDENT position
        # Expected: this is treated as IDENT "9"? No — 9 is a digit, starts a number.
        # The number is "9" only (no valid exponent), then "E" starts an IDENT that
        # continues "EFF". So: NUMBER("9"), IDENT("EFF").
        assert toks[0].type == "NUMBER"
        assert toks[0].value == "9"
        assert toks[1].type == "IDENT"
        assert toks[1].value == "EFF"


# ---------------------------------------------------------------------------
# Preamble parser — §3 of grammar spec
# ---------------------------------------------------------------------------


class TestPreamble:
    def test_empty_document(self) -> None:
        doc = parse_l3("")
        assert doc.namespace is None
        assert doc.uses == ()
        assert doc.tokens == ()
        assert doc.top_level == ()

    def test_namespace_only(self) -> None:
        doc = parse_l3("namespace dank.reference.screen-181")
        assert doc.namespace == "dank.reference.screen-181"

    def test_use_relative_path(self) -> None:
        doc = parse_l3('use "./02-card-sheet" as sheet22')
        assert doc.uses == (
            UseDecl(path="./02-card-sheet", alias="sheet22", is_relative=True),
        )

    def test_use_parent_path(self) -> None:
        doc = parse_l3('use "../lib/theme" as theme')
        assert doc.uses[0].is_relative is True

    def test_use_explicit_dd_extension(self) -> None:
        doc = parse_l3('use "lib/theme.dd" as theme')
        assert doc.uses[0].is_relative is True

    def test_use_logical_library_name_with_slash(self) -> None:
        """`universal/tokens` is a library name, NOT a relative path —
        the distinction is made at §6.2 by the absence of ./ or ../."""
        doc = parse_l3('use "universal/tokens" as ut')
        assert doc.uses[0].is_relative is False

    def test_multiple_uses(self) -> None:
        """Uses are normalized to canonical order (by alias lex) per §6.2."""
        src = '''
        use "universal/tokens" as ut
        use "./02-card-sheet" as sheet22
        '''
        doc = parse_l3(src)
        assert len(doc.uses) == 2
        # Canonical order: sorted by (alias, path). `sheet22` < `ut`.
        assert doc.uses[0].alias == "sheet22"
        assert doc.uses[1].alias == "ut"

    def test_tokens_block_hex_colors(self) -> None:
        """Tokens are normalized to canonical lex-sorted order per §2.8/§7.6."""
        src = '''
        tokens {
          color.brand.accent.start = #D9FF40
          color.brand.accent.end   = #9EFF85
          color.overlay            = #0000004D
        }
        '''
        doc = parse_l3(src)
        assert len(doc.tokens) == 3
        # Lex-sorted: `color.brand.accent.end` < `color.brand.accent.start`
        #             < `color.overlay`
        paths = [t.path for t in doc.tokens]
        assert paths == [
            "color.brand.accent.end",
            "color.brand.accent.start",
            "color.overlay",
        ]
        by_path = {t.path: t.value for t in doc.tokens}
        assert by_path["color.brand.accent.start"].raw == "#D9FF40"
        assert by_path["color.brand.accent.end"].raw == "#9EFF85"
        assert by_path["color.overlay"].raw == "#0000004D"

    def test_tokens_block_mixed_values(self) -> None:
        """Mixed value forms all parse; tokens surfaced in lex order."""
        src = '''
        tokens {
          space.card.padding_x     = 16
          radius.card              = 12
          typography.body.fontSize = 14
          config.debug             = true
          config.prod              = false
          config.default           = null
          config.label             = "hello"
          color.ref                = {color.surface.default}
        }
        '''
        doc = parse_l3(src)
        assert len(doc.tokens) == 8
        by_path = {t.path: t.value for t in doc.tokens}
        assert by_path["space.card.padding_x"].lit_kind == "number"
        assert by_path["space.card.padding_x"].py == 16
        assert by_path["config.debug"].lit_kind == "bool"
        assert by_path["config.debug"].py is True
        assert by_path["config.prod"].py is False
        assert by_path["config.default"].lit_kind == "null"
        assert by_path["config.default"].py is None
        assert by_path["config.label"].lit_kind == "string"
        assert by_path["config.label"].py == "hello"
        assert by_path["color.ref"].kind == "token-ref"
        assert by_path["color.ref"].path == "color.surface.default"

    def test_full_preamble(self) -> None:
        """The full preamble shape from fixture 03's header."""
        src = '''
        namespace dank.reference.screen-237

        use "./02-card-sheet" as sheet22

        tokens {
          color.brand.accent = #D9FF40
        }
        '''
        doc = parse_l3(src)
        assert doc.namespace == "dank.reference.screen-237"
        assert len(doc.uses) == 1
        assert doc.uses[0].alias == "sheet22"
        assert len(doc.tokens) == 1

    def test_scientific_number(self) -> None:
        doc = parse_l3("tokens { x.y = 1.5e-3 }")
        assert doc.tokens[0].value.py == 1.5e-3

    def test_comments_ignored(self) -> None:
        src = '''
        // top comment
        namespace x  /* inline */
        /* block
           comment */
        tokens {
          // inner comment
          a.b = 1
        }
        '''
        doc = parse_l3(src)
        assert doc.namespace == "x"
        assert len(doc.tokens) == 1


# ---------------------------------------------------------------------------
# Structural equality — round-trip through AST
# ---------------------------------------------------------------------------


def test_ast_structural_equality() -> None:
    """Same source produces == L3Documents — frozen dataclass semantics."""
    src = '''
    namespace x
    use "./a" as a
    tokens { color.one = #123456 }
    '''
    doc1 = parse_l3(src)
    doc2 = parse_l3(src)
    assert doc1 == doc2


def test_parse_error_carries_kind() -> None:
    """DDMarkupParseError has `.kind` from the catalog."""
    # Malformed — `use` expects a string literal, gets an IDENT
    with pytest.raises(DDMarkupParseError) as exc_info:
        parse_l3("use foo as bar")
    # Implementation-specific kind; current impl raises KIND_BAD_SYNTAX
    # when the expected token type doesn't match.
    assert hasattr(exc_info.value, "kind")
    assert isinstance(exc_info.value.kind, str)
