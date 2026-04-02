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
Parse a source artifact and store every recoverable detail in a structured store. Extraction is exhaustive and platform-specific. It captures MORE than the IR will ever need, because the renderer will reach back into this data later.

### Figma Extraction (BUILT — T1-T4)
- **Input**: Figma file via REST API + Plugin API
- **Output**: SQLite DB with:
  - `nodes` — 86K rows, 40+ columns: position, dimensions, layout mode, padding, spacing, sizing modes, fills (JSON), strokes (JSON), effects (JSON), corner radius, opacity, blend mode, font properties, text content, parent_id, component references
  - `node_token_bindings` — 182K rows: which node properties are bound to which design tokens
  - `tokens` / `token_values` / `token_collections` / `token_modes` — 388 tokens across 8 collections with multi-mode values
  - `components` — Formal Figma component definitions (master components, variants, keys)
  - `screens` — 338 screens with dimensions and device class
  - **Missing columns (need migration)**: `constraints` (horizontal/vertical), `layoutPositioning` (AUTO/ABSOLUTE). Extraction JS captures these but the schema doesn't store them yet.

### React Extraction (NOT BUILT)
- **Input**: React codebase (file system)
- **Output**: Store with:
  - Component definitions: name, file path, exported props (from TypeScript types), default values
  - Component usage: which components are used in which files, with what props
  - Import graph: which components import which other components
  - Token usage: which CSS variables / Tailwind classes / theme values are referenced
  - JSX structure: the component tree per page/route

### Screenshot Extraction (NOT BUILT)
- **Input**: Screenshot image(s)
- **Output**: Store with:
  - Detected UI elements: bounding boxes, recognized component types, text content (OCR)
  - Color samples: extracted from regions
  - Layout relationships: spatial arrangement, alignment patterns, spacing
  - Confidence scores per detection

### Prompt Extraction
- **Input**: Natural language description ("I need a settings page with toggle sections")
- **Output**: Parsed intent — screen type, requested components, constraints. No traditional extraction step; the prompt IS the composition intent. The system uses analysis from an EXISTING project (if available) to inform rendering.

### Key Principle
Extraction is greedy. Capture everything the source provides. The analysis and rendering layers decide what matters. Extraction never filters or interprets — it records.

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

## Open Questions for Steelmanning

### 1. Fidelity Loss in Compression
The Figma→IR path compresses 200 nodes to ~20 elements. When generating a NEW screen from that vocabulary, the output won't be pixel-identical to the source. Is "looks like it belongs to the same design system" sufficient? What visual deviations are acceptable vs. not?

### 2. Component Variants
A Button has multiple variants (primary, secondary, ghost, destructive). The IR says `{type: "button", props: {variant: "primary"}}`. The template extraction needs to capture per-variant structure. How does the renderer select the right variant template? Does each variant get its own template, or is it one template with variant-driven property overrides?

### 3. Informal vs Formal Components
Some UI patterns in Figma aren't formal components — they're recurring frame arrangements without a master component. A "card" might be 5 informal frames that always appear together. The analysis layer needs to recognize these patterns and create templates for them, even without a component key. How is structural similarity detected and clustered?

### 4. Multi-File Design Systems
Many Figma projects use a separate library file for component definitions. The renderer needs component keys from the library file, but the extracted DB is from the consumer file. How does the system connect these? Does the user need to extract both files?

### 5. Performance at Scale
Template extraction across 338 screens with 86K nodes will be computationally significant. Can analysis be incremental (analyze one screen at a time and merge results)? Can templates be cached and reused across sessions?

### 6. Missing DB Columns
`constraints` (horizontal/vertical) and `layoutPositioning` (AUTO/ABSOLUTE) are extracted by the JS extraction code but not stored in the nodes table. The Figma renderer needs these for correct positioning of stacked/absolute children. Schema migration needed.

### 7. Semantic Sizing Resolution
The IR says `sizing: { width: "fill" }` but the renderer needs actual pixel values for Figma frame construction. Where does the resolution happen? Options: from the component template's dimensions, from the target viewport, or from the source node's dimensions in the DB.

### 8. Error Recovery
What does a renderer do when:
- An IR element type has no mapping in the componentMap? → Create a generic container with the element's children.
- An IR slot references a type not allowed by the slot definition? → Place it anyway with a warning.
- A token ref doesn't resolve? → Renderer reads the literal from DB, or uses a hardcoded default.

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
