"""Component classification cascade (T5 Phase 1).

Classifies nodes against the component_type_catalog using:
  Step 1: Formal component matching (name/alias lookup)
  Step 2: Structural heuristics (position, layout, text patterns)
  Step 3: LLM fallback (deferred to Phase 1b)
  Step 4: Vision cross-validation (deferred to Phase 1b)
"""

from __future__ import annotations

import sqlite3
from typing import Any

from dd.catalog import get_catalog
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


def run_classification(
    conn: sqlite3.Connection,
    file_id: int,
    client: Any = None,
    file_key: str | None = None,
    fetch_screenshot: Any = None,
    since_screen_id: int | None = None,
    limit: int | None = None,
    progress_callback: Any = None,
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

        if client is not None and file_key is not None and fetch_screenshot is not None:
            from dd.classify_vision import cross_validate_vision
            vision_result = cross_validate_vision(
                conn, screen_id, file_key, client, fetch_screenshot,
            )
            total_vision["validated"] += vision_result["validated"]
            total_vision["agreed"] += vision_result["agreed"]
            total_vision["disagreed"] += vision_result["disagreed"]
            per_screen["vision"] = vision_result

        skeleton_result = extract_skeleton(conn, screen_id)
        if skeleton_result is not None:
            total_skeletons += 1
            per_screen["skeleton"] = True

        if progress_callback is not None:
            progress_callback(i, n, screen_id, per_screen)

    return {
        "screens_processed": len(screen_ids),
        "formal_classified": total_formal,
        "heuristic_classified": total_heuristic,
        "llm_classified": total_llm,
        "parent_links": total_linked,
        "vision": total_vision,
        "skeletons_generated": total_skeletons,
    }
