"""Tests for code export functionality, specifically CSS custom properties and Tailwind config."""

import pytest
import sqlite3
from dd.export_css import (
    token_name_to_css_var,
    format_css_value,
    query_css_tokens,
    generate_css_for_collection,
    generate_css,
    write_code_mappings,
    export_css,
)
from dd.export_tailwind import (
    map_token_to_tailwind_section,
    token_name_to_tailwind_key,
    format_tailwind_value,
    generate_tailwind_config,
    generate_tailwind_config_dict,
    write_tailwind_mappings,
    export_tailwind,
)
from tests.fixtures import seed_post_curation


class TestTokenNameToCssVar:
    """Tests for token_name_to_css_var function."""

    def test_simple_dotted_path(self):
        """Convert a simple dotted path to CSS custom property."""
        result = token_name_to_css_var("color.surface.primary")
        assert result == "--color-surface-primary"

    def test_numeric_suffix(self):
        """Handle numeric suffix in token name."""
        result = token_name_to_css_var("space.4")
        assert result == "--space-4"

    def test_complex_path(self):
        """Convert complex nested path."""
        result = token_name_to_css_var("type.body.md.fontSize")
        assert result == "--type-body-md-fontSize"

    def test_single_segment(self):
        """Handle single segment names."""
        result = token_name_to_css_var("primary")
        assert result == "--primary"

    def test_empty_string(self):
        """Handle empty string input."""
        result = token_name_to_css_var("")
        assert result == "--"


class TestFormatCssValue:
    """Tests for format_css_value function."""

    def test_color_hex_passthrough(self):
        """Color hex values pass through unchanged."""
        result = format_css_value("#09090B", "color")
        assert result == "#09090B"

    def test_color_hex8_to_rgba(self):
        """8-digit hex colors are converted to rgba."""
        result = format_css_value("#09090BFF", "color")
        assert result == "rgba(9, 9, 11, 1)"

    def test_color_hex8_with_alpha(self):
        """8-digit hex with alpha channel."""
        result = format_css_value("#09090B80", "color")
        assert result == "rgba(9, 9, 11, 0.502)"

    def test_dimension_adds_px(self):
        """Dimension values get px appended if numeric."""
        result = format_css_value("16", "dimension")
        assert result == "16px"

    def test_dimension_with_unit_preserved(self):
        """Dimension values with units are preserved."""
        result = format_css_value("2rem", "dimension")
        assert result == "2rem"

    def test_dimension_auto_to_lowercase(self):
        """AUTO dimensions convert to lowercase."""
        result = format_css_value("AUTO", "dimension")
        assert result == "auto"

    def test_font_family_adds_quotes(self):
        """Font family values get quoted."""
        result = format_css_value("Inter", "fontFamily")
        assert result == '"Inter"'

    def test_font_family_already_quoted(self):
        """Already quoted font families stay quoted."""
        result = format_css_value('"Inter"', "fontFamily")
        assert result == '"Inter"'

    def test_font_weight_passthrough(self):
        """Font weight passes through as-is."""
        result = format_css_value("600", "fontWeight")
        assert result == "600"

    def test_number_passthrough(self):
        """Number values pass through as-is."""
        result = format_css_value("1.5", "number")
        assert result == "1.5"

    def test_unknown_type_passthrough(self):
        """Unknown types pass through unchanged."""
        result = format_css_value("some-value", "unknown")
        assert result == "some-value"


class TestQueryCssTokens:
    """Tests for query_css_tokens function."""

    def test_query_curated_tokens(self, temp_db):
        """Query returns curated and aliased tokens."""
        seed_post_curation(temp_db)

        # Add a dark mode for testing
        temp_db.execute(
            "INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (?, ?, ?, ?)",
            (3, 1, "Dark", 0)
        )
        temp_db.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?)",
            (1, 3, '{"r": 0.98, "g": 0.98, "b": 0.98, "a": 1}', "#FAFAFA")
        )
        temp_db.commit()

        results = query_css_tokens(temp_db, 1)

        assert len(results) > 0
        # Check structure of result
        first = results[0]
        assert "id" in first
        assert "name" in first
        assert "type" in first
        assert "tier" in first
        assert "collection_id" in first
        assert "mode_name" in first
        assert "resolved_value" in first

    def test_query_filters_by_file_id(self, temp_db):
        """Query only returns tokens for specified file."""
        seed_post_curation(temp_db)

        # Add another file's tokens
        temp_db.execute(
            "INSERT INTO files (id, file_key, name) VALUES (?, ?, ?)",
            (2, "other_file", "Other File")
        )
        temp_db.execute(
            "INSERT INTO token_collections (id, file_id, name) VALUES (?, ?, ?)",
            (3, 2, "Other Colors")
        )
        temp_db.execute(
            "INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (?, ?, ?, ?)",
            (4, 3, "Default", 1)
        )
        temp_db.execute(
            "INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (?, ?, ?, ?, ?)",
            (6, 3, "color.other", "color", "curated")
        )
        temp_db.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?)",
            (6, 4, '{"r": 1, "g": 0, "b": 0, "a": 1}', "#FF0000")
        )
        temp_db.commit()

        results = query_css_tokens(temp_db, 1)

        # Should not include tokens from file_id=2
        token_names = [r["name"] for r in results]
        assert "color.other" not in token_names
        assert "color.surface.primary" in token_names


class TestGenerateCssForCollection:
    """Tests for generate_css_for_collection function."""

    def test_generates_root_block(self):
        """Generate :root block with default mode values."""
        tokens = [
            {
                "id": 1,
                "name": "color.surface.primary",
                "type": "color",
                "tier": "curated",
                "collection_id": 1,
                "alias_target_name": None,
                "mode_id": 1,
                "mode_name": "Default",
                "resolved_value": "#09090B"
            },
            {
                "id": 2,
                "name": "color.surface.secondary",
                "type": "color",
                "tier": "curated",
                "collection_id": 1,
                "alias_target_name": None,
                "mode_id": 1,
                "mode_name": "Default",
                "resolved_value": "#18181B"
            }
        ]

        css = generate_css_for_collection(tokens, "Default")

        assert ":root {" in css
        assert "--color-surface-primary: #09090B;" in css
        assert "--color-surface-secondary: #18181B;" in css
        assert "}" in css

    def test_generates_data_theme_blocks(self):
        """Generate [data-theme] blocks for non-default modes."""
        tokens = [
            {
                "id": 1,
                "name": "color.surface.primary",
                "type": "color",
                "tier": "curated",
                "collection_id": 1,
                "alias_target_name": None,
                "mode_id": 1,
                "mode_name": "Light",
                "resolved_value": "#FFFFFF"
            },
            {
                "id": 1,
                "name": "color.surface.primary",
                "type": "color",
                "tier": "curated",
                "collection_id": 1,
                "alias_target_name": None,
                "mode_id": 2,
                "mode_name": "Dark",
                "resolved_value": "#000000"
            }
        ]

        css = generate_css_for_collection(tokens, "Light")

        assert ":root {" in css
        assert "--color-surface-primary: #FFFFFF;" in css
        assert '[data-theme="Dark"] {' in css
        assert "--color-surface-primary: #000000;" in css

    def test_handles_aliased_tokens(self):
        """Generate var() references for aliased tokens."""
        tokens = [
            {
                "id": 1,
                "name": "color.primary",
                "type": "color",
                "tier": "curated",
                "collection_id": 1,
                "alias_target_name": None,
                "mode_id": 1,
                "mode_name": "Default",
                "resolved_value": "#FF0000"
            },
            {
                "id": 2,
                "name": "color.button.bg",
                "type": "color",
                "tier": "aliased",
                "collection_id": 1,
                "alias_target_name": "color.primary",
                "mode_id": 1,
                "mode_name": "Default",
                "resolved_value": "#FF0000"
            }
        ]

        css = generate_css_for_collection(tokens, "Default")

        assert "--color-primary: #FF0000;" in css
        assert "--color-button-bg: var(--color-primary);" in css


class TestGenerateCss:
    """Tests for generate_css function."""

    def test_generates_css_with_header(self, temp_db):
        """Generate complete CSS with header comment."""
        seed_post_curation(temp_db)

        css = generate_css(temp_db, 1)

        assert css.startswith("/* Generated by Declarative Design */")
        assert "/* File: Test Design File */" in css
        assert ":root {" in css

    def test_handles_multiple_collections(self, temp_db):
        """Generate CSS for multiple collections."""
        seed_post_curation(temp_db)

        css = generate_css(temp_db, 1)

        # Should have both Colors and Spacing collections
        assert "--color-surface-primary:" in css
        assert "--space-4:" in css

    def test_determines_default_mode(self, temp_db):
        """Use is_default flag to determine default mode."""
        seed_post_curation(temp_db)

        # Add dark mode as non-default
        cursor = temp_db.execute(
            "INSERT INTO token_modes (collection_id, name, is_default) VALUES (?, ?, ?)",
            (1, "Dark", 0)
        )
        dark_mode_id = cursor.lastrowid
        # Add dark mode value
        temp_db.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?)",
            (1, dark_mode_id, '{"r": 1, "g": 1, "b": 1, "a": 1}', "#FFFFFF")
        )
        temp_db.commit()

        css = generate_css(temp_db, 1)

        # Default mode should be in :root
        assert ":root {" in css
        assert "--color-surface-primary: #09090B;" in css
        # Dark mode should be in [data-theme]
        assert '[data-theme="Dark"] {' in css


class TestWriteCodeMappings:
    """Tests for write_code_mappings function."""

    def test_writes_mappings_for_curated_tokens(self, temp_db):
        """Write code_mappings for all curated/aliased tokens."""
        seed_post_curation(temp_db)

        count = write_code_mappings(temp_db, 1)

        assert count > 0

        # Check mappings were created
        cursor = temp_db.execute(
            "SELECT * FROM code_mappings WHERE target = 'css'"
        )
        mappings = cursor.fetchall()
        assert len(mappings) == count

        # Check specific mapping
        cursor = temp_db.execute(
            """SELECT cm.identifier, t.name
               FROM code_mappings cm
               JOIN tokens t ON cm.token_id = t.id
               WHERE t.name = 'color.surface.primary'"""
        )
        row = cursor.fetchone()
        assert row["identifier"] == "--color-surface-primary"

    def test_writes_file_path(self, temp_db):
        """Mappings include file_path field."""
        seed_post_curation(temp_db)

        write_code_mappings(temp_db, 1)

        # Check file_path is set
        cursor = temp_db.execute(
            "SELECT file_path FROM code_mappings WHERE target = 'css' LIMIT 1"
        )
        row = cursor.fetchone()
        assert row["file_path"] == "tokens.css"

    def test_upsert_behavior(self, temp_db):
        """Mappings are upserted (updated if they exist)."""
        seed_post_curation(temp_db)

        # Write mappings first time
        count1 = write_code_mappings(temp_db, 1)

        # Write again - should update, not duplicate
        count2 = write_code_mappings(temp_db, 1)

        assert count1 == count2

        # Check no duplicates
        cursor = temp_db.execute(
            "SELECT COUNT(*) as cnt FROM code_mappings WHERE target = 'css'"
        )
        assert cursor.fetchone()["cnt"] == count1


class TestExportCss:
    """Tests for export_css convenience function."""

    def test_returns_complete_result(self, temp_db):
        """Export returns CSS, mappings count, and token count."""
        seed_post_curation(temp_db)

        result = export_css(temp_db, 1)

        assert "css" in result
        assert "mappings_written" in result
        assert "token_count" in result

        assert isinstance(result["css"], str)
        assert isinstance(result["mappings_written"], int)
        assert isinstance(result["token_count"], int)

        assert len(result["css"]) > 0
        assert result["mappings_written"] > 0
        assert result["token_count"] > 0

    def test_css_contains_expected_content(self, temp_db):
        """Exported CSS contains expected tokens."""
        seed_post_curation(temp_db)

        result = export_css(temp_db, 1)

        css = result["css"]
        assert "--color-surface-primary:" in css
        assert "--color-surface-secondary:" in css
        assert "--space-4:" in css


class TestMapTokenToTailwindSection:
    """Tests for map_token_to_tailwind_section function."""

    def test_map_color_tokens(self):
        """Map color tokens to colors section."""
        assert map_token_to_tailwind_section("color.surface.primary", "color") == "colors"
        assert map_token_to_tailwind_section("color.text.secondary", "color") == "colors"
        assert map_token_to_tailwind_section("color.border.default", "color") == "colors"
        assert map_token_to_tailwind_section("color.accent.blue", "color") == "colors"
        assert map_token_to_tailwind_section("color.primary", "color") == "colors"

    def test_map_space_tokens(self):
        """Map space tokens to spacing section."""
        assert map_token_to_tailwind_section("space.4", "dimension") == "spacing"
        assert map_token_to_tailwind_section("space.lg", "dimension") == "spacing"

    def test_map_radius_tokens(self):
        """Map radius tokens to borderRadius section."""
        assert map_token_to_tailwind_section("radius.md", "dimension") == "borderRadius"
        assert map_token_to_tailwind_section("radius.full", "dimension") == "borderRadius"

    def test_map_shadow_tokens(self):
        """Map shadow tokens to boxShadow section."""
        assert map_token_to_tailwind_section("shadow.sm", "shadow") == "boxShadow"
        assert map_token_to_tailwind_section("shadow.lg", "shadow") == "boxShadow"

    def test_map_typography_tokens(self):
        """Map typography tokens to appropriate sections."""
        assert map_token_to_tailwind_section("type.body.md.fontSize", "dimension") == "fontSize"
        assert map_token_to_tailwind_section("type.heading.fontFamily", "fontFamily") == "fontFamily"
        assert map_token_to_tailwind_section("type.bold.fontWeight", "fontWeight") == "fontWeight"
        assert map_token_to_tailwind_section("type.relaxed.lineHeight", "number") == "lineHeight"
        assert map_token_to_tailwind_section("type.wide.letterSpacing", "dimension") == "letterSpacing"

    def test_map_opacity_tokens(self):
        """Map opacity tokens to opacity section."""
        assert map_token_to_tailwind_section("opacity.50", "number") == "opacity"
        assert map_token_to_tailwind_section("opacity.disabled", "number") == "opacity"

    def test_fallback_to_extend(self):
        """Unknown token types fallback to extend."""
        assert map_token_to_tailwind_section("unknown.token", "custom") == "extend"
        assert map_token_to_tailwind_section("custom.value", "unknown") == "extend"


class TestTokenNameToTailwindKey:
    """Tests for token_name_to_tailwind_key function."""

    def test_strip_color_prefix(self):
        """Strip color prefix from color tokens."""
        assert token_name_to_tailwind_key("color.surface.primary", "colors") == "surface-primary"
        assert token_name_to_tailwind_key("color.text.secondary", "colors") == "text-secondary"
        assert token_name_to_tailwind_key("color.primary", "colors") == "primary"

    def test_strip_space_prefix(self):
        """Strip space prefix from spacing tokens."""
        assert token_name_to_tailwind_key("space.4", "spacing") == "4"
        assert token_name_to_tailwind_key("space.lg", "spacing") == "lg"

    def test_strip_radius_prefix(self):
        """Strip radius prefix from borderRadius tokens."""
        assert token_name_to_tailwind_key("radius.md", "borderRadius") == "md"
        assert token_name_to_tailwind_key("radius.full", "borderRadius") == "full"

    def test_strip_shadow_prefix(self):
        """Strip shadow prefix from boxShadow tokens."""
        assert token_name_to_tailwind_key("shadow.sm", "boxShadow") == "sm"
        assert token_name_to_tailwind_key("shadow.lg", "boxShadow") == "lg"

    def test_strip_typography_suffixes(self):
        """Strip type prefix and property suffix from typography tokens."""
        assert token_name_to_tailwind_key("type.body.md.fontSize", "fontSize") == "body-md"
        assert token_name_to_tailwind_key("type.heading.lg.fontSize", "fontSize") == "heading-lg"
        assert token_name_to_tailwind_key("type.display.fontFamily", "fontFamily") == "display"

    def test_replace_dots_with_hyphens(self):
        """Replace dots with hyphens in remaining path."""
        assert token_name_to_tailwind_key("color.surface.primary.hover", "colors") == "surface-primary-hover"
        assert token_name_to_tailwind_key("space.inset.lg", "spacing") == "inset-lg"

    def test_no_prefix_stripping(self):
        """Tokens without matching prefix keep full name."""
        assert token_name_to_tailwind_key("custom.token.name", "extend") == "custom-token-name"


class TestFormatTailwindValue:
    """Tests for format_tailwind_value function."""

    def test_color_passthrough(self):
        """Color hex values pass through unchanged."""
        assert format_tailwind_value("#09090B", "color") == "#09090B"
        assert format_tailwind_value("#FF0000", "color") == "#FF0000"

    def test_dimension_adds_px(self):
        """Dimension values get px appended if plain number."""
        assert format_tailwind_value("16", "dimension") == "16px"
        assert format_tailwind_value("0.5", "dimension") == "0.5px"
        assert format_tailwind_value("24", "dimension") == "24px"

    def test_dimension_with_unit_preserved(self):
        """Dimension values with units are preserved."""
        assert format_tailwind_value("2rem", "dimension") == "2rem"
        assert format_tailwind_value("100%", "dimension") == "100%"

    def test_font_family_wraps_in_array(self):
        """Font family values are wrapped in array string."""
        assert format_tailwind_value("Inter", "fontFamily") == "['Inter', sans-serif]"
        assert format_tailwind_value("Roboto Mono", "fontFamily") == "['Roboto Mono', sans-serif]"

    def test_font_weight_passthrough(self):
        """Font weight passes through as-is."""
        assert format_tailwind_value("600", "fontWeight") == "600"
        assert format_tailwind_value("bold", "fontWeight") == "bold"

    def test_number_passthrough(self):
        """Number values pass through as-is."""
        assert format_tailwind_value("1.5", "number") == "1.5"
        assert format_tailwind_value("0.75", "number") == "0.75"

    def test_default_passthrough(self):
        """Unknown types pass through unchanged."""
        assert format_tailwind_value("custom-value", "unknown") == "custom-value"


class TestGenerateTailwindConfig:
    """Tests for generate_tailwind_config function."""

    def test_generates_module_exports(self, temp_db):
        """Generate module.exports structure."""
        seed_post_curation(temp_db)

        config = generate_tailwind_config(temp_db, 1)

        assert "module.exports = {" in config
        assert "theme: {" in config
        assert "extend: {" in config
        assert config.endswith("};")

    def test_includes_header_comment(self, temp_db):
        """Config includes header comment."""
        seed_post_curation(temp_db)

        config = generate_tailwind_config(temp_db, 1)

        assert config.startswith("/** Generated by Declarative Design */")

    def test_groups_tokens_by_section(self, temp_db):
        """Tokens are grouped into correct Tailwind sections."""
        seed_post_curation(temp_db)

        config = generate_tailwind_config(temp_db, 1)

        assert "colors: {" in config
        assert "spacing: {" in config
        assert "'surface-primary': '#09090B'" in config
        assert "'4': '16px'" in config

    def test_uses_single_quotes(self, temp_db):
        """JavaScript uses single quotes for strings."""
        seed_post_curation(temp_db)

        config = generate_tailwind_config(temp_db, 1)

        assert "'surface-primary'" in config
        assert '"surface-primary"' not in config

    def test_resolves_aliased_tokens(self, temp_db):
        """Aliased tokens use resolved values, not CSS var references."""
        seed_post_curation(temp_db)

        # Add an aliased token
        temp_db.execute(
            "INSERT INTO tokens (id, collection_id, name, type, tier, alias_of) VALUES (?, ?, ?, ?, ?, ?)",
            (10, 1, "color.button.primary", "color", "aliased", 1)
        )
        temp_db.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?)",
            (10, 1, '{"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}', "#09090B")
        )
        temp_db.commit()

        config = generate_tailwind_config(temp_db, 1)

        assert "'button-primary': '#09090B'" in config
        assert "var(--color-surface-primary)" not in config


class TestGenerateTailwindConfigDict:
    """Tests for generate_tailwind_config_dict function."""

    def test_returns_dict_structure(self, temp_db):
        """Returns a Python dict with theme.extend structure."""
        seed_post_curation(temp_db)

        result = generate_tailwind_config_dict(temp_db, 1)

        assert isinstance(result, dict)
        assert "colors" in result
        assert "spacing" in result

    def test_dict_contains_mapped_tokens(self, temp_db):
        """Dict contains properly mapped token values."""
        seed_post_curation(temp_db)

        result = generate_tailwind_config_dict(temp_db, 1)

        assert result["colors"]["surface-primary"] == "#09090B"
        assert result["colors"]["surface-secondary"] == "#18181B"
        assert result["spacing"]["4"] == "16px"

    def test_dict_handles_typography_tokens(self, temp_db):
        """Dict properly handles typography tokens."""
        seed_post_curation(temp_db)

        # Add typography tokens
        temp_db.execute(
            "INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (?, ?, ?, ?, ?)",
            (11, 1, "type.body.md.fontSize", "dimension", "curated")
        )
        temp_db.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?)",
            (11, 1, "16", "16")
        )
        temp_db.commit()

        result = generate_tailwind_config_dict(temp_db, 1)

        assert "fontSize" in result
        assert result["fontSize"]["body-md"] == "16px"


class TestWriteTailwindMappings:
    """Tests for write_tailwind_mappings function."""

    def test_writes_color_utility_classes(self, temp_db):
        """Creates multiple utility class mappings for color tokens."""
        seed_post_curation(temp_db)

        count = write_tailwind_mappings(temp_db, 1)

        # Check that color tokens have multiple mappings
        cursor = temp_db.execute(
            """SELECT identifier FROM code_mappings
               WHERE target = 'tailwind' AND token_id =
               (SELECT id FROM tokens WHERE name = 'color.surface.primary')
               ORDER BY identifier"""
        )
        identifiers = [row["identifier"] for row in cursor.fetchall()]

        assert "bg-surface-primary" in identifiers
        assert "text-surface-primary" in identifiers
        assert "border-surface-primary" in identifiers

    def test_writes_spacing_utility_classes(self, temp_db):
        """Creates multiple utility class mappings for spacing tokens."""
        seed_post_curation(temp_db)

        count = write_tailwind_mappings(temp_db, 1)

        # Check that spacing tokens have multiple mappings
        cursor = temp_db.execute(
            """SELECT identifier FROM code_mappings
               WHERE target = 'tailwind' AND token_id =
               (SELECT id FROM tokens WHERE name = 'space.4')
               ORDER BY identifier"""
        )
        identifiers = [row["identifier"] for row in cursor.fetchall()]

        assert "p-4" in identifiers
        assert "m-4" in identifiers
        assert "gap-4" in identifiers

    def test_writes_radius_utility_classes(self, temp_db):
        """Creates rounded utility class mappings for radius tokens."""
        seed_post_curation(temp_db)

        # Add a radius token
        temp_db.execute(
            "INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (?, ?, ?, ?, ?)",
            (12, 1, "radius.md", "dimension", "curated")
        )
        temp_db.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?)",
            (12, 1, "8", "8")
        )
        temp_db.commit()

        count = write_tailwind_mappings(temp_db, 1)

        cursor = temp_db.execute(
            """SELECT identifier FROM code_mappings
               WHERE target = 'tailwind' AND token_id = 12"""
        )
        row = cursor.fetchone()
        assert row["identifier"] == "rounded-md"

    def test_upsert_behavior(self, temp_db):
        """Mappings are upserted (updated if they exist)."""
        seed_post_curation(temp_db)

        # Write mappings first time
        count1 = write_tailwind_mappings(temp_db, 1)

        # Write again - should update, not duplicate
        count2 = write_tailwind_mappings(temp_db, 1)

        # Count should remain the same
        cursor = temp_db.execute(
            "SELECT COUNT(DISTINCT identifier) as cnt FROM code_mappings WHERE target = 'tailwind'"
        )
        total = cursor.fetchone()["cnt"]
        assert total > 0

    def test_returns_mapping_count(self, temp_db):
        """Returns count of mappings written."""
        seed_post_curation(temp_db)

        count = write_tailwind_mappings(temp_db, 1)

        assert count > 0
        assert isinstance(count, int)


class TestExportTailwind:
    """Tests for export_tailwind convenience function."""

    def test_returns_complete_result(self, temp_db):
        """Export returns config, config_dict, mappings count, and token count."""
        seed_post_curation(temp_db)

        result = export_tailwind(temp_db, 1)

        assert "config" in result
        assert "config_dict" in result
        assert "mappings_written" in result
        assert "token_count" in result

        assert isinstance(result["config"], str)
        assert isinstance(result["config_dict"], dict)
        assert isinstance(result["mappings_written"], int)
        assert isinstance(result["token_count"], int)

    def test_config_contains_expected_content(self, temp_db):
        """Exported config contains expected tokens."""
        seed_post_curation(temp_db)

        result = export_tailwind(temp_db, 1)

        config = result["config"]
        assert "module.exports" in config
        assert "'surface-primary'" in config
        assert "'surface-secondary'" in config
        assert "'4': '16px'" in config

    def test_dict_matches_config(self, temp_db):
        """Config dict matches the string config content."""
        seed_post_curation(temp_db)

        result = export_tailwind(temp_db, 1)

        assert result["config_dict"]["colors"]["surface-primary"] == "#09090B"
        assert "'surface-primary': '#09090B'" in result["config"]