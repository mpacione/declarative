# v0.3 — Minimum Viable First Implementation

The smallest code change that proves the v0.3 architecture works end-to-end. Referenced from `docs/architecture-v0.3.md` §8 Stage 1.

> **⚠ Prerequisites before this MVP can begin.** Three architectural critiques from the v0.3 review round flagged MVP-blocking questions (underscore fields representation, grammar modes for raw-vs-tokenized, RenderReport schema). These must be investigated and resolved on paper before Day 1 of this MVP. See `docs/continuation-v0.3-next-session.md` §Investigation priorities. Do NOT start without that resolution — the MVP probability drops below useful if executed against unresolved architectural questions.

**Goal (both, per user decision 2):**
1. Grammar completeness — markup can express the existing IR losslessly
2. Full Figma round-trip — parse(markup) → IR → render → verify 100% parity

These are two claims. The MVP aims at both; the first is the harder-to-fail gate, the second is the architectural premise.

**Scope:** internal tool working on Dank. No user-facing surface. No productization.

Derived from the simplest question: **if markup → IR → render preserves 100% parity on even one screen, the architectural premise is validated. Everything else is extension.**

---

## MVP scope (one sentence)

**Build a KDL-based markup parser + emitter that round-trips at least one real Dank screen through markup with 100% structural parity, matching the existing 204/204 baseline.**

That's it. No edit grammar yet. No synthesis yet. No verifier changes. No multi-target. No definitions/references beyond the minimum needed to express the IR. Just: can the markup represent what the IR already represents, losslessly?

If yes → the architecture is sound, subsequent stages proceed.
If no → we learn what the IR carries that the markup can't express, and the architecture has a gap to close before any downstream work.

---

## Success criteria

Three hard gates. All three must pass for MVP to be "done."

1. **Round-trip parity at 100%.** One extracted screen → emit markup → parse markup → generate IR → render → walk → verify. Zero structural differences from the original round-trip. If 1 of 20 sample screens fails, MVP is not done.
2. **No regressions.** `render_batch/sweep.py` still reports 204/204. The 1,950+ unit tests still pass. The markup path is purely additive.
3. **Parser + emitter are inverses.** `parse(emit(ir)) == ir` on every test screen (including edge cases like text with special chars, instances with override trees, gradient fills).

Stretch (nice to have, not required):
- Round-trip all 20 breadth-test screens (00i-breadth).
- Parse time < 100ms for typical screen.
- Emit time < 50ms.

---

## Deliverables

### File-by-file scope

```
dd/markup/
├── grammar.py              # Grammar rules, value forms, reserved tokens
├── parser.py               # Markup string → AST
├── emitter.py              # IR → markup string
├── ast.py                  # AST node types (Node, Value, Annotation)
├── ir_bridge.py            # AST ↔ CompositionSpec IR
└── __init__.py             # Public API: parse(), emit(), round_trip_test()

tests/
├── test_markup_parser.py       # Grammar + parser tests (TDD, ≥50 tests)
├── test_markup_emitter.py      # IR → markup tests (TDD, ≥30 tests)
├── test_markup_roundtrip.py    # Full round-trip on 20 sample screens
└── fixtures/markup/            # Hand-authored golden-file snippets

docs/
└── markup-grammar.md           # Formal grammar spec for reference
```

### No changes outside `dd/markup/` and `tests/` for MVP

The existing IR (`dd/compose.py` CompositionSpec shape), the existing renderer (`dd/renderers/figma.py`), and the existing extractor (`dd/extract_screens.py`, etc.) are **unchanged**. The markup module is a new peer that produces and consumes the same IR shape.

If the IR needs extension during MVP work (e.g., an optional provenance field), that's a flag we surface and debate — but ideally avoid.

---

## Implementation plan (sprint-style, one engineer, ~2 weeks)

### Week 1

**Day 1 — Grammar spec + test fixtures**
- Write `docs/markup-grammar.md`: a concrete BNF / pseudo-EBNF for v0.3 KDL.
- Hand-author `tests/fixtures/markup/01-login-expected.kdl` from the existing extracted IR for screen 1. Not auto-generated — done by hand, checked in, is the canonical example.
- Commit just the grammar and fixtures.

**Day 2-3 — Parser (TDD)**
- TDD: write 20+ tests for grammar pieces (value forms, node declarations, references, nesting, annotations).
- Implement `dd/markup/parser.py` with either tree-sitter-kdl or a hand-written recursive-descent parser. Hand-written is faster to iterate; tree-sitter is sturdier for grammar evolution.
- Cover: `{token.refs}`, raw values, component refs (`->`), node declarations (`type #eid { ... }`), wildcards (`*`, `**`), provenance annotations (`(retrieved ...)`), and property assignments (`key=value`).

**Day 4-5 — Emitter (TDD)**
- TDD: given an IR CompositionSpec, produce a markup string.
- Implement `dd/markup/emitter.py`.
- Two emit modes: **compact** (no whitespace/indent — shortest form; used in LLM prompts) and **pretty** (2-space indent — for human-readable files).
- Cover: sparse vs dense node output, token refs, instance refs, nested children, provenance annotations, escape sequences in strings.

**Day 6 — IR bridge**
- `dd/markup/ir_bridge.py`: AST → `CompositionSpec` and back.
- The markup's node becomes an IR element (via `elements[eid]`). Children are flattened into the spec's element map with eid references.
- Make sure `_node_id_map` survives a round-trip — it's how the renderer resolves real DB visuals vs synthetic.

**Day 7 — Round-trip test on one screen**
- `tests/test_markup_roundtrip.py::test_screen_1_roundtrip`.
- Pipeline: extract screen 1's IR → emit markup → write to disk → parse it back → compare ASTs and IRs. Assert equivalence.
- Pipeline part 2: render the parsed IR via existing `generate_figma_script` → walk via existing bridge → verify parity against original extraction. Zero diff.

### Week 2

**Day 8-9 — 20-sample coverage**
- Extend round-trip to 20 varied screens (small/large, with/without instances, with/without gradients, text-heavy, image-heavy, multi-depth).
- Debug each failure class. Common failures to watch for:
  - Gradient fills: JSON sub-structure round-trip
  - Instance override trees: nested provenance
  - Large text strings: escape handling
  - Vector paths: long string values
  - Font weight/style variants: value form ambiguity

**Day 10 — Parser-emitter inverse property**
- For each of the 20 screens, assert `parse(emit(ir)) == ir` (structural equality, not byte-for-byte).
- Also assert `emit(parse(markup)) == markup` for hand-authored markup files.

**Day 11-12 — Grammar-constrained decoding smoke test**
- Pick an LLM-friendly grammar format (XGrammar .gbnf or llguidance).
- Convert the v0.3 grammar to the format.
- Smoke test: Claude Haiku + constrained decoding, asked to emit a login screen in v0.3 markup. Verify output parses.
- This is only a smoke test — not production synthesis yet. Just confirms the grammar CAN be constrained-decoded.

**Day 13 — Documentation + commit**
- Update `docs/markup-grammar.md` with examples.
- Add a README in `dd/markup/` explaining the module.
- Commit with tests passing.

**Day 14 — Stress test + slack**
- Run the markup path on all 204 app_screens. Track which ones fail.
- Buffer for edge cases + integration fixes.

### Deliverable at end of week 2

- `dd/markup/` module with parser + emitter
- ≥100 unit tests in `tests/test_markup_*.py`
- 20 sample screens round-trip at 100% parity
- Grammar spec in `docs/markup-grammar.md`
- One commit: `feat(v0.3): markup parser + emitter with 20-screen round-trip parity`

---

## Go/no-go decision after MVP

Three possible outcomes:

### (a) 20/20 round-trip, no regressions → GO to Stage 2

Architecture validated. Proceed to definitions + references (`define` / `use` / `&`) per architecture doc §8 Stage 2. Markup becomes the authoring substrate for archetype skeletons; the 12 hand-authored JSON skeletons migrate to markup form.

### (b) 18/20 round-trip, edge cases documented → GO with caveats

Most screens work. Document the 2 failure classes as known edge cases. Proceed to Stage 2 but keep a TODO list for the failures. Likely failure classes (predicted): very deep nested instances, screens with exotic vector geometry, text-content with unusual unicode.

### (c) <15/20 round-trip OR IR changes required → PAUSE + REDESIGN

The markup is insufficient. Before proceeding, add what's missing to grammar/parser. Possible missing: richer escape handling, missing value form for some DB column, missing provenance kind. Re-execute MVP until gate clears.

If multiple redesign rounds happen, the architectural assumption is wrong and requires deeper rethink. Escalate.

---

## Architecture audience

The markup grammar targets **LLM-friendly + technical-reader human-readable**. Not designer-facing for v0.3. Reviewer 4's usability concern (designers struggling with `@eid`/`#eid`/`->`/`&`/wildcards) is explicitly out of scope — the reader is an engineer or design-systems technical lead, not a designer using the tool casually. This constrains grammar-complexity tradeoffs: favor constrained-decoding reliability and precise parse semantics over visual accessibility.

## What is NOT in the MVP

Explicitly deferred — do not sneak these in.

- **Edit grammar operations** (`set`, `append`, etc.). Round-trip first; edits are Stage 4.
- **Definitions + references.** Can be tested with hand-authored KDL but not wired into extract yet. Stage 2.
- **Synthetic tokens clustering.** Stage 3.
- **CRAG retrieval cascade.** Stage 4.
- **Verifier changes.** Stage 5.
- **Multi-target schema.** Stage 6.
- **Pattern detection.** Optimization pass, deferred.
- **LLM-authored synthesis through markup.** Stage 4.

---

## Risks + mitigations

| Risk | Probability | Mitigation |
|---|---|---|
| KDL grammar can't express some IR field (e.g. nested visual arrays) | Medium | Design grammar to have an escape-hatch `$extensions` bucket (DTCG pattern). Unknown/new IR fields land there; spec-compliant parsers preserve. |
| Parser performance issues on large screens (iPad Pro, 400+ nodes) | Low | Hand-written recursive-descent is linear; tree-sitter is incremental. Measure early. Budget 100ms. |
| Byte-for-byte round-trip impossible due to whitespace / ordering | High — accept | Test structural equality, not byte equality. `parse(emit(ir)) == ir` is the real invariant. |
| 204/204 parity breaks because of subtle IR field extension | Medium | Markup module is additive; IR shape unchanged in MVP. If extension needed, explicit flag + documented migration. |
| LLM-constrained-decoding format doesn't match KDL grammar exactly | Low | Smoke test in week 2 catches this. If misalignment, simplify grammar or pick different constrained-decoding library. |
| Pattern of 20 screens under-represents full 204 screens' edge cases | Medium | Stretch goal runs all 204 — use that as the real validation before claiming "done." |
| Hand-authored golden file for screen 1 diverges from auto-emitted | High (first time) | Iterate: hand-author based on what the emitter produces. The hand-authored version is the spec, the emitter is the implementation. |

---

## Post-MVP roadmap

After MVP success, the architecture doc §8 lays out Stages 2–6. Rough ordering by dependency:

- **Stage 2 (definitions + references, ~1 week)**: `define` / `use` / `&` grammar; expansion; cycle detection.
- **Stage 3 (synthetic tokens, ~3 days)**: ΔE color clustering, dimension histograms, type scale nearest-step. Unlocks cold-start synthesis.
- **Stage 4 (edit grammar + CRAG cascade, ~2 weeks)**: Edit verbs; CRAG τ thresholds; three-mode cascade wired into synthesis.
- **Stage 5 (verifier-as-agent, ~1 week)**: Gate ladder; pairwise VLM; agentic critic emits edits in the same grammar.
- **Stage 6 (multi-target schema, optional, ~1 week)**: `targets` column, `token_platforms` table, React renderer stub.

Each stage has its own success gate and ships independently behind a flag.

---

## Why MVP is specifically round-trip, not synthesis

Synthesis is the customer-facing feature; round-trip is the architecturally load-bearing proof. Three reasons MVP is round-trip:

1. **Round-trip is verifiable by a deterministic, existing test** (the 204/204 sweep). Synthesis requires a VLM, which is noisy and subject to quota.
2. **Round-trip forces the grammar to be complete.** Synthesis can work with an incomplete grammar because the LLM will just not emit what the grammar can't express. Round-trip fails loudly if the grammar is missing anything the IR needs.
3. **If round-trip works, synthesis is "just" the generator producing what the grammar can express.** The MVP validates the constraint; synthesis work later is about pipeline efficiency and VLM quality, not about whether the substrate works.

In practical terms: v0.1.5 shipped synthesis to 12/12 VLM-ok without the grammar. The grammar's benefit is structural cleanness, LLM reliability via constrained decoding, and unified authoring surface — all of which only matter if the grammar can represent what the system currently represents, losslessly.

MVP proves that, or it doesn't.

---

## One more note: this isn't a rewrite

v0.3 is additive. Every stage ships behind a flag. The existing v0.1.5 / v0.2 machinery runs unchanged until we flip the flag. `render_batch/sweep.py` passes 204/204 throughout MVP and all subsequent stages. If a stage breaks parity, that stage is halted, not shipped.

The fallback guarantee: **at any point during v0.3 development, `DD_ENABLE_MARKUP=0` (and other feature flags) returns the system to the v0.2 behavior exactly.** Nothing in the v0.3 architecture requires deleting v0.1.5/v0.2 code. Only adding.

---

*Canonical architecture: `docs/architecture-v0.3.md`. Research provenance: `docs/research/v0.3-architecture-research.md`. All guardrails from ADR-001 through ADR-008 remain in force.*
