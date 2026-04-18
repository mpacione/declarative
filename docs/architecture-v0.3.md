# Declarative Design — v0.3 Architecture

Canonical architecture document. The system's blueprint going forward. Every research thread that informed this is captured in `docs/research/v0.3-architecture-research.md`. The MVP implementation plan is `docs/continuation-v0.3-mvp.md`. The learnings and philosophical discussion are in `docs/learnings-v0.3.md`.

**Scope:** v0.3 is **internal infrastructure**, not a productized tool. The goal is architecture that works on Dank correctly end-to-end. Productization, distribution, and commercial positioning are explicitly out of scope. Evaluate every decision against "does this make the internal tool work" — not "does this sell."

This document supersedes `docs/continuation-v0.2-corpus-retrieval.md` as the forward direction. v0.1.5 and v0.2 machinery is preserved as the foundation; v0.3 builds on top without reverting 204/204 round-trip parity.

> **⚠ Next-session investigation required before MVP execution.** Three architectural critiques from the v0.3 review round raised real questions that must be investigated (not yet accepted as truth, but also not dismissed). See `docs/reviews/v0.3-review-synthesis.md` and `docs/continuation-v0.3-next-session.md` for the specific investigation list. Do NOT start MVP Stage 1 until the underscore-field question, the grammar-mode question, and the RenderReport-schema question are resolved on paper.

---

## Executive summary

**What this is:** A bidirectional design compiler for internal use. Parses UI from any source (Figma today; code/screenshots/prompts later) into an abstract IR, generates from that IR to Figma with design-token-bound fidelity (multi-target renderers deferred). Proven at 204/204 round-trip parity on an 86K-node Dank Figma corpus.

**What's new in v0.3:**
1. **Axis-polymorphic markup language** as the authoring surface for humans and LLMs, replacing JSON-as-the-UI for both. Every IR artifact (screen, pattern, edit, brief, diff) is expressible in this grammar.
2. **Density-per-node** (not levels) — every node is a point in a 5-axis specification space; any axis subset is valid.
3. **Named definitions + references** — patterns, themes, archetypes, edit templates all collapse into one reuse mechanism.
4. **Shared edit grammar** — the markup expresses IR state, diffs, and verifier feedback with one syntax.
5. **CRAG-style retrieval cascade** over the 42K classified corpus with three anchor modes (edit-donor, compose-subtrees, synthesize-from-skeleton).
6. **Verifier-as-agent** emitting the same edit grammar the generator uses — shared vocabulary, fresh context, monotone-accept.
7. **Synthetic tokens** for cold-start synthesis — raw values never hallucinated; always chosen from a token vocabulary (real or synthetic).
8. **Multi-target catalog schema** — per-target metadata per catalog entry (Code Connect + Style Dictionary patterns).

**What stays from v0.1.5/v0.2:**
- The round-trip extractor + renderer. 204/204 parity is load-bearing.
- The 42,938-node classified corpus + 338 skeletons.
- The existing IR shape (flat element map + token refs + layout + style + props) — v0.3 IR is a superset, not a replacement.
- The 1,950+ unit test suite.
- ADR-001 through ADR-008 principles (capability-gated emission, null-safe Mode 1, unified verification channel, etc.).

---

## 1. Foundational principles

### 1.1 Axis-polymorphic markup

Every node in the IR lives in a 5-axis specification space. Any subset of axes can be populated on any node independently.

| Axis | What it specifies |
|---|---|
| **Structure** | Types, children, hierarchy, slots |
| **Content** | Text, labels, data bindings, props |
| **Spatial** | Sizing, position, gap, padding, arrangement |
| **Visual** | Fills, strokes, effects, typography (per-node) |
| **System** | Token vocabulary, palette, type scale, spacing scale (project-wide) |

A node declares whatever it knows. Fields not present use defaults or are filled by later pipeline stages or the renderer.

**Why this matters:** different artifacts populate different axis subsets:
- A design brief: System axis only
- A wireframe: Structure + Spatial
- A prompt-derived skeleton: Structure only
- A full mockup: all five
- An edit patch: any subset, targeting existing eids
- Round-trip IR: all five, complete

All are valid markup in the same grammar. No "levels" or mode switches required.

### 1.2 Density-per-node, not levels

The T5 Pattern Language described five levels (Intent → Skeleton → Elaboration → Styling → Critique). That framing was **process-descriptive**, not markup-structural. A designer or an LLM pass fills axes in whatever order makes the current decision cheapest — which is *usually* Structure → Spatial → Content → Visual → System, but never required to be.

**Consequence:** The pipeline may use Pattern Language descent as an optimization (cheapest exploration goes through sparse-structure first, then elaborates). But the markup itself is fluid. A user who wants to start with a rich style brief and build structure around it is supported.

### 1.3 The IR never holds raw values

Every value in the IR is a reference. Either:
- **Real token** — resolves through the user's DTCG / Figma Variables / Style Dictionary vocabulary
- **Synthetic token** — created by the analysis layer, clustered from raw visual values (ΔE on colors, histogram on dimensions, nearest-step on type scale)
- **Universal-catalog default** — preloaded shadcn-flavored vocabulary for cold-start synthesis when no project tokens exist yet

The LLM picks from a known vocabulary — it never invents `#FF5733`. Grammar-constrained decoding enforces this at token emission. This is the same invariant the T5 archive specified (`t5-pattern-language.md` §L3 "The system cannot hallucinate a color") — v0.3 makes it enforceable at the grammar level, not just at review.

**Why synthetic tokens matter architecturally:** Scenario B (no design system, all raw values) degenerates into Scenario A (all tokens) the moment we cluster raw values into synthetic tokens at extract time. The IR, markup, and renderer stay uniform across all three scenarios. This is the load-bearing simplification.

### 1.4 One grammar, multiple speakers

The same markup grammar expresses:
- IR state (what the screen IS right now)
- Edits (how to mutate it)
- Patterns (reusable named subtrees)
- Themes (reusable token bundles)
- Archetypes (reusable skeletons)
- Constraints (system-level axes)
- Verifier feedback (proposed edits to fix issues)
- Extract output (what the extractor emitted)
- Synthesis output (what the LLM emitted)
- User authoring (what the designer typed)

Every layer of the pipeline speaks the same language. Constrained decoding uses one grammar. This is the deepest architectural unification in v0.3.

---

## 1.5. The canonical-IR question — resolved conservative

Raised 2026-04-18 after reviewer 3 flagged dual-representation risk: dict IR (round-trip path) vs dd markup (v0.3 LLM path). Two positions were considered:

- **Aggressive (unify):** dd markup becomes the canonical in-memory IR. Rewrites extract + renderers + composition providers to operate on the markup AST.
- **Conservative (bridge):** dd markup is a lossless serde over the dict IR. Dict IR remains canonical on the render path; markup is used at LLM boundaries.

**Decision: conservative.** Evidence: a throwaway serde (`dd/markup.py`) round-trips 204/204 app_screens at dict level (zero errors, 7.5s) AND produces byte-identical Figma scripts post-round-trip (204/204, 15.6s). Script-identity implies pixel parity by construction. Aggressive is a multi-week refactor for a maintenance optimization, not a feature enabler; conservative ships with zero renderer changes.

**Invariant this introduces:** any property added to the dict IR must also have a serde path through dd markup. Tests must verify round-trip parity remains 204/204 on every commit that touches the IR schema. Revisit aggressive only if an MVP feature requires it (none predicted).

**Full decision record:** `docs/decisions/v0.3-canonical-ir.md`.

**Consequences for downstream priorities:**
- **1A (underscore fields)** → resolved as bridge; no grammar-first-class treatment needed.
- **1B (grammar modes)** → unchanged.
- **1C (RenderReport schema)** → unchanged.
- **Priority 3 (provider audit)** → scope shrunk; providers keep operating on dict IR.
- **Priority 4 (parity gating)** → unchanged; still mandatory.

---

## 2. The markup language — overview

The dialect is called **dd markup** (file extension `.dd`). Syntactically it uses KDL v2 (finalized 2024) as the lexical and block-structure substrate, plus the extensions documented below (§2.1–2.6). Rationale for the KDL substrate in the research record §1 and §Thread 1 — the shortest defense: LLM-friendly, typed annotations in the grammar natively, built-in `/-` for deletes, has a schema language, and parsers exist. We do NOT call our dialect "KDL" in prose or spec — it is a dd-markup dialect atop KDL v2. Naming choice recorded 2026-04-18 after collision audit (avoided: DDL/SQL, DML/SQL, UIML, XAML, IDL, SDL-GraphQL).

### 2.1 Value grammar

```kdl
// Token reference (real or synthetic)
fill={color.brand.primary}

// Raw literal — value form tells you it's raw, no provenance trailer needed
fill=#FF5733
radius=16
text="Hello"

// Component instance (Mode 1) — external reference
button -> button/primary/lg

// Pattern reference (local definition) — inline expansion
& product-card

// Provenance annotation — only when interesting (not on every value)
fill=#F8F8F8 #[user-edited]
card (retrieved src="donor:142" conf=0.91)
```

Value-form IS provenance for the common case:
- Braces = token reference
- `#hex` / bare number / quoted string = raw literal
- `->` = external component instance
- `&` (or bare namespace path) = local pattern reference

### 2.2 Node declarations and references

```kdl
// Declare a new node with eid
card #form-card { ... }

// Reference an existing node (for edits or cross-references)
@form-card

// Anonymous declaration (eid auto-generated as type@N)
card { ... }
```

The two sigils `#` (declare) vs `@` (reference) are structurally mnemonic: `#` creates, `@` uses. No ambiguity.

### 2.3 Hierarchical paths

```kdl
// Nested expansion produces scoped paths
grid/product-card@0/buy-button   // auto-positional
grid/featured/buy-button         // when alias `as featured` used at call site

// Wildcards for bulk edits
@grid/*/buy-button label="Add to Cart"
```

Path separator: `/`. Dot-paths reserved for namespace (`pattern.product-card`) and property access (`card.fill=black`).

### 2.4 Edit operations — closed verb set

```kdl
// Implicit `set` (sugar)
@card-1 radius={radius.lg} fill={color.surface.elevated}

// Explicit set (always legal)
set @card-1 radius={radius.lg}

// Append a child (keyword args, not punctuation)
append to=@card-1 { link "Create account" color={color.action.link} }

// Insert with stable positional anchor (never by index)
insert into=@footer after=@logo { button label="Sign In" }

// Delete
delete @forgot-link

// Swap external-component reference
swap @submit to=button/primary/xl

// Replace a subtree
replace @submit with=link "Continue"

// Move (reparent)
move @submit to=@footer position=end
```

The seven verbs `set`, `append`, `insert`, `delete`, `move`, `swap`, `replace` are the complete edit vocabulary for v0.3. No English synonyms (`add`/`remove`/`edit`) — those create confusion for constrained decoding. All edits address by stable eid, never by index (JSON Whisperer finding: LLMs can't track index arithmetic across ops).

### 2.5 Definitions and references

```kdl
// At the top of a file
namespace pattern

define product-card(
  title: text = "Product",
  price: text,
  accent: color = {brand.primary},
) {
  card fill={color.surface.card} radius={radius.md} pad={space.md} {
    slot image                          // named slot, no default
    heading text=title font={typo.heading.s}
    text text=price font={typo.display.s} color=accent
    slot action = button/primary(label="Buy")   // slot with default
  }
}

// Importing a library
use "libs/ecommerce" as ec

// Using a definition
screen #home {
  & pattern.product-card title="Shoes" price="$120" {
    slot image: -> assets.shoes
  }
  & pattern.product-card as featured title="Featured" accent={brand.highlight} {
    slot image: -> assets.featured
    slot action = button/secondary(label="Shop")
  }
  & pattern.product-card title="Classic" price="$80" {
    slot image: -> assets.classic
    card.fill={color.surface.muted}            // path override
    heading.font={typo.heading.s-italic}       // path override
  }
}
```

Parametrization has three primitives with distinct responsibilities:
- **Typed scalar args** (`title: text`) for Content / single-value overrides
- **Named slots with defaults** (`slot action = button/primary(...)`) for Structure variation
- **Path-addressed property overrides** (`card.fill=black`) for partial axis overrides without declaring an arg

Override rules: call-site wins; slots and scalars replace by value; path overrides merge at property level; maps shallow-merge, arrays replace.

### 2.6 Provenance annotations

```kdl
// Node-level — inherits to descendants unless overridden
card (retrieved src="donor:142" conf=0.91) {
  heading "Welcome"                        // inherits retrieved
  button (substituted from=llm) label="Go" // overrides: LLM-provided
}

// Value-level trailer — only when interesting
card fill=#F8F8F8 #[raw reason="designer broke system"]
     radius={radius.md}                    // no trailer: default provenance
```

Four provenance kinds:
- `retrieved` — from a donor in the DB corpus
- `synthesized` — from a catalog template or universal default
- `substituted` — from an LLM intervention
- `user-edited` — from a human author

Provenance is queryable. "Show me all `synthesized` nodes with confidence <0.5" drives the verifier's repair target list.

---

## 3. The five markup-design decisions

These are the decisions that survived all research threads. Each is traceable to specific agents' findings.

### 3.1 Scoping + imports + cycles

- **One namespace per file.** Declared at top with `namespace <name>`.
- **Imports require mandatory alias:** `use "path/to/lib" as alias`.
- **Dot-paths for namespace resolution:** `alias.pattern.name` or local `pattern.name`.
- **Hard-error on cycles via three-color DFS** (parse-time). No silent partial-resolution. No tolerance.
- **No re-exports, no version pinning in syntax.** Version pinning lives at the registry / manifest level.
- **Last-in-file-wins with warning for shadowing.**

Research: `docs/research/v0.3-architecture-research.md` §Thread 1. Elm + W3C Design Tokens precedent.

### 3.2 Hierarchical IDs

- **Auto-generated `scope@N` suffix** by sibling-count when no explicit id or alias is given.
- **Explicit alias at call site:** `pattern.product-card as featured` or `pattern.product-card #promo`.
- **Propagating prefix for bulk naming:** `pattern.product-card name=hero` → children become `hero/title`, `hero/buy-button`.
- **Path separator is `/`.** Wildcards: `*` for same-level, `**` for any-descendant.
- **Constrained decoding enforces valid paths** against the live symbol table — eliminates LLM typos as a class.

Research: §Thread 2. MLIR + CSS Shadow Parts + React keys composite.

### 3.3 Parametrization

- **Three primitives, non-overlapping.** Typed scalar args + named slots with defaults + path-addressed property overrides.
- **Each primitive maps to specific axes.** Scalar args → Content/Visual scalars. Slots → Structure variation. Path overrides → partial axis overrides.
- **Figma Component Property model is the canonical precedent.** Text prop / Instance-swap prop / per-node override — exact parallel.
- **Override rules:** call-site > definition default (fail-open, no error). Maps shallow-merge; arrays replace.

Research: §Thread 3. Production convergence: Vue, React+children, Svelte 5, Figma. "Everything is slots" dies ergonomically.

### 3.4 Extract-vs-author distinction

- **Two sigils, deterministic parse:**
  - `-> component-key` = external component instance (source of truth: upstream component in Figma/React library)
  - `& pattern.name` = local pattern reference (source of truth: in-document `define`)
  - (no sigil) = inline structural subtree
- **Disambiguation by registry lookup:** `->` must resolve to a registered external key; `&` must resolve to a local `define`. Parser-level; no heuristic.
- **Extract emits ground truth.** INSTANCE nodes → `->`, FRAME nodes → inline. Never auto-collapses duplicates at extract time (preserves round-trip invariance).
- **Pattern detection is a separate optimization pass** with Rule of Three (N ≥ 3). Suggests, never applies. Users explicitly promote.
- **Four transitions documented:** inline → pattern, pattern → external component, external → inline (detach), external → pattern (fork).

Research: §Thread 4. Figma/Sketch/Penpot/Adobe XD/Framer/Storybook/React all follow the dual-node-type model.

### 3.5 Verifier-as-agent with shared grammar

- **Verifier emits edit operations in the same markup grammar as the generator.** Same verbs (`set`, `append`, `swap`, ...), same eid addressing, same token vocabulary.
- **Tiered ladder, not scalar score:**
  - Gate 1: Structural parity (ADR-007 RenderVerifier, per-node, hard)
  - Gate 2: Rule-based density (node count, container coverage, hard)
  - Gate 3: Jaccard fidelity (rank-only, for variant selection)
  - Gate 4: Pairwise VLM (rank-only, position-swap + majority vote)
- **Best-of-N variant generation** (N=3–5) > sequential refinement. Max 2 repair iterations on winner.
- **Fresh-context critic** prevents reward hacking (Pan 2024).
- **Quality-ceiling detection:** below Gate 1+2 thresholds, regenerate — do not refine.
- **Monotone-only accept** (ReLook): any dimension regression vetoes the revision.

Research: §Thread 4 (verify + refine) earlier. GUI-Critic-R1 + ReLook + UICrit precedents.

---

## 4. Pattern Language descent as pipeline optimization

The 5-level Pattern Language from `t5-pattern-language.md` is **one way the pipeline fills the markup axes**, optimizing for cheapest exploration. It is not a markup structural constraint.

**Pipeline staging (optimization, not required):**
```
L0 Intent           Prompt parsed into structured intent (archetype, platform, domain, density, mood)
L1 Skeleton         Fill Structure axis only, N variants (cheap)
L2 Elaboration      Fill slots + props on surviving skeletons (cheaper than full render)
L3 Styling          Apply tokens / visual axis (mostly deterministic)
L4 Critique         Verify + rank
L5 Refinement       Targeted edits via shared grammar
```

**What changed from T5:** L1/L2/L3 are pipeline stages; the markup grammar doesn't care which stage produced which fields. An L1 variant is valid markup at that density. An L3 variant is valid markup at that density. A user authoring at L3 directly is supported.

**Pattern Language as optimization:** when synthesizing from a prompt and the corpus, explore cheaply (Structure first, 3 variants, prune via rule-based critique) before committing LLM tokens to Content + Visual. When editing a retrieved donor (CRAG SCREEN_EDIT), skip L1 entirely because the donor has structure.

---

## 5. Retrieval cascade + synthetic tokens for cold start

### 5.1 CRAG-style three-mode cascade

```
Intent parsed
    ↓
Hybrid retrieval (hard SQL filter + soft multi-aspect rank)
    ↓
Fused match score → CRAG branch:

  score >= τ_high  →  SCREEN_EDIT
    starting IR = donor's IR (full, round-trip-verified)
    edits = content substitution + targeted adjustments via edit grammar
    
  τ_low <= score < τ_high  →  COMPOSITION
    starting IR = archetype skeleton
    donor subtrees (role-indexed) inserted as in-context exemplars
    LLM re-emits through grammar (never raw-stitches)
    
  score < τ_low  →  SYNTHESIS
    starting IR = archetype skeleton + universal catalog defaults
    LLM fills via Pattern Language descent (L1 → L2 → L3)
```

All three converge at the same pipeline stages 5 (content realization via edit grammar), 6 (render), and 7 (verify ladder).

### 5.2 Hybrid retrieval key

- **Hard filter** (SQL predicate): archetype × platform × domain
- **Soft rank** (multi-aspect fusion):
  - Structural similarity via pq-gram on L2 node-type sequences
  - Semantic similarity via sentence-transformer cosine on per-screen caption
  - Archetype classifier confidence as third signal
- **Fused score**: initial weights 0.4 semantic + 0.3 archetype + 0.3 structural; calibrate on held-out 20-breadth set.

At 204 screens, no graph autoencoders (Screen2Vec, Graph4GUI) — they need 15K+ to train from scratch. pq-gram + sentence-transformer is the proven sub-1K technique.

### 5.3 Synthetic tokens for cold start

Three vocabulary sources for the LLM at synthesis time:

| Scenario | Vocabulary source |
|---|---|
| Mature design system (Scenario A) | Real tokens from project DTCG / Figma Variables |
| No system, with extracted screens (Scenario B w/ extraction) | Synthetic tokens clustered from raw values (ΔE on colors, histogram on sizes/radii, nearest-step on type scale) |
| Cold start, no corpus yet (Scenario B pure) | Preloaded universal defaults (shadcn-flavored, the existing `_UNIVERSAL_MODE3_TOKENS`) |
| Dank-like mix (Scenario C) | Real where binding exists + synthetic for un-tokenized + universal for unmapped types |

In all four, the IR stores token refs. The renderer resolves through the token dictionary. The LLM never emits raw values — grammar constrains emission to valid token paths.

**What needs building:** the clustering pass (~100 lines) — ΔE on hex colors, histogram on dimensions, exact-match on typography. Produces a `synthetic_tokens` table with provenance pointing back to source node-ids.

---

## 6. Multi-target catalog extension

### 6.1 Schema shape

Each catalog entry extended with a per-target sub-object:

```json
{
  "catalog_id": "BUTTON_PRIMARY",
  "canonical_name": "Button",
  "variant_axes": ["size", "state"],
  "targets": {
    "figma": {
      "component_key": "dank:button-primary",
      "figma_node_id": "12345:67",
      "variant_map": {
        "size": { "sm": "Small", "md": "Medium", "lg": "Large" }
      }
    },
    "react": {
      "import": { "module": "@dank/ui", "name": "Button" },
      "prop_map": {
        "size": { "kind": "enum", "values": {"sm":"sm","md":"md"} }
      }
    },
    "swiftui": {
      "module": "DankUI",
      "view": "Button",
      "prop_map": { "size": { "kind": "enum", "values": {"sm":".small"} } }
    }
  }
}
```

- Mirrors Figma Code Connect's `figma.connect(ComponentRef, ...)` primitive set (`figma.enum`, `figma.boolean`, `figma.instance`) — the proven minimum vocabulary.
- Analogous to Style Dictionary's `platforms[name]` — target key flat, each target holds its own resolver table.
- `prop_map` is N:M by construction (real-world mapping is rarely 1:1).

### 6.2 Token resolution per target

Separate `token_platforms` table keyed `(token_id, target)` holding `name_transform`, `value_transform`, `output_path`. Tokens stay DTCG-pure. Don't put Tailwind class names inside `token_values`.

### 6.3 What this unlocks

Adding a new output target = adding one renderer + populating one sub-object per catalog entry. Mitosis is what you reach for if you need React/Vue/Svelte/Qwik/Solid codegen specifically — don't rebuild it.

### 6.4 Priority

Multi-target schema is an architectural extension but **not** required for v0.3 MVP. Ship Figma first; add React once the architecture is validated. The schema shape is fixed so existing data migrates without breakage when additional targets are added.

---

## 7. What's already built vs what v0.3 adds

### Already built (v0.1.5 + v0.2, load-bearing foundation)
- Bidirectional Figma extractor (REST + Plugin API supplement), 72-column `nodes` table, 86,766 nodes
- Round-trip renderer with 204/204 parity (ADR-001 capability-gated emission, ADR-007 verification channel, ADR-008 Mode-3 composition, all associated guardrails)
- Classification pipeline: `dd classify` → 42,938 labeled nodes + 338 screen skeletons (1.5 s)
- Token extraction + export infrastructure (CSS, Tailwind, DTCG, Figma variables)
- Component key registry (129 Dank component keys, 27,811 instances)
- Current Mode-3 synthesis pipeline (archetype classifier + universal catalog + splice)
- CorpusRetrievalProvider (behind `DD_ENABLE_CORPUS_RETRIEVAL`) — component-level subtree retrieval with structural match ranking
- Fidelity scorer + experiment drivers (00g, 00i, 00j)
- 1,950+ unit tests green

### New in v0.3 (additive, behind flags)
- KDL-based markup language parser (tree-sitter grammar + Python parser)
- Markup emitter from existing IR (for extracted screens)
- Definition + reference expansion (patterns, themes, archetypes as `define` blocks)
- Imperative-verb edit grammar on top of markup
- Synthetic token clustering pass (ΔE on colors, histograms on dimensions)
- CRAG-style three-mode cascade in synthesis
- Tiered verifier ladder (Gates 1–4) with agentic edit emission
- Multi-target catalog schema (forward compatibility; Figma first)
- `pattern-detect` subcommand (optimization pass, suggests only)

### Deferred beyond v0.3
- Taste model (quality-weighted distributions)
- Decision tree as persisted data
- Autonomous experimentation / self-play
- Full action taxonomy Tier 1–6 (v0.3 ships Tier 5 Group B only)
- Real React/SwiftUI/Flutter renderers (Figma first)
- Second-project portability validation

---

## 8. Build order

Staged for maximum early validation. Each stage produces a shippable artifact.

### Stage 0 — Prerequisites (done)
Classification complete (42,938 labels). 204/204 parity preserved. Baseline A/B numbers established on 00g (mean render-fid 0.728) and 00i (0.722).

### Stage 1 — Markup parser + emitter (MVP scope, ~2 weeks)
1. KDL-based grammar specification (v0.3.grammar)
2. Python parser → AST → IR
3. IR → markup emitter (for extracted screens)
4. Round-trip test: extracted IR → markup → IR → parity check on 20 sample screens
5. Grammar-constrained decoding integration (XGrammar or llguidance)

**Ship gate:** 20-sample round-trip at 100% parity via markup path.

### Stage 2 — Definitions + references (~1 week)
1. `define` / `use` / `namespace` grammar
2. Expansion algorithm with scope-table + auto-positional IDs
3. Cycle detection (three-color DFS)
4. Shadowing + precedence rules
5. Pattern detection (post-extract optimization, suggests only)

**Ship gate:** At least 12 hand-authored archetype skeletons from v0.1.5 rewritten as `define` blocks; synthesis uses them as starting IR.

### Stage 3 — Synthetic tokens for cold start (~3 days)
1. ΔE clustering on fills
2. Histogram clustering on dimensions
3. Nearest-step on type scale
4. New `synthetic_tokens` table + integration with IR token dictionary
5. Universal catalog defaults preloaded from shadcn data

**Ship gate:** Synthesis for 12-prompt canonical 00g never emits a raw hex color in the IR.

### Stage 4 — Edit grammar + CRAG cascade (~2 weeks)
1. Edit verb parser (`set`, `append`, `insert`, `delete`, `move`, `swap`, `replace`)
2. Applied-edit engine on IR
3. CRAG retrieval + τ thresholds (calibrated on 20-breadth set)
4. SCREEN_EDIT path (retrieve donor → emit edits → apply → render)
5. COMPOSITION path (archetype skeleton + donor exemplars + re-emit)
6. SYNTHESIS path (L1 → L2 → L3 descent)

**Ship gate:** 00g A/B with three-mode cascade produces mean fidelity ≥ 0.75 (vs current 0.728 baseline), with per-prompt regression ≤ 0.05 on any single prompt.

### Stage 5 — Verifier-as-agent (~1 week)
1. Gate 1–4 ladder implementation
2. Pairwise VLM (position-swap + majority vote)
3. Agentic critic emitting edit grammar
4. Best-of-N generation (N=3) with monotone-accept
5. Quality-ceiling detection (below threshold → regenerate, not refine)

**Ship gate:** 00g pairwise VLM agreement ≥ 75% vs human judgment on a 20-pair held-out set. Retrieval-on vs retrieval-off shows ≥ 1-point mean VLM improvement.

### Stage 6 — Multi-target catalog schema (optional for v0.3, ~1 week)
1. `targets` column on `component_type_catalog` (JSON blob)
2. Migration from current Figma-only columns
3. `token_platforms` table for per-target token resolution
4. React renderer stub (proof of schema, no production codegen yet)

**Ship gate:** Schema migration succeeds; existing Figma path unchanged; one hand-written React sub-object validates end-to-end.

---

## 9. Invariants that v0.3 cannot violate

These come from v0.1.5/v0.2 and earlier ADRs. Any change that breaks one of these is rejected, even if it's "cleaner."

1. **204/204 round-trip parity on Dank Experimental.** Every commit runs the sweep. Anything under 204 halts the work.
2. **1,950+ unit tests green** (current baseline). Regression requires rollback.
3. **Capability-gated emission** (ADR-001) — every property emission goes through the is_capable gate. Grammar extensions must register capabilities.
4. **Null-safe Mode 1** (ADR-002) — every `createInstance` has a missing-component placeholder fallback.
5. **Structured error channel** (ADR-006) — failures never silently swallow; always emit KIND_* diagnostics.
6. **Unified verification channel** (ADR-007) — per-node granularity for all verifier signals.
7. **Token-bound fidelity (synthesis regime).** Token refs are the canonical form for clusterable-axis values in **synthesis output** and LLM-facing IR. Extract-produced IR may hold raw values on any axis; clustering promotes them to refs where a binding exists. Renderers must accept either form and resolve via `TokenCascade` as needed. Resolved 2026-04-18 per `docs/decisions/v0.3-grammar-modes.md`.
7a. **One grammar, three validation modes.** The dd-markup grammar is one syntax. Validation operates in three modes: **Extract** (raw permitted), **Synthesis** (token-only on clusterable axes), **Render** (backend-capability-gated). A document is valid under one or more modes; documents from different sources must not be assumed valid under all modes.
8. **Dict IR is canonical on the render path.** dd markup is a lossless serde over the dict IR, NOT the in-memory representation used by extract/compose/render. Every dict IR property must have a serde path through dd markup; tests must verify 204/204 round-trip on every IR schema change. Added 2026-04-18 per `docs/decisions/v0.3-canonical-ir.md`.
9. **Leaf-parent gate** (Fix #1) — TEXT/RECTANGLE/VECTOR/LINE nodes cannot have appendChild called on them.

---

## 10. What success looks like at v0.3 ship

For the internal-tool scope, success means the architecture works end-to-end on Dank with no regressions. Concretely:

1. Any Dank screen can be extracted → emitted as markup → parsed → rendered back with structural parity.
2. A Dank pattern library (archetype skeletons as `define` blocks, imported via `use`) can be composed against during Mode-3 synthesis.
3. Existing 12 canonical prompts produce output with mean render-fidelity ≥ 0.8 (vs 0.728 baseline) via the retrieval cascade.
4. The verifier emits targeted edit proposals in the shared grammar and closes at ≤ 2 iterations.
5. Every IR — extracted, synthesized, or hand-authored in markup — renders identically because they're the same shape.
6. All v0.1.5/v0.2 invariants preserved: 204/204 parity, 1,950+ tests, ADR-001 through ADR-008.

**Not success criteria for v0.3:** user adoption, commercial validation, multi-target renderers beyond Figma, usability for non-technical designers, go-to-market fit. Those are out of scope. If v0.3 works architecturally on Dank, it's done.

### Grammar audience

The markup targets **LLM-friendly + technical-reader human-readable**. The reader is an engineer or design-systems technical person, not a designer using the tool casually. KDL syntax choices are oriented around constrained-decoding reliability and parseable structure. Designer-facing UX is a v0.4+ concern.

---

*Decisions in this document are traceable to `docs/research/v0.3-architecture-research.md`. Reviewer findings from 2026-04-18 at `docs/reviews/v0.3-reviews-full.md` + synthesis at `docs/reviews/v0.3-review-synthesis.md`. Investigation priorities for next session at `docs/continuation-v0.3-next-session.md`. Philosophical choices + architecture spec at `docs/learnings-v0.3.md`. Concrete implementation plan in `docs/continuation-v0.3-mvp.md`.*
