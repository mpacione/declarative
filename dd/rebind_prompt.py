"""Token variable rebinding for prompt-generated screens.

Bridges the generation pipeline's token_refs output to the existing
rebind infrastructure. Takes (element_id, property, token_name) tuples
from generate_figma_script and the M dict (element_id → figma_node_id)
from Figma execution, resolves variable IDs from the DB, and generates
compact rebind scripts.
"""

import sqlite3
from typing import Any

from dd.export_rebind import generate_compact_script


def query_token_variables(conn: sqlite3.Connection) -> dict[str, str]:
    """Fetch token name → Figma variable ID mapping.

    Returns dict mapping token names to their figma_variable_id for
    tokens that have been exported to Figma. Tokens without a variable
    ID are excluded.
    """
    cursor = conn.execute(
        "SELECT name, figma_variable_id FROM tokens "
        "WHERE figma_variable_id IS NOT NULL"
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def build_rebind_entries(
    token_refs: list[tuple[str, str, str]],
    figma_node_map: dict[str, str],
    token_variables: dict[str, str],
) -> list[dict[str, Any]]:
    """Build rebind entries from token refs + Figma node map.

    Takes:
    - token_refs: [(element_id, property, token_name), ...] from generate_figma_script
    - figma_node_map: {element_id → figma_node_id} from M dict after execution
    - token_variables: {token_name → figma_variable_id} from query_token_variables

    Returns list of entries compatible with generate_compact_script.
    """
    entries = []
    for element_id, prop, token_name in token_refs:
        figma_node_id = figma_node_map.get(element_id)
        if not figma_node_id:
            continue

        variable_id = token_variables.get(token_name)
        if not variable_id:
            continue

        entries.append({
            "node_id": figma_node_id,
            "property": prop,
            "variable_id": variable_id,
        })

    return entries


def generate_rebind_script(entries: list[dict[str, Any]]) -> str:
    """Generate a compact rebind script from entries.

    Delegates to the existing compact script generator from export_rebind.
    """
    return generate_compact_script(entries)
