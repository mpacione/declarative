"""P5b (Phase E Pattern 3 fix) — cluster_effects occurrence-key
binding.

Phase E §2 found 7 binding_token_consistency validator warnings on
Nouns. P3c cleared 4 (cluster_letter_spacing). P5a cleared 2 more
(cluster_spacing). The 7th is `shadow.lg.radius`: bindings 8872 and
8886 carry `8.0` while the token writes `1.0` — a multi-shadow
attribution bug.

Sonnet's audit (`audit/20260425-1930-phaseE-nouns/triage/pattern3-
cluster-rounding/sonnet-analysis.md`) traced it to
`dd/cluster_misc.py:586-631`: the binding-UPDATE loop iterates
`composite['node_ids']` and queries by `property LIKE 'effect%'`.
When a node has TWO shadows (effect.0 + effect.1), the loop
processes each composite in turn and rewrites EVERY
`effect.*.{field}` binding for that node — so the last composite
processed wins, regardless of which effect_idx originally generated
each binding.

Codex Phase E review (2026-04-25, gpt-5.5):
"Use eid+effect_idx as the primary key, with value checks as a
guard. Carry occurrences as effect_refs: [(node_id, effect_idx)].
Update exact properties: WHERE node_id = ? AND property = ?
with property = f'effect.{effect_idx}.{field}'."

The fix: `group_effects_by_composite` now also carries
`effect_refs: list[(node_id, effect_idx)]`. The binding UPDATE step
uses those tuples to target exact `effect.{idx}.{field}` rows.

Codex also caught a dead branch:
``hasattr(composite, 'merged_node_ids')`` was always False because
``composite`` is a dict, not an object. The reduced-confidence path
for color-merged composites never ran. Fixed by using dict-key
access via a precomputed `merged_pairs` set.

These tests pin the post-P5b behavior:
1. Multi-shadow node: each effect_idx's bindings attribute to its
   own composite's tokens (the headline fix).
2. Single-shadow node: still works (no regression on the common case).
3. Multiple nodes with mixed effect_idx counts: each binding lands
   on its corresponding shadow's token.
4. Validator (post-cluster) sees parity for shadow.* tokens.
"""

from __future__ import annotations

import pytest

from dd.cluster_misc import (
    cluster_effects,
    ensure_effects_collection,
    group_effects_by_composite,
)


def _seed_node_with_effect(
    conn,
    node_id: int,
    effect_idx: int,
    color: str,
    radius: str,
    offset_x: str = "0",
    offset_y: str = "0",
    spread: str = "0",
) -> None:
    """Insert one shadow's worth of bindings for a node (5 fields)."""
    fields = {
        "color": color,
        "radius": radius,
        "offsetX": offset_x,
        "offsetY": offset_y,
        "spread": spread,
    }
    for field, value in fields.items():
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, ?, ?, ?, 'unbound')""",
            (node_id, f"effect.{effect_idx}.{field}", value, value),
        )


@pytest.fixture
def multi_shadow_db(temp_db):
    """Seed two nodes — each carrying TWO shadows with different
    geometry. Pre-P5b this triggered the cross-attribution bug."""
    conn = temp_db
    conn.execute(
        "INSERT INTO files (id, file_key, name) VALUES (1, 'p5b_test', 'p5b.fig')"
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, '100:1', 'Screen 1', 375, 812)"
    )
    for i in range(1, 5):
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
            "VALUES (?, 1, ?, ?, 'FRAME')",
            (i, f"100:{i+1}", f"Node{i}"),
        )

    # Node 1 — TWO shadows: small (radius=1) at effect.0, large (radius=8) at effect.1
    _seed_node_with_effect(conn, 1, 0, "#000000", "1")
    _seed_node_with_effect(conn, 1, 1, "#000000", "8")

    # Node 2 — same pattern as node 1 (two shadows: 1 + 8). Together
    # with node 1 these give the small-shadow composite usage_count=2
    # and the large-shadow composite usage_count=2.
    _seed_node_with_effect(conn, 2, 0, "#000000", "1")
    _seed_node_with_effect(conn, 2, 1, "#000000", "8")

    # Node 3 — single shadow (radius=4) at effect.0. Different
    # geometry → its own composite.
    _seed_node_with_effect(conn, 3, 0, "#FF0000", "4")

    # Node 4 — single shadow matching node 1's small shadow
    # (radius=1, color=black). Bumps small composite to usage_count=3.
    _seed_node_with_effect(conn, 4, 0, "#000000", "1")

    conn.commit()
    yield conn


class TestEffectRefsCarriedThroughComposite:
    """The structural change at the composite-grouping step:
    `group_effects_by_composite` now carries
    `effect_refs: list[(node_id, effect_idx)]` so the binding UPDATE
    can target exact rows."""

    def test_composites_carry_effect_refs(self, multi_shadow_db):
        composites = group_effects_by_composite(multi_shadow_db, file_id=1)
        assert composites, "should have at least one composite"
        for comp in composites:
            assert "effect_refs" in comp, (
                f"P5b: every composite must carry effect_refs. Missing "
                f"in: {comp!r}"
            )
            assert isinstance(comp["effect_refs"], list)
            # Each entry is (node_id, effect_idx_str)
            for ref in comp["effect_refs"]:
                assert isinstance(ref, tuple)
                assert len(ref) == 2

    def test_small_shadow_composite_only_carries_effect_zero_refs(
        self, multi_shadow_db,
    ):
        """The headline P5b invariant: the small-shadow composite
        (radius=1) only carries effect.0 occurrences from nodes 1, 2,
        and 4. The large-shadow composite carries only effect.1 from
        nodes 1 + 2."""
        composites = group_effects_by_composite(multi_shadow_db, file_id=1)
        small = [c for c in composites if c["radius"] == "1"]
        large = [c for c in composites if c["radius"] == "8"]
        assert len(small) == 1
        assert len(large) == 1

        small_refs = set(small[0]["effect_refs"])
        assert small_refs == {
            (1, "0"), (2, "0"), (4, "0"),
        }, (
            f"P5b: small-shadow composite (radius=1) should carry "
            f"effect.0 from nodes 1, 2, 4. Got: {sorted(small_refs)}"
        )

        large_refs = set(large[0]["effect_refs"])
        assert large_refs == {
            (1, "1"), (2, "1"),
        }, (
            f"P5b: large-shadow composite (radius=8) should carry "
            f"effect.1 from nodes 1, 2. Got: {sorted(large_refs)}"
        )


class TestMultiShadowBindingAttribution:
    """The end-to-end fix: after `cluster_effects` runs, each
    `effect.{idx}.radius` binding points at the correct shadow token,
    not the last one processed."""

    def test_each_effect_idx_radius_binds_to_its_own_token(
        self, multi_shadow_db,
    ):
        collection_id, mode_id = ensure_effects_collection(multi_shadow_db, file_id=1)
        cluster_effects(multi_shadow_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

        # Pull bindings + their token's resolved_value.
        cursor = multi_shadow_db.execute(
            """SELECT ntb.node_id, ntb.property, ntb.resolved_value AS bind_val,
                      tv.resolved_value AS token_val, t.name AS token_name
               FROM node_token_bindings ntb
               JOIN tokens t ON ntb.token_id = t.id
               JOIN token_values tv ON tv.token_id = t.id
               WHERE ntb.binding_status = 'proposed'
                 AND ntb.property LIKE 'effect.%.radius'
               ORDER BY ntb.node_id, ntb.property"""
        )
        rows = list(cursor.fetchall())
        # 6 radius bindings total: node 1 (2 shadows) + node 2 (2) +
        # node 3 (1) + node 4 (1).
        assert len(rows) == 6

        for row in rows:
            # P5b headline: every radius binding's value (bind_val)
            # equals its token's value (token_val). Pre-P5b: node 1
            # effect.0 carried bind_val=1, but if effect.1 was
            # processed first, the token bound was the radius=8
            # token, so token_val would be 8. POST-P5b that mismatch
            # cannot happen.
            assert row["bind_val"] == row["token_val"], (
                f"P5b: effect.{row['property']} binding value "
                f"({row['bind_val']}) must equal its token value "
                f"({row['token_val']}). Mismatch on node {row['node_id']} "
                f"-> {row['token_name']}."
            )

    def test_no_cross_attribution_within_same_node(self, multi_shadow_db):
        """Tighter form of the above — for node 1 specifically (which
        has BOTH shadows), effect.0.radius must point at the small
        token and effect.1.radius at the large token."""
        collection_id, mode_id = ensure_effects_collection(multi_shadow_db, file_id=1)
        cluster_effects(multi_shadow_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

        cursor = multi_shadow_db.execute(
            """SELECT property, resolved_value
               FROM node_token_bindings
               WHERE node_id = 1
                 AND property LIKE 'effect.%.radius'
                 AND binding_status = 'proposed'
               ORDER BY property"""
        )
        rows = list(cursor.fetchall())
        # Two rows: effect.0.radius and effect.1.radius
        bindings = {r["property"]: r["resolved_value"] for r in rows}
        assert bindings.get("effect.0.radius") == "1", (
            f"P5b: node 1 effect.0.radius (small shadow) should still "
            f"resolve to '1', not the large shadow's '8'. "
            f"Got: {bindings}"
        )
        assert bindings.get("effect.1.radius") == "8", (
            f"P5b: node 1 effect.1.radius (large shadow) should still "
            f"resolve to '8', not the small shadow's '1'. "
            f"Got: {bindings}"
        )


class TestSingleShadowStillWorks:
    """Defensive: P5b's change must not regress the common case where
    each node has exactly one shadow."""

    def test_single_shadow_node_binds_correctly(self, multi_shadow_db):
        collection_id, mode_id = ensure_effects_collection(multi_shadow_db, file_id=1)
        cluster_effects(multi_shadow_db, file_id=1, collection_id=collection_id, mode_id=mode_id)

        # Node 3 has a unique shadow (radius=4, color=#FF0000). Its
        # bindings should point at a token whose resolved_value
        # matches.
        cursor = multi_shadow_db.execute(
            """SELECT ntb.property, ntb.resolved_value AS bind_val,
                      tv.resolved_value AS token_val
               FROM node_token_bindings ntb
               JOIN tokens t ON ntb.token_id = t.id
               JOIN token_values tv ON tv.token_id = t.id
               WHERE ntb.node_id = 3
                 AND ntb.binding_status = 'proposed'
                 AND ntb.property LIKE 'effect.%'"""
        )
        rows = list(cursor.fetchall())
        assert len(rows) == 5  # color+radius+offsetX+offsetY+spread
        for row in rows:
            assert row["bind_val"] == row["token_val"], (
                f"P5b: node 3 (single shadow) {row['property']} "
                f"should match its token. Got bind={row['bind_val']} "
                f"token={row['token_val']}."
            )


class TestEffectClusteringPreservesSemantics:
    """Defensive — the fix must not delete or insert bindings."""

    def test_binding_count_unchanged(self, multi_shadow_db):
        cursor = multi_shadow_db.execute(
            "SELECT COUNT(*) FROM node_token_bindings WHERE property LIKE 'effect%'"
        )
        pre = cursor.fetchone()[0]
        collection_id, mode_id = ensure_effects_collection(multi_shadow_db, file_id=1)
        cluster_effects(multi_shadow_db, file_id=1, collection_id=collection_id, mode_id=mode_id)
        cursor = multi_shadow_db.execute(
            "SELECT COUNT(*) FROM node_token_bindings WHERE property LIKE 'effect%'"
        )
        post = cursor.fetchone()[0]
        assert pre == post, f"effect-binding count drifted: pre={pre} post={post}"
