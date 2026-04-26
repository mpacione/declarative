"""Color clustering for Phase 5 of token extraction."""

import sqlite3

from dd.color import hex_to_oklch, hex_to_rgba, oklch_delta_e


def query_color_census(conn: sqlite3.Connection, file_id: int) -> list[dict]:
    """Query color census for unbound colors in a file.

    Args:
        conn: Database connection
        file_id: File ID to query

    Returns:
        List of dicts with keys: resolved_value, usage_count, node_count, properties
    """
    cursor = conn.execute(
        """SELECT ntb.resolved_value, COUNT(*) AS usage_count,
                  COUNT(DISTINCT ntb.node_id) AS node_count,
                  GROUP_CONCAT(DISTINCT ntb.property) AS properties
           FROM node_token_bindings ntb
           JOIN nodes n ON ntb.node_id = n.id
           JOIN screens s ON n.screen_id = s.id
           WHERE (ntb.property LIKE 'fill.%.color' OR ntb.property LIKE 'stroke.%.color'
                  OR ntb.property LIKE 'effect.%.color')
             AND ntb.binding_status = 'unbound'
             AND ntb.resolved_value IS NOT NULL
             AND ntb.resolved_value LIKE '#%'
             AND s.file_id = ?
           GROUP BY ntb.resolved_value
           ORDER BY usage_count DESC""",
        (file_id,)
    )

    return [dict(row) for row in cursor.fetchall()]


def group_by_delta_e(colors: list[dict], threshold: float = 2.0) -> list[list[dict]]:
    """Group colors by perceptual similarity.

    Args:
        colors: List of color census dicts
        threshold: Delta-E threshold for grouping (default 2.0)

    Returns:
        List of groups, where each group is a list of color dicts.
        Groups are sorted by total usage descending.
    """
    if not colors:
        return []

    groups = []

    # Process colors in usage_count descending order
    sorted_colors = sorted(colors, key=lambda c: c['usage_count'], reverse=True)

    for color in sorted_colors:
        hex_color = color['resolved_value']
        oklch = hex_to_oklch(hex_color)
        _, _, _, color_alpha = hex_to_rgba(hex_color)

        # Try to find an existing group this color belongs to
        placed = False
        for group in groups:
            # Compare to group's representative (first color, highest usage)
            representative = group[0]
            rep_oklch = hex_to_oklch(representative['resolved_value'])
            _, _, _, rep_alpha = hex_to_rgba(representative['resolved_value'])

            # Different alphas never cluster (e.g., #000000 vs #00000020)
            if abs(color_alpha - rep_alpha) > 0.01:
                continue

            delta_e = oklch_delta_e(oklch, rep_oklch)
            if delta_e < threshold:
                group.append(color)
                placed = True
                break

        if not placed:
            # Start a new group
            groups.append([color])

    # Sort groups by total usage
    groups.sort(key=lambda g: sum(c['usage_count'] for c in g), reverse=True)

    return groups


def classify_color_role(properties: str) -> str:
    """Classify color role based on properties.

    Args:
        properties: Comma-separated property names

    Returns:
        One of: 'surface', 'text', 'border', 'accent'
    """
    if 'stroke' in properties.lower():
        return 'border'

    # Default to surface for fills
    return 'surface'


def propose_color_name(role: str, lightness: float, index: int, existing_names: set[str]) -> str:
    """Propose a DTCG-compliant color name.

    Args:
        role: Color role (surface, text, border, accent)
        lightness: Lightness value (0-1)
        index: Index within the role
        existing_names: Set of already-used names

    Returns:
        Proposed name string
    """
    # Determine suffix based on index
    if index == 0:
        suffix = 'primary'
    elif index == 1:
        suffix = 'secondary'
    elif index == 2:
        suffix = 'tertiary'
    else:
        suffix = str(index + 1)

    base_name = f'color.{role}.{suffix}'

    # Handle duplicates
    if base_name not in existing_names:
        return base_name

    # Append numeric suffix for duplicates
    counter = 2
    while f'{base_name}.{counter}' in existing_names:
        counter += 1

    return f'{base_name}.{counter}'


def ensure_collection_and_mode(conn: sqlite3.Connection, file_id: int, collection_name: str = "Colors") -> tuple[int, int]:
    """Create or retrieve token collection and default mode.

    Args:
        conn: Database connection
        file_id: File ID
        collection_name: Name for the collection (default "Colors")

    Returns:
        Tuple of (collection_id, mode_id)
    """
    # Create or get collection
    conn.execute(
        """INSERT OR IGNORE INTO token_collections (file_id, name)
           VALUES (?, ?)""",
        (file_id, collection_name)
    )

    cursor = conn.execute(
        "SELECT id FROM token_collections WHERE file_id = ? AND name = ?",
        (file_id, collection_name)
    )
    collection_id = cursor.fetchone()['id']

    # Create or get default mode
    conn.execute(
        """INSERT OR IGNORE INTO token_modes (collection_id, name, is_default)
           VALUES (?, 'Default', 1)""",
        (collection_id,)
    )

    cursor = conn.execute(
        "SELECT id FROM token_modes WHERE collection_id = ? AND name = 'Default'",
        (collection_id,)
    )
    mode_id = cursor.fetchone()['id']

    return collection_id, mode_id


def cluster_colors(conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int, threshold: float = 2.0) -> dict:
    """Main entry point for color clustering.

    Args:
        conn: Database connection
        file_id: File ID to cluster
        collection_id: Token collection ID
        mode_id: Token mode ID
        threshold: Delta-E threshold for grouping

    Returns:
        Summary dict with keys: tokens_created, bindings_updated, groups
    """
    # Query census
    census = query_color_census(conn, file_id)
    if not census:
        return {'tokens_created': 0, 'bindings_updated': 0, 'groups': 0}

    # Group by similarity
    groups = group_by_delta_e(census, threshold)

    # Track existing names to ensure uniqueness
    existing_names = set()

    # Track counters
    tokens_created = 0
    bindings_updated = 0

    # Process each group by role
    role_groups = {}

    for group in groups:
        # Determine representative (first/highest usage)
        representative = group[0]
        hex_color = representative['resolved_value']

        # Classify role
        role = classify_color_role(representative['properties'])

        if role not in role_groups:
            role_groups[role] = []

        # Store group with lightness for sorting
        oklch = hex_to_oklch(hex_color)
        lightness = oklch[0]
        role_groups[role].append((lightness, group))

    # Process each role
    for role, role_group_list in role_groups.items():
        # Sort by lightness
        # For surface/border: lightness descending (light to dark)
        # For text: lightness ascending (dark to light)
        if role in ('text',):
            role_group_list.sort(key=lambda x: x[0])
        else:
            role_group_list.sort(key=lambda x: x[0], reverse=True)

        # Process groups within role
        for index, (lightness, group) in enumerate(role_group_list):
            representative = group[0]
            hex_color = representative['resolved_value']

            # Propose name
            token_name = propose_color_name(role, lightness, index, existing_names)
            existing_names.add(token_name)

            # Create token
            cursor = conn.execute(
                """INSERT INTO tokens (collection_id, name, type, tier)
                   VALUES (?, ?, 'color', 'extracted')""",
                (collection_id, token_name)
            )
            token_id = cursor.lastrowid
            tokens_created += 1

            # Create token value
            # Convert hex to RGBA JSON for raw_value
            # Since we only have hex, we'll store hex as both raw and resolved
            conn.execute(
                """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
                   VALUES (?, ?, ?, ?)""",
                (token_id, mode_id, hex_color, hex_color)
            )

            # Update bindings for all colors in the group.
            # Snap binding.resolved_value to the group's representative hex so
            # the validator (binding_token_consistency) and downstream consumers
            # see one canonical value per token. The original Figma hex remains
            # preserved in raw_value, so re-extraction / drift detection still
            # has access to it.
            representative_oklch = hex_to_oklch(hex_color)

            for color in group:
                color_hex = color['resolved_value']

                # Calculate confidence
                if color_hex == hex_color:
                    confidence = 1.0
                else:
                    color_oklch = hex_to_oklch(color_hex)
                    delta_e = oklch_delta_e(color_oklch, representative_oklch)
                    # Scale confidence: max(0.8, 1.0 - delta_e/10)
                    confidence = max(0.8, 1.0 - delta_e / 10.0)

                # Update all bindings with this color, snapping resolved_value
                # to the representative so post-merge values are consistent.
                cursor = conn.execute(
                    """UPDATE node_token_bindings
                       SET token_id = ?, binding_status = 'proposed', confidence = ?,
                           resolved_value = ?
                       WHERE resolved_value = ? AND binding_status = 'unbound'""",
                    (token_id, confidence, hex_color, color_hex)
                )
                bindings_updated += cursor.rowcount

    conn.commit()

    return {
        'tokens_created': tokens_created,
        'bindings_updated': bindings_updated,
        'groups': len(groups)
    }