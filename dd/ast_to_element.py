"""M2 demo-blocker — grammar-head -> IR-element resolver.

The Figma renderer (`dd.render_figma_ast._emit_phase1`) reads node
properties from `spec["elements"][spec_key]` and `db_visuals[nid]`.
Both are keyed on nodes from the ORIGINAL screen. New nodes created
by `append` / `insert` / `replace` during the authoring loop have no
spec entry and no DB nid, so their subsequent `set @eid prop=value`
edits land on `node.head.properties` — where the renderer can't see
them. Result: append-heavy demos render invisible nodes.

This module exposes:

- `ast_head_to_element(node)` — walks `node.head.properties` and
  produces the minimal IR-element dict shape that the existing
  emitters (`_emit_visual`, `_emit_layout` in `dd.renderers.figma`)
  already consume. This is the inverse of `_spatial_props` /
  `_visual_props` in `dd.compress_l3`.

- `resolve_element(...)` — merges sources in precedence order
  `head.properties > spec["elements"][key] > db_visuals[nid] >
  defaults` and returns the single element-shape dict the emitters
  want.

Covered both on ORIGINAL nodes (which benefit from head-overlays for
set-on-original edits) and on NEW nodes (which have nothing BUT a
head). Same code path, no second-class emission.
"""

from __future__ import annotations

from typing import Any, Optional

from dd.markup_l3 import (
    Literal_,
    Node,
    PropAssign,
    PropGroup,
    SizingValue,
)


# Grammar-enum -> element-dict enum. Mirrors the forward direction
# in `dd.compress_l3._LAYOUT_DIRECTION` (which only covers a subset
# of the canonical grammar tokens but those are the only two the
# forward emitter outputs).
_LAYOUT_GRAMMAR_TO_ELEMENT = {
    "horizontal": "horizontal",
    "vertical": "vertical",
}


# Grammar `mainAxis` / `crossAxis` values are already canonical —
# the element dict stores the same tokens, and the downstream
# `_emit_layout` translates them into Figma's uppercase enum via
# `_ALIGNMENT_MAP`. Listed explicitly so unknown tokens are silently
# skipped (forward compat).
_MAIN_AXIS_GRAMMAR = {
    "start", "center", "end", "space-between",
    "space-around", "space-evenly",
}
_CROSS_AXIS_GRAMMAR = {
    "start", "center", "end", "stretch", "baseline",
}


# Properties the renderer reads directly from `node.head`, NOT from
# the element dict. Listing them here documents why they're skipped.
_HEAD_ONLY_PROPS = {"x", "y", "rotation", "mirror"}


# ---------------------------------------------------------------------------
# Inverse grammar — PropAssign -> element dict contribution
# ---------------------------------------------------------------------------


def _literal_py(value: Any) -> Any:
    """Extract the Python-form value from a grammar Value."""
    if isinstance(value, Literal_):
        return value.py
    return None


def _apply_layout_prop(element: dict, key: str, value: Any) -> bool:
    """Write a layout-axis PropAssign into `element`. Returns True if
    the property was recognised."""
    layout = element.setdefault("layout", {})

    if key == "layout":
        grammar = _literal_py(value)
        if isinstance(grammar, str) and grammar in _LAYOUT_GRAMMAR_TO_ELEMENT:
            layout["direction"] = _LAYOUT_GRAMMAR_TO_ELEMENT[grammar]
        return True

    if key == "gap":
        gap = _literal_py(value)
        if isinstance(gap, (int, float)):
            layout["gap"] = gap
        return True

    if key == "padding":
        if isinstance(value, PropGroup):
            padding: dict[str, float] = {}
            for entry in value.entries:
                if not isinstance(entry, PropAssign):
                    continue
                side = entry.key
                if side not in ("top", "right", "bottom", "left"):
                    continue
                side_val = _literal_py(entry.value)
                if isinstance(side_val, (int, float)):
                    padding[side] = side_val
            if padding:
                layout["padding"] = padding
        return True

    if key == "align":
        # `align=X` is grammar sugar for `mainAxis=X crossAxis=X`
        # when both axes take the same value. The only canonical form
        # the forward emitter produces is `align=center`, but the
        # parser accepts any enum token; we mirror that flexibility.
        align = _literal_py(value)
        if isinstance(align, str):
            if align in _MAIN_AXIS_GRAMMAR:
                layout["mainAxisAlignment"] = align
            if align in _CROSS_AXIS_GRAMMAR:
                layout["crossAxisAlignment"] = align
        return True

    if key == "mainAxis":
        main = _literal_py(value)
        if isinstance(main, str) and main in _MAIN_AXIS_GRAMMAR:
            layout["mainAxisAlignment"] = main
        return True

    if key == "crossAxis":
        cross = _literal_py(value)
        if isinstance(cross, str) and cross in _CROSS_AXIS_GRAMMAR:
            layout["crossAxisAlignment"] = cross
        return True

    if key in ("width", "height"):
        sizing = layout.setdefault("sizing", {})
        if isinstance(value, SizingValue):
            sizing[key] = value.size_kind
            # bounded-form min/max are carried through when present;
            # the renderer doesn't consume these today but forward
            # compat beats silently dropping them.
            if value.min is not None:
                sizing[f"{key}Min"] = value.min
            if value.max is not None:
                sizing[f"{key}Max"] = value.max
        else:
            px = _literal_py(value)
            if isinstance(px, (int, float)):
                sizing[f"{key}Pixels"] = px
        return True

    return False


def _apply_visual_prop(element: dict, key: str, value: Any) -> bool:
    """Write a visual-axis PropAssign into `element`. Returns True if
    the property was recognised."""
    visual = element.setdefault("visual", {})

    if key == "fill":
        color = _literal_py(value)
        if isinstance(color, str):
            visual["fills"] = [{"type": "solid", "color": color}]
        return True

    if key == "stroke":
        color = _literal_py(value)
        if isinstance(color, str):
            strokes = visual.setdefault("strokes", [])
            if strokes:
                strokes[0]["color"] = color
                strokes[0].setdefault("type", "solid")
            else:
                strokes.append({
                    "type": "solid", "color": color, "width": 1,
                })
        return True

    if key == "stroke-weight":
        width = _literal_py(value)
        if isinstance(width, (int, float)):
            strokes = visual.setdefault("strokes", [])
            if strokes:
                strokes[0]["width"] = width
            else:
                # Width-only stroke — no colour. Matches the
                # forward-direction gating where `stroke-weight` can
                # ship with or without a colour.
                strokes.append({"type": "solid", "width": width})
        return True

    if key == "radius":
        radius = _literal_py(value)
        if isinstance(radius, (int, float)):
            visual["cornerRadius"] = radius
        return True

    if key == "opacity":
        op = _literal_py(value)
        if isinstance(op, (int, float)):
            visual["opacity"] = op
        return True

    return False


def _apply_top_level_prop(element: dict, key: str, value: Any) -> bool:
    """Write a node-level (non-layout, non-visual) PropAssign into
    `element`. Returns True if the property was recognised."""
    if key == "visible":
        vis = _literal_py(value)
        if isinstance(vis, bool):
            element["visible"] = vis
        return True
    return False


def ast_head_to_element(node: Node) -> dict[str, Any]:
    """Build a minimal IR-element dict from `node.head.properties`.

    The output follows the shape consumed by `_emit_visual` /
    `_emit_layout` — `{"layout": {...}, "visual": {...}, "visible":
    bool}`. Only keys ACTUALLY present on `node.head.properties` make
    it into the result; missing keys are simply absent so the caller
    can overlay this dict onto a spec/db base without clobbering.

    Defensive:
    - A node with no `head.properties` attribute returns `{}`.
    - `PathOverride` entries (no `.key`) are silently skipped.
    - Unknown property keys are silently skipped (forward compat).
    - Unknown value shapes are silently skipped — the emitters
      tolerate missing fields, never partial-write.
    """
    element: dict[str, Any] = {}

    head = getattr(node, "head", None)
    if head is None:
        return element

    properties = getattr(head, "properties", None)
    if not properties:
        return element

    for prop in properties:
        # PathOverride has no `.key`; skip without raising.
        if not hasattr(prop, "key"):
            continue

        key = prop.key
        value = getattr(prop, "value", None)

        if key in _HEAD_ONLY_PROPS:
            continue

        if _apply_layout_prop(element, key, value):
            continue
        if _apply_visual_prop(element, key, value):
            continue
        if _apply_top_level_prop(element, key, value):
            continue
        # Unknown key -> silent skip

    # Drop empty sub-dicts so `element` cleanly overlays onto a base
    # without announcing absent groups.
    if "layout" in element and not element["layout"]:
        del element["layout"]
    if "visual" in element and not element["visual"]:
        del element["visual"]

    return element


# ---------------------------------------------------------------------------
# Three-source resolver — precedence head > spec > db > default
# ---------------------------------------------------------------------------


def _deep_merge_element_keys(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    """Merge `overlay` onto `base` recursively for nested dicts. Lists
    (e.g. `fills`, `strokes`) are REPLACED whole, not merged.

    Contract: only keys PRESENT in `overlay` are touched — absent keys on
    `overlay` do not clobber `base`. This holds at every nesting depth,
    not just the top level.

    Figma fills/strokes are ordered stacks — merging them by index would
    silently corrupt the stack. The caller (head / spec / db) owns the
    full list when it mentions the key at all.

    Does not mutate inputs.

    F13a context (2026-04-25): the previous implementation only merged
    one level deep — when `overlay["layout"]["sizing"]` was a dict and
    `base["layout"]["sizing"]` was also a dict, the inner merge wrote
    overlay's sizing-dict whole into the result, clobbering sibling
    sizing keys (e.g. `widthPixels` from spec spec was lost when AST
    head only carried `width=hug`). Bug surface: bordered table on HGB
    Transactions Selected rendered 100×950 instead of 1400×950 because
    `widthPixels: 1400` was dropped during the merge. Codex review
    (2026-04-25): "Make `_deep_merge_element_keys` recursively
    deep-merge dicts while continuing to replace lists whole. That
    preserves `layout.sizing.widthPixels` without requiring AST head
    emission to know about spec provenance."
    """
    result: dict[str, Any] = {k: v for k, v in base.items()}
    for key, value in overlay.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            # Recurse so absent inner keys on the overlay don't clobber
            # the base's inner keys (the F13a fix).
            result[key] = _deep_merge_element_keys(result[key], value)
        else:
            result[key] = value
    return result


def resolve_element(
    *,
    node: Node,
    spec_elements: dict[str, dict[str, Any]],
    spec_key: str,
    db_visuals: dict[int, dict[str, Any]],
    nid: Optional[int],
    nid_map: dict[int, int],
) -> dict[str, Any]:
    """Merge element sources in precedence order:

        head.properties > spec["elements"][key] > db_visuals[nid]
        > defaults (empty)

    Returns the merged element-shape dict that downstream Figma
    emitters can consume. Head-overlay is applied to BOTH original
    nodes (where it captures `set @eid ...` edits) and new nodes
    (where it's the only source).

    `nid_map` is accepted for API symmetry with the caller — today
    only `nid` is consulted. Keeping the slot lets future versions
    look up the node's nid from its identity if `nid` is None.

    CRITICAL precedence guard: only KEYS that head mentions take
    precedence over spec/db. An absent `head.padding` must not
    clobber a present `spec["elements"][key]["layout"]["padding"]`.
    `ast_head_to_element` already omits absent keys, and
    `_deep_merge_element_keys` only writes keys that are present in
    the overlay.
    """
    base: dict[str, Any] = {}

    # Layer 1 — DB visual (weakest, other than an empty default).
    # Simple shallow lift into `visual`: the renderer's existing
    # `build_visual_from_db` path is still invoked upstream on the
    # raw DB row; this resolver is additive and only supplies a
    # base for NEW-node / edit-heavy paths where `raw_visual` is
    # empty. Priority is correctness over optimisation.
    if nid is not None and nid in db_visuals:
        db_visual = db_visuals[nid]
        if isinstance(db_visual, dict) and db_visual:
            base["visual"] = dict(db_visual)

    # Layer 2 — spec element.
    spec_element = spec_elements.get(spec_key) if spec_elements else None
    if isinstance(spec_element, dict) and spec_element:
        base = _deep_merge_element_keys(base, spec_element)

    # Layer 3 — head overlay. Highest precedence.
    head_element = ast_head_to_element(node)
    if head_element:
        base = _deep_merge_element_keys(base, head_element)

    return base


__all__ = ["ast_head_to_element", "resolve_element"]
