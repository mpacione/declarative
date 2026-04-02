"""Phase 3a integration tests against real Dank DB.

Verifies that component extraction populated the composition tables
with slot definitions, a11y contracts, and instance linkage.
Auto-skips if the Dank DB file is not present.
"""

import os
import sqlite3

import pytest

DANK_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db")
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)


@pytest.fixture
def dank_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DANK_DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestCompositionTablesPopulated:
    """Verify extract_components populated the composition tables."""

    def test_components_table_has_entries(self, dank_db):
        count = dank_db.execute("SELECT COUNT(*) FROM components").fetchone()[0]
        assert count > 10, f"Expected 10+ components, got {count}"

    def test_component_slots_has_entries(self, dank_db):
        count = dank_db.execute("SELECT COUNT(*) FROM component_slots").fetchone()[0]
        assert count > 20, f"Expected 20+ slots, got {count}"

    def test_component_a11y_has_entries(self, dank_db):
        count = dank_db.execute("SELECT COUNT(*) FROM component_a11y").fetchone()[0]
        assert count > 10, f"Expected 10+ a11y entries, got {count}"

    def test_instances_linked_to_components(self, dank_db):
        count = dank_db.execute("SELECT COUNT(*) FROM nodes WHERE component_id IS NOT NULL").fetchone()[0]
        assert count > 5000, f"Expected 5000+ linked instances, got {count}"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestKeyComponentsPresent:
    """Verify key structural components were extracted."""

    def test_nav_top_nav_exists(self, dank_db):
        row = dank_db.execute("SELECT * FROM components WHERE name = 'nav/top-nav'").fetchone()
        assert row is not None

    def test_buttons_exist(self, dank_db):
        buttons = dank_db.execute(
            "SELECT name FROM components WHERE name LIKE 'button/%'"
        ).fetchall()
        assert len(buttons) >= 4, f"Expected 4+ button variants, got {len(buttons)}"

    def test_field_input_exists(self, dank_db):
        row = dank_db.execute("SELECT * FROM components WHERE name = 'field/input'").fetchone()
        assert row is not None

    def test_nav_tabs_exists(self, dank_db):
        row = dank_db.execute("SELECT * FROM components WHERE name = 'nav/tabs'").fetchone()
        assert row is not None


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestSlotDefinitions:
    """Verify slot definitions are correct for key components."""

    def test_nav_top_nav_has_three_slots(self, dank_db):
        comp_id = dank_db.execute(
            "SELECT id FROM components WHERE name = 'nav/top-nav'"
        ).fetchone()[0]
        slots = dank_db.execute(
            "SELECT name FROM component_slots WHERE component_id = ? ORDER BY sort_order",
            (comp_id,),
        ).fetchall()
        slot_names = [s[0] for s in slots]
        assert len(slot_names) == 3
        assert "left" in slot_names
        assert "center" in slot_names
        assert "right" in slot_names

    def test_button_has_icon_and_text_slots(self, dank_db):
        comp_id = dank_db.execute(
            "SELECT id FROM components WHERE name = 'button/large/solid'"
        ).fetchone()[0]
        slots = dank_db.execute(
            "SELECT name, slot_type FROM component_slots WHERE component_id = ? ORDER BY sort_order",
            (comp_id,),
        ).fetchall()
        slot_types = [s[1] for s in slots]
        assert "icon" in slot_types
        assert "text" in slot_types

    def test_field_input_has_text_slot(self, dank_db):
        comp_id = dank_db.execute(
            "SELECT id FROM components WHERE name = 'field/input'"
        ).fetchone()[0]
        slots = dank_db.execute(
            "SELECT name, slot_type FROM component_slots WHERE component_id = ?",
            (comp_id,),
        ).fetchall()
        slot_types = [s[1] for s in slots]
        assert "text" in slot_types


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestA11yContracts:
    """Verify accessibility contracts are correct."""

    def test_buttons_have_button_role(self, dank_db):
        rows = dank_db.execute("""
            SELECT c.name, ca.role
            FROM component_a11y ca
            JOIN components c ON ca.component_id = c.id
            WHERE c.name LIKE 'button/%'
        """).fetchall()
        for r in rows:
            assert r[1] == "button", f"{r[0]} should have role=button, got {r[1]}"

    def test_nav_has_navigation_role(self, dank_db):
        row = dank_db.execute("""
            SELECT ca.role
            FROM component_a11y ca
            JOIN components c ON ca.component_id = c.id
            WHERE c.name = 'nav/top-nav'
        """).fetchone()
        assert row[0] == "navigation"

    def test_interactive_components_have_touch_targets(self, dank_db):
        rows = dank_db.execute("""
            SELECT c.name, ca.min_touch_target
            FROM component_a11y ca
            JOIN components c ON ca.component_id = c.id
            WHERE c.category IN ('button', 'input', 'nav')
        """).fetchall()
        for r in rows:
            assert r[1] == 44.0, f"{r[0]} should have min_touch_target=44, got {r[1]}"

    def test_icons_have_img_role(self, dank_db):
        rows = dank_db.execute("""
            SELECT c.name, ca.role
            FROM component_a11y ca
            JOIN components c ON ca.component_id = c.id
            WHERE c.category = 'icon'
        """).fetchall()
        for r in rows:
            assert r[1] == "img", f"{r[0]} should have role=img, got {r[1]}"
