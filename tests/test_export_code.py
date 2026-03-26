"""Tests for code export functionality, specifically CSS custom properties."""

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