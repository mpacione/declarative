# Sprint 2 — Registry-driven station parity

**Branch**: `v0.3-integration`
**Start tip**: `21fbf8d` (Sprint 2 attempt-1 C3)
**Plan authors**: Claude (main thread) + Codex 5.5 (architectural partner)
**Date**: 2026-04-27

## 1. Problem statement

Cross-corpus validation (commit `6905383`) surfaced two real
bugs the verifier missed:

- Wrong text content: `"Reject"` rendered as `"Send to Client"`
- Wrong sizing mode: `HUG/HUG` rendered as `FIXED/HUG`

Both slipped past the post-Sprint-1 verifier with "0 verifier
mismatches" reported. Investigation showed two coupled
architectural gaps:

1. **Verifier-side blind**: the verifier doesn't compare `characters`
   value (only empty/non-empty), and doesn't compare
   `layoutSizingHorizontal`/`Vertical` mode at all.
2. **Walker-side blind**: the walker (`render_test/walk_ref.js`)
   captures only ~17 of 50+ figma-emittable properties — fonts,
   padding, spacing, alignment, min/max sizing all uncaptured.
   Even adding verifier comparators for those would silently
   no-op against missing walker data.

Sprint 2 attempt-1 (commits `55cb211`, `a1e79e6`, `21fbf8d`)
addressed only the verifier-side gap. The user reframed:
*"this was the architectural audit i thought you were doing! doesn't
it make sense to have parity across all of these?"* — referring
to the four-station pipeline:

| Station | Component | Responsibility |
|---|---|---|
| 1 | Registry (`property_registry.py`) | Declares property + per-backend capability |
| 2 | Renderer (`renderers/figma.py`) | Emits via capability gate |
| 3 | Walker (`render_test/walk_ref.js`) | Reads back rendered values |
| 4 | Verifier (`verify_figma.py`) | Compares IR vs walker output |

Sprint 1 closed station 1→2 parity (capability table gates
emission). Stations 3 and 4 were left hand-rolled. The
"registry-as-single-source-of-truth" claim only held for
emission; the round-trip didn't verify it.

## 2. Sprint 2 thesis

> Sprint 2 is **not** "add more verifier checks". Sprint 2 is
> **make station parity explicit and registry-governed, then
> graduate only the smallest bug-closing slice**.

Future sprints (3, 4, ...) graduate additional families using
the rail Sprint 2 builds. Sprint 2 ships:

1. **The parity rail** — every property's disposition at every
   station is declared in the registry; generated artifacts
   (walker manifest) derive from it; tests fail when a property
   has undeclared disposition.
2. **Three graduated properties** — `characters`,
   `layoutSizingHorizontal`, `layoutSizingVertical` — closing
   the user-observed bug class.
3. **A1.1 descendant-path routing fix** — orthogonal real bug
   discovered during the cross-corpus investigation; included
   here because it's a prerequisite for the text-content
   graduation to actually emit overrides.

## 3. Station model

### Station 1 — Registry

Single source of truth. Every figma-emittable property is a
`FigmaProperty` entry with:

- `figma_name` — identity at the Figma backend
- `capabilities["figma"]` — frozenset of node types where the
  property applies
- `compare_figma` — Sprint 2 attempt-1 metadata for verifier
  dispatch (already exists post-C2)
- **Sprint 2 new**: per-station disposition fields (see §4)

### Station 2 — Renderer

Emits via capability table gate. Implementation:
`dd/renderers/figma.py`. Sprint 1 closed this; Sprint 2 doesn't
touch.

### Station 3 — Walker

Plugin JS executed via PROXY_EXECUTE in Figma desktop. Reads
live Figma DOM, returns per-node dict. Today hand-rolled. Sprint
2 makes it registry-derived: Python registry generates a
manifest (JSON), plugin-init injects, JS handlers remain
hand-written but accountability is registry-derived.

### Station 4 — Verifier

Compares IR vs walker output. Today hand-rolled. Sprint 2
attempt-1 added the comparator-spec metadata; Sprint 2 wires
dispatch from the registry.

## 4. Disposition vocabulary (locked per Codex)

Each station gets a typed status per property. Stored on
`FigmaProperty` (single source of truth, not a separate
manifest).

```python
class StationDisposition(enum.Enum):
    # Station 2 (renderer)
    EMIT_HANDLER         = "emit_handler"          # custom Python emit fn
    EMIT_UNIFORM         = "emit_uniform"          # _UNIFORM template
    EMIT_DEFERRED        = "emit_deferred"         # capability or context skip
    NOT_EMITTABLE        = "not_emittable"

    # Station 3 (walker)
    CAPTURED             = "captured"              # walker reads it
    NOT_CAPTURED_SUPPORTED = "not_captured_supported"  # walker COULD but doesn't
    NOT_CAPTURED_UNSUPPORTED = "not_captured_unsupported"  # Figma DOM doesn't expose
    DEDICATED_PATH       = "dedicated_path"        # captured via top-level fields, not figma_name

    # Station 4 (verifier)
    COMPARE_DISPATCH     = "compare_dispatch"      # via compare_figma in registry
    COMPARE_DEDICATED    = "compare_dedicated"     # via KIND_BOUNDS_MISMATCH etc
    EXEMPT_REASON        = "exempt_reason"         # documented exemption with code
```

**Definition of "graduated"** (Codex's contribution):

A property is **graduated** when it is:
1. Registered (Station 1, always true if it's in `PROPERTIES`)
2. Emitted or intentionally not-emitted (Station 2 disposition declared)
3. Captured with source semantics OR explicitly exempted (Station 3)
4. Compared via dispatch OR explicitly exempted (Station 4)
5. Covered by corpus regression sweep

This term keeps future sprints honest: no property should be
called "graduated" until all five conditions hold.

## 5. Registry authority

The registry is THE source of truth. Generated artifacts (walker
manifest JSON, etc.) derive from it. **Do not create a
JS-mirroring registry in walker.js — that recreates the drift
problem in a new place.**

Generation/validation contract:

- `dd/walker_manifest.py` (new) reads `PROPERTIES` and emits
  `render_test/walker_manifest.generated.json`
- A test in `tests/test_walker_manifest.py` generates and
  diff-checks it; CI fails if disk copy drifts from registry
- Plugin-init in walker reads the JSON, dispatches per-property
  to hand-written capture handlers
- Walker handlers stay JS (Figma DOM access isn't uniform —
  `n.fontSize` for some, `serializePaints(n.fills)` for others)
  but the dispatch table comes from the manifest

## 6. Walker capture semantics

**Locked: `(value, source)` tuples (Codex option B).**

Note: source tags are orthogonal to §4's station-3 disposition.
Disposition answers "does the walker capture this property at
all?"; source answers "for a captured value, was it set,
inherited, or computed?". A property can have disposition
`CAPTURED` and any source value at runtime.

Raw-value-only capture recreates today's noise in a new layer.
Source-tagged capture is the right architecture:

```json
{
  "fontSize": { "value": 16, "source": "set" },
  "paddingLeft": { "value": 0, "source": "computed_default" },
  "characters": { "value": "Reject", "source": "set" }
}
```

Source vocabulary:
- `set` — value was explicitly assigned (instance override or
  master default that's an explicit assignment)
- `computed_default` — Figma computed it from no-set + context
  (auto-layout default 0, etc.)
- `inherited` — value came from instance master not from
  override
- `unavailable` — Figma DOM doesn't expose this property on
  this node type (verifier should skip)
- `unknown` — transitional escape hatch only; reason recorded;
  verifier behavior conservative

Where Figma's API can't distinguish source cleanly (e.g. some
properties only expose value, not provenance), the JS handler
chooses the most conservative source tag and documents why.

This adds JS surface but eliminates a class of false-positives
that would otherwise turn the rail into noise.

## 7. Sprint 2 scope

**Sprint 2 graduates exactly three properties:**
- `characters`
- `layoutSizingHorizontal`
- `layoutSizingVertical`

Plus the orthogonal A1.1 descendant-path routing fix (text TEXT
overrides on instance descendants).

**Future sprints** (named in plan, not promised in scope):

| Sprint | Family | Properties |
|---|---|---|
| 3 | Auto-layout | paddingT/R/B/L, itemSpacing, counterAxisSpacing, layoutMode, primaryAxis/counterAxisAlignItems, layoutWrap, layoutPositioning |
| 4 | Text-styling | fontFamily, fontWeight, fontSize, fontStyle, lineHeight, letterSpacing, paragraphSpacing, textAlignH/V, textDecoration, textCase, textAutoResize, leadingTrim |
| 5 | Constrained sizing | minWidth, maxWidth, minHeight, maxHeight |
| 6 | Constraints | constraints.horizontal/vertical |
| 7+ | Low-frequency graduations | strokeCap, strokeJoin, cornerSmoothing, booleanOperation, arcData, etc. |

The rail Sprint 2 builds makes each future family-sprint a
cohesive unit (walker capture + verifier dispatch + corpus
regression for that family). Today they're scattered as
exemptions; the rail formalizes them as named work.

## 8. Commit ladder

C1-C3 already shipped at `21fbf8d`. They are **preparatory verifier
rail work**, not Sprint 2 deliverables — relabeled accordingly
(see §11 for revert plan).

The actual Sprint 2 work. Each commit cites which §-decision it
implements, so reviewers can audit the rail end-to-end:

| # | Title | Implements | Scope | Validates | Blocks |
|---|---|---|---|---|---|
| **C4** | Add station-disposition schema to FigmaProperty | §4 vocabulary + decision A | New StationDisposition enum + station_2/3/4 fields on FigmaProperty (defaults: NOT_EMITTABLE, NOT_CAPTURED_SUPPORTED, EXEMPT_REASON). No properties wired yet. | unit | C5 |
| **C5** | Inventory all properties at all four stations | §3 station model + decision A | Wire station_2/3/4 dispositions on every FigmaProperty. Metadata-only, no behavior change. Reviewable as the audit table. | unit | C6 |
| **C6** | Walker manifest generator + validation test | §5 registry authority + decision B | `dd/walker_manifest.py` generates `walker_manifest.generated.json` from registry; test diff-checks. **No plugin runtime changes yet.** | unit | C7 |
| **C7** | Plugin-init manifest injection + read path | §5 registry authority + decision B | Walker reads manifest at plugin init. Self-boot fallback retained. **No new captures yet.** | unit + sweep no-op | C8 |
| **C8** | Walker capture source envelope for graduated properties | §6 capture semantics + decision C + §7 scope | Add `(value, source)` capture for `characters`, `layoutSizingHorizontal`, `layoutSizingVertical`. Other captures unchanged. **Paired with C10 to keep behavior no-op until graduation** (§10 R2). | unit + sweep | C9 |
| **C9** | A1.1 descendant-path routing fix | (orthogonal real bug) | `_build_overrides_sidecar` handles `;<descendantPath>` rows for all `_INSTANCE_OVERRIDE_TO_FIGMA_NAME` entries. Behaviorally distinct from rail work; included because it's a prerequisite for text-content overrides to actually emit. | unit + sweep | C10 |
| **C10** | Verifier registry-dispatch for graduated properties | §3 station 4 + decision A | `FigmaRenderVerifier` consumes `compare_figma` for the 3 graduated properties; existing hand-rolled paths preserved for non-graduated. **Net comparison behavior changes here** (paired with C8). | unit + sweep | C11 |
| **C11** | All-corpus regression sweep + sprint results | §12 ship gate + decision D | Re-sweep Nouns + Dank + HGB. Confirm 3 verifier-only blind spots closed. Audit dir: `audit/sprint-2-station-parity-<timestamp>/`. Document which exemptions remain (and why). Update plan with Sprint 3 scope. | sweep | merge |

**Commits per Codex's structural correction**: C6 splits manifest
generation from plugin runtime injection — clean infra commit
before touching plugin behavior.

## 9. Subagent coordination

Per user directive ("remember to use codex and sonnet
subagents") and Sprint 1 lessons (parallel-write hazard).

### Codex 5.5 (architectural partner, singular per fork)

Consulted at:
- Plan authoring (this doc)
- Walker manifest format finalization (C6)
- Walker capture source-tag semantics finalization (C8)
- Verifier dispatch shape finalization (C10)
- Sprint 2 ship gate (C11)

Not consulted on:
- Mechanical metadata wiring (C4, C5 inventory)
- Test scaffolding
- Per-handler JS implementation details

### Sonnet workers (plural, parallel only on disjoint files)

Worker tasks identified for Sprint 2:
- C5 inventory: can be split by category if it gets large.
  Single worker is probably right (registry is one file).
- C6 + C7 manifest+plugin path: serial; same JS file.
- C8 walker handlers: could be split per-property (3 properties
  × 1 handler each) but trivial; main thread.
- C10 verifier dispatch: single file, main thread.

### Sonnet reviewers (after each main-thread commit)

Lightweight review pass:
- Spot-check cited files at cited lines
- Run the commit's claimed test count + claim no regression
- Flag anything that contradicts the commit message

### Parallel-work discipline (Sprint 1 lesson)

> Parallel work is allowed only when workers own disjoint files
> or disjoint handler families, and every worker states touched
> paths in the handoff. (Codex)

Main thread stays serial for:
- Registry schema (FigmaProperty)
- Manifest generation contract
- Verifier dispatch
- Shared test fixtures

## 10. Risk register

### R1 — Walker manifest injection breaks plugin init

If the manifest read fails, walker silently uses an empty
dispatch table, captures nothing, every screen DRIFTs.

**Mitigation**: walker keeps a self-boot fallback (today's
hard-coded behavior). Manifest read is additive. Test asserts
walker still works with empty manifest as smoke check.

### R2 — Default-vs-set semantics introduce more verifier drift than current surface

If walker captures `(value, source)` and verifier doesn't yet
know how to handle `computed_default`, every auto-layout
property might suddenly drift on Mode-1 INSTANCE.

**Mitigation**: ship walker capture WITH verifier dispatch in
the SAME commit (C8 + C10 paired) so net behavior is no-op until
graduation. Sprint 2 only graduates 3 properties; future-family
captures land in their respective sprints.

### R3 — Subagent parallel-write hazard (Sprint 1 lesson)

Two workers editing the same file produce auto-revert events
that silently roll back main-thread work.

**Mitigation**: file ownership stated in worker handoffs; main
thread serial when files overlap; reviewer subagents read
before writing.

### R4 — Inventory churn risk (Codex)

Categorizing 50+ properties at all four stations can become
semantic-design work that explodes the inventory commit (C5).

**Mitigation**: C5 may use conservative dispositions with
explicit TODO reasons. Graduation happens family-by-family in
later sprints. The inventory commit is an audit table, not a
design exercise.

## 11. Revert plan for mislabeled commits

C1-C3 (commits `55cb211`, `a1e79e6`, `21fbf8d`) were committed
under "Sprint 2 C1/C2/C3" labels but the sprint shape was
wrong. The work is correct and stays on the branch; the labels
are misleading.

Options considered:
- (a) Revert all three; recommit under correct labels (clean
  history, churns git)
- (b) Keep commits, document pivot in this plan (no churn,
  clear in plan doc)
- (c) Revert as cleanup commit referencing this plan

**Decision per user**: option (c) — revert mislabeled commits
with a single revert commit citing this plan. C1-C3 work then
re-lands as the new C0 (or merges into C4) under accurate
labels.

Specifically:
1. Land this plan doc as a commit
2. `git revert 21fbf8d a1e79e6 55cb211` — single chained revert
   commit
3. Begin Sprint 2 work (C4 onwards) under accurate labels

The reverted work isn't lost — it's still in git history at
`55cb211..21fbf8d`. C5 (inventory) and C10 (dispatch) will
reuse the same metadata shape, recommitted under correct
sprint framing.

## 12. Sprint 2 ship gate

Sprint 2 is shippable when:

1. ✅ Plan doc committed (this file)
2. ✅ Mislabeled commits reverted
3. C4-C11 all green
4. All-corpus regression sweep:
   - Nouns: still 100% structural parity
   - Dank: still 88.5% (23 VECTOR cornerRadius unchanged) OR
     better
   - HGB: 0 verifier mismatches OR new mismatches are real
     bugs (e.g. text content drift now visible after C8+C10)
5. The 3 graduated properties verified in unit tests AND in
   corpus reports
6. Codex 5.5 ship-gate review

Scope-creep guard: Sprint 2 graduates exactly the 3 properties
named in §7. If a Sprint 3 family looks tempting to bundle
mid-flight, **don't** — the cost-of-inventory and cost-of-
review-discipline argument that produced this plan still
holds. Bundle only if Codex 5.5 specifically retracts the §7
lock, in writing, in a follow-up call.

## 13. Out of scope for Sprint 2

Listed explicitly to prevent scope creep:

- VECTOR cornerRadius capability gap (separate one-line fix,
  noted in `audit/cross-corpus-20260427-190100/dank/FINDING-vector-cornerradius.md`)
- Auto-layout family graduations (Sprint 3)
- Text-styling family graduations (Sprint 4)
- Min/max sizing graduations (Sprint 5)
- Constraints model (Sprint 6)
- Mode-3 composition path verification (separate concern;
  Mode-3 doesn't go through extraction's _overrides chain)
- Multi-backend abstraction (deferred until backend #2 lands;
  current backend-shaped naming is the seam)

---

**Co-authored**: Claude Opus 4.7 (main thread) +
Codex 5.5 high-reasoning (architectural partner)
**Reviewed at draft**: Codex 5.5 round 5 architectural call +
Sonnet pre-commit review pass
