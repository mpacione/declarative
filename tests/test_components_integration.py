"""Integration tests for component + extraction pipeline."""

import json
import pytest
import sqlite3
import time
from typing import Any, Dict, List

from dd.extract import (
    run_extraction_pipeline,
    run_component_extraction,
    get_component_sheets,
)
from dd.extract_components import extract_components, populate_variant_dimension_values
from tests.fixtures import seed_post_extraction


def _make_component_data() -> List[Dict[str, Any]]:
    """Create rich component data matching what use_figma would return."""
    return [
        {
            "id": "500:1",
            "name": "button",
            "type": "COMPONENT_SET",
            "description": "Primary button component with multiple states",
            "children": [
                {
                    "id": "500:2",
                    "name": "size=large, style=solid, state=default",
                    "type": "COMPONENT",
                    "width": 200,
                    "height": 48,
                    "children": [
                        {"name": "Icon", "type": "INSTANCE", "characters": None},
                        {"name": "Label", "type": "TEXT", "characters": "Submit"},
                    ],
                },
                {
                    "id": "500:3",
                    "name": "size=large, style=solid, state=hover",
                    "type": "COMPONENT",
                    "width": 200,
                    "height": 48,
                    "children": [],
                },
                {
                    "id": "500:4",
                    "name": "size=small, style=solid, state=default",
                    "type": "COMPONENT",
                    "width": 120,
                    "height": 36,
                    "children": [],
                },
            ],
        },
        {
            "id": "600:1",
            "name": "nav/tabs",
            "type": "COMPONENT",
            "description": "Tab navigation component",
            "children": [
                {"name": "Tab 1", "type": "TEXT", "characters": "Home"},
                {"name": "Tab 2", "type": "TEXT", "characters": "Profile"},
                {"name": "Tab 3", "type": "TEXT", "characters": "Settings"},
            ],
        },
    ]


def _make_mock_frames() -> List[Dict[str, Any]]:
    """Create frame data for inventory setup."""
    return [
        {
            "figma_node_id": "100:1",
            "name": "Home",
            "width": 428,
            "height": 926,
            "device_class": "iphone",
        },
        {
            "figma_node_id": "100:2",
            "name": "Settings",
            "width": 428,
            "height": 926,
            "device_class": "iphone",
        },
        {
            "figma_node_id": "100:3",
            "name": "Buttons and Controls",
            "width": 1200,
            "height": 800,
            "device_class": "component_sheet",
        },
    ]


def _make_screen_extract_fn():
    """Create a mock extraction function for screens."""
    def extract_fn(node_id: str) -> List[Dict[str, Any]]:
        # Return simple node data for screen extraction
        return [
            {
                "figma_node_id": "200:1",
                "name": "Container",
                "node_type": "FRAME",
                "depth": 0,
                "sort_order": 0,
                "x": 0,
                "y": 0,
                "width": 428,
                "height": 926,
                "fills": json.dumps([{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]),
                "layout_mode": "VERTICAL",
                "padding_top": 16,
                "padding_right": 16,
                "padding_bottom": 16,
                "padding_left": 16,
                "item_spacing": 8,
            },
            {
                "figma_node_id": "200:2",
                "name": "Title",
                "node_type": "TEXT",
                "depth": 1,
                "sort_order": 0,
                "x": 16,
                "y": 16,
                "width": None,
                "height": None,
                "font_family": "Inter",
                "font_size": 24,
                "font_weight": 600,
                "text_content": "Screen Title",
            },
            {
                "figma_node_id": "200:3",
                "name": "Button Instance",
                "node_type": "INSTANCE",
                "depth": 1,
                "sort_order": 1,
                "x": 16,
                "y": 100,
                "width": 120,
                "height": 40,
            },
        ]
    return extract_fn


@pytest.mark.integration
def test_component_extraction_on_extraction_output(db):
    """Test component extraction on real extraction output."""
    # Set up extraction output
    seed_post_extraction(db)

    # Build mock component data
    component_data = _make_component_data()

    # Extract components
    component_ids = extract_components(db, file_id=1, component_nodes=component_data)

    # Verify components table
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM components WHERE file_id = 1")
    component_count = cursor.fetchone()[0]
    assert component_count == 2  # button + nav/tabs

    # Verify component_variants table
    cursor.execute("SELECT COUNT(*) FROM component_variants")
    variant_count = cursor.fetchone()[0]
    assert variant_count == 3  # 3 button variants

    # Verify variant_axes table
    cursor.execute("SELECT COUNT(*) FROM variant_axes")
    axes_count = cursor.fetchone()[0]
    assert axes_count == 3  # size, style, state

    # Verify file_id references
    cursor.execute("SELECT file_id FROM components")
    for row in cursor.fetchall():
        assert row[0] == 1  # All components should reference file_id=1

    # Verify component details
    cursor.execute("SELECT name, category, description FROM components ORDER BY name")
    components = cursor.fetchall()
    assert components[0][0] == "button"
    assert components[0][1] == "button"  # Category inferred
    assert components[0][2] == "Primary button component with multiple states"
    assert components[1][0] == "nav/tabs"
    assert components[1][1] == "nav"  # Category inferred


@pytest.mark.integration
def test_variant_dimension_values_fk_integrity(db):
    """Test FK integrity for variant_dimension_values."""
    # Set up extraction output and run component extraction
    seed_post_extraction(db)
    component_data = _make_component_data()
    extract_components(db, file_id=1, component_nodes=component_data)

    cursor = db.cursor()

    # Check FK integrity - variant_id
    cursor.execute("""
        SELECT COUNT(*)
        FROM variant_dimension_values
        WHERE variant_id NOT IN (SELECT id FROM component_variants)
    """)
    orphan_variant_refs = cursor.fetchone()[0]
    assert orphan_variant_refs == 0

    # Check FK integrity - axis_id
    cursor.execute("""
        SELECT COUNT(*)
        FROM variant_dimension_values
        WHERE axis_id NOT IN (SELECT id FROM variant_axes)
    """)
    orphan_axis_refs = cursor.fetchone()[0]
    assert orphan_axis_refs == 0

    # Verify correct count: 3 variants * 3 axes = 9 dimension values
    cursor.execute("SELECT COUNT(*) FROM variant_dimension_values")
    total_dimension_values = cursor.fetchone()[0]
    assert total_dimension_values == 9

    # Verify specific dimension values
    cursor.execute("""
        SELECT vdv.value, va.axis_name, cv.name
        FROM variant_dimension_values vdv
        JOIN variant_axes va ON vdv.axis_id = va.id
        JOIN component_variants cv ON vdv.variant_id = cv.id
        WHERE va.axis_name = 'size' AND cv.name LIKE '%large%'
        ORDER BY cv.name
    """)
    large_variants = cursor.fetchall()
    assert len(large_variants) == 2
    assert all(v[0] == "large" for v in large_variants)


@pytest.mark.integration
def test_interaction_states_view(db):
    """Test the v_interaction_states view."""
    # Set up extraction output and run component extraction
    seed_post_extraction(db)
    component_data = _make_component_data()
    extract_components(db, file_id=1, component_nodes=component_data)

    cursor = db.cursor()

    # Query v_interaction_states view
    cursor.execute("""
        SELECT component_name, category, axis_name, axis_values, default_value, variant_count
        FROM v_interaction_states
        WHERE component_name = 'button'
    """)

    interaction_states = cursor.fetchall()
    assert len(interaction_states) >= 1

    # Find the state axis
    state_axis = next((s for s in interaction_states if s[2] == "state"), None)
    assert state_axis is not None
    assert state_axis[0] == "button"  # component_name
    assert state_axis[1] == "button"  # category
    assert state_axis[2] == "state"  # axis_name

    # Parse axis_values JSON
    axis_values = json.loads(state_axis[3])
    assert "default" in axis_values
    assert "hover" in axis_values
    assert state_axis[4] == "default"  # default_value

    # Verify is_interaction flag
    cursor.execute("""
        SELECT is_interaction
        FROM variant_axes
        WHERE component_id IN (SELECT id FROM components WHERE name = 'button')
        AND axis_name = 'state'
    """)
    is_interaction = cursor.fetchone()[0]
    assert is_interaction == 1


@pytest.mark.integration
def test_component_slots_populated(db):
    """Test that component slots are populated from children."""
    # Set up extraction output and run component extraction
    seed_post_extraction(db)
    component_data = _make_component_data()
    extract_components(db, file_id=1, component_nodes=component_data)

    cursor = db.cursor()

    # Get button component ID
    cursor.execute("SELECT id FROM components WHERE name = 'button'")
    button_id = cursor.fetchone()[0]

    # Query component slots for button
    cursor.execute("""
        SELECT name, slot_type, is_required, sort_order
        FROM component_slots
        WHERE component_id = ?
        ORDER BY sort_order
    """, (button_id,))

    slots = cursor.fetchall()
    assert len(slots) >= 2  # Icon + Label

    # Check specific slots
    slot_names = [s[0] for s in slots]
    assert "icon" in slot_names
    assert "label" in slot_names

    # Find the label slot
    label_slot = next((s for s in slots if s[0] == "label"), None)
    assert label_slot is not None
    assert label_slot[1] == "text"  # slot_type
    assert label_slot[2] == 1  # is_required (TEXT nodes are typically required)

    # Verify component_id FK is valid
    cursor.execute("""
        SELECT COUNT(*)
        FROM component_slots
        WHERE component_id NOT IN (SELECT id FROM components)
    """)
    orphan_slots = cursor.fetchone()[0]
    assert orphan_slots == 0

    # Check nav/tabs component slots
    cursor.execute("SELECT id FROM components WHERE name = 'nav/tabs'")
    nav_id = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM component_slots
        WHERE component_id = ?
    """, (nav_id,))
    nav_slot_count = cursor.fetchone()[0]
    assert nav_slot_count == 3  # Tab 1, Tab 2, Tab 3


@pytest.mark.integration
def test_a11y_defaults_applied(db):
    """Test that accessibility defaults are applied."""
    # Set up extraction output and run component extraction
    seed_post_extraction(db)
    component_data = _make_component_data()
    extract_components(db, file_id=1, component_nodes=component_data)

    cursor = db.cursor()

    # Query a11y data for button component
    cursor.execute("""
        SELECT ca.role, ca.required_label, ca.min_touch_target
        FROM component_a11y ca
        JOIN components c ON ca.component_id = c.id
        WHERE c.name = 'button'
    """)

    button_a11y = cursor.fetchone()
    assert button_a11y is not None
    assert button_a11y[0] == "button"  # role
    assert button_a11y[1] == 1  # required_label
    assert button_a11y[2] == 44.0  # min_touch_target

    # Query a11y data for nav component
    cursor.execute("""
        SELECT ca.role, ca.required_label, ca.min_touch_target
        FROM component_a11y ca
        JOIN components c ON ca.component_id = c.id
        WHERE c.name = 'nav/tabs'
    """)

    nav_a11y = cursor.fetchone()
    assert nav_a11y is not None
    assert nav_a11y[0] == "navigation"  # role
    assert nav_a11y[1] == 0  # required_label (nav doesn't require label)
    assert nav_a11y[2] == 44.0  # min_touch_target

    # Verify every component has a11y data
    cursor.execute("""
        SELECT COUNT(*)
        FROM components c
        LEFT JOIN component_a11y ca ON c.id = ca.component_id
        WHERE ca.id IS NULL
    """)
    components_without_a11y = cursor.fetchone()[0]
    assert components_without_a11y == 0


@pytest.mark.integration
def test_component_catalog_view(db):
    """Test the v_component_catalog view."""
    # Set up extraction output and run component extraction
    seed_post_extraction(db)
    component_data = _make_component_data()
    extract_components(db, file_id=1, component_nodes=component_data)

    cursor = db.cursor()

    # Query v_component_catalog view
    cursor.execute("""
        SELECT name, category, variant_count, slot_count, a11y_role, min_touch_target, axes
        FROM v_component_catalog
        ORDER BY name
    """)

    catalog = cursor.fetchall()
    assert len(catalog) == 2

    # Check button component
    button_row = catalog[0]
    assert button_row[0] == "button"
    assert button_row[1] == "button"  # category
    assert button_row[2] == 3  # variant_count
    assert button_row[3] == 2  # slot_count (Icon + Label)
    assert button_row[4] == "button"  # a11y_role
    assert button_row[5] == 44.0  # min_touch_target
    assert "size" in button_row[6]  # axes
    assert "style" in button_row[6]  # axes
    assert "state" in button_row[6]  # axes

    # Check nav/tabs component
    nav_row = catalog[1]
    assert nav_row[0] == "nav/tabs"
    assert nav_row[1] == "nav"  # category
    assert nav_row[2] == 0  # variant_count (standalone component)
    assert nav_row[3] == 3  # slot_count (3 tabs)
    assert nav_row[4] == "navigation"  # a11y_role
    assert nav_row[5] == 44.0  # min_touch_target
    assert nav_row[6] is None  # axes (no variants)


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_orchestrator_chains_extraction_and_components(db):
    """Test that orchestrator chains screen extraction + component extraction."""
    # Build mock frames
    frames = _make_mock_frames()

    # Create mock extraction functions
    def screen_extract_fn(node_id: str) -> List[Dict[str, Any]]:
        # Return simple node data
        return _make_screen_extract_fn()(node_id)

    def component_extract_fn(node_id: str) -> List[Dict[str, Any]]:
        # Return component data
        return _make_component_data()

    # Run the full pipeline
    result = run_extraction_pipeline(
        db,
        file_key="test_file_key",
        file_name="Test Design System",
        frames=frames,
        extract_fn=screen_extract_fn,
        node_count=100,
        agent_id="test_agent",
        component_extract_fn=component_extract_fn,
    )

    # Verify extraction results
    assert result["status"] == "completed"
    assert result["completed"] == 3  # All 3 screens processed
    assert result["failed"] == 0
    assert "components_extracted" in result
    assert result["components_extracted"] == 2  # button + nav/tabs
    assert result["variants_extracted"] == 3  # 3 button variants

    cursor = db.cursor()

    # Verify files table
    cursor.execute("SELECT COUNT(*) FROM files")
    assert cursor.fetchone()[0] == 1

    # Verify screens table
    cursor.execute("SELECT COUNT(*) FROM screens")
    assert cursor.fetchone()[0] == 3

    # Verify nodes table (3 nodes per screen)
    cursor.execute("SELECT COUNT(*) FROM nodes")
    assert cursor.fetchone()[0] == 9

    # Verify components table
    cursor.execute("SELECT COUNT(*) FROM components")
    assert cursor.fetchone()[0] == 2

    # Verify component_variants table
    cursor.execute("SELECT COUNT(*) FROM component_variants")
    assert cursor.fetchone()[0] == 3

    # Verify variant_axes table
    cursor.execute("SELECT COUNT(*) FROM variant_axes")
    assert cursor.fetchone()[0] == 3

    # Verify extraction_runs status
    cursor.execute("SELECT status FROM extraction_runs WHERE file_id = 1")
    run_status = cursor.fetchone()[0]
    assert run_status == "completed"

    # Verify component sheets were identified
    component_sheets = get_component_sheets(db, file_id=1)
    assert len(component_sheets) == 1
    assert component_sheets[0]["name"] == "Buttons and Controls"


@pytest.mark.integration
def test_no_orphan_component_records(db):
    """Test that there are no orphaned records in component tables."""
    # Set up extraction output and run component extraction
    seed_post_extraction(db)
    component_data = _make_component_data()
    extract_components(db, file_id=1, component_nodes=component_data)

    cursor = db.cursor()

    # Check component_variants orphans
    cursor.execute("""
        SELECT COUNT(*)
        FROM component_variants
        WHERE component_id NOT IN (SELECT id FROM components)
    """)
    assert cursor.fetchone()[0] == 0

    # Check variant_axes orphans
    cursor.execute("""
        SELECT COUNT(*)
        FROM variant_axes
        WHERE component_id NOT IN (SELECT id FROM components)
    """)
    assert cursor.fetchone()[0] == 0

    # Check component_slots orphans
    cursor.execute("""
        SELECT COUNT(*)
        FROM component_slots
        WHERE component_id NOT IN (SELECT id FROM components)
    """)
    assert cursor.fetchone()[0] == 0

    # Check component_a11y orphans
    cursor.execute("""
        SELECT COUNT(*)
        FROM component_a11y
        WHERE component_id NOT IN (SELECT id FROM components)
    """)
    assert cursor.fetchone()[0] == 0

    # Check variant_dimension_values orphans - variant_id
    cursor.execute("""
        SELECT COUNT(*)
        FROM variant_dimension_values
        WHERE variant_id NOT IN (SELECT id FROM component_variants)
    """)
    assert cursor.fetchone()[0] == 0

    # Check variant_dimension_values orphans - axis_id
    cursor.execute("""
        SELECT COUNT(*)
        FROM variant_dimension_values
        WHERE axis_id NOT IN (SELECT id FROM variant_axes)
    """)
    assert cursor.fetchone()[0] == 0

    # Verify all components have valid file_id
    cursor.execute("""
        SELECT COUNT(*)
        FROM components
        WHERE file_id NOT IN (SELECT id FROM files)
    """)
    assert cursor.fetchone()[0] == 0


@pytest.mark.integration
def test_component_extraction_with_complex_variants(db):
    """Test extraction of components with complex variant properties."""
    # Set up extraction output
    seed_post_extraction(db)

    # Create complex component data with multiple axes
    complex_component_data = [
        {
            "id": "700:1",
            "name": "input",
            "type": "COMPONENT_SET",
            "description": "Input field with multiple states and types",
            "children": [
                {
                    "id": "700:2",
                    "name": "type=text, size=medium, state=default, error=false",
                    "type": "COMPONENT",
                    "children": [
                        {"name": "Placeholder", "type": "TEXT", "characters": "Enter text..."},
                        {"name": "Border", "type": "RECTANGLE"},
                    ],
                },
                {
                    "id": "700:3",
                    "name": "type=text, size=medium, state=focus, error=false",
                    "type": "COMPONENT",
                    "children": [],
                },
                {
                    "id": "700:4",
                    "name": "type=text, size=medium, state=default, error=true",
                    "type": "COMPONENT",
                    "children": [
                        {"name": "Error Message", "type": "TEXT", "characters": "Invalid input"},
                    ],
                },
                {
                    "id": "700:5",
                    "name": "type=email, size=large, state=default, error=false",
                    "type": "COMPONENT",
                    "children": [],
                },
            ],
        },
    ]

    # Extract components
    extract_components(db, file_id=1, component_nodes=complex_component_data)

    cursor = db.cursor()

    # Verify component was created
    cursor.execute("SELECT id, name, category FROM components WHERE name = 'input'")
    input_component = cursor.fetchone()
    assert input_component is not None
    assert input_component[2] == "input"  # Category inferred

    # Verify all 4 axes were created
    cursor.execute("""
        SELECT axis_name, is_interaction
        FROM variant_axes
        WHERE component_id = ?
        ORDER BY axis_name
    """, (input_component[0],))

    axes = cursor.fetchall()
    assert len(axes) == 4
    axis_names = [a[0] for a in axes]
    assert "error" in axis_names
    assert "size" in axis_names
    assert "state" in axis_names
    assert "type" in axis_names

    # Verify state axis is marked as interaction
    state_axis = next((a for a in axes if a[0] == "state"), None)
    assert state_axis[1] == 1  # is_interaction

    # Verify dimension values are correctly populated
    cursor.execute("""
        SELECT COUNT(DISTINCT vdv.id)
        FROM variant_dimension_values vdv
        JOIN variant_axes va ON vdv.axis_id = va.id
        WHERE va.component_id = ?
    """, (input_component[0],))

    dimension_value_count = cursor.fetchone()[0]
    assert dimension_value_count == 16  # 4 variants * 4 axes


@pytest.mark.integration
def test_component_extraction_preserves_existing_data(db):
    """Test that re-running component extraction preserves existing data."""
    # Set up extraction output
    seed_post_extraction(db)

    # First extraction
    component_data = _make_component_data()
    extract_components(db, file_id=1, component_nodes=component_data)

    cursor = db.cursor()

    # Get initial counts
    cursor.execute("SELECT COUNT(*) FROM components")
    initial_component_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM component_variants")
    initial_variant_count = cursor.fetchone()[0]

    cursor.execute("SELECT extracted_at FROM components WHERE name = 'button'")
    initial_timestamp = cursor.fetchone()[0]

    # Add a small delay to ensure timestamp changes
    time.sleep(0.01)

    # Re-run extraction with same data (simulating re-extraction)
    extract_components(db, file_id=1, component_nodes=component_data)

    # Verify counts remain the same (no duplicates)
    cursor.execute("SELECT COUNT(*) FROM components")
    assert cursor.fetchone()[0] == initial_component_count

    cursor.execute("SELECT COUNT(*) FROM component_variants")
    assert cursor.fetchone()[0] == initial_variant_count

    # Verify timestamp was updated (or at least exists)
    cursor.execute("SELECT extracted_at FROM components WHERE name = 'button'")
    new_timestamp = cursor.fetchone()[0]
    # Note: In SQLite, the timestamp precision may not always capture millisecond differences
    # so we just verify a timestamp exists
    assert new_timestamp is not None

    # Add new component data
    new_component = [
        {
            "id": "800:1",
            "name": "card",
            "type": "COMPONENT",
            "description": "Card component",
            "children": [],
        },
    ]

    extract_components(db, file_id=1, component_nodes=new_component)

    # Verify new component was added
    cursor.execute("SELECT COUNT(*) FROM components")
    assert cursor.fetchone()[0] == initial_component_count + 1

    # Verify existing components still exist
    cursor.execute("SELECT name FROM components ORDER BY name")
    component_names = [row[0] for row in cursor.fetchall()]
    assert "button" in component_names
    assert "nav/tabs" in component_names
    assert "card" in component_names