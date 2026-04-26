"""P3b (Phase E C2 fix) — orchestrator wiring for cluster_stroke_weight
and cluster_paragraph_spacing.

Phase E §2 found 6093 unbound `strokeWeight=1.0` bindings (76% of all
unbound) on Nouns. Sonnet's analysis confirmed: the clusterer
function exists at `dd/cluster_misc.py:948` (commit 45f6b2d) but
was never imported by `dd/cluster.py`. Same for
`cluster_paragraph_spacing`. P2's orphan detector flagged both.

P3b wires:
- new `ensure_stroke_weight_collection` helper in `cluster_misc.py`
- imports + dispatch in `dd/cluster.py` (step 7 strokeWeight after
  opacity; step 2c paragraphSpacing under typography collection,
  matching the cluster_letter_spacing pattern)
- `paragraphSpacing=0` added to `mark_default_bindings` (Codex P3b
  guardrail: the simple-dimension clusterer skips numeric zero, so
  default paragraphSpacing would otherwise stay as a coverage false
  negative)

This file is the orchestrator-level regression test Codex asked for:
seed strokeWeight + paragraphSpacing bindings, run `run_clustering`,
assert new tokens are proposed and defaults are marked.

If P3b regresses (e.g., someone removes the import from dd/cluster.py),
these tests will fail. P2's `test_p2_orphan_detector` provides the
complementary "is the function still wired?" assertion at the static-
analysis layer.
"""

from __future__ import annotations

import pytest

from dd.cluster import mark_default_bindings, run_clustering


@pytest.fixture
def stroke_weight_db(temp_db):
    """Seed temp_db with stroke-weight + paragraph-spacing fixtures.

    Several distinct stroke widths so the clusterer has something to
    propose. paragraphSpacing has both 0 (default) and non-zero
    values to exercise both the cluster path and the
    intentionally-unbound default-marking path.
    """
    conn = temp_db
    conn.execute(
        "INSERT INTO files (id, file_key, name) VALUES (1, 'p3b_test', 'p3b.fig')"
    )
    conn.execute(
        "INSERT INTO screens (id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, '100:1', 'Screen 1', 375, 812)"
    )
    # Several nodes so the binding count is meaningful
    for i in range(1, 11):
        conn.execute(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, node_type) "
            "VALUES (?, 1, ?, ?, 'RECTANGLE')",
            (i, f"100:{i+1}", f"Rect{i}"),
        )

    # 7 nodes with strokeWeight=1.0, 2 with strokeWeight=2.0, 1 with 0.5
    for i in range(1, 8):
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, 'strokeWeight', '1.0', '1.0', 'unbound')""",
            (i,),
        )
    for i in range(8, 10):
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, 'strokeWeight', '2.0', '2.0', 'unbound')""",
            (i,),
        )
    conn.execute(
        """INSERT INTO node_token_bindings
           (node_id, property, raw_value, resolved_value, binding_status)
           VALUES (10, 'strokeWeight', '0.5', '0.5', 'unbound')"""
    )

    # 5 nodes with paragraphSpacing=0 (Figma default — should be marked
    # intentionally_unbound), 3 with paragraphSpacing=8 (a real design
    # choice — should cluster).
    for i in range(1, 6):
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, 'paragraphSpacing', '0', '0', 'unbound')""",
            (i,),
        )
    for i in range(6, 9):
        conn.execute(
            """INSERT INTO node_token_bindings
               (node_id, property, raw_value, resolved_value, binding_status)
               VALUES (?, 'paragraphSpacing', '8', '8', 'unbound')""",
            (i,),
        )

    conn.commit()
    yield conn


class TestStrokeWeightClusters:
    def test_run_clustering_proposes_stroke_weight_tokens(self, stroke_weight_db):
        """The orchestrator should call cluster_stroke_weight and produce
        tokens for the distinct values in the corpus (1.0, 2.0, 0.5)."""
        result = run_clustering(stroke_weight_db, 1)
        # Summary's by_type breakdown carries per-axis token counts.
        # Key is 'stroke_weight' (matching results_by_type key set in
        # the orchestrator).
        sw_result = result.get("by_type", {}).get("stroke_weight", {})
        assert sw_result.get("tokens", 0) > 0, (
            f"P3b: cluster_stroke_weight should propose tokens for "
            f"distinct stroke values. Got: {sw_result!r}. Full "
            f"summary keys: {sorted(result.keys())}; by_type keys: "
            f"{sorted(result.get('by_type', {}).keys())}"
        )

    def test_stroke_weight_collection_created(self, stroke_weight_db):
        """The new 'Stroke Weight' collection should exist in
        token_collections after run_clustering."""
        run_clustering(stroke_weight_db, 1)
        cursor = stroke_weight_db.execute(
            "SELECT id FROM token_collections WHERE file_id = 1 AND name = 'Stroke Weight'"
        )
        row = cursor.fetchone()
        assert row is not None, (
            "P3b: ensure_stroke_weight_collection must create the "
            "'Stroke Weight' collection. Not found."
        )

    def test_stroke_weight_bindings_get_proposed(self, stroke_weight_db):
        """After clustering, the strokeWeight bindings should be
        'proposed' (the cluster proposes; user `accept-all` flips to
        'bound'). The headline P3b outcome (was: 6093 unbound on Nouns)
        is that strokeWeight bindings move OUT of 'unbound' status —
        either proposed or intentionally_unbound is acceptable."""
        run_clustering(stroke_weight_db, 1)
        cursor = stroke_weight_db.execute(
            """SELECT binding_status, COUNT(*) FROM node_token_bindings
               WHERE property = 'strokeWeight'
               GROUP BY binding_status"""
        )
        statuses = dict(cursor.fetchall())
        unbound = statuses.get("unbound", 0)
        proposed_or_bound = (
            statuses.get("proposed", 0)
            + statuses.get("bound", 0)
            + statuses.get("intentionally_unbound", 0)
        )
        assert proposed_or_bound > 0, (
            f"P3b: strokeWeight bindings should be proposed (or bound, "
            f"or intentionally_unbound) after clustering. Got status "
            f"distribution: {statuses}"
        )
        assert unbound < 10, (
            f"P3b: strokeWeight bindings should not all stay unbound. "
            f"Got status distribution: {statuses}"
        )


class TestParagraphSpacingClusters:
    def test_run_clustering_proposes_paragraph_spacing_tokens(
        self, stroke_weight_db,
    ):
        """The orchestrator should call cluster_paragraph_spacing
        for non-zero paragraph spacings (8 in the fixture)."""
        result = run_clustering(stroke_weight_db, 1)
        # cluster_paragraph_spacing's tokens get merged into the
        # typography results (it shares the typography collection).
        # Check that at least one paragraphSpacing token was created
        # by looking at the tokens table.
        cursor = stroke_weight_db.execute(
            """SELECT COUNT(*) FROM tokens t
               JOIN token_collections tc ON t.collection_id = tc.id
               WHERE tc.file_id = 1
                 AND t.name LIKE 'paragraphSpacing.%'"""
        )
        count = cursor.fetchone()[0]
        assert count > 0, (
            f"P3b: cluster_paragraph_spacing should produce at least "
            f"one paragraphSpacing.* token. Got count={count}. "
            f"Summary: {result!r}"
        )


class TestMarkDefaultBindingsHandlesParagraphSpacingZero:
    def test_paragraph_spacing_zero_marked_intentionally_unbound(
        self, stroke_weight_db,
    ):
        """Codex P3b guardrail (c): `_cluster_simple_dimension` skips
        numeric zero in its census, so default paragraphSpacing=0
        would stay unbound. mark_default_bindings now covers it."""
        # Run mark_default_bindings directly (no need for full
        # orchestrator).
        marked = mark_default_bindings(stroke_weight_db, 1)
        # 5 paragraphSpacing=0 bindings should now be intentionally_unbound.
        cursor = stroke_weight_db.execute(
            """SELECT binding_status, COUNT(*) FROM node_token_bindings
               WHERE property = 'paragraphSpacing'
                 AND CAST(resolved_value AS REAL) = 0
               GROUP BY binding_status"""
        )
        statuses = dict(cursor.fetchall())
        assert statuses.get("intentionally_unbound", 0) == 5, (
            f"P3b: paragraphSpacing=0 (Figma default) should be marked "
            f"intentionally_unbound. Got: {statuses}. mark_default "
            f"returned {marked}."
        )

    def test_paragraph_spacing_nonzero_NOT_marked_intentionally_unbound(
        self, stroke_weight_db,
    ):
        """Defensive: only the 0 values should be marked, not the
        real 8-value bindings."""
        mark_default_bindings(stroke_weight_db, 1)
        cursor = stroke_weight_db.execute(
            """SELECT binding_status FROM node_token_bindings
               WHERE property = 'paragraphSpacing'
                 AND CAST(resolved_value AS REAL) = 8"""
        )
        rows = cursor.fetchall()
        for row in rows:
            assert row[0] != "intentionally_unbound", (
                "P3b: paragraphSpacing=8 (real design value) should "
                "NOT be marked intentionally_unbound. The default-"
                "marker is too aggressive."
            )
