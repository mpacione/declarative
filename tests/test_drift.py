"""Unit tests for drift detection functionality."""

import json
import pytest
import sqlite3
from typing import Dict, List, Any

from dd.drift import (
    detect_drift,
    detect_drift_readonly,
    compare_token_values,
    parse_figma_variables_for_drift,
    generate_drift_report,
    update_sync_statuses,
    normalize_value_for_comparison
)
from tests.fixtures import seed_post_curation


# Helper Functions
def _build_mock_figma_response(tokens: List[Dict[str, Any]], modify: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Build a mock figma_get_variables response from a list of token dicts.

    Args:
        tokens: List of token dicts with keys: name, type, value, mode (optional)
        modify: Optional dict mapping token_name to new value

    Returns:
        Mock response matching figma_get_variables shape
    """
    collections = []

    # Group tokens by collection
    collection_tokens = {}
    for token in tokens:
        collection = token.get("collection", "Default")
        if collection not in collection_tokens:
            collection_tokens[collection] = []
        collection_tokens[collection].append(token)

    # Build collections
    for collection_name, tokens_list in collection_tokens.items():
        variables = []
        modes = set()

        for token in tokens_list:
            mode_name = token.get("mode", "Default")
            modes.add(mode_name)

            # Apply modifications if specified
            value = token["value"]
            if modify and token["name"] in modify:
                value = modify[token["name"]]

            # Build variable structure
            variable = {
                "id": f"VariableID:{hash(token['name']) % 1000}:1",
                "name": token["name"].replace(".", "/"),  # Convert DTCG to Figma path
                "type": token["type"].upper() if token["type"] == "color" else "FLOAT",
                "values": {
                    mode_name: value
                }
            }
            variables.append(variable)

        collection = {
            "name": collection_name,
            "variables": variables,
            "modes": [{"id": f"mode_{m}", "name": m} for m in sorted(modes)]
        }
        collections.append(collection)

    return {"collections": collections}


def _set_figma_variable_ids(db: sqlite3.Connection, file_id: int):
    """Set figma_variable_id on all curated tokens to simulate export."""
    db.execute("""
        UPDATE tokens
        SET figma_variable_id = 'VariableID:' || id || ':1'
        WHERE tier = 'curated'
    """)
    db.commit()


# Value Normalization Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_normalize_color_case_insensitive():
    """Test that hex colors are normalized to uppercase."""
    assert normalize_value_for_comparison("#09090B", "color") == normalize_value_for_comparison("#09090b", "color")
    assert normalize_value_for_comparison("#09090B", "color") == "09090B"
    assert normalize_value_for_comparison("#09090b", "color") == "09090B"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_normalize_dimension_trailing_zero():
    """Test that dimension values normalize decimal representations."""
    assert normalize_value_for_comparison("16", "dimension") == normalize_value_for_comparison("16.0", "dimension")
    assert normalize_value_for_comparison("16", "dimension") == "16"
    assert normalize_value_for_comparison("16.0", "dimension") == "16"
    assert normalize_value_for_comparison("16.000", "dimension") == "16"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_normalize_font_family_quotes():
    """Test that font family quotes are stripped."""
    assert normalize_value_for_comparison('"Inter"', "fontFamily") == normalize_value_for_comparison("Inter", "fontFamily")
    assert normalize_value_for_comparison('"Inter"', "fontFamily") == "Inter"
    assert normalize_value_for_comparison("'Inter'", "fontFamily") == "Inter"
    assert normalize_value_for_comparison("Inter", "fontFamily") == "Inter"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_normalize_color_preserves_alpha():
    """Test that 8-digit hex preserves alpha — it's a distinct value."""
    assert normalize_value_for_comparison("#09090BFF", "color") == "09090BFF"
    assert normalize_value_for_comparison("#09090B", "color") == "09090B"
    # Different alpha = different value
    assert normalize_value_for_comparison("#09090BFF", "color") != normalize_value_for_comparison("#09090B", "color")
    assert normalize_value_for_comparison("#09090B80", "color") == "09090B80"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_normalize_whitespace():
    """Test that whitespace is stripped from values."""
    assert normalize_value_for_comparison("  16  ", "dimension") == normalize_value_for_comparison("16", "dimension")
    assert normalize_value_for_comparison("  16  ", "dimension") == "16"
    assert normalize_value_for_comparison("\t16\n", "dimension") == "16"
    assert normalize_value_for_comparison("  #09090B  ", "color") == "09090B"


# Parse Figma Response Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_parse_figma_response_basic():
    """Test parsing a basic Figma response with 1 collection, 1 mode, 2 variables."""
    response = {
        "collections": [{
            "name": "Colors",
            "modes": [{"id": "mode_1", "name": "Default"}],
            "variables": [
                {
                    "id": "VariableID:1:1",
                    "name": "color/primary",
                    "type": "COLOR",
                    "valuesByMode": {
                        "mode_1": "#09090B"
                    }
                },
                {
                    "id": "VariableID:1:2",
                    "name": "color/secondary",
                    "type": "COLOR",
                    "valuesByMode": {
                        "mode_1": "#18181B"
                    }
                }
            ]
        }]
    }

    parsed = parse_figma_variables_for_drift(response)
    assert len(parsed) == 2

    # Check first variable
    assert parsed[0]["variable_id"] == "VariableID:1:1"
    assert parsed[0]["name"] == "color/primary"
    assert parsed[0]["dtcg_name"] == "color.primary"
    assert parsed[0]["collection_name"] == "Colors"
    assert parsed[0]["values"] == {"Default": "#09090B"}

    # Check second variable
    assert parsed[1]["variable_id"] == "VariableID:1:2"
    assert parsed[1]["name"] == "color/secondary"
    assert parsed[1]["dtcg_name"] == "color.secondary"
    assert parsed[1]["values"] == {"Default": "#18181B"}


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_parse_figma_response_multimode():
    """Test parsing response with 2 modes."""
    response = {
        "collections": [{
            "name": "Colors",
            "modes": [
                {"id": "mode_1", "name": "Light"},
                {"id": "mode_2", "name": "Dark"}
            ],
            "variables": [
                {
                    "id": "VariableID:1:1",
                    "name": "color/primary",
                    "type": "COLOR",
                    "valuesByMode": {
                        "mode_1": "#09090B",
                        "mode_2": "#FFFFFF"
                    }
                }
            ]
        }]
    }

    parsed = parse_figma_variables_for_drift(response)
    assert len(parsed) == 1
    assert parsed[0]["values"] == {"Light": "#09090B", "Dark": "#FFFFFF"}


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_parse_figma_response_empty():
    """Test parsing empty/minimal response returns empty list without error."""
    # Empty dict
    assert parse_figma_variables_for_drift({}) == []

    # Empty collections
    assert parse_figma_variables_for_drift({"collections": []}) == []

    # Collection with no variables
    response = {
        "collections": [{
            "name": "Empty",
            "modes": [{"id": "mode_1", "name": "Default"}],
            "variables": []
        }]
    }
    assert parse_figma_variables_for_drift(response) == []


# Comparison Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_compare_all_synced(db):
    """Test comparison when all tokens are synced with matching values."""
    seed_post_curation(db)
    _set_figma_variable_ids(db, 1)

    # Build mock response with matching values
    mock_response = _build_mock_figma_response([
        {"name": "color.surface.primary", "type": "color", "value": "#09090B", "collection": "Colors"},
        {"name": "color.surface.secondary", "type": "color", "value": "#18181B", "collection": "Colors"},
        {"name": "color.border.default", "type": "color", "value": "#D4D4D8", "collection": "Colors"},
        {"name": "color.text.primary", "type": "color", "value": "#FFFFFF", "collection": "Colors"},
        {"name": "space.4", "type": "dimension", "value": "16", "collection": "Spacing"}
    ])

    parsed = parse_figma_variables_for_drift(mock_response)
    comparison = compare_token_values(db, 1, parsed)

    assert len(comparison["synced"]) == 5
    assert len(comparison["drifted"]) == 0
    assert len(comparison["pending"]) == 0
    assert len(comparison["figma_only"]) == 0
    assert len(comparison["code_only"]) == 0


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_compare_drifted(db):
    """Test comparison when one token value has drifted."""
    seed_post_curation(db)
    _set_figma_variable_ids(db, 1)

    # Build mock response with ONE changed value
    mock_response = _build_mock_figma_response([
        {"name": "color.surface.primary", "type": "color", "value": "#09090B", "collection": "Colors"},
        {"name": "color.surface.secondary", "type": "color", "value": "#18181B", "collection": "Colors"},
        {"name": "color.border.default", "type": "color", "value": "#D4D4D8", "collection": "Colors"},
        {"name": "color.text.primary", "type": "color", "value": "#FFFFFF", "collection": "Colors"},
        {"name": "space.4", "type": "dimension", "value": "16", "collection": "Spacing"}
    ], modify={"color.surface.primary": "#FF0000"})  # Changed value

    parsed = parse_figma_variables_for_drift(mock_response)
    comparison = compare_token_values(db, 1, parsed)

    assert len(comparison["synced"]) == 4
    assert len(comparison["drifted"]) == 1

    # Check drifted token details
    drifted = comparison["drifted"][0]
    assert drifted["name"] == "color.surface.primary"
    assert drifted["db_value"] == "#09090B"
    assert drifted["figma_value"] == "#FF0000"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_compare_pending(db):
    """Test comparison when tokens have no figma_variable_id (pending export)."""
    seed_post_curation(db)
    # Don't set figma_variable_ids - leave them as pending

    mock_response = _build_mock_figma_response([])  # Empty Figma response

    parsed = parse_figma_variables_for_drift(mock_response)
    comparison = compare_token_values(db, 1, parsed)

    assert len(comparison["pending"]) == 5  # All 5 tokens are pending
    assert len(comparison["synced"]) == 0
    assert len(comparison["drifted"]) == 0
    assert len(comparison["figma_only"]) == 0
    assert len(comparison["code_only"]) == 0


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_compare_figma_only(db):
    """Test comparison when Figma has variables not in DB."""
    seed_post_curation(db)
    _set_figma_variable_ids(db, 1)

    # Build mock response with extra variable
    mock_response = _build_mock_figma_response([
        {"name": "color.surface.primary", "type": "color", "value": "#09090B", "collection": "Colors"},
        {"name": "color.surface.secondary", "type": "color", "value": "#18181B", "collection": "Colors"},
        {"name": "color.border.default", "type": "color", "value": "#D4D4D8", "collection": "Colors"},
        {"name": "color.text.primary", "type": "color", "value": "#FFFFFF", "collection": "Colors"},
        {"name": "space.4", "type": "dimension", "value": "16", "collection": "Spacing"},
        {"name": "color.brand.new", "type": "color", "value": "#FF5500", "collection": "Colors"}  # Not in DB
    ])

    parsed = parse_figma_variables_for_drift(mock_response)
    comparison = compare_token_values(db, 1, parsed)

    assert len(comparison["synced"]) == 5
    assert len(comparison["figma_only"]) == 1

    # Check figma_only details
    figma_only = comparison["figma_only"][0]
    assert figma_only["name"] == "color.brand.new"
    assert figma_only["values"] == {"Default": "#FF5500"}


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_compare_mixed_statuses(db):
    """Test comparison with mixed statuses: synced, drifted, pending."""
    seed_post_curation(db)

    # Set figma_variable_id only on some tokens
    db.execute("""
        UPDATE tokens
        SET figma_variable_id = 'VariableID:' || id || ':1'
        WHERE id IN (1, 2)  -- Only primary and secondary colors
    """)
    db.commit()

    # Build mock response with mixed conditions
    mock_response = _build_mock_figma_response([
        {"name": "color.surface.primary", "type": "color", "value": "#09090B", "collection": "Colors"},  # Synced
        {"name": "color.surface.secondary", "type": "color", "value": "#FF0000", "collection": "Colors"},  # Drifted
        {"name": "color.brand.extra", "type": "color", "value": "#00FF00", "collection": "Colors"}  # Figma-only
    ])

    parsed = parse_figma_variables_for_drift(mock_response)
    comparison = compare_token_values(db, 1, parsed)

    assert len(comparison["synced"]) == 1  # primary color
    assert len(comparison["drifted"]) == 1  # secondary color
    assert len(comparison["pending"]) == 3  # border, text, space.4 (no figma_variable_id)
    assert len(comparison["figma_only"]) == 1  # brand.extra
    assert len(comparison["code_only"]) == 0


# Update Sync Status Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_update_sync_synced(db):
    """Test updating sync status to synced."""
    seed_post_curation(db)
    _set_figma_variable_ids(db, 1)

    # Build comparison with synced tokens
    comparison = {
        "synced": [
            {"token_id": 1, "name": "color.surface.primary", "collection_name": "Colors"},
            {"token_id": 2, "name": "color.surface.secondary", "collection_name": "Colors"}
        ],
        "drifted": [],
        "pending": [],
        "figma_only": [],
        "code_only": []
    }

    counts = update_sync_statuses(db, 1, comparison)

    assert counts["synced"] == 2
    assert counts["updated"] == 2

    # Verify DB updated
    cursor = db.execute("SELECT sync_status FROM tokens WHERE id IN (1, 2)")
    statuses = [row["sync_status"] for row in cursor]
    assert all(status == "synced" for status in statuses)


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_update_sync_drifted(db):
    """Test updating sync status to drifted."""
    seed_post_curation(db)
    _set_figma_variable_ids(db, 1)

    # Build comparison with drifted tokens
    comparison = {
        "synced": [],
        "drifted": [
            {"token_id": 1, "name": "color.surface.primary", "collection_name": "Colors",
             "mode": "Default", "db_value": "#09090B", "figma_value": "#FF0000"}
        ],
        "pending": [],
        "figma_only": [],
        "code_only": []
    }

    counts = update_sync_statuses(db, 1, comparison)

    assert counts["drifted"] == 1
    assert counts["updated"] == 1

    # Verify DB updated
    cursor = db.execute("SELECT sync_status FROM tokens WHERE id = 1")
    status = cursor.fetchone()["sync_status"]
    assert status == "drifted"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_update_returns_counts(db):
    """Test that update_sync_statuses returns correct counts per status."""
    seed_post_curation(db)
    _set_figma_variable_ids(db, 1)

    # Build mixed comparison
    comparison = {
        "synced": [
            {"token_id": 1, "name": "color.surface.primary", "collection_name": "Colors"},
            {"token_id": 2, "name": "color.surface.secondary", "collection_name": "Colors"}
        ],
        "drifted": [
            {"token_id": 3, "name": "color.border.default", "collection_name": "Colors",
             "mode": "Default", "db_value": "#D4D4D8", "figma_value": "#FF0000"}
        ],
        "pending": [
            {"token_id": 4, "name": "color.text.primary", "collection_name": "Colors"}
        ],
        "figma_only": [
            {"name": "color.brand.new", "variable_id": "VariableID:999:1",
             "collection_name": "Colors", "values": {"Default": "#FF5500"}}
        ],
        "code_only": []
    }

    counts = update_sync_statuses(db, 1, comparison)

    assert counts["synced"] == 2
    assert counts["drifted"] == 1
    assert counts["pending"] == 1
    assert counts["figma_only"] == 1
    assert counts["code_only"] == 0
    assert counts["updated"] == 4  # synced + drifted + pending


# Full Drift Detection Tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_detect_drift_readonly_no_update(db):
    """Test that detect_drift_readonly does NOT modify DB sync_status."""
    seed_post_curation(db)

    # Check initial status (should be pending)
    cursor = db.execute("SELECT sync_status FROM tokens WHERE id = 1")
    initial_status = cursor.fetchone()["sync_status"]
    assert initial_status == "pending"

    # Run readonly drift detection
    mock_response = _build_mock_figma_response([
        {"name": "color.surface.primary", "type": "color", "value": "#09090B", "collection": "Colors"}
    ])

    result = detect_drift_readonly(db, 1, mock_response)

    # Verify status NOT changed
    cursor = db.execute("SELECT sync_status FROM tokens WHERE id = 1")
    final_status = cursor.fetchone()["sync_status"]
    assert final_status == "pending"  # Still pending, not updated

    # Result should still contain comparison
    assert "pending" in result
    assert len(result["pending"]) > 0


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_detect_drift_updates_db(db):
    """Test that detect_drift DOES update DB sync_status."""
    seed_post_curation(db)
    _set_figma_variable_ids(db, 1)

    # Build mock response with matching values
    mock_response = _build_mock_figma_response([
        {"name": "color.surface.primary", "type": "color", "value": "#09090B", "collection": "Colors"},
        {"name": "color.surface.secondary", "type": "color", "value": "#18181B", "collection": "Colors"},
        {"name": "color.border.default", "type": "color", "value": "#D4D4D8", "collection": "Colors"},
        {"name": "color.text.primary", "type": "color", "value": "#FFFFFF", "collection": "Colors"},
        {"name": "space.4", "type": "dimension", "value": "16", "collection": "Spacing"}
    ])

    result = detect_drift(db, 1, mock_response)

    # Verify DB updated to synced
    cursor = db.execute("SELECT sync_status FROM tokens WHERE tier = 'curated'")
    statuses = [row["sync_status"] for row in cursor]
    assert all(status == "synced" for status in statuses)

    # Check result structure
    assert "comparison" in result
    assert "updates" in result
    assert "report" in result
    assert result["updates"]["synced"] == 5


# Drift Report Test
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_generate_drift_report(db):
    """Test generating drift report with mix of statuses."""
    seed_post_curation(db)

    # Set up mixed statuses
    db.execute("UPDATE tokens SET sync_status = 'synced' WHERE id = 1")
    db.execute("UPDATE tokens SET sync_status = 'drifted' WHERE id = 2")
    db.execute("UPDATE tokens SET sync_status = 'pending' WHERE id IN (3, 4)")
    db.execute("UPDATE tokens SET sync_status = 'code_only' WHERE id = 5")
    db.commit()

    report = generate_drift_report(db, 1)

    # Check summary counts
    assert report["summary"]["synced"] == 1
    assert report["summary"]["drifted"] == 1
    assert report["summary"]["pending"] == 2
    assert report["summary"]["code_only"] == 1
    assert report["summary"]["figma_only"] == 0

    # Check drifted_tokens list
    assert len(report["drifted_tokens"]) == 1
    drifted = report["drifted_tokens"][0]
    assert drifted["token_name"] == "color.surface.secondary"
    assert drifted["db_value"] == "#18181B"

    # Check pending_tokens list
    assert len(report["pending_tokens"]) == 2
    pending_names = [t["token_name"] for t in report["pending_tokens"]]
    assert "color.border.default" in pending_names


# ---------------------------------------------------------------------------
# normalize_value_for_comparison edge cases
# ---------------------------------------------------------------------------

class TestNormalizeValueForComparison:
    """Cover edge cases in value normalization that cause false mismatch positives."""

    def test_dimension_json_lineheight_pixels(self):
        """JSON lineHeight like {"value":24,"unit":"PIXELS"} should normalize to "24"."""
        result = normalize_value_for_comparison('{"value":24,"unit":"PIXELS"}', "dimension")
        assert result == "24"

    def test_dimension_json_lineheight_auto(self):
        """JSON lineHeight {"unit":"AUTO"} should normalize to "AUTO"."""
        result = normalize_value_for_comparison('{"unit":"AUTO"}', "dimension")
        assert result == "AUTO"

    def test_dimension_json_letter_spacing(self):
        """JSON letterSpacing like {"value":-0.5,"unit":"PIXELS"} should normalize to "-0.5"."""
        result = normalize_value_for_comparison('{"value":-0.5,"unit":"PIXELS"}', "dimension")
        assert result == "-0.5"

    def test_dimension_float_noise_rounds_to_integer(self):
        """Figma float noise like 10.000000149 should match "10"."""
        result = normalize_value_for_comparison("10.000000149011612", "dimension")
        expected = normalize_value_for_comparison("10", "dimension")
        assert result == expected

    def test_dimension_float_noise_rounds_fractional(self):
        """Figma float noise like 24.000001 should match "24"."""
        result = normalize_value_for_comparison("24.000001", "dimension")
        expected = normalize_value_for_comparison("24", "dimension")
        assert result == expected

    def test_dimension_genuine_fractional_preserved(self):
        """Genuinely different values like 10 and 10.5 should NOT match."""
        result_10 = normalize_value_for_comparison("10", "dimension")
        result_105 = normalize_value_for_comparison("10.5", "dimension")
        assert result_10 != result_105

    def test_number_float_noise(self):
        """Float noise in number type (fontWeight) should also be handled."""
        result = normalize_value_for_comparison("400.0000001", "number")
        expected = normalize_value_for_comparison("400", "number")
        assert result == expected

    def test_color_unchanged(self):
        """Color normalization should be unaffected by these changes."""
        assert normalize_value_for_comparison("#09090B", "color") == "09090B"
        assert normalize_value_for_comparison("#09090B0D", "color") == "09090B0D"

    def test_fontfamily_unchanged(self):
        """fontFamily normalization should be unaffected."""
        assert normalize_value_for_comparison('"Inter"', "fontFamily") == "Inter"