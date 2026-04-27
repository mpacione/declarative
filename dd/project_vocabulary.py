"""C5 — project-vocabulary snapping for synth-gen demo.

Per docs/plan-synth-gen-demo.md C5: extract top-K most-frequent
literal values per dimension from a project DB, then snap untokenized
IR literals to their nearest project-canonical value. Keeps generated
variants on-brand by anchoring to the source design system's actual
color/radius/spacing/fontSize palette.

Codex 5.5 round-13 lock: post-IR transform (NOT a fourth mode),
gated behind ``--use-project-vocab`` (default OFF), reuses
``dd.color``, ``dd.cluster_misc``, ``dd.cluster_spacing``.

Pipeline integration (option (c)): ``_render_session_to_figma``
calls :func:`build_project_vocabulary` then
:func:`snap_ir_to_vocabulary` on the spec produced by ``generate_ir``
BEFORE ``_compress_to_l3_impl`` consumes it. Same variant rendered
with vs. without ``--use-project-vocab`` produces visibly different
output. Session DB is untouched.

Scope: this snaps values in ``spec["elements"][eid]["visual"]`` /
``["layout"]`` / ``["style"]``. LLM ``set @x fill=#XXXXXX`` edits
that land in the applied L3 doc's ``head.properties`` are NOT
touched here — that's the immutable-AST tree-walk, deferred. Most
Mode 2 emissions and all Mode 1 extracted values flow through the
spec, so spec-only snapping is the dominant lever.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from typing import Any

from dd.color import hex_to_oklch, oklch_delta_e


# ---------------------------------------------------------------------------
# Caps per dimension (Codex round-13 lock)
# ---------------------------------------------------------------------------

_CAP_CHROMATIC_FILLS = 16
_CAP_NEUTRAL_FILLS = 8
_CAP_RADII = 8
_CAP_SPACINGS = 12
_CAP_FONT_SIZES = 8

# OKLCH chroma threshold splitting chromatic vs neutral colors.
# C > 0.05 = chromatic (brand purple, red accents); C <= 0.05 =
# neutral (gray/white/black family).
_CHROMA_THRESHOLD = 0.05


# ---------------------------------------------------------------------------
# Snap thresholds (Codex round-13 lock)
# ---------------------------------------------------------------------------

# Color: OKLCH ΔE ≤ 10 (perceptual difference scale, JND ~2.0)
_COLOR_DELTA_E_THRESHOLD = 10.0
# Chromatic: also require hue Δ ≤ 24°
_COLOR_HUE_THRESHOLD = 24.0
# Neutral: require lightness Δ ≤ 0.10
_COLOR_LIGHTNESS_THRESHOLD = 0.10

# Radii: abs Δ ≤ 2px OR rel Δ ≤ 20%
_RADIUS_ABS_THRESHOLD = 2.0
_RADIUS_REL_THRESHOLD = 0.20

# Spacing: abs Δ ≤ 3px OR rel Δ ≤ 20%
_SPACING_ABS_THRESHOLD = 3.0
_SPACING_REL_THRESHOLD = 0.20

# Font size: abs Δ ≤ 2px OR rel Δ ≤ 12%
_FONT_SIZE_ABS_THRESHOLD = 2.0
_FONT_SIZE_REL_THRESHOLD = 0.12


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectVocabulary:
    """Frequency-based top-K canonical values per dimension.

    Caps: 16 chromatic / 8 neutral fills, 8 radii, 12 spacings,
    8 font_sizes (Codex round-13 lock).
    """
    chromatic_fills: tuple[str, ...]
    neutral_fills: tuple[str, ...]
    radii: tuple[float, ...]
    spacings: tuple[float, ...]
    font_sizes: tuple[float, ...]


@dataclass(frozen=True)
class SnapReport:
    """Per-dimension snap counters; printed to stderr per render."""
    fills_snapped: int
    radii_snapped: int
    spacing_snapped: int
    font_size_snapped: int

    def total(self) -> int:
        return (
            self.fills_snapped + self.radii_snapped
            + self.spacing_snapped + self.font_size_snapped
        )


# ---------------------------------------------------------------------------
# Vocabulary extraction
# ---------------------------------------------------------------------------


def _is_chromatic(hex_str: str) -> bool:
    """Return True if the hex color has OKLCH chroma > threshold."""
    try:
        _, chroma, _ = hex_to_oklch(hex_str)
        return chroma > _CHROMA_THRESHOLD
    except Exception:  # noqa: BLE001
        # Conservative default: treat unparseable hex as neutral so it
        # doesn't dilute the chromatic top-K.
        return False


def _normalize_hex(hex_str: str) -> str | None:
    """Return uppercase 6-digit hex with # prefix; None if invalid.

    Strips alpha (8-digit hex) — vocabulary is RGB-only since OKLCH
    encodes only perceptual color, not transparency.
    """
    if not isinstance(hex_str, str) or not hex_str.startswith("#"):
        return None
    digits = hex_str[1:]
    if len(digits) == 3:
        # Expand short form
        digits = "".join(c * 2 for c in digits)
    elif len(digits) == 8:
        # Strip alpha
        digits = digits[:6]
    if len(digits) != 6:
        return None
    try:
        int(digits, 16)
    except ValueError:
        return None
    return f"#{digits.upper()}"


def _figma_color_to_hex(color: dict) -> str | None:
    """Convert a Figma SOLID paint color dict to a normalized hex.
    Returns None if the dict is malformed.
    """
    try:
        r = max(0.0, min(1.0, float(color.get("r", 0.0))))
        g = max(0.0, min(1.0, float(color.get("g", 0.0))))
        b = max(0.0, min(1.0, float(color.get("b", 0.0))))
    except (TypeError, ValueError):
        return None
    return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"


def _extract_fill_hexes(
    conn: sqlite3.Connection, file_id: int,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Walk every node's fills JSON, count visible-SOLID hex usage,
    split into chromatic vs neutral by OKLCH chroma, return top-K each.
    """
    counter: Counter[str] = Counter()

    cursor = conn.execute(
        "SELECT n.fills FROM nodes n "
        "JOIN screens s ON n.screen_id = s.id "
        "WHERE s.file_id = ? AND n.fills IS NOT NULL "
        "AND n.fills != '[]' AND n.fills != ''",
        (file_id,),
    )
    for row in cursor.fetchall():
        raw = row[0] if not hasattr(row, "keys") else row["fills"]
        try:
            fills = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(fills, list):
            continue
        for fill in fills:
            if not isinstance(fill, dict):
                continue
            if fill.get("visible") is False:
                continue
            if fill.get("type") != "SOLID":
                continue
            hex_str = _figma_color_to_hex(fill.get("color") or {})
            if hex_str is None:
                continue
            counter[hex_str] += 1

    # Sort by frequency desc, then by hex asc for determinism.
    sorted_hexes = sorted(
        counter.items(), key=lambda x: (-x[1], x[0]),
    )

    chromatic: list[str] = []
    neutral: list[str] = []
    for hex_str, _count in sorted_hexes:
        if _is_chromatic(hex_str):
            if len(chromatic) < _CAP_CHROMATIC_FILLS:
                chromatic.append(hex_str)
        else:
            if len(neutral) < _CAP_NEUTRAL_FILLS:
                neutral.append(hex_str)
        if (
            len(chromatic) >= _CAP_CHROMATIC_FILLS
            and len(neutral) >= _CAP_NEUTRAL_FILLS
        ):
            break

    return tuple(chromatic), tuple(neutral)


def _extract_radii(
    conn: sqlite3.Connection, file_id: int,
) -> tuple[float, ...]:
    """Top-K corner radii by usage_count from cluster_misc census."""
    from dd.cluster_misc import query_radius_census

    rows = query_radius_census(conn, file_id)
    # Deduplicate after rounding to avoid noise (14.5697... vs 15)
    bucket: Counter[float] = Counter()
    for row in rows:
        try:
            value = float(row["resolved_value"])
        except (TypeError, ValueError, KeyError):
            continue
        if value <= 0:
            continue
        rounded = round(value, 1)
        bucket[rounded] += int(row.get("usage_count", 0))

    sorted_values = sorted(
        bucket.items(), key=lambda x: (-x[1], x[0]),
    )
    return tuple(v for v, _c in sorted_values[:_CAP_RADII])


def _extract_spacings(
    conn: sqlite3.Connection, file_id: int,
) -> tuple[float, ...]:
    """Top-K padding + itemSpacing values combined."""
    from dd.cluster_spacing import query_spacing_census

    rows = query_spacing_census(conn, file_id)
    bucket: Counter[float] = Counter()
    for row in rows:
        try:
            value = float(row["resolved_value"])
        except (TypeError, ValueError, KeyError):
            continue
        if value <= 0:
            continue
        rounded = round(value, 1)
        bucket[rounded] += int(row.get("usage_count", 0))

    sorted_values = sorted(
        bucket.items(), key=lambda x: (-x[1], x[0]),
    )
    return tuple(v for v, _c in sorted_values[:_CAP_SPACINGS])


def _extract_font_sizes(
    conn: sqlite3.Connection, file_id: int,
) -> tuple[float, ...]:
    """Top-K font sizes from nodes table by frequency."""
    cursor = conn.execute(
        "SELECT n.font_size, COUNT(*) AS c "
        "FROM nodes n "
        "JOIN screens s ON n.screen_id = s.id "
        "WHERE s.file_id = ? AND n.font_size IS NOT NULL "
        "GROUP BY n.font_size "
        "ORDER BY c DESC, n.font_size ASC",
        (file_id,),
    )
    out: list[float] = []
    for row in cursor.fetchall():
        try:
            value = float(row[0] if not hasattr(row, "keys") else row["font_size"])
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        out.append(value)
        if len(out) >= _CAP_FONT_SIZES:
            break
    return tuple(out)


def build_project_vocabulary(
    conn: sqlite3.Connection, file_id: int = 1,
) -> ProjectVocabulary:
    """Extract top-K canonical literal values per dimension via
    frequency analysis on the project DB.

    Args:
        conn: sqlite3 connection to a project DB extracted by ``dd
              extract`` — must have nodes/screens/files tables and
              ``node_token_bindings`` populated for radii/spacing.
        file_id: file identifier (default 1, since ``dd extract``
                 single-file runs).

    Returns:
        Frozen :class:`ProjectVocabulary` with per-dimension top-K.

    Raises:
        ValueError: if ``file_id`` doesn't exist in the ``files`` table.
    """
    file_row = conn.execute(
        "SELECT id FROM files WHERE id = ?", (file_id,),
    ).fetchone()
    if file_row is None:
        raise ValueError(
            f"build_project_vocabulary: file_id={file_id} not found in "
            f"files table; pass --project-db pointing to a populated "
            f"extracted DB."
        )

    chromatic, neutral = _extract_fill_hexes(conn, file_id)
    radii = _extract_radii(conn, file_id)
    spacings = _extract_spacings(conn, file_id)
    font_sizes = _extract_font_sizes(conn, file_id)

    return ProjectVocabulary(
        chromatic_fills=chromatic,
        neutral_fills=neutral,
        radii=radii,
        spacings=spacings,
        font_sizes=font_sizes,
    )


# ---------------------------------------------------------------------------
# Snap helpers
# ---------------------------------------------------------------------------


def _is_token_ref(value: Any) -> bool:
    """Return True if ``value`` is a token reference like
    ``"{color.brand.primary}"`` — must be left untouched."""
    return isinstance(value, str) and value.startswith("{")


def _hue_distance(h1: float, h2: float) -> float:
    """Shortest angular distance between two hues (degrees, 0-180)."""
    diff = abs(h1 - h2) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return diff


def _snap_color_hex(
    hex_value: str, vocab: ProjectVocabulary,
) -> str | None:
    """Find the nearest vocab color within thresholds. Return the
    canonical hex on snap, or None if no candidate is close enough.

    Rules per Codex round-13:
      - Same chromatic-vs-neutral category as input.
      - Chromatic: ΔE ≤ 10 AND hue Δ ≤ 24°.
      - Neutral:   ΔE ≤ 10 AND lightness Δ ≤ 0.10.
    """
    normalized = _normalize_hex(hex_value)
    if normalized is None:
        return None
    if normalized == hex_value.upper():
        # Already exact — but still check against vocab to canonicalize.
        pass

    try:
        L_in, C_in, h_in = hex_to_oklch(normalized)
    except Exception:  # noqa: BLE001
        return None

    chromatic_in = C_in > _CHROMA_THRESHOLD
    candidates = (
        vocab.chromatic_fills if chromatic_in else vocab.neutral_fills
    )
    if not candidates:
        return None

    best_hex: str | None = None
    best_delta = float("inf")
    for cand in candidates:
        try:
            cand_oklch = hex_to_oklch(cand)
        except Exception:  # noqa: BLE001
            continue
        L_c, C_c, h_c = cand_oklch
        delta_e = oklch_delta_e((L_in, C_in, h_in), cand_oklch)
        if delta_e > _COLOR_DELTA_E_THRESHOLD:
            continue
        if chromatic_in:
            if _hue_distance(h_in, h_c) > _COLOR_HUE_THRESHOLD:
                continue
        else:
            if abs(L_in - L_c) > _COLOR_LIGHTNESS_THRESHOLD:
                continue
        if delta_e < best_delta:
            best_delta = delta_e
            best_hex = cand

    return best_hex


def _snap_numeric(
    value: float,
    candidates: tuple[float, ...],
    *,
    abs_threshold: float,
    rel_threshold: float,
) -> float | None:
    """Find the nearest vocab numeric within abs OR rel thresholds.
    Return the canonical value on snap, or None.
    """
    if not candidates or value <= 0:
        return None
    best: float | None = None
    best_diff = float("inf")
    for cand in candidates:
        diff = abs(value - cand)
        rel = diff / value if value > 0 else float("inf")
        if diff <= abs_threshold or rel <= rel_threshold:
            if diff < best_diff:
                best_diff = diff
                best = cand
    return best


# ---------------------------------------------------------------------------
# Snap walker
# ---------------------------------------------------------------------------


def _snap_fills_list(
    fills: list, vocab: ProjectVocabulary,
) -> tuple[list, int]:
    """Snap solid fills' colors. Returns (new_fills, snap_count).

    Skips:
      - non-dict entries
      - non-solid types (gradients, images)
      - token refs (color starts with '{')
      - colors that don't have a nearby vocab match
    """
    out: list = []
    snapped = 0
    for fill in fills:
        if not isinstance(fill, dict):
            out.append(fill)
            continue
        new_fill = dict(fill)
        if new_fill.get("type") == "solid":
            color = new_fill.get("color")
            if isinstance(color, str) and not _is_token_ref(color):
                snapped_color = _snap_color_hex(color, vocab)
                if snapped_color is not None and snapped_color != color.upper():
                    new_fill["color"] = snapped_color
                    snapped += 1
        out.append(new_fill)
    return out, snapped


def _snap_padding(
    padding: dict, vocab: ProjectVocabulary,
) -> tuple[dict, int]:
    """Snap each side's numeric padding value."""
    out = dict(padding)
    snapped = 0
    for side in ("top", "right", "bottom", "left"):
        value = out.get(side)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if _is_token_ref(value):
            continue
        snapped_value = _snap_numeric(
            float(value),
            vocab.spacings,
            abs_threshold=_SPACING_ABS_THRESHOLD,
            rel_threshold=_SPACING_REL_THRESHOLD,
        )
        if snapped_value is not None and snapped_value != value:
            out[side] = snapped_value
            snapped += 1
    return out, snapped


def _snap_element(
    element: dict, vocab: ProjectVocabulary,
) -> tuple[dict, int, int, int, int]:
    """Snap a single element. Returns:
        (new_element, fills_snapped, radii_snapped,
         spacing_snapped, font_size_snapped)
    """
    new_element = dict(element)
    fills_snapped = 0
    radii_snapped = 0
    spacing_snapped = 0
    font_size_snapped = 0

    visual = new_element.get("visual")
    if isinstance(visual, dict):
        new_visual = dict(visual)

        # Fills
        fills = new_visual.get("fills")
        if isinstance(fills, list):
            new_fills, snapped = _snap_fills_list(fills, vocab)
            new_visual["fills"] = new_fills
            fills_snapped += snapped

        # cornerRadius
        radius = new_visual.get("cornerRadius")
        if (
            isinstance(radius, (int, float))
            and not isinstance(radius, bool)
            and not _is_token_ref(radius)
        ):
            snapped_radius = _snap_numeric(
                float(radius),
                vocab.radii,
                abs_threshold=_RADIUS_ABS_THRESHOLD,
                rel_threshold=_RADIUS_REL_THRESHOLD,
            )
            if snapped_radius is not None and snapped_radius != radius:
                new_visual["cornerRadius"] = snapped_radius
                radii_snapped += 1

        # fontSize on visual (LLM head-emitted form)
        font_size = new_visual.get("fontSize")
        if (
            isinstance(font_size, (int, float))
            and not isinstance(font_size, bool)
            and not _is_token_ref(font_size)
        ):
            snapped_size = _snap_numeric(
                float(font_size),
                vocab.font_sizes,
                abs_threshold=_FONT_SIZE_ABS_THRESHOLD,
                rel_threshold=_FONT_SIZE_REL_THRESHOLD,
            )
            if snapped_size is not None and snapped_size != font_size:
                new_visual["fontSize"] = snapped_size
                font_size_snapped += 1

        new_element["visual"] = new_visual

    layout = new_element.get("layout")
    if isinstance(layout, dict):
        new_layout = dict(layout)

        # Padding
        padding = new_layout.get("padding")
        if isinstance(padding, dict):
            new_padding, snapped = _snap_padding(padding, vocab)
            new_layout["padding"] = new_padding
            spacing_snapped += snapped

        # Gap (itemSpacing)
        gap = new_layout.get("gap")
        if (
            isinstance(gap, (int, float))
            and not isinstance(gap, bool)
            and not _is_token_ref(gap)
        ):
            snapped_gap = _snap_numeric(
                float(gap),
                vocab.spacings,
                abs_threshold=_SPACING_ABS_THRESHOLD,
                rel_threshold=_SPACING_REL_THRESHOLD,
            )
            if snapped_gap is not None and snapped_gap != gap:
                new_layout["gap"] = snapped_gap
                spacing_snapped += 1

        # counterAxisGap (less common, same threshold)
        cag = new_layout.get("counterAxisGap")
        if (
            isinstance(cag, (int, float))
            and not isinstance(cag, bool)
            and not _is_token_ref(cag)
        ):
            snapped_cag = _snap_numeric(
                float(cag),
                vocab.spacings,
                abs_threshold=_SPACING_ABS_THRESHOLD,
                rel_threshold=_SPACING_REL_THRESHOLD,
            )
            if snapped_cag is not None and snapped_cag != cag:
                new_layout["counterAxisGap"] = snapped_cag
                spacing_snapped += 1

        new_element["layout"] = new_layout

    style = new_element.get("style")
    if isinstance(style, dict):
        new_style = dict(style)

        # fontSize on style (typography binding form)
        font_size = new_style.get("fontSize")
        if (
            isinstance(font_size, (int, float))
            and not isinstance(font_size, bool)
            and not _is_token_ref(font_size)
        ):
            snapped_size = _snap_numeric(
                float(font_size),
                vocab.font_sizes,
                abs_threshold=_FONT_SIZE_ABS_THRESHOLD,
                rel_threshold=_FONT_SIZE_REL_THRESHOLD,
            )
            if snapped_size is not None and snapped_size != font_size:
                new_style["fontSize"] = snapped_size
                font_size_snapped += 1

        new_element["style"] = new_style

    return (
        new_element,
        fills_snapped,
        radii_snapped,
        spacing_snapped,
        font_size_snapped,
    )


def snap_ir_to_vocabulary(
    spec: dict, vocab: ProjectVocabulary,
) -> tuple[dict, SnapReport]:
    """Walk every untokenized literal in ``spec``; snap to nearest
    vocab value if within thresholds.

    Operates on a deep copy of ``spec`` — does NOT mutate input.

    Snap thresholds (Codex round-13 lock):
      - colors (SOLID fills only — gradients/images skipped):
          OKLCH ΔE ≤ 10, plus chromatic-vs-neutral category match
          (chromatic also requires hue Δ ≤ 24°; neutrals require
          lightness Δ ≤ 0.10). Token references skipped.
      - radii: abs Δ ≤ 2px OR rel Δ ≤ 20%
      - spacing/padding: abs Δ ≤ 3px OR rel Δ ≤ 20%
      - fontSize: abs Δ ≤ 2px OR rel Δ ≤ 12%

    Walks ``spec["elements"]`` looking at each element's:
      - ``element["visual"]["fills"]`` — solid fill colors
      - ``element["visual"]["cornerRadius"]`` — number
      - ``element["visual"]["fontSize"]`` — LLM head-emitted form
      - ``element["layout"]["padding"][side]`` — top/right/bottom/left
      - ``element["layout"]["gap"]`` — itemSpacing
      - ``element["layout"]["counterAxisGap"]``
      - ``element["style"]["fontSize"]`` — typography binding form

    Defensive — skips:
      - None values
      - token references (strings starting with ``{``)
      - non-numeric where numeric expected
      - non-solid fills (gradients, images)
    """
    new_spec = copy.deepcopy(spec)
    elements = new_spec.get("elements")
    if not isinstance(elements, dict):
        return new_spec, SnapReport(0, 0, 0, 0)

    fills_total = 0
    radii_total = 0
    spacing_total = 0
    font_size_total = 0

    for eid, element in elements.items():
        if not isinstance(element, dict):
            continue
        (
            new_element,
            fills_snapped,
            radii_snapped,
            spacing_snapped,
            font_size_snapped,
        ) = _snap_element(element, vocab)
        elements[eid] = new_element
        fills_total += fills_snapped
        radii_total += radii_snapped
        spacing_total += spacing_snapped
        font_size_total += font_size_snapped

    return new_spec, SnapReport(
        fills_snapped=fills_total,
        radii_snapped=radii_total,
        spacing_snapped=spacing_total,
        font_size_snapped=font_size_total,
    )


__all__ = [
    "ProjectVocabulary",
    "SnapReport",
    "build_project_vocabulary",
    "snap_ir_to_vocabulary",
]
