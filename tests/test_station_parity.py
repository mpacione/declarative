"""Sprint 2 — registry-driven station parity.

The architecture: every figma-emittable property has a known
disposition at every pipeline station (Registry / Renderer /
Walker / Verifier). The registry is the single source of truth;
generated artifacts (walker manifest) derive from it.

This module tests Sprint-2 deliverables, organized by the
``StationDisposition`` per-station status.

## Sprint 2 commit ladder (per docs/plan-sprint-2-station-parity.md)

  C4  Add station-disposition schema to FigmaProperty (THIS COMMIT)
  C5  Inventory all properties at all four stations
  C6  Walker manifest generator + validation test
  C7  Plugin-init manifest injection + read path
  C8  Walker capture (value, source) for graduated properties
  C9  A1.1 descendant-path routing fix
  C10 Verifier registry-dispatch for graduated properties
  C11 All-corpus regression sweep + sprint results

C4 ships:
  - StationDisposition enum (Station 2/3/4 status vocabulary)
  - station_2, station_3, station_4 fields on FigmaProperty
  - Default values that preserve current behavior on every
    existing property (no inventory, just schema)

Per Codex 5.5 round-5 architectural call: dispositions live on
FigmaProperty (single source of truth), NOT a separate manifest.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------
# C4 — StationDisposition enum exists with the right vocabulary
# ---------------------------------------------------------------------


class TestStationDispositionEnum:
    """Per docs/plan-sprint-2-station-parity.md §4 (locked):

    Station 2 (renderer):
      EMIT_HANDLER         — custom Python emit fn
      EMIT_UNIFORM         — _UNIFORM template
      EMIT_DEFERRED        — capability or context skip
      NOT_EMITTABLE        — capability gate excludes always

    Station 3 (walker):
      CAPTURED                  — walker reads it
      NOT_CAPTURED_SUPPORTED    — walker COULD but doesn't
      NOT_CAPTURED_UNSUPPORTED  — Figma DOM doesn't expose
      DEDICATED_PATH            — captured via top-level fields,
                                  not figma_name (e.g. width/height)

    Station 4 (verifier):
      COMPARE_DISPATCH     — via compare_figma in registry
      COMPARE_DEDICATED    — via KIND_BOUNDS_MISMATCH etc
      EXEMPT_REASON        — documented exemption with reason code
    """

    def test_station_disposition_enum_importable(self):
        from dd.property_registry import StationDisposition  # noqa: F401

    def test_station_2_renderer_dispositions(self):
        from dd.property_registry import StationDisposition

        # Station 2 vocabulary
        assert StationDisposition.EMIT_HANDLER
        assert StationDisposition.EMIT_UNIFORM
        assert StationDisposition.EMIT_DEFERRED
        assert StationDisposition.NOT_EMITTABLE

    def test_station_3_walker_dispositions(self):
        from dd.property_registry import StationDisposition

        assert StationDisposition.CAPTURED
        assert StationDisposition.NOT_CAPTURED_SUPPORTED
        assert StationDisposition.NOT_CAPTURED_UNSUPPORTED
        assert StationDisposition.DEDICATED_PATH

    def test_station_4_verifier_dispositions(self):
        from dd.property_registry import StationDisposition

        assert StationDisposition.COMPARE_DISPATCH
        assert StationDisposition.COMPARE_DEDICATED
        assert StationDisposition.EXEMPT_REASON

    def test_disposition_values_are_strings(self):
        """Values used in serialized walker-manifest JSON; must be
        strings not auto-int."""
        from dd.property_registry import StationDisposition

        assert isinstance(StationDisposition.EMIT_HANDLER.value, str)
        assert isinstance(StationDisposition.CAPTURED.value, str)
        assert isinstance(StationDisposition.COMPARE_DISPATCH.value, str)


# ---------------------------------------------------------------------
# C4 — FigmaProperty grows station_2/3/4 fields with safe defaults
# ---------------------------------------------------------------------


class TestFigmaPropertyStationFields:
    """C4 adds three new fields to FigmaProperty. Defaults are
    chosen so no existing property's behavior changes:

      station_2 = NOT_EMITTABLE
        (overridden by C5 inventory based on emit= dict)
      station_3 = NOT_CAPTURED_SUPPORTED
        (overridden by C5 inventory based on walk_ref.js audit)
      station_4 = EXEMPT_REASON
        (overridden by C5 inventory based on compare_figma /
         dedicated paths)

    C5 then wires the real dispositions per property.
    """

    def test_figma_property_has_station_2_field(self):
        from dd.property_registry import FigmaProperty, StationDisposition

        prop = FigmaProperty(figma_name="x", db_column=None)
        assert hasattr(prop, "station_2")
        assert prop.station_2 == StationDisposition.NOT_EMITTABLE

    def test_figma_property_has_station_3_field(self):
        from dd.property_registry import FigmaProperty, StationDisposition

        prop = FigmaProperty(figma_name="x", db_column=None)
        assert hasattr(prop, "station_3")
        assert prop.station_3 == StationDisposition.NOT_CAPTURED_SUPPORTED

    def test_figma_property_has_station_4_field(self):
        from dd.property_registry import FigmaProperty, StationDisposition

        prop = FigmaProperty(figma_name="x", db_column=None)
        assert hasattr(prop, "station_4")
        assert prop.station_4 == StationDisposition.EXEMPT_REASON

    def test_station_fields_settable_at_construction(self):
        from dd.property_registry import FigmaProperty, StationDisposition

        prop = FigmaProperty(
            figma_name="characters",
            db_column="text_content",
            station_2=StationDisposition.EMIT_HANDLER,
            station_3=StationDisposition.CAPTURED,
            station_4=StationDisposition.COMPARE_DISPATCH,
        )
        assert prop.station_2 == StationDisposition.EMIT_HANDLER
        assert prop.station_3 == StationDisposition.CAPTURED
        assert prop.station_4 == StationDisposition.COMPARE_DISPATCH

    def test_station_fields_are_frozen(self):
        """Like the rest of FigmaProperty — declarative, immutable."""
        from dd.property_registry import FigmaProperty, StationDisposition

        prop = FigmaProperty(figma_name="x", db_column=None)
        with pytest.raises(Exception):  # FrozenInstanceError
            prop.station_2 = StationDisposition.EMIT_HANDLER  # type: ignore[misc]

    def test_no_property_loses_existing_attributes(self):
        """C4 is purely additive — every existing FigmaProperty
        attribute (figma_name, capabilities, emit, etc.) still
        works."""
        from dd.property_registry import PROPERTIES

        for prop in PROPERTIES:
            assert hasattr(prop, "figma_name")
            assert hasattr(prop, "capabilities")
            assert hasattr(prop, "emit")
            assert hasattr(prop, "category")
            # And the new ones
            assert hasattr(prop, "station_2")
            assert hasattr(prop, "station_3")
            assert hasattr(prop, "station_4")


# ---------------------------------------------------------------------
# C4 — schema defaults still verifiable on a fresh property
# ---------------------------------------------------------------------
# (Pre-C5 these tests asserted defaults across PROPERTIES. Post-C5
# the registry's _apply_inventory replaces every property with real
# dispositions, so the per-PROPERTIES default assertion no longer
# holds. The C4-shape contract is now: a freshly-constructed
# FigmaProperty (no inventory applied) has the documented defaults.)


class TestC4DefaultsForFreshProperty:
    """C4's contract: a fresh FigmaProperty (not in PROPERTIES) gets
    the safe default dispositions. C5's _apply_inventory then
    replaces every property in PROPERTIES with a dispositioned copy
    (see tests/test_station_inventory.py for the per-property
    coverage)."""

    def test_fresh_property_default_station_2(self):
        from dd.property_registry import FigmaProperty, StationDisposition

        prop = FigmaProperty(figma_name="freshly_constructed", db_column=None)
        assert prop.station_2 == StationDisposition.NOT_EMITTABLE

    def test_fresh_property_default_station_3(self):
        from dd.property_registry import FigmaProperty, StationDisposition

        prop = FigmaProperty(figma_name="freshly_constructed", db_column=None)
        assert prop.station_3 == StationDisposition.NOT_CAPTURED_SUPPORTED

    def test_fresh_property_default_station_4(self):
        from dd.property_registry import FigmaProperty, StationDisposition

        prop = FigmaProperty(figma_name="freshly_constructed", db_column=None)
        assert prop.station_4 == StationDisposition.EXEMPT_REASON
