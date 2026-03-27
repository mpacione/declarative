"""Unit tests for mode creation functionality."""

import json
import pytest
import sqlite3

from dd.modes import (
    create_mode,
    copy_values_from_default,
    apply_oklch_inversion,
    apply_high_contrast,
    apply_scale_factor,
    create_dark_mode,
    create_compact_mode,
    create_high_contrast_mode,
    create_theme,
    oklch_to_hex
)
from tests.fixtures import seed_post_curation


# Mode Creation Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_create_mode_basic(db):
    """Test creating a new mode in a collection."""
    seed_post_curation(db)

    # Create "Dark" mode in Colors collection
    mode_id = create_mode(db, 1, "Dark")

    # Verify mode created
    cursor = db.execute("""
        SELECT * FROM token_modes
        WHERE id = ? AND collection_id = 1 AND name = 'Dark'
    """, (mode_id,))
    mode = cursor.fetchone()

    assert mode is not None
    assert mode["name"] == "Dark"
    assert mode["is_default"] == 0  # Not default
    assert mode["collection_id"] == 1


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_create_mode_duplicate_raises(db):
    """Test that creating duplicate mode name raises ValueError."""
    seed_post_curation(db)

    # Create mode once
    create_mode(db, 1, "Dark")

    # Try to create again - should raise
    with pytest.raises(ValueError, match="Mode 'Dark' already exists"):
        create_mode(db, 1, "Dark")


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_create_mode_returns_id(db):
    """Test that create_mode returns a positive integer ID."""
    seed_post_curation(db)

    mode_id = create_mode(db, 1, "Dark")

    assert isinstance(mode_id, int)
    assert mode_id > 0


# Copy Values Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_copy_values_from_default(db):
    """Test copying token values from default mode to new mode."""
    seed_post_curation(db)

    # Create Dark mode
    dark_mode_id = create_mode(db, 1, "Dark")

    # Copy values from Default to Dark
    count = copy_values_from_default(db, 1, dark_mode_id)

    # Verify count (4 color tokens, all curated, non-aliased)
    assert count == 4

    # Verify values were copied
    cursor = db.execute("""
        SELECT tv.*, t.name
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ?
        ORDER BY t.name
    """, (dark_mode_id,))

    dark_values = list(cursor)
    assert len(dark_values) == 4

    # Check that values match Default mode values
    for value_row in dark_values:
        token_id = value_row["token_id"]

        # Get Default mode value for comparison
        cursor = db.execute("""
            SELECT resolved_value
            FROM token_values tv
            JOIN token_modes tm ON tv.mode_id = tm.id
            WHERE tv.token_id = ? AND tm.is_default = 1
        """, (token_id,))
        default_value = cursor.fetchone()["resolved_value"]

        assert value_row["resolved_value"] == default_value


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_copy_values_no_default_raises(db):
    """Test that copy_values_from_default raises when no default mode exists."""
    seed_post_curation(db)

    # Create a new collection without default mode
    db.execute("INSERT INTO token_collections (id, file_id, name) VALUES (99, 1, 'Test')")
    db.execute("INSERT INTO token_modes (id, collection_id, name, is_default) VALUES (99, 99, 'NonDefault', 0)")
    db.commit()

    # Try to copy values - should raise
    with pytest.raises(ValueError, match="No default mode found"):
        copy_values_from_default(db, 99, 99)


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_copy_values_skips_aliased(db):
    """Test that copy_values_from_default skips aliased tokens."""
    seed_post_curation(db)

    # Add an aliased token
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier, alias_of)
        VALUES (99, 1, 'color.alias', 'color', 'aliased', 1)
    """)
    # Add a value for the aliased token in Default mode
    db.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (99, 1, '#AAAAAA', '#AAAAAA')
    """)
    db.commit()

    # Create Dark mode and copy values
    dark_mode_id = create_mode(db, 1, "Dark")
    count = copy_values_from_default(db, 1, dark_mode_id)

    # Should still be 4 (aliased token skipped)
    assert count == 4

    # Verify aliased token has no value in new mode
    cursor = db.execute("""
        SELECT COUNT(*) as cnt FROM token_values
        WHERE token_id = 99 AND mode_id = ?
    """, (dark_mode_id,))
    assert cursor.fetchone()["cnt"] == 0


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_copy_values_count(db):
    """Test that copy_values returns correct count of non-aliased tokens."""
    seed_post_curation(db)

    # Spacing collection has 1 spacing token
    spacing_collection_id = 2

    # Create new mode in Spacing collection
    new_mode_id = create_mode(db, spacing_collection_id, "Compact")

    # Copy values
    count = copy_values_from_default(db, spacing_collection_id, new_mode_id)

    # Should be 1 (the space.4 token)
    assert count == 1


# OKLCH Conversion Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_oklch_to_hex_white():
    """Test OKLCH to hex conversion for white."""
    hex_color = oklch_to_hex(1.0, 0.0, 0.0)

    # Parse hex to RGB values
    hex_clean = hex_color.lstrip('#')
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)

    # Should be close to white (within 2 in each channel)
    assert abs(r - 255) <= 2
    assert abs(g - 255) <= 2
    assert abs(b - 255) <= 2


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_oklch_to_hex_black():
    """Test OKLCH to hex conversion for black."""
    hex_color = oklch_to_hex(0.0, 0.0, 0.0)

    # Parse hex to RGB values
    hex_clean = hex_color.lstrip('#')
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)

    # Should be close to black (within 2 in each channel)
    assert abs(r - 0) <= 2
    assert abs(g - 0) <= 2
    assert abs(b - 0) <= 2


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_apply_oklch_inversion_inverts_colors(db):
    """Test that OKLCH inversion properly inverts colors."""
    seed_post_curation(db)

    # Create Dark mode and copy values
    dark_mode_id = create_mode(db, 1, "Dark")
    copy_values_from_default(db, 1, dark_mode_id)

    # Apply OKLCH inversion
    count = apply_oklch_inversion(db, 1, dark_mode_id)

    # Should have inverted 4 color tokens
    assert count == 4

    # Check that colors were inverted
    # color.surface.primary was #09090B (very dark), should become light
    cursor = db.execute("""
        SELECT tv.resolved_value, t.name
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'color.surface.primary'
    """, (dark_mode_id,))

    inverted_primary = cursor.fetchone()["resolved_value"]
    # Parse hex to check it's now light
    hex_clean = inverted_primary.lstrip('#')
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)
    avg_brightness = (r + g + b) / 3

    # Should be significantly brighter (> 200 average)
    assert avg_brightness > 200

    # color.text.primary was #FFFFFF (white), should become dark
    cursor = db.execute("""
        SELECT tv.resolved_value
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'color.text.primary'
    """, (dark_mode_id,))

    inverted_text = cursor.fetchone()["resolved_value"]
    hex_clean = inverted_text.lstrip('#')
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)
    avg_brightness = (r + g + b) / 3

    # Should be significantly darker (< 50 average)
    assert avg_brightness < 50


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_apply_oklch_inversion_only_colors(db):
    """Test that OKLCH inversion only affects color tokens, not dimensions."""
    seed_post_curation(db)

    # Add a spacing value to Colors collection to test it's not affected
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier)
        VALUES (100, 1, 'test.spacing', 'dimension', 'curated')
    """)
    db.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (100, 1, '24', '24')
    """)
    db.commit()

    # Create Dark mode and copy ALL values
    dark_mode_id = create_mode(db, 1, "Dark")
    db.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        SELECT tv.token_id, ?, tv.raw_value, tv.resolved_value
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = 1 AND t.collection_id = 1 AND t.alias_of IS NULL
    """, (dark_mode_id,))
    db.commit()

    # Apply OKLCH inversion
    count = apply_oklch_inversion(db, 1, dark_mode_id)

    # Should have inverted only the 4 color tokens, not the dimension
    assert count == 4

    # Verify spacing value unchanged
    cursor = db.execute("""
        SELECT resolved_value FROM token_values
        WHERE token_id = 100 AND mode_id = ?
    """, (dark_mode_id,))
    spacing_value = cursor.fetchone()["resolved_value"]
    assert spacing_value == "24"  # Unchanged


# Scale Factor Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_apply_scale_factor(db):
    """Test applying scale factor to dimension tokens."""
    seed_post_curation(db)

    # Create Compact mode in Spacing collection
    compact_mode_id = create_mode(db, 2, "Compact")

    # Copy values from default
    copy_values_from_default(db, 2, compact_mode_id)

    # Apply scale factor of 0.5
    count = apply_scale_factor(db, 2, compact_mode_id, 0.5)

    # Should have scaled 1 dimension token
    assert count == 1

    # Verify value was scaled from "16" to "8"
    cursor = db.execute("""
        SELECT tv.resolved_value
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'space.4'
    """, (compact_mode_id,))

    scaled_value = cursor.fetchone()["resolved_value"]
    assert scaled_value == "8"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_apply_scale_factor_skips_auto(db):
    """Test that scale factor skips AUTO values."""
    seed_post_curation(db)

    # Add a dimension token with AUTO value
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier)
        VALUES (101, 2, 'space.auto', 'dimension', 'curated')
    """)
    db.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (101, 2, 'AUTO', 'AUTO')
    """)
    db.commit()

    # Create Compact mode and copy values
    compact_mode_id = create_mode(db, 2, "Compact")
    db.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        SELECT tv.token_id, ?, tv.raw_value, tv.resolved_value
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = 2 AND t.collection_id = 2 AND t.alias_of IS NULL
    """, (compact_mode_id,))
    db.commit()

    # Apply scale factor
    count = apply_scale_factor(db, 2, compact_mode_id, 0.5)

    # Should have scaled only 1 (the numeric value, not AUTO)
    assert count == 1

    # Verify AUTO value unchanged
    cursor = db.execute("""
        SELECT resolved_value FROM token_values
        WHERE token_id = 101 AND mode_id = ?
    """, (compact_mode_id,))
    auto_value = cursor.fetchone()["resolved_value"]
    assert auto_value == "AUTO"  # Unchanged


# Convenience Function Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_create_dark_mode_full(db):
    """Test create_dark_mode convenience function."""
    seed_post_curation(db)

    result = create_dark_mode(db, 1, "Dark")

    # Check result structure
    assert "mode_id" in result
    assert "mode_name" in result
    assert "values_copied" in result
    assert "values_inverted" in result

    assert result["mode_name"] == "Dark"
    assert result["values_copied"] == 4  # 4 color tokens
    assert result["values_inverted"] == 4  # All colors inverted

    # Verify mode was created
    cursor = db.execute("""
        SELECT * FROM token_modes WHERE id = ?
    """, (result["mode_id"],))
    mode = cursor.fetchone()
    assert mode["name"] == "Dark"

    # Verify values were copied and inverted
    cursor = db.execute("""
        SELECT COUNT(*) as cnt FROM token_values WHERE mode_id = ?
    """, (result["mode_id"],))
    assert cursor.fetchone()["cnt"] == 4

    # Check that primary color was inverted (dark to light)
    cursor = db.execute("""
        SELECT tv.resolved_value
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'color.surface.primary'
    """, (result["mode_id"],))
    inverted = cursor.fetchone()["resolved_value"]

    # Should be light color now
    hex_clean = inverted.lstrip('#')
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)
    avg_brightness = (r + g + b) / 3
    assert avg_brightness > 200  # Light


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_create_theme_multi_collection(db):
    """Test creating a theme across multiple collections."""
    seed_post_curation(db)

    # Create dark theme across both Colors and Spacing collections
    result = create_theme(
        db,
        file_id=1,
        theme_name="Dark",
        collection_ids=None,  # Use all collections
        transform="dark",
        factor=1.0
    )

    # Check result
    assert result["theme_name"] == "Dark"
    assert result["collections_updated"] == 2  # Colors and Spacing
    assert result["total_values_copied"] == 5  # 4 colors + 1 spacing
    assert result["total_values_transformed"] == 4  # Only colors inverted

    # Verify Dark mode created in Colors collection
    cursor = db.execute("""
        SELECT id FROM token_modes
        WHERE collection_id = 1 AND name = 'Dark'
    """)
    colors_dark_mode = cursor.fetchone()
    assert colors_dark_mode is not None

    # Verify Dark mode created in Spacing collection
    cursor = db.execute("""
        SELECT id FROM token_modes
        WHERE collection_id = 2 AND name = 'Dark'
    """)
    spacing_dark_mode = cursor.fetchone()
    assert spacing_dark_mode is not None

    # Verify colors were inverted in Colors collection
    cursor = db.execute("""
        SELECT tv.resolved_value
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        JOIN token_modes tm ON tv.mode_id = tm.id
        WHERE t.name = 'color.surface.primary' AND tm.name = 'Dark'
    """)
    inverted_color = cursor.fetchone()["resolved_value"]

    # Should be light (inverted from dark #09090B)
    hex_clean = inverted_color.lstrip('#')
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)
    avg_brightness = (r + g + b) / 3
    assert avg_brightness > 200

    # Verify spacing was copied but NOT transformed
    cursor = db.execute("""
        SELECT tv.resolved_value
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        JOIN token_modes tm ON tv.mode_id = tm.id
        WHERE t.name = 'space.4' AND tm.name = 'Dark'
    """)
    spacing_value = cursor.fetchone()["resolved_value"]
    assert spacing_value == "16"  # Unchanged


# High Contrast Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_apply_high_contrast_pushes_light_colors_lighter(db):
    """Light colors should get pushed toward white in high contrast."""
    seed_post_curation(db)

    mode_id = create_mode(db, 1, "HighContrast")
    copy_values_from_default(db, 1, mode_id)
    apply_high_contrast(db, 1, mode_id)

    # color.border.default is #D4D4D8 (light gray, L~0.87)
    cursor = db.execute("""
        SELECT tv.resolved_value
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE t.name = 'color.border.default' AND tv.mode_id = ?
    """, (mode_id,))
    hc_value = cursor.fetchone()["resolved_value"]

    # Should be lighter than original (#D4D4D8 avg=212)
    hex_clean = hc_value.lstrip('#')
    r, g, b = int(hex_clean[0:2], 16), int(hex_clean[2:4], 16), int(hex_clean[4:6], 16)
    avg = (r + g + b) / 3
    assert avg > 220, f"Light color should be pushed lighter, got avg={avg} ({hc_value})"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_apply_high_contrast_pushes_dark_colors_darker(db):
    """Dark colors should get pushed toward black in high contrast."""
    seed_post_curation(db)

    mode_id = create_mode(db, 1, "HighContrast")
    copy_values_from_default(db, 1, mode_id)
    apply_high_contrast(db, 1, mode_id)

    # color.surface.primary is #09090B (near-black, L~0.03)
    cursor = db.execute("""
        SELECT tv.resolved_value
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE t.name = 'color.surface.primary' AND tv.mode_id = ?
    """, (mode_id,))
    hc_value = cursor.fetchone()["resolved_value"]

    hex_clean = hc_value.lstrip('#')
    r, g, b = int(hex_clean[0:2], 16), int(hex_clean[2:4], 16), int(hex_clean[4:6], 16)
    avg = (r + g + b) / 3
    assert avg < 15, f"Dark color should be pushed darker, got avg={avg} ({hc_value})"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_apply_high_contrast_skips_non_color_tokens(db):
    """Non-color tokens should be unchanged by high contrast transform."""
    seed_post_curation(db)

    # Apply to spacing collection (has no colors)
    mode_id = create_mode(db, 2, "HighContrast")
    copy_values_from_default(db, 2, mode_id)
    count = apply_high_contrast(db, 2, mode_id)

    assert count == 0


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_create_high_contrast_mode_convenience(db):
    """create_high_contrast_mode should create mode, copy values, and apply transform."""
    seed_post_curation(db)

    result = create_high_contrast_mode(db, 1)

    assert result["mode_name"] == "High Contrast"
    assert result["values_copied"] > 0
    assert result["values_transformed"] > 0
    assert result["mode_id"] > 0


# ---------------------------------------------------------------------------
# Value provenance: history rows written by transform functions
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.timeout(10)
def test_apply_oklch_inversion_writes_history(db):
    """apply_oklch_inversion should write a token_value_history row per inverted value."""
    seed_post_curation(db)

    dark_mode_id = create_mode(db, 1, "Dark")
    copy_values_from_default(db, 1, dark_mode_id)

    apply_oklch_inversion(db, 1, dark_mode_id)

    rows = db.execute(
        "SELECT changed_by, reason FROM token_value_history "
        "WHERE mode_id = ? AND reason = 'oklch_inversion'",
        (dark_mode_id,),
    ).fetchall()

    assert len(rows) == 4
    assert all(r["changed_by"] == "modes" for r in rows)


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_apply_scale_factor_writes_history(db):
    """apply_scale_factor should write a token_value_history row per scaled value."""
    seed_post_curation(db)

    compact_mode_id = create_mode(db, 2, "Compact")
    copy_values_from_default(db, 2, compact_mode_id)

    apply_scale_factor(db, 2, compact_mode_id, 0.5)

    rows = db.execute(
        "SELECT changed_by, reason FROM token_value_history "
        "WHERE mode_id = ? AND reason = 'scale_factor'",
        (compact_mode_id,),
    ).fetchall()

    assert len(rows) == 1
    assert rows[0]["changed_by"] == "modes"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_apply_high_contrast_writes_history(db):
    """apply_high_contrast should write a token_value_history row per transformed value."""
    seed_post_curation(db)

    mode_id = create_mode(db, 1, "HighContrast")
    copy_values_from_default(db, 1, mode_id)

    apply_high_contrast(db, 1, mode_id)

    rows = db.execute(
        "SELECT changed_by, reason FROM token_value_history "
        "WHERE mode_id = ? AND reason = 'high_contrast'",
        (mode_id,),
    ).fetchall()

    assert len(rows) == 4
    assert all(r["changed_by"] == "modes" for r in rows)