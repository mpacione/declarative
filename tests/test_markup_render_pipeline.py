"""Plan B Stage 1.5b — end-to-end render pipeline through dd markup.

Wires the full Stage 1.5 loop:

    generate_ir → compress_to_l3 → emit_l3 → parse_l3 → ast_to_dict_ir
        → generate_figma_script

Proves the pipeline doesn't crash and measures the script-parity gap
against the baseline (renderer fed with the original IR directly).

Stage 1.5c (byte-parity on one fixture) and Stage 1.5d (Tier 3 pixel
parity) are successor gates on this one — once this test establishes
the pipeline is healthy, byte-parity is a series of incremental
fidelity fixes until the two scripts match.

Skipped when the corpus DB is absent (matches `test_script_parity.py`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dd.compress_l3 import compress_to_l3
from dd.decompress_l3 import ast_to_dict_ir
from dd.ir import generate_ir, query_screen_visuals
from dd.markup_l3 import emit_l3, parse_l3
from dd.renderers.figma import generate_figma_script


DB_PATH = Path(__file__).resolve().parent.parent / "Dank-EXP-02.declarative.db"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        pytest.skip(f"corpus DB not present at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _roundtrip_spec(
    conn: sqlite3.Connection, screen_id: int,
) -> tuple[dict, dict]:
    """Compress → emit → parse → decompress. Returns
    (baseline_spec, round_tripped_spec).

    Passes `screen_id` to the decompressor so it can recover
    `_node_id_map` entries by name-matching AST EIDs against the
    screen's nodes table — lets `dd.renderers.figma.generate_figma_script`
    look up `db_visuals` (fonts / images / variants) the same way
    the baseline does.
    """
    ir = generate_ir(conn, screen_id, semantic=True, filter_chrome=False)
    baseline = ir["spec"]
    doc = compress_to_l3(baseline, conn, screen_id=screen_id)
    parsed = parse_l3(emit_l3(doc))
    round_tripped = ast_to_dict_ir(parsed, conn, screen_id=screen_id)
    return baseline, round_tripped


# ---------------------------------------------------------------------------
# Stage 1.5b — pipeline smoke gates
# ---------------------------------------------------------------------------


REFERENCE_SCREENS = [181, 222, 237]


@pytest.mark.parametrize("sid", REFERENCE_SCREENS)
def test_render_pipeline_baseline_produces_script(
    db_conn: sqlite3.Connection, sid: int,
) -> None:
    """Sanity gate: the unmodified baseline IR produces a non-empty
    Figma script. If this fails the round-trip test below has no
    meaningful baseline to compare against."""
    ir = generate_ir(db_conn, sid, semantic=True, filter_chrome=False)
    visuals = query_screen_visuals(db_conn, sid)
    script, _ = generate_figma_script(
        ir["spec"], db_visuals=visuals, ckr_built=True,
    )
    assert len(script) > 1000, (
        f"screen {sid}: baseline script suspiciously short "
        f"({len(script)} bytes)"
    )


@pytest.mark.parametrize("sid", REFERENCE_SCREENS)
def test_render_pipeline_round_trip_produces_script(
    db_conn: sqlite3.Connection, sid: int,
) -> None:
    """Stage 1.5b headline: the round-tripped IR must produce a
    non-empty Figma script (no exceptions, no empty output). This is
    the "pipeline healthy" gate — byte-parity with baseline comes
    next (Stage 1.5c)."""
    _, round_spec = _roundtrip_spec(db_conn, sid)
    visuals = query_screen_visuals(db_conn, sid)
    script, _ = generate_figma_script(
        round_spec, db_visuals=visuals, ckr_built=True,
    )
    assert len(script) > 1000, (
        f"screen {sid}: round-tripped script suspiciously short "
        f"({len(script)} bytes)"
    )


@pytest.mark.parametrize("sid", REFERENCE_SCREENS)
def test_render_pipeline_scripts_have_similar_size(
    db_conn: sqlite3.Connection, sid: int,
) -> None:
    """Gate the parity-gap: the round-tripped script must be within
    2× the baseline script's size. A huge divergence (>2×) indicates
    a structural bug (e.g., the decompressor produced a vastly
    different element tree than orig) that would render incorrectly
    regardless of byte parity.

    This is a SOFT baseline to tighten over Stage 1.5c as fidelity
    gaps close. Current measured ratio on screen 181: ~0.9.
    """
    baseline, round_spec = _roundtrip_spec(db_conn, sid)
    visuals = query_screen_visuals(db_conn, sid)
    script_b, _ = generate_figma_script(
        baseline, db_visuals=visuals, ckr_built=True,
    )
    script_r, _ = generate_figma_script(
        round_spec, db_visuals=visuals, ckr_built=True,
    )
    # Ratio bounds — catches structural regressions without requiring
    # byte-exact parity (which is Stage 1.5c).
    size_ratio = len(script_r) / len(script_b) if script_b else 0
    assert 0.5 <= size_ratio <= 2.0, (
        f"screen {sid}: round-trip script size ratio {size_ratio:.2f} "
        f"(baseline={len(script_b)}, round={len(script_r)}) — out of "
        f"tolerance band [0.5, 2.0]"
    )


def test_render_pipeline_full_corpus_no_crash(
    db_conn: sqlite3.Connection,
) -> None:
    """Every app_screen in the corpus must complete the
    compress→emit→parse→decompress→render pipeline without raising.
    Stage 1.5b's strongest gate short of full byte-parity."""
    screens = [
        r[0] for r in db_conn.execute(
            "SELECT id FROM screens "
            "WHERE screen_type='app_screen' "
            "ORDER BY id"
        ).fetchall()
    ]
    failures: list[tuple[int, str]] = []
    for sid in screens:
        try:
            _, round_spec = _roundtrip_spec(db_conn, sid)
            visuals = query_screen_visuals(db_conn, sid)
            script, _ = generate_figma_script(
                round_spec, db_visuals=visuals, ckr_built=True,
            )
            if not script or len(script) < 100:
                failures.append((sid, f"empty script ({len(script)} bytes)"))
        except Exception as e:
            failures.append((sid, f"{type(e).__name__}: {str(e)[:100]}"))
    if failures:
        details = "\n".join(
            f"  screen {sid}: {reason}" for sid, reason in failures[:10]
        )
        pytest.fail(
            f"{len(failures)}/{len(screens)} screens failed the render "
            f"pipeline:\n{details}"
        )
