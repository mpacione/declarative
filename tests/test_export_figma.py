"""Test export_figma_vars module for Figma variable payload generation."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from dd.config import MAX_TOKENS_PER_CALL
from dd.export_figma_vars import (
    dtcg_to_figma_path,
    figma_path_to_dtcg,
    generate_variable_payloads,
    generate_variable_payloads_checked,
    get_mode_names_for_collection,
    get_sync_status_summary,
    map_token_type_to_figma,
    parse_figma_variables_response,
    query_exportable_tokens,
    writeback_variable_ids,
    writeback_variable_ids_from_response,
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
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
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
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id, sync_status)
        VALUES (?, 'color.already.synced', 'color', 'curated', 'VariableID:123:456', 'synced')
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


class TestPathConversionRoundtrip:
    """Test bidirectional path conversion."""

    def test_figma_path_to_dtcg_simple(self):
        """Test simple slash to dot conversion."""
        assert figma_path_to_dtcg("color/surface/primary") == "color.surface.primary"

    def test_figma_path_to_dtcg_numeric(self):
        """Test conversion with numeric segments."""
        assert figma_path_to_dtcg("space/4") == "space.4"

    def test_figma_path_to_dtcg_single(self):
        """Test single segment (no slashes)."""
        assert figma_path_to_dtcg("primary") == "primary"

    def test_figma_path_to_dtcg_empty(self):
        """Test empty string."""
        assert figma_path_to_dtcg("") == ""

    def test_roundtrip_conversion(self):
        """Test that conversions are inverse operations."""
        original = "color.surface.primary.button"
        assert figma_path_to_dtcg(dtcg_to_figma_path(original)) == original

        figma_original = "color/surface/primary/button"
        assert dtcg_to_figma_path(figma_path_to_dtcg(figma_original)) == figma_original


class TestParseFigmaResponseProper:
    """Test parse_figma_variables_response function."""

    def test_parse_standard_response(self):
        """Test parsing standard Figma variables response."""
        response = {
            "collections": [
                {
                    "id": "VariableCollectionID:123",
                    "name": "Colors",
                    "modes": [
                        {"id": "modeId:1", "name": "Light"},
                        {"id": "modeId:2", "name": "Dark"}
                    ],
                    "variables": [
                        {
                            "id": "VariableID:123:456",
                            "name": "color/surface/primary",
                            "type": "COLOR"
                        },
                        {
                            "id": "VariableID:123:457",
                            "name": "color/surface/secondary",
                            "type": "COLOR"
                        }
                    ]
                },
                {
                    "id": "VariableCollectionID:124",
                    "name": "Spacing",
                    "modes": [
                        {"id": "modeId:3", "name": "Default"}
                    ],
                    "variables": [
                        {
                            "id": "VariableID:124:100",
                            "name": "space/4",
                            "type": "FLOAT"
                        }
                    ]
                }
            ]
        }

        parsed = parse_figma_variables_response(response)
        assert len(parsed) == 3

        # Check first variable
        var1 = next(v for v in parsed if v["variable_id"] == "VariableID:123:456")
        assert var1["name"] == "color.surface.primary"  # Converted to DTCG
        assert var1["collection_name"] == "Colors"
        assert var1["collection_id"] == "VariableCollectionID:123"
        assert len(var1["modes"]) == 2

        # Check spacing variable
        space = next(v for v in parsed if v["variable_id"] == "VariableID:124:100")
        assert space["name"] == "space.4"  # Converted to DTCG
        assert space["collection_name"] == "Spacing"

    def test_parse_list_response(self):
        """Test parsing when response is a list instead of dict."""
        response = [
            {
                "id": "VariableCollectionID:123",
                "name": "Colors",
                "modes": [{"id": "modeId:1", "name": "Light"}],
                "variables": [
                    {
                        "id": "VariableID:123:456",
                        "name": "color/primary",
                        "type": "COLOR"
                    }
                ]
            }
        ]

        parsed = parse_figma_variables_response(response)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "color.primary"

    def test_parse_empty_response(self):
        """Test parsing empty response."""
        assert parse_figma_variables_response({"collections": []}) == []
        assert parse_figma_variables_response([]) == []
        assert parse_figma_variables_response({}) == []

    def test_parse_missing_fields(self):
        """Test parsing with missing optional fields."""
        response = {
            "collections": [
                {
                    "id": "VariableCollectionID:123",
                    "name": "Colors",
                    # No modes field
                    "variables": [
                        {
                            "id": "VariableID:123:456",
                            "name": "color/primary"
                            # No type field
                        }
                    ]
                }
            ]
        }

        parsed = parse_figma_variables_response(response)
        assert len(parsed) == 1
        assert parsed[0]["modes"] == []


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


class TestParseFigmaResponse:
    """Test parse_figma_variables_response function."""

    def test_parse_standard_response(self):
        """Test parsing standard Figma variables response."""
        response = {
            "collections": [
                {
                    "id": "VariableCollectionID:123",
                    "name": "Colors",
                    "modes": [
                        {"id": "modeId:1", "name": "Light"},
                        {"id": "modeId:2", "name": "Dark"}
                    ],
                    "variables": [
                        {
                            "id": "VariableID:123:456",
                            "name": "color/surface/primary",
                            "type": "COLOR"
                        },
                        {
                            "id": "VariableID:123:457",
                            "name": "color/surface/secondary",
                            "type": "COLOR"
                        }
                    ]
                },
                {
                    "id": "VariableCollectionID:124",
                    "name": "Spacing",
                    "modes": [
                        {"id": "modeId:3", "name": "Default"}
                    ],
                    "variables": [
                        {
                            "id": "VariableID:124:100",
                            "name": "space/4",
                            "type": "FLOAT"
                        }
                    ]
                }
            ]
        }

        parsed = parse_figma_variables_response(response)
        assert len(parsed) == 3

        # Check first variable
        var1 = next(v for v in parsed if v["variable_id"] == "VariableID:123:456")
        assert var1["name"] == "color.surface.primary"  # Converted to DTCG
        assert var1["collection_name"] == "Colors"
        assert var1["collection_id"] == "VariableCollectionID:123"
        assert len(var1["modes"]) == 2

        # Check spacing variable
        space = next(v for v in parsed if v["variable_id"] == "VariableID:124:100")
        assert space["name"] == "space.4"  # Converted to DTCG
        assert space["collection_name"] == "Spacing"

    def test_parse_list_response(self):
        """Test parsing when response is a list instead of dict."""
        response = [
            {
                "id": "VariableCollectionID:123",
                "name": "Colors",
                "modes": [{"id": "modeId:1", "name": "Light"}],
                "variables": [
                    {
                        "id": "VariableID:123:456",
                        "name": "color/primary",
                        "type": "COLOR"
                    }
                ]
            }
        ]

        parsed = parse_figma_variables_response(response)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "color.primary"

    def test_parse_empty_response(self):
        """Test parsing empty response."""
        assert parse_figma_variables_response({"collections": []}) == []
        assert parse_figma_variables_response([]) == []
        assert parse_figma_variables_response({}) == []

    def test_parse_missing_fields(self):
        """Test parsing with missing optional fields."""
        response = {
            "collections": [
                {
                    "id": "VariableCollectionID:123",
                    "name": "Colors",
                    # No modes field
                    "variables": [
                        {
                            "id": "VariableID:123:456",
                            "name": "color/primary"
                            # No type field
                        }
                    ]
                }
            ]
        }

        parsed = parse_figma_variables_response(response)
        assert len(parsed) == 1
        assert parsed[0]["modes"] == []


class TestWritebackVariableIds:
    """Test writeback_variable_ids function."""

    def test_writeback_basic(self, populated_db):
        """Test basic variable ID writeback."""
        conn, file_id = populated_db

        # Prepare parsed Figma variables
        figma_variables = [
            {
                "variable_id": "VariableID:123:456",
                "name": "color.surface.primary",
                "collection_name": "Colors",
                "collection_id": "VariableCollectionID:123",
                "modes": [
                    {"id": "modeId:1", "name": "Light"},
                    {"id": "modeId:2", "name": "Dark"}
                ]
            },
            {
                "variable_id": "VariableID:123:457",
                "name": "color.surface.secondary",
                "collection_name": "Colors",
                "collection_id": "VariableCollectionID:123",
                "modes": [
                    {"id": "modeId:1", "name": "Light"},
                    {"id": "modeId:2", "name": "Dark"}
                ]
            },
            {
                "variable_id": "VariableID:124:100",
                "name": "space.4",
                "collection_name": "Spacing",
                "collection_id": "VariableCollectionID:124",
                "modes": [
                    {"id": "modeId:3", "name": "Default"}
                ]
            }
        ]

        result = writeback_variable_ids(conn, file_id, figma_variables)

        # Check result counts
        assert result["tokens_updated"] == 3
        assert result["tokens_not_found"] == 0
        assert result["collections_updated"] == 2
        assert result["modes_updated"] == 3

        # Verify database updates
        cursor = conn.execute("""
            SELECT figma_variable_id, sync_status FROM tokens
            WHERE name = 'color.surface.primary'
        """)
        row = cursor.fetchone()
        assert row["figma_variable_id"] == "VariableID:123:456"
        assert row["sync_status"] == "synced"

        # Check collection update
        cursor = conn.execute("""
            SELECT figma_id FROM token_collections WHERE name = 'Colors'
        """)
        assert cursor.fetchone()["figma_id"] == "VariableCollectionID:123"

        # Check mode update
        cursor = conn.execute("""
            SELECT figma_mode_id FROM token_modes WHERE name = 'Light'
        """)
        assert cursor.fetchone()["figma_mode_id"] == "modeId:1"

    def test_writeback_not_found(self, populated_db):
        """Test writeback with non-matching tokens."""
        conn, file_id = populated_db

        figma_variables = [
            {
                "variable_id": "VariableID:999:999",
                "name": "color.does.not.exist",
                "collection_name": "Colors",
                "collection_id": "VariableCollectionID:123",
                "modes": []
            }
        ]

        result = writeback_variable_ids(conn, file_id, figma_variables)

        assert result["tokens_updated"] == 0
        assert result["tokens_not_found"] == 1

    def test_writeback_aliased_token(self, populated_db):
        """Test writeback for aliased tokens."""
        conn, file_id = populated_db

        figma_variables = [
            {
                "variable_id": "VariableID:125:001",
                "name": "color.button.primary",  # This is an aliased token
                "collection_name": "Colors",
                "collection_id": "VariableCollectionID:123",
                "modes": []
            }
        ]

        result = writeback_variable_ids(conn, file_id, figma_variables)

        # Should update the aliased token
        assert result["tokens_updated"] == 1

        # Verify aliased token was updated
        cursor = conn.execute("""
            SELECT figma_variable_id, sync_status FROM tokens
            WHERE name = 'color.button.primary'
        """)
        row = cursor.fetchone()
        assert row["figma_variable_id"] == "VariableID:125:001"
        assert row["sync_status"] == "synced"

    def test_writeback_from_response(self, populated_db):
        """Test convenience wrapper writeback_variable_ids_from_response."""
        conn, file_id = populated_db

        raw_response = {
            "collections": [
                {
                    "id": "VariableCollectionID:123",
                    "name": "Colors",
                    "modes": [],
                    "variables": [
                        {
                            "id": "VariableID:123:456",
                            "name": "color/surface/primary",
                            "type": "COLOR"
                        }
                    ]
                }
            ]
        }

        result = writeback_variable_ids_from_response(conn, file_id, raw_response)

        assert result["tokens_updated"] == 1
        assert result["collections_updated"] == 1


class TestSyncStatusSummary:
    """Test get_sync_status_summary function."""

    def test_sync_status_summary(self, populated_db):
        """Test getting sync status summary."""
        conn, file_id = populated_db

        # Update some tokens to have different statuses
        conn.execute("""
            UPDATE tokens SET sync_status = 'synced'
            WHERE name = 'color.surface.primary'
        """)
        conn.execute("""
            UPDATE tokens SET sync_status = 'drifted'
            WHERE name = 'color.surface.secondary'
        """)
        conn.commit()

        summary = get_sync_status_summary(conn, file_id)

        # Should have counts for each status
        # Tokens created: primary, secondary, button.primary (alias), space.4, text.body (extracted), already.synced
        # After updates: primary->synced, secondary->drifted, already.synced was already synced
        # Remaining pending: button.primary (alias), space.4, text.body (extracted)
        assert summary["pending"] == 3  # button.primary, space.4, text.body
        assert summary["synced"] == 2  # primary + already.synced
        assert summary["drifted"] == 1  # secondary

    def test_sync_status_summary_empty(self, temp_db):
        """Test summary with no tokens."""
        conn = temp_db
        cursor = conn.execute("INSERT INTO files (name) VALUES ('empty.figma')")
        file_id = cursor.lastrowid
        conn.commit()

        summary = get_sync_status_summary(conn, file_id)

        # Empty dict if no tokens
        assert summary == {}