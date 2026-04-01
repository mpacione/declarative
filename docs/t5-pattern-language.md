# The Pattern Language — Core Concept

Captured from conversation 2026-03-31. This document defines the Pattern Language: the multi-level compositional descent process that is the central architectural idea for T5 Conjure.

---

## Origin

The Pattern Language concept emerged from mapping how a human designer (Matt) actually thinks about composing screens. The insight: designers don't work at a single level of abstraction. They work through a structured descent — starting with abstract component types ("I need a header, a list section, and a footer"), then elaborating each component's internal composition, then applying visual styling, then stepping back to critique the whole. This process has branching (explore multiple options at each level), pruning (discard weak options via critique), and re-entry (go back up the tree when something isn't working).

This maps directly to Christopher Alexander's 1977 "A Pattern Language" — a catalog of recurring solutions to design problems, each existing at a specific scale and connecting to patterns at adjacent scales. Alexander's patterns don't dictate specifics; they constrain the solution space at the right altitude. The 60 canonical UI component types (sourced from component.gallery's catalog of 2,676 implementations across 95 real design systems) are exactly this — patterns at the component scale, connecting downward to internal composition patterns and upward to screen-level arrangement patterns.

The key realization: **the Pattern Language is not a dataset, not a vocabulary, not a set of distributions. It is the compositional process itself — the method by which screens are composed through progressive descent across abstraction levels.**

---

## Definition

**Pattern Language** = the multi-level compositional descent process for composing design screens. It defines:

1. The abstraction levels a composition moves through
2. The branching and exploration at each level
3. The pruning via critique at each level
4. The re-entry points when steering or refining
5. The decision tree that records the path taken

Everything else — the component vocabulary, the token vocabulary, the taste model, the corpus — are inputs TO the Pattern Language. They feed into it at various levels. But the Pattern Language is the method of composition.

---

## The Five Levels

### Level 0 — Intent (Screen Brief)

What does this screen need to do? What problem does it solve? Who uses it? What content must it contain?

This is the input to the process. It may be a natural language prompt ("Build me a settings page for this iOS app"), a structured brief (screen type + platform + key requirements), or a reference ("Something like Linear's settings but with our design system").

**Output**: A screen specification that constrains all downstream levels.

### Level 1 — Skeleton (Structural Arrangement of Abstract Component Types)

Which abstract component types, in what structural arrangement? The designer thinks in Platonic forms here — a Card is a Card regardless of what it looks like. A Header is a Header. The question is: which forms, in what order, in what layout structure?

At this level, the vocabulary is ~60 canonical component types + ~7 layout primitives (stack, row, grid, overlay, scroll, etc.). The output space is tiny — maybe 200-500 tokens for a full screen skeleton. The system generates multiple skeleton options (typically 3) for exploration.

**Example output**:
```
Skeleton-A: stack(header, scroll(grouped-sections(3)), bottom-nav)
Skeleton-B: stack(header, flat-list(items), floating-action-button)
Skeleton-C: stack(header, tab-bar(3-tabs), tab-content, bottom-nav)
```

**Pruning**: Structural critique (cheap, Haiku-level) evaluates which skeletons are viable for the stated intent. A settings screen with 20+ options probably shouldn't use a flat list. The weakest skeleton is pruned.

### Level 2 — Elaboration (Internal Composition Per Component)

For each component in the chosen skeleton, what's the internal composition? There are usually a few canonical options per component type, and the choice depends on what the screen needs to communicate.

**Example**: For a "section" component within a grouped-sections settings skeleton:
```
Elaboration-1: section(heading, [toggle-row(label, subtitle, toggle)])
Elaboration-2: section(heading, [radio-group(label, options)])
Elaboration-3: section(heading, [card(icon, title, subtitle, chevron)])
```

This level also handles the relationships BETWEEN components — how the header relates to the content, how sections group logically, what the navigation affordance is.

**Pruning**: Structural critique evaluates whether the elaboration makes sense for the content. A notification preferences section probably needs toggles, not radio buttons. An account type selection needs radio buttons, not toggles.

### Level 3 — Styling (Token Application)

Now the token vocabulary enters. Colors, typefaces, spacing, radii, shadows. This step is largely deterministic — the designer is choosing FROM the vocabulary, not inventing values. Every value slot resolves to a real token in the DB.

This is where the Declarative Design DB vocabulary gets applied. The 388 tokens across 8 collections provide every possible value. The system cannot hallucinate a color or invent a spacing value. It can only reference what exists.

**This level has near-zero LLM cost** — it's a DB query that maps component slots to appropriate tokens based on the component type and semantic role.

### Level 4 — Holistic Critique

Step back. Does the whole thing solve the problem stated in Level 0? Is the visual hierarchy readable? Is the spacing balanced? Does it feel right? Does it meet accessibility requirements?

This is where the critique cascade runs (detailed in the architecture doc):
1. Rule-based validation (free, instant) — token coverage, contrast ratios, spacing consistency
2. Structural critique (cheap, Haiku) — layout logic, semantic grouping, hierarchy
3. Visual critique (expensive, vision model on screenshot) — only if rules and structural pass

Critique may loop back to any previous level:
- Fundamental layout problem → back to Level 1
- Component choice problem → back to Level 2
- Styling problem → back to Level 3 (cheapest fix)

### Level 5 — Refinement and Commitment

The designer looks at the resolved options side-by-side. They may:
- **Accept** one option as-is
- **Tweak** — make targeted adjustments at a specific level
- **Combine** — take the layout from option A, the component choices from option B, the spacing from option C
- **Restart** — go back to Level 1 with a different approach entirely

This is non-destructive. The decision tree preserves all explored paths. The designer can always go back and explore a branch they didn't take.

---

## The Decision Tree

The exploration across levels produces a tree structure:

```
Screen Brief: "Settings page for iOS app"
         │
    ┌────┼────────┐
    ▼    ▼        ▼
  Skel-A  Skel-B  Skel-C     ← Level 1: 3 skeleton options
  (grouped (flat   (tabbed
   sections) list)  sections)
    │
  ┌─┼──┐
  ▼ ▼  ▼
 E-1 E-2 E-3                 ← Level 2: elaborate chosen skeleton
 (toggle  (radio   (card-
  rows)   groups)   based)
    │
    ▼
  Styled                      ← Level 3: token application (deterministic)
    │
    ▼
  Critique                    ← Level 4: holistic evaluation
    │
  ┌─┼──┐
  ▼    ▼
 Tweak  Accept                ← Level 5: refine or commit
```

Each node in this tree is cheap to produce at Levels 1-2 (abstract, ~200-500 tokens). Cost is front-loaded where it's cheapest. Only the surviving options get materialized to Figma at Level 3+ (expensive MCP calls, screenshot, visual critique).

**The decision tree is a first-class data structure.** It should be stored, not just held in memory. Each node records:
- The level (skeleton / elaboration / styling)
- The choice made (which component types, which internal arrangement, which tokens)
- The alternatives considered and why they were pruned
- The critique results that influenced the choice
- Parent/child relationships to other decisions

This gives:
- **Non-destructive exploration** — go back and explore a path not taken
- **Design rationale** — "why does this screen look like this?" is answered by the decision tree
- **Learning** — over time, observe which decisions survive user steering and which get overridden (implicit taste data)

---

## Why This Is Different From Existing Approaches

### vs. Google Stitch
Stitch generates at a single level of abstraction — prompt → full output. It uses DESIGN.md as probabilistic guidance but has no structural descent, no branching, no compositional grammar. Colors drift from brand systems. Every generation "starts somewhat fresh."

### vs. SDUI (Airbnb/Netflix)
SDUI defines the component vocabulary and layout structure but has no generative layer — a human decides what goes where. It's a rendering framework, not a composition system.

### vs. Design Skills (Anthropic, OpenAI)
Design skills encode aesthetic principles and anti-patterns but produce HTML/CSS, not Figma-native output. They work at a single level — there's no descent through abstraction layers, no branching, no systematic exploration.

### vs. MLS (Modular Layout Synthesis)
MLS is the closest — it defines a formal IR with typed slots and a motif library. But it's framework-agnostic (outputs React/Vue/etc.), has no token vocabulary constraint, and doesn't model the multi-level descent. It's an encoding format, not a compositional process.

### What Declarative Design's Pattern Language adds:
1. **Multi-level descent with branching** — exploration at each level, pruning via critique
2. **Deterministic token binding** — every value resolves to a real DB token, not a hallucinated value
3. **Figma-native output** — actual variable bindings, not code
4. **Decision tree as data** — the design rationale is preserved and navigable
5. **Cost-efficient exploration** — abstract exploration is cheap, materialization happens late

---

## Relationship to Other System Components

| Component | What it is | How it feeds the Pattern Language |
|-----------|-----------|----------------------------------|
| Component Vocabulary | 60 canonical UI types (from component.gallery) | Provides the "nouns" at Levels 1-2 |
| Token Vocabulary | 388 DB tokens across 8 collections | Provides the "adjectives" at Level 3 |
| Taste Model | Quality-weighted distributions from curated corpus | Informs choices at Levels 1-2 (what's common, what's good, what's interesting) |
| Critique Cascade | Rule-based → structural → visual evaluation | Provides the pruning mechanism at Level 4 |
| Corpus | Raw curated screenshots + decompositions | Source material for deriving the taste model (never shipped, never used directly) |

The Pattern Language is the process. Everything else is an input to it.

---

## How Designers Actually Think (Matt's Process, Mapped)

Matt described his design process as:

1. Think about which abstract component types are needed, what structural arrangement makes sense. Consider options for this coarse abstract composition. **→ Level 1**

2. For each component, move down to think about what the composition INSIDE each component looks like at an abstracted level. There are usually a few options or idealized combinations depending on what the screen needs to do and the content it needs to have. Work through each of these until there are some good options. **→ Level 2**

3. Think about colors, typefaces, styling, sizing, spacing, radii, etc. **→ Level 3**

4. Step back and look at the whole. Does it solve what the screen needs to do? Does it look like it fits visually? Is it balanced? Does it have good hierarchy? Critique own work. **→ Level 4**

5. Make tweaks or sub-variations. Look at them all together and distill or combine down to a final screen. Do this non-destructively in case you want to go back and explore another approach further — like exploring a root system of possible design choices and paths. **→ Level 5**

The Pattern Language is a formalization of this natural design process. The system should work the way designers think.
