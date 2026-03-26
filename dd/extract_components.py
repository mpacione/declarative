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

    return {
        "figma_node_id": figma_node_id,
        "name": name,
        "description": description,
        "category": category,
        "variant_properties": json.dumps(variant_properties) if variant_properties else None,
        "variants": variants,
        "axes": axes
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

    return {
        "figma_node_id": figma_node_id,
        "name": name,
        "description": description,
        "category": category,
        "variant_properties": None,
        "variants": [],
        "axes": []
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

    # Commit all changes
    conn.commit()

    return component_ids