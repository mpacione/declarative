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
