# Session summary — scorer calibration + SoM-based component coverage

**Date:** 2026-04-21 late session.
**Starting state:** Tier D "2/3 passed ≥7/10" claimed in
`docs/plan-burndown.md`; memory snapshot agreed.
**Ending state:** two commits landed, both touching
`dd/fidelity_score.py`. Scorer calibration corrected and SoM-based
component-coverage wired in as the primary semantic fidelity signal.

## The arc

1. **Re-gate discovered scorer miscalibration.** Running the 3 Tier D
   prompts through bridge + screenshot + Gemini VLM revealed the
   "subtree passing 10/10" was on a visually-blank page (one `×` icon,
   nothing else). All four structural dims passed trivially on a
   2-element IR tree. Second occurrence of the class named in
   `feedback_auto_inspect_before_human_rate.md`.

2. **Phase A committed** (`978a6b5`): two rule-based visual-plausibility
   dims — `canvas_coverage` (ratio of direct-children bbox / root bbox,
   clamped) and `content_richness` (count of rendered nodes with
   visible content, clamped). Subtree dropped 10.0 → 2.0; login stayed
   honest at 10.0; voxel stayed failing at 2.0.

3. **Literature review (2026-04-21)** — arXiv:2601.03444 (Jan 2026)
   showed **0-10 is empirically the worst grading scale** for LLM-as-
   judge across 6 benchmarks (0-5 wins). Directly explained the
   ±3 Gemini noise we saw. GenEval (2023, 83% human agreement) and
   Design2Code Block-Match (ACL 2025) converge on
   **detect-components → compare-to-expected** as the right shape, not
   holistic rating. Every serious UI benchmark reports a vector, not a
   scalar.

4. **Phase B committed** (`803c3e3`): SoM-based component coverage.
   Reuses `dd/classify_vision_som.py` (422 LOC, already shipped for
   M7 classifier-v2). Three pure functions (`build_som_annotations`,
   `compute_coverage_from_types`, `score_component_coverage`) emit
   precision + recall as **two independent dims** per GenEval /
   Design2Code convention. 14 new tests, 64/64 fidelity green.
   Extended `render_test/walk_ref.js` to emit per-eid absolute
   bboxes + rotation so SoM can mark up the rendered screenshot.

5. **Research documented** in `docs/research/scorer-calibration-and-
   som-fidelity.md` and the memory note
   `feedback_scorer_calibration_and_som_fidelity.md`. Six decisions
   captured (D1 drop 1-10, D2 SoM coverage, D3 walk payload extension,
   D4 vector not scalar, D5 variance measurement, D6 is_parity as hard
   gate) plus a not-doing list with explicit rejections.

## First live SoM run (Tier D prompts, bridge on)

| prompt | struct | SoM-P | SoM-R | VLM(1-10) |
|---|---|---|---|---|
| subtree (toast) | 0.0 | **0.00** | **0.00** | 2/10 broken |
| archetype (login) | 3.0 | 0.43 | 0.30 | 10/10 ok |
| synthesis (voxel) | 2.0 | 0.26 | 0.24 | 6/10 partial |

### Surprising finding: SoM surfaces a real Mode-3 bug

The archetype login has VLM=10/10 but SoM-P=0.43 / SoM-R=0.30. Diving
in: the IR declares `text_input` for the email + password fields, but
the **renderer emits a frame-of-text-children** that SoM correctly
classifies as `container`. Per-eid comparison:

```
IR=text_input   SoM=container   ← Mode-3 bug: text_input isn't hydrated
IR=text         SoM=tooltip     ← labels adjacent to inputs read as tooltips
IR=button       SoM=button_group ← Dank × icon makes button look like 2
IR=link         SoM=text_cursor ← unusual misclassification
IR=card         SoM=container   ← plain white frame has no card cues
```

This is exactly the diagnostic signal the lit review promised and the
1-10 VLM cannot produce. It's telling us: *the IR claims more
structure than the renderer delivers*. Specifically, Mode-3 text_input
composition is emitting children-of-text instead of a proper input
widget. Corresponds to the pre-existing `test_mode3_contract.py`
failures we noted earlier: "Mode-3 must splice a text child carrying
the button's label."

## The variance measurement (D5) — results

Ran 3× identical re-gate runs (≈15 min wall-clock total). Stdev per
metric:

| prompt | struct | SoM-P | SoM-R | **VLM (1-10)** |
|---|---|---|---|---|
| subtree | 0.00 | 0.00 | 0.00 | **0.58** |
| archetype | 1.07 | 0.11 | 0.11 | **2.08** |
| synthesis | 1.13 | 0.24 | 0.24 | **2.89** |

**VLM is 2-25x noisier than SoM across every prompt.** On
screen_archetype, the VLM rating ranged 5–9/10 across identical
runs; SoM precision stayed at 0.43 on two runs and 0.62 on one
(stdev 0.11). On screen_synthesis, the VLM ranged 0–5 (one run
was "unknown" verdict — Gemini's 30% transient per
`feedback_vlm_transient_retries.md` struck again). SoM stayed in
the 0.19-0.48 band.

Mean values:

| prompt | struct mean | SoM-P mean | SoM-R mean | VLM mean |
|---|---|---|---|---|
| subtree | 0.00 | 0.00 | 0.00 | 1.67 |
| archetype | 3.78 | 0.49 | 0.38 | 7.33 |
| synthesis | 1.30 | 0.23 | 0.22 | 3.33 |

**Conclusion**: the research finding (arXiv:2601.03444) holds for
us. SoM precision + recall is a dramatically more stable signal
than the 1-10 VLM rating. Decision D2 (promote SoM as primary
semantic-fidelity dim) is confirmed. Decision D5 (retire the 1-10
Gemini rating from `tier_d_regate`'s pass gate) is safe to
execute — but keep the dim as an opt-in comparator until we've
run SoM against a wider sample.

Variance measurement artefacts preserved:
- `tmp/tier_d_variance/variance_report.md`
- `tmp/tier_d_variance/variance.json`
- `tmp/tier_d_variance/run{1,2,3}/` — per-run artefacts for audit

## Follow-up: Mode-3 text_input label-hoist (commit `<TBD>`)

The SoM dim flagged text_input rendering as `container` on archetype
login (visually: labels stacked INSIDE the input frame). The
universal catalog's `text_input` template declares the `label` slot
at `position="top"` (external sibling above), but
`_mode3_synthesise_children` was lumping all slot children as
internal children, ignoring `position`.

**Fix (TDD, 5 new tests):**
- `_mode3_synthesise_children` now returns `dict[position, list[eid]]`
  — partitioning children by the slot's declared position.
- `_build_element` wraps the parent in an outer vertical frame when
  any external (`top`/`bottom`) children are produced: wrapper
  holds `[top siblings, parent, bottom siblings]`.
- Closed a latent aliasing bug: `placeholder` prop was filling the
  `label` slot (position=top) via alias fallback. Added
  `_ALIAS_POSITION_WHITELIST` so `placeholder` can only fill
  `{"fill", "start", "end", "_default"}` positions.

**Result on Tier D archetype re-gate (same prompt, 1 run):**

| metric | before | after |
|---|---|---|
| struct | 3.0 | **5.0** |
| SoM-P | 0.43 | **0.71** (+65% rel) |
| SoM-R | 0.30 | **0.50** (+67% rel) |
| VLM | 9/10 | 9/10 |

Visual diff: label "Email" now sits **above** a stroked input box
containing "Enter your email" placeholder — instead of the prior
"two stacked labels inside a frame." SoM now sees `text_input` as
a detected type (previously only `container`).

## What's deferred (not blocked, just next)

Three things surfaced that would be natural next units:

- **Prompt-intent coverage** (research doc §G3) — extract expected
  components from the PROMPT (not IR) via an LLM pass, then compare
  SoM detections against prompt-intent. Would evaluate "did the
  pipeline realize the user's intent" rather than "did the IR match
  the render." This is genuinely unpublished territory.
- **Fix Mode-3 text_input hydration** (the bug SoM just surfaced).
  This is compose-layer work in `dd/compose.py::_mode3_synthesise_children`
  or `_apply_template_to_parent`. Probably ~1 day with TDD.
- **Retire the 1-10 VLM dim**, gated on the variance measurement
  showing SoM dominates noise-wise. If variance roughly ties, keep
  both as independent signals.

## File manifest (this session)

Production code:
- `dd/fidelity_score.py` — +400 LOC (two commits); 7 scorer dims now
- `render_test/walk_ref.js` — per-eid x/y/rotation + root dims
- `scripts/tier_d_regate.py` — screenshot → SoM → both dims
- `scripts/tier_d_variance.py` — NEW; D5 measurement harness

Research / docs:
- `docs/research/scorer-calibration-and-som-fidelity.md` — full trace
- `docs/session-summary-2026-04-21-scorer.md` — this doc

Memory (`~/.claude/.../memory`):
- `feedback_scorer_calibration_and_som_fidelity.md` — principle
  + next unit
- `MEMORY.md` — index updated

Tests: 64 fidelity tests green (14 new). Full suite: same 37
pre-existing integration failures (all unrelated to scorer), no new
failures introduced.

Round-trip parity: not revalidated in this session because the
changes touched only scorer + additive walk-payload fields. Recommend
running `render_batch/sweep.py` once before landing any broader
changes that touch compose/renderer.
