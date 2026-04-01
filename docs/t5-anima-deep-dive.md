# Anima Deep Dive — How Automatic Component Detection Actually Works

Investigative research compiled 2026-03-31. Based on founder backgrounds, open source repos, technical blog analysis, job postings, secondary sources, and product evolution analysis.

---

## Summary

Anima's "Automatic Component Detection through Visual Analysis" is **not deep-learning computer vision on rendered screenshots.** It is a multi-pass heuristic system operating on the structured Figma node tree that:

1. Extracts and normalizes subtree structure of design groups/frames
2. Computes structural and visual-property similarity between subtrees
3. Clusters similar subtrees as instances of the same implicit "component"
4. Identifies property differences between instances as "variant" dimensions
5. Uses LLMs (OpenAI, Anthropic, Google APIs) for code generation, not for detection
6. Uses a local embedding model (in VS Code) for matching design components to code components

The "visual" in "Visual Analysis" refers to analyzing visual design PROPERTIES (colors, spacing, typography), not pixel-based image analysis.

---

## Founders

**Avishay Cohen (CEO)** — BSc Computer Science, Ben-Gurion University of the Negev, Israel.

Before Anima:
- **Consultant to CTO at Trax Image Recognition** — designed in-house mobile department, led AR research for mobile computer-vision solutions
- **VP of R&D at Mobli** — managed R&D on the **EyeIn project**, a real-time image search engine using machine learning, computer vision, and NLP to analyze and categorize crowdsourced visual media. Took EyeIn from POC to production.

**Critical insight**: The CEO has direct, hands-on experience building production CV and ML systems. He chose to build Anima's component detection on structured data heuristics, not pixel-level CV. That's a deliberate architectural decision from someone who knows both approaches.

**Or Arbel (CTO, now departed)** — BSc CS, Ben-Gurion. Founded Yo (viral messaging app). Now Co-Founder & CEO of Toffu AI. Left Anima by 2026.

**Michal Cohen (CPO)** — BSc Management/Economics from Ben-Gurion, Visual Communication from Shenkar College. Previously finance at Bank Leumi. Only designer at Anima until ~2020.

All three met at Ben-Gurion University. Company founded 2017, Y Combinator S18, $10M Series A (Sep 2021), IBM strategic investment (2026). 20-35 employees. Offices in NYC and Tel Aviv.

---

## No Published Research or Patents

- Zero academic papers by any founder (Google Scholar search)
- Zero patents or applications (USPTO search)
- IP is entirely trade-secret-based
- Deliberately opaque about implementation — blog posts describe the "what" while omitting the "how"

---

## What Their Blog Reveals

**Key admission**: Platform is based on "a mix of LLMs and heuristics" that the company developed.

**On model providers**: "Regularly evaluate AI models to ensure best-of-class code." Providers are "market leaders such as OpenAI, Anthropic, and Google." They do NOT train their own foundation models.

**On Auto-Flexbox (circa 2020)**: "We used algorithms from the Computer Vision world and built an automated solution that takes any design, and applies Flexbox layout to it." Note: "algorithms from the Computer Vision world" applied to structured coordinates, not pixels.

**On local processing (Frontier/VS Code)**: "Performs significant preprocessing locally and sends the LLM in the cloud only a small amount of code." Local ML models for codebase indexing. In-memory embedding database stored in workspace (`.anima/library.json`), committable to git.

**On visual diff engine**: "Intelligently tracks changes between design updates, reducing hallucinations, broken code, and misaligned layouts." No algorithmic details.

---

## Open Source Repos (github.com/AnimaApp)

15 repositories. Significant ones:

- **scooby** (143 stars) — UI regression and fidelity testing framework. Compares rendered code output against reference designs via screenshots. Does NOT reveal image comparison algorithms.
- **anima-sdk** (28 stars) — Public API SDK. Reveals architecture: SSE streaming, Figma REST API for file access, server-side processing.
- **Auto-Layout** (851 stars, archived) — Original Sketch responsive design plugin.
- **design-token-validator** (26 stars) — Validates design tokens.

**No ML/AI code, no training pipelines, no model weights, no CV algorithms published.** Core engine is entirely proprietary.

---

## Technical Reconstruction: How Component Detection Works

### The Multi-Layer Pipeline

**Layer 1: Design File Structural Analysis (Heuristics)**
Figma Plugin API reads full node tree — every frame, group, rectangle, text node with all properties. Structured data, not pixels.

**Layer 2: Subtree Similarity Detection (Tree-Based Pattern Matching)**
The "repeating UI patterns" detection is almost certainly subtree comparison — comparing structural subtrees to find groups of nodes with similar structure, similar properties, and similar spatial relationships. Analogous to code clone detection using AST comparison.

When they say "for a computer, this is a different story" they're talking about the combinatorial explosion of comparing every possible subtree against every other.

**Layer 3: Visual Property Clustering**
"Visual analysis" = comparing visual properties (colors, sizes, fonts, spacing, border radii) across similar structural groups. Two groups with same structure but different text content → instances of the same "component." Differences → "variants."

**Layer 4: Embedding-Based Code Matching (Local ML)**
For Frontier/VS Code: local embedding model indexes developer's existing codebase components. Component matching between design and code uses vector similarity (cosine distance on embeddings). The `.anima/library.json` contains this index.

**Layer 5: LLM-Based Code Refinement (Cloud)**
Compact representation (not full codebase) → commercial LLMs → code synthesis. Visual diff engine compares outputs to inputs for hallucination detection.

### Evidence That It's Structural, Not Deep CV

1. **No ML/CV hiring.** A company doing real-time CV on design files would need ML engineers. Current job listings show zero ML/AI roles.
2. **Figma Plugin API gives structured data.** Complete node tree with every property. Pixel analysis would be wasteful.
3. **CEO's CV background is relevant but applied differently.** Cohen's Trax/EyeIn experience informed spatial analysis algorithms but implementation operates on structured data.
4. **"Computer Vision" used loosely.** Auto-Flexbox post says "algorithms from the Computer Vision world" — spatial analysis algorithms (bounding box intersection, proximity, alignment) borrowed from CV literature but applied to structured coordinates.
5. **Local embedding database.** Component signatures are structural + visual property vectors, not raw image embeddings.

---

## Product Evolution (2017-2026)

| Phase | Period | Focus | Technology |
|-------|--------|-------|------------|
| 1 | 2017-2018 | Sketch plugins (Auto-Layout, Launchpad, Timeline) | Pure heuristic code generation |
| 2 | 2018-2020 | Multi-platform + Auto-Flexbox | CV-inspired algorithms for layout detection. Deterministic/heuristic. |
| 3 | 2020-2021 | **Automatic Component Detection** | Heuristic subtree similarity on Figma node trees |
| 4 | 2022-2023 | Design System Automation (DSA) | Storybook → Figma reverse direction. Open-sourced Scooby. |
| 5 | 2023-2024 | GenAI Integration (Frontier) | LLM-powered code gen on top of deterministic engine |
| 6 | 2025-2026 | API-First + Agentic | SDK/API, MCP server, playground. IBM investment. |

Key observation: component detection was built in Phase 3 (2020-2021) BEFORE they added any LLM capabilities in Phase 5 (2023-2024). It was always a structural heuristics system. LLMs were added later for code generation, not for component detection.

---

## Figma Plugin Interaction Model

- Uses **Figma Plugin API** (not REST API) for node tree access
- Full document structure, properties, styles, component definitions — no rendering needed
- For code generation: data flows to cloud servers via API. Client sends file key + node IDs → backend fetches via Figma REST API → processes → streams results via SSE
- For VS Code (Frontier): codebase analysis entirely local. Only minimal representation sent to cloud LLM.
- Enterprise: Zero Data Retention + Bring Your Own LLM options

---

## Relevance to Declarative Design

### What Anima Proves

1. **Heuristic structural analysis of Figma node trees IS viable for component detection.** A real company has built a business on this approach since 2020 without custom-trained vision models.

2. **Subtree similarity detection works.** Finding informal component patterns (groups of nodes that form a recognizable component but aren't formally declared as Figma components) is solvable with tree-based pattern matching.

3. **You don't need deep learning for the core classification.** Someone with deep CV/ML expertise (the CEO) chose structured heuristics. LLMs are used for code generation, not detection.

### What We Have That Anima Doesn't

1. **A classification target vocabulary.** Anima discovers components bottom-up (find similar subtrees, cluster them). We can also classify top-down (given a subtree, which of the 60 canonical types does it match?). Both directions reinforce each other.

2. **A token vocabulary.** Anima maps to code. We map to design tokens with actual Figma variable bindings. Richer, more structured output.

3. **The bidirectional compositional model.** Anima goes design → code (one direction). We need analysis → compositional representation → generation (both directions through the same model).

### What We Can Learn From Anima

1. **Start with the structured data.** The Figma Plugin API gives you everything. Don't reach for vision when you have the full node tree.

2. **Subtree similarity is the key algorithm.** Comparing structural subtrees to find recurring patterns. This is the hard engineering problem — handling varying child counts, property differences vs. type differences, nesting depth, decoration layers.

3. **Visual property clustering complements structural matching.** Two subtrees with same structure but different text → same component type. Use visual properties (colors, sizes, fonts, spacing) as secondary classification signal.

4. **Build the heuristic system first, add LLM/vision later.** Anima's component detection predates their LLM integration by 2+ years. The heuristic foundation must work before you layer intelligence on top.

5. **Embeddings for matching, not classification.** Anima uses embeddings to match design components to code components (similarity search), not to classify what a component IS. The classification is heuristic; the matching is embedding-based. These are different problems.

---

---

## Additional Findings: Anima Documentation Deep Dive (2026-04-01)

Read from: docs.animaapp.com/docs/anima-ai-agent-design-skill, anima-mcp, anima-api, features

### Design Skill Architecture

**"MCP is the kitchen tools. The skill is the recipe."** Their MCP server provides raw operations (fetch playground, generate code from Figma). The design skill provides the WORKFLOW — how to sequence operations, when to generate variants, how to iterate.

### Explore Mode: 3 Parallel Variants

"Three distinct design interpretations with different visual treatments at once." This maps directly to our Pattern Language Level 1 divergence (3 skeleton options). Anima independently arrived at the same branching exploration approach.

### Prompting Philosophy: Right Altitude

Skill explicitly discourages: "code snippets, hex colors, pixel values, font sizes, component library names." Wants: "purpose, audience, mood, key features, and tone." Same insight as Anthropic's frontend-design skill — compositional intent, not implementation details.

### Three Input Paths

- **Prompt-to-code (p2c)**: Natural language → fully designed application
- **Link-to-code (l2c)**: Clone a URL into editable playground
- **Figma-to-code (f2c)**: Figma designs → functional interactive environments

### SDK Settings Reveal Classification Output

The API supports mapping to UI libraries: `mui`, `antd`, `radix`, `shadcn`. This REQUIRES their pipeline to classify Figma elements into component types that map to each library's vocabulary. A Figma frame gets classified as a "Button" and then rendered as `<Button>` in MUI or `<button>` in shadcn.

This is exactly our classification problem — but their target is code component libraries, ours is the 60 canonical types feeding the Pattern Language. Their mapping: `Figma subtree → MUI Button`. Our mapping: `Figma subtree → canonical "Button" type with slot decomposition`.

### enableAutoSplit and autoSplitThreshold

API settings for their informal component detection. Splits generated code into components based on "complexity." Threshold is configurable, confirming it's a heuristic (not a fixed model output).

### SDK Configuration Options (Full List)

```
language: TypeScript | JavaScript
framework: React | HTML
styling: plain_css | css_modules | styled_components | tailwind | sass | scss | inline_styles
uiLibrary: mui | antd | radix | shadcn (React only)
enableAutoSplit: boolean (component complexity splitting)
autoSplitThreshold: number
enableCompactStructure: boolean
responsivePages: array of frame IDs (breakpoint overrides)
```

### Server-Side Processing

SDK explicitly designed to run on backend only. Actual codegen engine is entirely server-side. No client-side processing of design classification. API is currently gated ("To get access, contact us").

### Relevance to Our Architecture

1. The explore mode (3 parallel variants) validates our Pattern Language divergence approach
2. The UI library mapping confirms they solve the classification-to-vocabulary problem we need
3. The right-altitude prompting aligns with our Level 0-1 abstraction approach
4. Their `enableAutoSplit` heuristic is a simpler version of our subtree similarity detection

---

## Sources

- Anima About: https://www.animaapp.com/about
- Y Combinator: https://www.ycombinator.com/companies/anima-app
- TechCrunch 2018: https://techcrunch.com/2018/07/02/anima-design/
- CTech Series A: https://www.calcalistech.com/ctech/articles/0,7340,L-3916884,00.html
- CTech IBM: https://www.calcalistech.com/ctechnews/article/hkm511mmdbe
- Frontier blog: https://www.animaapp.com/blog/genai/introducing-frontier-the-future-of-front-end-by-anima/
- GenAI intro: https://www.animaapp.com/blog/industry/introducing-generative-ai-in-design-to-code-at-anima/
- Auto-Flexbox: https://medium.com/sketch-app-sources/introducing-auto-flexbox-aaa4fc553cc0
- Component detection: https://www.animaapp.com/blog/product-updates/announcing-automatic-component-detection-in-anima/
- Scooby: https://github.com/AnimaApp/scooby
- Anima SDK: https://github.com/AnimaApp/anima-sdk
- Jobs: https://jobs.ashbyhq.com/anima
