"""Tests for Figma generation from CompositionSpec IR (T5 Phase 3)."""

import json
import sqlite3

import pytest

from dd.db import init_db
from dd.generate import (
    hex_to_figma_rgb,
    resolve_style_value,
    font_weight_to_style,
    collect_fonts,
    generate_figma_script,
    generate_screen,
)
from dd.catalog import seed_catalog


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

    def test_async_iife_shape(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "vertical", "sizing": {"width": 428, "height": 926}},
        }})
        script, refs = generate_figma_script(spec)
        assert script.startswith("(async () => {")
        assert script.rstrip().endswith("})();")
        assert "return M;" in script

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
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "layout": {"direction": "vertical", "sizing": {"width": "fill"}},
        }})
        script, _ = generate_figma_script(spec)
        assert 'layoutSizingHorizontal = "FILL"' in script

    def test_background_color(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "style": {"backgroundColor": "#FF0000"},
        }})
        script, _ = generate_figma_script(spec)
        assert "fills = [{" in script
        assert '"SOLID"' in script

    def test_border_radius(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "style": {"borderRadius": 8},
        }})
        script, _ = generate_figma_script(spec)
        assert "cornerRadius = 8" in script

    def test_opacity(self):
        spec = _make_spec({"screen-1": {
            "type": "screen",
            "style": {"opacity": 0.5},
        }})
        script, _ = generate_figma_script(spec)
        assert "opacity = 0.5" in script

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

    def test_token_ref_collected(self):
        spec = _make_spec(
            elements={
                "screen-1": {"type": "screen", "style": {"backgroundColor": "{color.primary}"}},
            },
            tokens={"color.primary": "#FF0000"},
        )
        script, refs = generate_figma_script(spec)
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

    def test_escapes_text_quotes(self):
        spec = _make_spec({
            "screen-1": {"type": "screen", "children": ["t-1"]},
            "t-1": {"type": "text", "props": {"text": 'He said "hello"'}},
        })
        script, _ = generate_figma_script(spec)
        assert '\\"hello\\"' in script


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

    def test_script_is_valid_iife(self, db: sqlite3.Connection):
        result = generate_screen(db, screen_id=1)
        assert result["structure_script"].startswith("(async () => {")
        assert "return M;" in result["structure_script"]

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
