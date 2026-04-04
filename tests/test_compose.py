"""Tests for prompt→IR composition (Phase 4b)."""

import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.compose import build_template_visuals, collect_template_rebind_entries, compare_generated_vs_ground_truth, compose_screen, generate_from_prompt
from dd.db import init_db

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

    def test_extracts_bound_variables_from_fills(self):
        templates = {
            "button": [{
                "fills": '[{"type":"SOLID","color":{"r":0,"g":0,"b":0,"a":1},'
                         '"boundVariables":{"color":{"type":"VARIABLE_ALIAS","id":"VariableID:5438:33630"}}}]',
                "strokes": None, "effects": None, "corner_radius": None,
                "opacity": 1.0, "stroke_weight": None,
            }],
        }
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, templates)
        button_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "button")
        nid = spec["_node_id_map"][button_eid]
        bindings = visuals[nid]["bindings"]
        assert len(bindings) >= 1
        assert bindings[0]["property"] == "fill.0.color"
        assert bindings[0]["variable_id"] == "VariableID:5438:33630"

    def test_extracts_bound_variables_from_strokes(self):
        templates = {
            "card": [{
                "fills": None,
                "strokes": '[{"type":"SOLID","color":{"r":0.5,"g":0.5,"b":0.5,"a":1},'
                           '"boundVariables":{"color":{"type":"VARIABLE_ALIAS","id":"VariableID:111:222"}}}]',
                "effects": None, "corner_radius": None,
                "opacity": 1.0, "stroke_weight": None,
            }],
        }
        spec = compose_screen([{"type": "card"}])
        visuals = build_template_visuals(spec, templates)
        card_eid = next(eid for eid, el in spec["elements"].items() if el["type"] == "card")
        nid = spec["_node_id_map"][card_eid]
        bindings = visuals[nid]["bindings"]
        assert any(b["property"] == "stroke.0.color" for b in bindings)


# ---------------------------------------------------------------------------
# collect_template_rebind_entries tests
# ---------------------------------------------------------------------------

class TestCollectTemplateRebindEntries:
    """Verify rebind entries are collected from template boundVariables."""

    def test_collects_entries_from_fills(self):
        templates = {
            "button": [{
                "fills": '[{"type":"SOLID","color":{"r":0,"g":0,"b":0,"a":1},'
                         '"boundVariables":{"color":{"type":"VARIABLE_ALIAS","id":"VariableID:5438:33630"}}}]',
                "strokes": None, "effects": None, "corner_radius": None,
                "opacity": 1.0, "stroke_weight": None,
            }],
        }
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, templates)
        entries = collect_template_rebind_entries(spec, visuals)
        button_entries = [e for e in entries if e["element_id"].startswith("button")]
        assert len(button_entries) >= 1
        assert button_entries[0]["variable_id"] == "VariableID:5438:33630"

    def test_empty_when_no_bound_variables(self):
        templates = {
            "card": [{
                "fills": '[{"type":"SOLID","color":{"r":1,"g":1,"b":1,"a":1}}]',
                "strokes": None, "effects": None, "corner_radius": None,
                "opacity": 1.0, "stroke_weight": None,
            }],
        }
        spec = compose_screen([{"type": "card"}])
        visuals = build_template_visuals(spec, templates)
        entries = collect_template_rebind_entries(spec, visuals)
        card_entries = [e for e in entries if e["element_id"].startswith("card")]
        assert len(card_entries) == 0

    def test_entries_have_required_keys(self):
        templates = {
            "button": [{
                "fills": '[{"type":"SOLID","color":{"r":0,"g":0,"b":0,"a":1},'
                         '"boundVariables":{"color":{"type":"VARIABLE_ALIAS","id":"VariableID:1:2"}}}]',
                "strokes": None, "effects": None, "corner_radius": None,
                "opacity": 1.0, "stroke_weight": None,
            }],
        }
        spec = compose_screen([{"type": "button"}])
        visuals = build_template_visuals(spec, templates)
        entries = collect_template_rebind_entries(spec, visuals)
        for entry in entries:
            assert "element_id" in entry
            assert "property" in entry
            assert "variable_id" in entry


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

    def test_includes_template_rebind_entries(self, db):
        result = generate_from_prompt(
            db,
            [{"type": "button", "props": {"text": "Save"}}],
        )
        assert "template_rebind_entries" in result
        assert isinstance(result["template_rebind_entries"], list)


# ---------------------------------------------------------------------------
# Variant-aware template selection tests
# ---------------------------------------------------------------------------

class TestVariantAwareSelection:
    """Verify compose_screen uses variant to select specific templates."""

    def test_variant_passed_through_to_element(self):
        spec = compose_screen([
            {"type": "button", "variant": "button/large/translucent"},
        ])
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        assert button["variant"] == "button/large/translucent"

    def test_variant_selects_matching_template(self):
        templates = {
            "button": [
                {"variant": "button/small/solid", "layout_mode": "HORIZONTAL",
                 "width": 100, "height": 40, "instance_count": 500},
                {"variant": "button/large/translucent", "layout_mode": "HORIZONTAL",
                 "width": 152, "height": 52, "instance_count": 3606},
            ],
        }
        spec = compose_screen(
            [{"type": "button", "variant": "button/large/translucent"}],
            templates=templates,
        )
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        assert button["layout"]["sizing"]["width"] == 152

    def test_sizing_mode_from_template(self):
        templates = {
            "card": [{
                "layout_mode": "VERTICAL", "width": 428, "height": 194,
                "layout_sizing_h": "HUG", "layout_sizing_v": "HUG",
                "instance_count": 50,
            }],
        }
        spec = compose_screen([{"type": "card"}], templates=templates)
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert card["layout"]["sizing"]["width"] == "hug"
        assert card["layout"]["sizing"]["height"] == "hug"

    def test_fixed_sizing_when_no_mode(self):
        templates = {
            "card": [{
                "layout_mode": "VERTICAL", "width": 428, "height": 194,
                "instance_count": 50,
            }],
        }
        spec = compose_screen([{"type": "card"}], templates=templates)
        card = next(el for el in spec["elements"].values() if el["type"] == "card")
        assert card["layout"]["sizing"]["width"] == 428
        assert card["layout"]["sizing"]["height"] == 194

    def test_without_variant_uses_highest_count(self):
        templates = {
            "button": [
                {"variant": "button/small/solid", "layout_mode": "HORIZONTAL",
                 "width": 100, "height": 40, "instance_count": 500,
                 "component_key": "key_small"},
                {"variant": "button/large/translucent", "layout_mode": "HORIZONTAL",
                 "width": 152, "height": 52, "instance_count": 3606,
                 "component_key": "key_large"},
            ],
        }
        spec = compose_screen([{"type": "button"}], templates=templates)
        button = next(el for el in spec["elements"].values() if el["type"] == "button")
        assert button["layout"]["sizing"]["width"] == 152


# ---------------------------------------------------------------------------
# Ground truth comparison tests
# ---------------------------------------------------------------------------

class TestCompareGeneratedVsGroundTruth:
    """Verify automated ground truth comparison against real DB screens."""

    @pytest.fixture
    def db(self, tmp_path):
        db_path = str(tmp_path / "test.declarative.db")
        conn = init_db(db_path)
        seed_catalog(conn)

        conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'Test')")
        file_id = conn.execute("SELECT id FROM files LIMIT 1").fetchone()[0]

        conn.execute(
            "INSERT INTO screens (file_id, figma_node_id, name, width, height, screen_type) "
            "VALUES (?, '1:1', 'Test Screen', 428, 926, 'app_screen')",
            (file_id,),
        )
        screen_id = conn.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]

        # Add nodes at depth 0 (screen frame)
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, width, height) "
            "VALUES (?, '1:1', 'Test Screen', 'FRAME', 0, 428, 926)",
            (screen_id,),
        )

        # Add classified instances
        for i, (ctype, comp_key) in enumerate([
            ("header", "key_header"),
            ("card", None),
            ("button", "key_btn1"),
            ("button", "key_btn2"),
            ("text", None),
            ("text", None),
            ("icon", "key_icon1"),
        ]):
            node_id_val = f"node_{i}"
            conn.execute(
                "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, depth, width, height, component_key) "
                "VALUES (?, ?, ?, 'INSTANCE', 1, 100, 50, ?)",
                (screen_id, node_id_val, f"{ctype}-{i}", comp_key),
            )
            nid = conn.execute("SELECT id FROM nodes WHERE figma_node_id = ?", (node_id_val,)).fetchone()[0]
            conn.execute(
                "INSERT INTO screen_component_instances (screen_id, node_id, canonical_type, classification_source) VALUES (?, ?, ?, 'heuristic')",
                (screen_id, nid, ctype),
            )

        conn.commit()
        yield conn
        conn.close()

    def test_returns_structured_report(self, db):
        spec = compose_screen([
            {"type": "header"},
            {"type": "card", "children": [
                {"type": "button"},
                {"type": "text"},
            ]},
        ])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert "generated" in report
        assert "reference" in report
        assert "diff" in report

    def test_reports_element_counts(self, db):
        spec = compose_screen([
            {"type": "header"},
            {"type": "card"},
        ])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert report["generated"]["element_count"] > 0
        assert report["reference"]["element_count"] == 7

    def test_reports_type_distribution(self, db):
        spec = compose_screen([
            {"type": "header"},
            {"type": "card"},
            {"type": "button"},
        ])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert "button" in report["reference"]["type_distribution"]
        assert report["reference"]["type_distribution"]["button"] == 2

    def test_reports_mode_ratio(self, db):
        spec = compose_screen([{"type": "button"}])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert "mode1_count" in report["reference"]
        assert "mode2_count" in report["reference"]
        assert report["reference"]["mode1_count"] == 4  # header + 2 buttons + icon have keys
        assert report["reference"]["mode2_count"] == 3  # card + 2 text

    def test_diff_shows_missing_and_extra_types(self, db):
        spec = compose_screen([
            {"type": "header"},
            {"type": "card"},
            {"type": "slider"},  # not in reference
        ])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert "button" in report["diff"]["missing_types"]
        assert "slider" in report["diff"]["extra_types"]

    def test_empty_spec_reports_all_missing(self, db):
        spec = compose_screen([])
        screen_id = db.execute("SELECT id FROM screens LIMIT 1").fetchone()[0]
        report = compare_generated_vs_ground_truth(db, spec, screen_id)

        assert report["generated"]["element_count"] == 1  # just screen root
        assert len(report["diff"]["missing_types"]) > 0
