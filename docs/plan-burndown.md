# Plan — Tiered Burn-Down (Execution Layer)

**Status**: ACTIVE. Authored 2026-04-21 following a 4-subagent deep-dive
review of the codebase + a vision/Alexander/multi-backend/performance
lens critique.

**Supplements**: [`docs/plan-synthetic-gen.md`](plan-synthetic-gen.md)
§4-§5 (the M7 milestone plan). This doc is the **execution layer**:
how we sequence the open work, not what the work is.

**Authority**: Until superseded, this is the active sequence. The
M7 milestone numbering still applies for exit criteria — this doc
reorders how those milestones get actually built.

---

## Why a separate execution plan

`plan-synthetic-gen.md` numbers milestones M7.0 → M7.8 in logical
dependency order: library first, then verbs, then composition. That
ordering is correct for understanding *what* depends on what; it's
wrong for *when* to build what.

Four load-bearing lenses drove the reorder:

1. **Vision lens**: the product is "designer prompts → screen."
   Infrastructure exists to serve that. A burn-down that delays
   composition to week 3 is a burn-down that delays demonstrating
   value for three weeks.
2. **Alexander lens** (per
   [`plan-synthetic-gen.md`](plan-synthetic-gen.md) §1.2): scale-
   agnostic entry (component / subtree / screen / variant), force-
   resolution over lookup, semi-lattice over tree. Dependency
   ordering violates semi-lattice. Build at the smallest scale
   first — the cheapest test of the mechanism.
3. **Multi-backend lens**: React / HTML / Android renderers are
   planned. Every Figma-specific coupling baked in now becomes
   later debt. A `RenderProtocol` abstraction sketched early
   prevents the scorer, repair loop, and composition from binding
   to `FigmaRenderVerifier` concretely.
4. **Performance lens**: render cycle is 60-180s, VLM calls cost
   money + have 30% transient error rate (per
   [`feedback_vlm_transient_retries.md`](../../.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_vlm_transient_retries.md)).
   Every tier adds cost. Tiers need explicit $ and latency budgets,
   not hand-waved "cross-cutting."

The tiered burn-down reorders work by "what demonstrable synthesis
capability does this tier deliver?" rather than "what infrastructure
layer are we on?"

---

## Out of scope for this plan

These items stay on the roadmap but aren't being tackled in this
sequence:

- **GBNF / XGrammar grammar-constrained decoding** — Claude tool-use
  is sufficient for current decode.
- **M7.8 M6(b) trigger evaluation** — decision doc, not
  implementation.
- **React / HTML renderer** — zero code today; Tier E's RenderProtocol
  audit is the prereq.
- **Second-project validation** — Dank-only today; this validation
  is post-v0.1.

---

## Tiered structure

### Tier A — Unblock composition (1-2 days)

**Goal**: make composition output visually non-broken.

| Task | Detail |
|---|---|
| **A.1** | **Mode-3 H1 template-propagation fix.** Extract the template style/layout merge block in `dd/compose.py` to `_apply_template_to_parent()`. Call unconditionally (currently only fires when element has no children). Extend merge allowlist to include `shadow`, `padding`, `gap`. See [`feedback_mode3_visual_gap_root_cause.md`](../../.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_mode3_visual_gap_root_cause.md) for diagnosis and [`docs/research/mode3-forensic-analysis.md`](research/mode3-forensic-analysis.md) for the forensic breakdown. This is a three-source-confirmed blocker (research / memory / docs). |
| **A.2** | **`rebuild_maps_after_edits` extended for Tier-B's verbs.** Currently swap-only (per `feedback_applied_doc_map_rebuild.md`). Add append / insert (new-node-no-original branch) and set (already works at AST level, but confirm map stability). Defer delete / replace until Tier D/E need them. TDD per verb. |
| **A.3** | **Visual assertion, not just `is_parity=True`.** Per [`feedback_verifier_blind_to_visual_loss.md`](../../.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_verifier_blind_to_visual_loss.md), structural parity can coexist with visual-loss defects. Before-and-after screenshot of an `m7_compose_demo` run, committed as test artefacts, locks in that H1 uplift is real. |

**Deliverable**: `m7_compose_demo --render` produces output where the
composed parent has fill/stroke/radius/shadow/padding preserved from
the donor template. PNG committed as before/after evidence.

**Budget**: 1-2 days. 2 days if Mode-3 refactor is deeper than
expected.

---

### Tier B — Smallest Mode-3 demo end-to-end, observe failures (2-3 days)

**Goal**: ship the cheapest possible synthesis demo and write down
what breaks.

Alexander's scale-agnostic entry principle: component scale is the
smallest — smallest inputs, smallest output, smallest room for
error. It's the cheapest test of the whole mechanism.

| Task | Detail |
|---|---|
| **B.1** | **Read `docs/spec-dd-markup-grammar.md` §8.5** to confirm whether S4.1 `define` grammar is shippable. If `define` syntax is uncertain, pivot Tier B to S4.2 at component granularity ("compose this 3-node button subtree"). |
| **B.2** | **One end-to-end synthesis demo.** Prompt → Mode-3 compose → render → screenshot. No scorer yet (built Tier C). |
| **B.3** | **Failure-mode inventory.** `docs/learnings-tier-b-failure-modes.md` — a written log of what the LLM got wrong, what Mode-3 dropped, what the library didn't cover. This is the input to Tier C's scorer design. |

**Deliverable**: one committed PNG + one failure-mode doc.

**Budget**: 2-3 days. Cost: ~$1-3 in Claude Haiku calls.

---

### Tier C — Judge + protocol + budget, scoped to Tier B (2 days)

**Goal**: build the scorer designed against what actually broke in
Tier B, not against an imagined 5-dim rubric. Sketch multi-backend
protocol to prevent Figma-lock-in debt.

| Task | Detail |
|---|---|
| **C.1** | **`dd/render_protocol.py`**: an ABC with `render(ast) → bytes`, `walk(rendered) → dict`, `verify(ast, walk) → RenderReport`. Current `FigmaRenderer` / `walk_ref.js` / `FigmaRenderVerifier` trio becomes the first concrete impl. Zero behavior change; pencils in the abstraction. |
| **C.2** | **VLM scorer** (`dd/fidelity_score.py`): scoped against Tier B's observed failures, not a generic 5-dim. If Tier B's inventory says "cards lose shadows" + "text sometimes overflows," the scorer tests *those things*. Per [`feedback_vlm_transient_retries.md`](../../.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_vlm_transient_retries.md), wrap in a 2-3× retry harness. Per [`docs/research/evaluation-rubric-calibration.md`](research/evaluation-rubric-calibration.md), target ≥7/10 (equivalent to ≥3/5 on a 0-5 scale); don't add a second VLM (cross-VLM ICC ≈ 0). |
| **C.3** | **Force-resolution test.** Alexander's guard: same donor, different forces (prompt context) → must produce distinct concrete. Without this test, the mechanism is Gang-of-Four lookup pretending to be generative. Concrete: compose the same donor card in two different prompt contexts; assert the outputs DIFFER on at least one visual property. |
| **C.4** | **Performance + cost budget**: `docs/perf-budget.md`. Log $/synthesis, sec/synthesis, memory/synthesis. Set soft caps per tier going forward. |
| **C.5** | **Patterns at scale**: lower `min_screens` to 2, sweep all canonical types via `scripts/m7_extract_patterns.py`. (Moved from original T1.6 — per subagent critique, patterns are synthesis vocabulary, not verification.) |

**Deliverable**: `dd/render_protocol.py` + `dd/fidelity_score.py` +
`docs/perf-budget.md` + expanded `patterns` table.

**Budget**: 2 days. Cost: ~$2-5.

---

### Tier D — Scale composition, gated by Tier C (3-5 days)

**Goal**: compose at multiple scales, each scored + gated.

| Task | Detail |
|---|---|
| **D.1** | **Populate `screen_skeletons`** — prereq for D.3. Extraction pass over the Dank corpus: compute skeleton notation per screen, persist. |
| **D.2** | **S4.2 subtree compose (re-gated)**. `m7_compose_demo` — shipped, now routed through Tier C's scorer at ≥7/10. |
| **D.3** | **S4.3 screen-from-archetype**. Load `dd/archetype_library/skeletons/` + populated `screen_skeletons`. Prompt → archetype classifier → skeleton → LLM fills slots. |
| **D.4** | **S4.4 pure SYNTHESIS fallback**. When no archetype matches, fall through to Mode-3 generic. |

Each demo gated at ≥7/10 Tier-C rubric. If a demo scores <7, the
repair loop (Tier E) gets engaged.

**Deliverable**: three compose demos (subtree / archetype-driven
screen / SYNTHESIS), all scored.

**Budget**: 3-5 days. Cost: ~$5-15.

---

### Tier E — Parallel / ongoing (alongside A-D, not blocking)

These items can run in parallel with A-D. They close hardened edges
without blocking critical-path delivery.

| Task | Detail |
|---|---|
| **E.1** | **Repair loop vs real `FigmaRenderVerifier`**. Currently uses synthetic `TextExpectationVerifier`. Swap in Tier C's scorer + the real verifier's hints (already populated on KIND_TYPE_SUBSTITUTION + KIND_MISSING_CHILD). |
| **E.2** | **Forces at scale**: batch 500-1000 rows through `scripts/m7_label_forces.py`. Alexander's force-resolution substrate. |
| **E.3** | **Shadcn cold-start spike**. `dd/composition/providers/ingested_system.py` backfills components from a canonical library (shadcn/Material-3-kit) so synthesis works on projects without ingested corpora. Per [`docs/research/style-induction.md`](research/style-induction.md) v0.1 scope. |
| **E.4** | **Human-reject UX spike**. Tiny CLI or artefact writer: how does a designer say "no, not that" on a synthesis proposal? Doc-level for now; real UX later. |
| **E.5** | **Hygiene**: delete zombies (`dd/rebind_prompt.py`, `dd/classify.py` legacy, `dd/m7_slots.py`), fix broken import at `dd/composition/providers/corpus_retrieval.py`, bridge timeout env-configurable, eid-collision guard in `m7_duplicate_demo.py`. |

**Budget**: overlaps A-D; estimate 1-2 days of effective work,
spread across the sprint.

---

### Tier F — Deferred until signal

Don't schedule. Promote when the signal is real.

| Task | Signal to promote |
|---|---|
| **F.1** Variant composition (S4.5/S4.6) | Tier D exposes variant needs; depends on `variant_token_binding` populated |
| **F.2** Render+verify for S1/S2 verbs not on Tier D path | A regression appears; otherwise trust shipped structural-verify |
| **F.3** M7.7 S5.1 pattern→template promotion | Tier C's scaled patterns surface high-confidence candidates |
| **F.4** M7.7 S5.3 screenshot→markup | User request or multi-backend parity need |
| **F.5** Full M7.0.f sticker-sheet reconciliation | Tier D compose needs overriding M7.0.b/c heuristics |
| **F.6** Full multi-backend audit + second-renderer impl | Second backend actually starts; Tier C's RenderProtocol is starter |

---

## Critical path

**A (1-2d) → B (2-3d) → C (2d) → D (3-5d)** = **8-12 days**.

Tier E is parallel, no critical-path time.

Tier F is deferred.

If any tier overruns by >50%, stop and reassess — the plan is wrong
somewhere.

---

## Architectural constraints (non-negotiable)

Inherited from ADRs and memory. Re-listed because burn-down execution
often erodes them if not watchdog'd:

1. **Capability-gated emission** (ADR-001): every rendered property
   is per-backend capability-checked. Tier C's scorer + Tier D's
   compose must not bypass this.
2. **No raw values in synthetic IR**: every `fill` / `radius` /
   `spacing` is a token ref. Tier B/D must reject LLM outputs with
   hex literals or pixel numbers.
3. **Force-resolution, not lookup** (Alexander): Tier C.3 test
   enforces this.
4. **Structural parity is necessary but not sufficient** (per
   `feedback_verifier_blind_to_visual_loss.md`): every tier's
   `is_parity=True` claim must be paired with a visual gate.
5. **Round-trip baseline preserved**: every commit keeps the
   204/204 Dank sweep green.
6. **Unified verification channel** (ADR-007): visual-loss kinds
   get their own `KIND_*` with hints.
7. **Scale-agnostic entry**: Tier B ships at component scale; Tier
   D ships at screen scale; neither is privileged in the IR.

---

## Decision log

**2026-04-21 (this doc's authorship session)**:

- T0-T5 (from the first draft) deprecated in favor of A-F.
- Critical-path pivot: **defendant before judge**. Tier B (demo)
  ships before Tier C (scorer). The scorer is scoped to what Tier
  B actually breaks.
- RenderProtocol ABC moved from original T5 to Tier C, pre-emptive
  before Figma-binding debt accumulates.
- Force-resolution test added as Tier C.3 (invisible in the
  original T0-T5).
- "Verify existing work" as a standalone tier deleted: work that
  moves the vision gets verified along with doing it; work that
  doesn't gets deferred to Tier F.
- Shadcn cold-start + human-reject UX added to Tier E (invisible
  in original).
- Performance budget concrete in Tier C (originally hand-waved).

---

*Update this doc as the burn-down proceeds. Promote Tier F items
when signals warrant. Record decisions that contradict the current
ordering in the log above.*
