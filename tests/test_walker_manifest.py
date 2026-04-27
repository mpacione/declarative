"""Sprint 2 C6 — walker manifest generator tests.

Per docs/plan-sprint-2-station-parity.md §5 (registry authority): the
generated walker manifest MUST stay in lock-step with the registry.

Two responsibilities:
  1. ``TestWalkerManifestSchema`` — the in-memory build conforms to the
     locked schema (version, key set, envelope rules, station strings).
  2. ``TestWalkerManifestArtifactInSync`` — the on-disk JSON artifact
     equals the in-memory build. Failure means a registry change
     wasn't reflected; the message tells you how to regenerate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dd.property_registry import PROPERTIES
from dd.walker_manifest import build_walker_manifest


_ARTIFACT_PATH = (
    Path(__file__).parent.parent / "render_test" / "walker_manifest.generated.json"
)

# The 3 Sprint 2 graduations per plan §7 — these are the only properties
# whose walker entries get the value_source envelope. Everything else
# is raw (today's behavior).
_VALUE_SOURCE_GRADUATIONS = frozenset({
    "characters",
    "layoutSizingHorizontal",
    "layoutSizingVertical",
})


class TestWalkerManifestSchema:
    """Schema invariants of the in-memory build."""

    def test_version_is_1_0(self):
        manifest = build_walker_manifest()
        assert manifest["version"] == "1.0"

    def test_all_properties_present(self):
        manifest = build_walker_manifest()
        actual_names = set(manifest["properties"].keys())
        expected_names = {p.figma_name for p in PROPERTIES}
        assert actual_names == expected_names

    def test_value_source_envelope_only_for_graduations(self):
        manifest = build_walker_manifest()
        value_source_props = {
            name
            for name, entry in manifest["properties"].items()
            if entry["envelope"] == "value_source"
        }
        raw_props = {
            name
            for name, entry in manifest["properties"].items()
            if entry["envelope"] == "raw"
        }
        assert value_source_props == _VALUE_SOURCE_GRADUATIONS
        # Every property has exactly one of the two envelopes; together
        # they cover the full set.
        assert value_source_props | raw_props == set(manifest["properties"].keys())

    def test_capability_types_are_sorted(self):
        manifest = build_walker_manifest()
        for name, entry in manifest["properties"].items():
            types = entry["capability_node_types"]
            assert types == sorted(types), (
                f"{name}: capability_node_types not sorted: {types}"
            )

    def test_station_dispositions_are_strings(self):
        manifest = build_walker_manifest()
        for name, entry in manifest["properties"].items():
            for station_key in ("station_2", "station_3", "station_4"):
                value = entry[station_key]
                assert isinstance(value, str), (
                    f"{name}: {station_key} expected str, got {type(value).__name__}"
                )
                assert value, f"{name}: {station_key} must not be empty"


class TestWalkerManifestArtifactInSync:
    """The on-disk JSON artifact must equal the in-memory build."""

    def test_generated_artifact_matches_registry(self):
        in_memory = build_walker_manifest()
        disk_text = _ARTIFACT_PATH.read_text(encoding="utf-8")
        on_disk = json.loads(disk_text)
        assert on_disk == in_memory, (
            "render_test/walker_manifest.generated.json is out of sync "
            "with dd/property_registry.py — regenerate with "
            "`python -m dd.walker_manifest`"
        )
