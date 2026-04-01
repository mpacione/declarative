# T5 Intermediate Representation (IR) Design

Compiled 2026-04-01. This document defines the Intermediate Representation — the abstract component layer that sits at the center of the hub-and-spoke architecture. Every input parses INTO this format, every output generates FROM it.

---

## Why the IR Is the Load-Bearing Wall

The IR is the single most important design decision in the system. Everything flows through it:

- **Parsers** (Figma, React, SwiftUI, screenshot, prompt) produce it
- **Generators** (Figma, React, SwiftUI, Flutter, HTML, spec documents) consume it
- **The Pattern Language** operates on it (descending through abstraction levels)
- **The Taste Model** informs choices within it
- **The Critique Cascade** evaluates it
- **The Decision Tree** records exploration paths through it

If the IR is too rigid, new inputs/outputs are hard to add. If too loose, translations are ambiguous. If it's missing information, outputs are lossy. If it captures too much platform-specific detail, it's not truly abstract.

---

## Design Principles (from research synthesis)

### 1. Flat Element Map, Not Nested Tree

Every mature system (json-render, A2UI, Airbnb SDUI) converges on this. Children referenced by ID, not by nesting.

**Why:**
- Enables streaming (generate elements as you go)
- Enables partial updates (change one element without touching siblings)
- Enables JSON Patch operations (RFC 6902)
- Easier for LLMs to generate (flat structure, no bracket-matching)
- Easier to diff, merge, and version

### 2. Typed Components from a Declared Catalog

The catalog IS the contract. Components can only be of types declared in the catalog. This constrains the output space and prevents hallucination.

### 3. Separated Concerns

Five independent layers within each element:
- **Structure** — what component, what children, what slots
- **Layout** — spatial arrangement (direction, gap, padding, alignment, sizing)
- **Style** — visual appearance via token references (not hardcoded values)
- **Behavior** — events, interactions, state
- **Data** — content (text strings, image refs, dynamic bindings)

### 4. Flexbox as Universal Layout Model

Yoga (Meta) proved this. Figma auto-layout, CSS flexbox, SwiftUI stacks, Flutter Row/Column all map to: direction, gap, padding, alignment, sizing (fill/hug/fixed). Platform-specific gaps handled by `$platform` hints.

### 5. Token References for Style Values

Numbers for absolute values, strings for token references: `gap: 16` (pixels) vs `gap: "{space.s16}"` (token). Existing DTCG/export infrastructure handles per-platform translation.

### 6. Intent-Preserving, Not Lossless

The IR captures WHAT the designer meant, not HOW a specific platform implements it. "These items are in a vertical list with equal spacing" is the intent. Whether that becomes `VStack`, `flex-direction: column`, or Figma auto-layout is a generator concern.

### 7. Platform Hints as Escape Hatch

For the ~10% of cases where platforms diverge meaningfully (CSS Grid, SwiftUI alignment guides, Figma absolute-position-within-auto-layout), a `$platform` field carries platform-specific overrides without polluting the universal model.

---

## The Three Layers

### Layer 1: The Catalog (Universal, Shared)

Defines what components exist, what props/slots they have, what semantic role they play. ~45-50 canonical types. Same for every project. Versioned and distributed.

```
Catalog
├── Component types (~45-50)
│   ├── Canonical name + aliases
│   ├── Behavioral description
│   ├── Prop definitions (typed)
│   ├── Slot definitions (named insertion points)
│   ├── Semantic role (heading, button, input, etc.)
│   ├── Recognition heuristics (for parsers)
│   └── Category (actions, selection, content, navigation, feedback, containment)
├── Layout primitives (~7)
│   └── stack, row, grid, overlay, scroll, wrap, spacer
└── Version identifier
```

### Layer 2: The Composition (Per-Screen, Abstract)

A flat element map referencing catalog types, with layout, slot assignments, and token references. Project-specific but format-agnostic. This is THE hub.

```
CompositionSpec
├── version: string
├── root: string (entry element ID)
├── elements: Record<string, Element> (flat map)
│   └── Element
│       ├── id: string
│       ├── type: string (from catalog)
│       ├── props: Record<string, value> (component-specific)
│       ├── children: string[] (element IDs)
│       ├── slots: Record<string, string[]> (named slots → element IDs)
│       ├── layout: Layout (flexbox model)
│       ├── style: Record<string, token-ref | value> (visual properties)
│       ├── on: Record<string, Action> (events)
│       ├── visible: Condition (conditional rendering)
│       └── $platform: Record<string, unknown> (escape hatch)
├── catalog: CatalogReference (which catalog version)
└── tokens: Record<string, TokenValue> (resolved token values for this project)
```

### Layer 3: The Renderers (Per-Platform, Mechanical)

Each renderer translates catalog types + layout + tokens into target format. Adding a new output = adding one renderer (~45-50 component mappings).

```
Renderers
├── Figma renderer → MCP calls + variable bindings
├── React renderer → JSX + imports + props
│   ├── shadcn mapping
│   ├── MUI mapping
│   └── Radix mapping
├── SwiftUI renderer → View structs + modifiers
├── Flutter renderer → Widget tree + ThemeData
├── HTML renderer → semantic HTML + Tailwind/CSS
└── Spec renderer → natural language description
```

---

## The Layout Model

Based on Yoga's proven cross-platform flexbox abstraction:

```
Layout
├── direction: "horizontal" | "vertical" | "stacked"
├── gap: number | token-ref
├── padding: { top, right, bottom, left } (each: number | token-ref)
├── mainAxisAlignment: "start" | "center" | "end" | "stretch" | "space-between" | "space-around"
├── crossAxisAlignment: "start" | "center" | "end" | "stretch"
├── wrap: boolean
└── sizing
    ├── width: "fill" | "hug" | number
    ├── height: "fill" | "hug" | number
    ├── minWidth, maxWidth, minHeight, maxHeight: number
    └── aspectRatio: number
```

### Platform mapping:

| IR Concept | Figma | CSS | SwiftUI | Flutter |
|---|---|---|---|---|
| direction: "horizontal" | layoutMode: "HORIZONTAL" | flex-direction: row | HStack | Row() |
| direction: "vertical" | layoutMode: "VERTICAL" | flex-direction: column | VStack | Column() |
| direction: "stacked" | (no auto-layout) | position: relative | ZStack | Stack() |
| gap: 16 | itemSpacing: 16 | gap: 16px | .spacing(16) | SizedBox(h:16) |
| sizing.width: "fill" | layoutSizingH: "FILL" | flex: 1 | .frame(maxW: .infinity) | Expanded() |
| sizing.width: "hug" | layoutSizingH: "HUG" | (default) | (default) | (default) |

---

## The Prop/Slot Model

```
PropType (union)
├── boolean (default?)
├── text (default?)
├── number (default?, min?, max?)
├── enum (options[], default?)
├── color (default?)
├── dimension (default?, unit?)
├── slot (allowedTypes?)
├── action (payload?)
├── asset (assetType: image | icon | video)
├── object (shape: Record<string, PropType>)
└── array (items: PropType)
```

### Platform mapping:

| IR Prop | Figma | React | SwiftUI |
|---|---|---|---|
| boolean | BOOLEAN property | boolean prop | Bool param |
| text | TEXT property | string prop | String param |
| slot | INSTANCE_SWAP property | ReactNode prop | @ViewBuilder closure |
| enum | VARIANT property | union type prop | enum param |
| action | N/A | () => void prop | Action closure |

---

## Example: A Settings Screen in the IR

```json
{
  "version": "1.0",
  "root": "screen-1",
  "catalog": { "name": "dd-catalog", "version": "1.0.0" },
  "tokens": {
    "color.surface.primary": "#FAFAFA",
    "color.text.primary": "#000000",
    "color.brand.accent": "#634AFF",
    "type.heading.lg": { "fontFamily": "Inter", "fontSize": 24, "fontWeight": 700 },
    "type.body.md": { "fontFamily": "Inter", "fontSize": 16, "fontWeight": 400 },
    "space.s16": 16,
    "space.s24": 24
  },
  "elements": {
    "screen-1": {
      "type": "Screen",
      "layout": { "direction": "vertical", "sizing": { "width": "fill", "height": "fill" } },
      "children": ["header-1", "content-1", "nav-1"],
      "style": { "backgroundColor": "{color.surface.primary}" }
    },
    "header-1": {
      "type": "Header",
      "props": { "title": "Settings" },
      "slots": { "leading": ["back-btn-1"] },
      "style": { "font": "{type.heading.lg}", "color": "{color.text.primary}" }
    },
    "back-btn-1": {
      "type": "Button",
      "props": { "icon": "arrow-left", "variant": "ghost" }
    },
    "content-1": {
      "type": "ScrollView",
      "layout": { "direction": "vertical", "gap": "{space.s24}", "padding": { "top": "{space.s16}", "left": "{space.s16}", "right": "{space.s16}" } },
      "children": ["section-1", "section-2"],
      "style": { "sizing": { "width": "fill", "height": "fill" } }
    },
    "section-1": {
      "type": "Section",
      "props": { "heading": "Notifications" },
      "children": ["toggle-1", "toggle-2"],
      "layout": { "direction": "vertical", "gap": "{space.s16}" }
    },
    "toggle-1": {
      "type": "ToggleRow",
      "props": { "label": "Push notifications", "subtitle": "Get notified about updates", "default": true },
      "style": { "label.font": "{type.body.md}", "label.color": "{color.text.primary}" }
    },
    "toggle-2": {
      "type": "ToggleRow",
      "props": { "label": "Email digest", "subtitle": "Weekly summary", "default": false }
    },
    "section-2": {
      "type": "Section",
      "props": { "heading": "Account" },
      "children": ["nav-row-1", "danger-btn-1"],
      "layout": { "direction": "vertical", "gap": "{space.s16}" }
    },
    "nav-row-1": {
      "type": "NavigationRow",
      "props": { "label": "Change password", "icon": "lock" },
      "on": { "tap": { "action": "navigate", "target": "/change-password" } }
    },
    "danger-btn-1": {
      "type": "Button",
      "props": { "label": "Delete account", "variant": "destructive" },
      "style": { "color": "{color.feedback.danger}" }
    },
    "nav-1": {
      "type": "BottomNav",
      "props": { "items": ["Home", "Search", "Settings"], "activeIndex": 2 },
      "style": { "backgroundColor": "{color.surface.primary}", "activeColor": "{color.brand.accent}" }
    }
  }
}
```

This same JSON can be:
- **Generated by** the Pattern Language engine (from a prompt)
- **Parsed from** a Figma file (via compositional analysis)
- **Parsed from** a React codebase (via AST analysis)
- **Rendered to** Figma (via MCP calls with variable bindings)
- **Rendered to** React + shadcn (via JSX generation)
- **Rendered to** SwiftUI (via View generation)
- **Critiqued** by the cascade (rule-based, structural, visual)

---

## The Information Hierarchy

### Universal (every platform needs)
- Component type, text content, nesting structure
- Layout direction, sizing, spacing, alignment
- Visibility, semantic role
- Component props (boolean, text, enum selections)

### Platform-Specific (handled via $platform hints)
- CSS grid-template-columns, media queries, z-index
- Figma constraints, absolute positioning within auto-layout
- SwiftUI alignment guides, environment values
- Flutter Expanded vs Flexible distinction
- Animation/transition specifics

### Derivable (computed from universal)
- Responsive breakpoints (from sizing constraints)
- Accessibility labels (from text content + semantic role)
- Tab order (from document order + semantic role)
- Color contrast ratios (from foreground/background tokens)
- Touch target sizes (from sizing + platform guidelines)

---

## Relationship to Existing Codebase

| Existing | IR Equivalent | Gap |
|----------|--------------|-----|
| `tokens` + `token_values` | `tokens` in CompositionSpec | Already solved |
| `nodes` (40+ columns) | `elements` (flat map) | nodes is Figma-specific; elements is abstract |
| `node_token_bindings` | `style` on each Element (token refs) | Same concept, different format |
| `components` + `component_slots` | Catalog component definitions | Needs expansion to 45-50 canonical types |
| `screens` | CompositionSpec (one per screen) | Needs skeleton + structural data |
| `instance_overrides` | `props` on each Element | Similar concept |

The compositional analysis layer bridges: Figma `nodes` → abstract `elements`. The reverse (generation) bridges: abstract `elements` → Figma MCP calls.

---

## Resolved Architectural Decisions (Steelman Review, 2026-04-01)

The IR was stress-tested for failure modes. Seven potential breaking points were identified, discussed, and resolved:

### 🔴 Catalog Granularity (RESOLVED: Composition over proliferation)

**Problem**: Real designs have components that don't fit the ~45 canonical types (e.g., a "Testimonial Card" that's neither a Card nor a Quote).

**Decision**: The catalog stays at ~45-50 primitive types. Complex components are COMPOSITIONS of catalog types, not new types. A Testimonial is `{ type: "Card", children: ["avatar-1", "quote-1", "attribution-1"] }`. The catalog doesn't need a "Testimonial" type — it's a composition pattern. Components are subtypes expressed through composition, not through catalog expansion.

**Implication**: The IR must support free nesting of catalog types. The Pattern Language and taste model capture common compositions as patterns, but the IR itself doesn't enumerate them as types.

### 🔴 Style Specificity (RESOLVED: Smart defaults + token overrides)

**Problem**: A Button in shadcn has `rounded-md px-4 py-2`. A Button in MUI has different defaults. If the design has a non-standard Button (e.g., square corners), how does the IR communicate this?

**Decision**: IR style values are OVERRIDES, not complete style definitions. Base styling comes from the target library's defaults. IR token references add or replace specific properties. If the IR says `style: { borderRadius: "{radius.v0}" }` and `radius.v0` = 0, the renderer applies square corners regardless of its default.

**Implication**: Renderers must implement a "base + override" model. Token references in the IR always win over library defaults. Absence of a style property means "use the library default."

### 🟡 Layout Precision (RESOLVED: Intent-preserving graceful degradation)

**Problem**: CSS Grid, SwiftUI LazyVGrid, and complex responsive layouts have no clean universal representation. The flexbox model covers ~90%.

**Decision**: Graceful degradation. The IR expresses layout INTENT (these regions should be arranged in a 2x2 layout). Each renderer does its best with native capabilities. CSS uses grid. Figma uses nested auto-layout frames. SwiftUI uses LazyVGrid. Results aren't pixel-identical but are intent-preserving. The `$platform` hints escape hatch carries platform-specific overrides when needed.

**Implication**: Accept that the IR is not lossless for layout. It captures intent. Renderers produce the closest faithful representation their platform supports.

### 🟡 Parser Completeness (RESOLVED: Optional fields + smart defaults)

**Problem**: Different inputs provide different levels of information. A Figma file gives everything. A prompt gives almost nothing. A screenshot gives visual information but no token values.

**Decision**: All fields in the IR are optional. The IR is valid at any level of completeness. A generator receiving a partially-filled IR applies sensible defaults from the catalog or target library. This aligns with the Pattern Language — early levels produce partial IRs that get more complete as you descend through abstraction levels.

**Implication**: Every IR field must have a sensible default behavior when absent. Generators must be robust to partial input. The IR spec must document what "not specified" means for each field.

### 🟡 Behavior/Interactivity (RESOLVED: Intent-level, defer specifics)

**Problem**: Interactive behavior varies wildly — Figma prototype connections, React event handlers, SwiftUI gestures, Flutter GestureDetector. No clean universal representation for complex interactions.

**Decision**: The IR captures interaction INTENT: "this element is interactive" and "this is the action type" (navigate, toggle, dismiss, submit). Platform-specific interaction mechanics are generator concerns. Complex interactions (swipe-to-delete, long-press menus, drag-and-drop) are deferred to `$platform` hints or future IR extensions.

**Implication**: v1 of the IR supports tap/click, navigation, and state toggles. More complex interactions are explicitly out of scope and handled per-platform.

### 🟢 Asset References (RESOLVED: Platform-agnostic keys + manifest)

**Problem**: An Image element needs different references per platform — Figma image hash, URL for web, asset catalog entry for iOS.

**Decision**: Asset references use platform-agnostic keys (e.g., `"hero-banner"`). An asset manifest maps keys to platform-specific locations. This is a solved pattern (same as design tokens for values, but for binary assets).

### 🟢 Rich Text (RESOLVED: Minimal inline markup, add complexity as needed)

**Problem**: Paragraphs with bold, italic, and linked text vary in representation across platforms.

**Decision**: Use a minimal inline markup format (markdown-like spans). Renderers translate to their native rich text model. Start minimal, add complexity as testing reveals what's needed. Text formatting can vary significantly even inline — this is acknowledged as an area that will grow.

---

## What No Existing System Does

| Capability | json-render | A2UI | Mitosis | SDUI | **Our IR** |
|---|---|---|---|---|---|
| Design tool input (Figma) | No | No | No | No | **Yes** |
| Design tool output (Figma) | No | No | No | No | **Yes** |
| Code input (parse React) | No | No | Yes (web) | No | **Yes** |
| Code output (generate) | Yes | Yes | Yes | Yes | **Yes** |
| Token references | No | No | No | No | **Yes** |
| Layout abstraction | No | Basic | No (CSS) | Yes | **Yes** |
| Bidirectional | No | No | No | No | **Yes** |
| Prompt input | Yes | Yes | No | No | **Yes** |
| Screenshot input | No | No | No | No | **Yes** |
| Visual critique | No | No | No | No | **Yes** |

The combination of bidirectionality + design tool support + token bindings + layout abstraction is genuinely unoccupied territory.
