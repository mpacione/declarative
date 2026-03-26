"""Generate rebind scripts for Figma Plugin API to bind nodes to variables."""

import math
import sqlite3
from typing import Any

from dd.config import MAX_BINDINGS_PER_SCRIPT

PROPERTY_HANDLERS = {
    "fill.N.color": "paint",
    "stroke.N.color": "paint",
    "effect.N.color": "effect",
    "effect.N.radius": "effect",
    "effect.N.offsetX": "effect",
    "effect.N.offsetY": "effect",
    "effect.N.spread": "effect",
    "cornerRadius": "direct",
    "topLeftRadius": "direct",
    "topRightRadius": "direct",
    "bottomLeftRadius": "direct",
    "bottomRightRadius": "direct",
    "padding.top": "padding",
    "padding.right": "padding",
    "padding.bottom": "padding",
    "padding.left": "padding",
    "itemSpacing": "direct",
    "counterAxisSpacing": "direct",
    "opacity": "direct",
    "strokeWeight": "direct",
    "strokeTopWeight": "direct",
    "strokeRightWeight": "direct",
    "strokeBottomWeight": "direct",
    "strokeLeftWeight": "direct",
    "fontSize": "direct",
    "fontFamily": "direct",
    "fontWeight": "direct",
    "fontStyle": "direct",
    "lineHeight": "direct",
    "letterSpacing": "direct",
    "paragraphSpacing": "direct",
}


def classify_property(property_path: str) -> str:
    """
    Determine the handler category for a given property path.

    Args:
        property_path: The property path (e.g., 'fill.0.color', 'fontSize')

    Returns:
        Handler category: 'paint_fill', 'paint_stroke', 'effect', 'padding', 'direct', or 'unknown'
    """
    if property_path.startswith("fill.") and property_path.endswith(".color"):
        return "paint_fill"
    if property_path.startswith("stroke.") and property_path.endswith(".color"):
        return "paint_stroke"
    if property_path.startswith("effect."):
        return "effect"
    if property_path.startswith("padding."):
        return "padding"

    # Check direct bind properties
    direct_properties = {
        "cornerRadius", "itemSpacing", "opacity", "fontSize", "fontFamily",
        "fontWeight", "fontStyle", "lineHeight", "letterSpacing", "paragraphSpacing",
        "counterAxisSpacing", "strokeWeight", "topLeftRadius", "topRightRadius",
        "bottomLeftRadius", "bottomRightRadius", "strokeTopWeight", "strokeRightWeight",
        "strokeBottomWeight", "strokeLeftWeight"
    }
    if property_path in direct_properties:
        return "direct"

    return "unknown"


def query_bindable_entries(conn: sqlite3.Connection, file_id: int) -> list[dict[str, Any]]:
    """
    Query bindings that can be rebound in Figma.

    Args:
        conn: Database connection
        file_id: File ID to query bindings for

    Returns:
        List of dicts with keys: binding_id, node_id, property, variable_id
    """
    query = """
        SELECT ntb.id AS binding_id,
               n.figma_node_id AS node_id,
               ntb.property,
               t.figma_variable_id AS variable_id
        FROM node_token_bindings ntb
        JOIN nodes n ON ntb.node_id = n.id
        JOIN screens s ON n.screen_id = s.id
        JOIN tokens t ON ntb.token_id = t.id
        WHERE s.file_id = ?
          AND ntb.binding_status = 'bound'
          AND t.figma_variable_id IS NOT NULL
        ORDER BY s.id, n.id, ntb.property
    """

    cursor = conn.execute(query, (file_id,))
    entries = []

    for row in cursor:
        # Filter out unknown property types
        if classify_property(row["property"]) != "unknown":
            entries.append({
                "binding_id": row["binding_id"],
                "node_id": row["node_id"],
                "property": row["property"],
                "variable_id": row["variable_id"],
            })

    return entries


def generate_single_script(entries: list[dict[str, Any]]) -> str:
    """
    Generate a self-contained async IIFE JavaScript string for rebinding.

    Args:
        entries: List of binding entry dicts (up to MAX_BINDINGS_PER_SCRIPT)

    Returns:
        JavaScript string for rebinding
    """
    # Build bindings array
    if not entries:
        bindings_js = "[]"
    else:
        bindings_js = "[\n"
        for entry in entries:
            bindings_js += f'    {{ nodeId: "{entry["node_id"]}", property: "{entry["property"]}", variableId: "{entry["variable_id"]}" }},\n'
        bindings_js = bindings_js.rstrip(",\n") + "\n  ]"

    script = f"""(async () => {{
  const bindings = {bindings_js};

  let bound = 0, failed = 0;

  for (const b of bindings) {{
    try {{
      const node = await figma.getNodeByIdAsync(b.nodeId);
      if (!node) {{ failed++; continue; }}

      const variable = await figma.variables.getVariableByIdAsync(b.variableId);
      if (!variable) {{ failed++; continue; }}

      // --- Paint bindings (fills, strokes) ---
      if (b.property.startsWith('fill.') && b.property.endsWith('.color')) {{
        const idx = parseInt(b.property.split('.')[1]);
        const fills = [...node.fills];
        fills[idx] = figma.variables.setBoundVariableForPaint(fills[idx], 'color', variable);
        node.fills = fills;

      }} else if (b.property.startsWith('stroke.') && b.property.endsWith('.color')) {{
        const idx = parseInt(b.property.split('.')[1]);
        const strokes = [...node.strokes];
        strokes[idx] = figma.variables.setBoundVariableForPaint(strokes[idx], 'color', variable);
        node.strokes = strokes;

      }} else if (b.property.startsWith('effect.')) {{
        const parts = b.property.split('.');
        const idx = parseInt(parts[1]);
        const field = parts[2];
        const effects = [...node.effects];
        effects[idx] = figma.variables.setBoundVariableForEffect(effects[idx], field, variable);
        node.effects = effects;

      }} else if (['cornerRadius','topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius',
                   'itemSpacing','counterAxisSpacing','opacity','strokeWeight',
                   'strokeTopWeight','strokeRightWeight','strokeBottomWeight','strokeLeftWeight'].includes(b.property)) {{
        node.setBoundVariable(b.property, variable);

      }} else if (b.property.startsWith('padding.')) {{
        const side = b.property.split('.')[1];
        const prop = 'padding' + side.charAt(0).toUpperCase() + side.slice(1);
        node.setBoundVariable(prop, variable);

      }} else if (['fontSize','fontFamily','fontWeight','fontStyle','lineHeight',
                   'letterSpacing','paragraphSpacing'].includes(b.property)) {{
        node.setBoundVariable(b.property, variable);

      }} else {{
        console.warn(`Unhandled property: ${{b.property}} on node ${{b.nodeId}}`);
        failed++;
        continue;
      }}
      bound++;
    }} catch (e) {{
      console.error(`Failed: ${{b.nodeId}} ${{b.property}}: ${{e.message}}`);
      failed++;
    }}
  }}

  figma.notify(`Rebound ${{bound}}/${{bindings.length}} properties (${{failed}} failures)`);
}})();"""

    return script


def generate_rebind_scripts(conn: sqlite3.Connection, file_id: int) -> list[str]:
    """
    Generate rebind scripts for all bindable entries in a file.

    Args:
        conn: Database connection
        file_id: File ID to generate scripts for

    Returns:
        List of JavaScript strings, each up to MAX_BINDINGS_PER_SCRIPT bindings
    """
    entries = query_bindable_entries(conn, file_id)

    if not entries:
        return []

    scripts = []
    for i in range(0, len(entries), MAX_BINDINGS_PER_SCRIPT):
        batch = entries[i:i + MAX_BINDINGS_PER_SCRIPT]
        scripts.append(generate_single_script(batch))

    return scripts


def get_rebind_summary(conn: sqlite3.Connection, file_id: int) -> dict[str, Any]:
    """
    Compute summary statistics for rebinding without generating scripts.

    Args:
        conn: Database connection
        file_id: File ID to summarize

    Returns:
        Dictionary with summary statistics
    """
    # Get all bound bindings with figma_variable_id
    query = """
        SELECT ntb.property
        FROM node_token_bindings ntb
        JOIN nodes n ON ntb.node_id = n.id
        JOIN screens s ON n.screen_id = s.id
        JOIN tokens t ON ntb.token_id = t.id
        WHERE s.file_id = ?
          AND ntb.binding_status = 'bound'
          AND t.figma_variable_id IS NOT NULL
        ORDER BY s.id, n.id, ntb.property
    """

    cursor = conn.execute(query, (file_id,))

    total_bindings = 0
    unbindable = 0
    by_property_type = {}

    for row in cursor:
        property_type = classify_property(row["property"])
        if property_type == "unknown":
            unbindable += 1
        else:
            total_bindings += 1
            by_property_type[property_type] = by_property_type.get(property_type, 0) + 1

    script_count = math.ceil(total_bindings / MAX_BINDINGS_PER_SCRIPT) if total_bindings > 0 else 0

    return {
        "total_bindings": total_bindings,
        "script_count": script_count,
        "by_property_type": by_property_type,
        "unbindable": unbindable,
    }