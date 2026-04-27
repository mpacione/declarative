# Orphan Detector — Post-P7 Noise Triage

**Date:** 2026-04-26
**Branch:** `v0.3-integration` after P7 (commits `e226df3` ALLOWLIST cleared)
**Detector tip:** `tools/orphan_detector.py` (P2)
**Detector verdict on the post-P7 codebase:** 286 flagged orphans / 704 dd public symbols, ALLOWLIST empty.

## Triage method

Sampled 12 flagged symbols across distinct dd/ modules
(agent, apply_render, catalog, classify_consensus, classify_review,
validate, variants, visual_inspect, ast_to_element). For each,
recorded grep-counts across `dd/`, `tests/`, `scripts/`, `docs/`
to determine the real reachability the detector missed.

Codex 2026-04-26 (gpt-5.5 high reasoning) advised: **read-only triage,
do NOT change detector contract or add a 286-symbol allowlist
autonomously. The 286 count is not by itself a strong code-smell
because the detector's known contract is narrow: public symbols
with test-only/script-only visibility will look orphaned.**

## Findings — all 12 samples are FALSE POSITIVES

| Symbol | Why detector flagged | Real reachability |
|---|---|---|
| `agent.loop.build_loop_tools` | dd-self only | Used in test_agent_loop |
| `agent.loop.cheap_structural_score` | dd-self only | test + docs/rationale |
| `apply_render.walk_rendered_via_bridge` | tests + scripts | **4 scripts** + 3 docs |
| `apply_render.rebuild_maps_after_edits` | (false positive) | **3 dd/ files: sessions, cli, apply_render** — detector missed dd→dd |
| `catalog.lookup_by_name` | dd-self + test | Test-fixture support API |
| `classify_consensus.build_calibrated_weights` | (false positive) | dd/classify.py calls it; detector missed dd→dd |
| `classify_review.apply_reviews_to_sci` | dd-self + tests + script | scripts/archive script-reachable |
| `validate.check_binding_coverage` | dd-self + test | Auto-registered by validator framework |
| `validate.detect_binding_mismatches` | dd-self + test + docs | Same — validator-framework discovery |
| `variants.derive_variants_from_ckr` | dd-self + test + script | **scripts/derive_variants.py** — script-reachable |
| `visual_inspect.inspect_screenshot` | dd-self + test + script | scripts/archive script-reachable |
| `ast_to_element.ast_head_to_element` | dd-self + 2 tests | Likely test-only public API |

## Pattern analysis

Four categories of false positive in the 286:

1. **Script-reachable** (~30-50% est) — detector doesn't scan
   `scripts/`. `walk_rendered_via_bridge`, `derive_variants_from_ckr`,
   `apply_reviews_to_sci`, `inspect_screenshot`,
   `build_calibrated_weights` etc. all have legitimate script callers.

2. **dd/ → dd/ false negatives** (~10-20% est) — the detector's AST
   walk in `_collect_imports_from_file` sometimes misses
   intra-package references, especially when the import is via a
   submodule path. `rebuild_maps_after_edits` is called from
   `dd.sessions`, `dd.cli`, AND `dd.apply_render` — definitely not
   orphaned.

3. **Validator-framework discovery** (~10% est) — `dd.validate.check_*`
   functions are registered by reflection / decorator-based discovery,
   so a static AST walk for callers misses the framework's call site.

4. **Genuine test-only public APIs** (~30% est) — intentional surface
   for testing internal behavior (`SessionRunResult`, `RenderedApplied`,
   etc.). These are stable internal-public APIs — tests use them, no
   dd/ caller should because they're already wrapped by higher-level
   APIs.

## What to do

**Recommendation: do nothing autonomously. Future-cycle work.**

If the 286 noise is bothering anyone, the right next steps (in order
of value):

1. **Add `scripts/` to the detector's "non-test caller" set**. Symbols
   used by scripts/ (including scripts/archive/) are by definition
   not test-only. This single change probably drops the count to
   ~150 and matches the detector's intended contract more honestly.

2. **Detect & exclude validator-framework auto-registration** — scan
   for `register_validator(` / `@validator` etc. decorators and treat
   the decorated function as caller-bound.

3. **Improve dd/ → dd/ caller detection** — `_collect_imports_from_file`
   may need to follow attribute access (`m.X.Y`) more aggressively.

4. **Then** decide whether the residuals (~30-50 genuine test-only
   APIs) deserve allowlist entries or removal/refactor.

The ADR-007 stack (the 13 entries P7 deleted) was the canonical
"test-only stack" the detector was designed to catch — and it caught
it. The 286 noise is the price of the detector's intentionally
narrow definition. The detector did its primary job.

## Final note

**No code changes made autonomously based on this triage.** Recording
the findings for future cycle work. If the user wants to tackle
detector noise as a follow-up, the priority order above is the
suggested approach.
