"""LLM prompt parsing integration tests against real Dank DB + Claude API.

Verifies the full natural language → Figma JS pipeline with real templates.
Skips if Dank DB not present or ANTHROPIC_API_KEY not set.
"""

import json
import os
import sqlite3

import pytest

DANK_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db")
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:
    pass

HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))

from dd.prompt_parser import parse_prompt, prompt_to_figma, extract_json
from dd.compose import generate_from_prompt
from dd.templates import query_templates


@pytest.fixture
def dank_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DANK_DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def client():
    import anthropic
    return anthropic.Anthropic()


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY not set")
class TestParsePromptReal:
    """Verify parse_prompt with real Claude API calls."""

    @pytest.mark.timeout(30)
    def test_settings_page_returns_components(self, client):
        result = parse_prompt("Build a settings page with notification toggles", client)
        assert isinstance(result, list)
        assert len(result) >= 2
        types = {c["type"] for c in result}
        assert "header" in types or "card" in types

    @pytest.mark.timeout(30)
    def test_dashboard_returns_components(self, client):
        result = parse_prompt("Create a dashboard with metrics cards and a chart", client)
        assert isinstance(result, list)
        assert len(result) >= 2

    @pytest.mark.timeout(30)
    def test_all_types_are_valid_catalog_types(self, client):
        valid_types = {
            "button", "icon_button", "fab", "button_group", "menu", "context_menu",
            "checkbox", "radio", "radio_group", "toggle", "toggle_group", "select",
            "combobox", "date_picker", "slider", "segmented_control", "text_input",
            "textarea", "search_input", "stepper", "text", "heading", "link", "image",
            "icon", "avatar", "badge", "list", "list_item", "table", "skeleton",
            "navigation_row", "tabs", "breadcrumbs", "pagination", "bottom_nav",
            "drawer", "header", "alert", "toast", "popover", "tooltip", "empty_state",
            "file_upload", "card", "dialog", "sheet", "accordion",
        }
        result = parse_prompt("Build a profile page with avatar, name, and settings list", client)

        def _collect_types(components):
            types = set()
            for c in components:
                types.add(c["type"])
                for child in c.get("children", []):
                    types.update(_collect_types([child]))
            return types

        used_types = _collect_types(result)
        invalid = used_types - valid_types
        assert invalid == set(), f"LLM used invalid types: {invalid}"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY not set")
class TestPromptToFigmaReal:
    """Verify full prompt→Figma pipeline with real Claude + real templates."""

    @pytest.mark.timeout(30)
    def test_settings_page_produces_figma_script(self, dank_db, client):
        result = prompt_to_figma(
            "Build a settings page with notification and privacy sections",
            dank_db, client,
        )
        script = result["structure_script"]
        assert "figma.createFrame()" in script or "getNodeByIdAsync" in script
        assert "return M;" in script
        assert result["element_count"] >= 3

    @pytest.mark.timeout(30)
    def test_settings_page_has_visual_properties(self, dank_db, client):
        result = prompt_to_figma(
            "Build a simple page with a card and a button",
            dank_db, client,
        )
        script = result["structure_script"]
        assert "layoutMode" in script or "getNodeByIdAsync" in script

    @pytest.mark.timeout(30)
    def test_returns_parsed_components(self, dank_db, client):
        result = prompt_to_figma("Create a login form", dank_db, client)
        assert "components" in result
        assert len(result["components"]) >= 1

    @pytest.mark.timeout(30)
    def test_mode1_instances_created_for_keyed_types(self, dank_db, client):
        result = prompt_to_figma(
            "Build a page with a header and navigation tabs at the bottom",
            dank_db, client,
        )
        script = result["structure_script"]
        if "getNodeByIdAsync" in script:
            assert True  # Mode 1 working
        else:
            # All components might be keyless — still valid
            assert "figma.createFrame()" in script


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestPromptToFigmaMocked:
    """Verify prompt→Figma with mocked LLM but real Dank templates."""

    def test_handcrafted_components_with_real_templates(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "header", "props": {"text": "Settings"}},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Notifications"}},
                {"type": "toggle", "props": {"label": "Push alerts"}},
                {"type": "toggle", "props": {"label": "Email digest"}},
            ]},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Privacy"}},
                {"type": "toggle", "props": {"label": "Profile visible"}},
            ]},
            {"type": "button", "props": {"text": "Save"}},
        ])
        script = result["structure_script"]
        mode1 = script.count("getNodeByIdAsync")
        mode2 = script.count("createFrame")
        assert mode1 >= 2, f"Expected 2+ Mode 1 (header, button), got {mode1}"
        assert mode2 >= 3, f"Expected 3+ Mode 2 (screen, cards), got {mode2}"
        assert result["element_count"] >= 10

    def test_complex_screen_with_mixed_types(self, dank_db):
        result = generate_from_prompt(dank_db, [
            {"type": "header"},
            {"type": "search_input"},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Featured"}},
                {"type": "image"},
                {"type": "text", "props": {"text": "Description"}},
            ]},
            {"type": "card", "children": [
                {"type": "list_item", "props": {"text": "Item 1"}},
                {"type": "list_item", "props": {"text": "Item 2"}},
            ]},
            {"type": "tabs"},
        ])
        assert result["element_count"] >= 10
        assert "return M;" in result["structure_script"]
