# Architectural flow matrix — Figma value extract→render across modes

**Date**: 2026-04-26
**Method**: 4 parallel agents (Codex 5.5 for extract + 3 Sonnet
Explore subagents for Mode 1/2/3) walked the same 8 diagnostic
property classes through every pipeline stage. Synthesis +
spot-verification by main thread (CONFIRMED claims read against
source).

**Goal**: surface architectural anti-patterns that produce repeat
bug instances ("issues we keep bumping into").

## Audit framework (Codex 5.5 design)

> Use **bug-class-driven primary** with a **per-mode comparison
> matrix** as display. Stages are useful columns, but recurring
> bugs aren't stage-local — they come from unclear contracts
> CROSSING stages.

Every value at every stage gets an **intent state** classification:
- passive snapshot
- explicit override
- explicit clear (e.g. `fills=[]`)
- inherited / no opinion (DB null)
- unsupported (Figma doesn't support on this node type)
- derived / synthesized

**Most recurring bugs are really failures to preserve or compare
intent state.**

## The 8 diagnostic property classes

1. **fills** — paint array (snapshot-vs-override class)
2. **strokes** — paint array (separate from strokeWeight)
3. **stroke-geometry** group — strokeWeight, strokeAlign, strokeDashes
4. **cornerRadius** — uniform OR per-corner
5. **opacity** — scalar with inheritance semantics
6. **layout container** group — layoutMode, padding*, itemSpacing, alignment
7. **typography** tuple — characters, fontFamily, fontStyle, fontSize, lineHeight
8. **vectorPaths** — encode-decode round-trip class

## Cross-cutting matrix (anti-patterns by class × mode × stage)

The anti-pattern matrix has too many cells to render here in
detail; the per-mode audits (Mode-1, Mode-2, Mode-3) carry the
full per-cell data. This synthesis surfaces **the patterns that
span audits** — the class-level architectural issues.

### Pattern A: Silent default leaks span all 3 modes

Three flavors:

- **Mode 1 opacity = 1.0 silently dropped** (CONFIRMED, line 1443):
  `if inst_opacity < 1.0: emit;` — IR opacity exactly 1.0 produces
  NO emission. Verifier can't distinguish "no opinion" from
  "explicitly 1.0." Same anti-pattern Codex flagged for
  strokeWeight registry.
- **Mode 2 hardcoded `fills = []` clear** (CONFIRMED, lines
  1075-1079): when visual dict is empty, frame/rectangle/ellipse/
  vector/bool nodes get explicit `fills=[]`. This bypasses the
  registry's per-node-type capability gate. Works today; brittle
  to new node types.
- **Mode 3 has no opacity in universal templates**
  (CONFIRMED): `_button_template`, `_card_template` don't carry
  opacity. Composed elements inherit Figma factory default 1.0.

Same root: **emission policy is "skip when no opinion" but no
mode signals "no opinion" distinctly from "matches default."**

### Pattern B: Snapshot-vs-override ambiguity is end-to-end

Confirmed across the entire pipeline:

- **Extract** (Codex audit): `instance_overrides` is the
  source-of-truth for explicit overrides, but it's populated
  ONLY by plugin supplement / unified extract paths — REST-only
  DBs have snapshots without provenance.
- **Encode** (`build_visual_from_db`, `_build_visual`): no
  override flag carried into IR. Verifier-side IR can't
  distinguish either.
- **Render** (Mode 1): emits OPACITY-when-nonzero, ROTATION,
  some text overrides. Skips fills/strokes/cornerRadius (delegate
  to master). Snapshot-vs-override decision happens implicitly
  via "did extraction record this in instance_overrides?" — but
  that signal never reaches the renderer.
- **Verifier**: existing narrow chip-1 suppression at
  `verify_figma:353-383` is the only place the asymmetry surfaces.

**This is the single largest architectural debt.** Documented in
`docs/plan-provenance-tagging.md` (Backlog #1). The forensic
audit confirms it spans every stage of the pipeline, not just
verifier.

### Pattern C: Coupled emission gates (the strokeWeight twin issue)

Multiple props get bundled together in single emission paths:

- **strokes + strokeWeight coupled** in `_emit_strokes()`
  (CONFIRMED — line 2505-2528): both emitted from single payload;
  strokeWeight extracted from `strokes[0].get("width")`. If
  strokes is empty, strokeWeight silently drops. Codex 5.5 flagged
  this as MUST FIX before provenance tagging lands.
- **Layout container props bundled** in `_emit_layout()`
  (CONFIRMED — lines 1085-1091): all six props
  (layoutMode/padding*/itemSpacing/align*) gated by single
  `if layout and not is_text` check. No per-property capability
  check in the bundled path; padding can land on TEXT nodes if
  the bundle gate accidentally passes.
- **Typography bundled across phases** (CONFIRMED): font props
  emitted in Phase 1; characters deferred to Phase 3. If Phase 1
  font emission throws, Phase 3 characters never reach
  assignments. No explicit phase-coordination signal.

**Fix shape**: split coupled emissions into independent gates per
property. This is also a precondition for provenance tagging
(per-property override flags require per-property emit gates).

### Pattern D: Mode 1's "delegate to master" is actually selective

Mode 1 audit's most useful finding:

- Mode 1 SKIPS: fills, strokes, cornerRadius, layoutMode,
  padding/itemSpacing, fontFamily/fontSize/fontStyle/lineHeight,
  vectorPaths
- Mode 1 EMITS: createInstance() result, name, swapComponent,
  resize/x/y/constraints, opacity (gated), rotation, characters
  (if `text_override` in element.props), visibility overrides
  (via PathOverride resolver)

The "delegate to master" framing in
`feedback_fill_mismatch_instance_suppression.md` is right for
fills/strokes/cornerRadius/layoutMode/typography. But Mode 1 DOES
emit some props unconditionally (resize, position, constraints) —
which are all ALSO snapshot-vs-override candidates. **The
narrative needs sharpening**: Mode 1 doesn't delegate everything
to the master; it delegates *visual paint properties* and
*self-contained text* but always re-asserts *position +
geometry*.

This matters for the provenance plan: width/height need per-axis
gating per Codex's Q4 advice. Same logic applies to position
(x/y) — currently unconditional, should be gated on instance
override presence too.

### Pattern E: Mode 3 has its own dispatch fragility

Mode-3 audit found 6 distinct anti-patterns NOT seen in Mode 1/2:

1. **Variant downgrade on label mismatch** (CONFIRMED): when LLM
   requests `variant: "primary"` but the catalog only has
   `custom_1` bindings, ProjectCKRProvider returns a default
   template (and emits `KIND_VARIANT_BINDING_MISSING` to
   `__errors__`, but the visual fallback IS silent — verified
   by reading `dd/composition/providers/project_ckr.py:115-162`).
2. **Slot-binding query skips slot-coverage validation**:
   bindings for slot=`label` returned even if template declares
   `[headline, supporting]`. Mismatched slots silently use
   universal defaults.
3. **Compose-time token overlay irreversible**: project tokens
   baked into IR at compose time; downstream changes invisible.
4. **Label-hoist wrapper ignores parent layout direction**:
   `compose.py:396-419` hardcoded `direction="vertical"` for
   the wrapper, may violate parent's `layout_direction="horizontal"`.
5. **Typography inheritance unidirectional**: child can't
   override parent template typography per variant.
6. **stroke-geometry not in PresentationTemplate schema** at all:
   strokeWeight/strokeAlign/strokeDashes have no Mode 3 surface.
   Always inherits whatever the catalog template sets (currently
   nothing → Figma factory).

### Pattern F: Encode-decode asymmetries (mostly addressed but two open)

Per Codex extract audit:

- **vectorPaths**: round-trip fix shipped; per-winding-rule
  preservation works. But legacy `svg_data` path is documented
  as lossy.
- **gradientHandlePositions vs gradientTransform**: BOTH stored
  in IR; no guard verifying each renderer picks the right one.
  Probable risk; not yet observed.
- **Multi-side stroke weights** (per-side `stroke_top_weight`
  etc.): stored as scalar columns, not registry properties; no
  override provenance possible. **Backlog #2 (0-weight-with-strokes)
  may be related to this.**
- **Image strokes**: extract code reads image hashes from FILLS
  only, not STROKES. Image strokes survive DB/IR but
  asset extraction never fetches the bytes. Verifier blind to
  any image-stroke drift.

### Pattern G: Verifier coverage gaps remain (post-P1)

P1 closed comparators for opacity/blendMode/rotation/isMask/
cornerRadius. Still not compared:

- strokeWeight (carried in IR, not compared)
- strokeAlign (same)
- dashPattern (same)
- clipsContent (same)
- per-side stroke weights (no IR shape at all)
- effect content (count compared via KIND_EFFECT_MISSING; specific
  effect properties not)
- token-bound colors that resolve at render time (verifier compares
  hex; if token resolution differs it's a wash)

## Architectural anti-patterns to fix systematically

Synthesized across all 4 audits:

| # | Anti-pattern | Severity | Where it bites |
|---|-------------|----------|----------------|
| **A1** | Snapshot-vs-override ambiguity not preserved end-to-end | MUST FIX (planned: Backlog #1) | All Mode-1 instances |
| **A2** | Coupled emission gates (strokes+strokeWeight, layout bundle, typography phases) | MUST FIX before A1 ships | Provenance gating impossible without splitting |
| **A3** | Silent default leaks (opacity=1.0, hardcoded fill clears, missing template props) | SHOULD FIX | Across all modes |
| **A4** | Mode 3 variant downgrade silent visual fallback | SHOULD FIX | Mode 3 specifically; affects design quality |
| **A5** | Verifier comparator coverage gaps for already-carried IR props | SHOULD FIX | Surfaces drift on strokeWeight/clipsContent/etc. |
| **A6** | Mode 1 selective emission narrative is too coarse (geometry vs paint) | FYI / docs | Affects provenance plan width/height handling |
| **A7** | Image strokes never asset-extracted | LOW | 0 confirmed cases on Nouns; theoretical |
| **A8** | gradientHandlePositions vs gradientTransform pick logic unguarded | LOW | No confirmed drift; defensive |

## Recommendations for Backlog #1 (provenance plan) revision

The audit confirms the provenance plan's design but adds
implementation order:

1. **First**: A2 — split coupled emission gates. Required
   precondition. Codex already flagged `_emit_strokes()` split.
   Add: split `_emit_layout()` to per-property capability checks;
   coordinate Phase 1 ↔ Phase 3 typography emission with explicit
   error-on-incomplete signal.
2. **Then**: Backlog #1 as planned (per-property `_overrides`
   side-car).
3. **Then**: A5 — wire verifier comparators for the already-carried
   IR props. Provenance lets these comparators distinguish
   override-from-snapshot, otherwise we repeat the chip-1 narrow
   suppression for each new comparator.
4. **Defer**: A4, A7, A8 — narrower scope; address as separate
   tickets.

## Sources

- 3 Sonnet Explore agents (Mode 1, Mode 2, Mode 3): output in
  `/private/tmp/claude-501/.../tasks/{a87a06f8...,a3780e97...,abfc1d65...}.output`
- Codex 5.5 extract audit:
  thread `019dcc47-ba96-7e40-a29e-0237ce9d5795`
- Codex 5.5 framework consult:
  thread `019dcc45-5597-7251-81fd-2cdc173d4f85`
- Spot-verifications: `dd/render_figma_ast.py:1075-1079, 1443`,
  `dd/composition/providers/project_ckr.py:115-162` — all confirmed
  via direct read.
