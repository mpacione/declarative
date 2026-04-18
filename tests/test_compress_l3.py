"""Plan B Stage 1.3/1.4 — compressor tests.

Tests `dd.compress_l3.compress_to_l3` end-to-end on each of the three
reference Dank screens. Verifies:

1. Compression produces a valid `L3Document` AST
2. The output emits cleanly via `emit_l3`
3. `parse_l3(emit_l3(doc)) == doc` — the grammar-level round-trip invariant

Skipped when the corpus DB is absent (matches `test_script_parity.py`'s
guard, so clean checkouts don't fail).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dd.compress_l3 import compress_to_l3, derive_comp_slash_path, normalize_to_eid
from dd.ir import generate_ir
from dd.markup_l3 import (
    Block,
    L3Document,
    Node,
    NodeTrailer,
    emit_l3,
    parse_l3,
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


# ---------------------------------------------------------------------------
# EID sanitization unit tests — L0↔L3 §2.3.1 examples
# ---------------------------------------------------------------------------


class TestNormalizeToEid:
    @pytest.mark.parametrize("raw,expected", [
        # Spec examples
        ("iPhone 13 Pro Max - 119", "iphone-13-pro-max-119"),
        ("nav/top-nav", "nav-top-nav"),
        ("Safari - Bottom", "safari-bottom"),
        ("Frame 354", "frame-354"),
        # Digit start → empty (caller uses auto-id)
        ("123", ""),
        # Empty string → empty
        ("", ""),
        # Parens stripped
        ("(internal spacer)", "internal-spacer"),
        # Multiple consecutive separators collapse
        ("foo  /  bar", "foo-bar"),
        # Leading/trailing separators trimmed
        ("  foo-bar  ", "foo-bar"),
        ("-foo-", "foo"),
    ])
    def test_normalization(self, raw: str, expected: str) -> None:
        assert normalize_to_eid(raw) == expected


class TestDeriveCompSlashPath:
    """Slash-path derivation from component master names — L0↔L3 §2.7.1."""

    @pytest.mark.parametrize("name,expected", [
        ("nav/top-nav", "nav/top-nav"),
        ("button/small/translucent", "button/small/translucent"),
        ("Safari - Bottom", "safari-bottom"),         # single-segment
        ("iOS/StatusBar", "ios/statusbar"),
        ("ios/alpha-keyboard", "ios/alpha-keyboard"),
        (".icons/safari/lock", "icons/safari/lock"),
    ])
    def test_component_names(self, name: str, expected: str) -> None:
        assert derive_comp_slash_path(name) == expected


# ---------------------------------------------------------------------------
# End-to-end compression on reference screens
# ---------------------------------------------------------------------------


REFERENCE_SCREENS = [
    (181, "01-login-welcome"),
    (222, "02-card-sheet"),
    (237, "03-keyboard-sheet"),
]


@pytest.mark.parametrize("screen_id,slug", REFERENCE_SCREENS)
def test_compress_produces_valid_l3_document(
    db_conn: sqlite3.Connection, screen_id: int, slug: str,
) -> None:
    """The compressor produces a well-formed L3Document for each
    reference screen."""
    ir = generate_ir(db_conn, screen_id, semantic=True)
    spec = ir["spec"]
    assert len(spec["elements"]) > 0, (
        f"screen {screen_id} has no elements — DB extraction issue"
    )

    doc = compress_to_l3(spec, db_conn, screen_id=screen_id)
    assert isinstance(doc, L3Document)
    assert len(doc.top_level) == 1, (
        f"expected 1 top-level node (screen root), got {len(doc.top_level)}"
    )

    root = doc.top_level[0]
    assert isinstance(root, Node)
    assert root.head.type_or_path == "screen"


@pytest.mark.parametrize("screen_id,slug", REFERENCE_SCREENS)
def test_compress_emits_valid_markup(
    db_conn: sqlite3.Connection, screen_id: int, slug: str,
) -> None:
    """The compressor's output emits cleanly via `emit_l3`."""
    spec = generate_ir(db_conn, screen_id, semantic=True)["spec"]
    doc = compress_to_l3(spec, db_conn, screen_id=screen_id)

    emitted = emit_l3(doc)
    assert len(emitted) > 100, "emitted output suspiciously short"
    assert "screen" in emitted
    assert f"(extracted src={screen_id})" in emitted


@pytest.mark.parametrize("screen_id,slug", REFERENCE_SCREENS)
def test_compress_output_round_trips(
    db_conn: sqlite3.Connection, screen_id: int, slug: str,
) -> None:
    """`parse_l3(emit_l3(compress(ir))) == compress(ir)` — the Tier 1
    grammar-level round-trip invariant."""
    spec = generate_ir(db_conn, screen_id, semantic=True)["spec"]
    doc = compress_to_l3(spec, db_conn, screen_id=screen_id)

    emitted = emit_l3(doc)
    doc2 = parse_l3(emitted)
    assert doc == doc2, (
        f"screen {screen_id}: compress→emit→parse not idempotent"
    )


def test_provenance_trailer_on_root(db_conn: sqlite3.Connection) -> None:
    """The compressor attaches `(extracted src=N)` to the screen root."""
    doc = compress_to_l3(
        generate_ir(db_conn, 181, semantic=True)["spec"],
        db_conn,
        screen_id=181,
    )
    root = doc.top_level[0]
    assert root.head.trailer is not None
    assert isinstance(root.head.trailer, NodeTrailer)
    assert root.head.trailer.kind == "extracted"
    attrs = dict(root.head.trailer.attrs)
    assert "src" in attrs
    assert attrs["src"].py == 181


def test_eid_derived_from_original_name(db_conn: sqlite3.Connection) -> None:
    """Screen 181's root name `"iPhone 13 Pro Max - 119"` sanitizes
    to `#iphone-13-pro-max-119` per L0↔L3 §2.3.1."""
    doc = compress_to_l3(
        generate_ir(db_conn, 181, semantic=True)["spec"],
        db_conn,
        screen_id=181,
    )
    assert doc.top_level[0].head.eid == "iphone-13-pro-max-119"
