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

from typing import Any, Optional

from dd.markup_l3 import (
    Block,
    FunctionCall,
    L3Document,
    Literal_,
    Node,
    PropAssign,
    PropGroup,
    SizingValue,
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

    def __init__(self) -> None:
        self.elements: dict[str, dict] = {}
        self.type_counter: dict[str, int] = {}

    def next_key(self, type_kw: str) -> str:
        n = self.type_counter.get(type_kw, 0) + 1
        self.type_counter[type_kw] = n
        return f"{type_kw}-{n}"


def _props_by_key(props: tuple[PropAssign, ...]) -> dict[str, PropAssign]:
    return {p.key: p for p in props}


def _decode_layout(
    props: dict[str, PropAssign], element: dict,
) -> None:
    """Populate `element["layout"]` from head-level PropAssigns."""
    layout: dict = element.setdefault("layout", {})

    # Direction (layout=<direction>)
    if "layout" in props:
        v = props["layout"].value
        if isinstance(v, Literal_) and v.lit_kind == "enum":
            direction = _LAYOUT_DIRECTION.get(str(v.py))
            if direction is not None:
                layout["direction"] = direction

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
        # CompRef — type is `frame`, slash-path is informational.
        type_kw = "frame"
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
    if head.eid:
        element["_original_name_eid"] = head.eid

    _decode_layout(props, element)
    _decode_visual(props, element)

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
    if node.block is not None:
        child_keys: list[str] = []
        for stmt in node.block.statements:
            if isinstance(stmt, Node):
                child_key = _decode_node(stmt, ctx)
                if child_key is not None:
                    child_keys.append(child_key)
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
    has_non_trivial_layout = any(
        k for k in root_layout.keys()
        if k not in ("direction", "sizing")
    ) or root_layout.get("direction") not in (None, "absolute")
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
    doc: L3Document, *, reexpand_screen_wrapper: bool = True,
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

    When `reexpand_screen_wrapper=True` (default), re-expands the
    synthetic screen→canvas-FRAME pair the compressor collapses — so
    the output structurally mirrors what `generate_ir` produced
    before compression. Pass `False` for the flat form (screen with
    hoisted visual + direct canvas grandchildren).

    Stage 1.5 MVP — handles the shapes the compressor can currently
    produce. Round-trip is semantic, not byte-exact: provenance
    trailers, auto-generated element keys, and compile-time warnings
    are compiler concerns that don't materialize in the dict IR.
    """
    empty_spec = {"version": "1.0", "root": None, "elements": {}}
    if not isinstance(doc, L3Document) or not doc.top_level:
        return empty_spec

    root_node = doc.top_level[0]
    if not isinstance(root_node, Node):
        return empty_spec

    ctx = _DecompressCtx()
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
