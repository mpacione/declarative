"""Tests for the Tier 1.5 classification review CLI (M7.0.a Step 6).

The review loop walks flagged rows on a screen, shows the three
source verdicts + reasons + a set of visual references (Figma
deep-link printed, local PNG opened, optional inline terminal image),
and prompts for a decision: accept one of the three sources, emit an
override type, flag as unsure, or skip. Decisions write to
`classification_reviews` — the table is additive, so re-runs stack
rows rather than overwriting.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dd.catalog import seed_catalog
from dd.classify_review import (
    detect_terminal_image_support,
    fetch_flagged_rows,
    format_figma_deep_link,
    record_review_decision,
    run_review_tui,
)
from dd.db import init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seed_flagged_row(
    db: sqlite3.Connection,
    *,
    sci_id: int = 1,
    screen_id: int = 1,
    node_id: int = 10,
    figma_node_id: str | None = None,
    node_name: str = "artboard",
    canonical_type: str = "unsure",
    consensus_method: str = "three_way_disagreement",
    flagged: int = 1,
    llm_type: str = "button",
    llm_confidence: float = 0.8,
    llm_reason: str = "Rounded rectangle shape with label",
    vision_ps_type: str = "card",
    vision_ps_confidence: float = 0.75,
    vision_ps_reason: str = "Bounded rectangular container",
    vision_cs_type: str = "container",
    vision_cs_confidence: float = 0.7,
    vision_cs_reason: str = "Structural grouping",
) -> None:
    """Seed a single flagged sci row plus all four sources populated.
    Mirrors the state after a three-source run where consensus flagged
    the row for review.
    """
    if figma_node_id is None:
        figma_node_id = f"{node_id}:1"
    db.execute(
        "INSERT OR IGNORE INTO files (id, file_key, name) "
        "VALUES (1, 'fk', 'F')"
    )
    db.execute(
        "INSERT OR IGNORE INTO screens "
        "(id, file_id, figma_node_id, name, width, height) "
        "VALUES (?, 1, ?, 'S', 428, 926)",
        (screen_id, f"s{screen_id}:0"),
    )
    db.execute(
        "INSERT OR IGNORE INTO nodes "
        "(id, screen_id, figma_node_id, name, node_type, depth, sort_order) "
        "VALUES (?, ?, ?, ?, 'FRAME', 1, 0)",
        (node_id, screen_id, figma_node_id, node_name),
    )
    db.execute(
        "INSERT INTO screen_component_instances "
        "(id, screen_id, node_id, canonical_type, confidence, "
        " classification_source, consensus_method, flagged_for_review, "
        " llm_type, llm_confidence, llm_reason, "
        " vision_ps_type, vision_ps_confidence, vision_ps_reason, "
        " vision_cs_type, vision_cs_confidence, vision_cs_reason) "
        "VALUES (?, ?, ?, ?, ?, 'llm', ?, ?, "
        "        ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sci_id, screen_id, node_id, canonical_type,
            llm_confidence, consensus_method, flagged,
            llm_type, llm_confidence, llm_reason,
            vision_ps_type, vision_ps_confidence, vision_ps_reason,
            vision_cs_type, vision_cs_confidence, vision_cs_reason,
        ),
    )
    db.commit()


# ---------------------------------------------------------------------------
# format_figma_deep_link
# ---------------------------------------------------------------------------

class TestFormatFigmaDeepLink:
    def test_builds_figma_desktop_url(self):
        url = format_figma_deep_link("drxXOUOdYEBBQ09mrXJeYu", "10:1")
        assert url.startswith("figma://file/drxXOUOdYEBBQ09mrXJeYu")
        assert "node-id=" in url
        # Colons in node ids must be URL-encoded — Figma's URL parser
        # treats ':' as a path separator on some platforms.
        assert "10%3A1" in url

    def test_empty_node_id_falls_back_to_file_url(self):
        url = format_figma_deep_link("fk", "")
        assert url == "figma://file/fk"


# ---------------------------------------------------------------------------
# fetch_flagged_rows
# ---------------------------------------------------------------------------

class TestFetchFlaggedRows:
    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        yield conn
        conn.close()

    def test_returns_only_flagged_rows(self, db: sqlite3.Connection):
        _seed_flagged_row(db, sci_id=1, node_id=10, flagged=1)
        _seed_flagged_row(
            db, sci_id=2, node_id=11,
            canonical_type="button", consensus_method="unanimous",
            flagged=0,
        )
        rows = fetch_flagged_rows(db)
        assert len(rows) == 1
        assert rows[0]["sci_id"] == 1

    def test_filters_by_screen_id(self, db: sqlite3.Connection):
        _seed_flagged_row(db, sci_id=1, screen_id=1, node_id=10)
        _seed_flagged_row(db, sci_id=2, screen_id=2, node_id=20)
        rows = fetch_flagged_rows(db, screen_id=1)
        assert len(rows) == 1
        assert rows[0]["screen_id"] == 1

    def test_includes_all_three_sources(self, db: sqlite3.Connection):
        _seed_flagged_row(db)
        rows = fetch_flagged_rows(db)
        row = rows[0]
        assert row["llm_type"] == "button"
        assert row["vision_ps_type"] == "card"
        assert row["vision_cs_type"] == "container"
        assert "Rounded rectangle" in row["llm_reason"]
        assert row["figma_node_id"] == "10:1"
        assert row["node_name"] == "artboard"

    def test_respects_limit(self, db: sqlite3.Connection):
        for i in range(5):
            _seed_flagged_row(db, sci_id=100 + i, node_id=100 + i)
        rows = fetch_flagged_rows(db, limit=2)
        assert len(rows) == 2

    def test_excludes_already_reviewed(self, db: sqlite3.Connection):
        """By default, rows with any review row are filtered out."""
        _seed_flagged_row(db, sci_id=1)
        db.execute(
            "INSERT INTO classification_reviews "
            "(sci_id, decision_type) VALUES (1, 'skip')"
        )
        db.commit()
        rows = fetch_flagged_rows(db)
        assert rows == []


# ---------------------------------------------------------------------------
# record_review_decision
# ---------------------------------------------------------------------------

class TestRecordReviewDecision:
    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        _seed_flagged_row(conn, sci_id=1)
        yield conn
        conn.close()

    def test_accept_source_records_row(self, db: sqlite3.Connection):
        record_review_decision(
            db, sci_id=1, decision_type="accept_source",
            source_accepted="vision_ps",
            decision_canonical_type="card",
            notes="Visual glyph settles it",
        )
        row = db.execute(
            "SELECT decision_type, source_accepted, "
            "       decision_canonical_type, notes, decided_by "
            "FROM classification_reviews WHERE sci_id = 1"
        ).fetchone()
        assert row[0] == "accept_source"
        assert row[1] == "vision_ps"
        assert row[2] == "card"
        assert row[3].startswith("Visual")
        assert row[4] == "human"

    def test_override_records_row(self, db: sqlite3.Connection):
        record_review_decision(
            db, sci_id=1, decision_type="override",
            decision_canonical_type="heading",
            notes="None of the sources had it right",
        )
        row = db.execute(
            "SELECT decision_type, decision_canonical_type, notes "
            "FROM classification_reviews WHERE sci_id = 1"
        ).fetchone()
        assert row[0] == "override"
        assert row[1] == "heading"

    def test_skip_records_row_without_type(self, db: sqlite3.Connection):
        record_review_decision(
            db, sci_id=1, decision_type="skip",
        )
        row = db.execute(
            "SELECT decision_type, decision_canonical_type "
            "FROM classification_reviews WHERE sci_id = 1"
        ).fetchone()
        assert row[0] == "skip"
        assert row[1] is None

    def test_multiple_reviews_stack(self, db: sqlite3.Connection):
        """Table is additive; repeated reviews create new rows. The
        consensus view (future) will prefer the latest.
        """
        record_review_decision(db, sci_id=1, decision_type="skip")
        record_review_decision(
            db, sci_id=1, decision_type="override",
            decision_canonical_type="card",
        )
        row = db.execute(
            "SELECT COUNT(*) FROM classification_reviews WHERE sci_id = 1"
        ).fetchone()
        assert row[0] == 2


# ---------------------------------------------------------------------------
# run_review_tui — stubbed input loop
# ---------------------------------------------------------------------------

class TestRunReviewTUI:
    """Drive the interactive loop with a deterministic input queue
    and capture stdout so decisions land in the DB without a human.
    """

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        _seed_flagged_row(db=conn, sci_id=1, node_id=10)
        _seed_flagged_row(db=conn, sci_id=2, node_id=11)
        yield conn
        conn.close()

    def _drive(self, db, inputs, file_key="fk"):
        input_queue = list(inputs)
        outputs: list[str] = []
        def input_fn(prompt=""):
            outputs.append(prompt)
            return input_queue.pop(0)
        def output_fn(*args, **kwargs):
            outputs.append(" ".join(str(a) for a in args))
        run_review_tui(
            db, file_key=file_key,
            input_fn=input_fn, output_fn=output_fn,
        )
        return outputs

    def test_accepts_source_1_as_llm(self, db: sqlite3.Connection):
        # Two rows; accept LLM for both.
        self._drive(db, ["1", "", "1", ""])
        rows = db.execute(
            "SELECT sci_id, decision_type, source_accepted, "
            "       decision_canonical_type "
            "FROM classification_reviews ORDER BY sci_id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][1] == "accept_source"
        assert rows[0][2] == "llm"
        assert rows[0][3] == "button"  # seeded llm_type

    def test_accepts_source_2_as_vision_ps(self, db: sqlite3.Connection):
        self._drive(db, ["2", "", "q"])
        row = db.execute(
            "SELECT source_accepted, decision_canonical_type "
            "FROM classification_reviews WHERE sci_id = 1"
        ).fetchone()
        assert row[0] == "vision_ps"
        assert row[1] == "card"

    def test_accepts_source_3_as_vision_cs(self, db: sqlite3.Connection):
        self._drive(db, ["3", "", "q"])
        row = db.execute(
            "SELECT source_accepted, decision_canonical_type "
            "FROM classification_reviews WHERE sci_id = 1"
        ).fetchone()
        assert row[0] == "vision_cs"
        assert row[1] == "container"

    def test_override_prompts_for_type(self, db: sqlite3.Connection):
        # Answer `o`, then the prompted type, then optional notes.
        self._drive(db, ["o", "heading", "", "q"])
        row = db.execute(
            "SELECT decision_type, decision_canonical_type "
            "FROM classification_reviews WHERE sci_id = 1"
        ).fetchone()
        assert row[0] == "override"
        assert row[1] == "heading"

    def test_skip_records_skip(self, db: sqlite3.Connection):
        self._drive(db, ["s", "q"])
        row = db.execute(
            "SELECT decision_type FROM classification_reviews WHERE sci_id = 1"
        ).fetchone()
        assert row[0] == "skip"

    def test_unsure_records_unsure(self, db: sqlite3.Connection):
        self._drive(db, ["u", "", "q"])
        row = db.execute(
            "SELECT decision_type FROM classification_reviews WHERE sci_id = 1"
        ).fetchone()
        assert row[0] == "unsure"

    def test_quit_before_any_decision(self, db: sqlite3.Connection):
        self._drive(db, ["q"])
        row = db.execute(
            "SELECT COUNT(*) FROM classification_reviews"
        ).fetchone()
        assert row[0] == 0

    def test_invalid_choice_reprompts(self, db: sqlite3.Connection):
        # Invalid `x` then valid `s` for first row, then quit.
        self._drive(db, ["x", "s", "q"])
        row = db.execute(
            "SELECT decision_type FROM classification_reviews WHERE sci_id = 1"
        ).fetchone()
        assert row[0] == "skip"


# ---------------------------------------------------------------------------
# detect_terminal_image_support
# ---------------------------------------------------------------------------

class TestDetectTerminalImageSupport:
    """Inline-image escape support is detected from environment vars.
    Real terminal behavior is untestable here; we just confirm the
    known strings match expected environments.
    """

    def test_iterm2(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        assert detect_terminal_image_support() == "iterm2"

    def test_kitty(self, monkeypatch):
        monkeypatch.setenv("KITTY_WINDOW_ID", "1")
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        assert detect_terminal_image_support() == "kitty"

    def test_ghostty(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        assert detect_terminal_image_support() == "ghostty"

    def test_unknown(self, monkeypatch):
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        assert detect_terminal_image_support() is None
