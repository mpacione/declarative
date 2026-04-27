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


# ---------------------------------------------------------------------
# C3 — registry-driven verifier coverage harness
# ---------------------------------------------------------------------


# Per Codex 5.5 sequencing call (round 4): Sprint 2 C3 is the
# architectural rail. Each FigmaProperty that the registry says is
# figma-emittable MUST either:
#   - declare ``compare_figma=``, OR
#   - appear on the typed exemption table below with a reason code.
#
# Reason codes (chosen to be distinguishable in CI output and
# tractable at sprint-planning time):
#
#   dedicated_path
#       Property is verified, but via a dedicated KIND_* path that
#       isn't routed through compare_figma metadata yet.
#       (e.g. width/height via KIND_BOUNDS_MISMATCH, isMask via
#       KIND_MASK_MISMATCH.) Sprint 2 wires width/height; isMask
#       remains a dedicated path until per-property routing is
#       worth refactoring.
#
#   walker_missing_deferred_family
#       Walker doesn't capture this property AND it belongs to
#       a coherent family (auto-layout, text-styling) whose
#       comparator work should land together as a unit, not
#       sprinkled commit-by-commit.
#
#   low_frequency_deferred
#       Walker doesn't capture; property is observed rarely on
#       current corpora. NOTE: Codex flagged that "rare" is a weak
#       reason — corpus frequency isn't a correctness argument
#       (see VECTOR cornerRadius surfacing 23 drifts on Dank after
#       being "absent on Nouns"). Use this category sparingly,
#       and graduate to a real comparator on first observation.
#
#   out_of_scope_current_sprint
#       Walker captures + comparator could be wired today but
#       Sprint 2 deliberately scoped to text + sizing-mode bugs.
#       Listed here so reviewers see the bounded scope.

import enum


class ExemptionReason(enum.Enum):
    DEDICATED_PATH = "dedicated_path"
    WALKER_MISSING_DEFERRED_FAMILY = "walker_missing_deferred_family"
    LOW_FREQUENCY_DEFERRED = "low_frequency_deferred"
    OUT_OF_SCOPE_CURRENT_SPRINT = "out_of_scope_current_sprint"


# Properties that the registry says are emittable but the walker
# doesn't capture, OR the walker captures but no per-property
# comparator is wired (handled elsewhere). Each entry has a typed
# reason code + a one-line note for the human reader.
_WALKER_CAPTURE_EXEMPTIONS: dict[str, tuple[ExemptionReason, str]] = {
    # === Dedicated comparator paths ===
    # Sprint 2 wires width/height via compare_figma in C3; this
    # entry exists for sentinel value (was originally an exemption
    # candidate; keeping isMask as the example of dedicated_path
    # exemption that remains).
    "isMask": (
        ExemptionReason.DEDICATED_PATH,
        "compared via KIND_MASK_MISMATCH dedicated path; "
        "structural-not-scalar comparison",
    ),
    "visible": (
        ExemptionReason.DEDICATED_PATH,
        "handled by element.visible structural skip + "
        "hidden_children resolver — not a per-prop check",
    ),

    # === Auto-layout family — coherent Sprint 3 workstream ===
    "paddingTop": (
        ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
        "auto-layout family",
    ),
    "paddingRight": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                     "auto-layout family"),
    "paddingBottom": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                      "auto-layout family"),
    "paddingLeft": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                    "auto-layout family"),
    "itemSpacing": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                    "auto-layout family"),
    "counterAxisSpacing": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                           "auto-layout family"),
    "layoutPositioning": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                          "auto-layout family"),
    "layoutWrap": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                   "auto-layout family"),

    # === Text-styling family — coherent future workstream ===
    "fontFamily": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                   "text-styling family"),
    "fontWeight": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                   "text-styling family"),
    "fontSize": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                 "text-styling family"),
    "fontStyle": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                  "text-styling family"),
    "lineHeight": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                   "text-styling family"),
    "letterSpacing": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                      "text-styling family"),
    "paragraphSpacing": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                         "text-styling family"),
    "textAlignHorizontal": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                            "text-styling family"),
    "textAlignVertical": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                          "text-styling family"),
    "textDecoration": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                       "text-styling family"),
    "textCase": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                 "text-styling family"),
    "textAutoResize": (
        ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
        "text-styling family — walker DOES capture but defer "
        "to text-styling sprint for coherent normalization",
    ),
    "leadingTrim": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                    "text-styling family"),

    # === Constrained sizing family ===
    "minWidth": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                 "min/max sizing family"),
    "maxWidth": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                 "min/max sizing family"),
    "minHeight": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                  "min/max sizing family"),
    "maxHeight": (ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
                  "min/max sizing family"),

    # === Constraint family (positioning hints, not rendered values) ===
    "constraints.horizontal": (
        ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
        "constraint family — positioning hints, "
        "verifier-equivalent needs separate model",
    ),
    "constraints.vertical": (
        ExemptionReason.WALKER_MISSING_DEFERRED_FAMILY,
        "constraint family",
    ),

    # === Low-frequency deferrals (Codex: use sparingly; graduate
    # on first observation) ===
    "strokeCap": (ExemptionReason.LOW_FREQUENCY_DEFERRED,
                  "no observed drift on current corpora"),
    "strokeJoin": (ExemptionReason.LOW_FREQUENCY_DEFERRED,
                   "no observed drift on current corpora"),
    "cornerSmoothing": (ExemptionReason.LOW_FREQUENCY_DEFERRED,
                        "sub-perceptual"),
    "booleanOperation": (ExemptionReason.LOW_FREQUENCY_DEFERRED,
                         "_BUILD_VISUAL_DEFERRED documented since pre-A1"),
    "arcData": (ExemptionReason.LOW_FREQUENCY_DEFERRED,
                "ELLIPSE-only; rare in extracted corpora"),

    # === Out-of-scope (Sprint 2 deliberately doesn't tackle) ===
    "layoutMode": (ExemptionReason.OUT_OF_SCOPE_CURRENT_SPRINT,
                   "auto-layout structural property; bundle with family"),
    "primaryAxisAlignItems": (ExemptionReason.OUT_OF_SCOPE_CURRENT_SPRINT,
                              "auto-layout alignment; bundle with family"),
    "counterAxisAlignItems": (ExemptionReason.OUT_OF_SCOPE_CURRENT_SPRINT,
                              "auto-layout alignment; bundle with family"),
}


# Properties that the registry says are emittable AND the walker
# captures, but no comparator is declared today. Each entry is a
# Sprint 2 deliverable — when the comparator lands, the entry is
# REMOVED from this dict. The harness fails loudly if a property
# that should be exempted isn't, OR if an exempted property has
# silently been comparator-wired (drift in either direction).
_PENDING_COMPARATOR_EXEMPTIONS: dict[str, str] = {
    "characters": (
        "Sprint 2 C5 will close — text content equality. "
        "Currently verify_figma only checks empty/non-empty "
        "(KIND_MISSING_TEXT). User caught 'Reject' vs 'Send to Client' "
        "drift on HGB by eyeball; cross-corpus result 6905383."
    ),
    "layoutSizingHorizontal": (
        "Sprint 2 C6 will close — sizing mode equality (HUG/FIXED/FILL). "
        "Currently invisible; bounds match but mode drifts."
    ),
    "layoutSizingVertical": (
        "Sprint 2 C6 will close — sizing mode equality (HUG/FIXED/FILL). "
        "Sibling of layoutSizingHorizontal, same root cause."
    ),
    # Layout properties that would benefit from comparators but are
    # out of scope for Sprint 2's targeted observable bugs:
    "layoutMode": (
        "auto-layout mode; out of Sprint 2 scope; container-only; "
        "low observed drift on Mode-1 INSTANCE corpus"
    ),
    "primaryAxisAlignItems": (
        "auto-layout alignment; out of Sprint 2 scope; comparator deferred"
    ),
    "counterAxisAlignItems": (
        "auto-layout alignment; out of Sprint 2 scope; comparator deferred"
    ),
}


def _walker_captures(figma_name: str) -> bool:
    """Static knowledge of which properties the walker
    (render_test/walk_ref.js) captures today. This is a hand-
    maintained list that mirrors the JS source. Sprint-2 doesn't
    refactor the walker; it ensures the registry+verifier surface
    matches what the walker reports."""
    # Captured per render_test/walk_ref.js (verified 2026-04-27):
    captured = frozenset({
        "fills", "strokes", "strokeWeight", "strokeAlign", "dashPattern",
        "effects", "opacity", "blendMode", "rotation", "cornerRadius",
        "clipsContent", "isMask",
        # Bounds — captured at rendered-tree top level (line 210-211)
        "width", "height",
        # Text content (the value, not the styling family)
        "characters",
        # Layout sizing modes
        "layoutSizingHorizontal", "layoutSizingVertical",
        # Auto-layout properties walker captures (mode + alignment)
        "layoutMode", "primaryAxisAlignItems", "counterAxisAlignItems",
        # Text auto-resize (lone text-styling capture; deferred to family)
        "textAutoResize",
    })
    return figma_name in captured


class TestRegistryDrivenVerifierCoverage:
    """The architectural rail.

    For each FigmaProperty registered as figma-emittable:
      - declare ``compare_figma=`` OR
      - appear on _WALKER_CAPTURE_EXEMPTIONS (typed) OR
      - appear on _PENDING_COMPARATOR_EXEMPTIONS (Sprint 2 targets)

    Otherwise the test fails — closing the directional asymmetry
    between what the LLM may emit (is_capable) and what the
    verifier checks.
    """

    def test_every_emittable_property_either_compared_or_exempted(self):
        """The synth-gen-relevant assertion: every figma-emittable
        property must be either (a) wired with compare_figma,
        (b) typed-exempted in _WALKER_CAPTURE_EXEMPTIONS, or
        (c) pending-exempted in _PENDING_COMPARATOR_EXEMPTIONS."""
        from dd.property_registry import PROPERTIES

        violations = []
        for prop in PROPERTIES:
            figma_caps = prop.capabilities.get("figma", frozenset())
            if not figma_caps:
                continue  # Not figma-emittable; not in scope
            if prop.compare_figma is not None:
                continue  # Comparator wired; covered
            if prop.figma_name in _WALKER_CAPTURE_EXEMPTIONS:
                continue  # Typed exemption with reason code
            if prop.figma_name in _PENDING_COMPARATOR_EXEMPTIONS:
                continue  # Sprint 2 target; will land via C5/C6
            # Otherwise: silent gap — fail the test
            violations.append(
                f"{prop.figma_name}: emittable on figma + no "
                f"compare_figma + no entry in _WALKER_CAPTURE_EXEMPTIONS "
                f"or _PENDING_COMPARATOR_EXEMPTIONS"
            )
        if violations:
            pytest.fail(
                "Registry-driven verifier coverage violations:\n  - "
                + "\n  - ".join(violations)
            )

    def test_no_stale_pending_exemptions(self):
        """If a property is on _PENDING_COMPARATOR_EXEMPTIONS but
        ALSO has compare_figma wired, the exemption is stale.
        Catches the case where a comparator lands without removing
        the exemption."""
        from dd.property_registry import PROPERTIES

        by_name = {p.figma_name: p for p in PROPERTIES}
        stale = []
        for figma_name in _PENDING_COMPARATOR_EXEMPTIONS:
            prop = by_name.get(figma_name)
            if prop and prop.compare_figma is not None:
                stale.append(figma_name)
        assert not stale, (
            f"Stale pending exemptions (compare_figma now wired): "
            f"{stale}"
        )

    def test_no_stale_walker_exemptions(self):
        """Same idea: if a walker-exempted property has compare_figma
        wired, the exemption is stale. (Note: a property can be
        walker-captured AND walker-exempted with reason
        DEDICATED_PATH — that's not stale, it just routes via a
        non-compare_figma path.)"""
        from dd.property_registry import PROPERTIES

        by_name = {p.figma_name: p for p in PROPERTIES}
        stale = []
        for figma_name, (reason, _note) in _WALKER_CAPTURE_EXEMPTIONS.items():
            prop = by_name.get(figma_name)
            if prop is None:
                continue  # Property may be a synthetic/derived name
            # DEDICATED_PATH exemptions are allowed even when the
            # property has compare_figma — that's fine.
            if prop.compare_figma is not None and reason != ExemptionReason.DEDICATED_PATH:
                stale.append((figma_name, reason.value))
        assert not stale, (
            f"Stale walker exemptions (compare_figma wired but "
            f"reason isn't DEDICATED_PATH): {stale}"
        )

    def test_pending_comparator_exemption_known_targets(self):
        """The pending list is Sprint-2's plan made concrete.
        characters and layoutSizingHorizontal/Vertical MUST be on
        the pending list to make C5/C6 = remove-and-add pairs."""
        for sprint2_target in ("characters", "layoutSizingHorizontal",
                              "layoutSizingVertical"):
            assert sprint2_target in _PENDING_COMPARATOR_EXEMPTIONS, (
                f"Sprint 2 plans to add {sprint2_target} comparator; "
                f"must be in _PENDING_COMPARATOR_EXEMPTIONS until "
                f"C5/C6 lands"
            )

    def test_walker_exemption_categories_are_typed(self):
        """Every walker-exemption uses ExemptionReason enum, not
        free-form strings. Codex's call: typed reason codes make
        the inventory tractable at sprint-planning time."""
        for figma_name, entry in _WALKER_CAPTURE_EXEMPTIONS.items():
            assert isinstance(entry, tuple) and len(entry) == 2, (
                f"{figma_name}: walker exemption must be "
                f"(ExemptionReason, note); got {entry!r}"
            )
            reason, note = entry
            assert isinstance(reason, ExemptionReason), (
                f"{figma_name}: reason must be ExemptionReason; "
                f"got {type(reason).__name__}"
            )
            assert isinstance(note, str) and note, (
                f"{figma_name}: note must be a non-empty string"
            )
