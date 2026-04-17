---
title: Screen-archetype + hierarchical-prompting approaches for Mode-3 v0.1.5
status: research memo, decision-grade
date: 2026-04-16
author: research synthesis (Claude Opus 4.7)
informs: ADR-008 follow-on; pre-v0.3-critic uplift
---

# Screen-archetype + hierarchical-prompting approaches for v0.1.5

## Executive summary

Mode-3 v3 reached 4 VLM-ok + 5 VLM-partial / 12 on the canonical prompts. The
outstanding failure mode is not rendering correctness — it is that the LLM
emits 4–6 flat top-level components (`header`, `card`, `button`) with no
internal structure, even for inherently composite archetypes (feed, dashboard,
meme wall). This memo surveys how the leading LLM-UI tools and the relevant
arxiv literature address that exact problem, and recommends a two-track v0.1.5
ship plan.

**Findings.** Every production system that consistently produces rich,
hierarchical screens does some form of *plan-then-fill* with a structured IR,
and *all four* of the strongest ones (GameUIAgent, SpecifyUI/SPEC, DesignCoder,
Figma First Draft) commit to a **two-level IR**: a global/page-level skeleton
plus a per-region/section expansion. Vercel v0 sidesteps the problem by
retrieving hand-curated archetype exemplars from a read-only filesystem rather
than planning ([Vercel blog](https://vercel.com/blog/how-we-made-v0-an-effective-coding-agent),
[Vercel composite model blog](https://vercel.com/blog/v0-composite-model-family)).
Google Stitch and Figma First Draft both sit on curated library foundations
([Figma blog](https://www.figma.com/blog/figma-ai-first-draft/),
[Google Developers blog](https://developers.googleblog.com/stitch-a-new-way-to-design-uis/)).
Anthropic's own frontend-design SKILL rejects the templating path entirely and
relies on *behavioural priming* ("pick an extreme") rather than structural
scaffolding ([Anthropic SKILL.md](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)).

**Recommendation.** Ship two small changes in v0.1.5, parallel, both fitting
inside the existing Mode-3 provider architecture:

1. **An archetype-conditioned few-shot pack** (A1): 8–12 canonical screen
   skeletons, each a 2–3 level JSON tree, selected per prompt by a lightweight
   classifier and injected into `SYSTEM_PROMPT`. Borrowed from First Draft's
   library model + UICrit's 55 % few-shot uplift result
   ([UICrit arxiv 2407.08850](https://arxiv.org/abs/2407.08850)).
2. **A plan-then-fill two-call pipeline** (A2): call #1 emits a
   page→section→component skeleton; call #2 fills leaf text/icons with the
   skeleton pinned in the context. Borrowed from SpecifyUI/SPEC
   ([arxiv 2509.07334](https://arxiv.org/abs/2509.07334)) and DesignCoder
   ([arxiv 2506.13663](https://arxiv.org/html/2506.13663v1)).

A1 is the quality floor — it costs ~+400 prompt tokens, zero latency, zero new
code paths. A2 is the quality ceiling — it costs 2× tokens and +0.8 s wall
clock, plus one new planning provider. Ship A1 this sprint; A2 behind a flag
in the same sprint if time allows; otherwise A2 is the obvious v0.2 lead.

Defer retrieval (B) and critic-refine (C) to v0.3 per the existing ADR-008
phasing — they depend on assets we don't yet have (an embedding index of real
screens and the `RenderVerifier` visual-loss taxonomy).

---

## Per-system analysis

### Vercel v0 — retrieval + autofix, no explicit planning

v0's public documentation
([v0 intro](https://v0.app/docs/introduction), [v0 prompting docs](https://vercel.com/blog/how-to-prompt-v0))
doesn't expose the generation pipeline, but the engineering blog
([how-we-made-v0-an-effective-coding-agent](https://vercel.com/blog/how-we-made-v0-an-effective-coding-agent))
and composite-model blog
([v0-composite-model-family](https://vercel.com/blog/v0-composite-model-family))
describe a three-layer stack: a **dynamic system prompt** that retrieves
hand-curated code samples into a read-only filesystem using embeddings and
keyword matching; **LLM Suspense** that rewrites the output stream in ≤100 ms
(URL tokenisation, icon-library fixups via embedding nearest-match); and a
fine-tuned **vercel-autofixer-01** that lifts error-free generation from
64.71 % (raw Sonnet baseline) to 93.87 %.

The leaked v0 system prompt
([jujumilk3/leaked-system-prompts/v0\_20250306.md](https://github.com/jujumilk3/leaked-system-prompts/blob/main/v0_20250306.md))
confirms there is **no hierarchical planning scaffold** — the model is told to
emit `<Thinking>` blocks before the project, then produce one React Project
block, one component per file, targeting shadcn/ui + Lucide icons +
Tailwind. Archetype richness comes from the retrieved examples and from
Sonnet's training prior over shadcn code on the web, not from a planner.

**Implication for us.** v0's approach is a *library + retrieval* system. The
library (shadcn) is doing the heavy lifting by encoding archetype expectations
in its composite primitives (`<Card><CardHeader>…</Card>`, `<Tabs><TabsList>…`).
We have an equivalent lever — the 129-entry project CKR — but our SYSTEM\_PROMPT
merely lists CKR keys as vocabulary. It does not show *how* to compose them
into a rich tree. A1 closes this gap.

### Figma First Draft — curated libraries, LLM picks from a closed menu

Figma's blog
([figma-ai-first-draft](https://www.figma.com/blog/figma-ai-first-draft/))
and help article
([Use First Draft with Figma AI](https://help.figma.com/hc/en-us/articles/23955143044247-Use-First-Draft-with-Figma-AI))
describe the approach explicitly: "Figma AI uses Figma-built wireframing and
design libraries as the foundation for generating designs … a set of building
blocks — or stacks of components — that are used to piece together your
design." Off-the-shelf models (GPT-4, Amazon Titan) plus four libraries
(Basic App, App Wireframe, Basic Site, Site Wireframe). The library is
selected by the AI if the user doesn't pick one; the LLM then "selects,
arranges, and customizes" from that closed menu.

**Implication for us.** This is *exactly* the shape of our registry-driven
composition. First Draft works because the library is a *composed* unit (a
"Basic App" wireframe stack is a pre-nested `screen→section→component` tree,
not a loose bag of primitives). Our 11 universal backbone templates are
single-level. A1 proposes we pre-compose 8–12 of them into full-screen
skeletons.

### Google Stitch — multimodal, graph-neural hierarchy predictor (unverified)

The official sources are thin
([Google blog](https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/),
[Google Developers blog](https://developers.googleblog.com/stitch-a-new-way-to-design-uis/),
[stitch.withgoogle.com](https://stitch.withgoogle.com/))
and confirm only that Stitch leverages "Gemini 2.5 Pro's multimodal
capabilities" to output clean front-end code. A secondary source
([ALM Corp guide](https://almcorp.com/blog/google-stitch-complete-guide-ai-ui-design-tool-2026/))
claims an internal "hierarchical component tree" with "graph neural networks
[that] predict hierarchies (e.g., nav > hero > cards)". **Caveat:** this is a
third-party blog, not Google documentation; treat as indicative, not
evidentiary. The March 2026 update
([Medium overhaul post](https://medium.com/google-cloud/how-i-overhauled-my-app-ui-in-minutes-with-stitch-and-ai-studio-524b965c3d45))
added design-system import, which confirms that at minimum Stitch can
condition generation on user-supplied tokens and components — matching the
First Draft playbook.

**Implication.** If the GNN-hierarchy claim is real, it's a neural substitute
for the plan-then-fill pattern (A2). We can't replicate a trained GNN in
v0.1.5, but the *plan-first* principle is the same.

### 0xdesign design-plugin — 6-phase workflow, N-variant generation

The repo README
([github.com/0xdesign/design-plugin](https://github.com/0xdesign/design-plugin))
describes 6 phases: preflight detection → style inference → discovery
interview → **variation generation (5 distinct variants exploring different
hierarchy, layout, density, interaction, visual expression)** → side-by-side
review → iterative refinement. Note: the user brief says 8 phases and a
`DESIGN_PRINCIPLES.md`; neither exists in the current repo. The persistent
outputs are `DESIGN_PLAN.md` and `DESIGN_MEMORY.md`.

**Implication.** The N-variant pattern is the cheapest way to explore
archetype-space without committing to a taxonomy. Anthropic's
frontend-design SKILL uses the same trick in prose form ("pick an extreme
direction"). Low priority for us because we already have a VLM gate that can
rank variants — but if A1+A2 underperform, generating 3 variants per prompt
and letting the VLM pick is a strong v0.2 move.

### Anthropic frontend-design SKILL — behavioural priming, no structure

The SKILL.md
([github.com/anthropics/skills — frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md),
[claude blog — improving-frontend-design-through-skills](https://claude.com/blog/improving-frontend-design-through-skills))
is emphatic: **no templates, no archetype taxonomy, no hierarchical
guidance**. It diagnoses the failure mode as "distributional convergence —
Claude gravitates toward safe, statistically common patterns" and prescribes
one remedy: force extremes (weights 100/900 not 400/600, size jumps 3×+ not
1.5×) to make mediocrity impossible.

**Implication.** This complements rather than replaces a structural approach.
Our VLM-partial prompts (05-paywall, 07-search, 10-carousel) are *not*
aesthetically generic — they're *structurally sparse*. The extreme-direction
trick won't close structural gaps. We should steal the phrasing for copy-tone
guidance inside the fill step of A2, but it is not the primary lever.

### Paper.design / Pencil.dev — out of scope

Paper.design
([paper.design](https://paper.design/)) is a bidirectional MCP canvas — agents
sync tokens/components with a codebase in a continuous loop. It does not do
prompt→UI generation; it does agent-assisted authoring inside an existing
design. Pencil.dev
([pencil.dev](https://pencil.dev/)) exposes only "Design on canvas. Land in
code." publicly; no architectural claims. Neither maps to our problem.

### Builder.io Visual Copilot — image-to-code, not prompt-to-UI

The blog
([builder.io — figma-to-code-visual-copilot](https://www.builder.io/blog/figma-to-code-visual-copilot))
describes a 3-stage pipeline: a model trained on 2M data points that maps
"flat design structures into code hierarchies", a Mitosis compiler that
emits framework code, and a fine-tuned LLM that refines output. The 2M-point
model is doing the same work as our *extractor*, not our *generator*. Not
directly applicable, but a useful proof that a large supervised flat→tree
model is feasible if we ever invest in training data.

### Mobbin — taxonomy reference only

[Mobbin](https://www.mobbin.com/) returned 403 to fetch, but it is publicly
known as a pattern library taxonomised by screen type (onboarding, sign-up,
empty state, paywall, settings, search, chat, feed, etc.) and by flow. Useful
as the *vocabulary* for our archetype taxonomy — not as a generation system.

---

## Academic prior art

- **UICrit** ([arxiv 2407.08850](https://arxiv.org/abs/2407.08850)) — 3,059
  human critiques on 983 UIs. **55 % gain in LLM-generated UI feedback
  quality via few-shot visual prompting.** The single strongest empirical
  case for few-shot over raw prompting in UI tasks.
- **GameUIAgent** ([arxiv 2603.14724](https://arxiv.org/abs/2603.14724)) —
  6-stage pipeline: prompt engineering → LLM generation of Design Spec JSON
  → post-processing (repair, data injection, rarity enhancement) →
  rendering → VLM review → Reflection Controller. Two findings matter for
  us. **Quality-ceiling effect** (Pearson r = −0.96): reflection-based
  refinement plateaus once base quality is below a threshold — fix the base
  generation before building a critic loop. This *directly argues against*
  jumping to v0.3 now. **Rarity enhancement** is a deterministic
  post-generation step that decorates the tree — a pattern we should copy for
  padding sparse LLM output with sensible defaults.
- **SpecifyUI/SPEC** ([arxiv 2509.07334](https://arxiv.org/abs/2509.07334))
  — **two-level IR**: global (layout/color/shape/usage quadruple) and page
  (Page → Section → Component with constraint
  `Sec_j.layout ⊆ 𝒢.L ∧ Sec_j.color ⊆ 𝒢.C`). Generation is a 3-stage
  extract → retrieve-from-a-2,000-pair-DB → debug-with-compiler-feedback
  loop. Component-correctness Likert M = 5.69 vs 4.20 baseline. This is the
  closest match to our architecture — their global/section/component IR maps
  onto our catalog + slot\_definitions + CKR.
- **DesignCoder** ([arxiv 2506.13663](https://arxiv.org/html/2506.13663v1))
  — explicitly "hierarchy-aware" UI-code generation. Chain-of-thought over
  UI grouping → component-tree construction → tree-aware code generation →
  self-correcting refinement. **TreeBLEU +30.19 %, container-match +29.31 %**
  over best prior baseline. Strongest empirical evidence that explicit
  tree construction before codegen wins on structural metrics.
- **UI Grammar + LLM** ([arxiv 2310.15455](https://arxiv.org/abs/2310.15455))
  — grammar production rules as prompt scaffolding; the abstract reports
  "promising capability" but no concrete numbers in the accessible portion.
  The grammar framing validates our existing
  `catalog.slot_definitions` — which is structurally a production grammar
  — as a legitimate prompt substrate.
- **Plan-then-render hybrid** — LayouSyn
  ([Lay-Your-Scene, ICCV 2025](https://mlpc-ucsd.github.io/Lay-Your-Scene/))
  and CreatiLayout
  ([creatilayout.github.io](https://creatilayout.github.io/)) both use an
  LLM for layout planning, then a specialist neural model for rendering.
  LLMs "drop to 57 % recall on layouts with >15 objects" is the claim cited
  in the user brief; I couldn't locate that exact figure in the accessible
  abstracts but the general phenomenon — LLMs underperform specialised
  planners at high object counts — is consistent with SpecifyUI's finding
  that splitting the IR helps.

---

## Cross-cutting findings

1. **The consensus architecture is plan-then-fill with a two-level IR.**
   SpecifyUI (global + section), GameUIAgent (spec + render), DesignCoder
   (grouping + generation) and the inferred Stitch GNN-hierarchy all split
   structure from content. Single-shot flat generation — which is what our
   Mode-3 v3 does — is the outlier.
2. **Few-shot of full, nested exemplars beats description-only prompting.**
   UICrit's 55 %, First Draft's entire business model, and v0's
   read-only-filesystem trick all trade prompt tokens for example-anchored
   structure. Our current SYSTEM\_PROMPT shows *one* example with 3 elements
   ([`dd/prompt_parser.py`](../../dd/prompt_parser.py) line 147 area). That
   is 10× too little.
3. **Archetype taxonomies come from corpora, not from first principles.**
   Figma built its libraries by observing real apps. Mobbin's taxonomy is
   empirical. SpecifyUI's 2,000-pair DB is mined. We should extend
   `dd/screen_patterns.py` to cluster screens by *deep* signatures (slot
   populations, not just root-type sets) and derive archetypes from the
   Dank corpus rather than hand-naming them.
4. **Critic loops underperform if the base generator is below threshold.**
   GameUIAgent's ceiling effect (r = −0.96) is a strong prior against
   jumping straight to v0.3 RenderVerifier-driven refinement. Fix the
   generator first.
5. **Deterministic post-processing ("rarity enhancement") is a free lever.**
   After the LLM returns, walking the tree and padding sparse nodes with
   sensible defaults (empty `feed` → 4 item children; empty `form` → 3
   field children) is zero-LLM-token and under-used in literature but
   obvious in engineering terms. Fold into A1 as a "compose cascade
   fallback" step.

---

## Candidate approaches

### A1 — Archetype-conditioned few-shot pack (recommended v0.1.5)

**Shape.** Extend `dd/screen_patterns.py` from root-type signatures to full
skeleton signatures; hand-author 8–12 canonical skeletons (feed, dashboard,
paywall, login, settings, search, onboarding-carousel, chat, empty-state,
profile, checkout, detail). Each skeleton is a 2–3 level JSON tree in our
IR dialect, 10–25 nodes. At classify time a lightweight classifier (keyword
match on the prompt, then Haiku 3.5 with a 12-way classification prompt as
tiebreaker) picks one or two skeletons; `SYSTEM_PROMPT` gets prepended with
the selected examples.

**v0.1 scope (1 week).**
- Write skeletons as JSON fixtures under `dd/archetype_library/`.
- Add `ArchetypeLibraryProvider` to the Mode-3 provider chain *upstream* of
  `UniversalCatalogProvider` — if the archetype provider matches, the LLM
  never sees the universal fall-through. This is the shape First Draft uses.
- Add a pre-prompt classifier (30-line function, literal-keyword map +
  Haiku fallback).
- Extend `SYSTEM_PROMPT` to inject the matched skeleton(s) inline as
  few-shot examples.
- Add a deterministic post-pass (the "rarity enhancement" idea): walk the
  LLM output; if an element of type `feed` has <3 children, insert
  placeholder item children from the skeleton. Same for `form`, `list`,
  `tabs`.
- 15 new unit tests; no round-trip regression.

**Expected uplift.** 4 → 7–8 VLM-ok. The three pure-structural failures
(03-meme, 04-dashboard, 12-round-trip) should all move to ok — a dashboard
skeleton that prescribes `header + kpi-row(4) + chart + table` is the exact
missing piece. Two of the five VLM-partials should move to ok because the
skeleton injection forces nested structure (05-paywall gains
`hero + feature-list + price-row + cta`, etc.). Conservative estimate based
on UICrit's 55 % few-shot gain and First Draft's working-product existence.

**Cost.** +350–600 prompt tokens per call (skeleton JSON is dense). +0
wall-clock (classifier is literal/cached Haiku). 0 new test-infrastructure
dependencies.

**Failure modes.**
- Prompt doesn't match any archetype → falls through to current Mode-3 v3
  behaviour. No regression.
- Skeleton over-prescribes — LLM copies it verbatim and produces something
  that doesn't match the prompt. Mitigation: examples are framed as
  "inspiration, not template"; mandatory instruction is to *modify* the
  skeleton for the specific prompt.
- Classifier mis-routes (e.g. "a search page with a feed of results" →
  picked as feed, not search). Mitigation: allow top-2 skeletons as
  multi-example few-shot.

**ADR-008 fit.** Ideal. Slots into the provider chain above
`UniversalCatalogProvider`. Consumes existing `screen_patterns.py`
infrastructure. No migration. `DD_DISABLE_ARCHETYPE_LIBRARY` flag matches
the existing `DD_DISABLE_MODE_3` convention.

### A2 — Plan-then-fill two-call pipeline (recommended v0.1.5 stretch, else v0.2)

**Shape.** First LLM call takes the prompt and returns *only* a skeleton
(page + sections + component-types, no copy, no leaf props). A deterministic
pass validates the skeleton against the catalog grammar. Second LLM call
takes the validated skeleton and fills `text`, `icon_name`, `variant`, and
optional overrides, with the skeleton pinned in the context so the model
cannot drop nodes. Mirrors SpecifyUI's extract + compose separation and
DesignCoder's grouping + generation split.

**v0.1 scope (1 week if parallel to A1).**
- New `dd/compose/plan.py` with two prompt templates and a JSON-mode Claude
  call for each.
- Skeleton-grammar validator (reuses existing
  `dd.composition.slots.validate_slot` + catalog capability gates).
- Feature flag `DD_ENABLE_PLAN_THEN_FILL` default off.
- 20 new unit tests (plan-schema validity, fill-preserves-skeleton,
  capability gating still enforced).

**Expected uplift.** 4 → 9–10 VLM-ok *when* combined with A1's skeletons as
the plan target. On its own (without A1) uplift is smaller (4 → 6–7) because
the LLM still has to invent structure. This is why A1 is the stronger solo
move.

**Cost.** 2× prompt tokens; ~+0.5–0.8 s wall clock. One new provider-chain
position.

**Failure modes.**
- Plan call returns invalid skeleton (unknown types, depth overflow). Guard
  via strict JSON schema + one retry with error feedback, then fall through
  to current single-call mode. GameUIAgent reports "non-regressive" loops
  via best-result tracking; same here.
- Fill call drifts from plan (drops nodes, adds new ones). Guard by
  diffing plan vs fill node-id sets post-hoc; any deletions trigger a
  single retry with a pinned plan.
- Doubled tokens if something goes wrong.

**ADR-008 fit.** Good. Replaces single-call composition inside
`dd/compose.py` with a two-call variant, both using the same provider
chain. Can coexist with current mode behind flag. Adds a new
`KIND_PLAN_INVALID` boundary error kind.

### B — Corpus retrieval (v0.2 — defer)

**Shape.** Embed every screen in the 204-screen Dank corpus; for each new
prompt, retrieve top-3 similar screens; inject their IR trees as few-shot
examples. This is v0's approach scaled to *our* corpus instead of hand
curation.

**Why defer.** We have neither an embedding index nor a corpus wide enough
(204 screens, one project) to retrieve diverse archetypes. A1 gets ~80 % of
the benefit from 12 hand-authored skeletons with no index. Ship A1 first;
rebuild this as retrieval once the corpus reaches multiple projects or ≥ 1k
screens.

### C — Critic-refine loop (v0.3 — defer per ADR-008)

**Shape.** The RenderVerifier-driven refinement already scoped as v0.3.

**Why defer.** GameUIAgent's quality-ceiling result
([arxiv 2603.14724](https://arxiv.org/abs/2603.14724)) is explicit: reflection
plateaus below a base-quality threshold. Fix the generator (A1/A2) before
building a critic loop; otherwise the loop refines slop into polished slop.

### D — N-variant + VLM-pick (v0.2 candidate)

**Shape.** Generate 3 variants per prompt (different extreme directions per
Anthropic SKILL), run all through the VLM sanity gate, pick the top-scoring
one as the ship candidate. The 0xdesign plugin's pattern.

**Why v0.2.** Triples token cost for a modest quality gain (empirically
~10–15 % in 0xdesign's anecdotal claims); lower value-for-token than A1/A2
at our current failure mode, which is structural not aesthetic.

---

## Recommendation and phasing

**v0.1.5 (ship this sprint):**
- **A1 (archetype few-shot pack)** — confident +3 to +4 VLM-ok prompts,
  low-risk, fits the provider model cleanly, ~1 week.
- **A2 (plan-then-fill)** behind `DD_ENABLE_PLAN_THEN_FILL` flag — if A1
  lands early, start A2 the same sprint. Otherwise it is the obvious v0.2
  headliner.

**v0.2:**
- **A2** if not shipped in v0.1.5.
- **B (corpus retrieval)** once a second project is ingested, or the
  archetype library grows to >25 skeletons that a retrieval index would
  serve faster than linear scan.
- **D (N-variant + VLM-pick)** if A1+A2 leaves ≥3 VLM-partials.

**v0.3:**
- **C (RenderVerifier critic loop)** per existing ADR-008 phasing, but
  explicitly gated on "base VLM-ok ≥ 8/12" per GameUIAgent's quality-ceiling
  finding.

**Why not just A2.** A2 without A1 still requires the LLM to invent
skeletons from prose; UICrit's evidence is that few-shot is the cheapest
gain in UI tasks and A1 provides the strongest per-token lift. A2 + A1 is
additive because the plan step uses A1's skeletons as its structural
priors.

---

## Open questions for the resulting ADR

1. **Archetype taxonomy source.** Hand-authored from the 12 canonical
   prompts, mined from the Dank corpus via extended
   `dd/screen_patterns.py`, or Mobbin-derived? Recommendation: start
   hand-authored (fast, exact fit to our prompt set), mine from corpus in
   v0.2 once the provider is proven.
2. **Skeleton fidelity vs freedom.** How strictly does A1's post-pass
   enforce the skeleton? "If feed has < 3 children, pad from skeleton"
   is safe; "replace LLM output with skeleton if it doesn't match" is
   almost certainly too rigid. Needs empirical tuning on the 12-prompt set.
3. **Plan-schema design for A2.** What is the minimum sufficient shape?
   SPEC's global/section/component is 3 levels. Our catalog already has
   slot\_definitions. Is the plan-level IR a pruned subset of our full IR,
   or a separate schema? Recommendation: pruned subset
   (`{type, id, children: [{type, id, count_hint?}]}`) to keep the
   plan LLM call small and reject-rate low.
4. **Classifier strategy for skeleton selection.** Keyword map + Haiku
   fallback works for our 12 prompts; will break on diverse prompts. When
   do we upgrade to an embedding classifier, and on what data?
5. **Provider chain ordering.** Archetype library above or below the
   project CKR provider? Recommendation: *above* — archetype supplies
   structural skeleton, CKR supplies per-node component references
   within the skeleton. The two layers compose cleanly.
6. **Rarity-enhancement-style post-pass — how far to push it?** Defaulting
   "empty list → 4 items" is uncontroversial. Defaulting "dashboard with
   no chart → synthesise a bar chart" is controversial. Needs a small
   rubric tied to archetype metadata.
7. **Does A1 invalidate the container-semantics hints currently in
   SYSTEM\_PROMPT** ([`dd/prompt_parser.py`](../../dd/prompt_parser.py)
   line ~147)? Recommendation: keep them but demote — they become the
   fallback when no skeleton matches.
8. **How do we measure density quantitatively?** VLM-ok is coarse. A
   `nodes-per-screen` + `max-depth` + `leaf-coverage` triple would let us
   track structural richness independent of VLM judgement. Cheap to add
   to the existing `inspect-experiment` command.
