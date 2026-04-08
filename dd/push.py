"""Push manifest generation for Figma variable sync.

Generates structured MCP action specs from DB state + optional Figma state.
This module produces manifests but does not make MCP calls directly.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from dd.config import MAX_TOKENS_PER_CALL
from dd.drift import compare_token_values, parse_figma_variables_for_drift
from dd.export_figma_vars import (
    dtcg_to_figma_path,
    get_mode_names_for_collection,
    map_token_type_to_figma,
    query_exportable_tokens,
)
from dd.export_rebind import (
    generate_rebind_scripts,
    get_rebind_summary,
)


def convert_value_for_figma(
    value_str: str, figma_type: str, is_opacity: bool = False,
) -> str | float | bool:
    """Convert a DB string value to a Figma-native typed value.

    Args:
        value_str: The string value from the database
        figma_type: The Figma variable type (COLOR, FLOAT, STRING, BOOLEAN)
        is_opacity: If True, scale 0-1 value to 0-100 (Figma opacity convention)

    Returns:
        The value in the appropriate Python type for JSON serialization
    """
    if figma_type == "COLOR":
        return value_str

    if figma_type == "FLOAT":
        cleaned = value_str.rstrip("px")
        result = float(cleaned)
        if is_opacity:
            result = result * 100
        return result

    if figma_type == "STRING":
        stripped = value_str.strip()
        if (stripped.startswith('"') and stripped.endswith('"')) or \
           (stripped.startswith("'") and stripped.endswith("'")):
            return stripped[1:-1]
        return stripped

    if figma_type == "BOOLEAN":
        return value_str.lower() in ("true", "1")

    return value_str


def _resolve_figma_mode_id(
    conn: sqlite3.Connection,
    collection_id: int,
    mode_name: str,
    raw_figma_state: dict[str, Any],
) -> str | None:
    """Resolve a Figma mode ID from DB or raw Figma state.

    First checks token_modes.figma_mode_id in DB. Falls back to
    matching mode name in the raw Figma state collections.
    """
    cursor = conn.execute(
        "SELECT figma_mode_id FROM token_modes WHERE collection_id = ? AND name = ?",
        (collection_id, mode_name),
    )
    row = cursor.fetchone()
    if row and row["figma_mode_id"]:
        return row["figma_mode_id"]

    collection_name_row = conn.execute(
        "SELECT name FROM token_collections WHERE id = ?", (collection_id,)
    ).fetchone()
    if not collection_name_row:
        return None

    col_name = collection_name_row["name"]
    for collection in raw_figma_state.get("collections", []):
        if collection.get("name") == col_name:
            for mode in collection.get("modes", []):
                if mode.get("name") == mode_name:
                    return mode.get("id")

    return None


def _build_create_actions(
    tokens_by_collection: dict[str, list[dict[str, Any]]],
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Build figma_setup_design_tokens actions for new tokens grouped by collection."""
    actions = []

    for collection_name, tokens in tokens_by_collection.items():
        if not tokens:
            continue

        collection_id = tokens[0]["collection_id"]
        mode_names = get_mode_names_for_collection(conn, collection_id)

        for i in range(0, len(tokens), MAX_TOKENS_PER_CALL):
            batch = tokens[i:i + MAX_TOKENS_PER_CALL]
            token_entries = []

            for token in batch:
                figma_type = map_token_type_to_figma(token["type"], token["name"])
                opacity = token["name"].startswith("opacity.")
                converted_values = {
                    mode: convert_value_for_figma(val, figma_type, is_opacity=opacity)
                    for mode, val in token["values"].items()
                }
                token_entries.append({
                    "name": dtcg_to_figma_path(token["name"]),
                    "resolvedType": figma_type,
                    "values": converted_values,
                })

            actions.append({
                "tool": "figma_setup_design_tokens",
                "params": {
                    "collectionName": collection_name,
                    "modes": mode_names,
                    "tokens": token_entries,
                },
            })

    return actions


def generate_variable_actions(
    conn: sqlite3.Connection,
    file_id: int,
    figma_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Generate MCP action specs for syncing DB tokens to Figma variables.

    Args:
        conn: Database connection
        file_id: File ID to push
        figma_state: Parsed Figma variables response, or None for first push

    Returns:
        Dict with 'summary' (create/update/delete/unchanged counts) and
        'actions' (list of MCP tool call specs)
    """
    all_tokens = query_exportable_tokens(conn, file_id, include_existing=True)

    if figma_state is None:
        tokens_by_collection: dict[str, list[dict[str, Any]]] = {}
        for token in all_tokens:
            col = token["collection_name"]
            if col not in tokens_by_collection:
                tokens_by_collection[col] = []
            tokens_by_collection[col].append(token)

        actions = _build_create_actions(tokens_by_collection, conn)

        return {
            "summary": {
                "create": len(all_tokens),
                "update": 0,
                "delete": 0,
                "unchanged": 0,
            },
            "actions": actions,
        }

    parsed_figma = parse_figma_variables_for_drift(figma_state)
    comparison = compare_token_values(conn, file_id, parsed_figma)

    create_tokens = comparison.get("pending", []) + comparison.get("code_only", [])
    drifted_entries = comparison.get("drifted", [])
    figma_only = comparison.get("figma_only", [])
    synced = comparison.get("synced", [])

    actions: list[dict[str, Any]] = []

    if create_tokens:
        create_by_collection: dict[str, list[dict[str, Any]]] = {}
        for item in create_tokens:
            token_match = next(
                (t for t in all_tokens if t["name"] == item["name"]), None
            )
            if token_match is None:
                continue
            col = token_match["collection_name"]
            if col not in create_by_collection:
                create_by_collection[col] = []
            create_by_collection[col].append(token_match)

        actions.extend(_build_create_actions(create_by_collection, conn))

    if drifted_entries:
        drifted_token_ids = {e["token_id"] for e in drifted_entries}
        update_items = []
        for token in all_tokens:
            if token["id"] in drifted_token_ids and token.get("figma_variable_id"):
                figma_type = map_token_type_to_figma(token["type"], token["name"])
                for mode_name, val in token["values"].items():
                    mode_id = _resolve_figma_mode_id(
                        conn, token["collection_id"], mode_name, figma_state
                    )
                    if mode_id:
                        update_items.append({
                            "variableId": token["figma_variable_id"],
                            "modeId": mode_id,
                            "value": convert_value_for_figma(val, figma_type),
                        })

        for i in range(0, len(update_items), MAX_TOKENS_PER_CALL):
            batch = update_items[i:i + MAX_TOKENS_PER_CALL]
            actions.append({
                "tool": "figma_batch_update_variables",
                "params": {"updates": batch},
            })

    for item in figma_only:
        actions.append({
            "tool": "figma_delete_variable",
            "params": {"variableId": item["variable_id"]},
        })

    return {
        "summary": {
            "create": len(create_tokens),
            "update": len(drifted_token_ids) if drifted_entries else 0,
            "delete": len(figma_only),
            "unchanged": len(synced),
        },
        "actions": actions,
    }


def generate_push_manifest(
    conn: sqlite3.Connection,
    file_id: int,
    figma_state_json: dict[str, Any] | None,
    phase: str = "all",
) -> dict[str, Any]:
    """Generate a complete push manifest with variable actions and/or rebind scripts.

    Args:
        conn: Database connection
        file_id: File ID to push
        figma_state_json: Raw Figma variables response JSON, or None for first push
        phase: Which phases to include — 'variables', 'rebind', or 'all'

    Returns:
        Manifest dict with 'phases' containing the requested phase data
    """
    manifest: dict[str, Any] = {"phases": {}}

    if phase in ("variables", "all"):
        manifest["phases"]["variables"] = generate_variable_actions(
            conn, file_id, figma_state_json
        )

    if phase in ("rebind", "all"):
        summary = get_rebind_summary(conn, file_id)
        scripts = generate_rebind_scripts(conn, file_id)
        manifest["phases"]["rebind"] = {
            "summary": summary,
            "scripts": scripts,
            "tool": "figma_execute",
            "timeout": 30000,
        }

    return manifest
