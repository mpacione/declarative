"""Sprint 2 C5 — inventory all FigmaProperty entries at all four stations.

Per docs/plan-sprint-2-station-parity.md §3 (station model) and §8 commit
ladder: C5 wires real station_2/3/4 dispositions on every FigmaProperty.

This is the audit-table commit. Every figma-emittable property has a
known disposition at every station. Tests assert the known-correct
ground truth derived from:

  Station 2 (renderer):
    - emit={"figma": HANDLER}      → EMIT_HANDLER
    - emit={"figma": _UNIFORM}     → EMIT_UNIFORM
    - emit={} or no figma key      → EMIT_DEFERRED (handled outside
                                     _emit_visual, e.g. visible / size /
                                     characters / fontFamily / constraints)

  Station 3 (walker, render_test/walk_ref.js audit 2026-04-27):
    - top-level entry.* fields     → DEDICATED_PATH
                                     (width, height, name, type, x, y, rotation)
    - explicit entry.<figma_name>  → CAPTURED
                                     (opacity, blendMode, isMask,
                                      cornerRadius, strokeWeight,
                                      strokeAlign, dashPattern,
                                      clipsContent, characters,
                                      textAutoResize, fills, strokes)
    - count-only capture           → CAPTURED (effects → effectCount)
    - everything else              → NOT_CAPTURED_SUPPORTED
                                     (the inventory of Sprint 3+ work)

  Station 4 (verifier, dd/verify_figma.py KIND_* audit):
    - dedicated KIND_* path        → COMPARE_DEDICATED
                                     (bounds, fills, strokes, opacity,
                                      blendMode, rotation, isMask,
                                      cornerRadius, strokeWeight,
                                      strokeAlign, dashPattern,
                                      clipsContent, effects)
    - everything else              → EXEMPT_REASON
                                     (no comparator today; reason captured
                                      in test exemption table when graduated)

Sprint 2 graduates exactly 3 properties from EXEMPT_REASON to
COMPARE_DISPATCH (via C10): characters, layoutSizingHorizontal,
layoutSizingVertical. Per plan §7. The 3 graduations land in C8+C10,
not C5.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------
# Ground-truth disposition tables
# ---------------------------------------------------------------------

# Properties that should map to each station_2 status. Derived from
# auditing dd/property_registry.py emit={...} and the CLI codepaths.
_EXPECTED_STATION_2: dict[str, str] = {
    # === EMIT_HANDLER — custom Python emit fn ===
    "fills": "EMIT_HANDLER",
    "strokes": "EMIT_HANDLER",
    "effects": "EMIT_HANDLER",
    "clipsContent": "EMIT_HANDLER",
    "arcData": "EMIT_HANDLER",
    "cornerRadius": "EMIT_HANDLER",

    # === EMIT_UNIFORM — _UNIFORM template ===
    "strokeWeight": "EMIT_UNIFORM",
    "strokeAlign": "EMIT_UNIFORM",
    "strokeCap": "EMIT_UNIFORM",
    "strokeJoin": "EMIT_UNIFORM",
    "dashPattern": "EMIT_UNIFORM",
    "opacity": "EMIT_UNIFORM",
    "blendMode": "EMIT_UNIFORM",
    "rotation": "EMIT_UNIFORM",
    "isMask": "EMIT_UNIFORM",
    "cornerSmoothing": "EMIT_UNIFORM",
    "booleanOperation": "EMIT_UNIFORM",
    "layoutMode": "EMIT_UNIFORM",
    "primaryAxisAlignItems": "EMIT_UNIFORM",
    "counterAxisAlignItems": "EMIT_UNIFORM",
    "paddingTop": "EMIT_UNIFORM",
    "paddingRight": "EMIT_UNIFORM",
    "paddingBottom": "EMIT_UNIFORM",
    "paddingLeft": "EMIT_UNIFORM",
    "itemSpacing": "EMIT_UNIFORM",
    "counterAxisSpacing": "EMIT_UNIFORM",
    "layoutWrap": "EMIT_UNIFORM",
    "layoutPositioning": "EMIT_UNIFORM",
    "minWidth": "EMIT_UNIFORM",
    "maxWidth": "EMIT_UNIFORM",
    "minHeight": "EMIT_UNIFORM",
    "maxHeight": "EMIT_UNIFORM",
    "fontSize": "EMIT_UNIFORM",
    "fontStyle": "EMIT_UNIFORM",
    "textAlignHorizontal": "EMIT_UNIFORM",
    "textAlignVertical": "EMIT_UNIFORM",
    "textAutoResize": "EMIT_UNIFORM",
    "textDecoration": "EMIT_UNIFORM",
    "textCase": "EMIT_UNIFORM",
    "lineHeight": "EMIT_UNIFORM",
    "letterSpacing": "EMIT_UNIFORM",
    "paragraphSpacing": "EMIT_UNIFORM",
    "leadingTrim": "EMIT_UNIFORM",

    # === EMIT_DEFERRED — handled outside _emit_visual ===
    # Each comment documents WHY the property is not emitted via
    # the registry's emit= path.
    "visible": "EMIT_DEFERRED",  # element.visible structural skip in main loop
    "layoutSizingHorizontal": "EMIT_DEFERRED",  # main loop, conditional on parent auto-layout
    "layoutSizingVertical": "EMIT_DEFERRED",  # main loop, conditional on parent auto-layout
    "width": "EMIT_DEFERRED",  # resize() call in main loop
    "height": "EMIT_DEFERRED",  # resize() call in main loop
    "characters": "EMIT_DEFERRED",  # text-emission code path; not _emit_visual
    "fontFamily": "EMIT_DEFERRED",  # text-emission code path
    "fontWeight": "EMIT_DEFERRED",  # text-emission code path
    "constraints.horizontal": "EMIT_DEFERRED",  # constraint-emission code path
    "constraints.vertical": "EMIT_DEFERRED",  # constraint-emission code path
}


# Properties that should map to each station_3 status. Derived from
# auditing render_test/walk_ref.js (entry.* assignments) on 2026-04-27.
_EXPECTED_STATION_3: dict[str, str] = {
    # === DEDICATED_PATH — top-level entry fields ===
    "width": "DEDICATED_PATH",
    "height": "DEDICATED_PATH",
    "rotation": "DEDICATED_PATH",  # entry.rotation, not entry.<figma_name>

    # === CAPTURED — explicit entry.<figma_name> assignment ===
    "fills": "CAPTURED",
    "strokes": "CAPTURED",
    "strokeWeight": "CAPTURED",
    "strokeAlign": "CAPTURED",
    "dashPattern": "CAPTURED",
    "opacity": "CAPTURED",
    "blendMode": "CAPTURED",
    "isMask": "CAPTURED",
    "cornerRadius": "CAPTURED",
    "clipsContent": "CAPTURED",
    "characters": "CAPTURED",
    "textAutoResize": "CAPTURED",
    "effects": "CAPTURED",  # captured as effectCount (count only)

    # === NOT_CAPTURED_SUPPORTED — walker COULD but doesn't ===
    # The Sprint 3+ inventory. These all have Figma Plugin API
    # surface (`n.<figma_name>`) but walk_ref.js doesn't emit
    # a corresponding entry.<figma_name>.
    "strokeCap": "NOT_CAPTURED_SUPPORTED",
    "strokeJoin": "NOT_CAPTURED_SUPPORTED",
    "cornerSmoothing": "NOT_CAPTURED_SUPPORTED",
    "booleanOperation": "NOT_CAPTURED_SUPPORTED",
    "arcData": "NOT_CAPTURED_SUPPORTED",
    "visible": "NOT_CAPTURED_SUPPORTED",  # implicit via tree structure, not entry field
    "layoutSizingHorizontal": "NOT_CAPTURED_SUPPORTED",  # graduates in C8
    "layoutSizingVertical": "NOT_CAPTURED_SUPPORTED",  # graduates in C8
    "layoutMode": "NOT_CAPTURED_SUPPORTED",
    "primaryAxisAlignItems": "NOT_CAPTURED_SUPPORTED",
    "counterAxisAlignItems": "NOT_CAPTURED_SUPPORTED",
    "paddingTop": "NOT_CAPTURED_SUPPORTED",
    "paddingRight": "NOT_CAPTURED_SUPPORTED",
    "paddingBottom": "NOT_CAPTURED_SUPPORTED",
    "paddingLeft": "NOT_CAPTURED_SUPPORTED",
    "itemSpacing": "NOT_CAPTURED_SUPPORTED",
    "counterAxisSpacing": "NOT_CAPTURED_SUPPORTED",
    "layoutWrap": "NOT_CAPTURED_SUPPORTED",
    "layoutPositioning": "NOT_CAPTURED_SUPPORTED",
    "minWidth": "NOT_CAPTURED_SUPPORTED",
    "maxWidth": "NOT_CAPTURED_SUPPORTED",
    "minHeight": "NOT_CAPTURED_SUPPORTED",
    "maxHeight": "NOT_CAPTURED_SUPPORTED",
    "fontFamily": "NOT_CAPTURED_SUPPORTED",
    "fontWeight": "NOT_CAPTURED_SUPPORTED",
    "fontSize": "NOT_CAPTURED_SUPPORTED",
    "fontStyle": "NOT_CAPTURED_SUPPORTED",
    "textAlignHorizontal": "NOT_CAPTURED_SUPPORTED",
    "textAlignVertical": "NOT_CAPTURED_SUPPORTED",
    "textDecoration": "NOT_CAPTURED_SUPPORTED",
    "textCase": "NOT_CAPTURED_SUPPORTED",
    "lineHeight": "NOT_CAPTURED_SUPPORTED",
    "letterSpacing": "NOT_CAPTURED_SUPPORTED",
    "paragraphSpacing": "NOT_CAPTURED_SUPPORTED",
    "leadingTrim": "NOT_CAPTURED_SUPPORTED",
    "constraints.horizontal": "NOT_CAPTURED_SUPPORTED",
    "constraints.vertical": "NOT_CAPTURED_SUPPORTED",
}


# Properties that should map to each station_4 status. Derived from
# auditing dd/verify_figma.py KIND_* paths on 2026-04-27.
_EXPECTED_STATION_4: dict[str, str] = {
    # === COMPARE_DEDICATED — explicit KIND_* dedicated path ===
    "width": "COMPARE_DEDICATED",  # KIND_BOUNDS_MISMATCH
    "height": "COMPARE_DEDICATED",  # KIND_BOUNDS_MISMATCH
    "fills": "COMPARE_DEDICATED",  # KIND_FILL_MISMATCH
    "strokes": "COMPARE_DEDICATED",  # KIND_STROKE_MISMATCH
    "strokeWeight": "COMPARE_DEDICATED",  # KIND_STROKE_WEIGHT_MISMATCH
    "strokeAlign": "COMPARE_DEDICATED",  # KIND_STROKE_ALIGN_MISMATCH
    "dashPattern": "COMPARE_DEDICATED",  # KIND_DASH_PATTERN_MISMATCH
    "opacity": "COMPARE_DEDICATED",  # KIND_OPACITY_MISMATCH
    "blendMode": "COMPARE_DEDICATED",  # KIND_BLENDMODE_MISMATCH
    "rotation": "COMPARE_DEDICATED",  # KIND_ROTATION_MISMATCH
    "isMask": "COMPARE_DEDICATED",  # KIND_MASK_MISMATCH
    "cornerRadius": "COMPARE_DEDICATED",  # KIND_CORNERRADIUS_MISMATCH
    "clipsContent": "COMPARE_DEDICATED",  # KIND_CLIPS_CONTENT_MISMATCH
    "effects": "COMPARE_DEDICATED",  # KIND_EFFECT_MISSING (count)

    # === EXEMPT_REASON — no comparator today ===
    # Sprint 2 graduates 3 of these to COMPARE_DISPATCH via C10
    # (characters, layoutSizingHorizontal, layoutSizingVertical).
    # All others stay EXEMPT_REASON until their family sprint.
    "characters": "EXEMPT_REASON",  # graduates in C10
    "layoutSizingHorizontal": "EXEMPT_REASON",  # graduates in C10
    "layoutSizingVertical": "EXEMPT_REASON",  # graduates in C10
    "strokeCap": "EXEMPT_REASON",
    "strokeJoin": "EXEMPT_REASON",
    "cornerSmoothing": "EXEMPT_REASON",
    "booleanOperation": "EXEMPT_REASON",
    "arcData": "EXEMPT_REASON",
    "visible": "EXEMPT_REASON",  # structural-skip, not per-prop check
    "layoutMode": "EXEMPT_REASON",
    "primaryAxisAlignItems": "EXEMPT_REASON",
    "counterAxisAlignItems": "EXEMPT_REASON",
    "paddingTop": "EXEMPT_REASON",
    "paddingRight": "EXEMPT_REASON",
    "paddingBottom": "EXEMPT_REASON",
    "paddingLeft": "EXEMPT_REASON",
    "itemSpacing": "EXEMPT_REASON",
    "counterAxisSpacing": "EXEMPT_REASON",
    "layoutWrap": "EXEMPT_REASON",
    "layoutPositioning": "EXEMPT_REASON",
    "minWidth": "EXEMPT_REASON",
    "maxWidth": "EXEMPT_REASON",
    "minHeight": "EXEMPT_REASON",
    "maxHeight": "EXEMPT_REASON",
    "fontFamily": "EXEMPT_REASON",
    "fontWeight": "EXEMPT_REASON",
    "fontSize": "EXEMPT_REASON",
    "fontStyle": "EXEMPT_REASON",
    "textAlignHorizontal": "EXEMPT_REASON",
    "textAlignVertical": "EXEMPT_REASON",
    "textAutoResize": "EXEMPT_REASON",
    "textDecoration": "EXEMPT_REASON",
    "textCase": "EXEMPT_REASON",
    "lineHeight": "EXEMPT_REASON",
    "letterSpacing": "EXEMPT_REASON",
    "paragraphSpacing": "EXEMPT_REASON",
    "leadingTrim": "EXEMPT_REASON",
    "constraints.horizontal": "EXEMPT_REASON",
    "constraints.vertical": "EXEMPT_REASON",
}


# ---------------------------------------------------------------------
# C5 — inventory tests
# ---------------------------------------------------------------------


@pytest.fixture
def by_name():
    from dd.property_registry import PROPERTIES

    return {p.figma_name: p for p in PROPERTIES}


class TestStation2Inventory:
    """Every property's station_2 disposition matches the audit
    of its emit={...} contents."""

    def test_inventory_covers_every_property(self, by_name):
        """The expected table must cover every PROPERTIES entry —
        if a property is missing here, the inventory has drifted."""
        expected_names = set(_EXPECTED_STATION_2.keys())
        actual_names = set(by_name.keys())
        missing = actual_names - expected_names
        extra = expected_names - actual_names
        assert not missing, (
            f"properties in registry but missing from "
            f"_EXPECTED_STATION_2 inventory: {missing}"
        )
        assert not extra, (
            f"properties in _EXPECTED_STATION_2 but not in registry: {extra}"
        )

    @pytest.mark.parametrize("figma_name,expected", sorted(_EXPECTED_STATION_2.items()))
    def test_property_station_2_matches_audit(
        self, by_name, figma_name, expected,
    ):
        from dd.property_registry import StationDisposition

        prop = by_name[figma_name]
        actual = prop.station_2.name
        assert actual == expected, (
            f"{figma_name}: station_2 expected {expected}, got {actual}"
        )


class TestStation3Inventory:
    """Every property's station_3 disposition matches the audit
    of render_test/walk_ref.js."""

    def test_inventory_covers_every_property(self, by_name):
        expected_names = set(_EXPECTED_STATION_3.keys())
        actual_names = set(by_name.keys())
        assert not (actual_names - expected_names), (
            f"properties missing from _EXPECTED_STATION_3 inventory"
        )
        assert not (expected_names - actual_names), (
            f"_EXPECTED_STATION_3 has properties not in registry"
        )

    @pytest.mark.parametrize("figma_name,expected", sorted(_EXPECTED_STATION_3.items()))
    def test_property_station_3_matches_audit(
        self, by_name, figma_name, expected,
    ):
        prop = by_name[figma_name]
        actual = prop.station_3.name
        assert actual == expected, (
            f"{figma_name}: station_3 expected {expected}, got {actual}"
        )


class TestStation4Inventory:
    """Every property's station_4 disposition matches the audit
    of dd/verify_figma.py."""

    def test_inventory_covers_every_property(self, by_name):
        expected_names = set(_EXPECTED_STATION_4.keys())
        actual_names = set(by_name.keys())
        assert not (actual_names - expected_names)
        assert not (expected_names - actual_names)

    @pytest.mark.parametrize("figma_name,expected", sorted(_EXPECTED_STATION_4.items()))
    def test_property_station_4_matches_audit(
        self, by_name, figma_name, expected,
    ):
        prop = by_name[figma_name]
        actual = prop.station_4.name
        assert actual == expected, (
            f"{figma_name}: station_4 expected {expected}, got {actual}"
        )


# ---------------------------------------------------------------------
# C5 — inventory summary stats (the audit table reviewers want)
# ---------------------------------------------------------------------


class TestInventorySummary:
    """The audit table sprint reviewers see. Reflects current state
    of station coverage; updates as future sprints graduate
    families."""

    def test_station_2_distribution(self, by_name):
        """Renderer coverage: how many properties are emitted, by
        which mechanism. Today's expectation derived from C5 wiring."""
        from collections import Counter

        counts = Counter(prop.station_2.name for prop in by_name.values())
        # Document expected today (post-C5):
        assert counts["EMIT_HANDLER"] == 6
        assert counts["EMIT_UNIFORM"] == 37
        assert counts["EMIT_DEFERRED"] == 10
        assert counts["NOT_EMITTABLE"] == 0

    def test_station_3_distribution(self, by_name):
        """Walker coverage: the inventory's main finding — only
        16/53 properties have walker capture today (3 dedicated +
        13 captured). Sprint 3+ graduations will move properties
        from NOT_CAPTURED_SUPPORTED to CAPTURED."""
        from collections import Counter

        counts = Counter(prop.station_3.name for prop in by_name.values())
        assert counts["DEDICATED_PATH"] == 3  # width, height, rotation
        assert counts["CAPTURED"] == 13  # per-property entry.<name> captures
        assert counts["NOT_CAPTURED_SUPPORTED"] == 37
        assert counts["NOT_CAPTURED_UNSUPPORTED"] == 0

    def test_station_4_distribution(self, by_name):
        """Verifier coverage: today's hand-rolled comparators reach
        14 properties. Sprint 2 graduates 3 more via COMPARE_DISPATCH
        in C10. Future sprints graduate families."""
        from collections import Counter

        counts = Counter(prop.station_4.name for prop in by_name.values())
        assert counts["COMPARE_DEDICATED"] == 14  # bounds + visual props
        assert counts["COMPARE_DISPATCH"] == 0  # C10 will move 3 here
        assert counts["EXEMPT_REASON"] == 39

    def test_total_property_count_unchanged(self, by_name):
        """Sanity: C5 doesn't add or remove properties, only sets
        their dispositions."""
        assert len(by_name) == 53


class TestSprint2GraduationCandidates:
    """The 3 properties Sprint 2 graduates (per plan §7) MUST be in
    EXEMPT_REASON post-C5 — that's how C10 knows what to move to
    COMPARE_DISPATCH."""

    @pytest.mark.parametrize(
        "figma_name",
        ["characters", "layoutSizingHorizontal", "layoutSizingVertical"],
    )
    def test_sprint_2_graduation_candidate_starts_exempt(
        self, by_name, figma_name,
    ):
        from dd.property_registry import StationDisposition

        prop = by_name[figma_name]
        assert prop.station_4 == StationDisposition.EXEMPT_REASON, (
            f"{figma_name}: Sprint 2 graduation candidate must start "
            f"as EXEMPT_REASON (post-C5); got {prop.station_4}"
        )

    def test_graduation_candidates_have_walker_capture_or_dedicated(self, by_name):
        """Pre-graduation invariant: a property can't graduate to
        COMPARE_DISPATCH (C10) unless its walker capture is in place.
        characters is captured today; layoutSizingH/V need walker
        capture added in C8."""
        from dd.property_registry import StationDisposition

        # characters: walker captures today
        chars = by_name["characters"]
        assert chars.station_3 == StationDisposition.CAPTURED

        # layoutSizingH/V: NOT captured today, need C8
        for name in ("layoutSizingHorizontal", "layoutSizingVertical"):
            prop = by_name[name]
            assert prop.station_3 == StationDisposition.NOT_CAPTURED_SUPPORTED, (
                f"{name}: still NOT_CAPTURED_SUPPORTED post-C5; "
                f"C8 will graduate to CAPTURED, then C10 to COMPARE_DISPATCH"
            )


# ---------------------------------------------------------------------
# C5 — _apply_inventory defensive contract
# ---------------------------------------------------------------------


class TestApplyInventoryRaisesOnMissingDisposition:
    """Per Sonnet review: _apply_inventory should raise RuntimeError
    if a property is missing from any inventory dict. Catches the
    failure mode where someone adds a property to PROPERTIES but
    forgets to wire its station_2/3/4 dispositions."""

    def test_missing_from_all_inventories_raises(self):
        from dd.property_registry import FigmaProperty, _apply_inventory

        # Construct a property NOT in any inventory dict
        rogue = FigmaProperty(figma_name="zzz_rogue_property",
                              db_column=None)
        with pytest.raises(RuntimeError) as exc_info:
            _apply_inventory((rogue,))
        msg = str(exc_info.value)
        assert "zzz_rogue_property" in msg
        # All three stations should be flagged as missing
        assert "station_2" in msg
        assert "station_3" in msg
        assert "station_4" in msg

    def test_missing_from_one_inventory_raises(self, monkeypatch):
        from dd.property_registry import (
            FigmaProperty, StationDisposition, _apply_inventory,
            _STATION_2_INVENTORY, _STATION_3_INVENTORY,
        )

        # Construct a property present in stations 2 and 3 but NOT 4
        partial = FigmaProperty(figma_name="zzz_partial",
                                db_column=None)
        monkeypatch.setitem(_STATION_2_INVENTORY, "zzz_partial",
                            StationDisposition.NOT_EMITTABLE)
        monkeypatch.setitem(_STATION_3_INVENTORY, "zzz_partial",
                            StationDisposition.NOT_CAPTURED_SUPPORTED)
        # _STATION_4_INVENTORY deliberately not patched — should fail

        with pytest.raises(RuntimeError) as exc_info:
            _apply_inventory((partial,))
        msg = str(exc_info.value)
        assert "zzz_partial" in msg
        assert "station_4" in msg
        # Station 2 and 3 should NOT be in the missing list
        assert "station_2" not in msg
        assert "station_3" not in msg
