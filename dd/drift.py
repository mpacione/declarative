"""Drift detection for Figma-DB synchronization (UC-6).

Compares database token values against Figma variable values to detect
drift and maintain sync status. This module does NOT call MCP directly -
it receives Figma data from agents with MCP access.
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional

from dd.export_figma_vars import figma_path_to_dtcg


def _try_extract_json_dimension(value: str) -> str | None:
    """Extract a scalar from a JSON dimension object like {"value":24,"unit":"PIXELS"}.

    Returns the extracted string, or None if the value isn't a JSON dimension object.
    """
    if not value.startswith("{"):
        return None
    try:
        obj = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    if obj.get("unit") == "AUTO":
        return "AUTO"
    if "value" in obj:
        return str(obj["value"])
    return None


def _normalize_numeric(value: str) -> str:
    """Normalize a numeric string, rounding Figma float noise.

    Figma produces values like 10.000000149011612 from internal float32
    representation. If the fractional part is < 0.001, round to integer.
    """
    try:
        f = float(value)
        rounded = round(f)
        if abs(f - rounded) < 0.001:
            return str(rounded)
        return str(f)
    except ValueError:
        return value


def normalize_value_for_comparison(value: str, token_type: str) -> str:
    """Normalize a value for drift comparison to avoid false positives.

    Args:
        value: The value to normalize
        token_type: The token type (color, dimension, fontFamily, etc.)

    Returns:
        Normalized string for comparison
    """
    # Strip whitespace
    normalized = value.strip()

    if token_type == "color":
        # Uppercase hex, strip leading #, normalize alpha
        if normalized.startswith("#"):
            normalized = normalized[1:]
        normalized = normalized.upper()
        # Keep 8-digit hex as-is — alpha is a distinct value

    elif token_type in ("dimension", "number", "fontWeight"):
        # Try to extract from JSON object (lineHeight, letterSpacing)
        extracted = _try_extract_json_dimension(normalized)
        if extracted is not None:
            normalized = extracted

        # Strip trailing px
        if normalized.endswith("px"):
            normalized = normalized[:-2].strip()

        # Normalize numeric representation with float noise rounding
        if normalized != "AUTO":
            normalized = _normalize_numeric(normalized)

    elif token_type == "fontFamily":
        # Strip surrounding quotes
        if normalized.startswith('"') and normalized.endswith('"'):
            normalized = normalized[1:-1]
        elif normalized.startswith("'") and normalized.endswith("'"):
            normalized = normalized[1:-1]

    return normalized


def parse_figma_variables_for_drift(raw_response: dict) -> List[Dict[str, Any]]:
    """Parse Figma variables response for drift detection.

    Args:
        raw_response: Raw response from figma_get_variables MCP call

    Returns:
        List of variable dicts with keys: variable_id, name (Figma slash-path),
        dtcg_name (dot-path), collection_name, values (mode_name -> value)
    """
    parsed_variables = []

    # Handle different response shapes
    collections = []
    if isinstance(raw_response, dict):
        # Check for "collections" key
        if "collections" in raw_response:
            collections = raw_response["collections"]
        # Check for "variables" key (flat structure)
        elif "variables" in raw_response:
            # Create a synthetic collection for flat variables
            variables = raw_response["variables"]
            if isinstance(variables, list):
                collections = [{
                    "name": "Default",
                    "variables": variables,
                    "modes": raw_response.get("modes", [{"name": "Default"}])
                }]
    elif isinstance(raw_response, list):
        # Direct list of collections or variables
        if raw_response and isinstance(raw_response[0], dict):
            if "variables" in raw_response[0]:
                # List of collections
                collections = raw_response
            else:
                # List of variables - wrap in synthetic collection
                collections = [{
                    "name": "Default",
                    "variables": raw_response,
                    "modes": [{"name": "Default"}]
                }]

    for collection in collections:
        collection_name = collection.get("name", "Default")
        variables = collection.get("variables", [])

        for variable in variables:
            variable_id = variable.get("id", "")
            figma_name = variable.get("name", "")

            # Convert Figma slash-path to DTCG dot-path
            dtcg_name = figma_path_to_dtcg(figma_name)

            # Extract values per mode
            values = {}
            if "valuesByMode" in variable:
                # Values keyed by mode ID
                modes = collection.get("modes", [])
                mode_lookup = {m.get("id"): m.get("name", "Default") for m in modes}
                for mode_id, value in variable.get("valuesByMode", {}).items():
                    mode_name = mode_lookup.get(mode_id, mode_id)
                    # Handle value objects with "value" field
                    if isinstance(value, dict) and "value" in value:
                        values[mode_name] = str(value["value"])
                    else:
                        values[mode_name] = str(value)
            elif "values" in variable:
                # Values keyed by mode name directly
                for mode_name, value in variable.get("values", {}).items():
                    if isinstance(value, dict) and "value" in value:
                        values[mode_name] = str(value["value"])
                    else:
                        values[mode_name] = str(value)
            elif "value" in variable:
                # Single value - use default mode
                value = variable["value"]
                if isinstance(value, dict) and "value" in value:
                    values["Default"] = str(value["value"])
                else:
                    values["Default"] = str(value)

            parsed_variables.append({
                "variable_id": variable_id,
                "name": figma_name,
                "dtcg_name": dtcg_name,
                "collection_name": collection_name,
                "values": values
            })

    return parsed_variables


def compare_token_values(conn: sqlite3.Connection, file_id: int,
                        figma_variables: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
    """Compare DB token values against Figma variable values.

    Args:
        conn: Database connection
        file_id: File ID to compare
        figma_variables: Parsed Figma variables from parse_figma_variables_for_drift

    Returns:
        Dict with comparison results grouped by sync status
    """
    # Query DB tokens with their values per mode
    cursor = conn.execute("""
        SELECT t.id, t.name, t.type, t.figma_variable_id, t.sync_status,
               tv.resolved_value AS db_value, tm.name AS mode_name,
               tc.name AS collection_name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        JOIN token_values tv ON tv.token_id = t.id
        JOIN token_modes tm ON tm.id = tv.mode_id
        WHERE tc.file_id = ? AND t.tier IN ('curated', 'aliased')
        ORDER BY t.name, tm.name
    """, (file_id,))

    # Build DB token lookup by (name, mode) -> value
    db_tokens = {}
    token_info = {}  # Track token metadata
    for row in cursor:
        token_id = row["id"]
        token_name = row["name"]
        mode_name = row["mode_name"]

        # Store token info
        if token_id not in token_info:
            token_info[token_id] = {
                "id": token_id,
                "name": token_name,
                "type": row["type"],
                "figma_variable_id": row["figma_variable_id"],
                "collection_name": row["collection_name"],
                "values": {}
            }

        # Store value for this mode
        token_info[token_id]["values"][mode_name] = row["db_value"]
        db_tokens[(token_name, mode_name)] = row["db_value"]

    # Build Figma variable lookup by (dtcg_name, mode) -> value
    figma_lookup = {}
    figma_by_name = {}  # Track Figma variables by name
    for variable in figma_variables:
        dtcg_name = variable["dtcg_name"]
        figma_by_name[dtcg_name] = variable

        for mode_name, value in variable["values"].items():
            figma_lookup[(dtcg_name, mode_name)] = value

    # Check for code_only tokens (have code_mappings)
    cursor = conn.execute("""
        SELECT DISTINCT t.id
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        JOIN code_mappings cm ON cm.token_id = t.id
        WHERE tc.file_id = ?
    """, (file_id,))

    tokens_with_code = {row["id"] for row in cursor}

    # Compare tokens
    comparison = {
        "synced": [],
        "drifted": [],
        "pending": [],
        "figma_only": [],
        "code_only": []
    }

    # Process DB tokens
    for token_id, info in token_info.items():
        token_name = info["name"]
        token_type = info["type"]
        figma_variable_id = info["figma_variable_id"]

        if not figma_variable_id:
            # No Figma variable ID - token is pending
            if token_id in tokens_with_code:
                # Has code mappings but no Figma variable
                comparison["code_only"].append({
                    "token_id": token_id,
                    "name": token_name,
                    "collection_name": info["collection_name"]
                })
            else:
                comparison["pending"].append({
                    "token_id": token_id,
                    "name": token_name,
                    "collection_name": info["collection_name"]
                })
        else:
            # Has Figma variable ID - check if exists in Figma response
            if token_name not in figma_by_name:
                # Token has Figma ID but not in current Figma response
                if token_id in tokens_with_code:
                    comparison["code_only"].append({
                        "token_id": token_id,
                        "name": token_name,
                        "collection_name": info["collection_name"]
                    })
                else:
                    # Mark as drifted (was exported but now missing)
                    comparison["drifted"].append({
                        "token_id": token_id,
                        "name": token_name,
                        "collection_name": info["collection_name"],
                        "mode": "all",
                        "db_value": str(info["values"]),
                        "figma_value": "missing"
                    })
            else:
                # Token exists in both DB and Figma - compare values
                is_synced = True
                drift_details = []

                for mode_name, db_value in info["values"].items():
                    figma_value = figma_lookup.get((token_name, mode_name))

                    if figma_value is None:
                        # Mode missing in Figma
                        is_synced = False
                        drift_details.append({
                            "mode": mode_name,
                            "db_value": db_value,
                            "figma_value": "missing"
                        })
                    else:
                        # Normalize and compare values
                        normalized_db = normalize_value_for_comparison(db_value, token_type)
                        normalized_figma = normalize_value_for_comparison(figma_value, token_type)

                        if normalized_db != normalized_figma:
                            is_synced = False
                            drift_details.append({
                                "mode": mode_name,
                                "db_value": db_value,
                                "figma_value": figma_value
                            })

                if is_synced:
                    comparison["synced"].append({
                        "token_id": token_id,
                        "name": token_name,
                        "collection_name": info["collection_name"]
                    })
                else:
                    # Add drift entries for each differing mode
                    for detail in drift_details:
                        comparison["drifted"].append({
                            "token_id": token_id,
                            "name": token_name,
                            "collection_name": info["collection_name"],
                            "mode": detail["mode"],
                            "db_value": detail["db_value"],
                            "figma_value": detail["figma_value"]
                        })

    # Check for Figma-only variables (in Figma but not DB)
    db_token_names = {info["name"] for info in token_info.values()}
    for dtcg_name, variable in figma_by_name.items():
        if dtcg_name not in db_token_names:
            comparison["figma_only"].append({
                "name": dtcg_name,
                "variable_id": variable["variable_id"],
                "collection_name": variable["collection_name"],
                "values": variable["values"]
            })

    return comparison


def update_sync_statuses(conn: sqlite3.Connection, file_id: int,
                        comparison: Dict[str, List[Dict]]) -> Dict[str, int]:
    """Update token sync_status based on comparison results.

    Args:
        conn: Database connection
        file_id: File ID being processed
        comparison: Comparison dict from compare_token_values

    Returns:
        Dict with update counts by status
    """
    counts = {
        "updated": 0,
        "synced": 0,
        "drifted": 0,
        "pending": 0,
        "code_only": 0,
        "figma_only": len(comparison.get("figma_only", []))
    }

    # Track which tokens have been updated to avoid duplicates
    updated_tokens = set()

    # Update synced tokens
    for item in comparison.get("synced", []):
        token_id = item["token_id"]
        if token_id not in updated_tokens:
            conn.execute("""
                UPDATE tokens
                SET sync_status = 'synced',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = ?
            """, (token_id,))
            updated_tokens.add(token_id)
            counts["synced"] += 1
            counts["updated"] += 1

    # Update drifted tokens
    for item in comparison.get("drifted", []):
        token_id = item["token_id"]
        if token_id not in updated_tokens:
            conn.execute("""
                UPDATE tokens
                SET sync_status = 'drifted',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = ?
            """, (token_id,))
            updated_tokens.add(token_id)
            counts["drifted"] += 1
            counts["updated"] += 1

    # Update pending tokens
    for item in comparison.get("pending", []):
        token_id = item["token_id"]
        if token_id not in updated_tokens:
            conn.execute("""
                UPDATE tokens
                SET sync_status = 'pending',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = ?
            """, (token_id,))
            updated_tokens.add(token_id)
            counts["pending"] += 1
            counts["updated"] += 1

    # Update code_only tokens
    for item in comparison.get("code_only", []):
        token_id = item["token_id"]
        if token_id not in updated_tokens:
            conn.execute("""
                UPDATE tokens
                SET sync_status = 'code_only',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = ?
            """, (token_id,))
            updated_tokens.add(token_id)
            counts["code_only"] += 1
            counts["updated"] += 1

    # Commit all updates
    conn.commit()

    return counts


def generate_drift_report(conn: sqlite3.Connection, file_id: int) -> Dict[str, Any]:
    """Generate a drift report for a file.

    Args:
        conn: Database connection
        file_id: File ID to report on

    Returns:
        Dict with summary and detailed drift information
    """
    # Query overall sync status distribution
    cursor = conn.execute("""
        SELECT t.sync_status, COUNT(*) AS count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
        GROUP BY t.sync_status
    """, (file_id,))

    summary = {
        "synced": 0,
        "drifted": 0,
        "pending": 0,
        "code_only": 0,
        "figma_only": 0
    }

    for row in cursor:
        status = row["sync_status"]
        if status in summary:
            summary[status] = row["count"]

    # Query drifted tokens using v_drift_report view logic
    cursor = conn.execute("""
        SELECT
            t.id AS token_id,
            t.name AS token_name,
            t.type,
            t.sync_status,
            t.figma_variable_id,
            tv.resolved_value AS db_value,
            tm.name AS mode_name,
            tc.name AS collection_name
        FROM tokens t
        JOIN token_values tv ON tv.token_id = t.id
        JOIN token_modes tm ON tm.id = tv.mode_id
        JOIN token_collections tc ON tc.id = t.collection_id
        WHERE tc.file_id = ? AND t.sync_status = 'drifted'
        ORDER BY tc.name, t.name, tm.name
    """, (file_id,))

    drifted_tokens = []
    for row in cursor:
        drifted_tokens.append({
            "token_id": row["token_id"],
            "token_name": row["token_name"],
            "db_value": row["db_value"],
            "mode_name": row["mode_name"],
            "collection_name": row["collection_name"]
        })

    # Query pending tokens
    cursor = conn.execute("""
        SELECT DISTINCT
            t.id AS token_id,
            t.name AS token_name,
            tc.name AS collection_name
        FROM tokens t
        JOIN token_collections tc ON tc.id = t.collection_id
        WHERE tc.file_id = ? AND t.sync_status = 'pending'
        ORDER BY tc.name, t.name
    """, (file_id,))

    pending_tokens = []
    for row in cursor:
        pending_tokens.append({
            "token_id": row["token_id"],
            "token_name": row["token_name"],
            "collection_name": row["collection_name"]
        })

    return {
        "summary": summary,
        "drifted_tokens": drifted_tokens,
        "pending_tokens": pending_tokens
    }


def detect_drift(conn: sqlite3.Connection, file_id: int,
                figma_variables_response: dict) -> Dict[str, Any]:
    """Main drift detection entry point - updates sync statuses.

    Args:
        conn: Database connection
        file_id: File ID to process
        figma_variables_response: Raw response from figma_get_variables

    Returns:
        Combined dict with comparison, updates, and report
    """
    # Parse Figma variables
    parsed_variables = parse_figma_variables_for_drift(figma_variables_response)

    # Compare values
    comparison = compare_token_values(conn, file_id, parsed_variables)

    # Update sync statuses
    updates = update_sync_statuses(conn, file_id, comparison)

    # Generate report
    report = generate_drift_report(conn, file_id)

    return {
        "comparison": comparison,
        "updates": updates,
        "report": report
    }


def detect_drift_readonly(conn: sqlite3.Connection, file_id: int,
                         figma_variables_response: dict) -> Dict[str, Any]:
    """Read-only drift detection - does NOT update sync statuses.

    Args:
        conn: Database connection
        file_id: File ID to process
        figma_variables_response: Raw response from figma_get_variables

    Returns:
        Comparison dict without modifying DB data
    """
    # Parse Figma variables
    parsed_variables = parse_figma_variables_for_drift(figma_variables_response)

    # Compare values (read-only)
    comparison = compare_token_values(conn, file_id, parsed_variables)

    return comparison