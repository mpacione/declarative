# Declarative Design — Technical Design Spec

Status: Draft v0.2
Date: 2025-03-25
Depends on: Architecture.md, Probe Results.md, Tooling Comparison.md, schema.sql (v0.2)

## System Overview

A local extraction-and-structuring pipeline that converts a hardcoded Figma file into a queryable SQLite database of tokens, components, compositions, and cross-tool mappings. The DB becomes the portable source of truth consumed by coding agents, Figma export scripts, and future design composition agents.

```
┌─────────────┐     use_figma (sync)      ┌──────────────┐
│  Figma File  │ ──────────────────────── → │  Extraction  │
│  (25K nodes) │                           │   Pipeline   │
└─────────────┘                            └──────┬───────┘
                                                  │
                                                  ▼
                                           ┌──────────────┐
                                           │   SQLite DB   │
                                           │  (source of   │
                                           │    truth)     │
                                           └──┬───┬───┬───┘
                                              │   │   │
                    ┌─────────────────────────┘   │   └──────────────────────┐
                    ▼                              ▼                          ▼
          ┌─────────────────┐           ┌──────────────────┐       ┌─────────────────┐
          │  Figma Export   │           │  Coding Agent    │       │  Clustering /   │
          │  (Console MCP   │           │  (reads DB       │       │  Curation UI    │
          │   + plugin      │           │   directly, or   │       │  (queries DB)   │
          │   scripts)      │           │   via companion  │       │                 │
          │                 │           │   skill)         │       │                 │
          └─────────────────┘           └──────────────────┘       └─────────────────┘
```

## Key Design Decisions

**Composite tokens (typography, shadow, border)** are stored as individual atomic tokens in the DB. DTCG composite types are assembled at export time when generating `tokens.json`. This keeps the DB queryable (you can ask "all font sizes" without parsing composite JSON) and avoids a grouping table that adds complexity with no query benefit. The `tokens.json` exporter reconstructs composites by matching token paths: `type.body.md.fontFamily` + `type.body.md.fontSize` + `type.body.md.lineHeight` → one DTCG `typography` composite.

**DTCG resolver format** (sets + modifiers) is generated at export time from the flat `token_collections` / `token_modes` tables. The DB mirrors Figma's mode model (1 collection = N flat modes) because: (a) Figma is the immediate export target, (b) flat rows are trivially queryable in SQL, (c) the source data being extracted is flat. The `tokens.json` exporter wraps each collection as a set and each non-default mode as a modifier context per W3C v2025.10 spec.

**No CLI.** The agent is the interface. Python scripts handle deterministic work (extraction, normalization, clustering). The agent orchestrates MCP calls and queries the DB directly. A CLI would add indirection with no benefit for a single-user system.

## Pipeline Phases

### Phase 1: File Inventory

**Tool:** Official MCP `get_metadata` or Console MCP `figma_get_file_data` (depth 1).
**Purpose:** Enumerate all top-level frames (screens) on the target page without extracting properties.
**Output:** Populated `files`, `screens`, and `extraction_runs` tables.

```
Input:  file_key = "drxXOUOdYEBBQ09mrXJeYu", page = "1312:136189"
Output: ~230 rows in screens table with figma_node_id, name, width, height, device_class
        1 row in extraction_runs with status = 'running'
        ~230 rows in screen_extraction_status with status = 'pending'
```

**Device classification logic:**
| Width | Height | device_class |
|-------|--------|-------------|
| 428   | 926    | iphone      |
| 834   | 1194   | ipad_11     |
| 1536  | 1152   | ipad_13     |
| other | other  | unknown     |

**Component sheet detection heuristics** (frames that are NOT screens):
1. Name contains "Buttons", "Controls", "Components", "Modals", "Popups", "Icons", "Website", or "Assets" (case-insensitive).
2. Dimensions don't match any known device class AND frame contains component definitions (node type = COMPONENT or COMPONENT_SET).
3. Frame contains no INSTANCE nodes (it's a definition sheet, not a composed screen).

Frames matching any heuristic are tagged `device_class = component_sheet` and extracted separately for component definitions in Phase 4.

### Phase 2: Screen Extraction

**Tool:** Figma REST API (`GET /v1/files/:key/nodes`) via `dd/figma_api.py`, invoked by CLI (`python -m dd extract`).
**Strategy:** Batch-fetch screens (10 per API call) via the `ids` parameter. Each response is converted to extraction format and processed through the existing pipeline. Retry with exponential backoff on 429 rate limits.

**Extraction run coordination:**
1. Before extracting, check `screen_extraction_status` for this run.
2. Skip screens with `status = 'completed'` (resume support).
3. Skip screens with `status = 'in_progress'` and `started_at` < 10 min ago (another agent owns it).
4. Set `status = 'in_progress'` before calling `use_figma`.
5. Set `status = 'completed'` after successful DB write. Update `node_count`, `binding_count`.
6. Set `status = 'failed'` with `error` message on failure.

**Extraction script template** (injected into `use_figma` code field):

```javascript
// Pseudocode — actual implementation will be a self-contained function
// that fits within 50K char code field limit

function extractScreen(screenId) {
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
    if ('cornerRadius' in node) entry.corner_radius = node.cornerRadius;
    if ('opacity' in node) entry.opacity = node.opacity;
    if ('blendMode' in node) entry.blend_mode = node.blendMode;
    if ('visible' in node) entry.visible = node.visible;

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
    }

    // Typography (TEXT nodes)
    if (node.type === 'TEXT') {
      entry.font_family = node.fontName?.family;
      entry.font_weight = node.fontWeight;
      entry.font_size = node.fontSize;
      entry.line_height = JSON.stringify(node.lineHeight);
      entry.letter_spacing = JSON.stringify(node.letterSpacing);
      entry.text_align = node.textAlignHorizontal;
      entry.text_content = node.characters;
    }

    // Component reference (INSTANCE nodes)
    if (node.type === 'INSTANCE' && node.mainComponent) {
      entry.component_figma_id = node.mainComponent.id;
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
```

**`is_semantic` computation** (applied during DB write, not in Figma script):
A node is flagged `is_semantic = 1` if ANY of these are true:
1. `node_type` is TEXT, INSTANCE, or COMPONENT.
2. `node_type` is FRAME and `layout_mode` is not NULL (auto-layout container).
3. Node `name` does not start with "Frame", "Group", "Rectangle", or "Vector" (user-renamed = intentional).
4. Node has ≥2 children and at least one child is `is_semantic` (meaningful parent).

Everything else gets `is_semantic = 0`. This is conservative — it's cheap to flip a node to semantic later during curation, expensive to un-flag thousands of noise nodes.

**Materialized path computation** (applied during DB write):
Each node gets a `path` string computed from its position in the tree. Root nodes get path `"0"`, `"1"`, etc. (by sort_order). Children append `.{sort_order}`: `"0.2.1"` means first root child → third child → second child. Computed bottom-up after the full tree is written, since parent IDs must resolve first.

This enables efficient subtree queries without recursive CTEs:
```sql
-- All descendants of the node with path '0.3'
SELECT * FROM nodes WHERE path LIKE '0.3.%' AND screen_id = ?;
```

**Throughput model:**
- ~200 nodes/screen × ~37K chars/response = well within limits
- 230 screens × ~4 sec/call = ~15 minutes
- Parallelism: Serial (one `use_figma` at a time per Figma session)

**Error handling:**
- If a call fails (timeout, Figma crash), log the screen ID and retry.
- If a screen exceeds 500 nodes (unlikely given ~200 avg), split into sub-trees.
- Checkpoint after each screen via `screen_extraction_status` — partial extraction is resumable.

### Phase 3: Value Normalization + Binding Creation

**Tool:** Local Python, no MCP calls.
**Runs immediately after each screen extraction, before the next `use_figma` call.**

For every node property that represents a design value:

| Property path | Raw value example | Resolved value |
|---|---|---|
| `fill.0.color` | `{"r":0.035,"g":0.035,"b":0.043,"a":1}` | `#09090B` |
| `fill.0.color` (with opacity) | `{"r":1,"g":1,"b":1,"a":0.5}` | `#FFFFFF80` |
| `stroke.0.color` | `{"r":0.831,"g":0.831,"b":0.847,"a":1}` | `#D4D4D8` |
| `cornerRadius` | `8` | `8` |
| `fontSize` | `16` | `16` |
| `fontFamily` | `"Inter"` | `Inter` |
| `fontWeight` | `600` | `600` |
| `lineHeight` | `{"value":24,"unit":"PIXELS"}` | `24` |
| `letterSpacing` | `{"value":-0.5,"unit":"PIXELS"}` | `-0.5` |
| `padding.top` | `16` | `16` |
| `itemSpacing` | `8` | `8` |
| `opacity` | `0.5` | `0.5` |
| `effect.0.color` | `{"r":0,"g":0,"b":0,"a":0.1}` | `#0000001A` |
| `effect.0.radius` | `6` | `6` |
| `effect.0.offsetX` | `0` | `0` |
| `effect.0.offsetY` | `4` | `4` |
| `effect.0.spread` | `-1` | `-1` |

**Color normalization:** RGBA 0-1 floats → 8-digit hex (with alpha) or 6-digit hex (if alpha = 1). Use round(component × 255) for each channel.

**Effect decomposition:** Each effect property gets its own binding row. A single DROP_SHADOW produces 5 bindings: `effect.0.color`, `effect.0.radius`, `effect.0.offsetX`, `effect.0.offsetY`, `effect.0.spread`. This maps 1:1 to Figma's `setBoundVariableForEffect` API which binds each field independently.

**Gradient handling:** Store as `fill.0.gradient` with stops array in raw_value. Resolved value is a CSS `linear-gradient()` or `radial-gradient()` string. Gradient color stops cannot be bound to variables in Figma — stored for code export only.

**Mixed fills:** Figma supports multiple fills per node. Each gets its own binding row: `fill.0.color`, `fill.1.color`, etc.

Each property produces one row in `node_token_bindings` with `token_id = NULL`, `binding_status = 'unbound'`.

### Phase 4: Component Extraction

**Tool:** Official MCP `use_figma` targeting component frames.
**Runs after screen extraction, targeting the "Buttons and Controls" frame and any detected component sets.**

For each component/component set:
1. Extract name, variant properties (axes like size, style, state).
2. Extract each variant's node ID and property combination.
3. Generate a structured `composition_hint` — an ordered list of slots with defaults, layout direction, spacing token, padding tokens.
4. Populate `variant_axes` table: normalize the JSON variant properties into structured rows. Flag axes where all values match known interaction states (default, hover, focus, pressed, disabled, selected, loading) as `is_interaction = 1`.
5. Populate `variant_dimension_values`: link each variant to its position on each axis.
6. Populate `component_slots`: analyze the component's direct children to identify named insertion points. A child is a slot if it's a distinct semantic element (not a spacer/divider/background fill).
7. Populate `component_a11y`: infer role from component category and name (button → `role: button`, input → `role: textbox`). Set `min_touch_target = 44` for interactive components (iOS default). Manual augmentation during curation.
8. Populate `component_responsive`: analyze variant axes for breakpoint-related properties. If no responsive variants exist, leave empty (nullable).

Stored in `components`, `component_variants`, `variant_axes`, `variant_dimension_values`, `component_slots`, `component_a11y`, and `component_responsive` tables.

### Phase 5: Clustering + Token Proposal

**Tool:** Local Python, no MCP calls.
**Input:** Census views from the DB.

**Color clustering:**
1. Query `v_color_census WHERE file_id = ?` — all unique hex values with usage counts.
2. Convert to OKLCH for perceptual clustering.
3. Group colors within ΔE < 2.0 (imperceptible difference). Merge to the most-used value.
4. For each cluster, propose a DTCG name based on heuristics:
   - Usage on large fills → `color.surface.*`
   - Usage on text → `color.text.*`
   - Usage on small accents/icons → `color.accent.*`
   - Usage on borders/strokes → `color.border.*`
5. Rank by lightness within each group for `.primary`, `.secondary`, `.tertiary` naming.

**Typography clustering:**
1. Query `v_type_census WHERE file_id = ?` — unique font/weight/size/lineHeight combos.
2. Group into scale tiers by font size.
3. Propose names: `type.display.lg`, `type.body.md`, `type.label.sm`, etc.

**Spacing clustering:**
1. Query `v_spacing_census WHERE file_id = ?` — unique values by property.
2. Identify scale pattern (likely 4px base: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64).
3. Propose names: `space.1` through `space.16` (multiplier notation) or `space.xs` through `space.4xl` (t-shirt notation).

**Radius clustering:**
1. Query `v_radius_census WHERE file_id = ?`.
2. Typically 3-5 unique values.
3. Propose names: `radius.sm`, `radius.md`, `radius.lg`, `radius.full`.

**Effect clustering:**
1. Query `v_effect_census WHERE file_id = ?` — unique shadow/blur values.
2. Group by composite similarity (same color + similar radius + similar offset = one shadow token).
3. Propose names: `shadow.sm`, `shadow.md`, `shadow.lg`.

**Multi-mode clustering:**

When a file already has modes (or modes are added post-extraction via UC-5), clustering operates per-mode:

1. Census views accept `file_id` filter and `mode_id` filter (via `v_color_census_by_mode`). Without mode filter, they return default-mode values only (not a cross-mode mix).
2. Clustering proposes one token per semantic role (e.g., `color.surface.primary`), with mode-specific values stored in `token_values` (one row per token per mode).
3. For the initial Dank file (0 modes), clustering runs in single-mode. When a user adds Dark mode later:
   a. System copies all curated token values from Default mode into the new Dark mode.
   b. System optionally applies a heuristic transform as a starting point — for colors, invert lightness in OKLCH space (L → 1-L), clamp chroma. This is a rough scaffold, not a solution. Real dark modes require curated adjustments for shadows (softer), elevation (different), borders (lighter/more prominent), and contrast ratios (WCAG compliance per mode). The designer curates every value.
   c. For spacing, radius, and typography: no transform by default (typically mode-independent). If density modes are needed, a scale factor can be applied.
   d. User reviews and adjusts all mode-specific values before export.
4. Mode completeness validation: before export (Phase 7), every token in a collection must have a value for every mode. Missing values block export with a clear error listing the gaps.

**Output:**
- New rows in `tokens` (tier = `extracted`).
- New rows in `token_values` (one per mode — default mode initially, additional modes when added).
- Updated `node_token_bindings` — `token_id` set, `binding_status` flipped to `proposed`, `confidence` set (1.0 for exact match, 0.8-0.99 for ΔE-merged).

### Phase 6: Curation Review

**Tool:** Interactive — user reviews proposals via DB queries or a lightweight UI.

The user sees:
1. **Token list** — proposed names, types, resolved values, usage counts (from `v_token_coverage`).
2. **Low-confidence bindings** — anything with `confidence < 0.9` for manual review.
3. **Orphan values** — bindings still `unbound` after clustering (one-off values, likely design inconsistencies).

User actions:
- **Accept** — token stays, tier promoted to `curated`.
- **Rename** — update `tokens.name`.
- **Merge** — combine two tokens, update all bindings to point to the survivor.
- **Split** — break a token into two, reassign bindings.
- **Reject** — delete token, bindings revert to `unbound`.
- **Create alias** — new token with `tier = aliased`, `alias_of` pointing to a curated token. Alias depth enforced to 1 by DB trigger.

After curation, remaining `unbound` bindings are either:
- Intentionally hardcoded (one-off values, not worth tokenizing).
- Flagged as design debt for future cleanup.

### Phase 6.5: Pre-Export Validation

**Tool:** Local Python, no MCP calls.
**Runs between curation (Phase 6) and Figma export (Phase 7). Blocks export if errors exist.**

Validation checks written to `export_validations` table:

| Check | Severity | Rule |
|---|---|---|
| `mode_completeness` | error | Every token in a collection has a value for every mode in that collection |
| `name_dtcg_compliant` | error | Token names match `^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*$` pattern |
| `orphan_tokens` | warning | No tokens with 0 bindings (created but never assigned) |
| `binding_coverage` | info | Report: N% of bindings are bound, M% proposed, K% unbound |
| `alias_targets_curated` | error | Every alias points to a token with `tier = curated` (not extracted) |
| `name_uniqueness` | error | No duplicate token names within a collection |
| `value_format` | error | All `resolved_value` entries match expected format for their token type |

Export proceeds only if zero `severity = 'error'` rows exist in the latest validation run. Warnings are logged. The `v_export_readiness` view shows the summary.

### Phase 7: Figma Variable Export

**Tool:** Console MCP `figma_setup_design_tokens`.

**Payload generation:**
1. Run pre-export validation (Phase 6.5). Abort if errors.
2. Query all tokens where `tier IN ('curated', 'aliased')` and `figma_variable_id IS NULL`.
3. Group by collection.
4. Generate payloads of ≤100 tokens per call, including all modes.

```json
{
  "collectionName": "Colors",
  "modes": ["Light", "Dark"],
  "tokens": [
    {
      "name": "color/surface/primary",
      "type": "COLOR",
      "values": { "Light": "#09090B", "Dark": "#FAFAFA" }
    },
    {
      "name": "color/surface/secondary",
      "type": "COLOR",
      "values": { "Light": "#18181B", "Dark": "#F4F4F5" }
    }
  ]
}
```

**DTCG-to-Figma name mapping:** Dots become slashes (`color.surface.primary` → `color/surface/primary`) because Figma uses `/` for variable group hierarchy.

**Post-creation:** Query `figma_get_variables` to retrieve Figma variable IDs. Write back to `tokens.figma_variable_id`. Update `sync_status` to `synced`.

### Phase 8: Node Rebinding

**Tool:** Console MCP `figma_execute` (automated), or plugin script pasted into Figma console (manual fallback).

**Script generation:**
1. Query all `node_token_bindings` where `binding_status = 'bound'` and the token has a `figma_variable_id`.
2. Generate self-contained async plugin scripts.

```javascript
// Generated rebind script — one per batch of nodes
(async () => {
  const bindings = [
    { nodeId: "2219:235701", property: "fill.0.color", variableId: "VariableID:123:456" },
    { nodeId: "2219:235702", property: "fontSize", variableId: "VariableID:123:789" },
    { nodeId: "2219:235703", property: "effect.0.color", variableId: "VariableID:123:012" },
    // ... up to ~500 per script to stay within console limits
  ];

  let bound = 0, failed = 0;

  for (const b of bindings) {
    try {
      const node = await figma.getNodeByIdAsync(b.nodeId);
      if (!node) { failed++; continue; }

      const variable = await figma.variables.getVariableByIdAsync(b.variableId);
      if (!variable) { failed++; continue; }

      // --- Paint bindings (fills, strokes) ---
      if (b.property.startsWith('fill.') && b.property.endsWith('.color')) {
        const idx = parseInt(b.property.split('.')[1]);
        const fills = [...node.fills];
        fills[idx] = figma.variables.setBoundVariableForPaint(fills[idx], 'color', variable);
        node.fills = fills;

      } else if (b.property.startsWith('stroke.') && b.property.endsWith('.color')) {
        const idx = parseInt(b.property.split('.')[1]);
        const strokes = [...node.strokes];
        strokes[idx] = figma.variables.setBoundVariableForPaint(strokes[idx], 'color', variable);
        node.strokes = strokes;

      // --- Effect bindings (shadows, blurs) ---
      // Uses figma.variables.setBoundVariableForEffect() — binds individual fields
      } else if (b.property.startsWith('effect.')) {
        const parts = b.property.split('.');  // effect.0.color, effect.0.radius, etc.
        const idx = parseInt(parts[1]);
        const field = parts[2];  // 'color', 'radius', 'spread', 'offsetX', 'offsetY'
        const effects = [...node.effects];
        effects[idx] = figma.variables.setBoundVariableForEffect(effects[idx], field, variable);
        node.effects = effects;

      // --- Dimension bindings (FLOAT variables) ---
      } else if (['cornerRadius','topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius',
                   'itemSpacing','counterAxisSpacing','opacity','strokeWeight',
                   'strokeTopWeight','strokeRightWeight','strokeBottomWeight','strokeLeftWeight'].includes(b.property)) {
        node.setBoundVariable(b.property, variable);

      } else if (b.property.startsWith('padding.')) {
        const side = b.property.split('.')[1];
        const prop = 'padding' + side.charAt(0).toUpperCase() + side.slice(1);
        node.setBoundVariable(prop, variable);

      // --- Typography bindings (TEXT nodes) ---
      // All supported: fontFamily, fontWeight, fontStyle, fontSize, lineHeight, letterSpacing, paragraphSpacing
      } else if (['fontSize','fontFamily','fontWeight','fontStyle','lineHeight',
                   'letterSpacing','paragraphSpacing'].includes(b.property)) {
        node.setBoundVariable(b.property, variable);

      } else {
        console.warn(`Unhandled property: ${b.property} on node ${b.nodeId}`);
        failed++;
        continue;
      }
      bound++;
    } catch (e) {
      console.error(`Failed: ${b.nodeId} ${b.property}: ${e.message}`);
      failed++;
    }
  }

  figma.notify(`Rebound ${bound}/${bindings.length} properties (${failed} failures)`);
})();
```

**Figma Plugin API coverage — all bindable property types:**

| Property path | API method | Variable type |
|---|---|---|
| `fill.N.color` | `figma.variables.setBoundVariableForPaint(paint, 'color', var)` | COLOR |
| `stroke.N.color` | `figma.variables.setBoundVariableForPaint(paint, 'color', var)` | COLOR |
| `effect.N.color` | `figma.variables.setBoundVariableForEffect(effect, 'color', var)` | COLOR |
| `effect.N.radius` | `figma.variables.setBoundVariableForEffect(effect, 'radius', var)` | FLOAT |
| `effect.N.offsetX` | `figma.variables.setBoundVariableForEffect(effect, 'offsetX', var)` | FLOAT |
| `effect.N.offsetY` | `figma.variables.setBoundVariableForEffect(effect, 'offsetY', var)` | FLOAT |
| `effect.N.spread` | `figma.variables.setBoundVariableForEffect(effect, 'spread', var)` | FLOAT |
| `cornerRadius`, `topLeftRadius`, etc. | `node.setBoundVariable(field, var)` | FLOAT |
| `paddingTop/Right/Bottom/Left` | `node.setBoundVariable(field, var)` | FLOAT |
| `itemSpacing`, `counterAxisSpacing` | `node.setBoundVariable(field, var)` | FLOAT |
| `opacity` | `node.setBoundVariable('opacity', var)` | FLOAT |
| `fontSize` | `node.setBoundVariable('fontSize', var)` | FLOAT |
| `fontFamily` | `node.setBoundVariable('fontFamily', var)` | STRING |
| `fontWeight` | `node.setBoundVariable('fontWeight', var)` | FLOAT |
| `fontStyle` | `node.setBoundVariable('fontStyle', var)` | STRING |
| `lineHeight` | `node.setBoundVariable('lineHeight', var)` | FLOAT |
| `letterSpacing` | `node.setBoundVariable('letterSpacing', var)` | FLOAT |
| `paragraphSpacing` | `node.setBoundVariable('paragraphSpacing', var)` | FLOAT |
| `strokeWeight`, `stroke*Weight` | `node.setBoundVariable(field, var)` | FLOAT |

**Known limitations:**
- Gradient color stops cannot be bound to variables. Gradients are stored for code export only.
- `paragraphSpacing` and `paragraphIndent` only work on full text nodes, not text ranges.
- Noise, texture, and glass effects don't support variable binding.
- Paint variable binding only works on `SolidPaint`, not gradient paints.

**Batching:** ~500 bindings per script. For 230 screens × ~10 bindings/node × ~200 nodes = ~460K bindings total. That's ~920 scripts. Automated via Console MCP `figma_execute`.

**Verification:** After rebinding, run `figma_audit_design_system` to check token coverage score (should jump from 0 to >80).

## Data Model

See `schema.sql` (v0.2) for complete CREATE TABLE statements. 22 tables, 15 views, 27 indexes, 2 triggers.

**Key relationships:**
```
files 1──* screens 1──* nodes 1──* node_token_bindings *──1 tokens
files 1──* token_collections 1──* token_modes
files 1──* components 1──* component_variants
token_collections 1──* tokens 1──* token_values
tokens 1──* code_mappings
screens 1──* route_mappings
nodes *──? components (INSTANCE nodes reference component definitions)
tokens ?──? tokens (alias_of self-reference, depth 1 enforced by trigger)

Component model:
components 1──* variant_axes 1──* variant_dimension_values
components 1──* component_slots
components 1──1 component_a11y
components 1──* component_responsive
variant_axes ──* variant_dimension_values ──* component_variants

Operations:
extraction_runs 1──* screen_extraction_status *──1 screens
```

**Node tree:** `nodes.parent_id` → `nodes.id` forms a recursive tree. `nodes.path` provides materialized path for efficient subtree queries. Root nodes have `parent_id = NULL` and `path = '0'`, `'1'`, etc. `depth` is denormalized for level-based queries. `sort_order` preserves Figma's z-ordering within siblings.

**Binding lifecycle:**
```
[extraction]     unbound (token_id = NULL)
      │
[clustering]     proposed (token_id set, confidence scored)
      │
[curation]       bound (user approved) or unbound (user rejected)
      │
[validation]     export_validations checked — errors block Phase 7
      │
[figma export]   bound (figma_variable_id written back, sync_status = synced)
```

## Parallel Agent Coordination

Multiple agents (or Cowork sessions) may operate on the same DB. SQLite WAL mode allows concurrent reads and serialized writes.

**Locking protocol:**
1. Before writing to a shared resource, acquire a lock via `INSERT INTO extraction_locks`.
2. Lock `resource` naming: `"screen:{figma_node_id}"` for extraction, `"curation"` for token ops, `"export"` for Figma export.
3. Locks expire after 10 minutes (crash recovery). Agents check `expires_at` before honoring a lock.
4. Before acquiring, clean stale locks: `DELETE FROM extraction_locks WHERE expires_at < datetime('now')`.

**Parallel extraction:** Two agents can extract different screens simultaneously. Each claims screens via `screen_extraction_status`. The `in_progress` status + `started_at` timestamp acts as an implicit lock.

**Unsupported concurrency:** Curation and export are single-agent operations. The `"curation"` and `"export"` locks are exclusive.

## MCP Tool Usage Map

| Phase | Tool | MCP | Cost | Calls |
|---|---|---|---|---|
| 1. Inventory | `get_metadata` or `figma_get_file_data` | Official or Console | 1 call | 1 |
| 2. Screen extraction | `use_figma` | Official | Metered | ~230 |
| 3. Normalization | Local Python | None | Free | 0 |
| 4. Component extraction | `use_figma` | Official | Metered | ~5-10 |
| 5. Clustering | Local Python | None | Free | 0 |
| 6. Curation | Local DB queries | None | Free | 0 |
| 6.5 Validation | Local Python | None | Free | 0 |
| 7. Variable export | `figma_setup_design_tokens` | Console | Free | 1-3 |
| 8. Rebinding | `figma_execute` | Console | Free | ~920 |

**Total metered calls:** ~240 (one-time extraction cost).
**Total free calls:** Everything else, forever.

## Error Handling

**Extraction failures:**
- Screen-level checkpointing via `screen_extraction_status`. If extraction fails on screen 147, resume picks up from 147.
- `extracted_at` timestamps enable freshness comparison — stale screens can be re-extracted selectively.
- Idempotent writes — re-extracting a screen UPSERTs all rows (keyed on `screen_id + figma_node_id` for nodes, `node_id + property` for bindings).

**Figma state drift:**
- If the file is modified between extraction and rebinding, node IDs may shift.
- Mitigation: extract and rebind in the same session, or re-extract modified screens before rebinding.
- `sync_status = 'drifted'` on tokens when DB and Figma values diverge.

**Mixed text styles:**
- Figma TEXT nodes can have mixed styles (different fonts/sizes within one text box).
- `use_figma` returns `figma.mixed` for these. Store as `"MIXED"` in raw_value, skip binding creation. Flag for manual review.

**Instance opacity:**
- INSTANCE nodes don't expose their internals in standard tree reads.
- Strategy: detect instances, record `component_id` reference, but don't recurse into instance internals. The component definition (extracted in Phase 4) provides the canonical structure.

**Re-extraction data preservation:**
Re-running extraction on a previously-extracted file must not destroy curation work. Strategy:

1. **Before re-extraction:** Create a DB snapshot via `VACUUM INTO 'declarative_backup_{timestamp}.db'`.
2. **Nodes:** UPSERT keyed on `(screen_id, figma_node_id)`. Changed properties overwrite. New nodes inserted. Nodes that existed in DB but no longer exist in Figma are flagged `visible = 0` (soft delete), not removed — they may have bound tokens.
3. **Bindings:** For a re-extracted node, only bindings with `binding_status = 'unbound'` are overwritten. Bindings with status `proposed`, `bound`, or `overridden` are preserved. If a node's property value changed AND has a bound token, the binding is flipped to `binding_status = 'overridden'` and the new raw/resolved values are written, but `token_id` is kept — this surfaces drift for review.
4. **Tokens and token_values:** Never touched by re-extraction. These are curation-level artifacts.
5. **Screens:** UPSERT keyed on `(file_id, figma_node_id)`. Updated `extracted_at`. New screens added, deleted screens soft-deleted.
6. **Components:** UPSERT keyed on `(file_id, figma_node_id)`. Property changes update in place.

The key invariant: **re-extraction only writes to System and Composition tables, never to token-tier data.** The binding table is the bridge — re-extraction can add new unbound rows and flag drift on existing bound rows, but never removes or downgrades a bound binding.

## Performance Considerations

**DB write throughput:** SQLite WAL mode handles ~50K inserts/sec. 230 screens × 200 nodes × 15 bindings (increased due to effect decomposition) = ~690K bindings. Total DB write time: <15 seconds. Not a bottleneck.

**Memory:** Largest single response is ~37K chars (~37KB). Python process will hold at most one screen's data in memory. No memory concerns.

**Disk:** Estimated DB size for full Dank file: ~60MB (690K binding rows + 46K node rows + component model + metadata). Negligible.

**The actual bottleneck is Figma MCP round-trip time.** At ~4 sec/call × 240 calls = ~16 minutes. This is the cost of extraction and it's paid once.

## Agent Cookbook — Example Queries

These are the query patterns a coding agent or companion skill uses to consume the DB. Included here to prove the schema supports the required access patterns and as reference for the companion skill.

**1. Get all color tokens for code generation:**
```sql
SELECT t.name, vrt.resolved_value, vrt.mode_name
FROM v_resolved_tokens vrt
JOIN tokens t ON vrt.id = t.id
WHERE t.type = 'color' AND t.tier IN ('curated', 'aliased')
ORDER BY t.name, vrt.mode_name;
```

**2. Get a screen's full composition tree (for "build me the settings page"):**
```sql
-- Screen metadata
SELECT * FROM v_screen_summary WHERE name LIKE '%Settings%';

-- Full node tree with token bindings
SELECT n.path, n.name, n.node_type, n.is_semantic,
       n.layout_mode, n.width, n.height,
       ntb.property, ntb.resolved_value, t.name AS token_name
FROM nodes n
LEFT JOIN node_token_bindings ntb ON ntb.node_id = n.id AND ntb.binding_status = 'bound'
LEFT JOIN tokens t ON ntb.token_id = t.id
WHERE n.screen_id = ?
ORDER BY n.path;
```

**3. Get all components with their interaction states:**
```sql
SELECT c.name, c.category, c.composition_hint,
       va.axis_name, va.axis_values, va.default_value,
       cs.name AS slot_name, cs.slot_type, cs.is_required,
       ca.role, ca.min_touch_target
FROM components c
LEFT JOIN variant_axes va ON va.component_id = c.id
LEFT JOIN component_slots cs ON cs.component_id = c.id
LEFT JOIN component_a11y ca ON ca.component_id = c.id
WHERE c.file_id = ?
ORDER BY c.category, c.name, va.axis_name;
```

**4. Find all hover states across all components:**
```sql
SELECT c.name AS component_name, cv.name AS variant_name, cv.properties
FROM variant_dimension_values vdv
JOIN variant_axes va ON vdv.axis_id = va.id
JOIN component_variants cv ON vdv.variant_id = cv.id
JOIN components c ON cv.component_id = c.id
WHERE va.is_interaction = 1 AND vdv.value = 'hover';
```

**5. Get all tokens with usage counts (for curation review):**
```sql
SELECT * FROM v_token_coverage WHERE binding_count > 0;
```

**6. Pipeline status dashboard:**
```sql
SELECT * FROM v_curation_progress;
-- Returns: bound 72.3%, proposed 18.1%, overridden 0.4%, unbound 9.2%
```

**7. All descendants of a container node:**
```sql
SELECT * FROM nodes WHERE path LIKE '0.3.%' AND screen_id = ?
ORDER BY path;
```

**8. Find design inconsistencies (one-off values used only once):**
```sql
SELECT resolved_value, property, COUNT(*) as usage
FROM node_token_bindings
WHERE binding_status = 'unbound'
GROUP BY resolved_value, property
HAVING COUNT(*) = 1
ORDER BY property;
```

**9. Drift check — compare DB tokens against Figma:**
```sql
SELECT * FROM v_drift_report;
```

**10. Export readiness check:**
```sql
SELECT * FROM v_export_readiness;
-- Shows: mode_completeness: 0 errors, name_dtcg_compliant: 0 errors, orphan_tokens: 2 warnings
```

## Companion Skill

A companion skill (`declarative-design.md`) teaches Claude how to work with the Declarative Design DB. It's installed in `.claude/skills/` and loaded automatically when the agent encounters a `.declarative.db` file or is asked to compose/build using a design system.

**Skill responsibilities:**
1. **DB discovery.** On load, find the `.declarative.db` file, run `v_curation_progress` and `v_screen_summary` to understand the system's state, report health.
2. **Token resolution.** When composing code or Figma screens, query `v_resolved_tokens` for the correct token value per mode. Never hardcode values that have tokens.
3. **Component instantiation.** Query `v_component_catalog` to understand available components, their slots, interaction states, and a11y contracts. Use `composition_hint` for structural guidance.
4. **Screen composition.** When asked to "build the settings page," query the DB for the screen's composition tree (query #2 above), then recreate it using real components and real tokens.
5. **Curation assistance.** Walk the user through token proposals using `v_token_coverage`, `v_unbound`, and `v_curation_progress`. Offer rename/merge/split suggestions.
6. **Export orchestration.** Run validation (Phase 6.5), generate `figma_setup_design_tokens` payloads, execute rebinding scripts, verify via `figma_audit_design_system`.
7. **Disconnected mode.** If Figma is not running (Console MCP unavailable), the skill still works for code generation and DB queries — just not Figma export.

**Skill structure:**
- System context: DB location, schema version, table overview, view catalog
- Query patterns: all 10 cookbook queries above
- MCP tool mapping: which Console MCP / Official MCP tool to use for each operation
- Constraints: token naming conventions, binding property path format, mode completeness rules
- Workflows: extraction, clustering, curation, export, drift detection

The skill is authored after the first successful extraction (when we have real data to validate against).

## Implementation Order

1. **schema.sql** — Done (v0.2). 22 tables, 15 views, 27 indexes, 2 triggers. Validated.
2. **extract_inventory.py** — Phase 1. Populate `files` + `screens` + `extraction_runs`. ~30 min to build.
3. **extract_screens.py** — Phase 2 + 3. Iterate screens, extract nodes, compute materialized paths, normalize values, create bindings, decompose effects. ~3-4 hours to build, ~15 min to run.
4. **extract_components.py** — Phase 4. Parse component frames, populate component model tables (variants, axes, slots, a11y, responsive). ~2 hours to build.
5. **cluster_tokens.py** — Phase 5. Census queries + OKLCH clustering + token proposals + effect clustering. ~2 hours to build.
6. **validate_export.py** — Phase 6.5. Pre-export validation checks. ~1 hour to build.
7. **export_figma_variables.py** — Phase 7. Generate `figma_setup_design_tokens` payloads with multi-mode support. ~1 hour to build.
8. **generate_rebind_scripts.py** — Phase 8. Generate plugin scripts from bound bindings with full property coverage. ~1.5 hours to build.
9. **export_dtcg_json.py** — FR-4.6. Generate W3C DTCG tokens.json with resolver format. ~1.5 hours to build.
10. **declarative-design.md** — Companion skill. Authored after first extraction. ~2 hours.

**Total estimated build time:** ~15-17 hours across sessions.
**Total estimated run time (first extraction):** ~20 minutes.

## Open Design Decisions

1. **Curation interface:** CLI queries, Python TUI, or lightweight web UI (Flask/Streamlit)? CLI is fastest to build but worst for reviewing 200+ token proposals. Leaning toward a single-page React app reading from SQLite via a thin API.
2. **Rebinding strategy:** 920 plugin scripts via `figma_execute` is the current plan. Alternative: a single Figma plugin that reads the binding map from a JSON file served by a local HTTP server. The plugin approach would be one install + one run vs. 920 MCP calls. Worth building if the 920-call approach proves too slow.
3. **Incremental sync:** Currently designed as full-extraction. For ongoing maintenance, need a delta detection strategy. Options: compare `file.last_modified`, or hash node properties per screen and compare. Deferred until after first full extraction.
4. **Pattern extraction:** The `patterns` table exists but has no extraction pipeline. This is a Phase 2 feature — requires analyzing composition trees across screens to find recurring structural motifs. Worth building only after the first successful extraction proves the data model.
5. **Component slot inference quality:** Slot detection from component child structure is heuristic. May need manual curation for complex components. The richer test file will inform whether the heuristics are sufficient.
