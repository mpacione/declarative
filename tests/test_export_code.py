"""Unit tests for all code export modules (CSS, Tailwind, DTCG)."""

import json
import pytest
import sqlite3
from datetime import datetime

from dd.export_css import (
    token_name_to_css_var,
    format_css_value,
    query_css_tokens,
    generate_css_for_collection,
    generate_css,
    write_code_mappings,
    export_css
)
from dd.export_tailwind import (
    TAILWIND_SECTION_MAP,
    map_token_to_tailwind_section,
    token_name_to_tailwind_key,
    format_tailwind_value,
    generate_tailwind_config,
    generate_tailwind_config_dict,
    write_tailwind_mappings,
    export_tailwind
)
from dd.export_dtcg import (
    DTCG_TYPE_MAP,
    TYPOGRAPHY_FIELDS,
    SHADOW_FIELDS,
    build_alias_reference,
    format_dtcg_value,
    assemble_composite_typography,
    assemble_composite_shadow,
    query_dtcg_tokens,
    build_token_tree,
    generate_dtcg_dict,
    generate_dtcg_json,
    export_dtcg
)

from tests.fixtures import seed_post_curation


# Helper functions
def _seed_with_typography_tokens(db: sqlite3.Connection) -> None:
    """Add typography atomic tokens after seed_post_curation."""
    # Typography collection
    db.execute("INSERT INTO token_collections (id, file_id, name) VALUES (?, ?, ?)",
               (3, 1, "Typography"))

    # Typography mode
    db.execute("INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (?, ?, ?, ?)",
               (3, 3, "Default", 1))

    # Typography tokens
    tokens = [
        (6, 3, "type.body.md.fontFamily", "fontFamily"),
        (7, 3, "type.body.md.fontSize", "dimension"),
        (8, 3, "type.body.md.fontWeight", "fontWeight"),
        (9, 3, "type.body.md.lineHeight", "dimension"),
    ]
    for token_id, collection_id, name, token_type in tokens:
        db.execute("INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (?, ?, ?, ?, ?)",
                   (token_id, collection_id, name, token_type, "curated"))

    # Typography values
    values = [
        (6, 6, 3, "Inter", "Inter"),
        (7, 7, 3, "16", "16"),
        (8, 8, 3, "600", "600"),
        (9, 9, 3, "24", "24"),
    ]
    for value_id, token_id, mode_id, raw_value, resolved_value in values:
        db.execute("INSERT INTO token_values (id, token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?, ?)",
                   (value_id, token_id, mode_id, raw_value, resolved_value))

    db.commit()


def _seed_with_shadow_tokens(db: sqlite3.Connection) -> None:
    """Add shadow atomic tokens after seed_post_curation."""
    # Shadow collection
    db.execute("INSERT INTO token_collections (id, file_id, name) VALUES (?, ?, ?)",
               (4, 1, "Shadows"))

    # Shadow mode
    db.execute("INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (?, ?, ?, ?)",
               (4, 4, "Default", 1))

    # Shadow tokens
    tokens = [
        (10, 4, "shadow.sm.color", "color"),
        (11, 4, "shadow.sm.radius", "dimension"),
        (12, 4, "shadow.sm.offsetX", "dimension"),
        (13, 4, "shadow.sm.offsetY", "dimension"),
        (14, 4, "shadow.sm.spread", "dimension"),
    ]
    for token_id, collection_id, name, token_type in tokens:
        db.execute("INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (?, ?, ?, ?, ?)",
                   (token_id, collection_id, name, token_type, "curated"))

    # Shadow values
    values = [
        (10, 10, 4, "#0000001A", "#0000001A"),
        (11, 11, 4, "6", "6"),
        (12, 12, 4, "0", "0"),
        (13, 13, 4, "4", "4"),
        (14, 14, 4, "-1", "-1"),
    ]
    for value_id, token_id, mode_id, raw_value, resolved_value in values:
        db.execute("INSERT INTO token_values (id, token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?, ?)",
                   (value_id, token_id, mode_id, raw_value, resolved_value))

    db.commit()


def _add_dark_mode(db: sqlite3.Connection) -> None:
    """Add Dark mode to Colors collection with inverted values."""
    # Add Dark mode to Colors collection (collection_id=1)
    db.execute("INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (?, ?, ?, ?)",
               (10, 1, "Dark", 0))

    # Add Dark mode values for existing color tokens
    values = [
        (20, 1, 10, json.dumps({"r": 1, "g": 1, "b": 1, "a": 1}), "#FFFFFF"),  # color.surface.primary inverted
        (21, 2, 10, json.dumps({"r": 0.9, "g": 0.9, "b": 0.9, "a": 1}), "#E5E5E5"),  # color.surface.secondary inverted
        (22, 3, 10, json.dumps({"r": 0.2, "g": 0.2, "b": 0.2, "a": 1}), "#333333"),  # color.border.default inverted
        (23, 4, 10, json.dumps({"r": 0.035, "g": 0.035, "b": 0.043, "a": 1}), "#09090B"),  # color.text.primary inverted
    ]
    for value_id, token_id, mode_id, raw_value, resolved_value in values:
        db.execute("INSERT INTO token_values (id, token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?, ?)",
                   (value_id, token_id, mode_id, raw_value, resolved_value))

    db.commit()


# CSS Tests (16 tests)
@pytest.mark.unit
def test_css_var_name_basic():
    """Test converting basic token name to CSS variable."""
    assert token_name_to_css_var("color.surface.primary") == "--color-surface-primary"


@pytest.mark.unit
def test_css_var_name_numeric():
    """Test converting numeric token name to CSS variable."""
    assert token_name_to_css_var("space.4") == "--space-4"


@pytest.mark.unit
def test_css_var_name_deep():
    """Test converting deeply nested token name to CSS variable."""
    assert token_name_to_css_var("type.body.md.fontSize") == "--type-body-md-fontSize"


@pytest.mark.unit
def test_css_value_color():
    """Test formatting color value for CSS."""
    assert format_css_value("#09090B", "color") == "#09090B"


@pytest.mark.unit
def test_css_value_color_alpha():
    """Test formatting color with alpha channel for CSS."""
    # 8-digit hex #FFFFFF80 (50% opacity) -> rgba
    result = format_css_value("#FFFFFF80", "color")
    assert result == "rgba(255, 255, 255, 0.502)"


@pytest.mark.unit
def test_css_value_dimension():
    """Test formatting dimension value for CSS."""
    assert format_css_value("16", "dimension") == "16px"


@pytest.mark.unit
def test_css_value_font_family():
    """Test formatting font family value for CSS."""
    assert format_css_value("Inter", "fontFamily") == '"Inter"'


@pytest.mark.unit
def test_css_value_font_weight():
    """Test formatting font weight value for CSS."""
    assert format_css_value("600", "fontWeight") == "600"


@pytest.mark.unit
def test_css_value_auto():
    """Test formatting AUTO dimension value for CSS."""
    assert format_css_value("AUTO", "dimension") == "auto"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_css_generate_root_block(db):
    """Test CSS generation contains :root block with variables."""
    seed_post_curation(db)
    css = generate_css(db, 1)

    assert ":root {" in css
    assert "--color-surface-primary" in css
    assert "#09090B" in css


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_css_generate_header(db):
    """Test CSS generation starts with proper header."""
    seed_post_curation(db)
    css = generate_css(db, 1)

    assert css.startswith("/* Generated by")
    assert "Declarative Design" in css


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_css_multimode(db):
    """Test CSS generation with multiple modes."""
    seed_post_curation(db)
    _add_dark_mode(db)
    css = generate_css(db, 1)

    assert ':root {' in css
    assert '[data-theme="Dark"]' in css
    # Dark mode should have inverted primary color
    assert '#FFFFFF' in css


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_css_alias_uses_var(db):
    """Test CSS generation uses var() for aliases."""
    seed_post_curation(db)

    # Create an alias token - use empty JSON object for raw_value
    db.execute("INSERT INTO tokens (id, collection_id, name, type, tier, alias_of) VALUES (?, ?, ?, ?, ?, ?)",
               (100, 1, "color.brand.primary", "color", "aliased", 1))
    db.execute("INSERT INTO token_values (id, token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?, ?)",
               (100, 100, 1, "{}", "#09090B"))
    db.commit()

    css = generate_css(db, 1)

    # Should use var() reference to target
    assert "--color-brand-primary: var(--color-surface-primary);" in css


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_css_write_mappings(db):
    """Test writing CSS code mappings to database."""
    seed_post_curation(db)

    count = write_code_mappings(db, 1)

    # Should have written mappings for all 5 curated tokens
    assert count == 5

    # Verify mappings exist
    cursor = db.execute("SELECT COUNT(*) FROM code_mappings WHERE target = 'css'")
    assert cursor.fetchone()[0] == 5


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_css_write_mappings_idempotent(db):
    """Test that writing CSS mappings twice is idempotent."""
    seed_post_curation(db)

    count1 = write_code_mappings(db, 1)
    count2 = write_code_mappings(db, 1)

    # Both calls should report same count
    assert count1 == count2

    # Should still only have 5 mappings (UPSERT)
    cursor = db.execute("SELECT COUNT(*) FROM code_mappings WHERE target = 'css'")
    assert cursor.fetchone()[0] == 5


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_css_export_returns_dict(db):
    """Test export_css returns proper dictionary."""
    seed_post_curation(db)

    result = export_css(db, 1)

    assert isinstance(result, dict)
    assert "css" in result
    assert "mappings_written" in result
    assert "token_count" in result
    assert result["token_count"] == 5


# Tailwind Tests (12 tests)
@pytest.mark.unit
def test_tailwind_section_color():
    """Test mapping color token to Tailwind section."""
    assert map_token_to_tailwind_section("color.surface.primary", "color") == "colors"


@pytest.mark.unit
def test_tailwind_section_spacing():
    """Test mapping spacing token to Tailwind section."""
    assert map_token_to_tailwind_section("space.4", "dimension") == "spacing"


@pytest.mark.unit
def test_tailwind_section_radius():
    """Test mapping radius token to Tailwind section."""
    assert map_token_to_tailwind_section("radius.md", "dimension") == "borderRadius"


@pytest.mark.unit
def test_tailwind_section_font_size():
    """Test mapping font size token to Tailwind section."""
    assert map_token_to_tailwind_section("type.body.md.fontSize", "dimension") == "fontSize"


@pytest.mark.unit
def test_tailwind_key_color():
    """Test generating Tailwind key for color token."""
    assert token_name_to_tailwind_key("color.surface.primary", "colors") == "surface-primary"


@pytest.mark.unit
def test_tailwind_key_spacing():
    """Test generating Tailwind key for spacing token."""
    assert token_name_to_tailwind_key("space.4", "spacing") == "4"


@pytest.mark.unit
def test_tailwind_key_radius():
    """Test generating Tailwind key for radius token."""
    assert token_name_to_tailwind_key("radius.md", "borderRadius") == "md"


@pytest.mark.unit
def test_tailwind_value_hex():
    """Test formatting hex color for Tailwind."""
    assert format_tailwind_value("#09090B", "color") == "#09090B"


@pytest.mark.unit
def test_tailwind_value_dimension():
    """Test formatting dimension value for Tailwind."""
    assert format_tailwind_value("16", "dimension") == "16px"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_tailwind_generate_config(db):
    """Test Tailwind config generation."""
    seed_post_curation(db)
    config = generate_tailwind_config(db, 1)

    assert "module.exports" in config
    assert "theme" in config
    assert "colors" in config


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_tailwind_config_dict(db):
    """Test Tailwind config dict generation."""
    seed_post_curation(db)
    config_dict = generate_tailwind_config_dict(db, 1)

    assert "colors" in config_dict
    assert "surface-primary" in config_dict["colors"]
    assert config_dict["colors"]["surface-primary"] == "#09090B"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_tailwind_write_mappings(db):
    """Test writing Tailwind code mappings."""
    seed_post_curation(db)

    count = write_tailwind_mappings(db, 1)

    # Should have written multiple mappings per token (bg-, text-, border- for colors)
    assert count > 5

    # Verify mappings exist
    cursor = db.execute("SELECT COUNT(*) FROM code_mappings WHERE target = 'tailwind'")
    assert cursor.fetchone()[0] > 0


# DTCG Tests (18 tests)
@pytest.mark.unit
def test_dtcg_alias_reference():
    """Test building DTCG alias reference syntax."""
    assert build_alias_reference("color.surface.primary") == "{color.surface.primary}"


@pytest.mark.unit
def test_dtcg_value_color():
    """Test formatting color value for DTCG."""
    assert format_dtcg_value("#09090B", "color") == "#09090B"


@pytest.mark.unit
def test_dtcg_value_dimension():
    """Test formatting dimension value for DTCG."""
    result = format_dtcg_value("16", "dimension")
    assert isinstance(result, dict)
    assert result["value"] == 16
    assert result["unit"] == "px"


@pytest.mark.unit
def test_dtcg_value_dimension_auto():
    """Test formatting AUTO dimension value for DTCG."""
    assert format_dtcg_value("AUTO", "dimension") == "auto"


@pytest.mark.unit
def test_dtcg_value_font_weight():
    """Test formatting font weight value for DTCG."""
    assert format_dtcg_value("600", "fontWeight") == 600


@pytest.mark.unit
def test_dtcg_value_number():
    """Test formatting number value for DTCG."""
    assert format_dtcg_value("0.5", "number") == 0.5


@pytest.mark.unit
def test_dtcg_composite_typography():
    """Test assembling composite typography from atomics."""
    atomic_tokens = {
        "fontFamily": {"resolved_value": "Inter"},
        "fontSize": {"resolved_value": "16"},
        "fontWeight": {"resolved_value": "600"},
        "lineHeight": {"resolved_value": "24"}
    }

    result = assemble_composite_typography(atomic_tokens)

    assert result is not None
    assert result["$type"] == "typography"
    assert result["$value"]["fontFamily"] == "Inter"
    assert result["$value"]["fontSize"]["value"] == 16
    assert result["$value"]["fontWeight"] == 600
    assert result["$value"]["lineHeight"]["value"] == 24


@pytest.mark.unit
def test_dtcg_composite_typography_minimal():
    """Test assembling composite typography with minimal fields."""
    atomic_tokens = {
        "fontFamily": {"resolved_value": "Inter"},
        "fontSize": {"resolved_value": "16"}
    }

    result = assemble_composite_typography(atomic_tokens)

    assert result is not None
    assert result["$type"] == "typography"
    assert result["$value"]["fontFamily"] == "Inter"
    assert result["$value"]["fontSize"]["value"] == 16
    assert "fontWeight" not in result["$value"]


@pytest.mark.unit
def test_dtcg_composite_typography_insufficient():
    """Test assembling composite typography with insufficient fields."""
    atomic_tokens = {
        "fontFamily": {"resolved_value": "Inter"}
        # Missing fontSize
    }

    result = assemble_composite_typography(atomic_tokens)

    assert result is None


@pytest.mark.unit
def test_dtcg_composite_shadow():
    """Test assembling composite shadow from atomics."""
    atomic_tokens = {
        "color": {"resolved_value": "#0000001A"},
        "radius": {"resolved_value": "6"},
        "offsetX": {"resolved_value": "0"},
        "offsetY": {"resolved_value": "4"},
        "spread": {"resolved_value": "-1"}
    }

    result = assemble_composite_shadow(atomic_tokens)

    assert result is not None
    assert result["$type"] == "shadow"
    assert result["$value"]["color"] == "#0000001A"
    assert result["$value"]["blur"]["value"] == 6  # radius maps to blur
    assert result["$value"]["offsetX"]["value"] == 0
    assert result["$value"]["offsetY"]["value"] == 4
    assert result["$value"]["spread"]["value"] == -1


@pytest.mark.unit
def test_dtcg_composite_shadow_blur_mapping():
    """Test that radius maps to blur in shadow composite."""
    atomic_tokens = {
        "color": {"resolved_value": "#000000"},
        "radius": {"resolved_value": "10"}
    }

    result = assemble_composite_shadow(atomic_tokens)

    assert result is not None
    assert "blur" in result["$value"]
    assert result["$value"]["blur"]["value"] == 10
    assert "radius" not in result["$value"]


@pytest.mark.unit
def test_dtcg_token_tree_nesting():
    """Test building nested token tree structure."""
    tokens = [
        {
            "name": "color.surface.primary",
            "type": "color",
            "tier": "curated",
            "alias_target_name": None,
            "mode_name": "Default",
            "resolved_value": "#09090B"
        }
    ]

    tree = build_token_tree(tokens, "Default")

    assert "color" in tree
    assert "surface" in tree["color"]
    assert "primary" in tree["color"]["surface"]
    assert tree["color"]["surface"]["primary"]["$type"] == "color"
    assert tree["color"]["surface"]["primary"]["$value"] == "#09090B"


@pytest.mark.unit
def test_dtcg_token_tree_alias():
    """Test token tree with alias references."""
    tokens = [
        {
            "name": "color.brand.primary",
            "type": "color",
            "tier": "aliased",
            "alias_target_name": "color.surface.primary",
            "mode_name": "Default",
            "resolved_value": "#09090B"
        }
    ]

    tree = build_token_tree(tokens, "Default")

    assert tree["color"]["brand"]["primary"]["$value"] == "{color.surface.primary}"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_dtcg_generate_json_valid(db):
    """Test DTCG JSON generation is valid JSON."""
    seed_post_curation(db)

    json_str = generate_dtcg_json(db, 1)

    # Should parse without error
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)
    assert "$schema" in parsed


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_dtcg_generate_has_type_and_value(db):
    """Test DTCG JSON has $type and $value for tokens."""
    seed_post_curation(db)

    dtcg_dict = generate_dtcg_dict(db, 1)

    # Check a color token
    assert "$type" in dtcg_dict["color"]["surface"]["primary"]
    assert "$value" in dtcg_dict["color"]["surface"]["primary"]
    assert dtcg_dict["color"]["surface"]["primary"]["$type"] == "color"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_dtcg_multimode(db):
    """Test DTCG JSON with multiple modes."""
    seed_post_curation(db)
    _add_dark_mode(db)

    dtcg_dict = generate_dtcg_dict(db, 1)

    # Should have extensions for non-default modes
    token = dtcg_dict["color"]["surface"]["primary"]
    assert "$extensions" in token
    assert "org.design-tokens.modes" in token["$extensions"]
    assert "Dark" in token["$extensions"]["org.design-tokens.modes"]


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_dtcg_single_mode_no_extensions(db):
    """Test DTCG JSON with single mode has no extensions."""
    seed_post_curation(db)

    dtcg_dict = generate_dtcg_dict(db, 1)

    # Should not have extensions with only default mode
    token = dtcg_dict["color"]["surface"]["primary"]
    assert "$extensions" not in token


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_dtcg_export_writes_mappings(db):
    """Test DTCG export writes code mappings."""
    seed_post_curation(db)

    result = export_dtcg(db, 1)

    assert result["mappings_written"] > 0

    # Verify mappings exist
    cursor = db.execute("SELECT COUNT(*) FROM code_mappings WHERE target = 'dtcg'")
    assert cursor.fetchone()[0] > 0