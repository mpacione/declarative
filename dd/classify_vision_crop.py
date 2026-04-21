"""Per-node image cropping + spotlight for classifier v2.

Same technique the review UI uses (`scripts/m7_review_server.py`),
extracted here so the classifier pipeline can send focused,
target-highlighted crops to the vision model instead of a full screen
+ bbox list. The vision model then spends its attention budget on
the actual classification target instead of visually scanning a
1.6-megapixel image for a 16×16 region.

The pattern — dim-everything-except-target + colored stroke — is
from Google Research's Spotlight paper (arXiv 2209.14927) for
mobile-UI VLM tasks.

Rotation handling (added 2026-04-20): 734 classifiable nodes in the
Dank corpus have non-zero rotation (mostly ±π/2). Figma's Plugin API
reports ``width``/``height`` as PRE-rotation dimensions — a 32×6
horizontal bar rotated 90° is stored as ``(w=6, h=32, rotation=π/2)``.
When ``rotation`` is non-zero, the spotlight draws the rotated polygon
and the dim mask is polygonal; otherwise behavior is identical to the
pre-rotation path.

Primary API:
    crop_node_with_spotlight(screen_png, node_x, node_y, node_width,
                             node_height, screen_width, screen_height,
                             *, padding_px=40, rotation=0.0) -> bytes
    crops_for_nodes(screens: dict[str, bytes],
                    nodes: list[dict]) -> dict[key, bytes]

``screens`` maps figma_node_id → full-screen PNG bytes (typically
cached per-screen; one REST fetch covers N nodes from that screen).
``nodes`` is a list of dicts with `key`, `screen_figma_id`, and the
bbox + screen-dims the crop function needs.
"""

from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw


def _rotated_corners(
    x: float, y: float, w: float, h: float, rotation: float,
) -> list[tuple[float, float]]:
    """Return the 4 corners of a rectangle rotated around its center,
    in the rectangle's parent coordinate space. Order: TL, TR, BR, BL
    (pre-rotation order preserved so polygon winds clockwise).

    Figma Plugin API's ``rotation`` is in radians. Positive rotation is
    counter-clockwise in Plugin coordinates. Center-origin is the
    convention that matches the visible AABB for our rotated-90°
    Frame 372 fixture.
    """
    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)
    cx, cy = x + w / 2.0, y + h / 2.0
    # Corners relative to center (TL, TR, BR, BL).
    local = [
        (-w / 2.0, -h / 2.0),
        (w / 2.0, -h / 2.0),
        (w / 2.0, h / 2.0),
        (-w / 2.0, h / 2.0),
    ]
    return [
        (cx + lx * cos_r - ly * sin_r, cy + lx * sin_r + ly * cos_r)
        for lx, ly in local
    ]


def crop_node_with_spotlight(
    screen_png: bytes,
    node_x: float,
    node_y: float,
    node_width: float,
    node_height: float,
    screen_width: float,
    screen_height: float,
    *,
    padding_px: int = 40,
    rotation: float = 0.0,
) -> bytes:
    """Return a PNG of the screen cropped to the node's bbox + padding,
    with pixels outside the bbox dimmed (~45% brightness) and the
    bbox edge stroked in magenta with a white halo.

    ``node_x`` / ``node_y`` are screen-relative Figma canvas
    coordinates (subtract the screen root's x/y before calling if
    you have absolute canvas coords). ``screen_width`` /
    ``screen_height`` are the Figma canvas dimensions; the rendered
    PNG may be at 2x density for retina iPads, and we scale the
    bbox by the actual/canvas ratio.

    ``rotation`` (radians, default 0) rotates the bbox around its
    center. Non-zero values draw a polygon highlight matching the
    actual rendered shape instead of an axis-aligned rectangle.
    """
    img = Image.open(BytesIO(screen_png)).convert("RGBA")
    iw, ih = img.size
    scale_x = iw / screen_width if screen_width > 0 else 1.0
    scale_y = ih / screen_height if screen_height > 0 else 1.0

    # For non-rotated nodes, behavior is unchanged.
    if not rotation:
        corners = [
            (node_x, node_y),
            (node_x + node_width, node_y),
            (node_x + node_width, node_y + node_height),
            (node_x, node_y + node_height),
        ]
    else:
        corners = _rotated_corners(
            node_x, node_y, node_width, node_height, rotation,
        )

    # Corners in image pixels (for polygon drawing + mask).
    img_corners = [(c[0] * scale_x, c[1] * scale_y) for c in corners]
    xs = [p[0] for p in img_corners]
    ys = [p[1] for p in img_corners]
    # Post-rotation AABB in image pixels.
    nl = max(0, int(min(xs)))
    nt = max(0, int(min(ys)))
    nr = min(iw, int(max(xs)))
    nb = min(ih, int(max(ys)))

    # Crop bounds (padded AABB).
    crop_left = max(0, int(min(xs) - padding_px * scale_x))
    crop_top = max(0, int(min(ys) - padding_px * scale_y))
    crop_right = min(iw, int(max(xs) + padding_px * scale_x))
    crop_bottom = min(ih, int(max(ys) + padding_px * scale_y))
    if crop_right <= crop_left or crop_bottom <= crop_top:
        # Bbox outside the screen image — return the full screen.
        return screen_png

    # Spotlight: dim everywhere; restore the bbox (or rotated polygon)
    # at full brightness using a polygon mask.
    dim = Image.new("RGBA", img.size, (0, 0, 0, 140))
    dimmed = Image.alpha_composite(img, dim)
    if nr > nl and nb > nt:
        # Build a polygon mask so rotated boxes don't leak background
        # from the AABB corners into the "bright" region.
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).polygon(img_corners, fill=255)
        dimmed.paste(img, (0, 0), mask)
    img = dimmed

    # Draw stroke + halo on the polygon edge (rotated correctly).
    draw = ImageDraw.Draw(img)
    halo = (255, 255, 255, 255)
    stroke = (255, 0, 180, 255)  # magenta
    halo_w = 5
    stroke_w = 3
    closed_poly = img_corners + [img_corners[0]]
    draw.line(closed_poly, fill=halo, width=halo_w, joint="curve")
    draw.line(closed_poly, fill=stroke, width=stroke_w, joint="curve")

    cropped = img.crop((crop_left, crop_top, crop_right, crop_bottom))

    # Upscale tiny crops so the vision model has legible pixels to
    # look at. 400px min-side is empirical — enough detail for most
    # small-button classification tasks.
    min_side = 400
    cw, ch = cropped.size
    smaller = min(cw, ch)
    if smaller < min_side:
        factor = min_side / smaller
        cropped = cropped.resize(
            (int(cw * factor), int(ch * factor)),
            Image.Resampling.LANCZOS,
        )

    out = BytesIO()
    cropped.save(out, format="PNG")
    return out.getvalue()


def crops_for_nodes(
    screens: dict[str, bytes],
    nodes: list[dict[str, Any]],
) -> dict[Any, bytes]:
    """Produce a `{key: png_bytes}` map for a batch of nodes.

    ``screens`` maps figma_node_id → full-screen PNG (typically cached
    per-screen; one REST fetch covers N nodes from that screen).

    Each ``nodes`` entry is a dict with:
    - ``key`` — opaque identifier the caller uses to map results back.
    - ``screen_figma_id`` — key into ``screens``.
    - ``node_x``, ``node_y``, ``node_width``, ``node_height``
      (screen-relative canvas coords).
    - ``screen_width``, ``screen_height`` (Figma canvas dims).

    Nodes whose screen isn't in ``screens`` are silently skipped —
    caller should log. Crop failures (PIL error, bad bbox) are also
    skipped.
    """
    out: dict[Any, bytes] = {}
    for n in nodes:
        screen_png = screens.get(n.get("screen_figma_id"))
        if screen_png is None:
            continue
        try:
            cropped = crop_node_with_spotlight(
                screen_png=screen_png,
                node_x=float(n["node_x"]),
                node_y=float(n["node_y"]),
                node_width=float(n["node_width"]),
                node_height=float(n["node_height"]),
                screen_width=float(n["screen_width"]),
                screen_height=float(n["screen_height"]),
            )
        except Exception:
            continue
        out[n["key"]] = cropped
    return out
