"""Tests for classifier v2 orchestrator (cross-screen dedup + per-
node crops).

Flow:
  1. Per-screen formal + heuristic + link_parents (no API).
  2. Collect unclassified candidates globally across all screens.
  3. Dedup by structural signature → groups.
  4. Classify each group's representative via LLM.
  5. Propagate LLM verdict to all sci rows in the group.
  6. Fetch screen screenshots; crop representatives.
  7. Vision PS — one-crop-per-group, returns verdict for the rep;
     propagate to all members.
  8. Vision CS — multi-crop-per-group (crops across screens);
     propagate to all members.
  9. Per-screen consensus + skeleton.

Tests mock the Anthropic client + screenshot fetcher so we can
exercise the orchestrator flow without real API calls. They assert
that dedup actually reduces classify-call count, that verdicts
propagate to every member, and that the final DB state reflects
the expected three-source columns.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dd.catalog import seed_catalog
from dd.classify_v2 import run_classification_v2
from dd.db import init_db


def _seed_corpus_with_dupes(conn: sqlite3.Connection) -> None:
    """Seed three iPad screens, each with a 'Left' nav zone that's
    structurally identical (same name, same children, same parent).
    Plus one unique node on each screen.
    After dedup, 'Left' should collapse to 1 representative → 1 LLM
    call + 1 PS call covering all 3 instances. 'Unique' nodes stay
    as 3 separate groups.
    """
    seed_catalog(conn)
    conn.execute(
        "INSERT INTO files (id, file_key, name) "
        "VALUES (1, 'fk', 'F')"
    )
    # 3 screens, all in the same device_class + skeleton (for v1 CS
    # grouping; v2 uses dedup groups directly).
    for sid in (1, 2, 3):
        conn.execute(
            "INSERT INTO screens "
            "(id, file_id, figma_node_id, name, width, height, "
            " device_class) "
            "VALUES (?, 1, ?, ?, 428, 926, 'iphone')",
            (sid, f"s{sid}:0", f"Screen {sid}"),
        )
        # Screen root node (parent_id NULL, depth 0).
        conn.execute(
            "INSERT INTO nodes "
            "(id, screen_id, figma_node_id, name, node_type, depth, "
            " sort_order, x, y, width, height) "
            "VALUES (?, ?, ?, ?, 'FRAME', 0, 0, "
            " 0, 0, 428, 926)",
            (sid * 10, sid, f"{sid}:0", f"root-{sid}"),
        )
        # 'Left' nav zone — identical structure across screens.
        conn.execute(
            "INSERT INTO nodes "
            "(id, screen_id, figma_node_id, name, node_type, depth, "
            " sort_order, x, y, width, height, parent_id) "
            "VALUES (?, ?, ?, 'Left', 'FRAME', 1, 0, "
            " 0, 0, 100, 60, ?)",
            (sid * 10 + 1, sid, f"{sid}:left", sid * 10),
        )
        # A unique FRAME per screen.
        conn.execute(
            "INSERT INTO nodes "
            "(id, screen_id, figma_node_id, name, node_type, depth, "
            " sort_order, x, y, width, height, parent_id) "
            "VALUES (?, ?, ?, ?, 'FRAME', 1, 1, "
            " 100, 0, 200, 150, ?)",
            (
                sid * 10 + 2, sid, f"{sid}:u",
                f"Uniq{sid}", sid * 10,
            ),
        )
    conn.commit()


def _mock_llm_response(verdicts: list[dict]) -> SimpleNamespace:
    """Build a mock Anthropic response carrying a classify_nodes
    tool_use block. `verdicts` is a list of {node_id, canonical_type,
    confidence, reason}.
    """
    return SimpleNamespace(content=[
        SimpleNamespace(
            type="tool_use",
            name="classify_nodes",
            input={"classifications": verdicts},
        ),
    ])


def _mock_crops_response(verdicts: list[dict]) -> SimpleNamespace:
    """Streaming response for classify_nodes_from_crops."""
    return SimpleNamespace(content=[
        SimpleNamespace(
            type="tool_use",
            name="classify_nodes_from_crops",
            input={"classifications": verdicts},
        ),
    ])


class _FakeStreamCtx:
    def __init__(self, response):
        self._response = response
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get_final_message(self):
        return self._response


def _make_client(llm_calls: list, crops_calls: list) -> MagicMock:
    """Client mock.
    `llm_calls`: list of verdict-lists to serve, one per .create call.
    `crops_calls`: list of verdict-lists to serve, one per .stream call.
    """
    client = MagicMock()
    client.messages.create.side_effect = [
        _mock_llm_response(v) for v in llm_calls
    ]
    client.messages.stream.side_effect = [
        _FakeStreamCtx(_mock_crops_response(v)) for v in crops_calls
    ]
    return client


def _tiny_png() -> bytes:
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


class TestRunClassificationV2Shape:
    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_corpus_with_dupes(conn)
        yield conn
        conn.close()

    def test_runs_end_to_end_with_dedup(self, db: sqlite3.Connection):
        """3 screens × 2 candidates = 6 total. After dedup on the
        3 identical 'Left' nodes, LLM should see ~4 representatives
        (1 Left + 3 unique Uniq1/2/3). 3 fewer API calls than v1
        would have made.
        """
        # Verdicts for the 4 dedup-group representatives.
        # The LLM sees them in dedup-group insertion order: first
        # the Left (seen on screen 1), then Uniq1, Uniq2, Uniq3.
        llm_verdicts = [
            {"node_id": 11, "canonical_type": "header",
             "confidence": 0.9, "reason": "left-zone of header"},
            {"node_id": 12, "canonical_type": "container",
             "confidence": 0.8, "reason": "generic frame 1"},
            {"node_id": 22, "canonical_type": "container",
             "confidence": 0.8, "reason": "generic frame 2"},
            {"node_id": 32, "canonical_type": "container",
             "confidence": 0.8, "reason": "generic frame 3"},
        ]
        # Vision PS classifies the same 4 reps.
        ps_verdicts = [
            {"screen_id": 1, "node_id": 11,
             "canonical_type": "header", "confidence": 0.85,
             "reason": "visual confirms header"},
            {"screen_id": 1, "node_id": 12,
             "canonical_type": "container", "confidence": 0.7,
             "reason": "no specific identity"},
            {"screen_id": 2, "node_id": 22,
             "canonical_type": "container", "confidence": 0.7,
             "reason": "no specific identity"},
            {"screen_id": 3, "node_id": 32,
             "canonical_type": "container", "confidence": 0.7,
             "reason": "no specific identity"},
        ]
        # Vision CS — only the 'Left' group has multiple members;
        # the three Uniq1/2/3 are singletons.
        cs_verdicts = [
            {"screen_id": 1, "node_id": 11,
             "canonical_type": "header", "confidence": 0.88,
             "reason": "3 crops all consistent"},
        ]

        client = _make_client(
            llm_calls=[llm_verdicts],  # 1 batched LLM call total
            crops_calls=[ps_verdicts, cs_verdicts],
        )
        fetch_screenshot = MagicMock(return_value=_tiny_png())

        result = run_classification_v2(
            db, file_id=1, client=client, file_key="fk",
            fetch_screenshot=fetch_screenshot,
        )

        assert result["screens_processed"] == 3
        # Dedup: 4 groups from 6 candidates.
        assert result.get("dedup_groups") == 4
        assert result.get("dedup_candidates") == 6

    def test_llm_verdict_propagates_to_all_members(
        self, db: sqlite3.Connection,
    ):
        llm_verdicts = [
            {"node_id": 11, "canonical_type": "header",
             "confidence": 0.9, "reason": "r"},
            {"node_id": 12, "canonical_type": "container",
             "confidence": 0.8, "reason": "r"},
            {"node_id": 22, "canonical_type": "container",
             "confidence": 0.8, "reason": "r"},
            {"node_id": 32, "canonical_type": "container",
             "confidence": 0.8, "reason": "r"},
        ]
        ps_verdicts = [
            {"screen_id": 1, "node_id": 11,
             "canonical_type": "header", "confidence": 0.85,
             "reason": "r"},
        ]
        cs_verdicts = [
            {"screen_id": 1, "node_id": 11,
             "canonical_type": "header", "confidence": 0.88,
             "reason": "r"},
        ]
        # PS for the 3 unique nodes just picks "container".
        ps_verdicts += [
            {"screen_id": 1, "node_id": 12,
             "canonical_type": "container", "confidence": 0.7,
             "reason": "r"},
            {"screen_id": 2, "node_id": 22,
             "canonical_type": "container", "confidence": 0.7,
             "reason": "r"},
            {"screen_id": 3, "node_id": 32,
             "canonical_type": "container", "confidence": 0.7,
             "reason": "r"},
        ]
        client = _make_client(
            llm_calls=[llm_verdicts],
            crops_calls=[ps_verdicts, cs_verdicts],
        )
        fetch_screenshot = MagicMock(return_value=_tiny_png())

        run_classification_v2(
            db, file_id=1, client=client, file_key="fk",
            fetch_screenshot=fetch_screenshot,
        )

        # All 3 'Left' nodes should now have llm_type='header'
        # even though the LLM only classified one of them.
        rows = db.execute(
            "SELECT sci.node_id, sci.llm_type, sci.vision_ps_type, "
            "       sci.vision_cs_type "
            "FROM screen_component_instances sci "
            "JOIN nodes n ON n.id = sci.node_id "
            "WHERE n.name = 'Left' "
            "ORDER BY sci.node_id"
        ).fetchall()
        assert len(rows) == 3
        for r in rows:
            assert r[1] == "header", (
                f"LLM verdict should propagate to all Left members; "
                f"got {r}"
            )
            assert r[2] == "header", (
                f"PS verdict should propagate; got {r}"
            )
            assert r[3] == "header", (
                f"CS verdict should propagate; got {r}"
            )

    def test_consensus_computed_per_screen(
        self, db: sqlite3.Connection,
    ):
        """After v2 runs, each screen's LLM-classified rows should
        have consensus_method set (either unanimous/majority/etc.
        for LLM rows, or formal/heuristic for trusted rows).
        """
        llm_verdicts = [
            {"node_id": 11, "canonical_type": "header",
             "confidence": 0.9, "reason": "r"},
            {"node_id": 12, "canonical_type": "container",
             "confidence": 0.8, "reason": "r"},
            {"node_id": 22, "canonical_type": "container",
             "confidence": 0.8, "reason": "r"},
            {"node_id": 32, "canonical_type": "container",
             "confidence": 0.8, "reason": "r"},
        ]
        ps_verdicts = [
            {"screen_id": 1, "node_id": 11,
             "canonical_type": "header", "confidence": 0.85,
             "reason": "r"},
            {"screen_id": 1, "node_id": 12,
             "canonical_type": "container", "confidence": 0.7,
             "reason": "r"},
            {"screen_id": 2, "node_id": 22,
             "canonical_type": "container", "confidence": 0.7,
             "reason": "r"},
            {"screen_id": 3, "node_id": 32,
             "canonical_type": "container", "confidence": 0.7,
             "reason": "r"},
        ]
        cs_verdicts = [
            {"screen_id": 1, "node_id": 11,
             "canonical_type": "header", "confidence": 0.88,
             "reason": "r"},
        ]
        client = _make_client(
            llm_calls=[llm_verdicts],
            crops_calls=[ps_verdicts, cs_verdicts],
        )
        fetch_screenshot = MagicMock(return_value=_tiny_png())

        run_classification_v2(
            db, file_id=1, client=client, file_key="fk",
            fetch_screenshot=fetch_screenshot,
        )

        rows = db.execute(
            "SELECT consensus_method "
            "FROM screen_component_instances "
            "WHERE consensus_method IS NOT NULL"
        ).fetchall()
        assert len(rows) > 0, (
            "consensus_method should be set after v2 runs"
        )


class TestRunClassificationV2Empty:
    def test_no_candidates_returns_cleanly(self):
        conn = init_db(":memory:")
        seed_catalog(conn)
        conn.execute(
            "INSERT INTO files (id, file_key, name) "
            "VALUES (1, 'fk', 'F')"
        )
        conn.execute(
            "INSERT INTO screens "
            "(id, file_id, figma_node_id, name, width, height) "
            "VALUES (1, 1, 's1', 'S', 428, 926)"
        )
        # No nodes at depth >= 1; nothing to classify.
        client = MagicMock()
        fetch_screenshot = MagicMock(return_value=None)
        result = run_classification_v2(
            conn, file_id=1, client=client, file_key="fk",
            fetch_screenshot=fetch_screenshot,
        )
        assert result["dedup_groups"] == 0
        assert result["dedup_candidates"] == 0
        # No API calls when there's nothing to classify.
        client.messages.create.assert_not_called()
        client.messages.stream.assert_not_called()
        conn.close()
