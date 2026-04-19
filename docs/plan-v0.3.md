# Plan — v0.3 Phase

**Status:** Canonical. The plan for completing the v0.3 foundation and positioning for Priority 1 (synthetic generation).
**Authored:** 2026-04-18.
**Scope:** defines both Plan A (write the specs) and Plan B (execute against the specs for Stage 1).

This doc exists so that any session — human or AI — can pick up where we are and know exactly what to do next, in what order, with what dependencies.

---

## Where we are right now

### Branch state

```
* v0.3-integration              ← current; Option A complete, pivoting to Option B
  v0.3-dd-markup-probe          ← preserved (original Priority 0 probe source)
  v0.3-stage-a-crag-scaffold    ← preserved but NOT merged (premature CRAG A+B)
  v0.3-stage-c-synthesis        ← preserved but NOT merged (premature CRAG C)
  v0.3-stage-d-composition      ← preserved but NOT merged (premature CRAG D)
  main                          ← 204/204 parity anchor (pre-markup state, tagged)
```

**Rollback tags** (applied 2026-04-18):
- `pre-markup-baseline` — main's HEAD; clean dict-IR 204/204 state (used for Anthropic interview share).
- `markup-compressor-mvp` — `c0102d5` on v0.3-integration; compressor MVP green, no decompressor.
- `option-a-complete` — v0.3-integration HEAD at the Option B pivot.
- `pre-revert/stages-a-d-2026-04-18` — pre-revert snapshot of CRAG A–D work (investigation-round archaeology).

Forward strategy: Option B migration proceeds on `v0.3-integration`. No new branch. Tags are the rollback points. At M6 cutover, v0.3-integration merges to main with `--no-ff` preserving the full history; tags survive the merge unchanged.

2,524 tests green on the full suite (target test surface: 163 across compressor + decompressor + markup + render pipeline + archetype). Tier 1 AST round-trip at 204/204. Tier 3 pixel parity currently 0/3 on the Option A markup-via-dict path (the finding that motivated the Option B pivot); Option B targets 204/204 at M4.

### What's on `v0.3-integration` today

**Completed and staying:**
- Grammar spec (`docs/spec-dd-markup-grammar.md`) and L0↔L3 spec (`docs/spec-l0-l3-relationship.md`) — Plan A output, closed all 20 open questions.
- `dd/markup_l3.py` — full grammar parser + emitter + AST + semantic passes. Backbone of Option B.
- `dd/compress_l3.py` — per-axis DB → L3 AST derivation. Renamed to `derive_markup` at M0, logic unchanged.
- `dd/archetype_library/*.dd` — 12 archetypes migrated from JSON, parse + round-trip clean.
- `tests/fixtures/markup/*.dd` — 3 reference-screen fixtures.
- `tests/test_markup_l3.py`, `tests/test_compress_l3.py`, `tests/test_archetype_skeletons.py` — all retained.
- Three rollback tags: `pre-markup-baseline`, `markup-compressor-mvp`, `option-a-complete`.

**Built for Option A, deleted at M6 per `docs/DEPRECATION.md`:**
- `dd/decompress_l3.py` — ~1100 LOC, 77 tests.
- `tests/test_decompress_l3.py`, `tests/test_markup_render_pipeline.py`.
- `$ext.nid` compile-time side-channel.
- `--via-markup` CLI flag (becomes default after cutover).
- `generate_ir` / `generate_figma_script` / `generate_screen` — replaced by `derive_markup` / `render_figma`.

**Legacy state removed pre-session:**
- `dd/markup.py` (original mechanical dict-IR serializer, pre-grammar-spec) was deleted during Plan A. Its Tier 2 harness pattern (`tests/test_script_parity.py`) survives as a reference for the migration-window A/B harness; itself deleted at M6.

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

**Purpose:** ship the dd markup grammar + parser + emitter + markup-native Figma renderer at 204/204 pixel parity.
**Migration model (adopted 2026-04-18 late-late session):** Option B — markup is the canonical IR end-to-end; no dict-IR intermediate on the render path. See `docs/decisions/v0.3-option-b-cutover.md`.

**Original Plan B stage numbering** (Stage 1.1–1.7, dict-IR Option A model) has been superseded by the milestone breakdown below. Commits that landed under the old numbering preserved in git history with their original labels — see §"What was built under Option A" below for the reconciliation.

#### Milestones (Option B)

| # | Milestone | Status | Evidence |
|---|---|---|---|
| M0 | Markup compressor (DB → L3 AST): parser + emitter + `compress_to_l3` green at 204/204 Tier 1 | ✅ | `tests/test_compress_l3.py::test_full_corpus_tier1_round_trip` |
| **M1** | **Markup-native Figma renderer MVP** — `render_figma(doc, conn, nid_map) → JS` walker | ✅ `TestM1cLeafNodeByteParity` + `TestM1dPipelineHealth` green | Sub-milestones below |
| — M1a | Extend `compress_to_l3` to return `(L3Document, eid_to_nid_map)`; `compress_to_l3_with_maps` also returns `eid_to_spec_key_map` | ✅ `df5aaa0` | `TestCompressToL3WithNidMap` (19 tests) |
| — M1b | `render_figma_preamble(doc, conn, nid_map, fonts, db_visuals, ckr_built, uses_placeholder) → str` emits byte-identical preamble on 3 reference fixtures (181 / 222 / 237) | ✅ `df5aaa0` | `TestM1bPreambleByteParity` (7 tests) |
| — M1c | Full `render_figma(...)` walker on a minimal synthetic fixture: dispatch + intrinsic properties for frame/rectangle/text + Phase 2 appendChild chain + end-wrapper. Walk order is BFS (matching baseline). Unsupported types fall through to `createFrame()`. | ✅ this commit | `TestM1cLeafNodeByteParity` (2 tests) + `TestCompressToL3WithMaps` (3 tests) |
| — M1d | Full walker on real Dank fixtures: `_original_name` side-car, leaf-parent append guard, Phase 3 position/resize/constraints, Mode-1 createInstance with fallback chain, per-type fill/stroke/effect emission, override tree emission, layoutSizing. Transitional `_spec_elements` shim into baseline `_emit_visual` / `_emit_layout` / `_emit_text_props` — removed at M2/M6. Pipeline-health gate on 3 reference fixtures: no crash, script > 1000 bytes, structural landmarks present, script-size ratio ≥ 0.90 | ✅ this commit | `TestM1dPipelineHealth` (9 tests); ratio 0.938–0.940 |
| M2 | Script byte-parity with the pre-markup renderer on 3 reference fixtures (181 / 222 / 237) | 🟡 in progress — M2a–d landed | Ratio 0.919–0.935 post M2a–d; byte-parity not yet; M2e+ remaining |
| — M2a | Variable numbering: match baseline's gappy `n{idx}` counter | ✅ `b5bdb58` | |
| — M2b | `_emit_override_tree` reuses preamble-prefetched `_pN` vars instead of inline `await getNodeByIdAsync` | ✅ `31ab5c6` | |
| — M2c | Mode 1 post-create props: `props.text` / `props.subtitle` / `rotation` / `opacity` / `visible=false` + `degraded_to_mode2` __errors push | ✅ `ba17646` | |
| — M2d | Promote `nodes.corner_radius` into `element.visual` before `_emit_visual` shim | ✅ `27f81bf` | Most Dank nodes are Mode 1 (cornerRadius from master), so ratio unchanged; Mode 2 gap closed |
| — M2e | `nodes.stroke_weight` DB fallback, `figma.group()` deferred creation, deferred `relativeTransform`, OpenType unicode substitution, `text_autoresize_deferred` Phase 2 emission | 🔲 | The remaining known gap list; each lands as its own sub-commit |
| M3 | Script byte-parity on full 204 corpus | 🔲 | `tests/test_script_parity_option_b.py` (new) |
| M4 | Pixel-parity via Figma sweep on full 204 corpus | 🔲 | `render_batch/sweep.py` on markup-native path reports 204/204 `is_parity=True` |
| M5 | Upstream consumer migration — `dd/compose.py`, providers, verifier consume `L3Document` | 🔲 | — |
| M6 | Atomic cutover PR — switch production to markup-native path; delete Option A code per `DEPRECATION.md` | 🔲 | Single commit; 204/204 on markup path required to land |
| M7+ | Stage 2 continuation (pattern expansion, `use`/import, cycle detection), Stage 3 (synthetic tokens), Stages 4–5 (synthetic generation) | 🔲 | Gated on M6 |

Commit prefix: `feat(option-b): Mk — <scope>` (e.g. `feat(option-b): M1b — preamble byte-parity on 3 fixtures`, `feat(option-b): M2 — render_figma byte-parity on screen 181`).

**Why M1 is split into 4 sub-milestones.** The pre-M1 research round (2026-04-18, evening) established that Option A never achieved byte-parity even at the preamble level — a font (`Inter Variable Regular`) was dropped across the AST round-trip on screen 181. So "byte-parity on screen 181" is a strictly tighter gate than what Option A hit (which was ratio 0.95–1.05 script-size and 0/3 at Tier 3 pixel parity). Breaking M1 into preamble → leaf nodes → full walker → ratio-parity gives four cheap, reversible A/B gates instead of one 2–3 week monolithic step. Each sub-milestone is individually commit-able; failure at M1b surfaces a bug in 1 day, not 14.

**Parity-protection during migration:** the Option A machinery (`dd/decompress_l3.py`, `ast_to_dict_ir`, `generate_figma_script`) stays operational in CI through M5. Both paths run per-commit; an A/B harness asserts byte-identical Figma script output on every screen. The M6 cutover PR is the one-shot deletion of Option A code.

**Rollback tags** (applied 2026-04-18):
- `pre-markup-baseline` — `main` HEAD. Clean dict-IR 204/204 before markup work.
- `markup-compressor-mvp` — `c0102d5`. Compressor MVP green; no decompressor yet.
- `option-a-complete` — `v0.3-integration` HEAD at the Option B pivot. Archaeology of the full Option A elaboration.

#### Stage 1 success criteria (Option B)

- All 3 fixture screens (181, 222, 237) pixel-parity through the markup-native path.
- Full 204 corpus reports 204/204 `is_parity=True` on `render_batch/sweep.py` after M6 cutover.
- AST-level round-trip `parse(emit(derive_markup(conn, sid))) == derive_markup(conn, sid)` holds on all 204 screens.
- Stage 2 onwards built on markup-native infrastructure (no Option A dependencies).

#### What was built under Option A (2026-04-18 session, before the late-late pivot)

39 commits on `v0.3-integration` delivered the Option A elaboration:
parser + emitter + compressor (all reusable for Option B), plus
decompressor + render pipeline via dict-IR lowering (to be deleted at
M6). The work demonstrated that the grammar captures the full
information — Tier 1 AST round-trip holds at 204/204 — and surfaced
the architectural cost that justified the Option B pivot.

Tagged at `option-a-complete`. The commits stay in history.

Key Option A commits for archaeology / reusable pieces:

- **Parser + emitter** (`bd48d7e`..`4e14d9b`): `dd/markup_l3.py`, full grammar coverage. **Preserved in Option B unchanged.**
- **Compressor Stage 1.4** (`b871c1b` + follow-ups through `06bed72`): `dd/compress_l3.py` per-axis derivation. **Reused at M0 as `derive_markup` core.**
- **Decompressor Stage 1.5a** (`68eb49b`..`2ceaa1c`): `dd/decompress_l3.py`, 77 tests. **Deleted at M6 per `DEPRECATION.md`.**
- **`$ext.nid` side-channel** (`5a5bcd9`): compile-time bridge for dict-IR identity. **Removed at M6 — renderer looks up DB on demand in Option B.**
- **Canonical-type classification** (`130288a`): applies sci classifications to spec types. **Concept reused in `derive_markup` at M0.**
- **Archetype migration** (`247f7b0`, `eaebc06`): 12 `.dd` files + fail-open parser. **Preserved in Option B.**
- **Render pipeline** (`b97bd3c`, `d89f96f`): `test_markup_render_pipeline.py`, `--via-markup` CLI flag, `generate_screen(via_markup=True)`. **Deleted at M6 — replaced by markup-native `render_figma`.**

The lessons preserved in `docs/decisions/v0.3-option-b-cutover.md` §2 (Evidence from the Option A attempt).

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
2. `docs/requirements-v0.3.md` — Tier 1, v0.3-specific scope (updated for Option B)
3. `docs/decisions/v0.3-option-b-cutover.md` — current architectural stance
4. **This doc** — plan and migration sequencing
5. `docs/DEPRECATION.md` — what gets deleted at M6 cutover
6. `docs/spec-l0-l3-relationship.md` — compression + expansion (expansion section rewritten for Option B)
7. `docs/spec-dd-markup-grammar.md` — grammar (unchanged by the pivot)
8. `memory/project_v0_3_plan.md` — session-boot summary

### Verify state

```bash
git checkout v0.3-integration
git status                                  # should be clean
git tag -l | grep -E "pre-markup|option-a|markup-compressor"  # 3 rollback tags present
pytest tests/test_compress_l3.py tests/test_markup_l3.py \
       tests/test_archetype_skeletons.py -q   # core markup infra: 160+ green
python3 render_batch/sweep.py --port <N>    # current state: 204/204 on pre-markup path (baseline)
```

### Kickoff — M1 (markup-native Figma renderer MVP)

**Next session starts at M1a.** Work the sub-milestone ladder in order; each is committable and reversible. Don't build the full walker on day one.

#### M1a — eid↔nid side-car

Extend `compress_to_l3(spec, conn, *, screen_id) → L3Document` to also return the `eid → db_node_id` mapping that `_compress_element` already computes internally from `spec["_node_id_map"]`. Preferred signature:

```python
def compress_to_l3(
    spec: dict, conn: Optional[sqlite3.Connection] = None,
    *, screen_id: Optional[int] = None,
) -> tuple[L3Document, dict[str, int]]:
    ...
```

Or a companion `derive_markup(conn, sid) → (doc, nid_map)` wrapper. The map is a side-car, NOT embedded in the grammar — that's the explicit difference from `$ext.nid` (which encoded the same information *inside* the markup and has been deprecated).

The map is what `render_figma` uses to resolve per-node DB lookups (`db_visuals[nid]`) without inventing a new identity scheme. Everything the renderer needs from the DB (fills, strokes, fonts, effects, vector paths, override trees, etc.) flows through this bridge.

Update `tests/test_compress_l3.py` to cover the new return shape. No parity claims yet.

#### M1b — preamble byte-parity

Add `dd/render_figma_ast.py` with a first function:

```python
def render_figma_preamble(
    doc: L3Document, conn: sqlite3.Connection, nid_map: dict[str, int],
) -> str:
    ...
```

It emits the preamble ONLY: font loads + `__errors` + `_rootPage` + prefetch. No Phase 1/2/3 yet.

A/B harness at `tests/test_option_b_parity.py`:

```python
def _preamble_region(script: str) -> str:
    """Extract the pre-Phase-1 prefix (everything up to the first
    `// Phase 1:` comment emitted by generate_figma_script)."""
    marker = "// Phase 1:"
    idx = script.find(marker)
    return script[:idx]

@pytest.mark.parametrize("sid", [181, 222, 237])
def test_m1b_preamble_byte_parity(db_conn, sid):
    ir = generate_ir(db_conn, sid, semantic=True, filter_chrome=False)
    visuals = query_screen_visuals(db_conn, sid)
    script_a, _ = generate_figma_script(ir["spec"], db_visuals=visuals, ckr_built=True)

    doc, nid_map = compress_to_l3(ir["spec"], db_conn, screen_id=sid)
    preamble_b = render_figma_preamble(doc, db_conn, nid_map)

    assert _preamble_region(script_a) == preamble_b
```

This gate catches font collection, prefetch target accuracy, and eid→nid map completeness in one shot. If it fails, the error is almost always one of: (a) `collect_fonts` walks text elements we haven't surfaced, (b) `nid_map` is missing entries for some nodes, (c) the sort order of the fonts set differs.

#### M1c — Phase 1 leaf-node byte-parity

Extend `render_figma_ast.py` with Phase 1 emit for `createFrame` / `createRectangle` / `createText` on a minimal synthetic fixture (one screen with one of each node type — no nesting, no instances). A/B harness asserts the full script is byte-identical for that fixture.

This sub-milestone catches the dispatch + intrinsic-property emission paths without the compounding complexity of instance resolution, group deferral, text re-layout, or constraints.

#### M1d — Full walker, pipeline-health gate

Full Phase 1/2/3 walker over `doc.top_level` on 3 reference fixtures (181, 222, 237). Gates are deliberately loose:
- No crash (no exceptions from the generated script or the renderer).
- Script > 1000 bytes (non-empty).
- `eid_map` produced by the walker has >= 1 entry per top-level node.
- Script-size ratio against baseline within 0.95–1.05 (Stage 1.5c-equivalent diagnostic, not an identity assertion).

This is the equivalent of `tests/test_markup_render_pipeline.py`'s existing gates but on the Option B path. Once M1d is green, we've proven the pipeline is healthy. Then M2 tightens to byte-identity.

#### What the verifier does with eids (why Option B auto-resolves Option A's 48 missing_child)

`dd/verify_figma.py` matches IR elements to rendered nodes via `rendered_ref["eid_map"][eid]`. The renderer builds `eid_map` in JS from `M[eid] = n0.id` assignments in Phase 1. The verifier never reads Figma `pluginData` — it reads the eid-keyed walk payload.

Option A's 48 `missing_child` errors on screen 181 were counter-drift between the baseline `generate_ir`'s element keys (`button-5`) and the decompressor's AST walk counter (`button-16`). Each walk produced different eids for the same physical node. In Option B, the compressor and renderer walk the same AST in the same deterministic order, so the eids are identical by construction. This class of failure does not exist in Option B — **do not carry forward workarounds designed for it**.

#### Feature coverage (M1d → M2), in order of render-critical priority

- Node creation (`createFrame` / `createRectangle` / `createText` / `createInstance` / `createVector`)
- Sizing + position (Phase 1 `resize`, Phase 3 `x/y`)
- Fills + strokes
- Text properties (font, size, weight, content)
- Component instances via `createInstance` (Mode 1 path) + missing-component placeholder
- Vector paths (from `conn` via `nid_map`)
- Effects (shadow, blur)
- Constraints
- Variant / swap handling

Each feature added = one more byte-parity screen moves to green.

### Principles for M1–M3 execution

- **Two paths in CI, every commit.** Pre-markup (Option A baseline) AND markup-native (Option B). Option A is the reference; Option B must byte-match.
- **Per-feature A/B harness.** When adding a feature (e.g. vector paths), there's a test that runs both paths on one screen exercising that feature, and asserts byte-identical script output. Every feature has its own parity gate.
- **Don't modify the Option A path.** The baseline IS the reference. Any change to `generate_figma_script` invalidates the A/B comparison.
- **Per-backend reference resolution.** When the Figma renderer resolves `{color.brand.primary}` via token catalog, document the lookup clearly — this is the pattern React/SwiftUI/Flutter renderers will follow at their respective stages.

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
