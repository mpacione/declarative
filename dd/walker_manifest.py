"""Sprint 2 C6 — registry → JSON manifest the walker reads at plugin init (C7).

Per docs/plan-sprint-2-station-parity.md §5 (registry authority): the
property registry is the single source of truth. Generated artifacts (this
walker manifest JSON) derive from it. Drift is caught by a test that
diff-checks the generated artifact against the in-memory build.

Single source of truth: dd/property_registry.py PROPERTIES.

The manifest is consumed by the walker (render_test/walk_ref.js) at
plugin init in C7. C8 then graduates three properties
(characters, layoutSizingHorizontal, layoutSizingVertical) to the
``value_source`` envelope; everything else stays ``raw``.

CLI usage::

    python -m dd.walker_manifest

Writes the JSON artifact at render_test/walker_manifest.generated.json.
Output is deterministic (sorted keys, no timestamp).
"""

from __future__ import annotations

import json
from pathlib import Path

from dd.property_registry import PROPERTIES, FigmaProperty


MANIFEST_VERSION = "1.0"


# Per docs/plan-sprint-2-station-parity.md §7: Sprint 2 graduates exactly
# these three properties. Their walker entries get the ``value_source``
# envelope so C8 can attach (value, source) tuples. All other properties
# get the ``raw`` envelope (today's behavior).
_VALUE_SOURCE_GRADUATIONS = frozenset({
    "characters",
    "layoutSizingHorizontal",
    "layoutSizingVertical",
})


def _capability_node_types(prop: FigmaProperty) -> list[str]:
    """Return the sorted list of Figma node types a property is capable on.

    Returns ``[]`` if the property has no ``capabilities["figma"]`` entry.
    Defensive: never crashes on missing capability data.
    """
    figma_caps = prop.capabilities.get("figma")
    if figma_caps is None:
        return []
    return sorted(figma_caps)


def _envelope_for(figma_name: str) -> str:
    """Return the walker capture envelope for a property.

    ``"value_source"`` for the three Sprint 2 graduations,
    ``"raw"`` for everything else (today's behavior).
    """
    if figma_name in _VALUE_SOURCE_GRADUATIONS:
        return "value_source"
    return "raw"


def _entry_for(prop: FigmaProperty) -> dict:
    """Build the manifest entry for a single property.

    Schema fields (locked by Codex 5.5 — see C6 brief):
    ``figma_name``, ``capability_node_types``, ``station_2``,
    ``station_3``, ``station_4``, ``envelope``, ``handler``.
    """
    return {
        "figma_name": prop.figma_name,
        "capability_node_types": _capability_node_types(prop),
        "station_2": prop.station_2.name,
        "station_3": prop.station_3.name,
        "station_4": prop.station_4.name,
        "envelope": _envelope_for(prop.figma_name),
        "handler": {
            "kind": "default_property",
            "property": prop.figma_name,
        },
    }


def build_walker_manifest() -> dict:
    """Build the JSON-serializable manifest from the registry.

    Pure function: never writes files. The CLI ``__main__`` block
    handles the write path.

    Output shape::

        {
          "version": "1.0",
          "properties": {
            "<figma_name>": {<entry>},
            ...
          }
        }

    ``properties`` is keyed by ``figma_name`` and (post-``json.dump``
    with ``sort_keys=True``) emitted in alphabetical order.
    """
    properties: dict[str, dict] = {}
    for prop in PROPERTIES:
        properties[prop.figma_name] = _entry_for(prop)
    return {
        "version": MANIFEST_VERSION,
        "properties": properties,
    }


def _artifact_path() -> Path:
    """Path to the generated JSON artifact, resolved from this file."""
    return Path(__file__).parent.parent / "render_test" / "walker_manifest.generated.json"


def _write_artifact() -> Path:
    """Write the manifest to render_test/walker_manifest.generated.json.

    Pretty-printed with ``indent=2``, ``sort_keys=True``, trailing
    newline. Deterministic across runs.
    """
    manifest = build_walker_manifest()
    out_path = _artifact_path()
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return out_path


if __name__ == "__main__":
    path = _write_artifact()
    print(f"wrote {path}")
