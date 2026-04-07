"""Generalizability tests: verify the pipeline works on non-Dank projects.

Creates a synthetic "second project" with different component names, templates,
and layout patterns to prove the pipeline isn't hardcoded to Dank-specific data.
"""

import json
import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.compose import (
    compose_screen,
    build_template_visuals,
    generate_from_prompt,
    resolve_type_aliases,
    validate_components,
)
from dd.db import init_db
from dd.renderers.figma import generate_figma_script
from dd.templates import query_templates


def _setup_ecommerce_project(conn: sqlite3.Connection) -> None:
    """Seed a synthetic e-commerce project with different components than Dank.

    This project uses different naming conventions, different component
    structures, and different layout patterns to prove pipeline generality.
    """
    conn.execute(
        "INSERT INTO files (id, file_key, name) VALUES (1, 'ecom_test_key', 'ShopUI Kit')"
    )

    # Templates with different naming patterns and layouts than Dank
    templates = [
        # nav-bar instead of header/nav/top-nav — horizontal, full-width
        ("header", "nav-bar", "comp_key_navbar", 45,
         "HORIZONTAL", 390, 64, 0, 16, 0, 16, 12, "MIN", "CENTER",
         '[{"type":"SOLID","color":{"r":1,"g":1,"b":1,"a":1}}]', None, None, 1.0,
         "HUG", "HUG", "16"),

        # product-card — vertical card with image + text — different from Dank cards
        ("card", "product-card", "comp_key_prodcard", 120,
         "VERTICAL", 180, 240, 8, 8, 8, 8, 4, "MIN", "MIN",
         '[{"type":"SOLID","color":{"r":0.98,"g":0.98,"b":0.98,"a":1}}]',
         None, None, 1.0, "FIXED", "HUG", "12"),

        # primary-btn — horizontal button with different sizing
        ("button", "primary-btn", "comp_key_pribtn", 80,
         "HORIZONTAL", 160, 44, 0, 24, 0, 24, 8, "CENTER", "CENTER",
         '[{"type":"SOLID","color":{"r":0.2,"g":0.6,"b":1,"a":1}}]',
         None, None, 1.0, "HUG", "HUG", "22"),

        # ghost-btn — button variant, no fill
        ("button", "ghost-btn", None, 30,
         "HORIZONTAL", 120, 36, 0, 12, 0, 12, 4, "CENTER", "CENTER",
         None, None, None, 1.0, "HUG", "HUG", "8"),

        # search-field — a text_input equivalent
        ("search_input", "search-field", "comp_key_search", 15,
         "HORIZONTAL", 358, 40, 0, 12, 0, 12, 8, "MIN", "CENTER",
         '[{"type":"SOLID","color":{"r":0.95,"g":0.95,"b":0.95,"a":1}}]',
         None, None, 1.0, "FILL", "FIXED", "20"),

        # tab-bar — horizontal tab set
        ("tabs", "tab-bar", "comp_key_tabs", 25,
         "HORIZONTAL", 390, 48, 0, 0, 0, 0, 0, "SPACE_BETWEEN", "CENTER",
         '[{"type":"SOLID","color":{"r":1,"g":1,"b":1,"a":1}}]',
         None, None, 1.0, "FILL", "FIXED", None),

        # small-icon — icon variant
        ("icon", "small-icon", "comp_key_smallicon", 200,
         None, 24, 24, 0, 0, 0, 0, 0, None, None,
         None, None, None, 1.0, "FIXED", "FIXED", None),

        # screen template — different dimensions (iPhone 15 Pro Max)
        ("screen", "app-screen", None, 1,
         "VERTICAL", 430, 932, 0, 0, 0, 0, 0, "MIN", "MIN",
         '[{"type":"SOLID","color":{"r":0.96,"g":0.96,"b":0.96,"a":1}}]',
         None, None, 1.0, None, None, None),
    ]

    for tmpl in templates:
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, component_key, instance_count, "
            "layout_mode, width, height, "
            "padding_top, padding_right, padding_bottom, padding_left, "
            "item_spacing, primary_align, counter_align, "
            "fills, strokes, effects, opacity, "
            "layout_sizing_h, layout_sizing_v, corner_radius) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tmpl,
        )

    # Component key registry — bridge to figma_node_ids
    conn.execute(
        "CREATE TABLE IF NOT EXISTS component_key_registry ("
        "component_key TEXT PRIMARY KEY, "
        "figma_node_id TEXT, "
        "name TEXT, "
        "instance_count INTEGER)"
    )
    registry_entries = [
        ("comp_key_navbar", "100:1", "nav-bar", 45),
        ("comp_key_prodcard", "100:2", "product-card", 120),
        ("comp_key_pribtn", "100:3", "primary-btn", 80),
        ("comp_key_search", "100:4", "search-field", 15),
        ("comp_key_tabs", "100:5", "tab-bar", 25),
        ("comp_key_smallicon", "100:6", "small-icon", 200),
    ]
    for entry in registry_entries:
        conn.execute(
            "INSERT INTO component_key_registry "
            "(component_key, figma_node_id, name, instance_count) "
            "VALUES (?, ?, ?, ?)",
            entry,
        )

    conn.commit()


@pytest.fixture
def ecom_db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    seed_catalog(conn)
    _setup_ecommerce_project(conn)
    yield conn
    conn.close()


class TestNonDankTemplateQuery:
    """Verify template querying works with different naming patterns."""

    def test_queries_all_ecom_templates(self, ecom_db):
        templates = query_templates(ecom_db)
        assert "header" in templates
        assert "card" in templates
        assert "button" in templates
        assert "search_input" in templates

    def test_ecom_templates_have_figma_ids(self, ecom_db):
        templates = query_templates(ecom_db)
        navbar = templates["header"][0]
        assert navbar.get("component_figma_id") == "100:1"

    def test_button_has_two_variants(self, ecom_db):
        templates = query_templates(ecom_db)
        assert len(templates["button"]) == 2

    def test_screen_template_uses_different_dimensions(self, ecom_db):
        templates = query_templates(ecom_db)
        screen_tmpl = templates["screen"][0]
        assert screen_tmpl["width"] == 430
        assert screen_tmpl["height"] == 932


class TestNonDankComposition:
    """Verify compose_screen works with non-Dank templates."""

    def test_screen_dimensions_from_ecom_template(self, ecom_db):
        templates = query_templates(ecom_db)
        spec = compose_screen([{"type": "header"}], templates=templates)
        root = spec["elements"][spec["root"]]
        assert root["layout"]["sizing"]["width"] == 430
        assert root["layout"]["sizing"]["height"] == 932

    def test_navbar_layout_is_horizontal(self, ecom_db):
        templates = query_templates(ecom_db)
        spec = compose_screen([{"type": "header"}], templates=templates)
        header = next(el for el in spec["elements"].values() if el["type"] == "header")
        assert header["layout"]["direction"] == "horizontal"

    def test_product_card_layout_is_vertical(self, ecom_db):
        templates = query_templates(ecom_db)
        spec = compose_screen([{"type": "card"}], templates=templates)
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert card["layout"]["direction"] == "vertical"

    def test_variant_selection_picks_primary_btn(self, ecom_db):
        templates = query_templates(ecom_db)
        spec = compose_screen(
            [{"type": "button", "variant": "primary-btn"}],
            templates=templates,
        )
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        assert button["layout"]["sizing"]["width"] == "hug"


class TestNonDankRendering:
    """Verify Figma script generation works with non-Dank visual data."""

    def test_mode1_uses_ecom_figma_ids(self, ecom_db):
        templates = query_templates(ecom_db)
        spec = compose_screen(
            [{"type": "header", "props": {"text": "Shop"}}],
            templates=templates,
        )
        visuals = build_template_visuals(spec, templates)
        script, _ = generate_figma_script(spec, db_visuals=visuals)
        # Should use the ecom navbar figma ID
        assert "100:1" in script

    def test_mode2_falls_back_for_keyless(self, ecom_db):
        templates = query_templates(ecom_db)
        spec = compose_screen(
            [{"type": "button", "variant": "ghost-btn"}],
            templates=templates,
        )
        visuals = build_template_visuals(spec, templates)
        script, _ = generate_figma_script(spec, db_visuals=visuals)
        # ghost-btn has no component_key → Mode 2
        assert "figma.createFrame()" in script

    def test_absolute_root_children_get_positioning(self, ecom_db):
        templates = query_templates(ecom_db)
        spec = compose_screen(
            [{"type": "card"}, {"type": "search_input"}],
            templates=templates,
        )
        visuals = build_template_visuals(spec, templates)
        script, _ = generate_figma_script(spec, db_visuals=visuals)
        # Root is absolute — children get x/y positioning, not FILL width
        assert ".x = 0;" in script
        assert ".y = " in script
        assert "resize(" in script

    def test_text_overrides_on_ecom_components(self, ecom_db):
        templates = query_templates(ecom_db)
        spec = compose_screen(
            [{"type": "button", "variant": "primary-btn", "props": {"text": "Add to Cart"}}],
            templates=templates,
        )
        visuals = build_template_visuals(spec, templates)
        script, _ = generate_figma_script(spec, db_visuals=visuals)
        assert "Add to Cart" in script


class TestNonDankEndToEnd:
    """Full end-to-end pipeline test with ecom project."""

    def test_generate_from_prompt_produces_valid_output(self, ecom_db):
        result = generate_from_prompt(
            ecom_db,
            [
                {"type": "header", "props": {"text": "My Shop"}},
                {"type": "card"},
                {"type": "card"},
                {"type": "button", "variant": "primary-btn", "props": {"text": "Checkout"}},
            ],
        )
        assert result["element_count"] >= 5  # screen + header + 2 cards + button
        assert "structure_script" in result
        assert "100:1" in result["structure_script"]  # navbar Mode 1
        assert "Checkout" in result["structure_script"]

    def test_type_aliases_work_on_ecom(self, ecom_db):
        """Toggle/checkbox alias resolution works in non-Dank projects."""
        templates = query_templates(ecom_db)
        components = [{"type": "toggle", "props": {"text": "Notify"}}, {"type": "checkbox", "props": {"text": "Accept"}}]
        resolved = resolve_type_aliases(components, templates)
        # Both become composed containers (label + icon)
        assert resolved[0]["type"] == "container"
        assert resolved[1]["type"] == "container"
        # Each has icon + text children
        assert any(c["type"] == "icon" for c in resolved[0]["children"])
        assert any(c["type"] == "icon" for c in resolved[1]["children"])

    def test_validate_warns_about_missing_ecom_types(self, ecom_db):
        templates = query_templates(ecom_db)
        components, warnings = validate_components(
            [{"type": "header"}, {"type": "date_picker"}],
            templates,
        )
        assert any("date_picker" in w for w in warnings)
        assert not any("header" in w for w in warnings)

    def test_page_name_works_on_ecom(self, ecom_db):
        result = generate_from_prompt(
            ecom_db,
            [{"type": "header", "props": {"text": "Products"}}],
            page_name="Generated: Products",
        )
        assert "Generated: Products" in result["structure_script"]
