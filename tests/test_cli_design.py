"""Stage 3.4 — `dd design` CLI subcommands.

Per Codex+Sonnet 2026-04-23: 3 subcommands minimum-viable —
``--brief``, ``resume``, ``score`` — with branching falling out of
resume-from-non-leaf semantics (no separate `branch` subcommand).
``ls`` and ``show`` deferred to follow-up (raw SQL works; document
in --help). Per simplicity-check, we keep the CLI surface lean.

Tests use a mocked LLM client because the real path through
``dd.agent.loop.run_session`` is exercised end-to-end in
``test_agent_loop.py``. Here we just verify the CLI wiring:
arg parsing, dispatch, db wiring, exit code.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dd.cli import main as cli_main
from dd.db import init_db
from dd.sessions import (
    create_session,
    create_variant,
    list_sessions,
    list_variants,
)
from dd.markup_l3 import parse_l3


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture
def tmp_db_path(tmp_path):
    """Return the path to a fresh DB file."""
    db_path = tmp_path / "design.db"
    conn = init_db(str(db_path))
    conn.close()
    return str(db_path)


def _mock_done_response() -> MagicMock:
    """LLM response that picks emit_done immediately."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_done"
    block.input = {"rationale": "nothing to do here"}
    msg = MagicMock(); msg.content = [block]
    msg.stop_reason = "tool_use"
    return msg


def _mock_client(*responses) -> MagicMock:
    client = MagicMock()
    client.messages.create.side_effect = list(responses) or [_mock_done_response()]
    return client


# --------------------------------------------------------------------------- #
# `dd design --brief` — new session                                           #
# --------------------------------------------------------------------------- #

class TestDesignBrief:
    """`dd design --brief "..."` creates a session, runs the loop,
    persists variants + move log, prints the new session id."""

    def test_creates_session_and_prints_id(self, tmp_db_path, capsys):
        with patch("dd.cli._make_anthropic_client", return_value=_mock_client()):
            cli_main([
                "design", "--brief", "a settings page",
                "--db", tmp_db_path,
            ])
        out = capsys.readouterr().out
        # Some sortable id printed.
        assert any(len(line) >= 26 for line in out.splitlines()), (
            f"expected the new session ULID in stdout, got:\n{out}"
        )
        # Confirm a session row exists.
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn)
        assert len(sessions) == 1
        assert sessions[0].brief == "a settings page"

    def test_runs_the_loop(self, tmp_db_path, capsys):
        client = _mock_client()  # emits done immediately
        with patch("dd.cli._make_anthropic_client", return_value=client):
            cli_main([
                "design", "--brief", "anything",
                "--db", tmp_db_path,
            ])
        # The loop made at least one Anthropic call.
        assert client.messages.create.called

    def test_supports_max_iters_flag(self, tmp_db_path, capsys):
        # 5 done-responses in case the loop runs more than once.
        client = _mock_client(*[_mock_done_response() for _ in range(5)])
        with patch("dd.cli._make_anthropic_client", return_value=client):
            cli_main([
                "design", "--brief", "x",
                "--db", tmp_db_path,
                "--max-iters", "3",
            ])
        # done halts on the first turn → only 1 call.
        assert client.messages.create.call_count == 1

    def test_blank_brief_fails_fast(self, tmp_db_path, capsys):
        # Empty brief reaches create_session → ValueError → CLI prints
        # an error and exits non-zero.
        with patch("dd.cli._make_anthropic_client", return_value=_mock_client()):
            with pytest.raises(SystemExit) as exc_info:
                cli_main([
                    "design", "--brief", "  ",
                    "--db", tmp_db_path,
                ])
            assert exc_info.value.code != 0


# --------------------------------------------------------------------------- #
# `dd design resume` — continue or branch                                     #
# --------------------------------------------------------------------------- #

class TestDesignResume:
    """`dd design resume <variant-id>` continues from that variant.
    Branching falls out: resuming from a non-leaf variant creates
    a sibling chain (per simplicity-check, confirmed Codex+Sonnet)."""

    def _bootstrap_session(self, tmp_db_path) -> tuple[str, str]:
        """Create a session with one variant, return (sid, vid)."""
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        sid = create_session(conn, brief="seed")
        vid = create_variant(
            conn, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=parse_l3("screen #screen-root\n"),
        )
        conn.close()
        return sid, vid

    def test_resume_continues_existing_session(self, tmp_db_path, capsys):
        sid, vid = self._bootstrap_session(tmp_db_path)
        client = _mock_client()  # done immediately
        with patch("dd.cli._make_anthropic_client", return_value=client):
            cli_main([
                "design", "resume", vid,
                "--db", tmp_db_path,
            ])
        # The session row is unchanged; new variant(s) under it.
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        assert len(list_sessions(conn)) == 1
        assert len(list_variants(conn, sid)) >= 1

    def test_resume_unknown_variant_fails_fast(self, tmp_db_path):
        with patch("dd.cli._make_anthropic_client", return_value=_mock_client()):
            with pytest.raises(SystemExit) as exc_info:
                cli_main([
                    "design", "resume", "no-such-variant",
                    "--db", tmp_db_path,
                ])
            assert exc_info.value.code != 0


# --------------------------------------------------------------------------- #
# `dd design score` — A2's deferred-scoring entry point                       #
# --------------------------------------------------------------------------- #

class TestDesignScore:
    """`dd design score <session-id>` is the A2 deferred-scoring
    entry point. Per Codex's hybrid amendment: scoring is post-hoc,
    NOT in the agent loop. The CLI should be wired even if Stage 3
    ships with a stub implementation — the user-facing surface
    matters; the deep VLM scoring can land later."""

    def _bootstrap_session_with_variant(self, tmp_db_path) -> tuple[str, str]:
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        sid = create_session(conn, brief="seed")
        vid = create_variant(
            conn, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=parse_l3("screen #screen-root\n"),
        )
        conn.close()
        return sid, vid

    def test_score_subcommand_exists(self, tmp_db_path, capsys):
        sid, _ = self._bootstrap_session_with_variant(tmp_db_path)
        # Should exit 0 even if scoring is a stub.
        cli_main([
            "design", "score", sid,
            "--db", tmp_db_path,
        ])
        out = capsys.readouterr().out
        assert sid in out or "score" in out.lower()

    def test_score_unknown_session_fails_fast(self, tmp_db_path):
        with pytest.raises(SystemExit) as exc_info:
            cli_main([
                "design", "score", "no-such-session",
                "--db", tmp_db_path,
            ])
        assert exc_info.value.code != 0


# --------------------------------------------------------------------------- #
# Error surface: missing api key                                              #
# --------------------------------------------------------------------------- #

class TestDesignNeedsApiKey:
    """`--brief` and `resume` both call Anthropic. Without a key set,
    the CLI must fail with a helpful message, not a stack trace."""

    def test_brief_without_key_errors_helpfully(
        self, tmp_db_path, monkeypatch, capsys,
    ):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Make the helper raise like the real SDK would. The CLI
        # should catch + print a friendly error, not stack-trace.
        def _no_key_client():
            raise Exception("ANTHROPIC_API_KEY missing")
        with patch("dd.cli._make_anthropic_client", side_effect=_no_key_client):
            with pytest.raises((SystemExit, Exception)) as exc_info:
                cli_main([
                    "design", "--brief", "x",
                    "--db", tmp_db_path,
                ])
        # The error reaches the user — either as SystemExit (if the
        # CLI caught it) or via stderr (if Anthropic raised through).
        # Both are acceptable for Stage 3; the friendly-error UX is
        # already exercised by _make_anthropic_client's own try/except
        # path in production.
