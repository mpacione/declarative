"""Figma variable payload generator (Phase 7).

Generates JSON payloads for figma_setup_design_tokens MCP calls and handles
post-creation ID writeback. This module produces payloads but does not make
MCP calls directly.
"""

import sqlite3
from typing import Any, Dict, List

from dd.config import MAX_TOKENS_PER_CALL
from dd.validate import is_export_ready

# DTCG to Figma type mapping
DTCG_TO_FIGMA_TYPE: Dict[str, str] = {
    "color": "COLOR",
    "dimension": "FLOAT",
    "fontFamily": "STRING",
    "fontWeight": "FLOAT",
    "fontStyle": "STRING",
    "number": "FLOAT",
    "shadow": "FLOAT",  # individual shadow fields are FLOAT except color
    "border": "FLOAT",
    "gradient": "COLOR",
}


def dtcg_to_figma_path(dtcg_name: str) -> str:
    """Convert DTCG dot-path to Figma slash-path.

    Args:
        dtcg_name: DTCG-style dot-separated name (e.g., "color.surface.primary")

    Returns:
        Figma-style slash-separated path (e.g., "color/surface/primary")
    """
    return dtcg_name.replace(".", "/")


def map_token_type_to_figma(token_type: str, token_name: str) -> str:
    """Determine Figma variable type from DTCG type and token name.

    Special cases:
    - Token names ending with ".color" always map to COLOR
    - fontFamily and fontStyle always map to STRING
    - Everything else maps to FLOAT (including dimensions, numbers, etc.)

    Args:
        token_type: DTCG token type (e.g., "color", "dimension")
        token_name: Full token name (e.g., "shadow.sm.color")

    Returns:
        Figma variable type: "COLOR", "FLOAT", or "STRING"
    """
    # Check name-based overrides first
    if token_name.endswith(".color"):
        return "COLOR"

    # Check type mappings
    if token_type == "color" or token_type == "gradient":
        return "COLOR"
    elif token_type == "fontFamily" or token_type == "fontStyle":
        return "STRING"
    else:
        return "FLOAT"


def get_mode_names_for_collection(conn: sqlite3.Connection, collection_id: int) -> List[str]:
    """Get mode names for a collection, ordered with default first.

    Args:
        conn: Database connection
        collection_id: Token collection ID

    Returns:
        List of mode names, default mode first
    """
    cursor = conn.execute("""
        SELECT name
        FROM token_modes
        WHERE collection_id = ?
        ORDER BY is_default DESC, name ASC
    """, (collection_id,))

    return [row["name"] for row in cursor]


def query_exportable_tokens(conn: sqlite3.Connection, file_id: int) -> List[Dict[str, Any]]:
    """Query tokens that are ready for Figma export.

    Finds all curated and aliased tokens that don't yet have Figma variable IDs.
    For aliased tokens, resolves to the target token's values.

    Args:
        conn: Database connection
        file_id: File ID to query

    Returns:
        List of token dicts with keys: id, name, type, tier, collection_id,
        collection_name, alias_of, values (dict mapping mode_name -> resolved_value)
    """
    tokens = []

    # Query tokens ready for export
    cursor = conn.execute("""
        SELECT t.id, t.name, t.type, t.tier, t.collection_id,
               tc.name AS collection_name,
               t.figma_variable_id, t.alias_of
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
          AND t.tier IN ('curated', 'aliased')
          AND t.figma_variable_id IS NULL
        ORDER BY tc.name, t.name
    """, (file_id,))

    for row in cursor:
        token = {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "tier": row["tier"],
            "collection_id": row["collection_id"],
            "collection_name": row["collection_name"],
            "alias_of": row["alias_of"],
            "values": {}
        }

        # Get values for this token
        if row["alias_of"] is not None:
            # For aliased tokens, get the target token's values
            value_cursor = conn.execute("""
                SELECT tv.resolved_value, tm.name AS mode_name
                FROM token_values tv
                JOIN token_modes tm ON tv.mode_id = tm.id
                WHERE tv.token_id = ?
                ORDER BY tm.is_default DESC, tm.name
            """, (row["alias_of"],))
        else:
            # For non-aliased tokens, get their own values
            value_cursor = conn.execute("""
                SELECT tv.resolved_value, tm.name AS mode_name
                FROM token_values tv
                JOIN token_modes tm ON tv.mode_id = tm.id
                WHERE tv.token_id = ?
                ORDER BY tm.is_default DESC, tm.name
            """, (row["id"],))

        for value_row in value_cursor:
            token["values"][value_row["mode_name"]] = value_row["resolved_value"]

        tokens.append(token)

    return tokens


def generate_variable_payloads(conn: sqlite3.Connection, file_id: int) -> List[Dict[str, Any]]:
    """Generate Figma variable creation payloads.

    Groups tokens by collection and batches them into payloads of at most
    MAX_TOKENS_PER_CALL tokens each.

    Args:
        conn: Database connection
        file_id: File ID to generate payloads for

    Returns:
        List of payload dicts ready for figma_setup_design_tokens
    """
    # Get all exportable tokens
    tokens = query_exportable_tokens(conn, file_id)

    if not tokens:
        return []

    # Group tokens by collection
    collections: Dict[str, List[Dict[str, Any]]] = {}
    for token in tokens:
        collection_name = token["collection_name"]
        if collection_name not in collections:
            collections[collection_name] = []
        collections[collection_name].append(token)

    # Generate payloads
    payloads = []

    for collection_name, collection_tokens in collections.items():
        # Get mode names for this collection
        if collection_tokens:
            collection_id = collection_tokens[0]["collection_id"]
            mode_names = get_mode_names_for_collection(conn, collection_id)
        else:
            mode_names = []

        # Batch tokens into payloads
        for i in range(0, len(collection_tokens), MAX_TOKENS_PER_CALL):
            batch = collection_tokens[i:i + MAX_TOKENS_PER_CALL]

            # Build token entries for payload
            token_entries = []
            for token in batch:
                token_entry = {
                    "name": dtcg_to_figma_path(token["name"]),
                    "type": map_token_type_to_figma(token["type"], token["name"]),
                    "values": token["values"]
                }
                token_entries.append(token_entry)

            payload = {
                "collectionName": collection_name,
                "modes": mode_names,
                "tokens": token_entries
            }
            payloads.append(payload)

    return payloads


def generate_variable_payloads_checked(conn: sqlite3.Connection, file_id: int) -> List[Dict[str, Any]]:
    """Generate payloads with validation check.

    Wrapper that ensures validation has passed before generating payloads.

    Args:
        conn: Database connection
        file_id: File ID to generate payloads for

    Returns:
        List of payload dicts ready for figma_setup_design_tokens

    Raises:
        RuntimeError: If validation has errors
    """
    if not is_export_ready(conn):
        raise RuntimeError("Export blocked: validation errors exist. Run validation first.")

    return generate_variable_payloads(conn, file_id)