# Phase E — post-fix sweep on Nouns (Experimental)

**Date:** 2026-04-26
**File:** Nouns (Experimental), file_key `B512WwrY9M0Pu4nacnMIPe`, 67 app screens
**Branch:** `v0.3-integration` at tip after P1..P7 + P3a-fix + P5b dead-branch test
**Bridge:** WebSocket port 9225, current page "Generated Test"

## Headline

| metric | Phase E baseline | Post-fix | delta |
|---|---:|---:|---:|
| total | 67 | 67 | 0 |
| `is_parity_true` (strict P1) | 1 | **40** | **+39** (40× improvement) |
| `is_structural_parity_true` | 61 | 62 | +1 |
| `is_parity_false` (DRIFT) | 6 | 4 (+1 walk_failed) | -2 |
| `total_runtime_errors` | 1015 | **52** | **-963 (-94.9%)** |
| `screens_with_runtime_errors` | 66 | 23 | -43 (-65%) |
| `append_child_failed` | 131 | **0** | **-131** (N1 cascade eliminated) |
| `bounds_mismatch` (structural) | 3 | 0 | -3 |
| `text_set_failed` | 698 | 20 | -678 (-97%) |
| `font_load_failed` | 168 | 17 | -151 (-90%) |
| Cluster validator warnings | 7 | 0 | -7 (verified on clean re-cluster) |
| Strokeweight unbound bindings | 7575 | 0 | -7575 (P3b restored axis) |

**Per-screen flips:** 0 regressions (PARITY → DRIFT), 2 recoveries (DRIFT → PARITY: screens 40 + 43, both nouns-ios-explore-05).

**Note on `is_parity_true`:** the baseline number used the OLD lax definition (`is_parity ⇔ structural only`). Post-fix uses the new STRICT P1 definition (`is_parity ⇔ structural AND runtime-clean`). Direct comparison: baseline `is_structural_parity` = 61; post-fix `is_structural_parity` = 62 (+1). The 40× improvement headline is on the strict metric — pre-P1 it was always 1 of 67 (only one screen had zero runtime errors), now it's 40 of 67 (the renderer's aggregated runtime errors fell 95% so most screens are runtime-clean too).

**P4 categories surfaced for the first time:** text_op_failed=20, font_health=17, instance_materialization=15. Total = 52 (matches total_runtime_errors). Categories make the residual signal scannable: 17 of 52 are font-license blockers (out of scope); 20 are text ops that fail downstream of font issues; 15 are instance prop writes on read-only-ish boolean operations. Future work would target the 15 instance_materialization residuals via 2-pass walk.

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

- 122/122 P-suite tests pass (P1..P7 + P3a-fix regression + P5b dead-branch test + P7 ADR-007-removed regression)
- 409/409 P + render + cluster + fidelity + compose + boundary + F12 regression tests pass
- 3669/3696 broader pytest tests/ run pass (27 pre-existing integration-test failures requiring real Dank DB data; not P-suite regressions)
- 4 pre-existing test failures verified against baseline tip 8461403 (3 compress_l3 snapshot drifts + 1 timeout); not caused by P1..P7

## Doc-update follow-ups (deferred)

Per Codex review: "Do not mark all ADR-007 docs superseded: the
unified verification channel is still live in dd/boundary.py,
dd/verify_figma.py, and renderer guards. Only the
RenderProtocol+Repair stack is superseded."

Historical-narrative references to deleted modules remain in:

- `docs/plan-authoring-loop.md` — describes M7.5 substrate
- `docs/research/designer-cognition-and-agent-architecture.md` —
  references repair_agent in role-specialised agent discussion
- `docs/plan-synthetic-gen.md` — M7.5 milestone description

These are historical records of the M7.5 journey, not active
specifications. They could be updated with "(removed in P7)" notes
in a follow-up, but the docs are accurate as historical narrative.
`docs/module-reference.md` (the active module catalog) WAS updated
to mark the deleted modules REMOVED with the Codex caveat preserved.

## Artifacts

- `audit/20260425-1930-phaseE-nouns/sections/07-roundtrip-render/sweep-out/summary.json` — Phase E baseline
- `audit/20260425-1930-phaseE-nouns/sections/07-roundtrip-render/sweep-out-postfix2/summary.json` — Post-fix
- `/tmp/compare_phase_e.py` — Comparison script (run with the two summary.json paths)
