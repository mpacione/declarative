"""M7.0.d — Alexander's forces-labeling pass over classified
instances.

Classification answers WHAT a node is (a button, a card); forces
labeling answers WHAT IT IS DOING THERE (main-cta in login-form,
avatar in list-item). Alexander: *"The same CARD pattern applied to
a product listing and to a user profile should produce different
results because the forces are different."*

Without forces, M7.6 S4 composition devolves into copy-and-paste
from the corpus: "I need a button" → a random button from any
context. Forces labels let retrieval pick a donor whose local
role matches the target role, keeping the composition honest.

Scope for the initial shipment:

- Label only load-bearing canonical_types (buttons / cards / nav /
  headers / heading / image / list_item / tabs / field_input /
  drawer / slider / select / toolbar). Icons / text / container /
  unsure are too generic — their forces label would be noise.
- Trust filter: same set the swap demo uses (formal / heuristic /
  unanimous / two_source_unanimous). Uncertain classifications
  would give the LLM bad context.
- Incremental: only label rows where ``compositional_role IS NULL``.
  Re-runs add to the labeled set, never clobber.
- Batched: N instances per API call keeps the per-row cost within
  the $0.001–$0.002 range.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Optional


_TARGETED_TYPES: frozenset[str] = frozenset({
    "button",
    "icon_button",
    "card",
    "header",
    "heading",
    "image",
    "list_item",
    "tabs",
    "field_input",
    "drawer",
    "slider",
    "select",
    "toolbar",
    "nav",
    "chip",
    "menu_item",
})


_TRUSTED_CONSENSUS_METHODS: tuple[str, ...] = (
    "formal", "heuristic", "unanimous", "two_source_unanimous",
)


@dataclass
class ForcesContext:
    """Per-instance context snapshot — what the LLM sees when asked
    to label one instance's forces."""

    sci_id: int
    screen_id: int
    canonical_type: str
    node_id: int
    node_name: str
    parent_id: Optional[int]
    parent_name: Optional[str]
    parent_canonical_type: Optional[str]
    siblings: list[dict[str, Any]] = field(default_factory=list)
    children: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BatchForcesResult:
    """Result of one :func:`label_instances_batch` call."""

    labels: dict[int, str] = field(default_factory=dict)
    missing_count: int = 0


@dataclass
class ForcesLabelingSummary:
    candidates: int = 0
    labeled: int = 0
    batches: int = 0
    errors: int = 0


def collect_instance_context(
    conn: sqlite3.Connection, sci_id: int,
) -> Optional[ForcesContext]:
    """Fetch the per-instance context for a single SCI row.

    Returns ``None`` when the SCI id doesn't exist. Does not care
    whether the row is labeled yet — callers filter via
    :func:`fetch_labeling_candidates`."""
    row = conn.execute(
        """
        SELECT sci.id, sci.screen_id, sci.node_id, sci.canonical_type,
               n.name AS node_name, n.parent_id
          FROM screen_component_instances sci
          JOIN nodes n ON n.id = sci.node_id
         WHERE sci.id = ?
        """,
        (sci_id,),
    ).fetchone()
    if row is None:
        return None

    parent_name: Optional[str] = None
    parent_canonical_type: Optional[str] = None
    siblings: list[dict[str, Any]] = []
    if row["parent_id"] is not None:
        p = conn.execute(
            """
            SELECT n.name, sci.canonical_type
              FROM nodes n
         LEFT JOIN screen_component_instances sci
                ON sci.node_id = n.id
             WHERE n.id = ?
            """,
            (row["parent_id"],),
        ).fetchone()
        if p is not None:
            parent_name = p["name"]
            parent_canonical_type = p["canonical_type"]
        sib_rows = conn.execute(
            """
            SELECT n.id, n.name, sci.canonical_type
              FROM nodes n
         LEFT JOIN screen_component_instances sci
                ON sci.node_id = n.id
             WHERE n.parent_id = ? AND n.id != ?
             ORDER BY n.id
             LIMIT 20
            """,
            (row["parent_id"], row["node_id"]),
        ).fetchall()
        siblings = [
            {
                "id": r["id"],
                "name": r["name"],
                "canonical_type": r["canonical_type"],
            }
            for r in sib_rows
        ]

    child_rows = conn.execute(
        """
        SELECT n.id, n.name, sci.canonical_type
          FROM nodes n
     LEFT JOIN screen_component_instances sci
            ON sci.node_id = n.id
         WHERE n.parent_id = ?
         ORDER BY n.id
         LIMIT 20
        """,
        (row["node_id"],),
    ).fetchall()
    children = [
        {
            "id": r["id"],
            "name": r["name"],
            "canonical_type": r["canonical_type"],
        }
        for r in child_rows
    ]

    return ForcesContext(
        sci_id=row["id"],
        screen_id=row["screen_id"],
        canonical_type=row["canonical_type"],
        node_id=row["node_id"],
        node_name=row["node_name"],
        parent_id=row["parent_id"],
        parent_name=parent_name,
        parent_canonical_type=parent_canonical_type,
        siblings=siblings,
        children=children,
    )


def fetch_labeling_candidates(
    conn: sqlite3.Connection, *,
    limit: int = 100,
    canonical_types: Optional[list[str]] = None,
    screen_id: Optional[int] = None,
) -> list[sqlite3.Row]:
    """Return SCI rows eligible for forces labeling.

    Filters:
    - ``canonical_type`` in the targeted set (or caller-supplied
      subset).
    - ``consensus_method`` in the trusted set (or NULL, for
      pre-classification-cascade rows that still have a
      formal/heuristic source).
    - ``compositional_role`` IS NULL (incremental; never clobber
      existing labels).
    """
    types = tuple(canonical_types or _TARGETED_TYPES)
    if not types:
        return []
    type_placeholders = ",".join("?" * len(types))
    trust_placeholders = ",".join("?" * len(_TRUSTED_CONSENSUS_METHODS))
    args: list[Any] = [*types, *_TRUSTED_CONSENSUS_METHODS]
    where_screen = ""
    if screen_id is not None:
        where_screen = "AND sci.screen_id = ?"
        args.append(screen_id)
    args.append(limit)
    rows = conn.execute(
        f"""
        SELECT sci.id, sci.screen_id, sci.node_id,
               sci.canonical_type, sci.consensus_method
          FROM screen_component_instances sci
         WHERE sci.canonical_type IN ({type_placeholders})
           AND (
               sci.consensus_method IS NULL
               OR sci.consensus_method IN ({trust_placeholders})
           )
           AND sci.compositional_role IS NULL
           {where_screen}
         ORDER BY sci.id
         LIMIT ?
        """,
        args,
    ).fetchall()
    return rows


def _format_context_for_prompt(ctx: ForcesContext) -> str:
    """Render one context as a compact prompt fragment. The
    ``sci_id=N`` marker lets downstream tests inspect which
    contexts made it into which batches."""
    parent = (
        f"{ctx.parent_name!r} "
        f"(canonical_type={ctx.parent_canonical_type!r})"
        if ctx.parent_name else "<top-level>"
    )
    sibs = ", ".join(
        f"{s['name']!r}:{s['canonical_type'] or '?'}"
        for s in ctx.siblings[:6]
    ) or "(none)"
    kids = ", ".join(
        f"{c['name']!r}:{c['canonical_type'] or '?'}"
        for c in ctx.children[:6]
    ) or "(none)"
    return (
        f"- sci_id={ctx.sci_id} canonical_type={ctx.canonical_type!r} "
        f"node_name={ctx.node_name!r}\n"
        f"    parent: {parent}\n"
        f"    siblings: {sibs}\n"
        f"    children: {kids}"
    )


def _build_forces_tool_schema(sci_ids: list[int]) -> dict[str, Any]:
    return {
        "name": "emit_forces_labels",
        "description": (
            "Emit compositional-role labels for a batch of UI "
            "instances. Each label is a flat pair of (role, "
            "context). Together they form `<role> in <context>`, "
            "Alexander's forces label."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "labels": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "sci_id": {
                                "type": "integer",
                                "enum": sci_ids,
                                "description": (
                                    "The instance's sci_id, echoed "
                                    "back from the prompt so we can "
                                    "route the label."
                                ),
                            },
                            "role": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 40,
                                "description": (
                                    "Short kebab-case role. Examples: "
                                    "main-cta / secondary-action / "
                                    "nav-target / item-thumbnail / "
                                    "avatar / status-badge / "
                                    "content-header / search-input."
                                ),
                            },
                            "context": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 40,
                                "description": (
                                    "Short kebab-case context. "
                                    "Examples: login-form / "
                                    "settings-row / card-header / "
                                    "bottom-nav / modal-title / "
                                    "list-item / page-header."
                                ),
                            },
                        },
                        "required": ["sci_id", "role", "context"],
                    },
                },
            },
            "required": ["labels"],
        },
    }


def _sanitise_fragment(s: str) -> str:
    """Normalise an LLM-returned role/context fragment to
    kebab-case lowercase alphanumerics.

    Removes leading/trailing quotes and whitespace, runs
    inner whitespace → hyphens, lowercases, collapses repeated
    hyphens."""
    import re
    cleaned = s.strip().strip('"\'').strip()
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = re.sub(r"[^a-zA-Z0-9\-_]", "", cleaned)
    return cleaned.lower().strip("-")


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


def label_instances_batch(
    client, contexts: list[ForcesContext], *,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 1024,
) -> BatchForcesResult:
    """Send one tool-use call covering every context in ``contexts``.

    The tool schema pins ``sci_id`` to the exact set of ids in this
    batch (enum-constrained) so the LLM can't emit a foreign id.
    Roles / contexts come back as free strings; we sanitise both
    before persisting."""
    if not contexts:
        return BatchForcesResult()

    sci_ids = [c.sci_id for c in contexts]
    tool_schema = _build_forces_tool_schema(sci_ids)
    context_lines = "\n".join(_format_context_for_prompt(c) for c in contexts)
    system = (
        "You label UI instances with their compositional role + "
        "context, per Alexander's pattern-forces framing. The role "
        "describes what the instance IS DOING; the context "
        "describes WHERE it sits. Keep both short, kebab-case, and "
        "explanatory — think how a designer would describe 'the "
        "main-cta in login-form' versus 'a secondary-action in "
        "the bottom-nav'. Avoid generic or redundant labels "
        "(e.g. never emit role=button; the classifier already "
        "provides canonical_type)."
    )
    user = (
        "### Instances to label\n" + context_lines +
        "\n\nEmit one entry per sci_id via `emit_forces_labels`."
    )
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": tool_schema["name"]},
        messages=[{"role": "user", "content": user}],
    )
    payload = _extract_tool_call(response, tool_schema["name"])
    if payload is None or not isinstance(payload.get("labels"), list):
        return BatchForcesResult(missing_count=len(contexts))

    requested = {c.sci_id for c in contexts}
    labels: dict[int, str] = {}
    for entry in payload["labels"]:
        sci_id = entry.get("sci_id")
        if sci_id not in requested:
            continue
        role = _sanitise_fragment(str(entry.get("role") or ""))
        context = _sanitise_fragment(str(entry.get("context") or ""))
        if not role or not context:
            continue
        labels[sci_id] = f"{role} in {context}"
    missing = len(contexts) - len(labels)
    return BatchForcesResult(labels=labels, missing_count=max(missing, 0))


def run_forces_labeling(
    conn: sqlite3.Connection, *,
    limit: int = 100,
    dry_run: bool = False,
    client=None,
    canonical_types: Optional[list[str]] = None,
    screen_id: Optional[int] = None,
    batch_size: int = 10,
    model: str = "claude-haiku-4-5-20251001",
) -> ForcesLabelingSummary:
    """Orchestrator: fetch candidates, batch, label, persist.

    ``dry_run`` → gather candidates + build contexts, but skip the
    API call and the DB write. Useful for cost estimation on a new
    screen set.
    """
    summary = ForcesLabelingSummary()
    rows = fetch_labeling_candidates(
        conn, limit=limit,
        canonical_types=canonical_types, screen_id=screen_id,
    )
    summary.candidates = len(rows)
    if not rows:
        return summary
    if dry_run or client is None:
        return summary

    for start in range(0, len(rows), batch_size):
        chunk = rows[start:start + batch_size]
        contexts: list[ForcesContext] = []
        for r in chunk:
            ctx = collect_instance_context(conn, r["id"])
            if ctx is not None:
                contexts.append(ctx)
        if not contexts:
            continue
        try:
            result = label_instances_batch(
                client, contexts, model=model,
            )
        except Exception:
            summary.errors += 1
            continue
        summary.batches += 1
        if not result.labels:
            continue
        conn.executemany(
            "UPDATE screen_component_instances "
            "SET compositional_role = ? WHERE id = ?",
            [(v, k) for k, v in result.labels.items()],
        )
        conn.commit()
        summary.labeled += len(result.labels)
    return summary
