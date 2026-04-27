# Performance + cost budget

**Status**: ACTIVE. Created 2026-04-21 at Tier C.4 of
`docs/plan-burndown.md`. Baseline numbers from a single Haiku-+
Dank-corpus measurement; each tier adds a new row with observed
numbers so regressions are detectable.

---

## Baseline (measured 2026-04-21, Haiku 4.5, Dank DB)

Single component-scale synthesis: "a primary CTA button labeled
'Get started'".

| Stage | Latency (s) | Cost (est) | Notes |
|---|---|---|---|
| `parse_prompt` (Claude Haiku) | 0.8 | ~$0.002 | 1x LLM call, ~2k tokens I/O |
| `generate_from_prompt` (compose + render, in-process) | ~0.01 | $0 | Pure Python + one sqlite query. Sub-second on a component-scale prompt. |
| `walk_rendered_via_bridge` (Figma plugin) | 2–170 | $0 | Highly variable (environmental). Fresh plugin: ~2s. Loaded plugin: up to 170s timeout per `feedback_sweep_transient_timeouts.md`. |
| VLM rubric (Gemini, optional) | 5–30 | ~$0.01 | 30% transient error rate per `feedback_vlm_transient_retries.md`; retry 2-3× to stabilise. |
| **Total critical path** | **3-180s** | **~$0.01** | Bridge is the dominant variable. |

Per-synthesis cost estimate (including one VLM pass): **$0.01–$0.02**
(~2/3 LLM compose, 1/3 VLM score). Mostly Haiku; Gemini is the
small fraction.

## Budgets per tier

Each tier should confirm these budgets hold at its scope. Exceeding
any row is a signal to stop and optimize before more work lands.

### Tier D — multi-prompt composition (D.2 / D.3 / D.4)

- **Per synthesis**: target ≤ 5 s wall clock + ≤ $0.03 (prompt
  parse + compose + render + score). 5 s is a soft cap; bridge
  walks over 60 s are environmental — retry once through a fresh
  plugin state.
- **Per session** (5 demo prompts): ≤ 30 s + ≤ $0.20.
- **Per regression run** (10 canonical prompts via CI): ≤ 2 min +
  ≤ $0.30.

### Tier E — forces labeling at scale

- 500 rows × batch=10 = 50 Haiku calls.
- Observed: ~$0.02 for 20 rows → ~$0.50 for 500 rows. Budget
  $1.

### Patterns sweep (Tier C.5)

- Sweep with `min_screens=2`. Prior run (`min_screens=3`) yielded
  13 candidates / 13 Haiku calls / ~$0.01 / ~15 s. Lowering threshold
  to 2 likely pulls 50–80 candidates. Budget $0.10 / 2 min.

### Shadcn cold-start (Tier E.3)

- One-time extraction of ~60 shadcn components. Each needs
  classification + slot inference. Estimate 1× pass at ~$2–3.
  Budget $5 + 10 min.

## Known performance hazards

### Bridge timeout (170s PROXY_EXECUTE)

Hardcoded in `render_test/walk_ref.js`. Per
`feedback_sweep_transient_timeouts.md`: iPad-sized screens under
cumulative plugin load hit this; individual retries through the
same bridge walk in 2 seconds. Plan fix: parameterise the timeout
via env (`BRIDGE_TIMEOUT_MS`) so CI can bump it, and add a
standard "wait + retry once" wrapper. Deferred to Tier E.5.

### VLM transient rate (30%)

Gemini 3.1 Pro exhibits ~30% transient error rate on 12-prompt
batches per `feedback_vlm_transient_retries.md`. Built-in 2×
retry insufficient; rerun the whole gate 2–3× to stabilise. For
Tier D gating, that means: VLM score only gates after 2+ agreeing
runs, or the score counts as "indeterminate" and the synthesis
passes on structural dimensions alone.

### Multiple-LLM path compounding cost

Tier D.3 archetype-driven screen compose = 1× archetype classifier
(Haiku) + 1× slot-fill prompt (Haiku) + 1× render + 1× bridge walk
+ 1× VLM score. Budget $0.05 / synthesis. Batch of 10 prompts
budget $0.60.

## Measurement protocol

When a tier ships:

1. Run a representative prompt 3× back-to-back. Record min/median/
   max latency + total cost.
2. Append a row to the "Measured" table below.
3. If any row exceeds the budget by 2×, stop and optimize.

## Measured

| Tier | Date | Prompt(s) | Latency min/med/max | Cost | Notes |
|---|---|---|---|---|---|
| B baseline | 2026-04-21 | 3 component-scale | 0.8s parse + bridge | ~$0.02 | bridge 2-3s fresh |
| C.3 force-resolution | 2026-04-21 | 2 prompts (destructive / CTA) | ~2 × 0.8s + render | ~$0.005 | compose < 10ms |

---

*Keep this doc honest. If a tier lands without updating the
Measured table, the perf claim is self-reported and unvalidated.*
