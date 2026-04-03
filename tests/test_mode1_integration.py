"""Mode 1 rendering integration tests against real Dank DB.

Verifies that component instances are created via getNodeByIdAsync
for templates with component keys, and Mode 2 frames for keyless types.
Auto-skips if the Dank DB file is not present.
"""

import os
import sqlite3

import pytest

from dd.compose import build_template_visuals, compose_screen, generate_from_prompt
from dd.templates import query_templates

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
class TestMode1InstanceCreation:
    """Verify Mode 1 emits getNodeByIdAsync for keyed components."""

    def test_header_uses_mode1(self, dank_db):
        result = generate_from_prompt(dank_db, [{"type": "header"}])
        assert "getNodeByIdAsync" in result["structure_script"]

    def test_button_uses_mode1(self, dank_db):
        result = generate_from_prompt(dank_db, [{"type": "button"}])
        assert "getNodeByIdAsync" in result["structure_script"]

    def test_tabs_uses_mode1(self, dank_db):
        result = generate_from_prompt(dank_db, [{"type": "tabs"}])
        assert "getNodeByIdAsync" in result["structure_script"]

    def test_card_uses_mode2(self, dank_db):
        result = generate_from_prompt(dank_db, [{"type": "card"}])
        script = result["structure_script"]
        assert "getNodeByIdAsync" not in script
        assert "figma.createFrame()" in script

    def test_heading_uses_mode2(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "heading", "props": {"text": "Title"}},
        ])
        script = result["structure_script"]
        assert "getNodeByIdAsync" not in script
        assert "figma.createText()" in script


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestMode1SkipsLayoutAndVisual:
    """Verify Mode 1 elements don't emit layout/visual JS (inherited from master)."""

    def test_mode1_header_no_layout_mode(self, dank_db):
        result = generate_from_prompt(dank_db, [{"type": "header"}])
        lines = result["structure_script"].split("\n")
        header_lines = [l for l in lines if "header-1" in l]
        assert not any("layoutMode" in l for l in header_lines)

    def test_mode1_button_no_fills(self, dank_db):
        result = generate_from_prompt(dank_db, [{"type": "button"}])
        lines = result["structure_script"].split("\n")
        button_lines = [l for l in lines if "button-1" in l]
        assert not any("fills" in l for l in button_lines)

    def test_mode2_card_has_fills(self, dank_db):
        result = generate_from_prompt(dank_db, [{"type": "card"}])
        assert "fills = [{" in result["structure_script"]


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestMode1ChildrenSkipped:
    """Verify children of Mode 1 elements are not created separately."""

    def test_mode1_button_children_not_in_script(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "button", "children": [
                {"type": "icon"},
                {"type": "text", "props": {"text": "Label"}},
            ]},
        ])
        script = result["structure_script"]
        # Mode 1 button's children come from the instance, not created
        assert script.count("getNodeByIdAsync") == 1  # just the button
        assert '"icon-1"' not in script


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestMixedModeScreen:
    """Verify a realistic screen mixes Mode 1 and Mode 2 correctly."""

    def test_settings_screen_mode_distribution(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "header"},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "General"}},
                {"type": "text", "props": {"text": "App settings"}},
            ]},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Account"}},
                {"type": "text", "props": {"text": "Profile info"}},
            ]},
            {"type": "button"},
            {"type": "tabs"},
        ])
        script = result["structure_script"]

        mode1_count = script.count("getNodeByIdAsync")
        mode2_frames = script.count("figma.createFrame()")
        mode2_text = script.count("figma.createText()")

        assert mode1_count == 3, f"Expected 3 Mode 1 (header, button, tabs), got {mode1_count}"
        assert mode2_frames >= 2, f"Expected 2+ Mode 2 frames (screen, cards), got {mode2_frames}"
        assert mode2_text >= 4, f"Expected 4+ text nodes, got {mode2_text}"

    def test_component_key_in_visuals(self, dank_db):
        templates = query_templates(dank_db)
        spec = compose_screen([{"type": "header"}, {"type": "card"}], templates=templates)
        visuals = build_template_visuals(spec, templates)

        header_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "header")
        card_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "card")

        header_nid = spec["_node_id_map"][header_eid]
        card_nid = spec["_node_id_map"][card_eid]

        assert visuals[header_nid].get("component_key") is not None
        assert visuals[card_nid].get("component_key") is None

    def test_component_figma_id_in_visuals(self, dank_db):
        templates = query_templates(dank_db)
        spec = compose_screen([{"type": "header"}], templates=templates)
        visuals = build_template_visuals(spec, templates)

        header_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "header")
        header_nid = spec["_node_id_map"][header_eid]

        assert visuals[header_nid].get("component_figma_id") is not None


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestMode1TextOverrides:
    """Verify Mode 1 instances set text content from props."""

    def test_button_text_override(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "button", "props": {"text": "Save Changes"}},
        ])
        script = result["structure_script"]
        assert "Save Changes" in script

    def test_header_text_override(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "header", "props": {"text": "Settings"}},
        ])
        script = result["structure_script"]
        assert "Settings" in script
