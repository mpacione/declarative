"""Archetype skeleton library for the ADR-008 v0.1.5 A1 uplift.

Canonical screen-level skeletons the LLM sees as few-shot inspiration
at compose time. ``ArchetypeLibraryProvider`` (Step 3) and the
SYSTEM_PROMPT injection wire these into the pipeline.

Provenance model:
- **corpus-mined**: extracted from a representative screen in the
  project DB — {slot, child_count_bucket}-style clustering.
- **hand-authored**: authored for v0.1.5 from the 12 canonical prompts
  and the Mobbin-style taxonomy. The current state is 100% hand-
  authored because Dank's ``components`` and
  ``screen_component_instances`` tables are empty; re-running the
  classifier chain is v0.2 work.

All skeletons are stored as ``skeletons/<name>.json`` — JSON arrays
shaped like the LLM's own output (``[{type, variant?, children}, ...]``)
with concrete text/colours/icon keys pruned so the LLM fills them.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_SKELETONS_DIR = Path(__file__).resolve().parent / "skeletons"
_PROVENANCE_PATH = Path(__file__).resolve().parent / "provenance.json"


# Canonical archetype names — kebab-case so they double as taxonomy
# keys + filesystem stems. Kept as a tuple so importers see the ordering
# (login first, Mobbin-ish sweep through feed/detail/settings, then the
# extras for wider canonical-prompt coverage).
ARCHETYPE_NAMES: tuple[str, ...] = (
    "login",
    "settings",
    "feed",
    "dashboard",
    "paywall",
    "search",
    "drawer-nav",
    "onboarding-carousel",
    "profile",
    "chat",
    "empty-state",
    "detail",
)


def list_archetypes() -> list[str]:
    return list(ARCHETYPE_NAMES)


@lru_cache(maxsize=None)
def load_skeleton(name: str) -> list[dict[str, Any]]:
    path = _SKELETONS_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"unknown archetype: {name!r}")
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def load_provenance() -> dict[str, dict[str, Any]]:
    return json.loads(_PROVENANCE_PATH.read_text())
