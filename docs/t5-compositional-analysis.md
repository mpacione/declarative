# T5 Compositional Analysis — The Missing Layer

Captured from conversation 2026-03-31. This document identifies the fundamental gap between the existing extraction architecture (which captures design as properties) and the Pattern Language (which needs design as composition). It defines the compositional analysis layer that bridges them.

---

## The Insight

The existing Declarative Design pipeline is an exceptional **recorder** of design. It captures every node, every visual property, every token binding with pixel-perfect fidelity. 182K nodes, 388 tokens, 22 new extended property columns. The extraction is exhaustive at the property level.

But the Pattern Language operates at a higher level of abstraction — composition. It needs to know:
- "This screen is a stack of: header, scrollable-sections(3), bottom-nav" (Level 1 — Skeleton)
- "Each section contains: heading, [toggle-row(label, subtitle, toggle)]" (Level 2 — Elaboration)

The existing DB doesn't capture this. It has the raw node tree with parent-child relationships and every visual property, but there's no layer that says "these 47 nodes collectively constitute a 'grouped-sections settings screen'" or "this subtree is a Card component with image-top, title, subtitle, and action-row slots."

**The system captures the LETTERS of design. It doesn't identify the WORDS, SENTENCES, or PARAGRAPHS.**

---

## What the Existing System Captures vs. What the Pattern Language Needs

### What exists (Level 3 and below — Properties)

| Table | What it captures | What it DOESN'T capture |
|-------|-----------------|------------------------|
| `screens` | Screen name, dimensions, device_class, node_count | What the screen is MADE OF — its compositional structure |
| `nodes` | 40+ property columns (fills, strokes, typography, layout), parent_id, path, depth | Semantic role ("this node is a Header"), component classification ("this subtree is a Card") |
| `node_token_bindings` | Every property→token binding (182K bound) | Which bindings belong to which semantic component |
| `components` | Formal Figma component definitions (name, key, variant_axes) | Informal patterns — a group of nodes that IS a card but isn't a formal Figma component |
| `component_slots` | Schema exists for named insertion points per component | **Empty** — nothing populates it |
| `component_a11y` | Schema exists for accessibility contracts per component | **Empty** — nothing populates it |
| `instance_overrides` | What properties an INSTANCE node has overridden | The canonical composition of the component being instantiated |

### What the Pattern Language needs (Levels 1-2 — Composition)

**Level 1 — Skeleton**: The abstract structural arrangement of a screen. Which high-level component types, in what layout structure?

Example: `stack(fixed-header, scroll(section-group(3, toggle-rows)), bottom-nav)`

This requires:
- Identifying the top-level structural zones of a screen (header zone, content zone, navigation zone)
- Classifying each zone by its role and layout type
- Expressing the arrangement as a compact structural notation

**Level 2 — Elaboration**: The internal composition of each component instance. What slots does it have? What fills each slot?

Example: `toggle-row: { label: text("Notifications"), subtitle: text("Get push notifications"), control: toggle(bound: true) }`

This requires:
- Recognizing component instances in the node tree (both formal Figma components AND informal recurring patterns)
- Classifying each instance against the 60 canonical component types
- Decomposing each instance into its constituent slots
- Identifying what content/elements fill each slot

---

## The Gap Is an Analysis Layer

The existing pipeline goes:

```
Figma File → [Extract] → Raw Nodes + Properties + Bindings
                              ↓
                         [Cluster] → Tokens
                              ↓
                         [Curate] → Named, Organized Tokens
                              ↓
                         [Push] → Figma Variables + Rebinding
```

Every step operates on PROPERTIES. Compositional structure is invisible.

The Pattern Language implies a new analysis layer:

```
Figma File → [Extract] → Raw Nodes + Properties + Bindings
                              ↓
                    ✦ [Analyze] → Compositional Structure ✦
                    ✦   Screen skeletons (L1)              ✦
                    ✦   Component instances + slots (L2)   ✦
                    ✦   Pattern recognition                ✦
                              ↓
                         [Cluster] → Tokens
                              ↓
                         [Curate] → Named, Organized Tokens
                              ↓
                         [Push] → Figma Variables + Rebinding
```

### The Analysis Layer Is Bidirectional

This is the key architectural insight: the compositional model works in BOTH directions.

**Forward (extraction/analysis)**: Given raw nodes → identify skeleton + component instances + slots. This was originally conceived as T5.12 (Pattern Extraction) — a standalone T5 action. But it's actually a core pipeline step that should run during or immediately after extraction.

**Backward (generation)**: Given skeleton + component instances + slots → produce nodes in Figma with token bindings. This is T5.9 (Compose Screen). It's the exact reverse operation.

**The same compositional model serves both directions.** You don't build extraction and generation as separate systems — you build one compositional model that reads in both directions. The data structure that records "this screen has this skeleton and these component instances" is the same structure that a generation engine reads to produce a new screen.

---

## Proposed Schema Additions

The existing tables DON'T need to change. They're the raw material — the Level 3 foundation. What's needed is ADDITIONAL tables that derive higher-order structure from the raw node tree.

### component_type_catalog (The 60 Canonical Types)

Seeds the system with the universal component vocabulary from component.gallery.

```
component_type_catalog:
  id                  INTEGER PRIMARY KEY
  canonical_name      TEXT NOT NULL UNIQUE    -- "accordion", "card", "toggle", etc.
  aliases             TEXT                    -- JSON array: ["collapse", "disclosure", "expandable"]
  category            TEXT                    -- "input", "display", "navigation", "feedback", "layout"
  slot_definitions    TEXT                    -- JSON: canonical slots this type typically has
  related_types       TEXT                    -- JSON array of related canonical type names
  description         TEXT                    -- What this component type IS (one sentence)
  recognition_hints   TEXT                    -- JSON: structural heuristics for identifying this type
                                             --   in a raw node tree (layout patterns, child counts,
                                             --   typical property combinations)
```

### screen_skeletons (Level 1 — Structural Arrangement)

Captures the abstract skeletal structure of each screen.

```
screen_skeletons:
  id                  INTEGER PRIMARY KEY
  screen_id           INTEGER NOT NULL REFERENCES screens(id)
  skeleton_notation   TEXT NOT NULL           -- compact tree notation:
                                             --   "stack(header, scroll(section-group(3)), bottom-nav)"
  skeleton_type       TEXT                    -- broad classification: "settings", "list-detail",
                                             --   "dashboard", "form", "onboarding", etc.
  platform_context    TEXT                    -- "ios", "android", "web", "tablet"
  zone_map            TEXT                    -- JSON: maps skeleton zones to node ranges
                                             --   {"header": {"root_node_id": "2219:235700", ...},
                                             --    "content": {"root_node_id": "2219:235710", ...}}
  confidence          REAL                    -- 0-1, how reliably the analysis identified this
  analysis_method     TEXT                    -- "formal_component" | "structural_heuristic" | "llm_classification"
  analyzed_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
```

### screen_component_instances (Level 2 — Component Recognition)

Identifies component instances within each screen — both formal Figma components and informal structural patterns.

```
screen_component_instances:
  id                      INTEGER PRIMARY KEY
  screen_id               INTEGER NOT NULL REFERENCES screens(id)
  canonical_type_id        INTEGER REFERENCES component_type_catalog(id)
  canonical_type_name      TEXT NOT NULL        -- "card", "toggle", "header", etc.
  root_node_id            TEXT NOT NULL         -- the figma_node_id of the subtree root
  parent_instance_id      INTEGER REFERENCES screen_component_instances(id)
                                               -- for nested components (a Card inside a List)
  skeleton_zone           TEXT                  -- which zone of the screen skeleton this sits in
  slot_assignments        TEXT                  -- JSON: which child nodes fill which slots
                                               --   {"image": "2219:235720",
                                               --    "title": "2219:235725",
                                               --    "action_row": ["2219:235730", "2219:235731"]}
  source                  TEXT NOT NULL         -- "formal_component" (has component_key) |
                                               --   "structural_match" (heuristic) |
                                               --   "llm_classified"
  figma_component_key     TEXT                  -- if this is a formal Figma component instance
  confidence              REAL                  -- 0-1
  analyzed_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
```

### Relationship to Existing Tables

```
screens (existing)
  └── screen_skeletons (NEW, 1:1 with screens)
        └── screen_component_instances (NEW, many per screen)
              ├── references → component_type_catalog (NEW)
              ├── references → nodes (existing, via root_node_id)
              └── self-referential parent_instance_id for nesting

component_type_catalog (NEW, universal)
  └── provides recognition vocabulary for the analysis pass
  └── provides slot definitions for generation
  └── seeded from component.gallery's 60 types
```

---

## The Classification Problem

The hardest challenge in the analysis layer: how does the system look at a subtree of nodes and determine "this is a Card" or "this is a Toggle row"?

### Three Approaches (Likely Used in Combination)

**1. Formal Component Matching (Free, Exact)**

If a node has a `component_key` (populated during T4.6 extraction), you already know what it is. The existing `components` table and `instance_overrides` table handle this. Cross-reference the component name against the 60 canonical types + aliases.

Coverage: Covers all formal Figma component instances. Does NOT cover informal patterns — nodes that form a recognizable component pattern but aren't formally defined as Figma components. In a well-structured design file, this might cover 60-80% of component instances. In a messy file, maybe 30-40%.

**2. Structural Pattern Matching (Free, ~70% Accurate)**

Heuristic rules that identify component patterns from node tree structure:
- "A vertical auto-layout frame containing an image node, text nodes, and a horizontal button row is probably a Card"
- "A horizontal auto-layout frame with a text node on the left and a boolean-type node on the right is probably a Toggle row"
- "A frame at the top of the screen with fixed height, containing a text node and possibly icon nodes, is probably a Header"

These heuristics operate on:
- Node type (FRAME, TEXT, INSTANCE, VECTOR, etc.)
- Layout properties (auto-layout direction, sizing mode, alignment)
- Child count and types
- Position within the screen (top = likely header, bottom = likely nav)
- Relative sizes and proportions

Coverage: Can identify common patterns but fails on unusual compositions, heavily nested structures, or designs that don't follow conventional patterns.

The `recognition_hints` field in `component_type_catalog` stores these heuristics per type, making them extensible and updatable.

**3. LLM Classification (Cheap Per Node, Most Robust)**

Feed a compact representation of the node subtree to a model and ask: "Which of these 60 canonical component types does this subtree most closely match? Or is it none of them?"

The compact representation would include:
- Node types and names in the subtree
- Layout properties (direction, alignment, sizing)
- Rough dimensions and proportions
- Number and types of children
- Token bindings (what styling is applied)

Using Haiku with the component vocabulary as context, this would cost ~500-1,000 tokens per classification. For a screen with ~15-20 component instances, that's ~10K-20K tokens total — maybe $0.01-0.02 per screen. Run once, cache forever.

### Proposed Classification Cascade

```
Step 1: Formal component matching (free, exact)
  → All nodes with component_key get classified immediately
  → ~60-80% coverage in well-structured files

Step 2: Structural heuristic matching (free, ~70% accurate)
  → Run recognition_hints from component_type_catalog against remaining unclassified subtrees
  → Flag low-confidence matches for Step 3

Step 3: LLM classification (cheap, ~90%+ accurate)
  → Only for unclassified or low-confidence subtrees
  → Feed compact subtree representation + the 60 canonical types
  → Store result with confidence score and source="llm_classified"

Total cost per screen: $0.01-0.02 (mostly from Step 3 on 20-40% of instances)
Run once during extraction, results cached permanently.
```

---

## Why This Changes the Build Sequence

The original T5 build sequence had Pattern Extraction (T5.12) as Phase 7 — late, after the generation engine was built. This was wrong.

**The compositional analysis IS the foundation.** Without it, the generation engine has no compositional data to work with. Without it, the taste model has nothing to derive distributions from. Without it, every screen is just a bag of 500 nodes with properties — useless for composition.

Revised build sequence:

```
Phase 1: Component vocabulary
  Seed component_type_catalog with 60 canonical types + aliases + slot definitions + recognition hints

Phase 2: Compositional analysis pass ← THIS IS THE NEW CRITICAL STEP
  Build the 3-stage classification cascade (formal → heuristic → LLM)
  Run it on all 338 existing screens in the Dank file
  Populate screen_skeletons and screen_component_instances
  This bootstraps the compositional data that everything else needs

Phase 3: Pattern Language engine
  Now has real compositional data to read from
  Can generate skeletons and elaborations grounded in actual analyzed screens

Phase 4: Compact DSL + Figma bridge
  ...

Phase 5: Critique cascade
  ...
```

The compositional analysis transforms "182K nodes with properties" into "338 screens with compositional structure" — which is what the Pattern Language engine actually needs to work with.

---

## The Bidirectional Payoff

Once the compositional model exists (the schema + the analysis pass), it pays off in both directions:

**Extraction direction (understanding existing designs)**:
- "Show me all screens that use a grouped-sections skeleton" → SQL query on screen_skeletons
- "Find all Card instances across the file and their slot structures" → SQL query on screen_component_instances
- "What percentage of screens have a bottom-nav?" → aggregate query
- Bootstraps the taste model with real distributions from analyzed screens

**Generation direction (composing new designs)**:
- "Compose a settings screen" → Pattern Language engine reads screen_skeletons to know what settings screens look like, reads screen_component_instances to know what components go inside them, reads token bindings to know how to style them
- The engine produces the same data structure that the analysis created — a skeleton + component instances + slot assignments — which then gets materialized to Figma nodes

**Feedback direction (improving over time)**:
- When the user steers a generated screen, the steering decision can update the compositional data
- When the autonomous experimentation mode generates and critiques screens, successful compositions add to the dataset
- The taste model's distributions get more accurate as more screens are analyzed or generated

---

## Relationship to T5.12 (Pattern Extraction)

T5.12 was originally defined as: "This card layout appears on 12 screens, save it as a pattern. Extract common structure into a composition template. Store in `patterns` table."

This is now reconceived as TWO things:

1. **Compositional analysis** (core pipeline step, runs on every screen): Identify skeleton + component instances + slots. Populate `screen_skeletons` and `screen_component_instances`. This is the foundational analysis.

2. **Pattern synthesis** (higher-order, runs across screens): Analyze the compositional data across ALL screens to find recurring patterns, derive distributions, and populate the taste model. "This card layout appears on 12 screens" is a QUERY against `screen_component_instances`, not a separate extraction step.

The first is a per-screen analysis. The second is a cross-screen synthesis. Both are needed, but the per-screen analysis must come first.

---

## Open Questions (To Be Researched)

1. **Classification accuracy**: How reliably can each method (formal matching, heuristics, LLM) classify component instances in real Figma files? What's the error rate? What are the failure modes?

2. **Skeleton identification**: How do you determine the screen-level skeleton from a raw node tree? The top-level children of a screen frame aren't always the structural zones — there may be background layers, decoration layers, overlays. How do you distinguish structural zones from decoration?

3. **Informal pattern recognition**: The hardest case is when a designer hasn't used formal components — just arranged frames, text, and shapes into a pattern that IS a card or toggle row but isn't declared as one. How well can heuristics + LLM handle this? Is there existing research on UI element recognition from structured view hierarchies (not screenshots)?

4. **Nesting depth**: Components nest — a Card inside a List inside a Section inside a Screen. How deep does the analysis need to go? Is there a practical depth limit?

5. **Cross-screen consistency**: The same informal pattern might look slightly different across screens (different padding, different child count). How do you determine "these are the same type of component" when they're not formal Figma components with a shared key?

6. **The recognition_hints format**: What's the right way to express structural heuristics? A DSL? JSON rules? Code? The format affects how extensible and maintainable the heuristic matching is.
