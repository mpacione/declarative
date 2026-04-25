# v0.4 Plan — Design-System Compiler, Made Provable

> **Version: v2 (in progress)**. v1 (commit `eccdab5`) was
> red-teamed by 5 critics; all returned REVISE. Critical
> issues integrated below. v2 is being written section-by-
> section; this revision covers §1-§4 W4. §5-§15 still
> reflect v1 framing and are flagged with `[V1 — REVISING]`
> until updated.
>
> **For the next session.** You are arriving cold. This
> document is self-contained — it captures the audit
> findings, the architectural decision, the ordered
> workstreams, the parallel-agent execution patterns, the
> verification gates, and the kill-shot demos that v0.4
> must produce.
>
> **Do not re-derive.** The plan IS the design. When
> something here conflicts with a prior plan or rationale
> doc, this document wins. Lessons that survived prior
> sessions are integrated; mistakes that surfaced are
> fenced off.
>
> **Read order**:
> 1. §1 Goal + §2 Audit — *why* we're doing this
> 2. §3 Architecture decision — *what* we're building
> 3. §4-§7 Workstreams — *the work*
> 4. §8 Phasing + §9 Parallel-agent execution pattern — *how
>    you'll execute*
> 5. §10 Verification gates — *how we know it landed*
> 6. §11 Demo deliverables — *what proves it*
> 7. §12 Risk register + §13 Anti-scope — *what could go
>    wrong, what to NOT do*
> 8. §14 Inheritance + §15 Rollback policy + §16
>    References

---

## 1. Goal statement

v0.4 ships **design-system-aware compilation as a provable
invariant**, not a prompt claim.

Given dd-markup that references tokens, text styles, and
components (including variants), the pipeline must preserve
semantics end-to-end: rendered Figma output uses INSTANCE
nodes for components, `setBoundVariable` for tokens, and
named text styles for typography — with **zero silent
degradation** to literal hex / raw FRAME / default
typography.

Concretely, after v0.4 lands:

- The `dd design --render-to-figma` path is **architecturally
  incapable of consuming unresolved input** in strict mode.
  Any unresolved TokenRef, component path, or variant axis
  becomes a typed error surfaced to the agent and the
  harness — not a silent fallback rendering.
- A **compat mode** resolver still produces a valid IR with
  explicit placeholder nodes when inputs are unresolved.
  This is required so that the byte-equivalence telemetry
  (W4) can run on every screen of the corpus during the
  transition, including screens with currently-unauthored
  properties. Strict mode is the demo / merge-gate; compat
  mode is the dev / telemetry mode.
- The agent receives a **filtered, component-reachable
  catalog + a session-scoped tool-schema enum + a session
  ledger**, so it can choose valid tokens/components and
  remember what it's already decided. Tool-schema enums are
  stable across a session to preserve prompt cache;
  reachable filtering happens in the user message as a
  hint, not as a hard constraint.
- The verifier rejects **literals when a near-token exists**
  (configurable distance, with `force_literal: true`
  escape-hatch for legitimate brand exceptions), and the
  agent can self-correct.
- Four kill-shot demos (§11) prove all the above on real
  Dank Experimental screens, side-by-side with the original.
- An **interim status demo** lands at end of Phase 1 (week 1)
  for stakeholders who can't wait 6 weeks for the full
  Loom.

**Time budget**: 6-7 weeks of focused work, 8-week buffer.
(v1 said 4-6; multiple critics said this was aggressive.)

**What v0.4 does NOT do**: §13.

---

## 2. Audit recap (verified pre-plan)

### What broke the demo trajectory

A late M2 demo run produced a generic blue rectangle when
asked to "add a sign-out button." MCP audit confirmed:

- Agent emitted `frame #button-sign-out { text "Sign Out" }`
  + literal hex `#007AFF` + 0 corner radius + Inter Regular
  12pt black-on-blue (contrast failure).
- The screen's existing buttons are 48×52 INSTANCEs of
  `button/large/translucent`, with `radius=10`,
  Inter SemiBold 16pt #09090b, all bound to design-system
  variables.

The agent's output was visually indistinguishable from
"Claude Code drew a box on a Figma file." The pitch — "uses
your real components, tokens, typography" — was not visible
in the artifact.

### The three legs of the gap

Verified by reading source:

1. **Grammar capability — WORKS.** dd-markup parses
   `fill={color.action.primary}`, `-> button/large/translucent
   #my-btn`, path overrides, variants. Spec documented
   (`docs/spec-dd-markup-grammar.md`). Fixtures exercise each
   shape (`tests/fixtures/markup/*.dd`). Compressor handles it.
   No new grammar work needed.

2. **LLM context — BROKEN.** Token catalog and component
   catalog never reach the agent. Tool schemas don't
   enumerate them. System prompt mentions one example token
   in passing. The CLI's `dd design` call site doesn't pass
   `component_paths`, so the swap tool isn't even registered
   (`dd/cli.py:2164-2168`, defaults to `()`).

3. **End-to-end semantic preservation — BROKEN.** The
   variant-render path bypasses the rebind pipeline that
   `dd push` uses successfully (and which carries the
   204/204 round-trip parity sweep). Resolver shipped during
   M2 silently drops TokenRef values
   (`dd/ast_to_element.py:166-170,198-202`). Renderer's
   path→component_key resolution lives in dead Mode-3 code
   (`dd/renderers/figma.py:904`). LLM-invented
   `-> button/X #my-btn` falls through to
   `figma.createFrame()` (`render_figma_ast.py:1017-1059`).

### The lens convergence

Five agents reviewed the gap independently (compiler architect,
systems engineer, ML pragmatist, demo strategist, Codex). They
converged on:

- **The IR is a federated view, not a compiler.** L0/L1/L2/L3
  are framed as a lowering pipeline but the renderer reads
  them à la carte. There's no single IR-with-invariants the
  renderer is required to consume.
- **Semantic preservation must be enforced by the type
  system AND runtime provenance.** The renderer's input type
  must make TokenRef-drop a type error AND the resolver must
  enforce "TokenRef-in ⇒ TokenBinding-out" with explicit
  per-pass provenance, because Python's type system alone
  doesn't prove that.
- **Path → component_key resolution belongs in a single
  pass, not six patches.** This is a multi-pass conversion
  pipeline, dataclass-based — sufficient for v0.4's scope.
- **The 204/204 round-trip will silently break** when
  variant-axis selection lands without new error kinds
  (`KIND_VARIANT_FALLBACK`). This must be solved BEFORE the
  refactor, not after.
- **Pre-flight ground-truthing is required.** Before any
  workstream ships, the four demo screens (333/217/091/412)
  must be DB-verified to have the structural properties the
  demos depend on, the MCP-verify assertions must be
  queryability-tested, and the dedicated test Figma file
  (`Dank-Test-v0.4`) must be created.

These findings define the architecture in §3 and the W0
foundation work that lands before W1.

---

## 3. Architecture decision

### The shape: ResolvedFigmaIR + multi-pass resolver + three-method renderer

Introduce a new IR — `ResolvedFigmaIR` — whose leaf values are
typed value-shapes carrying explicit provenance. The renderer
has exactly three methods per property (one per leaf-shape
kind), with type-checked dispatch:

```python
class FigmaEmitter:
    def apply_literal(self, var: str, prop: FigmaProperty, value: Literal[T]) -> list[str]: ...
    def apply_bound(self, var: str, prop: FigmaProperty, bound: TokenBinding[T]) -> list[str]: ...
    def apply_composite(self, var: str, prop: FigmaProperty, composite: Composite) -> list[str]: ...
    # No fourth method exists. Type system + dispatch table enforce this.
```

There is no fourth path that silently picks. **Dropping a
TokenRef becomes a type error at the boundary AND a runtime
assertion** (per-pass provenance, R7-R8 below), not a
runtime regression.

(v1 had two methods. Three critics flagged that
`Bound[T] = Literal[T] | TokenBinding[T]` doesn't fit
composite leaves like `cornerRadius` (uniform-or-per-corner),
constraints, or layout enums. The resolution is to add
`Composite` as a third leaf-shape that decomposes into
named child Bounds — the renderer's `apply_composite` knows
how to walk it. See §3.2.)

### 3.1 Strict mode vs compat mode

The resolver runs in two modes:

- **Strict mode**: any error of `kind ≠ KIND_FONT_UNAVAILABLE`
  aborts the IR build. `ResolveResult.ir is None`. Used for
  the demo path, merge gates, and the cutover gate.
- **Compat mode**: every error becomes a `PlaceholderNode`
  inserted at the failure site. The IR is always non-None.
  The placeholder carries the `ResolveError` so downstream
  rendering can decide to (a) emit a wireframe placeholder,
  (b) emit a no-op, or (c) refuse — but every screen
  produces SOME script. Used for the W4 byte-equivalence
  telemetry across the 204-screen corpus.

This split was missing in v1. Without it, `render_figma_compat`
can't accumulate divergence telemetry across screens that
have any unresolved input — which is most of them in early
weeks. Codex flagged this as critical.

```python
def resolve(
    ast: L3Document,
    catalog: DesignSystemCatalog,
    *,
    mode: Literal["strict", "compat"] = "strict",
) -> ResolveResult:
    """Returns (ir, list[ResolveError]). ir is None only in
    strict mode when errors occurred; otherwise always present
    (with placeholders in compat)."""
```

### 3.2 The IR — invariants R1-R8

Frozen dataclasses with slots, hashable, structurally equal.
The eight invariants:

- **R1**. Leaf values: `Literal[T] | TokenBinding[T] | Composite | None`.
  None = absent.
- **R2**. Comp-ref nodes carry `component_key: str`, not paths.
- **R3**. Variant selections are enum-typed against the
  catalog's known axes.
- **R4**. Path overrides rewritten as addressed overrides
  on specific descendants.
- **R5**. Token refs survive: `TokenBinding.token_path`
  always set, `resolved_literal` always present (renderer
  fallback when live-binding fails), `figma_variable_id`
  populated when known.
- **R6**. **No reference** to L3Document, spec dict,
  db_visuals, or any side-car. Resolver consumes `(ast,
  catalog)` only. Catalog includes `instance_baselines`
  (the data v1 leaked via `db_supplements`).
- **R7**. **TokenBinding carries the resolution chain**, not
  just a terminal path. `resolution_chain: tuple[str, ...]`
  records the alias trail (e.g., `("color.action.primary",
  "color.brand.blue.500")`). Renderer's
  `figma_variable_id` lookup uses the leaf, displays the
  surface name.
- **R8**. **Every node carries `resolved_at_pass: int`
  provenance**. Debugging "why did this end up Literal not
  TokenBinding" must be tractable.
  `placeholder_reason: Optional[ResolveError]` is set on
  PlaceholderNodes from compat mode, None elsewhere.

### 3.3 Type structure (paste-ready)

```python
@dataclass(frozen=True, slots=True)
class Literal(Generic[T]):
    value: T
    source: Literal["author", "catalog-default", "db-extract", "inferred"]
    resolved_at_pass: int  # R8

@dataclass(frozen=True, slots=True)
class TokenBinding(Generic[T]):
    token_path: str            # surface (what the agent wrote)
    scope_alias: Optional[str]
    resolution_chain: tuple[str, ...]  # R7 — alias trail
    resolved_literal: T        # always present — renderer fallback
    figma_variable_id: Optional[str]  # populated when known
    resolved_at_pass: int      # R8

@dataclass(frozen=True, slots=True)
class Composite:
    """Multi-axis leaf where each axis is independently
    bound. Used for cornerRadius (4 corners), constraints
    (h+v), padding (4 sides), sizing (h+v), etc."""
    kind: Literal["corner_radii", "constraints", "padding",
                  "sizing", "alignment"]
    components: dict[str, "Bound"]   # axis → Bound[T]
    resolved_at_pass: int

Bound = Union[Literal[T], TokenBinding[T], Composite]
```

Domain leaves: `Color`, `Length`, `FontFamily`, `Shadow`,
`Stroke`, `Fill`, `GradientStop`, `Sizing` (Composite-shaped),
`Padding` (Composite-shaped), `AutoLayout`,
`VariantSelection`, `ComponentInstanceRef`,
`InstancePropertyOverride`, `AddressedOverride`,
`TextContent`, `ResolvedNode`, `PlaceholderNode`,
`NodeProvenance`, `ResolvedFigmaIR`.

(See `dd/resolved_ir.py` after Agent T1 ships day 1.)

**Test scaffolding**: `tests/_factories/resolved.py` — every
leaf type has a factory with `Partial[T]` overrides per
CLAUDE.md test-data conventions. Schemas come from the
dataclasses themselves; never redefined in tests.

### 3.4 The resolver — corrected pass ordering

The resolver runs **seven** ordered sub-passes (was six in
v1). The change: **token resolution moves earlier** because
variant args, comp-ref paths, and path-override targets can
themselves contain TokenRefs, and the v1 ordering caused
spurious `KIND_VARIANT_INVALID` errors when value was an
unresolved TokenRef.

The corrected ordering:

1. **`pass_1_type_check`** — every node head has a known type
   (catalog-listed). No reference resolution yet.
2. **`pass_2_resolve_tokens`** *(was pass 4)* — every
   `TokenRef` in `node.head.properties`, `PathOverride.value`,
   `SlotFill.text`, **variant args**, **comp-ref path
   segments** → `TokenBinding[T]`. Emits
   `KIND_TOKEN_UNKNOWN` / `KIND_TOKEN_TYPE_MISMATCH`.
3. **`pass_3_resolve_paths`** *(was pass 2)* — every comp-ref
   path → `ComponentKeyEntry`. Now sees fully-resolved
   strings. Emits `KIND_PATH_UNRESOLVED`.
4. **`pass_4_resolve_variants`** *(was pass 3)* — variant
   args validated against `entry.variant_axes`. Now sees
   resolved string values. Emits `KIND_VARIANT_INVALID` /
   `KIND_VARIANT_MISSING_REQUIRED`.
5. **`pass_5_rewrite_path_overrides`** — every `PathOverride`
   becomes an `AddressedOverride` on a specific descendant.
   Emits `KIND_PATH_OVERRIDE_TARGET_MISSING`.
6. **`pass_6_assemble`** — build `ResolvedNode` tree, fill
   provenance, dedup font manifest, dedup
   `component_keys_used` set. **Strict-mode boundary check**:
   for every node, assert that any `head.property` whose AST
   value was a `TokenRef` resolved to a `TokenBinding` (R5
   + R7 enforcement). Emit `KIND_TOKEN_DROP_INTERNAL` if
   not — this is a resolver bug, not user input, and aborts.
7. **`pass_7_emit_or_placeholder`** — strict mode: collect
   errors from passes 1-5, abort if any non-soft errors;
   compat mode: replace nodes whose ancestors collected
   errors with `PlaceholderNode(error: ResolveError)`. Emit
   final `ResolvedFigmaIR`.

(Pass 7 is new in v2. v1 collapsed it into pass 6, which
made strict/compat mode-switching ad-hoc.)

### 3.5 Coexistence period

Both renderers live in tree for the entire 6-7 weeks:

```
[ AST (L3Document) ]
       │
       ├──── (legacy)  ──> _spec_elements / _spec_tokens / db_visuals
       │                    └──> render_figma   ──> script_legacy
       │
       └──── (new)     ──> resolve(ast, catalog, mode="compat")
                            └──> ResolvedFigmaIR
                                  └──> render_figma_v2  ──> script_v2
```

A bridge harness `dd/render_compat.py::render_figma_compat(...)`
accepts the legacy signature, runs both paths, computes a
**rendered-property diff** (not script byte-diff — see W4
update below), returns the legacy script (so production
behavior is identical), and logs every divergence to
`render_compat_diff.jsonl`.

`dd generate` and `dd design --render-to-figma` are switched
to `render_figma_compat` from week 2 (after W0+W1 land).
They keep emitting the legacy script. We accumulate
divergence telemetry **without bearing the risk**.

**Daily compat-diff CI summary** runs from day 1 of W4
(week 2). Any non-zero per-screen diff is a yellow flag,
investigated immediately. v1 silently accumulated divergence
until cutover; this CI summary surfaces drift early.

Cutover is three commits, with a ≥7-day dwell between #1
and #2-3:

1. `render_figma_compat` flips to return `script_v2`. CI runs
   smoke + nightly continuously for 7 days. Any
   regression = revert.
2. After 7 clean days: legacy code path tagged
   `pre-v0.4-cutover` for rollback reference.
3. Legacy delete. Separate PR. Not in same release.

If #1 fails on demo recording day, revert is trivial (one
commit). If #3 ships and a regression surfaces, `git revert
+ tag-restore` is the recovery.

### 3.6 Why this shape

- **It collapses six patches into one pass with explicit
  provenance.** v1 had separate fixes for `ast_to_element`
  TokenRef drop, variant-render rebind wiring, path→key
  resolver, typography binding, etc. All of those become
  consequences of "the resolver builds Bound[T] with R5-R8
  enforcement; the renderer can't consume anything else."
- **It makes regressions provable AND debuggable.**
  R7 (resolution chain) + R8 (per-pass provenance) mean any
  Bound value carries enough info to answer "why did this
  end up here" — solving the v1 critique that the IR was
  correct but unobservable.
- **It separates strict (gate) from compat (telemetry).**
  Strict mode is the bar to clear; compat mode is the
  microscope. v1 conflated them and made early-week
  telemetry impossible.
- **It matches the project's own pitch.** "Compiler" implies
  one IR with invariants. v0.4 ships that.

---

## 4. Workstreams

Nine workstreams, lettered W0-W8. (W0 is new in v2.)

### W0 — Pre-flight foundation

**Files**: `tests/_pre_flight/`, `Dank-Test-v0.4.fig` (Figma
file, not in repo), `tools/dd-test-fixture-create.py`.

**Owns**: Three independently-blockable pieces that v1
silently assumed were already done:

**W0.A — Demo screen verification.** Subagent queries the DB
to confirm:
- Screen 333 (Profile) has a `button/large/translucent`
  INSTANCE bound to `color.action.primary` with a
  tap-state variant axis
- Screen 217 (Cart) has `color.feedback.success` defined
  in tokens, and a cart-totals row that can accept an
  appended banner
- Screen 091 (Confirmation) has a chip-typed node in
  scope
- Screen 412 (Settings) library has `list-row/destructive`
  with `{size: lg, leading: icon, trailing: chevron}`
  variant axes

If any verification fails: REVISE the demo script (§11)
before any code lands. Block all subsequent workstreams
until W0.A is green.

**W0.B — MCP-verify queryability probe.** For each demo's
verify-command, run it against a hand-prepared fixture node
through `figma_execute` and confirm the assertion shape is
queryable. v1 asserted these as if pre-flight verified; they
weren't. ~half a day.

**W0.C — `Dank-Test-v0.4` file creation.** A clone of Dank
Experimental's component library subset, on a single
`Test/v0.4` page seeded with ~200 components covering all
variant axes the demos use. Versioned. Reproducible setup
script in `tools/dd-test-fixture-create.py`. ~2-4 days of
Figma + ops work.

**Size**: 3-4 days total. Coordinator owns; some pieces
delegable to subagents.

**Blocks**: every other workstream. Phase 1 doesn't start
until W0.A and W0.B are green.

### W1 — ResolvedFigmaIR types

**File**: `dd/resolved_ir.py` (new, ~700 LOC after R7+R8 +
Composite leaf).

**Owns**: The full type definition for the new IR. Frozen
dataclasses with slots, hashable, structurally equal. R1-R8
enforced.

**Test scaffolding**: `tests/_factories/resolved.py` — every
leaf type has a factory with `Partial[T]` overrides.

**Size**: 4 days. ~700 LOC + ~500 LOC factories. (v1 said
3 days; R7+R8+Composite+placeholder add real surface.)

**Blocks**: W0. **Unblocks**: W2, W3, W4.

### W2 — Resolution pass

**File**: `dd/resolve.py` (new, ~1500 LOC after pass 7 and
mode dispatch).
Plus `dd/resolve_loader.py` (catalog assembly from DB),
`dd/resolve_props.py` (head-property → element-axis mapping,
lifted from `ast_to_element.py`).

**Owns**: The seven-sub-pass resolution pipeline. Strict and
compat modes. R7 resolution chains. R8 per-pass provenance
stamps. Pass-6 internal-consistency boundary check
(KIND_TOKEN_DROP_INTERNAL).

**Catalog shape** (incorporating v1's `db_supplements` as
`instance_baselines`):

```python
@dataclass(frozen=True)
class DesignSystemCatalog:
    component_keys: dict[str, ComponentKeyEntry]
    types: dict[str, CatalogTypeEntry]
    tokens: dict[str, ResolvedTokenValue]
    master_descendants: dict[str, dict[str, str]]
    instance_baselines: dict[str, "BaselineProperties"]  # NEW
    # eid → ground-truth properties for Mode-1 instances the
    # agent didn't author. Replaces v1's db_supplements
    # side-channel; now part of the catalog contract,
    # consumed during pass 5.
```

Loader `build_catalog_from_db(conn) -> DesignSystemCatalog`
is the **only** place SQL touches resolution (per
`feedback_boundary_contract.md`). Resolver remains pure
over `(ast, catalog, mode)`.

**Error taxonomy** (`ResolveError`):

```python
KIND_TOKEN_UNKNOWN
KIND_TOKEN_TYPE_MISMATCH
KIND_TOKEN_DROP_INTERNAL       # NEW — pass 6 boundary check
KIND_PATH_UNRESOLVED
KIND_VARIANT_INVALID
KIND_VARIANT_MISSING_REQUIRED
KIND_INSTANCE_PROP_UNKNOWN
KIND_INSTANCE_PROP_TYPE_MISMATCH
KIND_PATH_OVERRIDE_TARGET_MISSING
KIND_LEAF_HAS_CHILDREN
KIND_TYPE_UNKNOWN
KIND_FONT_UNAVAILABLE          # soft warning
KIND_SLOT_REQUIRED_EMPTY
KIND_RESUME_DRIFT              # NEW — for v0.3 session resume
```

Each error carries `eid`, `property`, `detail`,
`suggestion` (e.g., "did you mean color/primary/600?"),
and `ast_node_id` (id(Node) for caller to highlight).

**Size**: 14 days. Critical path. ~1500 LOC + ~1800 LOC
tests. (v1 said 12; pass 7 + mode dispatch + R7 chains add
real complexity.)

**Blocks**: W1. **Unblocks**: W3 E2E equivalence, W6.

### W3 — Renderer v2

**File**: `dd/render_figma_v2.py` (new, ~1700 LOC).

**Owns**: Pure renderer that consumes only `ResolvedFigmaIR`
+ `ComponentKeyRegistry`.

```python
def render_figma_v2(
    resolved: ResolvedFigmaIR,
    ckr: ComponentKeyRegistry,
    *,
    page_name: Optional[str] = None,
    canvas_position: Optional[tuple[float, float]] = None,
) -> RenderResult:
    """Pure function. Reads ONLY resolved + ckr."""
```

**Three-method contract** (was two in v1):

```python
class FigmaEmitter:
    def apply_literal(self, var, prop, value: Literal[T]) -> list[str]: ...
    def apply_bound(self, var, prop, bound: TokenBinding[T]) -> list[str]: ...
    def apply_composite(self, var, prop, composite: Composite) -> list[str]: ...
```

`apply_bound` decides between live-binding (when
`figma_variable_id` is present and CKR confirmed) vs
literal-then-rebind (the v0.2 path). Token rebind entries
emit as a side effect into `RenderResult.token_refs`.

`apply_composite` decomposes into per-axis Bounds and
re-dispatches each. cornerRadius's four corners,
constraints' h+v, padding's four sides — all dispatched
through this single method.

`PlaceholderNode` (compat mode only) emits a wireframe
placeholder + `__errors.push({kind, eid, ...})` so downstream
tools see the failure shape.

**Size**: 12 days, concurrent with W2 (with W1's factories
as the seam between them). ~1700 LOC + ~1000 LOC tests.

**Blocks**: W1. **Unblocks**: W4.

### W4 — Compat / equivalence

**Files**: `dd/render_compat.py` (new, ~300 LOC),
`tests/test_v2_v1_equivalence.py` (the gating test),
`tools/compat-diff-summary.py` (daily CI summary).

**Owns**: The bridge wrapper that runs both paths, computes
a rendered-property diff (NOT script byte-diff, NOT raw
property-set diff — see below), returns legacy script
during the transition, accumulates divergence telemetry,
emits a daily CI summary.

**The diff algorithm — rendered-property semantic diff**:

v1 said "AST-walk both scripts, compute property-set diff."
Codex flagged: ordering, side-effectful operations
(rebind), float formatting, list ordering (fills/effects)
all break naive property-set diffs even when the rendered
output is equivalent.

Replacement: **diff the WALKED rendered tree**, not the
script. Both paths emit a script + can be walked via the
existing `walk_ref.js` machinery. The compat wrapper:

1. Emits `script_legacy` and `script_v2`.
2. (In CI / dev) walks both via the bridge → two
   `rendered_ref` payloads.
3. Computes structural property diff with documented
   tolerances:
   - Float comparisons: `abs(a - b) < 0.001` (one-thousandth
     of a pixel)
   - Color: `delta_e76(a, b) < 0.5` (visibly identical)
   - List ordering: bag-equality for fills/effects; ordered
     equality for children/auto-layout
   - Placeholder nodes (compat): excluded from comparison
4. Outputs `tests/.fixtures/v2_v1_diff.jsonl` per screen
   with shape:
   ```json
   {"screen_id": 333, "eid": "btn-save",
    "only_in_old": {"fills": [...]},
    "only_in_new": {},
    "tolerable": [], "intolerable": []}
   ```

**Cutover gate**: `intolerable.length == 0` across the
**baseline-204 set** (see §10 for baseline definition;
not all 204 screens are in baseline because of pre-existing
walk_failed / drift screens).

**Daily CI summary**: runs nightly from week 2 onwards.
Non-zero `intolerable` triggers a yellow alert, investigated
within 48 hours. This is the change v1 missed.

**Two execution modes**:
- **Per-commit smoke**: rendered-property diff on the
  4-fixture smoke set (Dank-Test-v0.4 file). ~10 minutes.
  Gates merge.
- **Nightly full**: rendered-property diff on the
  baseline-204 set (Dank Experimental). Gates next-day work.

**Size**: 6 days, mostly waiting on W2 + W3. ~300 LOC core
+ ~700 LOC tests + ~150 LOC summary tool.

**Blocks**: W2 + W3. **Unblocks**: cutover gate.

---

## §5-§15 — REVISING

The following sections still reflect v1 framing. They are
flagged for v2 revision pass, currently in progress.

[V1 — REVISING] §5 Bridge constraint mitigation —
**will be subsumed into W0.C in v2.**

[V1 — REVISING] §6 Tests — **will gain cassette/replay
tier for cost; reduce per-commit suite from 12 to ~4 fixtures;
formalize $0.50-2.00 per CI cost band; add verb-selection-rate
metric.**

[V1 — REVISING] §7 Existing codebase touchpoints — **needs
addition of session-resume migration (KIND_RESUME_DRIFT
handling); needs `dd design log --panel` flag for §11 panel
surface.**

[V1 — REVISING] §8 Phasing — **revising to 6-7 weeks honest;
W0 added as week-0; W2/W3 honestly span 2.5-3 weeks each
overlapping; W5 retargeted to today's producers.**

[V1 — REVISING] §9 Parallel-agent execution — **adding
commit-hash pinning of plan-v0.4.md in subagent prompts;
clarifying review pattern as "audit checklist + reproduction
artifacts" not "PR review."**

[V1 — REVISING] §10 Verification gates — **204/204 absolute
gate replaced with baseline-delta gate; daily compat-diff
yellow-flag mechanism added.**

[V1 — REVISING] §11 Demo deliverables — **edited-recording
disclosure; failure budget per demo; interim status demo at
end of Phase 1; panel via `dd design log --panel`;
MCP-verify queryability handled in W0.B.**

[V1 — REVISING] §12 Risk register — **adding R8 (provenance
loss), R9 (cache-bust on per-turn enums), R10 (brand-literal
false positive), R11 (verb-selection regression).**

[V1 — REVISING] §13 Anti-scope — **mostly stable; small
clarification on `apply_render::rebuild_maps_after_edits`
ordering.**

[V1 — REVISING] §14 Inheritance from v0.3 — **stable.**

[V1 — REVISING] §15 References — **stable; will add R7+R8
references, links to compat-diff fixtures.**

Adding §16 Rollback policy (new in v2): the ≥7-day dwell
between cutover commits, the `pre-v0.4-cutover` tag, the
revert-and-restore recipe.

---

*v2 in progress. Architecture revisions (§1-§4 W4) above
reflect critique-pass integrations. Remaining sections
follow.*
