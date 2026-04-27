# Plan: Override-vs-snapshot provenance tagging for Mode-1 INSTANCE heads

**Status**: design ready, implementation pending
**Author**: Claude (Sonnet 4.5) + Codex 5.5 review (2026-04-26)
**Blocks**: closing the 15 remaining DRIFT screens on Nouns
(8 fill_mismatch + 7 stroke_mismatch on Mode-1 INSTANCE heads)
**Estimated**: 200–400 LOC + tests + a single re-extract

## Problem

After the forensic-audit-2 sprint (commits `93b3d14..b7483a8`),
the Nouns post-rextract sweep has **15 remaining DRIFT screens**
all attributed to a single class:

> The IR carries an *extraction snapshot* of an instance's
> fills/strokes/etc. (the master's defaults observed at extraction
> time). The runtime master defaults differ. The verifier compares
> the snapshot to the runtime render and flags a mismatch. But
> there's no actual override — the renderer correctly delegates to
> the master.

Concrete example (node `id=5965` on screen 50, "States/Selected
Background"):

```
DB:                            instance_overrides:
  strokes = [#222529 SOLID]      STROKE_WEIGHT  (override_value=2)
  stroke_weight = 2              FILLS, OPACITY, CORNER_RADIUS,
                                 INSTANCE_SWAP, HEIGHT, WIDTH
                                 (NO STROKES row)

Rendered:
  strokes = [#FFFFFF SOLID]  ← runtime master default
  strokeWeight = 2           ← override applied correctly

Verifier:
  → KIND_STROKE_MISMATCH (IR=#222529 vs rendered=#FFFFFF)
```

The verifier has no signal that `strokes` is a passive snapshot
while `strokeWeight` is a real override.

## Existing partial fix (insufficient)

`feedback_fill_mismatch_instance_suppression.md` documented a
NARROW suppression rule for one specific shape: skip
`fill_mismatch` when rendered is INSTANCE AND IR has no solid
fills AND all IR fills are gradient-* with token-ref colors. That
cleared 3 chip-1 cases on Phase E. It does NOT cover:

- INSTANCE + solid IR fills + solid rendered fills (the 8
  fill_mismatch cases)
- INSTANCE + solid IR strokes + solid rendered strokes (the 7
  stroke_mismatch cases)
- Any future visual prop comparator the verifier learns

## Design

**Source of truth**: the existing `instance_overrides` table.
Per-property rows (FILLS, STROKES, STROKE_WEIGHT, OPACITY, …)
record the visual properties that were genuinely overridden at
extraction time. **Presence of a row = override.** **Absence on a
Mode-1 INSTANCE head = snapshot.**

This already exists; no schema change needed.

**Transport**: a new IR side-car field `element["_overrides"]:
list[str]` carrying the canonical figma property names (registry
keys) that have override rows for this node. Examples:

```json
{
  "type": "instance",
  "visual": {
    "fills": [...],
    "strokes": [...],
    "strokeWeight": 2
  },
  "_overrides": ["strokeWeight", "cornerRadius", "opacity", "width", "height"]
}
```

The IR `visual` dict still carries every observed value (snapshot
or override — same shape as today). Provenance is the side-car.

**Renderer rule** (Mode-1 INSTANCE successfully materialized):
- For each prop in `_overrides`: emit the prop write after
  `createInstance()`.
- For props NOT in `_overrides`: skip emission.
- This applies to fills, strokes, strokeWeight, opacity,
  cornerRadius, width, height, etc.

**Verifier rule** (Mode-1 INSTANCE successfully rendered):
- For each visual-prop comparator: check if the prop is in
  `_overrides`. If not, skip the comparison (it's a snapshot).
- If the prop IS in `_overrides`, compare normally and emit
  KIND_*_MISMATCH on drift.

**Critical scope rule** (per Codex 5.5): provenance gating
applies ONLY when the rendered node is actually an `INSTANCE`.
If Mode 1 fell back (createInstance failed → frame placeholder,
or `_missingComponentPlaceholder`), the snapshot becomes the
only reconstruction data and must be emitted normally. The
gating predicate is:

```python
if rendered.type == "INSTANCE" and prop_name not in overrides:
    skip
```

## Mapping `instance_overrides.property_type` → registry figma_name

| `property_type`   | figma_name        |
|-------------------|-------------------|
| FILLS             | `fills`           |
| STROKES           | `strokes`         |
| STROKE_WEIGHT     | `strokeWeight`    |
| EFFECTS           | `effects`         |
| CORNER_RADIUS     | `cornerRadius`    |
| OPACITY           | `opacity`         |
| BLEND_MODE        | `blendMode`       |
| CLIPS_CONTENT     | `clipsContent`    |
| WIDTH             | `width`           |
| HEIGHT            | `height`          |
| TEXT              | `characters`      |
| FONT_SIZE         | `fontSize`        |
| FONT_FAMILY       | `fontFamily`      |
| LAYOUT_SIZING_V   | `layoutSizingVertical` |
| BOOLEAN           | (visibility — special; already handled by PathOverride) |
| INSTANCE_SWAP     | (special; not a visual prop) |

Build the inverse map once in `dd/property_registry.py` (or a new
small module) so renderer + verifier + IR builder all agree.

## Implementation plan (TDD)

### Step 1 — IR side-car

- `dd/ir.py:map_node_to_element` (or `query_screen_for_ir`): join
  `instance_overrides` for INSTANCE node_ids; populate
  `element["_overrides"]` as the list of figma_names.
- Test: synthetic node with FILLS + STROKE_WEIGHT override rows
  produces `_overrides = ["fills", "strokeWeight"]`.
- Test: a non-INSTANCE node (e.g. a plain frame) gets no
  `_overrides` field.
- Test: an INSTANCE node with no override rows gets
  `_overrides = []` (explicit empty, not absent).

### Step 2 — Renderer gating

- Find the Mode-1 emission site in
  `dd/render_figma_ast.py:_emit_mode1_create`. Currently after
  `createInstance()` it emits name, swapComponent, then
  unconditional `resize()` and other prop writes.
- Refactor to check `_overrides` per prop. Codex caveat: split
  `_emit_strokes()` so `strokes` and `strokeWeight` have
  independent emission gates.
- Width/height: emit axis-specific resize:
  - both in `_overrides` → `resize(w, h)`
  - only `width` → `resize(w, node.height)`
  - only `height` → `resize(node.width, h)`
  - neither → no resize
- Test: instance with `_overrides=["strokeWeight"]` only emits
  `n.strokeWeight = 2;` and NOT `n.strokes = [...]`.
- Test: instance with `_overrides=[]` skips all visual writes.
- Test: instance with `_overrides=["fills","strokeWeight"]` emits
  both.

### Step 3 — Verifier gating

- `dd/verify_figma.py`: for each visual-prop comparator, add a
  guard:
  ```python
  if (
      rendered.get("type") == "INSTANCE"
      and prop_name not in (element.get("_overrides") or [])
  ):
      continue  # snapshot, not override — skip comparison
  ```
- Apply to: fills, strokes, strokeWeight, effects, cornerRadius,
  opacity, blendMode, isMask, rotation comparators.
- Test: mismatch on Mode-1 INSTANCE WITHOUT override → no
  KIND_*_MISMATCH.
- Test: mismatch on Mode-1 INSTANCE WITH override → KIND_*_MISMATCH
  fires (the override didn't take, real bug).
- Test: mismatch on non-INSTANCE → KIND_*_MISMATCH fires
  (regression guard).
- Remove the existing narrow chip-1 suppression at
  `dd/verify_figma.py:353-383` — it's subsumed by the new
  per-property gate.

### Step 4 — Re-extract + sweep + measure

- The existing canonical Nouns DB at `/tmp/nouns-postrextract.db`
  already has the `instance_overrides` rows populated; no
  re-extract needed for the data.
- Run sweep against `/tmp/nouns-postrextract.db`; expect:
  - 8 fill_mismatch → 0 (or much lower)
  - 7 stroke_mismatch → 0
  - 26 cornerradius_mismatch → either drops if cornerRadius
    overrides are absent, or stays where the override IS present
    and we have a real override-not-applied bug
  - Other prop comparators may surface new real bugs (good — that's
    the architectural value)

## Open questions before implementation

1. **Where does the `_overrides` extraction happen?** Probably
   `query_screen_for_ir` since it's already the IR-build entry
   point and has a connection. Could also be a separate
   side-car-builder pattern (like `descendant_visibility_resolver`).

2. **Backward compat**: existing scripts in `audit/.../scripts/*.js`
   were generated without provenance. They'll continue to drift.
   Acceptable — we don't re-render historical artifacts.

3. **Cross-renderer impact**: react/swiftui/etc backends will need
   to consume `_overrides` too. Consistent with the
   "renderer-agnostic IR" principle. Not in scope for this
   ticket; document the contract.

4. **When `_overrides` is absent (legacy IR)**: gates default to
   "treat as override" — safer to over-emit / over-flag than the
   reverse. Decode-on-old-data must be tolerant.

## Risk assessment

- **MEDIUM**: removing the narrow chip-1 suppression. Need to
  confirm the new per-property gate covers all the same cases.
  Test the chip-1 fixture explicitly.
- **MEDIUM**: width/height refactor blast radius. Layout code
  reads pixel bounds; conditional resize might surprise some
  consumer. Codex flagged this as "higher blast radius than paint
  props." Migrate carefully with regression guards.
- **LOW**: introducing `_overrides` as a new IR field. Adding a
  side-car is non-breaking; existing readers ignore unknown keys.

## Acceptance gates (in order)

1. Step 1 ships: `_overrides` populated on every INSTANCE in IR.
   Test the inverse property_type → figma_name mapping is
   complete (no UNKNOWN).
2. Step 2 ships: at least one fixture screen with mixed
   override+snapshot demonstrates correct selective emission.
3. Step 3 ships: chip-1 + iPhone-50 fixtures both pass without
   the narrow suppression.
4. Step 4 ships: full Nouns sweep shows ≤5 DRIFT screens (down
   from 15). Any remaining drift is a new class worth filing
   separately.

## Codex-flagged catches

- `_emit_strokes()` currently emits both `strokes` and
  `strokeWeight` from the strokes payload. **Must split** for
  independent provenance gating.
- Width/height needs **per-axis** resize (not unconditional
  `resize(w, h)` when only one axis is overridden).
- Provenance gating ONLY when the rendered node is actually an
  `INSTANCE`. Mode-1-fell-back-to-frame paths must emit normally.

## References

- `audit/post-rextract-20260426-214433/CODE-SMELLS-AUDIT.md` —
  forensic audit #2 synthesis
- `audit/sprint-final-20260426-230449/SPRINT-RESULTS.md` —
  results showing the 15 remaining DRIFT cases
- `feedback_fill_mismatch_instance_suppression.md` — earlier
  narrow suppression that this plan supersedes
- `feedback_verifier_blind_to_visual_loss.md` — the broader
  architectural principle
- Codex 5.5 design reviews: 2026-04-26 threads at
  `019dcc3c-e6cd-78d2-b973-2b3ddff1032b` (Q1+Q2) and
  `019dcc40-fd15-7a41-b5e7-5614218afecd` (refinement).
