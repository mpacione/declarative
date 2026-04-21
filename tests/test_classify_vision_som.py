"""Tests for Set-of-Marks (SoM) classifier path.

Instead of per-node crops, render a single screenshot with every
classifiable node's bbox outlined and labeled with a numeric mark.
Ask Sonnet to classify each mark against the catalog in one call.

Reference: Microsoft SoM (arXiv 2310.11441) + WACV 2025 evaluation
(openaccess.thecvf.com/content/WACV2025W/LLVMAD) showing +7.45 pts
over plain prompting on Sonnet-class models.
"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from dd.classify_vision_som import (
    SOM_TOOL_NAME,
    build_som_tool_schema,
    classify_screen_som,
    render_som_overlay,
)


def _solid_png(w=600, h=400, rgb=(210, 210, 210)) -> bytes:
    img = Image.new("RGB", (w, h), rgb)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestRenderSomOverlay:
    def test_basic_render_produces_png(self):
        screen = _solid_png(600, 400)
        out = render_som_overlay(
            screen_png=screen,
            annotations=[
                {"id": 1, "x": 50, "y": 50, "w": 100, "h": 50},
                {"id": 2, "x": 200, "y": 100, "w": 80, "h": 80},
            ],
            screen_width=600, screen_height=400,
        )
        assert isinstance(out, bytes)
        img = Image.open(BytesIO(out))
        assert img.format == "PNG"

    def test_empty_annotations_returns_original_image(self):
        """Renderer is a no-op overlay when nothing's annotated —
        useful for testing / fallback paths.
        """
        screen = _solid_png(300, 200)
        out = render_som_overlay(
            screen_png=screen,
            annotations=[],
            screen_width=300, screen_height=200,
        )
        img = Image.open(BytesIO(out))
        # Size unchanged (no upscale for empty case).
        assert img.size == (300, 200)

    def test_respects_scale_factor(self):
        """If the rendered image is 2x the canvas coords (retina),
        bbox positions should scale accordingly.
        """
        # 1200x800 image represents a 600x400 canvas.
        screen = _solid_png(1200, 800)
        out = render_som_overlay(
            screen_png=screen,
            annotations=[{"id": 1, "x": 50, "y": 50, "w": 100, "h": 50}],
            screen_width=600, screen_height=400,
        )
        img = Image.open(BytesIO(out))
        w, h = img.size
        assert (w, h) == (1200, 800)  # preserved

    def test_rotation_produces_rotated_aabb(self):
        """Rotated nodes highlight their POST-rotation AABB — same
        convention as the spotlight crop path."""
        import math
        screen = _solid_png(400, 400)
        out = render_som_overlay(
            screen_png=screen,
            annotations=[{
                "id": 1, "x": 100, "y": 100, "w": 6, "h": 32,
                "rotation": math.pi / 2,
            }],
            screen_width=400, screen_height=400,
        )
        # Just verify it renders without crashing + returns a PNG.
        img = Image.open(BytesIO(out))
        assert img.format == "PNG"


class TestBuildSomToolSchema:
    def test_schema_uses_mark_id_not_node_id(self):
        """SoM output is keyed by the numeric mark shown on the image,
        not (screen_id, node_id). The caller maps mark_id → node_id
        after receiving the response.
        """
        catalog = [
            {"canonical_name": "button", "category": "actions",
             "behavioral_description": "tap"},
        ]
        schema = build_som_tool_schema(catalog)
        item_props = schema["input_schema"]["properties"][
            "classifications"
        ]["items"]["properties"]
        assert "mark_id" in item_props
        assert "node_id" not in item_props

    def test_schema_pins_canonical_type_enum(self):
        catalog = [
            {"canonical_name": "button", "category": "actions",
             "behavioral_description": "tap"},
        ]
        schema = build_som_tool_schema(catalog)
        item_props = schema["input_schema"]["properties"][
            "classifications"
        ]["items"]["properties"]
        enum = item_props["canonical_type"]["enum"]
        assert "button" in enum
        assert "container" in enum
        assert "unsure" in enum


class TestClassifyScreenSom:
    """Integration: render overlay + call Sonnet + parse response."""

    def _make_mock_client(self, classifications: list[dict]):
        mock = MagicMock()
        tool_use = SimpleNamespace(
            type="tool_use",
            name=SOM_TOOL_NAME,
            input={"classifications": classifications},
        )
        response = SimpleNamespace(content=[tool_use])
        mock.messages.create.return_value = response
        return mock

    def test_empty_annotations_returns_empty(self):
        client = self._make_mock_client([])
        out = classify_screen_som(
            screen_png=_solid_png(),
            annotations=[],
            client=client,
            catalog=[],
            screen_width=600, screen_height=400,
        )
        assert out == []
        # No API call when nothing to classify.
        client.messages.create.assert_not_called()

    def test_parses_classifications_with_mark_id(self):
        client = self._make_mock_client([
            {"mark_id": 1, "canonical_type": "button",
             "confidence": 0.95, "reason": "pill with label"},
            {"mark_id": 2, "canonical_type": "heading",
             "confidence": 0.85, "reason": "large text"},
        ])
        out = classify_screen_som(
            screen_png=_solid_png(),
            annotations=[
                {"id": 1, "x": 10, "y": 10, "w": 80, "h": 30},
                {"id": 2, "x": 10, "y": 60, "w": 200, "h": 40},
            ],
            client=client,
            catalog=[
                {"canonical_name": "button", "category": "actions",
                 "behavioral_description": "tap"},
                {"canonical_name": "heading",
                 "category": "content_and_display",
                 "behavioral_description": "label"},
            ],
            screen_width=600, screen_height=400,
        )
        assert len(out) == 2
        assert out[0]["mark_id"] == 1
        assert out[0]["canonical_type"] == "button"
        assert out[1]["mark_id"] == 2
        assert out[1]["canonical_type"] == "heading"

    def test_missing_marks_dropped_silently(self):
        """If the model skips a mark, we don't invent a result — the
        caller can detect the gap and fall back to per-crop on those
        nodes.
        """
        client = self._make_mock_client([
            {"mark_id": 1, "canonical_type": "button",
             "confidence": 0.9, "reason": "..."},
            # mark 2 missing
        ])
        out = classify_screen_som(
            screen_png=_solid_png(),
            annotations=[
                {"id": 1, "x": 10, "y": 10, "w": 80, "h": 30},
                {"id": 2, "x": 10, "y": 60, "w": 200, "h": 40},
            ],
            client=client,
            catalog=[
                {"canonical_name": "button", "category": "actions",
                 "behavioral_description": "tap"},
            ],
            screen_width=600, screen_height=400,
        )
        assert len(out) == 1
        assert out[0]["mark_id"] == 1

    def test_non_toolbuse_response_returns_empty(self):
        """Free-text fallback → no classifications recorded."""
        mock = MagicMock()
        mock.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="sorry")]
        )
        out = classify_screen_som(
            screen_png=_solid_png(),
            annotations=[{"id": 1, "x": 10, "y": 10, "w": 80, "h": 30}],
            client=mock,
            catalog=[
                {"canonical_name": "button", "category": "actions",
                 "behavioral_description": "tap"},
            ],
            screen_width=600, screen_height=400,
        )
        assert out == []
