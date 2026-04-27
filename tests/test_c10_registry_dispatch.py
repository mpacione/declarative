"""Sprint 2 C10 — verifier registry-dispatch for graduated properties.

The keystone commit. Per docs/plan-sprint-2-station-parity.md §8 row 7:
"FigmaRenderVerifier consumes compare_figma for the 3 graduated
properties; existing hand-rolled paths preserved for non-graduated.
Net comparison behavior changes here."

Codex 5.5 round-9 locked:
  - Option A(i): additive dispatch loop at end of verify_node
  - Single comparator signature: (ir_value, rendered_value, element, *, spec)
  - Helper switch for IR-value reads (not declarative ir_path on spec)
  - Empty string compares — only None skips
  - Layout-sizing normalization: IR "fill"/"hug" lowercase + numeric;
    walker "FILL"/"HUG"/"FIXED" uppercase. Helper normalizes both to
    uppercase enum.

C10 closes the HGB button bug end-to-end: with C9's descendant-path
routing populating element["_overrides"] for the text descendant,
C8's walker emitting envelope, and C10's text_equality comparator
firing on IR "Reject" vs rendered "Send to Client", the verifier
emits KIND_TEXT_CONTENT_MISMATCH.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------
# C10 — KIND_* constants exist
# ---------------------------------------------------------------------


class TestKindConstants:
    """The 3 new KIND_* constants for the graduated comparators."""

    def test_kind_text_content_mismatch_exists(self):
        from dd.boundary import KIND_TEXT_CONTENT_MISMATCH
        assert KIND_TEXT_CONTENT_MISMATCH == "text_content_mismatch"

    def test_kind_layout_sizing_h_mismatch_exists(self):
        from dd.boundary import KIND_LAYOUT_SIZING_H_MISMATCH
        assert KIND_LAYOUT_SIZING_H_MISMATCH == "layout_sizing_h_mismatch"

    def test_kind_layout_sizing_v_mismatch_exists(self):
        from dd.boundary import KIND_LAYOUT_SIZING_V_MISMATCH
        assert KIND_LAYOUT_SIZING_V_MISMATCH == "layout_sizing_v_mismatch"


# ---------------------------------------------------------------------
# C10 — registry compare_figma metadata on graduations
# ---------------------------------------------------------------------


class TestRegistryGraduationsHaveCompareSpec:
    """The 3 graduations must have compare_figma metadata wired so the
    dispatcher can find them."""

    @pytest.fixture
    def by_name(self):
        from dd.property_registry import PROPERTIES
        return {p.figma_name: p for p in PROPERTIES}

    def test_characters_has_text_equality_spec(self, by_name):
        from dd.property_registry import StationDisposition

        prop = by_name["characters"]
        assert prop.station_4 == StationDisposition.COMPARE_DISPATCH
        assert prop.compare_figma is not None
        assert prop.compare_figma.comparator == "text_equality"
        assert prop.compare_figma.walker_key == "characters"
        assert prop.compare_figma.kind == "text_content_mismatch"

    def test_layout_sizing_h_has_enum_equality_spec(self, by_name):
        from dd.property_registry import StationDisposition

        prop = by_name["layoutSizingHorizontal"]
        assert prop.station_4 == StationDisposition.COMPARE_DISPATCH
        assert prop.compare_figma is not None
        assert prop.compare_figma.comparator == "enum_equality"
        assert prop.compare_figma.walker_key == "layoutSizingHorizontal"
        assert prop.compare_figma.kind == "layout_sizing_h_mismatch"

    def test_layout_sizing_v_has_enum_equality_spec(self, by_name):
        from dd.property_registry import StationDisposition

        prop = by_name["layoutSizingVertical"]
        assert prop.station_4 == StationDisposition.COMPARE_DISPATCH
        assert prop.compare_figma is not None
        assert prop.compare_figma.comparator == "enum_equality"
        assert prop.compare_figma.walker_key == "layoutSizingVertical"
        assert prop.compare_figma.kind == "layout_sizing_v_mismatch"


# ---------------------------------------------------------------------
# C10 — comparator implementation registry
# ---------------------------------------------------------------------


class TestComparatorRegistry:
    """Comparator implementations are registered by string id in
    dd/verify_figma.py and looked up via FigmaComparatorSpec.comparator."""

    def test_comparator_registry_importable(self):
        from dd.verify_figma import _COMPARATOR_IMPLS  # noqa: F401

    def test_text_equality_comparator_registered(self):
        from dd.verify_figma import _COMPARATOR_IMPLS

        assert "text_equality" in _COMPARATOR_IMPLS
        assert callable(_COMPARATOR_IMPLS["text_equality"])

    def test_enum_equality_comparator_registered(self):
        from dd.verify_figma import _COMPARATOR_IMPLS

        assert "enum_equality" in _COMPARATOR_IMPLS
        assert callable(_COMPARATOR_IMPLS["enum_equality"])

    def test_every_compare_dispatch_property_has_implementation(self):
        """Defensive contract per Codex round-9: don't silently
        skip; if a property is COMPARE_DISPATCH and points to an
        unregistered comparator, that's a bug. This test catches it."""
        from dd.property_registry import PROPERTIES, StationDisposition
        from dd.verify_figma import _COMPARATOR_IMPLS

        for prop in PROPERTIES:
            if prop.station_4 != StationDisposition.COMPARE_DISPATCH:
                continue
            assert prop.compare_figma is not None, (
                f"{prop.figma_name}: COMPARE_DISPATCH but no compare_figma"
            )
            comparator_id = prop.compare_figma.comparator
            assert comparator_id in _COMPARATOR_IMPLS, (
                f"{prop.figma_name}: comparator {comparator_id!r} "
                f"not registered in _COMPARATOR_IMPLS"
            )


class TestComparatorImpls:
    """Direct unit tests for the comparator functions."""

    def _make_spec(self, kind):
        from dd.property_registry import FigmaComparatorSpec
        return FigmaComparatorSpec(
            comparator="text_equality",
            walker_key="characters",
            kind=kind,
        )

    def test_text_equality_returns_none_on_match(self):
        from dd.verify_figma import _COMPARATOR_IMPLS

        spec = self._make_spec("text_content_mismatch")
        result = _COMPARATOR_IMPLS["text_equality"](
            "Reject", "Reject", {"id": "text-1"}, spec=spec,
        )
        assert result is None

    def test_text_equality_returns_error_on_mismatch(self):
        from dd.verify_figma import _COMPARATOR_IMPLS

        spec = self._make_spec("text_content_mismatch")
        result = _COMPARATOR_IMPLS["text_equality"](
            "Reject", "Send to Client", {"id": "text-1"}, spec=spec,
        )
        assert result is not None
        assert result.kind == "text_content_mismatch"
        assert "Reject" in result.error
        assert "Send to Client" in result.error

    def test_text_equality_handles_empty_strings(self):
        """Per Codex round-9: empty string must still compare. Two
        empty strings match (no error). Empty IR + non-empty rendered
        is a mismatch."""
        from dd.verify_figma import _COMPARATOR_IMPLS

        spec = self._make_spec("text_content_mismatch")
        # Empty == empty: match
        assert _COMPARATOR_IMPLS["text_equality"](
            "", "", {"id": "x"}, spec=spec,
        ) is None
        # Empty IR vs non-empty rendered: mismatch
        result = _COMPARATOR_IMPLS["text_equality"](
            "", "Hello", {"id": "x"}, spec=spec,
        )
        assert result is not None
        assert result.kind == "text_content_mismatch"

    def test_enum_equality_uses_spec_kind(self):
        """The enum_equality comparator is generic — same impl for
        layout_sizing_h and layout_sizing_v, with the kind driven
        by the spec."""
        from dd.property_registry import FigmaComparatorSpec
        from dd.verify_figma import _COMPARATOR_IMPLS

        spec_h = FigmaComparatorSpec(
            comparator="enum_equality",
            walker_key="layoutSizingHorizontal",
            kind="layout_sizing_h_mismatch",
        )
        result = _COMPARATOR_IMPLS["enum_equality"](
            "HUG", "FIXED", {"id": "f-1"}, spec=spec_h,
        )
        assert result is not None
        assert result.kind == "layout_sizing_h_mismatch"

        spec_v = FigmaComparatorSpec(
            comparator="enum_equality",
            walker_key="layoutSizingVertical",
            kind="layout_sizing_v_mismatch",
        )
        result = _COMPARATOR_IMPLS["enum_equality"](
            "FILL", "HUG", {"id": "f-1"}, spec=spec_v,
        )
        assert result is not None
        assert result.kind == "layout_sizing_v_mismatch"


# ---------------------------------------------------------------------
# C10 — IR value reader helper
# ---------------------------------------------------------------------


class TestIrValueForHelper:
    """The helper switch _ir_value_for(element, figma_name) reads the
    IR side of each graduated property, normalizing where necessary
    (e.g. layout sizing string + numeric → uppercase enum)."""

    def test_characters_reads_props_text(self):
        from dd.verify_figma import _ir_value_for

        element = {"type": "text", "props": {"text": "Reject"}}
        assert _ir_value_for(element, "characters") == "Reject"

    def test_characters_default_on_missing(self):
        from dd.verify_figma import _ir_value_for

        # No props: returns None (compare loop will skip)
        element = {"type": "text"}
        assert _ir_value_for(element, "characters") is None

    def test_layout_sizing_h_string_uppercased(self):
        """IR stores 'fill'/'hug' lowercase; walker emits uppercase.
        Helper normalizes IR side."""
        from dd.verify_figma import _ir_value_for

        element = {"layout": {"sizing": {"width": "hug"}}}
        assert _ir_value_for(element, "layoutSizingHorizontal") == "HUG"

    def test_layout_sizing_h_numeric_returns_fixed(self):
        """IR can have numeric width (pixels) when FIXED — helper
        returns 'FIXED' to match walker enum."""
        from dd.verify_figma import _ir_value_for

        element = {"layout": {"sizing": {"width": 100}}}
        assert _ir_value_for(element, "layoutSizingHorizontal") == "FIXED"

    def test_layout_sizing_v_returns_height(self):
        from dd.verify_figma import _ir_value_for

        element = {"layout": {"sizing": {"height": "fill"}}}
        assert _ir_value_for(element, "layoutSizingVertical") == "FILL"

    def test_layout_sizing_missing_returns_none(self):
        from dd.verify_figma import _ir_value_for

        element = {"type": "frame"}  # no layout
        assert _ir_value_for(element, "layoutSizingHorizontal") is None


# ---------------------------------------------------------------------
# C10 — end-to-end bug closure (HGB button scenario)
# ---------------------------------------------------------------------


class TestEndToEndBugClosure:
    """The user-observed bug closes here. Synthetic IR + rendered map
    that mimics the HGB button: source has TEXT="Reject" override on
    descendant; rendered output shows "Send to Client" (master default).

    Real-corpus validation is C11."""

    def test_text_content_mismatch_flagged_for_hgb_scenario(self):
        """End-to-end: build a minimal IR + rendered map matching the
        HGB button bug, run FigmaRenderVerifier, assert at least one
        KIND_TEXT_CONTENT_MISMATCH error."""
        from dd.verify_figma import FigmaRenderVerifier
        from dd.boundary import KIND_TEXT_CONTENT_MISMATCH

        # IR: a text element with characters=Reject and an _overrides
        # side-car that says "characters was overridden" — this is what
        # C9 produces from the descendant-path routing.
        spec = {
            "screen_id": 1,
            "screen_name": "test",
            "screen_type": "app_screen",
            "elements": {
                "text-1": {
                    "id": "text-1",
                    "type": "text",
                    "props": {"text": "Reject"},
                    "_overrides": ["characters"],  # C9 routed it here
                },
            },
            "tree": [{"id": "text-1", "children": []}],
        }
        # Rendered map: walker emitted envelope per C8 — but
        # the value is the master default, not the override.
        rendered_ref = {
            "rendered_root": "x",
            "rendered_root_width": 100,
            "rendered_root_height": 50,
            "eid_map": {
                "text-1": {
                    "type": "TEXT",
                    "name": "text-label",
                    "width": 100,
                    "height": 30,
                    "characters": {
                        "value": "Send to Client",
                        "source": "set",
                    },
                },
            },
        }

        report = FigmaRenderVerifier().verify(spec, rendered_ref)
        # The text content mismatch comparator must have fired
        kinds = [e.kind for e in report.errors]
        assert KIND_TEXT_CONTENT_MISMATCH in kinds, (
            f"expected KIND_TEXT_CONTENT_MISMATCH in errors; "
            f"got kinds={kinds}"
        )

    def test_text_content_match_no_error(self):
        """When IR text and rendered text agree, no error is emitted
        from the new comparator."""
        from dd.verify_figma import FigmaRenderVerifier
        from dd.boundary import KIND_TEXT_CONTENT_MISMATCH

        spec = {
            "screen_id": 1,
            "screen_name": "test",
            "screen_type": "app_screen",
            "elements": {
                "text-1": {
                    "id": "text-1",
                    "type": "text",
                    "props": {"text": "Submit"},
                    "_overrides": ["characters"],
                },
            },
            "tree": [{"id": "text-1", "children": []}],
        }
        rendered_ref = {
            "rendered_root": "x",
            "rendered_root_width": 100,
            "rendered_root_height": 50,
            "eid_map": {
                "text-1": {
                    "type": "TEXT",
                    "name": "label",
                    "width": 100,
                    "height": 30,
                    "characters": {
                        "value": "Submit",
                        "source": "set",
                    },
                },
            },
        }

        report = FigmaRenderVerifier().verify(spec, rendered_ref)
        kinds = [e.kind for e in report.errors]
        assert KIND_TEXT_CONTENT_MISMATCH not in kinds


class TestC5InventoryUpdated:
    """Per Codex round-9: graduating properties shifts station_4
    counts. C5 inventory + tests must reflect the new state."""

    def test_compare_dispatch_count_is_3(self):
        from collections import Counter
        from dd.property_registry import PROPERTIES

        counts = Counter(p.station_4.name for p in PROPERTIES)
        assert counts["COMPARE_DISPATCH"] == 3
        assert counts["COMPARE_DEDICATED"] == 14
        assert counts["EXEMPT_REASON"] == 36

    def test_3_graduations_are_the_expected_ones(self):
        from dd.property_registry import PROPERTIES, StationDisposition

        graduated = sorted(
            p.figma_name for p in PROPERTIES
            if p.station_4 == StationDisposition.COMPARE_DISPATCH
        )
        assert graduated == [
            "characters",
            "layoutSizingHorizontal",
            "layoutSizingVertical",
        ]
