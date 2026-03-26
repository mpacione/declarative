"""Tests for curation operations."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from dd.db import init_db, backup_db
from dd.curate import (
    accept_token,
    accept_all,
    rename_token,
    merge_tokens,
    split_token,
    reject_token,
    create_alias,
    _validate_dtcg_name,
)
from dd.status import (
    get_curation_progress,
    get_token_coverage,
    get_unbound_summary,
    get_export_readiness,
    format_status_report,
    get_status_dict,
)


@pytest.fixture
def memory_db():
    """Create an in-memory database with test data."""
    conn = init_db(":memory:")

    # Insert test data
    conn.execute("""
        INSERT INTO files (id, file_key, name, extracted_at)
        VALUES (1, 'test_file', 'Test File', '2024-01-01T00:00:00Z')
    """)

    conn.execute("""
        INSERT INTO token_collections (id, file_id, name)
        VALUES (1, 1, 'Test Collection')
    """)

    conn.execute("""
        INSERT INTO token_modes (id, collection_id, name, is_default)
        VALUES (1, 1, 'Light', 1)
    """)

    # Add some test tokens
    conn.executemany("""
        INSERT INTO tokens (id, collection_id, name, type, tier)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (1, 1, 'color.primary', 'color', 'extracted'),
        (2, 1, 'color.secondary', 'color', 'extracted'),
        (3, 1, 'space.sm', 'dimension', 'curated'),
    ])

    # Add token values
    conn.executemany("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (?, ?, ?, ?)
    """, [
        (1, 1, '#FF0000', '#FF0000'),
        (2, 1, '#00FF00', '#00FF00'),
        (3, 1, '8px', '8'),
    ])

    # Add a screen first
    conn.execute("""
        INSERT INTO screens (id, file_id, figma_node_id, name, width, height, device_class)
        VALUES (1, 1, 'screen1', 'Test Screen', 1920, 1080, 'web')
    """)

    # Add test nodes
    conn.executemany("""
        INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, node_type, depth, sort_order, is_semantic)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (1, 1, 'node1', None, 'Button', 'FRAME', 0, 0, 1),
        (2, 1, 'node2', 1, 'Text', 'TEXT', 1, 0, 1),
    ])

    # Add test bindings
    conn.executemany("""
        INSERT INTO node_token_bindings
        (id, node_id, property, token_id, raw_value, resolved_value, confidence, binding_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (1, 1, 'fill.0.color', 1, '#FF0000', '#FF0000', 0.95, 'proposed'),
        (2, 1, 'padding.top', 3, '8px', '8', 0.99, 'bound'),
        (3, 2, 'fill.0.color', 2, '#00FF00', '#00FF00', 0.85, 'proposed'),
        (4, 2, 'fontSize', None, '16px', '16px', None, 'unbound'),
    ])

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def file_db():
    """Create a file-based database for testing backup operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(str(db_path))

        # Same test data as memory_db
        conn.execute("""
            INSERT INTO files (id, file_key, name, extracted_at)
            VALUES (1, 'test_file', 'Test File', '2024-01-01T00:00:00Z')
        """)

        conn.execute("""
            INSERT INTO token_collections (id, file_id, name)
            VALUES (1, 1, 'Test Collection')
        """)

        conn.execute("""
            INSERT INTO token_modes (id, collection_id, name, is_default)
            VALUES (1, 1, 'Light', 1)
        """)

        conn.executemany("""
            INSERT INTO tokens (id, collection_id, name, type, tier)
            VALUES (?, ?, ?, ?, ?)
        """, [
            (1, 1, 'color.primary', 'color', 'extracted'),
            (2, 1, 'color.secondary', 'color', 'extracted'),
        ])

        conn.executemany("""
            INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
            VALUES (?, ?, ?, ?)
        """, [
            (1, 1, '#FF0000', '#FF0000'),
            (2, 1, '#00FF00', '#00FF00'),
        ])

        # Add a screen first
        conn.execute("""
            INSERT INTO screens (id, file_id, figma_node_id, name, width, height, device_class)
            VALUES (1, 1, 'screen1', 'Test Screen', 1920, 1080, 'web')
        """)

        conn.execute("""
            INSERT INTO nodes (id, screen_id, figma_node_id, parent_id, name, node_type, depth, sort_order, is_semantic)
            VALUES (1, 1, 'node1', ?, 'Button', 'FRAME', 0, 0, 1)
        """, (None,))

        conn.executemany("""
            INSERT INTO node_token_bindings
            (node_id, property, token_id, raw_value, resolved_value, confidence, binding_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'fill.0.color', 1, '#FF0000', '#FF0000', 0.95, 'proposed'),
            (1, 'stroke.0.color', 2, '#00FF00', '#00FF00', 0.85, 'proposed'),
        ])

        conn.commit()
        yield conn, str(db_path)
        conn.close()


class TestAcceptToken:
    def test_accept_token_success(self, memory_db):
        result = accept_token(memory_db, 1)

        assert result["token_id"] == 1
        assert result["bindings_updated"] == 1

        # Verify token tier updated
        cursor = memory_db.execute("SELECT tier FROM tokens WHERE id = 1")
        assert cursor.fetchone()["tier"] == "curated"

        # Verify binding status updated
        cursor = memory_db.execute("""
            SELECT binding_status FROM node_token_bindings
            WHERE token_id = 1 AND binding_status = 'bound'
        """)
        assert cursor.fetchone() is not None

    def test_accept_token_already_curated(self, memory_db):
        # Token 3 is already curated
        result = accept_token(memory_db, 3)

        assert result["token_id"] == 3
        assert result["bindings_updated"] == 0  # No proposed bindings to update

        cursor = memory_db.execute("SELECT tier FROM tokens WHERE id = 3")
        assert cursor.fetchone()["tier"] == "curated"

    def test_accept_token_invalid_id(self, memory_db):
        with pytest.raises(ValueError, match="Token 999 does not exist"):
            accept_token(memory_db, 999)


class TestAcceptAll:
    def test_accept_all_success(self, file_db):
        conn, db_path = file_db
        result = accept_all(conn, 1, db_path)

        assert result["tokens_accepted"] == 2
        assert result["bindings_updated"] == 2

        # Verify all tokens promoted
        cursor = conn.execute("SELECT COUNT(*) FROM tokens WHERE tier = 'curated'")
        assert cursor.fetchone()[0] == 2

        # Verify all bindings bound
        cursor = conn.execute("SELECT COUNT(*) FROM node_token_bindings WHERE binding_status = 'bound'")
        assert cursor.fetchone()[0] == 2

        # Verify backup was created in the project backup directory
        from dd import config
        backup_dir = config.BACKUP_DIR
        assert backup_dir.exists()
        assert len(list(backup_dir.glob("backup_test_*.db"))) > 0

    def test_accept_all_memory_db(self, memory_db):
        # Memory DB should not create backup
        result = accept_all(memory_db, 1)

        assert result["tokens_accepted"] == 2
        assert result["bindings_updated"] == 2


class TestRenameToken:
    def test_rename_token_success(self, memory_db):
        result = rename_token(memory_db, 1, "color.brand.primary")

        assert result["token_id"] == 1
        assert result["old_name"] == "color.primary"
        assert result["new_name"] == "color.brand.primary"

        cursor = memory_db.execute("SELECT name FROM tokens WHERE id = 1")
        assert cursor.fetchone()["name"] == "color.brand.primary"

    def test_rename_token_invalid_name(self, memory_db):
        invalid_names = [
            "Invalid Name",  # spaces
            "UPPERCASE",     # uppercase
            "123start",      # starts with number
            "color..double", # double dots
            ".startdot",     # starts with dot
            "enddot.",       # ends with dot
            "special-char",  # hyphen
            "special_char",  # underscore
        ]

        for invalid_name in invalid_names:
            with pytest.raises(ValueError, match="Invalid DTCG name"):
                rename_token(memory_db, 1, invalid_name)

    def test_rename_token_duplicate(self, memory_db):
        with pytest.raises(ValueError, match="already exists"):
            rename_token(memory_db, 1, "color.secondary")

    def test_rename_token_not_found(self, memory_db):
        with pytest.raises(ValueError, match="Token 999 does not exist"):
            rename_token(memory_db, 999, "new.name")


class TestMergeTokens:
    def test_merge_tokens_success(self, file_db):
        conn, db_path = file_db
        result = merge_tokens(conn, 1, 2, db_path)

        assert result["survivor_id"] == 1
        assert result["victim_id"] == 2
        assert result["bindings_reassigned"] == 1

        # Verify victim deleted
        cursor = conn.execute("SELECT COUNT(*) FROM tokens WHERE id = 2")
        assert cursor.fetchone()[0] == 0

        # Verify bindings reassigned
        cursor = conn.execute("SELECT COUNT(*) FROM node_token_bindings WHERE token_id = 1")
        assert cursor.fetchone()[0] == 2

        # Verify backup created in the project backup directory
        from dd import config
        backup_dir = config.BACKUP_DIR
        assert backup_dir.exists()
        assert len(list(backup_dir.glob("backup_test_*.db"))) > 0

    def test_merge_tokens_different_collections(self, memory_db):
        # Create token in different collection
        memory_db.execute("""
            INSERT INTO token_collections (id, file_id, name)
            VALUES (2, 1, 'Other Collection')
        """)
        memory_db.execute("""
            INSERT INTO tokens (id, collection_id, name, type, tier)
            VALUES (4, 2, 'other.token', 'color', 'extracted')
        """)

        with pytest.raises(ValueError, match="different collections"):
            merge_tokens(memory_db, 1, 4)

    def test_merge_tokens_not_found(self, memory_db):
        with pytest.raises(ValueError, match="Token .* does not exist"):
            merge_tokens(memory_db, 1, 999)


class TestSplitToken:
    def test_split_token_success(self, memory_db):
        result = split_token(memory_db, 1, "color.primary.light", [1])

        assert result["original_token_id"] == 1
        assert result["new_token_id"] > 0
        assert result["bindings_moved"] == 1

        # Verify new token created
        cursor = memory_db.execute("SELECT * FROM tokens WHERE name = 'color.primary.light'")
        new_token = cursor.fetchone()
        assert new_token is not None
        assert new_token["tier"] == "extracted"

        # Verify token values copied
        cursor = memory_db.execute(f"SELECT COUNT(*) FROM token_values WHERE token_id = {new_token['id']}")
        assert cursor.fetchone()[0] == 1

        # Verify binding reassigned
        cursor = memory_db.execute(f"SELECT token_id FROM node_token_bindings WHERE id = 1")
        assert cursor.fetchone()["token_id"] == new_token["id"]

    def test_split_token_invalid_binding(self, memory_db):
        with pytest.raises(ValueError, match="do not belong to token"):
            split_token(memory_db, 1, "color.new", [2])  # Binding 2 belongs to token 3

    def test_split_token_invalid_name(self, memory_db):
        with pytest.raises(ValueError, match="Invalid DTCG name"):
            split_token(memory_db, 1, "INVALID NAME", [1])


class TestRejectToken:
    def test_reject_token_success(self, file_db):
        conn, db_path = file_db
        result = reject_token(conn, 1, db_path)

        assert result["token_id"] == 1
        assert result["bindings_reverted"] == 1

        # Verify token deleted
        cursor = conn.execute("SELECT COUNT(*) FROM tokens WHERE id = 1")
        assert cursor.fetchone()[0] == 0

        # Verify bindings reverted to unbound
        cursor = conn.execute("""
            SELECT * FROM node_token_bindings
            WHERE property = 'fill.0.color' AND node_id = 1
        """)
        binding = cursor.fetchone()
        assert binding["token_id"] is None
        assert binding["binding_status"] == "unbound"
        assert binding["confidence"] is None

        # Verify backup created in the project backup directory
        from dd import config
        backup_dir = config.BACKUP_DIR
        assert backup_dir.exists()

    def test_reject_token_not_found(self, memory_db):
        with pytest.raises(ValueError, match="Token 999 does not exist"):
            reject_token(memory_db, 999)


class TestCreateAlias:
    def test_create_alias_success(self, memory_db):
        result = create_alias(memory_db, "color.brand", 1, 1)

        assert result["alias_id"] > 0
        assert result["alias_name"] == "color.brand"
        assert result["target_id"] == 1
        assert result["target_name"] == "color.primary"

        # Verify alias created
        cursor = memory_db.execute("SELECT * FROM tokens WHERE name = 'color.brand'")
        alias = cursor.fetchone()
        assert alias is not None
        assert alias["tier"] == "aliased"
        assert alias["alias_of"] == 1
        assert alias["type"] == "color"  # Same as target

    def test_create_alias_of_alias(self, memory_db):
        # First create an alias
        create_alias(memory_db, "color.brand", 1, 1)
        cursor = memory_db.execute("SELECT id FROM tokens WHERE name = 'color.brand'")
        alias_id = cursor.fetchone()["id"]

        # Try to create alias of an alias
        with pytest.raises(ValueError, match="cannot be an alias"):
            create_alias(memory_db, "color.brand2", alias_id, 1)

    def test_create_alias_duplicate_name(self, memory_db):
        with pytest.raises(ValueError, match="already exists"):
            create_alias(memory_db, "color.primary", 1, 1)  # Name already exists

    def test_create_alias_invalid_target(self, memory_db):
        with pytest.raises(ValueError, match="Target token 999 does not exist"):
            create_alias(memory_db, "color.brand", 999, 1)

    def test_create_alias_invalid_name(self, memory_db):
        with pytest.raises(ValueError, match="Invalid DTCG name"):
            create_alias(memory_db, "INVALID NAME", 1, 1)


class TestDTCGNameValidation:
    def test_valid_names(self):
        valid_names = [
            "color",
            "color.primary",
            "color.surface.primary",
            "space.s4",
            "type.body.md",
            "a",
            "a1",
            "a1.b2.c3",
        ]

        for name in valid_names:
            assert _validate_dtcg_name(name) is True

    def test_invalid_names(self):
        invalid_names = [
            "",              # empty
            "1",             # starts with number
            "1color",        # starts with number
            ".color",        # starts with dot
            "color.",        # ends with dot
            "color..primary", # double dot
            "color.Primary", # uppercase
            "color primary", # space
            "color-primary", # hyphen
            "color_primary", # underscore
            "color.primary!", # special char
        ]

        for name in invalid_names:
            assert _validate_dtcg_name(name) is False


class TestStatusReporting:
    """Tests for status reporting functions."""

    def test_status_functions_exist(self, memory_db):
        """Test that all status functions can be called."""
        # Test curation progress
        progress = get_curation_progress(memory_db)
        assert isinstance(progress, list)

        # Test token coverage
        coverage = get_token_coverage(memory_db)
        assert isinstance(coverage, list)

        # Test unbound summary
        unbound = get_unbound_summary(memory_db)
        assert isinstance(unbound, list)

        # Test export readiness
        readiness = get_export_readiness(memory_db)
        assert isinstance(readiness, list)

        # Test format status report
        report = format_status_report(memory_db)
        assert isinstance(report, str)

        # Test get status dict
        status_dict = get_status_dict(memory_db)
        assert isinstance(status_dict, dict)
        assert 'curation_progress' in status_dict
        assert 'token_count' in status_dict
        assert 'is_ready' in status_dict