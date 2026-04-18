# L0 ↔ L3 Relationship Specification

**Status:** ⚠ PLACEHOLDER. To be authored during Plan A.6, after Plan A.4 (fixtures) and Plan A.5 (grammar) are stable. See `docs/plan-v0.3.md`.
**Purpose:** specify the bidirectional relationship between L0 (the complete DB scene graph) and L3 (dd markup, the compact semantic tree) — including how L3 is derived from L0+L1+L2 (compression), how L3 renders back to Figma (expansion), and what constitutes a round-trip proof.
**Authored:** 2026-04-18 (scaffold only).

This spec answers the question: **when we have the dd markup grammar (from S2) and hand-authored fixtures (S4), how does the rest of the system produce and consume them?**

---

## Relationship to the other specs

- **`docs/requirements.md`** (Tier 0) states the design principles and invariants this spec must uphold.
- **`docs/requirements-v0.3.md`** (Tier 1) scopes what must be deliverable by v0.3.
- **`docs/spec-dd-markup-grammar.md`** (S2) defines the surface syntax.
- **This doc** defines the semantics — what the markup *means* at the IR level.
- **`tests/fixtures/markup/`** (S4) are the ground-truth examples this spec must produce from and consume back.

---

## Table of contents (to be filled in during Plan A.6)

### 1. Introduction
- What this spec covers (L0 ↔ L3 direction in both directions)
- What it does NOT cover (pure dd markup parsing — in S2; rendering L3 → pixels — delegated but described)
- Relationship to existing machinery (`dd/ir.py::generate_ir`, `dd/renderers/figma.py::generate_screen`)

### 2. Compression — extracting L3 from L0+L1+L2
- Input: DB rows for a Dank screen (L0), classifications (L1), token bindings (L2)
- Output: a `.dd` document — dd markup at L3 semantic density
- Target density: ~20 elements for a screen with ~200 L0 nodes
- Algorithm with per-axis decomposition:
  - **Structure axis:** which L0 nodes survive as L3 elements? Which collapse into component refs? Which become inline subtrees?
  - **Content axis:** text strings, labels, slot fills — direct transfer
  - **Spatial axis:** sizing ground-truth from DB → `fill` / `hug` / `fixed` semantic values + token refs where possible
  - **Visual axis:** fills/strokes/effects via `{token.path}` when L2 binding exists, raw-cluster-to-synthetic-token after Stage 3, literal only when nothing else works
  - **System axis:** top-level `tokens` block with resolved palette / scales
- Handling of L1 classification cascade:
  - INSTANCE → component ref (`-> component/key`)
  - FRAME with SCI classification → canonical type (card / button / etc.)
  - FRAME without SCI → inline structural node with primitive type
  - Synthetic nodes (platform artifacts) filtered at the L0 boundary per `feedback_synthetic_allowlist_not_heuristic`
- Handling of L2 bindings:
  - Bound property → `{token.path}` reference
  - Unbound property → raw literal (pre-Stage-3) OR synthetic token ref (post-Stage-3)
- Provenance emission: extracted-from-source provenance is the default for compression output; annotate only when interesting
- Children composition and override trees
- Deterministic ordering (for byte-stable round-trips)

### 3. Expansion — rendering L3 back to Figma
- Input: a `.dd` document at arbitrary axis density
- Output: a Figma script (via the existing `generate_figma_script` path) at pixel parity with the source (if it came from extraction)

Two candidate architectures — pick one in Plan A.6:

**Option A — L3 → L0 lowering, reuse existing renderer.**
Parse dd markup → produce a dict IR with all axes populated (filling defaults for unpopulated axes via catalog / component / theme) → hand to existing `generate_figma_script`. Zero renderer changes.

**Option B — L3-aware renderer.**
A new renderer path that walks the markup AST directly, resolving references at emit time. Potentially more efficient; potentially better at preserving provenance through to the emitted script. Duplicates machinery.

**Tentative preference:** Option A. Keeps the 204/204 dict-IR renderer as ground truth; dd markup round-trip becomes "markup → dict IR → existing renderer." The only new code is the markup-to-dict-IR lowering.

Either option must handle:
- `-> component/key` resolution via CKR + `getNodeByIdAsync`
- `& pattern.name` expansion via the definition table
- `{token.path}` resolution via the existing `TokenCascade` (project → ingested → universal layers)
- Default-fill when axes are unpopulated (component template defaults / catalog type defaults / platform defaults — same as today)
- Synthetic node filtering at the L0 boundary
- Leaf-parent gate (TEXT/RECTANGLE/VECTOR/LINE can't have appendChild)

### 4. Round-trip proof shape
- Pipeline: source Figma → extract (L0+L1+L2) → compress to L3 (dd markup) → expand back to Figma script → render → verify `is_parity=True`
- Tier-by-tier evidence (analogous to today's three-tier proof):
  - **Tier 1 — Dict-level round-trip.** `compress → expand → dict-IR == original-dict-IR` (structural equality, not byte)
  - **Tier 2 — Script byte-parity.** `generate_figma_script(original)` and `generate_figma_script(expand(compress(original)))` produce byte-identical scripts
  - **Tier 3 — Pixel parity via Figma sweep.** `render_batch/sweep.py` with markup-path enabled reports 204/204 `is_parity=True`
- Which tier is the blocking gate for each stage (Stage 1 ships Tier 1+2; Tier 3 follows)

### 5. Density semantics
- L3 at full density round-trips extractions
- L3 at reduced density (wireframe only, style only, mixed) does NOT round-trip to pixel-identical Figma, by construction — defaults fill in missing axes
- Which axis subsets are round-trippable:
  - All 5 axes populated → yes, pixel parity on extraction source
  - Missing Visual or System → renders with defaults, not pixel-equivalent to source
  - Missing Structure → cannot render
- How the compiler distinguishes "intentionally sparse" (author wanted defaults) from "incomplete" (author forgot to fill in)

### 6. Definitions and expansion
- How `define` / `&` expand during L3 → renderable-IR lowering
- Scope resolution, parametrization (scalar args / slot fills / path overrides)
- Auto-generated ids in expanded subtrees (Tier 0 §4.3)
- Interaction with `-> component/key` — local patterns vs external Figma components

### 7. Interaction with existing machinery
- `dd/ir.py::generate_ir` — does it stay and compress output to L3 as an additional step, or is L3 compression a separate pipeline?
- `dd/renderers/figma.py::generate_screen` — unchanged per Option A above
- `dd/composition/*` — how does this relate to generation from prompts (Stage 4 work — defer detailed coupling)
- `render_batch/sweep.py` — how does the markup round-trip plug in (env var, separate CLI mode, or first-class)

### 8. Open questions (resolved during Plan A.6)

---

## Open questions (must resolve before this spec is complete)

### OQ-1. Which L0 nodes become L3 elements?

**Question:** for a screen with 200 L0 nodes, which ~20 appear in L3?

**Candidates:**
- Every classified (SCI-annotated) node of a "semantic" type (card, header, button, etc.)
- Every FRAME with children that are also in L3 (container preservation)
- Every TEXT node that's not purely decorative
- Roll up sibling groups into a single L3 element when structurally equivalent (e.g., 5 identical toggle-rows → one `list<toggle-row>` element with count hint)

**Depends on:** the 3 reference screens (Plan A.3) showing concretely which nodes appear in the fixtures.

### OQ-2. Inline vs component reference decision

**Question:** at extract time, when does a FRAME become inline (`card { ... }`) vs a component ref (`-> card/standard`)?

**Candidate:** INSTANCE nodes always become `-> component/key`; FRAMEs are always inline. This matches `feedback_figma_frames_are_visual` — a frame IS a visual element, not a structural wrapper.

**Depends on:** confirmation against fixtures.

### OQ-3. Inline pattern detection — suggested, not applied

**Question:** during extraction of Dank, five cards with identical structure exist. Does the extractor emit them as five inline blocks, or suggest a `define pattern.card`?

**Candidate** (from Tier 0 §3.2): emit inline. Pattern detection is a separate optimization pass (Rule of Three) that runs post-extract and produces a suggestion — user-gated promotion, never auto-applied.

### OQ-4. Synthetic token emission timing

**Question:** when do raw values in L0 become synthetic tokens in L3?

**Candidate:** Stage 3 clustering pass runs post-extract, post-classification. Before Stage 3, L3 compression emits raw literals for un-tokenized values (violates Tier 0 §3.3 temporarily). After Stage 3, every un-tokenized value resolves to a synthetic token during compression.

**Implication:** Stage 1 round-trip parity is technically possible with raw literals present in L3 (Tier 0 invariant temporarily waived for the extract-path L3). Stage 3 closes the invariant.

### OQ-5. Expansion — Option A vs Option B

**Question:** does L3 lower to dict IR and reuse the existing renderer (Option A), or is there a new L3-aware renderer (Option B)?

**Candidate:** Option A for v0.3 to minimize renderer changes. Option B as a future consideration if (a) expansion produces code that's meaningfully different, or (b) we want L3-native edit feedback without round-tripping through dict IR.

**Needs:** concrete algorithm for "markup → dict IR lowering" that handles all axis densities.

### OQ-6. Tier 1 / Tier 2 / Tier 3 cadence during Stage 1

**Question:** for the round-trip proof on the 204 corpus, which tiers run when?

**Candidate:** Tier 1 (dict round-trip) for every commit. Tier 2 (script byte-parity) for every PR. Tier 3 (pixel parity via Figma bridge) for every merge to `main` + nightly. Matches existing branching strategy (`docs/decisions/v0.3-branching-strategy.md`).

### OQ-7. Density round-trippability

**Question:** a wireframe-density `.dd` file cannot pixel-round-trip — defaults fill in missing axes. What does it round-trip through?

**Candidate:** wireframe round-trips to a Figma file where default fills occupy the Visual axis, catalog defaults occupy Spatial where unspecified, etc. The Figma output is NOT pixel-equivalent to a fully-specified source; it's a coherent output that reflects the sparse input. Verifier reports match at the densities that were specified; absences are not failures.

**Needs:** clarification of when a round-trip test expects pixel parity vs structural parity vs semantic parity.

### OQ-8. Compression algorithm determinism

**Question:** does compression produce byte-identical `.dd` output on re-run (same DB snapshot)?

**Candidate:** yes. Deterministic ordering required for Tier 2 script byte-parity. Sort rules: Dict key insertion order (L0), stable sort on eid, etc.

### OQ-9. Interaction with override trees

**Question:** Figma instance overrides are stored as an override_tree today. How does L3 compress them?

**Candidate:** flatten override tree onto the `-> component/key` reference; each override becomes a property on the reference site. Nested instance swaps become nested `->` references.

**Needs:** concrete examples from Dank corpus.

### OQ-10. Relationship to `generate_ir`

**Question:** `dd/ir.py::generate_ir` already produces a dict IR (L0+L1+L2 merged). Does the L3 compression pass consume that output, or read directly from DB?

**Candidate:** consume `generate_ir` output. Keeps the existing machinery as the authoritative dict-IR layer; L3 compression becomes a thin layer on top.

---

## Plan A.6 deliverables

When this doc is complete:

1. All 10 open questions have decisions recorded.
2. The compression algorithm is specified precisely enough for a human reader to hand-simulate it on one reference screen and produce the same `.dd` as the fixture.
3. The expansion algorithm is specified precisely enough to predict what the existing `generate_figma_script` would emit given a parsed `.dd` AST.
4. The round-trip proof shape is specified with concrete acceptance criteria per tier.
5. The relationship to existing machinery (`generate_ir`, `generate_screen`, `sweep.py`) is diagrammed.

---

## Implementation hook

Plan B Stage 1.4 implements the compression algorithm (emitter side). Plan B Stage 1.2 implements the expansion (parser-to-dict-IR lowering, if Option A chosen). The round-trip tests (Plan B 1.5–1.7) exercise both ends against the fixtures and the 204 corpus.

---

*Plan A.6 authors this doc after A.4+A.5 are stable. Plan B Stage 1 implements against it. No code is written for compression/expansion before this doc is stable.*
