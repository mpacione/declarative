"""Phase 1 integration tests against real Dank DB.

Verifies that the generator's DB visual path produces identical output
to the IR visual path on real extracted data. Auto-skips if the
Dank DB file is not present.
"""

import os
import sqlite3

import pytest

from dd.ir import generate_ir, query_screen_visuals
from dd.generate import generate_figma_script

DANK_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db")
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)
SCREEN_184 = 184


@pytest.fixture
def dank_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DANK_DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestPhase1DankParity:
    """Verify IR and DB visual paths produce identical Figma JS on real data."""

    def test_scripts_identical(self, dank_db):
        ir_result = generate_ir(dank_db, screen_id=SCREEN_184)
        spec = ir_result["spec"]
        visuals = query_screen_visuals(dank_db, screen_id=SCREEN_184)

        ir_script, ir_refs = generate_figma_script(spec, db_visuals=None)
        db_script, db_refs = generate_figma_script(spec, db_visuals=visuals)

        assert ir_script == db_script

    def test_token_refs_identical(self, dank_db):
        ir_result = generate_ir(dank_db, screen_id=SCREEN_184)
        spec = ir_result["spec"]
        visuals = query_screen_visuals(dank_db, screen_id=SCREEN_184)

        _, ir_refs = generate_figma_script(spec, db_visuals=None)
        _, db_refs = generate_figma_script(spec, db_visuals=visuals)

        assert ir_refs == db_refs

    def test_script_has_visual_content(self, dank_db):
        ir_result = generate_ir(dank_db, screen_id=SCREEN_184)
        spec = ir_result["spec"]
        visuals = query_screen_visuals(dank_db, screen_id=SCREEN_184)

        db_script, db_refs = generate_figma_script(spec, db_visuals=visuals)

        assert "fills = [{" in db_script
        assert "SOLID" in db_script
        assert len(db_refs) > 10, f"Expected 10+ token refs, got {len(db_refs)}"

    def test_parity_across_multiple_screens(self, dank_db):
        screens = [row[0] for row in dank_db.execute(
            "SELECT id FROM screens WHERE screen_type = 'app_screen' LIMIT 5"
        ).fetchall()]

        for screen_id in screens:
            ir_result = generate_ir(dank_db, screen_id=screen_id)
            spec = ir_result["spec"]
            visuals = query_screen_visuals(dank_db, screen_id=screen_id)

            ir_script, _ = generate_figma_script(spec, db_visuals=None)
            db_script, _ = generate_figma_script(spec, db_visuals=visuals)

            assert ir_script == db_script, f"Parity failed on screen {screen_id}"
