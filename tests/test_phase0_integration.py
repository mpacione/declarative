"""Phase 0 integration tests against real Dank DB.

These tests verify that the renderer DB access infrastructure works
against real extracted data — not seeded fixtures. They skip
automatically if the Dank DB file is not present.
"""

import os
import sqlite3

import pytest

from dd.ir import build_composition_spec, query_screen_for_ir, query_screen_visuals

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
class TestPhase0DankIntegration:
    """Verify Phase 0 infrastructure against real Dank DB screen 184."""

    def test_query_screen_visuals_returns_nodes(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=SCREEN_184)
        assert len(visuals) > 100, f"Expected 100+ nodes, got {len(visuals)}"

    def test_nodes_have_fills(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=SCREEN_184)
        with_fills = sum(1 for v in visuals.values() if v["fills"] and v["fills"] != "[]")
        assert with_fills > 50, f"Expected 50+ nodes with fills, got {with_fills}"

    def test_nodes_have_component_keys(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=SCREEN_184)
        with_keys = sum(1 for v in visuals.values() if v["component_key"])
        assert with_keys > 30, f"Expected 30+ nodes with component_key, got {with_keys}"

    def test_nodes_have_bindings(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=SCREEN_184)
        with_bindings = sum(1 for v in visuals.values() if v["bindings"])
        assert with_bindings > 50, f"Expected 50+ nodes with bindings, got {with_bindings}"

    def test_node_id_map_covers_all_ir_elements(self, dank_db):
        data = query_screen_for_ir(dank_db, screen_id=SCREEN_184)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]
        visuals = query_screen_visuals(dank_db, screen_id=SCREEN_184)

        missing = [nid for nid in node_id_map.values() if nid not in visuals]
        assert missing == [], f"IR element node_ids missing from visuals: {missing}"

    def test_every_ir_element_has_visual_data_available(self, dank_db):
        data = query_screen_for_ir(dank_db, screen_id=SCREEN_184)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]
        visuals = query_screen_visuals(dank_db, screen_id=SCREEN_184)

        for eid, nid in node_id_map.items():
            assert nid in visuals, f"Element {eid} (node {nid}) not in visuals"

    def test_ir_token_count_nonzero(self, dank_db):
        data = query_screen_for_ir(dank_db, screen_id=SCREEN_184)
        spec = build_composition_spec(data)
        assert len(spec["tokens"]) > 30, f"Expected 30+ tokens, got {len(spec['tokens'])}"

    def test_visual_data_has_extended_columns(self, dank_db):
        visuals = query_screen_visuals(dank_db, screen_id=SCREEN_184)
        sample = next(iter(visuals.values()))
        expected_keys = [
            "fills", "strokes", "effects", "corner_radius", "opacity",
            "stroke_weight", "stroke_align", "blend_mode", "component_key",
            "constraint_h", "constraint_v", "bindings",
        ]
        for key in expected_keys:
            assert key in sample, f"Missing key '{key}' in visual data"
