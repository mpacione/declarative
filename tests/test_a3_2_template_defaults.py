"""A3.2 — silent default leak fix in Mode 3 universal templates.

Forensic-audit-2 (audit/architectural-flow-matrix-20260426.md, Pattern A
"Silent default leaks") flagged that universal templates carry no
``opacity`` and no stroke-geometry props (``strokeWeight``,
``strokeAlign``, ``dashPattern``). Composed elements inherited Figma
factory defaults (e.g. ``opacity = 1.0``), so an LLM-driven override
that wanted a translucent button could not distinguish the template's
silence from "no opinion."

A3.2 is the surgical "stop the bleed" fix:

1. Universal templates carry ``opacity: 1.0`` on every builder
   (explicit "no transparency" signal).
2. Templates that declare a ``stroke`` ref also carry
   ``strokeWeight``, ``strokeAlign``, ``dashPattern``.
3. Templates without a stroke ref do NOT carry stroke geometry —
   geometry-without-paint is brittle and conflicts with Backlog #2
   (0-weight-with-strokes).
4. ``_apply_template_to_parent`` in ``dd/compose.py`` forwards the
   new props from ``template.style`` into ``element["visual"]`` so
   the property-registry emit path picks them up.

Codex 5.5 (gpt-5.5 high reasoning) consulted on the schema choice:
keep new props top-level in ``template.style`` (sibling to ``fill`` /
``stroke``); seed ``element["visual"]`` (not ``element["style"]``)
because the renderer's IR-style overlay only handles
fill / stroke / cornerRadius. Backlog #1 (provenance tagging)
remains the proper end-state fix.
"""

from __future__ import annotations

import pytest

from dd.compose import compose_screen
from dd.composition.providers.universal import (
    UNIVERSAL_COMPONENT_TYPES,
    UniversalCatalogProvider,
)


# ---------------------------------------------------------------------------
# Template-level invariants — what the builders themselves carry
# ---------------------------------------------------------------------------


class TestTemplateOpacityDefault:
    """Every universal template's ``style`` carries an explicit
    ``opacity: 1.0``.

    Pre-A3.2 the templates were silent; post-A3.2 each builder makes
    the "normal opacity" intent explicit so a downstream LLM override
    has a concrete value to differ against.
    """

    @pytest.fixture
    def provider(self) -> UniversalCatalogProvider:
        return UniversalCatalogProvider()

    @pytest.mark.parametrize("catalog_type", sorted(UNIVERSAL_COMPONENT_TYPES))
    def test_every_universal_template_carries_opacity_one(
        self, provider: UniversalCatalogProvider, catalog_type: str,
    ) -> None:
        template = provider.resolve(catalog_type, None, {})
        assert template is not None, (
            f"resolve({catalog_type!r}) returned None — backbone "
            f"contract broken"
        )
        assert template.style.get("opacity") == 1.0, (
            f"{catalog_type} template must carry opacity=1.0 explicitly"
            f" (Pattern A silent-default-leak fix); got "
            f"{template.style.get('opacity')!r}"
        )

    def test_link_template_carries_opacity_despite_no_fill(
        self, provider: UniversalCatalogProvider,
    ) -> None:
        """``_link_template`` deliberately has ``fill: None`` (link is
        text-only, no surface). It must STILL carry ``opacity: 1.0``
        — opacity is independent of paint and always safe to assert.
        """
        template = provider.resolve("link", None, {})
        assert template is not None
        assert template.style.get("fill") is None, (
            "link template's no-fill contract changed; reassess "
            "whether opacity default still applies"
        )
        assert template.style.get("opacity") == 1.0


class TestTemplateStrokeGeometry:
    """Stroke geometry (``strokeWeight``, ``strokeAlign``,
    ``dashPattern``) is carried only on templates that declare a
    ``stroke`` ref.

    Codex 5.5: "Do not use strokeWeight: 0 to mean 'no stroke.' That
    encodes absence through geometry, which is brittle and can
    collide with the separate 0-weight-with-strokes backlog."
    """

    @pytest.fixture
    def provider(self) -> UniversalCatalogProvider:
        return UniversalCatalogProvider()

    @pytest.mark.parametrize(
        "catalog_type",
        [
            "card", "text_input", "textarea", "search_input",
            "header", "drawer", "menu", "popover",
            "checkbox", "radio",
        ],
    )
    def test_stroked_templates_carry_full_stroke_geometry(
        self, provider: UniversalCatalogProvider, catalog_type: str,
    ) -> None:
        template = provider.resolve(catalog_type, None, {})
        assert template is not None
        assert template.style.get("stroke") is not None, (
            f"{catalog_type} no longer carries a stroke ref; this "
            f"test's premise has changed"
        )
        assert template.style.get("strokeWeight") == 1.0, (
            f"{catalog_type} carries a stroke ref but no strokeWeight"
        )
        assert template.style.get("strokeAlign") == "INSIDE", (
            f"{catalog_type} carries a stroke ref but no strokeAlign"
        )
        assert template.style.get("dashPattern") == [], (
            f"{catalog_type} carries a stroke ref but no dashPattern"
        )

    def test_stroke_align_uses_inside(
        self, provider: UniversalCatalogProvider,
    ) -> None:
        """INSIDE keeps the stroke contained within the bounding box,
        which preserves the layout dimensions when token resolution
        provides a non-zero stroke. CENTER would extend by
        strokeWeight/2; OUTSIDE by strokeWeight."""
        template = provider.resolve("card", None, {})
        assert template is not None
        assert template.style.get("strokeAlign") == "INSIDE"

    @pytest.mark.parametrize(
        "catalog_type",
        ["icon_button", "list_item", "avatar", "image", "icon", "tooltip", "link"],
    )
    def test_unstroked_templates_omit_stroke_geometry(
        self, provider: UniversalCatalogProvider, catalog_type: str,
    ) -> None:
        """Templates without a ``stroke`` ref must not carry stroke
        geometry — geometry-without-paint is brittle and would imply
        an absent stroke at the renderer."""
        template = provider.resolve(catalog_type, None, {})
        assert template is not None
        assert template.style.get("stroke") is None, (
            f"premise changed: {catalog_type} now declares a stroke"
        )
        for prop in ("strokeWeight", "strokeAlign", "dashPattern"):
            assert prop not in template.style, (
                f"{catalog_type} has no stroke ref but carries "
                f"{prop}; that's a default leak the other direction"
            )


class TestTemplateVisibleNotEmitted:
    """``visible`` is intentionally NOT carried.

    Per Codex 5.5: "Visibility is handled separately as
    `element['visible'] is False`; `true` has no payoff and adds
    noise." Templates always default to visible.
    """

    @pytest.fixture
    def provider(self) -> UniversalCatalogProvider:
        return UniversalCatalogProvider()

    @pytest.mark.parametrize("catalog_type", sorted(UNIVERSAL_COMPONENT_TYPES))
    def test_no_template_carries_visible_key(
        self, provider: UniversalCatalogProvider, catalog_type: str,
    ) -> None:
        template = provider.resolve(catalog_type, None, {})
        assert template is not None
        assert "visible" not in template.style


# ---------------------------------------------------------------------------
# End-to-end — compose_screen propagates the new defaults to IR.visual
# ---------------------------------------------------------------------------


class TestComposeForwardsTemplateDefaults:
    """``_apply_template_to_parent`` must seed ``element['visual']``
    with the new visual-prop defaults so the property-registry emit
    path (which reads from ``visual``) actually emits them.

    Without the bridge, the template-level fix is a no-op: opacity
    in ``template.style`` would never reach the renderer.
    """

    def test_button_compose_carries_opacity_in_visual(self):
        """Headline case: a button composed via Mode 3 must surface
        ``opacity=1.0`` in its IR ``visual`` dict so the registry
        emitter outputs ``var.opacity = 1.0;``."""
        spec = compose_screen([{
            "type": "button",
            "props": {"text": "Sign In"},
        }])
        button = next(
            e for e in spec["elements"].values() if e["type"] == "button"
        )
        visual = button.get("visual") or {}
        assert visual.get("opacity") == 1.0

    def test_card_compose_carries_full_stroke_geometry(self):
        """Card has a stroke ref, so its composed IR must surface
        strokeWeight/strokeAlign/dashPattern in ``visual``."""
        spec = compose_screen([{
            "type": "card",
            "children": [{"type": "text", "props": {"text": "Hello"}}],
        }])
        card = next(
            e for e in spec["elements"].values() if e["type"] == "card"
        )
        visual = card.get("visual") or {}
        assert visual.get("strokeWeight") == 1.0
        assert visual.get("strokeAlign") == "INSIDE"
        assert visual.get("dashPattern") == []
        assert visual.get("opacity") == 1.0

    def test_avatar_compose_omits_stroke_geometry(self):
        """Avatar has no stroke ref; composed IR must not carry
        stroke geometry."""
        spec = compose_screen([{"type": "avatar", "props": {}}])
        avatar = next(
            e for e in spec["elements"].values() if e["type"] == "avatar"
        )
        visual = avatar.get("visual") or {}
        assert visual.get("opacity") == 1.0
        for prop in ("strokeWeight", "strokeAlign", "dashPattern"):
            assert prop not in visual, (
                f"avatar has no template stroke but composed IR "
                f"carries {prop} in visual"
            )

    def test_component_key_path_does_not_receive_template_defaults(self):
        """A node with explicit ``component_key`` is Mode-1 reuse;
        ``_apply_template_to_parent`` is gated on ``not component_key``,
        so the new visual defaults must not bleed onto Mode-1
        instances (the project library's master owns its visuals)."""
        spec = compose_screen([{
            "type": "button",
            "component_key": "button/primary",
            "props": {"text": "Go"},
        }])
        btn = next(
            e for e in spec["elements"].values() if e["type"] == "button"
        )
        visual = btn.get("visual") or {}
        assert "opacity" not in visual, (
            "Mode-1 instance must not receive Mode-3 template "
            "defaults — component master owns visuals"
        )
        assert "strokeWeight" not in visual

    def test_existing_fill_radius_overlay_still_works(self):
        """Regression guard: the existing `style` allowlist
        (fill/fg/stroke/radius/shadow) keeps working after we add
        the visual bridge alongside it."""
        spec = compose_screen([{
            "type": "card",
            "children": [{"type": "text", "props": {"text": "Hi"}}],
        }])
        card = next(
            e for e in spec["elements"].values() if e["type"] == "card"
        )
        # Existing test_compose.py contract — must not regress.
        assert "fill" in card.get("style", {})
        assert "radius" in card.get("style", {})

    def test_template_defaults_use_setdefault_semantics(self):
        """Don't-clobber contract: when ``element['visual']`` already
        has opacity (e.g. populated by ``_apply_retrieved_root_visual``
        from a corpus subtree), the template's default must NOT
        overwrite it. Verified by manually pre-populating the element
        and re-running the bridge."""
        from dd.compose import _apply_template_to_parent

        element: dict = {"type": "button", "visual": {"opacity": 0.42}}
        _apply_template_to_parent("button", None, element)
        assert element["visual"]["opacity"] == 0.42, (
            "_apply_template_to_parent overwrote a pre-existing "
            "visual.opacity — should be setdefault-only"
        )
