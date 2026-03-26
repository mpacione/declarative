"""Unit tests for export payload generation and rebind script generation."""

import json
import pytest
import sqlite3
from typing import Any, Dict, List

from dd.config import MAX_BINDINGS_PER_SCRIPT, MAX_TOKENS_PER_CALL
from dd.export_figma_vars import (
    DTCG_TO_FIGMA_TYPE,
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
from dd.export_rebind import (
    PROPERTY_HANDLERS,
    classify_property,
    generate_rebind_scripts,
    generate_single_script,
    get_rebind_summary,
    query_bindable_entries,
)
from tests.fixtures import seed_post_curation, seed_post_validation


# Helper Functions
def _seed_with_figma_ids(db: sqlite3.Connection) -> sqlite3.Connection:
    """Seed post-curation and add figma_variable_ids to simulate post-writeback state."""
    seed_post_curation(db)

    # Update tokens with figma_variable_id
    cursor = db.execute("SELECT id FROM tokens WHERE tier IN ('curated', 'aliased')")
    for i, row in enumerate(cursor.fetchall(), start=1):
        db.execute(
            "UPDATE tokens SET figma_variable_id = ? WHERE id = ?",
            (f"VariableID:1:{i}", row["id"])
        )

    db.commit()
    return db


def _make_mock_figma_response(token_names: List[str]) -> Dict[str, Any]:
    """Build a mock figma_get_variables response."""
    return {
        "collections": [
            {
                "id": "VariableCollectionId:1:1",
                "name": "Colors",
                "modes": [
                    {"id": "1:0", "name": "Default"}
                ],
                "variables": [
                    {
                        "id": f"VariableID:1:{i}",
                        "name": dtcg_to_figma_path(name)
                    }
                    for i, name in enumerate(token_names, start=1)
                ]
            }
        ]
    }


def _seed_many_tokens(db: sqlite3.Connection, count: int) -> sqlite3.Connection:
    """Seed post-curation then insert additional curated tokens."""
    seed_post_curation(db)

    # Get collection ID
    cursor = db.execute("SELECT id FROM token_collections WHERE name = 'Colors'")
    collection_id = cursor.fetchone()["id"]

    # Get mode ID
    cursor = db.execute("SELECT id FROM token_modes WHERE collection_id = ?", (collection_id,))
    mode_id = cursor.fetchone()["id"]

    # Get max token ID
    cursor = db.execute("SELECT MAX(id) AS max_id FROM tokens")
    max_id = cursor.fetchone()["max_id"] or 0

    # Insert additional tokens
    for i in range(1, count + 1):
        token_id = max_id + i
        db.execute(
            "INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (?, ?, ?, ?, ?)",
            (token_id, collection_id, f"color.generated.token{i:03d}", "color", "curated")
        )

        # Insert token value
        db.execute(
            """INSERT INTO token_values (id, token_id, mode_id, raw_value, resolved_value)
               VALUES (?, ?, ?, ?, ?)""",
            (token_id * 100, token_id, mode_id,
             json.dumps({"r": 0.5, "g": 0.5, "b": 0.5, "a": 1}), "#808080")
        )

    db.commit()
    return db


# Test Group 1: Name conversion tests
@pytest.mark.unit
def test_dtcg_to_figma_path_basic():
    """Test basic dot to slash conversion."""
    assert dtcg_to_figma_path("color.surface.primary") == "color/surface/primary"


@pytest.mark.unit
def test_dtcg_to_figma_path_single():
    """Test single segment (no dots)."""
    assert dtcg_to_figma_path("color") == "color"


@pytest.mark.unit
def test_dtcg_to_figma_path_numeric():
    """Test numeric segments."""
    assert dtcg_to_figma_path("space.4") == "space/4"


@pytest.mark.unit
def test_dtcg_to_figma_path_deep():
    """Test deep nested path."""
    assert dtcg_to_figma_path("type.body.md.fontSize") == "type/body/md/fontSize"


@pytest.mark.unit
def test_figma_path_to_dtcg_basic():
    """Test basic slash to dot conversion."""
    assert figma_path_to_dtcg("color/surface/primary") == "color.surface.primary"


@pytest.mark.unit
def test_figma_path_to_dtcg_roundtrip():
    """Test roundtrip conversion maintains original."""
    original = "color.surface.primary"
    figma = dtcg_to_figma_path(original)
    back = figma_path_to_dtcg(figma)
    assert back == original


# Test Group 2: Type mapping tests
@pytest.mark.unit
def test_type_mapping_color():
    """Test color type maps to COLOR."""
    assert map_token_type_to_figma("color", "color.surface.primary") == "COLOR"


@pytest.mark.unit
def test_type_mapping_dimension():
    """Test dimension type maps to FLOAT."""
    assert map_token_type_to_figma("dimension", "space.4") == "FLOAT"


@pytest.mark.unit
def test_type_mapping_font_family():
    """Test fontFamily type maps to STRING."""
    assert map_token_type_to_figma("fontFamily", "type.body.md.fontFamily") == "STRING"


@pytest.mark.unit
def test_type_mapping_font_weight():
    """Test fontWeight type maps to FLOAT."""
    assert map_token_type_to_figma("fontWeight", "type.body.md.fontWeight") == "FLOAT"


@pytest.mark.unit
def test_type_mapping_shadow_color_by_name():
    """Test shadow.color maps to COLOR by name override."""
    assert map_token_type_to_figma("dimension", "shadow.sm.color") == "COLOR"


@pytest.mark.unit
def test_type_mapping_font_style():
    """Test fontStyle type maps to STRING."""
    assert map_token_type_to_figma("fontStyle", "type.body.md.fontStyle") == "STRING"


# Test Group 3: Payload generation tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_payload_format(db):
    """Test payload has correct top-level keys."""
    seed_post_curation(db)

    payloads = generate_variable_payloads(db, 1)

    assert len(payloads) > 0
    for payload in payloads:
        assert "collectionName" in payload
        assert "modes" in payload
        assert "tokens" in payload
        assert isinstance(payload["tokens"], list)
        assert isinstance(payload["modes"], list)


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_payload_token_names_use_slashes(db):
    """Test all token names in payloads use slashes not dots."""
    seed_post_curation(db)

    payloads = generate_variable_payloads(db, 1)

    for payload in payloads:
        for token in payload["tokens"]:
            assert "." not in token["name"]
            assert "/" in token["name"] or len(token["name"].split("/")) == 1


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_payload_token_types_are_figma_types(db):
    """Test all token types are valid Figma types."""
    seed_post_curation(db)

    payloads = generate_variable_payloads(db, 1)
    valid_types = {"COLOR", "FLOAT", "STRING"}

    for payload in payloads:
        for token in payload["tokens"]:
            assert token["type"] in valid_types


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_payload_batch_size(db):
    """Test payloads respect MAX_TOKENS_PER_CALL limit."""
    _seed_many_tokens(db, 150)

    payloads = generate_variable_payloads(db, 1)

    assert len(payloads) >= 2  # Should have at least 2 batches
    for payload in payloads:
        assert len(payload["tokens"]) <= MAX_TOKENS_PER_CALL


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_payload_modes_match_collection(db):
    """Test payload modes match collection modes from DB."""
    seed_post_curation(db)

    payloads = generate_variable_payloads(db, 1)

    for payload in payloads:
        if payload["collectionName"] == "Colors":
            assert payload["modes"] == ["Default"]
        elif payload["collectionName"] == "Spacing":
            assert payload["modes"] == ["Default"]


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_payload_values_per_mode(db):
    """Test each token has values dict with keys matching modes."""
    seed_post_curation(db)

    payloads = generate_variable_payloads(db, 1)

    for payload in payloads:
        modes = payload["modes"]
        for token in payload["tokens"]:
            assert "values" in token
            assert isinstance(token["values"], dict)
            for mode in modes:
                assert mode in token["values"]


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_payload_only_curated_tokens(db):
    """Test payloads only include curated/aliased tokens."""
    seed_post_curation(db)

    # Add an extracted (non-curated) token
    db.execute(
        "INSERT INTO tokens (id, collection_id, name, type, tier) VALUES (?, ?, ?, ?, ?)",
        (100, 1, "color.not.curated", "color", "extracted")
    )
    db.commit()

    payloads = generate_variable_payloads(db, 1)

    # Check that non-curated token is not in payloads
    for payload in payloads:
        for token in payload["tokens"]:
            assert "not/curated" not in token["name"]


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_payload_skips_already_exported(db):
    """Test tokens with figma_variable_id are excluded."""
    seed_post_curation(db)

    # Set figma_variable_id on one token
    db.execute(
        "UPDATE tokens SET figma_variable_id = ? WHERE name = ?",
        ("VariableID:1:1", "color.surface.primary")
    )
    db.commit()

    tokens = query_exportable_tokens(db, 1)

    # Should not include the token with figma_variable_id
    token_names = [t["name"] for t in tokens]
    assert "color.surface.primary" not in token_names


# Test Group 4: Validation gate tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_checked_payload_passes_when_valid(db):
    """Test checked payload generation succeeds with valid data."""
    seed_post_validation(db)

    payloads = generate_variable_payloads_checked(db, 1)
    assert len(payloads) > 0


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_checked_payload_blocks_on_errors(db):
    """Test checked payload blocks when validation hasn't run."""
    seed_post_curation(db)  # No validation data

    with pytest.raises(RuntimeError) as exc_info:
        generate_variable_payloads_checked(db, 1)

    assert "validation errors exist" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_checked_payload_blocks_with_error_validations(db):
    """Test checked payload blocks with error-severity validations."""
    seed_post_validation(db)

    # Add an error validation
    db.execute(
        """INSERT INTO export_validations (check_name, severity, message, affected_ids, resolved)
           VALUES (?, ?, ?, ?, ?)""",
        ("test_error", "error", "Test error", json.dumps([1]), 0)
    )
    db.commit()

    with pytest.raises(RuntimeError) as exc_info:
        generate_variable_payloads_checked(db, 1)

    assert "validation errors exist" in str(exc_info.value)


# Test Group 5: Writeback tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_writeback_updates_variable_id(db):
    """Test writeback sets figma_variable_id on tokens."""
    seed_post_curation(db)

    figma_vars = [
        {
            "variable_id": "VariableID:1:1",
            "name": "color.surface.primary",
            "collection_name": "Colors",
            "collection_id": "VariableCollectionId:1:1",
            "modes": []
        }
    ]

    result = writeback_variable_ids(db, 1, figma_vars)

    assert result["tokens_updated"] == 1

    # Verify token has figma_variable_id
    cursor = db.execute("SELECT figma_variable_id FROM tokens WHERE name = ?", ("color.surface.primary",))
    row = cursor.fetchone()
    assert row["figma_variable_id"] == "VariableID:1:1"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_writeback_updates_sync_status(db):
    """Test writeback sets sync_status to 'synced'."""
    seed_post_curation(db)

    figma_vars = [
        {
            "variable_id": "VariableID:1:1",
            "name": "color.surface.primary",
            "collection_name": "Colors",
            "collection_id": "VariableCollectionId:1:1",
            "modes": []
        }
    ]

    writeback_variable_ids(db, 1, figma_vars)

    cursor = db.execute("SELECT sync_status FROM tokens WHERE name = ?", ("color.surface.primary",))
    row = cursor.fetchone()
    assert row["sync_status"] == "synced"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_writeback_unmatched_tokens(db):
    """Test writeback counts tokens not found."""
    seed_post_curation(db)

    figma_vars = [
        {
            "variable_id": "VariableID:1:999",
            "name": "color.does.not.exist",
            "collection_name": "Colors",
            "collection_id": "VariableCollectionId:1:1",
            "modes": []
        }
    ]

    result = writeback_variable_ids(db, 1, figma_vars)

    assert result["tokens_not_found"] == 1
    assert result["tokens_updated"] == 0


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_writeback_collection_id(db):
    """Test writeback updates collection figma_id."""
    seed_post_curation(db)

    figma_vars = [
        {
            "variable_id": "VariableID:1:1",
            "name": "color.surface.primary",
            "collection_name": "Colors",
            "collection_id": "VariableCollectionId:1:1",
            "modes": []
        }
    ]

    result = writeback_variable_ids(db, 1, figma_vars)

    assert result["collections_updated"] == 1

    cursor = db.execute("SELECT figma_id FROM token_collections WHERE name = ?", ("Colors",))
    row = cursor.fetchone()
    assert row["figma_id"] == "VariableCollectionId:1:1"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_sync_status_summary(db):
    """Test sync status summary returns correct counts."""
    _seed_with_figma_ids(db)

    # Mark some tokens as synced
    db.execute("UPDATE tokens SET sync_status = 'synced' WHERE id IN (1, 2)")
    db.execute("UPDATE tokens SET sync_status = 'pending' WHERE id = 3")
    db.commit()

    summary = get_sync_status_summary(db, 1)

    assert summary.get("synced", 0) == 2
    assert summary.get("pending", 0) >= 1  # At least 1 pending


# Test Group 6: Property classification tests
@pytest.mark.unit
def test_classify_fill_color():
    """Test fill.N.color classifies as paint_fill."""
    assert classify_property("fill.0.color") == "paint_fill"


@pytest.mark.unit
def test_classify_fill_index():
    """Test fill with different indices."""
    assert classify_property("fill.2.color") == "paint_fill"


@pytest.mark.unit
def test_classify_stroke_color():
    """Test stroke.N.color classifies as paint_stroke."""
    assert classify_property("stroke.0.color") == "paint_stroke"


@pytest.mark.unit
def test_classify_effect_color():
    """Test effect.N.color classifies as effect."""
    assert classify_property("effect.0.color") == "effect"


@pytest.mark.unit
def test_classify_effect_radius():
    """Test effect.N.radius classifies as effect."""
    assert classify_property("effect.0.radius") == "effect"


@pytest.mark.unit
def test_classify_effect_offset():
    """Test effect.N.offsetX classifies as effect."""
    assert classify_property("effect.1.offsetX") == "effect"


@pytest.mark.unit
def test_classify_padding():
    """Test padding.side classifies as padding."""
    assert classify_property("padding.top") == "padding"


@pytest.mark.unit
def test_classify_font_size():
    """Test fontSize classifies as direct."""
    assert classify_property("fontSize") == "direct"


@pytest.mark.unit
def test_classify_corner_radius():
    """Test cornerRadius classifies as direct."""
    assert classify_property("cornerRadius") == "direct"


@pytest.mark.unit
def test_classify_unknown():
    """Test unknown property classifies as unknown."""
    assert classify_property("fill.0.gradient") == "unknown"


# Test Group 7: Rebind script generation tests
@pytest.mark.unit
def test_script_is_async_iife():
    """Test script is an async IIFE."""
    script = generate_single_script([])

    assert script.startswith("(async () => {")
    assert script.endswith("})();")


@pytest.mark.unit
def test_script_contains_bindings_array():
    """Test script contains bindings array."""
    entries = [
        {
            "binding_id": 1,
            "node_id": "200:1",
            "property": "fontSize",
            "variable_id": "VariableID:1:1"
        }
    ]

    script = generate_single_script(entries)

    assert "const bindings = [" in script
    assert '"200:1"' in script
    assert '"fontSize"' in script
    assert '"VariableID:1:1"' in script


@pytest.mark.unit
def test_script_handles_fill_property():
    """Test script contains setBoundVariableForPaint for fills."""
    entries = [
        {
            "binding_id": 1,
            "node_id": "200:1",
            "property": "fill.0.color",
            "variable_id": "VariableID:1:1"
        }
    ]

    script = generate_single_script(entries)

    assert "setBoundVariableForPaint" in script
    assert "fills[idx]" in script


@pytest.mark.unit
def test_script_handles_effect_property():
    """Test script contains setBoundVariableForEffect for effects."""
    entries = [
        {
            "binding_id": 1,
            "node_id": "200:1",
            "property": "effect.0.radius",
            "variable_id": "VariableID:1:1"
        }
    ]

    script = generate_single_script(entries)

    assert "setBoundVariableForEffect" in script
    assert "effects[idx]" in script


@pytest.mark.unit
def test_script_handles_padding_conversion():
    """Test script converts padding.side to paddingSide."""
    entries = [
        {
            "binding_id": 1,
            "node_id": "200:1",
            "property": "padding.top",
            "variable_id": "VariableID:1:1"
        }
    ]

    script = generate_single_script(entries)

    # Check that the script contains the padding handling logic
    assert "b.property.startsWith('padding.')" in script
    assert "const side = b.property.split('.')[1]" in script
    assert "side.charAt(0).toUpperCase()" in script


@pytest.mark.unit
def test_script_handles_direct_property():
    """Test script uses setBoundVariable for direct properties."""
    entries = [
        {
            "binding_id": 1,
            "node_id": "200:1",
            "property": "fontSize",
            "variable_id": "VariableID:1:1"
        }
    ]

    script = generate_single_script(entries)

    assert "node.setBoundVariable" in script
    assert "'fontSize'" in script


@pytest.mark.unit
def test_script_syntax_valid():
    """Test script has balanced braces."""
    entries = [
        {
            "binding_id": 1,
            "node_id": "200:1",
            "property": "fontSize",
            "variable_id": "VariableID:1:1"
        },
        {
            "binding_id": 2,
            "node_id": "200:2",
            "property": "fill.0.color",
            "variable_id": "VariableID:1:2"
        }
    ]

    script = generate_single_script(entries)

    # Check balanced braces
    assert script.count("{") == script.count("}")
    assert script.count("(") == script.count(")")
    assert script.count("[") == script.count("]")


# Test Group 8: Rebind batch tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_rebind_batching(db):
    """Test rebind scripts respect MAX_BINDINGS_PER_SCRIPT."""
    _seed_with_figma_ids(db)

    # Create many new nodes to bind to (each binding must be unique node_id + property combo)
    for i in range(1, MAX_BINDINGS_PER_SCRIPT + 50):
        # Insert new node
        db.execute(
            """INSERT INTO nodes
               (id, screen_id, figma_node_id, name, node_type, is_semantic)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (100 + i, 1, f"300:{i}", f"Node {i}", "TEXT", 1)
        )
        # Insert binding for that node
        db.execute(
            """INSERT INTO node_token_bindings
               (id, node_id, property, token_id, raw_value, resolved_value, binding_status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (100 + i, 100 + i, "fontSize", 1, "16", "16", "bound")
        )
    db.commit()

    scripts = generate_rebind_scripts(db, 1)

    # Should have at least 2 scripts
    assert len(scripts) >= 2

    # Parse each script to count bindings
    for script in scripts:
        # Count occurrences of nodeId in bindings array
        binding_count = script.count('nodeId:')
        assert binding_count <= MAX_BINDINGS_PER_SCRIPT


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_rebind_scripts_cover_all_bound(db):
    """Test all bound bindings appear in scripts."""
    _seed_with_figma_ids(db)

    # Get all bindable entries (requires figma_variable_id on tokens and bound status)
    entries = query_bindable_entries(db, 1)
    entry_count = len(entries)

    scripts = generate_rebind_scripts(db, 1)

    # Count total bindings in all scripts
    total_bindings = 0
    for script in scripts:
        total_bindings += script.count('nodeId:')

    # Should have bindings for all bound entries that have figma_variable_ids
    assert total_bindings == entry_count


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_rebind_summary(db):
    """Test rebind summary returns correct counts."""
    _seed_with_figma_ids(db)

    summary = get_rebind_summary(db, 1)

    assert "total_bindings" in summary
    assert "script_count" in summary
    assert "by_property_type" in summary
    assert summary["total_bindings"] > 0
    assert summary["script_count"] > 0

    # Check property type breakdown
    if summary["by_property_type"]:
        for prop_type in summary["by_property_type"]:
            assert prop_type in ["paint_fill", "paint_stroke", "effect", "padding", "direct"]