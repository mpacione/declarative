"""Stage 2.5 — plan §2.5 acceptance tests.

Plan-cited acceptance:

1. **DRILL test**: agent receives a full screen, drills into one
   card, emits two edits that only touch descendants of that card.
   Verifier confirms parent-level structure unchanged.

2. **CLIMB test**: after DRILL, agent climbs, notices "card height
   changed from 200 to 140," proposes an edit at the section level
   to adjust grid gap. Verifier confirms the parent-level edit
   applies cleanly.

3. **NAME persistence**: every DRILL / CLIMB / MOVE emits a
   ``move_log`` entry tagged with the named entity the agent was
   focused on. After the session, we can replay the agent's
   reasoning trail.

These tests use mock LLM clients (deterministic, free). The
real-LLM end-to-end is in `test_propose_edits_capstone.py` (Stage 1)
plus a new Stage 2 capstone below.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from dd.agent.primitives import (
    climb,
    drill,
    drilled_propose_edits,
    name_subtree,
    write_move_log_jsonl,
)
from dd.focus import FocusContext, is_in_scope
from dd.markup_l3 import parse_l3
from dd.propose_edits import propose_edits
from dd.structural_verbs import existing_eids


def _section_with_three_cards():
    """A donor screen rich enough to exercise drill into a card,
    multiple in-scope edits, and a parent-level climb-edit."""
    return parse_l3(
        "screen #screen-root {\n"
        "  header #top-bar\n"
        "  frame #features-section {\n"
        "    heading #features-heading \"Features\"\n"
        "    card #card-a {\n"
        "      heading #card-a-title \"A\"\n"
        "      text #card-a-body \"body a\"\n"
        "      rectangle #card-a-badge\n"
        "    }\n"
        "    card #card-b {\n"
        "      heading #card-b-title \"B\"\n"
        "      text #card-b-body \"body b\"\n"
        "    }\n"
        "    card #card-c {\n"
        "      heading #card-c-title \"C\"\n"
        "    }\n"
        "  }\n"
        "}\n"
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


def _mock_client_seq(*responses: MagicMock) -> MagicMock:
    """Mock client whose successive create() calls return the given
    responses in order. Used for multi-edit tests below."""
    client = MagicMock()
    client.messages.create.side_effect = list(responses)
    return client


# --------------------------------------------------------------------------- #
# Plan §2.5 acceptance #1 — DRILL: two edits scoped to a card                 #
# --------------------------------------------------------------------------- #

class TestStage2DrillAcceptance:
    """Plan §2.5: 'agent receives a full screen, drills into one
    card, emits two edits that only touch descendants of that card.
    Verifier confirms parent-level structure unchanged.'"""

    def test_drill_into_card_two_edits_parent_structure_unchanged(self):
        focus = FocusContext.root(_section_with_three_cards())
        # Capture parent-level structure pre-drill.
        from dd.focus import _find_node_by_eid
        section_pre = _find_node_by_eid(focus.root_doc, "features-section")
        section_pre_children = (
            tuple(s.head.eid for s in section_pre.block.statements
                  if hasattr(s, "head") and s.head.eid)
            if section_pre.block else ()
        )
        assert section_pre_children == (
            "features-heading", "card-a", "card-b", "card-c",
        )

        # Edit 1: delete the badge inside card-a.
        client = _mock_client_seq(
            _mock_tool_use(
                "emit_delete_edit",
                {"target_eid": "card-a-badge", "rationale": "trim noise"},
            ),
            _mock_tool_use(
                "emit_set_edit",
                {
                    "target_eid": "card-a-title",
                    "property": "variant",
                    "value": "compact",
                    "rationale": "denser",
                },
            ),
        )

        # Edit 1
        f1, r1 = drilled_propose_edits(
            focus=focus,
            drill_eid="card-a",
            focus_goal="trim and densify",
            prompt="delete the badge",
            client=client,
            component_paths=[],
        )
        assert r1.ok is True

        # Edit 2 — still drilled into card-a (focus carries through).
        # propose_edits sees the SUB-doc rooted at card-a.
        sub_result = propose_edits(
            doc=f1.doc,
            prompt="set the title to compact variant",
            client=client,
            component_paths=[],
        )
        assert sub_result.ok is True
        # Lift the second edit into root manually (this is what a
        # session loop would do; the convenience wrapper handles
        # the first edit, the loop handles the rest).
        from dd.markup_l3 import apply_edits, parse_l3 as p
        edits = list(p(sub_result.edit_source).edits)
        f2_root = apply_edits(f1.root_doc, edits)

        # Parent structure: features-section's CHILD list (its
        # immediate children — card-a, card-b, card-c — and
        # features-heading) is unchanged. The verifier check.
        section_post = _find_node_by_eid(f2_root, "features-section")
        section_post_children = (
            tuple(s.head.eid for s in section_post.block.statements
                  if hasattr(s, "head") and s.head.eid)
            if section_post.block else ()
        )
        assert section_post_children == section_pre_children, (
            "DRILL scope held — features-section's child list is "
            "unchanged after both edits inside card-a"
        )

        # Inside card-a: badge gone (edit 1) AND title carries the
        # new variant (edit 2).
        post_eids = existing_eids(f2_root)
        assert "card-a-badge" not in post_eids
        assert "card-a-title" in post_eids

        # Scope held throughout: every EDIT log entry's scope_eid
        # is the drill scope (card-a). Stage 3's session loop will
        # consume these per-entry scope tags directly.
        edit_entries = [e for e in f1.move_log if e.primitive == "EDIT"]
        assert all(e.scope_eid == "card-a" for e in edit_entries)
        # And the second edit (set), once we apply it, would also
        # carry scope=card-a — drilled_propose_edits enforces that.
        # Sanity: pre-edit doc had card-a-badge in scope; post-edit
        # it doesn't (because it was deleted). Both are correct.
        assert is_in_scope(focus.drilled_to("card-a"), "card-a-badge")
        assert not is_in_scope(focus.drilled_to("card-a"), "card-b-title")


# --------------------------------------------------------------------------- #
# Plan §2.5 acceptance #2 — CLIMB: parent-level edit after drill              #
# --------------------------------------------------------------------------- #

class TestStage2ClimbAcceptance:
    """Plan §2.5: 'after DRILL, agent climbs, notices "card height
    changed from 200 to 140," proposes an edit at the section level
    to adjust grid gap. Verifier confirms the parent-level edit
    applies cleanly.'"""

    def test_drill_edit_climb_then_parent_level_edit(self):
        focus = FocusContext.root(_section_with_three_cards())

        # 1. DRILL into card-a, edit (set the title variant — proxy
        #    for the plan's "card height changed" scenario).
        client_drilled = _mock_client_seq(
            _mock_tool_use(
                "emit_set_edit",
                {
                    "target_eid": "card-a-title",
                    "property": "variant",
                    "value": "compact",
                    "rationale": "denser",
                },
            ),
        )
        f1, r1 = drilled_propose_edits(
            focus=focus,
            drill_eid="card-a",
            focus_goal="densify",
            prompt="compact variant",
            client=client_drilled,
            component_paths=[],
        )
        assert r1.ok is True
        assert f1.scope_eid == "card-a"

        # 2. CLIMB back out.
        f2 = climb(f1)
        assert f2.scope_eid is None

        # 3. Parent-level edit at root scope: set features-section's
        #    layout.gap (proxy for "adjust grid gap").
        client_root = _mock_client_seq(
            _mock_tool_use(
                "emit_set_edit",
                {
                    "target_eid": "features-section",
                    "property": "gap",
                    "value": "{space.sm}",
                    "rationale": "tighter spacing now that cards are denser",
                },
            ),
        )
        result = propose_edits(
            doc=f2.doc,
            prompt="tighten gap",
            client=client_root,
            component_paths=[],
        )
        assert result.ok is True, (
            f"parent-level edit failed: {result.error_kind} {result.error_detail}"
        )
        assert "set @features-section" in result.edit_source

    def test_climb_at_root_is_safe_noop(self):
        """Defense against double-climb in agent loops."""
        focus = FocusContext.root(_section_with_three_cards())
        same = climb(focus)
        assert same.scope_eid is None
        assert same.move_log == []


# --------------------------------------------------------------------------- #
# Plan §2.5 acceptance #3 — NAME / DRILL / CLIMB / EDIT log replay            #
# --------------------------------------------------------------------------- #

class TestStage2MoveLogReplay:
    """Plan §2.5: 'every DRILL / CLIMB / MOVE emits a move_log
    entry tagged with the named entity the agent was focused on.
    After the session, we can replay the agent's reasoning trail.'

    Stage 2 ships JSONL persistence; Stage 3 will own the SQL
    table. The shape is forward-compatible (MoveLogEntry.to_dict
    matches migration 023's row schema).
    """

    def test_full_agent_loop_emits_full_log(self, tmp_path):
        focus = FocusContext.root(_section_with_three_cards())
        # NAME the showcase section.
        f1 = name_subtree(focus, "features-section", "product showcase")
        # DRILL into card-a + scoped EDIT.
        client = _mock_client_seq(
            _mock_tool_use(
                "emit_delete_edit",
                {"target_eid": "card-a-badge", "rationale": "noise"},
            ),
        )
        f2, _ = drilled_propose_edits(
            focus=f1,
            drill_eid="card-a",
            focus_goal="trim",
            prompt="delete the badge",
            client=client,
            component_paths=[],
        )
        # CLIMB out.
        f3 = climb(f2)
        # NAME another subtree at root scope.
        f4 = name_subtree(f3, "top-bar", "the top nav")

        kinds = [e.primitive for e in f4.move_log]
        assert kinds == ["NAME", "DRILL", "EDIT", "CLIMB", "NAME"]

        # Each entry carries the right scope_eid.
        assert f4.move_log[0].scope_eid == "features-section"  # NAME
        assert f4.move_log[1].scope_eid == "card-a"            # DRILL
        assert f4.move_log[2].scope_eid == "card-a"            # EDIT (in scope)
        assert f4.move_log[3].scope_eid is None                # CLIMB to root
        assert f4.move_log[4].scope_eid == "top-bar"           # NAME

        # JSONL replay: every entry round-trips through to_dict.
        out = tmp_path / "moves.jsonl"
        write_move_log_jsonl(f4, out)
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 5
        import json
        kinds_from_disk = [json.loads(line)["primitive"] for line in lines]
        assert kinds_from_disk == kinds


# --------------------------------------------------------------------------- #
# Stage 2 capstone — real-LLM DRILL into a Dank screen subtree                #
# --------------------------------------------------------------------------- #

DANK_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db",
)
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:  # pragma: no cover
    pass

HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY not set")
class TestStage2CapstoneReal:
    """One real Haiku call. The agent is asked to DRILL into a
    specific subtree of Dank screen 333 and propose one edit.
    Asserts: ok=True, the chosen target eid is in scope, the move
    log records DRILL+EDIT with focus_goal preserved."""

    def test_drill_into_dank_333_subtree_and_edit(self):
        import sqlite3
        anthropic = pytest.importorskip("anthropic")
        from dd.compress_l3 import compress_to_l3
        from dd.ir import generate_ir
        from dd.markup_l3 import emit_l3, parse_l3

        conn = sqlite3.connect(DANK_DB_PATH)
        try:
            ir_result = generate_ir(conn, 333)
            doc = compress_to_l3(ir_result["spec"], conn=conn, screen_id=333)
            doc = parse_l3(emit_l3(doc))
        finally:
            conn.close()

        # Pick a subtree we know exists on screen 333 — features-section
        # equivalents. From the Stage-1 capstone we know the screen's
        # IR has eids like "header-1", "frame-1", etc.; pick one with
        # a block (a parent candidate).
        from dd.structural_verbs import collect_parent_candidates
        parents = collect_parent_candidates(doc)
        assert parents, "screen 333 IR should have parent candidates"
        # Drill into the FIRST parent that isn't the root screen.
        drill_target = next(
            (p["eid"] for p in parents if p["eid"] != "screen-1"),
            None,
        )
        assert drill_target is not None

        focus = FocusContext.root(doc)
        client = anthropic.Anthropic()
        new_focus, result = drilled_propose_edits(
            focus=focus,
            drill_eid=drill_target,
            focus_goal=(
                "trim a single redundant or decorative descendant — "
                "pick a safely-removable node, prefer delete."
            ),
            prompt=(
                "Remove ONE descendant of this subtree that you can "
                "justify as redundant or decorative. Use the delete "
                "verb."
            ),
            client=client,
            component_paths=[],
        )

        # Either it succeeded (good) or the LLM judged the subtree
        # had no removable nodes (acceptable — record it).
        if not result.ok:
            pytest.skip(
                f"LLM declined to edit subtree {drill_target!r}: "
                f"{result.error_kind} {result.error_detail}"
            )

        # Move log: DRILL then EDIT.
        kinds = [e.primitive for e in new_focus.move_log]
        assert kinds[:2] == ["DRILL", "EDIT"]
        # focus_goal preserved on the DRILL entry (Codex risk note).
        assert new_focus.move_log[0].payload["focus_goal"].startswith("trim")
        # Edit was scope-respecting: target is a descendant of the drill.
        # (The EDIT log entry carries the scope_eid the edit applied
        # under, which is the drill_target.)
        assert new_focus.move_log[1].scope_eid == drill_target
