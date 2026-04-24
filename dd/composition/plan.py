"""Plan-then-fill orchestrator for the ADR-008 v0.1.5 A2 uplift.

Two-stage Haiku composition behind ``DD_ENABLE_PLAN_THEN_FILL=1``:

1. **Plan call** — Haiku returns a pruned IR tree
   ``[{type, id, count_hint?, children?}]`` describing the skeleton.
   No props, no text.
2. **Validator** — rejects unknown types / invalid count_hints /
   duplicate ids before we spend the fill call.
3. **Fill call** — Haiku takes the pinned plan and emits a fleshed-
   out component list in the same shape today's A1 returns
   (``[{type, props?, children?, component_key?, variant?}]``).
4. **Plan-diff** — walks plan vs fill; if fill drops any planned type
   or undercounts a ``count_hint``, fire one fill retry with the plan
   restated. On second failure emit ``KIND_PLAN_INVALID``.

Default remains the A1 path; ``prompt_to_figma`` checks the flag.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from dd.catalog import CATALOG_ENTRIES


_HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Catalog allowlist for plan types. Built from the seed at import time.
_VALID_TYPES: frozenset[str] = frozenset({
    entry["canonical_name"] for entry in CATALOG_ENTRIES
})

# A plan-time clarification refusal uses the same prose-length signal
# as A1 so the pipeline routes the two outcomes identically.
_CLARIFICATION_PROSE_MIN_CHARS = 100


# --------------------------------------------------------------------------- #
# Errors                                                                      #
# --------------------------------------------------------------------------- #

class PlanValidationError(ValueError):
    """Raised when the plan LLM's output fails the shape/type checks."""


@dataclass(frozen=True)
class PlanDiff:
    """Result of comparing a plan vs a fill output."""

    missing_types: list[str] = field(default_factory=list)
    undercount: list[str] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        return bool(self.missing_types or self.undercount)


# --------------------------------------------------------------------------- #
# Validation                                                                  #
# --------------------------------------------------------------------------- #

def _walk_plan(nodes: list[dict]):
    """Depth-first iterator yielding (depth, node) tuples."""
    stack: list[tuple[int, dict]] = [(0, n) for n in reversed(nodes)]
    while stack:
        depth, node = stack.pop()
        yield depth, node
        children = node.get("children")
        if isinstance(children, list):
            for child in reversed(children):
                if isinstance(child, dict):
                    stack.append((depth + 1, child))


def validate_plan(plan: Any) -> None:
    """Raise ``PlanValidationError`` if the plan isn't shaped correctly.

    Rules:
    - Root must be a list of nodes.
    - Every node has string ``type`` in the catalog allowlist.
    - Every node has a string ``id``; ids unique across the tree.
    - ``count_hint`` if present is an int ≥ 1.
    - ``children`` if present is a list of further nodes.
    """
    if not isinstance(plan, list):
        raise PlanValidationError("plan must be a JSON array at root")

    seen_ids: set[str] = set()
    for depth, node in _walk_plan(plan):
        if not isinstance(node, dict):
            raise PlanValidationError(f"node must be a dict (got {type(node).__name__})")

        node_type = node.get("type")
        if not isinstance(node_type, str):
            raise PlanValidationError(f"missing 'type' at depth {depth}")
        if node_type not in _VALID_TYPES:
            raise PlanValidationError(
                f"unknown type {node_type!r} at depth {depth} "
                f"— not in catalog"
            )

        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise PlanValidationError(
                f"missing 'id' on {node_type!r} node at depth {depth}"
            )
        if node_id in seen_ids:
            raise PlanValidationError(
                f"duplicate id {node_id!r} at depth {depth}"
            )
        seen_ids.add(node_id)

        if "count_hint" in node:
            ch = node["count_hint"]
            if not isinstance(ch, int) or isinstance(ch, bool) or ch < 1:
                raise PlanValidationError(
                    f"count_hint on {node_id!r} must be int ≥ 1 (got {ch!r})"
                )

        if "children" in node and not isinstance(node["children"], list):
            raise PlanValidationError(
                f"children on {node_id!r} must be a list"
            )


# --------------------------------------------------------------------------- #
# Plan-diff                                                                   #
# --------------------------------------------------------------------------- #

def _flatten_types(nodes: list[dict]) -> list[str]:
    out: list[str] = []
    for _depth, node in _walk_plan(nodes):
        t = node.get("type")
        if isinstance(t, str):
            out.append(t)
    return out


def _count_hint_expectations(plan: list[dict]) -> Counter[str]:
    """Aggregate minimum expected counts per type across the plan.

    A plan node with ``count_hint=N`` contributes N to its type's
    expected count. Implicit count_hint is 1.
    """
    expected: Counter[str] = Counter()
    for _depth, node in _walk_plan(plan):
        t = node.get("type")
        if not isinstance(t, str):
            continue
        ch = node.get("count_hint", 1)
        if not isinstance(ch, int) or ch < 1:
            ch = 1
        expected[t] += ch
    return expected


def plan_diff(plan: list[dict], fill: list[dict]) -> PlanDiff:
    """Compare a plan against a fill output.

    - **missing_types**: plan types absent from fill entirely.
    - **undercount**: types whose count in fill is < plan expectation.

    Oversupply is not drift; the LLM expanding a pattern beyond the
    count_hint is fine.
    """
    expected = _count_hint_expectations(plan)
    fill_counts = Counter(_flatten_types(fill))

    missing: list[str] = []
    undercount: list[str] = []
    for t, want in expected.items():
        got = fill_counts.get(t, 0)
        if got == 0:
            missing.append(f"{t} (expected {want}, got 0)")
        elif got < want:
            undercount.append(f"{t} (expected {want}, got {got})")
    return PlanDiff(missing_types=missing, undercount=undercount)


# --------------------------------------------------------------------------- #
# Plan / fill prompts                                                         #
# --------------------------------------------------------------------------- #

def _build_plan_system() -> str:
    """Compose the plan SYSTEM prompt with the catalog allowlist baked in.

    The first run of 00h showed Haiku confidently inventing types like
    ``container`` / ``footer`` / ``carousel`` when the catalog wasn't
    explicitly listed. Failing closed at the validator is the right
    behaviour, but it burns plan calls — so the allowlist is in the
    prompt, not just the validator.

    Stage 0.1 + 0.2: `frame` is now in the vocabulary as the neutral
    structural primitive, and the old coercion rules (section → card /
    footer → card / carousel → list of card / hero → card) are gone.
    Those rules were patching a missing primitive with semantic-type
    flattening — Defect B of docs/plan-authoring-loop.md §1.2.
    """
    types_sorted = sorted(_VALID_TYPES)
    return (
        "You are a UI structural planner. Given a natural language screen "
        "description, emit a JSON array describing the screen's structural "
        "skeleton — types + nesting only, no text or props.\n\n"
        "Each node:\n"
        "  - type: string, MUST be one of the catalog types below\n"
        "  - id: string, unique within the tree\n"
        "  - children: optional array of further nodes\n"
        "  - count_hint: optional int ≥ 1 when a child is a repeated template\n\n"
        "Catalog types (use ONLY these):\n"
        f"  {', '.join(types_sorted)}\n\n"
        "For conceptual groupings — a section, a wrapper, a layout "
        "region that isn't itself a semantic component — use `frame`. "
        "`frame` is a neutral layout container; name it meaningfully "
        "via `id` (e.g. `product-showcase-section`, `action-bar`). "
        "Do NOT coerce conceptual groupings onto `card`; a `card` is a "
        "card, not a section.\n\n"
        "Container types that typically need count_hint on their child "
        "template: list (count_hint ≥ 4 for feeds), button_group "
        "(count_hint ≥ 2), pagination, toggle_group, segmented_control, "
        "navigation_row list, table rows.\n\n"
        "Example:\n"
        '[\n'
        '  {"type": "header", "id": "hdr", "children": [\n'
        '    {"type": "icon_button", "id": "back"},\n'
        '    {"type": "text", "id": "title"}\n'
        '  ]},\n'
        '  {"type": "frame", "id": "product-showcase-section", "children": [\n'
        '    {"type": "heading", "id": "section-title"},\n'
        '    {"type": "card", "id": "feature-card", "count_hint": 3}\n'
        '  ]}\n'
        ']\n\n'
        "Output ONLY the JSON array. No prose. No markdown fences."
    )


_PLAN_SYSTEM = _build_plan_system()


# --------------------------------------------------------------------------- #
# Stage 0.3 + 0.7 — flat named-node plan contract                             #
# --------------------------------------------------------------------------- #
#
# The flat-row contract replaces the nested tree that forces the LLM to
# pre-decide every child inside every parent. Instead:
#
#   {"nodes": [
#     {"eid": "...", "type": "...", "parent_eid": "..." | null,
#      "order": <int>, "repeat": <int>?},
#     ...
#   ]}
#
# Every node is individually addressable downstream. Parent-child
# relationships live in parent_eid. Position in the parent's child list
# lives in `order`. `repeat: N` expands at the adapter layer to N
# numbered siblings (`<eid>__1`, `<eid>__2`, ...), so compose never
# sees repeat semantics. See docs/plan-authoring-loop.md §0.3 / §0.7.


def validate_flat_plan(plan: Any) -> None:
    """Validate a flat-node plan. Raises :class:`PlanValidationError`
    on any shape issue.

    Rules:
    - Root is a dict with a "nodes" key → list of node dicts.
    - Every node has string ``eid`` (unique across the plan).
    - Every node has string ``type`` in the catalog allowlist.
    - Every node has integer ``order`` ≥ 0.
    - ``parent_eid`` is either None or another node's eid.
    - ``repeat`` if present is int ≥ 1.

    Does NOT enforce cycle-freedom beyond parent-eid existence; a
    self-cycle (``parent_eid == eid``) is caught separately below.
    """
    if not isinstance(plan, dict):
        raise PlanValidationError(
            "flat plan must be a JSON object with a 'nodes' key"
        )
    nodes = plan.get("nodes")
    if not isinstance(nodes, list):
        raise PlanValidationError("flat plan missing 'nodes' array")

    seen_eids: set[str] = set()
    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise PlanValidationError(
                f"flat plan node at index {idx} must be a dict "
                f"(got {type(node).__name__})"
            )
        eid = node.get("eid")
        if not isinstance(eid, str) or not eid:
            raise PlanValidationError(
                f"flat plan node at index {idx} missing 'eid'"
            )
        if eid in seen_eids:
            raise PlanValidationError(
                f"flat plan has duplicate eid {eid!r}"
            )
        seen_eids.add(eid)

        node_type = node.get("type")
        if not isinstance(node_type, str) or not node_type:
            raise PlanValidationError(
                f"flat plan node {eid!r} missing 'type'"
            )
        if node_type not in _VALID_TYPES:
            raise PlanValidationError(
                f"flat plan node {eid!r} has unknown type {node_type!r}"
            )

        order = node.get("order")
        if not isinstance(order, int) or isinstance(order, bool) or order < 0:
            raise PlanValidationError(
                f"flat plan node {eid!r} 'order' must be int ≥ 0 "
                f"(got {order!r})"
            )

        if "repeat" in node:
            r = node["repeat"]
            if not isinstance(r, int) or isinstance(r, bool) or r < 1:
                raise PlanValidationError(
                    f"flat plan node {eid!r} 'repeat' must be int ≥ 1 "
                    f"(got {r!r})"
                )

    # Second pass: validate parent_eid references.
    for node in nodes:
        parent_eid = node.get("parent_eid")
        if parent_eid is None:
            continue
        if not isinstance(parent_eid, str):
            raise PlanValidationError(
                f"flat plan node {node['eid']!r} 'parent_eid' must be "
                f"string or null (got {type(parent_eid).__name__})"
            )
        if parent_eid == node["eid"]:
            raise PlanValidationError(
                f"flat plan node {node['eid']!r} cannot be its own parent_eid"
            )
        if parent_eid not in seen_eids:
            raise PlanValidationError(
                f"flat plan node {node['eid']!r} references unknown "
                f"parent_eid {parent_eid!r}"
            )


def flat_plan_to_tree(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Adapt a flat-row plan to the legacy nested-tree shape.

    The tree shape is what ``_fill_system`` + ``compose_screen``
    consume today. Keeping the adapter out of compose means Stage 0
    doesn't rewrite compose; a later stage can delete this adapter
    and teach compose the flat shape directly.

    ``repeat: N`` expands deterministically to ``<eid>__1``,
    ``<eid>__2`` … so downstream sees concrete sibling nodes with
    unique eids and no repeat semantics to interpret.

    Precondition: ``plan`` has passed :func:`validate_flat_plan`.
    """
    nodes: list[dict[str, Any]] = plan.get("nodes", [])

    # Group nodes by parent_eid in stable (order, list-position) order
    children_of: dict[str | None, list[dict[str, Any]]] = {}
    for flat in nodes:
        parent = flat.get("parent_eid")
        children_of.setdefault(parent, []).append(flat)

    for bucket in children_of.values():
        bucket.sort(key=lambda n: (n.get("order", 0)))

    def _build(flat_node: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the 1..N tree nodes this flat row expands to."""
        eid = flat_node["eid"]
        node_type = flat_node["type"]
        repeat = flat_node.get("repeat", 1) or 1

        # Child subtrees are shared across the repeat expansion (one
        # build per canonical eid, cloned per repetition). Shared
        # references are safe because the tree is purely structural —
        # no runtime mutation downstream.
        kids: list[dict[str, Any]] = []
        for child_flat in children_of.get(eid, []):
            kids.extend(_build(child_flat))

        if repeat == 1:
            tree_node: dict[str, Any] = {"type": node_type, "id": eid}
            if kids:
                tree_node["children"] = kids
            return [tree_node]

        expanded: list[dict[str, Any]] = []
        for i in range(1, repeat + 1):
            tn: dict[str, Any] = {"type": node_type, "id": f"{eid}__{i}"}
            if kids:
                # Each repetition deep-shares structure but needs its
                # own children list so downstream mutation (if any)
                # doesn't smear across siblings.
                tn["children"] = list(kids)
            expanded.append(tn)
        return expanded

    roots: list[dict[str, Any]] = []
    for flat in children_of.get(None, []):
        roots.extend(_build(flat))
    return roots


def _build_flat_plan_system() -> str:
    """Flat-plan system prompt (Stage 0.7).

    The contract the LLM must follow is explicit:

    - ``type`` is CLOSED vocabulary (enum from the catalog).
    - ``eid`` is OPEN vocabulary (LLM invents meaningful kebab-case
      names).
    - ``parent_eid`` is an existing ``eid`` or ``null`` for roots.
    - ``order`` is the integer position within the parent's child list.
    - ``repeat: N`` expands to N deterministically-numbered siblings.
    - Conceptual groupings (section / wrapper / layout region) use
      ``type="frame"``, named via ``eid``.
    - The nested ``children`` array is forbidden; parent-child lives
      in ``parent_eid``.
    """
    types_sorted = sorted(_VALID_TYPES)
    return (
        "You are a UI structural planner. Given a natural language screen "
        "description, emit a flat table of named nodes addressed by "
        "parent_eid.\n\n"
        "HARD CONTRACT:\n"
        "- `type` is CLOSED vocabulary. Use only the catalog types below.\n"
        "- `eid` is OPEN vocabulary. Invent meaningful kebab-case names "
        "freely (e.g. `product-showcase-section`, `save-button`, "
        "`feature-card`). Every node must have its own unique eid.\n"
        "- `parent_eid` is the eid of the parent node, or null for "
        "roots. No node can be its own parent.\n"
        "- `order` is the integer position within the parent's child "
        "list (0-based). Lower numbers render first.\n"
        "- `repeat: N` (optional, N ≥ 1) asks the runtime to expand "
        "this node to N deterministically-numbered siblings "
        "(`<eid>__1`, `<eid>__2`, ... `<eid>__N`). Use for repeated "
        "templates like card grids or list items.\n"
        "- DO NOT emit a nested `children` array — nesting lives in "
        "`parent_eid`.\n"
        "- DO NOT invent primitive types. Use `frame` for conceptual "
        "groupings (section / wrapper / region); a `card` is a card, "
        "not a section.\n\n"
        "Catalog types (use ONLY these):\n"
        f"  {', '.join(types_sorted)}\n\n"
        "Output format — a single JSON object with a `nodes` array:\n"
        "{\n"
        '  "nodes": [\n'
        '    {"eid": "screen-root", "type": "frame", "parent_eid": null, "order": 0},\n'
        '    {"eid": "top-nav", "type": "header", "parent_eid": "screen-root", "order": 0},\n'
        '    {"eid": "product-showcase-section", "type": "frame", "parent_eid": "screen-root", "order": 1},\n'
        '    {"eid": "section-title", "type": "heading", "parent_eid": "product-showcase-section", "order": 0},\n'
        '    {"eid": "feature-card", "type": "card", "parent_eid": "product-showcase-section", "order": 1, "repeat": 3}\n'
        "  ]\n"
        "}\n\n"
        "Output ONLY the JSON object. No prose. No markdown fences."
    )


# --------------------------------------------------------------------------- #
# Stage 0.5 — slot name validation (log-only)                                 #
# --------------------------------------------------------------------------- #

_CATALOG_SLOT_SETS: dict[str, frozenset[str]] | None = None


def _catalog_slot_sets() -> dict[str, frozenset[str]]:
    """Build the per-type declared-slot-name index from CATALOG_ENTRIES.

    Lazily populated so import order stays light. Types whose catalog
    entry lacks ``slot_definitions`` don't get a set — callers treat
    absence as "accept any slot name" (structural types like ``frame``
    are the motivating case).
    """
    global _CATALOG_SLOT_SETS
    if _CATALOG_SLOT_SETS is None:
        sets: dict[str, frozenset[str]] = {}
        for entry in CATALOG_ENTRIES:
            slots = entry.get("slot_definitions")
            if not slots:
                continue
            # The `_default` slot is a wildcard ("any child goes here");
            # its presence alone shouldn't constrain named-slot names.
            named = {k for k in slots.keys() if k != "_default"}
            if named:
                sets[entry["canonical_name"]] = frozenset(named)
        _CATALOG_SLOT_SETS = sets
    return _CATALOG_SLOT_SETS


def validate_flat_plan_slots(plan: dict[str, Any]) -> list[Any]:
    """Surface slot-name violations as structured warnings.

    For each flat-plan node that carries a ``slot`` field, check that
    the parent type's catalog entry declares that slot name. Log-only
    per docs/plan-authoring-loop.md §8 decision 3: Stage 0 never
    blocks composition on an unknown slot; Stage 1 tightens to
    hard-error once real-run telemetry shows the planner isn't
    hallucinating.

    Returns a list of :class:`StructuredError` entries with kind
    :data:`KIND_SLOT_UNKNOWN` — empty when every slot name is valid
    or the parent type has no declared named slots.

    Precondition: ``plan`` has passed :func:`validate_flat_plan` so
    every ``parent_eid`` references an existing node.
    """
    # Local imports so the boundary / StructuredError chain doesn't
    # get pulled into the module's already-hot import path.
    from dd.boundary import KIND_SLOT_UNKNOWN, StructuredError

    nodes = plan.get("nodes") or []
    eid_to_type: dict[str, str] = {
        n["eid"]: n["type"] for n in nodes if isinstance(n, dict) and n.get("eid")
    }
    slot_sets = _catalog_slot_sets()
    warnings: list[Any] = []

    for node in nodes:
        slot_name = node.get("slot")
        if not slot_name:
            continue
        parent_eid = node.get("parent_eid")
        if parent_eid is None:
            continue
        parent_type = eid_to_type.get(parent_eid)
        if parent_type is None:
            continue
        allowed = slot_sets.get(parent_type)
        if allowed is None:
            # Parent type has no closed slot set — can't enforce.
            continue
        if slot_name in allowed:
            continue
        warnings.append(StructuredError(
            kind=KIND_SLOT_UNKNOWN,
            id=f"{parent_type}/{slot_name}",
            error=(
                f"slot {slot_name!r} on parent type {parent_type!r} is not "
                f"in the catalog's declared slot set "
                f"{sorted(allowed)}"
            ),
            context={
                "parent_type": parent_type,
                "parent_eid": parent_eid,
                "child_eid": node.get("eid"),
                "slot": slot_name,
                "allowed": sorted(allowed),
            },
        ))
    return warnings


# --------------------------------------------------------------------------- #
# Stage 0.6 — structural drift check                                          #
# --------------------------------------------------------------------------- #

def flat_plan_drift(
    plan: dict[str, Any],
    spec_elements: dict[str, dict[str, Any]],
    *,
    root_eid: str | None = None,
) -> list[Any]:
    """Compare the flat plan's intent against the compose output.

    For each planner-named node, check that compose produced:
    - an element with that eid (or the ``repeat``-expanded siblings),
    - with the planner-intended type,
    - under a parent that matches the planner-intended parent_eid
      (via the spec's ``children`` adjacency).

    Extra Mode-3-synthesised children (e.g. a button's text label)
    that the planner never named are NOT drift — the plan is a floor,
    not a ceiling.

    Returns a list of :class:`StructuredError` with kind
    :data:`KIND_PLAN_DRIFT`. Empty when compose preserved the plan.

    ``root_eid`` is the eid of the compose spec's root element; if
    omitted, we try to infer by scanning for the single element
    whose type is ``screen``.
    """
    from dd.boundary import KIND_PLAN_DRIFT, StructuredError

    nodes: list[dict[str, Any]] = plan.get("nodes") or []

    # Expand repeat-flagged rows to their concrete sibling eids so the
    # downstream check is per-concrete-eid, not per-template.
    expected: list[tuple[str, str, str | None]] = []  # (eid, type, parent_eid)
    for node in nodes:
        eid = node.get("eid")
        type_ = node.get("type")
        parent_eid = node.get("parent_eid")
        if not (isinstance(eid, str) and isinstance(type_, str)):
            continue
        repeat = node.get("repeat", 1) or 1
        if repeat <= 1:
            expected.append((eid, type_, parent_eid))
        else:
            for i in range(1, repeat + 1):
                expected.append((f"{eid}__{i}", type_, parent_eid))

    # Invert spec_elements to an (eid → parent_eid) map. The compose
    # root has no parent (or its parent is the screen wrapper).
    child_to_parent: dict[str, str | None] = {}
    for parent, el in spec_elements.items():
        for child in el.get("children") or []:
            child_to_parent[child] = parent

    # If the plan's "root" parent_eid is None but compose nests
    # everything under a screen-wrapper root, translate the None to
    # that wrapper so the comparison doesn't spuriously drift.
    inferred_root = root_eid
    if inferred_root is None:
        for eid, el in spec_elements.items():
            if el.get("type") == "screen":
                inferred_root = eid
                break

    warnings: list[Any] = []
    for eid, type_, parent_eid in expected:
        el = spec_elements.get(eid)
        if el is None:
            warnings.append(StructuredError(
                kind=KIND_PLAN_DRIFT,
                id=eid,
                error=f"planner-named eid {eid!r} missing from compose output",
                context={"eid": eid, "expected_type": type_, "expected_parent": parent_eid},
            ))
            continue
        if el.get("type") != type_:
            warnings.append(StructuredError(
                kind=KIND_PLAN_DRIFT,
                id=eid,
                error=(
                    f"planner-named eid {eid!r} expected type {type_!r} "
                    f"but compose produced {el.get('type')!r}"
                ),
                context={"eid": eid, "expected_type": type_, "got_type": el.get("type")},
            ))
            continue
        got_parent = child_to_parent.get(eid)
        expected_parent = parent_eid if parent_eid is not None else inferred_root
        if got_parent != expected_parent:
            warnings.append(StructuredError(
                kind=KIND_PLAN_DRIFT,
                id=eid,
                error=(
                    f"planner-named eid {eid!r} expected under parent "
                    f"{expected_parent!r} but compose put it under "
                    f"{got_parent!r}"
                ),
                context={
                    "eid": eid,
                    "expected_parent": expected_parent,
                    "got_parent": got_parent,
                },
            ))
    return warnings


def _fill_system(plan: list[dict]) -> str:
    """Two-pass plan-then-fill internals — synthesize-from-prompt path.

    DEPRECATED (Stage 1.6 — docs/plan-authoring-loop.md §4.1, soft
    deprecation per Codex 2026-04-23): the plan calls for deletion
    once propose_edits replaces it. propose_edits today only handles
    the EDIT mode (existing doc + prompt → one edit); the SYNTHESIZE
    mode (free-text prompt → fresh component list) is still owned
    by plan_then_fill via dd.prompt_parser.prompt_to_figma — the
    production composition path.

    Removal gate: delete when EITHER (a) prompt_to_figma migrates to
    a propose_edits-against-empty-doc loop, OR (b) `dd design`
    (Stage 3) becomes the primary natural-language entry point and
    prompt_to_figma is itself deleted. Until then, the two-pass
    contract is load-bearing for real prompts.

    See also: ``_extract_plan``, ``_extract_fill`` (same gate).
    """
    return (
        "You are a UI composition assistant filling a pre-planned "
        "skeleton. The plan (authoritative structure) is below. Emit "
        "the final component JSON array that realizes the plan: use "
        "the same nesting and at LEAST the count_hint child counts, "
        "fill in text via props, add variant / component_key where "
        "the project's vocabulary supports it.\n\n"
        "Plan:\n"
        f"```json\n{json.dumps(plan, indent=2)}\n```\n\n"
        "Rules:\n"
        "- Preserve the plan's top-level types in order.\n"
        "- For nodes with count_hint=N, emit ≥ N instances of that "
        "  type in that position.\n"
        "- You MAY add extra leaf nodes (e.g. trailing buttons) that "
        "  aren't in the plan — the plan is a floor, not a ceiling.\n"
        "- Fill text via props.text / props.label. Don't invent types "
        "  outside the catalog.\n\n"
        "Output ONLY the JSON array."
    )


def _extract_plan(raw_text: str) -> list[dict] | dict | None:
    """Pull the planner's JSON payload from ``raw_text``.

    Two acceptable shapes (Stage 0 Option C — both supported so the
    legacy path stays working until Stage 1 removes it):

    - Flat-plan object: ``{"nodes": [...]}`` (the new contract).
    - Legacy tree array: ``[{...}, {...}]`` (the old contract).

    Returns the parsed shape as-is (dict or list). Returns
    ``{"_clarification_refusal": <prose>}`` for long prose responses
    the LLM used to refuse. Returns None for unparseable short noise.
    """
    text = raw_text
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1)

    # Try a top-level JSON object first — the new flat-plan contract.
    # The object must contain a "nodes" key to count as a flat plan.
    object_match = re.search(r"\{.*\}", text, re.DOTALL)
    if object_match:
        try:
            parsed_obj = json.loads(object_match.group(0))
            if isinstance(parsed_obj, dict) and "nodes" in parsed_obj:
                return parsed_obj
        except (json.JSONDecodeError, TypeError):
            pass

    # Fall back to the legacy tree array shape.
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        try:
            parsed = json.loads(bracket_match.group(0))
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

    prose = raw_text.strip()
    if len(prose) >= _CLARIFICATION_PROSE_MIN_CHARS:
        return {"_clarification_refusal": prose}
    return None


def _extract_fill(raw_text: str) -> list[dict]:
    """Same contract as plan extraction, but fill may return [] legitimately."""
    text = raw_text
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1)
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if not bracket_match:
        return []
    try:
        parsed = json.loads(bracket_match.group(0))
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


# --------------------------------------------------------------------------- #
# Orchestrator                                                                #
# --------------------------------------------------------------------------- #

def _plan_system_with_skeleton(skeleton: list[dict]) -> str:
    """Plan prompt with an archetype skeleton baked in as a floor.

    The first 00h run showed Haiku planning minimally when given only
    the catalog list — outputs had fewer elements than A1's archetype-
    injected skeletons. Treating the skeleton as a structural floor
    (not a template) recovers the A1 density without giving up A2's
    plan-diff guarantees.
    """
    return (
        _PLAN_SYSTEM + "\n\n"
        "Structural floor (a canonical skeleton for this prompt's "
        "archetype — your plan should include AT LEAST these nodes; "
        "you may enrich with more containers / items as the prompt "
        "warrants):\n"
        f"```json\n{json.dumps(skeleton, indent=2)}\n```\n\n"
        "Respect the skeleton's nesting; add count_hint ≥ the visible "
        "repetition (e.g. a list of cards → count_hint ≥ 4). Don't "
        "reduce its structure."
    )


def plan_then_fill(
    prompt: str,
    client: Any,
    *,
    archetype_skeleton: list[dict] | None = None,
) -> dict:
    """Orchestrate plan + validate + fill (+ one retry on drift).

    Stage 0.3 + 0.7: the default planner system prompt is the flat-
    node contract (``_build_flat_plan_system``). Legacy nested-tree
    responses still validate against ``validate_plan`` for
    backwards-compatibility while Stage 1 finishes. ``archetype_
    skeleton`` continues to use the legacy tree prompt because the
    archetype library hasn't been migrated to flat-row shape yet —
    that migration is deferred.

    The function preserves the LLM's ORIGINAL plan shape in the
    return value so callers (tests, drift check, session log) see
    what the planner actually emitted. Internally, the flat-row
    shape is adapted to the tree form for the fill prompt + plan_diff.

    Returns:
        On success: ``{"components": [...], "plan": <original shape>,
          "retried": bool}``.
        On clarification refusal: ``{"_clarification_refusal": <prose>}``.
        On validation / invariant failure: ``{"kind": "KIND_PLAN_INVALID",
          "detail": <str>, "plan": <shape or None>, "fill": <list or None>}``.
    """
    if not prompt or not prompt.strip():
        return {"components": [], "plan": None, "retried": False}

    if archetype_skeleton is not None:
        # Archetype injection still uses the legacy tree prompt —
        # archetype_library skeletons are tree-shaped. Migrating
        # them to flat-row is Stage 1 work.
        plan_system = _plan_system_with_skeleton(archetype_skeleton)
    else:
        plan_system = _build_flat_plan_system()

    # ── Stage 1: plan ────────────────────────────────────────────────────
    plan_resp = client.messages.create(
        model=_HAIKU_MODEL,
        max_tokens=1024,
        temperature=0.0,
        system=plan_system,
        messages=[{"role": "user", "content": prompt}],
    )
    plan_raw = plan_resp.content[0].text
    extracted = _extract_plan(plan_raw)

    if isinstance(extracted, dict) and "_clarification_refusal" in extracted:
        return {"_clarification_refusal": extracted["_clarification_refusal"]}

    # Dispatch on shape: flat-plan object vs legacy tree array.
    original_plan: list[dict] | dict
    tree_plan: list[dict]
    slot_warnings: list[Any] = []
    if isinstance(extracted, dict) and "nodes" in extracted:
        try:
            validate_flat_plan(extracted)
        except PlanValidationError as e:
            return {
                "kind": "KIND_PLAN_INVALID",
                "detail": str(e),
                "plan": extracted,
                "fill": None,
            }
        # Stage 0.5: slot names are closed per parent type — validate
        # log-only. Hallucinated slots surface as warnings but do NOT
        # block composition. Upgrades to hard-error in a Stage 1 PR.
        slot_warnings = validate_flat_plan_slots(extracted)
        original_plan = extracted
        tree_plan = flat_plan_to_tree(extracted)
    elif isinstance(extracted, list):
        try:
            validate_plan(extracted)
        except PlanValidationError as e:
            return {
                "kind": "KIND_PLAN_INVALID",
                "detail": str(e),
                "plan": extracted,
                "fill": None,
            }
        original_plan = extracted
        tree_plan = extracted
    else:
        return {
            "kind": "KIND_PLAN_INVALID",
            "detail": "plan LLM returned no parseable JSON array or object",
            "plan": None,
            "fill": None,
        }

    # ── Stage 2+3: fill (+ one retry on drift) ───────────────────────────
    fill_system = _fill_system(tree_plan)
    retried = False
    final_fill: list[dict] = []

    for attempt in range(2):
        fill_resp = client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=2048,
            temperature=0.3,
            system=fill_system,
            messages=[{"role": "user", "content": prompt}],
        )
        fill_components = _extract_fill(fill_resp.content[0].text)
        diff = plan_diff(tree_plan, fill_components)
        if not diff.has_drift:
            final_fill = fill_components
            break
        retried = True
        final_fill = fill_components  # keep last attempt in case we give up

    if diff.has_drift:
        return {
            "kind": "KIND_PLAN_INVALID",
            "detail": (
                f"fill drift after retry: missing={diff.missing_types} "
                f"undercount={diff.undercount}"
            ),
            "plan": original_plan,
            "fill": final_fill,
            "warnings": slot_warnings,
        }

    return {
        "components": final_fill,
        "plan": original_plan,
        "retried": retried,
        "warnings": slot_warnings,
    }
