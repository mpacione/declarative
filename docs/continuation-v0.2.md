# Continuation — v0.2 entry point

> Supersedes `docs/continuation-v0.1.5-bridge.md` and
> `docs/continuation-v0.1.5-week2.md`. v0.1.5 is closed out; the ship
> state is A1 archetype-conditioned few-shot with 6/12 VLM-ok on the
> canonical gate (+50% vs 00f baseline).

## v0.1.5 ship state

**Default pipeline** — A1 archetype library live:
- Keyword-first classifier routes 9/12 canonical prompts
- Matched prompt's skeleton appended to SYSTEM_PROMPT as few-shot
- T=0.3 production composition temperature
- 204/204 round-trip parity preserved
- 1,912 unit tests green

**Flag-off** — A2 plan-then-fill:
- Full implementation at `dd/composition/plan.py`
- Regressed vs A1 on 12-prompt gate (6→4 VLM-ok, 1 KIND_PLAN_INVALID)
- `DD_ENABLE_PLAN_THEN_FILL=1` to re-enable

## v0.2 candidate scope

Prioritised by signal from the 00g / 00h runs:

### Tier 1 — close known regressions (render-template gap)

1. **04-dashboard "tables render as text stacks".**
   - VLM said "mostly unformatted text stacked vertically"
   - Table render template has no visual differentiation between
     column headers and row cells
   - Not an archetype problem (A1 AND A2 both regressed here)
   - Action: render-layer work — add table-row padding / separators
     at lowering time, inject a column-header variant
2. **10-onboarding-carousel "mostly empty with stray labels".**
   - Similar story: carousel slides render as stacked text without
     visual framing
   - Action: slide card template needs a visible border or bg

### Tier 2 — close A2's paywall regression

3. **05-paywall KIND_PLAN_INVALID on fill.**
   - Paywall plan has ≈30 nodes across 3 tiers + testimonial
   - Fill system_prompt carries the full plan verbatim → ~4k tokens
   - Haiku's fill returned `[]` twice (attention exhaustion?)
   - Action options:
     - Raise fill `max_tokens` from 2048 to 4096
     - Split fill per top-level region (fill each top-level node in
       a separate Haiku call, concat outputs)
     - Slacken plan-diff: only verify top-level type coverage, not
       repeated-template child counts

### Tier 3 — v0.2 headliners per v0.1.5-plan §4 deferred work

4. **Corpus retrieval (α's B).** Needs either SCI re-populated via
   classifier chain + ≥ 1k screens across projects, OR a second
   project. Current Dank SCI is 0 rows; v0.2 prerequisite.
5. **DIY human calibration** on 48 existing PNGs (00c/d/e/f + 00g).
   Matt rates 0-5 on Layout / Completeness / Readability; compute
   Spearman ρ vs Gemini's 1-10. Deliverable:
   `docs/research/calibration-48.md`. Informs 5-dim rubric graduation.
6. **Shadow 5-dim rubric** prompt in `dd/visual_inspect.py`. Gate
   stays on 1-10 until calibration data says otherwise.
7. **Classifier chain re-run** to populate `components` + `screen_
   component_instances`. Prerequisite for real corpus-mined
   archetypes (replacing the hand-authored placeholders) and for B.

### Tier 4 — A2 rework (if Tier 1 doesn't close the gate)

8. **A2 rework**: split-fill strategy. Split plan into top-level
   regions; for each region, run a dedicated fill call with only
   that region's plan in scope. Concat outputs. Addresses the
   paywall truncation + reduces the fill's attention budget per call.

### Explicit rejections (carried forward from v0.1.5)

- **Second VLM critic** — cross-VLM ICC = 0.021 per γ.
- **0-100 rating scale** — 0-5 > 0-10 > 0-100 for ICC.
- **Removing the rule-based gate** — orthogonal to VLM per γ's 69%
  disagreement finding.
- **Critic-refine loop** — gated on ≥ 8/12 VLM-ok baseline per
  GameUIAgent r=-0.96 ceiling; we're at 6/12.

## Useful state pointers

**Experiments to compare against:**
- `experiments/00f-mode3-v3/memo.md` — pre-v0.1.5 baseline (4 VLM-ok)
- `experiments/00g-mode3-v4/memo.md` — v0.1.5 ship state (6 VLM-ok)
- `experiments/00h-mode3-v5/memo.md` — A2 regression (4 VLM-ok + 1 invalid)
- `experiments/00g-matrix/memo.md` — 240-call matrix, no SYSTEM edit beats S0

**Memories worth re-reading before starting:**
- `feedback_proxy_execute_parse_depth.md` — the recurring bug pattern
- `feedback_vlm_transient_retries.md` — Gemini gate needs 2-3 reruns
- `feedback_auto_inspect_before_human_rate.md` — don't escalate to
  human rating without the gate
- `feedback_verifier_blind_to_visual_loss.md` — rule gate and VLM
  measure orthogonal things

**Commit chain (latest first):**
```
a7c6d92  00h A2 end-to-end (regression memo)
c703a0f  v0.1.5 F: plan-then-fill (A2) behind flag
3beedb8  docs: Week 1 epilogue + Week 2 continuation + learnings
897495b  v0.1.5 E (tail): full 00g pipeline + VLM gate
7f46518  docs: bridge-dependent continuation prompt
d23a743  v0.1.5 E (partial): 00g parse+compose baseline
22ce53c  v0.1.5 D: structural-density metric
0be0030  v0.1.5 C: classifier + injection
cfd753d  v0.1.5 B: 12 hand-authored skeletons
a4ef55f  v0.1.5 A: density matrix + analysis
```

## Session-kickoff checklist

```bash
cd /Users/mattpacione/declarative-build
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

# Sanity
python3 -m pytest tests/ -q --ignore=tests/test_child_composition.py \
  --ignore=tests/test_semantic_tree_integration.py \
  --ignore=tests/test_prompt_parser_integration.py \
  --ignore=tests/test_phase4b_integration.py \
  --ignore=tests/test_rebind_integration.py \
  --ignore=tests/test_screen_patterns_integration.py -m "not integration"

# Parity
python3 render_batch/sweep.py --port 9231 --skip-existing

# Confirm A2 flag is OFF (default)
unset DD_ENABLE_PLAN_THEN_FILL
```

## Pick a starting move

Default recommendation: **Tier 1, 04-dashboard render-template work.**
It's the biggest VLM-broken hold-out on 00g, and it's not a
generation problem — both A1 AND A2 produced reasonable structure
but both rendered as text stacks. Fix is in the render/template
layer. Expected to lift dashboard from broken(3) to partial or ok
and push the 12-prompt gate from 6 → 7 VLM-ok without touching the
prompt pipeline.
