"""Tests for Figma generation from CompositionSpec IR (T5 Phase 3)."""

import json
import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.db import init_db
from dd.renderers.figma import (
    collect_fonts,
    font_weight_to_style,
    format_js_value,
    generate_figma_script,
    generate_screen,
    normalize_font_style,
    hex_to_figma_rgba,
)
from dd.visual import build_visual_from_db, resolve_style_value

# ---------------------------------------------------------------------------
# Step 1: Pure helpers
# ---------------------------------------------------------------------------

class TestHexToFigmaRgb:
    """Verify hex color → Figma RGBA {r,g,b,a} conversion."""

    def test_black(self):
        assert hex_to_figma_rgba("#000000") == {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0}

    def test_white(self):
        assert hex_to_figma_rgba("#FFFFFF") == {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}

    def test_red(self):
        assert hex_to_figma_rgba("#FF0000") == {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}

    def test_mixed(self):
        result = hex_to_figma_rgba("#80C040")
        assert abs(result["r"] - 0.502) < 0.01
        assert abs(result["g"] - 0.7529) < 0.01
        assert abs(result["b"] - 0.2510) < 0.01
        assert result["a"] == 1.0

    def test_lowercase(self):
        assert hex_to_figma_rgba("#ff0000") == {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}

    def test_eight_digit_preserves_alpha(self):
        result = hex_to_figma_rgba("#FF000080")
        assert result["r"] == 1.0
        assert result["a"] == round(128 / 255.0, 4)


class TestResolveStyleValue:
    """Verify token ref resolution from style values."""

    def test_token_ref_resolves(self):
        tokens = {"color.surface.primary": "#FAFAFA"}
        value, token_name = resolve_style_value("{color.surface.primary}", tokens)
        assert value == "#FAFAFA"
        assert token_name == "color.surface.primary"

    def test_plain_hex_passes_through(self):
        value, token_name = resolve_style_value("#FF0000", {})
        assert value == "#FF0000"
        assert token_name is None

    def test_numeric_passes_through(self):
        value, token_name = resolve_style_value(8, {})
        assert value == 8
        assert token_name is None

    def test_missing_token_returns_none_value(self):
        value, token_name = resolve_style_value("{missing.token}", {})
        assert value is None
        assert token_name == "missing.token"


class TestFontWeightToStyle:
    """Verify numeric font weight → Figma style name."""

    def test_700_bold(self):
        assert font_weight_to_style(700) == "Bold"

    def test_400_regular(self):
        assert font_weight_to_style(400) == "Regular"

    def test_600_semi_bold(self):
        assert font_weight_to_style(600) == "Semi Bold"

    def test_none_defaults_regular(self):
        assert font_weight_to_style(None) == "Regular"

    def test_string_passthrough(self):
        assert font_weight_to_style("Bold") == "Bold"


class TestNormalizeFontStyle:
    """Verify family-aware font style normalization."""

    def test_inter_semi_bold_unchanged(self):
        assert normalize_font_style("Inter", "Semi Bold") == "Semi Bold"

    def test_sf_pro_text_semibold(self):
        assert normalize_font_style("SF Pro Text", "Semi Bold") == "Semibold"

    def test_sf_pro_display_semibold(self):
        assert normalize_font_style("SF Pro Display", "Semi Bold") == "Semibold"

    def test_sf_pro_semibold(self):
        assert normalize_font_style("SF Pro", "Semi Bold") == "Semibold"

    def test_baskerville_semibold(self):
        assert normalize_font_style("Baskerville", "Semi Bold") == "SemiBold"

    def test_regular_unchanged(self):
        assert normalize_font_style("SF Pro Text", "Regular") == "Regular"

    def test_bold_unchanged(self):
        assert normalize_font_style("SF Pro Text", "Bold") == "Bold"

    def test_sf_pro_extra_bold(self):
        assert normalize_font_style("SF Pro Text", "Extra Bold") == "Extra Bold"

    def test_helvetica_no_semi_bold(self):
        """Helvetica Neue has no Semi Bold — should stay as-is (will fail at load time, not our concern)."""
        assert normalize_font_style("Helvetica Neue", "Semi Bold") == "Semi Bold"


class TestCollectFonts:
    """Verify font collection from spec elements."""

    def test_collects_from_text_element(self):
        spec = _make_spec({"text-1": {
            "type": "text",
            "style": {"fontFamily": "Inter", "fontWeight": 700},
        }})
        fonts = collect_fonts(spec)
        assert ("Inter", "Bold") in fonts

    def test_default_for_bare_text(self):
        spec = _make_spec({"text-1": {"type": "text"}})
        fonts = collect_fonts(spec)
        assert ("Inter", "Regular") in fonts

    def test_ignores_non_text(self):
        spec = _make_spec({"frame-1": {"type": "button"}})
        fonts = collect_fonts(spec)
        assert fonts == []

    def test_deduplicates(self):
        spec = _make_spec({
            "text-1": {"type": "text", "style": {"fontFamily": "Inter", "fontWeight": 400}},
            "text-2": {"type": "heading", "style": {"fontFamily": "Inter", "fontWeight": 400}},
        })
        fonts = collect_fonts(spec)
        assert len(fonts) == 1


# ---------------------------------------------------------------------------
# Steps 2-4: Script generation tests
# ---------------------------------------------------------------------------

class TestGenerateFigmaScript:
    """Verify full Figma script generation from CompositionSpec."""

    def test_script_shape(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "vertical", "sizing": {"width": 428, "height": 926}},
        }})
        script, refs = generate_figma_script(spec)
        assert "const M = {};" in script
        assert "return M;" in script
        assert "(async" not in script

    def test_creates_frame(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "vertical"},
        }})
        script, _ = generate_figma_script(spec)
        assert "figma.createFrame()" in script

    def test_sets_layout_mode(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "horizontal"},
        }})
        script, _ = generate_figma_script(spec)
        assert 'layoutMode = "HORIZONTAL"' in script

    def test_vertical_layout(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "vertical"},
        }})
        script, _ = generate_figma_script(spec)
        assert 'layoutMode = "VERTICAL"' in script

    def test_stacked_no_layout_mode(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "stacked"},
        }})
        script, _ = generate_figma_script(spec)
        assert "layoutMode" not in script

    def test_gap(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "vertical", "gap": 16},
        }})
        script, _ = generate_figma_script(spec)
        assert "itemSpacing = 16" in script

    def test_padding(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "vertical", "padding": {"top": 8, "right": 16}},
        }})
        script, _ = generate_figma_script(spec)
        assert "paddingTop = 8" in script
        assert "paddingRight = 16" in script

    def test_fill_sizing(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["card-1"],
            },
            "card-1": {
                "type": "card",
                "layout": {"direction": "vertical", "sizing": {"width": "fill"}},
            },
        })
        script, _ = generate_figma_script(spec)
        assert 'layoutSizingHorizontal = "FILL"' in script

    def test_no_visual_output_without_db_visuals(self):
        spec = _make_spec({"screen-1": {"type": "screen"}})
        script, _ = generate_figma_script(spec, db_visuals=None)
        # fills = [] is OK (clears default white), but no actual fill data
        assert "SOLID" not in script

    def test_text_node_creation(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"}, "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}},
        })
        script, _ = generate_figma_script(spec)
        assert "figma.createText()" in script
        assert 'characters = "Hello"' in script

    def test_heading_uses_create_text(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["h-1"]},
            "h-1": {"type": "heading", "props": {"text": "Title"}},
        })
        script, _ = generate_figma_script(spec)
        assert "figma.createText()" in script

    def test_text_nodes_use_auto_resize_and_fill(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"}, "children": ["t-1"]},
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        script, _ = generate_figma_script(spec)
        assert "textAutoResize" in script
        assert 'layoutSizingHorizontal = "FILL"' in script

    def test_card_fills_parent_width_in_vertical_layout(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"}, "children": ["card-1"]},
            "card-1": {"type": "card", "layout": {"direction": "vertical"}},
        })
        script, _ = generate_figma_script(spec)
        assert 'layoutSizingHorizontal = "FILL"' in script

    def test_container_types_fill_parent_width(self):
        for container_type in ["card", "accordion", "header", "search_input", "tabs", "drawer"]:
            spec = _make_spec({
                "screen-1": {"type": "screen", "layout": {"direction": "vertical"}, "children": ["c-1"]},
                "c-1": {"type": container_type, "layout": {"direction": "vertical"}},
            })
            script, _ = generate_figma_script(spec)
            fill_count = script.count('layoutSizingHorizontal = "FILL"')
            assert fill_count >= 1, f"{container_type} should get FILL width but didn't"

    def test_mode1_card_instance_fills_parent_width(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"}, "children": ["card-1"]},
            "card-1": {"type": "card"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "card-1": -2}
        visuals = {
            -1: {"fills": None, "strokes": None, "effects": None, "corner_radius": None,
                 "opacity": None, "stroke_weight": None, "component_key": None,
                 "component_figma_id": None, "bindings": []},
            -2: {"fills": None, "strokes": None, "effects": None, "corner_radius": None,
                 "opacity": None, "stroke_weight": None, "component_key": "abc123",
                 "component_figma_id": "1:234", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=visuals)
        assert "getNodeByIdAsync" in script
        assert 'layoutSizingHorizontal = "FILL"' in script

    def test_button_does_not_fill_parent_width(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"}, "children": ["b-1"]},
            "b-1": {"type": "button", "layout": {"direction": "horizontal"}},
        })
        script, _ = generate_figma_script(spec)
        assert 'layoutSizingHorizontal = "FILL"' not in script

    def test_font_loading(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["t-1"]},
            "t-1": {"type": "text", "style": {"fontFamily": "Inter", "fontWeight": 700}},
        })
        script, _ = generate_figma_script(spec)
        assert "figma.loadFontAsync" in script
        assert '"Inter"' in script
        assert '"Bold"' in script

    def test_children_appended_in_order(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"},
                         "children": ["a-1", "b-1"]},
            "a-1": {"type": "button"},
            "b-1": {"type": "card"},
        })
        script, _ = generate_figma_script(spec)
        # a-1 appended before b-1
        a_pos = script.index("a-1")
        b_pos = script.index("b-1")
        assert a_pos < b_pos

    def test_root_appended_to_page(self):
        spec = _make_spec({"screen-1": {"type": "screen"}})
        script, _ = generate_figma_script(spec)
        assert "figma.currentPage.appendChild" in script

    def test_token_ref_collected_via_db_visuals(self):
        spec = _make_spec(
            elements={"screen-1": {"type": "screen"}},
            tokens={"color.primary": "#FF0000"},
        )
        spec["_node_id_map"] = {"screen-1": 10}
        db_visuals = {
            10: {
                "fills": json.dumps([{"type": "SOLID", "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}}]),
                "bindings": [{"property": "fill.0.color", "token_name": "color.primary", "resolved_value": "#FF0000"}],
            },
        }
        script, refs = generate_figma_script(spec, db_visuals=db_visuals)
        assert len(refs) >= 1
        assert any(r[2] == "color.primary" for r in refs)

    def test_token_ref_in_gap_collected(self):
        spec = _make_spec(
            elements={
                "screen-1": {"type": "screen", "layout": {"direction": "vertical", "gap": "{space.s16}"}},
            },
            tokens={"space.s16": 16},
        )
        script, refs = generate_figma_script(spec)
        assert "itemSpacing = 16" in script
        assert any(r[2] == "space.s16" for r in refs)

    def test_names_elements(self):
        spec = _make_spec({"my-button-1": {"type": "button"}})
        script, _ = generate_figma_script(spec)
        assert '"my-button-1"' in script

    def test_resize_for_numeric_sizing(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "vertical", "sizing": {"width": 428, "height": 926}},
        }})
        script, _ = generate_figma_script(spec)
        assert "resize(428, 926)" in script

    def test_resize_for_fixed_child(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"},
                         "children": ["card-1"]},
            "card-1": {"type": "card", "layout": {
                "direction": "vertical", "sizing": {"width": 200, "height": 100},
            }},
        })
        script, _ = generate_figma_script(spec)
        assert "resize(200, 100)" in script

    def test_no_resize_for_fill_child(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"},
                         "children": ["card-1"]},
            "card-1": {"type": "card", "layout": {
                "direction": "vertical", "sizing": {"width": "fill", "height": "hug"},
            }},
        })
        script, _ = generate_figma_script(spec)
        # Should have layoutSizing but NOT resize
        assert "FILL" in script
        assert "HUG" in script
        # Only the root might have resize, not the child
        lines = script.split("\n")
        card_lines = [l for l in lines if "card-1" in l or (lines.index(l) > 0 and "n1." in l)]
        assert not any("resize" in l for l in card_lines)

    def test_fixed_child_gets_fixed_sizing_mode(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"},
                         "children": ["btn-1"]},
            "btn-1": {"type": "button", "layout": {
                "direction": "horizontal", "sizing": {"width": 200, "height": 48},
            }},
        })
        script, _ = generate_figma_script(spec)
        assert 'layoutSizingHorizontal = "FIXED"' in script
        assert 'layoutSizingVertical = "FIXED"' in script
        assert "resize(200, 48)" in script

    def test_stacked_child_resize_no_layout_mode(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"},
                         "children": ["icon-1"]},
            "icon-1": {"type": "icon", "layout": {
                "direction": "stacked", "sizing": {"width": 24, "height": 24},
            }},
        })
        script, _ = generate_figma_script(spec)
        assert "resize(24, 24)" in script
        # icon-1 should NOT have layoutMode
        lines = script.split("\n")
        icon_start = next(i for i, l in enumerate(lines) if "icon-1" in l)
        icon_lines = []
        for i in range(icon_start, len(lines)):
            if lines[i].startswith("M[") and "icon-1" in lines[i]:
                break
            icon_lines.append(lines[i])
        assert not any("layoutMode" in l for l in icon_lines)

    def test_resize_with_fixed_width_hug_height(self):
        """When width is FIXED (pixel) and height is HUG, resize should use
        the pixel width and preserve the current height, not force height to 1."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"},
                         "children": ["row-1"]},
            "row-1": {"type": "frame", "layout": {
                "direction": "horizontal", "sizing": {"width": 394, "height": "hug"},
            }},
        })
        script, _ = generate_figma_script(spec)
        # Should NOT contain resize(394, 1) — that forces height to 1px
        assert "resize(394, 1)" not in script
        # Should resize width only, preserving current height
        assert "resize(394, " in script

    def test_resize_with_hug_width_fixed_height(self):
        """When width is HUG and height is FIXED, resize should preserve width."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"},
                         "children": ["col-1"]},
            "col-1": {"type": "frame", "layout": {
                "direction": "vertical", "sizing": {"width": "hug", "height": 300},
            }},
        })
        script, _ = generate_figma_script(spec)
        assert "resize(1, " not in script  # should not force width to 1

    def test_escapes_text_quotes(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["t-1"]},
            "t-1": {"type": "text", "props": {"text": 'He said "hello"'}},
        })
        script, _ = generate_figma_script(spec)
        assert '\\"hello\\"' in script


# ---------------------------------------------------------------------------
# DB-path script generation (Phase 1)
# ---------------------------------------------------------------------------

class TestGenerateFigmaScriptFromDB:
    """Verify generate_figma_script with db_visuals reads visual data from DB."""

    def test_fills_from_db_visuals(self):
        spec = _make_spec({"screen-1": {"type": "screen"}})
        spec["_node_id_map"] = {"screen-1": 10}
        db_visuals = {
            10: {
                "fills": json.dumps([{"type": "SOLID", "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}}]),
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "fills = [{" in script
        assert '"SOLID"' in script

    def test_strokes_from_db_visuals(self):
        spec = _make_spec({"screen-1": {"type": "screen"}})
        spec["_node_id_map"] = {"screen-1": 10}
        db_visuals = {
            10: {
                "strokes": json.dumps([{"type": "SOLID", "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0}}]),
                "stroke_weight": 2,
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "strokes = [{" in script
        assert "strokeWeight = 2" in script

    def test_effects_from_db_visuals(self):
        spec = _make_spec({"screen-1": {"type": "screen"}})
        spec["_node_id_map"] = {"screen-1": 10}
        db_visuals = {
            10: {
                "effects": json.dumps([{"type": "BACKGROUND_BLUR", "visible": True, "radius": 15.0}]),
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "effects = [{" in script
        assert "BACKGROUND_BLUR" in script

    def test_token_ref_collected_from_db_path(self):
        spec = _make_spec(
            elements={"screen-1": {"type": "screen"}},
            tokens={"color.primary": "#FF0000"},
        )
        spec["_node_id_map"] = {"screen-1": 10}
        db_visuals = {
            10: {
                "fills": json.dumps([{"type": "SOLID", "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}}]),
                "bindings": [{"property": "fill.0.color", "token_name": "color.primary", "resolved_value": "#FF0000"}],
            },
        }
        script, refs = generate_figma_script(spec, db_visuals=db_visuals)
        assert any(r[2] == "color.primary" for r in refs)

    def test_falls_back_to_empty_when_node_not_in_visuals(self):
        spec = _make_spec({"screen-1": {"type": "screen"}})
        spec["_node_id_map"] = {"screen-1": 10}
        db_visuals = {}  # node 10 not present
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "SOLID" not in script

    def test_none_db_visuals_produces_no_visual_output(self):
        spec = _make_spec({"screen-1": {"type": "screen"}})
        script, _ = generate_figma_script(spec, db_visuals=None)
        assert "SOLID" not in script

    def test_mode1_emits_import_component(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc123", "component_figma_id": "123:456", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "getNodeByIdAsync" in script
        assert '"123:456"' in script
        assert "createInstance()" in script

    def test_mode1_skips_layout_and_visual(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button", "layout": {"direction": "horizontal", "gap": 10}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "component_key": "abc123",
                "component_figma_id": "123:456",
                "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0, "a": 1}}]),
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        lines = script.split("\n")
        button_lines = [l for l in lines if "button-1" in l or ("n1" in l and "n1." in l)]
        # Mode 1 should NOT have layoutMode or fills
        assert not any("layoutMode" in l for l in button_lines)
        assert not any("fills" in l for l in button_lines)

    def test_mode1_children_skipped(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button", "children": ["icon-1"]},
            "icon-1": {"type": "icon"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2, "icon-1": -3}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc123", "component_figma_id": "123:456", "bindings": []},
            -3: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert '"icon-1"' not in script

    def test_mode1_text_override(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button", "props": {"text": "Save Changes"}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc123", "component_figma_id": "123:456", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "Save Changes" in script
        assert "findOne" in script
        assert "loadFontAsync" in script

    def test_mode1_no_text_override_when_no_props(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc123", "component_figma_id": "123:456", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "findOne" not in script

    def test_mode1_text_override_targets_title_or_label_first(self):
        """Text override should try to find a TEXT named Title/Label before
        falling back to any TEXT node."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["header-1"]},
            "header-1": {"type": "header", "props": {"text": "Settings"}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc123", "component_figma_id": "1835:155037", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "Settings" in script
        # Should try name-based search first, then fall back
        assert "Title" in script or "Label" in script or "title" in script
        assert "findOne" in script

    def test_mode1_text_override_with_explicit_text_target(self):
        """When props include text_target, the override finds that named node."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["header-1"]},
            "header-1": {"type": "header", "props": {"text": "Settings", "text_target": "Title"}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc123", "component_figma_id": "123:456", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "Settings" in script
        assert '"Title"' in script

    def test_mode1_subtitle_override(self):
        """When props include subtitle, a second text override targets Subtitle nodes."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["header-1"]},
            "header-1": {"type": "header", "props": {"text": "Settings", "subtitle": "Account preferences"}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc123", "component_figma_id": "123:456", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "Settings" in script
        assert "Account preferences" in script

    def test_page_name_finds_or_creates_page(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["card-1"]},
            "card-1": {"type": "card"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "card-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals, page_name="Generated")
        assert "figma.root.children.find" in script
        assert "figma.createPage()" in script
        assert '"Generated"' in script
        assert "setCurrentPageAsync" in script
        assert "figma.currentPage.appendChild" not in script

    def test_no_page_name_uses_current_page(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["card-1"]},
            "card-1": {"type": "card"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "card-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "figma.currentPage.appendChild" in script
        assert "figma.createPage()" not in script

    def test_mode2_still_creates_frame(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["card-1"]},
            "card-1": {"type": "card"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "card-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": None, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "figma.createFrame()" in script
        assert "importComponentByKeyAsync" not in script

    def test_composition_children_emit_instances(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["toolbar-1"]},
            "toolbar-1": {
                "type": "container",
                "_composition": [
                    {"child_type": "button", "count_mode": 3,
                     "component_key": None, "component_figma_id": "123:456", "frequency": 0.95},
                ],
            },
        })
        spec["_node_id_map"] = {"screen-1": -1, "toolbar-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": None, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert script.count("getNodeByIdAsync") == 3
        assert script.count("createInstance()") == 3
        assert script.count("appendChild") >= 3

    def test_composition_children_not_emitted_for_mode1(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["header-1"]},
            "header-1": {
                "type": "header",
                "_composition": [
                    {"child_type": "container", "count_mode": 3,
                     "component_key": None, "frequency": 0.9},
                ],
            },
        })
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc123", "component_figma_id": "789:012", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # Mode 1 element should NOT emit composition children (inherited from master)
        assert script.count("getNodeByIdAsync") == 1  # just the header itself

    def test_composition_children_skipped_when_ir_has_children(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["card-1"]},
            "card-1": {
                "type": "card",
                "children": ["heading-1"],
                "_composition": [
                    {"child_type": "container", "count_mode": 2,
                     "component_key": None, "frequency": 0.8},
                ],
            },
            "heading-1": {"type": "heading", "props": {"text": "Title"}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "card-1": -2, "heading-1": -3}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": None, "bindings": []},
            -3: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "container-child" not in script
        assert "Title" in script

    def test_composition_keyless_children_create_frames(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["card-1"]},
            "card-1": {
                "type": "card",
                "_composition": [
                    {"child_type": "container", "count_mode": 2,
                     "component_key": None, "frequency": 0.8},
                ],
            },
        })
        spec["_node_id_map"] = {"screen-1": -1, "card-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": None, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # card-1 is Mode 2 (no key), its 2 keyless children should create frames
        frame_count = script.count("figma.createFrame()")
        assert frame_count >= 3  # screen + card + 2 children (screen doesn't create frame directly)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Steps 5+6: Orchestrator + CLI tests
# ---------------------------------------------------------------------------

def _seed_gen_screen(db: sqlite3.Connection) -> None:
    """Insert classified screen data for generation tests."""
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

    nodes = [
        (10, 1, "h1", "nav/top-nav", "INSTANCE", 1, 0, 0, 0, 428, 56, "HORIZONTAL"),
        (11, 1, "t1", "Page Title", "TEXT", 2, 0, 16, 70, 396, 28, None),
    ]
    db.executemany(
        "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
        "x, y, width, height, layout_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        nodes,
    )
    db.execute("UPDATE nodes SET font_size = 24, font_weight = 700 WHERE id = 11")

    db.execute(
        "INSERT INTO screen_component_instances "
        "(screen_id, node_id, canonical_type, confidence, classification_source) "
        "VALUES (1, 10, 'header', 1.0, 'formal')"
    )
    db.execute(
        "INSERT INTO screen_component_instances "
        "(screen_id, node_id, canonical_type, confidence, classification_source) "
        "VALUES (1, 11, 'heading', 0.9, 'heuristic')"
    )
    db.execute(
        "INSERT INTO node_token_bindings (id, node_id, property, token_id, raw_value, resolved_value, binding_status) "
        "VALUES (1, 10, 'fill.0.color', 1, '#FAFAFA', '#FAFAFA', 'bound')"
    )
    db.commit()


class TestGenerateScreen:
    """Verify generate_screen() produces a complete manifest."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_gen_screen(conn)
        yield conn
        conn.close()

    def test_returns_manifest(self, db: sqlite3.Connection):
        result = generate_screen(db, screen_id=1)
        assert "structure_script" in result
        assert "token_refs" in result
        assert isinstance(result["structure_script"], str)

    def test_script_has_return(self, db: sqlite3.Connection):
        result = generate_screen(db, screen_id=1)
        assert "return M;" in result["structure_script"]
        assert "figma.createFrame()" in result["structure_script"]

    def test_has_element_count(self, db: sqlite3.Connection):
        result = generate_screen(db, screen_id=1)
        assert result["element_count"] >= 2  # header + heading at minimum

    def test_returns_token_variables(self, db: sqlite3.Connection):
        result = generate_screen(db, screen_id=1)
        assert "token_variables" in result
        assert isinstance(result["token_variables"], dict)

    def test_build_rebind_script_from_result(self, db: sqlite3.Connection):
        from dd.renderers.figma import build_rebind_script_from_result

        result = generate_screen(db, screen_id=1)
        # Simulate Figma returning M dict
        figma_node_map = {"header-1": "999:1", "heading-1": "999:2"}
        rebind_script = build_rebind_script_from_result(result, figma_node_map)
        # Should produce a script (may be empty if no token refs match)
        assert isinstance(rebind_script, str)


class TestGenerateCLI:
    """Verify generate CLI command."""

    def test_generate_command(self, tmp_path):
        db_path = str(tmp_path / "test.declarative.db")
        conn = init_db(db_path)
        _seed_gen_screen(conn)
        conn.close()

        from dd.cli import main
        main(["generate", "--db", db_path, "--screen", "1"])


# ---------------------------------------------------------------------------
# build_visual_from_db tests
# ---------------------------------------------------------------------------

SOLID_FILL_JSON = json.dumps([{
    "type": "SOLID", "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0},
    "opacity": 1.0,
}])

STROKE_JSON = json.dumps([{
    "type": "SOLID", "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0},
}])

EFFECT_JSON = json.dumps([{
    "type": "DROP_SHADOW", "visible": True,
    "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.25},
    "offset": {"x": 0.0, "y": 4.0}, "radius": 8.0, "spread": 0.0,
}])


class TestBuildVisualFromDB:
    """Verify build_visual_from_db normalizes raw DB data to _emit_visual format."""

    def test_normalizes_fills(self):
        raw = {"fills": SOLID_FILL_JSON, "bindings": []}
        visual = build_visual_from_db(raw)
        assert "fills" in visual
        assert visual["fills"][0]["type"] == "solid"
        assert visual["fills"][0]["color"] == "#FF0000"

    def test_normalizes_strokes(self):
        raw = {"strokes": STROKE_JSON, "stroke_weight": 2, "bindings": []}
        visual = build_visual_from_db(raw)
        assert "strokes" in visual
        assert visual["strokes"][0]["type"] == "solid"
        assert visual["strokes"][0]["width"] == 2

    def test_normalizes_effects(self):
        raw = {"effects": EFFECT_JSON, "bindings": []}
        visual = build_visual_from_db(raw)
        assert "effects" in visual
        assert visual["effects"][0]["type"] == "drop-shadow"
        assert visual["effects"][0]["blur"] == 8.0

    def test_normalizes_corner_radius(self):
        raw = {"corner_radius": "12", "bindings": []}
        visual = build_visual_from_db(raw)
        assert visual["cornerRadius"] == 12.0

    def test_normalizes_opacity(self):
        raw = {"opacity": 0.5, "bindings": []}
        visual = build_visual_from_db(raw)
        assert visual["opacity"] == 0.5

    def test_omits_full_opacity(self):
        raw = {"opacity": 1.0, "bindings": []}
        visual = build_visual_from_db(raw)
        assert "opacity" not in visual

    def test_token_bound_fill(self):
        raw = {
            "fills": SOLID_FILL_JSON,
            "bindings": [{"property": "fill.0.color", "token_name": "color.primary", "resolved_value": "#FF0000"}],
        }
        visual = build_visual_from_db(raw)
        assert visual["fills"][0]["color"] == "{color.primary}"

    def test_empty_input(self):
        visual = build_visual_from_db({})
        assert visual == {}

    def test_combined_visual_properties(self):
        bindings = [{"property": "fill.0.color", "token_name": "color.primary", "resolved_value": "#FF0000"}]
        node = {
            "fills": SOLID_FILL_JSON,
            "strokes": STROKE_JSON,
            "effects": EFFECT_JSON,
            "corner_radius": "8",
            "opacity": 0.9,
            "stroke_weight": 2,
            "bindings": bindings,
        }
        visual = build_visual_from_db(node)
        assert visual["fills"][0]["color"] == "{color.primary}"
        assert visual["strokes"][0]["width"] == 2
        assert visual["effects"][0]["type"] == "drop-shadow"
        assert visual["cornerRadius"] == 8.0
        assert visual["opacity"] == 0.9

    # --- font data ---

    def test_font_data_in_visual(self):
        visual = build_visual_from_db({
            "font_family": "Inter Variable", "font_size": 16.0,
            "font_weight": 600, "font_style": "Regular",
            "line_height": '{"unit": "AUTO"}', "letter_spacing": None,
            "text_align": "LEFT", "bindings": [],
        })
        assert visual["font"]["font_family"] == "Inter Variable"
        assert visual["font"]["font_size"] == 16.0
        assert visual["font"]["font_weight"] == 600

    def test_no_font_data_when_absent(self):
        visual = build_visual_from_db({"bindings": []})
        assert "font" not in visual

    # --- clipsContent ---

    def test_clips_content_truthy(self):
        visual = build_visual_from_db({"clips_content": 1, "bindings": []})
        assert visual["clipsContent"] is True

    def test_clips_content_absent_when_null(self):
        visual = build_visual_from_db({"clips_content": None, "bindings": []})
        assert "clipsContent" not in visual

    def test_clips_content_false_when_zero(self):
        visual = build_visual_from_db({"clips_content": 0, "bindings": []})
        assert visual["clipsContent"] is False

    # --- rotation ---

    def test_rotation_nonzero_stores_radians(self):
        import math
        visual = build_visual_from_db({"rotation": math.radians(45), "bindings": []})
        assert abs(visual["rotation"] - math.radians(45)) < 0.001

    def test_rotation_excluded_when_zero(self):
        visual = build_visual_from_db({"rotation": 0, "bindings": []})
        assert "rotation" not in visual

    def test_rotation_excluded_when_none(self):
        visual = build_visual_from_db({"rotation": None, "bindings": []})
        assert "rotation" not in visual

    # --- constraints ---

    def test_constraints_both_axes(self):
        visual = build_visual_from_db({
            "constraint_h": "SCALE", "constraint_v": "TOP", "bindings": [],
        })
        assert visual["constraints"] == {"horizontal": "SCALE", "vertical": "TOP"}

    def test_constraints_horizontal_only(self):
        visual = build_visual_from_db({
            "constraint_h": "CENTER", "constraint_v": None, "bindings": [],
        })
        assert visual["constraints"] == {"horizontal": "CENTER"}

    def test_constraints_absent_when_both_null(self):
        visual = build_visual_from_db({
            "constraint_h": None, "constraint_v": None, "bindings": [],
        })
        assert "constraints" not in visual


class TestEmitVisualAdditiveProperties:
    """Verify _emit_visual emits clipsContent, rotation, and constraints."""

    def test_emit_clips_content(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"clips_content": 1, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "clipsContent = true" in script

    def test_emit_rotation(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"rotation": __import__('math').radians(45), "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # REST API +rad (CCW) → Plugin API negative degrees (CW convention)
        assert "rotation = -45.0" in script or "rotation = -44.99" in script

    def test_no_rotation_when_zero(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"rotation": 0, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "rotation" not in script

    def test_rotation_sign_negated_for_plugin_api(self):
        """REST API positive radians (CCW) must become negative degrees (CW) for Plugin API."""
        import math
        # REST API stores +π/2 rad (CCW) → Plugin API expects -90° (CW)
        assert float(format_js_value(math.pi / 2, "number_radians")) == pytest.approx(-90.0)
        # REST API stores -π/2 rad (CW) → Plugin API expects +90° (CW)
        assert float(format_js_value(-math.pi / 2, "number_radians")) == pytest.approx(90.0)
        # REST API stores +π rad → Plugin API expects -180°
        assert float(format_js_value(math.pi, "number_radians")) == pytest.approx(-180.0)
        # REST API stores -π/4 rad → Plugin API expects +45°
        assert float(format_js_value(-math.pi / 4, "number_radians")) == pytest.approx(45.0)

    def test_emit_constraints(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"constraint_h": "SCALE", "constraint_v": "TOP", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "constraints" in script
        assert "SCALE" in script
        # TOP maps to MIN in Plugin API
        assert "MIN" in script

    def test_no_constraints_when_null(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "constraints" not in script

    def test_mode2_text_uses_font_from_visual(self):
        """Mode 2 text elements should use font data from db_visuals."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "bindings": [],
                "font": {
                    "font_family": "Inter Variable",
                    "font_size": 16.0,
                    "font_weight": 600,
                },
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert '"Inter"' in script  # Inter Variable normalized to Inter
        assert '"Semi Bold"' in script  # weight 600 → Semi Bold
        assert "fontSize = 16" in script

    def test_mode2_text_defaults_when_no_font(self):
        """Mode 2 text without font data should use Inter Regular."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert '"Inter"' in script
        assert '"Regular"' in script


class TestVisibilityOverrides:
    """Verify Mode 1 instances emit visibility overrides for hidden children."""

    def test_mode1_hides_children(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["header-1"]},
            "header-1": {"type": "header"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "component_key": "abc123",
                "component_figma_id": "123:456",
                "bindings": [],
                "hidden_children": [
                    {"name": "Title"},
                    {"name": "Titles"},
                ],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'n.name === "Title"' in script
        assert 'n.name === "Titles"' in script
        assert ".visible = false" in script

    def test_mode1_no_visibility_when_all_visible(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["header-1"]},
            "header-1": {"type": "header"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc123", "component_figma_id": "123:456", "bindings": [], "hidden_children": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert ".visible = false" not in script

    def test_mode1_no_visibility_when_no_key(self):
        """Mode 2 elements don't get visibility overrides."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["card-1"]},
            "card-1": {"type": "card"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "card-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": [], "hidden_children": [{"name": "Divider"}]},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert ".visible = false" not in script

    def test_mode1_escapes_child_names(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["header-1"]},
            "header-1": {"type": "header"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "component_key": "abc123",
                "component_figma_id": "123:456",
                "bindings": [],
                "hidden_children": [{"name": 'icon/back "test"'}],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'icon/back \\"test\\"' in script


class TestAbsolutePositioning:
    """Verify renderer handles absolute positioning (direction='absolute')."""

    def test_absolute_root_no_layout_mode(self):
        """Absolute root should NOT emit layoutMode."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
                "children": ["card-1"],
            },
            "card-1": {"type": "card"},
        })
        script, _ = generate_figma_script(spec)
        root_lines = [l for l in script.split("\n") if "n0." in l and "layoutMode" in l]
        assert len(root_lines) == 0

    def test_absolute_children_get_xy(self):
        """Children under absolute parent get x/y positioning."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
                "children": ["header-1"],
            },
            "header-1": {
                "type": "header",
                "layout": {"position": {"x": 0, "y": 0}, "sizing": {"width": 428, "height": 111}},
            },
        })
        script, _ = generate_figma_script(spec)
        assert ".x = 0;" in script
        assert ".y = 0;" in script

    def test_absolute_children_no_fill_width(self):
        """FILL_WIDTH_TYPES should NOT get FILL under absolute parent."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
                "children": ["card-1"],
            },
            "card-1": {
                "type": "card",
                "layout": {"position": {"x": 0, "y": 100}, "sizing": {"width": 428, "height": 200}},
            },
        })
        script, _ = generate_figma_script(spec)
        assert 'layoutSizingHorizontal = "FILL"' not in script

    def test_absolute_root_still_resizes(self):
        """Absolute root should still get resize()."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
            },
        })
        script, _ = generate_figma_script(spec)
        assert "resize(428, 926)" in script

    def test_absolute_root_with_clips_content(self):
        """Absolute root with clipsContent from db_visuals."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
            },
        })
        spec["_node_id_map"] = {"screen-1": -1}
        db_visuals = {-1: {"clips_content": 1, "bindings": []}}
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "clipsContent = true" in script

    def test_mixed_absolute_root_autolayout_children(self):
        """Absolute root with auto-layout children (children have their own direction)."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
                "children": ["card-1"],
            },
            "card-1": {
                "type": "card",
                "layout": {
                    "direction": "vertical",
                    "position": {"x": 0, "y": 100},
                    "sizing": {"width": 400, "height": 200},
                },
                "children": ["text-1"],
            },
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        script, _ = generate_figma_script(spec)
        # Root has no layoutMode
        lines = script.split("\n")
        n0_lines = [l for l in lines if l.startswith("n0.") and "layoutMode" in l]
        assert len(n0_lines) == 0
        # Card has layoutMode VERTICAL
        assert 'layoutMode = "VERTICAL"' in script
        # Card has x/y positioning
        assert ".x = 0;" in script
        assert ".y = 100;" in script

    def test_autolayout_root_still_applies_fill(self):
        """Existing behavior: vertical root still applies FILL width to cards."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical", "sizing": {"width": 428, "height": 926}},
                "children": ["card-1"],
            },
            "card-1": {"type": "card", "layout": {"direction": "vertical"}},
        })
        script, _ = generate_figma_script(spec)
        assert 'layoutSizingHorizontal = "FILL"' in script


# ---------------------------------------------------------------------------
# Phase 3: Node type dispatch, recursive skip, original names
# ---------------------------------------------------------------------------

class TestNodeTypeDispatch:
    """Verify the generator creates the correct Figma element for each node type."""

    def test_rectangle_creates_rectangle(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["rectangle-1"],
            },
            "rectangle-1": {
                "type": "rectangle",
                "layout": {"sizing": {"width": 50, "height": 50}},
            },
        })
        script, _ = generate_figma_script(spec)
        assert "figma.createRectangle()" in script

    def test_ellipse_creates_ellipse(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["ellipse-1"],
            },
            "ellipse-1": {
                "type": "ellipse",
                "layout": {"sizing": {"width": 50, "height": 50}},
            },
        })
        script, _ = generate_figma_script(spec)
        assert "figma.createEllipse()" in script

    def test_vector_type_skipped(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["vector-1"],
            },
            "vector-1": {
                "type": "vector",
                "layout": {"sizing": {"width": 20, "height": 20}},
            },
        })
        script, _ = generate_figma_script(spec)
        assert "vector" not in script.lower() or "createVector" not in script

    def test_group_type_skipped(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["group-1"],
            },
            "group-1": {
                "type": "group",
                "layout": {},
            },
        })
        script, _ = generate_figma_script(spec)
        assert "createFrame" not in script or 'name = "group' not in script


class TestRecursiveMode1Skip:
    """Verify Mode 1 instances skip ALL descendants, not just direct children."""

    def test_mode1_skips_grandchildren(self):
        spec = {
            "version": "1.0",
            "root": "screen-1",
            "tokens": {},
            "elements": {
                "screen-1": {
                    "type": "screen",
                    "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
                    "children": ["instance-1"],
                },
                "instance-1": {
                    "type": "instance",
                    "layout": {},
                    "children": ["child-1"],
                },
                "child-1": {
                    "type": "frame",
                    "layout": {},
                    "children": ["grandchild-1"],
                },
                "grandchild-1": {
                    "type": "text",
                    "layout": {},
                    "style": {},
                    "props": {"text": "should not appear"},
                },
            },
            "_node_id_map": {"instance-1": 100, "child-1": 101, "grandchild-1": 102},
        }
        db_visuals = {
            100: {"component_key": "abc123", "component_figma_id": "1:234", "bindings": [], "visible": 1},
            101: {"bindings": [], "visible": 1},
            102: {"bindings": [], "visible": 1},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'getNodeByIdAsync("1:234")' in script
        assert "should not appear" not in script


class TestOriginalNames:
    """Verify the generator uses _original_name for Figma layer names."""

    def test_original_name_in_script(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["frame-1"],
            },
            "frame-1": {
                "type": "frame",
                "layout": {},
                "_original_name": "Content Area",
            },
        })
        script, _ = generate_figma_script(spec)
        assert '"Content Area"' in script

    def test_falls_back_to_element_id(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["frame-1"],
            },
            "frame-1": {
                "type": "frame",
                "layout": {},
            },
        })
        script, _ = generate_figma_script(spec)
        assert '"frame-1"' in script


class TestTextAutoResize:
    """Verify text nodes use stored textAutoResize from DB instead of hardcoding."""

    def test_uses_db_text_auto_resize_height(self):
        """When DB has text_auto_resize=HEIGHT, script should emit HEIGHT not WIDTH_AND_HEIGHT."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["t-1"],
            },
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "t-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": [], "text_auto_resize": "HEIGHT"},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'textAutoResize = "HEIGHT"' in script
        assert 'textAutoResize = "WIDTH_AND_HEIGHT"' not in script

    def test_uses_db_text_auto_resize_none(self):
        """When DB has text_auto_resize=NONE, the text box is fixed-size."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["t-1"],
            },
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "t-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": [], "text_auto_resize": "NONE"},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'textAutoResize = "NONE"' in script
        assert 'textAutoResize = "WIDTH_AND_HEIGHT"' not in script

    def test_uses_db_text_auto_resize_truncate(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["t-1"],
            },
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "t-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": [], "text_auto_resize": "TRUNCATE"},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'textAutoResize = "TRUNCATE"' in script

    def test_defaults_to_width_and_height_when_no_db_visuals(self):
        """Without db_visuals, should default to WIDTH_AND_HEIGHT for safety."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["t-1"],
            },
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        script, _ = generate_figma_script(spec, db_visuals=None)
        assert 'textAutoResize = "WIDTH_AND_HEIGHT"' in script

    def test_defaults_to_width_and_height_when_null_in_db(self):
        """When DB has text_auto_resize=None, should default to WIDTH_AND_HEIGHT."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["t-1"],
            },
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "t-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": [], "text_auto_resize": None},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'textAutoResize = "WIDTH_AND_HEIGHT"' in script


class TestLayoutSizingFromDB:
    """Verify text nodes use DB layout_sizing_h instead of hardcoded FILL."""

    def test_text_uses_hug_from_db(self):
        """When DB has layout_sizing_h=HUG, text should get HUG not FILL."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["t-1"],
            },
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "t-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": [], "layout_sizing_h": "HUG"},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'layoutSizingHorizontal = "HUG"' in script
        assert 'layoutSizingHorizontal = "FILL"' not in script

    def test_text_uses_fixed_from_db(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["t-1"],
            },
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "t-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": [], "layout_sizing_h": "FIXED"},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'layoutSizingHorizontal = "FIXED"' in script
        assert 'layoutSizingHorizontal = "FILL"' not in script

    def test_text_defaults_to_fill_when_null(self):
        """When DB has no layout_sizing_h, text should fall back to FILL."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["t-1"],
            },
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "t-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'layoutSizingHorizontal = "FILL"' in script

    def test_layout_sizing_override_on_instance(self):
        """LAYOUT_SIZING_H override should set layoutSizingHorizontal on child."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["btn-1"],
            },
            "btn-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": 1, "btn-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {
                "component_key": "abc",
                "component_figma_id": "123:456",
                "bindings": [],
                "instance_overrides": [{
                    "target": ";1334:005",
                    "property": "layoutSizingHorizontal",
                    "value": "HUG",
                }],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'layoutSizingHorizontal = "HUG"' in script

    def test_layout_sizing_v_override_on_instance(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["btn-1"],
            },
            "btn-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": 1, "btn-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {
                "component_key": "abc",
                "component_figma_id": "123:456",
                "bindings": [],
                "instance_overrides": [{
                    "target": ";1334:005",
                    "property": "layoutSizingVertical",
                    "value": "FILL",
                }],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'layoutSizingVertical = "FILL"' in script


class TestDefaultFillClearing:
    """Verify transparent frames don't inherit Figma's default white fill."""

    def test_frame_without_fills_gets_empty_fills(self):
        """A frame with no fills in DB should get fills=[] to clear default white."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["f-1"],
            },
            "f-1": {"type": "frame", "layout": {"direction": "vertical"}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "f-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": []},  # no fills key
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # The frame n1 (f-1) should get fills = [] to clear default
        lines = script.split("\n")
        f1_lines = [l for l in lines if "n1." in l]
        assert any("fills = []" in l for l in f1_lines), (
            f"Expected fills=[] to clear default white fill, got: {f1_lines}"
        )

    def test_frame_with_fills_not_cleared(self):
        """A frame with actual fills should NOT get fills=[] on that node."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["f-1"],
            },
            "f-1": {"type": "frame", "layout": {"direction": "vertical"}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "f-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {
                "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0, "a": 1}}]),
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # f-1 is n1 — it should have real fills, not fills=[]
        lines = [l for l in script.split("\n") if "n1." in l]
        assert not any("fills = []" in l for l in lines), (
            f"Frame with fills should not get fills=[], got: {lines}"
        )

    def test_text_not_cleared(self):
        """Text nodes should NOT get fills=[] — they use fills for text color."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["t-1"],
            },
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "t-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # Text node should NOT get fills=[]
        lines = [l for l in script.split("\n") if "n1." in l]
        assert not any("fills = []" in l for l in lines)


class TestMode1L0Properties:
    """Verify Mode 1 instances apply L0 visual properties from DB."""

    def test_rotation_applied_to_mode1_instance(self):
        """A Mode 1 instance with rotation in DB should have rotation set.

        REST API stores -π/2 rad (CW rotation). Plugin API sign convention
        is opposite, so the emitted value must be +90°.
        """
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["icon-1"],
            },
            "icon-1": {"type": "icon"},
        })
        spec["_node_id_map"] = {"screen-1": 1, "icon-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {
                "component_key": "abc",
                "component_figma_id": "123:456",
                "bindings": [],
                "rotation": -1.5707963267948966,  # -90 degrees in radians (REST API)
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # REST API -rad → Plugin API positive degrees (sign negated)
        assert "rotation = 90" in script or "rotation = 90.0" in script

    def test_no_rotation_when_zero(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["icon-1"],
            },
            "icon-1": {"type": "icon"},
        })
        spec["_node_id_map"] = {"screen-1": 1, "icon-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {
                "component_key": "abc",
                "component_figma_id": "123:456",
                "bindings": [],
                "rotation": 0,
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "rotation" not in script

    def test_opacity_applied_to_mode1_instance(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["icon-1"],
            },
            "icon-1": {"type": "icon"},
        })
        spec["_node_id_map"] = {"screen-1": 1, "icon-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {
                "component_key": "abc",
                "component_figma_id": "123:456",
                "bindings": [],
                "opacity": 0.5,
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "opacity = 0.5" in script


class TestDeferredCanary:
    """Verify deferred section has yield, try/catch, and canary."""

    def _absolute_spec(self) -> dict:
        """Spec with absolute parent + positioned child — triggers deferred lines."""
        return _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
                "children": ["header-1"],
            },
            "header-1": {
                "type": "header",
                "layout": {"position": {"x": 0, "y": 50}, "sizing": {"width": 428, "height": 111}},
            },
        })

    def _autolayout_spec(self) -> dict:
        """Spec with auto-layout only — no deferred lines."""
        return _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical", "sizing": {"width": 428, "height": 926}},
                "children": ["card-1"],
            },
            "card-1": {"type": "card"},
        })

    def test_canary_emitted_when_deferred_lines_present(self):
        spec = self._absolute_spec()
        script, _ = generate_figma_script(spec)
        assert 'M["__canary"] = "deferred_ok"' in script

    def test_canary_not_emitted_when_no_deferred_lines(self):
        spec = self._autolayout_spec()
        script, _ = generate_figma_script(spec)
        assert "__canary" not in script

    def test_deferred_wrapped_in_try_catch(self):
        spec = self._absolute_spec()
        script, _ = generate_figma_script(spec)
        assert "try {" in script
        assert "} catch (_e) {" in script
        assert '"deferred_error: "' in script

    def test_yield_before_deferred_section(self):
        spec = self._absolute_spec()
        script, _ = generate_figma_script(spec)
        lines = script.split("\n")
        yield_idx = next(i for i, l in enumerate(lines) if "await new Promise" in l)
        deferred_idx = next(i for i, l in enumerate(lines) if "deferred until all children" in l)
        assert yield_idx < deferred_idx

    def test_canary_after_all_deferred_lines(self):
        spec = self._absolute_spec()
        script, _ = generate_figma_script(spec)
        lines = script.split("\n")
        canary_idx = next(i for i, l in enumerate(lines) if "__canary" in l and "deferred_ok" in l)
        position_indices = [i for i, l in enumerate(lines) if ".x = " in l or ".y = " in l]
        assert position_indices, "Expected position lines in deferred section"
        assert canary_idx > max(position_indices)

    def test_deferred_with_constraints_from_db(self):
        spec = self._absolute_spec()
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"constraint_h": "MIN", "constraint_v": "MIN", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        lines = script.split("\n")
        constraint_lines = [l for l in lines if ".constraints = " in l]
        assert constraint_lines, "Expected constraint lines"
        for cl in constraint_lines:
            assert cl.startswith("  "), f"Constraint line should be indented (inside try): {cl!r}"


class TestUnpublishedComponentFallback:
    """Verify Mode 1 falls back to instance figma_node_id for unpublished components."""

    def test_uses_figma_node_id_when_no_component_figma_id(self):
        """When component_figma_id is NULL, use the instance's figma_node_id to get main component."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["indicator-1"]},
            "indicator-1": {"type": "instance"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "indicator-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "component_key": "unpublished_key_abc",
                "component_figma_id": None,
                "figma_node_id": "2255:76359",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "importComponentByKeyAsync" not in script
        assert "getMainComponentAsync" in script
        assert "2255:76359" in script

    def test_uses_component_figma_id_when_available(self):
        """Normal path: component_figma_id present → use getNodeByIdAsync directly."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["header-1"]},
            "header-1": {"type": "header"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "component_key": "published_key",
                "component_figma_id": "123:456",
                "figma_node_id": "999:888",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "getMainComponentAsync" not in script
        assert "importComponentByKeyAsync" not in script
        assert "123:456" in script

    def test_fallback_creates_frame_when_no_ids(self):
        """When both component_figma_id and figma_node_id are missing, fall back to createFrame."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["thing-1"]},
            "thing-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "thing-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "component_key": "orphan_key",
                "component_figma_id": None,
                "figma_node_id": None,
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "createFrame()" in script
        assert "importComponentByKeyAsync" not in script
        assert "getMainComponentAsync" not in script


class TestOverrideGrouping:
    """Verify findOne calls are grouped by target to reduce tree traversals."""

    def _mode1_spec_with_overrides(self, overrides: list[dict]) -> tuple[dict, dict]:
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["header-1"]},
            "header-1": {"type": "header"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "component_key": "abc",
                "component_figma_id": "123:456",
                "bindings": [],
                "instance_overrides": overrides,
            },
        }
        return spec, db_visuals

    def test_self_overrides_no_findone(self):
        spec, db_visuals = self._mode1_spec_with_overrides([
            {"target": ":self", "property": "fills", "value": '[{"type":"SOLID","color":{"r":1,"g":0,"b":0}}]'},
        ])
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert ".fills = " in script
        assert "findOne" not in script or script.count("findOne") == 0

    def test_self_width_no_findone(self):
        spec, db_visuals = self._mode1_spec_with_overrides([
            {"target": ":self", "property": "width", "value": "200"},
        ])
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert ".resize(200," in script
        assert "findOne" not in script

    def test_grouped_overrides_single_findone(self):
        spec, db_visuals = self._mode1_spec_with_overrides([
            {"target": ";1334:005", "property": "fills", "value": '[{"type":"SOLID","color":{"r":1,"g":0,"b":0}}]'},
            {"target": ";1334:005", "property": "visible", "value": "true"},
        ])
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        id_finds = script.count('n.id.endsWith(";1334:005")')
        assert id_finds == 1, f"Expected 1 findOne for ;1334:005 but got {id_finds}"

    def test_different_targets_separate_findone(self):
        spec, db_visuals = self._mode1_spec_with_overrides([
            {"target": ";1334:005", "property": "visible", "value": "true"},
            {"target": ";1334:006", "property": "visible", "value": "false"},
        ])
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'n.id.endsWith(";1334:005")' in script
        assert 'n.id.endsWith(";1334:006")' in script

    def test_findone_count_reduced(self):
        spec, db_visuals = self._mode1_spec_with_overrides([
            {"target": ";1334:005", "property": "instance_swap", "value": "999:111"},
            {"target": ";1334:005", "property": "fills", "value": '[{"type":"SOLID","color":{"r":1,"g":0,"b":0}}]'},
            {"target": ";1334:005", "property": "visible", "value": "true"},
            {"target": ";1334:006", "property": "visible", "value": "false"},
            {"target": ":self", "property": "fills", "value": '[{"type":"SOLID","color":{"r":0,"g":1,"b":0}}]'},
        ])
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        findone_count = script.count("findOne")
        assert findone_count == 2, f"Expected 2 findOne calls (;1334:005 + ;1334:006) but got {findone_count}"


class TestTokenRefL0Fallback:
    """Verify renderer falls back to DB values when token refs can't be resolved.

    Progressive fallback: L2 (token) → L0 (raw DB). When the IR style has
    a token ref like {type.display.s32.fontSize} but the token isn't in the
    tokens dict, the renderer must use the DB value (font_size=32) instead
    of skipping the property entirely.
    """

    def test_font_size_falls_back_to_db_when_token_unresolvable(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {
                "type": "text",
                "style": {"fontSize": "{type.display.s32.fontSize}", "fontWeight": "{type.display.s32.fontWeight}"},
                "props": {"text": "Hello"},
            },
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"font_family": "Inter", "font_size": 32.0, "font_weight": 600, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "fontSize = 32" in script, "Should fall back to DB font_size when token is unresolvable"

    def test_font_size_uses_resolved_token_when_available(self):
        spec = _make_spec(
            {
                "screen-1": {"type": "screen", "children": ["text-1"]},
                "text-1": {
                    "type": "text",
                    "style": {"fontSize": "{type.display.s32.fontSize}"},
                    "props": {"text": "Hello"},
                },
            },
            tokens={"type.display.s32.fontSize": 32},
        )
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"font_size": 24.0, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "fontSize = 32" in script, "Should use resolved token value (32) not DB value (24)"

    def test_font_weight_falls_back_to_db(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {
                "type": "text",
                "style": {"fontWeight": "{type.body.fontWeight}"},
                "props": {"text": "Hello"},
            },
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"font_weight": 700, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert '"Bold"' in script, "Should fall back to DB font_weight (700 → Bold)"

    def test_literal_font_size_still_works(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {
                "type": "text",
                "style": {"fontSize": 18},
                "props": {"text": "Hello"},
            },
        })
        script, _ = generate_figma_script(spec)
        assert "fontSize = 18" in script


class TestPerCornerRadius:
    """Verify per-corner radius emission (asymmetric cornerRadius)."""

    def test_per_corner_radius_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["card-1"]},
            "card-1": {"type": "card"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "card-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "corner_radius": '{"tl": 28, "tr": 28, "bl": 0, "br": 0}',
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "topLeftRadius = 28" in script
        assert "topRightRadius = 28" in script
        assert "bottomLeftRadius = 0" in script
        assert "bottomRightRadius = 0" in script

    def test_uniform_radius_still_works(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["card-1"]},
            "card-1": {"type": "card"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "card-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"corner_radius": "16", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "cornerRadius = 16" in script
        assert "topLeftRadius" not in script


class TestFillTypeCoverage:
    """Verify _emit_fills handles every fill type that normalize_fills produces.

    This structural test prevents the 'normalize but forget to emit' gap
    pattern. If normalize_fills adds a new type, this test fails until
    _emit_fills handles it.
    """

    def test_solid_fill_emitted(self):
        from dd.renderers.figma import _emit_fills
        fills = [{"type": "solid", "color": "#FF0000"}]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 1
        assert "SOLID" in lines[0]

    def test_gradient_linear_emitted(self):
        from dd.renderers.figma import _emit_fills
        fills = [{
            "type": "gradient-linear",
            "stops": [{"color": "#000000", "position": 0}, {"color": "#FFFFFF", "position": 1}],
            "gradientTransform": [[1, 0, 0], [0, 1, 0]],
        }]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 1
        assert "GRADIENT_LINEAR" in lines[0]

    def test_gradient_radial_emitted(self):
        from dd.renderers.figma import _emit_fills
        fills = [{
            "type": "gradient-radial",
            "stops": [{"color": "#000000", "position": 0}, {"color": "#FFFFFF", "position": 1}],
            "gradientTransform": [[1, 0, 0.5], [0, 1, 0.5]],
        }]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 1
        assert "GRADIENT_RADIAL" in lines[0]

    def test_gradient_without_transform_skipped(self):
        """Gradients without gradientTransform (supplement not run) are skipped."""
        from dd.renderers.figma import _emit_fills
        fills = [{
            "type": "gradient-linear",
            "stops": [{"color": "#000000", "position": 0}],
            "handlePositions": [{"x": 0, "y": 0}],
        }]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 0

    def test_mixed_solid_and_gradient(self):
        from dd.renderers.figma import _emit_fills
        fills = [
            {"type": "solid", "color": "#FF0000"},
            {"type": "gradient-linear",
             "stops": [{"color": "#000000", "position": 0}, {"color": "#FFFFFF", "position": 1}],
             "gradientTransform": [[1, 0, 0], [0, 1, 0]]},
        ]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 1
        assert "SOLID" in lines[0]
        assert "GRADIENT_LINEAR" in lines[0]

    def test_gradient_with_opacity(self):
        from dd.renderers.figma import _emit_fills
        fills = [{
            "type": "gradient-linear",
            "stops": [{"color": "#000000", "position": 0}, {"color": "#000000", "position": 1}],
            "gradientTransform": [[0, -1, 1], [1, 0, 0]],
            "opacity": 0.1,
        }]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 1
        assert "0.1" in lines[0]

    def test_all_normalize_fill_types_have_emit_handler(self):
        """Structural coverage: every type normalize_fills can produce must be
        handled by _emit_fills. This test fails if a new fill type is added
        to normalize_fills without a corresponding handler in _emit_fills."""
        from dd.renderers.figma import _GRADIENT_EMIT_MAP
        from dd.ir import _GRADIENT_TYPE_MAP

        ir_gradient_types = set(_GRADIENT_TYPE_MAP.values())
        emit_gradient_types = set(_GRADIENT_EMIT_MAP.keys())
        assert ir_gradient_types == emit_gradient_types, (
            f"IR produces gradient types {ir_gradient_types} but renderer "
            f"only handles {emit_gradient_types}"
        )


class TestResolveLayoutSizing:
    """Verify the pure sizing resolution function."""

    def test_db_value_takes_priority(self):
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={}, db_sizing_h="FILL", db_sizing_v="HUG",
            text_auto_resize=None, is_text=False, etype="container",
        )
        assert h == "FILL"
        assert v == "HUG"

    def test_text_width_and_height_gives_hug(self):
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={"width": 66, "height": 21}, db_sizing_h=None, db_sizing_v=None,
            text_auto_resize="WIDTH_AND_HEIGHT", is_text=True, etype="text",
        )
        assert h == "hug"
        assert v == "hug"

    def test_text_height_gives_fill_h_hug_v(self):
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={"width": 66, "height": 21}, db_sizing_h=None, db_sizing_v=None,
            text_auto_resize="HEIGHT", is_text=True, etype="text",
        )
        assert h == "fill"
        assert v == "hug"

    def test_text_none_auto_resize_uses_pixel_sizing(self):
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={"width": 66, "height": 21}, db_sizing_h=None, db_sizing_v=None,
            text_auto_resize="NONE", is_text=True, etype="text",
        )
        assert h == "fixed"
        assert v == "fixed"

    def test_ir_string_sizing_maps(self):
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={"width": "fill", "height": "hug"}, db_sizing_h=None, db_sizing_v=None,
            text_auto_resize=None, is_text=False, etype="container",
        )
        assert h == "fill"
        assert v == "hug"

    def test_pixel_sizing_gives_fixed(self):
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={"width": 200, "height": 100}, db_sizing_h=None, db_sizing_v=None,
            text_auto_resize=None, is_text=False, etype="container",
        )
        assert h == "fixed"
        assert v == "fixed"

    def test_fill_width_type_gives_fill(self):
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={}, db_sizing_h=None, db_sizing_v=None,
            text_auto_resize=None, is_text=False, etype="card",
        )
        assert h == "fill"

    def test_text_without_auto_resize_gets_fill(self):
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={}, db_sizing_h=None, db_sizing_v=None,
            text_auto_resize=None, is_text=True, etype="text",
        )
        assert h == "fill"

    def test_db_overrides_text_reconciliation(self):
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={}, db_sizing_h="FIXED", db_sizing_v="FIXED",
            text_auto_resize="WIDTH_AND_HEIGHT", is_text=True, etype="text",
        )
        assert h == "FIXED"
        assert v == "FIXED"


class TestOverrideDecomposition:
    """Verify override decomposition at query time."""

    def test_decompose_fills_self(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("FILLS", ":self:fills")
        assert target == ":self"
        assert prop == "fills"

    def test_decompose_fills_child(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("FILLS", ";1334:10837:fills")
        assert target == ";1334:10837"
        assert prop == "fills"

    def test_decompose_corner_radius_self(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("CORNER_RADIUS", ":self:cornerRadius")
        assert target == ":self"
        assert prop == "cornerRadius"

    def test_decompose_effects_self(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("EFFECTS", ":self:effects")
        assert target == ":self"
        assert prop == "effects"

    def test_decompose_padding_self(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("PADDING_LEFT", ":self:paddingLeft")
        assert target == ":self"
        assert prop == "paddingLeft"

    def test_decompose_text_child(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("TEXT", ";1334:10837")
        assert target == ";1334:10837"
        assert prop == "characters"

    def test_decompose_text_self(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("TEXT", ":self")
        assert target == ":self"
        assert prop == "characters"

    def test_decompose_instance_swap(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("INSTANCE_SWAP", ";1334:005")
        assert target == ";1334:005"
        assert prop == "instance_swap"

    def test_decompose_instance_swap_self(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("INSTANCE_SWAP", ":self")
        assert target == ":self"
        assert prop == "instance_swap"

    def test_decompose_boolean_child(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("BOOLEAN", ";1334:10836:visible")
        assert target == ";1334:10836"
        assert prop == "visible"

    def test_decompose_item_spacing_self(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("ITEM_SPACING", ":self:itemSpacing")
        assert target == ":self"
        assert prop == "itemSpacing"

    def test_decompose_strokes_child(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("STROKES", ";1334:10836:strokes")
        assert target == ";1334:10836"
        assert prop == "strokes"

    def test_decompose_layout_sizing_h(self):
        from dd.ir import decompose_override
        target, prop = decompose_override("LAYOUT_SIZING_H", ":self:layoutSizingH")
        assert target == ":self"
        assert prop == "layoutSizingHorizontal"


class TestOverrideEmissionRegistryDriven:
    """Verify registry-driven override emission with decomposed overrides."""

    def test_corner_radius_self_override_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["inst-1"]},
            "inst-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "inst-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "component_key": "abc123",
                "component_figma_id": "999:1",
                "bindings": [],
                "instance_overrides": [
                    {"target": ":self", "property": "cornerRadius", "value": "10"},
                ],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "cornerRadius = 10" in script

    def test_effects_self_override_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["inst-1"]},
            "inst-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "inst-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "component_key": "abc123",
                "component_figma_id": "999:1",
                "bindings": [],
                "instance_overrides": [
                    {"target": ":self", "property": "effects", "value": '[{"type":"DROP_SHADOW"}]'},
                ],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "effects" in script
        assert "DROP_SHADOW" in script

    def test_fills_child_override_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["inst-1"]},
            "inst-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "inst-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "component_key": "abc123",
                "component_figma_id": "999:1",
                "bindings": [],
                "instance_overrides": [
                    {"target": ";1334:10837", "property": "fills", "value": '[{"type":"SOLID","color":{"r":1,"g":0,"b":0}}]'},
                ],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "1334:10837" in script
        assert "fills" in script


class TestHexToFigmaRgba:
    """Verify hex_to_figma_rgba preserves alpha channel."""

    def test_6_digit_hex(self):
        from dd.renderers.figma import hex_to_figma_rgba
        result = hex_to_figma_rgba("#FF0000")
        assert result == {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}

    def test_8_digit_hex_opaque(self):
        from dd.renderers.figma import hex_to_figma_rgba
        result = hex_to_figma_rgba("#FF0000FF")
        assert result == {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}

    def test_8_digit_hex_transparent(self):
        from dd.renderers.figma import hex_to_figma_rgba
        result = hex_to_figma_rgba("#00000000")
        assert result == {"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.0}

    def test_8_digit_hex_semi_transparent(self):
        from dd.renderers.figma import hex_to_figma_rgba
        result = hex_to_figma_rgba("#00000080")
        assert result["a"] == round(128 / 255.0, 4)

    def test_gradient_stop_alpha_emitted(self):
        from dd.renderers.figma import _emit_fills
        fills = [{
            "type": "gradient-linear",
            "gradientTransform": [[1, 0, 0], [0, 1, 0]],
            "stops": [
                {"color": "#000000", "position": 0.0},
                {"color": "#00000000", "position": 1.0},
            ],
        }]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 1
        js = lines[0]
        assert "a:0.0" in js or "a:0" in js

    def test_shadow_color_alpha_emitted(self):
        from dd.renderers.figma import _emit_effects
        effects = [{
            "type": "drop-shadow",
            "color": "#00000040",
            "offset": {"x": 0, "y": 4},
            "blur": 8,
            "spread": 0,
        }]
        lines, _ = _emit_effects("v", "e", effects, {})
        assert len(lines) == 1
        js = lines[0]
        assert "a:0.251" in js or "a:0.25" in js


class TestEmitMissingVisualProperties:
    """Verify emission of visual properties previously extracted but not emitted."""

    def test_stroke_align_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"stroke_align": "INSIDE", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'strokeAlign = "INSIDE"' in script

    def test_stroke_align_not_emitted_when_default(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "strokeAlign" not in script

    def test_dash_pattern_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"dash_pattern": "[10, 5]", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "dashPattern = [10, 5]" in script

    def test_dash_pattern_not_emitted_when_empty(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"dash_pattern": "[]", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "dashPattern" not in script


class TestEmitMissingLayoutProperties:
    """Verify emission of layout properties previously extracted but not emitted."""

    def test_counter_axis_spacing_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container", "layout": {"direction": "vertical"}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"counter_axis_spacing": 12, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "counterAxisSpacing = 12" in script

    def test_layout_wrap_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container", "layout": {"direction": "horizontal"}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"layout_wrap": "WRAP", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'layoutWrap = "WRAP"' in script

    def test_layout_positioning_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"layout_positioning": "ABSOLUTE", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'layoutPositioning = "ABSOLUTE"' in script

    def test_layout_wrap_not_emitted_when_null(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "layoutWrap" not in script
        assert "layoutPositioning" not in script
        assert "counterAxisSpacing" not in script


class TestEmitMissingSizeProperties:
    """Verify emission of size constraint properties."""

    def test_min_width_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"min_width": 100, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "minWidth = 100" in script

    def test_max_width_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"max_width": 500, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "maxWidth = 500" in script

    def test_min_max_height_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"min_height": 50, "max_height": 300, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "minHeight = 50" in script
        assert "maxHeight = 300" in script

    def test_size_constraints_not_emitted_when_null(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "container"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "minWidth" not in script
        assert "maxWidth" not in script
        assert "minHeight" not in script
        assert "maxHeight" not in script


class TestEmitMissingTextProperties:
    """Verify emission of text properties previously extracted but not emitted."""

    def test_text_align_horizontal_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"text_align": "CENTER", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'textAlignHorizontal = "CENTER"' in script

    def test_text_align_vertical_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"text_align_v": "BOTTOM", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'textAlignVertical = "BOTTOM"' in script

    def test_text_decoration_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"text_decoration": "UNDERLINE", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'textDecoration = "UNDERLINE"' in script

    def test_text_case_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"text_case": "UPPER", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'textCase = "UPPER"' in script

    def test_line_height_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"line_height": '{"value": 24, "unit": "PIXELS"}', "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "lineHeight" in script
        assert "24" in script

    def test_letter_spacing_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"letter_spacing": '{"value": 0.5, "unit": "PIXELS"}', "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "letterSpacing" in script
        assert "0.5" in script

    def test_paragraph_spacing_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"paragraph_spacing": 8, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "paragraphSpacing = 8" in script

    def test_font_style_italic_emitted(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "font_family": "Inter",
                "font_weight": 400,
                "font_style": "Italic",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "Italic" in script

    def test_text_props_not_emitted_when_null(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "text", "props": {"text": "Hello"}, "style": {}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "textAlignHorizontal" not in script
        assert "textAlignVertical" not in script
        assert "textDecoration" not in script
        assert "textCase" not in script
        assert "paragraphSpacing" not in script


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec(elements: dict, tokens: dict | None = None) -> dict:
    root_id = next(iter(elements)) if elements else "root"
    return {
        "version": "1.0",
        "root": root_id,
        "tokens": tokens or {},
        "elements": elements,
    }
