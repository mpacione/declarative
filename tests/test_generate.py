"""Tests for Figma generation from CompositionSpec IR (T5 Phase 3)."""

from __future__ import annotations

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
from dd.ir import build_override_tree
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

    def test_text_nodes_use_fill_layout_sizing(self):
        """Under the ADR-007 emission order, WIDTH_AND_HEIGHT is the
        Figma-Plugin-API default for newly-created text nodes and no
        longer needs an explicit assignment. Explicit emission remains
        for non-default modes (HEIGHT etc.) — see
        TestTextAutoResize::test_explicit_height_from_db_emits."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "layout": {"direction": "vertical"}, "children": ["t-1"]},
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        script, _ = generate_figma_script(spec)
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
        # _rootPage is a snapshot of figma.currentPage captured before any
        # getNodeByIdAsync side-effects it. See TestExplicitStateHarness.
        assert "_rootPage.appendChild" in script

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
        # _rootPage = figma.currentPage captured at entry; see
        # TestExplicitStateHarness for the harness contract rationale.
        assert "_rootPage.appendChild" in script
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


class TestCanvasPositioning:
    """Verify screens can be positioned at specific canvas coordinates."""

    def test_canvas_position_sets_root_xy(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
        }})
        script, _ = generate_figma_script(spec, canvas_position=(500, 200))
        assert ".x = 500;" in script
        assert ".y = 200;" in script

    def test_screen_name_used_for_root_frame(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "_original_name": "iPhone 13 Pro Max - 8",
            "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
        }})
        script, _ = generate_figma_script(spec)
        assert '.name = "iPhone 13 Pro Max - 8";' in script

    def test_no_canvas_position_omits_root_xy(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
        }})
        script, _ = generate_figma_script(spec)
        # Root frame should NOT have x/y set (defaults to 0,0)
        lines = script.split("\n")
        root_var_line = [l for l in lines if "figma.createFrame()" in l][0]
        root_var = root_var_line.split("const ")[1].split(" =")[0]
        # Check no x/y assignment immediately after root creation
        assert f"{root_var}.x = " not in script or f"{root_var}.x = 0" not in script


class TestCalculateCanvasLayout:
    """Verify canvas layout calculation for multiple screens."""

    def test_single_screen(self):
        from dd.renderers.figma import calculate_canvas_layout
        positions = calculate_canvas_layout([(428, 926)])
        assert positions == [(0, 0)]

    def test_multiple_screens_horizontal(self):
        from dd.renderers.figma import calculate_canvas_layout
        positions = calculate_canvas_layout([
            (428, 926), (428, 926), (428, 926),
        ])
        assert positions[0] == (0, 0)
        assert positions[1][0] > 428  # second screen is to the right
        assert positions[1][1] == 0   # same row
        assert positions[2][0] > positions[1][0]  # third is further right

    def test_gap_between_screens(self):
        from dd.renderers.figma import calculate_canvas_layout
        positions = calculate_canvas_layout([(100, 200), (100, 200)], gap=50)
        assert positions[0] == (0, 0)
        assert positions[1] == (150, 0)  # 100 width + 50 gap

    def test_custom_gap(self):
        from dd.renderers.figma import calculate_canvas_layout
        positions = calculate_canvas_layout([(200, 400), (300, 400)], gap=100)
        assert positions[1] == (300, 0)  # 200 + 100

    def test_mixed_sizes(self):
        from dd.renderers.figma import calculate_canvas_layout
        positions = calculate_canvas_layout([
            (428, 926), (834, 1194), (1536, 1152),
        ], gap=80)
        assert positions[0] == (0, 0)
        assert positions[1] == (508, 0)    # 428 + 80
        assert positions[2] == (1422, 0)   # 508 + 834 + 80


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

    def test_token_bound_cornerRadius_produces_token_refs(self):
        raw = {
            "corner_radius": "8",
            "bindings": [{"property": "cornerRadius", "token_name": "radius.md", "resolved_value": "8"}],
        }
        visual = build_visual_from_db(raw)
        assert visual["cornerRadius"] == 8.0
        assert visual["_token_refs"]["cornerRadius"] == "radius.md"

    def test_token_bound_opacity_not_skipped(self):
        """opacity=1.0 is normally skip_emit_if_default, but must NOT skip when token-bound."""
        raw = {
            "opacity": 1.0,
            "bindings": [{"property": "opacity", "token_name": "opacity.full", "resolved_value": "1.0"}],
        }
        visual = build_visual_from_db(raw)
        assert visual["opacity"] == 1.0
        assert visual["_token_refs"]["opacity"] == "opacity.full"

    def test_no_bindings_no_token_refs(self):
        raw = {"corner_radius": "8", "bindings": []}
        visual = build_visual_from_db(raw)
        assert "_token_refs" not in visual

    def test_token_bound_counterAxisSpacing(self):
        raw = {
            "counter_axis_spacing": 16,
            "bindings": [{"property": "counterAxisSpacing", "token_name": "spacing.md", "resolved_value": "16"}],
        }
        visual = build_visual_from_db(raw)
        assert visual["counterAxisSpacing"] == 16
        assert visual["_token_refs"]["counterAxisSpacing"] == "spacing.md"

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

    def test_vector_type_created_without_asset(self):
        """Vectors are always created (even without asset data)."""
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
        assert "createVector()" in script

    def test_vector_with_asset_creates_vector(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["vector-1"],
                "_node_id_map": {"vector-1": 42},
            },
            "vector-1": {
                "type": "vector",
                "layout": {"sizing": {"width": 20, "height": 20}},
            },
        })
        spec["_node_id_map"] = {"vector-1": 42}
        db_visuals = {
            42: {
                "fills": "[]",
                "strokes": "[]",
                "effects": "[]",
                "bindings": [],
                "_asset_refs": [
                    {"asset_hash": "vec_abc", "role": "icon", "kind": "svg_path",
                     "svg_data": "M 0 0 L 10 0 L 10 10 Z"},
                ],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "figma.createVector()" in script
        assert "vectorPaths" in script
        assert "M 0 0 L 10 0 L 10 10 Z" in script

    def test_boolean_operation_with_asset(self):
        """Boolean operations are created natively and get vector path data."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["bool-1"],
            },
            "bool-1": {
                "type": "boolean_operation",
                "layout": {"sizing": {"width": 24, "height": 24}},
            },
        })
        spec["_node_id_map"] = {"bool-1": 99}
        db_visuals = {
            99: {
                "fills": "[]",
                "strokes": "[]",
                "effects": "[]",
                "bindings": [],
                "_asset_refs": [
                    {"asset_hash": "bool_xyz", "role": "icon", "kind": "svg_path",
                     "svg_data": "M 5 0 L 10 10 L 0 10 Z"},
                ],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "createBooleanOperation()" in script

    def test_group_created_via_figma_group(self):
        """Groups must be created via figma.group() — not skipped, not createFrame."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["group-1"],
            },
            "group-1": {
                "type": "group",
                "layout": {},
                "children": ["rectangle-1"],
            },
            "rectangle-1": {
                "type": "rectangle",
                "layout": {},
            },
        })
        script, _ = generate_figma_script(spec)
        assert "figma.group(" in script
        assert "createRectangle" in script

    def test_vector_created_not_skipped(self):
        """Vectors without assets should be created, not skipped."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["vector-1"],
            },
            "vector-1": {
                "type": "vector",
                "layout": {},
            },
        })
        script, _ = generate_figma_script(spec)
        assert "createVector()" in script

    def test_boolean_operation_created_not_skipped(self):
        """Boolean operations should be created, not skipped."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["boolean_operation-1"],
            },
            "boolean_operation-1": {
                "type": "boolean_operation",
                "layout": {},
            },
        })
        script, _ = generate_figma_script(spec)
        assert "createBooleanOperation()" in script


class TestGroupRendering:
    """Groups are created via figma.group() with proper mask support."""

    def test_group_children_not_orphaned(self):
        """Children of groups must appear in the generated script."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["group-1"],
            },
            "group-1": {
                "type": "group",
                "layout": {},
                "children": ["ellipse-1", "rectangle-1"],
            },
            "ellipse-1": {
                "type": "ellipse",
                "layout": {},
            },
            "rectangle-1": {
                "type": "rectangle",
                "layout": {},
            },
        })
        script, _ = generate_figma_script(spec)
        assert "createEllipse" in script
        assert "createRectangle" in script
        assert "figma.group(" in script

    def test_mask_group_with_is_mask(self):
        """Mask groups work natively — isMask on child inside a real GROUP."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["group-1"],
            },
            "group-1": {
                "type": "group",
                "layout": {},
                "children": ["ellipse-1", "rectangle-1"],
            },
            "ellipse-1": {
                "type": "ellipse",
                "layout": {},
            },
            "rectangle-1": {
                "type": "rectangle",
                "layout": {},
            },
        })
        db_visuals = {
            10: {"is_mask": 1, "fills": "[]", "strokes": "[]", "effects": "[]", "bindings": [], "_asset_refs": []},
            20: {"fills": "[]", "strokes": "[]", "effects": "[]", "bindings": [], "_asset_refs": []},
        }
        spec["_node_id_map"] = {"ellipse-1": 10, "rectangle-1": 20, "group-1": 5}
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "figma.group(" in script
        assert ".isMask = true" in script

    def test_is_mask_property_emitted(self):
        """Nodes with is_mask=1 must have .isMask = true set in the generated JS."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["ellipse-1"],
            },
            "ellipse-1": {
                "type": "ellipse",
                "layout": {},
            },
        })
        db_visuals = {
            10: {"is_mask": 1, "fills": "[]", "strokes": "[]", "effects": "[]", "bindings": [], "_asset_refs": []},
        }
        spec["_node_id_map"] = {"ellipse-1": 10}
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert ".isMask = true" in script


class TestFix3BPropertyEmission:
    """Verify booleanOperation, cornerSmoothing, and arcData are emitted in generated JS."""

    def test_corner_smoothing_emitted(self):
        """cornerSmoothing emitted as float on frame nodes."""
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
        db_visuals = {
            10: {"corner_smoothing": 0.6, "fills": "[]", "strokes": "[]", "effects": "[]",
                 "bindings": [], "_asset_refs": []},
        }
        spec["_node_id_map"] = {"frame-1": 10}
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert ".cornerSmoothing = 0.6" in script

    def test_boolean_operation_emitted(self):
        """booleanOperation emitted on asset-backed boolean operation nodes."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["boolean_operation-1"],
            },
            "boolean_operation-1": {
                "type": "boolean_operation",
                "layout": {},
            },
        })
        db_visuals = {
            10: {
                "boolean_operation": "UNION",
                "fills": "[]", "strokes": "[]", "effects": "[]",
                "bindings": [],
                "_asset_refs": [{"asset_hash": "abc", "role": "icon", "kind": "svg_path",
                                 "svg_data": "M 0 0 L 10 10"}],
            },
        }
        spec["_node_id_map"] = {"boolean_operation-1": 10}
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert '.booleanOperation = "UNION"' in script

    def test_arc_data_emitted(self):
        """arcData emitted as JSON object on ellipse nodes."""
        import json
        arc = {"startingAngle": 0.0, "endingAngle": 3.14, "innerRadius": 0.5}
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 100, "height": 100}},
                "children": ["ellipse-1"],
            },
            "ellipse-1": {
                "type": "ellipse",
                "layout": {},
            },
        })
        db_visuals = {
            10: {"arc_data": json.dumps(arc), "fills": "[]", "strokes": "[]", "effects": "[]",
                 "bindings": [], "_asset_refs": []},
        }
        spec["_node_id_map"] = {"ellipse-1": 10}
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert ".arcData = " in script


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

    def test_no_explicit_emission_when_default_width_and_height(self):
        """ADR-007 follow-up: WIDTH_AND_HEIGHT is the Figma default for
        a newly-created text node. Explicit emission is skipped — it's
        redundant and historically caused width-lock side effects when
        emitted before .characters. Non-default modes (HEIGHT, NONE,
        TRUNCATE) still emit in Phase 2 after layoutSizing — see
        test_explicit_height_from_db_emits."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["t-1"],
            },
            "t-1": {"type": "text", "props": {"text": "Hello"}},
        })
        script, _ = generate_figma_script(spec, db_visuals=None)
        # No explicit textAutoResize line should appear; default is
        # Figma's WIDTH_AND_HEIGHT and emitting it is redundant.
        assert "textAutoResize" not in script

    def test_no_explicit_emission_when_null_in_db(self):
        """When DB text_auto_resize is None, defer to Figma's default
        (WIDTH_AND_HEIGHT). No emission required."""
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
        assert "textAutoResize" not in script


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
                "override_tree": build_override_tree([{
                    "target": ";1334:005",
                    "property": "layoutSizingHorizontal",
                    "value": "HUG",
                }], []),
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
                "override_tree": build_override_tree([{
                    "target": ";1334:005",
                    "property": "layoutSizingVertical",
                    "value": "FILL",
                }], []),
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


    def test_rectangle_without_fills_gets_empty_fills(self):
        """Rectangles with no fills should get fills=[] to clear Figma's default white."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["r-1"],
            },
            "r-1": {"type": "rectangle"},
        })
        spec["_node_id_map"] = {"screen-1": 1, "r-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        lines = [l for l in script.split("\n") if "n1." in l]
        assert any("fills = []" in l for l in lines), (
            f"Rectangle with no fills should get fills=[], got: {lines}"
        )

    def test_ellipse_without_fills_gets_empty_fills(self):
        """Ellipses with no fills should get fills=[] to clear Figma's default white."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["e-1"],
            },
            "e-1": {"type": "ellipse"},
        })
        spec["_node_id_map"] = {"screen-1": 1, "e-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        lines = [l for l in script.split("\n") if "n1." in l]
        assert any("fills = []" in l for l in lines), (
            f"Ellipse with no fills should get fills=[], got: {lines}"
        )

    def test_vector_without_fills_gets_empty_fills(self):
        """Vectors with no fills should get fills=[] to clear Figma's default white."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["v-1"],
            },
            "v-1": {"type": "vector"},
        })
        spec["_node_id_map"] = {"screen-1": 1, "v-1": 2}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        lines = [l for l in script.split("\n") if "n1." in l]
        assert any("fills = []" in l for l in lines), (
            f"Vector with no fills should get fills=[], got: {lines}"
        )


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


class TestDeferredPhase3Structure:
    """Phase 3 structure after ADR-007 Session B:

    - No coarse try/catch, no M["__canary"] — per-op guards replace both.
    - The async-yield (`await new Promise(r => setTimeout(r, 0))`) still
      runs before deferred operations so Figma's layout engine can
      resolve before positions/constraints/text are applied.
    - Each guarded operation is a short try/catch pushing a structured
      entry to __errors on failure.
    """

    def _absolute_spec(self) -> dict:
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
        return _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical", "sizing": {"width": 428, "height": 926}},
                "children": ["card-1"],
            },
            "card-1": {"type": "card"},
        })

    def test_no_canary_regardless_of_shape(self):
        for spec in (self._absolute_spec(), self._autolayout_spec()):
            script, _ = generate_figma_script(spec)
            assert "__canary" not in script, (
                "Session B removed M[\"__canary\"]; "
                "one failure channel (__errors) only"
            )

    def test_no_deferred_error_marker(self):
        spec = self._absolute_spec()
        script, _ = generate_figma_script(spec)
        assert "deferred_error" not in script
        assert "deferred_ok" not in script

    def test_yield_before_phase3_operations(self):
        spec = self._absolute_spec()
        script, _ = generate_figma_script(spec)
        lines = script.split("\n")
        phase3_idx = next(
            (i for i, l in enumerate(lines) if "// Phase 3:" in l), None,
        )
        if phase3_idx is None:
            pytest.skip("no Phase 3 emitted for this fixture")
        yield_line = lines[phase3_idx + 1]
        assert "await new Promise" in yield_line, (
            "async yield must immediately follow the Phase 3 marker"
        )

    def test_constraints_emitted_with_per_op_guard(self):
        spec = self._absolute_spec()
        spec["_node_id_map"] = {"screen-1": -1, "header-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"constraint_h": "MIN", "constraint_v": "MIN", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # Session B wraps each constraint assignment in its own try/catch
        # with kind="constraint_failed". Legacy indentation-as-marker
        # no longer applies because each line carries its own guard.
        assert ".constraints = " in script
        assert "constraint_failed" in script


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
                "override_tree": build_override_tree(overrides, []),
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

    def test_swap_emitted_before_descendant_override(self):
        """Instance swap on a target must emit BEFORE property overrides on descendants.

        This is the bug that caused wrong icon colors: swap replaces the subtree,
        so property overrides on descendants must come after the swap.
        """
        overrides = [
            {"target": ";1334:10838;2054:27785", "property": "strokes", "value": '[{"type":"SOLID"}]'},
        ]
        child_swaps = [
            {"child_id": ";1334:10838", "swap_target_id": "999:111"},
        ]
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
                "override_tree": build_override_tree(overrides, child_swaps),
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        swap_pos = script.find("swapComponent")
        strokes_pos = script.find(".strokes =")
        assert swap_pos > 0, "Expected swapComponent in output"
        assert strokes_pos > 0, "Expected strokes override in output"
        assert swap_pos < strokes_pos, (
            f"Swap (pos {swap_pos}) must come before strokes override (pos {strokes_pos})"
        )


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

    def test_image_fill_emitted(self):
        from dd.renderers.figma import _emit_fills
        fills = [{"type": "image", "asset_hash": "abc123", "scaleMode": "fill"}]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 1
        assert "IMAGE" in lines[0]
        assert "abc123" in lines[0]
        assert "FILL" in lines[0]

    def test_image_fill_with_opacity(self):
        from dd.renderers.figma import _emit_fills
        fills = [{"type": "image", "asset_hash": "xyz", "scaleMode": "fit", "opacity": 0.5}]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 1
        assert "FIT" in lines[0]
        assert "0.5" in lines[0]

    def test_mixed_solid_and_image_fills(self):
        from dd.renderers.figma import _emit_fills
        fills = [
            {"type": "solid", "color": "#FF0000"},
            {"type": "image", "asset_hash": "img1", "scaleMode": "fill"},
        ]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 1
        assert "SOLID" in lines[0]
        assert "IMAGE" in lines[0]

    def test_image_fill_with_image_transform_emitted(self):
        from dd.renderers.figma import _emit_fills
        transform = [[0.64, 0.0, 0.17], [0.0, 0.64, 0.17]]
        fills = [{"type": "image", "asset_hash": "abc123", "scaleMode": "stretch", "imageTransform": transform}]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert len(lines) == 1
        assert "CROP" in lines[0]
        assert "imageTransform" in lines[0]
        assert "0.64" in lines[0]
        assert "0.17" in lines[0]

    def test_image_fill_without_image_transform_no_crop(self):
        from dd.renderers.figma import _emit_fills
        fills = [{"type": "image", "asset_hash": "abc123", "scaleMode": "fill"}]
        lines, _ = _emit_fills("v", "e", fills, {})
        assert "imageTransform" not in lines[0]
        assert "FILL" in lines[0]

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

    def test_pixel_sizing_defaults_to_fixed(self):
        """Pixel dimensions with no DB sizing default to FIXED (Figma platform default)."""
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={"width": 200, "height": 100}, db_sizing_h=None, db_sizing_v=None,
            text_auto_resize=None, is_text=False, etype="container",
        )
        assert h == "fixed"
        assert v == "fixed"

    def test_db_sizing_takes_priority_over_pixel_dimensions(self):
        """Ground-truth DB sizing overrides pixel dimension defaults."""
        from dd.visual import _resolve_layout_sizing
        h, v = _resolve_layout_sizing(
            elem_sizing={"width": 200, "height": 100}, db_sizing_h="FILL", db_sizing_v="HUG",
            text_auto_resize=None, is_text=False, etype="container",
        )
        assert h == "FILL"
        assert v == "HUG"

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
                "override_tree": build_override_tree([
                    {"target": ":self", "property": "cornerRadius", "value": "10"},
                ], []),
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
                "override_tree": build_override_tree([
                    {"target": ":self", "property": "effects", "value": '[{"type":"DROP_SHADOW"}]'},
                ], []),
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
                "override_tree": build_override_tree([
                    {"target": ";1334:10837", "property": "fills", "value": '[{"type":"SOLID","color":{"r":1,"g":0,"b":0}}]'},
                ], []),
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


class TestClipsContentDefault:
    """Figma createFrame() defaults clipsContent to true.

    When clips_content is NULL in the DB (not extracted), the renderer must
    emit clipsContent=false as the safer default. Unexpected clipping is more
    visually destructive than missing clipping.
    See feedback_default_fills_per_platform.md for the analogous fills pattern.
    """

    def test_frame_without_clips_content_gets_false(self):
        """Frame with no clips_content in DB gets clipsContent=false."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "frame"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},  # No clips_content
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "clipsContent = false" in script

    def test_frame_with_explicit_true_stays_true(self):
        """Frame with clips_content=True keeps clipsContent=true."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "frame"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"clips_content": True, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "clipsContent = true" in script

    def test_text_nodes_not_affected(self):
        """Text nodes don't get clipsContent (only frames do)."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["text-1"]},
            "text-1": {"type": "heading", "style": {"fontFamily": "Inter"}, "props": {"text": "Hello"}},
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # Text node (n1) should not have clipsContent; screen root (n0) may
        lines = script.split("\n")
        text_clips = [l for l in lines if "n1.clipsContent" in l]
        assert len(text_clips) == 0

    def test_leaf_shape_nodes_not_affected(self):
        """Rectangle, ellipse, line, vector, boolean_operation don't support
        clipsContent — it's a FRAME-only property. Emitting it on these leaf
        shapes throws 'object is not extensible' at runtime in Figma.
        """
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "children": ["rect-1", "ellipse-1", "line-1", "vector-1", "bool-1"],
            },
            "rect-1": {"type": "rectangle"},
            "ellipse-1": {"type": "ellipse"},
            "line-1": {"type": "line"},
            "vector-1": {"type": "vector"},
            "bool-1": {"type": "boolean_operation"},
        })
        spec["_node_id_map"] = {
            "screen-1": -1,
            "rect-1": -2,
            "ellipse-1": -3,
            "line-1": -4,
            "vector-1": -5,
            "bool-1": -6,
        }
        db_visuals = {
            -1: {"bindings": []},
            -2: {"bindings": []},
            -3: {"bindings": []},
            -4: {"bindings": []},
            -5: {"bindings": []},
            -6: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        lines = script.split("\n")
        # Leaf shapes are n1..n5; none may carry clipsContent
        for leaf_var in ("n1", "n2", "n3", "n4", "n5"):
            leaf_clips = [l for l in lines if f"{leaf_var}.clipsContent" in l]
            assert len(leaf_clips) == 0, (
                f"{leaf_var} (leaf shape) must not emit clipsContent: {leaf_clips}"
            )


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

class TestRenderReadiness:
    """Verify render-readiness validation catches data gaps before rendering."""

    def test_warns_on_vector_without_asset(self):
        from dd.renderers.figma import validate_render_readiness
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["v-1"]},
            "v-1": {"type": "vector"},
        })
        spec["_node_id_map"] = {"screen-1": 1, "v-1": 2}
        db_visuals = {1: {"bindings": []}, 2: {"bindings": []}}
        warnings = validate_render_readiness(spec, db_visuals)
        vector_warnings = [w for w in warnings if w["code"] == "EMPTY_VECTOR"]
        assert len(vector_warnings) == 1
        assert "v-1" in vector_warnings[0]["element_id"]

    def test_no_warning_for_vector_with_asset(self):
        from dd.renderers.figma import validate_render_readiness
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["v-1"]},
            "v-1": {"type": "vector"},
        })
        spec["_node_id_map"] = {"screen-1": 1, "v-1": 2}
        db_visuals = {1: {"bindings": []}, 2: {"bindings": [], "_asset_refs": [{"svg_data": "M0 0"}]}}
        warnings = validate_render_readiness(spec, db_visuals)
        vector_warnings = [w for w in warnings if w["code"] == "EMPTY_VECTOR"]
        assert len(vector_warnings) == 0

    def test_warns_on_missing_sizing_mode(self):
        from dd.renderers.figma import validate_render_readiness
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "vertical"},
                "children": ["f-1"],
            },
            "f-1": {"type": "frame", "layout": {"sizing": {"width": 200}}},
        })
        spec["_node_id_map"] = {"screen-1": 1, "f-1": 2}
        db_visuals = {1: {"bindings": []}, 2: {"bindings": [], "layout_sizing_h": None}}
        warnings = validate_render_readiness(spec, db_visuals)
        sizing_warnings = [w for w in warnings if w["code"] == "MISSING_SIZING_MODE"]
        assert len(sizing_warnings) >= 1


class TestLayoutWrap:
    """Verify layoutWrap and counterAxisSpacing are emitted by the Figma renderer."""

    def test_wrap_layout_emitted(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {
                    "direction": "horizontal",
                    "gap": 12,
                    "wrap": "WRAP",
                    "counterAxisGap": 10,
                    "sizing": {"width": 380, "height": "hug"},
                },
            },
        })
        script, _ = generate_figma_script(spec)
        assert 'layoutWrap = "WRAP"' in script
        assert "counterAxisSpacing = 10" in script

    def test_no_wrap_not_emitted(self):
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {
                    "direction": "horizontal",
                    "gap": 12,
                    "sizing": {"width": 380, "height": "hug"},
                },
            },
        })
        script, _ = generate_figma_script(spec)
        assert "layoutWrap" not in script
        assert "counterAxisSpacing" not in script

    def test_wrap_with_children_renders_correctly(self):
        """WRAP layout with children that exceed parent width should wrap."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {
                    "direction": "horizontal",
                    "gap": 12,
                    "wrap": "WRAP",
                    "counterAxisGap": 10,
                    "sizing": {"width": 380, "height": "hug"},
                },
                "children": ["text-1", "btn-1", "btn-2"],
            },
            "text-1": {
                "type": "text",
                "layout": {"sizing": {"width": "fill", "height": "hug"}},
                "content": "Horizontal",
            },
            "btn-1": {
                "type": "button",
                "layout": {"direction": "horizontal", "sizing": {"width": 86, "height": 40}},
            },
            "btn-2": {
                "type": "button",
                "layout": {"direction": "horizontal", "sizing": {"width": 86, "height": 40}},
            },
        })
        script, _ = generate_figma_script(spec)
        assert 'layoutWrap = "WRAP"' in script
        assert "counterAxisSpacing = 10" in script


class TestGroupPositioning:
    """Verify GROUP nodes get position and constraints after figma.group() creation."""

    def test_group_gets_position_after_creation(self):
        """GROUP nodes should have x/y set in the deferred positioning block."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "stacked", "sizing": {"width": 428, "height": 926}},
                "children": ["grp-1"],
            },
            "grp-1": {
                "type": "group",
                "layout": {"direction": "stacked", "position": {"x": 50, "y": 100}},
                "children": ["rect-1"],
            },
            "rect-1": {
                "type": "rectangle",
                "layout": {"direction": "stacked", "sizing": {"width": 100, "height": 50}},
            },
        })
        script, _ = generate_figma_script(spec)
        # GROUP var should have position set
        assert ".x = 50" in script
        assert ".y = 100" in script

    def test_text_with_width_and_height_autoresize_is_not_resized(self):
        """Figma Plugin API quirk: calling resize() on a text node whose
        textAutoResize is WIDTH_AND_HEIGHT implicitly flips it to HEIGHT
        (locking the width). The subsequent .characters assignment then
        wraps the text within the locked width, producing visible
        "Commun / ity" style multi-line text that should be single-line.

        Fix: when the DB says the text node's textAutoResize is
        WIDTH_AND_HEIGHT, don't emit resize() — let the content
        determine the size."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
                "children": ["text-1"],
            },
            "text-1": {
                "type": "text",
                "layout": {
                    "sizing": {"width": 111, "height": 15},
                    "position": {"x": 0, "y": 0},
                },
                "props": {"text": "Community"},
                "style": {"fontFamily": "Inter", "fontWeight": 600, "fontSize": 20},
            },
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "node_type": "TEXT",
                "text_auto_resize": "WIDTH_AND_HEIGHT",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # Pull lines that belong to the text node's var. The var name is
        # deterministic from walk order — text-1 is the second walked
        # element so `n1`. But that's brittle; instead, scan every
        # assignment to any var that sets textAutoResize="WIDTH_AND_HEIGHT"
        # and verify that var never has a .resize(...) line.
        import re
        for m in re.finditer(
            r'(\w+)\.textAutoResize = "WIDTH_AND_HEIGHT";', script,
        ):
            var = m.group(1)
            # No resize line for this var anywhere in the script.
            resize_pattern = re.compile(rf"\b{re.escape(var)}\.resize\(")
            assert not resize_pattern.search(script), (
                f"text node {var} has textAutoResize=WIDTH_AND_HEIGHT "
                f"but renderer emitted resize(), which flips autoResize "
                f"to HEIGHT and causes text to wrap"
            )

    def test_fill_text_characters_set_before_layoutsizing(self):
        """A FILL-sized text node in a HORIZONTAL auto-layout parent,
        alongside a HUG sibling, must have its characters set BEFORE
        layoutSizingHorizontal is applied.

        Otherwise the HUG sibling has empty characters at layoutSizing
        time → it measures as 0 wide → the FILL child gets the wrong
        remaining space → when characters are finally assigned the text
        wraps at a locked-too-narrow width (e.g. "M/o/r/e" one char per
        line). This is the root cause of screen 176/177 wrap defects.
        """
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "children": ["row-1"],
                "layout": {"sizing": {"width": 428, "height": 926}},
            },
            "row-1": {
                "type": "frame",
                "layout": {
                    "direction": "horizontal",
                    "sizing": {"width": 393, "height": 22},
                    "position": {"x": 0, "y": 0},
                },
                "children": ["sibling-1", "fill-text-1"],
            },
            "sibling-1": {
                "type": "heading",
                "layout": {
                    "sizing": {
                        "width": "hug", "widthPixels": 254,
                        "height": "hug", "heightPixels": 22,
                    },
                },
                "props": {"text": "Trending Memes & Templates"},
                "style": {"fontFamily": "Inter", "fontWeight": 600, "fontSize": 18},
            },
            "fill-text-1": {
                "type": "heading",
                "layout": {
                    "sizing": {
                        "width": "fill", "widthPixels": 103,
                        "height": "hug", "heightPixels": 22,
                    },
                },
                "props": {"text": "More"},
                "style": {"fontFamily": "Inter", "fontWeight": 600, "fontSize": 18},
            },
        })
        spec["_node_id_map"] = {
            "screen-1": -1, "row-1": -2, "sibling-1": -3, "fill-text-1": -4,
        }
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "node_type": "FRAME",
                "layout_mode": "HORIZONTAL",
                "layout_sizing_h": "FIXED",
                "layout_sizing_v": "HUG",
                "bindings": [],
            },
            -3: {
                "node_type": "TEXT",
                "layout_sizing_h": "HUG",
                "layout_sizing_v": "HUG",
                "text_auto_resize": "WIDTH_AND_HEIGHT",
                "bindings": [],
            },
            -4: {
                "node_type": "TEXT",
                "layout_sizing_h": "FILL",
                "layout_sizing_v": "HUG",
                "text_auto_resize": "HEIGHT",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)

        # Find the two text nodes by their content and compare positions.
        # The characters assignment of ANY text node sharing a parent
        # with a FILL text must come before any layoutSizingHorizontal
        # assignment in the same parent's subtree.
        import re
        # Pull the position in the script of:
        #   1. sibling's characters assignment (HUG text)
        #   2. fill-text's characters assignment
        #   3. fill-text's layoutSizingHorizontal assignment
        chars_sibling_pos = -1
        chars_fill_pos = -1
        layoutsize_fill_pos = -1
        for m in re.finditer(r'(\w+)\.characters = "Trending Memes & Templates"', script):
            chars_sibling_pos = m.start()
        for m in re.finditer(r'(\w+)\.characters = "More"', script):
            chars_fill_pos = m.start()
            fill_var = m.group(1)
            layoutsize_match = re.search(
                rf'\b{re.escape(fill_var)}\.layoutSizingHorizontal',
                script,
            )
            if layoutsize_match:
                layoutsize_fill_pos = layoutsize_match.start()

        assert chars_sibling_pos > 0, "sibling text characters not emitted"
        assert chars_fill_pos > 0, "fill text characters not emitted"
        assert layoutsize_fill_pos > 0, "fill text layoutSizingHorizontal not emitted"

        # The HUG sibling's characters must be set BEFORE the FILL
        # child's layoutSizingHorizontal, so Figma's auto-layout sees
        # the real sibling width when computing FILL's remainder.
        assert chars_sibling_pos < layoutsize_fill_pos, (
            "HUG sibling characters must be set before FILL child's "
            "layoutSizingHorizontal — otherwise FILL sees an empty "
            "(0-width) sibling and mis-allocates space"
        )

    def test_text_with_height_autoresize_still_resizes(self):
        """HEIGHT mode (fixed width, grows height) legitimately needs
        the explicit width from the DB — the resize call is correct
        there. This guards against over-fixing the WIDTH_AND_HEIGHT
        case by accidentally suppressing all text resizes."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
                "children": ["text-1"],
            },
            "text-1": {
                "type": "text",
                "layout": {
                    "sizing": {"width": 200, "height": 60},
                    "position": {"x": 0, "y": 0},
                },
                "props": {"text": "Long paragraph"},
                "style": {"fontFamily": "Inter", "fontWeight": 400, "fontSize": 14},
            },
        })
        spec["_node_id_map"] = {"screen-1": -1, "text-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "node_type": "TEXT",
                "text_auto_resize": "HEIGHT",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # HEIGHT mode: resize should still be emitted.
        import re
        for m in re.finditer(
            r'(\w+)\.textAutoResize = "HEIGHT";', script,
        ):
            var = m.group(1)
            resize_pattern = re.compile(rf"\b{re.escape(var)}\.resize\(")
            assert resize_pattern.search(script), (
                f"text node {var} has textAutoResize=HEIGHT; resize() "
                f"must be emitted to set the fixed width"
            )

    def test_group_does_not_get_constraints(self):
        """GROUP nodes do NOT support .constraints in the Figma Plugin
        API — the property_registry capability set for constraint_h/v
        excludes GROUP. Previously the renderer's group branch was
        bypassing the capability gate and emitting the illegal
        assignment anyway, which Session B's micro-guard caught as a
        constraint_failed entry on every render. Fix: gate the
        emission so nothing is written for GROUP.
        """
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "stacked", "sizing": {"width": 428, "height": 926}},
                "children": ["grp-1"],
            },
            "grp-1": {
                "type": "group",
                "layout": {"direction": "stacked", "position": {"x": 0, "y": 0}},
                "children": ["rect-1"],
            },
            "rect-1": {
                "type": "rectangle",
                "layout": {"direction": "stacked", "sizing": {"width": 100, "height": 50}},
            },
        })
        spec["_node_id_map"] = {"screen-1": 1, "grp-1": 2, "rect-1": 3}
        db_visuals = {
            1: {"bindings": []},
            2: {"bindings": [], "constraint_h": "MIN", "constraint_v": "MIN"},
            3: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # The group's variable is "ggrp_1" (prefix g + eid with - → _).
        # No line in the generated script should assign
        # ggrp_1.constraints = { ... }.
        assert "ggrp_1.constraints" not in script


class TestGradientFallback:
    """Verify gradients with computed transform from handlePositions render correctly."""

    def test_gradient_with_computed_transform_emitted(self):
        """Gradient fills with gradientTransform (even computed) should be emitted."""
        spec = _make_spec(
            elements={
                "screen-1": {
                    "type": "screen",
                    "layout": {"direction": "vertical", "sizing": {"width": 428, "height": 926}},
                },
            },
        )
        spec["_node_id_map"] = {"screen-1": 10}
        db_visuals = {
            10: {
                "fills": json.dumps([{
                    "type": "GRADIENT_LINEAR",
                    "gradientHandlePositions": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 1.0, "y": 0.0},
                        {"x": 0.0, "y": 1.0},
                    ],
                    "gradientStops": [
                        {"color": {"r": 1, "g": 0, "b": 0, "a": 1}, "position": 0},
                        {"color": {"r": 0, "g": 0, "b": 1, "a": 1}, "position": 1},
                    ],
                }]),
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "GRADIENT_LINEAR" in script
        assert "gradientTransform" in script


class TestThreePhaseRendering:
    """Three-phase renderer: Materialize → Compose → Hydrate.

    Phase 1 (Materialize): Create all nodes, set intrinsic properties
    Phase 2 (Compose): Wire tree (appendChild), set layoutSizing
    Phase 3 (Hydrate): Set text characters, position, constraints

    This ordering eliminates the Figma Plugin API ordering bug where FILL
    text children appended to HUG parents before FIXED siblings establish
    width, causing text to wrap at ~0px.
    """

    def _build_hug_card_spec(self):
        """Card with HUG width, FILL text child, and FIXED sibling.

        This is the exact structure that triggers the vertical text bug
        in single-pass rendering: the text child gets FILL sizing but
        there's no width to fill yet because the FIXED sibling hasn't
        been appended.
        """
        return {
            "version": "1.0",
            "root": "screen-1",
            "_node_id_map": {
                "frame-1": 100,
                "text-1": 101,
                "frame-2": 102,
            },
            "tokens": {},
            "elements": {
                "screen-1": {
                    "type": "screen",
                    "layout": {
                        "direction": "absolute",
                        "sizing": {"width": 428, "height": 926},
                    },
                    "children": ["frame-1"],
                },
                "frame-1": {
                    "type": "frame",
                    "_original_name": "Card",
                    "layout": {
                        "direction": "vertical",
                        "sizing": {"width": "hug", "height": "hug"},
                    },
                    "children": ["text-1", "frame-2"],
                },
                "text-1": {
                    "type": "heading",
                    "_original_name": "Title",
                    "layout": {
                        "sizing": {"width": "fill", "height": "hug"},
                    },
                    "style": {
                        "fontFamily": "Inter",
                        "fontWeight": 700,
                        "fontSize": 24,
                    },
                    "props": {"text": "Card Title"},
                },
                "frame-2": {
                    "type": "frame",
                    "_original_name": "Content",
                    "layout": {
                        "sizing": {"width": 380, "height": 200, "widthPixels": 380, "heightPixels": 200},
                    },
                },
            },
        }

    def _build_db_visuals(self):
        return {
            100: {
                "layout_sizing_h": "HUG",
                "layout_sizing_v": "HUG",
                "bindings": [],
            },
            101: {
                "layout_sizing_h": "FILL",
                "layout_sizing_v": "HUG",
                "font_family": "Inter",
                "font_weight": 700,
                "font_size": 24,
                "text_content": "Card Title",
                "text_auto_resize": "HEIGHT",
                "font_style": "Bold",
                "bindings": [],
            },
            102: {
                "layout_sizing_h": "FIXED",
                "layout_sizing_v": "FIXED",
                "bindings": [],
            },
        }

    def test_all_creates_before_any_appends(self):
        """All node creation calls must precede all appendChild calls."""
        spec = self._build_hug_card_spec()
        script, _ = generate_figma_script(spec, db_visuals=self._build_db_visuals())
        js_lines = script.split("\n")

        last_create_line = -1
        first_append_line = len(js_lines)

        for i, line in enumerate(js_lines):
            stripped = line.strip()
            if stripped.startswith("const n") and ("figma.create" in stripped or "createInstance" in stripped):
                last_create_line = i
            if ".appendChild(" in stripped and not stripped.startswith("//"):
                first_append_line = min(first_append_line, i)

        assert last_create_line < first_append_line, (
            f"Node creation (line {last_create_line}) must precede "
            f"appendChild (line {first_append_line})"
        )

    def test_each_text_characters_follows_its_own_append(self):
        """ADR-007 follow-up: text .characters is emitted in Phase 2
        immediately after the node's own appendChild (and before
        layoutSizing), not in a single trailing Phase 3 block. The
        correct invariant is per-node: each text's characters must
        follow its own appendChild. This replaces the old rule ('all
        appendChild before all characters'), which silently forced
        FILL-next-to-HUG layouts to wrap at 0 width because HUG
        siblings had no content when FILL evaluated."""
        spec = self._build_hug_card_spec()
        script, _ = generate_figma_script(spec, db_visuals=self._build_db_visuals())
        js_lines = script.split("\n")

        import re
        for i, line in enumerate(js_lines):
            m = re.search(r'(\w+)\.characters = "', line)
            if not m:
                continue
            var = m.group(1)
            found = any(
                f".appendChild({var})" in js_lines[j]
                for j in range(i)
            )
            assert found, (
                f"{var}.characters on line {i} has no preceding appendChild({var})"
            )

    def test_phase_comments_present(self):
        """Generated script contains phase boundary comments. Phase 3
        is only emitted when deferred operations exist (position /
        resize / constraint) — with text characters now in Phase 2, a
        fixture with nothing deferred has no Phase 3 block."""
        spec = self._build_hug_card_spec()
        script, _ = generate_figma_script(spec, db_visuals=self._build_db_visuals())

        assert "Phase 1" in script or "Materialize" in script
        assert "Phase 2" in script or "Compose" in script

    def test_layout_sizing_after_append(self):
        """layoutSizing is set after appendChild, not before."""
        spec = self._build_hug_card_spec()
        script, _ = generate_figma_script(spec, db_visuals=self._build_db_visuals())
        js_lines = script.split("\n")

        for i, line in enumerate(js_lines):
            stripped = line.strip()
            if "layoutSizingHorizontal" in stripped or "layoutSizingVertical" in stripped:
                # Find the closest preceding appendChild for this variable
                var_name = stripped.split(".")[0]
                append_found = False
                for j in range(i - 1, -1, -1):
                    if f".appendChild({var_name})" in js_lines[j]:
                        append_found = True
                        break
                if var_name.startswith("n"):
                    assert append_found, (
                        f"layoutSizing on {var_name} (line {i}) has no preceding appendChild"
                    )

    def test_resize_before_characters_in_same_subtree(self):
        """Legacy invariant (pre-ADR-007): when a non-auto-layout
        parent's resize was deferred to Phase 3, its FILL descendants
        had to wait for that resize before .characters ran.

        After ADR-007's Phase-2 text emission, .characters is set
        immediately after each text node's own appendChild — no longer
        gated on a distant Phase 3 resize. The invariant that survived:
        at the moment .characters is set, the text's parent chain must
        already have concrete dimensions (established in Phase 1 via
        resize or Phase 2 via auto-layout).

        This test continues to guard that in the specific scenario
        where a FILL text descends from a card that has explicit
        pixel dimensions via widthPixels — those pixel dimensions are
        emitted in Phase 1 (via _emit_layout resize for non-auto-layout
        children), so by Phase 2 the chain has widths.
        """
        spec = {
            "version": "1.0",
            "root": "screen-1",
            "_node_id_map": {
                "frame-1": 200,
                "frame-2": 201,
                "text-1": 202,
            },
            "tokens": {},
            "elements": {
                "screen-1": {
                    "type": "screen",
                    "layout": {
                        "direction": "absolute",
                        "sizing": {"width": 428, "height": 926},
                    },
                    "children": ["frame-1"],
                },
                "frame-1": {
                    "type": "frame",
                    "_original_name": "iPhone",
                    "layout": {
                        "direction": "absolute",
                        "sizing": {"width": 428, "height": 926},
                    },
                    "children": ["frame-2"],
                },
                "frame-2": {
                    "type": "frame",
                    "_original_name": "Card",
                    "layout": {
                        "direction": "vertical",
                        "sizing": {
                            "width": "fill",
                            "height": "hug",
                            "widthPixels": 428,
                            "heightPixels": 225,
                        },
                    },
                    "children": ["text-1"],
                },
                "text-1": {
                    "type": "heading",
                    "_original_name": "Label",
                    "layout": {
                        "sizing": {"width": "fill", "height": "hug"},
                    },
                    "style": {
                        "fontFamily": "Inter",
                        "fontWeight": 700,
                        "fontSize": 24,
                    },
                    "props": {"text": "Strength"},
                },
            },
        }
        db_visuals = {
            200: {"bindings": []},
            201: {
                "layout_sizing_h": "FILL",
                "layout_sizing_v": "HUG",
                "bindings": [],
            },
            202: {
                "layout_sizing_h": "FILL",
                "layout_sizing_v": "HUG",
                "font_family": "Inter",
                "font_weight": 700,
                "font_size": 24,
                "text_auto_resize": "HEIGHT",
                "font_style": "Bold",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        js_lines = script.split("\n")

        # For each text.characters assignment, find the text's parent
        # chain and verify at least one ancestor resize() appears
        # earlier in the script. The text node itself may be
        # FILL-sized (no resize), but its ancestors must have had
        # their widths established.
        import re
        for i, line in enumerate(js_lines):
            m = re.search(r'(\w+)\.characters = "', line)
            if not m:
                continue
            # For this legacy test we specifically care that some
            # resize() came before some .characters — in the fixture
            # there's only one text so a global ordering check still
            # works.
            found_prior_resize = any(
                ".resize(" in js_lines[j]
                and not js_lines[j].strip().startswith("//")
                for j in range(i)
            )
            assert found_prior_resize, (
                f"text.characters at line {i} has no preceding resize() — "
                f"the text's container chain needs concrete widths before "
                f"characters is set, otherwise wrap happens at 0 width"
            )

    def test_phase3_uses_per_op_guards_not_canary(self):
        """ADR-007 Session B: three-phase mode emits per-op guards in
        Phase 3, never the legacy M["__canary"] coarse try/catch."""
        spec = self._build_hug_card_spec()
        script, _ = generate_figma_script(spec, db_visuals=self._build_db_visuals())
        assert "__canary" not in script
        assert "deferred_ok" not in script
        assert "deferred_error" not in script


class TestCapabilityLint:
    """Structural lint: no generated script may assign a property to a var
    whose native Figma type doesn't support it. This is a defense-in-depth
    test — the emit gate should already prevent illegal emissions, but this
    lint catches regressions from any code path that bypasses emit_from_registry.

    The lint is derived from the registry's capability table, so adding a
    new property with correct capabilities automatically extends coverage.
    """

    # JS create-call → Figma native node type
    _CREATE_TO_NATIVE = {
        "figma.createRectangle": "RECTANGLE",
        "figma.createEllipse": "ELLIPSE",
        "figma.createLine": "LINE",
        "figma.createVector": "VECTOR",
        "figma.createBooleanOperation": "BOOLEAN_OPERATION",
        "figma.createText": "TEXT",
        "figma.createFrame": "FRAME",
        "figma.createComponent": "COMPONENT",
    }

    def _var_native_types(self, script: str) -> dict[str, str]:
        """Scan `const nN = figma.createX();` declarations and build
        var → native Figma type map."""
        import re
        var_types: dict[str, str] = {}
        for match in re.finditer(
            r"const\s+(\w+)\s*=\s*(figma\.create\w+)\(\)", script,
        ):
            var, create = match.group(1), match.group(2)
            native = self._CREATE_TO_NATIVE.get(create)
            if native:
                var_types[var] = native
        # Mode 1 null-guards resolve to createInstance via an IIFE; any
        # createInstance-backed var is an INSTANCE.
        for match in re.finditer(
            r"const\s+(\w+)\s*=\s*await\s+\(async\s*\(\s*\)\s*=>", script,
        ):
            var = match.group(1)
            var_types.setdefault(var, "INSTANCE")
        return var_types

    def test_script_has_no_illegal_property_assignments(self):
        """Mixed-type screen: emit should never land layoutMode on TEXT,
        clipsContent on RECTANGLE, arcData on anything but ELLIPSE, etc."""
        import re
        from dd.property_registry import is_capable, by_figma_name, PROPERTIES

        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["rect-1", "text-1", "ellipse-1", "line-1"]},
            "rect-1": {"type": "rectangle"},
            "text-1": {"type": "text"},
            "ellipse-1": {"type": "ellipse"},
            "line-1": {"type": "line"},
        })
        spec["_node_id_map"] = {
            "screen-1": -1, "rect-1": -2, "text-1": -3,
            "ellipse-1": -4, "line-1": -5,
        }
        db_visuals = {
            -1: {"bindings": []}, -2: {"bindings": []},
            -3: {"bindings": []}, -4: {"bindings": []},
            -5: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        var_types = self._var_native_types(script)

        # Known registry property names for the lint sweep
        registry_props = {p.figma_name for p in PROPERTIES}

        violations: list[str] = []
        # Pattern: `nN.propertyName = ...` or `nN.propertyName =`
        for line in script.split("\n"):
            match = re.match(r"\s*(\w+)\.(\w+)\s*=", line)
            if not match:
                continue
            var, prop = match.group(1), match.group(2)
            if var not in var_types or prop not in registry_props:
                continue
            native = var_types[var]
            if not is_capable(prop, "figma", native):
                violations.append(f"{var} ({native}).{prop} — {line.strip()}")

        assert not violations, (
            "Generated script assigns properties to node types that don't "
            f"support them:\n  " + "\n  ".join(violations)
        )


class TestPrefetchNullSafety:
    """figma.getNodeByIdAsync() can throw on transient network errors
    ("Unable to establish connection to Figma after 10 seconds") or return
    null when a component has been deleted. A bare `const _p0 = await
    figma.getNodeByIdAsync(id);` aborts the whole script on either.

    Contract: every prefetch await is wrapped in a try/catch IIFE that
    resolves to null on failure and pushes a structured entry into
    __errors. Downstream Mode 1 null-guards already handle null __src.
    """

    def test_prefetch_is_null_safe(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc", "component_figma_id": "123:456",
                 "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # Bare `const _pN = await figma.getNodeByIdAsync(...)` is not allowed
        assert "const _p0 = await figma.getNodeByIdAsync" not in script
        # Must be wrapped in a try/catch IIFE that pushes to __errors
        assert "prefetch_failed" in script


class TestExplicitStateHarness:
    """figma.getNodeByIdAsync() side-effects figma.currentPage, silently
    moving the active page. Anything downstream that reads figma.currentPage
    (e.g. `figma.currentPage.appendChild`) leaks nodes to the wrong page.

    Contract: the generated script captures figma.currentPage into a local
    _rootPage variable BEFORE any prefetch / getNodeByIdAsync call, and all
    subsequent references use _rootPage. The harness owns the target page;
    the script pins explicitly and never reads ambient state after that.
    """

    def test_root_page_captured_before_prefetch(self):
        """_rootPage is declared before any getNodeByIdAsync call."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc", "component_figma_id": "123:456",
                 "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        root_pos = script.find("const _rootPage")
        fetch_pos = script.find("getNodeByIdAsync")
        assert root_pos != -1, "_rootPage must be declared"
        assert root_pos < fetch_pos, (
            "_rootPage must be captured before any getNodeByIdAsync call"
        )

    def test_append_child_uses_captured_root_page(self):
        """figma.currentPage.appendChild is replaced with _rootPage.appendChild
        so side-effecting page changes don't leak nodes to other pages."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": []},
        })
        spec["_node_id_map"] = {"screen-1": -1}
        script, _ = generate_figma_script(
            spec, db_visuals={-1: {"bindings": []}},
        )
        assert "_rootPage.appendChild" in script
        assert "figma.currentPage.appendChild" not in script


class TestMode1NullSafety:
    """Mode 1 instantiation must survive missing component nodes.

    The master-component resolution chain can return null at runtime when
    the component has been deleted, unpublished, or never existed in this
    file. The old emission path threw uncaught "cannot read property
    'getMainComponentAsync' of null" which aborted the entire script.

    Contract: every Mode 1 creation is wrapped in a null-guarded async
    expression that falls back to createFrame() and records the failure
    in the script's __errors array for structured reporting.
    """

    def test_mode1_via_component_figma_id_is_null_guarded(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc", "component_figma_id": "123:456",
                 "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # The instance creation must be guarded and have a placeholder fallback
        assert "createInstance()" in script
        assert "__errors" in script
        assert "figma.createFrame()" in script

    def test_mode1_via_instance_id_is_null_guarded(self):
        """The second fallback path (getMainComponentAsync) must null-guard."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        # Only figma_node_id provided, no component_figma_id → second path
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc", "figma_node_id": "999:1",
                 "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "getMainComponentAsync" in script
        assert "__errors" in script
        # Must not be the old bare double-await that crashes on null
        assert ".getMainComponentAsync()).createInstance()" not in script

    def test_generated_script_declares_errors_array(self):
        """Every generated script declares __errors so the runtime harness
        can read structured failure reports."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": []},
        })
        spec["_node_id_map"] = {"screen-1": -1}
        script, _ = generate_figma_script(spec, db_visuals={-1: {"bindings": []}})
        assert "__errors" in script


def _make_spec(elements: dict, tokens: dict | None = None) -> dict:
    root_id = next(iter(elements)) if elements else "root"
    return {
        "version": "1.0",
        "root": root_id,
        "tokens": tokens or {},
        "elements": elements,
    }


# ---------------------------------------------------------------------------
# ADR-007 Session A: Codegen-time degradation (Position 1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSessionA_Mode1GateWidening:
    """The Mode 1 gate at figma.py:827 previously required EITHER
    component_key OR component_figma_id. This blocked path 2 (lines
    851-863: instance_figma_node_id → getMainComponentAsync) from
    ever being reached, because the gate evaluated False before the
    elif branch was checked. ADR-007 Session A widens the gate so
    an INSTANCE node with only `instance_figma_node_id` reaches path 2.
    """

    def test_path1_reached_when_component_figma_id_present(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "node_type": "INSTANCE",
                "component_figma_id": "123:456",
                "figma_node_id": "789:1",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # Path 1: getNodeByIdAsync against component_figma_id → createInstance
        assert '"123:456"' in script
        assert "createInstance()" in script
        # Path 2's getMainComponentAsync should NOT be emitted on path 1
        assert "getMainComponentAsync" not in script

    def test_path2_reached_when_instance_only(self):
        """NEW: when only instance_figma_node_id is present on an INSTANCE
        node, the gate should fall through to path 2, which emits
        `getNodeByIdAsync(instance_id).getMainComponentAsync().createInstance()`.
        Before Session A this branch was dead code.
        """
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "node_type": "INSTANCE",
                "component_key": None,
                "component_figma_id": None,
                "figma_node_id": "789:1",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "getMainComponentAsync" in script, (
            "Session A: INSTANCE with only figma_node_id must reach path 2"
        )
        assert '"789:1"' in script
        assert "createInstance()" in script

    def test_non_instance_not_widened(self):
        """Only INSTANCE nodes get the path-2 fallback. A FRAME with
        figma_node_id but no component inputs must still take Mode 2.
        """
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "frame"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "node_type": "FRAME",
                "figma_node_id": "789:1",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # Mode 2: createFrame for non-INSTANCE nodes
        assert "figma.createFrame()" in script
        # No Mode 1 for this node
        assert "getMainComponentAsync" not in script


@pytest.mark.unit
class TestSessionA_DegradationEmission:
    """When the emitter makes a lossy choice (Mode 2 for what should be
    an INSTANCE), it pushes a structured __errors entry at codegen time.
    Silent type substitution becomes impossible.
    """

    def test_instance_with_no_inputs_emits_degraded_to_mode2(self):
        """An INSTANCE node whose DB row has no component_key, no
        component_figma_id, AND no figma_node_id is genuinely
        unresolvable. The emitter must record this as a structured
        entry next to the createFrame() fallback line."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "node_type": "INSTANCE",
                "component_key": None,
                "component_figma_id": None,
                "figma_node_id": None,
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "degraded_to_mode2" in script, (
            "Session A: silent INSTANCE→FRAME must emit a structured "
            "__errors entry"
        )
        # The push should carry the eid so downstream verification can
        # attribute the degradation to a specific IR position.
        assert "button-1" in script

    def test_instance_taking_mode1_does_not_emit_degradation(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {
                "node_type": "INSTANCE",
                "component_figma_id": "123:456",
                "bindings": [],
            },
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "degraded_to_mode2" not in script

    def test_non_instance_mode2_does_not_emit_degradation(self):
        """FRAMEs always take Mode 2; that's not a degradation."""
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["frame-1"]},
            "frame-1": {"type": "frame"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"node_type": "FRAME", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "degraded_to_mode2" not in script


@pytest.mark.unit
class TestSessionA_CkrUnbuiltSignal:
    """When the DB doesn't have CKR built, every INSTANCE downstream
    degrades. The script preamble must push one `ckr_unbuilt` entry so
    the root cause is traceable even before the extract-side auto-build
    is in place on every deployment.
    """

    def test_preamble_pushes_ckr_unbuilt_when_flag_false(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"node_type": "INSTANCE", "figma_node_id": "789:1", "bindings": []},
        }
        script, _ = generate_figma_script(
            spec, db_visuals=db_visuals, ckr_built=False,
        )
        assert "ckr_unbuilt" in script

    def test_preamble_does_not_push_when_flag_true(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"node_type": "INSTANCE", "figma_node_id": "789:1", "bindings": []},
        }
        script, _ = generate_figma_script(
            spec, db_visuals=db_visuals, ckr_built=True,
        )
        assert "ckr_unbuilt" not in script

    def test_default_ckr_built_is_true(self):
        """Existing callers that don't pass the flag must not see
        spurious ckr_unbuilt pushes."""
        spec = _make_spec({"screen-1": {"type": "screen"}})
        spec["_node_id_map"] = {"screen-1": -1}
        db_visuals = {-1: {"bindings": []}}
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "ckr_unbuilt" not in script


# ---------------------------------------------------------------------------
# ADR-007 Session B: Runtime micro-guards (Position 2)
# ---------------------------------------------------------------------------


def _spec_with_text_and_frame() -> tuple[dict, dict]:
    """Build a spec with position-requiring frame + text node for
    exercising Phase 3 emissions."""
    spec = _make_spec({
        "screen-1": {
            "type": "screen",
            "children": ["frame-1", "text-1"],
            "layout": {
                "sizing": {"width": 428, "height": 926},
                "position": {"x": 0, "y": 0},
            },
        },
        "frame-1": {
            "type": "frame",
            "layout": {
                "sizing": {"widthPixels": 200, "heightPixels": 100},
                "position": {"x": 10, "y": 20},
            },
        },
        "text-1": {
            "type": "text",
            "props": {"text": "Hello"},
            "layout": {
                "sizing": {"width": 100, "height": 24},
                "position": {"x": 10, "y": 140},
            },
            "style": {
                "fontFamily": "Inter",
                "fontWeight": 400,
                "fontSize": 14,
            },
        },
    })
    spec["_node_id_map"] = {"screen-1": -1, "frame-1": -2, "text-1": -3}
    db_visuals = {
        -1: {"bindings": []},
        -2: {"bindings": []},
        -3: {"bindings": []},
    }
    return spec, db_visuals


@pytest.mark.unit
class TestSessionB_NoCoarsePhaseGuards:
    """The Phase 3 coarse try/catch and M["__canary"] are removed.
    A single throw can no longer abort all subsequent statements."""

    def test_no_canary_in_emitted_script(self):
        spec, db_visuals = _spec_with_text_and_frame()
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert 'M["__canary"]' not in script
        assert "deferred_ok" not in script
        assert "deferred_error" not in script

    def test_phase3_try_blocks_are_small(self):
        """No single `try {` block in Phase 3 should contain more than a
        handful of statements. Per-op guards keep each try tiny."""
        spec, db_visuals = _spec_with_text_and_frame()
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)

        # Find Phase 3 block
        if "// Phase 3:" not in script:
            pytest.skip("no Phase 3 emitted for this fixture")
        phase3 = script.split("// Phase 3:", 1)[1]
        phase3 = phase3.split("M[\"__errors\"]", 1)[0]  # up to return

        # Count statements between a `try {` and its `catch`
        import re
        for m in re.finditer(r"try\s*\{([^}]*)\}", phase3):
            body = m.group(1)
            stmts = [s for s in body.split(";") if s.strip()]
            # Tolerate small try blocks (e.g. single-op guard), but not
            # the ~550-statement legacy phase guard.
            assert len(stmts) <= 3, (
                f"Phase 3 try block has {len(stmts)} statements — "
                f"expected <=3 for per-op guards"
            )


@pytest.mark.unit
class TestSessionB_PerOpGuards:
    """Each Phase 3 operation is wrapped in its own guard pushing a
    structured entry to __errors on failure."""

    def test_text_characters_assignment_has_guard(self):
        spec, db_visuals = _spec_with_text_and_frame()
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # The .characters = ... assignment is guarded with a catch that
        # pushes kind="text_set_failed"
        assert ".characters =" in script
        assert "text_set_failed" in script

    def test_resize_has_guard(self):
        spec, db_visuals = _spec_with_text_and_frame()
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert ".resize(" in script
        assert "resize_failed" in script

    def test_position_has_guard(self):
        spec, db_visuals = _spec_with_text_and_frame()
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # .x and .y setters are guarded
        assert "position_failed" in script

    def test_group_constraints_are_not_emitted(self):
        """GROUP nodes don't support .constraints in the Figma Plugin
        API; the property_registry already declares the capability
        excluding GROUP (constraint_h/v: _FIGMA_ALL_VISIBLE - _FIGMA_GROUP).
        The renderer's group branch at the Phase 3 emission site was
        bypassing the capability gate, producing a runtime throw
        ('object is not extensible') that Session B caught as a
        constraint_failed entry on every render. Fix: honour the
        capability gate in the group branch too."""
        spec = _make_spec({
            "screen-1": {
                "type": "screen",
                "layout": {"direction": "absolute", "sizing": {"width": 428, "height": 926}},
                "children": ["group-1"],
            },
            "group-1": {
                "type": "group",
                "layout": {"position": {"x": 0, "y": 0}},
                "children": ["rect-1"],
            },
            "rect-1": {
                "type": "rectangle",
                "layout": {
                    "sizing": {"widthPixels": 10, "heightPixels": 10},
                    "position": {"x": 0, "y": 0},
                },
            },
        })
        spec["_node_id_map"] = {"screen-1": -1, "group-1": -2, "rect-1": -3}
        db_visuals = {
            -1: {"bindings": []},
            # group has constraints in DB, but they must NOT be emitted
            -2: {
                "node_type": "GROUP",
                "constraint_h": "MIN",
                "constraint_v": "MIN",
                "bindings": [],
            },
            -3: {"bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # No line in the emitted script should set a GROUP's .constraints.
        # The guarded-op wrapper prefixes each Phase 3 op with `try {`, so
        # we scan for the g<eid>.constraints pattern regardless of wrapping.
        gvar = "ggroup_1"
        assert f"{gvar}.constraints" not in script, (
            "GROUP.constraints must be suppressed by the capability gate"
        )

    def test_eid_preserved_in_guard_entry(self):
        """Each structured entry carries the eid it came from so
        downstream verification can attribute failures per-node."""
        spec, db_visuals = _spec_with_text_and_frame()
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        # text-1 is our eid for the text node; it must appear in a push
        # statement (surrounded by structured-error scaffolding).
        import re
        # Find text_set_failed pushes and verify they carry eid="text-1"
        pushes = re.findall(
            r"__errors\.push\(\{[^}]*text_set_failed[^}]*\}\)", script
        )
        assert pushes, "no text_set_failed push found"
        assert any('"text-1"' in p for p in pushes), (
            "text_set_failed push must carry eid='text-1'"
        )
