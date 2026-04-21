"""Set-of-Marks (SoM) classifier path.

Experimental alternative to the per-node crop pipeline: render the
FULL screenshot with numeric labels over every classifiable region,
then ask Sonnet to classify each mark in one call. The model sees
siblings + parent context + exact relative geometry for free — the
signal our per-crop pass throws away.

References:
- Microsoft Set-of-Mark (arXiv 2310.11441, github.com/microsoft/SoM)
- WACV 2025 "Evaluating Multimodal VLM Prompting Strategies"
  (openaccess.thecvf.com/content/WACV2025W/LLVMAD): +7.45 pts grounding
  over plain prompting on Sonnet-class models.

Design goals for v1:
- No changes to existing PS/CS passes. This is a parallel path.
- Output format compatible with apply_vision_ps_results / apply_
  vision_cs_results once the caller maps mark_id → (screen_id, node_id).
- Enum-constrained canonical_type (carry forward from classify_llm
  constrained-decoding work).
- Rotation-aware AABB (share with crop_node_with_spotlight's logic).

Primary API:
    render_som_overlay(screen_png, annotations, *, screen_width,
                       screen_height) -> bytes
    build_som_tool_schema(catalog) -> dict
    classify_screen_som(screen_png, annotations, client, catalog, *,
                        screen_width, screen_height) -> list[dict]
"""

from __future__ import annotations

import base64
import copy
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from dd.classify_llm import build_canonical_type_enum
from dd.classify_vision_crop import rotated_aabb_dims


SOM_TOOL_NAME = "classify_marks"
_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 16384
_DEFAULT_CONFIDENCE = 0.7


_SOM_TOOL_SCHEMA_BASE: dict[str, Any] = {
    "name": SOM_TOOL_NAME,
    "description": (
        "Classify each numbered mark visible on the screenshot. "
        "Each mark is a colored outline + a numeric label placed at "
        "the corner of the target region. Your job is to pick ONE "
        "canonical UI component type per mark_id from the catalog's "
        "enum, cite the visual + contextual evidence, and assign a "
        "calibrated confidence. Every mark shown in the image must "
        "appear in the output exactly once. When a region's identity "
        "is genuinely unclear, use `unsure`."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "mark_id": {"type": "integer"},
                        "canonical_type": {"type": "string"},
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "One short sentence citing the visual "
                                "signals (shape, content, affordances "
                                "in the marked region) AND any context "
                                "from neighboring marks / siblings / "
                                "parent. Evidence-based; no speculation."
                            ),
                        },
                    },
                    "required": [
                        "mark_id", "canonical_type",
                        "confidence", "reason",
                    ],
                },
            },
        },
        "required": ["classifications"],
    },
}


def build_som_tool_schema(
    catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the SoM tool schema with ``canonical_type`` pinned to
    the catalog's enum (plus ``container`` + ``unsure``).
    """
    out = copy.deepcopy(_SOM_TOOL_SCHEMA_BASE)
    item_props = out["input_schema"]["properties"][
        "classifications"
    ]["items"]["properties"]
    item_props["canonical_type"] = {
        "type": "string",
        "enum": build_canonical_type_enum(catalog),
    }
    return out


def _try_load_label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Best-effort system font lookup for readable numeric labels.
    Falls back to PIL's bundled bitmap if no TrueType is available.
    """
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _label_size_for(bbox_w: float, bbox_h: float) -> int:
    """Label diameter scales with bbox size so tiny nodes get
    proportionally-smaller labels but never below a legible minimum.
    """
    # Tunable: 18px floor so a 16x16 node doesn't get a microscopic
    # label; 36px ceiling so huge cards don't get giant labels.
    return int(max(18, min(36, (bbox_w + bbox_h) * 0.08)))


def render_som_overlay(
    screen_png: bytes,
    annotations: list[dict[str, Any]],
    *,
    screen_width: float,
    screen_height: float,
) -> bytes:
    """Render the screenshot with each annotation's post-rotation AABB
    outlined and labeled with its ``id``. Annotations that fall
    entirely outside the screen are silently skipped.

    Each annotation dict takes:
      - ``id`` (int) — the numeric mark shown on the image
      - ``x``, ``y`` (canvas coords relative to screen origin)
      - ``w``, ``h`` (pre-rotation dimensions)
      - ``rotation`` (radians, optional; default 0)

    Returns the annotated PNG as bytes. The original PNG is returned
    unchanged when ``annotations`` is empty.
    """
    if not annotations:
        return screen_png

    img = Image.open(BytesIO(screen_png)).convert("RGBA")
    iw, ih = img.size
    scale_x = iw / screen_width if screen_width > 0 else 1.0
    scale_y = ih / screen_height if screen_height > 0 else 1.0

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    stroke_color = (255, 0, 180, 255)          # magenta
    halo_color = (255, 255, 255, 255)
    label_fill = (255, 0, 180, 230)            # semi-solid magenta disc
    label_text = (255, 255, 255, 255)

    halo_w = max(4, int(min(iw, ih) * 0.004))
    stroke_w = max(3, int(min(iw, ih) * 0.003))

    for ann in annotations:
        ann_id = ann.get("id")
        if not isinstance(ann_id, int):
            continue
        x = float(ann.get("x", 0))
        y = float(ann.get("y", 0))
        w = float(ann.get("w", 0))
        h = float(ann.get("h", 0))
        rot = float(ann.get("rotation") or 0.0)
        aabb_w, aabb_h = rotated_aabb_dims(w, h, rot)

        # In image pixels.
        nl = x * scale_x
        nt = y * scale_y
        nr = (x + aabb_w) * scale_x
        nb = (y + aabb_h) * scale_y
        if nr <= 0 or nb <= 0 or nl >= iw or nt >= ih:
            continue

        draw.rectangle((nl, nt, nr, nb), outline=halo_color, width=halo_w)
        draw.rectangle((nl, nt, nr, nb), outline=stroke_color, width=stroke_w)

        # Label: filled magenta disc at top-left corner with the
        # mark_id in white.
        lbl_size = _label_size_for(aabb_w * scale_x, aabb_h * scale_y)
        lbl_x = max(0, int(nl - lbl_size / 2))
        lbl_y = max(0, int(nt - lbl_size / 2))
        draw.ellipse(
            (lbl_x, lbl_y, lbl_x + lbl_size, lbl_y + lbl_size),
            fill=label_fill, outline=halo_color, width=2,
        )
        font = _try_load_label_font(max(10, int(lbl_size * 0.55)))
        text = str(ann_id)
        try:
            bbox = font.getbbox(text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except AttributeError:  # pragma: no cover
            tw, th = font.getsize(text)
        tx = lbl_x + (lbl_size - tw) / 2 - bbox[0]
        ty = lbl_y + (lbl_size - th) / 2 - bbox[1]
        draw.text((tx, ty), text, fill=label_text, font=font)

    composited = Image.alpha_composite(img, overlay).convert("RGB")
    out = BytesIO()
    composited.save(out, format="PNG")
    return out.getvalue()


def _extract_classifications_from_response(
    response: Any,
) -> list[dict[str, Any]]:
    """Pull the classifications array out of a tool_use response.
    Returns [] if the response isn't shaped as expected — no regex
    rescue paths.
    """
    if response is None or not getattr(response, "content", None):
        return []
    for block in response.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != SOM_TOOL_NAME:
            continue
        inp = getattr(block, "input", None)
        if isinstance(inp, dict):
            classifications = inp.get("classifications")
            if isinstance(classifications, list):
                return [c for c in classifications if isinstance(c, dict)]
        return []
    return []


def _build_som_prompt(
    annotations: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> str:
    from dd.classify_llm import _format_catalog_for_prompt
    catalog_block = _format_catalog_for_prompt(catalog) if catalog else ""
    mark_lines = []
    for ann in annotations:
        name = ann.get("name") or f"mark_{ann.get('id')}"
        parent = ann.get("parent_classified_as") or "(unknown)"
        node_type = ann.get("node_type") or "FRAME"
        extra = []
        if ann.get("sample_text"):
            extra.append(f'sample_text="{str(ann["sample_text"])[:60]}"')
        if ann.get("total_children"):
            extra.append(f"children={ann['total_children']}")
        extra_str = "; " + "; ".join(extra) if extra else ""
        mark_lines.append(
            f"  - mark_id={ann['id']}: name={name!r}, "
            f"type={node_type}, parent={parent}{extra_str}"
        )
    descriptions = "\n".join(mark_lines)
    n = len(annotations)
    return f"""You are classifying UI components on a mobile app screen. Each component has been outlined in magenta with a numbered label at its top-left corner.

## Canonical types (pick exactly one per mark)

Use the behavioral description to disambiguate. The UI component that matches the *function* shown in the marked region wins, not one that merely looks similar.
{catalog_block}

## Rules

1. **One canonical type per mark_id.** Prefer a specific catalog type when the evidence is strong. `container` and `unsure` are valid; prefer `unsure` only when the crop is truly ambiguous.

2. **Use siblings and parent context.** You can see the ENTIRE screen — exploit it. A mark inside a `bottom_nav`-shaped row is likely `navigation_row`. A mark sitting in a horizontal row of 3 similar elements is probably a `button_group` member, not a standalone `button`.

3. **Layout-slot names default to `container`.** Marks named `Left`, `Right`, `Center`, `Titles`, `Frame 267`, `Group 4` are almost always pure layout wrappers — classify as `container` unless the region shows unambiguous interactive or informational content.

4. **Wordmarks and logos → `image`.** A region named `wordmark`, `logo`, `brand`, `logomark` renders as an asset, not text.

5. **Empty-frame placeholders → `skeleton`.** Stacks of empty rounded rectangles, shimmer blocks, repeating grey placeholder rows.

6. **Reasons cite visual + structural signals.** One short sentence referencing shape, content, siblings, parent, or sample text.

7. **Confidence is calibrated.** 0.95+ for unambiguous, 0.85-0.94 for strong signal + minor alternative, 0.75-0.84 for real evidence + plausible alternative, below 0.75 → prefer `unsure`.

8. **Every mark_id below must appear in your output exactly once.** {n} marks total.

## Marks on this screen

Each mark below corresponds to one numbered label on the image.

{descriptions}

Return your classifications via the `{SOM_TOOL_NAME}` tool."""


def classify_screen_som(
    screen_png: bytes,
    annotations: list[dict[str, Any]],
    client: Any,
    catalog: list[dict[str, Any]],
    *,
    screen_width: float,
    screen_height: float,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> list[dict[str, Any]]:
    """End-to-end SoM classification for one screen.

    1. Render the annotated screenshot via ``render_som_overlay``.
    2. Build the enum-constrained tool schema.
    3. Call ``client.messages.create`` with the annotated image + prompt.
    4. Parse tool_use response → list of classification dicts keyed
       by ``mark_id``.

    Returns ``[]`` when there's nothing to classify. Missing marks in
    the response are dropped silently; the caller can detect the gap
    and fall back to per-crop.
    """
    if not annotations:
        return []

    annotated = render_som_overlay(
        screen_png=screen_png,
        annotations=annotations,
        screen_width=screen_width,
        screen_height=screen_height,
    )
    tool_schema = build_som_tool_schema(catalog)
    prompt = _build_som_prompt(annotations, catalog)

    content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(annotated).decode("utf-8"),
            },
        },
        {"type": "text", "text": prompt},
    ]

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": tool_schema["name"]},
        messages=[{"role": "user", "content": content}],
    )

    raw = _extract_classifications_from_response(response)
    out: list[dict[str, Any]] = []
    for c in raw:
        mid = c.get("mark_id")
        ctype = c.get("canonical_type")
        if not (isinstance(mid, int) and isinstance(ctype, str)):
            continue
        out.append({
            "mark_id": mid,
            "canonical_type": ctype,
            "confidence": float(c.get("confidence", _DEFAULT_CONFIDENCE)),
            "reason": str(c.get("reason", ""))[:500],
        })
    return out
