"""Semantic tree integration tests against real Dank DB.

Comprehensive validation of Phase 3b semantic tree construction across
all device classes: element reduction, slot assignment, system chrome
filtering, backward compatibility, and data integrity.
Auto-skips if the Dank DB file is not present.
"""

import os
import sqlite3

import pytest

from dd.classify_rules import is_system_chrome
from dd.ir import generate_ir, query_screen_visuals, query_slot_definitions

DANK_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db")
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)

PHONE_SCREEN = 184
TABLET_P_SCREEN = 150
TABLET_L_SCREEN = 118
STROKE_HEAVY_SCREEN = 298

ALL_TEST_SCREENS = [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN, STROKE_HEAVY_SCREEN]


def _walk_children(spec, eid, visited=None):
    if visited is None:
        visited = set()
    if eid in visited:
        return 0
    visited.add(eid)
    el = spec["elements"].get(eid, {})
    count = 1
    for child in el.get("children", []):
        count += _walk_children(spec, child, visited)
    return count


def _collect_slot_children(spec):
    slot_children = set()
    for el in spec["elements"].values():
        for slot_eids in el.get("slots", {}).values():
            slot_children.update(slot_eids)
    return slot_children


@pytest.fixture
def dank_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DANK_DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestElementReduction:
    """Verify semantic tree reduces element count across all device classes."""

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_fewer_reachable_than_flat(self, dank_db, screen_id):
        flat = generate_ir(dank_db, screen_id=screen_id, semantic=False)
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)

        flat_reachable = _walk_children(flat["spec"], flat["spec"]["root"])
        sem_reachable = _walk_children(sem["spec"], sem["spec"]["root"])

        assert sem_reachable < flat_reachable, (
            f"Screen {screen_id}: semantic ({sem_reachable}) >= flat ({flat_reachable})"
        )

    def test_phone_screen_collapses_to_under_30(self, dank_db):
        sem = generate_ir(dank_db, screen_id=PHONE_SCREEN, semantic=True)
        reachable = _walk_children(sem["spec"], sem["spec"]["root"])
        assert reachable <= 30, f"Phone screen should collapse to <=30, got {reachable}"

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_slot_children_absorbed(self, dank_db, screen_id):
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)
        slot_children = _collect_slot_children(sem["spec"])
        assert len(slot_children) > 10, (
            f"Screen {screen_id}: expected 10+ absorbed slot children, got {len(slot_children)}"
        )

    @pytest.mark.timeout(60)
    def test_reduction_across_10_app_screens(self, dank_db):
        screens = [row[0] for row in dank_db.execute(
            "SELECT id FROM screens WHERE screen_type = 'app_screen' ORDER BY id LIMIT 10"
        ).fetchall()]

        for screen_id in screens:
            flat = generate_ir(dank_db, screen_id=screen_id, semantic=False)
            sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)

            flat_r = _walk_children(flat["spec"], flat["spec"]["root"])
            sem_r = _walk_children(sem["spec"], sem["spec"]["root"])

            assert sem_r < flat_r, f"Screen {screen_id}: no reduction ({sem_r} >= {flat_r})"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestSlotAssignmentQuality:
    """Verify slots are assigned correctly with proper structure."""

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_header_has_named_slots(self, dank_db, screen_id):
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)
        spec = sem["spec"]

        headers = [el for el in spec["elements"].values() if el.get("type") == "header"]
        assert len(headers) >= 1

        header = headers[0]
        assert "slots" in header, "Header should have named slots"
        assert set(header["slots"].keys()) == {"left", "center", "right"}

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_slotted_elements_have_no_children_key(self, dank_db, screen_id):
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)
        for eid, el in sem["spec"]["elements"].items():
            if "slots" in el:
                assert "children" not in el, f"{eid} has both 'slots' and 'children'"

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_all_slot_children_exist_in_elements(self, dank_db, screen_id):
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)
        spec = sem["spec"]

        for eid, el in spec["elements"].items():
            for slot_name, slot_eids in el.get("slots", {}).items():
                for slot_eid in slot_eids:
                    assert slot_eid in spec["elements"], (
                        f"{eid}.slots.{slot_name} references {slot_eid} not in elements"
                    )

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_all_slot_children_have_node_id_map_entry(self, dank_db, screen_id):
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)
        spec = sem["spec"]
        node_id_map = spec["_node_id_map"]

        slot_children = _collect_slot_children(spec)
        for slot_eid in slot_children:
            assert slot_eid in node_id_map, f"Slot child {slot_eid} missing from _node_id_map"

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_all_slot_children_have_visual_data(self, dank_db, screen_id):
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)
        spec = sem["spec"]
        node_id_map = spec["_node_id_map"]
        visuals = query_screen_visuals(dank_db, screen_id=screen_id)

        slot_children = _collect_slot_children(spec)
        missing = []
        for slot_eid in slot_children:
            nid = node_id_map.get(slot_eid)
            if nid and nid not in visuals:
                missing.append((slot_eid, nid))

        assert missing == [], f"Slot children missing visual data: {missing[:5]}"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestSystemChromeRemoval:
    """Verify system chrome is filtered from the semantic IR."""

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_no_system_chrome_in_semantic_ir(self, dank_db, screen_id):
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)
        spec = sem["spec"]

        chrome = []
        for eid, nid in spec["_node_id_map"].items():
            name = dank_db.execute("SELECT name FROM nodes WHERE id = ?", (nid,)).fetchone()[0]
            if is_system_chrome(name):
                chrome.append((eid, name))

        assert chrome == [], f"Screen {screen_id}: chrome still present: {chrome}"

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_chrome_removed_count_is_consistent(self, dank_db, screen_id):
        flat = generate_ir(dank_db, screen_id=screen_id, semantic=False)
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)

        removed = flat["element_count"] - sem["element_count"]
        assert removed >= 0, f"Screen {screen_id}: semantic has MORE elements than flat"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestBackwardCompatibility:
    """Verify semantic=False preserves exact existing behavior."""

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_flat_ir_has_no_slots(self, dank_db, screen_id):
        flat = generate_ir(dank_db, screen_id=screen_id, semantic=False)
        for el in flat["spec"]["elements"].values():
            assert "slots" not in el, "Flat IR should never have slots"

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_flat_and_semantic_have_same_tokens(self, dank_db, screen_id):
        flat = generate_ir(dank_db, screen_id=screen_id, semantic=False)
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)
        assert flat["spec"]["tokens"] == sem["spec"]["tokens"]

    @pytest.mark.parametrize("screen_id", ALL_TEST_SCREENS)
    def test_flat_and_semantic_have_same_root(self, dank_db, screen_id):
        flat = generate_ir(dank_db, screen_id=screen_id, semantic=False)
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)
        assert flat["spec"]["root"] == sem["spec"]["root"]


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestSlotDefinitionCoverage:
    """Verify slot definitions in the DB cover the key components."""

    def test_slot_defs_exist_for_nav_top_nav(self, dank_db):
        slot_defs = query_slot_definitions(dank_db)
        assert "nav/top-nav" in slot_defs
        assert len(slot_defs["nav/top-nav"]) == 3

    def test_slot_defs_exist_for_buttons(self, dank_db):
        slot_defs = query_slot_definitions(dank_db)
        button_components = [k for k in slot_defs if k.startswith("button/")]
        assert len(button_components) >= 4

    def test_total_slot_defs_reasonable(self, dank_db):
        slot_defs = query_slot_definitions(dank_db)
        total_slots = sum(len(v) for v in slot_defs.values())
        assert total_slots >= 30, f"Expected 30+ total slot definitions, got {total_slots}"
