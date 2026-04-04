# T5 Delivery Plan — Incremental Build with Real Data Validation

> **Declarative Design is a bi-directional design compiler.** It parses UI from any source — Figma, code, screenshots, or plain English — into an abstract compositional IR, then generates to any target: Figma with real variable bindings, React, SwiftUI, or HTML. Every color, every spacing value, every font is bound to your design tokens. Not probabilistic. Not approximate. Compiler-grade fidelity, from any input to any output.

Compiled 2026-04-01. This document defines the phased delivery plan for T5, building from the existing T1-T4 infrastructure toward the full Pattern Language + IR architecture. Each phase is independently testable with real data (the Dank file). Each proves a specific architectural assumption before investing in the next layer.

---

## Guiding Principle

**Big architectural vision, granular delivery. Test incrementally with real data to see what breaks.** This is the same approach used for T1-T4: real files, real tokens, real bindings. Every phase produces artifacts that can be inspected, validated, and corrected by a human before proceeding.

---

## What Exists (T1-T4, Proven)

A complete property-level pipeline, end-to-end tested on the Dank file:

- **Extraction**: Figma → SQLite (182K nodes, 86K unique, 338 screens, 22 extended property columns)
- **Clustering**: Color (OKLCH ΔE), typography, spacing, effects, radius, opacity
- **Curation**: Rename, merge, split, alias, create collections (388 tokens, 8 collections)
- **Mode derivation**: Dark, compact, high-contrast (OKLCH transforms, alpha-baked colors)
- **Push**: DB → Figma variables (374 variables) + rebinding (182K bindings, PROXY_EXECUTE)
- **Export**: CSS custom properties, Tailwind config, DTCG JSON
- **Infrastructure**: Value provenance + history, 753 tests passing

The system understands **what everything LOOKS LIKE**. It does NOT understand **what everything IS**.

---

## What We're Building (T5, Designed But Not Built)

A compositional layer that adds understanding of structure, composition, and intent on top of the existing property layer:

- **Component Vocabulary**: ~45-50 canonical UI types (the nouns)
- **IR (Intermediate Representation)**: Abstract component layer — flat element map with layout, tokens, slots (the hub)
- **Pattern Language**: Multi-level compositional descent — skeleton → elaboration → styling → critique (the method)
- **Compositional Analysis**: Bridge from Figma nodes → IR (understanding what things ARE)
- **Classification Cascade**: Formal → heuristic → grammar → LLM → vision (identifying component types)
- **Critique Cascade**: Rule-based → structural → visual (evaluating composition quality)
- **Taste Model**: Quality-weighted distributions from analyzed screens (informing choices)
- **Decision Tree**: Exploration history as first-class data (non-destructive design)
- **Hub-and-Spoke**: Any input → IR → any output (universal translation)

---

## The Phases

### Phase 0: Seed the Catalog

**What we build**: Define the ~45-50 canonical component types with props, slots, aliases, categories, and recognition heuristics. Store in a `component_type_catalog` table in the DB.

**Sources for the catalog**:
- Component.gallery's 60 types (filtered to ~45-50, removing niche items)
- Cross-referenced against 10 major component libraries (shadcn, MUI, Ant, Radix, Bootstrap, Chakra, Mantine, Headless UI, Apple HIG, Google M3) — see `docs/t5-component-vocabulary-research.md`
- Organized by user intent (Actions, Selection & Input, Content & Display, Navigation, Feedback & Status, Containment & Overlay) following Apple HIG / Google M3 model

**Each type definition includes**:
- Canonical name + aliases (e.g., Toggle = Switch, Lightswitch)
- Category (which user-intent group)
- Behavioral description (what it does, not what it looks like)
- Prop definitions with types (boolean, text, enum, slot, etc.)
- Slot definitions (named insertion points with allowed types)
- Semantic role (heading, button, input, link, image, etc.)
- Recognition heuristics (structural patterns for identifying this type in a Figma node tree)
- Related types (e.g., Button → Button Group, Toggle → Checkbox)

**Test**: Query the catalog. "What types exist? What are a Card's slots? What aliases resolve to Toggle? What are the recognition heuristics for a Header?" Pure DB verification. No Figma, no LLM.

**Proves**: The vocabulary is coherent, complete enough for the Dank file's components, and has sufficient detail for the classification cascade.

**Size**: ~1-2 days. Mostly definition work, informed by the research already completed.

---

### Phase 1: Classify Real Screens (The Critical Gate)

**What we build**: The classification cascade, run against all 338 screens in the Dank file. Populates `screen_skeletons` and `screen_component_instances` tables. Includes a self-validation loop using vision as a cross-check.

**Why this is the riskiest and most important phase**: If classification accuracy is <80%, the entire compositional architecture needs rethinking before we invest in generators, the Pattern Language, or any downstream work. If it's >90%, the architecture is validated and everything downstream is viable.

#### Step 1: Formal Component Matching (Free, Exact)

Nodes with `component_key` (populated during T4.6 extraction) get looked up against the canonical type catalog + aliases. This handles all formal Figma component instances.

**What this catches**: Every node that IS a declared Figma component instance. Cross-reference the component name against the ~45-50 canonical types and their aliases. E.g., a Figma component named "Toggle/Default" matches canonical type "Toggle."

**Expected coverage**: 60-80% of component instances in the Dank file, depending on how thoroughly the designer used formal components. This is the free, zero-error baseline.

**Implementation**: SQL join between `nodes.component_key` → `components.name` → pattern match against `component_type_catalog.canonical_name` and `component_type_catalog.aliases`.

#### Step 2: Structural Heuristics + Text Content (Free, ~85-90%)

For nodes NOT matched in Step 1, apply structural pattern matching using the recognition heuristics defined in the catalog.

**What this uses**:
- **Position/size rules**: Fixed-height frame at top of screen = Header (Alibaba proved near-perfect accuracy for positional roles). Fixed-height row at bottom with icons = BottomNav.
- **Text content matching**: Node containing "Submit" or "Save" → likely Button. Date patterns → likely DatePicker. Tab-like labels → TabBar.
- **Auto-layout analysis**: Horizontal row with text-left + toggle-right → ToggleRow. Vertical stack with image-top + text nodes + button row → Card.
- **Design grammar matching**: Production rules like `Card → Image? Title Subtitle? ActionRow?` matched against subtree structure.
- **Child count and types**: A frame with 3-5 equally-sized children in a row → SegmentedControl or TabBar.

**Why Figma data is richer than any benchmark**: CLAY achieved 85.9% F1 on noisy Android view hierarchies. We have component keys, auto-layout properties with direction/sizing/alignment, semantic layer names chosen by the designer, full visual property data, and instance override information. Our structural classification should exceed CLAY's baseline.

**Implementation**: A cascade of heuristic functions, each checking specific structural patterns against the recognition hints stored in `component_type_catalog`. Confidence scores attached to each classification.

#### Step 3: LLM Classification Fallback (Cheap, ~90%+)

For nodes that remain unclassified or have low confidence from Step 2, send a compact subtree description to Haiku and ask: "Which of these 45 canonical component types does this subtree most closely match?"

**What gets sent to the LLM**: A compact representation of the subtree — node types, child count, text content, layout direction, key visual properties. NOT the full 40-column node data. Estimated ~500-1,000 tokens per classification.

**Cost**: ~$0.01-0.02 per screen (15-20 classifications per screen × ~500 tokens each at Haiku pricing). For 338 screens ≈ $3-7 total. Run once, cache permanently.

**Implementation**: Prompt with the 45 canonical types as the classification vocabulary. The LLM picks the best match or responds "none" for truly novel components.

#### Step 4: Vision Cross-Validation (Self-Critique Loop)

**This is the key innovation for Phase 1.** Since we have BOTH the structural data AND the ability to render screenshots from the same Figma file, we use them against each other to self-validate.

**How it works**:

For each classified component instance from Steps 1-3:
1. **Render a screenshot** of that specific subtree using `figma_capture_screenshot` on the component instance's root node
2. **Run vision classification** on the cropped screenshot — send to Sonnet/Haiku with the 45 canonical types as the classification vocabulary: "Looking at this screenshot of a UI component, which of these types is it?"
3. **Compare** structural classification vs. vision classification

**Three outcomes**:
- **Both agree** → High confidence. Auto-accepted. No human review needed.
- **Disagree** → Flagged for human review. Both classifications presented with reasoning.
- **Neither confident** → Flagged as potential novel component type.

**Why this works**: The structural classifier and the vision classifier have DIFFERENT failure modes. Structural fails on unusual node arrangements that visually look standard. Vision fails on custom-styled components that structurally follow standard patterns. When both agree, the probability of error is very low (errors are multiplicative, not additive).

**Cost**: Vision classification is ~500-1,000 tokens per component crop at Haiku pricing. For 338 screens with ~15-20 components each ≈ 5,000-7,000 classifications ≈ $5-7 total. Trivial for the accuracy improvement.

**Side effect**: This builds a **labeled dataset from the Dank file itself**. Every instance you confirm becomes ground truth. Over time, this dataset can be used to fine-tune the structural heuristics or even train a custom classifier if needed.

#### Step 5: Human Review of Disagreements

You review the flagged disagreements (~10-20% of total instances, estimated). For each:
- Confirm one of the two classifications is correct
- Correct to a different type if both are wrong
- Mark as "novel" if it doesn't fit any canonical type (this informs whether we need to add types)

**What you're reviewing**: A side-by-side view showing: the component screenshot, the structural classification + confidence + reasoning, the vision classification + confidence + reasoning, and the node's structural data (name, type, children, properties).

#### Step 6: Skeleton Extraction

After component instances are classified, extract the screen-level skeleton — the abstract structural arrangement.

**How it works**: Look at the top-level children of each screen frame. Group them into structural zones (header, content, navigation). Express the arrangement as a compact skeleton notation: `stack(header, scroll(section-group(3)), bottom-nav)`.

**This uses the same classification data** — if we've identified a Header component at the top and a BottomNav at the bottom, the skeleton writes itself. The content zone is everything in between.

#### Step 7: Accuracy Measurement and Decision

After all 338 screens are classified and you've reviewed the disagreements:
- Measure overall accuracy (what percentage of your corrections changed the classification)
- Measure per-step accuracy (how much did formal matching catch? heuristics? LLM? where did vision help?)
- Identify systematic failure patterns (are certain component types consistently misclassified?)

**Decision gate**:
- **>90% accuracy**: Architecture validated. Proceed to Phase 2.
- **80-90% accuracy**: Review failure patterns. Tune heuristics. Re-run on problem areas. Likely proceed.
- **<80% accuracy**: Stop. Rethink the approach. Consider whether the catalog types are wrong, the heuristics are insufficient, or the Dank file has patterns that don't match the canonical vocabulary.

#### Output of Phase 1

- `screen_skeletons` table populated for 338 screens
- `screen_component_instances` table populated with all classified instances
- Accuracy metrics documenting classifier performance
- A labeled dataset of ~5,000-7,000 component instances with confirmed types
- Systematic failure patterns documented for heuristic improvement

**Proves**: We can look at a real Figma file and understand what everything IS, not just what it looks like. The compositional analysis layer works.

**Size**: ~3-5 days. The heuristics are the bulk of the work. The vision cross-validation and LLM fallback are straightforward API calls.

---

### Phase 2: Generate IR from Classified Data

**What we build**: A function that takes a classified screen (skeleton + component instances + token bindings from existing `node_token_bindings`) and produces a `CompositionSpec` JSON — the IR format defined in `docs/t5-ir-design.md`.

**How it works**:
1. Read the screen's skeleton from `screen_skeletons`
2. Read all component instances from `screen_component_instances`
3. For each instance, read the relevant node properties and token bindings from existing tables
4. Map to the IR format: type (from catalog), props (from node properties + instance overrides), children (from instance hierarchy), layout (from auto-layout properties), style (token references from node_token_bindings)
5. Output a flat-map `CompositionSpec` JSON

**Test**: Generate IR for 5-10 screens across different screen types (settings, list, detail, component sheet, etc.). Review the IR manually:
- Does the structure match the visual screen?
- Are component types correct?
- Are slot assignments accurate?
- Are token references present and correct?
- Is the layout model (direction, gap, padding) faithful to the Figma auto-layout?
- Is anything important missing?

**This is where we discover IR schema gaps.** If the IR can't represent something important in the Dank file, we learn it here before building generators.

**Proves**: The IR format can capture real design compositions without losing important information. The bridge from Figma-specific `nodes` data to abstract `elements` works.

**Size**: ~2-3 days. Mostly mapping existing data to the new format.

---

### Phase 3: Round-Trip Proof (The Acid Test)

**What we build**: A Figma generator that reads a `CompositionSpec` JSON and produces Figma frames with auto-layout, component instances (using `component_key` + `importComponentByKeyAsync`), and variable bindings (using the existing rebind infrastructure).

**How it works**:
1. Read the IR's root element and walk the element tree
2. For each element, create a Figma frame with the specified layout (direction, gap, padding, sizing)
3. If the element type maps to a known Figma component (via `component_key`), instantiate it
4. Apply style overrides via token references → variable bindings (reusing `export_rebind.py` machinery)
5. Nest children according to the IR's children/slots arrays

**Test**: Take the IR generated in Phase 2 (from an EXISTING Dank file screen). Generate a NEW screen from it in a test page in Figma. Compare side-by-side with the original screen.
- How close is the visual match?
- What's lost in translation?
- Are variable bindings present and correct?
- Does auto-layout behavior match?
- What breaks?

**This is the acid test for the entire architecture.** If parse → IR → generate produces something recognizable and faithful, then:
- The IR schema is validated (complete enough for round-trip)
- The compositional analysis captures enough information
- The Figma generator can produce real output
- Everything downstream (Pattern Language, code generation) is viable

**Start simple**: Begin with the simplest screen in the Dank file (fewest components, simplest layout). Get that working perfectly. Then try progressively more complex screens.

**Proves**: Bidirectional works. The IR is not just a storage format — it's a generative specification.

**Size**: ~5-7 days. The Figma generator is the most complex new code, but it reuses existing MCP and rebinding infrastructure.

---

### Phase 4: Generate from Prompt (Pattern Language MVP)

**What we build**: A minimal Pattern Language descent: prompt → skeleton selection → elaboration → token application → IR → Figma generation.

**How it works**:
1. **L0 Intent**: Parse the user prompt ("Build me a settings page for this iOS app")
2. **L1 Skeleton**: Query the classified data from Phase 1 — "what do settings screens in the Dank file look like?" Use the distribution of existing skeletons to select 2-3 options (e.g., 78% grouped-sections, 15% flat-list, 7% tabbed)
3. **L2 Elaboration**: For the chosen skeleton, query component instances from Phase 1 — "what components appear inside settings sections?" Generate internal compositions for each section.
4. **L3 Styling**: Apply tokens from the project's token vocabulary. This is mostly deterministic — map component slots to appropriate tokens based on the component type and semantic role.
5. **L4 Output**: Produce a `CompositionSpec` (IR) and feed to the Figma generator from Phase 3.

**Test**: "Build me a settings page." The system uses distributions from the Dank file's own settings screens, generates an IR, renders to Figma. You evaluate:
- Is it a reasonable settings page?
- Does it use the right component types?
- Are tokens applied correctly?
- Is the layout sensible?
- Does it look like something that belongs in the Dank file?

**The taste model at this stage is simple**: just frequency distributions from Phase 1's classification data. No external corpus, no quality weighting. That comes later. The goal is to prove the descent process works end-to-end.

**Proves**: The full conjure loop works. Prompt in → fully resolved Figma screen out, with actual variable bindings. The Pattern Language is not theoretical — it produces real output.

**Size**: ~5-7 days. The descent logic + prompt engineering.

---

### Phase 5: Critique Cascade

**What we build**: Three of four critique levels:
- **L1 System** (deterministic, free): Check that all elements have token bindings (no hardcoded values), all required slots are filled, all component types are from the catalog
- **L4 Accessibility** (deterministic, free): Compute WCAG contrast ratios from resolved token values, check touch target sizes against spacing tokens, verify semantic roles are present
- **L2 Structural** (Haiku, cheap): "Given this IR for a settings screen, does the layout follow good design hierarchy? Is the spacing consistent? Are interactive elements accessible?"

L3 Visual (Sonnet + screenshot) deferred to after the critique foundation is proven.

**Test**: Run critique on outputs from Phase 3 (round-trip) and Phase 4 (generated). Evaluate:
- Does L1 catch missing token bindings?
- Does L4 catch contrast violations?
- Does L2 catch layout logic problems?
- Are the structured critique outputs (JSON with affected_nodes + suggested_fix) actionable?
- What's the false positive rate? (Things flagged that aren't actually problems)

**The refine loop**: When critique identifies issues, feed them back to the generator. Can it fix them with a targeted adjustment (re-enter at the affected level) rather than full regeneration?

**Proves**: The evaluation layer works and improves generation quality. The generate → critique → refine loop converges.

**Size**: ~3-5 days. L1/L4 are deterministic code. L2 is an LLM prompt with structured output.

---

### Phase 6: Code Generation (Hub-and-Spoke Proof)

**What we build**: A React + shadcn renderer that reads a `CompositionSpec` and produces React component code with imports, props, Tailwind classes, and CSS variable references for tokens.

**How it works**:
1. Walk the IR element map from root
2. For each element, map its canonical type to the shadcn component (Toggle → `<Switch />`, Card → `<Card />`, Button → `<Button />`)
3. Map props from IR prop names to shadcn prop names
4. Map token references to CSS variable references or Tailwind classes
5. Generate layout using Tailwind flex utilities (direction, gap, padding)
6. Output a complete React component file with imports

**Test**: Take an IR from Phase 2 (extracted from Dank file) or Phase 4 (generated from prompt). Generate React + shadcn code. Run it in a Next.js project with shadcn installed. Does it render? Does it look right? Compare to the Figma output from the same IR.

**Proves**: The IR truly is format-agnostic. One representation, two faithful outputs (Figma + React). The hub-and-spoke model works. Adding a new output target is just adding a renderer.

**Size**: ~3-5 days. The renderer is a template-based translation. shadcn has clean, well-documented component APIs.

---

## Risk Profile

| Phase | Risk Level | Key Risk | Mitigation |
|-------|-----------|----------|------------|
| 0: Catalog | Low | Types may be incomplete for Dank file | You validate against real components in the file |
| **1: Classify** | **HIGH** | **Classification accuracy unknown** | **Vision cross-validation catches errors. You review disagreements. Accuracy measured before proceeding. Hard gate at 80%.** |
| 2: IR generation | Medium | IR schema may be incomplete | Manual review of IR output reveals gaps early |
| 3: Round-trip | Medium | Figma generation complexity | Reuses existing MCP infrastructure. Start with simplest screens. |
| 4: Prompt generation | Medium | LLM composition quality | Constrained to Dank file's own patterns. Start with one screen type. |
| 5: Critique | Low | False positive rate | L1/L4 are deterministic. L2 is tunable via prompt. |
| 6: Code gen | Low | Template translation | shadcn has clear APIs. Well-understood problem. |

**Phase 1 is the critical gate.** Everything downstream depends on classification working on real data.

---

## Timeline

| Phase | Duration | Cumulative | Dependency |
|-------|----------|-----------|------------|
| 0: Catalog | 1-2 days | 1-2 days | None |
| 1: Classify | 3-5 days | 4-7 days | Phase 0 |
| 2: IR from data | 2-3 days | 6-10 days | Phase 1 |
| 3: Round-trip | 5-7 days | 11-17 days | Phase 2 |
| 4: Prompt gen | 5-7 days | 16-24 days | Phase 1 + 3 |
| 5: Critique | 3-5 days | 19-29 days | Phase 3 or 4 |
| 6: Code gen | 3-5 days | 22-34 days | Phase 2 |

Phases 4, 5, and 6 are partially parallelizable — they all depend on the IR (Phase 2) and Figma generator (Phase 3) but not on each other.

**Roughly 1-1.5 months to go from catalog seed to proven hub-and-spoke** with Figma + React output from the same IR, including critique loop. Each phase is a checkpoint with real data validation.

---

## Later Phases (Not Yet Scheduled)

These build on the foundation above but are not part of the initial delivery:

- **Autonomous exploration**: Generate multiple options (3 skeletons → 2 elaborations each), critique all, present top 2-3 to user
- **User steering**: Parse feedback ("I like B's layout but tighter spacing") → re-enter Pattern Language at the right level
- **Decision tree storage**: Persist exploration sessions, decision nodes, alternatives, and critiques in DB
- **Taste model from corpus**: Ingest external screenshots, decompose, derive quality-weighted distributions
- **Additional generators**: SwiftUI, Flutter, HTML + Tailwind
- **Additional parsers**: React code → IR (reverse of Phase 6), screenshot → IR (reverse of Phase 1 vision step)
- **Self-play experimentation**: Autonomous generation + critique to improve taste model distributions
- **Framework migration**: React+MUI → IR → React+shadcn (combining parser + generator)
- **Design system migration**: Figma file A → IR → remap tokens → Figma file B

---

## Relationship to Existing Documentation

| Document | What it covers | How this plan uses it |
|----------|---------------|----------------------|
| `t5-pattern-language.md` | The Pattern Language concept — 5 levels, designer process | Phase 4 implements this |
| `t5-ir-design.md` | IR schema — flat element map, layout model, prop/slot model, resolved decisions | Phases 2-6 all implement parts of this |
| `t5-ir-diagrams.md` | Visual architecture diagrams | Reference throughout |
| `t5-compositional-analysis.md` | The missing layer — properties vs. composition gap | Phase 1 implements this |
| `t5-classification-research.md` | All classification approaches — structural, vision, hybrid, plugins, models | Phase 1 uses these findings |
| `t5-architecture-vision.md` | Full architecture — exploration, critique, taste, distribution, terminology | The north star for all phases |
| `t5-component-vocabulary-research.md` | Library taxonomy comparison, universal core, categorization | Phase 0 uses this |
| `t5-anima-deep-dive.md` | How Anima's component detection works | Informs Phase 1 heuristic design |
| `t5-research-round2.md` | Design encoding, critique loops, efficiency | Informs Phases 4-5 |
| `t5-generation-efficiency.md` | Cost/performance numbers | Informs budgeting for all phases |
| `t5-bidirectional-ui-research.md` | Shared analysis/generation models | Informs Phase 3 round-trip design |
| `t5-vision-classification-research.md` | Vision models for classification | Informs Phase 1 vision step |
| `research-universal-ui-ir.md` | Universal IR research — Mitosis, json-render, A2UI, Yoga, DTCG | Informs IR schema design |
