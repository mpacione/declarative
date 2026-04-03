"""Screen pattern extraction and archetype matching.

Extracts common screen archetypes from classified screens by analyzing
the root-level component types. Provides archetype context to enrich
the LLM prompt with project-specific patterns.
"""

import sqlite3
from collections import Counter
from typing import Any, Dict, List


def extract_screen_archetypes(
    conn: sqlite3.Connection, file_id: int,
) -> List[Dict[str, Any]]:
    """Extract screen archetypes by clustering root component types.

    Groups app screens by their set of root-level classified component
    types and returns the most common patterns.
    """
    cursor = conn.execute(
        "SELECT s.id, GROUP_CONCAT(DISTINCT sci.canonical_type) as types "
        "FROM screens s "
        "JOIN screen_component_instances sci ON sci.screen_id = s.id "
        "WHERE s.file_id = ? AND s.screen_type = 'app_screen' "
        "AND sci.parent_instance_id IS NULL "
        "GROUP BY s.id",
        (file_id,),
    )

    signatures = Counter()
    for row in cursor.fetchall():
        types = sorted(set(row[1].split(", ")))
        sig = ", ".join(types)
        signatures[sig] += 1

    archetypes = []
    for sig, count in signatures.most_common(10):
        types = [t.strip() for t in sig.split(",")]
        archetypes.append({
            "signature": sig,
            "screen_count": count,
            "component_types": types,
        })

    return archetypes


def get_archetype_prompt_context(
    archetypes: List[Dict[str, Any]],
) -> str:
    """Generate LLM prompt context from extracted archetypes.

    Returns a text block describing the project's screen patterns
    for inclusion in the LLM system prompt.
    """
    if not archetypes:
        return ""

    lines = ["This project's screens follow these common patterns:"]
    for arch in archetypes[:5]:
        types_str = ", ".join(arch["component_types"])
        lines.append(f"- {types_str} ({arch['screen_count']} screens)")

    lines.append("")
    lines.append("When composing screens, prefer these established patterns.")
    return "\n".join(lines)
