# Module Reference — Complete Capability Inventory

> Every module in the system, what it does, its public API, and how it maps to the four-layer architecture.
> Reference document — for a high-level introduction see the [repo README](../README.md), for the architecture spec see [`compiler-architecture.md`](compiler-architecture.md).
> Updated 2026-04-22.
>
> **Body currency notice**: the Layer 1–4 sections below describe the
> M4-era extraction pipeline accurately (and those modules remain in
> use). Modules added during M5–M7 sprints are inventoried in the new
> [§ v0.3 Pipeline Additions (M5–M7)](#v03-pipeline-additions-m5m7)
> section at the end of this doc — add-then-merge rather than a full
> rewrite, to avoid churning stable content.
>
> - **Renamed**: `dd/m7_slots.py` → `dd/slots.py` (M7.0.b slot derivation),
>   `dd/m7_variants.py` → `dd/variants.py` (M7.0.c variant family
>   derivation). All scripts `scripts/m7_*.py` → `scripts/*.py`.
> - **Pending deprecation per `docs/DEPRECATION.md`**: `dd/markup.py`
>   (vestigial pre-grammar serializer; tied to M6(b) gate),
>   `dd/ir.py::generate_ir / build_composition_spec / query_screen_visuals`
>   (replaced by `derive_markup` + on-demand DB lookups inside
>   `render_figma`), `dd/renderers/figma.py::generate_figma_script`
>   (replaced by `render_figma`).
> - **2026-04-22 additions**: type/role split — `dd/ir.py` now emits
>   `{type (primitive), role (optional semantic)}`; grammar carries
>   `role=` as head PropAssign. `nodes.role` column via migration 021.
>   See [`plan-type-role-split.md`](plan-type-role-split.md).
>
> For current-truth module inventory beyond what's captured here, use
> code-graph MCP (`code-graph-mcp map`) or grep.

---

## Cross-Cutting: Property Registry

### dd/property_registry.py — Unified Property Registry
Single source of truth for all Figma node properties. Every pipeline layer references this registry instead of maintaining ad-hoc property lists.

| Function | Purpose |
|----------|---------|
| `PROPERTIES` | Tuple of `FigmaProperty` dataclass entries (with `token_binding_path` for binding awareness). Includes `isMask` boolean property for mask nodes. |
| `HANDLER` | Sentinel value for handler-emitted properties (see emit field) |
| `by_db_column(column)` | Look up property by DB column name |
| `by_figma_name(name)` | Look up property by Figma Plugin API name |
| `by_override_type(type)` | Look up property by instance override type |
| `by_override_field(field)` | Look up property by Figma overriddenFields name |
| `overrideable_properties()` | Properties with override_fields defined |

Each `FigmaProperty` maps: `figma_name` → `db_column` → `override_fields` → `category` → `value_type` → `override_type` → `default_value` → `emit` → `token_binding_path`.

The `emit` field classifies each property's emission category:
- **Template** (`{"figma": "{var}.{figma_name} = {value};"}`) — simple scalar, type-aware formatting via `format_js_value()`
- **Handler** (`{"figma": HANDLER}`) — complex, dispatched to renderer's handler function
- **Deferred** (`{}` empty) — emitted in a different pipeline phase

**Used by**: extract_supplement.py (override JS generation), ir.py (query column list), generate.py (build_visual_from_db, emit_from_registry, override dispatch).

---

## Layer 1: Extraction

### Extraction Workflow
Two-step process covering all Figma properties:
```
dd extract <figma-url>              # Step 1: REST API via boundary adapter (ADR-006).
                                    #   75% of properties. REST `components` map
                                    #   now populates `component_key` at ingest
                                    #   time — no Plugin-API round-trip needed
                                    #   for that field.
dd extract-plugin --port <N>        # Step 2: Unified Plugin-API pass (pt 6).
                                    #   Single walker, two slices (light + heavy),
                                    #   replaces the five legacy passes.
                                    #   Post-processes: rebuilds content-addressed
                                    #   SVG asset store + CKR.
```

The legacy commands `dd extract-supplement` and `python -m dd.extract_targeted --mode {properties,sizing,transforms,vector-geometry}` are preserved for incremental re-extraction after a schema change (they re-populate a single field set without re-running the entire Plugin pipeline).

### dd/extract.py — Extraction Orchestrator
Coordinates screen extraction + component extraction + binding extraction. Entry point for the `dd extract` CLI command. Uses the REST API path via `figma_api.py`.

| Function | Purpose |
|----------|---------|
| `run_inventory(conn, file_key, file_name, frames)` | Discover screens in Figma file, create extraction run |
| `process_screen(conn, run_id, screen, file_key)` | Extract one screen's node tree |
| `complete_run(conn, run_id)` | Finalize extraction run |
| `process_components(conn, file_id, component_data)` | Extract components via `extract_components` module |

### dd/boundary.py — ADR-006 Boundary Contract
Backend-neutral protocols and structured-error vocabulary for every external-system edge. Defines `IngestAdapter`, `ResourceProbe`, `StructuredError`, `IngestResult`, `FreshnessReport`, and the `KIND_*` constants. Every frontend must implement `IngestAdapter` to participate in the pipeline; the contract's honest summary (requested / succeeded / failed counts matching `errors[]`) is the invariant downstream stages rely on.

### dd/ingest_figma.py — ADR-006 Figma Adapter
Figma-specific instantiation of the boundary protocols.

| Class | Purpose |
|----------|---------|
| `FigmaIngestAdapter` | `extract_screens(ids)` → `IngestResult`. Auto-batches at ≤10 ids/call. Parallelism via `max_workers` constructor arg (default 1 — Figma's 429 limiter serializes parallel workers via backoff on moderate files; opt in for smaller files or higher API tiers). |
| `FigmaResourceProbe` | `probe(ids)` → `FreshnessReport`. Classifies as valid / missing / unknown. |

Structured-error kinds emitted: `KIND_API_ERROR` (network / 5xx), `KIND_NODE_NOT_FOUND` (API returned null for id), `KIND_MALFORMED_RESPONSE` (missing required keys). None raise exceptions; all are aggregated into the return `IngestResult`.

### dd/extract_plugin.py — Unified Plugin-API Extraction (pt 6)
Single-walker replacement for the 5-pass legacy Plugin-API pipeline. Collects every Plugin-only field set in two tree-walk slices.

| Function | Purpose |
|----------|---------|
| `generate_plugin_script(ids, slice="all")` | Emit JS walker. Slice controls payload size: `light` (layout flags, grid, overrides, mask/bool/arc, typography strings, gradient enrichment), `heavy` (relativeTransform per node, vectorPaths, fillGeometry/strokeGeometry, OpenType segments), or `all`. |
| `apply_plugin(conn, data)` | Dispatch walker output to target columns via the existing `apply_supplement` / `apply_targeted` / `apply_sizing` / `apply_transforms` / `apply_vector_geometry` functions. Reuse, not rewrite. |
| `run_plugin_extract(conn, execute_fn, ...)` | Orchestrator: runs light slice then heavy slice; auto-halves batch on script-size truncation; runs `process_vector_geometry(conn)` at the end to rebuild the content-addressed SVG asset store. |

Why two slices instead of one: a single unified walk exceeded Figma's ~64 KB PROXY_EXECUTE result buffer on moderate screens. The light slice's small per-node payload fits in the buffer; the heavy slice (relativeTransform for every node, per-vector geometries) needs a smaller batch size to fit.

Critical secondary fix landed alongside: the Node.js runner's `console.log(JSON.stringify(msg)); process.exit(0)` pattern silently truncated at the macOS 64 KB pipe buffer (process.exit doesn't flush stdout). Replaced with `process.stdout.write(..., callback)`. Applied to the legacy supplement runner too.

### dd/extract_screens.py — Plugin API Screen Extraction (36 tests)
Generates async Figma Plugin JS to walk node trees and extract 72 columns per node. Uses `getNodeByIdAsync` and `getMainComponentAsync` (Figma's async API).

| Function | Purpose |
|----------|---------|
| `generate_extraction_script(screen_node_id)` | Generate async JS that extracts full node tree |
| `parse_extraction_response(response)` | Normalize raw response, type-convert, handle JSON fields |
| `compute_is_semantic(nodes)` | Tag nodes as semantic vs. structural noise |
| `insert_nodes(conn, screen_id, nodes)` | Batch insert into `nodes` table with UPSERT |

**Captures**: fills, strokes, effects (JSON), corner radius, opacity, blend mode, layout mode, padding (4 sides), item spacing, counter axis spacing, alignment, sizing modes, layout_positioning, Grid properties (6 fields), font properties (8 fields), text content, constraints, rotation, clips_content, fillGeometry, strokeGeometry, component_key, component_figma_id. Total: 74 columns.

### dd/extract_supplement.py — Supplemental Plugin API Extraction
Registry-driven extraction for Plugin API-only fields: `componentKey`, `layoutPositioning`, Grid properties, and **all instance overrides**. CLI: `dd extract-supplement`.

| Function | Purpose |
|----------|---------|
| `generate_supplement_script(screen_node_ids)` | Generate JS with registry-driven override checks (~40 properties from `dd/property_registry.py`) |
| `_build_override_js_checks()` | Generates JS code for all overrideable properties from the registry |
| `override_suffix_for_type(property_type)` | Returns `(suffix, figma_name)` for a given override type. Single source of suffix knowledge — used by `decompose_override()` in ir.py |
| `apply_supplement(conn, supplement_data)` | Registry-driven storage: stores any override type defined in the registry |
| `run_supplement(conn, execute_fn, batch_size, delay)` | **Orchestrator**: auto-batch, auto-retry on 64KB truncation, individual retry for failed screens |

**Override extraction**: Captures 42 override types (69,866 total across 204 screens). Registry-driven — adding a property to the registry with `override_fields` automatically adds override extraction. Override `property_name` in DB is composite `{target}{suffix}`, decomposed at query time by `decompose_override()` in `ir.py`.

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

### dd/figma_api.py — Figma API Bridge
REST API wrapper + MCP bridge for Figma file access.

| Function | Purpose |
|----------|---------|
| `_request_with_retry(method, url, **kwargs)` | GET/POST with 429 handling. Exponential backoff (initial 2 s, up to 8 attempts), **jittered** to ±50% so concurrent workers don't re-sync their retries and re-trip the limiter. Honours `Retry-After` header. |
| `get_file_tree(file_key, token, page_id, depth)` | `/v1/files/:key` or `/v1/files/:key/nodes`. Returns JSON including the `components` map. |
| `get_screen_nodes(file_key, token, screen_ids)` | `/v1/files/:key/nodes?ids=...`. Returns `{nodes: {id: {document, components, ...}}}`. |
| `extract_top_level_frames(file_json, page_id, from_nodes_endpoint)` | Top-level FRAME / COMPONENT / COMPONENT_SET list. |
| `convert_node_tree(api_node, ..., components_map)` | Recursive node → extraction-format conversion. **Perf pt 6 #2**: when `components_map` is supplied, INSTANCE nodes resolve `componentId` → `component_key` at ingest time (no Plugin-API round-trip needed). |
| `_reconstruct_logical_dimensions(w, h, rot)` | Inverts AABB envelope back to logical dims for rotated nodes. |

### dd/extract_assets.py — Asset Extraction & Resolution (20 tests)
Content-addressed asset pipeline for raster images and SVG vector paths.

| Function | Purpose |
|----------|---------|
| `extract_image_hashes_from_db(conn)` | Scan fills JSON for IMAGE type, return unique hashes |
| `store_asset(conn, hash, kind, ...)` | INSERT OR IGNORE into assets table |
| `link_node_asset(conn, node_id, asset_hash, role, fill_index)` | Link node to asset via node_asset_refs |
| `process_vector_geometry(conn)` | Hash fill/stroke geometry from nodes, create svg_path assets with links |
| `AssetResolver` (ABC) | Abstract interface: `resolve(hash)` → asset dict, `resolve_batch(hashes)` → dict of assets |
| `SqliteAssetResolver` | Local DB implementation — queries assets table with metadata JSON parsing |

**Asset kinds**: `raster` (Figma IMAGE fills), `svg_path` (vector geometry paths), `svg_doc` (full SVG documents).
**Content addressing**: SHA-256 of `"{windingRule}:{path}"` concatenated with `;`. Identical paths share one asset row.

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
| `is_synthetic_node(name)` | Detect platform implementation artifacts — parenthesized Figma internal names like `(Auto Layout spacer)`, `(Adjust Auto Layout Spacing)`. Does NOT match system chrome (keyboards, status bars are design content). |
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

### dd/ir.py — IR Generation (110+ tests)
Transforms classified screen data + token bindings into CompositionSpec.

| Function | Purpose |
|----------|---------|
| `generate_ir(conn, screen_id)` | Main entry: query → build spec → serialize |
| `query_screen_for_ir(conn, screen_id)` | Fetch classified nodes, bindings, tokens from DB |
| `query_screen_visuals(conn, screen_id)` | Registry-driven: SELECTs all registry columns + x/y. Returns visual, layout, text properties + bindings + decomposed instance overrides + `_asset_refs` (from node_asset_refs JOIN assets). Builds `override_tree` (nested tree replacing flat overrides + child_swaps). Renderer's DB access path. |
| `decompose_override(property_type, property_name)` | Splits composite DB `property_name` into `(target, figma_property_name)` using suffix knowledge from extraction. |
| `_hoist_descendant_overrides(conn, ids, result)` | Hoists overrides from nested Mode 1 instances to their top-level ancestor, transforming `:self` to master-relative paths with deduplication. |
| `build_override_tree(instance_overrides, child_swaps)` | Converts flat override lists + child_swaps into nested tree structure. Tree nesting encodes dependency ordering (swaps before descendant property overrides). Semicolon-delimited paths parsed, intermediate ancestors created. |
| `build_composition_spec(data)` | Assemble flat element map, wire parent→children, inject containers. Filters synthetic nodes (parenthesized Figma internals) and their children via transitive closure. Propagates `screen_name` as `_original_name` on root element. Returns `_node_id_map` (element_id → node_id). |
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

### dd/visual.py — Shared Visual Infrastructure
Renderer-agnostic visual dict builder and layout sizing resolution. Any renderer imports from here.

| Function | Purpose |
|----------|---------|
| `build_visual_from_db(node_visual)` | Registry-driven: maps db_column → figma_name, applies `_apply_db_transform` (int→bool, JSON parse). Produces renderer-agnostic visual dict (hex colors, numeric weights, radians). Populates `_token_refs` sidecar from bindings via `token_binding_path`. |
| `_apply_db_transform(value, prop)` | Universal transforms only — int→bool, JSON string parse. No renderer-specific transforms. |
| `resolve_style_value(value, tokens)` | Resolve token references (`"{color.primary}"` → hex value). |
| `_resolve_layout_sizing(...)` | Pure function: DB > text reconciliation (`_TEXT_AUTO_RESIZE_SIZING`) > IR sizing > platform default (FIXED). No heuristic inference. Returns semantic lowercase ("fill", "hug", "fixed"). Ground-truth sizing from DB extraction (79,833 nodes). |

### dd/renderers/figma.py — Figma Plugin API Renderer
Generates Figma Plugin API JavaScript. All platform-specific transforms live here.

**Key patterns:**
- **Three-phase rendering**: Materialize (create nodes, intrinsic properties) → Compose (appendChild, layoutSizing) → Hydrate (text characters, position/constraints). Each phase has single responsibility. Eliminates Figma Plugin API ordering bugs structurally.
- **Progressive fallback**: DB visuals → IR layout → platform default for every property
- **layoutSizing at lowering**: Emitted post-appendChild when parent context is known. Never during frame creation. IR stores sizing intent unconditionally.
- **Default clearing**: fills=[], clipsContent=false to override Figma createFrame() defaults
- **42 override types**: Decomposed at query time into `{target, property, value}`. `_emit_override_op` uses `format_js_value` for generic properties.
- **Vector-aware skip**: VECTOR/BOOLEAN_OPERATION nodes check `_asset_refs` — render with `createVector()` + `vectorPaths` if asset data present, skip if not
- **IMAGE fill emission**: `imageHash` + `scaleMode` paint entries for raster assets
- **Font style ground-truth**: `db_font_style` from Plugin API used directly, normalized per family via bidirectional `normalize_font_style`
- **Rotation sign**: REST API radians → Plugin API degrees with sign negation (`-math.degrees(value)`)

| Function | Purpose |
|----------|---------|
| `generate_figma_script(spec, db_visuals, page_name)` | Walk IR, emit JS. Main entry point. |
| `generate_screen(conn, screen_id)` | Orchestrate: generate_ir → query_screen_visuals → generate_figma_script |
| `format_js_value(value, value_type)` | Type-aware JS formatting: boolean→true/false, enum→"quoted", number_radians→degrees, json→serialized. |
| `hex_to_figma_rgba(hex_str)` | Hex color → `{r, g, b, a}` floats (0-1). Preserves alpha. |
| `emit_from_registry(var, eid, visual, tokens)` | Registry dispatch: HANDLER → `_FIGMA_HANDLERS`, template → `format_js_value`. |
| `font_weight_to_style(weight)` | Numeric 600 → Figma style name "Semi Bold". |
| `normalize_font_style(family, style)` | Per-family style naming (SF Pro → "Semibold", Inter → "Semi Bold"). |
| `collect_fonts(spec, db_visuals)` | Collect (family, style) pairs for `loadFontAsync` preamble. |
| `_emit_override_tree(tree, var, lines, ...)` | Recursive pre-order walk of override tree. Emits swaps before descendant property overrides. Correct ordering for imperative renderers. |
| `_collect_swap_targets_from_tree(tree)` | Collect component IDs from override tree swap nodes for pre-fetch preamble (`getNodeByIdAsync` deduplication). |
| `_emit_layout/visual/fills/strokes/effects/text_props` | Figma JS emission for each property category. |
| `_emit_vector_paths(var, raw_visual, lines)` | Emit `vectorPaths` from asset ref SVG data for vector nodes. |

### dd/generate.py — Backward-Compatible Re-exports
Thin wrapper re-exporting from `dd.visual` and `dd.renderers.figma`. Existing imports continue to work. New code should import from the specific modules directly.

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

## Verification — ADR-007

### dd/verify_figma.py — RenderVerifier (ADR-007 Position 3)
Post-render verification. Walks a rendered subtree payload (produced by `render_test/walk_ref.js`) and diffs against the IR node-by-node.

| Function / Class | Purpose |
|----------|---------|
| `FigmaRenderVerifier` | Backend-specific verifier. `verify(spec, rendered_ref) → RenderReport`. |
| `RenderReport` | `{backend, ir_node_count, rendered_node_count, is_parity, parity_ratio(), errors[]}`. |
| Error kinds emitted | `KIND_DEGRADED_TO_MODE2`, `KIND_CKR_UNBUILT`, `KIND_BOUNDS_MISMATCH`, `KIND_FILL_MISMATCH`, `KIND_STROKE_MISMATCH`, `KIND_EFFECT_MISSING`, `KIND_MISSING_ASSET`, `KIND_OPENTYPE_UNSUPPORTED`, `KIND_GRADIENT_TRANSFORM_MISSING`, `KIND_COMPONENT_MISSING`, plus per-op runtime kinds (`text_set_failed`, `resize_failed`, `position_failed`, `constraint_failed`, ...). |

`is_parity = True` iff every IR node has a matching rendered node with matching structural and visual properties AND zero structured errors were recorded anywhere (codegen, runtime, post-render). This is the foundational correctness criterion.

### render_test/ — Script Runner + Walker Harness
Node.js scripts that execute generated JS on the Figma Desktop Bridge and produce rendered-ref payloads for `dd verify`.

| Script | Purpose |
|--------|---------|
| `run.js` | Executes a generated script on the bridge. Hard-asserts the output page by name (never trusts `figma.currentPage`, which `getNodeByIdAsync` side-effects). Cross-page relocate uses an explicit id manifest. |
| `walk_ref.js` | Runs script + walks the rendered subtree → rendered-ref JSON. Captures per-eid `{type, name, width, height, characters, textAutoResize, fillGeometryCount, strokeGeometryCount, fills, strokes, effectCount}`. Safeguard pattern identical to `run.js`. |

### render_batch/sweep.py — Corpus Driver
Per-screen generate → walk → verify → aggregate. Writes per-screen outputs under `render_batch/{scripts,walks,reports}/` and a `summary.json` aggregate (kinds distribution, parity counts, failures).

```bash
python3 render_batch/sweep.py --port 9231            # Full corpus
python3 render_batch/sweep.py --limit 10             # First 10
python3 render_batch/sweep.py --since 250            # Resume from id
python3 render_batch/sweep.py --skip-existing        # Reuse cached outputs
```

Latest (pt 6 verified): 204 / 204 is_parity=True, 0 failures, 449 s.

## Supporting Infrastructure

### dd/_timing.py — StageTimer
Zero-dependency pipeline profiler. Context-manager API; writes JSONL longitudinal log to `~/.cache/dd/extract_timings.jsonl` for cross-run comparison.

```python
timer = StageTimer()
with timer.stage("fetch_screens", items=338, unit="screens"):
    ...
timer.print_summary()   # tabulated output
```

Records `{timestamp, meta, stages[{name, duration_s, items, unit, **extra}]}`.

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
Schema initialization from `schema.sql`, connection management, WAL mode, migration runner. Current schema includes 77 node columns + `assets` + `node_asset_refs` + `component_key_registry` + ADR-007 extraction_runs / extraction_locks. Migrations 001..010 are additive and idempotent.

### dd/cli.py — CLI Commands (19 tests)
Entry points: `extract`, `extract-plugin`, `extract-supplement`, `cluster`, `accept-all`, `validate`, `export`, `push`, `status`, `classify`, `generate-ir`, `generate`, `generate-prompt`, `verify`, `seed-catalog`, `maintenance`, `curate-report`.

### dd/status.py — Status Reporting (18 tests)
Dashboard data: token counts by tier, binding coverage, sync status summary.

### dd/config.py — Configuration
Paths, thresholds, API limits. `SCHEMA_PATH`, `USE_FIGMA_CODE_LIMIT`.

### dd/types.py — Constants
`NON_SEMANTIC_PREFIXES`, `SEMANTIC_NODE_TYPES` — filtering heuristics for extraction.

---

## v0.3 Pipeline Additions (M5–M7)

This section inventories modules added during **M5** (Option B cutover,
2026-04-19) through **M7** (synthetic generation, 2026-04-21) and the
**type/role split** (2026-04-22). Full details live in per-module
docstrings and linked design docs; the entries below are navigation
anchors plus 1–2 lines each.

### Grammar / IR Pipeline (M5–M6)

- **`dd/markup_l3.py`** — L3 markup grammar parser, emitter, AST
  (`NodeHead`, `Node`, `L3Document`, etc.), `apply_edits` engine for
  the 7-verb edit grammar (M7.1). Source of truth for the markup
  spec; see `docs/decisions/v0.3-grammar-modes.md`.
- **`dd/compress_l3.py`** — Compressor from CompositionSpec dict →
  L3 AST (`compress_to_l3_with_maps`). Produces side-car maps keyed
  on `id(Node)` to disambiguate cousin subtrees with colliding eids.
  Emits `role=<semantic>` head prop when `element.role != element.type`
  (type/role split, 2026-04-22).
- **`dd/render_figma_ast.py`** — Markup-native Figma renderer
  (`render_figma`). Default post-M6 render path, replacing the
  dict-IR `dd.renderers.figma.generate_figma_script`. Emits
  `leaf_type_append_skipped` soft diagnostic when a leaf-typed parent
  would crash on `appendChild`. The type/role split reduced these
  emissions from 22/corpus → 0 on round-trip.
- **`dd/render_protocol.py`** — REMOVED in P7 (Phase E Pattern 1
  fix, 2026-04-25). The `RenderProtocol` ABC was a cross-backend
  scaffold (FigmaRenderer, Renderer, WalkResult) that never went
  into production — only dd/cli.py's `_run_verify` and
  dd/apply_render.py call the renderer directly. The unified
  verification channel that ADR-007 introduced is still live in
  dd/boundary.py + dd/verify_figma.py + the renderer guards;
  multi-backend fidelity scoring is deferred to v0.4 and will use
  a TypedDict/Protocol when a second backend exists.

### Classification (M7.0.a, 4-source pipeline)

- **`dd/classify_v2.py`** — 4-source classifier pipeline
  (LLM + PS + CS + SoM). `_insert_llm_verdicts` also syncs
  `nodes.role` alongside `screen_component_instances.canonical_type`
  (type/role split, 2026-04-22).
- **`dd/classify_consensus.py`** — Weighted-majority consensus
  (rule v2 with SoM weight 2; see `project_m7_classifier_v2.md`).
- **`dd/classify_dedup.py`** — Pre-classification dedup applied
  before any API call.
- **`dd/classify_review.py`** + **`dd/classify_audit.py`** — Tier 1.5
  review CLI and post-classification audit reports.
- **`dd/classify_few_shot.py`** — Few-shot prompt scaffolding for
  the LLM classifier.
- **`dd/classify_vision_som.py`** +
  **`dd/classify_vision_som_worker.py`** — Set-of-Marks (SoM) vision
  classifier; weight-2 source in consensus.
- **`dd/classify_vision_batched.py`**,
  **`dd/classify_vision_crop.py`**,
  **`dd/classify_vision_gemini.py`** — Per-crop, batched, and
  Gemini vision paths.

### Composition (M7.0.d–f + M7.6)

- **`dd/composition/registry.py`** — `ProviderRegistry` dispatches
  composition requests across provider backends.
- **`dd/composition/cascade.py`** — 3-mode cascade: Mode 1 INSTANCE →
  Mode 2 catalog template → Mode 3 synthesis.
- **`dd/composition/protocol.py`** — Provider ABC.
- **`dd/composition/archetype_classifier.py`** +
  **`archetype_injection.py`** — Archetype detection and donor
  injection (M7.6 S4).
- **`dd/composition/slots.py`** + **`dd/composition/variants.py`** —
  Slot grammar and variant-family composition helpers (not the same
  as top-level `dd/slots.py` / `dd/variants.py`, which are the
  M7.0.b/c derivation pipelines).
- **`dd/composition/matrix_contracts.py`** +
  **`matrix_measures.py`** — Contract-matrix and measurement
  primitives for synthesis.
- **`dd/composition/plan.py`** — Composition plan structures.
- **`dd/composition/providers/universal.py`** —
  `UniversalCatalogProvider` (Mode-2 template fallback).
- **`dd/composition/providers/project_ckr.py`** —
  `ProjectCKRProvider` (Mode-1 master lookup via
  `component_key_registry`).
- **`dd/composition/providers/corpus_retrieval.py`** —
  `CorpusRetrievalProvider` (v0.2 corpus-fragment retrieval).
  Emits post-type/role-split IR (`type` = primitive, `role` =
  optional semantic) as of 2026-04-22.
- **`dd/composition/providers/ingested.py`** — Provider backed by
  external ingested libraries.
- **`dd/forces.py`** — M7.0.d compositional-role labeling. Alexander
  forces guard: `<role> in <context>` (e.g., `main-cta in login-form`).
  Migration 019.
- **`dd/patterns.py`** — M7.0.e cross-screen pattern extraction and
  scoring.
- **`dd/sticker_sheet.py`** — M7.0.f sticker-sheet tagging for
  archetype injection.

### Edit grammar and repair (M7.1 → M7.5)

- **`dd/structural_verbs.py`** — Implementations of the 7-verb edit
  grammar (`set` / `delete` / `append` / `insert` / `move` / `swap` /
  `replace`). Called by `apply_edits` in `dd/markup_l3.py`.
- **`dd/apply_render.py`** — Compose-edit-render pipeline.
  `rebuild_maps_after_edits` refreshes the compressor's `id(Node)`-keyed
  side-car maps after `_splice_node`; `walk_rendered_via_bridge` wraps
  the walk harness for programmatic round-trips.
- **`dd/repair_agent.py`** — REMOVED in P7 (Phase E Pattern 1 fix,
  2026-04-25). M7.5 verifier-as-agent loop. The repair loop was
  test-only — `run_repair_loop` was never wired into a production
  CLI command; only `tests/test_repair_agent.py` and
  `scripts/repair_demo.py` consumed it. The `StructuredError.hint`
  channel that the loop read is still live; the loop itself is
  deferred to v0.4 if a real production use case appears.
- **`dd/repair_figma.py`** — REMOVED in P7. Was the Figma-specific
  verifier adapter feeding the repair loop.

### Scoring (Tier C / D)

- **`dd/fidelity_score.py`** — 7-dimension structural fidelity scorer:
  `coverage`, `rootedness`, `font_readiness`,
  `component_child_consistency`, `leaf_type_structural`,
  `canvas_coverage`, `content_richness`. Optional SoM-based
  `component_precision` + `component_recall` dims layered on top.

### Type/role split (2026-04-22)

Splits the IR `type` field into:

- **`type`** — structural primitive (`frame` / `text` / `rectangle` /
  `group` / `instance` / `line` / `ellipse` / `vector`), always
  present, deterministic (from `node_type`). Dispatch-safe.
- **`role`** — classifier's semantic label (`heading`, `card`,
  `button`, `container`, …), optional, elided when `role == type`.

See [`plan-type-role-split.md`](plan-type-role-split.md).
New helpers: `dd/ir.py::_resolve_primitive_type` (structural-only),
`dd/compose.py::_semantic_type` (role-first reader with type
fallback for Mode 3 pre-split LLM output). Markup emits `role=<value>`
as a regular head `PropAssign`; no grammar-schema change. `nodes.role`
column added via **migration 021** and backfilled from SCI.

### Other additions

- **`dd/checkerboard.py`** — Checkerboard background generator for
  self-hidden-node rendering in vision classification.
- **`dd/visual_inspect.py`** — Visual-diagnostic helpers; hard vs
  soft error partitioning for walk reports.
- **`dd/library_catalog.py`** — Component-library catalog utilities.
- **`dd/slots.py`** (renamed from `m7_slots.py`) — Slot derivation
  pipeline (M7.0.b).
- **`dd/variants.py`** (renamed from `m7_variants.py`) — Variant-family
  derivation pipeline (M7.0.c).
- **`dd/paths.py`** — Path-derivation utilities.
- **`dd/plugin_render.py`** — Plugin-side render helpers for
  vision classification (`render_screen_with_visible_nodes`).
- **`dd/maintenance.py`** — DB maintenance CLI (`prune-extraction-runs`).
- **`dd/extract_targeted.py`** — Targeted extraction CLI
  (`properties` / `sizing` / `transforms` / `vector-geometry` modes).
- **`dd/extract_inventory.py`** — Inventory-mode extraction helpers
  used by `dd/extract.py`.
- **`dd/curate_report.py`** — Curation-stage reporting (CLI-facing
  through `dd/curate.py`).

### Migrations (since M5)

| # | File | What |
|---|---|---|
| 011 | `classification_reason.sql` | LLM/vision reason column on SCI |
| 011 | `catalog_ontology_v2.sql` | Catalog ontology v2 |
| 012 | `variant_token_bindings.sql` | Variant-scoped token bindings |
| 013 | `three_source_classification.sql` | LLM + PS + CS consensus columns |
| 014 | `rename_classification_reason.sql` | Rename after 011 |
| 015 | `preserve_llm_verdict.sql` | Keep LLM verdict across rerun |
| 016 | `catalog_normalization.sql` | Canonical type catalog tables |
| 017 | `som_verdict_columns.sql` | SoM vision-verdict columns |
| 018 | `components_canonical_type.sql` | Components row canonical type |
| 019 | `forces_compositional_role.sql` | Alexander forces labeling |
| 020 | `components_authoritative_source.sql` | Components write-source-of-truth |
| 021 | `add_nodes_role.sql` | `nodes.role` column for type/role split |
