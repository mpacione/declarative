"""Vision cross-validation for classified components (T5 Phase 1b, Step 4).

Takes screenshots of classified component subtrees and re-classifies via
vision to detect disagreements between structural and visual classification.
"""

import base64
import json
import sqlite3
from typing import Any, Callable, Dict, List, Optional

from dd.catalog import get_catalog


_VISION_MODEL = "claude-haiku-4-5-20251001"


def cross_validate_vision(
    conn: sqlite3.Connection,
    screen_id: int,
    file_key: str,
    client: Any,
    fetch_screenshot: Callable[[str, str], Optional[bytes]],
    confidence_threshold: float = 0.95,
) -> Dict[str, Any]:
    """Cross-validate classified instances using vision.

    For each classified instance with confidence < threshold, fetches a
    screenshot and asks the vision model to classify it. Updates vision_type,
    vision_agrees, and flagged_for_review columns.

    Args:
        conn: Database connection
        screen_id: Screen to validate
        file_key: Figma file key for screenshot API
        client: Anthropic client (or mock)
        fetch_screenshot: Callable(file_key, figma_node_id) → PNG bytes or None
        confidence_threshold: Only validate instances below this confidence
    """
    instances = _get_instances_to_validate(conn, screen_id, confidence_threshold)
    if not instances:
        return {"validated": 0, "agreed": 0, "disagreed": 0}

    catalog_types = [e["canonical_name"] for e in get_catalog(conn)]
    validated = 0
    agreed = 0
    disagreed = 0

    for instance in instances:
        screenshot = fetch_screenshot(file_key, instance["figma_node_id"])
        if screenshot is None:
            continue

        vision_type = _classify_with_vision(
            client, screenshot, instance["figma_node_id"], catalog_types,
        )
        if vision_type is None:
            continue

        structural_type = instance["canonical_type"]
        agrees = 1 if vision_type == structural_type else 0
        flagged = 0 if agrees else 1

        conn.execute(
            "UPDATE screen_component_instances "
            "SET vision_type = ?, vision_agrees = ?, flagged_for_review = ? "
            "WHERE id = ?",
            (vision_type, agrees, flagged, instance["sci_id"]),
        )

        validated += 1
        if agrees:
            agreed += 1
        else:
            disagreed += 1

    conn.commit()
    return {"validated": validated, "agreed": agreed, "disagreed": disagreed}


def _get_instances_to_validate(
    conn: sqlite3.Connection,
    screen_id: int,
    confidence_threshold: float,
) -> List[Dict[str, Any]]:
    cursor = conn.execute(
        "SELECT sci.id as sci_id, sci.canonical_type, sci.confidence, n.figma_node_id "
        "FROM screen_component_instances sci "
        "JOIN nodes n ON sci.node_id = n.id "
        "WHERE sci.screen_id = ? AND sci.confidence < ? AND sci.vision_type IS NULL",
        (screen_id, confidence_threshold),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _classify_with_vision(
    client: Any,
    screenshot: bytes,
    figma_node_id: str,
    catalog_types: List[str],
) -> Optional[str]:
    """Send a screenshot to the vision model for classification."""
    type_list = ", ".join(catalog_types) + ", container"
    b64_image = base64.b64encode(screenshot).decode("utf-8")

    response = client.messages.create(
        model=_VISION_MODEL,
        max_tokens=256,
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
                {
                    "type": "text",
                    "text": (
                        f"What UI component type is this? Node ID: {figma_node_id}\n"
                        f"Choose one: {type_list}\n"
                        f"Respond with JSON: {{\"type\": \"...\", \"confidence\": 0.0-1.0}}"
                    ),
                },
            ],
        }],
    )

    try:
        text = response.content[0].text.strip()
        parsed = json.loads(text)
        return parsed.get("type")
    except (json.JSONDecodeError, KeyError, IndexError):
        return None
