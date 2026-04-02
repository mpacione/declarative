"""Tests for IR generation (T5 Phase 2)."""

import json
import sqlite3

import pytest

from dd.db import init_db
from dd.ir import (
    map_node_to_element, query_screen_for_ir, build_composition_spec, generate_ir,
    normalize_fills, normalize_strokes, normalize_effects, normalize_corner_radius,
)
from dd.catalog import seed_catalog


# ---------------------------------------------------------------------------
# Normalization function tests
# ---------------------------------------------------------------------------

SOLID_FILL_JSON = json.dumps([{
    "type": "SOLID", "color": {"r": 0.0353, "g": 0.0353, "b": 0.0431, "a": 1.0},
    "opacity": 1.0, "blendMode": "NORMAL",
}])

GRADIENT_FILL_JSON = json.dumps([{
    "type": "GRADIENT_LINEAR", "opacity": 1.0, "blendMode": "NORMAL",
    "gradientHandlePositions": [{"x": 0, "y": 0.5}, {"x": 1, "y": 0.5}, {"x": 0, "y": 0}],
    "gradientStops": [
        {"color": {"r": 0.643, "g": 0.957, "b": 0.255, "a": 1.0}, "position": 0.0},
        {"color": {"r": 0.145, "g": 0.827, "b": 0.4, "a": 1.0}, "position": 1.0},
    ],
}])

INVISIBLE_FILL_JSON = json.dumps([{
    "type": "SOLID", "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0},
    "visible": False, "blendMode": "NORMAL",
}])

STROKE_JSON = json.dumps([{
    "type": "SOLID", "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0},
    "blendMode": "NORMAL",
}])

SHADOW_JSON = json.dumps([{
    "type": "DROP_SHADOW", "visible": True,
    "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.25},
    "offset": {"x": 0.0, "y": 4.0}, "radius": 8.0, "spread": 0.0,
    "blendMode": "NORMAL",
}])


class TestNormalizeFills:
    def test_solid_fill(self):
        fills = normalize_fills(SOLID_FILL_JSON, [])
        assert len(fills) == 1
        assert fills[0]["type"] == "solid"
        assert fills[0]["color"].startswith("#")

    def test_gradient_fill(self):
        fills = normalize_fills(GRADIENT_FILL_JSON, [])
        assert len(fills) == 1
        assert fills[0]["type"] == "gradient-linear"
        assert len(fills[0]["stops"]) == 2
        assert "handlePositions" in fills[0]

    def test_invisible_fill_skipped(self):
        fills = normalize_fills(INVISIBLE_FILL_JSON, [])
        assert len(fills) == 0

    def test_token_bound_fill(self):
        bindings = [{"property": "fill.0.color", "token_name": "color.surface.ink", "resolved_value": "#09090B"}]
        fills = normalize_fills(SOLID_FILL_JSON, bindings)
        assert fills[0]["color"] == "{color.surface.ink}"

    def test_empty_input(self):
        assert normalize_fills(None, []) == []
        assert normalize_fills("[]", []) == []

    def test_paint_opacity(self):
        fills_json = json.dumps([{
            "type": "SOLID", "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0},
            "opacity": 0.5, "blendMode": "NORMAL",
        }])
        fills = normalize_fills(fills_json, [])
        assert fills[0]["opacity"] == 0.5


class TestNormalizeStrokes:
    def test_solid_stroke(self):
        strokes = normalize_strokes(STROKE_JSON, [], {"stroke_weight": 2})
        assert len(strokes) == 1
        assert strokes[0]["type"] == "solid"
        assert strokes[0]["color"].startswith("#")
        assert strokes[0]["width"] == 2

    def test_empty_input(self):
        assert normalize_strokes(None, [], {}) == []

    def test_token_bound_stroke(self):
        bindings = [{"property": "stroke.0.color", "token_name": "color.border", "resolved_value": "#000"}]
        strokes = normalize_strokes(STROKE_JSON, bindings, {"stroke_weight": 1})
        assert strokes[0]["color"] == "{color.border}"


class TestNormalizeEffects:
    def test_drop_shadow(self):
        effects = normalize_effects(SHADOW_JSON, [])
        assert len(effects) == 1
        assert effects[0]["type"] == "drop-shadow"
        assert effects[0]["blur"] == 8.0
        assert effects[0]["offset"]["y"] == 4.0
        assert effects[0]["color"].startswith("#")

    def test_empty_input(self):
        assert normalize_effects(None, []) == []


class TestNormalizeCornerRadius:
    def test_uniform_number(self):
        assert normalize_corner_radius(8.0) == 8.0

    def test_zero_returns_none(self):
        assert normalize_corner_radius(0) is None

    def test_none_returns_none(self):
        assert normalize_corner_radius(None) is None

    def test_json_string_number(self):
        assert normalize_corner_radius("8") == 8.0


# ---------------------------------------------------------------------------
# Element mapping tests
# ---------------------------------------------------------------------------

class TestMapNodeToElement:
    """Verify map_node_to_element() converts a node dict to an IR element."""

    def test_maps_type_from_canonical(self):
        node = _make_node(canonical_type="button")
        element = map_node_to_element(node)
        assert element["type"] == "button"

    def test_maps_horizontal_layout(self):
        node = _make_node(layout_mode="HORIZONTAL", item_spacing=16)
        element = map_node_to_element(node)
        assert element["layout"]["direction"] == "horizontal"
        assert element["layout"]["gap"] == 16

    def test_maps_vertical_layout(self):
        node = _make_node(layout_mode="VERTICAL")
        element = map_node_to_element(node)
        assert element["layout"]["direction"] == "vertical"

    def test_maps_null_layout_to_stacked(self):
        node = _make_node(layout_mode=None)
        element = map_node_to_element(node)
        assert element["layout"]["direction"] == "stacked"

    def test_maps_padding(self):
        node = _make_node(
            padding_top=16, padding_right=24, padding_bottom=16, padding_left=24
        )
        element = map_node_to_element(node)
        assert element["layout"]["padding"] == {
            "top": 16, "right": 24, "bottom": 16, "left": 24,
        }

    def test_token_bound_padding_in_layout_not_style(self):
        node = _make_node(
            padding_top=16, padding_right=24, padding_bottom=16, padding_left=24,
            bindings=[
                {"property": "padding.top", "token_name": "space.s16", "resolved_value": "16"},
                {"property": "padding.right", "token_name": "space.s24", "resolved_value": "24"},
                {"property": "padding.bottom", "token_name": "space.s16", "resolved_value": "16"},
                {"property": "padding.left", "token_name": "space.s24", "resolved_value": "24"},
            ],
        )
        element = map_node_to_element(node)
        # Token refs should appear in layout.padding
        assert element["layout"]["padding"]["top"] == "{space.s16}"
        assert element["layout"]["padding"]["right"] == "{space.s24}"
        # And NOT duplicated in style
        assert "paddingTop" not in element.get("style", {})
        assert "paddingRight" not in element.get("style", {})

    def test_token_bound_gap_in_layout_not_style(self):
        node = _make_node(
            item_spacing=16,
            bindings=[
                {"property": "itemSpacing", "token_name": "space.s16", "resolved_value": "16"},
            ],
        )
        element = map_node_to_element(node)
        assert element["layout"]["gap"] == "{space.s16}"
        assert "gap" not in element.get("style", {})

    def test_omits_zero_padding(self):
        node = _make_node(
            padding_top=0, padding_right=0, padding_bottom=0, padding_left=0
        )
        element = map_node_to_element(node)
        assert "padding" not in element.get("layout", {})

    def test_fixed_sizing_uses_pixel_values(self):
        node = _make_node(layout_sizing_h="FIXED", layout_sizing_v="FIXED")
        element = map_node_to_element(node)
        sizing = element["layout"]["sizing"]
        assert isinstance(sizing["width"], (int, float))
        assert isinstance(sizing["height"], (int, float))
        assert sizing["width"] == 428  # from _make_node default
        assert sizing["height"] == 48

    def test_null_sizing_uses_pixel_values(self):
        node = _make_node(layout_mode=None, layout_sizing_h=None, layout_sizing_v=None)
        element = map_node_to_element(node)
        sizing = element["layout"]["sizing"]
        assert isinstance(sizing["width"], (int, float))
        assert isinstance(sizing["height"], (int, float))

    def test_mixed_sizing_fill_and_fixed(self):
        node = _make_node(layout_sizing_h="FILL", layout_sizing_v="FIXED")
        element = map_node_to_element(node)
        sizing = element["layout"]["sizing"]
        assert sizing["width"] == "fill"
        assert isinstance(sizing["height"], (int, float))
        assert sizing["height"] == 48

    def test_maps_sizing(self):
        node = _make_node(layout_sizing_h="FILL", layout_sizing_v="HUG")
        element = map_node_to_element(node)
        assert element["layout"]["sizing"]["width"] == "fill"
        assert element["layout"]["sizing"]["height"] == "hug"

    def test_maps_token_binding_to_visual_fill(self):
        fills_json = json.dumps([{
            "type": "SOLID", "color": {"r": 0.98, "g": 0.98, "b": 0.98, "a": 1.0},
        }])
        node = _make_node(
            fills=fills_json,
            bindings=[
                {"property": "fill.0.color", "token_name": "color.surface.primary", "resolved_value": "#FAFAFA"},
            ],
        )
        element = map_node_to_element(node)
        assert element["visual"]["fills"][0]["color"] == "{color.surface.primary}"

    def test_maps_hardcoded_fill_from_raw_json(self):
        fills_json = json.dumps([{
            "type": "SOLID", "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0},
        }])
        node = _make_node(fills=fills_json)
        element = map_node_to_element(node)
        assert element["visual"]["fills"][0]["color"] == "#FF0000"

    def test_maps_font_size_token(self):
        node = _make_node(bindings=[
            {"property": "fontSize", "token_name": "type.body.md.fontSize", "resolved_value": "16"},
        ])
        element = map_node_to_element(node)
        assert element["style"]["fontSize"] == "{type.body.md.fontSize}"

    def test_maps_text_content_to_props(self):
        node = _make_node(canonical_type="text", text_content="Hello world")
        element = map_node_to_element(node)
        assert element["props"]["text"] == "Hello world"

    def test_maps_heading_text_to_props(self):
        node = _make_node(canonical_type="heading", text_content="Settings")
        element = map_node_to_element(node)
        assert element["props"]["text"] == "Settings"

    def test_maps_corner_radius_to_visual(self):
        node = _make_node(corner_radius="8")
        element = map_node_to_element(node)
        assert element["visual"]["cornerRadius"] == 8.0

    def test_maps_opacity_to_visual(self):
        node = _make_node(opacity=0.5)
        element = map_node_to_element(node)
        assert element["visual"]["opacity"] == 0.5

    def test_omits_full_opacity_from_visual(self):
        node = _make_node(opacity=1.0)
        element = map_node_to_element(node)
        visual = element.get("visual", {})
        assert "opacity" not in visual

    def test_omits_empty_sections(self):
        node = _make_node(canonical_type="icon")
        element = map_node_to_element(node)
        assert "props" not in element or element["props"] == {}
        assert "children" not in element

    # --- Visual model tests (Step 2: _build_style → _build_visual) ---

    def test_solid_fill_in_visual_section(self):
        fills_json = json.dumps([{
            "type": "SOLID", "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0},
            "opacity": 1.0,
        }])
        node = _make_node(fills=fills_json)
        element = map_node_to_element(node)
        assert "visual" in element
        assert len(element["visual"]["fills"]) == 1
        assert element["visual"]["fills"][0]["type"] == "solid"
        assert element["visual"]["fills"][0]["color"] == "#FF0000"

    def test_token_bound_fill_in_visual_section(self):
        fills_json = json.dumps([{
            "type": "SOLID", "color": {"r": 0.98, "g": 0.98, "b": 0.98, "a": 1.0},
        }])
        node = _make_node(
            fills=fills_json,
            bindings=[
                {"property": "fill.0.color", "token_name": "color.surface.primary", "resolved_value": "#FAFAFA"},
            ],
        )
        element = map_node_to_element(node)
        assert element["visual"]["fills"][0]["color"] == "{color.surface.primary}"

    def test_gradient_fill_in_visual_section(self):
        fills_json = json.dumps([{
            "type": "GRADIENT_LINEAR", "opacity": 1.0,
            "gradientHandlePositions": [{"x": 0, "y": 0.5}, {"x": 1, "y": 0.5}],
            "gradientStops": [
                {"color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}, "position": 0.0},
                {"color": {"r": 0.0, "g": 0.0, "b": 1.0, "a": 1.0}, "position": 1.0},
            ],
        }])
        node = _make_node(fills=fills_json)
        element = map_node_to_element(node)
        assert element["visual"]["fills"][0]["type"] == "gradient-linear"
        assert len(element["visual"]["fills"][0]["stops"]) == 2

    def test_strokes_in_visual_section(self):
        strokes_json = json.dumps([{
            "type": "SOLID", "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0},
        }])
        node = _make_node(strokes=strokes_json)
        element = map_node_to_element(node)
        assert "visual" in element
        assert len(element["visual"]["strokes"]) == 1
        assert element["visual"]["strokes"][0]["type"] == "solid"
        assert element["visual"]["strokes"][0]["color"] == "#000000"

    def test_effects_in_visual_section(self):
        effects_json = json.dumps([{
            "type": "DROP_SHADOW", "visible": True,
            "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.25},
            "offset": {"x": 0.0, "y": 4.0}, "radius": 8.0, "spread": 0.0,
        }])
        node = _make_node(effects=effects_json)
        element = map_node_to_element(node)
        assert "visual" in element
        assert len(element["visual"]["effects"]) == 1
        assert element["visual"]["effects"][0]["type"] == "drop-shadow"
        assert element["visual"]["effects"][0]["blur"] == 8.0

    def test_corner_radius_in_visual_section(self):
        node = _make_node(corner_radius="12")
        element = map_node_to_element(node)
        assert element["visual"]["cornerRadius"] == 12.0

    def test_opacity_in_visual_section(self):
        node = _make_node(opacity=0.5)
        element = map_node_to_element(node)
        assert element["visual"]["opacity"] == 0.5

    def test_full_opacity_omitted_from_visual(self):
        node = _make_node(opacity=1.0)
        element = map_node_to_element(node)
        visual = element.get("visual", {})
        assert "opacity" not in visual

    def test_no_visual_section_when_empty(self):
        node = _make_node(fills=None, strokes=None, effects=None, corner_radius=None, opacity=1.0)
        element = map_node_to_element(node)
        assert "visual" not in element or element["visual"] == {}

    def test_typography_stays_in_style(self):
        node = _make_node(bindings=[
            {"property": "fontSize", "token_name": "type.body.md.fontSize", "resolved_value": "16"},
            {"property": "fontFamily", "token_name": "type.body.md.fontFamily", "resolved_value": "Inter"},
        ])
        element = map_node_to_element(node)
        assert element["style"]["fontSize"] == "{type.body.md.fontSize}"
        assert element["style"]["fontFamily"] == "{type.body.md.fontFamily}"
        visual = element.get("visual", {})
        assert "fontSize" not in visual
        assert "fontFamily" not in visual


# ---------------------------------------------------------------------------
# Steps 2+3: Query layer + composition assembly tests
# ---------------------------------------------------------------------------

def _seed_ir_screen(db: sqlite3.Connection) -> None:
    """Insert classified screen data for IR generation tests."""
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'Settings', 428, 926)"
    )
    db.execute("INSERT INTO token_collections (id, file_id, name) VALUES (1, 1, 'Colors')")
    db.execute("INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (1, 1, 'Default', 1)")
    db.execute("INSERT INTO tokens (id, collection_id, name, type) VALUES (1, 1, 'color.surface.primary', 'color')")
    db.execute("INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (1, 1, '#FAFAFA', '#FAFAFA')")
    db.execute("INSERT INTO tokens (id, collection_id, name, type) VALUES (2, 1, 'color.text.primary', 'color')")
    db.execute("INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (2, 1, '#000000', '#000000')")

    nodes = [
        # header at depth 1
        (10, 1, "h1", "nav/top-nav", "INSTANCE", 1, 0, 0, 0, 428, 56, "HORIZONTAL", None, None, None, None, None, None),
        # icon inside header at depth 2
        (11, 1, "ib1", "icon/back", "INSTANCE", 2, 0, 8, 8, 24, 24, None, None, None, None, None, None, 10),
        # text heading at depth 2
        (12, 1, "t1", "Section Title", "TEXT", 2, 1, 16, 80, 396, 28, None, "Inter", 700, 24, None, "Settings", 10),
        # content frame at depth 1
        (13, 1, "c1", "Content", "FRAME", 1, 1, 0, 56, 428, 802, "VERTICAL", None, None, None, 16, None, None),
    ]
    db.executemany(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
        "x, y, width, height, layout_mode, font_family, font_weight, font_size, item_spacing, text_content, parent_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )

    # Classify: header and icon formally, heading by heuristic
    sci_rows = [
        (1, 10, "header", 1.0, "formal", None),
        (1, 11, "icon", 1.0, "formal", None),
        (1, 12, "heading", 0.9, "heuristic", None),
    ]
    db.executemany(
        "INSERT INTO screen_component_instances "
        "(screen_id, node_id, canonical_type, confidence, classification_source, parent_instance_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        sci_rows,
    )
    # Set parent linkage: icon → header
    header_sci_id = db.execute("SELECT id FROM screen_component_instances WHERE node_id = 10").fetchone()[0]
    db.execute(
        "UPDATE screen_component_instances SET parent_instance_id = ? WHERE node_id = 11",
        (header_sci_id,),
    )
    # heading → header
    db.execute(
        "UPDATE screen_component_instances SET parent_instance_id = ? WHERE node_id = 12",
        (header_sci_id,),
    )

    # Token bindings: header background
    db.execute(
        "INSERT INTO node_token_bindings (id, node_id, property, token_id, raw_value, resolved_value, binding_status) "
        "VALUES (1, 10, 'fill.0.color', 1, '#FAFAFA', '#FAFAFA', 'bound')"
    )
    # Text color on heading
    db.execute(
        "INSERT INTO node_token_bindings (id, node_id, property, token_id, raw_value, resolved_value, binding_status) "
        "VALUES (2, 12, 'fill.0.color', 2, '#000000', '#000000', 'bound')"
    )

    db.commit()


class TestQueryScreenForIR:
    """Verify query_screen_for_ir() fetches and groups classified node data."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_ir_screen(conn)
        yield conn
        conn.close()

    def test_returns_grouped_nodes(self, db: sqlite3.Connection):
        result = query_screen_for_ir(db, screen_id=1)
        assert isinstance(result, dict)
        assert "nodes" in result
        assert len(result["nodes"]) >= 3  # header, icon, heading

    def test_nodes_have_bindings(self, db: sqlite3.Connection):
        result = query_screen_for_ir(db, screen_id=1)
        header_node = next(n for n in result["nodes"] if n["node_id"] == 10)
        assert len(header_node["bindings"]) >= 1
        assert header_node["bindings"][0]["token_name"] == "color.surface.primary"

    def test_includes_screen_metadata(self, db: sqlite3.Connection):
        result = query_screen_for_ir(db, screen_id=1)
        assert result["screen_name"] == "Settings"
        assert result["width"] == 428
        assert result["height"] == 926


class TestBuildCompositionSpec:
    """Verify build_composition_spec() assembles a complete IR."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_ir_screen(conn)
        yield conn
        conn.close()

    def test_has_required_top_level_fields(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        assert "version" in spec
        assert "root" in spec
        assert "elements" in spec
        assert "tokens" in spec

    def test_root_element_exists(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        root_id = spec["root"]
        assert root_id in spec["elements"]

    def test_root_has_children(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        root = spec["elements"][spec["root"]]
        assert "children" in root
        assert len(root["children"]) > 0

    def test_header_element_has_children(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        # Find the header element
        header = next(
            (el for el in spec["elements"].values() if el["type"] == "header"),
            None,
        )
        assert header is not None
        assert "children" in header
        assert len(header["children"]) >= 1  # icon child

    def test_tokens_populated(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        assert "color.surface.primary" in spec["tokens"]
        assert spec["tokens"]["color.surface.primary"] == "#FAFAFA"

    def test_element_ids_are_strings(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        for eid in spec["elements"]:
            assert isinstance(eid, str)

    def test_serializable_to_json(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        json_str = json.dumps(spec, indent=2)
        assert len(json_str) > 100
        parsed = json.loads(json_str)
        assert parsed["version"] == spec["version"]


# ---------------------------------------------------------------------------
# Step 4: generate_ir wrapper + CLI
# ---------------------------------------------------------------------------

class TestContainerInjection:
    """Verify unclassified parent FRAMEs become container elements."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, 's1', 'Home', 428, 926)"
        )
        # Unclassified FRAME "Content Area" at depth 1 with two classified children
        nodes = [
            (10, 1, "f1", "Content Area", "FRAME", 1, 0, 0, 56, 428, 802, "VERTICAL", 16, None),
            (11, 1, "b1", "button/primary", "INSTANCE", 2, 0, 16, 100, 200, 48, None, None, 10),
            (12, 1, "b2", "button/secondary", "INSTANCE", 2, 1, 16, 160, 200, 48, None, None, 10),
        ]
        conn.executemany(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
            "x, y, width, height, layout_mode, item_spacing, parent_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            nodes,
        )
        # Only classify the buttons, NOT the parent frame
        conn.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, classification_source) "
            "VALUES (1, 11, 'button', 1.0, 'formal')"
        )
        conn.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, classification_source) "
            "VALUES (1, 12, 'button', 1.0, 'formal')"
        )
        conn.commit()
        yield conn
        conn.close()

    def test_injects_container_for_unclassified_parent(self, db):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)

        # The two buttons should NOT be root children
        root = spec["elements"][spec["root"]]
        # There should be a container element that holds them
        container = None
        for eid, el in spec["elements"].items():
            if el.get("type") == "container":
                container = el
                break

        assert container is not None, "Expected a container element for unclassified parent FRAME"
        assert "children" in container
        assert len(container["children"]) == 2

    def test_container_preserves_layout(self, db):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)

        container = next(
            el for el in spec["elements"].values() if el.get("type") == "container"
        )
        assert container["layout"]["direction"] == "vertical"
        assert container["layout"]["gap"] == 16

    def test_reduces_root_children(self, db):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)

        root = spec["elements"][spec["root"]]
        # Should have 1 container, not 2 loose buttons
        assert len(root["children"]) == 1


class TestGenerateIR:
    """Verify generate_ir() end-to-end wrapper."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_ir_screen(conn)
        yield conn
        conn.close()

    def test_returns_spec_and_json(self, db: sqlite3.Connection):
        result = generate_ir(db, screen_id=1)
        assert "spec" in result
        assert "json" in result
        assert isinstance(result["json"], str)
        assert result["spec"]["version"] == "1.0"

    def test_element_count(self, db: sqlite3.Connection):
        result = generate_ir(db, screen_id=1)
        # screen-1 + header + icon + heading = 4 elements
        assert len(result["spec"]["elements"]) >= 4


class TestGenerateIRCLI:
    """Verify generate-ir CLI command."""

    def test_generate_ir_command(self, tmp_path):
        db_path = str(tmp_path / "test.declarative.db")
        conn = init_db(db_path)
        _seed_ir_screen(conn)
        conn.close()

        from dd.cli import main
        main(["generate-ir", "--db", db_path, "--screen", "1"])


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def _make_node(
    canonical_type: str = "button",
    layout_mode: str | None = "VERTICAL",
    item_spacing: float | None = None,
    padding_top: float | None = None,
    padding_right: float | None = None,
    padding_bottom: float | None = None,
    padding_left: float | None = None,
    layout_sizing_h: str | None = None,
    layout_sizing_v: str | None = None,
    primary_align: str | None = None,
    counter_align: str | None = None,
    text_content: str | None = None,
    corner_radius: str | None = None,
    opacity: float | None = 1.0,
    fills: str | None = None,
    strokes: str | None = None,
    effects: str | None = None,
    bindings: list | None = None,
) -> dict:
    return {
        "node_id": 1,
        "canonical_type": canonical_type,
        "name": "test_node",
        "node_type": "FRAME",
        "layout_mode": layout_mode,
        "item_spacing": item_spacing,
        "counter_axis_spacing": None,
        "padding_top": padding_top,
        "padding_right": padding_right,
        "padding_bottom": padding_bottom,
        "padding_left": padding_left,
        "layout_sizing_h": layout_sizing_h,
        "layout_sizing_v": layout_sizing_v,
        "primary_align": primary_align,
        "counter_align": counter_align,
        "text_content": text_content,
        "corner_radius": corner_radius,
        "opacity": opacity,
        "fills": fills,
        "strokes": strokes,
        "effects": effects,
        "width": 428,
        "height": 48,
        "bindings": bindings or [],
    }
