"""Tests for dd/figma_api.py — Figma REST API client and node conversion.

These tests define the contract: given Figma REST API JSON shapes,
the conversion functions must produce dicts matching parse_extraction_response().
"""

import json
import pytest

from dd.figma_api import convert_node_tree, extract_top_level_frames


@pytest.mark.unit
class TestConvertNodeTree:
    """convert_node_tree converts a REST API node dict into extraction format."""

    def test_basic_frame_geometry(self):
        api_node = {
            "id": "100:1",
            "name": "Home",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 428, "height": 926},
            "fills": [],
            "strokes": [],
            "effects": [],
            "blendMode": "PASS_THROUGH",
            "children": [],
        }

        result = convert_node_tree(api_node)

        assert len(result) == 1
        node = result[0]
        assert node["figma_node_id"] == "100:1"
        assert node["name"] == "Home"
        assert node["node_type"] == "FRAME"
        assert node["x"] == 0
        assert node["y"] == 0
        assert node["width"] == 428
        assert node["height"] == 926
        assert node["depth"] == 0
        assert node["sort_order"] == 0
        assert node["parent_idx"] is None

    def test_solid_fill_converted_to_json_string(self):
        api_node = {
            "id": "100:2",
            "name": "Card",
            "type": "RECTANGLE",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [
                {
                    "blendMode": "NORMAL",
                    "type": "SOLID",
                    "color": {"r": 0.035, "g": 0.035, "b": 0.043, "a": 1.0},
                }
            ],
            "strokes": [],
            "effects": [],
            "children": [],
        }

        result = convert_node_tree(api_node)
        node = result[0]

        fills = json.loads(node["fills"])
        assert len(fills) == 1
        assert fills[0]["type"] == "SOLID"
        assert fills[0]["color"]["r"] == pytest.approx(0.035, abs=0.001)

    def test_gradient_fill_preserved(self):
        api_node = {
            "id": "100:3",
            "name": "Gradient",
            "type": "RECTANGLE",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [
                {
                    "blendMode": "NORMAL",
                    "type": "GRADIENT_LINEAR",
                    "gradientHandlePositions": [
                        {"x": 0, "y": 0.5},
                        {"x": 1, "y": 0.5},
                    ],
                    "gradientStops": [
                        {"color": {"r": 1, "g": 0, "b": 0, "a": 1}, "position": 0},
                        {"color": {"r": 0, "g": 0, "b": 1, "a": 1}, "position": 1},
                    ],
                }
            ],
            "strokes": [],
            "effects": [],
            "children": [],
        }

        result = convert_node_tree(api_node)
        fills = json.loads(result[0]["fills"])
        assert fills[0]["type"] == "GRADIENT_LINEAR"

    def test_stroke_converted_to_json_string(self):
        api_node = {
            "id": "100:4",
            "name": "Border",
            "type": "RECTANGLE",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [],
            "strokes": [
                {
                    "blendMode": "NORMAL",
                    "type": "SOLID",
                    "color": {"r": 0.831, "g": 0.831, "b": 0.847, "a": 1.0},
                }
            ],
            "effects": [],
            "children": [],
        }

        result = convert_node_tree(api_node)
        strokes = json.loads(result[0]["strokes"])
        assert len(strokes) == 1
        assert strokes[0]["color"]["r"] == pytest.approx(0.831, abs=0.001)

    def test_drop_shadow_effect(self):
        api_node = {
            "id": "100:5",
            "name": "Shadow",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [],
            "strokes": [],
            "effects": [
                {
                    "type": "DROP_SHADOW",
                    "visible": True,
                    "color": {"r": 0, "g": 0, "b": 0, "a": 0.1},
                    "blendMode": "NORMAL",
                    "offset": {"x": 0, "y": 4},
                    "radius": 8,
                    "spread": 0,
                }
            ],
            "children": [],
        }

        result = convert_node_tree(api_node)
        effects = json.loads(result[0]["effects"])
        assert len(effects) == 1
        assert effects[0]["type"] == "DROP_SHADOW"
        assert effects[0]["radius"] == 8
        assert effects[0]["offset"]["y"] == 4

    def test_typography_from_style_object(self):
        api_node = {
            "id": "100:6",
            "name": "Heading",
            "type": "TEXT",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 200, "height": 32},
            "fills": [
                {
                    "type": "SOLID",
                    "color": {"r": 0, "g": 0, "b": 0, "a": 1},
                }
            ],
            "strokes": [],
            "effects": [],
            "characters": "Hello World",
            "style": {
                "fontFamily": "Inter",
                "fontWeight": 600,
                "fontSize": 24,
                "textAlignHorizontal": "LEFT",
                "letterSpacing": -0.5,
                "lineHeightPx": 32,
                "lineHeightPercent": 133.33,
                "lineHeightUnit": "PIXELS",
            },
        }

        result = convert_node_tree(api_node)
        node = result[0]

        assert node["font_family"] == "Inter"
        assert node["font_weight"] == 600
        assert node["font_size"] == 24
        assert node["text_align"] == "LEFT"
        assert node["text_content"] == "Hello World"

        line_height = json.loads(node["line_height"])
        assert line_height["value"] == 32
        assert line_height["unit"] == "PIXELS"

        letter_spacing = json.loads(node["letter_spacing"])
        assert letter_spacing["value"] == -0.5
        assert letter_spacing["unit"] == "PIXELS"

    def test_typography_intrinsic_line_height(self):
        api_node = {
            "id": "100:7",
            "name": "Body",
            "type": "TEXT",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 200, "height": 20},
            "fills": [],
            "strokes": [],
            "effects": [],
            "characters": "Auto height",
            "style": {
                "fontFamily": "Inter",
                "fontWeight": 400,
                "fontSize": 16,
                "textAlignHorizontal": "LEFT",
                "letterSpacing": 0,
                "lineHeightPx": 19.36,
                "lineHeightPercent": 100,
                "lineHeightUnit": "INTRINSIC_%",
            },
        }

        result = convert_node_tree(api_node)
        line_height = json.loads(result[0]["line_height"])
        assert line_height["unit"] == "AUTO"

    def test_auto_layout_properties(self):
        api_node = {
            "id": "100:8",
            "name": "Container",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 428, "height": 926},
            "fills": [],
            "strokes": [],
            "effects": [],
            "layoutMode": "VERTICAL",
            "paddingTop": 16,
            "paddingRight": 16,
            "paddingBottom": 16,
            "paddingLeft": 16,
            "itemSpacing": 8,
            "counterAxisSpacing": None,
            "primaryAxisAlignItems": "MIN",
            "counterAxisAlignItems": "CENTER",
            "layoutSizingHorizontal": "FILL",
            "layoutSizingVertical": "HUG",
            "children": [],
        }

        result = convert_node_tree(api_node)
        node = result[0]

        assert node["layout_mode"] == "VERTICAL"
        assert node["padding_top"] == 16
        assert node["padding_right"] == 16
        assert node["padding_bottom"] == 16
        assert node["padding_left"] == 16
        assert node["item_spacing"] == 8
        assert node["primary_align"] == "MIN"
        assert node["counter_align"] == "CENTER"
        assert node["layout_sizing_h"] == "FILL"
        assert node["layout_sizing_v"] == "HUG"

    def test_layout_mode_none_omitted(self):
        api_node = {
            "id": "100:9",
            "name": "Static",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [],
            "strokes": [],
            "effects": [],
            "layoutMode": "NONE",
            "children": [],
        }

        result = convert_node_tree(api_node)
        assert "layout_mode" not in result[0]

    def test_uniform_corner_radius(self):
        api_node = {
            "id": "100:10",
            "name": "Rounded",
            "type": "RECTANGLE",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [],
            "strokes": [],
            "effects": [],
            "cornerRadius": 8,
            "rectangleCornerRadii": None,
            "children": [],
        }

        result = convert_node_tree(api_node)
        assert result[0]["corner_radius"] == 8

    def test_mixed_corner_radius(self):
        api_node = {
            "id": "100:11",
            "name": "Mixed",
            "type": "RECTANGLE",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [],
            "strokes": [],
            "effects": [],
            "cornerRadius": 8,
            "rectangleCornerRadii": [8, 0, 4, 4],
            "children": [],
        }

        result = convert_node_tree(api_node)
        radius = json.loads(result[0]["corner_radius"])
        assert radius == {"tl": 8, "tr": 0, "bl": 4, "br": 4}

    def test_instance_component_id(self):
        api_node = {
            "id": "100:12",
            "name": "button/large/solid",
            "type": "INSTANCE",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 200, "height": 48},
            "fills": [],
            "strokes": [],
            "effects": [],
            "componentId": "1334:10840",
            "children": [],
        }

        result = convert_node_tree(api_node)
        assert result[0]["component_figma_id"] == "1334:10840"

    def test_visibility_false(self):
        api_node = {
            "id": "100:13",
            "name": "Hidden",
            "type": "RECTANGLE",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [],
            "strokes": [],
            "effects": [],
            "visible": False,
            "children": [],
        }

        result = convert_node_tree(api_node)
        assert result[0]["visible"] is False

    def test_visibility_default_true(self):
        api_node = {
            "id": "100:14",
            "name": "Visible",
            "type": "RECTANGLE",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [],
            "strokes": [],
            "effects": [],
            "children": [],
        }

        result = convert_node_tree(api_node)
        assert result[0]["visible"] is True

    def test_opacity(self):
        api_node = {
            "id": "100:15",
            "name": "Faded",
            "type": "RECTANGLE",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [],
            "strokes": [],
            "effects": [],
            "opacity": 0.5,
            "children": [],
        }

        result = convert_node_tree(api_node)
        assert result[0]["opacity"] == 0.5

    def test_blend_mode(self):
        api_node = {
            "id": "100:16",
            "name": "Multiplied",
            "type": "RECTANGLE",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [],
            "strokes": [],
            "effects": [],
            "blendMode": "MULTIPLY",
            "children": [],
        }

        result = convert_node_tree(api_node)
        assert result[0]["blend_mode"] == "MULTIPLY"

    def test_tree_with_children_builds_parent_idx(self):
        api_node = {
            "id": "100:1",
            "name": "Screen",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 428, "height": 926},
            "fills": [],
            "strokes": [],
            "effects": [],
            "children": [
                {
                    "id": "100:2",
                    "name": "Header",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 428, "height": 64},
                    "fills": [],
                    "strokes": [],
                    "effects": [],
                    "children": [
                        {
                            "id": "100:3",
                            "name": "Title",
                            "type": "TEXT",
                            "absoluteBoundingBox": {"x": 16, "y": 20, "width": 100, "height": 24},
                            "fills": [],
                            "strokes": [],
                            "effects": [],
                            "characters": "Home",
                            "style": {
                                "fontFamily": "Inter",
                                "fontWeight": 700,
                                "fontSize": 18,
                                "textAlignHorizontal": "LEFT",
                                "letterSpacing": 0,
                                "lineHeightPx": 24,
                                "lineHeightPercent": 133,
                                "lineHeightUnit": "PIXELS",
                            },
                        },
                    ],
                },
                {
                    "id": "100:4",
                    "name": "Body",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 64, "width": 428, "height": 862},
                    "fills": [],
                    "strokes": [],
                    "effects": [],
                    "children": [],
                },
            ],
        }

        result = convert_node_tree(api_node)

        assert len(result) == 4
        assert result[0]["figma_node_id"] == "100:1"
        assert result[0]["parent_idx"] is None
        assert result[0]["depth"] == 0

        assert result[1]["figma_node_id"] == "100:2"
        assert result[1]["parent_idx"] == 0
        assert result[1]["depth"] == 1
        assert result[1]["sort_order"] == 0

        assert result[2]["figma_node_id"] == "100:3"
        assert result[2]["parent_idx"] == 1
        assert result[2]["depth"] == 2

        assert result[3]["figma_node_id"] == "100:4"
        assert result[3]["parent_idx"] == 0
        assert result[3]["depth"] == 1
        assert result[3]["sort_order"] == 1

    def test_node_without_bounding_box(self):
        api_node = {
            "id": "100:20",
            "name": "Mask",
            "type": "VECTOR",
            "fills": [],
            "strokes": [],
            "effects": [],
            "children": [],
        }

        result = convert_node_tree(api_node)
        assert result[0]["x"] is None
        assert result[0]["width"] is None

    def test_empty_fills_strokes_effects_omitted(self):
        api_node = {
            "id": "100:21",
            "name": "Empty",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "fills": [],
            "strokes": [],
            "effects": [],
            "children": [],
        }

        result = convert_node_tree(api_node)
        assert "fills" not in result[0] or result[0].get("fills") is None
        assert "strokes" not in result[0] or result[0].get("strokes") is None
        assert "effects" not in result[0] or result[0].get("effects") is None


@pytest.mark.unit
class TestExtractTopLevelFrames:
    """extract_top_level_frames pulls frame metadata from file JSON."""

    def test_extracts_frames_from_page(self):
        file_json = {
            "document": {
                "id": "0:0",
                "type": "DOCUMENT",
                "children": [
                    {
                        "id": "1:1",
                        "name": "Page 1",
                        "type": "CANVAS",
                        "children": [
                            {
                                "id": "100:1",
                                "name": "Home",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 0, "y": 0, "width": 428, "height": 926
                                },
                                "children": [],
                            },
                            {
                                "id": "100:2",
                                "name": "Settings",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 500, "y": 0, "width": 428, "height": 926
                                },
                                "children": [],
                            },
                        ],
                    }
                ],
            }
        }

        frames = extract_top_level_frames(file_json, page_id="1:1")

        assert len(frames) == 2
        assert frames[0]["figma_node_id"] == "100:1"
        assert frames[0]["name"] == "Home"
        assert frames[0]["width"] == 428
        assert frames[0]["height"] == 926

    def test_filters_to_specified_page(self):
        file_json = {
            "document": {
                "id": "0:0",
                "type": "DOCUMENT",
                "children": [
                    {
                        "id": "1:1",
                        "name": "Page 1",
                        "type": "CANVAS",
                        "children": [
                            {
                                "id": "100:1",
                                "name": "Home",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 0, "y": 0, "width": 428, "height": 926
                                },
                                "children": [],
                            },
                        ],
                    },
                    {
                        "id": "2:2",
                        "name": "Page 2",
                        "type": "CANVAS",
                        "children": [
                            {
                                "id": "200:1",
                                "name": "Other",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 0, "y": 0, "width": 1920, "height": 1080
                                },
                                "children": [],
                            },
                        ],
                    },
                ],
            }
        }

        frames = extract_top_level_frames(file_json, page_id="1:1")
        assert len(frames) == 1
        assert frames[0]["name"] == "Home"

    def test_uses_first_page_when_no_page_id(self):
        file_json = {
            "document": {
                "id": "0:0",
                "type": "DOCUMENT",
                "children": [
                    {
                        "id": "1:1",
                        "name": "Page 1",
                        "type": "CANVAS",
                        "children": [
                            {
                                "id": "100:1",
                                "name": "Home",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 0, "y": 0, "width": 428, "height": 926
                                },
                                "children": [],
                            },
                        ],
                    },
                ],
            }
        }

        frames = extract_top_level_frames(file_json)
        assert len(frames) == 1

    def test_includes_component_and_component_set(self):
        file_json = {
            "document": {
                "id": "0:0",
                "type": "DOCUMENT",
                "children": [
                    {
                        "id": "1:1",
                        "name": "Page 1",
                        "type": "CANVAS",
                        "children": [
                            {
                                "id": "100:1",
                                "name": "Button",
                                "type": "COMPONENT_SET",
                                "absoluteBoundingBox": {
                                    "x": 0, "y": 0, "width": 200, "height": 48
                                },
                                "children": [],
                            },
                            {
                                "id": "100:2",
                                "name": "Icon",
                                "type": "COMPONENT",
                                "absoluteBoundingBox": {
                                    "x": 0, "y": 0, "width": 24, "height": 24
                                },
                                "children": [],
                            },
                        ],
                    }
                ],
            }
        }

        frames = extract_top_level_frames(file_json, page_id="1:1")
        assert len(frames) == 2

    def test_frame_from_nodes_endpoint_format(self):
        """When using /v1/files/:key/nodes, the response wraps nodes differently."""
        nodes_response = {
            "nodes": {
                "1:1": {
                    "document": {
                        "id": "1:1",
                        "name": "Page 1",
                        "type": "CANVAS",
                        "children": [
                            {
                                "id": "100:1",
                                "name": "Home",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 0, "y": 0, "width": 428, "height": 926
                                },
                                "children": [],
                            },
                        ],
                    }
                }
            }
        }

        frames = extract_top_level_frames(
            nodes_response, page_id="1:1", from_nodes_endpoint=True
        )
        assert len(frames) == 1
        assert frames[0]["name"] == "Home"


@pytest.mark.unit
class TestConvertNodeTreeWithRealFixture:
    """Test conversion using recorded real Figma API data."""

    def test_real_fixture_converts_without_error(self):
        with open("tests/fixtures/figma_api_screen_fixture.json") as f:
            data = json.load(f)

        screen_node = data["nodes"]["2219:235687"]["document"]
        result = convert_node_tree(screen_node)

        assert len(result) > 0
        assert result[0]["figma_node_id"] == "2219:235687"
        assert result[0]["node_type"] == "FRAME"
        assert result[0]["width"] == pytest.approx(428, abs=1)
        assert result[0]["height"] == pytest.approx(926, abs=1)

    def test_real_fixture_all_nodes_have_required_fields(self):
        with open("tests/fixtures/figma_api_screen_fixture.json") as f:
            data = json.load(f)

        screen_node = data["nodes"]["2219:235687"]["document"]
        result = convert_node_tree(screen_node)

        for node in result:
            assert "figma_node_id" in node
            assert "name" in node
            assert "node_type" in node
            assert "depth" in node
            assert "sort_order" in node
            assert "parent_idx" in node

    def test_real_fixture_parent_idx_valid(self):
        with open("tests/fixtures/figma_api_screen_fixture.json") as f:
            data = json.load(f)

        screen_node = data["nodes"]["2219:235687"]["document"]
        result = convert_node_tree(screen_node)

        for i, node in enumerate(result):
            if node["parent_idx"] is not None:
                assert node["parent_idx"] < i, (
                    f"Node {node['figma_node_id']} has parent_idx {node['parent_idx']} "
                    f"but is at index {i}"
                )
