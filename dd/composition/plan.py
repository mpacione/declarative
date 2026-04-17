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
    """
    types_sorted = sorted(_VALID_TYPES)
    # Group for readability matching SYSTEM_PROMPT's categorisation.
    return (
        "You are a UI structural planner. Given a natural language screen "
        "description, emit a JSON array describing the screen's structural "
        "skeleton — types + nesting only, no text or props.\n\n"
        "Each node:\n"
        "  - type: string, MUST be one of the catalog types below\n"
        "  - id: string, unique within the tree\n"
        "  - children: optional array of further nodes\n"
        "  - count_hint: optional int ≥ 1 when a child is a repeated template\n\n"
        "Catalog types (use ONLY these — no 'container', 'footer', "
        "'carousel', 'section' etc.):\n"
        f"  {', '.join(types_sorted)}\n\n"
        "Mapping rules for common UI concepts that aren't in the catalog:\n"
        "  - a generic container / section / wrapper → use `card`\n"
        "  - a footer → use `card` at the bottom (there is no footer type)\n"
        "  - a carousel / slider → use `list` (count_hint ≥ 3) of `card` "
        "children\n"
        "  - a hero → use `card` with an `image` + `heading` + `text`\n\n"
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
        '  {"type": "list", "id": "feed", "children": [\n'
        '    {"type": "card", "id": "post", "count_hint": 4}\n'
        '  ]}\n'
        ']\n\n'
        "Output ONLY the JSON array. No prose. No markdown fences."
    )


_PLAN_SYSTEM = _build_plan_system()


def _fill_system(plan: list[dict]) -> str:
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
    """Pull the first JSON array from ``raw_text``.

    Mirrors ``dd.prompt_parser.extract_json`` but constrained to array
    output — the plan contract rules out dict responses (except the
    clarification-refusal sentinel).
    """
    text = raw_text
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1)
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

    Optional ``archetype_skeleton`` gets injected into the plan prompt
    as a structural floor — a canonical skeleton the plan must cover
    or exceed. Omit for a pure plan-then-fill (classifier returned
    None or flag off).

    Returns:
        On success: ``{"components": [...], "plan": [...], "retried": bool}``.
        On clarification refusal: ``{"_clarification_refusal": <prose>}``.
        On validation / invariant failure: ``{"kind": "KIND_PLAN_INVALID",
          "detail": <str>, "plan": <tree or None>, "fill": <list or None>}``.
    """
    if not prompt or not prompt.strip():
        return {"components": [], "plan": None, "retried": False}

    plan_system = (
        _plan_system_with_skeleton(archetype_skeleton)
        if archetype_skeleton is not None
        else _PLAN_SYSTEM
    )

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
    if not isinstance(extracted, list):
        return {
            "kind": "KIND_PLAN_INVALID",
            "detail": "plan LLM returned no parseable JSON array",
            "plan": None,
            "fill": None,
        }

    try:
        validate_plan(extracted)
    except PlanValidationError as e:
        return {
            "kind": "KIND_PLAN_INVALID",
            "detail": str(e),
            "plan": extracted,
            "fill": None,
        }

    plan: list[dict] = extracted

    # ── Stage 2+3: fill (+ one retry on drift) ───────────────────────────
    fill_system = _fill_system(plan)
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
        diff = plan_diff(plan, fill_components)
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
            "plan": plan,
            "fill": final_fill,
        }

    return {
        "components": final_fill,
        "plan": plan,
        "retried": retried,
    }
