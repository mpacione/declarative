# Bidirectional UI Models — Research Survey

Research on systems that share a single compositional model for both analyzing existing UI and generating new UI. Covers intermediate representations, pattern extraction, constrained generation, slot models, and cross-screen consistency.

Conducted 2026-03-31. Focused on 2023--2026 work from arxiv, CHI, UIST, and industry.

---

## 1. Bidirectional / Invertible UI Models

### 1.1 Figma MCP: The First Production Round-Trip System

The most concrete bidirectional system shipping today is the **Figma MCP Server** (Dev Mode MCP, open beta as of March 2026). It provides two directions through a shared protocol:

- **Design-to-code** (`get_design_context`): extracts structured design data — component trees, auto-layout properties, token bindings — from Figma files.
- **Code-to-design** (`generate_figma_design`): parses JSX AST, infers layout constraints (Flexbox direction, padding values), and generates Figma frames with matching auto-layout, component instances, and text.

The shared representation is effectively JSX AST ↔ Figma node tree, mediated by the MCP server. Figma announced bidirectional integration with Claude Code (February 2026) and OpenAI Codex (nine days later), both running through the same MCP server.

**Key limitation**: The round-trip is lossy. JSX → Figma → JSX does not produce identical code. The representations are structurally similar but not formally invertible.

Sources:
- [Figma Blog: Claude Code to Figma](https://www.figma.com/blog/introducing-claude-code-to-figma/)
- [GitHub Copilot Figma Bidirectional Sync](https://blockchain.news/news/github-copilot-figma-mcp-bidirectional-sync)
- [Figma MCP Server turns design and code into a two-way street](https://www.everydev.ai/p/blog-the-figma-mcp-server-turns-design-and-code-into-a-twoway-street)

### 1.2 UXPin Merge: Code IS the Design Artifact

UXPin Merge takes a different approach: there is no separate design representation. Designers work with actual React components imported from the codebase. The component IS both the design artifact and the code artifact — no translation needed.

This is "bidirectional by elimination" — there's only one representation. The tradeoff: designers must work within the constraints of existing code components. There's no design-first exploration.

Sources:
- [UXPin Merge](https://www.uxpin.com/merge)
- [UXPin Code-to-Design Guide 2025](https://www.uxpin.com/studio/blog/code-to-design-guide/)

### 1.3 Figma Code Connect: Bridging Without Merging

Figma's Code Connect maps Figma components to code components through explicit annotations rather than structural equivalence. It creates a "bridge" layer where designers maintain Figma components and developers maintain code components, with Code Connect maintaining the mapping between them.

This is a weaker form of bidirectionality — the mapping is manually maintained and doesn't support automatic round-tripping — but it's the most pragmatic approach in wide production use today.

Source:
- [Code Connect – Figma Help Center](https://help.figma.com/hc/en-us/articles/23920389749655-Code-Connect)

### 1.4 Bidirectional Transformations (BX) from PL Theory

The programming languages community has a formal theory of bidirectional transformations through **lenses**. A lens is a pair of functions — `get` (forward) and `put` (backward) — satisfying round-trip laws (GetPut, PutGet). Lens synthesis research has produced algorithms to automatically derive bijective lenses from type specifications.

No one has applied lens theory to UI transformations specifically, but the theoretical framework exists. A "UI lens" would be: `get: DesignTree → ComponentTree` and `put: (DesignTree, ComponentTree) → DesignTree`, where modifying the ComponentTree and running `put` updates the design consistently.

Sources:
- [Bidirectional transformation (Wikipedia)](https://en.wikipedia.org/wiki/Bidirectional_transformation)
- [Synthesizing Bijective Lenses (arxiv 1710.03248)](https://arxiv.org/pdf/1710.03248)
- [KBX: Verified Model Synchronization via Formal Bidirectional Transformation (2024)](https://arxiv.org/pdf/2404.18771)

---

## 2. Intermediate Representations for UI Composition

### 2.1 SpecifyUI: SPEC as Shared Semantic Layer (2025)

SpecifyUI introduces **SPEC Embedding** — a vision-centered intermediate representation that makes design intent explicit and controllable. Users extract specifications identifying Region, Style, and Layout, composing them into a structured IR. SPEC serves as a "shared language" between human intent and AI output, sitting between the ambiguity of natural language and the rigidity of code.

This is the closest academic work to a shared IR for analysis AND generation: the same SPEC representation is used to (a) extract specifications from existing designs and (b) guide generation of new designs.

Source:
- [SpecifyUI (arxiv 2509.07334)](https://arxiv.org/html/2509.07334v1)

### 2.2 Bridging Gulfs: Bidirectional Semantic Framework (2026)

"Bridging Gulfs in UI Generation through Semantic Guidance" derives a semantic framework that structures hierarchical, interdependent design information. It provides an intermediate layer that:
- **Parses** user intent into structured semantics (analysis direction)
- **Extracts** how semantics are realized in generated outputs (generation direction)

This is explicitly bidirectional — the same semantic structure connects specification and evaluation. The framework is hierarchical and interdependent, not flat.

Source:
- [Bridging Gulfs in UI Generation (arxiv 2601.19171)](https://arxiv.org/abs/2601.19171)

### 2.3 UI Grammar: Context-Free Grammar for UI Trees (2023--2024)

Lu & Tong define **UI Grammar** as a set of production rules for parent-child relationships in UI screen hierarchies. Each rule has the form `A → B` where A is a parent element type and B is a sequence of child element types — resembling context-free grammar.

This is used for generation (constraining LLM output to valid UI trees), but the same grammar could be used for analysis (parsing an existing UI tree into its grammatical derivation). The grammar captures compositional structure, not just visual properties.

Sources:
- [UI Layout Generation with LLMs Guided by UI Grammar (arxiv 2310.15455)](https://arxiv.org/abs/2310.15455)
- [Semantic Scholar PDF](https://www.semanticscholar.org/paper/UI-Layout-Generation-with-LLMs-Guided-by-UI-Grammar-Lu-Tong/5c6e22b8ed1c4cf224f19c3c14560a9a8a12ea6a)

### 2.4 SDUI Schemas: Airbnb Ghost Platform

Airbnb's Ghost Platform uses a single, shared GraphQL schema for Web, iOS, and Android. The schema defines three primitives:
- **Sections**: independent groups of related UI components
- **Screens**: define where and how sections appear
- **Actions**: handle user interaction

A `SectionComponentType` enum enables different visual renderings from the same data model. Everything — layout, section arrangement, data, and actions — is controlled by a single backend response.

This is a production-grade compositional IR, but it's generation-only. The schema drives rendering; it doesn't support analyzing an existing screen back into the schema representation.

Sources:
- [Airbnb Engineering: Deep Dive into SDUI](https://medium.com/airbnb-engineering/a-deep-dive-into-airbnbs-server-driven-ui-system-842244c5f5)
- [InfoQ: Airbnb SDUI Platform](https://www.infoq.com/news/2021/07/airbnb-server-driven-ui/)

### 2.5 A2UI: Google's Agent-to-UI Protocol (2025)

Google's A2UI (released December 2025) is a streaming protocol for agent-driven UIs. The critical design decision: **the client maintains a catalog of trusted, pre-approved components**, and the agent can only request components from that catalog.

Message types: `createSurface` (new rendering context), `updateComponents` (component definitions), `updateDataModel` (data injection). The protocol is declarative data, not executable code.

A2UI is generation-only (agent → UI), but the catalog constraint is directly relevant to bidirectional models: if you analyze an existing UI, you would decompose it into the same catalog components.

Sources:
- [Google Developers Blog: Introducing A2UI](https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/)
- [A2UI Specification v0.9](https://a2ui.org/specification/v0.9-a2ui/)
- [GitHub: google/A2UI](https://github.com/google/A2UI/)

### 2.6 Vercel json-render (2026)

Vercel's json-render framework (open-sourced January 2026, 13k+ stars) takes the catalog-constrained approach further. Developers define a catalog of permitted components using **Zod schemas**. An LLM generates a JSON spec constrained to that catalog. The framework renders the spec progressively as the model streams.

The key insight: the Zod schema serves as both the generation constraint and the validation/analysis schema. You could parse an existing UI back into the same JSON spec and validate it against the catalog.

Ships with 36 pre-built shadcn/ui components plus renderers for React, Vue, Svelte, Solid, and React Native.

Sources:
- [InfoQ: Vercel Releases JSON-Render](https://www.infoq.com/news/2026/03/vercel-json-render/)
- [GitHub: vercel-labs/json-render](https://github.com/vercel-labs/json-render)
- [json-render.dev](https://json-render.dev/)

---

## 3. Pattern Extraction from UI Trees

### 3.1 UI Semantic Group Detection (2024)

UISCGD detects semantic component groups — adjacent text and non-text elements with similar semantics that form perceptual groups. Built on deformable-DETR with UI element color representation and learned priors on group distribution.

Applications: retrieving perceptual groups, improving code structure in UI-to-code generation, generating accessibility data. Published March 2024.

Source:
- [UI Semantic Group Detection (arxiv 2403.04984)](https://arxiv.org/abs/2403.04984)

### 3.2 UISearch: Graph-Based UI Embeddings (2025)

UISearch converts UI screenshots into **attributed graphs** encoding hierarchical relationships and spatial arrangements. A contrastive graph autoencoder learns embeddings preserving multi-level similarity across visual, structural, and semantic properties.

Key finding: structural embeddings achieve better discriminative power than state-of-the-art vision encoders. This means the component tree structure is more useful for finding similar UIs than pixel similarity.

Performance: 0.92 Top-5 accuracy on 20,396 financial software UIs with 47.5ms median latency. Supports composable queries combining visual similarity, structural patterns, semantic intent, and metadata constraints.

Source:
- [UISearch (arxiv 2511.19380)](https://arxiv.org/abs/2511.19380)

### 3.3 RICO Bag-of-Components and Topic Modeling

The RICO dataset (66k+ mobile UI screens with view hierarchies) enables a "bag-of-components" representation analogous to bag-of-words. Using JSON view hierarchies with componentLabel, iconClass, text, bounds, and clickable fields, researchers extract semantic feature vectors per screen and cluster them (MiniBatch K-Means, K=20) into interpretable design topics.

This is essentially design-system inference: discovering that many screens share similar compositional patterns and grouping them.

Sources:
- [RICO Dataset](https://interactionmining.org/rico)
- [AI-Driven Mobile UI Pattern Recognition on RICO (2024)](https://www.researchgate.net/publication/401214634_AI-Driven_Mobile_UI_Pattern_Recognition_and_Design_Topic_Mining_on_RICO_Semantic_Clustering_and_Screenshot-Based_Topic_Classification)

### 3.4 DesignCoder: Hierarchy-Aware Decomposition (2025)

DesignCoder introduces **UI Grouping Chains** to enhance MLLMs' understanding of nested UI hierarchies. It uses a hierarchical divide-and-conquer approach: decompose a complex UI into hierarchical groups, generate code for each group, then compose.

This is analysis (decomposition into hierarchy) followed by generation (code per group), sharing a hierarchical representation. Results: 37.6% improvement in MSE, 30.2% improvement in TreeBLEU over baselines.

Source:
- [DesignCoder (arxiv 2506.13663)](https://arxiv.org/abs/2506.13663)

---

## 4. Compositional Generation from Patterns

### 4.1 Catalog-Constrained Generation (A2UI, json-render)

The dominant pattern emerging in 2025--2026 is **catalog-constrained generation**: define a finite set of allowed components, let the LLM compose from that catalog only. This guarantees:
- Output uses only known components and tokens
- Output is structurally valid (conforms to component schemas)
- Output can be validated/analyzed using the same schemas

A2UI (Google), json-render (Vercel), and Open-JSON-UI (OpenAI) all follow this pattern. The constraint is typically expressed as Zod schemas (json-render) or JSON Schema (A2UI).

### 4.2 Grammar-Based Generation

UI Grammar (Section 2.3) enables grammar-based generation where LLMs produce derivations from production rules rather than raw HTML/JSX. This is analogous to grammar-constrained decoding in NLP (XGrammar, etc.) applied to UI structure.

The grammar constrains the LLM to produce valid component trees. The same grammar can parse existing UIs into derivation trees.

### 4.3 Template-Based Generation with Hierarchical Specs

SpecifyUI (Section 2.1) enables template-based generation: extract specifications from reference designs (Region, Style, Layout), compose them into a SPEC, then use the SPEC to guide generation of new designs. Users can combine elements from multiple references hierarchically.

This is the closest to "fill slots in a known pattern" — the SPEC defines the compositional skeleton, and the generator fills in the details.

### 4.4 SDUI Screen Composition

Airbnb Ghost Platform composes screens from sections: the backend selects which sections to include, specifies their order and layout, and the client renders them. This is template-based composition at the screen level — the "template" is the screen layout, the "slots" are section positions.

Netflix extends this to experiments: different users see different section arrangements, all composed from the same section catalog.

---

## 5. The Slot Model

### 5.1 Web Components Slots (W3C Standard)

The W3C `<slot>` element is the canonical slot model. Named slots (`<slot name="header">`) define insertion points in Shadow DOM templates. Content is distributed to slots by matching `slot="header"` attributes. The W3C Web Components Community Group (2024) is working on CSS extensions for styling based on slotted state.

### 5.2 React Slot Patterns

React implements slots through several mechanisms:

- **children prop**: The simplest slot — one unnamed insertion point
- **Named props as slots**: `header={<Header />}` `footer={<Footer />}`
- **Render props**: Slots that receive data — `renderItem={(item) => <Card data={item} />}`
- **Compound components**: Multiple slots coordinated through context

### 5.3 Radix UI asChild/Slot: Composition by Delegation

Radix UI's `Slot` component and `asChild` prop implement a sophisticated slot model where the component merges its props (including behavior and accessibility attributes) onto its immediate child using `React.cloneElement`. When `asChild` is true, Radix doesn't render a default DOM element — it delegates rendering to the child while providing behavior.

This pattern can be nested arbitrarily deep, enabling composition of multiple primitive behaviors. It's the most production-relevant formal-ish treatment of slots in the React ecosystem.

Sources:
- [Radix Composition Guide](https://www.radix-ui.com/primitives/docs/guides/composition)
- [Radix Slot Utility](https://www.radix-ui.com/primitives/docs/utilities/slot)
- [Unpacking the Slot Component](https://www.yisukim.com/en/posts/unpacking-the-slot-component)

### 5.4 Design Tool Variants as Slot Configurations

In Figma, component variants are effectively slot configurations — a component set defines which properties (slots) are configurable and what values (content) each slot accepts. The variant matrix is a product space of slot values.

Figma's component properties (BOOLEAN, TEXT, INSTANCE_SWAP, VARIANT) map to typed slots:
- BOOLEAN → visibility slot (show/hide)
- TEXT → text content slot
- INSTANCE_SWAP → component slot (swap child component)
- VARIANT → configuration slot (select from enumerated options)

This is the closest design-tool equivalent to typed slots.

---

## 6. Cross-Screen Consistency

### 6.1 UISearch: Structural Similarity Across Screens

UISearch (Section 3.2) directly addresses cross-screen consistency by computing structural similarity between screens using graph embeddings. Two screens that use "the same type of card" would have similar subgraph structures even if they differ in content or minor styling.

The composable query language supports queries like "find all screens with a structure similar to this card pattern" — exactly the kind of cross-screen component vocabulary detection needed.

### 6.2 RICO Topic Clusters as Implicit Design Systems

The RICO bag-of-components clustering (Section 3.3) discovers implicit design systems: screens that share similar compositional patterns cluster together. The clusters represent shared component vocabularies — the same types of components arranged in similar ways.

This is design system inference: given a set of screens, extract the underlying compositional vocabulary they share.

### 6.3 Deep Learning for Cross-Platform UI Component Detection

Recent work (2024--2025) evaluates cross-domain generalization of object detectors (YOLOv8, YOLOv9, Faster R-CNN) trained on UI components across web, desktop, and mobile. YOLOv9 achieves up to 95.5% mAP when adapting from desktop to web. This enables detecting "the same kind of button" across platforms, not just across screens.

Source:
- [Evaluating Deep Learning Models for Cross-Platform UI Component Detection (ScienceDirect 2025)](https://www.sciencedirect.com/science/article/pii/S1877050925030959)

---

## 7. Synthesis: What a Bidirectional Compositional Model Needs

Based on this survey, a system that can both analyze and generate UI using the same representation needs:

### 7.1 A Component Catalog with Typed Slots

Every system that works well (A2UI, json-render, Airbnb Ghost, Figma variants) centers on a **finite, typed component catalog**. Each component has:
- A type identifier (what kind of component)
- Typed slots/properties (what can be configured)
- Composition rules (what can contain what)

The catalog serves as both the generation constraint and the analysis vocabulary.

### 7.2 A Hierarchical Composition Grammar

UI Grammar (Section 2.3) and DesignCoder (Section 3.4) show that component trees need **production rules** governing parent-child relationships. A grammar enables:
- **Generation**: produce valid trees by following rules
- **Analysis**: parse existing trees into derivations
- **Validation**: check whether a tree conforms to the grammar

### 7.3 Structural Similarity via Graph Embeddings

UISearch (Section 3.2) demonstrates that graph-based representations of component trees enable finding structurally similar compositions across screens. This is essential for:
- Detecting reuse of the same compositional pattern
- Maintaining a shared vocabulary across a project
- Inferring design systems from existing designs

### 7.4 Slot-Based Composition as the Unifying Primitive

The slot model (named insertion points with typed constraints) appears at every level:
- Web Components: `<slot name="...">`
- React: children, named props, render props
- Figma: component properties (BOOLEAN, TEXT, INSTANCE_SWAP, VARIANT)
- SDUI: sections within screen layouts
- A2UI/json-render: component props defined by schemas

A bidirectional model should represent all composition as slot-filling: analysis decomposes a UI into components with filled slots, generation fills empty slots with content.

### 7.5 The Missing Piece: Formal Round-Trip Guarantees

No existing system provides formal round-trip guarantees (analyze → modify → regenerate = predictable result). The lens theory from PL research (Section 1.4) provides the theoretical framework, but no one has instantiated it for UI transformations.

The practical systems (Figma MCP, UXPin Merge) achieve approximate bidirectionality through pragmatic engineering rather than formal guarantees.

---

## 8. Relevance to Declarative Build T5

For T5 Conjure (Compose and Analyze groups), this research suggests:

1. **The component catalog is the shared model.** The DB's token vocabulary (388 tokens, 22 extended property columns) already serves as a component catalog with typed properties. T5 should leverage this for both analysis (decompose existing designs into token-bound components) and generation (compose new designs from the same tokens).

2. **Grammar-based composition rules.** Define production rules like `Screen → Header, Content, Footer` and `Content → Card*` using the existing component vocabulary. Use these rules to both validate existing designs and constrain generation.

3. **Slot-filling as the generation primitive.** T5.8 (Compose Component) and T5.9 (Compose Screen) should work by selecting a compositional template (a tree skeleton with typed slots) and filling slots with appropriate token-bound values.

4. **Structural similarity for pattern reuse.** T5.6 (Duplicate Screen With Modifications) and T5.11 (Flow/Multi-Screen) need to detect structurally similar subtrees across screens. Graph-based embeddings (UISearch approach) over the Figma node tree would enable this.

5. **The json-render / A2UI pattern fits well.** Define component schemas (Zod-like), constrain generation to those schemas, validate output against the same schemas. The existing DB schema could serve as the Zod catalog.
