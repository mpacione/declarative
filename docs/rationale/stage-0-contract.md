# Stage 0 — Fix the generation contract

Stage 0 is the load-bearing prerequisite. Nothing else in the plan produces fluid multi-depth composition if Stage 0 is skipped, because the substrate (grammar, renderer, IR, edit apply) works — the LLM-facing contract was forcing the flatten.

## 1. What Stage 0 was for

Four defects, diagnosed jointly by Opus + Codex (plan §1.2). The quotes are verbatim:

- **Defect A — Missing neutral structural wrapper.** "`dd/catalog.py` defines 80 canonical types. Every single one is semantic — `button`, `card`, `heading`, `toggle`, `header`, `drawer`. There is no `frame`, `stack`, `group`, `section`, or `container` in the vocabulary exposed to the LLM."
- **Defect B — The prompt explicitly teaches wrong coercions.** The pre-Stage-0 planner prompt carried: "a generic container / section / wrapper → use `card`; a footer → use `card` at the bottom; a carousel → use `list` of `card` children; a hero → use `card`." Consequence: "every designer-intuitive intermediate entity becomes a 'card.' Nesting collapses to `card → card → card`."
- **Defect C — Identity loss in `compose.py::_allocate_id`.** "Even if the LLM emits a beautifully-named plan with `eid=product-showcase-section`, `compose.py` discards that and generates `frame-1`, `card-3`, `button-7`."
- **Defect D — Output contract is 'emit a closed component array,' not 'emit subtree moves.'** One-shot top-down. No workspace. No named entities to edit against later.

## 2. What we shipped

Six commits on `v0.3-integration`. Five Stage-0 implementation commits + a sixth visibility-toggle reversal:

- **`6ccbaf5` — Stage 0.4: preserve planner-supplied eids.** `_allocate_id(comp_type, preferred_eid=None)`. If the planner emits an eid that's well-formed and not already taken, it survives into `elements` as-is; otherwise fall back to the counter. `repeat: N` expands deterministically to `feature-card__1..__N`.
- **`68e28a1` — Stage 0.1+0.2: frame primitive + delete coercions.** Adds `Neutral wrapper: frame` to the planner vocabulary. Deletes the four coercion rules. Requires a catalog row for `frame`, which requires widening the `component_type_catalog.category` CHECK — that's migration 022.
- **`c189291` — Stage 0.3+0.7: flat named-node plan contract + new system prompt.** Plan output is `{"nodes": [{eid, type, parent_eid, order, slot?, repeat?}, ...]}` — explicit parent pointers, explicit order, `repeat: N` instead of `count_hint`. New system prompt spells out the closed/open contract.
- **`0af8361` — Stage 0.5+0.6: slot-name validation + structural drift check.** Slot names validate against the parent's declared slots (catalog slot_definitions or `component_slots`). Log-only first per the user's call — rejection promotes to hard error on trigger. Drift check compares `(eid, type, parent_eid, slot, repeat)` tuples; mismatches emit `KIND_PLAN_DRIFT`.
- **`8e36666` — Stage 0 cleanup: wire `ProjectCKRProvider` into both registries.** Plan §4.1 flagged it as existing-but-unplugged; this is the fix.
- **`538ebc9` — visibility-toggle reversal (post-Stage-0 visual inspection).** Scoped `try/finally` toggle around every `instance.findOne(...)` in the override emitter, to defeat the `skipInvisibleInstanceChildren=true` blindness against master-default-hidden slots. Reverses plan §4.1 Tension A.

## 3. The mechanics

**`frame` as a catalog citizen.** `frame` was already a grammar TypeKeyword (spec §2.7), parser/compressor/renderer all handled it — it was just absent from the prompt-facing vocabulary. Adding it to the planner required adding a `component_type_catalog` row; that required widening the category CHECK. Migration 022 (`migrations/022_catalog_structural_category.sql:24`) adds `structural` as a seventh category alongside the existing six. Without the migration the seed step fails on INSERT.

**`_allocate_id(preferred_eid=...)`.** `dd/compose.py:121` — the counter path stays as a fallback; the preferred path is "use the planner's name if it's a valid eid and not already in `elements`." Every `_build_element(comp)` call that has an `eid` in `comp` passes it through (`dd/compose.py:231`). For `repeat: N`, expansion is deterministic: the planner's eid is the stem, `__1 / __2 / __3` suffixes are non-colliding by construction.

**Flat-row plan contract.** The `{"nodes": [...]}` shape is validated top-to-bottom: every non-root node's `parent_eid` must already exist in the rows above; `order` sorts deterministically inside a parent; `repeat: N` is expanded post-validation so the flat list the composer sees is fully-materialised. Tests: `tests/test_composition_plan.py`.

**Slot-name validation (log-only first).** `dd/composition/plan.py:518-544` loads the parent's declared slots (catalog slot_definitions for canonical types; `component_slots` table for master-derived slots). Unknown slots emit `KIND_SLOT_UNKNOWN` — log-only until the promotion trigger (one week of real-prompt runs OR 20 consecutive runs with zero rejections).

**Structural drift check.** `dd/composition/plan.py:591-654` tuple-compares planner intent vs compose output. Pre-Stage-0 the drift check was a bare type-count diff; the new shape catches slot/order/parent/repeat drift too.

## 4. Design forks recorded

**Fork 1 — the initial Option-B TDD order.** Stage 0 was decomposed into five commits (0.1–0.7) but the implementation order put the eid-preservation work (0.4) first so the later commits had the addressable substrate to test against. Codex preferred this over a chronological 0.1 → 0.7 order for a cleaner TDD progression.

**Fork 2 — Tension A reversal mid-stage.** Plan §4.1 prescribed "delete `figma.skipInvisibleInstanceChildren = true` on `dd/render_figma_ast.py:148`" because it was flagged as the root of ~1,689 silent override failures on Dank. Both Codex and Claude Opus initially converged on "keep the perf line" in the pre-flight decision round (this was the "Tension A keep" call). Post-Stage-0 visual inspection of Dank screen 333 (`iPad Pro 11" - 43`) showed the sweep reporting 204/204 PARITY while the rendered nav was missing the Workshop pill, share icon, dropdown chevron, and shape-picker buttons. The perf flag was making `findOne` blind to master-default-hidden descendants, and the verifier walker (under the same flag) was blind in the same way — both sides "missed" the same nodes, counts matched, `is_parity=True`. The Tension-A "keep" decision was wrong. Commit `538ebc9` reversed it: a scoped `try/finally` toggles the flag off around each `findOne`, then restores it. Self-target overrides (which use the instance variable directly) skip the toggle. See `.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_skipinvisible_findone_blindness.md` for the full write-up.

## 5. What the plan got wrong

- **`_fetch_descendant_visibility_overrides` was NOT dead code.** Plan §4.1 said "delete the duplicate flat-depth resolver and let `override_tree` handle depth-N visibility." The slot-visibility grammar (commits `97f8220` → `1dcb446`, `b7484ce` cluster) shipped between plan-writing and Stage 0 and had already unified the hidden-children path onto the id-addressed resolver. The "duplicate" the plan described no longer existed in the form described. Deletion was skipped; the resolver was already doing the right thing.
- **Line numbers drifted.** Plan §4.1 said `_fill_system` was at `dd/composition/plan.py:239`. It's actually at `dd/composition/plan.py:670`. The file grew ~430 lines between plan-drafting (pre slot-visibility PR 2) and Stage 0 execution. Every plan line number is suspect; find symbols by name.
- **Tension A.** Already covered in §4 above. The plan was right about the symptom, wrong about the fix.

## 6. Empirical validation

[`docs/post-mortem-stage0.md`](../post-mortem-stage0.md) is the auto-gate between Stage 0 and Stage 1, per `feedback_auto_inspect_before_human_rate.md` (structural green doesn't prove the LLM composes better, only that nothing broke).

Five real Haiku-4.5 prompts, each targeting at least one defect:

| # | Prompt | A (frame used) | B (no card-as-wrapper) | C (named eids) | D (flat shape) |
|---|---|---|---|---|---|
| 1 | settings page with sections | yes (6 frames, 0 cards) | yes | 11/11 | yes |
| 2 | product showcase + 3 feature cards | yes | yes | 8/8 | yes |
| 3 | checkout form | yes | yes | 12/12 | yes |
| 4 | footer with 3 columns | yes | yes | 6/6 | yes |
| 5 | sidebar nav w/ workspace switcher + profile | yes | yes | 11/11 | yes |

Aggregate: 5/5 on every defect, zero slot-name hallucinations. The footer prompt is the single cleanest falsification of the pre-Stage-0 coercion rule — "a footer → use `card`" was verbatim in the prompt text before `68e28a1`; the same Haiku model organically emits `footer-root` as a `frame` after the rule is gone.

## 7. The visibility-toggle near-miss

Tension A is documented in full in `feedback_skipinvisible_findone_blindness.md`. The short version:

- The perf line (`figma.skipInvisibleInstanceChildren = true;`) was added `e19bdba` (2026-04-22) as the first preamble statement of every generated script. Real speedup on instance-heavy renders.
- The same flag also gates `instance.findOne(...)`. Under `true`, `findOne` skips master-default-hidden descendants and everything beneath them.
- `dd/renderers/figma.py::_emit_override_tree` emits `instance.findOne(n => n.id.endsWith(";<fid>"))` for every child-target override. For master-default-hidden slots (the `nav/top-nav` Workshop pill / share icon / dropdown chevron on Dank iPad screens) this returns `null`. Overrides silently no-op.
- `render_test/walk_ref.js` walks `n.children` under the same flag, so the verifier also misses those nodes. Both sides blind → `is_parity=True` false-positive.
- Plan §4.1 said "delete the perf line." That fixes the correctness issue but regresses the perf. The right move was scoping.
- `538ebc9` scopes the flag with `try/finally` around each `findOne`. Post-fix: 204/204 PARITY held; sweep runtime 685s (down from 950s — previously-hidden subtrees now contribute to legitimate skip pruning rather than masking the bug).

Lesson (logged as a feedback memory): when one memory says "load-bearing perf" and a plan note says "delete for correctness," the answer is usually "scope it," not "pick a side."

## 8. Where the code lives

- `migrations/022_catalog_structural_category.sql` — category CHECK widening (adds `structural`).
- `dd/compose.py:121-139` — `_allocate_id(comp_type, preferred_eid=None)`.
- `dd/compose.py:231` — `_build_element` call site that passes the planner eid through.
- `dd/composition/plan.py:670` — `_fill_system` (soft-deprecated in Stage 1.6; plan said 239).
- `dd/composition/plan.py:510-544` — `KIND_SLOT_UNKNOWN` emission (log-only).
- `dd/composition/plan.py:585-654` — `KIND_PLAN_DRIFT` structural tuple comparison.
- `dd/prompt_parser.py` — `Neutral wrapper: frame` added to the vocabulary block.
- `dd/renderers/figma.py` — `_emit_override_tree` `try/finally` toggle around `findOne`.
- `dd/render_figma_ast.py:148` — the global `skipInvisibleInstanceChildren = true` preamble (kept; scoped wrappers defeat it where needed).
- `tests/test_override_toggle_skipinvisible.py` — five unit tests pinning the toggle contract.

## 9. What's deferred

- **Slot validation promotion** — `KIND_SLOT_UNKNOWN` stays log-only until the promotion trigger fires. If a real prompt rejection surfaces in the meantime, triage before enforcing.
- **`DD_USE_LEGACY_PLAN=1` safety valve** — plan §8 Decision 2 gave a one-release window. Stage 1 landed in the same cycle; the flag is expected to be removed in the first follow-up after Stage 1 stabilises.
- **Two cosmetic residuals on screen 333** — swap-then-text addressing ("Workshop" title shows literal "Workshop" not "Meme-00001"; "Tap anywhere…" pill renders swap-target default text). Not a blindness issue; separate swap-then-override coordinate-frame bug class. Deferred to a focused pass when demo quality matters.
