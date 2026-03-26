"""Integration test for drift detection with realistic Figma data."""

import sqlite3
import pytest

from dd.drift import detect_drift, detect_drift_readonly
from tests.fixtures import seed_post_curation


def test_drift_detection_end_to_end(db):
    """Test drift detection with a realistic workflow."""
    # Setup DB with curated tokens
    conn = seed_post_curation(db)

    # Get file ID
    cursor = conn.execute("SELECT id FROM files LIMIT 1")
    file_id = cursor.fetchone()["id"]

    # Create a realistic Figma response (simulating what MCP would return)
    figma_response = {
        "collections": [
            {
                "id": "VariableCollectionId:1:1",
                "name": "Brand Colors",
                "modes": [
                    {"id": "1:0", "name": "light"},
                    {"id": "1:1", "name": "dark"}
                ],
                "variables": [
                    {
                        "id": "VariableID:100:1",
                        "name": "color/surface/primary",
                        "valuesByMode": {
                            "1:0": "#09090b",  # Lowercase to test normalization
                            "1:1": "#fafafa"
                        }
                    },
                    {
                        "id": "VariableID:100:2",
                        "name": "color/surface/secondary",
                        "valuesByMode": {
                            "1:0": "#71717A",  # Matches DB
                            "1:1": "#A1A1AA"   # Matches DB
                        }
                    },
                    {
                        "id": "VariableID:100:3",
                        "name": "color/brand/new",  # Not in DB
                        "valuesByMode": {
                            "1:0": "#FF0000",
                            "1:1": "#00FF00"
                        }
                    }
                ]
            }
        ]
    }

    # First, run read-only detection
    comparison = detect_drift_readonly(conn, file_id, figma_response)

    # Verify read-only results
    assert "synced" in comparison
    assert "drifted" in comparison
    assert "pending" in comparison
    assert "figma_only" in comparison
    assert "code_only" in comparison

    # Check that figma_only includes the new variable
    figma_only_names = {v["name"] for v in comparison["figma_only"]}
    assert "color.brand.new" in figma_only_names

    # Now run full detection with updates
    result = detect_drift(conn, file_id, figma_response)

    # Verify full results structure
    assert "comparison" in result
    assert "updates" in result
    assert "report" in result

    # Verify updates were applied
    assert result["updates"]["updated"] > 0

    # Check that sync statuses were updated in DB
    cursor = conn.execute("""
        SELECT sync_status, COUNT(*) as count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = ?
        GROUP BY sync_status
    """, (file_id,))

    statuses = {row["sync_status"]: row["count"] for row in cursor}

    # Should have some tokens in various states
    assert "pending" in statuses or "synced" in statuses or "drifted" in statuses

    # Verify drift report
    report = result["report"]
    assert "summary" in report
    assert "drifted_tokens" in report
    assert "pending_tokens" in report


def test_drift_normalization_prevents_false_positives(db):
    """Test that value normalization prevents false drift reports."""
    conn = db

    # Create minimal test data with various formats
    cursor = conn.execute("""
        INSERT INTO files (file_key, name) VALUES ('test', 'Test')
    """)
    file_id = cursor.lastrowid

    conn.execute("""
        INSERT INTO token_collections (id, file_id, name)
        VALUES (1, ?, 'Test')
    """, (file_id,))

    conn.execute("""
        INSERT INTO token_modes (id, collection_id, name, is_default)
        VALUES (1, 1, 'Default', 1)
    """)

    # Create tokens with values that should normalize to same
    conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id, sync_status)
        VALUES
        (1, 'color.test', 'color', 'curated', 'VAR1', 'synced'),
        (1, 'spacing.test', 'dimension', 'curated', 'VAR2', 'synced'),
        (1, 'font.test', 'fontFamily', 'curated', 'VAR3', 'synced')
    """)

    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES
        (1, 1, '#09090B', '#09090B'),
        (2, 1, '16', '16'),
        (3, 1, 'Inter', 'Inter')
    """)

    conn.commit()

    # Figma response with different formats that should normalize to same
    figma_response = {
        "collections": [
            {
                "name": "Test",
                "variables": [
                    {
                        "id": "VAR1",
                        "name": "color/test",
                        "values": {"Default": "#09090b"}  # Lowercase
                    },
                    {
                        "id": "VAR2",
                        "name": "spacing/test",
                        "values": {"Default": "16.0px"}  # With .0 and px
                    },
                    {
                        "id": "VAR3",
                        "name": "font/test",
                        "values": {"Default": '"Inter"'}  # With quotes
                    }
                ]
            }
        ]
    }

    comparison = detect_drift_readonly(conn, file_id, figma_response)

    # All should be synced despite format differences
    assert len(comparison["synced"]) == 3
    assert len(comparison["drifted"]) == 0

    synced_names = {t["name"] for t in comparison["synced"]}
    assert "color.test" in synced_names
    assert "spacing.test" in synced_names
    assert "font.test" in synced_names