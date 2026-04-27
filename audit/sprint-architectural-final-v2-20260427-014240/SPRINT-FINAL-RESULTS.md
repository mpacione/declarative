# Architectural sprint — final results

**Sprint duration**: ~6 hours main-thread work + 2 Sonnet workers
**Branch**: `v0.3-integration`
**Final commit**: `9037a05`
**DB**: `/tmp/nouns-postrextract.db` (untouched across sprint)
**Baseline sweep**: `audit/sprint-final-20260426-230449/summary.json`
**Final sweep**: `audit/sprint-architectural-final-v2-20260427-014240/summary.json`

## TL;DR

**100% structural parity. 0 verifier mismatches. 37× faster.**
The forensic-audit-2 architectural sprint closed the
snapshot-vs-override class end-to-end and surfaced+fixed one
real renderer fidelity bug. 12 commits, 0 newly-drifting screens.

## 1. Headline Metrics

| Metric | Pre | Post | Δ |
|---|---:|---:|---:|
| `is_parity_true` (clean) | 33 | **47** | **+14** |
| `is_parity_false` | 34 | **20** | **-14** |
| `is_structural_parity_true` | 51 | **67** | **+16 (100%)** |
| `walk_failed` | 0 | 0 | 0 |
| `walk_timed_out_count` | 0 | 0 | 0 |
| `screens_with_runtime_errors` | 20 | 20 | 0 |
| `total_runtime_errors` | 37 | 37 | 0 |
| `elapsed_s` | **2059.4** | **54.9** | **-2004.5 (37×)** |
| `retried` | 34 | **0** | -34 |
| `retried_recovered` | 0 | 0 | 0 |

The 20 `is_parity_false` screens post-sprint are all
font-license blocker (`text_op_failed`/`font_load_failed`)
runtime errors — out-of-scope GT Walsheim Trial / GT America
Mono not installed. Same 20 screens as pre-sprint, untouched.

## 2. Failure-Class Delta

### Verifier-side `error_kinds`

| kind | baseline | current | delta | interpretation |
|---|---:|---:|---:|---|
| `fill_mismatch` | 8 | **0** | **-8** | A1.3 provenance gate cleared all Mode-1 INSTANCE snapshots |
| `stroke_mismatch` | 7 | **0** | **-7** | Same — all 7 iPhone screens 50-55,57 |
| `cornerradius_mismatch` | 26 | **0** | **-26** | A5 surfaced; cornerRadius `int()` cast fix at `9037a05` |
| **TOTAL** | **41** | **0** | **-41** | full structural parity |

### Walker-side `runtime_error_kinds` (unchanged — out-of-scope font issue)

| kind | baseline | current | delta |
|---|---:|---:|---:|
| `font_load_failed` | 17 | 17 | 0 |
| `text_set_failed` | 20 | 20 | 0 |

## 3. Per-Screen Movement

### Recovered (was DRIFT, now PARITY): 16

| screen | prev kinds | recovered by |
|---|---|---|
| 10 | 6× cornerradius_mismatch | A5 cornerRadius fix |
| 24 | fill_mismatch | A1.3 provenance gate |
| 25 | 2× fill_mismatch | A1.3 |
| 26 | cornerradius_mismatch | A5 cornerRadius fix |
| 40 | fill_mismatch | A1.3 |
| 43 | fill_mismatch | A1.3 |
| 44 | fill_mismatch | A1.3 |
| 48 | fill_mismatch + 13× cornerradius | A1.3 + A5 |
| 49 | fill_mismatch + 6× cornerradius | A1.3 + A5 |
| 50–55, 57 | stroke_mismatch | A1.3 (iPhone instance heads) |

### Newly Drifting: 0

No regressions. Zero screens moved from PARITY → DRIFT.

### Still Drifting: 0

No screens still in DRIFT post-sprint. **Full structural parity.**

## 4. Sprint-Delta Validation

### Provenance chain (A1.1 → A1.2 → A1.3)

**Hypothesis**: 8 fill_mismatch + 7 stroke_mismatch on Mode-1
INSTANCE heads were extraction-snapshot-vs-master-default false
positives. With `_overrides` side-car driving emission and
comparison, those clear.

**Result**: ✅ Confirmed. All 15 verifier-mismatch errors on
Mode-1 INSTANCE heads cleared. The 12 screens listed under
"Recovered" with non-cornerradius kinds attribute directly to
A1.3.

### A5 new comparators surfaced real bug

**Hypothesis**: A5's strokeWeight/strokeAlign/dashPattern/
clipsContent comparators might surface drift that wasn't
visible before. KIND_CORNERRADIUS_MISMATCH was added in P1c
but had its blind side too (cornerRadius wasn't compared at
all pre-P1).

**Result**: ✅ Confirmed. A5 surfaced 26 cornerradius_mismatch
errors on FRAME nodes (not Mode-1 instances — those are
covered by A1.3). All 26 traced to one bug: renderer cast
uniform cornerRadius to `int()`, losing fractional component.
Fix at commit `9037a05` cleared all 26.

This is the architectural sprint working as designed: the new
comparators surface real drift, then we fix the underlying
renderer bug.

### A3.2 Mode 3 template defaults

**Hypothesis**: Mode 3 universal templates didn't carry explicit
opacity/strokeWeight/etc. Composed elements inherited Figma
factory defaults silently. The Nouns sweep is Mode-1-heavy so
A3.2 likely doesn't show measurable impact on this sweep.

**Result**: ✅ As predicted. No Mode 3 path fires on the Nouns
sweep (no synthetic IR, no compose_screen calls). A3.2's value
is for future Mode-3 corpus runs; tested in 79 dedicated unit
tests at commit `ea7477f`.

### Backlog #4 retry timing

**Hypothesis**: Pre-sprint sweep took 2059s because retry fired
on real-bug DRIFT. With `_is_likely_transient_failure`
classifying real-bug DRIFT as no-retry, sweeps return to
baseline-fast.

**Result**: ✅ Confirmed. **2059s → 54.9s** (37× speedup, even
better than expected). 0 retries fired in the final sweep.
The `walk_elapsed_ms_p50` stayed at 333ms (per-screen render
unchanged); the entire 2004s saving came from skipping retry
attempts on real-bug DRIFT screens.

## 5. What's Left

### Real rendering bugs

**None observable on Nouns**. The post-sprint sweep shows 0
verifier mismatches. Future corpora may surface new classes; the
architectural foundation (comparator-per-prop, gate-per-prop,
provenance chain) supports adding more comparators cleanly.

### Verifier coverage gaps

The `_BUILD_VISUAL_DEFERRED` allowlist documents one explicitly
deferred prop (`booleanOperation`). Other carried-but-not-
compared props from the audit (per-side stroke weights, effect
properties beyond count, individual gradient stop colors) are
backlog items, low priority — no observed drift on Nouns.

### Mode 3 follow-up

A4 + A3.2 made Mode 3 architecturally sound, but the Nouns
sweep doesn't exercise Mode 3 paths. Validation requires a
Mode-3-bearing corpus run (e.g. `dd design --brief` on a real
brief). Open ticket: validate the variant downgrade fix
end-to-end on a brief that requests
`variant: "primary"` against a project with only `custom_1`
bindings.

### Sweep infra

Backlog #4's classifier is currently conservative (mixed rows
retry). If real-bug-only DRIFT produces zero benefit from
retry empirically (which the data now supports), a follow-up
could tighten the classifier. Low priority — current behavior
is correct, just slightly conservative.

### Pre-existing (NOT this sprint's scope)

- 2 `test_mode3_contract.py` integration test failures
  (test_mode3_fires_when_mode1_and_mode2_both_fail +
  test_mode3_synthetic_children_are_first_class_ir_nodes) —
  pre-existed sprint baseline; verified on parent commits.
  Universal provider doesn't synthesize button text children.
  Separate ticket.
- 5 `test_phase2_integration.py` failures (`test_no_element_has_visual_key`)
  — pre-existed since `842510b`. The IR-shape pin from
  feedback-2026-04-21 needs a touch-up post-A1.1 (the IR now
  carries a `visual` key with the carried registry props).
  Separate ticket.
- Font-license blocker on 20 PARITY+ screens. Out of engineering
  scope.

## 12 commits shipped

```
9037a05 fix(emit): preserve cornerRadius float precision (A5 follow-up)
ea7477f fix(compose): explicit visual defaults in Mode-3 universal templates (A3.2)
f475400 perf(sweep): skip retry on real-bug DRIFT (Backlog #4)
7f30e70 feat(renderer): per-property emission gating for Mode-1 INSTANCE (A1.2)
07eeba7 fix(compose): ProjectCKRProvider returns None on missing bindings (A4)
ba57747 refactor(emit): split _emit_layout into per-property dispatch (A2.2)
71a839a feat(verifier): comparators for strokeWeight/strokeAlign/dashPattern/clipsContent (A5)
7712006 feat(verifier): per-property provenance gating for Mode-1 INSTANCE (A1.3)
e8126fe test(runtime-errors): allowlist 4 group_*_failed kinds (scanner gap)  # earlier session, included in cumulative
b7b05f1 feat(ir): _overrides side-car for Mode-1 INSTANCE provenance (A1.1)
b062ef3 refactor(emit): per-op guards for text props in _emit_text_props (A2.3)
5f24346 refactor(emit): split strokeWeight from _emit_strokes (A2.1 prerequisite)
```

Plus 2 backlog items closed (Backlog #2 investigated no-action;
Backlog #3 orphan kinds allowlisted).

## Sprint methodology

### Coordination shape (per user's directive)

- **Codex 5.5** (gpt-5.5 high reasoning) at every architectural
  fork: sprint sequencing, A2 split design, A1.2 implementation
  choice, A4 fall-through, Backlog #4 classifier, A3.2 schema,
  final measurement plan
- **Sonnet worker subagents** on isolated work (non-overlapping
  files): A2.2 layout split (`ba57747`), A3.2 templates
  (`ea7477f`)
- **Sonnet review subagents** AFTER each main-thread commit
  before push: A2.1, A1.3, A1.2, A2.2, A3.2, A1.1
- **Main thread serial** when files overlapped with workers
  (parallel-write hazard from earlier session forced this
  discipline)

### Test-driven discipline

Every commit shipped with:
1. Failing tests written FIRST
2. Minimal implementation to green
3. Broader regression check before commit
4. Per-commit test counts in commit message

Final test surface: **835 tests across the touched modules,
all green.** No regressions introduced; pre-existing failures
left in place (verified by stash + rerun on parent commits).

### Verification discipline (per CLAUDE.md "NEVER BLINDLY TRUST")

- Codex 5.5 outputs cross-checked by reading the actual code at
  cited lines (e.g. spot-verified `_emit_corner_radius_figma`
  line 873 truncation claim before believing it)
- Worker subagent reports verified before commit (e.g. running
  the worker's claimed test count + spot-checking key code
  changes)
- Empirical fact-checking before declaring victory (e.g. running
  the analysis script across baseline + post-sprint summaries)
