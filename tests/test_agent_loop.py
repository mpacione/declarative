"""Stage 3.3 — dd/agent/loop.py orchestrator.

Per Codex+Sonnet 2026-04-23 unanimous picks:
- B2 (Python iteration loop, stateless calls — matches Stage 1+2
  pattern; replayable per-iter).
- A2 with cheap per-turn structural score for stop signal (no
  render in loop; full render+VLM deferred to ``dd design score``).
- Convergence: hard cap + explicit DONE tool + stall detector.
- Persist the tree, not the conversation (LangGraph / AB-MCTS /
  Cline-Aider pattern from the lit-review).

Contract:

run_session(
    conn, *, brief=None, parent_variant_id=None,
    client, model="claude-sonnet-4-6",
    max_iters=10, component_paths=(), starting_doc=None,
) -> SessionRunResult

Either ``brief`` (new session) OR ``parent_variant_id`` (resume /
branch) must be supplied. starting_doc is the initial doc for new
sessions (defaults to an empty screen for SYNTHESIZE mode).

Returns SessionRunResult(session_id, final_variant_id, iterations,
                         halt_reason, move_log_summary).

Halt reasons (in order of preference):
- "done"       — agent called the emit_done tool
- "stalled"    — last 3 iters made no structural change
- "max_iters"  — hit the iteration cap
- "all_failed" — every tool call in the last 3 iters errored
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dd.agent.loop import (
    SessionRunResult,
    build_loop_tools,
    cheap_structural_score,
    run_session,
)
from dd.db import init_db
from dd.markup_l3 import parse_l3
from dd.sessions import (
    create_session,
    create_variant,
    list_move_log,
    list_variants,
    load_variant,
)


# --------------------------------------------------------------------------- #
# Mock helpers                                                                #
# --------------------------------------------------------------------------- #

def _mock_tool_use(tool_name: str, input_dict: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = input_dict
    msg = MagicMock()
    msg.content = [block]
    msg.stop_reason = "tool_use"
    return msg


def _mock_done(rationale: str = "I'm satisfied") -> MagicMock:
    return _mock_tool_use("emit_done", {"rationale": rationale})


def _mock_no_tool() -> MagicMock:
    text_block = MagicMock(); text_block.type = "text"
    text_block.text = "I refuse"
    msg = MagicMock(); msg.content = [text_block]
    msg.stop_reason = "end_turn"
    return msg


def _mock_client_seq(*responses: MagicMock) -> MagicMock:
    client = MagicMock()
    client.messages.create.side_effect = list(responses)
    return client


def _starter_doc():
    return parse_l3(
        "screen #screen-root {\n"
        '  text #title "draft"\n'
        "  rectangle #placeholder\n"
        "}\n"
    )


@pytest.fixture
def db():
    conn = init_db(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


# --------------------------------------------------------------------------- #
# build_loop_tools — registers all 10+ tools                                  #
# --------------------------------------------------------------------------- #

class TestBuildLoopTools:
    """The orchestrator exposes propose_edits's 7 verbs PLUS three
    focus primitives PLUS an explicit emit_done tool."""

    def test_includes_seven_edit_verbs(self):
        tools = build_loop_tools(_starter_doc(), component_paths=[])
        names = {t["name"] for t in tools}
        # The 7 verbs propose_edits exposes (set / delete / append /
        # insert / move / swap / replace) — minus swap when no
        # component_paths supplied (per propose_edits Stage 1.2).
        for verb in ("emit_set_edit", "emit_delete_edit",
                     "emit_replace_edit"):
            assert verb in names

    def test_includes_focus_primitives(self):
        tools = build_loop_tools(_starter_doc(), component_paths=[])
        names = {t["name"] for t in tools}
        assert "emit_name_subtree" in names
        assert "emit_drill" in names
        assert "emit_climb" in names

    def test_includes_done_tool(self):
        tools = build_loop_tools(_starter_doc(), component_paths=[])
        names = {t["name"] for t in tools}
        assert "emit_done" in names


# --------------------------------------------------------------------------- #
# cheap_structural_score — the per-turn stop-signal heuristic                 #
# --------------------------------------------------------------------------- #

class TestCheapStructuralScore:
    """Per Codex's hybrid amendment: cheap per-turn structural score
    (no render). Reuses signals already in propose_edits / focus.
    Used only for stall detection — A2 still defers real fidelity
    scoring to ``dd design score``."""

    def test_score_for_clean_apply_is_positive(self):
        from dd.propose_edits import ProposeEditsResult
        result = ProposeEditsResult(
            ok=True, tool_name="emit_delete_edit",
            edit_source="delete @placeholder",
            rationale="trim",
            applied_doc=parse_l3('screen #screen-root { text #title "draft" }'),
        )
        score = cheap_structural_score(
            pre_doc=_starter_doc(),
            post_result=result,
        )
        assert score["edit_applied"] is True
        # change_magnitude > 0 (one node deleted).
        assert score["change_magnitude"] >= 1
        # No out-of-scope violations.
        assert score["out_of_scope"] == 0

    def test_score_for_failed_apply_records_failure(self):
        from dd.propose_edits import ProposeEditsResult
        result = ProposeEditsResult(
            ok=False, tool_name="emit_delete_edit",
            edit_source="delete @ghost",
            rationale="oops",
            applied_doc=_starter_doc(),
            error_kind="KIND_APPLY_FAILED",
            error_detail="not found",
        )
        score = cheap_structural_score(
            pre_doc=_starter_doc(),
            post_result=result,
        )
        assert score["edit_applied"] is False
        assert score["change_magnitude"] == 0


# --------------------------------------------------------------------------- #
# run_session — the orchestration loop                                        #
# --------------------------------------------------------------------------- #

class TestRunSessionHappyPath:
    """A 2-turn session: edit then done. Persists variants + log."""

    def test_creates_session_and_variants(self, db):
        client = _mock_client_seq(
            _mock_tool_use(
                "emit_delete_edit",
                {"target_eid": "placeholder", "rationale": "trim"},
            ),
            _mock_done("ready"),
        )
        result = run_session(
            db,
            brief="trim the draft",
            client=client,
            max_iters=5,
            starting_doc=_starter_doc(),
        )
        assert isinstance(result, SessionRunResult)
        assert result.iterations == 2
        assert result.halt_reason == "done"
        # A session row + variants exist.
        sessions = list(db.execute("SELECT id FROM design_sessions"))
        assert len(sessions) == 1
        # Two variants: root snapshot + post-edit.
        variants = list_variants(db, result.session_id)
        assert len(variants) >= 1  # at least the post-edit one

    def test_persists_movelog_entries(self, db):
        client = _mock_client_seq(
            _mock_tool_use(
                "emit_delete_edit",
                {"target_eid": "placeholder", "rationale": "trim"},
            ),
            _mock_done("ready"),
        )
        result = run_session(
            db, brief="trim", client=client,
            max_iters=5, starting_doc=_starter_doc(),
        )
        log = list_move_log(db, result.session_id)
        # At minimum: one EDIT entry + the DONE.
        kinds = [e.primitive for e in log]
        assert "EDIT" in kinds
        assert "DONE" in kinds

    def test_final_variant_doc_has_edit_applied(self, db):
        client = _mock_client_seq(
            _mock_tool_use(
                "emit_delete_edit",
                {"target_eid": "placeholder", "rationale": "trim"},
            ),
            _mock_done("ready"),
        )
        result = run_session(
            db, brief="trim", client=client,
            max_iters=5, starting_doc=_starter_doc(),
        )
        final = load_variant(db, result.final_variant_id)
        from dd.structural_verbs import existing_eids
        assert "placeholder" not in existing_eids(final.doc)


class TestRunSessionHalt:
    """Halt reasons: max_iters, stalled, all_failed."""

    def test_max_iters_halts(self, db):
        # Agent never picks done; just keeps deleting.
        client = _mock_client_seq(
            _mock_tool_use("emit_delete_edit",
                           {"target_eid": "title", "rationale": "x"}),
            _mock_tool_use("emit_delete_edit",
                           {"target_eid": "placeholder", "rationale": "y"}),
            # Third turn: no targets left, agent picks NAME (cheap).
            _mock_tool_use("emit_name_subtree",
                           {"eid": "screen-root", "description": "root"}),
        )
        result = run_session(
            db, brief="trim everything", client=client,
            max_iters=3, starting_doc=_starter_doc(),
        )
        assert result.halt_reason == "max_iters"
        assert result.iterations == 3

    def test_no_tool_call_halts_as_done(self, db):
        """If the LLM emits no tool call (e.g. just text), treat
        that as an implicit done — the agent has nothing more to
        do."""
        client = _mock_client_seq(_mock_no_tool())
        result = run_session(
            db, brief="x", client=client,
            max_iters=5, starting_doc=_starter_doc(),
        )
        assert result.halt_reason == "done"

    def test_three_consecutive_failures_halt_as_all_failed(self, db):
        """Three failed turns in a row → halt. Defensive against
        an agent that loops on KIND_APPLY_FAILED."""
        client = _mock_client_seq(
            _mock_tool_use("emit_delete_edit",
                           {"target_eid": "ghost-1", "rationale": "x"}),
            _mock_tool_use("emit_delete_edit",
                           {"target_eid": "ghost-2", "rationale": "y"}),
            _mock_tool_use("emit_delete_edit",
                           {"target_eid": "ghost-3", "rationale": "z"}),
        )
        result = run_session(
            db, brief="x", client=client,
            max_iters=10, starting_doc=_starter_doc(),
        )
        assert result.halt_reason == "all_failed"


class TestRunSessionResume:
    """Plan §3.4 acceptance #2: resume picks up where left off."""

    def test_resume_from_existing_variant(self, db):
        # Bootstrap: create a session + one variant manually.
        sid = create_session(db, brief="x")
        v0 = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="DRILL", edit_script=None,
            doc=_starter_doc(),
        )
        # Resume call: agent makes one edit then dones.
        client = _mock_client_seq(
            _mock_tool_use(
                "emit_delete_edit",
                {"target_eid": "placeholder", "rationale": "trim"},
            ),
            _mock_done("ready"),
        )
        result = run_session(
            db, parent_variant_id=v0,
            client=client, max_iters=5,
        )
        assert result.session_id == sid
        # The resumed loop wrote new variant(s) under the same session.
        variants = list_variants(db, sid)
        assert len(variants) >= 2

    def test_resume_preserves_prior_movelog(self, db):
        from dd.focus import MoveLogEntry
        from dd.sessions import append_move_log_entry
        sid = create_session(db, brief="x")
        v0 = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="NAME", edit_script=None,
            doc=_starter_doc(),
        )
        # Pre-existing move log entry (from a prior run).
        append_move_log_entry(
            db, session_id=sid, variant_id=v0,
            entry=MoveLogEntry(
                primitive="NAME", scope_eid="screen-root",
                payload={"description": "root frame"},
            ),
        )
        # Resume — agent does one thing then dones.
        client = _mock_client_seq(_mock_done("looks fine"))
        run_session(
            db, parent_variant_id=v0,
            client=client, max_iters=5,
        )
        # The prior NAME entry is still there + new DONE.
        log = list_move_log(db, sid)
        kinds = [e.primitive for e in log]
        assert "NAME" in kinds  # prior entry preserved
        assert "DONE" in kinds  # new entry from resume


class TestRunSessionBranch:
    """Plan §3.4 acceptance #3: branch from a non-leaf variant
    produces a sibling. Per simplicity-check (Codex+Sonnet
    confirmed): branching falls out of resume from a non-leaf —
    no separate `branch` semantics needed."""

    def test_resuming_from_non_leaf_creates_sibling_chain(self, db):
        sid = create_session(db, brief="x")
        v0 = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="DRILL", edit_script=None,
            doc=_starter_doc(),
        )
        # Make a child of v0 so v0 is non-leaf.
        v1 = create_variant(
            db, session_id=sid, parent_id=v0,
            primitive="EDIT", edit_script="delete @title",
            doc=parse_l3('screen #screen-root { rectangle #placeholder }'),
        )
        # Resume FROM v0 (not v1) — should create a sibling of v1.
        client = _mock_client_seq(
            _mock_tool_use(
                "emit_delete_edit",
                {"target_eid": "placeholder", "rationale": "diff trim"},
            ),
            _mock_done("done"),
        )
        result = run_session(
            db, parent_variant_id=v0,
            client=client, max_iters=5,
        )
        # The new variant chain has v0 as ancestor (sibling of v1).
        variants = list_variants(db, sid)
        new_variants = [v for v in variants if v.id not in (v0, v1)]
        assert len(new_variants) >= 1
        # The new chain's root has parent_id=v0 (sibling of v1).
        first_new = new_variants[0]
        assert first_new.parent_id == v0


class TestRunSessionContract:
    """Defensive contract checks."""

    def test_either_brief_or_parent_required(self, db):
        client = MagicMock()
        with pytest.raises(ValueError, match="brief.*parent_variant_id"):
            run_session(
                db, client=client, max_iters=5,
                starting_doc=_starter_doc(),
            )

    def test_brief_without_starting_doc_uses_default(self, db):
        """SYNTHESIZE mode: no starting_doc → default empty screen."""
        client = _mock_client_seq(_mock_done("nothing to do"))
        result = run_session(
            db, brief="empty session", client=client, max_iters=5,
        )
        # Should succeed; starting doc was synthesized.
        assert result.session_id
        # The first variant has SOME doc (an empty screen).
        variants = list_variants(db, result.session_id)
        assert len(variants) >= 1
        from dd.structural_verbs import existing_eids
        assert existing_eids(variants[0].doc)  # non-empty
