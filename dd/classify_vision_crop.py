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

Rotation handling (revised 2026-04-20 after empirical check against
``relative_transform`` on Frame 372): Figma reports ``(n.x, n.y)`` as
the **post-rotation AABB top-left** and ``(n.w, n.h)`` as the
**pre-rotation dimensions**. The AABB dimensions are
``(w*|cos|+h*|sin|, w*|sin|+h*|cos|)``. For the 716 nodes at exactly
±π/2 this reduces to a simple w/h swap; for the 18 at arbitrary angles
the AABB over-covers the rotated rect slightly, which is fine — the
spotlight shows the region where the element renders, axis-aligned.

Primary API:
    crop_node_with_spotlight(screen_png, node_x, node_y, node_width,
                             node_height, screen_width, screen_height,
                             *, padding_px=80, rotation=0.0,
                             bbox_inflate_px=6) -> bytes
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


def rotated_aabb_dims(
    w: float, h: float, rotation: float,
) -> tuple[float, float]:
    """Return the width/height of the axis-aligned bounding box that
    fully contains a ``w × h`` rectangle rotated by ``rotation`` radians.

    For axis-aligned rotations (0, ±π, ±π/2) this is either the
    original dims or a straight swap. For arbitrary angles the AABB
    is always ≥ the original — we accept the mild over-cover so the
    spotlight stays axis-aligned (easier to read at a glance than a
    rotated polygon).
    """
    if not rotation:
        return (float(w), float(h))
    cos_r = abs(math.cos(rotation))
    sin_r = abs(math.sin(rotation))
    return (
        w * cos_r + h * sin_r,
        w * sin_r + h * cos_r,
    )


def rotated_top_left_offset(
    w: float, h: float, rotation: float,
) -> tuple[float, float]:
    """Return ``(dx, dy)`` offset from the post-rotation AABB top-left
    to the corner of the rotated rectangle that was originally the
    pre-rotation top-left.

    For a rectangle ``(0, 0, w, h)`` rotated by ``rotation`` radians
    (CCW, Figma convention) around ``(0, 0)``, compute where the
    original ``(0, 0)`` corner lands relative to the AABB top-left.
    For ``rotation=0`` this is ``(0, 0)`` — the AABB TL IS the node TL.

    Used by SoM overlay to anchor the numeric label to the visible
    rotated corner instead of an empty AABB corner.
    """
    if not rotation:
        return (0.0, 0.0)
    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)
    corners = (
        (0.0, 0.0),
        (w * cos_r, w * sin_r),
        (w * cos_r - h * sin_r, w * sin_r + h * cos_r),
        (-h * sin_r, h * cos_r),
    )
    min_x = min(c[0] for c in corners)
    min_y = min(c[1] for c in corners)
    return (-min_x, -min_y)


def crop_node_with_spotlight(
    screen_png: bytes,
    node_x: float,
    node_y: float,
    node_width: float,
    node_height: float,
    screen_width: float,
    screen_height: float,
    *,
    padding_px: int = 80,
    min_side_px: int = 800,
    rotation: float = 0.0,
    bbox_inflate_px: float = 6,
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

    ``rotation`` (radians, default 0): Figma reports (n.x, n.y) as
    the POST-rotation AABB top-left and (n.w, n.h) as PRE-rotation
    dims. For rotated nodes we compute the AABB width/height via
    ``rotated_aabb_dims`` and draw the spotlight as an axis-aligned
    rect (which matches the rendered element for ±π/2, over-covers
    slightly for arbitrary angles — acceptable).

    ``bbox_inflate_px`` (default 6) is the MINIMUM margin between the
    element and the magenta stroke in Figma canvas units. The actual
    inflate is ``max(bbox_inflate_px, 5% of max(aabb_w, aabb_h))`` so
    tiny elements get the floor while large elements get a
    proportional margin that's actually visible — a flat 6-canvas-unit
    inflate on a 1024×1024 card is a 0.6% halo you can't see.
    """
    img = Image.open(BytesIO(screen_png)).convert("RGBA")
    iw, ih = img.size
    scale_x = iw / screen_width if screen_width > 0 else 1.0
    scale_y = ih / screen_height if screen_height > 0 else 1.0

    # Compute the post-rotation AABB dimensions. For axis-aligned
    # rotations this is either (w, h) or (h, w); for arbitrary angles
    # we over-cover slightly.
    aabb_w, aabb_h = rotated_aabb_dims(node_width, node_height, rotation)

    # AABB in Figma canvas coords, then scaled to image pixels.
    bbox_l_canvas = node_x
    bbox_t_canvas = node_y
    bbox_r_canvas = node_x + aabb_w
    bbox_b_canvas = node_y + aabb_h

    # Inflate outward — floor at bbox_inflate_px, scaled to 5% of the
    # element's longer side so big elements get a visible margin too.
    elem_max = max(aabb_w, aabb_h)
    infl = max(float(bbox_inflate_px), elem_max * 0.05)
    infl_x = infl
    infl_y = infl

    # Bbox in actual-image pixels (tight + inflated).
    nl = max(0, int((bbox_l_canvas - infl_x) * scale_x))
    nt = max(0, int((bbox_t_canvas - infl_y) * scale_y))
    nr = min(iw, int((bbox_r_canvas + infl_x) * scale_x))
    nb = min(ih, int((bbox_b_canvas + infl_y) * scale_y))

    # Adaptive padding — tiny nodes get extra surrounding context so
    # the reviewer (and VLM) can see where they sit relative to the
    # parent. For a 16x16 node the fixed ``padding_px=80`` becomes
    # an 80/16=5x context window; for a 500x100 node we add another
    # 50% of max dim so context doesn't shrink proportionally.
    elem_max_dim = max(aabb_w, aabb_h)
    adaptive_padding = max(padding_px, int(elem_max_dim * 0.5))

    # Crop bounds (padded, in image pixels).
    crop_left = max(0, int((bbox_l_canvas - adaptive_padding) * scale_x))
    crop_top = max(0, int((bbox_t_canvas - adaptive_padding) * scale_y))
    crop_right = min(iw, int((bbox_r_canvas + adaptive_padding) * scale_x))
    crop_bottom = min(ih, int((bbox_b_canvas + adaptive_padding) * scale_y))
    if crop_right <= crop_left or crop_bottom <= crop_top:
        # Bbox outside the screen image — return the full screen.
        return screen_png

    # Spotlight: dim everywhere; restore the (inflated) bbox to full
    # brightness.
    dim = Image.new("RGBA", img.size, (0, 0, 0, 140))
    dimmed = Image.alpha_composite(img, dim)
    if nr > nl and nb > nt:
        bbox_region = img.crop((nl, nt, nr, nb))
        dimmed.paste(bbox_region, (nl, nt))
    img = dimmed

    # Stroke + halo on the inflated bbox edge. Stroke weight scales
    # with crop size so thin strokes don't disappear after upscaling.
    raw_w = crop_right - crop_left
    raw_h = crop_bottom - crop_top
    draw = ImageDraw.Draw(img)
    halo = (255, 255, 255, 255)
    stroke = (255, 0, 180, 255)  # magenta
    halo_w = max(6, int(min(raw_w, raw_h) * 0.012))
    stroke_w = max(4, int(min(raw_w, raw_h) * 0.008))
    draw.rectangle((nl, nt, nr, nb), outline=halo, width=halo_w)
    draw.rectangle((nl, nt, nr, nb), outline=stroke, width=stroke_w)

    cropped = img.crop((crop_left, crop_top, crop_right, crop_bottom))

    # Upscale to ``min_side_px`` so the vision model (and human
    # reviewer) have legible pixels. 800px default from the 2026-04-20
    # crop-quality review; 400px was producing blurry results on
    # 16x16 source crops even at scale=4 screenshots.
    cw, ch = cropped.size
    smaller = min(cw, ch)
    if smaller < min_side_px:
        factor = min_side_px / smaller
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
