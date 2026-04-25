# v0.4 Plan — Design-System Compiler, Made Provable

> **For the next session.** You are arriving cold. This document
> is self-contained — it captures the audit findings, the
> architectural decision, the ordered workstreams, the parallel-
> agent execution patterns, the verification gates, and the
> kill-shot demos that v0.4 must produce.
>
> **Do not re-derive.** The plan IS the design. When something
> here conflicts with a prior plan or rationale doc, this
> document wins. Lessons that survived prior sessions are
> integrated; mistakes that surfaced are fenced off.
>
> **Read order**:
> 1. §1 Goal + §2 Audit — *why* we're doing this
> 2. §3 Architecture decision — *what* we're building
> 3. §4-§7 Workstreams — *the work*
> 4. §8 Phasing + §9 Parallel-agent execution pattern — *how
>    you'll execute*
> 5. §10 Verification gates — *how we know it landed*
> 6. §11 Demo deliverables — *what proves it*
> 7. §12 Risk register + §13 Anti-scope — *what could go wrong,
>    what to NOT do*

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
  incapable of consuming unresolved input**. Any unresolved
  TokenRef, component path, or variant axis becomes a typed
  error surfaced to the agent and the harness — not a
  fallback rendering.
- The agent receives a **filtered, component-reachable
  catalog + a session ledger**, so it can choose valid
  tokens/components and remember what it's already decided.
- The verifier rejects **literals when a near-token exists**
  (configurable distance), and the agent can self-correct.
- Four kill-shot demos (§11) prove all the above on real
  Dank Experimental screens, side-by-side with the original.

**Time budget**: 4-5 weeks of focused work, 6-week buffer.

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
  system, not by per-stage cleanup.** The renderer's input
  type should make TokenRef-drop a compile error, not a
  runtime regression discovered via parity sweep.
- **Path → component_key resolution belongs in a single pass,
  not six patches.** This is the MLIR conversion-pass pattern.
- **The 204/204 round-trip will silently break** when
  variant-axis selection lands without new error kinds
  (`KIND_VARIANT_FALLBACK`). This must be solved BEFORE the
  refactor, not after.

These findings define the architecture in §3.

---

## 3. Architecture decision

### The shape: ResolvedFigmaIR + single resolution pass

Introduce a new IR — `ResolvedFigmaIR` — whose leaf values are
`Bound[T] = Literal[T] | TokenBinding[T]`. The renderer has
exactly two methods per property:

```python
class FigmaEmitter:
    def apply_literal(self, var: str, prop: FigmaProperty, value): ...
    def apply_bound(self, var: str, prop: FigmaProperty, bound: Bound): ...
    # No third method exists. Type system enforces this.
```

There is no third path that silently picks. **Dropping a
TokenRef becomes a type error at the boundary, not a runtime
regression.**

A single resolution pass converts AST → ResolvedFigmaIR:

```python
def resolve(
    ast: L3Document,
    catalog: DesignSystemCatalog,
    *,
    db_supplements: Optional[DBSupplements] = None,
) -> ResolveResult:
    """Returns (ir | None, list[ResolveError]). Never raises."""
```

The resolver runs six ordered sub-passes, each independently
testable:

1. `pass_1_type_check` — every node head has known type
2. `pass_2_resolve_paths` — every comp-ref path → component_key
3. `pass_3_resolve_variants` — variant args validated against axes
4. `pass_4_resolve_tokens` — every TokenRef → TokenBinding
5. `pass_5_rewrite_path_overrides` — paths → addressed overrides
6. `pass_6_assemble` — build ResolvedNode tree, fill provenance

Hard-fail policy: any error of kind ≠ `KIND_FONT_UNAVAILABLE`
aborts the IR build. Soft warnings are non-blocking and live
on `ir.soft_warnings`.

### Coexistence period

Both renderers live in tree for the entire 4-6 weeks:

```
[ AST (L3Document) ]
       │
       ├──── (legacy)  ──> _spec_elements / _spec_tokens / db_visuals
       │                    └──> render_figma   ──> script_legacy
       │
       └──── (new)     ──> resolve(ast, catalog)
                            └──> ResolvedFigmaIR
                                  └──> render_figma_v2  ──> script_v2
```

A bridge harness `dd/render_compat.py::render_figma_compat(...)`
accepts the legacy signature, runs both paths, byte-diffs them,
returns the legacy script (so production behavior is identical),
but logs every divergence to `render_compat_diff.jsonl`.

`dd generate` and `dd design --render-to-figma` are switched
to `render_figma_compat` from week 1. They keep emitting the
legacy script. We accumulate divergence telemetry **without
bearing the risk**.

Cutover is two commits at the end:
1. `render_figma_compat` flips to return `script_v2`
2. Legacy path deleted

Both gated on the equivalence signal (§10).

### Why this shape

- **It collapses six patches into one pass.** The proto-plan
  before this audit had separate fixes for `ast_to_element`
  TokenRef drop, variant-render rebind wiring, path→key
  resolver, typography binding, etc. All of those become
  consequences of "the resolver builds Bound[T]; the renderer
  can't consume anything else."
- **It makes regressions provable.** The compat wrapper
  produces a JSONL of divergences. Cutover requires
  `dropped_props_count: 0` across all 204 screens.
- **It matches the project's own pitch.** "Compiler" implies
  one IR. Today's three-IRs-as-federated-views was the lie
  the audit caught. This fixes it.

---

## 4. Workstreams

Eight workstreams, lettered W1-W8.

### W1 — ResolvedFigmaIR types

**File**: `dd/resolved_ir.py` (new, ~600 LOC).

**Owns**: The full type definition for the new IR. Frozen
dataclasses with slots, hashable, structurally equal. Every
leaf value is `Bound[T] | None`. Every comp-ref node carries
a resolved component_key. Every variant selection is
enum-typed against the catalog. Every path override is
rewritten to address a specific descendant.

**Invariants enforced (R1-R6)**:
- R1. Leaf values: `Bound[T] | None`. None = absent.
- R2. Comp-ref nodes carry `component_key: str`, not paths.
- R3. Variant selections are enum-typed.
- R4. Path overrides rewritten as addressed overrides.
- R5. Token refs survive: `TokenBinding.token_path` always
  set, `resolved_literal` always present (renderer chooses
  by mode).
- R6. **No reference** to L3Document, spec dict, db_visuals,
  or any side-car.

**Type structure** (paste-ready):

```python
@dataclass(frozen=True, slots=True)
class Literal(Generic[T]):
    value: T
    source: Literal["author", "catalog-default", "db-extract", "inferred"]

@dataclass(frozen=True, slots=True)
class TokenBinding(Generic[T]):
    token_path: str
    scope_alias: Optional[str]
    resolved_literal: T  # always present — renderer fallback
    figma_variable_id: Optional[str]  # populated when known

Bound = Union[Literal[T], TokenBinding[T]]
```

Domain leaves: `Color`, `Length`, `FontFamily`, `Shadow`,
`Stroke`, `Fill`, `GradientStop`, `Sizing`, `Padding`,
`AutoLayout`, `VariantSelection`, `ComponentInstanceRef`,
`InstancePropertyOverride`, `AddressedOverride`,
`TextContent`, `ResolvedNode`, `NodeProvenance`,
`ResolvedFigmaIR`.

(See `dd/resolved_ir.py` after Agent T1 ships day 1.)

**Test scaffolding**: `tests/_factories/resolved.py` — every
leaf type has a factory with `Partial[T]` overrides per
CLAUDE.md test-data conventions. Schemas come from the
dataclasses themselves; never redefined in tests.

**Size**: 3 days. ~600 LOC + ~400 LOC factories.

**Blocks**: nothing. **Unblocks**: W2, W3, W4.

### W2 — Resolution pass

**File**: `dd/resolve.py` (new, ~1200 LOC).
Plus `dd/resolve_loader.py` (catalog assembly from DB) and
`dd/resolve_props.py` (head-property → element-axis mapping,
lifted from `ast_to_element.py`).

**Owns**: The six-sub-pass resolution pipeline.

**Catalog shape**:

```python
@dataclass(frozen=True)
class DesignSystemCatalog:
    component_keys: dict[str, ComponentKeyEntry]
    types: dict[str, CatalogTypeEntry]
    tokens: dict[str, ResolvedTokenValue]
    master_descendants: dict[str, dict[str, str]]
```

Loader `build_catalog_from_db(conn) -> DesignSystemCatalog`
is the **only** place SQL touches resolution (per
`feedback_boundary_contract.md`). Resolver is a pure
function over `(ast, catalog, db_supplements)`.

**Error taxonomy** (`ResolveError`):

```python
KIND_TOKEN_UNKNOWN
KIND_TOKEN_TYPE_MISMATCH      # token resolves to Color, prop wants Length
KIND_PATH_UNRESOLVED          # comp-ref path not in CKR
KIND_VARIANT_INVALID          # axis or value not on master
KIND_VARIANT_MISSING_REQUIRED
KIND_INSTANCE_PROP_UNKNOWN
KIND_INSTANCE_PROP_TYPE_MISMATCH
KIND_PATH_OVERRIDE_TARGET_MISSING
KIND_LEAF_HAS_CHILDREN        # AST shape error caught at resolve
KIND_TYPE_UNKNOWN             # head type ∉ catalog
KIND_FONT_UNAVAILABLE         # soft warning
KIND_SLOT_REQUIRED_EMPTY
```

Each error carries `eid`, `property`, `detail`, `suggestion`
(e.g., "did you mean color/primary/600?"), and
`ast_node_id` (id(Node) for caller to highlight).

**Size**: 12 days. Critical path. ~1200 LOC + ~1500 LOC tests.

**Blocks**: W1. **Unblocks**: W3 (E2E equivalence), W6.

### W3 — Renderer v2

**File**: `dd/render_figma_v2.py` (new, ~1500 LOC).

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

Two-method contract is the only API. `apply_bound` decides
between live-binding (when `figma_variable_id` is present)
vs literal-then-rebind (the v0.2 path). Token rebind entries
emit as a side effect into `RenderResult.token_refs`.

**Size**: 10 days, concurrent with W2. ~1500 LOC + ~800 LOC
tests.

**Blocks**: W1. **Unblocks**: W4 (compat layer).

### W4 — Compat / equivalence

**File**: `dd/render_compat.py` (new, ~250 LOC).
Plus `tests/test_v2_v1_equivalence.py` (the gating test).

**Owns**: The bridge wrapper that runs both paths, byte-diffs
them, returns legacy script during the transition,
accumulates divergence telemetry.

The byte-diff has to be **structural** (not raw string),
because trivial whitespace and var-name shifts would
otherwise fail. Specifically:

1. AST-walk both scripts, extract `M["<eid>"] = ...` map
   declarations and per-eid `try { n.<prop> = <value> }`
   writes.
2. For each eid, compute property-set diff:
   `{prop: value}` from old vs new.
3. **Gate**: every eid in every one of the 204 screens has
   property-set diff size 0 OR property-set is a subset
   (new is allowed to be more strict, never to drop).

Output: `tests/.fixtures/v2_v1_diff.jsonl` per screen.
Cutover commit message must include
`dropped_props_count: 0` from that file.

**Size**: 4 days, mostly waiting on W2 + W3.

**Blocks**: W2 + W3. **Unblocks**: cutover gate.

### W5 — Verifier extensions

**Files**: `dd/verify_figma.py` (extend), per-error fixtures.

**Owns**: Four new error kinds with producer + consumer
wiring:

- **`KIND_VARIANT_FALLBACK`** — variant typo throws,
  placeholder returned. Producer in the variant-axis
  selector, fires *before* placeholder return so
  `M[key]` doesn't mask the error. Verifier downgrades
  `is_parity` on any occurrence.
- **`KIND_TOKEN_DROP`** — TokenRef silently lost.
  Producer at the resolver/renderer boundary. Hard
  parity break.
- **`KIND_PATH_UNRESOLVED`** — component path didn't
  resolve. Distinct from existing `KIND_COMPONENT_MISSING`
  (which is "no key at all"). Hard parity break.
- **`KIND_BINDING_REQUIRED_LITERAL`** — soft warning.
  Increments `binding_drift_count`. Phase gate uses
  count threshold, not parity downgrade.

**Critical**: Add error kinds BEFORE the IR refactor lands,
not after. Otherwise the 204/204 sweep silently regresses
when variant-axis selection breaks (per systems-engineer
audit).

**Size**: 4 days.

**Blocks**: nothing (independent of IR work). Should ship
in week 1 as foundation.

**Unblocks**: every other workstream by surfacing failure
modes loudly.

### W6 — Agent context (catalogs, ledger, instance awareness)

**Files**: `dd/agent/catalog_inject.py`, `dd/agent/annotate.py`,
`dd/agent/ledger.py` (all new).

**Owns**: Surface the design system to the agent.

**Per-turn token budget**:

| Block | Where | Bytes | Cacheable |
|---|---|---|---|
| System prompt + full token catalog + full component catalog | `system=` | ~6 KB | yes (ephemeral) |
| Brief + iteration counter | user msg | ~300 B | no |
| Focused subtree (compressed L3) | user msg | ~2 KB | no |
| Reachable-tokens slice + reachable-components slice | user msg | ~1 KB | no |
| Instance annotations | user msg | ~600 B | no |
| Session ledger | user msg | ~500 B | no |
| Tool schemas (7 verbs, eid-/component-/token-enum) | `tools=` | ~3 KB | yes when stable |

Target: ~10-12 KB cached + ~4-5 KB fresh ≈ $0.018/iter at
Sonnet 4.6. A 6-iter session ≈ $0.11.

**Reachable tokens** (filtering signal):

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

Cluster by prop type at injection — color tokens emit only
into fill/stroke/background props, length tokens into
gap/padding/size/radius.

**Component catalog** (from `dd/library_catalog.py:44`):

```
button/large/translucent
  variants: state ∈ {default, active, disabled, loading}
  slots: leading-icon, label, trailing-icon
  default-props: variant=default, fill={color.action.primary}
```

All ~30 components fit in <2 KB cached.

**Instance annotation** (A3):

```
### Instances in scope
@nav-toolbar-3   button/large/translucent · state=default
                 fill -> color.action.primary
                 leading-icon: @icon-22
@btn-save        button/large/solid       · state=disabled
```

**Session ledger** (the 4th leg):

```python
@dataclass
class Ledger:
    tokens_committed: dict[str, list[str]]      # {token_path: [eids]}
    components_used: dict[str, list[str]]
    decisions: list[tuple[int, str]]            # (iter, rationale)
    open_threads: list[str]                     # bounded LLM-summarized
```

Deterministic fields rebuilt from `move_log` table.
`open_threads` LLM-summarized once on session resume.

**Tool schema discriminated unions** (in
`dd/structural_verbs.py:390`):

```python
"value": {
    "oneOf": [
        {"type":"object","properties":{
            "kind":{"const":"literal"},
            "literal_value":{"type":"string"}
        },"required":["kind","literal_value"]},
        {"type":"object","properties":{
            "kind":{"const":"token_ref"},
            "token_path":{"type":"string","enum": reachable_token_paths_for(prop_class)}
        },"required":["kind","token_path"]}
    ]
}
```

Server-side canonicalization in `apply_edits`: literal close
to token (color ΔE≤5, length within 2px) → reject with
`nearest_token` field. Agent sees rejection next turn,
self-corrects.

**Size**: 5-6 days.

**Blocks**: nothing structurally (reads existing tables);
benefits from W5 error kinds for adversarial feedback.

**Unblocks**: W7 (acceptance fixtures), W8 (demos).

### W7 — Acceptance fixture suite

**Files**: `tests/acceptance/fixtures/`,
`tests/acceptance/runner.py`.

**Owns**: Three-tier fixture suite:

```
fixtures/
  smoke/         # 8-12, runs per-commit (~$1.50, 3-5min)
  nightly/       # 50, runs nightly
  weekly/        # 200, runs weekly drift sweep
  schema_v1.json # tool_schema_hash pinned
```

Smoke pins (12 fixtures): one per primitive — set, delete,
append-FRAME, append-INSTANCE, insert, move, swap, replace,
plus 4 binding-coverage briefs (color-token,
spacing-token, variant-selection, override-tree).

**Schema-hash mechanism**:
`dd/edit_grammar/schema.py::compute_tool_schema_hash()`
produces sha256 over the verb JSON-Schema. Fixture loader
verifies `expected.tool_schema_hash == current_hash` —
mismatch = test SKIP with `STALE_FIXTURE` error, forcing
fixture regen via `dd regen-fixtures`. CI fails on >2 stale
fixtures.

**Size**: 4 days.

**Blocks**: W6 (need agent context for fixtures to test
against). **Unblocks**: continuous regression catch.

### W8 — Demo deliverables

**Files**: `demos/A.txt`, `demos/B.txt`, etc., plus a
`demos/run.sh` orchestrator.

**Owns**: Four kill-shot demos (§11), each with brief, CLI
invocation, MCP-verify command, recording cuts.

**Size**: 3 days, last week.

**Blocks**: W3, W6, W7.

---

## 5. Bridge constraint mitigation

Dank Experimental's Dank 1.0 page has 87,095 descendants;
the bridge intermittently times out at 300s.

**Solution**: dedicated test file `Dank-Test-v0.4` —
clone Dank Experimental → single `Test/v0.4` page seeded
with ~200 components covering all variant axes. Smoke +
nightly hit this file only.

Setup/teardown per fixture:
- `figma.root.findOne(p => p.name === 'Test/v0.4')` and
  hard-assert identity (per
  `feedback_never_trust_currentpage.md`).
- Capture `figma.currentPage` before+after each
  `importComponentByKeyAsync`. Restore explicitly.
- Bridge call budget: cap at 2 calls per fixture.
  >2 = test fails with `BRIDGE_BUDGET_EXCEEDED`.

Weekly 200-brief sweep hits Dank Experimental directly.
Expected to be flaky. Use individual-retry pattern. NOT a
merge gate.

---

## 6. Tests

Layered architecture, behavior-first per CLAUDE.md.

**A. Resolver pure unit tests**
`tests/test_resolve_passes.py` — one suite per sub-pass.
Hand-built `L3Document` + `DesignSystemCatalog` from
factories. Every `KIND_*` error has at least two tests
(positive trigger + lookalike that should NOT trigger).

**B. Resolver integration tests**
`tests/test_resolve_integration.py` —
`parse_l3(source) → resolve(ast, catalog) → ResolvedFigmaIR`
on small hand-written L3 fixtures
(`tests/fixtures/resolve/*.dd`). Asserts IR shape.

**C. v2 renderer pure tests**
`tests/test_render_figma_v2.py` — feed hand-built
`ResolvedFigmaIR` to `render_figma_v2`. Assert script
structure. No DB.

**D. End-to-end equivalence (THE GATING TEST)**
`tests/test_v2_v1_equivalence.py` — for each of 204 Dank-EXP-02
screens:
```python
old = render_figma(ast, conn, nid_map, _spec_elements=..., ...)
ir  = resolve(ast, build_catalog_from_db(conn))
new = render_figma_v2(ir, ckr_from(conn))
assert script_byte_diff(old.script, new.script).is_empty
```
Slow. Gate behind `pytest -m parity_204`. Run on CI nightly.

**E. Adversarial resolver tests**
`tests/test_resolve_adversarial.py` — synthesize
`L3Document`s the agent might produce that should hard-fail.
Each `KIND_*` error has a fixture.

**F. Property-based round-trip**
`tests/test_resolve_inverse.py` — for a generated
`ResolvedFigmaIR`, build a synthetic `L3Document` that the
resolver should produce exactly that IR for. Uses
`hypothesis`.

**G. Acceptance smoke (per-commit)**
8-12 brief × Sonnet × bridge. ~$1.50, ~3-5 min. Gates merge
to main.

**H. Acceptance nightly**
50 briefs. ~$5-15. Gates next-day work.

**I. Acceptance weekly**
200 briefs. Drift sweep. Not a merge gate.

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
| `dd/verify_figma.py` | EXTEND (W5) — add 4 KINDs |
| `dd/structural_verbs.py:390` | MODIFY (W6) — discriminated-union schemas |
| `dd/agent/loop.py:586` | MODIFY (W6) — system prompt with cached catalog |
| `dd/agent/loop.py:269` | MODIFY (W6) — reachable slices in user msg |
| `dd/sessions.py:297` | EXTEND (W5) — coverage payload in move_log |
| `dd/cli.py:2102+2704` | MODIFY (W4 cutover) — call `render_figma_compat` |
| `dd/compose.py:1546` | MODIFY (W4 cutover) — call `render_figma_compat` |
| `dd/apply_render.py:537+560` | MODIFY (W4 cutover) — call `render_figma_compat` |
| `dd/render_figma_ast.py` | UNCHANGED until cutover, DELETED at end |
| `dd/renderers/figma.py` | UNCHANGED until cutover, DELETED at end |
| `dd/ast_to_element.py` | DEPRECATED at cutover (helpers lifted to `resolve_props.py`) |
| `dd/markup_l3.py` | UNCHANGED |
| `dd/extract_*` | UNCHANGED (catalog reads existing tables) |
| `dd/apply_render.py::rebuild_maps_after_edits` | DEPRECATED at v0.4.1 (separate cleanup, post-demo) |

---

## 8. Phasing

Four phases, end-of-week milestones.

### Phase 1 — Foundation (end of week 1)

**Workstreams active**:
- W1 (types) — full
- W5 (verifier extensions) — full
- W7 (acceptance fixtures) — start writing failing tests

**Phase gate**:
- `dd/resolved_ir.py` exists; type-check passes; factories
  cover every leaf type
- Four new `KIND_*` constants land; smoke fixture for each
  KIND triggers correctly
- ≥10 invariant tests in W7 are failing for the right
  reasons (tests assert the v0.4 behavior; fail because the
  behavior doesn't exist yet)

**Stop-condition revise** if:
- W1 takes >5 days (signals types are wrong)
- KIND constants don't surface in `__errors` reliably

### Phase 2 — Resolver produces ResolvedFigmaIR (end of week 2)

**Workstreams active**:
- W2 (resolver) — full
- W3 (v2 renderer) — start (concurrent with W2)
- W6 (agent context) — wave A: catalog injection,
  annotation, ledger
- W7 — expand fixtures

**Phase gate**:
- Resolver passes 1-6 implemented; key fixtures resolve
  tokens/components without fallback
- Every unresolved case emits explicit error kind (no
  rendering fallback)
- Token-rate >0% on smoke suite (agents see the catalog)

**Stop-condition revise** if:
- Resolver pass complexity exceeds ~1500 LOC (signals the
  type is wrong; redesign W1)

### Phase 3 — Renderer parity + agent fluency (end of week 3-4)

**Workstreams active**:
- W3 — full
- W4 (compat) — full
- W6 — wave B: discriminated-union tool schemas,
  adversarial feedback
- W7 — full smoke + nightly suites

**Phase gate**:
- `render_figma_compat` runs both paths and reports
  divergence
- 3 end-to-end fixtures: agent → resolver → v2 renderer →
  Figma; INSTANCE + token bindings + typography all visible
- Token rate >50% on 8-brief smoke
- KIND_TOKEN_DROP rate <5% per session

**Stop-condition revise** if:
- 204/204 equivalence test shows >0 dropped properties
  (signals resolver loses information)
- Agent over-binds (token rate >90%) — false positives
  dominate

### Phase 4 — Cutover + demos (end of week 5, week 6 buffer)

**Workstreams active**:
- W4 — cutover commits
- W8 — demos
- Cleanup

**Phase gate**:
- All four kill-shot demos pass on fresh clone
- 0 silent-drop regressions
- Smoke 12/12 pass; nightly 50/50 ≥95% pass
- Weekly 200-brief ≥90% parity (Dank Experimental directly)
- Loom recording captures all four demos

---

## 9. Parallel-agent execution pattern

This plan executes via multi-agent delegation with the
coordinator (you, the next session) writing synthesis,
critical glue, and code where measurement matters.

### Five concurrent threads

| Thread | Subagent | Owns | Contract (the seam) |
|---|---|---|---|
| **T1: Types** | Sonnet | `dd/resolved_ir.py` + factories | After day 1, signature is fixed; further changes need explicit T1 sign-off |
| **T2: Resolver** | Sonnet | `dd/resolve.py`, `dd/resolve_loader.py`, `dd/resolve_props.py`, tests | Consumes T1's types. Produces a callable that round-trips factories |
| **T3: Renderer v2** | Sonnet | `dd/render_figma_v2.py`, tests | Consumes T1's types. Builds against fake `ResolvedFigmaIR` from T1's factories |
| **T4: Compat / equivalence** | Sonnet | `dd/render_compat.py`, equivalence test | Consumes T2 + T3. Wrapper-shape stub on day 1; equivalence test fills in once T2 + T3 land |
| **T5: Migration** | Sonnet | Call-site swaps in CLI/compose/apply_render | Independent of T2/T3 — only depends on T4's wrapper landing |

### The "dispatcher → builders → reviewer" pattern

For high-leverage moments (especially the IR refactor):

1. **Dispatcher** (you) writes failing test(s) that pin the
   contract. Commits.
2. **Builders** (2-3 subagents in parallel) implement
   minimal code to satisfy. Each works on a non-overlapping
   subset (e.g., one builds `pass_2_resolve_paths`, another
   builds `pass_4_resolve_tokens`).
3. **Reviewer** (separate subagent or Codex) reviews the
   builder output for: silent fallback paths, missing error
   kinds, type violations.
4. Coordinator merges only after reviewer signs off.

### Codex consult points

- **After each major merge in W1/W2/W3**: type errors across
  repo, dead-path detection, API ergonomics review
- **Design forks**: e.g., the W6 "should reachable filtering
  use token ID or token path" decision
- **The architecture audit at end of Phase 2**: is the
  resolver shape holding up, or do we need to redesign?
- **Cutover sign-off**: Codex reviews the
  `dropped_props_count` JSONL before either cutover commit
  ships

### Cross-review pattern

No agent reviews their own code. Specifically:

- Agent A (T1, types) reviews B's resolver (semantic fit)
- Agent C (T3, v2 renderer) reviews D's compat wrapper
  (boundary correctness)
- Agent D reviews E's call-site swaps (no regression)
- Coordinator reviews all merges; Codex reviews coordinator's
  synthesis at phase boundaries

### Conflict-prevention seam

`dd/resolved_ir.py` is the contract. After T1 day 1, that
file is **read-only for everyone except Agent A**.
Mutations require an issue + sign-off. Everyone else builds
against the type, not against each other's progress.

### Parallelization map for W6 (agent-side)

W6's six pieces (token catalog, component catalog,
instance annotation, ledger, tool schemas, adversarial
feedback) split into two waves:

**Wave A (parallel, week 2)**:
- Subagent: token-catalog injection
- Subagent: component-catalog injection
- Subagent: instance annotation (A3)
- Subagent: session ledger

All four read existing DB tables; no IR dependencies.

**Wave B (parallel, week 4)**:
- Subagent: discriminated-union tool schemas (depends on
  Wave A token catalog)
- Subagent: adversarial verifier feedback loop (depends on
  Wave B schema definition)

### Parallelization map for W5 (verifier extensions)

Coordinator owns the KIND constants in `dd/verify_figma.py`
(producer + consumer must stay synced).

**Parallel subagents (one tool-call message)**:
- A: KIND_VARIANT_FALLBACK producer in renderer + smoke
  fixture
- B: KIND_TOKEN_DROP producer at resolver/renderer
  boundary + smoke fixture
- C: KIND_PATH_UNRESOLVED producer + smoke fixture
- D: Coverage instrumentation in `sessions.py` + `loop.py`
- E: Smoke fixture harness in `tests/acceptance/`
- F: Bridge-test-file setup script

Coordinator merges KIND additions into `verify_figma.py`
last, after all 4 producer PRs land — single integration
point keeps the consumer allowlist authoritative.

### Coordinator's role

You (the next session) are not just dispatching. You write:

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
- The cutover commit message and gate verification
- Phase-gate go/no-go decisions

**Always delegate**:
- Single-pass resolver implementation (split across builders)
- Test fixture authoring (mechanical)
- Migration call-site swaps (mechanical)
- Bridge-environment setup scripts (mechanical)

---

## 10. Verification gates

Each phase has a numerical gate. Numerical when possible —
"literal-vs-token rate <20% on 8-brief smoke" not "tokens
look better."

### Phase 1 gate
- W1 type definitions check with mypy, no errors
- 4 new KIND_* constants land
- Smoke fixture per KIND triggers correctly
- ≥10 W7 invariant tests fail for the right reasons

### Phase 2 gate
- Token rate >0% on smoke suite
- 0 cases where unresolved input renders without error
- Resolver passes 1-6 implemented and unit-tested

### Phase 3 gate
- `render_figma_compat` reports divergence on every of 204
  screens
- Token rate >50% on 8-brief smoke
- KIND_TOKEN_DROP rate <5% per session
- Smoke 12/12 pass

### Phase 4 gate (CUTOVER)
- `dropped_props_count: 0` across all 204 screens in
  `v2_v1_diff.jsonl`
- Smoke 12/12 pass
- Nightly 50/50 ≥95% pass
- Weekly 200/200 ≥90% parity
- All four kill-shot demos pass on fresh clone

---

## 11. Demo deliverables — kill-shots

Four demos, each ≤90s, each answering a different objection.

### Demo A — DS-correct edit

**Title**: "The agent edits inside the design system, not
next to it."

**Objection**: "How do I know your output isn't a hex-coded
knockoff that looks like our DS?"

**Brief**: `"Increase the radius on the primary CTA in the
Profile screen to 12 and fix its tap state."`

**File**: Dank-EXP-02. **Screen**: 333 (Profile, has
resolved button instance + tap-state variant).

**Why this combo**: screen contains a `button/large/translucent`
INSTANCE bound to `color.action.primary`; agent must edit
THAT instance, not replace it.

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

**Panel**:
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

**Timing**: ~30s

### Demo B — Token-mutation propagation

**Title**: "Change the token, the agent's output changes.
No re-prompt."

**Objection**: "Couldn't an LLM just spit out the right hex
once?"

**Brief**: `"Add a success banner above the cart total."`

**File**: Dank-EXP-02. **Screen**: 217 (Cart, has
`color.feedback.success` defined).

**Agent verbs**:
```
emit_append(@cart-totals-row, banner_template) →
emit_set_edit(@new-banner, {fill: token_ref("color.feedback.success"), text_style: token_ref("typography.body.emphasized")}) →
emit_done
```

**Canvas**: banner renders green-bound. Operator opens Figma
Variables, edits `color.feedback.success` from `#1F8A3B` →
`#0E5C26`. Agent panel re-resolves; canvas re-paints darker
green with no agent call.

**Panel**: `fill ← color.feedback.success → resolved
#1F8A3B` then live-updates to `→ resolved #0E5C26` after
the variable edit.

**Why prompt+MCP can't**: existing tools emit literals.
There is no Bound[T] leaf; nothing for a token mutation to
propagate through.

**Kill-shot**: Figma Variables panel and our agent panel
visible side-by-side; operator changes the swatch and within
one frame both update. No CLI call.

**Timing**: ~37s

### Demo C — Self-correcting agent (adversarial verifier)

**Title**: "An LLM constrained by a type system."

**Objection**: "Agents hallucinate. Won't yours emit
`#1F8A3B` and call it a day?"

**Brief**: `"Match the success-state color used elsewhere in
the app for this confirmation chip."` (Vague to bait a
literal.)

**File**: Dank-EXP-02. **Screen**: 091 (Confirmation).

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
literal would land. v0.4's `feedback_capability_gated_emission`
+ token-drop gate is the constraint.

**Kill-shot**: visible verifier rejection line in the
transcript next to the corrected canvas — audience sees the
agent being told no and recovering.

**Timing**: ~50s

### Demo D — Compose with real components

**Title**: "New instance, right variant axis, slots filled —
from one sentence."

**Objection**: "Sure you can edit. Can you compose?"

**Brief**: `"Add a destructive 'Delete account' row to the
bottom of Settings."`

**File**: Dank-EXP-02. **Screen**: 412 (Settings). Library
has `list-row/destructive` with axes `{size: lg, leading:
icon, trailing: chevron}`.

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
resolver + slot-fill grammar + variant axis catalog. MCP
can drop a frame; it can't pick the right axis combination.

**Kill-shot**: variant-axis chips in the panel light up `lg
/ icon / chevron` matching the rendered row.

**Timing**: ~55s

### Execution checklist (for v0.4 close)

| | A | B | C | D |
|---|---|---|---|---|
| **Pre-flight** | Dank-EXP-02 open on screen 333; clean session DB; bridge healthy; component catalog hydrated | Screen 217 open; Variables panel docked; clean session | Screen 091 open; verifier in `strict` mode; clean session | Screen 412 open; library `list-row/destructive` indexed |
| **CLI** | `dd design --brief @briefs/A.txt --screen 333 --record demos/A.cast` | `dd design --brief @briefs/B.txt --screen 217 --record demos/B.cast` | `dd design --brief @briefs/C.txt --screen 091 --verifier strict --record demos/C.cast` | `dd design --brief @briefs/D.txt --screen 412 --record demos/D.cast` |
| **MCP-verify** | `get_node(@profile-cta).componentKey == pre.componentKey AND .cornerRadius == 12 AND .variantProperties.state == "pressed"` | `get_node(@new-banner).boundVariables.fills[0].id == var(color.feedback.success)` then `set_variable(...)` then re-`get_node` shows new resolved hex | session ledger contains one `KIND_TOKEN_DROP` entry on attempt 1 and `is_parity=True` on attempt 2 | `get_node(@new-row).type == "INSTANCE" AND .componentKey resolves to list-row/destructive AND .variantProperties == {size:lg, leading:icon, trailing:chevron}` |

All four back-to-back: ~3 minutes total.

---

## 12. Risk register

Top 7 risks ordered by severity × likelihood.

| # | Risk | Sev | Like | Early Warning | Mitigation |
|---|------|-----|------|---------------|------------|
| 1 | 204/204 silent regression on variant fallback | Catastrophic | High | Smoke suite includes variant-typo fixture; verifier emits KIND_VARIANT_FALLBACK | Block merge if any smoke fixture's `is_parity` flips True without `kinds==[]`. Ship W5 BEFORE the IR refactor. |
| 2 | Resolver loses ground-truth properties (the `db_supplements` failure mode from §8 of W2 spec) | Catastrophic | High | `v2_v1_diff.jsonl` shows non-zero `dropped_props_count` on any Mode-1 screen | `db_supplements` kwarg on `resolve()`; resolver pass 5 merges into `AddressedOverride`; equivalence gate as cutover blocker |
| 3 | Bridge cumulative load on full sweep | Serious | High | Per-screen wall-time exceeds 90th-percentile baseline by >2× on nightly | Dedicated `Dank-Test-v0.4` file; individual retry per `feedback_sweep_transient_timeouts.md` |
| 4 | Prompt-cache invalidation from schema churn | Moderate | Medium | Cache hit rate <60% on smoke suite | Freeze verb schema at phase boundaries; `tool_schema_hash` only bumps in scheduled windows |
| 5 | Scope creep past 6 weeks | Serious | High | Phase gate measurement misses by >20% | Hard cut: any phase missing gate triggers de-scope review, NOT extension |
| 6 | Acceptance suite rot | Moderate | High | Smoke pass rate drifts >5pp w/o code change | Weekly fixture regen + `STALE_FIXTURE` count metric in CI |
| 7 | Agent over-binding tokens (false positives) | Serious | Medium | `binding_drift_count` rises while user-rated fidelity drops on adjudication sample | Adjudication review: 20 random binds/week; threshold-based `KIND_OVERBIND` emission |

---

## 13. Anti-scope (what v0.4 must NOT include)

These are tempting but premature. Defer.

- **Multi-screen reasoning** — the agent operates on one
  screen at a time. v0.4 does not introduce nav-graph IR or
  cross-screen state.
- **Mode-3 from-scratch composition** — the agent cannot
  generate a screen from nothing. Trim/edit/append-on-real
  -screen only. Mode-3's known visual gaps
  (`feedback_mode3_visual_gap_root_cause.md`) are out of
  scope.
- **Sketch input** — no image-to-design. v0.4 is text-brief
  only.
- **Cross-file design-system migration** — token aliasing
  across libraries is a v0.5 question.
- **Auto-detect missing tokens and propose new ones** —
  token authoring is out of compiler scope.
- **VLM fidelity scoring as a deliverable demo** — internal
  eval, not deliverable. Lives in M7.6 line of work.
- **`apply_render::rebuild_maps_after_edits` removal** —
  partially obsoleted by `provenance` but its
  `DegradedMapping` exception is the live demo's safety net.
  Remove in v0.4.1 cleanup post-demo, not in v0.4.
- **Removal of `dd/renderers/figma.py`** — that's the
  legacy-delete commit, after cutover. Separate workstream.
- **Generative layout search** — out.
- **Auto-migrate entire legacy files** — out.
- **Non-deterministic demos that can't be asserted by
  harness** — out.

---

## 14. Inheritance from v0.3

What survives from prior session work:

- The 7-verb edit grammar (Stages 1-2) — unchanged
- The session loop + branching + persistence (Stage 3) —
  unchanged structurally
- The progressive-constraint resume + REBRIEF logging
  (recent) — unchanged
- The `dd design log` reasoning trail (recent) — unchanged
- The Phase 1 per-op guards (recent) — unchanged
- The bridge-ack surfacing (recent) — unchanged
- The 204/204 round-trip parity (verified 2026-04-19) —
  must hold post-cutover
- The catalog at `dd/catalog.py` (65-type taxonomy) — used
  as input to `DesignSystemCatalog`

What v0.4 supersedes:

- The `dd/ast_to_element.py` resolver (M2 demo-blocker
  bandaid) — deprecated at cutover; helpers lifted to
  `dd/resolve_props.py`
- The variant-render path's `_emit_override_tree` →
  `_collect_swap_targets_from_tree` indirection — replaced
  by resolver's pass 5
- The `_spec_elements` shim in `render_figma_ast.py` —
  removed at cutover

---

## 15. References

- `docs/plan-authoring-loop.md` — the v0.3 plan (shipped)
- `docs/rationale/README.md` — v0.3 rationale (read for
  context)
- `docs/demo-vision.md` — the harness idea (post-v0.4)
- `docs/spec-dd-markup-grammar.md` — the grammar spec (no
  changes in v0.4)
- `LOOM_SCRIPT.md` — the original 5-7 minute Loom plan
  (deferred to post-v0.4)
- `feedback_capability_gated_emission.md` — the
  per-backend capability gate pattern
- `feedback_boundary_contract.md` — the SQL-only-in-loaders
  pattern that resolver follows
- `feedback_never_trust_currentpage.md` — the bridge gotcha
  that drives W5's bridge constraint
- `feedback_sweep_transient_timeouts.md` — the
  individual-retry pattern
- `feedback_verifier_blind_to_visual_loss.md` — why the
  204/204 can hold while the demo regresses; W5's
  motivation
- `feedback_mode3_visual_gap_root_cause.md` — why Mode-3 is
  out of scope

---

*End of v1 draft. Critique pass next.*
