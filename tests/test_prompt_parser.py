"""Tests for LLM prompt parsing (natural language → component list)."""

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from dd.catalog import seed_catalog
from dd.db import init_db
from dd.prompt_parser import SYSTEM_PROMPT, extract_json, parse_prompt, prompt_to_figma

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _mock_client(response_text: str) -> MagicMock:
    client = MagicMock()
    message = MagicMock()
    message.content = [MagicMock(text=response_text)]
    client.messages.create.return_value = message
    return client


VALID_RESPONSE = json.dumps([
    {"type": "header", "props": {"text": "Settings"}},
    {"type": "card", "children": [
        {"type": "heading", "props": {"text": "Notifications"}},
        {"type": "toggle", "props": {"label": "Push alerts"}},
    ]},
    {"type": "button", "props": {"text": "Save"}},
])

MARKDOWN_WRAPPED = f"```json\n{VALID_RESPONSE}\n```"

CATALOG_TYPES = [
    "button", "header", "card", "heading", "text", "toggle",
    "icon", "tabs", "image", "badge",
]


# ---------------------------------------------------------------------------
# extract_json tests
# ---------------------------------------------------------------------------

class TestExtractJson:
    """Verify JSON extraction from LLM responses."""

    def test_plain_json(self):
        result = extract_json('[{"type": "button"}]')
        assert result == [{"type": "button"}]

    def test_markdown_code_block(self):
        result = extract_json('```json\n[{"type": "button"}]\n```')
        assert result == [{"type": "button"}]

    def test_markdown_without_language(self):
        result = extract_json('```\n[{"type": "button"}]\n```')
        assert result == [{"type": "button"}]

    def test_text_before_json(self):
        result = extract_json('Here is the component list:\n[{"type": "button"}]')
        assert result == [{"type": "button"}]

    def test_invalid_json_returns_empty(self):
        result = extract_json('not json at all')
        assert result == []


# ---------------------------------------------------------------------------
# parse_prompt tests
# ---------------------------------------------------------------------------

class TestParsePrompt:
    """Verify parse_prompt calls Claude and returns component list."""

    def test_returns_component_list(self):
        client = _mock_client(VALID_RESPONSE)
        result = parse_prompt("build a settings page", client, CATALOG_TYPES)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["type"] == "header"

    def test_calls_claude_with_system_prompt(self):
        client = _mock_client(VALID_RESPONSE)
        parse_prompt("build a settings page", client, CATALOG_TYPES)
        call = client.messages.create.call_args
        assert call.kwargs.get("system") or any("catalog" in str(a).lower() for a in call.args)

    def test_handles_markdown_wrapped_response(self):
        client = _mock_client(MARKDOWN_WRAPPED)
        result = parse_prompt("build a settings page", client, CATALOG_TYPES)
        assert len(result) == 3

    def test_passes_user_prompt_as_message(self):
        client = _mock_client(VALID_RESPONSE)
        parse_prompt("build a dashboard", client, CATALOG_TYPES)
        call = client.messages.create.call_args
        messages = call.kwargs.get("messages", [])
        user_content = messages[0]["content"] if messages else ""
        assert "dashboard" in user_content

    def test_empty_response_returns_empty_list(self):
        client = _mock_client("I can't help with that")
        result = parse_prompt("something invalid", client, CATALOG_TYPES)
        assert result == []

    def test_nested_children_preserved(self):
        client = _mock_client(VALID_RESPONSE)
        result = parse_prompt("settings page", client, CATALOG_TYPES)
        card = next(c for c in result if c["type"] == "card")
        assert len(card["children"]) == 2


# ---------------------------------------------------------------------------
# prompt_to_figma tests
# ---------------------------------------------------------------------------

class TestPromptToFigma:
    """Verify prompt_to_figma end-to-end with mocked LLM."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, instance_count, layout_mode, width, height, "
            "fills, corner_radius, opacity) "
            "VALUES ('button', 'default', 10, 'HORIZONTAL', 200, 48, "
            "'[{\"type\":\"SOLID\",\"color\":{\"r\":0,\"g\":0.5,\"b\":1,\"a\":1}}]', '10', 1.0)"
        )
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, instance_count, layout_mode, width, height, opacity) "
            "VALUES ('heading', 'default', 5, NULL, 396, 28, 1.0)"
        )
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, instance_count, layout_mode, width, height, "
            "fills, corner_radius, opacity) "
            "VALUES ('card', 'default', 10, 'VERTICAL', 428, 194, "
            "'[{\"type\":\"SOLID\",\"color\":{\"r\":1,\"g\":1,\"b\":1,\"a\":1}}]', '28', 1.0)"
        )
        conn.commit()
        yield conn
        conn.close()

    def test_produces_figma_script(self, db):
        client = _mock_client(VALID_RESPONSE)
        result = prompt_to_figma("build a settings page", db, client)
        assert "structure_script" in result
        assert "figma.createFrame()" in result["structure_script"]

    def test_script_has_layout(self, db):
        client = _mock_client(VALID_RESPONSE)
        result = prompt_to_figma("settings page", db, client)
        assert "layoutMode" in result["structure_script"]

    def test_returns_element_count(self, db):
        client = _mock_client(VALID_RESPONSE)
        result = prompt_to_figma("settings page", db, client)
        assert result["element_count"] >= 4

    def test_returns_parsed_components(self, db):
        client = _mock_client(VALID_RESPONSE)
        result = prompt_to_figma("settings page", db, client)
        assert "components" in result
        assert len(result["components"]) == 3


# ---------------------------------------------------------------------------
# System prompt tests
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    """Verify the system prompt contains expected catalog types."""

    def test_contains_catalog_types(self):
        prompt = SYSTEM_PROMPT
        assert "button" in prompt
        assert "header" in prompt
        assert "card" in prompt
        assert "toggle" in prompt

    def test_contains_output_format(self):
        prompt = SYSTEM_PROMPT
        assert '"type"' in prompt
        assert '"props"' in prompt
        assert '"children"' in prompt
