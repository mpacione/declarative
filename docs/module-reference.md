# Module Reference — Complete Capability Inventory

> Every module in the system, what it does, its public API, and how it maps to the four-layer architecture. Updated 2026-04-06.

---

## Cross-Cutting: Property Registry

### dd/property_registry.py — Unified Property Registry
Single source of truth for all 58 Figma node properties. Every pipeline layer references this registry instead of maintaining ad-hoc property lists.

| Function | Purpose |
|----------|---------|
| `PROPERTIES` | Tuple of 48 `FigmaProperty` dataclass entries |
| `HANDLER` | Sentinel value for handler-emitted properties (see emit field) |
| `by_db_column(column)` | Look up property by DB column name |
| `by_figma_name(name)` | Look up property by Figma Plugin API name |
| `by_override_type(type)` | Look up property by instance override type |
| `by_override_field(field)` | Look up property by Figma overriddenFields name |
| `overrideable_properties()` | Properties with override_fields defined |

Each `FigmaProperty` maps: `figma_name` → `db_column` → `override_fields` → `category` → `value_type` → `override_type` → `default_value` → `emit`.

The `emit` field classifies each property's emission category:
- **Template** (`{"figma": "{var}.{figma_name} = {value};"}`) — simple scalar, type-aware formatting via `format_js_value()`
- **Handler** (`{"figma": HANDLER}`) — complex, dispatched to renderer's handler function
- **Deferred** (`{}` empty) — emitted in a different pipeline phase

**Used by**: extract_supplement.py (override JS generation), ir.py (query column list), generate.py (build_visual_from_db, emit_from_registry, override dispatch).

---

## Layer 1: Extraction (7 modules)

### Extraction Workflow
Two-step process covering all Figma properties:
```
dd extract <figma-url>              # Step 1: REST API — fast, reliable, ~90% of properties
dd extract-supplement --db <db>     # Step 2: Plugin API — componentKey, layoutPositioning, Grid
```

### dd/extract.py — Extraction Orchestrator
Coordinates screen extraction + component extraction + binding extraction. Entry point for the `dd extract` CLI command. Uses the REST API path via `figma_api.py`.

| Function | Purpose |
|----------|---------|
| `run_inventory(conn, file_key, file_name, frames)` | Discover screens in Figma file, create extraction run |
| `process_screen(conn, run_id, screen, file_key)` | Extract one screen's node tree |
| `complete_run(conn, run_id)` | Finalize extraction run |
| `process_components(conn, file_id, component_data)` | Extract components via `extract_components` module |

### dd/extract_screens.py — Plugin API Screen Extraction (29 tests)
Generates async Figma Plugin JS to walk node trees and extract 72 columns per node. Uses `getNodeByIdAsync` and `getMainComponentAsync` (Figma's async API).

| Function | Purpose |
|----------|---------|
| `generate_extraction_script(screen_node_id)` | Generate async JS that extracts full node tree |
| `parse_extraction_response(response)` | Normalize raw response, type-convert, handle JSON fields |
| `compute_is_semantic(nodes)` | Tag nodes as semantic vs. structural noise |
| `insert_nodes(conn, screen_id, nodes)` | Batch insert into `nodes` table with UPSERT |

**Captures**: fills, strokes, effects (JSON), corner radius, opacity, blend mode, layout mode, padding (4 sides), item spacing, counter axis spacing, alignment, sizing modes, layout_positioning, Grid properties (6 fields), font properties (8 fields), text content, constraints, rotation, clips_content, component_key, component_figma_id. Total: 72 columns.

### dd/extract_supplement.py — Supplemental Plugin API Extraction
Registry-driven extraction for Plugin API-only fields: `componentKey`, `layoutPositioning`, Grid properties, and **all instance overrides**. CLI: `dd extract-supplement`.

| Function | Purpose |
|----------|---------|
| `generate_supplement_script(screen_node_ids)` | Generate JS with registry-driven override checks (~40 properties from `dd/property_registry.py`) |
| `_build_override_js_checks()` | Generates JS code for all overrideable properties from the registry |
| `apply_supplement(conn, supplement_data)` | Registry-driven storage: stores any override type defined in the registry |
| `run_supplement(conn, execute_fn, batch_size, delay)` | **Orchestrator**: auto-batch, auto-retry on 64KB truncation, individual retry for failed screens |

**Override extraction**: Captures 17 override types (69,866 total across 204 screens): BOOLEAN, FILLS, STROKES, EFFECTS, CORNER_RADIUS, INSTANCE_SWAP, WIDTH, HEIGHT, OPACITY, LAYOUT_SIZING_H, ITEM_SPACING, PADDING_LEFT/RIGHT, PRIMARY_ALIGN, STROKE_WEIGHT, STROKE_ALIGN, TEXT. Registry-driven — adding a property to the registry automatically adds override extraction.

### dd/extract_bindings.py — Token Binding Extraction
Normalizes Figma node properties into token binding rows and manages binding lifecycle.

| Function | Purpose |
|----------|---------|
| `create_bindings_for_screen(conn, screen_id, force_renormalize)` | Normalize all node properties into binding rows |
| `insert_bindings(conn, bindings, force_renormalize)` | UPSERT bindings with status management |

**Normalization pipeline**: Uses `dd/normalize.py` functions to convert fills → `fill.N.color`, strokes → `stroke.N.color`, effects → `effect.N.color/radius/offset`, typography → `fontSize/fontFamily/fontWeight/lineHeight/letterSpacing`, spacing → `padding.top/right/bottom/left/itemSpacing`, radius → `cornerRadius` or per-corner.

### dd/extract_components.py — Component Discovery (BUILT, NOT RUN ON DANK)
Parses Figma COMPONENT_SET and COMPONENT nodes, extracts variants, infers slots, generates a11y contracts.

| Function | Purpose |
|----------|---------|
| `extract_components(conn, file_id, component_nodes)` | Main pipeline: parse → insert → a11y → variants → axes → dimension values → slots |
| `parse_component_set(component_set_data)` | Parse COMPONENT_SET with variants and axes |
| `parse_standalone_component(component_data)` | Parse single COMPONENT without variants |
| `infer_category(name)` | Keyword-match: button, input, nav, card, modal, icon, layout, chrome |
| `infer_slots(children)` | Infer slot definitions from child nodes, filter structural noise |
| `infer_slot_type(child)` | Classify child: text, icon, component, image, any |
| `infer_a11y(category, name)` | Generate accessibility contracts (role, label, touch target, ARIA props) |
| `insert_component(conn, file_id, data)` | UPSERT into `components` table |
| `insert_variants(conn, component_id, variants)` | UPSERT into `component_variants` |
| `insert_variant_axes(conn, component_id, axes)` | UPSERT into `variant_axes` with interaction detection |
| `populate_variant_dimension_values(conn, component_id)` | Cross-product: variant × axis → dimension values |
| `insert_slots(conn, component_id, slots)` | UPSERT into `component_slots` |
| `extract_slots_from_nodes(conn, component_id, figma_node_id)` | Query DB for child nodes, infer and insert slots |

**Populates**: `components`, `component_variants`, `variant_axes`, `variant_dimension_values`, `component_slots`, `component_a11y`. Currently ALL EMPTY in Dank DB — needs to be run.

**Slot inference heuristics**: Filters out structural noise (background, bg, divider, separator, spacer, line, border, overlay, shadow). Remaining children become slots with inferred types and sort order.

**Interaction detection**: Axis named "state" OR all values in {default, hover, focus, pressed, disabled, selected, loading} → marks as interaction axis.

### dd/normalize.py — Value Normalization (34 tests)
Converts Figma properties to normalized binding rows with hierarchical property names.

| Function | Properties | Output format |
|----------|-----------|---------------|
| `normalize_fill(fills)` | SOLID → `fill.N.color`, GRADIENT → `fill.N.gradient` + stops | property, raw_value (JSON), resolved_value (hex) |
| `normalize_stroke(strokes)` | SOLID → `stroke.N.color` | same |
| `normalize_effect(effects)` | SHADOW → `.color/.radius/.offsetX/.offsetY/.spread`, BLUR → `.radius` | same |
| `normalize_typography(node)` | fontSize, fontFamily, fontWeight, lineHeight, letterSpacing | same |
| `normalize_spacing(node)` | padding (4 sides), itemSpacing, counterAxisSpacing | same |
| `normalize_radius(corner_radius)` | cornerRadius (uniform) or topLeft/topRight/bottomLeft/bottomRight | same |
| `normalize_stroke_weight(node)` | strokeWeight (uniform) or per-side weights | same |
| `normalize_paragraph_spacing(node)` | paragraphSpacing | same |
| `normalize_font_style(node)` | fontStyle (skips "Regular") | same |

### dd/figma_api.py — Figma API Bridge (27 tests)
REST API wrapper + MCP bridge for Figma file access.

---

## Layer 2: Analysis (11 modules)

### dd/catalog.py — Component Type Catalog (50 tests)
48 canonical UI types with behavioral descriptions, aliases, recognition heuristics, organized by user-intent categories.

| Function | Purpose |
|----------|---------|
| `seed_catalog(conn)` | Insert/update all 48 types into `component_type_catalog` |
| `get_catalog(conn)` | Retrieve full catalog as list of dicts |
| `lookup_by_name(conn, name)` | Find catalog entry by canonical name or alias |

**Categories**: Actions, Selection & Input, Content & Display, Navigation, Feedback & Status, Containment & Overlay.

### dd/classify.py — Classification Orchestrator (64 tests)
Formal matching (name → alias index) + parent linkage.

| Function | Purpose |
|----------|---------|
| `build_alias_index(conn)` | Build name prefix → canonical type lookup from catalog aliases |
| `classify_formal(conn, screen_id)` | Match INSTANCE node names against alias index |
| `link_parent_instances(conn, screen_id)` | Walk node tree to set parent_instance_id on classifications |
| `run_classification(conn, screen_id)` | Full cascade: formal → heuristic → LLM (if configured) |

### dd/classify_rules.py — All Classification Rules
Single file containing every heuristic rule. Referenced by `classify_heuristics.py`.

| Function | Purpose |
|----------|---------|
| `is_system_chrome(name)` | Detect iOS/Safari/Android system UI (excluded from IR) |
| `is_generic_name(name)` | Detect auto-generated names ("Frame N", "Group N") |
| `rule_header(node, screen_width)` | Full-width, top position, horizontal layout → header |
| `rule_bottom_nav(node, screen_width, screen_height)` | Full-width, bottom position → bottom-nav |
| `rule_heading_text(node)` | TEXT with font size ≥ 20 → heading |
| `rule_body_text(node)` | TEXT with font size < 20 → text |
| `rule_generic_frame_container(node)` | Generic frame → container (ONLY if no fills/strokes/effects) |
| `_has_visual_properties(node)` | Check if node has fills, strokes, or effects |
| `apply_heuristic_rules(node, screen_width, screen_height)` | Apply all rules in priority order |

### dd/classify_heuristics.py — Heuristic Runner
Thin wrapper that applies `classify_rules.py` rules to unclassified nodes.

### dd/classify_llm.py — LLM Classification (14 tests)
Claude Haiku for ambiguous nodes. Prompt builder + response parser.

### dd/classify_vision.py — Vision Cross-Validation (8 tests)
Screenshot-based classification with retry/backoff for Figma API rate limits.

### dd/classify_skeleton.py — Skeleton Notation
Screen-level structural notation (`stack(header, scroll(content), bottom-nav)`).

### dd/cluster.py + dd/cluster_colors.py + dd/cluster_spacing.py + dd/cluster_typography.py + dd/cluster_misc.py — Token Clustering (38+ tests)
Groups raw extracted values into token proposals using perceptual similarity.

**Color clustering algorithm**:
1. Query unbound color bindings grouped by resolved_value
2. Group by OKLCH delta-E similarity (threshold 2.0 = JND)
3. Different alpha values never cluster together
4. Most-used color becomes group representative
5. Create token per group, assign bindings with confidence score
6. Confidence: `max(0.8, 1.0 - delta_e / 10)`

**Clustering types**: colors (delta-E), typography (font family + weight + size combinations), spacing (value ranges), radius (exact match), effects (shadow/blur parameters), opacity (value ranges).

### dd/modes.py — Mode Derivation (22 tests)
OKLCH-based dark mode, compact mode, and high-contrast mode generation.

| Function | Purpose |
|----------|---------|
| `create_dark_mode(conn, collection_id)` | Copy values → OKLCH lightness inversion (`L' = 1-L`, chroma clamped to 0.4) |
| `create_compact_mode(conn, collection_id, factor)` | Copy values → scale dimensions by factor (default 0.875 = 12.5% reduction) |
| `create_high_contrast_mode(conn, collection_id)` | Light colors brighter (`L * 1.2 + 0.1`), dark darker (`L * 0.6`), chroma boosted |
| `create_theme(conn, file_id, theme_name, transform)` | Apply transform across all collections in file |

**Color space**: OKLCH (perceptually uniform lightness). Manual conversion chain: sRGB → Linear RGB → XYZ D65 → OKLAB → OKLCH, with coloraide library as primary and manual fallback.

### dd/curate.py — Token Curation (31 tests)
Agent-driven refinement: rename, merge, split, alias, accept, reject tokens.

| Function | Purpose |
|----------|---------|
| `accept_token(conn, token_id)` | Promote to curated tier, bind proposed bindings |
| `accept_all(conn, file_id)` | Bulk accept all extracted tokens |
| `rename_token(conn, token_id, new_name)` | Rename with DTCG validation |
| `merge_tokens(conn, survivor_id, victim_id)` | Merge victim into survivor, reassign bindings |
| `split_token(conn, token_id, new_name, binding_ids)` | Split specific bindings to new token |
| `reject_token(conn, token_id)` | Revert bindings to unbound, delete token |
| `create_alias(conn, alias_name, target_token_id, collection_id)` | Create semantic alias pointing to another token |
| `convert_to_alias(conn, token_id, target_token_id)` | Convert valued token to alias |

**Token tier progression**: extracted → curated (after accept) → aliased (semantic names).
**Binding status progression**: unbound → proposed (clustering) → bound (accept) OR intentionally_unbound (defaults/gradients).

---

## Layer 3: Composition (1 module — needs refactoring)

### dd/ir.py — IR Generation (103 tests)
Transforms classified screen data + token bindings into CompositionSpec.

| Function | Purpose |
|----------|---------|
| `generate_ir(conn, screen_id)` | Main entry: query → build spec → serialize |
| `query_screen_for_ir(conn, screen_id)` | Fetch classified nodes, bindings, tokens from DB |
| `query_screen_visuals(conn, screen_id)` | Registry-driven: SELECTs 51 columns from property registry. Returns ALL visual, layout, text properties + bindings + instance overrides + child swaps for all nodes in a screen. Renderer's DB access path. |
| `_hoist_descendant_overrides(conn, ids, result)` | Hoists overrides from nested Mode 1 instances to their top-level ancestor, transforming `:self` to master-relative paths with deduplication. |
| `build_composition_spec(data)` | Assemble flat element map, wire parent→children, inject containers. Returns `_node_id_map` (element_id → node_id). |
| `map_node_to_element(node)` | Convert classified node to IR element (type, layout, visual, style, props) |
| `normalize_fills/strokes/effects/corner_radius` | Normalize Figma JSON to IR format with token binding overlay |

**Current state**: IR is thin — visual data read from DB by the generator via `query_screen_visuals` + `build_visual_from_db`. `query_screen_visuals` column list is registry-driven — automatically includes any property added to `dd/property_registry.py`.

---

## Layer 4: Rendering (6 modules)

### dd/compose.py — Prompt Composition (47 tests)
Composes a CompositionSpec from a component list using extracted templates.

| Function | Purpose |
|----------|---------|
| `compose_screen(components, templates)` | Build IR spec from component list with template layout defaults |
| `build_template_visuals(spec, templates)` | Map elements to template visual data with synthetic node IDs |
| `generate_from_prompt(conn, components, page_name)` | End-to-end: query_templates → compose → visuals → generate_figma_script |
| `validate_components(components, templates)` | Resolve type aliases then validate against templates, return warnings |
| `resolve_type_aliases(components, templates)` | Map unsupported types to existing templates (toggle→icon/switch, checkbox→icon/checkbox-empty, etc.) |
| `compare_generated_vs_ground_truth(conn, spec, screen_id)` | Diff generated spec vs real screen: element counts, type distributions, Mode 1/2 ratio |
| `collect_template_rebind_entries(spec, visuals)` | Collect variable rebind entries from template boundVariables |

### dd/prompt_parser.py — LLM Prompt Parsing (17 tests)
Parses natural language into component lists using Claude Haiku.

| Function | Purpose |
|----------|---------|
| `parse_prompt(prompt, client, catalog_types, system_prompt)` | Call Claude with catalog types, return component list |
| `prompt_to_figma(prompt, conn, client, page_name)` | End-to-end: enrich with screen patterns → parse → compose → render |
| `extract_json(text)` | Robust JSON extraction from LLM responses (code blocks, wrapping) |
| `build_project_vocabulary(conn, min_instances)` | Build variant name/key vocabulary for LLM system prompt injection |

### dd/screen_patterns.py — Screen Archetypes (7 tests)
Extracts common screen patterns from classified screens.

| Function | Purpose |
|----------|---------|
| `extract_screen_archetypes(conn, file_id)` | Cluster app screens by root component types, return ranked archetypes |
| `get_archetype_prompt_context(archetypes)` | Generate text block for LLM prompt enrichment |

### dd/templates.py — Template Extraction (16 tests)
Extracts component templates (structure + visual defaults) from classified instances.

| Function | Purpose |
|----------|---------|
| `extract_templates(conn, file_id)` | Compute mode templates per catalog type, populate component_templates table |
| `query_templates(conn)` | Fetch all templates keyed by catalog_type (with component_figma_id from registry) |
| `compute_mode_template(instances)` | Statistical mode for each field across instances |
| `build_component_key_registry(conn)` | Build unified component_key → figma_node_id registry (122 entries, 80% resolved) |
| `extract_child_composition(conn, file_id)` | Extract child composition patterns from parent→child relationships (139 entries) |

### dd/rebind_prompt.py — Token Rebinding for Prompt Screens (10 tests)
Bridges generation pipeline to existing rebind infrastructure.

| Function | Purpose |
|----------|---------|
| `query_token_variables(conn)` | Fetch token name → Figma variable ID mapping |
| `build_rebind_entries(token_refs, figma_node_map, token_variables)` | Convert token_refs + M dict to rebind entries |
| `build_template_rebind_entries(template_entries, figma_node_map)` | Convert template boundVariable data + M dict to rebind entries |
| `generate_rebind_script(entries)` | Generate compact pipe-delimited rebind JS |

### dd/generate.py — Figma Generation (81 tests)
Generates Figma Plugin API JavaScript from CompositionSpec + DB visuals. Mode 1 (component instances via getNodeByIdAsync) for keyed components, Mode 2 (createFrame + L0 properties) for keyless types.

**Key patterns:**
- **Progressive fallback**: DB visuals → IR layout → heuristic fallback for every property
- **Deferred positioning**: position + constraints + non-auto-layout layoutSizing set after all appendChild calls
- **Default clearing**: fills=[], clipsContent=false explicitly set to override Figma createFrame() defaults
- **Mode 1 L0 properties**: rotation (radians→degrees), opacity, visibility applied after createInstance()
- **Generic override handler**: Registry-defined override types dispatched automatically via `dd/property_registry.py`
- **17 override types**: TEXT, BOOLEAN, FILLS, STROKES, EFFECTS, CORNER_RADIUS, INSTANCE_SWAP, WIDTH, HEIGHT, OPACITY, LAYOUT_SIZING_H/V, ITEM_SPACING, PADDING_LEFT/RIGHT, PRIMARY_ALIGN, STROKE_WEIGHT, STROKE_ALIGN

| Function | Purpose |
|----------|---------|
| `generate_figma_script(spec, db_visuals, page_name)` | Walk IR, emit JS. `db_visuals` drives visual/layout from DB. |
| `generate_screen(conn, screen_id)` | Orchestrate: generate_ir → query_screen_visuals → generate_figma_script |
| `build_visual_from_db(node_visual)` | Registry-driven: iterates PROPERTIES to map db_column → figma_name, applies `_apply_db_transform` (radians→degrees, int→bool, JSON parse), bundles text into font dict, constraints into constraints dict |
| `emit_from_registry(var, eid, visual, tokens)` | Registry-driven emission: dispatches HANDLER properties to `_FIGMA_HANDLERS`, formats template properties via `format_js_value()`. Returns (lines, token_refs) |
| `format_js_value(value, value_type)` | Type-aware JS value formatter: boolean→true/false, enum/string→"quoted", json→serialized, number→string |
| `_emit_layout(var, eid, layout, tokens)` | Emit layoutMode, padding, sizing (auto-layout containers only — non-auto-layout deferred) |
| `_emit_visual(var, eid, visual, tokens)` | Delegates to `emit_from_registry` — all logic in registry |
| `_emit_fills/strokes/effects(...)` | Handler functions for complex JSON paint/effect arrays |
| `_emit_corner_radius_figma(...)` | Handler for uniform (number) vs per-corner (dict) radius |
| `_emit_clips_content_figma(...)` | Handler for JS boolean emission + always-emit behavior |
| `_emit_text_props(var, element, style, tokens, lines)` | Emit fontName, fontSize, characters, text alignment, decoration, spacing (progressive fallback) |
| `collect_fonts(spec)` | Collect unique (family, style) pairs for font loading |

### dd/export_figma_vars.py — Figma Variable Export (50 tests)
Push tokens to Figma as variables.

| Function | Purpose |
|----------|---------|
| `query_exportable_tokens(conn, file_id)` | Get curated/aliased tokens ready for export |
| `generate_variable_payloads(conn, file_id)` | Generate `figma_setup_design_tokens` action payloads (batched at 100) |
| `writeback_variable_ids(conn, file_id, figma_variables)` | Write Figma variable IDs back to DB after creation |
| `map_token_type_to_figma(token_type, token_name)` | Map DTCG type → Figma variable type (COLOR/FLOAT/STRING) |

### dd/export_rebind.py — Rebind Script Generation (55 tests)
Generate compact JavaScript that binds 182K node properties to Figma variables.

| Function | Purpose |
|----------|---------|
| `generate_rebind_scripts(conn, file_id)` | Generate all rebind scripts (batched at 950 bindings per script) |
| `query_bindable_entries(conn, file_id)` | Query bindings with bound status and variable IDs |
| `generate_compact_script(entries)` | Compact pipe-delimited encoding (~60% size reduction) |
| `generate_single_script(entries)` | Verbose format for debugging |
| `get_rebind_summary(conn, file_id)` | Statistics: total bindings, script count, by property type |
| `classify_property(property_path)` | Categorize: paint_fill, paint_stroke, effect, padding, direct |
| `encode_property(property_path)` | Shortcode: fill.0.color → "f0", fontSize → "fs", padding.top → "pt" |

**Batching**: 950 bindings per script, ~191 scripts for 182K bindings. Compact format fits 1500 bindings in 50K chars.

### dd/push.py — Push Orchestrator (36 tests)
Coordinates variable creation + rebinding.

| Function | Purpose |
|----------|---------|
| `generate_push_manifest(conn, file_id, figma_state, phase)` | Generate complete push manifest (variables + rebind phases) |
| `generate_variable_actions(conn, file_id, figma_state)` | Generate CREATE/UPDATE/DELETE actions for Figma variables |
| `convert_value_for_figma(value, figma_type, is_opacity)` | Type-convert DB values to Figma-native (opacity 0-1 → 0-100, strip "px", etc.) |

### dd/export_css.py — CSS Export (46 tests)
Token export to CSS custom properties.

### dd/export_tailwind.py — Tailwind Export
Token export to Tailwind config format.

### dd/export_dtcg.py — DTCG Export
Token export to W3C Design Token Community Group format.

---

## Supporting Infrastructure (8 modules)

### dd/color.py — Color Conversions (28 tests)
| Function | Purpose |
|----------|---------|
| `rgba_to_hex(r, g, b, a)` | RGBA floats → 6 or 8 digit hex |
| `hex_to_rgba(hex_color)` | Hex → RGBA floats (supports #RGB, #RRGGBB, #RRGGBBAA) |
| `hex_to_oklch(hex_color)` | Hex → OKLCH (Lightness, Chroma, Hue) via coloraide or manual |
| `oklch_delta_e(color1, color2)` | Perceptual distance (delta-E in OKLAB space, scaled ×100) |
| `oklch_invert_lightness(L, C, h)` | Invert L, clamp C for dark mode |

### dd/drift.py — Drift Detection (28 tests)
| Function | Purpose |
|----------|---------|
| `detect_drift(conn, file_id, figma_response)` | Full drift detection: parse → compare → update sync statuses → report |
| `compare_token_values(conn, file_id, figma_variables)` | Compare DB vs Figma values with type-aware normalization |
| `normalize_value_for_comparison(value, token_type)` | Handle JSON dimensions, Figma float noise, hex formats |

### dd/validate.py — Validation (20 tests)
8 validation checks that block export if errors found.

| Check | Severity | What |
|-------|----------|------|
| Mode completeness | ERROR | Every token has value for every mode |
| DTCG name compliance | ERROR | Token names match pattern |
| Orphan tokens | WARNING | Tokens with zero bindings |
| Binding coverage | INFO | % bound / proposed / unbound |
| Alias targets curated | ERROR | Aliases point to curated tokens |
| Name uniqueness | ERROR | No duplicate names in collection |
| Value format | ERROR | Colors are valid hex, dimensions are numbers |
| Binding-token consistency | WARNING | Bound binding values match token values |

### dd/db.py — Database Management
Schema initialization from `schema.sql`, connection management, WAL mode.

### dd/cli.py — CLI Commands (19 tests)
Entry points: extract, cluster, accept-all, validate, export, push, status, classify, generate-ir, seed-catalog, maintenance.

### dd/status.py — Status Reporting (18 tests)
Dashboard data: token counts by tier, binding coverage, sync status summary.

### dd/config.py — Configuration
Paths, thresholds, API limits. `SCHEMA_PATH`, `USE_FIGMA_CODE_LIMIT`.

### dd/types.py — Constants
`NON_SEMANTIC_PREFIXES`, `SEMANTIC_NODE_TYPES` — filtering heuristics for extraction.
