# Remix Mechanics: Architectural Survey for Mode 3 Composition

**Status:** Research memo, pre-ADR. Informs the Mode 3 composition story for synthesising subtrees when the corpus lacks a ready-made component. Target integration: ADR-006 (boundary) and ADR-007 (verification channel).

---

## 1. Executive Summary

Every mainstream design system factors component remix into three axes: **structural slots**, **variant records**, **token cascades**. What differs is *where authority lives* and *how failures surface*. cva, Stitches, Chakra, and Panda model variants as typed records with compound overrides; MUI, Radix, and Figma model structure as prop-driven slots; Material 3, Chakra, and Ant Design layer tokens in 2–3 tiers; Ant alone derives tokens *algorithmically*. None of the surveyed systems formalises *provider precedence* across coexisting libraries — that is an open seam we own.

Recommendation: **Hybrid Cascade + Registry (Option D)**. A `ComponentProvider` registry resolves `(type, variant) → PresentationTemplate` in priority order (project > ingested > universal); a DTCG token cascade resolves `{token-ref} → value` within the template. Both paths emit `StructuredError` on miss, consumed by the ADR-007 channel. Zero IR schema change in v0.1; additive `provider` provenance field in v0.2.

---

## 2. Per-System Analysis

**cva** — `base` + `variants` (axis→value→classes) + `compoundVariants` + `defaultVariants`. Resolution: base → selected variant → compound *layers on top* ([cva.style/docs/getting-started/variants](https://cva.style/docs/getting-started/variants)). Compound matchers accept arrays; boolean variants use `{ false: null, true: [...] }`. No runtime fallback for unknown variants — TypeScript enforces. Pure string concatenation, no token step.

**Material Design 3 tokens** — The M3 Compose guide ([developer.android.com/develop/ui/compose/designsystems/material3](https://developer.android.com/develop/ui/compose/designsystems/material3)) confirms components consume named roles (`MaterialTheme.colorScheme.primary`) rather than raw hex. The widely documented M3 convention layers reference palette tokens (e.g., tonal `primary40`) under system tokens (`md.sys.color.primary`) under component tokens (`md.comp.filled-button.container-color`), with component tokens as aliases into system tokens. Missing component values fall through to system by *convention*, not spec enforcement.

**Radix Slot / asChild** — `Slot.Root` merges parent props onto its child: `const Comp = asChild ? Slot.Root : "button"` ([radix-ui.com/primitives/docs/utilities/slot](https://www.radix-ui.com/primitives/docs/utilities/slot)). Child event handler runs first, parent checks `defaultPrevented`. Composition guide ([/primitives/docs/guides/composition](https://www.radix-ui.com/primitives/docs/guides/composition)) mandates: spread all props, forward refs, caller owns accessibility.

**Stitches** — `variants`, `compoundVariants`, `defaultVariants` ([stitches.dev/docs/variants](https://stitches.dev/docs/variants)). Absent-variant behaviour undocumented; the type system is the enforcement layer — a recurring pattern.

**Panda CSS recipes & slot recipes** — Same shape as cva but tokens as first-class values (`bg: 'red.200'` → `var(--colors-red-200)`) ([panda-css.com/docs/concepts/recipes](https://panda-css.com/docs/concepts/recipes)). Slot recipes extend to multi-part components — one variant declaration emits styles across named slots ([/docs/concepts/slot-recipes](https://panda-css.com/docs/concepts/slot-recipes)). Config recipes dead-strip unused variants at build time — exactly the constrained-grammar story we want for synthetic emission.

**MUI `sx` + slots** — `slots={{ root: MyComponent }}` substitutes interior DOM elements; `slotProps` passes props in ([v6.mui.com/base-ui/guides/overriding-component-structure](https://v6.mui.com/base-ui/guides/overriding-component-structure/)). Precedence: `slotProps.root` wins on same keys, *except* classes and style which *merge*. Cleanest *structure vs presentation* split surveyed: `slots` = what goes there, `sx`/theme = how it looks.

**Chakra Style Config** — `baseStyle` + `variants` + `sizes` + `defaultProps` via `useStyleConfig()` ([v2.chakra-ui.com/docs/styled-system/component-style](https://v2.chakra-ui.com/docs/styled-system/component-style)). Multi-part via `createMultiStyleConfigHelpers({ parts: [...] })` — structurally Panda slot recipes.

**Ant Design theme algorithm** — Three-layer derivation: **Seed** (`colorPrimary`) → **Map** (`colorPrimaryHover`, algorithmic) → **Alias** (`colorLink`) ([ant.design/docs/react/customize-theme](https://ant.design/docs/react/customize-theme), [#algorithm](https://ant.design/docs/react/customize-theme#algorithm)). Algorithm signature: `(SeedToken) => MapToken`; presets (default/dark/compact) compose. Uniquely *procedural* — Map tokens are computed, not declared. Relevant only if we need generated tonal ramps.

**React Aria** — Behaviour/presentation separated via **contexts**: components "automatically provide behavior to their children by passing event handlers and other attributes via context" ([react-aria.adobe.com/customization](https://react-aria.adobe.com/customization)). Three mechanisms: render props, named slots, `useContextProps`. Strict behaviour contract, free presentation — directly parallels our IR/renderer split.

**Figma components / variants** — Variants live in a **component set** with typed properties: `variant` (enum), `boolean`, `text`, `instance-swap` (with curated `preferredValues`) ([help.figma.com/.../360056440594](https://help.figma.com/hc/en-us/articles/360056440594-Create-and-use-variants), [.../5579474826519](https://help.figma.com/hc/en-us/articles/5579474826519-Explore-component-properties)). "You don't need a component for every possible combination" — behaviour on missing combos undocumented. `instance-swap` is Figma's slot primitive, bounded by a compatibility allowlist — the exact mechanism enabling Mode-3 "button-in-dialog-footer."

**DTCG spec** — Atomic types (color, dimension, duration, font-family, font-weight, number, cubic-bezier) plus composite (shadow, border, transition, gradient, typography, stroke-style). Aliases via `{group.token}` resolving to `$value`, or JSON Pointer `$ref: "#/path"` ([designtokens.org/TR/drafts/format](https://www.designtokens.org/TR/drafts/format/)). **No formal component-token extension, no formal themes/modes** — "tools _MUST NOT_ attempt to guess the type." Component-scoping is a naming convention. Validates our plan to layer our own conventions on top.

---

## 3. Cross-Cutting Answers

**A. Variant stacking.** Dominant model: **multi-axis enum record + compound overrides**. cva, Stitches, Chakra, Panda all converge. Base → axis selections → compound overrides layer last. Adopt this — it's the lingua franca and what an LLM already emits naturally.

**B. Token layering.** Two-to-three tiers with component-scoped tokens as aliases into system tokens (M3, Chakra). DTCG does **not** formalise layering — we specify it: **universal catalog → ingested system → project → component-scoped**, later layers override, all expressed as DTCG aliases.

**C. Provider precedence.** *No surveyed system solves this.* MUI, cva, Radix all assume a single-library world. Our precedence: **project CKR > ingested system CKR > universal catalog > synthesised-from-tokens**. Natural extension of the ADR-006 `IngestAdapter` pattern to the resolve side.

**D. Composition expression.** Three wild-found models: slot props (MUI, Radix, Panda, Figma instance-swap), named-child context (React Aria), nested `asChild` (Radix). Slot props win on explicitness, debug-ability, and match our IR's existing `children`. Model Mode 3 composition as *typed slot contracts on PresentationTemplate*.

**E. Render→critic→refine loop.** None of the surveyed systems do this; all static. Genuinely new capability, right v0.2 extension: the ADR-007 RenderVerifier already emits per-node `KIND_*` deltas, so a refine pass that re-resolves a single slot against a tightened constraint is the natural fit. Not v0.1.

**F. Failure modes.** Most surveyed systems fail at compile time (TypeScript) or silently at runtime. Figma's missing-combo is literally undocumented. **Our differentiator:** every no-match, partial-match, ambiguous-match produces `StructuredError` per-node: `KIND_VARIANT_NOT_FOUND`, `KIND_NO_PROVIDER_MATCH`, `KIND_TOKEN_UNRESOLVED`, `KIND_SLOT_TYPE_MISMATCH`.

---

## 4. Four Architectural Options

### Option A — Provider Registry (ordered walk)
**Shape:** `ComponentProvider` protocol; `resolve(type, variant, context) -> PresentationTemplate | None`. Registry is a priority-ordered list; first match wins.
**IR surface:** no change.
**Registration:** each provider declares `priority` and `backend`. Project CKR = 100, ingested shadcn = 50, universal catalog = 10, token-only synthesis = 0.
**Resolution:** linear walk; `None` → continue.
**Token binding:** internal to provider; templates carry their own refs.
**Failure:** exhausted walk → `KIND_NO_PROVIDER_MATCH`; known type, unknown variant → `KIND_VARIANT_NOT_FOUND` and continue.
**ADR fit:** symmetric mirror of ADR-006 on the resolve side; errors flow through the existing channel.

### Option B — Theme Cascade (nested scopes)
**Shape:** `Theme` tree; resolution walks from node to root collecting overrides.
**IR surface:** add optional `theme_scope: str` to nodes.
**Registration:** no concept — a library is just a theme layer.
**Resolution:** walk scope chain (node → parent → screen → project → ingested → universal); miss triggers next layer.
**Failure:** exhausted cascade → `KIND_NO_PROVIDER_MATCH`. No notion of "variant missing *in this layer*" — just walks.
**ADR fit:** single error class, less granular than A. Conflates library identity with token scope.

### Option C — Variant-as-Record (cva-style first-class)
**Shape:** each type owns a canonical `{ base, variants, compoundVariants, defaultVariants, slots }`. Mode 3 always resolves against it; providers merge *into* it.
**IR surface:** add `compound_variants: list[{match, overrides}]` beside existing `variant`.
**Registration:** providers contribute records; records deep-merge (project > ingested > universal).
**Resolution:** structural; resolve axes, apply compounds, resolve slots.
**Failure:** missing variant value → `KIND_VARIANT_NOT_FOUND`; no record → `KIND_NO_PROVIDER_MATCH`.
**ADR fit:** deep-merge across libraries is fiddly — whose `compoundVariants` win?

### Option D — Hybrid Cascade + Registry (**recommended**)
**Shape:** **registry** for `(type, variant) → PresentationTemplate` (Option A); **cascade** for `{token}` refs *within* the template (Option B for tokens only); compound variants expressed inside the template (Option C locally, not as cross-library merge).
**IR surface:** zero change v0.1. v0.2 adds optional `provider: str` provenance on resolved nodes.
**Registration:** `ComponentProvider` protocol with `priority`, `backend`, `supports(type, variant) -> bool`, `resolve(...) -> PresentationTemplate`. Registered in new `dd/composition/registry.py`. Project provider auto-built from CKR; ingested providers built from `IngestAdapter` output; universal catalog is built-in.
**Resolution:**
1. Registry walks providers by priority; first `supports()`-true match wins.
2. Template returned with unresolved DTCG `{token.path}` refs.
3. Token cascade resolves each ref: project tokens → ingested system → universal.
4. Template slots point at child nodes by `slot_name`; children recurse.
**Failure:** `KIND_NO_PROVIDER_MATCH(id=type)`; `KIND_VARIANT_NOT_FOUND(id=f"{type}/{variant}")` with walk continuation; `KIND_TOKEN_UNRESOLVED(id=ref)` with literal fallback; `KIND_SLOT_TYPE_MISMATCH` when footer expects Button, got Text.
**ADR fit:** symmetric with ADR-006 `IngestAdapter`/`IngestResult`; errors flow the ADR-007 `__errors` channel with the same `kind` vocabulary.

**Walkthrough (user's 80–90% Dank screen + novel destructive-confirm dialog):** Screen root = Dank `Screen` → Mode 1 via project CKR (unchanged). Novel `Dialog{variant:"destructive-confirm", slots:{footer:[Button{variant:"destructive"}], body:[Text]}}` — project `supports()` returns `False`, emits `KIND_VARIANT_NOT_FOUND(fallthrough=True)`, walks. Ingested shadcn provider matches, returning a template with footer/body slot contracts and token refs `{color.action.destructive}`, `{spacing.dialog.padding}`. Cascade resolves the former at ingested layer, the latter at universal. Button child recurses — ingested provides destructive; compound `(destructive, size:sm)` adjusts padding inside the template. ADR-007 channel: one informational entry, zero unrecoverable errors; round-trip verifier runs normally.

---

## 5. Recommendation + Phasing

**Adopt Option D.** Reuses the ADR-006 contract shape verbatim, keeps the v0.1 IR schema unchanged, and factors structural authority (registry) from leaf-value resolution (cascade) along the seam surveyed systems almost draw but never name.

**v0.1:** `dd/composition/registry.py` (`ComponentProvider` + priority registry); `dd/composition/cascade.py` (DTCG token cascade); three providers (`ProjectCKRProvider`, `IngestedSystemProvider` fed by existing `IngestAdapter`, `UniversalCatalogProvider`); new `KIND_*` codes on `dd/boundary.py`; `compose.py` integration at the Mode 3 fall-through point. Mode 1 / Mode 2 unchanged.

**v0.2:** additive `provider: str` IR field for per-node provenance; RenderVerifier attribution (which provider produced a delta); compound-variant expansion inside templates.

**v0.3 (speculative):** render→critic→refine loop — RenderVerifier deltas feed constrained slot re-resolves.

**No IR schema change required for v0.1.** Composition lives entirely in a new `dd/composition/` module.

---

## 6. Failing-Test Sketch

Black-box behaviour tests on the public `resolve()` surface:

1. `test_project_provider_wins_over_ingested_for_same_type` — priority ordering honoured.
2. `test_fallthrough_when_project_lacks_variant` — project returns `None`, ingested resolves.
3. `test_unknown_variant_emits_kind_variant_not_found` — structured error on mismatch; walk continues.
4. `test_no_provider_match_emits_kind_no_provider_match` — exhausted registry → terminal error.
5. `test_token_cascade_project_overrides_ingested_overrides_universal` — three-layer token order.
6. `test_unresolved_token_ref_emits_kind_token_unresolved_with_literal_fallback` — graceful degrade, still renders.
7. `test_slot_type_mismatch_emits_kind_slot_type_mismatch` — footer expects Button, got Text.
8. `test_compound_variant_overrides_simple_variant` — cva-style layering inside one template.
9. `test_provider_errors_are_ingestresult_shaped` — boundary invariant: `len(errors) == summary.failed`.
10. `test_resolution_is_deterministic_under_stable_priority` — tie-break by `backend` name.

---

## 7. Open Questions for the ADR

1. **Tie-breaking at equal priority.** Alphabetical on `backend` for reproducibility, or explicit `registered_at`? Lean alphabetical.
2. **Deep-merge vs replace on template overrides.** Recommendation: **shallow merge on axis, replace on compound** — avoids Option C's cross-library semantics.
3. **Where does "synthesise from tokens" live?** As a lowest-priority `TokenOnlyProvider` (preferred, symmetric), or a separate Mode 4? Former — keeps the abstraction flat.
4. **Should Figma `instance-swap` become a `SLOT` IR node-kind?** Would make slot-contract validation trivial but costs a schema change. Defer to v0.2.
5. **Provenance scope in `__errors`.** Walk history (richer training signal) vs terminal-only (quieter CI)? Lean walk history behind a `verbose=True` flag.
6. **DTCG themes/modes.** Ship `$mode: "light" | "dark"` now or wait? Wait — not on the destructive-dialog critical path.
