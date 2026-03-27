"""Screen extraction script generator for Figma node trees."""

import json
from typing import Any, Dict, List, Optional

from dd.config import USE_FIGMA_CODE_LIMIT
from dd.types import NON_SEMANTIC_PREFIXES, SEMANTIC_NODE_TYPES


def generate_extraction_script(screen_node_id: str) -> str:
    """
    Generate JavaScript code to extract a screen's node tree via use_figma.

    Args:
        screen_node_id: The Figma node ID of the screen to extract

    Returns:
        Self-contained JavaScript string that extracts the node tree
    """
    script = '''function extractScreen(screenId) {
  const screen = figma.getNodeById(screenId);
  const nodes = [];

  function walk(node, parentIdx, depth) {
    const entry = {
      figma_node_id: node.id,
      parent_idx: parentIdx,
      name: node.name,
      node_type: node.type,
      depth: depth,
      sort_order: node.parent?.children?.indexOf(node) ?? 0,
      x: node.x, y: node.y,
      width: node.width, height: node.height,
    };

    // Visual properties
    if ('fills' in node) entry.fills = JSON.stringify(node.fills);
    if ('strokes' in node) entry.strokes = JSON.stringify(node.strokes);
    if ('effects' in node) entry.effects = JSON.stringify(node.effects);

    // Handle cornerRadius - can be number or mixed
    if ('cornerRadius' in node) {
      if (node.cornerRadius === figma.mixed) {
        entry.corner_radius = JSON.stringify({
          tl: node.topLeftRadius || 0,
          tr: node.topRightRadius || 0,
          bl: node.bottomLeftRadius || 0,
          br: node.bottomRightRadius || 0
        });
      } else {
        entry.corner_radius = node.cornerRadius;
      }
    }

    if ('opacity' in node) entry.opacity = node.opacity;
    if ('blendMode' in node) entry.blend_mode = node.blendMode;
    if ('visible' in node) entry.visible = node.visible;

    // Stroke properties
    if ('strokeWeight' in node) {
      if (node.strokeWeight === figma.mixed) {
        entry.stroke_top_weight = node.strokeTopWeight;
        entry.stroke_right_weight = node.strokeRightWeight;
        entry.stroke_bottom_weight = node.strokeBottomWeight;
        entry.stroke_left_weight = node.strokeLeftWeight;
      } else {
        entry.stroke_weight = node.strokeWeight;
      }
    }
    if ('strokeAlign' in node) entry.stroke_align = node.strokeAlign;
    if ('strokeCap' in node && node.strokeCap !== figma.mixed) entry.stroke_cap = node.strokeCap;
    if ('strokeJoin' in node && node.strokeJoin !== figma.mixed) entry.stroke_join = node.strokeJoin;
    if ('dashPattern' in node && node.dashPattern?.length) entry.dash_pattern = JSON.stringify(node.dashPattern);

    // Transform + clipping
    if ('rotation' in node && node.rotation !== 0) entry.rotation = node.rotation;
    if ('clipsContent' in node) entry.clips_content = node.clipsContent ? 1 : 0;

    // Constraints
    if ('constraints' in node) {
      entry.constraint_h = node.constraints?.horizontal;
      entry.constraint_v = node.constraints?.vertical;
    }

    // Auto-layout
    if (node.layoutMode && node.layoutMode !== 'NONE') {
      entry.layout_mode = node.layoutMode;
      entry.padding_top = node.paddingTop;
      entry.padding_right = node.paddingRight;
      entry.padding_bottom = node.paddingBottom;
      entry.padding_left = node.paddingLeft;
      entry.item_spacing = node.itemSpacing;
      entry.counter_axis_spacing = node.counterAxisSpacing;
      entry.primary_align = node.primaryAxisAlignItems;
      entry.counter_align = node.counterAxisAlignItems;
      entry.layout_sizing_h = node.layoutSizingHorizontal;
      entry.layout_sizing_v = node.layoutSizingVertical;
      if ('layoutWrap' in node) entry.layout_wrap = node.layoutWrap;
      if ('minWidth' in node) entry.min_width = node.minWidth;
      if ('maxWidth' in node) entry.max_width = node.maxWidth;
      if ('minHeight' in node) entry.min_height = node.minHeight;
      if ('maxHeight' in node) entry.max_height = node.maxHeight;
    }

    // Typography (TEXT nodes)
    if (node.type === 'TEXT') {
      entry.font_family = node.fontName?.family;
      entry.font_style = node.fontName?.style;
      entry.font_weight = node.fontWeight;
      entry.font_size = node.fontSize;
      entry.line_height = JSON.stringify(node.lineHeight);
      entry.letter_spacing = JSON.stringify(node.letterSpacing);
      if ('paragraphSpacing' in node) entry.paragraph_spacing = node.paragraphSpacing;
      entry.text_align = node.textAlignHorizontal;
      if ('textAlignVertical' in node) entry.text_align_v = node.textAlignVertical;
      if ('textDecoration' in node && node.textDecoration !== figma.mixed) entry.text_decoration = node.textDecoration;
      if ('textCase' in node && node.textCase !== figma.mixed) entry.text_case = node.textCase;
      entry.text_content = node.characters;
    }

    // Component reference (INSTANCE nodes)
    if (node.type === 'INSTANCE' && node.mainComponent) {
      entry.component_figma_id = node.mainComponent.id;
      entry.component_key = node.mainComponent.key;
    }

    const idx = nodes.length;
    nodes.push(entry);

    if ('children' in node) {
      node.children.forEach(child => walk(child, idx, depth + 1));
    }
  }

  walk(screen, null, 0);
  return nodes;
}

return extractScreen("''' + screen_node_id + '''");'''

    if len(script) > USE_FIGMA_CODE_LIMIT:
        raise ValueError(f"Generated script exceeds {USE_FIGMA_CODE_LIMIT} character limit")

    return script


def parse_extraction_response(response: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parse and normalize the raw response from use_figma.

    Args:
        response: List of node dicts from the extraction script

    Returns:
        Cleaned list of dicts ready for DB insertion
    """
    parsed = []

    for node in response:
        # Validate required fields
        if "figma_node_id" not in node:
            raise ValueError("Missing required field: figma_node_id")
        if "name" not in node:
            raise ValueError("Missing required field: name")
        if "node_type" not in node:
            raise ValueError("Missing required field: node_type")

        # Create cleaned node dict
        cleaned = {
            "figma_node_id": node["figma_node_id"],
            "name": node["name"],
            "node_type": node["node_type"],
            "parent_idx": node.get("parent_idx"),
            "depth": int(node.get("depth", 0)),
            "sort_order": int(node.get("sort_order", 0)),
        }

        # Geometry - ensure float or None
        for field in ["x", "y", "width", "height"]:
            if field in node and node[field] is not None:
                cleaned[field] = float(node[field])
            else:
                cleaned[field] = None

        # Convert visible boolean to int
        if "visible" in node:
            cleaned["visible"] = 1 if node["visible"] else 0
        else:
            cleaned["visible"] = 1

        # Opacity
        if "opacity" in node:
            cleaned["opacity"] = float(node["opacity"])

        # Blend mode
        if "blend_mode" in node:
            cleaned["blend_mode"] = node["blend_mode"]

        # Visual properties - ensure JSON strings
        for field in ["fills", "strokes", "effects"]:
            if field in node:
                value = node[field]
                if isinstance(value, (list, dict)):
                    cleaned[field] = json.dumps(value)
                else:
                    cleaned[field] = value

        # Corner radius - can be number or object
        if "corner_radius" in node:
            value = node["corner_radius"]
            if isinstance(value, dict):
                cleaned["corner_radius"] = json.dumps(value)
            elif value is not None:
                cleaned["corner_radius"] = str(value)

        # Stroke properties
        for field in ["stroke_weight", "stroke_top_weight", "stroke_right_weight",
                      "stroke_bottom_weight", "stroke_left_weight"]:
            if field in node and node[field] is not None:
                cleaned[field] = float(node[field])
        for field in ["stroke_align", "stroke_cap", "stroke_join"]:
            if field in node:
                cleaned[field] = node[field]
        if "dash_pattern" in node:
            value = node["dash_pattern"]
            if isinstance(value, list):
                cleaned["dash_pattern"] = json.dumps(value)
            else:
                cleaned["dash_pattern"] = value

        # Transform + clipping
        if "rotation" in node and node["rotation"] is not None:
            cleaned["rotation"] = float(node["rotation"])
        if "clips_content" in node:
            cleaned["clips_content"] = 1 if node["clips_content"] else 0

        # Constraints
        for field in ["constraint_h", "constraint_v"]:
            if field in node:
                cleaned[field] = node[field]

        # Auto-layout properties
        if "layout_mode" in node:
            cleaned["layout_mode"] = node["layout_mode"]
            for field in ["padding_top", "padding_right", "padding_bottom", "padding_left",
                          "item_spacing", "counter_axis_spacing",
                          "min_width", "max_width", "min_height", "max_height"]:
                if field in node:
                    cleaned[field] = float(node[field]) if node[field] is not None else None
            for field in ["primary_align", "counter_align", "layout_sizing_h", "layout_sizing_v",
                          "layout_wrap"]:
                if field in node:
                    cleaned[field] = node[field]

        # Typography properties
        if node.get("node_type") == "TEXT":
            for field in ["font_family", "font_style", "text_align", "text_align_v",
                          "text_decoration", "text_case", "text_content"]:
                if field in node:
                    cleaned[field] = node[field]
            if "font_weight" in node:
                cleaned["font_weight"] = int(node["font_weight"]) if node["font_weight"] is not None else None
            if "font_size" in node:
                cleaned["font_size"] = float(node["font_size"]) if node["font_size"] is not None else None
            if "paragraph_spacing" in node and node["paragraph_spacing"] is not None:
                cleaned["paragraph_spacing"] = float(node["paragraph_spacing"])

            # Line height and letter spacing - ensure JSON strings
            for field in ["line_height", "letter_spacing"]:
                if field in node:
                    value = node[field]
                    if isinstance(value, dict):
                        cleaned[field] = json.dumps(value)
                    else:
                        cleaned[field] = value

        # Component reference
        if "component_figma_id" in node:
            cleaned["component_figma_id"] = node["component_figma_id"]
        if "component_key" in node:
            cleaned["component_key"] = node["component_key"]

        parsed.append(cleaned)

    return parsed


def compute_is_semantic(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Compute the is_semantic flag for each node based on TDS rules.

    Args:
        nodes: List of parsed node dicts with parent_idx references

    Returns:
        Updated list with is_semantic field set on each node
    """
    # First pass: apply rules a, b, c
    for node in nodes:
        is_semantic = 0

        # Rule a: node_type in SEMANTIC_NODE_TYPES
        if node.get("node_type") in SEMANTIC_NODE_TYPES:
            is_semantic = 1

        # Rule b: FRAME with layout_mode
        elif node.get("node_type") == "FRAME" and node.get("layout_mode") is not None:
            is_semantic = 1

        # Rule c: name doesn't start with NON_SEMANTIC_PREFIXES
        elif not any(node.get("name", "").startswith(prefix) for prefix in NON_SEMANTIC_PREFIXES):
            is_semantic = 1

        node["is_semantic"] = is_semantic

    # Second pass: apply rule d (parent with 2+ children where 1+ is semantic)
    # Build parent-child relationships
    for i, node in enumerate(nodes):
        if node.get("parent_idx") is None:
            continue

        parent_idx = node["parent_idx"]
        if parent_idx < len(nodes):
            parent = nodes[parent_idx]
            if "child_indices" not in parent:
                parent["child_indices"] = []
            parent["child_indices"].append(i)

    # Apply rule d - work from leaves up (reversed order since walk is depth-first)
    for node in reversed(nodes):
        if node.get("is_semantic") == 1:
            continue  # Already semantic

        child_indices = node.get("child_indices", [])
        if len(child_indices) >= 2:
            # Check if at least one child is semantic
            has_semantic_child = any(nodes[idx]["is_semantic"] == 1 for idx in child_indices)
            if has_semantic_child:
                node["is_semantic"] = 1

    # Clean up temporary child_indices field
    for node in nodes:
        if "child_indices" in node:
            del node["child_indices"]

    return nodes


def insert_nodes(conn, screen_id: int, nodes: List[Dict[str, Any]]) -> List[int]:
    """
    Insert nodes into the database with parent_idx to parent_id mapping.

    Args:
        conn: SQLite database connection
        screen_id: ID of the screen these nodes belong to
        nodes: List of node dicts with parent_idx references

    Returns:
        List of inserted node database IDs
    """
    node_ids = []

    for node in nodes:
        # Map parent_idx to parent_id
        parent_id = None
        if node.get("parent_idx") is not None:
            parent_idx = node["parent_idx"]
            if parent_idx < len(node_ids):
                parent_id = node_ids[parent_idx]

        # Prepare values for insertion
        values = {
            "screen_id": screen_id,
            "figma_node_id": node["figma_node_id"],
            "parent_id": parent_id,
            "name": node["name"],
            "node_type": node["node_type"],
            "depth": node.get("depth", 0),
            "sort_order": node.get("sort_order", 0),
            "is_semantic": node.get("is_semantic", 0),
        }

        # Add optional fields
        optional_fields = [
            "x", "y", "width", "height",
            "layout_mode", "padding_top", "padding_right", "padding_bottom", "padding_left",
            "item_spacing", "counter_axis_spacing", "primary_align", "counter_align",
            "layout_sizing_h", "layout_sizing_v", "layout_wrap",
            "min_width", "max_width", "min_height", "max_height",
            "fills", "strokes", "effects", "corner_radius",
            "opacity", "blend_mode", "visible",
            "stroke_weight", "stroke_top_weight", "stroke_right_weight",
            "stroke_bottom_weight", "stroke_left_weight",
            "stroke_align", "stroke_cap", "stroke_join", "dash_pattern",
            "rotation", "clips_content",
            "constraint_h", "constraint_v",
            "font_family", "font_weight", "font_size", "font_style",
            "line_height", "letter_spacing", "paragraph_spacing",
            "text_align", "text_align_v", "text_decoration", "text_case", "text_content",
            "component_key",
        ]

        for field in optional_fields:
            if field in node:
                values[field] = node[field]

        # Build INSERT statement
        columns = list(values.keys())
        placeholders = ["?" for _ in columns]

        sql = f"""
            INSERT INTO nodes ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT(screen_id, figma_node_id) DO UPDATE SET
            {', '.join(f'{col} = excluded.{col}' for col in columns if col not in ['screen_id', 'figma_node_id'])}
            RETURNING id
        """

        cursor = conn.execute(sql, list(values.values()))
        node_id = cursor.fetchone()[0]
        node_ids.append(node_id)

    conn.commit()
    return node_ids


def update_screen_status(
    conn,
    run_id: int,
    screen_id: int,
    status: str,
    node_count: Optional[int] = None,
    binding_count: Optional[int] = None,
    error: Optional[str] = None
) -> None:
    """
    Update the extraction status for a screen in a run.

    Args:
        conn: SQLite database connection
        run_id: Extraction run ID
        screen_id: Screen ID
        status: New status (pending, in_progress, completed, failed, skipped)
        node_count: Number of nodes extracted (optional)
        binding_count: Number of bindings created (optional)
        error: Error message if failed (optional)
    """
    # Build update fields
    updates = ["status = ?"]
    values = [status]

    if status == "in_progress":
        updates.append("started_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")
    elif status in ["completed", "failed"]:
        updates.append("completed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")

    if node_count is not None:
        updates.append("node_count = ?")
        values.append(node_count)

    if binding_count is not None:
        updates.append("binding_count = ?")
        values.append(binding_count)

    if error is not None:
        updates.append("error = ?")
        values.append(error)

    # Add run_id and screen_id for WHERE clause
    values.extend([run_id, screen_id])

    sql = f"""
        UPDATE screen_extraction_status
        SET {', '.join(updates)}
        WHERE run_id = ? AND screen_id = ?
    """

    conn.execute(sql, values)
    conn.commit()