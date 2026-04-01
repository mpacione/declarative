"""LLM classification for ambiguous nodes (T5 Phase 1b, Step 3).

Uses Claude Haiku to classify nodes that formal matching and heuristics
couldn't resolve. Targets depth-1 named FRAMEs and remaining INSTANCEs.
"""

import json
import re
import sqlite3
from typing import Any, Dict, List, Optional

from dd.catalog import get_catalog
from dd.classify import is_system_chrome, parse_component_name


_DEFAULT_LLM_CONFIDENCE = 0.7
_LLM_MODEL = "claude-haiku-4-5-20251001"


def build_classification_prompt(
    nodes: List[Dict[str, Any]],
    catalog_types: List[str],
) -> str:
    """Build a classification prompt for a batch of unclassified nodes.

    Returns a prompt string asking the LLM to classify each node as one
    of the catalog types or "container".
    """
    type_list = ", ".join(catalog_types) + ", container"

    node_descriptions = []
    for node in nodes:
        desc = (
            f"- node_id={node['node_id']}: name=\"{node['name']}\", "
            f"type={node.get('node_type', '?')}, "
            f"size={node.get('width', 0):.0f}x{node.get('height', 0):.0f}, "
            f"layout={node.get('layout_mode', 'none')}, "
            f"children={node.get('child_count', 0)}, "
            f"y_position={node.get('y', 0):.0f} "
            f"(screen: {node.get('screen_name', '?')} {node.get('screen_width', 0):.0f}x{node.get('screen_height', 0):.0f})"
        )
        node_descriptions.append(desc)

    nodes_block = "\n".join(node_descriptions)

    return f"""Classify each UI node into one of these canonical component types:
{type_list}

Use "container" for structural layout frames that aren't a specific component.

Nodes to classify:
{nodes_block}

Respond with a JSON array. Each entry must have "node_id", "type", and "confidence" (0.0-1.0).
Example: [{{"node_id": 1, "type": "card", "confidence": 0.85}}]"""


def parse_classification_response(response_text: str) -> List[Dict[str, Any]]:
    """Parse LLM response into classification results.

    Handles raw JSON and JSON wrapped in markdown code blocks.
    Returns list of dicts with node_id, type, confidence.
    """
    text = response_text.strip()

    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []

    if not isinstance(parsed, list):
        return []

    results = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        if "type" not in entry or "node_id" not in entry:
            continue
        results.append({
            "node_id": entry["node_id"],
            "type": entry["type"],
            "confidence": entry.get("confidence", _DEFAULT_LLM_CONFIDENCE),
        })

    return results


def classify_llm(
    conn: sqlite3.Connection,
    screen_id: int,
    client: Any,
) -> Dict[str, Any]:
    """Classify unclassified nodes using LLM.

    Fetches unclassified FRAME/INSTANCE nodes at depth >= 1, builds a
    prompt, calls the LLM, and inserts results with source='llm'.
    """
    unclassified = _get_unclassified_for_llm(conn, screen_id)
    if not unclassified:
        return {"classified": 0}

    catalog_types = [e["canonical_name"] for e in get_catalog(conn)]
    prompt = build_classification_prompt(unclassified, catalog_types)

    response = client.messages.create(
        model=_LLM_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = response.content[0].text
    results = parse_classification_response(response_text)

    node_id_set = {n["node_id"] for n in unclassified}
    catalog_id_lookup = {e["canonical_name"]: e["id"] for e in get_catalog(conn)}

    inserts = []
    for r in results:
        nid = r["node_id"]
        ctype = r["type"]
        if nid not in node_id_set:
            continue
        if ctype == "container":
            catalog_id = None
        else:
            catalog_id = catalog_id_lookup.get(ctype)
            if catalog_id is None and ctype != "container":
                continue

        inserts.append((
            screen_id, nid, catalog_id, ctype, r["confidence"], "llm",
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


def _get_unclassified_for_llm(
    conn: sqlite3.Connection, screen_id: int
) -> List[Dict[str, Any]]:
    """Fetch unclassified nodes suitable for LLM classification."""
    screen = conn.execute(
        "SELECT name, width, height FROM screens WHERE id = ?", (screen_id,)
    ).fetchone()
    if screen is None:
        return []

    cursor = conn.execute(
        "SELECT n.id as node_id, n.name, n.node_type, n.depth, "
        "n.width, n.height, n.y, n.layout_mode, "
        "(SELECT COUNT(*) FROM nodes c WHERE c.parent_id = n.id) as child_count "
        "FROM nodes n "
        "LEFT JOIN screen_component_instances sci "
        "  ON sci.node_id = n.id AND sci.screen_id = n.screen_id "
        "WHERE n.screen_id = ? "
        "  AND n.node_type IN ('FRAME', 'INSTANCE', 'COMPONENT') "
        "  AND n.depth >= 1 "
        "  AND sci.id IS NULL",
        (screen_id,),
    )
    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    result = []
    for row in rows:
        if is_system_chrome(row["name"]):
            continue
        candidates = parse_component_name(row["name"])
        if not candidates:
            continue
        row["screen_name"] = screen[0]
        row["screen_width"] = screen[1]
        row["screen_height"] = screen[2]
        result.append(row)

    return result
