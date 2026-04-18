"""Plan B Stage 1.1 — axis-polymorphic L3 grammar parser tests.

Normative test suite for the dd markup grammar specified in
`docs/spec-dd-markup-grammar.md`. The tests parametrize over the three
reference fixtures (`tests/fixtures/markup/{01,02,03}-*.dd`) and the nine
invalid variations (`tests/fixtures/markup/invalid-variations.md`).

**STATUS: all tests skipped until Plan B Stage 1.2 ships.** The
`dd.markup` module on `v0.3-integration` today is a mechanical dict-IR
serde (Priority 0 probe, see `docs/decisions/v0.3-canonical-ir.md`).
It does NOT parse the axis-polymorphic grammar this suite exercises.

Plan B Stage 1.2 rebuilds `dd.markup` against the grammar spec. When that
lands, the module-level skip below is removed and these tests become the
TDD red phase. Per the user's CLAUDE.md TDD workflow, the impl in 1.2
starts from red and works to green one test at a time.

The test contract is:

* `parse_l3(source: str) -> L3Document`         — parses a .dd source file
* `L3Document`                                  — dataclass per grammar §3
* `DDMarkupParseError` with `.kind: str`        — structured errors per
                                                  ADR-006 boundary contract
* `emit_l3(doc: L3Document) -> str`             — emitter round-trips
                                                  `parse_l3(emit_l3(doc)) == doc`

The contract is documented in `docs/spec-dd-markup-grammar.md` §15
(implementation hook) and `docs/spec-l0-l3-relationship.md` §3
(expansion pipeline).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Module-level skip until Plan B Stage 1.2 ships the new parser.
# Remove this gate once `dd.markup.parse_l3` exists.
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.skip(
    reason=(
        "Plan B Stage 1.2: `dd.markup.parse_l3` is not yet implemented. "
        "These tests become the TDD red phase when the new parser lands. "
        "See docs/plan-v0.3.md and docs/spec-dd-markup-grammar.md §15."
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
# expected `.kind` attribute.
INVALID_VARIATIONS: list[tuple[str, str]] = [
    ("01-invalid-duplicate-eid",          "KIND_DUPLICATE_EID"),
    ("01-invalid-unresolved-token",       "KIND_UNRESOLVED_REF"),
    ("01-invalid-unknown-function",       "KIND_UNKNOWN_FUNCTION"),
    ("02-invalid-slot-missing",           "KIND_SLOT_MISSING"),
    ("02-invalid-mixed-path-styles",      "KIND_BAD_PATH"),
    ("02-invalid-circular-define",        "KIND_CIRCULAR_DEFINE"),
    ("03-invalid-wildcard-in-construction","KIND_WILDCARD_IN_CONSTRUCT"),
    ("03-invalid-empty-block",            "KIND_EMPTY_BLOCK"),
    ("03-invalid-ambiguous-param",        "KIND_AMBIGUOUS_PARAM"),
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
    from dd.markup import parse_l3  # noqa: F401  (deferred until 1.2)

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
    from dd.markup import emit_l3, parse_l3

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
    from dd.markup import DDMarkupParseError, parse_l3

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

def test_token_ref_value_position() -> None:
    """`{dotted.path}` in value position resolves as TokenRef."""
    from dd.markup import parse_l3

    source = "screen #s { width=428 height=926 fill={color.surface.default} }"
    doc = parse_l3(source)
    screen = doc.top_level[0]
    fill = screen.properties["fill"]
    assert fill.kind == "token-ref"
    assert fill.path == "color.surface.default"


def test_slot_placeholder_block_position() -> None:
    """`{name}` on its own in a Block resolves as SlotPlaceholder."""
    from dd.markup import parse_l3

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
    from dd.markup import parse_l3

    source = "screen #s { -> nav/top-nav #top x=0 y=0 }"
    doc = parse_l3(source)
    child = doc.top_level[0].children[0]
    assert child.kind == "component-ref"
    assert child.path == "nav/top-nav"


def test_pattern_ref_dotted_path() -> None:
    """`& a.b.c` parses as a PatternRef (dotted path, not slash)."""
    from dd.markup import parse_l3

    source = """
    define pattern.section() { frame #body }
    screen #s { & pattern.section #sec }
    """.strip()
    doc = parse_l3(source)
    assert doc.top_level[1].children[0].kind == "pattern-ref"
    assert doc.top_level[1].children[0].path == "pattern.section"


def test_provenance_trailer_node_level() -> None:
    """`(extracted src=181)` on a head line is a NodeTrailer."""
    from dd.markup import parse_l3

    source = "screen #s (extracted src=181) { width=428 height=926 }"
    doc = parse_l3(source)
    screen = doc.top_level[0]
    assert screen.provenance.kind == "extracted"
    assert screen.provenance.attrs["src"] == 181


def test_provenance_trailer_value_level() -> None:
    """`fill=... #[user-edited]` is a ValueTrailer on the fill value."""
    from dd.markup import parse_l3

    source = 'screen #s { fill=#F8F8F8 #[kind=user-edited reason="brand review"] }'
    doc = parse_l3(source)
    fill = doc.top_level[0].properties["fill"]
    assert fill.trailer is not None
    assert fill.trailer.kind == "user-edited"
    assert fill.trailer.attrs["reason"] == "brand review"


def test_ext_metadata_preserved() -> None:
    """`$ext.*` keys are opaque to the grammar and preserved."""
    from dd.markup import emit_l3, parse_l3

    source = 'screen #s { $ext.figma_page = "Home" $ext.custom.key = 42 }'
    doc = parse_l3(source)
    emitted = emit_l3(doc)
    assert "$ext.figma_page" in emitted
    assert "$ext.custom.key" in emitted


def test_edit_grammar_construction_and_edit_parse_identically() -> None:
    """Per Tier 0 §4.2: `set @eid prop=val` and `#eid prop=val` share grammar."""
    from dd.markup import parse_l3

    construct = "screen #s { frame #card-1 fill=#F00 }"
    edit      = "screen #s { @card-1 fill=#F00 }"
    # Both parse; the first declares, the second references. Shape is the same.
    assert parse_l3(construct) is not None
    assert parse_l3(edit) is not None
