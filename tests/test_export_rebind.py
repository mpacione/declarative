"""Test export_rebind module for rebind script generation."""

import math

import pytest

from dd.config import MAX_BINDINGS_PER_SCRIPT
from dd.export_rebind import (
    PROPERTY_HANDLERS,
    PROPERTY_SHORTCODES,
    classify_property,
    encode_property,
    generate_compact_script,
    generate_opacity_restore_scripts,
    generate_rebind_scripts,
    generate_single_script,
    get_rebind_summary,
    query_bindable_entries,
)


# Uses temp_db fixture from conftest.py (full schema via init_db)


def seed_file_and_collection(conn):
    """Insert minimum parent rows needed for rebind tests. Returns (file_id, coll_id, screen_id)."""
    cursor = conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'test.figma')")
    file_id = cursor.lastrowid
    cursor = conn.execute("INSERT INTO token_collections (file_id, name) VALUES (?, 'TestColors')", (file_id,))
    coll_id = cursor.lastrowid
    conn.execute("INSERT INTO token_modes (collection_id, name, is_default) VALUES (?, 'Default', 1)", (coll_id,))
    cursor = conn.execute("INSERT INTO screens (file_id, figma_node_id, name, width, height) VALUES (?, '1:100', 'Screen', 428, 926)", (file_id,))
    screen_id = cursor.lastrowid
    conn.commit()
    return file_id, coll_id, screen_id


@pytest.fixture
def populated_db(temp_db):
    """Create a database populated with test data."""
    conn = temp_db

    # Create a file
    cursor = conn.execute("INSERT INTO files (file_key, name) VALUES ('test123', 'test.figma')")
    file_id = cursor.lastrowid

    # Create collection + mode (required by real schema FK)
    cursor = conn.execute("INSERT INTO token_collections (file_id, name) VALUES (?, 'Colors')", (file_id,))
    coll_id = cursor.lastrowid
    conn.execute("INSERT INTO token_modes (collection_id, name, is_default) VALUES (?, 'Default', 1)", (coll_id,))

    # Create a screen
    cursor = conn.execute("INSERT INTO screens (file_id, figma_node_id, name, width, height) VALUES (?, '1:100', 'Screen 1', 428, 926)", (file_id,))
    screen_id = cursor.lastrowid

    # Create nodes
    cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name, node_type) VALUES (?, '2219:235701', 'Button', 'FRAME')", (screen_id,))
    node1_id = cursor.lastrowid
    cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name, node_type) VALUES (?, '2219:235702', 'Text', 'TEXT')", (screen_id,))
    node2_id = cursor.lastrowid
    cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name, node_type) VALUES (?, '2219:235703', 'Card', 'RECTANGLE')", (screen_id,))
    node3_id = cursor.lastrowid
    cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name, node_type) VALUES (?, '2219:235704', 'Frame', 'FRAME')", (screen_id,))
    node4_id = cursor.lastrowid

    # Create tokens with figma_variable_id
    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id)
        VALUES (?, 'color.primary', 'color', 'curated', 'VariableID:123:456')
    """, (coll_id,))
    token1_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id)
        VALUES (?, 'size.md', 'dimension', 'curated', 'VariableID:123:789')
    """, (coll_id,))
    token2_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id)
        VALUES (?, 'shadow.sm', 'color', 'curated', 'VariableID:123:012')
    """, (coll_id,))
    token3_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id)
        VALUES (?, 'space.4', 'dimension', 'curated', 'VariableID:123:345')
    """, (coll_id,))
    token4_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id)
        VALUES (?, 'radius.md', 'dimension', 'curated', 'VariableID:123:678')
    """, (coll_id,))
    token5_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, tier)
        VALUES (?, 'color.secondary', 'color', 'curated')
    """, (coll_id,))
    token6_id = cursor.lastrowid  # No figma_variable_id

    # Create bindings - mix of bound and unbound, with various property types
    # Bound bindings with figma_variable_id
    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
        VALUES (?, 'fill.0.color', ?, '#FF0000', '#FF0000', 'bound')
    """, (node1_id, token1_id))

    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
        VALUES (?, 'fontSize', ?, '16', '16', 'bound')
    """, (node2_id, token2_id))

    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
        VALUES (?, 'effect.0.color', ?, '#000000', '#000000', 'bound')
    """, (node3_id, token3_id))

    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
        VALUES (?, 'padding.top', ?, '16', '16', 'bound')
    """, (node4_id, token4_id))

    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
        VALUES (?, 'cornerRadius', ?, '8', '8', 'bound')
    """, (node1_id, token5_id))

    # Bound binding but token has no figma_variable_id (should be excluded)
    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
        VALUES (?, 'stroke.0.color', ?, '#00FF00', '#00FF00', 'bound')
    """, (node1_id, token6_id))

    # Unbound binding (should be excluded)
    conn.execute("""
        INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
        VALUES (?, 'opacity', NULL, '0.5', '0.5', 'unbound')
    """, (node2_id,))

    conn.commit()
    return conn, file_id


class TestPropertyHandlers:
    """Test PROPERTY_HANDLERS constant."""

    def test_property_handlers_exists(self):
        """Test that PROPERTY_HANDLERS is defined."""
        assert PROPERTY_HANDLERS is not None
        assert isinstance(PROPERTY_HANDLERS, dict)

    def test_property_handlers_has_expected_keys(self):
        """Test that PROPERTY_HANDLERS has expected property patterns."""
        expected_patterns = [
            "fill.N.color", "stroke.N.color", "effect.N.color", "effect.N.radius",
            "cornerRadius", "padding.top", "itemSpacing", "fontSize", "fontFamily"
        ]
        for pattern in expected_patterns:
            assert pattern in PROPERTY_HANDLERS


class TestClassifyProperty:
    """Test classify_property function."""

    def test_classify_fill_color(self):
        """Test classification of fill color properties."""
        assert classify_property("fill.0.color") == "paint_fill"
        assert classify_property("fill.1.color") == "paint_fill"
        assert classify_property("fill.99.color") == "paint_fill"

    def test_classify_stroke_color(self):
        """Test classification of stroke color properties."""
        assert classify_property("stroke.0.color") == "paint_stroke"
        assert classify_property("stroke.1.color") == "paint_stroke"

    def test_classify_effect(self):
        """Test classification of effect properties."""
        assert classify_property("effect.0.color") == "effect"
        assert classify_property("effect.0.radius") == "effect"
        assert classify_property("effect.1.offsetX") == "effect"
        assert classify_property("effect.1.offsetY") == "effect"
        assert classify_property("effect.2.spread") == "effect"

    def test_classify_padding(self):
        """Test classification of padding properties."""
        assert classify_property("padding.top") == "padding"
        assert classify_property("padding.right") == "padding"
        assert classify_property("padding.bottom") == "padding"
        assert classify_property("padding.left") == "padding"

    def test_classify_direct(self):
        """Test classification of direct bind properties."""
        assert classify_property("fontSize") == "direct"
        assert classify_property("fontFamily") == "direct"
        assert classify_property("fontWeight") == "direct"
        assert classify_property("fontStyle") == "direct"
        assert classify_property("lineHeight") == "direct"
        assert classify_property("letterSpacing") == "direct"
        assert classify_property("paragraphSpacing") == "direct"
        assert classify_property("cornerRadius") == "direct"
        assert classify_property("topLeftRadius") == "direct"
        assert classify_property("topRightRadius") == "direct"
        assert classify_property("bottomLeftRadius") == "direct"
        assert classify_property("bottomRightRadius") == "direct"
        assert classify_property("itemSpacing") == "direct"
        assert classify_property("counterAxisSpacing") == "direct"
        assert classify_property("opacity") == "direct"
        assert classify_property("strokeWeight") == "direct"
        assert classify_property("strokeTopWeight") == "direct"
        assert classify_property("strokeRightWeight") == "direct"
        assert classify_property("strokeBottomWeight") == "direct"
        assert classify_property("strokeLeftWeight") == "direct"

    def test_classify_unknown(self):
        """Test classification of unknown properties."""
        assert classify_property("unknown.property") == "unknown"
        assert classify_property("random") == "unknown"
        assert classify_property("fill.0") == "unknown"  # Missing .color
        assert classify_property("stroke.1") == "unknown"  # Missing .color


class TestQueryBindableEntries:
    """Test query_bindable_entries function."""

    def test_query_basic(self, populated_db):
        """Test querying bindable entries."""
        conn, file_id = populated_db
        entries = query_bindable_entries(conn, file_id)

        # Should get 5 entries (all bound with figma_variable_id, excluding stroke.0.color and opacity)
        assert len(entries) == 5

        # Check first entry structure
        entry = entries[0]
        assert "binding_id" in entry
        assert "node_id" in entry
        assert "property" in entry
        assert "variable_id" in entry

        # Check specific entries
        node_ids = [e["node_id"] for e in entries]
        assert "2219:235701" in node_ids
        assert "2219:235702" in node_ids
        assert "2219:235703" in node_ids
        assert "2219:235704" in node_ids

        properties = [e["property"] for e in entries]
        assert "fill.0.color" in properties
        assert "fontSize" in properties
        assert "effect.0.color" in properties
        assert "padding.top" in properties
        assert "cornerRadius" in properties

    def test_query_filters_unknown_properties(self, temp_db):
        """Test that unknown properties are filtered out."""
        conn = temp_db
        file_id, coll_id, screen_id = seed_file_and_collection(conn)
        cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name, node_type) VALUES (?, '1:101', 'Node', 'FRAME')", (screen_id,))
        node_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id) VALUES (?, 'test', 'color', 'curated', 'VariableID:123')", (coll_id,))
        token_id = cursor.lastrowid

        # Add binding with unknown property
        conn.execute("""
            INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
            VALUES (?, 'unknownProperty', ?, 'value', 'value', 'bound')
        """, (node_id, token_id))
        conn.commit()

        entries = query_bindable_entries(conn, file_id)
        assert len(entries) == 0  # Unknown property should be filtered

    def test_query_excludes_item_spacing_on_space_between(self, temp_db):
        """itemSpacing bindings should be excluded when node has SPACE_BETWEEN alignment."""
        conn = temp_db
        file_id, coll_id, screen_id = seed_file_and_collection(conn)

        # Node with SPACE_BETWEEN
        cursor = conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, primary_align) VALUES (?, '1:101', 'AutoNode', 'FRAME', 'SPACE_BETWEEN')",
            (screen_id,))
        auto_node_id = cursor.lastrowid

        # Node without SPACE_BETWEEN
        cursor = conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, primary_align) VALUES (?, '1:102', 'FixedNode', 'FRAME', 'MIN')",
            (screen_id,))
        fixed_node_id = cursor.lastrowid

        cursor = conn.execute("INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id) VALUES (?, 'space.s10', 'dimension', 'curated', 'VariableID:123')", (coll_id,))
        token_id = cursor.lastrowid

        # Both nodes get itemSpacing bindings
        conn.execute("""
            INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
            VALUES (?, 'itemSpacing', ?, '10', '10', 'bound')
        """, (auto_node_id, token_id))
        conn.execute("""
            INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
            VALUES (?, 'itemSpacing', ?, '10', '10', 'bound')
        """, (fixed_node_id, token_id))
        conn.commit()

        entries = query_bindable_entries(conn, file_id)

        node_ids = [e["node_id"] for e in entries]
        assert "1:102" in node_ids, "Fixed-spacing node should be included"
        assert "1:101" not in node_ids, "SPACE_BETWEEN node should be excluded"

    def test_query_empty(self, temp_db):
        """Test with no bindable entries."""
        conn = temp_db
        file_id, _, _ = seed_file_and_collection(conn)

        entries = query_bindable_entries(conn, file_id)
        assert entries == []


class TestGenerateSingleScript:
    """Test generate_single_script function."""

    def test_generate_basic_script(self):
        """Test basic script generation."""
        entries = [
            {"binding_id": 1, "node_id": "2219:235701", "property": "fill.0.color", "variable_id": "VariableID:123:456"},
            {"binding_id": 2, "node_id": "2219:235702", "property": "fontSize", "variable_id": "VariableID:123:789"},
        ]

        script = generate_single_script(entries)

        # Check script structure
        assert "(async () =>" in script
        assert "const bindings = [" in script
        assert 'nodeId: "2219:235701"' in script
        assert 'property: "fill.0.color"' in script
        assert 'variableId: "VariableID:123:456"' in script
        assert 'nodeId: "2219:235702"' in script
        assert 'property: "fontSize"' in script
        assert 'variableId: "VariableID:123:789"' in script
        assert "figma.getNodeByIdAsync" in script
        assert "figma.variables.getVariableByIdAsync" in script
        assert "figma.notify" in script
        assert "})();" in script

    def test_generate_script_with_all_property_types(self):
        """Test script generation with all property handler types."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "fill.0.color", "variable_id": "VariableID:1"},
            {"binding_id": 2, "node_id": "1:2", "property": "stroke.1.color", "variable_id": "VariableID:2"},
            {"binding_id": 3, "node_id": "1:3", "property": "effect.0.radius", "variable_id": "VariableID:3"},
            {"binding_id": 4, "node_id": "1:4", "property": "padding.top", "variable_id": "VariableID:4"},
            {"binding_id": 5, "node_id": "1:5", "property": "cornerRadius", "variable_id": "VariableID:5"},
        ]

        script = generate_single_script(entries)

        # Check for property handlers
        assert "if (b.property.startsWith('fill.') && b.property.endsWith('.color'))" in script
        assert "figma.variables.setBoundVariableForPaint(fills[idx], 'color', variable)" in script
        assert "if (b.property.startsWith('stroke.') && b.property.endsWith('.color'))" in script
        assert "figma.variables.setBoundVariableForPaint(strokes[idx], 'color', variable)" in script
        assert "if (b.property.startsWith('effect.'))" in script
        assert "figma.variables.setBoundVariableForEffect(effects[idx], field, variable)" in script
        assert "if (b.property.startsWith('padding.'))" in script
        assert "'padding' + side.charAt(0).toUpperCase() + side.slice(1)" in script
        assert "node.setBoundVariable(b.property, variable)" in script

    def test_generate_empty_script(self):
        """Test script generation with no entries."""
        script = generate_single_script([])

        # Should still generate valid script structure
        assert "(async () =>" in script
        assert "const bindings = []" in script
        assert "figma.notify" in script

    def test_script_valid_javascript(self):
        """Test that generated script is syntactically valid."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "fill.0.color", "variable_id": "VariableID:1"},
        ]

        script = generate_single_script(entries)

        # Check for balanced braces and parentheses
        assert script.count("{") == script.count("}")
        assert script.count("(") == script.count(")")
        assert script.count("[") == script.count("]")

        # Check for proper async IIFE structure
        assert script.startswith("(async () =>")
        assert script.endswith("})();")


class TestGenerateRebindScripts:
    """Test generate_rebind_scripts function."""

    def test_generate_scripts_batching(self, populated_db):
        """Test that scripts are batched correctly."""
        conn, file_id = populated_db
        scripts = generate_rebind_scripts(conn, file_id)

        # With 5 bindable entries and batch size 1500, should get 1 script
        assert len(scripts) == 1
        assert "(async()=>{" in scripts[0]

    def test_generate_scripts_large_batch(self, temp_db):
        """Test batching with many entries splits into correct number of scripts."""
        conn = temp_db
        file_id, coll_id, screen_id = seed_file_and_collection(conn)

        entry_count = 1500
        for i in range(entry_count):
            cursor = conn.execute(f"INSERT INTO nodes (screen_id, figma_node_id, name, node_type) VALUES (?, '1:{i}', 'Node{i}', 'FRAME')", (screen_id,))
            node_id = cursor.lastrowid
            cursor = conn.execute(f"INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id) VALUES (?, 'token{i}', 'color', 'curated', 'VariableID:{i}')", (coll_id,))
            token_id = cursor.lastrowid
            conn.execute("""
                INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
                VALUES (?, 'fill.0.color', ?, '#000000', '#000000', 'bound')
            """, (node_id, token_id))

        conn.commit()

        scripts = generate_rebind_scripts(conn, file_id)
        expected_scripts = math.ceil(entry_count / MAX_BINDINGS_PER_SCRIPT)
        assert len(scripts) == expected_scripts

        # Total bindings across all scripts should equal entry_count
        # Compact scripts use pipe-delimited lines, count by newlines in data
        total = sum(s.count('|f0|') for s in scripts)
        assert total == entry_count

    def test_generate_scripts_empty(self, temp_db):
        """Test with no scripts to generate."""
        conn = temp_db
        file_id, _, _ = seed_file_and_collection(conn)

        scripts = generate_rebind_scripts(conn, file_id)
        assert scripts == []


class TestPropertyShortcodes:
    """Test PROPERTY_SHORTCODES mapping and encode_property function."""

    def test_shortcodes_cover_all_known_properties(self):
        """Every classifiable property path has a shortcode."""
        known_properties = [
            "fill.0.color", "stroke.0.color", "effect.0.color", "effect.0.radius",
            "effect.0.offsetX", "effect.0.offsetY", "effect.0.spread",
            "cornerRadius", "topLeftRadius", "topRightRadius",
            "bottomLeftRadius", "bottomRightRadius",
            "padding.top", "padding.right", "padding.bottom", "padding.left",
            "itemSpacing", "counterAxisSpacing", "opacity",
            "strokeWeight", "strokeTopWeight", "strokeRightWeight",
            "strokeBottomWeight", "strokeLeftWeight",
            "fontSize", "fontFamily", "fontWeight", "fontStyle",
            "lineHeight", "letterSpacing", "paragraphSpacing",
        ]
        for prop in known_properties:
            code = encode_property(prop)
            assert code is not None, f"No shortcode for {prop}"
            assert len(code) <= 4, f"Shortcode too long for {prop}: {code}"

    def test_shortcodes_are_unique(self):
        """All shortcode values must be unique to avoid decode collisions."""
        values = list(PROPERTY_SHORTCODES.values())
        assert len(values) == len(set(values)), "Duplicate shortcode values found"

    def test_encode_fill_with_index(self):
        """Fill properties encode the paint index."""
        assert encode_property("fill.0.color") == "f0"
        assert encode_property("fill.1.color") == "f1"
        assert encode_property("fill.9.color") == "f9"

    def test_encode_stroke_with_index(self):
        """Stroke properties encode the paint index."""
        assert encode_property("stroke.0.color") == "s0"
        assert encode_property("stroke.2.color") == "s2"

    def test_encode_effect_with_index_and_field(self):
        """Effect properties encode index and field."""
        assert encode_property("effect.0.color") == "e0c"
        assert encode_property("effect.1.radius") == "e1r"
        assert encode_property("effect.0.offsetX") == "e0x"
        assert encode_property("effect.0.offsetY") == "e0y"
        assert encode_property("effect.2.spread") == "e2s"

    def test_encode_direct_properties(self):
        """Direct-bind properties use short fixed codes."""
        assert encode_property("cornerRadius") == "cr"
        assert encode_property("fontSize") == "fs"
        assert encode_property("padding.top") == "pt"

    def test_encode_unknown_returns_none(self):
        """Unknown properties return None."""
        assert encode_property("unknownProp") is None


class TestGenerateCompactScript:
    """Test generate_compact_script function."""

    def test_compact_script_uses_pipe_delimited_data(self):
        """Compact script encodes bindings as pipe-delimited string."""
        entries = [
            {"binding_id": 1, "node_id": "2219:235701", "property": "fill.0.color", "variable_id": "VariableID:123:456"},
            {"binding_id": 2, "node_id": "2219:235702", "property": "fontSize", "variable_id": "VariableID:123:789"},
        ]
        script = generate_compact_script(entries)

        # Should contain pipe-delimited data, not JSON objects
        assert "2219:235701|f0|123:456" in script
        assert "2219:235702|fs|123:789" in script
        assert "nodeId:" not in script

    def test_compact_script_strips_variable_id_prefix(self):
        """VariableID: prefix is stripped and reconstructed in handler."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "fill.0.color", "variable_id": "VariableID:5438:33595"},
        ]
        script = generate_compact_script(entries)

        assert "5438:33595" in script
        assert "VariableID:5438:33595" not in script.split("const D=")[1].split(";")[0]
        assert "VariableID:" in script  # Should be in the handler to reconstruct

    def test_compact_script_is_valid_structure(self):
        """Compact script has proper async IIFE structure."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "fill.0.color", "variable_id": "VariableID:1:2"},
        ]
        script = generate_compact_script(entries)

        assert script.startswith("(async()=>{")
        assert script.endswith("})();")
        assert script.count("{") == script.count("}")
        assert script.count("(") == script.count(")")

    def test_compact_script_handles_all_property_types(self):
        """Compact script handler supports all property type categories."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "fill.0.color", "variable_id": "VariableID:1:1"},
            {"binding_id": 2, "node_id": "1:2", "property": "stroke.0.color", "variable_id": "VariableID:1:2"},
            {"binding_id": 3, "node_id": "1:3", "property": "effect.0.color", "variable_id": "VariableID:1:3"},
            {"binding_id": 4, "node_id": "1:4", "property": "padding.top", "variable_id": "VariableID:1:4"},
            {"binding_id": 5, "node_id": "1:5", "property": "cornerRadius", "variable_id": "VariableID:1:5"},
            {"binding_id": 6, "node_id": "1:6", "property": "fontSize", "variable_id": "VariableID:1:6"},
        ]
        script = generate_compact_script(entries)

        assert "setBoundVariableForPaint" in script
        assert "setBoundVariableForEffect" in script
        assert "setBoundVariable" in script

    def test_compact_script_smaller_than_verbose(self):
        """Compact scripts are significantly smaller than verbose ones."""
        entries = [
            {"binding_id": i, "node_id": f"1:{i}", "property": "fill.0.color", "variable_id": f"VariableID:100:{i}"}
            for i in range(100)
        ]
        compact = generate_compact_script(entries)
        verbose = generate_single_script(entries)

        assert len(compact) < len(verbose) * 0.6

    def test_compact_script_fits_50k_with_1500_bindings(self):
        """1500 bindings should fit within the 50K char limit."""
        entries = [
            {"binding_id": i, "node_id": f"2219:{235700 + i}", "property": "stroke.0.color", "variable_id": f"VariableID:5438:{33000 + i}"}
            for i in range(1500)
        ]
        script = generate_compact_script(entries)

        assert len(script) < 50000, f"Script too large: {len(script)} chars"

    def test_compact_empty_entries(self):
        """Compact script handles empty entries list."""
        script = generate_compact_script([])
        assert script.startswith("(async()=>{")
        assert "figma.notify" in script

    def test_compact_handler_font_shortcodes_not_treated_as_fills(self):
        """Font shortcodes (fs, ff, fw, fst) must NOT match the fill branch (f0, f1)."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "fontSize", "variable_id": "VariableID:1:1"},
            {"binding_id": 2, "node_id": "1:2", "property": "fontFamily", "variable_id": "VariableID:1:2"},
            {"binding_id": 3, "node_id": "1:3", "property": "fontWeight", "variable_id": "VariableID:1:3"},
            {"binding_id": 4, "node_id": "1:4", "property": "fontStyle", "variable_id": "VariableID:1:4"},
            {"binding_id": 5, "node_id": "1:5", "property": "fill.0.color", "variable_id": "VariableID:1:5"},
        ]
        script = generate_compact_script(entries)

        assert "1:1|fs|" in script
        assert "1:5|f0|" in script
        # Fill branch (p[0]==='f') must also check digit, not just length
        # Otherwise fs/ff/fw (font properties) match the fill paint branch
        fill_branch_start = script.find("p[0]==='f'")
        assert fill_branch_start != -1
        # The fill condition must include a digit check before the closing )
        fill_condition = script[fill_branch_start:script.find("{", fill_branch_start)]
        assert "isNaN" in fill_condition or ">='0'" in fill_condition, (
            f"Fill branch missing digit check: {fill_condition}"
        )


class TestCompactHandlerAlphaBaked:
    """Test that compact handler relies on alpha-baked color variables (no manual opacity preservation)."""

    def test_handler_does_not_manually_preserve_fill_opacity(self):
        """Fill branch should NOT save/restore opacity — alpha is baked into the color variable."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "fill.0.color", "variable_id": "VariableID:1:1"},
        ]
        script = generate_compact_script(entries)

        fill_section = script[script.find("p[0]==='f'"):script.find("else if(p[0]==='s'")]
        assert "origOp" not in fill_section, "Fill branch should not preserve opacity manually"

    def test_handler_does_not_manually_preserve_stroke_opacity(self):
        """Stroke branch should NOT save/restore opacity — alpha is baked into the color variable."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "stroke.0.color", "variable_id": "VariableID:1:1"},
        ]
        script = generate_compact_script(entries)

        stroke_section = script[script.find("p[0]==='s'"):script.find("else if(p[0]==='e'")]
        assert "origOp" not in stroke_section, "Stroke branch should not preserve opacity manually"

    def test_handler_does_not_manually_preserve_effect_alpha(self):
        """Effect branch should NOT save/restore alpha — alpha is baked into the color variable."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "effect.0.color", "variable_id": "VariableID:1:1"},
        ]
        script = generate_compact_script(entries)

        effect_section = script[script.find("p[0]==='e'"):script.find("else{const M=")]
        assert "origA" not in effect_section, "Effect branch should not preserve alpha manually"

    def test_handler_skips_item_spacing_on_space_between(self):
        """itemSpacing binding must be skipped when node uses SPACE_BETWEEN (auto gap)."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "itemSpacing", "variable_id": "VariableID:1:1"},
        ]
        script = generate_compact_script(entries)

        assert "SPACE_BETWEEN" in script, "Handler must check for SPACE_BETWEEN before binding itemSpacing"


class TestCompactHandlerErrorPersistence:
    """Test that compact handler persists errors to figma.root.pluginData."""

    def test_handler_stores_errors_in_plugin_data(self):
        """Compact handler must write error details to figma.root.setPluginData."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "fill.0.color", "variable_id": "VariableID:1:1"},
        ]
        script = generate_compact_script(entries)

        assert "setPluginData" in script
        assert "rebind_errors" in script

    def test_handler_captures_error_reason(self):
        """Each failure should record nodeId, property code, and reason."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "fill.0.color", "variable_id": "VariableID:1:1"},
        ]
        script = generate_compact_script(entries)

        assert "NODE_NOT_FOUND" in script or "node_missing" in script
        assert "VAR_NOT_FOUND" in script or "var_missing" in script

    def test_handler_appends_not_overwrites(self):
        """Errors must append to existing plugin data, not overwrite previous batches."""
        entries = [
            {"binding_id": 1, "node_id": "1:1", "property": "fill.0.color", "variable_id": "VariableID:1:1"},
        ]
        script = generate_compact_script(entries)

        assert "getPluginData" in script
        assert "concat" in script or "push" in script or "..." in script

    def test_handler_still_fits_50k_with_error_logging(self):
        """Error logging overhead must not push 950-binding scripts over the 50K limit."""
        entries = [
            {"binding_id": i, "node_id": f"2219:{235700 + i}", "property": "stroke.0.color", "variable_id": f"VariableID:5438:{33000 + i}"}
            for i in range(950)
        ]
        script = generate_compact_script(entries)

        assert len(script) < 50000, f"Script too large with error logging: {len(script)} chars"


class TestGenerateErrorReadScript:
    """Test generate_error_read_script function."""

    def test_error_read_script_reads_plugin_data(self):
        """Should generate a script that reads rebind_errors from pluginData."""
        from dd.export_rebind import generate_error_read_script
        script = generate_error_read_script()

        assert "getPluginData" in script
        assert "rebind_errors" in script

    def test_error_read_script_returns_data(self):
        """Should return the error data for consumption."""
        from dd.export_rebind import generate_error_read_script
        script = generate_error_read_script()

        assert "return" in script or "console.log" in script


class TestGenerateErrorClearScript:
    """Test generate_error_clear_script function."""

    def test_error_clear_script_clears_plugin_data(self):
        """Should generate a script that clears rebind_errors from pluginData."""
        from dd.export_rebind import generate_error_clear_script
        script = generate_error_clear_script()

        assert "setPluginData" in script
        assert "rebind_errors" in script


class TestGenerateOpacityRestoreScripts:
    """Test generate_opacity_restore_scripts for restoring paint opacities and effect alphas."""

    def test_generates_scripts_for_sub_opacity_fills(self, temp_db):
        """Should generate restore scripts when fills have opacity < 1."""
        conn = temp_db
        file_id, _, screen_id = seed_file_and_collection(conn)
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, fills) VALUES (?, '1:101', 'SearchBar', 'FRAME', ?)",
            (screen_id, '[{"type":"SOLID","color":{"r":0.46,"g":0.46,"b":0.5,"a":1},"opacity":0.12,"visible":true}]')
        )
        conn.commit()

        scripts = generate_opacity_restore_scripts(conn, file_id=1)

        assert len(scripts) >= 1
        assert "1:101" in scripts[0]
        assert "0.12" in scripts[0]

    def test_generates_scripts_for_sub_alpha_effects(self, temp_db):
        """Should generate restore scripts when effects have color alpha < 1."""
        conn = temp_db
        file_id, _, screen_id = seed_file_and_collection(conn)
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, effects) VALUES (?, '1:102', 'Card', 'FRAME', ?)",
            (screen_id, '[{"type":"DROP_SHADOW","color":{"r":0,"g":0,"b":0,"a":0.05},"radius":10,"offset":{"x":0,"y":1},"spread":0,"visible":true}]')
        )
        conn.commit()

        scripts = generate_opacity_restore_scripts(conn, file_id=1)

        assert len(scripts) >= 1
        assert "1:102" in scripts[0]
        assert "0.05" in scripts[0]

    def test_skips_full_opacity_fills(self, temp_db):
        """Should not generate scripts for fills at full opacity."""
        conn = temp_db
        file_id, _, screen_id = seed_file_and_collection(conn)
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, fills) VALUES (?, '1:101', 'FullOpacity', 'FRAME', ?)",
            (screen_id, '[{"type":"SOLID","color":{"r":1,"g":0,"b":0,"a":1},"opacity":1}]')
        )
        conn.commit()

        scripts = generate_opacity_restore_scripts(conn, file_id=1)

        assert len(scripts) == 0

    def test_skips_invisible_fills(self, temp_db):
        """Should not restore opacity on invisible fills."""
        conn = temp_db
        file_id, _, screen_id = seed_file_and_collection(conn)
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, fills) VALUES (?, '1:101', 'Hidden', 'FRAME', ?)",
            (screen_id, '[{"type":"SOLID","color":{"r":1,"g":0,"b":0,"a":1},"opacity":0.5,"visible":false}]')
        )
        conn.commit()

        scripts = generate_opacity_restore_scripts(conn, file_id=1)

        assert len(scripts) == 0

    def test_handles_mixed_fills_strokes_effects(self, temp_db):
        """Should handle fills, strokes, and effects with sub-1 opacity/alpha."""
        conn = temp_db
        file_id, _, screen_id = seed_file_and_collection(conn)
        conn.execute(
            """INSERT INTO nodes (screen_id, figma_node_id, name, node_type, fills, strokes, effects)
            VALUES (?, '1:101', 'Mixed', 'FRAME', ?, ?, ?)""",
            (
                screen_id,
                '[{"type":"SOLID","opacity":0.5}]',
                '[{"type":"SOLID","opacity":0.3}]',
                '[{"type":"DROP_SHADOW","color":{"r":0,"g":0,"b":0,"a":0.1},"radius":5}]',
            )
        )
        conn.commit()

        scripts = generate_opacity_restore_scripts(conn, file_id=1)

        all_scripts = '\n'.join(scripts)
        assert "1:101" in all_scripts
        # All three types present
        assert "0.5" in all_scripts  # fill opacity
        assert "0.3" in all_scripts  # stroke opacity
        assert "0.1" in all_scripts  # effect alpha

    def test_scripts_fit_50k_limit(self, temp_db):
        """Restore scripts must fit within 50K char limit."""
        conn = temp_db
        file_id, _, screen_id = seed_file_and_collection(conn)
        # Create many nodes with sub-1 opacity
        for i in range(1000):
            conn.execute(
                "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, fills) VALUES (?, ?, ?, 'FRAME', ?)",
                (screen_id, f'1:{i}', f'Node{i}', '[{"type":"SOLID","opacity":0.12}]')
            )
        conn.commit()

        scripts = generate_opacity_restore_scripts(conn, file_id=1)

        for script in scripts:
            assert len(script) < 50000, f"Script too large: {len(script)} chars"

    def test_returns_empty_when_no_restorations_needed(self, temp_db):
        """Should return empty list when all opacities are full."""
        conn = temp_db
        file_id, _, screen_id = seed_file_and_collection(conn)
        conn.execute(
            "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, fills) VALUES (?, '1:101', 'Normal', 'FRAME', ?)",
            (screen_id, '[{"type":"SOLID","opacity":1}]')
        )
        conn.commit()

        scripts = generate_opacity_restore_scripts(conn, file_id=1)
        assert scripts == []


class TestGetRebindSummary:
    """Test get_rebind_summary function."""

    def test_summary_basic(self, populated_db):
        """Test basic summary generation."""
        conn, file_id = populated_db
        summary = get_rebind_summary(conn, file_id)

        assert summary["total_bindings"] == 5
        assert summary["script_count"] == 1
        assert "by_property_type" in summary
        assert summary["by_property_type"]["paint_fill"] == 1
        assert summary["by_property_type"]["direct"] == 2  # fontSize, cornerRadius
        assert summary["by_property_type"]["effect"] == 1
        assert summary["by_property_type"]["padding"] == 1
        assert summary["unbindable"] == 0

    def test_summary_with_unknown(self, temp_db):
        """Test summary with unbindable properties."""
        conn = temp_db
        file_id, coll_id, screen_id = seed_file_and_collection(conn)
        cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name, node_type) VALUES (?, '1:101', 'Node', 'FRAME')", (screen_id,))
        node_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO tokens (collection_id, name, type, tier, figma_variable_id) VALUES (?, 'test', 'color', 'curated', 'VariableID:123')", (coll_id,))
        token_id = cursor.lastrowid

        # Add binding with unknown property
        conn.execute("""
            INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
            VALUES (?, 'unknownProperty', ?, 'value', 'value', 'bound')
        """, (node_id, token_id))

        # Add a valid binding
        conn.execute("""
            INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
            VALUES (?, 'fontSize', ?, '16', '16', 'bound')
        """, (node_id, token_id))
        conn.commit()

        summary = get_rebind_summary(conn, file_id)

        assert summary["total_bindings"] == 1  # Only valid binding
        assert summary["unbindable"] == 1  # The unknown property

    def test_summary_empty(self, temp_db):
        """Test summary with no bindings."""
        conn = temp_db
        file_id, _, _ = seed_file_and_collection(conn)

        summary = get_rebind_summary(conn, file_id)

        assert summary["total_bindings"] == 0
        assert summary["script_count"] == 0
        assert summary["unbindable"] == 0
        assert summary["by_property_type"] == {}