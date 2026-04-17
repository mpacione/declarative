"""Structural measures for the v0.1.5 generation-density matrix.

Per the density-design memo §3.2 the matrix runner reduces each Haiku
response to eight structural dependent variables; this module is the
pure reduction step so the 00g driver stays a thin orchestrator.

The ninth measure — ``clarification_refusal`` — is the ADR-008 v0.1.5
pipeline-contract side-fix signal that lives alongside ``empty_output``
but is counted separately: a refusal is categorically better than a
blank array.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any


# The six container types whose non-empty emission counts toward the
# container-coverage score. Verbatim from the density-design memo §3.2
# measure 4; don't quietly add/drop without a memo update.
CONTAINER_TYPES: frozenset[str] = frozenset({
    "list",
    "button_group",
    "pagination",
    "toggle_group",
    "header",
    "table",
})


@dataclass(frozen=True)
class MatrixMeasures:
    """One cell's structural measures for one Haiku response."""

    total_node_count: int
    top_level_count: int
    max_depth: int
    container_coverage: int
    component_key_rate: float
    variant_rate: float
    json_valid: int
    empty_output: int
    clarification_refusal: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _iter_nodes(nodes: list[dict]):
    """Depth-first iterator yielding every node in the tree."""
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node
        children = node.get("children")
        if isinstance(children, list):
            yield from _iter_nodes(children)


def _tree_depth(nodes: list[dict], current: int = 1) -> int:
    best = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        children = node.get("children")
        if isinstance(children, list) and children:
            best = max(best, _tree_depth(children, current + 1))
        else:
            best = max(best, current)
    return best


def _container_coverage(nodes: list[dict]) -> int:
    emitted: set[str] = set()
    for node in _iter_nodes(nodes):
        node_type = node.get("type")
        if node_type not in CONTAINER_TYPES:
            continue
        children = node.get("children")
        if isinstance(children, list) and len(children) > 0:
            emitted.add(node_type)
    return len(emitted)


def _rate(predicate, nodes: list[dict]) -> float:
    total = 0
    hits = 0
    for node in _iter_nodes(nodes):
        total += 1
        if predicate(node):
            hits += 1
    return hits / total if total else 0.0


def _json_valid(raw_text: str, extracted: Any) -> int:
    """1 iff a JSON array was parseable from the raw text.

    Mirrors ``extract_json``'s own regex so the metric reflects what the
    pipeline actually sees. Refusal dicts and pure-noise strings are 0.
    """
    if isinstance(extracted, dict):
        return 0
    text = raw_text
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1)
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if not bracket_match:
        return 0
    try:
        parsed = json.loads(bracket_match.group(0))
    except (json.JSONDecodeError, TypeError):
        return 0
    return 1 if isinstance(parsed, list) else 0


def compute_measures(
    raw_text: str,
    extracted: list[dict] | dict[str, Any],
) -> MatrixMeasures:
    """Compute the 8+1 structural measures for one Haiku response.

    ``raw_text`` is the full LLM response string; ``extracted`` is
    whatever ``dd.prompt_parser.extract_json`` returned (either a list
    of component dicts, an empty list, or a clarification-refusal dict).
    """
    if isinstance(extracted, dict) and "_clarification_refusal" in extracted:
        return MatrixMeasures(
            total_node_count=0,
            top_level_count=0,
            max_depth=0,
            container_coverage=0,
            component_key_rate=0.0,
            variant_rate=0.0,
            json_valid=_json_valid(raw_text, extracted),
            empty_output=0,
            clarification_refusal=1,
        )

    components = extracted if isinstance(extracted, list) else []

    total = sum(1 for _ in _iter_nodes(components))
    top_level = len(components)
    depth = _tree_depth(components)
    coverage = _container_coverage(components)
    ck_rate = _rate(lambda n: bool(n.get("component_key")), components)
    var_rate = _rate(lambda n: bool(n.get("variant")), components)
    valid = _json_valid(raw_text, extracted)
    empty = 1 if top_level == 0 else 0

    return MatrixMeasures(
        total_node_count=total,
        top_level_count=top_level,
        max_depth=depth,
        container_coverage=coverage,
        component_key_rate=ck_rate,
        variant_rate=var_rate,
        json_valid=valid,
        empty_output=empty,
        clarification_refusal=0,
    )
