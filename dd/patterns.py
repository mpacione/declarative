"""M7.0.e — rule-of-three pattern extraction from classified
instances.

Finds subtree shapes that repeat across ≥N distinct screens and
persists each to the ``patterns`` table with an LLM-assigned name,
category, and human-readable description. The extracted patterns
are what M7.0.f (sticker-sheet reconciliation) and M7.6 (S4
composition) consume.

Shape signature (initial shipment):

    (parent_canonical_type, tuple(child_canonical_types))

— a one-level, order-sensitive signature. Multi-level matching is
deliberately deferred; one-level catches the most common
compositional patterns (nav-bar / card-row / toolbar / etc.) with
no ambiguity about what "the same shape" means.

Only structural parents qualify — ``container`` / ``icon`` / ``text``
/ ``frame`` / ``unsure`` are too generic to extract useful patterns
from. See ``_STRUCTURAL_PARENT_TYPES`` for the current set.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional


_STRUCTURAL_PARENT_TYPES: frozenset[str] = frozenset({
    "toolbar", "nav", "header", "footer", "card", "list_item",
    "drawer", "tabs", "select", "field_input", "chip", "menu_item",
    "modal", "dialog", "sheet",
})


_PATTERN_CATEGORIES: tuple[str, ...] = (
    "nav", "card", "form", "modal", "page", "section",
    "list", "toolbar", "menu",
)


_TRUSTED_CONSENSUS_METHODS: tuple[str, ...] = (
    "formal", "heuristic", "unanimous", "two_source_unanimous",
)


@dataclass
class PatternCandidate:
    """A subtree shape seen across multiple screens."""

    parent_type: str
    child_types: tuple[str, ...]
    screen_ids: list[int] = field(default_factory=list)

    @property
    def signature(self) -> tuple[str, tuple[str, ...]]:
        return (self.parent_type, self.child_types)


@dataclass
class PatternLabels:
    """LLM-assigned labels for a pattern candidate."""

    name: str
    category: str
    description: str


@dataclass
class PatternExtractionSummary:
    candidates: int = 0
    persisted: int = 0
    skipped_duplicate: int = 0
    llm_missing: int = 0


def collect_subtree_shapes(
    conn: sqlite3.Connection, *,
    parent_types: Optional[list[str]] = None,
    trust_filter: bool = True,
) -> dict[tuple[str, tuple[str, ...]], list[tuple[int, int]]]:
    """Walk every structural-typed SCI + its direct children, group
    by (parent_type, child_type_tuple), and return ``{signature:
    [(screen_id, parent_sci_id), ...]}``.

    Child ordering follows ``nodes.id`` ascending — approximates
    document order as it was captured during extraction. Children
    without a matching SCI row contribute ``"?"`` to the tuple
    rather than being dropped, so shape signatures stay stable
    across classifier re-runs.
    """
    types = tuple(parent_types or _STRUCTURAL_PARENT_TYPES)
    if not types:
        return {}

    placeholders = ",".join("?" * len(types))
    where_trust = ""
    args: list[Any] = list(types)
    if trust_filter:
        trust = ",".join("?" * len(_TRUSTED_CONSENSUS_METHODS))
        where_trust = (
            f" AND (sci.consensus_method IS NULL OR "
            f"sci.consensus_method IN ({trust}))"
        )
        args.extend(_TRUSTED_CONSENSUS_METHODS)

    rows = conn.execute(
        f"""
        SELECT sci.id AS parent_sci_id, sci.screen_id,
               sci.canonical_type AS parent_type,
               sci.node_id AS parent_node_id
          FROM screen_component_instances sci
         WHERE sci.canonical_type IN ({placeholders})
               {where_trust}
        """,
        args,
    ).fetchall()

    shapes: dict[
        tuple[str, tuple[str, ...]], list[tuple[int, int]]
    ] = defaultdict(list)

    for r in rows:
        child_rows = conn.execute(
            """
            SELECT child_sci.canonical_type AS ct
              FROM nodes child_n
         LEFT JOIN screen_component_instances child_sci
                ON child_sci.node_id = child_n.id
             WHERE child_n.parent_id = ?
             ORDER BY child_n.id
            """,
            (r["parent_node_id"],),
        ).fetchall()
        if not child_rows:
            continue
        child_tuple = tuple(cr["ct"] or "?" for cr in child_rows)
        key = (r["parent_type"], child_tuple)
        shapes[key].append((r["screen_id"], r["parent_sci_id"]))

    return dict(shapes)


def find_repeated_patterns(
    shapes: dict[tuple[str, tuple[str, ...]], list[tuple[int, int]]],
    *,
    min_screens: int = 3,
) -> list[PatternCandidate]:
    """Filter ``shapes`` to those seen on ``min_screens`` distinct
    screens (rule-of-three when min_screens=3).

    Returns candidates sorted by distinct-screen count descending —
    most-repeated patterns get the LLM-labeling budget first.
    """
    out: list[PatternCandidate] = []
    for (parent_type, child_tuple), hits in shapes.items():
        distinct = sorted({sid for sid, _ in hits})
        if len(distinct) < min_screens:
            continue
        out.append(
            PatternCandidate(
                parent_type=parent_type,
                child_types=child_tuple,
                screen_ids=distinct,
            )
        )
    out.sort(key=lambda p: (-len(p.screen_ids), p.parent_type))
    return out


def _build_pattern_label_tool_schema() -> dict[str, Any]:
    return {
        "name": "emit_pattern_label",
        "description": (
            "Emit a name, category, and short description for a "
            "repeating subtree pattern extracted from the corpus."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "minLength": 3,
                    "maxLength": 80,
                    "pattern": "^[a-z][a-z0-9/_-]*$",
                    "description": (
                        "Canonical pattern name, slash-delimited "
                        "like `toolbar/drawer-and-two-buttons` or "
                        "`card/image-title-actions`. Lowercase, "
                        "kebab-case within segments."
                    ),
                },
                "category": {
                    "type": "string",
                    "enum": list(_PATTERN_CATEGORIES),
                    "description": "Top-level category bucket.",
                },
                "description": {
                    "type": "string",
                    "minLength": 20,
                    "maxLength": 240,
                    "description": (
                        "One-to-two sentence plain-English "
                        "explanation of when a designer would "
                        "reach for this pattern."
                    ),
                },
            },
            "required": ["name", "category", "description"],
        },
    }


def _extract_tool_call(response, tool_name: str) -> Optional[dict]:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != tool_name:
            continue
        inp = getattr(block, "input", None)
        if isinstance(inp, dict):
            return inp
    return None


def label_pattern_with_llm(
    client, candidate: PatternCandidate, *,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 512,
) -> Optional[PatternLabels]:
    """Ask Claude for a canonical name + category + description for
    the given candidate. Returns ``None`` when the LLM doesn't emit
    the expected tool call (caller decides to retry or skip)."""
    tool_schema = _build_pattern_label_tool_schema()
    user = (
        f"### Repeating pattern detected\n"
        f"- parent canonical_type: {candidate.parent_type}\n"
        f"- child canonical_types (in order): "
        f"{list(candidate.child_types)}\n"
        f"- occurs on {len(candidate.screen_ids)} distinct screens: "
        f"{candidate.screen_ids[:10]}"
        f"{'…' if len(candidate.screen_ids) > 10 else ''}\n\n"
        "Emit a canonical name, category, and short description "
        "for this pattern via `emit_pattern_label`. The name is "
        "how a designer would refer to this structural family, "
        "e.g. `toolbar/drawer-and-two-buttons` or "
        "`card/image-title-actions`. Be specific — the name "
        "should distinguish this shape from similar ones."
    )
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": tool_schema["name"]},
        messages=[{"role": "user", "content": user}],
    )
    payload = _extract_tool_call(response, tool_schema["name"])
    if payload is None:
        return None
    try:
        return PatternLabels(
            name=payload["name"].strip(),
            category=payload["category"].strip(),
            description=payload["description"].strip(),
        )
    except (KeyError, AttributeError):
        return None


def persist_pattern(
    conn: sqlite3.Connection,
    candidate: PatternCandidate,
    labels: PatternLabels,
) -> bool:
    """Write one pattern row. Returns ``True`` on insert, ``False``
    when a row with the same name already exists (idempotent).

    Recipe JSON captures the structural signature + source
    candidate; M7.6 composition consumes this to pick a donor
    whose shape matches the target request.
    """
    recipe = {
        "parent_type": candidate.parent_type,
        "child_sequence": list(candidate.child_types),
        "distinct_screen_count": len(candidate.screen_ids),
    }
    try:
        conn.execute(
            """
            INSERT INTO patterns
                (name, category, recipe, description, source_screens)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                labels.name,
                labels.category,
                json.dumps(recipe, separators=(",", ":")),
                labels.description,
                json.dumps(candidate.screen_ids),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Unique-constraint violation on `name` — already inserted.
        return False


def run_pattern_extraction(
    conn: sqlite3.Connection, *,
    client=None,
    min_screens: int = 3,
    max_patterns: Optional[int] = None,
    dry_run: bool = False,
    parent_types: Optional[list[str]] = None,
    model: str = "claude-haiku-4-5-20251001",
) -> PatternExtractionSummary:
    """Orchestrator: collect shapes → find repeats → label → persist."""
    summary = PatternExtractionSummary()
    shapes = collect_subtree_shapes(conn, parent_types=parent_types)
    candidates = find_repeated_patterns(shapes, min_screens=min_screens)
    if max_patterns is not None:
        candidates = candidates[:max_patterns]
    summary.candidates = len(candidates)
    if dry_run or client is None:
        return summary

    for c in candidates:
        labels = label_pattern_with_llm(client, c, model=model)
        if labels is None:
            summary.llm_missing += 1
            continue
        if persist_pattern(conn, c, labels):
            summary.persisted += 1
        else:
            summary.skipped_duplicate += 1
    return summary
