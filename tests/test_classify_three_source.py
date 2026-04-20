"""Tests for the three-source orchestrator (M7.0.a Step 4).

Verifies the pipeline: formal / heuristic / LLM produce primary
verdicts; vision PS + CS add per-source verdicts; `apply_consensus`
computes canonical_type + consensus_method + flagged_for_review from
the persisted raw signals.

The three-source cascade lives inside `dd.classify.run_classification`
under the `three_source=True` flag. Rows originated by formal or
heuristic stages bypass voting (those sources are trusted);
`consensus_method` for them just records the cascade source.
"""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dd.catalog import seed_catalog
from dd.classify import (
    apply_consensus_to_screen,
    apply_vision_cs_results,
    apply_vision_ps_results,
)
from dd.db import init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seed_row(
    db: sqlite3.Connection, *,
    sci_id: int = 1, screen_id: int = 1, node_id: int = 1,
    canonical_type: str = "button",
    classification_source: str = "llm",
    confidence: float = 0.85,
    llm_type: str | None = None,
    llm_confidence: float | None = None,
    vision_ps_type: str | None = None,
    vision_ps_confidence: float | None = None,
    vision_cs_type: str | None = None,
    vision_cs_confidence: float | None = None,
    figma_node_id: str = "1:1",
    node_name: str = "btn/primary",
) -> None:
    """Seed a single sci row with whichever per-source columns the
    test case needs populated.
    """
    # Files / screens / nodes skeleton.
    db.execute(
        "INSERT OR IGNORE INTO files (id, file_key, name) "
        "VALUES (1, 'fk', 'F')"
    )
    db.execute(
        "INSERT OR IGNORE INTO screens "
        "(id, file_id, figma_node_id, name, width, height) "
        "VALUES (?, 1, ?, 'S', 428, 926)",
        (screen_id, f"s{screen_id}"),
    )
    db.execute(
        "INSERT OR IGNORE INTO nodes "
        "(id, screen_id, figma_node_id, name, node_type, depth, sort_order) "
        "VALUES (?, ?, ?, ?, 'INSTANCE', 1, 0)",
        (node_id, screen_id, figma_node_id, node_name),
    )
    db.execute(
        "INSERT INTO screen_component_instances "
        "(id, screen_id, node_id, canonical_type, confidence, "
        " classification_source, "
        " llm_type, llm_confidence, "
        " vision_ps_type, vision_ps_confidence, "
        " vision_cs_type, vision_cs_confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sci_id, screen_id, node_id, canonical_type, confidence,
            classification_source,
            llm_type, llm_confidence,
            vision_ps_type, vision_ps_confidence,
            vision_cs_type, vision_cs_confidence,
        ),
    )
    db.commit()


# ---------------------------------------------------------------------------
# apply_consensus_to_screen — bypass (formal / heuristic) branches
# ---------------------------------------------------------------------------

class TestConsensusBypassForTrustedSources:
    """Formal + heuristic classifications are trusted; consensus is a
    pass-through that just records the cascade source in
    consensus_method.
    """

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        yield conn
        conn.close()

    def test_formal_row_keeps_type_and_sets_method(
        self, db: sqlite3.Connection,
    ) -> None:
        _seed_row(db, classification_source="formal",
                  canonical_type="button", confidence=1.0)
        apply_consensus_to_screen(db, screen_id=1, rule="v1")
        row = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "button"
        assert row[1] == "formal"
        assert row[2] == 0

    def test_heuristic_row_keeps_type_and_sets_method(
        self, db: sqlite3.Connection,
    ) -> None:
        _seed_row(db, classification_source="heuristic",
                  canonical_type="header", confidence=0.8)
        apply_consensus_to_screen(db, screen_id=1, rule="v1")
        row = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "header"
        assert row[1] == "heuristic"
        assert row[2] == 0


# ---------------------------------------------------------------------------
# apply_consensus_to_screen — three-source voting branches
# ---------------------------------------------------------------------------

class TestConsensusThreeSourceVoting:
    """LLM rows with full three-source data → rule v1 chooses the
    canonical_type. Rows with partial data fall through to degraded
    branches (single_source / two_source_*).
    """

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        yield conn
        conn.close()

    def test_unanimous_agreement(self, db: sqlite3.Connection):
        _seed_row(
            db, classification_source="llm",
            canonical_type="button",
            llm_type="button", llm_confidence=0.9,
            vision_ps_type="button", vision_ps_confidence=0.85,
            vision_cs_type="button", vision_cs_confidence=0.88,
        )
        apply_consensus_to_screen(db, screen_id=1, rule="v1")
        row = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "button"
        assert row[1] == "unanimous"
        assert row[2] == 0

    def test_majority_overrides_original(self, db: sqlite3.Connection):
        # LLM says button; both vision say card. Majority → card.
        # canonical_type gets rewritten to card.
        _seed_row(
            db, classification_source="llm",
            canonical_type="button",
            llm_type="button", llm_confidence=0.8,
            vision_ps_type="card", vision_ps_confidence=0.85,
            vision_cs_type="card", vision_cs_confidence=0.9,
        )
        apply_consensus_to_screen(db, screen_id=1, rule="v1")
        row = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "card"
        assert row[1] == "majority"
        assert row[2] == 0

    def test_any_unsure_flags(self, db: sqlite3.Connection):
        _seed_row(
            db, classification_source="llm",
            canonical_type="button",
            llm_type="button", llm_confidence=0.8,
            vision_ps_type="unsure", vision_ps_confidence=0.4,
            vision_cs_type="button", vision_cs_confidence=0.85,
        )
        apply_consensus_to_screen(db, screen_id=1, rule="v1")
        row = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "unsure"
        assert row[1] == "any_unsure"
        assert row[2] == 1

    def test_three_way_disagreement_flags(self, db: sqlite3.Connection):
        _seed_row(
            db, classification_source="llm",
            canonical_type="button",
            llm_type="button", llm_confidence=0.8,
            vision_ps_type="card", vision_ps_confidence=0.7,
            vision_cs_type="container", vision_cs_confidence=0.7,
        )
        apply_consensus_to_screen(db, screen_id=1, rule="v1")
        row = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "unsure"
        assert row[1] == "three_way_disagreement"
        assert row[2] == 1

    def test_llm_only_single_source_no_flag(
        self, db: sqlite3.Connection,
    ) -> None:
        # Vision stages didn't run / failed; keep LLM's verdict, mark
        # single_source. Not flagged when the verdict isn't unsure.
        _seed_row(
            db, classification_source="llm",
            canonical_type="button",
            llm_type="button", llm_confidence=0.8,
        )
        apply_consensus_to_screen(db, screen_id=1, rule="v1")
        row = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "button"
        assert row[1] == "single_source"
        assert row[2] == 0

    def test_two_source_agreement_commits(
        self, db: sqlite3.Connection,
    ) -> None:
        _seed_row(
            db, classification_source="llm",
            canonical_type="button",
            llm_type="button", llm_confidence=0.8,
            vision_ps_type="button", vision_ps_confidence=0.85,
        )
        apply_consensus_to_screen(db, screen_id=1, rule="v1")
        row = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "button"
        assert row[1] == "two_source_unanimous"
        assert row[2] == 0

    def test_consensus_is_idempotent(self, db: sqlite3.Connection):
        """Running consensus twice on the same state must not change
        anything. Recomputable from persisted raw signals.
        """
        _seed_row(
            db, classification_source="llm",
            canonical_type="button",
            llm_type="button", llm_confidence=0.8,
            vision_ps_type="card", vision_ps_confidence=0.7,
            vision_cs_type="container", vision_cs_confidence=0.7,
        )
        apply_consensus_to_screen(db, screen_id=1, rule="v1")
        apply_consensus_to_screen(db, screen_id=1, rule="v1")
        # Still flagged with three_way_disagreement; llm_type intact.
        row = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review, "
            "       llm_type, vision_ps_type, vision_cs_type "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "unsure"
        assert row[1] == "three_way_disagreement"
        assert row[2] == 1
        assert row[3] == "button"
        assert row[4] == "card"
        assert row[5] == "container"


# ---------------------------------------------------------------------------
# apply_vision_ps_results / apply_vision_cs_results — write helpers
# ---------------------------------------------------------------------------

class TestApplyVisionResults:
    """The two helpers take `classify_batch`-shaped output and write
    vision_ps_* / vision_cs_* columns on the matching rows.
    """

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        seed_catalog(conn)
        _seed_row(
            conn, sci_id=1, screen_id=1, node_id=1,
            classification_source="llm",
            canonical_type="button", llm_type="button",
            llm_confidence=0.85,
        )
        yield conn
        conn.close()

    def test_ps_writes_type_confidence_reason(
        self, db: sqlite3.Connection,
    ) -> None:
        apply_vision_ps_results(db, [
            {
                "screen_id": 1, "node_id": 1,
                "canonical_type": "card", "confidence": 0.82,
                "reason": "Rounded rectangle with internal structure",
            },
        ])
        row = db.execute(
            "SELECT vision_ps_type, vision_ps_confidence, vision_ps_reason "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "card"
        assert row[1] == 0.82
        assert row[2].startswith("Rounded rectangle")

    def test_cs_writes_type_confidence_reason_evidence(
        self, db: sqlite3.Connection,
    ) -> None:
        apply_vision_cs_results(db, [
            {
                "screen_id": 1, "node_id": 1,
                "canonical_type": "card", "confidence": 0.9,
                "reason": "Same pattern appears on 3 other screens",
                "cross_screen_evidence": [
                    {"other_screen_id": 2, "other_node_id": 20,
                     "relation": "same_component"},
                ],
            },
        ])
        row = db.execute(
            "SELECT vision_cs_type, vision_cs_confidence, "
            "       vision_cs_reason, vision_cs_evidence_json "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] == "card"
        assert row[1] == 0.9
        assert row[2].startswith("Same pattern")
        evidence = json.loads(row[3])
        assert evidence[0]["relation"] == "same_component"

    def test_cs_leaves_evidence_null_when_absent(
        self, db: sqlite3.Connection,
    ) -> None:
        apply_vision_cs_results(db, [
            {
                "screen_id": 1, "node_id": 1,
                "canonical_type": "card", "confidence": 0.9,
                "reason": "No cross-screen signal on this one",
            },
        ])
        row = db.execute(
            "SELECT vision_cs_evidence_json "
            "FROM screen_component_instances WHERE id = 1"
        ).fetchone()
        assert row[0] is None

    def test_silently_skips_results_for_unknown_rows(
        self, db: sqlite3.Connection,
    ) -> None:
        # node_id 999 doesn't exist; apply_vision_* must not crash.
        apply_vision_ps_results(db, [
            {
                "screen_id": 1, "node_id": 999,
                "canonical_type": "card", "confidence": 0.8,
                "reason": "phantom",
            },
        ])
        row = db.execute(
            "SELECT COUNT(*) FROM screen_component_instances"
        ).fetchone()
        assert row[0] == 1  # still just the seeded row


# ---------------------------------------------------------------------------
# run_classification(three_source=True) — end-to-end cascade
# ---------------------------------------------------------------------------

def _mock_tool_response(classifications, tool_name):
    return SimpleNamespace(content=[
        SimpleNamespace(
            type="tool_use",
            name=tool_name,
            input={"classifications": classifications},
        ),
    ])


def _make_llm_client_returning(type_for_node: dict[int, str]) -> MagicMock:
    """Mocked Anthropic client that returns canned LLM classifications
    (tool_use block shaped like `classify_nodes`) for the given
    per-node types. Confidence 0.85 / stub reason.
    """
    classifications = [
        {"node_id": nid, "canonical_type": ctype,
         "confidence": 0.85, "reason": f"stub for {nid}"}
        for nid, ctype in type_for_node.items()
    ]
    mock = MagicMock()
    mock.messages.create.return_value = _mock_tool_response(
        classifications, "classify_nodes",
    )
    return mock


def _make_dual_client_returning(
    llm_types: dict[int, str],
    ps_types: dict[tuple[int, int], str],
    cs_types: dict[tuple[int, int], str],
) -> MagicMock:
    """Single mock client that multiplexes between classify_nodes
    (LLM text, non-streaming) and classify_nodes_across_screens
    (batched vision PS / CS, streaming).

    PS / CS discrimination strategy: in the orchestrator the PS call
    for screen S always precedes the CS batch call that includes S.
    When a (screen_id, node_id) appears in both the PS map AND the CS
    map, the first streaming call that references it returns the PS
    verdict; subsequent calls return the CS verdict. This keeps the
    mock robust even when a CS batch collapses to one effective screen
    because peers had no LLM candidates.
    """
    llm_response = _mock_tool_response(
        [
            {"node_id": nid, "canonical_type": ctype,
             "confidence": 0.85, "reason": f"llm:{nid}"}
            for nid, ctype in llm_types.items()
        ],
        "classify_nodes",
    )

    served_ps: set[tuple[int, int]] = set()

    def batched_response(screen_ids_in_prompt: list[int]):
        classifications: list[dict] = []
        for sid in screen_ids_in_prompt:
            for (map_sid, nid), _ in list(ps_types.items()) + list(cs_types.items()):
                if map_sid != sid:
                    continue
                key = (sid, nid)
                if key not in served_ps and key in ps_types:
                    ctype = ps_types[key]
                    served_ps.add(key)
                    source = "ps"
                elif key in cs_types:
                    ctype = cs_types[key]
                    source = "cs"
                else:
                    continue
                existing = [
                    c for c in classifications
                    if c["screen_id"] == sid and c["node_id"] == nid
                ]
                if existing:
                    continue
                classifications.append({
                    "screen_id": sid, "node_id": nid,
                    "canonical_type": ctype, "confidence": 0.82,
                    "reason": f"vision_{source}:{sid}:{nid}",
                })
        return _mock_tool_response(
            classifications, "classify_nodes_across_screens",
        )

    mock = MagicMock()
    mock.messages.create.return_value = llm_response

    class _StreamCtx:
        def __init__(self, screen_ids):
            self._screen_ids = screen_ids

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return batched_response(self._screen_ids)

    def stream_factory(*, messages, **kwargs):
        import re
        prompt_text = ""
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        prompt_text += block.get("text", "")
            elif isinstance(content, str):
                prompt_text += content
        screen_ids_in_prompt = sorted(set(
            int(m) for m in re.findall(r"screen_id=(\d+)", prompt_text)
        ))
        return _StreamCtx(screen_ids_in_prompt)

    mock.messages.stream = MagicMock(side_effect=stream_factory)
    return mock


def _seed_three_source_corpus(db: sqlite3.Connection) -> None:
    """Two screens in the same device_class + skeleton_type so they
    end up in the same cross-screen batch. Each has one unclassified
    FRAME that the LLM will classify.
    """
    seed_catalog(db)
    db.execute(
        "INSERT INTO files (id, file_key, name) VALUES (1, 'fk', 'F')"
    )
    db.execute(
        "INSERT INTO screens "
        "(id, file_id, figma_node_id, name, width, height, device_class) "
        "VALUES (1, 1, 's1:1', 'Home', 428, 926, 'iphone')"
    )
    db.execute(
        "INSERT INTO screens "
        "(id, file_id, figma_node_id, name, width, height, device_class) "
        "VALUES (2, 1, 's2:1', 'Settings', 428, 926, 'iphone')"
    )
    db.execute(
        "INSERT INTO screen_skeletons "
        "(screen_id, skeleton_notation, skeleton_type) "
        "VALUES (1, 'stack(hdr, body)', 'standard')"
    )
    db.execute(
        "INSERT INTO screen_skeletons "
        "(screen_id, skeleton_notation, skeleton_type) "
        "VALUES (2, 'stack(hdr, body)', 'standard')"
    )
    # One unclassified FRAME on each screen at depth 1.
    db.executemany(
        "INSERT INTO nodes "
        "(id, screen_id, figma_node_id, name, node_type, depth, "
        " sort_order, x, y, width, height) "
        "VALUES (?, ?, ?, ?, 'FRAME', 1, 0, 0, 100, 400, 200)",
        [
            (10, 1, "10:1", "artboard"),
            (20, 2, "20:1", "overlay"),
        ],
    )
    db.commit()


class TestRunClassificationThreeSource:
    """End-to-end orchestrator runs formal / heuristic / LLM + vision
    PS per-screen, then vision CS cross-screen, then consensus.
    """

    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_three_source_corpus(conn)
        yield conn
        conn.close()

    def test_all_three_sources_agree_unanimous(
        self, db: sqlite3.Connection,
    ) -> None:
        from dd.classify import run_classification
        client = _make_dual_client_returning(
            llm_types={10: "card", 20: "card"},
            ps_types={(1, 10): "card", (2, 20): "card"},
            cs_types={(1, 10): "card", (2, 20): "card"},
        )
        fetch = MagicMock(return_value=b"\x89PNG\r\n\x1a\n")

        result = run_classification(
            db, file_id=1, client=client, file_key="fk",
            fetch_screenshot=fetch, three_source=True,
        )

        assert result["screens_processed"] == 2
        assert result["llm_classified"] == 2
        assert result["vision_ps_applied"] >= 1  # tolerant
        # Consensus counts: 2 rows, both unanimous on card.
        rows = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review, "
            "       llm_type, vision_ps_type, vision_cs_type "
            "FROM screen_component_instances ORDER BY id"
        ).fetchall()
        for row in rows:
            assert row[0] == "card", row
            assert row[1] == "unanimous", row
            assert row[2] == 0
            assert row[3] == "card"
            assert row[4] == "card"
            assert row[5] == "card"

    def test_three_source_disagreement_resolves_to_cs_under_v2(
        self, db: sqlite3.Connection,
    ) -> None:
        """Under rule v2 (the default post-2026-04-20), three-way
        disagreement resolves to CS's verdict because CS has 2x vote.
        LLM=card(1), PS=button(1), CS=container(2) → container wins.
        Rule v1's `three_way_disagreement` flag is covered by the
        v1-explicit tests in TestConsensusThreeSourceVoting.
        """
        from dd.classify import run_classification
        client = _make_dual_client_returning(
            llm_types={10: "card"},
            ps_types={(1, 10): "button"},
            cs_types={(1, 10): "container"},
        )
        fetch = MagicMock(return_value=b"\x89PNG\r\n\x1a\n")

        run_classification(
            db, file_id=1, client=client, file_key="fk",
            fetch_screenshot=fetch, three_source=True,
        )
        row = db.execute(
            "SELECT canonical_type, consensus_method, flagged_for_review, "
            "       llm_type, vision_ps_type, vision_cs_type "
            "FROM screen_component_instances WHERE node_id = 10"
        ).fetchone()
        assert row[0] == "container"
        assert row[1] == "weighted_majority"
        assert row[2] == 0
        assert row[3] == "card"
        assert row[4] == "button"
        assert row[5] == "container"
