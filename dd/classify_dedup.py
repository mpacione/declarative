"""Structural-signature dedup for classifier v2.

Classifier v1 sends every unclassified node through LLM + vision
independently. With 6,233 LLM rows in the Dank corpus and strong
duplication (a given `Left` nav zone appears on 30+ iPad screens
with identical structure), that's 5-8x more API work than needed.

v2 clusters candidates by a structural signature BEFORE the API
call, classifies one representative per cluster, then propagates
the verdict to every sci row in the cluster.

The signature is a tuple chosen to be tight enough that two nodes
with identical signatures are genuinely the same pattern, and loose
enough that real duplicates dedup. Keys used:

- `name` — designer-assigned label. Very strong signal for Figma.
- `node_type` — FRAME / INSTANCE / COMPONENT.
- `parent_classified_as` — the parent's canonical_type (None if
  unclassified). Distinguishes "Left inside header" from "Left
  inside toolbar".
- `child_type_dist` — multiset of child node types (order ignored).
  Catches structural-shape differences.
- `sample_text` first 60 chars — first text child's content. Sample
  length > 60 is not load-bearing once the prefix matches.
- `component_key` — Figma master key (INSTANCE nodes). Two instances
  of different masters are never the same pattern regardless of
  displayed name.

None values in any position are normalised (None ≡ "") so
candidates with the same "nothing here" shape dedup.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any


def dedup_key(candidate: dict[str, Any]) -> tuple:
    """Build the structural-signature tuple for a classifier candidate.

    ``candidate`` is the same shape ``_fetch_unclassified_for_screen``
    emits: a dict with keys ``name``, ``node_type``,
    ``parent_classified_as``, ``child_type_dist``, ``sample_text``,
    ``component_key``. Missing keys are treated as None / empty.
    """
    name = candidate.get("name") or ""
    node_type = candidate.get("node_type") or ""
    parent_type = candidate.get("parent_classified_as") or ""
    children = candidate.get("child_type_dist") or {}
    sample_text = (candidate.get("sample_text") or "")[:60]
    component_key = candidate.get("component_key") or ""

    # Child-type distribution as a sorted tuple so dict insertion order
    # doesn't matter.
    children_tuple = tuple(sorted(children.items()))

    return (
        name,
        node_type,
        parent_type,
        children_tuple,
        sample_text,
        component_key,
    )


def group_candidates(
    candidates: list[dict[str, Any]],
) -> dict[tuple, list[dict[str, Any]]]:
    """Group candidates by `dedup_key`. First-seen candidate per group
    becomes the representative (stable across repeated runs).

    Returns an ``OrderedDict`` so iteration order matches candidate
    arrival order — lets a classify pass replay deterministically
    from the same input.
    """
    groups: OrderedDict[tuple, list[dict[str, Any]]] = OrderedDict()
    for c in candidates:
        key = dedup_key(c)
        groups.setdefault(key, []).append(c)
    return groups
