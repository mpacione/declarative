"""Component extraction logic for Phase 4 of the DD pipeline.

This module parses component/component_set data fetched from Figma via MCP,
structures it, and writes to the database. It does not call MCP directly.
"""

import json
import sqlite3
from typing import Dict, List, Optional, FrozenSet, Any

from dd.db import get_connection


# Interaction state values that indicate interaction-related variant axes
INTERACTION_STATE_VALUES: FrozenSet[str] = frozenset({
    "default", "hover", "focus", "pressed", "disabled", "selected", "loading"
})

# Component category keywords for auto-categorization
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "button": ["button", "btn"],
    "input": ["input", "text field", "textfield", "search"],
    "nav": ["nav", "tab", "menu", "sidebar"],
    "card": ["card"],
    "modal": ["modal", "dialog", "popup", "popover", "sheet"],
    "icon": ["icon"],
    "layout": ["layout", "container", "stack"],
    "chrome": ["status bar", "home indicator", "chrome"],
}

# Names/patterns that indicate non-slot children (structural noise)
NON_SLOT_HEURISTICS: FrozenSet[str] = frozenset({
    "background", "bg", "divider", "separator", "spacer", "line", "border", "overlay", "shadow"
})


def infer_category(name: str) -> Optional[str]:
    """
    Infer component category from its name using keyword matching.

    Args:
        name: Component name to analyze

    Returns:
        The first matching category, or None if no match
    """
    name_lower = name.lower()

    # Check for icon first (more specific)
    if "icon" in name_lower:
        return "icon"

    for category, keywords in CATEGORY_KEYWORDS.items():
        if category == "icon":  # Skip icon, already checked
            continue
        for keyword in keywords:
            if keyword in name_lower:
                return category
    return None


def parse_variant_properties(variant_name: str) -> Dict[str, str]:
    """
    Parse a Figma variant name into property key-value pairs.

    Examples:
        "size=large, style=solid, state=default" -> {"size": "large", "style": "solid", "state": "default"}
        "size=large" -> {"size": "large"}

    Args:
        variant_name: Variant name string from Figma

    Returns:
        Dictionary of property names to values
    """
    properties = {}

    # Split on comma-space separator
    parts = variant_name.split(", ")

    for part in parts:
        # Strip any extra whitespace
        part = part.strip()

        # Split on equals sign
        if "=" in part:
            key, value = part.split("=", 1)
            properties[key.strip()] = value.strip()

    return properties


def detect_interaction_axis(axis_name: str, axis_values: List[str]) -> bool:
    """
    Detect if an axis represents interaction states.

    Returns True if:
    - The axis name is "state" (case-insensitive), OR
    - ALL values in axis_values are members of INTERACTION_STATE_VALUES

    Args:
        axis_name: Name of the axis
        axis_values: List of possible values for this axis

    Returns:
        True if this is an interaction axis
    """
    # Check if axis name is "state"
    if axis_name.lower() == "state":
        return True

    # Check if all values are interaction states
    if not axis_values:
        return False

    # Convert all values to lowercase for comparison
    lower_values = {value.lower() for value in axis_values}
    return lower_values.issubset(INTERACTION_STATE_VALUES)


def infer_slot_type(child: Dict[str, Any]) -> str:
    """
    Infer the slot type based on a child node's properties.

    Args:
        child: Dict with 'node_type' and optionally 'name' keys

    Returns:
        The inferred slot type: "text", "icon", "component", "image", or "any"
    """
    node_type = child.get("node_type", "")
    name = child.get("name", "").lower()

    # TEXT nodes are text slots
    if node_type == "TEXT":
        return "text"

    # INSTANCE nodes could be icons or components
    if node_type == "INSTANCE":
        if "icon" in name:
            return "icon"
        return "component"

    # VECTOR and ELLIPSE are typically icons
    if node_type in ("VECTOR", "ELLIPSE"):
        return "icon"

    # RECTANGLE might be an image placeholder
    if node_type == "RECTANGLE":
        if any(keyword in name for keyword in ("image", "photo", "avatar")):
            return "image"

    # Everything else is "any"
    return "any"


def infer_slots(children: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Infer component slots from direct children of a component.

    Filters out non-slot children (background, dividers, etc.) and converts
    remaining children into slot definitions.

    Args:
        children: List of dicts with keys: name, node_type, sort_order,
                 optionally text_content, width, height

    Returns:
        List of slot dicts with keys: name, slot_type, is_required,
        default_content, sort_order, description
    """
    slots = []

    for child in children:
        child_name = child.get("name", "")
        child_name_lower = child_name.lower()

        # Check if this is a non-slot child
        is_non_slot = False
        for pattern in NON_SLOT_HEURISTICS:
            if pattern in child_name_lower or child_name_lower.startswith(pattern):
                is_non_slot = True
                break

        if is_non_slot:
            continue

        # Convert name to snake_case for slot name
        slot_name = child_name.replace(" ", "_").lower()

        # Infer slot type
        slot_type = infer_slot_type(child)

        # TEXT nodes are typically required (labels), others are optional
        is_required = 1 if child.get("node_type") == "TEXT" else 0

        # For TEXT nodes, store default content if available
        default_content = None
        if child.get("node_type") == "TEXT" and "text_content" in child:
            default_content = json.dumps({
                "type": "text",
                "value": child["text_content"]
            })

        slots.append({
            "name": slot_name,
            "slot_type": slot_type,
            "is_required": is_required,
            "default_content": default_content,
            "sort_order": child.get("sort_order", 0),
            "description": None
        })

    return slots


def insert_slots(conn: sqlite3.Connection, component_id: int, slots: List[Dict[str, Any]]) -> List[int]:
    """
    Insert or update component slots in the database.

    Args:
        conn: Database connection
        component_id: ID of the parent component
        slots: List of slot dicts

    Returns:
        List of slot IDs
    """
    cursor = conn.cursor()
    slot_ids = []

    for slot in slots:
        cursor.execute("""
            INSERT INTO component_slots (
                component_id, name, slot_type, is_required,
                default_content, sort_order, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(component_id, name) DO UPDATE SET
                slot_type = excluded.slot_type,
                is_required = excluded.is_required,
                default_content = excluded.default_content,
                sort_order = excluded.sort_order,
                description = COALESCE(excluded.description, component_slots.description)
        """, (
            component_id,
            slot["name"],
            slot["slot_type"],
            slot["is_required"],
            slot["default_content"],
            slot["sort_order"],
            slot["description"]
        ))

        # Get the slot ID
        cursor.execute(
            "SELECT id FROM component_slots WHERE component_id = ? AND name = ?",
            (component_id, slot["name"])
        )
        slot_id = cursor.fetchone()[0]
        slot_ids.append(slot_id)

    return slot_ids


def extract_slots_from_nodes(conn: sqlite3.Connection, component_id: int,
                           component_figma_node_id: str,
                           children: Optional[List[Dict[str, Any]]] = None) -> List[int]:
    """
    Extract and insert slots for a component from its children.

    Args:
        conn: Database connection
        component_id: ID of the component
        component_figma_node_id: Figma node ID of the component
        children: Optional list of child dicts. If not provided, queries the DB.

    Returns:
        List of slot IDs
    """
    if children is None:
        # Query the database for children
        # This is a simplified approach - in practice, we'd need to find
        # the actual child nodes from a component_sheet screen
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, node_type, sort_order
            FROM nodes
            WHERE component_id = ?
            ORDER BY sort_order
        """, (component_id,))

        children = []
        for row in cursor.fetchall():
            children.append({
                "name": row[0],
                "node_type": row[1],
                "sort_order": row[2]
            })

    # Infer slots from children
    slots = infer_slots(children)

    # Insert slots into database
    if slots:
        return insert_slots(conn, component_id, slots)

    return []


def parse_component_set(component_set_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse a COMPONENT_SET node from Figma.

    Args:
        component_set_data: Dict with keys: id, name, type, children (list of COMPONENT nodes)

    Returns:
        Structured dict with component info, variants, and axes
    """
    figma_node_id = component_set_data["id"]
    name = component_set_data["name"]
    description = component_set_data.get("description")

    # Parse variants from children
    variants = []
    all_axes = {}  # axis_name -> set of values

    children = component_set_data.get("children", [])
    for child in children:
        if child.get("type") == "COMPONENT":
            child_id = child["id"]
            child_name = child.get("name", "")

            # Parse variant properties from the name
            properties = parse_variant_properties(child_name)

            variants.append({
                "figma_node_id": child_id,
                "name": child_name,
                "properties": properties
            })

            # Collect axes and values
            for axis_name, value in properties.items():
                if axis_name not in all_axes:
                    all_axes[axis_name] = set()
                all_axes[axis_name].add(value)

    # Process axes
    axes = []
    for axis_name, values in all_axes.items():
        values_list = sorted(list(values))

        # Determine default value
        default_value = None
        if "default" in values_list:
            default_value = "default"
        elif values_list:
            # Use the first value (after sorting) as default
            default_value = values_list[0]

        # Detect if this is an interaction axis
        is_interaction = detect_interaction_axis(axis_name, values_list)

        axes.append({
            "axis_name": axis_name,
            "axis_values": values_list,
            "is_interaction": is_interaction,
            "default_value": default_value
        })

    # Infer category
    category = infer_category(name)

    # Get variant properties (list of axis names)
    variant_properties = sorted(list(all_axes.keys())) if all_axes else None

    # Extract children from first variant if available
    variant_children = None
    if variants and children:
        # Find the first variant's children in the original data
        first_variant_id = variants[0]["figma_node_id"]
        for child in children:
            if child.get("id") == first_variant_id and "children" in child:
                variant_children = child["children"]
                break

    return {
        "figma_node_id": figma_node_id,
        "name": name,
        "description": description,
        "category": category,
        "variant_properties": json.dumps(variant_properties) if variant_properties else None,
        "variants": variants,
        "axes": axes,
        "children": variant_children
    }


def parse_standalone_component(component_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse a standalone COMPONENT node (not part of a COMPONENT_SET).

    Args:
        component_data: Dict with keys: id, name, type, optionally description

    Returns:
        Structured dict with component info (no variants or axes)
    """
    figma_node_id = component_data["id"]
    name = component_data["name"]
    description = component_data.get("description")

    # Infer category
    category = infer_category(name)

    # Get children if available
    children = component_data.get("children")

    return {
        "figma_node_id": figma_node_id,
        "name": name,
        "description": description,
        "category": category,
        "variant_properties": None,
        "variants": [],
        "axes": [],
        "children": children
    }


def insert_component(conn: sqlite3.Connection, file_id: int, component_data: Dict[str, Any]) -> int:
    """
    Insert or update a component in the database.

    Args:
        conn: Database connection
        file_id: ID of the file this component belongs to
        component_data: Parsed component data

    Returns:
        The component ID
    """
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO components (
            file_id, figma_node_id, name, description,
            category, variant_properties
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_id, figma_node_id) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            category = excluded.category,
            variant_properties = excluded.variant_properties,
            extracted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    """, (
        file_id,
        component_data["figma_node_id"],
        component_data["name"],
        component_data["description"],
        component_data["category"],
        component_data["variant_properties"]
    ))

    # Get the component ID
    cursor.execute(
        "SELECT id FROM components WHERE file_id = ? AND figma_node_id = ?",
        (file_id, component_data["figma_node_id"])
    )
    component_id = cursor.fetchone()[0]

    return component_id


def insert_variants(conn: sqlite3.Connection, component_id: int, variants: List[Dict[str, Any]]) -> List[int]:
    """
    Insert or update variants for a component.

    Args:
        conn: Database connection
        component_id: ID of the parent component
        variants: List of variant data dicts

    Returns:
        List of variant IDs
    """
    cursor = conn.cursor()
    variant_ids = []

    for variant in variants:
        properties_json = json.dumps(variant["properties"])

        cursor.execute("""
            INSERT INTO component_variants (
                component_id, figma_node_id, name, properties
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(component_id, figma_node_id) DO UPDATE SET
                name = excluded.name,
                properties = excluded.properties
        """, (
            component_id,
            variant["figma_node_id"],
            variant["name"],
            properties_json
        ))

        # Get the variant ID
        cursor.execute(
            "SELECT id FROM component_variants WHERE component_id = ? AND figma_node_id = ?",
            (component_id, variant["figma_node_id"])
        )
        variant_id = cursor.fetchone()[0]
        variant_ids.append(variant_id)

    return variant_ids


def insert_variant_axes(conn: sqlite3.Connection, component_id: int, axes: List[Dict[str, Any]]) -> List[int]:
    """
    Insert or update variant axes for a component.

    Args:
        conn: Database connection
        component_id: ID of the parent component
        axes: List of axis data dicts

    Returns:
        List of axis IDs
    """
    cursor = conn.cursor()
    axis_ids = []

    for axis in axes:
        axis_values_json = json.dumps(axis["axis_values"])

        cursor.execute("""
            INSERT INTO variant_axes (
                component_id, axis_name, axis_values,
                is_interaction, default_value
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(component_id, axis_name) DO UPDATE SET
                axis_values = excluded.axis_values,
                is_interaction = excluded.is_interaction,
                default_value = excluded.default_value
        """, (
            component_id,
            axis["axis_name"],
            axis_values_json,
            1 if axis["is_interaction"] else 0,
            axis["default_value"]
        ))

        # Get the axis ID
        cursor.execute(
            "SELECT id FROM variant_axes WHERE component_id = ? AND axis_name = ?",
            (component_id, axis["axis_name"])
        )
        axis_id = cursor.fetchone()[0]
        axis_ids.append(axis_id)

    return axis_ids


def populate_variant_dimension_values(conn: sqlite3.Connection, component_id: int) -> int:
    """
    Populate variant_dimension_values table linking each variant to its axis values.

    Args:
        conn: Database connection
        component_id: ID of the component to populate dimension values for

    Returns:
        Total number of dimension values inserted/updated
    """
    cursor = conn.cursor()

    # Query all variants for this component
    cursor.execute("""
        SELECT id, properties
        FROM component_variants
        WHERE component_id = ?
    """, (component_id,))
    variants = cursor.fetchall()

    # Return 0 if no variants
    if not variants:
        return 0

    # Query all axes for this component
    cursor.execute("""
        SELECT id, axis_name
        FROM variant_axes
        WHERE component_id = ?
    """, (component_id,))
    axes = cursor.fetchall()

    # Return 0 if no axes
    if not axes:
        return 0

    # Create axis_name -> axis_id mapping
    axis_map = {axis_name: axis_id for axis_id, axis_name in axes}

    count = 0
    for variant_id, properties_json in variants:
        # Parse the properties JSON string
        try:
            properties = json.loads(properties_json)
        except (json.JSONDecodeError, TypeError):
            # Skip if properties is malformed
            continue

        # Insert dimension value for each axis
        for axis_name, axis_id in axis_map.items():
            # Get the variant's value for this axis
            value = properties.get(axis_name)

            # Skip if variant doesn't have a value for this axis
            if value is None:
                continue

            # UPSERT the dimension value
            cursor.execute("""
                INSERT INTO variant_dimension_values (variant_id, axis_id, value)
                VALUES (?, ?, ?)
                ON CONFLICT(variant_id, axis_id) DO UPDATE SET
                    value = excluded.value
            """, (variant_id, axis_id, value))

            count += 1

    # Commit after all inserts
    conn.commit()

    return count


def extract_components(conn: sqlite3.Connection, file_id: int, component_nodes: List[Dict[str, Any]]) -> List[int]:
    """
    Process a list of component/component_set nodes from Figma.

    Args:
        conn: Database connection
        file_id: ID of the file these components belong to
        component_nodes: List of raw component/component_set nodes from Figma

    Returns:
        List of component IDs inserted
    """
    component_ids = []

    for node in component_nodes:
        node_type = node.get("type")

        if node_type == "COMPONENT_SET":
            # Parse as component set
            parsed = parse_component_set(node)
        elif node_type == "COMPONENT":
            # Parse as standalone component
            parsed = parse_standalone_component(node)
        else:
            # Skip non-component nodes
            continue

        # Insert component
        component_id = insert_component(conn, file_id, parsed)
        component_ids.append(component_id)

        # Insert variants if any
        if parsed["variants"]:
            insert_variants(conn, component_id, parsed["variants"])

        # Insert axes if any
        if parsed["axes"]:
            insert_variant_axes(conn, component_id, parsed["axes"])

        # Populate variant dimension values
        populate_variant_dimension_values(conn, component_id)

        # Extract and insert slots if children data is available
        if parsed.get("children"):
            # Transform Figma children data to our format
            children_for_slots = []
            for idx, child in enumerate(parsed["children"]):
                children_for_slots.append({
                    "name": child.get("name", ""),
                    "node_type": child.get("type", ""),
                    "sort_order": idx,
                    "text_content": child.get("characters") if child.get("type") == "TEXT" else None
                })

            if children_for_slots:
                slots = infer_slots(children_for_slots)
                if slots:
                    insert_slots(conn, component_id, slots)

    # Commit all changes
    conn.commit()

    return component_ids