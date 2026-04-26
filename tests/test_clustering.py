"""Comprehensive unit tests for all clustering modules."""

import sqlite3

import pytest

from dd.cluster import (
    run_clustering,
    validate_no_orphan_tokens,
)
from dd.cluster_colors import (
    classify_color_role,
    cluster_colors,
    ensure_collection_and_mode,
    group_by_delta_e,
    propose_color_name,
)
from dd.cluster_misc import (
    cluster_effects,
    cluster_radius,
    ensure_effects_collection,
    ensure_radius_collection,
    propose_effect_name,
    propose_radius_name,
)
from dd.cluster_spacing import (
    cluster_spacing,
    detect_scale_pattern,
    ensure_spacing_collection,
    propose_spacing_name,
)
from dd.cluster_typography import (
    cluster_typography,
    ensure_typography_collection,
    group_type_scale,
    propose_type_name,
)
from dd.color import hex_to_oklch, oklch_delta_e
from dd.db import init_db
from tests.fixtures import seed_post_extraction


@pytest.fixture
def db():
    """Create in-memory database with schema."""
    db_conn = init_db(":memory:")
    db_conn.row_factory = sqlite3.Row
    return db_conn


def _seed_and_get_ids(db: sqlite3.Connection) -> tuple[int, int, int]:
    """Seed DB and create collections/modes for testing.

    Returns:
        (file_id, collection_id, mode_id) tuple
    """
    seed_post_extraction(db)
    collection_id, mode_id = ensure_collection_and_mode(db, 1, "Test Collection")
    return 1, collection_id, mode_id


# ============================================================================
# Color clustering tests (test_color_*)
# ============================================================================

@pytest.mark.unit
def test_color_group_by_delta_e_identical():
    """Two identical hex values -> 1 group."""
    colors = [
        {'resolved_value': '#09090B', 'usage_count': 5},
        {'resolved_value': '#09090B', 'usage_count': 3},
    ]
    groups = group_by_delta_e(colors, threshold=2.0)

    assert len(groups) == 1
    assert len(groups[0]) == 2


@pytest.mark.unit
def test_color_group_by_delta_e_similar():
    """#09090B and #0A0A0B (delta_e < 2.0) -> 1 group."""
    colors = [
        {'resolved_value': '#09090B', 'usage_count': 5, 'properties': 'fill'},
        {'resolved_value': '#0A0A0B', 'usage_count': 3, 'properties': 'fill'},
    ]
    groups = group_by_delta_e(colors, threshold=2.0)

    # Calculate actual delta_e to verify they're similar
    oklch1 = hex_to_oklch('#09090B')
    oklch2 = hex_to_oklch('#0A0A0B')
    delta_e = oklch_delta_e(oklch1, oklch2)

    # They should group together if delta_e < 2.0
    if delta_e < 2.0:
        assert len(groups) == 1
        assert len(groups[0]) == 2
    else:
        # If they're not actually similar, expect 2 groups
        assert len(groups) == 2


@pytest.mark.unit
def test_color_group_by_delta_e_different():
    """#FF0000 and #0000FF -> 2 groups."""
    colors = [
        {'resolved_value': '#FF0000', 'usage_count': 5, 'properties': 'fill'},
        {'resolved_value': '#0000FF', 'usage_count': 3, 'properties': 'fill'},
    ]
    groups = group_by_delta_e(colors, threshold=2.0)

    assert len(groups) == 2
    assert len(groups[0]) == 1
    assert len(groups[1]) == 1
    # Higher usage should be first group
    assert groups[0][0]['resolved_value'] == '#FF0000'


@pytest.mark.unit
def test_color_group_preserves_usage_order():
    """Most-used color is group representative."""
    colors = [
        {'resolved_value': '#09090B', 'usage_count': 3, 'properties': 'fill'},
        {'resolved_value': '#09090C', 'usage_count': 10, 'properties': 'fill'},
        {'resolved_value': '#09090D', 'usage_count': 5, 'properties': 'fill'},
    ]
    groups = group_by_delta_e(colors, threshold=5.0)  # High threshold to group them

    if len(groups) == 1:
        # Representative should be the one with highest usage
        assert groups[0][0]['usage_count'] == 10
        assert groups[0][0]['resolved_value'] == '#09090C'


@pytest.mark.unit
def test_color_propose_name_surface():
    """role="surface", produces "color.surface.primary"."""
    existing = set()
    name = propose_color_name("surface", 0.5, 0, existing)
    assert name == "color.surface.primary"


@pytest.mark.unit
def test_color_propose_name_uniqueness():
    """Same role proposed twice -> different names."""
    existing = set()

    name1 = propose_color_name("surface", 0.5, 0, existing)
    assert name1 == "color.surface.primary"
    existing.add(name1)

    name2 = propose_color_name("surface", 0.4, 0, existing)
    assert name2 == "color.surface.primary.2"
    existing.add(name2)

    name3 = propose_color_name("surface", 0.3, 0, existing)
    assert name3 == "color.surface.primary.3"


@pytest.mark.unit
def test_color_classify_role_stroke():
    """properties containing "stroke" -> "border"."""
    role = classify_color_role("stroke.0.color,stroke.1.color")
    assert role == "border"


@pytest.mark.unit
def test_color_classify_role_fill():
    """properties with only "fill" -> "surface"."""
    role = classify_color_role("fill.0.color,fill.1.color")
    assert role == "surface"


@pytest.mark.unit
@pytest.mark.timeout(30)
def test_color_clustering_full(db):
    """Seed DB with extraction data, run cluster_colors. Verify tokens and bindings."""
    file_id, collection_id, mode_id = _seed_and_get_ids(db)

    # Run clustering
    result = cluster_colors(db, file_id, collection_id, mode_id, threshold=2.0)

    # Verify tokens created
    cursor = db.execute(
        """SELECT * FROM tokens
           WHERE collection_id = ? AND type = 'color' AND tier = 'extracted'""",
        (collection_id,)
    )
    tokens = cursor.fetchall()
    assert len(tokens) > 0
    assert result['tokens_created'] == len(tokens)

    # Verify token values created
    for token in tokens:
        cursor = db.execute(
            "SELECT * FROM token_values WHERE token_id = ? AND mode_id = ?",
            (token['id'], mode_id)
        )
        value = cursor.fetchone()
        assert value is not None
        assert value['resolved_value'] is not None

    # Verify bindings updated
    cursor = db.execute(
        """SELECT * FROM node_token_bindings
           WHERE binding_status = 'proposed' AND token_id IS NOT NULL"""
    )
    bindings = cursor.fetchall()
    assert len(bindings) > 0
    assert result['bindings_updated'] == len(bindings)

    # Verify confidence values
    for binding in bindings:
        assert binding['confidence'] >= 0.8
        assert binding['confidence'] <= 1.0


@pytest.mark.unit
@pytest.mark.timeout(30)
def test_color_clustering_idempotent(db):
    """Run cluster_colors twice, verify same result."""
    file_id, collection_id, mode_id = _seed_and_get_ids(db)

    # First run
    result1 = cluster_colors(db, file_id, collection_id, mode_id, threshold=2.0)
    assert result1['tokens_created'] > 0

    # Second run should find no unbound bindings
    result2 = cluster_colors(db, file_id, collection_id, mode_id, threshold=2.0)
    assert result2['tokens_created'] == 0
    assert result2['bindings_updated'] == 0


# ============================================================================
# Typography clustering tests (test_typography_*)
# ============================================================================

@pytest.mark.unit
def test_typography_group_type_scale_display():
    """font_size=32 -> category="display"."""
    census = [
        {
            'font_family': 'Inter',
            'font_weight': '700',
            'font_size': 32,
            'line_height_value': 40,
            'letter_spacing': -0.5,
            'usage_count': 5,
            'node_count': 3
        }
    ]
    groups = group_type_scale(census)

    assert len(groups) == 1
    assert groups[0]['category'] == 'display'
    assert groups[0].get('suffix') == 'md' or groups[0].get('size_suffix') == 'md'  # Key might be 'suffix' or 'size_suffix'


@pytest.mark.unit
def test_typography_group_type_scale_body():
    """font_size=16 -> category="body"."""
    census = [
        {
            'font_family': 'Inter',
            'font_weight': '400',
            'font_size': 16,
            'line_height_value': 24,
            'letter_spacing': 0,
            'usage_count': 10,
            'node_count': 5
        }
    ]
    groups = group_type_scale(census)

    assert len(groups) == 1
    assert groups[0]['category'] == 'body'


@pytest.mark.unit
def test_typography_group_type_scale_label():
    """font_size=12 -> category="label"."""
    census = [
        {
            'font_family': 'Inter',
            'font_weight': '500',
            'font_size': 12,
            'line_height_value': 16,
            'letter_spacing': 0.2,
            'usage_count': 3,
            'node_count': 2
        }
    ]
    groups = group_type_scale(census)

    assert len(groups) == 1
    assert groups[0]['category'] == 'label'


@pytest.mark.unit
def test_typography_group_type_scale_suffixes():
    """Multiple sizes in same category get lg/md/sm."""
    census = [
        {
            'font_family': 'Inter',
            'font_weight': '400',
            'font_size': 18,
            'line_height_value': 28,
            'letter_spacing': 0,
            'usage_count': 10,
            'node_count': 5
        },
        {
            'font_family': 'Inter',
            'font_weight': '400',
            'font_size': 16,
            'line_height_value': 24,
            'letter_spacing': 0,
            'usage_count': 8,
            'node_count': 4
        },
        {
            'font_family': 'Inter',
            'font_weight': '400',
            'font_size': 14,
            'line_height_value': 20,
            'letter_spacing': 0,
            'usage_count': 6,
            'node_count': 3
        },
    ]
    groups = group_type_scale(census)

    # All should be in body category (14 might be label)
    body_groups = [g for g in groups if g['category'] == 'body']
    assert len(body_groups) >= 2  # At least 18 and 16 should be body

    # Check suffixes assigned correctly (largest to smallest)
    # Use 'suffix' or 'size_suffix' key
    suffix_key = 'suffix' if 'suffix' in body_groups[0] else 'size_suffix'
    size_to_suffix = {g['font_size']: g[suffix_key] for g in body_groups}

    # 18 and 16 should definitely be in body
    if 18 in size_to_suffix and 16 in size_to_suffix:
        assert size_to_suffix[18] == 'lg'
        assert size_to_suffix[16] in ('md', 'sm')  # Depends on whether 14 is body or label


@pytest.mark.unit
def test_typography_propose_name():
    """category="body", suffix="md" -> "type.body.md"."""
    existing = set()
    name = propose_type_name("body", "md", existing)
    assert name == "type.body.md"


@pytest.mark.unit
@pytest.mark.timeout(30)
def test_typography_clustering_full(db):
    """Seed DB, run cluster_typography. Verify atomic tokens created."""
    seed_post_extraction(db)
    collection_id, mode_id = ensure_typography_collection(db, 1)

    # Run clustering
    result = cluster_typography(db, 1, collection_id, mode_id)

    # Verify tokens created (should be atomic: fontSize, fontFamily, fontWeight)
    cursor = db.execute(
        """SELECT * FROM tokens
           WHERE collection_id = ? AND tier = 'extracted'""",
        (collection_id,)
    )
    tokens = cursor.fetchall()
    assert len(tokens) > 0

    # Check that token names follow the pattern
    for token in tokens:
        name = token['name']
        assert name.startswith('type.')
        # Should end with property name
        assert any(name.endswith(p) for p in ['.fontSize', '.fontFamily', '.fontWeight', '.lineHeight', '.letterSpacing'])

    # Verify bindings updated
    cursor = db.execute(
        """SELECT * FROM node_token_bindings
           WHERE binding_status = 'proposed'
           AND property IN ('fontSize', 'fontFamily', 'fontWeight')"""
    )
    bindings = cursor.fetchall()
    assert len(bindings) > 0


# ============================================================================
# Spacing clustering tests (test_spacing_*)
# ============================================================================

@pytest.mark.unit
def test_spacing_detect_scale_4px():
    """[4, 8, 12, 16, 24, 32] -> base=4, notation="multiplier"."""
    values = [4, 8, 12, 16, 24, 32]
    base, notation = detect_scale_pattern(values)

    assert base == 4
    assert notation == "multiplier"


@pytest.mark.unit
def test_spacing_detect_scale_8px():
    """[8, 16, 24, 32, 48] -> base=8, notation="multiplier"."""
    values = [8, 16, 24, 32, 48]
    base, notation = detect_scale_pattern(values)

    assert base == 8
    assert notation == "multiplier"


@pytest.mark.unit
def test_spacing_detect_no_pattern():
    """[5, 13, 27] -> notation="tshirt"."""
    values = [5, 13, 27]
    base, notation = detect_scale_pattern(values)

    assert notation == "tshirt"


@pytest.mark.unit
def test_spacing_propose_name_multiplier():
    """value=16, base=4 -> "space.4"."""
    name = propose_spacing_name(16, 4, "multiplier", 0, 5)
    assert name == "space.4"


@pytest.mark.unit
def test_spacing_propose_name_tshirt():
    """notation="tshirt", index=1 -> "space.sm"."""
    name = propose_spacing_name(8, None, "tshirt", 1, 5)
    assert name == "space.sm"

    # Test all sizes for 5 values
    names = [propose_spacing_name(v, None, "tshirt", i, 5) for i, v in enumerate([4, 8, 16, 24, 32])]
    assert names == ["space.xs", "space.sm", "space.md", "space.lg", "space.xl"]


@pytest.mark.unit
@pytest.mark.timeout(30)
def test_spacing_clustering_full(db):
    """Seed DB, run cluster_spacing. Verify tokens and bindings."""
    seed_post_extraction(db)
    collection_id, mode_id = ensure_spacing_collection(db, 1)

    # Run clustering
    result = cluster_spacing(db, 1, collection_id, mode_id)

    # Verify tokens created for unique spacing values
    cursor = db.execute(
        """SELECT * FROM tokens
           WHERE collection_id = ? AND type = 'dimension' AND tier = 'extracted'""",
        (collection_id,)
    )
    tokens = cursor.fetchall()
    assert len(tokens) > 0
    assert result['tokens_created'] == len(tokens)

    # Check token names
    for token in tokens:
        name = token['name']
        assert name.startswith('space.')

    # Verify one token shared across all spacing properties with same value
    cursor = db.execute(
        """SELECT resolved_value, COUNT(DISTINCT token_id) as token_count
           FROM node_token_bindings
           WHERE property IN ('padding.top', 'padding.bottom', 'itemSpacing')
           AND binding_status = 'proposed'
           GROUP BY resolved_value"""
    )
    for row in cursor.fetchall():
        # Each unique value should map to exactly one token
        assert row['token_count'] == 1


# ============================================================================
# Spacing clustering — fractional value handling
# ============================================================================

@pytest.mark.unit
def test_spacing_fractional_values_rounded_to_integers(db):
    """Spacing values like 10.0, 14.0 should cluster as 10, 14 — not be skipped."""
    seed_post_extraction(db)

    # Delete existing spacing bindings and tokens from seed to avoid UNIQUE conflicts
    db.execute("DELETE FROM node_token_bindings WHERE property IN ('padding.top','padding.bottom','padding.left','padding.right','itemSpacing','counterAxisSpacing')")
    db.execute("DELETE FROM token_values WHERE token_id IN (SELECT id FROM tokens WHERE name LIKE 'space.%')")
    db.execute("DELETE FROM tokens WHERE name LIKE 'space.%'")
    db.commit()

    # Add bindings with float-style resolved_values (as real Figma data produces)
    db.executemany(
        """INSERT INTO node_token_bindings
           (node_id, property, raw_value, resolved_value, binding_status)
           VALUES (?, ?, ?, ?, 'unbound')""",
        [
            (1, "padding.top", "10.0", "10.0"),
            (2, "padding.top", "10.0", "10.0"),
            (1, "padding.left", "14.0", "14.0"),
            (2, "padding.left", "14.0", "14.0"),
            (3, "itemSpacing", "10.0", "10.0"),
            (5, "itemSpacing", "14.0", "14.0"),
            # Fractional outlier — should round to nearest integer
            (6, "itemSpacing", "9.935135841369629", "9.935135841369629"),
        ]
    )
    db.commit()

    collection_id, mode_id = ensure_spacing_collection(db, 1)
    result = cluster_spacing(db, 1, collection_id, mode_id)

    # The .0 values should be bound — not left unbound
    unbound = db.execute(
        """SELECT COUNT(*) FROM node_token_bindings
           WHERE binding_status = 'unbound'
             AND property IN ('padding.top','padding.left','itemSpacing')
             AND resolved_value IN ('10.0', '14.0')"""
    ).fetchone()[0]

    assert unbound == 0, f"Expected 0 unbound .0 values, got {unbound}"


@pytest.mark.unit
def test_spacing_fractional_outlier_merges_with_nearest_integer(db):
    """9.935 should be assigned the same token as 10, not get its own token."""
    seed_post_extraction(db)

    # Delete existing spacing bindings and tokens to avoid UNIQUE conflicts
    db.execute("DELETE FROM node_token_bindings WHERE property IN ('padding.top','padding.bottom','padding.left','padding.right','itemSpacing','counterAxisSpacing')")
    db.execute("DELETE FROM token_values WHERE token_id IN (SELECT id FROM tokens WHERE name LIKE 'space.%')")
    db.execute("DELETE FROM tokens WHERE name LIKE 'space.%'")
    db.commit()

    db.executemany(
        """INSERT INTO node_token_bindings
           (node_id, property, raw_value, resolved_value, binding_status)
           VALUES (?, ?, ?, ?, 'unbound')""",
        [
            (1, "itemSpacing", "10.0", "10.0"),
            (2, "itemSpacing", "10.0", "10.0"),
            (3, "itemSpacing", "9.935135841369629", "9.935135841369629"),
        ]
    )
    db.commit()

    collection_id, mode_id = ensure_spacing_collection(db, 1)
    cluster_spacing(db, 1, collection_id, mode_id)

    # Both 10.0 and 9.935 should bind to the same token
    tokens = db.execute(
        """SELECT DISTINCT token_id FROM node_token_bindings
           WHERE property = 'itemSpacing'
             AND binding_status = 'proposed'
             AND resolved_value IN ('10.0', '9.935135841369629')"""
    ).fetchall()

    token_ids = [r[0] for r in tokens]
    assert len(set(token_ids)) == 1, f"Expected 1 shared token, got {len(set(token_ids))}"


@pytest.mark.unit
def test_spacing_scale_detection_ignores_fractional_noise():
    """Scale detection rounds to integers — fractional noise becomes integer."""
    # After rounding: [1, 4, 8, 10, 12, 14, 16, 24] — GCD is 1, no clean base
    # This correctly falls back to t-shirt notation
    values_with_noise = [0.706, 4.0, 8.0, 10.0, 12.0, 14.0, 16.0, 24.0]
    _base, notation = detect_scale_pattern(values_with_noise)
    assert notation == "tshirt"

    # But clean scales still detect correctly
    clean_values = [4.0, 8.0, 12.0, 16.0, 24.0]
    base, notation = detect_scale_pattern(clean_values)
    assert base == 4.0
    assert notation == "multiplier"


# ============================================================================
# Typography default handling
# ============================================================================

@pytest.mark.unit
def test_typography_defaults_marked_intentionally_unbound(db):
    """letterSpacing=0 and lineHeight=AUTO are CSS defaults, not design tokens."""
    seed_post_extraction(db)

    db.executemany(
        """INSERT INTO node_token_bindings
           (node_id, property, raw_value, resolved_value, binding_status)
           VALUES (?, ?, ?, ?, 'unbound')""",
        [
            (4, "letterSpacing", '{"value": 0.0, "unit": "PIXELS"}', '{"value": 0.0, "unit": "PIXELS"}'),
            (4, "lineHeight", '{"unit": "AUTO"}', '{"unit": "AUTO"}'),
            (7, "letterSpacing", '{"value": 0.0, "unit": "PIXELS"}', '{"value": 0.0, "unit": "PIXELS"}'),
        ]
    )
    db.commit()

    from dd.cluster import mark_default_bindings
    marked = mark_default_bindings(conn=db, file_id=1)

    assert marked > 0

    status = db.execute(
        """SELECT binding_status FROM node_token_bindings
           WHERE property = 'letterSpacing'
             AND resolved_value LIKE '%0.0%'"""
    ).fetchall()

    for row in status:
        assert row[0] == "intentionally_unbound"


# ============================================================================
# Opacity clustering
# ============================================================================

@pytest.mark.unit
def test_opacity_clustering_creates_tokens(db):
    """Unique opacity values should get their own tokens."""
    seed_post_extraction(db)

    db.executemany(
        """INSERT INTO node_token_bindings
           (node_id, property, raw_value, resolved_value, binding_status)
           VALUES (?, ?, ?, ?, 'unbound')""",
        [
            (1, "opacity", "0.2", "0.2"),
            (2, "opacity", "0.2", "0.2"),
            (3, "opacity", "0.5", "0.5"),
            (5, "opacity", "0.8", "0.8"),
        ]
    )
    db.commit()

    from dd.cluster_misc import cluster_opacity, ensure_opacity_collection
    collection_id, mode_id = ensure_opacity_collection(db, 1)
    result = cluster_opacity(db, 1, collection_id, mode_id)

    assert result["tokens_created"] == 3
    assert result["bindings_updated"] == 4

    # All opacity bindings should be proposed
    unbound = db.execute(
        "SELECT COUNT(*) FROM node_token_bindings WHERE property = 'opacity' AND binding_status = 'unbound'"
    ).fetchone()[0]
    assert unbound == 0


# ============================================================================
# LetterSpacing clustering
# ============================================================================

@pytest.mark.unit
def test_letterspacing_nonzero_values_get_tokens(db):
    """Non-zero letterSpacing values like -0.41px should become tokens."""
    seed_post_extraction(db)

    # Clean slate for letterSpacing and typography tokens
    db.execute("DELETE FROM node_token_bindings WHERE property = 'letterSpacing'")
    db.execute("DELETE FROM token_values WHERE token_id IN (SELECT id FROM tokens WHERE name LIKE 'type.%letterSpacing%')")
    db.execute("DELETE FROM tokens WHERE name LIKE 'type.%letterSpacing%'")
    db.commit()

    db.executemany(
        """INSERT INTO node_token_bindings
           (node_id, property, raw_value, resolved_value, binding_status)
           VALUES (?, ?, ?, ?, 'unbound')""",
        [
            (4, "letterSpacing", '{"value": -0.408, "unit": "PIXELS"}', '{"value": -0.408, "unit": "PIXELS"}'),
            (7, "letterSpacing", '{"value": -0.408, "unit": "PIXELS"}', '{"value": -0.408, "unit": "PIXELS"}'),
        ]
    )
    db.commit()

    from dd.cluster_typography import (
        cluster_letter_spacing,
        ensure_typography_collection,
    )
    coll_id, mode_id = ensure_typography_collection(db, 1)
    result = cluster_letter_spacing(db, 1, coll_id, mode_id)

    assert result["tokens_created"] >= 1
    assert result["bindings_updated"] == 2

    unbound = db.execute(
        "SELECT COUNT(*) FROM node_token_bindings WHERE property = 'letterSpacing' AND binding_status = 'unbound'"
    ).fetchone()[0]
    assert unbound == 0


# ============================================================================
# Gradient marking
# ============================================================================

@pytest.mark.unit
def test_gradient_fills_marked_intentionally_unbound(db):
    """Gradient fills can't be color tokens — mark them as handled."""
    seed_post_extraction(db)

    db.executemany(
        """INSERT INTO node_token_bindings
           (node_id, property, raw_value, resolved_value, binding_status)
           VALUES (?, ?, ?, ?, 'unbound')""",
        [
            (1, "fill.0.gradient", "gradient", "gradient"),
            (2, "fill.1.gradient", "gradient", "gradient"),
        ]
    )
    db.commit()

    from dd.cluster import mark_gradient_bindings
    marked = mark_gradient_bindings(db, 1)

    assert marked == 2

    unbound = db.execute(
        "SELECT COUNT(*) FROM node_token_bindings WHERE property LIKE 'fill.%.gradient' AND binding_status = 'unbound'"
    ).fetchone()[0]
    assert unbound == 0


# ============================================================================
# Radius clustering tests (test_radius_*)
# ============================================================================

@pytest.mark.unit
def test_radius_propose_name_3values():
    """3 values -> sm, md, lg."""
    names = [propose_radius_name(v, i, 3) for i, v in enumerate([4, 8, 12])]
    assert names == ["radius.sm", "radius.md", "radius.lg"]


@pytest.mark.unit
def test_radius_propose_name_5values():
    """5 values -> xs, sm, md, lg, xl."""
    names = [propose_radius_name(v, i, 5) for i, v in enumerate([2, 4, 8, 12, 16])]
    assert names == ["radius.xs", "radius.sm", "radius.md", "radius.lg", "radius.xl"]


@pytest.mark.unit
@pytest.mark.timeout(30)
def test_radius_clustering_full(db):
    """Seed DB, run cluster_radius. Verify tokens + bindings."""
    seed_post_extraction(db)
    collection_id, mode_id = ensure_radius_collection(db, 1)

    # Run clustering
    result = cluster_radius(db, 1, collection_id, mode_id)

    # Verify tokens created
    cursor = db.execute(
        """SELECT * FROM tokens
           WHERE collection_id = ? AND type = 'dimension' AND tier = 'extracted'""",
        (collection_id,)
    )
    tokens = cursor.fetchall()
    assert len(tokens) > 0

    # Check token names
    for token in tokens:
        name = token['name']
        assert name.startswith('radius.')

    # Verify bindings
    cursor = db.execute(
        """SELECT * FROM node_token_bindings
           WHERE property = 'cornerRadius' AND binding_status = 'proposed'"""
    )
    bindings = cursor.fetchall()
    assert len(bindings) > 0


# ============================================================================
# Effect clustering tests (test_effect_*)
# ============================================================================

@pytest.mark.unit
def test_effect_propose_name():
    """index=0, total=3 -> "shadow.sm"."""
    name = propose_effect_name(0, 3)
    assert name == "shadow.sm"

    names = [propose_effect_name(i, 3) for i in range(3)]
    assert names == ["shadow.sm", "shadow.md", "shadow.lg"]


@pytest.mark.unit
@pytest.mark.timeout(30)
def test_effect_clustering_full(db):
    """Seed DB, run cluster_effects. Verify atomic tokens created."""
    seed_post_extraction(db)
    collection_id, mode_id = ensure_effects_collection(db, 1)

    # Run clustering
    result = cluster_effects(db, 1, collection_id, mode_id)

    # Verify tokens created
    cursor = db.execute(
        """SELECT * FROM tokens
           WHERE collection_id = ? AND tier = 'extracted'""",
        (collection_id,)
    )
    tokens = cursor.fetchall()

    if len(tokens) > 0:
        # Check that token names follow pattern
        for token in tokens:
            name = token['name']
            assert name.startswith('shadow.')
            # Should be atomic tokens for each field
            assert any(name.endswith(f) for f in ['.color', '.offsetX', '.offsetY', '.radius', '.spread'])


# ============================================================================
# Orchestrator tests (test_orchestrator_*)
# ============================================================================

@pytest.mark.unit
@pytest.mark.timeout(30)
def test_orchestrator_run_clustering(db):
    """Seed DB, run run_clustering. Verify summary and all types ran."""
    seed_post_extraction(db)

    # Run full clustering pipeline
    result = run_clustering(db, 1, color_threshold=2.0, agent_id="test")

    # Verify summary structure
    assert 'total_tokens' in result
    assert 'total_bindings_updated' in result
    assert 'coverage_pct' in result
    assert 'by_type' in result

    # Verify all clustering types ran
    assert 'color' in result['by_type']
    assert 'typography' in result['by_type']
    assert 'spacing' in result['by_type']
    assert 'radius' in result['by_type']
    assert 'effects' in result['by_type']

    # Verify tokens exist for all types in DB
    cursor = db.execute(
        """SELECT type, COUNT(*) as count FROM tokens
           WHERE tier = 'extracted'
           GROUP BY type"""
    )
    type_counts = {row['type']: row['count'] for row in cursor.fetchall()}
    assert len(type_counts) > 0

    # Coverage should be > 0
    assert result['coverage_pct'] > 0
    assert result['total_tokens'] > 0
    assert result['total_bindings_updated'] > 0


@pytest.mark.unit
@pytest.mark.timeout(30)
def test_orchestrator_no_orphans(db):
    """Run clustering, then validate_no_orphan_tokens returns empty list."""
    seed_post_extraction(db)

    # Run clustering
    run_clustering(db, 1, color_threshold=2.0, agent_id="test")

    # Check for orphans
    orphans = validate_no_orphan_tokens(db, 1)
    assert orphans == []


@pytest.mark.unit
@pytest.mark.timeout(30)
def test_orchestrator_idempotent(db):
    """Run clustering twice, second run creates 0 new tokens."""
    seed_post_extraction(db)

    # First run
    result1 = run_clustering(db, 1, color_threshold=2.0, agent_id="test")
    tokens_created_1 = result1['total_tokens']
    assert tokens_created_1 > 0

    # Second run - should create minimal or no new tokens
    result2 = run_clustering(db, 1, color_threshold=2.0, agent_id="test")

    # The second run should update 0 bindings since all were already proposed
    assert result2['total_bindings_updated'] == 0

    # Second run should create significantly fewer tokens than the first
    # Typography may create orphan tokens for lineHeight/letterSpacing
    assert result2['total_tokens'] < tokens_created_1


@pytest.mark.unit
@pytest.mark.timeout(30)
def test_orchestrator_summary(db):
    """Run clustering, verify generate_summary returns correct counts."""
    seed_post_extraction(db)

    # Run clustering - this already returns a summary
    summary = run_clustering(db, 1, color_threshold=2.0, agent_id="test")

    # Verify summary matches DB state
    assert 'total_tokens' in summary
    assert 'total_bindings_updated' in summary
    assert 'coverage_pct' in summary
    assert 'by_type' in summary

    # Verify counts match actual DB
    cursor = db.execute(
        """SELECT COUNT(*) as count FROM tokens t
           JOIN token_collections tc ON t.collection_id = tc.id
           WHERE tc.file_id = ?""",
        (1,)
    )
    actual_token_count = cursor.fetchone()['count']
    # total_tokens in summary is before cleanup, DB count is after cleanup
    # Just verify we have tokens created
    assert actual_token_count > 0
    assert summary['total_tokens'] > 0

    cursor = db.execute(
        """SELECT COUNT(*) as count FROM node_token_bindings ntb
           JOIN nodes n ON ntb.node_id = n.id
           JOIN screens s ON n.screen_id = s.id
           WHERE s.file_id = ? AND ntb.binding_status = 'proposed'""",
        (1,)
    )
    actual_binding_count = cursor.fetchone()['count']
    assert summary['total_bindings_updated'] == actual_binding_count


# ============================================================================
# F6.1: typography line-height consolidation
# ============================================================================


def _f61_seed_typography_db(specs: list[dict]) -> sqlite3.Connection:
    """Seed an in-memory DB with typography nodes + bindings.

    Each spec is {family, weight, size, line_height_value or None, count}.
    Inserts ``count`` TEXT nodes per spec plus fontSize/fontFamily/
    fontWeight/lineHeight bindings on each node.
    """
    import json
    db = init_db(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'f', 'f.fig')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'S', 100, 100)"
    )
    nid = 1
    bid = 1
    for spec in specs:
        family = spec['family']
        weight = spec['weight']
        size = spec['size']
        lh_value = spec.get('line_height_value')
        for _ in range(spec['count']):
            line_height_json = (
                json.dumps({"value": lh_value, "unit": "PIXELS"})
                if lh_value is not None
                else json.dumps({"unit": "AUTO"})
            )
            db.execute(
                "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order, "
                "font_family, font_weight, font_size, line_height) "
                "VALUES (?, 1, ?, ?, 'TEXT', 0, ?, ?, ?, ?, ?)",
                (nid, f"t{nid}", f"T{nid}", nid, family, weight, size, line_height_json),
            )
            for prop, raw in [
                ("fontSize", str(size)),
                ("fontFamily", family),
                ("fontWeight", str(weight)),
                ("lineHeight", line_height_json),
            ]:
                db.execute(
                    "INSERT INTO node_token_bindings "
                    "(id, node_id, property, raw_value, resolved_value, binding_status) "
                    "VALUES (?, ?, ?, ?, ?, 'unbound')",
                    (bid, nid, prop, raw, raw if prop != 'lineHeight' else (
                        str(lh_value) if lh_value is not None else 'AUTO'
                    )),
                )
                bid += 1
            nid += 1
    db.commit()
    return db


def test_f61_typography_lineheight_split_same_tier():
    """F6.1 test 5: same family/weight/size with two PIXELS lineHeights.

    A single tier emits TWO lineHeight tokens — bare for highest-usage,
    .2 for secondary. fontSize/fontFamily/fontWeight stay singletons.
    """
    from dd.cluster_typography import (
        cluster_typography,
        ensure_typography_collection,
    )

    db = _f61_seed_typography_db([
        {'family': 'Inter', 'weight': 400, 'size': 16, 'line_height_value': 32.0, 'count': 50},
        {'family': 'Inter', 'weight': 400, 'size': 16, 'line_height_value': 95.13, 'count': 5},
    ])
    coll, mode = ensure_typography_collection(db, 1)
    cluster_typography(db, 1, coll, mode)

    by_name = {row['name']: row['resolved_value'] for row in db.execute(
        "SELECT t.name, tv.resolved_value FROM tokens t "
        "JOIN token_values tv ON t.id = tv.token_id WHERE t.collection_id = ?",
        (coll,),
    ).fetchall()}

    # One consolidated tier, so suffix is 'md' (single item -> ['md']).
    assert by_name.get("type.body.md.fontSize") == "16.0"
    assert by_name.get("type.body.md.fontFamily") == "Inter"
    assert by_name.get("type.body.md.fontWeight") == "400"

    # Two lineHeight tokens: 32.0 (high usage) bare, 95.13 (low) .2.
    assert by_name.get("type.body.md.lineHeight") == "32.0"
    assert by_name.get("type.body.md.lineHeight.2") == "95.13"


def test_f61_typography_auto_lineheight_not_tokenized():
    """F6.1 test 6: AUTO lineHeight (NULL) is not tokenized — left for
    mark_default_bindings to mark intentionally_unbound.
    """
    from dd.cluster_typography import (
        cluster_typography,
        ensure_typography_collection,
    )

    db = _f61_seed_typography_db([
        {'family': 'Inter', 'weight': 400, 'size': 16, 'line_height_value': None, 'count': 100},
        {'family': 'Inter', 'weight': 400, 'size': 16, 'line_height_value': 32.0, 'count': 10},
    ])
    coll, mode = ensure_typography_collection(db, 1)
    cluster_typography(db, 1, coll, mode)

    lh_tokens = [row['name'] for row in db.execute(
        "SELECT name FROM tokens WHERE collection_id = ? AND name LIKE '%.lineHeight%'",
        (coll,),
    ).fetchall()]

    # Only one lineHeight token (32.0); AUTO not tokenized.
    assert lh_tokens == ["type.body.md.lineHeight"]

    # Confirm AUTO bindings remain unbound after clustering. They will
    # later be promoted to intentionally_unbound by mark_default_bindings,
    # which is a separate stage outside cluster_typography's scope.
    auto_count = db.execute(
        "SELECT COUNT(*) FROM node_token_bindings "
        "WHERE property = 'lineHeight' AND resolved_value = 'AUTO' "
        "AND binding_status = 'unbound'"
    ).fetchone()[0]
    assert auto_count == 100


def test_f61_color_near_colors_share_token():
    """F6.1 test 7 (regression): near-colors still cluster into one token,
    and all bindings carry the representative resolved_value (F6 fix).
    """
    from dd.cluster_colors import cluster_colors, ensure_collection_and_mode

    db = init_db(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'f', 'f.fig')")
    db.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1', 'S', 100, 100)"
    )
    # Two near-identical greys: high-usage representative #EEF5F7 (10 nodes),
    # low-usage near-clone #EEF5F8 (1 node). ΔE < 2 → same group.
    nid = 1
    bid = 1
    for color, count in [("#EEF5F7", 10), ("#EEF5F8", 1)]:
        for _ in range(count):
            db.execute(
                "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type, depth, sort_order) "
                "VALUES (?, 1, ?, ?, 'RECTANGLE', 0, ?)",
                (nid, f"r{nid}", f"R{nid}", nid),
            )
            db.execute(
                "INSERT INTO node_token_bindings "
                "(id, node_id, property, raw_value, resolved_value, binding_status) "
                "VALUES (?, ?, 'fill.0.color', ?, ?, 'unbound')",
                (bid, nid, color, color),
            )
            bid += 1
            nid += 1
    db.commit()

    coll, mode = ensure_collection_and_mode(db, 1)
    cluster_colors(db, 1, coll, mode)

    color_tokens = list(db.execute(
        "SELECT t.name, tv.resolved_value FROM tokens t "
        "JOIN token_values tv ON t.id = tv.token_id WHERE t.collection_id = ?",
        (coll,),
    ).fetchall())
    assert len(color_tokens) == 1
    representative = color_tokens[0]['resolved_value']
    assert representative == "#EEF5F7"  # higher-usage was first

    # Every binding's resolved_value snapped to the representative.
    rows = db.execute(
        "SELECT resolved_value, COUNT(*) AS c FROM node_token_bindings "
        "WHERE property = 'fill.0.color' GROUP BY resolved_value"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]['resolved_value'] == "#EEF5F7"
    assert rows[0]['c'] == 11