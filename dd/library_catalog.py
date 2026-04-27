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


# Canonical prefix of an L3 CompRef literal (grammar spec §7).
# Factored so the serialiser + any doc-generation pinning stays in
# sync if the grammar ever evolves.
COMP_REF_PREFIX = "-> "

# Serializer output shape version. Bump when a consumer depends on
# breaking-change fields (e.g., variants added under a different key).
LIBRARY_SCHEMA_VERSION = 1


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


def _fetch_variant(
    conn: sqlite3.Connection, component_id: int,
) -> Optional[dict[str, Any]]:
    """The variant row for a components.id, if any. Returns
    ``{name, properties}`` where ``properties`` is the decoded JSON
    axis-value map (e.g. ``{"size": "small", "style": "solid"}``).
    """
    row = conn.execute(
        "SELECT name, properties FROM component_variants "
        "WHERE component_id = ? LIMIT 1",
        (component_id,),
    ).fetchone()
    if row is None:
        return None
    name, props_json = row
    try:
        props = json.loads(props_json) if props_json else {}
    except (ValueError, TypeError):
        props = {}
    return {"name": name, "properties": props}


def _comp_ref_for(name: str) -> str:
    """Render the CompRef literal the LLM should emit to swap in this
    master (`docs/spec-dd-markup-grammar.md` §7).
    """
    return f"{COMP_REF_PREFIX}{name}"


def _prop_defs_by_type(
    conn: sqlite3.Connection,
) -> dict[str, dict[str, Any]]:
    """Return canonical_name → prop_definitions for catalog rows.

    ``prop_definitions`` is stored as a JSON string in
    ``component_type_catalog``; decoded here so callers can include
    it in the LLM tool context (M7.3 set-edits need to know valid
    property names + types).
    """
    rows = conn.execute(
        "SELECT canonical_name, prop_definitions "
        "FROM component_type_catalog"
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for name, pd in rows:
        if not pd:
            continue
        try:
            decoded = json.loads(pd) if isinstance(pd, str) else pd
        except (ValueError, TypeError):
            decoded = None
        if isinstance(decoded, dict):
            out[name] = decoded
    return out


def serialize_library(
    conn: sqlite3.Connection,
    *,
    canonical_types: Optional[Iterable[str]] = None,
    file_id: Optional[int] = None,
    include_slots: bool = True,
    include_prop_defs: bool = False,
    include_figma_ids: bool = False,
    include_variants: bool = False,
) -> dict[str, Any]:
    """Return a JSON-serialisable catalog description.

    ``canonical_types``: restrict to these types (case-sensitive). None
    returns every typed component.
    ``file_id``: filter by file (Dank has only 1; pass when scaling
    to multi-file DBs).
    ``include_slots``: set False to skip per-component slot lookup when
    the LLM task doesn't need slot information (e.g., swap-only flows
    where only the CompRef path matters).
    ``include_prop_defs``: set True when downstream LLM flows emit
    `set` verbs — gives each entry a ``prop_definitions`` field
    describing valid property names + types from the catalog. Off
    by default to keep the swap-only demo lean.
    ``include_figma_ids``: set True to include the master's
    figma_node_id. Off by default — the LLM selects via name /
    CompRef and doesn't need raw node ids.
    ``include_variants``: set True to include the master's
    component_variants row (name + properties axis-value map).
    Lets M7.3+ flows emit axis-aware swaps (``style=translucent``)
    instead of selecting by full CompRef path.
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

    prop_defs = _prop_defs_by_type(conn) if include_prop_defs else {}

    entries: list[dict[str, Any]] = []
    for cid, name, ctype, category, fid in rows:
        entry: dict[str, Any] = {
            "name": name,
            "canonical_type": ctype,
            "category": category,
            "comp_ref": _comp_ref_for(name),
        }
        if include_figma_ids:
            entry["figma_node_id"] = fid
        if include_slots:
            entry["slots"] = _fetch_slots(conn, cid)
        if include_prop_defs:
            pd = prop_defs.get(ctype)
            if pd:
                entry["prop_definitions"] = pd
        if include_variants:
            variant = _fetch_variant(conn, cid)
            if variant is not None:
                entry["variant"] = variant
        entries.append(entry)

    return {
        "_version": LIBRARY_SCHEMA_VERSION,
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
