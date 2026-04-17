"""SYSTEM_PROMPT contract variants for the v0.1.5 density matrix.

The density-design memo §3.1 defines five contracts to vary while
holding model + max_tokens constant:

- S0 — current SYSTEM_PROMPT + archetype + vocab (baseline).
- S1 — S0 with a ``<plan>…</plan>`` preamble before the JSON array.
- S2 — S0 with min-count + clarify-as-empty rules.
- S3 — S0 + three worked examples (dashboard / meme-feed / onboarding).
- S4 — minimal control: bare catalog types + output-format note only.

``build_contract_prompt`` is pure — the driver injects the project
archetype + vocab once per run, then maps (variant × prompt × temp)
into Haiku calls with this function as the system-prompt factory.
"""

from __future__ import annotations

from dd.prompt_parser import SYSTEM_PROMPT


CONTRACT_IDS: tuple[str, str, str, str, str] = ("S0", "S1", "S2", "S3", "S4")


_S1_PREAMBLE = (
    "First, write a one-line plan inside <plan>…</plan> listing the "
    "top-level regions you will emit. Then emit the JSON array.\n\n"
)


_S2_APPENDIX = (
    "\n\n"
    "Additional rules for v0.1.5:\n"
    "- If the prompt implies a list/feed/table/carousel/specs screen, "
    "emit at least 4 child items in the corresponding container.\n"
    "- If the prompt is under-specified — e.g. it references an image "
    "or screen ID you cannot see — emit `[]` and do NOT invent a "
    "different screen."
)


_S3_EXAMPLES = """

Worked examples (use as inspiration; modify for the specific prompt):

### Example 1 — dashboard
[
  {"type": "header", "props": {"title": "Dashboard"}},
  {"type": "card", "children": [
    {"type": "heading", "props": {"text": "Revenue"}},
    {"type": "text", "props": {"text": "Last 30 days"}}
  ]},
  {"type": "table", "children": [
    {"type": "text", "props": {"text": "Date"}},
    {"type": "text", "props": {"text": "Amount"}},
    {"type": "list_item", "children": [
      {"type": "text", "props": {"text": "Apr 15"}},
      {"type": "badge", "props": {"text": "$1,204"}}
    ]},
    {"type": "list_item", "children": [
      {"type": "text", "props": {"text": "Apr 14"}},
      {"type": "badge", "props": {"text": "$982"}}
    ]}
  ]}
]

### Example 2 — meme-feed
[
  {"type": "header", "props": {"title": "Feed"}},
  {"type": "list", "children": [
    {"type": "card", "children": [
      {"type": "image"},
      {"type": "text", "props": {"text": "When the tests are green on Friday"}},
      {"type": "button_group", "children": [
        {"type": "button", "props": {"text": "Upvote"}},
        {"type": "button", "props": {"text": "Share"}}
      ]}
    ]},
    {"type": "card", "children": [
      {"type": "image"},
      {"type": "text", "props": {"text": "Monday migration vibes"}},
      {"type": "button_group", "children": [
        {"type": "button", "props": {"text": "Upvote"}},
        {"type": "button", "props": {"text": "Share"}}
      ]}
    ]}
  ]}
]

### Example 3 — onboarding-carousel
[
  {"type": "header", "props": {"title": "Welcome"}},
  {"type": "card", "children": [
    {"type": "image"},
    {"type": "heading", "props": {"text": "Track your finances"}},
    {"type": "text", "props": {"text": "See where your money goes each month."}}
  ]},
  {"type": "card", "children": [
    {"type": "image"},
    {"type": "heading", "props": {"text": "Budget with ease"}},
    {"type": "text", "props": {"text": "Set goals, hit them."}}
  ]},
  {"type": "card", "children": [
    {"type": "image"},
    {"type": "heading", "props": {"text": "Stay on top"}},
    {"type": "text", "props": {"text": "Get alerts that matter."}}
  ]},
  {"type": "button", "variant": "primary", "props": {"text": "Get started"}}
]
"""


_S4_MINIMAL = """You are a UI composition assistant. Given a natural \
language description of a screen, produce a JSON array of components.

Available component types (use ONLY these):

Actions: button, icon_button, fab, button_group, menu, context_menu
Selection & Input: checkbox, radio, toggle, toggle_group, select, \
combobox, date_picker, slider, segmented_control, text_input, textarea, \
search_input, stepper
Content & Display: text, heading, link, image, icon, avatar, badge, \
list, list_item, table, skeleton
Navigation: navigation_row, tabs, breadcrumbs, pagination, bottom_nav, \
drawer, header
Feedback & Status: alert, toast, popover, tooltip, empty_state, \
file_upload
Containment & Overlay: card, dialog, sheet, accordion

Output ONLY a JSON array. No explanation."""


def _compose_baseline(*, archetype: str, vocab: str) -> str:
    """S0 base: current SYSTEM_PROMPT + archetype + vocab injection,
    mirroring ``prompt_to_figma``'s construction."""
    out = SYSTEM_PROMPT
    if archetype:
        out = out + "\n\n" + archetype
    if vocab:
        out = out + "\n\n" + vocab
    return out


def build_contract_prompt(
    variant: str,
    *,
    archetype: str,
    vocab: str,
) -> str:
    """Construct the SYSTEM_PROMPT for one matrix contract variant.

    Raises ValueError if ``variant`` is not one of ``CONTRACT_IDS``.
    """
    if variant not in CONTRACT_IDS:
        raise ValueError(f"unknown contract variant: {variant!r}")

    if variant == "S4":
        return _S4_MINIMAL

    baseline = _compose_baseline(archetype=archetype, vocab=vocab)

    if variant == "S0":
        return baseline
    if variant == "S1":
        return _S1_PREAMBLE + baseline
    if variant == "S2":
        return baseline + _S2_APPENDIX
    if variant == "S3":
        return baseline + _S3_EXAMPLES

    raise ValueError(f"unreachable: variant={variant!r}")
