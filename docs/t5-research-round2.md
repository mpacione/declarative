# T5 Research Round 2 — Design Encoding, Critique Loops, Efficiency

Compiled 2026-03-31 from 4 parallel research agents. This document captures ALL findings from the research, organized by topic. Used to inform the Pattern Language architecture and T5 implementation decisions.

---

## 1. Design Encoding Formats for LLMs

### 1.1 Google Stitch's DESIGN.md

Stitch (Google Labs, launched Google I/O May 2025) introduced DESIGN.md as an "agent-readable" markdown file encoding a project's complete design system. Format uses plain markdown with semantic headers:

- **Brand Identity** — mood, aesthetic, visual principles
- **Color System** — semantic token names with hex values and usage guidance
- **Typography** — font stacks, type scale, weight conventions, line-height
- **Spacing & Layout** — base grid (8px), named token set, container widths
- **Component Guidelines** — per-component rules (border radius, padding, hover states, variants)
- **Do's and Don'ts** — explicit negative constraints

Key insight: DESIGN.md is deliberately NOT a formal schema. Uses natural-language markdown because models understand markdown natively. Functions as persistent system-prompt context that Gemini reads before every generation pass. Portable across Stitch, Cursor, Claude Code, Gemini CLI.

Critical limitation: probabilistic enforcement. The model reads it as guidance, not as hard constraints. Colors drift, components deviate, cross-session consistency is poor.

### 1.2 OpenAI's Frontend Design Playbook (GPT-5.4)

Encodes aesthetic principles as YAML-based "skill" files with three layers:
- **Beautiful Defaults** — prescriptive patterns to favor
- **Hard Rules** — explicit constraints (one composition per first viewport, brand-first design, expressive typography, no flat backgrounds, full-bleed hero images)
- **Reject These Failures** — anti-patterns to actively avoid (generic cards, weak branding, UI clutter)

Notable: encodes design flow as narrative structure (hero → supporting imagery → product detail → social proof → CTA) rather than component trees, steering compositional rhythm. Recommends visual references/mood boards as guardrails, leveraging image understanding for layout rhythm.

### 1.3 SDUI: Airbnb's Ghost Platform

Airbnb's Ghost Platform defines declarative UI via a single shared GraphQL schema. Decomposes UI into three primitives:
- **Screens** — where and how sections appear
- **Sections** — independent groups of related UI components
- **Actions** — user interaction handlers

Each section has a `SectionComponentType` enum allowing different visual renderings from the same data model. Server sends complete UI trees with component types, layout definitions, styling properties, action handlers. Netflix extended similar model beyond mobile to Web and TV.

Relevance: demonstrates UI can be fully described as structured data with a fixed component vocabulary and compositional rules — a DSL for UI that separates content from presentation.

### 1.4 LayoutGPT (NeurIPS 2023)

Demonstrated CSS-like syntax is effective for LLM spatial reasoning. Layouts represented as style-sheet structures with normalized coordinates. Uses CSS `img` tag properties with bounding boxes. Achieved strong results in both 2D image layout and 3D indoor scene composition. Outperformed other methods by 20-40% on spatial reasoning when combined with region-controlled image generation.

Validation: LLMs can reason about spatial relationships when given structured, CSS-like coordinate representations.

### 1.5 MLS — Modular Layout Synthesis (arXiv Dec 2025)

Most formally rigorous IR found. Three-stage pipeline:

**Stage 1 — Layout Arborescence**: Each node is `(category, geometry, payload)`. Categories from fixed vocabulary: `{wrap, row, col, text, media, ctl, link}` (7 types). Geometry is normalized `[0,1]^4` bounding coordinates. Payload is out-of-band content. Serialized as bracketed topology strings parseable by simple balanced-brace grammar.

**Stage 2 — Framework-Agnostic Blueprint**: Four-tuple of:
1. Skeleton Tree — structure with typed holes replacing literals
2. Motif Library — discovered reusable templates
3. Instance Tables — per-instance field values for loop/component params
4. Typing Environment — prop schemas (`{Str, Num, Bool, Url, Enum}`)

**Stage 3 — Constrained Generation**: Framework-conditioned protocol guides LLM to emit typed components without expanding duplicates.

Key relevance: MLS's motif library concept maps to our component vocabulary. Its typed slots map to our token vocabulary constraints. Its fixed 7-category vocabulary demonstrates that a small, constrained output space dramatically improves generation quality.

### 1.6 Figma MCP Design System Rules

Figma's MCP server generates agent-readable rules files encoding token definitions, component libraries, style hierarchies, naming conventions. With Code Connect, produces `CodeConnectSnippet` wrappers with import statements, real usage code, design properties, and custom instructions — giving agents enough context to use existing components rather than generating new ones.

### 1.7 W3C DTCG Design Tokens Format (2025.10)

First stable version of vendor-neutral JSON interchange format using `$`-prefixed properties. Over 10 tools support it. Not designed for LLM consumption, but provides standardized machine-parseable representation of design decisions. Our DB already uses DTCG as internal type system.

### 1.8 LaySPA (arXiv 2026)

Related to LayoutGPT — shows that serializing layouts into HTML/CSS/SVG text formats enables LLMs to apply recursive reasoning over spatial dependencies.

### 1.9 LLMs as Layout Designers (arXiv 2025)

Further validation that LLMs can serve as layout planners when given appropriate structured representations.

---

## 2. What Encoding Properties Matter for LLM Reasoning

### 2.1 Format Comparison

Research consistently shows **markdown outperforms HTML** for LLM reasoning: 60.7% accuracy extracting insights from markdown tables vs. 53.6% for HTML. Markdown wins on token efficiency, structural clarity, and noise reduction.

A November 2025 study on prompt formatting evaluated plain text, Markdown, YAML, and JSON across GPT models — format choice measurably impacts performance.

### 2.2 CSS-Like Syntax for Spatial Reasoning

CSS notation works because:
- LLMs have extensive training data in CSS
- Bounding-box coordinates map naturally to CSS positioning
- Hierarchical selectors encode parent-child spatial relationships
- Property-value pairs are concise and unambiguous

### 2.3 Properties That Make Encodings Effective (ranked by importance)

1. **Fixed, small vocabulary** — MLS uses 7 categories; SDUI uses enumerated types. Constraining output space dramatically improves quality.
2. **Normalized coordinates** — `[0,1]` ranges rather than absolute pixels. Generalizes across screen sizes.
3. **Hierarchical tree structure** — every successful format represents UI as a tree.
4. **Separation of structure from content** — keep structural skeleton distinct from literal values.
5. **Typed slots over raw values** — constrain what can fill each position, reducing hallucination.
6. **Negative constraints alongside positive rules** — telling the model what NOT to do is as important as what to do.
7. **Qualitative principles over quantitative specs** — LLMs reason better about design intent than pixel-precise reproduction.

### 2.4 The Emerging Consensus: Layered Encoding

No single format is sufficient. The most effective approaches combine:
- **Layer 1 (tokens):** Structured JSON/DTCG for design tokens (colors, spacing, typography values)
- **Layer 2 (rules):** Markdown for compositional rules, constraints, and aesthetic principles
- **Layer 3 (structure):** CSS-like or bracketed tree notation for spatial layout
- **Layer 4 (reference):** Visual examples (screenshots) for calibrating taste

---

## 3. Design Quality Encoding

### 3.1 UIClip (UIST 2024)

CLIP-based model that scores UI design quality given screenshot + natural language description. Trained on automated crawling + synthetic augmentation + ratings from 12 human designers. Highest agreement with human ground-truth rankings among all tested baselines. Encodes quality implicitly through learned embeddings — proximity to high-quality examples implies quality, without explicit rules. Supports: scoring generated code, design recommendations, quality-filtered search.

### 3.2 DesignPref (2024)

12k pairwise comparisons annotated by 20 professional designers with multi-level preference ratings. Key finding: **personalized models consistently outperform aggregated baselines**. Design quality is not a single axis but a multi-dimensional space where individual taste vectors matter.

### 3.3 Taste (buildwithtaste.com)

Users capture screenshots of admired UI (Cmd+Shift+T). GPT Vision extracts tokens and synthesizes qualitative taste profile. Explicitly states extracted tokens are observations, not specs — for "calibration of instincts" not copying hex codes. Encodes:
- **Extracted tokens** — colors, radius, shadows, padding, typography (observational)
- **Qualitative profile** — "gravitates toward cool and muted color palettes," "generous spacing"
- **Reference screenshots** — organized by category

Most conceptually interesting approach: encodes taste as a direction vector in aesthetic space rather than a set of rules.

### 3.4 Academic Framework (arXiv Jan 2026)

Proposes linking subjective aesthetic evaluations with domain-specific features and computer vision measures. Aims to bridge learned embeddings (UIClip-style) and explicit rules (design system-style).

### 3.5 Summary of Quality Encoding Approaches

| Approach | Format | Quality Signal | Personalization |
|----------|--------|---------------|-----------------|
| UIClip | Learned embedding | Screenshot + description similarity | No (aggregated) |
| DesignPref | Pairwise comparisons | Designer preference rankings | Yes (per-designer) |
| Taste | Qualitative markdown + screenshots | Visual reference similarity | Yes (per-user) |
| OpenAI Skill | YAML rules | Hard constraints + anti-patterns | Partial (per-project) |
| Stitch DESIGN.md | Markdown tokens + rules | Consistency with defined system | Partial (per-project) |
| DTCG | JSON spec | Token conformance | No (system-level) |

---

## 4. The Anthropic Frontend-Design Skill (Detailed)

### Structure and Philosophy

~400 tokens. Uses "just-in-time context loading" — activates only when Claude identifies frontend tasks. Solves "distributional convergence" — LLMs predict tokens based on statistical patterns, converging toward safe design choices dominating training data (Inter fonts, purple gradients, minimal animations).

### The "Right Altitude" Encoding

Not hardcoding low-level specs (exact hex codes) but not being vague. Provides targeted language that encourages critical thinking across specific design dimensions while remaining implementable.

### Four Design Vectors

**Typography**: Explicitly bans overused fonts (Inter, Roboto, Arial, system fonts). Instructs pairing "distinctive display font with refined body font." Even with bans, models converge on new favorites (Space Grotesk), so skill reinforces variety.

**Color & Theme**: Does not prescribe palettes. Directs toward "commitment and cohesion" — "Dominant colors with sharp accents outperform timid, evenly-distributed palettes." CSS variables for consistency.

**Spatial Composition**: Names compositional moves: "Unexpected layouts. Asymmetry. Overlap. Diagonal flow. Grid-breaking elements. Generous negative space OR controlled density."

**Motion**: "One well-orchestrated page load with staggered reveals creates more delight than scattered micro-interactions."

### Anti-Pattern Recognition

Explicit catalog of what to avoid. The anti-patterns are as important as positive instructions.

### Design Thinking Process

Before coding, demands answering: Purpose (problem, audience), Tone (pick an extreme — brutalist, maximalist, retro-futuristic), Constraints (framework, a11y), Differentiation (what makes this unforgettable).

### 8 Key Techniques for LLM Design Quality

1. **Negative constraints as powerful as positive instructions.** Banning specific patterns prevents distributional convergence.
2. **Encode at the right altitude.** Not pixel specs, not vague aspirations. Name compositional moves.
3. **Force aesthetic commitment before implementation.** "Pick an extreme" prevents averaging across styles.
4. **Separate intent from code generation.** UX flows, a11y, motion as separate checklist items.
5. **Encode taste through pattern analysis of existing work.** Point LLM at actual projects, extract patterns, lock into skill.
6. **Reinforce variety across generations.** "NEVER converge on common choices across generations."
7. **Match implementation complexity to aesthetic vision.** Maximalist designs need elaborate code.
8. **Multi-pass workflow.** Aesthetic direction first, then craft polish, then accessibility, then performance.

### The Owl-Listener Design Skills Collection (63 skills)

"Claude doesn't need paragraphs of theory. It needs clear frameworks, decision criteria, and an understanding of when to apply what."

Visual hierarchy encoded as five tools with quantitative thresholds: Size (1.5x minimum difference), Weight (bold/thick/filled vs light), Color/Contrast (high for CTAs), Spacing (more whitespace = more importance), Position (F-pattern, Z-pattern).

Four explicit hierarchy levels: Primary, Secondary, Tertiary, Quaternary.

Grid components defined as ranges: columns 4-12, gutters 16/24/32px, margins 16px mobile to 48px desktop, breakpoints at 375/768/1024/1440px.

---

## 5. Adversarial Design Critique Research

### 5.1 Vision Models for Design Evaluation

**AesEval-Bench** (Microsoft, March 2026): First systematic benchmark for VLM aesthetic assessment of graphic design. Four dimensions (layout, typography, color, imagery) across twelve indicators. Key findings:
- Proprietary VLMs (GPT series) outperform open-source but ALL have clear gaps vs. human-level aesthetic assessment
- **Reasoning-augmented VLMs (GPT-o1, GPT-o3, Gemini-2.5-Pro) offer NO clear advantage** for aesthetic tasks. Chain-of-thought doesn't help with design judgment.
- Fine-tuning on design-specific data consistently improves performance

**ScreenAI** (Google, IJCAI 2024): 5B params, PaLI architecture. SOTA on UI understanding tasks. Understands element types, locations, descriptions. Fundamentally a comprehension model, not aesthetic judgment.

**Bottom line**: Vision models are strong at structural critique (alignment, element presence, layout violations) and moderate at aesthetic critique (color harmony, visual hierarchy, whitespace balance). Fine-tuning helps.

### 5.2 Multi-Model Critique Loop Patterns

**Self-Refine** (NeurIPS 2023): Foundational generate-feedback-refine loop. Maximum 4 iterations. ~20% absolute improvement on average. Convergence not guaranteed — needs scalar stopping criteria.

**Iterative Consensus Ensemble (ICE)**: Three LLMs critique each other until convergence. 7-15 point accuracy increase over best single model. Closest to true adversarial multi-model approach.

**PASR — ProActive Self-Refinement** (August 2025): Instead of post-hoc refinement, model decides DURING generation whether, when, and how to refine. Results: **-41.6% token usage, +8.2% accuracy** vs. standard generation. Suggests the future of refinement is in-process, not multi-pass.

**Constitutional AI**: Anthropic's pattern of model critiquing itself against principles. Maps directly to design — define a "design constitution" (Gestalt, WCAG, hierarchy rules). Limitation: works less well with smaller models.

### 5.3 Systems That Implement Generate-Screenshot-Critique-Refine

**VisRefiner** (Feb 2025): Trains models to learn from visual differences between rendered code and target screenshots. Two stages: difference-aligned supervision (links localized visual changes to corrective code edits) and RL with self-refinement. Most directly relevant paper — trains visual difference detection INTO the model.

**WebGen-Agent** (Sep 2025): VLM generates text critiques from screenshots + GUI-agent testing feedback, with backtracking and select-best mechanisms. Results:
- **Claude 3.5 Sonnet accuracy: 26.4% → 51.9%** (nearly 2x)
- Appearance score: 3.0 → 3.9 (out of 5)
- Introduces Step-GRPO: dense step-level rewards from screenshot and GUI-agent feedback
- Open-sourced: code, training data, model weights

**1D-Bench** (Feb 2026): Benchmark for iterative visual refinement. Finding: iterative editing generally improves performance by increasing rendering success and visual similarity. RL-based editing showed limited, unstable gains — likely from sparse terminal rewards.

**Visual Prompting with Iterative Refinement for Design Critique** (Dec 2024): Gemini-1.5-Pro and GPT-4o iteratively generate design critiques with bounding boxes from screenshots + design guidelines. Human experts preferred pipeline-generated critiques over baselines, reducing gap from human performance by 50%.

**Vercel v0**: Retrieval-grounded generation + frontier LLM + "AutoFix" streaming post-processor for errors and best-practice violations. Refinement is conversational (user-in-loop), not automated critique. Does NOT appear to use screenshot-based visual evaluation.

**Builder.io Visual Copilot**: Three-stage pipeline: (1) specialized model converts Figma → code hierarchies, (2) Mitosis compiler for framework translation, (3) fine-tuned LLM adapts output. Multi-pass but structural, not screenshot-based.

**Design2Code** (NAACL 2025): 484 real-world webpages. Claude-4-Sonnet achieves ~76.3/100. Divide-and-Conquer improves pixel-level and structural scores by 12-37% on mobile.

**Interaction2Code** (2024): First benchmark for interactive webpage generation. Key finding: visual-only descriptions insufficient; interaction semantics require multimodal understanding.

### 5.4 Convergence Behavior

- **1-2 rounds** capture majority of improvement (diminishing returns)
- **3-4 rounds** is practical maximum before improvements plateau or oscillate
- **Stopping criteria are critical** — without them, models can degrade outputs
- **Component-level edits** (1D-Bench) converge more reliably than full-page regeneration
- RL-based iterative editing shows limited, unstable gains vs. supervised approaches

### 5.5 Cost/Performance Profile

Each screenshot-critique-refine cycle adds ~10-30s (rendering + VLM critique + refinement). A 3-round loop therefore adds roughly 30-90 seconds. WebGen-Agent's backtracking + select-best (generate multiple candidates, pick best) may be more practical than sequential refinement.

---

## 6. Efficiency and Cost Research

### 6.1 Token Representation Sizes

| Representation | Tokens (typical screen) |
|---|---|
| Raw HTML (Design2Code benchmark) | ~31,000 median |
| Raw DOM (web app page) | 100,000+ |
| Figma REST API JSON (full file) | 48MB+ |
| Accessibility tree (standard) | 14,500-19,400 |
| Accessibility tree (optimized) | 3,000-7,800 (51-79% smaller) |
| Mind2Web UI (raw) | ~52,000 |
| Mind2Web UI (UIFormer optimized) | ~6,100 (88% reduction) |
| Android screen (UIFormer optimized) | 596-1,484 (49-54% reduction) |

**UI representations account for 80-99% of total tokens. This is THE optimization target.**

### 6.2 UIFormer (Deployed at WeChat)

Achieved 49-88% token reduction depending on platform. 76.9% average in production. IMPROVED task success rates while reducing tokens. Key technique: DSL that merges parent-child nodes and strips non-actionable elements while preserving semantic hierarchy. Also reduced latency by 26.1% and increased throughput by 35.2%.

### 6.3 Representation Format Efficiency

| Format | Token Efficiency | LLM Comprehension |
|---|---|---|
| Full node-tree JSON | Worst | Good |
| TOON (tabular) | 60% fewer than JSON | Good |
| Markdown | ~50% fewer than HTML | Excellent |
| HTML (vs JSON for actions) | 11% fewer, 3.9% better success | Good |
| Custom DSL | Best possible | Requires training/examples |
| Declarative spec (structured schema) | Compact | Excellent |

### 6.4 The Validation Cascade (Cost Pyramid)

| Level | Cost | Catches |
|---|---|---|
| Schema validation | ~0 tokens (code) | 30-40% of issues |
| Rule-based structural | ~0 tokens (code) | 20-30% of issues |
| LLM structural critique | 500-2,000 tokens | 15-25% of issues |
| Vision critique | 1,000-5,000 tokens + image | 10-15% of issues |

**85-90% of generations never need the expensive vision pass.**

ViCR (Visual Critic without Rendering): predicting visual discrepancy from code alone achieves comparable performance to screenshot comparison, at much lower cost.

### 6.5 Model Routing Strategy

| Task | Model | Why |
|---|---|---|
| Schema validation | None (code) | Zero cost |
| Rule-based checks | None (code) | Zero cost |
| Design token lookup | Haiku | Simple retrieval |
| Layout structure generation | Sonnet | Spatial reasoning |
| Component selection | Haiku | Pattern matching |
| Full screen composition | Sonnet | Complex but not frontier |
| Visual critique (screenshot) | Sonnet | Vision capability |
| Novel/creative layout | Opus | Only genuinely hard problems |

Typical cascade: 60-70% at Haiku cost, 25-30% Sonnet, 3-5% Opus. Produces **50-60% cost reduction** vs. Sonnet-for-everything.

### 6.6 Self-Refine Convergence Formula

```
Acc_t = Upp - alpha^t * (Upp - Acc_0)
```

With typical parameters: Rounds 1-2 capture 75% of total improvement. Hard cap at 3 iterations.

### 6.7 Cost Per Screen

| Scenario | Cost |
|---|---|
| Single pass Sonnet (compact spec) | $0.025-0.03 |
| With 1 critique iteration | $0.05-0.08 |
| Worst case (3 iterations + vision) | $0.15-0.20 |
| 100 screens batch | $2.50-5.00 total |
| For comparison: Bolt.new error recovery | $3-8 per task |

### 6.8 Prompt Caching Impact

Cache hits cost 10% of base input price. Design system prefix of 6-20K tokens cached across 100 screens saves $1.60-5.40. Second-highest-impact optimization after compact output schemas.

### 6.9 Time Per Generation

| Phase | Time |
|---|---|
| Schema validation | <10ms |
| Rule engine | <100ms |
| Haiku generation | 1-2s |
| Sonnet generation | 2-4s |
| Vision critique | 3-5s |
| Figma API write | 0.5-2s |
| **Total (optimal, single pass)** | **3-8s** |
| **Total (with 1 critique loop)** | **6-12s** |

### 6.10 Key Optimizations Ranked by Impact

1. **Compact declarative schema** — 10-20x fewer output tokens vs raw HTML/CSS
2. **Prompt caching** — 90% savings on design system prefix
3. **Rule-based validation first** — eliminates 85% of critique LLM calls
4. **Model routing** — Haiku for simple, Sonnet for generation
5. **Batch API** — 50% discount for non-interactive generation
6. **Template/pattern reuse** — start from known-good, not blank canvas
7. **Stop at 2-3 iterations** — 75-87.5% of improvement captured

---

## 7. Source Index

### Academic Papers
- AesEval-Bench — https://arxiv.org/abs/2603.01083
- ScreenAI — https://arxiv.org/abs/2402.04615
- Self-Refine — https://selfrefine.info/
- PASR — https://arxiv.org/abs/2508.12903
- VisRefiner — https://arxiv.org/abs/2602.05998
- WebGen-Agent — https://arxiv.org/abs/2509.22644 (open-sourced)
- 1D-Bench — https://arxiv.org/abs/2602.18548
- Visual Prompting for Design Critique — https://arxiv.org/abs/2412.16829
- Design2Code — https://salt-nlp.github.io/Design2Code/
- Interaction2Code — https://arxiv.org/abs/2411.03292
- LayoutGPT — https://arxiv.org/abs/2305.15393
- MLS — https://arxiv.org/abs/2512.18996
- LaySPA — https://arxiv.org/abs/2602.13912
- UIClip — https://arxiv.org/abs/2404.12500
- DesignPref — ResearchGate (2024)
- UIFormer — https://arxiv.org/abs/2512.13438
- DOM Downsampling — https://arxiv.org/html/2508.04412v1

### Tools and Systems
- Google Stitch — https://stitch.withgoogle.com/
- Taste — https://buildwithtaste.com/
- Component Gallery — https://component.gallery
- Figma MCP — https://www.figma.com/blog/design-systems-ai-mcp/
- W3C DTCG — https://www.designtokens.org/tr/drafts/format/
- v0 System Prompt — https://agentic-design.ai/prompt-hub/vercel/v0-20250306
- Builder.io Visual Copilot — https://www.builder.io/blog/figma-to-code-visual-copilot
- WebGen-Agent GitHub — https://github.com/mnluzimu/WebGen-Agent

### Design Skills
- Anthropic frontend-design SKILL.md — https://github.com/anthropics/claude-code/blob/main/plugins/frontend-design/skills/frontend-design/SKILL.md
- Owl-Listener/designer-skills (63 skills) — https://github.com/Owl-Listener/designer-skills
- mager/frontend-design — https://www.mager.co/blog/2026-02-08-mager-frontend-design/

### Industry Analysis
- Anthropic Constitutional AI — https://www.anthropic.com/research/constitutional-ai-harmlessness-from-ai-feedback
- Anthropic Computer Use — https://www.anthropic.com/news/3-5-models-and-computer-use
- OpenAI Frontend Design Playbook — https://developers.openai.com/blog/designing-delightful-frontends-with-gpt-5-4
- Airbnb Ghost Platform — https://medium.com/airbnb-engineering/a-deep-dive-into-airbnbs-server-driven-ui-system-842244c5f5
- Figma: 5 Shifts Redefining Design Systems — https://www.figma.com/blog/5-shifts-redefining-design-systems-in-the-ai-era/
