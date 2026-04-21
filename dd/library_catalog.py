"""Library-catalog serialiser for M7.2 LLM tool context.

The LLM needs to know what components are available to swap in or
reference. This module serialises `components` + `component_slots`
(+ `component_variants` when M7.0.c lands) into a compact JSON
shape suitable for an Anthropic tool-use system prompt or message
body.

The serialised catalog is cheap to include in context (target:
<5KB for Dank's 100 components), filterable by canonical_type (so
the LLM sees only relevant families for a given task), and written
in the same vocabulary as the L3 CompRef path — if the LLM wants
to swap in ``button/small/solid`` it sees exactly that name in the
catalog.

Shape::

    {
      "total_components": 100,
      "components": [
        {
          "name": "button/small/solid",
          "canonical_type": "button",
          "category": "actions",
          "comp_ref": "-> button/small/solid",
          "slots": [
            {"name": "leading_icon", "slot_type": "component",
             "is_required": False,
             "description": "Optional icon displayed before the label"},
            {"name": "label", "slot_type": "text",
             "is_required": True,
             "description": "The primary text label"},
            {"name": "trailing_icon", "slot_type": "component",
             "is_required": False,
             "description": "Optional icon after the label"}
          ]
        },
        ...
      ]
    }

Usage::

    from dd.library_catalog import serialize_library
    catalog = serialize_library(conn, canonical_types=["button"])
    # Pass `catalog` as a JSON string in the LLM tool-use system prompt.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Optional


def _fetch_slots(
    conn: sqlite3.Connection, component_id: int,
) -> list[dict[str, Any]]:
    """All slots for one component, ordered by sort_order."""
    rows = conn.execute(
        "SELECT name, slot_type, is_required, description, sort_order "
        "FROM component_slots WHERE component_id = ? "
        "ORDER BY sort_order",
        (component_id,),
    ).fetchall()
    return [
        {
            "name": r[0],
            "slot_type": r[1],
            "is_required": bool(r[2]),
            "description": r[3] or "",
            "sort_order": r[4],
        }
        for r in rows
    ]


def _comp_ref_for(name: str) -> str:
    """Render the CompRef literal the LLM should emit to swap in this
    master. ``-> name`` matches the L3 markup spec's CompRef syntax
    (`docs/spec-dd-markup-grammar.md` §7).
    """
    return f"-> {name}"


def serialize_library(
    conn: sqlite3.Connection,
    *,
    canonical_types: Optional[Iterable[str]] = None,
    file_id: Optional[int] = None,
    include_slots: bool = True,
) -> dict[str, Any]:
    """Return a JSON-serialisable catalog description.

    ``canonical_types``: restrict to these types (case-sensitive). None
    returns every typed component.
    ``file_id``: filter by file (Dank has only 1; pass when scaling
    to multi-file DBs).
    ``include_slots``: set False to skip per-component slot lookup when
    the LLM task doesn't need slot information (e.g., a whole-screen
    structural-similarity swap where only the CompRef path matters).
    """
    clauses: list[str] = ["c.canonical_type IS NOT NULL"]
    params: list[Any] = []
    if canonical_types is not None:
        types = [t for t in canonical_types if t]
        if not types:
            return {"total_components": 0, "components": []}
        placeholders = ",".join("?" * len(types))
        clauses.append(f"c.canonical_type IN ({placeholders})")
        params.extend(types)
    if file_id is not None:
        clauses.append("c.file_id = ?")
        params.append(file_id)

    sql = (
        "SELECT c.id, c.name, c.canonical_type, c.category, "
        "       c.figma_node_id "
        "FROM components c "
        f"WHERE {' AND '.join(clauses)} "
        "ORDER BY c.canonical_type, c.name"
    )
    rows = conn.execute(sql, params).fetchall()

    entries: list[dict[str, Any]] = []
    for cid, name, ctype, category, fid in rows:
        entry: dict[str, Any] = {
            "name": name,
            "canonical_type": ctype,
            "category": category,
            "comp_ref": _comp_ref_for(name),
            "figma_node_id": fid,
        }
        if include_slots:
            entry["slots"] = _fetch_slots(conn, cid)
        entries.append(entry)

    return {
        "total_components": len(entries),
        "components": entries,
    }


def serialize_library_json(
    conn: sqlite3.Connection, **kwargs: Any,
) -> str:
    """Convenience: serialize + `json.dumps` so callers can drop the
    result into an LLM prompt with one call.
    """
    return json.dumps(
        serialize_library(conn, **kwargs),
        ensure_ascii=False,
        indent=2,
    )
