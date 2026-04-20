"""Tests for dedup by structural signature (classifier v2 step 1).

The dedup key groups nodes that are structurally identical so they
share a classification verdict instead of being classified
individually. Saves 5-8x on API calls on the full corpus per the
user's review data (674 flagged rows collapsed to 218 patterns on
post-classification signature alone).
"""

from __future__ import annotations

import pytest

from dd.classify_dedup import dedup_key, group_candidates


def _mk_node(
    *,
    name: str = "Frame 413",
    node_type: str = "FRAME",
    parent_type: str | None = "header",
    children: dict[str, int] | None = None,
    sample_text: str | None = None,
    component_key: str | None = None,
) -> dict:
    """Build a candidate-shaped dict like `_fetch_unclassified_for_screen`
    returns.
    """
    return {
        "name": name,
        "node_type": node_type,
        "parent_classified_as": parent_type,
        "child_type_dist": children or {},
        "sample_text": sample_text,
        "component_key": component_key,
    }


class TestDedupKey:
    def test_identical_nodes_same_key(self):
        a = _mk_node()
        b = _mk_node()
        assert dedup_key(a) == dedup_key(b)

    def test_different_name_different_key(self):
        assert dedup_key(_mk_node(name="A")) != dedup_key(_mk_node(name="B"))

    def test_different_node_type_different_key(self):
        a = _mk_node(node_type="FRAME")
        b = _mk_node(node_type="INSTANCE")
        assert dedup_key(a) != dedup_key(b)

    def test_different_parent_type_different_key(self):
        a = _mk_node(parent_type="header")
        b = _mk_node(parent_type="bottom_nav")
        assert dedup_key(a) != dedup_key(b)

    def test_none_parent_handled(self):
        # Same structure, both with None parents → same key.
        a = _mk_node(parent_type=None)
        b = _mk_node(parent_type=None)
        assert dedup_key(a) == dedup_key(b)

    def test_child_dist_ordering_ignored(self):
        # {'FRAME': 2, 'TEXT': 1} should dedup with {'TEXT': 1, 'FRAME': 2}.
        a = _mk_node(children={"FRAME": 2, "TEXT": 1})
        b = _mk_node(children={"TEXT": 1, "FRAME": 2})
        assert dedup_key(a) == dedup_key(b)

    def test_child_dist_values_matter(self):
        a = _mk_node(children={"FRAME": 2})
        b = _mk_node(children={"FRAME": 3})
        assert dedup_key(a) != dedup_key(b)

    def test_sample_text_truncated_to_60(self):
        # Two nodes with long sample_text that differ only AFTER char 60
        # still dedup (they'll be close enough for classifier purposes;
        # full text isn't load-bearing once the first 60 chars match).
        prefix = "same first sixty chars of shared content 1234567890123456789"
        assert len(prefix) >= 60
        a = _mk_node(sample_text=prefix + "TAIL_A" * 20)
        b = _mk_node(sample_text=prefix + "TAIL_B" * 20)
        assert dedup_key(a) == dedup_key(b)

    def test_sample_text_differs_in_first_60(self):
        a = _mk_node(sample_text="Sign in")
        b = _mk_node(sample_text="Sign up")
        assert dedup_key(a) != dedup_key(b)

    def test_sample_text_none_vs_empty(self):
        # Both represent "no sample text" — treat as equivalent.
        a = _mk_node(sample_text=None)
        b = _mk_node(sample_text="")
        assert dedup_key(a) == dedup_key(b)

    def test_component_key_matters(self):
        a = _mk_node(component_key="mkey-button-primary")
        b = _mk_node(component_key="mkey-button-secondary")
        assert dedup_key(a) != dedup_key(b)

    def test_component_key_none_vs_missing(self):
        a = _mk_node(component_key=None)
        b = _mk_node(component_key="")
        assert dedup_key(a) == dedup_key(b)


class TestGroupCandidates:
    def test_empty_input(self):
        assert group_candidates([]) == {}

    def test_all_unique(self):
        a = _mk_node(name="A")
        b = _mk_node(name="B")
        c = _mk_node(name="C")
        groups = group_candidates([a, b, c])
        assert len(groups) == 3
        for members in groups.values():
            assert len(members) == 1

    def test_all_duplicates(self):
        items = [_mk_node() for _ in range(5)]
        groups = group_candidates(items)
        assert len(groups) == 1
        assert list(groups.values())[0] == items

    def test_mixed(self):
        x1 = _mk_node(name="X")
        x2 = _mk_node(name="X")
        x3 = _mk_node(name="X")
        y1 = _mk_node(name="Y")
        y2 = _mk_node(name="Y")
        z1 = _mk_node(name="Z")
        groups = group_candidates([x1, x2, x3, y1, y2, z1])
        assert len(groups) == 3
        sizes = sorted(len(v) for v in groups.values())
        assert sizes == [1, 2, 3]

    def test_group_preserves_insertion_order(self):
        """Representative is the FIRST item in the group; later callers
        classify the representative and propagate. Order stability
        matters so reproducing a run picks the same representative.
        """
        x1 = _mk_node(name="X", sample_text="first")
        x2 = _mk_node(name="X", sample_text="first")
        x3 = _mk_node(name="X", sample_text="first")
        groups = group_candidates([x1, x2, x3])
        members = list(groups.values())[0]
        assert members[0] is x1
        assert members[-1] is x3

    def test_deterministic_keys_across_calls(self):
        a = _mk_node()
        g1 = group_candidates([a])
        g2 = group_candidates([a])
        assert list(g1.keys()) == list(g2.keys())
