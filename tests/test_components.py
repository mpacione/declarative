"""Unit tests for component extraction module."""

import json
from typing import Any

import pytest

from dd.extract_components import (
    detect_interaction_axis,
    extract_components,
    infer_a11y,
    infer_category,
    infer_slot_type,
    infer_slots,
    insert_a11y,
    insert_component,
    insert_slots,
    insert_variant_axes,
    insert_variants,
    parse_component_set,
    parse_standalone_component,
    parse_variant_properties,
    populate_variant_dimension_values,
)


def _make_mock_component_set() -> dict[str, Any]:
    """Create mock COMPONENT_SET data matching Figma structure."""
    return {
        "id": "500:1",
        "name": "button",
        "type": "COMPONENT_SET",
        "description": "Primary button component",
        "children": [
            {
                "id": "500:2",
                "name": "size=large, style=solid, state=default",
                "type": "COMPONENT",
                "width": 200,
                "height": 48,
                "children": [
                    {"name": "Icon", "type": "INSTANCE", "sort_order": 0},
                    {"name": "Label", "type": "TEXT", "sort_order": 1, "characters": "Submit"}
                ]
            },
            {
                "id": "500:3",
                "name": "size=large, style=solid, state=hover",
                "type": "COMPONENT",
                "width": 200,
                "height": 48,
                "children": []
            },
            {
                "id": "500:4",
                "name": "size=large, style=outline, state=default",
                "type": "COMPONENT",
                "width": 200,
                "height": 48,
                "children": []
            },
            {
                "id": "500:5",
                "name": "size=small, style=solid, state=default",
                "type": "COMPONENT",
                "width": 120,
                "height": 36,
                "children": []
            }
        ]
    }


def _make_mock_standalone_component() -> dict[str, Any]:
    """Create mock standalone COMPONENT data."""
    return {
        "id": "600:1",
        "name": "logo",
        "type": "COMPONENT",
        "description": "App logo"
    }


# Category inference tests
@pytest.mark.unit
def test_infer_category_button():
    assert infer_category("button/large") == "button"


@pytest.mark.unit
def test_infer_category_input():
    assert infer_category("text field/default") == "input"


@pytest.mark.unit
def test_infer_category_nav():
    assert infer_category("nav/tabs") == "nav"


@pytest.mark.unit
def test_infer_category_none():
    assert infer_category("some random component") is None


@pytest.mark.unit
def test_infer_category_case_insensitive():
    assert infer_category("BUTTON Large") == "button"


# Variant property parsing tests
@pytest.mark.unit
def test_parse_variant_properties_standard():
    result = parse_variant_properties("size=large, style=solid, state=default")
    assert result == {"size": "large", "style": "solid", "state": "default"}


@pytest.mark.unit
def test_parse_variant_properties_single():
    result = parse_variant_properties("size=large")
    assert result == {"size": "large"}


@pytest.mark.unit
def test_parse_variant_properties_empty():
    result = parse_variant_properties("")
    assert result == {}


@pytest.mark.unit
def test_parse_variant_properties_whitespace():
    result = parse_variant_properties("size = large , style = solid")
    assert result == {"size": "large", "style": "solid"}


# Interaction axis detection tests
@pytest.mark.unit
def test_detect_interaction_axis_state():
    assert detect_interaction_axis("state", ["default", "hover", "focus"]) is True


@pytest.mark.unit
def test_detect_interaction_axis_by_values():
    assert detect_interaction_axis("status", ["default", "pressed", "disabled"]) is True


@pytest.mark.unit
def test_detect_interaction_axis_size():
    assert detect_interaction_axis("size", ["small", "medium", "large"]) is False


@pytest.mark.unit
def test_detect_interaction_axis_mixed():
    # Not ALL are interaction states
    assert detect_interaction_axis("status", ["default", "hover", "custom_state"]) is False


# Component set parsing tests
@pytest.mark.unit
def test_parse_component_set_basic():
    mock_data = _make_mock_component_set()
    result = parse_component_set(mock_data)

    assert result["name"] == "button"
    assert result["figma_node_id"] == "500:1"
    assert result["description"] == "Primary button component"
    assert len(result["variants"]) == 4
    assert result["category"] == "button"


@pytest.mark.unit
def test_parse_component_set_axes():
    mock_data = _make_mock_component_set()
    result = parse_component_set(mock_data)

    assert len(result["axes"]) == 3

    # Find each axis
    axes_by_name = {axis["axis_name"]: axis for axis in result["axes"]}

    assert "size" in axes_by_name
    assert "style" in axes_by_name
    assert "state" in axes_by_name

    # Verify interaction detection
    assert axes_by_name["size"]["is_interaction"] is False
    assert axes_by_name["style"]["is_interaction"] is False
    assert axes_by_name["state"]["is_interaction"] is True


@pytest.mark.unit
def test_parse_component_set_default_values():
    mock_data = _make_mock_component_set()
    result = parse_component_set(mock_data)

    axes_by_name = {axis["axis_name"]: axis for axis in result["axes"]}

    # state axis should have "default" as default value
    assert axes_by_name["state"]["default_value"] == "default"

    # Other axes should have first alphabetical value
    assert axes_by_name["size"]["default_value"] == "large"
    assert axes_by_name["style"]["default_value"] == "outline"


# Standalone component parsing tests
@pytest.mark.unit
def test_parse_standalone_component():
    mock_data = _make_mock_standalone_component()
    result = parse_standalone_component(mock_data)

    assert result["name"] == "logo"
    assert result["figma_node_id"] == "600:1"
    assert result["description"] == "App logo"
    assert result["variants"] == []
    assert result["axes"] == []
    assert result["variant_properties"] is None


@pytest.mark.unit
def test_parse_standalone_component_category():
    mock_data = _make_mock_standalone_component()
    result = parse_standalone_component(mock_data)

    # Logo component has no matching category
    assert result["category"] is None


# DB insertion tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_insert_component_creates_row(db_with_file):
    conn = db_with_file

    component_data = {
        "figma_node_id": "500:1",
        "name": "test_button",
        "description": "A test button",
        "category": "button",
        "variant_properties": json.dumps(["size", "state"])
    }

    component_id = insert_component(conn, 1, component_data)

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM components WHERE id = ?", (component_id,))
    row = cursor.fetchone()

    assert row is not None
    assert row[2] == "500:1"  # figma_node_id
    assert row[3] == "test_button"  # name


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_insert_component_upsert(db_with_file):
    conn = db_with_file

    component_data = {
        "figma_node_id": "500:1",
        "name": "test_button",
        "description": "Original description",
        "category": "button",
        "variant_properties": None
    }

    # First insert
    component_id1 = insert_component(conn, 1, component_data)

    # Update with same figma_node_id
    component_data["description"] = "Updated description"
    component_id2 = insert_component(conn, 1, component_data)

    # Should be the same ID
    assert component_id1 == component_id2

    # Verify only 1 row exists
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM components WHERE file_id = 1 AND figma_node_id = '500:1'")
    count = cursor.fetchone()[0]
    assert count == 1

    # Verify description was updated
    cursor.execute("SELECT description FROM components WHERE id = ?", (component_id1,))
    desc = cursor.fetchone()[0]
    assert desc == "Updated description"


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_insert_variants_creates_rows(db_with_file):
    conn = db_with_file

    # First insert a component
    component_id = insert_component(conn, 1, {
        "figma_node_id": "500:1",
        "name": "button",
        "description": None,
        "category": "button",
        "variant_properties": None
    })

    variants = [
        {"figma_node_id": "500:2", "name": "size=large, state=default", "properties": {"size": "large", "state": "default"}},
        {"figma_node_id": "500:3", "name": "size=large, state=hover", "properties": {"size": "large", "state": "hover"}},
        {"figma_node_id": "500:4", "name": "size=small, state=default", "properties": {"size": "small", "state": "default"}},
        {"figma_node_id": "500:5", "name": "size=small, state=hover", "properties": {"size": "small", "state": "hover"}},
    ]

    variant_ids = insert_variants(conn, component_id, variants)

    assert len(variant_ids) == 4

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM component_variants WHERE component_id = ?", (component_id,))
    count = cursor.fetchone()[0]
    assert count == 4


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_insert_variant_axes_creates_rows(db_with_file):
    conn = db_with_file

    # First insert a component
    component_id = insert_component(conn, 1, {
        "figma_node_id": "500:1",
        "name": "button",
        "description": None,
        "category": "button",
        "variant_properties": None
    })

    axes = [
        {"axis_name": "size", "axis_values": ["small", "large"], "is_interaction": False, "default_value": "large"},
        {"axis_name": "style", "axis_values": ["solid", "outline"], "is_interaction": False, "default_value": "solid"},
        {"axis_name": "state", "axis_values": ["default", "hover", "focus"], "is_interaction": True, "default_value": "default"},
    ]

    axis_ids = insert_variant_axes(conn, component_id, axes)

    assert len(axis_ids) == 3

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM variant_axes WHERE component_id = ?", (component_id,))
    rows = cursor.fetchall()
    assert len(rows) == 3

    # Verify is_interaction values
    for row in rows:
        axis_name = row[2]  # axis_name column
        is_interaction = row[4]  # is_interaction column
        if axis_name == "state":
            assert is_interaction == 1
        else:
            assert is_interaction == 0


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_extract_components_full(db_with_file):
    conn = db_with_file

    nodes = [
        _make_mock_component_set(),
        _make_mock_standalone_component()
    ]

    component_ids = extract_components(conn, 1, nodes)

    assert len(component_ids) == 2

    # Verify components table
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM components WHERE file_id = 1")
    assert cursor.fetchone()[0] == 2

    # Verify variants for component set
    cursor.execute("""
        SELECT COUNT(*) FROM component_variants cv
        JOIN components c ON cv.component_id = c.id
        WHERE c.figma_node_id = '500:1'
    """)
    assert cursor.fetchone()[0] == 4

    # Verify axes for component set
    cursor.execute("""
        SELECT COUNT(*) FROM variant_axes va
        JOIN components c ON va.component_id = c.id
        WHERE c.figma_node_id = '500:1'
    """)
    assert cursor.fetchone()[0] == 3

    # Verify no variants/axes for standalone
    cursor.execute("""
        SELECT COUNT(*) FROM component_variants cv
        JOIN components c ON cv.component_id = c.id
        WHERE c.figma_node_id = '600:1'
    """)
    assert cursor.fetchone()[0] == 0


# Variant dimension values tests
@pytest.mark.unit
@pytest.mark.timeout(10)
def test_populate_variant_dimension_values_basic(db_with_file):
    conn = db_with_file

    # Insert component
    component_id = insert_component(conn, 1, {
        "figma_node_id": "500:1",
        "name": "button",
        "description": None,
        "category": "button",
        "variant_properties": json.dumps(["size", "style", "state"])
    })

    # Insert variants (4 variants)
    variants = [
        {"figma_node_id": "500:2", "name": "v1", "properties": {"size": "large", "style": "solid", "state": "default"}},
        {"figma_node_id": "500:3", "name": "v2", "properties": {"size": "large", "style": "solid", "state": "hover"}},
        {"figma_node_id": "500:4", "name": "v3", "properties": {"size": "large", "style": "outline", "state": "default"}},
        {"figma_node_id": "500:5", "name": "v4", "properties": {"size": "small", "style": "solid", "state": "default"}},
    ]
    insert_variants(conn, component_id, variants)

    # Insert axes (3 axes)
    axes = [
        {"axis_name": "size", "axis_values": ["small", "large"], "is_interaction": False, "default_value": "large"},
        {"axis_name": "style", "axis_values": ["solid", "outline"], "is_interaction": False, "default_value": "solid"},
        {"axis_name": "state", "axis_values": ["default", "hover"], "is_interaction": True, "default_value": "default"},
    ]
    insert_variant_axes(conn, component_id, axes)

    # Populate dimension values
    count = populate_variant_dimension_values(conn, component_id)

    # 4 variants × 3 axes = 12 dimension values
    assert count == 12

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM variant_dimension_values")
    assert cursor.fetchone()[0] == 12


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_populate_variant_dimension_values_standalone(db_with_file):
    conn = db_with_file

    # Insert standalone component (no variants)
    component_id = insert_component(conn, 1, {
        "figma_node_id": "600:1",
        "name": "logo",
        "description": None,
        "category": None,
        "variant_properties": None
    })

    # Populate dimension values (should handle no variants gracefully)
    count = populate_variant_dimension_values(conn, component_id)

    assert count == 0


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_populate_variant_dimension_values_query(db_with_file):
    """Test the hover-state cross-component query from Agent Cookbook."""
    conn = db_with_file

    # Create two button components with hover states
    for i, name in enumerate(["primary_button", "secondary_button"], 1):
        component_id = insert_component(conn, 1, {
            "figma_node_id": f"50{i}:1",
            "name": name,
            "description": None,
            "category": "button",
            "variant_properties": json.dumps(["state"])
        })

        variants = [
            {"figma_node_id": f"50{i}:2", "name": "state=default", "properties": {"state": "default"}},
            {"figma_node_id": f"50{i}:3", "name": "state=hover", "properties": {"state": "hover"}},
        ]
        insert_variants(conn, component_id, variants)

        axes = [
            {"axis_name": "state", "axis_values": ["default", "hover"], "is_interaction": True, "default_value": "default"},
        ]
        insert_variant_axes(conn, component_id, axes)

        populate_variant_dimension_values(conn, component_id)

    # Query from Agent Cookbook
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.name, cv.name as variant_name, cv.figma_node_id
        FROM components c
        JOIN component_variants cv ON c.id = cv.component_id
        JOIN variant_dimension_values vdv ON cv.id = vdv.variant_id
        JOIN variant_axes va ON vdv.axis_id = va.id
        WHERE va.axis_name = 'state' AND vdv.value = 'hover'
        AND c.category = 'button'
    """)

    results = cursor.fetchall()
    assert len(results) == 2

    # Verify we got hover variants from both buttons
    component_names = {row[0] for row in results}
    assert "primary_button" in component_names
    assert "secondary_button" in component_names

    # All should be hover variants
    for row in results:
        assert "hover" in row[1]


# Slot inference tests
@pytest.mark.unit
def test_infer_slot_type_text():
    child = {"node_type": "TEXT", "name": "Label"}
    assert infer_slot_type(child) == "text"


@pytest.mark.unit
def test_infer_slot_type_icon_instance():
    child = {"node_type": "INSTANCE", "name": "Icon"}
    assert infer_slot_type(child) == "icon"


@pytest.mark.unit
def test_infer_slot_type_component_instance():
    child = {"node_type": "INSTANCE", "name": "Badge"}
    assert infer_slot_type(child) == "component"


@pytest.mark.unit
def test_infer_slots_filters_noise():
    children = [
        {"name": "background", "node_type": "RECTANGLE", "sort_order": 0},
        {"name": "spacer", "node_type": "FRAME", "sort_order": 1},
        {"name": "Label", "node_type": "TEXT", "sort_order": 2},
        {"name": "Icon", "node_type": "INSTANCE", "sort_order": 3},
        {"name": "divider", "node_type": "LINE", "sort_order": 4},
    ]

    slots = infer_slots(children)

    # Should only have Label and Icon
    assert len(slots) == 2
    assert slots[0]["name"] == "label"
    assert slots[1]["name"] == "icon"


@pytest.mark.unit
def test_infer_slots_snake_case_names():
    children = [
        {"name": "Leading Icon", "node_type": "INSTANCE", "sort_order": 0},
        {"name": "Main Label", "node_type": "TEXT", "sort_order": 1},
    ]

    slots = infer_slots(children)

    assert slots[0]["name"] == "leading_icon"
    assert slots[1]["name"] == "main_label"


@pytest.mark.unit
def test_infer_slots_text_required():
    children = [
        {"name": "Label", "node_type": "TEXT", "sort_order": 0, "text_content": "Submit"},
        {"name": "Icon", "node_type": "INSTANCE", "sort_order": 1},
    ]

    slots = infer_slots(children)

    # TEXT slot should be required
    assert slots[0]["is_required"] == 1
    # INSTANCE slot should be optional
    assert slots[1]["is_required"] == 0


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_insert_slots_creates_rows(db_with_file):
    conn = db_with_file

    # Insert component
    component_id = insert_component(conn, 1, {
        "figma_node_id": "500:1",
        "name": "button",
        "description": None,
        "category": "button",
        "variant_properties": None
    })

    slots = [
        {
            "name": "icon",
            "slot_type": "icon",
            "is_required": 0,
            "default_content": None,
            "sort_order": 0,
            "description": None
        },
        {
            "name": "label",
            "slot_type": "text",
            "is_required": 1,
            "default_content": json.dumps({"type": "text", "value": "Submit"}),
            "sort_order": 1,
            "description": None
        }
    ]

    slot_ids = insert_slots(conn, component_id, slots)

    assert len(slot_ids) == 2

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM component_slots WHERE component_id = ?", (component_id,))
    assert cursor.fetchone()[0] == 2


# A11y inference tests
@pytest.mark.unit
def test_infer_a11y_button():
    a11y = infer_a11y("button", "primary button")

    assert a11y["role"] == "button"
    assert a11y["required_label"] == 1
    assert a11y["min_touch_target"] == 44.0
    assert a11y["aria_properties"] == json.dumps({"aria-pressed": "boolean"})


@pytest.mark.unit
def test_infer_a11y_input():
    a11y = infer_a11y("input", "text field")

    assert a11y["role"] == "textbox"
    assert a11y["required_label"] == 1
    assert a11y["min_touch_target"] == 44.0
    assert a11y["aria_properties"] == json.dumps({"aria-required": "boolean", "aria-invalid": "boolean"})


@pytest.mark.unit
def test_infer_a11y_card():
    a11y = infer_a11y("card", "product card")

    assert a11y["role"] == "article"
    assert a11y["required_label"] == 0
    assert a11y["min_touch_target"] is None
    assert a11y["aria_properties"] is None


@pytest.mark.unit
def test_infer_a11y_from_name():
    # No category, but name contains "button"
    a11y = infer_a11y(None, "button large")

    assert a11y["role"] == "button"
    assert a11y["required_label"] == 0  # No category, so defaults to 0
    assert a11y["min_touch_target"] is None  # No category


@pytest.mark.unit
def test_infer_a11y_unknown():
    a11y = infer_a11y(None, "widget")

    assert a11y["role"] is None
    assert a11y["required_label"] == 0
    assert a11y["min_touch_target"] is None
    assert a11y["aria_properties"] is None


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_insert_a11y_creates_row(db_with_file):
    conn = db_with_file

    # Insert component
    component_id = insert_component(conn, 1, {
        "figma_node_id": "500:1",
        "name": "button",
        "description": None,
        "category": "button",
        "variant_properties": None
    })

    a11y_data = {
        "role": "button",
        "required_label": 1,
        "focus_order": None,
        "min_touch_target": 44.0,
        "keyboard_shortcut": None,
        "aria_properties": json.dumps({"aria-pressed": "boolean"}),
        "notes": None
    }

    row_id = insert_a11y(conn, component_id, a11y_data)

    assert row_id is not None

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM component_a11y WHERE component_id = ?", (component_id,))
    row = cursor.fetchone()

    assert row is not None
    assert row[2] == "button"  # role
    assert row[3] == 1  # required_label
    assert row[5] == 44.0  # min_touch_target


@pytest.mark.unit
@pytest.mark.timeout(10)
def test_insert_a11y_upsert(db_with_file):
    conn = db_with_file

    # Insert component
    component_id = insert_component(conn, 1, {
        "figma_node_id": "500:1",
        "name": "button",
        "description": None,
        "category": "button",
        "variant_properties": None
    })

    # First insert
    a11y_data = {
        "role": "button",
        "required_label": 1,
        "focus_order": None,
        "min_touch_target": 44.0,
        "keyboard_shortcut": None,
        "aria_properties": None,
        "notes": "Original note"
    }

    row_id1 = insert_a11y(conn, component_id, a11y_data)

    # Update with new data
    a11y_data["notes"] = "Updated note"
    row_id2 = insert_a11y(conn, component_id, a11y_data)

    # Should be the same row
    assert row_id1 == row_id2

    # Verify only 1 row exists
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM component_a11y WHERE component_id = ?", (component_id,))
    assert cursor.fetchone()[0] == 1

    # Verify notes updated
    cursor.execute("SELECT notes FROM component_a11y WHERE component_id = ?", (component_id,))
    assert cursor.fetchone()[0] == "Updated note"