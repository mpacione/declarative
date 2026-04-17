# Continuation — v0.1.5 bridge-dependent finish line

> Paste this into a fresh Claude Code session once the Figma bridge
> is connected. Short session: run render + walk + VLM gate, make
> the ship/continue decision.

## State handed over

18 commits on `main` (all green). v0.1.5 Week 1 Commits A–E shipped
(commits `a4ef55f` → `cfd753d` → `0be0030` → `22ce53c` → `d23a743`,
stacked on top of the ADR-008 13-commit base + the `3796058` side-fix).

Full chain in `memory/project_adr008_status.md`.

**What's live in the compose pipeline:**
- 12 hand-authored archetype skeletons in `dd/archetype_library/`
- Keyword-first → Haiku classifier at `dd/composition/archetype_classifier.py`
- SYSTEM_PROMPT injection at `dd/composition/archetype_injection.py`
- Wired into `prompt_to_figma` (dd/prompt_parser.py) — no caller changes
- Feature flag `DD_DISABLE_ARCHETYPE_LIBRARY=1` for rollback
- Structural-density metric in `inspect_walk` + `sanity_report.md`

**What's already verified:**
- 1,888 unit tests pass
- 204/204 round-trip parity preserved (renderer untouched)
- Partial 00g on all 12 canonical prompts: 9 archetype-matched, 0
  refusals, +42 nodes (+16%) structural-density uplift vs 00f
- Biggest per-prompt wins: feed +10, paywall +9, dashboard +6,
  round-trip-test +29

**What's NOT verified (needs bridge):**
- Visual plausibility via Gemini VLM on rendered screenshots
- Whether the structural uplift translates into ≥7 VLM-ok (plan §5
  stopping criterion)

## Your job

1. Verify the bridge is connected (see below).
2. Run the render + walk + screenshot + VLM pipeline on the
   partial-run artefacts already at `experiments/00g-mode3-v4/`.
3. Compute rule + VLM sanity-gate verdict.
4. Apply the plan §5 stopping criterion.
5. Commit the tail of 00g + update the memo.
6. (Conditional) proceed to Week 2 Step 6 (A2 plan-then-fill) if gate
   misses, or wrap v0.1.5 if gate passes.

## Pre-flight

```bash
cd /Users/mattpacione/declarative-build
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

# 1. Bridge check — port 9231 open
python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1', 9231)); print('bridge OK'); s.close()"

# 2. Identity check — assert connected to the Dank file we think we are
node render_test/walk_ref.js --help 2>&1 | head -3 || echo "node available"

# 3. Parity baseline (quick — ~30s with --skip-existing)
python3 render_batch/sweep.py --port 9231 --skip-existing 2>&1 | tail -5
```

If bridge is down → ask the user to restart the Figma plugin pointed at
Dank (Experimental). Do NOT run any render commands until the port is
open.

## Step 1 — extend 00g runner to include render/walk

The existing `experiments/00g-mode3-v4/run_parse_compose.py` does the
Haiku stages only. For the full pipeline, mirror 00f's pattern:

Option A — **extend the existing driver** by adding render + walk
subprocess calls like 00f does (see
`experiments/00f-mode3-v3/run_experiment.py:207-328`). Copy those two
stage blocks verbatim and point them at the existing artefacts.

Option B — **write a sibling `run_render_walk.py`** that reads
each `artefacts/NN-slug/ir.json` + synthesizes the `script.js`
(via `dd.compose.generate_from_prompt`), then runs `node render_test/run.js`
+ `node render_test/walk_ref.js` against the bridge.

Option B is cleaner because the Haiku artefacts are already on disk
and re-running parse wastes ~$0.05. Use Option B.

Key invariants to preserve:
- port 9231 (matches 00f)
- same subprocess patterns (run_node_cmd) for timeout + stderr capture
- write render_result.json + walk.json + rendered_node_id.txt per prompt
- on render failure, write FAILURE.md with stderr tail (matching 00f)

## Step 2 — screenshot + VLM inspection

```bash
# Build a screenshot manifest from the successful walks
python3 -c "
import json
from pathlib import Path
manifest = []
for d in sorted(Path('experiments/00g-mode3-v4/artefacts').iterdir()):
    rn = d / 'rendered_node_id.txt'
    if rn.exists():
        node_id = rn.read_text().strip()
        manifest.append({
            'slug': d.name,
            'node_id': node_id,
            'out': str(d / 'screenshot.png'),
        })
Path('experiments/00g-mode3-v4/screenshot_manifest.json').write_text(
    json.dumps(manifest, indent=2)
)
print(f'manifest: {len(manifest)} entries')
"

# Capture via the node batch capturer
node render_test/batch_screenshot.js \
  experiments/00g-mode3-v4/screenshot_manifest.json 9231

# Run sanity gate (rule + VLM)
python3 -m dd inspect-experiment experiments/00g-mode3-v4 --vlm
```

Expected VLM cost: ~$0.20 for 12 screenshots via Gemini 3.1 Pro.

## Step 3 — apply the §5 stopping criterion

Read `experiments/00g-mode3-v4/sanity_report.json` and compute:

| metric | 00f | 00g | plan prediction |
|---|---|---|---|
| rule gate | 6 / 5 / 1 PASSES | ? | 4/5/3 PASSES or better |
| VLM-ok | 4 / 12 | ? | 7-8 / 12 (A1 alone) |
| VLM-partial | 5 / 12 | ? | 3-4 / 12 |
| VLM-broken | 3 / 12 (+1 timeout) | ? | 1 / 12 |
| Mode-1 calls | 63 | ? | 70-80 |

**Decision rule:**
- ≥7 VLM-ok AND structural-density mean ≥ 00f + 1 std-dev → **ship v0.1.5**. Skip A2.
- <7 VLM-ok → proceed to Week 2 Step 6 (plan-then-fill behind `DD_ENABLE_PLAN_THEN_FILL`).
- Unexpected regression (VLM-ok drops below 00f's 4/12) → investigate. The archetype injection should be rollback-safe via `DD_DISABLE_ARCHETYPE_LIBRARY=1`; rerun with the flag to isolate.

## Step 4 — commit the tail

Commit boundary matches the v0.1.5 plan's "Commit E" but with full
pipeline artefacts this time:

```
feat(experiments/00g-mode3-v4): full pipeline + VLM gate (ADR-008 v0.1.5 E tail)

- render + walk + screenshot + VLM results for all 12 canonical prompts
- sanity_report.{json,md} with per-prompt rule + VLM verdict
- memo.md updated with vs-00f comparison + §5 stopping decision
```

Append the result to `memory/project_adr008_status.md` (new line item
in the "v0.1.5 Week 1" section) and update the index entry in
`memory/MEMORY.md`.

## Guardrails (reiterated)

- **204/204 round-trip parity is load-bearing** — re-verify after
  render/walk changes. Any regression blocks the ship decision.
- **Unit test count: 1,888** — new tests welcome; don't delete.
- **Don't build the critic loop** — GameUIAgent's r=-0.96 ceiling
  finding gates it on ≥8/12 VLM-ok. Even a full-pass on A1 alone
  doesn't cross that threshold.
- **Don't upgrade the rubric mid-sprint** — 5-dim graduation is v0.2
  pending calibration data.
- **Don't ship rarity-enhancement post-pass unless 00g misses the
  gate.** The matrix showed container coverage is baseline-limited;
  adding a post-pass without evidence risks regression.

## If time remains after the gate

**If gate passes (≥7 VLM-ok):**
- Run Week 2 Step 7 — DIY human calibration on the 48 existing
  screenshots (00c/00d/00e/00f). Matt rates 0-5 on Layout /
  Completeness / Readability; compute Spearman ρ vs Gemini's 1-10.
  Deliverable: `docs/research/calibration-48.md`.
- Run Week 2 Step 8 — shadow 5-dim rubric prompt added to
  `dd/visual_inspect.py` emitting the GameUIAgent 5-dim vector
  alongside the current 1-10. Gate still uses 1-10 through v0.1.5;
  the shadow lets v0.2 graduate with data.

**If gate misses (<7 VLM-ok):**
- Week 2 Step 6 — plan-then-fill behind `DD_ENABLE_PLAN_THEN_FILL`.
  Full spec in `docs/research/v0.1.5-plan.md` §Week 2. Two-stage
  Haiku: plan call returns a pruned IR tree `{type, id, count_hint}`,
  fill call takes the pinned plan + writes leaves. Plan-diff retry on
  drift. New `KIND_PLAN_INVALID` on `dd/boundary.py`. Flag off by
  default.

## Useful one-liners

```bash
# Unit tests
python3 -m pytest tests/ -q --ignore=tests/test_child_composition.py \
  --ignore=tests/test_semantic_tree_integration.py \
  --ignore=tests/test_prompt_parser_integration.py \
  --ignore=tests/test_phase4b_integration.py \
  --ignore=tests/test_rebind_integration.py \
  --ignore=tests/test_screen_patterns_integration.py -m "not integration"

# Round-trip parity
python3 render_batch/sweep.py --port 9231 --skip-existing

# Try a single archetype-routing prompt manually
python3 -c "
from dd.composition.archetype_classifier import classify_archetype
print(classify_archetype('a login screen', client=None))  # 'login'
print(classify_archetype('something cool', client=None))  # None
"

# Inspect 00g artefacts quickly
ls experiments/00g-mode3-v4/artefacts/
cat experiments/00g-mode3-v4/memo.md
```

## Expected session length

~30-60 minutes of wall clock. Most of it is the VLM sanity gate
(Gemini latency, not CPU).

Predicted outcome per plan §5: **4 → 7-8 VLM-ok on A1 alone**.

## Handoff

When you finish, update the continuation doc in place — either
mark v0.1.5 as shipped with the final metrics, or write a Week 2
continuation if A2 is needed.
