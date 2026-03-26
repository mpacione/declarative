"""W3C DTCG v2025.10 tokens.json export module."""

import json
from typing import Any, Optional, Union


DTCG_TYPE_MAP = {
    "color": "color",
    "dimension": "dimension",
    "fontFamily": "fontFamily",
    "fontWeight": "fontWeight",
    "number": "number",
    "shadow": "shadow",
    "border": "border",
    "gradient": "gradient",
}

TYPOGRAPHY_FIELDS = ["fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing"]
SHADOW_FIELDS = ["color", "radius", "offsetX", "offsetY", "spread"]


def build_alias_reference(target_name: str) -> str:
    """Build a DTCG alias reference string."""
    return f"{{{target_name}}}"


def format_dtcg_value(resolved_value: str, token_type: str) -> Any:
    """Format a resolved value for DTCG JSON."""
    if token_type == "color":
        return resolved_value

    elif token_type == "dimension":
        if resolved_value == "AUTO":
            return "auto"
        try:
            # Try to parse as number and return with px unit
            value = float(resolved_value)
            # Return integer if it's a whole number
            if value.is_integer():
                return {"value": int(value), "unit": "px"}
            return {"value": value, "unit": "px"}
        except ValueError:
            # Already has units, return as-is
            return resolved_value

    elif token_type == "fontFamily":
        return resolved_value

    elif token_type == "fontWeight":
        try:
            # Try to convert to integer
            weight = int(resolved_value)
            return weight
        except ValueError:
            # Return as string (e.g., "bold")
            return resolved_value

    elif token_type == "number":
        try:
            value = float(resolved_value)
            # Return integer if it's a whole number
            if value.is_integer():
                return int(value)
            return value
        except ValueError:
            return resolved_value

    # Default: return as string
    return resolved_value


def assemble_composite_typography(atomic_tokens: dict[str, dict]) -> Optional[dict]:
    """Assemble a DTCG composite typography value from atomic tokens."""
    # Check minimum required fields
    if "fontFamily" not in atomic_tokens or "fontSize" not in atomic_tokens:
        return None

    composite = {
        "$type": "typography",
        "$value": {}
    }

    for field in TYPOGRAPHY_FIELDS:
        if field in atomic_tokens:
            value = atomic_tokens[field]["resolved_value"]

            if field == "fontFamily":
                composite["$value"][field] = value
            elif field == "fontWeight":
                try:
                    composite["$value"][field] = int(value)
                except ValueError:
                    composite["$value"][field] = value
            else:
                # fontSize, lineHeight, letterSpacing are dimensions
                try:
                    num_value = float(value)
                    if num_value.is_integer():
                        composite["$value"][field] = {"value": int(num_value), "unit": "px"}
                    else:
                        composite["$value"][field] = {"value": num_value, "unit": "px"}
                except ValueError:
                    composite["$value"][field] = value

    return composite


def assemble_composite_shadow(atomic_tokens: dict[str, dict]) -> Optional[dict]:
    """Assemble a DTCG composite shadow value from atomic tokens."""
    # Check we have enough fields to make a shadow
    if "color" not in atomic_tokens:
        return None

    composite = {
        "$type": "shadow",
        "$value": {}
    }

    for field in SHADOW_FIELDS:
        if field in atomic_tokens:
            value = atomic_tokens[field]["resolved_value"]

            if field == "color":
                composite["$value"]["color"] = value
            elif field == "radius":
                # Map radius to blur in DTCG
                try:
                    num_value = float(value)
                    if num_value.is_integer():
                        composite["$value"]["blur"] = {"value": int(num_value), "unit": "px"}
                    else:
                        composite["$value"]["blur"] = {"value": num_value, "unit": "px"}
                except ValueError:
                    composite["$value"]["blur"] = value
            else:
                # offsetX, offsetY, spread are dimensions
                try:
                    num_value = float(value)
                    if num_value.is_integer():
                        composite["$value"][field] = {"value": int(num_value), "unit": "px"}
                    else:
                        composite["$value"][field] = {"value": num_value, "unit": "px"}
                except ValueError:
                    composite["$value"][field] = value

    return composite


def query_dtcg_tokens(conn, file_id: int) -> list[dict]:
    """Query curated/aliased tokens with resolved values."""
    cursor = conn.execute("""
        SELECT vrt.id, vrt.name, vrt.type, vrt.tier, vrt.alias_target_name,
               vrt.mode_name, vrt.resolved_value, vrt.collection_id
        FROM v_resolved_tokens vrt
        JOIN token_collections tc ON vrt.collection_id = tc.id
        JOIN token_modes tm ON vrt.mode_id = tm.id
        WHERE tc.file_id = ? AND vrt.tier IN ('curated', 'aliased')
        ORDER BY vrt.name
    """, (file_id,))

    return [dict(row) for row in cursor.fetchall()]


def build_token_tree(tokens: list[dict], default_mode: str) -> dict:
    """Convert flat token list into nested DTCG JSON structure."""
    tree = {}

    # Group tokens by name for composite detection
    tokens_by_prefix = {}

    # Process default mode tokens
    for token in tokens:
        if token["mode_name"] != default_mode:
            continue

        name = token["name"]
        parts = name.split(".")

        # Check for composite patterns
        if len(parts) > 1:
            # Check if this is a typography field
            last_part = parts[-1]
            if last_part in TYPOGRAPHY_FIELDS:
                prefix = ".".join(parts[:-1])
                if prefix not in tokens_by_prefix:
                    tokens_by_prefix[prefix] = {}
                tokens_by_prefix[prefix][last_part] = token
                continue

            # Check if this is a shadow field
            if last_part in SHADOW_FIELDS:
                prefix = ".".join(parts[:-1])
                if prefix not in tokens_by_prefix:
                    tokens_by_prefix[prefix] = {}
                tokens_by_prefix[prefix][last_part] = token
                continue

        # Build nested structure for regular token
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # Last part - add token data
                if token["alias_target_name"]:
                    # Aliased token
                    current[part] = {
                        "$type": DTCG_TYPE_MAP.get(token["type"], token["type"]),
                        "$value": build_alias_reference(token["alias_target_name"])
                    }
                else:
                    # Regular token
                    current[part] = {
                        "$type": DTCG_TYPE_MAP.get(token["type"], token["type"]),
                        "$value": format_dtcg_value(token["resolved_value"], token["type"])
                    }
            else:
                # Intermediate part - create nested dict if needed
                if part not in current:
                    current[part] = {}
                current = current[part]

    # Process composites
    for prefix, fields in tokens_by_prefix.items():
        # Try to assemble typography
        typography = assemble_composite_typography(fields)
        if typography:
            # Add composite to tree
            parts = prefix.split(".")
            current = tree
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    current[part] = typography
                else:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

            # Also add atomic tokens
            for field_name, field_token in fields.items():
                name = f"{prefix}.{field_name}"
                parts = name.split(".")
                current = tree
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        current[part] = {
                            "$type": DTCG_TYPE_MAP.get(field_token["type"], field_token["type"]),
                            "$value": format_dtcg_value(field_token["resolved_value"], field_token["type"])
                        }
                    else:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
            continue

        # Try to assemble shadow
        shadow = assemble_composite_shadow(fields)
        if shadow:
            # Add composite to tree
            parts = prefix.split(".")
            current = tree
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    current[part] = shadow
                else:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

            # Also add atomic tokens
            for field_name, field_token in fields.items():
                name = f"{prefix}.{field_name}"
                parts = name.split(".")
                current = tree
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        # For shadow fields, map radius to blur in the name
                        display_name = "blur" if part == "radius" else part
                        current[display_name] = {
                            "$type": DTCG_TYPE_MAP.get(field_token["type"], field_token["type"]),
                            "$value": format_dtcg_value(field_token["resolved_value"], field_token["type"])
                        }
                    else:
                        if part not in current:
                            current[part] = {}
                        current = current[part]

    return tree


def build_dtcg_with_modes(conn, file_id: int) -> dict:
    """Build the full DTCG structure including sets and modifiers for multi-mode support."""
    # Get all tokens
    tokens = query_dtcg_tokens(conn, file_id)

    if not tokens:
        return {
            "$schema": "https://design-tokens.org/schema.json"
        }

    # Find default mode by checking is_default flag
    cursor = conn.execute("""
        SELECT tm.name
        FROM token_modes tm
        JOIN token_collections tc ON tm.collection_id = tc.id
        WHERE tc.file_id = ? AND tm.is_default = 1
        LIMIT 1
    """, (file_id,))
    row = cursor.fetchone()
    default_mode = row["name"] if row else "Default"

    # Build base tree from default mode
    result = {
        "$schema": "https://design-tokens.org/schema.json"
    }

    base_tree = build_token_tree(tokens, default_mode)
    result.update(base_tree)

    # Group tokens by name and mode for multi-mode support
    tokens_by_name = {}
    for token in tokens:
        name = token["name"]
        mode = token["mode_name"]

        if name not in tokens_by_name:
            tokens_by_name[name] = {}
        tokens_by_name[name][mode] = token

    # Add non-default mode values as extensions
    modes = set(token["mode_name"] for token in tokens)
    non_default_modes = modes - {default_mode}

    if non_default_modes:
        # Add mode values to each token
        for name, modes_data in tokens_by_name.items():
            if len(modes_data) > 1:
                # This token has multiple mode values
                parts = name.split(".")

                # Navigate to the token in the tree
                current = result
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        # Last part - this should be the token
                        if part in current and isinstance(current[part], dict) and "$type" in current[part]:
                            # Add extensions for non-default modes
                            extensions = {}
                            for mode_name in non_default_modes:
                                if mode_name in modes_data:
                                    mode_token = modes_data[mode_name]
                                    if mode_token["alias_target_name"]:
                                        extensions[mode_name] = build_alias_reference(mode_token["alias_target_name"])
                                    else:
                                        extensions[mode_name] = format_dtcg_value(
                                            mode_token["resolved_value"],
                                            mode_token["type"]
                                        )

                            if extensions:
                                if "$extensions" not in current[part]:
                                    current[part]["$extensions"] = {}
                                current[part]["$extensions"]["org.design-tokens.modes"] = extensions
                    else:
                        if part in current:
                            current = current[part]
                        else:
                            break

    return result


def generate_dtcg_dict(conn, file_id: int) -> dict:
    """Main entry point returning the DTCG structure as a Python dict."""
    return build_dtcg_with_modes(conn, file_id)


def generate_dtcg_json(conn, file_id: int, indent: int = 2) -> str:
    """Generate DTCG JSON string."""
    dtcg_dict = generate_dtcg_dict(conn, file_id)
    return json.dumps(dtcg_dict, indent=indent, ensure_ascii=False)


def export_dtcg(conn, file_id: int) -> dict:
    """Generate DTCG JSON and write code mappings."""
    import datetime

    # Generate the DTCG structure
    dtcg_dict = generate_dtcg_dict(conn, file_id)
    dtcg_json = json.dumps(dtcg_dict, indent=2, ensure_ascii=False)

    # Get tokens to write mappings
    tokens = query_dtcg_tokens(conn, file_id)

    # Write code mappings
    mappings_written = 0
    for token in tokens:
        # Use the token's DTCG path as the identifier
        identifier = token["name"]

        conn.execute("""
            INSERT OR REPLACE INTO code_mappings
            (token_id, target, identifier, file_path, extracted_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            token["id"],
            "dtcg",
            identifier,
            "tokens.json",
            datetime.datetime.now().isoformat()
        ))
        mappings_written += 1

    conn.commit()

    # Count unique tokens (by name, not by mode)
    unique_names = set(token["name"] for token in tokens)

    return {
        "json": dtcg_json,
        "dict": dtcg_dict,
        "mappings_written": mappings_written,
        "token_count": len(unique_names)
    }