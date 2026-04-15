"""Unit tests for the extraction pipeline modules."""

import json

import pytest

from dd.db import init_db
from dd.extract import (
    complete_run,
    get_next_screen,
    process_screen,
    run_inventory,
)
from dd.extract_bindings import (
    create_bindings_for_node,
    insert_bindings,
)
from dd.extract_inventory import (
    classify_screen,
    create_extraction_run,
    get_pending_screens,
    populate_file,
    populate_screens,
)
from dd.extract_screens import (
    compute_is_semantic,
    generate_extraction_script,
    insert_nodes,
    parse_extraction_response,
)
from dd.paths import (
    compute_is_semantic as compute_is_semantic_db,
)
from dd.paths import (
    compute_paths,
    compute_paths_and_semantics,
)


def _make_mock_response(node_count=5):
    """Create a mock Figma extraction response."""
    if node_count == 5:
        return [
            {
                "figma_node_id": "100:1",
                "parent_idx": None,
                "name": "Home",
                "node_type": "FRAME",
                "depth": 0,
                "sort_order": 0,
                "x": 0,
                "y": 0,
                "width": 428,
                "height": 926,
                "visible": True,
                "opacity": 1.0,
                "fills": '[{"type":"SOLID","color":{"r":0.035,"g":0.035,"b":0.043,"a":1}}]',
                "layout_mode": "VERTICAL",
                "padding_top": 16,
                "padding_bottom": 16,
                "padding_left": 16,
                "padding_right": 16,
                "item_spacing": 8,
            },
            {
                "figma_node_id": "100:2",
                "parent_idx": 0,
                "name": "Header",
                "node_type": "FRAME",
                "depth": 1,
                "sort_order": 0,
                "x": 0,
                "y": 0,
                "width": 396,
                "height": 44,
                "visible": True,
                "layout_mode": "HORIZONTAL",
                "item_spacing": 12,
            },
            {
                "figma_node_id": "100:3",
                "parent_idx": 1,
                "name": "Title",
                "node_type": "TEXT",
                "depth": 2,
                "sort_order": 0,
                "x": 0,
                "y": 0,
                "width": 200,
                "height": 24,
                "visible": True,
                "font_family": "Inter",
                "font_weight": 600,
                "font_size": 16,
                "line_height": '{"value":24,"unit":"PIXELS"}',
                "text_content": "Home",
            },
            {
                "figma_node_id": "100:4",
                "parent_idx": 0,
                "name": "Card",
                "node_type": "FRAME",
                "depth": 1,
                "sort_order": 1,
                "x": 0,
                "y": 60,
                "width": 396,
                "height": 200,
                "visible": False,
                "fills": '[{"type":"SOLID","color":{"r":0.094,"g":0.094,"b":0.106,"a":1}}]',
                "corner_radius": "8",
                "effects": '[{"type":"DROP_SHADOW","visible":true,"color":{"r":0,"g":0,"b":0,"a":0.1},"radius":6,"offset":{"x":0,"y":4},"spread":-1}]',
            },
            {
                "figma_node_id": "100:5",
                "parent_idx": 3,
                "name": "Card Label",
                "node_type": "TEXT",
                "depth": 2,
                "sort_order": 0,
                "x": 16,
                "y": 16,
                "width": 100,
                "height": 20,
                "visible": True,
                "font_family": "Inter",
                "font_weight": 400,
                "font_size": 14,
                "line_height": '{"value":20,"unit":"PIXELS"}',
                "text_content": "Settings",
                "letter_spacing": '{"value":0.1,"unit":"PIXELS"}',
            },
        ]
    else:
        # Generate dynamic count
        nodes = []
        for i in range(node_count):
            nodes.append({
                "figma_node_id": f"100:{i+1}",
                "parent_idx": None if i == 0 else 0,
                "name": f"Node {i+1}",
                "node_type": "FRAME" if i == 0 else "TEXT",
                "depth": 0 if i == 0 else 1,
                "sort_order": i,
                "x": 0,
                "y": i * 50,
                "width": 100,
                "height": 40,
                "visible": True,
            })
        return nodes


# ========== 1. Inventory tests ==========


@pytest.mark.unit
def test_populate_file_creates_row():
    """Insert a file and verify it exists in DB with correct data."""
    conn = init_db(":memory:")

    file_id = populate_file(
        conn,
        file_key="ABC123",
        name="Test File",
        node_count=100,
        screen_count=5,
        last_modified="2024-01-01T12:00:00Z",
        metadata='{"version": "1.0"}',
    )

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    row = cursor.fetchone()

    assert row is not None
    assert row["file_key"] == "ABC123"
    assert row["name"] == "Test File"
    assert row["node_count"] == 100
    assert row["screen_count"] == 5
    assert row["last_modified"] == "2024-01-01T12:00:00Z"
    assert row["metadata"] == '{"version": "1.0"}'


@pytest.mark.unit
def test_populate_file_upsert():
    """Insert same file_key twice and verify only 1 row exists with updated data."""
    conn = init_db(":memory:")

    # First insert
    file_id1 = populate_file(conn, "ABC123", "Original Name", node_count=50)

    # Second insert (upsert)
    file_id2 = populate_file(conn, "ABC123", "Updated Name", node_count=100)

    assert file_id1 == file_id2  # Same ID returned

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM files WHERE file_key = ?", ("ABC123",))
    count = cursor.fetchone()[0]
    assert count == 1

    cursor.execute("SELECT name, node_count FROM files WHERE file_key = ?", ("ABC123",))
    row = cursor.fetchone()
    assert row["name"] == "Updated Name"
    assert row["node_count"] == 100


@pytest.mark.unit
def test_classify_screen_iphone():
    """width=428, height=926 -> iphone."""
    result = classify_screen("Home Screen", 428, 926)
    assert result == "iphone"


@pytest.mark.unit
def test_classify_screen_component_sheet_by_name():
    """Name 'Buttons and Controls' -> component_sheet."""
    result = classify_screen("Buttons and Controls", 1234, 5678)
    assert result == "component_sheet"


@pytest.mark.unit
def test_classify_screen_component_sheet_by_content():
    """Unknown dims + has_components=True -> component_sheet."""
    result = classify_screen("Some Screen", 9999, 9999, has_components=True)
    assert result == "component_sheet"


@pytest.mark.unit
def test_populate_screens_creates_rows():
    """Insert 3 frames and verify 3 rows in screens with correct device_class."""
    conn = init_db(":memory:")

    # Create a file first
    file_id = populate_file(conn, "ABC123", "Test File")

    frames = [
        {"figma_node_id": "1:1", "name": "iPhone Screen", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Desktop", "width": 1440, "height": 900},
        {"figma_node_id": "1:3", "name": "Components", "width": 5000, "height": 3000,
         "has_components": True},
    ]

    screen_ids = populate_screens(conn, file_id, frames)

    assert len(screen_ids) == 3

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM screens WHERE file_id = ? ORDER BY id", (file_id,))
    rows = cursor.fetchall()

    assert len(rows) == 3
    assert rows[0]["name"] == "iPhone Screen"
    assert rows[0]["device_class"] == "iphone"
    assert rows[1]["name"] == "Desktop"
    assert rows[1]["device_class"] == "unknown"  # 1440x900 not in DEVICE_DIMENSIONS
    assert rows[2]["name"] == "Components"
    assert rows[2]["device_class"] == "component_sheet"


@pytest.mark.unit
def test_create_extraction_run():
    """Create run and verify run row + screen_extraction_status rows exist."""
    conn = init_db(":memory:")

    # Setup: file with screens
    file_id = populate_file(conn, "ABC123", "Test File")
    frames = [
        {"figma_node_id": "1:1", "name": "Screen 1", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Screen 2", "width": 428, "height": 926},
    ]
    screen_ids = populate_screens(conn, file_id, frames)

    # Create run
    run_id = create_extraction_run(conn, file_id, agent_id="test-agent")

    # Verify run row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM extraction_runs WHERE id = ?", (run_id,))
    run_row = cursor.fetchone()
    assert run_row is not None
    assert run_row["file_id"] == file_id
    assert run_row["agent_id"] == "test-agent"
    assert run_row["total_screens"] == 2
    assert run_row["status"] == "running"

    # Verify status rows
    cursor.execute("SELECT COUNT(*) FROM screen_extraction_status WHERE run_id = ?", (run_id,))
    count = cursor.fetchone()[0]
    assert count == 2


@pytest.mark.unit
def test_get_pending_screens():
    """Create run, verify pending screens returned, complete one, verify it's excluded."""
    conn = init_db(":memory:")

    # Setup
    file_id = populate_file(conn, "ABC123", "Test File")
    frames = [
        {"figma_node_id": "1:1", "name": "Screen 1", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Screen 2", "width": 428, "height": 926},
    ]
    screen_ids = populate_screens(conn, file_id, frames)
    run_id = create_extraction_run(conn, file_id)

    # Get pending screens
    pending = get_pending_screens(conn, run_id)
    assert len(pending) == 2
    assert pending[0]["name"] == "Screen 1"
    assert pending[1]["name"] == "Screen 2"

    # Complete one screen
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE screen_extraction_status SET status = 'completed' WHERE run_id = ? AND screen_id = ?",
        (run_id, screen_ids[0])
    )
    conn.commit()

    # Get pending again
    pending = get_pending_screens(conn, run_id)
    assert len(pending) == 1
    assert pending[0]["name"] == "Screen 2"


# ========== 2. Screen extraction tests ==========


@pytest.mark.unit
def test_generate_extraction_script_format():
    """Verify script contains function, node ID, return statement, under 50K chars."""
    script = generate_extraction_script("123:456")

    assert "async function extractScreen" in script
    assert "123:456" in script
    assert "return await extractScreen" in script
    assert len(script) < 50000
    assert "await walk(screen, null, 0)" in script


@pytest.mark.unit
@pytest.mark.unit
class TestExtractWhitelistsAreRegistryDriven:
    """`parse_extraction_response` and `insert_nodes` used to maintain
    hand-rolled whitelists of fields to forward. Adding a new property
    to the registry (e.g. `leading_trim`) didn't auto-extend them;
    result: the new column silently dropped between extraction and
    DB insert, and a re-extract showed 0 rows of the new field despite
    every upstream/downstream path being correct.

    See feedback_extract_whitelist_drift.md for the cost in
    re-extract iterations.

    These structural tests pin the invariant: both whitelists MUST be
    a superset of the registry's text-category and all-category
    db_columns. Adding a new registry property with a db_column
    automatically extends the whitelists (via registry lookup in
    extract_screens.py)."""

    def test_parse_extraction_forwards_every_text_category_registry_column(self):
        """Every registry property with category='text' and db_column
        set must appear in the parsed output when present in the
        input."""
        from dd.property_registry import PROPERTIES
        text_cols = [
            p.db_column for p in PROPERTIES
            if p.category == "text" and p.db_column
        ]
        assert text_cols, "registry must expose at least one text-category db_column"

        # Build a mock input that includes every text column. The parser
        # should forward every one of them into its output dict.
        node_input = {
            "figma_node_id": "test:1",
            "name": "t1",
            "node_type": "TEXT",
            "depth": 0,
            "sort_order": 0,
        }
        # Seed each text column with a marker value.
        for col in text_cols:
            # Only set columns the parser knows to forward generically.
            # font_size / font_weight / line_height / letter_spacing /
            # paragraph_spacing need type coercion and are handled
            # separately in the parser. Use string values for the rest.
            if col in {"font_size", "font_weight", "line_height",
                       "letter_spacing", "paragraph_spacing"}:
                node_input[col] = 1.0 if col != "font_weight" else 400
            else:
                node_input[col] = f"__marker_{col}__"

        parsed = parse_extraction_response([node_input])
        assert len(parsed) == 1
        result = parsed[0]

        missing = [col for col in text_cols if col not in result]
        assert missing == [], (
            f"registry text columns missing from parse output: {missing}. "
            f"`parse_extraction_response` whitelist has drifted from the "
            f"property registry — adding a new text-category property "
            f"must auto-extend it."
        )

    def test_insert_nodes_accepts_every_registry_db_column(self):
        """`insert_nodes` must forward every registry-declared db_column
        (across all categories) into its SQL INSERT statement."""
        from dd.property_registry import PROPERTIES
        reg_cols = {p.db_column for p in PROPERTIES if p.db_column}
        assert reg_cols, "registry must expose db_columns"

        # Rather than run the real INSERT (requires DB + schema), inspect
        # the source to assert the whitelist — or equivalently, import
        # the module-level whitelist if one exists. Use source
        # introspection via the registry's canonical set.
        from dd import extract_screens
        # Expose the effective whitelist used by insert_nodes. The
        # function computes it internally; expose it as a module
        # attribute for introspection.
        assert hasattr(extract_screens, "INSERT_NODE_COLUMNS"), (
            "extract_screens must expose INSERT_NODE_COLUMNS so drift "
            "tests can read the effective whitelist"
        )
        whitelist = set(extract_screens.INSERT_NODE_COLUMNS)
        missing = reg_cols - whitelist
        assert missing == set(), (
            f"registry db_columns missing from insert_nodes whitelist: "
            f"{sorted(missing)}. Whitelist has drifted from registry."
        )


def test_parse_extraction_response_basic():
    """Pass the 5-node mock response and verify all nodes parsed with correct types."""
    response = _make_mock_response(5)
    parsed = parse_extraction_response(response)

    assert len(parsed) == 5

    # Check first node
    assert parsed[0]["figma_node_id"] == "100:1"
    assert parsed[0]["name"] == "Home"
    assert parsed[0]["node_type"] == "FRAME"
    assert parsed[0]["parent_idx"] is None
    assert parsed[0]["depth"] == 0
    assert parsed[0]["width"] == 428.0
    assert parsed[0]["height"] == 926.0

    # Check third node (TEXT)
    assert parsed[2]["figma_node_id"] == "100:3"
    assert parsed[2]["node_type"] == "TEXT"
    assert parsed[2]["font_family"] == "Inter"
    assert parsed[2]["font_weight"] == 600
    assert parsed[2]["font_size"] == 16.0
    assert parsed[2]["text_content"] == "Home"


@pytest.mark.unit
def test_parse_extraction_response_converts_visible():
    """Boolean true/false -> int 1/0."""
    response = _make_mock_response(5)
    parsed = parse_extraction_response(response)

    # First node has visible=True
    assert parsed[0]["visible"] == 1
    # Fourth node has visible=False
    assert parsed[3]["visible"] == 0


@pytest.mark.unit
def test_compute_is_semantic_text_node():
    """TEXT nodes marked semantic."""
    nodes = [
        {"figma_node_id": "1", "name": "Frame", "node_type": "FRAME", "parent_idx": None},
        {"figma_node_id": "2", "name": "Label", "node_type": "TEXT", "parent_idx": 0},
    ]
    result = compute_is_semantic(nodes)

    assert result[0]["is_semantic"] == 0  # Frame not semantic by default
    assert result[1]["is_semantic"] == 1  # TEXT is semantic


@pytest.mark.unit
def test_compute_is_semantic_named_frame():
    """Frame named 'MyWidget' is semantic; 'Frame 1' is not."""
    nodes = [
        {"figma_node_id": "1", "name": "Frame 1", "node_type": "FRAME", "parent_idx": None},
        {"figma_node_id": "2", "name": "MyWidget", "node_type": "FRAME", "parent_idx": None},
    ]
    result = compute_is_semantic(nodes)

    assert result[0]["is_semantic"] == 0  # "Frame 1" starts with non-semantic prefix
    assert result[1]["is_semantic"] == 1  # "MyWidget" doesn't start with prefix


@pytest.mark.unit
def test_compute_is_semantic_bottom_up():
    """Parent with 2+ semantic children promoted."""
    nodes = [
        {"figma_node_id": "1", "name": "Frame 1", "node_type": "FRAME", "parent_idx": None},
        {"figma_node_id": "2", "name": "Text1", "node_type": "TEXT", "parent_idx": 0},
        {"figma_node_id": "3", "name": "Text2", "node_type": "TEXT", "parent_idx": 0},
    ]
    result = compute_is_semantic(nodes)

    # Parent should be promoted to semantic (2 semantic children)
    assert result[0]["is_semantic"] == 1
    assert result[1]["is_semantic"] == 1
    assert result[2]["is_semantic"] == 1


@pytest.mark.unit
def test_insert_nodes_parent_resolution():
    """Insert 5-node tree and verify parent_id chain is correct."""
    conn = init_db(":memory:")

    # Setup: create file and screen
    file_id = populate_file(conn, "ABC123", "Test File")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO screens (file_id, figma_node_id, name, width, height, device_class) VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, "1:1", "Test Screen", 428, 926, "iphone")
    )
    screen_id = cursor.lastrowid

    # Parse mock response
    response = _make_mock_response(5)
    parsed = parse_extraction_response(response)
    nodes_with_semantic = compute_is_semantic(parsed)

    # Insert nodes
    node_ids = insert_nodes(conn, screen_id, nodes_with_semantic)

    assert len(node_ids) == 5

    # Verify parent relationships
    cursor.execute("SELECT id, parent_id, name FROM nodes WHERE screen_id = ? ORDER BY id", (screen_id,))
    rows = cursor.fetchall()

    assert rows[0]["parent_id"] is None  # Root has no parent
    assert rows[1]["parent_id"] == node_ids[0]  # Header's parent is Home
    assert rows[2]["parent_id"] == node_ids[1]  # Title's parent is Header
    assert rows[3]["parent_id"] == node_ids[0]  # Card's parent is Home
    assert rows[4]["parent_id"] == node_ids[3]  # Card Label's parent is Card


@pytest.mark.unit
def test_insert_nodes_upsert():
    """Insert same nodes twice and verify no duplicates."""
    conn = init_db(":memory:")

    # Setup
    file_id = populate_file(conn, "ABC123", "Test File")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO screens (file_id, figma_node_id, name, width, height, device_class) VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, "1:1", "Test Screen", 428, 926, "iphone")
    )
    screen_id = cursor.lastrowid

    # Parse and insert twice
    response = _make_mock_response(3)
    parsed = parse_extraction_response(response)

    node_ids1 = insert_nodes(conn, screen_id, parsed)
    node_ids2 = insert_nodes(conn, screen_id, parsed)

    # Should return same IDs
    assert node_ids1 == node_ids2

    # Verify no duplicates
    cursor.execute("SELECT COUNT(*) FROM nodes WHERE screen_id = ?", (screen_id,))
    count = cursor.fetchone()[0]
    assert count == 3


# ========== 3. Binding tests ==========


@pytest.mark.unit
def test_create_bindings_for_node_with_fill():
    """Node with solid fill -> 1 color binding."""
    node = {
        "fills": '[{"type":"SOLID","color":{"r":1,"g":0,"b":0,"a":1}}]'
    }
    bindings = create_bindings_for_node(node)

    assert len(bindings) == 1
    assert bindings[0]["property"] == "fill.0.color"
    assert bindings[0]["resolved_value"] == "#FF0000"  # rgba_to_hex returns uppercase


@pytest.mark.unit
def test_create_bindings_for_node_with_effect():
    """Node with DROP_SHADOW -> 5 effect bindings."""
    node = {
        "effects": '[{"type":"DROP_SHADOW","visible":true,"color":{"r":0,"g":0,"b":0,"a":0.25},"radius":4,"offset":{"x":0,"y":2},"spread":0}]'
    }
    bindings = create_bindings_for_node(node)

    # Should have bindings for color, radius, offset-x, offset-y, spread
    assert len(bindings) == 5
    prop_names = [b["property"] for b in bindings]
    assert "effect.0.color" in prop_names
    assert "effect.0.radius" in prop_names
    assert "effect.0.offsetX" in prop_names
    assert "effect.0.offsetY" in prop_names
    assert "effect.0.spread" in prop_names


@pytest.mark.unit
def test_create_bindings_for_node_text():
    """TEXT node -> typography bindings."""
    node = {
        "font_family": "Inter",
        "font_weight": 600,
        "font_size": 16,
        "line_height": '{"value":24,"unit":"PIXELS"}',
        "letter_spacing": '{"value":0.5,"unit":"PIXELS"}'
    }
    bindings = create_bindings_for_node(node)

    # Should have typography bindings
    assert len(bindings) > 0
    prop_names = [b["property"] for b in bindings]
    assert "fontFamily" in prop_names
    assert "fontWeight" in prop_names
    assert "fontSize" in prop_names
    assert "lineHeight" in prop_names
    assert "letterSpacing" in prop_names


@pytest.mark.unit
def test_create_bindings_for_node_spacing():
    """Node with padding and itemSpacing -> spacing bindings."""
    node = {
        "padding_top": 16,
        "padding_right": 16,
        "padding_bottom": 16,
        "padding_left": 16,
        "item_spacing": 8,
    }
    bindings = create_bindings_for_node(node)

    assert len(bindings) == 5
    prop_names = [b["property"] for b in bindings]
    assert "padding.top" in prop_names
    assert "padding.right" in prop_names
    assert "padding.bottom" in prop_names
    assert "padding.left" in prop_names
    assert "itemSpacing" in prop_names


@pytest.mark.unit
def test_create_bindings_for_node_empty():
    """Node with no visual properties -> 0 bindings."""
    node = {
        "figma_node_id": "1:1",
        "name": "Empty",
    }
    bindings = create_bindings_for_node(node)

    assert len(bindings) == 0


@pytest.mark.unit
def test_insert_bindings_preserves_bound():
    """Insert binding, mark as 'bound', re-insert -> bound binding preserved."""
    conn = init_db(":memory:")

    # Setup: create a node
    file_id = populate_file(conn, "ABC123", "Test File")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO screens (file_id, figma_node_id, name, width, height, device_class) VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, "1:1", "Test Screen", 428, 926, "iphone")
    )
    screen_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO nodes (screen_id, figma_node_id, name, node_type) VALUES (?, ?, ?, ?)",
        (screen_id, "100:1", "Test Node", "FRAME")
    )
    node_id = cursor.lastrowid

    # Insert initial binding
    bindings1 = [{"property": "background-color", "raw_value": "#ff0000", "resolved_value": "#ff0000"}]
    count = insert_bindings(conn, node_id, bindings1)
    assert count == 1

    # Mark as bound
    cursor.execute(
        "UPDATE node_token_bindings SET binding_status = 'bound' WHERE node_id = ? AND property = ?",
        (node_id, "background-color")
    )
    conn.commit()

    # Try to re-insert with different value
    bindings2 = [{"property": "background-color", "raw_value": "#00ff00", "resolved_value": "#00ff00"}]
    count = insert_bindings(conn, node_id, bindings2)

    # Verify original value preserved but status changed to overridden
    cursor.execute(
        "SELECT raw_value, resolved_value, binding_status FROM node_token_bindings WHERE node_id = ? AND property = ?",
        (node_id, "background-color")
    )
    row = cursor.fetchone()
    assert row["raw_value"] == "#00ff00"  # New raw value
    assert row["resolved_value"] == "#00ff00"  # New resolved value
    assert row["binding_status"] == "overridden"  # Status changed


# ========== 4. Path computation tests ==========


@pytest.mark.unit
def test_compute_paths_root_node():
    """Single root gets path '0'."""
    conn = init_db(":memory:")

    # Setup
    file_id = populate_file(conn, "ABC123", "Test File")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO screens (file_id, figma_node_id, name, width, height, device_class) VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, "1:1", "Test Screen", 428, 926, "iphone")
    )
    screen_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, parent_id, sort_order, depth) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (screen_id, "100:1", "Root", "FRAME", None, 0, 0)
    )

    # Compute paths
    compute_paths(conn, screen_id)

    # Verify
    cursor.execute("SELECT path FROM nodes WHERE screen_id = ?", (screen_id,))
    row = cursor.fetchone()
    assert row["path"] == "0"


@pytest.mark.unit
def test_compute_paths_tree():
    """5-node tree gets correct hierarchical paths."""
    conn = init_db(":memory:")

    # Setup: create file and screen
    file_id = populate_file(conn, "ABC123", "Test File")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO screens (file_id, figma_node_id, name, width, height, device_class) VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, "1:1", "Test Screen", 428, 926, "iphone")
    )
    screen_id = cursor.lastrowid

    # Insert 5 nodes manually with parent relationships
    cursor.execute(
        "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, parent_id, sort_order, depth) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (screen_id, "100:1", "Root", "FRAME", None, 0, 0)
    )
    root_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, parent_id, sort_order, depth) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (screen_id, "100:2", "Child1", "FRAME", root_id, 0, 1)
    )
    child1_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, parent_id, sort_order, depth) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (screen_id, "100:3", "Child2", "TEXT", root_id, 1, 1)
    )
    cursor.execute(
        "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, parent_id, sort_order, depth) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (screen_id, "100:4", "Grandchild", "TEXT", child1_id, 0, 2)
    )

    # Compute paths
    compute_paths(conn, screen_id)

    # Verify paths
    cursor.execute("SELECT figma_node_id, path FROM nodes WHERE screen_id = ? ORDER BY id", (screen_id,))
    rows = cursor.fetchall()

    assert rows[0]["path"] == "0"      # Root
    assert rows[1]["path"] == "0.0"    # Child1
    assert rows[2]["path"] == "0.1"    # Child2
    assert rows[3]["path"] == "0.0.0"  # Grandchild


@pytest.mark.unit
def test_compute_is_semantic_db():
    """Verify DB-level is_semantic computation matches expectations."""
    conn = init_db(":memory:")

    # Setup
    file_id = populate_file(conn, "ABC123", "Test File")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO screens (file_id, figma_node_id, name, width, height, device_class) VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, "1:1", "Test Screen", 428, 926, "iphone")
    )
    screen_id = cursor.lastrowid

    # Insert nodes with different semantic properties
    cursor.execute(
        "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, parent_id, depth) VALUES (?, ?, ?, ?, ?, ?)",
        (screen_id, "100:1", "Frame 1", "FRAME", None, 0)
    )
    parent_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, parent_id, depth) VALUES (?, ?, ?, ?, ?, ?)",
        (screen_id, "100:2", "Label", "TEXT", parent_id, 1)
    )
    cursor.execute(
        "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, parent_id, depth) VALUES (?, ?, ?, ?, ?, ?)",
        (screen_id, "100:3", "Button", "INSTANCE", parent_id, 1)
    )

    # Compute semantic flags
    compute_is_semantic_db(conn, screen_id)

    # Verify
    cursor.execute("SELECT figma_node_id, is_semantic FROM nodes WHERE screen_id = ? ORDER BY id", (screen_id,))
    rows = cursor.fetchall()

    # Parent should be promoted (has 2+ children with at least 1 semantic)
    assert rows[0]["is_semantic"] == 1  # Parent promoted
    assert rows[1]["is_semantic"] == 1  # TEXT is semantic
    assert rows[2]["is_semantic"] == 1  # INSTANCE is semantic


@pytest.mark.unit
def test_compute_paths_and_semantics():
    """Convenience function runs both."""
    conn = init_db(":memory:")

    # Setup
    file_id = populate_file(conn, "ABC123", "Test File")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO screens (file_id, figma_node_id, name, width, height, device_class) VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, "1:1", "Test Screen", 428, 926, "iphone")
    )
    screen_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO nodes (screen_id, figma_node_id, name, node_type, parent_id, sort_order, depth) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (screen_id, "100:1", "Label", "TEXT", None, 0, 0)
    )

    # Run combined function
    compute_paths_and_semantics(conn, screen_id)

    # Verify both computed
    cursor.execute("SELECT path, is_semantic FROM nodes WHERE screen_id = ?", (screen_id,))
    row = cursor.fetchone()
    assert row["path"] == "0"
    assert row["is_semantic"] == 1  # TEXT is semantic


# ========== 5. Orchestrator tests ==========


@pytest.mark.unit
def test_run_inventory():
    """Full inventory setup returns correct dict."""
    conn = init_db(":memory:")

    frames = [
        {"figma_node_id": "1:1", "name": "Screen 1", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Screen 2", "width": 428, "height": 926},
    ]

    result = run_inventory(
        conn,
        file_key="ABC123",
        file_name="Test File",
        frames=frames,
        node_count=100,
        agent_id="test-agent"
    )

    assert "file_id" in result
    assert "run_id" in result
    assert result["screen_count"] == 2
    assert len(result["pending_screens"]) == 2


@pytest.mark.unit
def test_process_screen():
    """Process a mock response and verify nodes + bindings + paths in DB."""
    conn = init_db(":memory:")

    # Setup inventory
    frames = [{"figma_node_id": "1:1", "name": "Test Screen", "width": 428, "height": 926}]
    inventory = run_inventory(conn, "ABC123", "Test File", frames)
    run_id = inventory["run_id"]
    screen_id = inventory["pending_screens"][0]["screen_id"]

    # Process screen with mock response
    raw_response = _make_mock_response(5)
    result = process_screen(conn, run_id, screen_id, "1:1", raw_response)

    assert result["screen_id"] == screen_id
    assert result["node_count"] == 5
    assert result["binding_count"] > 0
    assert result["status"] == "completed"

    # Verify nodes in DB
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM nodes WHERE screen_id = ?", (screen_id,))
    count = cursor.fetchone()[0]
    assert count == 5

    # Verify paths computed
    cursor.execute("SELECT path FROM nodes WHERE screen_id = ? AND parent_id IS NULL", (screen_id,))
    row = cursor.fetchone()
    assert row["path"] is not None

    # Verify bindings created
    cursor.execute("SELECT COUNT(*) FROM node_token_bindings WHERE node_id IN (SELECT id FROM nodes WHERE screen_id = ?)", (screen_id,))
    binding_count = cursor.fetchone()[0]
    assert binding_count > 0


@pytest.mark.unit
def test_resume_support():
    """Create run, complete 1 screen, call get_next_screen, verify it returns next uncompleted."""
    conn = init_db(":memory:")

    # Setup with 3 screens
    frames = [
        {"figma_node_id": "1:1", "name": "Screen 1", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Screen 2", "width": 428, "height": 926},
        {"figma_node_id": "1:3", "name": "Screen 3", "width": 428, "height": 926},
    ]
    inventory = run_inventory(conn, "ABC123", "Test File", frames)
    run_id = inventory["run_id"]

    # Complete first screen
    screen1_id = inventory["pending_screens"][0]["screen_id"]
    raw_response = _make_mock_response(3)
    process_screen(conn, run_id, screen1_id, "1:1", raw_response)

    # Get next screen
    next_screen = get_next_screen(conn, run_id)
    assert next_screen is not None
    assert next_screen["name"] == "Screen 2"

    # Complete second screen
    process_screen(conn, run_id, next_screen["screen_id"], "1:2", raw_response)

    # Get next screen again
    next_screen = get_next_screen(conn, run_id)
    assert next_screen is not None
    assert next_screen["name"] == "Screen 3"


@pytest.mark.unit
def test_complete_run_all_completed():
    """All screens completed -> run status 'completed'."""
    conn = init_db(":memory:")

    # Setup with 2 screens
    frames = [
        {"figma_node_id": "1:1", "name": "Screen 1", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Screen 2", "width": 428, "height": 926},
    ]
    inventory = run_inventory(conn, "ABC123", "Test File", frames)
    run_id = inventory["run_id"]

    # Complete both screens
    raw_response = _make_mock_response(3)
    for screen in inventory["pending_screens"]:
        process_screen(conn, run_id, screen["screen_id"], screen["figma_node_id"], raw_response)

    # Complete the run
    summary = complete_run(conn, run_id)

    assert summary["status"] == "completed"
    assert summary["completed"] == 2
    assert summary["failed"] == 0


@pytest.mark.unit
def test_complete_run_with_failures():
    """Some screens failed -> run status 'failed'."""
    conn = init_db(":memory:")

    # Setup with 2 screens
    frames = [
        {"figma_node_id": "1:1", "name": "Screen 1", "width": 428, "height": 926},
        {"figma_node_id": "1:2", "name": "Screen 2", "width": 428, "height": 926},
    ]
    inventory = run_inventory(conn, "ABC123", "Test File", frames)
    run_id = inventory["run_id"]

    # Complete one, fail the other
    raw_response = _make_mock_response(3)
    screen1 = inventory["pending_screens"][0]
    screen2 = inventory["pending_screens"][1]

    # Complete first screen
    process_screen(conn, run_id, screen1["screen_id"], screen1["figma_node_id"], raw_response)

    # Manually fail second screen
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE screen_extraction_status SET status = 'failed', error = 'Test error' WHERE run_id = ? AND screen_id = ?",
        (run_id, screen2["screen_id"])
    )
    conn.commit()

    # Complete the run
    summary = complete_run(conn, run_id)

    assert summary["status"] == "failed"
    assert summary["completed"] == 1
    assert summary["failed"] == 1


# ---------------------------------------------------------------------------
# Mask extraction tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extraction_script_captures_is_mask():
    """The extraction JS must read node.isMask so we can store it."""
    script = generate_extraction_script("1:1")
    assert "isMask" in script


@pytest.mark.unit
def test_parse_extraction_response_preserves_is_mask():
    """is_mask field preserved through parse when present."""
    response = [
        {
            "figma_node_id": "200:1",
            "parent_idx": None,
            "name": "Mask Group",
            "node_type": "GROUP",
            "depth": 0,
            "sort_order": 0,
            "x": 0, "y": 0, "width": 100, "height": 100,
            "visible": True,
        },
        {
            "figma_node_id": "200:2",
            "parent_idx": 0,
            "name": "Mask Shape",
            "node_type": "ELLIPSE",
            "depth": 1,
            "sort_order": 0,
            "x": 0, "y": 0, "width": 100, "height": 100,
            "visible": True,
            "is_mask": 1,
        },
        {
            "figma_node_id": "200:3",
            "parent_idx": 0,
            "name": "Photo",
            "node_type": "RECTANGLE",
            "depth": 1,
            "sort_order": 1,
            "x": 0, "y": 0, "width": 100, "height": 100,
            "visible": True,
        },
    ]
    parsed = parse_extraction_response(response)
    assert parsed[1].get("is_mask") == 1
    assert parsed[0].get("is_mask") is None  # Group itself is not a mask
    assert parsed[2].get("is_mask") is None  # Photo is not a mask


@pytest.mark.unit
def test_insert_nodes_stores_is_mask(db):
    """is_mask column round-trips through DB insertion."""
    conn = db
    # Seed a file and screen
    conn.execute("INSERT INTO files (file_key, name) VALUES ('f1', 'Test')")
    conn.execute("INSERT INTO screens (file_id, figma_node_id, name, width, height) VALUES (1, '1:1', 'S1', 100, 100)")
    conn.commit()

    nodes = [
        {
            "figma_node_id": "300:1",
            "name": "Group",
            "node_type": "GROUP",
            "depth": 0,
            "sort_order": 0,
            "is_semantic": 0,
            "x": 0, "y": 0, "width": 100, "height": 100,
            "visible": 1,
        },
        {
            "figma_node_id": "300:2",
            "parent_idx": 0,
            "name": "Mask",
            "node_type": "ELLIPSE",
            "depth": 1,
            "sort_order": 0,
            "is_semantic": 0,
            "x": 0, "y": 0, "width": 100, "height": 100,
            "visible": 1,
            "is_mask": 1,
        },
    ]
    node_ids = insert_nodes(conn, 1, nodes)
    assert len(node_ids) == 2

    row = conn.execute("SELECT is_mask FROM nodes WHERE id = ?", (node_ids[1],)).fetchone()
    assert row[0] == 1

    row0 = conn.execute("SELECT is_mask FROM nodes WHERE id = ?", (node_ids[0],)).fetchone()
    assert row0[0] is None or row0[0] == 0


# ---------------------------------------------------------------------------
# Fix 3B: booleanOperation, cornerSmoothing, arcData extraction tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extraction_script_captures_boolean_operation():
    """Plugin API extraction must read booleanOperation for BOOLEAN_OPERATION nodes."""
    script = generate_extraction_script("1:1")
    assert "booleanOperation" in script


@pytest.mark.unit
def test_extraction_script_captures_corner_smoothing():
    """Plugin API extraction must read cornerSmoothing."""
    script = generate_extraction_script("1:1")
    assert "cornerSmoothing" in script


@pytest.mark.unit
def test_extraction_script_captures_arc_data():
    """Plugin API extraction must read arcData for ELLIPSE nodes."""
    script = generate_extraction_script("1:1")
    assert "arcData" in script


@pytest.mark.unit
def test_parse_preserves_boolean_operation():
    """booleanOperation round-trips through parse."""
    response = [{
        "figma_node_id": "400:1", "parent_idx": None, "name": "Union",
        "node_type": "BOOLEAN_OPERATION", "depth": 0, "sort_order": 0,
        "x": 0, "y": 0, "width": 50, "height": 50, "visible": True,
        "boolean_operation": "UNION",
    }]
    parsed = parse_extraction_response(response)
    assert parsed[0]["boolean_operation"] == "UNION"


@pytest.mark.unit
def test_parse_preserves_corner_smoothing():
    """cornerSmoothing round-trips through parse."""
    response = [{
        "figma_node_id": "400:2", "parent_idx": None, "name": "Card",
        "node_type": "FRAME", "depth": 0, "sort_order": 0,
        "x": 0, "y": 0, "width": 200, "height": 100, "visible": True,
        "corner_smoothing": 0.6,
    }]
    parsed = parse_extraction_response(response)
    assert parsed[0]["corner_smoothing"] == pytest.approx(0.6)


@pytest.mark.unit
def test_parse_preserves_arc_data():
    """arcData round-trips through parse as JSON."""
    arc = {"startingAngle": 0.0, "endingAngle": 3.14, "innerRadius": 0.5}
    response = [{
        "figma_node_id": "400:3", "parent_idx": None, "name": "Arc",
        "node_type": "ELLIPSE", "depth": 0, "sort_order": 0,
        "x": 0, "y": 0, "width": 50, "height": 50, "visible": True,
        "arc_data": json.dumps(arc),
    }]
    parsed = parse_extraction_response(response)
    assert parsed[0]["arc_data"] == json.dumps(arc)


@pytest.mark.unit
def test_insert_nodes_stores_3b_properties(db):
    """booleanOperation, cornerSmoothing, arcData round-trip through DB."""
    conn = db
    conn.execute("INSERT INTO files (file_key, name) VALUES ('f1', 'Test')")
    conn.execute("INSERT INTO screens (file_id, figma_node_id, name, width, height) VALUES (1, '1:1', 'S1', 100, 100)")
    conn.commit()

    arc = json.dumps({"startingAngle": 0.0, "endingAngle": 6.28, "innerRadius": 0.5})
    nodes = [
        {
            "figma_node_id": "500:1", "name": "Union", "node_type": "BOOLEAN_OPERATION",
            "depth": 0, "sort_order": 0, "is_semantic": 0,
            "x": 0, "y": 0, "width": 50, "height": 50, "visible": 1,
            "boolean_operation": "UNION",
        },
        {
            "figma_node_id": "500:2", "parent_idx": 0, "name": "Card", "node_type": "FRAME",
            "depth": 1, "sort_order": 0, "is_semantic": 0,
            "x": 0, "y": 0, "width": 200, "height": 100, "visible": 1,
            "corner_smoothing": 0.6,
        },
        {
            "figma_node_id": "500:3", "parent_idx": 0, "name": "Arc", "node_type": "ELLIPSE",
            "depth": 1, "sort_order": 1, "is_semantic": 0,
            "x": 0, "y": 0, "width": 50, "height": 50, "visible": 1,
            "arc_data": arc,
        },
    ]
    node_ids = insert_nodes(conn, 1, nodes)
    assert len(node_ids) == 3

    row = conn.execute("SELECT boolean_operation FROM nodes WHERE id = ?", (node_ids[0],)).fetchone()
    assert row[0] == "UNION"

    row = conn.execute("SELECT corner_smoothing FROM nodes WHERE id = ?", (node_ids[1],)).fetchone()
    assert abs(row[0] - 0.6) < 0.01

    row = conn.execute("SELECT arc_data FROM nodes WHERE id = ?", (node_ids[2],)).fetchone()
    assert row[0] == arc