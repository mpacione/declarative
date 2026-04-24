"""Stage 1.2 — unified `propose_edits` orchestrator.

Wraps all 7 verb tool schemas into one entry point the LLM uses
to emit a single edit against a current tree state. Reuses the
per-verb schemas from `dd/structural_verbs.py` (Stage 1.1) instead
of re-implementing them, and lowers the LLM's tool_use response
into edit-grammar source that `apply_edits` consumes.

Per Codex (2026-04-23 fork decision): registers all 7 tools in the
same `tools=[...]` array — Anthropic tool-use's native "pick one
of these tools" matches verb-pick semantics. Discriminator-in-one-
tool was the alternative; rejected because it requires post-hoc
validation anyway and produces worse error modes when Claude picks
the wrong nested shape.

Risk Codex flagged: Claude may emit MULTIPLE tool calls per turn.
The orchestrator must enforce "exactly one edit tool call per
turn" and surface a clear retry signal otherwise — these tests
pin that contract.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dd.markup_l3 import apply_edits, parse_l3
from dd.propose_edits import (
    ProposeEditsResult,
    build_propose_edits_tools,
    parse_tool_call_to_edit,
    propose_edits,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

def _fixture_doc():
    src = (
        "screen #screen-1 {\n"
        "  frame #frame-1 {\n"
        "    text #title \"hello\"\n"
        "    rectangle #badge\n"
        "  }\n"
        "  frame #archive\n"
        "}\n"
    )
    return parse_l3(src)


def _mock_tool_use_response(tool_name: str, input_dict: dict) -> MagicMock:
    """Mimic an Anthropic SDK Message containing one tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = input_dict
    msg = MagicMock()
    msg.content = [tool_block]
    msg.stop_reason = "tool_use"
    return msg


def _mock_no_tool_response(text: str = "I cannot do that") -> MagicMock:
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    msg = MagicMock()
    msg.content = [text_block]
    msg.stop_reason = "end_turn"
    return msg


def _mock_multi_tool_response() -> MagicMock:
    """Simulate the multi-tool-call risk Codex flagged."""
    tb1 = MagicMock(); tb1.type = "tool_use"; tb1.name = "emit_delete_edit"
    tb1.input = {"target_eid": "badge", "rationale": "first"}
    tb2 = MagicMock(); tb2.type = "tool_use"; tb2.name = "emit_delete_edit"
    tb2.input = {"target_eid": "title", "rationale": "second"}
    msg = MagicMock()
    msg.content = [tb1, tb2]
    msg.stop_reason = "tool_use"
    return msg


def _mock_client(response: MagicMock) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = response
    return client


# --------------------------------------------------------------------------- #
# build_propose_edits_tools                                                   #
# --------------------------------------------------------------------------- #

class TestBuildProposeEditsTools:
    """The tool list registered with Claude. Must include all 7 verbs
    drawn from the doc's actual eid set + the project's CKR for swap."""

    def test_includes_all_seven_verb_tools(self):
        doc = _fixture_doc()
        tools = build_propose_edits_tools(doc, component_paths=["icon/back"])
        names = {t["name"] for t in tools}
        assert names == {
            "emit_set_edit", "emit_delete_edit", "emit_append_edit",
            "emit_insert_edit", "emit_move_edit", "emit_swap_edit",
            "emit_replace_edit",
        }

    def test_set_tool_uses_unique_eids_from_doc(self):
        doc = _fixture_doc()
        tools = build_propose_edits_tools(doc, component_paths=[])
        set_tool = next(t for t in tools if t["name"] == "emit_set_edit")
        eids = set(set_tool["input_schema"]["properties"]["target_eid"]["enum"])
        assert {"screen-1", "frame-1", "title", "badge", "archive"}.issubset(eids)

    def test_swap_tool_uses_supplied_component_paths(self):
        doc = _fixture_doc()
        tools = build_propose_edits_tools(
            doc, component_paths=["icon/back", "icon/close"],
        )
        swap_tool = next(t for t in tools if t["name"] == "emit_swap_edit")
        with_enum = swap_tool["input_schema"]["properties"]["with_component"]["enum"]
        assert set(with_enum) == {"icon/back", "icon/close"}

    def test_swap_tool_omitted_when_no_component_paths(self):
        """If the project has no CKR / no component_paths supplied, the
        swap tool would have an empty enum — which Anthropic rejects.
        The orchestrator must omit swap rather than ship a broken tool."""
        doc = _fixture_doc()
        tools = build_propose_edits_tools(doc, component_paths=[])
        names = {t["name"] for t in tools}
        assert "emit_swap_edit" not in names

    def test_excludes_verb_tools_with_no_candidates(self):
        """insert / move need (parent, anchor) / (target, dest) pairs;
        a single-leaf doc has neither, so those tools must be omitted
        rather than emitted with empty enums (Anthropic rejects
        ``enum: []``)."""
        # `text` is NOT in the container-keyword set, and it carries
        # no block — so collect_parent_candidates returns []. That
        # also kills append/insert/move whose pairs derive from
        # parent-anchor / parent-child relationships.
        leaf_only = parse_l3('text #only-leaf "x"\n')
        tools = build_propose_edits_tools(leaf_only, component_paths=[])
        names = {t["name"] for t in tools}
        # set + replace still work on the leaf.
        assert "emit_set_edit" in names
        # insert / move require multi-node setups.
        assert "emit_insert_edit" not in names
        assert "emit_move_edit" not in names
        # append also gone — no parent-with-block, no container-type
        # node available for appendable parent collection.
        assert "emit_append_edit" not in names


# --------------------------------------------------------------------------- #
# parse_tool_call_to_edit                                                     #
# --------------------------------------------------------------------------- #

class TestParseToolCallToEdit:
    """Lower a tool_use input dict into an edit-grammar source string
    that `parse_l3` + `apply_edits` consume."""

    def test_parses_delete_to_grammar(self):
        src = parse_tool_call_to_edit(
            "emit_delete_edit",
            {"target_eid": "badge", "rationale": "noise"},
            doc=_fixture_doc(),
        )
        assert src == "delete @badge"

    def test_parses_set_to_grammar(self):
        src = parse_tool_call_to_edit(
            "emit_set_edit",
            {
                "target_eid": "title", "property": "variant",
                "value": "disabled", "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        # set @title variant=disabled
        assert src.startswith("set @title")
        assert "variant=disabled" in src

    def test_parses_swap_to_grammar(self):
        src = parse_tool_call_to_edit(
            "emit_swap_edit",
            {
                "target_eid": "badge", "with_component": "icon/close",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        # swap @badge with=-> icon/close
        assert src.startswith("swap @badge")
        assert "icon/close" in src

    def test_parses_append_to_grammar(self):
        src = parse_tool_call_to_edit(
            "emit_append_edit",
            {
                "parent_eid": "frame-1", "child_type": "text",
                "child_eid": "new-leaf", "child_text": "hi",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        # The parser only needs valid edit-grammar syntax. apply_edits
        # then validates eid uniqueness etc. at apply time.
        assert "append" in src and "@frame-1" in src
        assert "#new-leaf" in src

    def test_parses_insert_to_grammar(self):
        # insert requires a (parent, anchor) pair from the doc's
        # collected pairs. Lower from pair_index to the actual eids.
        src = parse_tool_call_to_edit(
            "emit_insert_edit",
            {
                "pair_index": 0, "child_type": "text",
                "child_eid": "between", "child_text": "x",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        assert src.startswith("insert into=@")
        assert "after=@" in src and "#between" in src

    def test_parses_move_to_grammar(self):
        src = parse_tool_call_to_edit(
            "emit_move_edit",
            {"pair_index": 0, "position": "first", "rationale": "test"},
            doc=_fixture_doc(),
        )
        assert src.startswith("move @")
        assert "to=@" in src and "position=first" in src

    def test_parses_replace_to_grammar(self):
        src = parse_tool_call_to_edit(
            "emit_replace_edit",
            {
                "target_eid": "badge",
                "replacement_root_type": "text",
                "replacement_root_eid": "fresh",
                "replacement_root_text": "new",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        assert src.startswith("replace @badge")
        assert "#fresh" in src

    def test_unknown_tool_name_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            parse_tool_call_to_edit(
                "emit_unknown_edit", {}, doc=_fixture_doc(),
            )


# --------------------------------------------------------------------------- #
# propose_edits orchestrator                                                  #
# --------------------------------------------------------------------------- #

class TestProposeEditsOrchestrator:
    """End-to-end: doc + prompt + mock client → ProposeEditsResult.

    The result carries the proposed edit, the tool name, the LLM's
    rationale, and the applied doc (or an error if anything failed).
    """

    def test_happy_path_delete(self):
        doc = _fixture_doc()
        client = _mock_client(_mock_tool_use_response(
            "emit_delete_edit",
            {"target_eid": "badge", "rationale": "decorative noise"},
        ))
        result = propose_edits(
            doc=doc, prompt="delete the decorative badge",
            client=client, component_paths=[],
        )
        assert isinstance(result, ProposeEditsResult)
        assert result.ok is True
        assert result.tool_name == "emit_delete_edit"
        assert result.edit_source.strip() == "delete @badge"
        assert result.rationale == "decorative noise"
        # Applied doc no longer has badge.
        from dd.structural_verbs import existing_eids
        assert "badge" not in existing_eids(result.applied_doc)

    def test_no_tool_call_returns_failure(self):
        doc = _fixture_doc()
        client = _mock_client(_mock_no_tool_response("I'm not sure"))
        result = propose_edits(
            doc=doc, prompt="ambiguous prompt",
            client=client, component_paths=[],
        )
        assert result.ok is False
        assert result.error_kind == "KIND_NO_TOOL_CALL"

    def test_multiple_tool_calls_returns_failure(self):
        """Codex's risk: Claude may emit multiple tool calls in one
        turn. The orchestrator MUST fail loudly rather than picking
        the first silently — silent first-pick would corrupt the
        session log without telling anyone."""
        doc = _fixture_doc()
        client = _mock_client(_mock_multi_tool_response())
        result = propose_edits(
            doc=doc, prompt="do many things",
            client=client, component_paths=[],
        )
        assert result.ok is False
        assert result.error_kind == "KIND_MULTIPLE_TOOL_CALLS"

    def test_invalid_eid_returns_failure(self):
        """If the LLM somehow emits a target_eid that isn't in the
        doc (shouldn't happen — enum constrained — but defense in
        depth), apply_edits will fail. The orchestrator surfaces
        that as a structured error, not an exception."""
        doc = _fixture_doc()
        client = _mock_client(_mock_tool_use_response(
            "emit_delete_edit",
            {"target_eid": "nonexistent-eid", "rationale": "test"},
        ))
        result = propose_edits(
            doc=doc, prompt="delete the missing thing",
            client=client, component_paths=[],
        )
        assert result.ok is False
        assert result.error_kind == "KIND_APPLY_FAILED"

    def test_passes_doc_state_in_user_message(self):
        """Per plan §1.2: the agent receives the current tree state
        as a context. This is the load-bearing change from Stage 0
        ("here's an empty IR, build something") to Stage 1 ("here's
        the current tree, propose an edit")."""
        doc = _fixture_doc()
        client = _mock_client(_mock_tool_use_response(
            "emit_delete_edit",
            {"target_eid": "badge", "rationale": "test"},
        ))
        propose_edits(
            doc=doc, prompt="delete the badge",
            client=client, component_paths=[],
        )
        call = client.messages.create.call_args
        msgs = call.kwargs["messages"]
        # The user message must include the current tree somewhere
        # (markup form is the canonical representation).
        user_text = msgs[0]["content"]
        if isinstance(user_text, list):
            user_text = " ".join(
                b.get("text", "") for b in user_text if isinstance(b, dict)
            )
        assert "@badge" in user_text or "#badge" in user_text or "badge" in user_text

    def test_registers_all_seven_tools_with_client(self):
        doc = _fixture_doc()
        client = _mock_client(_mock_tool_use_response(
            "emit_delete_edit",
            {"target_eid": "badge", "rationale": "test"},
        ))
        propose_edits(
            doc=doc, prompt="delete the badge",
            client=client, component_paths=["icon/close"],
        )
        call = client.messages.create.call_args
        tool_names = {t["name"] for t in call.kwargs["tools"]}
        assert "emit_swap_edit" in tool_names
        # The 4 always-applicable verbs.
        assert {"emit_set_edit", "emit_delete_edit", "emit_append_edit"}.issubset(
            tool_names,
        )

    def test_tool_choice_any(self):
        """Stage 1.2: tool_choice='any' so Claude picks the verb;
        we don't force a specific tool. (Demos use tool_choice='tool'
        but they target one verb at a time; the orchestrator must
        let Claude decide.)"""
        doc = _fixture_doc()
        client = _mock_client(_mock_tool_use_response(
            "emit_delete_edit",
            {"target_eid": "badge", "rationale": "test"},
        ))
        propose_edits(
            doc=doc, prompt="anything",
            client=client, component_paths=[],
        )
        call = client.messages.create.call_args
        tc = call.kwargs.get("tool_choice")
        assert tc is None or tc == {"type": "any"} or tc.get("type") == "any"
