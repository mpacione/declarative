"""Test export_figma_vars module for Figma variable payload generation."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from dd.config import MAX_TOKENS_PER_CALL
from dd.export_figma_vars import (
    dtcg_to_figma_path,
    generate_variable_payloads,
    generate_variable_payloads_checked,
    get_mode_names_for_collection,
    map_token_type_to_figma,
    query_exportable_tokens,
)


@pytest.fixture
def temp_db():
    """Create a temporary database with schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmpfile:
        db_path = Path(tmpfile.name)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create minimal schema for testing
    conn.executescript("""
        CREATE TABLE files (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        );

        CREATE TABLE token_collections (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id),
            figma_id TEXT,
            name TEXT NOT NULL,
            description TEXT
        );

        CREATE TABLE token_modes (
            id INTEGER PRIMARY KEY,
            collection_id INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
            figma_mode_id TEXT,
            name TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            UNIQUE(collection_id, name)
        );

        CREATE TABLE tokens (
            id INTEGER PRIMARY KEY,
            collection_id INTEGER NOT NULL REFERENCES token_collections(id),
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            tier TEXT NOT NULL DEFAULT 'extracted'
                CHECK(tier IN ('extracted', 'curated', 'aliased')),
            alias_of INTEGER REFERENCES tokens(id),
            description TEXT,
            figma_variable_id TEXT,
            sync_status TEXT NOT NULL DEFAULT 'pending'
                CHECK(sync_status IN ('pending', 'figma_only', 'code_only', 'synced', 'drifted')),
            UNIQUE(collection_id, name)
        );

        CREATE TABLE token_values (
            id INTEGER PRIMARY KEY,
            token_id INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
            mode_id INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
            raw_value TEXT NOT NULL,
            resolved_value TEXT NOT NULL,
            UNIQUE(token_id, mode_id)
        );

        CREATE TABLE export_validations (
            id INTEGER PRIMARY KEY,
            run_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            check_name TEXT NOT NULL,
            severity TEXT NOT NULL CHECK(severity IN ('error', 'warning', 'info')),
            message TEXT NOT NULL,
            affected_ids TEXT,
            resolved INTEGER NOT NULL DEFAULT 0
        );
    """)

    yield conn

    conn.close()
    db_path.unlink()


@pytest.fixture
def populated_db(temp_db):
    """Create a database populated with test data."""
    conn = temp_db

    # Create a file
    cursor = conn.execute("INSERT INTO files (name) VALUES ('test.figma')")
    file_id = cursor.lastrowid

    # Create collections
    cursor = conn.execute("INSERT INTO token_collections (file_id, name) VALUES (?, 'Colors')", (file_id,))
    colors_collection_id = cursor.lastrowid

    cursor = conn.execute("INSERT INTO token_collections (file_id, name) VALUES (?, 'Spacing')", (file_id,))
    spacing_collection_id = cursor.lastrowid

    # Create modes
    cursor = conn.execute("INSERT INTO token_modes (collection_id, name, is_default) VALUES (?, 'Light', 1)", (colors_collection_id,))
    light_mode_id = cursor.lastrowid
    cursor = conn.execute("INSERT INTO token_modes (collection_id, name, is_default) VALUES (?, 'Dark', 0)", (colors_collection_id,))
    dark_mode_id = cursor.lastrowid

    cursor = conn.execute("INSERT INTO token_modes (collection_id, name, is_default) VALUES (?, 'Default', 1)", (spacing_collection_id,))
    default_mode_id = cursor.lastrowid

    # Create tokens
    # Curated color token (ready for export)
    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id)
        VALUES (?, 'color.surface.primary', 'color', 'curated', NULL)
    """, (colors_collection_id,))
    primary_token_id = cursor.lastrowid

    # Add values for both modes
    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (?, ?, '#09090B', '#09090B')
    """, (primary_token_id, light_mode_id))
    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (?, ?, '#FAFAFA', '#FAFAFA')
    """, (primary_token_id, dark_mode_id))

    # Another curated color token
    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id)
        VALUES (?, 'color.surface.secondary', 'color', 'curated', NULL)
    """, (colors_collection_id,))
    secondary_token_id = cursor.lastrowid

    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (?, ?, '#18181B', '#18181B')
    """, (secondary_token_id, light_mode_id))
    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (?, ?, '#F4F4F5', '#F4F4F5')
    """, (secondary_token_id, dark_mode_id))

    # Aliased token that references primary
    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id, alias_of)
        VALUES (?, 'color.button.primary', 'color', 'aliased', NULL, ?)
    """, (colors_collection_id, primary_token_id))
    alias_token_id = cursor.lastrowid

    # Curated spacing token
    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id)
        VALUES (?, 'space.4', 'dimension', 'curated', NULL)
    """, (spacing_collection_id,))
    space_token_id = cursor.lastrowid

    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (?, ?, '16', '16')
    """, (space_token_id, default_mode_id))

    # Extracted token (should not be exported)
    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier)
        VALUES (?, 'color.text.body', 'color', 'extracted')
    """, (colors_collection_id,))
    extracted_token_id = cursor.lastrowid

    conn.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (?, ?, '#000000', '#000000')
    """, (extracted_token_id, light_mode_id))

    # Token with existing figma_variable_id (should not be exported)
    conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id)
        VALUES (?, 'color.already.synced', 'color', 'curated', 'VariableID:123:456')
    """, (colors_collection_id,))

    conn.commit()

    return conn, file_id


class TestNameConversion:
    """Test DTCG to Figma path conversion."""

    def test_dtcg_to_figma_path_simple(self):
        """Test simple dot to slash conversion."""
        assert dtcg_to_figma_path("color.surface.primary") == "color/surface/primary"

    def test_dtcg_to_figma_path_numeric(self):
        """Test conversion with numeric segments."""
        assert dtcg_to_figma_path("space.4") == "space/4"

    def test_dtcg_to_figma_path_single(self):
        """Test single segment (no dots)."""
        assert dtcg_to_figma_path("primary") == "primary"

    def test_dtcg_to_figma_path_empty(self):
        """Test empty string."""
        assert dtcg_to_figma_path("") == ""


class TestTypeMapping:
    """Test DTCG to Figma type mapping."""

    def test_map_token_type_color(self):
        """Test color type mapping."""
        assert map_token_type_to_figma("color", "color.surface.primary") == "COLOR"

    def test_map_token_type_dimension(self):
        """Test dimension type mapping."""
        assert map_token_type_to_figma("dimension", "space.4") == "FLOAT"

    def test_map_token_type_font_family(self):
        """Test fontFamily type mapping."""
        assert map_token_type_to_figma("fontFamily", "type.body.md.fontFamily") == "STRING"

    def test_map_token_type_font_weight(self):
        """Test fontWeight type mapping."""
        assert map_token_type_to_figma("fontWeight", "type.body.md.fontWeight") == "FLOAT"

    def test_map_token_type_font_style(self):
        """Test fontStyle type mapping."""
        assert map_token_type_to_figma("fontStyle", "type.body.fontStyle") == "STRING"

    def test_map_token_type_number(self):
        """Test number type mapping."""
        assert map_token_type_to_figma("number", "opacity.50") == "FLOAT"

    def test_map_token_type_shadow_color(self):
        """Test shadow color field mapping (name-based override)."""
        assert map_token_type_to_figma("shadow", "shadow.sm.color") == "COLOR"
        assert map_token_type_to_figma("dimension", "shadow.sm.color") == "COLOR"

    def test_map_token_type_shadow_radius(self):
        """Test shadow non-color field mapping."""
        assert map_token_type_to_figma("shadow", "shadow.sm.radius") == "FLOAT"

    def test_map_token_type_border(self):
        """Test border type mapping."""
        assert map_token_type_to_figma("border", "border.thin") == "FLOAT"

    def test_map_token_type_gradient(self):
        """Test gradient type mapping."""
        assert map_token_type_to_figma("gradient", "gradient.sunset") == "COLOR"


class TestQueryExportable:
    """Test query_exportable_tokens function."""

    def test_query_exportable_tokens_basic(self, populated_db):
        """Test querying exportable tokens."""
        conn, file_id = populated_db
        tokens = query_exportable_tokens(conn, file_id)

        # Should get 4 tokens: 2 curated colors, 1 aliased color, 1 curated spacing
        # (not the extracted one, not the already-synced one)
        assert len(tokens) == 4

        # Check primary color token
        primary = next(t for t in tokens if t["name"] == "color.surface.primary")
        assert primary["type"] == "color"
        assert primary["tier"] == "curated"
        assert primary["collection_name"] == "Colors"
        assert primary["values"]["Light"] == "#09090B"
        assert primary["values"]["Dark"] == "#FAFAFA"

        # Check aliased token
        alias = next(t for t in tokens if t["name"] == "color.button.primary")
        assert alias["tier"] == "aliased"
        assert alias["alias_of"] is not None
        # Aliased tokens should have the target's values
        assert alias["values"]["Light"] == "#09090B"
        assert alias["values"]["Dark"] == "#FAFAFA"

        # Check spacing token
        space = next(t for t in tokens if t["name"] == "space.4")
        assert space["type"] == "dimension"
        assert space["collection_name"] == "Spacing"
        assert space["values"]["Default"] == "16"

    def test_query_exportable_tokens_empty(self, temp_db):
        """Test with no exportable tokens."""
        conn = temp_db
        cursor = conn.execute("INSERT INTO files (name) VALUES ('empty.figma')")
        file_id = cursor.lastrowid
        conn.commit()

        tokens = query_exportable_tokens(conn, file_id)
        assert tokens == []


class TestGetModeNames:
    """Test get_mode_names_for_collection function."""

    def test_get_mode_names_ordered(self, populated_db):
        """Test getting mode names with default first."""
        conn, _ = populated_db

        # Get Colors collection modes
        colors_collection_id = conn.execute(
            "SELECT id FROM token_collections WHERE name = 'Colors'"
        ).fetchone()[0]
        modes = get_mode_names_for_collection(conn, colors_collection_id)
        assert modes == ["Light", "Dark"]  # Light is default

        # Get Spacing collection modes
        spacing_collection_id = conn.execute(
            "SELECT id FROM token_collections WHERE name = 'Spacing'"
        ).fetchone()[0]
        modes = get_mode_names_for_collection(conn, spacing_collection_id)
        assert modes == ["Default"]


class TestPayloadGeneration:
    """Test generate_variable_payloads function."""

    def test_generate_payloads_basic(self, populated_db):
        """Test basic payload generation."""
        conn, file_id = populated_db
        payloads = generate_variable_payloads(conn, file_id)

        # Should have 2 payloads (one per collection)
        assert len(payloads) == 2

        # Find Colors payload
        colors_payload = next(p for p in payloads if p["collectionName"] == "Colors")
        assert colors_payload["modes"] == ["Light", "Dark"]
        assert len(colors_payload["tokens"]) == 3  # primary, secondary, alias

        # Check token conversion
        primary_token = next(t for t in colors_payload["tokens"] if t["name"] == "color/surface/primary")
        assert primary_token["type"] == "COLOR"
        assert primary_token["values"]["Light"] == "#09090B"
        assert primary_token["values"]["Dark"] == "#FAFAFA"

        # Check aliased token
        alias_token = next(t for t in colors_payload["tokens"] if t["name"] == "color/button/primary")
        assert alias_token["type"] == "COLOR"
        assert alias_token["values"]["Light"] == "#09090B"  # Should use target's values
        assert alias_token["values"]["Dark"] == "#FAFAFA"

        # Find Spacing payload
        spacing_payload = next(p for p in payloads if p["collectionName"] == "Spacing")
        assert spacing_payload["modes"] == ["Default"]
        assert len(spacing_payload["tokens"]) == 1

        space_token = spacing_payload["tokens"][0]
        assert space_token["name"] == "space/4"
        assert space_token["type"] == "FLOAT"
        assert space_token["values"]["Default"] == "16"

    def test_generate_payloads_batching(self, temp_db):
        """Test that payloads are batched to MAX_TOKENS_PER_CALL."""
        conn = temp_db

        # Create a file and collection
        cursor = conn.execute("INSERT INTO files (name) VALUES ('large.figma')")
        file_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO token_collections (file_id, name) VALUES (?, 'LargeCollection')", (file_id,))
        collection_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO token_modes (collection_id, name, is_default) VALUES (?, 'Default', 1)", (collection_id,))
        mode_id = cursor.lastrowid

        # Create 150 tokens (should result in 2 payloads)
        for i in range(150):
            cursor = conn.execute("""
                INSERT INTO tokens (collection_id, name, type, tier)
                VALUES (?, ?, 'color', 'curated')
            """, (collection_id, f"color.test.token{i}"))
            token_id = cursor.lastrowid
            conn.execute("""
                INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
                VALUES (?, ?, '#FF0000', '#FF0000')
            """, (token_id, mode_id))

        conn.commit()

        payloads = generate_variable_payloads(conn, file_id)
        assert len(payloads) == 2
        assert len(payloads[0]["tokens"]) == MAX_TOKENS_PER_CALL
        assert len(payloads[1]["tokens"]) == 50

    def test_generate_payloads_empty(self, temp_db):
        """Test with no tokens to export."""
        conn = temp_db
        cursor = conn.execute("INSERT INTO files (name) VALUES ('empty.figma')")
        file_id = cursor.lastrowid
        conn.commit()

        payloads = generate_variable_payloads(conn, file_id)
        assert payloads == []


class TestPayloadGenerationChecked:
    """Test generate_variable_payloads_checked with validation checks."""

    def test_generate_payloads_checked_valid(self, populated_db):
        """Test with passing validation."""
        conn, file_id = populated_db

        # Insert a passing validation run (no errors)
        conn.execute("""
            INSERT INTO export_validations (check_name, severity, message)
            VALUES ('test_check', 'info', 'All good')
        """)
        conn.commit()

        # Should work normally
        payloads = generate_variable_payloads_checked(conn, file_id)
        assert len(payloads) == 2

    def test_generate_payloads_checked_error(self, populated_db):
        """Test with validation errors."""
        conn, file_id = populated_db

        # Insert a validation run with errors
        conn.execute("""
            INSERT INTO export_validations (check_name, severity, message)
            VALUES ('test_check', 'error', 'Something is wrong')
        """)
        conn.commit()

        # Should raise error
        with pytest.raises(RuntimeError, match="Export blocked: validation errors exist"):
            generate_variable_payloads_checked(conn, file_id)

    def test_generate_payloads_checked_no_validation(self, populated_db):
        """Test with no validation runs."""
        conn, file_id = populated_db

        # Should raise error (no validation run)
        with pytest.raises(RuntimeError, match="Export blocked: validation errors exist"):
            generate_variable_payloads_checked(conn, file_id)

    def test_generate_payloads_checked_warnings_ok(self, populated_db):
        """Test that warnings don't block export."""
        conn, file_id = populated_db

        # Insert a validation run with only warnings
        conn.execute("""
            INSERT INTO export_validations (check_name, severity, message)
            VALUES ('test_check', 'warning', 'Minor issue')
        """)
        conn.commit()

        # Should work normally (warnings don't block)
        payloads = generate_variable_payloads_checked(conn, file_id)
        assert len(payloads) == 2