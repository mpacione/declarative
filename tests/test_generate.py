"""Tests for Figma generation from CompositionSpec IR (T5 Phase 3)."""

import json
import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.db import init_db
from dd.generate import (
    build_visual_from_db,
    collect_fonts,
    font_weight_to_style,
    generate_figma_script,
    generate_screen,
    hex_to_figma_rgb,
    resolve_style_value,
)

# ---------------------------------------------------------------------------
# Step 1: Pure helpers
# ---------------------------------------------------------------------------

class TestHexToFigmaRgb:
    """Verify hex color → Figma RGB {r,g,b} conversion."""

    def test_black(self):
        assert hex_to_figma_rgb("#000000") == {"r": 0.0, "g": 0.0, "b": 0.0}

    def test_white(self):
        assert hex_to_figma_rgb("#FFFFFF") == {"r": 1.0, "g": 1.0, "b": 1.0}

    def test_red(self):
        assert hex_to_figma_rgb("#FF0000") == {"r": 1.0, "g": 0.0, "b": 0.0}

    def test_mixed(self):
        result = hex_to_figma_rgb("#80C040")
        assert abs(result["r"] - 0.502) < 0.01
        assert abs(result["g"] - 0.7529) < 0.01
        assert abs(result["b"] - 0.2510) < 0.01

    def test_lowercase(self):
        assert hex_to_figma_rgb("#ff0000") == {"r": 1.0, "g": 0.0, "b": 0.0}

    def test_eight_digit_drops_alpha(self):
        result = hex_to_figma_rgb("#FF000080")
        assert result == {"r": 1.0, "g": 0.0, "b": 0.0}


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
        assert "fills" not in script

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
        assert "fills" not in script

    def test_none_db_visuals_produces_no_visual_output(self):
        spec = _make_spec({"screen-1": {"type": "screen"}})
        script, _ = generate_figma_script(spec, db_visuals=None)
        assert "fills" not in script

    def test_mode1_emits_import_component(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["button-1"]},
            "button-1": {"type": "button"},
        })
        spec["_node_id_map"] = {"screen-1": -1, "button-1": -2}
        db_visuals = {
            -1: {"bindings": []},
            -2: {"component_key": "abc123", "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "importComponentByKeyAsync" in script
        assert '"abc123"' in script
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
            -2: {"component_key": "abc123", "bindings": []},
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
            -2: {"component_key": "abc123", "bindings": []},
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
            -2: {"component_key": "abc123", "bindings": []},
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
            -2: {"component_key": "abc123", "bindings": []},
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
            -2: {"component_key": "abc123", "bindings": []},
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

    def test_clips_content_absent_when_zero(self):
        visual = build_visual_from_db({"clips_content": 0, "bindings": []})
        assert "clipsContent" not in visual

    # --- rotation ---

    def test_rotation_nonzero(self):
        visual = build_visual_from_db({"rotation": 45.0, "bindings": []})
        assert visual["rotation"] == 45.0

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
            -2: {"rotation": 45.0, "bindings": []},
        }
        script, _ = generate_figma_script(spec, db_visuals=db_visuals)
        assert "rotation = 45" in script

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
            -2: {"component_key": "abc123", "bindings": [], "hidden_children": []},
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
