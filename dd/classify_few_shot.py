"""Few-shot retrieval from user review history (classifier v2.1 phase B).

For each classify candidate, pull 3-5 structurally-similar nodes
from the `classification_reviews` table (user ground-truth labels)
and inject them into the LLM/vision prompt as in-context examples.

Similarity score:
- +1.0 if the reviewed node's parent canonical_type == candidate's
  parent_classified_as.
- +0.5 if the reviewed node's name == candidate's name.
- +0.3 if the reviewed node's children count is within 50% of
  candidate's total_children.

Top-k scorers (sorted descending) are returned. Ties broken by
review recency. When no review exists for a candidate's parent
type, falls back to any reviewed node with matching name.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional


def _load_candidate_reviews(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Fetch every reviewed row with the context we need to rank
    against a candidate: name, parent canonical_type, child count,
    ground-truth label from the review.

    Only rows where the review resolved to a canonical type (either
    `accept_source` with a source verdict or `override` with an
    explicit type) are candidates for few-shot.
    """
    cursor = conn.execute(
        """
        SELECT
            r.id AS review_id,
            r.decision_type,
            r.source_accepted,
            r.decision_canonical_type,
            r.decided_at,
            sci.id AS sci_id,
            sci.canonical_type AS sci_canonical_type,
            sci.llm_type, sci.vision_ps_type, sci.vision_cs_type,
            n.name AS node_name,
            n.node_type,
            n.width, n.height,
            (SELECT COUNT(*) FROM nodes c WHERE c.parent_id = n.id)
              AS child_count,
            parent_sci.canonical_type AS parent_canonical_type
        FROM classification_reviews r
        JOIN screen_component_instances sci ON sci.id = r.sci_id
        JOIN nodes n ON n.id = sci.node_id
        LEFT JOIN nodes parent_n ON parent_n.id = n.parent_id
        LEFT JOIN screen_component_instances parent_sci
          ON parent_sci.node_id = parent_n.id
          AND parent_sci.screen_id = n.screen_id
        WHERE r.decision_type IN ('accept_source', 'override')
        ORDER BY r.decided_at DESC
        """
    )
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, r)) for r in cursor.fetchall()]

    # Resolve the ground-truth type per row: `override` uses
    # decision_canonical_type; `accept_source` uses the source's
    # verdict column (llm_type / vision_ps_type / vision_cs_type).
    for r in rows:
        if r["decision_type"] == "override":
            r["ground_truth_type"] = r["decision_canonical_type"]
        elif r["decision_type"] == "accept_source":
            src = r["source_accepted"]
            if src == "llm":
                r["ground_truth_type"] = r["llm_type"]
            elif src == "vision_ps":
                r["ground_truth_type"] = r["vision_ps_type"]
            elif src == "vision_cs":
                r["ground_truth_type"] = r["vision_cs_type"]
            else:
                r["ground_truth_type"] = r["sci_canonical_type"]
        else:
            r["ground_truth_type"] = None
        # Alias fields for consumer convenience.
        r["name"] = r.get("node_name")
        r["review_decision"] = r.get("decision_type")
    return rows


def _score_similarity(
    candidate: dict[str, Any],
    review: dict[str, Any],
) -> float:
    """Rank how similar a reviewed node is to the candidate."""
    score = 0.0
    cand_parent = candidate.get("parent_classified_as")
    if cand_parent and review.get("parent_canonical_type") == cand_parent:
        score += 1.0
    if candidate.get("name") and review.get("node_name") == candidate.get("name"):
        score += 0.5
    cand_children = (
        candidate.get("total_children")
        or sum((candidate.get("child_type_dist") or {}).values())
    )
    rev_children = review.get("child_count") or 0
    if cand_children and rev_children:
        ratio = min(cand_children, rev_children) / max(
            cand_children, rev_children,
        )
        if ratio >= 0.5:
            score += 0.3
    return score


def retrieve_few_shot(
    conn: sqlite3.Connection,
    candidate: dict[str, Any],
    *,
    k: int = 3,
    min_score: float = 0.5,
) -> list[dict[str, Any]]:
    """Top-k most-similar user-reviewed nodes for this candidate.

    Returns empty list when nothing scores ≥ `min_score` — it's
    better to skip the few-shot block than inject misleading
    examples.
    """
    pool = _load_candidate_reviews(conn)
    if not pool:
        return []

    scored: list[tuple[float, dict[str, Any]]] = [
        (_score_similarity(candidate, r), r) for r in pool
    ]
    scored = [
        (s, r) for s, r in scored
        if s >= min_score and r.get("ground_truth_type")
    ]
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:k]]


def format_few_shot_block(
    examples: list[dict[str, Any]],
) -> str:
    """Render examples as a prompt section the LLM can read as
    in-context ground truth.
    """
    if not examples:
        return ""
    lines = ["## Examples from human review on this project", ""]
    for i, e in enumerate(examples, 1):
        parts = [
            f"Example {i}:",
            f'name="{e.get("node_name") or e.get("name") or "?"}"',
            f"parent={e.get('parent_canonical_type') or '(none)'}",
        ]
        if e.get("child_count"):
            parts.append(f"children={e['child_count']}")
        if e.get("sample_text"):
            parts.append(f'sample_text="{e["sample_text"]}"')
        # Indent with the ground-truth.
        header = " ".join(parts)
        gt = e.get("ground_truth_type") or "?"
        lines.append(
            f"- {header} → reviewer classified as "
            f"**`{gt}`** (reviewed)."
        )
    return "\n".join(lines) + "\n"
