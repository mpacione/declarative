---
taskId: TASK-011
title: "Implement screen extraction script generator"
wave: wave-1
testFirst: false
testLevel: unit
dependencies: [TASK-002, TASK-003]
produces:
  - dd/extract_screens.py
verify:
  - type: typecheck
    command: 'python -c "from dd.extract_screens import generate_extraction_script, parse_extraction_response, insert_nodes"'
    passWhen: 'exits 0'
  - type: custom
    command: 'python -c "from dd.extract_screens import generate_extraction_script; script = generate_extraction_script(\"100:1\"); assert \"figma.getNodeById\" in script or \"getNodeById\" in script; assert len(script) < 50000; print(\"OK\")"'
    passWhen: 'exits 0'
contextProfile: full
---

# TASK-011: Implement screen extraction script generator

## Spec Context

### From Technical Design Spec -- Phase 2: Screen Extraction

> **Tool:** Official MCP `use_figma` (synchronous Plugin API).
> **Strategy:** One call per screen. Each call traverses the full node tree and returns all properties.
>
> **Extraction script template** (injected into `use_figma` code field):
>
> ```javascript
> function extractScreen(screenId) {
>   const screen = figma.getNodeById(screenId);
>   const nodes = [];
>
>   function walk(node, parentIdx, depth) {
>     const entry = {
>       figma_node_id: node.id,
>       parent_idx: parentIdx,
>       name: node.name,
>       node_type: node.type,
>       depth: depth,
>       sort_order: node.parent?.children?.indexOf(node) ?? 0,
>       x: node.x, y: node.y,
>       width: node.width, height: node.height,
>     };
>
>     // Visual properties
>     if ('fills' in node) entry.fills = JSON.stringify(node.fills);
>     if ('strokes' in node) entry.strokes = JSON.stringify(node.strokes);
>     if ('effects' in node) entry.effects = JSON.stringify(node.effects);
>     if ('cornerRadius' in node) entry.corner_radius = node.cornerRadius;
>     if ('opacity' in node) entry.opacity = node.opacity;
>     if ('blendMode' in node) entry.blend_mode = node.blendMode;
>     if ('visible' in node) entry.visible = node.visible;
>
>     // Auto-layout
>     if (node.layoutMode && node.layoutMode !== 'NONE') {
>       entry.layout_mode = node.layoutMode;
>       entry.padding_top = node.paddingTop;
>       entry.padding_right = node.paddingRight;
>       entry.padding_bottom = node.paddingBottom;
>       entry.padding_left = node.paddingLeft;
>       entry.item_spacing = node.itemSpacing;
>       entry.counter_axis_spacing = node.counterAxisSpacing;
>       entry.primary_align = node.primaryAxisAlignItems;
>       entry.counter_align = node.counterAxisAlignItems;
>       entry.layout_sizing_h = node.layoutSizingHorizontal;
>       entry.layout_sizing_v = node.layoutSizingVertical;
>     }
>
>     // Typography (TEXT nodes)
>     if (node.type === 'TEXT') {
>       entry.font_family = node.fontName?.family;
>       entry.font_weight = node.fontWeight;
>       entry.font_size = node.fontSize;
>       entry.line_height = JSON.stringify(node.lineHeight);
>       entry.letter_spacing = JSON.stringify(node.letterSpacing);
>       entry.text_align = node.textAlignHorizontal;
>       entry.text_content = node.characters;
>     }
>
>     // Component reference (INSTANCE nodes)
>     if (node.type === 'INSTANCE' && node.mainComponent) {
>       entry.component_figma_id = node.mainComponent.id;
>     }
>
>     const idx = nodes.length;
>     nodes.push(entry);
>
>     if ('children' in node) {
>       node.children.forEach(child => walk(child, idx, depth + 1));
>     }
>   }
>
>   walk(screen, null, 0);
>   return nodes;
> }
> ```

> **Throughput model:**
> - ~200 nodes/screen x ~37K chars/response = well within limits
> - 230 screens x ~4 sec/call = ~15 minutes

### From User Requirements Spec -- Constraints

> C-1: Official Figma MCP `use_figma` code field limit: 50,000 characters per call.
> C-2: Official Figma MCP `use_figma` return payload: uncapped but ~37K observed per 200-node screen.

### From Technical Design Spec -- is_semantic computation

> A node is flagged `is_semantic = 1` if ANY of these are true:
> 1. `node_type` is TEXT, INSTANCE, or COMPONENT.
> 2. `node_type` is FRAME and `layout_mode` is not NULL (auto-layout container).
> 3. Node `name` does not start with "Frame", "Group", "Rectangle", or "Vector" (user-renamed = intentional).
> 4. Node has >= 2 children and at least one child is `is_semantic` (meaningful parent).

### From schema.sql -- nodes table

> ```sql
> CREATE TABLE IF NOT EXISTS nodes (
>     id              INTEGER PRIMARY KEY,
>     screen_id       INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
>     figma_node_id   TEXT NOT NULL,
>     parent_id       INTEGER REFERENCES nodes(id),
>     path            TEXT,
>     name            TEXT NOT NULL,
>     node_type       TEXT NOT NULL,
>     depth           INTEGER NOT NULL DEFAULT 0,
>     sort_order      INTEGER NOT NULL DEFAULT 0,
>     is_semantic     INTEGER NOT NULL DEFAULT 0,
>     component_id    INTEGER REFERENCES components(id),
>     x               REAL, y REAL, width REAL, height REAL,
>     layout_mode     TEXT,
>     padding_top     REAL, padding_right REAL, padding_bottom REAL, padding_left REAL,
>     item_spacing    REAL, counter_axis_spacing REAL,
>     primary_align   TEXT, counter_align TEXT,
>     layout_sizing_h TEXT, layout_sizing_v TEXT,
>     fills           TEXT, strokes TEXT, effects TEXT, corner_radius TEXT,
>     opacity         REAL DEFAULT 1.0, blend_mode TEXT DEFAULT 'NORMAL',
>     visible         INTEGER NOT NULL DEFAULT 1,
>     font_family     TEXT, font_weight INTEGER, font_size REAL,
>     line_height     TEXT, letter_spacing TEXT, text_align TEXT, text_content TEXT,
>     extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
>     UNIQUE(screen_id, figma_node_id)
> );
> ```

### From dd/types.py (produced by TASK-003)

> Exports:
> - `SEMANTIC_NODE_TYPES: frozenset[str]` = {"TEXT", "INSTANCE", "COMPONENT"}
> - `NON_SEMANTIC_PREFIXES: tuple[str, ...]` = ("Frame", "Group", "Rectangle", "Vector")

### From dd/config.py (produced by TASK-001)

> Exports: `USE_FIGMA_CODE_LIMIT = 50000`

## Task

Create `dd/extract_screens.py` implementing screen-level extraction. This module generates JS code for the `use_figma` MCP call, parses the response, computes `is_semantic`, and inserts nodes into the DB. The actual MCP call is made by a separate agent session -- this module only produces the JS code and consumes the response.

1. **`generate_extraction_script(screen_node_id: str) -> str`**:
   - Return a self-contained JavaScript string that, when executed via `use_figma`, traverses the screen's node tree and returns an array of node objects.
   - Use the extraction script template from the TDS (see Spec Context) as the basis.
   - The script must call the `extractScreen` function with the given `screen_node_id` and return the result.
   - The script must be under 50,000 characters (USE_FIGMA_CODE_LIMIT).
   - The returned JavaScript should end with `return extractScreen("${screen_node_id}");` so `use_figma` gets the result.
   - Handle the `fontName` being a `{family, style}` object -- extract `family`.
   - Handle `cornerRadius` potentially being `figma.mixed` -- in that case, read individual corner radii `topLeftRadius`, `topRightRadius`, `bottomLeftRadius`, `bottomRightRadius` and store as JSON object.

2. **`parse_extraction_response(response: list[dict]) -> list[dict]`**:
   - Accept the raw response from `use_figma` -- a list of node dicts.
   - Validate that each dict has required keys: `figma_node_id`, `name`, `node_type`.
   - Normalize data types: ensure `depth` and `sort_order` are ints, `x/y/width/height` are floats or None.
   - Convert `visible` to int (1/0) from boolean.
   - Convert `fills`, `strokes`, `effects` to JSON strings if they are objects/lists.
   - Handle `corner_radius`: if it's a number, store as string. If it's an object (mixed radii), store as JSON string.
   - Handle `line_height` and `letter_spacing`: ensure they're JSON strings.
   - Return the cleaned list of dicts, each ready for DB insertion.

3. **`compute_is_semantic(nodes: list[dict]) -> list[dict]`**:
   - Accept a list of parsed node dicts (with `parent_idx` for parent reference).
   - Apply the is_semantic rules from the TDS:
     a. `node_type` in SEMANTIC_NODE_TYPES -> is_semantic = 1
     b. `node_type == "FRAME"` and `layout_mode` is not None -> is_semantic = 1
     c. `name` does not start with any NON_SEMANTIC_PREFIXES -> is_semantic = 1
     d. Node has >= 2 children and at least one child is_semantic -> is_semantic = 1
   - Rule (d) requires a bottom-up pass -- process children before parents.
   - Set `is_semantic` field on each node dict.
   - Return the updated list.

4. **`insert_nodes(conn, screen_id: int, nodes: list[dict]) -> list[int]`**:
   - Insert nodes into the `nodes` table using UPSERT (`INSERT ... ON CONFLICT(screen_id, figma_node_id) DO UPDATE`).
   - The `parent_idx` field in each node dict is an index into the `nodes` list (not a DB id). Convert to `parent_id` by mapping: after inserting each node, store its DB id; when a child references `parent_idx=N`, look up the DB id of node at index N.
   - Strategy: Insert nodes in order (parents before children since walk is depth-first). After each insert, record the DB id. When processing a child with `parent_idx`, use the pre-recorded parent's DB id.
   - Do NOT compute `path` here -- that's done by TASK-013 (`dd/paths.py`).
   - Return list of DB node IDs.
   - Commit after all inserts.

5. **`update_screen_status(conn, run_id: int, screen_id: int, status: str, node_count: int | None = None, binding_count: int | None = None, error: str | None = None)`**:
   - Update `screen_extraction_status` for this run/screen with the given status.
   - Set `started_at` if status is 'in_progress', `completed_at` if status is 'completed' or 'failed'.
   - Update `node_count` and `binding_count` if provided.
   - Update `error` if provided.

## Acceptance Criteria

- [ ] `python -c "from dd.extract_screens import generate_extraction_script, parse_extraction_response, insert_nodes, compute_is_semantic, update_screen_status"` exits 0
- [ ] `generate_extraction_script("100:1")` returns a JS string containing "100:1" and under 50000 chars
- [ ] The generated JS string contains `extractScreen` function definition and a return statement
- [ ] `parse_extraction_response` handles a list of dicts with mixed key presence (some nodes have fills, some don't)
- [ ] `parse_extraction_response` converts boolean `visible` to integer 1/0
- [ ] `compute_is_semantic` marks TEXT nodes as semantic
- [ ] `compute_is_semantic` marks FRAME nodes with layout_mode as semantic
- [ ] `compute_is_semantic` marks nodes with user-set names (not starting with "Frame"/"Group"/"Rectangle"/"Vector") as semantic
- [ ] `compute_is_semantic` marks parent with 2+ children where at least one is semantic as semantic
- [ ] `insert_nodes` inserts nodes and resolves parent_idx to parent_id correctly
- [ ] `insert_nodes` with same data twice (UPSERT) doesn't create duplicate nodes
- [ ] `update_screen_status` updates the status and timestamps correctly

## Notes

- This module generates JavaScript code but does NOT execute it. A separate agent session with MCP access will call `use_figma` with this code and pass the response back to `parse_extraction_response`.
- The `parent_idx` to `parent_id` mapping is critical. The walk function emits nodes in depth-first order, so a parent always appears before its children in the list. The parent_idx is the array index of the parent in the flat list.
- The `path` field is left NULL by `insert_nodes`. TASK-013 (`dd/paths.py`) computes paths after all nodes are inserted.
- `corner_radius` in Figma can be a single number (uniform) or `figma.mixed` (different per corner). When mixed, the individual radii (`topLeftRadius` etc.) are available on the node. The JS script should handle this.