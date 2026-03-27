"""Unit tests for curation operations and status functions."""

import pytest

from dd.curate import (
    accept_token,
    accept_all,
    rename_token,
    merge_tokens,
    split_token,
    reject_token,
    create_alias,
    create_collection,
    convert_to_alias,
)
from dd.status import (
    get_curation_progress,
    get_token_coverage,
    format_status_report,
    get_status_dict,
)
from tests.fixtures import seed_post_clustering, seed_post_curation


# Curation operation tests

@pytest.mark.unit
def test_accept_token(db):
    """Test accepting a single token."""
    seed_post_clustering(db)

    # Accept token_id=1
    result = accept_token(db, 1)

    assert result["token_id"] == 1
    assert result["bindings_updated"] == 2  # Two bindings for token 1

    # Verify token tier updated
    cursor = db.execute("SELECT tier FROM tokens WHERE id = ?", (1,))
    assert cursor.fetchone()["tier"] == "curated"

    # Verify bindings updated to bound
    cursor = db.execute(
        "SELECT binding_status FROM node_token_bindings WHERE token_id = ?",
        (1,)
    )
    statuses = [row["binding_status"] for row in cursor]
    assert all(status == "bound" for status in statuses)


@pytest.mark.unit
def test_accept_token_nonexistent(db):
    """Test accepting a non-existent token raises ValueError."""
    seed_post_clustering(db)

    with pytest.raises(ValueError, match="Token 999 does not exist"):
        accept_token(db, 999)


@pytest.mark.unit
def test_accept_all(db):
    """Test bulk accepting all tokens for a file."""
    seed_post_clustering(db)

    result = accept_all(db, 1)

    assert result["tokens_accepted"] == 5  # All 5 extracted tokens
    assert result["bindings_updated"] == 5  # All proposed bindings

    # Verify all tokens curated
    cursor = db.execute("SELECT tier FROM tokens")
    tiers = [row["tier"] for row in cursor]
    assert all(tier == "curated" for tier in tiers)

    # Verify all proposed bindings are now bound
    cursor = db.execute(
        "SELECT binding_status FROM node_token_bindings WHERE token_id IS NOT NULL"
    )
    statuses = [row["binding_status"] for row in cursor]
    assert all(status == "bound" for status in statuses)


@pytest.mark.unit
def test_rename_token_valid(db):
    """Test renaming a token with a valid name."""
    seed_post_clustering(db)

    result = rename_token(db, 1, "color.background.primary")

    assert result["token_id"] == 1
    assert result["old_name"] == "color.surface.primary"
    assert result["new_name"] == "color.background.primary"

    # Verify name changed in DB
    cursor = db.execute("SELECT name FROM tokens WHERE id = ?", (1,))
    assert cursor.fetchone()["name"] == "color.background.primary"


@pytest.mark.unit
def test_rename_token_invalid_name(db):
    """Test renaming with an invalid DTCG name raises ValueError."""
    seed_post_clustering(db)

    with pytest.raises(ValueError, match="Invalid DTCG name"):
        rename_token(db, 1, "Invalid Name")


@pytest.mark.unit
def test_rename_token_uppercase(db):
    """Test renaming with uppercase letters raises ValueError."""
    seed_post_clustering(db)

    with pytest.raises(ValueError, match="Invalid DTCG name"):
        rename_token(db, 1, "Color.Surface")


@pytest.mark.unit
def test_rename_token_duplicate(db):
    """Test renaming to an existing name in same collection raises ValueError."""
    seed_post_clustering(db)

    # Try to rename token 1 to the name of token 2
    with pytest.raises(ValueError, match="already exists in collection"):
        rename_token(db, 1, "color.surface.secondary")


@pytest.mark.unit
def test_merge_tokens(db):
    """Test merging two tokens."""
    seed_post_clustering(db)

    # Count initial bindings for each token
    cursor = db.execute(
        "SELECT COUNT(*) as cnt FROM node_token_bindings WHERE token_id = ?", (1,)
    )
    survivor_count = cursor.fetchone()["cnt"]

    cursor = db.execute(
        "SELECT COUNT(*) as cnt FROM node_token_bindings WHERE token_id = ?", (2,)
    )
    victim_count = cursor.fetchone()["cnt"]

    result = merge_tokens(db, 1, 2)

    assert result["survivor_id"] == 1
    assert result["victim_id"] == 2
    assert result["bindings_reassigned"] == victim_count

    # Verify victim token deleted
    cursor = db.execute("SELECT * FROM tokens WHERE id = ?", (2,))
    assert cursor.fetchone() is None

    # Verify victim's token_values deleted
    cursor = db.execute("SELECT * FROM token_values WHERE token_id = ?", (2,))
    assert cursor.fetchone() is None

    # Verify all bindings now point to survivor
    cursor = db.execute(
        "SELECT COUNT(*) as cnt FROM node_token_bindings WHERE token_id = ?", (1,)
    )
    new_count = cursor.fetchone()["cnt"]
    assert new_count == survivor_count + victim_count


@pytest.mark.unit
def test_merge_tokens_different_collections(db):
    """Test merging tokens from different collections raises ValueError."""
    seed_post_clustering(db)

    # Token 1 is in collection 1 (Colors), token 5 is in collection 2 (Spacing)
    with pytest.raises(ValueError, match="Cannot merge tokens from different collections"):
        merge_tokens(db, 1, 5)


@pytest.mark.unit
def test_merge_tokens_binding_count(db):
    """Test that merged token has correct binding count."""
    seed_post_clustering(db)

    # Token 2 already has 1 binding (id=4) from seed data
    # Add another binding to token 2 for testing
    db.execute("""
        UPDATE node_token_bindings
        SET token_id = 2, binding_status = 'proposed', confidence = 0.9
        WHERE id = 2
    """)
    db.commit()

    # Now token 1 has 2 bindings, token 2 has 2 bindings (one from seed, one just added)
    result = merge_tokens(db, 1, 2)

    assert result["bindings_reassigned"] == 2

    cursor = db.execute(
        "SELECT COUNT(*) as cnt FROM node_token_bindings WHERE token_id = ?", (1,)
    )
    assert cursor.fetchone()["cnt"] == 4  # 2 original + 2 from victim


@pytest.mark.unit
def test_split_token(db):
    """Test splitting a token by moving some bindings."""
    seed_post_clustering(db)

    # Token 1 has bindings with IDs 1 and 5
    result = split_token(db, 1, "color.surface.alt", [1])

    assert result["original_token_id"] == 1
    assert result["bindings_moved"] == 1

    new_token_id = result["new_token_id"]

    # Verify new token created
    cursor = db.execute("SELECT name, type FROM tokens WHERE id = ?", (new_token_id,))
    new_token = cursor.fetchone()
    assert new_token["name"] == "color.surface.alt"
    assert new_token["type"] == "color"

    # Verify binding moved
    cursor = db.execute(
        "SELECT token_id FROM node_token_bindings WHERE id = ?", (1,)
    )
    assert cursor.fetchone()["token_id"] == new_token_id

    # Verify original token still has its other binding
    cursor = db.execute(
        "SELECT token_id FROM node_token_bindings WHERE id = ?", (5,)
    )
    assert cursor.fetchone()["token_id"] == 1


@pytest.mark.unit
def test_split_token_invalid_name(db):
    """Test split with invalid name raises ValueError."""
    seed_post_clustering(db)

    with pytest.raises(ValueError, match="Invalid DTCG name"):
        split_token(db, 1, "Invalid Name", [1])


@pytest.mark.unit
def test_split_token_wrong_bindings(db):
    """Test split with bindings not belonging to token raises ValueError."""
    seed_post_clustering(db)

    # Try to move binding 3 which belongs to token 3, not token 1
    with pytest.raises(ValueError, match="binding IDs do not belong to token"):
        split_token(db, 1, "color.surface.alt", [3])


@pytest.mark.unit
def test_split_token_copies_values(db):
    """Test that split token gets token_values copied from original."""
    seed_post_clustering(db)

    result = split_token(db, 1, "color.surface.alt", [1])
    new_token_id = result["new_token_id"]

    # Verify token_values copied
    cursor = db.execute(
        "SELECT raw_value, resolved_value FROM token_values WHERE token_id = ?",
        (new_token_id,)
    )
    new_values = cursor.fetchone()

    cursor = db.execute(
        "SELECT raw_value, resolved_value FROM token_values WHERE token_id = ?",
        (1,)
    )
    orig_values = cursor.fetchone()

    assert new_values["raw_value"] == orig_values["raw_value"]
    assert new_values["resolved_value"] == orig_values["resolved_value"]


@pytest.mark.unit
def test_reject_token(db):
    """Test rejecting a token."""
    seed_post_clustering(db)

    # Count bindings for token 1
    cursor = db.execute(
        "SELECT COUNT(*) as cnt FROM node_token_bindings WHERE token_id = ?", (1,)
    )
    binding_count = cursor.fetchone()["cnt"]

    result = reject_token(db, 1)

    assert result["token_id"] == 1
    assert result["bindings_reverted"] == binding_count

    # Verify token deleted
    cursor = db.execute("SELECT * FROM tokens WHERE id = ?", (1,))
    assert cursor.fetchone() is None

    # Verify bindings reverted to unbound with NULL token_id
    cursor = db.execute(
        "SELECT token_id, binding_status FROM node_token_bindings WHERE id IN (1, 5)"
    )
    for row in cursor:
        assert row["token_id"] is None
        assert row["binding_status"] == "unbound"


@pytest.mark.unit
def test_reject_token_nonexistent(db):
    """Test rejecting a non-existent token raises ValueError."""
    seed_post_clustering(db)

    with pytest.raises(ValueError, match="Token 999 does not exist"):
        reject_token(db, 999)


@pytest.mark.unit
def test_create_collection(db):
    """Test creating a new collection with default mode."""
    seed_post_curation(db)

    result = create_collection(db, "Color Primitives", file_id=1)

    assert result["collection_id"] > 0
    assert result["name"] == "Color Primitives"
    assert result["mode_id"] > 0

    cursor = db.execute("SELECT name FROM token_collections WHERE id = ?", (result["collection_id"],))
    assert cursor.fetchone()["name"] == "Color Primitives"

    cursor = db.execute("SELECT name, is_default FROM token_modes WHERE collection_id = ?", (result["collection_id"],))
    mode = cursor.fetchone()
    assert mode["name"] == "Default"
    assert mode["is_default"] == 1


@pytest.mark.unit
def test_create_collection_with_custom_modes(db):
    """Test creating a collection with specific mode names."""
    seed_post_curation(db)

    result = create_collection(db, "Themed Colors", file_id=1, mode_names=["Light", "Dark"])

    modes = db.execute(
        "SELECT name, is_default FROM token_modes WHERE collection_id = ? ORDER BY id",
        (result["collection_id"],)
    ).fetchall()
    assert len(modes) == 2
    assert modes[0]["name"] == "Light"
    assert modes[0]["is_default"] == 1
    assert modes[1]["name"] == "Dark"


@pytest.mark.unit
def test_create_collection_duplicate_name_raises(db):
    """Test creating a collection with an existing name raises ValueError."""
    seed_post_curation(db)

    create_collection(db, "MyCollection", file_id=1)
    with pytest.raises(ValueError, match="already exists"):
        create_collection(db, "MyCollection", file_id=1)


@pytest.mark.unit
def test_convert_to_alias(db):
    """Test converting a valued token into an alias."""
    seed_post_curation(db)

    # Create a target primitive token
    coll = create_collection(db, "Primitives", file_id=1)
    cursor = db.execute(
        "INSERT INTO tokens (collection_id, name, type, tier) VALUES (?, 'prim.white', 'color', 'curated')",
        (coll["collection_id"],)
    )
    primitive_id = cursor.lastrowid
    mode_id = coll["mode_id"]
    db.execute(
        "INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value) VALUES (?, ?, '#FFFFFF', '#FFFFFF')",
        (primitive_id, mode_id)
    )
    db.commit()

    # Token 1 is a curated color token with bindings
    original_bindings = db.execute(
        "SELECT COUNT(*) as cnt FROM node_token_bindings WHERE token_id = 1"
    ).fetchone()["cnt"]
    assert original_bindings > 0

    result = convert_to_alias(db, token_id=1, target_token_id=primitive_id)

    assert result["token_id"] == 1
    assert result["target_token_id"] == primitive_id

    # Token should now be an alias
    token = db.execute("SELECT alias_of, tier FROM tokens WHERE id = 1").fetchone()
    assert token["alias_of"] == primitive_id
    assert token["tier"] == "aliased"

    # Token values should be cleared (aliases derive from target)
    values = db.execute("SELECT COUNT(*) as cnt FROM token_values WHERE token_id = 1").fetchone()["cnt"]
    assert values == 0

    # Bindings should be preserved
    post_bindings = db.execute(
        "SELECT COUNT(*) as cnt FROM node_token_bindings WHERE token_id = 1"
    ).fetchone()["cnt"]
    assert post_bindings == original_bindings


@pytest.mark.unit
def test_convert_to_alias_target_must_not_be_alias(db):
    """Test converting to alias fails if target is itself an alias."""
    seed_post_curation(db)

    alias_result = create_alias(db, "color.bg", 1, 1)
    alias_id = alias_result["alias_id"]

    with pytest.raises(ValueError, match="cannot be an alias"):
        convert_to_alias(db, token_id=2, target_token_id=alias_id)


@pytest.mark.unit
def test_convert_to_alias_nonexistent_target_raises(db):
    """Test converting to alias fails with nonexistent target."""
    seed_post_curation(db)

    with pytest.raises(ValueError, match="does not exist"):
        convert_to_alias(db, token_id=1, target_token_id=9999)


@pytest.mark.unit
def test_create_alias(db):
    """Test creating an alias to a curated token."""
    seed_post_curation(db)

    result = create_alias(db, "color.bg", 1, 1)

    assert result["alias_name"] == "color.bg"
    assert result["target_id"] == 1
    assert result["target_name"] == "color.surface.primary"

    alias_id = result["alias_id"]

    # Verify alias created with correct properties
    cursor = db.execute(
        "SELECT name, tier, alias_of, type FROM tokens WHERE id = ?",
        (alias_id,)
    )
    alias = cursor.fetchone()
    assert alias["name"] == "color.bg"
    assert alias["tier"] == "aliased"
    assert alias["alias_of"] == 1
    assert alias["type"] == "color"  # Inherited from target


@pytest.mark.unit
def test_create_alias_to_alias_blocked(db):
    """Test creating an alias pointing to another alias raises ValueError."""
    seed_post_curation(db)

    # Create first alias
    result = create_alias(db, "color.bg", 1, 1)
    alias_id = result["alias_id"]

    # Try to create alias to the alias
    with pytest.raises(ValueError, match="Target token cannot be an alias"):
        create_alias(db, "color.bg2", alias_id, 1)


@pytest.mark.unit
def test_create_alias_invalid_name(db):
    """Test creating alias with invalid name raises ValueError."""
    seed_post_curation(db)

    with pytest.raises(ValueError, match="Invalid DTCG name"):
        create_alias(db, "Invalid Name", 1, 1)


@pytest.mark.unit
def test_create_alias_to_noncurated(db):
    """Test creating alias to extracted token is allowed but will fail validation."""
    seed_post_clustering(db)  # Tokens are extracted, not curated

    # This should succeed - validation will catch it later
    result = create_alias(db, "color.bg", 1, 1)

    assert result["alias_name"] == "color.bg"
    assert result["target_id"] == 1

    # Verify alias created even though target is not curated
    cursor = db.execute(
        "SELECT tier FROM tokens WHERE id = ?",
        (result["alias_id"],)
    )
    assert cursor.fetchone()["tier"] == "aliased"


# Status tests

@pytest.mark.unit
def test_status_curation_progress(db):
    """Test getting curation progress."""
    seed_post_clustering(db)

    progress = get_curation_progress(db)

    assert len(progress) > 0

    # Check we have proposed and unbound entries
    statuses = {item['status'] for item in progress}
    assert 'proposed' in statuses
    assert 'unbound' in statuses

    # Verify counts
    proposed = next(p for p in progress if p['status'] == 'proposed')
    assert proposed['count'] == 5  # 5 proposed bindings

    unbound = next(p for p in progress if p['status'] == 'unbound')
    assert unbound['count'] == 10  # 10 unbound bindings


@pytest.mark.unit
def test_status_curation_progress_empty(db):
    """Test curation progress with empty DB returns empty list."""
    progress = get_curation_progress(db)
    assert progress == []


@pytest.mark.unit
def test_status_token_coverage(db):
    """Test getting token coverage statistics."""
    seed_post_clustering(db)

    coverage = get_token_coverage(db, file_id=1)

    assert len(coverage) == 5  # 5 tokens total

    # Tokens with bindings should be listed first (higher binding_count)
    # Tokens 1-4 have bindings, token 5 doesn't
    tokens_with_bindings = [t for t in coverage if t['binding_count'] > 0]
    assert len(tokens_with_bindings) == 4


@pytest.mark.unit
def test_status_format_report(db):
    """Test formatting status report as text."""
    seed_post_clustering(db)

    report = format_status_report(db, file_id=1)

    assert isinstance(report, str)
    assert len(report) > 0
    assert "Curation Progress" in report
    assert "Token Coverage" in report
    assert "Unbound Bindings" in report
    assert "Export Readiness" in report


@pytest.mark.unit
def test_status_dict(db):
    """Test getting status as structured dict."""
    seed_post_clustering(db)

    status = get_status_dict(db, file_id=1)

    assert isinstance(status, dict)
    assert "curation_progress" in status
    assert "token_count" in status
    assert "token_coverage" in status
    assert "unbound_count" in status
    assert "export_readiness" in status
    assert "is_ready" in status

    assert status["token_count"] == 5
    assert status["unbound_count"] == 10  # 10 unbound bindings
    assert status["is_ready"] is False  # No validation run yet