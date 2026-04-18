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
# Module-level skip until Plan B Stage 1.2 full parser ships. The
# preamble-only tests that the current `dd.markup_l3` can satisfy live
# in `tests/test_dd_markup_l3_preamble.py` and run unconditionally.
# Remove this skip when the full node / define / pattern-ref surface
# lands in `dd.markup_l3`.
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.skip(
    reason=(
        "Plan B Stage 1.2: full node/define/pattern-ref parsing not yet "
        "shipped in `dd.markup_l3`. Preamble tests live in "
        "`test_dd_markup_l3_preamble.py` and run. These tests become the "
        "TDD red phase for the remaining slices. See "
        "docs/plan-v0.3.md and docs/spec-dd-markup-grammar.md §15."
    ),
)


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
    """Helper — assumes NodeHead exposes a `get_prop(key)` method or
    `props_by_key` dict-view. Resolved by the Stage 1.2 impl."""
    if hasattr(node.head, "get_prop"):
        return node.head.get_prop(key)
    return node.head.props_by_key.get(key)


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
    """`& a.b.c` parses as a PatternRef (dotted path, not slash)."""
    from dd.markup_l3 import parse_l3

    source = """
    define pattern.section() { frame #body }
    screen #s { & pattern.section #sec }
    """.strip()
    doc = parse_l3(source)
    screen = doc.top_level[1]                  # define is 0, screen is 1
    ref = screen.block.statements[0]
    assert ref.head.head_kind == "pattern-ref"
    assert ref.head.type_or_path == "pattern.section"


def test_provenance_trailer_node_level() -> None:
    """`(extracted src=181)` on a head line is a NodeTrailer."""
    from dd.markup_l3 import parse_l3

    source = "screen #s (extracted src=181) { width=428 height=926 }"
    doc = parse_l3(source)
    screen = doc.top_level[0]
    assert screen.head.trailer is not None
    assert screen.head.trailer.kind == "extracted"
    assert dict(screen.head.trailer.attrs)["src"] == 181


def test_provenance_trailer_value_level() -> None:
    """`fill=... #[user-edited]` is a ValueTrailer on the fill value."""
    from dd.markup_l3 import parse_l3

    source = 'screen #s { fill=#F8F8F8 #[user-edited reason="brand review"] }'
    doc = parse_l3(source)
    screen = doc.top_level[0]
    fill = _find_prop(screen, "fill")
    assert fill.trailer is not None
    assert fill.trailer.kind == "user-edited"
    assert dict(fill.trailer.attrs)["reason"] == "brand review"


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

    construct = "screen #s { frame #card-1 fill=#F00 }"
    edit      = "screen #s { @card-1 fill=#F00 }"
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


def test_multi_fill_array() -> None:
    """`fills=[...]` array form (Dank screen roots carry 3 fills)."""
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
