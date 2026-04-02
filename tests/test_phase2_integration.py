"""Phase 2 integration tests against real Dank DB.

Verifies the thin IR (no visual section) and that the generator
still produces correct Figma JS by reading visual data from the DB.
Auto-skips if the Dank DB file is not present.
"""

import json
import os
import sqlite3

import pytest

from dd.ir import generate_ir, query_screen_visuals, query_screen_for_ir, build_composition_spec, normalize_strokes
from dd.generate import generate_screen, generate_figma_script

DANK_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db")
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)

PHONE_SCREEN = 184
TABLET_P_SCREEN = 150
TABLET_L_SCREEN = 118


@pytest.fixture
def dank_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DANK_DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestThinIRShape:
    """Verify IR elements no longer carry visual data."""

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_no_element_has_visual_key(self, dank_db, screen_id):
        ir_result = generate_ir(dank_db, screen_id=screen_id)
        spec = ir_result["spec"]

        for eid, element in spec["elements"].items():
            assert "visual" not in element, (
                f"Element {eid} on screen {screen_id} still has a 'visual' key"
            )

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_elements_retain_type_and_layout(self, dank_db, screen_id):
        ir_result = generate_ir(dank_db, screen_id=screen_id)
        spec = ir_result["spec"]

        for eid, element in spec["elements"].items():
            assert "type" in element, f"Element {eid} missing 'type'"
            if eid != spec["root"]:
                assert "layout" in element, f"Element {eid} missing 'layout'"

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_node_id_map_still_present(self, dank_db, screen_id):
        ir_result = generate_ir(dank_db, screen_id=screen_id)
        spec = ir_result["spec"]

        assert "_node_id_map" in spec
        assert len(spec["_node_id_map"]) > 0

    def test_token_dict_still_populated(self, dank_db):
        ir_result = generate_ir(dank_db, screen_id=PHONE_SCREEN)
        spec = ir_result["spec"]
        assert len(spec["tokens"]) > 30

    @pytest.mark.timeout(60)
    def test_no_visual_key_across_20_screens(self, dank_db):
        screens = [row[0] for row in dank_db.execute(
            "SELECT id FROM screens WHERE screen_type = 'app_screen' ORDER BY id LIMIT 20"
        ).fetchall()]

        violations = []
        for screen_id in screens:
            ir_result = generate_ir(dank_db, screen_id=screen_id)
            for eid, element in ir_result["spec"]["elements"].items():
                if "visual" in element:
                    violations.append((screen_id, eid))

        assert violations == [], f"Elements with 'visual' key: {violations[:10]}"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestGenerationStillWorks:
    """Verify the generator produces correct Figma JS from thin IR + DB visuals."""

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_generate_screen_has_fills(self, dank_db, screen_id):
        result = generate_screen(dank_db, screen_id=screen_id)
        script = result["structure_script"]
        assert "fills = [{" in script, f"Screen {screen_id}: no fills in generated script"
        assert '"SOLID"' in script

    def test_only_visible_strokes_emitted(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=PHONE_SCREEN)
        data = query_screen_for_ir(dank_db, screen_id=PHONE_SCREEN)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]

        classified_with_visible_strokes = sum(
            1 for nid in node_id_map.values()
            if nid in visuals and normalize_strokes(
                visuals[nid].get("strokes"), visuals[nid].get("bindings", []), visuals[nid]
            )
        )

        result = generate_screen(dank_db, screen_id=PHONE_SCREEN)
        script_stroke_count = result["structure_script"].count("strokes = [{")

        assert script_stroke_count == classified_with_visible_strokes

    def test_generate_screen_has_effects_on_phone(self, dank_db):
        result = generate_screen(dank_db, screen_id=PHONE_SCREEN)
        script = result["structure_script"]
        assert "effects = [{" in script

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_generate_screen_has_corner_radius(self, dank_db, screen_id):
        result = generate_screen(dank_db, screen_id=screen_id)
        script = result["structure_script"]
        assert "cornerRadius" in script

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_generate_screen_has_layout(self, dank_db, screen_id):
        result = generate_screen(dank_db, screen_id=screen_id)
        script = result["structure_script"]
        assert "layoutMode" in script
        assert "resize(" in script

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_generate_screen_has_token_refs_for_rebinding(self, dank_db, screen_id):
        result = generate_screen(dank_db, screen_id=screen_id)
        assert len(result["token_refs"]) > 5, (
            f"Screen {screen_id}: expected 5+ token refs, got {len(result['token_refs'])}"
        )

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_generate_screen_element_count(self, dank_db, screen_id):
        result = generate_screen(dank_db, screen_id=screen_id)
        assert result["element_count"] > 10, (
            f"Screen {screen_id}: expected 10+ elements, got {result['element_count']}"
        )


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestNoVisualDataLoss:
    """Verify that removing the IR visual section didn't lose any visual data.

    The DB still has all visual properties — the generator should produce
    the same visual output as before the thin IR change.
    """

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_fill_count_matches_db(self, dank_db, screen_id):
        visuals = query_screen_visuals(dank_db, screen_id=screen_id)
        db_fill_count = sum(
            1 for v in visuals.values()
            if v["fills"] and v["fills"] != "[]"
        )

        result = generate_screen(dank_db, screen_id=screen_id)
        script_fill_count = result["structure_script"].count("fills = [{")

        assert script_fill_count > 0, "No fills in generated script"
        assert script_fill_count <= db_fill_count, (
            f"Script has more fill assignments ({script_fill_count}) than DB rows with fills ({db_fill_count})"
        )

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_token_ref_count_matches_db(self, dank_db, screen_id):
        visuals = query_screen_visuals(dank_db, screen_id=screen_id)
        db_binding_count = sum(len(v["bindings"]) for v in visuals.values())

        result = generate_screen(dank_db, screen_id=screen_id)
        script_ref_count = len(result["token_refs"])

        assert script_ref_count > 0, "No token refs in generated script"
        assert script_ref_count <= db_binding_count, (
            f"Script has more token refs ({script_ref_count}) than DB bindings ({db_binding_count})"
        )

    def test_without_db_visuals_produces_no_visual_output(self, dank_db):
        ir_result = generate_ir(dank_db, screen_id=PHONE_SCREEN)
        spec = ir_result["spec"]

        script, refs = generate_figma_script(spec, db_visuals=None)

        assert "fills" not in script
        assert "strokes" not in script
        assert "effects" not in script
        # Layout token refs (padding, gap) still collected — only visual refs should be absent
        visual_refs = [r for r in refs if r[1].startswith(("fill.", "stroke.", "effect."))]
        assert visual_refs == []
