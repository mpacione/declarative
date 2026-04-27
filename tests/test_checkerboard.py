"""Tests for the checkerboard compositor.

Transparent PNG regions (from exportAsync on a node with no opaque
ancestor scrim) otherwise render on the viewer's default background
— black in the adjudicator, hard to discern.

The compositor overlays the PNG onto a grey checkerboard base,
preserving opaque pixels and exposing transparent regions as a
visible checker pattern.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from dd.checkerboard import composite_on_checkerboard


def _rgba_png(w: int, h: int, rgba: tuple[int, int, int, int]) -> bytes:
    img = Image.new("RGBA", (w, h), rgba)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestCompositeOnCheckerboard:
    def test_fully_opaque_png_unchanged(self):
        """An all-opaque PNG should return bytes that decode to the
        original pixels — checkerboard is purely under transparent
        regions.
        """
        src = _rgba_png(32, 32, (120, 200, 60, 255))
        out = composite_on_checkerboard(src)
        img = Image.open(BytesIO(out)).convert("RGBA")
        assert img.size == (32, 32)
        # Centre pixel: opaque green stays green.
        px = img.getpixel((16, 16))
        assert px[:3] == (120, 200, 60)

    def test_fully_transparent_shows_both_checker_colors(self):
        """A fully-transparent PNG should render the checker pattern.
        With default cell_px=16, a 32x32 image has 4 cells → two of
        each checker colour.
        """
        src = _rgba_png(32, 32, (0, 0, 0, 0))
        out = composite_on_checkerboard(src)
        img = Image.open(BytesIO(out)).convert("RGB")
        colors = {img.getpixel((x, y)) for x in range(32) for y in range(32)}
        # Expect at least 2 distinct colours (the checker squares).
        assert len(colors) >= 2, f"only got colours {colors}"

    def test_returns_png_bytes(self):
        src = _rgba_png(16, 16, (0, 0, 0, 128))
        out = composite_on_checkerboard(src)
        assert isinstance(out, bytes)
        img = Image.open(BytesIO(out))
        assert img.format == "PNG"

    def test_checker_cell_size_configurable(self):
        """cell_px=8 on a 16x16 transparent PNG gives 4 cells instead
        of 1 (which would be the default at cell_px=16 → 1 cell fills
        the whole image).
        """
        src = _rgba_png(16, 16, (0, 0, 0, 0))
        small = composite_on_checkerboard(src, cell_px=8)
        img = Image.open(BytesIO(small)).convert("RGB")
        colors = {img.getpixel((x, y)) for x in range(16) for y in range(16)}
        assert len(colors) >= 2

    def test_preserves_image_dimensions(self):
        src = _rgba_png(137, 253, (100, 100, 100, 200))
        out = composite_on_checkerboard(src)
        img = Image.open(BytesIO(out))
        assert img.size == (137, 253)

    def test_alpha_blending_for_translucent_source(self):
        """Half-alpha grey source (128/255) over a visible checker
        should produce a pixel that's somewhere between the source
        colour and the underlying checker colour — not a pure
        source colour and not a pure checker colour.
        """
        src = _rgba_png(32, 32, (255, 0, 0, 128))  # half-alpha red
        out = composite_on_checkerboard(src)
        img = Image.open(BytesIO(out)).convert("RGB")
        # Somewhere in the image, the red channel should be <255
        # (because it's blended with a lighter checker cell).
        reds = [img.getpixel((x, y))[0] for x in range(32) for y in range(32)]
        assert min(reds) < 255, "expected some alpha blending below pure red"
