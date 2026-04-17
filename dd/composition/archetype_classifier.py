"""Archetype classifier for the ADR-008 v0.1.5 A1 uplift.

Routes a natural-language prompt to one of the 12 archetype skeletons
in ``dd/archetype_library/``. Literal-keyword match first (fast, zero-
latency); Haiku 4.5 fallback for prompts that miss every keyword.

Feature flag ``DD_DISABLE_ARCHETYPE_LIBRARY=1`` skips the whole path
and returns None, leaving the compose pipeline on v0.1 SYSTEM_PROMPT-
only behaviour for rollback.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dd.archetype_library import ARCHETYPE_NAMES


_HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Ordered keyword → archetype map. First match wins — more specific
# patterns must come first. Each key is a case-insensitive substring /
# alternation-regex-friendly token. Boundaries baked into the compiled
# pattern via \b so "login" matches "a login screen" but not "login-ish".
_KEYWORD_MAP: tuple[tuple[str, str], ...] = (
    # --- onboarding-carousel (before feed/search to avoid drift) ---
    (r"onboarding\s+carousel", "onboarding-carousel"),
    (r"\bcarousel\b", "onboarding-carousel"),
    (r"\bonboarding\b", "onboarding-carousel"),
    (r"\bwelcome\s+screen\b", "onboarding-carousel"),
    (r"\bintro\s+slides?\b", "onboarding-carousel"),

    # --- drawer-nav (before 'profile'/'settings' since 'nav menu' is ambiguous) ---
    (r"\bdrawer\b", "drawer-nav"),
    (r"\bside\s+menu\b", "drawer-nav"),
    (r"\bnav\s+menu\b", "drawer-nav"),
    (r"\bhamburger\s+menu\b", "drawer-nav"),

    # --- paywall ---
    (r"\bpaywall\b", "paywall"),
    (r"\bpricing\s+tiers?\b", "paywall"),
    (r"\bsubscribe\b", "paywall"),
    (r"\bsubscription\s+plans?\b", "paywall"),

    # --- dashboard ---
    (r"\bdashboard\b", "dashboard"),
    (r"\banalytics\b", "dashboard"),
    (r"\bmetrics\s+page\b", "dashboard"),

    # --- feed (before 'search' to route 'search feed' → feed) ---
    (r"\bfeed\b", "feed"),
    (r"\btimeline\b", "feed"),
    (r"\binfinite\s+scroll\b", "feed"),
    (r"\bsocial\s+posts?\b", "feed"),

    # --- search ---
    (r"\bsearch\s+screen\b", "search"),
    (r"\bsearch\s+page\b", "search"),
    (r"^search$", "search"),
    (r"\bsearch\b", "search"),

    # --- login (before 'sign' alone which could appear in 'design') ---
    (r"\blogin\b", "login"),
    (r"\bsign[-\s]in\b", "login"),
    (r"\bsign[-\s]up\b", "login"),
    (r"\bauth(entication)?\s+screen\b", "login"),

    # --- settings (before 'profile' since 'profile settings' → settings) ---
    (r"\bsettings\b", "settings"),
    (r"\bpreferences\b", "settings"),
    (r"\baccount\s+settings\b", "settings"),

    # --- chat ---
    (r"\bchat\b", "chat"),
    (r"\bmessag(es?|ing)\b", "chat"),
    (r"\bconversation\b", "chat"),

    # --- profile (after settings) ---
    (r"\bprofile\b", "profile"),
    (r"\buser\s+page\b", "profile"),

    # --- detail ---
    (r"\bdetail\s+page\b", "detail"),
    (r"\bproduct\s+detail\b", "detail"),
    (r"\bspec\s+sheet\b", "detail"),
    (r"\bitem\s+detail\b", "detail"),

    # --- empty-state ---
    (r"\bempty\s+state\b", "empty-state"),
    (r"\bno\s+data\b", "empty-state"),
    (r"\bnothing\s+(to\s+show|here)\b", "empty-state"),
)


def classify_by_keyword(prompt: str) -> str | None:
    """Match the first keyword hit. Returns archetype name or None."""
    if not prompt:
        return None
    lowered = prompt.lower()
    for pattern, archetype in _KEYWORD_MAP:
        if re.search(pattern, lowered):
            return archetype
    return None


def _haiku_classify(prompt: str, client: Any) -> str | None:
    """Ask Haiku to pick an archetype name. Returns None if the
    response is malformed or names an unknown archetype."""
    system = (
        "You are a UI archetype classifier. Given a natural language "
        "description of a screen, pick the single best-matching "
        "archetype from this list:\n"
        f"  {', '.join(ARCHETYPE_NAMES)}\n\n"
        "Output ONLY a JSON object: {\"archetype\": \"<name>\"} or "
        "{\"archetype\": null} if none fits."
    )
    try:
        response = client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=64,
            temperature=0.0,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
    except Exception:  # noqa: BLE001 — classifier is best-effort
        return None

    # Classifier expects a single JSON object ``{"archetype": "<name>"}``;
    # we don't reuse ``extract_json`` here because that module's
    # list-extraction heuristics are for the compose path, and a direct
    # import would introduce a circular dependency once the classifier
    # is wired into ``prompt_to_figma``.
    stripped = text.strip()
    # Tolerate ```json fences and surrounding prose.
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", stripped, re.DOTALL)
    if fence_match:
        stripped = fence_match.group(1).strip()
    obj_match = re.search(r"\{.*?\}", stripped, re.DOTALL)
    if obj_match:
        stripped = obj_match.group(0)
    try:
        payload = json.loads(stripped)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None

    archetype = payload.get("archetype")
    if isinstance(archetype, str) and archetype in ARCHETYPE_NAMES:
        return archetype
    return None


def classify_archetype(prompt: str, *, client: Any | None = None) -> str | None:
    """Classify a prompt to an archetype name.

    Literal-keyword match first; Haiku fallback if provided; None if
    nothing routes. Respects the ``DD_DISABLE_ARCHETYPE_LIBRARY`` flag
    so the archetype-conditioned path can be rolled back in one env var.
    """
    if os.environ.get("DD_DISABLE_ARCHETYPE_LIBRARY") == "1":
        return None
    if not prompt or not prompt.strip():
        return None

    keyword_hit = classify_by_keyword(prompt)
    if keyword_hit is not None:
        return keyword_hit

    if client is None:
        return None

    return _haiku_classify(prompt, client)
