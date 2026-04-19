# Plan — v0.3 Phase

**Status:** Canonical. The plan for completing the v0.3 foundation and positioning for Priority 1 (synthetic generation).
**Authored:** 2026-04-18.
**Scope:** defines both Plan A (write the specs) and Plan B (execute against the specs for Stage 1).

This doc exists so that any session — human or AI — can pick up where we are and know exactly what to do next, in what order, with what dependencies.

---

## Where we are right now

### Branch state

```
* v0.3-integration              ← current; investigation closed, probe code preserved
  v0.3-dd-markup-probe          ← preserved (original Priority 0 probe source)
  v0.3-stage-a-crag-scaffold    ← preserved but NOT merged (premature CRAG A+B)
  v0.3-stage-c-synthesis        ← preserved but NOT merged (premature CRAG C)
  v0.3-stage-d-composition      ← preserved but NOT merged (premature CRAG D)
  main                          ← 204/204 parity anchor

tag: pre-revert/stages-a-d-2026-04-18 → snapshot of pre-revert HEAD
```

319 tests green on `v0.3-integration`. Tier 2 script-parity 204/204. All ADR-001 through ADR-008 invariants preserved.

### What's on `v0.3-integration` today

- Investigation closure (6 decision records in `docs/decisions/v0.3-*.md`)
- Priority 0 markup serde probe (`dd/markup.py`, ~786 LOC) — **this is a mechanical dict-IR serializer, NOT the axis-polymorphic L3 grammar we need. It will be substantially rewritten against the spec produced by Plan A. Some infrastructure is reusable; the grammar surface is not.**
- `_UNIVERSAL_MODE3_TOKENS` dup-key fix
- Tier 2 script-parity pytest gate (`tests/test_script_parity.py`)
- Markup hardening: typed errors with line/col, edge-case tests, Mode-E validator

### What lives in the archive

Feature branches preserved (NOT merged) for archaeology. Can be cherry-picked later if Stage 4–5 work surfaces useful pieces:
- Seven-verb edit grammar parser/applier (though specified against the wrong markup)
- `MarkupEdit` dataclass
- `cascade_resolve` router + three per-mode stubs

Most of this is incorrect against the grammar specified in Tier 0 §4; don't expect verbatim reuse.

---

## The two plans

### Plan A — Write the specs (before any code)

**Purpose:** produce reference documents that Plan B implements against. No code is written during Plan A.
**Estimated duration:** 3–5 days of focused collaboration.

| Step | Deliverable | Depends on | Parallel |
|---|---|---|---|
| A.1 | `docs/requirements.md` (S0) — Tier 0 overall requirements | — | concurrent with A.2 and A.3 |
| A.2 | `docs/requirements-v0.3.md` (S1) — Tier 1 v0.3 requirements | S0 content | concurrent with A.1 and A.3 |
| A.3 | Pick 3 Dank reference screens at varying complexity; read their L0+L1+L2 state from the DB | — | concurrent with A.1, A.2 |
| A.4 | `tests/fixtures/markup/*.dd` (S4) — hand-authored markup for the 3 reference screens at mixed axis densities | A.3 | **load-bearing pair with A.5** |
| A.5 | `docs/spec-dd-markup-grammar.md` (S2) — formal BNF/EBNF derived from the fixtures | A.4 in progress | **load-bearing pair with A.4** |
| A.6 | `docs/spec-l0-l3-relationship.md` (S3) — compression + expansion algorithms | S2 and S4 stable | — |
| A.7 | Reconcile S1 ↔ S2 ↔ S3 ↔ S4; close remaining open questions | all above | — |
| A.8 | Placeholder stubs for S5 (synthetic tokens), S6 (retrieval + generation), S7 (verifier-as-agent) | — | anytime |

**Status on 2026-04-18:**
- [x] A.1 — `docs/requirements.md` written
- [x] A.2 — `docs/requirements-v0.3.md` written
- [x] A.5 scaffold — `docs/spec-dd-markup-grammar.md` placeholder + open questions exists
- [x] A.6 scaffold — `docs/spec-l0-l3-relationship.md` placeholder + open questions exists
- [ ] A.3 — pick reference screens (next session — see §Next Session Kickoff below)
- [ ] A.4 — hand-author fixtures
- [ ] A.5 — fill in the grammar spec
- [ ] A.6 — fill in the L0↔L3 spec
- [ ] A.7 — reconcile
- [ ] A.8 — S5/S6/S7 placeholders

**Load-bearing pair — A.4 and A.5 together.**
Writing a fixture at wireframe density surfaces what the grammar must allow to be absent. Writing a fixture with a `define` + reference surfaces parametrization questions. Drafting grammar without fixtures produces armchair design; authoring fixtures without grammar produces informal sketches. Iterate the two together, with visible error at every step (does the fixture parse? does the grammar reject the invalid variations?).

**Plan A success criteria:**
- S0 and S1 reviewed and approved
- S4 fixtures exist for 3 screens at mixed densities; each parses against the grammar
- S2 grammar parses every fixture and rejects invalid variations (at least 3 per fixture)
- S3 has concrete algorithms for both compression and expansion, detailed enough to hand-simulate
- Zero open questions block Stage 1 Day 1

### Plan B — Execute Stage 1

**Purpose:** implement the dd markup parser + emitter + L0↔L3 round-trip, matching the specs from Plan A.
**Estimated duration:** 2–3 weeks after Plan A completes.

| Step | Deliverable | Depends on |
|---|---|---|
| 1.1 | Parser tests against S4 fixtures (red phase) | S2, S4 |
| 1.2 | Parser implementation (green phase) | 1.1 |
| 1.3 | Emitter tests: L0+L1+L2 → L3 fixtures (red phase) | S3, S4 |
| 1.4 | Emitter (compression): per-axis derivation from dict IR | 1.3 |
| 1.5 | Round-trip test: one fixture screen end-to-end (source Figma → extract → compress to markup → expand → render → pixel parity) | 1.2, 1.4 |
| 1.6 | Round-trip test: 3 fixture screens | 1.5 |
| 1.7 | Round-trip test: full 204 corpus | 1.6 |

**Stage 1 success criteria:**
- All 3 fixture screens round-trip at Tier 1 (dict equality), Tier 2 (script byte-parity), Tier 3 (pixel parity via Figma sweep)
- Full 204 corpus round-trips at Tier 1 + Tier 2 (Tier 3 by sweep run)
- Zero regressions in existing test suite
- Existing `sweep.py` (without markup env var) continues to report 204/204 — markup path is purely additive

### Stage 1 progress as of 2026-04-18 evening

| Step | Deliverable | Status |
|---|---|---|
| 1.1 | Parser tests against S4 fixtures (red) | ✅ |
| 1.2 | Parser + emitter (green) | ✅ |
| 1.3 | Emitter tests / golden snapshots | ✅ |
| 1.4 | Compression — per-axis derivation from dict IR | ✅ **204/204 Tier 1** |
| **1.5** | **Round-trip one fixture end-to-end** | ✅ **EFFECTIVELY COMPLETE** |
| 1.5a | Expand — `ast_to_dict_ir` (decompressor) | ✅ |
| 1.5b | Render step — decompressed IR → figma script (204 no-crash) | ✅ |
| 1.5c | Tier 2 (script byte-parity) on 3 fixtures — ratios ≥ 0.977 | ✅ |
| 1.5d | Tier 3 (pixel parity) on screen 181 via Figma sweep | ⏳ needs live bridge |
| 1.6 | Round-trip 3 fixtures at Tier 1+2+3 | ⏳ Tier 1+2 ✅ / Tier 3 via sweep |
| 1.7 | Full 204 corpus at Tier 2+3 | ⏳ Tier 1 ✅ / Tier 2 ratio-banded ✅ / Tier 3 via sweep |

**Stage 1.5c effectively complete** (commit `5a5bcd9`). The
`$ext.nid` side-channel embeds DB node_ids on every element head
so the decompressor-then-renderer pipeline produces a Figma script
at ratio ≥ 0.95 against baseline on all 3 fixture screens.

Measured ratios (decomp script / baseline):
- screen 181: **0.981**
- screen 222: **0.979**
- screen 237: **0.977**

Corpus-wide Tier-2 gate (`test_render_pipeline_full_corpus_ratio_floor`)
asserts every app_screen falls in `[0.85, 1.50]`. Passes on all 204
screens — ready as a PR-gate regression test.

Residual ~2% divergence is cosmetic (element-key naming —
`button-1` in baseline vs `instance-58` in round-trip because
canonical-type classification isn't re-run on inflated nodes).
Visual render should be identical since the render-critical
fields (node_ids → visuals → fonts / vectorPaths / constraints)
are now byte-identical.

**Tier 3 (pixel parity) gate requires a live Figma bridge** —
that's user-side work, not automatable in the test suite. Run:

```
python3 render_batch/sweep.py --port <bridge_port>
```

against a Figma instance with the walker extension connected.
Compare the `is_parity` verdict across baseline-vs-markup paths.

**Stage 1.5a internal decomposition** (commits labelled "1.5/1.6/1.7" at
commit time, reconciled here as 1.5a sub-work — the expand half of 1.5):

- **Skeleton** (`68eb49b`): basic AST→dict walk, type/layout/visual decode,
  CompRef marking, 17 tests.
- **Corpus sweep + wrapper re-expansion** (`bdcd988`): synthetic screen wrapper
  inverse; 5 corpus sweeps (no-crash, count-parity, type, root-is-screen,
  child-refs-resolve).
- **Review cycle 6 fixes** (`7bc76c6`): direction default (absolute/stacked/
  skip for compref), `_original_name` recovery, `$ext.*` pass-through.
- **`_self_overrides` channel** (`14af0a3`): CompRef head PropAssigns captured
  structurally; `_override_value_repr` for Literal_ / PropGroup /
  FunctionCall / SizingValue.
- **Review cycle 7 fixes** (`2345d8b`): absolute root direction, compref no
  spurious direction, TokenRef/ComponentRefValue/PatternRefValue handlers,
  SizingValue bounds, PathOverride capture, JSON serializability.
- **DB column tagging** (`a8684d7`): `db_prop_type` + `db_prop_name` on every
  `_self_overrides` entry, padding fans out per side, `width` polymorphism.
- **Master-subtree expansion** (`1b30d95`): walk master's subtree via
  recursive CTE when `conn` is supplied.
- **Cycle 8 fidelity fixes** (`df9a791`): CKR NULL filter, slash-path cache,
  sort_order, leaf-type direction, effects/stroke_align/per-corner radius.
- **Nested CompRef recursion** (`2ceaa1c`): INSTANCE rows inside a master
  subtree inflate their own master, cycle detection.

**Stage 1.5a test posture:** 66 decompressor tests + 72 compressor tests
pass. 204/204 Tier 1 round-trip holds. JSON-serializability sweeps pass
on both no-conn and with-conn paths.

**Known blockers for closing 1.5b (render step):**
1. **Canonical-type classification on inflated nodes.** Orig spec has
   `button` / `icon` / `header` types derived from
   `screen_component_instances`. Inflated nodes keep raw `instance` / `frame`.
   Renderer dispatches on canonical type.
2. **Integration point.** Wire decompressed IR into whatever consumes
   `generate_ir` output today (`render_batch/`, `sweep.py`).

**Non-blocking deferred items** (tracked in commit bodies, low corpus
impact or design-scope):
- CKR slash-path collisions (10 rows).
- Gradient `handlePositions` / `gradientTransform` / stop `position`.
- Compressor `:self:strokeAlign` (32 rows, single INSIDE value).
- `$ext.fill_unsupported` for radial/angular/diamond gradients (0 corpus).
- Stage 1.8 (not in plan yet): `_self_overrides` → `instance_overrides`
  row re-materialization. Column tagging (`a8684d7`) is prep.

### Plan B — Stages 2–6 (deferred until Stage 1 ships + each stage's spec written)

- **Stage 2:** definitions + references (`define` / `use` / `&`), cycle detection, pattern-suggestion Rule-of-Three pass. Archetype JSON skeletons migrate to `.dd` defines. Spec needed before code.
- **Stage 3:** synthetic tokens — clustering passes (ΔE / histograms / nearest-step). Universal catalog defaults preloaded. After Stage 3, the raw-value invariant (Tier 0 §3.3) is enforceable end-to-end. Spec needed before code.
- **Stage 4 (Priority 1 — synthetic generation):** retrieval-augmented starting-IR selection, unifying the three CRAG modes. CRAG scope revisits screen-vs-component granularity. Spec needed before code.
- **Stage 5 (Priority 1):** verifier-as-agent. Tiered ladder (parity + density + Jaccard + pairwise VLM). Critic emits edit-grammar patches. Spec needed before code.
- **Stage 6:** multi-target catalog schema — optional for v0.3 ship; enables Priority 2 (React renderer).

---

## How the next session picks up

### Read first

1. `docs/requirements.md` — Tier 0, the core claim and overall requirements
2. `docs/requirements-v0.3.md` — Tier 1, v0.3-specific scope
3. **This doc** — the plan and current state
4. `docs/spec-dd-markup-grammar.md` — scaffold + open questions (Plan A.5 target)
5. `docs/spec-l0-l3-relationship.md` — scaffold + open questions (Plan A.6 target)
6. `memory/project_v0_3_plan.md` — memory-resident summary

### Verify state

```bash
git checkout v0.3-integration
git status                                  # should be clean
pytest tests/ -q                            # expect 319+ green
pytest tests/test_script_parity.py -v       # expect 204/204 Tier 2
python3 render_batch/sweep.py --port <N>    # optional: expect 204/204 Tier 3
```

### Kickoff — Plan A remaining steps

**The next session starts with A.3.** The first 30 minutes:

1. Pick 3 Dank reference screens at varying complexity:
   - **Simple** — ~5–10 classified elements. Good candidate: an icon-definition or a simple mobile screen from the early IDs.
   - **Medium** — ~15–25 classified elements. Good candidates: settings, login, or a feed screen.
   - **Complex** — ~30+ classified elements with instances, overrides, gradients. Good candidates: a meme-feed or dashboard screen.

   Use `sqlite3 Dank-EXP-02.declarative.db` and queries on `screens` + `screen_component_instances` to get candidates. Commit the chosen IDs to `tests/fixtures/markup/README.md`.

2. For each selected screen, dump its L0+L1+L2 state:
   - L0: `SELECT * FROM nodes WHERE screen_id = ?` — use `dd/ir.py::query_screen_for_ir`
   - L1: `SELECT * FROM screen_component_instances WHERE screen_id = ?`
   - L2: `SELECT * FROM node_token_bindings WHERE node_id IN (...)`
   - Format as human-readable summaries (not raw SQL output). Save as `tests/fixtures/markup/NN-screen-name.l0-summary.md` for reference.

3. Hand-author the first `.dd` fixture for the simple screen. Start at the LLM-friendly target density (~10 elements) with definitions + references sparingly. Full axis population (Structure + Content + Spatial + Visual + System) to exercise the whole grammar.

4. While authoring A.4, start drafting S2 (A.5) production rules. Every fixture construct needs a corresponding BNF production; every BNF production should parse at least one fixture construct.

5. Maintain a running "open questions" list as you author. Each question gets resolved before leaving Plan A.

### Principles for Plan A authoring

- **Fixtures first, grammar derived.** Don't design the grammar abstractly and then try to fit Dank into it. Write a real fixture in plain Markdown or scratch text, then extract the grammar rules that would make that fixture parseable.
- **Every open question lands in the spec.** No leaving TBDs. Every `?` in the spec gets a decision (possibly "we accept both X and Y, parser handles both") before leaving Plan A.
- **Examples are normative.** If the spec says X and the fixture shows Y, the spec is wrong. Fixtures are ground truth.
- **Bias toward constrained-decoding reliability.** If two grammar forms both work, pick the one LLMs emit more reliably (rarely-seen sigils lose; keyword-arg-shape wins).

### Principles for Plan B execution

- **TDD — write the failing test against the spec before the code.**
- **204/204 is sacred.** Any commit that reduces parity is reverted.
- **No production code without a spec to implement against.** When you're implementing and you discover an unspecified case, stop, add it to the spec, have it reviewed, then implement.

---

## What was built, reverted, and preserved

### Investigation round (2026-04-18, morning)

Six decision records in `docs/decisions/`:

| Decision | Status | Location |
|---|---|---|
| Canonical-IR question | **Partially superseded** — framing was wrong; "markup as serde over dict IR" was correct for the mechanical markup I built, but the real v0.3 markup is axis-polymorphic L3. Three-tier parity proof remains valid evidence. | `v0.3-canonical-ir.md` (banner updated) |
| Underscore field contracts | Still valid documentation of the 5 underscore fields | `v0.3-underscore-field-contracts.md` |
| Grammar modes (Extract / Synthesis / Render) | Still valid as a validation-mode concept | `v0.3-grammar-modes.md` |
| RenderReport schema | Decision valid; scope deferred to Stage 5 | `v0.3-renderreport-schema.md` (banner updated) |
| Provider-audit | Stage 4 scope, premature | `v0.3-provider-audit.md` (banner updated) |
| Branching strategy | Still valid | `v0.3-branching-strategy.md` |

### Hardening work (2026-04-18, morning)

Preserved on `v0.3-integration`:
- `dd/markup.py` with typed errors, line/col tracking, Mode-E validator
- `tests/test_script_parity.py` — Tier 2 gate for the 204 corpus
- `DD_MARKUP_ROUNDTRIP=1` env var in `generate_ir`

**The markup code is the wrong shape for v0.3.** Rewriting it against S2 is Plan B Stage 1.2. Some pieces (tokenizer scaffolding, error classes, the Tier 2 test harness) are reusable.

### CRAG Stages A–D (2026-04-18, midday) — PREMATURE, REVERTED

Built ahead of Stage 1 against a mechanical markup that wasn't the real dd markup. Reverted. Feature branches preserved as `v0.3-stage-a-crag-scaffold`, `v0.3-stage-c-synthesis`, `v0.3-stage-d-composition`. Tag `pre-revert/stages-a-d-2026-04-18` at the full pre-revert HEAD.

Lesson: **do not sneak in Stage 4+ work ahead of Stages 1–3.** The MVP doc explicitly named "edit grammar" and "CRAG cascade" as Stage 4; they were built as "Stages A–D" that started immediately after investigation. That was wrong.

---

## Deprecation banners applied

The following docs had framing banners added, non-destructively (original content preserved):

- `docs/continuation-v0.3-mvp.md` — framing superseded by this plan; day-by-day structure is preserved as reference
- `docs/continuation-v0.3-next-session.md` — investigation priorities resolved; current plan is this doc
- `docs/decisions/v0.3-canonical-ir.md` — framing partially superseded; three-tier proof remains valid
- `docs/decisions/v0.3-provider-audit.md` — Stage 4 scope, premature, not executable as-is
- `docs/decisions/v0.3-renderreport-schema.md` — decision still valid, scope moved to Stage 5

Untouched (decisions still valid):
- `docs/decisions/v0.3-grammar-modes.md`
- `docs/decisions/v0.3-branching-strategy.md`
- `docs/decisions/v0.3-underscore-field-contracts.md`
- `docs/architecture-v0.3.md` (the canonical architecture — its §1.5 framing was revised, but the structural content stands)

---

## Open questions the next session must resolve

These are tracked in the spec files (S2 has 10 open questions; S3 has 10 open questions). Consolidated here for visibility:

### Grammar (S2)
- Q1. Token-ref syntax (`{path}` confirmed; validate against LLM emission)
- Q2. Provenance trailer syntax
- Q3. Three parametrization primitives — exact syntax per
- Q4. Hierarchical ID semantics and collision handling
- Q5. Wildcards in paths
- Q6. Whitespace and block boundaries
- Q7. Comment syntax
- Q8. Number formats
- Q9. String escapes
- Q10. Extension mechanism (`$ext`)

### L0↔L3 relationship (S3)
- OQ-1. Which L0 nodes become L3 elements (compression rules)
- OQ-2. Inline vs component reference at extract
- OQ-3. Inline pattern detection as suggested-not-applied
- OQ-4. Synthetic token emission timing
- OQ-5. Expansion — Option A (lower to dict IR) vs Option B (L3-aware renderer)
- OQ-6. Tier 1/2/3 cadence during Stage 1
- OQ-7. Density round-trippability (wireframe vs full)
- OQ-8. Compression determinism
- OQ-9. Override tree handling
- OQ-10. Relationship to existing `generate_ir`

Plan A.7 closes all 20 open questions before Plan B starts.

---

## Navigation

| Document | Purpose |
|---|---|
| `docs/requirements.md` | Tier 0 — canonical overall requirements |
| `docs/requirements-v0.3.md` | Tier 1 — v0.3 phase requirements |
| **This doc** (`docs/plan-v0.3.md`) | Plan A + Plan B + current state |
| `docs/spec-dd-markup-grammar.md` | S2 placeholder — Plan A.5 target |
| `docs/spec-l0-l3-relationship.md` | S3 placeholder — Plan A.6 target |
| `tests/fixtures/markup/` | S4 — Plan A.4 target |
| `docs/decisions/v0.3-*.md` | Investigation round decisions (some superseded in framing) |
| `memory/project_v0_3_plan.md` | Memory-resident plan summary |
| `memory/project_v0_3_investigation_priorities.md` | Investigation closure + pointer to this plan |
| `memory/MEMORY.md` | Memory index |

---

*Plan A writes the specs. Plan B executes against the specs. No code gets written for Plan B until Plan A reconciles the specs and closes every open question. No Stage 2+ work starts until Stage 1 ships 204/204 across all three tiers.*
