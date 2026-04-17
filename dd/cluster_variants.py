"""Variant inducer — Stream B v0.1 (ADR-008 PR #1).

Cluster-then-label pipeline that learns per-(catalog_type, variant,
slot) → token bindings from the extracted corpus. Persisted to the
``variant_token_binding`` table for consumption by the ``ProjectCKRProvider``
at Mode-3 resolution time.

Algorithm for v0.1 (full implementation deferred; the shape of the
public API is fixed by ADR-008 and the contract tests):

1. For each catalog type with ≥ 5 classified instances in
   ``screen_component_instances``, collect a feature vector per instance
   (fill, stroke, radius, dimensions, icon-presence, adjacency).
2. K-means in OKLCH + normalised dimensions; silhouette score picks K.
3. For each cluster, send ≤ 10 rendered thumbnails plus adjacency
   context to Gemini 3.1 Pro via an injected ``vlm_call`` callable with
   a closed vocabulary of variant names.
4. Persist one row per (catalog_type, variant, slot) with the cluster's
   representative token value.

The v0.1 shell below implements the schema-level contract and the
unknown-label ``custom_N`` fallback path. The richer cluster-analysis
and VLM-prompting logic lands incrementally; tests pin the contract.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import Any


# Closed vocabulary from ADR-008. VLM labels not in this set persist as
# ``custom_N`` so the LLM generator retains them in prompt vocabulary.
STANDARD_VARIANTS = (
    "primary",
    "secondary",
    "destructive",
    "ghost",
    "link",
    "disabled",
)

# Slot names we attempt to bind tokens for at v0.1. Broader per-type slot
# grammars (Material's 6-slot list_item, card's new media/header split)
# are consumed by providers; the inducer focuses on the four high-value
# visual slots common to nearly every interactive type.
CORE_SLOTS = ("bg", "fg", "border", "radius")

VlmCall = Callable[[str, list[bytes]], dict[str, Any]]


def _collect_instances(
    conn: sqlite3.Connection, catalog_type: str,
) -> list[dict[str, Any]]:
    """Return feature-vector-ready dicts for every instance of a type.

    Joins ``screen_component_instances`` → ``nodes`` and pulls the
    columns needed to build a clustering feature vector. A type with
    no classified instances returns an empty list.
    """
    rows = conn.execute(
        "SELECT sci.node_id, n.width, n.height, n.corner_radius, "
        "       n.fills, n.strokes, n.effects "
        "FROM screen_component_instances sci "
        "JOIN nodes n ON n.id = sci.node_id "
        "WHERE sci.canonical_type = ?",
        (catalog_type,),
    ).fetchall()
    return [
        {
            "node_id": r[0],
            "width": r[1],
            "height": r[2],
            "corner_radius": r[3],
            "fills": r[4],
            "strokes": r[5],
            "effects": r[6],
        }
        for r in rows
    ]


def _cluster_and_label(
    instances: list[dict[str, Any]],
    vlm_call: VlmCall,
    catalog_type: str,
) -> list[dict[str, Any]]:
    """Return labelled clusters for a catalog type.

    v0.1 shell: treats all instances as a single cluster and calls the
    VLM once to label them. Per-feature k-means + silhouette lands
    alongside when real corpus coverage is wired up.

    Output shape per cluster dict:
    ``{"variant": str, "members": list[int], "representative_values": dict}``
    """
    if not instances:
        return []

    response = vlm_call(f"Label variant for {catalog_type}", [])
    raw_verdict = (response.get("verdict") or "unknown").lower()
    confidence = float(response.get("confidence", 0.5))

    if raw_verdict in STANDARD_VARIANTS:
        variant = raw_verdict
    else:
        variant = "custom_1"

    return [
        {
            "variant": variant,
            "confidence": confidence,
            "members": [inst["node_id"] for inst in instances],
            "source": "vlm" if raw_verdict != "unknown" else "cluster",
            "representative_values": {
                "bg": None,
                "fg": None,
                "border": None,
                "radius": None,
            },
        },
    ]


def _persist_bindings(
    conn: sqlite3.Connection,
    catalog_type: str,
    clusters: list[dict[str, Any]],
) -> int:
    """Write one row per (catalog_type, variant, slot) to
    ``variant_token_binding``. Returns the number of rows written."""
    written = 0
    for cluster in clusters:
        variant = cluster["variant"]
        confidence = cluster["confidence"]
        source = cluster["source"]
        values = cluster["representative_values"]
        for slot in CORE_SLOTS:
            conn.execute(
                "INSERT OR REPLACE INTO variant_token_binding "
                "(catalog_type, variant, slot, token_id, literal_value, "
                " confidence, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    catalog_type,
                    variant,
                    slot,
                    None,
                    json.dumps(values.get(slot)) if values.get(slot) else None,
                    confidence,
                    source,
                ),
            )
            written += 1
    conn.commit()
    return written


def induce_variants(
    conn: sqlite3.Connection,
    vlm_call: VlmCall,
    catalog_types: list[str] | None = None,
) -> dict[str, int]:
    """Induce variant bindings for each catalog type and persist.

    Returns a dict ``{catalog_type: rows_written}`` for every type that
    had at least one instance. Types below the 5-instance threshold are
    short-circuited — if there is nothing to cluster, a single
    ``custom_1`` placeholder row is still written so providers have a
    fallback binding shape (keeps the LLM vocabulary complete).
    """
    written: dict[str, int] = {}

    if catalog_types is None:
        rows = conn.execute(
            "SELECT DISTINCT canonical_type FROM screen_component_instances"
        ).fetchall()
        catalog_types = [r[0] for r in rows]
        if not catalog_types:
            # Empty SCI (classify stage hasn't run). Fall back to the full
            # catalog so every known type gets at least a custom_1
            # placeholder row — gives ProjectCKRProvider something to
            # query at Mode-3 resolution time.
            from dd.catalog import CATALOG_ENTRIES
            catalog_types = [entry["canonical_name"] for entry in CATALOG_ENTRIES]

    for catalog_type in catalog_types:
        instances = _collect_instances(conn, catalog_type)

        # Below-threshold types still produce a placeholder binding so
        # downstream consumers have a row to query.
        if len(instances) < 5:
            clusters = [
                {
                    "variant": "custom_1",
                    "confidence": 0.0,
                    "members": [inst["node_id"] for inst in instances],
                    "source": "cluster",
                    "representative_values": {slot: None for slot in CORE_SLOTS},
                },
            ]
        else:
            clusters = _cluster_and_label(instances, vlm_call, catalog_type)

        written[catalog_type] = _persist_bindings(conn, catalog_type, clusters)

    return written
