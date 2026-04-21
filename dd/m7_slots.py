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


# Catalog-backed definition of "icon" — used by the child
# classifier below. Anything that an M7.0.a classifier calls an
# icon gets bucketed as ICON; unclassified INSTANCEs stay as
# COMPONENT so the slot vocabulary distinguishes "leading_icon"
# from a nested-component slot.
_ICON_CANONICAL_TYPES = frozenset({"icon", "icon_button", "control_point"})


def _child_class(
    conn: sqlite3.Connection,
    node_id: int,
    node_type: str,
    component_key: Optional[str],
) -> str:
    """Return the cluster-level class of a child node:
    TEXT / ICON / COMPONENT / CONTAINER / OTHER.

    For INSTANCEs, we look at whether the master points at an
    icon-typed component (via components.canonical_type, seeded in
    M7.0.b Step 1). Anything else (nested buttons, badges, cards)
    stays COMPONENT so the cluster key can tell icon slots apart
    from non-icon component slots.
    """
    if node_type == "TEXT":
        return "TEXT"
    if node_type in ("VECTOR", "BOOLEAN_OPERATION", "ELLIPSE"):
        return "ICON"
    if node_type in ("INSTANCE", "COMPONENT") and component_key:
        row = conn.execute(
            "SELECT canonical_type FROM components c "
            "JOIN nodes m ON m.figma_node_id = c.figma_node_id "
            "WHERE m.component_key = ? LIMIT 1",
            (component_key,),
        ).fetchone()
        if row and row[0] in _ICON_CANONICAL_TYPES:
            return "ICON"
        return "COMPONENT"
    if node_type in ("INSTANCE", "COMPONENT"):
        return "COMPONENT"
    if node_type == "FRAME":
        return "CONTAINER"
    return "OTHER"


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
    """Return a Counter mapping child-class tuples to instance count.

    Each child is bucketed into TEXT / ICON / COMPONENT / CONTAINER
    / OTHER (see ``_child_class``). This is finer-grained than raw
    node_type — it distinguishes icon slots (``icon/back``,
    ``control_point``) from non-icon component slots (nested
    buttons, badges) even though both are INSTANCE node_types —
    which matters because they want different slot vocabularies.

    Two instances end up in the same cluster iff their child
    classes line up exactly in sort_order.
    """
    counter: Counter = Counter()
    for nid in node_ids:
        kids = conn.execute(
            "SELECT id, node_type, component_key FROM nodes "
            "WHERE parent_id = ? ORDER BY sort_order",
            (nid,),
        ).fetchall()
        shape = tuple(
            _child_class(conn, kid_id, ntype, ckey)
            for kid_id, ntype, ckey in kids
        )
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


def _slot_type_for_child_class(child_class: str) -> str:
    """Map cluster child-class → component_slots.slot_type tag.

    The cluster classes are already semantic (TEXT / ICON /
    COMPONENT / CONTAINER / OTHER) so the mapping is 1:1 lowercase.
    """
    return child_class.lower()


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
    """Collect sample child names / text per position for instances
    whose child-class tuple matches ``shape``. Returns (names_by_pos,
    texts_by_pos, match_count).
    """
    names_by_pos: dict[int, list[str]] = {i: [] for i in range(len(shape))}
    texts_by_pos: dict[int, list[str]] = {i: [] for i in range(len(shape))}
    match_count = 0
    for nid in node_ids:
        kids = conn.execute(
            "SELECT id, node_type, component_key, name, text_content "
            "FROM nodes WHERE parent_id = ? ORDER BY sort_order",
            (nid,),
        ).fetchall()
        kid_shape = tuple(
            _child_class(conn, kid_id, ntype, ckey)
            for kid_id, ntype, ckey, _name, _text in kids
        )
        if kid_shape != shape:
            continue
        match_count += 1
        for i, (_kid_id, _ntype, _ckey, name, text) in enumerate(kids):
            if name and name not in names_by_pos[i]:
                names_by_pos[i].append(name)
            if text:
                snippet = str(text).strip()[:40]
                if snippet and snippet not in texts_by_pos[i]:
                    texts_by_pos[i].append(snippet)
    return names_by_pos, texts_by_pos, match_count


def _node_ids_matching_shape(
    conn: sqlite3.Connection,
    node_ids: list[int],
    shape: tuple[str, ...],
) -> list[int]:
    """Return the subset of ``node_ids`` whose children classify
    into exactly ``shape``. Used to compute data-derived metrics
    scoped to the dominant cluster.
    """
    out: list[int] = []
    for nid in node_ids:
        kids = conn.execute(
            "SELECT id, node_type, component_key FROM nodes "
            "WHERE parent_id = ? ORDER BY sort_order",
            (nid,),
        ).fetchall()
        kid_shape = tuple(
            _child_class(conn, kid_id, ntype, ckey)
            for kid_id, ntype, ckey in kids
        )
        if kid_shape == shape:
            out.append(nid)
    return out


def _compute_is_required(
    conn: sqlite3.Connection,
    node_ids: list[int],
    shape_len: int,
) -> dict[int, bool]:
    """Position-wise ``is_required`` from data.

    A position ``i`` is required iff every examined instance has at
    least ``i+1`` children. With the cluster filter applied upstream
    this is trivially 100% for positions [0, shape_len), but the
    helper supports fuzzy-shape matching in the future.
    """
    if shape_len == 0:
        return {}
    present_counts = {i: 0 for i in range(shape_len)}
    total = 0
    for nid in node_ids:
        count = conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE parent_id = ?",
            (nid,),
        ).fetchone()[0]
        total += 1
        for i in range(shape_len):
            if count > i:
                present_counts[i] += 1
    if total == 0:
        return {i: False for i in range(shape_len)}
    return {i: present_counts[i] == total for i in range(shape_len)}


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

    # 3b. Data-derived is_required across ALL trusted instances
    # (not just the matching cluster). Plan §SD-2: "is_required=0
    # flags optional slots not present in every instance" — the
    # correct way to compute this is to count all trusted instances
    # (including minority shapes) and mark a position required iff
    # every instance has a child there.
    #
    # Example: dominant cluster (COMPONENT, TEXT, COMPONENT) at 84%,
    # minority (TEXT,) at 7%. Every trusted button has ≥1 child, so
    # position 0 is always filled → required. Positions 1 and 2
    # only appear in the 84% cluster → is_required=False, i.e.,
    # "optional in some variants".
    is_required_by_pos = _compute_is_required(
        conn, node_ids, len(shape),
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

    # 4b. Validate LLM positions: every entry must have a position
    # integer in [0, len(shape)); collect mismatches so downstream
    # reporting surfaces them.
    valid_positions = set(range(len(shape)))
    oob_entries = [
        s for s in raw_slots
        if not isinstance(s.get("position"), int)
        or s["position"] not in valid_positions
    ]

    # 5. Build slot descriptors. ``is_required`` comes from the
    # LLM's semantic judgment — e.g., for a button the LLM correctly
    # says label=required and leading_icon=optional, even though
    # data-derived "is position i present in every instance" would
    # say label is optional (pure-text variants have TEXT at
    # position 0, not 1, so position 1 isn't always filled across
    # ALL trusted instances). The LLM understands slot SEMANTICS;
    # raw positional presence doesn't.
    #
    # The data-derived signal is kept as cross-check metadata in
    # ``is_required_mismatches`` so humans can audit outliers.
    slots: list[SlotDescriptor] = []
    is_required_mismatches: list[dict[str, Any]] = []
    for i, child_cls in enumerate(shape):
        entry = next(
            (s for s in raw_slots if s.get("position") == i), None,
        )
        if entry is None:
            continue
        data_required = is_required_by_pos.get(i, False)
        llm_required = bool(entry.get("is_required", False))
        if data_required != llm_required:
            is_required_mismatches.append({
                "position": i,
                "llm_said": llm_required,
                "data_says": data_required,
            })
        slots.append(_mk_slot_desc(
            name=str(entry.get("name", f"slot_{i}")),
            slot_type=_slot_type_for_child_class(child_cls),
            is_required=llm_required,
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
            "llm_out_of_bounds_entries": len(oob_entries),
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
        "llm_out_of_bounds_entries": len(oob_entries),
        "is_required_mismatches": is_required_mismatches,
    }


# Convenience: the production LLM invoker.
def make_anthropic_invoker(client: Any) -> Callable[[str], list[dict[str, Any]]]:
    def _invoke(prompt: str) -> list[dict[str, Any]]:
        return _invoke_llm(client, prompt)
    return _invoke
