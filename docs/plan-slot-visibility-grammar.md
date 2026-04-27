# Plan — Slot-Visibility Grammar

**Status**: **PR 2 (Stages 1–5) shipped 2026-04-22** — commits `0e8aeb5`, `e977ecc`, `6ddf098`, `bc193a4`. **PR 1 in flight** (subagent `a7085f02af8acd030`, isolated worktree) — unified visibility resolver + production wiring in `generate_figma_script` + `hidden_children` removal.
**Rollback tags**: `f1fa345` (pre-slot-visibility-arc); `bc193a4` (PR 2 done, PR 1 not started).
**Cross-refs**: [plan-v0.3.md](plan-v0.3.md), [plan-type-role-split.md](plan-type-role-split.md), [spec-dd-markup-grammar.md](spec-dd-markup-grammar.md), [continuation-slot-visibility-grammar-next.md](continuation-slot-visibility-grammar-next.md). Memory: `project_slot_visibility_grammar.md`, `feedback_hidden_children_broken_path.md`, `feedback_phase1_perf_wins.md`, `feedback_verifier_blind_to_visual_loss.md`, `feedback_override_decomposition.md`.

## 1. Problem

The Phase-1 sweep on 2026-04-22 put a large batch of rendered screens in front of the user for the first time. Visible defect: top-nav content missing across many screens. Specifically:

- DANK wordmark missing (present in source)
- Workshop button missing
- Meme-00001 dropdown missing
- Nav right-slot share icon missing
- Toolbar row-2 leading icons (brush-lines, opacity-disc, brush-cap) missing

All rendered screens passed the structural verifier (`is_parity=True`). This is the class documented in [feedback_verifier_blind_to_visual_loss.md](../memory/feedback_verifier_blind_to_visual_loss.md).

### 1.1 Root cause

`dd/ir.py:670-687` computes per-INSTANCE `hidden_children` by SQL-harvesting all `nodes.visible = 0` descendants, keyed by `name`. The renderer emits:

```js
{ const _h = n9.findOne(n => n.name === "logo/dank"); if (_h) _h.visible = false; }
```

Figma's `findOne(name)` returns the FIRST match. When a component master has two same-named descendants (common: `nav/top-nav` has two `logo/dank` children — one in the Workshop-button slot, one in the wordmark slot), the wrong one is hit. The visible sibling gets hidden; the already-hidden sibling stays hidden; net zero `logo/dank` rendered.

The bug is pre-existing. Regenerating against the `pre-type-role-split` tag (before the current session) emits the identical broken code. It surfaces now because the Phase-1 sweep is the first large batch of renders the user has visually inspected.

### 1.2 Why this keeps happening

The renderer has TWO descendant-override paths running in parallel:

| Path | Source | Addressing | Status |
|---|---|---|---|
| `hidden_children` | `nodes.visible = 0` harvest | `findOne(name)` | **BROKEN** |
| `override_tree` | `instance_overrides` table | `id.endsWith(";<nid>")` | **WORKS** |

The `instance_overrides` table (20,803 BOOLEAN rows on Dank-EXP-02) already carries per-descendant visibility with Plugin-API-authoritative stable-id addressing. Property-name format: `;<figmaNodeId>:visible` and `:self:visible`; override_value is `'true'`/`'false'` string. The `hidden_children` harvest is a redundant SQL-side parallel pipeline that doesn't use the correct ground-truth data.

## 2. Prior-art summary (research 2026-04-22)

| Family | Representative | Slot visibility expression | Addressing |
|---|---|---|---|
| Design-to-code with master-diff | Figma, Penpot | Override on descendant in instance | Stable descendant id OR slot-path |
| Web-native component | Web Components, React, Vue, Svelte | Conditional render (`{condition && <X/>}`, `v-if`, `{#if}`) | No master concept; slot is a prop |
| Visual page builders | Plasmic, Mitosis, Webstudio | Conditional prop + slot-null | Slot name + element id |
| Mobile-native | SwiftUI, Jetpack Compose | `EmptyView()` / null slot / `if` inside slot body | Slot parameter |

**Key finding**: Figma and Penpot are the ONLY models with clone-tree + diff override semantics. Everything else renders outside-in (no master-diff concept) and expresses absence as conditional render or slot-null.

The grammar form we adopt must (1) round-trip losslessly through dd-markup, (2) compute from an IR-level diff without consulting any backend, (3) be re-emittable by an LLM from master signature + intended change, (4) carry enough info for each backend adapter to pick its native representation.

## 3. Grammar decision (locked)

Two primitives, no new keywords.

### 3.1 PathOverride with `.visible = false`

The existing prop-override syntax already reaches `.visible` as a reachable property. Form:

```
-> nav/top-nav {
  left.logo/dank.visible = false
  right.button/small/translucent.visible = false
}
```

This is the **canonical** form. It computes from the instance-override diff directly; LLM can emit it from the master signature; every backend can lower it.

### 3.2 `{empty}` SlotFill sentinel (syntactic sugar)

Equivalent sugar for the most common case — a named slot that the author intentionally left empty:

```
@top-nav(type=instance) {
  left = @logo-dank(type=instance)
  right = {empty}
}
```

At parse time, `{empty}` lowers to a PathOverride setting the slot's default child `.visible = false`. Purely syntactic; no new AST node; no change to the renderer contract. It exists because the LLM is more likely to generate `right = {empty}` than to know the correct descendant id for a PathOverride.

### 3.3 Rejected: dedicated `hide` keyword (Option B)

Rejected. PathOverride already carries the information. A second surface form would split the grammar and fork backend lowering without adding expressiveness.

## 4. Key invariant

> Visibility must be expressed as a structural override keyed by stable descendant identity (path + spec-key or slot name), not by Figma-runtime node ids or by mutation side-effects.

Four properties any grammar form must satisfy:

1. **Survives compress → markup → parse** with identity preserved.
2. **Computable from an IR-level diff** (master vs instance) without consulting any backend.
3. **Re-emittable by an LLM** given only the master's `define` signature and the intended visual change. No runtime ids leak into the grammar surface.
4. **Carries enough information** for each backend adapter to pick its native representation (Figma override array / React conditional / SwiftUI EmptyView / Compose null-slot).

The current `findOne(name)` emission fails invariant 3 (naming ambiguity under same-name siblings). The new PathOverride form keyed by slot-path + spec-key passes all four.

## 5. PR 1 — data layer (delete broken path)

**Target**: PARITY maintained on 190/204 Dank sweep. Top-nav content visibly renders on all screens.
**Estimate**: 4-6h.
**Rollback**: `pre-slot-visibility-pr1`.

### 5.1 Scope

Remove `hidden_children` parallel pipeline. `override_tree` + `instance_overrides` already carries the correct data with stable-id addressing.

### 5.2 Files touched

- `dd/ir.py:670-687` — delete `hidden_children` harvest.
- `dd/render_figma_ast.py:895-901` — delete `findOne(name)` emission loop.
- `dd/renderers/figma.py:1214-1220` — delete twin emission loop.
- Any call site consuming `element.hidden_children` — check + clean.

### 5.3 TDD stages

| Stage | Red | Green |
|---|---|---|
| 1 | Test: regenerate screen with `nav/top-nav` + verify emitted JS contains NO `findOne(n => n.name === ...)` for visibility | Delete `hidden_children` field wiring |
| 2 | Test: round-trip sweep ≥190/204 PARITY | Run `dd render-all` |
| 3 | Test: visual inspect one top-nav-heavy screen + assert wordmark present via walk_ref | Fix any gap from override_tree path |

### 5.4 Acceptance gate

- Round-trip sweep: ≥ 190/204 PARITY.
- Visual inspect on 3 screens with same-name siblings: no missing content that used to render as phantom-missing.
- `grep 'findOne.*name ===.*visible' dd/` returns zero hits.

## 6. PR 2 — grammar extension

**Target**: PathOverride `.visible=false` + `{empty}` SlotFill sugar flow end-to-end. Multi-backend stub tests confirm cross-backend survival.
**Estimate**: ~2 days.
**Rollback**: `pre-slot-visibility-pr2`.

### 6.1 Scope

Lift visibility into the grammar surface. Compressor emits PathOverride when instance-override `visible` diff detected. Renderer lowers PathOverride `.visible` to native. Same arc for `{empty}` SlotFill sugar.

### 6.2 Files touched

- `dd/markup_l3.py` — grammar: PathOverride parsing already exists; verify `.visible` passes through. Add `{empty}` parse rule.
- `dd/compress_l3.py` — emit PathOverride on visibility diff (replaces whatever PR 1 left).
- `dd/render_figma_ast.py` + `dd/renderers/figma.py` — lower PathOverride `.visible=false` to Figma: `n.findOne(n => n.id.endsWith(";<nid>")).visible = false`. Lower `{empty}` to same.
- `dd/ir.py` — `_lift_overrides` or equivalent: compute PathOverride from instance_overrides table. Existing `build_override_tree` already does the hard work; just extend to include `visible`.

### 6.3 TDD stages

| Stage | Red | Green |
|---|---|---|
| 1 | Parser test: `right.icon/share.visible = false` parses as PathOverride with `visible` target and boolean value | Parser update (if needed) |
| 2 | Compressor test: instance with `.visible=false` override on a descendant produces markup with PathOverride | Compressor emits PathOverride |
| 3 | Renderer test: markup with PathOverride `.visible=false` emits Figma JS with `id.endsWith(";<nid>").visible = false` (NOT `findOne(name)`) | Renderer lowers PathOverride |
| 4 | Round-trip: compress → markup → parse → render on 3 top-nav screens, byte-diff vs pre-PR1 (should match PR-1 output) | Wire through |
| 5 | `{empty}` parse test: `right = {empty}` parses as PathOverride `.visible=false` on the slot's default | Grammar sugar |
| 6 | Multi-backend stub test: PathOverride `.visible=false` lowers to HTML `{false && <X/>}`, SwiftUI `EmptyView()`, Compose null-slot | Per-backend adapter hook (stubs OK; real adapters land in later milestones) |
| 7 | Full Dank sweep: 190/204 → maintained or improved | Fix regressions |

### 6.4 Acceptance gate

- Round-trip sweep: ≥ 190/204 PARITY (bar does not lower).
- Markup round-trip fixtures: identity preserved through compress → parse cycles.
- Multi-backend stub tests: green on all 4 backend adapters.
- LLM emission test: give the model the `nav/top-nav` master signature + "hide the wordmark"; grammar-valid PathOverride expected.

## 7. Backend lowering table

| Backend | Source form | Lowered form |
|---|---|---|
| Figma (Plugin API) | `left.logo/dank.visible = false` | `n9.findOne(n => n.id.endsWith(";5749:84278")).visible = false` |
| HTML / React | `left.logo/dank.visible = false` | `<LogoDank style={{display: slot === "left" ? "none" : undefined}} />` or `{slot !== "left" && <LogoDank/>}` |
| SwiftUI | `left.logo/dank.visible = false` | `if slot != .left { LogoDank() } else { EmptyView() }` |
| Jetpack Compose | `left.logo/dank.visible = false` | `if (slot != Slot.Left) { LogoDank() }` — null is a valid slot |
| `{empty}` sugar | `right = {empty}` | Any of the above, scoped to the slot's default child |

The lowering table is the contract the grammar form satisfies. If a new backend adapter can't express "this slot/descendant doesn't render", it's the backend that needs extension, not the grammar.

## 8. Out of scope

- Making the renderer "smart" about inferring visibility from style (opacity=0, size=0, etc). Those are separate IR properties; don't fold them in here.
- Classifier-driven visibility. The classifier labels *semantic* roles (see type/role split). Visibility is a *structural* override, sourced from `instance_overrides`, not `screen_component_instances`.
- Multi-state component visibility (show-only-on-hover, show-only-on-active). Those are state variants; a future milestone. For now, the instance snapshot's visibility diff is the only signal.

## 9. Dependencies / ordering

- No dependency on type/role split. They're orthogonal. Can land in either order; current branch `v0.3-integration` already has type/role split (Stage 4a complete).
- Depends on `instance_overrides` table being populated. Confirmed via Plugin API supplement pass; 20,803 BOOLEAN rows on Dank-EXP-02.
- Opens the door to classifier-v3 rendering self-hidden UI (see `feedback_plugin_render_toggle.md`) via the same grammar surface — but that's a separate build.

## 10. Success metric

A human inspecting the Phase-1 sweep output, screen by screen, sees no "phantom missing content" — every element present in the source appears in the render. Structural verifier `is_parity=True` is no longer undermined by same-name-sibling visibility drift.
