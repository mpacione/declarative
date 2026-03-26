"""Clustering module for radius and effect values.

This module implements Phase 5 radius and effect clustering:
1. Query radius/effect census from database
2. Group effects by composite shadows
3. Propose token names (t-shirt sizes)
4. Create atomic tokens and update bindings
"""

import sqlite3
from typing import Optional
from collections import defaultdict

from dd.color import hex_to_oklch, oklch_delta_e


def query_radius_census(conn: sqlite3.Connection, file_id: int) -> list[dict]:
    """Query radius bindings from database, filtering by unbound status.

    Args:
        conn: Database connection
        file_id: File ID to query

    Returns:
        List of dicts with resolved_value and usage_count
    """
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        """SELECT ntb.resolved_value, COUNT(*) AS usage_count
           FROM node_token_bindings ntb
           JOIN nodes n ON ntb.node_id = n.id
           JOIN screens s ON n.screen_id = s.id
           WHERE (ntb.property LIKE 'cornerRadius%'
                  OR ntb.property LIKE 'topLeftRadius%'
                  OR ntb.property LIKE 'topRightRadius%'
                  OR ntb.property LIKE 'bottomLeftRadius%'
                  OR ntb.property LIKE 'bottomRightRadius%')
             AND ntb.property NOT LIKE 'effect%'
             AND ntb.binding_status = 'unbound'
             AND s.file_id = ?
           GROUP BY ntb.resolved_value
           ORDER BY CAST(ntb.resolved_value AS REAL)""",
        (file_id,)
    )

    return [dict(row) for row in cursor.fetchall()]


def propose_radius_name(value: float, index: int, total: int, has_full: bool = False) -> str:
    """Propose a name for a radius token.

    Args:
        value: The radius value in pixels (or 99999 for full radius group)
        index: Position in sorted list (0-based)
        total: Total number of unique values
        has_full: Whether the set includes a "full" radius value

    Returns:
        Token name like "radius.sm", "radius.md", "radius.lg", "radius.full"
    """
    # Special cases for full radius (includes 0 and 9999+)
    if value >= 9999 or value == 0 or value == 99999:
        return "radius.full"

    # If we have a "full" radius, don't count it for t-shirt sizing
    effective_total = total - 1 if has_full else total

    # Map to t-shirt sizes based on total count and position
    if effective_total <= 3:
        sizes = ["sm", "md", "lg"]
    elif effective_total == 4:
        sizes = ["xs", "sm", "md", "lg"]
    elif effective_total == 5:
        sizes = ["xs", "sm", "md", "lg", "xl"]
    else:
        # 6+ values
        sizes = ["xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl", "5xl"]

    # Return the appropriate size
    if index < len(sizes):
        return f"radius.{sizes[index]}"
    else:
        # Fallback to numeric for very large sets
        return f"radius.{index + 1}"


def cluster_radius(conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int) -> dict:
    """Cluster radius values and create tokens.

    Args:
        conn: Database connection
        file_id: File ID to process
        collection_id: Collection to add tokens to
        mode_id: Mode to add token values to

    Returns:
        Dict with tokens_created and bindings_updated counts
    """
    # Query radius census
    census = query_radius_census(conn, file_id)

    if not census:
        return {"tokens_created": 0, "bindings_updated": 0}

    # Deduplicate and group values
    unique_values = {}
    for row in census:
        val = float(row['resolved_value'])

        # Group 0 and 9999+ as "full" radius
        if val == 0 or val >= 9999:
            key = 99999  # Use a special key for full radius
        else:
            key = round(val)  # Round to nearest int for grouping

        if key not in unique_values:
            unique_values[key] = []
        unique_values[key].append(row['resolved_value'])

    # Sort by value, but keep 99999 (full radius) at the end
    sorted_values = sorted([k for k in unique_values.keys() if k != 99999])
    if 99999 in unique_values:
        sorted_values.append(99999)

    tokens_created = 0
    bindings_updated = 0
    existing_tokens = set()

    # Check if we have a full radius value
    has_full = 99999 in unique_values

    # Create tokens for each unique value
    for idx, value in enumerate(sorted_values):
        # Propose a name
        name = propose_radius_name(value, idx, len(sorted_values), has_full)

        # Ensure unique name
        if name in existing_tokens:
            suffix = 2
            while f"{name}.{suffix}" in existing_tokens:
                suffix += 1
            name = f"{name}.{suffix}"
        existing_tokens.add(name)

        # Check if token already exists
        cursor = conn.execute(
            """SELECT id FROM tokens WHERE collection_id = ? AND name = ?""",
            (collection_id, name)
        )
        existing_token = cursor.fetchone()

        if existing_token:
            token_id = existing_token['id']
        else:
            # Insert token
            cursor = conn.execute(
                """INSERT INTO tokens (collection_id, name, type, tier)
                   VALUES (?, ?, 'dimension', 'extracted')""",
                (collection_id, name)
            )
            token_id = cursor.lastrowid
            tokens_created += 1

        # Insert or update token value
        conn.execute(
            """INSERT OR REPLACE INTO token_values (token_id, mode_id, raw_value, resolved_value)
               VALUES (?, ?, ?, ?)""",
            (token_id, mode_id, str(value), str(value))
        )

        # Update all matching bindings
        for original_value in unique_values[value]:
            cursor = conn.execute(
                """UPDATE node_token_bindings
                   SET token_id = ?, binding_status = 'proposed', confidence = 1.0
                   WHERE resolved_value = ?
                     AND binding_status = 'unbound'
                     AND (property LIKE 'cornerRadius%'
                          OR property LIKE 'topLeftRadius%'
                          OR property LIKE 'topRightRadius%'
                          OR property LIKE 'bottomLeftRadius%'
                          OR property LIKE 'bottomRightRadius%')
                     AND property NOT LIKE 'effect%'
                     AND node_id IN (
                         SELECT n.id FROM nodes n
                         JOIN screens s ON n.screen_id = s.id
                         WHERE s.file_id = ?
                     )""",
                (token_id, original_value, file_id)
            )
            bindings_updated += cursor.rowcount

    conn.commit()
    return {"tokens_created": tokens_created, "bindings_updated": bindings_updated}


def query_effect_census(conn: sqlite3.Connection, file_id: int) -> list[dict]:
    """Query effect bindings from database, filtering by unbound status.

    Args:
        conn: Database connection
        file_id: File ID to query

    Returns:
        List of dicts with resolved_value, property, and usage_count
    """
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        """SELECT ntb.resolved_value, ntb.property, COUNT(*) AS usage_count
           FROM node_token_bindings ntb
           JOIN nodes n ON ntb.node_id = n.id
           JOIN screens s ON n.screen_id = s.id
           WHERE ntb.property LIKE 'effect%'
             AND ntb.binding_status = 'unbound'
             AND s.file_id = ?
           GROUP BY ntb.resolved_value, ntb.property
           ORDER BY usage_count DESC""",
        (file_id,)
    )

    return [dict(row) for row in cursor.fetchall()]


def group_effects_by_composite(conn: sqlite3.Connection, file_id: int) -> list[dict]:
    """Group effect bindings into composite shadows.

    Since effects are stored as individual bindings (effect.0.color, effect.0.radius, etc.),
    we need to group them back into composites for clustering.

    Args:
        conn: Database connection
        file_id: File ID to process

    Returns:
        List of composite shadow dicts with color, radius, offsetX, offsetY, spread, usage_count
    """
    conn.row_factory = sqlite3.Row

    # Query all effect bindings grouped by node and effect index
    cursor = conn.execute(
        """SELECT ntb.node_id, ntb.property, ntb.resolved_value
           FROM node_token_bindings ntb
           JOIN nodes n ON ntb.node_id = n.id
           JOIN screens s ON n.screen_id = s.id
           WHERE ntb.property LIKE 'effect%'
             AND ntb.binding_status = 'unbound'
             AND s.file_id = ?
           ORDER BY ntb.node_id, ntb.property""",
        (file_id,)
    )

    # Build composite shadows per node
    effects_by_node = defaultdict(lambda: defaultdict(dict))
    for row in cursor:
        node_id = row['node_id']
        property = row['property']
        value = row['resolved_value']

        # Parse effect index and field from property
        # e.g., 'effect.0.color' -> index='0', field='color'
        parts = property.split('.')
        if len(parts) >= 3:
            effect_idx = parts[1]
            field = parts[2]
            effects_by_node[node_id][effect_idx][field] = value

    # Group identical composites
    composite_map = {}
    for node_id, effects in effects_by_node.items():
        for effect_idx, fields in effects.items():
            # Create composite key
            key = (
                fields.get('color', ''),
                fields.get('radius', '0'),
                fields.get('offsetX', '0'),
                fields.get('offsetY', '0'),
                fields.get('spread', '0')
            )

            if key not in composite_map:
                composite_map[key] = {
                    'color': fields.get('color', ''),
                    'radius': fields.get('radius', '0'),
                    'offsetX': fields.get('offsetX', '0'),
                    'offsetY': fields.get('offsetY', '0'),
                    'spread': fields.get('spread', '0'),
                    'usage_count': 0,
                    'node_ids': []
                }

            composite_map[key]['usage_count'] += 1
            composite_map[key]['node_ids'].append(node_id)

    # Convert to list and sort by radius (smaller shadows first)
    composites = list(composite_map.values())
    composites.sort(key=lambda x: float(x['radius']))

    # Merge similar colors
    merged_composites = []
    for comp in composites:
        merged = False

        # Try to merge with existing composite if colors are similar
        for existing in merged_composites:
            if (comp['radius'] == existing['radius'] and
                comp['offsetX'] == existing['offsetX'] and
                comp['offsetY'] == existing['offsetY'] and
                comp['spread'] == existing['spread']):

                # Check color similarity
                try:
                    # Handle empty colors
                    if not comp['color'] or not existing['color']:
                        continue

                    color1 = hex_to_oklch(comp['color'])
                    color2 = hex_to_oklch(existing['color'])
                    delta = oklch_delta_e(color1, color2)

                    if delta < 2.0:  # Imperceptible difference
                        # Merge into existing
                        existing['usage_count'] += comp['usage_count']
                        existing['node_ids'].extend(comp['node_ids'])
                        # Mark nodes as merged for confidence calculation
                        existing['merged_node_ids'] = existing.get('merged_node_ids', [])
                        existing['merged_node_ids'].extend(comp['node_ids'])
                        merged = True
                        break
                except Exception:
                    # If color conversion fails, don't merge
                    pass

        if not merged:
            merged_composites.append(comp)

    return merged_composites


def propose_effect_name(index: int, total: int) -> str:
    """Propose a name for an effect/shadow token.

    Args:
        index: Position in sorted list (0-based)
        total: Total number of shadow groups

    Returns:
        Token name prefix like "shadow.sm", "shadow.md", "shadow.lg"
    """
    if total <= 3:
        sizes = ["sm", "md", "lg"]
    elif total == 4:
        sizes = ["xs", "sm", "md", "lg"]
    elif total == 5:
        sizes = ["xs", "sm", "md", "lg", "xl"]
    else:
        # 6+ values
        sizes = ["xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl", "5xl"]

    if index < len(sizes):
        return f"shadow.{sizes[index]}"
    else:
        # Fallback to numeric for very large sets
        return f"shadow.{index + 1}"


def cluster_effects(conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int) -> dict:
    """Cluster effect values and create atomic tokens.

    Creates individual tokens for each effect field (color, radius, offsetX, offsetY, spread)
    following the design that composite tokens are stored as atomic tokens in the DB.

    Args:
        conn: Database connection
        file_id: File ID to process
        collection_id: Collection to add tokens to
        mode_id: Mode to add token values to

    Returns:
        Dict with tokens_created, bindings_updated, and shadow_groups counts
    """
    # Group effects into composites
    composites = group_effects_by_composite(conn, file_id)

    if not composites:
        return {"tokens_created": 0, "bindings_updated": 0, "shadow_groups": 0}

    tokens_created = 0
    bindings_updated = 0

    # Create tokens for each composite shadow
    for idx, composite in enumerate(composites):
        # Propose base name for this shadow
        base_name = propose_effect_name(idx, len(composites))

        # Create individual atomic tokens for each field
        fields = [
            ('color', composite['color'], 'color'),
            ('radius', composite['radius'], 'dimension'),
            ('offsetX', composite['offsetX'], 'dimension'),
            ('offsetY', composite['offsetY'], 'dimension'),
            ('spread', composite['spread'], 'dimension'),
        ]

        field_tokens = {}
        for field_name, value, token_type in fields:
            token_name = f"{base_name}.{field_name}"

            # Insert token
            cursor = conn.execute(
                """INSERT INTO tokens (collection_id, name, type, tier)
                   VALUES (?, ?, ?, 'extracted')""",
                (collection_id, token_name, token_type)
            )
            token_id = cursor.lastrowid
            tokens_created += 1

            # Insert token value
            conn.execute(
                """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
                   VALUES (?, ?, ?, ?)""",
                (token_id, mode_id, value, value)
            )

            field_tokens[field_name] = (token_id, value)

        # Update bindings for this composite
        for node_id in composite['node_ids']:
            # Query all effect bindings for this node
            cursor = conn.execute(
                """SELECT id, property, resolved_value
                   FROM node_token_bindings
                   WHERE node_id = ? AND property LIKE 'effect%'
                     AND binding_status = 'unbound'""",
                (node_id,)
            )

            for binding in cursor:
                # Parse property to get field
                parts = binding['property'].split('.')
                if len(parts) >= 3:
                    field = parts[2]

                    if field in field_tokens:
                        token_id, expected_value = field_tokens[field]

                        # Calculate confidence based on value match
                        confidence = 1.0
                        if field == 'color':
                            # Check if this node was merged (similar color)
                            if hasattr(composite, 'merged_node_ids') and node_id in composite.get('merged_node_ids', []):
                                # This node was merged due to similar color
                                try:
                                    color1 = hex_to_oklch(binding['resolved_value'])
                                    color2 = hex_to_oklch(expected_value)
                                    delta = oklch_delta_e(color1, color2)
                                    # Set confidence based on delta
                                    confidence = max(0.8, min(0.99, 1.0 - delta / 10.0))
                                except:
                                    # If color conversion fails, use 0.9
                                    confidence = 0.9
                            elif binding['resolved_value'] != expected_value:
                                # Should not happen unless something is wrong
                                confidence = 0.9

                        # Update binding
                        conn.execute(
                            """UPDATE node_token_bindings
                               SET token_id = ?, binding_status = 'proposed', confidence = ?
                               WHERE id = ?""",
                            (token_id, confidence, binding['id'])
                        )
                        bindings_updated += 1

    conn.commit()
    return {
        "tokens_created": tokens_created,
        "bindings_updated": bindings_updated,
        "shadow_groups": len(composites)
    }


def ensure_radius_collection(conn: sqlite3.Connection, file_id: int) -> tuple[int, int]:
    """Create or retrieve Radius collection and default mode.

    Args:
        conn: Database connection
        file_id: File ID

    Returns:
        Tuple of (collection_id, mode_id)
    """
    conn.row_factory = sqlite3.Row

    # Check for existing collection
    cursor = conn.execute(
        "SELECT id FROM token_collections WHERE file_id = ? AND name = 'Radius'",
        (file_id,)
    )
    row = cursor.fetchone()

    if row:
        collection_id = row['id']
    else:
        # Create collection
        cursor = conn.execute(
            """INSERT INTO token_collections (file_id, name)
               VALUES (?, 'Radius')""",
            (file_id,)
        )
        collection_id = cursor.lastrowid

    # Get or create default mode
    cursor = conn.execute(
        "SELECT id FROM token_modes WHERE collection_id = ? AND is_default = 1",
        (collection_id,)
    )
    row = cursor.fetchone()

    if row:
        mode_id = row['id']
    else:
        # Create default mode
        cursor = conn.execute(
            """INSERT INTO token_modes (collection_id, name, is_default)
               VALUES (?, 'Default', 1)""",
            (collection_id,)
        )
        mode_id = cursor.lastrowid

    conn.commit()
    return (collection_id, mode_id)


def ensure_effects_collection(conn: sqlite3.Connection, file_id: int) -> tuple[int, int]:
    """Create or retrieve Effects collection and default mode.

    Args:
        conn: Database connection
        file_id: File ID

    Returns:
        Tuple of (collection_id, mode_id)
    """
    conn.row_factory = sqlite3.Row

    # Check for existing collection
    cursor = conn.execute(
        "SELECT id FROM token_collections WHERE file_id = ? AND name = 'Effects'",
        (file_id,)
    )
    row = cursor.fetchone()

    if row:
        collection_id = row['id']
    else:
        # Create collection
        cursor = conn.execute(
            """INSERT INTO token_collections (file_id, name)
               VALUES (?, 'Effects')""",
            (file_id,)
        )
        collection_id = cursor.lastrowid

    # Get or create default mode
    cursor = conn.execute(
        "SELECT id FROM token_modes WHERE collection_id = ? AND is_default = 1",
        (collection_id,)
    )
    row = cursor.fetchone()

    if row:
        mode_id = row['id']
    else:
        # Create default mode
        cursor = conn.execute(
            """INSERT INTO token_modes (collection_id, name, is_default)
               VALUES (?, 'Default', 1)""",
            (collection_id,)
        )
        mode_id = cursor.lastrowid

    conn.commit()
    return (collection_id, mode_id)