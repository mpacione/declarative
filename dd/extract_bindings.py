"""Create bindings from extracted nodes using normalization functions."""

import json
import sqlite3
from typing import Dict, List, Any, Optional

from dd.normalize import (
    normalize_fill,
    normalize_stroke,
    normalize_effect,
    normalize_typography,
    normalize_spacing,
    normalize_radius
)


def create_bindings_for_node(node_row: Dict[str, Any]) -> List[Dict[str, str]]:
    """Create binding dictionaries from a node's extracted data.

    Args:
        node_row: A node dict as stored in the DB or returned by parse_extraction_response

    Returns:
        List of binding dicts with property, raw_value, resolved_value
    """
    bindings = []

    # Process fills
    fills = node_row.get('fills')
    if fills is not None:
        # Handle JSON string or list
        if isinstance(fills, str):
            try:
                fills = json.loads(fills)
            except (json.JSONDecodeError, ValueError):
                fills = None

        if fills and isinstance(fills, list):
            bindings.extend(normalize_fill(fills))

    # Process strokes
    strokes = node_row.get('strokes')
    if strokes is not None:
        # Handle JSON string or list
        if isinstance(strokes, str):
            try:
                strokes = json.loads(strokes)
            except (json.JSONDecodeError, ValueError):
                strokes = None

        if strokes and isinstance(strokes, list):
            bindings.extend(normalize_stroke(strokes))

    # Process effects
    effects = node_row.get('effects')
    if effects is not None:
        # Handle JSON string or list
        if isinstance(effects, str):
            try:
                effects = json.loads(effects)
            except (json.JSONDecodeError, ValueError):
                effects = None

        if effects and isinstance(effects, list):
            bindings.extend(normalize_effect(effects))

    # Process typography (only for TEXT nodes - indicated by font_size not None)
    if node_row.get('font_size') is not None:
        typography_data = {
            'font_family': node_row.get('font_family'),
            'font_weight': node_row.get('font_weight'),
            'font_size': node_row.get('font_size'),
            'line_height': node_row.get('line_height'),
            'letter_spacing': node_row.get('letter_spacing')
        }
        bindings.extend(normalize_typography(typography_data))

    # Process spacing (only if any spacing property is not None)
    spacing_props = ['padding_top', 'padding_right', 'padding_bottom', 'padding_left',
                    'item_spacing', 'counter_axis_spacing']
    if any(node_row.get(prop) is not None for prop in spacing_props):
        spacing_data = {prop: node_row.get(prop) for prop in spacing_props}
        bindings.extend(normalize_spacing(spacing_data))

    # Process corner radius
    corner_radius = node_row.get('corner_radius')
    if corner_radius is not None:
        bindings.extend(normalize_radius(corner_radius))

    # Process opacity (only if not 1.0)
    opacity = node_row.get('opacity')
    if opacity is not None and opacity != 1.0:
        bindings.append({
            'property': 'opacity',
            'raw_value': json.dumps(opacity),
            'resolved_value': str(opacity)
        })

    return bindings


def insert_bindings(
    conn: sqlite3.Connection,
    node_id: int,
    bindings: List[Dict[str, str]],
    force_renormalize: bool = False,
) -> int:
    """Insert or update bindings for a node.

    Implements re-extraction safety: only unbound bindings are overwritten.
    For bound/proposed bindings where the value changed, sets binding_status to 'overridden'.

    When force_renormalize=True, updates resolved_value on bound/proposed bindings
    without changing binding_status. Use this when normalization rules change and
    existing bound bindings need their values updated while preserving curation.

    Args:
        conn: Database connection
        node_id: The node ID to insert bindings for
        bindings: List of binding dicts
        force_renormalize: If True, update bound/proposed values without marking overridden

    Returns:
        Count of bindings inserted/updated
    """
    if not bindings:
        return 0

    cursor = conn.cursor()
    count = 0

    for binding in bindings:
        # Step 1: Try UPSERT (only updates if binding_status = 'unbound')
        cursor.execute("""
            INSERT INTO node_token_bindings (node_id, property, raw_value, resolved_value, binding_status)
            VALUES (?, ?, ?, ?, 'unbound')
            ON CONFLICT(node_id, property) DO UPDATE SET
                raw_value = excluded.raw_value,
                resolved_value = excluded.resolved_value
            WHERE binding_status = 'unbound'
        """, (node_id, binding['property'], binding['raw_value'], binding['resolved_value']))

        if cursor.rowcount > 0:
            count += 1

        # Step 2: Handle value changes in bound/proposed bindings
        if force_renormalize:
            # Update value only, preserve binding_status
            cursor.execute("""
                UPDATE node_token_bindings
                SET raw_value = ?,
                    resolved_value = ?
                WHERE node_id = ?
                    AND property = ?
                    AND binding_status IN ('proposed', 'bound')
                    AND resolved_value != ?
            """, (binding['raw_value'], binding['resolved_value'],
                  node_id, binding['property'], binding['resolved_value']))
        else:
            # Mark as overridden (existing behavior)
            cursor.execute("""
                UPDATE node_token_bindings
                SET raw_value = ?,
                    resolved_value = ?,
                    binding_status = 'overridden'
                WHERE node_id = ?
                    AND property = ?
                    AND binding_status IN ('proposed', 'bound')
                    AND resolved_value != ?
            """, (binding['raw_value'], binding['resolved_value'],
                  node_id, binding['property'], binding['resolved_value']))

        if cursor.rowcount > 0:
            count += 1

    conn.commit()
    return count


def create_bindings_for_screen(
    conn: sqlite3.Connection,
    screen_id: int,
    force_renormalize: bool = False,
) -> int:
    """Create bindings for all nodes in a screen.

    Args:
        conn: Database connection
        screen_id: The screen ID to process
        force_renormalize: If True, update bound/proposed values without marking overridden

    Returns:
        Total count of bindings created/updated
    """
    cursor = conn.cursor()

    # Query all nodes for the screen
    cursor.execute("""
        SELECT id, fills, strokes, effects, corner_radius,
               font_family, font_weight, font_size, line_height, letter_spacing,
               padding_top, padding_right, padding_bottom, padding_left,
               item_spacing, counter_axis_spacing, opacity
        FROM nodes
        WHERE screen_id = ?
    """, (screen_id,))

    rows = cursor.fetchall()
    total_count = 0

    for row in rows:
        # Convert row to dict
        node_data = {
            'id': row[0],
            'fills': row[1],
            'strokes': row[2],
            'effects': row[3],
            'corner_radius': row[4],
            'font_family': row[5],
            'font_weight': row[6],
            'font_size': row[7],
            'line_height': row[8],
            'letter_spacing': row[9],
            'padding_top': row[10],
            'padding_right': row[11],
            'padding_bottom': row[12],
            'padding_left': row[13],
            'item_spacing': row[14],
            'counter_axis_spacing': row[15],
            'opacity': row[16]
        }

        # Create bindings for this node
        bindings = create_bindings_for_node(node_data)

        # Insert bindings
        if bindings:
            count = insert_bindings(conn, node_data['id'], bindings, force_renormalize=force_renormalize)
            total_count += count

    return total_count