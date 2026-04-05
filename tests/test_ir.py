"""Tests for IR generation (T5 Phase 2)."""

import json
import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.db import init_db
from dd.ir import (
    build_composition_spec,
    build_semantic_tree,
    filter_system_chrome,
    generate_ir,
    map_node_to_element,
    normalize_corner_radius,
    normalize_effects,
    normalize_fills,
    normalize_strokes,
    query_screen_for_ir,
    query_screen_visuals,
    query_slot_definitions,
)

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

    def test_no_visual_section_in_thin_ir(self):
        fills_json = json.dumps([{
            "type": "SOLID", "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0},
        }])
        node = _make_node(fills=fills_json, corner_radius="8", opacity=0.5)
        element = map_node_to_element(node)
        assert "visual" not in element

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

    def test_omits_empty_sections(self):
        node = _make_node(canonical_type="icon")
        element = map_node_to_element(node)
        assert "props" not in element or element["props"] == {}
        assert "children" not in element

    def test_typography_stays_in_style(self):
        node = _make_node(bindings=[
            {"property": "fontSize", "token_name": "type.body.md.fontSize", "resolved_value": "16"},
            {"property": "fontFamily", "token_name": "type.body.md.fontFamily", "resolved_value": "Inter"},
        ])
        element = map_node_to_element(node)
        assert element["style"]["fontSize"] == "{type.body.md.fontSize}"
        assert element["style"]["fontFamily"] == "{type.body.md.fontFamily}"


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
        # screen frame at depth 0 (unclassified, layout_mode=None = absolute positioning)
        (9, 1, "s1_frame", "iPhone 13 Pro Max", "FRAME", 0, 0, -9000, 7000, 428, 926, None, None, None, None, None, None, None),
        # header at depth 1 (absolute coords: screen origin + relative → (0, 0))
        (10, 1, "h1", "nav/top-nav", "INSTANCE", 1, 0, -9000, 7000, 428, 56, "HORIZONTAL", None, None, None, None, None, 9),
        # icon inside header at depth 2
        (11, 1, "ib1", "icon/back", "INSTANCE", 2, 0, -8992, 7008, 24, 24, None, None, None, None, None, None, 10),
        # text heading at depth 2
        (12, 1, "t1", "Section Title", "TEXT", 2, 1, -8984, 7080, 396, 28, None, "Inter", 700, 24, None, "Settings", 10),
        # content frame at depth 1 (relative to parent: (0, 56))
        (13, 1, "c1", "Content", "FRAME", 1, 1, -9000, 7056, 428, 802, "VERTICAL", None, None, None, 16, None, 9),
        # background image at depth 1 (unclassified RECTANGLE)
        (14, 1, "img1", "image 319", "RECTANGLE", 1, 2, -9000, 7000, 1012, 1012, None, None, None, None, None, None, 9),
        # system chrome at depth 1 (unclassified INSTANCE)
        (15, 1, "sb1", "iOS/StatusBar", "INSTANCE", 1, 3, -9000, 7000, 428, 47, None, None, None, None, None, None, 9),
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

    def test_fetches_strokes_and_effects_columns(self, db: sqlite3.Connection):
        strokes_json = json.dumps([{"type": "SOLID", "color": {"r": 0, "g": 0, "b": 0, "a": 1}}])
        effects_json = json.dumps([{"type": "DROP_SHADOW", "visible": True, "color": {"r": 0, "g": 0, "b": 0, "a": 0.25}, "offset": {"x": 0, "y": 4}, "radius": 8, "spread": 0}])
        db.execute("UPDATE nodes SET strokes = ?, effects = ? WHERE id = 10", (strokes_json, effects_json))
        db.commit()
        result = query_screen_for_ir(db, screen_id=1)
        header_node = next(n for n in result["nodes"] if n["node_id"] == 10)
        assert header_node["strokes"] == strokes_json
        assert header_node["effects"] == effects_json

    def test_includes_all_nodes_with_left_join(self, db: sqlite3.Connection):
        """All 7 fixture nodes should be returned — classified and unclassified."""
        result = query_screen_for_ir(db, screen_id=1)
        assert len(result["nodes"]) == 7

    def test_unclassified_node_has_null_canonical_type(self, db: sqlite3.Connection):
        """Unclassified RECTANGLE (node 14) has canonical_type=None."""
        result = query_screen_for_ir(db, screen_id=1)
        rect_node = next(n for n in result["nodes"] if n["node_id"] == 14)
        assert rect_node["canonical_type"] is None
        assert rect_node["sci_id"] is None

    def test_unclassified_node_preserves_real_node_type(self, db: sqlite3.Connection):
        """Unclassified nodes carry their real node_type from L0."""
        result = query_screen_for_ir(db, screen_id=1)
        rect_node = next(n for n in result["nodes"] if n["node_id"] == 14)
        assert rect_node["node_type"] == "RECTANGLE"

        frame_node = next(n for n in result["nodes"] if n["node_id"] == 9)
        assert frame_node["node_type"] == "FRAME"

    def test_includes_component_key_column(self, db: sqlite3.Connection):
        """component_key is available for Mode 1 detection in the renderer."""
        db.execute("UPDATE nodes SET component_key = 'test_key_abc' WHERE id = 10")
        db.commit()
        result = query_screen_for_ir(db, screen_id=1)
        header_node = next(n for n in result["nodes"] if n["node_id"] == 10)
        assert header_node["component_key"] == "test_key_abc"


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

    def test_no_visual_section_in_thin_ir(self, db: sqlite3.Connection):
        fills_json = json.dumps([{"type": "SOLID", "color": {"r": 0.98, "g": 0.98, "b": 0.98, "a": 1.0}}])
        db.execute("UPDATE nodes SET fills = ? WHERE id = 10", (fills_json,))
        db.commit()
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        header = next(el for el in spec["elements"].values() if el["type"] == "header")
        assert "visual" not in header

    def test_serializable_to_json(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        json_str = json.dumps(spec, indent=2)
        assert len(json_str) > 100
        parsed = json.loads(json_str)
        assert parsed["version"] == spec["version"]

    def test_node_id_map_present(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        assert "_node_id_map" in spec

    def test_node_id_map_maps_element_ids_to_node_ids(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]

        # Every element (except the synthetic screen root) should have a node_id entry
        for eid in spec["elements"]:
            if eid == spec["root"]:
                continue
            assert eid in node_id_map, f"Element {eid} missing from _node_id_map"
            assert isinstance(node_id_map[eid], int), f"Node ID for {eid} should be int"

    def test_node_id_map_values_are_real_node_ids(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]

        # Node IDs from the seed data: 10 (header), 11 (icon), 12 (heading)
        node_ids_in_map = set(node_id_map.values())
        assert 10 in node_ids_in_map  # header node
        assert 11 in node_ids_in_map  # icon node
        assert 12 in node_ids_in_map  # heading node

    def test_screen_root_direction_is_absolute(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        root = spec["elements"][spec["root"]]
        assert root["layout"]["direction"] == "absolute"

    def test_root_children_have_position(self, db: sqlite3.Connection):
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        root = spec["elements"][spec["root"]]
        for child_id in root["children"]:
            child = spec["elements"][child_id]
            assert "position" in child["layout"], f"{child_id} missing position"
            assert "x" in child["layout"]["position"]
            assert "y" in child["layout"]["position"]

    def test_root_children_position_from_db(self, db: sqlite3.Connection):
        """Position values come from real node x/y coordinates."""
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        # Header is at x=0, y=0 in seed data (node 10)
        header = next(el for el in spec["elements"].values() if el["type"] == "header")
        assert header["layout"]["position"]["x"] == 0
        assert header["layout"]["position"]["y"] == 0

    def test_ir_includes_unclassified_depth1_rectangle(self, db: sqlite3.Connection):
        """Unclassified RECTANGLE at depth 1 should be in the IR."""
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_ids = set(spec["_node_id_map"].values())
        assert 14 in node_ids  # image 319 RECTANGLE

    def test_unclassified_element_uses_node_type_as_type(self, db: sqlite3.Connection):
        """Unclassified RECTANGLE gets type='rectangle' (from node_type.lower())."""
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]
        rect_eid = next(eid for eid, nid in node_id_map.items() if nid == 14)
        assert spec["elements"][rect_eid]["type"] == "rectangle"

    def test_unclassified_element_id_uses_node_type(self, db: sqlite3.Connection):
        """Unclassified RECTANGLE gets element ID like 'rectangle-1'."""
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]
        rect_eid = next(eid for eid, nid in node_id_map.items() if nid == 14)
        assert rect_eid.startswith("rectangle-")

    def test_classified_element_still_uses_canonical_type(self, db: sqlite3.Connection):
        """Classified nodes still use canonical_type, not node_type."""
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        header = next(el for el in spec["elements"].values() if el.get("type") == "header")
        assert header is not None

    def test_original_name_preserved_in_element(self, db: sqlite3.Connection):
        """Elements carry _original_name from the DB node name."""
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]
        rect_eid = next(eid for eid, nid in node_id_map.items() if nid == 14)
        assert spec["elements"][rect_eid].get("_original_name") == "image 319"

    def test_ir_includes_system_chrome_instances(self, db: sqlite3.Connection):
        """System chrome nodes ARE in the IR (needed for round-trip).

        The semantic path (generate_ir(semantic=True)) filters them post-build
        via filter_system_chrome(). The structural IR includes everything.
        """
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_ids = set(spec["_node_id_map"].values())
        assert 15 in node_ids  # iOS/StatusBar — included for round-trip

    def test_children_of_non_autolayout_parent_have_position(self, db: sqlite3.Connection):
        """Children of parents with no layout_mode get absolute position.

        Node 9 (depth 0) has layout_mode=None. Its children (10, 13, 14)
        should have position set relative to node 9's origin.
        Node 9 is at (-9000, 7000). Node 13 (Content) is at (-9000, 7056).
        So Content's position should be (0, 56).
        """
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]

        # Content frame (node 13) should have position relative to parent (node 9)
        content_eid = next(eid for eid, nid in node_id_map.items() if nid == 13)
        content_el = spec["elements"][content_eid]
        assert "position" in content_el.get("layout", {}), "Content should have absolute position"
        assert content_el["layout"]["position"]["x"] == 0
        assert content_el["layout"]["position"]["y"] == 56

    def test_children_of_autolayout_parent_have_no_position(self, db: sqlite3.Connection):
        """Children inside auto-layout parents should NOT get position.

        Node 10 (header, HORIZONTAL layout) has children 11 and 12.
        These should NOT have position — auto-layout determines their placement.
        """
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]

        # icon (node 11) is child of header (node 10, HORIZONTAL layout)
        icon_eid = next(eid for eid, nid in node_id_map.items() if nid == 11)
        icon_el = spec["elements"][icon_eid]
        assert "position" not in icon_el.get("layout", {}), "Auto-layout child should not have position"

    def test_hidden_node_has_visible_false(self, db: sqlite3.Connection):
        """Nodes with visible=0 in DB should carry visible=false in element."""
        # Make node 14 hidden
        db.execute("UPDATE nodes SET visible = 0 WHERE id = 14")
        db.commit()
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]

        rect_eid = next(eid for eid, nid in node_id_map.items() if nid == 14)
        rect_el = spec["elements"][rect_eid]
        assert rect_el.get("visible") is False

    def test_visible_node_has_no_visible_key(self, db: sqlite3.Connection):
        """Nodes with visible=1 should NOT have a visible key (default)."""
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)
        node_id_map = spec["_node_id_map"]

        header_eid = next(eid for eid, nid in node_id_map.items() if nid == 10)
        header_el = spec["elements"][header_eid]
        assert "visible" not in header_el


# ---------------------------------------------------------------------------
# Step 4: generate_ir wrapper + CLI
# ---------------------------------------------------------------------------

class TestUnclassifiedParentWiring:
    """Verify unclassified parent FRAMEs wire children correctly via parent_id."""

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

    def test_unclassified_parent_has_classified_children(self, db):
        """Unclassified FRAME wires classified button children via parent_id."""
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)

        # Find the element for unclassified FRAME (node 10)
        node_id_map = spec["_node_id_map"]
        frame_eid = next(eid for eid, nid in node_id_map.items() if nid == 10)
        frame_el = spec["elements"][frame_eid]

        assert "children" in frame_el
        assert len(frame_el["children"]) == 2

    def test_unclassified_parent_preserves_layout(self, db):
        """Unclassified FRAME's layout properties come from L0."""
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)

        node_id_map = spec["_node_id_map"]
        frame_eid = next(eid for eid, nid in node_id_map.items() if nid == 10)
        frame_el = spec["elements"][frame_eid]

        assert frame_el["layout"]["direction"] == "vertical"
        assert frame_el["layout"]["gap"] == 16

    def test_reduces_root_children(self, db):
        """Buttons are children of the FRAME, not root children."""
        data = query_screen_for_ir(db, screen_id=1)
        spec = build_composition_spec(data)

        root = spec["elements"][spec["root"]]
        # Should have 1 element (the unclassified FRAME), not 2 loose buttons
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
# Semantic tree tests (Phase 3b)
# ---------------------------------------------------------------------------

def _seed_slots(db: sqlite3.Connection) -> None:
    """Insert component + slot data for semantic tree tests."""
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO components (id, file_id, name, figma_node_id) "
        "VALUES (1, 1, 'nav/top-nav', '1835:155037')"
    )
    db.executemany(
        "INSERT INTO component_slots (id, component_id, name, slot_type, is_required, sort_order) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, 1, "left", "any", 0, 0),
            (2, 1, "center", "any", 0, 1),
            (3, 1, "right", "any", 0, 2),
        ],
    )
    db.commit()


class TestQuerySlotDefinitions:
    """Verify query_slot_definitions() returns slot defs keyed by component name."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        _seed_slots(conn)
        yield conn
        conn.close()

    def test_returns_dict_keyed_by_component_name(self, db):
        slot_defs = query_slot_definitions(db)
        assert isinstance(slot_defs, dict)
        assert "nav/top-nav" in slot_defs

    def test_slot_defs_have_correct_shape(self, db):
        slot_defs = query_slot_definitions(db)
        nav_slots = slot_defs["nav/top-nav"]
        assert len(nav_slots) == 3
        slot_names = [s["name"] for s in nav_slots]
        assert slot_names == ["left", "center", "right"]

    def test_slot_defs_include_type_and_order(self, db):
        slot_defs = query_slot_definitions(db)
        left_slot = slot_defs["nav/top-nav"][0]
        assert left_slot["name"] == "left"
        assert left_slot["slot_type"] == "any"
        assert left_slot["sort_order"] == 0

    def test_empty_db_returns_empty_dict(self):
        conn = init_db(":memory:")
        seed_catalog(conn)
        slot_defs = query_slot_definitions(conn)
        assert slot_defs == {}
        conn.close()


class TestFilterSystemChrome:
    """Verify filter_system_chrome removes chrome elements from spec."""

    def test_removes_ios_status_bar(self):
        spec = {
            "elements": {
                "screen-1": {"type": "screen", "children": ["header-1", "container-1"]},
                "header-1": {"type": "header"},
                "container-1": {"type": "container"},
            },
            "_node_id_map": {"header-1": 10, "container-1": 20},
        }
        node_names = {10: "nav/top-nav", 20: "iOS/StatusBar"}
        filtered = filter_system_chrome(spec, node_names)
        assert "container-1" not in filtered["elements"]
        assert "container-1" not in filtered["elements"]["screen-1"]["children"]

    def test_removes_home_indicator(self):
        spec = {
            "elements": {
                "screen-1": {"type": "screen", "children": ["header-1", "icon-1"]},
                "header-1": {"type": "header"},
                "icon-1": {"type": "icon"},
            },
            "_node_id_map": {"header-1": 10, "icon-1": 20},
        }
        node_names = {10: "nav/top-nav", 20: "iOS/HomeIndicator"}
        filtered = filter_system_chrome(spec, node_names)
        assert "icon-1" not in filtered["elements"]

    def test_preserves_non_chrome_elements(self):
        spec = {
            "elements": {
                "screen-1": {"type": "screen", "children": ["header-1", "button-1"]},
                "header-1": {"type": "header"},
                "button-1": {"type": "button"},
            },
            "_node_id_map": {"header-1": 10, "button-1": 20},
        }
        node_names = {10: "nav/top-nav", 20: "button/large/solid"}
        filtered = filter_system_chrome(spec, node_names)
        assert "header-1" in filtered["elements"]
        assert "button-1" in filtered["elements"]

    def test_removes_safari_bottom(self):
        spec = {
            "elements": {
                "screen-1": {"type": "screen", "children": ["container-1"]},
                "container-1": {"type": "container"},
            },
            "_node_id_map": {"container-1": 20},
        }
        node_names = {20: "Safari - Bottom"}
        filtered = filter_system_chrome(spec, node_names)
        assert "container-1" not in filtered["elements"]

    def test_does_not_mutate_input(self):
        spec = {
            "elements": {
                "screen-1": {"type": "screen", "children": ["container-1"]},
                "container-1": {"type": "container"},
            },
            "_node_id_map": {"container-1": 20},
        }
        node_names = {20: "iOS/StatusBar"}
        filtered = filter_system_chrome(spec, node_names)
        assert "container-1" in spec["elements"]  # original unchanged


class TestBuildSemanticTree:
    """Verify build_semantic_tree collapses flat spec into semantic tree with slots."""

    def _make_flat_spec(self):
        """A flat spec with a header containing icon, heading, and tabs children."""
        return {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {
                    "type": "screen",
                    "layout": {"direction": "vertical"},
                    "children": ["header-1", "button-1"],
                },
                "header-1": {
                    "type": "header",
                    "layout": {"direction": "horizontal"},
                    "children": ["icon-1", "heading-1", "tabs-1"],
                },
                "icon-1": {"type": "icon", "props": {"icon": "back"}},
                "heading-1": {"type": "heading", "props": {"text": "Settings"}},
                "tabs-1": {"type": "tabs"},
                "button-1": {"type": "button", "props": {"text": "Save"}},
            },
            "tokens": {"color.primary": "#FF0000"},
            "_node_id_map": {
                "header-1": 10,
                "icon-1": 11,
                "heading-1": 12,
                "tabs-1": 13,
                "button-1": 20,
            },
        }

    def _make_slot_defs(self):
        return {
            "nav/top-nav": [
                {"name": "left", "slot_type": "any", "sort_order": 0},
                {"name": "center", "slot_type": "any", "sort_order": 1},
                {"name": "right", "slot_type": "any", "sort_order": 2},
            ],
        }

    def _make_node_positions(self):
        """x/y/width for slot assignment by position."""
        return {
            10: {"x": 0, "y": 0, "width": 428, "height": 64, "name": "nav/top-nav"},
            11: {"x": 8, "y": 8, "width": 24, "height": 24, "name": "icon/back"},
            12: {"x": 140, "y": 8, "width": 180, "height": 28, "name": "Settings"},
            13: {"x": 340, "y": 8, "width": 80, "height": 44, "name": "nav/tabs"},
            20: {"x": 16, "y": 200, "width": 200, "height": 48, "name": "button/save"},
        }

    def test_collapses_children_into_slots(self):
        spec = self._make_flat_spec()
        slot_defs = self._make_slot_defs()
        node_data = self._make_node_positions()

        result = build_semantic_tree(spec, slot_defs, node_data)

        header = result["elements"]["header-1"]
        assert "slots" in header
        assert "children" not in header

    def test_header_has_three_named_slots(self):
        spec = self._make_flat_spec()
        result = build_semantic_tree(spec, self._make_slot_defs(), self._make_node_positions())

        header = result["elements"]["header-1"]
        assert "left" in header["slots"]
        assert "center" in header["slots"]
        assert "right" in header["slots"]

    def test_icon_assigned_to_left_slot(self):
        spec = self._make_flat_spec()
        result = build_semantic_tree(spec, self._make_slot_defs(), self._make_node_positions())

        header = result["elements"]["header-1"]
        assert "icon-1" in header["slots"]["left"]

    def test_heading_assigned_to_center_slot(self):
        spec = self._make_flat_spec()
        result = build_semantic_tree(spec, self._make_slot_defs(), self._make_node_positions())

        header = result["elements"]["header-1"]
        assert "heading-1" in header["slots"]["center"]

    def test_tabs_assigned_to_right_slot(self):
        spec = self._make_flat_spec()
        result = build_semantic_tree(spec, self._make_slot_defs(), self._make_node_positions())

        header = result["elements"]["header-1"]
        assert "tabs-1" in header["slots"]["right"]

    def test_slot_children_remain_in_elements(self):
        spec = self._make_flat_spec()
        result = build_semantic_tree(spec, self._make_slot_defs(), self._make_node_positions())

        assert "icon-1" in result["elements"]
        assert "heading-1" in result["elements"]
        assert "tabs-1" in result["elements"]

    def test_standalone_button_keeps_children_pattern(self):
        spec = self._make_flat_spec()
        result = build_semantic_tree(spec, self._make_slot_defs(), self._make_node_positions())

        screen = result["elements"]["screen-1"]
        assert "button-1" in screen["children"]

    def test_element_without_slot_defs_keeps_children(self):
        spec = self._make_flat_spec()
        result = build_semantic_tree(spec, {}, self._make_node_positions())

        header = result["elements"]["header-1"]
        assert "children" in header
        assert "slots" not in header

    def test_does_not_mutate_input(self):
        spec = self._make_flat_spec()
        original_children = list(spec["elements"]["header-1"]["children"])
        build_semantic_tree(spec, self._make_slot_defs(), self._make_node_positions())
        assert spec["elements"]["header-1"]["children"] == original_children

    def test_preserves_node_id_map(self):
        spec = self._make_flat_spec()
        result = build_semantic_tree(spec, self._make_slot_defs(), self._make_node_positions())
        assert result["_node_id_map"] == spec["_node_id_map"]


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


# ---------------------------------------------------------------------------
# query_screen_visuals tests
# ---------------------------------------------------------------------------

def _seed_visual_screen(db: sqlite3.Connection) -> None:
    """Insert screen data with rich visual properties for query_screen_visuals tests."""
    seed_catalog(db)
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'Settings', 428, 926)"
    )

    fills_json = json.dumps([{
        "type": "SOLID", "color": {"r": 0.98, "g": 0.98, "b": 0.98, "a": 1.0},
        "opacity": 1.0,
    }])
    strokes_json = json.dumps([{
        "type": "SOLID", "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0},
    }])
    effects_json = json.dumps([{
        "type": "BACKGROUND_BLUR", "visible": True, "radius": 15.0,
    }])

    db.execute(
        "INSERT INTO nodes "
        "(id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
        "x, y, width, height, fills, strokes, effects, corner_radius, opacity, "
        "stroke_weight, stroke_align, blend_mode, visible, clips_content, "
        "component_key, rotation, constraint_h, constraint_v, "
        "font_family, font_weight, font_size, font_style, line_height, "
        "letter_spacing, text_align, text_content) "
        "VALUES (10, 1, 'h1', 'nav/top-nav', 'INSTANCE', 1, 0, "
        "0, 0, 428, 56, ?, ?, ?, '8', 0.95, "
        "2.0, 'INSIDE', 'NORMAL', 1, 0, "
        "'abc123', 0.0, 'MIN', 'MIN', "
        "NULL, NULL, NULL, NULL, NULL, "
        "NULL, NULL, NULL)",
        (fills_json, strokes_json, effects_json),
    )
    db.execute(
        "INSERT INTO nodes "
        "(id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
        "x, y, width, height, "
        "font_family, font_weight, font_size, font_style, line_height, "
        "letter_spacing, text_align, text_content) "
        "VALUES (11, 1, 't1', 'Section Title', 'TEXT', 2, 1, "
        "16, 80, 396, 28, "
        "'Inter', 700, 24, 'Bold', '32', "
        "'0.5', 'LEFT', 'Settings')",
    )

    # Token + binding
    db.execute("INSERT INTO token_collections (id, file_id, name) VALUES (1, 1, 'Colors')")
    db.execute("INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (1, 1, 'Default', 1)")
    db.execute("INSERT INTO tokens (id, collection_id, name, type) VALUES (1, 1, 'color.surface.primary', 'color')")
    db.execute("INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (1, 1, '#FAFAFA', '#FAFAFA')")
    db.execute(
        "INSERT INTO node_token_bindings (id, node_id, property, token_id, raw_value, resolved_value, binding_status) "
        "VALUES (1, 10, 'fill.0.color', 1, '#FAFAFA', '#FAFAFA', 'bound')"
    )

    db.commit()


class TestQueryScreenVisuals:
    """Verify query_screen_visuals() fetches visual properties for all nodes in a screen."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_visual_screen(conn)
        yield conn
        conn.close()

    def test_returns_dict_keyed_by_node_id(self, db: sqlite3.Connection):
        result = query_screen_visuals(db, screen_id=1)
        assert isinstance(result, dict)
        assert 10 in result
        assert 11 in result

    def test_includes_fills_strokes_effects(self, db: sqlite3.Connection):
        result = query_screen_visuals(db, screen_id=1)
        node_10 = result[10]
        assert node_10["fills"] is not None
        assert node_10["strokes"] is not None
        assert node_10["effects"] is not None

    def test_includes_extended_visual_columns(self, db: sqlite3.Connection):
        result = query_screen_visuals(db, screen_id=1)
        node_10 = result[10]
        assert node_10["stroke_weight"] == 2.0
        assert node_10["stroke_align"] == "INSIDE"
        assert node_10["blend_mode"] == "NORMAL"
        assert node_10["corner_radius"] == "8"
        assert node_10["opacity"] == 0.95
        assert node_10["visible"] == 1
        assert node_10["clips_content"] == 0
        assert node_10["rotation"] == 0.0
        assert node_10["constraint_h"] == "MIN"
        assert node_10["constraint_v"] == "MIN"

    def test_includes_component_key(self, db: sqlite3.Connection):
        result = query_screen_visuals(db, screen_id=1)
        assert result[10]["component_key"] == "abc123"

    def test_includes_typography(self, db: sqlite3.Connection):
        result = query_screen_visuals(db, screen_id=1)
        node_11 = result[11]
        assert node_11["font_family"] == "Inter"
        assert node_11["font_weight"] == 700
        assert node_11["font_size"] == 24
        assert node_11["font_style"] == "Bold"
        assert node_11["line_height"] == "32"
        assert node_11["letter_spacing"] == "0.5"
        assert node_11["text_align"] == "LEFT"
        assert node_11["text_content"] == "Settings"

    def test_includes_bindings(self, db: sqlite3.Connection):
        result = query_screen_visuals(db, screen_id=1)
        node_10 = result[10]
        assert "bindings" in node_10
        assert len(node_10["bindings"]) == 1
        assert node_10["bindings"][0]["property"] == "fill.0.color"
        assert node_10["bindings"][0]["token_name"] == "color.surface.primary"

    def test_empty_screen_returns_empty_dict(self, db: sqlite3.Connection):
        result = query_screen_visuals(db, screen_id=999)
        assert result == {}

    def test_node_without_bindings_has_empty_list(self, db: sqlite3.Connection):
        result = query_screen_visuals(db, screen_id=1)
        node_11 = result[11]
        assert node_11["bindings"] == []

    def test_includes_component_figma_id_from_registry(self, db: sqlite3.Connection):
        """When component_key_registry exists, figma_node_id is included."""
        db.execute(
            "CREATE TABLE IF NOT EXISTS component_key_registry "
            "(component_key TEXT PRIMARY KEY, figma_node_id TEXT, name TEXT, instance_count INTEGER)"
        )
        db.execute(
            "INSERT INTO component_key_registry VALUES ('abc123', '1835:155037', 'nav/top-nav', 45)"
        )
        db.commit()
        result = query_screen_visuals(db, screen_id=1)
        assert result[10].get("component_figma_id") == "1835:155037"

    def test_component_figma_id_none_without_registry(self, db: sqlite3.Connection):
        """Without the registry table, component_figma_id is absent."""
        result = query_screen_visuals(db, screen_id=1)
        # component_figma_id not in result when registry doesn't exist
        assert result[10].get("component_figma_id") is None


class TestDeepChildSwaps:
    """Verify child_swaps captures swapped instances at any nesting depth."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, 's1', 'Screen', 428, 926)"
        )

        # Top-level INSTANCE (nav/top-nav, depth 1)
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
            "is_semantic, visible, component_key, parent_id, x, y, width, height, extracted_at) "
            "VALUES (100, 1, '2244:100', 'nav/top-nav', 'INSTANCE', 1, 0, "
            "1, 1, 'nav_key', NULL, 0, 0, 428, 111, '2026-01-01')"
        )
        # Frame inside instance (Left, depth 2)
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
            "is_semantic, visible, parent_id, x, y, width, height, extracted_at) "
            "VALUES (101, 1, 'I2244:100;1835:001', 'Left', 'FRAME', 2, 0, "
            "0, 1, 100, 0, 0, 130, 64, '2026-01-01')"
        )
        # Button INSTANCE inside frame (depth 3) — with a swapped icon
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
            "is_semantic, visible, component_key, parent_id, x, y, width, height, extracted_at) "
            "VALUES (102, 1, 'I2244:100;2036:002', 'button/small/translucent', 'INSTANCE', 3, 0, "
            "0, 1, 'btn_small_key', 101, 0, 0, 48, 32, '2026-01-01')"
        )
        # Swapped icon INSTANCE inside button (depth 4) — the actual icon
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
            "is_semantic, visible, component_key, parent_id, x, y, width, height, extracted_at) "
            "VALUES (103, 1, 'I2244:100;2036:002;1334:003', 'icon/undo', 'INSTANCE', 4, 0, "
            "0, 1, 'icon_undo_key', 102, 0, 0, 24, 24, '2026-01-01')"
        )

        # Non-overridden INSTANCE at depth 3 (default component, should NOT be swapped)
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
            "is_semantic, visible, component_key, parent_id, x, y, width, height, extracted_at) "
            "VALUES (104, 1, 'I2244:100;2036:004', 'button/small/translucent', 'INSTANCE', 3, 1, "
            "0, 1, 'btn_default_key', 101, 50, 0, 48, 32, '2026-01-01')"
        )

        # Component key registry for the swap targets
        conn.execute(
            "CREATE TABLE IF NOT EXISTS component_key_registry "
            "(component_key TEXT PRIMARY KEY, figma_node_id TEXT, name TEXT, instance_count INTEGER)"
        )
        conn.execute(
            "INSERT INTO component_key_registry VALUES ('nav_key', '1835:155037', 'nav/top-nav', 10)"
        )
        conn.execute(
            "INSERT INTO component_key_registry VALUES ('icon_undo_key', '1315:139115', 'icon/undo', 5)"
        )
        conn.execute(
            "INSERT INTO component_key_registry VALUES ('btn_small_key', '1334:10864', 'button/small', 20)"
        )
        conn.execute(
            "INSERT INTO component_key_registry VALUES ('btn_default_key', '1334:10865', 'button/default', 20)"
        )

        # Instance overrides: only the icon swap is an actual override
        conn.execute(
            "CREATE TABLE IF NOT EXISTS instance_overrides ("
            "id INTEGER PRIMARY KEY, "
            "node_id INTEGER NOT NULL, "
            "property_type TEXT NOT NULL, "
            "property_name TEXT NOT NULL, "
            "override_value TEXT, "
            "UNIQUE(node_id, property_name))"
        )
        # override_value is the figma_node_id of the swap target component
        conn.execute(
            "INSERT INTO instance_overrides (node_id, property_type, property_name, override_value) "
            "VALUES (100, 'INSTANCE_SWAP', ';2036:002;1334:003', '1315:139115')"
        )
        # Also add a non-swap override to verify it's not picked up as a swap
        conn.execute(
            "INSERT INTO instance_overrides (node_id, property_type, property_name, override_value) "
            "VALUES (100, 'BOOLEAN', ';2036:004:visible', 'false')"
        )
        conn.commit()
        yield conn
        conn.close()

    def test_overridden_child_swap_captured(self, db: sqlite3.Connection):
        """Only overridden icon swap should appear, not all descendant instances."""
        result = query_screen_visuals(db, screen_id=1)

        nav_visual = result[100]
        child_swaps = nav_visual.get("child_swaps", [])

        # Should find the overridden icon swap
        swap_ids = [cs["child_id"] for cs in child_swaps]
        assert any(";1334:003" in sid for sid in swap_ids), (
            f"Expected overridden swap ;1334:003, got {swap_ids}"
        )

    def test_all_descendant_instances_included(self, db: sqlite3.Connection):
        """All visible descendant INSTANCE nodes appear in child_swaps.

        The recursive CTE returns every descendant instance because we can't
        know which ones differ from the master's default without storing
        master component data. swapComponent is a no-op for matching components.
        """
        result = query_screen_visuals(db, screen_id=1)

        nav_visual = result[100]
        child_swaps = nav_visual.get("child_swaps", [])

        # Both overridden (node 103) and non-overridden (node 104) are included
        swap_ids = [cs["child_id"] for cs in child_swaps]
        assert any(";1334:003" in sid for sid in swap_ids), "Overridden icon should be in swaps"
        assert any(";2036:004" in sid for sid in swap_ids), "All descendants included"

    def test_swap_has_correct_target_id(self, db: sqlite3.Connection):
        """The swap target should come from instance_overrides, not the node's own key."""
        result = query_screen_visuals(db, screen_id=1)

        nav_visual = result[100]
        child_swaps = nav_visual.get("child_swaps", [])
        icon_swap = next(cs for cs in child_swaps if ";1334:003" in cs["child_id"])
        assert icon_swap["swap_target_id"] == "1315:139115"
