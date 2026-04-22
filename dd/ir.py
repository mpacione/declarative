"""CompositionSpec IR generation (T5 Phase 2).

Transforms classified screen data + token bindings into a platform-agnostic
intermediate representation. The IR is a normalized visual intent layer —
every element carries its complete visual description with token refs as
inline annotations where they exist, literal values where they don't.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from dd.classify_rules import is_synthetic_node, is_system_chrome
from dd.color import rgba_to_hex

# ---------------------------------------------------------------------------
# Visual property normalization (Figma JSON → IR format)
# ---------------------------------------------------------------------------

_GRADIENT_TYPE_MAP = {
    "GRADIENT_LINEAR": "gradient-linear",
    "GRADIENT_RADIAL": "gradient-radial",
    "GRADIENT_ANGULAR": "gradient-angular",
    "GRADIENT_DIAMOND": "gradient-diamond",
}


def _figma_color_to_hex(color: dict[str, float], paint_opacity: float = 1.0) -> str:
    r, g, b = color.get("r", 0), color.get("g", 0), color.get("b", 0)
    a = color.get("a", 1.0) * paint_opacity
    return rgba_to_hex(r, g, b, a)


def normalize_fills(
    raw_json: str | None, bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize Figma fills JSON to IR fill array.

    Handles SOLID and GRADIENT_* types. Skips invisible fills.
    Token bindings overlay as "{token.name}" where they exist.
    """
    if not raw_json or raw_json == "[]":
        return []

    try:
        fills = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return []

    binding_map = {b["property"]: b.get("token_name") for b in bindings if b.get("token_name")}
    result = []

    for i, fill in enumerate(fills):
        if fill.get("visible") is False:
            continue

        fill_type = fill.get("type", "")
        paint_opacity = fill.get("opacity", 1.0)

        if fill_type == "SOLID":
            color = fill.get("color", {})
            hex_val = _figma_color_to_hex(color, 1.0)
            token = binding_map.get(f"fill.{i}.color")
            entry: dict[str, Any] = {
                "type": "solid",
                "color": f"{{{token}}}" if token else hex_val,
            }
            if paint_opacity < 1.0:
                entry["opacity"] = paint_opacity
            result.append(entry)

        elif fill_type in _GRADIENT_TYPE_MAP:
            stops = []
            for j, stop in enumerate(fill.get("gradientStops", [])):
                stop_color = stop.get("color", {})
                stop_hex = _figma_color_to_hex(stop_color, 1.0)
                stop_token = binding_map.get(f"fill.{i}.gradient.stop.{j}.color")
                stops.append({
                    "color": f"{{{stop_token}}}" if stop_token else stop_hex,
                    "position": stop.get("position", 0.0),
                })
            entry = {
                "type": _GRADIENT_TYPE_MAP[fill_type],
                "stops": stops,
            }
            handle_positions = fill.get("gradientHandlePositions")
            if handle_positions:
                entry["handlePositions"] = handle_positions
            # Preserve Plugin API gradientTransform when available (added by
            # supplement extraction). Both representations are stored so each
            # renderer can use whichever maps best to its target format.
            # gradientTransform: ONLY from Plugin API (supplement extraction).
            # The REST API handlePositions and Plugin API gradientTransform
            # use different coordinate conventions. Computing one from the
            # other produces wrong gradient scale/orientation (e.g. half-height
            # gradients, wrong axis mapping). handlePositions are preserved
            # separately for backends that want to do their own math.
            gradient_transform = fill.get("gradientTransform")
            if gradient_transform:
                entry["gradientTransform"] = gradient_transform
            if paint_opacity < 1.0:
                entry["opacity"] = paint_opacity
            result.append(entry)

        elif fill_type == "IMAGE":
            image_hash = fill.get("imageHash") or fill.get("imageRef")
            if image_hash:
                entry = {
                    "type": "image",
                    "asset_hash": image_hash,
                    "scaleMode": (fill.get("scaleMode") or "FILL").lower(),
                }
                image_transform = fill.get("imageTransform")
                if image_transform:
                    entry["imageTransform"] = image_transform
                if paint_opacity < 1.0:
                    entry["opacity"] = paint_opacity
                result.append(entry)

    return result


def normalize_strokes(
    raw_json: str | None, bindings: list[dict[str, Any]], node: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize Figma strokes JSON to IR stroke array."""
    if not raw_json or raw_json == "[]":
        return []

    try:
        strokes = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return []

    binding_map = {b["property"]: b.get("token_name") for b in bindings if b.get("token_name")}
    result = []

    for i, stroke in enumerate(strokes):
        if stroke.get("visible") is False:
            continue
        if stroke.get("type") != "SOLID":
            continue

        color = stroke.get("color", {})
        hex_val = _figma_color_to_hex(color, 1.0)
        token = binding_map.get(f"stroke.{i}.color")

        entry: dict[str, Any] = {
            "type": "solid",
            "color": f"{{{token}}}" if token else hex_val,
            "width": int(node.get("stroke_weight") or 1),
        }
        align = node.get("stroke_align")
        if align:
            entry["align"] = align.lower()
        result.append(entry)

    return result


def normalize_effects(
    raw_json: str | None, bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize Figma effects JSON to IR effect array."""
    if not raw_json or raw_json == "[]":
        return []

    try:
        effects = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return []

    binding_map = {b["property"]: b.get("token_name") for b in bindings if b.get("token_name")}
    result = []

    for i, effect in enumerate(effects):
        if effect.get("visible") is False:
            continue

        effect_type = effect.get("type", "")

        if effect_type in ("DROP_SHADOW", "INNER_SHADOW"):
            color = effect.get("color", {})
            hex_val = _figma_color_to_hex(color, 1.0)
            token = binding_map.get(f"effect.{i}.color")
            offset = effect.get("offset", {})
            entry = {
                "type": "drop-shadow" if effect_type == "DROP_SHADOW" else "inner-shadow",
                "color": f"{{{token}}}" if token else hex_val,
                "offset": {"x": offset.get("x", 0), "y": offset.get("y", 0)},
                "blur": effect.get("radius", 0),
                "spread": effect.get("spread", 0),
            }
            # Collect token refs for non-color sub-properties
            entry_refs: dict[str, str] = {}
            for sub_prop in ("spread", "offsetX", "offsetY", "radius"):
                sub_token = binding_map.get(f"effect.{i}.{sub_prop}")
                if sub_token:
                    entry_refs[sub_prop] = sub_token
            if entry_refs:
                entry["_token_refs"] = entry_refs
            result.append(entry)

        elif effect_type in ("LAYER_BLUR", "BACKGROUND_BLUR"):
            result.append({
                "type": "layer-blur" if effect_type == "LAYER_BLUR" else "background-blur",
                "radius": effect.get("radius", 0),
            })

    return result


def normalize_corner_radius(
    raw_value: str | int | float | None,
) -> float | dict[str, float] | None:
    """Normalize corner radius to number or per-corner dict."""
    if raw_value is None:
        return None

    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except (json.JSONDecodeError, ValueError):
            try:
                parsed = float(raw_value)
            except ValueError:
                return None
        raw_value = parsed

    if isinstance(raw_value, (int, float)):
        return float(raw_value) if raw_value > 0 else None

    if isinstance(raw_value, dict):
        result = {}
        for key in ("tl", "tr", "bl", "br"):
            val = raw_value.get(key, 0)
            if val > 0:
                result[key] = float(val)
        return result if result else None

    return None


# Typography binding properties → IR style key (visual props handled by _build_visual)
_TYPOGRAPHY_BINDING_MAP = {
    "fontSize": "fontSize",
    "fontFamily": "fontFamily",
    "fontWeight": "fontWeight",
    "lineHeight": "lineHeight",
    "letterSpacing": "letterSpacing",
}

# Types where text_content maps to props.text
_TEXT_PROP_TYPES = frozenset({"text", "heading", "link", "badge"})

# Layout direction mapping
_DIRECTION_MAP = {
    "HORIZONTAL": "horizontal",
    "VERTICAL": "vertical",
}

# Sizing mapping
_SIZING_MAP = {
    "FILL": "fill",
    "HUG": "hug",
    "FIXED": "fixed",
}


def _build_binding_index(bindings: list[dict[str, Any]]) -> dict[str, str]:
    """Build property → token ref string from bindings list.

    Returns dict mapping Figma property names to "{token.name}" strings
    for bindings that have a token_name set.
    """
    index: dict[str, str] = {}
    for b in bindings:
        if b.get("token_name"):
            index[b["property"]] = f"{{{b['token_name']}}}"
    return index


# Properties that belong in layout, not style
_LAYOUT_BINDING_PROPERTIES = frozenset({
    "padding.top", "padding.right", "padding.bottom", "padding.left",
    "itemSpacing", "counterAxisSpacing",
})


def _resolve_primitive_type(node: dict[str, Any]) -> str:
    """Return the structural primitive — what Figma node to create.

    Always sourced from ``node_type`` (the extractor-written,
    deterministic column). Never affected by classifier opinion. This
    is the dispatch-safe half of the type/role split (see
    ``docs/plan-type-role-split.md``). Downstream renderers, verifiers,
    and leaf-parent gates read this field.

    GROUP is special: Figma's transform-transparent group container is
    a distinct concept from FRAME-based layout containers. Children
    get grandparent-relative coordinates and a different creation API
    (``figma.group()`` vs ``figma.createFrame()``).
    """
    node_type_raw = node.get("node_type", "")
    if node_type_raw == "GROUP":
        return "group"
    return node_type_raw.lower() or "frame"


def _resolve_element_type(node: dict[str, Any]) -> str:
    """Resolve the role-first identifier for eid naming.

    Returns ``canonical_type`` when the classifier assigned one, else
    falls through to the structural primitive. This is the grammar-
    facing identifier namespace: eids like ``heading-2`` / ``card-1``
    come from the classifier's label when available, ``frame-338`` /
    ``text-2`` from structure otherwise.

    Used by ``build_composition_spec`` for eid prefix counter keys.
    For the dispatch-safe structural primitive, use
    ``_resolve_primitive_type`` instead.
    """
    node_type_raw = node.get("node_type", "")
    if node_type_raw == "GROUP":
        return "group"
    return node.get("canonical_type") or node_type_raw.lower() or "frame"


def map_node_to_element(node: dict[str, Any]) -> dict[str, Any]:
    """Convert a classified node dict to an IR element.

    Expects node dict with keys: canonical_type, layout_mode, padding_*,
    item_spacing, layout_sizing_h/v, text_content, corner_radius, opacity,
    and bindings (list of {property, token_name, resolved_value}).
    """
    bindings = node.get("bindings", [])
    binding_index = _build_binding_index(bindings)

    # Type/role split (docs/plan-type-role-split.md): type is always
    # the structural primitive; role is the classifier's semantic
    # label, included only when it differs from type (redundancy
    # elision). Downstream dispatch reads type; grammar/semantic
    # consumers read role.
    primitive_type = _resolve_primitive_type(node)
    semantic_role = node.get("canonical_type")

    element: dict[str, Any] = {
        "type": primitive_type,
    }
    if semantic_role and semantic_role != primitive_type:
        element["role"] = semantic_role

    # ADR-007 / Defect-1 residual: name-only classification (e.g. a FRAME
    # named "card/sheet/success") can promote the IR type to "card" even
    # though the DB has no component backing. The renderer's Mode 1 gate
    # will never fire for these and the downstream RenderVerifier would
    # otherwise spuriously flag type_substitution on every render.
    #
    # Mark each element with whether Mode 1 is actually eligible — same
    # gate as dd/renderers/figma.py:827. Verifier consults this flag
    # before treating a FRAME-for-INSTANCE result as a degradation.
    node_type = node.get("node_type")
    component_key = node.get("component_key")
    component_figma_id = node.get("component_figma_id")
    instance_figma_node_id = node.get("figma_node_id")
    mode1_eligible = bool(
        component_key
        or component_figma_id
        or (node_type == "INSTANCE" and instance_figma_node_id)
    )
    element["_mode1_eligible"] = mode1_eligible

    layout = _build_layout(node, binding_index)
    if layout:
        element["layout"] = layout

    style = _build_style(node, binding_index)
    if style:
        element["style"] = style

    props = _build_props(node)
    if props:
        element["props"] = props

    visual = _build_visual(node, bindings)
    if visual:
        element["visual"] = visual

    if node.get("visible") == 0:
        element["visible"] = False

    return element


def _build_visual(node: dict[str, Any], bindings: list[dict[str, Any]]) -> dict[str, Any]:
    """Build visual section — normalized fills/strokes/effects for verification.

    The verifier compares IR visual properties against rendered ones
    per-eid. Only populates when the node has visible visual properties;
    empty visual dicts are omitted to keep the IR compact.
    """
    visual: dict[str, Any] = {}

    fills = normalize_fills(node.get("fills"), bindings)
    if fills:
        visual["fills"] = fills

    strokes = normalize_strokes(node.get("strokes"), bindings, node)
    if strokes:
        visual["strokes"] = strokes

    effects = normalize_effects(node.get("effects"), bindings)
    if effects:
        visual["effects"] = effects

    return visual


def _build_layout(node: dict[str, Any], binding_index: dict[str, str]) -> dict[str, Any]:
    layout: dict[str, Any] = {}

    direction = _DIRECTION_MAP.get(node.get("layout_mode") or "", "stacked")
    layout["direction"] = direction

    gap_token = binding_index.get("itemSpacing")
    gap = node.get("item_spacing")
    if gap_token:
        layout["gap"] = gap_token
    elif gap and gap > 0:
        layout["gap"] = gap

    padding = _build_padding(node, binding_index)
    if padding:
        layout["padding"] = padding

    sizing = _build_sizing(node)
    if sizing:
        layout["sizing"] = sizing

    wrap = node.get("layout_wrap")
    cas = node.get("counter_axis_spacing")
    # Infer WRAP from counter_axis_spacing when layout_wrap is missing
    if not wrap and cas and cas > 0:
        wrap = "WRAP"
    if wrap and wrap != "NO_WRAP":
        layout["wrap"] = wrap
        cas_token = binding_index.get("counterAxisSpacing")
        if cas_token:
            layout["counterAxisGap"] = cas_token
        elif cas and cas > 0:
            layout["counterAxisGap"] = cas

    align = node.get("primary_align")
    if align:
        layout["mainAxisAlignment"] = align.lower()

    cross = node.get("counter_align")
    if cross:
        layout["crossAxisAlignment"] = cross.lower()

    return layout


def _build_padding(node: dict[str, Any], binding_index: dict[str, str]) -> dict[str, Any] | None:
    padding: dict[str, Any] = {}
    for side in ("top", "right", "bottom", "left"):
        token = binding_index.get(f"padding.{side}")
        val = node.get(f"padding_{side}")
        if token:
            padding[side] = token
        elif val and val > 0:
            padding[side] = val

    return padding if padding else None


def _build_sizing(node: dict[str, Any]) -> dict[str, Any] | None:
    """Build sizing dict from node layout sizing modes + pixel dimensions.

    FILL/HUG → store as string (parent/content determines size).
    FIXED or NULL → store pixel value (explicit dimensions needed).

    Pixel dimensions are always stored as widthPixels/heightPixels when
    the semantic sizing is a string. Renderers need both: the semantic mode
    for layoutSizing (post-appendChild) and pixel values for resize().
    """
    sizing: dict[str, Any] = {}
    h = node.get("layout_sizing_h")
    v = node.get("layout_sizing_v")
    width = node.get("width")
    height = node.get("height")

    if h in ("FILL", "HUG"):
        sizing["width"] = _SIZING_MAP[h]
        if width is not None:
            sizing["widthPixels"] = width
    elif width is not None:
        sizing["width"] = width

    if v in ("FILL", "HUG"):
        sizing["height"] = _SIZING_MAP[v]
        if height is not None:
            sizing["heightPixels"] = height
    elif height is not None:
        sizing["height"] = height

    return sizing if sizing else None


def _build_style(node: dict[str, Any], binding_index: dict[str, str]) -> dict[str, Any]:
    """Build style section — typography bindings only."""
    style: dict[str, Any] = {}

    for binding in node.get("bindings", []):
        prop = binding["property"]
        token_name = binding.get("token_name")
        resolved = binding.get("resolved_value")

        ir_key = _TYPOGRAPHY_BINDING_MAP.get(prop)
        if ir_key is None:
            continue

        if token_name:
            style[ir_key] = f"{{{token_name}}}"
        elif resolved:
            style[ir_key] = resolved

    return style


def _build_props(node: dict[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = {}

    canonical_type = node.get("canonical_type") or node.get("node_type", "").lower()
    text = node.get("text_content")

    if text and canonical_type in _TEXT_PROP_TYPES:
        props["text"] = text

    return props


# ---------------------------------------------------------------------------
# Override decomposition
# ---------------------------------------------------------------------------

def decompose_override(property_type: str, property_name: str) -> tuple[str, str]:
    """Decompose a DB override into (target, figma_property_name).

    The DB stores overrides as composite property_name = "{target}{suffix}".
    This function splits them using the same suffix knowledge that extraction
    used to construct them — no second map to maintain.

    Returns (target, property) where:
      target: ":self" or ";1334:10837" (Figma node path)
      property: "fills", "cornerRadius", "characters", "instance_swap", etc.
    """
    from dd.extract_supplement import override_suffix_for_type

    suffix, figma_name = override_suffix_for_type(property_type)

    if suffix and property_name.endswith(suffix):
        target = property_name[:-len(suffix)]
        return target, figma_name
    if not suffix:
        return property_name, figma_name
    return property_name, figma_name


# ---------------------------------------------------------------------------
# Query layer
# ---------------------------------------------------------------------------

def query_screen_visuals(conn: sqlite3.Connection, screen_id: int) -> dict[int, dict[str, Any]]:
    """Fetch visual properties for all nodes in a screen.

    Returns dict keyed by node_id with all visual, layout, and text
    properties, component_key, and token bindings.

    Column list driven by the property registry — automatically includes
    any new property added to the registry without manual SQL changes.
    """
    from dd.property_registry import PROPERTIES

    has_registry = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='component_key_registry'"
    ).fetchone()

    # Build column list from registry, filtered by what exists in this DB
    node_cols = {row[1] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}
    registry_cols = []
    for prop in PROPERTIES:
        if prop.db_column and prop.db_column in node_cols:
            registry_cols.append(prop.db_column)
    # Always include structural columns (not in registry — they're structural)
    if "component_key" not in registry_cols and "component_key" in node_cols:
        registry_cols.append("component_key")
    if "figma_node_id" not in registry_cols and "figma_node_id" in node_cols:
        registry_cols.append("figma_node_id")
    # ADR-007 Session A: node_type is required so the renderer can
    # distinguish INSTANCE nodes from FRAME/RECTANGLE/etc. when deciding
    # Mode 1 path 2 eligibility and emitting degraded_to_mode2 entries.
    if "node_type" not in registry_cols and "node_type" in node_cols:
        registry_cols.append("node_type")
    # relativeTransform disambiguates mirrors from rotations (ADR session)
    if "relative_transform" not in registry_cols and "relative_transform" in node_cols:
        registry_cols.append("relative_transform")
    # OpenType features per text segment (SUPS, SUBS, LIGA, etc.)
    if "opentype_features" not in registry_cols and "opentype_features" in node_cols:
        registry_cols.append("opentype_features")
    # Note: x/y are NOT included here. Position is spatial encoding
    # (absolute canvas coords in DB, parent-relative in IR). Renderers
    # read position from the IR, not from the visual dict.
    # See compiler-architecture.md Section 4.1.

    col_list = ", ".join(f"n.{c}" for c in registry_cols)

    if has_registry:
        cursor = conn.execute(
            f"SELECT n.id, {col_list}, "
            "ckr.figma_node_id as component_figma_id "
            "FROM nodes n "
            "LEFT JOIN component_key_registry ckr ON n.component_key = ckr.component_key "
            "WHERE n.screen_id = ?",
            (screen_id,),
        )
    else:
        col_list_bare = ", ".join(registry_cols)
        cursor = conn.execute(
            f"SELECT id, {col_list_bare} "
            "FROM nodes WHERE screen_id = ?",
            (screen_id,),
        )
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    if not rows:
        return {}

    node_ids = [row[0] for row in rows]
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        node_dict = dict(zip(columns, row))
        node_id = node_dict.pop("id")
        node_dict["bindings"] = []
        result[node_id] = node_dict

    placeholders = ",".join("?" for _ in node_ids)
    bindings_cursor = conn.execute(
        f"SELECT ntb.node_id, ntb.property, t.name as token_name, ntb.resolved_value "
        f"FROM node_token_bindings ntb "
        f"LEFT JOIN tokens t ON ntb.token_id = t.id "
        f"WHERE ntb.node_id IN ({placeholders}) AND ntb.binding_status = 'bound'",
        node_ids,
    )
    for row in bindings_cursor.fetchall():
        node_id = row[0]
        if node_id in result:
            result[node_id]["bindings"].append({
                "property": row[1],
                "token_name": row[2],
                "resolved_value": row[3],
            })

    instance_ids = [nid for nid, v in result.items() if v.get("component_key")]
    if instance_ids:
        ph = ",".join("?" for _ in instance_ids)

        # PR-1: the legacy `hidden_children` name-based descendant walk
        # was deleted here. Its replacement — a unified resolver that
        # pulls both `instance_overrides` BOOLEAN `:visible` rows
        # (Source A) and `nodes.visible=0` descendants at arbitrary
        # depth (Source B) — lives in
        # `compress_l3._fetch_descendant_visibility_overrides`. The
        # renderer consumes backend-neutral `.visible=bool`
        # PathOverrides on CompRef heads and lowers them via the
        # resolver's Figma-id side-car into stable
        # `id.endsWith(";<fig>")` calls, sidestepping the
        # name-ambiguity bug that `findOne(name=X)` hit on masters
        # with multiple same-name descendants.

        # Instance overrides (text, visibility, instance swap from Plugin API)
        has_overrides = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='instance_overrides'"
        ).fetchone()
        if has_overrides:
            override_cursor = conn.execute(
                f"SELECT node_id, property_type, property_name, override_value "
                f"FROM instance_overrides WHERE node_id IN ({ph})",
                instance_ids,
            )
            for row in override_cursor.fetchall():
                node_id = row[0]
                if node_id in result:
                    if "instance_overrides" not in result[node_id]:
                        result[node_id]["instance_overrides"] = []
                    target, prop = decompose_override(row[1], row[2])
                    result[node_id]["instance_overrides"].append({
                        "target": target,
                        "property": prop,
                        "value": row[3],
                    })

        # Instance child swaps from two sources:
        # 1. instance_overrides INSTANCE_SWAP entries (from Figma's overrides API)
        # 2. Descendant instances with component_keys (from recursive CTE)
        # Source 1 catches swaps that Figma reports on the parent instance.
        # Source 2 catches swaps on nested children that Figma reports on the
        # child instance itself (e.g., icon swaps inside buttons).
        # Deduplicate by child_id to avoid double-swapping.
        swap_child_ids_seen: dict[int, set[str]] = {}

        if has_overrides:
            swap_cursor = conn.execute(
                f"SELECT node_id, property_name, override_value "
                f"FROM instance_overrides "
                f"WHERE node_id IN ({ph}) AND property_type = 'INSTANCE_SWAP'",
                instance_ids,
            )
            for row in swap_cursor.fetchall():
                inst_id = row[0]
                child_id = row[1]
                swap_target_id = row[2]
                if inst_id in result and child_id and swap_target_id:
                    if "child_swaps" not in result[inst_id]:
                        result[inst_id]["child_swaps"] = []
                    result[inst_id]["child_swaps"].append({
                        "child_id": child_id,
                        "swap_target_id": swap_target_id,
                    })
                    if inst_id not in swap_child_ids_seen:
                        swap_child_ids_seen[inst_id] = set()
                    swap_child_ids_seen[inst_id].add(child_id)

        # Source 2: recursive CTE for descendant instances at any depth.
        # Finds ALL INSTANCE descendants within each top-level instance's
        # subtree, deduplicating against Source 1 via swap_child_ids_seen.
        # swapComponent is a no-op when the component already matches.
        if has_registry:
            child_swap_cursor = conn.execute(
                f"WITH RECURSIVE subtree(id, root_id) AS ("
                f"  SELECT id, id as root_id FROM nodes WHERE id IN ({ph}) "
                f"  UNION ALL "
                f"  SELECT n.id, s.root_id FROM nodes n JOIN subtree s ON n.parent_id = s.id"
                f") "
                f"SELECT s.root_id, c.figma_node_id, ckr.figma_node_id as swap_target_id "
                f"FROM nodes c "
                f"JOIN subtree s ON c.id = s.id "
                f"JOIN component_key_registry ckr ON c.component_key = ckr.component_key "
                f"WHERE c.node_type = 'INSTANCE' AND c.component_key IS NOT NULL "
                f"AND c.visible = 1 AND c.id != s.root_id",
                instance_ids,
            )
            for row in child_swap_cursor.fetchall():
                root_inst_id = row[0]
                child_figma_id = row[1]
                swap_target_id = row[2]
                if root_inst_id in result and child_figma_id and swap_target_id and ";" in child_figma_id:
                    master_child_id = child_figma_id[child_figma_id.index(";"):]
                    seen = swap_child_ids_seen.get(root_inst_id, set())
                    if master_child_id not in seen:
                        if "child_swaps" not in result[root_inst_id]:
                            result[root_inst_id]["child_swaps"] = []
                        result[root_inst_id]["child_swaps"].append({
                            "child_id": master_child_id,
                            "swap_target_id": swap_target_id,
                        })

        # Hoist overrides from nested Mode 1 instances to their top-level ancestor.
        # When nav/top-nav (Mode 1) contains button/small (also Mode 1), the
        # button is skipped during rendering. Its overrides must be applied
        # on the top-level instance instead, with :self references transformed
        # to master-relative paths derived from the nested instance's figma_node_id.
        if has_overrides and len(instance_ids) > 1:
            _hoist_descendant_overrides(conn, instance_ids, result)

        # Build override trees from the flat lists.
        # This replaces instance_overrides + child_swaps with a single
        # nested structure where nesting encodes dependency ordering.
        for inst_id in instance_ids:
            vis = result.get(inst_id)
            if vis is None:
                continue
            ovs = vis.pop("instance_overrides", [])
            swaps = vis.pop("child_swaps", [])
            if ovs or swaps:
                vis["override_tree"] = build_override_tree(ovs, swaps)

    # Attach asset refs (vector paths, image assets) when the tables exist
    has_asset_refs = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='node_asset_refs'"
    ).fetchone()
    if has_asset_refs:
        placeholders = ",".join("?" for _ in node_ids)
        asset_cursor = conn.execute(
            f"SELECT nar.node_id, nar.asset_hash, nar.role, nar.fill_index, "
            f"a.kind, a.metadata "
            f"FROM node_asset_refs nar "
            f"JOIN assets a ON nar.asset_hash = a.hash "
            f"WHERE nar.node_id IN ({placeholders})",
            node_ids,
        )
        for row in asset_cursor.fetchall():
            nid = row[0]
            if nid in result:
                ref_entry: dict[str, Any] = {
                    "asset_hash": row[1],
                    "role": row[2],
                    "kind": row[4],
                }
                if row[3] is not None:
                    ref_entry["fill_index"] = row[3]
                metadata_json = row[5]
                if metadata_json:
                    metadata = json.loads(metadata_json)
                    svg_data = metadata.get("svg_data")
                    if svg_data:
                        ref_entry["svg_data"] = svg_data
                    # Structured per-path data — preserves per-path windingRule
                    svg_paths = metadata.get("svg_paths")
                    if svg_paths:
                        ref_entry["svg_paths"] = svg_paths
                if "_asset_refs" not in result[nid]:
                    result[nid]["_asset_refs"] = []
                result[nid]["_asset_refs"].append(ref_entry)

    return result


def build_override_tree(
    instance_overrides: list[dict[str, Any]],
    child_swaps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a nested override tree from flat overrides and child swaps.

    The tree mirrors the component instance's slot/child structure.
    Nesting encodes dependency: a swap at a parent node must happen before
    property overrides on its descendants. Pre-order traversal of the tree
    gives correct ordering for imperative renderers. Declarative renderers
    map the tree directly to nested props.

    Target paths are semicolon-delimited Figma node IDs (;pageId:nodeId).
    Parent of ";A;B" is ";A". Parent of ";A" is ":self" (root).
    """
    # Collect all data by target
    target_data: dict[str, dict[str, Any]] = {}
    for ov in instance_overrides:
        t = ov["target"]
        target_data.setdefault(t, {"properties": [], "swap": None})
        target_data[t]["properties"].append({
            "property": ov["property"],
            "value": ov["value"],
        })

    for cs in child_swaps:
        t = cs["child_id"]
        target_data.setdefault(t, {"properties": [], "swap": None})
        target_data[t]["swap"] = cs["swap_target_id"]

    # Build root node
    root_data = target_data.pop(":self", {"properties": [], "swap": None})
    root: dict[str, Any] = {
        "target": ":self",
        "swap": root_data["swap"],
        "properties": root_data["properties"],
        "children": [],
    }

    if not target_data:
        return root

    # Ensure all intermediate ancestor paths exist as nodes.
    # Target ";A;B;C" implies ";A;B" and ";A" exist in the tree
    # even if they have no explicit overrides.
    all_targets = set(target_data.keys())
    for target in list(all_targets):
        segments = target.split(";")
        # segments[0] is empty (leading ";"), real segments start at [1]
        for i in range(2, len(segments)):
            ancestor = ";".join(segments[:i])
            if ancestor and ancestor not in all_targets:
                target_data[ancestor] = {"properties": [], "swap": None}
                all_targets.add(ancestor)

    # Create tree nodes
    nodes: dict[str, dict[str, Any]] = {}
    for target, data in target_data.items():
        nodes[target] = {
            "target": target,
            "swap": data["swap"],
            "properties": data["properties"],
            "children": [],
        }

    # Wire parent→child relationships
    all_nodes: dict[str, dict[str, Any]] = {":self": root}
    # Process shallowest first so parents exist before children
    for target in sorted(nodes.keys(), key=lambda t: t.count(";")):
        node = nodes[target]
        last_semi = target.rfind(";")
        if last_semi <= 0:
            parent_target = ":self"
        else:
            parent_target = target[:last_semi]

        parent = all_nodes.get(parent_target, root)
        parent["children"].append(node)
        all_nodes[target] = node

    return root


def _hoist_descendant_overrides(
    conn: sqlite3.Connection,
    instance_ids: list[int],
    result: dict[int, dict[str, Any]],
) -> None:
    """Move overrides from nested Mode 1 instances to their top-level ancestor.

    For each Mode 1 instance that is a descendant of another Mode 1 instance:
    - Transform :self references to master-relative paths
    - Non-self paths are already master-relative and pass through unchanged
    - Add the transformed overrides to the ancestor's instance_overrides list
    """
    instance_id_set = set(instance_ids)

    # Build parent_id + figma_node_id lookup for instance nodes
    ph = ",".join("?" for _ in instance_ids)
    rows = conn.execute(
        f"SELECT id, parent_id, figma_node_id FROM nodes WHERE id IN ({ph})",
        instance_ids,
    ).fetchall()

    parent_map: dict[int, int | None] = {r[0]: r[1] for r in rows}
    figma_id_map: dict[int, str] = {r[0]: r[2] for r in rows}

    # For each instance, walk up parent_id to find the nearest Mode 1 ancestor.
    # Need parent_ids for intermediate (non-instance) nodes too.
    all_parent_ids: set[int] = set()
    for pid in parent_map.values():
        if pid is not None:
            all_parent_ids.add(pid)
    # Fetch parents that aren't already in parent_map
    missing = all_parent_ids - instance_id_set
    if missing:
        mph = ",".join("?" for _ in missing)
        for r in conn.execute(
            f"SELECT id, parent_id FROM nodes WHERE id IN ({mph})",
            list(missing),
        ).fetchall():
            parent_map[r[0]] = r[1]

    def find_mode1_ancestor(node_id: int) -> int | None:
        current = parent_map.get(node_id)
        while current is not None:
            if current in instance_id_set:
                return current
            current = parent_map.get(current)
        return None

    for inst_id in instance_ids:
        ancestor_id = find_mode1_ancestor(inst_id)
        if ancestor_id is None:
            continue  # top-level instance, nothing to hoist

        nested_overrides = result.get(inst_id, {}).get("instance_overrides", [])
        if not nested_overrides:
            continue

        figma_nid = figma_id_map.get(inst_id, "")
        if ";" not in figma_nid:
            continue  # can't derive master-relative path

        master_relative = figma_nid[figma_nid.index(";"):]

        if "instance_overrides" not in result[ancestor_id]:
            result[ancestor_id]["instance_overrides"] = []

        # Build set of existing (property, target) to deduplicate
        existing = {
            (ov["property"], ov["target"])
            for ov in result[ancestor_id]["instance_overrides"]
        }

        for ov in nested_overrides:
            target = ov["target"]
            if target == ":self":
                new_target = master_relative
            else:
                new_target = target

            key = (ov["property"], new_target)
            if key in existing:
                continue  # already reported by parent's own overrides

            existing.add(key)
            result[ancestor_id]["instance_overrides"].append({
                "target": new_target,
                "property": ov["property"],
                "value": ov["value"],
            })


def query_slot_definitions(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """Fetch slot definitions keyed by component name.

    Returns dict mapping component name to list of slot dicts, each with
    name, slot_type, is_required, sort_order. Used by build_semantic_tree
    to assign children to named slots.
    """
    cursor = conn.execute(
        "SELECT c.name as component_name, cs.name, cs.slot_type, cs.is_required, cs.sort_order "
        "FROM component_slots cs "
        "JOIN components c ON cs.component_id = c.id "
        "ORDER BY c.name, cs.sort_order"
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for row in cursor.fetchall():
        comp_name = row[0]
        if comp_name not in result:
            result[comp_name] = []
        result[comp_name].append({
            "name": row[1],
            "slot_type": row[2],
            "is_required": row[3],
            "sort_order": row[4],
        })
    return result


def filter_system_chrome(
    spec: dict[str, Any], node_names: dict[int, str],
) -> dict[str, Any]:
    """Remove system chrome elements from a CompositionSpec.

    Takes a spec and a mapping of node_id → node name. Removes elements
    whose source node name matches system chrome patterns (iOS/StatusBar,
    HomeIndicator, Safari, keyboards, etc). Does not mutate the input.
    """
    node_id_map = spec.get("_node_id_map", {})
    chrome_eids = set()

    for eid, node_id in node_id_map.items():
        name = node_names.get(node_id, "")
        if is_system_chrome(name):
            chrome_eids.add(eid)

    if not chrome_eids:
        return spec

    new_elements = {}
    for eid, element in spec["elements"].items():
        if eid in chrome_eids:
            continue
        new_element = dict(element)
        if "children" in new_element:
            new_element["children"] = [
                c for c in new_element["children"] if c not in chrome_eids
            ]
        new_elements[eid] = new_element

    new_node_id_map = {
        eid: nid for eid, nid in node_id_map.items() if eid not in chrome_eids
    }

    return {**spec, "elements": new_elements, "_node_id_map": new_node_id_map}


def _assign_children_to_slots(
    children_eids: list[str],
    slot_defs: list[dict[str, Any]],
    node_id_map: dict[str, int],
    node_data: dict[int, dict[str, Any]],
    parent_node_id: int,
) -> dict[str, list[str]]:
    """Assign child element IDs to named slots by spatial position.

    Divides the parent's width into N equal zones (one per slot) and
    assigns each child to the zone its x-coordinate falls into.
    """
    parent_info = node_data.get(parent_node_id, {})
    parent_width = parent_info.get("width", 0)
    num_slots = len(slot_defs)

    if num_slots == 0 or parent_width == 0:
        return {}

    zone_width = parent_width / num_slots
    parent_x = parent_info.get("x", 0)

    slots: dict[str, list[str]] = {s["name"]: [] for s in slot_defs}
    slot_names_ordered = [s["name"] for s in slot_defs]

    for child_eid in children_eids:
        child_node_id = node_id_map.get(child_eid)
        if child_node_id is None:
            continue
        child_info = node_data.get(child_node_id, {})
        child_x = child_info.get("x", 0)
        child_width = child_info.get("width", 0)
        relative_x = (child_x + child_width / 2) - parent_x
        slot_index = min(int(relative_x / zone_width), num_slots - 1)
        slot_index = max(slot_index, 0)
        slots[slot_names_ordered[slot_index]].append(child_eid)

    return slots


def build_semantic_tree(
    spec: dict[str, Any],
    slot_defs: dict[str, list[dict[str, Any]]],
    node_data: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Collapse a flat CompositionSpec into a semantic tree with slots.

    For each element whose component has slot definitions, assigns its
    children to named slots by spatial position. Children are moved from
    the `children` list to a `slots` dict. Elements without slot defs
    keep their `children` list unchanged. Does not mutate the input.
    """
    node_id_map = spec.get("_node_id_map", {})
    new_elements: dict[str, dict[str, Any]] = {}

    component_name_by_eid: dict[str, str] = {}
    for eid, node_id in node_id_map.items():
        info = node_data.get(node_id, {})
        component_name_by_eid[eid] = info.get("name", "")

    for eid, element in spec["elements"].items():
        new_element = dict(element)
        children = element.get("children", [])
        comp_name = component_name_by_eid.get(eid, "")
        defs = slot_defs.get(comp_name)

        if defs and children:
            parent_node_id = node_id_map.get(eid)
            if parent_node_id is not None:
                assigned = _assign_children_to_slots(
                    children, defs, node_id_map, node_data, parent_node_id,
                )
                if assigned:
                    new_element["slots"] = assigned
                    del new_element["children"]

        new_elements[eid] = new_element

    return {**spec, "elements": new_elements}


def query_screen_for_ir(conn: sqlite3.Connection, screen_id: int) -> dict[str, Any]:
    """Fetch all nodes for a screen with L1/L2 annotations where available.

    Uses LEFT JOIN on screen_component_instances so ALL nodes are returned.
    Classified nodes have canonical_type, sci_id, parent_instance_id set.
    Unclassified nodes have those fields as NULL — the renderer uses
    progressive fallback (L2 → L1 → L0) to handle both cases.

    Returns dict with screen metadata and a list of node dicts,
    each containing its bindings grouped in-memory.
    """
    screen_row = conn.execute(
        "SELECT name, width, height FROM screens WHERE id = ?",
        (screen_id,),
    ).fetchone()
    if screen_row is None:
        return {"screen_name": "", "width": 0, "height": 0, "nodes": []}

    # Include relative_transform if the column exists (migration-gated)
    node_cols_local = {row[1] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}
    rt_col = "n.relative_transform, " if "relative_transform" in node_cols_local else ""
    # Migration 021: nodes.role (type/role split — plan-type-role-split.md).
    # Gated for DBs that haven't run the migration yet.
    role_col = "n.role, " if "role" in node_cols_local else ""
    cursor = conn.execute(
        "SELECT n.id as node_id, n.name, n.node_type, n.depth, n.sort_order, "
        "n.x, n.y, n.width, n.height, "
        "n.layout_mode, n.padding_top, n.padding_right, n.padding_bottom, n.padding_left, "
        "n.item_spacing, n.counter_axis_spacing, "
        "n.layout_sizing_h, n.layout_sizing_v, n.primary_align, n.counter_align, "
        "n.text_content, n.corner_radius, n.opacity, n.fills, n.strokes, n.effects, "
        "n.font_family, n.font_weight, n.font_size, "
        "n.parent_id, n.component_key, n.visible, "
        f"{rt_col}"
        f"{role_col}"
        "sci.canonical_type, sci.id as sci_id, sci.parent_instance_id "
        "FROM nodes n "
        "LEFT JOIN screen_component_instances sci ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
        "WHERE n.screen_id = ? "
        "ORDER BY n.depth, n.sort_order",
        (screen_id,),
    )
    columns = [desc[0] for desc in cursor.description]
    all_nodes = [dict(zip(columns, row)) for row in cursor.fetchall()]

    bindings_cursor = conn.execute(
        "SELECT ntb.node_id, ntb.property, t.name as token_name, ntb.resolved_value "
        "FROM node_token_bindings ntb "
        "JOIN nodes n ON ntb.node_id = n.id "
        "LEFT JOIN tokens t ON ntb.token_id = t.id "
        "WHERE n.screen_id = ? AND ntb.binding_status = 'bound'",
        (screen_id,),
    )
    bindings_by_node: dict[int, list[dict[str, Any]]] = {}
    for row in bindings_cursor.fetchall():
        node_id = row[0]
        if node_id not in bindings_by_node:
            bindings_by_node[node_id] = []
        bindings_by_node[node_id].append({
            "property": row[1],
            "token_name": row[2],
            "resolved_value": row[3],
        })

    for node_dict in all_nodes:
        node_dict["bindings"] = bindings_by_node.get(node_dict["node_id"], [])

    tokens_cursor = conn.execute(
        "SELECT DISTINCT t.name, ntb.resolved_value "
        "FROM node_token_bindings ntb "
        "JOIN nodes n ON ntb.node_id = n.id "
        "JOIN tokens t ON ntb.token_id = t.id "
        "WHERE n.screen_id = ? AND ntb.binding_status = 'bound'",
        (screen_id,),
    )
    tokens = {row[0]: row[1] for row in tokens_cursor.fetchall()}

    origin_row = conn.execute(
        "SELECT x, y FROM nodes WHERE screen_id = ? AND depth = 0 LIMIT 1",
        (screen_id,),
    ).fetchone()
    screen_origin_x = origin_row[0] if origin_row else 0
    screen_origin_y = origin_row[1] if origin_row else 0

    return {
        "screen_name": screen_row[0],
        "width": screen_row[1],
        "height": screen_row[2],
        "nodes": all_nodes,
        "tokens": tokens,
        "screen_origin_x": screen_origin_x or 0,
        "screen_origin_y": screen_origin_y or 0,
    }


# ---------------------------------------------------------------------------
# Composition assembly
# ---------------------------------------------------------------------------

def build_composition_spec(data: dict[str, Any]) -> dict[str, Any]:
    """Assemble a CompositionSpec from query results.

    Builds the flat element map, assigns IDs, wires parent→children
    relationships, and collects referenced tokens.
    """
    raw_nodes = data.get("nodes", [])
    if not raw_nodes:
        return {"version": "1.0", "root": "", "elements": {}, "tokens": {}, "_node_id_map": {}}

    # Filter synthetic nodes (platform artefacts like Figma auto-layout spacers).
    # L0 stays lossless (nodes remain in DB); the composition spec excludes them.
    synthetic_node_ids: set[int] = set()
    for node in raw_nodes:
        name = node.get("name", "")
        if is_synthetic_node(name):
            synthetic_node_ids.add(node["node_id"])

    # Also exclude children of synthetic nodes (transitive closure)
    if synthetic_node_ids:
        node_by_id = {n["node_id"]: n for n in raw_nodes}
        changed = True
        while changed:
            changed = False
            for node in raw_nodes:
                if node["node_id"] in synthetic_node_ids:
                    continue
                parent_id = node.get("parent_id")
                if parent_id in synthetic_node_ids:
                    synthetic_node_ids.add(node["node_id"])
                    changed = True

    nodes = [n for n in raw_nodes if n["node_id"] not in synthetic_node_ids]

    type_counters: dict[str, int] = {}
    node_id_to_element_id: dict[int, str] = {}
    sci_id_to_element_id: dict[int, str] = {}
    elements: dict[str, dict[str, Any]] = {}

    for node in nodes:
        resolved_type = _resolve_element_type(node)
        type_counters[resolved_type] = type_counters.get(resolved_type, 0) + 1
        element_id = f"{resolved_type}-{type_counters[resolved_type]}"

        node_id_to_element_id[node["node_id"]] = element_id
        if node.get("sci_id") is not None:
            sci_id_to_element_id[node["sci_id"]] = element_id

        element = map_node_to_element(node)
        if node.get("name"):
            element["_original_name"] = node["name"]
        elements[element_id] = element

    # Wire children: always use DB parent_id (L0 ground-truth tree structure).
    # SCI parent_instance_id is NOT used for tree wiring — it can skip
    # intermediate unclassified INSTANCE nodes (e.g. keyboard containers),
    # flattening the hierarchy and losing auto-layout context.
    # SCI provides classification (canonical_type, component_key) only.
    # See project_session8_plan.md, feedback_figma_api_quirks.md.
    children_map: dict[str, list[str]] = {}
    has_parent = set()

    for node in nodes:
        element_id = node_id_to_element_id[node["node_id"]]
        parent_node_id = node.get("parent_id")

        if parent_node_id is not None and parent_node_id in node_id_to_element_id:
            parent_element_id = node_id_to_element_id[parent_node_id]
            if parent_element_id not in children_map:
                children_map[parent_element_id] = []
            children_map[parent_element_id].append(element_id)
            has_parent.add(element_id)

    for parent_eid, child_ids in children_map.items():
        elements[parent_eid]["children"] = child_ids

    # Root elements: containers + classified nodes that have no parent
    root_ids = [
        node_id_to_element_id[n["node_id"]]
        for n in nodes
        if node_id_to_element_id[n["node_id"]] not in has_parent
    ]

    # Build node lookup for position data
    node_by_id = {n["node_id"]: n for n in nodes}
    origin_x = data.get("screen_origin_x", 0)
    origin_y = data.get("screen_origin_y", 0)

    # Absolute positioning: children of non-auto-layout parents get explicit x/y.
    # In Figma, children of frames with no layoutMode are absolutely positioned.
    # Auto-layout children (parent has HORIZONTAL/VERTICAL) get position from flow.
    element_id_to_nid = {eid: nid for nid, eid in node_id_to_element_id.items()}

    for node in nodes:
        eid = node_id_to_element_id.get(node["node_id"])
        if eid is None:
            continue

        parent_node_id = node.get("parent_id")
        if parent_node_id is None:
            # Root-level element: position relative to screen origin
            if "layout" not in elements[eid]:
                elements[eid]["layout"] = {}
            elements[eid]["layout"]["position"] = {
                "x": (node.get("x", 0) or 0) - origin_x,
                "y": (node.get("y", 0) or 0) - origin_y,
            }
            continue

        parent_node = node_by_id.get(parent_node_id)
        if parent_node is None:
            continue

        parent_layout_mode = parent_node.get("layout_mode")
        if parent_layout_mode in ("HORIZONTAL", "VERTICAL"):
            continue  # Auto-layout child — position comes from flow

        # Parent has no auto-layout: set position relative to parent origin.
        # Prefer the Plugin API relativeTransform's translation column
        # (rt[0][2], rt[1][2]) — it's parent-local by construction. The
        # old node_x - parent_x world-delta computation is wrong when the
        # parent is rotated: it gives the world-space delta, not the
        # parent-local position. Fall back to subtraction only when
        # relativeTransform isn't captured.
        rt_json = node.get("relative_transform")
        pos_x: float
        pos_y: float
        if rt_json:
            try:
                rt = json.loads(rt_json) if isinstance(rt_json, str) else rt_json
                pos_x = float(rt[0][2])
                pos_y = float(rt[1][2])
            except (json.JSONDecodeError, IndexError, TypeError, ValueError):
                pos_x = (node.get("x", 0) or 0) - (parent_node.get("x", 0) or 0)
                pos_y = (node.get("y", 0) or 0) - (parent_node.get("y", 0) or 0)
        else:
            pos_x = (node.get("x", 0) or 0) - (parent_node.get("x", 0) or 0)
            pos_y = (node.get("y", 0) or 0) - (parent_node.get("y", 0) or 0)

        if "layout" not in elements[eid]:
            elements[eid]["layout"] = {}
        elements[eid]["layout"]["position"] = {
            "x": pos_x,
            "y": pos_y,
        }

    root_id = "screen-1"
    root_element: dict[str, Any] = {
        "type": "screen",
        "layout": {
            "direction": "absolute",
            "sizing": {"width": data.get("width", 0), "height": data.get("height", 0)},
        },
        "children": root_ids,
    }
    screen_name = data.get("screen_name")
    if screen_name:
        root_element["_original_name"] = screen_name
    elements[root_id] = root_element

    element_id_to_node_id = {eid: nid for nid, eid in node_id_to_element_id.items()}

    return {
        "version": "1.0",
        "root": root_id,
        "elements": elements,
        "tokens": data.get("tokens", {}),
        "_node_id_map": element_id_to_node_id,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_ir(
    conn: sqlite3.Connection,
    screen_id: int,
    semantic: bool = False,
    *,
    filter_chrome: bool = True,
) -> dict[str, Any]:
    """Generate CompositionSpec IR for a single screen.

    When semantic=True, collapses the flat element tree into a semantic
    tree with named slots, filters system chrome, and produces ~15-25
    elements instead of ~100+.

    `filter_chrome=False` (semantic-only) keeps system-chrome nodes in
    the spec — use this when you WANT the keyboard / safari bar / home
    indicator / status bar as design content (per
    `feedback_system_chrome_is_design.md`: system chrome is design,
    not platform artifact). Synthetic-node filtering (Figma internal
    spacers) is still applied unconditionally upstream via
    `build_composition_spec`.

    Returns dict with 'spec' (the CompositionSpec dict) and 'json' (serialized).
    """
    import json as json_mod
    import os
    data = query_screen_for_ir(conn, screen_id)
    spec = build_composition_spec(data)

    # Priority 0 probe — when DD_MARKUP_ROUNDTRIP=1, pass the spec through
    # the dd-markup serde before returning. Used to verify end-to-end
    # pixel parity via the render sweep. Default off; no behavior change.
    if os.environ.get("DD_MARKUP_ROUNDTRIP") == "1":
        from dd.markup import parse_dd, serialize_ir
        spec = parse_dd(serialize_ir(spec))

    if semantic:
        node_id_map = spec.get("_node_id_map", {})
        node_names = {}
        node_positions = {}
        for eid, nid in node_id_map.items():
            row = conn.execute(
                "SELECT name, x, y, width, height FROM nodes WHERE id = ?", (nid,),
            ).fetchone()
            if row:
                node_names[nid] = row[0]
                node_positions[nid] = {
                    "x": row[1], "y": row[2], "width": row[3], "height": row[4],
                    "name": row[0],
                }

        if filter_chrome:
            spec = filter_system_chrome(spec, node_names)

        slot_defs = query_slot_definitions(conn)
        spec = build_semantic_tree(spec, slot_defs, node_positions)

    return {
        "spec": spec,
        "json": json_mod.dumps(spec, indent=2),
        "element_count": len(spec.get("elements", {})),
        "token_count": len(spec.get("tokens", {})),
    }
