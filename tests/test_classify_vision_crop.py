"""Tests for classifier-v2 per-node image cropping.

Takes a full screen PNG + a node bbox and returns a cropped PNG with
the target node spotlighted (non-bbox region dimmed) and its edge
outlined in magenta. Same technique the review UI uses; moved into
`dd.classify_vision_crop` so both the review server + classifier
pipeline share one implementation.
"""

from __future__ import annotations

import base64
from io import BytesIO

import pytest
from PIL import Image

from dd.classify_vision_crop import (
    crop_node_with_spotlight,
    crops_for_nodes,
)


def _make_solid_png(width: int = 800, height: int = 600, rgb=(200, 200, 200)) -> bytes:
    """Fixture PNG of the given size + solid color."""
    img = Image.new("RGB", (width, height), rgb)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestCropNodeWithSpotlight:
    def test_basic_crop_is_bytes(self):
        screen = _make_solid_png(800, 600)
        out = crop_node_with_spotlight(
            screen_png=screen,
            node_x=100, node_y=100,
            node_width=200, node_height=150,
            screen_width=800, screen_height=600,
        )
        assert isinstance(out, bytes)
        # Output should be a valid PNG.
        img = Image.open(BytesIO(out))
        assert img.format == "PNG"

    def test_crop_contains_node_region(self):
        screen = _make_solid_png(800, 600)
        out = crop_node_with_spotlight(
            screen_png=screen,
            node_x=100, node_y=100,
            node_width=200, node_height=150,
            screen_width=800, screen_height=600,
        )
        img = Image.open(BytesIO(out))
        # Crop should be larger than the raw bbox (200x150) due to
        # padding, but smaller than the full screen (800x600) — or
        # upscaled if the bbox is tiny.
        w, h = img.size
        assert w >= 200
        assert h >= 150

    def test_tiny_bbox_upscaled(self):
        screen = _make_solid_png(1000, 1000)
        out = crop_node_with_spotlight(
            screen_png=screen,
            node_x=500, node_y=500,
            node_width=16, node_height=16,  # tiny
            screen_width=1000, screen_height=1000,
        )
        img = Image.open(BytesIO(out))
        w, h = img.size
        # Min-side is 400 per the impl — ensures tiny nodes are
        # visible to the vision model.
        assert min(w, h) >= 400

    def test_bbox_out_of_bounds_returns_screen(self):
        screen = _make_solid_png(800, 600)
        out = crop_node_with_spotlight(
            screen_png=screen,
            node_x=10000, node_y=10000,  # absolute coords; off-canvas
            node_width=16, node_height=16,
            screen_width=800, screen_height=600,
        )
        # Shouldn't crash; should return the original screen.
        assert isinstance(out, bytes)
        img = Image.open(BytesIO(out))
        assert img.format == "PNG"

    def test_scale_factor_applied(self):
        """When the rendered screen is 2x the Figma canvas (retina
        iPad), bbox coords must be scaled up.
        """
        # Rendered at 2x: 1600x1200 image represents a 800x600 canvas.
        screen = _make_solid_png(1600, 1200)
        out = crop_node_with_spotlight(
            screen_png=screen,
            node_x=100, node_y=100,       # canvas coords
            node_width=200, node_height=150,
            screen_width=800, screen_height=600,  # canvas dims
        )
        img = Image.open(BytesIO(out))
        w, h = img.size
        # Expected crop at 2x scale: (200+padding*2) * 2 = ~(560, 460)
        # or similar. Definitely > 400px.
        assert w > 400
        assert h > 300

    def test_spotlight_dims_non_bbox_region(self):
        """Pixels outside the bbox should be noticeably darker than
        pixels inside (spotlight effect).
        """
        # A bright-red screen so dimming is obvious in samples.
        screen = _make_solid_png(800, 600, rgb=(255, 0, 0))
        out = crop_node_with_spotlight(
            screen_png=screen,
            node_x=200, node_y=200,
            node_width=400, node_height=200,
            screen_width=800, screen_height=600,
            padding_px=40,
        )
        img = Image.open(BytesIO(out)).convert("RGB")
        w, h = img.size
        # Sample near the top-left corner (outside the bbox, in the
        # padded region). Should be dimmed. In-bbox center should be
        # near full red.
        corner = img.getpixel((2, 2))
        center = img.getpixel((w // 2, h // 2))
        # Dimmed corner red < bright center red.
        assert corner[0] < center[0], (
            f"expected corner red {corner[0]} < center red {center[0]}"
        )


class TestCropsForNodes:
    def test_empty_input(self):
        screens = {"s1:1": _make_solid_png(400, 300)}
        result = crops_for_nodes(screens, [])
        assert result == {}

    def test_single_crop(self):
        screens = {"s1:1": _make_solid_png(400, 300)}
        nodes = [{
            "key": "n1",
            "screen_figma_id": "s1:1",
            "node_x": 50, "node_y": 50,
            "node_width": 100, "node_height": 80,
            "screen_width": 400, "screen_height": 300,
        }]
        result = crops_for_nodes(screens, nodes)
        assert "n1" in result
        assert isinstance(result["n1"], bytes)

    def test_missing_screen_omits_node(self):
        screens = {"s1:1": _make_solid_png(400, 300)}
        nodes = [{
            "key": "n1",
            "screen_figma_id": "s2:1",  # not in screens dict
            "node_x": 0, "node_y": 0,
            "node_width": 10, "node_height": 10,
            "screen_width": 400, "screen_height": 300,
        }]
        result = crops_for_nodes(screens, nodes)
        assert result == {}

    def test_multiple_nodes_same_screen(self):
        screens = {"s1:1": _make_solid_png(400, 300)}
        nodes = [
            {"key": "a", "screen_figma_id": "s1:1",
             "node_x": 10, "node_y": 10,
             "node_width": 50, "node_height": 50,
             "screen_width": 400, "screen_height": 300},
            {"key": "b", "screen_figma_id": "s1:1",
             "node_x": 200, "node_y": 200,
             "node_width": 80, "node_height": 80,
             "screen_width": 400, "screen_height": 300},
        ]
        result = crops_for_nodes(screens, nodes)
        assert set(result.keys()) == {"a", "b"}
