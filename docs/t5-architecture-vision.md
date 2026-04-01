# T5 Architecture Vision — Generation, Critique, and Taste

Captured from conversation 2026-03-31. This document defines the full architectural vision for T5 Conjure: how screens are generated, critiqued, steered, and refined. Includes the autonomous exploration model, the critique cascade, the taste model concept, the corpus pipeline design, the distribution architecture, and the terminology definitions.

---

## Terminology (Canonical Definitions)

These terms were explicitly discussed and agreed upon. Use them consistently.

| Term | Definition | What it is NOT |
|------|-----------|----------------|
| **Pattern Language** | The multi-level compositional descent process for composing design screens. The method itself — the levels, the branching, the pruning, the re-entry points. See `docs/t5-pattern-language.md`. | Not a dataset. Not distributions. Not a vocabulary. |
| **Taste Model** | Quality-weighted distributions derived from the curated corpus. Statistical summaries of what's common, what's good, and what's interesting at each level of the Pattern Language. Feeds into the Pattern Language as an input. Built and refined separately. | Not the corpus itself. Not the pattern language. Not raw screenshots. |
| **Component Vocabulary** | The 60 canonical UI component types, inspired by component.gallery's catalog of 2,676 implementations across 95 design systems. These are the "nouns" of the design language. | Not specific component implementations. Not visual designs. |
| **Token Vocabulary** | The DB's design tokens (currently 388 across 8 collections in the Dank file). These are the "adjectives" — the colors, typefaces, spacing values, radii, etc. Per-project, not universal. | Not the component vocabulary. Not styling rules. |
| **Corpus** | The raw curated screenshots + structural decompositions used to derive the taste model. Source material. Never shipped to users. Never used directly at generation time. | Not the taste model. Not the pattern language. |
| **Critique Cascade** | The multi-level evaluation process: rule-based → structural → visual. Provides the pruning mechanism at Level 4 of the Pattern Language. | Not a single-pass evaluation. Not just a vision model check. |
| **Decision Tree** | The tree of design choices explored during a Pattern Language descent. A first-class data structure recording what was tried, what was chosen, and why. Enables non-destructive exploration. | Not a flat history. Not just the final output. |

---

## The Autonomous Exploration Architecture

The system operates in two modes: autonomous exploration and user steering. The agent does the full Pattern Language descent autonomously, then presents 2-3 fully resolved options. The user steers by providing feedback that re-enters the tree at the appropriate level.

### Why Fully Resolved (Not Wireframes)

Wireframes require a second creative pass to become real screens. That second pass re-opens decisions you thought were closed — colors change perceived hierarchy, type sizes change spatial rhythm, a component that looked fine as a gray box breaks with real content. Wireframes lie. The only trustworthy evaluation is on resolved output.

The cost math works: if the agent explores ~3 skeletons, prunes to 2, elaborates each, applies tokens, renders to Figma, runs visual critique — that's maybe 6-8 fully resolved screens at $0.05-0.08 each. Under $0.50 per exploration cycle.

### The Exploration Flow

```
User: "Build me a settings page for this iOS app"
                    │
                    ▼
         ┌── EXPLORE (autonomous) ──┐
         │                          │
         │  Phase 1: DIVERGE        │
         │  Generate 3 skeletons    │   ← ~500 tokens each, abstract
         │  Structural critique     │   ← Haiku, prune weakest
         │                          │
         │  Phase 2: ELABORATE      │
         │  Top 2 → internal comp   │   ← ~1K tokens each
         │  Structural critique     │   ← prune/merge
         │                          │
         │  Phase 3: RESOLVE        │
         │  Apply token vocabulary  │   ← deterministic DB lookup
         │  Generate Figma specs    │   ← compact DSL → MCP calls
         │  Render in Figma         │
         │                          │
         │  Phase 4: CRITIQUE       │
         │  Rule-based (free)       │
         │  Visual (screenshot)     │
         │  Self-fix minor issues   │
         │                          │
         │  Phase 5: PRESENT        │
         │  2-3 fully resolved      │
         │  screens in Figma        │
         │  + decision rationale    │
         └──────────────────────────┘
                    │
                    ▼
         User: "I like B's layout but
         the card spacing from A. And
         make the toggle section more
         prominent."
                    │
                    ▼
         ┌── STEER (targeted) ──────┐
         │  Route feedback to level: │
         │  "B's layout" → L1       │
         │  "card spacing" → L3     │
         │  "more prominent" → L2/3 │
         │  Regenerate from deepest │
         │  affected level          │
         └──────────────────────────┘
                    │
                    ▼
         1-2 refined options
```

### How Steering Works

User feedback maps to specific re-entry points in the abstraction hierarchy:

| Steering input | Level | Cost to re-resolve |
|---|---|---|
| "Different layout entirely" | L1 skeleton | Full re-descent |
| "Horizontal cards instead of vertical" | L2 component elaboration | Re-elaborate + re-style |
| "Tighten the spacing" | L3 tokens | Re-apply tokens (near free) |
| "CTA needs more prominence" | L2/L3 hierarchy | Targeted adjustment |
| "I like it, ship it" | Done | — |

The system knows which level to re-enter because the decision tree is preserved. When the user says "I like B's layout," the system can graft A's token choices onto B's skeleton without regenerating from scratch.

---

## The Critique Cascade

Four levels of critique, ordered by cost. Run cheapest first. Only escalate to more expensive levels when cheaper levels pass.

### Level 1 — System Critique (Deterministic, Free)

Query the DB: Are all nodes token-bound? Are any hardcoded values present? Are components used where they should be? Are required slots filled?

This is validation — no LLM cost, runs in milliseconds.

### Level 2 — Structural Critique (Cheap, Haiku)

Read the node tree: Does the layout follow hierarchy? Is spacing consistent? Is typography applied with proper scale? Are interactive states present where needed? Is the visual hierarchy readable (Primary → Secondary → Tertiary)?

Can be done with an LLM reading the structured representation — no screenshot needed. ~500-2,000 tokens.

### Level 3 — Visual Critique (Expensive, Vision Model on Screenshot)

Take a screenshot via MCP, pass to vision model with critique prompt. Is the visual balance right? Does the spacing FEEL right? Is the hierarchy readable visually (not just structurally)? Does it look designed or accidental?

This is where taste lives. Also where the taste model eventually provides reference comparisons. 1,000-5,000 tokens + image.

### Level 4 — Accessibility Critique (Deterministic, Free)

Pull resolved color values from DB, compute WCAG contrast ratios, check tap target sizes against spacing tokens, verify focus order, check label presence.

Computable without a model. Run in parallel with Level 1.

### Ordering

**L1 and L4 run first (parallel, free). L2 next (cheap). L3 only if L1, L2, L4 pass.**

Research finding: 85-90% of generations never need the expensive L3 vision pass. Rule-based checks catch 60-70% of issues. Structural LLM check catches another 10-15%.

### Structured Critique Output

Not freeform prose. Structured JSON that the generation agent can act on:

```json
{
  "pass": false,
  "level": "structural",
  "issues": [
    {
      "severity": "high",
      "category": "hierarchy",
      "description": "Primary CTA has same visual weight as secondary action",
      "affected_nodes": ["button-primary-1", "button-secondary-1"],
      "suggested_fix": "Increase font weight or size of primary CTA, or bind to type.label.lg"
    },
    {
      "severity": "low",
      "category": "spacing",
      "description": "Gap between header and content inconsistent with section gaps",
      "affected_nodes": ["section-header-1"],
      "suggested_fix": "Set itemSpacing to space.s24 token (matches other section gaps)"
    }
  ]
}
```

`affected_nodes` referencing DB IDs means the generation agent makes targeted fixes, not full regeneration.

### Iteration Budget

Based on Self-Refine convergence research: rounds 1-2 capture 75% of total improvement. Hard cap at 3 iterations. After that, diminishing returns dominate. If 3 iterations haven't resolved the issues, the system should present what it has and let the user steer.

---

## The Taste Model

### What It Is

The taste model is the set of quality-weighted statistical distributions derived from the curated corpus. It provides empirical grounding for choices at each level of the Pattern Language.

### What It Contains

For each screen type + platform combination:

**Skeleton distributions (Level 1)**:
- Which structural arrangements are used, with frequency AND quality weighting
- Quality weighting comes from the curator's ratings — not all examples are equally good
- Example: "Of 47 settings screens, grouped-sections appears 78% (freq) but the 15 highest-rated use profile-hero+groups (quality-weighted)"

**Elaboration distributions (Level 2)**:
- Which internal component compositions are used within each skeleton type
- Example: "Within grouped-sections, toggle-rows 65%, descriptive-rows 20%, card-based 15%"

**Cross-level correlations**:
- How choices at one level correlate with choices at other levels
- Example: "Screens using card-based settings tend toward more border-radius and shadow tokens"

**Compositional rules**:
- Observed principles that hold across high-quality examples
- Example: "Danger zone (destructive actions) always at bottom, visually separated"

### What It Does NOT Contain

- Exact token values (those come from the user's project DB)
- Screenshots (those stay in the corpus)
- Component implementations (those come from the component vocabulary)
- Aesthetic direction (that comes from taste encoding / design principles — a separate concern from statistical distributions)

### Separating Frequency from Quality

A critical insight from the discussion: shipping only frequency distributions would produce the statistical median of design — the most average, least distinctive output possible. The same distributional convergence problem the Anthropic frontend-design skill fights.

The taste model must separate:
- **What's common** (frequency) — prevents nonsensical choices
- **What's good** (quality-weighted) — steers toward quality
- **What's interesting** (outliers that scored well) — enables distinctive exploration

The agent uses all three sampling strategies:
- Option A: High-probability choice (what most apps do) — safe default
- Option B: Quality-weighted choice (what the BEST apps do) — premium feel
- Option C: Interesting outlier (unexpected but well-rated) — distinctive

### Size and Portability

The taste model is compact. Statistical distributions compress:

```
60 component types × metadata ≈ 50KB
Screen-level skeleton distributions ≈ 100KB
Component-level elaboration distributions ≈ 200KB
Cross-level correlations ≈ 100KB
Compositional rules + constraints ≈ 50KB
─────────────────────────────────────────
Total: ~500KB - 2MB
```

Whether derived from 50 or 50,000 corpus screens, the output size is the same — the distribution gets more accurate but doesn't get larger. The corpus grows; the taste model stays compact.

### Building the Taste Model (Deferred)

The full corpus ingestion pipeline is deferred to a later phase. The detailed capture/ingestion system will be designed separately. For now, the key decisions:
- The corpus is curated personally (Matt selects which apps/screens go in)
- The curator's ratings provide the quality weighting
- Structural decomposition must be high accuracy (not the 80% approximation initially suggested — Matt pushed back on this)
- The taste model is derived/distilled from the corpus, not the corpus itself
- The corpus is never shipped; only the taste model is distributed

---

## Distribution Architecture

For a publicly distributable system:

```
┌─────────────────────────────────┐
│  Declarative Design (CLI/Agent) │
│                                 │
│  ┌───────────┐  ┌────────────┐  │
│  │ Project DB│  │  Taste      │  │
│  │ (per-file)│  │  Model      │  │
│  │           │  │  (shared)   │  │
│  │ tokens    │  │             │  │
│  │ bindings  │  │ distrib.    │  │
│  │ nodes     │  │ correlat.   │  │
│  │ screens   │  │ rules       │  │
│  └───────────┘  └──────┬──────┘  │
│                        │         │
└────────────────────────┼─────────┘
                         │
              ┌──────────┴──────────┐
              │  Distribution       │
              │                     │
              │  dd-taste@1.2.0     │
              │  (versioned, ~1MB)  │
              │                     │
              │  SQLite file or     │
              │  JSON bundle        │
              └─────────────────────┘
```

**Versioned releases**: `dd-taste@1.0.0` ships with initial curation. Minor versions add patterns/refine distributions. Major versions change schema. Users pin or auto-update.

**Update mechanism**: `dd update-taste` pulls latest bundle. No heavy downloads, no re-indexing. Swap the file.

### User Contribution Modes

**Mode 1 — Use only (default)**: Download taste model, use for generation. Project DB provides token vocabulary. Taste model informs composition.

**Mode 2 — Local enrichment**: User's extracted Figma screens get analyzed and folded into their LOCAL taste model copy. System learns from their existing design decisions. Stays local.

**Mode 3 — Contribute back (opt-in)**: User submits structural decompositions (not screenshots, not token values — just abstract patterns) to central registry. Curator folds into next release. Privacy-safe: abstract patterns are non-proprietary.

---

## The Component Vocabulary

### Source: component.gallery

60 canonical UI component types derived from component.gallery's catalog of 2,676 real-world implementations across 95 design systems. Christopher Alexander's Pattern Language applied to UI.

### Structure

- **Flat taxonomy** — all 60 types are peers, no hierarchical categories
- **Canonical name + aliases** — each type has one canonical name and zero or more aliases (e.g., "Accordion" also known as: Arrow toggle, Collapse, Collapsible, Details, Disclosure, Expandable)
- **Cross-referencing** — types link to related types (e.g., Button → Button group)

### The Full 60 Types

Accordion, Alert, Avatar, Badge, Breadcrumbs, Button, Button group, Card, Carousel, Checkbox, Color picker, Combobox, Date input, Datepicker, Drawer, Dropdown menu, Empty state, Fieldset, File, File upload, Footer, Form, Header, Heading, Hero, Icon, Image, Label, Link, List, Modal, Navigation, Pagination, Popover, Progress bar, Progress indicator, Quote, Radio button, Rating, Rich text editor, Search input, Segmented control, Select, Separator, Skeleton, Skip link, Slider, Spinner, Stack, Stepper, Table, Tabs, Text input, Textarea, Toast, Toggle, Tooltip, Tree view, Video, Visually hidden.

### Layout Primitives (Separate from Component Types)

~7 structural layout types inspired by MLS's formal vocabulary: stack, row, grid, overlay, scroll, wrap, spacer. These describe HOW components are arranged, not WHAT the components are. They are the "verbs" that connect the "nouns" (component types).

### Adaptation for Declarative Design

The component.gallery list is web-centric. Some types may need adaptation:
- Web-specific types that are less relevant for mobile (Skip link, Visually hidden)
- Mobile patterns that may be missing (Bottom sheet, Pull to refresh, Swipe actions)
- The list should be extended, not replaced — start from the 60 and modify

This adaptation is a design decision to be made during implementation, not pre-decided now.

---

## The Decision Tree as First-Class Data

### Why Store It

The tree of design decisions should be stored in the DB, not just held in memory. This enables:

- **Non-destructive exploration** — go back and explore paths not taken
- **Design rationale** — "why does this screen look like this?" answered by the decision tree
- **Learning** — observe which decisions survive user steering and which get overridden (implicit taste data)
- **Steering** — user says "I like B's layout" and the system can graft A's choices onto B's skeleton
- **Resumability** — come back to an exploration session later

### What Each Node Records

- The level (skeleton / elaboration / styling / critique)
- The choice made (which component types, which internal arrangement, which tokens)
- The alternatives considered
- The critique results that influenced the choice
- Parent/child relationships to other decisions
- Whether the user accepted, rejected, or steered from this node

### Relationship to Existing DB Schema

The decision tree is a new concept not yet represented in the schema. It will need its own tables — likely:
- `exploration_sessions` — one per user prompt/exploration cycle
- `decision_nodes` — one per choice point in the tree, with parent_id for tree structure
- `decision_alternatives` — the options considered at each choice point
- `decision_critiques` — critique results attached to each node

Schema design deferred to implementation phase.

---

## Autonomous Experimentation (Self-Play)

The same architecture that powers the generate→critique→steer loop can run autonomously to improve the taste model:

```
EXPERIMENT MODE:

1. Agent picks a screen type (e.g., "onboarding welcome screen")
2. Generates 5 skeletons from current taste model distributions
3. Elaborates all 5
4. Resolves with tokens
5. Renders to Figma
6. Runs full critique cascade (rules → structural → visual)
7. Scores each on: token coverage, hierarchy, balance, contrast, spacing
8. The highest-scoring compositions become NEW entries in the taste model
9. The distributions update

This runs overnight. You wake up to refined distributions.
```

Analogous to AlphaGo's self-play — the system improves its taste model by generating and evaluating its own compositions. The critique cascade is the reward function. The taste model is the policy.

Constraints (token vocabulary + component types) prevent nonsense. Critique cascade prevents bad patterns from entering the model. New patterns are added non-destructively — curator can review and prune.

**The feedback loop**: corpus → taste model → generation → critique → better taste model.

This capability is built on top of everything else and comes last in the build sequence.

---

## Build Sequence (Proposed)

Based on all discussions, the proposed build order:

1. **Pattern Language engine** — the multi-level descent process, decision tree storage, the exploration/pruning/steering loop. This is the core.

2. **Component vocabulary** — the 60 canonical types + layout primitives, stored in DB, queryable by the agent.

3. **Generation loop** — diverge → elaborate → resolve → critique → present. End-to-end for a single screen type (e.g., settings screen).

4. **Critique cascade** — rule-based → structural → visual. The evaluation system.

5. **Pattern extraction from Figma** (T5.12) — bootstraps taste model data from user's own file. First real training data.

6. **Corpus ingestion pipeline** — captures and decomposes external screenshots. Enriches taste model. Built in parallel track.

7. **Autonomous experimentation** — self-play mode for improving the taste model.

---

## Key Architectural Decisions and Rationale

### Decision: Fully resolved options, not wireframes
**Rationale**: Wireframes lie. Colors change perceived hierarchy, type sizes change spatial rhythm. The only trustworthy evaluation is on resolved output. Cost is manageable (~$0.05-0.08 per resolved screen).

### Decision: Autonomous exploration with user steering (not interactive step-by-step)
**Rationale**: Matt's design process involves exploring multiple options then distilling. The agent should do the same autonomously and present results for steering, not stop at every level to ask.

### Decision: Taste model as derived distributions, not raw corpus
**Rationale**: The corpus could be 500MB-2GB. The distributions are ~1-2MB. Users need the distilled knowledge, not the source material. This also protects contributor privacy.

### Decision: Component vocabulary from component.gallery's 60 types
**Rationale**: Real-world grounded (2,676 implementations across 95 systems), well-curated, inspired by Alexander's Pattern Language. Better to start from established taxonomy and adapt than invent from scratch.

### Decision: Critique cascade with cost ordering (L1/L4 → L2 → L3)
**Rationale**: Research shows 85-90% of issues caught by rule-based + structural checks. Vision critique is expensive and should only run when cheaper checks pass. Self-Refine convergence data shows 2-3 iterations is optimal.

### Decision: Per-project token vocabulary, shared taste model
**Rationale**: Every project has its own design tokens (colors, spacing, etc.). But compositional patterns (how settings screens are structured) are universal. Ship the universal part, combine with the project-specific part at generation time.

### Decision: Separate taste from frequency in the taste model
**Rationale**: Frequency-only distributions produce average, generic output (distributional convergence). Quality-weighting via curator ratings and separating "common," "good," and "interesting" enables distinctive generation. Three sampling strategies from the same data.

---

## The Abstract Component Layer as Universal Hub (Added 2026-04-01)

### The Vision

The abstract component layer is not a bridge between two specific endpoints (Figma ↔ Code). It is a **hub** in a hub-and-spoke model. Every input is a parser that converts TO the abstract format. Every output is a generator that converts FROM it. Adding a new input or output is just adding one spoke. The hub never changes.

```
        INPUTS                          OUTPUTS

  Text prompt ──────┐          ┌──────► Figma (with variable bindings)
  Figma file ───────┤          ├──────► React + shadcn/MUI/Radix
  Screenshot ───────┤          ├──────► SwiftUI
  Code repo ────────┤   ┌──┐  ├──────► Flutter
  Wireframe ────────┼──►│AC│──┼──────► HTML + Tailwind
  URL (live site) ──┤   │L │  ├──────► Design spec (text)
  Design spec ──────┤   └──┘  ├──────► Design tokens (CSS/DTCG)
  Sketch/XD file ───┘          ├──────► Another Figma file
                               └──────► Code (framework migration)
```

### Example Transformations

Any combination of input and output is a valid transformation:

| Input | Output | What it does |
|-------|--------|-------------|
| Text prompt | Figma | **Conjure** — compose screen from description (T5.9) |
| Figma | React+shadcn | **Design-to-code** — what Anima/Builder.io do |
| React+MUI | React+shadcn | **Framework migration** — parse one, generate the other |
| Code repo | Text spec | **Reverse engineering** — extract composition → describe it |
| Screenshot | Figma | **Screenshot to system-native** (T5.14) |
| Figma file A | Figma file B | **Design system migration** — extract with tokens A, regenerate with tokens B |
| URL | Figma | **Clone to Figma** — what Anima's l2c does |
| Text prompt | Text spec | **Design planning** — Pattern Language descent without materialization |

Every transformation is: **parse input → abstract composition → generate output.** The Pattern Language operates entirely in the abstract middle layer.

### What the Abstract Representation Must Capture

For any output format to produce a faithful translation, the representation needs:

1. **Component type** (from the ~45-50 canonical vocabulary)
2. **Slot assignments** (what fills each slot — text, another component, token reference)
3. **Token bindings** (which token fills each visual property)
4. **Structural arrangement** (the skeleton — how components relate spatially)
5. **Behavioral state** (interactive states, variants, conditions)
6. **Enough metadata** for any output format to produce faithful translation

### Library Mapping Layer

Each canonical type maps to target libraries via a thin translation layer:

```
Toggle (abstract)  →  shadcn: <Switch />
                   →  MUI: <Switch />
                   →  Radix: <Switch.Root />
                   →  SwiftUI: Toggle("Label", isOn: $value)
                   →  Figma: Component instance + BOOLEAN property
                   →  HTML: <input type="checkbox" role="switch" />
```

Adding a new output target means adding ~45-50 mappings (one per canonical type), not rebuilding the system. The abstract representation itself never changes.

### Existing Infrastructure That Supports This

The token translation layer already exists:
- `export_css.py` → CSS custom properties
- `export_tailwind.py` → Tailwind config
- `export_dtcg.py` → DTCG JSON
- `export_figma_vars.py` → Figma variables

These translate the TOKEN vocabulary. The new composition export layer would translate the COMPONENT vocabulary using the same pattern.

### What This Makes Declarative Design

Not "a Figma tool." Not "a design-to-code tool." A **universal design composition platform** where the abstract component layer is the lingua franca.

The existing T1-T4 codebase built the token vocabulary infrastructure (extract, cluster, curate, push tokens). T5 builds the composition infrastructure (component types, Pattern Language, translation layer). Together: a system that can read, write, and translate complete design compositions in any format, with every value constrained to a curated token vocabulary.

### The Critical Schema Design Problem

The abstract component representation is the single most important design decision in the entire system. Everything flows through it. If it's too rigid, new inputs/outputs are hard to add. If it's too loose, translations are ambiguous. If it's missing information, outputs are lossy.

This schema design — the conceptual schema for the abstract component layer — is the next major problem to solve.

### Component Vocabulary Refinement (from library taxonomy research)

Cross-analysis of 10 major component libraries (shadcn, MUI, Ant Design, Radix, Bootstrap, Chakra, Mantine, Headless UI, Apple HIG, Google M3) revealed:

**Universal core (~15 types)**: Button, Checkbox, Dialog, Select, Tabs, Switch, Radio, Input, Progress, Alert, Tooltip, Slider, Accordion, Menu, Popover. These appear in ALL libraries and are the non-negotiable foundation.

**The right size is ~45-50 canonical types**, not 60. Component.gallery's list includes niche items that shouldn't be in the core.

**Organize by user intent** (Apple/Google model), not technical function (web library model):
- Actions — things users DO
- Selection & Input — things users CHOOSE or TYPE
- Content & Display — things users SEE
- Navigation — things users GO TO
- Feedback & Status — what the system TELLS users
- Containment & Overlay — HOW content APPEARS

**Layout primitives are separate** from component types. They're structural grammar (verbs), not content (nouns).

**Canonical types are behavioral concepts**, not visual implementations. A Toggle is "a binary choice control" — it maps to shadcn Switch, MUI Switch, SwiftUI Toggle, and Figma component instance. The type definition includes behavioral description, slot definitions, recognition heuristics, and library mappings.

Full details in `docs/t5-component-vocabulary-research.md`.

---

## Open Questions (Carried Forward)

These questions from the original T5 research remain open and are explicitly deferred:

1. **Corpus curation fidelity**: High accuracy is required (Matt's feedback). Exact pipeline for achieving this is deferred.

2. **External design system seeding**: Radix/shadcn/Material (structured, available) vs. scraping screenshots vs. ingesting from other Figma files — different extraction challenges. Deferred.

3. **Critique iteration budget**: Hard cap at 3 proposed. Exact stopping criteria TBD.

4. **Visual critique taste calibration**: Generic design principles (CRAP, Gestalt, WCAG) vs. user-written taste rules. Both are possible without a corpus. Deferred.

5. **Component vocabulary adaptation**: Which of the 60 types need modification for mobile? What mobile patterns are missing? Deferred to implementation.

6. **Decision tree schema**: Exact table structure for storing exploration sessions, decision nodes, alternatives, and critiques. Deferred to implementation.

7. **Compact DSL format**: The exact encoding format for the generation output (the compact spec that maps to Figma MCP calls). Research points toward CSS-like with constrained vocabulary. Exact design deferred.

8. **Taste model schema**: Exact storage format for distributions, quality weights, correlations, and compositional rules. Deferred.
