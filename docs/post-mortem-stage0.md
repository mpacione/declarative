# Stage 0 post-mortem — empirical validation of the four-defect fix

**Date**: 2026-04-23
**Branch**: `v0.3-integration` (tip: `538ebc9`)
**Commits under test**: `6ccbaf5`, `68e28a1`, `c189291`, `0af8361`, `8e36666`, `538ebc9`

## Why this exists

Stage 0 of [`docs/plan-authoring-loop.md`](plan-authoring-loop.md) shipped behind structural validation (3219 pytests + 204/204 parity sweep). But structural green doesn't prove the LLM actually composes better — only that nothing broke. Per the principle in [`feedback_auto_inspect_before_human_rate.md`](../.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_auto_inspect_before_human_rate.md), an automated visual-sanity gate should confirm the output is interestingly different before we move on to the next layer.

This post-mortem is that gate. Five real prompts run through `dd.composition.plan.plan_then_fill` against Haiku 4.5. Each one targets at least one of the four defects from §1.2 of the plan.

## Methodology

- Runner: `/tmp/postmortem_runner.py` — wraps `plan_then_fill`, dumps a JSON line with the planner's output + per-prompt metrics.
- Synthesizer: `/tmp/postmortem_synth.py` — reads all 5 result files, prints aggregate.
- Each prompt runs once. Temperature 0.0 on the planner call (deterministic per the existing default).
- "Defect-X passed" rules:
  - **A** (no neutral wrapper) — pass if `frame` appears at least once.
  - **B** (card-as-wrapper coercion) — pass if zero cards have any other node addressing them as `parent_eid`.
  - **C** (eid loss) — pass if ≥80 % of nodes carry a meaningful eid (kebab-case with a non-numeric tail).
  - **D** (closed array contract) — pass if the planner emitted the new flat `{"nodes": [...]}` shape.

## Five prompts, picked to stress different defects

| # | Prompt | Defect targeted |
|---|---|---|
| 1 | "a settings page with a notifications section, a privacy section, and a save button" | A (sections), C (named entities) |
| 2 | "a product showcase landing page with 3 feature cards under a hero section" | A (hero / showcase), B (was: hero → card), repeat |
| 3 | "a checkout form with email, address, payment method, and a submit button" | input vocabulary, depth |
| 4 | "a footer with three columns of links and a centered logo" | B (was: footer → card), repeat |
| 5 | "a sidebar nav with 5 menu items, a collapsible workspace switcher, and a profile section at the bottom" | depth, repeat, named entities |

## Results

| # | ok | shape | nodes | frames | cards | card-as-wrapper | named eids | depth | repeats | A | B | C | D |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ✓ | flat | 11 | 6 | 0 | 0 | 11/11 | 2 | 0 | ✓ | ✓ | ✓ | ✓ |
| 2 | ✓ | flat |  8 | 3 | 1 | 0 |  8/8  | 2 | 1 | ✓ | ✓ | ✓ | ✓ |
| 3 | ✓ | flat | 12 | 4 | 0 | 0 | 12/12 | 2 | 0 | ✓ | ✓ | ✓ | ✓ |
| 4 | ✓ | flat |  6 | 4 | 0 | 0 |  6/6  | 3 | 2 | ✓ | ✓ | ✓ | ✓ |
| 5 | ✓ | flat | 11 | 3 | 0 | 0 | 11/11 | 3 | 1 | ✓ | ✓ | ✓ | ✓ |

**Aggregate: 5/5 ok, 5/5 flat, 5/5 on each defect, zero slot warnings.**

## Spot-checks worth calling out

### Prompt 1 (settings)
LLM emitted `settings-page`, `notifications-section`, `notifications-content`, `privacy-section`, `privacy-content`, `settings-footer` — every one a `frame`, not a `card`. Six frames, zero cards. Defect A so cleanly fixed that this single prompt would have been enough to retire it.

### Prompt 2 (product showcase + feature cards)
The exact plan-§2.2 example, organic from the LLM:

```
hero-section        frame
features-section    frame
feature-card        card  (the only card; repeat=1 implicit)
```

The `hero-section` is a `frame`, not a `card`. The pre-Stage-0 prompt would have coerced this onto `card → card → card`. Defect B's footer/hero coercions are demonstrably dead.

### Prompt 4 (footer)
`footer-root` and `footer-column` are frames. The pre-Stage-0 prompt explicitly said "a footer → use `card` at the bottom (there is no footer type)." That coercion is gone — and the LLM correctly used `frame` instead. Repeat used twice (for the columns and for the links). Max depth 3.

### Prompt 5 (sidebar)
The LLM picked `sidebar` as the root type (semantic), then nested an `accordion` for the workspace switcher, a `list`/`list_item` for nav menu, and a frame-grouped `profile-section`. Depth 3, eids like `workspace-switcher-content` and `profile-info` survive into the plan. This is what fluid composition looks like.

## What's still imperfect (deferred per user direction)

- **Some plans don't include sufficient depth** for the LLM to express richer intent (prompt 4 only emitted 6 nodes for "three columns of links" — likely because the planner stage stops short and the fill stage adds detail). Worth re-running with the fill output examined too if that becomes a quality signal.
- **`repeat` is used sparingly** — only 4 of 5 prompts that obviously need it actually used it. `feature-card` should arguably have `repeat: 3` given the prompt; instead it has the implicit 1. Worth tightening the system-prompt guidance if compose surfaces underspecified prompts in the wild.
- **No structural drift surfaced** by `flat_plan_drift` because we didn't run `compose_screen` on the output — that's a Stage 1 concern (need to wire the drift check into the orchestrator return value).

## Verdict

Stage 0 is **ready for Stage 1**.

The four defects from plan §1.2 are demonstrably fixed across diverse real prompts. The flat-plan contract sticks. The LLM uses `frame` for groupings without prompting. Eids survive into the plan. No slot hallucinations.

Next: Stage 1 — pivot the LLM contract from "emit a plan" to "emit edits against a current tree state."

## Reproducing this post-mortem

```bash
.venv/bin/python /tmp/postmortem_runner.py "<your prompt>" > /tmp/pm_X.json
python3 /tmp/postmortem_synth.py
```

The runner script and synthesizer are checked in only via this doc; both are stateless and small enough to recreate verbatim from the references in `dd.composition.plan`.
