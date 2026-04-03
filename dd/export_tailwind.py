"""Export design tokens to Tailwind CSS theme configuration."""

import sqlite3
from datetime import datetime

TAILWIND_SECTION_MAP = {
    "color.surface": "colors",
    "color.text": "colors",
    "color.border": "colors",
    "color.accent": "colors",
    "color": "colors",
    "space": "spacing",
    "radius": "borderRadius",
    "shadow": "boxShadow",
    "type": "fontSize",
    "opacity": "opacity",
}


def map_token_to_tailwind_section(token_name: str, token_type: str) -> str:
    """
    Determine which Tailwind theme section a token belongs to.

    Args:
        token_name: The DTCG token name (e.g., "color.surface.primary")
        token_type: The token type (e.g., "color", "dimension")

    Returns:
        The Tailwind section name (e.g., "colors", "spacing")
    """
    # Check for typography tokens by the final segment
    if ".fontSize" in token_name:
        return "fontSize"
    elif ".fontFamily" in token_name:
        return "fontFamily"
    elif ".fontWeight" in token_name:
        return "fontWeight"
    elif ".lineHeight" in token_name:
        return "lineHeight"
    elif ".letterSpacing" in token_name:
        return "letterSpacing"

    # Match by longest prefix first
    for prefix in sorted(TAILWIND_SECTION_MAP.keys(), key=len, reverse=True):
        if token_name.startswith(prefix):
            return TAILWIND_SECTION_MAP[prefix]

    # Default fallback for unknown types
    return "extend"


def token_name_to_tailwind_key(token_name: str, section: str) -> str:
    """
    Convert a DTCG token name to a Tailwind config key.

    Args:
        token_name: The DTCG token name (e.g., "color.surface.primary")
        section: The Tailwind section (e.g., "colors")

    Returns:
        The Tailwind key (e.g., "surface-primary")
    """
    key = token_name

    # Strip section-specific prefixes to avoid redundancy
    if section == "colors" and key.startswith("color."):
        key = key[6:]  # Remove "color."
    elif section == "spacing" and key.startswith("space."):
        key = key[6:]  # Remove "space."
    elif section == "borderRadius" and key.startswith("radius."):
        key = key[7:]  # Remove "radius."
    elif section == "boxShadow" and key.startswith("shadow."):
        key = key[7:]  # Remove "shadow."
    elif section == "fontSize" and key.startswith("type."):
        key = key[5:]  # Remove "type."
        # Also remove .fontSize suffix if present
        if key.endswith(".fontSize"):
            key = key[:-9]  # Remove ".fontSize"
    elif section == "fontFamily" and key.startswith("type."):
        key = key[5:]  # Remove "type."
        # Also remove .fontFamily suffix if present
        if key.endswith(".fontFamily"):
            key = key[:-11]  # Remove ".fontFamily"
    elif section in ["fontWeight", "lineHeight", "letterSpacing"] and key.startswith("type."):
        key = key[5:]  # Remove "type."
        # Remove property suffixes
        for suffix in [".fontWeight", ".lineHeight", ".letterSpacing"]:
            if key.endswith(suffix):
                key = key[:-len(suffix)]
                break

    # Replace dots with hyphens
    key = key.replace(".", "-")

    return key


def format_tailwind_value(resolved_value: str, token_type: str) -> str:
    """
    Format a resolved value for Tailwind config.

    Args:
        resolved_value: The resolved token value
        token_type: The token type (e.g., "color", "dimension")

    Returns:
        The formatted value for Tailwind config
    """
    if token_type == "color":
        # Return hex string as-is
        return resolved_value
    elif token_type == "dimension":
        # Append px if plain number
        try:
            float(resolved_value)
            return f"{resolved_value}px"
        except ValueError:
            # Already has units
            return resolved_value
    elif token_type == "fontFamily":
        # Wrap in array string for Tailwind
        return f"['{resolved_value}', sans-serif]"
    elif token_type == "fontWeight":
        # Return as-is (numeric string or keyword)
        return resolved_value
    elif token_type == "number":
        # Return as-is
        return resolved_value
    else:
        # Default: return as-is
        return resolved_value


def generate_tailwind_config(conn: sqlite3.Connection, file_id: int) -> str:
    """
    Generate a Tailwind theme config from curated tokens.

    Args:
        conn: Database connection
        file_id: File ID to export tokens for

    Returns:
        JavaScript config string
    """
    # Query curated/aliased tokens from the default mode
    cursor = conn.execute("""
        SELECT DISTINCT
            t.id, t.name, t.type, t.tier,
            vrt.resolved_value
        FROM v_resolved_tokens vrt
        JOIN tokens t ON t.id = vrt.id
        JOIN token_collections tc ON t.collection_id = tc.id
        JOIN token_modes tm ON tm.id = vrt.mode_id
        WHERE tc.file_id = ?
            AND t.tier IN ('curated', 'aliased')
            AND tm.is_default = 1
        ORDER BY t.name
    """, (file_id,))

    tokens = cursor.fetchall()

    # Group tokens by Tailwind section
    sections: dict[str, dict[str, str]] = {}

    for token in tokens:
        token_name = token["name"]
        token_type = token["type"]
        resolved_value = token["resolved_value"]

        # Determine section and key
        section = map_token_to_tailwind_section(token_name, token_type)
        key = token_name_to_tailwind_key(token_name, section)

        # Format value
        value = format_tailwind_value(resolved_value, token_type)

        # Add to appropriate section
        if section not in sections:
            sections[section] = {}
        sections[section][key] = value

    # Build the JavaScript config string
    config_lines = ["/** Generated by Declarative Design */\n"]
    config_lines.append("module.exports = {")
    config_lines.append("  theme: {")
    config_lines.append("    extend: {")

    # Add each section
    for i, (section_name, section_tokens) in enumerate(sections.items()):
        # Skip the "extend" section for now as it's the container
        if section_name == "extend":
            continue

        config_lines.append(f"      {section_name}: {{")

        # Add tokens
        for j, (key, value) in enumerate(section_tokens.items()):
            # Format value with single quotes for JS
            if value.startswith("["):
                # Array values already formatted
                formatted_value = value
            elif value.startswith("#") or value.endswith("px") or value.endswith("rem") or value.isdigit():
                # Wrap in single quotes
                formatted_value = f"'{value}'"
            else:
                # Other string values
                formatted_value = f"'{value}'"

            # Add comma except for last item
            comma = "," if j < len(section_tokens) - 1 else ""
            config_lines.append(f"        '{key}': {formatted_value}{comma}")

        # Close section, add comma if not last
        comma = "," if i < len(sections) - 1 else ""
        config_lines.append(f"      }}{comma}")

    config_lines.append("    },")
    config_lines.append("  },")
    config_lines.append("};")

    return "\n".join(config_lines)


def generate_tailwind_config_dict(conn: sqlite3.Connection, file_id: int) -> dict:
    """
    Generate a Tailwind theme config dict from curated tokens.

    Args:
        conn: Database connection
        file_id: File ID to export tokens for

    Returns:
        Python dict representing the theme.extend object
    """
    # Query curated/aliased tokens from the default mode
    cursor = conn.execute("""
        SELECT DISTINCT
            t.id, t.name, t.type, t.tier,
            vrt.resolved_value
        FROM v_resolved_tokens vrt
        JOIN tokens t ON t.id = vrt.id
        JOIN token_collections tc ON t.collection_id = tc.id
        JOIN token_modes tm ON tm.id = vrt.mode_id
        WHERE tc.file_id = ?
            AND t.tier IN ('curated', 'aliased')
            AND tm.is_default = 1
        ORDER BY t.name
    """, (file_id,))

    tokens = cursor.fetchall()

    # Group tokens by Tailwind section
    sections: dict[str, dict[str, str]] = {}

    for token in tokens:
        token_name = token["name"]
        token_type = token["type"]
        resolved_value = token["resolved_value"]

        # Determine section and key
        section = map_token_to_tailwind_section(token_name, token_type)
        key = token_name_to_tailwind_key(token_name, section)

        # Format value
        value = format_tailwind_value(resolved_value, token_type)

        # Add to appropriate section
        if section not in sections:
            sections[section] = {}
        sections[section][key] = value

    # Remove the "extend" section if it exists (it's just a fallback)
    sections.pop("extend", None)

    return sections


def write_tailwind_mappings(conn: sqlite3.Connection, file_id: int) -> int:
    """
    Write Tailwind utility class mappings to code_mappings table.

    Args:
        conn: Database connection
        file_id: File ID to write mappings for

    Returns:
        Number of mappings written
    """
    # Query curated/aliased tokens
    cursor = conn.execute("""
        SELECT DISTINCT
            t.id, t.name, t.type
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
            AND t.tier IN ('curated', 'aliased')
        ORDER BY t.name
    """, (file_id,))

    tokens = cursor.fetchall()

    mappings_written = 0
    extracted_at = datetime.now().isoformat()

    for token in tokens:
        token_id = token["id"]
        token_name = token["name"]
        token_type = token["type"]

        # Determine section and key
        section = map_token_to_tailwind_section(token_name, token_type)
        key = token_name_to_tailwind_key(token_name, section)

        # Generate utility class identifiers based on section
        identifiers = []

        if section == "colors":
            # Multiple utility classes for colors
            identifiers.extend([
                f"bg-{key}",
                f"text-{key}",
                f"border-{key}"
            ])
        elif section == "spacing":
            # Multiple utility classes for spacing
            identifiers.extend([
                f"p-{key}",
                f"m-{key}",
                f"gap-{key}"
            ])
        elif section == "borderRadius":
            # Single utility class for radius
            identifiers.append(f"rounded-{key}")
        elif section == "fontSize":
            # Single utility class for font size
            identifiers.append(f"text-{key}")
        elif section == "boxShadow":
            # Single utility class for shadow
            identifiers.append(f"shadow-{key}")
        elif section == "opacity":
            # Single utility class for opacity
            identifiers.append(f"opacity-{key}")
        elif section == "fontFamily":
            # Single utility class for font family
            identifiers.append(f"font-{key}")
        elif section == "fontWeight":
            # Single utility class for font weight
            identifiers.append(f"font-{key}")
        elif section == "lineHeight":
            # Single utility class for line height
            identifiers.append(f"leading-{key}")
        elif section == "letterSpacing":
            # Single utility class for letter spacing
            identifiers.append(f"tracking-{key}")
        else:
            # Fallback: use the key as-is
            identifiers.append(key)

        # UPSERT each identifier
        for identifier in identifiers:
            conn.execute("""
                INSERT INTO code_mappings (token_id, target, identifier, file_path, extracted_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(token_id, target, identifier)
                DO UPDATE SET
                    file_path = excluded.file_path,
                    extracted_at = excluded.extracted_at
            """, (token_id, "tailwind", identifier, "tailwind.config.js", extracted_at))
            mappings_written += 1

    conn.commit()
    return mappings_written


def export_tailwind(conn: sqlite3.Connection, file_id: int) -> dict:
    """
    Export Tailwind config and write mappings.

    Args:
        conn: Database connection
        file_id: File ID to export

    Returns:
        Dict with config, config_dict, mappings_written, and token_count
    """
    config = generate_tailwind_config(conn, file_id)
    config_dict = generate_tailwind_config_dict(conn, file_id)
    mappings_written = write_tailwind_mappings(conn, file_id)

    # Count total tokens
    cursor = conn.execute("""
        SELECT COUNT(DISTINCT t.id) as cnt
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
            AND t.tier IN ('curated', 'aliased')
    """, (file_id,))
    token_count = cursor.fetchone()["cnt"]

    return {
        "config": config,
        "config_dict": config_dict,
        "mappings_written": mappings_written,
        "token_count": token_count
    }