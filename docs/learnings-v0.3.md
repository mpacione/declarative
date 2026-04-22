# v0.3 — Learnings, Philosophy, Architecture Spec

Compiled from the 2026-04-17 / 2026-04-18 session that produced the v0.3 architecture. This document captures the **reasoning behind the architecture**, not just the architecture itself. The architecture doc (`architecture-v0.3.md`) is terse and operational; this doc is the conversation log that informed it.

Purpose: when a future session (me, or anyone) asks "why did we choose X over Y?", this is the source of truth. The architecture doc answers "what"; this doc answers "why."

---

## Part 1 — The arc from v0.1.5 to v0.3

### Where v0.1.5 landed
Mode-3 synthesis shipped at 12/12 VLM-ok on canonical 00g after five rounds of renderer-side forensic patches (H1, H2, R3, H7-reverted, Fix #1). Four defect classes were deferred: baked-× icon inheritance, image placeholders, horizontal layout collapse, meme-feed perf. The system worked but the fixes were accumulating as bandaids in the compose/render boundary.

### Where v0.2 landed
Architectural pivot to **corpus-fragment retrieval** from catalog-template synthesis. Built `CorpusRetrievalProvider`, populated SCI via `dd classify` (42,938 nodes classified, 338 skeletons), compose-layer splice with universal template fallback. Static fidelity came to zero-delta (retrieval didn't regress vs baseline) — but per-prompt VLM testing showed retrieval went 9→10 on 01-login, suggesting real visual improvement even where static metrics didn't detect it.

### The "stepping back" moment
In v0.2 the user asked: *"we HAVE A WORKING RENDERER. is it that for some reason, synthetic generation fundamentally does not work the same way? or is it something else."*

That question forced a pattern recognition across all the patches: the round-trip path succeeds because it feeds the renderer IR that was created by a real designer with real layout intent. Mode 3 fails because it synthesizes IR from scratch by stacking atomic components, which defaults to vertical-everything.

The reframe: **the renderer is fine. The gap is the QUALITY OF IR being handed to it.** Corpus retrieval helps — but only as long as the retrieval target exists. The deeper fix is to make synthesis look MORE LIKE round-trip: treat real corpus screens as donors, edit their IR rather than invent from scratch.

### The markup language question
Once the "edit IR, don't invent IR" stance was clear, the user raised the long-dormant markup-language question: "long ago when we started this project we talked about a markup lang - why wouldnt we try to build a rich expressive markup language..."

Archive archaeology found:
- `docs/archive/t5-pattern-language.md` (2026-03-31) — Pattern Language as 5-level compositional descent
- `docs/research/format-comparison-examples.md` — 8-format evaluation, custom DSL vs YAML verdict
- `docs/archive/t5-ir-design.md` — IR as flat element map with typed components

The T5 design had specified the architecture. The implementation had shipped a flat JSON IR and a Mode-3 composer that effectively compressed all five Pattern Language levels into one LLM call. The archive contained what we needed; the implementation had lost it.

This pattern — **critical architectural direction lives in the archive; the active docs drift from it** — recurred twice in this project. The first time was `dd classify` pipeline (built since T5 Phase 1, never run on current DB); we rediscovered it in v0.2. The markup language is the second. There is probably a third.

---

## Part 2 — Philosophical choices

These are the choices that differentiate v0.3 from other possible architectures. Each has a "why" that isn't in the architecture doc.

### Choice 1: The markup is the primary artifact, the JSON IR is implementation detail

Most design tools treat a proprietary binary or JSON shape as primary and text representations as exports. We inverted this. **The markup is canonical; the JSON IR is a rendering of the markup for the existing Python machinery.**

Why this matters:
- LLMs read and write text. A text-first IR is grammar-constrainable at emission.
- Humans review diffs. A text-first IR is PR-reviewable, git-diffable, version-controllable.
- One grammar serves multiple speakers. Generator, verifier, user, extractor all speak it.

The trade-off: the JSON IR becomes a derived artifact that must stay in sync with the markup. Round-trip tests enforce this.

### Choice 2: Density-per-node, not pipeline levels

The Pattern Language described 5 levels (Intent → Skeleton → Elaboration → Styling → Critique) as a compositional process. v0.3 explicitly reframes: **levels are a pipeline optimization (cheapest exploration order); they're not a markup-structural constraint.**

Why:
- Designers work at whatever density makes sense for the current decision — sometimes wireframe-only, sometimes jumping straight to full detail, sometimes mixing densities in the same screen.
- A sketch input IS a partial IR at Spatial+Structure density. Forcing it through Level 1 (pure skeleton, no spatial) loses information.
- Edit operations address any density at any point in the tree. Forcing "you must regenerate the whole Level 1 output to change something at Level 3" makes iteration expensive.

The reviewers (Reviewer 1) flagged that this reframe might be a straw man — the original Pattern Language never claimed levels were markup-structural. Fair critique. The reframe is a **clarification** rather than a reversal. What's new isn't that density-per-node is correct; it's that the implementation had drifted into treating levels as pipeline phases where all five happen in one LLM call.

### Choice 3: The IR never holds raw values — synthetic tokens fill cold-start gaps

`t5-pattern-language.md` line 73: *"Now the token vocabulary enters. Colors, typefaces, spacing, radii, shadows. This step is largely deterministic — the designer is choosing FROM the vocabulary, not inventing values."*

v0.3 preserves this principle and extends it for Scenario B (no design system). Raw hex values (`#FF5733`) are clustered at extraction time into synthetic tokens (`{color.synthetic.orange_3}`). Cold-start synthesis preloads universal defaults (shadcn-flavored). LLM grammar-constrained decoding ensures the emitter never produces a value outside the vocabulary.

Why:
- Enforces brand/system compliance structurally, not via review
- Prevents the "LLM hallucinates plausible hex" failure mode
- Keeps the IR semantically uniform across scenarios (tokenized, untokenized, mixed)

The reviewers flagged a real gap (Reviewer 1, Reviewer 3): between extraction and synthetic-token clustering, the IR *does* hold raw values. There's a window where invariant 7 is technically violated. This is an investigation target: either the invariant needs a "pre-clustering" exception, or clustering happens during extraction (not as a separate stage).

### Choice 4: One grammar, multiple speakers

Same syntax for:
- IR state (what a screen IS)
- Edits (diffs and patches)
- Patterns (reusable subtree definitions)
- Themes (token bundles)
- Archetypes (skeleton definitions)
- Constraints (system-level axes)
- Verifier feedback (proposed edits to fix issues)
- Extract output
- Synthesis output
- User authoring

Why: every boundary where two speakers use different grammars is a boundary where translation bugs live. ADR-007's unified verification channel exists because having 3 different error formats was fragile. One grammar across the whole system reduces boundary count.

Reviewer 3 flagged: ADR-001 (capability-gated emission) uses a capability table as the constrained-decoding source. The markup grammar is a second constraint source. Having two sources that must stay in sync reduces the benefit. This is investigation target #2: either derive the markup grammar from the capability table, or explicitly acknowledge two sources with documented sync logic.

### Choice 5: Named definitions as first-class

`define product-card { ... }` + `& product-card title="..."` with three parametrization primitives (scalar args / named slots / path-addressed property overrides).

Why: archetype libraries, theme files, component catalogs, and edit templates are all the same thing at different axis subsets. Collapsing them into one mechanism (`define`) reduces conceptual surface. The research thread (§Thread 3) found this pattern (scalar + slot + override) is the universal production pattern — Vue, React+children, Svelte 5, Figma all converge.

### Choice 6: Edit grammar with imperative verbs, not JSON-patch

Seven verbs: `set`, `append`, `insert`, `delete`, `move`, `swap`, `replace`. Not RFC 6902 JSON Patch.

Why: JSON Whisperer 2025 finding + Anka DSL 2025 result. LLMs emit verbs + keyword args at high reliability; they emit JSON Patch array-index arithmetic poorly. Ocaml-ish `set @eid prop=value` is parseable by both humans and constrained decoders.

### Choice 7: CRAG three-mode cascade

SCREEN_EDIT / COMPOSITION / SYNTHESIS as confidence-gated anchor modes. Published pattern (Corrective-RAG applied to structured design). Low score → synthesize from scratch; high score → edit donor IR directly; mid → compose subtree donors.

Why: unoccupied in shipping systems (the research record confirms this). The architecture mirrors what research systems (SpecifyUI, PrototypeAgent) have validated at small scale; we have corpus scale (42K classified nodes) they lack.

### Choice 8: Verifier emits edits, not scalar scores

GUI-Critic-R1 pattern: the verifier is an agent that inspects output and proposes specific edits in the same grammar the generator uses. Not "this screen scores 7/10" but "swap @submit to=button/primary/xl, set @card.radius={radius.md}".

Why: closes the feedback loop with structured action, not handwaving. Monotone-accept (ReLook) prevents reward hacking. Fresh-context critic prevents dialogue drift.

Reviewer 3 flagged: adding a `proposed_edits` field to the frozen `RenderReport` dataclass is a breaking schema change. Architecture called it "additive"; it isn't. Investigation target #3: explicit migration task, not hidden in the "shared grammar" framing.

---

## Part 3 — The debates this session had, and how they resolved

### Debate: is the combination novel, or are we reinventing something?

User: *"is anyone else doing this?"*

Answer after 5 parallel research agents: **no one is shipping the specific combination of bidirectional + multi-target + typed IR + round-trip fidelity + token-bound + retrieval-augmented at any scale**, but individual pieces are everywhere. Two enterprise attempts at formal IRs failed (Airbnb Lona 2019, Google Relay 2025 sunset). Closest academic match is Apple Athena/SQUIRE (Aug 2025). Closest commercial is Builder.io + Mitosis (multi-target, forward-only) and Figma Code Layers + MCP (bidirectional, no IR).

The user's response: *"this is not relevant right now. i was only asking to learn about how novel our thing is, not to turn into a business right now."*

Meaning: competitive landscape is context, not driver. v0.3 is built regardless. This resolved Reviewer 5's strategic pushback as out-of-scope.

### Debate: grammar for LLM or grammar for human?

User: *"llm friendly, but human readable. doesnt need to be designer - can be eng/technical reader."*

This is the load-bearing scope decision. Resolves Reviewer 4's critique (designer-usability) as out-of-scope. Justifies the sigil-heavy grammar (`@eid`, `#eid`, `->`, `&`, `{tokens}`, `#[provenance]`) that a designer would find unwieldy but a technical reader can learn in an afternoon.

### Debate: should the markup be the whole grammar, or multiple grammars composed?

Initial v0.3 draft: one grammar for everything.
Reviewer 1 found: this is false — the grammar has at least two modes (extract permits raw literals, synthesis prohibits them). ADR-001 capability table is a third constraint surface.

Resolution (pending next session investigation): decide whether "one grammar with validation-mode variants" or "explicit two grammars with shared syntax" is the honest framing. Either works architecturally; the current doc is imprecise.

### Debate: what goes in the IR, what stays in the DB?

The T5 four-layer architecture specified: **IR carries token references; DB carries raw values.** The renderer resolves from IR's token dictionary (which contains both real and synthetic token entries), falling back to DB for edge cases.

v0.3 preserves this. It's the single most important architectural decision — it's what makes the IR sparse and the markup LLM-emittable, because the LLM is choosing from a closed vocabulary.

### Debate: is the Pattern Language a process or a structure?

`t5-pattern-language.md` framed it as a process ("the compositional descent itself"). The implementation drifted into treating it as a flat single-level pass. v0.3 re-articulates: **it's a process; the IR is the structure. The process operates on the structure.**

Reviewer 1: this reframe is a straw man because the original never claimed levels were structural. Fair. Acknowledged in doc.

### Debate: should patterns be auto-extracted from corpus?

v0.3 says no — extract emits ground truth (INSTANCE → `->`, FRAME → inline); pattern detection is a separate optimization pass with Rule of Three (N ≥ 3). Users explicitly promote inline → pattern.

Why: round-trip invariant requires extraction to be lossless. Auto-deduplication at extract-time is interpretive and would break round-trip.

---

## Part 4 — What was deferred (and why)

### Taste model (quality-weighted distributions)

The T5 architecture-vision specified a taste model that separates "common / good / interesting" — statistical distributions derived from a curated corpus. v0.3 defers this. Without it, Best-of-N variant selection is driven by Jaccard fidelity + pairwise VLM, which don't encode taste (they encode similarity and image-quality).

Why deferred: taste calibration requires human rating data we don't have. Research record Part 6, item 6: required before shipping critic-refine loop (per GameUIAgent r=−0.96 finding) but not required for v0.3's goals on Dank.

### Decision tree as persisted data

T5 architecture-vision specified storing exploration history as a first-class data structure. v0.3 defers this.

Why deferred: matters when autonomous exploration + steering UX exists. For v0.3's internal-tool scope, git log on markup edits serves the same purpose. Revisit in v0.4.

### Second-project portability

Reviewer 4 flagged: our retrieval CRAG is entirely calibrated on Dank donors. A non-Dank project gets wrong thresholds, irrelevant donors, broken COMPOSITION mode.

Why deferred: v0.3 is explicitly scoped to "work on Dank." Second-project portability is a v0.4 goal. The architecture is designed so this is addable later (retrieval thresholds become per-project calibrations, corpus queries become project-scoped), but the validation requires real second-project data.

### Multi-target renderers beyond Figma

Architecture §6 specifies the multi-target catalog schema. v0.3 doesn't ship React / SwiftUI / Flutter renderers.

Why deferred: the schema shape is the load-bearing decision (it's the extension point). Actual renderers require significant per-target work (Mitosis if React/Vue; hand-built if SwiftUI). v0.3 validates the schema can hold the right shape by including it forward-compatibly; real renderers ship later.

### Full action taxonomy Tier 1–4 operations

v0.3's 7 edit verbs cover Tier 5 (conjure). Tier 1–4 (cleanup, semantic, generative, structural token-system operations from `action-taxonomy.md`) require grammar verbs that don't exist.

Why deferred: these are token-system governance operations, not UI-composition operations. They can be implementable "on top of" the shared grammar but require verbs like `define-token`, `bind`, `rename`, `merge`. The architecture doc flags this as an open item (Reviewer 1 correctly noted the "one grammar" claim is compromised here).

---

## Part 5 — What we learned about the problem space

### Enterprise IRs failed when they pre-dated LLMs

Airbnb Lona (archived 2019) and Google Relay (sunset April 2025) both tried formal design IRs with multi-target generation. Both died. Common failure mode: **rigid IR that had to express everything structurally, with no graceful fallback.** Pre-LLM, this meant designers had to author in the tool's IR language, or the extractor had to be perfect.

Post-LLM, the game changes. LLMs provide fallback — when the IR can't express something, the LLM wrapping the pipeline compensates. v0.3 bets on this: progressive-fallback IR + LLM-as-co-author + verification channel catching silent errors.

This is a contrarian bet. The industry (Uber uSpec 2026, Figma MCP 2025) explicitly chose "LLM-as-translator, NO typed IR." v0.3 bets the opposite — that LLMs make typed IRs VIABLE for the first time, because the LLM is the fallback that brittle pre-LLM IRs lacked.

### The consensus has converged to scaffolded IRs

Apple (Athena + SQUIRE), Zhejiang (SpecifyUI), UICopilot — all 2025 papers — converged on "scaffolded IR with typed intermediate layer" as the accepted frame. v0.3 is aligned with research frontier, not isolated.

### The corpus is the moat

42,938 classified nodes from 338 round-trip-verified screens is unmatched at research or shipping scale. SpecifyUI has 2k pairs. UI Remix has 900 screens. v0.3 can build CRAG-style retrieval with confidence because the corpus is dense enough to give decent coverage across archetypes.

Reviewer 4 flagged: this is a Dank-only moat. Second-project portability is deferred. True moat requires the extractor+classifier to work on any Figma file. That's achievable (the extractor is file-agnostic); it's just untested.

### Round-trip parity as a metric is load-bearing even if no customer buys it

Reviewer 5 dismissed 204/204 parity as "engineering elegance that doesn't sell." For v0.3's internal scope, this critique is irrelevant — parity is how we verify the architecture works. But even post-v0.3, round-trip parity is what prevents the Google-Relay failure mode: when the IR lies (gradient round-trip format drift, ordering bugs, etc.), rigid IRs silently corrupt output. Parity catches drift.

### Markup language comes from archive research but implementation drifted

The single biggest meta-learning: **valuable architectural research exists in the archive; active development drifts from it over iterations.** The Pattern Language, the IR specification, the four-layer architecture, the action taxonomy — all specified in detail, all predate actual implementation by 6+ months, all forgotten by the time implementation was shipping.

Future-me: **when adding a feature, first grep the archive for whether it was already specified.** This session found the markup language design; the previous session found the classification pipeline; two for two on "the answer was in the archive."

### Ship-risk compromises drift architectural principles (2026-04-18 late-late session)

This session elaborated the markup compressor + decompressor to Option A (dict IR canonical on render path; markup lowers to dict IR). The rationale at the time was ship-risk minimization: rewriting the Figma renderer to walk markup AST would take 2-3 weeks with parity-recovery in the middle, vs. writing only the compressor and letting the existing 204/204 renderer consume the dict-IR output unchanged.

The problem surfaced during a Figma sweep on the Option A path: 0/3 pixel parity on the smoke test. Root-cause analysis produced:
1. Dict-IR identity drift (counter-based element keys diverge between baseline `generate_ir` and the decompressor's AST walk).
2. Content drift (fill/bounds/effect mismatches from decompressor bugs).

The fix for (1) was a compile-time side-channel (`$ext.spec_key`) pickling the dict-IR counter key into the markup so the decompressor could reproduce it. Working through it I noticed: this is **scaffolding for a system that's meant to be demolished**. Every Stage 2+ feature (pattern expansion, synthetic tokens, synthesis, multi-backend) would accrete dependencies on the dict-IR intermediate and the side channels preserving its identity.

We then traced the architectural stance through the doc stack:
- Tier 0 §6 lists L0-L3 as the MLIR levels. Dict IR is NOT listed.
- `learnings-v0.3.md` Choice 1 says **"The markup is canonical; the JSON IR is a rendering of the markup for the existing Python machinery."**
- `canonical-ir.md` mid-session revision said "dict IR remains canonical on the render path; markup lowers to dict IR."

The three documents were pointing in different directions. The Choice 1 statement was the TRUE philosophical stance from the beginning. The canonical-ir mid-session revision was a ship-risk compromise that drifted from it.

**Decision: pivot to Option B** (markup-native renderer). ~1 week additional work vs. continuing Option A, paid once against carrying scaffolding through every subsequent stage. Documented in `docs/decisions/v0.3-option-b-cutover.md`.

Meta-learning: **when ship-risk compromises drift from the doc stack's stated philosophical principles, they accumulate hidden cost through every subsequent layer.** The tell in this case was the second `$ext.*` side-channel (one was arguably fine; two signaled a pattern). Grep-check: if the same flavor of workaround is about to be added twice, stop and re-read the principles.

Related: the sweep-driven validation was ESSENTIAL. The Tier 2 script-size ratio of ~0.98 that we celebrated earlier masked real semantic divergence. Byte-parity is the spec claim; approximate parity doesn't count. **Ratio ≠ byte-parity. Script-size ≠ script-identity.** Every future parity claim needs to match the spec's actual criterion, not a near-miss approximation.

---

## Part 6 — The architecture spec (compressed)

Single-page reference. Full detail in `architecture-v0.3.md`.

### IR / markup

- **Five axes per node**: Structure, Content, Spatial, Visual, System
- **Density per node**: any axis subset is valid
- **Values**: token-ref `{path}`, raw literal (`#hex`, `"text"`, `123`), component instance `-> key`, pattern reference `& pattern.name`
- **Node identity**: `#eid` declares, `@eid` references
- **Provenance (optional)**: `(retrieved src="donor:142" conf=0.9)` inherits; `#[user-edited]` trailer per-value

### Edit grammar

- 7 imperative verbs: `set`, `append`, `insert`, `delete`, `move`, `swap`, `replace`
- Keyword args: `to=`, `from=`, `into=`, `after=`, `position=`
- Always by stable eid, never by positional index
- `set` is implicit in property-assignment sugar: `@card-1 radius={radius.lg}`

### Definitions

- `namespace <name>` at file top
- `use "path" as alias` with mandatory alias
- `define name(args) { body }` with three parametrization primitives:
  - Typed scalar args: `title: text = "Product"`
  - Named slots with defaults: `slot action = button/primary(...)`
  - Path-addressed property overrides at call site: `& product-card card.fill=black`
- Expansion produces `scope@N` auto-positional paths; explicit alias via `as name` or `#id`
- Hard-error on cycles (three-color DFS)

### Pipeline (internal tool, Dank-only)

0. Prerequisites done: 42K classified, 204/204 parity, 1,950+ tests
1. MVP: markup parser + emitter + 20-screen round-trip (~2 weeks, **pending investigation prereqs**)
2. Definitions + references + cycle detection (~1 week)
3. Synthetic tokens for cold start (~3 days)
4. Edit grammar + CRAG three-mode cascade (~2 weeks)
5. Verifier-as-agent tiered ladder + Best-of-N (~1 week)
6. Multi-target catalog schema (optional for v0.3 ship) (~1 week)

### Invariants preserved from v0.1.5 / v0.2

- 204/204 round-trip parity on Dank Experimental
- 1,950+ unit tests green
- ADR-001 capability-gated emission
- ADR-002 null-safe Mode 1
- ADR-006 structured error channel
- ADR-007 unified verification channel
- Leaf-parent gate (Fix #1)

---

## Part 7 — Open architectural questions (investigation targets)

These are the reviewer findings that must be resolved before MVP Stage 1 begins. Listed here as learnings for future context; tracked operationally in `archive/continuations/continuation-v0.3-next-session.md`.

### Open Q1: Underscore field representation

The IR carries 5 underscore fields (`_node_id_map`, `_mode1_eligible`, `_corpus_source_node_id`, `_original_name`, `_composition`) consumed at 14+ renderer sites. Each may need a different representation decision in markup:

- Grammar first-class (add syntax)
- Bridge-time computed (document reconstruction logic)
- Opaque pass-through state (document contract)

The wrong answer for any one breaks round-trip parity. `_corpus_source_node_id` as a raw integer also technically violates invariant 7.

### Open Q2: Grammar modes (raw vs token-only)

The extract path legitimately holds raw values in the IR pre-clustering. The synthesis path is grammar-constrained to token refs only. The v0.3 doc claims "one grammar" but these are different validation modes.

Investigation: either acknowledge two explicit modes with shared syntax, or reframe as "one grammar with mode-specific validation rules."

### Open Q3: RenderReport schema extension

Verifier-as-agent emits edit-grammar actions via `RenderReport`. But `RenderReport` is a frozen dataclass. Adding a `proposed_edits` field touches boundary.py, verify_figma.py, every consumer, the sweep runner. Not "additive" — a breaking schema change.

Investigation: explicit migration plan in Stage 5, not handwaved in "shared grammar" framing.

### Open Q4 (minor): `_UNIVERSAL_MODE3_TOKENS` duplicate keys

`space.generic.padding_x` appears at compose.py:444 AND 446 with different values; `space.generic.padding_y` at 447 overrides 445. Python dict last-write shadowing; production vocabulary doesn't match docs.

Trivial fix. Do during Investigation.

### Open Q5 (scope refresh): MVP calendar

Reviewer 2's analysis puts 100% round-trip on 20 screens at 20-35% probability in 2 weeks. Possible responses:

- Reduce scope (grammar-completeness only)
- Expand calendar (3-4 weeks)
- Both (grammar-first in 5 days, round-trip-proper in 2 weeks more)

User decision: both goals required. Calendar re-evaluated after investigation.

---

## Part 8 — Navigation

| Document | Purpose |
|---|---|
| `docs/architecture-v0.3.md` | Canonical architecture. Terse, operational. |
| `docs/archive/continuations/continuation-v0.3-mvp.md` | MVP implementation plan (blocked on investigation). |
| `docs/archive/continuations/continuation-v0.3-next-session.md` | Next-session priorities: investigation tasks. |
| `docs/research/v0.3-architecture-research.md` | 18-thread research record. Source provenance for every decision. |
| `docs/reviews/v0.3-reviews-full.md` | Full reviewer reports (all 5). |
| `docs/reviews/v0.3-review-synthesis.md` | Synthesis + post-decision framing. |
| `docs/learnings-v0.3.md` | **This doc** — philosophical choices + debates + learnings. |
| `docs/archive/t5-*.md` | T5 archive — Pattern Language, IR design, four-layer architecture. Load-bearing historical context. |
| `docs/architecture-decisions.md` | ADR-001 through ADR-008. All remain in force. |

---

*The architecture docs say WHAT. This doc says WHY. When the WHY is lost, the WHAT drifts.*
