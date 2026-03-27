"""Unit tests for normalization utilities."""

import json
import pytest
from dd.normalize import (
    normalize_fill,
    normalize_stroke,
    normalize_effect,
    normalize_typography,
    normalize_spacing,
    normalize_radius,
)


pytestmark = pytest.mark.unit
pytest.mark.timeout(10)


class TestNormalizeFill:
    """Test normalize_fill function."""

    def test_single_solid_fill(self):
        """Test single solid fill produces correct binding."""
        fills = [
            {
                "type": "SOLID",
                "visible": True,
                "color": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1.0},
            }
        ]
        result = normalize_fill(fills)
        assert len(result) == 1
        assert result[0]["property"] == "fill.0.color"
        assert result[0]["resolved_value"] == "#808080"
        # Verify raw_value is valid JSON
        raw_data = json.loads(result[0]["raw_value"])
        assert raw_data == {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1.0}

    def test_two_solid_fills(self):
        """Test two solid fills produce indexed bindings."""
        fills = [
            {"type": "SOLID", "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}},
            {"type": "SOLID", "color": {"r": 0.0, "g": 1.0, "b": 0.0, "a": 1.0}},
        ]
        result = normalize_fill(fills)
        assert len(result) == 2
        assert result[0]["property"] == "fill.0.color"
        assert result[0]["resolved_value"] == "#FF0000"
        assert result[1]["property"] == "fill.1.color"
        assert result[1]["resolved_value"] == "#00FF00"

    def test_gradient_fill(self):
        """Test gradient fill produces gradient binding."""
        fills = [
            {
                "type": "GRADIENT_LINEAR",
                "gradientStops": [
                    {"position": 0, "color": {"r": 0, "g": 0, "b": 0, "a": 1}},
                    {"position": 1, "color": {"r": 1, "g": 1, "b": 1, "a": 1}},
                ],
            }
        ]
        result = normalize_fill(fills)
        assert len(result) == 1
        assert result[0]["property"] == "fill.0.gradient"
        assert result[0]["resolved_value"] == "gradient"
        # Verify raw_value contains full gradient data
        raw_data = json.loads(result[0]["raw_value"])
        assert raw_data["type"] == "GRADIENT_LINEAR"

    def test_invisible_fill_skipped(self):
        """Test invisible fill is skipped."""
        fills = [
            {"type": "SOLID", "visible": False, "color": {"r": 1, "g": 0, "b": 0}},
            {"type": "SOLID", "visible": True, "color": {"r": 0, "g": 1, "b": 0}},
        ]
        result = normalize_fill(fills)
        assert len(result) == 1
        # Only the visible fill at original index 1 is processed, but indexed as 0 in output
        assert result[0]["property"] == "fill.1.color"
        assert result[0]["resolved_value"] == "#00FF00"

    def test_image_fill_skipped(self):
        """Test IMAGE fill type is skipped."""
        fills = [
            {"type": "IMAGE", "imageRef": "some-image"},
            {"type": "SOLID", "color": {"r": 0, "g": 0, "b": 1}},
        ]
        result = normalize_fill(fills)
        assert len(result) == 1
        assert result[0]["property"] == "fill.1.color"
        assert result[0]["resolved_value"] == "#0000FF"

    def test_empty_fills(self):
        """Test empty fills list returns empty bindings."""
        result = normalize_fill([])
        assert result == []

    def test_mixed_visible_invisible(self):
        """Test mix of visible and invisible fills."""
        fills = [
            {"type": "SOLID", "visible": True, "color": {"r": 1, "g": 0, "b": 0}},
            {"type": "SOLID", "visible": False, "color": {"r": 0, "g": 1, "b": 0}},
            {"type": "SOLID", "visible": True, "color": {"r": 0, "g": 0, "b": 1}},
        ]
        result = normalize_fill(fills)
        assert len(result) == 2
        assert result[0]["property"] == "fill.0.color"
        assert result[0]["resolved_value"] == "#FF0000"
        assert result[1]["property"] == "fill.2.color"
        assert result[1]["resolved_value"] == "#0000FF"


    def test_fill_with_sub_1_opacity_includes_alpha(self):
        """Fill paint opacity < 1 should produce 8-digit hex with alpha baked in."""
        fills = [
            {
                "type": "SOLID",
                "visible": True,
                "color": {"r": 0.46, "g": 0.46, "b": 0.50, "a": 1.0},
                "opacity": 0.12,
            }
        ]
        result = normalize_fill(fills)
        assert len(result) == 1
        # resolved_value should be 8-digit hex with alpha
        assert len(result[0]["resolved_value"]) == 9  # #RRGGBBAA
        assert result[0]["resolved_value"].endswith("1F") or result[0]["resolved_value"].endswith("1E")  # 0.12 * 255 ≈ 31 = 0x1F

    def test_fill_with_full_opacity_stays_6_digit(self):
        """Fill paint opacity = 1.0 should produce standard 6-digit hex."""
        fills = [
            {
                "type": "SOLID",
                "visible": True,
                "color": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1.0},
                "opacity": 1.0,
            }
        ]
        result = normalize_fill(fills)
        assert len(result[0]["resolved_value"]) == 7  # #RRGGBB

    def test_fill_without_opacity_field_defaults_to_full(self):
        """Fill without explicit opacity field should default to 1.0 (6-digit hex)."""
        fills = [
            {"type": "SOLID", "color": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1.0}}
        ]
        result = normalize_fill(fills)
        assert len(result[0]["resolved_value"]) == 7  # #RRGGBB


class TestNormalizeStroke:
    """Test normalize_stroke function."""

    def test_single_solid_stroke(self):
        """Test single solid stroke produces correct binding."""
        strokes = [
            {
                "type": "SOLID",
                "visible": True,
                "color": {"r": 0.2, "g": 0.3, "b": 0.4, "a": 1.0},
            }
        ]
        result = normalize_stroke(strokes)
        assert len(result) == 1
        assert result[0]["property"] == "stroke.0.color"
        assert result[0]["resolved_value"] == "#334C66"  # 6-digit hex, no paint opacity
        raw_data = json.loads(result[0]["raw_value"])
        assert raw_data == {"r": 0.2, "g": 0.3, "b": 0.4, "a": 1.0}

    def test_stroke_with_sub_1_opacity_includes_alpha(self):
        """Stroke paint opacity < 1 should produce 8-digit hex with alpha baked in."""
        strokes = [
            {
                "type": "SOLID",
                "visible": True,
                "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0},
                "opacity": 0.3,
            }
        ]
        result = normalize_stroke(strokes)
        assert len(result[0]["resolved_value"]) == 9  # #RRGGBBAA

    def test_invisible_stroke_skipped(self):
        """Test invisible stroke is skipped."""
        strokes = [
            {"type": "SOLID", "visible": False, "color": {"r": 1, "g": 0, "b": 0}},
            {"type": "SOLID", "color": {"r": 0, "g": 1, "b": 0}},  # visible not specified
        ]
        result = normalize_stroke(strokes)
        assert len(result) == 1
        assert result[0]["property"] == "stroke.1.color"

    def test_multiple_strokes_indexed(self):
        """Test multiple strokes are indexed correctly."""
        strokes = [
            {"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0}},
            {"type": "SOLID", "color": {"r": 0, "g": 1, "b": 0}},
            {"type": "SOLID", "color": {"r": 0, "g": 0, "b": 1}},
        ]
        result = normalize_stroke(strokes)
        assert len(result) == 3
        assert result[0]["property"] == "stroke.0.color"
        assert result[1]["property"] == "stroke.1.color"
        assert result[2]["property"] == "stroke.2.color"


class TestNormalizeEffect:
    """Test normalize_effect function."""

    def test_drop_shadow(self):
        """Test DROP_SHADOW produces 5 bindings."""
        effects = [
            {
                "type": "DROP_SHADOW",
                "visible": True,
                "color": {"r": 0, "g": 0, "b": 0, "a": 0.25},
                "radius": 4,
                "offset": {"x": 0, "y": 2},
                "spread": 0,
            }
        ]
        result = normalize_effect(effects)
        assert len(result) == 5

        # Check all properties are present
        props = {r["property"] for r in result}
        assert props == {
            "effect.0.color",
            "effect.0.radius",
            "effect.0.offsetX",
            "effect.0.offsetY",
            "effect.0.spread",
        }

        # Verify specific values
        color_binding = next(r for r in result if r["property"] == "effect.0.color")
        assert color_binding["resolved_value"] == "#00000040"

        radius_binding = next(r for r in result if r["property"] == "effect.0.radius")
        assert radius_binding["resolved_value"] == "4"

    def test_inner_shadow(self):
        """Test INNER_SHADOW also produces 5 bindings."""
        effects = [
            {
                "type": "INNER_SHADOW",
                "color": {"r": 1, "g": 1, "b": 1, "a": 0.5},
                "radius": 8,
                "offset": {"x": -2, "y": -2},
                "spread": 2,
            }
        ]
        result = normalize_effect(effects)
        assert len(result) == 5

        # Verify all expected properties
        props = {r["property"] for r in result}
        assert "effect.0.color" in props
        assert "effect.0.offsetX" in props
        assert "effect.0.offsetY" in props

    def test_layer_blur(self):
        """Test LAYER_BLUR produces only radius binding."""
        effects = [{"type": "LAYER_BLUR", "radius": 10}]
        result = normalize_effect(effects)
        assert len(result) == 1
        assert result[0]["property"] == "effect.0.radius"
        assert result[0]["resolved_value"] == "10"

    def test_invisible_effect_skipped(self):
        """Test invisible effect is skipped."""
        effects = [
            {"type": "DROP_SHADOW", "visible": False, "radius": 4},
            {"type": "LAYER_BLUR", "visible": True, "radius": 5},
        ]
        result = normalize_effect(effects)
        assert len(result) == 1
        assert result[0]["property"] == "effect.1.radius"

    def test_multiple_effects_indexed(self):
        """Test two effects are indexed correctly."""
        effects = [
            {"type": "LAYER_BLUR", "radius": 5},
            {"type": "LAYER_BLUR", "radius": 10},
        ]
        result = normalize_effect(effects)
        assert len(result) == 2
        assert result[0]["property"] == "effect.0.radius"
        assert result[0]["resolved_value"] == "5"
        assert result[1]["property"] == "effect.1.radius"
        assert result[1]["resolved_value"] == "10"


class TestNormalizeTypography:
    """Test normalize_typography function."""

    def test_full_text_node(self):
        """Test text node with all properties."""
        node = {
            "font_size": 16,
            "font_family": "Inter",
            "font_weight": 600,
            "line_height": {"value": 24, "unit": "PIXELS"},
            "letter_spacing": {"value": 0.5, "unit": "PIXELS"},
        }
        result = normalize_typography(node)
        assert len(result) == 5

        # Check all properties
        props = {r["property"]: r["resolved_value"] for r in result}
        assert props["fontSize"] == "16"
        assert props["fontFamily"] == "Inter"
        assert props["fontWeight"] == "600"
        assert props["lineHeight"] == "24"
        assert props["letterSpacing"] == "0.5"

    def test_mixed_values_skipped(self):
        """Test MIXED values are skipped."""
        node = {
            "font_size": "MIXED",
            "font_family": "Inter",
            "font_weight": "MIXED",
            "line_height": 20,
        }
        result = normalize_typography(node)
        assert len(result) == 2
        props = {r["property"] for r in result}
        assert "fontSize" not in props
        assert "fontWeight" not in props
        assert "fontFamily" in props
        assert "lineHeight" in props

    def test_none_values_skipped(self):
        """Test None values are skipped."""
        node = {
            "font_size": 14,
            "font_family": None,
            "font_weight": None,
        }
        result = normalize_typography(node)
        assert len(result) == 1
        assert result[0]["property"] == "fontSize"

    def test_line_height_auto(self):
        """Test lineHeight with AUTO unit."""
        node = {"line_height": {"unit": "AUTO"}}
        result = normalize_typography(node)
        assert len(result) == 1
        assert result[0]["property"] == "lineHeight"
        assert result[0]["resolved_value"] == "AUTO"

    def test_line_height_pixels(self):
        """Test lineHeight with PIXELS unit."""
        node = {"line_height": {"value": 24, "unit": "PIXELS"}}
        result = normalize_typography(node)
        assert len(result) == 1
        assert result[0]["resolved_value"] == "24"


class TestNormalizeSpacing:
    """Test normalize_spacing function."""

    def test_full_spacing_node(self):
        """Test node with all spacing properties."""
        node = {
            "padding_top": 8,
            "padding_right": 16,
            "padding_bottom": 8,
            "padding_left": 16,
            "item_spacing": 12,
            "counter_axis_spacing": 4,
        }
        result = normalize_spacing(node)
        assert len(result) == 6

        # Check property mapping
        props = {r["property"]: r["resolved_value"] for r in result}
        assert props["padding.top"] == "8"
        assert props["padding.right"] == "16"
        assert props["padding.bottom"] == "8"
        assert props["padding.left"] == "16"
        assert props["itemSpacing"] == "12"
        assert props["counterAxisSpacing"] == "4"

    def test_zero_values_skipped(self):
        """Test zero values are skipped."""
        node = {
            "padding_top": 0,
            "padding_right": 10,
            "padding_bottom": 0,
            "padding_left": 10,
            "item_spacing": 0,
        }
        result = normalize_spacing(node)
        assert len(result) == 2
        props = {r["property"] for r in result}
        assert "padding.top" not in props
        assert "padding.right" in props
        assert "itemSpacing" not in props

    def test_none_values_skipped(self):
        """Test None values are skipped."""
        node = {
            "padding_top": None,
            "padding_right": 5,
            "item_spacing": None,
        }
        result = normalize_spacing(node)
        assert len(result) == 1
        assert result[0]["property"] == "padding.right"

    def test_property_name_mapping(self):
        """Test property names are mapped correctly."""
        node = {
            "padding_top": 1,
            "item_spacing": 2,
            "counter_axis_spacing": 3,
        }
        result = normalize_spacing(node)
        props = {r["property"] for r in result}
        # Check renamed properties
        assert "padding.top" in props
        assert "itemSpacing" in props
        assert "counterAxisSpacing" in props
        # Original names should not appear
        assert "padding_top" not in props
        assert "item_spacing" not in props


class TestNormalizeRadius:
    """Test normalize_radius function."""

    def test_single_number(self):
        """Test single number produces uniform radius."""
        result = normalize_radius(8)
        assert len(result) == 1
        assert result[0]["property"] == "cornerRadius"
        assert result[0]["resolved_value"] == "8"
        # Verify raw_value is valid JSON
        assert json.loads(result[0]["raw_value"]) == 8

    def test_dict_mixed_values(self):
        """Test dict with mixed values produces per-corner bindings."""
        radius = {"tl": 8, "tr": 0, "bl": 4, "br": 4}
        result = normalize_radius(radius)
        assert len(result) == 3  # tr=0 is skipped

        props = {r["property"]: r["resolved_value"] for r in result}
        assert props["topLeftRadius"] == "8"
        assert "topRightRadius" not in props  # Zero value skipped
        assert props["bottomLeftRadius"] == "4"
        assert props["bottomRightRadius"] == "4"

    def test_zero_radius(self):
        """Test zero radius returns empty list."""
        result = normalize_radius(0)
        assert result == []

    def test_none_radius(self):
        """Test None returns empty list."""
        result = normalize_radius(None)
        assert result == []

    def test_float_radius(self):
        """Test float radius value."""
        result = normalize_radius(5.5)
        assert len(result) == 1
        assert result[0]["property"] == "cornerRadius"
        assert result[0]["resolved_value"] == "5.5"

    def test_dict_all_corners(self):
        """Test dict with all corners non-zero."""
        radius = {"tl": 2, "tr": 4, "bl": 6, "br": 8}
        result = normalize_radius(radius)
        assert len(result) == 4

        props = {r["property"]: r["resolved_value"] for r in result}
        assert props["topLeftRadius"] == "2"
        assert props["topRightRadius"] == "4"
        assert props["bottomLeftRadius"] == "6"
        assert props["bottomRightRadius"] == "8"