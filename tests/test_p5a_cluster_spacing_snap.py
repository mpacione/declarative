"""P5a (Phase E Pattern 3 fix) — cluster_spacing snap-on-UPDATE.

Phase E §2 found 7 `binding_token_consistency` validator warnings on
Nouns. P3c (cluster_letter_spacing) cleared 4 of them. Two more come
from `cluster_spacing`: the clusterer rounds floats to integers when
naming and creating tokens (`14.5697... → 15`), but the binding's
`resolved_value` keeps the sub-pixel original. The downstream
validator's `_normalize_numeric` only collapses values within 0.001
of an integer; sub-pixel noise like `14.5697...` falls outside that
window, so `space.10` (×24) and `space.md` (×6) light up post-cluster.

Sonnet's audit (`audit/20260425-1930-phaseE-nouns/triage/pattern3-
cluster-rounding/sonnet-analysis.md`) recommended the cheapest fix:
"Port `cluster_colors:289-295` snap-on-UPDATE into
`cluster_letter_spacing` and `cluster_spacing`. One-line diff each."

Codex's Phase E review (2026-04-25, gpt-5.5) confirmed and added: this
is the canonical contract — every numeric clusterer must canonicalize
the binding's `resolved_value` to match the token's. The contract
will be codified in P5c via `dd/cluster_axis.py:AxisSpec`.

These tests pin the snap-on-UPDATE behavior end-to-end:
1. After clustering, every bound binding's `resolved_value` equals
   the canonical integer string the token writes.
2. Sub-pixel float noise (`14.5697...`, `3.6424...`) is collapsed.
3. Already-integer values (`16`, `24`) round-trip unchanged.
4. The validator (post-cluster) sees parity and emits zero
   `binding_token_consistency` warnings for spacing properties.
"""

from __future__ import annotations

import pytest

from dd.cluster_spacing import cluster_spacing


@pytest.fixture
def spacing_db(temp_db):
    """Seed temp_db with a mix of clean integer + sub-pixel float
    spacing values across multiple spacing properties."""
    conn = temp_db
    conn.execute(
        "INSERT INTO files (id, file_key, name) VALUES (1, 'p5a_test', 'p5a.fig')"
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, '100:1', 'Screen 1', 375, 812)"
    )
    # Create a spacing token collection (cluster_spacing expects one)
    cursor = conn.execute(
        "INSERT INTO token_collections (file_id, name) VALUES (1, 'Spacing')"
    )
    collection_id = cursor.lastrowid
    cursor = conn.execute(
        "INSERT INTO token_modes (collection_id, name) VALUES (?, 'Default')",
        (collection_id,),
    )
    mode_id = cursor.lastrowid

    # Several nodes
    for i in range(1, 16):
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
            "VALUES (?, 1, ?, ?, 'FRAME')",
            (i, f"100:{i+1}", f"Node{i}"),
        )

    # 5 nodes with padding=14.5697... (sub-pixel noise that rounds to 15)
    for i in range(1, 6):
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, 'padding.top', '14.569705963134766', '14.569705963134766', 'unbound')""",
            (i,),
        )

    # 3 nodes with padding=3.6424... (rounds to 4)
    for i in range(6, 9):
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, 'itemSpacing', '3.6424...', '3.642407417297363', 'unbound')""",
            (i,),
        )

    # 4 nodes with itemSpacing=16 (clean integer, no rounding needed)
    for i in range(9, 13):
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, 'itemSpacing', '16', '16.0', 'unbound')""",
            (i,),
        )

    # 2 nodes with padding.left=24 (clean integer)
    for i in range(13, 15):
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, 'padding.left', '24', '24.0', 'unbound')""",
            (i,),
        )

    conn.commit()
    yield conn, collection_id, mode_id


class TestSpacingSnapOnUpdate:
    """The headline P5a contract: every bound binding's
    resolved_value equals the canonical integer string the token
    wrote, even if the original was sub-pixel float noise."""

    def test_subpixel_padding_snapped_to_integer(self, spacing_db):
        conn, collection_id, mode_id = spacing_db
        result = cluster_spacing(conn, file_id=1, collection_id=collection_id, mode_id=mode_id)
        assert result["tokens_created"] > 0
        assert result["bindings_updated"] >= 5

        # All padding.top bindings (originally 14.5697...) should now
        # carry the canonical "15" string.
        cursor = conn.execute(
            """SELECT resolved_value FROM node_token_bindings
               WHERE property = 'padding.top'
                 AND binding_status = 'proposed'"""
        )
        values = [row[0] for row in cursor.fetchall()]
        assert len(values) == 5
        assert all(v == "15" for v in values), (
            f"P5a: sub-pixel padding (14.5697...) must snap to canonical "
            f"'15' on UPDATE. Got: {values}"
        )

    def test_subpixel_itemspacing_snapped_to_integer(self, spacing_db):
        conn, collection_id, mode_id = spacing_db
        cluster_spacing(conn, file_id=1, collection_id=collection_id, mode_id=mode_id)
        cursor = conn.execute(
            """SELECT resolved_value FROM node_token_bindings
               WHERE property = 'itemSpacing'
                 AND binding_status = 'proposed'
                 AND resolved_value IN ('4', '16')"""
        )
        values = [row[0] for row in cursor.fetchall()]
        # 3 bindings of "3.6424..." should be "4"; 4 of "16.0" should be "16"
        assert values.count("4") == 3
        assert values.count("16") == 4

    def test_clean_integers_roundtrip_unchanged_value(self, spacing_db):
        """Already-integer values must also be canonicalized to the
        same form the token writes (i.e. `'16'` not `'16.0'`)."""
        conn, collection_id, mode_id = spacing_db
        cluster_spacing(conn, file_id=1, collection_id=collection_id, mode_id=mode_id)
        cursor = conn.execute(
            """SELECT resolved_value FROM node_token_bindings
               WHERE property = 'padding.left'
                 AND binding_status = 'proposed'"""
        )
        values = [row[0] for row in cursor.fetchall()]
        # Both 24.0 originals should snap to canonical "24"
        assert all(v == "24" for v in values), (
            f"P5a: clean integer (24.0) must snap to canonical '24' "
            f"to match the token's resolved_value. Got: {values}"
        )


class TestTokenAndBindingValueParity:
    """Codex review: structural test should prove behavior, not just
    metadata. After clustering, every bound binding's resolved_value
    must equal its token's resolved_value — the cluster_colors
    snap-on-UPDATE invariant."""

    def test_every_bound_binding_matches_its_token_value(self, spacing_db):
        conn, collection_id, mode_id = spacing_db
        cluster_spacing(conn, file_id=1, collection_id=collection_id, mode_id=mode_id)
        # JOIN bindings to tokens via token_id and the token's resolved
        # value to the binding's resolved value.
        cursor = conn.execute(
            """SELECT ntb.resolved_value AS binding_val,
                      tv.resolved_value AS token_val,
                      ntb.property
               FROM node_token_bindings ntb
               JOIN tokens t ON ntb.token_id = t.id
               JOIN token_values tv ON tv.token_id = t.id
               WHERE ntb.binding_status = 'proposed'
                 AND ntb.property IN
                   ('padding.top','padding.right','padding.bottom','padding.left',
                    'itemSpacing','counterAxisSpacing')"""
        )
        rows = cursor.fetchall()
        assert rows, "should have at least one bound spacing binding"
        mismatches = [
            (r["property"], r["binding_val"], r["token_val"])
            for r in rows
            if r["binding_val"] != r["token_val"]
        ]
        assert not mismatches, (
            f"P5a contract: every bound binding's resolved_value must "
            f"equal its token's resolved_value. Mismatches: {mismatches!r}"
        )


class TestSpacingClusteringPreservesSemantics:
    """Defensive: snap-on-UPDATE should not silently change the
    binding count, only the value column."""

    def test_binding_count_unchanged_by_snap(self, spacing_db):
        conn, collection_id, mode_id = spacing_db
        cursor = conn.execute(
            "SELECT COUNT(*) FROM node_token_bindings"
        )
        pre = cursor.fetchone()[0]
        cluster_spacing(conn, file_id=1, collection_id=collection_id, mode_id=mode_id)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM node_token_bindings"
        )
        post = cursor.fetchone()[0]
        assert pre == post, (
            f"P5a: snap-on-UPDATE must not delete or insert bindings, "
            f"only rewrite resolved_value. pre={pre}, post={post}"
        )
