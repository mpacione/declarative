"""Phase 3b integration tests against real Dank DB.

Verifies semantic tree construction collapses the flat IR into
~15-25 elements with named slots, filters system chrome, and
absorbs slot children. Auto-skips if Dank DB not present.
"""

import os
import sqlite3

import pytest

from dd.ir import generate_ir

DANK_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db")
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)

PHONE_SCREEN = 184
TABLET_P_SCREEN = 150
TABLET_L_SCREEN = 118


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


@pytest.fixture
def dank_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DANK_DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestSemanticTreeReduction:
    """Verify semantic tree reduces element count to ~15-25."""

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_semantic_has_fewer_reachable_elements(self, dank_db, screen_id):
        flat = generate_ir(dank_db, screen_id=screen_id, semantic=False)
        sem = generate_ir(dank_db, screen_id=screen_id, semantic=True)

        flat_reachable = _walk_children(flat["spec"], flat["spec"]["root"])
        sem_reachable = _walk_children(sem["spec"], sem["spec"]["root"])

        assert sem_reachable < flat_reachable, (
            f"Screen {screen_id}: semantic ({sem_reachable}) should be less than flat ({flat_reachable})"
        )

    def test_phone_screen_has_15_to_30_elements(self, dank_db):
        sem = generate_ir(dank_db, screen_id=PHONE_SCREEN, semantic=True)
        reachable = _walk_children(sem["spec"], sem["spec"]["root"])
        assert 10 <= reachable <= 40, f"Expected 10-40 reachable elements, got {reachable}"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestSlotAssignment:
    """Verify slot children are assigned to named slots."""

    def test_header_has_named_slots(self, dank_db):
        """Header exposes ≥3 named slots. Exact names are LLM-derived
        via M7.0.b Step 2 (formerly {left, center, right} when hand-
        seeded; now {leading_content, center_content, trailing_content}
        from the Haiku labeller). Test the invariant, not the names.
        """
        sem = generate_ir(dank_db, screen_id=PHONE_SCREEN, semantic=True)
        spec = sem["spec"]

        headers = [
            el for el in spec["elements"].values()
            if el.get("type") == "header"
        ]
        assert len(headers) >= 1, "Expected at least one header element"

        header = headers[0]
        assert "slots" in header, "Header should have slots"
        slot_names = list(header["slots"].keys())
        assert len(slot_names) >= 3, (
            f"header should have ≥3 slots, got {slot_names}"
        )
        assert all(isinstance(n, str) and n for n in slot_names)

    def test_slot_children_not_in_children_list(self, dank_db):
        sem = generate_ir(dank_db, screen_id=PHONE_SCREEN, semantic=True)
        spec = sem["spec"]

        for el in spec["elements"].values():
            if "slots" in el:
                assert "children" not in el, "Element with slots should not have children"

    def test_slot_children_still_in_elements_dict(self, dank_db):
        sem = generate_ir(dank_db, screen_id=PHONE_SCREEN, semantic=True)
        spec = sem["spec"]

        for el in spec["elements"].values():
            for slot_eids in el.get("slots", {}).values():
                for slot_eid in slot_eids:
                    assert slot_eid in spec["elements"], f"Slot child {slot_eid} missing from elements"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestSystemChromeFiltered:
    """Verify system chrome is removed from semantic IR."""

    def test_no_statusbar_elements(self, dank_db):
        sem = generate_ir(dank_db, screen_id=PHONE_SCREEN, semantic=True)
        spec = sem["spec"]
        node_id_map = spec["_node_id_map"]

        for eid, nid in node_id_map.items():
            name = dank_db.execute("SELECT name FROM nodes WHERE id = ?", (nid,)).fetchone()[0]
            assert "_StatusBar" not in name, f"System chrome still present: {eid} ({name})"

    def test_flat_ir_unchanged(self, dank_db):
        flat = generate_ir(dank_db, screen_id=PHONE_SCREEN, semantic=False)
        assert flat["element_count"] > 100, "Flat IR should still have 100+ elements"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestBackwardCompatibility:
    """Verify semantic=False preserves existing behavior."""

    @pytest.mark.parametrize("screen_id", [PHONE_SCREEN, TABLET_P_SCREEN, TABLET_L_SCREEN])
    def test_default_produces_flat_ir(self, dank_db, screen_id):
        result = generate_ir(dank_db, screen_id=screen_id)
        spec = result["spec"]

        has_slots = any("slots" in el for el in spec["elements"].values())
        assert not has_slots, "Default IR should not have slots"
