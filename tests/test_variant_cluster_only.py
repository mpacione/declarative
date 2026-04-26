"""Phase E #4 fix — variant induction is now cluster-only (no VLM).

Pre-fix dd/cluster_variants.py:_cluster_and_label was a v0.1 shell:
single cluster per type, custom_1, all-NULL slot values, vlm_call
with empty images list (Gemini never invoked). Pure schema padding.

Codex 2026-04-26 (gpt-5.5 high reasoning) review:
"B is the right call... Mode-3 does not need human-perfect variant
names to become valuable; it needs real grouped instances and real
representative values. custom_1, custom_2, etc. are acceptable if
they honestly mean 'observed visual variant cluster.'"

Phase E #4 implementation:
- K-means clustering in OKLCH+dimensions (NaN-aware distance)
- Silhouette over 2..min(8, n) picks K with K=1 fallback
- Medoid (not centroid) as representative value source — real
  observed values from the cluster, not averages
- Honest custom_N labels; source="cluster"; confidence based on
  silhouette cohesion
- VLM call ignored entirely (ABI retained for ADR-008 Stream B
  follow-on)

These tests pin the post-fix behavior contract.
"""

from __future__ import annotations

import json

import pytest

from dd.cluster_variants import (
    _cluster_and_label,
    _feature_vector,
    _kmeans,
    _primary_solid_hex,
    _representative_values,
    _silhouette,
)


def _instance(
    *,
    node_id: int,
    fill_hex: str | None = None,
    stroke_hex: str | None = None,
    width: float = 100,
    height: float = 50,
    corner_radius: float | None = None,
) -> dict:
    """Build an instance dict in the shape _cluster_and_label expects."""
    fills = (
        [{"type": "SOLID", "color": fill_hex}]
        if fill_hex
        else None
    )
    strokes = (
        [{"type": "SOLID", "color": stroke_hex}]
        if stroke_hex
        else None
    )
    return {
        "node_id": node_id,
        "width": width,
        "height": height,
        "corner_radius": corner_radius,
        "fills": json.dumps(fills) if fills else None,
        "strokes": json.dumps(strokes) if strokes else None,
        "effects": None,
    }


def _no_vlm_call(*args, **kwargs):
    """Placeholder VLM call — never invoked by the post-fix code."""
    raise AssertionError(
        "Phase E #4: cluster-only induction must not call the VLM."
    )


class TestSingleClusterFallbacks:
    """Tiny inputs: stable single-cluster output."""

    def test_empty_instances_returns_empty(self):
        result = _cluster_and_label(
            [], _no_vlm_call, "button",
        )
        assert result == []

    def test_single_instance_returns_single_cluster(self):
        result = _cluster_and_label(
            [_instance(node_id=1, fill_hex="#FF0000")],
            _no_vlm_call, "button",
        )
        assert len(result) == 1
        assert result[0]["variant"] == "custom_1"
        assert result[0]["source"] == "cluster"
        assert result[0]["members"] == [1]


class TestMultipleClustersEmerge:
    """Visually distinct instances: emits multiple clusters."""

    def test_two_color_groups_yield_two_clusters(self):
        """5 red instances + 5 green instances → 2 clusters
        (distinct fill colors create separable feature vectors)."""
        instances = (
            [_instance(node_id=i, fill_hex="#FF0000", width=100, height=40)
             for i in range(1, 6)]
            + [_instance(node_id=i, fill_hex="#00FF00", width=100, height=40)
               for i in range(6, 11)]
        )
        result = _cluster_and_label(instances, _no_vlm_call, "button")
        assert len(result) >= 2, (
            f"Expected ≥2 clusters for visually distinct red/green "
            f"buttons. Got {len(result)} clusters."
        )

    def test_members_partitioned_exactly_once(self):
        """Every input instance appears in exactly one cluster's
        members list."""
        instances = (
            [_instance(node_id=i, fill_hex="#FF0000")
             for i in range(1, 6)]
            + [_instance(node_id=i, fill_hex="#0000FF")
               for i in range(6, 11)]
        )
        result = _cluster_and_label(instances, _no_vlm_call, "button")
        all_members = [
            m for cluster in result for m in cluster["members"]
        ]
        assert sorted(all_members) == list(range(1, 11)), (
            "Members must be partitioned exactly once across "
            f"clusters. Got: {sorted(all_members)}"
        )


class TestRepresentativeValuesObservedNotAveraged:
    """The medoid produces real observed values, not centroid averages."""

    def test_representative_values_match_a_real_instance(self):
        """When a cluster has a clear color, the representative
        value should be one of the observed colors (from the medoid),
        not a synthetic average."""
        instances = [
            _instance(node_id=1, fill_hex="#FF0000", corner_radius=8),
            _instance(node_id=2, fill_hex="#FF0000", corner_radius=8),
            _instance(node_id=3, fill_hex="#FF0000", corner_radius=8),
            _instance(node_id=4, fill_hex="#0000FF", corner_radius=12),
            _instance(node_id=5, fill_hex="#0000FF", corner_radius=12),
            _instance(node_id=6, fill_hex="#0000FF", corner_radius=12),
        ]
        result = _cluster_and_label(instances, _no_vlm_call, "button")
        # At least one cluster should have bg matching #FF0000 or #0000FF
        bg_values = [c["representative_values"]["bg"] for c in result]
        assert any(bg in ("#FF0000", "#0000FF") for bg in bg_values), (
            f"Representative bg values should match observed instance "
            f"colors. Got: {bg_values}"
        )

    def test_representative_radius_is_observed_integer(self):
        instances = [
            _instance(node_id=i, fill_hex="#FF0000", corner_radius=8)
            for i in range(1, 6)
        ]
        result = _cluster_and_label(instances, _no_vlm_call, "button")
        radii = [c["representative_values"]["radius"] for c in result]
        # All instances had radius=8; result should reflect that.
        assert all(r == 8 for r in radii if r is not None)


class TestNoVLMCalled:
    """The headline contract — the VLM is never invoked."""

    def test_vlm_call_not_invoked(self):
        """The injected vlm_call raises AssertionError; if induction
        called it, the test would fail."""
        instances = [
            _instance(node_id=i, fill_hex="#FF0000")
            for i in range(1, 6)
        ]
        # Should NOT raise — vlm_call never invoked.
        _cluster_and_label(instances, _no_vlm_call, "button")

    def test_source_is_cluster_not_vlm(self):
        instances = [
            _instance(node_id=i, fill_hex="#FF0000")
            for i in range(1, 6)
        ]
        result = _cluster_and_label(instances, _no_vlm_call, "button")
        for cluster in result:
            assert cluster["source"] == "cluster", (
                "Phase E #4: cluster-only induction emits "
                "source='cluster'. VLM-derived 'vlm' source is "
                "deferred to ADR-008 Stream B follow-on."
            )

    def test_variant_label_is_custom_n(self):
        instances = [
            _instance(node_id=i, fill_hex=f"#{i:06X}")
            for i in range(1, 11)
        ]
        result = _cluster_and_label(instances, _no_vlm_call, "button")
        for cluster in result:
            assert cluster["variant"].startswith("custom_"), (
                f"Phase E #4: cluster-only induction produces "
                f"custom_N labels (no semantic naming until VLM "
                f"lands). Got: {cluster['variant']}"
            )


class TestFeatureVectorShape:
    """Feature vector includes color, dims, radius; missing values
    become NaN (not zero) so they don't pollute distance."""

    def test_feature_vector_with_full_instance(self):
        inst = _instance(
            node_id=1, fill_hex="#FF0000",
            width=200, height=100, corner_radius=8,
        )
        v = _feature_vector(inst)
        assert len(v) == 6
        # L*, C, h are populated; corner_radius=8; width=200; height=100
        import math
        assert not math.isnan(v[0])  # L*
        assert v[3] == 8  # corner_radius
        assert v[4] == 200  # width
        assert v[5] == 100  # height

    def test_feature_vector_no_fills_yields_nan_color(self):
        """Missing fill → NaN for L/C/h dimensions."""
        import math
        inst = _instance(node_id=1, fill_hex=None)
        v = _feature_vector(inst)
        assert math.isnan(v[0])  # L*
        assert math.isnan(v[1])  # C
        assert math.isnan(v[2])  # h


class TestPrimarySolidHex:
    """The fill-extraction helper handles JSON, dict, and string forms."""

    def test_returns_none_for_no_fills(self):
        assert _primary_solid_hex(None) is None
        assert _primary_solid_hex("") is None
        assert _primary_solid_hex([]) is None

    def test_extracts_from_dict_color(self):
        # Figma plugin shape: {r, g, b, a} in 0..1
        fills = [{
            "type": "SOLID",
            "color": {"r": 1.0, "g": 0.0, "b": 0.0},
        }]
        result = _primary_solid_hex(json.dumps(fills))
        assert result == "#FF0000"

    def test_extracts_from_string_hex(self):
        fills = [{"type": "SOLID", "color": "#ABCDEF"}]
        assert _primary_solid_hex(json.dumps(fills)) == "#ABCDEF"

    def test_skips_non_solid_fills(self):
        fills = [
            {"type": "GRADIENT_LINEAR"},
            {"type": "SOLID", "color": "#FF0000"},
        ]
        assert _primary_solid_hex(json.dumps(fills)) == "#FF0000"


class TestRepresentativeValuesShape:
    """The output dict contract."""

    def test_keys_are_bg_fg_border_radius(self):
        inst = _instance(
            node_id=1, fill_hex="#112233",
            stroke_hex="#445566", corner_radius=4,
        )
        result = _representative_values(inst)
        assert set(result.keys()) == {"bg", "fg", "border", "radius"}
        assert result["bg"] == "#112233"
        assert result["border"] == "#445566"
        assert result["radius"] == 4
        # fg is None (cluster-only doesn't infer fg; VLM follow-on
        # will).
        assert result["fg"] is None
