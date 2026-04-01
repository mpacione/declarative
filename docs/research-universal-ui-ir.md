# Research: Universal Abstract Intermediate Representation for UI Compositions

## Executive Summary

This document surveys existing approaches to creating format-agnostic, cross-platform UI intermediate representations. The goal: a single abstract schema that can be **parsed FROM** any input (Figma, React, SwiftUI, screenshots, prompts) and **generated TO** any output (Figma, React, SwiftUI, Flutter, HTML).

The core finding: **nobody has fully solved this**. Every existing system makes different tradeoffs between abstraction and fidelity. But a clear consensus architecture is emerging around a **flat, typed, component-tree with separated concerns** (structure vs. style vs. behavior vs. layout).

---

## 1. Existing Universal UI IRs

### 1.1 Mitosis (Builder.io) — The Closest Analog

**What it is**: A compiler that takes one component source and produces native code for React, Vue, Svelte, Angular, Solid, Qwik, Alpine, and more. Uses LLVM as its explicit conceptual model — one IR, many backends.

**Key architectural insight**: Mitosis does NOT use a runtime abstraction. It compiles to native framework code. The IR is a static JSON AST that captures structure, state, bindings, and lifecycle — then serializers translate to each target.

**The MitosisComponent IR** (actual structure from source):
```json
{
  "@type": "@builder.io/mitosis/component",
  "name": "MyComponent",
  "imports": [{ "path": "@builder.io/mitosis", "imports": { "useStore": "useStore" } }],
  "state": [
    { "name": "count", "type": "property", "propertyType": "normal", "code": "0" },
    { "name": "handleClick", "type": "function", "code": "() => { state.count++ }" }
  ],
  "hooks": {
    "onInit": { "code": "..." },
    "onMount": [{ "code": "console.log('mounted')", "onSSR": false }],
    "onUpdate": [],
    "onUnMount": null
  },
  "context": { "get": {}, "set": {} },
  "refs": {},
  "children": [ /* MitosisNode[] */ ],
  "meta": {},
  "inputs": [],
  "props": {},
  "defaultProps": {}
}
```

**The MitosisNode IR** (the tree node):
```json
{
  "@type": "@builder.io/mitosis/node",
  "name": "div",
  "properties": { "className": "container", "id": "main" },
  "bindings": {
    "value": { "bindingType": "expression", "code": "state.name", "type": "single" },
    "onClick": { "bindingType": "function", "code": "handleClick()", "arguments": ["event"] }
  },
  "children": [],
  "slots": {},
  "scope": {},
  "meta": {}
}
```

Three node variants via a union type:
- **BaseNode** — standard elements
- **ForNode** — iteration (`name: 'For'`, scope includes `forName`, `indexName`, `collectionName`)
- **ShowNode** — conditional rendering (`name: 'Show'`)

**Relevance to our problem**: Mitosis proves the IR approach works for code-to-code. But it does NOT handle:
- Design tool inputs (Figma node trees)
- Visual/screenshot inputs
- Layout abstraction (it uses CSS classes directly)
- Non-web targets (SwiftUI, Flutter)

It is a WEB framework compiler, not a universal UI IR.

Sources:
- [BuilderIO/mitosis GitHub](https://github.com/BuilderIO/mitosis)
- [Mitosis Overview](https://mitosis.builder.io/docs/overview/)
- [DeepWiki Mitosis](https://deepwiki.com/BuilderIO/mitosis)

---

### 1.2 Yoga (Meta) — The Layout-Only IR

**What it is**: A cross-platform layout engine implementing CSS Flexbox, written in C++ with bindings for Java, Swift, C#, and JavaScript. Used by React Native, Litho (Android), and ComponentKit (iOS).

**Key insight**: Yoga solves ONLY the layout problem, but it does it universally. It takes a flexbox-like specification and computes absolute positions/sizes that any renderer can use.

**The layout model** is flexbox with these properties:
- `flexDirection` (row, column, row-reverse, column-reverse)
- `justifyContent` (flex-start, center, flex-end, space-between, space-around, space-evenly)
- `alignItems` / `alignSelf` / `alignContent`
- `flexWrap`
- `flexGrow` / `flexShrink` / `flexBasis`
- `width` / `height` / `minWidth` / `maxWidth` / `minHeight` / `maxHeight`
- `margin` / `padding` / `border` (all four sides)
- `gap` (row and column)
- `position` (relative, absolute)
- `aspectRatio`

**Why this matters**: Yoga proves that flexbox IS the universal layout abstraction. Every platform has mapped to it:
- CSS flexbox = native
- Figma auto-layout = flexbox with slight differences
- SwiftUI HStack/VStack = flexbox direction
- Flutter Row/Column = flexbox direction
- React Native = Yoga directly

The remaining gaps between platforms are small and well-documented.

Sources:
- [Yoga Layout Engine - Meta Engineering](https://engineering.fb.com/2016/12/07/android/yoga-a-cross-platform-layout-engine/)
- [Yoga Layout](https://www.yogalayout.dev/)

---

### 1.3 Flutter Widget Tree

Flutter uses a single rendering engine (Skia/Impeller) on all platforms. Its "IR" is the widget tree itself:
- `Row` / `Column` / `Stack` for layout (maps to flexbox concepts)
- Widgets are composable functions that return other widgets
- Layout is computed by Flutter's own engine, not platform-native layout

**Key insight**: Flutter avoids the cross-platform layout problem entirely by owning the renderer. It doesn't need to TRANSLATE layout — it computes it once.

### 1.4 Compose Multiplatform (JetBrains/Kotlin)

Similar to Flutter — compiles Kotlin composable functions through Kotlin's FIR (Frontend Intermediate Representation), then renders via Skiko (Kotlin wrapper for Skia) on all platforms.

**Key insight**: Like Flutter, Compose sidesteps translation by owning the rendering pipeline. The IR is Kotlin's compiler IR, not a UI-specific format.

Sources:
- [Compose Multiplatform GitHub](https://github.com/JetBrains/compose-multiplatform)

---

## 2. json-render (Vercel) — AI-to-UI Schema

**What it is**: A framework where developers define a component catalog with Zod schemas, an LLM generates a constrained JSON spec, and a renderer maps it to platform-specific implementations. Supports React, Vue, Svelte, Solid, React Native, PDF, email, video, terminal, and 3D.

**The Three-Phase Architecture**:
1. **Definition** — developer defines catalog (Zod schemas)
2. **Generation** — LLM produces spec (constrained JSON)
3. **Rendering** — platform-specific registry renders it

**Catalog Definition** (actual code):
```typescript
const catalog = defineCatalog(schema, {
  components: {
    Card: {
      props: z.object({ title: z.string() }),
      description: "A card container",
    },
    Metric: {
      props: z.object({
        label: z.string(),
        value: z.string(),
        format: z.enum(["currency", "percent", "number"]).nullable(),
      }),
      description: "Display a metric value",
    },
  },
  actions: {
    export_report: { description: "Export dashboard to PDF" },
  },
});
```

**The Spec Format** (flat element structure):
```typescript
type Spec = {
  root: string;              // entry point element key
  elements: Record<string, UIElement>;
  state?: Record<string, any>;
};

type UIElement = {
  type: string;              // component name from catalog
  props: Record<string, any>;
  children?: string[];       // references to other element keys
  on?: Record<string, Action>;
  visible?: VisibilityCondition;
};
```

Example spec:
```json
{
  "root": "card-1",
  "elements": {
    "card-1": {
      "type": "Card",
      "props": { "title": "Dashboard" },
      "children": ["metric-1", "metric-2"]
    },
    "metric-1": {
      "type": "Metric",
      "props": { "label": "Revenue", "value": "$1.2M", "format": "currency" }
    },
    "metric-2": {
      "type": "Metric",
      "props": { "label": "Growth", "value": "23%", "format": "percent" }
    }
  }
}
```

**Registry** (platform-specific implementations):
```typescript
const { registry } = defineRegistry(catalog, {
  components: {
    Card: ({ props, children }) => (
      <div className="card"><h3>{props.title}</h3>{children}</div>
    ),
    Metric: ({ props }) => (
      <div className="metric"><span>{props.label}</span></div>
    ),
  },
});
```

**Key design decisions**:
- **Flat, not nested**: Elements reference children by key, not by nesting. Enables streaming, partial updates via JSON Patch (RFC 6902), and efficient LLM generation.
- **Catalog-constrained**: The LLM can only produce components declared in the catalog. This is the contract between AI and application.
- **Platform-agnostic spec, platform-specific registry**: The same spec renders differently on each platform.
- **No layout primitives**: json-render does NOT define layout. Components handle their own layout. This is both a feature (simplicity) and a limitation (no cross-platform layout abstraction).

**Relevance**: json-render's flat spec + catalog + registry architecture is directly applicable. The key gap is that it has NO layout system and NO design tool integration.

Sources:
- [json-render GitHub](https://github.com/vercel-labs/json-render)
- [InfoQ: Vercel Releases JSON-Render](https://www.infoq.com/news/2026/03/vercel-json-render/)
- [DeepWiki json-render](https://deepwiki.com/vercel-labs/json-render)

---

## 3. A2UI (Google) — Agent-to-User Interface

**What it is**: An open protocol for AI agents to generate rich, updatable UIs. Apache 2.0, with contributions from CopilotKit.

**Protocol Messages** (server-to-client):
1. `createSurface` — initialize a UI area with a catalog reference
2. `updateComponents` — provide component definitions as a flat list
3. `updateDataModel` — update data at JSON Pointer paths
4. `deleteSurface` — remove a UI area

**Component Model** (adjacency list, like json-render):
```json
{
  "id": "heading-1",
  "component": "Text",
  "text": "Welcome"
}
```
```json
{
  "id": "layout-1",
  "component": "Row",
  "children": ["heading-1", "button-1"]
}
```

**Key differences from json-render**:
- A2UI includes **layout primitives** (Row, Column, List, Card)
- A2UI has **data binding** via JSON Pointers (RFC 6901) — both absolute (`/user/name`) and relative paths
- A2UI supports **dynamic types** (DynamicString, DynamicNumber, DynamicBoolean) for reactive data
- A2UI has **validation functions** (required, email, etc.) built into the schema
- v0.9 is designed for **prompt embedding** rather than structured output

**Built-in Components** (from the basic catalog):
- **Layout**: Row, Column, List, Card
- **Input**: TextField, CheckBox, ChoicePicker, DateTimeInput, Slider
- **Display**: Text, Button, Image, Link, Divider
- **Interactive**: Button with server actions

**Transport**: JSONL stream, transport-agnostic (works over A2A, AG-UI, MCP, SSE, WebSocket)

**Relevance**: A2UI's component model with built-in layout primitives is closer to what a universal IR needs. But it's designed for agent-generated UIs, not design tool / code generation bidirectional flows.

Sources:
- [A2UI Specification v0.9](https://a2ui.org/specification/v0.9-a2ui/)
- [Google A2UI GitHub](https://github.com/google/A2UI/)
- [Google Developers Blog: Introducing A2UI](https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/)

---

## 4. SDUI Schemas (Airbnb, Netflix, Lyft)

### 4.1 Airbnb Ghost Platform

**Core model**: Sections + Screens

- **Section**: The atomic UI building block. Contains pre-translated, pre-localized, pre-formatted data. Each section has a `SectionComponentType` that controls rendering.
- **Screen**: Describes layout — where sections appear (called "placements"). Uses `ILayout` interface with `LayoutsPerFormFactor` for responsive rendering.

**GraphQL schema structure**:
```graphql
interface GPResponse {
  sections: [SectionContainer!]!
  screens: [Screen!]!
}

type SectionContainer {
  section: Section  # union of all section types
  metadata: SectionMetadata
  loggingData: LoggingData
}
```

**Key insight**: Airbnb separates DATA (sections) from LAYOUT (screens). One section type can render in multiple ways via different `SectionComponentType` values. Layout is specified per form factor.

### 4.2 Lyft Canvas

Uses **Protocol Buffers** (not JSON/GraphQL):
- Primitives: buttons, layouts, action callbacks defined in protobuf
- Renderers on each platform interpret the hierarchy
- Feature-agnostic backend manages screen templates

**Key insight**: Lyft chose protobuf for 40-60% smaller payloads and faster serialization. They advise designing components for business requirements, not maximal flexibility.

### 4.3 Netflix CLSC/UMA

Uses **JSON** wire protocol. Built CLSC as a wrapper around Hawkins (their design system), not as a general-purpose UI specification.

**Key insight**: Netflix wraps their existing design system rather than creating a new abstraction. The SDUI layer is thin — it maps to known Hawkins components.

### 4.4 Common SDUI Pattern

All SDUI systems converge on a similar JSON shape:
```json
{
  "type": "Column",
  "children": [
    { "type": "Image", "props": { "url": "https://..." } },
    { "type": "Text", "props": { "value": "Product Name", "style": "title" } },
    { "type": "Button", "props": { "label": "Add to cart", "action": "ADD_TO_CART" } }
  ]
}
```

Sources:
- [Airbnb Ghost Platform Deep Dive](https://medium.com/airbnb-engineering/a-deep-dive-into-airbnbs-server-driven-ui-system-842244c5f5)
- [Apollo GraphQL SDUI Schema Design](https://www.apollographql.com/docs/graphos/schema-design/guides/sdui/schema-design)

---

## 5. Design Token Formats as Inspiration

### 5.1 DTCG (W3C Design Tokens Community Group) — v2025.10

The DTCG specification provides a JSON format for expressing design decisions in a platform-agnostic way. Reached stable v1 in October 2025 with backing from Adobe, Amazon, Google, Microsoft, Meta, Figma, and others.

**Token format**:
```json
{
  "colors": {
    "$type": "color",
    "primary": {
      "$value": { "colorSpace": "srgb", "components": [0, 0.4, 0.8] },
      "$description": "Main brand color"
    }
  },
  "spacing": {
    "$type": "dimension",
    "sm": { "$value": { "value": 8, "unit": "px" } },
    "md": { "$value": { "value": 16, "unit": "px" } }
  }
}
```

**Cross-platform translation strategy**:
- `px` converts to `dp` (Android), `pt` (iOS)
- `rem` can convert to fixed pixels using a base font size
- Font weights use OpenType `wght` numeric values (platform-agnostic)
- Colors support sRGB, Display P3, Oklch

**Alias/reference system**:
```json
{
  "semantic": {
    "primary": { "$value": "{colors.primary}" }
  }
}
```

**Three-layer organizational pattern** (from Martin Fowler article):
1. **Option tokens** (primitives): Available choices (color palette, spacing scale)
2. **Decision tokens** (semantic): Which option for which purpose
3. **Component tokens**: Which decision for which element in which component

### 5.2 Can the Token Approach Work for Components?

**Yes, with caveats.** The key parallel:

| Design Tokens | Component IR |
|---|---|
| Token type (color, dimension) | Component type (Button, Card) |
| Token value | Component props/configuration |
| Token alias/reference | Component composition (children) |
| Platform translation | Platform-specific rendering |
| Three-layer hierarchy | Primitive → Semantic → Composed |

**What tokens get right for components**:
- Platform-agnostic VALUE specification with platform-specific TRANSLATION
- Alias/composition system for building complex from simple
- Hierarchical organization (option → decision → component)
- Single source of truth with automated distribution

**What tokens DON'T solve for components**:
- Layout (tokens are values, not spatial relationships)
- Behavior/interactivity (tokens are static)
- Composition structure (tokens are flat key-value, components are trees)

Sources:
- [DTCG Specification](https://www.designtokens.org/tr/drafts/format/)
- [Design Token-Based UI Architecture (Martin Fowler)](https://martinfowler.com/articles/design-token-based-ui-architecture.html)

---

## 6. The Layout Abstraction Problem

This is the hardest part of the universal IR. Here is how each platform represents the same concept:

### 6.1 Layout Property Mapping

| Concept | Figma Auto-Layout | CSS Flexbox | SwiftUI | Flutter |
|---|---|---|---|---|
| Horizontal flow | `layoutMode: "HORIZONTAL"` | `flex-direction: row` | `HStack` | `Row()` |
| Vertical flow | `layoutMode: "VERTICAL"` | `flex-direction: column` | `VStack` | `Column()` |
| Stacking/overlap | Absolute positioning | `position: absolute` or grid | `ZStack` | `Stack()` |
| Gap between items | `itemSpacing: 16` | `gap: 16px` | `.spacing(16)` | `MainAxisAlignment.spaceEvenly` or `SizedBox` |
| Padding | `paddingTop/Right/Bottom/Left` | `padding: 16px` | `.padding(16)` | `EdgeInsets.all(16)` |
| Main axis align | `primaryAxisAlignItems` | `justify-content` | HStack alignment param | `mainAxisAlignment` |
| Cross axis align | `counterAxisAlignItems` | `align-items` | VStack alignment param | `crossAxisAlignment` |
| Child sizing: fill | `layoutSizingHorizontal: "FILL"` | `flex: 1` | `.frame(maxWidth: .infinity)` | `Expanded()` |
| Child sizing: hug | `layoutSizingHorizontal: "HUG"` | (default) | (default) | (default) |
| Child sizing: fixed | `layoutSizingHorizontal: "FIXED"` | `width: 100px` | `.frame(width: 100)` | `SizedBox(width: 100)` |
| Wrap | `layoutWrap: "WRAP"` | `flex-wrap: wrap` | Not native (LazyVGrid) | `Wrap()` |

### 6.2 The Universal Layout Model

Based on this analysis, flexbox IS the universal layout abstraction. Every platform maps to it. The minimal layout model:

```typescript
type LayoutDirection = "horizontal" | "vertical" | "stacked";

type LayoutSizing = "fill" | "hug" | "fixed";

type LayoutAlignment = "start" | "center" | "end" | "stretch" | "space-between";

type Layout = {
  direction: LayoutDirection;
  gap?: number;                          // spacing between children
  padding?: {
    top?: number;
    right?: number;
    bottom?: number;
    left?: number;
  };
  mainAxisAlignment?: LayoutAlignment;
  crossAxisAlignment?: LayoutAlignment;
  wrap?: boolean;
  sizing?: {
    width?: LayoutSizing;
    height?: LayoutSizing;
    fixedWidth?: number;
    fixedHeight?: number;
    minWidth?: number;
    maxWidth?: number;
    minHeight?: number;
    maxHeight?: number;
  };
};
```

### 6.3 Platform-Specific Gaps (The Lossy Parts)

Things that DO NOT map cleanly:
- **CSS Grid**: No equivalent in Figma, SwiftUI (LazyVGrid is partial), or Flutter (GridView is different)
- **SwiftUI alignment guides**: Custom alignment that has no CSS/Figma equivalent
- **Figma absolute positioning within auto-layout**: Special case behavior
- **Flutter's `Expanded` vs `Flexible`**: More nuanced than the universal model
- **Responsive breakpoints**: Each platform handles differently (CSS media queries, SwiftUI GeometryReader, Figma device frames)
- **Text wrapping / overflow**: Platform-specific behavior

**How to handle the lossy gap**: Use a **platform hints** extension mechanism:
```json
{
  "layout": { "direction": "horizontal", "gap": 16 },
  "$platform": {
    "css": { "display": "grid", "gridTemplateColumns": "1fr 2fr" },
    "figma": { "layoutMode": "HORIZONTAL", "layoutWrap": "NO_WRAP" },
    "swiftui": { "alignmentGuide": ".leading" }
  }
}
```

---

## 7. Slot/Prop Abstraction

### 7.1 Cross-Platform Property Mapping

| Concept | Figma | React | SwiftUI | Flutter |
|---|---|---|---|---|
| Boolean toggle | BOOLEAN property | `boolean` prop | `Bool` parameter | `bool` parameter |
| Text content | TEXT property | `string` prop / children | `String` parameter | `String` parameter |
| Component slot | INSTANCE_SWAP property | `ReactNode` prop / children | `@ViewBuilder` closure | `Widget` parameter |
| Variant selection | VARIANT property | Union type prop | Enum parameter | Enum parameter |
| Event handler | N/A | `() => void` prop | Action closure | VoidCallback |
| Style override | N/A | `className` / `style` prop | ViewModifier | ThemeData |

### 7.2 Universal Prop Model

```typescript
type PropType =
  | { kind: "boolean"; default?: boolean }
  | { kind: "text"; default?: string }
  | { kind: "number"; default?: number; min?: number; max?: number }
  | { kind: "enum"; options: string[]; default?: string }
  | { kind: "slot" }                    // child component(s)
  | { kind: "action"; payload?: PropType }  // event handler
  | { kind: "asset"; assetType: "image" | "icon" | "video" };

type ComponentSpec = {
  name: string;
  description?: string;
  props: Record<string, {
    type: PropType;
    required?: boolean;
    description?: string;
  }>;
  slots?: Record<string, {
    description?: string;
    allowedTypes?: string[];   // restrict which components can fill this slot
  }>;
};
```

---

## 8. Academic Work

### 8.1 UIML (User Interface Markup Language)

Early academic work (2001) on building UIs with a generic vocabulary rendered for multiple platforms. Introduced the concept of a "logical model" that captures UI at a higher abstraction than any physical model, mapping to different platforms.

### 8.2 UI-UG (2025)

Recent paper on unified multimodal LLM for UI understanding AND generation. Uses a JSON-based DSL:

```json
{
  "type": "Tag",
  "name": "div",
  "className": "flex gap-4 p-6",
  "params": {
    "textContent": { "bindType": "Static", "value": "Hello" }
  },
  "children": [...]
}
```

Key features:
- Supports both `Static` and `Data` bind types (hardcoded vs. dynamic)
- Uses Tailwind CSS tokens for styling
- Handles UI understanding (screenshot/DOM to DSL) AND generation (prompt to DSL)

### 8.3 SpecifyUI / Semantic Guidance Papers

Recent work on structured specifications for UI design intent:
- DSLs offer precise control but are too restrictive for design tasks
- Semi-formal specifications incorporate semantic cues but often miss hierarchical structure
- Emerging consensus: intermediate representations that balance semantic meaning with structural precision

Sources:
- [UIML Paper (arxiv)](https://arxiv.org/pdf/cs/0111024)
- [UI-UG Paper (arxiv)](https://arxiv.org/html/2509.24361v2)
- [SpecifyUI (arxiv)](https://arxiv.org/html/2509.07334v1)
- [Bridging Gulfs in UI Generation (arxiv)](https://arxiv.org/html/2601.19171v1)

---

## 9. The Information Hierarchy

Based on all research, information in a UI composition falls into three tiers:

### 9.1 UNIVERSAL (every platform needs it)

- **Component type** — what kind of element (text, button, container, input)
- **Text content** — the actual text strings
- **Nesting structure** — parent-child relationships
- **Layout direction** — horizontal, vertical, stacked
- **Layout sizing** — fill, hug, fixed (+ specific dimensions)
- **Spacing** — gap between children, padding around edges
- **Alignment** — main axis and cross axis
- **Visibility** — whether the element is shown
- **Component props** — boolean toggles, text values, enum selections
- **Semantic role** — heading, paragraph, link, button, input, image

### 9.2 PLATFORM-SPECIFIC (only some platforms need it)

- **CSS-specific**: grid-template-columns, media queries, pseudo-elements, z-index stacking context
- **Figma-specific**: constraints, layout mode details, absolute position within auto-layout, plugin data
- **SwiftUI-specific**: alignment guides, environment values, preference keys
- **Flutter-specific**: Expanded vs Flexible distinction, IntrinsicHeight/Width
- **Accessibility platform details**: iOS VoiceOver hints, Android TalkBack labels, ARIA attributes
- **Animation/transition specifics**: CSS transitions vs. SwiftUI withAnimation vs. Flutter AnimationController

### 9.3 DERIVABLE (can be computed from universal info)

- **Responsive breakpoints** — can be computed from sizing constraints + container queries
- **Accessibility labels** — can be derived from text content + semantic role
- **Tab order** — can be derived from document order + semantic role
- **Color contrast ratios** — can be computed from foreground/background colors
- **Touch target sizes** — can be validated from sizing + platform guidelines
- **RTL layout** — can be mirrored from layout direction

---

## 10. Synthesis: Architecture for a Universal UI IR

### 10.1 The Emerging Consensus Pattern

Every system reviewed converges on similar architectural decisions:

1. **Flat element map, not nested tree** (json-render, A2UI, Airbnb)
   - Children referenced by ID, not by nesting
   - Enables streaming, partial updates, efficient patches
   - Avoids deep nesting complexity

2. **Typed components from a catalog** (json-render, A2UI, all SDUI systems)
   - Components are declared with their allowed props
   - Zod/JSON Schema validates the specification
   - The catalog is the contract

3. **Separated concerns** (all systems)
   - Structure (what components exist, how they nest)
   - Layout (how they are spatially arranged)
   - Style (how they look — colors, typography)
   - Behavior (what happens on interaction)
   - Data (what content they display)

4. **Platform-specific renderers, not platform-specific specs** (Mitosis, json-render, DTCG)
   - One spec, many renderers
   - The renderer knows how to translate to native code
   - Platform hints for cases that don't translate cleanly

### 10.2 Proposed Architecture Sketch

```
┌─────────────────────────────────────────────────┐
│                    INPUTS                        │
│  Figma  │  React  │  SwiftUI  │  Screenshot  │  Prompt  │
└────┬────┴────┬────┴─────┬─────┴──────┬───────┴────┬─────┘
     │         │          │            │            │
     ▼         ▼          ▼            ▼            ▼
┌─────────────────────────────────────────────────┐
│              INPUT PARSERS                       │
│  (platform-specific → universal IR)              │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│            UNIVERSAL IR (the schema)             │
│                                                  │
│  ┌─────────────┐  ┌──────────┐  ┌────────────┐ │
│  │  Component   │  │  Layout  │  │   Style    │ │
│  │  Catalog     │  │  Model   │  │   Tokens   │ │
│  └─────────────┘  └──────────┘  └────────────┘ │
│                                                  │
│  ┌─────────────┐  ┌──────────┐  ┌────────────┐ │
│  │  Composition │  │ Behavior │  │  Platform  │ │
│  │  Tree (flat) │  │  Events  │  │   Hints    │ │
│  └─────────────┘  └──────────┘  └────────────┘ │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│             OUTPUT GENERATORS                    │
│  (universal IR → platform-specific)              │
└────┬────┬────┬─────┬──────┬────┬────────────────┘
     │    │    │     │      │    │
     ▼    ▼    ▼     ▼      ▼    ▼
   Figma React SwiftUI Flutter HTML  ...
```

### 10.3 Proposed IR Shape

Combining the best ideas from all systems:

```typescript
// === COMPOSITION (the tree) ===
type CompositionSpec = {
  version: string;
  root: string;                           // entry element ID
  elements: Record<string, Element>;      // flat map
  catalog: CatalogReference;              // which components are available
  tokens?: Record<string, TokenValue>;    // design token values
};

type Element = {
  id: string;
  type: string;                           // component type from catalog
  props: Record<string, unknown>;         // component-specific props
  children?: string[];                    // child element IDs
  slots?: Record<string, string[]>;       // named slots with element IDs
  layout?: Layout;                        // layout configuration
  style?: StyleOverrides;                 // style token overrides
  on?: Record<string, Action>;            // event handlers
  visible?: Condition;                    // conditional rendering
  repeat?: RepeatBinding;                 // list iteration
  $platform?: Record<string, unknown>;    // platform-specific hints
};

// === LAYOUT (the spatial model) ===
type Layout = {
  direction?: "horizontal" | "vertical" | "stacked";
  gap?: number | string;                  // number = px, string = token ref
  padding?: Spacing;
  mainAxisAlignment?: Alignment;
  crossAxisAlignment?: Alignment;
  wrap?: boolean;
  sizing?: SizingSpec;
};

type Spacing = {
  top?: number | string;
  right?: number | string;
  bottom?: number | string;
  left?: number | string;
};

type SizingSpec = {
  width?: "fill" | "hug" | number;
  height?: "fill" | "hug" | number;
  minWidth?: number;
  maxWidth?: number;
  minHeight?: number;
  maxHeight?: number;
  aspectRatio?: number;
};

type Alignment = "start" | "center" | "end" | "stretch" | "space-between" | "space-around";

// === CATALOG (the contract) ===
type CatalogReference = {
  name: string;
  version: string;
  components: Record<string, ComponentSpec>;
};

type ComponentSpec = {
  description?: string;
  props: Record<string, PropSpec>;
  slots?: Record<string, SlotSpec>;
  category?: string;                      // grouping: layout, input, display, etc.
  semanticRole?: string;                  // heading, paragraph, button, etc.
};

type PropSpec = {
  type: PropType;
  required?: boolean;
  description?: string;
};

type PropType =
  | { kind: "boolean"; default?: boolean }
  | { kind: "text"; default?: string }
  | { kind: "number"; default?: number; min?: number; max?: number }
  | { kind: "enum"; options: string[]; default?: string }
  | { kind: "color"; default?: string }
  | { kind: "dimension"; default?: number; unit?: string }
  | { kind: "slot" }
  | { kind: "action"; payload?: Record<string, PropType> }
  | { kind: "asset"; assetType: "image" | "icon" | "video" }
  | { kind: "object"; shape: Record<string, PropType> }
  | { kind: "array"; items: PropType };

type SlotSpec = {
  description?: string;
  allowedTypes?: string[];
  required?: boolean;
};
```

### 10.4 Key Design Decisions for Our System

1. **Flat element map** — follow json-render and A2UI, not nested trees
2. **Flexbox-based layout model** — follow Yoga, covers all platforms
3. **Token references for style values** — follow DTCG pattern
4. **Platform hints for the lossy gaps** — `$platform` escape hatch
5. **Catalog-first** — components are declared before use (like json-render)
6. **Semantic roles** — enable accessibility derivation
7. **Separate layout from component type** — a Button can be in a horizontal or vertical flow; layout is a property of the container, not the component
8. **String-or-number for spacing values** — numbers are pixels, strings are token references

### 10.5 What Makes This Different from Existing Solutions

| System | Handles Design Tools | Handles Code | Has Layout | Has Tokens | Bidirectional |
|---|---|---|---|---|---|
| Mitosis | No | Yes (web only) | No (CSS direct) | No | No |
| json-render | No | Yes (multi-platform) | No | No | No (generate only) |
| A2UI | No | Partial | Yes (basic) | No | No (generate only) |
| SDUI (Airbnb) | No | Yes (proprietary) | Yes | No | No |
| DTCG | No | No (values only) | No | Yes | N/A |
| **Proposed IR** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

The unique value of the proposed IR is **bidirectionality** (parse FROM and generate TO any platform) combined with **design tool support** (Figma as both input and output).

---

## 11. Open Questions

1. **How deep should the layout model go?** Flexbox covers 90% of cases. Should we include grid? Absolute positioning? Or handle those as platform hints?

2. **How to handle responsive design?** The IR needs to represent breakpoints/variants somehow. Options: multiple compositions per breakpoint, conditional visibility, or a responsive wrapper component.

3. **How to handle animation/transitions?** None of the surveyed systems handle this well. Could be deferred to platform hints.

4. **How to handle form validation?** A2UI includes it (required, email functions). Should validation be in the IR or in behavior logic?

5. **What is the right level of component granularity?** A primitive catalog (Text, Button, Input, Container) or a rich catalog (Card, DataTable, NavigationBar)?

6. **How to handle text styling?** Inline formatting (bold, italic) within text nodes. Rich text is hard to abstract.

7. **How to handle images/assets?** Asset references need to be platform-agnostic (URLs? Asset keys?) with platform-specific delivery (resolution, format).
