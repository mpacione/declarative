# T5 Conjure — Research & Architecture Discussion

Captured from conversation starting at "Dope! ok i think nows the time to move on to T5... lets discuss"

---

## Context

T1–T4.6 complete. DB has 388 tokens, 182,871 bound nodes, extended properties (22 new columns), and a full round-trip push/rebind pipeline. The question: what should T5 look like, and how do we architect it to be extensible?

---

## T5 Taxonomy Reorganization

The original T5 was a flat list of 9 actions. Reorganized into 3 groups across 14 actions:

**Group A: Transform** (modify existing nodes)
- T5.1 Systematic Refactor — rebind all nodes from old token to new
- T5.2 Theme Application — apply design system to unstyled wireframe
- T5.3 Generate Variant States — add hover/focus/disabled states
- T5.4 Layout Reflow — change layout direction/sizing on existing frame
- T5.5 Component Instance Override — swap properties across all instances

**Group B: Compose** (create new nodes)
- T5.6 Duplicate Screen With Modifications
- T5.7 Design System Documentation Page
- T5.8 Compose Component From Prompt
- T5.9 Compose Screen From Prompt ← core value proposition
- T5.10 Responsive Adaptation
- T5.11 Flow / Multi-Screen Generation

**Group C: Intelligence** (analyze and infer)
- T5.12 Pattern Extraction → Template (stores to `patterns` table, no Figma required)
- T5.13 Pattern Extraction → Component (creates Figma component, replaces instances)
- T5.14 Screenshot to System-Native (external image → match tokens → compose)

---

## Architectural Approach: #2 — DB Template → CLI Code Generation

Chosen approach: `patterns` table stores IR (slot structure + token slot references + layout constraints). CLI generates MCP action batch. Agent executes. Figma-native output with actual variable bindings.

**Rationale:**
- DB is the single source of truth — generation is constrained, not probabilistic
- Token slots are references to live DB vocabulary, not hardcoded values
- Composable: retrieval step is swappable (SQL now, semantic later)
- The variable binding guarantee is the differentiator — no other tool does this

---

## Research Agent 1: design.md + Google Stitch

### design.md
- A human-readable, agent-friendly markdown file (20-40 lines) capturing colors, typography, spacing, component patterns
- Created by Google as part of Stitch; gaining adoption across Claude Code, Copilot, Cursor, Aider
- LLMs understand markdown structure reliably — headings = hierarchy, bullets = enumeration
- **Critical limitation**: read probabilistically, not deterministically. Guides the model but doesn't guarantee compliance
- Complementary format: `designtoken.md` — more structured, 150+ lines, full color scales with light/dark modes

### Google Stitch
- Google Labs tool (launched Google I/O May 2025) built on Gemini 2.5 Flash/Pro
- Inputs: text prompts, wireframe sketches, screenshots (multimodal)
- Outputs: responsive HTML/CSS + visual designs
- Includes "Vibe mode" — captures aesthetic direction from visual references
- Can extract a design system from any URL → produces DESIGN.md
- Designs can be pasted into Figma or exported as HTML/CSS
- Google Stitch SDK + MCP server available for programmatic access

**Critical failures (community feedback):**
- Cannot enforce component library, design tokens, or brand guidelines consistently
- Colors drift from brand systems
- Complex flows require significant human intervention
- Every generation "starts somewhat fresh" — no cross-session enforcement
- **This is exactly the gap Declarative Design fills**: token-enforced, Figma-native generation

**Relevance to Declarative Design:**
- DESIGN.md is a portable design context file — we could export one from the DB (export format)
- Stitch's "extract from URL" → structured rules is essentially what `dd extract` does from Figma
- Their probabilistic enforcement vs. our deterministic enforcement is the key architectural differentiator

---

## Research Agent 2: Screenshot Corpus + Taste Encoding

### Design Taste Extraction Tools
- **Taste** (buildwithtaste.com): GPT Vision reads screenshots → extracts design tokens → synthesizes qualitative design sensibility descriptions → auto-exports to AI assistants
- **Uizard, Banani, Visily**: Various commercial tools for style extraction from screenshots
- None produce token-constrained, Figma-native output

### Academic Corpora
| Dataset | Size | What's included |
|---------|------|-----------------|
| RICO | 66k+ screens | Screenshots, Android view hierarchies, interaction traces, 64-dim layout embeddings |
| Enrico | 1,460 screens | Human-curated, 20 design topics, semantic wireframes |
| WebUI | 400k+ web pages | Screenshots + semantic annotations from browser engine metadata |
| MobileViews | 600k+ | Screenshot-VH pairs, 20k+ modern mobile apps |

**Mobbin** (400k+ screenshots, curated real apps) is the closest to what Matt described. They launched visual search in 2025 — upload screenshot, find visually similar screens. Same basic RAG idea.

### Embedding Models for UI
- **Screen2Vec** (CHI 2021): Self-supervised, layout-aware. UI2Vec (element) → Screen2Vec (screen). Uses text content + visual design + layout + app metadata.
- **GUIClip**: ViT-B/32 CLIP fine-tuned on UI datasets. Recall@10 ≈ 0.69. Powers GUing mobile GUI search engine.
- **UIClip**: Assesses UI design quality, incorporates CRAP principles (contrast, repetition, alignment, proximity).
- **ScreenAI** (Google, 5B params): PaLI architecture, trained on 400M+ samples. State-of-the-art on UI understanding tasks.

### The Metadata Problem
Raw screenshots alone are insufficient. Useful representation requires:
- Element segmentation (bounding boxes + component types)
- Semantic labeling (NavBar, Card, CTA, etc.)
- Layout hierarchy
- OCR text
- Token value matches (observed color/type/spacing → nearest vocabulary token)

**This pipeline doesn't exist turn-key for arbitrary app screenshots.** It requires running a vision model (ScreenAI / GPT-4V) over each screenshot to produce structured records.

### Segmentation + Semantic Annotation
- **UIBert**: Transformer trained on 537k screenshot-view hierarchy pairs. 5 pre-training tasks including UI object detection.
- **UI-DETR**: Identifies 98 UI element types
- **pix2code**: CNN + LSTM, 77% accuracy, screenshot → DSL code
- **DesignPref** (2024): Captures per-designer aesthetic preferences via 12k pairwise comparisons + VAE + meta-learning. Supports domain transfer.

---

## Research Agent 3: Net-New Design Generation

### Layout Generation Models
- **LayoutDiffusion** (ICCV 2023): Discrete denoising diffusion on RICO/PubLayNet. Outperforms prior SOTA.
- **LayoutGPT** (NeurIPS 2023): LLM as visual planner via CSS-style prompts + in-context visual demos. Outperforms other methods by 20-40% on spatial reasoning when combined with region-controlled image generation.
- **Towards Aligned Layout Generation with Aesthetic Constraints** (ICLR 2024): Enforces aesthetic constraints *during* generation, not just as input.

### How Style Constraints Are Enforced (State of the Art)
1. **Design token integration** — every visual property resolves to a token value (guarantees correctness at the binding level)
2. **Structured specification** — YAML/JSON token + component definitions as system-level context
3. **Constrained decoding** — limits LLM next-token predictions to valid output tokens
4. **Automated auditing** — post-generation validation catches every violation
5. **CSS-style prompts** — LayoutGPT's approach: render design spec directly into context as CSS

### The Gap Nobody Has Solved
Generating Figma nodes with actual variable bindings, constrained to a specific token vocabulary.

- Builder.io Visual Copilot is closest — component-library-aware code generation — but outputs HTML/CSS/React, not Figma-native
- Ugic AI generates Figma designs from component libraries but no variable binding
- Stitch generates visual + HTML, no token system enforcement

**This is Declarative Design's T5 territory.**

### End-to-End Pipeline References
- **PSD2Code** (2025): ParseAlignGenerate — extract hierarchy + layer properties from PSD → constraint-based alignment → generate React+SCSS. Strong model independence.
- **Design2Code** benchmark: Evaluates MLLMs on design-to-code across visual fidelity + code correctness
- **Interaction2Code** (2024): First benchmark for interactive webpage generation. Key finding: visual-only descriptions insufficient, interaction semantics require multimodal understanding.

### Context Window for Generation
Research shows context composition matters. For constrained design generation, the window needs:
1. Query / user intent
2. Retrieved similar patterns (structural + visual)
3. Token definitions (semantic meanings + resolved values)
4. Component vocabulary (available components, variants)
5. Layout/constraint rules (grammar for valid compositions)
6. Structural rules / taste guidelines

---

## Visual RAG Thesis (Shared by Matt)

Proposed pipeline:
1. Curated screenshot corpus → structural decomposition (component tree + layout graph + tokens)
2. ColPali multi-vector embeddings (late interaction, token-level visual retrieval)
3. Retrieval at query time → structured output specification
4. LLM generates constrained composition from specification

**Key insight from discussion**: The Declarative Design DB *already is* the structural decomposition layer for screens that have been extracted. The `nodes` table + `node_token_bindings` + `tokens` gives richer structure than what ColPali would infer from pixels.

**Where ColPali/visual RAG adds value**: T5.14 (Screenshot to System-Native), where the input is an *external* screenshot that hasn't been extracted. For that case, you need to bridge from pixel space to token space, and visual embeddings are the right tool.

**Where SQL is sufficient**: T5.9 (Compose Screen From Prompt) — "settings page" → find patterns with `list-item`, `toggle`, `section-header` component types → SQL query against patterns/component catalog.

---

## Architecture Synthesis

### Two-Layer Model

**Layer 1 — DB Template (IR, no Figma required)**
- `patterns` table: slot structure + token slot references + layout constraints
- Populated by T5.12 (pattern extraction from existing screens) or manually
- Slot model influenced by SDUI sections/placements pattern (Airbnb)

**Layer 2 — Code Generation (CLI + MCP execution)**
- `dd compose <pattern-name> [--mode dark] [--screen-name ...]`
- CLI resolves token slots against live tokens → generates MCP action batch
- Agent executes via `figma_execute` / PROXY_EXECUTE
- Result written back to DB

### Generate → Critique → Refine Loop

```
Generate → Screenshot → Critique → Refine → Screenshot → Critique → Accept
```

**Four levels of critique, ordered by cost:**

| Level | Input | Cost | Type |
|-------|-------|------|------|
| L1 System | DB queries | Cheap | Deterministic |
| L4 Accessibility | Token values → WCAG computation | Cheap | Deterministic |
| L2 Structural | Node tree + design principles | Moderate | LLM |
| L3 Visual | Screenshot + vision model | Expensive | LLM |

**L1 and L4 run first (parallel). L2 next. L3 only if others pass.**

**Structured critique output** (not freeform):
```json
{
  "pass": false,
  "issues": [
    {
      "severity": "high",
      "category": "hierarchy",
      "description": "Primary CTA same weight as secondary action",
      "affected_nodes": ["button-primary-1"],
      "suggested_fix": "Increase font weight or bind to type.label.lg"
    }
  ]
}
```

`affected_nodes` referencing DB IDs → generation agent makes targeted fixes, not full regeneration.

### Corpus as Future Enhancement Layer

The corpus doesn't change the loop — it enriches the retrieval step:

- **Now**: "Generate a settings screen using patterns extracted from this Figma file"
- **Later**: "Here are 3 real settings screens from top-quality apps [corpus retrieval]. Generate using those as structural reference, constrained to this file's token vocabulary"
- **In critique**: "Here is a reference screen with good visual hierarchy [corpus]. Compare and identify gaps"

Corpus = taste calibration layer, not a prerequisite. Build the full loop now, slot corpus in later.

### Sequencing

```
T5.12 (pattern extraction) → T5.1/T5.2 (transform, prove rebinding works)
→ T5.9 (compose screen, first full loop) + critique agents
→ T5.14 (screenshot to system-native, where visual RAG earns its keep)
→ corpus pipeline (screenshot → segment → embed → retrieve)
```

---

## Open Questions (Tabled for Later)

1. **Taste vs. Structure from corpus**: Aesthetic encoding ("feel like Linear") vs. structural pattern retrieval ("settings screen layout from real apps") require different pipelines. Which is the priority?

2. **Corpus curation fidelity**: Manual curation + light annotation vs. fully automated pipeline? Automated segmentation/labeling is ~80% accurate — is that sufficient?

3. **External corpus vs. per-file patterns**: Does the corpus inform a global taste layer, or is it always resolved against the specific file's token vocabulary?

4. **Generation target**: Figma-native (hard, novel, differentiator) vs. HTML/code output (easier, closer to existing tools). Figma-native is the moat.

5. **External design system seeding**: Radix/shadcn/Material (structured, available) vs. scraping real app screenshots vs. ingesting components from user's other Figma files — different extraction challenges.

6. **Critique iteration budget**: 3 rounds? 5? Until all critics pass? Need a ceiling to avoid loops.

7. **Visual critique taste calibration**: Generic design principles (CRAP, Gestalt, WCAG) vs. user-written taste rules (a DESIGN.md analog for the critique prompt). User-written rules possible even without corpus.
