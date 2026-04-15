"""Screen extraction script generator for Figma node trees."""

from __future__ import annotations

import json
from typing import Any

from dd.config import USE_FIGMA_CODE_LIMIT
from dd.property_registry import PROPERTIES
from dd.types import NON_SEMANTIC_PREFIXES, SEMANTIC_NODE_TYPES


# ---------------------------------------------------------------------------
# Registry-driven forwarding lists
#
# These lists used to be hand-rolled. Adding a new property to the registry
# (e.g. `leading_trim`) didn't extend them, so the new column silently
# dropped between extraction and DB insert. Deriving them from the registry
# means a new FigmaProperty with a db_column automatically extends both
# forwards without hand-edits.
#
# See feedback_extract_whitelist_drift.md for the incident that motivated
# this. Structural test: tests/test_extraction.py::TestExtractWhitelistsAreRegistryDriven.
# ---------------------------------------------------------------------------

# Text-category columns forwarded by parse_extraction_response as plain
# strings (no type coercion). Numeric/json-array text columns (font_size,
# font_weight, line_height, letter_spacing, paragraph_spacing) are handled
# separately in the parser because they need float/int/json coercion.
_TEXT_COERCED: frozenset[str] = frozenset({
    "font_size", "font_weight", "line_height",
    "letter_spacing", "paragraph_spacing",
})

TEXT_PASSTHROUGH_COLUMNS: tuple[str, ...] = tuple(
    p.db_column for p in PROPERTIES
    if p.category == "text" and p.db_column and p.db_column not in _TEXT_COERCED
)

# Columns not in the registry but still forwarded into the nodes table by
# insert_nodes. Structural (position, grid, geometry, per-side stroke, FK).
# These are legitimately outside the registry's scope today; if the registry
# grows to cover them, move them to the derived list.
_STRUCTURAL_INSERT_COLUMNS: tuple[str, ...] = (
    "x", "y",
    "grid_row_count", "grid_column_count",
    "grid_row_gap", "grid_column_gap",
    "grid_row_sizes", "grid_column_sizes",
    "fill_geometry", "stroke_geometry",
    "stroke_top_weight", "stroke_right_weight",
    "stroke_bottom_weight", "stroke_left_weight",
    "component_key",
)

# Every column insert_nodes forwards into the SQL INSERT statement. Tested
# by TestExtractWhitelistsAreRegistryDriven.
INSERT_NODE_COLUMNS: tuple[str, ...] = tuple(
    dict.fromkeys([
        # Size + layout (width, height, padding, etc.) come from the
        # registry's size / layout / constraint categories. Visual columns
        # (fills, strokes, effects, corner_radius, etc.) from 'visual'.
        # Text columns handled below.
        *(p.db_column for p in PROPERTIES if p.db_column),
        *_STRUCTURAL_INSERT_COLUMNS,
    ])
)


def generate_extraction_script(screen_node_id: str) -> str:
    """
    Generate JavaScript code to extract a screen's node tree via use_figma.

    Args:
        screen_node_id: The Figma node ID of the screen to extract

    Returns:
        Self-contained JavaScript string that extracts the node tree
    """
    script = '''async function extractScreen(screenId) {
  const screen = await figma.getNodeByIdAsync(screenId);
  const nodes = [];

  // Safe property reader: handles non-enumerable props, prototype getters,
  // and properties that throw on wrong node types. Returns undefined on miss.
  function safeRead(node, prop) {
    try { const v = node[prop]; return v === undefined ? undefined : v; }
    catch(e) { return undefined; }
  }

  // safeRead with figma.mixed check — returns undefined if mixed.
  function safeReadNoMixed(node, prop) {
    const v = safeRead(node, prop);
    return v === figma.mixed ? undefined : v;
  }

  async function walk(node, parentIdx, depth) {
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
    const fills = safeRead(node, 'fills');
    if (fills !== undefined) entry.fills = JSON.stringify(fills);
    const strokes = safeRead(node, 'strokes');
    if (strokes !== undefined) entry.strokes = JSON.stringify(strokes);
    const effects = safeRead(node, 'effects');
    if (effects !== undefined) entry.effects = JSON.stringify(effects);

    // Handle cornerRadius - can be number or mixed
    const cr = safeRead(node, 'cornerRadius');
    if (cr !== undefined) {
      if (cr === figma.mixed) {
        entry.corner_radius = JSON.stringify({
          tl: node.topLeftRadius || 0,
          tr: node.topRightRadius || 0,
          bl: node.bottomLeftRadius || 0,
          br: node.bottomRightRadius || 0
        });
      } else {
        entry.corner_radius = cr;
      }
    }

    const opacity = safeRead(node, 'opacity');
    if (opacity !== undefined) entry.opacity = opacity;
    const blendMode = safeRead(node, 'blendMode');
    if (blendMode !== undefined) entry.blend_mode = blendMode;
    const visible = safeRead(node, 'visible');
    if (visible !== undefined) entry.visible = visible;

    // Stroke properties
    const sw = safeRead(node, 'strokeWeight');
    if (sw !== undefined) {
      if (sw === figma.mixed) {
        entry.stroke_top_weight = node.strokeTopWeight;
        entry.stroke_right_weight = node.strokeRightWeight;
        entry.stroke_bottom_weight = node.strokeBottomWeight;
        entry.stroke_left_weight = node.strokeLeftWeight;
      } else {
        entry.stroke_weight = sw;
      }
    }
    const sa = safeRead(node, 'strokeAlign');
    if (sa !== undefined) entry.stroke_align = sa;
    const sc = safeReadNoMixed(node, 'strokeCap');
    if (sc !== undefined) entry.stroke_cap = sc;
    const sj = safeReadNoMixed(node, 'strokeJoin');
    if (sj !== undefined) entry.stroke_join = sj;
    const dp = safeRead(node, 'dashPattern');
    if (dp?.length) entry.dash_pattern = JSON.stringify(dp);

    // Vector geometry (VECTOR, BOOLEAN_OPERATION, ELLIPSE, LINE, etc.)
    const fg = safeRead(node, 'fillGeometry');
    if (fg?.length) entry.fill_geometry = JSON.stringify(fg);
    const sg = safeRead(node, 'strokeGeometry');
    if (sg?.length) entry.stroke_geometry = JSON.stringify(sg);
    const bo = safeRead(node, 'booleanOperation');
    if (bo !== undefined) entry.boolean_operation = bo;

    // Corner smoothing (iOS-style smooth corners)
    const cs = safeRead(node, 'cornerSmoothing');
    if (cs !== undefined && cs > 0) entry.corner_smoothing = cs;

    // Arc data (partial arcs on ELLIPSE nodes)
    const ad = safeRead(node, 'arcData');
    if (ad !== undefined) entry.arc_data = JSON.stringify(ad);

    // Transform + clipping
    const rot = safeRead(node, 'rotation');
    if (rot !== undefined && rot !== 0) entry.rotation = rot;
    const cc = safeRead(node, 'clipsContent');
    if (cc !== undefined) entry.clips_content = cc ? 1 : 0;

    // Mask
    const im = safeRead(node, 'isMask');
    if (im) entry.is_mask = 1;

    // Constraints
    const constraints = safeRead(node, 'constraints');
    if (constraints) {
      entry.constraint_h = constraints.horizontal;
      entry.constraint_v = constraints.vertical;
    }

    // Child positioning within auto-layout parent
    const lp = safeRead(node, 'layoutPositioning');
    if (lp !== undefined) entry.layout_positioning = lp;

    // Layout sizing: read for ALL nodes (auto-layout children, text nodes, etc.)
    const lsh = safeRead(node, 'layoutSizingHorizontal');
    if (lsh !== undefined) entry.layout_sizing_h = lsh;
    const lsv = safeRead(node, 'layoutSizingVertical');
    if (lsv !== undefined) entry.layout_sizing_v = lsv;

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
      const lw = safeRead(node, 'layoutWrap');
      if (lw !== undefined) entry.layout_wrap = lw;
      const miw = safeRead(node, 'minWidth');
      if (miw !== undefined) entry.min_width = miw;
      const maw = safeRead(node, 'maxWidth');
      if (maw !== undefined) entry.max_width = maw;
      const mih = safeRead(node, 'minHeight');
      if (mih !== undefined) entry.min_height = mih;
      const mah = safeRead(node, 'maxHeight');
      if (mah !== undefined) entry.max_height = mah;

      // Grid layout properties (layoutMode === 'GRID')
      if (node.layoutMode === 'GRID') {
        const grc = safeRead(node, 'gridRowCount');
        if (grc !== undefined) entry.grid_row_count = grc;
        const gcc = safeRead(node, 'gridColumnCount');
        if (gcc !== undefined) entry.grid_column_count = gcc;
        const grg = safeRead(node, 'gridRowGap');
        if (grg !== undefined) entry.grid_row_gap = grg;
        const gcg = safeRead(node, 'gridColumnGap');
        if (gcg !== undefined) entry.grid_column_gap = gcg;
        const grs = safeRead(node, 'gridRowSizes');
        if (grs !== undefined) entry.grid_row_sizes = JSON.stringify(grs);
        const gcs = safeRead(node, 'gridColumnSizes');
        if (gcs !== undefined) entry.grid_column_sizes = JSON.stringify(gcs);
      }
    }

    // Typography (TEXT nodes)
    if (node.type === 'TEXT') {
      const fn = safeRead(node, 'fontName');
      if (fn && fn !== figma.mixed) {
        entry.font_family = fn.family;
        entry.font_style = fn.style;
      }
      const fw = safeReadNoMixed(node, 'fontWeight');
      if (fw !== undefined) entry.font_weight = fw;
      const fs = safeReadNoMixed(node, 'fontSize');
      if (fs !== undefined) entry.font_size = fs;
      const lh = safeRead(node, 'lineHeight');
      if (lh !== undefined) entry.line_height = JSON.stringify(lh);
      const ls = safeRead(node, 'letterSpacing');
      if (ls !== undefined) entry.letter_spacing = JSON.stringify(ls);
      const ps = safeRead(node, 'paragraphSpacing');
      if (ps !== undefined) entry.paragraph_spacing = ps;
      const tah = safeRead(node, 'textAlignHorizontal');
      if (tah !== undefined) entry.text_align = tah;
      const tav = safeRead(node, 'textAlignVertical');
      if (tav !== undefined) entry.text_align_v = tav;
      const td = safeReadNoMixed(node, 'textDecoration');
      if (td !== undefined) entry.text_decoration = td;
      const tc = safeReadNoMixed(node, 'textCase');
      if (tc !== undefined) entry.text_case = tc;
      entry.text_content = node.characters;
      const tar = safeRead(node, 'textAutoResize');
      if (tar !== undefined) entry.text_auto_resize = tar;
    }

    // Component reference (INSTANCE nodes)
    if (node.type === 'INSTANCE') {
      try {
        const main = await node.getMainComponentAsync();
        if (main) {
          entry.component_figma_id = main.id;
          entry.component_key = main.key;
        }
      } catch (e) {}
    }

    const idx = nodes.length;
    nodes.push(entry);

    if ('children' in node) {
      for (const child of node.children) {
        await walk(child, idx, depth + 1);
      }
    }
  }

  await walk(screen, null, 0);
  return nodes;
}

return await extractScreen("''' + screen_node_id + '''");'''

    if len(script) > USE_FIGMA_CODE_LIMIT:
        raise ValueError(f"Generated script exceeds {USE_FIGMA_CODE_LIMIT} character limit")

    return script


def parse_extraction_response(response: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

        # Vector geometry
        for field in ["fill_geometry", "stroke_geometry"]:
            if field in node:
                value = node[field]
                if isinstance(value, (list, dict)):
                    cleaned[field] = json.dumps(value)
                else:
                    cleaned[field] = value

        # Boolean operation type
        if "boolean_operation" in node:
            cleaned["boolean_operation"] = node["boolean_operation"]

        # Corner smoothing
        if "corner_smoothing" in node and node["corner_smoothing"] is not None:
            cleaned["corner_smoothing"] = float(node["corner_smoothing"])

        # Arc data
        if "arc_data" in node:
            value = node["arc_data"]
            if isinstance(value, dict):
                cleaned["arc_data"] = json.dumps(value)
            else:
                cleaned["arc_data"] = value

        # Transform + clipping
        if "rotation" in node and node["rotation"] is not None:
            cleaned["rotation"] = float(node["rotation"])
        if "clips_content" in node:
            cleaned["clips_content"] = 1 if node["clips_content"] else 0

        # Mask
        if "is_mask" in node and node["is_mask"]:
            cleaned["is_mask"] = 1

        # Constraints
        for field in ["constraint_h", "constraint_v"]:
            if field in node:
                cleaned[field] = node[field]

        # Child positioning within auto-layout parent
        if "layout_positioning" in node:
            cleaned["layout_positioning"] = node["layout_positioning"]

        # Layout sizing: how this node sizes within its PARENT's layout context.
        # Valid on any node inside an auto-layout parent, not just containers.
        for field in ["layout_sizing_h", "layout_sizing_v"]:
            if field in node:
                cleaned[field] = node[field]

        # Auto-layout properties (container-level)
        if "layout_mode" in node:
            cleaned["layout_mode"] = node["layout_mode"]
            for field in ["padding_top", "padding_right", "padding_bottom", "padding_left",
                          "item_spacing", "counter_axis_spacing",
                          "min_width", "max_width", "min_height", "max_height"]:
                if field in node:
                    cleaned[field] = float(node[field]) if node[field] is not None else None
            for field in ["primary_align", "counter_align",
                          "layout_wrap"]:
                if field in node:
                    cleaned[field] = node[field]

            # Grid layout properties
            for field in ["grid_row_count", "grid_column_count"]:
                if field in node and node[field] is not None:
                    cleaned[field] = int(node[field])
            for field in ["grid_row_gap", "grid_column_gap"]:
                if field in node and node[field] is not None:
                    cleaned[field] = float(node[field])
            for field in ["grid_row_sizes", "grid_column_sizes"]:
                if field in node:
                    value = node[field]
                    if isinstance(value, list):
                        cleaned[field] = json.dumps(value)
                    else:
                        cleaned[field] = value

        # Typography properties. Derived from the property registry's
        # `text` category so a new text-column property (e.g.
        # leading_trim) auto-propagates. Columns that need type coercion
        # (font_size, font_weight, line_height, etc.) are handled
        # separately below.
        if node.get("node_type") == "TEXT":
            for field in TEXT_PASSTHROUGH_COLUMNS:
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


def compute_is_semantic(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        if node.get("node_type") in SEMANTIC_NODE_TYPES or (node.get("node_type") == "FRAME" and node.get("layout_mode") is not None) or not any(node.get("name", "").startswith(prefix) for prefix in NON_SEMANTIC_PREFIXES):
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


def insert_nodes(conn, screen_id: int, nodes: list[dict[str, Any]]) -> list[int]:
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

        # Add optional fields. Derived from INSERT_NODE_COLUMNS at module
        # scope (registry-driven + _STRUCTURAL_INSERT_COLUMNS). A new
        # registry property with a db_column is auto-forwarded; only
        # explicitly structural columns (x/y/grid/geometry/FK) need
        # hand-listing in _STRUCTURAL_INSERT_COLUMNS.
        for field in INSERT_NODE_COLUMNS:
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
    node_count: int | None = None,
    binding_count: int | None = None,
    error: str | None = None
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