"""Unit tests for validation checks and export readiness."""

import json
import pytest

from dd.validate import (
    check_mode_completeness,
    check_name_dtcg_compliant,
    check_orphan_tokens,
    check_binding_coverage,
    check_alias_targets_curated,
    check_name_uniqueness,
    check_value_format,
    run_validation,
    is_export_ready,
)
from tests.fixtures import seed_post_clustering, seed_post_curation


# Validation check tests

@pytest.mark.unit
def test_check_mode_completeness_pass(db):
    """Test mode completeness with all values present."""
    seed_post_curation(db)

    # All tokens have values for all modes (only one mode in seed data)
    issues = check_mode_completeness(db, file_id=1)
    assert len(issues) == 0


@pytest.mark.unit
def test_check_mode_completeness_fail(db):
    """Test mode completeness detection with missing values."""
    seed_post_curation(db)

    # Add a second mode without corresponding token_values
    db.execute("""
        INSERT INTO token_modes (id, collection_id, name, is_default)
        VALUES (10, 1, 'Dark', 0)
    """)
    db.commit()

    issues = check_mode_completeness(db, file_id=1)
    assert len(issues) > 0

    for issue in issues:
        assert issue["severity"] == "error"
        assert "Dark" in issue["message"]
        assert issue["check_name"] == "mode_completeness"


@pytest.mark.unit
def test_check_name_dtcg_valid(db):
    """Test DTCG name validation with valid names."""
    seed_post_curation(db)

    # All seeded tokens have valid DTCG names
    issues = check_name_dtcg_compliant(db, file_id=1)
    assert len(issues) == 0


@pytest.mark.unit
def test_check_name_dtcg_invalid(db):
    """Test DTCG name validation with invalid name."""
    seed_post_curation(db)

    # Insert token with invalid name
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier)
        VALUES (100, 1, 'Invalid Name', 'color', 'extracted')
    """)
    db.commit()

    issues = check_name_dtcg_compliant(db, file_id=1)
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert "Invalid Name" in issues[0]["message"]
    assert "DTCG" in issues[0]["message"]


@pytest.mark.unit
def test_check_name_dtcg_allows_numeric(db):
    """Test that numeric segments are allowed in DTCG names."""
    seed_post_curation(db)

    # space.4 already exists in the seed data
    issues = check_name_dtcg_compliant(db, file_id=1)
    assert len(issues) == 0

    # Also test another numeric pattern
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier)
        VALUES (100, 2, 'space.4.5', 'dimension', 'extracted')
    """)
    db.commit()

    issues = check_name_dtcg_compliant(db, file_id=1)
    assert len(issues) == 0


@pytest.mark.unit
def test_check_orphan_tokens_none(db):
    """Test orphan detection when all tokens have bindings."""
    seed_post_curation(db)

    # All seeded tokens (except space.4) have bindings
    issues = check_orphan_tokens(db, file_id=1)

    # Token 5 (space.4) has no bindings, so it's an orphan
    orphan_issues = [i for i in issues if i["severity"] == "warning"]
    assert len(orphan_issues) == 1
    assert "space.4" in orphan_issues[0]["message"]


@pytest.mark.unit
def test_check_orphan_tokens_found(db):
    """Test orphan detection with tokens without bindings."""
    seed_post_curation(db)

    # Insert token with no bindings
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier)
        VALUES (100, 1, 'color.orphan', 'color', 'extracted')
    """)
    db.commit()

    issues = check_orphan_tokens(db, file_id=1)

    # Should find space.4 and color.orphan as orphans
    orphan_names = []
    for issue in issues:
        if issue["severity"] == "warning":
            orphan_names.append(issue["message"])

    assert any("color.orphan" in msg for msg in orphan_names)


@pytest.mark.unit
def test_check_binding_coverage(db):
    """Test binding coverage calculation."""
    seed_post_curation(db)

    issues = check_binding_coverage(db, file_id=1)
    assert len(issues) == 1
    assert issues[0]["severity"] == "info"
    assert issues[0]["check_name"] == "binding_coverage"
    assert "%" in issues[0]["message"]  # Contains percentage


@pytest.mark.unit
def test_check_alias_targets_curated_pass(db):
    """Test alias validation when pointing to curated token."""
    seed_post_curation(db)

    # Create alias pointing to curated token
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier, alias_of)
        VALUES (100, 1, 'color.alias', 'color', 'aliased', 1)
    """)
    db.commit()

    issues = check_alias_targets_curated(db, file_id=1)
    assert len(issues) == 0


@pytest.mark.unit
def test_check_alias_targets_curated_fail(db):
    """Test alias validation when pointing to extracted token."""
    seed_post_clustering(db)  # Tokens are extracted, not curated

    # Create alias pointing to extracted token
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier, alias_of)
        VALUES (100, 1, 'color.alias', 'color', 'aliased', 1)
    """)
    db.commit()

    issues = check_alias_targets_curated(db, file_id=1)
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert "color.alias" in issues[0]["message"]
    assert "extracted" in issues[0]["message"]


@pytest.mark.unit
def test_check_name_uniqueness_pass(db):
    """Test name uniqueness with all unique names."""
    seed_post_curation(db)

    issues = check_name_uniqueness(db, file_id=1)
    assert len(issues) == 0


@pytest.mark.unit
def test_check_value_format_color_valid(db):
    """Test color format validation with valid hex."""
    seed_post_curation(db)

    # Update a token value to ensure it's a valid hex color
    db.execute("""
        UPDATE token_values SET resolved_value = '#09090B'
        WHERE token_id = 1 AND mode_id = 1
    """)
    db.commit()

    issues = check_value_format(db, file_id=1)
    # Filter to only color format issues
    color_issues = [i for i in issues if "color format" in i.get("message", "")]
    assert len(color_issues) == 0


@pytest.mark.unit
def test_check_value_format_color_invalid(db):
    """Test color format validation with invalid value."""
    seed_post_curation(db)

    # Update a color token to have invalid value
    db.execute("""
        UPDATE token_values SET resolved_value = 'not-a-hex'
        WHERE token_id = 1 AND mode_id = 1
    """)
    db.commit()

    issues = check_value_format(db, file_id=1)
    color_issues = [i for i in issues if "color format" in i.get("message", "")]
    assert len(color_issues) >= 1
    assert color_issues[0]["severity"] == "error"


@pytest.mark.unit
def test_check_value_format_dimension_valid(db):
    """Test dimension format validation with valid numeric value."""
    seed_post_curation(db)

    # Token 5 (space.4) has resolved_value = "16" which is valid
    issues = check_value_format(db, file_id=1)
    dimension_issues = [i for i in issues if "dimension format" in i.get("message", "")]
    assert len(dimension_issues) == 0


@pytest.mark.unit
def test_run_validation_pass(db):
    """Test run_validation with clean data."""
    seed_post_curation(db)

    result = run_validation(db, file_id=1)

    assert "passed" in result
    assert "errors" in result
    assert "warnings" in result
    assert "info" in result
    assert "run_at" in result
    assert "issues" in result

    # Should pass if no errors (warnings are OK)
    assert result["passed"] == (result["errors"] == 0)


@pytest.mark.unit
def test_run_validation_fail(db):
    """Test run_validation with data containing errors."""
    seed_post_curation(db)

    # Add a token with bad name
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier)
        VALUES (100, 1, 'Bad Name', 'color', 'extracted')
    """)
    db.commit()

    result = run_validation(db, file_id=1)

    assert result["passed"] is False
    assert result["errors"] > 0


@pytest.mark.unit
def test_run_validation_writes_to_db(db):
    """Test that run_validation writes to export_validations table."""
    seed_post_curation(db)

    # Check table is empty before
    cursor = db.execute("SELECT COUNT(*) as cnt FROM export_validations")
    assert cursor.fetchone()["cnt"] == 0

    # Run validation
    run_validation(db, file_id=1)

    # Check table has entries after
    cursor = db.execute("SELECT COUNT(*) as cnt FROM export_validations")
    assert cursor.fetchone()["cnt"] > 0


@pytest.mark.unit
def test_is_export_ready_no_validation(db):
    """Test is_export_ready when no validation has been run."""
    seed_post_curation(db)

    # No validation run yet
    assert is_export_ready(db) is False


@pytest.mark.unit
def test_is_export_ready_after_pass(db):
    """Test is_export_ready after successful validation."""
    seed_post_curation(db)

    # Run validation on clean data
    result = run_validation(db, file_id=1)

    # If there are no errors, should be ready
    if result["errors"] == 0:
        assert is_export_ready(db) is True
    else:
        assert is_export_ready(db) is False


@pytest.mark.unit
def test_is_export_ready_after_fail(db):
    """Test is_export_ready after failed validation."""
    seed_post_curation(db)

    # Add bad data
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier)
        VALUES (100, 1, 'Bad Name', 'color', 'extracted')
    """)
    db.commit()

    # Run validation
    run_validation(db, file_id=1)

    # Should not be ready due to errors
    assert is_export_ready(db) is False