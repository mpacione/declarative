"""Tests for classifier-v2.1 few-shot retrieval.

For each classify candidate, retrieve 3-5 structurally-similar nodes
from the user's review history (`classification_reviews` joined to
`screen_component_instances`). The retrieved examples are injected
into the LLM prompt as in-context ground-truth labels so the model
sees human judgments for similar patterns.

Retrieval ranks by `(parent_canonical_type_match, child_shape_jaccard,
name_overlap)` so an example whose parent + child-shape matches
exactly outranks a near-miss.
"""

from __future__ import annotations

import sqlite3

import pytest

from dd.catalog import seed_catalog
from dd.classify_few_shot import (
    retrieve_few_shot,
    format_few_shot_block,
)
from dd.db import init_db


def _seed_reviews(db: sqlite3.Connection) -> None:
    """Fixture: one file, one screen, parents + children properly
    linked via parent_id so the SQL join in retrieve_few_shot lands.
    """
    seed_catalog(db)
    db.execute(
        "INSERT INTO files (id, file_key, name) "
        "VALUES (1, 'fk', 'F')"
    )
    db.execute(
        "INSERT INTO screens "
        "(id, file_id, figma_node_id, name, width, height) "
        "VALUES (1, 1, 's1:0', 'S', 428, 926)"
    )
    # Parent nodes with sci rows (each has a distinct canonical type).
    parents = [
        (100, "header-1", "header"),
        (101, "bottom-nav-1", "bottom_nav"),
        (102, "card-1", "card"),
        (103, "pager-1", "pagination"),
    ]
    for pid, pname, pct in parents:
        db.execute(
            "INSERT INTO nodes "
            "(id, screen_id, figma_node_id, name, node_type, depth, "
            " sort_order, x, y, width, height) "
            "VALUES (?, 1, ?, ?, 'FRAME', 1, ?, 0, 0, 400, 60)",
            (pid, f"{pid}:0", pname, pid),
        )
        db.execute(
            "INSERT INTO screen_component_instances "
            "(screen_id, node_id, canonical_type, confidence, "
            " classification_source) "
            "VALUES (1, ?, ?, 0.95, 'formal')",
            (pid, pct),
        )

    # Child nodes + sci rows + reviews, each linked to a parent via
    # parent_id. ground_truth is what the reviewer said the child
    # should be classified as.
    fixtures = [
        # (nid, name, parent_nid, ground_truth, decision, source)
        (10, "Left", 100, "header", "accept_source", "llm"),
        (11, "Left", 100, "header", "accept_source", "vision_ps"),
        (12, "Left", 101, "navigation_row", "accept_source", "vision_cs"),
        (13, "image-box", 102, "image", "override", None),
        (14, "Frame 42", 102, "container", "accept_source", "llm"),
        (15, "dot", 103, "icon", "accept_source", "vision_ps"),
    ]
    for nid, name, parent_nid, gt, dtype, src in fixtures:
        db.execute(
            "INSERT INTO nodes "
            "(id, screen_id, figma_node_id, name, node_type, depth, "
            " sort_order, x, y, width, height, parent_id) "
            "VALUES (?, 1, ?, ?, 'FRAME', 2, ?, 0, 0, 100, 60, ?)",
            (nid, f"{nid}:0", name, nid, parent_nid),
        )
        # The child's own sci row — canonical_type reflects the
        # pre-review classifier verdict; the review can override it
        # via `decision_canonical_type`.
        db.execute(
            "INSERT INTO screen_component_instances "
            "(id, screen_id, node_id, canonical_type, confidence, "
            " classification_source, llm_type, vision_ps_type, "
            " vision_cs_type) "
            "VALUES (?, 1, ?, ?, 0.9, 'llm', ?, ?, ?)",
            # We set all 3 source columns to `gt` so whichever
            # source the reviewer accepted resolves to gt.
            (nid, nid, gt, gt, gt, gt),
        )
        db.execute(
            "INSERT INTO classification_reviews "
            "(sci_id, decision_type, source_accepted, "
            " decision_canonical_type) "
            "VALUES (?, ?, ?, ?)",
            (nid, dtype, src, gt if dtype == "override" else None),
        )
    db.commit()


def _mk_candidate(**overrides):
    base = {
        "name": "Left",
        "node_type": "FRAME",
        "parent_classified_as": "header",
        "child_type_dist": {"FRAME": 3, "TEXT": 1},
        "sample_text": "Filename",
    }
    base.update(overrides)
    return base


class TestRetrieveFewShot:
    @pytest.fixture
    def db(self) -> sqlite3.Connection:
        conn = init_db(":memory:")
        _seed_reviews(conn)
        yield conn
        conn.close()

    def test_returns_similar_reviewed_nodes(
        self, db: sqlite3.Connection,
    ):
        examples = retrieve_few_shot(
            db, _mk_candidate(parent_classified_as="header"), k=3,
        )
        assert len(examples) > 0
        # Should surface reviewed 'Left'-under-'header' nodes.
        names = [e["name"] for e in examples]
        assert "Left" in names

    def test_parent_type_match_ranks_highest(
        self, db: sqlite3.Connection,
    ):
        examples = retrieve_few_shot(
            db, _mk_candidate(parent_classified_as="header"), k=5,
        )
        # Top example's parent should match the query parent (header).
        assert examples[0].get("parent_canonical_type") == "header"

    def test_returns_ground_truth_label(
        self, db: sqlite3.Connection,
    ):
        examples = retrieve_few_shot(
            db, _mk_candidate(parent_classified_as="header"), k=1,
        )
        e = examples[0]
        assert e.get("ground_truth_type") in (
            "header", "navigation_row",
        )
        assert e.get("review_decision") in (
            "accept_source", "override",
        )

    def test_empty_when_no_reviews(self):
        db = init_db(":memory:")
        seed_catalog(db)
        examples = retrieve_few_shot(
            db, _mk_candidate(), k=3,
        )
        assert examples == []
        db.close()

    def test_k_caps_result_count(self, db: sqlite3.Connection):
        examples = retrieve_few_shot(
            db, _mk_candidate(parent_classified_as="header"), k=2,
        )
        assert len(examples) <= 2


class TestFormatFewShotBlock:
    def test_empty_list_returns_empty_string(self):
        assert format_few_shot_block([]) == ""

    def test_renders_example_lines(self):
        examples = [
            {
                "name": "Left",
                "parent_canonical_type": "header",
                "child_count": 5,
                "sample_text": "Filename",
                "ground_truth_type": "header",
                "review_decision": "accept_source",
            },
        ]
        block = format_few_shot_block(examples)
        # Each example appears + ground truth is labelled.
        assert "Left" in block
        assert "header" in block
        assert "ground truth" in block.lower() or "reviewed" in block.lower()
