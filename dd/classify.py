"""Component classification cascade (T5 Phase 1 + M7.0.a three-source).

Classifies nodes against the component_type_catalog using:
  Step 1: Formal component matching (name/alias lookup)
  Step 2: Structural heuristics (position, layout, text patterns)
  Step 3: LLM fallback
  Step 4: Vision cross-validation — two variants under M7.0.a:
          (a) legacy `cross_validate_vision` — single-source vision
              on low-confidence rows;
          (b) three-source (PS + CS) when `three_source=True` in
              `run_classification`. Per-source verdicts are persisted
              and `apply_consensus_to_screen` computes a consensus
              canonical_type via rule v1.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from typing import Any

from dd.catalog import get_catalog
from dd.classify_consensus import compute_consensus_v1, compute_consensus_v2
from dd.classify_rules import is_system_chrome, parse_component_name


def build_alias_index(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Build a lookup dict mapping prefixes and aliases to catalog entries.

    Returns dict where keys are lowercase names/aliases and values are
    dicts with catalog_type_id, canonical_name, and category.
    """
    catalog = get_catalog(conn)
    index: dict[str, dict[str, Any]] = {}

    for entry in catalog:
        record = {
            "catalog_type_id": entry["id"],
            "canonical_name": entry["canonical_name"],
            "category": entry["category"],
        }

        index[entry["canonical_name"]] = record

        if entry.get("aliases"):
            for alias in entry["aliases"]:
                index[alias.lower()] = record

    return index


def _ckr_name_lookup(conn: sqlite3.Connection) -> dict[str, str]:
    """Build a ``component_key → registered_name`` map from CKR.

    When an INSTANCE node's own ``name`` is designer-overridden and
    doesn't match any canonical type, we fall back to the master
    component's registered name via the node's ``component_key``.
    The registered name typically carries a canonical path
    (``button/primary/lg``) which `parse_component_name` resolves
    longest-first against the alias index.

    Returns an empty map when CKR doesn't exist (pre-CKR corpus /
    fresh test DB). Callers treat missing entries as "no CKR signal,
    fall through to LLM stage."
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='component_key_registry'"
    ).fetchone()
    if not exists:
        return {}
    rows = conn.execute(
        "SELECT component_key, name FROM component_key_registry"
    ).fetchall()
    return {ck: nm for ck, nm in rows}


def classify_formal(conn: sqlite3.Connection, screen_id: int) -> dict[str, Any]:
    """Step 1: Classify nodes by matching against the catalog.

    Two paths, checked in order:

    1. **Node name** — the node's own ``name`` field, split by ``/``
       and resolved longest-first against the alias index. Handles
       the common case where the designer did not override the
       master component's name on the instance.
    2. **CKR fallback** — the master component's registered name
       looked up via ``nodes.component_key`` ↔ ``component_key_registry.
       component_key``. Handles designer-overridden instance names
       (``"Call to Action"`` for a ``button/primary/lg`` instance,
       etc.). Archived T5 plan specified this; previously missing.

    Processes INSTANCE / FRAME / COMPONENT nodes that aren't already
    classified. Uses INSERT OR IGNORE so re-runs are idempotent.
    Returns dict with classified count.
    """
    alias_index = build_alias_index(conn)
    ckr_names = _ckr_name_lookup(conn)

    cursor = conn.execute(
        "SELECT n.id, n.name, n.node_type, n.component_key "
        "FROM nodes n "
        "LEFT JOIN screen_component_instances sci "
        "  ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
        "WHERE n.screen_id = ? "
        "  AND n.node_type IN ('INSTANCE', 'FRAME', 'COMPONENT') "
        "  AND sci.id IS NULL",
        (screen_id,),
    )
    nodes = cursor.fetchall()

    inserts = []
    for node_id, name, node_type, component_key in nodes:
        if is_system_chrome(name):
            continue

        # Path 1: node name lookup.
        match = None
        for candidate in parse_component_name(name):
            match = alias_index.get(candidate)
            if match is not None:
                break

        # Path 2: CKR fallback when name didn't match. Uses the master
        # component's registered name from `component_key_registry`.
        if match is None and component_key:
            ckr_name = ckr_names.get(component_key)
            if ckr_name:
                for candidate in parse_component_name(ckr_name):
                    match = alias_index.get(candidate)
                    if match is not None:
                        break

        if match is None:
            continue

        inserts.append((
            screen_id,
            node_id,
            match["catalog_type_id"],
            match["canonical_name"],
            1.0,
            "formal",
        ))

    if inserts:
        conn.executemany(
            "INSERT OR IGNORE INTO screen_component_instances "
            "(screen_id, node_id, catalog_type_id, canonical_type, confidence, classification_source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            inserts,
        )
        conn.commit()

    return {"classified": len(inserts)}


def link_parent_instances(conn: sqlite3.Connection, screen_id: int) -> dict[str, Any]:
    """Set parent_instance_id for nested classified instances.

    For each classified instance, walks up the node tree via parent_id
    to find the nearest ancestor that is also a classified instance.
    """
    # Get all classified instances for this screen, keyed by node_id
    cursor = conn.execute(
        "SELECT sci.id, sci.node_id "
        "FROM screen_component_instances sci "
        "WHERE sci.screen_id = ?",
        (screen_id,),
    )
    instance_by_node: dict[int, int] = {}
    for sci_id, node_id in cursor.fetchall():
        instance_by_node[node_id] = sci_id

    # Build parent_id map for all nodes in this screen
    cursor = conn.execute(
        "SELECT id, parent_id FROM nodes WHERE screen_id = ?",
        (screen_id,),
    )
    node_parent: dict[int, int | None] = {}
    for node_id, parent_id in cursor.fetchall():
        node_parent[node_id] = parent_id

    # For each classified instance, walk up to find nearest classified ancestor
    updates = []
    for node_id, sci_id in instance_by_node.items():
        ancestor_node = node_parent.get(node_id)
        parent_sci_id = None

        while ancestor_node is not None:
            if ancestor_node in instance_by_node:
                parent_sci_id = instance_by_node[ancestor_node]
                break
            ancestor_node = node_parent.get(ancestor_node)

        if parent_sci_id is not None:
            updates.append((parent_sci_id, sci_id))

    if updates:
        conn.executemany(
            "UPDATE screen_component_instances SET parent_instance_id = ? WHERE id = ?",
            updates,
        )
        conn.commit()

    return {"linked": len(updates)}


def truncate_classifications(conn: sqlite3.Connection) -> dict[str, int]:
    """Delete every row from classification result tables.

    Used by M7.0.a's full-cascade rerun (decision: ``(b) truncate
    + full cascade rerun`` in the 2026-04-19 session). Leaves
    ``component_type_catalog`` and ``component_key_registry``
    intact — those are the vocabulary + master index, not
    classifications.

    Returns a dict reporting how many rows were deleted per table.
    """
    before_instances = conn.execute(
        "SELECT COUNT(*) FROM screen_component_instances"
    ).fetchone()[0]
    before_skeletons = conn.execute(
        "SELECT COUNT(*) FROM screen_skeletons"
    ).fetchone()[0]
    conn.execute("DELETE FROM screen_component_instances")
    conn.execute("DELETE FROM screen_skeletons")
    conn.commit()
    return {
        "instances_deleted": before_instances,
        "skeletons_deleted": before_skeletons,
    }


# ---------------------------------------------------------------------------
# Three-source cascade helpers (M7.0.a)
# ---------------------------------------------------------------------------
# The three-source cascade persists LLM + vision_ps + vision_cs
# verdicts independently; consensus is a computed value that rule-v2
# iteration can recompute without re-classifying. `apply_consensus_to_screen`
# walks every row on the screen and writes canonical_type +
# consensus_method + flagged_for_review from the persisted sources.
# `apply_vision_ps_results` / `apply_vision_cs_results` unpack the
# output of `dd.classify_vision_batched.classify_batch` into the
# per-source columns.


def apply_vision_ps_results(
    conn: sqlite3.Connection,
    results: Iterable[dict[str, Any]],
) -> dict[str, int]:
    """Write vision per-screen verdicts to `vision_ps_*` columns.

    Rows that don't match an existing (screen_id, node_id) are
    silently skipped — the orchestrator runs vision PS against rows
    LLM classified, so phantom rows shouldn't happen; but a defensive
    no-op keeps pipeline robustness aligned with ADR-007 (failures
    surface via the verification channel, not a crash).
    """
    applied = 0
    for r in results:
        ctype = r.get("canonical_type")
        if not isinstance(ctype, str):
            continue
        screen_id = r.get("screen_id")
        node_id = r.get("node_id")
        confidence = r.get("confidence")
        reason = r.get("reason")
        cursor = conn.execute(
            "UPDATE screen_component_instances "
            "SET vision_ps_type = ?, vision_ps_confidence = ?, "
            "    vision_ps_reason = ? "
            "WHERE screen_id = ? AND node_id = ?",
            (
                ctype,
                float(confidence) if confidence is not None else None,
                reason if isinstance(reason, str) else None,
                screen_id, node_id,
            ),
        )
        if cursor.rowcount:
            applied += 1
    conn.commit()
    return {"applied": applied}


def apply_vision_cs_results(
    conn: sqlite3.Connection,
    results: Iterable[dict[str, Any]],
) -> dict[str, int]:
    """Write vision cross-screen verdicts to `vision_cs_*` columns,
    serialising the optional `cross_screen_evidence` array to
    `vision_cs_evidence_json`. Missing evidence leaves the column NULL.
    """
    applied = 0
    for r in results:
        ctype = r.get("canonical_type")
        if not isinstance(ctype, str):
            continue
        screen_id = r.get("screen_id")
        node_id = r.get("node_id")
        confidence = r.get("confidence")
        reason = r.get("reason")
        evidence = r.get("cross_screen_evidence")
        evidence_json = (
            json.dumps(evidence) if isinstance(evidence, list) and evidence
            else None
        )
        cursor = conn.execute(
            "UPDATE screen_component_instances "
            "SET vision_cs_type = ?, vision_cs_confidence = ?, "
            "    vision_cs_reason = ?, vision_cs_evidence_json = ? "
            "WHERE screen_id = ? AND node_id = ?",
            (
                ctype,
                float(confidence) if confidence is not None else None,
                reason if isinstance(reason, str) else None,
                evidence_json,
                screen_id, node_id,
            ),
        )
        if cursor.rowcount:
            applied += 1
    conn.commit()
    return {"applied": applied}


def apply_consensus_to_screen(
    conn: sqlite3.Connection,
    screen_id: int,
    *,
    rule: str = "v2",
) -> dict[str, int]:
    """Walk every row on the screen and compute consensus.

    Rows classified by formal / heuristic bypass voting — those
    sources are trusted at confidence 1.0 / 0.x. `consensus_method`
    for them is set to their `classification_source` and
    `flagged_for_review` to 0. `canonical_type` is preserved.

    Rows classified by `llm` enter three-source voting. ``rule`` selects
    ``v1`` (plain majority, conservative) or ``v2`` (weighted — CS gets
    2x vote based on empirical accuracy). v2 is the default after the
    2026-04-20 full-corpus analysis showed +6.4 pts lift on user-review
    match. The LLM's original verdict is read from ``llm_type``
    (preserved in migration 015) — NOT from canonical_type, which
    consensus overwrites on this same update. Vision sources contribute
    their ``vision_ps_type`` + ``vision_cs_type``. The final
    canonical_type, consensus_method, and flag are written in a
    single UPDATE.

    Returns a count summary per consensus_method so callers (CLI +
    orchestrator) can print a progress line.
    """
    if rule == "v1":
        compute = compute_consensus_v1
    elif rule == "v2":
        compute = compute_consensus_v2
    else:
        raise ValueError(f"unknown consensus rule: {rule!r}")

    rows = conn.execute(
        "SELECT id, classification_source, canonical_type, "
        "       llm_type, vision_ps_type, vision_cs_type "
        "FROM screen_component_instances WHERE screen_id = ?",
        (screen_id,),
    ).fetchall()

    counts: dict[str, int] = {}
    for sci_id, source, canonical_type, llm_type, ps_type, cs_type in rows:
        if source in ("formal", "heuristic"):
            conn.execute(
                "UPDATE screen_component_instances "
                "SET consensus_method = ?, flagged_for_review = 0 "
                "WHERE id = ?",
                (source, sci_id),
            )
            counts[source] = counts.get(source, 0) + 1
            continue

        # LLM / manual rows go through voting. Prefer persisted
        # `llm_type` when present; fall back to canonical_type so rows
        # written before migration 015 still work.
        llm_verdict = llm_type if llm_type is not None else canonical_type
        result_type, method, flagged = compute(
            llm_verdict, ps_type, cs_type,
        )
        conn.execute(
            "UPDATE screen_component_instances "
            "SET canonical_type = ?, consensus_method = ?, "
            "    flagged_for_review = ? "
            "WHERE id = ?",
            (
                result_type if result_type is not None else "unsure",
                method,
                1 if flagged else 0,
                sci_id,
            ),
        )
        counts[method] = counts.get(method, 0) + 1

    conn.commit()
    return counts


def run_classification(
    conn: sqlite3.Connection,
    file_id: int,
    client: Any = None,
    file_key: str | None = None,
    fetch_screenshot: Any = None,
    since_screen_id: int | None = None,
    limit: int | None = None,
    progress_callback: Any = None,
    three_source: bool = False,
) -> dict[str, Any]:
    """Orchestrate the full classification cascade for all screens in a file.

    Runs: formal → heuristics → [LLM] → parent linkage → [vision] → skeleton.

    - LLM step runs only if ``client`` is provided.
    - Vision step runs only if ``client``, ``file_key``, and
      ``fetch_screenshot`` are provided.
    - Skips ``component_sheet`` screens.
    - ``since_screen_id``: crude resume — skip screens with id < this
      value. Combined with the existing per-row ``INSERT OR IGNORE``
      semantics, lets a crashed run pick up roughly where it left
      off without restarting from zero.
    - ``limit``: stop after processing this many screens. Useful for
      dry-runs (``--limit 1`` probes a single screen before
      committing token budget to the full corpus).
    - ``progress_callback(i, n, screen_id, per_screen_result)``:
      called after each screen completes. Used by the CLI to print
      per-screen progress + by a future checkpoint layer to persist
      run state.
    """
    from dd.classify_heuristics import classify_heuristics
    from dd.classify_skeleton import extract_skeleton

    query = (
        "SELECT id FROM screens WHERE file_id = ? "
        "AND (device_class IS NULL OR device_class != 'component_sheet')"
    )
    params: list[Any] = [file_id]
    if since_screen_id is not None:
        query += " AND id >= ?"
        params.append(since_screen_id)
    query += " ORDER BY id"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    cursor = conn.execute(query, params)
    screen_ids = [row[0] for row in cursor.fetchall()]

    total_formal = 0
    total_heuristic = 0
    total_llm = 0
    total_linked = 0
    total_vision = {"validated": 0, "agreed": 0, "disagreed": 0}
    total_vision_ps = 0
    total_vision_cs = 0
    consensus_counts: dict[str, int] = {}
    total_skeletons = 0

    n = len(screen_ids)
    for i, screen_id in enumerate(screen_ids, 1):
        per_screen: dict[str, Any] = {"screen_id": screen_id}

        formal_result = classify_formal(conn, screen_id)
        total_formal += formal_result["classified"]
        per_screen["formal"] = formal_result["classified"]

        heuristic_result = classify_heuristics(conn, screen_id)
        total_heuristic += heuristic_result["classified"]
        per_screen["heuristic"] = heuristic_result["classified"]

        if client is not None:
            from dd.classify_llm import classify_llm
            llm_result = classify_llm(conn, screen_id, client)
            total_llm += llm_result["classified"]
            per_screen["llm"] = llm_result["classified"]

        link_result = link_parent_instances(conn, screen_id)
        total_linked += link_result["linked"]
        per_screen["linked"] = link_result["linked"]

        vision_available = (
            client is not None
            and file_key is not None
            and fetch_screenshot is not None
        )

        if vision_available and not three_source:
            # Legacy single-source vision path: validates low-confidence
            # rows by re-classifying via screenshot + comparing to the
            # structural/LLM type. Writes vision_type + vision_agrees +
            # flagged_for_review only.
            from dd.classify_vision import cross_validate_vision
            vision_result = cross_validate_vision(
                conn, screen_id, file_key, client, fetch_screenshot,
            )
            total_vision["validated"] += vision_result["validated"]
            total_vision["agreed"] += vision_result["agreed"]
            total_vision["disagreed"] += vision_result["disagreed"]
            per_screen["vision"] = vision_result

        if three_source and vision_available:
            # Three-source mode: vision PS runs per-screen and writes
            # to vision_ps_* columns. Vision CS batched across screens
            # runs AFTER the per-screen loop. Consensus runs last.
            # `target_source="llm"` fetches the same candidate set
            # LLM classified — three sources independently vote on
            # the same rows.
            from dd.classify_vision_batched import classify_batch
            ps_results = classify_batch(
                conn, [screen_id], client,
                file_key, fetch_screenshot,
                target_source="llm",
            )
            ps_summary = apply_vision_ps_results(conn, ps_results)
            total_vision_ps += ps_summary["applied"]
            per_screen["vision_ps"] = ps_summary["applied"]

        skeleton_result = extract_skeleton(conn, screen_id)
        if skeleton_result is not None:
            total_skeletons += 1
            per_screen["skeleton"] = True

        if progress_callback is not None:
            progress_callback(i, n, screen_id, per_screen)

    if three_source:
        # Cross-screen vision: batched by (device_class, skeleton_type),
        # target 5 screens per call. Writes to vision_cs_* columns.
        # Safe to skip when vision isn't available — rows with only
        # llm_type set fall through to the consensus single_source
        # branch.
        if vision_available := (
            client is not None
            and file_key is not None
            and fetch_screenshot is not None
        ):
            from dd.classify_vision_batched import (
                classify_batch,
                group_screens_by_skeleton_and_device,
            )
            cs_batches = group_screens_by_skeleton_and_device(
                conn, screen_ids, target_batch_size=5,
            )
            for batch in cs_batches:
                cs_results = classify_batch(
                    conn, batch, client, file_key, fetch_screenshot,
                    target_source="llm",
                )
                cs_summary = apply_vision_cs_results(conn, cs_results)
                total_vision_cs += cs_summary["applied"]

        # Compute consensus for every screen, now that all three
        # source columns are populated wherever possible.
        for screen_id in screen_ids:
            counts = apply_consensus_to_screen(conn, screen_id)
            for k, v in counts.items():
                consensus_counts[k] = consensus_counts.get(k, 0) + v

    out: dict[str, Any] = {
        "screens_processed": len(screen_ids),
        "formal_classified": total_formal,
        "heuristic_classified": total_heuristic,
        "llm_classified": total_llm,
        "parent_links": total_linked,
        "vision": total_vision,
        "skeletons_generated": total_skeletons,
    }
    if three_source:
        out["vision_ps_applied"] = total_vision_ps
        out["vision_cs_applied"] = total_vision_cs
        out["consensus"] = consensus_counts
    return out
