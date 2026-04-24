"""Prompt→IR composition + template-based rendering (Phase 4b).

Composes a CompositionSpec from a list of component descriptions,
populates visual data from extracted templates, and generates Figma JS.

ADR-008 Mode-3 integration: when an LLM component has no ``children``
and no ``component_key`` (i.e. neither Mode-1 instance nor extracted
DB subtree applies), :func:`_build_element` consults the composition
``ProviderRegistry`` and synthesises structural child IR nodes from
the resolved template's slot grammar.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from dd.compress_l3 import compress_to_l3_with_maps
from dd.render_figma_ast import render_figma
from dd.renderers.figma import collect_fonts
from dd.templates import query_templates

_DIRECTION_MAP = {
    "HORIZONTAL": "horizontal",
    "VERTICAL": "vertical",
}

_SIZING_MAP = {
    "FILL": "fill",
    "HUG": "hug",
    "FIXED": "fixed",
}


def _semantic_type(element: dict[str, Any]) -> str:
    """Return the element's semantic type (role-first, with type fallback).

    Compose reads "semantic type" for template lookup / type counting /
    warning emission. Post-Stage-1 DB-sourced IR has ``role`` (semantic
    classifier label) and ``type`` (structural primitive) split; Mode 3
    LLM-generated IR still uses the conflated ``type`` only. This
    helper handles both shapes by reading role-first then falling
    through to type.

    See docs/plan-type-role-split.md §4 Stage 3a.
    """
    return element.get("role") or element.get("type", "")


def _ckr_is_built(conn: sqlite3.Connection) -> bool:
    """Return True iff `component_key_registry` exists and has rows.

    Shared by `generate_from_prompt` and `dd.renderers.figma.
    generate_screen`; both pipelines gate Mode-1 instance resolution
    on CKR presence and need the same boolean to set the
    `ckr_built` kwarg on the renderer.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='component_key_registry'"
    ).fetchone()
    if not exists:
        return False
    row = conn.execute(
        "SELECT COUNT(*) FROM component_key_registry"
    ).fetchone()
    return bool(row and row[0] > 0)


def _pick_best_template(
    tmpl_list: list[dict[str, Any]] | None,
    variant: str | None = None,
) -> dict[str, Any] | None:
    """Pick the best template from a list, preferring one with a component_key.

    When variant is provided, prefers the template matching that variant name.
    Otherwise prefers the keyed template with the highest instance count (Mode 1).
    Falls back to keyless (Mode 2) if no keyed template exists.
    """
    if not tmpl_list:
        return None

    if variant:
        match = next((t for t in tmpl_list if t.get("variant") == variant), None)
        if match:
            return match

    keyed = [t for t in tmpl_list if t.get("component_key")]
    if keyed:
        return max(keyed, key=lambda t: t.get("instance_count") or 0)
    return tmpl_list[0]


def compose_screen(
    components: list[dict[str, Any]],
    templates: dict[str, list[dict[str, Any]]] | None = None,
    registry: Any | None = None,
) -> dict[str, Any]:
    """Build a CompositionSpec from a list of component descriptions.

    Each component is a dict with 'type' (required), 'props' (optional),
    and 'children' (optional, recursive). Templates provide layout
    defaults (dimensions, padding, direction) when available.

    ADR-008 Mode-3: leaves with no ``children`` and no ``component_key``
    go through :func:`_mode3_synthesise` which consults a default
    provider registry and produces synthetic child IR elements (e.g. a
    ``button`` with ``props.text="Sign In"`` gets a text child carrying
    the label).

    v0.2 retrieval: when ``registry`` is provided with a
    :class:`CorpusRetrievalProvider` at higher priority, matching
    component types have their real DB subtree spliced into the emitted
    spec instead of synthesising from hand-authored templates.
    """
    type_counters: dict[str, int] = {}
    elements: dict[str, dict[str, Any]] = {}

    def _allocate_id(comp_type: str, preferred_eid: str | None = None) -> str:
        """Allocate an eid for a new element.

        Stage 0.4: when the planner supplied a ``preferred_eid`` (a
        named entity like ``product-showcase-section``), honour it so
        the LLM's own ontology survives into downstream addressing
        (edit grammar, drift check, session log). Falls back to the
        counter form when the preferred eid is missing, non-string,
        whitespace-only, or already taken — callers rely on compose
        never crashing on a duplicate, even though Stage 0.6's drift
        check is expected to surface duplicate-eid as KIND_PLAN_DRIFT
        before composition runs.
        """
        if (
            isinstance(preferred_eid, str)
            and preferred_eid.strip()
            and preferred_eid not in elements
        ):
            return preferred_eid
        type_counters[comp_type] = type_counters.get(comp_type, 0) + 1
        return f"{comp_type}-{type_counters[comp_type]}"

    def _try_corpus_splice(
        comp: dict[str, Any],
    ) -> str | None:
        """Query the registry for a corpus_subtree; splice if present.

        Only fires full-subtree splice when the LLM provided no
        ``children`` for this component — that's the signal we're
        free to use the corpus's structural intent. When the LLM gave
        children, the retrieval contribution reduces to applying the
        root element's visual / layout onto the caller's element
        (a subsequent step via ``_apply_retrieved_root_visual``), and
        recursion into LLM children proceeds normally. This respects
        LLM structural intent and prevents over-splicing large
        corpus subtrees into prompts that asked for something small.

        Returns the newly-allocated element id for the spliced root
        when a full-subtree splice happens, or None otherwise.
        """
        if registry is None:
            return None
        if comp.get("children"):
            return None
        comp_type = comp["type"]
        variant = comp.get("variant")
        template, _errors = registry.resolve(comp_type, variant, {})
        if template is None or getattr(template, "corpus_subtree", None) is None:
            return None
        return _splice_subtree(
            template.corpus_subtree,
            llm_props=comp.get("props") or {},
            elements=elements,
            allocate_id=_allocate_id,
        )

    def _apply_retrieved_root_visual(
        comp: dict[str, Any],
        element: dict[str, Any],
    ) -> bool:
        """When retrieval has a subtree for this type but we chose not
        to full-splice (LLM gave children), copy the subtree ROOT's
        visual + layout onto the caller's element. This gives us the
        DB's real fills/strokes/effects/corner_radius on the parent
        while preserving LLM-supplied children below.

        Registry.resolve stops at the first matching provider, so when
        corpus retrieval wins, UniversalCatalogProvider's token-based
        layout defaults (gap/align/primary_axis) never fire. We pull
        them explicitly here as a fallback layer so every element gets
        a sensible auto-layout shape even when retrieval contributes
        the paint.

        Returns True if retrieval contributed, False otherwise.
        """
        if registry is None:
            return False
        comp_type = comp["type"]
        variant = comp.get("variant")
        # Context hint for structural-match ranking in the provider:
        # the canonical types of the LLM plan's direct children.
        ctx = {
            "expected_children": [
                c.get("type") for c in (comp.get("children") or [])
                if c.get("type")
            ],
        }
        template, _errors = registry.resolve(comp_type, variant, ctx)
        if template is None or getattr(template, "corpus_subtree", None) is None:
            return False
        subtree = template.corpus_subtree
        root_elem = subtree["elements"][subtree["root"]]
        if root_elem.get("visual"):
            element.setdefault("visual", {}).update(root_elem["visual"])
            element["_corpus_source_node_id"] = root_elem.get(
                "_corpus_source_node_id",
            )
        if root_elem.get("layout"):
            layout = element.setdefault("layout", {})
            for k, v in root_elem["layout"].items():
                layout.setdefault(k, v)
        _apply_universal_template_fallback(comp_type, variant, element)
        return True

    def _build_element(comp: dict[str, Any]) -> str:
        spliced_eid = _try_corpus_splice(comp)
        if spliced_eid is not None:
            return spliced_eid

        comp_type = comp["type"]
        eid = _allocate_id(comp_type, preferred_eid=comp.get("eid"))

        element: dict[str, Any] = {"type": comp_type}

        variant = comp.get("variant")
        if variant:
            element["variant"] = variant

        component_key = comp.get("component_key")
        if component_key:
            element["component_key"] = component_key

        layout = _build_layout_from_template(comp_type, templates, variant=variant)
        layout_direction_override = comp.get("layout_direction")
        if layout_direction_override:
            layout["direction"] = layout_direction_override
        layout_sizing_override = comp.get("layout_sizing")
        if layout_sizing_override:
            if "sizing" not in layout:
                layout["sizing"] = {}
            layout["sizing"].update(layout_sizing_override)
        if layout:
            element["layout"] = layout

        props = comp.get("props")
        if props:
            element["props"] = dict(props)

        # ADR-008 v0.1.5 H1: apply PresentationTemplate.layout +
        # .style to the parent element *unconditionally* when this
        # node isn't a Mode-1 instance (component_key wins). Before
        # H1 this only happened inside _mode3_synthesise_children,
        # which is gated on "no LLM children" — so any LLM-supplied
        # parent silently lost its fill / stroke / radius / padding.
        # v0.2: if corpus retrieval has a subtree for this type, copy
        # the root's real DB visual + layout onto the element first;
        # universal-catalog merge below only fills gaps.
        if not component_key:
            _apply_retrieved_root_visual(comp, element)
            _apply_template_to_parent(comp_type, variant, element)

        children = comp.get("children", [])
        if children:
            child_ids = [_build_element(child) for child in children]
            element["children"] = child_ids
            elements[eid] = element
            return eid
        elif (
            not component_key
            and not _mode3_disabled()
            and comp_type not in _LEAF_TYPES_FOR_HOIST
        ):
            # Mode-3 fall-through: synthesise children when the LLM
            # provided none AND the parent type can legitimately host
            # children. Tier D.3 F4 gate: leaf types (button, icon,
            # switch, chip, etc.) resolve Mode-1 to INSTANCE — their
            # internal structure comes from the library master and
            # they can't host added children (Figma Plugin API
            # rejects `instance.appendChild`). If Mode-3 synthesises
            # a text child here, Phase 2 would throw and cascade
            # (F3). Template-to-parent merge already happened above
            # via _apply_template_to_parent; leaf types get their
            # visible text via props.text instead.
            synthetic_by_pos = _mode3_synthesise_children(
                comp_type, variant, props or {}, elements, _allocate_id,
                parent_element=None,
            )
            external_top = synthetic_by_pos.get("top") or []
            external_bottom = synthetic_by_pos.get("bottom") or []
            internal_ids: list[str] = []
            for pos, ids in synthetic_by_pos.items():
                if pos in ("top", "bottom"):
                    continue
                internal_ids.extend(ids)
            if internal_ids:
                element["children"] = internal_ids

            # Label-hoist (per docs/research/scorer-calibration-and-
            # som-fidelity.md §6.1): slots declared with position="top"
            # or "bottom" are EXTERNAL siblings, not internal children.
            # SoM surfaced the bug — text_input was rendering as a
            # container of stacked text labels because we lumped the
            # `label` slot as internal. Fix: wrap the parent in an
            # outer vertical frame when external positions are present.
            if external_top or external_bottom:
                elements[eid] = element
                wrapper_eid = _allocate_id("frame")
                wrapper_children: list[str] = []
                wrapper_children.extend(external_top)
                wrapper_children.append(eid)
                wrapper_children.extend(external_bottom)
                wrapper_layout: dict[str, Any] = {
                    "direction": "vertical",
                    "sizing": {"width": "fill", "height": "hug"},
                    "gap": 4,
                }
                wrapper: dict[str, Any] = {
                    "type": "frame",
                    "layout": wrapper_layout,
                    "children": wrapper_children,
                    "_label_hoist": {
                        "parent_type": comp_type,
                        "external_top": list(external_top),
                        "external_bottom": list(external_bottom),
                    },
                }
                elements[wrapper_eid] = wrapper
                return wrapper_eid

        elements[eid] = element
        return eid

    root_child_ids = [_build_element(comp) for comp in components]

    root_id = "screen-1"
    # v3-memo items 1+2: screen root defaults to vertical auto-layout
    # with FILL-width children. Fixes the "children stack in top-left,
    # overlapping at 50px y-increments" failure mode that survived the
    # Mode-3 prop-expansion fix.
    screen_layout: dict[str, Any] = {
        "direction": "vertical",
        "sizing": {"width": 428, "height": 926},
        "padding": {"top": 16, "right": 16, "bottom": 16, "left": 16},
        "gap": 12,
        "primary_axis_sizing": "FIXED",
        "counter_axis_sizing": "FIXED",
    }

    screen_tmpl = _pick_best_template(templates.get("screen")) if templates else None
    if screen_tmpl:
        w = screen_tmpl.get("width")
        h = screen_tmpl.get("height")
        if w and h:
            screen_layout["sizing"] = {"width": w, "height": h}
        # Honor an extracted screen template's auto-layout direction if present
        direction = _DIRECTION_MAP.get(screen_tmpl.get("layout_mode") or "")
        if direction:
            screen_layout["direction"] = direction

    # Vertical-auto-layout screens: children stack by tree order. Drop
    # the old y_cursor positioning, and mark each non-screen root child
    # as FILL-width so it spans the screen instead of the createFrame()
    # default 100px. Opt-out: if a child has an explicit position
    # (from a template), preserve it — the renderer gates on direction.
    if screen_layout["direction"] in ("vertical", "horizontal"):
        for child_id in root_child_ids:
            child = elements[child_id]
            if "layout" not in child:
                child["layout"] = {}
            layout = child["layout"]
            sizing = layout.setdefault("sizing", {})
            # Child spans screen width unless it already declared one.
            if "width" not in sizing:
                sizing["width"] = "fill"
            # Clear any absolute-positioning inherited from an earlier
            # compose path — meaningless inside auto-layout.
            layout.pop("position", None)
    else:
        # Legacy absolute path (preserves old behavior when a screen
        # template explicitly demands it).
        _DEFAULT_ELEMENT_HEIGHT = 50
        y_cursor: float = 0
        for child_id in root_child_ids:
            child = elements[child_id]
            if "layout" not in child:
                child["layout"] = {}
            child["layout"]["position"] = {"x": 0, "y": y_cursor}
            sizing = child["layout"].get("sizing", {})
            child_height = sizing.get("heightPixels") or sizing.get("height")
            if isinstance(child_height, (int, float)):
                y_cursor += child_height
            else:
                y_cursor += _DEFAULT_ELEMENT_HEIGHT

    elements[root_id] = {
        "type": "screen",
        "layout": screen_layout,
        "clipsContent": True,
        "children": root_child_ids,
    }

    # ADR-008 Mode-3 v0.1: seed the spec tokens dict with shadcn-flavoured
    # literal fallbacks so token refs in PresentationTemplates resolve
    # at emit time. A real project token cascade replaces this in v0.2.
    seeded_tokens: dict[str, Any] = {}
    if not _mode3_disabled():
        seeded_tokens.update(_UNIVERSAL_MODE3_TOKENS)

    return {
        "version": "1.0",
        "root": root_id,
        "elements": elements,
        "tokens": seeded_tokens,
        "_node_id_map": {},
    }


def _mode3_disabled() -> bool:
    """True when ``DD_DISABLE_MODE_3`` env var is set to a non-empty value."""
    return bool(os.environ.get("DD_DISABLE_MODE_3", "").strip())


def _splice_subtree(
    corpus_subtree: dict[str, Any],
    *,
    llm_props: dict[str, Any],
    elements: dict[str, dict[str, Any]],
    allocate_id,
) -> str:
    """Splice a retrieved corpus subtree into ``elements``.

    The subtree's internal element ids are renumbered through
    ``allocate_id`` so they don't collide with IDs the caller has
    already allocated. LLM-supplied text props are substituted into the
    subtree's text slots in tree order (first LLM text → first text
    slot, etc.). Returns the spliced root's newly-allocated id.
    """
    subtree_elements = corpus_subtree["elements"]
    subtree_root = corpus_subtree["root"]

    # Pre-allocate new ids for every node in the subtree so child
    # references can be rewritten in a single pass.
    id_remap: dict[str, str] = {}
    for old_eid, elem in subtree_elements.items():
        id_remap[old_eid] = allocate_id(elem["type"])

    # Gather LLM text values (in stable order). Empty strings are kept
    # — if the LLM said ``text=""`` they intended blank, and we must
    # NOT fall back to the DB's original text (which leaks source-
    # screen content like "Do the thing" or "Buy Trophy").
    llm_texts = _extract_llm_text_values(llm_props, include_empty=True)
    text_slot_idx = 0

    # BFS the subtree in the stored order; copy into ``elements`` with
    # child references rewritten to the new ids.
    for old_eid, elem in subtree_elements.items():
        new_eid = id_remap[old_eid]
        new_elem = {k: v for k, v in elem.items() if k != "children"}

        # Overwrite every text slot in the retrieved subtree. Use the
        # LLM's text in order when available, else empty string. Never
        # let a DB original text stand — that's a leak of the source
        # screen's content into a Mode-3 output.
        if isinstance(new_elem.get("props"), dict) and "text" in new_elem["props"]:
            if text_slot_idx < len(llm_texts):
                new_elem["props"]["text"] = llm_texts[text_slot_idx]
            else:
                new_elem["props"]["text"] = ""
            text_slot_idx += 1

        old_children = elem.get("children", [])
        if old_children:
            new_elem["children"] = [id_remap[c] for c in old_children]

        elements[new_eid] = new_elem

    return id_remap[subtree_root]


def _extract_llm_text_values(
    props: dict[str, Any],
    *,
    include_empty: bool = False,
) -> list[str]:
    """Pull text-like string values from an LLM props dict, in a stable
    order. Keys like 'text', 'title', 'subtitle', 'label', 'caption',
    'body' are treated as text slots.

    When ``include_empty`` is True, empty strings are kept — caller
    intent is "blank text," not "I didn't supply one." The splice path
    uses this so LLM-intended-blank never falls back to DB originals.
    """
    text_keys = ("text", "title", "heading", "subtitle", "label", "caption", "body")
    out: list[str] = []
    for k in text_keys:
        v = props.get(k)
        if isinstance(v, str) and (v or include_empty):
            out.append(v)
    return out


# Prop-name aliases we try when filling a text-typed slot. The LLM
# emits 'text' on most leaves regardless of the catalog's nominal slot
# name; headers use 'title'; text_input uses 'placeholder'/'label'.
# This list is intentionally short — slot semantics stay in catalog
# slot_definitions; the aliases only cover LLM idiom drift.
_TEXT_SLOT_PROP_ALIASES: tuple[str, ...] = (
    "text", "label", "title", "headline", "placeholder", "message", "description",
)

# Some alias props are semantically positional — they should not fill
# a slot at an incompatible position. Without this, an LLM emitting
# ``text_input {props: {placeholder: "Search..."}}`` (no label) would
# see the "placeholder" alias swallowed by the label slot (position=top)
# because it's first in slot-declaration order. Surfaced by SoM coverage
# test 2026-04-21.
#
# Keyed on the alias prop name. Value is the set of slot positions the
# alias is allowed to fill. Aliases absent from this map match any
# position (preserving prior behavior for generic aliases like "text").
_ALIAS_POSITION_WHITELIST: dict[str, frozenset[str]] = {
    "placeholder": frozenset({"fill", "start", "end", "_default"}),
    "helper": frozenset({"bottom"}),
}


# ---------------------------------------------------------------------------
# Mode-3 universal token seed (ADR-008 v0.1)
#
# Shadcn-derived literal fallback values for the DTCG refs the
# UniversalCatalogProvider's PresentationTemplates emit. Without a real
# token cascade wired (v0.2), these seed the spec's ``tokens`` dict so
# the renderer's ``resolve_style_value`` finds concrete values at emit
# time. Values approximate shadcn defaults: 16-pixel spacing grid, 8px
# radius, sans text stack, neutral palette plus an accent blue.
# ---------------------------------------------------------------------------
_UNIVERSAL_MODE3_TOKENS: dict[str, Any] = {
    # Spacing
    "space.button.padding_x": 16,
    "space.button.padding_y": 10,
    "space.button.gap": 8,
    "space.icon_button.padding": 8,
    "space.input.gap": 6,
    "space.card.padding_x": 16,
    "space.card.padding_y": 16,
    "space.card.gap": 12,
    "space.generic.padding_x": 12,
    "space.generic.padding_y": 8,
    "space.generic.gap": 8,
    "space.dialog.padding_x": 24,
    "space.dialog.padding_y": 24,
    "space.dialog.gap": 16,
    "space.toggle.gap": 8,
    "space.checkbox.gap": 8,
    "space.list_item.padding_x": 16,
    "space.list_item.padding_y": 12,
    "space.list_item.gap": 12,
    # Radii
    "radius.button": 8,
    "radius.input": 8,
    "radius.card": 12,
    "radius.dialog": 16,
    "radius.toggle": 999,
    "radius.checkbox": 4,
    "radius.default": 8,
    # Colors (shadcn neutral + primary blue)
    "color.action.primary.bg": "#0F172A",
    "color.action.primary.fg": "#F8FAFC",
    "color.action.secondary.bg": "#E2E8F0",
    "color.action.secondary.fg": "#0F172A",
    "color.action.destructive.bg": "#EF4444",
    "color.action.destructive.fg": "#FFFFFF",
    "color.action.ghost.bg": "#FFFFFF00",
    "color.action.ghost.fg": "#0F172A",
    "color.action.default.bg": "#F1F5F9",
    "color.action.default.fg": "#0F172A",
    "color.input.bg": "#FFFFFF",
    "color.input.border": "#CBD5E1",
    "color.surface.card": "#FFFFFF",
    "color.surface.card_border": "#E2E8F0",
    "color.surface.dialog": "#FFFFFF",
    "color.surface.list_item": "#FFFFFF",
    "color.surface.default": "#F8FAFC",
    "color.toggle.track.off": "#E2E8F0",
    "color.toggle.thumb": "#FFFFFF",
    "color.checkbox.fill": "#FFFFFF",
    "color.checkbox.border": "#94A3B8",
    # Typography — split into per-type (family, size, weight) so
    # the renderer's _emit_text_props can consume them directly.
    "typography.button.fontFamily": "Inter",
    "typography.button.fontSize": 14,
    "typography.button.fontWeight": 600,
    "typography.input.fontFamily": "Inter",
    "typography.input.fontSize": 14,
    "typography.input.fontWeight": 400,
    "typography.list_item.fontFamily": "Inter",
    "typography.list_item.fontSize": 15,
    "typography.list_item.fontWeight": 500,
    "typography.body.fontFamily": "Inter",
    "typography.body.fontSize": 14,
    "typography.body.fontWeight": 400,
    "typography.heading.fontFamily": "Inter",
    "typography.heading.fontSize": 20,
    "typography.heading.fontWeight": 700,
    "typography.header.fontSize": 17,
    "typography.header.fontWeight": 600,
    "typography.caption.fontSize": 12,
    "typography.caption.fontWeight": 400,
    "typography.badge.fontSize": 12,
    "typography.badge.fontWeight": 600,
    "typography.avatar.fontSize": 14,
    "typography.avatar.fontWeight": 600,
    # Text-foreground colors — separate from surface colors so body
    # text on white cards doesn't inherit the card's fill as its fg
    # (which was the low-contrast complaint in 00e).
    "color.text.default": "#0F172A",
    "color.text.heading": "#020617",
    "color.text.caption": "#475569",
    "color.text.link": "#2563EB",
    "color.text.on_tooltip": "#FFFFFF",
    "color.text.on_primary": "#F8FAFC",
    "color.text.on_destructive": "#FFFFFF",
    # Additional surface colors for the 11 new backbone templates.
    "color.surface.header": "#FFFFFF",
    "color.surface.header_border": "#E2E8F0",
    "color.surface.drawer": "#FFFFFF",
    "color.surface.drawer_border": "#E2E8F0",
    "color.surface.menu": "#FFFFFF",
    "color.surface.menu_border": "#E2E8F0",
    "color.surface.popover": "#FFFFFF",
    "color.surface.popover_border": "#E2E8F0",
    "color.surface.tooltip": "#0F172A",
    "color.surface.badge": "#F1F5F9",
    "color.surface.image_placeholder": "#E2E8F0",
    "color.avatar.fill": "#E2E8F0",
    "color.avatar.fg": "#334155",
    # Status palette for badge / alert tone variants.
    "color.status.success.bg": "#22C55E",
    "color.status.success.fg": "#FFFFFF",
    "color.status.warning.bg": "#F59E0B",
    "color.status.warning.fg": "#FFFFFF",
    "color.status.info.bg": "#3B82F6",
    "color.status.info.fg": "#FFFFFF",
    # Spacing (additional)
    "space.input.padding_x": 12,
    "space.input.padding_y": 10,
    "space.header.padding_x": 16,
    "space.header.padding_y": 12,
    "space.header.gap": 8,
    "space.drawer.padding_x": 16,
    "space.drawer.padding_y": 24,
    "space.drawer.gap": 4,
    "space.menu.padding_x": 8,
    "space.menu.padding_y": 8,
    "space.menu.gap": 2,
    "space.popover.padding_x": 16,
    "space.popover.padding_y": 16,
    "space.popover.gap": 8,
    "space.tooltip.padding_x": 8,
    "space.tooltip.padding_y": 4,
    "space.badge.padding_x": 8,
    "space.badge.padding_y": 4,
    "space.badge.gap": 4,
    # Radii
    "radius.badge": 999,
    "radius.menu": 8,
    "radius.popover": 8,
    "radius.tooltip": 6,
    "radius.image": 8,
    # Effects
    # ADR-008 v0.1.5 H2: non-zero shadow elevations. Cards / dialogs /
    # menus / popovers all want modest elevation to read as floating
    # surfaces. Elevation is a y-offset in pixels; renderer synthesises
    # the drop-shadow with 2× blur + 10 % alpha.
    "shadow.card": 2,
    "shadow.dialog": 8,
    "shadow.menu": 4,
    "shadow.popover": 4,
}


def _default_provider_registry():
    """Lazy-built default registry for Mode-3 synthesis.

    Only the universal provider is wired in v0.1. Project CKR and
    ingested providers join the registry once their DB wiring is in
    place in the generate-prompt code path (which has a DB connection).
    """
    from dd.composition.providers.universal import UniversalCatalogProvider
    from dd.composition.registry import build_registry_from_env

    return build_registry_from_env([UniversalCatalogProvider()])


def _build_default_mode3_registry(conn: sqlite3.Connection):
    """Build the default Mode-3 cascade with corpus retrieval.

    Always includes CorpusRetrievalProvider — its ``supports()`` gates
    on ``DD_ENABLE_CORPUS_RETRIEVAL`` internally, so when the flag is
    off the provider quietly falls through to UniversalCatalogProvider.
    """
    from dd.composition.providers.corpus_retrieval import CorpusRetrievalProvider
    from dd.composition.providers.universal import UniversalCatalogProvider
    from dd.composition.registry import build_registry_from_env

    return build_registry_from_env([
        CorpusRetrievalProvider(conn=conn),
        UniversalCatalogProvider(),
    ])


def _apply_universal_template_fallback(
    comp_type: str,
    variant: str | None,
    element: dict[str, Any],
) -> None:
    """Apply the UniversalCatalogProvider template's layout/style onto
    the element without going through the priority cascade.

    Used when corpus retrieval already contributed the element's
    visual/layout at the root level but we still want the universal
    catalog's token-based gap/align/sizing defaults to fill gaps.
    Bypasses the registry because corpus-retrieval won the cascade.
    """
    if _mode3_disabled():
        return
    from dd.composition.providers.universal import UniversalCatalogProvider

    tmpl = UniversalCatalogProvider().resolve(comp_type, variant, {})
    if tmpl is None:
        return
    # Apply layout.
    parent_layout = element.setdefault("layout", {})
    for key, value in (tmpl.layout or {}).items():
        if key == "sizing":
            sizing = parent_layout.setdefault("sizing", {})
            for sk, sv in (value or {}).items():
                sizing.setdefault(sk, sv)
        elif key == "padding":
            existing = parent_layout.setdefault("padding", {})
            if isinstance(value, dict):
                x_val = value.get("x")
                y_val = value.get("y")
                for side, v in (("top", y_val), ("bottom", y_val),
                                ("left", x_val), ("right", x_val)):
                    if v is not None and side not in existing:
                        existing[side] = v
                for side in ("top", "right", "bottom", "left"):
                    if side in value and side not in existing:
                        existing[side] = value[side]
        elif key not in parent_layout:
            parent_layout[key] = value


def _apply_template_to_parent(
    comp_type: str,
    variant: str | None,
    element: dict[str, Any],
) -> None:
    """Merge a resolved ``PresentationTemplate``'s layout + style onto
    the parent element.

    Called unconditionally from ``_build_element`` for every non-Mode-1
    node, regardless of whether the LLM or synthesis provides the
    children. Before v0.1.5 H1 this merge was embedded in
    ``_mode3_synthesise_children`` and so never fired when the LLM
    supplied children — the root-cause of the "cards render as
    invisible rectangles" forensic finding at
    ``docs/research/mode3-forensic-analysis.md``.

    Tokens remain as ``{name}`` refs; the renderer's
    ``resolve_style_value`` resolves them against the spec-level
    ``tokens`` dict seeded with :data:`_UNIVERSAL_MODE3_TOKENS`.
    """
    if _mode3_disabled():
        return
    registry = _default_provider_registry()
    template, _errors = registry.resolve(comp_type, variant, {})
    if template is None:
        return

    parent_layout = element.setdefault("layout", {})
    for key, value in (template.layout or {}).items():
        # Don't clobber caller-supplied overrides (direction from
        # layout_direction, width/height explicitly set).
        if key == "sizing":
            sizing = parent_layout.setdefault("sizing", {})
            for sk, sv in (value or {}).items():
                sizing.setdefault(sk, sv)
        elif key == "padding":
            # PresentationTemplates express padding as {x, y} (horizontal
            # and vertical). The renderer's `_emit_auto_layout` reads
            # `padding.{top,right,bottom,left}`. Normalise at merge time
            # so padding actually lands in the generated script.
            existing = parent_layout.setdefault("padding", {})
            if isinstance(value, dict):
                x_val = value.get("x")
                y_val = value.get("y")
                for side, v in (("top", y_val), ("bottom", y_val),
                                ("left", x_val), ("right", x_val)):
                    if v is not None and side not in existing:
                        existing[side] = v
                # If the template already used top/right/bottom/left,
                # still forward those.
                for side in ("top", "right", "bottom", "left"):
                    if side in value and side not in existing:
                        existing[side] = value[side]
        elif key == "gap":
            # Gap in auto-layout maps to itemSpacing. The renderer reads
            # layout.gap directly, but it also accepts layout.itemSpacing.
            # Leave as `gap` so renderer handles either form.
            if "gap" not in parent_layout:
                parent_layout["gap"] = value
        elif key not in parent_layout:
            parent_layout[key] = value
    # Seed pixel dims from the template's style.height_pixels /
    # width_pixels — these are concrete numbers even before
    # token resolution, and give the renderer a resize() seed
    # that beats the 100×100 createFrame default.
    style = template.style or {}
    sizing = parent_layout.setdefault("sizing", {})
    if "heightPixels" not in sizing and isinstance(style.get("height_pixels"), (int, float)):
        sizing["heightPixels"] = style["height_pixels"]
    if "widthPixels" not in sizing and isinstance(style.get("width_pixels"), (int, float)):
        sizing["widthPixels"] = style["width_pixels"]
    # Surface fills / radius / stroke / shadow refs as IR style so
    # the renderer's _emit_visual path picks them up. H2 adds shadow
    # to the allowlist; before v0.1.5 the template's `shadow` token
    # (e.g. `{shadow.card}`) silently dropped on the floor.
    parent_style = element.setdefault("style", {})
    for key in ("fill", "fg", "stroke", "radius", "shadow"):
        if key in style and key not in parent_style:
            parent_style[key] = style[key]


def _mode3_synthesise_children(
    comp_type: str,
    variant: str | None,
    props: dict[str, Any],
    elements: dict[str, dict[str, Any]],
    allocate_id,
    parent_element: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Produce synthetic child IR eids for a parent that has no LLM
    children, partitioned by slot position.

    Returns a dict keyed on slot ``position`` ("top", "bottom", "start",
    "end", "fill", or "_default" when unset). Each value is the list of
    synthesised eids for that position.

    Label-hoist contract (2026-04-21): positions "top" and "bottom" are
    EXTERNAL siblings of the parent (label above / helper below in an
    outer wrapper frame). Positions "fill", "start", "end", "_default"
    stay as INTERNAL children of the parent. The caller (``_build_element``)
    is responsible for wrapping when external children are present.

    Walks the resolved ``PresentationTemplate``'s slot grammar; for
    each text-typed slot with a matching prop in ``props`` (directly by
    slot name or via the ``_TEXT_SLOT_PROP_ALIASES`` fallbacks), allocates
    a text-child IR element and routes it into the position bucket.

    Historically this also applied the template to the parent element
    — that merge is now factored out into
    :func:`_apply_template_to_parent` and called unconditionally by
    ``_build_element`` (H1). The ``parent_element`` kwarg is retained
    for API compat but no longer applies template layout/style.
    """
    by_position: dict[str, list[str]] = {}
    registry = _default_provider_registry()
    template, _errors = registry.resolve(comp_type, variant, {})
    if template is None:
        return by_position

    if not template.slots:
        return by_position

    consumed_props: set[str] = set()

    for slot_name, slot_spec in template.slots.items():
        if not _slot_accepts_text(slot_spec):
            continue

        slot_position = getattr(slot_spec, "position", None) or "_default"

        value: str | None = None
        if slot_name in props and slot_name not in consumed_props and props[slot_name]:
            value = str(props[slot_name])
            consumed_props.add(slot_name)
        else:
            for alias in _TEXT_SLOT_PROP_ALIASES:
                if alias in consumed_props:
                    continue
                # Positional aliases (placeholder, helper) refuse to fill
                # slots at incompatible positions — otherwise
                # `{placeholder: "Search..."}` with no label would land the
                # placeholder in the label slot (position=top) because it's
                # first in declaration order. Surfaced 2026-04-21 by SoM.
                whitelist = _ALIAS_POSITION_WHITELIST.get(alias)
                if whitelist is not None and slot_position not in whitelist:
                    continue
                if alias in props and props[alias]:
                    value = str(props[alias])
                    consumed_props.add(alias)
                    break

        if not value:
            continue

        # Inherit typography from the parent template's style.typography.
        # The renderer's _emit_text_props consumes style.fontFamily /
        # fontSize / fontWeight directly — split the dict now to match.
        child_style: dict[str, Any] = {}
        typography = (template.style or {}).get("typography") or {}
        if isinstance(typography, dict):
            for key in ("fontFamily", "fontSize", "fontWeight"):
                if typography.get(key) is not None:
                    child_style[key] = typography[key]

        # Label-ish slots inherit the parent's `fg` color ref. Text-node
        # color in Figma is expressed as a `fills` paint, so we stash the
        # ref under `style.fill` — the renderer's Mode-3 IR-style overlay
        # synthesises a SOLID fill from it.
        fg_ref = (template.style or {}).get("fg")
        if fg_ref and slot_name in ("label", "headline", "title", "text"):
            child_style.setdefault("fill", fg_ref)

        child_eid = allocate_id("text")
        position = getattr(slot_spec, "position", None) or "_default"
        child: dict[str, Any] = {
            "type": "text",
            "props": {"text": str(value)},
            "layout": {"direction": "vertical"},
            "_synthesised_from": {
                "parent_type": comp_type,
                "parent_variant": variant,
                "slot": slot_name,
                "position": position,
                "provider": template.provider,
            },
        }
        if child_style:
            child["style"] = child_style
        elements[child_eid] = child
        by_position.setdefault(position, []).append(child_eid)

    return by_position


def _slot_accepts_text(slot_spec) -> bool:
    """Return True if a :class:`SlotSpec` accepts text-typed children."""
    allowed = getattr(slot_spec, "allowed", None) or []
    return any(a in allowed for a in ("text", "heading", "any"))


def _build_layout_from_template(
    comp_type: str,
    templates: dict[str, list[dict[str, Any]]] | None = None,
    variant: str | None = None,
) -> dict[str, Any]:
    """Build layout dict from template defaults for a component type."""
    layout: dict[str, Any] = {}

    if not templates or comp_type not in templates:
        layout["direction"] = "vertical"
        return layout

    tmpl = _pick_best_template(templates.get(comp_type), variant=variant)
    if not tmpl:
        layout["direction"] = "vertical"
        return layout

    direction = _DIRECTION_MAP.get(tmpl.get("layout_mode") or "", "stacked")
    layout["direction"] = direction

    sizing_h = tmpl.get("layout_sizing_h")
    sizing_v = tmpl.get("layout_sizing_v")
    width = tmpl.get("width")
    height = tmpl.get("height")
    sizing: dict[str, Any] = {}

    if sizing_h and sizing_h in _SIZING_MAP:
        sizing["width"] = _SIZING_MAP[sizing_h].lower()
    elif width is not None:
        sizing["width"] = width

    if sizing_v and sizing_v in _SIZING_MAP:
        sizing["height"] = _SIZING_MAP[sizing_v].lower()
    elif height is not None:
        sizing["height"] = height

    if width is not None:
        sizing["widthPixels"] = width
    if height is not None:
        sizing["heightPixels"] = height

    if sizing:
        layout["sizing"] = sizing

    gap = tmpl.get("item_spacing")
    if gap and gap > 0:
        layout["gap"] = gap

    padding: dict[str, float] = {}
    for side in ("top", "right", "bottom", "left"):
        val = tmpl.get(f"padding_{side}")
        if val and val > 0:
            padding[side] = val
    if padding:
        layout["padding"] = padding

    return layout


def _extract_bound_variables(
    raw_json: str | None,
    property_prefix: str,
) -> list[dict[str, str]]:
    """Extract boundVariables from raw Figma JSON fills/strokes.

    Returns a list of binding dicts with 'property' and 'variable_id'
    suitable for the rebind pipeline.
    """
    if not raw_json:
        return []
    try:
        items = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return []

    bindings: list[dict[str, str]] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        bound_vars = item.get("boundVariables", {})
        for prop_name, var_ref in bound_vars.items():
            if isinstance(var_ref, dict) and var_ref.get("id"):
                bindings.append({
                    "property": f"{property_prefix}.{i}.{prop_name}",
                    "variable_id": var_ref["id"],
                })
    return bindings


def build_template_visuals(
    spec: dict[str, Any],
    templates: dict[str, list[dict[str, Any]]],
    conn: sqlite3.Connection | None = None,
) -> dict[int, dict[str, Any]]:
    """Map spec elements to template visual data.

    Assigns synthetic negative node IDs to each element and builds a
    db_visuals-compatible dict from template visual defaults. Mutates
    spec to add _node_id_map. Extracts boundVariables from template
    fills/strokes for token rebinding.

    ADR-008 Mode-3: when an element carries an IR-level `component_key`
    (emitted by the LLM from the CKR vocabulary), look up its Figma
    node id in `component_key_registry` so the renderer's Mode-1
    path can call ``getNodeByIdAsync(figma_node_id).createInstance()``.
    A ``conn`` must be supplied to enable this lookup; tests without a
    DB connection get the pre-ADR-008 behaviour (component_key is set
    but component_figma_id stays None, so Mode-1 falls through to
    a placeholder).
    """
    ckr_by_name: dict[str, str] = {}
    if conn is not None:
        try:
            ckr_rows = conn.execute(
                "SELECT name, figma_node_id FROM component_key_registry"
            ).fetchall()
            ckr_by_name = {row[0]: row[1] for row in ckr_rows if row[0] and row[1]}
        except sqlite3.OperationalError:
            ckr_by_name = {}

    node_id_map: dict[str, int] = {}
    visuals: dict[int, dict[str, Any]] = {}

    for idx, (eid, element) in enumerate(spec["elements"].items()):
        synthetic_nid = -(idx + 1)
        node_id_map[eid] = synthetic_nid

        comp_type = _semantic_type(element)
        variant = element.get("variant")
        tmpl_list = templates.get(comp_type)
        tmpl = _pick_best_template(tmpl_list, variant=variant)

        bindings: list[dict[str, str]] = []
        if tmpl:
            bindings.extend(_extract_bound_variables(tmpl.get("fills"), "fill"))
            bindings.extend(_extract_bound_variables(tmpl.get("strokes"), "stroke"))

        children_composition = tmpl.get("children_composition", []) if tmpl else []
        if children_composition:
            element["_composition"] = children_composition

        font_data: dict[str, Any] = {}
        if tmpl:
            for fk in ("font_family", "font_size", "font_weight", "font_style",
                        "line_height", "letter_spacing", "text_align"):
                val = tmpl.get(fk)
                if val is not None:
                    font_data[fk] = val

        # Resolve Mode-1 identity with the IR element taking precedence
        # over the old component_templates row when both are present.
        ir_component_key = element.get("component_key")
        resolved_component_key = ir_component_key or (tmpl.get("component_key") if tmpl else None)
        resolved_component_figma_id = tmpl.get("component_figma_id") if tmpl else None
        if ir_component_key and ir_component_key in ckr_by_name:
            resolved_component_figma_id = ckr_by_name[ir_component_key]

        # v0.2 retrieval: when compose spliced a real DB subtree into
        # this element (via CorpusRetrievalProvider), element["visual"]
        # carries DB-native fills/strokes/effects/corner_radius/etc.
        # Prefer those over template lookup so the renderer paints with
        # real round-trip visuals instead of token refs.
        corpus_visual = element.get("visual") if isinstance(element, dict) else None
        if corpus_visual:
            visual_entry = {
                "fills": corpus_visual.get("fills"),
                "strokes": corpus_visual.get("strokes"),
                "effects": corpus_visual.get("effects"),
                "corner_radius": corpus_visual.get("corner_radius"),
                "opacity": corpus_visual.get("opacity"),
                "stroke_weight": corpus_visual.get("stroke_weight"),
                "component_key": resolved_component_key,
                "component_figma_id": resolved_component_figma_id,
                "bindings": bindings,
            }
        else:
            visual_entry = {
                "fills": tmpl.get("fills") if tmpl else None,
                "strokes": tmpl.get("strokes") if tmpl else None,
                "effects": tmpl.get("effects") if tmpl else None,
                "corner_radius": tmpl.get("corner_radius") if tmpl else None,
                "opacity": tmpl.get("opacity") if tmpl else None,
                "stroke_weight": None,
                "component_key": resolved_component_key,
                "component_figma_id": resolved_component_figma_id,
                "bindings": bindings,
            }
        if font_data:
            visual_entry["font"] = font_data

        visuals[synthetic_nid] = visual_entry

    spec["_node_id_map"] = node_id_map
    return visuals


def collect_template_rebind_entries(
    spec: dict[str, Any],
    visuals: dict[int, dict[str, Any]],
) -> list[dict[str, str]]:
    """Collect variable rebind entries from template boundVariables.

    Returns entries with element_id, property, and variable_id that can
    be used with build_rebind_entries after Figma execution provides the
    M dict (element_id → figma_node_id).
    """
    node_id_map = spec.get("_node_id_map", {})
    eid_by_nid = {nid: eid for eid, nid in node_id_map.items()}

    entries: list[dict[str, str]] = []
    for nid, visual in visuals.items():
        eid = eid_by_nid.get(nid)
        if not eid:
            continue
        for binding in visual.get("bindings", []):
            entries.append({
                "element_id": eid,
                "property": binding["property"],
                "variable_id": binding["variable_id"],
            })
    return entries


def compare_generated_vs_ground_truth(
    conn: sqlite3.Connection,
    spec: dict[str, Any],
    reference_screen_id: int,
) -> dict[str, Any]:
    """Compare a generated CompositionSpec against a real screen in the DB.

    Returns a structured report with:
      generated: element_count, type_distribution
      reference: element_count, type_distribution, mode1_count, mode2_count
      diff: missing_types, extra_types, element_count_delta
    """
    elements = spec.get("elements", {})
    gen_types: dict[str, int] = {}
    for element in elements.values():
        etype = _semantic_type(element)
        if etype == "screen":
            continue
        gen_types[etype] = gen_types.get(etype, 0) + 1

    ref_rows = conn.execute(
        "SELECT sci.canonical_type, "
        "CASE WHEN n.component_key IS NOT NULL THEN 1 ELSE 0 END AS is_keyed "
        "FROM screen_component_instances sci "
        "JOIN nodes n ON sci.node_id = n.id "
        "WHERE sci.screen_id = ?",
        (reference_screen_id,),
    ).fetchall()

    ref_types: dict[str, int] = {}
    mode1_count = 0
    mode2_count = 0
    for row in ref_rows:
        ctype = row[0]
        is_keyed = row[1]
        ref_types[ctype] = ref_types.get(ctype, 0) + 1
        if is_keyed:
            mode1_count += 1
        else:
            mode2_count += 1

    all_types = set(gen_types.keys()) | set(ref_types.keys())
    missing = sorted(t for t in all_types if t in ref_types and t not in gen_types)
    extra = sorted(t for t in all_types if t in gen_types and t not in ref_types)

    gen_element_count = len(elements)
    ref_element_count = len(ref_rows)

    return {
        "generated": {
            "element_count": gen_element_count,
            "type_distribution": dict(gen_types),
        },
        "reference": {
            "element_count": ref_element_count,
            "type_distribution": dict(ref_types),
            "mode1_count": mode1_count,
            "mode2_count": mode2_count,
        },
        "diff": {
            "element_count_delta": gen_element_count - ref_element_count,
            "missing_types": missing,
            "extra_types": extra,
        },
    }


# Composed alias patterns: unsupported types → container with label + control.
# Each entry defines the container direction and child elements.
# "from_prop" means the child gets its text from the parent component's prop.
_COMPOSED_ALIASES: dict[str, dict[str, Any]] = {
    "toggle": {
        "direction": "horizontal",
        "children": [
            {"type": "text", "from_prop": "text"},
            {"type": "icon", "variant": "icon/switch"},
        ],
    },
    "checkbox": {
        "direction": "horizontal",
        "children": [
            {"type": "icon", "variant": "icon/checkbox-empty"},
            {"type": "text", "from_prop": "text"},
        ],
    },
    "radio": {
        "direction": "horizontal",
        "children": [
            {"type": "icon", "variant": "icon/checkbox-empty"},
            {"type": "text", "from_prop": "text"},
        ],
    },
    "radio_group": {
        "direction": "horizontal",
        "children": [
            {"type": "icon", "variant": "icon/checkbox-empty"},
            {"type": "text", "from_prop": "text"},
        ],
    },
    "toggle_group": {
        "direction": "horizontal",
        "children": [
            {"type": "text", "from_prop": "text"},
            {"type": "icon", "variant": "icon/switch"},
        ],
    },
}

# Simple alias mapping for types that map 1:1 (no container wrapping needed).
_SIMPLE_ALIASES: dict[str, tuple[str, str]] = {
    "navigation_row": ("button", "button/large/translucent"),
    "icon_button": ("button", "button/small/translucent"),
    "select": ("button", "button/small/solid"),
    "segmented_control": ("tabs", "nav/tabs"),
}


def resolve_type_aliases(
    components: list[dict[str, Any]],
    templates: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Resolve unsupported component types via composed patterns or simple aliases.

    Composed aliases (toggle, checkbox, radio) expand into a container with
    label text + icon children. Simple aliases (segmented_control, icon_button)
    remap to an existing type + variant.

    Mutates nothing — returns a new list. Recurses into children.
    """
    available_types = set(templates.keys())

    def _resolve(comp: dict[str, Any]) -> dict[str, Any]:
        comp_type = _semantic_type(comp)
        resolved = dict(comp)

        if comp_type not in available_types:
            if comp_type in _COMPOSED_ALIASES and not comp.get("variant"):
                pattern = _COMPOSED_ALIASES[comp_type]
                icon_type = next(
                    (c["type"] for c in pattern["children"] if c["type"] != "text"),
                    None,
                )
                if icon_type and icon_type in available_types:
                    props = comp.get("props", {})
                    children: list[dict[str, Any]] = []
                    for child_spec in pattern["children"]:
                        child: dict[str, Any] = {"type": child_spec["type"]}
                        if child_spec.get("variant"):
                            child["variant"] = child_spec["variant"]
                        if child_spec.get("from_prop"):
                            prop_val = props.get(child_spec["from_prop"])
                            if prop_val:
                                child["props"] = {"text": prop_val}
                        children.append(child)

                    resolved = {
                        "type": "container",
                        "layout_direction": pattern["direction"],
                        "layout_sizing": {"width": "fill", "height": "hug"},
                        "children": children,
                    }
                    return resolved

            if comp_type in _SIMPLE_ALIASES:
                target_type, target_variant = _SIMPLE_ALIASES[comp_type]
                if target_type in available_types:
                    resolved["type"] = target_type
                    if not comp.get("variant"):
                        resolved["variant"] = target_variant

        children = comp.get("children", [])
        if children:
            resolved["children"] = [_resolve(child) for child in children]

        return resolved

    return [_resolve(comp) for comp in components]


# Types that resolve Mode-1 to INSTANCE and therefore can't host
# children in the Figma Plugin API (F4 from
# `docs/learnings-tier-b-failure-modes.md`). A child under one of
# these produces an `appendChild: Cannot move node` throw in Phase
# 2 of the render script (F2 — cascading).
#
# TODO(Tier E.3): derive from component_type_catalog.resolution_mode
# instead of hardcoding; see note in dd/fidelity_score.py
# LEAF_TYPES.
_LEAF_TYPES_FOR_HOIST: frozenset[str] = frozenset({
    "button", "icon_button", "icon", "chip",
    "switch", "toggle", "checkbox", "radio",
    "link", "badge",
    "text", "heading",      # already leaves in the renderer
    "avatar",
})

# Prop slot names we hoist children's text into, keyed on the
# parent LEAF type. `text` is the universal slot; some parents
# might use a different slot in the future.
_HOIST_TEXT_PROP = "text"


def _hoist_children_into_props(
    comp: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Recursively hoist text content out of children of LEAF-typed
    parents into ``props.text``.

    Tier D.3 F4 fix. When the LLM emits ``{type: button, children:
    [{type: text, props: {text: "Sign in"}}]}``, we rewrite to
    ``{type: button, props: {text: "Sign in"}, children: []}``
    before compose+render. Otherwise Phase 2 emits
    ``instance.appendChild(text_node)`` which Figma rejects.

    Returns ``(hoisted_comp, n_hoists_applied)``. The count is for
    diagnostics + metrics; 0 means no change.
    """
    hoisted_count = 0
    ctype = comp.get("type") or ""
    children = comp.get("children") or []

    if ctype in _LEAF_TYPES_FOR_HOIST and children:
        props = dict(comp.get("props") or {})
        # Find the first text-bearing child and pull its text.
        for child in children:
            if _HOIST_TEXT_PROP in props:
                break
            ch_props = child.get("props") or {}
            if child.get("type") in ("text", "heading", "link"):
                t = ch_props.get("text") or ""
                if t:
                    props[_HOIST_TEXT_PROP] = t
                    break
        # Drop children entirely — the leaf type can't host them.
        new_comp = dict(comp)
        new_comp["children"] = []
        if props:
            new_comp["props"] = props
        hoisted_count += 1
        return new_comp, hoisted_count

    # Recurse into non-leaf parents' children.
    if children:
        new_children: list[dict[str, Any]] = []
        total = 0
        for child in children:
            hoisted_child, n = _hoist_children_into_props(child)
            new_children.append(hoisted_child)
            total += n
        if total:
            new_comp = dict(comp)
            new_comp["children"] = new_children
            hoisted_count += total
            return new_comp, hoisted_count

    return comp, 0


def validate_components(
    components: list[dict[str, Any]],
    templates: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate LLM-output components against available templates.

    Resolves type aliases first, runs the F4 hoist pass (leaf-type
    parents lose their children; first text-bearing child's text is
    hoisted into ``props.text``), then checks remaining unsupported
    types. Returns (components, warnings).
    """
    resolved = resolve_type_aliases(components, templates)

    # Tier D.3 F4: hoist children from leaf-type parents. Must run
    # BEFORE the template-availability check so hoisted components
    # don't get flagged for types they no longer reference.
    hoisted: list[dict[str, Any]] = []
    total_hoists = 0
    for comp in resolved:
        new_comp, n = _hoist_children_into_props(comp)
        hoisted.append(new_comp)
        total_hoists += n

    available_types = set(templates.keys())
    warnings: list[str] = []

    def _check(comp: dict[str, Any]) -> None:
        comp_type = _semantic_type(comp)
        if comp_type and comp_type not in available_types:
            warnings.append(
                f"Type '{comp_type}' has no template in this project — will render as empty frame"
            )
        for child in comp.get("children", []):
            _check(child)

    for comp in hoisted:
        _check(comp)

    if total_hoists:
        warnings.append(
            f"Hoisted {total_hoists} leaf-type-parent child subtree(s) "
            f"into `props.text` (F4 — leaf types can't host children)."
        )

    return hoisted, warnings


def generate_from_prompt(
    conn: sqlite3.Connection,
    components: list[dict[str, Any]],
    page_name: str | None = None,
    registry: Any | None = None,
) -> dict[str, Any]:
    """Generate Figma JS from a component list using templates.

    Orchestrates: query_templates → validate → compose_screen →
    build_template_visuals → compress_to_l3 → render_figma (markup-
    native Option B path; see docs/decisions/v0.3-option-b-cutover.md).
    Returns dict with structure_script and metadata. When page_name is
    provided, the script creates a new Figma page.

    ``registry`` is an optional :class:`ProviderRegistry` for Mode-3
    composition — pass one from callers that have a DB connection
    (e.g. prompt_to_figma) to enable corpus-subtree retrieval via
    :class:`CorpusRetrievalProvider`. When None, compose_screen uses
    its internal default registry (universal catalog only).
    """
    templates = query_templates(conn)
    components, warnings = validate_components(components, templates)
    # When no registry passed, build the default Mode-3 cascade here so
    # direct callers (experiments/00g run_parse_compose, tests) share
    # the same provider stack as prompt_to_figma. Corpus retrieval
    # remains flag-gated inside the provider itself.
    effective_registry = registry if registry is not None else _build_default_mode3_registry(conn)
    spec = compose_screen(components, templates=templates, registry=effective_registry)
    # Pass conn through so build_template_visuals can resolve IR-level
    # component_key refs against component_key_registry (ADR-008 Mode-3).
    visuals = build_template_visuals(spec, templates, conn=conn)

    # CKR gate for the Option B preamble — mirrors
    # `dd.renderers.figma.generate_screen`. When CKR isn't built, the
    # walker emits a structured `CKR_NOT_BUILT` diagnostic so
    # downstream Mode-1 degradations trace back to the root cause
    # instead of appearing as mysterious placeholder wireframes.
    ckr_built = _ckr_is_built(conn)

    doc, _eid_nid, nid_map, spec_key_map, original_name_map = (
        compress_to_l3_with_maps(spec, conn, collapse_wrapper=False)
    )
    fonts = collect_fonts(spec, db_visuals=visuals)
    script, token_refs = render_figma(
        doc, conn, nid_map,
        fonts=fonts,
        spec_key_map=spec_key_map,
        original_name_map=original_name_map,
        db_visuals=visuals,
        ckr_built=ckr_built,
        page_name=page_name,
        _spec_elements=spec["elements"],
        _spec_tokens=spec.get("tokens", {}),
    )
    template_rebind_entries = collect_template_rebind_entries(spec, visuals)

    return {
        "structure_script": script,
        "token_refs": token_refs,
        "template_rebind_entries": template_rebind_entries,
        "element_count": len(spec["elements"]),
        "spec": spec,
        "warnings": warnings,
    }
