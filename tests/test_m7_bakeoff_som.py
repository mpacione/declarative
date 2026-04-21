"""Tests for the M7 SoM bake-off dedup wrapper.

The bake-off adds a thin layer on top of ``dd.classify_dedup`` that
takes the rep rows produced by ``_fetch_reps`` and collapses them into
representatives + propagation lists. This avoids classifying a given
copy-pasted card 10x when it appears on 10 iPad-variant screens.

The dedup logic itself is tested in ``test_classify_dedup.py``; these
tests cover only the bake-off's wrapper that builds candidate dicts
from rep rows and returns ``(representatives, members_by_rep_sci)``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.m7_bakeoff_som import _compute_group_reps


class _FakeConn:
    """Minimal sqlite-ish stand-in that answers the one query the
    helper runs (child-type distribution per node_id).
    """

    def __init__(self, child_dist_by_node: dict[int, dict[str, int]]):
        self._dist = child_dist_by_node

    def execute(self, sql, params):
        # Only the child-type-dist query hits here — it takes a single
        # node_id and returns [(node_type, count), ...].
        node_id = params[0]
        pairs = list(self._dist.get(node_id, {}).items())
        return SimpleNamespace(fetchall=lambda: pairs)


def _mk_rep(*, sci_id, screen_id, node_id, name="Frame 413",
            parent_type="header", width=100.0, height=100.0):
    return {
        "sci_id": sci_id,
        "screen_id": screen_id,
        "node_id": node_id,
        "name": name,
        "node_type": "FRAME",
        "parent_classified_as": parent_type,
        "width": width,
        "height": height,
        "llm_type": None,
        "vision_ps_type": None,
        "vision_cs_type": None,
    }


class TestComputeGroupReps:
    def test_identical_reps_across_screens_collapse(self):
        """Two reps on different screens with same name + structure
        collapse to one representative group.
        """
        r1 = _mk_rep(sci_id=1, screen_id=276, node_id=100)
        r2 = _mk_rep(sci_id=2, screen_id=277, node_id=200)
        conn = _FakeConn({100: {}, 200: {}})
        reps, members = _compute_group_reps([r1, r2], conn)
        assert len(reps) == 1
        assert reps[0]["sci_id"] == 1  # first-seen wins
        assert set(members[1]) == {1, 2}

    def test_different_names_stay_distinct(self):
        r1 = _mk_rep(sci_id=1, screen_id=276, node_id=100, name="Alpha")
        r2 = _mk_rep(sci_id=2, screen_id=276, node_id=200, name="Beta")
        conn = _FakeConn({100: {}, 200: {}})
        reps, members = _compute_group_reps([r1, r2], conn)
        assert len(reps) == 2

    def test_generic_frame_numbers_collapse(self):
        """'Frame 292' and 'Frame 293' with same structure are
        auto-generated names — must dedup.
        """
        r1 = _mk_rep(sci_id=1, screen_id=276, node_id=100, name="Frame 292")
        r2 = _mk_rep(sci_id=2, screen_id=277, node_id=200, name="Frame 293")
        conn = _FakeConn({100: {}, 200: {}})
        reps, _ = _compute_group_reps([r1, r2], conn)
        assert len(reps) == 1

    def test_different_child_dist_stays_distinct(self):
        r1 = _mk_rep(sci_id=1, screen_id=276, node_id=100)
        r2 = _mk_rep(sci_id=2, screen_id=277, node_id=200)
        conn = _FakeConn({100: {"TEXT": 1}, 200: {"TEXT": 2}})
        reps, _ = _compute_group_reps([r1, r2], conn)
        assert len(reps) == 2

    def test_singleton_rep_has_self_as_only_member(self):
        r1 = _mk_rep(sci_id=1, screen_id=276, node_id=100)
        conn = _FakeConn({100: {}})
        reps, members = _compute_group_reps([r1], conn)
        assert len(reps) == 1
        assert members[1] == [1]

    def test_first_seen_rep_preserved_as_representative(self):
        """When multiple reps share a signature, the first in the
        input order is the representative — matches the ordering
        convention of classify_dedup.group_candidates.
        """
        r1 = _mk_rep(sci_id=10, screen_id=276, node_id=100)
        r2 = _mk_rep(sci_id=20, screen_id=277, node_id=200)
        r3 = _mk_rep(sci_id=30, screen_id=278, node_id=300)
        conn = _FakeConn({100: {}, 200: {}, 300: {}})
        reps, members = _compute_group_reps([r1, r2, r3], conn)
        assert len(reps) == 1
        assert reps[0]["sci_id"] == 10
        assert members[10] == [10, 20, 30]
