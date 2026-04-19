"""Option B migration — A/B parity tests.

Asserts the Option B markup-native renderer produces output byte-identical
to the Option A dict-IR renderer. Each sub-milestone adds its own class of
gates:

- M1b (this file): preamble byte-parity on 3 reference fixtures.
- M1c: Phase 1 leaf-node byte-parity on minimal fixture.
- M1d: full-walker pipeline-health gate (no crash, non-empty, ratio
  0.95-1.05).
- M2: full script byte-parity on 3 reference fixtures.
- M3: full script byte-parity on full 204 corpus.

Deleted at M6 alongside the rest of the Option A reference machinery.
Skipped when the corpus DB is absent (matches `tests/test_script_parity.py`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dd.compress_l3 import compress_to_l3_with_nid_map
from dd.ir import generate_ir, query_screen_visuals
from dd.render_figma_ast import render_figma_preamble
from dd.renderers.figma import collect_fonts, generate_figma_script


DB_PATH = Path(__file__).resolve().parent.parent / "Dank-EXP-02.declarative.db"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        pytest.skip(f"corpus DB not present at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


REFERENCE_SCREENS = [181, 222, 237]


def _extract_preamble(script: str) -> str:
    """Split the baseline renderer output at the Phase 1 marker — the
    everything-before is the preamble region we're comparing against.
    """
    marker = "// Phase 1:"
    idx = script.find(marker)
    assert idx != -1, "baseline script has no Phase 1 marker"
    return script[:idx]


def _first_diff(a: str, b: str) -> str:
    """Human-readable first point of divergence. Shows 80 bytes of
    context around the first mismatched byte. Invoked on assertion
    failure so the PR reviewer can see the drift without eyeballing
    the full output."""
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            line_a = a[:i].count("\n") + 1
            line_b = b[:i].count("\n") + 1
            start = max(0, i - 40)
            end_a = min(len(a), i + 40)
            end_b = min(len(b), i + 40)
            return (
                f"  first diff at byte {i} (line A={line_a}, B={line_b}):\n"
                f"    A: ...{a[start:end_a]!r}\n"
                f"    B: ...{b[start:end_b]!r}"
            )
    if len(a) != len(b):
        shorter, longer = (a, b) if len(a) < len(b) else (b, a)
        tag = "B" if len(a) < len(b) else "A"
        extra = longer[len(shorter):len(shorter) + 80]
        return (
            f"  one is prefix of the other: len(A)={len(a)}, len(B)={len(b)}\n"
            f"  extra on {tag} side: {extra!r}"
        )
    return "  (strings identical)"


# ---------------------------------------------------------------------------
# M1b — preamble byte-parity
# ---------------------------------------------------------------------------


class TestM1bPreambleByteParity:
    """`render_figma_preamble(doc, conn, nid_map, db_visuals, ckr_built)`
    emits the pre-Phase-1 prefix byte-identically against
    `generate_figma_script(...)`'s corresponding region.

    Catches three failure classes in one gate:
    - Font collection (AST walk must find the same text elements
      `generate_figma_script.collect_fonts` does, and resolve their
      families/styles identically via nid_map → db_visuals.font).
    - Prefetch target set (component_figma_ids + override-tree swaps).
    - Error channel + _rootPage + CKR-unbuilt marker emission order.
    """

    @pytest.mark.parametrize("sid", REFERENCE_SCREENS)
    def test_preamble_byte_identical(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        ir = generate_ir(db_conn, sid, semantic=True, filter_chrome=False)
        visuals = query_screen_visuals(db_conn, sid)
        script_a, _ = generate_figma_script(
            ir["spec"], db_visuals=visuals, ckr_built=True,
        )
        preamble_a = _extract_preamble(script_a)

        doc, nid_map = compress_to_l3_with_nid_map(
            ir["spec"], db_conn, screen_id=sid,
        )
        fonts = collect_fonts(ir["spec"], db_visuals=visuals)
        uses_placeholder = "_missingComponentPlaceholder" in script_a
        preamble_b = render_figma_preamble(
            doc, db_conn, nid_map,
            fonts=fonts, db_visuals=visuals, ckr_built=True,
            uses_placeholder=uses_placeholder,
        )

        assert preamble_b == preamble_a, (
            f"preamble byte divergence on screen {sid} "
            f"(len A={len(preamble_a)}, B={len(preamble_b)}):\n"
            + _first_diff(preamble_a, preamble_b)
        )

    @pytest.mark.parametrize("sid", REFERENCE_SCREENS)
    def test_preamble_emits_expected_structural_landmarks(
        self, db_conn: sqlite3.Connection, sid: int,
    ) -> None:
        """Diagnostic gate: even if byte-parity drifts, the preamble
        must at minimum emit the four structural landmarks. A failure
        here means the Option B preamble is structurally broken, not
        just format-drifted."""
        ir = generate_ir(db_conn, sid, semantic=True, filter_chrome=False)
        visuals = query_screen_visuals(db_conn, sid)
        doc, nid_map = compress_to_l3_with_nid_map(
            ir["spec"], db_conn, screen_id=sid,
        )
        fonts = collect_fonts(ir["spec"], db_visuals=visuals)
        preamble = render_figma_preamble(
            doc, db_conn, nid_map,
            fonts=fonts, db_visuals=visuals, ckr_built=True,
        )
        for landmark in (
            "const __errors = [];",
            "const M = {};",
            "const _rootPage = figma.currentPage;",
            'await figma.loadFontAsync({family: "Inter", style: "Regular"});',
        ):
            assert landmark in preamble, (
                f"screen {sid}: preamble missing landmark {landmark!r}"
            )

    def test_preamble_ckr_unbuilt_marker_emitted_when_flag_false(
        self, db_conn: sqlite3.Connection,
    ) -> None:
        ir = generate_ir(db_conn, 181, semantic=True, filter_chrome=False)
        visuals = query_screen_visuals(db_conn, 181)
        doc, nid_map = compress_to_l3_with_nid_map(
            ir["spec"], db_conn, screen_id=181,
        )
        fonts = collect_fonts(ir["spec"], db_visuals=visuals)
        preamble = render_figma_preamble(
            doc, db_conn, nid_map,
            fonts=fonts, db_visuals=visuals, ckr_built=False,
        )
        assert 'kind:"ckr_unbuilt"' in preamble
