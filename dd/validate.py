"""Pre-export validation phase (Phase 6.5).

Validates token data before export to Figma, checking for completeness,
compliance, and quality issues. Blocks export if error-severity issues exist.
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

from dd.types import Severity


def check_mode_completeness(conn: sqlite3.Connection, file_id: int) -> List[Dict[str, Any]]:
    """Check that every token has a value for every mode in its collection.

    Aliased tokens are skipped since they reference target token values.

    Args:
        conn: Database connection
        file_id: File ID to check

    Returns:
        List of validation issues with severity 'error'
    """
    issues = []

    # Find tokens missing mode values
    cursor = conn.execute("""
        SELECT t.id AS token_id, t.name, tc.name AS collection_name, tm.name AS mode_name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        CROSS JOIN token_modes tm ON tm.collection_id = tc.id
        LEFT JOIN token_values tv ON tv.token_id = t.id AND tv.mode_id = tm.id
        WHERE tc.file_id = ? AND tv.id IS NULL AND t.alias_of IS NULL
    """, (file_id,))

    for row in cursor:
        issues.append({
            "check_name": "mode_completeness",
            "severity": Severity.ERROR.value,
            "message": f"Token '{row['name']}' in collection '{row['collection_name']}' missing value for mode '{row['mode_name']}'",
            "affected_ids": json.dumps([row["token_id"]])
        })

    return issues


def check_name_dtcg_compliant(conn: sqlite3.Connection, file_id: int) -> List[Dict[str, Any]]:
    """Check that token names comply with DTCG naming pattern.

    Pattern: ^[a-z][a-z0-9]*(\\.[a-z0-9]+)*$
    Allows numeric segments for spacing multipliers (e.g., "space.4")

    Args:
        conn: Database connection
        file_id: File ID to check

    Returns:
        List of validation issues with severity 'error'
    """
    issues = []
    pattern = re.compile(r'^[a-z][a-z0-9]*(\.[a-z0-9]+)*$')

    cursor = conn.execute("""
        SELECT t.id, t.name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
    """, (file_id,))

    for row in cursor:
        if not pattern.match(row["name"]):
            issues.append({
                "check_name": "name_dtcg_compliant",
                "severity": Severity.ERROR.value,
                "message": f"Token name '{row['name']}' does not match DTCG pattern (lowercase, dot-separated)",
                "affected_ids": json.dumps([row["id"]])
            })

    return issues


def check_orphan_tokens(conn: sqlite3.Connection, file_id: int) -> List[Dict[str, Any]]:
    """Check for tokens with zero bindings (created but never assigned).

    Aliased tokens are skipped from this check.

    Args:
        conn: Database connection
        file_id: File ID to check

    Returns:
        List of validation issues with severity 'warning'
    """
    issues = []

    cursor = conn.execute("""
        SELECT t.id, t.name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
        WHERE tc.file_id = ? AND ntb.id IS NULL AND t.alias_of IS NULL
    """, (file_id,))

    for row in cursor:
        issues.append({
            "check_name": "orphan_tokens",
            "severity": Severity.WARNING.value,
            "message": f"Token '{row['name']}' has no bindings (orphan)",
            "affected_ids": json.dumps([row["id"]])
        })

    return issues


def check_binding_coverage(conn: sqlite3.Connection, file_id: int) -> List[Dict[str, Any]]:
    """Report binding coverage statistics.

    Args:
        conn: Database connection
        file_id: File ID to check (unused but kept for consistency)

    Returns:
        Single info-level issue with coverage statistics
    """
    # Query binding statistics
    cursor = conn.execute("""
        SELECT
            binding_status,
            COUNT(*) AS count
        FROM node_token_bindings ntb
        JOIN nodes n ON ntb.node_id = n.id
        JOIN screens s ON n.screen_id = s.id
        WHERE s.file_id = ?
        GROUP BY binding_status
    """, (file_id,))

    stats = {row["binding_status"]: row["count"] for row in cursor}

    if not stats:
        return [{
            "check_name": "binding_coverage",
            "severity": Severity.INFO.value,
            "message": "No bindings found",
            "affected_ids": None
        }]

    total = sum(stats.values())
    bound_pct = round(100.0 * stats.get("bound", 0) / total, 1)
    proposed_pct = round(100.0 * stats.get("proposed", 0) / total, 1)
    unbound_pct = round(100.0 * stats.get("unbound", 0) / total, 1)

    message = f"Binding coverage: {bound_pct}% bound, {proposed_pct}% proposed, {unbound_pct}% unbound"

    return [{
        "check_name": "binding_coverage",
        "severity": Severity.INFO.value,
        "message": message,
        "affected_ids": None
    }]


def check_alias_targets_curated(conn: sqlite3.Connection, file_id: int) -> List[Dict[str, Any]]:
    """Check that every alias points to a curated token (not extracted).

    Args:
        conn: Database connection
        file_id: File ID to check

    Returns:
        List of validation issues with severity 'error'
    """
    issues = []

    cursor = conn.execute("""
        SELECT t.id, t.name, target.name AS target_name, target.tier AS target_tier
        FROM tokens t
        JOIN tokens target ON t.alias_of = target.id
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ? AND t.tier = 'aliased' AND target.tier != 'curated'
    """, (file_id,))

    for row in cursor:
        issues.append({
            "check_name": "alias_targets_curated",
            "severity": Severity.ERROR.value,
            "message": f"Alias token '{row['name']}' points to {row['target_tier']} token '{row['target_name']}' (must point to curated)",
            "affected_ids": json.dumps([row["id"]])
        })

    return issues


def check_name_uniqueness(conn: sqlite3.Connection, file_id: int) -> List[Dict[str, Any]]:
    """Check for duplicate token names within a collection.

    The UNIQUE constraint should prevent this, but we check anyway for robustness.

    Args:
        conn: Database connection
        file_id: File ID to check

    Returns:
        List of validation issues with severity 'error'
    """
    issues = []

    cursor = conn.execute("""
        SELECT t.collection_id, tc.name AS collection_name, t.name, COUNT(*) AS cnt
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
        GROUP BY t.collection_id, t.name
        HAVING COUNT(*) > 1
    """, (file_id,))

    for row in cursor:
        issues.append({
            "check_name": "name_uniqueness",
            "severity": Severity.ERROR.value,
            "message": f"Duplicate token name '{row['name']}' in collection '{row['collection_name']}' ({row['cnt']} occurrences)",
            "affected_ids": json.dumps([row["collection_id"]])
        })

    return issues


def check_value_format(conn: sqlite3.Connection, file_id: int) -> List[Dict[str, Any]]:
    """Validate resolved_value format per token type.

    Type validations:
    - color: must match ^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$
    - dimension: must be a valid number (int or float)
    - fontFamily: must be a non-empty string
    - fontWeight: must be a number in 100-900 range
    - number: must be a valid number

    Args:
        conn: Database connection
        file_id: File ID to check

    Returns:
        List of validation issues with severity 'error'
    """
    issues = []

    # Color format validation
    color_pattern = re.compile(r'^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$')

    cursor = conn.execute("""
        SELECT t.id, t.name, t.type, tv.resolved_value, tm.name AS mode_name
        FROM tokens t
        JOIN token_values tv ON tv.token_id = t.id
        JOIN token_modes tm ON tm.id = tv.mode_id
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
    """, (file_id,))

    for row in cursor:
        token_type = row["type"]
        value = row["resolved_value"]
        valid = True
        error_msg = ""

        if token_type == "color":
            if not color_pattern.match(value):
                valid = False
                error_msg = f"Invalid color format for token '{row['name']}' in mode '{row['mode_name']}': '{value}' (expected hex)"

        elif token_type == "dimension" or token_type == "number":
            try:
                float(value)
            except ValueError:
                valid = False
                type_name = "dimension" if token_type == "dimension" else "number"
                error_msg = f"Invalid {type_name} format for token '{row['name']}' in mode '{row['mode_name']}': '{value}' (expected numeric)"

        elif token_type == "fontFamily":
            if not value or not value.strip():
                valid = False
                error_msg = f"Invalid fontFamily format for token '{row['name']}' in mode '{row['mode_name']}': empty value"

        elif token_type == "fontWeight":
            try:
                weight = float(value)
                if weight < 100 or weight > 900:
                    valid = False
                    error_msg = f"Invalid fontWeight for token '{row['name']}' in mode '{row['mode_name']}': {weight} (must be 100-900)"
            except ValueError:
                valid = False
                error_msg = f"Invalid fontWeight format for token '{row['name']}' in mode '{row['mode_name']}': '{value}' (expected numeric)"

        if not valid:
            issues.append({
                "check_name": "value_format",
                "severity": Severity.ERROR.value,
                "message": error_msg,
                "affected_ids": json.dumps([row["id"]])
            })

    return issues


def run_validation(conn: sqlite3.Connection, file_id: int) -> Dict[str, Any]:
    """Run all validation checks and write results to database.

    Args:
        conn: Database connection
        file_id: File ID to validate

    Returns:
        Dictionary with validation results:
        - passed: True if no errors
        - errors: Count of error-severity issues
        - warnings: Count of warning-severity issues
        - info: Count of info-severity issues
        - run_at: ISO timestamp of validation run
        - issues: List of all validation issues
    """
    # Generate timestamp for this run
    run_at = datetime.now(timezone.utc).isoformat()

    # Run all checks
    all_issues = []
    all_issues.extend(check_mode_completeness(conn, file_id))
    all_issues.extend(check_name_dtcg_compliant(conn, file_id))
    all_issues.extend(check_orphan_tokens(conn, file_id))
    all_issues.extend(check_binding_coverage(conn, file_id))
    all_issues.extend(check_alias_targets_curated(conn, file_id))
    all_issues.extend(check_name_uniqueness(conn, file_id))
    all_issues.extend(check_value_format(conn, file_id))

    # Write to database
    for issue in all_issues:
        conn.execute("""
            INSERT INTO export_validations (run_at, check_name, severity, message, affected_ids)
            VALUES (?, ?, ?, ?, ?)
        """, (
            run_at,
            issue["check_name"],
            issue["severity"],
            issue["message"],
            issue["affected_ids"]
        ))
    conn.commit()

    # Count by severity
    error_count = sum(1 for i in all_issues if i["severity"] == Severity.ERROR.value)
    warning_count = sum(1 for i in all_issues if i["severity"] == Severity.WARNING.value)
    info_count = sum(1 for i in all_issues if i["severity"] == Severity.INFO.value)

    return {
        "passed": error_count == 0,
        "errors": error_count,
        "warnings": warning_count,
        "info": info_count,
        "run_at": run_at,
        "issues": all_issues
    }


def is_export_ready(conn: sqlite3.Connection) -> bool:
    """Check if the latest validation run has no error-severity issues.

    Args:
        conn: Database connection

    Returns:
        True if export can proceed, False otherwise
    """
    # Check if any validation has been run
    cursor = conn.execute("SELECT COUNT(*) FROM export_validations")
    if cursor.fetchone()[0] == 0:
        return False  # No validation run, not ready

    # Check latest run for errors
    cursor = conn.execute("""
        SELECT COUNT(*) AS error_count
        FROM export_validations
        WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
        AND severity = 'error'
    """)

    return cursor.fetchone()["error_count"] == 0