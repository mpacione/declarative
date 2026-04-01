"""Component classification cascade (T5 Phase 1).

Classifies nodes against the component_type_catalog using:
  Step 1: Formal component matching (name/alias lookup)
  Step 2: Structural heuristics (position, layout, text patterns)
  Step 3: LLM fallback (deferred to Phase 1b)
  Step 4: Vision cross-validation (deferred to Phase 1b)
"""

import re
import sqlite3
from typing import Any, Dict, Optional

from dd.catalog import get_catalog


# Patterns that indicate generic auto-named nodes (not real component names)
_GENERIC_NAME_RE = re.compile(
    r"^(Frame|Group|Rectangle|Vector|Ellipse|Boolean)\s*\d*$",
    re.IGNORECASE,
)


def parse_component_prefix(name: str) -> Optional[str]:
    """Extract the component type prefix from a node name.

    For names like "button/large/translucent", returns "button".
    For names like "Sidebar", returns "sidebar".
    Returns None for generic auto-names like "Frame 359".
    """
    if _GENERIC_NAME_RE.match(name):
        return None

    prefix = name.split("/")[0].strip().lower()
    if not prefix:
        return None

    return prefix


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
        prefix = parse_component_prefix(name)
        if prefix is None:
            continue

        match = alias_index.get(prefix)
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
