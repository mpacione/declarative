# Plan — Synthetic Screen Generation + Editing

**Status:** v2 — decisions locked in the 2026-04-19 session. Replaces the v1 draft.
**Scope:** Priority 1 on the roadmap. Builds on the v0.3 markup-native foundation (complete 2026-04-19).
**Successor to:** the archived `docs/archive/t5-delivery-plan.md`. This doc is the current authoritative plan; the archived one predates the v0.3 cutover and should be consulted only for historical intent.

**Envelope:** ~5–8 months calendar at full commitment. Not a weekend project.

---

## 1. What we're building

Three capabilities that collapse to one underlying mechanism:

1. **Full unit synthesis** — produce a new L3 markup document for a requested unit (screen / component / subtree) from a prompt.
2. **Unit editing** — mutate an existing L3 document with targeted changes.
3. **Variation generation** — produce related L3 documents from one starting point.

All three reduce to **"apply edits to a starting IR."** The starting IR varies: empty AST (synthesis), donor AST (editing), reference AST + mutations (variation). The *mechanism* — LLM emits edit statements, engine applies them, renderer + verifier round-trip — is shared across all three.

### 1.1 The CRAG three-mode cascade is scope-polymorphic

The CRAG cascade (from ADR-008) runs identically at every scale: screen / component / subtree / variant. The mode choice depends on *how much donor or skeleton is available for the requested unit*, not on the unit's size. Christopher Alexander's "A Pattern Language" named this structure — a pattern language is a **semi-lattice, not a tree**, and designers legitimately enter it at any scale they want.

Scopes the cascade runs at:
- **Screen** — full app screen. Largest unit.
- **Component** — a reusable `define` (button, card, nav-bar, toolbar, field-input, etc.). Often parametrized with slots.
- **Subtree / fragment** — a contiguous piece of a screen's tree that isn't yet promoted to a component (a headline + subtitle cluster, a 3-card grid).
- **Variant** — a related sibling to an existing unit (button/hover from button/default).

Three modes within each scope:
- **EDIT** — high-confidence donor available → targeted edits → render + verify. *"Edit this nav-bar to add a search slot."*
- **COMPOSITION** — partial match → assemble via refs + exemplar subtrees → render + verify. *"Compose a card using our existing header-row and action-strip fragments."*
- **SYNTHESIS** — no donor at the requested scope → emit from universal catalog + prompt → render + verify. *"Give me a pricing tile"* when no such thing exists in the corpus.

The mechanism is identical across scopes. The only differences are (a) how much of the starting IR comes from retrieval vs. prompt-fill, and (b) what level of the L3 tree the generated/edited unit occupies.

**Most real synth-gen requests are NOT full-screen synthesis.** They're "add a button here," "swap this card variant," "make me a nav bar like the ones elsewhere in the product." The ladder in §4 is structured with this in mind: every screen-scope action has a component-scope twin.

### 1.2 Alexander's three load-bearing principles

Pulled from the research agent's digest of Alexander's 1977 *A Pattern Language*, 1979 *The Timeless Way of Building*, and 1964 *Notes on the Synthesis of Form*:

1. **Scale-agnostic entry is structurally correct.** APL explicitly instructs readers to enter the pattern graph at whatever scale their current problem sits at and navigate outward in both directions. Designers thinking screens-first and components-first are both doing valid things; the IR must not privilege one traversal order.

2. **The overfitting guard is force-resolution.** Alexander: *"The same CARD pattern applied to a product listing and to a user profile should produce different results because the forces are different. The pattern names the invariant relational structure; local context determines the concrete form."* Our system's answer: always reference + override (`swap @card with=-> card/default` + property `set`), never copy + hand-modify. The capability table is the force-resolution domain; the library is the vocabulary.

3. **Piecemeal growth beats full planning.** Alexander: *"When we apply a pattern, we don't copy it. We use it as a generator — the forces it names shape the local situation."* The 1964 → 1977 arc: Alexander tried formal decomposition first (*Notes*), repudiated it when he discovered the misfit graph is impossible to fully enumerate. He moved to *enabling generative composition through a constrained vocabulary* — which is exactly what our grammar + capability table do. **Our counter-trap:** if the library becomes a lookup table rather than a generative process, we replicate the Gang of Four's mistake (Richard Gabriel's critique). The CRAG EDIT mode is the dangerous one — lookup-flavored. Guard: always re-run the forces through the LLM when overriding a retrieved donor.

## 2. Why the L3 substrate is the right level

Every decision in v0.3 was made so this phase would have a clean target:

- **Grammar is constrained-decodable** (`docs/spec-dd-markup-grammar.md`). LLMs emit `.dd`, not JS, not JSON wrapped in prose.
- **Capability gates double as decode grammar** (ADR-001). The same table that rejects `visible=true` on a VECTOR node during rendering rejects it during LLM decoding.
- **No raw values in the IR** (requirements.md §3.3). LLMs pick from a known vocabulary of token refs. `fill={color.brand.primary}`, not `fill=#FF5733`.
- **Seven-verb edit grammar** (spec-dd-markup-grammar.md §8) gives a closed mutation vocabulary. Every verifier-proposed repair is expressible in the same grammar.
- **Progressive fallback** already works at the render layer. An under-specified L3 node still renders via universal-catalog defaults; the LLM doesn't need to fill every property.

## 3. What's in place vs what's greenfield

### 3.1 Compositional substrate (from v0.2-era Layer 2 analysis)

| Table | Rows | State |
|---|---:|---|
| `component_type_catalog` | 53 | populated — the canonical vocabulary |
| `screen_skeletons` | 338 | populated — one per screen |
| `screen_component_instances` | 42,938 | populated — but **unverified accuracy** (M7.0.a gate) |
| `component_key_registry` | 129 | populated — formal Figma components |
| `component_templates` | 103 | populated — used by compose.py today |
| `component_slots` | 0 | schema only — **M7.0.b populates** |
| `component_variants` | 0 | schema only — **M7.0.c populates** |
| `patterns` | 0 | schema only — **M7.0.e populates** |

The compositional IR is already bidirectional (reads IN for extraction/analysis, reads OUT for generation). Nothing new needs to be built at the schema level for M7.

### 3.2 L3 markup + renderer

| Component | State |
|---|---|
| L3 grammar spec (`docs/spec-dd-markup-grammar.md`) | complete, all 7 edit verbs in §8 |
| L3 parser — construction mode (`dd/markup_l3.py::parse_l3`) | complete |
| L3 parser — `@eid` edit references | partial (`_parse_edit_node` lexes `@eid` but no verb-statement productions) |
| L3 parser — verb-statement productions | **greenfield — M7.1** |
| `EditStatement` AST types | **greenfield — M7.1** |
| `apply_edits(doc, [stmt]) → doc` engine | **greenfield — M7.1** |
| Compressor (DB → L3) | complete; emits rotation/mirror as decomposed primitives |
| Renderer (L3 → Figma) | complete; 204/204 pixel parity |
| Verifier | complete; `StructuredError` with `KIND_*` vocabulary |
| Verifier-emits-hints on `StructuredError` | **greenfield — M7.5 verifier-as-agent** |
| `dd/compose.py` | already migrated to Option B markup-native path |
| `dd/prompt_parser` + archetypes | operational end-to-end today |

### 3.3 LLM integration

| Component | State |
|---|---|
| Claude tool-use / structured outputs | working (used by `dd/prompt_parser` today) |
| Grammar-constrained decoding (GBNF / XGrammar / llguidance) | not integrated — **deferred to M7.5+** once core loop works |

## 4. The action ladder — S1 through S5

Structured like the T1–T5 curation tiers (mechanical → contextual → generative → structural → intelligent): each tier adds capability, each subtask is independently testable, each has a clean round-trip verification pattern. **All S-tiers run at both screen and component/subtree/variant scopes.**

### Tier S1 — Single-node property edits (the `set` verb)

Smallest possible synthetic action: mutate one property on one named node. Tests the edit-grammar core end-to-end without compounding structural complexity.

- **S1.1** Change a text string — `set @field-title text="New title"`
- **S1.2** Toggle visibility — `set @badge visible=false`
- **S1.3** Change a color token — `set @card-1 fill={color.brand.primary}`
- **S1.4** Change a radius / padding / size scalar — `set @card-1 radius={radius.lg}`
- **S1.5** Change an icon — via `swap` at component scope

**Gate:** `apply_edits(doc, [set_stmt]) → doc'`; `render_figma(doc')` produces the mutated frame; `verify(doc', rendered_ref).is_parity is True` AND the targeted property matches expected.

### Tier S2 — Structural edits (one parent-child at a time)

- **S2.1** Delete a node — `delete @badge`
- **S2.2** Append a child — `append to=@toolbar { button label="New" }`
- **S2.3** Insert at position — `insert into=@grid after=@card-3 { ... }`
- **S2.4** Move a node — `move @card-1 to=@archive position=first`
- **S2.5** Swap a component — `swap @button-cta with=-> button/primary/lg` ← **first LLM demo target (M7.2)**

**Gate:** as S1, plus parent-child edges match exactly — ordered sibling list correct.

### Tier S3 — Multi-node coordinated edits

- **S3.1** Apply theme (multiple `set` across tree)
- **S3.2** Generate variant states (`replace` with override family)
- **S3.3** Layout reflow (structural + scalar edits together)
- **S3.4** Verifier-as-agent repair loop (verifier hints → LLM re-edit → re-verify, 3-iteration cap)
- **S3.5** Duplicate screen with modifications (from Reviewer B gap-fill on T5.6) — clone donor AST, apply edit sequence, verify. Most common real designer workflow.

**Gate:** multi-edit end-to-end verifier round-trip; every targeted property matches; failure mode is "which edit didn't land and why," never silent.

### Tier S4 — Composition (creating new units, any scope)

Starting IR transitions from donor to skeleton to empty. **Every subtask runs at all four scopes** (screen / component / subtree / variant).

- **S4.1** *[component]* Compose a component from prompt — standalone `define` in `.dd`.
- **S4.2** *[subtree]* Compose a subtree into an existing screen.
- **S4.3** *[screen]* Compose a screen from archetype + prompt (skeleton fills slots + visual axis).
- **S4.4** *[screen]* Compose a screen from empty (pure SYNTHESIS mode — rarest case).
- **S4.5** *[variant]* Compose a responsive variant from a source screen.
- **S4.6** *[variant]* Compose a component variant family (primary / secondary / tertiary / disabled from one starting IR).

**Gate:** produced unit renders without hard failures; structural verify passes (all typed components resolve, all token refs resolve); fidelity rated ≥ v0.2 VLM baseline (0.728).

### Tier S5 — Intelligence

- **S5.1** Pattern extraction → template (rule-of-three promotion)
- **S5.2** Pattern extraction → component (subtree → external CompRef)
- **S5.3** Screenshot to markup (VLM pass, structured extraction)

Less about edit grammar, more about feedback into the system: finding reusable structure, learning from real screens, closing the loop from generation back to the catalog.

## 5. Milestones — M7 series

Milestones continue the v0.3 M0–M6(a) numbering. **Ordering: library-first.** The library is the foundation everything else sits on.

| Milestone | Scope | Exit criteria |
|---|---|---|
| **M7.0** | **Library population.** Fills the empty compositional tables. See §5.1 for sub-structure. | Quant gate: all six sub-tasks complete + classification accuracy ≥80% on spot-check. Qual gate: LLM smoke test — Claude (tool-use) receives a screen's L3 + library context, emits a valid reference-and-override edit that round-trips to `is_parity=True`. |
| **M7.1** | **Edit grammar — all seven verbs at once.** Parser productions in `dd/markup_l3.py`; `EditStatement` AST types; `apply_edits(doc, [stmt]) → doc'` engine; unit tests per verb. No LLM. | All 7 verbs parse + apply correctly on minimal fixtures; each verb × each common case has a passing unit test. |
| **M7.2** | **First LLM-in-loop demo — S2.5 component swap.** Library-intensive: exercises slot definitions + variant families + the `swap` verb end-to-end via Claude tool-use. | Claude receives a screen's L3 + library catalog as tool context. Emits `swap @X with=-> family/variant` as a tool call. Apply + render + verify: `is_parity=True` + the resolved component matches the requested variant. |
| **M7.3** | **S1 tier expansion (rest of single-node property edits).** | S1.1–S1.4 each pass end-to-end with Claude tool-use. |
| **M7.4** | **S2 tier full (structural edits + S3.5 duplicate-with-mods).** | S2.1–S2.5 pass; S3.5 passes. |
| **M7.5** | **Verifier-as-agent (S3.4) + grammar-constrained decoding option.** Add `StructuredError.hint: str \| None`. 3-iteration repair loop. Wire GBNF / XGrammar as optional path for hardened emission. | S3.4 passes; repair converges ≤3 iterations on 80% of seeded-error cases. Grammar-constrained path produces valid `.dd` 100% on a 20-prompt test set. |
| **M7.6** | **S4 composition — library-grounded at all scales.** Component composition (S4.1), subtree composition (S4.2), screen composition (S4.3–S4.4), variants (S4.5–S4.6). | All S4 subtasks produce structurally-valid output. VLM fidelity ≥ v0.2 baseline. |
| **M7.7** | **S5 intelligence — pattern extraction + screenshot-to-markup.** | S5.1–S5.3 pass on test sets. |
| **M7.8** | **M6(b) trigger evaluation.** Synthetic-gen prototype has run end-to-end on the L3 path through S4. Evaluate whether the `_spec_elements` shim in `render_figma` is still required, or if we can go AST-native. | Decision doc authored; M6(b) either starts or is deferred again with explicit reasoning. |

### 5.1 M7.0 sub-structure (library population)

| Sub | Scope | Approach |
|---|---|---|
| **M7.0.a** | Full classification cascade re-run from scratch. Formal → heuristic → LLM → vision. Records per-instance confidence + cascade-stage provenance. | Runs on all candidate component-like subtrees across 338 screens. Truncates + repopulates `screen_component_instances`. |
| **M7.0.b** | Slot-definition derivation per canonical_type. | For each canonical_type with ≥N instances, auto-cluster children by role/position; Claude labels each cluster's slot purpose. Populates `component_slots`. |
| **M7.0.c** | Variant-family derivation. | Auto-cluster instances by structural/visual similarity; Claude labels variant names + purposes. Populates `component_variants`. |
| **M7.0.d** | Forces/context per-instance LLM label. | Claude labels each instance's compositional role (e.g., "main-cta in login-form"). Alexander's overfitting guard. Adds a column to `screen_component_instances`. |
| **M7.0.e** | Cross-screen pattern extraction. | Rule-of-three detection of repeating subtrees. Populates `patterns`. |
| **M7.0.f** | Sticker-sheet-authoritative tagging (where present, e.g., Frame 429/430 in Dank). | Reconciles with M7.0.b/c output; when present, sticker sheet wins. Skipped silently on projects without a sticker sheet. |

**Approach decided:** auto-cluster (A) + LLM label (C), worth the tokens.
**Accuracy threshold:** 80% on spot-check gate before M7.0 progresses to M7.1.
**Decode stack:** Claude tool-use via structured outputs for all M7.0 labeling work. Grammar-native decode deferred to M7.5+.

## 6. Architectural constraints (non-negotiable)

Inherited from v0.3 and reinforced by Alexander:

1. **Every edit produces a verifiable round-trip.** No "this should work" without `dd verify`. Same pattern as T1–T5 token curation.
2. **No raw values in synthesized IR.** Every fill / stroke / radius is a token ref. Synthetic tokens acceptable; raw hex is not.
3. **Capability gates enforced at emit time AND decode time.** One table, two consumers.
4. **Seven-verb closed set.** No new verbs added without a spec amendment.
5. **Progressive fallback stays load-bearing.** Under-specified output renders via universal-catalog defaults.
6. **Structural parity is the gate, not "looks right."** `is_parity=True` + per-node verification. VLM fidelity is secondary signal, never the gate.
7. **204/204 baseline preserved.** Every M7.N commit keeps the corpus sweep green.
8. **Force-resolution, not lookup.** Always reference + override; never copy + hand-modify (Alexander overfitting guard).
9. **Scale-agnostic entry.** The cascade and the ladder both run at every scope.

## 7. Open questions

Resolved this session:
- ~~CRAG at sub-screen scope~~ — scope-polymorphic; the library is the donor index at every scale.
- ~~Library: hand-authored vs extracted~~ — derived from corpus via auto-cluster + LLM; sticker sheets opportunistic.
- ~~Component-first vs screen-first~~ — scale-agnostic; both are valid entry points (Alexander semi-lattice).
- ~~M7.0 scope~~ — all six sub-tasks; 80% accuracy threshold; quant + qual completion gates.
- ~~Decode stack~~ — Claude tool-use now; grammar-native deferred to M7.5+.
- ~~Verifier-as-agent shape~~ — errors + textual hints on `StructuredError`; 3-iteration cap.
- ~~First LLM demo~~ — S2.5 component swap at M7.2.
- ~~Execution cadence~~ — autonomous + parallel, user-in-loop at judgment points.

Still open (to resolve during M7.0 execution or flag explicitly):
1. **Cluster-similarity thresholds for M7.0.b/c.** What counts as "same slot" across a canonical_type's instances? Empirical — set after dry-run.
2. **Forces/context label format.** Flat string ("main-cta in login-form") or structured (role, context, intent)? Empirical — set after dry-run.
3. **Synthetic token naming under cold start.** When an LLM wants a color not in the registry. Most critical for S4 SYNTHESIS mode.
4. **Atomicity semantics for multi-edit.** When `apply_edits([s1, s2, s3])` partially succeeds. Recommend: sequential with explicit `KIND_EDIT_CONFLICT` on contradictions.
5. **Sticker-sheet detection heuristic.** For projects without Frame 429/430 equivalents, can we auto-detect that a frame serves that role?

## 8. What comes after

- **Priority 2 — React + HTML/CSS renderer.** L3 primitives are backend-neutral; adding React = new walker + per-backend reference-resolution policy. Deferred behind Priority 1.
- **M6(b) cutover.** Eliminate the `_spec_elements` shim. Migrate intrinsic-property emission AST-native. Delete `generate_ir`, `build_composition_spec`, `query_screen_visuals`. Gated on M7.8 trigger.
- **Stage 2 grammar features.** Pattern-language + `use` imports across projects (piggyback on edit grammar).
- **Second project validation.** Verify synthesis generalizes beyond Dank corpus.

---

*Decisions 1–13 locked in the 2026-04-19 session (see session transcript). Edit this doc as M7.0 exposes real constraints; the plan is expected to evolve as actual implementation data arrives.*
