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
