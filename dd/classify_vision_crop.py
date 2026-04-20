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

Primary API:
    crop_node_with_spotlight(screen_png, node_x, node_y, node_width,
                             node_height, screen_width, screen_height,
                             *, padding_px=40) -> bytes
    crops_for_nodes(screens: dict[str, bytes],
                    nodes: list[dict]) -> dict[key, bytes]

``screens`` maps figma_node_id → full-screen PNG bytes (typically
cached per-screen; one REST fetch covers N nodes from that screen).
``nodes`` is a list of dicts with `key`, `screen_figma_id`, and the
bbox + screen-dims the crop function needs.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw


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
    """
    img = Image.open(BytesIO(screen_png)).convert("RGBA")
    iw, ih = img.size
    scale_x = iw / screen_width if screen_width > 0 else 1.0
    scale_y = ih / screen_height if screen_height > 0 else 1.0

    # Node bbox in actual-image pixels.
    nl = max(0, int(node_x * scale_x))
    nt = max(0, int(node_y * scale_y))
    nr = min(iw, int((node_x + node_width) * scale_x))
    nb = min(ih, int((node_y + node_height) * scale_y))

    # Crop bounds (padded).
    crop_left = max(0, int((node_x - padding_px) * scale_x))
    crop_top = max(0, int((node_y - padding_px) * scale_y))
    crop_right = min(iw, int((node_x + node_width + padding_px) * scale_x))
    crop_bottom = min(ih, int((node_y + node_height + padding_px) * scale_y))
    if crop_right <= crop_left or crop_bottom <= crop_top:
        # Bbox outside the screen image — return the full screen.
        return screen_png

    # Spotlight: dim everywhere; restore the bbox at full brightness.
    dim = Image.new("RGBA", img.size, (0, 0, 0, 140))
    dimmed = Image.alpha_composite(img, dim)
    if nr > nl and nb > nt:
        bbox_region = img.crop((nl, nt, nr, nb))
        dimmed.paste(bbox_region, (nl, nt))
    img = dimmed

    # Draw stroke + halo on the bbox edge.
    draw = ImageDraw.Draw(img)
    halo = (255, 255, 255, 255)
    stroke = (255, 0, 180, 255)  # magenta
    halo_w = 5
    stroke_w = 3
    draw.rectangle(
        (nl - halo_w, nt - halo_w, nr + halo_w, nb + halo_w),
        outline=halo, width=halo_w,
    )
    draw.rectangle(
        (nl, nt, nr, nb), outline=stroke, width=stroke_w,
    )

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
