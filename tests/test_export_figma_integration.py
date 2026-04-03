"""Integration tests for the curation-to-Figma-export pipeline.

Tests verify the boundary between curation output (Wave 4) and Figma export (Wave 5).
All tests use real DB (in-memory SQLite) and real curation output from fixtures.
"""

import json
import sqlite3

import pytest

from dd.curate import create_alias
from dd.export_figma_vars import (
    generate_variable_payloads,
    generate_variable_payloads_checked,
    get_sync_status_summary,
    writeback_variable_ids,
)
from dd.export_rebind import generate_rebind_scripts, get_rebind_summary
from dd.validate import run_validation
from tests.fixtures import seed_post_curation


@pytest.fixture
def db():
    """Create in-memory SQLite database with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Load schema
    with open("schema.sql") as f:
        conn.executescript(f.read())

    return conn


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_payloads_reference_valid_curated_tokens(db):
    """Test that all tokens in payloads are valid curated/aliased tokens."""
    # Seed with post-curation data
    seed_post_curation(db)

    # Generate payloads
    payloads = generate_variable_payloads(db, file_id=1)

    # Verify payloads generated
    assert len(payloads) > 0, "Expected at least one payload"

    # Build set of valid token names from DB
    cursor = db.execute("""
        SELECT t.name, tc.name as collection_name
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1 AND t.tier IN ('curated', 'aliased')
    """)
    valid_tokens = {}
    for row in cursor:
        if row["collection_name"] not in valid_tokens:
            valid_tokens[row["collection_name"]] = set()
        valid_tokens[row["collection_name"]].add(row["name"])

    # Verify each token in payloads
    for payload in payloads:
        collection_name = payload["collectionName"]
        assert collection_name in valid_tokens, f"Collection {collection_name} not in DB"

        for token in payload["tokens"]:
            # Convert Figma name back to DTCG
            dtcg_name = token["name"].replace("/", ".")

            # Verify token exists and is curated/aliased
            assert dtcg_name in valid_tokens[collection_name], (
                f"Token {dtcg_name} not found as curated/aliased in {collection_name}"
            )

    # Verify no extracted tokens in payloads
    cursor = db.execute("""
        SELECT COUNT(*) as count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1 AND t.tier = 'extracted'
    """)
    extracted_count = cursor.fetchone()["count"]
    if extracted_count > 0:
        # Ensure none of the extracted tokens appear in payloads
        cursor = db.execute("""
            SELECT t.name
            FROM tokens t
            JOIN token_collections tc ON t.collection_id = tc.id
            WHERE tc.file_id = 1 AND t.tier = 'extracted'
        """)
        extracted_names = {row["name"] for row in cursor}

        for payload in payloads:
            for token in payload["tokens"]:
                dtcg_name = token["name"].replace("/", ".")
                assert dtcg_name not in extracted_names, (
                    f"Extracted token {dtcg_name} should not be in payload"
                )


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_payload_batch_sizing(db):
    """Test that payloads respect MAX_TOKENS_PER_CALL batch size limit."""
    # Seed with post-curation data
    seed_post_curation(db)

    # Insert 120 additional curated tokens to exceed the 100-per-call limit
    for i in range(120):
        token_id = 100 + i
        db.execute("""
            INSERT INTO tokens (id, collection_id, name, type, tier)
            VALUES (?, 1, ?, 'color', 'curated')
        """, (token_id, f"color.test.{i}"))

        # Insert token value for default mode
        db.execute("""
            INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
            VALUES (?, 1, ?, ?)
        """, (token_id, json.dumps({"r": 0.5, "g": 0.5, "b": 0.5, "a": 1}), "#808080"))

    db.commit()

    # Generate payloads
    payloads = generate_variable_payloads(db, file_id=1)

    # Verify we have multiple payloads (should be at least 2 for Colors collection)
    colors_payloads = [p for p in payloads if p["collectionName"] == "Colors"]
    assert len(colors_payloads) >= 2, "Expected at least 2 payloads for Colors collection"

    # Verify each payload respects the 100 token limit
    for payload in payloads:
        assert len(payload["tokens"]) <= 100, (
            f"Payload has {len(payload['tokens'])} tokens, exceeds limit of 100"
        )

    # Verify total token count across all Colors payloads
    total_colors_tokens = sum(len(p["tokens"]) for p in colors_payloads)
    assert total_colors_tokens == 124, (
        f"Expected 124 total color tokens (4 original + 120 added), got {total_colors_tokens}"
    )

    # Verify Spacing collection still in single payload
    spacing_payloads = [p for p in payloads if p["collectionName"] == "Spacing"]
    assert len(spacing_payloads) == 1, "Spacing collection should be in single payload"
    assert len(spacing_payloads[0]["tokens"]) == 1, "Spacing should have 1 token"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_dtcg_to_figma_path_in_payloads(db):
    """Test that DTCG dot-paths are converted to Figma slash-paths in payloads."""
    # Seed with post-curation data
    seed_post_curation(db)

    # Generate payloads
    payloads = generate_variable_payloads(db, file_id=1)

    # Check all token names in payloads
    for payload in payloads:
        for token in payload["tokens"]:
            name = token["name"]

            # Verify uses slash separator, not dot
            assert "/" in name or "." not in name.split("/")[-1], (
                f"Token name '{name}' should use / separator"
            )

            # Verify no dots except potentially in the last segment
            # (e.g., "space/4" is valid, "space.4" would be invalid as a path)
            if "." in name:
                # Only the final segment can have dots (for decimal values)
                parts = name.split("/")
                for part in parts[:-1]:
                    assert "." not in part, f"Non-final segment '{part}' should not contain dots"

            # Verify no consecutive slashes
            assert "//" not in name, f"Token name '{name}' has consecutive slashes"

            # Verify no leading/trailing slashes
            assert not name.startswith("/"), f"Token name '{name}' has leading slash"
            assert not name.endswith("/"), f"Token name '{name}' has trailing slash"

    # Verify specific expected conversions
    colors_payload = next(p for p in payloads if p["collectionName"] == "Colors")
    token_names = {t["name"] for t in colors_payload["tokens"]}

    assert "color/surface/primary" in token_names, "Missing color/surface/primary"
    assert "color/surface/secondary" in token_names, "Missing color/surface/secondary"
    assert "color/border/default" in token_names, "Missing color/border/default"
    assert "color/text/primary" in token_names, "Missing color/text/primary"

    # Ensure dot-paths are NOT present
    assert "color.surface.primary" not in token_names, "Found unconverted dot-path"

    spacing_payload = next(p for p in payloads if p["collectionName"] == "Spacing")
    spacing_names = {t["name"] for t in spacing_payload["tokens"]}
    assert "space/4" in spacing_names, "Missing space/4"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_multi_mode_values_in_payloads(db):
    """Test that multi-mode tokens have values for all modes in payloads."""
    # Seed with post-curation data
    seed_post_curation(db)

    # Add a second mode "Dark" to the Colors collection
    db.execute("""
        INSERT INTO token_modes (id, collection_id, name, is_default)
        VALUES (3, 1, 'Dark', 0)
    """)

    # Add Dark mode values for all 4 color tokens
    dark_values = [
        (1, 3, json.dumps({"r": 0.9, "g": 0.9, "b": 0.9, "a": 1}), "#E6E6E6"),  # color.surface.primary
        (2, 3, json.dumps({"r": 0.8, "g": 0.8, "b": 0.8, "a": 1}), "#CCCCCC"),  # color.surface.secondary
        (3, 3, json.dumps({"r": 0.3, "g": 0.3, "b": 0.3, "a": 1}), "#4D4D4D"),  # color.border.default
        (4, 3, json.dumps({"r": 0.1, "g": 0.1, "b": 0.1, "a": 1}), "#1A1A1A"),  # color.text.primary
    ]
    for token_id, mode_id, raw_value, resolved_value in dark_values:
        db.execute("""
            INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
            VALUES (?, ?, ?, ?)
        """, (token_id, mode_id, raw_value, resolved_value))

    db.commit()

    # Generate payloads
    payloads = generate_variable_payloads(db, file_id=1)

    # Find Colors payload
    colors_payload = next(p for p in payloads if p["collectionName"] == "Colors")

    # Verify modes list contains both Default and Dark
    assert "Default" in colors_payload["modes"], "Missing Default mode"
    assert "Dark" in colors_payload["modes"], "Missing Dark mode"
    assert len(colors_payload["modes"]) == 2, "Should have exactly 2 modes"

    # Verify each token has values for both modes
    for token in colors_payload["tokens"]:
        assert "Default" in token["values"], f"Token {token['name']} missing Default value"
        assert "Dark" in token["values"], f"Token {token['name']} missing Dark value"

        # Verify values are non-empty strings
        assert token["values"]["Default"], f"Token {token['name']} has empty Default value"
        assert token["values"]["Dark"], f"Token {token['name']} has empty Dark value"
        assert isinstance(token["values"]["Default"], str), "Default value should be string"
        assert isinstance(token["values"]["Dark"], str), "Dark value should be string"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_rebind_scripts_syntactically_valid(db):
    """Test that rebind scripts are syntactically valid JavaScript."""
    # Seed with post-curation data
    seed_post_curation(db)

    # Set figma_variable_id on all tokens (simulate successful export)
    db.execute("""
        UPDATE tokens
        SET figma_variable_id = 'V:' || id || ':test',
            sync_status = 'synced'
        WHERE tier IN ('curated', 'aliased')
    """)
    db.commit()

    # Generate rebind scripts
    scripts = generate_rebind_scripts(db, file_id=1)

    # Verify we have scripts
    assert len(scripts) > 0, "Expected at least one rebind script"

    for i, script in enumerate(scripts):
        # Verify it's a non-empty string
        assert script, f"Script {i} is empty"
        assert isinstance(script, str), f"Script {i} is not a string"

        # Verify compact IIFE structure
        assert script.startswith("(async()=>{"), f"Script {i} doesn't start with compact async IIFE"
        assert script.endswith("})();"), f"Script {i} doesn't end with }})();"

        # Verify key API calls present in compact handler
        assert "figma.getNodeByIdAsync" in script, f"Script {i} missing getNodeByIdAsync"
        assert "figma.variables.getVariableByIdAsync" in script, f"Script {i} missing getVariableByIdAsync"

        # Verify balanced braces
        open_braces = script.count("{")
        close_braces = script.count("}")
        assert open_braces == close_braces, (
            f"Script {i} has unbalanced braces: {open_braces} open, {close_braces} close"
        )

        # Verify balanced parentheses
        open_parens = script.count("(")
        close_parens = script.count(")")
        assert open_parens == close_parens, (
            f"Script {i} has unbalanced parentheses: {open_parens} open, {close_parens} close"
        )

        # Verify compact data string is present
        assert "const D='" in script, f"Script {i} missing compact data string"

        # Verify notification at end
        assert "figma.notify" in script, f"Script {i} missing notification"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_rebind_scripts_cover_all_property_types(db):
    """Test that rebind scripts cover all property handler categories."""
    # Seed with post-curation data
    seed_post_curation(db)

    # Create radius and effect tokens and bind them
    # Add radius token
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier, figma_variable_id, sync_status)
        VALUES (6, 2, 'radius.default', 'dimension', 'curated', 'V:6:test', 'synced')
    """)
    db.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (6, 2, '{"value": 8, "unit": "px"}', '8')
    """)

    # Add effect radius token
    db.execute("""
        INSERT INTO tokens (id, collection_id, name, type, tier, figma_variable_id, sync_status)
        VALUES (7, 2, 'effect.shadow.radius', 'dimension', 'curated', 'V:7:test', 'synced')
    """)
    db.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        VALUES (7, 2, '{"value": 6, "unit": "px"}', '6')
    """)

    # Link spacing bindings to the spacing token
    db.execute("""
        UPDATE node_token_bindings
        SET token_id = 5, binding_status = 'bound'
        WHERE property IN ('padding.top', 'padding.bottom', 'itemSpacing')
    """)

    # Link radius bindings
    db.execute("""
        UPDATE node_token_bindings
        SET token_id = 6, binding_status = 'bound'
        WHERE property = 'cornerRadius'
    """)

    # Link effect bindings
    db.execute("""
        UPDATE node_token_bindings
        SET token_id = 7, binding_status = 'bound'
        WHERE property = 'effect.0.radius'
    """)

    # Set figma_variable_id on all tokens
    db.execute("""
        UPDATE tokens
        SET figma_variable_id = 'V:' || id || ':test',
            sync_status = 'synced'
        WHERE tier IN ('curated', 'aliased') AND figma_variable_id IS NULL
    """)
    db.commit()

    # Generate rebind scripts
    scripts = generate_rebind_scripts(db, file_id=1)

    # Extract property shortcodes from compact pipe-delimited data
    all_shortcodes = set()
    for script in scripts:
        data_start = script.find("const D='") + len("const D='")
        data_end = script.find("';", data_start)
        if data_start > -1 and data_end > -1:
            data_str = script[data_start:data_end]
            for line in data_str.split("\\n"):
                if line:
                    parts = line.split("|")
                    if len(parts) >= 2:
                        all_shortcodes.add(parts[1])

    # Verify we have fill bindings (shortcode f0, f1, etc.)
    fill_codes = [c for c in all_shortcodes if c.startswith("f") and c[1:].isdigit()]
    assert len(fill_codes) > 0, "Missing fill shortcodes (f0, f1, etc.)"

    # Verify we have spacing bindings (pt, pr, pb, pl, is)
    spacing_codes = [c for c in all_shortcodes if c in ("pt", "pr", "pb", "pl", "is")]
    assert len(spacing_codes) > 0, "Missing spacing shortcodes (pt/pr/pb/pl/is)"

    # Verify we have radius bindings (cr)
    radius_codes = [c for c in all_shortcodes if c in ("cr", "tlr", "trr", "blr", "brr")]
    assert len(radius_codes) > 0, "Missing radius shortcodes (cr, tlr, etc.)"

    # Verify we have effect bindings (e0c, e0r, etc.)
    effect_codes = [c for c in all_shortcodes if c.startswith("e") and len(c) >= 2 and c[1].isdigit()]
    assert len(effect_codes) > 0, "Missing effect shortcodes (e0c, e0r, etc.)"

    # Use get_rebind_summary to verify property type distribution
    summary = get_rebind_summary(db, file_id=1)

    assert summary["total_bindings"] > 0, "No bindable entries found"
    assert "paint_fill" in summary["by_property_type"], "Missing paint_fill property type"
    assert "padding" in summary["by_property_type"] or "direct" in summary["by_property_type"], (
        "Missing padding or direct property types"
    )

    # Verify effect properties in summary
    if effect_codes:
        assert "effect" in summary["by_property_type"], "Missing effect property type in summary"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_writeback_after_payload_generation(db):
    """Test that writeback correctly updates tokens after payload generation."""
    # Seed with post-curation data
    seed_post_curation(db)

    # Generate payloads
    payloads = generate_variable_payloads(db, file_id=1)

    # Build mock Figma response matching the tokens in the payloads
    mock_response = {
        "collections": [
            {
                "id": "VC:1",
                "name": "Colors",
                "modes": [{"id": "M:1", "name": "Default"}],
                "variables": [
                    {"id": "V:1:1", "name": "color/surface/primary", "type": "COLOR"},
                    {"id": "V:1:2", "name": "color/surface/secondary", "type": "COLOR"},
                    {"id": "V:1:3", "name": "color/border/default", "type": "COLOR"},
                    {"id": "V:1:4", "name": "color/text/primary", "type": "COLOR"},
                ]
            },
            {
                "id": "VC:2",
                "name": "Spacing",
                "modes": [{"id": "M:2", "name": "Default"}],
                "variables": [
                    {"id": "V:2:1", "name": "space/4", "type": "FLOAT"},
                ]
            }
        ]
    }

    # Parse and writeback
    from dd.export_figma_vars import parse_figma_variables_response
    parsed = parse_figma_variables_response(mock_response)
    result = writeback_variable_ids(db, file_id=1, figma_variables=parsed)

    # Verify writeback counts
    assert result["tokens_updated"] == 5, f"Expected 5 tokens updated, got {result['tokens_updated']}"
    assert result["tokens_not_found"] == 0, f"Unexpected tokens not found: {result['tokens_not_found']}"
    assert result["collections_updated"] == 2, f"Expected 2 collections updated, got {result['collections_updated']}"

    # Verify tokens now have figma_variable_id set
    cursor = db.execute("""
        SELECT t.id, t.name, t.figma_variable_id, t.sync_status
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1 AND t.tier IN ('curated', 'aliased')
    """)

    for row in cursor:
        assert row["figma_variable_id"] is not None, f"Token {row['name']} missing figma_variable_id"
        assert row["sync_status"] == "synced", f"Token {row['name']} not marked as synced"

    # Verify collections have figma_id set
    cursor = db.execute("""
        SELECT name, figma_id FROM token_collections WHERE file_id = 1
    """)
    for row in cursor:
        assert row["figma_id"] is not None, f"Collection {row['name']} missing figma_id"

    # Verify get_sync_status_summary shows synced
    summary = get_sync_status_summary(db, file_id=1)
    assert summary.get("synced", 0) == 5, f"Expected 5 synced tokens, got {summary}"
    assert summary.get("pending", 0) == 0, f"Expected 0 pending tokens, got {summary}"

    # Re-generate payloads: should return empty list (all tokens have figma_variable_id)
    new_payloads = generate_variable_payloads(db, file_id=1)
    assert len(new_payloads) == 0, "Expected no payloads after writeback (all tokens synced)"


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_aliased_tokens_in_payloads(db):
    """Test that aliased tokens appear in payloads with correct resolved values."""
    # Seed with post-curation data
    seed_post_curation(db)

    # Create alias "color.bg" -> token 1 (color.surface.primary)
    result = create_alias(db, alias_name="color.bg", target_token_id=1, collection_id=1)
    assert "alias_id" in result, f"Failed to create alias: {result}"

    # Add token_value for alias (should resolve to target's value)
    alias_id = result["alias_id"]
    db.execute("""
        INSERT INTO token_values (token_id, mode_id, raw_value, resolved_value)
        SELECT ?, mode_id, raw_value, resolved_value
        FROM token_values
        WHERE token_id = 1
    """, (alias_id,))
    db.commit()

    # Generate payloads
    payloads = generate_variable_payloads(db, file_id=1)

    # Find Colors payload
    colors_payload = next(p for p in payloads if p["collectionName"] == "Colors")

    # Find alias token in payload
    alias_token = next((t for t in colors_payload["tokens"] if t["name"] == "color/bg"), None)
    assert alias_token is not None, "Alias token color/bg not found in payload"

    # Find target token in payload
    target_token = next(t for t in colors_payload["tokens"] if t["name"] == "color/surface/primary")

    # Verify alias has same resolved values as target
    assert alias_token["values"] == target_token["values"], (
        f"Alias values {alias_token['values']} don't match target {target_token['values']}"
    )

    # Verify specific expected value
    assert alias_token["values"]["Default"] == "#09090B", (
        f"Alias Default value incorrect: {alias_token['values']['Default']}"
    )


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_export_pipeline_end_to_end_from_curation(db):
    """Test the complete export pipeline from curation to rebind scripts."""
    # Seed with post-curation data
    seed_post_curation(db)

    # Run validation
    validation_result = run_validation(db, file_id=1)
    assert validation_result["passed"], f"Validation failed: {validation_result}"
    assert validation_result["errors"] == 0, "Validation has errors"

    # Generate payloads with validation check
    payloads = generate_variable_payloads_checked(db, file_id=1)
    assert len(payloads) > 0, "No payloads generated"

    # Count total tokens in payloads
    total_tokens = sum(len(p["tokens"]) for p in payloads)
    assert total_tokens == 5, f"Expected 5 tokens in payloads, got {total_tokens}"

    # Build mock Figma response for all tokens
    mock_response = {
        "collections": []
    }

    for payload in payloads:
        collection = {
            "id": f"VC:{len(mock_response['collections']) + 1}",
            "name": payload["collectionName"],
            "modes": [{"id": f"M:{i+1}", "name": mode} for i, mode in enumerate(payload["modes"])],
            "variables": []
        }

        for token in payload["tokens"]:
            collection["variables"].append({
                "id": f"V:{len(collection['variables']) + 1}",
                "name": token["name"],
                "type": token["type"]
            })

        mock_response["collections"].append(collection)

    # Writeback variable IDs
    from dd.export_figma_vars import parse_figma_variables_response
    parsed = parse_figma_variables_response(mock_response)
    writeback_result = writeback_variable_ids(db, file_id=1, figma_variables=parsed)

    assert writeback_result["tokens_updated"] == 5, f"Expected 5 tokens updated: {writeback_result}"

    # Verify all curated tokens have figma_variable_id
    cursor = db.execute("""
        SELECT COUNT(*) as count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
          AND t.tier IN ('curated', 'aliased')
          AND t.figma_variable_id IS NOT NULL
    """)
    synced_count = cursor.fetchone()["count"]
    assert synced_count == 5, f"Expected 5 synced tokens, got {synced_count}"

    # Verify all have sync_status='synced'
    cursor = db.execute("""
        SELECT COUNT(*) as count
        FROM tokens t
        JOIN token_collections tc ON t.collection_id = tc.id
        WHERE tc.file_id = 1
          AND t.tier IN ('curated', 'aliased')
          AND t.sync_status = 'synced'
    """)
    synced_status_count = cursor.fetchone()["count"]
    assert synced_status_count == 5, f"Expected 5 tokens with synced status, got {synced_status_count}"

    # Generate rebind scripts
    rebind_scripts = generate_rebind_scripts(db, file_id=1)
    assert len(rebind_scripts) > 0, "No rebind scripts generated"

    # Verify rebind scripts encode variable IDs in compact pipe-delimited data
    for script in rebind_scripts:
        # In compact format, variable ID suffixes appear after the second pipe
        # e.g., "200:1|f0|1:test" where "1:test" is the suffix of "V:1:test"
        data_start = script.find("const D='") + len("const D='")
        data_end = script.find("';", data_start)
        data_str = script[data_start:data_end]
        assert data_str, "Script has empty data string"
        # Each line should have a variable ID suffix (third field)
        for line in data_str.split("\\n"):
            if line:
                parts = line.split("|")
                assert len(parts) == 3, f"Expected 3 pipe-delimited fields, got {len(parts)}"
                assert parts[2], f"Missing variable ID suffix in line: {line}"

    # Get rebind summary
    rebind_summary = get_rebind_summary(db, file_id=1)
    assert rebind_summary["total_bindings"] > 0, "No bindings found in summary"

    # Verify summary matches expected binding counts from fixture
    # Fixture has 15 bindings total, but some may be unbindable
    assert rebind_summary["total_bindings"] <= 15, (
        f"More bindings than expected: {rebind_summary['total_bindings']}"
    )

    # Verify property type distribution
    assert len(rebind_summary["by_property_type"]) > 0, "No property types in summary"