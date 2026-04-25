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

# Per-kind composite types — keys are typed, not open dict.
# Codex critique: open `dict[str, Bound]` lets apply_composite
# turn into ad-hoc per-prop logic. Closed enums per kind keep
# the contract honest.

@dataclass(frozen=True, slots=True)
class CornerRadii:
    top_left: "Bound[Length]"
    top_right: "Bound[Length]"
    bottom_left: "Bound[Length]"
    bottom_right: "Bound[Length]"
    resolved_at_pass: int

@dataclass(frozen=True, slots=True)
class Constraints:
    horizontal: Literal["MIN","MAX","CENTER","STRETCH","SCALE"]
    vertical:   Literal["MIN","MAX","CENTER","STRETCH","SCALE"]
    resolved_at_pass: int

@dataclass(frozen=True, slots=True)
class PaddingComposite:
    top: "Bound[Length]"; right: "Bound[Length]"
    bottom: "Bound[Length]"; left: "Bound[Length]"
    resolved_at_pass: int

@dataclass(frozen=True, slots=True)
class SizingComposite:
    horizontal: "Bound[Sizing]"
    vertical: "Bound[Sizing]"
    resolved_at_pass: int

@dataclass(frozen=True, slots=True)
class AlignmentComposite:
    main_axis: Literal["start","center","end","space-between","space-around","space-evenly"]
    cross_axis: Literal["start","center","end","stretch","baseline"]
    resolved_at_pass: int

Composite = Union[CornerRadii, Constraints, PaddingComposite,
                  SizingComposite, AlignmentComposite]

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
   segments** → `TokenBinding[T]`.

   **Expectation-set side effect** (Codex's clarification):
   pass 2 records, for every TokenRef occurrence, a tuple
   `(ast_node_id, property_path, composite_axis_or_None)`
   into a `binding_expectations: set[BindingExpectation]`
   that travels with the partial result. The pass-6 boundary
   check (below) uses this to assert "TokenRef-in =>
   TokenBinding-out" without re-walking the AST.

   Emits `KIND_TOKEN_UNKNOWN` / `KIND_TOKEN_TYPE_MISMATCH`.
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
   `component_keys_used` set.

   **Boundary check via expectation set**: for each
   `BindingExpectation` recorded by pass 2, look up the
   corresponding leaf in the assembled IR using
   `(ast_node_id, property_path, composite_axis)` and assert
   the leaf is `TokenBinding` (or a `Composite` whose named
   axis is `TokenBinding`). Emit `KIND_TOKEN_DROP_INTERNAL`
   if any expectation is unmet — this is a resolver bug
   (TokenRef silently coerced to Literal), not user input,
   and ALWAYS aborts (even in compat mode — bugs in the
   resolver itself are not "compat").
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

**Placeholder-coverage telemetry** (Codex's catch):
compat-mode placeholders are EXCLUDED from the rendered-
property diff (we can't compare a placeholder to a real
node). But they're tracked separately as
`placeholder_count` and `placeholder_area_ratio` per
screen in the JSONL. Cutover requires:
- `intolerable.length == 0` (no semantic divergence on
  rendered nodes)
- `placeholder_count == 0` on the baseline-204 set
  (every screen fully resolves in strict mode)

The placeholder-coverage metric is the safety net against
"diff looks clean because half the tree got placeholdered."

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

### W5 — Verifier extensions (retargeted)

**Files**: `dd/verify_figma.py` (extend), per-error fixtures.

**Owns**: Four new error kinds with producer + consumer
wiring. **Critical scope change from v1**: producers target
TODAY's code, not the future resolver/renderer.

v1 said "ship W5 first" but the proposed producers lived
inside the resolver/renderer that hadn't been built. Codex
flagged the chicken-and-egg. v2 retargets:

- **`KIND_VARIANT_FALLBACK`** — producer in TODAY's
  variant-axis selector path (`_emit_override_tree`'s
  swap target dispatcher). Fires *before* placeholder
  return so `M[key]` doesn't mask the error. Verifier
  downgrades `is_parity` on any occurrence.
- **`KIND_TOKEN_DROP`** — producer at TODAY's
  `ast_to_element` resolver boundary (the spot that
  currently silently returns None for TokenRef values).
  Plus a future producer at the W2 resolver (added when
  W2 ships). Hard parity break.
- **`KIND_PATH_UNRESOLVED`** — producer at the
  `figma.createFrame()` fallthrough in
  `render_figma_ast.py:1017-1059` where LLM-invented
  paths today silently degrade. Hard parity break.
- **`KIND_BINDING_REQUIRED_LITERAL`** — soft warning.
  Increments `binding_drift_count`. Threshold-gated, not
  parity-gated.

This way W5 ships in week 1 against today's producers,
catches regressions immediately, and gains the W2/W3
producers when they land without re-architecting.

**Size**: 5 days (was 4 in v1; adding today's-producer
wiring takes more grep + integration).

**Blocks**: nothing (independent of IR work).

**Unblocks**: every other workstream by surfacing failure
modes loudly during dev.

### W6 — Agent context (catalogs, ledger, instance awareness)

**Files**: `dd/agent/catalog_inject.py`, `dd/agent/annotate.py`,
`dd/agent/ledger.py` (all new).

**Owns**: Surface the design system to the agent.

**Per-turn token budget** (revised from v1 with cache reality):

| Block | Where | Bytes | Cacheable |
|---|---|---|---|
| System prompt | `system=` | ~3 KB | yes (ephemeral, session-stable) |
| Tool schemas with full session-scoped enum | `tools=` | ~5-8 KB | yes (ephemeral, session-stable) |
| Brief + iteration counter | user msg | ~300 B | no |
| Focused subtree (compressed L3) | user msg | ~2 KB | no |
| Reachable-tokens hint slice | user msg | ~800 B | no |
| Reachable-components hint slice | user msg | ~600 B | no |
| Instance annotations | user msg | ~600 B | no |
| Session ledger (in-scope view) | user msg | ~500 B | no |

**Tool-schema cache strategy** (Codex + ML pragmatist
critique): **enums are SESSION-SCOPED, not per-turn**. v1
made the cache-busting mistake of regenerating tool schemas
per turn with reachable-token enums. v2 builds the enum
ONCE per session from the full token catalog at session
boot; the per-turn user-message hint narrows the agent's
attention without changing the schema.

This means:
- Tool schemas tokenize once per session and cache cleanly
- The agent CAN emit any token in the catalog (full enum)
- The user-message hint says "these N tokens are most
  relevant for the current focus"
- Validation server-side: if the agent picks an out-of-
  catalog token, that's a hard error (the enum prevents it
  at the API level anyway)

**Realistic cost per iter** (revised from v1's $0.018):
~$0.04-0.06 per iter assuming 90% cache hit on system+tools
blocks. ~$0.30 for a 6-iter session. ~$2-4 for the smoke
suite.

**Reachable tokens** (filtering signal for the user-message
hint, not the schema enum):

```python
def reachable_tokens(conn, focus_doc, prop_class) -> list[TokenRow]:
    component_paths = walk_instances(focus_doc)
    eid_set = existing_eids(focus_doc)
    return conn.execute("""
        SELECT t.path, t.token_type, tv.resolved_value
        FROM token_uses tu
        JOIN tokens t ON t.id = tu.token_id
        JOIN token_values tv ON tv.token_id = t.id
        WHERE tu.component_path IN (?) OR tu.eid IN (?)
        GROUP BY t.path
    """, ...).fetchall()
```

**Component catalog** (from `dd/library_catalog.py:44`):

All ~30 components in a stable table, full enum in tool
schema, hint table in user message:
```
button/large/translucent
  variants: state ∈ {default, active, disabled, loading}
  slots: leading-icon, label, trailing-icon
  default-props: variant=default, fill={color.action.primary}
```

**Instance annotation** (A3):

```
### Instances in scope
@nav-toolbar-3   button/large/translucent · state=default
                 fill -> color.action.primary
                 leading-icon: @icon-22
@btn-save        button/large/solid       · state=disabled
```

**Session ledger** (the 4th leg) — with focus-scoping (ML
pragmatist's catch):

```python
@dataclass
class Ledger:
    # FULL session view — used for resume + post-hoc
    # analysis, never directly injected into agent context.
    global_tokens_committed: dict[str, list[str]]
    global_components_used: dict[str, list[str]]
    global_decisions: list[tuple[int, str]]

    # FILTERED view for current focus subtree.
    # Computed each turn. This is what the agent sees.
    in_scope_tokens_committed: dict[str, list[str]]
    in_scope_components_used: dict[str, list[str]]
    open_threads: list[str]   # bounded LLM-summary
```

Deterministic fields rebuilt from `move_log` table.
`open_threads` LLM-summarized once on session resume.

**Discriminated-union tool schemas** (in
`dd/structural_verbs.py:390`) — with stable session-scoped
enum:

```python
"value": {
    "oneOf": [
        {"type":"object","properties":{
            "kind":{"const":"literal"},
            "literal_value":{"type":"string"}
        },"required":["kind","literal_value"]},
        {"type":"object","properties":{
            "kind":{"const":"token_ref"},
            "token_path":{"type":"string","enum": all_tokens_in_session_for(prop_class)}
        },"required":["kind","token_path"]}
    ]
}
```

Server-side canonicalization in `apply_edits`: literal close
to token (color ΔE≤5, length within 2px) → reject with
`nearest_token` field UNLESS the value carries
`force_literal: true`.

**Brand-literal escape hatch** (ML pragmatist's catch):
agent can emit `{kind: "literal", literal_value: "#1F8A3D",
force_literal: true}` when the brief specifies a one-off
color. Verifier downgrades to soft-warning,
`KIND_BINDING_REQUIRED_LITERAL` increments
`binding_drift_count` for adjudication review. Default
behavior is reject; opt-in is the explicit literal.

**Adversarial verifier feedback loop**: agent gets
`rejection_kind: "literal_near_token"` next turn with
`nearest_token`, `delta`, `suggestion`. ~80B/turn. Empirical
convergence in 1 retry from prior testing.

**Verb-selection rate metric** (ML pragmatist's catch):
W6 includes a per-fixture metric — was the FIRST tool call
the right verb? Track per-fixture across phases.
**Regression-gate at 80%** (current Stage 1-3 baseline). If
adding catalogs + ledger DROPS verb selection, that's a
yellow flag.

**Size**: 7 days (was 5-6 in v1; ledger focus-scoping +
escape hatch + verb-selection-rate add real surface).

**Blocks**: nothing structurally; benefits from W5 error
kinds for adversarial feedback.

**Unblocks**: W7 (acceptance fixtures), W8 (demos).

### W7 — Acceptance fixture suite

**Files**: `tests/acceptance/fixtures/`,
`tests/acceptance/runner.py`,
`tests/acceptance/cassettes/`.

**Owns**: Three-tier fixture suite with cassette/replay for
cost (ML pragmatist + systems engineer's joint catch):

```
fixtures/
  smoke/         # 4 fixtures, runs per-commit (~$0 with cassette, ~$2 cold)
  nightly/       # 50 fixtures, runs nightly (~$5-15)
  weekly/        # 200 fixtures, runs weekly drift sweep
  schema_v1.json # tool_schema_hash pinned

cassettes/
  smoke/<fixture>.cassette.jsonl   # recorded Sonnet responses
  nightly/...                       # recorded for stability
```

**Smoke pins (4 fixtures, not 12)** — Codex critique on
v1 cost: 12 × per-commit was unviable. 4 fixtures pinned to
specific failure classes:

- 1 × append-INSTANCE-with-bound-token (the M2-fail fixture)
- 1 × set-token-on-existing-instance (Demo A shape)
- 1 × variant-axis-selection (Demo D shape)
- 1 × adversarial-literal-near-token (Demo C shape)

Each smoke fixture runs against a recorded cassette by
default. CI cost: ~$0. Re-record cassettes on schema-hash
bump or weekly cadence: ~$0.50/regen.

Live-Sonnet runs only at nightly tier (50 fixtures × $5-15)
and weekly drift sweep (200 fixtures × $20-60). Phase gates
use nightly results, not smoke.

**Schema-hash mechanism**:
`dd/edit_grammar/schema.py::compute_tool_schema_hash()`
produces sha256 over the verb JSON-Schema. Fixture loader
verifies `expected.tool_schema_hash == current_hash` —
mismatch = test SKIP with `STALE_FIXTURE` error, forcing
fixture regen via `dd regen-fixtures`. CI fails on >2 stale
fixtures.

**Re-recording owner**: Coordinator. Triggered by phase-
gate transitions or schema bumps. Documented in `tools/
dd-regen-cassettes.sh` with explicit invocation.

**Verb-selection-rate metric**: each fixture asserts the
expected first verb. Aggregate rate gates Phase 3.

**Realistic cost band**: $0.50-2.00 per CI run with cache,
$5-15 nightly, $20-60 weekly. Monthly: ~$200-700. Plan
acknowledges this; budget approval is a project-level
decision.

**Size**: 5 days (was 4; cassette infrastructure adds work).

**Blocks**: W6 (need agent context + tool schemas).
**Unblocks**: continuous regression catch.

### W8 — Demo deliverables

**Files**: `demos/A.txt` etc., `demos/run.sh`,
`demos/RECORDING_NOTES.md`.

**Owns**: Four kill-shot demos (§11) with edited-recording
disclosure, failure budget per demo, panel via
`dd design log --panel` flag.

**Panel surface** (demo strategist's catch): the
instrumentation panel doesn't need to be a UI build. v2
adds a `--panel` flag to `dd design log` that emits a
two-column markdown showing prop ← bound-variable per
agent-edited node. Cheap, ties to existing surface,
screenshot-friendly for video. Adds ~1 day of work to W6
(the ledger emit code already has the data).

**Failure budget per demo**: each demo includes a fallback
narrative if the agent picks an unexpected verb or the
bridge flakes mid-demo. Documented in
`demos/RECORDING_NOTES.md`. Pre-record all four; live-
record one as cinema.

**Edited-recording disclosure**: §11 explicitly states
"recordings are edited; full unedited capture available."
This isn't a defect — it's an honesty convention that
preserves credibility.

**Size**: 4 days, last week (was 3 in v1; adding panel +
failure-budget docs).

**Blocks**: W3, W6, W7. **Unblocks**: Loom recording.

---

## 5. (consolidated into W0.C above — no separate section)

## 6. Tests

Layered architecture, behavior-first per CLAUDE.md.

**A. Resolver pure unit tests**
`tests/test_resolve_passes.py` — one suite per sub-pass.
Hand-built `L3Document` + `DesignSystemCatalog` from
factories. Every `KIND_*` error has at least two tests
(positive trigger + lookalike that should NOT trigger).
**Plus pass-6 boundary check tests**: hand-build inputs
that trigger `KIND_TOKEN_DROP_INTERNAL` (the resolver-bug
detector).

**B. Resolver integration tests**
`tests/test_resolve_integration.py` —
`parse_l3(source) → resolve(ast, catalog) → ResolvedFigmaIR`
on small hand-written L3 fixtures
(`tests/fixtures/resolve/*.dd`). Asserts IR shape.
**Both modes tested** (strict + compat).

**C. v2 renderer pure tests**
`tests/test_render_figma_v2.py` — feed hand-built
`ResolvedFigmaIR` to `render_figma_v2`. Assert script
structure. No DB. **Three-method dispatch tested**:
explicit cases for apply_literal, apply_bound,
apply_composite per leaf type.

**D. End-to-end equivalence (THE GATING TEST)**
`tests/test_v2_v1_equivalence.py` — for each screen in
the **baseline-204 set** (see §10):
```python
old = render_figma(ast, conn, nid_map, _spec_elements=..., ...)
ir  = resolve(ast, build_catalog_from_db(conn), mode="compat")
new = render_figma_v2(ir, ckr_from(conn))
# Walk both via bridge, compute rendered-property diff
assert diff.intolerable.length == 0
assert ir.placeholder_count == 0  # in strict mode
```
Slow. Gate behind `pytest -m parity_baseline`. Run on CI
nightly.

**E. Adversarial resolver tests**
`tests/test_resolve_adversarial.py` — synthesize
`L3Document`s the agent might produce that should hard-fail
in strict mode and produce placeholders in compat mode.
Each `KIND_*` error has a fixture for both modes.

**F. Property-based round-trip**
`tests/test_resolve_inverse.py` — for a generated
`ResolvedFigmaIR`, build a synthetic `L3Document` that the
resolver should produce exactly that IR for. Uses
`hypothesis`.

**G. Acceptance smoke (per-commit)**
4 fixtures × cassette replay. ~$0 with cache, ~$2 cold.
~3-5 min. Gates merge to main.

**H. Acceptance nightly**
50 fixtures × live Sonnet. ~$5-15. Gates next-day work.

**I. Acceptance weekly**
200 fixtures × live Sonnet × Dank Experimental directly.
Drift sweep. NOT a merge gate.

**J. Verb-selection rate**
Per-fixture metric. Aggregate gate >=80% (Stage 1-3
baseline). Surfaced in nightly summary.

---

## 7. Existing codebase touchpoints

| Path | What happens |
|---|---|
| `dd/resolved_ir.py` | NEW (W1) |
| `dd/resolve.py` | NEW (W2) |
| `dd/resolve_loader.py` | NEW (W2) |
| `dd/resolve_props.py` | NEW (W2, lifted from `ast_to_element.py`) |
| `dd/render_figma_v2.py` | NEW (W3) |
| `dd/render_compat.py` | NEW (W4) |
| `dd/agent/catalog_inject.py` | NEW (W6) |
| `dd/agent/annotate.py` | NEW (W6) |
| `dd/agent/ledger.py` | NEW (W6) |
| `dd/verify_figma.py` | EXTEND (W5) — add 4 KINDs against TODAY's producers |
| `dd/structural_verbs.py:390` | MODIFY (W6) — discriminated-union schemas, session-stable enum |
| `dd/agent/loop.py:586` | MODIFY (W6) — system prompt with cached catalog block |
| `dd/agent/loop.py:269` | MODIFY (W6) — reachable hint slices in user msg |
| `dd/sessions.py:297` | EXTEND (W5) — coverage payload in move_log; KIND_RESUME_DRIFT handling |
| `dd/cli.py:2102+2704` | MODIFY (W4 cutover) — call `render_figma_compat` |
| `dd/cli.py` | MODIFY (W6/W8) — `dd design log --panel` flag |
| `dd/compose.py:1546` | MODIFY (W4 cutover) — call `render_figma_compat` |
| `dd/apply_render.py:537+560` | MODIFY (W4 cutover) — call `render_figma_compat` |
| `dd/render_figma_ast.py` | UNCHANGED until cutover, DELETED at end |
| `dd/renderers/figma.py` | UNCHANGED until cutover, DELETED at end |
| `dd/ast_to_element.py` | DEPRECATED at cutover (helpers lifted to `resolve_props.py`) |
| `dd/markup_l3.py` | UNCHANGED |
| `dd/extract_*` | UNCHANGED (catalog reads existing tables) |
| `dd/apply_render.py::rebuild_maps_after_edits` | DEPRECATED at v0.4.1 (separate cleanup, post-demo) |

**Session-resume migration** (compiler architect's catch):
v0.3 sessions persisted with the old `ast_to_element` may
not re-resolve identically through the new resolver.
`dd design --resume <vid>` adds a first-iter check: run
the new resolver in compat mode, compute
`dropped_props_count` against what the persisted variant
implied. Non-zero = `KIND_RESUME_DRIFT` warning to user.
User can choose to continue or restart the session.

---

## 8. Phasing

Six phases, end-of-week milestones. (v1 had 4; v2 honestly
spans 6-7 weeks, with W0 added.)

### Phase 0 — Pre-flight (week 0)

**Workstreams active**:
- W0.A demo-screen DB verification
- W0.B MCP-verify queryability probe
- W0.C `Dank-Test-v0.4` file creation

**Phase gate**:
- All four demo screens (333, 217, 091, 412) DB-verified
- All four demos' MCP-verify commands probe-tested
- `Dank-Test-v0.4` created, versioned, reproducible setup
  script committed
- Plan v0.4 commit-hash pinned in subagent dispatch
  templates (§9)

**Stop-condition revise** if:
- Any demo screen lacks the cited structural property —
  REVISE §11 demos before any code lands
- `Dank-Test-v0.4` setup takes >4 days — revisit scope

### Phase 1 — Foundation (week 1)

**Workstreams active**:
- W1 (types) — full
- W5 (verifier extensions retargeted to today's producers) — full
- W7 — start writing failing cassette-replay tests

**Phase gate**:
- `dd/resolved_ir.py` with R1-R8, three Composite leaves,
  PlaceholderNode; mypy clean
- Four new `KIND_*` constants land in `dd/verify_figma.py`;
  each has a smoke fixture that triggers correctly against
  TODAY's code
- ≥8 W7 invariant tests fail with **specific KIND_* assertions**
  (not "fail for the right reasons" — explicit kinds)
- **Interim status demo** recorded — 2-minute scope-honest
  Loom for Anthropic stakeholders explaining current
  capability + the gap being closed

**Stop-condition revise** if:
- W1 takes >5 days (signals types are wrong)
- W5 KINDs don't surface reliably against today's
  producers

### Phase 2 — Resolver produces ResolvedFigmaIR (weeks 2-3)

**Workstreams active**:
- W2 (resolver) — full, both modes
- W3 (v2 renderer) — start (concurrent with W2)
- W6 — wave A: catalog injection, instance annotation,
  ledger (session-stable schema enums)
- W7 — expand fixtures

**Phase gate**:
- Resolver passes 1-7 implemented; all `KIND_*` errors
  have unit tests
- `KIND_TOKEN_DROP_INTERNAL` boundary check passes on
  hand-built fixtures
- Both strict and compat modes tested
- Token rate >0% on smoke suite (agents see the catalog)

### Phase 3 — Renderer parity + agent fluency (weeks 3-4)

**Workstreams active**:
- W3 — full
- W4 (compat) — full, with daily CI summary running
- W6 — wave B: discriminated-union tool schemas,
  adversarial feedback, escape hatch
- W7 — full smoke + nightly suites

**Phase gate**:
- `render_figma_compat` runs both paths and reports
  divergence; daily CI summary live
- 3 end-to-end fixtures: agent → resolver → v2 renderer →
  Figma; INSTANCE + token bindings + typography all visible
- Token rate >50% on smoke
- KIND_TOKEN_DROP rate <5% per session
- Verb-selection rate >=80% (no regression from baseline)

### Phase 4 — Pre-cutover stabilization (week 5)

**Workstreams active**:
- W3 + W4 — close out divergences
- W7 — gate baseline-204 nightly

**Phase gate**:
- `intolerable.length == 0` across baseline-204
- `placeholder_count == 0` on baseline-204 (strict mode)
- 7 consecutive nights of clean nightly runs
- All four demos pre-recorded with failure-budget
  fallbacks

### Phase 5 — Cutover + demos (week 6, week 7 buffer)

**Workstreams active**:
- W4 cutover commit #1 (compat-flips-to-v2)
- 7-day dwell observation
- W4 cutover commit #2 (tag pre-v0.4-cutover)
- W4 cutover commit #3 (legacy delete) — separate PR,
  separate week
- W8 — demos final pass

**Phase gate**:
- All four kill-shot demos pass on fresh clone
- 0 silent-drop regressions in dwell period
- Loom recording captures all four demos + interim
  status

---

## 9. Parallel-agent execution pattern

This plan executes via multi-agent delegation with the
coordinator (the next session) writing synthesis,
critical glue, and code where measurement matters.

### Plan-version pinning

**Critical addition from v1 critique**: every subagent
dispatch includes the commit-hash of `plan-v0.4.md` at
dispatch time. The subagent's first action is to re-read
the plan at that hash and proceed against it. If the plan
mutates between dispatch and review, A and B work on
different versions silently. The coordinator pins.

### Five concurrent threads

| Thread | Agent | Owns | Contract (the seam) |
|---|---|---|---|
| **T0: Pre-flight** | Subagent fanout | W0.A, W0.B, W0.C | DB queries + MCP probes + Figma file setup |
| **T1: Types** | Sonnet | `dd/resolved_ir.py` + factories | After day 1, signature is fixed; further changes need explicit T1 sign-off |
| **T2: Resolver** | Sonnet | `dd/resolve.py`, `dd/resolve_loader.py`, `dd/resolve_props.py`, tests | Consumes T1's types. Produces a callable that round-trips factories |
| **T3: Renderer v2** | Sonnet | `dd/render_figma_v2.py`, tests | Consumes T1's types. Builds against fake `ResolvedFigmaIR` from T1's factories |
| **T4: Compat / equivalence** | Sonnet | `dd/render_compat.py`, equivalence test, daily CI summary | Consumes T2 + T3. Wrapper-shape stub on day 1; equivalence test fills in once T2 + T3 land |
| **T5: Migration** | Sonnet | Call-site swaps in CLI/compose/apply_render | Independent of T2/T3 — only depends on T4's wrapper landing |
| **T6: Agent context** | Sonnet | W6 pieces (catalog inject, ledger, annotate) | Independent; reads existing DB tables |

### Review pattern (concrete, not aspirational)

v1 said "no agent reviews their own code." Subagents in
this harness can't actually do PR review. v2 prescribes the
real shape:

**Audit checklist + reproduction artifacts pattern**:

1. Builder agent ships code + a markdown `AUDIT.md` listing
   the invariants it claims to satisfy + the test files
   demonstrating each
2. Reviewer agent (separate session) reads `AUDIT.md`, runs
   the listed tests, attempts adversarial reproduction
   (e.g., "what input would break invariant R7?"), reports
3. Coordinator merges only if: (a) reviewer's tests pass,
   (b) reviewer's adversarial attempts surface no
   regressions, (c) coordinator agrees the audit checklist
   is complete

This is mechanical and executable in the actual harness.

### The "dispatcher → builders → reviewer" pattern

For high-leverage moments (especially the IR refactor):

1. **Dispatcher** (coordinator) writes failing test(s) that
   pin the contract. Commits.
2. **Builders** (2-3 subagents in parallel) implement
   minimal code to satisfy. Each works on a non-overlapping
   subset.
3. **Reviewer** (separate subagent or Codex) reads the
   builders' AUDIT.md files + tests; runs reproduction.
4. Coordinator merges only after reviewer signs off.

### Codex consult points

- **After each major merge in W1/W2/W3**: type errors across
  repo, dead-path detection, API ergonomics review
- **Design forks**: e.g., the W6 "should reachable filtering
  be in user-message hint or schema enum" decision (already
  made: hint, not enum)
- **The architecture audit at end of Phase 2**: is the
  resolver shape holding up, or do we need to redesign?
- **Cutover sign-off**: Codex reviews the
  `placeholder_count` + `intolerable` JSONL before either
  cutover commit ships

### Parallelization map for W6 (agent-side)

W6's seven pieces split into two waves:

**Wave A (parallel, week 2)**:
- Subagent: token-catalog injection (full enum + reachable hint)
- Subagent: component-catalog injection
- Subagent: instance annotation (A3)
- Subagent: session ledger (with focus-scoped view)

All four read existing DB tables; no IR dependencies.

**Wave B (parallel, week 4)**:
- Subagent: discriminated-union tool schemas with stable
  session-scoped enum
- Subagent: adversarial verifier feedback loop + escape hatch
- Subagent: `dd design log --panel` markdown output for §11
- Subagent: verb-selection-rate metric + nightly summary

### Parallelization map for W5 (verifier extensions)

Coordinator owns the KIND constants in `dd/verify_figma.py`
(producer + consumer must stay synced).

**Parallel subagents (one tool-call message)**:
- A: KIND_VARIANT_FALLBACK producer in TODAY's
  `_emit_override_tree` swap dispatch + smoke fixture
- B: KIND_TOKEN_DROP producer at TODAY's `ast_to_element`
  resolver boundary + smoke fixture
- C: KIND_PATH_UNRESOLVED producer at TODAY's
  `figma.createFrame()` fallthrough + smoke fixture
- D: Coverage instrumentation in `sessions.py` + `loop.py`
- E: Smoke fixture cassette infrastructure in
  `tests/acceptance/cassettes/`
- F: `Dank-Test-v0.4` setup script (W0.C)

Coordinator merges KIND additions into `verify_figma.py`
last, after all 4 producer PRs land — single integration
point keeps the consumer allowlist authoritative.

### Coordinator's role

The next session is not just dispatching. They write:

- The architectural decisions in commit messages and
  rationale docs
- Glue code at integration points where multi-agent output
  needs harmonizing
- The v2_v1 equivalence test (W4) — too critical to delegate
- The cutover commits — explicit, documented, gated
- Synthesis docs at phase boundaries (1-page status
  snapshots)

**Avoid delegating**:
- Type definitions in `dd/resolved_ir.py` (single coherent
  artifact)
- The cutover commit messages and gate verification
- Phase-gate go/no-go decisions
- The interim status demo at end of Phase 1

**Always delegate**:
- Single-pass resolver implementation (split across builders)
- Test fixture authoring (mechanical)
- Migration call-site swaps (mechanical)
- Bridge-environment setup scripts (mechanical)
- Cassette regeneration

---

## 10. Verification gates

Each phase has a numerical gate. Numerical when possible.

### The baseline-204 set (new in v2)

v1's "204/204 absolute gate" was uncomputable: 14 known-drift
screens + ~17% intermittent timeouts pre-existing.

v2 defines:
- **Baseline-204 set** = the 204 Dank-EXP-02 screens MINUS
  the 14 known-drift screens documented in
  `feedback_dank_corpus_drift_25.md` AT THE TIME OF v0.4
  KICKOFF. This becomes a snapshot in `tests/.fixtures/
  baseline_screens.json` committed at end of Phase 0.
- **Cutover gate**: delta against this baseline must be
  zero — not absolute count.

### Phase 0 gate
- All 4 demo screens DB-verified
- All 4 MCP-verify commands probe-tested
- `Dank-Test-v0.4` file exists, versioned, with setup script
- Baseline-204 snapshot committed

### Phase 1 gate
- `dd/resolved_ir.py` mypy-clean with R1-R8
- 4 new KIND_* constants land
- Smoke fixture per KIND triggers (against TODAY's code)
- ≥8 W7 invariant tests fail with explicit KIND_*
  assertions
- Interim status demo recorded

### Phase 2 gate
- Token rate >0% on smoke suite
- 0 cases where unresolved input renders without error
  (in strict mode)
- Resolver passes 1-7 implemented; pass-6 boundary check
  passes on hand-built fixtures
- Both modes (strict + compat) tested

### Phase 3 gate
- `render_figma_compat` runs; daily CI summary live
- Token rate >50% on smoke
- KIND_TOKEN_DROP rate <5% per session
- Verb-selection rate >=80% (no regression)
- Smoke 4/4 pass

### Phase 4 gate (PRE-CUTOVER)
- `intolerable.length == 0` across baseline-204
- `placeholder_count == 0` on baseline-204 (strict mode)
- 7 consecutive clean nightly runs
- Demos pre-recorded with failure-budget fallbacks

### Phase 5 gate (CUTOVER)
- Cutover commit #1 (flip) ships
- 7-day dwell observation passes
- Demos pass on fresh clone
- Loom recording captures all four + interim demo

---

## 11. Demo deliverables — kill-shots

Four demos, each ≤90s **edited wall-clock** (~2× displayed
time of unedited LLM latency), each answering a different
objection.

**Edited-recording convention** (demo strategist's catch):
Loom recordings are EDITED. Each cut between agent verb
dispatches removes ~5-10s of LLM round-trip latency. Full
unedited captures are committed alongside the edited
versions in `demos/raw/`. Audience is told this in the
Loom intro.

### Interim status demo (recorded at end of Phase 1)

**Title**: "Where we are, where we're going."

**Length**: 2 minutes.

**What it shows**: today's `dd design --brief` against a
real Dank screen, demonstrating that the EDIT loop runs
end-to-end with real Sonnet + bridge, BUT honestly framing
that the agent currently doesn't use the design system's
tokens or components. The next milestone (v0.4) closes
that gap.

**Why this exists**: Anthropic + design staff can't wait
6 weeks for an update. This buys 5 weeks of credibility
by being scope-honest about today's capability while
naming the gap.

### Demo A — DS-correct edit

**Title**: "The agent edits inside the design system, not
next to it."

**Objection**: "How do I know your output isn't a hex-coded
knockoff that looks like our DS?"

**Brief**: `"Increase the radius on the primary CTA in the
Profile screen to 12 and fix its tap state."`

**Pre-flight verified in W0.A**: Screen 333 has a
`button/large/translucent` INSTANCE bound to
`color.action.primary` with a tap-state variant.

**Failure budget**: if agent picks `replace` instead of
`set`, recording shifts to a pre-recorded golden run.
Documented in `demos/RECORDING_NOTES.md`.

**Agent verbs**:
```
emit_drill(@profile-cta) →
emit_set_edit(@profile-cta, {radius: 12}) →
emit_set_edit(@profile-cta, {variant.state: "pressed"}) →
emit_done
```

**Canvas**: same INSTANCE node id, `instance.componentId`
unchanged, `cornerRadius=12`, variant axis `state=pressed`,
fill still bound to `color.action.primary`. No detached
frame.

**Panel via `dd design log --panel`**:
```
cornerRadius ← (literal 12) ✓ within token scale
fill ← color.action.primary
typography ← typography.button
componentKey: 8a2f… (unchanged)
variant.state: default → pressed
```

**Why prompt+MCP can't**: Figma MCP `set_node` accepts hex;
nothing forces variant-axis routing or refuses to detach.
Our verifier rejects detach + KIND_PATH_UNRESOLVED gates
the variant swap.

**Kill-shot**: bottom-right of panel shows `componentKey:
8a2f…` unchanged before and after.

**Wall-clock unedited**: ~60s. **Edited**: ~30s.

### Demo B — Token-mutation propagation

**Title**: "Change the token, the agent's output changes.
No re-prompt."

**Objection**: "Couldn't an LLM just spit out the right hex
once?"

**Brief**: `"Add a success banner above the cart total."`

**Pre-flight verified in W0.A**: Screen 217 has
`color.feedback.success` defined.

**Failure budget**: token mutation propagation requires the
binding to be live in Figma at render-time, not deferred.
If propagation doesn't fire, recording shifts to pre-
recorded version.

**Agent verbs**:
```
emit_append(@cart-totals-row, banner_template) →
emit_set_edit(@new-banner, {fill: token_ref("color.feedback.success"), text_style: token_ref("typography.body.emphasized")}) →
emit_done
```

**Canvas**: banner renders green-bound. Operator opens
Figma Variables, edits `color.feedback.success` from
`#1F8A3B` → `#0E5C26`. Agent panel re-resolves; canvas
re-paints darker green with no agent call.

**Panel**: `fill ← color.feedback.success → resolved
#1F8A3B` then live-updates to `→ resolved #0E5C26` after
the variable edit.

**Why prompt+MCP can't**: existing tools emit literals.
There is no Bound[T] leaf; nothing for a token mutation to
propagate through.

**Kill-shot**: Figma Variables panel and our agent panel
visible side-by-side; operator changes the swatch and
within one frame both update. No CLI call.

**Wall-clock unedited**: ~75s. **Edited**: ~37s.

### Demo C — Self-correcting agent (adversarial verifier)

**Title**: "An LLM constrained by a type system."

**Objection**: "Agents hallucinate. Won't yours emit
`#1F8A3B` and call it a day?"

**Brief**: `"Match the success-state color used elsewhere in
the app for this confirmation chip."` (Vague to bait a
literal.)

**Pre-flight verified in W0.A**: Screen 091 has a chip-
typed node + `color.feedback.success` token within
ΔE=5 of the brief's intent.

**Failure budget**: if first-attempt emits the token
directly (no rejection), recording uses pre-recorded
version where rejection fires.

**Agent verbs**:
```
emit_set_edit(@chip, {fill: "#1F8A3C"}) →
[verifier rejects: KIND_TOKEN_DROP, nearest=color.feedback.success ΔE=0.4] →
emit_set_edit(@chip, {fill: token_ref("color.feedback.success")}) →
emit_done
```

**Canvas**: chip ends green, bound. Transcript shows
rejected first attempt, verifier message including
nearest-token suggestion, retried attempt.

**Panel**:
```
attempt 1: fill ← #1F8A3C ✗ KIND_TOKEN_DROP
                     (nearest: color.feedback.success ΔE=0.4)
attempt 2: fill ← color.feedback.success ✓
```

**Why prompt+MCP can't**: no adversarial verifier; the
literal would land. v0.4's gate is the constraint.

**Kill-shot**: visible verifier rejection line in the
transcript next to the corrected canvas.

**Wall-clock unedited**: ~100s. **Edited**: ~50s.

### Demo D — Compose with real components

**Title**: "New instance, right variant axis, slots filled —
from one sentence."

**Objection**: "Sure you can edit. Can you compose?"

**Brief**: `"Add a destructive 'Delete account' row to the
bottom of Settings."`

**Pre-flight verified in W0.A**: Screen 412 library has
`list-row/destructive` with the cited variant axes.

**Failure budget**: if `importComponentByKeyAsync` fails
or variant axis selection is wrong, recording shifts to
pre-recorded version.

**Agent verbs**:
```
emit_drill(@settings-list) →
emit_append(list_row_instance, {
  component_key: resolved_from_path("list-row/destructive"),
  variant: {size: "lg", leading: "icon", trailing: "chevron"},
  slots: {label: "Delete account", icon: icon.trash}
}) →
emit_done
```

**Canvas**: real INSTANCE node, axes correctly selected,
label slot filled, icon slot bound to `icon.trash`, fill
bound to `color.action.destructive`.

**Panel**:
```
componentKey: list-row/destructive (3c91…)
variant.size: lg
variant.leading: icon
variant.trailing: chevron
slot.label: "Delete account"
slot.icon ← icon.trash
fill ← color.action.destructive
```

**Why prompt+MCP can't**: requires path→component_key
resolver + slot-fill grammar + variant axis catalog.

**Kill-shot**: variant-axis chips in the panel light up
matching the rendered row.

**Wall-clock unedited**: ~110s. **Edited**: ~55s.

### Execution checklist (for v0.4 close)

| | A | B | C | D |
|---|---|---|---|---|
| **Pre-flight** | Dank-EXP-02 open on screen 333; clean session DB; bridge healthy | Screen 217 open; Variables panel docked; clean session | Screen 091 open; verifier in `strict` mode; clean session | Screen 412 open; library `list-row/destructive` indexed |
| **CLI** | `dd design --brief @briefs/A.txt --screen 333 --record demos/A.cast` | `dd design --brief @briefs/B.txt --screen 217 --record demos/B.cast` | `dd design --brief @briefs/C.txt --screen 091 --verifier strict --record demos/C.cast` | `dd design --brief @briefs/D.txt --screen 412 --record demos/D.cast` |
| **MCP-verify** | Probe-tested in W0.B | Probe-tested in W0.B | Probe-tested in W0.B | Probe-tested in W0.B |
| **Recording** | Edited; raw in `demos/raw/A.mov` | Edited; raw in `demos/raw/B.mov` | Edited; raw in `demos/raw/C.mov` | Edited; raw in `demos/raw/D.mov` |

All four back-to-back: ~3 minutes total edited.

---

## 12. Risk register

Top 11 risks ordered by severity × likelihood. v2 adds
R8-R11 from the critique pass.

| # | Risk | Sev | Like | Early Warning | Mitigation |
|---|------|-----|------|---------------|------------|
| 1 | 204/204 silent regression on variant fallback | Catastrophic | High | Smoke fixture per KIND from W5 day 1 | Block merge if any smoke fixture's `is_parity` flips True without `kinds==[]`. W5 ships first. |
| 2 | Resolver loses ground-truth properties | Catastrophic | High | `intolerable.length` non-zero in compat-diff JSONL on any baseline screen | `instance_baselines` in catalog (R6); pass-6 boundary check; daily CI summary surfaces drift early |
| 3 | Bridge cumulative load on full sweep | Serious | High | Per-screen wall-time exceeds 90th-percentile baseline by >2× | `Dank-Test-v0.4` for smoke; individual retry per `feedback_sweep_transient_timeouts.md` |
| 4 | Prompt-cache invalidation from schema churn | Serious | Medium | Cache hit rate <60% on smoke | Stable session-scoped enum (W6); freeze schema at phase boundaries |
| 5 | Scope creep past 7 weeks | Serious | High | Phase gate measurement misses by >20% | Hard cut: any phase missing gate triggers de-scope review, NOT extension |
| 6 | Acceptance suite rot | Moderate | High | Smoke pass rate drifts >5pp w/o code change | Cassette/replay + weekly re-record + `STALE_FIXTURE` count |
| 7 | Agent over-binding tokens (false positives) | Serious | Medium | `binding_drift_count` rises while user-rated fidelity drops | `force_literal: true` escape hatch + adjudication review |
| **8** | **Provenance loss in IR pass-6 boundary** | **Catastrophic** | **Medium** | **`KIND_TOKEN_DROP_INTERNAL` fires in CI** | **Boundary check enforces TokenRef-in => TokenBinding-out from expectation set built in pass 2** |
| **9** | **Cache-bust on per-turn enum changes** | **Serious** | **High (was; mitigated by design)** | **Cache hit rate <80% on smoke** | **Session-scoped enums (W6); user-message reachable hints not schema enums** |
| **10** | **Brand-literal false positive (legitimate one-off color rejected)** | **Moderate** | **Medium** | **adjudication sample shows >10% false rejections** | **`force_literal: true` escape hatch surfaced in tool schema** |
| **11** | **Verb-selection regression from added context** | **Serious** | **Medium** | **Verb-selection rate <80% in smoke** | **Per-fixture metric in W7; gate at 80% (Stage 1-3 baseline)** |

---

## 13. Anti-scope (what v0.4 must NOT include)

- **Multi-screen reasoning** — agent operates on one
  screen at a time. No nav-graph IR.
- **Mode-3 from-scratch composition** — agent cannot
  generate a screen from nothing. Trim/edit/append-on-real
  -screen only. Mode-3's known visual gaps are out of scope.
- **Sketch input** — no image-to-design. Text-brief only.
- **Cross-file design-system migration** — token aliasing
  across libraries is v0.5.
- **Auto-detect missing tokens and propose new ones** —
  token authoring out of compiler scope.
- **VLM fidelity scoring as deliverable demo** — internal
  eval, not deliverable. Lives in M7.6 line.
- **`apply_render::rebuild_maps_after_edits` removal** —
  partially obsoleted by `provenance` but its
  `DegradedMapping` exception is the live demo's safety
  net. Remove in v0.4.1 cleanup AFTER 7-day post-cutover
  observation, not in v0.4 itself.
- **Removal of `dd/renderers/figma.py`** — separate
  workstream after cutover commit #3, not in v0.4.
- **Generative layout search** — out.
- **Auto-migrate entire legacy files** — out.
- **Non-deterministic demos that can't be asserted by
  harness** — out.

---

## 14. Inheritance from v0.3

What survives:

- 7-verb edit grammar (Stages 1-2) — unchanged
- Session loop + branching + persistence (Stage 3) —
  unchanged structurally
- Progressive-constraint resume + REBRIEF logging — unchanged
- `dd design log` reasoning trail — extended with
  `--panel` flag
- Phase 1 per-op guards — unchanged
- Bridge-ack surfacing — unchanged
- 204/204 round-trip parity (verified 2026-04-19) —
  baseline-204 set defined in §10
- `dd/catalog.py` 65-type taxonomy — used as input to
  `DesignSystemCatalog`

What v0.4 supersedes:

- `dd/ast_to_element.py` resolver — deprecated at
  cutover; helpers lifted to `dd/resolve_props.py`
- Variant-render path's `_emit_override_tree` —
  replaced by resolver's pass 5
- `_spec_elements` shim in `render_figma_ast.py` —
  removed at cutover

---

## 15. Rollback policy (new in v2)

The cutover is three commits with a ≥7-day dwell:

1. **Cutover commit #1**: `render_figma_compat` flips to
   return `script_v2`. Tagged `v0.4-cutover-flip`. CI runs
   smoke + nightly continuously for 7 days. Any regression
   that breaches phase 4 gate = `git revert <commit>`.
2. **Cutover commit #2** (after 7-day dwell): tag
   `pre-v0.4-cutover` placed on the legacy code's last
   green commit, for rollback reference.
3. **Cutover commit #3** (separate PR, ≥1 week later):
   legacy delete (`dd/render_figma_ast.py` and
   `dd/renderers/figma.py`).

**Rollback recipe**:

If commit #1 surfaces a demo-day regression:
```bash
git revert <#1-sha>
git push  # done — back to legacy
```

If commit #3 ships and a regression surfaces:
```bash
git revert <#3-sha>           # restore legacy files
git checkout pre-v0.4-cutover -- dd/render_figma_ast.py dd/renderers/figma.py
# verify the legacy paths still work
```

**Recording-day discipline**: don't ship cutover commit #3
in the same week as the Loom recording. The buffer between
cutover-flip-stable and legacy-delete is also a buffer
between cutover-stable and demo-recording.

---

## 16. References

- `docs/plan-authoring-loop.md` — v0.3 plan (shipped)
- `docs/rationale/README.md` — v0.3 rationale
- `docs/demo-vision.md` — harness idea (post-v0.4)
- `docs/spec-dd-markup-grammar.md` — grammar spec (no
  changes in v0.4)
- `LOOM_SCRIPT.md` — original 5-7 minute Loom plan
  (deferred to post-v0.4)
- `feedback_capability_gated_emission.md` — per-backend
  capability gate pattern
- `feedback_boundary_contract.md` — SQL-only-in-loaders
- `feedback_never_trust_currentpage.md` — bridge gotcha
- `feedback_sweep_transient_timeouts.md` —
  individual-retry pattern
- `feedback_verifier_blind_to_visual_loss.md` — why
  204/204 can hold while demo regresses; W5 motivation
- `feedback_mode3_visual_gap_root_cause.md` — Mode-3
  out-of-scope justification
- `feedback_dank_corpus_drift_25.md` — baseline-204 set
  derivation

---

*v2 complete. All §1-§16 reflect critique-pass integrations
across architecture, workstreams, phasing, demos, risks,
and rollback. Phase 4 critique pass next.*
