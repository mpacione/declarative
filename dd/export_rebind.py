"""Generate rebind scripts for Figma Plugin API to bind nodes to variables."""

import math
import sqlite3
from typing import Any

from dd.config import MAX_BINDINGS_PER_SCRIPT

PROPERTY_SHORTCODES: dict[str, str] = {
    "cornerRadius": "cr",
    "topLeftRadius": "tlr",
    "topRightRadius": "trr",
    "bottomLeftRadius": "blr",
    "bottomRightRadius": "brr",
    "padding.top": "pt",
    "padding.right": "pr",
    "padding.bottom": "pb",
    "padding.left": "pl",
    "itemSpacing": "is",
    "counterAxisSpacing": "cas",
    "opacity": "op",
    "strokeWeight": "sw",
    "strokeTopWeight": "stw",
    "strokeRightWeight": "srw",
    "strokeBottomWeight": "sbw",
    "strokeLeftWeight": "slw",
    "fontSize": "fs",
    "fontFamily": "ff",
    "fontWeight": "fw",
    "fontStyle": "fst",
    "lineHeight": "lh",
    "letterSpacing": "ls",
    "paragraphSpacing": "ps",
}

EFFECT_FIELD_CODES: dict[str, str] = {
    "color": "c",
    "radius": "r",
    "offsetX": "x",
    "offsetY": "y",
    "spread": "s",
}


def encode_property(property_path: str) -> str | None:
    """
    Encode a property path to a compact shortcode.

    Returns None for unknown properties.
    """
    if property_path in PROPERTY_SHORTCODES:
        return PROPERTY_SHORTCODES[property_path]

    if property_path.startswith("fill.") and property_path.endswith(".color"):
        idx = property_path.split(".")[1]
        return f"f{idx}"

    if property_path.startswith("stroke.") and property_path.endswith(".color"):
        idx = property_path.split(".")[1]
        return f"s{idx}"

    if property_path.startswith("effect."):
        parts = property_path.split(".")
        idx = parts[1]
        field = parts[2]
        field_code = EFFECT_FIELD_CODES.get(field)
        if field_code:
            return f"e{idx}{field_code}"

    return None


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


COMPACT_HANDLER = r"""const R=D.split('\n').filter(l=>l);let b=0,f=0;const E=[];
const prev=figma.root.getPluginData('rebind_errors');const errs=prev?JSON.parse(prev):[];
for(const l of R){const[n,p,v]=l.split('|');try{
const nd=await figma.getNodeByIdAsync(n);if(!nd){f++;E.push({n,p,r:'NODE_NOT_FOUND'});continue;}
const vr=await figma.variables.getVariableByIdAsync('VariableID:'+v);if(!vr){f++;E.push({n,p,r:'VAR_NOT_FOUND'});continue;}
if(p[0]==='f'&&p.length<=2&&!isNaN(p[1])){const i=+p[1],fl=[...nd.fills];const origOp=fl[i].opacity;fl[i]=figma.variables.setBoundVariableForPaint(fl[i],'color',vr);fl[i]={...fl[i],opacity:origOp};nd.fills=fl;}
else if(p[0]==='s'&&p.length<=2&&!isNaN(p[1])){const i=+p[1],st=[...nd.strokes];const origOp=st[i].opacity;st[i]=figma.variables.setBoundVariableForPaint(st[i],'color',vr);st[i]={...st[i],opacity:origOp};nd.strokes=st;}
else if(p[0]==='e'){const i=+p[1],fm={c:'color',r:'radius',x:'offsetX',y:'offsetY',s:'spread'}[p[2]],ef=[...nd.effects];if(fm==='color'){const origA=ef[i].color?ef[i].color.a:1;ef[i]=figma.variables.setBoundVariableForEffect(ef[i],fm,vr);ef[i]={...ef[i],color:{...ef[i].color,a:origA}};}else{ef[i]=figma.variables.setBoundVariableForEffect(ef[i],fm,vr);}nd.effects=ef;}
else{const M={cr:'cornerRadius',tlr:'topLeftRadius',trr:'topRightRadius',blr:'bottomLeftRadius',brr:'bottomRightRadius',pt:'paddingTop',pr:'paddingRight',pb:'paddingBottom',pl:'paddingLeft',is:'itemSpacing',cas:'counterAxisSpacing',op:'opacity',sw:'strokeWeight',stw:'strokeTopWeight',srw:'strokeRightWeight',sbw:'strokeBottomWeight',slw:'strokeLeftWeight',fs:'fontSize',ff:'fontFamily',fw:'fontWeight',fst:'fontStyle',lh:'lineHeight',ls:'letterSpacing',ps:'paragraphSpacing'};
const prop=M[p];if(prop==='itemSpacing'&&nd.primaryAxisAlignItems==='SPACE_BETWEEN'){b++;continue;}
if(prop){nd.setBoundVariable(prop,vr);}else{f++;E.push({n,p,r:'UNKNOWN_PROP'});continue;}}
b++;}catch(e){f++;E.push({n,p,r:e.message});}}
figma.root.setPluginData('rebind_errors',JSON.stringify(errs.concat(E)));
figma.notify(`Rebound ${b}/${R.length} (${f} failures)`);"""


def generate_compact_script(entries: list[dict[str, Any]]) -> str:
    """
    Generate a compact rebind script using pipe-delimited encoding.

    Each binding is encoded as `nodeId|propertyCode|variableIdSuffix` where:
    - propertyCode is a short code from PROPERTY_SHORTCODES
    - variableIdSuffix strips the 'VariableID:' prefix

    This produces scripts ~60% smaller than generate_single_script,
    allowing ~1500 bindings per script within the 50K char limit.
    """
    if not entries:
        return f"(async()=>{{const D='';{COMPACT_HANDLER}}})();"

    lines = []
    for entry in entries:
        code = encode_property(entry["property"])
        if code is None:
            continue
        var_suffix = entry["variable_id"].removeprefix("VariableID:")
        lines.append(f"{entry['node_id']}|{code}|{var_suffix}")

    data_str = "\\n".join(lines)
    return f"(async()=>{{const D='{data_str}';{COMPACT_HANDLER}}})();"


def generate_error_read_script() -> str:
    """Generate a script that reads persisted rebind errors from pluginData."""
    return (
        "const d=figma.root.getPluginData('rebind_errors');"
        "const errors=d?JSON.parse(d):[];"
        "console.log('REBIND_ERRORS:'+JSON.stringify(errors));"
        "return {count:errors.length,errors:errors.slice(0,200)};"
    )


def generate_error_clear_script() -> str:
    """Generate a script that clears persisted rebind errors from pluginData."""
    return "figma.root.setPluginData('rebind_errors','[]');return 'cleared';"


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
        scripts.append(generate_compact_script(batch))

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