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
        """Pick any registered property; the new attribute should
        exist and default to None until commit 2 wires the
        existing comparators."""
        from dd.property_registry import PROPERTIES

        prop = next(p for p in PROPERTIES if p.figma_name == "fills")
        # Field exists on every property
        assert hasattr(prop, "compare_figma")
        # Default: None (this is the no-op commit)
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
