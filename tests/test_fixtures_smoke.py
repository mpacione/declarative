"""Smoke tests for fixture functions."""

import pytest
import sqlite3

from tests.fixtures import (
    seed_post_extraction,
    seed_post_clustering,
    seed_post_curation,
    seed_post_validation,
    make_mock_figma_response
)


@pytest.mark.unit
def test_seed_post_extraction(db: sqlite3.Connection):
    """Test that seed_post_extraction creates expected data."""
    conn = seed_post_extraction(db)

    # Check file count
    cursor = conn.execute("SELECT COUNT(*) FROM files")
    assert cursor.fetchone()[0] == 1

    # Check screen count
    cursor = conn.execute("SELECT COUNT(*) FROM screens")
    assert cursor.fetchone()[0] == 3

    # Check node count
    cursor = conn.execute("SELECT COUNT(*) FROM nodes")
    assert cursor.fetchone()[0] == 10

    # Check binding count
    cursor = conn.execute("SELECT COUNT(*) FROM node_token_bindings")
    assert cursor.fetchone()[0] == 15

    # Check all bindings are unbound
    cursor = conn.execute(
        "SELECT COUNT(*) FROM node_token_bindings WHERE binding_status = 'unbound'"
    )
    assert cursor.fetchone()[0] == 15

    # Check no tokens exist yet
    cursor = conn.execute("SELECT COUNT(*) FROM tokens")
    assert cursor.fetchone()[0] == 0


@pytest.mark.unit
def test_seed_post_clustering(db: sqlite3.Connection):
    """Test that seed_post_clustering extends extraction data correctly."""
    conn = seed_post_clustering(db)

    # Check tokens exist
    cursor = conn.execute("SELECT COUNT(*) FROM tokens")
    assert cursor.fetchone()[0] == 5  # 4 colors + 1 spacing

    # Check token collections
    cursor = conn.execute("SELECT COUNT(*) FROM token_collections")
    assert cursor.fetchone()[0] == 2  # Colors and Spacing

    # Check token values
    cursor = conn.execute("SELECT COUNT(*) FROM token_values")
    assert cursor.fetchone()[0] == 5  # 4 color values + 1 spacing value

    # Check bindings have token_ids
    cursor = conn.execute(
        "SELECT COUNT(*) FROM node_token_bindings WHERE token_id IS NOT NULL"
    )
    assert cursor.fetchone()[0] == 5  # 5 color bindings updated

    # Check binding status is proposed for updated ones
    cursor = conn.execute(
        "SELECT COUNT(*) FROM node_token_bindings WHERE binding_status = 'proposed'"
    )
    assert cursor.fetchone()[0] == 5


@pytest.mark.unit
def test_seed_post_curation(db: sqlite3.Connection):
    """Test that seed_post_curation promotes tokens and bindings."""
    conn = seed_post_curation(db)

    # Check tokens are curated
    cursor = conn.execute(
        "SELECT COUNT(*) FROM tokens WHERE tier = 'curated'"
    )
    assert cursor.fetchone()[0] == 5

    # Check no extracted tokens remain
    cursor = conn.execute(
        "SELECT COUNT(*) FROM tokens WHERE tier = 'extracted'"
    )
    assert cursor.fetchone()[0] == 0

    # Check bindings are bound
    cursor = conn.execute(
        "SELECT COUNT(*) FROM node_token_bindings WHERE binding_status = 'bound'"
    )
    assert cursor.fetchone()[0] == 5  # All proposed bindings become bound

    # Check no proposed bindings remain
    cursor = conn.execute(
        "SELECT COUNT(*) FROM node_token_bindings WHERE binding_status = 'proposed'"
    )
    assert cursor.fetchone()[0] == 0


@pytest.mark.unit
def test_seed_post_validation(db: sqlite3.Connection):
    """Test that seed_post_validation adds validation rows."""
    conn = seed_post_validation(db)

    # Check export_validations rows exist
    cursor = conn.execute("SELECT COUNT(*) FROM export_validations")
    assert cursor.fetchone()[0] == 4

    # Check all validations are info level (passing)
    cursor = conn.execute(
        "SELECT COUNT(*) FROM export_validations WHERE severity = 'info'"
    )
    assert cursor.fetchone()[0] == 4

    # Check no errors or warnings
    cursor = conn.execute(
        "SELECT COUNT(*) FROM export_validations WHERE severity IN ('error', 'warning')"
    )
    assert cursor.fetchone()[0] == 0

    # Check specific validation checks
    cursor = conn.execute(
        "SELECT check_name FROM export_validations ORDER BY id"
    )
    checks = [row[0] for row in cursor.fetchall()]
    assert checks == [
        "mode_completeness",
        "name_dtcg_compliant",
        "orphan_tokens",
        "name_uniqueness"
    ]


@pytest.mark.unit
def test_make_mock_figma_response():
    """Test that make_mock_figma_response generates expected data."""
    # Test with default node count
    response = make_mock_figma_response("Test Screen")
    assert len(response) == 10
    assert all("figma_node_id" in node for node in response)
    assert all("node_type" in node for node in response)
    assert all("name" in node for node in response)

    # Check root node
    root = response[0]
    assert root["node_type"] == "FRAME"
    assert root["depth"] == 0
    assert "layout_mode" in root

    # Test with custom node count
    response_5 = make_mock_figma_response("Small Screen", 5)
    assert len(response_5) == 5

    # Test deterministic based on screen name
    response1 = make_mock_figma_response("Screen A")
    response2 = make_mock_figma_response("Screen A")
    assert response1[0]["figma_node_id"] == response2[0]["figma_node_id"]

    response3 = make_mock_figma_response("Screen B")
    assert response1[0]["figma_node_id"] != response3[0]["figma_node_id"]

    # Check for type-specific properties
    text_nodes = [n for n in response if n["node_type"] == "TEXT"]
    if text_nodes:
        assert all("font_family" in n for n in text_nodes)
        assert all("font_size" in n for n in text_nodes)
        assert all("text_content" in n for n in text_nodes)