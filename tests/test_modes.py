"""Tests for mode creation and value seeding."""

import pytest
import sqlite3
import json
from dd.modes import (
    create_mode,
    copy_values_from_default,
    apply_oklch_inversion,
    apply_scale_factor,
    create_dark_mode,
    create_compact_mode,
    create_theme,
    oklch_to_hex
)
from dd.db import init_db


@pytest.fixture
def conn():
    """Create an in-memory database with test data."""
    conn = init_db(":memory:")

    # Insert test file
    conn.execute("INSERT INTO files (file_key, name) VALUES ('test_file_key', 'Test')")

    # Insert test collection
    conn.execute("""
        INSERT INTO token_collections (file_id, name)
        VALUES (1, 'Test Collection')
    """)

    # Insert default mode
    conn.execute("""
        INSERT INTO token_modes (collection_id, name, is_default)
        VALUES (1, 'Default', 1)
    """)

    # Insert test tokens
    conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier)
        VALUES
            (1, 'color.primary', 'color', 'curated'),
            (1, 'color.secondary', 'color', 'curated'),
            (1, 'spacing.small', 'dimension', 'curated'),
            (1, 'spacing.large', 'dimension', 'curated'),
            (1, 'spacing.auto', 'dimension', 'curated')
    """)

    # Insert test values for default mode
    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES
            (1, 1, '"#0000FF"', '#0000FF'),
            (2, 1, '"#FF0000"', '#FF0000'),
            (3, 1, '8', '8'),
            (4, 1, '24', '24'),
            (5, 1, '"AUTO"', 'AUTO')
    """)

    conn.commit()
    yield conn
    conn.close()


def test_create_mode(conn):
    """Test creating a new mode."""
    mode_id = create_mode(conn, 1, "Dark")

    # Verify mode was created
    cursor = conn.execute(
        "SELECT * FROM token_modes WHERE id = ?", (mode_id,)
    )
    row = cursor.fetchone()

    assert row is not None
    assert row['name'] == 'Dark'
    assert row['collection_id'] == 1
    assert row['is_default'] == 0


def test_create_mode_duplicate_raises(conn):
    """Test that creating a duplicate mode raises ValueError."""
    create_mode(conn, 1, "Dark")

    with pytest.raises(ValueError) as exc_info:
        create_mode(conn, 1, "Dark")

    assert "already exists" in str(exc_info.value)


def test_copy_values_from_default(conn):
    """Test copying values from default mode."""
    mode_id = create_mode(conn, 1, "Dark")
    count = copy_values_from_default(conn, 1, mode_id)

    # Should copy 5 values (all non-aliased tokens)
    assert count == 5

    # Verify values were copied
    cursor = conn.execute(
        "SELECT COUNT(*) as cnt FROM token_values WHERE mode_id = ?",
        (mode_id,)
    )
    assert cursor.fetchone()['cnt'] == 5

    # Verify specific value was copied correctly
    cursor = conn.execute("""
        SELECT resolved_value FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'color.primary'
    """, (mode_id,))

    assert cursor.fetchone()['resolved_value'] == '#0000FF'


def test_copy_values_no_default_raises(conn):
    """Test that copying without a default mode raises ValueError."""
    # Create a collection without a default mode
    conn.execute("""
        INSERT INTO token_collections (file_id, name)
        VALUES (1, 'No Default Collection')
    """)

    mode_id = create_mode(conn, 2, "Test")

    with pytest.raises(ValueError) as exc_info:
        copy_values_from_default(conn, 2, mode_id)

    assert "No default mode" in str(exc_info.value)


def test_copy_values_skips_aliased(conn):
    """Test that copying skips aliased tokens."""
    # Add an aliased token
    conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, alias_of)
        VALUES (1, 'color.alias', 'color', 'aliased', 1)
    """)

    # Add value for the aliased token in default mode
    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (6, 1, '"#0000FF"', '#0000FF')
    """)

    mode_id = create_mode(conn, 1, "Dark")
    count = copy_values_from_default(conn, 1, mode_id)

    # Should still only copy 5 values (excluding the aliased token)
    assert count == 5


def test_apply_oklch_inversion(conn):
    """Test OKLCH lightness inversion for colors."""
    mode_id = create_mode(conn, 1, "Dark")
    copy_values_from_default(conn, 1, mode_id)

    count = apply_oklch_inversion(conn, 1, mode_id)

    # Should invert 2 color values
    assert count == 2

    # Check that color values were changed
    cursor = conn.execute("""
        SELECT resolved_value FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'color.primary'
    """, (mode_id,))

    new_color = cursor.fetchone()['resolved_value']
    # Blue (#0000FF) inverted should be much lighter
    assert new_color != '#0000FF'
    assert new_color.startswith('#')
    assert len(new_color) == 7


def test_apply_oklch_only_affects_colors(conn):
    """Test that OKLCH inversion only affects color tokens."""
    mode_id = create_mode(conn, 1, "Dark")
    copy_values_from_default(conn, 1, mode_id)

    # Get dimension value before
    cursor = conn.execute("""
        SELECT resolved_value FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'spacing.small'
    """, (mode_id,))
    spacing_before = cursor.fetchone()['resolved_value']

    apply_oklch_inversion(conn, 1, mode_id)

    # Check dimension value unchanged
    cursor = conn.execute("""
        SELECT resolved_value FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'spacing.small'
    """, (mode_id,))
    spacing_after = cursor.fetchone()['resolved_value']

    assert spacing_after == spacing_before


def test_oklch_to_hex_white():
    """Test OKLCH to hex conversion for white."""
    hex_val = oklch_to_hex(1.0, 0.0, 0.0)
    assert hex_val == '#FFFFFF'


def test_oklch_to_hex_black():
    """Test OKLCH to hex conversion for black."""
    hex_val = oklch_to_hex(0.0, 0.0, 0.0)
    assert hex_val == '#000000'


def test_oklch_to_hex_color():
    """Test OKLCH to hex conversion produces valid hex."""
    # Mid-lightness red
    hex_val = oklch_to_hex(0.5, 0.15, 30)

    assert hex_val.startswith('#')
    assert len(hex_val) == 7
    # Should be a valid hex color
    int(hex_val[1:], 16)


def test_apply_scale_factor(conn):
    """Test applying scale factor to dimensions."""
    mode_id = create_mode(conn, 1, "Compact")
    copy_values_from_default(conn, 1, mode_id)

    count = apply_scale_factor(conn, 1, mode_id, 0.5)

    # Should scale 2 numeric dimension values (not AUTO)
    assert count == 2

    # Check scaled values
    cursor = conn.execute("""
        SELECT resolved_value FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'spacing.small'
    """, (mode_id,))

    # 8 * 0.5 = 4
    assert cursor.fetchone()['resolved_value'] == '4'

    cursor = conn.execute("""
        SELECT resolved_value FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'spacing.large'
    """, (mode_id,))

    # 24 * 0.5 = 12
    assert cursor.fetchone()['resolved_value'] == '12'


def test_apply_scale_factor_skips_non_numeric(conn):
    """Test that scale factor skips non-numeric values."""
    mode_id = create_mode(conn, 1, "Compact")
    copy_values_from_default(conn, 1, mode_id)

    apply_scale_factor(conn, 1, mode_id, 0.5)

    # Check AUTO value unchanged
    cursor = conn.execute("""
        SELECT resolved_value FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'spacing.auto'
    """, (mode_id,))

    assert cursor.fetchone()['resolved_value'] == 'AUTO'


def test_create_dark_mode(conn):
    """Test convenience function for dark mode creation."""
    result = create_dark_mode(conn, 1, "MyDark")

    assert result['mode_name'] == 'MyDark'
    assert result['values_copied'] == 5
    assert result['values_inverted'] == 2
    assert isinstance(result['mode_id'], int)

    # Verify mode exists
    cursor = conn.execute(
        "SELECT * FROM token_modes WHERE id = ?",
        (result['mode_id'],)
    )
    assert cursor.fetchone()['name'] == 'MyDark'


def test_create_compact_mode(conn):
    """Test convenience function for compact mode creation."""
    result = create_compact_mode(conn, 1, 0.75, "MyCompact")

    assert result['mode_name'] == 'MyCompact'
    assert result['values_copied'] == 5
    assert result['values_scaled'] == 2
    assert isinstance(result['mode_id'], int)

    # Verify scaled value
    cursor = conn.execute("""
        SELECT resolved_value FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.name = 'spacing.small'
    """, (result['mode_id'],))

    # 8 * 0.75 = 6
    assert cursor.fetchone()['resolved_value'] == '6'


def test_create_theme_all_collections(conn):
    """Test creating theme across all collections."""
    # Add another collection with dimension tokens
    conn.execute("""
        INSERT INTO token_collections (file_id, name)
        VALUES (1, 'Spacing Collection')
    """)

    conn.execute("""
        INSERT INTO token_modes (collection_id, name, is_default)
        VALUES (2, 'Default', 1)
    """)

    conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier)
        VALUES (2, 'gap.small', 'dimension', 'curated')
    """)

    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (6, 2, '4', '4')
    """)

    result = create_theme(conn, 1, "MyTheme")

    assert result['theme_name'] == 'MyTheme'
    assert result['collections_updated'] == 2
    assert result['total_values_copied'] == 6  # 5 + 1
    assert result['total_values_transformed'] == 0  # No transform specified


def test_create_theme_dark_transform(conn):
    """Test creating theme with dark transform."""
    result = create_theme(conn, 1, "Dark", transform="dark")

    assert result['collections_updated'] == 1
    assert result['total_values_copied'] == 5
    assert result['total_values_transformed'] == 2  # Only color tokens


def test_create_theme_compact_transform(conn):
    """Test creating theme with compact transform."""
    result = create_theme(conn, 1, "Compact", transform="compact", factor=0.8)

    assert result['collections_updated'] == 1
    assert result['total_values_copied'] == 5
    assert result['total_values_transformed'] == 2  # Only numeric dimensions


def test_create_theme_specific_collections(conn):
    """Test creating theme for specific collections only."""
    # Add another collection that won't be updated
    conn.execute("""
        INSERT INTO token_collections (file_id, name)
        VALUES (1, 'Ignored Collection')
    """)

    result = create_theme(conn, 1, "MyTheme", collection_ids=[1])

    assert result['collections_updated'] == 1

    # Verify mode wasn't created in collection 2
    cursor = conn.execute(
        "SELECT COUNT(*) as cnt FROM token_modes WHERE collection_id = 2 AND name = 'MyTheme'"
    )
    assert cursor.fetchone()['cnt'] == 0


def test_mode_values_independent(conn):
    """Test that mode values are independent after creation."""
    # Create dark mode
    mode_id = create_mode(conn, 1, "Dark")
    copy_values_from_default(conn, 1, mode_id)

    # Modify value in new mode
    conn.execute("""
        UPDATE token_values
        SET resolved_value = '#AAAAAA'
        WHERE mode_id = ? AND token_id = 1
    """, (mode_id,))

    # Check original value unchanged
    cursor = conn.execute("""
        SELECT resolved_value FROM token_values
        WHERE mode_id = 1 AND token_id = 1
    """)
    assert cursor.fetchone()['resolved_value'] == '#0000FF'

    # Check new mode value changed
    cursor = conn.execute("""
        SELECT resolved_value FROM token_values
        WHERE mode_id = ? AND token_id = 1
    """, (mode_id,))
    assert cursor.fetchone()['resolved_value'] == '#AAAAAA'


def test_every_token_has_value_in_new_mode(conn):
    """Test that every non-aliased token has a value in the new mode."""
    mode_id = create_mode(conn, 1, "Complete")
    copy_values_from_default(conn, 1, mode_id)

    # Count non-aliased tokens
    cursor = conn.execute("""
        SELECT COUNT(*) as cnt FROM tokens
        WHERE collection_id = 1 AND alias_of IS NULL
    """)
    token_count = cursor.fetchone()['cnt']

    # Count values in new mode
    cursor = conn.execute("""
        SELECT COUNT(*) as cnt FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.collection_id = 1
    """, (mode_id,))
    value_count = cursor.fetchone()['cnt']

    assert value_count == token_count