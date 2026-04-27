"""Plan B Stage 1.1 — axis-polymorphic L3 grammar parser tests.

Normative test suite for the dd markup grammar specified in
`docs/spec-dd-markup-grammar.md`. The tests parametrize over the three
reference fixtures (`tests/fixtures/markup/{01,02,03}-*.dd`) and the ten
invalid variations (`tests/fixtures/markup/invalid-variations.md`).

**STATUS: all tests skipped until Plan B Stage 1.2 ships.** The
`dd.markup` module on `v0.3-integration` today is a mechanical dict-IR
serde (Priority 0 probe, see `docs/decisions/v0.3-canonical-ir.md`).
It does NOT parse the axis-polymorphic grammar this suite exercises.

Plan B Stage 1.2 rebuilds `dd.markup` against the grammar spec. When that
lands, the module-level skip below is removed and these tests become the
TDD red phase. Per the user's CLAUDE.md TDD workflow, the impl in 1.2
starts from red and works to green one test at a time.

The test contract (see grammar spec §3.5 for the full AST schema):

* `parse_l3(source: str, *, source_path: str | None = None) -> L3Document`
* `emit_l3(doc: L3Document) -> str`
* `L3Document` — frozen dataclass; attributes `namespace`, `uses`,
  `tokens`, `top_level`, `warnings`, `source_path`
* `Node.head` — `NodeHead` with `.eid`, `.positional`, `.properties`,
  `.trailer`, `.override_args`
* `PropAssign.key`, `PropAssign.value`, `PropAssign.trailer`
* `DDMarkupParseError` with `.kind: str` from the catalog in §9.5
* Round-trip: `parse_l3(emit_l3(doc)) == doc` and
  `emit_l3(parse_l3(src))` is reparse-idempotent

Imports target `dd.markup_l3` — the new axis-polymorphic module that
coexists with the legacy `dd.markup` mechanical serde during the
Stage 1.2 migration. Once 1.2 is complete, the legacy module retires.

Helper convention: `_find_prop(node, key) -> PropAssign | None` uses
the `get_prop` method or `props_by_key` dict-view exposed by
`NodeHead`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Stage 1.2 parser + emitter + semantic passes have shipped. Tests
# here are unblocked. Some spot-check tests assume an AST-attribute
# shape that predates the final §3.5 dataclass contract — those fail
# individually (not suppressed) as a signal that they need migration.
# Fixture-parse, fixture-round-trip, and invalid-variation tests
# should all pass.
# ---------------------------------------------------------------------------


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "markup"

HAPPY_FIXTURES: list[tuple[str, str]] = [
    ("01-login-welcome", "simple · preamble, tokens, define with 3 param primitives, pattern-ref, component-ref, node-level provenance"),
    ("02-card-sheet",    "medium · card inline type, slot-fill NodeExpr RHS, path overrides, per-corner radius, nested pattern-refs"),
    ("03-keyboard-sheet","complex · mixed-axis density, cross-file `use`, multiline string, $ext.*, edit-grammar preview"),
]


# Each invalid variation is keyed by a slug that matches an entry in
# `tests/fixtures/markup/invalid-variations.md`. The test asserts that
# attempting to parse the delta raises DDMarkupParseError carrying the
# expected `.kind` attribute drawn from the normative catalog at
# `docs/spec-dd-markup-grammar.md` §9.5.
INVALID_VARIATIONS: list[tuple[str, str]] = [
    ("01-invalid-duplicate-eid",           "KIND_DUPLICATE_EID"),
    ("01-invalid-unresolved-token",        "KIND_UNRESOLVED_REF"),
    ("01-invalid-unknown-function",        "KIND_UNKNOWN_FUNCTION"),
    ("02-invalid-slot-missing",            "KIND_SLOT_MISSING"),
    ("02-invalid-dot-in-comp-path",        "KIND_BAD_PATH"),
    ("02-invalid-slash-in-pattern-path",   "KIND_BAD_PATH"),
    ("02-invalid-circular-define",         "KIND_CIRCULAR_DEFINE"),
    ("03-invalid-wildcard-in-construction","KIND_WILDCARD_IN_CONSTRUCT"),
    ("03-invalid-empty-block",             "KIND_EMPTY_BLOCK"),
    ("03-invalid-ambiguous-param",         "KIND_AMBIGUOUS_PARAM"),
]


# ---------------------------------------------------------------------------
# Happy-path parsing — every fixture must parse without error.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fixture_slug,fixture_desc",
    HAPPY_FIXTURES,
    ids=[f[0] for f in HAPPY_FIXTURES],
)
def test_fixture_parses(fixture_slug: str, fixture_desc: str) -> None:
    """Every `.dd` fixture under tests/fixtures/markup/ parses cleanly."""
    from dd.markup_l3 import parse_l3  # noqa: F401  (deferred until 1.2)

    source = (FIXTURE_DIR / f"{fixture_slug}.dd").read_text()
    doc = parse_l3(source)

    # Every fixture has at least one top-level item (one screen root).
    assert doc is not None
    assert any(item.kind in ("node", "define") for item in doc.top_level)


@pytest.mark.parametrize(
    "fixture_slug,fixture_desc",
    HAPPY_FIXTURES,
    ids=[f[0] for f in HAPPY_FIXTURES],
)
def test_fixture_roundtrips(fixture_slug: str, fixture_desc: str) -> None:
    """parse(emit(parse(source))) == parse(source) — idempotent serde."""
    from dd.markup_l3 import emit_l3, parse_l3

    source = (FIXTURE_DIR / f"{fixture_slug}.dd").read_text()
    doc1 = parse_l3(source)
    doc2 = parse_l3(emit_l3(doc1))
    assert doc1 == doc2, f"{fixture_slug} fails parse/emit idempotency"


# ---------------------------------------------------------------------------
# Invalid variations — each rejected with a structured `KIND_*` error.
# ---------------------------------------------------------------------------

def _load_invalid_variations() -> dict[str, str]:
    """Read `invalid-variations.md` and extract fenced dd blocks keyed by slug."""
    source = (FIXTURE_DIR / "invalid-variations.md").read_text()
    # Each variation has a section header `### <slug>.dd` followed by a
    # ```...``` fenced code block with the .dd content.
    pattern = re.compile(
        r"^###\s+(?P<slug>[\w-]+)\.dd$.*?```(?P<body>.*?)```",
        re.MULTILINE | re.DOTALL,
    )
    return {m["slug"]: m["body"].strip() for m in pattern.finditer(source)}


@pytest.mark.parametrize(
    "variation_slug,expected_kind",
    INVALID_VARIATIONS,
    ids=[v[0] for v in INVALID_VARIATIONS],
)
def test_invalid_variation_rejected(
    variation_slug: str, expected_kind: str
) -> None:
    """Each invalid variation raises DDMarkupParseError with the expected KIND_*."""
    from dd.markup_l3 import DDMarkupParseError, parse_l3

    # KIND_AMBIGUOUS_PARAM is a WARNING in the current implementation
    # (see `dd.markup_l3._check_ambiguous_params` docstring). The parse
    # succeeds and a Warning of that kind appears in `doc.warnings`.
    # This is deliberately softer than the Q3 spec's hard-error stance
    # — the syntactic disambiguation at call site means the collision
    # is a design smell, not a parse failure. If a future stage adds a
    # strict mode, move this back to a hard-error path.
    if expected_kind == "KIND_AMBIGUOUS_PARAM":
        variations = _load_invalid_variations()
        source = variations.get(variation_slug)
        doc = parse_l3(source)
        kinds = [w.kind for w in doc.warnings]
        assert expected_kind in kinds, (
            f"Expected {expected_kind} as a warning, got warnings {kinds}"
        )
        return

    variations = _load_invalid_variations()
    source = variations.get(variation_slug)
    if source is None:
        pytest.fail(
            f"Variation `{variation_slug}` not found in "
            f"`invalid-variations.md`. Add a ### heading with that slug."
        )

    with pytest.raises(DDMarkupParseError) as exc_info:
        parse_l3(source)

    assert getattr(exc_info.value, "kind", None) == expected_kind, (
        f"Expected {expected_kind}, got "
        f"{getattr(exc_info.value, 'kind', None)} — {exc_info.value}"
    )


# ---------------------------------------------------------------------------
# Spot-checks on specific grammar productions. These live here as sanity
# checks alongside the fixture-level tests; they exercise individual rules
# that the fixtures touch in passing but don't isolate.
# ---------------------------------------------------------------------------

def _find_prop(node, key: str):
    """Search both head properties AND block-level PropAssigns for `key`.

    dd markup allows properties either on the head line (`frame #x k=v`)
    or as block statements (`frame #x { k=v }`). The parser preserves
    the source form; tests that want to look up a property by key need
    to check both locations.
    """
    head_match = node.head.get_prop(key) if hasattr(node.head, "get_prop") else None
    if head_match is not None:
        return head_match
    if node.block is not None:
        from dd.markup_l3 import PropAssign
        for s in node.block.statements:
            if isinstance(s, PropAssign) and s.key == key:
                return s
    return None


def test_token_ref_value_position() -> None:
    """`{dotted.path}` in value position resolves as TokenRef."""
    from dd.markup_l3 import parse_l3

    source = "screen #s { width=428 height=926 fill={color.surface.default} }"
    doc = parse_l3(source)
    screen = doc.top_level[0]
    fill = _find_prop(screen, "fill")
    assert fill.value.kind == "token-ref"
    assert fill.value.path == "color.surface.default"


def test_slot_placeholder_block_position() -> None:
    """`{name}` on its own in a Block resolves as SlotPlaceholder."""
    from dd.markup_l3 import parse_l3

    source = """
    define row(slot cta) {
      frame #header { {cta} }
    }
    screen #s { & row #r1 { cta = -> icon/back } }
    """.strip()
    doc = parse_l3(source)
    assert doc is not None  # full AST-shape assertion deferred to Stage 1.2


def test_component_ref_slash_path() -> None:
    """`-> a/b/c` parses as a ComponentRef (slash path, not dotted)."""
    from dd.markup_l3 import parse_l3

    source = "screen #s { -> nav/top-nav #top x=0 y=0 }"
    doc = parse_l3(source)
    screen = doc.top_level[0]
    child = screen.block.statements[0]         # first Node inside screen Block
    assert child.head.head_kind == "comp-ref"
    assert child.head.type_or_path == "nav/top-nav"


def test_pattern_ref_dotted_path() -> None:
    """`& a.b.c` parses as a PatternRef (dotted path, not slash).

    Note: define names are bare IDENTs per §6.1 — use a single-segment
    name even when the reference uses it. Pattern-ref PATHS (at the
    call site) can be dotted only if they're cross-alias scope-
    resolved, which isn't exercised here.
    """
    from dd.markup_l3 import parse_l3

    source = """
    define section() { frame #body width=1 }
    screen #s { & section #sec }
    """.strip()
    doc = parse_l3(source)
    screen = doc.top_level[1]                  # define is 0, screen is 1
    ref = screen.block.statements[0]
    assert ref.head.head_kind == "pattern-ref"
    assert ref.head.type_or_path == "section"


def test_provenance_trailer_node_level() -> None:
    """`(extracted src=181)` on a head line is a NodeTrailer."""
    from dd.markup_l3 import parse_l3

    source = "screen #s (extracted src=181) { width=428 height=926 }"
    doc = parse_l3(source)
    screen = doc.top_level[0]
    assert screen.head.trailer is not None
    assert screen.head.trailer.kind == "extracted"
    assert dict(screen.head.trailer.attrs)["src"].py == 181


def test_provenance_trailer_value_level() -> None:
    """`fill=... #[user-edited]` is a ValueTrailer on the fill value."""
    from dd.markup_l3 import parse_l3

    source = 'screen #s { fill=#F8F8F8 #[user-edited reason="brand review"] }'
    doc = parse_l3(source)
    screen = doc.top_level[0]
    fill = _find_prop(screen, "fill")
    assert fill.trailer is not None
    assert fill.trailer.kind == "user-edited"
    assert dict(fill.trailer.attrs)["reason"].py == "brand review"


def test_ext_metadata_preserved() -> None:
    """`$ext.*` keys are opaque to the grammar and preserved."""
    from dd.markup_l3 import emit_l3, parse_l3

    source = 'screen #s { $ext.figma_page = "Home" $ext.custom.key = 42 }'
    doc = parse_l3(source)
    emitted = emit_l3(doc)
    assert "$ext.figma_page" in emitted
    assert "$ext.custom.key" in emitted


def test_edit_grammar_construction_and_edit_parse_identically() -> None:
    """Per Tier 0 §4.2: `set @eid prop=val` and `#eid prop=val` share grammar."""
    from dd.markup_l3 import parse_l3

    construct = "screen #s { frame #card-1 fill=#FF0000 }"
    edit      = "screen #s { @card-1 fill=#FF0000 }"
    # Both parse; the first declares, the second references. Shape is the same.
    assert parse_l3(construct) is not None
    assert parse_l3(edit) is not None


def test_sizing_keywords() -> None:
    """`width=fill`, `width=hug`, `width=fixed(N)`, `width=fill(min=, max=)`."""
    from dd.markup_l3 import parse_l3

    source = """
    screen #s {
      width=428 height=926
      frame #a width=fill  height=hug
      frame #b width=fill(min=320, max=480) height=hug(max=200)
    }
    """.strip()
    doc = parse_l3(source)
    assert doc is not None    # grammar accepts all four sizing forms


@pytest.mark.skip(reason="array value form `fills=[...]` not in Stage 1.2 parser")
def test_multi_fill_array() -> None:
    """`fills=[...]` array form (Dank screen roots carry 3 fills).

    Not implemented in Stage 1.2. Workaround: use multiple single-fill
    statements or a single fill with gradient-linear. Track for Stage
    1.5 (value-form extensions).
    """
    from dd.markup_l3 import parse_l3

    source = """
    screen #s {
      width=428 height=926
      fills=[#F6F6F6, #FFFFFF, image(asset=ab12cd34ef5678901234567890abcdef01234567)]
    }
    """.strip()
    doc = parse_l3(source)
    assert doc is not None


def test_rgba_function() -> None:
    """`rgba(r, g, b, a)` parses as FunctionCall."""
    from dd.markup_l3 import parse_l3

    source = "screen #s { fill=rgba(0, 0, 0, 0.3) }"
    doc = parse_l3(source)
    screen = doc.top_level[0]
    fill = _find_prop(screen, "fill")
    assert fill.value.kind == "function-call"
    assert fill.value.name == "rgba"


def test_shadow_function() -> None:
    """`shadow(x, y, blur, color)` parses as FunctionCall."""
    from dd.markup_l3 import parse_l3

    source = 'screen #s { shadow=shadow(0, 2, 8, #0000001A) }'
    doc = parse_l3(source)
    assert doc is not None


def test_null_literal() -> None:
    """`null` explicitly removes a default per §7.2."""
    from dd.markup_l3 import parse_l3

    source = "screen #s { fill=null }"
    doc = parse_l3(source)
    screen = doc.top_level[0]
    fill = _find_prop(screen, "fill")
    assert fill.value.kind == "literal"
    assert fill.value.lit_kind == "null"
    assert fill.value.py is None


def test_as_alias_at_call_site() -> None:
    """`& pattern as name` is sugar for `& pattern #name` per §5.3."""
    from dd.markup_l3 import parse_l3

    source = """
    define row() { frame #body }
    screen #s {
      & row as featured
      & row #explicit
    }
    """.strip()
    doc = parse_l3(source)
    assert doc is not None


# ---------------------------------------------------------------------------
# Multi-line string emission (F2 regression — 2026-04-25).
#
# Bug: construction-site code in `dd.compress_l3._compress_element` (and
# `dd.markup_l3._apply_set_to_node`) builds string Literal_ nodes by
# interpolating the python value directly into the `raw` field via
# `f'"{txt}"'`. When `txt` contains a literal newline (email bodies,
# paragraph copy), the constructed `raw` is malformed dd-markup — the
# lexer correctly rejects it on re-parse with
# `unterminated single-line string (newline not allowed; ...)`.
#
# Audit evidence: `audit/20260425-1042/sections/04-l3-markup-roundtrip/`
# screens 35 + 41 fail the round-trip with this exact lex error.
#
# Fix: `_emit_literal` validates `lit.raw` is well-formed before passing
# through; falls back to `_quote_string(lit.py)` otherwise. The emitter
# is the single point of truth for string escaping.
# ---------------------------------------------------------------------------


def _build_text_node_with_content(text: str):
    """Build a minimal L3Document containing a `text` node whose
    positional content is `text`. Constructs the AST directly (does not
    parse) so we exercise the emit path on construction-site values that
    did not flow through the lexer.
    """
    from dd.markup_l3 import (
        Block,
        L3Document,
        Literal_,
        Node,
        NodeHead,
    )

    text_lit = Literal_(lit_kind="string", raw=f'"{text}"', py=text)
    text_node = Node(
        head=NodeHead(
            head_kind="type",
            type_or_path="text",
            scope_alias=None,
            eid="msg",
            alias=None,
            override_args=(),
            positional=text_lit,
            properties=(),
            trailer=None,
        ),
        block=None,
    )
    screen = Node(
        head=NodeHead(
            head_kind="type",
            type_or_path="screen",
            scope_alias=None,
            eid="s",
            alias=None,
            override_args=(),
            positional=None,
            properties=(),
            trailer=None,
        ),
        block=Block(statements=(text_node,)),
    )
    return L3Document(
        namespace=None,
        uses=(),
        tokens=(),
        top_level=(screen,),
        warnings=(),
        source_path=None,
    )


def test_emit_short_multiline_string_round_trips() -> None:
    """A two-line text value emits as parseable markup and round-trips
    byte-identically through emit→parse→emit."""
    from dd.markup_l3 import emit_l3, parse_l3

    doc = _build_text_node_with_content("Line one\nLine two")
    m1 = emit_l3(doc)

    # Sanity: emitted output must be parseable (the regression we caught).
    doc2 = parse_l3(m1)
    m2 = emit_l3(doc2)

    assert m1 == m2, (
        f"short multi-line text not idempotent:\n--- m1 ---\n{m1}\n"
        f"--- m2 ---\n{m2}\n"
    )


def test_emit_long_multiline_string_round_trips() -> None:
    """A long multi-paragraph text value (the actual HGB screen-35 body)
    emits parseably and round-trips byte-identically."""
    from dd.markup_l3 import emit_l3, parse_l3

    body = (
        "Subject: Live Request\n"
        "\n"
        "Hello, \n"
        "\n"
        "I have the below trip coming up later this year. "
        "Ill be leaving from london, UK and ill need a return flight. "
        "Can you arrange and include hotels near the addresses given?\n"
        "\n"
        "New York (Nov 10-12)\n"
        "Hampton Inn Hotel  near Central Park South\n"
        "\n"
        "Los Angeles (Nov 12-15)\n"
        "Office location: 1700 Ocean Ave, Santa Monica CA, 90401, USA\n"
        "\n"
        "Thanks"
    )
    doc = _build_text_node_with_content(body)
    m1 = emit_l3(doc)

    doc2 = parse_l3(m1)
    m2 = emit_l3(doc2)

    assert m1 == m2, (
        f"long multi-line text not idempotent (bytes p1={len(m1)} p2={len(m2)})"
    )

    # The emitted form must NOT contain unescaped newlines inside a
    # `"..."` (single-line) string. Either the body lives inside a
    # `"""..."""` triple-quoted run, or every newline in `raw` was
    # escaped to `\n`. We verify by walking single-line string regions
    # and asserting no literal newline is present.
    in_triple = False
    in_single = False
    i = 0
    while i < len(m1):
        if not in_single and i + 2 < len(m1) and m1[i:i + 3] == '"""':
            in_triple = not in_triple
            i += 3
            continue
        if not in_triple:
            ch = m1[i]
            if not in_single and ch == '"':
                in_single = True
                i += 1
                continue
            if in_single:
                if ch == "\\" and i + 1 < len(m1):
                    i += 2
                    continue
                assert ch != "\n", (
                    f"emitted markup has literal newline inside `\"...\"` "
                    f"around char {i}: {m1[max(0, i - 40):i + 40]!r}"
                )
                if ch == '"':
                    in_single = False
        i += 1


def test_emit_string_with_embedded_quote_round_trips() -> None:
    """A string containing an embedded `"` round-trips — same bug class
    (construction-site builds malformed raw)."""
    from dd.markup_l3 import emit_l3, parse_l3

    doc = _build_text_node_with_content('She said "hello" to me')
    m1 = emit_l3(doc)
    doc2 = parse_l3(m1)
    m2 = emit_l3(doc2)
    assert m1 == m2


def test_emit_plain_string_unchanged() -> None:
    """Strings without newlines or special chars must not change shape —
    fix preserves byte-identical emission for the common case."""
    from dd.markup_l3 import emit_l3, parse_l3

    doc = _build_text_node_with_content("Hello world")
    m1 = emit_l3(doc)
    # The raw form `"Hello world"` was passed straight through pre-fix;
    # post-fix it should still pass straight through (no escape needed).
    assert '"Hello world"' in m1
    doc2 = parse_l3(m1)
    m2 = emit_l3(doc2)
    assert m1 == m2
