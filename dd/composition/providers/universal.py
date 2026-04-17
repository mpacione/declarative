"""Universal catalog provider (ADR-008) — priority 10, backend ``catalog:universal``.

Hand-authored presentation templates for the 22-type universal backbone
(button, text_input, card, dialog, toggle, etc.) informed by:

- **Structure**: Stream A's ontology survey consensus (``docs/research/component-taxonomy-survey.md``)
  + ``dd/catalog.py``'s ``slot_definitions``.
- **Sizing**: Exp I's per-type defaults (``experiments/I-sizing-defaults/defaults.yaml``).
- **Values**: shadcn's token defaults (MIT-licensed), ported via DTCG
  aliases into ``{color.*}`` / ``{radius.*}`` / ``{space.*}`` /
  ``{typography.*}`` refs.

All refs resolve through ``TokenCascade`` at Mode-3 resolution time —
the provider never emits literal hex/px on the happy path.

The templates cover the 22 universal types enumerated in Stream A.
Types beyond the backbone return ``None`` (falling through to the
ingested provider in the registry walk).
"""

from __future__ import annotations

from typing import Any, ClassVar

from dd.composition.protocol import (
    PresentationTemplate,
    SlotSpec,
)


# 22-type universal backbone (ADR-008 §10). Extended types fall through
# to ingested providers.
_BACKBONE: frozenset[str] = frozenset({
    "button", "icon_button", "text_input", "textarea", "checkbox",
    "radio", "toggle", "select", "combobox", "slider", "tabs", "card",
    "list", "list_item", "avatar", "badge", "icon", "dialog", "tooltip",
    "popover", "menu", "link",
})


def _button_template(variant: str | None) -> PresentationTemplate:
    """Frame+text button with variant-dependent fill and text color."""
    tone = (variant or "default").lower()
    fill = {
        "primary": "{color.action.primary.bg}",
        "secondary": "{color.action.secondary.bg}",
        "destructive": "{color.action.destructive.bg}",
        "ghost": None,
    }.get(tone, "{color.action.default.bg}")
    fg = {
        "primary": "{color.action.primary.fg}",
        "secondary": "{color.action.secondary.fg}",
        "destructive": "{color.action.destructive.fg}",
        "ghost": "{color.action.ghost.fg}",
    }.get(tone, "{color.action.default.fg}")

    return PresentationTemplate(
        catalog_type="button",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "hug", "height": "fixed"},
            "padding": {"x": "{space.button.padding_x}", "y": "{space.button.padding_y}"},
            "gap": "{space.button.gap}",
            "align": "center",
        },
        slots={
            "icon": SlotSpec(allowed=["icon"], required=False, position="start"),
            "label": SlotSpec(allowed=["text"], required=True, position="fill"),
        },
        style={
            "fill": fill,
            "fg": fg,
            "radius": "{radius.button}",
            "typography": "{typography.button.label}",
            "height_pixels": 44,
        },
    )


def _text_input_template(variant: str | None) -> PresentationTemplate:
    return PresentationTemplate(
        catalog_type="text_input",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "vertical",
            "sizing": {"width": "fill", "height": "hug"},
            "gap": "{space.input.gap}",
        },
        slots={
            "label": SlotSpec(allowed=["text"], required=False, position="top"),
            "leading": SlotSpec(allowed=["icon"], required=False, position="start"),
            "input": SlotSpec(allowed=["text"], required=True, position="fill"),
            "trailing": SlotSpec(allowed=["icon", "button", "icon_button"], required=False, position="end"),
            "helper": SlotSpec(allowed=["text"], required=False, position="bottom"),
        },
        style={
            "fill": "{color.input.bg}",
            "stroke": "{color.input.border}",
            "radius": "{radius.input}",
            "typography": "{typography.input.value}",
            "height_pixels": 48,
        },
    )


def _card_template(variant: str | None) -> PresentationTemplate:
    return PresentationTemplate(
        catalog_type="card",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "vertical",
            "sizing": {"width": "fill", "height": "hug"},
            "padding": {"x": "{space.card.padding_x}", "y": "{space.card.padding_y}"},
            "gap": "{space.card.gap}",
        },
        slots={
            "media": SlotSpec(allowed=["image", "video", "vector"], required=False, position="start"),
            "header": SlotSpec(allowed=["heading", "text"], required=False, position="start"),
            "title": SlotSpec(allowed=["heading", "text"], required=False, position="start"),
            "body": SlotSpec(allowed=["text", "any"], required=False, position="fill"),
            "actions": SlotSpec(allowed=["button", "button_group", "link"], required=False, position="end", quantity="multiple"),
        },
        style={
            "fill": "{color.surface.card}",
            "stroke": "{color.surface.card_border}",
            "radius": "{radius.card}",
            "shadow": "{shadow.card}",
        },
    )


def _dialog_template(variant: str | None) -> PresentationTemplate:
    return PresentationTemplate(
        catalog_type="dialog",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "vertical",
            "sizing": {"width": "fixed", "height": "hug"},
            "padding": {"x": "{space.dialog.padding_x}", "y": "{space.dialog.padding_y}"},
            "gap": "{space.dialog.gap}",
            "width_pixels": 400,
        },
        slots={
            "title": SlotSpec(allowed=["heading", "text"], required=False, position="top"),
            "body": SlotSpec(allowed=["text", "any"], required=True, position="fill"),
            "footer": SlotSpec(allowed=["button", "button_group"], required=False, position="bottom", quantity="multiple"),
        },
        style={
            "fill": "{color.surface.dialog}",
            "radius": "{radius.dialog}",
            "shadow": "{shadow.dialog}",
        },
    )


def _toggle_template(variant: str | None) -> PresentationTemplate:
    return PresentationTemplate(
        catalog_type="toggle",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "hug", "height": "hug"},
            "gap": "{space.toggle.gap}",
            "align": "center",
        },
        slots={
            "track": SlotSpec(allowed=[], required=True, position="start"),
            "thumb": SlotSpec(allowed=[], required=True, position="start"),
            "label": SlotSpec(allowed=["text"], required=False, position="end"),
        },
        style={
            "fill": "{color.toggle.track.off}",
            "thumb_fill": "{color.toggle.thumb}",
            "radius": "{radius.toggle}",
            "track_width_pixels": 44,
            "track_height_pixels": 26,
        },
    )


def _checkbox_template(variant: str | None) -> PresentationTemplate:
    return PresentationTemplate(
        catalog_type="checkbox",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "hug", "height": "hug"},
            "gap": "{space.checkbox.gap}",
            "align": "center",
        },
        slots={
            "indicator": SlotSpec(allowed=[], required=True, position="start"),
            "label": SlotSpec(allowed=["text"], required=False, position="end"),
        },
        style={
            "fill": "{color.checkbox.fill}",
            "stroke": "{color.checkbox.border}",
            "radius": "{radius.checkbox}",
            "size_pixels": 20,
        },
    )


def _icon_button_template(variant: str | None) -> PresentationTemplate:
    return PresentationTemplate(
        catalog_type="icon_button",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "fixed", "height": "fixed"},
            "align": "center",
            "padding": {"x": "{space.icon_button.padding}", "y": "{space.icon_button.padding}"},
            "width_pixels": 40,
            "height_pixels": 40,
        },
        slots={
            "icon": SlotSpec(allowed=["icon"], required=True, position="fill"),
        },
        style={
            "fill": "{color.action.ghost.bg}",
            "radius": "{radius.button}",
        },
    )


def _list_item_template(variant: str | None) -> PresentationTemplate:
    return PresentationTemplate(
        catalog_type="list_item",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "fill", "height": "hug"},
            "padding": {"x": "{space.list_item.padding_x}", "y": "{space.list_item.padding_y}"},
            "gap": "{space.list_item.gap}",
            "align": "center",
        },
        slots={
            "leading": SlotSpec(allowed=["icon", "avatar", "image"], required=False, position="start"),
            "overline": SlotSpec(allowed=["text"], required=False, position="content"),
            "headline": SlotSpec(allowed=["text", "heading"], required=True, position="content"),
            "supporting": SlotSpec(allowed=["text"], required=False, position="content"),
            "trailing_supporting": SlotSpec(allowed=["text"], required=False, position="end"),
            "trailing": SlotSpec(allowed=["icon", "badge", "text", "icon_button"], required=False, position="end"),
        },
        style={
            "fill": "{color.surface.list_item}",
        },
    )


def _generic_frame_template(
    catalog_type: str, variant: str | None,
) -> PresentationTemplate:
    """Fallback for backbone types without a dedicated template yet.

    v0.1 ships dedicated templates for the highest-value types (button,
    text_input, card, dialog, toggle, checkbox, icon_button, list_item).
    Other backbone types get a plausible default: a frame with a single
    text slot. Shadcn backfill in v0.2 promotes them to real structure.
    """
    return PresentationTemplate(
        catalog_type=catalog_type,
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "hug", "height": "hug"},
            "padding": {"x": "{space.generic.padding_x}", "y": "{space.generic.padding_y}"},
            "align": "center",
        },
        slots={
            "label": SlotSpec(allowed=["text", "icon"], required=False, position="fill"),
        },
        style={
            "fill": "{color.surface.default}",
            "radius": "{radius.default}",
        },
    )


_BUILDERS: dict[str, Any] = {
    "button": _button_template,
    "text_input": _text_input_template,
    "textarea": _text_input_template,
    "search_input": _text_input_template,
    "card": _card_template,
    "dialog": _dialog_template,
    "toggle": _toggle_template,
    "checkbox": _checkbox_template,
    "radio": _checkbox_template,
    "icon_button": _icon_button_template,
    "list_item": _list_item_template,
}


class UniversalCatalogProvider:
    """Hand-authored universal defaults; priority 10 (lowest before token-only)."""

    backend: ClassVar[str] = "catalog:universal"
    priority: ClassVar[int] = 10

    def supports(self, catalog_type: str, variant: str | None) -> bool:
        return catalog_type in _BACKBONE

    def resolve(
        self,
        catalog_type: str,
        variant: str | None,
        context: dict[str, Any],
    ) -> PresentationTemplate | None:
        builder = _BUILDERS.get(catalog_type)
        if builder is not None:
            return builder(variant)
        if catalog_type in _BACKBONE:
            return _generic_frame_template(catalog_type, variant)
        return None
