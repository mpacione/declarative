"""Clustering module for radius and effect values.

This module implements Phase 5 radius and effect clustering:
1. Query radius/effect census from database
2. Group effects by composite shadows
3. Propose token names (t-shirt sizes)
4. Create atomic tokens and update bindings
"""

import sqlite3
from collections import defaultdict
from collections.abc import Callable, Hashable
from typing import Any

from dd.color import hex_to_oklch, oklch_delta_e


def assign_bucketed_rank_names(
    items: list[dict],
    bucket_key: Callable[[dict], Hashable],
    bucket_sort_key: Callable[[Hashable], Any],
    base_name_for_bucket_index: Callable[[int, int], str],
    value_sort_key: Callable[[dict], Any],
) -> list[tuple[dict, str]]:
    """Assign stable bucketed-rank names with a usage-count tiebreaker.

    Token IDENTITY is exact value (each item is its own token); base NAME
    is a coarser bucket. Within a bucket, the item with the highest
    `usage_count` keeps the bare name (e.g. ``radius.xs``); subsequent
    items get ``.2``, ``.3`` suffixes. This decouples value-splitting
    (F6) from name-shuffling (F6.1).

    Args:
        items: list of dicts with at least ``usage_count``.
        bucket_key: callable returning a hashable bucket key per item.
        bucket_sort_key: callable returning the sort key for buckets
            (applied to the bucket key, not items). Buckets are sorted
            ascending by this key.
        base_name_for_bucket_index: callable ``(bucket_idx, n_buckets)
            -> str`` returning the bare name for a bucket.
        value_sort_key: callable returning the within-bucket sort key
            (applied to items). Used as the secondary tiebreaker after
            usage_count.

    Returns:
        List of ``(item, name)`` tuples, in iteration order grouped by
        bucket then within-bucket rank. Determinism: same inputs (and
        hashable keys with stable orderings) produce identical names.
    """
    if not items:
        return []

    buckets: dict[Hashable, list[dict]] = {}
    for item in items:
        key = bucket_key(item)
        buckets.setdefault(key, []).append(item)

    sorted_bucket_keys = sorted(buckets.keys(), key=bucket_sort_key)

    assignments: list[tuple[dict, str]] = []
    for bucket_idx, b_key in enumerate(sorted_bucket_keys):
        bucket_items = buckets[b_key]
        # Stable sort: usage_count DESC primary; value_sort_key ASC tiebreaker.
        bucket_items.sort(
            key=lambda it: (-int(it.get('usage_count', 0)), value_sort_key(it))
        )
        base_name = base_name_for_bucket_index(bucket_idx, len(sorted_bucket_keys))
        for rank, item in enumerate(bucket_items):
            name = base_name if rank == 0 else f"{base_name}.{rank + 1}"
            assignments.append((item, name))

    return assignments


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


_FULL_RADIUS_BUCKET = 99999


def _radius_bucket_key(item: dict) -> int:
    """Bucket key for radius items: rounded value (sub-pixel collapses).

    0 and 9999+ collapse to ``_FULL_RADIUS_BUCKET`` (semantically "full").
    All other values round to nearest integer for the NAME bucket; the
    item's exact value still becomes its own token (identity preserved).
    """
    val = float(item['resolved_value'])
    if val == 0 or val >= 9999:
        return _FULL_RADIUS_BUCKET
    return round(val)


def _radius_bucket_sort_key(bucket_key: int) -> tuple[int, int]:
    """Sort buckets numerically; full radius pinned to end."""
    if bucket_key == _FULL_RADIUS_BUCKET:
        return (1, 0)
    return (0, bucket_key)


def _radius_value_sort_key(item: dict) -> float:
    """Within-bucket tiebreaker after usage_count: numeric value asc."""
    return float(item['resolved_value'])


def cluster_radius(conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int) -> dict:
    """Cluster radius values and create tokens.

    F6 (commit 29faf24): groups by EXACT value so semantically distinct
    radii (e.g. 0.75 vs 1.0) never collapse into one token.

    F6.1: bucketed naming with usage-rank tiebreaker. The bucket
    (rounded value) determines the bare base name (``radius.xs``,
    ``radius.sm``, …). Within a bucket, the highest-usage exact value
    keeps the bare name; secondary values get ``.2``, ``.3`` suffixes.
    This stabilizes name → value mapping across runs that previously
    reshuffled when a low-usage variant entered the corpus.

    Args:
        conn: Database connection
        file_id: File ID to process
        collection_id: Collection to add tokens to
        mode_id: Mode to add token values to

    Returns:
        Dict with tokens_created and bindings_updated counts
    """
    census = query_radius_census(conn, file_id)
    if not census:
        return {"tokens_created": 0, "bindings_updated": 0}

    # Pre-aggregate the FULL bucket: 0 and 9999+ are semantically the
    # same radius (fully circular), so they collapse into ONE token.
    # All other values keep their own token (F6 identity preservation).
    items: list[dict] = []
    full_originals: list[str] = []
    full_usage = 0
    for row in census:
        val = float(row['resolved_value'])
        if val == 0 or val >= 9999:
            full_originals.append(row['resolved_value'])
            full_usage += int(row['usage_count'])
        else:
            items.append(dict(row))

    if full_originals:
        items.append({
            'resolved_value': str(_FULL_RADIUS_BUCKET),
            'usage_count': full_usage,
            '_full_originals': full_originals,
        })

    bucket_keys = {_radius_bucket_key(it) for it in items}
    has_full = _FULL_RADIUS_BUCKET in bucket_keys

    def base_name_for_bucket(bucket_idx: int, n_buckets: int) -> str:
        # bucket_idx is the position in sort_key order (full last when present).
        # propose_radius_name expects (value, index, total, has_full); we pass a
        # sentinel value derived from has_full + bucket position so the
        # existing t-shirt mapping continues to work unchanged.
        sorted_keys = sorted(bucket_keys, key=_radius_bucket_sort_key)
        b_key = sorted_keys[bucket_idx]
        sentinel_value = float(_FULL_RADIUS_BUCKET) if b_key == _FULL_RADIUS_BUCKET else float(b_key)
        return propose_radius_name(sentinel_value, bucket_idx, n_buckets, has_full)

    assignments = assign_bucketed_rank_names(
        items=items,
        bucket_key=_radius_bucket_key,
        bucket_sort_key=_radius_bucket_sort_key,
        base_name_for_bucket_index=base_name_for_bucket,
        value_sort_key=_radius_value_sort_key,
    )

    tokens_created = 0
    bindings_updated = 0

    for item, name in assignments:
        # FULL bucket items carry _full_originals (list of source values)
        # and a synthetic representative value; non-full items carry the
        # exact resolved value.
        full_originals_for_item = item.get('_full_originals')
        original_value = item['resolved_value']

        cursor = conn.execute(
            """SELECT id FROM tokens WHERE collection_id = ? AND name = ?""",
            (collection_id, name)
        )
        existing_token = cursor.fetchone()

        if existing_token:
            token_id = existing_token['id']
        else:
            cursor = conn.execute(
                """INSERT INTO tokens (collection_id, name, type, tier)
                   VALUES (?, ?, 'dimension', 'extracted')""",
                (collection_id, name)
            )
            token_id = cursor.lastrowid
            tokens_created += 1

        conn.execute(
            """INSERT OR REPLACE INTO token_values (token_id, mode_id, raw_value, resolved_value)
               VALUES (?, ?, ?, ?)""",
            (token_id, mode_id, str(original_value), str(original_value))
        )

        # Bind every original value mapped to this token (one per
        # non-full item; many for the full bucket).
        binding_values = full_originals_for_item or [original_value]
        for raw_value in binding_values:
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
                (token_id, raw_value, file_id),
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


def _effect_bucket_key(comp: dict) -> tuple[int, int, int, int]:
    """Bucket key for an effect composite: rounded shadow geometry.

    Color is intentionally excluded — colors with the same geometry but
    different alphas/hues should still share the size bucket so users
    see ``shadow.sm`` + ``shadow.sm.2`` rather than two unrelated names.
    """
    return (
        round(float(comp.get('radius', 0) or 0)),
        round(float(comp.get('offsetX', 0) or 0)),
        round(float(comp.get('offsetY', 0) or 0)),
        round(float(comp.get('spread', 0) or 0)),
    )


def _effect_bucket_sort_key(b_key: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Sort buckets by rounded radius (size), then offsetY, offsetX, spread."""
    radius, offset_x, offset_y, spread = b_key
    return (radius, offset_y, offset_x, spread)


def _effect_value_sort_key(comp: dict) -> tuple[float, float, float, float, str]:
    """Within-bucket tiebreaker after usage_count: numeric value asc."""
    return (
        float(comp.get('radius', 0) or 0),
        float(comp.get('offsetY', 0) or 0),
        float(comp.get('offsetX', 0) or 0),
        float(comp.get('spread', 0) or 0),
        str(comp.get('color', '')),
    )


def cluster_effects(conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int) -> dict:
    """Cluster effect values and create atomic tokens.

    Creates individual tokens for each effect field (color, radius, offsetX, offsetY, spread)
    following the design that composite tokens are stored as atomic tokens in the DB.

    F6.1: bucketed naming with usage-rank tiebreaker. The bucket
    (rounded radius/offsetX/offsetY/spread) determines the bare base
    name (``shadow.sm``, ``shadow.md``, …). Within a bucket, the
    highest-usage composite keeps the bare name; secondary composites
    get ``.2``, ``.3`` suffixes. Geometry-different shadows continue
    to land in different buckets — only near-identical composites
    (e.g. radius 23.9 vs 24.0) trigger the in-bucket tiebreaker.

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

    # Compute bucketed assignments. Each composite carries usage_count
    # and node_ids already from group_effects_by_composite.
    bucket_keys = {_effect_bucket_key(c) for c in composites}
    n_buckets = len(bucket_keys)

    def base_name_for_bucket(bucket_idx: int, _n: int) -> str:
        return propose_effect_name(bucket_idx, n_buckets)

    assignments = assign_bucketed_rank_names(
        items=composites,
        bucket_key=_effect_bucket_key,
        bucket_sort_key=_effect_bucket_sort_key,
        base_name_for_bucket_index=base_name_for_bucket,
        value_sort_key=_effect_value_sort_key,
    )

    for composite, base_name in assignments:
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

# ============================================================================
# Opacity clustering
# ============================================================================

def ensure_opacity_collection(conn: sqlite3.Connection, file_id: int) -> tuple[int, int]:
    """Create or retrieve Opacity collection and Default mode."""
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        "SELECT id FROM token_collections WHERE file_id = ? AND name = 'Opacity'",
        (file_id,)
    )
    row = cursor.fetchone()

    if row:
        collection_id = row['id']
    else:
        cursor = conn.execute(
            """INSERT INTO token_collections (file_id, name, created_at)
               VALUES (?, 'Opacity', datetime('now'))""",
            (file_id,)
        )
        collection_id = cursor.lastrowid

    cursor = conn.execute(
        "SELECT id FROM token_modes WHERE collection_id = ? AND name = 'Default'",
        (collection_id,)
    )
    row = cursor.fetchone()

    if row:
        mode_id = row['id']
    else:
        cursor = conn.execute(
            """INSERT INTO token_modes (collection_id, name, is_default)
               VALUES (?, 'Default', 1)""",
            (collection_id,)
        )
        mode_id = cursor.lastrowid

    conn.commit()
    return (collection_id, mode_id)


def ensure_stroke_weight_collection(
    conn: sqlite3.Connection, file_id: int,
) -> tuple[int, int]:
    """Create or retrieve Stroke Weight collection and Default mode.

    P3b (Phase E C2 fix): `cluster_stroke_weight` exists as a function
    (line 948 below) but had no orchestrator wiring. Phase E §2 found
    6093 unbound `strokeWeight=1.0` bindings (76% of all unbound)
    because the orchestrator never invoked the clusterer for this
    axis. This `ensure_*_collection` helper supplies the missing
    `(collection_id, mode_id)` pair so the orchestrator can call
    cluster_stroke_weight.

    Mirrors `ensure_opacity_collection` / `ensure_radius_collection`.
    Codex P3b design review (2026-04-25): "Give strokeWeight its own
    'Stroke Weight' collection. Don't put it in 'Defaults'; even if
    1.0 dominates, border width is a real reusable visual token."
    """
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        "SELECT id FROM token_collections WHERE file_id = ? AND name = 'Stroke Weight'",
        (file_id,),
    )
    row = cursor.fetchone()

    if row:
        collection_id = row["id"]
    else:
        cursor = conn.execute(
            """INSERT INTO token_collections (file_id, name, created_at)
               VALUES (?, 'Stroke Weight', datetime('now'))""",
            (file_id,),
        )
        collection_id = cursor.lastrowid

    cursor = conn.execute(
        "SELECT id FROM token_modes WHERE collection_id = ? AND name = 'Default'",
        (collection_id,),
    )
    row = cursor.fetchone()

    if row:
        mode_id = row["id"]
    else:
        cursor = conn.execute(
            """INSERT INTO token_modes (collection_id, name, is_default)
               VALUES (?, 'Default', 1)""",
            (collection_id,),
        )
        mode_id = cursor.lastrowid

    conn.commit()
    return (collection_id, mode_id)


def cluster_opacity(conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int) -> dict:
    """Cluster opacity values into tokens.

    Opacity has very few unique values (typically 3-5), so no perceptual
    grouping is needed - each unique value becomes its own token.

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
           WHERE ntb.property = 'opacity'
             AND ntb.binding_status = 'unbound'
             AND s.file_id = ?
           GROUP BY ntb.resolved_value
           ORDER BY CAST(ntb.resolved_value AS REAL)""",
        (file_id,)
    )
    census = [dict(row) for row in cursor.fetchall()]

    if not census:
        return {"tokens_created": 0, "bindings_updated": 0}

    tokens_created = 0
    bindings_updated = 0

    for row in census:
        raw_value = float(row['resolved_value'])
        pct = round(raw_value * 100)
        token_name = f"opacity.{pct}"

        cursor = conn.execute(
            """INSERT OR IGNORE INTO tokens (collection_id, name, type, tier)
               VALUES (?, ?, 'number', 'extracted')""",
            (collection_id, token_name)
        )
        if cursor.lastrowid:
            token_id = cursor.lastrowid
            tokens_created += 1

            conn.execute(
                """INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
                   VALUES (?, ?, ?, ?)""",
                (token_id, mode_id, json.dumps(raw_value), str(raw_value))
            )
        else:
            token_id = conn.execute(
                "SELECT id FROM tokens WHERE collection_id = ? AND name = ?",
                (collection_id, token_name)
            ).fetchone()['id']

        cursor = conn.execute(
            """UPDATE node_token_bindings
               SET token_id = ?, binding_status = 'proposed', confidence = 1.0
               WHERE resolved_value = ?
                 AND property = 'opacity'
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


def _cluster_simple_dimension(
    conn: sqlite3.Connection,
    file_id: int,
    collection_id: int,
    mode_id: int,
    property_name: str,
    token_prefix: str,
) -> dict:
    """Generic clustering for a single dimension property.

    Queries unbound bindings for the given property, creates a token per
    unique value, and updates bindings to 'proposed'.
    """
    conn.row_factory = sqlite3.Row

    census = conn.execute(
        """SELECT ntb.resolved_value, COUNT(*) AS usage_count
           FROM node_token_bindings ntb
           JOIN nodes n ON ntb.node_id = n.id
           JOIN screens s ON n.screen_id = s.id
           WHERE s.file_id = ?
             AND ntb.property = ?
             AND ntb.binding_status = 'unbound'
           GROUP BY ntb.resolved_value
           ORDER BY CAST(ntb.resolved_value AS REAL)""",
        (file_id, property_name),
    ).fetchall()

    if not census:
        return {"tokens_created": 0, "bindings_updated": 0}

    tokens_created = 0
    bindings_updated = 0
    existing_names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM tokens WHERE collection_id = ?", (collection_id,)
        ).fetchall()
    }

    for row in census:
        val_str = row["resolved_value"]
        try:
            val = float(val_str)
        except (ValueError, TypeError):
            continue
        if val == 0:
            continue

        name = f"{token_prefix}.v{int(val)}" if val == int(val) else f"{token_prefix}.v{val}"
        if name in existing_names:
            continue
        existing_names.add(name)

        cursor = conn.execute(
            "INSERT INTO tokens (collection_id, name, type, tier) VALUES (?, ?, 'dimension', 'extracted')",
            (collection_id, name),
        )
        token_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, ?, ?)",
            (token_id, mode_id, val_str, val_str),
        )
        tokens_created += 1

        cursor = conn.execute(
            """UPDATE node_token_bindings
               SET token_id = ?, binding_status = 'proposed', confidence = 1.0
               WHERE resolved_value = ?
                 AND property = ?
                 AND binding_status = 'unbound'
                 AND node_id IN (
                     SELECT n.id FROM nodes n
                     JOIN screens s ON n.screen_id = s.id
                     WHERE s.file_id = ?
                 )""",
            (token_id, val_str, property_name, file_id),
        )
        bindings_updated += cursor.rowcount

    conn.commit()
    return {"tokens_created": tokens_created, "bindings_updated": bindings_updated}


def cluster_stroke_weight(
    conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int
) -> dict:
    """Cluster stroke weight values into tokens."""
    return _cluster_simple_dimension(
        conn, file_id, collection_id, mode_id, "strokeWeight", "strokeWeight"
    )


def cluster_paragraph_spacing(
    conn: sqlite3.Connection, file_id: int, collection_id: int, mode_id: int
) -> dict:
    """Cluster paragraph spacing values into tokens."""
    return _cluster_simple_dimension(
        conn, file_id, collection_id, mode_id, "paragraphSpacing", "paragraphSpacing"
    )
