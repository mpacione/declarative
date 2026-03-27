"""Mode creation and value seeding for design tokens."""

import json
import math
import sqlite3
from typing import Any

from dd.color import hex_to_oklch, oklch_invert_lightness, rgba_to_hex


def create_mode(conn: sqlite3.Connection, collection_id: int, mode_name: str) -> int:
    """Create a new mode in a collection.

    Args:
        conn: Database connection
        collection_id: ID of the target collection
        mode_name: Name for the new mode

    Returns:
        ID of the created mode

    Raises:
        ValueError: If a mode with that name already exists in the collection
    """
    try:
        cursor = conn.execute(
            "INSERT INTO token_modes (collection_id, name, is_default) VALUES (?, ?, 0)",
            (collection_id, mode_name)
        )
        mode_id = cursor.lastrowid
        conn.commit()
        return mode_id
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            raise ValueError(f"Mode '{mode_name}' already exists in collection {collection_id}")
        raise


def copy_values_from_default(conn: sqlite3.Connection, collection_id: int, new_mode_id: int) -> int:
    """Copy all token values from the default mode to a new mode.

    Args:
        conn: Database connection
        collection_id: ID of the collection
        new_mode_id: ID of the target mode

    Returns:
        Count of values copied

    Raises:
        ValueError: If no default mode exists for the collection
    """
    # Find the default mode
    cursor = conn.execute(
        "SELECT id FROM token_modes WHERE collection_id = ? AND is_default = 1",
        (collection_id,)
    )
    row = cursor.fetchone()

    if not row:
        raise ValueError(f"No default mode found for collection {collection_id}")

    default_mode_id = row['id']

    # Copy values from default to new mode (skip aliased tokens)
    cursor = conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        SELECT tv.token_id, ?, tv.raw_value, tv.resolved_value
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.collection_id = ? AND t.alias_of IS NULL
    """, (new_mode_id, default_mode_id, collection_id))

    count = cursor.rowcount
    conn.commit()
    return count


def oklch_to_hex(L: float, C: float, h: float) -> str:
    """Convert OKLCH color to hex string.

    Args:
        L: Lightness (0-1)
        C: Chroma (0-0.4 typical)
        h: Hue in degrees (0-360)

    Returns:
        Hex color string (#RRGGBB uppercase)
    """
    try:
        from coloraide import Color
        c = Color('oklch', [L, C, h])
        c.fit('srgb')  # Bring out-of-gamut colors into range
        hex_val = c.convert('srgb').to_string(hex=True).upper()
        return hex_val
    except ImportError:
        # Manual conversion fallback
        return _oklch_to_hex_manual(L, C, h)


def _oklch_to_hex_manual(L: float, C: float, h: float) -> str:
    """Manual OKLCH to hex conversion.

    Args:
        L: Lightness (0-1)
        C: Chroma (0-0.4 typical)
        h: Hue in degrees (0-360)

    Returns:
        Hex color string (#RRGGBB uppercase)
    """
    # OKLCH to OKLAB
    h_rad = math.radians(h)
    a = C * math.cos(h_rad)
    b = C * math.sin(h_rad)

    # OKLAB to LMS (inverse of forward conversion)
    l = L + 0.3963377774 * a + 0.2158037573 * b
    m = L - 0.1055613458 * a - 0.0638541728 * b
    s = L - 0.0894841775 * a - 1.2914855480 * b

    # Cube to get LMS
    l_ = l * l * l
    m_ = m * m * m
    s_ = s * s * s

    # LMS to XYZ (D65)
    X = 1.2270138511 * l_ - 0.5577999807 * m_ + 0.2812561490 * s_
    Y = -0.0405801784 * l_ + 1.1122568696 * m_ - 0.0716766787 * s_
    Z = -0.0763812845 * l_ - 0.4214819784 * m_ + 1.5861632204 * s_

    # XYZ to Linear RGB
    R_lin = 3.2404541621 * X - 1.5371385940 * Y - 0.4985314096 * Z
    G_lin = -0.9692660305 * X + 1.8760108454 * Y + 0.0415560175 * Z
    B_lin = 0.0556434310 * X - 0.2040259135 * Y + 1.0572251882 * Z

    # Linear RGB to sRGB (apply gamma)
    def linear_to_srgb(c: float) -> float:
        # Clamp to [0, 1] first
        c = max(0.0, min(1.0, c))
        if c <= 0.0031308:
            return 12.92 * c
        else:
            return 1.055 * (c ** (1/2.4)) - 0.055

    r_srgb = linear_to_srgb(R_lin)
    g_srgb = linear_to_srgb(G_lin)
    b_srgb = linear_to_srgb(B_lin)

    # Convert to hex
    return rgba_to_hex(r_srgb, g_srgb, b_srgb)


def apply_oklch_inversion(conn: sqlite3.Connection, collection_id: int, mode_id: int) -> int:
    """Apply OKLCH lightness inversion to color tokens in a mode.

    Args:
        conn: Database connection
        collection_id: ID of the collection
        mode_id: ID of the mode to modify

    Returns:
        Count of values inverted
    """
    # Query all color values in the mode
    cursor = conn.execute("""
        SELECT tv.id, tv.resolved_value, t.type
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.collection_id = ? AND t.type = 'color'
    """, (mode_id, collection_id))

    rows = cursor.fetchall()
    count = 0

    for row in rows:
        value_id = row['id']
        hex_color = row['resolved_value']

        try:
            # Convert to OKLCH
            L, C, h = hex_to_oklch(hex_color)

            # Invert lightness
            new_L, new_C, new_h = oklch_invert_lightness(L, C, h)

            # Convert back to hex
            new_hex = oklch_to_hex(new_L, new_C, new_h)

            # Update the value
            conn.execute(
                "UPDATE token_values SET resolved_value = ?, raw_value = ? WHERE id = ?",
                (new_hex, json.dumps(new_hex), value_id)
            )
            count += 1
        except Exception:
            # Skip values that can't be converted
            pass

    conn.commit()
    return count


def apply_scale_factor(conn: sqlite3.Connection, collection_id: int, mode_id: int, factor: float) -> int:
    """Apply a scale factor to dimension tokens in a mode.

    Args:
        conn: Database connection
        collection_id: ID of the collection
        mode_id: ID of the mode to modify
        factor: Scale factor to apply

    Returns:
        Count of values scaled
    """
    # Query all dimension values in the mode
    cursor = conn.execute("""
        SELECT tv.id, tv.resolved_value, t.type
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.collection_id = ? AND t.type = 'dimension'
    """, (mode_id, collection_id))

    rows = cursor.fetchall()
    count = 0

    for row in rows:
        value_id = row['id']
        value_str = row['resolved_value']

        try:
            # Parse numeric value
            numeric_value = float(value_str)

            # Apply scale factor
            new_value = round(numeric_value * factor)

            # Update the value
            conn.execute(
                "UPDATE token_values SET resolved_value = ?, raw_value = ? WHERE id = ?",
                (str(new_value), json.dumps(new_value), value_id)
            )
            count += 1
        except (ValueError, TypeError):
            # Skip non-numeric values like "AUTO"
            pass

    conn.commit()
    return count


def create_dark_mode(conn: sqlite3.Connection, collection_id: int, mode_name: str = "Dark") -> dict[str, Any]:
    """Create a dark mode with OKLCH inversion.

    Args:
        conn: Database connection
        collection_id: ID of the collection
        mode_name: Name for the new mode (default: "Dark")

    Returns:
        Dictionary with mode creation details
    """
    # Create the mode
    mode_id = create_mode(conn, collection_id, mode_name)

    # Copy values from default
    values_copied = copy_values_from_default(conn, collection_id, mode_id)

    # Apply OKLCH inversion
    values_inverted = apply_oklch_inversion(conn, collection_id, mode_id)

    return {
        "mode_id": mode_id,
        "mode_name": mode_name,
        "values_copied": values_copied,
        "values_inverted": values_inverted
    }


def create_compact_mode(
    conn: sqlite3.Connection,
    collection_id: int,
    factor: float = 0.875,
    mode_name: str = "Compact"
) -> dict[str, Any]:
    """Create a compact/density mode with scale factor.

    Args:
        conn: Database connection
        collection_id: ID of the collection
        factor: Scale factor to apply (default: 0.875)
        mode_name: Name for the new mode (default: "Compact")

    Returns:
        Dictionary with mode creation details
    """
    # Create the mode
    mode_id = create_mode(conn, collection_id, mode_name)

    # Copy values from default
    values_copied = copy_values_from_default(conn, collection_id, mode_id)

    # Apply scale factor
    values_scaled = apply_scale_factor(conn, collection_id, mode_id, factor)

    return {
        "mode_id": mode_id,
        "mode_name": mode_name,
        "values_copied": values_copied,
        "values_scaled": values_scaled
    }


def apply_high_contrast(conn: sqlite3.Connection, collection_id: int, mode_id: int) -> int:
    """Apply high contrast transform to color tokens in a mode.

    Pushes light colors toward white and dark colors toward black,
    maximizing the contrast gap. Slightly boosts chroma for vivid colors.

    Args:
        conn: Database connection
        collection_id: ID of the collection
        mode_id: ID of the mode to modify

    Returns:
        Count of values transformed
    """
    cursor = conn.execute("""
        SELECT tv.id, tv.resolved_value, t.type
        FROM token_values tv
        JOIN tokens t ON tv.token_id = t.id
        WHERE tv.mode_id = ? AND t.collection_id = ? AND t.type = 'color'
    """, (mode_id, collection_id))

    rows = cursor.fetchall()
    count = 0

    for row in rows:
        value_id = row['id']
        hex_color = row['resolved_value']

        try:
            L, C, h = hex_to_oklch(hex_color)

            if L > 0.5:
                new_L = min(1.0, L * 1.2 + 0.1)
            else:
                new_L = max(0.0, L * 0.6)

            new_C = min(0.4, C * 1.15)

            new_hex = oklch_to_hex(new_L, new_C, h)

            conn.execute(
                "UPDATE token_values SET resolved_value = ?, raw_value = ? WHERE id = ?",
                (new_hex, json.dumps(new_hex), value_id)
            )
            count += 1
        except Exception:
            pass

    conn.commit()
    return count


def create_high_contrast_mode(
    conn: sqlite3.Connection,
    collection_id: int,
    mode_name: str = "High Contrast"
) -> dict[str, Any]:
    """Create a high contrast mode for accessibility.

    Args:
        conn: Database connection
        collection_id: ID of the collection
        mode_name: Name for the new mode (default: "High Contrast")

    Returns:
        Dictionary with mode creation details
    """
    mode_id = create_mode(conn, collection_id, mode_name)
    values_copied = copy_values_from_default(conn, collection_id, mode_id)
    values_transformed = apply_high_contrast(conn, collection_id, mode_id)

    return {
        "mode_id": mode_id,
        "mode_name": mode_name,
        "values_copied": values_copied,
        "values_transformed": values_transformed
    }


def create_theme(
    conn: sqlite3.Connection,
    file_id: int,
    theme_name: str,
    collection_ids: list[int] | None = None,
    transform: str | None = None,
    factor: float = 1.0
) -> dict[str, Any]:
    """Create a theme spanning multiple collections.

    Args:
        conn: Database connection
        file_id: ID of the file
        theme_name: Name for the theme/mode
        collection_ids: List of collection IDs to update (None for all)
        transform: Optional transform to apply ("dark", "compact", or None)
        factor: Scale factor for compact transform (default: 1.0)

    Returns:
        Dictionary with theme creation details
    """
    # Get target collections
    if collection_ids is None:
        cursor = conn.execute(
            "SELECT id FROM token_collections WHERE file_id = ?",
            (file_id,)
        )
        collection_ids = [row['id'] for row in cursor.fetchall()]

    collections_updated = 0
    total_values_copied = 0
    total_values_transformed = 0

    for collection_id in collection_ids:
        # Create mode in this collection
        mode_id = create_mode(conn, collection_id, theme_name)
        collections_updated += 1

        # Copy values from default
        values_copied = copy_values_from_default(conn, collection_id, mode_id)
        total_values_copied += values_copied

        # Apply transform if specified
        if transform == "dark":
            # Check if collection has color tokens
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM tokens WHERE collection_id = ? AND type = 'color'",
                (collection_id,)
            )
            if cursor.fetchone()['cnt'] > 0:
                values_transformed = apply_oklch_inversion(conn, collection_id, mode_id)
                total_values_transformed += values_transformed

        elif transform == "compact":
            # Check if collection has dimension tokens
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM tokens WHERE collection_id = ? AND type = 'dimension'",
                (collection_id,)
            )
            if cursor.fetchone()['cnt'] > 0:
                values_transformed = apply_scale_factor(conn, collection_id, mode_id, factor)
                total_values_transformed += values_transformed

    return {
        "theme_name": theme_name,
        "collections_updated": collections_updated,
        "total_values_copied": total_values_copied,
        "total_values_transformed": total_values_transformed
    }