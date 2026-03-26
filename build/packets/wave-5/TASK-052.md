---
taskId: TASK-052
title: "Implement rebind script generator (Phase 8)"
wave: wave-5
testFirst: true
testLevel: unit
dependencies: [TASK-002]
produces:
  - dd/export_rebind.py
verify:
  - type: typecheck
    command: 'python -c "from dd.export_rebind import generate_rebind_scripts, generate_single_script, query_bindable_entries, PROPERTY_HANDLERS"'
    passWhen: 'exits 0'
  - type: test
    command: 'pytest tests/test_export_figma.py -k "rebind or script or property_type" -v'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-052: Implement rebind script generator (Phase 8)

## Spec Context

### From Technical Design Spec -- Phase 8: Node Rebinding

> **Tool:** Console MCP `figma_execute` (automated), or plugin script pasted into Figma console (manual fallback).
>
> **Script generation:**
> 1. Query all `node_token_bindings` where `binding_status = 'bound'` and the token has a `figma_variable_id`.
> 2. Generate self-contained async plugin scripts.
>
> ```javascript
> // Generated rebind script -- one per batch of nodes
> (async () => {
>   const bindings = [
>     { nodeId: "2219:235701", property: "fill.0.color", variableId: "VariableID:123:456" },
>     { nodeId: "2219:235702", property: "fontSize", variableId: "VariableID:123:789" },
>     { nodeId: "2219:235703", property: "effect.0.color", variableId: "VariableID:123:012" },
>     // ... up to ~500 per script to stay within console limits
>   ];
>
>   let bound = 0, failed = 0;
>
>   for (const b of bindings) {
>     try {
>       const node = await figma.getNodeByIdAsync(b.nodeId);
>       if (!node) { failed++; continue; }
>
>       const variable = await figma.variables.getVariableByIdAsync(b.variableId);
>       if (!variable) { failed++; continue; }
>
>       // --- Paint bindings (fills, strokes) ---
>       if (b.property.startsWith('fill.') && b.property.endsWith('.color')) {
>         const idx = parseInt(b.property.split('.')[1]);
>         const fills = [...node.fills];
>         fills[idx] = figma.variables.setBoundVariableForPaint(fills[idx], 'color', variable);
>         node.fills = fills;
>
>       } else if (b.property.startsWith('stroke.') && b.property.endsWith('.color')) {
>         const idx = parseInt(b.property.split('.')[1]);
>         const strokes = [...node.strokes];
>         strokes[idx] = figma.variables.setBoundVariableForPaint(strokes[idx], 'color', variable);
>         node.strokes = strokes;
>
>       } else if (b.property.startsWith('effect.')) {
>         const parts = b.property.split('.');
>         const idx = parseInt(parts[1]);
>         const field = parts[2];
>         const effects = [...node.effects];
>         effects[idx] = figma.variables.setBoundVariableForEffect(effects[idx], field, variable);
>         node.effects = effects;
>
>       } else if (['cornerRadius','topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius',
>                    'itemSpacing','counterAxisSpacing','opacity','strokeWeight',
>                    'strokeTopWeight','strokeRightWeight','strokeBottomWeight','strokeLeftWeight'].includes(b.property)) {
>         node.setBoundVariable(b.property, variable);
>
>       } else if (b.property.startsWith('padding.')) {
>         const side = b.property.split('.')[1];
>         const prop = 'padding' + side.charAt(0).toUpperCase() + side.slice(1);
>         node.setBoundVariable(prop, variable);
>
>       } else if (['fontSize','fontFamily','fontWeight','fontStyle','lineHeight',
>                    'letterSpacing','paragraphSpacing'].includes(b.property)) {
>         node.setBoundVariable(b.property, variable);
>
>       } else {
>         console.warn(`Unhandled property: ${b.property} on node ${b.nodeId}`);
>         failed++;
>         continue;
>       }
>       bound++;
>     } catch (e) {
>       console.error(`Failed: ${b.nodeId} ${b.property}: ${e.message}`);
>       failed++;
>     }
>   }
>
>   figma.notify(`Rebound ${bound}/${bindings.length} properties (${failed} failures)`);
> })();
> ```

> **Batching:** ~500 bindings per script. For 230 screens x ~10 bindings/node x ~200 nodes = ~460K bindings total. That's ~920 scripts.

### From User Requirements Spec -- FR-4.2

> FR-4.2: Generate rebind plugin scripts executable in Figma console, covering all bindable property types: fills, strokes, effects (shadows), corner radius, font size, font family, font weight, line height, letter spacing, padding (4-sided), item spacing, counter-axis spacing, opacity.

### From User Requirements Spec -- FR-4.7

> FR-4.7: Rebind scripts must handle all property types in the binding table. Any property path in `node_token_bindings` that has a corresponding Figma binding API must be covered.

### From Technical Design Spec -- Figma Plugin API coverage -- all bindable property types

> | Property path | API method | Variable type |
> |---|---|---|
> | `fill.N.color` | `figma.variables.setBoundVariableForPaint(paint, 'color', var)` | COLOR |
> | `stroke.N.color` | `figma.variables.setBoundVariableForPaint(paint, 'color', var)` | COLOR |
> | `effect.N.color` | `figma.variables.setBoundVariableForEffect(effect, 'color', var)` | COLOR |
> | `effect.N.radius` | `figma.variables.setBoundVariableForEffect(effect, 'radius', var)` | FLOAT |
> | `effect.N.offsetX` | `figma.variables.setBoundVariableForEffect(effect, 'offsetX', var)` | FLOAT |
> | `effect.N.offsetY` | `figma.variables.setBoundVariableForEffect(effect, 'offsetY', var)` | FLOAT |
> | `effect.N.spread` | `figma.variables.setBoundVariableForEffect(effect, 'spread', var)` | FLOAT |
> | `cornerRadius`, `topLeftRadius`, etc. | `node.setBoundVariable(field, var)` | FLOAT |
> | `paddingTop/Right/Bottom/Left` | `node.setBoundVariable(field, var)` | FLOAT |
> | `itemSpacing`, `counterAxisSpacing` | `node.setBoundVariable(field, var)` | FLOAT |
> | `opacity` | `node.setBoundVariable('opacity', var)` | FLOAT |
> | `fontSize` | `node.setBoundVariable('fontSize', var)` | FLOAT |
> | `fontFamily` | `node.setBoundVariable('fontFamily', var)` | STRING |
> | `fontWeight` | `node.setBoundVariable('fontWeight', var)` | FLOAT |
> | `fontStyle` | `node.setBoundVariable('fontStyle', var)` | STRING |
> | `lineHeight` | `node.setBoundVariable('lineHeight', var)` | FLOAT |
> | `letterSpacing` | `node.setBoundVariable('letterSpacing', var)` | FLOAT |
> | `paragraphSpacing` | `node.setBoundVariable('paragraphSpacing', var)` | FLOAT |
> | `strokeWeight`, `stroke*Weight` | `node.setBoundVariable(field, var)` | FLOAT |

### From schema.sql -- node_token_bindings table

> ```sql
> CREATE TABLE IF NOT EXISTS node_token_bindings (
>     id              INTEGER PRIMARY KEY,
>     node_id         INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
>     property        TEXT NOT NULL,
>     token_id        INTEGER REFERENCES tokens(id),
>     raw_value       TEXT NOT NULL,
>     resolved_value  TEXT NOT NULL,
>     confidence      REAL,
>     binding_status  TEXT NOT NULL DEFAULT 'unbound'
>                     CHECK(binding_status IN ('unbound', 'proposed', 'bound', 'overridden')),
>     UNIQUE(node_id, property)
> );
> ```

### From schema.sql -- nodes and tokens tables

> ```sql
> CREATE TABLE IF NOT EXISTS nodes (
>     id              INTEGER PRIMARY KEY,
>     screen_id       INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
>     figma_node_id   TEXT NOT NULL,
>     ...
>     UNIQUE(screen_id, figma_node_id)
> );
>
> CREATE TABLE IF NOT EXISTS tokens (
>     id              INTEGER PRIMARY KEY,
>     ...
>     figma_variable_id TEXT,
>     ...
> );
> ```

### From dd/config.py (produced by TASK-001)

> Exports:
> - `MAX_BINDINGS_PER_SCRIPT = 500`

## Task

Create `dd/export_rebind.py` implementing the rebind script generator from Phase 8. This module queries bound bindings with Figma variable IDs and generates self-contained async JavaScript plugin scripts.

1. **`PROPERTY_HANDLERS: dict[str, str]`**:
   - Map property patterns to handler categories for documentation/testing:
     ```python
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
         "fontSize": "direct",
         "fontFamily": "direct",
         "fontWeight": "direct",
         "fontStyle": "direct",
         "lineHeight": "direct",
         "letterSpacing": "direct",
         "paragraphSpacing": "direct",
     }
     ```

2. **`classify_property(property_path: str) -> str`**:
   - Determine the handler category for a given property path.
   - If starts with `fill.` and ends with `.color` -> `"paint_fill"`
   - If starts with `stroke.` and ends with `.color` -> `"paint_stroke"`
   - If starts with `effect.` -> `"effect"`
   - If starts with `padding.` -> `"padding"`
   - If in the set of direct-bind properties (cornerRadius, itemSpacing, opacity, fontSize, fontFamily, fontWeight, fontStyle, lineHeight, letterSpacing, paragraphSpacing, counterAxisSpacing, strokeWeight, topLeftRadius, topRightRadius, bottomLeftRadius, bottomRightRadius, strokeTopWeight, strokeRightWeight, strokeBottomWeight, strokeLeftWeight) -> `"direct"`
   - Otherwise -> `"unknown"`

3. **`query_bindable_entries(conn, file_id: int) -> list[dict]`**:
   - Query bindings that can be rebound in Figma:
     ```sql
     SELECT ntb.id AS binding_id,
            n.figma_node_id,
            ntb.property,
            t.figma_variable_id
     FROM node_token_bindings ntb
     JOIN nodes n ON ntb.node_id = n.id
     JOIN screens s ON n.screen_id = s.id
     JOIN tokens t ON ntb.token_id = t.id
     WHERE s.file_id = ?
       AND ntb.binding_status = 'bound'
       AND t.figma_variable_id IS NOT NULL
     ORDER BY s.id, n.id, ntb.property
     ```
   - Return list of dicts: `{"binding_id": int, "node_id": str, "property": str, "variable_id": str}`.
   - Filter out entries where `classify_property(property)` returns `"unknown"` (can't bind in Figma).

4. **`generate_single_script(entries: list[dict]) -> str`**:
   - Accept a list of binding entry dicts (up to MAX_BINDINGS_PER_SCRIPT).
   - Generate a self-contained async IIFE JavaScript string.
   - The script template follows the TDS Phase 8 template exactly (see Spec Context above).
   - Build the `bindings` array from the entries: each entry becomes `{ nodeId: "...", property: "...", variableId: "..." }`.
   - Include the full property dispatch logic covering all handler categories:
     - paint_fill: `setBoundVariableForPaint` on fills array
     - paint_stroke: `setBoundVariableForPaint` on strokes array
     - effect: `setBoundVariableForEffect` on effects array
     - padding: convert `padding.top` to `paddingTop` etc., then `setBoundVariable`
     - direct: `setBoundVariable` directly
   - Include error handling (try/catch per binding).
   - Include the `figma.notify` summary at the end.
   - Return the JavaScript string.

5. **`generate_rebind_scripts(conn, file_id: int) -> list[str]`**:
   - Main entry point.
   - Call `query_bindable_entries(conn, file_id)`.
   - Batch into chunks of `MAX_BINDINGS_PER_SCRIPT` (500).
   - For each batch, call `generate_single_script(batch)`.
   - Return list of JavaScript strings.

6. **`get_rebind_summary(conn, file_id: int) -> dict`**:
   - Without generating scripts, compute summary stats:
     ```python
     {
         "total_bindings": int,
         "script_count": int,  # ceil(total / 500)
         "by_property_type": dict[str, int],  # count per handler category
         "unbindable": int,  # entries with unknown property type
     }
     ```

## Acceptance Criteria

- [ ] `python -c "from dd.export_rebind import generate_rebind_scripts, generate_single_script, query_bindable_entries, classify_property, get_rebind_summary, PROPERTY_HANDLERS"` exits 0
- [ ] `classify_property("fill.0.color")` returns `"paint_fill"`
- [ ] `classify_property("stroke.1.color")` returns `"paint_stroke"`
- [ ] `classify_property("effect.0.radius")` returns `"effect"`
- [ ] `classify_property("effect.0.color")` returns `"effect"`
- [ ] `classify_property("padding.top")` returns `"padding"`
- [ ] `classify_property("fontSize")` returns `"direct"`
- [ ] `classify_property("fontFamily")` returns `"direct"`
- [ ] `classify_property("opacity")` returns `"direct"`
- [ ] `classify_property("cornerRadius")` returns `"direct"`
- [ ] `classify_property("unknown.property")` returns `"unknown"`
- [ ] `generate_single_script` returns a string containing `(async () =>` and `figma.notify`
- [ ] `generate_single_script` includes handlers for fill, stroke, effect, padding, and direct properties
- [ ] `generate_single_script` produces syntactically valid JS (contains matching braces, no unclosed strings)
- [ ] `generate_rebind_scripts` batches entries into scripts of at most 500 bindings each
- [ ] `query_bindable_entries` only returns bound bindings with figma_variable_id
- [ ] `get_rebind_summary` returns correct counts per property type
- [ ] Scripts handle all property types from the TDS binding table

## Notes

- This module generates JavaScript code but does NOT execute it. A separate agent with Console MCP access will execute scripts via `figma_execute`, or the user will paste them into the Figma console.
- The generated JS must be self-contained: no external dependencies, no imports. Everything needed is in the IIFE.
- The property dispatch logic in the script exactly mirrors the TDS Phase 8 template. The padding conversion (`padding.top` -> `paddingTop`) is important because Figma's API uses camelCase while our DB uses dot-notation.
- The `classify_property` function is used both for query filtering (skip unknown types) and for the `get_rebind_summary` stats.
- The script uses `figma.getNodeByIdAsync` and `figma.variables.getVariableByIdAsync` (async variants) because Console MCP's `figma_execute` requires async Plugin API.