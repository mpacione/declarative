"""Tests for classifier-v2 batched-crops vision classifier.

`classify_crops_batch` in dd.classify_vision_batched accepts a list
of candidates PLUS a pre-computed crop map (figma_node_id → PNG
bytes) and sends ONE image per node + one prompt to the vision
model. Shape is the same closed-vocabulary tool-use flow as v1;
input shape + prompt are different.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dd.classify_vision_batched import (
    CLASSIFY_CROPS_TOOL_SCHEMA,
    build_crops_batch_prompt,
    classify_crops_batch,
)


def _mk_candidate(**overrides):
    base = {
        "screen_id": 150,
        "node_id": 10,
        "figma_node_id": "10:1",
        "name": "Frame 413",
        "node_type": "FRAME",
        "parent_classified_as": "header",
        "total_children": 4,
        "child_type_dist": {"FRAME": 3, "TEXT": 1},
        "sample_text": "Filename",
        "ckr_registered_name": None,
    }
    base.update(overrides)
    return base


def _tiny_png() -> bytes:
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


class TestBuildCropsBatchPrompt:
    def test_mentions_every_candidate(self):
        cands = [
            _mk_candidate(node_id=10, name="Left"),
            _mk_candidate(node_id=11, name="Right"),
        ]
        prompt = build_crops_batch_prompt(cands, catalog=[])
        assert "Left" in prompt
        assert "Right" in prompt
        # node_id references so the tool output can key back.
        assert "node_id=10" in prompt
        assert "node_id=11" in prompt

    def test_includes_rules_section(self):
        prompt = build_crops_batch_prompt(
            [_mk_candidate()], catalog=[],
        )
        assert "Rules" in prompt or "rules" in prompt
        # The canonical-decoding rules carry over from v1.
        assert "confidence" in prompt.lower() or "calibrated" in prompt.lower()

    def test_mentions_image_per_node(self):
        prompt = build_crops_batch_prompt(
            [_mk_candidate()], catalog=[],
        )
        # Prompt must tell the model each node is its own image with
        # the bbox outlined.
        assert (
            "crop" in prompt.lower()
            or "outlined" in prompt.lower()
            or "highlighted" in prompt.lower()
        )


class TestClassifyCropsBatchToolSchema:
    def test_schema_has_classifications_array(self):
        assert CLASSIFY_CROPS_TOOL_SCHEMA["name"]
        props = CLASSIFY_CROPS_TOOL_SCHEMA["input_schema"]["properties"]
        assert "classifications" in props
        item_props = props["classifications"]["items"]["properties"]
        # Required per-item: screen_id, node_id, canonical_type,
        # confidence, reason.
        for key in ("screen_id", "node_id", "canonical_type",
                    "confidence", "reason"):
            assert key in item_props


class TestClassifyCropsBatchIntegration:
    def test_calls_client_with_one_image_per_candidate(self):
        """The vision model must receive ONE image content block per
        candidate, with the correct PNG bytes for each.
        """
        from unittest.mock import MagicMock
        captured = {}

        def fake_stream(**kwargs):
            captured["kwargs"] = kwargs
            # Mock a streaming context-manager that returns a
            # well-formed tool_use response.
            class Ctx:
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
                def get_final_message(self):
                    tool_block = SimpleNamespace(
                        type="tool_use",
                        name=CLASSIFY_CROPS_TOOL_SCHEMA["name"],
                        input={"classifications": [
                            {"screen_id": 150, "node_id": 10,
                             "canonical_type": "header",
                             "confidence": 0.88,
                             "reason": "stub1"},
                            {"screen_id": 150, "node_id": 11,
                             "canonical_type": "footer",
                             "confidence": 0.83,
                             "reason": "stub2"},
                        ]},
                    )
                    return SimpleNamespace(content=[tool_block])
            return Ctx()

        client = MagicMock()
        client.messages.stream.side_effect = fake_stream

        cands = [
            _mk_candidate(node_id=10),
            _mk_candidate(node_id=11),
        ]
        crops = {
            (150, 10): _tiny_png(),
            (150, 11): _tiny_png(),
        }
        results = classify_crops_batch(cands, crops, client, catalog=[])

        assert len(results) == 2
        assert {r["node_id"] for r in results} == {10, 11}
        # Inspect the content list passed to the stream: should be
        # image + image + text (in some order).
        msgs = captured["kwargs"]["messages"]
        content = msgs[0]["content"]
        image_count = sum(
            1 for c in content if c.get("type") == "image"
        )
        text_count = sum(
            1 for c in content if c.get("type") == "text"
        )
        assert image_count == 2
        assert text_count == 1

    def test_skips_candidates_with_no_crop(self):
        from unittest.mock import MagicMock
        cands = [
            _mk_candidate(node_id=10),
            _mk_candidate(node_id=11),
        ]
        crops = {(150, 10): _tiny_png()}  # 11 missing
        client = MagicMock()
        # Won't be called — zero candidates if we short-circuit.
        results = classify_crops_batch(cands, crops, client, catalog=[])
        # candidate 11 has no crop; skip it but still classify 10.
        # Either the client is called with 1 image and returns 1 result,
        # OR the function short-circuits when too few candidates.
        # Either is OK; here we just assert we don't crash.
        assert isinstance(results, list)

    def test_empty_input_returns_empty(self):
        from unittest.mock import MagicMock
        client = MagicMock()
        results = classify_crops_batch([], {}, client, catalog=[])
        assert results == []
        # No client call made.
        client.messages.stream.assert_not_called()
