# Four-Layer Architecture Specification

> **Declarative Design is a bi-directional design compiler.** It parses UI from any source into an abstract compositional IR, then generates to any target with token-bound fidelity. This document specifies the four-layer architecture that makes that possible.

Status: DRAFT v2 — enriched with resolved architectural decisions (2026-04-02).

---

## The Four Layers

```
Layer 1: EXTRACTION     Source → DB/Store        "Record everything"
Layer 2: ANALYSIS        DB/Store → Abstractions  "Understand what's there"
Layer 3: COMPOSITION     Abstractions → IR         "Describe what to build"
Layer 4: RENDERING       IR + DB/Config → Output   "Build it concretely"
```

Each layer has a single responsibility. Data flows up through Layers 1-2 (concrete → abstract) and down through Layers 3-4 (abstract → concrete). The IR at Layer 3 is the narrowest point — pure semantic intent with no platform-specific detail.

**The critical loop**: Analysis reads the DB to build abstractions (concrete → abstract). The IR uses those abstractions to compose (abstract intent). The renderer dereferences back to the source data to build (abstract → concrete). The DB is the ground truth through the entire loop.

---

## Layer 1: Extraction

### Purpose
Parse a source artifact and store every recoverable detail in a structured store. Extraction is exhaustive and platform-specific. It captures MORE than the IR will ever need, because: (a) the analysis layer creates synthetic tokens from raw visual values, and (b) the renderer may fall back to the DB for edge cases where a value has no token entry. The primary rendering path is: resolve token refs (real + synthetic) from the IR's token dictionary.

### Figma Extraction

**Status**: Core extraction built (T1-T4). Schema has 40+ columns on `nodes` table. Extraction JS captures most properties. Significant gaps in component-level data.

**Input**: Figma file via REST API (file structure, image exports) + Plugin API (node properties, variable bindings)

**Output**: SQLite DB with the following tables:

#### Node-Level Data (`nodes` table — 86K rows in Dank)

Every node in the Figma tree becomes a row. The renderer reads this data to reconstruct visual properties.

| Category | Columns | Status |
|----------|---------|--------|
| **Identity** | id, screen_id, figma_node_id, parent_id, path, name, node_type, depth, sort_order, is_semantic | Built, populated |
| **Geometry** | x, y, width, height | Built, populated |
| **Auto-layout** | layout_mode, padding (4 sides), item_spacing, counter_axis_spacing, primary_align, counter_align, layout_sizing_h/v | Built, populated |
| **Auto-layout extensions** | layout_wrap, min/max width/height | Schema exists, extraction captures, **Dank DB needs migration** |
| **Visual fills/strokes/effects** | fills (JSON), strokes (JSON), effects (JSON) | Built, populated |
| **Corner radius** | corner_radius (number or per-corner JSON) | Built, populated |
| **Opacity/blend** | opacity, blend_mode, visible | Built, populated |
| **Stroke detail** | stroke_weight (uniform), stroke per-side weights (4), stroke_align, stroke_cap, stroke_join, dash_pattern | Schema exists, extraction captures, **Dank DB needs migration** |
| **Transform** | rotation, clips_content | Schema exists, extraction captures, **Dank DB needs migration** |
| **Constraints** | constraint_h, constraint_v | Schema exists, extraction captures, **Dank DB needs migration** |
| **Typography** | font_family, font_weight, font_size, font_style, line_height, letter_spacing, paragraph_spacing, text_align, text_align_v, text_decoration, text_case, text_content | Schema exists, some populated, font_style/text_align_v/text_decoration/text_case/paragraph_spacing **need migration** |
| **Component reference** | component_id (FK), component_key | Schema exists, extraction captures component_key, **but component_id never linked (components table empty)** |
| **Missing: layoutPositioning** | Whether a child is AUTO or ABSOLUTE within auto-layout parent | **Not in schema, not extracted**. Needed for stacked/absolute child positioning. |

**Critical gap — component_key**: The extraction JS correctly reads `node.mainComponent.key` for INSTANCE nodes (line 124 of `extract_screens.py`). The schema has the `component_key` column. But the Dank DB was created from an older schema missing the column. After migration, re-extraction will populate component keys for all 27,810 INSTANCE nodes. This unblocks Mode 1 rendering (component instantiation).

#### Token Data (`tokens`, `token_values`, `token_collections`, `token_modes` — 388 tokens)

Design tokens extracted from Figma's variable collections. Multi-mode support (Light, Dark, High Contrast).

| Table | What | Status |
|-------|------|--------|
| `token_collections` | Variable collections (Colors, Spacing, Typography, etc.) | Built, populated |
| `token_modes` | Modes per collection (Default, Dark, etc.) | Built, populated |
| `tokens` | Individual variables (name, type, collection, tier) | Built, populated |
| `token_values` | Per-mode resolved values, provenance tracking | Built, populated |

#### Binding Data (`node_token_bindings` — 182K rows)

Maps which node properties are bound to which tokens. This is what the IR's `style` section draws from (token refs only), and what the Figma renderer uses for Phase B variable rebinding.

| Column | What |
|--------|------|
| node_id | Which node |
| property | Which property (fill.0.color, fontSize, padding.top, etc.) |
| token_id | Which token it's bound to |
| raw_value | The raw value before resolution |
| resolved_value | The resolved value (following aliases) |
| binding_status | bound, unbound, overridden |

#### Component Data (EMPTY — needs population)

The schema defines rich component tables but none are populated:

| Table | Purpose | Status |
|-------|---------|--------|
| `components` | Master component definitions (name, figma_node_id, description, variant_properties) | **0 rows**. Extraction doesn't populate this — needs a component discovery pass. |
| `component_variants` | Individual variants of each component | **0 rows** |
| `variant_axes` | Variant dimensions (Size, State, Type) | **0 rows** |
| `variant_dimension_values` | Per-variant axis values (hover, large, solid) | **0 rows** |
| `component_slots` | Named insertion points per component | **0 rows**. Slots need to be defined for all 48 catalog types. |
| `component_a11y` | Accessibility contracts per component | **0 rows** |
| `component_responsive` | Responsive behavior per component | **0 rows** |
| `patterns` | Reusable composition recipes (screen-level patterns) | **0 rows** |

**What needs to happen**: A new extraction phase that discovers master components from the Figma file, enumerates their variants, and populates these tables. For INSTANCE nodes, this means:
1. Find all unique `mainComponent` references across all INSTANCE nodes
2. For each master component: extract its name, key, description, variant axes, and property definitions
3. Store in `components` + `variant_axes` + `variant_dimension_values`
4. Link INSTANCE nodes to their components via `component_id` and `component_key`

This data feeds both template extraction (Layer 2) and Mode 1 rendering (Layer 4).

#### Screen Data (`screens` — 338 rows)

One row per top-level frame in the Figma file (pages with multiple screens).

#### What Figma Extraction Does NOT Need to Capture

- Vector path data (SVG paths, boolean operations) — too low-level for the IR, and icons are rendered by instantiating Figma components
- Image raster data — referenced by hash/URL, not stored in DB
- Prototype connections — interaction data, deferred to v2
- Plugin data — third-party plugin state, not relevant
- Comments — Figma comments/annotations, separate concern

### React Extraction (NOT BUILT)

**Input**: React/TypeScript codebase (file system access)

**Output**: Store (SQLite or in-memory) with:

#### Component Definitions
For each exported React component found in the codebase:

| Field | Source | Example |
|-------|--------|---------|
| name | Export name | `Header`, `Button`, `ToggleRow` |
| file_path | File location | `src/components/ui/header.tsx` |
| catalog_type | Mapped from name/props (heuristic + user config) | `"header"` |
| props | TypeScript interface extraction | `[{name: "title", type: "string", required: true}, {name: "variant", type: "primary\|ghost", default: "primary"}]` |
| slots | Children/render prop analysis | `[{name: "leading", prop: "leftContent", type: "ReactNode"}]` |
| imports | What it imports | `["@radix-ui/react-slot", "./button"]` |
| library | Which library it belongs to | `"shadcn"`, `"custom"`, `"mui"` |

**How components are discovered:**
1. Scan for `.tsx`/`.jsx` files with exported functions/classes
2. Parse TypeScript types for prop interfaces (using ts-morph or AST)
3. Identify slots from `children` props, render props, and `ReactNode` typed props
4. Match component names to catalog types using name heuristics + configurable overrides

#### Component Usage (per page/route)
For each page component (identified by router configuration or file conventions like `app/page.tsx`):

| Field | Source | Example |
|-------|--------|---------|
| page_path | Route or file path | `/settings`, `app/settings/page.tsx` |
| component_tree | JSX nesting structure | `Header > [Button, SearchInput]`, `Section > [ToggleRow, ToggleRow]` |
| prop_values | Prop values passed in JSX | `title="Settings"`, `variant="primary"` |
| layout_hints | CSS flex/grid usage | `flex flex-col gap-4` → `direction: vertical, gap: 16` |

#### Token Usage
| Field | Source | Example |
|-------|--------|---------|
| token_name | CSS variable or Tailwind class | `--color-surface-primary`, `bg-surface-primary` |
| usage_locations | Where it's used | `header.tsx:12`, `button.tsx:34` |
| resolved_value | From tailwind.config or CSS | `#FAFAFA` |

**Extraction approach**: AST parsing via TypeScript compiler API or babel. NOT regex — components have complex nesting, generics, and conditional rendering. Libraries like `ts-morph` provide programmatic access to TypeScript's type system.

**Key difference from Figma extraction**: React extraction gives us EXPLICIT component structure (names, props, types) but NO visual properties (no fills, no pixel dimensions, no colors unless in CSS). The IR from React will have rich type/slot/prop data but sparse style data.

### Screenshot Extraction (NOT BUILT)

**Input**: One or more screenshot images (PNG/JPG) of UI screens

**Output**: Store with detected elements and spatial relationships

#### Element Detection
For each detected UI element:

| Field | Source | Example |
|-------|--------|---------|
| catalog_type | Vision model classification | `"button"`, `"header"`, `"card"` |
| confidence | Model confidence score | `0.92` |
| bounding_box | Pixel coordinates | `{x: 16, y: 738, width: 396, height: 48}` |
| text_content | OCR extraction | `"Settings"` |
| visual_samples | Color sampling from region | `{background: "#FFFFFF", text: "#000000", border: "#E0E0E0"}` |

#### Layout Inference
Spatial analysis to determine relationships:

| Field | How Derived | Example |
|-------|-------------|---------|
| parent_child | Containment detection (box A inside box B) | `header contains [icon, text, button]` |
| sibling_group | Aligned elements with consistent spacing | `[card, card, card]` at y=200, y=400, y=600 |
| layout_direction | Alignment axis of sibling groups | `"vertical"` (cards stacked) |
| spacing_estimate | Gap between siblings | `~16px` |

#### What Screenshot Extraction CANNOT Provide
- Internal component structure (what's inside a card vs. what IS the card)
- Token references (colors are sampled, not bound to variables)
- Font specifics (OCR can detect text but not font family/weight reliably)
- Component variants (can't distinguish "primary" from "secondary" button without seeing both)
- Interactive state (hover, pressed, disabled look similar in screenshots)

**Extraction approach**: Vision model pipeline. Options:
1. **OmniParser v2** — open-source UI element detection, good bounding boxes
2. **Custom YOLO model** — trained on UI datasets (Roboflow has 61 UI element classes)
3. **Claude Vision** — send screenshot, ask for structured component detection with bounding boxes
4. **Hybrid**: YOLO for detection + Claude for classification and OCR

**Key difference**: Screenshot extraction is the lowest-fidelity path. It produces approximate structure with confidence scores. The IR from screenshots will be sparser than from Figma or React. Useful for "recreate this in my design system" workflows where exact reproduction isn't the goal.

### Prompt Input (No Extraction)

**Input**: Natural language description ("I need a settings page with toggle sections")

A prompt doesn't require traditional extraction. The prompt IS the composition intent — it feeds directly into Layer 3 (Composition). However, the system needs a project CONTEXT to render into:

- **Existing Figma file**: The project's DB provides tokens, component vocabulary, and templates for rendering
- **Existing React codebase**: The project's component library provides the RendererConfig
- **No existing project**: The system uses pre-seeded default templates and a default token vocabulary

The prompt is parsed into structured intent (screen type, requested components, constraints) by Layer 3's composition logic, not by a Layer 1 extractor.

### Extraction Architecture Principles

1. **Greedy**: Capture everything the source provides. The analysis and rendering layers decide what matters. Extraction never filters or interprets — it records.

2. **Exhaustive over efficient**: It's better to extract a property you might not use than to need it later and not have it. Re-extraction is expensive (requires Figma API calls or re-parsing).

3. **Idempotent**: Re-running extraction on the same source produces the same DB state. Supports incremental updates (extract only changed screens).

4. **Schema-complete before extraction**: All columns must exist in the schema before extraction runs. The Dank DB's 26 missing columns demonstrate what happens when schema and extraction code diverge.

5. **Component discovery is separate from node extraction**: Node-level extraction captures properties per-node. Component discovery identifies master components, their variants, and their property definitions. These are different passes with different Figma API calls.

---

## Layer 2: Analysis

### Purpose
Read the extracted data and build abstractions at increasing levels. Analysis transforms raw platform-specific data into the vocabulary that the IR composes with. Each abstraction references back to the source data it was derived from.

### Two Levels of Abstraction

#### Level A: Component Vocabulary
"What components exist in this project, and how are they built?"

- **Input**: Extracted node tree + classifications
- **Output**: For each of the ~50 catalog types found in this project:
  - Which nodes are instances of this type (from classification: 93.6% coverage on Dank)
  - The canonical Figma structure: frame arrangement, auto-layout config, child positions — this is the **component template**
  - Visual defaults: typical fills, strokes, effects, radius for this type
  - Slot definitions: named insertion points (leading, title, trailing for a Header) — defined for all 48 catalog types
  - Figma component key: if this maps to a formal master component
  - Variants: the different visual/behavioral variants of this type (e.g., Button: primary, secondary, ghost, destructive)

- **Example**: "Header in this project = nav/top-nav (component key abc123). Horizontal auto-layout, 3 slots: Left (icon+label), Center (nav items), Right (action buttons). White background, background blur effect. 338 instances across all screens, 2 variants (with/without search)."

- **References back to DB**: Every component vocabulary entry points to specific node IDs, property values, and token bindings. The renderer uses these references to retrieve actual visual properties at render time.

#### Level B: Screen Patterns
"What screen-level patterns exist in this project?"

- **Input**: Component vocabulary + classified screens + skeleton notation
- **Output**: Recognized screen patterns:
  - Screen archetypes: settings, dashboard, chat, profile, search, list, detail, onboarding, etc.
  - For each archetype: the typical skeleton (component types in what arrangement)
  - Composition rules: what components commonly appear together, in what ratios
  - Spacing/rhythm conventions: typical gap sizes, padding patterns, content density

- **Example**: "Settings screen pattern (found in 12 screens): stack(header, scroll(section-group(2-4, toggle-rows + nav-rows)), bottom-nav). Average 3.2 sections per screen."

- **References back to vocabulary**: Every pattern references catalog types from Level A.

### Per-Source Analysis

#### From Figma
Both levels can be derived. The DB has enough information for component vocabulary (classification + template extraction) and screen patterns (skeleton extraction + screen clustering).

#### From React
- Level A: Map React component names to catalog types (heuristic + user config). Extract prop interfaces as slot/prop definitions.
- Level B: Analyze page components to identify screen patterns (which components compose each route).
- Less information than Figma (no visual properties, no pixel positions) but component structure is explicit.

#### From Screenshot
- Level A: Vision model recognizes component types with bounding boxes. No internal structure — each detection is a leaf, not a tree.
- Level B: Spatial analysis identifies screen archetype from component arrangement.
- Lowest fidelity. Good for "make something like this" but not for exact reconstruction.

#### From Prompt
- No analysis step. The prompt IS the composition intent. The system uses analysis from an EXISTING project (if available) to inform how to render the composition.

### Key Principle
Analysis is lossy by design. It compresses platform-specific detail into universal abstractions. "These 47 Figma nodes with specific auto-layout configs and pixel values" becomes "a Header with three slots." The lost detail isn't gone — it lives in the DB/store, and the renderer retrieves it when needed.

---

## Layer 3: Composition (The IR)

### Purpose
Express design intent as an abstract, platform-agnostic composition. The IR is the narrowest point in the system — it carries only what every platform needs to know, nothing more. It is the universal hub through which all translations pass.

### What the IR Carries

```
CompositionSpec
  version: string
  root: element ID
  tokens: { token.name → resolved value }       // for this project
  elements: {
    element-id: {
      type: string                               // from catalog (~50 types)
      children: [element IDs]                    // ordered child elements
      slots: { slot-name → [element IDs] }       // named insertion points
      props: {                                   // component-specific
        text: string                             // text content
        icon: string                             // icon name (canonical)
        variant: string                          // visual variant
        checked: boolean                         // state
        ...                                      // per catalog type
      }
      layout: {                                  // abstract flexbox (universal)
        direction: "horizontal" | "vertical" | "stacked"
        gap: "{token.ref}" | "none"              // semantic, not pixels
        padding: { top, right, bottom, left }    // token refs or semantic
        sizing: {
          width: "fill" | "hug" | "fixed"        // SEMANTIC, not pixels
          height: "fill" | "hug" | "fixed"       // renderer resolves to actual dimensions
        }
        mainAxisAlignment: string
        crossAxisAlignment: string
      }
      style: {                                   // token references ONLY
        backgroundColor: "{color.surface.primary}"
        textColor: "{color.text.primary}"
        borderColor: "{color.border.default}"
        ...
        // ONLY properties with token bindings appear here.
        // Unbound visual properties are NOT in the IR — the
        // renderer reads them from the DB or templates.
      }
      on: {                                      // basic interaction intent (v1)
        tap: { action: "navigate", target: "/settings" }
        toggle: { binds: "notifications.enabled" }
      }
      visible: condition                         // conditional rendering
      $platform: { ... }                         // escape hatch (rare)
    }
  }
```

### Resolved Decisions

#### Layout uses semantic sizing, not pixel values
The IR says `sizing: { width: "fill" }` not `sizing: { width: 428 }`. Pixel dimensions are platform-specific (428px is a phone screen in Figma, meaningless in responsive web). The renderer resolves semantic sizing to actual dimensions using the component template, the target viewport, or the source DB.

`direction: "stacked"` means children are overlaid/absolutely positioned. The IR doesn't carry x/y coordinates — the renderer determines positioning from the component template or source data.

#### Style contains token references only — renderer fills in unbound values
The IR style section is sparse. It ONLY contains properties that have token bindings:
```
// Node with token-bound background but unbound border:
style: { backgroundColor: "{color.surface.primary}" }
// borderColor is NOT here — no token binding for it
```
The renderer sees the token ref and resolves it. For properties NOT in the IR style section (unbound/literal values), the renderer reads the source DB directly, or uses template defaults if no source exists. This keeps the IR thin while ensuring complete visual output.

**Important**: Many Figma files have zero tokenized styles. The IR style section may be completely empty. The renderer still produces correct visual output by reading all values from the DB/templates.

#### Interaction intent is included at a basic level (v1)
The IR carries simple interaction semantics: "this is tappable," "this navigates to X," "this toggles Y." Complex interactions (swipe-to-delete, long-press, drag-and-drop) are deferred to `$platform` hints or future IR extensions.

#### The 48 catalog types are the right abstraction level
Types like `toggle-row`, `card`, `header`, `button` are concrete enough for renderers to map to specific implementations but abstract enough to translate across platforms. A `toggle-row` becomes a Switch inside a flex row in React, a Toggle with label in SwiftUI, and a specific frame structure in Figma.

### What the IR Does NOT Carry

| Excluded | Why | Where it lives instead |
|----------|-----|----------------------|
| Fill arrays, stroke objects, effects | Platform-specific rendering detail | DB nodes table or component template |
| Literal hex colors (#FF0000) | Not universal — renderer resolves per platform | DB token_values or node properties |
| Pixel dimensions (428px, 16px) | Viewport-dependent, not semantic | DB nodes table or component template |
| Font family/weight/size literals | May differ per platform | DB nodes table or renderer config |
| Corner radius, opacity values | Visual detail, not intent | DB nodes table or component template |
| Figma frame structure, auto-layout config | How to build, not what to build | Component templates in renderer config |
| x/y coordinates, constraints | Figma positioning model | DB nodes table |
| Component keys, instance overrides | Figma-specific references | DB components table |
| CSS class names, React import paths | Platform-specific | React renderer config |
| SwiftUI modifiers, Flutter widgets | Platform-specific | Respective renderer configs |

### How the IR Gets Created

#### From Figma (parsing an existing screen)
1. Classification identifies what each node IS (Header, Button, Card...)
2. Semantic tree construction groups classified nodes into component-level elements
3. Slot filling maps children to named slots based on position and type
4. Token references are inlined where bindings exist
5. Unclassified intermediate frames are absorbed — they're Figma implementation details
6. System chrome (status bar, home indicator) is excluded — device framing, not app design
7. Result: ~15-25 elements per screen, each a semantic component

#### From a Prompt (generating a new screen)
1. Parse intent: "homepage with cards" → screen type + requested components
2. Select screen pattern from Level B vocabulary (or compose from Level A components)
3. Fill slots: header gets logo + nav items, card-grid gets 6 cards with image/title/subtitle
4. Token references added from project's token vocabulary
5. Result: same ~15-25 element structure, but composed rather than parsed

#### From React (parsing a codebase)
1. AST analysis identifies component usage per page
2. Component names mapped to catalog types (Button → "button", Header → "header")
3. Props extracted and mapped to IR props/slots
4. Layout inferred from component nesting and flex/grid usage
5. Result: same IR structure, derived from code rather than pixels

#### From Screenshot (recognizing a design)
1. Vision model detects component bounding boxes with type labels
2. Spatial analysis infers layout (horizontal/vertical grouping, alignment)
3. OCR extracts text content
4. Color sampling suggests token mappings
5. Result: same IR structure, but lower confidence and fewer details

### The IR Is Valid at Any Completeness
All fields are optional. A prompt-generated IR might have types and slots but no token references. A screenshot-derived IR might have types and text but no layout details. A Figma-parsed IR will be the most complete. Renderers apply sensible defaults for missing fields — the component template provides the base, the IR provides overrides.

### Key Principle
The IR expresses what the designer MEANT, not how any platform implements it. "A Header with a back button and title" is intent. "A 428px wide frame with HORIZONTAL auto-layout, 15px padding, background blur, and three child frames" is Figma implementation. The IR carries the former. The renderer produces the latter.

---

## Layer 4: Rendering

### Purpose
Take an abstract IR composition and produce concrete output for a specific platform, in the style of a specific project. The renderer needs two inputs: the IR (what to build) and a RendererConfig (how to build it here).

### RendererConfig

Every renderer answers one question: **"For each of my ~50 catalog types, what is the implementation on this platform, in this project?"**

```
RendererConfig
  platform: "figma" | "react" | "swiftui" | "flutter" | "html"
  project: string                         // which project/design system
  componentMap: {                         // per catalog type
    "header": { ... platform-specific ... }
    "button": { ... platform-specific ... }
    ...
  }
  tokenResolver: {                        // how token refs become values
    format: "css-var" | "tailwind" | "figma-variable" | "swift-asset" | ...
    mapping: { token.name → platform value }
  }
  defaults: {                             // when no mapping exists
    unknownComponent: "frame" | "div" | "View"
    defaultFont: "Inter"
    defaultSpacing: 16
  }
```

### Per-Platform Rendering

#### Figma Renderer

**Config source**: Extracted from the DB by the analysis layer (Level A component templates). For new projects: pre-seeded default Figma component libraries shipped with the system.

```
FigmaRendererConfig
  componentMap: {
    "header": {
      componentKey: "abc123"              // for importComponentByKeyAsync
      frameStructure: { ... }             // auto-layout, padding, sizing
      visualDefaults: { fills, strokes, effects, radius }
      slotPositions: { leading: 0, title: 1, trailing: 2 }
      variants: { "with-search": {...}, "without-search": {...} }
    }
    ...
  }
  tokenResolver: {
    format: "figma-variable"
    variableIds: { "color.surface.primary" → "VariableID:123:456" }
  }
  dbConnection: sqlite3.Connection        // for reading unbound literal values
```

**Rendering process**:
1. Walk IR elements in tree order
2. For each element, look up its type in componentMap
3. If componentKey exists → `importComponentByKeyAsync(key)`, create instance, set overrides from IR props
4. If no componentKey → create frame structure from frameStructure template
5. Fill slots: insert child elements at slotPositions
6. Apply token references from IR style → resolve via tokenResolver, bind Figma variables
7. For visual properties NOT in IR style (unbound): read from DB if source node exists, or use visualDefaults from template
8. Apply layout from template (direction, padding, sizing resolved to actual pixel values)

**When source exists** (Figma→Figma, editing existing screens): renderer reads specific node visual properties from DB for unbound values.
**When no source exists** (Prompt→Figma, generating new screens): renderer uses component templates. Visual properties come entirely from template visualDefaults + token bindings.

#### React Renderer

**Config source**: Shipped presets (shadcn, MUI, Radix) or extracted from user's codebase.

```
ReactRendererConfig
  componentMap: {
    "header": {
      import: "@/components/ui/header"
      componentName: "Header"
      propMap: { title: "title", leading: "leftContent", trailing: "rightContent" }
      slotPattern: "children" | "named-props" | "render-props"
    }
    "button": {
      import: "@/components/ui/button"
      componentName: "Button"
      propMap: { variant: "variant", text: "children" }
      variantMap: { "primary": "default", "destructive": "destructive", "ghost": "ghost" }
    }
    ...
  }
  tokenResolver: {
    format: "css-var"
    prefix: "--"
    mapping: { "color.surface.primary" → "var(--color-surface-primary)" }
  }
```

**Rendering process**:
1. Walk IR elements in tree order
2. For each element, look up in componentMap → get import path, component name
3. Map IR props to React props via propMap
4. Map IR slots to React children/props (depends on slotPattern)
5. Map IR layout to wrapper elements or CSS classes (flex, gap, padding)
6. Map token refs via tokenResolver to CSS variables
7. Emit JSX + imports

**No DB needed.** React rendering is fully determined by the IR + config. The React component library already encapsulates visual implementation — the renderer just maps catalog types to library components and wires props.

#### SwiftUI Renderer

**Config source**: Framework mappings (mostly static, some per-project for custom components).

```
SwiftUIRendererConfig
  componentMap: {
    "header": {
      viewName: "NavigationStack"
      modifier: ".toolbar { ToolbarItem(placement: .navigationBarLeading) { $leading } }"
      slotPattern: "view-builder"
    }
    "button": {
      viewName: "Button"
      propMap: { text: "label", variant: "role" }
      variantMap: { "destructive": ".destructive", "primary": null }
    }
    ...
  }
  tokenResolver: {
    format: "swift-asset"
    mapping: { "color.surface.primary" → "Color(\"surfacePrimary\")" }
  }
```

#### HTML/Tailwind Renderer

**Config source**: Tailwind config + semantic HTML mappings.

```
HTMLRendererConfig
  componentMap: {
    "header": { element: "header", class: "flex items-center px-4 py-3" }
    "button": { element: "button", classMap: { primary: "bg-primary text-white", ghost: "bg-transparent" } }
    ...
  }
  tokenResolver: {
    format: "tailwind"
    mapping: { "color.surface.primary" → "bg-surface-primary" }
  }
```

### Key Principle
The renderer is mechanical. Given an IR element type and a config mapping, the output is deterministic. The creative/analytical work happens in Layers 2-3. Layer 4 is translation, not interpretation.

---

## Translation Paths

### Figma → IR → Figma (generate new screens matching existing design)

```
Figma file
  → L1: Extract → DB (86K nodes, 182K bindings, 388 tokens)
  → L2: Analyze → Component vocabulary (48 types classified, templates extracted)
                 → Screen patterns (settings, chat, dashboard, ...)
  → L3: User says "new settings page"
         → Select "settings" screen pattern
         → Compose IR: screen → [header, scroll([section, section, section]), bottom-nav]
         → Token refs from project vocabulary where bindings exist
  → L4: Figma renderer reads IR + FigmaRendererConfig
         → "header" → finds nav/top-nav (key abc123) → importComponentByKeyAsync
         → Fills slots from IR → sets title, leading icon, trailing actions
         → Resolves token refs → binds Figma variables
         → Unbound visual properties → reads from template visualDefaults
  → Output: New Figma screen that looks like it belongs to the existing file
```

### Prompt → IR → Figma (generate from natural language)

```
"Build me a dashboard with a sidebar and card grid"
  → L1: No extraction. But user must have a project context:
         EITHER an existing Figma file (→ use its analysis for L2 and its DB/templates for L4)
         OR select a pre-seeded default design system
  → L2: Analysis already done (from existing file or defaults loaded)
  → L3: Interpret prompt → compose IR
         → sidebar(nav-items) + main(header + card-grid(6, card(image, title, metric)))
         → Token refs from project's token vocabulary
  → L4: Figma renderer reads IR + templates
         → No source nodes in DB for this screen (it's new)
         → All visual properties from template visualDefaults + token bindings
  → Output: New Figma screen in the user's design language
```

### Figma → IR → React (design to code)

```
Figma file
  → L1: Extract → DB
  → L2: Analyze → Component vocabulary (classify screen's nodes)
  → L3: Build IR from classified screen
         → Semantic tree: header-1 with slots, sections with children
         → Token refs from bindings
  → L4: React renderer reads IR + ReactRendererConfig(shadcn)
         → "header" → import { Header } from "@/components/ui/header"
         → Maps IR slots to React props/children
         → Token refs → CSS variables
         → Unbound values → reads from DB, emits as literal CSS
  → Output: React components with imports, props, and token-bound styling
```

### React → IR → Figma (code to design)

```
React codebase
  → L1: Extract → Parse AST → store component tree, props, imports
  → L2: Analyze → Map React components to catalog types
         → <Header /> → "header", <Button variant="ghost" /> → "button"
  → L3: Build IR from parsed component tree
  → L4: Figma renderer reads IR + FigmaRendererConfig
         → Component templates from user's existing Figma file OR pre-seeded defaults
         → Builds Figma frames from templates, fills slots, binds tokens
  → Output: Figma file representing the React app's UI
```

### Screenshot → IR → Figma (reverse engineering)

```
Screenshot image
  → L1: Extract → Vision analysis (detect components, OCR, color sampling)
  → L2: Analyze → Map detections to catalog types (lower confidence)
  → L3: Build IR from detections (sparser — types and text, approximate layout)
  → L4: Figma renderer reads IR + templates
         → Builds from templates (no source DB)
         → Applies sampled colors / estimated dimensions
  → Output: Figma approximation — a starting point, not exact reproduction
```

### Prompt → IR → React (generate code from description)

```
"Build me a settings page with toggle sections"
  → L1: No extraction needed
  → L2: Use project's existing analysis (if codebase exists) OR defaults
  → L3: Compose IR from intent
  → L4: React renderer reads IR + ReactRendererConfig(shadcn)
         → Maps to library components, emits JSX + imports
  → Output: React component file(s) ready to use
```

### Figma → IR → SwiftUI (design to native mobile code)

```
Figma file
  → L1: Extract → DB
  → L2: Analyze → Component vocabulary
  → L3: Build IR from classified screen
  → L4: SwiftUI renderer reads IR + SwiftUIRendererConfig
         → "header" → NavigationStack + .toolbar
         → Token refs → Color("tokenName") from asset catalog
         → Layout: HStack/VStack/ZStack from IR direction
  → Output: SwiftUI View files with modifiers and asset references
```

---

## Deep Dive: How Renderers Work

### Component Template Schema

A component template captures HOW a catalog type is physically built on a specific platform. For Figma, this means the frame structure, auto-layout config, visual defaults, and slot-to-position mapping.

```
ComponentTemplate
  catalogType: string                      // "header", "button", "card"
  variant: string | null                   // "primary", "with-search", null for default

  // Source reference (how we found this template)
  source: {
    componentKey: string | null            // Figma component key for importComponentByKeyAsync
    representativeNodeId: number | null    // DB node ID of the canonical instance
    instanceCount: number                  // how many instances informed this template
  }

  // Frame structure (the physical Figma tree)
  structure: {
    layoutMode: "HORIZONTAL" | "VERTICAL" | "NONE"
    sizing: { width: number, height: number }        // default dimensions
    padding: { top, right, bottom, left }             // from auto-layout
    itemSpacing: number | null
    primaryAxisAlignment: string | null
    counterAxisAlignment: string | null
    cornerRadius: number | null
  }

  // Visual defaults (applied when no source node or token exists)
  visual: {
    fills: [{ type: "SOLID", color: "#FFFFFF", opacity: 1.0 }]
    strokes: [...]
    effects: [{ type: "BACKGROUND_BLUR", radius: 15.0 }]
    opacity: number
  }

  // Slot-to-position mapping (which child index = which slot)
  slots: {
    "leading":  { childIndex: 0, defaultWidth: 130, defaultHeight: 64 }
    "title":    { childIndex: 1, defaultWidth: 182, defaultHeight: 64 }
    "trailing": { childIndex: 2, defaultWidth: 130, defaultHeight: 64 }
  }
```

Templates are extracted by Layer 2 (Analysis) from classified instances. When multiple instances of the same type exist (e.g., 338 headers across 338 screens), the template captures the MOST COMMON structure — the mode, not the mean. Variants are captured as separate templates.

### The Two Figma Generation Modes

The Figma renderer operates in two fundamentally different modes depending on whether a component key is available:

**Mode 1: Component Instantiation (high fidelity)**
When the template has a `componentKey` (the source was a formal Figma component):
1. Call `figma.importComponentByKeyAsync(key)` → get the master component
2. Create an instance → inherits the full frame structure, auto-layout, visual properties
3. Set overrides from IR props: text content, icon swaps, variant selection, visibility toggles
4. Bind token variables via `setBoundVariable` for tokenized properties
5. The instance looks exactly like the designer's original because it IS the original component

This is the preferred path. It produces pixel-perfect output because it uses the designer's actual components. Most INSTANCE nodes in a well-structured Figma file will have component keys.

**Mode 2: Template Construction (lower fidelity, but works without component library)**
When no `componentKey` exists (informal components, or pre-seeded defaults):
1. Create a frame: `figma.createFrame()`
2. Apply structure from template: `layoutMode`, padding, sizing, alignment
3. Apply visual defaults from template: fills, strokes, effects, radius
4. Create child frames for each slot, sized per template slot definitions
5. Recursively render child IR elements into their slot positions
6. Bind token variables where IR style has token refs
7. Read unbound visual properties from DB (if source exists) or leave template defaults

This mode produces functional but potentially less polished output. It's used for:
- Generating from prompt (no source Figma file for new elements)
- Informal components that aren't formal Figma components
- Pre-seeded default libraries

### Figma Renderer Algorithm (detailed)

```
function renderToFigma(spec: CompositionSpec, config: FigmaRendererConfig):

  nodeMap = {}  // IR element ID → created Figma node ID

  // Phase A: Create all elements (BFS from root)
  for each element in BFS(spec.root, spec.elements):
    template = config.componentMap[element.type]

    if template and template.source.componentKey:
      // MODE 1: Instantiate real component
      masterComponent = await figma.importComponentByKeyAsync(template.source.componentKey)
      node = masterComponent.createInstance()

      // Apply variant selection from IR props
      if element.props.variant and template.variants:
        applyVariantProperties(node, element.props.variant, template.variants)

      // Set text/boolean overrides from IR props
      for prop in element.props:
        setComponentProperty(node, prop.name, prop.value)

    else:
      // MODE 2: Construct from template
      node = figma.createFrame()
      applyTemplateStructure(node, template.structure)
      applyTemplateVisuals(node, template.visual)

    // Name the node for debugging/mapping
    node.name = element.id

    // Parent it
    if element has parent in nodeMap:
      parentNode = figma.getNodeById(nodeMap[parent.id])
      parentNode.appendChild(node)

    nodeMap[element.id] = node.id

  // Phase B: Apply token bindings
  for each element in spec.elements:
    node = figma.getNodeById(nodeMap[element.id])

    for each (property, tokenRef) in element.style:
      tokenName = extractTokenName(tokenRef)   // "{color.primary}" → "color.primary"
      variableId = config.tokenResolver.variableIds[tokenName]

      if variableId:
        variable = figma.variables.getVariableById(variableId)
        bindVariable(node, property, variable)  // setBoundVariable / setBoundVariableForPaint

    // For unbound visual properties: read from DB
    if config.dbConnection and element has source node:
      sourceNode = queryNodeVisuals(config.dbConnection, element.sourceNodeId)
      applyUnboundVisuals(node, sourceNode)

  // Phase C: Slot filling (for Mode 2 nodes)
  for each element with slots in spec.elements:
    if element was Mode 2 (template construction):
      for each (slotName, childIds) in element.slots:
        slotPosition = template.slots[slotName]
        for childId in childIds:
          childNode = figma.getNodeById(nodeMap[childId])
          // Reparent child into the slot's position
          insertChildAtSlot(parentNode, childNode, slotPosition)

  return nodeMap  // for future reference / rebinding
```

### Semantic Tree Construction Algorithm

This is how Layer 3 transforms 200 classified Figma nodes into ~20 semantic IR elements.

**Input**: Classified nodes from DB (each has canonical_type, parent_id, bindings), slot definitions from catalog.

**Output**: Flat element map with ~15-25 elements, each with filled slots.

```
Algorithm: buildSemanticTree(classifiedNodes, slotDefinitions)

  // Step 1: Build the Figma parent-child tree
  // Use actual parent_id (Figma layer tree), NOT classification parent_instance_id
  figmaTree = buildTree(classifiedNodes, using: node.parent_id)

  // Step 2: Identify "component roots" — classified nodes that represent
  // complete components (not internal parts of a parent component)
  //
  // A node is a component root if:
  //   - It has no classified ancestor, OR
  //   - Its nearest classified ancestor's slot definitions accept this type
  //
  // Example: An icon inside a header is NOT a root — it fills the header's
  // leading slot. A header inside a screen IS a root — it's a top-level
  // component of the screen.

  componentRoots = []
  for node in classifiedNodes:
    nearestClassifiedAncestor = walkUpTree(node, until: classified)

    if nearestClassifiedAncestor is None:
      componentRoots.append(node)  // top-level component
    elif nodeTypeMatchesAnySlot(node.type, nearestClassifiedAncestor.type, slotDefinitions):
      // This node fills a slot of its ancestor — it's a slot fill, not a root
      assignToSlot(nearestClassifiedAncestor, node, slotDefinitions)
    else:
      componentRoots.append(node)  // doesn't fit any slot — treat as root

  // Step 3: Filter system chrome
  // Status bars, home indicators, Safari chrome, etc. are device framing,
  // not app design. Identified by is_system_chrome() heuristic.
  componentRoots = [n for n in componentRoots if not isSystemChrome(n)]

  // Step 4: Absorb unclassified intermediate frames
  // Figma trees often have "Frame 359" structural wrappers between
  // components. These are Figma implementation details.
  // They DON'T become IR elements — their layout properties are absorbed
  // into the parent component's template.
  //
  // Example: Header → Frame "Left" → icon/back
  // The "Left" frame is absorbed. The icon goes into Header.leading slot.

  // Step 5: Build IR elements
  for each componentRoot:
    element = {
      type: componentRoot.canonical_type,
      slots: assignedSlots[componentRoot],     // from Step 2
      props: extractProps(componentRoot),       // text content, icon name, variant
      layout: extractSemanticLayout(componentRoot),  // direction, gap, sizing
      style: extractTokenRefs(componentRoot),   // token refs only
    }
    elements[generateElementId(element.type)] = element

  // Step 6: Wire parent-children at the IR level
  // Component roots that share a Figma parent become siblings in the IR
  // Grouped under a screen root element
  screenRoot = { type: "screen", children: [root element IDs] }

  return CompositionSpec(root: screenRoot.id, elements: allElements)
```

**Key insight**: The algorithm walks the Figma tree (parent_id) to determine spatial containment, but uses classification (canonical_type) to determine semantic role. Unclassified nodes are absorbed as structural glue. Classified nodes either become component roots or fill slots of their classified ancestors.

### Token Resolution Flow

The full chain from token reference in the IR to platform-specific output:

```
IR element: { style: { backgroundColor: "{color.surface.primary}" } }
                                    │
                                    ▼
                    Renderer extracts token name
                    "color.surface.primary"
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
         Figma Renderer       React Renderer       SwiftUI Renderer
              │                     │                     │
              ▼                     ▼                     ▼
    config.tokenResolver     config.tokenResolver     config.tokenResolver
    format: figma-variable   format: css-var          format: swift-asset
              │                     │                     │
              ▼                     ▼                     ▼
    variableIds lookup       mapping lookup           mapping lookup
    "VariableID:123:456"     "var(--color-surface-    "Color(\"surface
              │                primary)"               Primary\")"
              ▼                     │                     │
    figma.variables              │                     │
      .getVariableById()         │                     │
              │                     │                     │
              ▼                     ▼                     ▼
    setBoundVariableForPaint  emit in JSX style       emit as modifier
    (node, variable)          attribute                .background(Color(...))
```

**When no token binding exists** (the property isn't in IR style):
```
IR element: { style: {} }    // no backgroundColor token ref
                │
                ▼
    Renderer checks: is there a source node in DB?
                │
         ┌──────┴──────┐
         YES            NO
         │              │
         ▼              ▼
    Read from DB     Read from template
    node.fills →     template.visual.fills →
    literal color    default color
         │              │
         ▼              ▼
    Apply directly   Apply as default
    (no variable     (no variable
     binding)         binding)
```

### Asset and Icon Resolution

Icons and images are catalog types (`icon`, `image`) with platform-agnostic references in the IR. Each platform resolves them differently.

**In the IR:**
```json
{
  "type": "icon",
  "props": {
    "icon": "back",           // canonical name from vocabulary
    "size": "medium"          // semantic size, not pixels
  }
}
```

**Figma resolution:**
- Analysis extracts: `icon/back` component → component key `abc123`
- Renderer: `importComponentByKeyAsync("abc123")` → creates instance
- The icon's vector paths come from the component instance, not the IR
- If no component key: create an empty placeholder frame (icon content can't be reconstructed from the IR alone)

**React resolution:**
- Config maps: `"back"` → `{ import: "lucide-react", component: "ArrowLeft" }`
- Renderer: `import { ArrowLeft } from "lucide-react"` → `<ArrowLeft size={20} />`

**SwiftUI resolution:**
- Config maps: `"back"` → `Image(systemName: "chevron.left")`
- Uses SF Symbols system

**Image elements:**
```json
{
  "type": "image",
  "props": {
    "src": "hero-banner",     // asset key
    "alt": "Welcome banner"
  }
}
```
Asset keys are resolved via an asset manifest (per project):
- Figma: image hash → fill with image paint
- React: `"/images/hero-banner.jpg"`
- SwiftUI: `Image("heroBanner")` from asset catalog

**Key constraint**: Vector paths and raster image data are NOT in the IR. They're platform-specific binary assets. The IR carries only the semantic reference (icon name, asset key). The renderer resolves to the actual asset via the config or asset manifest.

### Element-to-Node Mapping

After the renderer creates Figma nodes from IR elements, the system needs a persistent mapping for:
- **Token rebinding**: Phase B needs to find the created nodes to bind variables
- **Future editing**: If the user asks "change the header," the system needs to find which Figma node is the header
- **Incremental updates**: Modifying one IR element should update only the corresponding Figma node

**The mapping is maintained as:**
```
nodeMap: { IR element ID → Figma node ID }

Example:
  "header-1"    → "5507:28"
  "button-1"    → "5507:26"
  "icon-1"      → "5507:32"
```

**Storage**: The `nodeMap` is returned by the renderer after execution. For persistence, it can be:
- Stored in `figma.root.setPluginData("nodeMap", JSON.stringify(map))` for same-session access
- Written to a new DB table (`ir_element_node_map`) for cross-session persistence
- Embedded in the Figma node names (element IDs are already used as node names)

**For Mode 1 (component instantiation)**: The node ID comes from the created instance.
**For Mode 2 (template construction)**: The node ID comes from the created frame.

**Slot children**: The mapping includes ALL IR elements, including those that fill slots. An icon inside a header's leading slot has its own entry: `"icon-1" → "5507:35"`.

**Rebinding uses the mapping:**
```
for each (elementId, property, tokenName) in tokenRefs:
  figmaNodeId = nodeMap[elementId]
  variableId = config.tokenResolver.variableIds[tokenName]
  node = figma.getNodeById(figmaNodeId)
  bindVariable(node, property, variable)
```

---

## The RendererConfig Lifecycle

### Where Configs Come From

| Config Type | Source | When Created | Persistence |
|------------|--------|--------------|-------------|
| Figma (existing project) | Extracted from DB by analysis (L2) | After classification + template extraction | Stored in DB or cached file |
| Figma (new project) | Pre-seeded default library | Shipped with system | Static, versioned |
| Figma (user's design system) | Imported from published Figma library | User-initiated | Stored in project config |
| React + shadcn | Shipped preset | Built into system | Static, versioned |
| React + MUI | Shipped preset | Built into system | Static, versioned |
| React + custom | Extracted from user's codebase | User-initiated or auto-detected | Stored in project config |
| SwiftUI | Framework mapping | Built into system | Static, versioned |
| HTML + Tailwind | Tailwind config mapping | Built into system / from tailwind.config | Static or project-specific |

### Config Evolution

A project's Figma RendererConfig evolves:
1. **First extraction**: Analyze the file, classify components, extract templates. Config is auto-generated.
2. **User customizes**: Overrides template defaults, adds custom component mappings, adjusts slot definitions.
3. **File evolves**: Designer adds new screens/components. Re-run analysis to update vocabulary and templates. Config is incrementally updated — user customizations are preserved, new types are added.
4. **Cross-project**: Templates from one project can seed another. "Use Dank's button style for my new project."

---

## The DB's Role

The DB is the **Figma parser's working storage** — the output of Layer 1 for Figma inputs specifically. Other parsers (React AST, screenshot vision) have their own storage formats.

The DB serves double duty in Figma workflows:
- **Layer 2 (Analysis) reads it** to build component vocabulary and extract templates
- **Layer 4 (Figma Renderer) reads it** to get unbound visual properties when reconstructing elements

This dual role is specific to Figma paths. For Prompt→Figma, the renderer reads templates (extracted from DB earlier) but not the DB directly for new elements. For Figma→React, the DB is read by analysis and by the React renderer for unbound literal values — but the React renderer could also read them from the templates.

### DB Tables and Their Layer

| Table | Layer 1 (Extraction) | Layer 2 (Analysis) | Layer 4 (Rendering) |
|-------|---------------------|-------------------|--------------------------|
| `nodes` | Written | Read for classification | Read for unbound visual properties |
| `node_token_bindings` | Written | Read for token mapping | Read for variable rebinding |
| `tokens` / `token_values` | Written | Read for vocabulary | Read for token resolution |
| `screens` | Written | Read for pattern analysis | Read for screen dimensions |
| `components` | Written | Read for formal matching | Read for component keys |
| `screen_component_instances` | — | Written by classification | Read for element→node mapping |
| `component_type_catalog` | — | Written (seeded) | Read for type validation |
| Component templates (NEW) | — | Written by template extraction | Read for frame structure + visual defaults |

---

## Slot Definitions

Slots are named insertion points within a component. They define WHERE children go and WHAT types of children are allowed. Slots are defined for ALL 48 catalog types in the `component_type_catalog`.

### Examples

```
Header:
  slots:
    leading:   { allowed: [icon, button, image], quantity: "single" }
    title:     { allowed: [text, heading], quantity: "single" }
    trailing:  { allowed: [icon, button, image], quantity: "multiple" }

Card:
  slots:
    media:    { allowed: [image, video], quantity: "single" }
    content:  { allowed: [text, heading, badge], quantity: "multiple" }
    actions:  { allowed: [button, icon_button], quantity: "multiple" }

ToggleRow:
  slots:
    label:    { allowed: [text], quantity: "single" }
    subtitle: { allowed: [text], quantity: "single" }
    control:  { allowed: [toggle, checkbox], quantity: "single" }
```

### How Slots Work in the Loop

- **Layer 2 (Analysis)**: Classification identifies nodes. Semantic tree construction assigns classified children to their parent's named slots based on position, type match, and the Figma parent_id tree.
- **Layer 3 (IR)**: The element carries `slots: { leading: ["icon-1"], title: ["heading-1"] }`. Each slot value is a list of element IDs.
- **Layer 4 (Rendering)**: The renderer's component template knows the slot→position mapping. "Leading slot content goes in child index 0 of the frame."

---

## Future Extensions

The following capabilities are part of the broader vision but are NOT required for the core four-layer loop to function. They can be designed and integrated later without changing the fundamental architecture.

### Taste Model
Quality-weighted distributions derived from a curated corpus. Informs composition choices (Layer 3) — e.g., "Settings screens in high-quality apps tend to use 3 sections with 4-6 rows each." Would be built as a separate pipeline (corpus → analysis → taste model) and shipped as a versioned package (~1-2MB). The four-layer architecture doesn't depend on it.

### Autonomous Exploration (Pattern Language Meta-Process)
An orchestration layer that uses the four-layer architecture iteratively: compose multiple IR variants, render each, critique via vision model, prune weak options, present top 2-3 to user. This sits ABOVE the four layers as an agent loop, not inside them. Each iteration is a full L3→L4 pass.

### Decision Tree
Records exploration history as first-class data — which compositions were tried, which were selected, which were rejected and why. Enables non-destructive design exploration and user steering ("go back to option B but with the spacing from option A"). Would be a new schema alongside the IR, not part of it.

### Bidirectional Sync
If a user generates a screen from the IR then manually edits it in Figma, detecting what changed and updating the IR. Requires maintaining a mapping from IR elements to generated Figma nodes. A hard problem — essentially incremental re-parsing.

---

## What's Already Built (Capability Inventory)

38 Python modules, 1,004 tests. Full module API reference in `docs/module-reference.md`.

### Layer 1: Extraction — BUILT (6 modules, ~126 tests)

| Module | What it does | Tests |
|--------|-------------|-------|
| `dd/extract.py` | Orchestrator — coordinates screen extraction + component extraction | 31 |
| `dd/extract_screens.py` | Generates Figma Plugin JS to extract full node trees (40+ properties per node) | 19 |
| `dd/extract_bindings.py` | Normalizes Figma properties into token binding rows (fills, strokes, effects, typography, spacing, radius) | 9 |
| `dd/extract_inventory.py` | Discovers screens in a Figma file, manages extraction runs | - |
| `dd/extract_components.py` | **Complete component pipeline** — parses COMPONENT_SET/COMPONENT nodes, extracts variants, infers slots, generates a11y contracts | 40 |
| `dd/figma_api.py` | Figma REST API + MCP bridge | 27 |

**Component extraction (`extract_components.py`) is fully built but never run on Dank:**
- `parse_component_set()` — extracts variants, builds axes, detects interaction states (hover/pressed/disabled)
- `infer_slots()` — identifies slot children, filters structural noise (background, divider, spacer), assigns types (text/icon/component/image)
- `infer_a11y()` — generates accessibility contracts per component (role, required label, touch target, ARIA properties)
- `insert_component/variants/axes/slots/a11y()` — populates ALL composition tables
- `populate_variant_dimension_values()` — cross-product table enabling queries like "all hover variants across all buttons"
- **All 6 composition tables are EMPTY** in Dank DB because this module hasn't been run. Running it would populate: `components`, `component_variants`, `variant_axes`, `variant_dimension_values`, `component_slots`, `component_a11y`.

**Normalization (`dd/normalize.py`, 34 tests)** — converts Figma properties to hierarchical binding rows:
- `normalize_fill()` — SOLID → `fill.N.color`, GRADIENT → `fill.N.gradient` + stop colors
- `normalize_stroke()` — SOLID → `stroke.N.color`
- `normalize_effect()` — SHADOW → `.color/.radius/.offsetX/.offsetY/.spread`, BLUR → `.radius`
- `normalize_typography()` — fontSize, fontFamily, fontWeight, lineHeight, letterSpacing
- `normalize_spacing()` — padding (4 sides), itemSpacing, counterAxisSpacing
- `normalize_radius()` — cornerRadius (uniform) or per-corner
- `normalize_stroke_weight()` — uniform or per-side
- `normalize_paragraph_spacing()`, `normalize_font_style()`

### Layer 2: Analysis — PARTIALLY BUILT (11 modules, ~260 tests)

**Classification (7 modules, ~150 tests)**:
| Module | What it does | Tests |
|--------|-------------|-------|
| `dd/catalog.py` | 48 canonical types with behavioral descriptions, aliases, recognition heuristics | 50 |
| `dd/classify.py` | Orchestrator — formal matching (name → alias index), parent linkage | 64 |
| `dd/classify_rules.py` | ALL heuristic rules (single file): header, bottom-nav, heading, body-text, generic-frame-container | - |
| `dd/classify_heuristics.py` | Applies rules to unclassified nodes, fetches fills/strokes/effects for visual property check | - |
| `dd/classify_llm.py` | Claude Haiku for ambiguous nodes (prompt builder + response parser) | 14 |
| `dd/classify_vision.py` | Screenshot-based cross-validation with retry/backoff | 8 |
| `dd/classify_skeleton.py` | Screen-level skeleton notation | - |

**Classification pipeline**: Formal (55%) → Heuristic (37%) → LLM (7%) = **93.6% adjusted coverage on Dank** (47,292 of 50,517 classifiable nodes).

**Token analysis (4 modules, ~110 tests)**:
| Module | What it does | Tests |
|--------|-------------|-------|
| `dd/cluster.py` + `dd/cluster_*.py` | Token clustering by perceptual similarity (5 type-specific modules) | 38+ |
| `dd/curate.py` | Agent-driven curation: rename, merge, split, alias, accept, reject | 31 |
| `dd/modes.py` | **OKLCH-based mode derivation** — dark, compact, high-contrast modes | 22 |
| `dd/drift.py` | **Value drift detection** — DB vs Figma sync state | 28 |

**Color clustering algorithm** (`cluster_colors.py`):
1. Query unbound color bindings grouped by resolved hex value
2. Group by OKLCH delta-E perceptual similarity (threshold 2.0 = just-noticeable difference)
3. Different alpha values NEVER cluster (e.g., `#000000` and `#00000020` are separate tokens)
4. Most-used color becomes group representative
5. Confidence per binding: `max(0.8, 1.0 - delta_e / 10)`

**OKLCH mode derivation** (`modes.py`):
- `create_dark_mode()`: Copy default values → invert lightness (`L' = 1.0 - L`), clamp chroma (`min(C, 0.4)`)
- `create_compact_mode()`: Scale all dimensions by factor (default 0.875 = 12.5% reduction)
- `create_high_contrast_mode()`: Light colors brighter (`L * 1.2 + 0.1`), dark colors darker (`L * 0.6`), chroma boosted
- `create_theme()`: Apply transform across ALL collections in a file
- **Color space**: OKLCH via coloraide library with full manual fallback (sRGB → Linear RGB → XYZ D65 → OKLAB → OKLCH)

**Drift detection** (`drift.py`):
- `detect_drift()`: Parse Figma variables response → compare with DB → update sync statuses → generate report
- **Type-aware normalization**: Handles JSON dimension objects (`{"value":24,"unit":"PIXELS"}` → `24`), Figma float32 noise (`10.000000149` → `10`), hex format differences
- **Sync states**: pending → synced / drifted / code_only / figma_only

**What's missing for Layer 2**: Component template extraction (how each type is physically built), screen pattern recognition (clustering screens into archetypes like "settings", "dashboard", "chat").

### Layer 3: Composition — PARTIALLY BUILT (1 module, 64 tests)

| Module | What it does | Tests |
|--------|-------------|-------|
| `dd/ir.py` | IR generation — `map_node_to_element`, `build_composition_spec`, normalization functions | 64 |

**What's built**: Flat element map from classified nodes, token ref inlining, container injection for unclassified parent frames, visual property normalization (fills, strokes, effects, corner radius via `normalize_fills/strokes/effects/corner_radius`).

**What needs to change**: IR is currently too thick (carries visual data that should be in DB/renderer). Semantic tree construction (200→20 elements) not implemented. Slot filling not implemented. The IR should carry only type + children/slots + props + layout + token refs.

### Layer 4: Rendering — SUBSTANTIALLY BUILT (7 modules, ~288 tests)

**Figma generation (1 module, 51 tests)**:
| Module | What it does | Tests |
|--------|-------------|-------|
| `dd/generate.py` | Figma Plugin JS generation from CompositionSpec (BFS walk, layout + visual + text emission) | 51 |

**Token export — code renderers' token resolution (3 modules, ~46 tests)**:
| Module | What it does | Tests |
|--------|-------------|-------|
| `dd/export_css.py` | Token export to CSS custom properties | 46 |
| `dd/export_tailwind.py` | Token export to Tailwind config | (incl.) |
| `dd/export_dtcg.py` | Token export to W3C DTCG format | (incl.) |

These are the `tokenResolver` for React/HTML renderers. The CSS export produces `--color-surface-primary: #FAFAFA` — exactly what a React renderer needs for `var(--color-surface-primary)`. **The code-side token resolution is substantially solved.**

**Figma variable push + rebind (3 modules, ~141 tests)**:
| Module | What it does | Tests |
|--------|-------------|-------|
| `dd/export_figma_vars.py` | Push tokens to Figma as variables (batched at 100 per MCP call) | 50 |
| `dd/export_rebind.py` | Generate compact rebind scripts (182K bindings, 950 per script, ~191 scripts) | 55 |
| `dd/push.py` | Orchestrate full push cycle (variables → rebind), incremental sync with drift detection | 36 |

**This is the Figma renderer's variable binding infrastructure — fully operational:**
- **Variable push**: 388 tokens → Figma variables across 8 collections, batched at 100 per `figma_setup_design_tokens` call. Supports first push (all CREATE) and incremental sync (CREATE/UPDATE/DELETE based on drift detection).
- **Rebind**: 182K node properties → bound to Figma variables. Compact pipe-delimited encoding (`nodeId|propertyCode|variableIdSuffix`) achieves 60% size reduction. Property shortcodes: `f0` (fill.0.color), `fs` (fontSize), `pt` (padding.top), `cr` (cornerRadius), etc.
- **Writeback**: After Figma creates variables, IDs are written back to DB (`tokens.figma_variable_id`, `token_collections.figma_id`, `token_modes.figma_mode_id`).
- **Execution**: Scripts run via `figma_execute` MCP (50K char limit) or PROXY_EXECUTE WebSocket (no limit). Inter-script delay: 200ms. Total time: ~108 seconds for 191 scripts.
- **Error handling**: Failed bindings stored in `figma.root.pluginData('rebind_errors')` for debugging. Scripts are idempotent (safe to re-run).

**What needs to change**: Generator currently reads visual data from IR instead of DB/templates. No React/SwiftUI code generators yet. No RendererConfig abstraction. But the token resolution (CSS/Tailwind export) and variable binding (push/rebind) infrastructure is proven at scale.

### Supporting Infrastructure (4 modules, ~86 tests)

| Module | What it does | Tests |
|--------|-------------|-------|
| `dd/color.py` | Color conversions: hex↔RGBA↔OKLCH, delta-E distance, lightness inversion | 28 |
| `dd/validate.py` | 8 validation checks (mode completeness, DTCG compliance, binding consistency, etc.) | 20 |
| `dd/status.py` | Dashboard data: token counts by tier, binding coverage, sync status summary | 18 |
| `dd/db.py` / `dd/cli.py` / `dd/config.py` / `dd/types.py` | Schema init, CLI commands, configuration, constants | 19 |

### Schema Status
`schema.sql` defines ALL needed tables:
- **Populated in Dank DB**: `nodes` (86K, but missing 26 extended columns), `node_token_bindings` (182K), `tokens` (388), `token_values`, `token_collections`, `token_modes`, `screens` (338), `screen_component_instances` (47K)
- **Empty in Dank DB (schema exists, code exists, just needs to be run)**: `components`, `component_variants`, `variant_axes`, `variant_dimension_values`, `component_slots`, `component_a11y`, `component_responsive`, `patterns`
- **Missing from Dank DB (needs migration)**: 26 columns on `nodes` table that exist in schema.sql but not in the older Dank DB

---

## Resolved Decisions (from Steelmanning, 2026-04-02)

### 1. Un-tokenized Visual Values — Synthetic Tokens
**Challenge**: Real Figma files have many un-tokenized values (hardcoded colors, one-off shadows). The thin IR only carries token refs. These values would be lost.

**Decision**: The analysis layer creates **synthetic tokens** for ALL visual values, not just Figma-variable-bound ones. Synthetic tokens are internal — they exist in the DB for rendering but are never exported to Figma variables or CSS.

**Implementation**:
- New tier: `synthetic` in `tokens.tier` (alongside `extracted`, `curated`, `aliased`)
- Naming convention: `_` prefix (e.g., `_syn.color.surface.1`) — DTCG-non-compliant, so never confused with real tokens
- Invisible to curation/export (those filter by `curated`/`aliased`)
- The IR's `tokens` dictionary carries resolved values for both real and synthetic tokens — the renderer has one code path (resolve ref → get value)
- **Promotable**: Users can promote synthetic → extracted → curated if they decide a value should be a real design token. This turns "un-tokenized value discovery" into a feature.
- Token count stays manageable via clustering (86K nodes → ~200-300 unique visual values → ~50-80 synthetic tokens after delta-E grouping)

### 2. Semantic Sizing — Responsive Breakpoints
**Challenge**: `sizing: { width: "fill" }` works, but real designs need different sizing at different viewports. A card is "fixed" on phone but "fill" on tablet.

**Decision**: The IR carries **responsive sizing hints per breakpoint class**. No raw pixel values.

```json
"sizing": {
  "width": { "default": "fixed", "tablet": "fill", "desktop": "fill" },
  "height": "hug"
}
```

Templates carry default pixel dimensions for "fixed" elements. The renderer resolves breakpoint classes to platform-appropriate thresholds. Exact schema deferred to responsive implementation phase, but the decision is made: **the IR is responsive-aware, not single-viewport**.

### 3. Semantic Tree Construction — Tractable
**Challenge**: Can we collapse 200 Figma nodes to ~20 IR elements without losing structure?

**Decision**: Yes. Analysis of screen 184 confirms clean boundaries:
- Depth 0: screen frame → IR root (always)
- Depth 1: system chrome (Safari bar, StatusBar, HomeIndicator) → filtered by `is_system_chrome()`
- Depth 1-2: classified components (header, button, container) → IR elements
- Depth 3+: vectors, ellipses, boolean operations (76 nodes) → absorbed into nearest classified ancestor (icon internals)
- Unclassified intermediate frames → structural glue, absorbed into parent component

Algorithm: walk Figma `parent_id` chain. If node A is classified and node B is classified and B is inside A's subtree, B becomes a slot fill of A. All unclassified nodes between them are A's implementation detail. 93.6% classification coverage is sufficient — the 6.4% are system chrome or leaf drawing primitives.

### 4. RendererConfig — Conceptual Pattern, Not Shared Interface
**Challenge**: Figma and React renderer configs have fundamentally different shapes. Is a shared interface useful?

**Decision**: Conceptual pattern only. Each renderer defines its own config type. The documented pattern is: "for each catalog type, provide an implementation mapping." No shared base class or interface — that's premature abstraction. We can extract shared interfaces later if a real need emerges.

### 5. Component Templates — Two Rendering Strategies
**Challenge**: Not all components are importable Figma instances. Some are informal patterns without component keys.

**Decision**: Templates carry TWO strategies:
1. **Instance path** (preferred): If `componentKey` exists → `importComponentByKeyAsync(key)`, create instance, set overrides. Maintains design system integrity — generated instances update when master changes.
2. **Frame path** (fallback): If no key or import fails → construct from `frameStructure` template. Raw frames with auto-layout and visual properties.

Renderer always tries instance path first. Falls back to frame path automatically.

### 6. Missing Component Types — Default Library Fallback
**Challenge**: IR requests a type (e.g., "date-picker") that doesn't exist in the user's Figma file.

**Decision**: Resolution chain:
1. **Project template** (from user's file) — highest fidelity
2. **Default library template** (shipped with system) — generic but functional
3. **Should never reach "missing"** — IR is constrained to catalog types, and the default library covers all ~48 types

The default library is a one-time design effort: a reference Figma file with clean implementations of all catalog types, extracted into templates and shipped with the system.

### 7. extract_components.py — Complementary to Template Extraction
**Challenge**: The existing `extract_components.py` parses component DEFINITIONS (master components). Template extraction needs component USAGE (how instances look in context).

**Decision**: Both are needed, in sequence:
1. Run `extract_components()` on Dank file → populates `components`, `component_slots`, `component_variants` tables
2. Use slot definitions FROM those tables to guide template extraction
3. Template extraction is NEW code that analyzes classified instances + slot definitions to build renderer config entries

The existing module gives us catalog-level infrastructure. Template extraction gives us project-level instances.

### 8. DB Staleness — Existing Infrastructure Handles It
**Challenge**: The DB is a point-in-time snapshot. The Figma file keeps changing.

**Decision**: Acceptable — existing infrastructure mitigates:
- `dd/drift.py` detects value drift between DB and Figma
- `screen_extraction_status` tracks extraction timestamps
- Incremental re-extraction for changed screens
- Pattern: extract → detect drift → re-extract stale → generate

Generation quality depends on extraction freshness. The spec documents this as an operational concern, not an architectural one.

### 9. Instance-First Figma Rendering
**Challenge**: Should the renderer prefer Figma component instances or constructed frames?

**Decision**: Always prefer instances via `importComponentByKeyAsync`. Fall back to frame construction only when import fails. Instances maintain component linkage — when the designer updates the master, all generated instances update automatically. This preserves design system integrity.

### 10. Token Resolution for Figma Renderer
**Challenge**: The IR says `style: { backgroundColor: "{color.surface.primary}" }`. But many Figma values aren't tokenized. How does the renderer get the value?

**Decision**: Modified Option C from discussion. The IR always uses token refs (both real AND synthetic). The renderer resolves from the IR's token dictionary. For un-tokenized values, synthetic tokens were created during analysis (Decision #1), so the token dictionary has entries for everything. If a token ref has no entry (edge case), the renderer reads the literal value from the DB's `node_token_bindings.resolved_value`.

---

## Integration Checkpoints

Each implementation phase ends with an integration test against the real Dank DB (338 screens, 86K nodes, 182K bindings). These are not unit tests — they verify the system produces correct results on real data.

### Phase 0 Checkpoint: FigmaPlatformContext
```
INPUT:  Dank DB, screen 184
TEST:   build_figma_context(conn, screen_id=184) produces context
VERIFY:
  - Context has visual data for nodes with fills/strokes/effects
  - Context element IDs match IR element IDs (same node → same ID)
  - Context token dict has 73 entries (matches IR token count)
  - All 35 fill-bearing nodes have visual.fills in context
```

### Phase 1 Checkpoint: Dual-Read Generator Equivalence
```
INPUT:  Dank DB, screen 184
TEST:   Generate Figma script two ways:
        (a) Current path: generator reads IR visual section
        (b) New path: generator reads context visual data
VERIFY:
  - Scripts (a) and (b) produce identical Figma JS
  - Execute script (b) via PROXY_EXECUTE → screenshot matches script (a) output
  - Token refs collected are identical in both paths
```

### Phase 2 Checkpoint: Thin IR Invariants
```
INPUT:  Dank DB, screen 184
TEST:   generate_ir(conn, screen_id=184) produces thin IR
VERIFY:
  - No element has a "visual" key
  - No element.style value is a literal hex color (all are "{token.ref}" strings)
  - Synthetic tokens exist in tokens table with tier='synthetic'
  - Token dictionary has entries for ALL visual values (real + synthetic)
  - Generator with context produces same Figma output as pre-thinning
```

### Phase 3a Checkpoint: Component Extraction + Slot Definitions
```
INPUT:  Dank DB (after running extract_components)
TEST:   Composition tables populated
VERIFY:
  - components table has entries (was 0, now > 0)
  - component_slots has slot definitions for key types (header, button, card)
  - component_variants has variants for component sets
  - variant_dimension_values cross-product populated
  - component_a11y has accessibility contracts
```

### Phase 3b Checkpoint: Semantic Tree Construction
```
INPUT:  Dank DB, screen 184
TEST:   build_composition_spec produces semantic IR
VERIFY:
  - Element count: 15-25 (was 116)
  - Header element has filled slots (leading, title, trailing)
  - System chrome excluded (no status-bar, home-indicator, safari-bar elements)
  - Unclassified vectors/rectangles not present as IR elements
  - All classified components reachable from root
  - Generate from semantic IR → execute in Figma → screenshot shows correct composition
```

### Phase 4 Checkpoint: Template Extraction + Rendering
```
INPUT:  Dank DB, all 338 screens
TEST:   Extract templates, generate NEW screen from prompt
VERIFY:
  - Templates exist for each catalog type found in Dank (header, button, card, etc.)
  - Header template has componentKey (from nav/top-nav master component)
  - Template frame structure matches actual Figma layout (auto-layout, padding, sizing)
  - Generate "settings page with toggle sections" from prompt
  - Render using extracted templates
  - Execute in Figma → screenshot shows plausible settings screen in Dank's visual style
```

### End-to-End Checkpoint: Full Round-Trip
```
INPUT:  Dank DB screen 184 (original) + prompt "make a similar screen with different sections"
TEST:   Full loop: extract → analyze → compose → render
VERIFY:
  - Generated screen uses the same component types as screen 184
  - Visual style matches (same colors, fonts, spacing — from tokens)
  - Component instances link to real master components (not raw frames)
  - Token variables are bound (not just literal values)
  - Side-by-side with original: "looks like it belongs to the same app"
```

---

## Resolved: Previously Open Questions (Steelmanning Round 2, 2026-04-02)

### 1. Component Variants in Templates — RESOLVED
**Decision**: Templates carry multiple variants, each with own frame structure and visual defaults. Variant detection via two methods:

**Name parsing** (primary, covers Dank file): Component names like `button/large/translucent` are split on `/` — first segment is base type, remaining are variant axis values. Dank file uses this exclusively (3,677 `button/large/translucent`, 2,537 `button/small/translucent`, etc.). The existing `parse_variant_properties()` handles `key=value` syntax; we also need `/`-delimited parsing.

**Visual clustering** (fallback for files without naming conventions): Group instances by canonical type → extract structural fingerprint (child count, child types, layout mode, visual properties) → cluster by similarity → each cluster is a variant.

**Template model**:
```
ComponentTemplate
  catalog_type: "button"
  variants: {
    "large/translucent": { frameStructure, visualDefaults, componentKey? },
    "small/solid": { frameStructure, visualDefaults, componentKey? },
    ...
  }
  default_variant: "large/translucent"  // most common
```

**Instance path**: Figma handles variants natively (set variant property on instance).
**Frame path**: Renderer looks up `variants[variant_name]` for the right template.

### 2. Informal Component Recognition — RESOLVED
**Decision**: Full structural clustering for the 1,950 non-container classified FRAMEs.

**Algorithm**:
1. Group classified FRAMEs by canonical type (e.g., all 174 cards, all 949 buttons)
2. Extract structural fingerprint per instance: `(child_count, child_types_ordered, layout_mode, has_fills, has_strokes)`
3. Cluster by fingerprint similarity (exact match for structure, delta-E for visual properties)
4. Each structural cluster = a variant of that component type
5. Extract template from the most common instance in each cluster
6. Naming: from name parsing (`button/large/translucent`) or structural clustering (`card.cluster_1`)

**Reuses existing infrastructure**: delta-E clustering for colors, extended to component-level structural fingerprints.

### 3. Multi-File Design Systems — RESOLVED
**Decision**: Multi-file works via component keys. No need to extract the library file separately.

**Data flow**: INSTANCE nodes have `mainComponent.key` in Figma → extraction JS captures as `component_key` → DB stores it → `importComponentByKeyAsync(key)` works for published library components automatically (Figma resolves cross-file references via keys).

**Prerequisite**: Schema migration to add `component_key` column to Dank DB (it's in the full schema, just missing from the older Dank DB). Then re-extract to populate.

**Key finding**: All 27,810 INSTANCE nodes currently have `component_id = None`. The extraction JS DOES capture `component_key` and `component_figma_id`, but the Dank DB lacks the columns. This is a migration gap, not a code gap.

### 4. Missing DB Columns — RESOLVED
**Decision**: Schema migration is a prerequisite for implementation. 24 columns missing from Dank DB:

**Critical for four-layer architecture**:
- `component_key` — instance-first rendering (importComponentByKeyAsync)
- `constraint_h`, `constraint_v` — absolute/stacked positioning
- `stroke_weight`, `stroke_align` — stroke rendering
- `clips_content` — overflow behavior

**Also needed**: `font_style`, `text_case`, `text_decoration`, `text_align_v`, `layout_wrap`, `min/max_width/height`, `rotation`, `dash_pattern`, `paragraph_spacing`, `stroke_cap/join`, per-side stroke weights.

**The extraction JS already captures all 24 fields**. This is purely a DB schema gap. Add columns via `ALTER TABLE`, then re-extract affected screens.

### 5. Default Library Design — RESOLVED
**Decision**: Modern neutral aesthetic. Clean, Inter font, neutral palette, proper spacing. Looks good out of the box — not a wireframe, not a branded design system. Think shadcn/ui defaults.

**Implementation**: Create a reference Figma file with clean implementations of all ~48 catalog types → extract templates → ship as the system's default library. This is a design+engineering effort done once the template extraction pipeline is built.

---

## Relationship to Existing Research

This architecture aligns with the consensus from surveyed systems (Mitosis, Yoga, json-render, A2UI, SDUI):

1. **Flat element map, not nested tree** — children by ID reference
2. **Typed components from a declared catalog** — constrains output space
3. **Separated concerns** — structure, layout, style, behavior, data as independent layers
4. **Platform-specific renderers, not platform-specific specs** — the IR is universal
5. **Platform hints escape hatch** — `$platform` for the ~10% that doesn't translate

No existing system combines: design tool input + design tool output + bidirectionality + token bindings + layout abstraction. This combination is genuinely unoccupied territory.

---

## Deep Sweep Findings (2026-04-02)

Systematic audit of the codebase, real Dank DB data, and prior art. All HIGH severity items resolved.

### Screen Classification (Prerequisite for Layer 2-4)

The 338 "screens" in the Dank DB are NOT all app screens:

| Category | Count | Dimensions | Use in pipeline |
|----------|-------|-----------|----------------|
| Phone screens | 69 | 428x926 | App screens — full pipeline |
| Tablet portrait | 68 | 834x1194, 834x955 | App screens — full pipeline |
| Tablet landscape | 67 | 1536x1152 | App screens — full pipeline |
| Icon definitions | 117 | 20x20, 40x40 | Component definitions — Layer 1 only |
| Component definitions | 14 | Various small | Component definitions — Layer 1 only |
| Design canvases | 3 | 3257x1385, 3881x2622, 3226x2322 | Design exploration — exclude from pipeline |

**Action**: Filter screens before Layer 2 analysis. Only phone/tablet screens (204 total) should enter the classification → IR → rendering pipeline. Icon/component definition screens are Layer 1 data (for component discovery via `extract_components.py`). Design canvases are excluded entirely.

### Token-Bound Unclassified Nodes — NOT a Problem

36,477 nodes have token bindings but are not classified. Investigation showed:
- **86.1% (31,402)**: Internal nodes of classified components (icon vector paths, button internal frames). Every one has a classified ancestor within 3 levels. These are absorbed during semantic tree construction.
- **13.9% (5,075)**: Nodes on non-app artboards (design canvases, marketing exports). Excluded by screen filtering.

**No template binding changes needed.** Instance-path rendering handles internal bindings automatically. Frame-path templates inherit from the source structure.

### Classification Coverage — Better Than Reported

The "93.6% classification" was on classifiable nodes. On real app screens, the breakdown is:
- **0 genuinely missed INSTANCE nodes** on app screens. All 3,304 unclassified INSTANCEs are either:
  - 1,281 on non-app artboards (design canvases with 0 classifications)
  - 2,023 system chrome on app screens (`_Key`, `_KeyContainer`, `iOS/StatusBar`, `Safari - Bottom`, `ios/alpha-keyboard`, `HomeIndicator`)
- **System chrome is correctly excluded** by `is_system_chrome()` — not a classification failure.

**The classification pipeline works correctly on app screens.**

### Synthetic Token Volume — Minimal for Well-Tokenized Files

The Dank file has only ~150 unique visual values (68 fill colors, 10 stroke colors, 4 effect colors, 34 font sizes, 34 radii). After delta-E clustering, synthetic tokens would number ~50-80. Combined with 388 real tokens, the total is manageable (~450-470).

**Caveat**: The Dank file is unusually well-tokenized (89% bound). Files with lower tokenization will need more synthetic tokens. The system must handle the 0%-tokenized worst case.

### layoutPositioning (AUTO vs ABSOLUTE) — Add but Not Blocking

`layoutPositioning` determines whether a child in an auto-layout parent participates in flow (AUTO) or floats freely (ABSOLUTE). It's not extracted or stored.

Investigation: 64% of HORIZONTAL parents have children with overlapping x-ranges. Some of this is genuine ABSOLUTE positioning (icon overlaid on text), some is just compact button layouts.

**Decision**: Add to extraction JS and schema as a prerequisite. Not blocking for Phases 0-2 (instance-first rendering handles positioning automatically). Required for Phase 3+ (frame-path template construction needs to know flow vs absolute).

### Screen Skeletons — Already Extracted

335 screen skeletons exist in `screen_skeletons` table (columns: id, screen_id, skeleton_notation, skeleton_type, zone_map, created_at). Example: `stack(scroll(content), content)`. These are Layer 2 data usable for screen pattern recognition.

### Spec Clarification: Token Dictionary vs DB Read

The primary rendering path is: **renderer resolves ALL visual values from the IR's token dictionary** (which contains both real and synthetic token entries). The DB is a fallback for edge cases where a value has no token entry. This was resolved in steelmanning decision #10 but the Layer 1 description said "renderer reads from DB" — the primary path is the token dictionary, not direct DB reads.

### No Prior Art

Web research confirmed: no existing system does bidirectional compilation through a universal IR with token binding at the property level. Builder.io does component mapping (not compilation). story.to.design does code→Figma (one direction). Figma MCP servers do one-shot translation (no IR). The closest analog is Mitosis (compiler architecture) but it's web-framework-only.

---

## Glossary

| Term | Definition |
|------|-----------|
| **IR** | Intermediate Representation — the abstract composition. Flat element map with types, slots, token refs, layout intent. |
| **CompositionSpec** | The concrete JSON format of an IR instance. |
| **RendererConfig** | Per-platform, per-project configuration telling a renderer how to build each catalog type. |
| **Component Template** | A RendererConfig entry for one catalog type on one platform — the physical implementation. |
| **Catalog** | The ~48 canonical UI component types. Universal, versioned, shared across projects. |
| **Slot** | A named insertion point in a component (e.g., Header.leading, Card.media). |
| **Token Reference** | A string like `"{color.surface.primary}"` in the IR that the renderer resolves per-platform. |
| **Component Vocabulary** | Layer 2 output — what components exist in THIS project and how they're built. |
| **Screen Pattern** | Layer 2 output — recognized screen archetypes (settings, dashboard, chat, etc.). |
