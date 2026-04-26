"""Phase E #4 follow-on — VLM-driven variant labeling.

The cluster-only induction (test_variant_cluster_only.py) shipped
custom_N labels with real medoid-derived representative values.
This commit adds the VLM-relabeling layer per Codex 2026-04-26
(gpt-5.5 high reasoning) review:

  "Make it an actual mocked VLM labeling path, not just dormant
  infrastructure."

Per Codex's design:
  - VlmCall + ImageProvider protocols
  - null_vlm_call + null_image_provider defaults (preserve
    cluster-only behavior)
  - build_variant_label_prompt: per-cluster prompt with closed
    STANDARD_VARIANTS vocab + 'unknown' option
  - build_gemini_vlm_call: Gemini-backed adapter wrapping
    dd.classify_vision_gemini._default_gemini_call (the existing
    multi-image + JSON-schema infrastructure)
  - _apply_vlm_labels: per-cluster relabeling with thresholds:
    * skip clusters with < 2 members (no visual evidence)
    * skip when image_provider returns no images
    * relabel only when verdict in STANDARD_VARIANTS AND
      confidence >= threshold AND verdict not already used
    * keep custom_N otherwise; record verdict for triage

Bridge thumbnail rendering is the deferred follow-on per Codex:
"the bridge integration is the riskiest part of the pipeline."
The image_provider parameter is injectable; tests use synthetic
PNG bytes.
"""

from __future__ import annotations

import json

from dd.cluster_variants import (
    DEFAULT_VLM_CONFIDENCE_THRESHOLD,
    STANDARD_VARIANTS,
    VlmCall,
    _apply_vlm_labels,
    _cluster_and_label,
    build_gemini_vlm_call,
    build_variant_label_prompt,
    null_image_provider,
    null_vlm_call,
)


# Synthetic PNG bytes — minimal valid PNG header so the image
# provider returns "non-empty" without depending on a real renderer.
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def _instance(node_id: int, fill_hex: str = "#FF0000") -> dict:
    """Match the shape used by test_variant_cluster_only.py."""
    return {
        "node_id": node_id,
        "width": 100,
        "height": 50,
        "corner_radius": 8,
        "fills": json.dumps([{"type": "SOLID", "color": fill_hex}]),
        "strokes": None,
        "effects": None,
    }


def _fixed_image_provider(node_ids: list[int]) -> list:
    """Returns synthetic PNGs for every node id."""
    return [_FAKE_PNG] * len(node_ids)


class TestNullDefaults:
    """The default null_vlm_call / null_image_provider preserve
    cluster-only behavior (Phase E #4 contract)."""

    def test_null_vlm_call_returns_unknown(self):
        verdict = null_vlm_call("any prompt", [_FAKE_PNG])
        assert verdict["verdict"] == "unknown"
        assert verdict["confidence"] == 0.0
        assert "no vlm" in verdict["reason"].lower()

    def test_null_image_provider_returns_all_none(self):
        result = null_image_provider([1, 2, 3])
        assert result == [None, None, None]

    def test_apply_vlm_labels_with_nulls_preserves_clusters(self):
        clusters = [
            {
                "variant": "custom_1",
                "confidence": 0.9,
                "members": [1, 2, 3],
                "source": "cluster",
                "representative_values": {"bg": "#FF0000"},
            },
        ]
        relabeled = _apply_vlm_labels(
            clusters, "button", null_vlm_call, null_image_provider,
        )
        # null_image_provider returns no images → VLM not called →
        # cluster-only labels preserved.
        assert relabeled[0]["variant"] == "custom_1"
        assert relabeled[0]["source"] == "cluster"


class TestPromptBuilder:
    """build_variant_label_prompt produces a sensible prompt."""

    def test_includes_catalog_type(self):
        p = build_variant_label_prompt("button", 0, 3)
        assert "button" in p

    def test_includes_cluster_index(self):
        p = build_variant_label_prompt("button", 2, 5)
        assert "cluster 3 of 5" in p

    def test_lists_all_standard_variants(self):
        p = build_variant_label_prompt("button", 0, 1)
        for variant in STANDARD_VARIANTS:
            assert f'"{variant}"' in p

    def test_includes_unknown_option(self):
        p = build_variant_label_prompt("button", 0, 1)
        assert '"unknown"' in p

    def test_requests_json_response(self):
        p = build_variant_label_prompt("button", 0, 1)
        assert "JSON" in p
        assert "verdict" in p
        assert "confidence" in p


class TestRelabelingWithVlmVerdict:
    """When VLM returns a high-confidence STANDARD_VARIANT, relabel
    the cluster from custom_N to the verdict."""

    def test_high_confidence_primary_relabels_custom_to_primary(self):
        def vlm(prompt: str, images: list[bytes]) -> dict:
            return {"verdict": "primary", "confidence": 0.95, "reason": "filled blue"}

        clusters = [
            {
                "variant": "custom_1",
                "confidence": 0.9,
                "members": [1, 2, 3],
                "source": "cluster",
                "representative_values": {"bg": "#0000FF"},
            },
        ]
        relabeled = _apply_vlm_labels(
            clusters, "button", vlm, _fixed_image_provider,
        )
        assert relabeled[0]["variant"] == "primary"
        assert relabeled[0]["source"] == "vlm"
        assert relabeled[0]["confidence"] == 0.95
        assert relabeled[0]["vlm_reason"] == "filled blue"
        # representative values unchanged (cluster-derived)
        assert relabeled[0]["representative_values"]["bg"] == "#0000FF"

    def test_low_confidence_keeps_custom_label(self):
        def vlm(prompt: str, images: list[bytes]) -> dict:
            return {"verdict": "primary", "confidence": 0.3, "reason": "guess"}

        clusters = [
            {
                "variant": "custom_1",
                "confidence": 0.9,
                "members": [1, 2, 3],
                "source": "cluster",
                "representative_values": {"bg": "#FF0000"},
            },
        ]
        relabeled = _apply_vlm_labels(
            clusters, "button", vlm, _fixed_image_provider,
        )
        # Low confidence (0.3 < 0.75 default threshold) → keep custom
        assert relabeled[0]["variant"] == "custom_1"
        assert relabeled[0]["source"] == "cluster"
        # But VLM verdict is recorded for triage
        assert relabeled[0]["vlm_verdict"] == "primary"
        assert relabeled[0]["vlm_confidence"] == 0.3

    def test_unknown_verdict_keeps_custom_label(self):
        def vlm(prompt: str, images: list[bytes]) -> dict:
            return {"verdict": "unknown", "confidence": 0.9, "reason": "?"}

        clusters = [
            {
                "variant": "custom_1",
                "confidence": 0.9,
                "members": [1, 2, 3],
                "source": "cluster",
                "representative_values": {"bg": "#FF0000"},
            },
        ]
        relabeled = _apply_vlm_labels(
            clusters, "button", vlm, _fixed_image_provider,
        )
        # 'unknown' is not in STANDARD_VARIANTS → keep custom
        assert relabeled[0]["variant"] == "custom_1"
        assert relabeled[0]["source"] == "cluster"

    def test_invalid_verdict_keeps_custom_label(self):
        def vlm(prompt: str, images: list[bytes]) -> dict:
            return {"verdict": "weird-label-not-in-vocab", "confidence": 0.95}

        clusters = [
            {
                "variant": "custom_1",
                "confidence": 0.9,
                "members": [1, 2, 3],
                "source": "cluster",
                "representative_values": {"bg": "#FF0000"},
            },
        ]
        relabeled = _apply_vlm_labels(
            clusters, "button", vlm, _fixed_image_provider,
        )
        assert relabeled[0]["variant"] == "custom_1"

    def test_singleton_cluster_skipped(self):
        """Singleton clusters skip VLM (no visual evidence cluster)."""
        called = []

        def vlm(prompt: str, images: list[bytes]) -> dict:
            called.append(True)
            return {"verdict": "primary", "confidence": 0.95}

        clusters = [
            {
                "variant": "custom_1",
                "confidence": 0.5,
                "members": [1],  # singleton
                "source": "cluster",
                "representative_values": {"bg": "#FF0000"},
            },
        ]
        relabeled = _apply_vlm_labels(
            clusters, "button", vlm, _fixed_image_provider,
        )
        assert not called, "Singleton clusters should not invoke VLM."
        assert relabeled[0]["variant"] == "custom_1"

    def test_duplicate_verdict_keeps_second_as_custom(self):
        """If VLM returns 'primary' for two clusters, only the first
        gets relabeled — duplicates fall back to custom_N."""
        verdicts = ["primary", "primary"]
        idx = [0]

        def vlm(prompt: str, images: list[bytes]) -> dict:
            v = verdicts[idx[0]]
            idx[0] += 1
            return {"verdict": v, "confidence": 0.9, "reason": "dup"}

        clusters = [
            {
                "variant": "custom_1",
                "confidence": 0.9,
                "members": [1, 2, 3],
                "source": "cluster",
                "representative_values": {"bg": "#0000FF"},
            },
            {
                "variant": "custom_2",
                "confidence": 0.9,
                "members": [4, 5, 6],
                "source": "cluster",
                "representative_values": {"bg": "#1A00FF"},
            },
        ]
        relabeled = _apply_vlm_labels(
            clusters, "button", vlm, _fixed_image_provider,
        )
        assert relabeled[0]["variant"] == "primary"
        assert relabeled[0]["source"] == "vlm"
        assert relabeled[1]["variant"] == "custom_2", (
            "Duplicate VLM verdict should keep the second cluster's "
            "custom_N label (duplicate-prevention guard)."
        )


class TestImageProviderEmptyResult:
    """When image_provider returns all None for a cluster's members,
    that cluster is skipped (cluster-only label preserved). The
    other clusters are still attempted."""

    def test_partial_image_coverage(self):
        def vlm(prompt: str, images: list[bytes]) -> dict:
            return {"verdict": "primary", "confidence": 0.95}

        # Image provider returns images only for cluster 1's
        # members [1,2,3]; for cluster 2's members [4,5,6] returns
        # all None.
        def image_provider(node_ids: list[int]) -> list:
            if 1 in node_ids:
                return [_FAKE_PNG] * len(node_ids)
            return [None] * len(node_ids)

        clusters = [
            {
                "variant": "custom_1",
                "confidence": 0.9,
                "members": [1, 2, 3],
                "source": "cluster",
                "representative_values": {"bg": "#0000FF"},
            },
            {
                "variant": "custom_2",
                "confidence": 0.9,
                "members": [4, 5, 6],
                "source": "cluster",
                "representative_values": {"bg": "#FF00FF"},
            },
        ]
        relabeled = _apply_vlm_labels(
            clusters, "button", vlm, image_provider,
        )
        # Cluster 1 has images → relabeled
        assert relabeled[0]["variant"] == "primary"
        # Cluster 2 has no images → keep custom
        assert relabeled[1]["variant"] == "custom_2"


class TestThresholdConfigurable:
    """The confidence threshold is parameter; default is documented."""

    def test_default_threshold_is_0_75(self):
        # Just pin the constant; a future change is intentional.
        assert DEFAULT_VLM_CONFIDENCE_THRESHOLD == 0.75

    def test_custom_threshold_lower_accepts_more(self):
        def vlm(prompt: str, images: list[bytes]) -> dict:
            return {"verdict": "primary", "confidence": 0.5, "reason": "uncertain"}

        clusters = [
            {
                "variant": "custom_1",
                "confidence": 0.5,
                "members": [1, 2],
                "source": "cluster",
                "representative_values": {"bg": "#000"},
            },
        ]
        # Default threshold (0.75) → would reject 0.5 confidence
        default_relabeled = _apply_vlm_labels(
            clusters, "button", vlm, _fixed_image_provider,
        )
        assert default_relabeled[0]["variant"] == "custom_1"

        # Lower threshold → accepts
        permissive_relabeled = _apply_vlm_labels(
            clusters, "button", vlm, _fixed_image_provider,
            threshold=0.3,
        )
        assert permissive_relabeled[0]["variant"] == "primary"


class TestGeminiAdapterBuildShape:
    """build_gemini_vlm_call returns a callable matching VlmCall."""

    def test_returns_callable_with_no_images_short_circuits(self):
        # Build with a fake key — never actually called because
        # the image list will be empty.
        call = build_gemini_vlm_call(api_key="test-key-not-used")
        verdict = call("prompt", [])
        # Empty images → no API call → verdict='unknown'
        assert verdict["verdict"] == "unknown"
        assert verdict["confidence"] == 0.0
        assert "no images" in verdict["reason"].lower()


class TestEndToEndInduceVariantsWithVlm:
    """induce_variants accepts an image_provider parameter; when
    provided alongside a real vlm_call, the relabel path fires."""

    def _make_db_with_button_instances(self) -> "sqlite3.Connection":
        import sqlite3
        from dd import db as dd_db
        conn = dd_db.init_db(":memory:")
        conn.execute(
            "INSERT INTO files (id, file_key, name) "
            "VALUES (1, 'test', 'test.fig')"
        )
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, "
            "width, height) VALUES (1, 1, '1:1', 'Screen 1', 375, 812)"
        )
        from dd.catalog import seed_catalog
        seed_catalog(conn)
        # Add 5+ button instances with one distinct cluster
        for i in range(1, 11):
            conn.execute(
                "INSERT INTO nodes "
                "(id, screen_id, figma_node_id, name, node_type, "
                "fills, corner_radius) VALUES (?, 1, ?, 'btn', "
                "'INSTANCE', ?, 8)",
                (
                    i,
                    f"1:{i}",
                    json.dumps([{
                        "type": "SOLID",
                        "color": "#FF0000",
                    }]),
                ),
            )
            conn.execute(
                "INSERT INTO screen_component_instances "
                "(screen_id, node_id, canonical_type, classification_source) "
                "VALUES (1, ?, 'button', 'heuristic')",
                (i,),
            )
        conn.commit()
        return conn

    def test_induce_variants_relabels_with_vlm(self):
        from dd.cluster_variants import induce_variants

        conn = self._make_db_with_button_instances()

        def vlm(prompt: str, images: list[bytes]) -> dict:
            return {"verdict": "primary", "confidence": 0.95}

        result = induce_variants(
            conn, vlm, ["button"], image_provider=_fixed_image_provider,
        )
        assert result["button"] > 0

        # Inspect persisted rows: at least one should have variant="primary"
        # and source="vlm".
        cursor = conn.execute(
            "SELECT variant, source FROM variant_token_binding "
            "WHERE catalog_type = 'button' "
            "GROUP BY variant, source"
        )
        rows = list(cursor.fetchall())
        variants = [r[0] for r in rows]
        sources = [r[1] for r in rows]
        # At least one cluster should have been relabeled to primary.
        assert "primary" in variants, (
            f"Expected at least one VLM-relabeled 'primary' variant. "
            f"Got variants: {variants}"
        )
        assert "vlm" in sources, (
            f"Expected at least one row with source='vlm'. "
            f"Got sources: {sources}"
        )

    def test_induce_variants_without_image_provider_stays_cluster_only(self):
        """Default behavior (no image_provider passed) preserves
        the Phase E #4 cluster-only contract."""
        from dd.cluster_variants import induce_variants

        conn = self._make_db_with_button_instances()

        def vlm(prompt: str, images: list[bytes]) -> dict:
            raise AssertionError(
                "VLM should not be invoked when image_provider is None"
            )

        # No image_provider → null_image_provider is used → no PNGs
        # → vlm_call short-circuits → cluster-only labels.
        result = induce_variants(conn, vlm, ["button"])
        assert result["button"] > 0
        cursor = conn.execute(
            "SELECT DISTINCT source FROM variant_token_binding "
            "WHERE catalog_type = 'button'"
        )
        sources = [r[0] for r in cursor.fetchall()]
        assert sources == ["cluster"], (
            f"Default induce_variants (no image_provider) should "
            f"produce cluster-only sources. Got: {sources}"
        )
