"""Plan B Stage 1.5 — L3 AST → dict IR decompressor.

Inverse of `dd.compress_l3.compress_to_l3`. Takes an `L3Document` AST
and produces a CompositionSpec dict IR in the shape
`dd.ir.generate_ir(..., semantic=True)` returns.

Together, the two form Tier-2 round-trip:

    ast_to_dict_ir(compress_to_l3(spec)) ≈ spec

(semantic equivalence, not byte-exact — provenance trailers,
auto-generated element keys, and warnings are compiler concerns that
don't round-trip through the dict IR.)

Stage 1.5 scope (skeleton MVP):
- Re-expand the synthetic `screen-1` wrapper dropped by
  `_collapse_synthetic_screen_wrapper`.
- Type keyword decoding (`screen`, `frame`, `text`, `rectangle`,
  `container`, `card`, `button`).
- CompRef head (`-> slash/path`) → `_mode1_eligible=true` leaf.
- Spatial axis: `x`, `y`, `width`, `height`, `layout`, `gap`,
  `padding`, `mainAxis`, `crossAxis`, `align`.
- Visual axis: single `fill=<hex|gradient|image>`, `stroke`,
  `stroke-weight`, `radius` (scalar + per-corner PropGroup),
  `shadow=shadow(...)`, `opacity`, `visible`.
- Text content: `text "..."` positional on TEXT/HEADING nodes.

DEFERRED (follow-up slices):
- Instance-override re-materialization (Stage 1.6).
- Master-subtree expansion for CompRefs (Stage 1.7).
- Token bindings.
- Multi-fill / multi-stroke / multi-shadow arrays.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from dd.markup_l3 import (
    Block,
    ComponentRefValue,
    FunctionCall,
    L3Document,
    Literal_,
    Node,
    PathOverride,
    PatternRefValue,
    PropAssign,
    PropGroup,
    SizingValue,
    TokenRef,
    Value,
)


# ---------------------------------------------------------------------------
# Inverse enum maps — grammar §7.4 canonical values back to the dict-IR
# lowercase Figma enum that `dd.ir.generate_ir` emits.
# ---------------------------------------------------------------------------


_MAIN_AXIS_GRAMMAR_TO_SPEC = {
    "start": "min",
    "center": "center",
    "end": "max",
    "space-between": "space_between",
    "space-around": "space_around",
    "space-evenly": "space_evenly",
}

_CROSS_AXIS_GRAMMAR_TO_SPEC = {
    "start": "min",
    "center": "center",
    "end": "max",
    "stretch": "stretch",
    "baseline": "baseline",
}


# ---------------------------------------------------------------------------
# dd-markup key → `instance_overrides` (property_type, property_name) map.
# Used by the `_self_overrides` channel to tag each entry with its DB
# column values so Stage 1.7 can directly re-materialize rows.
#
# Keys with no entry here are spec-derived (e.g. `x`, `y`, `position`) —
# those got computed by `dd.ir.generate_ir` from the node's parent-
# relative coordinates and don't correspond to DB overrides. Stage 1.7
# will filter on `db_prop_type is None` when rebuilding rows.
# ---------------------------------------------------------------------------


_SCALAR_KEY_TO_DB_MAP: dict[str, tuple[str, str]] = {
    "visible": ("BOOLEAN", ":self:visible"),
    "height": ("HEIGHT", ":self:height"),
    "radius": ("CORNER_RADIUS", ":self:cornerRadius"),
    "opacity": ("OPACITY", ":self:opacity"),
    "gap": ("ITEM_SPACING", ":self:itemSpacing"),
    "stroke-weight": ("STROKE_WEIGHT", ":self:strokeWeight"),
    "fill": ("FILLS", ":self:fills"),
    "stroke": ("STROKES", ":self:strokes"),
    "shadow": ("EFFECTS", ":self:effects"),
    "mainAxis": ("PRIMARY_ALIGN", ":self:primaryAxisAlignItems"),
}


_PADDING_KEY_TO_DB_MAP: dict[str, tuple[str, str]] = {
    "top": ("PADDING_TOP", ":self:paddingTop"),
    "right": ("PADDING_RIGHT", ":self:paddingRight"),
    "bottom": ("PADDING_BOTTOM", ":self:paddingBottom"),
    "left": ("PADDING_LEFT", ":self:paddingLeft"),
}


def _tag_and_fan_out_override(
    pa: PropAssign,
) -> list[dict[str, Any]]:
    """Convert a single head-level PropAssign into one or more
    `_self_overrides` entries, each tagged with the DB
    (`property_type`, `property_name`) pair when the key maps to a
    known `instance_overrides` column.

    Fan-out rule: padding PropGroup → one entry per side (each with
    its own `PADDING_{SIDE}` property_type).

    Polymorphic-type rule: `width` is either `WIDTH` (numeric) or
    `LAYOUT_SIZING_H` (SizingValue enum) depending on the Value
    shape. Resolved here at capture time so Stage 1.7 doesn't need
    type-dispatch logic.

    Entries with no matching DB column get `db_prop_type=None` /
    `db_prop_name=None` — typically spec-derived properties (x, y,
    position) that `generate_ir` computed rather than loaded from
    `instance_overrides`.
    """
    out: list[dict[str, Any]] = []

    # Padding fan-out — each side becomes its own override entry.
    if pa.key == "padding" and isinstance(pa.value, PropGroup):
        for entry in pa.value.entries:
            db_pair = _PADDING_KEY_TO_DB_MAP.get(entry.key)
            out.append({
                "key": f"padding.{entry.key}",
                "value": _override_value_repr(entry.value),
                "db_prop_type": db_pair[0] if db_pair else None,
                "db_prop_name": db_pair[1] if db_pair else None,
            })
        return out

    # Width is polymorphic: number Literal_ → WIDTH, SizingValue →
    # LAYOUT_SIZING_H.
    if pa.key == "width":
        if isinstance(pa.value, SizingValue):
            db_pair: Optional[tuple[str, str]] = (
                "LAYOUT_SIZING_H", ":self:layoutSizingH",
            )
        else:
            db_pair = ("WIDTH", ":self:width")
        out.append({
            "key": pa.key,
            "value": _override_value_repr(pa.value),
            "db_prop_type": db_pair[0],
            "db_prop_name": db_pair[1],
        })
        return out

    # Scalar-map lookup.
    db_pair = _SCALAR_KEY_TO_DB_MAP.get(pa.key)
    out.append({
        "key": pa.key,
        "value": _override_value_repr(pa.value),
        "db_prop_type": db_pair[0] if db_pair else None,
        "db_prop_name": db_pair[1] if db_pair else None,
    })
    return out


# Layout direction keywords — grammar `horizontal`/`vertical`/`stacked`
# map to the spec's `horizontal`/`vertical`/`stacked` (no change).
# `absolute` is the screen wrapper's placeholder direction.
_LAYOUT_DIRECTION = {
    "horizontal": "horizontal",
    "vertical": "vertical",
    "stacked": "stacked",
    "absolute": "absolute",
}


# ---------------------------------------------------------------------------
# Value decoders
# ---------------------------------------------------------------------------


def _literal_py(v: Value) -> Any:
    """Extract the Python value from a `Literal_` (identity for other
    Value kinds — caller must handle FunctionCall / PropGroup / etc.
    itself)."""
    if isinstance(v, Literal_):
        return v.py
    return None


def _fill_value_to_dict(v: Value) -> Optional[dict]:
    """Convert a dd-markup fill Value back into a spec-normalized
    fill dict (the shape the IR's `visual.fills[0]` uses)."""
    if isinstance(v, Literal_) and v.lit_kind == "hex-color":
        return {"type": "solid", "color": str(v.py)}
    if isinstance(v, FunctionCall):
        if v.name == "gradient-linear":
            stops: list[dict] = []
            for arg in v.args:
                if (
                    isinstance(arg.value, Literal_)
                    and arg.value.lit_kind == "hex-color"
                ):
                    stops.append({"color": str(arg.value.py)})
            return {"type": "gradient-linear", "stops": stops}
        if v.name == "image":
            for arg in v.args:
                if arg.name == "asset":
                    if isinstance(arg.value, Literal_):
                        return {
                            "type": "image",
                            "asset_hash": str(arg.value.py),
                        }
    return None


def _shadow_function_to_dict(v: Value) -> Optional[dict]:
    """Convert a `shadow(x, y, blur, color)` FunctionCall back into
    the spec-normalized effect dict shape."""
    if not isinstance(v, FunctionCall) or v.name != "shadow":
        return None
    out: dict = {"type": "drop-shadow", "visible": True}
    for arg in v.args:
        val = _literal_py(arg.value)
        if arg.name == "x":
            out.setdefault("offset", {})["x"] = val
        elif arg.name == "y":
            out.setdefault("offset", {})["y"] = val
        elif arg.name == "blur":
            out["radius"] = val
        elif arg.name == "color":
            out["color"] = val
    return out


def _override_value_repr(v: Value) -> Any:
    """Serialize a PropAssign Value into a JSON-friendly form for
    the `_self_overrides` channel. Preserves enough structure to
    re-materialize an `instance_overrides` row downstream.

    - `Literal_` → its `py` payload.
    - `PropGroup` → dict of entry.key → `_override_value_repr(value)`.
    - `FunctionCall` → dict `{fn: name, args: [{name, value}, ...]}`.
    - `SizingValue` → dict `{sizing: kind, min?: N, max?: N}` —
      preserves any bounded-sizing min/max.
    - `TokenRef` → dict `{token: path, scope_alias?: str}` — matches
      grammar §6 token reference form.
    - `ComponentRefValue` / `PatternRefValue` → dict
      `{comp_ref|pattern_ref: path, ...}` — deep slot-default refs.
    - `Node` (slot-default NodeExpr) — unhandled at this layer; emit
      a placeholder `{node_head: <type>}` so JSON-ser stays clean.
    - Anything else → `{"_unhandled": class_name}` so downstream can
      detect the drop (never `repr()` — that leaks non-JSON strings).
    """
    if isinstance(v, Literal_):
        return v.py
    if isinstance(v, PropGroup):
        return {
            e.key: _override_value_repr(e.value) for e in v.entries
        }
    if isinstance(v, FunctionCall):
        return {
            "fn": v.name,
            "args": [
                {"name": a.name, "value": _override_value_repr(a.value)}
                for a in v.args
            ],
        }
    if isinstance(v, SizingValue):
        out: dict[str, Any] = {"sizing": v.size_kind}
        if v.min is not None:
            out["min"] = v.min
        if v.max is not None:
            out["max"] = v.max
        return out
    if isinstance(v, TokenRef):
        token_dict: dict[str, Any] = {"token": v.path}
        if v.scope_alias is not None:
            token_dict["scope_alias"] = v.scope_alias
        return token_dict
    if isinstance(v, ComponentRefValue):
        return {
            "comp_ref": v.path,
            "scope_alias": v.scope_alias,
            "override_args": [
                {"key": oa.key, "value": _override_value_repr(oa.value)}
                for oa in v.override_args
            ],
        }
    if isinstance(v, PatternRefValue):
        pr_dict: dict[str, Any] = {"pattern_ref": v.path}
        if v.scope_alias is not None:
            pr_dict["scope_alias"] = v.scope_alias
        return pr_dict
    if isinstance(v, Node):
        return {"node_head": v.head.type_or_path, "eid": v.head.eid}
    return {"_unhandled": type(v).__name__}


def _sizing_dict_value(v: Value) -> Any:
    """Convert a sizing PropAssign value back into the spec-IR shape:
    numeric for px, string for fill/hug, dict for bounded min/max."""
    if isinstance(v, SizingValue):
        if v.size_kind in ("fill", "hug"):
            return v.size_kind
        return v.size_kind          # fallback — shouldn't happen
    if isinstance(v, Literal_) and v.lit_kind == "number":
        return v.py
    return None


# ---------------------------------------------------------------------------
# Node → element dict
# ---------------------------------------------------------------------------


class _DecompressCtx:
    """Running state shared across the recursive walk. Generates
    sibling-counter element keys (`frame-1`, `frame-2`, ...) and
    accumulates the elements dict."""

    def __init__(self, conn: Optional[sqlite3.Connection] = None) -> None:
        self.elements: dict[str, dict] = {}
        self.type_counter: dict[str, int] = {}
        self.conn = conn
        # slash_path → master root node_id, populated lazily on first
        # CompRef lookup. Avoids O(CKR × CompRefs) rescans across the
        # corpus sweep (129 CKR rows × ~100 CompRefs per screen × 204
        # screens = ~2.6M Python string ops without the cache).
        self._master_root_cache: Optional[dict[str, Optional[int]]] = None
        # component_key → master root node_id (analogous cache for
        # the nested-INSTANCE inflation path, keyed by the column
        # value INSTANCE nodes carry).
        self._ckr_key_cache: Optional[dict[str, Optional[int]]] = None
        # Master root node_ids currently being inflated — prevents
        # runaway recursion when a master contains a (hypothetical)
        # instance of itself.
        self.visiting_masters: set[int] = set()

    def next_key(self, type_kw: str) -> str:
        n = self.type_counter.get(type_kw, 0) + 1
        self.type_counter[type_kw] = n
        return f"{type_kw}-{n}"

    def resolve_master_root(self, slash_path: str) -> Optional[int]:
        """Cached lookup from slash-path to master root node_id.
        Builds the full CKR → slash-path map on first call."""
        if self.conn is None:
            return None
        if self._master_root_cache is None:
            self._master_root_cache = _build_master_root_cache(self.conn)
        return self._master_root_cache.get(slash_path)

    def resolve_master_root_by_ck(
        self, component_key: str,
    ) -> Optional[int]:
        """Cached lookup from component_key (the SHA INSTANCE nodes
        carry) to master root node_id. Used by the nested-INSTANCE
        inflation path."""
        if self.conn is None or not component_key:
            return None
        if self._ckr_key_cache is None:
            self._ckr_key_cache = _build_ckr_key_cache(self.conn)
        return self._ckr_key_cache.get(component_key)


# ---------------------------------------------------------------------------
# Master-subtree expansion — Stage 1.7
# ---------------------------------------------------------------------------
#
# When a CompRef is encountered, look up the master component's node-id
# via `component_key_registry.name == slash_path` and inflate the
# master's subtree as the CompRef element's children. This matches the
# shape `dd.ir.generate_ir` originally produced before compression
# dropped the master-subtree children.
#
# Scope for Stage 1.7 MVP:
# - Resolve master by slash-path name match (CKR.name).
# - Walk descendants via `nodes.parent_id` (depth-first, sort_order).
# - Emit lightweight element dicts (type, layout.position + sizing,
#   visual.fills/strokes/radius/opacity, text content).
# - Use the same `_DecompressCtx.next_key` counter scheme.
# - Nested CompRef inside master (i.e., a master that contains
#   instances of other components) recurses via the same pathway.
#
# Explicit non-goals (deferred):
# - Applying `:self:*` overrides onto the inflated root (the overrides
#   stay in `_self_overrides`; renderers choose which takes precedence).
# - Applying child-path overrides (`;figmaId:...`) to specific
#   descendant nodes.
# - Synthetic-node filtering / semantic-tree collapses.
# ---------------------------------------------------------------------------


_LAYOUT_MODE_TO_SPEC_DIRECTION = {
    "HORIZONTAL": "horizontal",
    "VERTICAL": "vertical",
    # NULL / NONE in DB → "stacked" (no auto-layout)
    None: "stacked",
    "NONE": "stacked",
}


def _build_ckr_key_cache(
    conn: sqlite3.Connection,
) -> dict[str, Optional[int]]:
    """Build a `{component_key: master_root_node_id}` map. Analogous
    to `_build_master_root_cache` but keyed by the SHA that INSTANCE
    nodes carry in `nodes.component_key`, rather than the sanitized
    slash-path."""
    rows = conn.execute(
        "SELECT component_key, figma_node_id FROM component_key_registry "
        "WHERE figma_node_id IS NOT NULL AND component_key IS NOT NULL"
    ).fetchall()
    ck_to_fnid: dict[str, str] = {ck: fnid for ck, fnid in rows}
    if not ck_to_fnid:
        return {}
    fnids = list(ck_to_fnid.values())
    placeholders = ",".join("?" for _ in fnids)
    node_rows = conn.execute(
        f"SELECT figma_node_id, id FROM nodes WHERE "
        f"figma_node_id IN ({placeholders})",
        fnids,
    ).fetchall()
    fnid_to_nid: dict[str, int] = {fnid: int(nid) for fnid, nid in node_rows}
    return {
        ck: fnid_to_nid.get(fnid)
        for ck, fnid in ck_to_fnid.items()
    }


def _build_master_root_cache(
    conn: sqlite3.Connection,
) -> dict[str, Optional[int]]:
    """Build a `{slash_path: master_root_node_id}` map for every
    resolvable CompRef. One CKR scan + one batched nodes lookup.

    Behavior:
    - CKR rows with NULL `figma_node_id` are skipped (10 such rows
      in the corpus — no master node in the DB; falling back to
      them silently hid CompRef inflation when they happened to
      match the slash-path first).
    - Slash-path collisions (10 real collisions in the corpus,
      including two rows collapsing to empty string `""`) aren't
      auto-resolved; we keep the FIRST figma_node_id encountered
      per path. Downstream that uses the cached map gets
      deterministic resolution instead of relying on SQLite's
      per-call row order.
    """
    from dd.compress_l3 import derive_comp_slash_path
    rows = conn.execute(
        "SELECT figma_node_id, name FROM component_key_registry "
        "WHERE figma_node_id IS NOT NULL"
    ).fetchall()
    slash_to_fnid: dict[str, str] = {}
    for fnid, name in rows:
        if not name:
            continue
        slash = derive_comp_slash_path(name)
        if not slash or slash in slash_to_fnid:
            continue
        slash_to_fnid[slash] = fnid
    if not slash_to_fnid:
        return {}
    # Resolve figma_node_ids to node_ids in ONE query.
    fnids = list(slash_to_fnid.values())
    placeholders = ",".join("?" for _ in fnids)
    node_rows = conn.execute(
        f"SELECT figma_node_id, id FROM nodes WHERE "
        f"figma_node_id IN ({placeholders})",
        fnids,
    ).fetchall()
    fnid_to_nid: dict[str, int] = {fnid: int(nid) for fnid, nid in node_rows}
    return {
        slash: fnid_to_nid.get(fnid)
        for slash, fnid in slash_to_fnid.items()
    }


def _raw_db_fills_to_visual_fills(raw_json: Optional[str]) -> list:
    """Convert nodes.fills JSON (raw Figma paint array) into the
    spec-normalized fill array. Drops hidden paints; first visible
    wins (matching `_visual_props` semantics)."""
    if not raw_json:
        return []
    try:
        paints = json.loads(raw_json)
    except (ValueError, TypeError):
        return []
    if not isinstance(paints, list):
        return []
    out: list = []
    for p in paints:
        norm = _normalize_raw_paint_for_master(p)
        if norm is not None:
            out.append(norm)
    return out


def _normalize_raw_paint_for_master(raw: dict) -> Optional[dict]:
    """Localized copy of the compressor's `_normalize_raw_paint` so the
    decompressor doesn't depend on compressor-internal imports. Keeps
    the two modules decoupled."""
    if not isinstance(raw, dict):
        return None
    if raw.get("visible") is False:
        return None
    typ = raw.get("type", "")
    if typ in ("SOLID", "solid"):
        color = raw.get("color")
        if not isinstance(color, dict):
            return None
        op = raw.get("opacity")
        merged = dict(color)
        if isinstance(op, (int, float)) and op < 1.0:
            base_a = float(color.get("a", 1.0))
            merged["a"] = base_a * op
        return {"type": "solid", "color": _color_dict_to_hex_local(merged)}
    if typ == "GRADIENT_LINEAR":
        stops = []
        for s in raw.get("gradientStops") or []:
            c = s.get("color") if isinstance(s, dict) else None
            if isinstance(c, dict):
                stops.append({"color": _color_dict_to_hex_local(c)})
        return {"type": "gradient-linear", "stops": stops}
    if typ == "IMAGE":
        h = raw.get("imageHash")
        if isinstance(h, str):
            return {"type": "image", "asset_hash": h}
    return None


def _color_dict_to_hex_local(color: dict) -> str:
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


# Node types that are visual "leaves" — they don't carry a layout
# direction in the orig spec shape (only frames/components do).
_LEAF_NODE_TYPES = frozenset({
    "text", "rectangle", "ellipse", "line", "vector", "regular_polygon",
    "star", "boolean_operation",
})


def _db_row_to_element(
    row: dict, parent_row: Optional[dict],
) -> dict[str, Any]:
    """Translate a `nodes` table row into a spec-element dict."""
    raw_type = (row.get("node_type") or "frame").lower()
    element: dict[str, Any] = {"type": raw_type}
    name = row.get("name")
    if name:
        element["_original_name"] = name

    # Layout: direction (only for container-like types), sizing, position.
    layout: dict[str, Any] = {}
    if raw_type not in _LEAF_NODE_TYPES:
        lm = row.get("layout_mode")
        layout["direction"] = _LAYOUT_MODE_TO_SPEC_DIRECTION.get(lm, "stacked")
    w = row.get("width")
    h = row.get("height")
    sizing: dict[str, Any] = {}
    if w is not None:
        sizing["width"] = w
    if h is not None:
        sizing["height"] = h
    if sizing:
        layout["sizing"] = sizing
    # Position relative to parent.
    if parent_row is not None:
        px = (row.get("x") or 0) - (parent_row.get("x") or 0)
        py = (row.get("y") or 0) - (parent_row.get("y") or 0)
    else:
        px = row.get("x") or 0
        py = row.get("y") or 0
    if px != 0 or py != 0:
        layout["position"] = {"x": px, "y": py}
    if layout:
        element["layout"] = layout

    # Visual: fills, strokes, effects, radius, opacity.
    visual: dict[str, Any] = {}
    fills = _raw_db_fills_to_visual_fills(row.get("fills"))
    if fills:
        visual["fills"] = fills
    strokes = _raw_db_fills_to_visual_fills(row.get("strokes"))
    if strokes:
        # Mirror `dd/ir.py:143-156` — stroke dicts carry a `width`
        # field pulled from `stroke_weight` (defaulting to 1 when
        # the stroke exists but has no weight, matching generate_ir).
        stroke_weight = row.get("stroke_weight") or 1
        for s in strokes:
            s["width"] = int(stroke_weight)
        # stroke_align was missing — orig spec emits `align` on the
        # stroke dict via `dd/ir.py:155-157`.
        stroke_align = row.get("stroke_align")
        if isinstance(stroke_align, str):
            for s in strokes:
                s["align"] = stroke_align.lower()
        visual["strokes"] = strokes
    effects = _raw_db_effects_to_visual_effects(row.get("effects"))
    if effects:
        visual["effects"] = effects
    cr = _normalize_corner_radius(row.get("corner_radius"))
    if cr is not None:
        visual["cornerRadius"] = cr
    op = row.get("opacity")
    if isinstance(op, (int, float)) and op < 1.0:
        visual["opacity"] = op
    if visual:
        element["visual"] = visual

    # Text content.
    text = row.get("text_content")
    if isinstance(text, str) and text:
        element.setdefault("props", {})["text"] = text

    # Visibility (only when false).
    if row.get("visible") == 0:
        element["visible"] = False

    return element


def _raw_db_effects_to_visual_effects(raw_json: Optional[str]) -> list:
    """Convert nodes.effects JSON into the spec-normalized effect array.
    Mirrors `dd/ir.py:163-215`'s `normalize_effects` minus the binding
    resolution (overrides aren't applied during master-subtree walk).
    """
    if not raw_json:
        return []
    try:
        effects = json.loads(raw_json)
    except (ValueError, TypeError):
        return []
    if not isinstance(effects, list):
        return []
    out: list = []
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        if effect.get("visible") is False:
            continue
        etype = effect.get("type", "")
        if etype in ("DROP_SHADOW", "INNER_SHADOW"):
            color = effect.get("color", {})
            offset = effect.get("offset", {})
            out.append({
                "type": (
                    "drop-shadow" if etype == "DROP_SHADOW"
                    else "inner-shadow"
                ),
                "color": (
                    _color_dict_to_hex_local(color)
                    if isinstance(color, dict) else "#000000"
                ),
                "offset": {
                    "x": offset.get("x", 0) if isinstance(offset, dict) else 0,
                    "y": offset.get("y", 0) if isinstance(offset, dict) else 0,
                },
                "blur": effect.get("radius", 0),
                "spread": effect.get("spread", 0),
            })
        elif etype in ("LAYER_BLUR", "BACKGROUND_BLUR"):
            out.append({
                "type": (
                    "layer-blur" if etype == "LAYER_BLUR"
                    else "background-blur"
                ),
                "radius": effect.get("radius", 0),
            })
    return out


def _normalize_corner_radius(cr: Any) -> Any:
    """Handle both scalar (uniform) and dict (per-corner) corner
    radius. The nodes.corner_radius column can be a number OR a JSON
    string encoding `{"tl": N, "tr": N, "bl": N, "br": N}`."""
    if isinstance(cr, (int, float)) and cr > 0:
        return cr
    if isinstance(cr, str):
        try:
            parsed = json.loads(cr)
        except (ValueError, TypeError):
            return None
        if isinstance(parsed, dict) and parsed:
            return parsed
        if isinstance(parsed, (int, float)) and parsed > 0:
            return parsed
    return None


_MASTER_COLS = (
    "id", "parent_id", "name", "node_type", "x", "y", "width", "height",
    "layout_mode", "fills", "strokes", "effects", "corner_radius",
    "opacity", "stroke_weight", "stroke_align", "text_content", "visible",
    "sort_order", "component_key",
)


def _expand_master_subtree(
    slash_path: str, ctx: _DecompressCtx,
) -> list[str]:
    """Inflate the master component's subtree into `ctx.elements` and
    return the child element keys. Returns [] if the master cannot
    be resolved (CKR miss, slash-path not found, or no conn).
    """
    master_root_id = ctx.resolve_master_root(slash_path)
    if master_root_id is None:
        return []

    conn = ctx.conn
    assert conn is not None, "resolve_master_root returns None without conn"
    # Fetch master root + all descendants in ONE recursive CTE pass.
    # Sort by parent_id + sort_order so sibling order matches what
    # Figma / the screen extract saw. Previously used `id` which is
    # insertion order and can drift from sibling order.
    cols = ", ".join(_MASTER_COLS)
    rows = conn.execute(
        f"WITH RECURSIVE sub(id) AS ("
        f"  SELECT ? UNION ALL "
        f"  SELECT n.id FROM nodes n JOIN sub ON n.parent_id = sub.id"
        f") "
        f"SELECT {cols} FROM nodes WHERE id IN (SELECT id FROM sub) "
        f"ORDER BY parent_id, sort_order, id",
        (master_root_id,),
    ).fetchall()
    if not rows:
        return []

    by_id: dict[int, dict] = {
        row[0]: dict(zip(_MASTER_COLS, row)) for row in rows
    }
    master_row = by_id.get(master_root_id)
    if master_row is None:
        return []

    # Index children by parent (preserving the ORDER BY sort order).
    children_by_parent: dict[int, list[dict]] = {}
    for row in rows:
        pid = row[1]
        if pid is not None and pid in by_id:
            children_by_parent.setdefault(pid, []).append(
                dict(zip(_MASTER_COLS, row))
            )

    def walk(row: dict, parent_row: Optional[dict]) -> str:
        element = _db_row_to_element(row, parent_row)
        is_instance = (row.get("node_type") or "").upper() == "INSTANCE"
        if is_instance:
            element["_mode1_eligible"] = True
        key = ctx.next_key(element["type"])

        # Direct descendants in the same subtree.
        child_keys: list[str] = []
        for crow in children_by_parent.get(row["id"], []):
            child_keys.append(walk(crow, row))

        # Nested CompRef re-inflation: an INSTANCE row inside a master
        # subtree typically has no DB descendants of its own (its
        # children live under a DIFFERENT master). Look up its own
        # master via `component_key` and inflate recursively, with
        # cycle detection.
        if is_instance and not child_keys:
            ck = row.get("component_key")
            if isinstance(ck, str) and ck:
                inner_master_id = ctx.resolve_master_root_by_ck(ck)
                if (
                    inner_master_id is not None
                    and inner_master_id not in ctx.visiting_masters
                ):
                    ctx.visiting_masters.add(inner_master_id)
                    try:
                        child_keys = _expand_master_by_root_id(
                            inner_master_id, ctx,
                        )
                    finally:
                        ctx.visiting_masters.discard(inner_master_id)

        if child_keys:
            element["children"] = child_keys
        ctx.elements[key] = element
        return key

    result_keys: list[str] = []
    for crow in children_by_parent.get(master_root_id, []):
        result_keys.append(walk(crow, master_row))
    return result_keys


def _expand_master_by_root_id(
    master_root_id: int, ctx: _DecompressCtx,
) -> list[str]:
    """Inflate a master's direct children given the master's root
    node_id directly (bypassing the slash-path resolution step).
    Used by the nested-INSTANCE recursion path."""
    conn = ctx.conn
    if conn is None:
        return []
    cols = ", ".join(_MASTER_COLS)
    rows = conn.execute(
        f"WITH RECURSIVE sub(id) AS ("
        f"  SELECT ? UNION ALL "
        f"  SELECT n.id FROM nodes n JOIN sub ON n.parent_id = sub.id"
        f") "
        f"SELECT {cols} FROM nodes WHERE id IN (SELECT id FROM sub) "
        f"ORDER BY parent_id, sort_order, id",
        (master_root_id,),
    ).fetchall()
    if not rows:
        return []
    by_id: dict[int, dict] = {
        row[0]: dict(zip(_MASTER_COLS, row)) for row in rows
    }
    master_row = by_id.get(master_root_id)
    if master_row is None:
        return []
    children_by_parent: dict[int, list[dict]] = {}
    for row in rows:
        pid = row[1]
        if pid is not None and pid in by_id:
            children_by_parent.setdefault(pid, []).append(
                dict(zip(_MASTER_COLS, row))
            )

    def walk_inner(row: dict, parent_row: Optional[dict]) -> str:
        element = _db_row_to_element(row, parent_row)
        is_inner_instance = (
            (row.get("node_type") or "").upper() == "INSTANCE"
        )
        if is_inner_instance:
            element["_mode1_eligible"] = True
        key = ctx.next_key(element["type"])
        child_keys: list[str] = []
        for crow in children_by_parent.get(row["id"], []):
            child_keys.append(walk_inner(crow, row))
        if is_inner_instance and not child_keys:
            ck = row.get("component_key")
            if isinstance(ck, str) and ck:
                deeper_master_id = ctx.resolve_master_root_by_ck(ck)
                if (
                    deeper_master_id is not None
                    and deeper_master_id not in ctx.visiting_masters
                ):
                    ctx.visiting_masters.add(deeper_master_id)
                    try:
                        child_keys = _expand_master_by_root_id(
                            deeper_master_id, ctx,
                        )
                    finally:
                        ctx.visiting_masters.discard(deeper_master_id)
        if child_keys:
            element["children"] = child_keys
        ctx.elements[key] = element
        return key

    result_keys: list[str] = []
    for crow in children_by_parent.get(master_root_id, []):
        result_keys.append(walk_inner(crow, master_row))
    return result_keys


def _props_by_key(props: tuple[PropAssign, ...]) -> dict[str, PropAssign]:
    return {p.key: p for p in props}


def _decode_layout(
    props: dict[str, PropAssign], element: dict,
    *, is_screen_root: bool = False, is_compref: bool = False,
    type_kw: str = "",
) -> None:
    """Populate `element["layout"]` from head-level PropAssigns.

    Direction default logic:
    - If `layout=` prop is present: decode directly.
    - If absent on a SCREEN root: default to `"absolute"` (matches
      `generate_ir`'s synthetic-wrapper shape, `dd/ir.py:1371`).
    - If absent on a CompRef: omit direction entirely (master owns
      the layout axis in the spec IR; CompRefs typically carry no
      direction of their own).
    - If absent on a leaf type (text/rectangle/vector/etc.): omit
      direction entirely (leaves have no auto-layout axis).
    - If absent on any other inline frame-like node: default to
      `"stacked"` (the spec sentinel for "no auto-layout").
    """
    layout: dict = element.setdefault("layout", {})

    if "layout" in props:
        v = props["layout"].value
        if isinstance(v, Literal_) and v.lit_kind == "enum":
            direction = _LAYOUT_DIRECTION.get(str(v.py))
            if direction is not None:
                layout["direction"] = direction
    else:
        if is_screen_root:
            layout["direction"] = "absolute"
        elif is_compref or type_kw in _LEAF_NODE_TYPES:
            pass                              # no direction (master-owned or leaf)
        else:
            layout["direction"] = "stacked"

    # Sizing (width, height)
    sizing: dict = {}
    if "width" in props:
        w = _sizing_dict_value(props["width"].value)
        if w is not None:
            sizing["width"] = w
    if "height" in props:
        h = _sizing_dict_value(props["height"].value)
        if h is not None:
            sizing["height"] = h
    if sizing:
        layout["sizing"] = sizing

    # Position (x, y)
    position: dict = {}
    if "x" in props:
        x = _literal_py(props["x"].value)
        if isinstance(x, (int, float)):
            position["x"] = x
    if "y" in props:
        y = _literal_py(props["y"].value)
        if isinstance(y, (int, float)):
            position["y"] = y
    if position:
        layout["position"] = position

    # Gap
    if "gap" in props:
        g = _literal_py(props["gap"].value)
        if isinstance(g, (int, float)):
            layout["gap"] = g

    # Padding PropGroup → layout.padding dict
    if "padding" in props:
        pv = props["padding"].value
        if isinstance(pv, PropGroup):
            pad: dict = {}
            for entry in pv.entries:
                v = _literal_py(entry.value)
                if isinstance(v, (int, float)):
                    pad[entry.key] = v
            if pad:
                layout["padding"] = pad

    # Alignment. `align=center` is the §7.4 shorthand for both axes.
    if "align" in props:
        a = _literal_py(props["align"].value)
        if a == "center":
            layout["mainAxisAlignment"] = "center"
            layout["crossAxisAlignment"] = "center"
    if "mainAxis" in props:
        ma = _literal_py(props["mainAxis"].value)
        if ma in _MAIN_AXIS_GRAMMAR_TO_SPEC:
            layout["mainAxisAlignment"] = _MAIN_AXIS_GRAMMAR_TO_SPEC[ma]
    if "crossAxis" in props:
        ca = _literal_py(props["crossAxis"].value)
        if ca in _CROSS_AXIS_GRAMMAR_TO_SPEC:
            layout["crossAxisAlignment"] = _CROSS_AXIS_GRAMMAR_TO_SPEC[ca]

    if not layout:
        element.pop("layout", None)


def _decode_visual(
    props: dict[str, PropAssign], element: dict,
) -> None:
    """Populate `element["visual"]` from head-level PropAssigns."""
    visual: dict = {}

    if "fill" in props:
        fv = _fill_value_to_dict(props["fill"].value)
        if fv is not None:
            visual["fills"] = [fv]

    if "stroke" in props:
        sv = _fill_value_to_dict(props["stroke"].value)
        if sv is not None:
            stroke_entry = dict(sv)
            if "stroke-weight" in props:
                w = _literal_py(props["stroke-weight"].value)
                if isinstance(w, (int, float)) and w > 0:
                    stroke_entry["width"] = w
            visual["strokes"] = [stroke_entry]

    if "shadow" in props:
        eff = _shadow_function_to_dict(props["shadow"].value)
        if eff is not None:
            visual["effects"] = [eff]

    if "radius" in props:
        rv = props["radius"].value
        if isinstance(rv, Literal_) and rv.lit_kind == "number":
            visual["cornerRadius"] = rv.py
        elif isinstance(rv, PropGroup):
            # Per-corner — emit as the spec's dict form if the IR uses
            # it. For MVP, take the maximum as a scalar uniform radius
            # (lossy but preserves single-value round-trip).
            per_corner: dict = {}
            for entry in rv.entries:
                v = _literal_py(entry.value)
                if isinstance(v, (int, float)):
                    per_corner[entry.key] = v
            if per_corner:
                visual["cornerRadius"] = per_corner

    if "opacity" in props:
        o = _literal_py(props["opacity"].value)
        if isinstance(o, (int, float)) and o < 1.0:
            visual["opacity"] = o

    if visual:
        element["visual"] = visual


def _decode_node(
    node: Node, ctx: _DecompressCtx,
) -> Optional[str]:
    """Recursively decompress a Node into an element dict, register
    it in `ctx.elements`, and return its element key."""
    head = node.head

    # Determine element type and whether this is a CompRef.
    is_compref = head.head_kind == "comp-ref"
    if is_compref:
        # CompRef — matches `dd.ir.generate_ir`'s Mode-1-eligible
        # INSTANCE shape (`type="instance"`, `_mode1_eligible=true`).
        # Using `frame` here creates a Tier-2-script-parity gap
        # because `generate_figma_script` dispatches on the `type`
        # field (see `dd/renderers/figma.py:ir_to_figma_type`).
        type_kw = "instance"
    else:
        type_kw = head.type_or_path

    # Element key — sibling-scoped counter. Prefer sanitized EID when
    # the caller cares about preserving it; for MVP we use the counter.
    key = ctx.next_key(type_kw)

    props = _props_by_key(head.properties)

    element: dict[str, Any] = {"type": type_kw}
    if is_compref:
        element["_mode1_eligible"] = True
        element["_master_slash_path"] = head.type_or_path
        # Stage 1.6 MVP — surface raw `:self:*` overrides as a
        # structured channel so downstream consumers can
        # re-materialize `instance_overrides`-shaped rows. Every
        # head-level PropAssign on a CompRef is a local override
        # of the master by definition (CompRefs inherit all
        # properties; anything on the head overrides the inherited
        # value). Excludes `$ext.*` diagnostics which have their
        # own channel.
        self_overrides: list[dict[str, Any]] = []
        for pa in head.properties:
            if pa.key.startswith("$ext."):
                continue
            # Each PropAssign may fan out into multiple entries
            # (padding PropGroup splits per side) and is tagged with
            # the corresponding `instance_overrides` DB columns when
            # the key has a known mapping.
            self_overrides.extend(_tag_and_fan_out_override(pa))
        # Capture block-level child-path overrides (`;figmaId:...=value`).
        # Stage 1.3/1.4 compressor flattens only `:self:*` rows;
        # child-path rows persist when the AST comes from another
        # source (e.g., hand-authored markup). Preserving them in the
        # same channel lets Stage 1.7 re-materialize them directly.
        if node.block is not None:
            for stmt in node.block.statements:
                if isinstance(stmt, PathOverride):
                    self_overrides.append({
                        "path": stmt.path,
                        "value": _override_value_repr(stmt.value),
                        "db_prop_type": None,
                        "db_prop_name": stmt.path,
                    })
        if self_overrides:
            element["_self_overrides"] = self_overrides
    if head.eid:
        # Approximate `_original_name` from the AST EID. Lossy (EID
        # is the sanitized, lowercased IDENT form — not the raw Figma
        # name) but reads back through `normalize_to_eid` identically,
        # so downstream key-preservation works.
        element["_original_name"] = head.eid

    _decode_layout(
        props, element,
        is_screen_root=(type_kw == "screen"),
        is_compref=is_compref,
        type_kw=type_kw,
    )
    _decode_visual(props, element)

    # Ext-props (`$ext.*` diagnostic PropAssigns emitted by the
    # compressor's override handlers — e.g. `$ext.shadow_all_hidden`,
    # `$ext.shadow_extra_count`). Preserve as a sub-dict on the
    # element so downstream tooling can read them; the sub-dict key
    # strips the `$ext.` prefix.
    ext_props: dict = {}
    for key_, pa in props.items():
        if key_.startswith("$ext."):
            ext_props[key_[len("$ext."):]] = _literal_py(pa.value)
    if ext_props:
        element["$ext"] = ext_props

    # Visibility
    if "visible" in props:
        vp = _literal_py(props["visible"].value)
        if vp is False:
            element["visible"] = False

    # Text content (positional on text/heading)
    if head.positional is not None:
        if (
            isinstance(head.positional, Literal_)
            and head.positional.lit_kind == "string"
        ):
            element.setdefault("props", {})["text"] = head.positional.py

    # Children
    child_keys: list[str] = []
    if node.block is not None:
        for stmt in node.block.statements:
            if isinstance(stmt, Node):
                child_key = _decode_node(stmt, ctx)
                if child_key is not None:
                    child_keys.append(child_key)

    # Stage 1.7 — CompRef master-subtree expansion. When a DB conn is
    # available, inflate the master component's direct children as
    # children of this CompRef element. Matches `dd.ir.generate_ir`'s
    # output shape where Mode-1 instances carry their full subtree.
    if is_compref and not child_keys and ctx.conn is not None:
        child_keys = _expand_master_subtree(head.type_or_path, ctx)

    if child_keys:
        element["children"] = child_keys

    ctx.elements[key] = element
    return key


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _reexpand_synthetic_wrapper(spec: dict) -> dict:
    """Inverse of the compressor's `_collapse_synthetic_screen_wrapper`.

    When the compressor emits a `screen` top-level with hoisted visual
    properties (fill, etc.) and direct canvas-level children, this
    function splits the single element back into the pair
    `generate_ir` originally produced:

        screen-1 (type=screen, direction=absolute, sizing only)
          └── frame-1 (type=frame, visual + layout + children)

    Keeps the synthetic `_original_name` on both elements so the shape
    matches `generate_ir` exactly.

    Heuristic for triggering: root.type == "screen" AND root has a
    `visual` dict OR root.layout contains more than just direction +
    sizing. Without hoisted properties the screen is already in the
    "bare wrapper" form and doesn't need re-expansion.
    """
    root_key = spec.get("root")
    elements = spec.get("elements")
    if not isinstance(root_key, str) or not isinstance(elements, dict):
        return spec
    root = elements.get(root_key)
    if not isinstance(root, dict) or root.get("type") != "screen":
        return spec

    has_visual = bool(root.get("visual"))
    root_layout = root.get("layout") or {}
    # "Non-trivial layout" = any layout key beyond direction+sizing,
    # OR a direction that's neither the "no auto-layout" default
    # (`absolute` / `stacked`) nor absent. The bare-wrapper shape
    # `generate_ir` produces has direction=absolute and nothing else,
    # so none of those trigger re-expansion.
    has_non_trivial_layout = any(
        k for k in root_layout.keys()
        if k not in ("direction", "sizing")
    ) or root_layout.get("direction") not in (None, "absolute", "stacked")
    if not (has_visual or has_non_trivial_layout):
        return spec

    # Build the inner frame carrying everything except the screen's
    # authoritative sizing.
    inner_key = "frame-1"
    # Avoid collision with existing keys.
    n = 1
    while inner_key in elements:
        n += 1
        inner_key = f"frame-{n}"

    # The inner frame carries the REAL layout (direction, padding,
    # alignment, gap). The outer screen only gets a placeholder
    # `direction=absolute` + sizing. Keep sizing on the inner too —
    # the canvas frame carries the same dimensions.
    inner_layout = dict(root_layout)
    inner: dict = {
        "type": "frame",
        "_mode1_eligible": False,
        "layout": inner_layout,
    }
    if root.get("visual"):
        inner["visual"] = root["visual"]
    if "_original_name" in root:
        inner["_original_name"] = root["_original_name"]
    # Inner child's position is 0,0 by definition.
    inner_layout.setdefault("position", {"x": 0, "y": 0})
    # Original children of the collapsed root become children of the
    # inner frame.
    if root.get("children"):
        inner["children"] = list(root["children"])

    # Rewrite the outer screen: strip visual, keep direction=absolute,
    # keep sizing, its only child is the inner frame.
    outer: dict = {
        "type": "screen",
        "layout": {
            "direction": "absolute",
            "sizing": dict(root_layout.get("sizing") or {}),
        },
        "children": [inner_key],
    }
    if "_original_name" in root:
        outer["_original_name"] = root["_original_name"]

    new_elements = dict(elements)
    new_elements[root_key] = outer
    new_elements[inner_key] = inner

    return {**spec, "elements": new_elements}


def ast_to_dict_ir(
    doc: L3Document,
    conn: Optional[sqlite3.Connection] = None,
    *,
    reexpand_screen_wrapper: bool = True,
) -> dict:
    """Decompress an `L3Document` AST into a CompositionSpec dict IR.

    Output shape matches `dd.ir.generate_ir(..., semantic=True)["spec"]`:

        {
            "version": "1.0",
            "root": "screen-1",
            "elements": {
                "screen-1": {type, layout, children, ...},
                ...
            },
        }

    When `conn` is provided, CompRef elements inflate their master
    component's subtree as children (Stage 1.7) — matching the shape
    `dd.ir.generate_ir` produced before compression dropped those
    children. Without `conn`, CompRefs remain leaves (Stage 1.5/1.6
    behavior).

    When `reexpand_screen_wrapper=True` (default), re-expands the
    synthetic screen→canvas-FRAME pair the compressor collapses — so
    the output structurally mirrors what `generate_ir` produced
    before compression. Pass `False` for the flat form (screen with
    hoisted visual + direct canvas grandchildren).

    Round-trip is semantic, not byte-exact: provenance trailers,
    auto-generated element keys, and compile-time warnings are
    compiler concerns that don't materialize in the dict IR.
    """
    empty_spec = {"version": "1.0", "root": None, "elements": {}}
    if not isinstance(doc, L3Document) or not doc.top_level:
        return empty_spec

    root_node = doc.top_level[0]
    if not isinstance(root_node, Node):
        return empty_spec

    ctx = _DecompressCtx(conn=conn)
    root_key = _decode_node(root_node, ctx)
    if root_key is None:
        return empty_spec

    spec = {
        "version": "1.0",
        "root": root_key,
        "elements": ctx.elements,
    }
    if reexpand_screen_wrapper:
        spec = _reexpand_synthetic_wrapper(spec)
    return spec
