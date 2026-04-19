"""Vision cross-validation for classified components (T5 Phase 1b, Step 4).

Takes screenshots of classified component subtrees and re-classifies
via vision to detect disagreements between structural and visual
classification. M7.0.a rewrote this stage to mirror the tool-use
shape of ``dd.classify_llm`` — full catalog with behavioral
descriptions, structured output via Claude tool-use, `unsure` as a
first-class answer, calibrated confidence.

Trigger: runs on classifications with ``confidence < threshold``
(default 0.95). Agreement with the structural/LLM classification
corroborates; disagreement flags the row for review.
"""

from __future__ import annotations

import base64
import sqlite3
from collections.abc import Callable
from typing import Any

from dd.catalog import get_catalog
from dd.classify_llm import _format_catalog_for_prompt


_VISION_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_CONFIDENCE_THRESHOLD = 0.95


# Structured output schema for the vision classifier. Simpler than
# the LLM batch schema because vision runs one node at a time
# (each call carries a single screenshot).
VISION_TOOL_SCHEMA = {
    "name": "classify_node_from_screenshot",
    "description": (
        "Return the canonical UI component type that best matches "
        "the rendered screenshot. Use `container` when the view is "
        "a structural layout frame with no specific component "
        "identity. Use `unsure` when the screenshot alone cannot "
        "determine identity — do NOT invent a classification to "
        "avoid this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "canonical_type": {"type": "string"},
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "reason": {
                "type": "string",
                "description": (
                    "One short sentence citing the visual signals "
                    "that led to this classification (shape, "
                    "content, layout, affordances). Evidence-based; "
                    "no speculation."
                ),
            },
        },
        "required": ["canonical_type", "confidence", "reason"],
    },
}


def build_vision_prompt(
    catalog: list[dict[str, Any]],
    figma_node_id: str,
    structural_type: str,
    node_name: str | None = None,
    parent_classified_as: str | None = None,
) -> str:
    """Render the vision classification prompt.

    The vision model sees the screenshot + this text. The text
    provides the catalog vocabulary (required so the model can't
    invent a non-canonical type) and a small amount of structural
    context (what was the structural/LLM classification — "what do
    you see" vs. a claim it's meant to validate).
    """
    catalog_block = _format_catalog_for_prompt(catalog)

    context_lines = [f"Node ID: {figma_node_id}"]
    if node_name:
        context_lines.append(f'Layer name: "{node_name}"')
    if parent_classified_as:
        context_lines.append(f"Parent classified as: {parent_classified_as}")
    context_lines.append(
        f"Structural/LLM classification (what you're validating): "
        f"{structural_type}"
    )
    context_block = "\n".join(context_lines)

    return f"""You are validating a UI component classification by examining its rendered screenshot against a fixed catalog of canonical component types. This classification feeds a design-system compiler — accuracy matters, and "unsure" is a valid answer.

## Node context

{context_block}

## Canonical types (pick exactly one)

Use the behavioral description to disambiguate. The UI component that matches the *function* shown in the screenshot wins, not the one that merely looks similar.
{catalog_block}

## Rules

1. **Judge the screenshot, not the structural guess.** If the visual evidence contradicts the structural classification, emit the visual answer — that's the whole point of this cross-check.
2. **Confidence is calibrated.** 0.95+ = unambiguous. 0.8 = strong signal but one ambiguity. 0.6 = weak. Below 0.6 → prefer `unsure`.
3. **`container` and `unsure` are valid** — prefer a specific type when evidence supports it, but never invent.
4. **Reasons are evidence-based.** Cite what you see (shape, content, affordances). "Looks like a button" is bad; "Rounded rectangle with centered 'Sign in' label and solid fill" is good.

Return your classification via the `classify_node_from_screenshot` tool."""


def _extract_classification_from_response(response: Any) -> dict[str, Any] | None:
    """Extract the classification dict from a tool-use response.
    Returns None when the expected tool_use block is missing —
    caller logs and skips the instance rather than inventing data.
    """
    if response is None or not getattr(response, "content", None):
        return None
    for block in response.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != VISION_TOOL_SCHEMA["name"]:
            continue
        inp = getattr(block, "input", None)
        if isinstance(inp, dict) and "canonical_type" in inp:
            return inp
        return None
    return None


def _classify_with_vision(
    client: Any,
    screenshot: bytes,
    figma_node_id: str,
    structural_type: str,
    catalog: list[dict[str, Any]],
    node_name: str | None = None,
    parent_classified_as: str | None = None,
) -> dict[str, Any] | None:
    """Call the vision model with the screenshot + structured prompt.

    Returns the extracted classification dict (``{canonical_type,
    confidence, reason}``) or None on failure.
    """
    b64_image = base64.b64encode(screenshot).decode("utf-8")
    prompt = build_vision_prompt(
        catalog=catalog,
        figma_node_id=figma_node_id,
        structural_type=structural_type,
        node_name=node_name,
        parent_classified_as=parent_classified_as,
    )

    response = client.messages.create(
        model=_VISION_MODEL,
        max_tokens=1024,
        tools=[VISION_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": VISION_TOOL_SCHEMA["name"]},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64_image,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return _extract_classification_from_response(response)


def cross_validate_vision(
    conn: sqlite3.Connection,
    screen_id: int,
    file_key: str,
    client: Any,
    fetch_screenshot: Callable,
    confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    """Cross-validate classified instances using vision.

    For each classified instance with ``confidence < threshold``,
    fetches a screenshot and asks the vision model (via tool-use)
    to classify it. Updates ``vision_type``, ``vision_agrees``, and
    ``flagged_for_review`` on the instance row.

    ``fetch_screenshot`` can be either:
    - ``Callable(file_key, node_id) → bytes | None`` (single fetch)
    - ``Callable(file_key, [node_ids]) → {node_id: bytes}`` (batch)
    The function auto-detects based on the second arg shape.
    """
    instances = _get_instances_to_validate(conn, screen_id, confidence_threshold)
    if not instances:
        return {"validated": 0, "agreed": 0, "disagreed": 0}

    node_ids = [inst["figma_node_id"] for inst in instances]
    screenshots = _fetch_screenshots_batch(fetch_screenshot, file_key, node_ids)

    catalog = get_catalog(conn)
    validated = 0
    agreed = 0
    disagreed = 0

    for instance in instances:
        screenshot = screenshots.get(instance["figma_node_id"])
        if screenshot is None:
            continue

        result = _classify_with_vision(
            client=client,
            screenshot=screenshot,
            figma_node_id=instance["figma_node_id"],
            structural_type=instance["canonical_type"],
            catalog=catalog,
            node_name=instance.get("node_name"),
            parent_classified_as=instance.get("parent_classified_as"),
        )
        if result is None:
            continue

        vision_type = result.get("canonical_type")
        vision_reason = result.get("reason")
        if not isinstance(vision_type, str):
            continue

        structural_type = instance["canonical_type"]
        agrees = 1 if vision_type == structural_type else 0
        flagged = 0 if agrees else 1

        conn.execute(
            "UPDATE screen_component_instances "
            "SET vision_type = ?, vision_agrees = ?, flagged_for_review = ?, "
            "vision_reason = ? "
            "WHERE id = ?",
            (vision_type, agrees, flagged,
             vision_reason if isinstance(vision_reason, str) else None,
             instance["sci_id"]),
        )

        validated += 1
        if agrees:
            agreed += 1
        else:
            disagreed += 1

    conn.commit()
    return {"validated": validated, "agreed": agreed, "disagreed": disagreed}


def _fetch_screenshots_batch(
    fetch_fn: Callable,
    file_key: str,
    node_ids: list[str],
) -> dict[str, bytes]:
    """Fetch screenshots, auto-detecting single vs batch fetch function.

    Tries to call fetch_fn with a list of node_ids first. If it
    returns a dict, use that. Otherwise falls back to calling
    per-node.
    """
    if not node_ids:
        return {}

    try:
        result = fetch_fn(file_key, node_ids)
        if isinstance(result, dict):
            return result
    except TypeError:
        pass

    screenshots: dict[str, bytes] = {}
    for nid in node_ids:
        data = fetch_fn(file_key, nid)
        if data is not None:
            screenshots[nid] = data
    return screenshots


def _get_instances_to_validate(
    conn: sqlite3.Connection,
    screen_id: int,
    confidence_threshold: float,
) -> list[dict[str, Any]]:
    """Fetch classified instances eligible for vision validation,
    enriched with the context the vision prompt needs (node name,
    parent's canonical_type when available).
    """
    cursor = conn.execute(
        """
        SELECT sci.id AS sci_id, sci.canonical_type, sci.confidence,
               n.figma_node_id, n.name AS node_name,
               parent_sci.canonical_type AS parent_classified_as
        FROM screen_component_instances sci
        JOIN nodes n ON sci.node_id = n.id
        LEFT JOIN screen_component_instances parent_sci
          ON parent_sci.id = sci.parent_instance_id
        WHERE sci.screen_id = ?
          AND sci.confidence < ?
          AND sci.vision_type IS NULL
        """,
        (screen_id, confidence_threshold),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
