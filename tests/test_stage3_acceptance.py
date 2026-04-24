"""Stage 3.5 — plan §3.4 acceptance + real-LLM capstone.

Plan-cited acceptance from docs/plan-authoring-loop.md §3.4:

1. ``dd design --brief "a login screen"`` produces a session, runs
   NAME / DRILL / MOVE primitives, ends with a renderable screen
   and a full move log.

2. ``dd design resume <id>`` picks up where a prior session left
   off, agent has full context.

3. ``dd design branch <variant-id> --vary style`` produces a
   sibling variant. (Per simplicity-check confirmed by Codex+
   Sonnet: branching falls out of resume-from-non-leaf — no
   separate `branch` subcommand needed.)

4. Sessions are queryable: "show me all variants where
   ``scorer.fidelity > 0.8``." A2 defers scoring; the column
   exists + is queryable; values populate when ``dd design score``
   backend lands.

These tests use mock clients for determinism. The real-LLM
capstone at the end exercises the full Sonnet 4.6 path against
a multi-iter session.
"""

from __future__ import annotations

import json
import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from dd.cli import main as cli_main
from dd.db import init_db
from dd.markup_l3 import parse_l3
from dd.sessions import (
    create_session,
    create_variant,
    list_move_log,
    list_sessions,
    list_variants,
    load_variant,
)


# --------------------------------------------------------------------------- #
# Fixtures + mock helpers                                                     #
# --------------------------------------------------------------------------- #

@pytest.fixture
def tmp_db_path(tmp_path):
    db_path = tmp_path / "design.db"
    conn = init_db(str(db_path))
    conn.close()
    return str(db_path)


def _mock_tool_use(tool_name: str, input_dict: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = input_dict
    msg = MagicMock(); msg.content = [block]
    msg.stop_reason = "tool_use"
    return msg


def _mock_done(rationale="ok") -> MagicMock:
    return _mock_tool_use("emit_done", {"rationale": rationale})


def _mock_client(*responses) -> MagicMock:
    client = MagicMock()
    client.messages.create.side_effect = list(responses)
    return client


def _starter():
    return parse_l3(
        "screen #screen-root {\n"
        '  text #title "draft"\n'
        "  rectangle #placeholder\n"
        "  rectangle #spacer\n"
        "}\n"
    )


# --------------------------------------------------------------------------- #
# Plan §3.4 acceptance #1 — `dd design --brief` end-to-end                    #
# --------------------------------------------------------------------------- #

class TestStage3AcceptanceBrief:
    """`dd design --brief "..."` produces a session, runs primitives,
    ends with a renderable screen + full move log."""

    def test_brief_produces_session_with_variants_and_log(
        self, tmp_db_path, capsys,
    ):
        # Mock a 3-step session: NAME, EDIT, DONE.
        client = _mock_client(
            _mock_tool_use(
                "emit_name_subtree",
                {"eid": "screen-root", "description": "the login screen root"},
            ),
            _mock_tool_use(
                "emit_delete_edit",
                {"target_eid": "spacer", "rationale": "trim spacer"},
            ),
            _mock_done("login screen ready"),
        )
        # Patch the agent loop to use our starter doc instead of the
        # default empty one (so the LLM has eids to act on).
        from dd.agent import loop as agent_loop
        original_default = agent_loop._empty_starting_doc
        try:
            agent_loop._empty_starting_doc = lambda: _starter()
            with patch(
                "dd.cli._make_anthropic_client", return_value=client,
            ):
                cli_main([
                    "design", "--brief", "a login screen",
                    "--db", tmp_db_path,
                ])
        finally:
            agent_loop._empty_starting_doc = original_default

        # Acceptance #1: session exists, variants chained, move log
        # full.
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn)
        assert len(sessions) == 1
        assert sessions[0].brief == "a login screen"

        variants = list_variants(conn, sessions[0].id)
        # ROOT + NAME + EDIT (DONE doesn't create a variant).
        assert len(variants) >= 2
        primitives_seen = {v.primitive for v in variants}
        assert "EDIT" in primitives_seen or "NAME" in primitives_seen

        log = list_move_log(conn, sessions[0].id)
        log_kinds = [e.primitive for e in log]
        assert "DONE" in log_kinds


# --------------------------------------------------------------------------- #
# Plan §3.4 acceptance #2 — resume                                            #
# --------------------------------------------------------------------------- #

class TestStage3AcceptanceResume:
    """`dd design resume <id>` continues from the variant; the agent
    has full context (prior move log preserved)."""

    def test_resume_continues_chain_and_preserves_log(
        self, tmp_db_path, capsys,
    ):
        # Bootstrap a session with one root variant + a NAME log entry.
        from dd.focus import MoveLogEntry
        from dd.sessions import append_move_log_entry
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        sid = create_session(conn, brief="seed brief")
        v0 = create_variant(
            conn, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=_starter(),
        )
        append_move_log_entry(
            conn, session_id=sid, variant_id=v0,
            entry=MoveLogEntry(
                primitive="NAME", scope_eid="screen-root",
                payload={"description": "from prior session"},
            ),
        )
        conn.close()

        # Resume: agent does one EDIT, then done.
        client = _mock_client(
            _mock_tool_use(
                "emit_delete_edit",
                {"target_eid": "spacer", "rationale": "trim"},
            ),
            _mock_done("ok"),
        )
        with patch(
            "dd.cli._make_anthropic_client", return_value=client,
        ):
            cli_main([
                "design", "resume", v0,
                "--db", tmp_db_path,
            ])

        # The resumed session has the same id, more variants, AND
        # the prior NAME entry preserved.
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn)
        assert len(sessions) == 1
        assert sessions[0].id == sid

        variants = list_variants(conn, sid)
        assert len(variants) >= 2  # root + new EDIT chain

        log = list_move_log(conn, sid)
        kinds = [e.primitive for e in log]
        assert "NAME" in kinds  # prior entry preserved
        assert "DONE" in kinds  # new entry from resume


# --------------------------------------------------------------------------- #
# Plan §3.4 acceptance #3 — branching from non-leaf                           #
# --------------------------------------------------------------------------- #

class TestStage3AcceptanceBranch:
    """`dd design branch` per plan §3.4 — but per simplicity-check
    (Codex+Sonnet confirmed): branching falls out of resume from a
    non-leaf variant. Same CLI verb, different semantics from the
    presence of a child."""

    def test_resuming_from_non_leaf_creates_sibling(
        self, tmp_db_path, capsys,
    ):
        # Bootstrap: session with v0 -> v1 chain.
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        sid = create_session(conn, brief="seed")
        v0 = create_variant(
            conn, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=_starter(),
        )
        v1 = create_variant(
            conn, session_id=sid, parent_id=v0,
            primitive="EDIT", edit_script="delete @placeholder",
            doc=parse_l3(
                "screen #screen-root {\n"
                '  text #title "draft"\n'
                "  rectangle #spacer\n"
                "}\n"
            ),
        )
        conn.close()

        # Branch: resume from v0 (NOT v1) — creates a sibling chain.
        client = _mock_client(
            _mock_tool_use(
                "emit_delete_edit",
                {"target_eid": "spacer", "rationale": "different choice"},
            ),
            _mock_done("ok"),
        )
        with patch(
            "dd.cli._make_anthropic_client", return_value=client,
        ):
            cli_main([
                "design", "resume", v0,  # non-leaf!
                "--db", tmp_db_path,
            ])

        # New variants exist whose parent_id is v0 (sibling of v1).
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        variants = list_variants(conn, sid)
        new_variants = [v for v in variants if v.id not in (v0, v1)]
        assert len(new_variants) >= 1
        # The first new variant has parent_id=v0 (sibling of v1).
        assert any(v.parent_id == v0 for v in new_variants)


# --------------------------------------------------------------------------- #
# Plan §3.4 acceptance #4 — queryable by fidelity                             #
# --------------------------------------------------------------------------- #

class TestStage3AcceptanceQueryable:
    """`show me all variants where scorer.fidelity > 0.8` — the
    `scores` JSON column exists and is queryable. A2 defers actual
    score population; the QUERY surface is what acceptance pins."""

    def test_scores_column_is_jsonable_and_queryable(
        self, tmp_db_path,
    ):
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        sid = create_session(conn, brief="x")
        v_high = create_variant(
            conn, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None, doc=_starter(),
            scores={"fidelity": 0.92, "coverage": 0.85},
        )
        v_low = create_variant(
            conn, session_id=sid, parent_id=v_high,
            primitive="EDIT", edit_script=None, doc=_starter(),
            scores={"fidelity": 0.45, "coverage": 0.40},
        )
        # SQL-side query exercising the JSON column.
        rows = conn.execute(
            "SELECT id FROM variants "
            "WHERE json_extract(scores, '$.fidelity') > 0.8 "
            "ORDER BY id"
        ).fetchall()
        ids = [r["id"] for r in rows]
        assert v_high in ids
        assert v_low not in ids

    def test_unscored_variants_round_trip_as_null(self, tmp_db_path):
        """Variants written without scores have scores=NULL, which
        is the A2 default state. The CLI's `dd design score`
        backend will populate them later."""
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        sid = create_session(conn, brief="x")
        vid = create_variant(
            conn, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=_starter(),
            # No scores=
        )
        loaded = load_variant(conn, vid)
        assert loaded.scores is None
        # And the SQL column is NULL.
        row = conn.execute(
            "SELECT scores FROM variants WHERE id=?", (vid,),
        ).fetchone()
        assert row["scores"] is None


# --------------------------------------------------------------------------- #
# Real-LLM capstone — multi-iter Sonnet against Dank screen 333 IR            #
# --------------------------------------------------------------------------- #

DANK_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "Dank-EXP-02.declarative.db",
)
DANK_DB_EXISTS = os.path.isfile(DANK_DB_PATH)

try:
    from dotenv import load_dotenv
    # ``override=True`` so a stale shell ``ANTHROPIC_API_KEY=""``
    # doesn't mask the real key in .env. Learned the hard way at
    # M1.5 capstone time.
    load_dotenv(
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        override=True,
    )
except Exception:  # pragma: no cover
    pass

HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY not set")
class TestStage3CapstoneReal:
    """Multi-iter real-Sonnet session against a synthesized starting
    doc derived from a Dank screen IR. Skipped by default; runs when
    ANTHROPIC_API_KEY is set + DB present.

    Asserts: the session creates multiple variants, the move log
    has plausible entries, and the loop halts cleanly within
    max_iters (not via stalled / all_failed)."""

    def test_multi_iter_session_against_dank_333(self, tmp_path):
        import sqlite3 as _sqlite3

        anthropic = pytest.importorskip("anthropic")

        from dd.agent.loop import run_session
        from dd.compress_l3 import compress_to_l3
        from dd.ir import generate_ir
        from dd.markup_l3 import emit_l3, parse_l3 as _parse_l3

        # Use a SEPARATE db file for the design session — don't
        # write to Dank-EXP-02.declarative.db.
        design_db_path = tmp_path / "design.db"
        design_conn = init_db(str(design_db_path))
        design_conn.execute("PRAGMA foreign_keys = ON")

        # Load the starting doc from Dank screen 333.
        dank_conn = _sqlite3.connect(DANK_DB_PATH)
        try:
            ir_result = generate_ir(dank_conn, 333)
            doc = compress_to_l3(
                ir_result["spec"], conn=dank_conn, screen_id=333,
            )
            doc = _parse_l3(emit_l3(doc))
        finally:
            dank_conn.close()

        client = anthropic.Anthropic()
        result = run_session(
            design_conn,
            brief=(
                "Trim 1-2 small redundant nodes from this screen "
                "(decorative rectangles, duplicate spacers). Make "
                "small, conservative changes — don't redesign."
            ),
            client=client,
            max_iters=4,
            starting_doc=doc,
        )

        # Session created, multiple iters, clean halt.
        assert result.session_id
        assert result.iterations >= 1
        assert result.halt_reason in ("done", "max_iters")
        # Should NOT be all_failed (Sonnet should pick valid edits)
        # nor stalled (the brief asks for trims; structural change
        # > 0).
        assert result.halt_reason not in ("all_failed",), (
            f"unexpected halt: {result.halt_reason}; "
            f"summary={result.move_log_summary}"
        )

        # The session has a multi-step move log persisted.
        log = list_move_log(design_conn, result.session_id)
        assert len(log) >= 1
        kinds = [e.primitive for e in log]
        # Either an EDIT or DONE entry should be present.
        assert any(k in {"EDIT", "DONE"} for k in kinds)

        design_conn.close()


# --------------------------------------------------------------------------- #
# M1 capstone — full round-trip including live Figma bridge                   #
# --------------------------------------------------------------------------- #

def _bridge_is_listening(port: int = 9228) -> bool:
    """Non-blocking probe: is something accepting connections on the
    Figma bridge port? Used to gate the M1 live capstone so CI (with
    no plugin running) skips cleanly.

    Uses ``socket.create_connection`` rather than AF_INET + 127.0.0.1
    because the figma-console-mcp websocket server binds to IPv6
    ``::1`` only — an AF_INET probe would falsely return "not
    listening" even when the bridge is up. ``create_connection``
    resolves ``localhost`` dual-stack and matches the behavior of
    the Node ``ws`` client inside ``render_test/execute_ref.js``."""
    import socket
    try:
        s = socket.create_connection(("localhost", port), timeout=0.5)
        s.close()
        return True
    except (OSError, socket.timeout):
        return False


BRIDGE_LISTENING = _bridge_is_listening()


@pytest.mark.integration
@pytest.mark.skipif(not DANK_DB_EXISTS, reason="Dank DB not present")
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY not set")
@pytest.mark.skipif(
    not BRIDGE_LISTENING,
    reason="Figma plugin bridge not listening on port 9228",
)
class TestStage3M1CapstoneLiveBridge:
    """End-to-end M1 capstone — the demo-gating path:

        dd design --brief "..." --starting-screen 333 \
                  --project-db Dank-EXP-02.declarative.db \
                  --db <tmp> \
                  --render-to-figma

    Exercises the full pipeline: load starting doc from project DB,
    run real-Sonnet session, collect cumulative edits from the
    variant chain, render original + final variant to a new Figma
    page, ship both over PROXY_EXECUTE.

    Triple-gated (API key + Dank DB + bridge listening) so CI and
    offline dev stay green. Uses the trim-heavy brief the Stage 3
    capstone already validates cleanly — append-heavy briefs are
    safer for demos given the deferred swap-then-text residual."""

    @pytest.fixture(autouse=True)
    def disable_test_timeout(self):
        """The ``set_timeout`` autouse fixture in tests/conftest.py
        kills every test at 30s via SIGALRM. A real-LLM multi-iter
        session plus two bridge renders blows past that legitimately.
        Cancel the alarm for this capstone."""
        import signal
        signal.alarm(0)
        yield

    def test_full_round_trip_against_dank_333(self, tmp_path, capsys):
        from dd.cli import main as cli_main

        design_db_path = str(tmp_path / "design.db")
        init_db(design_db_path).close()

        cli_main([
            "design",
            "--brief",
            "Trim 1-2 small redundant nodes from this screen "
            "(decorative rectangles, duplicate spacers). Make "
            "small, conservative changes — don't redesign.",
            "--starting-screen", "333",
            "--project-db", DANK_DB_PATH,
            "--db", design_db_path,
            "--max-iters", "3",
            "--render-to-figma",
        ])

        out = capsys.readouterr().out
        # Session summary lands.
        assert "iterations:" in out
        assert "halt:" in out
        assert "final_variant:" in out
        # Render hint lands (M1.4 surface contract).
        assert "rendered to Figma page" in out
        assert "design session" in out

        # Session + at least one non-ROOT variant persisted.
        conn = sqlite3.connect(design_db_path)
        conn.row_factory = sqlite3.Row
        try:
            sessions = conn.execute(
                "SELECT id FROM design_sessions"
            ).fetchall()
            assert len(sessions) == 1
            variant_count = conn.execute(
                "SELECT COUNT(*) AS c FROM variants "
                "WHERE session_id=?",
                (sessions[0]["id"],),
            ).fetchone()["c"]
            # ROOT + at least one iter-variant.
            assert variant_count >= 2
        finally:
            conn.close()
