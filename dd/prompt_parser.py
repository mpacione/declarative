"""LLM prompt parsing — natural language → component list (Phase 4c).

Takes a natural language description of a UI screen and produces the
component list that compose_screen() consumes. Uses Claude Haiku for
fast, cheap parsing.
"""

import json
import re
import sqlite3
from typing import Any

from dd.compose import generate_from_prompt as _generate_from_prompt
from dd.screen_patterns import extract_screen_archetypes, get_archetype_prompt_context

_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a UI composition assistant. Given a natural language description of a screen, produce a JSON array of components.

Available component types (use ONLY these):

Actions: button, icon_button, fab, button_group, menu, context_menu
Selection & Input: checkbox, radio, toggle, toggle_group, select, combobox, date_picker, slider, segmented_control, text_input, textarea, search_input, stepper
Content & Display: text, heading, link, image, icon, avatar, badge, list, list_item, table, skeleton
Navigation: navigation_row, tabs, breadcrumbs, pagination, bottom_nav, drawer, header
Feedback & Status: alert, toast, popover, tooltip, empty_state, file_upload
Containment & Overlay: card, dialog, sheet, accordion

Output format — a JSON array:
[
  {"type": "header", "props": {"text": "Settings"}},
  {"type": "card", "children": [
    {"type": "heading", "props": {"text": "Notifications"}},
    {"type": "toggle", "props": {"label": "Push alerts", "checked": true}},
    {"type": "toggle", "props": {"label": "Email digest", "checked": false}}
  ]},
  {"type": "card", "children": [
    {"type": "heading", "props": {"text": "Privacy"}},
    {"type": "navigation_row", "props": {"text": "Blocked users"}},
    {"type": "navigation_row", "props": {"text": "Data export"}}
  ]},
  {"type": "button", "props": {"text": "Save Changes"}}
]

Rules:
- Use ONLY the component types listed above
- Group related items inside "card" containers
- Include a "header" at the top of most screens
- Text content goes in props.text, labels in props.label
- Keep it practical: 5-15 top-level components
- Output ONLY the JSON array, no explanation"""


def extract_json(text: str) -> list[dict[str, Any]]:
    """Extract a JSON array from LLM response text.

    Handles plain JSON, markdown code blocks, and text before/after JSON.
    Returns empty list if no valid JSON array found.
    """
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1)

    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        text = bracket_match.group(0)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    return []


def parse_prompt(
    prompt: str,
    client: Any,
    catalog_types: list[str] | None = None,
    system_prompt: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a natural language prompt into a component list using Claude.

    Returns a list of component dicts suitable for compose_screen().
    """
    response = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        system=system_prompt or SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = response.content[0].text
    return extract_json(response_text)


def prompt_to_figma(
    prompt: str,
    conn: sqlite3.Connection,
    client: Any,
) -> dict[str, Any]:
    """End-to-end: natural language prompt → Figma JS script.

    Enriches the LLM prompt with project-specific screen patterns
    extracted from the DB, then orchestrates:
    parse_prompt → generate_from_prompt (compose + render).
    """
    file_row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
    file_id = file_row[0] if file_row else None

    archetype_context = ""
    if file_id:
        archetypes = extract_screen_archetypes(conn, file_id)
        archetype_context = get_archetype_prompt_context(archetypes)

    system = SYSTEM_PROMPT
    if archetype_context:
        system = system + "\n\n" + archetype_context

    components = parse_prompt(prompt, client, system_prompt=system)
    result = _generate_from_prompt(conn, components)
    result["components"] = components
    return result
