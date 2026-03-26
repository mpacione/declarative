-- Declarative Design — SQLite Schema v0.2
-- Date: 2025-03-25
-- Four table groups: System, Compositions, Mappings, Operations
-- Designed against probe data shapes from Dank file (drxXOUOdYEBBQ09mrXJeYu)
--
-- DESIGN NOTES:
-- * Nodes table is intentionally wide (40+ cols). Denormalization avoids N+1
--   JOINs for the most common agent query pattern: "give me a screen's full tree
--   with all visual properties." SQLite handles wide rows efficiently.
-- * Composite tokens (DTCG typography, shadow, border) are NOT stored as grouped
--   references. Atomic tokens are stored individually; composite types are
--   assembled at export time when generating tokens.json (FR-4.6).
-- * DTCG resolver format (sets + modifiers) is generated at export time from
--   the flat token_collections/token_modes tables. The DB mirrors Figma's mode
--   model (1 collection = N flat modes) for queryability and 1:1 export mapping.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- SYSTEM TABLES — the vocabulary
-- ============================================================

-- Source Figma files. Multi-file support from day one.
CREATE TABLE files (
    id              INTEGER PRIMARY KEY,
    file_key        TEXT NOT NULL UNIQUE,        -- Figma file key (e.g. drxXOUOdYEBBQ09mrXJeYu)
    name            TEXT NOT NULL,
    last_modified   TEXT,                        -- ISO 8601 from Figma API
    extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    node_count      INTEGER,                    -- 25547 for Dank
    screen_count    INTEGER,
    metadata        TEXT                         -- JSON blob for anything else (version, editor, etc.)
);

-- Maps to Figma variable collections. One collection = one token domain (colors, spacing, etc.)
-- Or one collection per brand/theme — your call at curation time.
CREATE TABLE token_collections (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id),
    figma_id        TEXT,                        -- Figma collection key (null before export)
    name            TEXT NOT NULL,
    description     TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Modes within a collection (e.g. Light/Dark, Compact/Comfortable).
-- Figma enforces modes-per-collection, so this mirrors that.
CREATE TABLE token_modes (
    id              INTEGER PRIMARY KEY,
    collection_id   INTEGER NOT NULL REFERENCES token_collections(id) ON DELETE CASCADE,
    figma_mode_id   TEXT,                        -- Figma mode ID (null before export)
    name            TEXT NOT NULL,
    is_default      INTEGER NOT NULL DEFAULT 0,  -- 1 = default mode
    UNIQUE(collection_id, name)
);

-- Token definitions. One row per token, regardless of how many modes it has.
-- Tier tracks maturity: extracted (raw from Figma) → curated (clustered/named) → aliased (references another token).
-- ALIAS RULE: alias_of must point to a non-aliased token (depth = 1 max).
-- Enforced by trigger trg_alias_depth_check below.
CREATE TABLE tokens (
    id              INTEGER PRIMARY KEY,
    collection_id   INTEGER NOT NULL REFERENCES token_collections(id),
    name            TEXT NOT NULL,               -- DTCG path: color.surface.primary
    type            TEXT NOT NULL,               -- DTCG $type: color, dimension, fontFamily, fontWeight, number, shadow, etc.
    tier            TEXT NOT NULL DEFAULT 'extracted'
                    CHECK(tier IN ('extracted', 'curated', 'aliased')),
    alias_of        INTEGER REFERENCES tokens(id),  -- self-ref FK for aliased tokens (max depth 1)
    description     TEXT,
    figma_variable_id TEXT,                      -- Figma variable ID (null before export)
    sync_status     TEXT NOT NULL DEFAULT 'pending'
                    CHECK(sync_status IN ('pending', 'figma_only', 'code_only', 'synced', 'drifted')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(collection_id, name)
);

-- Enforce alias depth = 1. An aliased token must point to a non-aliased token.
CREATE TRIGGER trg_alias_depth_check
BEFORE INSERT ON tokens
WHEN NEW.alias_of IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Alias target must not itself be an alias (max depth 1)')
    WHERE (SELECT alias_of FROM tokens WHERE id = NEW.alias_of) IS NOT NULL;
END;

CREATE TRIGGER trg_alias_depth_check_update
BEFORE UPDATE OF alias_of ON tokens
WHEN NEW.alias_of IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Alias target must not itself be an alias (max depth 1)')
    WHERE (SELECT alias_of FROM tokens WHERE id = NEW.alias_of) IS NOT NULL;
END;

-- Per-mode token values. One row per token per mode.
-- raw_value: exact Figma representation (JSON). Lossless round-trip.
-- resolved_value: normalized for querying/clustering. Hex for colors, number for dimensions.
CREATE TABLE token_values (
    id              INTEGER PRIMARY KEY,
    token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
    mode_id         INTEGER NOT NULL REFERENCES token_modes(id) ON DELETE CASCADE,
    raw_value       TEXT NOT NULL,               -- JSON: {"r":0.035,"g":0.035,"b":0.043,"a":1} or {"value":16,"unit":"px"}
    resolved_value  TEXT NOT NULL,               -- "#09090B" or "16" or "Inter/600/16px/24px"
    extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(token_id, mode_id)
);

-- Component definitions (not instances — those live in nodes table).
-- Maps to Figma component sets or standalone components.
CREATE TABLE components (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id),
    figma_node_id   TEXT NOT NULL,               -- Figma node ID of the component/set
    name            TEXT NOT NULL,               -- e.g. "button", "nav/tabs", "input/text"
    description     TEXT,
    category        TEXT,                        -- button, input, nav, card, modal, icon, layout, chrome
    variant_properties TEXT,                     -- JSON: ["size","style","state"] — the axes (denormalized, see variant_axes for structured)
    composition_hint TEXT,                       -- JSON: structured recipe — see Component Model section
    extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(file_id, figma_node_id)
);

-- Individual variants within a component set.
CREATE TABLE component_variants (
    id              INTEGER PRIMARY KEY,
    component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    figma_node_id   TEXT NOT NULL,
    name            TEXT NOT NULL,               -- e.g. "size=large, style=solid"
    properties      TEXT NOT NULL,               -- JSON: {"size":"large","style":"solid","state":"default"}
    UNIQUE(component_id, figma_node_id)
);

-- ============================================================
-- COMPONENT MODEL — structured component knowledge for agents
-- ============================================================

-- Structured variant axes. Normalizes the JSON in components.variant_properties
-- so agents can query across components: "show me all components with a state axis"
CREATE TABLE variant_axes (
    id              INTEGER PRIMARY KEY,
    component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    axis_name       TEXT NOT NULL,               -- "size", "style", "state", "density"
    axis_values     TEXT NOT NULL,               -- JSON array: ["small","medium","large"]
    is_interaction  INTEGER NOT NULL DEFAULT 0,  -- 1 = state axis (hover, focus, disabled, pressed, selected, loading)
    default_value   TEXT,                        -- "default" or "medium" — the baseline variant
    UNIQUE(component_id, axis_name)
);

-- Per-variant axis values. Links each variant to its position on each axis.
-- Enables: "all hover variants across all components"
CREATE TABLE variant_dimension_values (
    id              INTEGER PRIMARY KEY,
    variant_id      INTEGER NOT NULL REFERENCES component_variants(id) ON DELETE CASCADE,
    axis_id         INTEGER NOT NULL REFERENCES variant_axes(id) ON DELETE CASCADE,
    value           TEXT NOT NULL,               -- "hover", "large", "solid"
    UNIQUE(variant_id, axis_id)
);

-- Named insertion points within a component. Tells a Conjure agent:
-- "button has an optional leading icon slot and a required label slot"
CREATE TABLE component_slots (
    id              INTEGER PRIMARY KEY,
    component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,               -- "leading_icon", "label", "trailing_action", "badge"
    slot_type       TEXT,                        -- icon, text, component, image, any
    is_required     INTEGER NOT NULL DEFAULT 0,  -- 1 = must be filled, 0 = optional
    default_content TEXT,                        -- JSON: default fill if any (e.g., {"type":"text","value":"Submit"})
    sort_order      INTEGER NOT NULL DEFAULT 0,  -- visual order within the component
    description     TEXT,
    UNIQUE(component_id, name)
);

-- Accessibility contract per component.
-- Extracted where available, manually augmented during curation.
CREATE TABLE component_a11y (
    id              INTEGER PRIMARY KEY,
    component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    role            TEXT,                        -- button, link, navigation, dialog, tab, listitem, etc.
    required_label  INTEGER NOT NULL DEFAULT 0,  -- 1 = must have aria-label or visible label
    focus_order     INTEGER,                    -- tab order position (null = natural DOM order)
    min_touch_target REAL,                      -- minimum tap target in px (44 for iOS, 48 for Android)
    keyboard_shortcut TEXT,                     -- if applicable
    aria_properties TEXT,                        -- JSON: {"aria-expanded": "boolean", "aria-selected": "boolean"}
    notes           TEXT,                        -- free-text a11y guidance
    UNIQUE(component_id)
);

-- How the component adapts across breakpoints/contexts.
-- One row per responsive behavior (a component can have multiple).
CREATE TABLE component_responsive (
    id              INTEGER PRIMARY KEY,
    component_id    INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    breakpoint      TEXT,                        -- "mobile", "tablet", "desktop" or pixel value "768"
    layout_change   TEXT,                        -- JSON: {"direction":"HORIZONTAL→VERTICAL","sizing":"FIXED→FILL"}
    visibility      TEXT,                        -- "visible", "hidden", "collapsed"
    slot_changes    TEXT,                        -- JSON: {"trailing_action":"hidden","badge":"collapsed"}
    notes           TEXT,
    UNIQUE(component_id, breakpoint)
);

-- Layout patterns / composition recipes. Populated during curation, not extraction.
-- These are reusable structural templates an agent can instantiate.
CREATE TABLE patterns (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,         -- e.g. "nav/sidebar", "card/pricing", "form/settings"
    category        TEXT NOT NULL,               -- nav, card, form, modal, page, section
    recipe          TEXT NOT NULL,               -- JSON: structural recipe (component refs, layout rules, slot definitions)
    description     TEXT,
    source_screens  TEXT,                        -- JSON array of screen IDs this was derived from
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ============================================================
-- COMPOSITION TABLES — the sentences
-- ============================================================

-- Screens / top-level frames. One row per screen in the file.
CREATE TABLE screens (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id),
    figma_node_id   TEXT NOT NULL,               -- e.g. "2219:235687"
    name            TEXT NOT NULL,
    width           REAL NOT NULL,
    height          REAL NOT NULL,
    device_class    TEXT,                        -- iphone, ipad_11, ipad_13, web, component_sheet, unknown
    node_count      INTEGER,                    -- nodes in this screen (~204 observed)
    extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(file_id, figma_node_id)
);

-- Full node tree within screens. Every frame, group, text, rectangle, instance, vector.
-- parent_id is self-referential for tree structure. Root nodes have parent_id = NULL.
-- path is a materialized path for efficient tree queries: "1.5.12.3"
-- Enables: WHERE path LIKE '1.5.%' to get all descendants of node 1.5
CREATE TABLE nodes (
    id              INTEGER PRIMARY KEY,
    screen_id       INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
    figma_node_id   TEXT NOT NULL,
    parent_id       INTEGER REFERENCES nodes(id),
    path            TEXT,                        -- materialized path: "1.5.12.3" (computed at write time)
    name            TEXT NOT NULL,
    node_type       TEXT NOT NULL,               -- FRAME, TEXT, RECTANGLE, INSTANCE, VECTOR, GROUP, ELLIPSE, etc.
    depth           INTEGER NOT NULL DEFAULT 0,  -- tree depth from screen root
    sort_order      INTEGER NOT NULL DEFAULT 0,  -- sibling order (Figma z-order)
    is_semantic     INTEGER NOT NULL DEFAULT 0,  -- 1 = meaningful container, 0 = Figma structural noise

    -- Component reference (for INSTANCE nodes)
    component_id    INTEGER REFERENCES components(id),

    -- Geometry
    x               REAL,
    y               REAL,
    width           REAL,
    height          REAL,

    -- Auto-layout (null if not auto-layout)
    layout_mode     TEXT,                        -- HORIZONTAL, VERTICAL, null
    padding_top     REAL,
    padding_right   REAL,
    padding_bottom  REAL,
    padding_left    REAL,
    item_spacing    REAL,
    counter_axis_spacing REAL,
    primary_align   TEXT,                        -- MIN, CENTER, MAX, SPACE_BETWEEN
    counter_align   TEXT,                        -- MIN, CENTER, MAX, BASELINE
    layout_sizing_h TEXT,                        -- FIXED, HUG, FILL
    layout_sizing_v TEXT,                        -- FIXED, HUG, FILL

    -- Visual properties (raw JSON — full fidelity)
    fills           TEXT,                        -- JSON array of fills
    strokes         TEXT,                        -- JSON array of strokes
    effects         TEXT,                        -- JSON array of effects (shadows, blurs)
    corner_radius   TEXT,                        -- JSON: number or {"tl":8,"tr":8,"bl":0,"br":0}
    opacity         REAL DEFAULT 1.0,
    blend_mode      TEXT DEFAULT 'NORMAL',
    visible         INTEGER NOT NULL DEFAULT 1,

    -- Typography (TEXT nodes only)
    font_family     TEXT,
    font_weight     INTEGER,
    font_size       REAL,
    line_height     TEXT,                        -- JSON: {"value":24,"unit":"PIXELS"} or {"unit":"AUTO"}
    letter_spacing  TEXT,                        -- JSON: {"value":0,"unit":"PIXELS"} or {"value":-2,"unit":"PERCENT"}
    text_align      TEXT,                        -- LEFT, CENTER, RIGHT, JUSTIFIED
    text_content    TEXT,                        -- actual text string

    extracted_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(screen_id, figma_node_id)
);

-- Token bindings: which token is bound to which property of which node.
-- Before tokens exist, this stores extracted raw values with token_id = NULL.
-- After curation, token_id links to the assigned token.
CREATE TABLE node_token_bindings (
    id              INTEGER PRIMARY KEY,
    node_id         INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    property        TEXT NOT NULL,               -- fill.0.color, stroke.0.color, cornerRadius, fontSize, fontFamily, effect.0.color, effect.0.radius, padding.top, itemSpacing, opacity, etc.
    token_id        INTEGER REFERENCES tokens(id),  -- NULL until token is assigned
    raw_value       TEXT NOT NULL,               -- extracted value before tokenization
    resolved_value  TEXT NOT NULL,               -- normalized for matching: "#09090B", "16", "Inter"
    confidence      REAL,                        -- clustering confidence (0-1) when auto-assigned
    binding_status  TEXT NOT NULL DEFAULT 'unbound'
                    CHECK(binding_status IN ('unbound', 'proposed', 'bound', 'overridden', 'intentionally_unbound')),
    UNIQUE(node_id, property)
);

-- ============================================================
-- MAPPING TABLES — the rosetta stone
-- ============================================================

-- Cross-tool mappings. One row per token per target system.
-- This is how a coding agent knows token X = CSS var Y = Tailwind class Z.
CREATE TABLE code_mappings (
    id              INTEGER PRIMARY KEY,
    token_id        INTEGER NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
    target          TEXT NOT NULL,               -- css, tailwind, react_prop, swift, compose
    identifier      TEXT NOT NULL,               -- --color-surface-primary, bg-surface-primary, surfacePrimary
    file_path       TEXT,                        -- where this mapping was found/should go
    extracted_at    TEXT,
    UNIQUE(token_id, target, identifier)
);

-- Route/view to screen mapping. Links app routes to Figma screens.
-- Useful for "build me the /settings page" → agent knows which screen to reference.
CREATE TABLE route_mappings (
    id              INTEGER PRIMARY KEY,
    screen_id       INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
    route           TEXT NOT NULL,               -- /settings, /home, /profile/:id
    platform        TEXT NOT NULL DEFAULT 'web', -- web, ios, android
    component_path  TEXT,                        -- src/pages/Settings.tsx
    UNIQUE(screen_id, route, platform)
);

-- ============================================================
-- OPERATIONS TABLES — pipeline coordination + locking
-- ============================================================

-- Extraction run tracking. One row per pipeline invocation.
-- Enables resume, progress reporting, and history.
CREATE TABLE extraction_runs (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id),
    started_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at    TEXT,
    agent_id        TEXT,                        -- identifier for the agent running this extraction
    total_screens   INTEGER,
    extracted_screens INTEGER DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK(status IN ('running', 'completed', 'failed', 'cancelled'))
);

-- Per-screen extraction status within a run.
-- Enables: resume from screen 147, parallel agent coordination (skip in_progress screens).
CREATE TABLE screen_extraction_status (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES extraction_runs(id) ON DELETE CASCADE,
    screen_id       INTEGER NOT NULL REFERENCES screens(id),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped')),
    started_at      TEXT,
    completed_at    TEXT,
    node_count      INTEGER,
    binding_count   INTEGER,
    error           TEXT,
    UNIQUE(run_id, screen_id)
);

-- Advisory locks for parallel agent coordination.
-- Cooperative: agents must check before writing. Locks auto-expire.
CREATE TABLE extraction_locks (
    id              INTEGER PRIMARY KEY,
    resource        TEXT NOT NULL UNIQUE,         -- "screen:2219:235687" or "curation" or "export" or "clustering"
    agent_id        TEXT NOT NULL,               -- identifier for the locking agent
    acquired_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at      TEXT NOT NULL                -- auto-expire after timeout (crash recovery)
);

-- Pre-export validation results. Populated by validation gate before Phase 7/8.
-- Blocks export if any row has severity = 'error'.
CREATE TABLE export_validations (
    id              INTEGER PRIMARY KEY,
    run_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    check_name      TEXT NOT NULL,               -- "mode_completeness", "name_dtcg_compliant", "orphan_tokens", "binding_coverage"
    severity        TEXT NOT NULL CHECK(severity IN ('error', 'warning', 'info')),
    message         TEXT NOT NULL,               -- human-readable description
    affected_ids    TEXT,                        -- JSON array of token/collection/binding IDs
    resolved        INTEGER NOT NULL DEFAULT 0   -- 1 = user acknowledged/fixed
);

-- ============================================================
-- INDEXES
-- ============================================================

-- Token lookups
CREATE INDEX idx_tokens_type ON tokens(type);
CREATE INDEX idx_tokens_tier ON tokens(tier);
CREATE INDEX idx_tokens_sync ON tokens(sync_status);
CREATE INDEX idx_tokens_collection ON tokens(collection_id);
CREATE INDEX idx_token_values_resolved ON token_values(resolved_value);
CREATE INDEX idx_token_values_token_mode ON token_values(token_id, mode_id);

-- Node tree traversal
CREATE INDEX idx_nodes_screen ON nodes(screen_id);
CREATE INDEX idx_nodes_parent ON nodes(parent_id);
CREATE INDEX idx_nodes_type ON nodes(node_type);
CREATE INDEX idx_nodes_semantic ON nodes(screen_id, is_semantic) WHERE is_semantic = 1;
CREATE INDEX idx_nodes_component ON nodes(component_id) WHERE component_id IS NOT NULL;
CREATE INDEX idx_nodes_path ON nodes(path);                    -- materialized path lookups

-- Binding lookups (composite indexes for common query patterns)
CREATE INDEX idx_bindings_token ON node_token_bindings(token_id) WHERE token_id IS NOT NULL;
CREATE INDEX idx_bindings_status ON node_token_bindings(binding_status);
CREATE INDEX idx_bindings_resolved ON node_token_bindings(resolved_value);
CREATE INDEX idx_bindings_token_status ON node_token_bindings(token_id, binding_status);
CREATE INDEX idx_bindings_status_property ON node_token_bindings(binding_status, property);
CREATE INDEX idx_bindings_node_status ON node_token_bindings(node_id, binding_status);

-- Component model lookups
CREATE INDEX idx_variant_axes_component ON variant_axes(component_id);
CREATE INDEX idx_variant_axes_interaction ON variant_axes(is_interaction) WHERE is_interaction = 1;
CREATE INDEX idx_variant_dim_values_axis ON variant_dimension_values(axis_id);
CREATE INDEX idx_component_slots_component ON component_slots(component_id);

-- Code mapping lookups
CREATE INDEX idx_code_mappings_target ON code_mappings(target);

-- Screen lookups
CREATE INDEX idx_screens_device ON screens(device_class);
CREATE INDEX idx_screens_file ON screens(file_id);

-- Operations
CREATE INDEX idx_extraction_status_run ON screen_extraction_status(run_id, status);
CREATE INDEX idx_locks_expires ON extraction_locks(expires_at);

-- ============================================================
-- VIEWS — convenience queries for agents
-- ============================================================

-- All unique extracted color values across the file, with usage count.
-- This is your clustering input. Joins through nodes→screens for file_id filtering.
CREATE VIEW v_color_census AS
SELECT
    ntb.resolved_value,
    COUNT(*) AS usage_count,
    COUNT(DISTINCT ntb.node_id) AS node_count,
    GROUP_CONCAT(DISTINCT ntb.property) AS properties,
    s.file_id
FROM node_token_bindings ntb
JOIN nodes n ON ntb.node_id = n.id
JOIN screens s ON n.screen_id = s.id
WHERE ntb.property LIKE 'fill%' OR ntb.property LIKE 'stroke%'
GROUP BY ntb.resolved_value, s.file_id
ORDER BY usage_count DESC;

-- All unique typography combinations.
CREATE VIEW v_type_census AS
SELECT
    n.font_family,
    n.font_weight,
    n.font_size,
    json_extract(n.line_height, '$.value') AS line_height_value,
    COUNT(*) AS usage_count,
    s.file_id
FROM nodes n
JOIN screens s ON n.screen_id = s.id
WHERE n.node_type = 'TEXT' AND n.font_family IS NOT NULL
GROUP BY n.font_family, n.font_weight, n.font_size, json_extract(n.line_height, '$.value'), s.file_id
ORDER BY usage_count DESC;

-- All unique spacing values (padding + gap).
CREATE VIEW v_spacing_census AS
SELECT
    ntb.resolved_value,
    ntb.property,
    COUNT(*) AS usage_count,
    s.file_id
FROM node_token_bindings ntb
JOIN nodes n ON ntb.node_id = n.id
JOIN screens s ON n.screen_id = s.id
WHERE ntb.property IN ('padding.top','padding.right','padding.bottom','padding.left','itemSpacing','counterAxisSpacing')
GROUP BY ntb.resolved_value, ntb.property, s.file_id
ORDER BY CAST(ntb.resolved_value AS REAL), usage_count DESC;

-- All unique corner radius values.
CREATE VIEW v_radius_census AS
SELECT
    ntb.resolved_value,
    COUNT(*) AS usage_count,
    s.file_id
FROM node_token_bindings ntb
JOIN nodes n ON ntb.node_id = n.id
JOIN screens s ON n.screen_id = s.id
WHERE ntb.property LIKE 'cornerRadius%' OR ntb.property LIKE '%Radius'
GROUP BY ntb.resolved_value, s.file_id
ORDER BY CAST(ntb.resolved_value AS REAL);

-- All unique effect (shadow) values.
CREATE VIEW v_effect_census AS
SELECT
    ntb.resolved_value,
    ntb.property,
    COUNT(*) AS usage_count,
    s.file_id
FROM node_token_bindings ntb
JOIN nodes n ON ntb.node_id = n.id
JOIN screens s ON n.screen_id = s.id
WHERE ntb.property LIKE 'effect%'
GROUP BY ntb.resolved_value, ntb.property, s.file_id
ORDER BY usage_count DESC;

-- Unbound bindings — nodes with extracted values but no token assigned yet.
CREATE VIEW v_unbound AS
SELECT
    ntb.id AS binding_id,
    s.name AS screen_name,
    s.file_id,
    n.name AS node_name,
    n.node_type,
    ntb.property,
    ntb.resolved_value
FROM node_token_bindings ntb
JOIN nodes n ON ntb.node_id = n.id
JOIN screens s ON n.screen_id = s.id
WHERE ntb.token_id IS NULL
ORDER BY ntb.resolved_value;

-- Token coverage: how many bindings each token satisfies.
CREATE VIEW v_token_coverage AS
SELECT
    t.name AS token_name,
    t.type AS token_type,
    t.tier,
    t.collection_id,
    COUNT(ntb.id) AS binding_count,
    COUNT(DISTINCT ntb.node_id) AS node_count,
    COUNT(DISTINCT n.screen_id) AS screen_count
FROM tokens t
LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
LEFT JOIN nodes n ON ntb.node_id = n.id
GROUP BY t.id
ORDER BY binding_count DESC;

-- Screen composition summary — what an agent needs to build a screen.
CREATE VIEW v_screen_summary AS
SELECT
    s.id AS screen_id,
    s.file_id,
    s.name,
    s.device_class,
    s.width,
    s.height,
    s.node_count,
    COUNT(DISTINCT n.component_id) AS unique_components,
    SUM(CASE WHEN n.node_type = 'INSTANCE' THEN 1 ELSE 0 END) AS instance_count,
    SUM(CASE WHEN n.layout_mode IS NOT NULL THEN 1 ELSE 0 END) AS autolayout_count
FROM screens s
LEFT JOIN nodes n ON n.screen_id = s.id
GROUP BY s.id;

-- Resolved tokens — follows alias chain to return final value for any token.
-- Alias depth is enforced to 1 by trigger, so single JOIN suffices.
CREATE VIEW v_resolved_tokens AS
SELECT
    t.id,
    t.name,
    t.type,
    t.tier,
    t.collection_id,
    t.sync_status,
    t.figma_variable_id,
    CASE
        WHEN t.alias_of IS NOT NULL THEN target.name
        ELSE NULL
    END AS alias_target_name,
    tv.mode_id,
    tm.name AS mode_name,
    COALESCE(target_tv.resolved_value, tv.resolved_value) AS resolved_value,
    COALESCE(target_tv.raw_value, tv.raw_value) AS raw_value
FROM tokens t
LEFT JOIN tokens target ON t.alias_of = target.id
LEFT JOIN token_values tv ON tv.token_id = t.id
LEFT JOIN token_values target_tv ON target_tv.token_id = target.id AND target_tv.mode_id = tv.mode_id
LEFT JOIN token_modes tm ON tm.id = tv.mode_id;

-- Mode-aware color census — filter by mode for multi-mode clustering.
-- Usage: SELECT * FROM v_color_census_by_mode WHERE mode_name = 'Dark';
-- For PRE-clustering (no tokens yet), use v_color_census which reads raw bindings.
-- This view is for POST-clustering analysis of mode-specific token values.
CREATE VIEW v_color_census_by_mode AS
SELECT
    tv.resolved_value,
    tm.name AS mode_name,
    tm.id AS mode_id,
    t.name AS token_name,
    COUNT(ntb.id) AS binding_count
FROM tokens t
JOIN token_values tv ON tv.token_id = t.id
JOIN token_modes tm ON tm.id = tv.mode_id
LEFT JOIN node_token_bindings ntb ON ntb.token_id = t.id
WHERE t.type = 'color'
GROUP BY tv.resolved_value, tm.id, t.id
ORDER BY binding_count DESC;

-- Drift report — tokens where DB and Figma may be out of sync.
CREATE VIEW v_drift_report AS
SELECT
    t.id AS token_id,
    t.name AS token_name,
    t.type,
    t.sync_status,
    t.figma_variable_id,
    tv.resolved_value AS db_value,
    tm.name AS mode_name,
    tc.name AS collection_name
FROM tokens t
JOIN token_values tv ON tv.token_id = t.id
JOIN token_modes tm ON tm.id = tv.mode_id
JOIN token_collections tc ON tc.id = t.collection_id
WHERE t.sync_status IN ('pending', 'drifted', 'figma_only', 'code_only')
ORDER BY t.sync_status, tc.name, t.name;

-- Curation progress — overall pipeline status at a glance.
CREATE VIEW v_curation_progress AS
SELECT
    binding_status,
    COUNT(*) AS binding_count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM node_token_bindings), 1) AS pct
FROM node_token_bindings
GROUP BY binding_status
ORDER BY
    CASE binding_status
        WHEN 'bound' THEN 1
        WHEN 'proposed' THEN 2
        WHEN 'overridden' THEN 3
        WHEN 'unbound' THEN 4
    END;

-- Interaction state overview — all components with state axes and their values.
CREATE VIEW v_interaction_states AS
SELECT
    c.name AS component_name,
    c.category,
    va.axis_name,
    va.axis_values,
    va.default_value,
    COUNT(DISTINCT cv.id) AS variant_count
FROM variant_axes va
JOIN components c ON va.component_id = c.id
LEFT JOIN variant_dimension_values vdv ON vdv.axis_id = va.id
LEFT JOIN component_variants cv ON vdv.variant_id = cv.id
WHERE va.is_interaction = 1
GROUP BY va.id
ORDER BY c.name, va.axis_name;

-- Component catalog — full component overview for agent consumption.
CREATE VIEW v_component_catalog AS
SELECT
    c.id,
    c.name,
    c.category,
    c.description,
    c.composition_hint,
    COUNT(DISTINCT cv.id) AS variant_count,
    COUNT(DISTINCT cs.id) AS slot_count,
    ca.role AS a11y_role,
    ca.min_touch_target,
    GROUP_CONCAT(DISTINCT va.axis_name) AS axes
FROM components c
LEFT JOIN component_variants cv ON cv.component_id = c.id
LEFT JOIN component_slots cs ON cs.component_id = c.id
LEFT JOIN component_a11y ca ON ca.component_id = c.id
LEFT JOIN variant_axes va ON va.component_id = c.id
GROUP BY c.id
ORDER BY c.category, c.name;

-- Pre-export validation summary.
CREATE VIEW v_export_readiness AS
SELECT
    check_name,
    severity,
    COUNT(*) AS issue_count,
    SUM(resolved) AS resolved_count
FROM export_validations
WHERE run_at = (SELECT MAX(run_at) FROM export_validations)
GROUP BY check_name, severity
ORDER BY
    CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END;
