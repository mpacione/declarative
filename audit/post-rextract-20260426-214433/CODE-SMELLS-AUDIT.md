# Forensic audit #2 — code smells across the pipeline

**Run**: 2026-04-26 ~14:55 PT
**Method**: 4 parallel `Explore` subagents, each scoped to a distinct
smell class. Each finding required CONFIRMED status (read the actual
code at the cited line). Cross-cutting synthesis follows.

## Why a second audit?

The first audit (earlier this session) was scoped to **silent property
drops** between extract and emit. It found the gradient-stroke
3-layer drop. After fixing that and re-extracting Nouns, the sweep
revealed 17 new DRIFT screens — all caused by a *different class*
of bug: dispatch fall-through and verifier blindness. The user
asked: "are there other 'code smell' issues we can look for?"

Yes — at least four classes. This audit found 13 distinct issues,
all but two CONFIRMED via direct source read.

## Cross-cutting pattern: **gates without re-validation**

Three of the four audits independently surface the same architectural
anti-pattern, just at different layers:

> **A dispatch decision is made at one point, then prop writes
> downstream assume the gate's path is still right — but no one
> verifies that assumption at emit time, and the verifier gets no
> signal when the gate silently flips.**

Concrete instances:

- **Audit #2a finding 1**: Mode-1 vs Mode-2 dispatch (line 840-883).
  Gate: `component_figma_id or instance_figma_node_id or component_key`.
  Failure mode: silent fall-through to `createFrame()`. No error.
- **Audit #2a finding 2**: bool-op skip (line 939). After
  `figma.union`, only name + M[] + z-order replayed. Visual props
  never emitted.
- **Audit #2a finding 5**: Override resolver no-op (line 1509).
  `if (_t)` with no fallback when `map.get` returns undefined.
- **Audit #2b finding 1**: strokeWeight registry has no
  `default_value`. Visual.py:162 skips emission. Figma factory `1.0`
  persists. IR null → renderer silent → DB doesn't know to flag it.
- **Audit #2d (the big one)**: `_build_visual` in `ir.py:464` carries
  fills/strokes/effects only. Renderer emits opacity/blendMode/
  rotation/isMask/cornerRadius via the registry-driven path, but
  the verifier-side IR doesn't carry them, so verifier can't check
  drift. **The 17 newly-revealed DRIFT screens post-rextract are
  the visible tip of this iceberg** — when Mode-1 finally fired
  correctly, the verifier started looking at the right nodes and
  caught the fill/stroke drift that was always present.

## Findings (consolidated)

### Confirmed (read the code, the bug is unambiguous)

| # | Smell class | Site | Mechanism | Severity |
|---|---|---|---|---|
| 1 | dispatch fall-through | `dd/render_figma_ast.py:840-883` | Mode-1 → Mode-2 silent fall-through; no `__errors.push` on gate failure | HIGH |
| 2 | bool-op skip without replay | `dd/render_figma_ast.py:939, 1896` | `continue` in main loop; post-materialization only re-emits name + M[] + z-order. Visual props never replayed. | HIGH (10 screens DRIFT) |
| 3 | name-based override resolver | `dd/render_figma_ast.py:1455, 1468` | `resolver_bucket.get(prop.path)` keyed on name string; duplicate-name children → wrong target | MEDIUM (7 iPhone screens) |
| 4 | stale-CKR re-route invisibility | `dd/render_figma_ast.py:841` | If CKR row changes between IR build and render, gate silently re-routes to Mode 2 | MEDIUM |
| 5 | silent override no-op | `dd/render_figma_ast.py:1509` | `if (_t) ...` with no fallback when `map.get` returns undefined | LOW (logged via the path-resolver pattern) |
| 6 | strokeWeight silent default leak | `dd/property_registry.py:99-102` + `dd/visual.py:162` | No `default_value` in registry; null skips emission; Figma factory `1.0` persists | HIGH (potentially 26K nodes) |
| 7 | clipsContent double-emit | `dd/render_figma_ast.py:1037, 1069, 1083-1087, 1090, 1093` | Two emission paths fire on the same node; idempotent but ~5KB wasted JS per render | LOW (cosmetic) |
| 8 | verifier-blind: opacity | `dd/ir.py:464-485` (`_build_visual`) | Renderer emits via registry; verifier-side IR omits. `is_parity: True` masks opacity drift | HIGH (architectural) |
| 9 | verifier-blind: blendMode | same | same | HIGH (architectural) |
| 10 | verifier-blind: rotation | same; walker captures (`walk_ref.js:233-238`) but verifier doesn't compare | half-instrumented | HIGH (architectural) |
| 11 | verifier-blind: isMask | same | same | MEDIUM |
| 12 | verifier-blind: cornerRadius | `dd/visual.py:129-136` populates render side; `dd/ir.py:_build_visual` omits | half-instrumented | MEDIUM |

### Probable (logical inference; needs spot-check before fixing)

| # | Smell class | Site | Mechanism |
|---|---|---|---|
| 13 | gradientHandlePositions vs gradientTransform pick-the-right-one | `dd/ir.py:88-102` | IR carries both REST and Plugin representations; no guard verifies each renderer picks the right one for its target backend |

### Refuted by audit

- vectorPath round-trip — was broken; PATCHED. Format is now compatible with Plugin API setter.
- rotation/mirror decompose — math is sound and tested.
- GROUP appendChild — safeguard prevents orphaning.
- Text characters — properly escaped.
- REST→DB field mapping — centralized in `figma_api.py`; no per-module divergence.

## Recommended fix shape

Three priorities, in order:

### Priority 1 — verifier coverage (the architectural fix that matters most)

Port the registry-driven approach from `dd/visual.py:build_visual_from_db`
into `dd/ir.py:_build_visual`. Every property with `category == "visual"`
in `PROPERTIES` should land in the verifier-side IR's `visual` dict.
Add corresponding verifier checks in `dd/verify_figma.py` with proper
KIND_* classes:

- `KIND_OPACITY_MISMATCH`
- `KIND_BLENDMODE_MISMATCH`
- `KIND_ROTATION_MISMATCH` (walker already captures; just add the compare)
- `KIND_MASK_MISMATCH`
- `KIND_CORNERRADIUS_MISMATCH`

This single change closes findings 8-12 simultaneously and provides
the signal channel needed to surface dispatch-fall-through bugs (#1,
#3, #4, #5) — the verifier will start catching the silent failures.

**Estimated: 200-300 LOC + tests.**

### Priority 2 — bool-op visual replay (follow-on #1)

Already filed earlier. Add visual prop emission after
`figma.union/subtract/intersect/exclude` materialization.
**Estimated: ~50 LOC + tests, ~3 screens recovered immediately.**

### Priority 3 — Mode-1 override targeting (follow-on #2)

Migrate `descendant_visibility_resolver` from name-based path lookup
to id-stable lookup (mirror `feedback_hidden_children_broken_path.md`
which did the same migration for hidden_children).
**Estimated: ~150 LOC + tests, ~7 screens recovered.**

### Priority 4 — strokeWeight default leak (registry hygiene)

Add `default_value=1.0` to the strokeWeight `FigmaProperty` in
`dd/property_registry.py`. Impacts 26K nodes potentially. Test the
change against a small fixture before re-extracting.
**Estimated: 10 LOC + tests.**

### Priority 5 — explicit dispatch-failure errors (architectural)

The root pattern. When Mode-1 dispatch silently fails, emit
`__errors.push({eid, kind:"mode1_dispatch_failed", reason})`
instead of falling through. Same for any other gate. Verifier
gets the signal; we stop hiding bugs.
**Estimated: ~50 LOC + verifier walker integration.**

## Coverage / no-go zones

The audits found a few things that LOOK like smells but aren't:

- **clipsContent double-emit** — idempotent; cosmetic optimization
  only; not a correctness bug. Skip unless you're optimizing JS
  payload size.
- **`fails open not closed` normalization** (per existing memory) —
  audit confirmed this principle is correctly applied.
- **per-platform default fills** — the existing fix from
  `feedback_default_fills_per_platform.md` is in place and correct.

## Verification metadata

All findings tagged with file:line. Each subagent was instructed to
NEVER cite without reading. Critical claims spot-checked by me:

- `_build_visual` at `dd/ir.py:397` confirmed to carry only
  fills/strokes/effects (verified earlier this session)
- Bool-op `continue` at `dd/render_figma_ast.py:939` confirmed
  by direct read (Codex 5.5 also independently verified)
- Mode-1 gate at `dd/render_figma_ast.py:840-883` not yet personally
  spot-checked; flagging as TODO before any fix work begins
