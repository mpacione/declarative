"""Typography clustering for design token extraction."""

import sqlite3


def query_type_census(conn: sqlite3.Connection, file_id: int) -> list[dict]:
    """
    Query the typography census view for unique font combinations.

    Args:
        conn: Database connection
        file_id: File ID to query

    Returns:
        List of dicts with font_family, font_weight, font_size, line_height_value, usage_count
    """
    cursor = conn.execute("""
        SELECT
            font_family,
            font_weight,
            font_size,
            line_height_value,
            usage_count
        FROM v_type_census
        WHERE file_id = ? AND font_size IS NOT NULL
        ORDER BY usage_count DESC
    """, (file_id,))

    return [dict(row) for row in cursor.fetchall()]


def group_type_scale(census: list[dict]) -> list[dict]:
    """
    Group typography census entries into semantic scale tiers.

    Args:
        census: List of census entries with font properties

    Returns:
        List of dicts with category, size_suffix, font properties, and usage_count
    """
    # Group by category based on font_size
    categories = {
        'display': [],
        'heading': [],
        'body': [],
        'label': [],
        'caption': []
    }

    for entry in census:
        font_size = entry['font_size']

        if font_size >= 32:
            category = 'display'
        elif font_size >= 24:
            category = 'heading'
        elif font_size >= 16:
            category = 'body'
        elif font_size >= 12:
            category = 'label'
        else:
            category = 'caption'

        categories[category].append(entry)

    # Process each category to assign suffixes
    result = []

    for category, items in categories.items():
        if not items:
            continue

        # Sort by font_size descending within category
        items.sort(key=lambda x: (-x['font_size'], -x['usage_count']))

        # Assign size suffixes based on count
        if len(items) == 1:
            suffixes = ['md']
        elif len(items) == 2:
            suffixes = ['lg', 'sm']
        elif len(items) == 3:
            suffixes = ['lg', 'md', 'sm']
        elif len(items) == 4:
            suffixes = ['xl', 'lg', 'md', 'sm']
        elif len(items) == 5:
            suffixes = ['xl', 'lg', 'md', 'sm', 'xs']
        else:
            # For more than 5, use the first 5 suffixes and then append numbers
            suffixes = ['xl', 'lg', 'md', 'sm', 'xs']
            for i in range(5, len(items)):
                suffixes.append(f'{i-3}')

        # Build result entries
        for i, (item, suffix) in enumerate(zip(items, suffixes)):
            result.append({
                'category': category,
                'size_suffix': suffix,
                'font_family': item['font_family'],
                'font_weight': item['font_weight'],
                'font_size': item['font_size'],
                'line_height': item['line_height_value'],
                'usage_count': item['usage_count']
            })

    return result


def propose_type_name(category: str, size_suffix: str, existing_names: set[str]) -> str:
    """
    Propose a DTCG-compliant typography token name.

    Args:
        category: Type category (e.g., 'body', 'display')
        size_suffix: Size suffix (e.g., 'lg', 'md', 'sm')
        existing_names: Set of already used names

    Returns:
        Unique token name like 'type.body.md'
    """
    base_name = f"type.{category}.{size_suffix}"

    if base_name not in existing_names:
        return base_name

    # Add numeric suffix for duplicates
    counter = 2
    while f"{base_name}.{counter}" in existing_names:
        counter += 1

    return f"{base_name}.{counter}"


def ensure_typography_collection(conn: sqlite3.Connection, file_id: int) -> tuple[int, int]:
    """
    Create or retrieve the Typography collection and Default mode.

    Args:
        conn: Database connection
        file_id: File ID

    Returns:
        Tuple of (collection_id, mode_id)
    """
    # Check if Typography collection exists
    cursor = conn.execute("""
        SELECT id FROM token_collections
        WHERE file_id = ? AND name = 'Typography'
    """, (file_id,))

    row = cursor.fetchone()

    if row:
        collection_id = row['id']
    else:
        # Create Typography collection
        cursor = conn.execute("""
            INSERT INTO token_collections (file_id, name, description)
            VALUES (?, 'Typography', 'Extracted typography tokens')
        """, (file_id,))
        collection_id = cursor.lastrowid
        conn.commit()

    # Check if Default mode exists
    cursor = conn.execute("""
        SELECT id FROM token_modes
        WHERE collection_id = ? AND name = 'Default'
    """, (collection_id,))

    row = cursor.fetchone()

    if row:
        mode_id = row['id']
    else:
        # Create Default mode
        cursor = conn.execute("""
            INSERT INTO token_modes (collection_id, name, is_default)
            VALUES (?, 'Default', 1)
        """, (collection_id,))
        mode_id = cursor.lastrowid
        conn.commit()

    return collection_id, mode_id


def cluster_typography(conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int) -> dict:
    """
    Main entry point for typography clustering.

    Creates individual atomic tokens (fontSize, fontFamily, fontWeight, lineHeight)
    for each type scale tier and updates node bindings.

    Args:
        conn: Database connection
        file_id: File ID to process
        collection_id: Token collection ID
        mode_id: Token mode ID

    Returns:
        Dict with tokens_created, bindings_updated, type_scales counts
    """
    # Query typography census
    census = query_type_census(conn, file_id)

    if not census:
        return {'tokens_created': 0, 'bindings_updated': 0, 'type_scales': 0}

    # Group into type scale tiers
    type_scales = group_type_scale(census)

    # Track created tokens and existing names
    tokens_created = 0
    bindings_updated = 0
    existing_names = set()

    # Get existing token names in this collection
    cursor = conn.execute("""
        SELECT name FROM tokens WHERE collection_id = ?
    """, (collection_id,))
    existing_names.update(row['name'] for row in cursor.fetchall())

    # Process each type scale tier
    for tier in type_scales:
        # Generate base name for this tier
        base_name = propose_type_name(tier['category'], tier['size_suffix'], existing_names)
        # Remove 'type.' prefix for the tier name part
        tier_name = base_name[5:]  # Skip 'type.'

        # Create individual atomic tokens for this tier

        # 1. fontSize token
        font_size_name = f"type.{tier_name}.fontSize"
        if font_size_name not in existing_names:
            cursor = conn.execute("""
                INSERT INTO tokens (collection_id, name, type, tier)
                VALUES (?, ?, 'dimension', 'extracted')
            """, (collection_id, font_size_name))
            font_size_token_id = cursor.lastrowid

            # Insert token value
            conn.execute("""
                INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
                VALUES (?, ?, ?, ?)
            """, (font_size_token_id, mode_id, str(tier['font_size']), str(tier['font_size'])))

            tokens_created += 1
            existing_names.add(font_size_name)

            # Update bindings for nodes matching this font_size + family + weight
            cursor = conn.execute("""
                UPDATE node_token_bindings
                SET token_id = ?, binding_status = 'proposed', confidence = 1.0
                WHERE property = 'fontSize'
                    AND binding_status = 'unbound'
                    AND node_id IN (
                        SELECT n.id FROM nodes n
                        JOIN screens s ON n.screen_id = s.id
                        WHERE s.file_id = ?
                            AND n.font_size = ?
                            AND n.font_family = ?
                            AND n.font_weight = ?
                    )
            """, (font_size_token_id, file_id, tier['font_size'], tier['font_family'], tier['font_weight']))
            bindings_updated += cursor.rowcount

        # 2. fontFamily token
        font_family_name = f"type.{tier_name}.fontFamily"
        if font_family_name not in existing_names:
            cursor = conn.execute("""
                INSERT INTO tokens (collection_id, name, type, tier)
                VALUES (?, ?, 'fontFamily', 'extracted')
            """, (collection_id, font_family_name))
            font_family_token_id = cursor.lastrowid

            # Insert token value
            conn.execute("""
                INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
                VALUES (?, ?, ?, ?)
            """, (font_family_token_id, mode_id, tier['font_family'], tier['font_family']))

            tokens_created += 1
            existing_names.add(font_family_name)

            # Update bindings
            cursor = conn.execute("""
                UPDATE node_token_bindings
                SET token_id = ?, binding_status = 'proposed', confidence = 1.0
                WHERE property = 'fontFamily'
                    AND binding_status = 'unbound'
                    AND node_id IN (
                        SELECT n.id FROM nodes n
                        JOIN screens s ON n.screen_id = s.id
                        WHERE s.file_id = ?
                            AND n.font_size = ?
                            AND n.font_family = ?
                            AND n.font_weight = ?
                    )
            """, (font_family_token_id, file_id, tier['font_size'], tier['font_family'], tier['font_weight']))
            bindings_updated += cursor.rowcount

        # 3. fontWeight token
        font_weight_name = f"type.{tier_name}.fontWeight"
        if font_weight_name not in existing_names:
            cursor = conn.execute("""
                INSERT INTO tokens (collection_id, name, type, tier)
                VALUES (?, ?, 'fontWeight', 'extracted')
            """, (collection_id, font_weight_name))
            font_weight_token_id = cursor.lastrowid

            # Insert token value
            conn.execute("""
                INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
                VALUES (?, ?, ?, ?)
            """, (font_weight_token_id, mode_id, str(tier['font_weight']), str(tier['font_weight'])))

            tokens_created += 1
            existing_names.add(font_weight_name)

            # Update bindings
            cursor = conn.execute("""
                UPDATE node_token_bindings
                SET token_id = ?, binding_status = 'proposed', confidence = 1.0
                WHERE property = 'fontWeight'
                    AND binding_status = 'unbound'
                    AND node_id IN (
                        SELECT n.id FROM nodes n
                        JOIN screens s ON n.screen_id = s.id
                        WHERE s.file_id = ?
                            AND n.font_size = ?
                            AND n.font_family = ?
                            AND n.font_weight = ?
                    )
            """, (font_weight_token_id, file_id, tier['font_size'], tier['font_family'], tier['font_weight']))
            bindings_updated += cursor.rowcount

        # 4. lineHeight token (if not None and if bindings exist)
        # Filter binding update by the tier's specific line_height value via the
        # nodes.line_height JSON column. Without this filter, nodes with different
        # actual lineHeight (AUTO / PIXELS / PERCENT) but the same
        # (font_size, family, weight) would all bind to a single token, causing
        # silent semantic loss flagged later by binding_token_consistency.
        if tier['line_height'] is not None:
            # Check if there are any lineHeight bindings for this tier matching the tier's value
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM node_token_bindings ntb
                JOIN nodes n ON ntb.node_id = n.id
                JOIN screens s ON n.screen_id = s.id
                WHERE ntb.property = 'lineHeight'
                    AND ntb.binding_status = 'unbound'
                    AND s.file_id = ?
                    AND n.font_size = ?
                    AND n.font_family = ?
                    AND n.font_weight = ?
                    AND json_extract(n.line_height, '$.value') = ?
            """, (file_id, tier['font_size'], tier['font_family'], tier['font_weight'], tier['line_height']))

            has_bindings = cursor.fetchone()['count'] > 0

            if has_bindings:
                line_height_name = f"type.{tier_name}.lineHeight"
                if line_height_name not in existing_names:
                    cursor = conn.execute("""
                        INSERT INTO tokens (collection_id, name, type, tier)
                        VALUES (?, ?, 'dimension', 'extracted')
                    """, (collection_id, line_height_name))
                    line_height_token_id = cursor.lastrowid

                    # Insert token value
                    conn.execute("""
                        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
                        VALUES (?, ?, ?, ?)
                    """, (line_height_token_id, mode_id, str(tier['line_height']), str(tier['line_height'])))

                    tokens_created += 1
                    existing_names.add(line_height_name)

                    # Update lineHeight bindings — restricted to nodes whose actual
                    # lineHeight JSON value matches the tier (so AUTO / PERCENT
                    # variants stay unbound and flow to mark_default_bindings).
                    cursor = conn.execute("""
                        UPDATE node_token_bindings
                        SET token_id = ?, binding_status = 'proposed', confidence = 1.0
                        WHERE property = 'lineHeight'
                            AND binding_status = 'unbound'
                            AND node_id IN (
                                SELECT n.id FROM nodes n
                                JOIN screens s ON n.screen_id = s.id
                                WHERE s.file_id = ?
                                    AND n.font_size = ?
                                    AND n.font_family = ?
                                    AND n.font_weight = ?
                                    AND json_extract(n.line_height, '$.value') = ?
                            )
                    """, (line_height_token_id, file_id, tier['font_size'], tier['font_family'], tier['font_weight'], tier['line_height']))
                    bindings_updated += cursor.rowcount

    conn.commit()

    return {
        'tokens_created': tokens_created,
        'bindings_updated': bindings_updated,
        'type_scales': len(type_scales)
    }

def cluster_letter_spacing(conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int) -> dict:
    """Cluster non-zero letterSpacing values into tokens.

    These are specific tracking adjustments (e.g., -0.41px, 0.36px) that
    represent intentional design decisions. Zero values are handled
    separately by mark_default_bindings.

    Returns:
        Dict with tokens_created and bindings_updated.
    """
    import json

    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        """SELECT ntb.resolved_value, COUNT(*) AS usage_count
           FROM node_token_bindings ntb
           JOIN nodes n ON ntb.node_id = n.id
           JOIN screens s ON n.screen_id = s.id
           WHERE ntb.property = 'letterSpacing'
             AND ntb.binding_status = 'unbound'
             AND s.file_id = ?
           GROUP BY ntb.resolved_value
           ORDER BY usage_count DESC""",
        (file_id,)
    )
    census = [dict(row) for row in cursor.fetchall()]

    if not census:
        return {"tokens_created": 0, "bindings_updated": 0}

    tokens_created = 0
    bindings_updated = 0

    for idx, row in enumerate(census):
        raw_json = row['resolved_value']
        parsed = json.loads(raw_json)
        value = parsed.get('value', 0)

        # Round to 2 decimal places for clean token name
        rounded = round(value, 2)
        if rounded == 0:
            continue

        # Name: type.tracking.tight, type.tracking.wide, etc. or by value
        if rounded < -0.3:
            label = f"tight{abs(idx) + 1}" if idx > 0 else "tight"
        elif rounded < 0:
            label = f"snug{idx + 1}" if idx > 0 else "snug"
        else:
            label = f"wide{idx + 1}" if idx > 0 else "wide"

        token_name = f"type.tracking.{label}"

        # Avoid duplicate names
        existing = conn.execute(
            "SELECT id FROM tokens WHERE collection_id = ? AND name = ?",
            (collection_id, token_name)
        ).fetchone()

        if existing:
            token_id = existing['id']
        else:
            cursor = conn.execute(
                """INSERT INTO tokens (collection_id, name, type, tier)
                   VALUES (?, ?, 'dimension', 'extracted')""",
                (collection_id, token_name)
            )
            token_id = cursor.lastrowid
            tokens_created += 1

            conn.execute(
                """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
                   VALUES (?, ?, ?, ?)""",
                (token_id, mode_id, raw_json, str(rounded))
            )

        cursor = conn.execute(
            """UPDATE node_token_bindings
               SET token_id = ?, binding_status = 'proposed', confidence = 0.8
               WHERE resolved_value = ?
                 AND property = 'letterSpacing'
                 AND binding_status = 'unbound'
                 AND node_id IN (
                     SELECT n.id FROM nodes n
                     JOIN screens s ON n.screen_id = s.id
                     WHERE s.file_id = ?
                 )""",
            (token_id, row['resolved_value'], file_id)
        )
        bindings_updated += cursor.rowcount

    conn.commit()
    return {"tokens_created": tokens_created, "bindings_updated": bindings_updated}
