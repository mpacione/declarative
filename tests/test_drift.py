"""Tests for drift detection module."""

import pytest
import sqlite3
from typing import Any, Dict

from dd.drift import (
    detect_drift,
    detect_drift_readonly,
    compare_token_values,
    parse_figma_variables_for_drift,
    generate_drift_report,
    update_sync_statuses,
    normalize_value_for_comparison
)


def create_test_data(conn: sqlite3.Connection) -> int:
    """Create test tokens and related data.

    Returns:
        File ID for the test data
    """
    # Create file
    cursor = conn.execute("""
        INSERT INTO files (file_key, name, extracted_at)
        VALUES ('test_file_key_123', 'Test File', '2024-01-01T00:00:00Z')
    """)
    file_id = cursor.lastrowid

    # Create collections
    conn.execute("""
        INSERT INTO token_collections (id, file_id, figma_id, name)
        VALUES
        (1, ?, 'VariableCollectionId:1:1', 'Colors'),
        (2, ?, 'VariableCollectionId:1:2', 'Spacing')
    """, (file_id, file_id))

    # Create modes
    conn.execute("""
        INSERT INTO token_modes (id, collection_id, figma_mode_id, name, is_default)
        VALUES
        (1, 1, '1:0', 'Light', 1),
        (2, 1, '1:1', 'Dark', 0),
        (3, 2, '2:0', 'Default', 1)
    """)

    # Create tokens with different sync statuses
    conn.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier, figma_variable_id, sync_status)
        VALUES
        (1, 1, 'color.surface.primary', 'color', 'curated', 'VariableID:123:456', 'synced'),
        (2, 1, 'color.surface.secondary', 'color', 'curated', 'VariableID:123:457', 'drifted'),
        (3, 1, 'color.text.primary', 'color', 'curated', NULL, 'pending'),
        (4, 2, 'spacing.xs', 'dimension', 'curated', 'VariableID:123:458', 'synced'),
        (5, 2, 'spacing.sm', 'dimension', 'aliased', NULL, 'pending'),
        (6, 1, 'color.background', 'color', 'curated', 'VariableID:123:459', 'code_only')
    """)

    # Create token values
    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES
        -- Synced token (color.surface.primary)
        (1, 1, '#09090B', '#09090B'),
        (1, 2, '#FAFAFA', '#FAFAFA'),
        -- Drifted token (color.surface.secondary)
        (2, 1, '#71717A', '#71717A'),
        (2, 2, '#A1A1AA', '#A1A1AA'),
        -- Pending token (color.text.primary)
        (3, 1, '#000000', '#000000'),
        (3, 2, '#FFFFFF', '#FFFFFF'),
        -- Synced spacing
        (4, 3, '4px', '4'),
        -- Pending spacing
        (5, 3, '8px', '8'),
        -- Code-only token
        (6, 1, '#F5F5F5', '#F5F5F5'),
        (6, 2, '#1A1A1A', '#1A1A1A')
    """)

    # Add code mapping for code_only token
    conn.execute("""
        INSERT INTO code_mappings (token_id, target, identifier, file_path)
        VALUES (6, 'css', '--color-background', 'styles.css')
    """)

    conn.commit()
    return file_id


def test_normalize_value_for_comparison():
    """Test value normalization for drift comparison."""
    # Color normalization
    assert normalize_value_for_comparison("#09090B", "color") == "09090B"
    assert normalize_value_for_comparison("#09090b", "color") == "09090B"
    assert normalize_value_for_comparison("09090B", "color") == "09090B"
    assert normalize_value_for_comparison("#09090BFF", "color") == "09090B"
    assert normalize_value_for_comparison("#09090BA0", "color") == "09090BA0"

    # Dimension normalization
    assert normalize_value_for_comparison("16px", "dimension") == "16"
    assert normalize_value_for_comparison("16", "dimension") == "16"
    assert normalize_value_for_comparison("16.0", "dimension") == "16"
    assert normalize_value_for_comparison("16.5px", "dimension") == "16.5"
    assert normalize_value_for_comparison(" 16 px ", "dimension") == "16"

    # Font family normalization
    assert normalize_value_for_comparison('"Inter"', "fontFamily") == "Inter"
    assert normalize_value_for_comparison("'Inter'", "fontFamily") == "Inter"
    assert normalize_value_for_comparison("Inter", "fontFamily") == "Inter"
    assert normalize_value_for_comparison(' "Inter" ', "fontFamily") == "Inter"

    # Other types - minimal normalization
    assert normalize_value_for_comparison(" 500 ", "fontWeight") == "500"
    assert normalize_value_for_comparison("normal", "fontStyle") == "normal"


def test_parse_figma_variables_for_drift():
    """Test parsing various Figma variable response formats."""
    # Standard format with collections
    response1 = {
        "collections": [
            {
                "id": "VariableCollectionId:1:1",
                "name": "Colors",
                "modes": [
                    {"id": "1:0", "name": "Light"},
                    {"id": "1:1", "name": "Dark"}
                ],
                "variables": [
                    {
                        "id": "VariableID:123:456",
                        "name": "color/surface/primary",
                        "valuesByMode": {
                            "1:0": "#09090B",
                            "1:1": "#FAFAFA"
                        }
                    }
                ]
            }
        ]
    }

    parsed = parse_figma_variables_for_drift(response1)
    assert len(parsed) == 1
    assert parsed[0]["variable_id"] == "VariableID:123:456"
    assert parsed[0]["name"] == "color/surface/primary"
    assert parsed[0]["dtcg_name"] == "color.surface.primary"
    assert parsed[0]["collection_name"] == "Colors"
    assert parsed[0]["values"] == {"Light": "#09090B", "Dark": "#FAFAFA"}

    # Flat variables format
    response2 = {
        "variables": [
            {
                "id": "VariableID:123:456",
                "name": "spacing/xs",
                "value": "4px"
            }
        ]
    }

    parsed = parse_figma_variables_for_drift(response2)
    assert len(parsed) == 1
    assert parsed[0]["dtcg_name"] == "spacing.xs"
    assert parsed[0]["values"] == {"Default": "4px"}

    # Direct list of variables
    response3 = [
        {
            "id": "VariableID:123:456",
            "name": "color/text/primary",
            "values": {"Light": "#000000", "Dark": "#FFFFFF"}
        }
    ]

    parsed = parse_figma_variables_for_drift(response3)
    assert len(parsed) == 1
    assert parsed[0]["dtcg_name"] == "color.text.primary"
    assert parsed[0]["values"] == {"Light": "#000000", "Dark": "#FFFFFF"}

    # Empty response
    response4 = {}
    parsed = parse_figma_variables_for_drift(response4)
    assert parsed == []

    # Nested value objects
    response5 = {
        "collections": [
            {
                "name": "Typography",
                "variables": [
                    {
                        "id": "VariableID:123:456",
                        "name": "font/size/base",
                        "values": {
                            "Default": {"value": "16px"}
                        }
                    }
                ]
            }
        ]
    }

    parsed = parse_figma_variables_for_drift(response5)
    assert len(parsed) == 1
    assert parsed[0]["values"] == {"Default": "16px"}


def test_compare_token_values(db):
    """Test comparing DB tokens with Figma variables."""
    conn = db
    file_id = create_test_data(conn)

    # Simulate Figma variables response
    figma_variables = [
        {
            "variable_id": "VariableID:123:456",
            "name": "color/surface/primary",
            "dtcg_name": "color.surface.primary",
            "collection_name": "Colors",
            "values": {"Light": "#09090B", "Dark": "#FAFAFA"}
        },
        {
            "variable_id": "VariableID:123:457",
            "name": "color/surface/secondary",
            "dtcg_name": "color.surface.secondary",
            "collection_name": "Colors",
            "values": {"Light": "#71717B", "Dark": "#A1A1AA"}  # Different from DB
        },
        {
            "variable_id": "VariableID:123:458",
            "name": "spacing/xs",
            "dtcg_name": "spacing.xs",
            "collection_name": "Spacing",
            "values": {"Default": "4"}
        },
        {
            "variable_id": "VariableID:999:999",
            "name": "color/brand/new",
            "dtcg_name": "color.brand.new",
            "collection_name": "Colors",
            "values": {"Light": "#FF0000", "Dark": "#00FF00"}
        }
    ]

    comparison = compare_token_values(conn, file_id, figma_variables)

    # Check synced tokens
    assert len(comparison["synced"]) == 2
    synced_names = {t["name"] for t in comparison["synced"]}
    assert "color.surface.primary" in synced_names
    assert "spacing.xs" in synced_names

    # Check drifted tokens - only Light mode differs
    assert len(comparison["drifted"]) == 1  # One mode differs
    drifted = comparison["drifted"][0]
    assert drifted["name"] == "color.surface.secondary"
    assert drifted["mode"] == "Light"
    assert drifted["db_value"] == "#71717A"
    assert drifted["figma_value"] == "#71717B"

    # Check pending tokens
    assert len(comparison["pending"]) == 2
    pending_names = {t["name"] for t in comparison["pending"]}
    assert "color.text.primary" in pending_names
    assert "spacing.sm" in pending_names

    # Check figma_only tokens
    assert len(comparison["figma_only"]) == 1
    assert comparison["figma_only"][0]["name"] == "color.brand.new"

    # Check code_only tokens
    assert len(comparison["code_only"]) == 1
    assert comparison["code_only"][0]["name"] == "color.background"


def test_update_sync_statuses(db):
    """Test updating sync statuses in the database."""
    conn = db
    file_id = create_test_data(conn)

    # Create comparison results
    comparison = {
        "synced": [{"token_id": 1, "name": "color.surface.primary"}],
        "drifted": [{"token_id": 2, "name": "color.surface.secondary", "mode": "Light",
                    "db_value": "#71717A", "figma_value": "#71717B"}],
        "pending": [{"token_id": 3, "name": "color.text.primary"}],
        "code_only": [{"token_id": 6, "name": "color.background"}],
        "figma_only": [{"name": "color.brand.new", "variable_id": "VariableID:999:999"}]
    }

    counts = update_sync_statuses(conn, file_id, comparison)

    assert counts["updated"] == 4
    assert counts["synced"] == 1
    assert counts["drifted"] == 1
    assert counts["pending"] == 1
    assert counts["code_only"] == 1
    assert counts["figma_only"] == 1

    # Verify statuses were updated
    cursor = conn.execute("SELECT id, sync_status FROM tokens WHERE id IN (1, 2, 3, 6)")
    statuses = {row["id"]: row["sync_status"] for row in cursor}
    assert statuses[1] == "synced"
    assert statuses[2] == "drifted"
    assert statuses[3] == "pending"
    assert statuses[6] == "code_only"


def test_generate_drift_report(db):
    """Test generating drift report."""
    conn = db
    file_id = create_test_data(conn)

    report = generate_drift_report(conn, file_id)

    # Check summary counts
    assert report["summary"]["synced"] == 2  # tokens 1 and 4
    assert report["summary"]["drifted"] == 1  # token 2
    assert report["summary"]["pending"] == 2  # tokens 3 and 5
    assert report["summary"]["code_only"] == 1  # token 6

    # Check drifted tokens details - one entry per mode
    # Note: color.surface.secondary has 2 modes, so 2 entries in report
    assert len(report["drifted_tokens"]) == 2  # One token with 2 modes
    drifted_names = {t["token_name"] for t in report["drifted_tokens"]}
    assert "color.surface.secondary" in drifted_names
    assert all("mode_name" in t for t in report["drifted_tokens"])
    assert all("db_value" in t for t in report["drifted_tokens"])

    # Check pending tokens
    assert len(report["pending_tokens"]) == 2
    pending_names = {t["token_name"] for t in report["pending_tokens"]}
    assert "color.text.primary" in pending_names
    assert "spacing.sm" in pending_names


def test_detect_drift_readonly(db):
    """Test read-only drift detection."""
    conn = db
    file_id = create_test_data(conn)

    # Simulate Figma response
    figma_response = {
        "collections": [
            {
                "id": "VariableCollectionId:1:1",
                "name": "Colors",
                "modes": [
                    {"id": "1:0", "name": "Light"},
                    {"id": "1:1", "name": "Dark"}
                ],
                "variables": [
                    {
                        "id": "VariableID:123:456",
                        "name": "color/surface/primary",
                        "valuesByMode": {
                            "1:0": "#09090b",  # Lowercase to test normalization
                            "1:1": "#fafafa"
                        }
                    }
                ]
            }
        ]
    }

    # Get initial sync status
    cursor = conn.execute("SELECT sync_status FROM tokens WHERE id = 1")
    initial_status = cursor.fetchone()["sync_status"]

    # Run read-only detection
    comparison = detect_drift_readonly(conn, file_id, figma_response)

    # Verify comparison results
    assert "synced" in comparison
    assert "drifted" in comparison
    assert "pending" in comparison

    # Verify no DB changes were made
    cursor = conn.execute("SELECT sync_status FROM tokens WHERE id = 1")
    final_status = cursor.fetchone()["sync_status"]
    assert final_status == initial_status  # Status unchanged


def test_detect_drift_full(db):
    """Test full drift detection with status updates."""
    conn = db
    file_id = create_test_data(conn)

    # Simulate comprehensive Figma response
    figma_response = {
        "collections": [
            {
                "id": "VariableCollectionId:1:1",
                "name": "Colors",
                "modes": [
                    {"id": "1:0", "name": "Light"},
                    {"id": "1:1", "name": "Dark"}
                ],
                "variables": [
                    {
                        "id": "VariableID:123:456",
                        "name": "color/surface/primary",
                        "valuesByMode": {
                            "1:0": "#09090B",
                            "1:1": "#FAFAFA"
                        }
                    },
                    {
                        "id": "VariableID:123:457",
                        "name": "color/surface/secondary",
                        "valuesByMode": {
                            "1:0": "#71717C",  # Different from DB
                            "1:1": "#A1A1AB"   # Different from DB
                        }
                    }
                ]
            },
            {
                "id": "VariableCollectionId:1:2",
                "name": "Spacing",
                "modes": [
                    {"id": "2:0", "name": "Default"}
                ],
                "variables": [
                    {
                        "id": "VariableID:123:458",
                        "name": "spacing/xs",
                        "valuesByMode": {
                            "2:0": "4px"  # Will normalize to "4"
                        }
                    }
                ]
            }
        ]
    }

    result = detect_drift(conn, file_id, figma_response)

    # Check comparison
    assert "comparison" in result
    assert len(result["comparison"]["synced"]) > 0
    assert len(result["comparison"]["drifted"]) > 0

    # Check updates
    assert "updates" in result
    assert result["updates"]["updated"] > 0

    # Check report
    assert "report" in result
    assert "summary" in result["report"]
    assert result["report"]["summary"]["drifted"] > 0

    # Verify DB was updated
    cursor = conn.execute("""
        SELECT sync_status FROM tokens WHERE name = 'color.surface.secondary'
    """)
    status = cursor.fetchone()["sync_status"]
    assert status == "drifted"


def test_drift_with_missing_modes(db):
    """Test drift detection when Figma is missing some modes."""
    conn = db
    file_id = create_test_data(conn)

    # Figma response missing Dark mode for a token
    figma_response = {
        "collections": [
            {
                "name": "Colors",
                "modes": [
                    {"id": "1:0", "name": "Light"}
                ],
                "variables": [
                    {
                        "id": "VariableID:123:456",
                        "name": "color/surface/primary",
                        "valuesByMode": {
                            "1:0": "#09090B"
                            # Missing Dark mode value
                        }
                    }
                ]
            }
        ]
    }

    comparison = detect_drift_readonly(conn, file_id, figma_response)

    # Should detect drift due to missing mode
    assert len(comparison["drifted"]) > 0
    drifted = [d for d in comparison["drifted"] if d["name"] == "color.surface.primary"]
    assert any(d["figma_value"] == "missing" for d in drifted)


def test_drift_with_case_variations(db):
    """Test that case variations in hex colors don't cause false drift."""
    conn = db
    file_id = create_test_data(conn)

    # Figma response with different case hex values
    figma_response = {
        "collections": [
            {
                "name": "Colors",
                "modes": [
                    {"id": "1:0", "name": "Light"},
                    {"id": "1:1", "name": "Dark"}
                ],
                "variables": [
                    {
                        "id": "VariableID:123:456",
                        "name": "color/surface/primary",
                        "valuesByMode": {
                            "1:0": "#09090b",  # Lowercase
                            "1:1": "#fAfAfA"   # Mixed case
                        }
                    }
                ]
            }
        ]
    }

    comparison = detect_drift_readonly(conn, file_id, figma_response)

    # Should be synced despite case differences
    synced = [s for s in comparison["synced"] if s["name"] == "color.surface.primary"]
    assert len(synced) == 1


def test_v_drift_report_view(db):
    """Test that v_drift_report view returns correct data."""
    conn = db
    file_id = create_test_data(conn)

    # Query the view directly
    cursor = conn.execute("""
        SELECT token_name, sync_status, collection_name
        FROM v_drift_report
        ORDER BY sync_status, token_name
    """)

    results = list(cursor)
    assert len(results) > 0

    # Group by sync status
    by_status = {}
    for row in results:
        status = row["sync_status"]
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(row["token_name"])

    # Check expected statuses are present
    assert "pending" in by_status
    assert "drifted" in by_status
    assert "code_only" in by_status

    # Verify specific tokens
    assert "color.text.primary" in by_status["pending"]
    assert "color.surface.secondary" in by_status["drifted"]
    assert "color.background" in by_status["code_only"]