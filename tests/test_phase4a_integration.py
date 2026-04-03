"""Phase 4a integration tests against real Dank DB.

Verifies template extraction produces correct templates with structure,
visual defaults, and component keys from real extracted data.
Auto-skips if the Dank DB file is not present.
"""

import os
import sqlite3

import pytest

from dd.templates import extract_templates, query_templates

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
class TestTemplateExtraction:
    """Verify extract_templates produces templates from real Dank data."""

    def test_creates_templates(self, dank_db):
        count = dank_db.execute("SELECT COUNT(*) FROM component_templates").fetchone()[0]
        assert count > 50, f"Expected 50+ templates, got {count}"

    def test_covers_all_catalog_types(self, dank_db):
        templates = query_templates(dank_db)
        expected_types = {"button", "header", "icon", "text", "heading", "card", "tabs"}
        actual_types = set(templates.keys())
        missing = expected_types - actual_types
        assert missing == set(), f"Missing catalog types: {missing}"

    def test_header_has_component_key(self, dank_db):
        templates = query_templates(dank_db)
        header_templates = templates.get("header", [])
        keyed = [t for t in header_templates if t.get("component_key")]
        assert len(keyed) >= 1, "Expected at least one header template with componentKey"

    def test_button_has_multiple_variants(self, dank_db):
        templates = query_templates(dank_db)
        button_templates = templates.get("button", [])
        assert len(button_templates) >= 3, f"Expected 3+ button variants, got {len(button_templates)}"

    def test_icon_templates_have_component_keys(self, dank_db):
        templates = query_templates(dank_db)
        icon_templates = templates.get("icon", [])
        keyed = [t for t in icon_templates if t.get("component_key")]
        assert len(keyed) >= 50, f"Expected 50+ icon templates with keys, got {len(keyed)}"


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
class TestTemplateStructureQuality:
    """Verify extracted templates have correct structural data."""

    def test_header_template_has_correct_dimensions(self, dank_db):
        templates = query_templates(dank_db)
        header_keyed = [t for t in templates["header"] if t.get("component_key")]
        assert len(header_keyed) >= 1
        header = header_keyed[0]
        assert header["width"] == 428.0
        assert header["height"] == 111.0

    def test_button_template_has_layout(self, dank_db):
        templates = query_templates(dank_db)
        button_keyed = [t for t in templates["button"] if t.get("component_key")]
        horizontal = [t for t in button_keyed if t.get("layout_mode") == "HORIZONTAL"]
        assert len(horizontal) >= 1, "Expected at least one HORIZONTAL button template"

    def test_icon_template_has_standard_dimensions(self, dank_db):
        templates = query_templates(dank_db)
        icon_20x20 = [t for t in templates["icon"] if t.get("width") == 20.0 and t.get("height") == 20.0]
        assert len(icon_20x20) >= 50, f"Expected 50+ 20x20 icon templates, got {len(icon_20x20)}"

    def test_card_template_has_vertical_layout(self, dank_db):
        templates = query_templates(dank_db)
        card_templates = templates.get("card", [])
        assert len(card_templates) >= 1
        card = card_templates[0]
        assert card["layout_mode"] == "VERTICAL"

    def test_tabs_template_has_component_key(self, dank_db):
        templates = query_templates(dank_db)
        tabs_keyed = [t for t in templates.get("tabs", []) if t.get("component_key")]
        assert len(tabs_keyed) >= 1

    def test_all_templates_have_instance_count(self, dank_db):
        templates = query_templates(dank_db)
        for cat_type, variants in templates.items():
            for t in variants:
                assert t["instance_count"] is not None and t["instance_count"] > 0, (
                    f"{cat_type}/{t.get('variant')}: instance_count should be > 0"
                )

    def test_mode_1_templates_have_component_keys(self, dank_db):
        templates = query_templates(dank_db)
        mode_1_types = {"icon", "button", "header", "tabs", "drawer"}
        for cat_type in mode_1_types:
            if cat_type not in templates:
                continue
            keyed = [t for t in templates[cat_type] if t.get("component_key")]
            assert len(keyed) >= 1, f"{cat_type}: expected at least one template with componentKey"
