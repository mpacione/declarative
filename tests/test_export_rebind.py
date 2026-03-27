"""Test export_rebind module for rebind script generation."""

import sqlite3
import tempfile
from pathlib import Path

import math

import pytest

from dd.config import MAX_BINDINGS_PER_SCRIPT
from dd.export_rebind import (
    PROPERTY_HANDLERS,
    PROPERTY_SHORTCODES,
    classify_property,
    encode_property,
    generate_compact_script,
    generate_rebind_scripts,
    generate_single_script,
    get_rebind_summary,
    query_bindable_entries,
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
            file_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL
        );

        CREATE TABLE screens (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id),
            figma_node_id TEXT NOT NULL,
            name TEXT NOT NULL
        );

        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            screen_id INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
            figma_node_id TEXT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(screen_id, figma_node_id)
        );

        CREATE TABLE tokens (
            id INTEGER PRIMARY KEY,
            collection_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            figma_variable_id TEXT
        );

        CREATE TABLE node_token_bindings (
            id INTEGER PRIMARY KEY,
            node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            property TEXT NOT NULL,
            token_id INTEGER REFERENCES tokens(id),
            raw_value TEXT NOT NULL,
            resolved_value TEXT NOT NULL,
            binding_status TEXT NOT NULL DEFAULT 'unbound'
                CHECK(binding_status IN ('unbound', 'proposed', 'bound', 'overridden', 'intentionally_unbound')),
            UNIQUE(node_id, property)
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
    cursor = conn.execute("INSERT INTO files (file_key, name) VALUES ('test123', 'test.figma')")
    file_id = cursor.lastrowid

    # Create a screen
    cursor = conn.execute("INSERT INTO screens (file_id, figma_node_id, name) VALUES (?, '1:100', 'Screen 1')", (file_id,))
    screen_id = cursor.lastrowid

    # Create nodes
    cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name) VALUES (?, '2219:235701', 'Button')", (screen_id,))
    node1_id = cursor.lastrowid
    cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name) VALUES (?, '2219:235702', 'Text')", (screen_id,))
    node2_id = cursor.lastrowid
    cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name) VALUES (?, '2219:235703', 'Card')", (screen_id,))
    node3_id = cursor.lastrowid
    cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name) VALUES (?, '2219:235704', 'Frame')", (screen_id,))
    node4_id = cursor.lastrowid

    # Create tokens with figma_variable_id
    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, figma_variable_id)
        VALUES (1, 'color.primary', 'color', 'VariableID:123:456')
    """)
    token1_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, figma_variable_id)
        VALUES (1, 'size.md', 'dimension', 'VariableID:123:789')
    """)
    token2_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, figma_variable_id)
        VALUES (1, 'shadow.sm', 'color', 'VariableID:123:012')
    """)
    token3_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, figma_variable_id)
        VALUES (1, 'space.4', 'dimension', 'VariableID:123:345')
    """)
    token4_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type, figma_variable_id)
        VALUES (1, 'radius.md', 'dimension', 'VariableID:123:678')
    """)
    token5_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO tokens (collection_id, name, type)
        VALUES (1, 'color.secondary', 'color')
    """)
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
        cursor = conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'test.figma')")
        file_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO screens (file_id, figma_node_id, name) VALUES (?, '1:100', 'Screen')", (file_id,))
        screen_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name) VALUES (?, '1:101', 'Node')", (screen_id,))
        node_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO tokens (collection_id, name, type, figma_variable_id) VALUES (1, 'test', 'color', 'VariableID:123')")
        token_id = cursor.lastrowid

        # Add binding with unknown property
        conn.execute("""
            INSERT INTO node_token_bindings (node_id, property, token_id, raw_value, resolved_value, binding_status)
            VALUES (?, 'unknownProperty', ?, 'value', 'value', 'bound')
        """, (node_id, token_id))
        conn.commit()

        entries = query_bindable_entries(conn, file_id)
        assert len(entries) == 0  # Unknown property should be filtered

    def test_query_empty(self, temp_db):
        """Test with no bindable entries."""
        conn = temp_db
        cursor = conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'test.figma')")
        file_id = cursor.lastrowid
        conn.commit()

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
        cursor = conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'test.figma')")
        file_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO screens (file_id, figma_node_id, name) VALUES (?, '1:100', 'Screen')", (file_id,))
        screen_id = cursor.lastrowid

        entry_count = 1500
        for i in range(entry_count):
            cursor = conn.execute(f"INSERT INTO nodes (screen_id, figma_node_id, name) VALUES (?, '1:{i}', 'Node{i}')", (screen_id,))
            node_id = cursor.lastrowid
            cursor = conn.execute(f"INSERT INTO tokens (collection_id, name, type, figma_variable_id) VALUES (1, 'token{i}', 'color', 'VariableID:{i}')")
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
        cursor = conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'test.figma')")
        file_id = cursor.lastrowid
        conn.commit()

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
        cursor = conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'test.figma')")
        file_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO screens (file_id, figma_node_id, name) VALUES (?, '1:100', 'Screen')", (file_id,))
        screen_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO nodes (screen_id, figma_node_id, name) VALUES (?, '1:101', 'Node')", (screen_id,))
        node_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO tokens (collection_id, name, type, figma_variable_id) VALUES (1, 'test', 'color', 'VariableID:123')")
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
        cursor = conn.execute("INSERT INTO files (file_key, name) VALUES ('test', 'test.figma')")
        file_id = cursor.lastrowid
        conn.commit()

        summary = get_rebind_summary(conn, file_id)

        assert summary["total_bindings"] == 0
        assert summary["script_count"] == 0
        assert summary["unbindable"] == 0
        assert summary["by_property_type"] == {}