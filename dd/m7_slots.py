"""M7.0.b Step 2 — slot derivation per canonical_type.

Given a canonical_type (e.g., ``button``), cluster every trusted
instance's children by structural signature, pick the dominant cluster,
label its slots via Claude Haiku, then write one ``component_slots``
row per slot for every master component of that canonical_type.

Trusted instance = ``consensus_method`` in plan §SD-3's trusted set,
or NULL (pre-M7.0.a legacy). Untrusted weighted_tie /
weighted_majority rows would muddy the cluster.

Built around the contract that:
- ``canonical_type`` is on ``components`` (migration 018) so we can
  fetch the master set without re-JOINing through instances.
- ``component_key_registry`` maps component_key → figma_node_id so
  we find master ids by joining ``nodes.component_key = ckr.key``
  → ``nodes.figma_node_id`` → ``components.figma_node_id``.
- The LLM's job is only to LABEL slots (name + description). The
  cluster shape comes from data.

Public entry:

- ``cluster_children`` — pure helper, returns shape → count Counter.
- ``derive_slots_for_canonical_type`` — orchestrates cluster +
  LLM-label + INSERT. Writes rows to ``component_slots`` for every
  master of the given canonical_type.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any, Callable, Optional


# Same trust set as the backfill (plan §SD-3).
_TRUSTED_CONSENSUS_METHODS = (
    "formal", "heuristic", "unanimous", "two_source_unanimous",
)


SlotDescriptor = dict[str, Any]  # {name, slot_type, is_required,
                                  #  sort_order, description}


def _trusted_instance_ids(
    conn: sqlite3.Connection, canonical_type: str, limit: Optional[int] = None,
) -> list[int]:
    """Return node_ids of trusted instances of the given canonical_type.

    ``limit`` caps the sample (useful for bulk canonical_types where
    clustering on 8k+ rows is wasteful — the dominant pattern surfaces
    quickly).
    """
    placeholders = ",".join("?" * len(_TRUSTED_CONSENSUS_METHODS))
    sql = (
        f"SELECT sci.node_id FROM screen_component_instances sci "
        f"WHERE sci.canonical_type = ? AND ("
        f"  sci.consensus_method IS NULL "
        f"  OR sci.consensus_method IN ({placeholders}))"
    )
    params: list[Any] = [canonical_type, *_TRUSTED_CONSENSUS_METHODS]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [r[0] for r in rows]


def cluster_children(
    conn: sqlite3.Connection, node_ids: list[int],
) -> Counter:
    """Return a Counter mapping child-type tuples to instance count.

    The tuple is the child node_types in ``sort_order``. Two instances
    end up in the same cluster iff their children line up exactly —
    same count, same types, same order. That's strict enough for slot
    derivation: if one button has (INSTANCE, TEXT, INSTANCE) and
    another has (TEXT, INSTANCE), they're different slot vocabularies.
    """
    counter: Counter = Counter()
    for nid in node_ids:
        kids = conn.execute(
            "SELECT node_type FROM nodes WHERE parent_id = ? "
            "ORDER BY sort_order",
            (nid,),
        ).fetchall()
        shape = tuple(r[0] for r in kids)
        counter[shape] += 1
    return counter


def dominant_cluster(
    counts: Counter, *, min_share: float = 0.5,
) -> Optional[tuple[str, ...]]:
    """Return the most-common child-type tuple iff it carries at least
    ``min_share`` of the total. Returns ``None`` when the distribution
    is too flat — slot derivation would be unreliable on a type whose
    top cluster is a minority.
    """
    if not counts:
        return None
    total = sum(counts.values())
    shape, n = counts.most_common(1)[0]
    if total == 0 or n / total < min_share:
        return None
    return shape


def _mk_slot_desc(
    *, name: str, slot_type: str, is_required: bool,
    sort_order: int, description: str,
) -> SlotDescriptor:
    return {
        "name": name,
        "slot_type": slot_type,
        "is_required": 1 if is_required else 0,
        "sort_order": sort_order,
        "description": description,
    }


def _slot_type_for_node_type(node_type: str) -> str:
    """Map Figma node_type → component_slots.slot_type tag."""
    mapping = {
        "TEXT": "text",
        "INSTANCE": "component",
        "COMPONENT": "component",
        "FRAME": "container",
        "VECTOR": "icon",
        "BOOLEAN_OPERATION": "icon",
    }
    return mapping.get(node_type, node_type.lower())


def _build_llm_prompt(
    canonical_type: str,
    shape: tuple[str, ...],
    total_instances: int,
    cluster_size: int,
    sample_texts_by_pos: dict[int, list[str]],
    sample_names_by_pos: dict[int, list[str]],
) -> str:
    """Structured prompt for Claude: given a (canonical_type, shape),
    return one slot descriptor per position.
    """
    lines = [
        f"You are labelling the slots of a **{canonical_type}** "
        f"UI component.",
        "",
        (
            f"We analysed {total_instances} instances of "
            f"{canonical_type} and {cluster_size} "
            f"({100 * cluster_size / max(total_instances, 1):.0f}%) "
            f"share this exact child structure:"
        ),
        "",
    ]
    for i, ntype in enumerate(shape):
        names = sample_names_by_pos.get(i, [])
        texts = sample_texts_by_pos.get(i, [])
        name_preview = ", ".join(f"{n!r}" for n in names[:5])
        text_preview = ", ".join(f"{t!r}" for t in texts[:5]) or "(none)"
        lines.append(
            f"  position {i}: node_type={ntype} — "
            f"common child names: [{name_preview}], "
            f"sample text content: [{text_preview}]"
        )
    lines += [
        "",
        "For each position, emit a slot descriptor via the tool:",
        "- `name` — snake_case slot name (label / leading_icon / "
        "trailing_icon / content / title / etc.)",
        "- `is_required` — true iff every instance in this cluster "
        "has a node at this position",
        "- `description` — 1 sentence explaining the slot's role",
        "",
        "Conventions:",
        "- TEXT children holding the primary label → `label`",
        "- INSTANCE children before the label → `leading_icon` "
        "(or `leading_content` for non-icon components)",
        "- INSTANCE children after the label → `trailing_icon`",
        "- Decorative-only INSTANCE siblings (dividers, scrims) → "
        "describe by role",
    ]
    return "\n".join(lines)


_SLOT_TOOL_SCHEMA = {
    "name": "emit_slots",
    "description": (
        "Emit one slot descriptor per position in the cluster. The "
        "positions come in order; the response must have exactly "
        "one entry per position."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "slots": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "position": {"type": "integer"},
                        "name": {"type": "string"},
                        "is_required": {"type": "boolean"},
                        "description": {"type": "string"},
                    },
                    "required": [
                        "position", "name", "is_required", "description",
                    ],
                },
            },
        },
        "required": ["slots"],
    },
}


def _invoke_llm(
    client: Any,
    prompt: str,
    *,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 2048,
) -> list[dict[str, Any]]:
    """Call Claude with the slot tool schema. Returns the parsed slots
    list. Caller is responsible for error handling.
    """
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[_SLOT_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": _SLOT_TOOL_SCHEMA["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != _SLOT_TOOL_SCHEMA["name"]:
            continue
        inp = getattr(block, "input", None)
        if isinstance(inp, dict):
            slots = inp.get("slots")
            if isinstance(slots, list):
                return slots
    return []


def _sample_children(
    conn: sqlite3.Connection, node_ids: list[int], shape: tuple[str, ...],
) -> tuple[dict[int, list[str]], dict[int, list[str]], int]:
    """Collect sample child names / sample_text per position across all
    instances that match ``shape``. Returns (names_by_pos, texts_by_pos,
    match_count).
    """
    names_by_pos: dict[int, list[str]] = {i: [] for i in range(len(shape))}
    texts_by_pos: dict[int, list[str]] = {i: [] for i in range(len(shape))}
    match_count = 0
    for nid in node_ids:
        kids = conn.execute(
            "SELECT node_type, name, text_content FROM nodes "
            "WHERE parent_id = ? ORDER BY sort_order",
            (nid,),
        ).fetchall()
        kid_shape = tuple(k[0] for k in kids)
        if kid_shape != shape:
            continue
        match_count += 1
        for i, (ntype, name, text) in enumerate(kids):
            if name and name not in names_by_pos[i]:
                names_by_pos[i].append(name)
            if text:
                snippet = str(text).strip()[:40]
                if snippet and snippet not in texts_by_pos[i]:
                    texts_by_pos[i].append(snippet)
    return names_by_pos, texts_by_pos, match_count


def _master_component_ids(
    conn: sqlite3.Connection, canonical_type: str, *, file_id: int,
) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM components "
        "WHERE canonical_type = ? AND file_id = ?",
        (canonical_type, file_id),
    ).fetchall()
    return [r[0] for r in rows]


def derive_slots_for_canonical_type(
    conn: sqlite3.Connection,
    canonical_type: str,
    *,
    file_id: int,
    llm_invoker: Optional[Callable[[str], list[dict[str, Any]]]] = None,
    sample_limit: int = 500,
    min_cluster_share: float = 0.5,
) -> dict[str, Any]:
    """End-to-end: cluster → label → write component_slots rows.

    ``llm_invoker`` is a callable taking the prompt and returning the
    parsed slot list. Tests pass a stub; production wraps
    ``_invoke_llm``. Returns a stats dict with ``masters``,
    ``slots_inserted``, and ``dominant_shape`` + ``cluster_share`` for
    human-readable reports.
    """
    # 1. Trusted instances.
    node_ids = _trusted_instance_ids(
        conn, canonical_type, limit=sample_limit,
    )
    if not node_ids:
        return {
            "canonical_type": canonical_type,
            "masters": 0,
            "slots_inserted": 0,
            "error": "no trusted instances",
        }

    # 2. Cluster by child-type shape.
    counts = cluster_children(conn, node_ids)
    shape = dominant_cluster(counts, min_share=min_cluster_share)
    if shape is None:
        return {
            "canonical_type": canonical_type,
            "masters": 0,
            "slots_inserted": 0,
            "error": (
                f"no dominant cluster (top={counts.most_common(3) if counts else []})"
            ),
        }

    total = sum(counts.values())
    cluster_n = counts[shape]

    # 3. Sample children from the matching instances.
    names_by_pos, texts_by_pos, match_count = _sample_children(
        conn, node_ids, shape,
    )
    prompt = _build_llm_prompt(
        canonical_type=canonical_type,
        shape=shape,
        total_instances=total,
        cluster_size=cluster_n,
        sample_texts_by_pos=texts_by_pos,
        sample_names_by_pos=names_by_pos,
    )

    # 4. LLM-label the slots.
    if llm_invoker is None:
        raise ValueError(
            "llm_invoker required — pass a callable returning the "
            "tool-use slot list."
        )
    raw_slots = llm_invoker(prompt)
    if not raw_slots:
        return {
            "canonical_type": canonical_type,
            "masters": 0,
            "slots_inserted": 0,
            "error": "llm returned no slots",
            "dominant_shape": shape,
        }

    # 5. Build slot descriptors, merging LLM labels with cluster data.
    slots: list[SlotDescriptor] = []
    for i, ntype in enumerate(shape):
        # Find the LLM entry for this position (by-position match, not
        # index-in-array, so the LLM can return them out of order).
        entry = next(
            (s for s in raw_slots if s.get("position") == i), None,
        )
        if entry is None:
            continue
        slots.append(_mk_slot_desc(
            name=str(entry.get("name", f"slot_{i}")),
            slot_type=_slot_type_for_node_type(ntype),
            is_required=bool(entry.get("is_required", False)),
            sort_order=i,
            description=str(entry.get("description", "")),
        ))

    if not slots:
        return {
            "canonical_type": canonical_type,
            "masters": 0,
            "slots_inserted": 0,
            "error": "llm returned entries but none matched positions",
            "dominant_shape": shape,
        }

    # 6. INSERT one slot row per master × slot. Idempotent via
    # UNIQUE(component_id, name) in the schema.
    masters = _master_component_ids(
        conn, canonical_type, file_id=file_id,
    )
    inserted = 0
    for component_id in masters:
        for slot in slots:
            try:
                conn.execute(
                    "INSERT INTO component_slots "
                    "(component_id, name, slot_type, is_required, "
                    " sort_order, description) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        component_id, slot["name"], slot["slot_type"],
                        slot["is_required"], slot["sort_order"],
                        slot["description"],
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                # Existing row (UNIQUE collision) — leave it. Running
                # the script twice is idempotent.
                pass
    conn.commit()

    return {
        "canonical_type": canonical_type,
        "masters": len(masters),
        "slots_inserted": inserted,
        "dominant_shape": shape,
        "cluster_share": cluster_n / max(total, 1),
        "sample_size": total,
    }


# Convenience: the production LLM invoker.
def make_anthropic_invoker(client: Any) -> Callable[[str], list[dict[str, Any]]]:
    def _invoke(prompt: str) -> list[dict[str, Any]]:
        return _invoke_llm(client, prompt)
    return _invoke
