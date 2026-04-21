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
| **M7.1** ✅ | **Edit grammar — all seven verbs at once.** Parser productions in `dd/markup_l3.py`; `EditStatement` AST types; `apply_edits(doc, [stmt]) → doc'` engine; unit tests per verb. No LLM. | All 7 verbs parse + apply correctly on minimal fixtures; each verb × each common case has a passing unit test. **Shipped 2026-04-19/20 in 9 passes (commits `39aa39e` → `fb693e1`); 109 passing + 1 skipped tests. See `docs/plan-m7.1.md` + `docs/m7_assumptions_log.md`.** |
| **M7.2** 🟡 | **First LLM-in-loop demo — S2.5 component swap.** Library-intensive: exercises slot definitions + variant families + the `swap` verb end-to-end via Claude tool-use. | Claude receives a screen's L3 + library catalog as tool context. Emits `swap @X with=-> family/variant` as a tool call. Apply + render + verify: `is_parity=True` + the resolved component matches the requested variant. **Partial (2026-04-21): structural verify landed (commits `fbda4d3` → `90d9a94`). LLM-in-loop run on screen 183 picks a valid alternate master, `apply_edits` splices cleanly, the target eid's new CompRef path matches the LLM's pick. `dd/library_catalog.py` serialises the 100-component library (filter by canonical_type; slots + opt-in prop_definitions + version field); `scripts/m7_swap_demo.py` is the reproducible smoke test. Tool schema pins eid + master enums per run so the LLM can't emit out-of-catalog values. Remaining: drive `render_figma(applied_doc, ...)` + `FigmaRenderVerifier.verify` for the plan's full is_parity=True exit — separate milestone, needs the compressor map plumbing made M7.2-friendly.** |
| **M7.3** | **S1 tier expansion (rest of single-node property edits).** | S1.1–S1.4 each pass end-to-end with Claude tool-use. |
| **M7.4** | **S2 tier full (structural edits + S3.5 duplicate-with-mods).** | S2.1–S2.5 pass; S3.5 passes. |
| **M7.5** | **Verifier-as-agent (S3.4) + grammar-constrained decoding option.** Add `StructuredError.hint: str \| None`. 3-iteration repair loop. Wire GBNF / XGrammar as optional path for hardened emission. | S3.4 passes; repair converges ≤3 iterations on 80% of seeded-error cases. Grammar-constrained path produces valid `.dd` 100% on a 20-prompt test set. |
| **M7.6** | **S4 composition — library-grounded at all scales.** Component composition (S4.1), subtree composition (S4.2), screen composition (S4.3–S4.4), variants (S4.5–S4.6). | All S4 subtasks produce structurally-valid output. VLM fidelity ≥ v0.2 baseline. |
| **M7.7** | **S5 intelligence — pattern extraction + screenshot-to-markup.** | S5.1–S5.3 pass on test sets. |
| **M7.8** | **M6(b) trigger evaluation.** Synthetic-gen prototype has run end-to-end on the L3 path through S4. Evaluate whether the `_spec_elements` shim in `render_figma` is still required, or if we can go AST-native. | Decision doc authored; M6(b) either starts or is deferred again with explicit reasoning. |

### 5.1 M7.0 sub-structure (library population)

| Sub | Scope | Approach |
|---|---|---|
| **M7.0.a** ✅ | Full classification cascade re-run from scratch. Formal → heuristic → LLM → vision per-screen → vision cross-screen → **vision SoM (4th source, 2026-04-21)**. Records per-source confidence + reason + provenance. **See §5.1.a for full decisions.** | Runs on all candidate component-like subtrees across 338 screens. Truncates + repopulates `screen_component_instances`. **Shipped. Post-2026-04-21 session: 4-source pipeline (classify_v2 adds SoM as Pass 8b), catalog expanded 55 → 81 types (M3 / Apple HIG / design-tool audit), `--rerun` flag preserves `classification_reviews` via UPSERT, plugin render-toggle + checkerboard for self-hidden nodes, rule v2 revived with SoM weight 2. Final↔SoM agreement 43% → 60.9% post-consensus. See `project_m7_classifier_v2.md`.** |
| **M7.0.b** ✅ | Slot-definition derivation per canonical_type. | For each canonical_type with ≥N instances, auto-cluster children by role/position; Claude labels each cluster's slot purpose. Populates `component_slots`. **Shipped 2026-04-21 in two steps. Step 1 (commits `faf9902` → `ec5967c`): backfill `components` from CKR — 100 rows (of 129 CKR entries; 25 remote-library masters skipped, 4 duplicate figma_ids). Schema decisions SD-1, SD-2, SD-3, SD-4 applied per spec; migration 018 adds `canonical_type` to `components`. Step 2 (commits `5dc3705` → `1f092d6`): cluster by semantic child-class (TEXT / ICON / COMPONENT / CONTAINER) not raw node_type; LLM-label each cluster via Claude Haiku; write per-master slot rows. 99 total slots derived across button (9) / icon (86) / tabs (1) / header (3). Image correctly rejected (47/47 flat split, no dominant cluster). Leaf types skip the LLM call cleanly.** |
| **M7.0.c** ✅ | Variant-family derivation. | Auto-cluster instances by structural/visual similarity; Claude labels variant names + purposes. Populates `component_variants`. **Shipped 2026-04-21 (commits `3f74a67` → `fe22f62`). Pragmatic deviation: Dank's slash-delimited CKR convention (`button/large/translucent`) lets us parse axes directly from names rather than clustering structurally; Claude Haiku labels each family's axes from a shared AXIS_VOCABULARY (size / style / state / orientation / density / category / role / type / theme / shape). 100 variants inserted across 7 families. Library catalog serializer extended with include_variants for M7.3+ axis-aware swaps.** |
| **M7.0.d** | Forces/context per-instance LLM label. | Claude labels each instance's compositional role (e.g., "main-cta in login-form"). Alexander's overfitting guard. Adds a column to `screen_component_instances`. |
| **M7.0.e** | Cross-screen pattern extraction. | Rule-of-three detection of repeating subtrees. Populates `patterns`. |
| **M7.0.f** | Sticker-sheet-authoritative tagging (where present, e.g., Frame 429/430 in Dank). | Reconciles with M7.0.b/c output; when present, sticker sheet wins. Skipped silently on projects without a sticker sheet. |

**Approach decided:** auto-cluster (A) + LLM label (C), worth the tokens.
**Accuracy threshold:** 80% on spot-check gate before M7.0 progresses to M7.1.
**Decode stack:** Claude tool-use via structured outputs for all M7.0 labeling work. Grammar-native decode deferred to M7.5+.

### 5.1.a M7.0.a deep-dive — classification cascade decisions (2026-04-19 session)

The classification cascade (M7.0.a) received a full design-and-prototype pass during the 2026-04-19 long session. Recording all the decisions here so future sessions don't re-litigate.

#### Three-source architecture (option c2)

The cascade runs **three independent classification sources** per node. All three verdicts are persisted; a consensus rule computes the canonical_type for downstream use, but the raw data is never collapsed.

| Source | Role | Model | Trigger |
|---|---|---|---|
| **Formal** | Exact-match via node name + CKR `component_key` fallback | none (rule-based) | always |
| **Heuristic** | 5 structural rules (header/footer/text/container position + size) | none (rule-based) | always on unclassified |
| **LLM text** | Structural classification from node description + catalog + parent/child/sample-text context, no image | Claude Haiku 4.5 | always on remaining unclassified |
| **Vision per-screen (PS)** | Full-screen image + per-node bbox. Independent per-node reasoning | Claude Sonnet 4.6 | always on candidates after LLM |
| **Vision cross-screen (CS)** | N=5 screens batched per call, grouped by `(device_class, skeleton_type)`. Explicit cross-screen consistency signal via `cross_screen_evidence` | Claude Sonnet 4.6 | always on same candidates |

All three LLM/vision stages use Claude tool-use (structured output) per Decision 10. Grammar-constrained decode deferred to M7.5+.

#### Model + cost envelope

- LLM text stage: **Claude Haiku 4.5** via tool-use. ~$0.02–$0.05 per screen at production batch sizes.
- Vision stages (PS + CS): **Claude Sonnet 4.6** via tool-use + streaming (`max_tokens=32768`, long-request gate). ~$5–$15 per stage across the 204-screen corpus.
- **Full-corpus three-source cascade: ~$35** (cheap enough that information loss from single-source collapse is the real cost to minimize).

#### Batching

- **Vision per-screen (PS):** one API call per screen. All unclassified nodes on that screen classified in one tool call. Rationale: preserves max visual fidelity, simplest to reason about.
- **Vision cross-screen (CS):** batched by `(device_class, skeleton_type)`, target size 5 screens per call. Smaller groups emitted at natural size; larger groups split into consecutive chunks. Rationale: gives the model explicit cross-screen signal for consistency/variant/outlier detection; found during the bake-off to catch patterns per-screen missed (skeleton tiles in content grids) while systematically regressing specifics to `container` on isolated cases.

#### Prompt rules (v1, locked 2026-04-19)

Both the LLM text prompt and the vision batched prompt share these rules:

1. Pick one canonical type per node; `container` and `unsure` are valid.
2. Confidence calibrated: 0.95+ unambiguous, 0.85–0.94 strong+minor-alt, 0.75–0.84 real-evidence+plausible-alt, **below 0.75 → prefer `unsure` with reason**.
3. Don't regress to `container` when a specific type has evidence. Distinctive names (`grabber`, `wordmark`), characteristic children (3 ellipses, 2 chevrons), sample text, or known patterns get specific types.
4. Parent/sibling context informs classification (nodes in a `bottom_nav` are navigation_rows; text nodes at the top of a `card` are headings).
5. Sample text is a strong signal ("Sign in" → button, "9:41" → text in status bar).
6. Empty-frame grid pattern → `skeleton`; decorative-child pattern → `icon`.
7. Reasons are evidence-based, not speculation.

Vision-specific additional rules (cross-screen):
- Cross-screen signal REINFORCES specificity, does NOT downgrade to `container`. Repetition across screens is evidence FOR the specific type, not against it.
- `cross_screen_evidence` citations use enum relations: `same_component`, `same_variant_family`, `contrasting_variant`, `structural_analogue`, `outlier`.

#### Persistence model

**Schema**: `screen_component_instances` is extended with per-source columns:
- `classification_reason` (exists, migration 011) — LLM/heuristic reason
- `vision_reason` (exists, migration 011) — vision per-screen reason
- Planned migration 012 adds: `vision_ps_type`, `vision_ps_confidence`, `vision_cs_type`, `vision_cs_confidence`, `vision_cs_reason`, `vision_cs_evidence_json`, `consensus_method`

Current `canonical_type` column becomes the **computed consensus** (not the primary signal). The `classification_source` column still records the source that produced the consensus.

**New table `classification_reviews`**: one row per human decision. Columns: `sci_id`, `decided_at`, `decided_by`, `decision_type` (`accept_source` / `override` / `unsure` / `skip`), `decision_canonical_type`, `notes`. Reviews are additive and reversible; the consensus view joins against the most-recent review row per sci_id.

#### Consensus rule v1 (naive majority + unsure catch-all)

```
if all three agree → commit, consensus_method = "unanimous"
elif any source returned `unsure` → `unsure`, "any_unsure"
elif 2/3 agree → commit majority, "majority"
else (all differ) → `unsure`, "three_way_disagreement" (flag)
```

Rule v1 is the shipping rule. Rule v2 bias-aware overrides (ignore cross-screen-alone container, honor cross-screen-alone skeleton on empty grids, confidence-tiebreaker) will be ratcheted in after the full corpus run produces real disagreement data. Resolution is recomputed from persisted sources — no re-classification needed to change the rule.

#### Review workflow — Tier 1.5

Flagged rows (`flagged_for_review = 1` where consensus_method ∈ `{three_way_disagreement, any_unsure}`) get reviewed via:

- **`dd classify-review --screen <sid>`** — CLI interactive TUI. Per row shows all three classifications + reasons, prompts `[1] / [2] / [3] / [o] other / [u] unsure / [s] skip / [q] quit`. Decisions write to `classification_reviews`.
- **Visual reference layers** (auto-detected):
  - Figma deep-link (`figma://` URL) printed — jumps to exact node in Figma Desktop on Cmd+click.
  - Local PNG fetched from Figma REST and opened via `open` on macOS.
  - Inline terminal image (iTerm2 / Kitty / Ghostty / compatible) — rendered above prompt.
- **`dd classify-review-index --screen <sid> --html <out>`** — one-shot HTML companion page. Each flagged row as a card with node screenshot + three classifications + reasons side-by-side. Scan in browser while CLI handles decisions.

Separate from review: **`dd classify-audit --sample N`** runs a periodic quality check on *unflagged* rows (agreements that may all be wrong together). Same UX.

#### Bake-off outcomes (2026-04-19)

- **v1 (initial prompts):** 74.4% agreement between PS and CS on screens 150–159.
- **v2 (tightened prompts):** 76.9% agreement — +2.5 points. Major convergence on skeleton (12→24/24) and button_group (5→24/25). Cross-screen container-drift on header/status-bar nodes persists.
- **Conclusion:** the divergence is structural to cross-screen framing, not a prompt-quality issue. Three-source consensus is the right answer — preserve the biases as signal rather than try to collapse them.

#### Operational state (as of 2026-04-19 late session)

Shipped commits, in order:
1. `62be113` — component_key formal-match fallback
2. `7c5da22` — LLM + vision stages rewritten with tool-use
3. `46dee2d` — truncate + since-resume + progress_callback
4. `18f6b12` — `--limit` flag + `classification_reason` persistence
5. `4e9d293` — cross-screen batched vision + bake-off infrastructure + dry-run reports
6. `b083243` — prompt tightening v1 + bake-off v2 results
7. `a2820fa` — M7.0.a decisions captured in this section

**2026-04-19 evening session shipped the remaining infrastructure (Steps 1–8, 10):**
8. `15e9155` — migration 013 (three-source columns + classification_reviews)
9. `f0124ac` — rename classification_reason → llm_reason (migration 014)
10. `d446883` — consensus rule v1 pure function
11. `448cc64` — three-source orchestrator + migration 015 (llm_type / llm_confidence)
12. `6acc3f0` — `--three-source` CLI flag
13. `9fdab37` — `dd classify-review` interactive TUI
14. `d13aa06` — `dd classify-review-index` HTML companion
15. `07ba3d9` — `dd classify-audit` spot-check
16. `02e445e` — `scripts/m7_disagreement_report.py`

Infrastructure shipped (Step numbering matches §5.1.b below):
- Migrations 013, 014, 015 applied to Dank DB
- Orchestrator `run_classification(three_source=True)` runs all three sources
- Consensus computation `dd.classify_consensus.compute_consensus_v1`
- `dd classify --three-source` CLI flag
- `dd classify-review` CLI (Tier 1.5 TUI + visual refs)
- `dd classify-review-index` HTML companion
- `dd classify-audit --sample N --seed` spot-check
- `scripts.m7_disagreement_report` markdown report generator

Dry-run validation (3 iPad screens, 150–152): 452 rows classified end-to-end —
formal 219 / heuristic 163 / LLM 70, vision PS applied 70, vision CS applied 70,
consensus breakdown 48 unanimous / 21 majority / 1 three_way_disagreement. Pair
disagreement rates (LLM↔PS 24%, LLM↔CS 29%, PS↔CS 11%) consistent with the v2
bake-off's 76.9% agreement.

Tests: 194+ across classify modules; 54 pre-existing failures in unrelated
modules unchanged.

Full-corpus 204-screen cascade run: in progress / see commit log for completion.

### 5.1.b M7.0.a build plan — step status

Step-by-step execution plan. Steps 1–8, 10 were completed in the 2026-04-19
evening session. Each step is independently testable and commits cleanly.

**Step 1 — Migration 013 (schema extension).** ✅ Shipped `15e9155`. Renumbered
from "012" in the original plan because `012_variant_token_bindings.sql` already
existed. File: `migrations/013_three_source_classification.sql`. Adds 8 columns
to `screen_component_instances` (`vision_ps_*`, `vision_cs_*`, `consensus_method`)
+ `classification_reviews` table. Also added `audit` to the `decision_type`
CHECK enum (required for Step 8 spot-check workflow).

**Step 2 — Rename `classification_reason` → `llm_reason`.** ✅ Shipped `f0124ac`.
Migration 014 uses `ALTER TABLE ... RENAME COLUMN` — SQLite ≥ 3.25 preserves
data in place. Callers: `dd/classify_llm.py`, `scripts/m7_dry_run_10.py`.

**Step 3 — Consensus computation module (`dd/classify_consensus.py`).** ✅
Shipped `d446883`. 13 unit tests cover every rule-v1 branch including degraded
input (1 or 2 sources available). **Extra (not in original plan):** added
`llm_type` + `llm_confidence` columns via migration 015 (`448cc64`) so the
LLM's primary verdict survives consensus overwriting `canonical_type`. Rule-v2
iteration reads `llm_type`, not `canonical_type`.

**Step 4 — Three-source orchestrator.** ✅ Shipped `448cc64`. `run_classification(
three_source=True)` runs formal → heuristic → LLM → vision_ps per-screen, then
vision_cs batched by (device_class, skeleton_type), then consensus per screen.
`apply_vision_ps_results` / `apply_vision_cs_results` / `apply_consensus_to_screen`
live in `dd/classify.py`. 15 end-to-end tests.

**Step 5 — CLI flag for three-source mode.** ✅ Shipped `6acc3f0`.
`dd classify --three-source` implies `--llm` + `--vision`. Progress line gains
`ps=N` marker; summary prints vision_ps_applied / vision_cs_applied / consensus
breakdown.

**Step 6 — `dd classify-review` CLI (Tier 1.5).** ✅ Shipped `9fdab37`.
Interactive TUI at `dd/classify_review.py`. Figma deep-link (`figma://`),
local PNG via `open`, iTerm2/Kitty/Ghostty env-var detection hook. Records
decisions in `classification_reviews`. 23 tests covering every prompt branch.

**Step 7 — `dd classify-review-index` HTML.** ✅ Shipped `d13aa06`.
`render_review_index_html(conn, file_key, ...)` returns a self-contained
HTML doc with inline CSS + base64 screenshots. 7 tests.

**Step 8 — `dd classify-audit` spot-check.** ✅ Shipped `07ba3d9`.
`dd/classify_audit.py`: `fetch_audit_sample(conn, n, seed, screen_id)` with
reproducible seeded sampling. `run_audit_tui` records every decision as
`decision_type='audit'` regardless of outcome. 10 tests.

**Step 9 — Full 204-screen cascade run.** Command:
```
.venv/bin/python3 -m dd classify --truncate --three-source
```
Budget: ~$35, wall time ~30–60 min. **Dry run on 3 iPad screens** (150/151/152)
validated the pipeline end-to-end: 452 rows classified, 70 LLM + PS + CS,
consensus 48 unanimous / 21 majority / 1 three_way_disagreement in ~45 sec.

**Step 10 — Disagreement report.** ✅ Shipped `02e445e`. `scripts/m7_disagreement_report.py`
emits markdown with summary / pair matrix / top-N 3-way rows / pattern clusters.
Smoke-tested on dry-run data: surfaces a genuine disagreement with all three
reasons preserved. 8 tests.

**Step 11 — Manual review sprint** (user-facing). Work through
`dd classify-review` across flagged rows. `--screen <sid>` filters by screen;
HTML companion via `dd classify-review-index --out <path>` scrolls alongside.

**Step 12 — Rule v2 design** (based on real data). Consume `m7_disagreement_report.py`
+ human overrides; encode bias-aware consensus rules (e.g., "discount cross-
screen-alone container," "honor cross-screen-alone skeleton on empty grids,"
confidence tiebreaker). Consensus recomputes from persisted `llm_type` +
`vision_ps_type` + `vision_cs_type` — no re-classification needed.

**Commands shipped for M7.0.a:**
```
dd classify --three-source [--truncate] [--since SID] [--limit N]
dd classify-review [--screen SID] [--limit N] [--no-preview]
dd classify-review-index [--screen SID] [--limit N] [--out PATH] [--no-screenshots]
dd classify-audit [--sample N] [--screen SID] [--seed K] [--no-preview]
python3 -m scripts.m7_disagreement_report --db PATH [--top-n N] [--out PATH]
```

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
