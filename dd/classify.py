"""Component classification cascade (T5 Phase 1).

Classifies nodes against the component_type_catalog using:
  Step 1: Formal component matching (name/alias lookup)
  Step 2: Structural heuristics (position, layout, text patterns)
  Step 3: LLM fallback (deferred to Phase 1b)
  Step 4: Vision cross-validation (deferred to Phase 1b)
"""

import re
import sqlite3
from typing import Any, Dict, List, Optional

from dd.catalog import get_catalog


# Patterns that indicate generic auto-named nodes (not real component names)
_GENERIC_NAME_RE = re.compile(
    r"^(Frame|Group|Rectangle|Vector|Ellipse|Boolean)\s*\d*$",
    re.IGNORECASE,
)


def parse_component_name(name: str) -> List[str]:
    """Extract candidate lookup keys from a node name, longest first.

    For "button/large/translucent" returns:
      ["button/large/translucent", "button/large", "button"]
    For "Sidebar" returns: ["sidebar"]
    For generic names like "Frame 359" returns: []
    """
    if _GENERIC_NAME_RE.match(name):
        return []

    lowered = name.strip().lower()
    if not lowered:
        return []

    parts = lowered.split("/")
    candidates = []
    for i in range(len(parts), 0, -1):
        candidates.append("/".join(parts[:i]))
    return candidates


def build_alias_index(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    """Build a lookup dict mapping prefixes and aliases to catalog entries.

    Returns dict where keys are lowercase names/aliases and values are
    dicts with catalog_type_id, canonical_name, and category.
    """
    catalog = get_catalog(conn)
    index: Dict[str, Dict[str, Any]] = {}

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


def classify_formal(conn: sqlite3.Connection, screen_id: int) -> Dict[str, Any]:
    """Step 1: Classify nodes by matching name prefixes to the catalog.

    Processes INSTANCE and FRAME nodes that aren't already classified.
    Uses INSERT OR IGNORE so re-runs are idempotent.
    Returns dict with classified count.
    """
    alias_index = build_alias_index(conn)

    cursor = conn.execute(
        "SELECT n.id, n.name, n.node_type "
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
    for node_id, name, node_type in nodes:
        candidates = parse_component_name(name)
        if not candidates:
            continue

        match = None
        for candidate in candidates:
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


def link_parent_instances(conn: sqlite3.Connection, screen_id: int) -> Dict[str, Any]:
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
    instance_by_node: Dict[int, int] = {}
    for sci_id, node_id in cursor.fetchall():
        instance_by_node[node_id] = sci_id

    # Build parent_id map for all nodes in this screen
    cursor = conn.execute(
        "SELECT id, parent_id FROM nodes WHERE screen_id = ?",
        (screen_id,),
    )
    node_parent: Dict[int, Optional[int]] = {}
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


def run_classification(conn: sqlite3.Connection, file_id: int) -> Dict[str, Any]:
    """Orchestrate the full classification cascade for all screens in a file.

    Runs: formal matching → structural heuristics → skeleton extraction.
    Skips component_sheet screens. Returns summary dict.
    """
    from dd.classify_heuristics import classify_heuristics
    from dd.classify_skeleton import extract_skeleton

    cursor = conn.execute(
        "SELECT id FROM screens WHERE file_id = ? "
        "AND (device_class IS NULL OR device_class != 'component_sheet') "
        "ORDER BY id",
        (file_id,),
    )
    screen_ids = [row[0] for row in cursor.fetchall()]

    total_formal = 0
    total_heuristic = 0
    total_linked = 0
    total_skeletons = 0

    for screen_id in screen_ids:
        formal_result = classify_formal(conn, screen_id)
        total_formal += formal_result["classified"]

        heuristic_result = classify_heuristics(conn, screen_id)
        total_heuristic += heuristic_result["classified"]

        link_result = link_parent_instances(conn, screen_id)
        total_linked += link_result["linked"]

        skeleton_result = extract_skeleton(conn, screen_id)
        if skeleton_result is not None:
            total_skeletons += 1

    return {
        "screens_processed": len(screen_ids),
        "formal_classified": total_formal,
        "heuristic_classified": total_heuristic,
        "parent_links": total_linked,
        "skeletons_generated": total_skeletons,
    }
