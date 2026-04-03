"""CSS custom property export from curated design tokens."""

import sqlite3
from typing import Any


def token_name_to_css_var(token_name: str) -> str:
    """
    Convert a DTCG dot-path token name to a CSS custom property name.

    Args:
        token_name: Token name with dot-separated segments (e.g. "color.surface.primary")

    Returns:
        CSS custom property name (e.g. "--color-surface-primary")
    """
    if not token_name:
        return "--"
    return "--" + token_name.replace(".", "-")


def format_css_value(resolved_value: str, token_type: str) -> str:
    """
    Format a resolved_value for CSS output based on token type.

    Args:
        resolved_value: The resolved token value
        token_type: The token type (color, dimension, fontFamily, etc.)

    Returns:
        Formatted CSS value
    """
    if token_type == "color":
        # Handle 8-digit hex (with alpha) by converting to rgba
        if len(resolved_value) == 9 and resolved_value.startswith("#"):
            # Extract RGBA components
            r = int(resolved_value[1:3], 16)
            g = int(resolved_value[3:5], 16)
            b = int(resolved_value[5:7], 16)
            a = int(resolved_value[7:9], 16) / 255
            # Round alpha to 3 decimal places
            a = round(a, 3)
            # Format to avoid .0 for whole numbers
            if a == 1.0:
                return f"rgba({r}, {g}, {b}, 1)"
            return f"rgba({r}, {g}, {b}, {a})"
        return resolved_value

    elif token_type == "dimension":
        # Handle AUTO case
        if resolved_value.upper() == "AUTO":
            return "auto"
        # Add px if plain number
        if resolved_value.isdigit():
            return f"{resolved_value}px"
        # Check if it's a decimal number without unit
        try:
            float(resolved_value)
            return f"{resolved_value}px"
        except ValueError:
            # Already has a unit or is not a number
            return resolved_value

    elif token_type == "fontFamily":
        # Add quotes if not already quoted
        if not (resolved_value.startswith('"') and resolved_value.endswith('"')):
            return f'"{resolved_value}"'
        return resolved_value

    elif token_type == "fontWeight" or token_type == "number":
        # Pass through as-is
        return resolved_value

    # Unknown types pass through unchanged
    return resolved_value


def query_css_tokens(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
    """
    Query curated/aliased tokens with their resolved values per mode.

    Args:
        conn: Database connection
        file_id: File ID to query tokens for

    Returns:
        List of token dictionaries with all columns from v_resolved_tokens
    """
    cursor = conn.execute("""
        SELECT vrt.id, vrt.name, vrt.type, vrt.tier, vrt.collection_id,
               vrt.alias_target_name, vrt.mode_id, vrt.mode_name, vrt.resolved_value
        FROM v_resolved_tokens vrt
        JOIN token_collections tc ON vrt.collection_id = tc.id
        WHERE tc.file_id = ? AND vrt.tier IN ('curated', 'aliased')
        ORDER BY vrt.name, vrt.mode_name
    """, (file_id,))

    # Convert Row objects to dicts
    results = []
    for row in cursor.fetchall():
        results.append({
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "tier": row["tier"],
            "collection_id": row["collection_id"],
            "alias_target_name": row["alias_target_name"],
            "mode_id": row["mode_id"],
            "mode_name": row["mode_name"],
            "resolved_value": row["resolved_value"]
        })

    return results


def generate_css_for_collection(tokens: list[dict[str, Any]], default_mode_name: str) -> str:
    """
    Generate CSS for a collection with all its modes.

    Args:
        tokens: List of token dicts (all from same collection, all modes included)
        default_mode_name: Name of the default mode for :root block

    Returns:
        CSS string with :root and [data-theme] blocks
    """
    if not tokens:
        return ""

    # Group tokens by mode
    tokens_by_mode: dict[str, list[dict[str, Any]]] = {}
    for token in tokens:
        mode_name = token["mode_name"]
        if mode_name not in tokens_by_mode:
            tokens_by_mode[mode_name] = []
        tokens_by_mode[mode_name].append(token)

    css_parts = []

    # Generate :root block for default mode
    if default_mode_name in tokens_by_mode:
        css_parts.append(":root {")

        # Group by token name to handle multi-mode properly
        tokens_by_name: dict[str, dict[str, Any]] = {}
        for token in tokens_by_mode[default_mode_name]:
            tokens_by_name[token["name"]] = token

        # Generate CSS variables
        for token_name in sorted(tokens_by_name.keys()):
            token = tokens_by_name[token_name]
            css_var_name = token_name_to_css_var(token["name"])

            if token["tier"] == "aliased" and token["alias_target_name"]:
                # Aliased token - use var() reference
                target_var = token_name_to_css_var(token["alias_target_name"])
                css_parts.append(f"  {css_var_name}: var({target_var});")
            else:
                # Regular token - use formatted value
                css_value = format_css_value(token["resolved_value"], token["type"])
                css_parts.append(f"  {css_var_name}: {css_value};")

        css_parts.append("}")

    # Generate [data-theme] blocks for non-default modes
    for mode_name, mode_tokens in sorted(tokens_by_mode.items()):
        if mode_name == default_mode_name:
            continue

        css_parts.append("")
        css_parts.append(f'[data-theme="{mode_name}"] {{')

        # Group by token name
        tokens_by_name: dict[str, dict[str, Any]] = {}
        for token in mode_tokens:
            tokens_by_name[token["name"]] = token

        # Generate CSS variables
        for token_name in sorted(tokens_by_name.keys()):
            token = tokens_by_name[token_name]
            css_var_name = token_name_to_css_var(token["name"])

            if token["tier"] == "aliased" and token["alias_target_name"]:
                # Aliased token - use var() reference
                target_var = token_name_to_css_var(token["alias_target_name"])
                css_parts.append(f"  {css_var_name}: var({target_var});")
            else:
                # Regular token - use formatted value
                css_value = format_css_value(token["resolved_value"], token["type"])
                css_parts.append(f"  {css_var_name}: {css_value};")

        css_parts.append("}")

    return "\n".join(css_parts)


def generate_css(conn: sqlite3.Connection, file_id: int) -> str:
    """
    Generate complete CSS custom properties for a file.

    Args:
        conn: Database connection
        file_id: File ID to generate CSS for

    Returns:
        Complete CSS string with header and all collections
    """
    # Get file name for header
    cursor = conn.execute("SELECT name FROM files WHERE id = ?", (file_id,))
    file_row = cursor.fetchone()
    file_name = file_row["name"] if file_row else f"File {file_id}"

    # Query all tokens
    tokens = query_css_tokens(conn, file_id)

    if not tokens:
        return f"/* Generated by Declarative Design */\n/* File: {file_name} */\n\n/* No curated tokens found */\n"

    # Group tokens by collection
    tokens_by_collection: dict[int, list[dict[str, Any]]] = {}
    for token in tokens:
        collection_id = token["collection_id"]
        if collection_id not in tokens_by_collection:
            tokens_by_collection[collection_id] = []
        tokens_by_collection[collection_id].append(token)

    # Generate CSS parts
    css_parts = []
    css_parts.append("/* Generated by Declarative Design */")
    css_parts.append(f"/* File: {file_name} */")
    css_parts.append("")

    # Process each collection
    for collection_id in sorted(tokens_by_collection.keys()):
        collection_tokens = tokens_by_collection[collection_id]

        # Get default mode for this collection
        cursor = conn.execute(
            "SELECT name FROM token_modes WHERE collection_id = ? AND is_default = 1",
            (collection_id,)
        )
        default_row = cursor.fetchone()
        default_mode_name = default_row["name"] if default_row else "Default"

        # Generate CSS for this collection
        collection_css = generate_css_for_collection(collection_tokens, default_mode_name)
        if collection_css:
            css_parts.append(collection_css)

    return "\n".join(css_parts)


def write_code_mappings(conn: sqlite3.Connection, file_id: int) -> int:
    """
    Write code mappings for CSS variables to the database.

    Args:
        conn: Database connection
        file_id: File ID to write mappings for

    Returns:
        Number of mappings written
    """
    # Query curated/aliased tokens for this file
    cursor = conn.execute("""
        SELECT DISTINCT t.id, t.name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ? AND t.tier IN ('curated', 'aliased')
    """, (file_id,))

    count = 0
    for row in cursor.fetchall():
        token_id = row["id"]
        token_name = row["name"]
        css_var_name = token_name_to_css_var(token_name)

        # UPSERT the mapping
        conn.execute("""
            INSERT INTO code_mappings (token_id, target, identifier, file_path)
            VALUES (?, 'css', ?, 'tokens.css')
            ON CONFLICT(token_id, target, identifier)
            DO UPDATE SET file_path = excluded.file_path
        """, (token_id, css_var_name))

        count += 1

    conn.commit()
    return count


def export_css(conn: sqlite3.Connection, file_id: int) -> dict[str, Any]:
    """
    Convenience function that generates CSS and writes code mappings.

    Args:
        conn: Database connection
        file_id: File ID to export

    Returns:
        Dictionary with css, mappings_written, and token_count
    """
    css = generate_css(conn, file_id)
    mappings_written = write_code_mappings(conn, file_id)

    # Count unique tokens
    cursor = conn.execute("""
        SELECT COUNT(DISTINCT t.id) as count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ? AND t.tier IN ('curated', 'aliased')
    """, (file_id,))
    token_count = cursor.fetchone()["count"]

    return {
        "css": css,
        "mappings_written": mappings_written,
        "token_count": token_count
    }