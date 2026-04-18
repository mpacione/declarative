# Continuation — v0.1.5 implementation

> Paste this into a fresh Claude Code session. Read it top-to-bottom
> before touching code. It captures the full state of the sprint so
> the next session picks up without re-deriving.

## Orient (30-second version)

ADR-008 Mode-3 composition shipped. 13 commits, all on `main`,
chain described in `memory/project_adr008_status.md`. Sanity gate
passes on Dank's 12 canonical prompts (6 broken / 5 partial / 1 ok
rule-based, 4 VLM-ok + 5 partial + 3 broken + 1 API timeout). 63
Mode-1 `createInstance()` calls. 204/204 round-trip parity preserved.
1,765 unit tests pass.

Three research streams (α/β/γ) landed and converged on a **v0.1.5
plan** at `docs/research/v0.1.5-plan.md`. That plan is binding —
the user signed off on (sequence OK, corpus-mine archetypes,
matrix-before-A1) and asked you to keep moving.

Your job is to execute week 1 of that plan, then week 2 if time
remains. Don't re-derive; the ADR, contracts, and research are all
committed.

## State of the repo

Most recent commits (most recent first):

```
3796058  feat(prompt_parser): clarification-refusal detection + temperature=0.3 default
          (v0.1.5 Week 1 side-fix)
---     research: v0.1.5 plan converged from three parallel streams
          (α/β/γ memos + converged plan; no code changes)
d417591  feat(composition+visual_inspect): drawer fills screen + VLM retry on transient
8234388  feat(composition): Mode-3 v3 — 11 backbone templates + text-foreground palette
2cfec07  feat(mode3): v2 — typography splits + Mode-1 CKR lookup + threshold calibration
ad95c3d  feat(compose+renderer): PR #1 Part C — auto-layout + template-to-parent + fill overlay
c85a2cc  feat(cli): dd induce-variants + CATALOG_ENTRIES fallback
40b5eb4  feat(prompt): surface CKR to LLM + container-semantics hints
e8c97b0  feat(composition): PR #1 part B — providers + inducer + compose integration
163422b  feat(composition): PR #1 part A — core modules (ADR-008)
b596eb0  feat(catalog): PR #0 — catalog ontology v2 (ADR-008 precursor)
66c5090  research: Mode 3 composition trilayer + ADR-008 + contract tests
ba3561e  feat: auto-inspect gate + deep diagnosis of Mode 3 gap
```

Environment:
- `.env` has `ANTHROPIC_API_KEY`, `FIGMA_ACCESS_TOKEN`, `GOOGLE_API_KEY` — all verified.
- Figma Desktop bridge on port 9231 connected to "Dank (Experimental)". Output page is "Generated Test".
- Python 3.11+ in `.venv`, Node 18+ in `node_modules/`.
- `Dank-EXP-02.declarative.db` has migrations 011 + 012 applied; 212 placeholder `variant_token_binding` rows.

Test state:
- 1,765 unit tests passing.
- 46/46 `tests/test_mode3_contract.py` green.
- 204/204 round-trip parity on Dank, re-verified three times post-ADR-008.

## What shipped most recently (commit `3796058`)

1. `dd/prompt_parser.py::extract_json` — returns `{"_clarification_refusal": <prose>}` when LLM emits ≥100 chars of non-JSON prose. Restores the `KIND_PROMPT_UNDERSPECIFIED` signal the pipeline was silently swallowing.
2. `parse_prompt` — new `temperature` kwarg; production default set to `_COMPOSE_TEMPERATURE = 0.3` (awaiting Stream-β matrix confirmation).
3. `prompt_to_figma` — detects the clarification-refusal dict and returns `{clarification_refusal, structure_script: None, ...}` instead of rendering a blank frame.
4. Tests: `test_long_prose_returns_clarification_refusal` + `test_short_noise_still_returns_empty`.

## Week 1 — what you do next (in order)

### Step 1 — Matrix runner (β's 240-call experiment)

**Goal:** empirically confirm S2 @ T=0.3 is the dominant cell before
embedding its contract in the archetype library.

**Spec** at `docs/research/generation-density-design.md` §3–6. Summary:

- **Dimensions**
  - T ∈ {0.0, 0.5, 1.0}
  - S ∈ {S0 current, S1 plan-first, S2 min-count + clarify-as-empty, S3 few-shot rich, S4 minimal}
- **Prompts** — the 12 at `experiments/00c-vanilla-v3/artefacts/NN-slug/prompt.txt`
- **Samples** — 1 per cell × 15 cells × 12 prompts = 180, plus a variance slice (T=1.0, S0, 12 prompts × 5 samples = 60) → 240 total Haiku calls
- **Measures** (structural only, VLM deferred):
  1. Total node count
  2. Top-level count
  3. Max depth
  4. Container-emission score (0-6, sum over `list, button_group, pagination, toggle_group, header, table`)
  5. `component_key` rate
  6. `variant` declaration rate
  7. JSON-validity (0/1) + English-explanation detection
  8. Empty-output rate
- **Budget:** ~$0.70 Haiku + optional $0.96 VLM confirmation. ~5 min parallel
- **Stopping:** a contract variant scoring ≥ 1 std-dev above S0 on ≥ 3 of 5 measures, with empty-output-rate ≤ S0, on ≥ 9 of 12 prompts. Ship that (T, S).

**Where to build it:** new `experiments/00g-matrix/` directory. Script: `run_matrix.py`. Output: `matrix_results.json`
with per-cell measures. Produce a `memo.md` with the 3×5 heatmap per measure.

**Gotchas:**
- Respect the clarification-refusal dict return from `extract_json` — a cell that returns a dict is NOT an empty-output-rate hit, it's a "structured refusal" that should be counted separately.
- Use the structural measures from the memo verbatim — don't invent new ones mid-run.

### Step 2 — Corpus-mine the archetype skeletons

**Goal:** extract 8-12 canonical skeletons from the 204 Dank app_screens.

**Approach:**

1. **Extend `dd/screen_patterns.py`** from shallow signatures (root-type
   Counter) to deep signatures. Candidate signature: `(root_type,
   sorted_slot_populations, max_depth)` where `slot_populations` is a
   tuple of `(slot_name, child_count_bucket)` derived from each
   screen's `screen_component_instances` + slot definitions in
   `dd/catalog.py`.
2. **Cluster screens** by signature. Use `Counter.most_common(30)` to
   get the top patterns; manually review to pick 8-12 clusters that
   have enough diversity to be useful.
3. **Extract the modal skeleton** per cluster: pick the cluster's
   representative screen, walk its IR (via `generate_ir` from
   `dd/ir.py`), prune concrete props/colours/text — keep only
   `{type, variant?, children}`. Save as
   `dd/archetype_library/<name>.json`.
4. **Name each archetype** from the Mobbin-style taxonomy
   (feed / dashboard / paywall / login / settings / search /
   onboarding-carousel / chat / empty-state / profile / checkout /
   detail). Map Dank clusters to these names by slot composition.
5. **Dank coverage check:** if Dank's screens only cover 4-5 named
   archetypes (likely — it's a single wallet/finance app), backfill
   the remaining names with hand-authored skeletons based on the 12
   canonical prompts. Be honest about which ones are corpus-derived
   vs hand-authored in the file's metadata.

**Tests:** `tests/test_archetype_mining.py` asserting:
- `mine_archetypes(conn)` returns ≥ 5 clusters for Dank DB
- Each skeleton is valid per the catalog (types + slots exist)
- Skeletons have depth ≥ 2 (not just root-level lists)

### Step 3 — `ArchetypeLibraryProvider` + classifier + SYSTEM_PROMPT injection

**Goal:** wire the skeletons into the Mode-3 provider chain so the LLM sees
them as few-shot inspiration for the matched archetype.

**Scope:**

1. **New provider** at `dd/composition/providers/archetype_library.py` —
   priority 75 (above universal 10, below project CKR 100).
   - `supports(catalog_type, variant)`: True for `screen` + any
     archetype-name variant ("login", "dashboard", etc.).
   - `resolve(...)`: returns a `PresentationTemplate` whose structure
     field contains the full skeleton JSON.
   - Register in `build_registry_from_env` after universal.
2. **Classifier** at `dd/composition/archetype_classifier.py`:
   literal-keyword map → Haiku 4.5 classification fallback →
   top-1 (stretch: top-2 as multi-shot). Keyword map built from
   the archetype names + obvious aliases ("feed" → "feed", "meme
   feed" → "feed", "dashboard" → "dashboard", etc.).
3. **SYSTEM_PROMPT injection** in `dd/prompt_parser.py::prompt_to_figma`:
   classify → select skeleton(s) → prepend to SYSTEM_PROMPT with
   framing: "Here's a canonical skeleton for a <archetype> — use as
   inspiration, modify for the prompt. Do not copy verbatim."
4. **Rarity-enhancement post-pass** in `dd/compose.py`: walk the
   compose_screen output; for each container type (list, button_group,
   pagination, toggle_group, table, tabs, menu) that has < N children
   per the archetype's skeleton metadata, pad from the skeleton's
   default children.
5. **Feature flag** `DD_DISABLE_ARCHETYPE_LIBRARY=1` falls back to
   v0.1 behaviour (SYSTEM_PROMPT without skeleton injection, provider
   registry without archetype tier).
6. **Tests** `tests/test_archetype_library.py` — provider supports
   the 12 archetypes, classifier routes on fixtures, SYSTEM_PROMPT
   contains the injected skeleton for a matched prompt.

### Step 4 — Structural-density metric

**Goal:** cheap observability independent of VLM judgement.

**Scope:**

1. Extend `dd/visual_inspect.py::inspect_walk` to also compute
   `max_depth` and `container_coverage` (sum over
   `list, button_group, pagination, header, table, tabs, menu` whose
   walked subtree has ≥ 1 child) alongside existing metrics.
2. Store in `RuleBasedScore` dataclass + `to_dict()`.
3. Surface in `sanity_report.md` memo output.
4. Tests: extend `tests/test_visual_inspect.py` to cover the new fields.

### Step 5 — 00g experiment

Fresh end-to-end run on the 12 canonical prompts with archetype
library live + matrix-confirmed contract + structural-density
metric. Structure mirrors 00f (`experiments/00f-mode3-v3/`):

1. `experiments/00g-mode3-v4/run_experiment.py` — copy 00f's driver.
2. Run pipeline: parse (Haiku @ T=matrix-winner) → compose (with
   archetype classifier) → render (bridge) → walk → screenshot →
   sanity gate (rule + VLM).
3. `memo.md` comparing 00f → 00g across:
   - VLM-ok / partial / broken counts
   - Structural density (nodes, max_depth, container_coverage)
   - Mode-1 calls + archetype-matched count
   - Individual per-prompt delta
4. Commit.

**Expected outcome** per the plan: 4 → 7-8 VLM-ok on A1 alone.

### Step 6 — Commit + update memory

Commit boundaries:
- **Commit A**: matrix infrastructure + results + memo
- **Commit B**: corpus mining + skeletons (data-only)
- **Commit C**: ArchetypeLibraryProvider + classifier + SYSTEM_PROMPT + rarity post-pass
- **Commit D**: structural-density metric
- **Commit E**: 00g experiment artefacts + memo

Update `memory/project_adr008_status.md` + `memory/MEMORY.md` with
the 00g result.

## Week 2 — plan-then-fill + calibration (stretch, if Week 1 landed cleanly)

Full spec at `docs/research/v0.1.5-plan.md` §Week 2. Summary:

### Step 7 — Plan-then-fill (A2) behind `DD_ENABLE_PLAN_THEN_FILL`

- `dd/composition/plan.py` — two prompt templates + JSON-mode Claude calls
- Plan LLM returns `{type, id, children: [{type, id, count_hint}]}` pruned tree
- Skeleton-grammar validator reusing `dd.composition.slots.validate_slot_child`
- Fill LLM takes pinned plan; fills leaf text/icons/variants
- Plan-diff post-hoc: any dropped nodes → single retry with pinned plan
- New `KIND_PLAN_INVALID` on `dd/boundary.py`
- Flag off by default; turn on for 00h experiment
- Measure additional uplift over A1

### Step 8 — DIY human calibration

- Matt rates each of 48 existing PNG screenshots (00c/d/e/f artefacts) 0-5 on Layout / Completeness / Readability
- Compute Spearman ρ vs Gemini's 1-10 scores
- Deliverable: `docs/research/calibration-48.md` with the correlation + recommendation on 5-dim graduation in v0.2

### Step 9 — Shadow 5-dim rubric prompt

- `dd/visual_inspect.py` gets an opt-in second prompt emitting the GameUIAgent 5-dim vector alongside 1-10
- Store both in sanity_report.json
- Gate still uses 1-10 through v0.1.5
- Informs rubric graduation decision in v0.2

## Rules / invariants to preserve

- **204/204 round-trip parity.** Never regress. Re-verify via
  `render_batch/sweep.py --port 9231 --skip-existing` after any
  renderer or compose change.
- **1,765 unit tests passing.** Don't break existing tests; add new
  ones for new behaviour (TDD, per `~/.claude/CLAUDE.md`).
- **ADR-006 boundary contract symmetry.** Any new provider plugs in
  via `ComponentProvider` protocol; any new failure mode gets a
  `KIND_*` constant.
- **ADR-007 unified verification channel.** All new failure modes
  flow through the existing `__errors` channel.
- **Feature flags on new behaviour.** Every v0.1.5 change is
  rollback-safe via env var.

## Guardrails — things to NOT do

- **Don't upgrade the rubric mid-sprint.** γ recommended holding 1-10
  + calibration-in-parallel. Graduating to 5-dim is v0.2 work.
- **Don't build a second VLM critic.** Cross-VLM ICC=0.021 kills the
  value. One strict critic is sufficient through v0.1.5.
- **Don't build the RenderVerifier critic loop.** GameUIAgent's
  r=-0.96 quality-ceiling finding gates it on ≥8/12 VLM-ok.
- **Don't remove the rule-based gate.** 69% rule-vs-VLM disagreement
  reflects orthogonal measurement (nodes vs renders), not redundancy.
- **Don't invent new experiments.** Scope is 00g this sprint; 00h
  only if Week 1's 00g misses the ≥7 VLM-ok stopping criterion.

## Open questions flagged for the ADR-008 follow-on ADR

1. Archetype taxonomy source — corpus-mined (current choice) vs
   Mobbin-derived for the next iteration
2. Skeleton fidelity vs freedom — how strictly post-pass enforces the
   skeleton
3. Plan-schema shape for A2 — pruned subset of full IR vs separate schema
4. Classifier upgrade threshold — keyword + Haiku fallback works for
   12 prompts; embedding classifier when?
5. Rarity-enhancement aggressiveness — "empty list → 4 items" (safe) vs
   "dashboard with no chart → synthesise chart" (controversial)
6. Provider-chain ordering sanity — archetype 75 vs project CKR 100
   seems right; confirm doesn't cause regressions in projects with
   very deep CKRs
7. When does A1 invalidate the current SYSTEM_PROMPT container-hint
   section?

## If you finish Week 1 + 2 early

Work one of:

1. **v0.2 headliner — corpus retrieval (α's B).** Embed the 204 Dank screens
   + 48 v3 synthetic outputs; retrieve top-3 per prompt as additional
   few-shot. Builds on Week-1 archetype infrastructure.
2. **v0.2 headliner — 5-dim rubric graduation** gated on Week-2
   calibration data. If Spearman ρ > 0.7, implement the GameUIAgent
   5-dim scale with anchor paragraphs.
3. **v0.3 groundwork — critic-refine loop.** ONLY if 00g / 00h
   stopping criterion is met (≥8/12 VLM-ok). Otherwise don't.

## If you hit a blocker

- **Matrix returns flat (no dominant contract).** Ship A1 anyway — it's
  α-backed independent of β's matrix — and log the result for v0.2.
- **Dank corpus is too narrow for archetype mining.** Fall back to
  hand-authored skeletons for archetypes not represented. Document
  per-archetype provenance.
- **Classifier mis-routes.** Top-2 as multi-shot. If both misroute, add
  the specific prompt to a hand-authored mapping override.
- **Archetype overfit (LLM copies skeleton verbatim).** Retry with
  "diverge from the skeleton" instruction. Log as KIND_*.

## Useful commands

```bash
# Unit tests (should always stay green)
source .venv/bin/activate
python3 -m pytest tests/ -q --ignore=tests/test_child_composition.py \
  --ignore=tests/test_semantic_tree_integration.py \
  --ignore=tests/test_prompt_parser_integration.py \
  --ignore=tests/test_phase4b_integration.py \
  --ignore=tests/test_rebind_integration.py \
  --ignore=tests/test_screen_patterns_integration.py -m "not integration"

# Round-trip parity (~30s with --skip-existing)
python3 render_batch/sweep.py --port 9231 --skip-existing

# End-to-end synthesis + gate (the 00d/00e/00f pattern)
export $(grep -v '^#' .env | xargs)
PYTHONPATH=$(pwd) python3 experiments/00g-mode3-v4/run_experiment.py
PYTHONPATH=$(pwd) python3 experiments/00g-mode3-v4/run_walks_and_finalize.py
python3 -c "import json; from pathlib import Path; [...]  # build manifest"
node render_test/batch_screenshot.js experiments/00g-mode3-v4/screenshot_manifest.json 9231
python3 -m dd inspect-experiment experiments/00g-mode3-v4 --vlm
```

## Handoff note

Research is done, the plan is binding, the side-fix landed. The next
session's job is mechanical TDD execution: build the matrix runner,
mine the corpus, wire the provider, measure. Expected VLM-ok trajectory
is 4 → 7-8 on A1 alone; 8-10 with A2. Keep each change rollback-safe;
keep the suite green; keep the memory current.

Good luck.
