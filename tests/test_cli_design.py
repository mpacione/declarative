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


# --------------------------------------------------------------------------- #
# M1 — `--starting-screen <ID>` + `--render-to-figma` (close the loop)        #
# --------------------------------------------------------------------------- #

def _seed_project_db(db_path: str) -> int:
    """Seed a minimal classified screen and return its id.

    Mirrors tests/test_generate.py::_seed_gen_screen — one 428×926
    screen with a header + heading, enough for generate_ir +
    compress_to_l3 to produce a non-empty starting doc."""
    from dd.catalog import seed_catalog

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        seed_catalog(conn)
        conn.execute(
            "INSERT INTO files (id, file_key, name) VALUES "
            "(1, 'fk', 'Dank')"
        )
        conn.execute(
            "INSERT INTO screens (id, file_id, figma_node_id, name, "
            "width, height) VALUES "
            "(1, 1, 's1', 'Settings', 428, 926)"
        )
        nodes = [
            (10, 1, "h1", "nav/top-nav", "INSTANCE", 1, 0, 0, 0,
             428, 56, "HORIZONTAL"),
            (11, 1, "t1", "Page Title", "TEXT", 2, 0, 16, 70,
             396, 28, None),
        ]
        conn.executemany(
            "INSERT INTO nodes (id, screen_id, figma_node_id, name, "
            "node_type, depth, sort_order, x, y, width, height, "
            "layout_mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            nodes,
        )
        conn.execute(
            "UPDATE nodes SET font_size = 24, font_weight = 700 "
            "WHERE id = 11"
        )
        conn.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, "
            " classification_source) "
            "VALUES (1, 10, 'header', 1.0, 'formal')"
        )
        conn.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, "
            " classification_source) "
            "VALUES (1, 11, 'heading', 0.9, 'heuristic')"
        )
        conn.commit()
    finally:
        conn.close()
    return 1


class TestDesignBriefWithStartingScreen:
    """`dd design --brief "..." --starting-screen <ID> [--project-db <path>]`
    loads the starting doc from the project DB so the agent session
    operates on real content, not the default SYNTHESIZE empty doc.

    Split `--db` (session DB, where sessions/variants/move_log persist)
    from `--project-db` (source-of-truth DB, where screens + classified
    nodes + tokens + CKR live). Defaulting --project-db to --db keeps
    the single-DB path working."""

    def test_starting_screen_loads_doc_from_project_db(
        self, tmp_db_path, tmp_path, capsys,
    ):
        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        screen_id = _seed_project_db(project_db)

        captured_docs: list[object] = []

        def fake_run_session(conn, **kwargs):
            captured_docs.append(kwargs.get("starting_doc"))
            from dd.agent.loop import SessionRunResult
            # Bootstrap a session + root variant so downstream
            # orchestration has something to reference.
            from dd.sessions import create_session, create_variant
            sid = create_session(conn, brief=kwargs.get("brief") or "x")
            vid = create_variant(
                conn, session_id=sid, parent_id=None,
                primitive="ROOT", edit_script=None,
                doc=kwargs["starting_doc"],
            )
            return SessionRunResult(
                session_id=sid, iterations=0, halt_reason="done",
                final_variant_id=vid, move_log_summary=[],
            )

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.agent.loop.run_session",
                       side_effect=fake_run_session):
                cli_main([
                    "design", "--brief", "trim this",
                    "--starting-screen", str(screen_id),
                    "--project-db", project_db,
                    "--db", tmp_db_path,
                ])

        # The loop received a real starting_doc (not None) with
        # content — both elements from the project DB should be
        # reachable by eid.
        assert len(captured_docs) == 1
        doc = captured_docs[0]
        assert doc is not None
        # L3Document has top_level with the loaded screen.
        assert doc.top_level, "expected non-empty starting doc"

    def test_starting_screen_defaults_project_db_to_session_db(
        self, tmp_db_path, capsys,
    ):
        """If --project-db is omitted, the session DB is used as the
        source of truth (single-DB path). That's the simplest
        workflow when sessions + screens live together."""
        # Seed the session DB with a screen too.
        _seed_project_db(tmp_db_path)

        captured_docs: list[object] = []

        def fake_run_session(conn, **kwargs):
            captured_docs.append(kwargs.get("starting_doc"))
            from dd.agent.loop import SessionRunResult
            from dd.sessions import create_session, create_variant
            sid = create_session(conn, brief=kwargs.get("brief") or "x")
            vid = create_variant(
                conn, session_id=sid, parent_id=None,
                primitive="ROOT", edit_script=None,
                doc=kwargs["starting_doc"],
            )
            return SessionRunResult(
                session_id=sid, iterations=0, halt_reason="done",
                final_variant_id=vid, move_log_summary=[],
            )

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.agent.loop.run_session",
                       side_effect=fake_run_session):
                cli_main([
                    "design", "--brief", "x",
                    "--starting-screen", "1",
                    "--db", tmp_db_path,
                ])

        assert captured_docs and captured_docs[0] is not None

    def test_starting_screen_missing_screen_id_fails_fast(
        self, tmp_db_path, capsys,
    ):
        """Specifying a screen id that doesn't exist in the project DB
        must surface a clear error before the Anthropic client gets
        called (burning an API call on a doomed session is the wrong
        failure mode)."""
        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with pytest.raises(SystemExit) as exc_info:
                cli_main([
                    "design", "--brief", "x",
                    "--starting-screen", "9999",
                    "--db", tmp_db_path,
                ])
            assert exc_info.value.code != 0
        err = capsys.readouterr().err
        assert "9999" in err or "not found" in err.lower()


class TestDesignBriefRenderToFigma:
    """`--render-to-figma` closes the loop: after the session halts,
    the CLI renders both the original screen AND the final variant
    to a new Figma page keyed on the session ULID, side-by-side.

    Bridge I/O is stubbed in these tests — the live-bridge capstone
    is a separate integration asset gated on ANTHROPIC_API_KEY + a
    running plugin."""

    def test_render_to_figma_without_starting_screen_fails_fast(
        self, tmp_db_path, capsys,
    ):
        """Codex's risk: ambiguous flag combinations. For M1, the two
        flags must be used together — rendering 'to Figma' with no
        starting screen produces an empty-canvas result, which is a
        confusing demo. Fail loudly with a clear error."""
        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with pytest.raises(SystemExit) as exc_info:
                cli_main([
                    "design", "--brief", "x",
                    "--render-to-figma",
                    "--db", tmp_db_path,
                ])
            assert exc_info.value.code != 0
        err = capsys.readouterr().err
        assert "starting-screen" in err

    def test_starting_screen_without_render_to_figma_skips_bridge(
        self, tmp_db_path, tmp_path, capsys,
    ):
        """`--starting-screen` alone runs the session against real
        content but never touches Figma. Useful for testing without
        a live bridge."""
        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        _seed_project_db(project_db)

        bridge_calls: list[str] = []

        def fake_execute(**kwargs):
            bridge_calls.append(kwargs.get("script", ""))
            return {"__ok": True, "errors": [], "request_id": "x"}

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.apply_render.execute_script_via_bridge",
                       side_effect=fake_execute):
                cli_main([
                    "design", "--brief", "x",
                    "--starting-screen", "1",
                    "--project-db", project_db,
                    "--db", tmp_db_path,
                ])

        assert bridge_calls == []

    def test_render_to_figma_calls_bridge_with_session_page_name(
        self, tmp_db_path, tmp_path, capsys,
    ):
        """After the session halts, the CLI executes two render
        scripts via the bridge — one for the original screen, one
        for the final variant. Both share a page_name keyed on the
        session ULID (render_figma_ast's find-or-create preamble
        makes the second call land beside the first on the same
        page)."""
        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        _seed_project_db(project_db)

        bridge_calls: list[str] = []

        def fake_execute(**kwargs):
            bridge_calls.append(kwargs.get("script", ""))
            return {"__ok": True, "errors": [], "request_id": "x"}

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.apply_render.execute_script_via_bridge",
                       side_effect=fake_execute):
                cli_main([
                    "design", "--brief", "leave it as is",
                    "--starting-screen", "1",
                    "--project-db", project_db,
                    "--db", tmp_db_path,
                    "--render-to-figma",
                ])

        # Two bridge calls — original render + variant render.
        assert len(bridge_calls) == 2, (
            f"expected original + variant renders, got "
            f"{len(bridge_calls)} calls"
        )
        # Both scripts target a page name that carries "design session".
        for i, script in enumerate(bridge_calls):
            assert "design session" in script, (
                f"call {i} script missing page name preamble"
            )
        # Canvas positioning: original at (0,0), variant offset right.
        # The root-frame x/y emission happens inside the
        # setCurrentPageAsync(_page) block (render_figma_ast line
        # ~1747). Grab that block's `<var>.x = <num>;` line — the
        # variant render should have a larger x offset than the
        # original.
        import re
        xs = []
        for script in bridge_calls:
            # Root attach happens right after setCurrentPageAsync, so
            # the very next `.x = N;` line is the root frame's origin.
            after_page = script.split("setCurrentPageAsync", 1)
            tail = after_page[1] if len(after_page) > 1 else script
            m = re.search(r"\.x = (\d+(?:\.\d+)?);", tail)
            xs.append(float(m.group(1)) if m else -1.0)
        assert len(xs) == 2
        # One at 0, one >= screen_width (228 default screen; test
        # seed uses 428, so variant offset should be >= 428+200).
        assert min(xs) == 0.0, f"expected one render at x=0, got xs={xs}"
        assert max(xs) >= 428.0, (
            f"expected variant offset right of screen, got xs={xs}"
        )

    def test_render_to_figma_prints_session_summary_with_page_hint(
        self, tmp_db_path, tmp_path, capsys,
    ):
        """The demo surface wants a clear `→ rendered to Figma page
        'design session <ULID>'` line so the user knows what to look
        for. Without it the render happens silently and the user
        doesn't know where to click."""
        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        _seed_project_db(project_db)

        def fake_execute(**kwargs):
            return {"__ok": True, "errors": [], "request_id": "x"}

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.apply_render.execute_script_via_bridge",
                       side_effect=fake_execute):
                cli_main([
                    "design", "--brief", "x",
                    "--starting-screen", "1",
                    "--project-db", project_db,
                    "--db", tmp_db_path,
                    "--render-to-figma",
                ])

        out = capsys.readouterr().out
        assert "Figma page" in out or "figma page" in out.lower()
        assert "design session" in out

    def test_dump_scripts_writes_original_and_variant_to_disk(
        self, tmp_db_path, tmp_path, capsys,
    ):
        """`--dump-scripts <dir>` is an additive diagnostic side-channel:
        both JS render scripts land on disk AND the bridge still runs.
        Useful when the bridge times out or the variant render comes
        up empty — the on-disk files are the only thing left to read.
        """
        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        _seed_project_db(project_db)

        dump_dir = tmp_path / "scripts"

        bridge_calls: list[str] = []

        def fake_execute(**kwargs):
            bridge_calls.append(kwargs.get("script", ""))
            return {"__ok": True, "errors": [], "request_id": "x"}

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.apply_render.execute_script_via_bridge",
                       side_effect=fake_execute):
                cli_main([
                    "design", "--brief", "leave it as is",
                    "--starting-screen", "1",
                    "--project-db", project_db,
                    "--db", tmp_db_path,
                    "--render-to-figma",
                    "--dump-scripts", str(dump_dir),
                ])

        original_path = dump_dir / "original.js"
        variant_path = dump_dir / "variant.js"
        assert original_path.exists(), (
            f"expected {original_path} to be written"
        )
        assert variant_path.exists(), (
            f"expected {variant_path} to be written"
        )
        assert original_path.read_text().strip(), (
            "original.js was written but is empty"
        )
        assert variant_path.read_text().strip(), (
            "variant.js was written but is empty"
        )
        # Additive — bridge was still called for both renders.
        assert len(bridge_calls) == 2, (
            f"--dump-scripts must not skip bridge I/O; got "
            f"{len(bridge_calls)} bridge calls"
        )

    def test_render_to_figma_bridge_error_reaches_user(
        self, tmp_db_path, tmp_path, capsys,
    ):
        """Codex's explicit risk: silent partial execution. When the
        bridge rejects a script (connection refused, bad script,
        timeout) the CLI must surface that to the user, not swallow
        it and exit 0 with a successful-looking session summary."""
        from dd.apply_render import BridgeError

        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        _seed_project_db(project_db)

        def failing_execute(**kwargs):
            raise BridgeError(
                "execute_ref.js exited 1: PROXY_EXECUTE rejected"
            )

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.apply_render.execute_script_via_bridge",
                       side_effect=failing_execute):
                with pytest.raises(SystemExit) as exc_info:
                    cli_main([
                        "design", "--brief", "x",
                        "--starting-screen", "1",
                        "--project-db", project_db,
                        "--db", tmp_db_path,
                        "--render-to-figma",
                    ])
                assert exc_info.value.code != 0
        err = capsys.readouterr().err
        assert "bridge" in err.lower() or "proxy_execute" in err.lower()

    def test_render_session_page_name_includes_variant_id(
        self, tmp_db_path, tmp_path, capsys,
    ):
        """Page collision fix: a session's page_name must embed both
        the session prefix AND the final variant prefix. Two renders
        against the same session_id land on DIFFERENT pages (one per
        variant leaf) so the multi-turn demo doesn't stack renders
        at identical coordinates on a single page."""
        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        _seed_project_db(project_db)

        page_names_called: list[str] = []

        def fake_execute(**kwargs):
            script = kwargs.get("script", "")
            # The render_figma_ast preamble embeds the page name as
            # a JS string literal — capture it via regex.
            import re
            m = re.search(r'p\.name === "([^"]+)"', script)
            if m:
                page_names_called.append(m.group(1))
            return {"__ok": True, "errors": [], "request_id": "x"}

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.apply_render.execute_script_via_bridge",
                       side_effect=fake_execute):
                cli_main([
                    "design", "--brief", "leave it as is",
                    "--starting-screen", "1",
                    "--project-db", project_db,
                    "--db", tmp_db_path,
                    "--render-to-figma",
                ])

        # Both bridge calls target the same page, so there should be
        # two identical entries (one per script).
        assert len(page_names_called) == 2, (
            f"expected 2 bridge scripts with page_name preambles, got "
            f"{page_names_called}"
        )
        assert page_names_called[0] == page_names_called[1], (
            f"original + variant must target same page, got "
            f"{page_names_called}"
        )
        pn = page_names_called[0]
        # Session prefix still present.
        assert pn.startswith("design session "), (
            f"page_name {pn!r} must start with 'design session '"
        )
        # Variant-prefix substring also present — " / <ULID prefix>".
        import re
        # "design session XXXXXXXX / YYYYYYYYYYYY" — variant prefix
        # extends into the ULID random region (12 chars) so back-to-
        # back resumes within the same millisecond don't collide.
        m = re.match(
            r"design session ([0-9A-Z]{8}) / ([0-9A-Z]{12})$", pn,
        )
        assert m is not None, (
            f"page_name {pn!r} must carry BOTH session prefix and "
            "variant prefix — expected 'design session <SID8> / "
            "<VID12>'"
        )
        # Pull the actual session + variant ids out of the DB and
        # confirm the prefixes match (not just that two prefixes exist).
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        try:
            sessions = list_sessions(conn)
            assert len(sessions) == 1
            sid = sessions[0].id
            variants = list_variants(conn, sid)
            # The final variant is the leaf of the session — in a
            # done-immediately flow it's just the root.
            vids = [v.id for v in variants]
        finally:
            conn.close()
        assert m.group(1) == sid[:8], (
            f"session prefix mismatch: page_name had {m.group(1)!r}, "
            f"session id starts with {sid[:8]!r}"
        )
        assert m.group(2) in {v[:12] for v in vids}, (
            f"variant prefix {m.group(2)!r} not in session variants "
            f"{[v[:12] for v in vids]}"
        )

    def test_variant_only_skips_original_render(
        self, tmp_db_path, tmp_path, capsys,
    ):
        """Demo-recovery flag: `--variant-only` skips the heavy
        original-screen render and ships ONLY the final variant.

        Why it exists: rendering the source screen against a fresh
        Figma file containing the 87k-descendant Dank 1.0 library page
        consistently times out at the 300s PROXY_EXECUTE cap. The
        original render does many findOne calls under the preamble's
        currentPage side-effect dance and is the heavier of the two.
        The user can compare to the original by opening it directly
        in the source file — they don't need a fresh copy.

        Pin: with --variant-only, the bridge is called exactly ONCE
        (not twice), and the lone script carries the variant render
        (it has the page-name preamble + `appendChild` calls)."""
        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        _seed_project_db(project_db)

        bridge_calls: list[str] = []

        def fake_execute(**kwargs):
            bridge_calls.append(kwargs.get("script", ""))
            return {"__ok": True, "errors": [], "request_id": "x"}

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.apply_render.execute_script_via_bridge",
                       side_effect=fake_execute):
                cli_main([
                    "design", "--brief", "leave it as is",
                    "--starting-screen", "1",
                    "--project-db", project_db,
                    "--db", tmp_db_path,
                    "--render-to-figma",
                    "--variant-only",
                ])

        # The key invariant: ONE bridge call, not two. The whole
        # point of the flag is to skip the original render.
        assert len(bridge_calls) == 1, (
            f"--variant-only must skip the original render and ship "
            f"exactly one script (the variant); got "
            f"{len(bridge_calls)} calls"
        )
        # The lone script is a render — it carries the page-name
        # preamble + the variant's appendChild compose phase.
        script = bridge_calls[0]
        assert "design session" in script, (
            "single script must carry the page-name preamble"
        )
        assert "appendChild" in script, (
            "single script must be a render (variant render's compose "
            "phase emits appendChild)"
        )
        # Canvas position: with variant-only there's no original to
        # sit beside, so the variant should land at x=0 (not offset
        # right by screen_width + 200).
        import re
        after_page = script.split("setCurrentPageAsync", 1)
        tail = after_page[1] if len(after_page) > 1 else script
        m = re.search(r"\.x = (\d+(?:\.\d+)?);", tail)
        assert m is not None, (
            "could not find root frame x= in script tail"
        )
        assert float(m.group(1)) == 0.0, (
            f"variant-only must place variant at x=0 (no original "
            f"beside it), got x={m.group(1)}"
        )

    def test_variant_only_works_with_resume(
        self, tmp_db_path, tmp_path, capsys,
    ):
        """Sibling flag plumbing: `--variant-only` is also accepted on
        `resume` and produces the same single-script behavior, so the
        multi-turn demo (brief + resume) can still avoid the heavy
        original render on every iteration."""
        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        _seed_project_db(project_db)

        # Bootstrap a resumable variant so the dispatcher reaches
        # _run_design_resume rather than exiting before flag parsing.
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

        bridge_calls: list[str] = []

        def fake_execute(**kwargs):
            bridge_calls.append(kwargs.get("script", ""))
            return {"__ok": True, "errors": [], "request_id": "x"}

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.apply_render.execute_script_via_bridge",
                       side_effect=fake_execute):
                cli_main([
                    "design", "resume", vid,
                    "--starting-screen", "1",
                    "--project-db", project_db,
                    "--db", tmp_db_path,
                    "--render-to-figma",
                    "--variant-only",
                ])

        assert len(bridge_calls) == 1, (
            f"resume --variant-only must ship exactly one script "
            f"(the variant); got {len(bridge_calls)} calls"
        )
        script = bridge_calls[0]
        assert "design session" in script
        assert "appendChild" in script


class TestDesignResumeRenderToFigma:
    """Bug 1 + Bug 2 regression pin: `dd design resume` must support
    the same render-to-figma flag family as `--brief`, AND distinct
    resume renders against the same session must land on DIFFERENT
    pages (variant-prefix in page_name).

    Without this, the multi-turn demo (brief A, resume w/ refining
    brief B) can't ship — either `resume` can't render at all, or
    two renders stack at identical coordinates on the same page."""

    def test_resume_supports_render_flags(
        self, tmp_db_path, tmp_path, capsys,
    ):
        """Argparse-level smoke: the resume subparser accepts the
        same render-family flags as --brief. Failure mode pre-fix:
        argparse rejects the flags as unknown. We don't exercise the
        full pipeline here — just prove the flags parse."""
        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        _seed_project_db(project_db)

        # Bootstrap a resumable variant so the dispatcher reaches
        # _run_design_resume instead of exiting before argparse even
        # sees the resume-render flags.
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

        def fake_execute(**kwargs):
            return {"__ok": True, "errors": [], "request_id": "x"}

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.apply_render.execute_script_via_bridge",
                       side_effect=fake_execute):
                # Must not raise argparse errors.
                cli_main([
                    "design", "resume", vid,
                    "--starting-screen", "1",
                    "--project-db", project_db,
                    "--db", tmp_db_path,
                    "--render-to-figma",
                ])

    def test_resume_render_to_figma_creates_per_variant_page(
        self, tmp_db_path, tmp_path, capsys,
    ):
        """End-to-end: `--brief` once, then `resume <leaf>` with
        --render-to-figma. Asserts two bridge executions per render
        (original + variant = 4 total) and that each render lands on
        a DIFFERENT page (per-variant page_name, not per-session).

        Uses a `run_session` stub on the resume turn so the test
        deterministically creates a NEW leaf variant (a real done-
        immediately mock returns the parent we resumed from, which
        masks the page-collision under-test)."""
        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        _seed_project_db(project_db)

        page_names_by_call: list[str] = []

        def fake_execute(**kwargs):
            script = kwargs.get("script", "")
            import re
            m = re.search(r'p\.name === "([^"]+)"', script)
            if m:
                page_names_by_call.append(m.group(1))
            return {"__ok": True, "errors": [], "request_id": "x"}

        # 1. First render — `--brief`. Done-immediately is fine; the
        # session creates its ROOT variant before halting.
        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.apply_render.execute_script_via_bridge",
                       side_effect=fake_execute):
                cli_main([
                    "design", "--brief", "a",
                    "--starting-screen", "1",
                    "--project-db", project_db,
                    "--db", tmp_db_path,
                    "--render-to-figma",
                ])

        # Grab the brief's session + leaf-variant for the resume.
        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        try:
            sessions = list_sessions(conn)
            assert len(sessions) == 1
            sid = sessions[0].id
            variants = list_variants(conn, sid)
            assert len(variants) >= 1
            brief_leaf_vid = variants[-1].id
        finally:
            conn.close()

        # 2. Resume — stub run_session so it creates a fresh child
        # variant under the same session and returns the new id as
        # final_variant_id. This is the "agent did productive work"
        # shape — without it the page-name collision under test
        # is masked by the no-new-variant edge case.
        from dd.agent.loop import SessionRunResult
        from dd.sessions import create_variant as _cv
        from dd.markup_l3 import parse_l3 as _pl3

        def fake_resume_run_session(conn, **kwargs):
            new_vid = _cv(
                conn,
                session_id=sid,
                parent_id=kwargs["parent_variant_id"],
                primitive="EDIT",
                edit_script="set @screen-root brief-resumed=1",
                doc=_pl3("screen #screen-root brief-resumed=1\n"),
            )
            return SessionRunResult(
                session_id=sid,
                iterations=1,
                halt_reason="done",
                final_variant_id=new_vid,
                move_log_summary=[],
            )

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.agent.loop.run_session",
                       side_effect=fake_resume_run_session):
                with patch("dd.apply_render.execute_script_via_bridge",
                           side_effect=fake_execute):
                    cli_main([
                        "design", "resume", brief_leaf_vid,
                        "--starting-screen", "1",
                        "--project-db", project_db,
                        "--db", tmp_db_path,
                        "--render-to-figma",
                    ])

        # 4 bridge calls total — 2 per render.
        assert len(page_names_by_call) == 4, (
            f"expected 4 bridge calls (2 per render × 2 renders), "
            f"got {len(page_names_by_call)}: {page_names_by_call}"
        )
        # Within each render the two scripts share a page.
        assert page_names_by_call[0] == page_names_by_call[1], (
            f"--brief render split across pages: {page_names_by_call}"
        )
        assert page_names_by_call[2] == page_names_by_call[3], (
            f"resume render split across pages: {page_names_by_call}"
        )
        # The two renders must NOT share a page — that's the
        # page-collision regression. Different variant leaves =
        # different page names.
        brief_page = page_names_by_call[0]
        resume_page = page_names_by_call[2]
        assert brief_page != resume_page, (
            f"brief + resume landed on the same page "
            f"({brief_page!r}); page-collision regression. Each "
            "variant leaf must get its own page."
        )
        # Both pages should carry the shared session-prefix substring
        # (so the sidebar relationship is visible to the user).
        shared_session_prefix = f"design session {sid[:8]}"
        assert shared_session_prefix in brief_page, (
            f"brief page_name {brief_page!r} missing shared session "
            f"prefix {shared_session_prefix!r}"
        )
        assert shared_session_prefix in resume_page, (
            f"resume page_name {resume_page!r} missing shared "
            f"session prefix {shared_session_prefix!r}"
        )


class TestStartingDocWrapperShapeMatchesRenderer:
    """Regression pin for the 2026-04-24 "variant renders blank"
    bug. The agent's starting doc (produced by `_load_starting_doc`)
    and the renderer's original doc (produced by
    `_render_session_to_figma`) must use the SAME wrapper-collapse
    setting when compressing the same screen. If they diverge, the
    eid-chain paths in `rebuild_maps_after_edits._index_by_path`
    don't line up and every entry in nid_map misses — the final
    variant falls to Mode-2 cheap-emission for every node.

    Without this pin a pure-delete edit sequence can produce an
    almost-empty Figma render and pass structural tests silently
    (because spec_key_map falls through the "fresh node" branch
    and claims 100% coverage — it's the nid_map that matters).

    The pin: a starting doc loaded via `_load_starting_doc` must
    produce a tree whose eid-chain paths match what the renderer's
    `_compress_to_l3_impl(collapse_wrapper=False)` produces.
    Expressed as: a pure-delete round-trip preserves >90% nid_map
    coverage against the renderer's original_doc."""

    def test_load_starting_doc_matches_renderer_wrapper_shape(
        self, tmp_path,
    ):
        from dd.apply_render import rebuild_maps_after_edits
        from dd.cli import _load_starting_doc
        from dd.compress_l3 import _compress_to_l3_impl
        from dd.db import get_connection
        from dd.ir import generate_ir
        from dd.markup_l3 import Node, apply_edits, parse_l3

        project_db = str(tmp_path / "project.db")
        init_db(project_db).close()
        screen_id = _seed_project_db(project_db)

        starting_doc = _load_starting_doc(
            project_db_path=project_db, screen_id=screen_id,
        )

        # Simulate a pure-delete edit (grab the deepest leaf eid from
        # the starting doc and issue `delete @<eid>` against it). The
        # shape of the edit doesn't matter; what matters is that the
        # applied doc still has ≥90% of its nodes matching paths in
        # the renderer's original_doc.
        leaves: list[Node] = []
        stack = list(starting_doc.top_level)
        while stack:
            n = stack.pop()
            if not isinstance(n, Node):
                continue
            if n.block is None or not any(
                isinstance(s, Node) for s in n.block.statements
            ):
                leaves.append(n)
            else:
                stack.extend(n.block.statements)
        assert leaves, "fixture produced no leaves"
        target_eid = leaves[0].head.eid
        edit_doc = parse_l3(f"delete @{target_eid}\n")
        applied_doc = apply_edits(
            starting_doc, list(edit_doc.edits),
        )

        # Renderer side: exactly what `_render_session_to_figma` does.
        proj_conn = get_connection(project_db)
        try:
            ir_result = generate_ir(proj_conn, screen_id)
            (
                original_doc, _eid_nid, nid_map, spec_key_map,
                original_name_map, _desc,
            ) = _compress_to_l3_impl(
                ir_result["spec"], proj_conn, screen_id=screen_id,
                collapse_wrapper=False,
            )
            maps = rebuild_maps_after_edits(
                applied_doc=applied_doc,
                original_doc=original_doc,
                edits=list(edit_doc.edits),
                old_nid_map=nid_map,
                old_spec_key_map=spec_key_map,
                old_original_name_map=original_name_map,
                conn=proj_conn,
            )
        finally:
            proj_conn.close()

        # BFS the applied doc and count how many nodes got nid-mapped.
        applied_nodes: list[Node] = []
        q = list(applied_doc.top_level)
        while q:
            n = q.pop(0)
            if not isinstance(n, Node):
                continue
            applied_nodes.append(n)
            if n.block is not None:
                q.extend(n.block.statements)

        covered = sum(
            1 for n in applied_nodes if id(n) in maps.nid_map
        )
        total = len(applied_nodes)
        ratio = covered / max(total, 1)
        # Pre-fix (collapse_wrapper mismatch): nid_map was 0/N for
        # every applied-doc node — EVERY surviving node fell to
        # Mode-2 cheap emission. Post-fix on the real Dank capstone:
        # 109/109 = 100%. The seed fixture is only 2 nodes (1
        # survives after delete), so the strongest guarantee is
        # "strictly > 0" — but the bug produced exactly 0, so even
        # this pins the regression. On the real live-bridge capstone
        # (tests/test_stage3_acceptance.py) the assertion embedded in
        # the CLI output check tightens this to "visible content on
        # the canvas".
        assert covered > 0, (
            f"nid_map coverage {covered}/{total} — pre-fix this was "
            "exactly 0. _load_starting_doc's collapse_wrapper setting "
            "has diverged from the renderer's. See dd/cli.py "
            "_load_starting_doc CRITICAL comment."
        )
        # Sanity: the renderer-side original_doc must be non-empty
        # (if the seed fixture changes and produces a 1-node tree,
        # the coverage check above trivially passes).
        assert total >= 2, (
            "fixture too small — extend the seed screen or this "
            "regression pin has no teeth"
        )


# --------------------------------------------------------------------------- #
# M1 follow-up 2 — demo UX: auto-init, lower max-iters, progress output       #
# --------------------------------------------------------------------------- #

class TestDesignDemoUX:
    """The three UX warts Codex + a post-M1 real-run pass surfaced:

    1. `dd design --db /tmp/demo.db` on a fresh file dies with
       `no such table: design_sessions` — the CLI should init_db
       implicitly so one-command demos just work.
    2. `--max-iters` default of 10 means ~1 minute/iter × 10 =
       10 minutes of silence before stdout. That's demo-hostile.
       Lower default to 4; long-form runs pass explicit
       --max-iters.
    3. No per-iter progress output. Users stare at a blank
       terminal for minutes, assume it's hung. Emit an `[iter N/M]`
       line to stderr at the start of each session iteration."""

    def test_fresh_db_file_auto_inits_on_brief(
        self, tmp_path, capsys,
    ):
        """Pointing --db at a fresh file (no schema yet) must NOT
        fail with 'no such table'. The CLI initializes the schema
        transparently; idempotent if the DB already has tables."""
        fresh_db = tmp_path / "fresh.db"
        # Create the FILE but not the schema — simulates what
        # happens when the user copy-pastes `--db /tmp/demo.db`
        # and the OS creates the file on first connection.
        fresh_db.touch()
        assert fresh_db.exists()
        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            cli_main([
                "design", "--brief", "anything",
                "--db", str(fresh_db),
            ])
        # Successful exit → session persisted → schema got
        # initialized in-line.
        conn = sqlite3.connect(str(fresh_db))
        conn.row_factory = sqlite3.Row
        try:
            sessions = conn.execute(
                "SELECT id FROM design_sessions"
            ).fetchall()
            assert len(sessions) == 1
        finally:
            conn.close()

    def test_nonexistent_db_path_auto_inits(
        self, tmp_path, capsys,
    ):
        """Same guarantee when the file doesn't exist yet at all —
        the canonical demo flow. One command, session lands."""
        db_path = tmp_path / "does-not-exist-yet.db"
        assert not db_path.exists()
        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            cli_main([
                "design", "--brief", "anything",
                "--db", str(db_path),
            ])
        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM design_sessions"
            ).fetchone()[0]
            assert count == 1
        finally:
            conn.close()

    def test_max_iters_default_is_demo_friendly(self, tmp_db_path):
        """Default --max-iters is 4 (down from 10). A 4-iter Sonnet
        session against a mid-complexity screen lands in ~15-30s;
        10 iters can hit 4+ minutes. Demo-hostile default was
        making every first-time run feel hung."""
        client = _mock_client(
            *[_mock_done_response() for _ in range(15)]
        )
        # Simulate a non-halting LLM: return something that DOESN'T
        # halt. Easiest: an EDIT-like tool that keeps emitting edit
        # intents. The loop will only cap out if it doesn't halt
        # naturally. But our simple _mock_done_response halts on
        # iter 1 by emitting `emit_done`. Instead, look directly at
        # what CLI default feeds into run_session.
        captured: dict = {}

        def fake_run_session(conn, **kwargs):
            captured["max_iters"] = kwargs.get("max_iters")
            from dd.agent.loop import SessionRunResult
            from dd.sessions import create_session, create_variant
            from dd.markup_l3 import parse_l3
            sid = create_session(conn, brief=kwargs.get("brief") or "x")
            doc = kwargs.get("starting_doc") or parse_l3(
                "screen #stub {\n  text #t1 \"x\"\n}\n"
            )
            vid = create_variant(
                conn, session_id=sid, parent_id=None,
                primitive="ROOT", edit_script=None, doc=doc,
            )
            return SessionRunResult(
                session_id=sid, iterations=0,
                halt_reason="done", final_variant_id=vid,
                move_log_summary=[],
            )

        with patch("dd.cli._make_anthropic_client",
                   return_value=_mock_client()):
            with patch("dd.agent.loop.run_session",
                       side_effect=fake_run_session):
                cli_main([
                    "design", "--brief", "x",
                    "--db", tmp_db_path,
                ])
        # Default should be the new demo-friendly value.
        assert captured["max_iters"] == 4, (
            f"expected max_iters default of 4, got "
            f"{captured.get('max_iters')}"
        )

    def test_per_iter_progress_emitted_to_stderr(
        self, tmp_db_path, capsys,
    ):
        """The loop writes `[iter N/M] ...` to stderr on each turn
        so the user sees heartbeat progress during a multi-minute
        session. Without this the terminal looks hung.

        We validate via a 3-response mock that's forced to run 3
        iters (so the loop prints at least 2 iter lines)."""
        block_name = MagicMock(); block_name.type = "tool_use"
        block_name.name = "emit_name_subtree"
        block_name.input = {
            "eid": "screen-root",
            "description": "the screen root",
        }
        msg_name = MagicMock(); msg_name.content = [block_name]
        msg_name.stop_reason = "tool_use"

        block_done = MagicMock(); block_done.type = "tool_use"
        block_done.name = "emit_done"
        block_done.input = {"rationale": "ok"}
        msg_done = MagicMock(); msg_done.content = [block_done]
        msg_done.stop_reason = "tool_use"

        client = _mock_client(msg_name, msg_name, msg_done)

        # Patch `_empty_starting_doc` so the default SYNTHESIZE
        # path gives the LLM an addressable `#screen-root` eid
        # for emit_name_subtree.
        from dd.agent import loop as agent_loop
        original_default = agent_loop._empty_starting_doc
        try:
            agent_loop._empty_starting_doc = lambda: parse_l3(
                "screen #screen-root {\n"
                "  text #t1 \"hi\"\n"
                "}\n"
            )
            with patch("dd.cli._make_anthropic_client",
                       return_value=client):
                cli_main([
                    "design", "--brief", "x",
                    "--db", tmp_db_path,
                    "--max-iters", "3",
                ])
        finally:
            agent_loop._empty_starting_doc = original_default

        err = capsys.readouterr().err
        # At least one per-iter heartbeat landed before halt.
        assert "[iter 1" in err, (
            f"expected '[iter 1' progress line on stderr; got:\n{err}"
        )
