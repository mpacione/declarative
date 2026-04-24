"""Stage 2.2 — NAME primitive + JSONL move-log writer.

Per docs/plan-authoring-loop.md §2.1: ``name_subtree(eid, description)``
announces "this subtree is a product-showcase-section" for the
agent's own rationale tracking. Does NOT create a new type — the
node still has type=frame — the name is promoted from ad-hoc eid
to semantic marker. Stored in move_log as a NAME entry.

Per Codex 2026-04-23 fork: option B — NAME is a deterministic
orchestrator entry point, not an LLM-callable tool. Pure function
of (focus, eid, description) → updated focus.

JSONL writer is the persistence stopgap for Stage 2 (Stage 3 owns
the SQL ``move_log`` table via migration 023). Per the audit, no
table exists today; the JSONL shape round-trips into the future
SQL schema row-for-row.
"""

from __future__ import annotations

import json

import pytest

from dd.agent.primitives import name_subtree, write_move_log_jsonl
from dd.focus import FocusContext, MoveLogEntry
from dd.markup_l3 import parse_l3


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

def _three_section_doc():
    return parse_l3(
        "screen #screen-root {\n"
        "  header #top-bar {\n"
        "    text #title \"Title\"\n"
        "  }\n"
        "  frame #features-section {\n"
        "    heading #features-heading \"Features\"\n"
        "    card #feature-card-1\n"
        "  }\n"
        "}\n"
    )


# --------------------------------------------------------------------------- #
# name_subtree                                                                #
# --------------------------------------------------------------------------- #

class TestNameSubtree:
    """The NAME primitive: tag a subtree with a semantic description.
    Pure metadata — does not change the doc, only the move log."""

    def test_returns_focus_with_appended_name_entry(self):
        focus = FocusContext.root(_three_section_doc())
        new_focus = name_subtree(
            focus, "features-section", "product showcase section",
        )
        assert len(new_focus.move_log) == 1
        entry = new_focus.move_log[0]
        assert entry.primitive == "NAME"
        assert entry.scope_eid == "features-section"
        assert entry.payload["description"] == "product showcase section"

    def test_does_not_mutate_input_focus(self):
        focus = FocusContext.root(_three_section_doc())
        name_subtree(focus, "features-section", "product showcase section")
        assert focus.move_log == []  # input untouched

    def test_does_not_change_doc_or_scope(self):
        focus = FocusContext.root(_three_section_doc()).drilled_to("features-section")
        new_focus = name_subtree(
            focus, "feature-card-1", "the first feature card",
        )
        assert new_focus.scope_eid == "features-section"
        assert new_focus.parent_chain == focus.parent_chain
        assert new_focus.root_doc is focus.root_doc

    def test_rejects_eid_not_in_root_doc(self):
        """Naming a node that isn't in the root doc is a no-op-with-
        warning. Silent acceptance would let the LLM accumulate names
        on nodes that don't exist; loud rejection forces a real eid."""
        focus = FocusContext.root(_three_section_doc())
        with pytest.raises(ValueError, match="ghost-eid"):
            name_subtree(focus, "ghost-eid", "phantom")

    def test_naming_works_outside_current_scope(self):
        """NAME is metadata; it should work on any eid in the root
        doc, regardless of current focus scope. The agent might want
        to label sibling subtrees while drilled into another."""
        focus = FocusContext.root(_three_section_doc()).drilled_to("features-section")
        new_focus = name_subtree(focus, "top-bar", "the top navigation")
        # Even though top-bar is OUT of scope, the NAME entry was
        # recorded — it's pure metadata.
        assert len(new_focus.move_log) == 1
        assert new_focus.move_log[0].scope_eid == "top-bar"

    def test_multiple_names_accumulate_in_log(self):
        focus = FocusContext.root(_three_section_doc())
        f1 = name_subtree(focus, "features-section", "showcase")
        f2 = name_subtree(f1, "top-bar", "nav")
        assert len(f2.move_log) == 2
        assert f2.move_log[0].payload["description"] == "showcase"
        assert f2.move_log[1].payload["description"] == "nav"


# --------------------------------------------------------------------------- #
# write_move_log_jsonl                                                        #
# --------------------------------------------------------------------------- #

class TestMoveLogJsonl:
    """JSONL persistence stopgap. Stage 3's SQL schema (migration
    023) consumes the same shape via ``MoveLogEntry.to_dict``, so a
    Stage 2 .jsonl file is a forward-compatible artifact."""

    def test_writes_one_line_per_entry(self, tmp_path):
        focus = FocusContext.root(_three_section_doc())
        focus = name_subtree(focus, "features-section", "showcase")
        focus = name_subtree(focus, "top-bar", "nav")
        out = tmp_path / "moves.jsonl"
        write_move_log_jsonl(focus, out)
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_each_line_is_parseable_json(self, tmp_path):
        focus = FocusContext.root(_three_section_doc())
        focus = name_subtree(focus, "features-section", "showcase")
        out = tmp_path / "moves.jsonl"
        write_move_log_jsonl(focus, out)
        line = out.read_text().strip()
        parsed = json.loads(line)
        assert parsed["primitive"] == "NAME"
        assert parsed["scope_eid"] == "features-section"
        assert parsed["payload"]["description"] == "showcase"
        assert "ts" in parsed

    def test_empty_log_produces_empty_file(self, tmp_path):
        focus = FocusContext.root(_three_section_doc())
        out = tmp_path / "moves.jsonl"
        write_move_log_jsonl(focus, out)
        assert out.read_text() == ""

    def test_jsonl_round_trips_to_movelogentry(self, tmp_path):
        """Codex's risk: design with Stage 3 in mind. A read-back
        helper proves the JSONL shape is the same shape Stage 3's
        SQL row would carry — promoting from JSONL to SQL is a
        bulk-import, not a re-serialization."""
        focus = FocusContext.root(_three_section_doc())
        focus = name_subtree(focus, "features-section", "showcase")
        out = tmp_path / "moves.jsonl"
        write_move_log_jsonl(focus, out)
        # Read back the only row, reconstruct an entry, compare to the
        # in-memory entry's to_dict output.
        line = json.loads(out.read_text().strip())
        original = focus.move_log[0]
        assert line == original.to_dict()


# --------------------------------------------------------------------------- #
# DRILL primitive (Stage 2.3)                                                 #
# --------------------------------------------------------------------------- #

from unittest.mock import MagicMock  # noqa: E402

from dd.agent.primitives import (  # noqa: E402
    climb,
    drill,
    drilled_propose_edits,
)


def _mock_tool_use(tool_name: str, input_dict: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = input_dict
    msg = MagicMock()
    msg.content = [block]
    msg.stop_reason = "tool_use"
    return msg


def _mock_client(response: MagicMock) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = response
    return client


class TestDrill:
    """The DRILL primitive — narrow focus into a subtree.

    Pure function over FocusContext; doesn't itself call propose_edits.
    The caller follows up with `drilled_propose_edits` (or directly
    with `propose_edits(focus.doc, ...)`) to act inside the new scope.
    """

    def test_drill_narrows_scope(self):
        focus = FocusContext.root(_three_section_doc())
        drilled = drill(focus, "features-section", focus_goal="tighten layout")
        assert drilled.scope_eid == "features-section"
        # The .doc view is the subtree.
        from dd.structural_verbs import existing_eids
        sub_eids = existing_eids(drilled.doc)
        assert "features-section" in sub_eids
        assert "screen-root" not in sub_eids

    def test_drill_emits_drill_log_entry(self):
        focus = FocusContext.root(_three_section_doc())
        drilled = drill(focus, "features-section", focus_goal="tighten layout")
        assert len(drilled.move_log) == 1
        entry = drilled.move_log[0]
        assert entry.primitive == "DRILL"
        assert entry.scope_eid == "features-section"
        assert entry.payload["focus_goal"] == "tighten layout"

    def test_drill_with_no_focus_goal(self):
        """focus_goal is optional — DRILL still records a payload."""
        focus = FocusContext.root(_three_section_doc())
        drilled = drill(focus, "features-section")
        assert drilled.move_log[0].primitive == "DRILL"
        # focus_goal absent means an empty payload (or None).
        assert drilled.move_log[0].payload.get("focus_goal") in (None, "")

    def test_drill_into_unknown_eid_raises(self):
        focus = FocusContext.root(_three_section_doc())
        with pytest.raises(ValueError, match="ghost"):
            drill(focus, "ghost-eid", focus_goal="x")

    def test_drill_doesnt_mutate_input_focus(self):
        focus = FocusContext.root(_three_section_doc())
        drill(focus, "features-section", focus_goal="x")
        assert focus.scope_eid is None
        assert focus.move_log == []


class TestDrilledProposeEdits:
    """The convenience wrapper that runs propose_edits inside a DRILL
    scope. Per the 2a mechanic chosen 2026-04-23: the LLM sees the
    SUB-doc, but the edit applies against the ROOT doc (so the
    change persists). Same edit-grammar source applies to both;
    eids are stable across the doc."""

    def test_lifts_edit_into_root_doc(self):
        focus = FocusContext.root(_three_section_doc())
        # Mock the LLM picking delete @feature-card-1 (only valid
        # inside the features-section scope; not at root).
        client = _mock_client(_mock_tool_use(
            "emit_delete_edit",
            {"target_eid": "feature-card-1", "rationale": "trim noise"},
        ))
        result = drilled_propose_edits(
            focus=focus,
            drill_eid="features-section",
            focus_goal="trim",
            prompt="delete the first feature card",
            client=client,
            component_paths=[],
        )
        # The orchestrator returned a focus + a propose_edits result.
        new_focus, propose_result = result
        assert propose_result.ok is True
        assert propose_result.tool_name == "emit_delete_edit"
        # The applied doc is the ROOT doc with the edit applied.
        from dd.structural_verbs import existing_eids
        root_eids = existing_eids(new_focus.root_doc)
        assert "feature-card-1" not in root_eids
        # screen-root and other sections are still present.
        assert "screen-root" in root_eids
        assert "top-bar" in root_eids
        assert "features-section" in root_eids

    def test_focus_remains_in_drill_scope_after_edit(self):
        """The agent stays drilled after an edit applies — only CLIMB
        pops scope. Per plan §2.3."""
        focus = FocusContext.root(_three_section_doc())
        client = _mock_client(_mock_tool_use(
            "emit_delete_edit",
            {"target_eid": "feature-card-1", "rationale": "trim"},
        ))
        new_focus, _ = drilled_propose_edits(
            focus=focus,
            drill_eid="features-section",
            focus_goal="trim",
            prompt="delete the first feature card",
            client=client,
            component_paths=[],
        )
        assert new_focus.scope_eid == "features-section"

    def test_emits_drill_then_edit_log_entries(self):
        focus = FocusContext.root(_three_section_doc())
        client = _mock_client(_mock_tool_use(
            "emit_delete_edit",
            {"target_eid": "feature-card-1", "rationale": "trim"},
        ))
        new_focus, _ = drilled_propose_edits(
            focus=focus,
            drill_eid="features-section",
            focus_goal="trim",
            prompt="delete it",
            client=client,
            component_paths=[],
        )
        kinds = [e.primitive for e in new_focus.move_log]
        assert kinds == ["DRILL", "EDIT"]
        edit_entry = new_focus.move_log[1]
        assert edit_entry.scope_eid == "features-section"
        assert edit_entry.payload["edit_source"].startswith("delete @")
        assert edit_entry.rationale == "trim"

    def test_drilled_then_climbed_can_edit_at_parent_scope(self):
        """The plan's load-bearing CLIMB acceptance: after DRILL +
        scoped edit, climb back to root and propose another edit
        at the parent level. Proves the focus stack actually pops."""
        focus = FocusContext.root(_three_section_doc())
        # First: drill + edit (delete a card).
        drill_client = _mock_client(_mock_tool_use(
            "emit_delete_edit",
            {"target_eid": "feature-card-1", "rationale": "trim"},
        ))
        f1, _ = drilled_propose_edits(
            focus=focus,
            drill_eid="features-section",
            focus_goal="trim",
            prompt="delete the first feature card",
            client=drill_client,
            component_paths=[],
        )
        # Climb back out.
        f2 = climb(f1)
        assert f2.scope_eid is None
        # Now propose at root scope: delete the top-bar (sibling of
        # the section we just edited inside). Done via raw
        # propose_edits since we're not drilling.
        from dd.propose_edits import propose_edits
        root_client = _mock_client(_mock_tool_use(
            "emit_delete_edit",
            {"target_eid": "top-bar", "rationale": "drop the nav"},
        ))
        result = propose_edits(
            doc=f2.doc,
            prompt="delete the top bar",
            client=root_client,
            component_paths=[],
        )
        assert result.ok is True
        from dd.structural_verbs import existing_eids
        # top-bar gone, AND the prior drill-edit (feature-card-1
        # removal) is still in effect.
        post = existing_eids(result.applied_doc)
        assert "top-bar" not in post
        assert "feature-card-1" not in post  # prior drill-edit held
        assert "features-section" in post  # ancestor preserved

    def test_edit_targeting_out_of_scope_eid_fails_at_inner_apply(self):
        """The LLM emits an edit naming a node outside the drill scope.

        Defense in depth — there are TWO layers that catch this:
        1. propose_edits's tool enum is built from the SUB-doc's
           eids, so the LLM can't even name out-of-scope eids in
           the happy path. Mock-bypass tests hit the inner apply
           which raises KIND_APPLY_FAILED.
        2. drilled_propose_edits has its own is_in_scope check
           (covered by the next test) for callers that bypass the
           sub-doc construction.

        Either way: the root doc stays UNCHANGED on a violation.
        """
        focus = FocusContext.root(_three_section_doc())
        client = _mock_client(_mock_tool_use(
            "emit_delete_edit",
            {"target_eid": "top-bar", "rationale": "remove the nav"},
        ))
        new_focus, propose_result = drilled_propose_edits(
            focus=focus,
            drill_eid="features-section",
            focus_goal="trim",
            prompt="delete top-bar",
            client=client,
            component_paths=[],
        )
        # The edit was rejected, NOT applied.
        assert propose_result.ok is False
        assert propose_result.error_kind in (
            "KIND_APPLY_FAILED", "KIND_OUT_OF_SCOPE",
        )
        # Root doc unchanged: top-bar is still there.
        from dd.structural_verbs import existing_eids
        assert "top-bar" in existing_eids(new_focus.root_doc)


# --------------------------------------------------------------------------- #
# CLIMB primitive (Stage 2.4)                                                 #
# --------------------------------------------------------------------------- #

class TestClimb:
    """The CLIMB primitive — pop one level of drill scope.

    Per plan §2.3: "After drilling, the agent checks 'did my local
    subtree change break a parent constraint?'" — that introspection
    is the agent's job. The CLIMB primitive itself just narrows the
    focus by one level and emits a CLIMB log entry. Whether the
    agent then re-runs propose_edits at the parent scope is the
    next caller decision (see TestDrilledProposeEdits.
    test_drilled_then_climbed_can_edit_at_parent_scope above for
    the integration shape).
    """

    def test_climb_pops_one_drill_level(self):
        focus = FocusContext.root(_three_section_doc())
        f1 = drill(focus, "features-section", focus_goal="x")
        f2 = climb(f1)
        assert f2.scope_eid is None  # back to root
        assert f2.parent_chain == []

    def test_climb_emits_climb_log_entry(self):
        focus = FocusContext.root(_three_section_doc())
        f1 = drill(focus, "features-section", focus_goal="x")
        f2 = climb(f1)
        kinds = [e.primitive for e in f2.move_log]
        assert kinds == ["DRILL", "CLIMB"]
        climb_entry = f2.move_log[1]
        # The CLIMB entry records WHICH scope we left.
        assert climb_entry.payload["from_scope"] == "features-section"

    def test_climb_at_root_is_noop_no_log_entry(self):
        """Climbing at root is defensive (per plan §2.3). It should
        be a no-op AND should NOT pollute the log with a spurious
        CLIMB entry — otherwise replay would re-DRILL into nothing."""
        focus = FocusContext.root(_three_section_doc())
        climbed = climb(focus)
        assert climbed.scope_eid is None
        assert climbed.move_log == []

    def test_double_drill_double_climb_returns_to_root(self):
        focus = FocusContext.root(_three_section_doc())
        f1 = drill(focus, "features-section", focus_goal="x")
        f2 = drill(f1, "feature-card-1", focus_goal="y")
        c1 = climb(f2)
        c2 = climb(c1)
        assert c2.scope_eid is None
        assert c2.parent_chain == []
        kinds = [e.primitive for e in c2.move_log]
        assert kinds == ["DRILL", "DRILL", "CLIMB", "CLIMB"]

    def test_climb_doesnt_mutate_input_focus(self):
        focus = FocusContext.root(_three_section_doc())
        f1 = drill(focus, "features-section", focus_goal="x")
        climb(f1)
        # f1 is still drilled (input untouched).
        assert f1.scope_eid == "features-section"
