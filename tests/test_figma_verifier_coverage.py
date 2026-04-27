"""Sprint 2 — registry-driven Figma verifier coverage.

The architectural sprint (12 commits, tip 91a67f2) added per-prop
provenance gating + new comparators (A1.3 + A5). The cross-corpus
sweep (commit 6905383) then ran on Dank + HGB and a human caught
two real bugs by eyeballing one rendered button:

1. Wrong text content (verifier never compares characters value)
2. Wrong sizing mode (verifier never compares HUG/FIXED/FILL)

Codex 5.5 confirmed both gaps + identified the meta-gap:
the verifier's compared-property set isn't registry-driven.
The same property registry that powers constrained decoding for
synthesis (`is_capable("strokeAlign", "RECTANGLE", "figma")`)
must also power verifier coverage. Otherwise the directional
asymmetry — registry constrains generation, hand-rolled
comparators constrain verification — bites synth-gen's
feedback loop.

This module tests the new ``compare_figma`` field on
``FigmaProperty`` plus the coverage harness.

## Sprint 2 commit ladder

1. metadata types (this commit) — ``FigmaComparatorSpec`` +
   ``compare_figma`` field on ``FigmaProperty``, no
   properties wired yet.
2. annotate properties already compared today (no behavior change)
3. coverage test fails when registry says emittable +
   walker captures it + no ``compare_figma`` declared, with
   explicit exemption list for known-deferred properties.
4. A1.1 descendant-path routing for non-:self override rows.
5. text characters comparator → removes 1st exemption.
6. layoutSizingHorizontal/Vertical comparator → removes 2nd.
7. registry-driven dispatch in ``FigmaRenderVerifier``.
8. all-corpus regression sweep + sprint results.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------
# C1 — metadata types exist + are wireable on FigmaProperty
# ---------------------------------------------------------------------


class TestComparatorSpecExists:
    """The metadata type that lets a property declare how it should
    be compared on the Figma backend. Per Codex 5.5: declarative
    string ids, not inline callables, so the registry doesn't
    import verifier code."""

    def test_figma_comparator_spec_importable(self):
        from dd.property_registry import FigmaComparatorSpec  # noqa: F401

    def test_figma_comparator_spec_required_fields(self):
        from dd.property_registry import FigmaComparatorSpec

        spec = FigmaComparatorSpec(
            comparator="text_equality",
            walker_key="characters",
            kind="text_content_mismatch",
        )
        assert spec.comparator == "text_equality"
        assert spec.walker_key == "characters"
        assert spec.kind == "text_content_mismatch"

    def test_figma_comparator_spec_defaults(self):
        from dd.property_registry import FigmaComparatorSpec

        spec = FigmaComparatorSpec(
            comparator="numeric_equality",
            walker_key="opacity",
            kind="opacity_mismatch",
        )
        # Sensible defaults for optional fields per ComparatorSpec
        # contract negotiated with Codex 5.5
        assert spec.tolerance is None
        assert spec.skip_when_provenance_absent is True

    def test_figma_comparator_spec_with_tolerance(self):
        """Numeric comparators with float tolerance — needed for
        opacity, cornerRadius, etc."""
        from dd.property_registry import FigmaComparatorSpec

        spec = FigmaComparatorSpec(
            comparator="numeric_equality",
            walker_key="opacity",
            kind="opacity_mismatch",
            tolerance=0.001,
        )
        assert spec.tolerance == pytest.approx(0.001)

    def test_figma_comparator_spec_skip_provenance_off(self):
        """Some comparators MUST run regardless of provenance
        (e.g. Mode-1 head bounds compare). The flag exists so
        registry can opt out of A1.3 gating."""
        from dd.property_registry import FigmaComparatorSpec

        spec = FigmaComparatorSpec(
            comparator="bounds_equality",
            walker_key="bounds",
            kind="bounds_mismatch",
            skip_when_provenance_absent=False,
        )
        assert spec.skip_when_provenance_absent is False

    def test_figma_comparator_spec_is_frozen(self):
        """Like FigmaProperty, the spec is frozen — registry is
        declarative."""
        from dd.property_registry import FigmaComparatorSpec

        spec = FigmaComparatorSpec(
            comparator="t",
            walker_key="w",
            kind="k",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.comparator = "other"  # type: ignore[misc]


class TestFigmaPropertyCompareField:
    """The new ``compare_figma`` field on FigmaProperty. Backend-
    shaped naming per Codex's guidance: explicit single-backend
    now, promotable to ``compare={'figma': ...}`` when backend
    #2 lands. Defaults to None (no comparator declared) so this
    commit is no-op for every existing property."""

    def test_existing_property_has_compare_figma_field(self):
        """Pick a not-yet-wired property; the new attribute should
        exist on every FigmaProperty.

        After C2: ``fills`` etc. have spec wired. C5/C6 will wire
        more; deferred properties remain None. Use ``cornerSmoothing``
        as the no-op example (deferred — no comparator planned in
        this sprint)."""
        from dd.property_registry import PROPERTIES

        # Field exists on every property
        for prop in PROPERTIES:
            assert hasattr(prop, "compare_figma"), (
                f"{prop.figma_name} missing compare_figma attribute"
            )

        # Default for unwired property: None
        prop = next(p for p in PROPERTIES if p.figma_name == "cornerSmoothing")
        assert prop.compare_figma is None

    def test_compare_figma_can_be_set_to_spec(self):
        """Constructing a FigmaProperty with a comparator spec
        works."""
        from dd.property_registry import FigmaProperty, FigmaComparatorSpec

        spec = FigmaComparatorSpec(
            comparator="text_equality",
            walker_key="characters",
            kind="text_content_mismatch",
        )
        prop = FigmaProperty(
            figma_name="characters",
            db_column="text_content",
            override_fields=("characters",),
            category="text",
            value_type="string",
            compare_figma=spec,
        )
        assert prop.compare_figma is spec

    def test_compare_figma_can_remain_none(self):
        """Properties that aren't compared (e.g. token-bound,
        deferred) leave compare_figma at None — the harness will
        require an explicit exemption rather than silent skip."""
        from dd.property_registry import FigmaProperty

        prop = FigmaProperty(
            figma_name="someProp",
            db_column=None,
            category="misc",
        )
        assert prop.compare_figma is None


# ---------------------------------------------------------------------
# C2 — annotate existing comparators (no behavior change)
# ---------------------------------------------------------------------


class TestExistingComparatorsRegistered:
    """Sprint-1 comparators are already implemented in
    ``dd/verify_figma.py`` — Sprint-2 C2 declares them in the
    registry so future C3/C7 commits can validate / dispatch from
    the registry. This commit changes no runtime behavior; it only
    pins the metadata-vs-impl correspondence as a regression
    guard."""

    @pytest.fixture
    def by_name(self):
        from dd.property_registry import PROPERTIES

        return {p.figma_name: p for p in PROPERTIES}

    @pytest.mark.parametrize(
        "figma_name, comparator, walker_key, kind",
        [
            ("fills", "paint_list_equality", "fills", "fill_mismatch"),
            ("strokes", "paint_list_equality", "strokes", "stroke_mismatch"),
            ("strokeWeight", "numeric_equality", "strokeWeight",
             "stroke_weight_mismatch"),
            ("strokeAlign", "enum_equality", "strokeAlign",
             "stroke_align_mismatch"),
            ("dashPattern", "list_equality", "dashPattern",
             "dash_pattern_mismatch"),
            ("clipsContent", "bool_equality", "clipsContent",
             "clips_content_mismatch"),
            ("opacity", "numeric_equality", "opacity",
             "opacity_mismatch"),
            ("blendMode", "enum_equality", "blendMode",
             "blendmode_mismatch"),
            ("cornerRadius", "corner_radius_equality", "cornerRadius",
             "cornerradius_mismatch"),
            ("rotation", "numeric_equality", "rotation",
             "rotation_mismatch"),
            ("effects", "effect_count_equality", "effects",
             "effect_missing"),
        ],
    )
    def test_existing_comparator_declared(
        self, by_name, figma_name, comparator, walker_key, kind,
    ):
        """Each property already compared by FigmaRenderVerifier
        must declare its comparator metadata."""
        prop = by_name.get(figma_name)
        assert prop is not None, f"property {figma_name!r} not in registry"
        assert prop.compare_figma is not None, (
            f"{figma_name}: compare_figma is None — "
            f"sprint-2 C2 should have wired it"
        )
        assert prop.compare_figma.comparator == comparator, (
            f"{figma_name}: comparator id mismatch"
        )
        assert prop.compare_figma.walker_key == walker_key, (
            f"{figma_name}: walker_key mismatch"
        )
        assert prop.compare_figma.kind == kind, (
            f"{figma_name}: kind mismatch"
        )

    def test_opacity_has_tolerance(self, by_name):
        """Numeric float comparison needs tolerance — verifier
        currently uses 0.001 for opacity per
        ``_OPACITY_FLOAT_TOLERANCE``."""
        prop = by_name["opacity"]
        assert prop.compare_figma.tolerance == pytest.approx(0.001)

    def test_provenance_gated_comparators_default_to_skip(self, by_name):
        """Per A1.3: visual props on Mode-1 INSTANCE skip when
        not in _overrides side-car. Default behavior."""
        # Visual props that A1.3 gates
        for figma_name in ("fills", "strokes", "opacity", "cornerRadius",
                          "strokeWeight", "strokeAlign", "blendMode"):
            prop = by_name[figma_name]
            assert prop.compare_figma.skip_when_provenance_absent is True, (
                f"{figma_name} should be A1.3-gated"
            )
