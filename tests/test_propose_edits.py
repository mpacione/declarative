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

    def test_emit_append_frame_with_text_lowers_to_nested_text(self):
        """Codex A-fix: non-text child_types can't accept a bare string
        trailer (grammar §2.7: only `_TEXT_BEARING_TYPES` do). When the
        LLM supplies child_text on a frame, lower it to a nested
        `text #<eid>-label "…"` child so the output parses as valid L3."""
        src = parse_tool_call_to_edit(
            "emit_append_edit",
            {
                "parent_eid": "frame-1", "child_type": "frame",
                "child_eid": "card-1", "child_text": "Sign Out",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        # Grammar-level check: must parse without error.
        parsed = parse_l3(src)
        # Round-trip: apply against the doc and inspect the new subtree.
        applied = apply_edits(_fixture_doc(), list(parsed.edits))
        # Find the new frame and verify it has a nested text child with
        # the supplied content.
        from dd.markup_l3 import emit_l3
        out = emit_l3(applied)
        assert "frame #card-1" in out
        assert "text #card-1-label" in out
        assert '"Sign Out"' in out

    def test_emit_append_frame_without_text_still_bare(self):
        """When no child_text is supplied, a frame remains a bare
        `frame #eid` node — no spurious empty text child injected."""
        src = parse_tool_call_to_edit(
            "emit_append_edit",
            {
                "parent_eid": "frame-1", "child_type": "frame",
                "child_eid": "empty-frame",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        # Must parse; must contain the bare frame; must NOT synthesize
        # a child text node.
        parse_l3(src)
        assert "frame #empty-frame" in src
        assert "text #" not in src

    def test_emit_append_rectangle_silently_drops_text(self):
        """rectangle / ellipse / vector do not render text. If the LLM
        supplies child_text (it shouldn't per the schema description),
        Codex's rule is to silently drop it — no spurious text child,
        no bare-string trailer that would fail the parser."""
        src = parse_tool_call_to_edit(
            "emit_append_edit",
            {
                "parent_eid": "frame-1", "child_type": "rectangle",
                "child_eid": "rect-new",
                "child_text": "ignored content",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        # Parses: no bare-string trailer on rectangle.
        parse_l3(src)
        # Text content doesn't appear at all in the lowered source.
        assert "ignored content" not in src
        # No synthesized child text node either.
        assert "text #" not in src

    def test_emit_append_text_still_uses_bare_string_trailer(self):
        """Regression guard: text (a text-bearing type) MUST still use
        the compact `text #eid \"…\"` form — no unnecessary nesting
        into a synthetic text-child. The single `{ ... }` wrapper is
        the append statement's own block; there should be no *second*
        nested block containing a text child."""
        src = parse_tool_call_to_edit(
            "emit_append_edit",
            {
                "parent_eid": "frame-1", "child_type": "text",
                "child_eid": "leaf-1", "child_text": "hello",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        parse_l3(src)
        assert 'text #leaf-1 "hello"' in src
        # Exactly one `{` / `}` pair — no nested block for a synthesized
        # sub-child.
        assert src.count("{") == 1
        assert src.count("}") == 1

    def test_emit_insert_frame_with_text_lowers_to_nested_text(self):
        """Same A-fix applies to insert: frame with child_text must
        lower through a nested text child, not a bare-string trailer."""
        src = parse_tool_call_to_edit(
            "emit_insert_edit",
            {
                "pair_index": 0, "child_type": "frame",
                "child_eid": "ins-frame", "child_text": "Label",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        parse_l3(src)
        assert "frame #ins-frame" in src
        assert "text #ins-frame-label" in src
        assert '"Label"' in src

    def test_emit_replace_frame_with_text_lowers_to_nested_text(self):
        """Same A-fix applies to replace: replacement_root_type=frame
        with replacement_root_text must lower through a nested text
        child, not a bare-string trailer."""
        src = parse_tool_call_to_edit(
            "emit_replace_edit",
            {
                "target_eid": "badge",
                "replacement_root_type": "frame",
                "replacement_root_eid": "new-frame",
                "replacement_root_text": "New label",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        parse_l3(src)
        assert "frame #new-frame" in src
        assert "text #new-frame-label" in src
        assert '"New label"' in src

    def test_emit_append_long_eid_label_stays_within_grammar_limit(self):
        """The eid grammar cap is 39 chars (^[a-z][a-z0-9-]{1,38}$).
        Naive suffixing would overflow if the base eid is already long.
        Guard: when `<eid>-label` would overflow, truncate then append
        a 4-char sha1 prefix of the base eid so the derived eid remains
        unique AND within the cap."""
        # 35-char base eid; +"-label" (6) = 41 chars, overflows.
        long_eid = "long-frame-eid-that-is-near-the-cap"  # 35 chars
        assert len(long_eid) == 35
        src = parse_tool_call_to_edit(
            "emit_append_edit",
            {
                "parent_eid": "frame-1", "child_type": "frame",
                "child_eid": long_eid, "child_text": "Hi",
                "rationale": "test",
            },
            doc=_fixture_doc(),
        )
        # Must parse: eid length <= 39 chars on every node.
        parse_l3(src)
        # Find the nested text eid in the source and verify its length.
        import re as _re
        m = _re.search(r"text #([a-z][a-z0-9-]+)", src)
        assert m is not None, f"no text child eid found in {src!r}"
        derived = m.group(1)
        assert len(derived) <= 39, (
            f"derived eid {derived!r} overflows 39-char cap"
        )

    def test_parse_tool_call_validates_lowered_l3(self, monkeypatch):
        """Codex C-fix: validation boundary. Any path that produces
        invalid L3 must raise ValueError before returning, so bad
        strings never persist as variant edit_scripts.

        Forced failure via monkeypatch: inject a lowering that returns
        syntactically invalid L3; the function must re-raise as
        ValueError mentioning the tool name."""
        from dd import propose_edits as pe

        # Monkeypatch the handler path: force the delete lowering to
        # return invalid L3. This exercises the final parse_l3 guard.
        original = pe.parse_tool_call_to_edit

        def broken(tool_name, tool_input, *, doc):
            if tool_name == "emit_delete_edit":
                # Skip the real impl; return syntactically invalid L3.
                src = "delete @@@ not-valid-l3"
                from dd.markup_l3 import parse_l3 as _p
                try:
                    _p(src)
                except Exception as e:
                    raise ValueError(
                        f"invalid L3 from {tool_name} lowering: {e}"
                    ) from e
                return src
            return original(tool_name, tool_input, doc=doc)

        monkeypatch.setattr(pe, "parse_tool_call_to_edit", broken)
        with pytest.raises(ValueError, match="invalid L3"):
            pe.parse_tool_call_to_edit(
                "emit_delete_edit", {"target_eid": "x", "rationale": "z"},
                doc=_fixture_doc(),
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
