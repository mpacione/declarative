# Designer cognition + LLM-agent architecture for design exploration

**Authored:** 2026-04-21 late session (after April cleanup).
**Source:** synthesis of 3 parallel research agents (cognition lit, 2025-2026 systems survey, architectural sketch on our stack) + the user's stated cognitive model.
**Status:** research note. Not implemented. Read alongside `docs/research/scorer-calibration-and-som-fidelity.md` (the scorer foundation that any designer-agent loop builds on).

> **Why this exists separately from the scorer doc**: the scorer arc was about *how to measure*. This is about *how a designer-agent loop would think*. Both inform any next "make Claude design like a designer" work, but they're separate concerns and each deserves its own canonical home.

---

## 1. The user's stated cognitive model

The user described how they (a designer) actually approach a new screen. Paraphrased — *not* mined for axioms, kept fluid:

1. **Think broadly** — what does this screen need? From a spec, a list, spitballing, experimentation.
2. **Wireframe of content** — top nav, scrolling grid of cards, sidebar, bottom nav. Structural, no styling.
3. **Drill into components** — logo here, menu buttons for sections, image + text + 2 buttons inside a card.
4. **Look for examples** — own corpus, web inspiration, references.
5. **Try variations non-destructively** — multiple layouts side-by-side, comparable visually.
6. **Style comes LATER** — placeholder typeface, refine as visual system emerges.
7. **Reuse existing components / sizes / spacing / margins** where possible.
8. **Sometimes invert: components first** — 3 modal styles, button styles, dropdowns, icons → assemble screens from them.
9. **Iterate up + down the abstraction ladder** — components inform screens inform components.

Their phrase: *"It really does mimic Christopher Alexander's model of a pattern language, moving up and down the abstraction ladder."*

The fluidity is load-bearing. Earlier in the session I extracted "style comes LATER" as a hard architectural rule and got correctly called out — the brief was about *flow*, not phases.

---

## 2. Cognitive primitives — the agent's action vocabulary

From Schön (1983/1992), Goldschmidt (2014), Cross & Dorst (2001), Lawson (1980/2005), Suwa & Tversky, plus 2024-2026 GenAI cognition work. **15 named operations** that a designer's mind performs. These should be the agent's *tool surface* — not "emit_component_list" but operations that match how a designer reasons.

| # | Primitive | Source | What it is | Where it fires in our loop |
|---|---|---|---|---|
| 1 | **NAME** | Schön (problem setting) | Decide which entities deserve attention ("nav," "card grid"). Naming determines what can be solved. | Pre-wireframe; before any markup write |
| 2 | **FRAME** | Schön | Pick the lens — "this is a settings dashboard." Frame constrains all subsequent moves. | After NAME; sets the retrieval prior for corpus lookup |
| 3 | **SEE-AS** | Schön | Map the unfamiliar onto a known repertoire item ("treat this like Material 3 list-detail"). | Drives template/fragment retrieval (Mode-3 corpus pull) |
| 4 | **MOVE** | Schön / Goldschmidt | One discrete change to the design (add node, set prop, replace subtree). The atomic unit. | Maps 1:1 to our 7-verb edit grammar |
| 5 | **SEE-MOVE-SEE** | Schön | After every MOVE, re-perceive the artifact; consequences exceed intent. | Renderer-in-loop + scorer feedback after each edit batch |
| 6 | **LATERAL MOVE** | Lawson, de Bono | Generate sibling alternative *at same abstraction* without committing. | Branch in design-space tree; non-destructive variant |
| 7 | **VERTICAL DRILL** | Lawson, abstraction-ladder lit | Descend one level of detail ("card → image+title+CTA"). | Triggers density-down on the dd markup node |
| 8 | **VERTICAL CLIMB** | Cross/Dorst | Ascend; let component decisions inform screen-level constraints. | Re-evaluate parent; update tokens / layout spec |
| 9 | **CO-EVOLVE P/S** | Dorst & Cross 2001 | Refine problem statement *because* a solution attempt revealed something. | Spec rewrite triggered by render failure, not regenerate |
| 10 | **DEFAULT vs SURPRISE** | Dorst & Cross | Compare current artifact to "default expected"; on surprise, choose embrace-or-reject. | Scorer signal + LLM judge: "surprising-good or surprising-bad?" |
| 11 | **CRITICAL MOVE** | Goldschmidt linkography | A move that links to many earlier and later moves; load-bearing. | Promote to memorialized pattern; cache as fragment |
| 12 | **APPRECIATE** | Schön (appreciative system) | Apply tacit aesthetic/functional criteria, not articulable rules. | Where VLM critic + QWAN-trained scorer live |
| 13 | **REFRAME** | Schön | Drop the current frame; problem was wrong shape. | Restart from a different corpus retrieval; prune subtree |
| 14 | **CHUNK / WEB / SAWTOOTH** | Goldschmidt | Recognized topology of move-clusters in a session: chunks = focused detail; webs = integration; sawtooths = stalling. | Linkography monitor on agent's own trajectory; intervene on sawtooth |
| 15 | **FIXATION-BREAK** | Jansson & Smith; GenAI fixation lit (2025) | Inject orthogonal precedent when output stops varying. | Persona swap, corpus shard switch, temperature bump on detected homogenization |

Eight of these map 1:1 to existing modules in our stack:

| Designer primitive | Already in our stack |
|---|---|
| NAME / FRAME | `dd/prompt_parser.py`, `dd/composition/archetype_classifier.py` |
| SEE-AS | `dd/composition/providers/corpus_retrieval.py` |
| MOVE | `dd/markup_l3.apply_edits` (M7.1) + per-verb scripts |
| SEE-MOVE-SEE | `render_test/walk_ref.js`, `render_test/batch_screenshot.js`, `dd/apply_render.py` |
| APPRECIATE | `dd/fidelity_score.py` (post-`803c3e3` SoM scorer) |
| VERTICAL DRILL | `scripts/compose_demo.py` (M7.6 S4.2) |
| REPAIR (≈ FIXATION-BREAK) | `dd/repair_agent.py` (M7.5) |
| PROMOTE (≈ CRITICAL MOVE) | `dd/patterns.py` (M7.0.e) |

The work isn't building those — it's **wiring them together as a loop the LLM can navigate as a unified vocabulary**.

---

## 3. Five architectural patterns from the literature

For "LLM-as-designer" loops. None are exclusive; layer them.

### Pattern A — Linkography-Monitored Generator-Critic

- **Structure:** Generator → Renderer → VLM Critic (APPRECIATE) → Linkograph monitor (Fuzzy Linkography 2025) → Controller decides next primitive.
- **Loop:** Each MOVE embeds; cosine-similarity links it to prior moves; controller watches linkograph density index (LDI) and entropy; sawtooth pattern triggers FIXATION-BREAK.
- **Guards against:** runaway local refinement, fixation, agent burning iterations on cosmetic changes.
- **Built by:** Fuzzy Linkography (Karimi et al. 2025), iGOAT (2026) — neither closes the loop back to generation; we'd be first.

### Pattern B — Co-Evolutionary Twin-Tree

- **Structure:** Two parallel grow-able trees: ProblemTree (named/framed entities, criteria) and SolutionTree (markup variants). Edges cross at "bridge" nodes (Dorst & Cross's "creative event").
- **Loop:** SEE-MOVE-SEE on solution side; on surprise, controller mutates problem side ("we thought it was a dashboard; it's actually a feed") — re-retrieve.
- **Guards against:** spec rigidity. Pure spec-driven generation can't notice when the spec is the bug.
- **Built by:** concept is Dorst & Cross 2001; no LLM agent implements it explicitly. SpecifyUI (2025) gets close but spec is read-only during generation.

### Pattern C — Blackboard with Specialist Agents

- **Structure:** Shared blackboard holds (Spec ⊕ MarkupTree ⊕ VariantSet ⊕ MoveLog ⊕ TokenSystem). Specialist agents subscribe: Wireframer, Stylist, Component-Reuser, Critic, Pruner, Linkographer. Each posts when its preconditions match.
- **Loop:** Opportunistic, not orchestrated. Wireframer fires when NAME+FRAME present; Stylist waits until structural moves stabilize; Reuser scans for repeated subtrees and proposes extraction.
- **Guards against:** premature styling, monolithic prompts, brittleness to phase ordering.
- **Built by:** Lu et al. 2025 (LLM-Blackboard), Confluent's event-driven multi-agent. None do *design phases*.

### Pattern D — MCTS-AHD over Markup Trees

- **Structure:** Each node = a candidate dd markup AST. Children = MOVEs applied. Selection by UCB1 with reward = scorer ⊕ VLM-judge. Expansion calls LLM with linkography context. Backprop updates parent stats.
- **Loop:** MCTS-AHD (ICML 2025) but with renderer-in-the-loop reward. Cheap rollout = compose + score; expensive rollout = render + VLM. Tier the budget.
- **Guards against:** myopic greedy refinement; never explores LATERAL MOVES it would otherwise prune as worse-immediately.
- **Built by:** Zheng et al. ICML 2025 for heuristic synthesis; nobody for UI design.

### Pattern E — Reflection Controller with Reified Phases (Wireframe → Component → Style)

- **Structure:** Hard phase gates. Phase 1 (Wireframing): only structural primitives allowed. Phase 2 (Componentizing): SEE-AS retrieves from corpus; subtrees get typed. Phase 3 (Styling): tokens bound, density-up on visual properties. A single Reflection Controller decides phase transitions based on stability.
- **Loop:** GameUIAgent's six stages, but with explicit phase semantics tied to dd markup density.
- **Guards against:** "style smear" — LLMs paint while wireframing.
- **Built by:** GameUIAgent (2026) has phases but no "no-styling-allowed" gate. SpecifyUI is closest with hierarchical SPEC.

**Recommendation: layer them.** E gives the temporal skeleton (the user's process). C is the runtime substrate. A is the meta-monitor watching the agent's own moves. B is how to handle SURPRISE. D is offline search when there's budget.

---

## 4. The design-space tree as a data structure

Two representations side-by-side: in-memory live tree, and serialized snapshot. Both mirror the markup AST + a thin agent-trace overlay.

**In-memory (controller manipulates):**

```python
DesignNode {
  id: ULID,                              # monotonic, sortable by time
  parent_id: ULID | null,                # null = root variant
  primitive: enum{NAME, FRAME, MOVE, LATERAL, DRILL, ...},
  edit: EditScript | null,               # the dd-markup edit that birthed this from parent
  spec_delta: dict | null,               # P/S co-evolution: spec changes accompanying the edit
  markup_ast_ref: blob_hash,             # content-addressed; reuse if unchanged
  render_ref: blob_hash | null,          # rendered PNG hash
  scores: { fidelity, vlm, lint, ... },  # scorer outputs
  embedding: vec[384],                   # for linkograph link inference
  status: enum{open, pruned, promoted, frontier},
  parent_links: [ULID],                  # cross-edges (graft from another branch) — makes it a DAG
  notes: str,                            # LLM's own rationale (one sentence)
  qoc: { question, option_of, criteria_hits },  # MacLean QOC overlay
}
```

Three orthogonal views over the same store:

1. **Tree view** — parent_id chains. Each branch = a non-destructive exploration.
2. **Linkograph view** — fully-connected weighted graph by cosine similarity of embeddings. Compute LDI/entropy live. Marks critical moves.
3. **QOC view** — flatten by `question`. Each design decision is a Question; sibling DesignNodes are Options; criteria are scorer dimensions. Lets you say "here are the 3 LATERALs we tried at 'how to handle long card titles' and here's why we picked Option B."

**On disk** — sqlite, mirroring our existing dd schema:
- `design_nodes` table (the struct above)
- `design_edges` table (cross-edges; tree edges live in parent_id)
- `design_artifacts` blob store (markup AST + render + scorer report, all content-addressed; never overwritten)
- `design_moves` event log (append-only; this is the input to live linkography)

**Key affordances:**

- **Non-destructive variant**: lateral moves create siblings, never overwrite. "Try B" = new node with same parent.
- **Graft**: parent_links lets you say "take subtree X from branch B, splice into branch C." Implementation: copy markup_ast_ref of subtree, splice via existing `apply_edits` (per `feedback_applied_doc_map_rebuild.md`).
- **Compare**: any two nodes diffable at three layers — markup AST, render PNG, scorer dims. Powers "side by side" UI.
- **Prune**: mark status=pruned but never delete. QOC view still references rejected options; useful as negative training signal.
- **Re-enter**: status=open frontier nodes are MCTS leaves. Controller picks one (UCB1) and resumes.
- **Promote**: status=promoted nodes seed the corpus (Mode-3 retrieval index). Critical moves with high scores → fragments.

This is essentially git's commit DAG specialized for design: commits are MOVEs, branches are LATERALs, cherry-pick is GRAFT. Onshape and the CAD-branching literature confirm the model works for parametric artifacts; nobody has done it for UI-AST + LLM-agent.

---

## 5. State-of-the-art systems (2025-2026)

The 19+ systems the SoTA-review subagent found that sit adjacent to "designer-agent loop":

| # | System | Key insight | URL |
|---|---|---|---|
| 1 | **PrototypeFlow / PrototypeAgent** (CHI 2025, TOCHI 2025) | Top-down multi-agent: Theme Design Agent clarifies intent, then dispatches specialized sub-agents (text/image/icon/retrieval). Designers can regenerate at any tier. | [arXiv:2412.20071](https://arxiv.org/abs/2412.20071) |
| 2 | **MAxPrototyper** (CHI 2024) | Earlier four-agent split (Theme + Text + Image + Icon) producing SVG/JSON. | [arXiv:2405.07131](https://arxiv.org/abs/2405.07131) |
| 3 | **UI Remix** (IUI 2026) | Multimodal-RAG over a curated UI corpus; explicitly distinguishes global vs. component retrieval and adds source-transparency cues. **Closest published precedent for what we want.** | [arXiv:2601.18759](https://arxiv.org/abs/2601.18759) |
| 4 | **Generative Interfaces for Language Models** (SALT NLP, 2025) | Per-query rubric generation followed by generate→score→refine loop until ≥90 score or 5 iterations. Adaptive rubric is load-bearing (-17% without). | [arXiv:2508.19227](https://arxiv.org/abs/2508.19227) |
| 5 | **AlignUI** (Jan 2026) | Inference-time alignment of LLM UIs to crowd-sourced user-preference data, no RLHF cost. | [arXiv:2601.17614](https://arxiv.org/abs/2601.17614) |
| 6 | **DesignPref** (Nov 2025) | 12k pairwise designer comparisons; Krippendorff α=0.25 between designers. Documents that aggregate preference is statistically the wrong target — personalization beats it 20× sample-efficiently. | [arXiv:2511.20513](https://arxiv.org/abs/2511.20513) |
| 7 | **Improving UI Generation Models from Designer Feedback** (Apple, CHI 2026) | Replaces ranking-style RLHF with comment + sketch + direct manipulation feedback (~1500 annotations). Outperforms GPT-5 baselines. | [arXiv:2509.16779](https://arxiv.org/abs/2509.16779) |
| 8 | **MLLM-as-UI-Judge** (Oct 2025) | Benchmarks GPT-4o/Claude/Llama against human ratings; >75% within ±1 on 7-point Likert; weaker on subjective dimensions. **Validates VLM-as-judge for UI specifically.** | [arXiv:2510.08783](https://arxiv.org/abs/2510.08783) |
| 9 | **UI2Code^N** (Nov 2025) | Open-source VLM unifying generate/edit/polish; trained with a "carefully designed verifier" RL stage. | [arXiv:2511.08195](https://arxiv.org/abs/2511.08195) |
| 10 | **LaySPA** (Sep 2025) | RL-trained layout designer on a structured textual canvas; multi-objective reward (geometric validity + relational coherence + aesthetic). Outperforms larger proprietary LLMs on layout. | [arXiv:2509.16891](https://arxiv.org/abs/2509.16891) |
| 11 | **LayoutVLM** (CVPR 2025) | Two-stage VLM: first emit pose+relation symbols, then *differentiable* optimization. Useful template for "produce IR, then optimize against a scorer." | [arXiv:2412.02193](https://arxiv.org/abs/2412.02193) |
| 12 | **AB-MCTS / Multi-LLM AB-MCTS** (Sakana, ICLR 2025 / NeurIPS 2025) | Adaptive branching MCTS over LLM samples; Thompson-sampled "go wider vs. go deeper." Multi-LLM extension cooperates across Gemini/o4-mini/DeepSeek. | [arXiv:2503.04412](https://arxiv.org/abs/2503.04412) |
| 13 | **GenSelect + Learning Generative Selection** (Jul 2025 / Feb 2026) | Replaces pointwise reward scoring of Best-of-N with a *generative* selector LLM that reasons across candidates. RL-trained 1.7B selectors beat majority voting. | [arXiv:2507.17797](https://arxiv.org/abs/2507.17797), [arXiv:2602.02143](https://arxiv.org/abs/2602.02143) |
| 14 | **OS-Themis** (Mar 2026) | Multi-agent critic that decomposes trajectories into verifiable milestones with an audit/review step. +10.3% online RL on AndroidWorld. | [arXiv:2603.19191](https://arxiv.org/abs/2603.19191) |
| 15 | **Luminate** (CHI 2024) | LLM first emits orthogonal *dimensions* of the design space, then a grid of variants per dimension. **Anti-fixation by construction.** | [arXiv:2310.12953](https://arxiv.org/abs/2310.12953) |
| 16 | **Beyond Code Generation: Pail** (CHI 2025) | Three-agent IDE: chat + design-decision tracker + alternatives surfacer. The "make implicit decisions explicit" framing transfers cleanly to UI. | [arXiv:2503.06911](https://arxiv.org/abs/2503.06911) |
| 17 | **ContextBranch** (Dec 2025) | Git-style checkpoint/branch/switch/inject for LLM conversations; 58% context reduction. **Direct primitive for non-destructive design exploration.** | [arXiv:2512.13914](https://arxiv.org/abs/2512.13914) |
| 18 | **Anthropic Frontend-Design Skill** | Five parallel domain searches (product/style/color/landing/typography) with explicit anti-convergence rules. The clearest production instance of "diversity as a hard constraint." | [github.com/anthropics/skills](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) |
| 19 | **Industry tools** | Google Stitch (5 connected screens per prompt + voice canvas + Gemini-3); [Claude Design](https://www.anthropic.com/news/claude-design-anthropic-labs) (codebase-derived design system, sliders); Adobe Firefly Assistant; Pencil.dev (MCP-bridged design state); v0.app (Git-panel branching of UI generations); [Vision2Web](https://arxiv.org/abs/2603.26648) (3-tier benchmark with GUI agent + VLM judge). | various |

### Recurring architectural patterns (in adjacent systems)

- **Theme/Director + Specialist Sub-agents** (PrototypeFlow, MAxPrototyper, Anthropic frontend-design): one coordinator owns intent, separate agents own text / image / icon / typography.
- **Generate → Self-Critique with Per-Query Rubric → Refine** (Generative Interfaces, UI2Code^N, ReLook). Adaptive rubric is the load-bearing piece.
- **Wide-then-deep test-time search** (AB-MCTS, parallel-then-GenSelect): branching factor is *adaptive*, not fixed.
- **IR-first, then differentiable / RL-tuned spatial optimization** (LayoutVLM, LaySPA).
- **Multimodal RAG over a curated UI corpus** (UI Remix, Pencil's UI kits, Stitch's component library).
- **Conversation-version-control** (ContextBranch, Pail, v0 Git panel): branch / checkpoint / inject as a *first-class* exploration primitive.
- **Designer feedback ≠ ranking** (Apple CHI 2026, DesignPref): commenting/sketching/direct-manipulation outperforms pairwise ranking.
- **Dimensional design-space generation** (Luminate, Anthropic's parallel-domain search): emit orthogonal axes *first*, then sample combinations — diversity by construction.

---

## 6. Four architectural sketches over our existing stack

Three the user requested + one unsolicited pitch. **Not exclusive — they share the substrate** (L3 markup + 7-verb edit grammar + capability table + DTCG cascade + SoM scorer + live Figma bridge). They differ on **where the LLM lives, what holds state across iterations, and how branching is represented**.

### Architecture 1 — "Senior + Junior + Librarian"

Three role-specialised agents over the same substrate. Closest in spirit to ADR-008 Mode-3 today (`dd/compose.py`) and `dd/repair_agent.py`, but elevates retrieval and critique to peers of generation.

```
                user brief / sketch / screenshot
                              │
                              ▼
   ┌─────────────────────────────────────────────────────┐
   │  SENIOR (Sonnet 4.6, planning + critique)           │
   │   reads: brief, last critique, decision-tree node    │
   │   writes: PlanSpec {archetype, axes_to_explore,     │
   │           N_variants, donor_query, deadline_axis}   │
   └─────────────────────────────────────────────────────┘
                              │ PlanSpec
                              ▼
   ┌─────────────────────────────────────────────────────┐
   │  LIBRARIAN (Haiku 4.5, RAG)                          │
   │   queries: corpus_retrieval, library_catalog,        │
   │   screen_patterns, compress_l3 (donor screens)      │
   │   returns: DonorPack {top-K screens, fragments,     │
   │           tokens vocab, masters list, patterns}     │
   └─────────────────────────────────────────────────────┘
                              │ DonorPack + PlanSpec
                              ▼
   ┌─────────────────────────────────────────────────────┐
   │  JUNIORS × N (Haiku 4.5, parallel)                  │
   │   each emits a single L3 doc through tool-use,      │
   │   constrained by capability table (ADR-001).        │
   └─────────────────────────────────────────────────────┘
                  │           │           │
                  ▼           ▼           ▼
              variant-A   variant-B   variant-C
                              │  apply_edits + render_figma
                              ▼  (dd/apply_render.py)
                ┌──── Figma bridge (live) ────┐
                │   walk_ref.js + bbox extract │
                └──────────────────────────────┘
                              │ screenshots + walk payload
                              ▼
   ┌─────────────────────────────────────────────────────┐
   │  SCORER (deterministic) — dd/fidelity_score.py      │
   └─────────────────────────────────────────────────────┘
                              │ DimVector × N
                              ▼
   ┌─────────────────────────────────────────────────────┐
   │  SENIOR critique pass                                │
   │   compares variants, picks winner OR replan         │
   └─────────────────────────────────────────────────────┘
```

- **Net-new code**: ~1,800–2,400 LOC (3 agent modules + orchestrator + state)
- **Cost per cycle (N=3)**: ~$0.16; 3-cycle session ~$0.50
- **First demo**: ~3 weeks
- **Risk to round-trip parity**: low (additive)

### Architecture 2 — "Pattern-Language Descent Tree"

Materialises `t5-pattern-language.md`'s decision tree as **a persistent, queryable, branchable data structure** with a single agent operating it. Closest fit to the user's stated cognitive model (steps 1–9). Re-entry on user feedback is the design's explicit purpose.

```
User brief
  │
  ▼
┌───────────────────────────────────────────────────┐
│  TREE_ROOT (DecisionNode, level=L0/intent)       │
└───────────────────────────────────────────────────┘
  │
  ├── child: SkeletonExpansion (level=L1)
  │     branches: A, B, C — three skeletons (Structure-only L3 docs)
  │     prune: rule-based + SoM coverage on rough render
  │
  ├── child of surviving skeletons: Elaboration (level=L2)
  │     branches: per-component slot fills, donor or universal
  │
  ├── child: Styling (level=L3)
  │     branches: theme A vs theme B (System-axis swap via tokens)
  │
  └── child: Critique (level=L4)
        scorer DimVector + senior LLM rationale
```

- **Net-new code**: ~3,200–4,000 LOC (tree CRUD + per-level expanders + pruner + orchestrator + steering + serde)
- **Cost per full descent**: ~$0.30 (4 Sonnet calls + N×3 Haiku critiques + 2 render cycles)
- **First demo**: ~4 weeks
- **Risk**: low (additive tables)
- **Where the LLM lives**: one Sonnet 4.6 agent called once per tree-expansion step. Tool schemas vary by level (L1: `emit_skeletons`; L2: `emit_slot_fills`; L3: `emit_styling`; L4: `emit_critique`).

### Architecture 3 — "Sketch → Donor → Edit Loop"

Editing IS the primitive. Synthesis is a degenerate case: editing an empty donor. Heaviest reliance on the corpus + 7-verb grammar.

```
User brief
  │
  ▼
[Brief → CoarseQuery (Haiku tool-use)]
  │
  ▼
[Retrieval (existing CorpusRetrievalProvider)]
  │  top-K donors (K=5) returned as L3Documents
  ▼
[Edit-plan generation × K (Sonnet 4.6)]
  │  for each donor, emit a sequence of 7-verb edits
  ▼
[apply_edits + render_figma + scorer × K]
  │
  ▼
[pick winner; if score < threshold → repair_agent loop, max 3]
```

- **Net-new code**: ~900–1,300 LOC
- **Cost per cycle**: ~$0.30 (1 Haiku query + K=5 Sonnet edit-plans + repair tail)
- **First demo**: ~2 weeks (cheapest)
- **Risk**: low. Reuses `corpus_retrieval` (already shipped) + `apply_edits` (M7.1) + `repair_agent` (M7.5) + `structural_verbs` (M7.4)
- **Synthesis case**: starting donor = empty L3Document

### Architecture 4 (the unsolicited pitch) — "Live Branching Canvas"

After reading the brief carefully, none of the three above fully match step 5 ("variations side-by-side, comparable visually") and step 9 ("up + down the abstraction ladder") **as a continuous experience**. The three above all treat each generation cycle as discrete.

**The pitch**: persistent branching canvas where every render is a leaf in a live, navigable git-of-design. Combines Arch 1's role-specialisation, Arch 2's tree as data, and Arch 3's edit-as-primitive — but reframes the user-visible loop as a **canvas of side-by-side variants** that the user can dive into, branch from, or merge between, **not a one-shot N-output gallery**.

- **Net-new code**: ~5,500+ LOC (includes a user-facing surface — HTML or TUI canvas)
- **Risk**: most novelty, least published precedent
- **First demo**: ~6 weeks
- **Why better**: step 5 is canvas-native, step 9 becomes click navigation, component-first start (step 8) is a special case (canvas root = component)

---

## 7. Comparison matrix

| Dim | Arch 1: Senior+Junior+Librarian | Arch 2: Pattern-Language Tree | Arch 3: Sketch→Donor→Edit | Arch 4: Live Branching Canvas |
|---|---|---|---|---|
| Net-new LOC | 1,800–2,400 | 3,200–4,000 | 900–1,300 | 5,500+ |
| Novelty (vs published) | medium | high | low–medium | very high |
| Risk to round-trip parity | low | low | low | low–medium |
| Cost per full cycle | ~$0.16 (3 variants) | ~$0.30 (4 levels) | ~$0.30 (5 donors + repair) | ~$0.40 amortised |
| Latency to first render | 60–90s (parallel) | 90–150s (sequential levels) | 60–90s | 60s (canvas async) |
| Fit to user's described workflow | partial — discrete cycles | strong — exactly the ladder | partial — donor-flavoured | strongest — canvas-native |
| Time-to-first-demo | ~3 weeks | ~4 weeks | ~2 weeks | ~6 weeks |
| Component-first start (step 8) | yes (Junior emits a `define`) | yes (root node = component) | yes (donor = a component) | native (filter the canvas) |
| Side-by-side variants visible (step 5) | yes (one shot) | yes (tree row) | yes (one shot) | always |
| Style-LATER (step 6) | requires Senior to skip Visual axis | natural (L3 is its own level) | requires Sonnet to omit Visual edits | natural |
| Reusability of M7.0–M7.6 | full | full | full | full |

---

## 8. The 8 honest gaps (what nobody has built — where we'd be novel)

1. **Phase-gated cognitive primitives.** Nobody enforces "wireframe-only primitives during Phase 1." Encode as typed primitive tables per phase, validated by ADR-001 capability table extension.

2. **Live linkography as a controller signal.** Fuzzy Linkography (2025) computes linkographs *post-hoc on humans*. No published system uses live linkograph entropy/critical-move detection to *steer the agent's own next move*. We have the move log already from `apply_edits`.

3. **Surprise-driven REFRAME.** Dorst & Cross's "default vs surprise" is theoretical. No agent decides "the spec was wrong" rather than "regenerate harder." Wiring: when scorer-delta exceeds threshold but VLM-judge is positive → propose spec mutation, not re-roll.

4. **QOC as agent self-explanation.** Every MOVE the agent commits should emit a QOC triple: what Question is this answering, what Option among siblings, against what Criterion. Cheap byproduct: design rationale is automatic.

5. **Component-first inversion.** User's step 8 ("3 modal styles, then assemble screens"). Inverted retrieval: instead of "find a screen like this," "find screens that *use* these components I just designed." Latent-space retrieval keyed on subtree embeddings.

6. **Vertical-climb feedback.** Component → screen propagation is unidirectional in every system found. When a card layout decision implies a page-level grid constraint, push that back up.

7. **Anti-fixation as first-class loop concern.** GenAI fixation literature names the disease but cures are prompt-level. Agent-level cure: linkograph entropy threshold → invoke FIXATION-BREAK primitive (persona swap, corpus shard switch, force a LATERAL with cosine-distance constraint > 0.6 from all prior siblings).

8. **Habitability scoring.** Gabriel's "habitability" / Alexander's QWAN — never operationalized for UI. Scorer is currently fidelity + VLM. Add "modifiability" — can a downstream edit grammar change one thing without breaking three?

---

## 9. Five unsolved problems where our substrate makes us uniquely positioned

These came from the literature search and they're all genuinely-novel paper-shaped territory:

1. **Edit-grammar-aware tree search.** AB-MCTS branches over free-form text. Our seven verbs are typed and finite, so we can reason about *inverse operations*, *minimum-diff to reach state S*, and *semantic dedup of edit traces*. Text-domain ToT can't touch this.

2. **Per-designer preference as retrieval, not fine-tune.** DesignPref shows aggregate preference is α=0.25 noise. Nobody has connected per-designer DPO with corpus-conditioned RAG; our corpus already carries authored examples that are implicitly per-designer-labeled.

3. **VLM-judge calibration *per design-decision dimension*.** MLLM-as-UI-Judge reports global accuracy. With our SoM coverage + classified-component corpus, we could publish dimension-conditional calibration ("VLM agrees with humans on hierarchy 88%, on color harmony 61%") and expose this to the search controller.

4. **Bidirectional ladder traversal as a search primitive.** Every published system goes either top-down or bottom-up. Going *up* the IR ladder mid-search ("this screen failed; abstract its failed region back to a slot, retrieve a different donor, re-concretize") needs our L0↔L3 invertibility.

5. **Sketch input as IR, not as image.** Apple's CHI 2026 result is the loudest signal that sketching is the right channel — but they treat the sketch as feedback. With our edit grammar, a sketch can be *parsed* into proposed grammar operations against a current state. Sketch2Code-style work is all open-ended pixels-to-HTML; sketch-to-edit-grammar is a wedge no surveyed system occupies.

---

## 10. Recommendation

**Stage 1: build Architecture 3 (Sketch→Donor→Edit) as the cheapest end-to-end demo (~2 weeks).** It reuses the most existing code (`compose_demo`, `swap_demo`, `repair_demo`, `structural_edit_demo` are already ~80% of the parts). Surfaces real failure modes at the smallest possible test of the whole loop.

**Stage 2: layer Architecture 2's persistent decision tree (~3 weeks).** Natural next step once Stage 1 reveals where the user genuinely wants to branch. The user wants step 9 (up/down the ladder) and that's *exactly* the decision tree. Don't build it before knowing which levels actually matter.

**Stage 3: harvest Architecture 1's senior/librarian roles into Stage 2's tree expansion (~2 weeks).** By this point the librarian is just a wrapper around what `library_catalog.serialize_library` + `corpus_retrieval` already do; the senior is just structured prompts around what's tested. They're features of the tree, not separate agents.

**Defer Architecture 4** unless Stage 2 demos drive the user to ask for a real canvas surface. Don't build the GUI before the underlying tree proves it deserves one.

### Why not start with Architecture 1
Senior/junior/librarian is closest to LangGraph / CrewAI / Anthropic-MAS demos, but it's also the most published. The user's brief explicitly invites going outside the request, and the project's competitive moat (per `requirements.md` §5 "capability table IS the grammar") is in the substrate, not the multi-agent ceremony. Architectures 2 + 3 lean harder on the moat.

### Why not start with Architecture 2
~4,000 LOC before the first demo renders. `plan-burndown.md` Tier A–B are explicit that we deferred infrastructure to demonstrate value first. Build the tree before knowing how the user wants to navigate it would burn budget on the wrong thing.

---

## 11. The minimal-additive proposal (post-cleanup user-confirmed framing)

After the user pushed back on building a parallel system ("don't build new, evolve existing"), the proposal narrowed to **~700 LOC of orchestration over existing primitives, no new IR / grammar / renderer / classifier / scorer** :

**Stage 1 (1 week, ~700 LOC, all orchestration):**

1. Migration 023 — `design_sessions` + `variants` + `move_log` tables.
2. `dd/agent/loop.py` — orchestrator that calls existing scripts and writes to those tables. Exposes designer-vocabulary tools to a single Sonnet 4.6 agent.
3. `dd/compose.py` — `phase` parameter gating axis emission via existing capability table.
4. `dd design` CLI — `dd design --brief "..."`, `dd design ls`, `dd design show <session>`, `dd design resume <session>`, `dd design branch <variant> --vary <axis>`.

**Demo at end of Stage 1**: `dd design --brief "a login screen for a fintech app"` runs through FRAME → SEE-AS → MOVE → SCORE → optional LATERAL on visual style → optional DRILL on the card → optional STYLE phase. Persists everything. User can `dd design resume <id>` and branch from any variant. Total cost per session: ~$0.20–0.40.

**Stage 2 (1 week)** — add the linkograph monitor + FIXATION-BREAK trigger.

**Stage 3 (optional, 1 week)** — minimal HTML index of the variants tree.

**Stage 4+ (defer)** — pattern accretion (auto-promote critical moves to fragments), sketch parser, multi-agent role split.

---

## 12. Decision points the user must weigh in on

Before any of this gets built:

1. **Workspace persistence model** — do we GC trees after N days, or keep forever? Affects DB scaling.
2. **User in loop or out** — autonomous to depth N, or pause for steering at every level?
3. **Sketch input** — promote it to Stage 0 (parse sketch → tree-root frame) or defer? It's the real wedge per Apple CHI 2026 but it's also a separate parser problem.
4. **Component-first inversion** — user's step 8. Same workspace, root node = component instead of screen. Worth confirming as a Stage-2 demo target.
5. **Multi-agent vs single-agent** — leaning single-agent with primitive-tool-calls. Multi-agent is published more, but the substrate makes it less necessary.
6. **Self-play / pattern accretion** — Stage 4 promotes CRITICAL MOVES from successful trajectories to fragments. The corpus EVOLVES. Worth designing a curator role for human review of promoted patterns?

---

## Sources

- [Schön — Designing as reflective conversation](https://creativetech.mat.ucsb.edu/readings/Schon1992_Article_DesigningAsReflectiveConversat.pdf)
- [Schön, The Reflective Practitioner — Saffer notes](https://odannyboy.medium.com/notes-on-donald-sh%C3%B6ns-the-reflective-practitioner-e67f753879d8)
- [Schön — Bringing Design to Software, Stanford HCI](https://hci.stanford.edu/publications/bds/9-schon.html)
- [Goldschmidt — Linkography (MIT Press)](https://mitpress.mit.edu/9780262027199/linkography/)
- [Fuzzy Linkography (Karimi et al. 2025)](https://arxiv.org/abs/2502.04599)
- [iGOAT — intelligent linkography (ScienceDirect 2026)](https://www.sciencedirect.com/science/article/abs/pii/S1071581926000431)
- [Cross — Designerly Ways of Knowing (1982 PDF)](https://www.makinggood.ac.nz/media/1255/cross_1982_designerlywaysofknowing.pdf)
- [Dorst & Cross — Co-evolution of Problem-Solution](https://oro.open.ac.uk/3278/)
- [Lawson — How Designers Think (Routledge)](https://www.routledge.com/How-Designers-Think/Lawson/p/book/9780750660778)
- [Tree of Thoughts](https://www.analyticsvidhya.com/blog/2024/07/tree-of-thoughts/)
- [Graph of Thoughts (Besta et al., AAAI 2024)](https://arxiv.org/abs/2308.09687)
- [MCTS for LLM-Based Automatic Heuristic Design (ICML 2025)](https://arxiv.org/abs/2501.08603)
- [SpecifyUI](https://arxiv.org/html/2509.07334v1)
- [Towards Human-AI Synergy in UI Design (PrototypeFlow)](https://arxiv.org/abs/2412.20071)
- [GameUIAgent](https://arxiv.org/html/2603.14724)
- [Sketch2Code](https://arxiv.org/html/2410.16232v1)
- [Luminate (CHI 2024)](https://dl.acm.org/doi/10.1145/3613904.3642400)
- [Understanding Design Fixation in Generative AI](https://arxiv.org/html/2502.05870v1)
- [Examining Barriers to Diversity in LLM-Generated Ideas](https://arxiv.org/abs/2602.20408)
- [Stiny — Shape Grammars overview](https://en.wikipedia.org/wiki/Shape_grammar)
- [Pattern Language (Wikipedia)](https://en.wikipedia.org/wiki/Pattern_language)
- [QWAN — Quality Without a Name](https://www.qwan.eu/about)
- [Gabriel — Patterns of Software (PDF)](https://www.dreamsongs.com/Files/PatternsOfSoftware.pdf)
- [Habitability and piecemeal growth — Akkartik](https://akkartik.name/post/habitability)
- [User Perspectives on Branching in CAD](https://arxiv.org/html/2307.02583)
- [Untangling the Timeline — version control in CAD](https://arxiv.org/html/2602.09236)
- [LLM-Based Multi-Agent Blackboard System](https://arxiv.org/abs/2510.01285)
- [Progressive Ideation — agentic AI for co-creation](https://arxiv.org/html/2601.00475v1)
- [QOC — Questions Options Criteria (HCI 1991)](https://www.tandfonline.com/doi/abs/10.1080/07370024.1991.9667168)
- [MAxPrototyper](https://arxiv.org/abs/2405.07131)
- [UI Remix (IUI 2026)](https://arxiv.org/abs/2601.18759)
- [Generative Interfaces for Language Models](https://arxiv.org/abs/2508.19227)
- [AlignUI](https://arxiv.org/abs/2601.17614)
- [DesignPref](https://arxiv.org/abs/2511.20513)
- [Improving UI Generation Models from Designer Feedback (Apple)](https://arxiv.org/abs/2509.16779)
- [MLLM as a UI Judge](https://arxiv.org/abs/2510.08783)
- [UI2Code^N](https://arxiv.org/abs/2511.08195)
- [LaySPA / LLMs as Layout Designers](https://arxiv.org/abs/2509.16891)
- [LayoutVLM (CVPR 2025)](https://arxiv.org/abs/2412.02193)
- [AB-MCTS (Sakana AI)](https://arxiv.org/abs/2503.04412)
- [GenSelect](https://arxiv.org/abs/2507.17797)
- [Learning Generative Selection for Best-of-N](https://arxiv.org/abs/2602.02143)
- [OS-Themis](https://arxiv.org/abs/2603.19191)
- [Beyond Code Generation / Pail](https://arxiv.org/abs/2503.06911)
- [ContextBranch](https://arxiv.org/abs/2512.13914)
- [Anthropic Frontend-Design Skill](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)
- [Claude Design (Anthropic Labs)](https://www.anthropic.com/news/claude-design-anthropic-labs)
- [Multi-Agent Tree of Thought (concept impl)](https://github.com/FradSer/mas-tree-of-thought)
