"""Phase E #7 fix — Mode-3 universal types no longer warn.

Audit's "templateless types → defaults" finding: `image` and `card`
warned as "no template — will render as empty frame" on Nouns.
But `dd/composition/providers/universal.py:_BUILDERS` HAS templates
for these types — `UniversalCatalogProvider` supplies them via the
cascade at render time. The warning was conflating two distinct
concepts:
  - "no template available anywhere" → real warning
  - "no project-specific override in component_templates table" →
    false alarm; universal fallback handles it

Codex 2026-04-26 (gpt-5.5 high reasoning) recommended exporting
`UNIVERSAL_COMPONENT_TYPES` as a public constant from the universal
provider module, then unioning it into compose.py's
`_UNIVERSAL_TYPES` whitelist.

Phase E impact:
- p1-onboarding had 1 warning (image) — now silent
- p2-explore-grid had 6 warnings (3×card + 3×image) — now silent
- p3-auction-detail had 3 warnings (2×card + 1×image) — now silent
"""

from __future__ import annotations

from dd.composition.providers.universal import (
    _BACKBONE,
    UNIVERSAL_COMPONENT_TYPES,
)


class TestUniversalComponentTypesExport:
    """The public constant exists and equals _BACKBONE (per Codex's
    recommendation)."""

    def test_universal_component_types_is_frozenset(self):
        assert isinstance(UNIVERSAL_COMPONENT_TYPES, frozenset)

    def test_universal_component_types_equals_backbone(self):
        # Codex: "If _BACKBONE is the better semantic source,
        # UNIVERSAL_COMPONENT_TYPES = _BACKBONE."
        assert UNIVERSAL_COMPONENT_TYPES == _BACKBONE

    def test_known_types_in_universal_set(self):
        for t in (
            "image", "card", "button", "dialog",
            "tooltip", "popover", "menu", "icon",
        ):
            assert t in UNIVERSAL_COMPONENT_TYPES, (
                f"{t} is in _BUILDERS / _BACKBONE but missing from "
                f"UNIVERSAL_COMPONENT_TYPES."
            )


class TestComposeNoWarnsForUniversalTypes:
    """The headline regression test — `image` and `card` no longer
    trigger the templateless-warning in dd.compose.validate_components."""

    def _validate(self, components: list[dict], templates: dict | None = None) -> tuple[list[dict], list[str]]:
        from dd.compose import validate_components
        return validate_components(components, templates or {})

    def test_image_no_longer_warns(self):
        """Pre-fix this fired 'Type image has no template — will
        render as empty frame'. Post-fix the universal provider's
        _image_template handles it; no warning."""
        comps = [{"type": "image", "props": {}}]
        _, warnings = self._validate(comps, templates={})
        templateless_warnings = [
            w for w in warnings
            if "image" in w.lower() and "no template" in w.lower()
        ]
        assert not templateless_warnings, (
            f"Phase E #7: `image` should not produce a templateless "
            f"warning — universal provider handles it. Got: "
            f"{templateless_warnings}"
        )

    def test_card_no_longer_warns(self):
        comps = [{"type": "card", "children": []}]
        _, warnings = self._validate(comps, templates={})
        templateless_warnings = [
            w for w in warnings
            if "card" in w.lower() and "no template" in w.lower()
        ]
        assert not templateless_warnings, (
            f"Phase E #7: `card` should not produce a templateless "
            f"warning. Got: {templateless_warnings}"
        )

    def test_unknown_type_still_warns(self):
        """Defensive: types NOT in UNIVERSAL_COMPONENT_TYPES and
        NOT in project templates SHOULD still warn — that's the
        real signal."""
        # `pickle_jar` is intentionally a fake type
        comps = [{"type": "pickle_jar", "props": {}}]
        _, warnings = self._validate(comps, templates={})
        templateless_warnings = [
            w for w in warnings
            if "pickle_jar" in w.lower() and "no template" in w.lower()
        ]
        assert templateless_warnings, (
            "Defensive: unknown types not in universal set should "
            "still warn — the suppression should be specific to "
            "_BACKBONE / _BUILDERS."
        )


class TestComposeWarningsForBackboneSubset:
    """Sample several backbone types to make sure the union covers them."""

    def test_avatar_no_warning(self):
        from dd.compose import validate_components
        _, warnings = validate_components(
            [{"type": "avatar", "props": {}}], templates={},
        )
        assert not [
            w for w in warnings if "avatar" in w.lower() and "no template" in w.lower()
        ]

    def test_drawer_no_warning(self):
        from dd.compose import validate_components
        _, warnings = validate_components(
            [{"type": "drawer", "props": {}}], templates={},
        )
        assert not [
            w for w in warnings if "drawer" in w.lower() and "no template" in w.lower()
        ]

    def test_tooltip_no_warning(self):
        from dd.compose import validate_components
        _, warnings = validate_components(
            [{"type": "tooltip", "props": {}}], templates={},
        )
        assert not [
            w for w in warnings if "tooltip" in w.lower() and "no template" in w.lower()
        ]
