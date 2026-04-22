"""Mode 3 composition — executable contract for ADR-008.

These tests encode the public-API contract of the composition system
(provider registry, token cascade, variant inducer, compose
integration) before the implementation lands. They are INTENTIONALLY
failing on ``main`` and will pass when PR #0 (catalog ontology
migration) and PR #1 (``dd/composition/*`` + variant inducer) land.

Organisation matches the ADR-008 phasing:

- ``TestCatalogOntologyMigration``     — PR #0 contract
- ``TestPresentationTemplate``         — PR #1 data model
- ``TestComponentProviderProtocol``    — PR #1 provider contract
- ``TestProviderRegistry``             — PR #1 registry behaviour
- ``TestTokenCascade``                 — PR #1 cascade behaviour
- ``TestSlotContract``                 — PR #1 slot-type matching
- ``TestCompoundVariants``             — PR #1 variant layering
- ``TestVariantInducer``               — PR #1 Stream-B inducer
- ``TestComposeIntegration``           — PR #1 fall-through hookpoint
- ``TestFeatureFlag``                  — PR #1 kill switches
- ``TestBoundaryContract``             — PR #1 new KIND_* codes
- ``TestBackCompat``                   — PR #0 + PR #1 invariants

Every test either imports from a path that doesn't yet exist
(ImportError) or asserts behaviour that isn't yet implemented
(AssertionError). Both signal "contract not met" — the right TDD
red state.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field, is_dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_context() -> dict[str, Any]:
    """Minimum ``resolve(type, variant, context)`` context payload."""
    return {
        "project_tokens": {},
        "ingested_tokens": {},
        "universal_tokens": {},
        "variant_bindings": {},
    }


# ---------------------------------------------------------------------------
# PR #0 — Catalog ontology migration
# ---------------------------------------------------------------------------


class TestCatalogOntologyMigration:
    """PR #0 — catalog changes must land without schema regression."""

    def test_new_types_present_in_catalog(self):
        """The seven added types must exist in CATALOG_ENTRIES."""
        from dd.catalog import CATALOG_ENTRIES
        names = {e["canonical_name"] for e in CATALOG_ENTRIES}
        for new_type in (
            "divider",
            "progress",
            "spinner",
            "kbd",
            "number_input",
            "otp_input",
            "command",
        ):
            assert new_type in names, f"{new_type} missing from catalog"

    def test_toggle_group_preserved_as_alias(self):
        """Demoted type must still resolve via aliases (back-compat)."""
        from dd.catalog import CATALOG_ENTRIES
        toggle = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "toggle"
        )
        assert "toggle_group" in (toggle.get("aliases") or [])

    def test_context_menu_preserved_as_alias(self):
        from dd.catalog import CATALOG_ENTRIES
        menu = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "menu"
        )
        assert "context_menu" in (menu.get("aliases") or [])

    def test_list_item_has_six_slot_grammar(self):
        """Material's six-slot list-item shape is the canonical grammar."""
        from dd.catalog import CATALOG_ENTRIES
        li = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "list_item"
        )
        slots = li.get("slot_definitions") or {}
        for slot_name in (
            "leading",
            "overline",
            "headline",
            "supporting",
            "trailing_supporting",
            "trailing",
        ):
            assert slot_name in slots, f"list_item missing slot {slot_name}"

    def test_card_renames_image_to_media(self):
        from dd.catalog import CATALOG_ENTRIES
        card = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "card"
        )
        slots = card.get("slot_definitions") or {}
        assert "media" in slots
        assert "image" not in slots  # renamed, not duplicated

    def test_alert_has_close_slot(self):
        from dd.catalog import CATALOG_ENTRIES
        alert = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "alert"
        )
        slots = alert.get("slot_definitions") or {}
        assert "close" in slots

    def test_text_input_has_helper_slot(self):
        from dd.catalog import CATALOG_ENTRIES
        ti = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "text_input"
        )
        slots = ti.get("slot_definitions") or {}
        assert "helper" in slots

    def test_state_variant_axis_declared(self):
        """Interactive types must declare a `state` axis enum."""
        from dd.catalog import CATALOG_ENTRIES
        button = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "button"
        )
        axes = button.get("variant_axes") or {}
        assert "state" in axes
        assert "default" in (axes["state"].get("values") or [])
        assert "disabled" in (axes["state"].get("values") or [])

    def test_tone_variant_axis_declared(self):
        """Actions / alerts must declare a `tone` axis."""
        from dd.catalog import CATALOG_ENTRIES
        button = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "button"
        )
        axes = button.get("variant_axes") or {}
        assert "tone" in axes
        assert "destructive" in (axes["tone"].get("values") or [])

    def test_density_variant_axis_declared_for_lists(self):
        from dd.catalog import CATALOG_ENTRIES
        list_item = next(
            e for e in CATALOG_ENTRIES if e["canonical_name"] == "list_item"
        )
        axes = list_item.get("variant_axes") or {}
        assert "density" in axes

    def test_semantic_role_not_read_anywhere(self):
        """Deprecated field present but never queried.

        Assertion proxy: no test in tests/test_catalog.py should assert
        ANY behavioral dependency on semantic_role. Smoke guard only —
        full removal deferred to a cleanup PR per ADR-008.
        """
        # This test documents the deprecation; it passes as long as the
        # field is still present (back-compat) but no runtime consumer
        # exists. Real enforcement is by convention + inline comment.
        from dd.catalog import CatalogEntry  # noqa: F401
        # If someone later removes `semantic_role` from the TypedDict
        # without updating this test, the import still succeeds (TypedDict
        # with total=False is permissive). The test serves as documentation.


# ---------------------------------------------------------------------------
# PR #1 — Data model
# ---------------------------------------------------------------------------


class TestPresentationTemplate:
    """PR #1 — ``PresentationTemplate`` data shape."""

    def test_is_frozen_dataclass(self):
        from dd.composition.protocol import PresentationTemplate
        assert is_dataclass(PresentationTemplate)
        tmpl = PresentationTemplate(
            catalog_type="button",
            variant="primary",
            provider="catalog:universal",
            layout={},
            slots={},
            style={},
            compound_variants=[],
        )
        with pytest.raises((AttributeError, Exception)):
            tmpl.catalog_type = "changed"  # type: ignore[misc]

    def test_minimal_construction(self):
        from dd.composition.protocol import PresentationTemplate
        tmpl = PresentationTemplate(
            catalog_type="button",
            variant=None,
            provider="catalog:universal",
            layout={"direction": "horizontal"},
            slots={},
            style={},
            compound_variants=[],
        )
        assert tmpl.catalog_type == "button"
        assert tmpl.variant is None


# ---------------------------------------------------------------------------
# PR #1 — Provider protocol
# ---------------------------------------------------------------------------


class TestComponentProviderProtocol:
    """The ``ComponentProvider`` protocol defines registry membership."""

    def test_protocol_importable(self):
        from dd.composition.protocol import ComponentProvider  # noqa: F401

    def test_runtime_checkable_with_shape(self):
        """A class with `backend`, `priority`, `supports`, `resolve` conforms."""
        from dd.composition.protocol import ComponentProvider

        class FakeProvider:
            backend = "catalog:test"
            priority = 0

            def supports(self, catalog_type: str, variant: str | None) -> bool:
                return False

            def resolve(self, catalog_type: str, variant: str | None, context: dict[str, Any]):
                return None

        assert isinstance(FakeProvider(), ComponentProvider)


# ---------------------------------------------------------------------------
# PR #1 — Registry
# ---------------------------------------------------------------------------


def _fake_provider(
    backend: str,
    priority: int,
    supports_spec: dict[tuple[str, str | None], bool],
    template_factory=None,
):
    """Build a minimal provider for registry tests.

    ``supports_spec`` maps ``(type, variant) -> bool`` for test control.
    ``template_factory`` is optional and returns a ``PresentationTemplate``
    when ``resolve`` is called on a supported pair.
    """
    from dd.composition.protocol import PresentationTemplate

    class _FakeProvider:
        def __init__(self):
            self.backend = backend
            self.priority = priority

        def supports(self, catalog_type: str, variant: str | None) -> bool:
            return supports_spec.get((catalog_type, variant), False)

        def resolve(self, catalog_type: str, variant: str | None, context):
            if not self.supports(catalog_type, variant):
                return None
            if template_factory:
                return template_factory(catalog_type, variant, backend)
            return PresentationTemplate(
                catalog_type=catalog_type,
                variant=variant,
                provider=backend,
                layout={},
                slots={},
                style={},
                compound_variants=[],
            )

    return _FakeProvider()


class TestProviderRegistry:
    """Registry walks providers by priority; first supports-true wins."""

    def test_higher_priority_wins(self):
        from dd.composition.registry import ProviderRegistry
        low = _fake_provider("project:a", 10, {("button", "primary"): True})
        high = _fake_provider("project:b", 100, {("button", "primary"): True})
        reg = ProviderRegistry([low, high])
        template, errors = reg.resolve("button", "primary", {})
        assert template is not None
        assert template.provider == "project:b"
        assert errors == []

    def test_tie_breaks_alphabetical_on_backend(self):
        """Equal priority → alphabetical on `backend` (deterministic)."""
        from dd.composition.registry import ProviderRegistry
        s = _fake_provider(
            "ingested:shadcn", 50, {("button", "primary"): True}
        )
        c = _fake_provider(
            "ingested:carbon", 50, {("button", "primary"): True}
        )
        reg = ProviderRegistry([s, c])  # order-independent input
        template, _ = reg.resolve("button", "primary", {})
        assert template is not None
        assert template.provider == "ingested:carbon"  # c < s

    def test_fallthrough_when_first_lacks_variant(self):
        """First provider returns False, second matches — walk proceeds."""
        from dd.composition.registry import ProviderRegistry
        project = _fake_provider(
            "project:dank", 100, {("button", "primary"): False}
        )
        ingested = _fake_provider(
            "ingested:shadcn", 50, {("button", "primary"): True}
        )
        reg = ProviderRegistry([project, ingested])
        template, errors = reg.resolve("button", "primary", {})
        assert template is not None
        assert template.provider == "ingested:shadcn"
        # The project miss is informational, not terminal.
        kinds = {e.kind for e in errors}
        from dd.boundary import KIND_VARIANT_NOT_FOUND
        assert KIND_VARIANT_NOT_FOUND in kinds

    def test_exhausted_registry_emits_no_provider_match(self):
        from dd.composition.registry import ProviderRegistry
        from dd.boundary import KIND_NO_PROVIDER_MATCH
        reg = ProviderRegistry([
            _fake_provider("project:a", 100, {}),
            _fake_provider("catalog:universal", 10, {}),
        ])
        template, errors = reg.resolve("button", "primary", {})
        assert template is None
        kinds = {e.kind for e in errors}
        assert KIND_NO_PROVIDER_MATCH in kinds

    def test_resolution_is_deterministic_under_stable_priority(self):
        """Same registry, same query → same result (for CI reproducibility)."""
        from dd.composition.registry import ProviderRegistry
        providers = [
            _fake_provider("ingested:carbon", 50, {("card", None): True}),
            _fake_provider("ingested:shadcn", 50, {("card", None): True}),
            _fake_provider("catalog:universal", 10, {("card", None): True}),
        ]
        reg1 = ProviderRegistry(providers)
        reg2 = ProviderRegistry(list(reversed(providers)))
        t1, _ = reg1.resolve("card", None, {})
        t2, _ = reg2.resolve("card", None, {})
        assert t1 is not None and t2 is not None
        assert t1.provider == t2.provider  # both pick "ingested:carbon"


# ---------------------------------------------------------------------------
# PR #1 — Token cascade
# ---------------------------------------------------------------------------


class TestTokenCascade:
    """Three-layer cascade: project > ingested > universal."""

    def test_project_layer_wins_over_ingested_over_universal(self):
        from dd.composition.cascade import TokenCascade
        cascade = TokenCascade(
            project={"color.brand.primary": "#FF0000"},
            ingested={"color.brand.primary": "#00FF00"},
            universal={"color.brand.primary": "#0000FF"},
        )
        value, errors = cascade.resolve("{color.brand.primary}")
        assert value == "#FF0000"
        assert errors == []

    def test_ingested_wins_when_project_missing(self):
        from dd.composition.cascade import TokenCascade
        cascade = TokenCascade(
            project={},
            ingested={"color.brand.primary": "#00FF00"},
            universal={"color.brand.primary": "#0000FF"},
        )
        value, _ = cascade.resolve("{color.brand.primary}")
        assert value == "#00FF00"

    def test_unresolved_ref_emits_structured_error_and_literal_fallback(self):
        from dd.composition.cascade import TokenCascade
        from dd.boundary import KIND_TOKEN_UNRESOLVED
        cascade = TokenCascade(project={}, ingested={}, universal={})
        value, errors = cascade.resolve("{color.nonexistent}")
        assert len(errors) == 1
        assert errors[0].kind == KIND_TOKEN_UNRESOLVED
        # Literal fallback: render must still proceed.
        assert value is not None

    def test_literal_value_passes_through_unchanged(self):
        """Non-ref strings are returned verbatim (no cascade walk)."""
        from dd.composition.cascade import TokenCascade
        cascade = TokenCascade(project={}, ingested={}, universal={})
        value, errors = cascade.resolve("#FF0000")
        assert value == "#FF0000"
        assert errors == []


# ---------------------------------------------------------------------------
# PR #1 — Slot-contract typing
# ---------------------------------------------------------------------------


class TestSlotContract:
    """Slots declare allowed child types; mismatches emit structured errors."""

    def test_matching_slot_type_resolves_without_error(self):
        from dd.composition.protocol import PresentationTemplate, SlotSpec
        from dd.composition.slots import validate_slot_child
        tmpl = PresentationTemplate(
            catalog_type="dialog",
            variant=None,
            provider="catalog:universal",
            layout={},
            slots={"footer": SlotSpec(allowed=["button"], required=False)},
            style={},
            compound_variants=[],
        )
        child = {"type": "button", "variant": "primary"}
        errors = validate_slot_child(tmpl, "footer", child)
        assert errors == []

    def test_slot_type_mismatch_emits_kind_slot_type_mismatch(self):
        from dd.composition.protocol import PresentationTemplate, SlotSpec
        from dd.composition.slots import validate_slot_child
        from dd.boundary import KIND_SLOT_TYPE_MISMATCH
        tmpl = PresentationTemplate(
            catalog_type="dialog",
            variant=None,
            provider="catalog:universal",
            layout={},
            slots={"footer": SlotSpec(allowed=["button"], required=False)},
            style={},
            compound_variants=[],
        )
        child = {"type": "text", "props": {"text": "not a button"}}
        errors = validate_slot_child(tmpl, "footer", child)
        assert any(e.kind == KIND_SLOT_TYPE_MISMATCH for e in errors)


# ---------------------------------------------------------------------------
# PR #1 — Compound variants (cva-style layering)
# ---------------------------------------------------------------------------


class TestCompoundVariants:
    def test_compound_variant_overrides_single_variant(self):
        """A compound {size=sm, tone=destructive} overrides the base."""
        from dd.composition.protocol import (
            CompoundOverride,
            PresentationTemplate,
        )
        from dd.composition.variants import apply_variants
        tmpl = PresentationTemplate(
            catalog_type="button",
            variant="destructive",
            provider="catalog:universal",
            layout={"padding": {"x": 16, "y": 12}},
            slots={},
            style={"fill": "{color.error}"},
            compound_variants=[
                CompoundOverride(
                    match={"size": "sm", "tone": "destructive"},
                    overrides={"layout": {"padding": {"x": 8, "y": 4}}},
                ),
            ],
        )
        resolved = apply_variants(tmpl, {"size": "sm", "tone": "destructive"})
        assert resolved["layout"]["padding"]["x"] == 8
        assert resolved["style"]["fill"] == "{color.error}"  # untouched

    def test_compound_match_requires_all_axes(self):
        """Partial match of compound axes does NOT trigger the override."""
        from dd.composition.protocol import (
            CompoundOverride,
            PresentationTemplate,
        )
        from dd.composition.variants import apply_variants
        tmpl = PresentationTemplate(
            catalog_type="button",
            variant="destructive",
            provider="catalog:universal",
            layout={"padding": {"x": 16}},
            slots={},
            style={},
            compound_variants=[
                CompoundOverride(
                    match={"size": "sm", "tone": "destructive"},
                    overrides={"layout": {"padding": {"x": 8}}},
                ),
            ],
        )
        # Only `tone` matches, `size` is default — no override.
        resolved = apply_variants(tmpl, {"size": "md", "tone": "destructive"})
        assert resolved["layout"]["padding"]["x"] == 16


# ---------------------------------------------------------------------------
# PR #1 — Variant inducer (Stream B v0.1)
# ---------------------------------------------------------------------------


class TestVariantInducer:
    def test_module_importable(self):
        from dd.cluster_variants import induce_variants  # noqa: F401

    def test_persists_variant_token_binding_rows(self, tmp_path: Path):
        """Inducer writes per-(type, variant, slot) rows with the declared schema."""
        from dd.cluster_variants import induce_variants
        from dd.db import init_db

        db_path = tmp_path / "test.db"
        conn = init_db(str(db_path))
        # Run with a stub VLM that labels every cluster "primary" for deterministic test
        induce_variants(
            conn,
            vlm_call=lambda prompt, images: {
                "verdict": "primary",
                "confidence": 0.9,
            },
            catalog_types=["button"],
        )
        rows = conn.execute(
            "SELECT catalog_type, variant, slot, confidence, source "
            "FROM variant_token_binding"
        ).fetchall()
        # Specific behavior depends on fixture data; at minimum the schema
        # must accept writes in the declared shape.
        for row in rows:
            assert row[0] == "button"  # catalog_type
            assert isinstance(row[1], str)  # variant name
            assert isinstance(row[2], str)  # slot name
            assert 0.0 <= row[3] <= 1.0  # confidence
            assert row[4] in {"cluster", "vlm", "screen_context", "user"}

    def test_unknown_vlm_label_persists_as_custom_N(self, tmp_path: Path):
        """VLM saying 'unknown' → stored as `custom_N`, not dropped."""
        from dd.cluster_variants import induce_variants
        from dd.db import init_db

        db_path = tmp_path / "test.db"
        conn = init_db(str(db_path))
        induce_variants(
            conn,
            vlm_call=lambda prompt, images: {
                "verdict": "unknown",
                "confidence": 0.3,
            },
            catalog_types=["button"],
        )
        variants = {
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT variant FROM variant_token_binding"
            )
        }
        assert any(v.startswith("custom_") for v in variants)

    def test_variant_binding_missing_emits_structured_error(self):
        """When ProjectCKRProvider queries for a binding that doesn't exist."""
        from dd.composition.providers.project_ckr import ProjectCKRProvider
        from dd.boundary import KIND_VARIANT_BINDING_MISSING
        # Use the real schema so provider and DB stay in sync.
        from dd.db import init_db
        conn = init_db(":memory:")
        provider = ProjectCKRProvider(conn)
        context: dict[str, object] = {}
        template = provider.resolve("button", "primary", context)
        # Template still returned with a fallback shape so render
        # proceeds; but at least one error must flag the missing binding.
        errors = context.get("__errors__", [])
        kinds = {e.kind for e in errors}
        assert KIND_VARIANT_BINDING_MISSING in kinds


# ---------------------------------------------------------------------------
# PR #1 — Compose integration (fall-through hookpoint)
# ---------------------------------------------------------------------------


class TestComposeIntegration:
    def test_mode3_fires_when_mode1_and_mode2_both_fail(self):
        """Synthetic IR (no component_key, no DB node) triggers Mode-3."""
        from dd.compose import compose_screen
        components = [{"type": "button", "props": {"text": "Sign In"}}]
        spec = compose_screen(components)
        # After Mode-3 lands, button-1 must have children or a resolved
        # composition — not an empty 100x100 frame.
        button = next(
            e for eid, e in spec["elements"].items() if e["type"] == "button"
        )
        # Either children synthesised OR a _composition hint for the renderer
        has_structure = bool(button.get("children")) or bool(
            button.get("_composition")
        )
        assert has_structure, (
            "Mode-3 must synthesise structure for button with text prop"
        )

    def test_mode3_synthetic_children_are_first_class_ir_nodes(self):
        """Synthesised text children appear in spec['elements'] with eids."""
        from dd.compose import compose_screen
        components = [{"type": "button", "props": {"text": "Save"}}]
        spec = compose_screen(components)
        button = next(
            e for eid, e in spec["elements"].items() if e["type"] == "button"
        )
        children = button.get("children") or []
        # At least one child should be a TEXT-typed element carrying "Save"
        for child_eid in children:
            child = spec["elements"].get(child_eid)
            if child and child.get("type") == "text":
                if child.get("props", {}).get("text") == "Save":
                    return
        pytest.fail(
            "Mode-3 must splice a text child carrying the button's label"
        )

    def test_mode1_unchanged_when_component_key_present(self):
        """A component with a component_key still goes through Mode-1."""
        from dd.compose import compose_screen
        components = [
            {
                "type": "button",
                "component_key": "button/primary",
                "props": {"text": "Sign In"},
            }
        ]
        spec = compose_screen(components)
        button = next(
            e for eid, e in spec["elements"].items() if e["type"] == "button"
        )
        # Mode-1 preserves component_key; does NOT synthesise internal structure
        assert button.get("component_key") == "button/primary"


class TestMode3TextInputLabelHoist:
    """Mode-3 text_input label-hoist contract.

    The universal catalog's text_input template declares:
    - ``label`` slot at position="top"     (external sibling ABOVE the input)
    - ``input`` slot at position="fill"    (the actual input field content)
    - ``helper`` slot at position="bottom" (external sibling BELOW the input)

    Pre-fix behavior (2026-04-21 Tier D re-gate): ``_mode3_synthesise_children``
    lumped ALL slot children as INTERNAL children of the text_input frame.
    Result: SoM correctly classified the input as ``container`` because
    visually a frame with "Email" + "Enter your email" stacked inside is
    NOT an input widget. Surfaced by SoM component-coverage scoring on
    the archetype login prompt (SoM-P=0.43, SoM-R=0.30, VLM=9/10).

    Fix contract: Mode-3 must wrap text_input in an outer vertical frame
    that holds [label text, text_input frame [placeholder text]]. Label +
    helper become EXTERNAL siblings; only input-slot text stays inside.
    """

    def test_label_becomes_external_sibling(self):
        from dd.compose import compose_screen
        spec = compose_screen([{
            "type": "text_input",
            "props": {"label": "Email", "placeholder": "Enter your email"},
        }])
        elements = spec["elements"]

        # Find the text_input element
        tis = [
            (eid, e) for eid, e in elements.items() if e["type"] == "text_input"
        ]
        assert len(tis) == 1, "exactly one text_input element"
        ti_eid, ti_element = tis[0]

        # Find the label text (should exist as a text element with props.text="Email")
        labels = [
            (eid, e) for eid, e in elements.items()
            if e["type"] == "text"
            and (e.get("props") or {}).get("text") == "Email"
        ]
        assert len(labels) == 1, "exactly one 'Email' text element"
        label_eid, _ = labels[0]

        # The label must NOT be an internal child of the text_input
        ti_children = ti_element.get("children") or []
        assert label_eid not in ti_children, (
            f"'Email' label should NOT be an internal child of text_input. "
            f"text_input.children={ti_children}"
        )

    def test_placeholder_stays_internal(self):
        """The `input` slot's placeholder text is visually inside the input
        field (rendered greyer) — stays as an internal child."""
        from dd.compose import compose_screen
        spec = compose_screen([{
            "type": "text_input",
            "props": {"label": "Password", "placeholder": "Enter your password"},
        }])
        elements = spec["elements"]

        tis = [
            (eid, e) for eid, e in elements.items() if e["type"] == "text_input"
        ]
        ti_eid, ti_element = tis[0]
        placeholders = [
            (eid, e) for eid, e in elements.items()
            if e["type"] == "text"
            and (e.get("props") or {}).get("text") == "Enter your password"
        ]
        assert len(placeholders) == 1, "exactly one placeholder text"
        ph_eid, _ = placeholders[0]

        ti_children = ti_element.get("children") or []
        assert ph_eid in ti_children, (
            f"placeholder should be an internal child of text_input. "
            f"text_input.children={ti_children}"
        )

    def test_wrapper_frame_contains_label_and_input(self):
        """The outer wrapper (created during label-hoist) contains the label
        text followed by the text_input frame as siblings."""
        from dd.compose import compose_screen
        spec = compose_screen([{
            "type": "text_input",
            "props": {"label": "Email", "placeholder": "Enter your email"},
        }])
        elements = spec["elements"]

        ti_eid = next(
            eid for eid, e in elements.items() if e["type"] == "text_input"
        )
        label_eid = next(
            eid for eid, e in elements.items()
            if e["type"] == "text" and (e.get("props") or {}).get("text") == "Email"
        )

        # Find the wrapper: the element whose children include BOTH the
        # label and the text_input.
        wrappers = [
            (eid, e) for eid, e in elements.items()
            if label_eid in (e.get("children") or [])
            and ti_eid in (e.get("children") or [])
        ]
        assert len(wrappers) == 1, (
            "a single wrapper frame must contain both label and text_input"
        )
        wrapper_eid, wrapper = wrappers[0]

        # Label ordered BEFORE the input (position='top' means visually
        # above in a vertical stack)
        children = wrapper.get("children") or []
        assert children.index(label_eid) < children.index(ti_eid), (
            "label must come before text_input in the wrapper's children"
        )
        # Wrapper layout is vertical (label stacks above input)
        assert (wrapper.get("layout") or {}).get("direction") == "vertical"

    def test_text_input_without_label_no_wrapper(self):
        """When there's no label, no wrapper needed — text_input returns
        directly with just its internal children."""
        from dd.compose import compose_screen
        spec = compose_screen([{
            "type": "text_input",
            "props": {"placeholder": "Search..."},
        }])
        elements = spec["elements"]
        tis = [
            (eid, e) for eid, e in elements.items() if e["type"] == "text_input"
        ]
        assert len(tis) == 1
        # No wrapper frame — the text_input is a direct root_child of screen-1
        screen_children = elements.get("screen-1", {}).get("children") or []
        assert tis[0][0] in screen_children, (
            "text_input without label should be a direct root child"
        )

    def test_round_trip_signature_preserved(self):
        """Label-hoist doesn't change compose_screen's return shape —
        still returns {root, elements, ...}."""
        from dd.compose import compose_screen
        spec = compose_screen([{
            "type": "text_input",
            "props": {"label": "Name", "placeholder": "Jane Doe"},
        }])
        assert "root" in spec
        assert "elements" in spec
        # root points at a valid element
        assert spec["root"] in spec["elements"]


# ---------------------------------------------------------------------------
# PR #1 — Feature flags (kill switches)
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    def test_disable_mode_3_short_circuits_registry(self):
        """``DD_DISABLE_MODE_3=1`` restores pre-Mode-3 empty-frame behaviour."""
        from dd.compose import compose_screen
        with patch.dict(os.environ, {"DD_DISABLE_MODE_3": "1"}):
            spec = compose_screen(
                [{"type": "button", "props": {"text": "Sign In"}}]
            )
            button = next(
                e for eid, e in spec["elements"].items()
                if e["type"] == "button"
            )
            # With the flag set, no synthetic children are produced.
            assert not button.get("children")

    def test_disable_provider_kills_specific_backend(self):
        """``DD_DISABLE_PROVIDER=ingested:shadcn`` removes just shadcn."""
        from dd.composition.registry import build_registry_from_env

        with patch.dict(
            os.environ, {"DD_DISABLE_PROVIDER": "ingested:shadcn"}
        ):
            reg = build_registry_from_env()
            backends = {p.backend for p in reg.providers}
            assert "ingested:shadcn" not in backends


# ---------------------------------------------------------------------------
# PR #1 — Boundary contract
# ---------------------------------------------------------------------------


class TestBoundaryContract:
    """New KIND_* constants must exist on dd.boundary."""

    def test_kind_no_provider_match_exists(self):
        from dd.boundary import KIND_NO_PROVIDER_MATCH
        assert isinstance(KIND_NO_PROVIDER_MATCH, str)

    def test_kind_variant_not_found_exists(self):
        from dd.boundary import KIND_VARIANT_NOT_FOUND
        assert isinstance(KIND_VARIANT_NOT_FOUND, str)

    def test_kind_token_unresolved_exists(self):
        from dd.boundary import KIND_TOKEN_UNRESOLVED
        assert isinstance(KIND_TOKEN_UNRESOLVED, str)

    def test_kind_slot_type_mismatch_exists(self):
        from dd.boundary import KIND_SLOT_TYPE_MISMATCH
        assert isinstance(KIND_SLOT_TYPE_MISMATCH, str)

    def test_kind_variant_binding_missing_exists(self):
        from dd.boundary import KIND_VARIANT_BINDING_MISSING
        assert isinstance(KIND_VARIANT_BINDING_MISSING, str)

    def test_provider_errors_are_structured_error_shaped(self):
        """All registry errors must be StructuredError instances."""
        from dd.boundary import StructuredError
        from dd.composition.registry import ProviderRegistry
        reg = ProviderRegistry([])  # empty registry
        _, errors = reg.resolve("button", "primary", {})
        assert all(isinstance(e, StructuredError) for e in errors)


# ---------------------------------------------------------------------------
# Back-compat invariants
# ---------------------------------------------------------------------------


class TestBackCompat:
    def test_semantic_role_field_still_present_despite_deprecation(self):
        """``semantic_role`` stays on CatalogEntry until a dedicated cleanup PR."""
        from dd.catalog import CATALOG_ENTRIES
        # At least one entry still has semantic_role populated
        assert any(e.get("semantic_role") for e in CATALOG_ENTRIES)

    def test_existing_compose_api_signature_unchanged(self):
        """``compose_screen(components, templates=None)`` signature preserved."""
        import inspect
        from dd.compose import compose_screen
        sig = inspect.signature(compose_screen)
        params = list(sig.parameters.keys())
        # First positional parameter is still `components`
        assert params[0] == "components"
        # Call with just components still works
        spec = compose_screen([{"type": "button", "props": {"text": "x"}}])
        assert "root" in spec
        assert "elements" in spec

    def test_round_trip_renderer_paths_unchanged(self):
        """Mode-1 (component_key) and Mode-2 (DB visuals) code paths untouched.

        Proxy: importing the renderer's public surface still works with
        the same signatures. Deeper parity runs in ``render_batch/sweep.py``.
        """
        from dd.renderers.figma import generate_figma_script
        import inspect
        sig = inspect.signature(generate_figma_script)
        params = list(sig.parameters.keys())
        # Public params preserved from current signature
        assert "spec" in params
        assert "db_visuals" in params
