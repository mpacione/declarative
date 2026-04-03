"""Phase 4b integration tests against real Dank DB.

Verifies prompt→IR composition + template-based rendering produces
valid Figma JS using real extracted templates from the Dank file.
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
class TestComposeWithRealTemplates:
    """Verify compose_screen uses real Dank templates for layout defaults."""

    def test_header_gets_layout_from_keyed_template(self, dank_db):
        templates = query_templates(dank_db)
        spec = compose_screen([{"type": "header"}], templates=templates)
        header = next(el for el in spec["elements"].values() if el["type"] == "header")
        # nav/top-nav (keyed, Mode 1) has layout_mode=None → "stacked"
        # Layout is inherited from the component instance, not set by us
        assert "layout" in header

    def test_card_gets_vertical_layout(self, dank_db):
        templates = query_templates(dank_db)
        spec = compose_screen([{"type": "card"}], templates=templates)
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert card["layout"]["direction"] == "vertical"

    def test_card_gets_padding_from_template(self, dank_db):
        templates = query_templates(dank_db)
        spec = compose_screen([{"type": "card"}], templates=templates)
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert "padding" in card["layout"]
        assert card["layout"]["padding"]["top"] > 0

    def test_button_gets_dimensions_from_template(self, dank_db):
        templates = query_templates(dank_db)
        spec = compose_screen([{"type": "button"}], templates=templates)
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        assert "sizing" in button["layout"]
        w = button["layout"]["sizing"]["width"]
        h = button["layout"]["sizing"]["height"]
        assert (isinstance(w, str) and w in ("hug", "fill", "fixed")) or (isinstance(w, (int, float)) and w > 0)
        assert (isinstance(h, str) and h in ("hug", "fill", "fixed")) or (isinstance(h, (int, float)) and h > 0)


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestTemplateVisualsFromRealDB:
    """Verify build_template_visuals produces visual data from real templates."""

    def test_card_gets_fills(self, dank_db):
        templates = query_templates(dank_db)
        spec = compose_screen([{"type": "card"}], templates=templates)
        visuals = build_template_visuals(spec, templates)
        card_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "card")
        nid = spec["_node_id_map"][card_eid]
        assert visuals[nid]["fills"] is not None

    def test_card_gets_corner_radius(self, dank_db):
        templates = query_templates(dank_db)
        spec = compose_screen([{"type": "card"}], templates=templates)
        visuals = build_template_visuals(spec, templates)
        card_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "card")
        nid = spec["_node_id_map"][card_eid]
        assert visuals[nid]["corner_radius"] is not None

    def test_heading_gets_fills(self, dank_db):
        templates = query_templates(dank_db)
        spec = compose_screen([{"type": "heading", "props": {"text": "Title"}}], templates=templates)
        visuals = build_template_visuals(spec, templates)
        h_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "heading")
        nid = spec["_node_id_map"][h_eid]
        assert visuals[nid]["fills"] is not None

    def test_all_elements_get_visual_entries(self, dank_db):
        templates = query_templates(dank_db)
        spec = compose_screen([
            {"type": "header"},
            {"type": "card", "children": [{"type": "heading", "props": {"text": "T"}}]},
            {"type": "button", "props": {"text": "Go"}},
        ], templates=templates)
        visuals = build_template_visuals(spec, templates)
        for eid in spec["elements"]:
            nid = spec["_node_id_map"][eid]
            assert nid in visuals, f"Element {eid} missing from visuals"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestGenerateFromPromptEndToEnd:
    """Verify generate_from_prompt produces complete Figma JS from real templates."""

    def test_settings_page(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "header", "props": {"text": "Settings"}},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Notifications"}},
                {"type": "text", "props": {"text": "Enable push notifications"}},
            ]},
            {"type": "button", "props": {"text": "Save"}},
        ])
        script = result["structure_script"]
        assert "figma.createFrame()" in script
        assert "fills = [{" in script
        assert "layoutMode" in script
        assert "resize(" in script
        assert result["element_count"] >= 6

    def test_simple_screen_with_button(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "button", "props": {"text": "Click me"}},
        ])
        assert "figma.createFrame()" in result["structure_script"]
        assert result["element_count"] >= 2

    def test_complex_screen_with_multiple_cards(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "header"},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Section 1"}},
                {"type": "text", "props": {"text": "Content 1"}},
            ]},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Section 2"}},
                {"type": "text", "props": {"text": "Content 2"}},
            ]},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Section 3"}},
                {"type": "text", "props": {"text": "Content 3"}},
            ]},
            {"type": "button", "props": {"text": "Done"}},
        ])
        assert result["element_count"] >= 12
        assert result["structure_script"].count("cornerRadius") >= 3

    def test_script_has_return_statement(self, dank_db):
        result = generate_from_prompt(dank_db, [{"type": "button"}])
        assert "return M;" in result["structure_script"]

    def test_script_has_font_loading(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "text", "props": {"text": "Hello"}},
        ])
        assert "loadFontAsync" in result["structure_script"]

    def test_script_appends_to_page(self, dank_db):
        result = generate_from_prompt(dank_db, [{"type": "button"}])
        assert "figma.currentPage.appendChild" in result["structure_script"]

    def test_empty_components_produces_empty_screen(self, dank_db):
        result = generate_from_prompt(dank_db, [])
        assert "figma.createFrame()" in result["structure_script"]
        assert result["element_count"] == 1

    def test_nested_children_wired_correctly(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Title"}},
            ]},
        ])
        script = result["structure_script"]
        assert "appendChild" in script
        lines = script.split("\n")
        heading_var = None
        card_var = None
        for line in lines:
            if '"heading-1"' in line and ".name" in line:
                heading_var = line.split(".name")[0].strip().split()[-1]
            if '"card-1"' in line and ".name" in line:
                card_var = line.split(".name")[0].strip().split()[-1]
        assert heading_var and card_var
        assert f"{card_var}.appendChild({heading_var})" in script
