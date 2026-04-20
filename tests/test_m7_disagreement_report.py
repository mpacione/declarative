"""Tests for scripts/m7_disagreement_report.py (M7.0.a Step 10).

The report reads `screen_component_instances` + per-source columns
and emits a markdown document: summary stats, pair-disagreement heat
map, top-N 3-way-disagreement rows, and pattern clusters. Output is
the input to rule-v2 design in Step 12 — no re-classification needed,
just data.
"""

from __future__ import annotations

import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.db import init_db
from scripts.m7_disagreement_report import (
    cluster_by_pattern,
    count_by_consensus_method,
    pair_disagreement_matrix,
    render_report,
    top_three_way_disagreements,
)


def _seed_consensus_row(
    db: sqlite3.Connection,
    *,
    sci_id: int,
    node_id: int,
    screen_id: int = 1,
    canonical_type: str = "button",
    consensus_method: str = "unanimous",
    flagged: int = 0,
    llm_type: str | None = "button",
    vision_ps_type: str | None = "button",
    vision_cs_type: str | None = "button",
) -> None:
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
        (node_id, screen_id, f"{node_id}:1", f"node-{node_id}"),
    )
    db.execute(
        "INSERT INTO screen_component_instances "
        "(id, screen_id, node_id, canonical_type, confidence, "
        " classification_source, consensus_method, flagged_for_review, "
        " llm_type, vision_ps_type, vision_cs_type) "
        "VALUES (?, ?, ?, ?, 0.85, 'llm', ?, ?, ?, ?, ?)",
        (
            sci_id, screen_id, node_id, canonical_type,
            consensus_method, flagged,
            llm_type, vision_ps_type, vision_cs_type,
        ),
    )
    db.commit()


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    seed_catalog(conn)

    # 5 unanimous rows.
    for i in range(5):
        _seed_consensus_row(
            conn, sci_id=i + 1, node_id=10 + i,
            canonical_type="button", consensus_method="unanimous",
            llm_type="button", vision_ps_type="button",
            vision_cs_type="button",
        )

    # 3 majority rows (LLM=card, PS+CS=button).
    for i in range(3):
        _seed_consensus_row(
            conn, sci_id=100 + i, node_id=100 + i,
            canonical_type="button", consensus_method="majority",
            llm_type="card", vision_ps_type="button",
            vision_cs_type="button",
        )

    # 4 any_unsure rows with flagged=1.
    for i in range(4):
        _seed_consensus_row(
            conn, sci_id=200 + i, node_id=200 + i,
            canonical_type="unsure", consensus_method="any_unsure",
            flagged=1,
            llm_type="button", vision_ps_type="unsure",
            vision_cs_type="button",
        )

    # 2 three_way_disagreement rows with flagged=1.
    for i in range(2):
        _seed_consensus_row(
            conn, sci_id=300 + i, node_id=300 + i,
            canonical_type="unsure",
            consensus_method="three_way_disagreement",
            flagged=1,
            llm_type="button", vision_ps_type="card",
            vision_cs_type="container",
        )

    yield conn
    conn.close()


class TestCountByConsensusMethod:
    def test_counts_all_methods(self, db: sqlite3.Connection):
        counts = count_by_consensus_method(db)
        assert counts["unanimous"] == 5
        assert counts["majority"] == 3
        assert counts["any_unsure"] == 4
        assert counts["three_way_disagreement"] == 2


class TestPairDisagreementMatrix:
    def test_pair_counts(self, db: sqlite3.Connection):
        matrix = pair_disagreement_matrix(db)
        # LLM vs PS: unanimous 5 agree, majority 3 disagree (llm=card,
        # ps=button), any_unsure 4 disagree (llm=button, ps=unsure),
        # three_way 2 disagree (llm=button, ps=card) = 9 disagree.
        assert matrix[("llm", "vision_ps")]["disagree"] == 9
        assert matrix[("llm", "vision_ps")]["agree"] == 5

        # LLM vs CS: unanimous 5 agree, majority 3 disagree (llm=card,
        # cs=button), any_unsure 4 agree (both button),
        # three_way 2 disagree (llm=button, cs=container).
        assert matrix[("llm", "vision_cs")]["disagree"] == 5
        assert matrix[("llm", "vision_cs")]["agree"] == 9

        # PS vs CS: unanimous 5 agree, majority 3 agree (both button),
        # any_unsure 4 disagree (ps=unsure, cs=button),
        # three_way 2 disagree (ps=card, cs=container).
        assert matrix[("vision_ps", "vision_cs")]["disagree"] == 6
        assert matrix[("vision_ps", "vision_cs")]["agree"] == 8


class TestTopThreeWayDisagreements:
    def test_returns_only_three_way_rows(self, db: sqlite3.Connection):
        rows = top_three_way_disagreements(db, n=50)
        assert len(rows) == 2
        for r in rows:
            assert r["consensus_method"] == "three_way_disagreement"
            # All three types differ on a 3-way row.
            types = {r["llm_type"], r["vision_ps_type"], r["vision_cs_type"]}
            assert len(types) == 3

    def test_respects_limit(self, db: sqlite3.Connection):
        rows = top_three_way_disagreements(db, n=1)
        assert len(rows) == 1


class TestClusterByPattern:
    def test_clusters_flagged_rows_only(self, db: sqlite3.Connection):
        """Cluster function is scoped to flagged rows — the majority
        rows (flagged=0) don't contribute even though they do have
        a cross-source disagreement pattern. Rule-v2 targets the
        flagged cases.
        """
        clusters = cluster_by_pattern(db)
        # The any_unsure pattern: llm=button, ps=unsure, cs=button.
        assert any(
            "vision_ps=unsure" in k and "vision_cs=button" in k
            for k in clusters
        )
        # The three_way pattern: llm=button, ps=card, cs=container.
        assert any(
            "vision_ps=card" in k and "vision_cs=container" in k
            for k in clusters
        )
        # Non-flagged majority pattern (llm=card, ps+cs=button) MUST
        # NOT be in the flagged-rows cluster.
        assert not any(
            "llm=card / vision_ps=button / vision_cs=button" in k
            for k in clusters
        )


class TestRenderReport:
    def test_contains_summary_sections(self, db: sqlite3.Connection):
        md = render_report(db)
        assert "# M7.0.a disagreement report" in md
        assert "## Summary" in md
        assert "## Pair disagreement" in md
        assert "## Top" in md  # Top N three-way-disagreement
        assert "## Pattern clusters" in md

    def test_contains_flagged_count(self, db: sqlite3.Connection):
        md = render_report(db)
        # 4 any_unsure + 2 three_way = 6 flagged.
        assert "6 flagged" in md or "flagged: 6" in md or "flagged=6" in md

    def test_mentions_consensus_methods(self, db: sqlite3.Connection):
        md = render_report(db)
        assert "unanimous" in md
        assert "majority" in md
        assert "any_unsure" in md
        assert "three_way_disagreement" in md
