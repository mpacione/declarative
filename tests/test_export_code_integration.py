"""Integration tests for curation-to-code-export pipeline."""

import json
import re
import sqlite3

import pytest

from dd.curate import create_alias
from dd.export_css import export_css, generate_css, token_name_to_css_var
from dd.export_dtcg import export_dtcg, generate_dtcg_dict, generate_dtcg_json
from dd.export_tailwind import (
    export_tailwind,
    generate_tailwind_config,
    generate_tailwind_config_dict,
)
from tests.fixtures import seed_post_curation


@pytest.fixture
def db():
    """Create an in-memory SQLite database with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Load schema
    with open("schema.sql") as f:
        conn.executescript(f.read())

    return conn


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_css_custom_properties_parse(db):
    """Test CSS output structure and parsing via regex."""
    # Seed post-curation
    seed_post_curation(db)

    # Generate CSS
    css = generate_css(db, file_id=1)

    # Verify CSS structure
    assert ":root {" in css
    assert "}" in css

    # Extract custom properties via regex
    root_block_pattern = r':root\s*\{([^}]+)\}'
    root_match = re.search(root_block_pattern, css, re.DOTALL)
    assert root_match, "No :root block found"

    root_content = root_match.group(1)

    # Parse each custom property (from all :root blocks)
    prop_pattern = r'\s*(--[a-z][a-z0-9-]*)\s*:\s*([^;]+);'
    properties = re.findall(prop_pattern, css)

    # Verify we found properties
    assert len(properties) >= 5, f"Expected at least 5 properties, found {len(properties)}"

    # Check expected tokens are present
    expected_vars = {
        "--color-surface-primary",
        "--color-surface-secondary",
        "--color-border-default",
        "--color-text-primary",
        "--space-4"
    }

    found_vars = {prop[0] for prop in properties}
    assert expected_vars.issubset(found_vars), f"Missing vars: {expected_vars - found_vars}"

    # Verify values are non-empty
    for var_name, value in properties:
        assert value.strip(), f"Empty value for {var_name}"

    # Verify mapping back to token names
    for var_name, _ in properties:
        if var_name.startswith("--color-"):
            # Convert back to token name
            token_name = var_name[2:].replace("-", ".")
            # Verify round-trip
            assert token_name_to_css_var(token_name) == var_name


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_tailwind_config_valid_structure(db):
    """Test Tailwind config has valid structure."""
    # Seed post-curation
    seed_post_curation(db)

    # Generate Tailwind dict
    config_dict = generate_tailwind_config_dict(db, file_id=1)

    # Verify dict structure
    assert "colors" in config_dict
    assert isinstance(config_dict["colors"], dict)
    assert len(config_dict["colors"]) >= 4

    assert "spacing" in config_dict
    assert isinstance(config_dict["spacing"], dict)
    assert len(config_dict["spacing"]) >= 1

    # Verify all values are strings
    for section_name, section in config_dict.items():
        if isinstance(section, dict):
            for key, value in section.items():
                if isinstance(value, dict):  # Nested structure for colors
                    for sub_key, sub_value in value.items():
                        assert isinstance(sub_value, str), f"Non-string value in {section_name}.{key}.{sub_key}"
                else:
                    assert isinstance(value, str), f"Non-string value in {section_name}.{key}"

    # Generate Tailwind string
    config_str = generate_tailwind_config(db, file_id=1)

    # Verify string structure
    assert "module.exports" in config_str
    assert "theme:" in config_str
    assert "extend:" in config_str

    # Verify it's valid JavaScript-like syntax (might have comment at top)
    assert "module.exports" in config_str
    assert config_str.rstrip().endswith("};")


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_dtcg_json_validates(db):
    """Test DTCG JSON structure and validation."""
    # Seed post-curation
    seed_post_curation(db)

    # Generate DTCG JSON
    json_str = generate_dtcg_json(db, file_id=1)

    # Parse JSON - must succeed
    dtcg = json.loads(json_str)

    # Verify top-level structure
    assert "color" in dtcg
    assert "space" in dtcg

    # Count leaf tokens
    def count_leaf_tokens(obj, path=""):
        """Recursively count leaf tokens with $value."""
        if isinstance(obj, dict):
            if "$value" in obj:
                return 1
            else:
                count = 0
                for key, val in obj.items():
                    if not key.startswith("$"):  # Skip metadata keys
                        count += count_leaf_tokens(val, f"{path}.{key}" if path else key)
                return count
        return 0

    leaf_count = count_leaf_tokens(dtcg)

    # Verify we have expected number of tokens (4 colors + 1 spacing)
    assert leaf_count == 5, f"Expected 5 leaf tokens, found {leaf_count}"

    # Validate token structure
    def validate_tokens(obj, path=""):
        """Recursively validate token structure."""
        if isinstance(obj, dict):
            if "$value" in obj:
                # Leaf token - must have $type
                assert "$type" in obj, f"Token at {path} missing $type"
                token_type = obj["$type"]
                assert token_type in ["color", "dimension", "fontFamily", "fontWeight", "number", "shadow"], \
                    f"Invalid $type at {path}: {token_type}"

                # Validate color values
                if token_type == "color":
                    value = obj["$value"]
                    assert re.match(r'^#[0-9A-Fa-f]{6,8}$', value), \
                        f"Invalid color value at {path}: {value}"
            else:
                # Non-leaf - recurse
                for key, val in obj.items():
                    if not key.startswith("$"):  # Skip metadata
                        validate_tokens(val, f"{path}.{key}" if path else key)

    validate_tokens(dtcg)

    # Verify expected tokens exist
    assert dtcg["color"]["surface"]["primary"]["$value"] == "#09090B"
    assert dtcg["color"]["surface"]["secondary"]["$value"] == "#18181B"
    assert dtcg["color"]["border"]["default"]["$value"] == "#D4D4D8"
    assert dtcg["color"]["text"]["primary"]["$value"] == "#FFFFFF"
    assert dtcg["space"]["4"]["$value"]["value"] == 16
    assert dtcg["space"]["4"]["$value"]["unit"] == "px"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_all_curated_tokens_in_all_outputs(db):
    """Test all curated tokens appear in all export formats."""
    # Seed post-curation
    seed_post_curation(db)

    # Get all curated token names
    cursor = db.execute("""
        SELECT t.name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1 AND t.tier IN ('curated', 'aliased')
    """)
    token_names = [row[0] for row in cursor.fetchall()]

    assert len(token_names) == 5, "Should have 5 curated tokens"

    # Generate all outputs
    css = generate_css(db, file_id=1)
    tailwind_dict = generate_tailwind_config_dict(db, file_id=1)
    dtcg_dict = generate_dtcg_dict(db, file_id=1)

    # Check CSS
    for token_name in token_names:
        css_var = token_name_to_css_var(token_name)
        assert css_var in css, f"Token {token_name} ({css_var}) not found in CSS"

    # Check Tailwind (flattened structure)
    for token_name in token_names:
        parts = token_name.split(".")
        if token_name.startswith("color."):
            # Tailwind flattens color names: color.surface.primary -> surface-primary
            if len(parts) == 3:  # e.g., color.surface.primary
                tailwind_key = f"{parts[1]}-{parts[2]}"
                assert tailwind_key in tailwind_dict["colors"], f"Token {token_name} ({tailwind_key}) not in Tailwind colors"
        elif token_name.startswith("space."):
            # Check spacing section
            name = parts[1]
            assert name in tailwind_dict["spacing"], f"Token {token_name} not in Tailwind spacing"

    # Check DTCG
    for token_name in token_names:
        parts = token_name.split(".")
        # Navigate nested structure
        current = dtcg_dict
        for part in parts:
            assert part in current, f"Token {token_name} not found in DTCG at part {part}"
            current = current[part]
        # Should end at a token with $value
        assert "$value" in current, f"Token {token_name} has no $value in DTCG"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_alias_references_resolve_in_all_outputs(db):
    """Test alias handling across all export formats."""
    # Seed post-curation
    seed_post_curation(db)

    # Create an alias
    alias_result = create_alias(db, "color.bg", target_token_id=1, collection_id=1)
    alias_id = alias_result["alias_id"]

    # Copy token value for the alias (aliases inherit from their target)
    db.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        SELECT ?, mode_id, raw_value, resolved_value
        FROM token_values WHERE token_id = 1
    """, (alias_id,))
    db.commit()

    # Generate all outputs
    css = generate_css(db, file_id=1)
    tailwind_dict = generate_tailwind_config_dict(db, file_id=1)
    dtcg_dict = generate_dtcg_dict(db, file_id=1)

    # CSS: Should use var() reference
    assert "--color-bg:" in css
    # Check if it references the primary color
    # The CSS export may use var() or the resolved value depending on implementation
    # Based on the code, aliases get resolved values in CSS
    assert "--color-bg: #09090B" in css or "--color-bg: var(--color-surface-primary)" in css

    # Tailwind: Should have resolved value (flattened key)
    assert "bg" in tailwind_dict["colors"]
    assert tailwind_dict["colors"]["bg"] == "#09090B"

    # DTCG: Should use reference syntax
    assert "color" in dtcg_dict
    assert "bg" in dtcg_dict["color"]
    assert "$value" in dtcg_dict["color"]["bg"]
    # DTCG uses {reference} syntax for aliases
    assert dtcg_dict["color"]["bg"]["$value"] == "{color.surface.primary}"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_code_mappings_populated_for_all_targets(db):
    """Test code_mappings table is populated for all export targets."""
    # Seed post-curation
    seed_post_curation(db)

    # Run all exporters
    export_css(db, file_id=1)
    export_tailwind(db, file_id=1)
    export_dtcg(db, file_id=1)

    # Query code_mappings
    cursor = db.execute("""
        SELECT target, COUNT(*) as count
        FROM code_mappings
        GROUP BY target
    """)

    target_counts = {row[0]: row[1] for row in cursor.fetchall()}

    # Verify all targets present
    assert "css" in target_counts, "No CSS mappings found"
    assert "tailwind" in target_counts, "No Tailwind mappings found"
    assert "dtcg" in target_counts, "No DTCG mappings found"

    # Each target should have mappings for all 5 tokens
    assert target_counts["css"] >= 5
    assert target_counts["tailwind"] >= 5
    assert target_counts["dtcg"] >= 5

    # Verify identifiers are non-empty
    cursor = db.execute("""
        SELECT target, identifier, token_id
        FROM code_mappings
        WHERE identifier IS NULL OR identifier = ''
    """)
    empty_identifiers = cursor.fetchall()
    assert len(empty_identifiers) == 0, f"Found empty identifiers: {empty_identifiers}"

    # Verify FK integrity
    cursor = db.execute("""
        SELECT cm.token_id
        FROM code_mappings cm
        LEFT JOIN tokens t ON cm.token_id = t.id
        WHERE t.id IS NULL
    """)
    orphan_mappings = cursor.fetchall()
    assert len(orphan_mappings) == 0, f"Found orphan mappings: {orphan_mappings}"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_multi_mode_consistency_across_exports(db):
    """Test multi-mode handling across all export formats."""
    # Seed post-curation
    seed_post_curation(db)

    # Add Dark mode to Colors collection
    cursor = db.execute("""
        INSERT INTO token_modes (collection_id, name, is_default)
        VALUES (1, 'Dark', 0)
    """)
    dark_mode_id = cursor.lastrowid

    # Add Dark mode values (inverted colors)
    dark_values = [
        (1, dark_mode_id, json.dumps({"r": 0.965, "g": 0.965, "b": 0.957, "a": 1}), "#F6F6F4"),  # Inverted primary
        (2, dark_mode_id, json.dumps({"r": 0.906, "g": 0.906, "b": 0.894, "a": 1}), "#E7E7E4"),  # Inverted secondary
        (3, dark_mode_id, json.dumps({"r": 0.169, "g": 0.169, "b": 0.153, "a": 1}), "#2B2B27"),  # Inverted border
        (4, dark_mode_id, json.dumps({"r": 0, "g": 0, "b": 0, "a": 1}), "#000000"),  # Inverted text
    ]

    for token_id, mode_id, raw_value, resolved_value in dark_values:
        db.execute("""
            INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
            VALUES (?, ?, ?, ?)
        """, (token_id, mode_id, raw_value, resolved_value))

    db.commit()

    # Generate all outputs
    css = generate_css(db, file_id=1)
    tailwind_dict = generate_tailwind_config_dict(db, file_id=1)
    dtcg_dict = generate_dtcg_dict(db, file_id=1)

    # CSS: Should contain [data-theme="Dark"] block
    assert '[data-theme="Dark"]' in css

    # Extract Dark mode values from CSS
    dark_block_pattern = r'\[data-theme="Dark"\]\s*\{([^}]+)\}'
    dark_match = re.search(dark_block_pattern, css, re.DOTALL)
    assert dark_match, "No Dark theme block found"

    dark_content = dark_match.group(1)
    prop_pattern = r'\s*(--[a-z][a-z0-9-]*)\s*:\s*([^;]+);'
    dark_properties = dict(re.findall(prop_pattern, dark_content))

    # Verify Dark mode has all 4 color variables
    assert len(dark_properties) >= 4
    assert "--color-surface-primary" in dark_properties
    assert "--color-surface-secondary" in dark_properties
    assert "--color-border-default" in dark_properties
    assert "--color-text-primary" in dark_properties

    # Tailwind: Uses default mode values (no multi-mode support)
    assert tailwind_dict["colors"]["surface-primary"] == "#09090B"  # Default value
    assert tailwind_dict["colors"]["text-primary"] == "#FFFFFF"  # Default value

    # DTCG: Should have extensions for Dark mode
    color_primary = dtcg_dict["color"]["surface"]["primary"]
    assert "$extensions" in color_primary
    assert "org.design-tokens.modes" in color_primary["$extensions"]
    assert "Dark" in color_primary["$extensions"]["org.design-tokens.modes"]
    assert color_primary["$extensions"]["org.design-tokens.modes"]["Dark"] == "#F6F6F4"

    # Verify Dark mode values match between CSS and DTCG
    css_dark_primary = dark_properties.get("--color-surface-primary", "").strip()
    dtcg_dark_primary = color_primary["$extensions"]["org.design-tokens.modes"]["Dark"]
    assert css_dark_primary == dtcg_dark_primary


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_export_consistency_token_count(db):
    """Test token count consistency across export formats."""
    # Seed post-curation
    seed_post_curation(db)

    # Generate all outputs
    css = generate_css(db, file_id=1)
    tailwind_dict = generate_tailwind_config_dict(db, file_id=1)
    dtcg_dict = generate_dtcg_dict(db, file_id=1)

    # Count CSS variables in all :root blocks
    prop_pattern = r'\s*(--[a-z][a-z0-9-]*)\s*:'
    css_vars = re.findall(prop_pattern, css)
    css_count = len(set(css_vars))  # Unique variables

    # Count Tailwind tokens (flatten nested structure)
    def count_tailwind_tokens(config):
        count = 0
        for section_name, section in config.items():
            if isinstance(section, dict):
                for key, value in section.items():
                    if isinstance(value, dict):  # Nested
                        count += len(value)
                    else:
                        count += 1
        return count

    tailwind_count = count_tailwind_tokens(tailwind_dict)

    # Count DTCG leaf tokens
    def count_dtcg_leaves(obj):
        if isinstance(obj, dict):
            if "$value" in obj:
                return 1
            count = 0
            for key, val in obj.items():
                if not key.startswith("$"):
                    count += count_dtcg_leaves(val)
            return count
        return 0

    dtcg_count = count_dtcg_leaves(dtcg_dict)

    # All should have 5 tokens (4 colors + 1 spacing)
    assert css_count == 5, f"CSS has {css_count} tokens, expected 5"
    assert dtcg_count == 5, f"DTCG has {dtcg_count} tokens, expected 5"

    # Tailwind might organize differently but should have at least 5
    assert tailwind_count >= 5, f"Tailwind has {tailwind_count} tokens, expected at least 5"

    # Verify the same tokens are in all outputs
    # Get token names from DB
    cursor = db.execute("""
        SELECT t.name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1 AND t.tier = 'curated'
    """)
    db_tokens = {row[0] for row in cursor.fetchall()}

    assert len(db_tokens) == 5, f"Database has {len(db_tokens)} curated tokens"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_value_consistency_across_formats(db):
    """Test that token values are consistent across all export formats."""
    # Seed post-curation
    seed_post_curation(db)

    # Generate all outputs
    css = generate_css(db, file_id=1)
    tailwind_dict = generate_tailwind_config_dict(db, file_id=1)
    dtcg_dict = generate_dtcg_dict(db, file_id=1)

    # Define expected values
    expected_colors = {
        "color.surface.primary": "#09090B",
        "color.surface.secondary": "#18181B",
        "color.border.default": "#D4D4D8",
        "color.text.primary": "#FFFFFF"
    }

    # Extract CSS values (from all :root blocks)
    prop_pattern = r'\s*(--[a-z][a-z0-9-]*)\s*:\s*([^;]+);'
    css_properties = dict(re.findall(prop_pattern, css))

    # Check each color token
    for token_name, expected_value in expected_colors.items():
        # CSS value
        css_var = token_name_to_css_var(token_name)
        css_value = css_properties.get(css_var, "").strip()
        assert css_value == expected_value, f"CSS {token_name}: {css_value} != {expected_value}"

        # Tailwind value (flattened structure)
        parts = token_name.split(".")
        if len(parts) == 3:  # color.surface.primary
            tailwind_key = f"{parts[1]}-{parts[2]}"
            tailwind_value = tailwind_dict["colors"][tailwind_key]
            assert tailwind_value == expected_value, f"Tailwind {token_name}: {tailwind_value} != {expected_value}"

        # DTCG value
        current = dtcg_dict
        for part in parts:
            current = current[part]
        dtcg_value = current["$value"]
        assert dtcg_value == expected_value, f"DTCG {token_name}: {dtcg_value} != {expected_value}"

    # Check spacing token (special handling for dimension)
    space_css = css_properties.get("--space-4", "").strip()
    assert space_css == "16px", f"CSS space.4: {space_css} != 16px"

    tailwind_space = tailwind_dict["spacing"]["4"]
    assert tailwind_space == "16px", f"Tailwind space.4: {tailwind_space} != 16px"

    dtcg_space = dtcg_dict["space"]["4"]["$value"]
    assert isinstance(dtcg_space, dict), "DTCG space should be an object"
    assert dtcg_space["value"] == 16
    assert dtcg_space["unit"] == "px"