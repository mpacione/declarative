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

# Primitive Figma types → dd-markup keywords (fallback when L1 is absent).
_NODE_TYPE_TO_KEYWORD = {
    "FRAME": "frame",
    "TEXT": "text",
    "RECTANGLE": "rectangle",
    "VECTOR": "vector",
    "ELLIPSE": "ellipse",
    "GROUP": "group",
    "BOOLEAN_OPERATION": "boolean-operation",
    "LINE": "line",
    "STAR": "star",
    "POLYGON": "polygon",
    "INSTANCE": "frame",                 # fallback when no component key resolves
}


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
    """Wrap a number in a canonical-form Literal_."""
    # Prefer int when lossless for canonical short emission
    if isinstance(n, bool):
        raw = "true" if n else "false"
        return Literal_(lit_kind="bool", raw=raw, py=n)
    if isinstance(n, float) and n.is_integer() and abs(n) < 1e16:
        n = int(n)
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


def _spatial_props(layout: dict) -> list[PropAssign]:
    """Derive Spatial-axis PropAssigns from a CompositionSpec element's
    `layout` sub-dict. Omits zero/default values per §2.5."""
    props: list[PropAssign] = []
    # Position — only non-zero for absolute children
    position = layout.get("position") or {}
    if isinstance(position, dict):
        x = position.get("x")
        y = position.get("y")
        if x is not None and x != 0:
            props.append(PropAssign(key="x", value=_num_literal(x)))
        if y is not None and y != 0:
            props.append(PropAssign(key="y", value=_num_literal(y)))
        elif x is not None and x == 0 and position.get("y", 0) != 0:
            props.append(PropAssign(key="x", value=_num_literal(0)))

    # Sizing
    sizing = layout.get("sizing") or {}
    if isinstance(sizing, dict):
        w = sizing.get("width")
        h = sizing.get("height")
        wv = _sizing_value(w) if w is not None else None
        hv = _sizing_value(h) if h is not None else None
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

    # Radius (uniform only in MVP)
    cr = visual.get("cornerRadius")
    if isinstance(cr, (int, float)) and cr > 0:
        props.append(PropAssign(key="radius", value=_num_literal(cr)))

    # Opacity (non-default)
    op = visual.get("opacity")
    if isinstance(op, (int, float)) and op < 1.0:
        props.append(PropAssign(key="opacity", value=_num_literal(op)))

    return props


def _content_props(element: dict) -> list[PropAssign]:
    """Text-bearing nodes carry positional content via the type-specific
    `text` / `characters` field. In the CompositionSpec this appears as
    `"text": "..."` when `type == text`; emitted as the node's
    `positional` content by the caller, not as a PropAssign."""
    return []


# ---------------------------------------------------------------------------
# Element → Node
# ---------------------------------------------------------------------------


def _auto_eid(type_kw: str, sibling_index: int) -> str:
    return f"{type_kw}-{sibling_index}"


def _compress_element(
    eid_key: str,
    spec: dict,
    parent_sibling_counter: dict[str, int],
    used_eids: set[str],
    comp_names: dict[str, str],
) -> Optional[Node]:
    """Turn a CompositionSpec element dict into an AST Node.

    `eid_key` is the element's spec key (e.g., `"screen-1"`, `"frame-3"`).
    `comp_names` maps element-id → master component name (from CKR) for
    Mode-1-eligible elements; an empty string signals "lookup failed,
    fall back to inline frame".
    Returns None if the element has no usable type.
    """
    element = spec["elements"].get(eid_key)
    if not element:
        return None

    # CompositionSpec uses underscore-delimited type strings (e.g.
    # `"boolean_operation"` from `node_type.lower()`); dd markup uses
    # the hyphen-delimited form (grammar §2.7). Normalize here.
    raw_type = element.get("type", "frame")
    type_str = raw_type.replace("_", "-") if isinstance(raw_type, str) else "frame"

    # EID: prefer sanitized original name, fall back to auto-id
    original_name = element.get("_original_name", "")
    eid_candidate = normalize_to_eid(original_name) if original_name else ""
    if eid_candidate and eid_candidate not in used_eids:
        eid = eid_candidate
    else:
        parent_sibling_counter[type_str] = parent_sibling_counter.get(type_str, 0) + 1
        eid = _auto_eid(type_str, parent_sibling_counter[type_str])
        # Ensure auto-id doesn't collide either
        while eid in used_eids:
            parent_sibling_counter[type_str] += 1
            eid = _auto_eid(type_str, parent_sibling_counter[type_str])
    used_eids.add(eid)

    # Mode-1 eligible nodes with a resolved CKR master name emit as a
    # CompRef (`-> slash/path`). Lookup miss → fall back to inline type.
    head_kind = "type"
    type_or_path = type_str
    master_name = comp_names.get(eid_key, "")
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
    props.extend(_spatial_props(element.get("layout") or {}))
    props.extend(_visual_props(element.get("visual") or {}))
    props.extend(visible_prop)

    # Positional content for text nodes
    positional: Optional[Value] = None
    if type_str == "text":
        txt = element.get("text") or element.get("characters")
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

    # Children
    child_ids = element.get("children") or []
    child_counter: dict[str, int] = {}
    child_nodes: list[Node] = []
    for child_id in child_ids:
        child_node = _compress_element(
            child_id, spec, child_counter, used_eids, comp_names,
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
    root_key = spec.get("root")
    if not root_key:
        return L3Document(namespace=None)

    used_eids: set[str] = set()
    root_counter: dict[str, int] = {}
    comp_names = _build_comp_names_map(spec, conn)
    root_node = _compress_element(
        root_key, spec, root_counter, used_eids, comp_names,
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
        warnings=(),
        source_path=None,
    )
