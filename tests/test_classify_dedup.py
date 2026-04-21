"""Tests for dedup by structural signature (classifier v2 step 1).

The dedup key groups nodes that are structurally identical so they
share a classification verdict instead of being classified
individually. Saves 5-8x on API calls on the full corpus per the
user's review data (674 flagged rows collapsed to 218 patterns on
post-classification signature alone).
"""

from __future__ import annotations

import pytest

from dd.classify_dedup import (
    aspect_bucket, dedup_key, group_candidates, size_bucket,
)


def _mk_node(
    *,
    name: str = "Frame 413",
    node_type: str = "FRAME",
    parent_type: str | None = "header",
    children: dict[str, int] | None = None,
    sample_text: str | None = None,
    component_key: str | None = None,
    width: float | None = 100.0,
    height: float | None = 100.0,
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
        "width": width,
        "height": height,
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


class TestAspectBucket:
    """Aspect ratio (width/height) bucketed into 3 coarse categories.
    Solves the Frame 373 bug: 6x32 (aspect 0.19) collapsing with
    square/wide 'Frame 373' instances whose verdict doesn't apply.
    """

    def test_very_tall_rectangle(self):
        # aspect < 0.7 → "tall"
        assert aspect_bucket(width=6, height=32) == "tall"
        assert aspect_bucket(width=40, height=200) == "tall"

    def test_square_ish(self):
        # 0.7 ≤ aspect ≤ 1.4 → "square"
        assert aspect_bucket(width=100, height=100) == "square"
        assert aspect_bucket(width=108, height=108) == "square"
        assert aspect_bucket(width=80, height=100) == "square"  # aspect 0.8
        assert aspect_bucket(width=120, height=100) == "square"  # aspect 1.2

    def test_wide_rectangle(self):
        # aspect > 1.4 → "wide"
        assert aspect_bucket(width=300, height=50) == "wide"
        assert aspect_bucket(width=428, height=120) == "wide"

    def test_zero_or_missing_dimensions_safe(self):
        # Degenerate input shouldn't crash; bucket as "unknown".
        assert aspect_bucket(width=0, height=100) == "unknown"
        assert aspect_bucket(width=100, height=0) == "unknown"
        assert aspect_bucket(width=None, height=100) == "unknown"
        assert aspect_bucket(width=100, height=None) == "unknown"


class TestSizeBucket:
    """Max-dimension size bucket. Solves the Frame 366 / Frame 362 bug:
    square 108x108 collapsing with square 16x16 — same aspect, very
    different semantic (large content vs tiny icon).
    """

    def test_tiny(self):
        # max dim < 32 → "tiny"
        assert size_bucket(width=16, height=16) == "tiny"
        assert size_bucket(width=24, height=24) == "tiny"

    def test_small(self):
        # 32 ≤ max dim < 96 → "small"
        assert size_bucket(width=40, height=40) == "small"
        assert size_bucket(width=64, height=32) == "small"

    def test_medium(self):
        # 96 ≤ max dim < 300 → "medium"
        assert size_bucket(width=108, height=108) == "medium"
        assert size_bucket(width=200, height=50) == "medium"

    def test_large(self):
        # max dim ≥ 300 → "large"
        assert size_bucket(width=428, height=100) == "large"
        assert size_bucket(width=400, height=400) == "large"

    def test_zero_or_missing_dimensions_safe(self):
        assert size_bucket(width=0, height=0) == "unknown"
        assert size_bucket(width=None, height=100) == "unknown"
        assert size_bucket(width=100, height=None) == "unknown"


class TestDedupKeyVisualBuckets:
    """dedup_key incorporates aspect + size buckets so visually-
    different instances with the same structural signature no longer
    collapse.
    """

    def test_same_name_different_aspect_split(self):
        # Frame 373 bug: 6x32 (tall) vs 64x64 (square).
        a = _mk_node(name="Frame 373", width=6, height=32)
        b = _mk_node(name="Frame 373", width=64, height=64)
        assert dedup_key(a) != dedup_key(b)

    def test_same_name_different_size_split(self):
        # Frame 362/366 bug: 16x16 (tiny square) vs 108x108 (medium sq).
        a = _mk_node(name="Frame 362", width=16, height=16)
        b = _mk_node(name="Frame 362", width=108, height=108)
        assert dedup_key(a) != dedup_key(b)

    def test_same_name_same_bucket_still_dedups(self):
        # Two 100x100 squares still collapse.
        a = _mk_node(name="Icon", width=100, height=100)
        b = _mk_node(name="Icon", width=100, height=100)
        assert dedup_key(a) == dedup_key(b)

    def test_close_sizes_within_same_bucket_dedup(self):
        # Both medium squares (108 and 120), dedup is desired.
        a = _mk_node(name="Avatar", width=108, height=108)
        b = _mk_node(name="Avatar", width=120, height=120)
        assert dedup_key(a) == dedup_key(b)

    def test_different_aspect_same_size_split(self):
        # Same max-dim (200), different aspect (square vs wide).
        a = _mk_node(name="Banner", width=200, height=200)  # square
        b = _mk_node(name="Banner", width=200, height=50)   # wide
        assert dedup_key(a) != dedup_key(b)

    def test_missing_dimensions_fall_into_unknown_bucket(self):
        # Two candidates with no geometry still group together.
        a = _mk_node(name="Ghost", width=None, height=None)
        b = _mk_node(name="Ghost", width=None, height=None)
        assert dedup_key(a) == dedup_key(b)

    def test_deterministic_keys_across_calls(self):
        a = _mk_node()
        g1 = group_candidates([a])
        g2 = group_candidates([a])
        assert list(g1.keys()) == list(g2.keys())
