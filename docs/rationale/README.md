# Rationale — the authoring loop (`v0.3-integration`, Stages 0–3)

## What this folder is

A cold-read companion to [`docs/plan-authoring-loop.md`](../plan-authoring-loop.md). The plan says what we set out to build. These docs say what we actually built, where the plan was wrong, what forks we hit, and where the code lives. If you're returning to this project in two weeks and the plan looks like implementation-already-done, start in [`ENTRYPOINT.md`](ENTRYPOINT.md), then read whichever stage you're touching, then skim [`what-the-plan-got-wrong.md`](what-the-plan-got-wrong.md) before trusting any line number in the plan.

## The throughline

The LLM writes dd-markup. The compiler does the rest. The authoring loop makes it a workflow.

Before Stage 0 the LLM emitted a closed, top-down, nested component array — no neutral wrapper, coercion rules that taught `section → card`, and compose discarded any eid the planner named. That made multi-depth composition impossible. Stages 0–3 kept every invariant the renderer dispatches on closed (type / variant / component_key / slot / verb / token) and opened every field the runtime treats as a label or address (eid / copy / depth / groupings). Stage 0 fixed the contract, Stage 1 replaced "emit a plan" with "emit 7-verb edits against the current tree," Stage 2 added deterministic NAME/DRILL/CLIMB primitives over edits, Stage 3 gave the whole thing a persistence layer and a `dd design` CLI.

## Stage ledger

| Stage | One-line goal | Shipped commits (v0.3-integration) |
|---|---|---|
| 0 | Add `frame` primitive; delete coercion; preserve planner eids; flat plan shape; slot validation | `6ccbaf5` → `8e36666` (+ visibility-toggle follow-on `538ebc9`) |
| 1 | Pivot LLM contract to `propose_edits` over 7 verb tools | `8446769` → `ddd5866` |
| 2 | Deterministic NAME/DRILL/CLIMB primitives over FocusContext | `fd5c5c5` → `cf677d1` |
| 3 | `dd design --brief` CLI + session persistence + branching | `75a55b7` → `a5d01bb` |

Branch tip at writing: `a5d01bb`.

## Suggested read order

1. [`ENTRYPOINT.md`](ENTRYPOINT.md) — one-page map of where we are and what ships.
2. [`../plan-authoring-loop.md`](../plan-authoring-loop.md) — the canonical plan. Read the body; distrust line numbers.
3. Per-stage rationale — the stage you're touching. Each file ends with where-the-code-lives, acceptance + capstone, forks, and plan-vs-reality.
4. [`what-the-plan-got-wrong.md`](what-the-plan-got-wrong.md) — the four specific plan errors (phantom tools, dead code that wasn't dead, drifted line numbers, Tension A reversal).

## Per-stage summaries

**[stage-0-contract.md](stage-0-contract.md).** The four-defect fix. Adds `frame` as the only neutral wrapper, widens the catalog category CHECK via migration 022, teaches `_allocate_id(preferred_eid=)` to keep the planner's names, replaces the nested component array with a flat parent_eid/order table, validates slot names (log-only first), and upgrades the drift check to structural tuple comparison. Five Stage-0 commits plus a sixth `538ebc9` that reversed Tension A after visual inspection caught `skipInvisibleInstanceChildren=true` silently breaking `findOne` against master-default-hidden slots. Post-mortem result: 5/5 Haiku prompts pass all four defect checks.

**[stage-1-propose-edits.md](stage-1-propose-edits.md).** New tool surface: seven per-verb tools (set, append, insert, delete, move, swap, replace), one `propose_edits` orchestrator in `dd/propose_edits.py`. Starting-IR is whatever doc you pass in (empty, extracted screen, or mid-session state). Real-Haiku capstone deleted a decorative rectangle from Dank screen 333 in 2.58s with a sensible rationale.

**[stage-2-focus-primitives.md](stage-2-focus-primitives.md).** `FocusContext` (frozen dataclass) + `extract_subtree` + `is_in_scope`. Three primitives — NAME (metadata), DRILL (focus-as-view on root doc, edits apply against root via stable eids), CLIMB (focus pop). `drilled_propose_edits` wraps it. Codex picked deterministic Python over LLM-callable tools; Stage 3 later chose to expose them as tools inside the session loop, same semantics. Haiku capstone: DRILL into `ipad-pro-11-43`, delete `@rectangle-22280`, 2.19s.

**[stage-3-session-loop.md](stage-3-session-loop.md).** Migration 023 (three tables: `design_sessions`, `variants` with gzipped TEXT markup_blob inline, `move_log`). ULIDs for PKs. `dd design --brief` / `resume` / `score` CLI. Branching falls out of resume-from-non-leaf — no separate `branch` verb. Option 3 (hybrid) + B (keep move_log) picked unanimously by Codex + Sonnet. Real-Sonnet capstone: 4-iter session on Dank 333, four thoughtful delete rationales targeting decorative magnifier-mask rectangles, halted cleanly at max_iters in 17.4s.

## Where NOT to read

- `docs/archive/` — superseded plans (pre-Option-B CompRef work, pre-Stage-0 coercion docs). Kept for historical record only. Anything in there is stale by construction.
- `/tmp/postmortem_*.py` — Stage 0 post-mortem reproducer scripts. Intentionally un-checked-in; recreate from `dd.composition.plan` if you need them.

## Cross-links

- Canonical plan: [`docs/plan-authoring-loop.md`](../plan-authoring-loop.md)
- Empirical gate: [`docs/post-mortem-stage0.md`](../post-mortem-stage0.md)
- Memory (auto-updated across sessions): `.claude/projects/-Users-mattpacione-declarative-build/memory/project_stage{0_postmortem,1_complete,2_complete,3_complete}.md`
- Visibility-toggle post-mortem: `.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_skipinvisible_findone_blindness.md`
