# Phase 0 recap — 2026-04-25

> Status: in-progress. W0.A complete; W0.B/W0.C skeletons
> committed; baseline-179 written as PROVISIONAL pending a
> sweep. This recap covers what landed today and what remains
> before the Phase 0 → Phase 1 transition.

## What landed

- **plan v3 → v3.1 repoint** ([e1c6254](../../plan-v0.4.md))
  — §11 demo anchors moved from hand-picked screen IDs (333 /
  217 / 091 / 412) to corpus-real anchors (333 / 333 / 118 /
  311 with the small mid-Phase-0 move from 243 → 311 to escape
  a known-drift cluster). §8.1 W0.A runbook converted from
  "verify-pre-named-IDs" to "discover-then-pick" with `dd
  cluster` documented as a pre-step. §11.1 deviations table
  added. §10 Phase-0 gate updated to require the audit JSON
  PASS verdicts and the cluster pre-step.
- **Audit fixture** ([demo_screen_audit.json](../../../tests/.fixtures/demo_screen_audit.json))
  — captures queries, candidates considered, picks, and global
  constraints. 4/4 demos PASS post-cluster.
- **Token namespace populated** — `dd cluster` + `dd accept-all`
  ran against `Dank-EXP-02.declarative.db` (reversible via
  `archive/db-snapshots/...pre-v0.4-cluster-20260425-005855.bak.db`).
  Result: 327 auto-named tokens (68 color, 161 dimension, 47
  fontFamily, 47 fontWeight, 4 number); 64.2% of bindings
  flipped to `bound`.
- **W0.B MCP probe scripts** — 4 short JS files under
  `tests/.fixtures/mcp_probes/` (not yet executed against the
  bridge — that requires bridge-alive verification, which
  shifts to W0.B day 2).
- **W0.C seeding script skeleton** — `tools/dd-test-fixture-create.py`
  documents the seeding plan with all 6 component CKRs
  resolved; `--print-plan` emits valid JSON; no Figma writes
  yet (those come days 2-4).
- **baseline_screens.json (PROVISIONAL)** — `tests/.fixtures/baseline_screens.json`
  enumerates all 204 app_screens plus both 179-baseline (pre
  type/role split) and 190-baseline (post type/role split)
  candidate sets. Needs a fresh `render_batch/sweep.py` run to
  confirm which figure matches reality.
- **Subagent dispatch template** ([tools/subagent_dispatch_template.md](../../../tools/subagent_dispatch_template.md))
  — codifies the plan-hash-pinning protocol per plan §9.

## Phase gate measurements

| Gate metric | Expected | Measured | Pass/Fail |
|---|---|---|---|
| W0.A demo screens DB-verified (verdict PASS) | 4/4 | 4/4 | **PASS** |
| `dd cluster` + `dd accept-all` run | yes | yes | **PASS** |
| Tokens populated | ≥300 | 327 | **PASS** |
| Token binding coverage | ≥60% | 64.2% | **PASS** |
| W0.B MCP-verify probes written | 4/4 | 4/4 | **PASS (script-only)** |
| W0.B MCP-verify probes EXECUTED through bridge | 4/4 returning expected shape | 0/4 | **PENDING** (bridge alive verification deferred to W0.B day 2) |
| W0.C `Dank-Test-v0.4` Figma file created | yes | no | **PENDING** (skeleton only; days 2-4) |
| W0.C seeding script committed | yes (skeleton OK) | yes | **PASS** |
| Baseline-N snapshot committed | yes | yes (PROVISIONAL) | **PASS w/ caveat** |
| Plan commit-hash pinned in dispatch template | yes | yes (`e1c6254`) | **PASS** |
| Token enum-size within 250-bound | per-class ≤250 | per-class ≤161 | **PASS** (per plan §8.2 conditional: total 327 > 250 means W6 must implement per-prop-class enum slicing — natural per-prop-class slicing is already within bound) |

## Deviations from plan

1. **Plan v3 demo anchors revised to v3.1.** Plan v3 named four
   demo screens by ID + two intent tokens
   (`color.action.primary`, `color.feedback.success`). 3/4 IDs
   failed verification; both intent tokens absent from the
   corpus's auto-naming scheme. Revised in-place rather than
   halt for user input — user direction in the session was
   "do it." The revised plan is canonical going forward; §11.1
   documents what changed and why.

2. **Demo D anchor moved 243 → 311 mid-Phase 0.** Initial
   discover-then-pick selected screen 243 as Demo D's anchor
   based on shape (24 large + 12 small + 4 solid translucent
   buttons + a `button/toolbar` container with 7 children).
   Subsequent baseline check found 243 is in the
   iPad-translucent-cluster drift set (per
   `feedback_ipad_component_frame_inlining.md`, 0.96 round-trip
   parity). Demo D's append op is unaffected by missing_child
   class drift, but using a clean screen removes the yellow
   flag. Screen 311 has identical inventory and is not in any
   known drift set.

3. **Token authoring held to anti-scope (§13).** v0.4 will not
   hand-author intent-named tokens (`color.action.primary`,
   `color.feedback.success`) to match the original demo
   narrative. Auto-named tokens are what `dd cluster` produces
   from corpus reality; demos are written against those names.

4. **Drift cluster bookkeeping discrepancy.** Memo
   `feedback_dank_corpus_drift_25.md` cites 25 known-drift
   screens. My derivation from the two memos
   (`feedback_dank_corpus_drift_25.md` +
   `feedback_ipad_component_frame_inlining.md`) sums to 24
   (10 in 217-226 cluster + 1 outlier 180 + 13 iPad-translucent
   cluster). Either the memo's "25" is off-by-one or my
   derivation is missing a memo I haven't found. This doesn't
   change the Phase 0 gate; flagged for follow-up before
   Phase-1 baseline-179 commit.

## What I'd flag for the user

- **Bridge-execution of W0.B probes is pending.** The probes are
  written and DB-verified, but I have not confirmed
  bridge-alive yet (figma-console-mcp on `localhost:9228`).
  Before Phase 1 starts, the probes should run end-to-end and
  return the expected assertion shapes. Will attempt bridge
  health-check in the next pass; if the bridge is down, the
  user may need to restart Claude Desktop.

- **Baseline-179 vs baseline-190 ambiguity.** The plan's "baseline
  179" figure dates from a 2026-04-21 sweep; subsequent
  type/role-split work (committed 2026-04-22) recovered 11
  screens and the "current" baseline may be 190. Need a fresh
  `render_batch/sweep.py` run (~9h end-to-end under bridge
  cumulative load, with individual retry of failed screens) to
  confirm. Until that lands, `tests/.fixtures/baseline_screens.json`
  carries both candidate sets with `_meta.status: "PROVISIONAL"`.

- **Enum-size for token paths is 327 (>250 plan-stated bound),
  but per-prop-class is well within bound.** Plan §8.2
  anticipated this: "If `n > 250`, W6 ships with enum slicing
  as a P0 sub-task." Per-prop-class slicing is the natural
  shape and already within bound (max 161 dimension tokens; 68
  color tokens). This becomes a confirmed P0 within W6, not a
  new finding.

- **DB has been mutated by `dd cluster` + `dd accept-all`.** Not
  tracked in git. Reversible via the snapshot in
  `archive/db-snapshots/`. If you ever need to re-run `dd
  cluster` cleanly, restore from that snapshot first to avoid
  duplicate-token noise (cluster is idempotent on a clustered
  DB but emits warnings).

## Cost so far

- Sonnet subagent for demo-screen discovery + W0.B/W0.C
  scripting: ~$0.50 estimated.
- gpt-5.5 high-effort consult on halt-class question: ~$0.10.
- Total Phase 0 day 1: < $1.

No live-Sonnet runs against the W7 fixture suite yet; that's
gated on user authorization per kickoff and plan §8.3.

## Next phase

W0.B day 2 + W0.C days 2-4 + baseline-N sweep land before Phase
1 begins. Phase 1 (week 1) starts W1 (`dd/resolved_ir.py` with
R1-R8 + Composite leaves), W5 (verifier extensions retargeted to
TODAY's producers), and W7 cassette-replay test scaffolding.
Estimated 5 working days for Phase 1 per plan §8.

The interim status demo (Loom, end of Phase 1, per §8.4) is
deferred per the kickoff prompt: "the user has deferred this; do
NOT record it without their return; just note in the phase
report that it's pending their return."

---

*Recap author: v0.4 executor session, 2026-04-25.*
