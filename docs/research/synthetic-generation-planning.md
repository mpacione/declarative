# Synthetic Screen Generation — Exploration and Planning

> **Status:** exploration phase, not yet implemented.
> **Audience:** anyone picking this up cold — a future Claude session, a contributor, a designer reviewing the plan.
> **Last updated:** 2026-04-16.

## What we're building

Synthetic screen generation is the next major phase after the round-trip
foundation. The goal: given a natural-language prompt (and eventually a
sketch, a screenshot, or a rough layout), produce a Figma file that a
designer would accept as a sensible starting point — using a specific
project's design system when one exists, graceful defaults when it
doesn't.

The naive framing is "have an LLM write Figma Plugin API JavaScript."
That produces invalid code, hallucinated APIs, and output that looks
like the public web rather than like the target design system. Every
serious tool in this space has moved past it.

Our framing is different: **the LLM produces IR, not scripts.** The
existing deterministic renderer (the one that now passes 204/204
parity on Dank Experimental) lowers valid IR to valid Figma. The
LLM's job shrinks accordingly — it emits a high-level semantic tree;
the compiler does the heavy structural lifting.

## Why now

The round-trip foundation just closed. We can extract a file into IR
losslessly, re-render it with zero drift, and verify parity at
node-level granularity via a structured-error channel. That's three
independent guarantees that reduce the synthesis problem to "can the
LLM produce plausible IR" rather than "can the LLM produce anything
at all that renders."

Several things came together externally around the same time:

- **DTCG stable spec landed** (October 2025). Cross-vendor token
  vocabulary is now a real, typed object. Adobe, Google, Microsoft,
  Figma, Shopify, Salesforce all signatories.
- **Agent Skills spec went cross-vendor** (December 2025). Anthropic
  and OpenAI both adopted SKILL.md. Composable, installable,
  distributable capabilities.
- **Vision models crossed a quality threshold**. Gemini 3.1 Pro is
  #1 on WebDev Arena. Qwen3-VL-235B open-weights competes with GPT-5
  on GUI grounding. Moondream 3 (2B active) does usable UI critique
  locally.
- **UICrit dataset** (UIST 2024) — 983 mobile UIs with 3,059 designer
  critiques, bounding-box regions. +55% reported improvement in LLM
  UI-feedback quality as few-shot. Nobody in the design-to-code tool
  space has used it.

The "should we do this now" question has a straightforward answer:
everything that gates the attempt is now in place.

## What already exists in the repo

Important to be honest about maturity before planning additions.

| Piece | State |
|---|---|
| `dd/prompt_parser.py` | Works end-to-end. Claude Haiku call with a 48-type system prompt. Output: JSON component list. |
| `dd/compose.py` | `compose_screen(component_list) → CompositionSpec`. Flat vertical stacking with spacing defaults. |
| `dd/catalog.py` | 48 canonical types with `slot_definitions`, `prop_definitions`, recognition heuristics. Rich metadata — almost none surfaced to the LLM. |
| `dd/templates.py` | `component_templates` table with extracted instance templates. `build_project_vocabulary()` does surface variant names + instance counts to the LLM. This is the one retrieval mechanism that's live. |
| `dd/extract_components.py` | Built but never run on the Dank corpus. Populates `component_variants`, `variant_axes`, `variant_dimension_values`, `component_slots`, `component_a11y`. |
| Capability gate (`dd/property_registry.py`) | Per-backend capability table on every property. Used at emission. Doubles as the grammar-constrained-decoding vocabulary (not yet wired). |
| Boundary contract (ADR-006) | Ingest side live. Egress side (synthetic IR validation) not yet. |
| Verification channel (ADR-007) | Live. `is_parity`, `KIND_*`, `RenderReport`. Runs post-render. |

**Maturity assessment:** probably ~40-50% of the plumbing for a
working v0.1 already exists. The biggest gaps aren't fundamental —
they're "the DB knows things that never reach the LLM."

## The research summary

### What production tools do

- **Anthropic's frontend-design SKILL** — single-shot, aesthetic
  injection via "pick an extreme direction" prompt. No critique loop.
  41 lines.
- **0xdesign/design-plugin** — 8-phase pipeline: detect framework,
  infer project style, interview, generate 5 variants on orthogonal
  design axes (hierarchy / layout / density / interaction /
  expression), render side-by-side, human-in-the-loop via browser
  overlay, synthesise a 6th. Ships with a 2140-line
  `DESIGN_PRINCIPLES.md`.
- **Pencil.dev** — infinite canvas, agents with visible cursors,
  `.pen` JSON IR in `/design`. Built-in UI kits (Shadcn, Lunaris,
  Halo, Nitro) as retrieval anchors. MCP protocol for parallel agents.
- **Paper.design** — real HTML/CSS. MCP tools expose screenshots as
  agent inputs. Agent decides placement strategy.
- **Google Stitch** — layout primitives → hierarchical tree →
  responsive grid mapping. Gemini 2.5 / 3 under the hood.
  Image-conditioned mode.
- **Anima** — Figma-first translator, not a generator.

### Key papers

- **GameUIAgent** (arXiv 2603.14724) — six-stage pipeline with a
  recursive Design Spec JSON IR, VLM Reflection Controller scoring
  5 dimensions (Layout / Consistency / Readability / Completeness /
  Aesthetics) at threshold θ=7.5, non-regressive best-result tracking,
  dimension-specific repair instructions. Closest published analogue
  to what we'd want.
- **ReLook** (arXiv 2510.11498) — RL-trained vision critic + strict
  acceptance rule (regenerations only accepted if they strictly
  exceed best prior score). Prevents the "overconfident self-correction
  makes it worse" failure mode. Uses temporal snapshots for render-
  time issues a text model misses.
- **SpecifyUI / SPEC** (arXiv 2509.07334) — hierarchical two-level IR,
  scoped edits at global / regional / component granularity,
  Co-DETR + Gestalt-principle merging for region segmentation. Edits
  as `<operation, path, value>` triplets, not regenerations.
- **Visual Prompting with Iterative Refinement** (arXiv 2412.16829) —
  six-LLM cascade for design critique with bounding boxes + zoomed
  patches. Separate LLMs for generation and refinement to prevent
  self-bias.
- **UI Grammar + LLM** (arXiv 2310.15455) — grammar of production
  rules `parent → [child, child, ...]` as LLM-prompt scaffolding.
  Direct prior art for our L3 framing.
- **AIDL** (arXiv 2502.09819) — solver-aided DSL in CAD. LLM emits
  soft geometric intent; Z3 resolves positions. Architecture transfers
  directly to UI.
- **Two-stage hybrid systems** (e.g. LayouSyn, CreatiLayout ICCV 2025)
  — LLM plans, neural layout model renders. **LLMs drop to 57%
  recall on layouts with >15 objects**; hybrid beats pure LLM by
  12–15% on layout fidelity.

### Corpora we could ingest

- **RICO → MUD** (runtime-mined Android). **CLAY** (59,555 denoised
  RICO UIs). **ENRICO** (1,460 topic-classified). All legitimate
  academic datasets.
- **WebSight v0.2** — 2M HTML/Tailwind screenshot pairs, CC-BY.
- **DesignBench** — 900 webpage samples × 3 frameworks (React / Vue /
  Angular) × generate / edit / repair semantics.
- **DTCG token files** from the big design systems: Material, Fluent,
  Carbon, Polaris, Lightning, Primer, Radix, shadcn, Geist, Base Web,
  Ant, Chakra, Mantine. All public GitHub.
- **UICrit** — 983 UIs with 3,059 designer critiques. The only
  publicly-available designer-preference dataset we found.

Two-person-weeks to build an aggregated "default knowledge" corpus
across these. Nobody's done it yet.

## Key reframings from research

Five findings that actually changed the plan, ranked by architectural
impact:

### 1. Mono-Claude is a latent risk

Generator and critic in the same model family share blind spots.
Every recent paper with strong results uses cross-family pipelines.

**Decision implication:** critic is a different model from generator.
Probably Gemini 3.1 Pro for the primary critic. Claude for generation.
Moondream 3 as a cheap local gate before escalating.

### 2. DTCG is the L2 vocabulary

The stable spec (Oct 2025) is typed, cross-vendor, and adopted. Any
MLIR-style design compiler that doesn't base L2 on DTCG token
semantics is building on sand.

**Decision implication:** our existing tokens table should be
DTCG-compatible. Export goes through DTCG. Synthesis reads DTCG.
This is a quiet refactor, not a new system.

### 3. UICrit exists and nobody's using it

The +55% reported improvement from few-shot UICrit in the critic
prompt is free lunch. No one in the production tool space has built
on it. Critique-dataset is the unoccupied territory, not generation.

**Decision implication:** UICrit few-shot in the critic prompt on
day one. Cheap, high-leverage.

### 4. Skills are the distribution model

Cross-vendor SKILL.md spec + Figma's own skills shipping means "a
CLI that talks to Claude" is the wrong shape. "An installable skill
that any Claude Code / Codex user can chain with Figma's skills"
is the right shape.

**Decision implication:** split our surface into four skills —
`extract-figma`, `verify`, `design-md`, `generate`. Each wraps the
existing CLI. Discoverability + composition for free.

### 5. Our 5-variant plan is a degenerate genetic algorithm

Variants = population. Critic scores = fitness. LLM-with-fresh-
temperature = mutation operator. The missing pieces are crossover
(synthesise from two parents) and selection pressure (discard bottom
half). Formalising this is a refactor of prompting, not a new system.

LLM-guided evolution has been explored for code (GenDLN ACL 2025,
GECCO 2024) and for ML architectures. UI is still open.

**Decision implication:** formalise the 5-variant exploration as a
GA with explicit operators. Novel territory; possibly meaningful
quality gain; low cost.

## The proposed architecture

The elegant collapse: we don't build a new pipeline parallel to the
existing one. We extend the existing symmetry.

### "Generation is extraction from imagination"

The project already has:
- **Ingest adapter** (ADR-006) — produces IR from a source.
- **Renderer** — lowers IR to a target.
- **Verifier** (ADR-007) — checks the renderer's output matches the IR.

Synthetic generation is the same shape with different inputs:

- **Generation adapter** — produces IR from a prompt plus context.
  Same `IngestResult + StructuredError` contract. ADR-006's symmetry
  carries through to the egress side.
- **Quality adapter** — checks *rendered* output matches *intent*
  (not just the IR). Same interface as the existing verifier,
  different checks.

Both plug into the existing spine. The IR stays central.

### Context object

The generation adapter's `generate(prompt, context) → IR` takes a
`context` bundle:

- **Universal catalog** — the 48-type catalog, DTCG-aligned for
  tokens. Stable across projects.
- **design.md** — per-project, designer-editable. Auto-generated v1
  from the MLIR (components, tokens, conventions, adjacencies),
  edited by a designer into v2.
- **Retrieved exemplars** — kNN against indexed corpus (own screens
  + ingested open corpora). RAS-style retrieval of IR subtrees, not
  RAG of text.
- **Default library** — for cases where the project lacks a component
  the prompt needs. Small, curated, universal.

The LLM doesn't "know what a card is." It receives: here's the
catalog's card contract, here's *this project's* card realisation
with 3 exemplar subtrees, here are the tokens you may reference,
here's how cards adjacent to this prompt's context have historically
been composed.

### Layout: soft intent, solver resolves

The LLM never emits coordinates. Ever. It emits:

- Tree structure (parent-child, auto-layout direction, ordering).
- Sizing modes (hug / fill / fixed-px).
- Token refs for padding / gap.
- Soft spatial intent expressed as constraints ("header above
  content, 16px gap").

A constraint solver (Cassowary / Z3) consumes the soft intent plus
the layout parent geometry and solves for concrete positions.

### Fall-through for component resolution

The IR carries *intent*, not *commitment*. Lowering tries:

1. **Exact match** — same `component_key` as requested.
2. **Family match** — same canonical type, compatible variants.
   Structural similarity if simple methods miss.
3. **Generic** — Mode 2 frame from catalog default slot structure.
4. **Default** — small curated library of universal fallbacks.

Fidelity loss at any level surfaces as a `KIND_*` structured error.
The verifier sees it. The critic can target the specific region.

### Evaluation is multi-adapter

Quality adapter runs in order:

1. **Structural verifier** (existing). Does the render match the IR?
2. **Vision critic** — Gemini 3.1 Pro (or swap) on the 5-dimension
   GameUIAgent rubric with UICrit few-shot.
3. **Token consistency** — do rendered values resolve to the tokens
   the IR bound?
4. **Corpus coherence** (optional) — kNN the rendered screen against
   the corpus; flag if it's an outlier in style.

Non-regressive accept (ReLook rule). Zoom-in on low-scoring regions
(SpecifyUI). Loop bounded by iteration budget or score plateau.

### The pipeline, end to end

```
prompt
  → generation_adapter       [5 variants on orthogonal axes]
  → layout_solver            [Cassowary over soft intent]
  → existing lowering + render
  → existing structural verifier
  → quality_adapter          [vision critic, non-regressive accept]
  → zoomed-in region critique + targeted edits (SpecifyUI pattern)
  → loop until plateau or budget
```

Everything inside `existing lowering + render` stays unchanged.
That's the elegance — the round-trip foundation carries the new
workload.

## Open questions

Named so we track them rather than pretend:

1. **Vision-model critic reliability on our corpus.** UICrit is
   mobile-only. Does a Gemini 3.1 Pro critic with UICrit few-shot
   give designer-agreement scores on Dank screens? Unknown.

2. **Structural similarity for fidelity fall-through.** How do we
   match a requested IR subtree to a CKR entry? Canonical-type
   equality gets us 80% for free; the last 20% may need embeddings.

3. **design.md as prompt payload vs retrieval target.** Size
   determines engineering approach. Needs measurement.

4. **Eval that isn't `is_parity`.** Our verifier checks "the IR
   rendered correctly." It doesn't check "the IR is actually a good
   answer to the prompt." VLM-as-judge vs human rating vs pairwise
   preference — we don't know which works best for our output.

5. **Cold-start for a new design system.** Dank has 204 screens. A
   new file with 10 screens has too thin a corpus. Does the pipeline
   gracefully degrade to ingested-defaults only? Unmeasured.

## Experimental plan (v0)

Eight experiments designed to answer the open questions and
pressure-test the architectural claims. All run against the existing
Dank corpus; no new infrastructure required.

| # | Experiment | Output file | Success criterion |
|---|---|---|---|
| 0 | Vanilla baseline — run current `dd generate-prompt` on 12 realistic prompts; collect artefacts without ratings | `experiments/00-vanilla-baseline/memo.md` + 12 artefact triples | Pipeline completes; failure modes tagged; designer-rateable output collected |
| 1 | Vision critic stress test — programmatic defect injection + Exp 0 outputs + Gemini 3.1 Pro with UICrit few-shot | `experiments/01-vision-critic/memo.md` | Critic flags ≥ 4/5 of each defect class with score drop ≥ 1.0 |
| 2 | Structural match ablation — 50 held-out INSTANCE nodes, 3 matchers | `experiments/02-structural-match/memo.md` + results CSV | Gap between canonical-type-only vs embeddings tells us if embeddings are v0.1 or v0.2 |
| 3 | design.md size analysis — generate v1 from Dank MLIR, measure | `experiments/03-design-md/memo.md` + generated `design.md` | Token count decides prompt-cache vs retrieval-chunked approach |
| 4 | VLM-as-judge correlation — 10 prompts, human + Gemini ratings | `experiments/04-vlm-judge/memo.md` | Spearman correlation > 0.7 (human vs VLM on intent-match) |
| 5 | Cold-start degradation — DEFERRED, run only after generator loop works | — | — |
| A | Symmetric adapter paper test — sketch `GenerationAdapter`, force 3 failure cases through it | `experiments/A-adapter-sketch/sketch.md` | All three scenarios fit the `IngestResult + StructuredError` shape without contortion |
| B | Cassowary solver reconstruction — strip coordinates from 10 screens, reconstruct from structure | `experiments/B-solver/memo.md` + results CSV | Mean IoU > 0.85 on bounding-box reconstruction |
| C | SKILL.md drafts — draft 4 skills (extract, verify, design-md, generate) | `experiments/C-skills/` | Four SKILL.md files that compose cleanly across realistic user flows |

### Lightweight, not production

These experiments are deliberately small, deliberately bounded, and
produce memos rather than proposals. The point is to move from
"I think X would work" to "on 50 held-out nodes, X works 78% of the
time." Everything documented in the `experiments/` directory becomes
a reviewable artefact for the v0.1 plan.

## Execution — three waves

### Wave 1 — launch in parallel

Five independent streams. No dependencies. Runs concurrently.
Wall-clock ~90 min.

- Agent: **Exp 0** vanilla baseline (uses the Figma bridge)
- Agent: **Exp 2** structural match ablation (pure compute)
- Agent: **Exp 3** design.md generator (pure compute)
- Agent: **Exp B** Cassowary layout reconstructor (pure compute)
- Main session: **Exp A** adapter sketch + **Exp C** SKILL.md drafts

### Wave 2 — rating pass (blocks on designer)

Designer rates the 12 Exp 0 artefacts on the failure-mode taxonomy
and the 10 Exp 4 outputs on intent-match. One batch, ~30–45 min.

### Wave 3 — critique experiments using Wave 1 artefacts

- Agent: **Exp 1 + Exp 4** merged — vision critic on Exp 0 artefacts
  + programmatic defects, plus VLM-vs-human rating correlation.

Wall-clock ~60 min.

## Pushback to re-address after experiments

Three architectural framings I want to stress-test with empirical
data, not opinions:

1. **"Generation is extraction from imagination."** Symmetric
   ADR-006. Paper test is Exp A.

2. **LLM never emits coordinates; solver always resolves.** More
   aggressive than 80% of production tools. Empirical test is
   Exp B — does Cassowary reconstruct positions from structure
   alone?

3. **Skill-first distribution.** Product decision. Paper test is
   Exp C — do the four SKILL.md files compose cleanly, or does the
   abstraction fight the existing CLI?

After Wave 3 completes, regroup and rewrite the v0.1 scope against
what we actually measured.

---

## Wave 1 findings (2026-04-16)

All four Wave 1 experiments completed. Summary of what shifted:

### Exp 0 — vanilla baseline: 1/12 completed

Pipeline fails catastrophically on synthetic IR because the
existing renderer emits `layoutMode = "VERTICAL"` on TEXT nodes,
which the Figma Plugin API rejects. 204/204 parity survived because
extracted TEXT nodes never have `layoutMode` set — only
synthetic-generated IR has the shape that triggers it. **Latent
bug in the existing renderer**, not synthetic-gen itself.

Secondary finding: **ADR-007 has a blind spot.** Script-level
throws bypass the per-op `__errors` channel. Zero `KIND_*` errors
surfaced despite 11 failures. Needs an outer `try/catch` that
pushes `KIND_RENDER_THROWN` into `__errors` before re-raising.

Tertiary (expected): zero Mode-1 instances across all 12 prompts,
zero token references, every non-screen element is a default
100×100 Mode-2 frame. Confirms the LLM sees almost nothing useful
through `build_project_vocabulary()` today.

### Exp 2 — embeddings ARE load-bearing for v0.1

Top-1 accuracy: canonical-type only = 42%, +prop compat = 44%,
embeddings = **86%**. The gap is entirely driven by the icon
long-tail (91 candidates, same canonical type, same size) — pure
type matching is a 91-way guess. Embeddings against paraphrased
glyph names lift icon accuracy to 92%. 7 embedding misses are
all top-3 correct; 3 of those have two component_keys sharing
the same name (information-theoretic ceiling).

Infrastructure cost: ~2 engineer-days with `all-MiniLM-L6-v2`
(384-dim), disk-cached, invalidated on CKR rebuild.

### Exp 3 — design.md fits in a single prompt cache entry

11,551 tokens for Dank (338 screens, 129 CKR entries, 86,766
nodes). Well under the 50K cache threshold with 4× headroom.
Extrapolation: 500 CKR entries = ~23K tokens (still cache);
Material-scale 2,000 entries = ~93K tokens (retrieval becomes
mandatory).

Top sections by size: component inventory (52%), token palette
(11%), adjacencies (11%).

**Surprising finding:** Dank has no conventional 4/8/16px grid.
Modal padding values are 10px (43%) and 14px (20%); only 24% of
values are 4px multiples. Three catalog types (`card`, `sheet`,
`slider`) exist visually but not as CKR components. These are
design-system-maturity signals. They also confirm auto-extraction
from the MLIR per-file is load-bearing — canned universal
principles docs ("align to 8-point grid") would produce actively
wrong guidance for Dank.

### Exp B — coordinate-free claim holds, with a reframe

Global mean IoU 0.098 (raw claim fails). But decomposing:
- **Auto-layout children, parent-local IoU: 0.915.** 90.5% above
  0.85. The existing spatial intent is sufficient.
- **Non-auto-layout children, parent-local IoU: 0.304.** Figma's
  `constraint_h`/`constraint_v` enum (MIN/CENTER/MAX/STRETCH/SCALE)
  doesn't carry starting offset, so a pinned-{MIN, MIN} node with
  16px inset reconstructs at (0, 0).
- Root screens in Dank have `layout_mode=None` (100% of 204
  screens), cascading the failure to every descendant.

Agent proposed three IR vocabulary additions to close the gap:
`offset_h`/`offset_v` (anchor + token offset), `semantic_anchor`
enum, and an asset-boundary seal on vector nodes.

### Exp A — symmetric `GenerationAdapter` shape holds

Paper-tested against three scenarios (clean generation, partial
success with fidelity loss, total refusal). All three fit the
`IngestResult + StructuredError` shape without contortion. One
addition: a `degraded` bucket in the summary for the "IR produced
but lossy" case (no analogue on ingest side).

Six new `KIND_*` constants extend the existing vocabulary naturally:
`KIND_PROMPT_UNDERSPECIFIED`, `KIND_COMPONENT_UNAVAILABLE`,
`KIND_DEGRADED_VARIANT`, `KIND_TOKEN_UNAVAILABLE`,
`KIND_SCHEMA_VIOLATION`, `KIND_LLM_REFUSED`.

### Exp C — four skills compose across three realistic user flows

`extract-figma`, `verify-parity`, `generate-design-md`,
`generate-screen`. No flow required a mega-skill or a sub-skill.
Each is a unit of user intent, thin wrapper over existing CLI.

## Architecture correction — IR fields stay out of L0

**The "add three IR fields" recommendation from Exp B's memo
is wrong.** The data it was trying to encode (anchor + offset) is
already present in the extracted corpus via `relative_transform`.
The Cassowary solver failed because it tried to reason from
Figma's constraint enum, not from `relative_transform`. That's a
translation problem, not a data problem.

Cleaner architecture:

- **L0 stays unchanged.** Figma-native scene graph, lossless.
  Adding synthesis-oriented fields pollutes it.
- **L3 generation intent is a separate vocabulary.** An LLM emits
  `{anchor: "top-leading", offset_h: "{space.md}", offset_v:
  "{space.lg}"}`. That's L3 — intent.
- **Lowering translates L3 → L0.** The solver's job is to resolve
  L3 intent into `relative_transform` + `x`/`y` values. For
  retrieval exemplars, derive L3 on the fly from extracted L0.
- DTCG at L2 (tokens). L3 intent *references* L2 tokens where
  values are needed (`offset_h: "{space.md}"`). They compose
  without overlap.

This matches how real compiler IRs (LLVM, MLIR) separate intent
at the top from geometry at the bottom. It also matches the
structure of the only research systems with explicit IRs
(SpecifyUI's two-level IR, GameUIAgent's recursive IR). Production
tools like Pencil / Paper / Stitch use coordinates directly
because they don't have an IR — they serialise state.

**Implications for v0.1 scope:**

- No schema migration. No `ALTER TABLE`.
- Generator emits L3 with the new vocabulary.
- A `lowering` stage translates L3 → L0.
- A `derive_l3_from_l0` helper produces retrieval-ready L3 from
  extracted corpus.
- Both directions live in one new module, probably `dd/intent.py`.

## Blocking bugs to fix before Wave 1.5

Two bugs surfaced by Exp 0 that block everything downstream:

1. **`layoutMode` on TEXT nodes.** Gate `layoutMode` emission on
   node type (FRAME / COMPONENT / INSTANCE / GROUP only).
2. **Outer `try/catch` in generated script.** Push
   `KIND_RENDER_THROWN` into `__errors` before re-raising.

Both ~30-90 min fixes. Both pure win — they close gaps in the
round-trip foundation that only didn't bite because the extractor
doesn't produce the shapes that trigger them.

## Added experiments (post-Wave 1)

Three experiments added to the plan based on what we learned:

- **Exp D — anchor exemplar impact.** Does kNN-retrieved IR
  context actually improve generation? Runs after Wave 1.5 with
  the fixed pipeline on the 12 prompts, with and without
  retrieval. Answers the central retrieval-thesis question.
- **Exp E — design-principles auto-induction.** Can Gemini 3.1
  Pro look at 20-30 Dank screenshots and produce the voice /
  intent / lineage sections that are currently TODO in design.md?
- **Exp F — critic ensemble disagreement.** Do Gemini and Claude
  disagree on synthetic output quality? Deferred until we have
  working generation to critique.

## A note on the meta

We went wide on this (the user's phrase: diverge/converge exploration)
before converging on a plan. The deliberate breadth surfaced
things we wouldn't have found with a narrower brief: Gemini 3.1 Pro's
WebDev Arena lead, the DTCG stable spec, UICrit's unused presence,
the skill-first distribution angle, the GA reframe of 5-variant
generation. All five changed the architecture.

The convergence step is these eight experiments. Each one turns a
judgment call into a measurement. Whatever the measurements show,
we plan v0.1 against reality instead of intuition.

---

## Pointers

- **Existing docs:**
  [`docs/compiler-architecture.md`](../compiler-architecture.md) |
  [`docs/roadmap.md`](../roadmap.md) |
  [`docs/architecture-decisions.md`](../architecture-decisions.md)
- **Existing research:**
  [`docs/research/t5-component-vocabulary-research.md`](t5-component-vocabulary-research.md) |
  [`docs/research/t5-generation-efficiency.md`](t5-generation-efficiency.md) |
  [`docs/research/t5-compositional-analysis.md`](t5-compositional-analysis.md)
- **Experiments (to be created):** `experiments/` (this directory
  does not yet exist — each subagent creates its own subdirectory).


---

## Wave 1.5 + Wave 2 reality check (2026-04-16 late-session)

After three Wave 1.5 runs (v1 credits, v2 partial fix, v3 properly
fixed renderer), all 12 prompts now render structurally — 12/12
`__ok:true`, 229 walked eids, zero script errors. The pipeline is
structurally sound.

**But the output is categorically broken at the visual level.** When
the screenshots were actually examined (which I should have done before
writing the rating template), every one of the 12 renders as:

- A handful of `text`/`heading` labels at top-left.
- Everything else (buttons, inputs, cards, icons, images) renders as
  invisible 100×100 grey frames.
- No visible UI structure at all.

This is consistent with the Wave 1.5 v3 memo's warning — 212 of 229
non-screen nodes at Figma's `createFrame()` default, Mode-2 has no
internal templates — but the impact is more categorical than "low
structural quality." There's literally nothing for a designer to
rate. The rating template at
`experiments/00c-vanilla-v3/RATING.md` was premature.

**Process correction going forward:**

1. **Auto-inspect before human-rate.** Any experiment that produces
   rendered output must run a cheap visual sanity check (VLM score,
   or even a rule-based "% non-background pixels" metric) BEFORE
   escalating to human review. If the output is categorically
   broken, fix the pipeline first. Never ask a human to rate empty
   grey rectangles.

2. **Re-run with gating before assuming a baseline is a baseline.**
   Wave 1.5 v3's "12/12 success" was about script execution, not
   visual output. A fresh baseline needs BOTH gates (script
   completes AND VLM sees non-trivial content) before it's a
   useful comparator.

## What unblocks synthetic generation now

The single highest-leverage next step is **Exp H Step 1 — ingest
shadcn/ui** (spec at `experiments/H-design-systems/spec.md`). Until
the pipeline has real component templates to fall through to,
generation will keep producing empty-frames-plus-text-labels
regardless of LLM quality.

Estimated 2-3 engineer-days for shadcn MVP, following the spec's
five-step rollout. Step 2 is measuring impact; Step 3 adds Material
Design 3 to cover the 36 catalog gaps Dank can't supply.

After H lands, re-run Wave 1.5 v3's 12 prompts with shadcn linked —
now Exp D (retrieval impact) and Wave 2 (rating) become meaningful.
