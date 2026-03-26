"""Clustering module for spacing values.

This module implements Phase 5 spacing clustering:
1. Query spacing census from database
2. Detect scale pattern (e.g., 4px base)
3. Propose token names (multiplier or t-shirt notation)
4. Create tokens and update bindings
"""

import json
import math
import sqlite3
from typing import Optional


def query_spacing_census(conn: sqlite3.Connection, file_id: int) -> list[dict]:
    """Query spacing bindings from database, filtering by binding_status.

    Args:
        conn: Database connection
        file_id: File ID to query

    Returns:
        List of dicts with resolved_value, property, usage_count
    """
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        """SELECT ntb.resolved_value, ntb.property, COUNT(*) AS usage_count
           FROM node_token_bindings ntb
           JOIN nodes n ON ntb.node_id = n.id
           JOIN screens s ON n.screen_id = s.id
           WHERE ntb.property IN ('padding.top','padding.right','padding.bottom','padding.left',
                                  'itemSpacing','counterAxisSpacing')
             AND ntb.binding_status = 'unbound'
             AND s.file_id = ?
             AND ntb.resolved_value != '0'
             AND ntb.resolved_value != ''
           GROUP BY ntb.resolved_value, ntb.property
           ORDER BY CAST(ntb.resolved_value AS REAL)""",
        (file_id,)
    )

    return [dict(row) for row in cursor.fetchall()]


def detect_scale_pattern(values: list[float]) -> tuple[float, str]:
    """Detect if spacing values follow a clear scale pattern.

    Args:
        values: Sorted list of unique spacing values as floats

    Returns:
        Tuple of (base_unit, notation_type)
        - base_unit: The detected base (e.g., 4.0) or 0 if no pattern
        - notation_type: "multiplier" if base detected, "tshirt" otherwise
    """
    if len(values) <= 1:
        # Can't detect pattern from single value
        return (0, "tshirt")

    # Convert to integers for GCD calculation
    int_values = [round(v) for v in values if v > 0]

    if not int_values:
        return (0, "tshirt")

    # Find GCD of all values
    def gcd(a: int, b: int) -> int:
        while b:
            a, b = b, a % b
        return a

    def gcd_list(lst: list[int]) -> int:
        if not lst:
            return 0
        result = lst[0]
        for val in lst[1:]:
            result = gcd(result, val)
        return result

    base = gcd_list(int_values)

    # Common bases in design systems
    if base in [4, 8, 2]:
        # Verify that all values are reasonable multiples
        max_multiplier = max(int_values) / base
        if max_multiplier <= 20:  # Reasonable range for multipliers
            return (float(base), "multiplier")

    # No clear pattern
    return (0, "tshirt")


def propose_spacing_name(value: float, base: float, notation: str, index: int, total: int) -> str:
    """Propose a name for a spacing token.

    Args:
        value: The spacing value in pixels
        base: The base unit (0 if using t-shirt notation)
        notation: "multiplier" or "tshirt"
        index: Index of this value in the sorted list
        total: Total number of unique values

    Returns:
        Token name like "space.4" or "space.md"
    """
    if notation == "multiplier" and base > 0:
        multiplier = round(value / base)
        return f"space.{multiplier}"

    # T-shirt notation
    sizes = ["xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl"]

    if index < len(sizes):
        return f"space.{sizes[index]}"

    # Beyond standard sizes, use numeric
    return f"space.{index + 1}"


def ensure_spacing_collection(conn: sqlite3.Connection, file_id: int) -> tuple[int, int]:
    """Create or retrieve Spacing collection and Default mode.

    Args:
        conn: Database connection
        file_id: File ID

    Returns:
        Tuple of (collection_id, mode_id)
    """
    conn.row_factory = sqlite3.Row

    # Check if collection exists
    cursor = conn.execute(
        "SELECT id FROM token_collections WHERE file_id = ? AND name = 'Spacing'",
        (file_id,)
    )
    row = cursor.fetchone()

    if row:
        collection_id = row['id']
    else:
        # Create collection
        cursor = conn.execute(
            """INSERT INTO token_collections (file_id, name, created_at)
               VALUES (?, 'Spacing', datetime('now'))""",
            (file_id,)
        )
        collection_id = cursor.lastrowid

    # Check if Default mode exists
    cursor = conn.execute(
        "SELECT id FROM token_modes WHERE collection_id = ? AND name = 'Default'",
        (collection_id,)
    )
    row = cursor.fetchone()

    if row:
        mode_id = row['id']
    else:
        # Create mode
        cursor = conn.execute(
            """INSERT INTO token_modes (collection_id, name, is_default)
               VALUES (?, 'Default', 1)""",
            (collection_id,)
        )
        mode_id = cursor.lastrowid

    conn.commit()
    return (collection_id, mode_id)


def cluster_spacing(conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int) -> dict:
    """Main entry point for spacing clustering.

    Args:
        conn: Database connection
        file_id: File ID to process
        collection_id: Collection ID to create tokens in
        mode_id: Mode ID for token values

    Returns:
        Dict with tokens_created, bindings_updated, base_unit, notation
    """
    conn.row_factory = sqlite3.Row

    # Query spacing census
    census = query_spacing_census(conn, file_id)

    if not census:
        return {
            "tokens_created": 0,
            "bindings_updated": 0,
            "base_unit": 0,
            "notation": "none"
        }

    # Extract unique values
    unique_values = sorted(list(set(float(row['resolved_value']) for row in census)))

    # Detect scale pattern
    base_unit, notation = detect_scale_pattern(unique_values)

    tokens_created = 0
    bindings_updated = 0

    # Create tokens for each unique value
    for idx, value in enumerate(unique_values):
        # Propose name
        token_name = propose_spacing_name(value, base_unit, notation, idx, len(unique_values))

        # Create token
        cursor = conn.execute(
            """INSERT INTO tokens (collection_id, name, type, tier)
               VALUES (?, ?, 'dimension', 'extracted')""",
            (collection_id, token_name)
        )
        token_id = cursor.lastrowid
        tokens_created += 1

        # Convert value to string format that matches resolved_value
        # If value is a whole number, don't include decimal point
        if value == int(value):
            value_str = str(int(value))
        else:
            value_str = str(value)

        # Create token value
        raw_value = json.dumps({"value": value, "unit": "px"})
        conn.execute(
            """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
               VALUES (?, ?, ?, ?)""",
            (token_id, mode_id, raw_value, value_str)
        )

        # Update all bindings with this value
        cursor = conn.execute(
            """UPDATE node_token_bindings
               SET token_id = ?, binding_status = 'proposed', confidence = 1.0
               WHERE resolved_value = ?
                 AND property IN ('padding.top','padding.right','padding.bottom','padding.left',
                                 'itemSpacing','counterAxisSpacing')
                 AND binding_status = 'unbound'
                 AND node_id IN (
                     SELECT n.id FROM nodes n
                     JOIN screens s ON n.screen_id = s.id
                     WHERE s.file_id = ?
                 )""",
            (token_id, value_str, file_id)
        )
        bindings_updated += cursor.rowcount

    conn.commit()

    return {
        "tokens_created": tokens_created,
        "bindings_updated": bindings_updated,
        "base_unit": base_unit,
        "notation": notation
    }