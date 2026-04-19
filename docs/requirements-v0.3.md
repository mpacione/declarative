# Requirements — v0.3 Phase

**Status:** v0.3 foundation complete (2026-04-19). This document is preserved for reference against every requirement listed here; follow-on work (Priority 1 synthetic generation) has its own requirements doc.
**Authored:** 2026-04-18.
**Completed:** 2026-04-19 with `6377105` (M6(a) atomic cutover).
**Scope:** internal tool, Dank Experimental corpus.

v0.3 is **the foundation** — not one of many priorities but the prerequisite substrate that Priority 1 (synthetic generation) needs to begin. Its scope is narrow and load-bearing: complete dd markup as the shared-grammar substrate, and round-trip the Dank corpus through it at pixel parity. **Both delivered.**

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

### 1.2 Markup-native Figma renderer round-tripping the corpus

**Option B (adopted 2026-04-18 late-late session; see
`docs/decisions/v0.3-option-b-cutover.md`):** the Figma renderer walks
the L3 markup AST directly. No dict-IR intermediate on the render path.

```
Extract (Figma → DB) → L0+L1+L2 → derive_markup(conn, sid) → L3Document
  → render_figma(doc, conn) → Figma JS → execute → walk → verify → is_parity=True
```

The full Dank corpus must round-trip at pixel parity through this path
(204/204 `is_parity=True` via `render_batch/sweep.py`).

During the migration window (M1–M5 per
`docs/decisions/v0.3-option-b-cutover.md`) the pre-markup dict-IR
renderer remains operational in CI as the reference against which the
new markup-native renderer proves byte-parity. At M6 cutover it is
deleted per `docs/DEPRECATION.md`.

**Architectural invariant:** there are **two** stable representations
in the system end-to-end — the DB (L0+L1+L2, ground truth, lossless)
and the L3 markup AST (in-flight IR for any single screen/component).
Nothing else. Dict IR is transitional scaffolding.

### 1.3 Three foundational stages

**Stage 1 — Grammar + parser + markup-native renderer.**
- Formal dd markup grammar spec (BNF/EBNF) — ✅ complete (`docs/spec-dd-markup-grammar.md`)
- Hand-authored fixtures across multiple axis densities (wireframe-only, style-only, mixed, full) — ✅ 3 reference screens
- Parser + emitter — ✅ complete (`dd/markup_l3.py`)
- `derive_markup(conn, sid) → L3Document` — DB → L3 AST (existing compressor logic; renamed at M0 cutover)
- `render_figma(doc, conn)` — L3 AST → Figma JS, walking the AST directly (built at M1)
- Round-trip proof: `parse(emit(derive_markup(conn, sid))) == derive_markup(conn, sid)` Tier 1 + pixel-parity sweep Tier 3 on Dank corpus at 204/204

Milestone breakdown: `docs/decisions/v0.3-option-b-cutover.md` §5 (M0..M6+).

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
- Mode 3 composition w/ markup-native IR (ADR-008, revised per `docs/decisions/v0.3-option-b-cutover.md`; the 2026-04-18 mid-session "conservative IR serde" stance in `v0.3-canonical-ir.md` is superseded)
- Leaf-parent gate (Fix #1)

### 2.5 v0.3 preserves the 204/204 baseline through the migration

`render_batch/sweep.py` (on the pre-markup dict-IR renderer path) continues to report 204/204 throughout milestones M1–M5 of the Option B migration — that path is the reference against which the new markup-native renderer is byte-parity-matched. The markup-native path (`render_figma(doc, conn)`) is built alongside and reaches 204/204 at M3 (script byte-parity) and M4 (pixel parity).

At the M6 cutover, the atomic PR that deletes the dict-IR path must land with 204/204 `is_parity=True` on the markup-native path. Any stage that breaks either parity pre-cutover is halted, not shipped. The migration is **sequenced additive** — both paths coexist in CI until one is proven equivalent and the other is deleted — NOT "purely additive" as originally framed.

---

## 3. Success criteria

v0.3 is done when all the following hold:

### Foundation-level (Stages 1–3)

- **Every Dank corpus screen** renders through the markup-native Figma renderer at pixel parity. `render_batch/sweep.py` (on the post-cutover single path) reports 204/204 `is_parity=True`.
- **Hand-authored `.dd` markup** (for the 3+ reference screens in `tests/fixtures/markup/`) renders to valid Figma at pixel parity against the original sources.
- **Grammar expresses** all five axis subsets, definitions, references, and edits uniformly — a fixture written at wireframe density and another written at full density both parse and round-trip.
- **Same grammar** parses extraction output, synthesis output (as produced in Stage 4 eventually), user authoring, verifier critique.
- **`parse(emit(derive_markup(conn, sid))) == derive_markup(conn, sid)`** Tier 1 AST-level round-trip invariant on every fixture and on the 204-corpus sweep.
- **Grammar is constrained-decodable** — smoke test: Claude Haiku + XGrammar/llguidance produces a valid `.dd` fragment for a small prompt.
- **Raw-value test** — after Stage 3 synthetic-token clustering, no Dank-corpus IR carries a raw hex / raw pixel / raw font-name where a token (real, synthetic, or catalog-default) could resolve.
- **204/204 parity maintained** through the Option B migration: the pre-markup dict-IR path stays green in CI until the M6 cutover lands with 204/204 on the markup-native path.
- **1,950+ unit tests green** (current baseline; net code volume at M6 cutover goes DOWN — ~2000 LOC of Option A scaffolding deleted, ~1000–1500 LOC of markup-native renderer added).

### Spec-level

- All specs in `docs/spec-*.md` and `docs/requirements-*.md` exist and are internally consistent.
- No open questions listed in any spec block the next phase (Priority 1 synthetic generation).

### Downstream-measurement (observed once Stage 4–5 arrive)

- 12-prompt canonical mean fidelity ≥ 0.8 (vs 0.728 v0.2 baseline) — demonstrates the substrate does its job for synthesis.

---

## 4. Where we are vs where we're going

### 4.1 Current state (2026-04-19)

- Branch: `v0.3-integration`. Tags: `pre-markup-baseline` (main pre-migration anchor), `markup-compressor-mvp` (c0102d5), `option-a-complete` (end-of-Option-A reference). Open v0.3-integration HEAD: `6377105` (M6(a) atomic cutover).
- **Option B migration complete** — M0 through M6(a). All consumers are on the markup-native path. Tier 1 AST round-trip at 204/204, Tier 2 + Tier 3 (pixel parity) at 204/204 via `render_batch/sweep.py`. 61-screen grid review (2026-04-19) resolved 7 visual-defect classes (`visible=false` emission, GROUP coord normalization, rotation/mirror → relativeTransform matrix) in 3 fixes: commits `1faad8c`, `2fe5934`, `7d95190`.
- **Option A deletion (M6(a)) — shipped.** ~6,800 LOC removed: `dd/decompress_l3.py`, 3 test files, `--via-markup` / `--via-option-b` flags, segregated `*-markup` / `*-option-b` artefact dirs, the `via_markup` branch in `generate_screen`. Preserved at git tag `option-a-complete` for archaeology.
- **Option A internal plumbing (M6(b)) — pending, gated.** `generate_ir`, `build_composition_spec`, `query_screen_visuals`, `generate_figma_script`, `generate_screen`, and the `_spec_elements` shim inside `render_figma` remain as infrastructure the compressor + walker still consume. M6(b) rewrites them to an L3-native shape once the synthetic-gen prototype trigger hits.
- `dd/markup_l3.py` — parser/emitter/AST/semantic passes — backbone of Option B. Unchanged.
- `dd/compress_l3.py` — per-axis derivation. The compressor now emits `rotation` + `mirror` as decomposed L3 primitives (rather than matrices), keeping the AST backend-neutral.
- 2,649+ tests passing (M4/M5/M6(a) added ~25 tests; grammar round-trip + compose + option-b-parity suites all green). 24 pre-existing v0.2 failures in unrelated test modules (semantic_tree, rebind, phase2/3 integration) predate this work and are orthogonal.

### 4.2 What was learned that informs v0.3

- **CRAG Stages A–D (2026-04-18 midday) were premature.** They built a screen-level retrieval cascade on top of a mechanical markup that wasn't the real dd markup. Reverted. Feature branches preserved as archaeology (`v0.3-stage-a-crag-scaffold`, `v0.3-stage-c-synthesis`, `v0.3-stage-d-composition`), tag `pre-revert/stages-a-d-2026-04-18`.
- **The canonical-IR question was asked twice.** Initial answer (mid-session 2026-04-18): "markup lowers to dict IR, dict IR canonical on render path" — Option A. Then a Figma sweep attempt on the Option A path revealed the scaffolding cost: two compile-time side-channels (`$ext.nid`, `$ext.spec_key`) and active content drift in the decompressor. Re-asked late-late-session: the side channels are scaffolding for a system being demolished; elegance is worth the ~1-week cost delta. **Adopted Option B**: markup IS the canonical IR end-to-end; renderer walks AST directly; no dict IR.
- **Script-size ratio ≠ byte parity.** The 0.977–0.981 script-size ratios that looked promising on Option A masked real semantic divergence (element-key counter drift, content drift). The Tier 2 spec claim is byte-identity, not near-identity — important lesson for how to measure parity going forward.
- **Starting CRAG before Stage 1 was the diversion.** The MVP doc explicitly said "do not sneak in edit grammar or CRAG cascade — those are Stage 4." The current plan restores that ordering.

### 4.3 What happened (M1 through M6(a))

All milestones from §4.3 above are **complete** as of 2026-04-19. For the historical breakdown of each milestone + the commit map, see `docs/plan-v0.3.md` §Status and the M6(a) progress table in `docs/DEPRECATION.md`.

### 4.4 What happens next

**Priority 1 — Synthetic screen generation + editing.** Active planning in `docs/plan-synthetic-gen.md` (use-case ladder, requirements, milestone breakdown). The L3 markup is now the substrate for an LLM decode target (constrained by the grammar spec) and for seven-verb edits (`set`, `add`, `remove`, `move`, `replace`, `wrap`, `unwrap` per §8 of `docs/spec-dd-markup-grammar.md`).

**M6(b) — AST-native emission cutover.** Gated. Triggers when the synthetic-gen prototype runs end-to-end; at that point we'll know which intrinsic-property emission paths need the `_spec_elements` shim vs. which can go straight from the AST.

**Priority 2 — React / HTML-CSS renderer.** Not scheduled. The L3 markup is backend-neutral by design; adding a renderer is a new walker and a per-backend reference-resolution policy, not an IR change. Ready to start whenever Priority 1 has a stable prototype.

---

## 5. Open questions — resolution status

Plan A closed all 20 open questions (Grammar Q1–Q10, L0↔L3 OQ-1–OQ-10) before Plan B Stage 1 started. Historical tracking preserved in the spec files themselves.

**Notable: OQ-5 (expansion algorithm) was resolved twice:**

- Initial resolution (2026-04-18 mid-session): Option A — L3 lowers to dict IR, existing renderer consumes dict unchanged.
- Final resolution (2026-04-18 late-late session): Option B — L3 consumed directly by a markup-native renderer. Full rationale in `docs/decisions/v0.3-option-b-cutover.md`.

All resolved questions from Plan A (§2 and §3 of `spec-dd-markup-grammar.md` and `spec-l0-l3-relationship.md`):

### Grammar (resolved in S2)

- Exact sigil semantics: `#eid` optional vs required; `@eid` required vs implicit in context; path separator behavior (`/`) vs namespace resolution (`.`); wildcards (`*`, `**`).
- Value polymorphism: raw literals, token refs `{path}`, component refs `-> key`, pattern refs `& name` — disambiguation via statement-starter rules.
- Provenance per-value trailer form: `#[kind attrs]` (chosen for LLM emission reliability).
- Definition parametrization: scalar args / slots / path overrides — all three syntaxes specified in §6.

### L0↔L3 relationship (resolved in S3)

- **Compression algorithm.** Per-axis decomposition; L1 classifications drive type keyword choice; L2 bindings become `{token}` refs when present; Mode-1 INSTANCES become `-> slash/path` CompRefs; pattern suggestions reserved for Rule-of-Three optimization pass (Stage 2+).
- **Expansion algorithm.** Option B (markup-native renderer) — see `docs/decisions/v0.3-option-b-cutover.md`.
- **Round-trip proof shape.** Three tiers — AST-level `parse(emit(doc)) == doc` + script byte-parity (against the Option A baseline, during migration) + pixel parity via Figma sweep.

---

## 6. Non-negotiables, restated

Pulling from `docs/requirements.md` §3:

1. **204/204 round-trip pixel parity preserved through every change.** During M1–M5 of the Option B migration, this is enforced on the pre-markup dict-IR path (which stays in CI). At M6 cutover, the atomic PR must achieve 204/204 on the markup-native path before the dict-IR path is deleted.
2. **Lossless extraction; extraction emits ground truth; no auto-deduplication.**
3. **No raw values in the IR** — every value is a reference (real token, synthetic, or universal default). Option B strengthens this: reference resolution happens at one place (the renderer), with per-backend rules.
4. **No silent drift** — every failure mode is a named `KIND_*`.
5. **All ADRs in force.** ADR-008 revised per `docs/decisions/v0.3-option-b-cutover.md` to specify markup-native Mode 3 composition (the "conservative IR serde" stance in the ADR's v0.3-canonical-ir.md revision is superseded).

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
