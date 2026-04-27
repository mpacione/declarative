"""C3 — dd design lateral subcommand.

Per docs/plan-synth-gen-demo.md C3: produces N sibling variants from
one parent variant. Tests verify CLI surface + dispatcher logic +
that run_session is called with parent_variant_id once per brief.

End-to-end agent-loop coverage lives in tests/test_agent_loop.py;
these tests pin the CLI wiring + multi-brief loop semantics, with
``run_session`` stubbed so they don't depend on the Anthropic SDK.
"""

from __future__ import annotations

import sqlite3
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from dd.cli import _run_design_lateral, main as cli_main
from dd.db import init_db
from dd.markup_l3 import parse_l3
from dd.sessions import create_session, create_variant


@pytest.fixture
def tmp_db_path(tmp_path):
    """Return the path to a fresh session DB file (schema applied)."""
    db_path = tmp_path / "lateral.db"
    init_db(str(db_path)).close()
    return str(db_path)


@pytest.fixture
def seeded_parent(tmp_db_path):
    """Seed a session + ROOT variant; return (db_path, parent_variant_id).

    The lateral command's parent must exist before run_session is
    called; without this fixture a `parent variant ... not found`
    exit short-circuits every dispatcher test.
    """
    conn = sqlite3.connect(tmp_db_path)
    conn.row_factory = sqlite3.Row
    try:
        sid = create_session(conn, brief="seed for lateral siblings")
        vid = create_variant(
            conn,
            session_id=sid,
            parent_id=None,
            primitive="ROOT",
            edit_script=None,
            doc=parse_l3("screen #screen-root\n"),
        )
    finally:
        conn.close()
    return tmp_db_path, vid


def _mock_done_response() -> MagicMock:
    """LLM response that picks emit_done immediately."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_done"
    block.input = {"rationale": "nothing to do here"}
    msg = MagicMock()
    msg.content = [block]
    msg.stop_reason = "tool_use"
    return msg


def _mock_client(*responses) -> MagicMock:
    client = MagicMock()
    client.messages.create.side_effect = (
        list(responses) or [_mock_done_response()]
    )
    return client


# --------------------------------------------------------------------------- #
# CLI help-output                                                             #
# --------------------------------------------------------------------------- #

class TestLateralHelpOutput:
    """`dd design lateral --help` advertises the documented surface."""

    def test_lateral_help_mentions_brief(self):
        result = subprocess.run(
            [".venv/bin/python", "-m", "dd", "design", "lateral", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--brief" in result.stdout
        assert "Repeatable" in result.stdout

    def test_lateral_help_mentions_bridge_port(self):
        result = subprocess.run(
            [".venv/bin/python", "-m", "dd", "design", "lateral", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--bridge-port" in result.stdout

    def test_lateral_help_mentions_render_to_figma(self):
        result = subprocess.run(
            [".venv/bin/python", "-m", "dd", "design", "lateral", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--render-to-figma" in result.stdout
        assert "--starting-screen" in result.stdout
        assert "--variant-only" in result.stdout
        assert "--no-labels" in result.stdout
        assert "--dump-scripts" in result.stdout


# --------------------------------------------------------------------------- #
# Dispatcher semantics                                                         #
# --------------------------------------------------------------------------- #

class TestLateralDispatcher:
    """``_run_design_lateral`` calls ``run_session`` once per --brief
    with ``parent_variant_id`` pinned to the input."""

    def test_calls_run_session_once_per_brief(self, seeded_parent, capsys):
        db_path, parent_vid = seeded_parent
        captured_kwargs: list[dict] = []

        def fake_run_session(conn, **kwargs):
            captured_kwargs.append(dict(kwargs))
            from dd.agent.loop import SessionRunResult

            new_vid = create_variant(
                conn,
                session_id=_session_for(conn, kwargs["parent_variant_id"]),
                parent_id=kwargs["parent_variant_id"],
                primitive="EDIT",
                edit_script="set @screen-root x=1",
                doc=parse_l3("screen #screen-root x=1\n"),
            )
            return SessionRunResult(
                session_id=_session_for(conn, kwargs["parent_variant_id"]),
                final_variant_id=new_vid,
                iterations=1,
                halt_reason="done",
                move_log_summary=[],
            )

        with patch(
            "dd.cli._make_anthropic_client", return_value=_mock_client(),
        ):
            with patch(
                "dd.agent.loop.run_session", side_effect=fake_run_session,
            ):
                _run_design_lateral(
                    db_path,
                    parent_variant_id=parent_vid,
                    briefs=["A brief", "B brief", "C brief"],
                    max_iters=3,
                )

        assert len(captured_kwargs) == 3
        for kwargs in captured_kwargs:
            assert kwargs["parent_variant_id"] == parent_vid
        # Briefs preserved in argument order, one per call.
        assert [k["brief"] for k in captured_kwargs] == [
            "A brief", "B brief", "C brief",
        ]

    def test_summary_lists_one_session_per_run(
        self, seeded_parent, capsys,
    ):
        """``run_session`` resolves session_id from
        ``parent.session_id``, so all siblings share one session.
        The summary header pins one ``session:`` line."""
        db_path, parent_vid = seeded_parent

        def fake_run_session(conn, **kwargs):
            from dd.agent.loop import SessionRunResult

            sid = _session_for(conn, kwargs["parent_variant_id"])
            new_vid = create_variant(
                conn,
                session_id=sid,
                parent_id=kwargs["parent_variant_id"],
                primitive="EDIT",
                edit_script="set @screen-root x=1",
                doc=parse_l3("screen #screen-root x=1\n"),
            )
            return SessionRunResult(
                session_id=sid,
                final_variant_id=new_vid,
                iterations=1,
                halt_reason="done",
                move_log_summary=[],
            )

        with patch(
            "dd.cli._make_anthropic_client", return_value=_mock_client(),
        ):
            with patch(
                "dd.agent.loop.run_session", side_effect=fake_run_session,
            ):
                _run_design_lateral(
                    db_path,
                    parent_variant_id=parent_vid,
                    briefs=["A", "B"],
                    max_iters=2,
                )

        out = capsys.readouterr().out
        session_lines = [
            line for line in out.splitlines() if line.startswith("session: ")
        ]
        assert len(session_lines) == 1, (
            f"expected exactly one 'session:' header line; got "
            f"{session_lines!r} in:\n{out}"
        )
        # Parent variant referenced as the root.
        assert any(parent_vid in line for line in out.splitlines()), (
            f"summary missing root variant {parent_vid!r}:\n{out}"
        )
        # Two sibling variant lines.
        variant_lines = [
            line for line in out.splitlines()
            if line.lstrip().startswith("variant ")
        ]
        assert len(variant_lines) == 2


# --------------------------------------------------------------------------- #
# Validation / fail-fast                                                       #
# --------------------------------------------------------------------------- #

class TestLateralValidation:
    """Pre-flight guards: brief count, parent existence, render-flag
    pairing — every fail-fast happens BEFORE the Anthropic client is
    constructed (no API call burned on a doomed session)."""

    def test_requires_two_or_more_briefs(self, seeded_parent):
        db_path, parent_vid = seeded_parent
        with pytest.raises(SystemExit):
            _run_design_lateral(
                db_path,
                parent_variant_id=parent_vid,
                briefs=["only one"],
                max_iters=2,
            )

    def test_zero_briefs_exits(self, seeded_parent):
        db_path, parent_vid = seeded_parent
        with pytest.raises(SystemExit):
            _run_design_lateral(
                db_path,
                parent_variant_id=parent_vid,
                briefs=[],
                max_iters=2,
            )

    def test_argparse_rejects_zero_briefs(self, tmp_db_path):
        """The CLI parser path also rejects zero briefs (action="append"
        leaves briefs=None which becomes []). Same SystemExit."""
        # Bootstrap a parent variant so the parent-exists check would
        # also pass — we want to assert the brief-count guard fires.
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        try:
            sid = create_session(conn, brief="seed")
            vid = create_variant(
                conn, session_id=sid, parent_id=None,
                primitive="ROOT", edit_script=None,
                doc=parse_l3("screen #screen-root\n"),
            )
        finally:
            conn.close()

        with patch(
            "dd.cli._make_anthropic_client", return_value=_mock_client(),
        ):
            with pytest.raises(SystemExit):
                cli_main([
                    "design", "lateral", vid,
                    "--db", tmp_db_path,
                ])

    def test_validates_parent_exists(self, tmp_db_path, capsys):
        """A bogus parent_variant_id exits with a clear stderr message."""
        with patch(
            "dd.cli._make_anthropic_client", return_value=_mock_client(),
        ):
            with pytest.raises(SystemExit):
                _run_design_lateral(
                    tmp_db_path,
                    parent_variant_id="01ZZZNOT_A_REAL_VARIANT_ID",
                    briefs=["A", "B"],
                    max_iters=2,
                )
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_rejects_render_without_starting_screen(self, seeded_parent):
        db_path, parent_vid = seeded_parent
        with pytest.raises(SystemExit):
            _run_design_lateral(
                db_path,
                parent_variant_id=parent_vid,
                briefs=["A", "B"],
                max_iters=2,
                render_to_figma=True,
                starting_screen=None,
            )


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _session_for(conn, variant_id: str) -> str:
    """Look up the session_id for a variant id (mock helper)."""
    row = conn.execute(
        "SELECT session_id FROM variants WHERE id=?", (variant_id,),
    ).fetchone()
    assert row is not None, f"variant {variant_id} not in DB"
    return row["session_id"]
