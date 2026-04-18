"""Tier 2 parity gate — Figma-script byte-identity across dd-markup round-trip.

Per `docs/decisions/v0.3-branching-strategy.md`, Tier 2 is the PR-gate test
that proves the dd-markup serde preserves render behavior WITHOUT requiring
the live Figma bridge. For each app_screen in the corpus:

    1. Build dict IR via generate_ir(conn, sid)
    2. Round-trip through dd markup: parse_dd(serialize_ir(ir))
    3. Generate Figma JS via generate_figma_script(...) from BOTH
    4. Assert byte-identical scripts + identical token_refs

Byte-identical scripts imply byte-identical walks imply identical is_parity
verdicts. This is strictly stronger than Tier 1 (dict equality) and almost
as strong as Tier 3 (full pixel sweep) at detecting markup-serde regressions.

Runtime target: under 30 seconds on the 204-screen corpus. Observed ~15s.

Requires: `Dank-EXP-02.declarative.db` at the repo root (skipped when absent
so unit test runs on a clean checkout don't fail).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dd.ir import generate_ir, query_screen_visuals
from dd.markup import parse_dd, serialize_ir
from dd.renderers.figma import generate_figma_script


DB_PATH = Path(__file__).resolve().parent.parent / "Dank-EXP-02.declarative.db"


def _ckr_built(conn: sqlite3.Connection) -> bool:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='component_key_registry'"
    ).fetchone()
    if not exists:
        return False
    row = conn.execute("SELECT COUNT(*) FROM component_key_registry").fetchone()
    return bool(row and row[0] > 0)


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        pytest.skip(f"corpus DB not present at {DB_PATH}; script parity skipped")
    conn = sqlite3.connect(str(DB_PATH))
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def screen_ids(db_conn: sqlite3.Connection) -> list[int]:
    rows = db_conn.execute(
        "SELECT id FROM screens WHERE screen_type='app_screen' ORDER BY id"
    ).fetchall()
    return [r[0] for r in rows]


@pytest.fixture(scope="module")
def ckr(db_conn: sqlite3.Connection) -> bool:
    return _ckr_built(db_conn)


@pytest.mark.integration
class TestScriptParity:
    """The parity gate — byte-identical scripts across the markup round-trip."""

    def test_all_app_screens_script_byte_identical(
        self,
        db_conn: sqlite3.Connection,
        screen_ids: list[int],
        ckr: bool,
    ) -> None:
        assert len(screen_ids) > 0, "no app_screens in DB — corpus is empty"

        diffs: list[tuple[int, str]] = []
        for sid in screen_ids:
            ir = generate_ir(db_conn, sid)
            spec_baseline = ir["spec"]
            spec_round = parse_dd(serialize_ir(spec_baseline))

            visuals = query_screen_visuals(db_conn, sid)
            script_b, refs_b = generate_figma_script(
                spec_baseline, db_visuals=visuals, ckr_built=ckr,
            )
            script_r, refs_r = generate_figma_script(
                spec_round, db_visuals=visuals, ckr_built=ckr,
            )

            if script_b != script_r:
                diffs.append((sid, "script_differs"))
            elif refs_b != refs_r:
                diffs.append((sid, "token_refs_differ"))

        assert not diffs, (
            f"script parity regression on {len(diffs)}/{len(screen_ids)} "
            f"screens: {diffs[:5]}"
        )

    def test_sample_screen_full_round_trip(
        self,
        db_conn: sqlite3.Connection,
        screen_ids: list[int],
    ) -> None:
        """Sanity probe — one smallest screen round-trips at dict level."""
        sid = screen_ids[0]
        ir = generate_ir(db_conn, sid)
        spec = ir["spec"]
        parsed = parse_dd(serialize_ir(spec))
        assert parsed == spec, f"dict-level round-trip failed on screen {sid}"
