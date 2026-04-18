# Requirements — v0.3 Phase

**Status:** Canonical for the v0.3 phase. Derives from `docs/requirements.md` (Tier 0). Every v0.3 spec and plan traces to this.
**Authored:** 2026-04-18.
**Scope:** internal tool, Dank Experimental corpus.

v0.3 is **the foundation** — not one of many priorities but the prerequisite substrate that Priority 1 (synthetic generation) needs to begin. Its scope is narrow and load-bearing: complete dd markup as the shared-grammar substrate, and round-trip the Dank corpus through it at pixel parity.

---

## 1. What v0.3 delivers

### 1.1 dd markup — the shared grammar

A KDL-substrate dialect expressing L3 (the semantic tree level of the multi-level IR) as:

- **Axis-polymorphic.** Any subset of Structure / Content / Spatial / Visual / System on any node. Wireframes, style briefs, partial mockups, and full IRs are all valid markup.
- **Reference-always for values.** Token refs `{path}`, component refs `-> key`, pattern refs `& name`. Raw literals only for structural content; no raw style values in the IR.
- **Definition-enabled.** `define name(args) { body }` with three parametrization primitives (scalar args, named slots with defaults, path-addressed overrides).
- **Edit-addressable with no separate grammar.** Construction and editing parse through the same rules; `@eid` addresses existing nodes; seven imperative verbs for structural edits; property assignment for leaf updates.
- **LLM-constrained-decodable.** Formal grammar suitable for XGrammar / Outlines / llguidance. Vocabulary exposure in the system prompt paired with grammar mask at decode time — two mechanisms working together, both depending on the same capability table.
- **Engineer-readable.** Not designer-facing in v0.3. Grammar optimized for parser reliability and LLM emission, not for casual visual appeal.

### 1.2 Figma renderer round-trip through dd markup

The existing Figma renderer (204/204 parity on dict IR today) must round-trip the full Dank corpus through dd markup at pixel parity:

```
Extract (Figma → DB) → L0+L1+L2 → derive L3 (dd markup)
  → render-via-markup-path → Figma → verify → is_parity=True
```

This is strictly stronger than today's 204/204 because it adds the L3 round-trip step without removing any existing proof.

### 1.3 Three foundational stages

**Stage 1 — Grammar + parser + round-trip.**
- Formal dd markup grammar spec (BNF/EBNF)
- Hand-authored fixtures across multiple axis densities (wireframe-only, style-only, mixed, full)
- Parser + emitter
- L0↔L3 derivation algorithms (both compression and expansion)
- Round-trip proof on the Dank corpus at pixel parity

The edit grammar is part of Stage 1 because it's the same grammar. Construction and edits parse identically; separating them would be ceremony.

**Stage 2 — Definitions + references.**
- Migrate the 12 archetype JSON skeletons in `dd/archetype_library/` to `.dd` defines
- Import mechanism (`namespace X` + `use "path" as alias`)
- Cycle detection (three-color DFS at parse time, hard-error no tolerance)
- Pattern-suggestion optimization pass (Rule of Three — N ≥ 3 occurrences before suggestion, user-gated promotion, never auto-apply)
- Definitions can be project-scoped, spec-scoped (inline), or library-imported

**Stage 3 — Synthetic tokens for cold start.**
- Clustering passes: ΔE on colors, histograms on dimensions, nearest-step on type scales
- Universal catalog defaults preloaded (shadcn-flavored, leveraging existing `_UNIVERSAL_MODE3_TOKENS`)
- **After Stage 3, the LLM cannot emit raw values** — vocabulary + grammar mask together make it structurally impossible
- Synthetic token entries are internal (exist in DB for rendering; not exported to Figma variables or CSS)

### 1.4 What v0.3 does NOT deliver (gated beyond)

Stages 4–6 are Priority 1 (synthetic generation) and Priority 2 (multi-target) work. Gated on v0.3 foundation completion:

- **Stage 4 — Retrieval-augmented starting-IR selection.** Unified pipeline: classify retrieval confidence, pick starting IR, apply edits. The four synthetic-generation classes (full screens / components / variations / style transfers) are the same pipeline parameterized differently. CRAG scope revisits the screen-vs-component granularity question.
- **Stage 5 — Verifier-as-agent.** Tiered ladder (structural parity, density, Jaccard, pairwise VLM). Critic emits edit-grammar patches in the same grammar as the generator. Fresh context, monotone-accept.
- **Stage 6 — Multi-target catalog schema.** Optional for v0.3 ship; enables Priority 2 (React renderer).

---

## 2. v0.3 scope boundaries

### 2.1 Internal tool, Dank-only corpus

v0.3 is explicitly scoped to "work on Dank." Second-project portability is a later concern; the architecture is designed so that retrieval thresholds become per-project calibrations and corpus queries become project-scoped, but validation requires real second-project data that we don't have yet.

### 2.2 Grammar audience

**LLM-friendly + technical-reader human-readable** (engineer, design-systems lead). NOT designer-facing in v0.3. This constrains grammar-complexity tradeoffs: favor constrained-decoding reliability and precise parse semantics over visual accessibility for non-technical users.

### 2.3 Both goals required

- Grammar completeness — markup can express the existing IR losslessly, plus the axis-polymorphic + definition-enabled features specified here
- Full Figma round-trip — extract → dd markup → render → 204/204 pixel parity

Reducing to "grammar-completeness only" or "smaller MVP round-trip" was explicitly rejected.

### 2.4 All ADR-001 through ADR-008 invariants preserved

- Capability-gated emission (ADR-001)
- Null-safe Mode 1 (ADR-002)
- Explicit state harness (ADR-003)
- Verification loop (ADR-004)
- Null-safe prefetch (ADR-005)
- Boundary contract (ADR-006)
- Unified verification channel (ADR-007)
- Mode 3 composition w/ conservative IR serde (ADR-008, revised per `docs/decisions/v0.3-canonical-ir.md`)
- Leaf-parent gate (Fix #1)

### 2.5 v0.3 preserves the 204/204 baseline

`render_batch/sweep.py` continues to report 204/204 throughout v0.3 development. Any stage that breaks parity is halted, not shipped. v0.3 is purely additive — at any point, the existing Figma renderer path (dict IR → script → pixels) continues to work unchanged. The markup path is an additional capability, not a replacement.

---

## 3. Success criteria

v0.3 is done when all the following hold:

### Foundation-level (Stages 1–3)

- **Every Dank corpus screen** round-trips through dd markup at pixel parity. `DD_MARKUP_ROUNDTRIP=1 render_batch/sweep.py` reports 204/204 `is_parity=True`.
- **Hand-authored `.dd` markup** (for the 3+ reference screens in `tests/fixtures/markup/`) renders to valid Figma at pixel parity against the original sources.
- **Grammar expresses** all five axis subsets, definitions, references, and edits uniformly — a fixture written at wireframe density and another written at full density both parse and round-trip.
- **Same grammar** parses extraction output, synthesis output (as produced in Stage 4 eventually), user authoring, verifier critique.
- **`parse(emit(ir)) == ir`** structural invariant on every fixture and on the 204-corpus sample.
- **Grammar is constrained-decodable** — smoke test: Claude Haiku + XGrammar/llguidance produces a valid `.dd` fragment for a small prompt.
- **Raw-value test** — after Stage 3 synthetic-token clustering, no Dank-corpus IR carries a raw hex / raw pixel / raw font-name where a token (real, synthetic, or catalog-default) could resolve.
- **204/204 parity preserved** on the existing dict-IR path throughout.
- **1,950+ unit tests green** (current baseline; v0.3 is purely additive).

### Spec-level

- All specs in `docs/spec-*.md` and `docs/requirements-*.md` exist and are internally consistent.
- No open questions listed in any spec block the next phase (Priority 1 synthetic generation).

### Downstream-measurement (observed once Stage 4–5 arrive)

- 12-prompt canonical mean fidelity ≥ 0.8 (vs 0.728 v0.2 baseline) — demonstrates the substrate does its job for synthesis.

---

## 4. Where we are vs where we're going

### 4.1 Current state (end of 2026-04-18 session)

- Branch: `v0.3-integration` (reset to probe + hardening, post-revert of premature CRAG Stage A–D work)
- `dd/markup.py` (~786 LOC) exists as a starting point but is a **mechanical dict-IR serializer**, not the axis-polymorphic L3 grammar specified here. It parses and round-trips 204/204 at dict level, but it's the wrong shape for v0.3. It will be substantially rewritten — some infrastructure (tokenizer, error classes, Tier 2 test harness) is reusable; the grammar surface is not.
- Six decision records from the investigation round are in `docs/decisions/v0.3-*.md`. Some remain valid as-is (grammar modes, branching strategy, underscore-field contracts); others (canonical-IR, provider-audit, renderreport-schema) are partially superseded by this requirements doc — see each decision record's updated header.
- 319 tests green on `v0.3-integration`. `DD_MARKUP_ROUNDTRIP=1` env var is plumbed through `generate_ir`.

### 4.2 What was learned that informs v0.3

- **CRAG Stages A–D (2026-04-18) were premature.** They built a screen-level retrieval cascade on top of a mechanical markup that wasn't the real dd markup. Reverted. Feature branches preserved as archaeology (`v0.3-stage-a-crag-scaffold`, `v0.3-stage-c-synthesis`, `v0.3-stage-d-composition`), tag `pre-revert/stages-a-d-2026-04-18`.
- **The canonical-IR question was framed wrong** in the initial investigation. "Markup as serde over dict IR" was the right answer for the mechanical-serialization markup I built; it's not the right framing for the axis-polymorphic L3 grammar specified in Tier 0 §4. The "conservative" position is reinterpreted as: **dict IR remains canonical on the render path; dd markup is L3 and lowers to dict IR via the compression/expansion algorithms specified in S3**.
- **Starting CRAG before Stage 1 was the diversion.** The MVP doc explicitly said "do not sneak in edit grammar or CRAG cascade — those are Stage 4." The current plan restores that ordering.

### 4.3 What happens next

Per `docs/plan-v0.3.md`:

1. **Plan A — Write specs** (3–5 days of collaboration). Produces formal grammar spec, L0↔L3 relationship spec, hand-authored fixtures.
2. **Plan B — Execute Stage 1** (2–3 weeks). Parser, emitter, round-trip on Dank corpus.
3. Stage 2 (definitions), Stage 3 (synthetic tokens) after Stage 1 ships.
4. Priority 1 synthetic generation (Stages 4–5) begins when foundation is complete.

---

## 5. Open questions that must be resolved during Plan A

These are tracked as open-question blocks inside S2 and S3; calling out here for visibility:

### Grammar (resolved in S2)

- Exact sigil semantics: when is `#eid` optional vs required; when is `@eid` required vs implicit in context; path separator behavior (`/`) vs namespace resolution (`.`); wildcards (`*`, `**`).
- Value polymorphism: raw literals, token refs `{path}`, component refs `-> key`, pattern refs `& name` — one value slot, four forms, how does the parser disambiguate.
- Provenance per-value trailer form: `#[...]` or alternative. LLM emission reliability should decide.
- Definition parametrization: scalar args / slots / path overrides — exact syntax for each.

### L0↔L3 relationship (resolved in S3)

- **Compression algorithm.** How do we turn 200 L0 nodes into ~20 L3 elements? Which L1 classifications collapse to component refs? Which L2 bindings become `{token}` refs in the markup? What stays inline? What triggers a `define` suggestion?
- **Expansion algorithm.** How does L3 render — via L3→L0 lowering and reusing the existing renderer, or via a new L3-aware renderer? How are `-> key` refs resolved via CKR? How does wireframe-density markup fill from catalog defaults?
- **Round-trip proof shape.** What exactly do we compare: pixel parity on the source Figma file vs the rendered markup? Per-node structural diff against the original IR? Both?

Plan A closes these before Plan B starts.

---

## 6. Non-negotiables, restated

Pulling from `docs/requirements.md` §3:

1. **204/204 round-trip pixel parity preserved through every change.**
2. **Lossless extraction; extraction emits ground truth; no auto-deduplication.**
3. **No raw values in the IR** — every value is a reference (real token, synthetic, or universal default).
4. **No silent drift** — every failure mode is a named `KIND_*`.
5. **All ADRs in force.**

Any v0.3 change that would break one of these is rejected.

---

## 7. Navigation

| Document | Purpose |
|---|---|
| `docs/requirements.md` | Tier 0 — overall project requirements. |
| **This doc** (`docs/requirements-v0.3.md`) | Tier 1 — v0.3 phase requirements. |
| `docs/plan-v0.3.md` | Plan A (write specs) + Plan B (execute). |
| `docs/spec-dd-markup-grammar.md` | Formal grammar spec — to be authored during Plan A.5. |
| `docs/spec-l0-l3-relationship.md` | L0↔L3 algorithms — to be authored during Plan A.6. |
| `tests/fixtures/markup/` | Hand-authored reference `.dd` files — to be authored during Plan A.4. |
| `docs/decisions/v0.3-*.md` | Investigation-round decisions; several reframed, see each file's header. |
| `memory/project_v0_3_plan.md` | Memory-resident summary for cross-session continuity. |

---

*v0.3 is the foundation, not a detour. Get the grammar right; everything downstream falls into place.*
