"""Stage 3.2 — sessions persistence layer.

CRUD wrapping the migration-023 shape. Per Option 3 (gzipped TEXT
snapshots, no sibling blob store) + B (keep move_log).

The module owns:
- create_session(conn, brief) -> session_id
- create_variant(conn, session_id, parent_id, primitive, edit_script,
                 doc, scores=None, notes=None) -> variant_id
  (compresses the L3 doc to gzip+base64 for the markup_blob column)
- load_variant(conn, variant_id) -> VariantRow (snapshot decoded)
- list_variants(conn, session_id) -> list[VariantRow] (chronological)
- append_move_log_entry(conn, session_id, variant_id, entry)
  (writes a Stage-2 MoveLogEntry as a move_log row via to_dict)
- list_move_log(conn, session_id) -> list[MoveLogEntry] (chronological)
- list_sessions(conn, status_filter=None) -> list[SessionRow]

These are the building blocks Stage 3.3's loop + Stage 3.4's CLI
both consume. Stage-3 read paths return decoded markup as
L3Document — caller doesn't need to know about the gzip+base64
storage detail.
"""

from __future__ import annotations

import sqlite3

import pytest

from dd.db import init_db
from dd.focus import MoveLogEntry
from dd.markup_l3 import emit_l3, parse_l3
from dd.sessions import (
    SessionRow,
    VariantRow,
    append_move_log_entry,
    create_session,
    create_variant,
    iter_edits_on_path,
    list_move_log,
    list_sessions,
    list_variants,
    load_variant,
)


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _small_doc():
    return parse_l3(
        "screen #screen-root {\n"
        '  text #title "hello"\n'
        "}\n"
    )


# --------------------------------------------------------------------------- #
# create_session                                                              #
# --------------------------------------------------------------------------- #

class TestCreateSession:
    def test_returns_ulid_string(self, db):
        sid = create_session(db, brief="a settings page")
        assert isinstance(sid, str)
        assert len(sid) == 26  # ULID

    def test_persists_brief(self, db):
        sid = create_session(db, brief="a settings page")
        row = db.execute(
            "SELECT brief, status FROM design_sessions WHERE id=?",
            (sid,),
        ).fetchone()
        assert row["brief"] == "a settings page"
        assert row["status"] == "open"

    def test_blank_brief_rejected(self, db):
        # Empty / whitespace-only briefs are pointless — fail loud.
        with pytest.raises(ValueError, match="brief"):
            create_session(db, brief="")
        with pytest.raises(ValueError, match="brief"):
            create_session(db, brief="   ")


# --------------------------------------------------------------------------- #
# create_variant + load_variant                                               #
# --------------------------------------------------------------------------- #

class TestCreateAndLoadVariant:
    def test_root_variant_has_no_parent(self, db):
        sid = create_session(db, brief="x")
        vid = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="DRILL", edit_script=None,
            doc=_small_doc(),
        )
        row = db.execute(
            "SELECT parent_id, primitive FROM variants WHERE id=?",
            (vid,),
        ).fetchone()
        assert row["parent_id"] is None
        assert row["primitive"] == "DRILL"

    def test_child_variant_carries_parent(self, db):
        sid = create_session(db, brief="x")
        v1 = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="DRILL", edit_script=None,
            doc=_small_doc(),
        )
        v2 = create_variant(
            db, session_id=sid, parent_id=v1,
            primitive="EDIT", edit_script="delete @title",
            doc=_small_doc(),
        )
        row = db.execute(
            "SELECT parent_id FROM variants WHERE id=?", (v2,),
        ).fetchone()
        assert row["parent_id"] == v1

    def test_load_variant_decodes_doc(self, db):
        """The markup_blob column stores gzipped+base64 markup; load
        decodes it back to an L3Document the caller can use directly."""
        sid = create_session(db, brief="x")
        original = _small_doc()
        vid = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="DRILL", edit_script=None,
            doc=original,
        )
        loaded = load_variant(db, vid)
        assert isinstance(loaded, VariantRow)
        # Round-trip the doc through emit/parse — semantic equality.
        assert emit_l3(loaded.doc) == emit_l3(original)
        assert loaded.id == vid
        assert loaded.session_id == sid
        assert loaded.parent_id is None
        assert loaded.primitive == "DRILL"

    def test_load_variant_carries_metadata(self, db):
        sid = create_session(db, brief="x")
        vid = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="EDIT", edit_script="delete @title",
            doc=_small_doc(),
            scores={"fidelity": 0.92},
            notes="agent removed dead title",
        )
        loaded = load_variant(db, vid)
        assert loaded.edit_script == "delete @title"
        assert loaded.scores == {"fidelity": 0.92}
        assert loaded.notes == "agent removed dead title"

    def test_load_unknown_variant_returns_none(self, db):
        assert load_variant(db, "nonexistent-id") is None

    def test_compressed_blob_is_smaller_than_raw_for_real_doc(self, db):
        """Sanity check that gzip helps on a real-sized doc — Option 3
        skipped session_blobs on the assumption gzipped TEXT is enough."""
        from dd.markup_l3 import emit_l3
        # Build a doc with ~50 nodes — proxy for a real screen IR.
        src_lines = ["screen #screen-root {"]
        for i in range(50):
            src_lines.append(f'  text #t{i} "node {i}"')
        src_lines.append("}")
        src = "\n".join(src_lines)
        big_doc = parse_l3(src)
        sid = create_session(db, brief="x")
        vid = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="DRILL", edit_script=None,
            doc=big_doc,
        )
        row = db.execute(
            "SELECT length(markup_blob) AS blen FROM variants WHERE id=?",
            (vid,),
        ).fetchone()
        raw_len = len(emit_l3(big_doc))
        # Compressed + base64 should be SMALLER than raw markup at this
        # scale (~50 repetitive nodes compress well).
        assert row["blen"] < raw_len


# --------------------------------------------------------------------------- #
# list_variants                                                               #
# --------------------------------------------------------------------------- #

class TestListVariants:
    def test_returns_chronological(self, db):
        import time
        sid = create_session(db, brief="x")
        v1 = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="DRILL", edit_script=None, doc=_small_doc(),
        )
        time.sleep(0.002)  # ensure ULID time prefix differs
        v2 = create_variant(
            db, session_id=sid, parent_id=v1,
            primitive="EDIT", edit_script="delete @title",
            doc=_small_doc(),
        )
        rows = list_variants(db, sid)
        assert len(rows) == 2
        assert rows[0].id == v1
        assert rows[1].id == v2

    def test_filters_by_session(self, db):
        s1 = create_session(db, brief="a")
        s2 = create_session(db, brief="b")
        create_variant(
            db, session_id=s1, parent_id=None,
            primitive="DRILL", edit_script=None, doc=_small_doc(),
        )
        create_variant(
            db, session_id=s2, parent_id=None,
            primitive="DRILL", edit_script=None, doc=_small_doc(),
        )
        assert len(list_variants(db, s1)) == 1
        assert len(list_variants(db, s2)) == 1


# --------------------------------------------------------------------------- #
# move_log persistence                                                        #
# --------------------------------------------------------------------------- #

class TestMoveLog:
    def test_appends_movelogentry(self, db):
        sid = create_session(db, brief="x")
        vid = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="DRILL", edit_script=None, doc=_small_doc(),
        )
        entry = MoveLogEntry(
            primitive="NAME",
            scope_eid="features-section",
            payload={"description": "the showcase"},
            rationale=None,
        )
        append_move_log_entry(db, session_id=sid, variant_id=vid, entry=entry)
        row = db.execute(
            "SELECT primitive, payload FROM move_log WHERE session_id=?",
            (sid,),
        ).fetchone()
        assert row["primitive"] == "NAME"
        # Payload deserializes back to MoveLogEntry's to_dict shape.
        import json
        loaded = json.loads(row["payload"])
        assert loaded["primitive"] == "NAME"
        assert loaded["scope_eid"] == "features-section"
        assert loaded["payload"] == {"description": "the showcase"}

    def test_list_returns_chronological_movelogentries(self, db):
        sid = create_session(db, brief="x")
        vid = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="DRILL", edit_script=None, doc=_small_doc(),
        )
        e1 = MoveLogEntry(primitive="NAME", scope_eid="a", payload={})
        e2 = MoveLogEntry(primitive="DRILL", scope_eid="b", payload={"focus_goal": "x"})
        append_move_log_entry(db, session_id=sid, variant_id=vid, entry=e1)
        append_move_log_entry(db, session_id=sid, variant_id=vid, entry=e2)
        loaded = list_move_log(db, sid)
        assert len(loaded) == 2
        assert isinstance(loaded[0], MoveLogEntry)
        assert loaded[0].primitive == "NAME"
        assert loaded[1].primitive == "DRILL"
        assert loaded[1].payload == {"focus_goal": "x"}

    def test_variant_id_can_be_null(self, db):
        """Some move log entries (NAME on a session-level scope) may
        not be tied to a specific variant. Allow it."""
        sid = create_session(db, brief="x")
        entry = MoveLogEntry(primitive="NAME", scope_eid="root", payload={})
        append_move_log_entry(
            db, session_id=sid, variant_id=None, entry=entry,
        )
        rows = list_move_log(db, sid)
        assert len(rows) == 1


# --------------------------------------------------------------------------- #
# list_sessions                                                               #
# --------------------------------------------------------------------------- #

class TestListSessions:
    def test_returns_all_sessions_chronological(self, db):
        import time
        s1 = create_session(db, brief="first")
        time.sleep(0.002)
        s2 = create_session(db, brief="second")
        rows = list_sessions(db)
        assert len(rows) == 2
        assert rows[0].id == s1
        assert rows[0].brief == "first"
        assert rows[1].id == s2

    def test_filters_by_status(self, db):
        s_open = create_session(db, brief="active")
        s_archived = create_session(db, brief="old")
        db.execute(
            "UPDATE design_sessions SET status='archived' WHERE id=?",
            (s_archived,),
        )
        rows = list_sessions(db, status_filter="open")
        assert {r.id for r in rows} == {s_open}


# --------------------------------------------------------------------------- #
# iter_edits_on_path — variant-chain walker                                   #
# --------------------------------------------------------------------------- #

class TestIterEditsOnPath:
    """Walk ROOT → ... → variant_id via parent_id and concat the
    parsed L3 edit statements in order.

    M1 of the Figma round-trip needs the cumulative edit list to hand
    to `render_applied_doc(edits=...)` — the final variant's doc is
    the applied tree, but rebuild_maps_after_edits needs the full edit
    sequence to carry the original-screen nids through. Stage 4+ MCTS
    will want the same walker to reconstruct any point in the variant
    DAG. Living in dd/sessions.py keeps it co-located with the
    parent_id semantics it's walking.

    Non-EDIT variants (ROOT, NAME, DRILL, CLIMB) carry edit_script=NULL —
    the walker skips them silently.
    """

    def test_root_only_returns_empty_list(self, db):
        """ROOT has no edit_script. Walking a root variant yields no
        edits — distinguishable from 'variant not found' by not raising."""
        sid = create_session(db, brief="x")
        root = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=_small_doc(),
        )
        assert iter_edits_on_path(db, root) == []

    def test_single_edit_variant_returns_one_statement(self, db):
        """A ROOT → EDIT chain yields exactly one parsed edit."""
        sid = create_session(db, brief="x")
        root = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=_small_doc(),
        )
        v1 = create_variant(
            db, session_id=sid, parent_id=root,
            primitive="EDIT", edit_script="delete @title",
            doc=_small_doc(),
        )
        edits = iter_edits_on_path(db, v1)
        assert len(edits) == 1
        # Shape: a DeleteStatement targeting 'title'.
        from dd.markup_l3 import DeleteStatement
        assert isinstance(edits[0], DeleteStatement)

    def test_multi_edit_chain_returns_root_to_leaf_order(self, db):
        """Edits on a linear chain concatenate in chronological order
        (root → leaf). M1 needs this order to feed apply_edits /
        render_applied_doc — applying out of order would splice the
        wrong tree."""
        sid = create_session(db, brief="x")
        root = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=_small_doc(),
        )
        v1 = create_variant(
            db, session_id=sid, parent_id=root,
            primitive="EDIT", edit_script="delete @title",
            doc=_small_doc(),
        )
        v2 = create_variant(
            db, session_id=sid, parent_id=v1,
            primitive="EDIT", edit_script="delete @screen-root",
            doc=_small_doc(),
        )
        edits = iter_edits_on_path(db, v2)
        assert len(edits) == 2
        from dd.markup_l3 import DeleteStatement
        assert all(isinstance(e, DeleteStatement) for e in edits)
        # Root-to-leaf: title delete comes before screen-root delete.
        assert edits[0].target.path == "title"
        assert edits[1].target.path == "screen-root"

    def test_skips_non_edit_variants(self, db):
        """NAME / DRILL / CLIMB variants have edit_script=NULL — the
        walker traverses them but yields no statements. Semantic
        variants affect the agent's focus state, not the applied
        tree."""
        sid = create_session(db, brief="x")
        root = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=_small_doc(),
        )
        name = create_variant(
            db, session_id=sid, parent_id=root,
            primitive="NAME", edit_script=None,
            doc=_small_doc(),
        )
        drill = create_variant(
            db, session_id=sid, parent_id=name,
            primitive="DRILL", edit_script=None,
            doc=_small_doc(),
        )
        edit = create_variant(
            db, session_id=sid, parent_id=drill,
            primitive="EDIT", edit_script="delete @title",
            doc=_small_doc(),
        )
        edits = iter_edits_on_path(db, edit)
        assert len(edits) == 1

    def test_raises_when_variant_missing(self, db):
        """Surface this clearly, not as an empty list — the caller's
        session wiring is broken, not 'the session had no edits'."""
        with pytest.raises(ValueError) as exc:
            iter_edits_on_path(db, "01ZZZNOTAREALULID00000000000")
        assert "not found" in str(exc.value).lower()

    def test_raises_on_parent_cycle(self, db):
        """Codex flagged this: guard against cycles / corrupt parent
        pointers. Variants should form a DAG via parent_id, but a
        future writer (or a misaligned migration) could leave a cycle.
        The walker tracks visited ids and fails loudly."""
        sid = create_session(db, brief="x")
        # Create two variants linearly.
        v1 = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=_small_doc(),
        )
        v2 = create_variant(
            db, session_id=sid, parent_id=v1,
            primitive="EDIT", edit_script="delete @title",
            doc=_small_doc(),
        )
        # Corrupt the tree: parent v1 points at v2 (cycle).
        db.execute(
            "UPDATE variants SET parent_id=? WHERE id=?",
            (v2, v1),
        )
        db.commit()
        with pytest.raises(ValueError) as exc:
            iter_edits_on_path(db, v2)
        assert "cycle" in str(exc.value).lower()

    def test_iter_edits_raises_with_variant_context_on_bad_edit_script(
        self, db,
    ):
        """Codex C-fix: the render-time re-parse of a persisted
        ``edit_script`` used to raise a bare ``DDMarkupParseError`` from
        deep inside the parser — no variant_id, no excerpt. If a bad
        row ever slips past the upstream validation boundary (or comes
        in via a schema migration), the walker must wrap the parse
        failure with enough context to debug the offending row.

        This test deliberately bypasses the upstream validation by
        writing invalid L3 directly via raw sqlite, then asserts the
        wrapped error mentions the variant_id and an excerpt of the
        bad edit_script."""
        sid = create_session(db, brief="x")
        root = create_variant(
            db, session_id=sid, parent_id=None,
            primitive="ROOT", edit_script=None,
            doc=_small_doc(),
        )
        # Create a legitimate EDIT variant first, then corrupt its
        # edit_script via raw sqlite (bypassing any validation).
        v1 = create_variant(
            db, session_id=sid, parent_id=root,
            primitive="EDIT", edit_script="delete @title",
            doc=_small_doc(),
        )
        bad_script = 'append to=@X { frame #eid "Sign Out" }'
        db.execute(
            "UPDATE variants SET edit_script=? WHERE id=?",
            (bad_script, v1),
        )
        db.commit()

        with pytest.raises(ValueError) as exc:
            iter_edits_on_path(db, v1)
        msg = str(exc.value)
        assert v1 in msg, f"variant_id {v1} not in error: {msg!r}"
        # Excerpt of the offending edit_script in the error.
        assert "Sign Out" in msg or "append to=@X" in msg, (
            f"bad edit_script excerpt missing from error: {msg!r}"
        )
