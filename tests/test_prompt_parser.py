"""Tests for LLM prompt parsing (natural language → component list)."""

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from dd.catalog import seed_catalog
from dd.db import init_db
from dd.prompt_parser import SYSTEM_PROMPT, build_project_vocabulary, extract_json, parse_prompt, prompt_to_figma

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

    def test_long_prose_returns_clarification_refusal(self):
        """ADR-008 v0.1.5 side-fix: when the LLM returns ≥100 chars of
        non-JSON prose (e.g. asking for clarification), extract_json
        returns a dict with ``_clarification_refusal`` so the driver
        surfaces it as KIND_PROMPT_UNDERSPECIFIED instead of silently
        treating it as an empty component list."""
        prose = (
            "I don't have a reference image or description of "
            "'iPhone 13 Pro Max - 109'. Could you share a screenshot "
            "or describe the screen you'd like me to rebuild?"
        )
        result = extract_json(prose)
        assert isinstance(result, dict)
        assert "_clarification_refusal" in result
        assert "iPhone 13 Pro Max - 109" in result["_clarification_refusal"]

    def test_short_noise_still_returns_empty(self):
        """Under the 100-char threshold, treat as noise — preserves
        historical contract for tiny malformed outputs."""
        result = extract_json('oops')
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

    def test_empty_prompt_returns_empty_list(self):
        client = _mock_client(VALID_RESPONSE)
        result = parse_prompt("", client, CATALOG_TYPES)
        assert result == []
        client.messages.create.assert_not_called()

    def test_whitespace_prompt_returns_empty_list(self):
        client = _mock_client(VALID_RESPONSE)
        result = parse_prompt("   \n  ", client, CATALOG_TYPES)
        assert result == []
        client.messages.create.assert_not_called()

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

    def test_empty_prompt_returns_empty_screen(self, db):
        client = _mock_client(VALID_RESPONSE)
        result = prompt_to_figma("", db, client)
        assert result["components"] == []
        assert result["element_count"] == 1  # just the root screen element
        client.messages.create.assert_not_called()

    def test_archetype_skeleton_injected_when_classifier_matches(self, db):
        """ADR-008 v0.1.5 A1: when the prompt routes to a known
        archetype, the skeleton JSON is appended to the system prompt
        so the LLM sees it as few-shot inspiration."""
        client = _mock_client(VALID_RESPONSE)
        prompt_to_figma("a dashboard with line chart and a table", db, client)
        call = client.messages.create.call_args
        system = call.kwargs.get("system", "")
        assert "dashboard" in system.lower()
        # Skeleton fragment includes a JSON code fence
        assert "```json" in system

    def test_no_archetype_injection_when_classifier_misses(self, db):
        """Prompts that don't match any keyword and fall through to the
        Haiku classifier returning None should see an unchanged
        SYSTEM_PROMPT."""
        # Haiku classifier can be hit in this path; stub it to return
        # an "unknown" payload so classify_archetype → None.
        noop_client = MagicMock()
        # First call = classifier (returns malformed); second call = parse
        classify_msg = MagicMock()
        classify_msg.content = [MagicMock(text='{"archetype": null}')]
        parse_msg = MagicMock()
        parse_msg.content = [MagicMock(text=VALID_RESPONSE)]
        noop_client.messages.create.side_effect = [classify_msg, parse_msg]

        prompt_to_figma("something cool", db, noop_client)

        # The parse call (second) is the one we care about.
        calls = noop_client.messages.create.call_args_list
        parse_call_system = calls[-1].kwargs.get("system", "")
        # No archetype fragment — framing template's signature line absent.
        assert "canonical skeleton for the" not in parse_call_system.lower()

    def test_archetype_injection_disabled_by_flag(self, db, monkeypatch):
        monkeypatch.setenv("DD_DISABLE_ARCHETYPE_LIBRARY", "1")
        client = _mock_client(VALID_RESPONSE)
        prompt_to_figma("a dashboard with line chart", db, client)
        call = client.messages.create.call_args
        system = call.kwargs.get("system", "")
        assert "canonical skeleton for the" not in system.lower()
        # Only one Haiku call — no classifier call when flag is set.
        assert client.messages.create.call_count == 1

    # ---- ADR-008 v0.1.5 A2 plan-then-fill wiring ----

    def test_a2_flag_off_uses_single_call_path(self, db):
        """With DD_ENABLE_PLAN_THEN_FILL unset, behaviour is unchanged
        from A1 (single parse call after the optional archetype
        classifier)."""
        client = _mock_client(VALID_RESPONSE)
        prompt_to_figma("settings page", db, client)
        # Single Haiku call (just the parse) — classifier short-circuited
        # on the 'settings' keyword.
        assert client.messages.create.call_count == 1

    def test_a2_flag_on_fires_plan_then_fill(self, db, monkeypatch):
        """With DD_ENABLE_PLAN_THEN_FILL=1, prompt_to_figma routes to
        the plan + fill two-call path."""
        monkeypatch.setenv("DD_ENABLE_PLAN_THEN_FILL", "1")
        monkeypatch.setenv("DD_DISABLE_ARCHETYPE_LIBRARY", "1")

        plan = json.dumps([
            {"type": "header", "id": "hdr", "children": [
                {"type": "text", "id": "title"},
            ]},
            {"type": "card", "id": "c", "children": [
                {"type": "heading", "id": "h"},
                {"type": "toggle", "id": "t", "count_hint": 1},
            ]},
            {"type": "button", "id": "b"},
        ])
        fill = json.dumps([
            {"type": "header", "children": [{"type": "text", "props": {"text": "Settings"}}]},
            {"type": "card", "children": [
                {"type": "heading", "props": {"text": "Prefs"}},
                {"type": "toggle", "props": {"label": "Dark mode"}},
            ]},
            {"type": "button", "props": {"text": "Save"}},
        ])
        client = MagicMock()
        client.messages.create.side_effect = [
            MagicMock(content=[MagicMock(text=plan)]),
            MagicMock(content=[MagicMock(text=fill)]),
        ]
        result = prompt_to_figma("a settings page", db, client)
        # Plan + fill = 2 calls.
        assert client.messages.create.call_count == 2
        # Result should still carry components per the existing contract.
        assert "components" in result
        assert len(result["components"]) == 3

    def test_a2_plan_invalid_surfaces_structured_error(self, db, monkeypatch):
        monkeypatch.setenv("DD_ENABLE_PLAN_THEN_FILL", "1")
        monkeypatch.setenv("DD_DISABLE_ARCHETYPE_LIBRARY", "1")
        bad_plan = json.dumps([{"type": "holographic_widget", "id": "h"}])
        client = MagicMock()
        client.messages.create.side_effect = [
            MagicMock(content=[MagicMock(text=bad_plan)]),
        ]
        result = prompt_to_figma("a settings page", db, client)
        assert result.get("kind") == "KIND_PLAN_INVALID"
        assert result["components"] == []
        # Fill must NOT have fired.
        assert client.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# System prompt tests
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# build_project_vocabulary tests
# ---------------------------------------------------------------------------

class TestBuildProjectVocabulary:
    """Verify project vocabulary extraction from templates."""

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute("INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'Dank')")
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, component_key, instance_count, "
            "layout_mode, width, height, opacity, slots) "
            "VALUES ('button', 'button/large/translucent', 'key_btn_lt', 3606, "
            "'HORIZONTAL', 152, 52, 1.0, "
            "'[{\"child_type\": \"icon\", \"count_mode\": 2, \"component_key\": \"key_icon\", \"frequency\": 0.95}]')"
        )
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, component_key, instance_count, "
            "layout_mode, width, height, opacity) "
            "VALUES ('tabs', 'nav/tabs', 'key_tabs', 812, "
            "'HORIZONTAL', 489, 44, 1.0)"
        )
        conn.execute(
            "INSERT INTO component_templates "
            "(catalog_type, variant, instance_count, "
            "layout_mode, width, height, opacity) "
            "VALUES ('card', NULL, 10, "
            "'VERTICAL', 428, 194, 1.0)"
        )
        conn.commit()
        yield conn
        conn.close()

    def test_returns_string(self, db):
        result = build_project_vocabulary(db)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_variant_names(self, db):
        result = build_project_vocabulary(db)
        assert "button/large/translucent" in result

    def test_includes_instance_counts(self, db):
        result = build_project_vocabulary(db)
        assert "3606" in result

    def test_excludes_low_count_templates(self, db):
        result = build_project_vocabulary(db, min_instances=100)
        # Templates section excludes card (10 instances). Don't assert
        # "card not in result" because the CKR section may surface card-
        # prefixed keys independently.
        templates_block = result.split("Project component keys")[0]
        assert "card" not in templates_block
        assert "button/large/translucent" in result

    @staticmethod
    def _ensure_ckr_table(conn: sqlite3.Connection) -> None:
        # CKR table is created lazily by build_component_key_registry;
        # tests that exercise the CKR branch of build_project_vocabulary
        # need to mirror that shape here.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS component_key_registry ("
            "component_key TEXT PRIMARY KEY, "
            "figma_node_id TEXT, "
            "name TEXT NOT NULL, "
            "instance_count INTEGER)"
        )

    def test_includes_ckr_component_keys(self, db):
        """ADR-008 Tier 2: CKR entries surface to LLM for Mode-1 reuse."""
        self._ensure_ckr_table(db)
        db.execute(
            "INSERT INTO component_key_registry "
            "(component_key, figma_node_id, name, instance_count) "
            "VALUES ('k1', 'n1', 'icon/chevron-right', 16), "
            "('k2', 'n2', 'button/primary', 42), "
            "('k3', 'n3', 'logo/dank', 8)"
        )
        db.commit()
        result = build_project_vocabulary(db)
        assert "icon/chevron-right" in result
        assert "button/primary" in result
        assert "logo/dank" in result

    def test_ckr_section_distinct_header(self, db):
        """CKR keys appear under a distinct header so the LLM knows
        they are Mode-1-reusable keys, not Mode-2 type variants."""
        self._ensure_ckr_table(db)
        db.execute(
            "INSERT INTO component_key_registry "
            "(component_key, figma_node_id, name, instance_count) "
            "VALUES ('k1', 'n1', 'icon/menu', 5)"
        )
        db.commit()
        result = build_project_vocabulary(db)
        assert "component_key" in result.lower() or "Project component keys" in result

    def test_ckr_missing_table_is_gracefully_skipped(self, db):
        """DBs without CKR (older schema) should not crash the
        vocabulary builder — the CKR section is just absent."""
        # Fixture `db` does NOT create the CKR table.
        result = build_project_vocabulary(db)
        assert isinstance(result, str)
        # Templates section still renders; CKR section is absent.
        assert "button/large/translucent" in result


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

    def test_mentions_container_types(self):
        """ADR-008 Tier 2: LLM must know which types are containers
        so list/list_item/pagination/header/etc. get emitted with
        children, not as empty leaves."""
        prompt = SYSTEM_PROMPT.lower()
        # The prompt should call out containers by name so the LLM
        # stops emitting them as leaves with a single `text` prop.
        assert "container" in prompt or "nested" in prompt
        # Explicit namedrop of the highest-volume offender from the v3
        # baseline failure taxonomy:
        assert "list_item" in prompt


class TestMode3RegistryIncludesProjectCKR:
    """Stage 0 cleanup (docs/plan-authoring-loop.md §4.1): the Mode-3
    cascade must include ProjectCKRProvider between
    CorpusRetrievalProvider (priority 150) and UniversalCatalogProvider
    (priority 10). Without it the project's own component_key_registry
    + variant_token_binding rows never win the resolution cascade, and
    "Mode 3 resolves project components" doesn't actually work
    end-to-end. The two Mode-3 registries (one in dd/prompt_parser.py,
    one in dd/compose.py) must both include it — otherwise fixing
    one site silently leaves the other drifted."""

    def _has_provider_of_class(self, registry, cls):
        # ProviderRegistry exposes its ordered providers list;
        # when it doesn't, fall back to duck-typing the `backend`.
        providers = getattr(registry, "providers", None) or []
        return any(isinstance(p, cls) for p in providers)

    def test_prompt_parser_mode3_registry_includes_project_ckr(self):
        import sqlite3

        from dd.composition.providers.project_ckr import ProjectCKRProvider
        from dd.prompt_parser import _build_mode3_registry
        conn = sqlite3.connect(":memory:")
        reg = _build_mode3_registry(conn)
        assert self._has_provider_of_class(reg, ProjectCKRProvider)

    def test_compose_default_mode3_registry_includes_project_ckr(self):
        import sqlite3

        from dd.compose import _build_default_mode3_registry
        from dd.composition.providers.project_ckr import ProjectCKRProvider
        conn = sqlite3.connect(":memory:")
        reg = _build_default_mode3_registry(conn)
        assert self._has_provider_of_class(reg, ProjectCKRProvider)
