"""Structural-signature dedup for classifier v2.

Classifier v1 sends every unclassified node through LLM + vision
independently. With 6,233 LLM rows in the Dank corpus and strong
duplication (a given `Left` nav zone appears on 30+ iPad screens
with identical structure), that's 5-8x more API work than needed.

v2 clusters candidates by a structural signature BEFORE the API
call, classifies one representative per cluster, then propagates
the verdict to every sci row in the cluster.

The signature is a tuple chosen to be tight enough that two nodes
with identical signatures are genuinely the same pattern, and loose
enough that real duplicates dedup. Keys used:

- `name` — designer-assigned label. Normalised first: bare
  Figma auto-generated names (``Frame 292`` etc.) collapse to a
  single sentinel so copy-pasted frames with auto-numbers dedup.
  Human-authored names stay distinct.
- `node_type` — FRAME / INSTANCE / COMPONENT.
- `parent_classified_as` — the parent's canonical_type (None if
  unclassified). Distinguishes "Left inside header" from "Left
  inside toolbar".
- `child_type_dist` — multiset of child node types (order ignored).
  Catches structural-shape differences.
- `component_key` — Figma master key (INSTANCE nodes). Two instances
  of different masters are never the same pattern regardless of
  displayed name.
- `aspect_bucket` — tall / square / wide. Added 2026-04-20 after
  dedup collapsed 6x32 sliver + 64x64 square under name "Frame 373";
  vision's verdict on one didn't apply to the other.
- `size_bucket` — tiny / small / medium / large (max of width,
  height). Added same day for the Frame 362/366 case where 16x16
  icon and 108x108 avatar both hit `square` aspect but obviously
  aren't the same component.

`sample_text` is deliberately excluded from the key (dropped
2026-04-20): iPad-variant cards holding user-name data ("Alice" vs
"Bob") failed to collapse when text differed but structure matched.
Sample text is still carried in the candidate dict for the LLM
prompt; it's just no longer a grouping dimension.

None values in any position are normalised (None ≡ "") so
candidates with the same "nothing here" shape dedup.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any, Optional


_GENERIC_FRAME_PATTERN = re.compile(r"^Frame\s+\d+$")
_GENERIC_NAME_SENTINEL = "__frame_numbered__"


_ASPECT_TALL_MAX = 0.7
_ASPECT_WIDE_MIN = 1.4

_SIZE_TINY_MAX = 32
_SIZE_SMALL_MAX = 96
_SIZE_MEDIUM_MAX = 300


def aspect_bucket(
    width: Optional[float], height: Optional[float],
) -> str:
    """Coarse aspect-ratio bucket: tall | square | wide | unknown.

    Thresholds:
    - tall: width/height < 0.7 (catches 6x32 sliver)
    - square: 0.7 ≤ ratio ≤ 1.4 (caters for near-square icons/avatars)
    - wide: ratio > 1.4 (toolbar / bar patterns)
    """
    if not width or not height:
        return "unknown"
    try:
        w = float(width)
        h = float(height)
    except (TypeError, ValueError):
        return "unknown"
    if w <= 0 or h <= 0:
        return "unknown"
    ratio = w / h
    if ratio < _ASPECT_TALL_MAX:
        return "tall"
    if ratio > _ASPECT_WIDE_MIN:
        return "wide"
    return "square"


def size_bucket(
    width: Optional[float], height: Optional[float],
) -> str:
    """Coarse size bucket by max dimension: tiny | small | medium |
    large | unknown.

    Thresholds chosen to match the scale breakpoints in the Dank
    corpus:
    - tiny: max < 32 (inline icons / glyphs)
    - small: 32 ≤ max < 96 (icon buttons / small avatars)
    - medium: 96 ≤ max < 300 (cards / list rows / large avatars)
    - large: ≥ 300 (banners / hero images / sections)
    """
    if not width or not height:
        return "unknown"
    try:
        w = float(width)
        h = float(height)
    except (TypeError, ValueError):
        return "unknown"
    if w <= 0 or h <= 0:
        return "unknown"
    m = max(w, h)
    if m < _SIZE_TINY_MAX:
        return "tiny"
    if m < _SIZE_SMALL_MAX:
        return "small"
    if m < _SIZE_MEDIUM_MAX:
        return "medium"
    return "large"


def _normalize_name(name: str) -> str:
    """Collapse Figma auto-generated ``Frame <digits>`` names to a
    shared sentinel so copy-pasted frames dedup regardless of the
    auto-assigned number. Any name with a human-authored suffix or
    a different prefix passes through unchanged.
    """
    if _GENERIC_FRAME_PATTERN.match(name):
        return _GENERIC_NAME_SENTINEL
    return name


def dedup_key(candidate: dict[str, Any]) -> tuple:
    """Build the structural-signature tuple for a classifier candidate.

    ``candidate`` is the same shape ``_fetch_unclassified_for_screen``
    emits: a dict with keys ``name``, ``node_type``,
    ``parent_classified_as``, ``child_type_dist``, ``component_key``,
    ``width``, ``height`` (``sample_text`` is read from the dict by
    callers but deliberately NOT included in the key — see module
    docstring). Missing keys are treated as None / empty.
    """
    name = _normalize_name(candidate.get("name") or "")
    node_type = candidate.get("node_type") or ""
    parent_type = candidate.get("parent_classified_as") or ""
    children = candidate.get("child_type_dist") or {}
    component_key = candidate.get("component_key") or ""

    # Child-type distribution as a sorted tuple so dict insertion order
    # doesn't matter.
    children_tuple = tuple(sorted(children.items()))

    # Visual buckets — keep close-but-different geometry apart.
    a_bucket = aspect_bucket(
        candidate.get("width"), candidate.get("height"),
    )
    s_bucket = size_bucket(
        candidate.get("width"), candidate.get("height"),
    )

    return (
        name,
        node_type,
        parent_type,
        children_tuple,
        component_key,
        a_bucket,
        s_bucket,
    )


def group_candidates(
    candidates: list[dict[str, Any]],
) -> dict[tuple, list[dict[str, Any]]]:
    """Group candidates by `dedup_key`. First-seen candidate per group
    becomes the representative (stable across repeated runs).

    Returns an ``OrderedDict`` so iteration order matches candidate
    arrival order — lets a classify pass replay deterministically
    from the same input.
    """
    groups: OrderedDict[tuple, list[dict[str, Any]]] = OrderedDict()
    for c in candidates:
        key = dedup_key(c)
        groups.setdefault(key, []).append(c)
    return groups
