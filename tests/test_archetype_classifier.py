"""Tests for the v0.1.5 archetype classifier.

Routes a natural-language prompt to one of the 12 archetype skeletons.
Primary path is a literal-keyword match; Haiku 4.5 is the fallback for
prompts that don't hit any keyword.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from dd.composition.archetype_classifier import (
    classify_archetype,
    classify_by_keyword,
)


def _mock_client(archetype_name: str | None) -> MagicMock:
    """Mock an Anthropic client returning a JSON object with archetype name."""
    client = MagicMock()
    message = MagicMock()
    body = json.dumps({"archetype": archetype_name}) if archetype_name else "{}"
    message.content = [MagicMock(text=body)]
    client.messages.create.return_value = message
    return client


# --------------------------------------------------------------------------- #
# Keyword classifier                                                          #
# --------------------------------------------------------------------------- #

class TestKeywordRouting:
    @pytest.mark.parametrize("prompt,expected", [
        ("a login screen with email, password, and a sign-in button", "login"),
        ("sign-in page", "login"),
        ("a profile settings page with avatar", "settings"),
        ("a feed of memes with upvote and share buttons under each", "feed"),
        ("a data dashboard with a line chart and a table", "dashboard"),
        ("a paywall screen with three pricing tiers", "paywall"),
        ("a search screen", "search"),
        ("a drawer menu with 6 nav items", "drawer-nav"),
        ("an onboarding carousel with 3 slides", "onboarding-carousel"),
        ("user profile page", "profile"),
        ("a chat screen with messages", "chat"),
        ("empty state when no data", "empty-state"),
        ("product detail page", "detail"),
    ])
    def test_routes_canonical_prompts(self, prompt, expected):
        assert classify_by_keyword(prompt) == expected

    def test_unmatched_prompt_returns_none(self):
        assert classify_by_keyword("something cool") is None
        assert classify_by_keyword("rebuild iPhone 13 Pro Max - 109 from scratch") is None


# --------------------------------------------------------------------------- #
# classify_archetype (keyword → Haiku fallback)                               #
# --------------------------------------------------------------------------- #

class TestClassifyArchetype:
    def test_keyword_match_short_circuits_no_client_call(self):
        client = _mock_client("feed")  # would be wrong if called
        result = classify_archetype("a login screen", client=client)
        assert result == "login"
        client.messages.create.assert_not_called()

    def test_falls_back_to_haiku_when_keyword_misses(self):
        client = _mock_client("empty-state")
        result = classify_archetype("something cool", client=client)
        assert result == "empty-state"
        client.messages.create.assert_called_once()

    def test_haiku_returns_unknown_archetype_degrades_to_none(self):
        """If Haiku picks an archetype that isn't in the library, we
        degrade to no-archetype rather than crash."""
        client = _mock_client("holographic-wallet")
        result = classify_archetype("something cool", client=client)
        assert result is None

    def test_no_client_no_keyword_match_returns_none(self):
        result = classify_archetype("something cool", client=None)
        assert result is None

    def test_haiku_malformed_response_returns_none(self):
        client = MagicMock()
        message = MagicMock()
        message.content = [MagicMock(text="what do you mean?")]
        client.messages.create.return_value = message
        result = classify_archetype("something cool", client=client)
        assert result is None

    def test_feature_flag_disables_classifier(self, monkeypatch):
        monkeypatch.setenv("DD_DISABLE_ARCHETYPE_LIBRARY", "1")
        client = _mock_client("feed")
        result = classify_archetype("a login screen", client=client)
        assert result is None
        client.messages.create.assert_not_called()

    def test_empty_prompt_returns_none(self):
        assert classify_archetype("", client=None) is None
        assert classify_archetype("   ", client=None) is None
