# Continuation — post-April-cleanup handoff

**Session date:** 2026-04-21 (long session, single thread).
**End state:** tagged `cleanup-complete-2026-04-21`.
**Read first to ground:** `docs/research/scorer-calibration-and-som-fidelity.md`, this file, then the deferred-work list below.

## What landed in this session

A scorer correctness arc + a tidying arc, in that order.

### Scorer + Mode-3 (4 commits)

| commit | what |
|---|---|
| `978a6b5` | fix(scorer): visual-plausibility dims (`canvas_coverage` + `content_richness`) — caught Tier D scoring 10/10 on a visually-blank toast |
| `803c3e3` | feat(scorer): SoM-based component coverage (precision + recall) — replaces the noisy 1-10 Gemini rating |
| `890098a` | feat(scorer): variance measurement — VLM 1-10 is **2-25× noisier** than SoM coverage on every prompt |
| `249454f` | fix(compose): Mode-3 slot positions — text_input label-hoist (SoM surfaced this bug; archetype SoM-P 0.43→0.71, SoM-R 0.30→0.50) |

Net effect: the scorer is now honest. Tier D archetype (login) scores SoM-P 0.71, SoM-R 0.50, struct 5.0. The wireframe-placeholder confusion that prompted the original investigation was a transient bridge-load issue, not a real bug.

Memory notes added: `feedback_scorer_calibration_and_som_fidelity.md`, `feedback_slot_position_label_hoist.md`.

Doc landed: `docs/research/scorer-calibration-and-som-fidelity.md` — full lit review (16 papers), 6 decisions D1-D6, build plan, D5 measurement results, follow-up status. **Read this first** for scorer architecture context.

### April cleanup sweep (7 commits, PR-2 skipped)

| commit | what |
|---|---|
| `e9e6482` | PR-1 chore(gitignore): tmp/, render_batch artefacts, DB auto-backups, .claude/ + 3 stray markdowns committed |
| `3645e9d` | PR-3 refactor: `dd/m7_slots,m7_variants` → `dd/slots,variants` (drop m7_ from dd/) |
| `ffce73b` | PR-4 refactor(scripts): drop m7_ from all 35 scripts + 3 tests + 14 doc references |
| `7163d06` | PR-5 chore(docs): archive 6 zero-reference stale handoffs |
| `88c3356` | feat(sweep): per-screen retry on transient bridge failures (the wireframe-placeholder symptom) |
| `9fd2590` | PR-6 chore(docs): archive 9 cross-referenced docs + module-reference partial-update notice |

PR-2 (delete dead modules) was skipped — the audit was over-aggressive. All 5 candidates (`dd/markup.py`, `dd/maintenance.py`, `dd/extract_targeted.py`, `dd/curate_report.py`, `dd/extract_inventory.py`) have live production callers and need M6(b) deprecation coordination.

Memory notes added: `feedback_dank_corpus_drift_25.md` — explains the 179/204 round-trip number we now see.

### Three rollback tags

```
pre-cleanup-2026-04-21    ← rollback target (start of cleanup)
post-cleanup-2026-04-21   ← after PR-1..PR-5 (no retry)
cleanup-complete-2026-04-21 ← after PR-6 + retry (final)
```

`git reset --hard pre-cleanup-2026-04-21` undoes everything cleanup-related in one step.

## Current state at handoff

- **Tests**: 3146 passed, 37 known integration failures (pre-existing, DB-state-dependent), 6 skipped — same baseline as start.
- **Round-trip parity**: **179/204 PARITY** with retry layer enabled (87.7%). 25 persistent `missing_child` drifts (parity 0.95-0.98 mostly; one outlier at 0.66). All pre-existing from M5/M7 sprints, not caused by cleanup.
- **Generated Test page on Dank**: contains residue from late-session diagnostic renders. Cosmetic — gets cleared on the next render.
- **Generated Test page on Recon**: was clobbered earlier in session by mistaken renders against the wrong port. The file is recoverable; the user can delete the page if it bothers them.

## What's deferred (priority-ordered)

### High priority — known issues that block honest claims about the system

1. **25 persistent missing_child drifts** (`feedback_dank_corpus_drift_25.md`). The "204/204 round-trip parity" claim in older memory notes is now optimistic. Current state: 179/204. To investigate:
   - Pick screen 217 (typical case, 2 errors). Diff `render_batch/scripts/217.js` against `render_batch/walks/217.json`.
   - Identify the 2 missing children — what's the IR claiming + what actually rendered?
   - Bisect against M4 tag (`6377105`): `git checkout 6377105 && python3 render_batch/sweep.py --port <p> --limit 1 --since 217` — was screen 217 passing then?
   - Cluster: screens 217-226 are 10 consecutive iPad Pro 11" screens with identical 2-error pattern; one root cause likely.

2. **Module-reference body refresh** (`docs/module-reference.md`). Header has a partial-update notice listing M5-M7 + April-cleanup additions/renames, but the body still describes the M4-era pipeline. A dedicated documentation pass should rewrite it module-by-module; meanwhile readers should use `code-graph-mcp` or grep for current truth.

### Medium priority — cleanup completion that was deferred for risk reasons

3. **Script consolidation** — meaningful duplication remains:
   - `scripts/set_text_demo.py` + `set_color_demo.py` + `set_radius_demo.py` + `set_visibility_demo.py` (4 scripts, ~80% identical scaffold) → `scripts/edit_node_property.py` with `--property {text,color,radius,visibility}` flag
   - `scripts/tier_d_eval.py` + `tier_d_regate.py` + `tier_d_variance.py` (3 scripts, progressive instrumentation) → `scripts/eval_synthesis_quality.py` with `--mode {struct,vlm,variance}` flag
   - `scripts/bakeoff_som.py` merges into `scripts/vision_bakeoff.py` as `--include-som` flag
   - 11 one-off scripts (`bakeoff_gemini`, `dry_run_10`, `resume_three_source`, `som_adjudicate`, etc.) move to `scripts/archive/`
   
   Deferred because each merge requires writing new combined code that can introduce bugs in things that work today. Should be done in a focused TDD session.

4. **dd/* dead-code deletions** — the 5 candidates from the April-cleanup audit are real cleanup targets but each is entangled:
   - `dd/markup.py` (786 LOC vestigial pre-grammar serializer, gated by `DD_MARKUP_ROUNDTRIP=1` env probe in `dd/ir.py`) — tied to M6(b) gate per `docs/DEPRECATION.md`
   - `dd/maintenance.py` (live CLI feature `dd prune-extraction-runs`)
   - `dd/extract_targeted.py` (679 LOC own CLI: `python -m dd.extract_targeted --mode {properties,sizing,transforms,vector-geometry}`)
   - `dd/curate_report.py` (CLI-facing through curate)
   - `dd/extract_inventory.py` (used by `dd/extract.py`)
   
   Don't delete in isolation; coordinate with M6(b) deprecation work.

### Lower priority — research → architecture

5. **Designer-agent loop architecture**. The session's research thread (3 parallel deep-research agents + designer cognition synthesis) produced 4 architecture sketches in `docs/research/scorer-calibration-and-som-fidelity.md` §6.1 and a longer thread on cognitive primitives. The user pushed back on building a parallel system — wants to **shape the existing system** to support designer-flavored exploration. Concrete next step proposal (~700 LOC, 5 stages of 1 week each):
   - Stage 0: workspace data model (`design_sessions` + `variants` + `move_log` tables)
   - Stage 1: edit-loop on the workspace (orchestrator over existing scripts)
   - Stage 2: cognitive-primitive tool surface for the LLM (NAME / FRAME / MOVE / LATERAL / DRILL / APPRECIATE)
   - Stage 3: live linkograph monitor + FIXATION-BREAK
   - Stage 4: HTML index of variants tree for steering
   
   Not started. The user explicitly said NOT to build a new system; this would be **additive orchestration** over existing M7.0–M7.6 modules, not new infrastructure. Confirm scope before starting.

### Low priority — known defects with workarounds

6. **`link-1` empty in archetype output** (saw via MCP query of live render). Same class as the pre-existing button-leaf-type contract failure (`tests/test_mode3_contract.py::test_mode3_synthetic_children_are_first_class_ir_nodes`). Link is in `_LEAF_TYPES_FOR_HOIST`, gets no children synthesised, and the renderer's `props.text` consumption only fires on real text-type nodes. Needs a renderer-side gate that lets compose synthesise children for would-be-Mode-1-INSTANCE leaves while skipping `appendChild` at render time when node resolves as INSTANCE.

7. **Dank `button/large/translucent` × icon inheritance** (ADR-008 Fix #4 deferred). Visible on every Sign In button in archetype output. Cosmetic but persistent.

8. **ADR-008 Fix #5 (horizontal layout collapse)**. `dd/compose.py:147` hard-codes `direction=vertical` on screen-root children; LLM doesn't emit horizontal wrappers. Affects archetypes other than login.

## Critical session-learnings to carry forward

These are class-level patterns that hurt this session and should be avoided:

1. **Audit-by-grep is unreliable for "is this dead?"**. The April-cleanup audit recommended deleting 5 dd/ modules; verification showed all 5 had live production callers. Always verify a deletion candidate by running the actual code paths that import it, not just grep.

2. **The bridge has TWO failure modes that look the same**. Wrong-port renders (writing into the wrong file) produce missing-master-style errors that look identical to bridge-load transients. Always confirm bridge → file mapping before interpreting parity drops as data issues.

3. **Tags + measurements first, then conclusions**. The "round-trip regressed" finding mid-session was a wrong-port artifact; confirmed by checking out the pre-cleanup tag and re-running. Always confirm before concluding a regression.

4. **Bridge-load transients hide as data bugs**. The "wireframe placeholder firing" was diagnosed as bridge load (not code bug) only after isolating one screen and showing it ran cleanly on a fresh bridge call. Per-screen retry is now the standard sweep harness pattern.

5. **m7_ vocabulary is journal-entry naming, not API**. Using milestone numbers as permanent file/module names creates spaghetti. Action verbs name what code does.

6. **Don't take the user's casual mention as a hard architectural rule**. Earlier in the session "style comes LATER" was elevated to "the strongest signal in the brief" — but the user was describing a fluid process, not specifying a phase gate. Listen to descriptions of how something works; don't mine them for axioms.

## Pointers for next session start

```bash
# Confirm state
git tag -l "cleanup-*"     # 3 tags should be present
git log --oneline -10      # latest = chore(docs): archive 9 cross-referenced...
.venv/bin/python3 -m pytest tests/ -q --tb=no --timeout=60 2>&1 | tail -3
# expected: 3146 passed, 37 failed, 6 skipped

# If picking up the 25-drift investigation:
.venv/bin/python3 render_batch/sweep.py --port <port> --since 217 --limit 10
# expected: 217-226 all DRIFT with parity 0.95-0.98

# If picking up the designer-agent architecture:
# read docs/research/scorer-calibration-and-som-fidelity.md §6.1
# read docs/archive/continuations/continuation-v0.3-next-session.md (archived but informative)
```

## Files that grew this session

- `dd/fidelity_score.py` — +470 LOC across 4 commits (now has 7 dimensions: coverage, rootedness, font_readiness, component_child_consistency, leaf_type_structural, canvas_coverage, content_richness, plus optional component_precision + component_recall)
- `render_test/walk_ref.js` — extended to emit per-eid absolute bboxes + rotation (for SoM)
- `render_batch/sweep.py` — retry layer
- `dd/compose.py` — Mode-3 slot-position partition + label-hoist wrapper + alias position whitelist
- `tests/test_fidelity_score.py` — +14 tests for new dims (64 total fidelity tests green)
- `tests/test_mode3_contract.py` — +5 tests for label-hoist contract
- `scripts/tier_d_regate.py` (renamed from m7_tier_d_regate.py) — added SoM coverage + variance integration

## Files removed / moved this session

- `scripts/m7_*.py` × 35 → `scripts/*.py` (drop m7_)
- `tests/test_m7_*.py` × 3 → `tests/test_*.py`  
- `dd/m7_slots.py` → `dd/slots.py`
- `dd/m7_variants.py` → `dd/variants.py`
- 15 stale docs → `docs/archive/{continuations/,session-summaries/}`

That's the handoff. Memory + scorer state is solid. Cleanup is done with explicit deferrals. Next session can pick any of the 8 deferred items or start the designer-agent architecture sketch.
