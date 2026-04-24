# Declarative Build — session entrypoint

Single-file orientation for a Claude session arriving cold. Read this
first, then open the linked docs.

## Status at a glance

- **Current branch**: `v0.3-integration` (tip `a5d01bb`)
- **Stages 0–3 of `docs/plan-authoring-loop.md` have shipped.** Stage 4+
  is explicitly deferred.
- **204/204 effective round-trip parity sweep holds.** (The raw sweep
  number is 169/204 PARITY + 35 `walk_failed` on contiguous IDs 270–304
  — the documented bridge cumulative-load pattern. Individual retry
  puts all 35 at PARITY. Zero `is_parity=False`.)
- **`dd design --brief "…"` is a working command.** Real-Sonnet 4-iter
  capstone halted cleanly in 17.4 s with 4 thoughtful EDITs against
  Dank screen 333.
- **Test suite**: 3375 pass, 15 skip (API-key / DB-gated). Baseline
  diff zero new regressions — the 41 FAILED + 7 ERROR are pre-existing
  optional-dep / DB-fixture failures.

## Where to read (in order)

1. `docs/plan-authoring-loop.md` — the canonical plan. Stages 0–3
   shipped; Stage 4+ deferred. §1.2 has the four-defect diagnosis that
   drove Stage 0. **The plan is prescriptive; line numbers drifted and
   two cleanup items were wrong — trust the rationale docs when they
   conflict.**
2. `docs/rationale/README.md` — why we built it the way we did.
   One doc per stage + an index. Each stage-doc records the design
   forks, where the plan got audit-corrected, and the real-LLM
   capstone result.
3. `docs/post-mortem-stage0.md` — empirical Stage 0 validation: five
   Haiku prompts, all four defects fixed.
4. Your assistant memory path — session-to-session context (project
   notes, feedback entries, index).

## Where NOT to read (unless researching a past decision)

- `docs/archive/` — superseded plans, historical continuations.
- `docs/archive/research/` — the t5-\* pre-v0.3 research cluster.
- `scripts/archive/` — shipped-M7.x demos preserved for reference.
- `archive/` — non-doc artifacts (DB snapshots, scratch runs).

## What's running

- `dd design --brief "…"` — agent session loop (Stage 3).
  - `dd design resume <session>` — continue (or branch from a
    non-leaf variant).
  - `dd design score <session>` — stub (confirms session + variant
    count; real fidelity pass deferred).
- `python3 render_batch/sweep.py` — 204-screen round-trip parity
  sweep. Expect ~9 h end-to-end under bridge cumulative load; retry
  contiguous timeouts individually.
- `pytest` — full suite, 3375 pass, 15 skip.

## What's NOT shipped

- `dd design score <session>` has no scoring backend yet. Currently
  a stub. See `docs/rationale/stage-3-session-loop.md`.
- Stage 4+ deferrals: linkography monitor, MCTS, multi-agent role
  split, canvas UI, sketch input, pattern auto-accretion, per-designer
  DPO. Variant-graph hooks exist (parent_id self-FK + scores JSON).
- **Demo-cleanup follow-up PR.** Plan §4.1 Stage-3 cleanup listed four
  superseded demos (~1647 LOC) for deletion; we deliberately split it
  from the orchestrator PR to protect the atomic-commit discipline.
  Not yet shipped.
- Two cosmetic residuals on screen 333: swap-then-text addressing.
  Not a blindness issue — that was fixed in `538ebc9`. It's a
  swap-then-override coordinate-frame mismatch, a separate bug class.
  See `feedback_skipinvisible_findone_blindness.md` (kin section).

## If you're continuing work

- **Read the stage rationale docs, not the individual commit
  messages.** The commits are granular (23 commits across Stages 0–3);
  the rationale docs compress them into design decisions + forks.
- **Trust the rationale docs when they conflict with the plan.** The
  plan document is prescriptive (what we intended to do); the
  rationale documents what we actually did + why it diverged — line
  numbers drifted, two "dead code" cleanup items turned out to be
  load-bearing, one "already wired" hook was wired but behind a
  feature we weren't using.
- **Codex was consulted on every major fork.** Decisions are recorded
  inline in `docs/rationale/` (search for "Codex"). When in doubt,
  re-consult Codex rather than reverse-engineering from code.

## The one-line framing

**Declarative Build is a compiler for design systems.** Figma in,
Figma out (today); React / SwiftUI / Flutter out (next). Stages 0–3
added the authoring loop that lets an LLM write the compiler's source
language — incrementally, persistently, at arbitrary composition
depth — against the user's own components and tokens.