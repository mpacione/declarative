# Continuation — v0.1.5 Week 2: A2 plan-then-fill

> Supersedes `docs/continuation-v0.1.5-bridge.md` (Week 1 finish line).
> Week 1 is done; A1 landed at 6/12 VLM-ok, short of the ≥7 ship gate.
> Plan §5 routes to A2 plan-then-fill.

## State summary

21 commits on `main`. Full chain in `memory/project_adr008_status.md`.

**Live in production:**
- 12 archetype skeletons in `dd/archetype_library/`
- Classifier + injection wired into `prompt_to_figma`
- Structural-density metric in `RuleBasedScore`
- `DD_DISABLE_ARCHETYPE_LIBRARY=1` flips A1 off

**Verified metrics (00g full pipeline):**
- VLM-ok: 4 (00f) → 6 (00g), +50 %
- Mean nodes: 21.8 → 25.2, ≈ +1.02 σ over 00f baseline
- Round-trip parity: 204 / 204 preserved
- 1,888 unit tests green

**Gaps we still need to close:**
- 04-dashboard regressed from partial(5) to broken(3) — tables render
  as text stacks; **not an archetype problem**, render-template work
  needed independent of A2.
- 11-vague regressed from ok(8) to partial(4) — classifier=None +
  T=0.3 is more conservative than 00f's T=1.0 luck. Vague prompts are
  inherently high-variance; may not be closable without multi-sample.

## Week 2 Step 6 — plan-then-fill (A2)

Full spec at `docs/research/v0.1.5-plan.md` §Week 2. TL;DR:

1. **New module** `dd/composition/plan.py`:
   - Plan LLM (Haiku, JSON-mode): produces a pruned IR tree
     `{type, id, count_hint, children: [...]}`. Deterministic structure,
     no props/text. Roughly one level of nesting above what our IR
     carries.
   - Validator: reuses `dd.composition.slots.validate_slot_child` +
     capability gate to reject invalid plans before fill.
   - Fill LLM (Haiku): takes the validated plan pinned in context,
     writes leaf text / icons / variants. Identical output shape to
     today's `parse_prompt` so compose pipeline is unchanged.
   - Plan-diff post-hoc: if fill dropped a planned node, retry once
     with the pinned plan restated. On second failure emit
     `KIND_PLAN_INVALID`.
2. **Boundary extension** at `dd/boundary.py`: add
   `KIND_PLAN_INVALID` to the `KIND_*` constants. Surfaces through
   the unified __errors channel per ADR-007.
3. **Wire into `prompt_to_figma`** behind `DD_ENABLE_PLAN_THEN_FILL=1`:
   - Flag off → current A1-live behaviour (ship default).
   - Flag on → classify archetype → build plan → validate → fill.
   - Archetype skeleton still injected into the PLAN prompt for
     structure; fill prompt doesn't need it (plan pins structure).
4. **Unit tests** (`tests/test_plan_then_fill.py`):
   - Plan-shape validation (types in catalog, count_hint ≥ 1, etc.)
   - Plan-diff detection (fill drops a planned id → retry fires)
   - Fill producing valid component list given a plan
   - End-to-end mock of parse_prompt via plan+fill for the 12 prompts
5. **00h experiment** (`experiments/00h-mode3-v5/`):
   - Mirror 00g structure: `run_parse_compose.py` calls plan+fill,
     `run_render_walk.py` unchanged.
   - Compare vs 00g by VLM-ok, structural density, plan-diff retry
     rate, and `KIND_PLAN_INVALID` incidence.

## Step 6 TDD order (matches Week 1 discipline)

1. **Red/Green**: plan-shape validator (pure, offline).
2. **Red/Green**: plan-diff detector (pure, input: plan + fill output).
3. **Red/Green**: mock-LLM plan+fill orchestrator (no real API).
4. **Smoke**: single-prompt live A2 run (login or settings).
5. **Full**: 12-prompt 00h end-to-end with VLM gate.
6. **Commit boundaries**:
   - F — `dd/composition/plan.py` + tests
   - G — boundary `KIND_PLAN_INVALID` + wiring into `prompt_to_figma`
   - H — `experiments/00h-mode3-v5/` driver + artefacts + memo

## Budget

- **Plan call**: ~500 output tokens @ T=0.0 = ~$0.0025 each
- **Fill call**: ~700 output tokens @ T=0.3 = ~$0.0035 each
- **Retry rate estimate**: 5-15 % of prompts hit plan-diff retry
- Per prompt: ~$0.006 (2× the current A1 cost)
- 00h full run: 12 × 2 calls = ~$0.08
- Plus VLM: ~$0.20
- **Total 00h budget: ~$0.30**

Wall-clock: ~60 s parse (vs ~30 s for A1) + 10 s render + 30 s VLM = ~100 s.

## Expected outcome

Plan §5 prediction with A1+A2: 9-10 VLM-ok, ≥ 1 broken. Hitting 9+ VLM-ok
→ ship v0.1.5 with A2 on by default. Below 8 → revisit render-template
gap for dashboard, reconsider sprint scope.

## Guardrails (same as Week 1)

- TDD every new module
- Unit tests must stay 1,888+ green throughout
- Round-trip parity: 204/204 preserved after every commit
- A2 is flag-off by default until 00h confirms uplift
- Don't rebuild the rule-based gate; don't introduce a second critic
- `KIND_PLAN_INVALID` flows through existing channels; don't invent a
  parallel error surface

## Parallel-track options (Steps 7 + 8)

Step 7 — **DIY human calibration** (1 h). Rate the 48 existing
screenshots (00c/d/e/f) on Layout / Completeness / Readability 0-5.
Compute Spearman ρ vs Gemini's 1-10. Deliverable:
`docs/research/calibration-48.md`. Decides the v0.2 rubric graduation.

Step 8 — **Shadow 5-dim rubric** (2 h). Opt-in second prompt in
`dd/visual_inspect.py` emitting GameUIAgent's 5-dim vector alongside
1-10. Gate stays on 1-10; shadow collects data.

Neither blocks Step 6. Run whichever has time.

## One-liners

```bash
# Sanity check current state
source .venv/bin/activate
python3 -m pytest tests/ -q --ignore=tests/test_child_composition.py \
  --ignore=tests/test_semantic_tree_integration.py \
  --ignore=tests/test_prompt_parser_integration.py \
  --ignore=tests/test_phase4b_integration.py \
  --ignore=tests/test_rebind_integration.py \
  --ignore=tests/test_screen_patterns_integration.py -m "not integration"

# Parity
python3 render_batch/sweep.py --port 9231 --skip-existing

# Flip to A1-only verification (should match 00g baseline)
export DD_ENABLE_PLAN_THEN_FILL=0
PYTHONPATH=$(pwd) python3 experiments/00g-mode3-v4/run_parse_compose.py

# A2 live (after Step 6 lands)
export DD_ENABLE_PLAN_THEN_FILL=1
PYTHONPATH=$(pwd) python3 experiments/00h-mode3-v5/run_parse_compose.py
```

## Handoff

When 00h lands: update `memory/project_adr008_status.md` with the
commit chain + final gate metrics, supersede this doc with a
v0.2-scope continuation (or close out v0.1.5 if shipping).
