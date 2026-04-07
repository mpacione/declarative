"""End-to-end integration tests against real Dank DB.

Verifies the full pipeline (extraction → IR → visual query → generation)
works correctly on real extracted data across device classes and screen types.
Auto-skips if the Dank DB file is not present.

Run with: python -m pytest tests/test_integration_real_db.py -v
"""

import os
import sqlite3

import pytest

from dd.renderers.figma import generate_screen
from dd.visual import build_visual_from_db
from dd.ir import (
    build_composition_spec,
    normalize_effects,
    normalize_fills,
    normalize_strokes,
    query_screen_for_ir,
    query_screen_visuals,
)

DANK_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db")
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)

# Representative screens across device classes
PHONE_SCREEN = 184      # iPhone 13 Pro Max (428x926)
TABLET_P_SCREEN = 150   # iPad Pro 11" portrait (834x1194)
TABLET_L_SCREEN = 118   # iPad Pro 12.9" landscape (1536x1152)


@pytest.fixture
def dank_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DANK_DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestEndToEndGeneration:
    """Full pipeline: DB → IR → visual query → Figma JS generation."""

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_generate_screen_produces_valid_script(self, dank_db, screen_id):
        result = generate_screen(dank_db, screen_id=screen_id)
        script = result["structure_script"]

        assert "figma.createFrame()" in script
        assert "return M;" in script
        assert result["element_count"] > 5
        assert result["token_count"] > 10

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_generated_script_has_visual_properties(self, dank_db, screen_id):
        result = generate_screen(dank_db, screen_id=screen_id)
        script = result["structure_script"]

        assert "fills = [{" in script, "Generated script should contain fill assignments"
        assert '"SOLID"' in script, "Generated script should contain SOLID fill type"

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_generated_script_has_token_refs(self, dank_db, screen_id):
        result = generate_screen(dank_db, screen_id=screen_id)
        assert len(result["token_refs"]) > 5, "Expected token refs for variable rebinding"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestNodeIdMapCompleteness:
    """The _node_id_map covers all IR elements and all map to real visual data."""

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_all_elements_have_visual_data(self, dank_db, screen_id):
        data = query_screen_for_ir(dank_db, screen_id=screen_id)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]
        visuals = query_screen_visuals(dank_db, screen_id=screen_id)

        for eid, nid in node_id_map.items():
            assert nid in visuals, f"Element {eid} (node {nid}) missing from visuals on screen {screen_id}"

    @pytest.mark.timeout(60)
    def test_no_orphan_elements_across_sampled_app_screens(self, dank_db):
        screens = [row[0] for row in dank_db.execute(
            "SELECT id FROM screens WHERE screen_type = 'app_screen' ORDER BY id LIMIT 15"
        ).fetchall()]

        orphans = []
        for screen_id in screens:
            data = query_screen_for_ir(dank_db, screen_id=screen_id)
            spec = build_composition_spec(data)
            node_id_map = spec["_node_id_map"]
            visuals = query_screen_visuals(dank_db, screen_id=screen_id)

            for eid, nid in node_id_map.items():
                if nid not in visuals:
                    orphans.append((screen_id, eid, nid))

        assert orphans == [], f"Orphan elements (no visual data): {orphans[:10]}"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestVisualDataQuality:
    """Visual data from the DB is well-formed and normalizable."""

    def test_all_fills_parseable(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=PHONE_SCREEN)
        parse_failures = []

        for nid, v in visuals.items():
            raw_fills = v.get("fills")
            if not raw_fills or raw_fills == "[]":
                continue
            try:
                normalized = normalize_fills(raw_fills, v.get("bindings", []))
                for fill in normalized:
                    assert "type" in fill
                    assert "color" in fill or "stops" in fill
            except Exception as e:
                parse_failures.append((nid, str(e)))

        assert parse_failures == [], f"Fill parse failures: {parse_failures[:5]}"

    def test_all_strokes_parseable(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=PHONE_SCREEN)
        parse_failures = []

        for nid, v in visuals.items():
            raw_strokes = v.get("strokes")
            if not raw_strokes or raw_strokes == "[]":
                continue
            try:
                normalized = normalize_strokes(raw_strokes, v.get("bindings", []), v)
                for stroke in normalized:
                    assert "type" in stroke
            except Exception as e:
                parse_failures.append((nid, str(e)))

        assert parse_failures == [], f"Stroke parse failures: {parse_failures[:5]}"

    def test_all_effects_parseable(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=PHONE_SCREEN)
        parse_failures = []

        for nid, v in visuals.items():
            raw_effects = v.get("effects")
            if not raw_effects or raw_effects == "[]":
                continue
            try:
                normalized = normalize_effects(raw_effects, v.get("bindings", []))
                for effect in normalized:
                    assert "type" in effect
            except Exception as e:
                parse_failures.append((nid, str(e)))

        assert parse_failures == [], f"Effect parse failures: {parse_failures[:5]}"

    def test_build_visual_from_db_succeeds_for_all_nodes(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=PHONE_SCREEN)
        failures = []

        for nid, v in visuals.items():
            try:
                visual = build_visual_from_db(v)
                assert isinstance(visual, dict)
            except Exception as e:
                failures.append((nid, str(e)))

        assert failures == [], f"build_visual_from_db failures: {failures[:5]}"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestComponentKeyPresence:
    """Component keys are present for instance-first rendering."""

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_instance_nodes_have_component_keys(self, dank_db, screen_id):
        visuals = query_screen_visuals(dank_db, screen_id=screen_id)

        instance_nodes = [
            nid for nid in visuals
            if dank_db.execute(
                "SELECT node_type FROM nodes WHERE id = ?", (nid,)
            ).fetchone()[0] == "INSTANCE"
        ]
        with_keys = [nid for nid in instance_nodes if visuals[nid]["component_key"]]

        coverage = len(with_keys) / len(instance_nodes) if instance_nodes else 1.0
        assert coverage > 0.5, (
            f"Screen {screen_id}: only {len(with_keys)}/{len(instance_nodes)} "
            f"INSTANCE nodes have component_key ({coverage:.0%})"
        )

    def test_component_keys_are_valid_strings(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=PHONE_SCREEN)
        keys = [v["component_key"] for v in visuals.values() if v["component_key"]]
        assert len(keys) > 0, "Expected at least some component keys"
        for key in keys:
            assert isinstance(key, str)
            assert len(key) > 5, f"Suspiciously short component key: {key}"
