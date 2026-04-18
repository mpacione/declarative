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


# ---------------------------------------------------------------------------
# Slice C — CompRef emission via CKR lookup
# ---------------------------------------------------------------------------


def test_comp_refs_emitted_for_mode1_instances(
    db_conn: sqlite3.Connection,
) -> None:
    """Mode-1-eligible INSTANCE nodes emit as `-> slash/path` CompRefs
    at their highest level — the master component provides all children
    at render time per L0↔L3 §2.7. Deeply nested Mode-1 instances (e.g.
    an `icon/back` inside a `button` inside a `nav`) are covered by the
    OUTER CompRef and don't emit their own CompRef lines.

    Screen 181 has ~4 top-level CompRefs (the CTA button + 3 content-
    row icons) at the level where the spec's 3-tier row structure
    surfaces individual icons. That's the correct count — not 56.
    """
    doc = compress_to_l3(
        generate_ir(db_conn, 181, semantic=True)["spec"],
        db_conn,
        screen_id=181,
    )
    emitted = emit_l3(doc)
    arrow_count = emitted.count("-> ")
    # Sanity: at least 3 CompRefs (nav/top-nav + CTA button + content icons).
    assert arrow_count >= 3, (
        f"expected ≥3 CompRefs on screen 181; got {arrow_count}"
    )


def test_compref_path_matches_ckr_master_name(
    db_conn: sqlite3.Connection,
) -> None:
    """CompRef slash-path derives from `component_key_registry.name`
    (NOT from the instance layer name) per L0↔L3 §2.7.1."""
    doc = compress_to_l3(
        generate_ir(db_conn, 181, semantic=True)["spec"],
        db_conn,
        screen_id=181,
    )
    emitted = emit_l3(doc)
    # nav/top-nav appears at the top level so it emits as a CompRef
    assert "-> nav/top-nav" in emitted
    # The CTA button is a `button/large/translucent` instance at root
    assert "-> button/large/translucent" in emitted


def test_compref_without_conn_falls_back_to_frame(
    db_conn: sqlite3.Connection,
) -> None:
    """With `conn=None`, CKR lookup is skipped; Mode-1-eligible nodes
    fall back to inline `frame` / type keyword."""
    spec = generate_ir(db_conn, 181, semantic=True)["spec"]
    doc = compress_to_l3(spec, conn=None, screen_id=181)
    emitted = emit_l3(doc)
    # No CompRefs should appear without the CKR lookup.
    assert "-> " not in emitted, (
        "expected no CompRefs when conn is None; fallback to inline"
    )


def test_compref_roundtrips_at_grammar_level(
    db_conn: sqlite3.Connection,
) -> None:
    """CompRef emission must satisfy the same Tier 1 round-trip
    invariant as the rest of the compressor."""
    doc = compress_to_l3(
        generate_ir(db_conn, 222, semantic=True)["spec"],
        db_conn,
        screen_id=222,
    )
    emitted = emit_l3(doc)
    doc2 = parse_l3(emitted)
    assert doc == doc2


# ---------------------------------------------------------------------------
# Full-corpus Tier 1 sweep — the headline proof for Stage 1.3/1.4
# ---------------------------------------------------------------------------


def test_full_corpus_tier1_round_trip(db_conn: sqlite3.Connection) -> None:
    """Every app_screen in the Dank corpus round-trips through
    compress → emit → parse with structural equality. Tier 1 per
    L0↔L3 §4.1.

    This is the headline invariant for Stage 1.3/1.4. Runs in under
    10s on the 204-screen corpus.
    """
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    assert len(screens) > 0, "no app_screens in DB"

    failures: list[tuple[int, str]] = []
    for sid in screens:
        try:
            spec = generate_ir(db_conn, sid, semantic=True)["spec"]
            doc = compress_to_l3(spec, db_conn, screen_id=sid)
            emitted = emit_l3(doc)
            doc2 = parse_l3(emitted)
            if doc != doc2:
                failures.append((sid, "structural-equality mismatch"))
        except Exception as e:
            failures.append((sid, f"{type(e).__name__}: {str(e)[:100]}"))

    if failures:
        # Report first 10 failures
        details = "\n".join(f"  screen {sid}: {reason}" for sid, reason in failures[:10])
        pytest.fail(
            f"{len(failures)}/{len(screens)} screens failed Tier 1 round-trip:\n{details}"
        )


# ---------------------------------------------------------------------------
# Golden-file snapshots — L0↔L3 §2.11
# ---------------------------------------------------------------------------
#
# Each reference screen gets a frozen snapshot of its compressor output.
# On first run the snapshot is WRITTEN and the test passes (with a
# notice); on subsequent runs the current output is compared byte-wise.
# Regressions surface as diffs in the test output.
#
# Set `COMPRESS_L3_UPDATE_SNAPSHOTS=1` to rewrite all snapshots.


SNAPSHOT_DIR = Path(__file__).parent / "fixtures" / "markup"


def _snapshot_path(slug: str) -> Path:
    return SNAPSHOT_DIR / f"{slug}.stage1-expected.dd"


@pytest.mark.parametrize("screen_id,slug", REFERENCE_SCREENS)
def test_stage1_expected_snapshot(
    db_conn: sqlite3.Connection, screen_id: int, slug: str,
) -> None:
    """Freeze the compressor's current output per reference screen.

    Regressions manifest as diff between the fresh emit and the
    committed `stage1-expected.dd` snapshot. This is the Stage 1
    regression baseline until the Stage 3 synthetic-token pass lands
    — see L0↔L3 §2.11 for the two-track oracle model.
    """
    import os
    spec = generate_ir(db_conn, screen_id, semantic=True)["spec"]
    doc = compress_to_l3(spec, db_conn, screen_id=screen_id)
    emitted = emit_l3(doc)
    path = _snapshot_path(slug)

    if os.environ.get("COMPRESS_L3_UPDATE_SNAPSHOTS") == "1" or not path.exists():
        path.write_text(emitted)
        if not path.exists():                  # shouldn't happen, but guard
            pytest.skip(f"wrote new snapshot: {path}")
        return

    expected = path.read_text()
    if emitted != expected:
        # Produce a short diff hint for humans
        e_lines = expected.splitlines()
        a_lines = emitted.splitlines()
        diff = []
        for i, (e, a) in enumerate(zip(e_lines, a_lines)):
            if e != a:
                diff.append(f"  line {i+1}:")
                diff.append(f"    expected: {e}")
                diff.append(f"    actual:   {a}")
                if len(diff) > 15:
                    break
        if len(a_lines) != len(e_lines):
            diff.append(f"  line count: expected {len(e_lines)}, got {len(a_lines)}")
        pytest.fail(
            f"snapshot drift on screen {screen_id} ({slug}):\n" +
            "\n".join(diff) +
            "\n(run with COMPRESS_L3_UPDATE_SNAPSHOTS=1 to accept)"
        )
