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
            "mainAxisAlignment": "CENTER",
            "crossAxisAlignment": "CENTER",
        },
        slots={
            "icon": SlotSpec(allowed=["icon"], required=False, position="start"),
            "label": SlotSpec(allowed=["text"], required=True, position="fill"),
        },
        style={
            "fill": fill,
            "fg": fg,
            "radius": "{radius.button}",
            "typography": {
                "fontFamily": "{typography.button.fontFamily}",
                "fontSize": "{typography.button.fontSize}",
                "fontWeight": "{typography.button.fontWeight}",
            },
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
            "padding": {"x": "{space.input.padding_x}", "y": "{space.input.padding_y}"},
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
            "typography": {
                "fontFamily": "{typography.input.fontFamily}",
                "fontSize": "{typography.input.fontSize}",
                "fontWeight": "{typography.input.fontWeight}",
            },
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
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.body.fontSize}",
                "fontWeight": "{typography.body.fontWeight}",
            },
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
            "crossAxisAlignment": "CENTER",
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
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.body.fontSize}",
                "fontWeight": "{typography.body.fontWeight}",
            },
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
            "crossAxisAlignment": "CENTER",
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
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.body.fontSize}",
                "fontWeight": "{typography.body.fontWeight}",
            },
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
            "crossAxisAlignment": "CENTER",
            "mainAxisAlignment": "CENTER",
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
            "crossAxisAlignment": "CENTER",
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
            "typography": {
                "fontFamily": "{typography.list_item.fontFamily}",
                "fontSize": "{typography.list_item.fontSize}",
                "fontWeight": "{typography.list_item.fontWeight}",
            },
        },
    )


def _header_template(variant: str | None) -> PresentationTemplate:
    """iOS/Android-style top app bar: leading icon button + title + trailing actions."""
    return PresentationTemplate(
        catalog_type="header",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "fill", "height": "fixed"},
            "padding": {"x": "{space.header.padding_x}", "y": "{space.header.padding_y}"},
            "gap": "{space.header.gap}",
            "align": "center",
            "crossAxisAlignment": "CENTER",
            "mainAxisAlignment": "SPACE_BETWEEN",
        },
        slots={
            "leading": SlotSpec(allowed=["icon_button", "icon"], required=False, position="start"),
            "title": SlotSpec(allowed=["text", "heading"], required=False, position="content"),
            "trailing": SlotSpec(allowed=["icon_button", "avatar", "button", "icon"], required=False, position="end", quantity="multiple"),
        },
        style={
            "fill": "{color.surface.header}",
            "stroke": "{color.surface.header_border}",
            "fg": "{color.text.heading}",
            "typography": {
                "fontFamily": "{typography.heading.fontFamily}",
                "fontSize": "{typography.header.fontSize}",
                "fontWeight": "{typography.header.fontWeight}",
            },
            "height_pixels": 56,
        },
    )


def _drawer_template(variant: str | None) -> PresentationTemplate:
    """Side drawer: header + vertical nav menu + footer.

    Width is FILL by default (mobile-first: drawer IS the screen when
    opened on small form factors). Desktop fixed-width side-panel
    usage can pass ``variant="side-panel"`` in v0.2 to get a pinned
    280-wide shape; v0.1 ships with FILL to match the 00e → 00f
    "drawer + 6 nav items" LLM prompt shape.
    """
    return PresentationTemplate(
        catalog_type="drawer",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "vertical",
            "sizing": {"width": "fill", "height": "fill"},
            "padding": {"x": "{space.drawer.padding_x}", "y": "{space.drawer.padding_y}"},
            "gap": "{space.drawer.gap}",
        },
        slots={
            "header": SlotSpec(allowed=["heading", "avatar", "text"], required=False, position="top"),
            "menu": SlotSpec(allowed=["navigation_row", "list_item"], required=True, position="fill", quantity="multiple"),
            "footer": SlotSpec(allowed=["text", "button"], required=False, position="bottom"),
        },
        style={
            "fill": "{color.surface.drawer}",
            "stroke": "{color.surface.drawer_border}",
            "fg": "{color.text.default}",
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.body.fontSize}",
                "fontWeight": "{typography.body.fontWeight}",
            },
        },
    )


def _navigation_row_template(variant: str | None) -> PresentationTemplate:
    """Tappable row: leading icon + label + trailing chevron/badge/text."""
    return PresentationTemplate(
        catalog_type="navigation_row",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "fill", "height": "hug"},
            "padding": {"x": "{space.list_item.padding_x}", "y": "{space.list_item.padding_y}"},
            "gap": "{space.list_item.gap}",
            "align": "center",
            "crossAxisAlignment": "CENTER",
            "mainAxisAlignment": "SPACE_BETWEEN",
        },
        slots={
            "icon": SlotSpec(allowed=["icon"], required=False, position="start"),
            "label": SlotSpec(allowed=["text"], required=True, position="content"),
            "trailing": SlotSpec(allowed=["icon", "badge", "text"], required=False, position="end"),
        },
        style={
            "fill": "{color.surface.list_item}",
            "fg": "{color.text.default}",
            "typography": {
                "fontFamily": "{typography.list_item.fontFamily}",
                "fontSize": "{typography.list_item.fontSize}",
                "fontWeight": "{typography.list_item.fontWeight}",
            },
            "height_pixels": 48,
        },
    )


def _avatar_template(variant: str | None) -> PresentationTemplate:
    """Circular image container with fallback initials."""
    return PresentationTemplate(
        catalog_type="avatar",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "fixed", "height": "fixed"},
            "align": "center",
            "crossAxisAlignment": "CENTER",
            "mainAxisAlignment": "CENTER",
            "width_pixels": 40,
            "height_pixels": 40,
        },
        slots={
            "fallback": SlotSpec(allowed=["text", "icon"], required=False, position="fill"),
        },
        style={
            "fill": "{color.avatar.fill}",
            "fg": "{color.avatar.fg}",
            "radius": 999,
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.avatar.fontSize}",
                "fontWeight": "{typography.avatar.fontWeight}",
            },
        },
    )


def _badge_template(variant: str | None) -> PresentationTemplate:
    """Small pill with icon + label."""
    tone = (variant or "default").lower()
    fill = {
        "destructive": "{color.action.destructive.bg}",
        "success": "{color.status.success.bg}",
        "warning": "{color.status.warning.bg}",
        "info": "{color.status.info.bg}",
    }.get(tone, "{color.surface.badge}")
    fg = {
        "destructive": "{color.action.destructive.fg}",
        "success": "{color.status.success.fg}",
        "warning": "{color.status.warning.fg}",
        "info": "{color.status.info.fg}",
    }.get(tone, "{color.text.default}")
    return PresentationTemplate(
        catalog_type="badge",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "hug", "height": "hug"},
            "padding": {"x": "{space.badge.padding_x}", "y": "{space.badge.padding_y}"},
            "gap": "{space.badge.gap}",
            "align": "center",
            "crossAxisAlignment": "CENTER",
        },
        slots={
            "icon": SlotSpec(allowed=["icon"], required=False, position="start"),
            "label": SlotSpec(allowed=["text"], required=True, position="fill"),
        },
        style={
            "fill": fill,
            "fg": fg,
            "radius": "{radius.badge}",
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.badge.fontSize}",
                "fontWeight": "{typography.badge.fontWeight}",
            },
        },
    )


def _image_template(variant: str | None) -> PresentationTemplate:
    """Placeholder frame with a neutral tint; real image content comes from props.src."""
    return PresentationTemplate(
        catalog_type="image",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "fill", "height": "fixed"},
            "height_pixels": 160,
        },
        slots={},
        style={
            "fill": "{color.surface.image_placeholder}",
            "radius": "{radius.image}",
        },
    )


def _icon_template(variant: str | None) -> PresentationTemplate:
    """Small square shape — the Mode-1 instance path populates real glyphs."""
    return PresentationTemplate(
        catalog_type="icon",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "fixed", "height": "fixed"},
            "width_pixels": 20,
            "height_pixels": 20,
        },
        slots={},
        style={
            "fill": "{color.text.default}",
            "radius": 4,
        },
    )


def _menu_template(variant: str | None) -> PresentationTemplate:
    """Vertical list of items under a trigger — v0.1 ships only the panel shape."""
    return PresentationTemplate(
        catalog_type="menu",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "vertical",
            "sizing": {"width": "fixed", "height": "hug"},
            "padding": {"x": "{space.menu.padding_x}", "y": "{space.menu.padding_y}"},
            "gap": "{space.menu.gap}",
            "width_pixels": 220,
        },
        slots={
            "items": SlotSpec(allowed=["text", "icon", "list_item"], required=True, position="fill", quantity="multiple"),
        },
        style={
            "fill": "{color.surface.menu}",
            "stroke": "{color.surface.menu_border}",
            "radius": "{radius.menu}",
            "shadow": "{shadow.menu}",
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.body.fontSize}",
                "fontWeight": "{typography.body.fontWeight}",
            },
        },
    )


def _tooltip_template(variant: str | None) -> PresentationTemplate:
    """Small dark hint label."""
    return PresentationTemplate(
        catalog_type="tooltip",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "hug", "height": "hug"},
            "padding": {"x": "{space.tooltip.padding_x}", "y": "{space.tooltip.padding_y}"},
            "align": "center",
            "crossAxisAlignment": "CENTER",
        },
        slots={
            "content": SlotSpec(allowed=["text"], required=True, position="fill"),
        },
        style={
            "fill": "{color.surface.tooltip}",
            "fg": "{color.text.on_tooltip}",
            "radius": "{radius.tooltip}",
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.caption.fontSize}",
                "fontWeight": "{typography.caption.fontWeight}",
            },
        },
    )


def _popover_template(variant: str | None) -> PresentationTemplate:
    """Floating panel anchored to a trigger."""
    return PresentationTemplate(
        catalog_type="popover",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "vertical",
            "sizing": {"width": "fixed", "height": "hug"},
            "padding": {"x": "{space.popover.padding_x}", "y": "{space.popover.padding_y}"},
            "gap": "{space.popover.gap}",
            "width_pixels": 280,
        },
        slots={
            "content": SlotSpec(allowed=["any"], required=True, position="fill"),
        },
        style={
            "fill": "{color.surface.popover}",
            "stroke": "{color.surface.popover_border}",
            "radius": "{radius.popover}",
            "shadow": "{shadow.popover}",
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.body.fontSize}",
                "fontWeight": "{typography.body.fontWeight}",
            },
        },
    )


def _link_template(variant: str | None) -> PresentationTemplate:
    """Inline text styled as a link (no frame; passes through as text node)."""
    return PresentationTemplate(
        catalog_type="link",
        variant=variant,
        provider="catalog:universal",
        layout={
            "direction": "horizontal",
            "sizing": {"width": "hug", "height": "hug"},
            "align": "center",
            "crossAxisAlignment": "CENTER",
        },
        slots={
            "label": SlotSpec(allowed=["text"], required=True, position="fill"),
        },
        style={
            "fill": None,
            "fg": "{color.text.link}",
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.body.fontSize}",
                "fontWeight": "{typography.body.fontWeight}",
            },
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
            "crossAxisAlignment": "CENTER",
        },
        slots={
            "label": SlotSpec(allowed=["text", "icon"], required=False, position="fill"),
        },
        style={
            "fill": "{color.surface.default}",
            "radius": "{radius.default}",
            "typography": {
                "fontFamily": "{typography.body.fontFamily}",
                "fontSize": "{typography.body.fontSize}",
                "fontWeight": "{typography.body.fontWeight}",
            },
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
    # ADR-008 Part D: 11 backbone types that previously fell through to
    # the generic frame template, now dedicated.
    "header": _header_template,
    "drawer": _drawer_template,
    "navigation_row": _navigation_row_template,
    "avatar": _avatar_template,
    "badge": _badge_template,
    "image": _image_template,
    "icon": _icon_template,
    "menu": _menu_template,
    "tooltip": _tooltip_template,
    "popover": _popover_template,
    "link": _link_template,
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
