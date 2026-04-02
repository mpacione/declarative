# Module Reference — Complete Capability Inventory

> Every module in the system, what it does, its public API, and how it maps to the four-layer architecture. Generated 2026-04-02 from deep code analysis.

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
Targeted extraction for Plugin API-only fields: `componentKey`, `layoutPositioning`, and Grid properties. CLI: `dd extract-supplement`.

| Function | Purpose |
|----------|---------|
| `generate_supplement_script(screen_node_ids)` | Generate compact JS for batch screen extraction (only non-default values) |
| `apply_supplement(conn, supplement_data)` | Update nodes table with supplemental data from compact format |
| `run_supplement(conn, execute_fn, batch_size, delay)` | **Orchestrator**: auto-batch, auto-retry on 64KB truncation, individual retry for failed screens |

**Auto-batching**: Default 5 screens per call. On 64KB response truncation, halves batch size and retries. Falls back to individual screen extraction for persistent failures.

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

### dd/ir.py — IR Generation (64 tests)
Transforms classified screen data + token bindings into CompositionSpec.

| Function | Purpose |
|----------|---------|
| `generate_ir(conn, screen_id)` | Main entry: query → build spec → serialize |
| `query_screen_for_ir(conn, screen_id)` | Fetch classified nodes, bindings, tokens from DB |
| `build_composition_spec(data)` | Assemble flat element map, wire parent→children, inject containers |
| `map_node_to_element(node)` | Convert classified node to IR element (type, layout, visual, style, props) |
| `normalize_fills(raw_json, bindings)` | Normalize Figma fills JSON to IR fill array |
| `normalize_strokes(raw_json, bindings, node)` | Normalize Figma strokes JSON to IR stroke array |
| `normalize_effects(raw_json, bindings)` | Normalize Figma effects JSON to IR effect array |
| `normalize_corner_radius(raw_value)` | Normalize to number or per-corner dict |

**Current state**: IR is too thick — carries visual properties (fills, strokes, effects) that should be in DB/renderer. Semantic tree construction (200→20 elements) not implemented. Slot filling not implemented. These are the key items for the thin IR refactor.

---

## Layer 4: Rendering (6 modules)

### dd/generate.py — Figma Generation (51 tests)
Generates Figma Plugin API JavaScript from CompositionSpec.

| Function | Purpose |
|----------|---------|
| `generate_figma_script(spec)` | Walk IR, emit JS for frame/text creation, layout, visual properties |
| `generate_screen(conn, screen_id)` | Orchestrate: generate_ir → generate_figma_script |
| `_emit_layout(var, eid, layout, tokens)` | Emit layoutMode, padding, sizing, alignment |
| `_emit_visual(var, eid, visual, tokens)` | Emit fills, strokes, effects, cornerRadius, opacity |
| `_emit_fills(var, eid, fills, tokens)` | Emit Figma paint array from IR fills |
| `_emit_strokes(var, eid, strokes, tokens)` | Emit Figma stroke array |
| `_emit_effects(var, eid, effects, tokens)` | Emit Figma effects array |
| `_emit_text_props(var, element, style, tokens, lines)` | Emit fontName, fontSize, characters |
| `collect_fonts(spec)` | Collect unique (family, style) pairs for font loading |
| `hex_to_figma_rgb(hex_str)` | Convert hex → Figma {r, g, b} dict |
| `resolve_style_value(value, tokens)` | Resolve token ref or pass through literal |
| `font_weight_to_style(weight)` | Map numeric weight → Figma style name ("Semi Bold", etc.) |

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
