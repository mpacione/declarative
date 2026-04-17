# 00h-mode3-v5 — A2 plan-then-fill live, end-to-end

v0.1.5 Week 2 Step 6. 12 canonical prompts through plan-then-fill (A2)
with the archetype library feeding the plan as a structural floor.
Goal: close the 6→≥7 VLM-ok gap per plan §5 stopping criterion.

## Headline: A2 REGRESSED vs A1

| metric | 00f | 00g (A1) | **00h (A2)** | Δ vs A1 |
|---|---:|---:|---:|---:|
| VLM-ok | 4 / 12 | 6 / 12 | **4 / 11** | **−2** |
| VLM-partial | 5 / 12 | 4 / 12 | 4 / 11 | 0 |
| VLM-broken | 3 / 12 (+1 timeout) | 2 / 12 | 3 / 11 | +1 |
| KIND_PLAN_INVALID | 0 | 0 | **1 / 12** (paywall) | +1 |
| fill_retried | — | — | 0 / 11 | — |
| round-trip parity | 204 / 204 | 204 / 204 | 204 / 204 | preserved |

**Net: −3 VLM-ok + 1 new failure mode.** Ships as a regression.

## Per-prompt (00g A1 → 00h A2)

| slug | 00g VLM | 00h VLM | shift |
|---|---|---|---|
| 01-login | ok (8) | ok (7) | flat |
| 02-profile-settings | ok (8) | ok (7) | flat |
| 03-meme-feed | partial (4) | partial (5) | flat |
| 04-dashboard | broken (3) | broken (2) | flat |
| 05-paywall | ok (8) | **KIND_PLAN_INVALID** | **regress** |
| 06-spa-minimal | partial (5) | broken (2) | regress |
| 07-search | ok (8) | partial (5) | regress |
| 08-explicit-structure | ok (8) | ok (7) | flat |
| 09-drawer-nav | partial (4) | partial (5) | flat |
| 10-onboarding-carousel | broken (2) | broken (2) | flat |
| **11-vague** | partial (4) | **ok (7)** | **gain** |
| 12-round-trip-test | ok (8) | partial (5) | regress |

3 regressions, 1 gain, 1 hard-failure, 7 flat.

## Why A2 regressed (hypothesis)

1. **Plan-then-fill is strictly more constrained than A1's
   SYSTEM_PROMPT injection.** A1 gave Haiku the skeleton as
   inspiration with T=0.3 and let it fill freehand. A2 pins the
   structure first, then the fill call is bound by plan-diff — the
   fill LLM is less free to expand or add richness.
2. **Plan-LLM-at-T=0.0 is minimal-biased.** First 00h pass (before
   the skeleton-floor fix) produced even sparser plans. Adding the
   archetype-skeleton-as-floor recovered count but not *variety* —
   the plan covers the floor but no more.
3. **Fill LLM truncation on long plans.** Paywall plan has
   ~30 nodes across 3 pricing tiers + testimonial; fill's
   system_prompt carries the full plan JSON verbatim. Haiku's fill
   returned `[]` twice → KIND_PLAN_INVALID. Probably hit an
   attention-exhaustion / JSON-parse dead end when the system prompt
   approaches 4k tokens and output budget is 2048.
4. **Plan-diff is too strict for the reality of Haiku output.** The
   current diff counts types across the full tree; a plan like
   `card(count_hint=3) -> [image, heading, text]` expects 3 images +
   3 headings + 3 texts. Haiku often respects `card: 3` but shortens
   the inner contents on repeat cards.

## What A2 actually bought

- **11-vague gained.** The vague prompt ("something cool") got
  `detail` archetype via Haiku fallback + enforced structural floor;
  VLM scored 7 vs 4 on A1. Demonstrates A2's value on under-specified
  prompts WHEN the classifier routes well.
- **Zero plan-diff retries fired** across 11 successful runs — the
  fills are either clean or catastrophically empty (paywall). No
  "halfway valid" fill that retry could rescue.

## Decision

**Ship A1 (00g) as v0.1.5** with `DD_ENABLE_PLAN_THEN_FILL` staying
off by default. A2 as implemented is net-negative on the 12-prompt
canonical gate.

Keep the code. The architecture is correct; the prompt engineering
isn't there. Revisit for v0.2 with:
- **Longer fill budget** (4096+ tokens) when plan is large, OR
- **Split-fill strategy** for big skeletons (fill one top-level
  region at a time, concat outputs), OR
- **Plan-diff slackening**: only check top-level type coverage, not
  child counts — A1-style archetype injection already enforced child
  floors; A2's plan-diff is redundant + over-strict.

## Rollback

Already rolled back by default — flag off. A1 path is unchanged.

## Artefacts

- 11 successfully-rendered prompts with screenshots + walks
- 1 plan-invalid prompt (05-paywall) with plan.json but no script
- `sanity_report.{json,md}` — 4 ok / 7 partial / 0 broken combined
  (the VLM-broken 4 are dragged to "broken" combined through either
  rule or VLM; 05-paywall missing because no screenshot)
- `run_summary.json` — per-prompt stage latencies + counts
- `activity.log` — timestamped trace
