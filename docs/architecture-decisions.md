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
