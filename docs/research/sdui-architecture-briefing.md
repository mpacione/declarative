# Server-Driven UI Architecture Briefing

Technical deep dive into Airbnb Ghost Platform and the SDUI ecosystem.
Prepared for design-system IR architecture discussion.

---

## 1. What SDUI Is and Why It Exists

Server-Driven UI inverts the traditional client architecture. Instead of the client
containing layout logic and requesting raw domain data, the **server describes what UI
to render** and the client becomes a generic rendering engine that interprets that
description into native components.

The core shift: the API returns **product information** (formatted strings, layout
instructions, component types) rather than **domain data** (raw prices, boolean flags,
enum statuses). The client's job becomes "handle pixels, not data."

### Why companies adopt it

1. **Deployment velocity**: Ship UI changes without app store review cycles. Lyft
   reported experiments going from 2+ weeks (native) to 1-2 days (SDUI).

2. **Cross-platform consistency**: One backend response controls iOS, Android, and web
   simultaneously. No more "the button is blue on iOS but grey on Android because
   three teams diverged."

3. **A/B testing at scale**: Swapping entire screen layouts or section arrangements is
   a server-side config change. Airbnb described it as "changing one source of truth
   in our backend."

4. **No version fragmentation**: Old app versions get payloads they understand. No
   "please update your app" for UI changes. The server adapts the response to the
   client's declared capabilities.

5. **Feature flag integration**: Features can be toggled per cohort, geography, or
   behavior without deploying new binaries.

---

## 2. Airbnb Ghost Platform Architecture

Ghost Platform (GP) is Airbnb's production SDUI system. The name comes from
**G**uest + **Host** = Ghost. It powers search, listing pages, checkout, and the
majority of their most-used features.

### 2.1 The Three Primitives

Ghost has exactly three building blocks:

**Sections** -- The most primitive unit. A section is a cohesive group of UI
components with pre-formatted data (already translated, localized, formatted). Sections
are fully independent of surrounding context, which is what makes them reusable across
features without business-logic coupling. Examples: `HeroSection`, `TitleSection`.

**Screens** -- Define layout and orchestration. A screen specifies:
- Which layout to use (via `LayoutsPerFormFactor` for responsive behavior)
- Where sections appear (called "placements")
- Presentation metadata (modal, bottom sheet, full-screen, popover)
- Logging configuration

**Actions** -- Handle user interactions. When a user taps a button inside a section
component, it fires an `IAction` instance. The GP infrastructure routes this to
feature-specific event handlers. Standard generic actions handle navigation and
scrolling; features define custom `IAction` types for specialized behavior.

### 2.2 The GPResponse Structure

A single response contains:
- An arbitrary number of screens
- A **central sections array** (shared/referenced, not embedded per-screen)
- Metadata for cross-platform rendering

This is a pointer-based architecture: screens reference sections by ID rather than
embedding them. This enables section reuse across multiple screens and layout
configurations, and optimizes response payload size.

### 2.3 The SectionComponentType System

This is the key type-system concept. `SectionComponentType` is an enum that controls
**how** a section's data model gets rendered, enabling one data model to produce
multiple visual presentations.

Example: `TITLE` and `PLUS_TITLE` both use the same `TitleSection` data model, but
`PLUS_TITLE` renders with Airbnb Plus-specific logo and title styling.

Each `SectionComponentType` maps to exactly **one** rendering implementation per
platform. The mapping is:

```
SectionComponentType  +  Platform  -->  Exactly one native component
```

This is essentially a **component registry** keyed by (type_enum, platform).

### 2.4 Layout System

Layouts implement the `ILayout` interface. Concrete implementations include
`SingleColumnLayout` and `MultiColumnLayout`. The rendering pipeline:

1. Determine form factor (compact = mobile, wide = tablet/desktop)
2. Select appropriate layout via `LayoutsPerFormFactor`
3. For each placement in the layout:
   a. Locate the `SectionDetail` object
   b. Resolve section data by ID from the root sections array
   c. Instantiate the appropriate section component (keyed by `SectionComponentType`)
   d. Position the built UI into the designated layout region

Layout is **not** a generic flexbox/grid system. It's a constrained set of layout
types that the client knows how to render. The server picks which layout type to use
and fills its slots.

### 2.5 Responsive Behavior

Ghost uses `LayoutsPerFormFactor` -- the server sends different layout configurations
for compact (mobile) and wide (tablet/desktop) breakpoints. The client selects the
appropriate layout based on its form factor. This is a **discrete** responsive model
(pick one of N layouts) rather than a **continuous** one (fluid CSS-like constraints).

### 2.6 Data Model (GraphQL)

A single shared GraphQL schema serves all platforms. Key patterns:

```graphql
union Section = HeroSection | TitleSection | PriceSection | ...
```

Section types are union members. The `__typename` field acts as the routing key for
the component registry.

Data is pre-formatted at the source: strings come localized, prices come formatted,
dates come human-readable. The client does minimal transformation.

### 2.7 Deferred Loading / Pagination

Ghost uses GraphQL operation registry with deferred responses. Above-the-fold content
loads immediately; additional sections load progressively as the user scrolls. This is
essentially **UI pagination** -- the screen definition says "here are placements for
10 sections" but only the first 3 resolve immediately.

### 2.8 The Viaduct Service Mesh

GP sits on top of Viaduct, Airbnb's unified data-service mesh. Viaduct provides
the shared data layer across backend services, enabling centralized schema management
and consistent data transformation. GP is not an isolated system -- it's a UI layer
on top of a mature data infrastructure.

---

## 3. How A/B Testing Works

In a traditional architecture, A/B testing UI requires:
1. Both variants compiled into the client binary
2. Feature flags evaluated client-side
3. App store deployment before the experiment can run
4. Waiting for adoption rollout

With SDUI, A/B testing becomes a server-side concern:
1. The server decides which variant to serve based on user cohort
2. Different sections, different layouts, or entirely different screens get returned
3. Changes deploy instantly -- no app store wait
4. Rollback is a server config change

The Ghost response structure naturally supports this: the server can include/exclude
sections, swap `SectionComponentType` values, or return entirely different screen
configurations based on experiment assignment.

---

## 4. Comparison: Other SDUI Systems

### 4.1 Lyft Canvas

**Serialization**: Protocol Buffers (not GraphQL). Chosen for compact binary format
and built-in field-level versioning (numbered fields enable forward/backward compat).

**Component model**: Primitives defined in protobuf schemas -- buttons, layouts, action
callbacks. Renderers on each platform interpret the hierarchy.

**Key difference from Airbnb**: Lyft went lower-level. Where Airbnb has
domain-specific section types (`HeroSection`, `TitleSection`), Lyft's primitives are
more generic (closer to "button" and "stack" than "hero image carousel").

**Versioning**: Protobuf's numbered field architecture handles version skew natively.
New fields are silently ignored by old clients.

**Velocity gains**: Experiments from 2+ weeks down to 1-2 days.

### 4.2 Netflix CLCS / UMA

**Scope**: Deliberately restricted to notifications and interstitials (payment
failures, promotions, lifecycle events). Netflix explicitly chose NOT to use SDUI for
their core browsing experience (the movie/show grid), recognizing that
performance-critical surfaces benefit from dedicated native implementation.

**Component model**: CLCS (Customer Lifecycle Component System) wraps their Hawkins
design system. UI primitives include stacks, buttons, input fields, text (with
typography tokens), images. Components are authored in JSX/TSX on the server:

```tsx
export function showBox(): Screen {
  return (
    <Modal>
      <VerticalStack>
        <Text typography='title' content='Come back next week' />
      </VerticalStack>
    </Modal>
  );
}
```

This generates a GraphQL/JSON payload that clients consume.

**Layout**: Nested stack-based composition. Vertical stacks, horizontal stacks,
responsive stacks that flip orientation based on screen space. Apps handle final
positioning and sizing decisions.

**Backward compatibility**: Three-layer strategy:
1. **GraphQL schema safety**: CI/CD blocks breaking schema changes
2. **Component fallbacks**: New components include fallback definitions built from
   baseline primitives
3. **Baseline components**: Minimum set guaranteed across all platform versions

The tell for client capabilities: each GraphQL request explicitly references supported
components via fragments. If a client doesn't request `FancyLabel`, the server falls
back to plain `Text`.

**State management**: Uses a pre-existing state machine for user lifecycle. Navigation
between interstitial screens routes through the state machine.

**Testing**: Three layers -- demo payloads for screenshot tests, backend snapshot
tests, and a headless client that traverses the component tree for validation.

### 4.3 DoorDash Facets

**Architecture**: Facets map 1:1 to views on screen. The data model is recursive
(tree-structured), which caused problems with GraphQL (no clean way to query arbitrary
depth). Solution: flatten the tree at the gateway layer, reconstruct on the client.

**Versioning**: Semantic versioning per component. Clients declare supported versions;
server adapts payloads.

**Edge cases DoorDash documented** (highly relevant for any SDUI system):
1. Container components receiving unrecognized children display empty containers
2. New component versions with different identifiers cause older apps to silently
   omit the view entirely
3. Components may render successfully but fail on interaction when action types
   aren't supported by the client

### 4.4 Delivery Hero (Fluid)

Template-based architecture with widget models and widget factories. Includes offline
caching and type-safe data binding. Forward/backward compatibility versioning.

### 4.5 Nubank (Backend Driven Content)

Instruction-based: backend sends rendering instructions rather than embedded layouts.
~70% of new screens run on their BDC system. Built on Flutter + Clojure.

### 4.6 Spotify HubFramework (DEPRECATED)

The cautionary tale. iOS-only component-driven UI framework, deprecated January 2019.
Failures:
- iOS-only scope eliminated cross-platform benefits (the main SDUI win)
- Abstraction didn't provide sufficient value for their use cases
- Network latency overhead for every UI change
- Documented in their talk "The Silver Bullet That Wasn't"

---

## 5. The SDUI Type System Spectrum

Looking across all these systems, there's a clear spectrum of how "typed" the
component vocabulary is:

```
Low-level primitives  <----->  Domain-specific sections
(Lyft Canvas)                  (Airbnb Ghost)
```

**Low-level** (Lyft, Netflix CLCS): Components are generic UI primitives -- stacks,
buttons, text, inputs. More flexible but requires more complex server-side composition.

**High-level** (Airbnb Ghost): Components are domain-specific -- `HeroSection`,
`TitleSection`, `PriceBreakdownSection`. Less flexible but more semantic, easier to
reason about, and better encapsulation of platform-specific rendering details.

Apollo GraphQL's documentation recommends a middle path using **interfaces and union
types**:

```graphql
interface UIComponent {
  id: ID
}

type UILogo implements UIComponent {
  id: ID
  url: String
  alt: String
}

type UIProductCard implements UIComponent {
  id: ID
  title: String
  price: String
  badge: UIBadge
}

type UISection {
  id: ID
  content: [UIComponent]  # Polymorphic composition
}
```

The `__typename` field becomes the component registry key on the client.

---

## 6. Key Tradeoffs and Criticisms

### What you gain
- Deployment velocity (bypass app stores)
- Cross-platform consistency (one source of truth)
- A/B testing at scale (server-side experiment assignment)
- No version fragmentation (server adapts to client capabilities)
- Forced design system discipline (clients must have a component catalog)

### What you lose
- **Performance**: SDUI payloads can be massive for complex screens. Caching is harder
  because the server determines layout. Partial loading states are harder because the
  client doesn't know the page structure until the response arrives.

- **Offline support**: If the UI is server-defined and you can't reach the server,
  what do you render? Netflix explicitly called this out as a fundamental tension.

- **Developer experience**: Frontend engineers lose understanding of the business data
  model. Debugging crosses the frontend/backend boundary. The action is "in the
  backend."

- **Tight coupling**: Despite the goal of decoupling, SDUI creates tight coupling
  between all clients and the backend schema. Pushing features requires coordination
  across teams around a shared schema.

- **The long tail**: SDUI works well for the 80% of UI that fits into known patterns.
  The remaining 20% -- custom animations, novel interactions, one-off screens -- either
  needs escape hatches or forces the component vocabulary to grow indefinitely.

- **Tooling burden**: Without robust mocking/preview infrastructure, developers cannot
  visualize changes without running the full backend. This is a significant dev-ex
  cost.

### The HN criticism worth internalizing

SDUI is philosophically a return to server-side rendering. The architecture resembles
HTML (server sends structure, client renders it) but with a proprietary schema instead
of a standard one. The question is whether the proprietary schema earns its complexity
over just using, well, HTML.

---

## 7. Relevance to Our Architecture

Our system has a different problem but overlapping concerns. We're building a design
system IR that multiple renderers consume. Here's where SDUI patterns map and where
they diverge.

### What maps directly

**Component registry pattern**: Ghost's `SectionComponentType` enum mapping to
platform-specific renderers is exactly our RendererConfig pattern. The IR names a
component type; the renderer knows how to produce it in its target platform.

**Sections as independent, pre-formatted units**: Ghost sections carry their own data,
already formatted. Our IR nodes should similarly be self-contained -- a renderer
shouldn't need to reach outside the node to understand what to produce (though our
renderer DOES walk the DB for visual properties, which is a different concern).

**Union/interface type system**: Ghost uses GraphQL unions (`Section = HeroSection |
TitleSection | ...`). Our component vocabulary is the same concept -- a finite set of
typed components that renderers must know how to handle.

**Layout as discrete types, not generic constraint systems**: Ghost doesn't send
CSS-like layout constraints. It picks from known layout types (`SingleColumnLayout`,
`MultiColumnLayout`) and the client renders them. This is closer to our pattern
vocabulary than to a generic layout engine.

**The pointer-based architecture**: Ghost responses reference sections by ID rather
than embedding them. Our IR references DB nodes by ID. Same principle: the description
layer points at data rather than duplicating it.

### What diverges

**Our IR is not a wire protocol**: Ghost's schema is a communication format between
server and client. Our IR is an intermediate representation between analysis phases
in a pipeline. We don't have the backward-compatibility / version-skew problem because
both producer and consumer are in the same process.

**We have the DB as ground truth**: Ghost sections carry ALL their data pre-formatted.
Our IR carries semantic classification + token references, and the renderer walks the
DB for visual details. Ghost doesn't have (or need) this two-layer data model.

**Our renderers are code generators, not UI frameworks**: Ghost clients are live
rendering engines interpreting a runtime payload. Our renderers produce static output
(Figma API calls, code). Different optimization pressures.

**We need to handle the "long tail" differently**: Ghost handles custom UI by adding
new section types to the vocabulary. We need to handle arbitrary Figma designs that
may not fit any vocabulary pattern. Our escape hatch is the DB scene graph (L0 in
our multi-level IR), not a growing enum.

### Design principles to steal

1. **Pre-format at the source**: Data flowing through the IR should be transformed
   as early as possible. Don't push formatting decisions downstream.

2. **Section independence**: Each IR node should be renderable without knowing its
   siblings. Context-coupling is a sign of leaky abstraction.

3. **The component type IS the contract**: Ghost's `SectionComponentType` is the API
   boundary between server and client. Our component vocabulary entries are the API
   boundary between analysis and rendering. Treat them with the same rigor.

4. **Discrete layout types over continuous constraints**: Don't try to build a generic
   layout solver. Identify the layout patterns that matter and make them first-class.

5. **Pointer-based, not embedded**: The IR should reference source data, not copy it.
   This is what our thin-IR / renderer-walks-DB design already does.

6. **The Netflix lesson -- scope deliberately**: Don't try to make everything
   server-driven (or IR-driven). Some screens/components should be handled with
   dedicated rendering paths. Hybrid is fine.

---

## Sources

- [A Deep Dive into Airbnb's Server-Driven UI System](https://medium.com/airbnb-engineering/a-deep-dive-into-airbnbs-server-driven-ui-system-842244c5f5) -- Ryan Brooks, Airbnb Tech Blog (primary reference)
- [Airbnb's Server-Driven UI Platform](https://www.infoq.com/news/2021/07/airbnb-server-driven-ui/) -- InfoQ
- [Server-Driven UI: What Airbnb, Netflix, and Lyft Learned](https://medium.com/@aubreyhaskett/server-driven-ui-what-airbnb-netflix-and-lyft-learned-building-dynamic-mobile-experiences-20e346265305) -- Aubrey Haskett
- [QCon London: Netflix Saves Time and Money with Server-Driven Notifications](https://www.infoq.com/news/2024/07/netflix-server-driven-ui/) -- InfoQ (Christopher Luu's talk)
- [Server-Driven UI for Mobile and Beyond](https://www.infoq.com/presentations/server-ui-mobile/) -- Christopher Luu, QCon London 2024
- [The Journey to Server-Driven UI at Lyft Bikes and Scooters](https://eng.lyft.com/the-journey-to-server-driven-ui-at-lyft-bikes-and-scooters-c19264a0378e) -- Alex Hartwell, Lyft Engineering
- [How Top Tech Companies Use Server-Driven UI to Move Faster](https://stac.dev/blogs/tech-companies-sdui) -- Stac
- [Apollo GraphQL SDUI Basics](https://www.apollographql.com/docs/graphos/schema-design/guides/sdui/basics)
- [Apollo GraphQL SDUI Schema Design](https://www.apollographql.com/docs/graphos/schema-design/guides/sdui/schema-design)
- [Apollo GraphQL SDUI Client Design](https://www.apollographql.com/docs/graphos/schema-design/guides/sdui/client-design)
- [Improving Development Velocity with Generic, Server-Driven UI Components](https://careersatdoordash.com/blog/improving-development-velocity-with-generic-server-driven-ui-components/) -- DoorDash
- [Using Display Modules to Enable Rapid UI Experimentation](https://careersatdoordash.com/blog/using-display-modules-to-enable-rapid-experimentation/) -- DoorDash
- [Spotify HubFramework (deprecated)](https://github.com/spotify/HubFramework) -- GitHub
- [Airbnb's Server-Driven UI System -- HN Discussion](https://news.ycombinator.com/item?id=27707423)
- [Server Driven UI: Streamlining Mobile Development and Release](https://www.infoq.com/presentations/sduie/) -- Tom Chao, QCon SF 2023
