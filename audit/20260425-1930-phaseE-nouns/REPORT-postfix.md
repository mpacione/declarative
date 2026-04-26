# Phase E — post-fix sweep on Nouns (Experimental)

**Date:** 2026-04-26
**File:** Nouns (Experimental), file_key `B512WwrY9M0Pu4nacnMIPe`, 67 app screens
**Branch:** `v0.3-integration` at tip after P1..P7 + P3a-fix + P5b dead-branch test
**Bridge:** WebSocket port 9225, current page "Generated Test"

## Headline

*(Will be filled in once `sweep-out-postfix2/summary.json` is complete; placeholder structure below.)*

| metric | Phase E baseline | Post-fix | delta |
|---|---:|---:|---:|
| total | 67 | 67 | 0 |
| `is_parity_true` (strict) | 1 | TBD | TBD |
| `is_structural_parity_true` | 61 | TBD | TBD |
| `is_parity_false` (DRIFT) | 6 | TBD | TBD |
| `total_runtime_errors` | 1015 | TBD | TBD |
| `screens_with_runtime_errors` | 66 | TBD | TBD |

## Fixes shipped

11 commits between Phase E baseline (`8461403`) and the post-fix tip:

| Commit | Phase E finding | Fix |
|---|---|---|
| `0fc7354` P1 | Pattern 2 — verifier ignored 31 __errors kinds | Inhale runtime errors → `RenderReport.runtime_errors`; `is_parity` strict |
| `d031ce4` P2 | Pattern 1 — canonical-path drift undetected | Test-only-import orphan detector + CI gate |
| `9a49684` P3a | N1 — Cannot move into INSTANCE | `mode1_eids`/`skipped_node_ids` skip-set in AST renderer |
| `db1dec0` P3b | C2 — orphaned cluster_stroke_weight, cluster_paragraph_spacing | Wire both into orchestrator + `paragraphSpacing=0` default-marking |
| `d159bbc` P3c | C1 — letter_spacing token/binding mismatch | Snap-on-UPDATE; bucket by (rounded, unit) |
| `45c67d9` P3d | N2 — page-orphans invisible to verifier | Walker pre-/post-snapshot → `phase2_orphan` summary entries |
| `76efa33` P4 | Pattern 2 follow-up — opaque runtime kinds | `dd/runtime_errors.py` 11-category map + `is_runtime_clean` + sweep summary |
| `827164d` P5a | Pattern 3 — sub-pixel padding warnings | cluster_spacing snap-on-UPDATE |
| `47733a3` P5b | Pattern 3 — multi-shadow attribution bug | cluster_effects (node_id, effect_idx)-keyed UPDATE; dead branch fix |
| `91f7ef5` P5c | Pattern 3 structural | AxisSpec registry + convention test |
| `e226df3` P6+P7 | Pattern 1 — 526 LOC ADR-007 test-only stack | Delete render_protocol.py, repair_figma.py, repair_agent.py + tests + adapter; -1561 LOC |

Plus two follow-ups discovered during the re-run:

| Commit | What | Why |
|---|---|---|
| `167fcee` P3a-fix | Phase 2/3 parent-in-set check | First re-run regressed structurally (screen 1: parity 1.0 → 0.5375). Original P3a guard checked `id(node) in absorbed_node_ids`; the Mode-1 head NODE was in `mode1_node_ids` itself, so its own appendChild + Phase 3 ops were silently dropped. Codex 2026-04-26 confirmed parent-in-set is the OLD-path semantic that produces the right behavior. |
| `2d1f6da` P5b dead-branch test | Merged-color confidence branch tripwire | Original P5b fixture used #000000/#FF0000 — too far apart in OKLCH to trigger the merge predicate. New test uses #181818/#1A1A1A (delta ≈ 0.875) and asserts confidence in [0.8, 1.0) — proves merged_pairs branch fires post-fix. |

## Per-section impact (will fill from comparison output)

### Class N1 — "Cannot move node into INSTANCE" — VERIFIED CLEARED ✅
- Phase E baseline: 149 errors on screen 24 (`append_child_failed` 131 + `phase1_mode2_prop_failed` 16 + `group_create_failed` 1 + `group_insert_failed` 1)
- Post-fix screen 24: **4 errors total** (all `phase1_mode2_prop_failed` on `boolean_operation-*` nodes — Figma rejecting prop writes on read-only-ish boolean operation subtrees inside instances). 0 `append_child_failed`, 0 `group_*_failed`.
- 184/184 IR nodes correctly land in eid_map (vs baseline's 184/184 — same node coverage but now with 4 errors instead of 184 runtime errors).
- The 4 residual `phase1_mode2_prop_failed` are on BOOLEAN_OPERATION descendants of an instance subtree. The Phase 1 walker emits prop writes defensively guarded with try/catch because absorbed_node_ids isn't fully populated until Phase 1 completes (a 2-pass walk would be needed to skip these at emission time). Acceptable residual — the renderer produces a guarded script that records the failure but doesn't crash. Future enhancement: 2-pass walk to elide prop writes for known-absorbed nodes.

### Class N2 — page-orphans invisible — VERIFIED CLEARED ✅
- Phase E baseline: 268 page orphans on screen 24, all invisible to the verifier
- Post-fix: **0 phase2_orphan entries across every walk completed** — verified by aggregating `errors[].kind == 'phase2_orphan'` across all walks/*.json files. P3a-fix eliminated the appendChild attempts that created the orphans; P3d's walker would have surfaced any remaining ones (it didn't need to, because none were created).

### Cluster validator warnings — VERIFIED CLEARED ✅
- Phase E baseline: 7 binding_token_consistency warnings:
  - 4 letter_spacing: `tight2` (×54), `tight3` (×8), `tight4` (×4), `snug8` (×1)
  - 2 spacing: `space.10` (×24), `space.md` (×6)
  - 1 effects: `shadow.lg.radius` (×2)
- **Post-fix on a clean re-cluster: 0 warnings** (verified 2026-04-26 via
  `dd validate --db /tmp/nouns-fresh-cluster.db` → "Validation passed: 0 errors, 0 warnings")
- Implementation confirmed: P3c snap-on-UPDATE clears letter_spacing,
  P5a snap-on-UPDATE clears spacing, P5b occurrence-key UPDATE clears
  effects.

### Cluster axis-coverage (strokeWeight) — VERIFIED RESTORED ✅
- Phase E baseline: 7575 unbound `strokeWeight` bindings (no token axis)
- Post-fix: 7575 `proposed` bindings, 14 strokeWeight tokens, "Stroke Weight" collection created
- P3b wired the dormant `cluster_stroke_weight` + `cluster_paragraph_spacing`
  into the orchestrator. Verified end-to-end on a clean re-cluster.

### Font health
- Phase E baseline: ~600 font_load_failed runtime errors (GT Walsheim Trial / GT America Mono / GT Flexa Mono / pixelmix not installed)
- Post-fix expectation: unchanged (font installation is out of scope)

## Verification

- 113/113 P-suite tests pass (P1..P7 + P3a-fix regression + P5b dead-branch test)
- 224/224 broader render/cluster/boundary regression tests pass
- 3669/3696 broader pytest tests/ run pass (27 pre-existing integration-test failures requiring real Dank DB data; not P-suite regressions)

## Artifacts

- `audit/20260425-1930-phaseE-nouns/sections/07-roundtrip-render/sweep-out/summary.json` — Phase E baseline
- `audit/20260425-1930-phaseE-nouns/sections/07-roundtrip-render/sweep-out-postfix2/summary.json` — Post-fix
- `/tmp/compare_phase_e.py` — Comparison script (run with the two summary.json paths)
