"""LLM prompt parsing — natural language → component list (Phase 4c).

Takes a natural language description of a UI screen and produces the
component list that compose_screen() consumes. Uses Claude Haiku for
fast, cheap parsing.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from dd.composition.archetype_classifier import classify_archetype
from dd.composition.archetype_injection import inject_archetype
from dd.compose import generate_from_prompt as _generate_from_prompt
from dd.screen_patterns import extract_screen_archetypes, get_archetype_prompt_context

_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_MIN_INSTANCES = 50

# ADR-008 v0.1.5: lower the production composition temperature to 0.3.
# The 00c-00f runs used the Haiku default (~1.0) and exhibited high
# cross-run variance (12-round-trip-test emitted 0 / 6 / 6 / 0
# components on identical prompts). Stream-β's matrix design predicts
# S2 @ T=0.3 as the dominant cell; confirmation by the 240-call run
# upstream of this default-flip. The old behaviour is available by
# passing ``temperature=None`` explicitly to ``parse_prompt``.
_COMPOSE_TEMPERATURE = 0.3


_CKR_MIN_INSTANCES = 1
_CKR_ENTRIES_PER_PREFIX = 8

# Prefixes we prefer when surfacing the CKR to the LLM. Project components
# with these prefixes are semantically useful for composition; the ones
# NOT in this list (single-char keyboard keys, `_Key`, `.?123`, `!,`, etc.)
# add noise. Unknown prefixes still appear but are pushed below the
# semantic ones.
_CKR_SEMANTIC_PREFIXES: tuple[str, ...] = (
    "button", "icon", "nav", "logo", "avatar", "badge", "card", "list",
    "header", "footer", "toolbar", "menu", "tab", "tabs", "dialog",
    "sheet", "drawer", "toast", "alert", "input", "search", "toggle",
    "checkbox", "radio", "slider", "chip", "divider", "progress",
    "fab", "action", "link",
)


def build_project_vocabulary(
    conn: sqlite3.Connection,
    min_instances: int = _DEFAULT_MIN_INSTANCES,
) -> str:
    """Build a project vocabulary block for LLM system-prompt injection.

    Two sections:

    1. **Component variants** (existing) — from ``component_templates``
       with ``instance_count >= min_instances``. Groups variants per
       catalog_type. Tells the LLM which named variants the project
       has authored.

    2. **Component keys** (ADR-008 Tier 2) — from
       ``component_key_registry``. Lets the LLM emit
       ``"component_key": "<name>"`` for Mode-1 instance reuse. Keys
       are grouped by prefix (the token before the first ``/``) so
       the LLM sees "icon: chevron-right, menu, close, ..." rather
       than 129 loose entries. Up to eight entries per prefix keeps
       the prompt tight even on large corpora.
    """
    from collections import defaultdict

    lines: list[str] = []

    # ── Section 1: component templates (variants) ───────────────────
    rows = conn.execute(
        "SELECT catalog_type, variant, component_key, instance_count "
        "FROM component_templates "
        "WHERE instance_count >= ? "
        "ORDER BY catalog_type, instance_count DESC",
        (min_instances,),
    ).fetchall()

    if rows:
        by_type: dict[str, list] = defaultdict(list)
        for r in rows:
            by_type[r[0]].append({
                "variant": r[1],
                "component_key": r[2],
                "instance_count": r[3],
            })

        lines.append(
            "This project has these specific component variants "
            "(use exact variant names when composing):"
        )
        for cat_type in sorted(by_type.keys()):
            variants = by_type[cat_type]
            variant_strs: list[str] = []
            for v in variants:
                name = v["variant"] or "default"
                count = v["instance_count"]
                key_str = f", key={v['component_key']}" if v["component_key"] else ""
                variant_strs.append(f"{name} ({count} instances{key_str})")
            lines.append(f"  {cat_type}: {', '.join(variant_strs)}")

        lines.append("")
        lines.append(
            "When outputting components, include a \"variant\" field with the "
            "exact variant name from above when a specific variant applies."
        )

    # ── Section 2: CKR component_keys (ADR-008 Tier 2) ──────────────
    try:
        ckr_rows = conn.execute(
            "SELECT component_key, name, instance_count "
            "FROM component_key_registry "
            "WHERE instance_count >= ? "
            "ORDER BY instance_count DESC, name",
            (_CKR_MIN_INSTANCES,),
        ).fetchall()
    except sqlite3.OperationalError:
        ckr_rows = []

    if ckr_rows:
        by_prefix: dict[str, list] = defaultdict(list)
        for component_key, name, instance_count in ckr_rows:
            if not name:
                continue
            prefix = name.split("/", 1)[0].lower() if "/" in name else name.lower()
            by_prefix[prefix].append((name, instance_count))

        if by_prefix:
            if lines:
                lines.append("")
            lines.append(
                "Project component keys (emit `\"component_key\": \"<name>\"` "
                "to reuse the exact instance from this project's corpus). "
                "The component_key name is authoritative; do NOT alter it."
            )
            # Semantic prefixes first (button, icon, nav, logo, …), then
            # everything else alphabetically. Within each bucket, order by
            # prefix name. This shifts the LLM-useful entries to the top
            # of the block.
            semantic = [p for p in by_prefix.keys() if p in _CKR_SEMANTIC_PREFIXES]
            non_semantic = [p for p in by_prefix.keys() if p not in _CKR_SEMANTIC_PREFIXES]
            semantic.sort()
            non_semantic.sort()
            for prefix in semantic + non_semantic:
                entries = by_prefix[prefix][:_CKR_ENTRIES_PER_PREFIX]
                formatted = ", ".join(f"{n} ({c})" for n, c in entries)
                overflow = len(by_prefix[prefix]) - len(entries)
                suffix = f", +{overflow} more" if overflow > 0 else ""
                lines.append(f"  {prefix}: {formatted}{suffix}")

    return "\n".join(lines)

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
  {"type": "header", "props": {"title": "Settings"}, "children": [
    {"type": "icon_button", "component_key": "icon/back"}
  ]},
  {"type": "card", "children": [
    {"type": "heading", "props": {"text": "Notifications"}},
    {"type": "toggle", "props": {"label": "Push alerts", "checked": true}},
    {"type": "toggle", "props": {"label": "Email digest", "checked": false}}
  ]},
  {"type": "card", "children": [
    {"type": "heading", "props": {"text": "Privacy"}},
    {"type": "navigation_row", "props": {"text": "Blocked users"}, "children": [
      {"type": "text", "props": {"text": "Blocked users"}},
      {"type": "icon", "component_key": "icon/chevron-right"}
    ]},
    {"type": "navigation_row", "props": {"text": "Data export"}}
  ]},
  {"type": "button", "variant": "primary", "props": {"text": "Save Changes"}}
]

Notice:
- `component_key: "icon/back"` reuses an EXACT instance from this project
  via Mode-1 lookup. Use component_key values from the "Project component
  keys" section below whenever you'd otherwise emit a generic `icon` or
  generic `button` variant. Project-native always beats catalog-default.
- `variant: "primary"` picks a named variant axis from the component
  catalog (see catalog variant_axes).

Rules:
- Use ONLY the component types listed above
- Group related items inside "card" containers
- Include a "header" at the top of most screens
- Text content goes in props.text, labels in props.label
- Keep it practical: 5-15 top-level components
- Output ONLY the JSON array, no explanation

Container types — always emit these with a "children" array, NEVER as leaves:
  list (children = list_item x N)
  list_item (children = text + optional icon/badge/avatar)
  button_group (children = button x N)
  pagination (children = button x N)
  toggle_group (children = toggle x N)
  segmented_control (children = text x N)
  drawer, dialog, sheet, popover, accordion (children = slot-fillers)
  bottom_nav, tabs (children = items / labels x N)
  header (children = icon_button leading + title + icon_button/avatar trailing)
  table (children = column headers + row cells)
  command (children = search_input + list + list_item x N)

A list_item MUST have at least a text child with its label; emit
  {"type": "list_item", "children": [{"type": "text", "props": {"text": "Blocked users"}}]}
NOT
  {"type": "list_item", "props": {"text": "Blocked users"}}"""


# Responses shorter than this threshold that fail to parse are treated as
# malformed output (not as clarification requests). Raised from the old
# "always return []" contract — see v0.1.5 plan §Week 1 side-fix.
_CLARIFICATION_PROSE_MIN_CHARS = 100


def extract_json(text: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Extract a JSON array from LLM response text.

    Handles plain JSON, markdown code blocks, and text before/after JSON.

    Returns:
    - A ``list`` of component dicts on normal success.
    - A ``{"_clarification_refusal": <prose>}`` dict when the LLM
      returned prose explaining it can't comply (e.g. "I don't have a
      reference image for 'iPhone 13 Pro Max - 109'…"). This restores
      the ADR-008 ``KIND_PROMPT_UNDERSPECIFIED`` signal the pipeline
      used to swallow as ``[]``; callers route it to notes.md and
      skip rendering instead of emitting a blank frame.
    - An empty list on pure malformed output (no prose, no JSON).
    """
    raw_input = text
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

    # No JSON array parseable. Distinguish "LLM asked for clarification
    # or refused" from "LLM emitted noise" by prose length. Anything
    # above the threshold is assumed to be a real refusal / clarification
    # request that the caller must see; shorter noise degrades to the
    # historical empty-list contract.
    prose = raw_input.strip()
    if len(prose) >= _CLARIFICATION_PROSE_MIN_CHARS:
        return {"_clarification_refusal": prose}

    return []


def parse_prompt(
    prompt: str,
    client: Any,
    catalog_types: list[str] | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Parse a natural language prompt into a component list using Claude.

    Returns:
    - A list of component dicts suitable for ``compose_screen()`` on
      normal success.
    - A ``{"_clarification_refusal": <text>}`` dict when the LLM
      refused / asked for clarification (e.g. prompt referenced an
      image the model can't see). Callers surface this as
      ``KIND_PROMPT_UNDERSPECIFIED`` and skip rendering.
    - An empty list for empty/whitespace-only prompts or unparseable
      non-refusal output.

    ``temperature`` is forwarded to the Anthropic API when supplied.
    ADR-008 v0.1.5 sets ``0.3`` as the production default for
    composition; omitting the argument preserves backwards-compat
    behaviour (provider default, typically 1.0).
    """
    if not prompt or not prompt.strip():
        return []

    kwargs: dict[str, Any] = {
        "model": _MODEL,
        "max_tokens": 2048,
        "system": system_prompt or SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    response = client.messages.create(**kwargs)
    response_text = response.content[0].text
    return extract_json(response_text)


def prompt_to_figma(
    prompt: str,
    conn: sqlite3.Connection,
    client: Any,
    page_name: str | None = None,
) -> dict[str, Any]:
    """End-to-end: natural language prompt → Figma JS script.

    Enriches the LLM prompt with project-specific screen patterns
    extracted from the DB, then orchestrates:
    parse_prompt → generate_from_prompt (compose + render).
    When page_name is provided, the script creates a new Figma page.
    """
    file_row = conn.execute("SELECT id FROM files LIMIT 1").fetchone()
    file_id = file_row[0] if file_row else None

    archetype_context = ""
    if file_id:
        archetypes = extract_screen_archetypes(conn, file_id)
        archetype_context = get_archetype_prompt_context(archetypes)

    vocabulary_context = build_project_vocabulary(conn)

    system = SYSTEM_PROMPT
    if archetype_context:
        system = system + "\n\n" + archetype_context
    if vocabulary_context:
        system = system + "\n\n" + vocabulary_context

    # ADR-008 v0.1.5 A1: classify the prompt → one of the 12 canonical
    # archetypes → append the skeleton as few-shot inspiration. No-op
    # when the keyword classifier misses and Haiku either isn't
    # available or also doesn't route. ``DD_DISABLE_ARCHETYPE_LIBRARY=1``
    # short-circuits the whole path.
    matched_archetype = classify_archetype(prompt, client=client)
    system = inject_archetype(system, archetype=matched_archetype)

    components = parse_prompt(prompt, client, system_prompt=system, temperature=_COMPOSE_TEMPERATURE)

    # ADR-008 v0.1.5 side-fix: when the LLM returned a clarification
    # refusal (e.g. "I don't have a reference image for X"),
    # `parse_prompt` returns {"_clarification_refusal": <text>}
    # instead of a component list. Surface as a structured-error
    # payload the driver routes to notes.md; do NOT compose/render
    # an empty screen in that case.
    if isinstance(components, dict) and "_clarification_refusal" in components:
        return {
            "components": [],
            "clarification_refusal": components["_clarification_refusal"],
            "structure_script": None,
            "element_count": 0,
            "warnings": ["LLM returned clarification request; no render emitted."],
            "token_refs": [],
            "template_rebind_entries": [],
            "spec": None,
        }

    result = _generate_from_prompt(conn, components, page_name=page_name)
    result["components"] = components
    return result
