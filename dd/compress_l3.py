"""Plan B Stage 1.3/1.4 — L0+L1+L2 → L3 compressor.

Consumes the dict-IR output of `dd.ir.generate_ir` and emits an
`L3Document` AST per the L0↔L3 spec at
`docs/spec-l0-l3-relationship.md` §2.

Public API:

    compress_to_l3(spec: dict, conn: sqlite3.Connection) -> L3Document

The `conn` is required because `override_tree` lives in the raw
visual-dict path (not the semantic CompositionSpec). The compressor
fetches instance overrides on demand per L0↔L3 §2.7.2.

**Stage 1.3/1.4 scope (MVP):**

Shipped in this slice — single reference screen:
- Type keyword resolution (screen / frame / text / rectangle / etc.)
- Children ordering (via `children` field in CompositionSpec elements)
- EID sanitization (per L0↔L3 §2.3.1 `normalize_to_eid`)
- Spatial axis (x, y, width, height, layout, gap, padding, alignment)
- Visual axis (single-fill SOLID/GRADIENT/IMAGE, radius, opacity,
  visible)
- Component references via `_original_name` → slash-path derivation

NOT shipped yet (subsequent slices):
- Instance override flattening (requires per-screen override tree)
- Multi-fill arrays
- Effects, strokes
- Stroke colors and sizes
- Text typography
- Token-binding resolution (L2 → `{token.path}` — DB has no accepted
  tokens today so this is a no-op)
- Synthetic token clustering (Stage 3 scope)

The MVP produces output that parses via `parse_l3` and round-trips
via `emit_l3` at the grammar level. It does NOT yet reproduce the
pixel-perfect corpus round-trip (that's Stage 1.5–1.7).
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from typing import Any, Optional

from dd.markup_l3 import (
    Block,
    FuncArg,
    FunctionCall,
    L3Document,
    Literal_,
    Node,
    NodeHead,
    NodeTrailer,
    PropAssign,
    PropGroup,
    SizingValue,
    TokenRef,
    Value,
    Warning,
    parse_l3,
)


# ---------------------------------------------------------------------------
# EID sanitization — L0↔L3 §2.3.1
# ---------------------------------------------------------------------------


def normalize_to_eid(raw: str) -> str:
    """Normalize a Figma layer name to a valid dd-markup IDENT per
    grammar §2.4 and L0↔L3 §2.3.1.

    Returns the sanitized name, or "" if no valid IDENT is producible
    (empty result, digit-start, etc.) — callers fall back to
    `{type}-{n}` auto-id.
    """
    s = raw.lower()
    # Replace spaces and slashes with hyphens
    s = re.sub(r"[\s/]+", "-", s)
    # Drop non-IDENT chars
    s = re.sub(r"[^a-z0-9_-]+", "", s)
    # Trim leading/trailing separators
    s = s.strip("-_")
    # Collapse runs of -
    s = re.sub(r"-+", "-", s)
    if not s or s[0].isdigit():
        return ""
    return s


# ---------------------------------------------------------------------------
# Slash-path derivation for component refs — L0↔L3 §2.7.1
# ---------------------------------------------------------------------------


def derive_comp_slash_path(component_name: str) -> str:
    """Normalize each segment of a slash-separated master name."""
    segments = component_name.split("/")
    normalized = [normalize_to_eid(seg) for seg in segments if seg.strip()]
    if not normalized or any(s == "" for s in normalized):
        return ""
    return "/".join(normalized)


# ---------------------------------------------------------------------------
# Type keyword mapping
# ---------------------------------------------------------------------------

# Note: the `build_composition_spec` upstream already lowercases and
# normalizes `node_type` values into the `element["type"]` field, so
# the compressor applies an underscore→hyphen transform and passes the
# string through directly (see `_compress_element`). A raw mapping
# table is unused.


# ---------------------------------------------------------------------------
# Visual axis helpers
# ---------------------------------------------------------------------------


def _fill_to_value(fill: dict) -> Optional[Value]:
    """Convert a single fill dict to a ValueExpr. Returns None for
    unsupported shapes (caller drops the property)."""
    if not isinstance(fill, dict):
        return None
    typ = fill.get("type", "").lower()
    if typ == "solid":
        color = fill.get("color")
        if isinstance(color, str) and color.startswith("#"):
            # Validate hex color shape (6 or 8 digits)
            rest = color[1:]
            if len(rest) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in rest):
                return Literal_(lit_kind="hex-color", raw=color, py=color)
        return None
    if typ in ("gradient-linear", "gradient_linear"):
        stops = fill.get("stops") or []
        stop_args: list[FuncArg] = []
        for stop in stops:
            c = stop.get("color")
            if isinstance(c, str) and c.startswith("#"):
                stop_args.append(
                    FuncArg(name=None, value=Literal_(
                        lit_kind="hex-color", raw=c, py=c,
                    ))
                )
        if len(stop_args) >= 2:
            return FunctionCall(name="gradient-linear", args=tuple(stop_args))
        return None
    if typ == "image":
        asset_hash = fill.get("asset_hash")
        if isinstance(asset_hash, str) and len(asset_hash) == 40 and all(
            c in "0123456789abcdefABCDEF" for c in asset_hash
        ) and any(c in "0123456789" for c in asset_hash):
            return FunctionCall(
                name="image",
                args=(FuncArg(
                    name="asset",
                    value=Literal_(
                        lit_kind="asset-hash", raw=asset_hash, py=asset_hash,
                    ),
                ),),
            )
        return None
    return None


# ---------------------------------------------------------------------------
# Spatial axis helpers
# ---------------------------------------------------------------------------


def _num_literal(n: float | int) -> Literal_:
    """Wrap a number in a canonical-form Literal_.

    Round-then-snap: first round to 4 decimal places (sub-pixel
    precision), then snap to int if the rounded value is a whole
    number. This cleans Figma IEEE-754 coordinate residuals like
    `6.000001430511475` → `6` and `15.556350708007812` → `15.5564`
    while preserving meaningful sub-pixel values.
    """
    if isinstance(n, bool):
        raw = "true" if n else "false"
        return Literal_(lit_kind="bool", raw=raw, py=n)
    if isinstance(n, float) and abs(n) < 1e16:
        rounded = round(n, 4)
        if rounded.is_integer():
            n = int(rounded)
        else:
            n = rounded
    raw = str(n)
    return Literal_(lit_kind="number", raw=raw, py=n)


_LAYOUT_DIRECTION = {
    "HORIZONTAL": "horizontal",
    "VERTICAL": "vertical",
    "horizontal": "horizontal",
    "vertical": "vertical",
}


def _enum_literal(kw: str) -> Literal_:
    return Literal_(lit_kind="enum", raw=kw, py=kw)


def _sizing_value(s: Any) -> Optional[Value]:
    """Convert a CompositionSpec sizing entry (`"fill"`, `"hug"`, or a
    number) into the matching ValueExpr."""
    if isinstance(s, str):
        if s in ("fill", "hug"):
            return SizingValue(size_kind=s)   # type: ignore[arg-type]
        return None
    if isinstance(s, (int, float)):
        return _num_literal(s)
    return None


# ---------------------------------------------------------------------------
# Per-axis emitters
# ---------------------------------------------------------------------------


def _spatial_props(
    layout: dict, bounds: Optional[dict[str, float]] = None,
) -> list[PropAssign]:
    """Derive Spatial-axis PropAssigns from a CompositionSpec element's
    `layout` sub-dict. Omits zero/default values per §2.5.

    `bounds` is an optional `{min_width?, max_width?, min_height?,
    max_height?}` dict queried from the nodes table; when present AND
    the corresponding axis is `fill`, emits the bounded form
    `width=fill(min=N, max=N)` per grammar §4.4.
    """
    props: list[PropAssign] = []
    # Position — emit both x AND y whenever EITHER is non-zero, so we
    # don't silently drop y=0 in an `(x=0, y!=0)` pair or vice versa.
    # (Previously the elif branch was dead code and `y=0` when `x!=0`
    # was silently dropped.)
    position = layout.get("position") or {}
    if isinstance(position, dict):
        x = position.get("x")
        y = position.get("y")
        both_zero = (x in (None, 0)) and (y in (None, 0))
        if not both_zero:
            if x is not None:
                props.append(PropAssign(key="x", value=_num_literal(x)))
            if y is not None:
                props.append(PropAssign(key="y", value=_num_literal(y)))

    # Sizing — bounded form when the axis is `fill` and the node
    # carries min/max bounds.
    sizing = layout.get("sizing") or {}
    if isinstance(sizing, dict):
        w = sizing.get("width")
        h = sizing.get("height")
        wv = _sizing_value(w) if w is not None else None
        hv = _sizing_value(h) if h is not None else None
        # Promote bare `fill` / `hug` to bounded form when bounds exist
        if bounds:
            if isinstance(wv, SizingValue) and wv.size_kind in ("fill", "hug"):
                min_w = bounds.get("min_width")
                max_w = bounds.get("max_width")
                if min_w is not None or max_w is not None:
                    wv = SizingValue(
                        size_kind=wv.size_kind,
                        min=min_w,
                        max=max_w,
                    )
            if isinstance(hv, SizingValue) and hv.size_kind in ("fill", "hug"):
                min_h = bounds.get("min_height")
                max_h = bounds.get("max_height")
                if min_h is not None or max_h is not None:
                    hv = SizingValue(
                        size_kind=hv.size_kind,
                        min=min_h,
                        max=max_h,
                    )
        if wv is not None:
            props.append(PropAssign(key="width", value=wv))
        if hv is not None:
            props.append(PropAssign(key="height", value=hv))

    # Layout direction
    direction = layout.get("direction")
    if isinstance(direction, str):
        # `"stacked"` is the spec sentinel for "no auto-layout; absolute
        # is default" — omit the layout property.
        if direction in _LAYOUT_DIRECTION:
            props.append(PropAssign(
                key="layout",
                value=_enum_literal(_LAYOUT_DIRECTION[direction]),
            ))

    # Gap
    gap = layout.get("gap")
    if isinstance(gap, (int, float)) and gap != 0:
        props.append(PropAssign(key="gap", value=_num_literal(gap)))

    # Padding — emit only non-zero sides
    padding = layout.get("padding") or {}
    if isinstance(padding, dict):
        entries: list[PropAssign] = []
        for side in ("top", "right", "bottom", "left"):
            v = padding.get(side)
            if isinstance(v, (int, float)) and v != 0:
                entries.append(PropAssign(key=side, value=_num_literal(v)))
        if entries:
            props.append(PropAssign(
                key="padding", value=PropGroup(entries=tuple(entries)),
            ))

    # Alignment
    main_align = layout.get("mainAxisAlignment")
    cross_align = layout.get("crossAxisAlignment")
    if (
        main_align == "center" and cross_align == "center"
    ):
        props.append(PropAssign(key="align", value=_enum_literal("center")))
    else:
        if isinstance(main_align, str):
            props.append(PropAssign(
                key="mainAxis", value=_enum_literal(main_align),
            ))
        if isinstance(cross_align, str):
            props.append(PropAssign(
                key="crossAxis", value=_enum_literal(cross_align),
            ))

    return props


def _visual_props(visual: dict) -> list[PropAssign]:
    """Derive Visual-axis PropAssigns from the `visual` sub-dict."""
    props: list[PropAssign] = []

    # Fills (single-fill common case)
    fills = visual.get("fills") or []
    if isinstance(fills, list) and fills:
        if len(fills) == 1:
            fv = _fill_to_value(fills[0])
            if fv is not None:
                props.append(PropAssign(key="fill", value=fv))
        # Multi-fill array: deferred to a follow-up slice (value-array
        # form `fills=[...]` not yet supported in Stage 1.2 parser).

    # Strokes (single-stroke common case; multi-stroke deferred)
    strokes = visual.get("strokes") or []
    if isinstance(strokes, list) and strokes and len(strokes) == 1:
        sv = _fill_to_value(strokes[0])      # same hex/gradient/image forms
        if sv is not None:
            props.append(PropAssign(key="stroke", value=sv))
        stroke_width = strokes[0].get("width") if isinstance(strokes[0], dict) else None
        if isinstance(stroke_width, (int, float)) and stroke_width > 0:
            props.append(PropAssign(
                key="stroke-weight", value=_num_literal(stroke_width),
            ))

    # Effects — DROP_SHADOW becomes `shadow=shadow(dx, dy, blur, color)`;
    # blur effects (BACKGROUND_BLUR / LAYER_BLUR) are deferred (no
    # matching grammar function yet — §4.3 only has `shadow`).
    # Nodes with multi-shadow stacks emit only the first; an `$ext`
    # counter surfaces the truncation so tooling can identify them.
    effects = visual.get("effects") or []
    if isinstance(effects, list):
        shadow_value = _effects_to_shadow(effects)
        if shadow_value is not None:
            props.append(PropAssign(key="shadow", value=shadow_value))
        extra = _count_extra_shadows(effects)
        if extra > 0:
            props.append(PropAssign(
                key="$ext.shadow_extra_count",
                value=_num_literal(extra),
            ))

    # Radius (uniform only in MVP)
    cr = visual.get("cornerRadius")
    if isinstance(cr, (int, float)) and cr > 0:
        props.append(PropAssign(key="radius", value=_num_literal(cr)))

    # Opacity (non-default)
    op = visual.get("opacity")
    if isinstance(op, (int, float)) and op < 1.0:
        props.append(PropAssign(key="opacity", value=_num_literal(op)))

    return props


def _count_extra_shadows(effects: list) -> int:
    """Count visible DROP_SHADOW entries beyond the first. Used to emit
    a `$ext.shadow_extra_count=N` diagnostic so tooling can identify
    nodes whose multi-shadow stack was truncated (8,574 corpus nodes
    have 2+ shadows; grammar §4.3 lacks a multi-shadow form)."""
    if not isinstance(effects, list):
        return 0
    count = 0
    for eff in effects:
        if not isinstance(eff, dict):
            continue
        if eff.get("type") not in ("drop-shadow", "DROP_SHADOW"):
            continue
        if eff.get("visible") is False:
            continue
        count += 1
    return max(0, count - 1)


def _effects_to_shadow(effects: list) -> Optional[Value]:
    """Convert the first DROP_SHADOW effect into a `shadow(...)` FunctionCall.

    Grammar §4.3 defines `shadow(x=<px>, y=<px>, blur=<px>, color=<color>)`.
    Ignores BACKGROUND_BLUR, LAYER_BLUR, INNER_SHADOW, and any drops after
    the first one (multi-shadow arrays aren't in the grammar yet — see
    `_count_extra_shadows` for a diagnostic).
    """
    for eff in effects:
        if not isinstance(eff, dict):
            continue
        if eff.get("type") != "drop-shadow" and eff.get("type") != "DROP_SHADOW":
            continue
        if eff.get("visible") is False:
            continue                         # skip hidden drops
        dx = eff.get("offset", {}).get("x") if isinstance(eff.get("offset"), dict) else eff.get("offsetX", 0)
        dy = eff.get("offset", {}).get("y") if isinstance(eff.get("offset"), dict) else eff.get("offsetY", 0)
        blur = eff.get("radius", 0)
        color = eff.get("color")
        if isinstance(color, dict):          # normalized DB form
            color_hex = _color_dict_to_hex(color)
        elif isinstance(color, str):
            color_hex = color
        else:
            color_hex = "#00000040"          # sensible default
        args = [
            FuncArg(name="x", value=_num_literal(dx or 0)),
            FuncArg(name="y", value=_num_literal(dy or 0)),
            FuncArg(name="blur", value=_num_literal(blur or 0)),
            FuncArg(
                name="color",
                value=Literal_(lit_kind="hex-color", raw=color_hex, py=color_hex),
            ),
        ]
        return FunctionCall(name="shadow", args=tuple(args))
    return None


def _normalize_raw_paint(raw: dict) -> Optional[dict]:
    """Convert a Figma-raw paint dict (from `instance_overrides`) into
    the spec-normalized shape consumed by `_fill_to_value`.

    Raw form: `{type: "SOLID", color: {r,g,b[,a]}, visible, opacity, ...}`
    Spec form: `{type: "solid", color: "#RRGGBB[AA]"}`

    Hidden (`visible == false`) paints return None so callers skip them.
    Opacity is folded into the alpha channel for SOLID; for gradients
    each stop already carries alpha in its color dict.
    """
    if not isinstance(raw, dict):
        return None
    if raw.get("visible") is False:
        return None
    typ = raw.get("type", "")
    typ_lower = typ.lower() if isinstance(typ, str) else ""
    if typ == "SOLID" or typ_lower == "solid":
        color = raw.get("color")
        if not isinstance(color, dict):
            return None
        # Fold paint-level opacity into alpha if sub-unit.
        op = raw.get("opacity")
        merged = dict(color)
        if isinstance(op, (int, float)) and op < 1.0:
            base_a = float(color.get("a", 1.0))
            merged["a"] = base_a * op
        return {"type": "solid", "color": _color_dict_to_hex(merged)}
    if typ.startswith("GRADIENT_") or typ_lower.startswith("gradient-"):
        stops_raw = raw.get("gradientStops") or raw.get("stops") or []
        stops: list[dict] = []
        for s in stops_raw:
            if not isinstance(s, dict):
                continue
            c = s.get("color")
            if isinstance(c, dict):
                stops.append({"color": _color_dict_to_hex(c)})
            elif isinstance(c, str):
                stops.append({"color": c})
        # Grammar §4.3 only has `gradient-linear(...)` — fold all linear
        # gradient types to that form; radial/angular/diamond fall back
        # to None (caller drops).
        if typ == "GRADIENT_LINEAR" or typ_lower == "gradient-linear":
            return {"type": "gradient-linear", "stops": stops}
        return None
    if typ == "IMAGE" or typ_lower == "image":
        asset_hash = raw.get("imageHash") or raw.get("asset_hash")
        if not isinstance(asset_hash, str):
            return None
        return {"type": "image", "asset_hash": asset_hash}
    return None


def _color_dict_to_hex(color: dict) -> str:
    """Convert a `{r,g,b,a}` dict (normalized 0..1) into `#RRGGBB[AA]`."""
    try:
        r = int(round(float(color.get("r", 0)) * 255))
        g = int(round(float(color.get("g", 0)) * 255))
        b = int(round(float(color.get("b", 0)) * 255))
        a = float(color.get("a", 1.0))
    except (TypeError, ValueError):
        return "#000000"
    base = f"#{r:02X}{g:02X}{b:02X}"
    if a >= 0.999:
        return base
    return f"{base}{int(round(a * 255)):02X}"


# ---------------------------------------------------------------------------
# Element → Node
# ---------------------------------------------------------------------------


# Canonical property ordering per grammar §7.5. Mirrors the emitter's
# `_prop_rank` in `dd/markup_l3.py` so the AST the compressor produces
# matches what the parser produces after round-trip.
_PROP_RANK_STRUCTURAL = ("variant", "role", "as")
_PROP_RANK_CONTENT = (
    "text", "label", "placeholder", "content", "value", "min", "max",
)
_PROP_RANK_SPATIAL = (
    "x", "y", "width", "height",
    "min-width", "max-width", "min-height", "max-height",
    "layout", "gap", "padding",
    "mainAxis", "crossAxis", "align", "constraints",
)
_PROP_RANK_VISUAL = (
    "fill", "fills", "stroke", "strokes", "stroke-weight",
    "effects", "shadow", "radius", "opacity", "blend", "visible",
    "font", "size", "weight", "color",
    "line-height", "letter-spacing",
)


def _compress_prop_rank(key: str) -> tuple[int, str]:
    if key.startswith("$ext."):
        return (4, key)
    if "." in key:
        return (5, key)
    for idx, bucket in enumerate((
        _PROP_RANK_STRUCTURAL, _PROP_RANK_CONTENT,
        _PROP_RANK_SPATIAL, _PROP_RANK_VISUAL,
    )):
        if key in bucket:
            return (idx, f"{bucket.index(key):04d}")
    return (3, "~" + key)


def _auto_eid(type_kw: str, sibling_index: int) -> str:
    return f"{type_kw}-{sibling_index}"


def _compress_element(
    eid_key: str,
    spec: dict,
    parent_sibling_counter: dict[str, int],
    used_eids: set[str],
    comp_names: dict[str, str],
    self_overrides: dict[str, list[PropAssign]],
    radius_map: dict[str, object],
    bounds_map: dict[str, dict[str, float]],
    swap_paths: dict[str, str],
    visiting: frozenset[str] = frozenset(),
) -> Optional[Node]:
    """Turn a CompositionSpec element dict into an AST Node.

    `eid_key` is the element's spec key (e.g., `"screen-1"`, `"frame-3"`).
    `comp_names` maps element-id → master component name (from CKR) for
    Mode-1-eligible elements; an empty string signals "lookup failed,
    fall back to inline frame".
    `visiting` is a frozenset of element-ids currently on the recursion
    stack — a cycle in `children` edges returns None instead of
    blowing the stack.
    Returns None if the element has no usable type or is already on
    the recursion stack.
    """
    if eid_key in visiting:
        return None                          # circular-reference guard
    element = spec["elements"].get(eid_key)
    if not element:
        return None

    # CompositionSpec uses underscore-delimited type strings (e.g.
    # `"boolean_operation"` from `node_type.lower()`); dd markup uses
    # the hyphen-delimited form (grammar §2.7). Normalize here.
    raw_type = element.get("type", "frame")
    type_str = raw_type.replace("_", "-") if isinstance(raw_type, str) else "frame"

    # EID — prefer sanitized original name. Per L0↔L3 §2.3.1 collision
    # handling: when the name-derived candidate collides, append `-N`
    # (smallest int ≥ 2) rather than falling through to the auto-id.
    # Only fall through to auto-id when the original name has no
    # sanitized IDENT form (digit-start, empty, etc.).
    original_name = element.get("_original_name", "")
    eid_candidate = normalize_to_eid(original_name) if original_name else ""
    eid: str
    if eid_candidate:
        eid = eid_candidate
        n = 2
        while eid in used_eids:
            eid = f"{eid_candidate}-{n}"
            n += 1
    else:
        parent_sibling_counter[type_str] = (
            parent_sibling_counter.get(type_str, 0) + 1
        )
        eid = _auto_eid(type_str, parent_sibling_counter[type_str])
        while eid in used_eids:
            parent_sibling_counter[type_str] += 1
            eid = _auto_eid(type_str, parent_sibling_counter[type_str])
    used_eids.add(eid)

    # Mode-1 eligible nodes with a resolved CKR master name emit as a
    # CompRef (`-> slash/path`). Lookup miss → fall back to inline type.
    # An INSTANCE_SWAP `:self` override overrides the master name: the
    # swap's replacement slash-path takes precedence per L0↔L3 §2.7.2
    # step 3 (root form — the WHOLE CompRef changes).
    head_kind = "type"
    type_or_path = type_str
    master_name = swap_paths.get(eid_key) or comp_names.get(eid_key, "")
    if element.get("_mode1_eligible") and master_name:
        slash = derive_comp_slash_path(master_name)
        if slash:
            head_kind = "comp-ref"
            type_or_path = slash

    # Determine visibility
    visible = element.get("visible", True)
    visible_prop: list[PropAssign] = []
    if visible is False:
        visible_prop.append(PropAssign(
            key="visible",
            value=Literal_(lit_kind="bool", raw="false", py=False),
        ))

    # Build property list — canonical order handled by emitter
    props: list[PropAssign] = []
    props.extend(_spatial_props(
        element.get("layout") or {},
        bounds=bounds_map.get(eid_key),
    ))
    props.extend(_visual_props(element.get("visual") or {}))
    # cornerRadius isn't in the CompositionSpec; pull from our batched
    # DB lookup. Value is either a scalar float (uniform) or a dict
    # `{"tl": ..., "tr": ..., "bl": ..., "br": ...}` (per-corner).
    if eid_key in radius_map and not any(p.key == "radius" for p in props):
        radius_val = radius_map[eid_key]
        if isinstance(radius_val, (int, float)):
            props.append(PropAssign(
                key="radius", value=_num_literal(radius_val),
            ))
        elif isinstance(radius_val, dict):
            # Per-corner: emit as PropGroup in grammar §7.6 canonical
            # order `top-left, top-right, bottom-right, bottom-left`.
            # The DB uses abbreviated `tl/tr/bl/br` keys.
            canonical_corners = (
                ("tl", "top-left"),
                ("tr", "top-right"),
                ("br", "bottom-right"),
                ("bl", "bottom-left"),
            )
            entries: list[PropAssign] = []
            for short, long_name in canonical_corners:
                v = radius_val.get(short)
                if isinstance(v, (int, float)) and v != 0:
                    entries.append(PropAssign(
                        key=long_name, value=_num_literal(v),
                    ))
            if entries:
                props.append(PropAssign(
                    key="radius", value=PropGroup(entries=tuple(entries)),
                ))
    props.extend(visible_prop)

    # Slice B MVP: flatten `:self` instance overrides onto CompRef heads.
    # Only runs for Mode-1-eligible nodes that successfully resolved to
    # a CompRef; inline-frame fallbacks skip this step.
    if head_kind == "comp-ref" and eid_key in self_overrides:
        # Merge override props, de-duplicating by key (override wins
        # over the compressor's default derivation — per §2.7.2 the
        # override IS the authoritative value).
        existing_keys = {p.key for p in props}
        for override_prop in self_overrides[eid_key]:
            if override_prop.key in existing_keys:
                # Replace the existing prop with the override version
                props = [p for p in props if p.key != override_prop.key]
            props.append(override_prop)

    # Sort properties into canonical order (grammar §7.5) so the
    # AST matches what the parser would produce after round-trip.
    # Without this, the unsorted compressor output fails
    # `parse(emit(doc)) == doc` equality because the parser sorts but
    # the compressor didn't.
    props.sort(key=lambda p: _compress_prop_rank(p.key))

    # Positional content for text-bearing nodes. Text content lives
    # under `element["props"]["text"]` in the CompositionSpec —
    # `element["text"]` is a sibling of `props` and is NOT populated by
    # `build_composition_spec`. Reading the wrong key silently drops
    # the entire Content axis.
    positional: Optional[Value] = None
    if type_str in ("text", "heading"):
        txt = (element.get("props") or {}).get("text")
        if isinstance(txt, str) and txt:
            positional = Literal_(
                lit_kind="string", raw=f'"{txt}"', py=txt,
            )

    head = NodeHead(
        head_kind=head_kind,
        type_or_path=type_or_path,
        scope_alias=None,
        eid=eid,
        alias=None,
        override_args=(),
        positional=positional,
        properties=tuple(props),
        trailer=None,
    )

    # Children. CompRefs emit WITHOUT a child block — the master
    # component provides the subtree at render time (L0↔L3 §2.7). Only
    # inline nodes carry their own children.
    child_nodes: list[Node] = []
    if head_kind != "comp-ref":
        child_ids = element.get("children") or []
        child_counter: dict[str, int] = {}
        child_used_eids: set[str] = set()     # per-Block scope
        next_visiting = visiting | {eid_key}
        for child_id in child_ids:
            child_node = _compress_element(
                child_id, spec, child_counter, child_used_eids,
                comp_names, self_overrides, radius_map, bounds_map,
                swap_paths, visiting=next_visiting,
            )
            if child_node is not None:
                child_nodes.append(child_node)

    block: Optional[Block] = None
    if child_nodes:
        block = Block(statements=tuple(child_nodes))

    return Node(head=head, block=block)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Visual-axis enrichment from the DB — `corner_radius` isn't in the
# CompositionSpec (`build_composition_spec` doesn't copy it), so we
# query `nodes.corner_radius` directly for every element that has a
# node-id mapping. This is a low-cost batched lookup per screen.
# ---------------------------------------------------------------------------


def _fetch_sizing_bounds_map(
    conn: Optional[sqlite3.Connection],
    node_id_map: dict[str, int],
) -> dict[str, dict[str, float]]:
    """Batched query: `element_id → {min_w?, max_w?, min_h?, max_h?}`
    for every node with at least one non-null bound. Used by the
    spatial-axis emitter to produce `width=fill(min=N, max=N)` and
    `height=fill(...)` bounded forms per grammar §4.4.

    The CompositionSpec doesn't include these fields (matches
    `corner_radius`); we query `nodes` directly.
    """
    if conn is None or not node_id_map:
        return {}
    node_ids = list(node_id_map.values())
    if not node_ids:
        return {}
    placeholders = ",".join("?" for _ in node_ids)
    rows = conn.execute(
        f"SELECT id, min_width, max_width, min_height, max_height "
        f"FROM nodes WHERE id IN ({placeholders}) "
        f"  AND (min_width IS NOT NULL OR max_width IS NOT NULL "
        f"       OR min_height IS NOT NULL OR max_height IS NOT NULL)",
        node_ids,
    ).fetchall()
    by_node_id: dict[int, dict[str, float]] = {}
    for row in rows:
        nid, minw, maxw, minh, maxh = row[0], row[1], row[2], row[3], row[4]
        bounds: dict[str, float] = {}
        if minw is not None:
            bounds["min_width"] = float(minw)
        if maxw is not None:
            bounds["max_width"] = float(maxw)
        if minh is not None:
            bounds["min_height"] = float(minh)
        if maxh is not None:
            bounds["max_height"] = float(maxh)
        if bounds:
            by_node_id[nid] = bounds
    out: dict[str, dict[str, float]] = {}
    for eid, nid in node_id_map.items():
        if nid in by_node_id:
            out[eid] = by_node_id[nid]
    return out


def _fetch_corner_radius_map(
    conn: Optional[sqlite3.Connection],
    node_id_map: dict[str, int],
) -> dict[str, object]:
    """Batched query: `element_id → corner_radius` for every node with
    a non-null, non-zero `corner_radius` value.

    The DB `corner_radius` column is polymorphic: usually a uniform
    float (e.g. `10.0`), but for per-corner radii it stores a JSON
    string like `'{"tl": 28.0, "tr": 28.0, "bl": 0.0, "br": 0.0}'`.
    Callers dispatch on the value type.
    """
    if conn is None or not node_id_map:
        return {}
    node_ids = list(node_id_map.values())
    if not node_ids:
        return {}
    import json
    placeholders = ",".join("?" for _ in node_ids)
    rows = conn.execute(
        f"SELECT id, corner_radius FROM nodes "
        f"WHERE id IN ({placeholders}) "
        f"  AND corner_radius IS NOT NULL AND corner_radius != '0' "
        f"  AND corner_radius != 0",
        node_ids,
    ).fetchall()
    by_node_id: dict[int, object] = {}
    for row in rows:
        raw = row[1]
        if isinstance(raw, (int, float)):
            if raw != 0:
                by_node_id[row[0]] = float(raw)
        elif isinstance(raw, str):
            if not raw or raw == "0" or raw == "0.0":
                continue
            # Try JSON — per-corner dict — before float
            if raw.startswith("{"):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        by_node_id[row[0]] = parsed
                        continue
                except (ValueError, TypeError):
                    pass
            # Fall through: try as float scalar
            try:
                fv = float(raw)
                # Guard against NaN / Infinity — both pass `float()`
                # but would produce unparseable Literal_ nodes.
                if math.isfinite(fv) and fv != 0:
                    by_node_id[row[0]] = fv
            except (ValueError, TypeError):
                pass
    out: dict[str, object] = {}
    for eid, nid in node_id_map.items():
        if nid in by_node_id:
            out[eid] = by_node_id[nid]
    return out


# ---------------------------------------------------------------------------
# Slice B MVP — `:self` instance overrides per L0↔L3 §2.7.2 step 1
# ---------------------------------------------------------------------------
#
# Flattens a subset of the `instance_overrides` DB table onto CompRef
# heads as PropAssigns. Covers only `:self:*` rows (no child-path walk
# required) and only the scalar forms (no JSON parsing of fills/
# effects/strokes). Covers the high-frequency cases:
#
#   BOOLEAN :self:visible            → visible=<bool>
#   WIDTH   :self:width              → width=<number>
#   HEIGHT  :self:height             → height=<number>
#   CORNER_RADIUS :self:cornerRadius → radius=<number>
#   OPACITY :self:opacity            → opacity=<float>
#   ITEM_SPACING :self:itemSpacing   → gap=<number>
#   LAYOUT_SIZING_H :self:layoutSizingH → width=fixed/fill/hug
#   STROKE_WEIGHT :self:strokeWeight → stroke-weight=<number>
#
# Complex types (FILLS, EFFECTS, STROKES, INSTANCE_SWAP, PADDING_*,
# PRIMARY_ALIGN, STROKE_ALIGN) and all child-path overrides are
# DEFERRED — either requiring JSON parsing or master-subtree walking
# that isn't in scope for Slice B MVP.


_SELF_OVERRIDE_SCALAR_MAP = {
    # (property_type, property_name) → (dd-markup key, conversion fn)
    ("BOOLEAN", ":self:visible"):
        ("visible", lambda v: Literal_(lit_kind="bool", raw=v, py=(v == "true"))),
    ("WIDTH", ":self:width"):
        ("width", lambda v: _num_literal(float(v))),
    ("HEIGHT", ":self:height"):
        ("height", lambda v: _num_literal(float(v))),
    ("CORNER_RADIUS", ":self:cornerRadius"):
        ("radius", lambda v: _num_literal(float(v))),
    ("OPACITY", ":self:opacity"):
        ("opacity", lambda v: _num_literal(float(v))),
    ("ITEM_SPACING", ":self:itemSpacing"):
        ("gap", lambda v: _num_literal(float(v))),
    ("STROKE_WEIGHT", ":self:strokeWeight"):
        ("stroke-weight", lambda v: _num_literal(float(v))),
}


_LAYOUT_SIZING_MAP = {
    "FIXED": "fixed",
    "FILL": "fill",
    "HUG": "hug",
}


_PRIMARY_AXIS_MAP = {
    # `primaryAxisAlignItems` values from the Figma API. Spec §4.2
    # maps these onto the `mainAxis=<enum>` PropAssign.
    "MIN": "min",
    "CENTER": "center",
    "MAX": "max",
    "SPACE_BETWEEN": "space-between",
}


_PADDING_SIDE_MAP = {
    ":self:paddingLeft": "left",
    ":self:paddingRight": "right",
    ":self:paddingTop": "top",
    ":self:paddingBottom": "bottom",
}


def _fetch_self_overrides(
    conn: Optional[sqlite3.Connection],
    node_id_map: dict[str, int],
    eligible_eids: list[str],
) -> tuple[dict[str, list[PropAssign]], dict[str, str]]:
    """Fetch `:self:*` instance overrides for every element-id that
    emitted as a CompRef.

    Returns:
    - `props_by_eid`: `{eid: [PropAssign, ...]}` — scalar override
      properties to merge onto the CompRef head.
    - `swap_by_eid`: `{eid: replacement_component_key}` — root
      INSTANCE_SWAP overrides (the CompRef's slash-path itself
      changes). Caller resolves replacement_component_key via CKR.

    Skips child-path (`;figmaId:...`) rows — those require master-
    subtree walking (Stage 1.7 scope).
    """
    if conn is None or not eligible_eids:
        return {}, {}
    node_ids = [node_id_map[eid] for eid in eligible_eids if eid in node_id_map]
    if not node_ids:
        return {}, {}
    placeholders = ",".join("?" for _ in node_ids)
    rows = conn.execute(
        f"SELECT io.node_id, io.property_type, io.property_name, "
        f"       io.override_value "
        f"FROM instance_overrides io "
        f"WHERE io.node_id IN ({placeholders}) "
        f"  AND io.property_name LIKE ':self%'",
        node_ids,
    ).fetchall()

    # Build node_id → eid inverse map
    node_id_to_eid: dict[int, str] = {}
    for eid, nid in node_id_map.items():
        if eid in eligible_eids:
            node_id_to_eid[nid] = eid

    props_by_eid: dict[str, list[PropAssign]] = {}
    swap_by_eid: dict[str, str] = {}
    # Per-side padding is coalesced into a single `padding={...}`
    # PropGroup per eid so that `:self:paddingLeft` + `:self:paddingRight`
    # produce `padding={right=N left=N}` rather than two scattered
    # ext-props.
    padding_by_eid: dict[str, dict[str, float]] = {}
    for row in rows:
        nid, ptype, pname, pval = row[0], row[1], row[2], row[3]
        eid = node_id_to_eid.get(nid)
        if eid is None or pval is None:
            continue
        # Root INSTANCE_SWAP — `property_name == ':self'`, override_value
        # is the replacement `component_key`. The CompRef slash-path
        # will be re-resolved against the CKR.
        if ptype == "INSTANCE_SWAP" and pname == ":self":
            swap_by_eid[eid] = pval
            continue
        props = props_by_eid.setdefault(eid, [])
        # Scalar map handles the common cases in one dict
        key_fn = _SELF_OVERRIDE_SCALAR_MAP.get((ptype, pname))
        if key_fn is not None:
            key, conv = key_fn
            try:
                props.append(PropAssign(key=key, value=conv(pval)))
            except (ValueError, KeyError):
                pass
            continue
        # LAYOUT_SIZING_H: emit as width=<enum>
        if ptype == "LAYOUT_SIZING_H" and pname == ":self:layoutSizingH":
            dd_val = _LAYOUT_SIZING_MAP.get(pval)
            if dd_val is not None:
                if dd_val == "fixed":
                    # `fixed` has no bare keyword; map would require a
                    # pixel value that's not in the override row. Skip.
                    continue
                props.append(PropAssign(
                    key="width",
                    value=SizingValue(size_kind=dd_val),  # type: ignore[arg-type]
                ))
            continue
        # FILLS / STROKES — JSON paint arrays. First visible paint wins
        # (matches Stage-1 visual-axis emission from the spec).
        if ptype == "FILLS" and pname == ":self:fills":
            value = _raw_paint_json_to_value(pval)
            if value is not None:
                props.append(PropAssign(key="fill", value=value))
            continue
        if ptype == "STROKES" and pname == ":self:strokes":
            value = _raw_paint_json_to_value(pval)
            if value is not None:
                props.append(PropAssign(key="stroke", value=value))
            continue
        # EFFECTS — JSON array; emit first DROP_SHADOW as
        # `shadow=shadow(...)`. Truncation (2+ shadows) surfaces as the
        # same `$ext.shadow_extra_count` diagnostic used in `_visual_props`.
        if ptype == "EFFECTS" and pname == ":self:effects":
            try:
                effects = json.loads(pval)
            except (ValueError, TypeError):
                effects = None
            if isinstance(effects, list):
                sv = _effects_to_shadow(effects)
                if sv is not None:
                    props.append(PropAssign(key="shadow", value=sv))
                extra = _count_extra_shadows(effects)
                if extra > 0:
                    props.append(PropAssign(
                        key="$ext.shadow_extra_count",
                        value=_num_literal(extra),
                    ))
            continue
        # PRIMARY_ALIGN — bare enum → `mainAxis=<value>`.
        if ptype == "PRIMARY_ALIGN" and pname == ":self:primaryAxisAlignItems":
            dd_val = _PRIMARY_AXIS_MAP.get(pval)
            if dd_val is not None:
                props.append(PropAssign(
                    key="mainAxis", value=_enum_literal(dd_val),
                ))
            continue
        # PADDING_* — bare numeric per side; coalesce per eid below.
        if pname in _PADDING_SIDE_MAP:
            try:
                fv = float(pval)
            except (ValueError, TypeError):
                continue
            if not math.isfinite(fv):
                continue
            side = _PADDING_SIDE_MAP[pname]
            padding_by_eid.setdefault(eid, {})[side] = fv
            continue

    # Emit coalesced padding PropGroups. Side order matches grammar
    # §7.6: `top right bottom left`. PropGroup entries are themselves
    # PropAssigns (same shape as the inline-layout padding emission).
    for eid, sides in padding_by_eid.items():
        entries: list[PropAssign] = []
        for side in ("top", "right", "bottom", "left"):
            if side in sides:
                entries.append(PropAssign(
                    key=side, value=_num_literal(sides[side]),
                ))
        if entries:
            props_by_eid.setdefault(eid, []).append(PropAssign(
                key="padding", value=PropGroup(entries=tuple(entries)),
            ))

    return props_by_eid, swap_by_eid


def _raw_paint_json_to_value(raw_json: str) -> Optional[Value]:
    """Parse a Figma-raw paint-array JSON (from `instance_overrides`)
    and return the first visible paint's dd-markup Value. Used for
    `:self:fills` and `:self:strokes` override rows."""
    try:
        arr = json.loads(raw_json)
    except (ValueError, TypeError):
        return None
    if not isinstance(arr, list):
        return None
    for raw in arr:
        normalized = _normalize_raw_paint(raw)
        if normalized is None:
            continue
        value = _fill_to_value(normalized)
        if value is not None:
            return value
    return None


def _resolve_swap_component_name(
    conn: Optional[sqlite3.Connection],
    figma_node_ids: list[str],
) -> dict[str, str]:
    """Look up replacement-component names for INSTANCE_SWAP overrides.

    `instance_overrides.override_value` for INSTANCE_SWAP rows stores a
    Figma node id (format `"5749:82213"`), NOT a component_key SHA-1.
    The join is against `component_key_registry.figma_node_id`, not
    `component_key_registry.component_key`. Regressions here are
    silent (empty dict means no swaps fire), so agent review caught
    this inversion with a direct SQL probe.
    """
    if conn is None or not figma_node_ids:
        return {}
    placeholders = ",".join("?" for _ in figma_node_ids)
    rows = conn.execute(
        f"SELECT figma_node_id, name FROM component_key_registry "
        f"WHERE figma_node_id IN ({placeholders})",
        figma_node_ids,
    ).fetchall()
    return {row[0]: row[1] for row in rows if row[1]}


def _build_comp_names_map(
    spec: dict, conn: Optional[sqlite3.Connection],
) -> dict[str, str]:
    """Build an `element_id → master_component_name` map from the CKR.

    Uses `spec["_node_id_map"]` (element-id → node-id) to look up each
    Mode-1-eligible element's node_id, then joins to
    `component_key_registry` to get the master name. Missing entries
    are omitted — caller falls back to inline-frame emission.
    """
    if conn is None:
        return {}
    node_id_map = spec.get("_node_id_map") or {}
    # Only fetch for Mode-1-eligible elements (skip frames / text / etc.)
    eligible_eids = [
        eid for eid, el in (spec.get("elements") or {}).items()
        if el.get("_mode1_eligible")
    ]
    if not eligible_eids:
        return {}
    node_ids = [node_id_map[eid] for eid in eligible_eids if eid in node_id_map]
    if not node_ids:
        return {}
    placeholders = ",".join("?" for _ in node_ids)
    rows = conn.execute(
        f"SELECT n.id, ckr.name "
        f"FROM nodes n "
        f"LEFT JOIN component_key_registry ckr "
        f"  ON ckr.component_key = n.component_key "
        f"WHERE n.id IN ({placeholders})",
        node_ids,
    ).fetchall()
    node_id_to_name = {row[0]: row[1] for row in rows if row[1]}
    out: dict[str, str] = {}
    for eid in eligible_eids:
        nid = node_id_map.get(eid)
        if nid is not None and nid in node_id_to_name:
            out[eid] = node_id_to_name[nid]
    return out


def _collapse_synthetic_screen_wrapper(spec: dict) -> dict:
    """Collapse the synthetic `screen-1` → Figma-canvas-FRAME wrapper.

    `dd.ir.generate_ir` emits a synthetic `screen-1` parent around every
    screen's real canvas frame (which carries the user-visible name,
    fill, etc.). Without this collapse, every screen renders as:

        screen #iphone-13-pro-max-119 width=428 height=926 {
          frame #iphone-13-pro-max-119 width=428 height=926 fill=#F6F6F6 {
            ...

    The two lines are redundant (identical eid, identical sizing) and
    the second frame just holds the wrapper fill. Per L0↔L3 the screen
    IS the canvas — one line, not two.

    This pass:
      1. Detects the pattern (root is `screen`; one child; child has
         the same `_original_name`).
      2. Hoists the child's visual + layout (except sizing) onto the
         screen.
      3. Replaces the screen's children with the grand-children.
      4. Rewrites `_node_id_map` so override lookups keyed on
         `screen-1` resolve to the canvas frame's node-id (the child
         is what the DB actually knows about).

    Returns a shallow-copied spec; original is not mutated.
    """
    elements = spec.get("elements")
    root_key = spec.get("root")
    if not isinstance(elements, dict) or not root_key:
        return spec
    root = elements.get(root_key)
    if not isinstance(root, dict):
        return spec
    children = root.get("children") or []
    if len(children) != 1:
        return spec
    child_key = children[0]
    child = elements.get(child_key)
    if not isinstance(child, dict):
        return spec
    # Must match on original name (defensive against unrelated
    # single-child roots).
    root_name = root.get("_original_name")
    child_name = child.get("_original_name")
    if not root_name or root_name != child_name:
        return spec

    # Build merged root.
    new_root = dict(root)
    # Hoist visual (fills / strokes / radius / effects / opacity).
    if "visual" in child:
        new_root["visual"] = child["visual"]
    # Hoist layout direction (screen's is "absolute" placeholder) but
    # KEEP the screen's sizing — it's the authoritative canvas size.
    root_layout = dict(root.get("layout") or {})
    child_layout = child.get("layout") or {}
    if "direction" in child_layout:
        root_layout["direction"] = child_layout["direction"]
    if "gap" in child_layout:
        root_layout["gap"] = child_layout["gap"]
    if "padding" in child_layout:
        root_layout["padding"] = child_layout["padding"]
    if "alignment" in child_layout:
        root_layout["alignment"] = child_layout["alignment"]
    new_root["layout"] = root_layout
    # Grandchildren become children.
    new_root["children"] = list(child.get("children") or [])
    # Promote _mode1_eligible if child had it (synthetic screen never does).
    if child.get("_mode1_eligible") is not None:
        new_root["_mode1_eligible"] = child["_mode1_eligible"]

    new_elements = dict(elements)
    new_elements[root_key] = new_root
    # Leave the child element in place for any node_id_map lookups
    # that expect to find it — but remap its node-id to the root.
    node_id_map = dict(spec.get("_node_id_map") or {})
    child_nid = node_id_map.get(child_key)
    if child_nid is not None:
        # Root now refers to the real canvas in the DB.
        node_id_map[root_key] = child_nid

    new_spec = dict(spec)
    new_spec["elements"] = new_elements
    new_spec["_node_id_map"] = node_id_map
    return new_spec


def compress_to_l3(
    spec: dict, conn: Optional[sqlite3.Connection] = None,
    *, screen_id: Optional[int] = None,
) -> L3Document:
    """Compress a CompositionSpec dict into an L3Document AST.

    `spec` is the `["spec"]` sub-dict returned by
    `dd.ir.generate_ir(..., semantic=True)` — NOT the full wrapper.

    `conn` is required to look up CompRef master names via the CKR;
    may be omitted in tests that don't care about Mode-1 emission
    (those elements then fall back to inline-frame output).

    `screen_id` is used to populate the node-level `(extracted src=...)`
    trailer when present; optional because the spec dict doesn't carry
    it explicitly.
    """
    # Defensive guards — bad input shouldn't crash with AttributeError.
    if not isinstance(spec, dict):
        return L3Document(namespace=None)
    # Collapse the synthetic `screen` wrapper around the real Figma
    # canvas frame before any property collection runs — downstream
    # lookups (CKR, overrides, radius, bounds) key off the screen's
    # remapped node-id.
    spec = _collapse_synthetic_screen_wrapper(spec)
    elements = spec.get("elements")
    if elements is None:
        return L3Document(namespace=None)
    root_key = spec.get("root")
    if not root_key or root_key not in elements:
        return L3Document(namespace=None)

    used_eids: set[str] = set()
    root_counter: dict[str, int] = {}
    node_id_map = spec.get("_node_id_map") or {}
    comp_names = _build_comp_names_map(spec, conn)
    # Eligible EIDs for override lookup = those that will emit as
    # CompRefs (Mode-1 + CKR resolved).
    eligible_eids = list(comp_names.keys())
    self_overrides, swap_keys = _fetch_self_overrides(
        conn, node_id_map, eligible_eids,
    )
    # Resolve INSTANCE_SWAP replacement figma_node_ids → names via CKR.
    # Unresolved swaps (replacement node absent from CKR) surface as
    # `KIND_SWAP_UNRESOLVED` warnings so downstream tooling can
    # distinguish "swap resolved" from "swap silently dropped".
    swap_names = _resolve_swap_component_name(
        conn, list(set(swap_keys.values())),
    )
    swap_paths: dict[str, str] = {}
    swap_warnings: list[Warning] = []
    for eid, ck in swap_keys.items():
        if ck in swap_names:
            swap_paths[eid] = swap_names[ck]
        else:
            swap_warnings.append(Warning(
                kind="KIND_SWAP_UNRESOLVED",
                message=(
                    f"INSTANCE_SWAP on `#{eid}` references figma_node_id "
                    f"`{ck}` which is not in component_key_registry; "
                    f"keeping original master"
                ),
            ))
    # cornerRadius + min/max bounds live in the nodes table — neither
    # is copied into the CompositionSpec. Both require a batched query.
    radius_map = _fetch_corner_radius_map(conn, node_id_map)
    bounds_map = _fetch_sizing_bounds_map(conn, node_id_map)
    root_node = _compress_element(
        root_key, spec, root_counter, used_eids,
        comp_names, self_overrides, radius_map, bounds_map, swap_paths,
    )
    if root_node is None:
        return L3Document(namespace=None)

    # Attach provenance trailer
    if screen_id is not None:
        attrs: tuple[tuple[str, Value], ...] = (
            ("src", _num_literal(screen_id)),
        )
        new_head = NodeHead(
            head_kind=root_node.head.head_kind,
            type_or_path=root_node.head.type_or_path,
            scope_alias=root_node.head.scope_alias,
            eid=root_node.head.eid,
            alias=root_node.head.alias,
            override_args=root_node.head.override_args,
            positional=root_node.head.positional,
            properties=root_node.head.properties,
            trailer=NodeTrailer(kind="extracted", attrs=attrs),
        )
        root_node = Node(head=new_head, block=root_node.block)

    return L3Document(
        namespace=None,
        uses=(),
        tokens=(),
        top_level=(root_node,),
        warnings=tuple(swap_warnings),
        source_path=None,
    )
