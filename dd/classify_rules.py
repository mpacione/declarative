"""Centralized classification rules for component identification.

All name matching, system chrome detection, heuristic rules, and structural
patterns live here. This is the single location to audit and tune
classification behavior.
"""

import re
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# Name patterns
# ═══════════════════════════════════════════════════════════════════════════

GENERIC_NAME_RE = re.compile(
    r"^(Frame|Group|Rectangle|Vector|Ellipse|Boolean)\s*\d*$",
    re.IGNORECASE,
)

BUTTON_N_RE = re.compile(r"^Button\s+\d+$")

KEYBOARD_SINGLE_CHAR_RE = re.compile(r"^[a-z]$")


# ═══════════════════════════════════════════════════════════════════════════
# System chrome (OS-level UI excluded from classification)
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_CHROME_EXACT: frozenset[str] = frozenset({
    "home indicator", "homeindicator", "safari - bottom",
    "view mode", "_key", "_keycontainer",
    "shift", "caps lock", "space", "delete", "enter", "emoji",
    "dictation", ".?123", "?.", "!,", "tab",
    "keyboard layout", "keyboard close",
})


def is_system_chrome(name: str) -> bool:
    """Check if a node name represents OS-level system chrome.

    Matches iOS status bars, Safari chrome, keyboard keys,
    and other non-app UI elements.
    """
    lowered = name.strip().lower()

    if lowered.startswith("ios/"):
        return True
    if lowered.startswith("_statusbar"):
        return True
    if lowered in SYSTEM_CHROME_EXACT:
        return True
    if KEYBOARD_SINGLE_CHAR_RE.match(lowered):
        return True
    if lowered.startswith("keyboard "):
        return True

    return False


# ═══════════════════════════════════════════════════════════════════════════
# Name parsing
# ═══════════════════════════════════════════════════════════════════════════

def is_generic_name(name: str) -> bool:
    """Check if a name is auto-generated (Frame 359, Group 12, etc.)."""
    return bool(GENERIC_NAME_RE.match(name))


def parse_component_name(name: str) -> list[str]:
    """Extract candidate lookup keys from a node name, longest first.

    For "button/large/translucent" returns:
      ["button/large/translucent", "button/large", "button"]
    For "Sidebar" returns: ["sidebar"]
    For "Button 3" returns: ["button"]  (normalized)
    For generic names like "Frame 359" returns: []
    """
    if is_generic_name(name):
        return []

    if BUTTON_N_RE.match(name):
        return ["button"]

    lowered = name.strip().lower()
    if not lowered:
        return []

    parts = lowered.split("/")
    candidates = []
    for i in range(len(parts), 0, -1):
        candidates.append("/".join(parts[:i]))
    return candidates


# ═══════════════════════════════════════════════════════════════════════════
# Structural heuristic rules
#
# Each rule takes a node dict and returns (canonical_type, confidence)
# or None if it doesn't match. Rules are applied in priority order.
# ═══════════════════════════════════════════════════════════════════════════

def rule_header(node: dict[str, Any], screen_width: float) -> tuple[str, float] | None:
    """Full-width frame at top of screen with horizontal layout → header."""
    if node["node_type"] != "FRAME":
        return None
    if node["depth"] != 1:
        return None

    y = node.get("y") or 0
    width = node.get("width") or 0
    height = node.get("height") or 0

    is_top = y <= 60
    is_full_width = width >= screen_width * 0.9
    is_short = 30 <= height <= 80

    if is_top and is_full_width and is_short:
        return ("header", 0.85)

    return None


def rule_bottom_nav(
    node: dict[str, Any], screen_width: float, screen_height: float,
) -> tuple[str, float] | None:
    """Full-width frame at bottom of screen → bottom_nav."""
    if node["node_type"] != "FRAME":
        return None
    if node["depth"] != 1:
        return None

    y = node.get("y") or 0
    width = node.get("width") or 0
    height = node.get("height") or 0

    is_bottom = (y + height) >= screen_height * 0.9
    is_full_width = width >= screen_width * 0.9
    is_short = 40 <= height <= 100

    if is_bottom and is_full_width and is_short:
        return ("bottom_nav", 0.8)

    return None


def rule_heading_text(node: dict[str, Any]) -> tuple[str, float] | None:
    """TEXT node with large font size → heading.

    Font size >= 18 is sufficient. Heavy weight increases confidence
    but is not required (many headings use regular weight at large sizes).
    """
    if node["node_type"] != "TEXT":
        return None

    font_size = node.get("font_size")
    if font_size is None:
        return None

    if font_size >= 18:
        font_weight = node.get("font_weight")
        confidence = 0.9 if (font_weight and font_weight >= 600) else 0.8
        return ("heading", confidence)

    return None


def rule_body_text(node: dict[str, Any]) -> tuple[str, float] | None:
    """TEXT node with standard font size → text."""
    if node["node_type"] != "TEXT":
        return None

    font_size = node.get("font_size")
    if font_size is None:
        return None

    if 8 <= font_size < 18:
        return ("text", 0.85)

    return None


def _has_visual_properties(node: dict[str, Any]) -> bool:
    """Check if a node has visual properties (fills, strokes, effects)."""
    for prop in ("fills", "strokes", "effects"):
        raw = node.get(prop)
        if raw and raw != "[]":
            return True
    return False


def rule_generic_frame_container(node: dict[str, Any]) -> tuple[str, float] | None:
    """Generic 'Frame N' or 'Group N' → container or surface.

    Unnamed structural frames that Figma auto-generates are layout
    containers ONLY if they have no visual properties. Frames with
    fills, strokes, or effects are visual elements (surfaces).
    """
    if node["node_type"] not in ("FRAME", "GROUP"):
        return None

    name = node.get("name", "")
    if not is_generic_name(name):
        return None

    if _has_visual_properties(node):
        return None

    return ("container", 0.7)


# ═══════════════════════════════════════════════════════════════════════════
# Rule application order
# ═══════════════════════════════════════════════════════════════════════════

def apply_heuristic_rules(
    node: dict[str, Any],
    screen_width: float,
    screen_height: float,
) -> tuple[str, float] | None:
    """Apply all heuristic rules in priority order.

    Returns (canonical_type, confidence) or None.
    """
    result = rule_header(node, screen_width)
    if result:
        return result

    result = rule_bottom_nav(node, screen_width, screen_height)
    if result:
        return result

    result = rule_heading_text(node)
    if result:
        return result

    result = rule_body_text(node)
    if result:
        return result

    result = rule_generic_frame_container(node)
    if result:
        return result

    return None
