"""Checkerboard background compositor for self-hidden node renders.

When a self-hidden Figma node is made visible via the plugin
render-toggle and the resulting export carries transparent regions
(the dialog has alpha, or its area extends past the opaque screen
content), the adjudicator UI renders those regions as black — the
default browser canvas colour. Black backgrounds tank VLM confidence
on dark-themed UI and make human adjudication harder.

Compositing onto a grey checkerboard base: opaque regions pass
through unchanged, transparent regions expose the checker. Both the
VLM and a human reviewer can immediately tell "this is transparency"
without confusing it for a design choice.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image


_DEFAULT_CELL_PX = 16
_DEFAULT_COLOR_A = (210, 210, 210)  # light grey
_DEFAULT_COLOR_B = (170, 170, 170)  # darker grey — ~40 unit gap, readable
                                     # against both white and dark UI palettes


def _make_checker_base(
    size: tuple[int, int],
    *,
    cell_px: int,
    color_a: tuple[int, int, int],
    color_b: tuple[int, int, int],
) -> Image.Image:
    """Build a checkerboard RGBA image at the requested size. Cells
    alternate ``color_a`` and ``color_b`` starting with A at (0, 0).
    """
    w, h = size
    base = Image.new("RGBA", size, color_a + (255,))
    # Draw B cells one cell at a time — stripe fill is cheap for the
    # sizes we care about (<2K × <2K).
    for cy in range(0, h, cell_px):
        for cx in range(0, w, cell_px):
            cell_index = (cx // cell_px) + (cy // cell_px)
            if cell_index % 2 == 0:
                continue
            x2 = min(cx + cell_px, w)
            y2 = min(cy + cell_px, h)
            cell = Image.new(
                "RGBA", (x2 - cx, y2 - cy), color_b + (255,),
            )
            base.paste(cell, (cx, cy))
    return base


def composite_on_checkerboard(
    png: bytes,
    *,
    cell_px: int = _DEFAULT_CELL_PX,
    color_a: tuple[int, int, int] = _DEFAULT_COLOR_A,
    color_b: tuple[int, int, int] = _DEFAULT_COLOR_B,
) -> bytes:
    """Composite ``png`` onto a grey checkerboard base. Transparent
    regions in the source expose the checker; opaque regions pass
    through unchanged. Alpha is blended in the standard PIL way.

    Returns PNG-encoded bytes in RGB mode (no alpha) since the
    composited image is fully opaque by construction.
    """
    src = Image.open(BytesIO(png)).convert("RGBA")
    base = _make_checker_base(
        src.size, cell_px=cell_px, color_a=color_a, color_b=color_b,
    )
    composited = Image.alpha_composite(base, src).convert("RGB")
    out = BytesIO()
    composited.save(out, format="PNG")
    return out.getvalue()
