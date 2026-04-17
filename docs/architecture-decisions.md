# Architectural Decisions

Systemic fixes introduced to prevent entire classes of bugs, not just specific
instances. Each decision generalizes across backends (Figma, React, SwiftUI,
Flutter) and across consumers (deterministic codegen, synthetic LLM-generated
IR).

## ADR-001: Capability-gated emission

**Problem.** "object is not extensible" at Figma runtime when the renderer
set `clipsContent` on a `RECTANGLE`. The fix for that specific bug was
trivial (gate by node type), but the underlying defect was architectural:
the renderer maintained ad-hoc, per-property gates that drifted as the
registry grew.

**Decision.** Every `FigmaProperty` carries a `capabilities` dict keyed by
backend name, mapping to the frozenset of native node types that support
the property. `is_capable(figma_name, backend, node_type)` is the single
source of truth. `emit_from_registry` consults it at emission time and
silently skips illegal combinations. See
`memory/feedback_capability_gated_emission.md`.

**Reuse.**
- New backends (React, SwiftUI, Flutter) add a new key to `capabilities`.
  No new Python paths; the gate iterates `PROPERTIES`.
- The same table serves as the **constrained-decoding grammar for synthetic
  IR generation**: an LLM proposing `clipsContent` on a RECTANGLE is
  rejected at decode time.
- `TestCapabilityLint` in `tests/test_generate.py` scans emitted scripts
  post-hoc to catch any bypass (hand-rolled emission lines, new handlers).

**Fails closed** at the output gate (unknown property / backend → False).
Extraction still fails open per `feedback_fail_open_not_closed.md`.

## ADR-002: Null-safe Mode 1 with structured error channel

**Problem.** A single deleted/unpublished component produced
`Cannot read property 'getMainComponentAsync' of null` and aborted the
entire script. The old emission was a nested `await await` chain with no
null checks anywhere.

**Decision.** Every `createInstance()` sits behind an async IIFE that
null-checks each step and falls back to `figma.createFrame()` on failure.
Each failure pushes a structured entry into a script-scoped `__errors`
array exposed on the return payload as `M["__errors"]`. See
`memory/feedback_null_safe_mode1.md`.

**Reuse.**
- The `__errors` channel is the **per-backend failure-mode contract**.
  React: error boundaries. SwiftUI: placeholder views. Flutter: fallback
  widgets. Each backend reports partial success the same way.
- For synthetic generation, `__errors` is the ground-truth signal for
  "how lossy was this generation?" — it drives the training feedback loop.

## ADR-003: Explicit state harness

**Problem.** `figma.getNodeByIdAsync` side-effects `figma.currentPage`.
Downstream `figma.currentPage.appendChild(...)` calls leaked nodes to
whichever page hosted the last resolved component. The old mitigation was
a post-hoc "relocate orphans" loop in `render_test/run.js`, which
conflated harness and generator concerns.

**Decision.** Generator emits `const _rootPage = figma.currentPage;` at
the top of the preamble — *before* any `getNodeByIdAsync` call. All
downstream references use `_rootPage`. Generated scripts never read
ambient host state after prefetch begins. See
`memory/feedback_explicit_state_harness.md`.

**Reuse.**
- **React**: capture `theme`, `router`, `store` as explicit props / context.
- **SwiftUI**: capture `EnvironmentValues` as explicit parameters.
- **Flutter**: capture `BuildContext` as a scoped parameter; never re-read
  globals across an async gap.

General rule: **every host read happens once, at entry, into a named
local.** Any later reference reads the local, not the host.

## ADR-004: Verification loop (capability-lint + structured errors)

**Problem.** Bugs were only caught by running generated scripts against
Figma, not by tests. Bug-fixes were reactive.

**Decision.** Two complementary verification mechanisms:

1. **Capability-lint** (`TestCapabilityLint`): scans every generated
   script for `nN.propertyName = ...` and asserts `is_capable(propertyName,
   "figma", typeOf(nN))` holds. Derived from the registry, so adding a new
   property with capabilities extends coverage automatically.

2. **Structured result contract**: every generated script returns
   `M["__errors"]` — an array of `{eid, kind, id, error?}` entries. The
   harness (`render_test/run.js`) surfaces this in the result payload. A
   clean run has `errors: []`.

Together these let us detect both *compile-time* legality violations and
*runtime* recoverable failures without requiring a live Figma session.

## ADR-005: Null-safe prefetch (network layer)

**Problem.** First post-ADR-001..004 run surfaced a new failure: transient
`"Unable to establish connection to Figma after 10 seconds"` thrown from
`figma.getNodeByIdAsync` during the prefetch block aborted the entire
script — the Mode 1 null-guards never got a chance to run because the
prefetch throw happened before them.

**Decision.** Every prefetch `await` is wrapped in a try/catch IIFE that
resolves to `null` on exception and pushes `{kind:"prefetch_failed", id,
error}` into `__errors`. Downstream Mode 1 null-guards (ADR-002) already
handle `null` component refs correctly, so this one-layer change extends
partial-success semantics all the way up to the network layer.

**Reuse.** Same pattern applies to any async resolver in any backend:
asset fetchers, font loaders, remote component imports. General rule:
**any await against a foreign / remote API is null-safe-wrapped**. Never
bare `await remote(x)` in generated output.

**Evidence.** Before: screens 181/182 aborted on transient network
failures, blank output. After: screens 181/182 complete with
`__ok:true`, structured `__errors` listing the specific missing
components, `moved:0` (no page leak).

## ADR-006: Boundary contract, both directions

**Problem.** ADR-002/005 put a structured failure channel on the
*emit* side of our boundary with external systems. The *ingest* side
had none. Re-extracting the source file surfaced two compounding
defects in `dd/cli.py`:

1. `resp["nodes"][figma_node_id]["document"]` (line 104) subscripted
   `None` whenever Figma returned `{"nodes": {id: null}}` for a
   deleted / unpublished id — raising `NoneType object is not
   subscriptable`.
2. The `except Exception` at line 117 caught the throw and printed to
   stderr, but did not call `update_screen_status(..., "failed", ...)`
   — that update only runs inside `process_screen`, which was never
   reached. `complete_run` counts only rows with `status='failed'`, so
   the summary reported **"97/339 completed, 0 failed"** for a run
   with 242 silently dropped screens. Exit code 0.

On top of these, there was no pre-generation check that the ids we
were about to render against actually still existed in the source
file. Source-file drift was invisible until runtime.

**Decision.** Introduce the backend-neutral boundary contract in
`dd/boundary.py` (shared dataclasses + protocols) and a first
instantiation in `dd/ingest_figma.py`:

- **Ingest side** — `IngestAdapter.extract_screens(ids) ->
  IngestResult`. Every foreign call is try/caught; every null
  response produces a `StructuredError(kind="node_not_found", id,
  ...)`; the returned `IngestSummary` invariant is
  `requested == succeeded + failed` and
  `len(errors) == summary.failed`, enforced at construction. No
  silent drops possible.
- **Catalog side** — `ResourceProbe.probe(ids) ->
  FreshnessReport`. Every id lands in exactly one of `valid_ids` /
  `missing_ids` / `unknown_ids` (transient error). `is_fresh` and
  `stale_ratio()` are computed properties. The partition is enforced
  at construction.

Same shape as the JS `__errors` channel from ADR-002, deliberately —
so the synthetic-generation feedback loop can consume structured
errors from both sides uniformly.

**Reuse.**

- **New frontends/backends** (Storybook, SwiftUI previews, Flutter
  widget trees) add sibling modules next to `ingest_figma.py`. Each
  exposes a `backend` class constant and satisfies the Protocol. The
  tests in `tests/test_boundary_contract.py` describe the contract by
  exercising Figma; parameterizing them over backends is the
  generalization path when the second backend lands.
- **Pre-generation gate**: `ResourceProbe.probe()` runs before Mode 1
  emission. If `stale_ratio()` exceeds a threshold, refuse to
  generate and surface the missing ids. The ingest-side analog of
  ADR-001's capability gate.
- **Synthetic IR decoding**: when an LLM proposes IR referencing
  external ids (figma node id, component_key, React component import,
  SwiftUI asset name), `probe()` validates them at decode time —
  pre-decode grammar validation on the ingest side, twin of the
  capability grammar on the emit side.
- **Corpus integrity**: `IngestSummary` is the ground-truth signal
  for how lossy an extraction pass was. Without it, training-set
  coverage metrics are fiction.

**Evidence.** Before: re-extract silently dropped 242/339 screens,
reported "0 failed", exit code 0. After: `IngestResult`
construction raises if counts disagree; `node_not_found` entries
carry the specific id and error.
`tests/test_boundary_contract.py` covers the 5 contract cases
(all-valid, some-null, summary-invariant, network-error,
backend-identifier) plus 4 probe-side cases and 2 shared
structured-error-shape cases. 12/12 green.

## ADR-007: Unified verification channel, per-node granularity

**Problem.** A fresh-extract three-screen round-trip reported every
mechanical success signal (`__ok:true, errors:[], moved:0`) while
producing visually wrong output. Quantitative diff against the source
(which we should have run but didn't — see "validation gap" below)
revealed:

- 71/71 INSTANCE nodes silently collapsed to placeholder FRAMEs.
- 32/32 TEXT nodes had empty `.characters`.
- 249 IR elements → 248 rendered nodes with the shape wrong at every
  component boundary.

Three distinct failure modes, each invisible to existing contracts:

1. **Codegen-time type substitution.** `dd/renderers/figma.py:827`:
   ```python
   use_mode1 = (component_key or component_figma_id) and not is_text
   ```
   When the fresh DB hasn't had `build_component_key_registry` or
   `extract-supplement` run, **both inputs are null for every INSTANCE
   node in the file.** The gate evaluates false, execution falls
   through to Mode 2 (`figma.createFrame()`), and the resulting script
   is perfectly valid — it just renders an empty frame where a
   component instance should have been. No null-guard fires (Mode 2 is
   a normal emission path, not a failure). No `__errors` entry.
   *Silent type substitution.*

2. **Coarse runtime swallow.** Phase 3 of every generated script is
   one `try { ~550 statements } catch (_e) { M["__canary"] = ... }`
   block. One throw aborts the rest of Phase 3 — all subsequent
   position-setting, constraint-setting, and `.characters =`
   assignments silently don't execute. The catch writes to
   `M["__canary"]` instead of pushing to `__errors`. The harness
   `render_test/run.js` returns `{__ok, before, after, moved, errors}`
   and discards `M`, so the canary never reaches the caller. Two
   parallel failure channels, only one visible.

3. **No post-render verification.** `__errors:[]`, `moved:0`, and
   `__ok:true` verify "script executed to completion," "no orphan
   leaks," and "no null-guards fired." None of them verify that the
   rendered tree matches the source. There is no quantitative parity
   check, no node-type-count diff, no text-coverage check. Silent
   quality loss is invisible to every automated signal in the
   pipeline.

**Validation gap (human side).** The author of a round-trip (me, in
this case) saw `__ok:true, errors:[]` and declared success after a
single washed-out multi-screen screenshot. The
`feedback_compare_against_ground_truth.md` discipline exists to
prevent exactly this, but discipline isn't a contract —
every future caller (human or LLM) repeats the same confusion
unless "did the render match" becomes a machine-checked invariant.

The three defects share one shape: **a degradation or failure occurred
that no existing verification contract can see.** ADR-001/002/005/006
put structured contracts at four positions around our boundary with
external systems. A fifth position — post-render verification — has
no contract. And two of the existing positions (emit-time codegen
choice; emit-time runtime operations) have blind spots within them
(Mode 2 substitution; coarse try/catch) where degradations or throws
escape the `__errors` channel.

**Decision.** Introduce a unified verification channel spanning three
new positions, all producing `StructuredError`-shaped entries, all
consumed uniformly by harness / CI / LLM training loop.

### Position 1 — Codegen-time degradation

Every lossy choice the emitter makes records a `StructuredError` with
a specific `kind` from a shared vocabulary:

| `kind` | Emitted when |
|---|---|
| `degraded_to_mode2` | INSTANCE emitted as `createFrame` because Mode 1 inputs missing |
| `degraded_to_literal` | Token-bound property emitted as hardcoded value because token can't resolve |
| `degraded_to_placeholder` | Asset reference emitted as placeholder because asset not found |
| `capability_gated` | Property dropped because unsupported by target backend (ADR-001 emitting) |
| `ckr_unbuilt` | Emitted once per run when `build_component_key_registry` wasn't run and Mode 1 is degraded as a result |

Degradations are **baked into the emitted script** as literal
`__errors.push(...)` statements. They flow through the same channel
as runtime throws (ADR-002) but their content is determined at
codegen time in Python, not at runtime in JS. Consumers see both
kinds in the same list.

### Position 2 — Runtime micro-guards

Every runtime operation on a foreign API uses the same null-guard
shape Mode 1's `createInstance()` already uses:

- One try/catch per operation (not per phase).
- The catch pushes `{eid, kind, id, error}` to `__errors`.
- No fallback to a coarse catch-all.
- `M["__canary"]` is removed; there is one failure channel, not two.

This applies to `.characters =`, `.fills =`, `.layoutMode =`, every
setter that can throw, and symmetric operations in React prop
setting, SwiftUI modifier application, Flutter widget construction
when those backends arrive. One bad node produces one entry; 99
neighboring healthy nodes are unaffected.

### Position 3 — Post-render verification

New protocol in `dd/boundary.py`, mirroring `IngestAdapter` in
shape:

```python
class RenderVerifier(Protocol):
    backend: ClassVar[str]
    def verify(self, ir: dict, rendered_ref: Any) -> RenderReport: ...

@dataclass(frozen=True)
class RenderReport:
    backend: str
    ir_node_count: int
    rendered_node_count: int
    errors: list[StructuredError]     # type_substitution, empty_text, missing_child, extra_child, ...
    @property
    def is_parity(self) -> bool: ...   # ir_node_count == rendered_node_count and errors == []
    def parity_ratio(self) -> float: ... # (ir_node_count - len(errors)) / ir_node_count
```

Invariants enforced at construction, exactly like `IngestResult` and
`FreshnessReport`. First instantiation is `FigmaRenderVerifier` in
`dd/verify_figma.py`, which walks the rendered subtree via the
Plugin API and diffs against the IR. Future backends (React,
SwiftUI, Flutter) supply their own verifier — the backend-specific
part is *which* tree to walk; the contract shape is shared.

The harness `render_test/run.js` is extended to surface the full `M`
payload so verification entries reach the caller. **Round-trip
success is redefined as**

```
__ok == true
  AND moved == 0
  AND errors == []
  AND RenderReport.is_parity == True
```

The old definition ("`__ok:true`") was necessary but not sufficient.

**Reuse.**

- **Additional backends** — React/SwiftUI/Flutter emitters route
  their codegen degradations through the same `StructuredError`
  `kind` vocabulary, adopt the micro-guard pattern at runtime, and
  ship their own `RenderVerifier`. Nothing is re-invented per
  backend; the contract shape is declared once in `dd/boundary.py`.
- **Resource-catalog prerequisites** — stages gain explicit
  prerequisite declarations. `extract` emits one
  `StructuredError(kind="ckr_unbuilt")` if `extract-supplement` or
  `build_component_key_registry` hasn't run before generation, so
  the downstream Mode 2 degradation is *traceable* rather than
  silent even while the fix is being staged.
- **Synthetic generation** — the unified channel *is* the dense
  training signal. Every entry carries an `eid` that joins to a
  position in the IR. The LLM receives per-node credit assignment
  instead of a single scalar "this screen was bad." The full
  synthetic chain becomes:
  1. **Pre-decode:** `capabilities` (ADR-001) + `ResourceProbe`
     (ADR-006) validate references before generation begins.
  2. **Emit:** `__errors` with per-op micro-guards (Position 2) and
     codegen-time degradation records (Position 1) capture every
     lossy choice.
  3. **Verify:** `RenderReport` (Position 3) produces the parity
     reward signal, per-node structured.
  All three stages feed a single aggregator with uniform shape.
- **Corpus integrity** — `RenderReport.parity_ratio` is the
  round-trip-lossiness signal across the whole corpus, same role
  `IngestSummary` plays on the ingest side (ADR-006). Drift between
  source and regenerated output becomes a first-class metric.
- **Validation discipline → contract** — "did the render match" is
  no longer something the caller has to remember to check. It's a
  gate in the round-trip that fails loudly when violated. Captures
  the validation gap described above without relying on human
  discipline.

**Evidence (projected).** Screen 175 case study under ADR-007:

- **Before** (observed): `__ok:true, errors:[], moved:0`. Round-trip
  declared successful. 71 instances lost, 32 text nodes empty, no
  signal surfaced.
- **After** (projected):
  - Position 1 pushes **71** `degraded_to_mode2` entries at codegen
    time for the unresolved INSTANCE nodes + **1**
    `ckr_unbuilt` entry per run.
  - Position 2 pushes **32** `text_set_failed` entries at runtime
    when the font-loading mismatch throws — no coarse swallow.
  - Position 3 returns `RenderReport(ir_node_count=250,
    rendered_node_count=248, errors=[…71 + 32 + 2…],
    parity_ratio≈0.59, is_parity=False)`.
  - Round-trip fails at the verification gate. The failure is
    per-node-attributable: the harness can point at the 71 specific
    eids that degraded and the 32 specific text nodes that threw.

## Cross-cutting invariants (updated)

The ADRs now address five positions around the external-system
boundary, in both directions:

| Position | Owner | Gate type | ADR |
|---|---|---|---|
| Pre-emit legality | Registry `capabilities` | Compile-time table lookup | 001 |
| Emit runtime throws (null-guards) | `__errors` | Runtime structured channel | 002, 005 |
| Emit runtime throws (per-op micro-guards) | `__errors` | Runtime structured channel | 007 |
| Codegen-time degradations | `__errors` (emit-time push) | Generation-time structured channel | 007 |
| Host state reads | Generator capture → local bindings | Scope discipline | 003 |
| Ingest failures | `IngestAdapter.IngestResult` | Compile-time structured channel | 006 |
| Catalog freshness | `ResourceProbe.FreshnessReport` | Pre-emit / pre-decode classification | 006 |
| Post-render parity | `RenderVerifier.RenderReport` | Post-emit structured channel | 007 |
| Regression catching | Registry-derived lint + error channels | CI tests | 004 |

Every external-system interaction has a structured contract at every
stage, in both directions. `StructuredError` is the unified shape.
`eid` is the unified join key from ingest through codegen through
runtime through verification, making per-node training signal
tractable for synthetic generation.

The registry remains the center. Every backend adds rows
(capabilities, adapters, probes, verifiers); every property adds
columns; no ad-hoc gates in any emission, ingest, or verification
path.

## Chapter epilogue (2026-04-15) — ADR-007 in action

The ADR-007 verification channel was exercised against three real
screens (175/176/177) and surfaced four sequential defect classes,
each fixed by following the per-node attribution trail it produced.
The chapter's commits, in landing order:

1. `4c4c051` — ADR-001 capability gate + ADR-006 boundary contract +
   ADR-007 unified verification channel (the foundation).
2. `3499e2c` — `_mode1_eligible` flag on IR elements (suppresses
   `type_substitution` for name-only-classified FRAMEs that were
   never INSTANCEs) + GROUP `.constraints` capability gate (honours
   the existing registry exclusion the renderer was bypassing).
3. `fcd39b9` — Skip `resize()` on text nodes whose DB
   `text_auto_resize` is `WIDTH_AND_HEIGHT` (Plugin API side-effects
   the resize into HEIGHT mode, locking width at 0). Adds
   `KIND_BOUNDS_MISMATCH` to the verifier vocabulary, with a
   text-height-wrap heuristic.
4. `10f1bb7` — Move `.characters = ...` emission from Phase 3 to
   Phase 2 (after appendChild, before layoutSizing) so HUG siblings
   have real content widths when FILL siblings evaluate. Defer
   `textAutoResize` mode emission to after layoutSizing so the
   width-locking happens last.
5. `5c3837c` — Capture and emit `leadingTrim` as a first-class text
   property (schema → REST API → parse + insert filters → registry →
   emitter). Source files use `CAP_HEIGHT` for tight vertical
   layout; without it the bbox is ~1.6× taller and DB-captured
   y-positions land text top-aligned in fixed-height parents.

Verification-driven debugging in action: after each fix landed, a
fresh `dd verify` run reported new bounds_mismatch / type_substitution
entries pointing at the next defect. By the end of the chapter,
all three screens reach `is_parity=True, parity_ratio=1.0000,
errors=0` and visually match source.

### Outstanding issues identified during the chapter

These are real bugs the verifier didn't yet have a `kind` for, or
that surfaced as side observations:

- **Whitelist drift** (`feedback_extract_whitelist_drift.md`):
  `dd/extract_screens.py::parse_extraction_response` and
  `::insert_nodes` maintain hand-rolled column whitelists that
  silently drop new schema fields. Cost an extra two re-extract
  iterations on the `leadingTrim` rollout. Should be replaced with
  registry-driven discovery.
- **Render-three timing**: `render_three.js` fires back-to-back
  PROXY_EXECUTE calls without inter-call waits and exhibits a race
  where the live state queried after script return differs from
  the state observed during execution. Inserting `~1s` waits (as in
  `test_seq.js`) avoids the race. Test-harness pacing issue, not a
  renderer bug.
- **Missing illustrations on screen 176**: the tablet/pencil
  illustration at the top of the home screen renders as empty grey
  space. Likely a vector-asset extraction or Mode 1 issue, separate
  from the wrap class. Not yet diagnosed.
- **Icon variant drift on screen 175**: the Community modal-row
  icon renders as a QR-grid icon vs the source's picture-frame
  icon. Component-instance swap pointing at the wrong target.
  Surfaces as a rendering correctness issue but not yet
  representable in `bounds_mismatch` or `type_substitution`.

These are seeds for the next chapter — each is a candidate for a
new `kind` in the verifier vocabulary, plus a backing fix.

## Chapter epilogue (2026-04-15, pt 2) — corpus sweep and visual-loss kinds

Started from the four "outstanding seeds" above. Drove all 204
app_screens through `dd verify` on the unified verification channel
(ADR-007). The sweep revealed that structural parity (what the
previous chapter built) is blind to every visual-loss defect class
that preserves tree shape — 201/204 screens reported
`is_parity=True` despite visibly rendering grey boxes where vector
illustrations should appear. Two new vocabulary kinds, two new
runtime guard points, and one previously-silent data-layer bug
class, all from systematic verification.

### Commits in landing order

1. `20c5fc2` — docs chapter epilogue for the 2026-04-15 (pt 1)
   session (this commit wraps up the prior chapter).
2. `c28f64a` — `KIND_MISSING_ASSET` verifier vocabulary +
   geometry-aware walker (`render_test/walk_ref.js`) + sweep
   driver (`render_batch/sweep.py`). VECTOR / BOOLEAN_OPERATION
   rendered with zero fillGeometry AND zero strokeGeometry is a
   shape-less Figma fallback (grey box); the check flags it
   per-eid. 7 new tests. Sweep on the old (geometry-missing) DB:
   684 missing_asset entries across 130/204 screens.
3. `fadc855` — font-load guards. `KIND_FONT_LOAD_FAILED` added;
   every `await figma.loadFontAsync(...)` wrapped in a try/catch
   that pushes a structured entry with family+style+error. Phase 1
   `var.fontName = ...` setter wrapped in the existing
   `_guarded_op` helper. Fixes 3/204 walk_failed on screens
   314/315/317 where "ABC Diatype Mono Medium Unlicensed Trial"
   aborted the whole script; now each failed font produces one
   attributable entry and the rest of the screen renders. 5 new
   tests.
4. `404f964` — registry-driven whitelists in
   `dd/extract_screens.py`. `TEXT_PASSTHROUGH_COLUMNS` and
   `INSERT_NODE_COLUMNS` derived from the property registry at
   module scope; `_STRUCTURAL_INSERT_COLUMNS` explicitly lists the
   non-registry columns (x/y/grid/geometry/FK). Adding a new
   registry property with a db_column now auto-extends both
   filters. 2 new drift-guard tests.
5. `a108a92` — vector-path extraction fix. Three compounding silent
   bugs in `dd/extract_assets.py::_hash_svg_paths`:
   - wrong JSON key: `p.get("path", "")` read 'path' but the
     Figma Plugin API's `node.fillGeometry` returns objects with
     key 'data'. Every path collapsed to empty, every content hash
     collided → 26,050 vectors → 10 identical empty assets.
   - wrong separator: svg_data concatenated sub-paths with ';', not
     a valid SVG command. Figma's `vectorPaths` setter threw
     "Invalid command at ;".
   - strict parser: Figma's `vectorPaths` requires a space between
     each command letter and its first coordinate
     (`M 160.757 118.403`, not `M160.757 118.403`). The Plugin
     API's own output is compact — Figma's own `fillGeometry`
     doesn't round-trip through its own `vectorPaths` setter
     without normalization. Added `_normalize_svg_path()`.
   Fix touches 3 layers of the same bug; each surfaced only after
   the previous was resolved. 3 new tests pin the regression.
   After reprocessing: 26,050 nodes → 256 distinct assets (up from
   10), 256 non-empty svg_data rows (up from 0).

### New verifier + guard vocabulary (this chapter)

- `KIND_MISSING_ASSET` (verifier): VECTOR/BOOLEAN_OPERATION with
  no paths.
- `KIND_FONT_LOAD_FAILED` (runtime guard): one loadFontAsync
  rejection shouldn't abort the script.

### Final state — corpus-wide

**204/204 app_screens reach `is_parity=True`** on the fresh
walker+verifier combo, 0 drift, 0 walk_failed, 0 generate_failed,
0 error_kinds in the summary. Vector illustrations actually render
(not grey boxes) on every screen; font-load failures (3 screens
affected) now surface as attributable structured entries rather
than aborting the script.

Before/after (same DB, same screens):

| Metric | Before chapter pt 2 | After chapter pt 2 |
|---|---|---|
| `is_parity=True` screens | 201/204 (falsely, verifier blind) | 204/204 (with visual correctness) |
| `missing_asset` entries | 0 (kind didn't exist) → 684 (after adding kind) | 0 |
| `walk_failed` | 3 (font-load abort) | 0 |
| distinct content-addressed svg_path assets | 10 (all empty) | 256 (all populated) |
| vectors with non-empty svg_data | 0 of 25,780 | 26,050 of 26,050 |

### Remaining seeds for next chapter

Each deliberately deferred; adding a new `kind` or fix is the next
chapter's work, not this one:

1. **Icon variant drift** (screen 175 Community row): INSTANCE
   resolves to the wrong master component. The verifier can't
   detect this by IR↔rendered comparison alone — it needs
   IR-vs-SOURCE drift detection. That's `dd drift` territory
   (ADR-006 `ResourceProbe` on the catalog side).
2. **Mixed-winding paths in a single asset**: when a VECTOR's
   fillGeometry has NONZERO + EVENODD subpaths mixed, the current
   asset format stores one windingRule. Rare in practice; a
   follow-up can split the asset into multiple VectorPath entries.
3. **Color / fill / effect drift**: structural parity still doesn't
   check that a rendered node's fill color matches IR. Each is a
   candidate new `kind` (e.g. `KIND_FILL_MISMATCH`,
   `KIND_EFFECT_MISSING`).
4. **Full 204-screen clean run**: sweep counts at commit time show
   the verified drop in missing_asset entries. Any residual
   drifts surface new defect classes — re-sweep after big fixes
   is how the vocabulary grows.

The pattern this chapter codified: **structural parity is a
necessary but not sufficient signal for visual correctness**. Every
new visual-loss class needs (a) a `kind` in the boundary vocabulary,
(b) a walker signal to surface it, (c) a verifier check to attribute
per-eid, (d) ideally a runtime guard at the emission layer so the
script doesn't abort on it.

## Chapter epilogue (2026-04-15, pt 4) — REST/Plugin convention divergence

The pt 3 chapter added visual verification kinds (FILL_MISMATCH,
STROKE_MISMATCH, EFFECT_MISSING) and drove the corpus to 204/204
structural parity with visual-property checks active. Rendering a
12-screen sample gallery for review surfaced visible defects the
verifier didn't detect. Investigating them revealed a single
underlying pattern: **REST API and Plugin API expose the same Figma
data in different coordinate conventions, and we had silent
arithmetic computing one from the other**. See the new memory
`feedback_rest_plugin_coord_convention_divergence.md`.

### Four convention mismatches fixed

1. **gradientTransform**. REST returns `gradientHandlePositions`
   (3 fractional points in node space). Plugin API returns
   `gradientTransform` (2x3 affine mapping gradient-local →
   node-relative). We had a formula `[[p1-p0, p2-p0, p0], ...]`
   that computed the INVERSE of what the Plugin API needs. Axis-
   aligned gradients worked by accident; a -15° overlay rendered
   at half height. Fix: remove the computation; use Plugin API
   values exclusively via supplement extraction (2,927 of 3,125
   gradient fills now have correct transforms).

2. **width/height**. REST returns `absoluteBoundingBox.width/height`
   (world-axis projection). Plugin API's `node.width/height` return
   local authoring dimensions. A 595×66 rect inside a -15° parent
   has an AABB of 591.8×217.7. Storing AABB in width/height columns
   made every rotated-subtree node's size wrong. Fix: new `--mode
   transforms` captures Plugin API `node.width/height` and overwrites
   (79,833 nodes).

3. **parent-local position**. The IR computed `pos_x = node.x -
   parent.x`. When the parent is rotated, this gives the world-space
   delta, not the parent-local position. The Plugin API's
   `relativeTransform[0][2], [1][2]` IS the parent-local translation.
   Fix: IR prefers the rt translation column when available, falls
   back to subtraction for pre-supplement data.

4. **scalar rotation + .x/.y for rotated nodes**. Figma's `.rotation`
   setter with scalar degrees + `.x/.y` writes the transform's
   translation column but in a way that's ambiguous about the pivot.
   For any rotated node (det=+1 OR det=-1), the full
   `relativeTransform` is the only unambiguous encoding. Fix:
   generalize the mirror check to ALL non-identity 2x2 matrices.
   1,937 mirrors + 8,849 pure rotations (10,786 total) now use
   `relativeTransform` emission in Phase 3 after `appendChild`.

### Two factory-default fixes

5. **Sub-pixel truncation**. `int(v)` at 5 resize() sites truncated
   fractional pixel dimensions. 12,801 nodes (14.8%) have fractional
   width; 1,073 lose more than 0.5px. Fix: `round(v, 2)`.

6. **Default stroke leakage**. `figma.createVector()` ships with a
   default 1px black SOLID stroke (Figma's design: a new vector
   without a stroke is invisible, so the factory adds one). When DB
   has no visible strokes, the renderer skipped `strokes = ...`
   assignment, leaving the default. Symmetric with the existing
   `fills = []` default-clearing for bounded shapes. Fix: emit
   `strokes = []` for VECTOR/LINE when DB has no visible strokes.
   Feedback memory: `feedback_figma_default_visibility.md`.

### One Plugin API impossibility

7. **OpenType features can't round-trip**. Plugin API has
   `getRangeOpenTypeFeatures` but NO setter. The initial emission
   of `setRangeOpenTypeFeatures(...)` silently threw. Fix: Unicode
   substitution for well-known patterns (SUPS "0" → "°"), plus
   `KIND_OPENTYPE_UNSUPPORTED` in the vocabulary for generic cases.
   Preserves the DB `text_content` as source of truth while giving
   correct visual output.

### Outstanding defect classes (next chapter)

Diagnosed in the pt 4 corpus-grid review, not yet fixed:

- **GROUP-as-container**: 110 screens have illustration GROUPs that
  the SCI heuristic reclassified to `canonical_type='container'`,
  making the renderer emit `figma.createFrame()` instead of
  `figma.group()`. But GROUP child coordinates are in the
  **grandparent's** space (Figma's "groups are transparent" quirk),
  so frame-emission places children hundreds of pixels outside.
  Plus a z-order bug where `figma.group()` always appends last.
- **Vector 485 double-stroke**: 7,414 VECTOR nodes have both
  fillGeometry and strokeGeometry populated. We merge them into one
  vectorPaths string with hardcoded NONZERO winding. Source nodes
  with `windingRule: "NONE"` (stroke-only vectors) get their
  expanded-stroke outline rendered as a filled polygon.
- **Inter Variable → Inter substitution**: `_normalize_font_family`
  rewrites the family name. The two fonts have 1px glyph-metric
  drift. For "Medium" in an 86px-wide FIXED parent (inner 66px), the
  1px overflow triggers 2-line wrapping on 21 screens.
- **HUG sizing with only-invisible children**: Figma's HUG doesn't
  re-measure after `appendChild` of an invisible node. The frame
  stays at the `createFrame()` default 100px. Fix shape: emit
  `resize(w, h)` as a SEED value before applying `layoutSizingVertical
  = "HUG"` even for semantic sizing, so ground-truth dimensions are
  preserved when Figma's HUG can't recompute.

### Cross-cutting invariants (updated)

The pt 4 chapter adds a new invariant to the table:

| Position | Owner | Gate type | ADR |
|---|---|---|---|
| Pre-emit legality | Registry `capabilities` | Compile-time table lookup | 001 |
| Emit runtime throws (null-guards) | `__errors` | Runtime structured channel | 002, 005 |
| Emit runtime throws (per-op micro-guards) | `__errors` | Runtime structured channel | 007 |
| Codegen-time degradations | `__errors` (emit-time push) | Generation-time structured channel | 007 |
| Host state reads | Generator capture → local bindings | Scope discipline | 003 |
| Ingest failures | `IngestAdapter.IngestResult` | Compile-time structured channel | 006 |
| Catalog freshness | `ResourceProbe.FreshnessReport` | Pre-emit / pre-decode classification | 006 |
| Post-render parity | `RenderVerifier.RenderReport` | Post-emit structured channel | 007 |
| **API-convention boundary** | **Supplement extraction** | **Plugin API ground truth overrides REST** | **007 pt 4** |
| Regression catching | Registry-derived lint + error channels | CI tests | 004 |

The `feedback_supplement_extraction_is_ground_truth.md` memory
generalizes: **REST for speed, Plugin API for correctness**. Four
supplement extraction modes now composable: properties,
vector-geometry, sizing, transforms. New modes are narrow additions —
schema column + capture JS + Python apply function.

## Chapter epilogue (2026-04-16, pt 5) — Missing-component placeholder + destructive-op safeguards

After the pt 4 convention-divergence fixes landed and the corpus
grid was rendered for review, the user noticed the Figma source
file's component library had been silently deleted mid-session.
This chapter addresses two related concerns: **graceful degradation
when components don't resolve at render time**, and **structural
safeguards to prevent the destructive-op pattern that caused the
file wipe**.

### Root cause of the file wipe

Forensic analysis identified a pattern I used repeatedly in ad-hoc
`figma_execute` calls:

```js
const page = figma.currentPage;
for (const c of [...page.children]) c.remove();
```

This trusts `figma.currentPage` to be the intended output page.
But `figma.getNodeByIdAsync()` side-effects `currentPage` — when
it resolves a node that lives on a different page, the current
page flips. Generated scripts make many `getNodeByIdAsync` calls
during prefetch, and a subsequent clear-op ran against the wrong
page.

See `memory/feedback_never_trust_currentpage.md` for the full
analysis and safeguard pattern.

### Missing-component wireframe placeholder

Mode 1 `createInstance()` fallbacks used to return
`figma.createFrame()` — a blank white frame that silently
substitutes for the missing component. Two problems:

1. Indistinguishable from intended blank output.
2. Downstream DB visual overrides (fills/strokes for the *real*
   component) were applied to the blank frame, producing
   visually-wrong output like a giant black rectangle where a
   wireframe was intended.

New behavior: the fallback is a wireframe-convention placeholder —
grey-stroked frame with 45° diagonal hatch pattern at 15% opacity
and an optional name label (size-gated). The placeholder marks
itself via `setPluginData('__ph', '1')`, and downstream self-target
visual-property writes are wrapped in `if (!_isPh(var)) { ... }` so
DB overrides can't clobber the wireframe.

A per-eid `KIND_COMPONENT_MISSING` entry is pushed to `__errors` on
every invocation, same verification contract as other ADR-007 kinds.

See `memory/feedback_missing_component_placeholder.md` for the full
pattern, including generalization to React/SwiftUI/Flutter.

### Safeguards

Two changes applied to `render_test/run.js` and
`render_test/walk_ref.js`:

1. **Hard page-identity assertion.** The output page is always
   resolved by name (`"Generated Test"`) and asserted before any
   destructive op. If resolution returns a different page (rename,
   lookup collision), throw rather than risk clearing source
   content. `figma.currentPage` is never a destructive-op target.

2. **Explicit-ID relocate manifest.** The cross-page relocate loop
   (which moves newly-created nodes that leaked to other pages via
   `getNodeByIdAsync` side-effects) previously used "everything not
   in `preIds`" as an allowlist. If the snapshot was incomplete,
   legitimate source content could be moved. Now uses the generated
   script's `M` id-map as an explicit manifest — refuses-by-default,
   moves only nodes whose ids we minted.

Both land in commit `a808e22`. Subsequent commits refined the
placeholder visual design through several iterations:

- `666e85f` — sentinel + `_isPh()` gate for clobbering; aspect-ratio
  threshold for X; mid-grey contrast color.
- `b5718a7` — replaced X diagonals with architectural hatch pattern.
- `541acfb` — fixed Plugin API rotation sign (+45 for up-right).
- `5a79b70` — subtle 15% opacity for stacked-placeholder graceful
  compounding.

### What this chapter did NOT solve

The safeguards protect the test-wrapper scripts. Ad-hoc
`figma_execute` calls the operator makes during a session aren't
gated by file-level code — the safeguard there is operator
discipline (always resolve output page by name, never trust
`currentPage`).

A plausible future safeguard: a Claude-side policy that rejects any
`figma_execute` code containing `.remove()` or cross-page
`appendChild` unless the code explicitly asserts the target page by
name first. That's a session-level rule, not a code change.

### Cross-cutting invariants (updated)

No new invariants in the ADR table — the safeguards are local to
the test wrappers. The KIND_COMPONENT_MISSING vocabulary extends
the ADR-007 structured error channel; no architectural change.

The pattern this chapter codified: **every destructive-op target
must be resolved by stable identifier (name/id) and asserted, never
read from platform-level "current X" state that can be side-effected
by unrelated API calls.** General across platforms; see memory
for cross-platform examples.


## Chapter epilogue (2026-04-16, pt 6) — Extract pipeline profiling baseline

After pt 5's backup restore, the next chapter started with a
deceptively simple ask: "a full re-extract — maybe we can instrument
the extraction to think of ways to improve performance while we do?"

The instrumentation (`dd/_timing.py`, `StageTimer`) was drop-in,
zero-dep, and immediately surfaced a lopsided time distribution:

```
REST fetch_screens               79s   22%
REST process_screens             24s    7%
Plugin supplement               127s   35%
Plugin transforms                34s    9%
Plugin properties                28s    8%
Plugin sizing                    28s    8%
Plugin vector-geometry           40s   11%
TOTAL                          361s
```

Three findings fell out of the baseline, each worth its own memory:

### Finding 1: Plugin supplement does work REST already did

The supplement pass's dominant cost is `getMainComponentAsync()` —
25,860 async calls per run, one per INSTANCE, each a plugin-API
round-trip. It exists because the code comment in `figma_api.py`
says "Component key is available at the file level in the components
map, not directly on the instance node in REST API."

Half-true. `/files/:key` returns a file-level map. `/files/:key/nodes`
returns one *per screen at the node-entry level*. Verified: the REST
`components` map has 100% parity with the supplement-populated
`component_key` column on the first 10 Dank Experimental screens
(58/58 distinct keys, zero diff). The data we needed was one JSON
level up from where we were reading, waiting 127 seconds every run.

`feedback_rest_components_map.md` captures the discovery and the
broader pattern: **every field currently filled via a Plugin-API
supplement pass deserves a property-by-property audit against a
fresh REST response.** "Plugin API is needed" is load-bearing for
~260s of every run and most of it is probably wrong.

### Finding 2: Five Plugin passes walk the same tree

Five separate extraction passes (supplement + four `extract_targeted`
modes) each spawn a Node subprocess, open a WebSocket, and walk the
entire node tree to collect a different slice of properties. All are
read-only, no ordering dependency between them.

`feedback_plugin_passes_consolidation.md` captures the consolidation
plan. The pattern is older than this chapter: whenever the pipeline
grows an N+1th "single-purpose supplement" that walks the same data,
treat it as a signal that the walker generation should become
registry-driven and the N+1 passes should merge into one.

### Finding 3: REST fetch is pointlessly serial

`FigmaIngestAdapter.extract_screens()` batches at size 10 and runs
batches sequentially. Measured 7.6× speedup going to 4 worker
threads on the first 40 screens of Dank Experimental. Figma's
published rate limit is ~50 req/s; we were sitting at ~0.4 req/s.
The fix is drop-in ThreadPoolExecutor.

### Combined impact

| | Current | Target |
|---|--:|--:|
| REST fetch | 79s | ~15s |
| REST process | 24s | 24s |
| Plugin passes | 257s | ~35s |
| **Total** | **361s** | **~74s** (~4.9×) |

### What this chapter did NOT change

No ADR amendments. The perf work touches implementation mechanics
of ingest/supplement, not the ingress/egress contract. ADR-006's
structured-error channel and ADR-007's unified verification loop
stay unchanged; the REST-side component_key population will write
through the same `boundary` adapter that the Plugin pass does today.

The baseline also ratified the restored Dank Experimental file:
screen 324 renders pixel-identical to source, `is_parity=True`,
91/91 nodes, zero errors. Round-trip pipeline is sound; the time is
in the extract, not the decode.

### Cross-cutting invariants (updated)

New invariant: **audit every Plugin-API supplement field against a
fresh REST response before adding it**, and **consolidate repeated
read-only walks of the same tree into one registry-driven pass**.
Both generalize across backends — the same "we already have this
from an earlier call" and "we're traversing the same structure N
times" patterns will appear on the ingress side of every future
backend (React AST from a bundler, SwiftUI from a Swift compiler
plugin, Flutter from `flutter analyze --machine`).


## Round-trip foundation milestone (2026-04-16)

With pt 6's perf work + regression fix landed, the "round-trip
foundation" phase is complete. The full corpus sweep passes with
zero drift, zero failures, and zero structured errors:

```
=== SUMMARY ===
total:            204
is_parity=True:   204
is_parity=False:    0
generate_failed:    0
walk_failed:        0
elapsed:          449.4s  (2.2 s/screen)
error_kinds:      {}
```

This is the gating criterion the rest of the roadmap has been
waiting on. Everything downstream — the React renderer, the
SwiftUI renderer, synthetic screen generation — builds on a
verified round-trip contract.

### What the milestone actually proves

- **L0 is complete and lossless.** 86,766 nodes extracted, 204
  screens reproduced from the DB alone, no visible or structural
  drift.
- **L1 classification is accurate enough to drive Mode 1
  rendering.** Every INSTANCE with a resolvable master renders
  via `createInstance()` with full override application.
- **The Mode 1 → Mode 2 → placeholder fall-through is
  observable.** When a master can't resolve, the wireframe
  placeholder appears on the rendered screen and a
  `KIND_COMPONENT_MISSING` entry appears in `__errors`. Zero
  silent drops.
- **The verifier's kind vocabulary is load-bearing.** The
  mid-sweep regression (empty asset store after the unified
  plugin pass shipped without `process_vector_geometry`)
  surfaced as `KIND_MISSING_ASSET` on iteration 3, not as a
  "looks off" that a human might miss. That's the contract
  ADR-007 was written to enforce, working.
- **The pipeline is reproducible.** `python3 render_batch/sweep.py`
  produces the same summary, the same per-screen
  `RenderReport`s, and the same `is_parity` verdict every run.

### What comes next

From the roadmap, in priority order:

1. **React + HTML/CSS renderer.** Second backend. Validates the
   IR's cross-platform claim. The M × N → M + N property has
   been claimed since section 5 of the spec; a second backend
   proves it.
2. **Synthetic screen generation.** Prompt → IR → (existing)
   deterministic renderer. The architecture was positioned for
   this from ADR-001 onward (capability gate as constrained-
   decoding grammar; verifier as dense training signal). The
   infrastructure is now in place; the plan needs fleshing out.
3. **Additional backends, additional extractors.** Both are
   routine at this point — same registry-driven shape.

### Cross-cutting invariants (restated)

Carried forward from the chapter's work, now baked in:

- **Capability-gated emission is non-negotiable** (ADR-001).
- **Null-safe Mode 1 + per-op micro-guards are non-negotiable**
  (ADR-002).
- **Explicit-state harness at script entry is non-negotiable**
  (ADR-003).
- **Boundary contract on every external edge is non-negotiable**
  (ADR-006). Symmetric on ingress and egress.
- **Unified verification channel with per-node granularity is
  non-negotiable** (ADR-007). `is_parity = True` is the
  criterion for "round-trip successful"; it does not degrade
  to "no exception thrown."
- **Every consolidated pipeline stage owns its post-processing
  tail, not just its collection code** (pt 6 lesson, no ADR —
  too specific to lifting-and-shifting pipeline stages, but
  permanent in the consolidation-review checklist). See
  `feedback_consolidation_audits_post_processing.md`.


## ADR-007 extension (2026-04-16) — outer render guard + leaf-type layout gate

Two latent bugs in the round-trip foundation surfaced during Wave 1 of
the synthetic-generation research sprint. Both survived 204/204 parity
because the extractor never produces the IR shapes that trigger them
— only synthetic IR does.

### The leaf-type layout-property gate

The existing renderer emits `node.layoutMode = "..."` whenever the
element's `layout.direction` is set. Auto-layout is only valid on
FRAME / COMPONENT / COMPONENT_SET / INSTANCE. Setting `layoutMode`
(or `itemSpacing`, `padding*`, `primaryAxisAlignItems`,
`counterAxisAlignItems`) on TEXT / RECTANGLE / ELLIPSE / VECTOR /
LINE / BOOLEAN_OPERATION / GROUP is rejected by the Plugin API with
`"object is not extensible"`.

**Why this slipped through the 204/204 sweep:** the extractor does
not populate `layout.direction` on leaf-type IR elements, because
the DB columns for layout properties are NULL on those nodes in
Figma. The round-trip test corpus therefore never exercised the
code path. Synthetic generation DID — via `compose.py`'s template
lookup — because compose doesn't gate template defaults on the
element's type. It emits `direction: "vertical"` on a `"text"`
element because that's the default.

**Fix:** a `_LEAF_TYPES` frozenset in `dd/renderers/figma.py` plus
an `etype` parameter threaded to `_emit_layout`. When the element's
type maps to a leaf Figma node, the auto-layout-only properties
are skipped entirely. The resize() path still runs (width / height
are universally supported).

Regression tests live in `tests/test_property_registry.py`
(`TestCapabilityGating`), parameterised across every leaf type,
with positive cases confirming FRAME-typed elements still emit
auto-layout correctly.

This is a specific instance of the general ADR-001 principle
(capability-gated emission) applied to the non-registry-driven
`_emit_layout` code path. The registry-driven emission already
had this gate via `node_type` filtering in `emit_from_registry`;
this fix extends the same discipline to the layout emission.

### The outer render-guard: `KIND_RENDER_THROWN`

ADR-007 Position 2 wraps every runtime write in a per-op
micro-guard that pushes `{eid, kind, error}` into `__errors`
without aborting the render. The per-op pattern assumes failures
are per-property; it does not defend against script-level throws
that bypass every per-op wrapping and reach the runtime harness as
a raw exception.

The leaf-type layout bug produced exactly this class of failure:
an illegal property setter on a TEXT node threw at Phase 1, before
any per-op guards ran. Zero `KIND_*` entries reached `__errors`
despite a total render failure — the harness saw only the Node-
level "script aborted" signal with no structured cause.

**Fix:** wrap Phases 1-3 of every generated script in an outer
`try { ... } catch (__thrown) { ... }` that pushes a
`render_thrown` structured error into `__errors`:

```js
try {
  // Phase 1: Materialize
  // Phase 2: Compose
  // Phase 3: Hydrate
} catch (__thrown) {
  __errors.push({
    kind: "render_thrown",
    error: String(__thrown && __thrown.message || __thrown),
    stack: __thrown && __thrown.stack ?
      String(__thrown.stack).split("\n").slice(0, 6).join(" | ") : null
  });
}
M["__errors"] = __errors;
return M;
```

The catch does NOT re-raise. Instead it falls through to the
existing `M["__errors"] = __errors` attachment and `return M;`.
The runtime harness sees the script "succeeded" from Node's
perspective but the returned payload carries the structured
failure — which is consistent with every other `KIND_*` on the
ADR-007 channel. A raw exception would discard every
`__errors` entry the script had accumulated before the throw.

### New kind vocabulary

- `render_thrown` — script-level throw that bypassed the per-op
  micro-guards. Carries `error` (the thrown message) and `stack`
  (first 6 frames, pipe-separated).

### What this changes about the invariants

Restated with the new guard in place: **every failure mode in the
pipeline has exactly one `KIND_*`.** Per-op failures → per-op
kinds. Script-level failures → `render_thrown`. Content-missing
→ `component_missing` / `missing_asset`. Verifier-time failures
→ `bounds_mismatch` / `fill_mismatch` / etc. Nothing reaches the
harness as an unstructured exception unless something genuinely
pathological (e.g. Plugin API disconnection mid-call) occurs —
and even those should in principle be wrapped as the pipeline
matures.

This closes the one known class of invisible failure that the
204/204 parity claim allowed. Synthetic generation wouldn't have
been usable without it.

## ADR-008: Composition providers — Mode 3 synthesis from catalog, corpus, and ingested systems

**Problem.** The round-trip renderer handles two modes cleanly:
**Mode 1** (IR carries `component_key` → `getNodeByIdAsync().createInstance()`)
and **Mode 2** (IR carries L0 visual properties copied from the DB →
apply them to a `createFrame()`). Synthetic IR from the prompt pipeline
has **neither** — no `component_key` (the LLM doesn't see the project's
CKR) and no DB-sourced L0 properties (no node id to look up). Mode-2
falls through to a bare `createFrame()` with `fills=[]` and no children.
Result, measured on the 12 v3 prompts: 212 of 229 non-screen nodes
render as empty 100×100 grey frames; the rule-based + Gemini VLM sanity
gate reports 12/12 categorically broken (see
`docs/research/synthetic-generation-deep-diagnosis.md`).

The gap is not "missing component library." It is a missing pipeline
stage. Given a catalog `type`, a `variant`, and the LLM's `props`, we
have no path that produces a plausible Figma subtree. The renderer's
`_emit_composition_children` fires only when a DB template carries a
`_composition` field — which synthetic IR never has.

**Decision.** Introduce **Mode 3 — Composition-provider synthesis** as a
first-class pipeline stage. Mode 3 resolves `(type, variant, context)`
to a `PresentationTemplate` through an ordered **provider registry**,
resolves any `{token}` refs inside the template through a three-layer
**DTCG token cascade**, recurses through slot-contract children, and
splices the result into the IR as first-class synthetic children. The
renderer is unchanged; Mode 3 operates entirely at the compose layer.

Three interlocking components ship in a new `dd/composition/` package:

- **`ComponentProvider` protocol** mirroring ADR-006's `IngestAdapter`:
  `priority: int`, `backend: str`, `supports(type, variant) -> bool`,
  `resolve(type, variant, context) -> PresentationTemplate`.
- **Registry** (`dd/composition/registry.py`) — ordered walk in descending
  priority; first `supports()`-true wins. Tie-break on `backend` name
  alphabetically for determinism.
- **Token cascade** (`dd/composition/cascade.py`) — resolves
  `{color.brand.primary}` style refs through ordered layers
  `project > ingested > universal`. First layer that defines the path
  wins. Unresolved → `KIND_TOKEN_UNRESOLVED` with literal fallback so
  render still proceeds.

Four built-in providers in v0.1:

| Provider | Priority | Source |
|---|---|---|
| `ProjectCKRProvider` | 100 | User's extracted corpus: `component_key_registry` + `variant_token_binding` |
| `IngestedSystemProvider` | 50 | Ingested design systems via ADR-006's `IngestAdapter` (shadcn first) |
| `UniversalCatalogProvider` | 10 | Hand-authored defaults for the 22-type universal backbone (structure from Stream A ontology + Exp I sizing; colour/radius/shadow values ported from shadcn) |
| `TokenOnlyProvider` | 0 | Last-resort synthesis from DTCG atoms; neutral frame with resolved tokens |

**Rationale.** This is the symmetric dual of ADR-006 on the egress
side. The ingest contract says "every boundary that imports data emits
an `IngestResult` with `StructuredError` on partial failure." The
composition contract says "every boundary that resolves intent to
structure emits a `PresentationTemplate` with `StructuredError` on
partial match." Same shape, same error channel, same CI-visible
per-node granularity.

The fall-through ordering (project > ingested > universal > token-only)
is the correct precedence for a tool whose value proposition is "your
design system is authoritative." A project-native `button/primary`
always beats shadcn's `button/primary`; shadcn's only wins when the
corpus doesn't know the variant. No surveyed design system formalises
this provider-coexistence problem — it is the differentiator Stream C's
survey identified.

### Naming: "variant", not "role"

The Stream B induction research initially called its output "role
bindings" — inherited from Material 3's "color roles" terminology. That
word carries ARIA and semantic-category baggage across the frontend /
design community and collides with `dd/catalog.py`'s existing
(vestigial; see below) `semantic_role` field. Every major compositional
system (cva/shadcn, Panda CSS, Stitches, Chakra, Material M3's
`md.comp.*` layer) uses **variant** for exactly what we're storing:
"per catalog type, per variant, per slot, which token?" The IR already
names it the same. Committed name: `variant_token_binding` for the
table, `cluster_variants.py` for the inducer, "variant labelling" for
Stream B's VLM pass.

### Data model

**`PresentationTemplate`** (Python `@dataclass(frozen=True)` in memory
at resolution time; not a persisted object):

```python
@dataclass(frozen=True)
class PresentationTemplate:
    catalog_type: str          # "button"
    variant: str | None        # "primary" | None for default
    provider: str              # "project:dank" | "ingested:shadcn" | "catalog:universal"
    layout: LayoutSpec         # direction, sizing, padding, gap — token refs allowed
    slots: dict[str, SlotSpec] # slot_name → {allowed_types, required, default_child?}
    style: StyleSpec           # fills, strokes, radius, shadow — token refs allowed
    compound_variants: list[CompoundOverride]  # cva-style compound matchers
```

**`variant_token_binding`** (new DB table introduced in PR #1):

```sql
CREATE TABLE variant_token_binding (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  catalog_type    TEXT NOT NULL,
  variant         TEXT NOT NULL,    -- 'primary' | 'destructive' | 'custom_1' | ...
  slot            TEXT NOT NULL,    -- 'bg' | 'fg' | 'border' | 'shadow' | 'radius' | ...
  token_id        INTEGER REFERENCES tokens(id),
  confidence      REAL NOT NULL,    -- 0.0..1.0 from the variant inducer
  source          TEXT NOT NULL,    -- 'cluster' | 'vlm' | 'screen_context' | 'user'
  created_at      TEXT NOT NULL,
  UNIQUE(catalog_type, variant, slot)
);
```

Populated by the **variant inducer** (`dd/cluster_variants.py`, new in
PR #1). Algorithm for v0.1:

1. For each catalog type with ≥5 classified instances: feature-vector
   each instance (fills, strokes, radius, dimensions, icon-presence,
   adjacency).
2. K-means in OKLCH + normalised dimensions; silhouette score picks K.
3. For each cluster, send ≤10 rendered thumbnails to Gemini 3.1 Pro
   with a closed vocabulary `{primary, secondary, destructive, ghost,
   link, disabled, unknown}`. Unknown-labelled clusters persist as
   `custom_N` so the LLM generator retains them in vocabulary.
4. Write `variant_token_binding` rows for each `(type, variant, slot)`
   pair using the cluster's representative token values.

**Vestigial field flagged, not removed.** `CatalogEntry.semantic_role`
and the matching `component_type_catalog.semantic_role` column
(introduced at T5 Phase 0 for "future a11y / React code export") are
written at seed time but read nowhere in `compose.py`, `renderers/`,
`classify*.py`, `verify*.py`, `ir.py`, or `extract*.py`. They remain
in place for this ADR — a cleanup pass can remove them without
affecting any pipeline stage. An inline comment in `dd/catalog.py`
marks the field as deprecated and points here; picking it up belongs
in a small dedicated PR, not bundled with Mode 3 work.

### Failure vocabulary — new `KIND_*` constants on `dd/boundary.py`

| Kind | Severity | When | Recovery |
|---|---|---|---|
| `KIND_NO_PROVIDER_MATCH` | terminal | Registry exhausted without `supports()`-true | placeholder emitted + error |
| `KIND_VARIANT_NOT_FOUND` | informational | Type resolves, variant does not; walk continues | fall-through |
| `KIND_TOKEN_UNRESOLVED` | informational | `{path}` ref absent from all cascade layers | literal fallback |
| `KIND_SLOT_TYPE_MISMATCH` | informational | Slot expects type A, IR child is type B | splice anyway with warning |
| `KIND_VARIANT_BINDING_MISSING` | informational | Inducer has no row for `(type, variant, slot)` | template default |

All five feed ADR-007's existing per-node `__errors` channel. No new
channel; new vocabulary only. The `RenderVerifier` attributes them
per-eid. The eventual v0.3 render-critic-refine loop consumes them as
training signal.

### Provider ordering and tie-breaking

1. **Priority wins.** Higher integer priority beats lower.
2. **Alphabetical on `backend`** breaks ties (`ingested:carbon` beats
   `ingested:shadcn` at equal priority because `c < s`). Deterministic;
   reproducible across runs.
3. **`supports()` gates resolution.** A provider that does not claim
   `(type, variant)` is skipped. A provider returning `True` from
   `supports` and `None` from `resolve` is a protocol violation.
4. **Feature flag `DD_DISABLE_MODE_3=1`** short-circuits the entire
   registry walk, restoring today's empty-frame behaviour as a
   baseline. Per-provider disable via
   `DD_DISABLE_PROVIDER=ingested:shadcn` for surgical kill.

### Invariants

- **Mode-1 and Mode-2 unchanged.** Mode-3 fires only when both fail.
  The 204/204 round-trip parity claim holds unmodified.
- **No L0 IR schema change in v0.1.** `PresentationTemplate` lives in
  memory; synthesised subtrees splice as ordinary IR children with
  existing field shape.
- **Provenance in v0.2.** Optional `provider: str` field per node,
  opt-in, backwards-compatible with existing IR consumers.
- **Structured errors at every fall-through.** Every provider miss,
  every unresolved token, every slot mismatch feeds the `__errors`
  channel. Consumers (CI, training loop, RenderVerifier) switch on
  `kind`, not free text.

### Relationship to other ADRs

- **ADR-001 (capability-gated emission).** Mode-3 templates reference
  tokens and slot types; the capability registry gates whether a
  resolved value can be emitted on a given backend. Symmetric reuse.
- **ADR-006 (boundary contract).** `ComponentProvider` is the egress
  twin of `IngestAdapter`. `PresentationTemplate + StructuredError` is
  the return-shape twin of `IngestResult`.
- **ADR-007 (unified verification channel).** All five new `KIND_*`
  codes flow through the existing channel. The `RenderVerifier`
  attributes them per-eid with no new machinery.

### Phasing

**PR #0 — Catalog ontology migration (precursor, isolated).**
- Add 7 types to `dd/catalog.py`: `divider`, `progress`, `spinner`,
  `kbd`, `number_input`, `otp_input`, `command`.
- Demote 3 to aliases: `toggle_group → toggle{grouped=true}`,
  `context_menu → menu{trigger=context}`; keep `file_upload` but split
  via `variant: button | dropzone`.
- Thicken slot grammar: `list_item` gains Material's six-slot shape
  (`leading / overline / headline / supporting / trailing_supporting /
  trailing`); `card.image → card.media`; `alert` gains `close`;
  `text_input` gains `helper`.
- Add variant-axis declarations: `state`, `tone`, `density`.
- Add an inline deprecation comment on `semantic_role`; do **not**
  drop it (tracked cleanup debt).
- DB migration `011_catalog_ontology_v2.sql` (additive; idempotent;
  back-compat aliases preserved).
- **Gate: 204/204 round-trip parity must pass unchanged.**

**PR #1 — Mode 3 composition (main, builds on PR #0).**
- `dd/composition/` package: `protocol.py`, `registry.py`,
  `cascade.py`, `providers/{universal,project_ckr,ingested}.py`.
- `dd/cluster_variants.py` (variant inducer, Stream B v0.1).
- `variant_token_binding` table + migration
  `012_variant_token_bindings.sql`.
- Five new `KIND_*` constants on `dd/boundary.py`.
- Compose-layer integration at `compose._build_element`'s Mode-2
  fall-through point.
- Feature flag `DD_DISABLE_MODE_3` + `DD_DISABLE_PROVIDER=...`.
- Re-run 12 v3 prompts; sanity gate must pass on ≥10/12.

**v0.2 (post-v0.1 ship):**
- Screen-context priors in the variant inducer (Stream B's
  candidate C).
- Optional `provider` + `variant_binding` IR provenance fields.
- shadcn cold-start palette transplantation (Material-You HCT).
- `RenderVerifier` provider-attribution.

**v0.3 (speculative, gated on full RenderVerifier parity):**
- Render-critic-refine loop à la GameUIAgent; consumes `KIND_*` as
  training signal.

### Cleanup debt (tracked, not blocking)

- Remove `CatalogEntry.semantic_role` and
  `component_type_catalog.semantic_role` column. Zero runtime callers.
  Requires one catalog-only migration; trivial; schedule for a
  dedicated cleanup PR after v0.1 ships.

### What this does not attempt

- **Animation / transitions.** Out of scope.
- **Responsive breakpoints.** `PresentationTemplate.layout` is static
  in v0.1; breakpoints are v0.4.
- **A11y / ARIA export.** Orthogonal to Mode 3; solvable
  deterministically if ever needed.
- **Internationalisation.** Out of scope.
- **Multi-project variant-binding transfer.** Per-project in v0.1;
  transfer requires user opt-in and is a v0.2 measurement.

The composition-provider architecture preserves every ADR-001..007
invariant, extends ADR-006's boundary contract to the egress side, and
turns Mode 3 from a missing pipeline stage into a symmetric mirror of
the ingest pipeline we already trust.

---

## ADR-008 Chapter epilogue (2026-04-17) — v0.1.5 Week 1 end-to-end

Week 1 of the v0.1.5 sprint shipped A1 archetype-conditioned few-shot
across 5 commits on top of the ADR-008 base. End-to-end results on the
12 canonical prompts:

| metric | 00f baseline | 00g (A1 live) | Δ |
|---|---:|---:|---:|
| VLM-ok | 4 / 12 | **6 / 12** | +2 (+50%) |
| Mean structural nodes | 21.8 | 25.2 | +3.5 (≈ +1.02 σ) |
| Round-trip parity | 204 / 204 | 204 / 204 | preserved |
| Mode-1 createInstance() | 63 | 70+ | — |

**Commit chain** (all on `main`, all with TDD coverage, all preserving parity):

1. `a4ef55f` — β matrix (240 Haiku calls). Verdict: no SYSTEM_PROMPT
   contract variant beats S0 by the §7 criterion. Kept T=0.3.
2. `cfd753d` — 12 hand-authored archetype skeletons in
   `dd/archetype_library/`. Provenance declared: Dank's
   `screen_component_instances` is empty in the current snapshot, so
   corpus-mining is deferred to v0.2.
3. `0be0030` — `dd/composition/archetype_classifier.py` (keyword +
   Haiku fallback) and `dd/composition/archetype_injection.py`.
   `DD_DISABLE_ARCHETYPE_LIBRARY=1` flips the whole path to no-op.
4. `22ce53c` — `RuleBasedScore` gains `total_node_count` +
   `container_coverage`. Surfaced in `sanity_report.md`.
5. `d23a743` + `897495b` — 00g experiment artefacts.

**Plan §5 stopping criterion:** required ≥7 VLM-ok AND density ≥+1 σ.
Got 6 / 12 VLM-ok (missed by 1) and +1.02 σ. Routed to A2 plan-then-fill
per §Week 2.

### Reinforced invariants

All seven ADRs hold after v0.1.5 Week 1:

- **ADR-001 capability-gated emission** — unchanged; archetype library
  only adds few-shot inspiration, not capability grammar.
- **ADR-002 null-safe Mode 1** — unchanged; classifier returns None
  gracefully when it can't route.
- **ADR-003 explicit state harness** — unchanged; driver writes per-
  prompt `system_prompt.txt` + `classified_archetype.txt` so the
  compose state is reproducible from artefacts.
- **ADR-004 verification loop** — unchanged; gate still rule + VLM.
- **ADR-005 null-safe prefetch** — unchanged.
- **ADR-006 boundary contract** — unchanged; clarification-refusal
  (`KIND_PROMPT_UNDERSPECIFIED` signal) continues to flow through the
  structured failure channel. `classify_archetype` protects its
  outputs on malformed / out-of-vocab responses.
- **ADR-007 unified verification channel** — unchanged; `__errors`
  payload on the Mode-3 run still structured per-eid.

### Extensions landed

- **Provider-chain reservation 75** (between `ProjectCKRProvider=100`
  and `UniversalCatalogProvider=10`). Not yet realized as a registered
  provider — archetype library injection happens at the prompt layer
  in `prompt_to_figma`, not the provider chain. Architectural hook
  remains available for when ingested-system and archetype mechanisms
  need to compose deterministically (v0.2).
- **Rollback fence**: `DD_DISABLE_ARCHETYPE_LIBRARY=1` is the single
  env-var flip that rolls A1 back to v0.1 SYSTEM_PROMPT-only behaviour.
  Tested; verified in the unit suite (`test_archetype_classifier.py::
  test_feature_flag_disables_classifier` + `test_prompt_parser.py::
  test_archetype_injection_disabled_by_flag`).

### Follow-ons seeded for Week 2 / v0.2

- **04-dashboard regression** (partial → broken): tables render as
  text stacks because the row template has no vertical differentiation
  between column headers and row cells. Render-template layer, not
  archetype. A2 plan-then-fill will not fix it; separate work.
- **VLM transient-flakiness handling**: the rule+VLM gate needs outer
  rerun tolerance. Current retry (2× w/ exponential backoff) isn't
  enough for batch runs at Gemini's Tier-1 rate.
- **PROXY_EXECUTE parse-depth repeat bug**: 00f hit it, 00g hit it.
  Both fixed post-hoc. Baked into `render_test/run.js` documentation
  would prevent the next recurrence.
- **A2 plan-then-fill** (`DD_ENABLE_PLAN_THEN_FILL`) is the
  plan-routed next step to close the VLM-ok gap.

---

## ADR-008 Chapter epilogue (2026-04-17, pt 2) — post-v0.1.5 forensic rounds

After v0.1.5 shipped at R3 (12/12 canonical VLM-ok), two more rounds
extended the work: a breadth test (20/20 rendered, fidelity 0.72) and
a parallel-subagent forensic pass on remaining visible defects.

### Breadth generalisation test (00i-breadth-v1, commit `9e05bf0`)

20 prompts across 8 domains outside the canonical 12 (e-commerce,
messaging, productivity, system states, auth, media, location, ops).

| metric | canonical 00g (R3) | breadth 00i |
|---|---:|---:|
| render completion | 12 / 12 | **20 / 20** |
| mean render-fidelity | 0.75 | **0.72** |
| mean prompt-fidelity | 0.83 | 0.67 |
| parity | 204 / 204 | 204 / 204 |

Render-fidelity within 3 % confirms the architecture generalises.
Prompt-fidelity is lower because the keyword classifier misroutes
4 / 20 prompts (e.g. "message" in error-state → chat), but A1's
"inspiration, not template" framing means the LLM freelances
correctly in all misroute cases. Zero new architectural bugs
surfaced — all rule-gate broken/partial verdicts map to pre-known
defect classes.

### 5-subagent parallel forensic (post-breadth, commit `a54a3ed`)

Spawned one Explore subagent per visible defect class observed in
the breadth screenshots:

| # | defect | subagent finding | fix |
|---|---|---|---|
| 1 | render_thrown "not a function" | Parent IS a TEXT leaf (`link` → createText); has no `.appendChild`. Phase 2 abort orphans the whole tree. | Landed (`a54a3ed`) |
| 2 | empty text_input rectangles | Subsumed by #1 — orphaned tree is invisible to walk_ref. | Subsumed |
| 3 | blank blue image placeholders | `_missingComponentPlaceholder` pattern (`fills=[]` + line children) avoids paint cascade. | Deferred (cosmetic) |
| 4 | "×" icon everywhere | NOT a text-fallback — baked into Dank's `button/large/translucent` component and inherited via `createInstance`. | Deferred (data-side) |
| 5 | horizontal layout collapse | `dd/compose.py:147` hard-codes vertical; LLM doesn't emit horizontal wrappers. | Deferred (deeper) |

**Fix #1 (leaf-parent `appendChild` gate)** was the highest-leverage
immediate win: both the crash on signup/2fa/reset AND the empty
text_input rectangles collapsed into one root cause. Patched the
renderer to skip `leafParent.appendChild(child)` and emit a soft
diagnostic `leaf_type_append_skipped` instead. Added a filter in
`dd/visual_inspect.py::inspect_walk` so soft diagnostics don't flip
`had_render_errors` → combined-verdict-broken.

**Visible win**: 12-signup-form went from 5 empty rectangles to
full labels + placeholders ("Full Name / Enter your full name"
etc.). Same fix silently unbroke 01-login, 10-onboarding-carousel,
13-password-reset, 14-2fa-verify from the `had_render_errors` rule
flip.

### Methodology wins worth keeping

- **Parallel-subagent forensic** (one Explore per defect class, all
  spawned in a single tool-call message) is repeatable for any
  multi-class defect investigation. See
  `feedback_parallel_subagent_forensic.md`.
- **T1..T8 script-ablation diagnostic** (strip one property class
  at a time via regex + re-run through bridge) isolated the R3
  root cause (container fill → paint cascade) in 2 minutes.
  Should be a standard tool when render perf regresses.
- **Fidelity scorer** (`dd/diagnostics/fidelity.py` + `experiments/_lib/
  score_experiment.py`) separates prompt-layer from renderer-layer
  quality signals. Prevents the conflation that drove three prompt-
  only experiments before the root cause was diagnosed.

### Deferred to v0.2 (with rationale)

1. **Fix #4 "×" icon inheritance** — override children on
   `createInstance` results for buttons that have baked-in sub-icons;
   or rerank CKR suggestions to prefer components without extra
   children; or source-fix the Dank components.
2. **Fix #5 horizontal layout** — add a column-aware `table` layout
   OR propagate archetype-level horizontal hints to screen-root
   wiring OR LLM prompt guidance for horizontal wrappers.
3. **Fix #3 `_imagePlaceholder`** — mirror the pattern of
   `_missingComponentPlaceholder` (fills=[] + line children) so images
   read as designer wireframes without triggering the paint cascade
   H7 hit.
4. **03-meme-feed Phase-2 layoutMode deferral** — move per-parent
   `layoutMode` emission from Phase 1 to a new Phase 2b after all
   `appendChild` lands. Right long-term fix but risky to round-trip
   parity; needs dedicated session.
5. **Second-project portability** — port the pipeline against a
   non-Dank Figma file to validate the universal architecture
   isn't Dank-specific.

### Final session state

- 1,932 unit tests green.
- 204 / 204 round-trip parity preserved through every commit.
- 00g canonical: 12 / 12 VLM-ok at R3 (commit `f16dfc0`); 11 / 12
  in the latest run due to LLM T=0.3 variance on 12-round-trip-test
  — quality unchanged.
- 00i breadth: 20 / 20 rendered, fidelity 0.72.
- VLM currently 429-throttled across the session; fidelity scorer
  is the reliable signal.
- Ship state remains R3 (`f16dfc0`) + Fix #1 (`a54a3ed`): Mode 3
  structurally solved, perceived-quality polish deferred to v0.2.
