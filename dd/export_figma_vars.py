"""Figma variable payload generator (Phase 7).

Generates JSON payloads for figma_setup_design_tokens MCP calls and handles
post-creation ID writeback. This module produces payloads but does not make
MCP calls directly.
"""

import sqlite3
from typing import Any

from dd.config import MAX_TOKENS_PER_CALL
from dd.validate import is_export_ready

# DTCG to Figma type mapping
DTCG_TO_FIGMA_TYPE: dict[str, str] = {
    "color": "COLOR",
    "dimension": "FLOAT",
    "fontFamily": "STRING",
    "fontWeight": "FLOAT",
    "fontStyle": "STRING",
    "number": "FLOAT",
    "shadow": "FLOAT",  # individual shadow fields are FLOAT except color
    "border": "FLOAT",
    "gradient": "COLOR",
    "boolean": "BOOLEAN",
}


def dtcg_to_figma_path(dtcg_name: str) -> str:
    """Convert DTCG dot-path to Figma slash-path.

    Args:
        dtcg_name: DTCG-style dot-separated name (e.g., "color.surface.primary")

    Returns:
        Figma-style slash-separated path (e.g., "color/surface/primary")
    """
    return dtcg_name.replace(".", "/")


def figma_path_to_dtcg(figma_name: str) -> str:
    """Convert Figma slash-path to DTCG dot-path.

    Args:
        figma_name: Figma-style slash-separated path (e.g., "color/surface/primary")

    Returns:
        DTCG-style dot-separated name (e.g., "color.surface.primary")
    """
    return figma_name.replace("/", ".")


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


def get_mode_names_for_collection(conn: sqlite3.Connection, collection_id: int) -> list[str]:
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


def query_exportable_tokens(
    conn: sqlite3.Connection,
    file_id: int,
    include_existing: bool = False,
) -> list[dict[str, Any]]:
    """Query tokens that are ready for Figma export.

    Finds curated and aliased tokens. By default only returns tokens without
    Figma variable IDs (new tokens). With include_existing=True, returns all
    curated/aliased tokens including those already exported.

    Args:
        conn: Database connection
        file_id: File ID to query
        include_existing: If True, include tokens that already have figma_variable_id

    Returns:
        List of token dicts with keys: id, name, type, tier, collection_id,
        collection_name, figma_variable_id, alias_of, values (dict mapping mode_name -> resolved_value)
    """
    tokens = []

    filter_clause = "" if include_existing else "AND t.figma_variable_id IS NULL"

    cursor = conn.execute(f"""
        SELECT t.id, t.name, t.type, t.tier, t.collection_id,
               tc.name AS collection_name,
               t.figma_variable_id, t.alias_of
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
          AND t.tier IN ('curated', 'aliased')
          {filter_clause}
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
            "figma_variable_id": row["figma_variable_id"],
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


def generate_variable_payloads(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
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
    collections: dict[str, list[dict[str, Any]]] = {}
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


def generate_variable_payloads_checked(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
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


def parse_figma_variables_response(response: Any) -> list[dict[str, Any]]:
    """Parse Figma variables response into a flat list.

    Handles multiple response formats from figma_get_variables:
    - Dict with "collections" key containing list
    - Direct list of collections
    - Empty responses

    Args:
        response: Raw response from figma_get_variables MCP call

    Returns:
        List of dicts with keys: variable_id, name (in DTCG format),
        collection_name, collection_id, modes
    """
    parsed_variables = []

    # Handle different response shapes
    collections = []
    if isinstance(response, dict):
        collections = response.get("collections", [])
    elif isinstance(response, list):
        collections = response

    for collection in collections:
        collection_id = collection.get("id", "")
        collection_name = collection.get("name", "")
        modes = collection.get("modes", [])
        variables = collection.get("variables", [])

        for variable in variables:
            variable_id = variable.get("id", "")
            figma_name = variable.get("name", "")

            # Convert Figma slash-path to DTCG dot-path
            dtcg_name = figma_path_to_dtcg(figma_name)

            parsed_variables.append({
                "variable_id": variable_id,
                "name": dtcg_name,
                "collection_name": collection_name,
                "collection_id": collection_id,
                "modes": modes
            })

    return parsed_variables


def writeback_variable_ids(conn: sqlite3.Connection, file_id: int,
                          figma_variables: list[dict[str, Any]]) -> dict[str, int]:
    """Write back Figma variable IDs to the database.

    Updates tokens with their Figma variable IDs and marks them as synced.
    Also updates collection and mode Figma IDs for future reference.

    Args:
        conn: Database connection
        file_id: File ID being processed
        figma_variables: List of parsed Figma variables from parse_figma_variables_response

    Returns:
        Dict with counts: tokens_updated, tokens_not_found, collections_updated, modes_updated
    """
    tokens_updated = 0
    tokens_not_found = 0
    collections_updated = 0
    modes_updated = 0

    # Track which collections and modes we've already updated
    updated_collections = set()
    updated_modes = set()

    for variable in figma_variables:
        variable_id = variable["variable_id"]
        token_name = variable["name"]  # Already in DTCG format
        collection_name = variable["collection_name"]
        collection_id = variable["collection_id"]
        modes = variable["modes"]

        # Find matching token in DB
        cursor = conn.execute("""
            SELECT t.id
            FROM tokens t
            JOIN token_collections tc ON t.collection_id = tc.id
            WHERE tc.file_id = ? AND t.name = ?
        """, (file_id, token_name))

        row = cursor.fetchone()
        if row:
            token_id = row["id"]

            # Update token with Figma variable ID and sync status
            conn.execute("""
                UPDATE tokens
                SET figma_variable_id = ?,
                    sync_status = 'synced',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = ?
            """, (variable_id, token_id))

            tokens_updated += 1
        else:
            tokens_not_found += 1

        # Update collection Figma ID if not already done
        if collection_id and collection_name and collection_name not in updated_collections:
            conn.execute("""
                UPDATE token_collections
                SET figma_id = ?
                WHERE file_id = ? AND name = ?
            """, (collection_id, file_id, collection_name))

            updated_collections.add(collection_name)
            collections_updated += 1

        # Update mode Figma IDs if not already done
        if modes and collection_name:
            # Get collection ID from DB
            cursor = conn.execute("""
                SELECT id FROM token_collections
                WHERE file_id = ? AND name = ?
            """, (file_id, collection_name))

            collection_row = cursor.fetchone()
            if collection_row:
                db_collection_id = collection_row["id"]

                for mode in modes:
                    mode_id = mode.get("id")
                    mode_name = mode.get("name")

                    if mode_id and mode_name and (mode_name, db_collection_id) not in updated_modes:
                        conn.execute("""
                            UPDATE token_modes
                            SET figma_mode_id = ?
                            WHERE collection_id = ? AND name = ?
                        """, (mode_id, db_collection_id, mode_name))

                        updated_modes.add((mode_name, db_collection_id))
                        modes_updated += 1

    conn.commit()

    return {
        "tokens_updated": tokens_updated,
        "tokens_not_found": tokens_not_found,
        "collections_updated": collections_updated,
        "modes_updated": modes_updated
    }


def get_sync_status_summary(conn: sqlite3.Connection, file_id: int) -> dict[str, int]:
    """Get summary of sync status for tokens in a file.

    Args:
        conn: Database connection
        file_id: File ID to summarize

    Returns:
        Dict mapping sync_status to count
    """
    cursor = conn.execute("""
        SELECT t.sync_status, COUNT(*) AS count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
        GROUP BY t.sync_status
    """, (file_id,))

    summary = {}
    for row in cursor:
        summary[row["sync_status"]] = row["count"]

    return summary