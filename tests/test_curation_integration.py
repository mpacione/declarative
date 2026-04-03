"""Integration tests for clustering-to-curation pipeline."""

import pytest

from dd.curate import (
    accept_all,
    accept_token,
    create_alias,
    merge_tokens,
    reject_token,
    split_token,
)
from dd.validate import is_export_ready, run_validation
from tests.fixtures import seed_post_clustering, seed_post_curation


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_accept_merge_then_validate(db):
    """Test accept and merge operations followed by validation."""
    seed_post_clustering(db)

    # Accept token 1 (promote to curated, bindings to bound)
    result = accept_token(db, 1)
    assert result["token_id"] == 1
    assert result["bindings_updated"] == 2  # 2 bindings for token 1

    # Verify token 1 state
    cursor = db.execute("SELECT tier FROM tokens WHERE id = 1")
    assert cursor.fetchone()[0] == "curated"

    cursor = db.execute(
        "SELECT binding_status FROM node_token_bindings WHERE token_id = 1"
    )
    statuses = [row[0] for row in cursor.fetchall()]
    assert all(status == "bound" for status in statuses)

    # Merge token 3 into token 2 (reassign bindings)
    result = merge_tokens(db, 2, 3)
    assert result["survivor_id"] == 2
    assert result["victim_id"] == 3
    assert result["bindings_reassigned"] == 1  # token 3 had 1 binding

    # Verify token 3 no longer exists
    cursor = db.execute("SELECT COUNT(*) FROM tokens WHERE id = 3")
    assert cursor.fetchone()[0] == 0

    # Verify token 3's bindings now point to token 2
    cursor = db.execute(
        "SELECT token_id FROM node_token_bindings WHERE id = 3"
    )
    assert cursor.fetchone()[0] == 2

    # Accept token 2 (now with merged bindings)
    result = accept_token(db, 2)
    assert result["token_id"] == 2
    assert result["bindings_updated"] == 2  # original + merged binding

    # Verify token 2 state
    cursor = db.execute("SELECT tier FROM tokens WHERE id = 2")
    assert cursor.fetchone()[0] == "curated"

    # Run validation
    validation_result = run_validation(db, 1)
    assert "passed" in validation_result
    # May have warnings but no errors for curated tokens

    # Check v_token_coverage
    cursor = db.execute("""
        SELECT token_name, binding_count
        FROM v_token_coverage
        WHERE token_name IN ('color.surface.primary', 'color.surface.secondary')
    """)
    coverage = {row[0]: row[1] for row in cursor.fetchall()}
    assert coverage["color.surface.primary"] == 2
    assert coverage["color.surface.secondary"] == 2  # original + merged binding


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_reject_reverts_bindings_to_unbound(db):
    """Test that rejecting a token reverts its bindings to unbound."""
    seed_post_clustering(db)

    # Count proposed bindings for token 1
    cursor = db.execute(
        "SELECT COUNT(*) FROM node_token_bindings WHERE token_id = 1"
    )
    initial_binding_count = cursor.fetchone()[0]
    assert initial_binding_count == 2

    # Reject token 1
    result = reject_token(db, 1)
    assert result["token_id"] == 1
    assert result["bindings_reverted"] == 2

    # Verify token 1 no longer exists
    cursor = db.execute("SELECT COUNT(*) FROM tokens WHERE id = 1")
    assert cursor.fetchone()[0] == 0

    # Verify bindings are now unbound with NULL token_id
    cursor = db.execute("""
        SELECT token_id, binding_status
        FROM node_token_bindings
        WHERE id IN (1, 5)
    """)
    for row in cursor:
        assert row[0] is None
        assert row[1] == "unbound"

    # Total binding count unchanged
    cursor = db.execute("SELECT COUNT(*) FROM node_token_bindings")
    total_bindings = cursor.fetchone()[0]
    assert total_bindings == 15

    # Check v_curation_progress
    cursor = db.execute("""
        SELECT binding_status, binding_count
        FROM v_curation_progress
    """)
    progress = {row[0]: row[1] for row in cursor.fetchall()}
    assert progress.get("unbound", 0) > 0
    # After rejecting, we should have more unbound bindings
    assert progress.get("unbound", 0) >= 12  # Original 10 unbound + 2 reverted


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_split_preserves_fk_integrity(db):
    """Test that splitting a token preserves FK integrity."""
    seed_post_clustering(db)

    # Get binding IDs for token 1
    cursor = db.execute(
        "SELECT id FROM node_token_bindings WHERE token_id = 1 ORDER BY id"
    )
    binding_ids = [row[0] for row in cursor.fetchall()]
    assert len(binding_ids) == 2  # token 1 has 2 bindings

    # Split token 1, moving 1 binding to new token
    result = split_token(db, 1, "color.surface.alt", [binding_ids[0]])
    new_token_id = result["new_token_id"]
    assert result["bindings_moved"] == 1

    # Verify new token exists
    cursor = db.execute(
        "SELECT name, tier, collection_id FROM tokens WHERE id = ?",
        (new_token_id,)
    )
    row = cursor.fetchone()
    assert row[0] == "color.surface.alt"
    assert row[1] == "extracted"
    assert row[2] == 1  # same collection as original

    # Verify moved binding references new token
    cursor = db.execute(
        "SELECT token_id FROM node_token_bindings WHERE id = ?",
        (binding_ids[0],)
    )
    assert cursor.fetchone()[0] == new_token_id

    # Verify remaining binding still references original token
    cursor = db.execute(
        "SELECT token_id FROM node_token_bindings WHERE id = ?",
        (binding_ids[1],)
    )
    assert cursor.fetchone()[0] == 1

    # Verify new token has token_values (copied from original)
    cursor = db.execute(
        "SELECT COUNT(*) FROM token_values WHERE token_id = ?",
        (new_token_id,)
    )
    assert cursor.fetchone()[0] == 1

    # Check FK integrity - no orphaned bindings
    cursor = db.execute("""
        SELECT COUNT(*)
        FROM node_token_bindings
        WHERE token_id NOT IN (SELECT id FROM tokens)
        AND token_id IS NOT NULL
    """)
    assert cursor.fetchone()[0] == 0


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_alias_chain_resolves(db):
    """Test that alias chains resolve correctly through v_resolved_tokens."""
    seed_post_curation(db)

    # Create alias "color.bg" -> token 1 (color.surface.primary)
    result = create_alias(db, "color.bg", 1, 1)
    alias_id = result["alias_id"]

    # Add a token_value for the alias to enable the view join
    # (aliases need a token_value row to join with the target's values)
    db.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (?, 1, '', '')
    """, (alias_id,))

    # Query v_resolved_tokens for the alias
    cursor = db.execute("""
        SELECT id, name, tier, alias_target_name, resolved_value
        FROM v_resolved_tokens
        WHERE id = ?
    """, (alias_id,))

    row = cursor.fetchone()
    assert row is not None
    assert row[1] == "color.bg"
    assert row[2] == "aliased"
    assert row[3] == "color.surface.primary"
    assert row[4] == "#09090B"  # resolved to target's value


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_validation_catches_incomplete_curation(db):
    """Test that validation catches incomplete curation."""
    seed_post_clustering(db)

    # DO NOT accept any tokens - they remain extracted

    # Create an alias pointing to an extracted (non-curated) token
    result = create_alias(db, "color.alias", 1, 1)

    # Run validation
    validation_result = run_validation(db, 1)
    assert validation_result["passed"] is False

    # Check for alias_targets_curated error
    cursor = db.execute("""
        SELECT severity, message
        FROM export_validations
        WHERE check_name = 'alias_targets_curated'
        AND run_at = (SELECT MAX(run_at) FROM export_validations)
    """)
    rows = cursor.fetchall()
    assert len(rows) > 0
    assert any(row[0] == "error" for row in rows)

    # Verify is_export_ready returns False
    assert is_export_ready(db) is False

    # Check v_export_readiness
    cursor = db.execute("""
        SELECT check_name, severity, issue_count
        FROM v_export_readiness
        WHERE severity = 'error'
    """)
    errors = cursor.fetchall()
    assert len(errors) > 0
    assert any("alias_targets_curated" in row[0] for row in errors)


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_validation_passes_after_full_curation(db):
    """Test that validation passes after full curation."""
    seed_post_clustering(db)

    # Accept all tokens
    result = accept_all(db, 1)
    assert result["tokens_accepted"] == 5  # 4 color + 1 spacing token

    # Run validation
    validation_result = run_validation(db, 1)
    assert validation_result["passed"] is True

    # Verify is_export_ready returns True
    assert is_export_ready(db) is True

    # Check that validation run created rows
    cursor = db.execute("""
        SELECT COUNT(*)
        FROM export_validations
        WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
    """)
    assert cursor.fetchone()[0] > 0

    # No error-severity rows in the latest run
    cursor = db.execute("""
        SELECT COUNT(*)
        FROM export_validations
        WHERE severity = 'error'
        AND run_at = (SELECT MAX(run_at) FROM export_validations)
    """)
    assert cursor.fetchone()[0] == 0


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_merge_then_validate_binding_coverage(db):
    """Test binding coverage after merge operations."""
    seed_post_clustering(db)

    # Accept all tokens
    result = accept_all(db, 1)
    assert result["tokens_accepted"] == 5

    # Run validation
    validation_result = run_validation(db, 1)

    # Query v_token_coverage
    cursor = db.execute("""
        SELECT token_name, binding_count
        FROM v_token_coverage
        WHERE collection_id IN (1, 2)
    """)

    coverage = {row[0]: row[1] for row in cursor.fetchall()}

    # Color tokens should have bindings, spacing token doesn't in the fixture
    for token_name, count in coverage.items():
        if token_name.startswith("color"):
            assert count > 0, f"Token {token_name} has no bindings"

    # Check binding_coverage validation
    cursor = db.execute("""
        SELECT message
        FROM export_validations
        WHERE check_name = 'binding_coverage'
        AND run_at = (SELECT MAX(run_at) FROM export_validations)
    """)
    row = cursor.fetchone()
    assert row is not None
    # Should show some percentage bound
    assert "bound" in row[0].lower() or "coverage" in row[0].lower()


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_curation_progress_view_reflects_operations(db):
    """Test that v_curation_progress accurately reflects state changes."""
    seed_post_clustering(db)

    # Initial state
    cursor = db.execute("""
        SELECT binding_status, binding_count
        FROM v_curation_progress
        ORDER BY binding_status
    """)
    initial_progress = {row[0]: row[1] for row in cursor.fetchall()}
    assert initial_progress.get("proposed", 0) > 0
    assert initial_progress.get("unbound", 0) > 0

    # Accept all tokens
    accept_all(db, 1)

    # Check progress after accept_all
    cursor = db.execute("""
        SELECT binding_status, binding_count
        FROM v_curation_progress
        ORDER BY binding_status
    """)
    after_accept = {row[0]: row[1] for row in cursor.fetchall()}
    assert after_accept.get("proposed", 0) == 0
    assert after_accept.get("bound", 0) > initial_progress.get("bound", 0)

    # Reject token 4 (color.text.primary)
    reject_token(db, 4)

    # Check progress after reject
    cursor = db.execute("""
        SELECT binding_status, binding_count
        FROM v_curation_progress
        ORDER BY binding_status
    """)
    after_reject = {row[0]: row[1] for row in cursor.fetchall()}
    assert after_reject.get("unbound", 0) > after_accept.get("unbound", 0)
    assert after_reject.get("bound", 0) < after_accept.get("bound", 0)


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_validation_mode_completeness_with_new_mode(db):
    """Test mode completeness validation with missing mode values."""
    seed_post_curation(db)

    # Add a second mode "Dark" to the Colors collection
    db.execute("""
        INSERT INTO token_modes (collection_id, name, is_default)
        VALUES (1, 'Dark', 0)
    """)
    db.commit()

    # DO NOT add token_values for the Dark mode

    # Run validation
    validation_result = run_validation(db, 1)
    assert validation_result["passed"] is False

    # Check for mode_completeness errors
    cursor = db.execute("""
        SELECT severity, message
        FROM export_validations
        WHERE check_name = 'mode_completeness'
        AND run_at = (SELECT MAX(run_at) FROM export_validations)
    """)
    rows = cursor.fetchall()
    assert len(rows) > 0

    # Should have errors for each token missing Dark mode
    for row in rows:
        assert row[0] == "error"
        assert "Dark" in row[1]


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_no_orphan_records_after_curation_sequence(db):
    """Test that complex curation sequences don't leave orphan records."""
    seed_post_clustering(db)

    # Complex curation sequence
    accept_token(db, 1)  # Accept token 1
    merge_tokens(db, 2, 3)  # Merge 3 into 2
    reject_token(db, 4)  # Reject 4
    accept_token(db, 2)  # Accept 2

    # Verify no orphan bindings
    cursor = db.execute("""
        SELECT COUNT(*)
        FROM node_token_bindings
        WHERE token_id NOT IN (SELECT id FROM tokens)
        AND token_id IS NOT NULL
    """)
    assert cursor.fetchone()[0] == 0

    # Verify all token_values reference valid tokens
    cursor = db.execute("""
        SELECT COUNT(*)
        FROM token_values
        WHERE token_id NOT IN (SELECT id FROM tokens)
    """)
    assert cursor.fetchone()[0] == 0

    # Verify all token_values reference valid modes
    cursor = db.execute("""
        SELECT COUNT(*)
        FROM token_values
        WHERE mode_id NOT IN (SELECT id FROM token_modes)
    """)
    assert cursor.fetchone()[0] == 0

    # Verify tokens table integrity
    cursor = db.execute("""
        SELECT COUNT(*)
        FROM tokens
        WHERE alias_of NOT IN (SELECT id FROM tokens)
        AND alias_of IS NOT NULL
    """)
    assert cursor.fetchone()[0] == 0