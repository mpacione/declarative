# Requirements — Overall Project

**Status:** Canonical. Top of the doc stack. Every downstream doc (v0.3 requirements, grammar spec, L0↔L3 spec, plans) traces to this.
**Authored:** 2026-04-18.

This document states what the system is, what we're trying to achieve, the foundational correctness criteria, the structural design principles, and the roadmap. It exists so that a fresh session — human or AI — can anchor to a single source of intent before touching anything downstream.

---

## 1. The core claim

Design artifacts — Figma files today, eventually React / SwiftUI / Flutter; extractable from any source, renderable to any target, authorable by humans and AI in collaboration — can be **compiled between formats through a shared multi-level intermediate representation** that preserves design intent: structure, spatial arrangement, content, visual treatment, system tokens, and provenance.

Modeled on LLVM's MLIR. One IR, many frontends, many backends. The same structural trick that lowers C/Rust/Swift to x86/ARM/WASM, applied to design artifacts.

The IR has four coexisting levels: L0 scene graph (DB), L1 classification, L2 token bindings, L3 semantic tree. **L3 is expressed in dd markup** — the axis-polymorphic authoring surface that LLMs and humans share. "dd markup" and "L3 markup" are the same thing; "dd markup" is used throughout this doc stack.

---

## 2. Ultimate goal — synthetic design generation

**The purpose of this compilation is synthetic design generation** — producing design artifacts in any target format from human-level inputs (text prompts, rough sketches, screenshots, verbal modification requests) in a manner that enables true human + AI design collaboration.

Synthetic generation spans **four distinct granularities**:

1. **Full screen synthesis** — prompt / sketch / screenshot → complete IR for a screen that didn't exist
2. **Component synthesis** — new reusable components (new card variants, new header layouts, new button treatments) that extend the design system
3. **Element variations on existing screens** — take a current screen, produce N alternatives at any axis: same structure different theme, same theme different layout, same screen denser / sparser content, multi-turn refinement
4. **Style extractions and transfers** — extract a theme or pattern (`define theme.X { ... }`) from one screen's visual language, apply it to another

All four are the same operation under the multi-granularity framing: **apply edits to a starting IR**. The starting IR ranges from empty (full synthesis) through archetype skeleton + donor exemplars (composition) through real donor IR (targeted edit). Edit volume ranges from large (whole-screen generation) to a single property change. Same pipeline. Same grammar. Same verifier.

Quality criteria across all four:

- **Rich** — output honors the design system. Values are always references (real tokens, synthetic tokens, or universal-catalog defaults). Real component masters when available; idiomatic inline composition when not.
- **Efficient** — LLMs work at whatever axis density makes the current decision cheapest. Explore three spatial arrangements before committing style. Elaborate one structural skeleton. Layer theme onto an approved wireframe. The compiler handles lowering; the LLM handles intent.
- **Verifiable** — every artifact passes the same structural verifier that catches round-trip drift, at per-node granularity, machine-checked.
- **Progressive** — generation degrades gracefully when the design system can't express something. Token missing → synthetic token. Component missing → inline composition. Nothing hard-fails.

---

## 3. Foundational correctness criteria

These are preserved through every change. Any modification that breaks one is rejected, even if it's "cleaner."

### 3.1 Round-trip pixel parity

Figma → extract → IR → render → Figma at **pixel-level parity**. 204/204 today on the Dank Experimental corpus. Without round-trip, the IR is lying, and every downstream feature inherits the lie.

### 3.2 Lossless extraction + ground-truth emission

L0 captures every property; L1/L2/L3 add annotations, never remove. **Extraction emits ground truth; it never auto-deduplicates.** Every Figma INSTANCE becomes a component reference (`-> key`); every FRAME becomes an inline structural node. The extractor does not collapse structurally-similar subtrees into `define`s — that's an interpretive step reserved for a separate optimization pass with the **Rule of Three** (N ≥ 3 occurrences before suggestion, user-gated promotion). This preserves round-trip as strictly invertible.

### 3.3 No raw values in the IR

**This is the single most load-bearing invariant for synthesis validity.** Across all five axes of dd markup, every value is a reference:

- A real design-system token (`{color.brand.primary}`, `{space.md}`)
- A synthetic token clustered from raw values at extract time (ΔE grouping on colors, histograms on dimensions, nearest-step on type scales)
- A universal-catalog default (shadcn-flavored, preloaded for cold start when no project tokens exist)
- Structural content (text strings, labels — inherently raw, but content not style)

Raw literals live in the DB and in user-typed content. The IR never holds them for style/spacing/typography. This is what makes LLM synthesis structurally valid — LLMs pick from a known vocabulary, never invent `#FF5733`. It also means the IR is uniform across three very different project states: mature design system / no design system with extracted corpus / cold start with no corpus. One resolution path regardless.

### 3.4 No silent drift

Every failure mode — codegen-time degradation, runtime exception, post-render mismatch, extraction error — surfaces as a named `KIND_*` through the unified verification channel (ADR-007). Per-node granularity. No scalar "looks right" judgments; everything is machine-checkable.

### 3.5 All ADRs remain in force

ADR-001 (capability-gated emission) through ADR-008 (Mode 3 composition, with the canonical-IR revision per `docs/decisions/v0.3-canonical-ir.md`). New ADRs extend, never revert.

---

## 4. Structural design principles

### 4.1 Axis-polymorphic specification

Every node in dd markup is a point in a **five-axis specification space**:

| Axis | What it specifies |
|---|---|
| **Structure** | Types, children, hierarchy, slots |
| **Content** | Text, labels, data bindings, props |
| **Spatial** | Sizing, position, gap, padding, arrangement |
| **Visual** | Fills, strokes, effects, typography (per-node) |
| **System** | Palette, type scale, spacing scale, radius scale (project-wide) |

Any subset of axes on any node is a valid specification. A style brief is System-only. A wireframe is Structure + Spatial. A prompt-derived skeleton is Structure-only. A round-trip IR has all five. An edit patch populates any subset at any target node.

This isn't pipeline ordering — it matches how designers actually work. Sometimes they start with boxes (Structure + Spatial), iterate variations there, fill detail later. Sometimes they start with theme. Sometimes they layer style onto an approved structure. Sometimes they jump straight to a detailed mockup. The substrate accepts every entry point, at any node, at any depth.

### 4.2 One grammar, many speakers

The same dd markup syntax expresses:

- **IR state** — what a screen is right now
- **Edits** — how to mutate it
- **Patterns** — reusable named subtrees
- **Themes** — token bundles
- **Archetypes** — skeleton definitions
- **Constraints** — system-level axes
- **Verifier feedback** — proposed edits to fix issues
- **Extract output** — what the extractor emitted
- **Synthesis output** — what the LLM emitted
- **User authoring** — what the designer typed

Every boundary where two speakers would use different grammars is a boundary where translation bugs live. We collapse those boundaries into one.

**There is no separate edit grammar.** Construction and editing parse through identical rules; the only distinction is whether a node is being created (`card #form-card { ... }`) or addressed by existing id (`@form-card radius={radius.lg}`). `append to=@card-1 { button ... }` is construction inside an edit target. `@card-1 radius={radius.lg}` is implicit `set` on an existing node.

### 4.3 Definitions as first-class — Alexander's Pattern Language, computationally

dd markup has **named reusable subtrees** (`define pattern.product-card { ... }`) and **references** (`& pattern.product-card title="..."`). This single mechanism subsumes five otherwise-separate concepts:

| Concept | Expressed as a `define` at... |
|---|---|
| Archetype skeleton (login, settings, feed) | Structure + Spatial axes |
| Theme / design-system styles | System + Visual axes |
| Project component library (Dank CKR) | `-> component/key` — external Figma instance |
| Universal catalog templates | Structure + partial Style axes |
| Edit template ("make primary") | Visual axis only, applied via overlay |

Every pattern, theme, archetype, component, and edit template is a definition. Every spec is a composition of references. This mirrors Christopher Alexander's 1977 *A Pattern Language*: patterns at different scales, referencing each other, constraining the solution space at the right altitude. The pattern library grows over time — through extraction, analysis, and user authoring — and the grammar treats the newest addition identically to the oldest archetype.

Three parametrization primitives for definitions, non-overlapping:

- **Typed scalar args** — `title: text = "Product"` — for Content/Visual scalars
- **Named slots with defaults** — `slot action = button/primary(...)` — for Structure variation
- **Path-addressed property overrides** — `pattern.product-card card.fill=black` — for partial axis overrides at call site

These don't unify. Collapsing them into "everything is slots" dies ergonomically — LLM emission produces div-wrapped spans, and Structure-axis refactors break all call sites. Production convergence across Vue, React+children, Svelte 5, and Figma Component Properties validates the three-primitive split.

### 4.4 Provenance — queryable and addressable

**Provenance** means: where each value came from. Six kinds:

- `extracted` — from the source Figma file
- `retrieved` — from a corpus donor during composition
- `substituted` — from an LLM intervention
- `synthesized` — from a catalog template or universal default
- `user-edited` — from a human author
- `catalog-default` — fallback when no other provenance applies

Provenance is first-class in dd markup: node-level annotations (`card (retrieved src="donor:142" conf=0.91)` inherits to descendants); per-value trailers (`fill=#F8F8F8 #[user-edited]`) only when the provenance is richer than what the value's syntax already self-describes. Verifier feedback targets low-confidence `synthesized` values first; users filter views by provenance kind. It's queryable across the pattern library, addressable in edits, and round-trips through the serde.

### 4.5 Multi-granularity editing as universal interface

Edits span every level: change a word, swap a button, add a card, move a group, change typeface, adjust padding, restyle a theme. These aren't different operations — they're the same dd markup grammar addressing different nodes at different tree depths.

The three CRAG modes **collapse to one operation**: "apply edits to a starting IR." They differ only in what the starting IR is:

| Mode | Starting IR | Edit volume |
|---|---|---|
| SCREEN_EDIT | Real donor IR (high retrieval confidence) | Small, targeted |
| COMPOSITION | Archetype skeleton + donor subtree references (mid) | Medium |
| SYNTHESIS | Archetype skeleton + catalog defaults (low/none) | Large |

Same grammar. Same pipeline. Same verification. User editing, multi-turn refinement, partial generation (fill one slot), and verifier critique are additional cases of the same operation — they just start from the current IR with different edit volumes.

Seven edit verbs, closed set: `set`, `append`, `insert`, `delete`, `move`, `swap`, `replace`. Addressed by stable `@eid`, never by positional index. `set` is implicit sugar on property assignment. Keyword args (`to=`, `from=`, `into=`, `after=`). No punctuation puzzles.

### 4.6 Progressive fallback

Renderers read the highest IR level available and degrade gracefully through lower levels. L0 is always the safety net — complete and lossless. Renderers never hard-fail; they degrade.

```
L3 (semantic intent / dd markup) → highest abstraction
  ↓ fallback
L2 (token bindings)              → design-system portability
  ↓ fallback
L1 (classification)              → component identity
  ↓ fallback
L0 (raw DB properties)           → complete, lossless, always available
```

---

## 5. The architectural insight — capability table IS the grammar

The system wasn't designed with a generator bolted on. The **load-bearing reason synthesis works on top of a round-trip compiler** is that **one table does two jobs**.

The per-property, per-backend **capability table** (ADR-001) serves both as the compile-time emission gate AND as the constrained-decoding grammar for LLM output. Not two systems that must be kept in sync — one system with two consumers. Adding a property extends both simultaneously. An LLM cannot emit an invalid property on an invalid node type because the same table that would refuse at emission time refuses at decode time.

Every other correctness-for-synthesis property flows from this alignment:

**LLM vocabulary comes from two mechanisms working together.** (1) **System-prompt exposure** lists the project's available tokens, components, patterns, and catalog types — it informs the LLM what choices exist. (2) **Grammar-constrained decoding** (XGrammar / Outlines / llguidance) masks the logits at emission so invalid paths are literally unreachable — it enforces that only valid choices get picked. Informing without enforcement produces hallucinations under distribution shift; enforcement without informing produces empty or repetitive output. Together they produce valid, diverse, design-system-compliant markup. Both depend on the same capability table.

**Boundary contract** (ADR-006) serves as both the extractor's failure channel AND pre-decode validation for LLM-produced component keys and token paths. Same `KIND_*` vocabulary both directions.

**Unified verification channel** (ADR-007) serves as both the round-trip parity check AND the dense per-node feedback signal for generation quality and repair. The verifier that proves round-trip is the verifier that rewards synthesis.

Same table, same vocabulary, same boundary contract, same verifier — used twice. This is why the architecture positions us for synthesis, not because of retrofitting but because the invariants were always the right shape.

---

## 6. Bidirectional + multi-level IR

Four coexisting levels, each adding information, none removing. Frontends fill the levels their source supports; backends read the highest level available and fall back.

```
FRONTENDS (parsers)                               BACKENDS (renderers)
                    ┌──────────────────────┐
Figma extraction ──→│                      │──→ Figma renderer (live, 204/204)
React parser ──────→│   Multi-Level IR     │──→ React + HTML/CSS (next)
SwiftUI parser ────→│                      │──→ SwiftUI renderer
Prompt / sketch ───→│   L0 ─ L1 ─ L2 ─ L3  │──→ Flutter renderer
                    └──────────────────────┘
```

- **L0** — DB `nodes` table. 77 columns per node. `parent_id` tree. Lossless.
- **L1** — `screen_component_instances` table. 48 canonical types via classification cascade.
- **L2** — `node_token_bindings` table. Property-level token refs (real or synthetic).
- **L3** — dd markup. Compact semantic tree. Human/LLM readable.

---

## 7. Roadmap

**Foundation — v0.3:** Complete dd markup spec + Figma renderer round-tripping the full Dank Experimental corpus through the markup at pixel parity. See `docs/requirements-v0.3.md` and `docs/plan-v0.3.md`.

Priorities after foundation:

1. **Synthetic generation** — the headline capability, decomposed into the four classes in §2 (screens / components / variations / style transfers). Same pipeline parameterized differently. Corresponds to v0.3 Stages 4–5 work (retrieval-augmented starting-IR selection + verifier-as-agent), gated on foundation completion.
2. **React + HTML/CSS renderer** — validates cross-platform IR claim with a real second backend. Same pattern as the Figma renderer: walks the L3 markup AST directly; resolves token / component / asset references against the React flavor of the catalog. Couples naturally with v0.3 Stage 6 (multi-target catalog schema).
3. **Additional backends** — SwiftUI, Flutter. Same pattern as React; different per-backend value transforms (see `docs/cross-platform-value-formats.md`).
4. **Additional extractors** — W3C DTCG tokens JSON (single-level import), Sketch / Penpot (variants of Figma extractor), React / SwiftUI parsers (reverse of renderers). Triggered by concrete pull.

---

## 8. Current state snapshot

**As of 2026-04-18:**

- 204/204 round-trip parity on Dank Experimental
- 86,766 nodes extracted across 338 screens
- 42,938 classified nodes (L1), 293,183 token bindings (L2)
- 129 components in CKR, 253 unique SVG path assets (26,050 node references)
- 319+ tests green on `v0.3-integration` branch (post-revert of premature CRAG work)
- ADRs 001 through 008 in force
- Investigation priorities resolved (see `docs/decisions/v0.3-*.md`)
- dd markup probe code exists (`dd/markup.py`, ~786 LOC) as starting point — but is a mechanical dict-IR serializer, not the axis-polymorphic L3 grammar specified here. Must be rebuilt for this foundation.

---

## 9. Navigation

| Document | Purpose |
|---|---|
| **This doc** (`docs/requirements.md`) | Canonical source of overall intent. |
| `docs/requirements-v0.3.md` | Requirements for the current phase (foundation). |
| `docs/plan-v0.3.md` | Plan A (write specs) + Plan B (execute). |
| `docs/spec-dd-markup-grammar.md` | Formal grammar spec (to be authored per Plan A.5). |
| `docs/spec-l0-l3-relationship.md` | L0↔L3 derivation algorithms (to be authored per Plan A.6). |
| `docs/compiler-architecture.md` | Authoritative technical spec for the already-built compiler. |
| `docs/architecture-decisions.md` | ADR-001 through ADR-008. |
| `docs/roadmap.md` | Long-form roadmap detail (existing doc; this file's §7 is the short version). |
| `docs/module-reference.md` | Per-module capability inventory. |
| `docs/decisions/` | Decision records from 2026-04-18 investigation round. Several superseded in framing; see each file's header. |
| `memory/MEMORY.md` | Cross-session memory index. |
| `memory/project_v0_3_plan.md` | Memory-resident summary of this plan for cross-session continuity. |

---

*This document is the top of the doc stack. If it conflicts with anything else in the repo, update this file first and let it propagate. When it grows past one page, split into sub-docs and link, don't delete.*
