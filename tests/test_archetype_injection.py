"""Tests for the v0.1.5 archetype SYSTEM_PROMPT injection.

Builds the "here's a canonical skeleton" fragment that prepends /
appends to the SYSTEM_PROMPT when the archetype classifier matches.

The injection:
- is *inspiration, not a template* — the framing text must say so
- surfaces the matched archetype name so the LLM knows the route
- embeds the raw skeleton JSON inline so the LLM can read / mutate
  (no string summarisation; the LLM handles JSON better than prose)
"""

from __future__ import annotations

import json

import pytest

from dd.composition.archetype_injection import (
    build_archetype_injection,
    inject_archetype,
)


# --------------------------------------------------------------------------- #
# build_archetype_injection                                                   #
# --------------------------------------------------------------------------- #

class TestBuildInjection:
    def test_names_matched_archetype(self):
        text = build_archetype_injection("login")
        assert "login" in text

    def test_frames_as_inspiration_not_template(self):
        text = build_archetype_injection("dashboard")
        lower = text.lower()
        assert "inspiration" in lower
        # Must explicitly invite modification; don't let the LLM copy verbatim.
        assert "modify" in lower or "adapt" in lower or "not copy" in lower

    def test_embeds_full_skeleton_as_valid_json(self):
        text = build_archetype_injection("feed")
        start = text.find("[")
        end = text.rfind("]")
        assert start != -1 and end != -1
        parsed = json.loads(text[start:end + 1])
        assert isinstance(parsed, list)
        assert len(parsed) >= 1
        # First element must be a node with a type
        assert "type" in parsed[0]

    def test_unknown_archetype_raises(self):
        with pytest.raises(ValueError):
            build_archetype_injection("not-an-archetype")


# --------------------------------------------------------------------------- #
# inject_archetype (SYSTEM_PROMPT composition)                                #
# --------------------------------------------------------------------------- #

BASE_SYSTEM = "You are a UI composition assistant. Do the thing."


class TestInjectArchetype:
    def test_none_archetype_passes_system_through_unchanged(self):
        out = inject_archetype(BASE_SYSTEM, archetype=None)
        assert out == BASE_SYSTEM

    def test_matched_archetype_appends_skeleton_fragment(self):
        out = inject_archetype(BASE_SYSTEM, archetype="login")
        assert out.startswith(BASE_SYSTEM)
        assert len(out) > len(BASE_SYSTEM)
        assert "login" in out.lower()

    def test_preserves_base_system_verbatim(self):
        """Injection is additive — the base SYSTEM_PROMPT must be
        byte-for-byte preserved so v0.1 contract semantics are
        unchanged when archetype fires."""
        out = inject_archetype(BASE_SYSTEM, archetype="dashboard")
        assert BASE_SYSTEM in out

    def test_unknown_archetype_degrades_to_passthrough(self):
        """An unknown name should not crash the pipeline. Degrades to
        passthrough like the classifier returning None."""
        out = inject_archetype(BASE_SYSTEM, archetype="not-an-archetype")
        assert out == BASE_SYSTEM
