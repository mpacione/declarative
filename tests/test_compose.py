"""Tests for prompt→IR composition (Phase 4b)."""

import json
import sqlite3

import pytest

from dd.db import init_db
from dd.catalog import seed_catalog
from dd.compose import compose_screen, build_template_visuals, generate_from_prompt
from dd.generate import generate_figma_script


# ---------------------------------------------------------------------------
# compose_screen tests
# ---------------------------------------------------------------------------

class TestComposeScreen:
    """Verify compose_screen builds a spec from a component list."""

    def test_produces_spec_with_root(self):
        spec = compose_screen([{"type": "header"}, {"type": "button"}])
        assert "root" in spec
        assert spec["root"] in spec["elements"]

    def test_root_has_children(self):
        spec = compose_screen([{"type": "header"}, {"type": "button"}])
        root = spec["elements"][spec["root"]]
        assert "children" in root
        assert len(root["children"]) == 2

    def test_elements_have_type(self):
        spec = compose_screen([{"type": "header"}, {"type": "card"}])
        types = {el["type"] for el in spec["elements"].values()}
        assert "header" in types
        assert "card" in types

    def test_elements_have_unique_ids(self):
        spec = compose_screen([{"type": "button"}, {"type": "button"}])
        button_ids = [eid for eid in spec["elements"] if eid.startswith("button")]
        assert len(button_ids) == 2
        assert button_ids[0] != button_ids[1]

    def test_props_passed_through(self):
        spec = compose_screen([{"type": "button", "props": {"text": "Save"}}])
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        assert button["props"]["text"] == "Save"

    def test_nested_children(self):
        spec = compose_screen([{
            "type": "card",
            "children": [
                {"type": "heading", "props": {"text": "Title"}},
                {"type": "text", "props": {"text": "Body"}},
            ],
        }])
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert len(card["children"]) == 2

    def test_layout_from_templates(self):
        templates = {
            "header": [{"layout_mode": "HORIZONTAL", "width": 428.0, "height": 111.0,
                         "padding_top": 0, "padding_right": 0, "padding_bottom": 0, "padding_left": 0,
                         "item_spacing": None, "primary_align": None, "counter_align": None}],
        }
        spec = compose_screen([{"type": "header"}], templates=templates)
        header = next(el for el in spec["elements"].values() if el["type"] == "header")
        assert header["layout"]["direction"] == "horizontal"
        assert header["layout"]["sizing"]["width"] == 428.0

    def test_empty_list_produces_empty_screen(self):
        spec = compose_screen([])
        root = spec["elements"][spec["root"]]
        assert root["children"] == []

    def test_version_present(self):
        spec = compose_screen([])
        assert spec["version"] == "1.0"


# ---------------------------------------------------------------------------
# build_template_visuals tests
# ---------------------------------------------------------------------------

class TestBuildTemplateVisuals:
    """Verify build_template_visuals maps elements to template visual data."""

    def _make_templates(self):
        return {
            "button": [{"fills": '[{"type":"SOLID","color":{"r":0,"g":0.5,"b":1,"a":1}}]',
                         "strokes": None, "effects": None, "corner_radius": "10",
                         "opacity": 1.0, "stroke_weight": None,
                         "component_key": "key_btn_solid"}],
            "header": [{"fills": '[{"type":"SOLID","color":{"r":0.98,"g":0.98,"b":0.98,"a":1}}]',
                         "strokes": None, "effects": '[{"type":"BACKGROUND_BLUR","visible":true,"radius":15}]',
                         "corner_radius": None, "opacity": 0.95, "stroke_weight": None}],
        }

    def test_returns_visuals_dict(self):
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, self._make_templates())
        assert isinstance(visuals, dict)
        assert len(visuals) > 0

    def test_assigns_synthetic_node_ids(self):
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, self._make_templates())
        assert "_node_id_map" in spec
        for eid in spec["elements"]:
            assert eid in spec["_node_id_map"]

    def test_visuals_have_fills(self):
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, self._make_templates())
        button_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "button")
        nid = spec["_node_id_map"][button_eid]
        assert visuals[nid]["fills"] is not None

    def test_visuals_have_bindings_list(self):
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, self._make_templates())
        for v in visuals.values():
            assert "bindings" in v
            assert v["bindings"] == []

    def test_unknown_type_gets_empty_visual(self):
        spec = compose_screen([{"type": "unknown_widget"}])
        visuals = build_template_visuals(spec, self._make_templates())
        unknown_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "unknown_widget")
        nid = spec["_node_id_map"][unknown_eid]
        assert visuals[nid]["fills"] is None

    def test_component_key_propagated(self):
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, self._make_templates())
        button_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "button")
        nid = spec["_node_id_map"][button_eid]
        assert visuals[nid]["component_key"] == "key_btn_solid"

    def test_no_component_key_for_unknown_type(self):
        spec = compose_screen([{"type": "unknown_widget"}])
        visuals = build_template_visuals(spec, self._make_templates())
        eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "unknown_widget")
        nid = spec["_node_id_map"][eid]
        assert visuals[nid]["component_key"] is None


# ---------------------------------------------------------------------------
# generate_from_prompt tests
# ---------------------------------------------------------------------------

class TestGenerateFromPrompt:
    """Verify generate_from_prompt produces valid Figma JS."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
        # Insert a template
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, component_key, instance_count, "
            "layout_mode, width, height, padding_top, padding_right, padding_bottom, padding_left, "
            "item_spacing, fills, corner_radius, opacity) "
            "VALUES ('button', 'default', NULL, 10, "
            "'HORIZONTAL', 200, 48, 0, 16, 0, 16, "
            "10, '[{\"type\":\"SOLID\",\"color\":{\"r\":0,\"g\":0.5,\"b\":1,\"a\":1}}]', '10', 1.0)"
        )
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, instance_count, "
            "layout_mode, width, height, fills, opacity) "
            "VALUES ('heading', 'default', 5, "
            "NULL, 396, 28, NULL, 1.0)"
        )
        conn.commit()
        yield conn
        conn.close()

    def test_produces_figma_script(self, db):
        result = generate_from_prompt(
            db,
            [{"type": "button", "props": {"text": "Click me"}}],
        )
        assert "structure_script" in result
        assert "figma.createFrame()" in result["structure_script"]

    def test_script_has_visual_properties(self, db):
        result = generate_from_prompt(
            db,
            [{"type": "button", "props": {"text": "Click me"}}],
        )
        script = result["structure_script"]
        assert "fills = [{" in script

    def test_script_has_layout(self, db):
        result = generate_from_prompt(
            db,
            [{"type": "button", "props": {"text": "Click me"}}],
        )
        script = result["structure_script"]
        assert "layoutMode" in script
        assert "resize(" in script

    def test_element_count(self, db):
        result = generate_from_prompt(
            db,
            [
                {"type": "heading", "props": {"text": "Title"}},
                {"type": "button", "props": {"text": "Save"}},
            ],
        )
        assert result["element_count"] >= 3  # screen + heading + button
