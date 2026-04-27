"""M7.4 S2 structural-verb helpers.

Shared scaffolding for the four LLM-in-loop demos: delete /
append / insert / move. Each verb's candidate-collector + tool
schema + structural verifier lives here so the CLI stays thin.

The S2-tier demos only assert structural parity on the edit
itself (per plan §4 S2 gate "parent-child edges match exactly —
ordered sibling list correct"); render + is_parity is M7.2's
scope and applies to swap-style edits where Mode-1 resolution
kicks in. A delete / append / insert / move doesn't need
rebuild_maps extensions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Optional


# Universal-catalog types the LLM may introduce via append/insert.
# Deliberately narrow — if the user wants a button swap it's an
# M7.2 swap, not an append.
_APPENDABLE_TYPES: tuple[str, ...] = (
    "text", "heading", "rectangle", "ellipse", "frame",
)


def _walk_nodes(doc) -> list:
    out: list = []

    def go(ns):
        for n in ns:
            if hasattr(n, "head"):
                out.append(n)
            if getattr(n, "block", None):
                go(n.block.statements)

    go(doc.top_level)
    return out


def unique_eids(doc) -> list[str]:
    """Return every eid that appears exactly once in ``doc``.

    Bare ``@X`` addressing fires KIND_AMBIGUOUS_EREF when more
    than one node carries that eid. All four S2 verbs use bare
    references, so the candidate set must be filtered to
    globally-unique eids up front."""
    counts: Counter = Counter()
    for n in _walk_nodes(doc):
        if n.head.eid:
            counts[n.head.eid] += 1
    return [e for e, c in counts.items() if c == 1]


def existing_eids(doc) -> set[str]:
    """Return every eid present in ``doc`` regardless of multiplicity.

    Used as a collision-guard for LLM-proposed new eids (append /
    insert / compose). If the LLM invents ``new-child`` and the
    donor already has a ``#new-child`` node somewhere, the post-
    apply doc would have two ``@new-child`` nodes and every
    subsequent bare reference fires KIND_AMBIGUOUS_EREF. Call
    sites should reject the proposal before apply."""
    out: set[str] = set()
    for n in _walk_nodes(doc):
        if n.head.eid:
            out.add(n.head.eid)
    return out


def collect_removable_candidates(doc) -> list[dict[str, Any]]:
    """Nodes eligible for ``delete @X``.

    Filters:
    - Globally unique eid (bare ref resolvable).
    - Not the top-level root (deleting the root produces an
      empty doc, which breaks downstream verify).
    - Has a parent node (root-level siblings included).
    """
    uniq = set(unique_eids(doc))
    candidates: list[dict[str, Any]] = []
    roots = {id(n) for n in doc.top_level}

    def go(ns, parent):
        for n in ns:
            if id(n) in roots and parent is None:
                if getattr(n, "block", None):
                    go(n.block.statements, n)
                continue
            if n.head.eid in uniq:
                candidates.append({
                    "eid": n.head.eid,
                    "type": n.head.type_or_path,
                    "parent_eid": (
                        parent.head.eid if parent else None
                    ),
                })
            if getattr(n, "block", None):
                go(n.block.statements, n)

    go(doc.top_level, None)
    return candidates


def collect_parent_candidates(doc) -> list[dict[str, Any]]:
    """Nodes eligible for ``append to=@X`` — any node that can
    host a child. We include every unique-eid'd node that
    already has a block (confirming it's a valid parent in the
    grammar) or whose type_or_path is a container-ish keyword.
    """
    uniq = set(unique_eids(doc))
    out: list[dict[str, Any]] = []
    container_types = {
        "screen", "frame", "card", "section", "drawer", "dialog",
        "modal", "sheet", "toolbar", "header", "footer", "nav",
        "tabs", "container",
    }
    for n in _walk_nodes(doc):
        if n.head.eid not in uniq:
            continue
        has_block = getattr(n, "block", None) is not None
        is_container = n.head.type_or_path in container_types
        if has_block or is_container:
            child_count = (
                len(n.block.statements) if has_block else 0
            )
            out.append({
                "eid": n.head.eid,
                "type": n.head.type_or_path,
                "child_count": child_count,
            })
    return out


def collect_insert_candidates(doc) -> list[dict[str, Any]]:
    """``insert into=@parent after=@anchor {...}`` —
    (parent, anchor) pairs where anchor is a direct child of
    parent and both eids are unique.
    """
    uniq = set(unique_eids(doc))
    out: list[dict[str, Any]] = []

    def go(ns, parent):
        for n in ns:
            block = getattr(n, "block", None)
            if (
                parent is not None
                and n.head.eid in uniq
                and parent.head.eid in uniq
            ):
                out.append({
                    "parent_eid": parent.head.eid,
                    "anchor_eid": n.head.eid,
                    "parent_type": parent.head.type_or_path,
                    "anchor_type": n.head.type_or_path,
                })
            if block is not None:
                go(block.statements, n)

    go(doc.top_level, None)
    return out


def collect_move_candidates(doc) -> list[dict[str, Any]]:
    """``move @target to=@dest`` — (target, destination) pairs
    where both are unique-eid'd and destination can host
    children."""
    targets = collect_removable_candidates(doc)
    destinations = collect_parent_candidates(doc)
    dest_set = {d["eid"]: d for d in destinations}
    out: list[dict[str, Any]] = []
    for t in targets:
        for dest_eid, dest in dest_set.items():
            if dest_eid == t["eid"]:
                continue
            if dest_eid == t["parent_eid"]:
                # Moving to the same parent is a no-op unless
                # position changes; keep for completeness, LLM
                # decides.
                pass
            out.append({
                "target_eid": t["eid"],
                "target_type": t["type"],
                "dest_eid": dest_eid,
                "dest_type": dest["type"],
            })
    return out


# ---------------------------------------------------------------
# Tool schemas (per-verb, enum-pinned)
# ---------------------------------------------------------------


def build_delete_tool_schema(eids: list[str]) -> dict[str, Any]:
    return {
        "name": "emit_delete_edit",
        "description": (
            "Emit one `delete @X` statement removing a non-root "
            "node from the document. Prefer safely-removable "
            "nodes (decorative / duplicate / error-state) over "
            "structural ones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_eid": {
                    "type": "string", "enum": eids,
                    "description": "Eid of the node to delete.",
                },
                "rationale": {
                    "type": "string",
                    "description": "One-sentence reason.",
                },
            },
            "required": ["target_eid", "rationale"],
        },
    }


def build_append_tool_schema(
    parent_eids: list[str],
    child_types: tuple[str, ...] = _APPENDABLE_TYPES,
) -> dict[str, Any]:
    return {
        "name": "emit_append_edit",
        "description": (
            "Emit one `append to=@X { TYPE #NEW_EID \"TEXT\" }` "
            "statement adding a child to the end of a parent's "
            "block. Pick only from the allowed child types."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "parent_eid": {
                    "type": "string", "enum": parent_eids,
                },
                "child_type": {
                    "type": "string",
                    "enum": list(child_types),
                },
                "child_eid": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9-]{1,38}$",
                    "description": (
                        "Globally-unique kebab-case eid for the "
                        "new child (no leading @)."
                    ),
                },
                "child_text": {
                    "type": "string",
                    "minLength": 1, "maxLength": 80,
                    "description": (
                        "Visible text. Required for text/"
                        "heading; ignored for non-text types."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "One-sentence reason.",
                },
            },
            "required": [
                "parent_eid", "child_type", "child_eid",
                "child_text", "rationale",
            ],
        },
    }


def build_insert_tool_schema(
    pairs: list[dict[str, Any]],
    child_types: tuple[str, ...] = _APPENDABLE_TYPES,
) -> dict[str, Any]:
    pair_indices = list(range(len(pairs)))
    return {
        "name": "emit_insert_edit",
        "description": (
            "Emit one `insert into=@parent after=@anchor { ... }` "
            "statement adding a new sibling immediately after an "
            "existing anchor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pair_index": {
                    "type": "integer", "enum": pair_indices,
                    "description": (
                        "Index into the (parent, anchor) pair "
                        "list."
                    ),
                },
                "child_type": {
                    "type": "string",
                    "enum": list(child_types),
                },
                "child_eid": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9-]{1,38}$",
                },
                "child_text": {
                    "type": "string",
                    "minLength": 1, "maxLength": 80,
                },
                "rationale": {"type": "string"},
            },
            "required": [
                "pair_index", "child_type", "child_eid",
                "child_text", "rationale",
            ],
        },
    }


def build_move_tool_schema(
    pairs: list[dict[str, Any]],
) -> dict[str, Any]:
    pair_indices = list(range(len(pairs)))
    return {
        "name": "emit_move_edit",
        "description": (
            "Emit one `move @target to=@dest position=first|last` "
            "statement relocating a node to a new parent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pair_index": {
                    "type": "integer", "enum": pair_indices,
                },
                "position": {
                    "type": "string",
                    "enum": ["first", "last"],
                },
                "rationale": {"type": "string"},
            },
            "required": ["pair_index", "position", "rationale"],
        },
    }


# Property identifier shape — same kebab/dot pattern grammar accepts
# (e.g. ``variant``, ``layout.gap``, ``$ext.nid``). The capability
# table at apply time is what gates which properties are valid for
# which type; the schema is permissive at the syntax layer.
_PROPERTY_PATTERN = r"^[a-z][a-z0-9.\-_$]{0,40}$"


def build_set_tool_schema(eids: list[str]) -> dict[str, Any]:
    """Stage 1.1 — `set @<eid> <prop>=<value>` schema.

    The most-common edit verb in repair / variant flows. Schema
    constrains ``target_eid`` to the doc's actual eid set (no
    hallucination). ``property`` is open at the schema layer
    (kebab-case pattern only) — apply_edits + the per-backend
    capability table do the closed-set rejection at apply time. Per
    plan §1.4 principle: keep dispatch fields closed, addressing /
    label fields open.
    """
    return {
        "name": "emit_set_edit",
        "description": (
            "Emit one `set @<eid> <property>=<value>` statement "
            "modifying a single property on an existing node. Use "
            "for variant flips (variant=disabled), text content "
            "(label=\"Save\"), token rebinds (color={color.brand.600})"
            ", and other single-property updates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_eid": {
                    "type": "string", "enum": eids,
                    "description": "Eid of the node to modify.",
                },
                "property": {
                    "type": "string",
                    "pattern": _PROPERTY_PATTERN,
                    "description": (
                        "Property key (e.g. `variant`, `label`, "
                        "`color`, `layout.gap`). Must be a valid "
                        "property for the target's type per the "
                        "capability table — apply will reject "
                        "unknown keys at apply time."
                    ),
                },
                "value": {
                    "type": "string",
                    "description": (
                        "Property value as a string. May be a "
                        "literal (\"Save\"), an enum value "
                        "(disabled), a number (16), or a token "
                        "reference ({color.brand.600})."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "One-sentence reason.",
                },
            },
            "required": ["target_eid", "property", "value", "rationale"],
        },
    }


def build_swap_tool_schema(
    eids: list[str],
    component_paths: list[str],
) -> dict[str, Any]:
    """Stage 1.1 — `swap @<eid> with=-> <component_path>` schema.

    Pivots an existing instance to a different component master
    (Mode-1 swap). Distinct from `replace` (subtree substitution).
    ``with_component`` is enum-constrained to the project's CKR so
    the LLM can't hallucinate component names like
    ``icon/menu-v2``.
    """
    return {
        "name": "emit_swap_edit",
        "description": (
            "Emit one `swap @<eid> with=-> <component_path>` "
            "statement pivoting an existing instance to a different "
            "library component. Pick the with_component from the "
            "project's known component paths."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_eid": {
                    "type": "string", "enum": eids,
                    "description": "Eid of the instance to swap.",
                },
                "with_component": {
                    "type": "string",
                    "enum": component_paths,
                    "description": (
                        "Path of the replacement library "
                        "component (e.g. `icon/close`, "
                        "`button/primary/lg`). Must already exist "
                        "in the project's CKR."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "One-sentence reason.",
                },
            },
            "required": ["target_eid", "with_component", "rationale"],
        },
    }


def build_replace_tool_schema(
    eids: list[str],
    child_types: tuple[str, ...] = _APPENDABLE_TYPES,
) -> dict[str, Any]:
    """Stage 1.1 — `replace @<eid> { ... }` schema.

    Wholesale subtree substitution. The replacement subtree's root
    follows the same flat-row shape used elsewhere (catalog type +
    new kebab-case eid + visible text). Reuses
    ``_APPENDABLE_TYPES`` for the new root type so the LLM can't
    swap in a `screen` mid-tree.
    """
    return {
        "name": "emit_replace_edit",
        "description": (
            "Emit one `replace @<eid> { TYPE #NEW_EID \"TEXT\" }` "
            "statement swapping the named subtree for a fresh one. "
            "Use when the existing subtree's structure is wrong; "
            "use `swap` when only the master needs to change."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_eid": {
                    "type": "string", "enum": eids,
                    "description": "Eid of the subtree to replace.",
                },
                "replacement_root_type": {
                    "type": "string",
                    "enum": list(child_types),
                    "description": "Type of the new subtree's root.",
                },
                "replacement_root_eid": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9-]{1,38}$",
                    "description": (
                        "Globally-unique kebab-case eid for the "
                        "new root (no leading @)."
                    ),
                },
                "replacement_root_text": {
                    "type": "string",
                    "minLength": 0, "maxLength": 80,
                    "description": (
                        "Visible text for the new root. Required "
                        "for text/heading; ignored for non-text "
                        "types."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "One-sentence reason.",
                },
            },
            "required": [
                "target_eid", "replacement_root_type",
                "replacement_root_eid", "rationale",
            ],
        },
    }


# ---------------------------------------------------------------
# Verifiers (post-apply AST inspection)
# ---------------------------------------------------------------


def verify_deleted(doc, target_eid: str) -> bool:
    """Target eid is absent from the applied doc."""
    for n in _walk_nodes(doc):
        if n.head.eid == target_eid:
            return False
    return True


def verify_appended(
    doc, parent_eid: str, child_eid: str,
) -> bool:
    """Parent now ends with a node whose eid is ``child_eid``."""
    for n in _walk_nodes(doc):
        if n.head.eid == parent_eid:
            block = getattr(n, "block", None)
            if block is None or not block.statements:
                return False
            last = block.statements[-1]
            return (
                hasattr(last, "head") and last.head.eid == child_eid
            )
    return False


def verify_inserted(
    doc, parent_eid: str, anchor_eid: str, child_eid: str,
) -> bool:
    """Parent's child sequence has ``child_eid`` immediately after
    ``anchor_eid``."""
    for n in _walk_nodes(doc):
        if n.head.eid != parent_eid:
            continue
        block = getattr(n, "block", None)
        if block is None:
            return False
        stmts = list(block.statements)
        for i, s in enumerate(stmts[:-1]):
            if hasattr(s, "head") and s.head.eid == anchor_eid:
                nxt = stmts[i + 1]
                return (
                    hasattr(nxt, "head")
                    and nxt.head.eid == child_eid
                )
    return False


def verify_moved(
    doc, target_eid: str, dest_eid: str,
    position: str,
) -> bool:
    """Target is now a direct child of dest, at the requested end."""
    for n in _walk_nodes(doc):
        if n.head.eid != dest_eid:
            continue
        block = getattr(n, "block", None)
        if block is None or not block.statements:
            return False
        stmts = [s for s in block.statements if hasattr(s, "head")]
        if not stmts:
            return False
        pick = stmts[0] if position == "first" else stmts[-1]
        return pick.head.eid == target_eid
    return False


def extract_tool_call(response, tool_name: str) -> Optional[dict]:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != tool_name:
            continue
        inp = getattr(block, "input", None)
        if isinstance(inp, dict):
            return inp
    return None
