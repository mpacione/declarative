# Four-Layer Architecture Specification

> **Declarative Design is a bi-directional design compiler.** It parses UI from any source into an abstract compositional IR, then generates to any target with token-bound fidelity. This document specifies the four-layer architecture that makes that possible.

Status: DRAFT — for analysis, critique, and steelmanning. Not yet implemented.

---

## The Four Layers

```
Layer 1: EXTRACTION     Source → DB/Store        "Record everything"
Layer 2: ANALYSIS        DB/Store → Abstractions  "Understand what's there"
Layer 3: COMPOSITION     Abstractions → IR         "Describe what to build"
Layer 4: RENDERING       IR + DB/Config → Output   "Build it concretely"
```

Each layer has a single responsibility. Data flows up through Layers 1-2 (concrete → abstract) and down through Layers 3-4 (abstract → concrete). The IR at Layer 3 is the narrowest point — pure semantic intent with no platform-specific detail.

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

### Prompt Extraction (NOT BUILT — may not need a traditional extraction step)
- **Input**: Natural language description ("I need a settings page with toggle sections")
- **Output**: Parsed intent:
  - Screen type: settings
  - Requested components: toggle sections (implies toggle rows, section headings)
  - Constraints: none specified → use defaults from taste model

### Key Principle
Extraction is greedy. Capture everything the source provides. The analysis and rendering layers decide what matters. Extraction never filters or interprets — it records.

---

## Layer 2: Analysis

### Purpose
Read the extracted data and build abstractions at increasing levels. Analysis transforms raw platform-specific data into the vocabulary that the IR composes with. Each abstraction references back to the source data it was derived from.

### Three Levels of Abstraction

#### Level A: Component Vocabulary
"What components exist in this project, and how are they built?"

- **Input**: Extracted node tree + classifications
- **Output**: For each of the ~50 catalog types found in this project:
  - Which nodes are instances of this type (from classification: 93.6% coverage on Dank)
  - The canonical Figma structure: frame arrangement, auto-layout config, child positions
  - Visual defaults: typical fills, strokes, effects, radius for this type
  - Slot definitions: named insertion points (leading, title, trailing for a Header)
  - Figma component key: if this maps to a formal master component
  - Variants: the different visual/behavioral variants of this type (e.g., Button: primary, secondary, ghost, destructive)

- **Example**: "Header in this project = nav/top-nav (component key abc123). Horizontal auto-layout, 428px wide, 111px tall, 3 slots: Left (130px, icon+label), Center (182px, nav items), Right (130px, action buttons). White background, background blur effect. 338 instances across all screens, 2 variants (with/without search)."

- **References back to DB**: Every component vocabulary entry points to specific node IDs, property values, and token bindings.

#### Level B: Pattern Language
"What screen-level patterns exist in this project?"

- **Input**: Component vocabulary + classified screens + skeleton notation
- **Output**: Recognized screen patterns:
  - Screen archetypes: settings, dashboard, chat, profile, search, list, detail, onboarding, etc.
  - For each archetype: the typical skeleton (component types in what arrangement)
  - Composition rules: what components commonly appear together, in what ratios
  - Spacing/rhythm conventions: typical gap sizes, padding patterns, content density

- **Example**: "Settings screen pattern (found in 12 screens): stack(header, scroll(section-group(2-4, toggle-rows + nav-rows)), bottom-nav). Average 3.2 sections per screen. Sections use 16px gap between items, 24px gap between sections."

- **References back to vocabulary**: Every pattern references catalog types from Level A.

#### Level C: Taste Model (FUTURE)
"What makes the good examples good?"

- **Input**: Curated corpus + pattern analysis
- **Output**: Quality-weighted distributions for Pattern Language decisions
- Not required for the core loop to work. The system functions with just Levels A and B.

### Per-Source Analysis

#### From Figma
All three levels can be derived. The DB has enough information for component vocabulary (classification), pattern language (skeleton extraction + screen clustering), and eventually taste model.

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
  tokens: { token.name → resolved value }  // for this project
  elements: {
    element-id: {
      type: string                          // from catalog (~50 types)
      children: [element IDs]               // ordered child elements
      slots: { slot-name → [element IDs] }  // named insertion points
      props: {                              // component-specific
        text: string                        // text content
        icon: string                        // icon name (canonical)
        variant: string                     // visual variant
        checked: boolean                    // state
        ...                                 // per catalog type
      }
      layout: {                             // abstract flexbox (universal)
        direction: "horizontal" | "vertical" | "stacked"
        gap: number | "{token.ref}"
        padding: { top, right, bottom, left }
        sizing: { width, height }           // "fill" | "hug" | number
        mainAxisAlignment: string
        crossAxisAlignment: string
      }
      style: {                              // token references ONLY
        backgroundColor: "{color.surface.primary}"
        textColor: "{color.text.primary}"
        borderColor: "{color.border.default}"
        ...                                 // values are ALWAYS token refs
      }
      on: { event → action }               // interaction intent
      visible: condition                    // conditional rendering
      $platform: { ... }                   // escape hatch (rare)
    }
  }
```

### What the IR Does NOT Carry

| Excluded | Why | Where it lives instead |
|----------|-----|----------------------|
| Fill arrays, stroke objects, effects | Figma-specific rendering detail | DB nodes table, used by Figma renderer |
| Literal hex colors (#FF0000) | Platform-specific value | DB token_values, resolved by renderer per-platform |
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
5. Result: ~15-25 elements per screen, each a semantic component

#### From a Prompt (generating a new screen)
1. Parse intent: "homepage with cards" → screen type + requested components
2. Pattern Language selects a skeleton: header + hero + card-grid + footer
3. Elaboration fills slots: header gets logo + nav items, card-grid gets 6 cards with image/title/subtitle
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

All fields are optional. A prompt-generated IR might have types and slots but no token references. A screenshot-derived IR might have types and text but no layout details. A Figma-parsed IR will be the most complete. Renderers apply sensible defaults for missing fields.

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

**Config source**: Extracted from the DB by the analysis layer.

```
FigmaRendererConfig
  componentMap: {
    "header": {
      componentKey: "abc123"              // for importComponentByKeyAsync
      frameStructure: { ... }             // auto-layout, padding, sizing
      visualDefaults: { fills, strokes, effects, radius }
      slotPositions: { leading: 0, title: 1, trailing: 2 }  // child indices
    }
    ...
  }
  tokenResolver: {
    format: "figma-variable"
    variableIds: { "color.surface.primary" → "VariableID:123:456" }
  }
  dbConnection: sqlite3.Connection        // for reading node-level detail
```

**Rendering process**:
1. Walk IR elements in tree order
2. For each element, look up its type in componentMap
3. If componentKey exists → `importComponentByKeyAsync(key)`, create instance, set overrides
4. If no componentKey → create frame structure from frameStructure template
5. Fill slots: insert child elements at slotPositions
6. Apply token references: resolve via tokenResolver, bind Figma variables
7. Apply layout: set auto-layout mode, padding, sizing from IR layout section
8. For properties not in IR (visual detail): read from DB if source node exists, or use visualDefaults from template

**When source exists** (Figma→Figma, editing existing screens): renderer reads specific node visual properties from DB.
**When no source exists** (Prompt→Figma, generating new screens): renderer uses component templates extracted from the user's existing file, or falls back to pre-seeded default templates.

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

**No DB needed.** React rendering is fully determined by the IR + config. The config is static (shipped preset or one-time extraction from codebase).

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
  → L2: Analyze → Component vocabulary (48 types classified)
                 → Screen patterns (settings, chat, dashboard, ...)
                 → Component templates (how each type is built in Figma)
  → L3: User says "new settings page" → Pattern Language composes IR
         IR: { screen → [header, scroll([section, section, section]), bottom-nav] }
  → L4: Figma renderer reads IR
         Looks up "header" in componentMap → finds nav/top-nav (key abc123)
         importComponentByKeyAsync → creates instance
         Fills slots from IR → sets title, leading icon, trailing actions
         Resolves token refs → binds Figma variables
         Repeats for each element
  → Output: New Figma screen that looks like it belongs to the existing file
```

**L1 already built.** L2 partially built (classification done, templates not yet). L3 IR structure exists but too thick. L4 generator exists but reads from IR visual section instead of DB/templates.

### Prompt → IR → Figma (generate from natural language)

```
"Build me a dashboard with a sidebar and card grid"
  → L1: No extraction. But user must have a project context:
         EITHER an existing Figma file (→ use its DB for L2 and L4)
         OR a pre-seeded design system (→ use default templates)
  → L2: Analysis already done on project's existing file (or defaults loaded)
         Component vocabulary and templates available for rendering
  → L3: Pattern Language interprets prompt
         Selects "dashboard" archetype from pattern library
         Composes: sidebar(nav-items) + main(header + card-grid(6, card(image, title, metric)))
         Emits IR with token refs from project's token vocabulary
  → L4: Figma renderer reads IR + templates
         Builds each component using project's templates
         No source nodes in DB for this screen (it's new)
         Falls back to templates for visual properties
  → Output: New Figma screen in the user's design language
```

**Requires**: Pattern Language (L3, not built), templates (L2, not built), pre-seeded defaults for new projects.

### Figma → IR → React (design to code)

```
Figma file
  → L1: Extract → DB (already done)
  → L2: Analyze → Component vocabulary (classify screen's nodes)
                 → Map each catalog type to target React library
  → L3: Build IR from classified screen
         header-1 with slots: { leading: [icon-1], title: "Settings", trailing: [button-1] }
         scroll-1 with children: [section-1, section-2]
         Each element carries token refs from bindings
  → L4: React renderer reads IR + ReactRendererConfig(shadcn)
         "header" → import { Header } from "@/components/ui/header"
         Maps IR slots to React props/children
         Token refs → CSS variables: "{color.surface.primary}" → "var(--color-surface-primary)"
         Emits JSX + imports + token CSS file
  → Output: React components with proper imports, props, and token-bound styling
```

**Requires**: React renderer config (shipped presets for shadcn/MUI/Radix), token export to CSS variables (partially built in T4).

### React → IR → Figma (code to design)

```
React codebase
  → L1: Extract → Parse AST
         Identify component files, exported props, usage sites
         Map imports to component names
         Extract JSX trees per page/route
  → L2: Analyze → Map React components to catalog types
         <Header /> → "header", <Button variant="ghost" /> → "button" (variant: ghost)
         Extract prop values as IR props
         Identify layout from flex/grid CSS
  → L3: Build IR from parsed component tree
         Same IR structure as Figma-sourced or prompt-sourced
  → L4: Figma renderer reads IR + FigmaRendererConfig
         Needs component templates — where from?
         OPTION A: User has existing Figma file → use its templates
         OPTION B: No Figma file → use pre-seeded default templates
         Builds Figma frames from templates, fills slots, binds tokens
  → Output: Figma file that represents the React app's UI
```

**Key tension**: Where do the Figma templates come from when there's no existing Figma file? This is the "cold start" problem. Pre-seeded default templates are the answer, but they'll produce generic-looking output until the user customizes.

### Screenshot → IR → Figma (reverse engineering)

```
Screenshot image
  → L1: Extract → Vision analysis
         Detect component bounding boxes + types (header, card, button, ...)
         OCR text content
         Sample colors from regions
         Estimate spacing/alignment
  → L2: Analyze → Map detections to catalog types
         Lower confidence than Figma or React parsing
         No internal structure — each detection is a leaf
         Layout inferred from spatial relationships
  → L3: Build IR from detections
         Sparser IR — types and text, less slot detail, approximate layout
         Token refs: create new tokens from sampled colors, or match to existing project tokens
  → L4: Figma renderer reads IR + templates
         Builds from templates (no source DB for this screenshot)
         Applies sampled colors / estimated dimensions
  → Output: Figma approximation of the screenshot — a starting point, not exact
```

**Lowest fidelity path.** Useful for "make something like this" or "recreate this competitor's screen in our design system." The output needs human refinement.

### Prompt → IR → React (generate code from description)

```
"Build me a settings page with toggle sections"
  → L1: No extraction needed
  → L2: Use project's existing analysis (if React codebase exists)
         OR use default component vocabulary
  → L3: Pattern Language composes IR
         Same as Prompt → Figma, but token refs may target CSS variables
  → L4: React renderer reads IR + ReactRendererConfig
         Maps to shadcn/MUI/Radix components
         Token refs → CSS variables or Tailwind classes
         Emits complete page component with imports
  → Output: React component file(s) ready to use
```

**Cleanest code generation path.** React libraries already encapsulate component implementations, so the renderer is a straightforward mapping.

### Figma → IR → SwiftUI (design to native mobile code)

```
Figma file
  → L1: Extract → DB (same as always)
  → L2: Analyze → Component vocabulary (same classification)
  → L3: Build IR from classified screen (same as Figma→React)
  → L4: SwiftUI renderer reads IR + SwiftUIRendererConfig
         "header" → NavigationStack + .toolbar
         "button" → Button(role:) with label
         "toggle-row" → Toggle with label/subtitle
         Token refs → Color("tokenName") from asset catalog
         Layout: HStack/VStack/ZStack from IR direction
  → Output: SwiftUI View files with proper modifiers and asset references
```

**Requires**: SwiftUI renderer config (framework mappings, mostly static). Token export to Xcode asset catalogs.

---

## The RendererConfig Lifecycle

### Where Configs Come From

| Config Type | Source | When Created | Persistence |
|------------|--------|--------------|-------------|
| Figma (existing project) | Extracted from DB by analysis | After classification + template extraction | Stored in DB or cached file |
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

The DB is NOT a universal system component. It is the **Figma parser's working storage** — the output of Layer 1 for Figma inputs specifically. Other parsers (React AST, screenshot vision) have their own storage formats.

However, the DB serves double duty for the Figma renderer:
- **Analysis reads it** to build component vocabulary and extract templates
- **The Figma renderer reads it** to get visual properties when reconstructing elements from an existing file

This dual role is specific to the Figma→Figma path. For Prompt→Figma, the renderer reads templates (extracted from DB earlier) but not the DB directly. For Figma→React, the DB is read by analysis but the React renderer never touches it.

### DB Tables and Their Layer

| Table | Layer 1 (Extraction) | Layer 2 (Analysis) | Layer 4 (Figma Rendering) |
|-------|---------------------|-------------------|--------------------------|
| `nodes` | Written | Read for classification | Read for visual properties |
| `node_token_bindings` | Written | Read for token mapping | Read for variable rebinding |
| `tokens` / `token_values` | Written | Read for vocabulary | Read for value resolution |
| `screens` | Written | Read for pattern analysis | Read for screen dimensions |
| `components` | Written | Read for formal matching | Read for component keys |
| `screen_component_instances` | — | Written by classification | Read for element→node mapping |
| `component_type_catalog` | — | Written (seeded) | Read for type validation |
| Component templates (NEW) | — | Written by template extraction | Read for frame structure |

---

## Open Questions for Steelmanning

### 1. Layout in the IR
The IR layout section carries pixel values for sizing (`width: 428, height: 926`). Are pixel dimensions "platform-specific detail" that should live in the renderer config? Or are they universal intent ("this screen is phone-sized")?

**Argument for keeping in IR**: Sizing is intent. "This card is 300px wide" is a design decision, not a platform implementation detail. Every platform needs to know the intended dimensions.

**Argument for removing**: Pixel values only make sense in the context of a specific viewport. "300px" means different things on mobile vs desktop. Maybe the IR should say `sizing: { width: "medium" }` and let the renderer resolve that per-platform.

### 2. Token References Without Values
The IR carries `style: { backgroundColor: "{color.surface.primary}" }` but what if the target project doesn't have that token? What if the user is generating into a NEW project with no tokens yet?

Options:
- IR also carries resolved literal values as fallback (but then it's not thin)
- Token vocabulary is a prerequisite — you must have a design system before generating
- Renderer has hardcoded defaults for standard token names

### 3. Cold Start Problem
For Prompt→Figma with no existing file, and React→Figma with no Figma file, where do component templates come from? Pre-seeded defaults work but produce generic output. Is that acceptable? Or must the user always start from an existing design system?

### 4. Slot Definition Completeness
The catalog has 48 types with 0 slot definitions. For semantic tree construction to work (Layer 3), we need to know what slots each type has. This is a significant research/design effort. Can we start with a subset (the 10 most common types in the Dank file) and expand incrementally?

### 5. Fidelity Loss in Compression
The Figma→IR path compresses 200 nodes to 20 elements. When generating a NEW screen from that vocabulary, the output won't be pixel-identical to the source. How much fidelity loss is acceptable? Is "looks like it belongs to the same design system" sufficient?

### 6. Component Variants
A Button in the Dank file has multiple variants (primary, secondary, ghost, destructive). The IR says `{type: "button", props: {variant: "primary"}}`. The Figma renderer needs to know which specific frame structure corresponds to the "primary" variant. The template extraction needs to capture per-variant structure, not just per-type.

### 7. Informal vs Formal Components
Some UI patterns in Figma aren't formal components — they're just recurring frame arrangements. A "card" might be 5 informal frames that always appear together but aren't a Figma component. The analysis layer needs to recognize these patterns and create templates for them, even without a component key.

### 8. Multi-File Design Systems
Many Figma projects use a separate library file for component definitions. The renderer needs component keys from the library file, but the extracted DB is from the consumer file. How does the system connect these?

### 9. Bidirectional Sync
If a user generates a screen from the IR, then manually edits it in Figma, can the system detect what changed and update the IR? This is the "round-trip editing" problem. The generated screen would need to maintain a mapping from IR elements to Figma nodes.

### 10. Performance at Scale
Template extraction across 338 screens with 86K nodes will be computationally significant. Can analysis be incremental (analyze one screen at a time and merge results)? Can templates be cached and reused across sessions?
