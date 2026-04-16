---
name: generate-screen
description: Generate a new Figma screen from a natural-language prompt using the extracted design system's components, tokens, and style conventions. Produces IR first, then renders. Non-regressive iterative refinement via a vision critic and the round-trip verification channel.
when_to_use: User describes a UI they want built, in their existing Figma design system's style. Phrases like "generate a settings screen", "make me a dashboard in this app's style", "create a profile page". Also chainable — user can ask for variants, refinements, or critiques.
requires:
  - An existing declarative-build SQLite database with the IR
  - A design.md style snapshot (produced by generate-design-md)
  - Figma Desktop bridge running (for rendering)
  - Anthropic API key (Claude for generation)
  - Google API key (Gemini for vision critique) — optional but recommended
---

# generate-screen

The synthetic-generation pipeline. Takes a prompt + design.md + corpus
retrieval context and produces a rendered Figma screen in the
project's style, verified for both structural parity (the IR matches
what rendered) and aesthetic quality (the render looks right).

## Pipeline stages

1. **Prompt parse.** Claude structured-output call with schema derived
   from the component catalog + property registry + design.md. Output:
   IR L3 tree with soft spatial intent (no concrete coordinates).
2. **Variant generation.** Optionally produce 5 variants on orthogonal
   design axes (information hierarchy, layout model, density,
   interaction model, expressive direction) for user selection.
3. **Layout resolution.** A constraint solver consumes the IR's soft
   spatial intent (auto-layout flags, sizing modes, token-bound
   padding/gap, ordering) and produces concrete positions. The LLM
   does not emit coordinates.
4. **Lowering + render.** Existing deterministic renderer produces the
   Figma Plugin script. Renders to the "Generated Test" page (or a
   user-specified page).
5. **Structural verification.** Existing `RenderVerifier` walks the
   rendered subtree and diffs against the IR. Produces a
   `RenderReport` with `is_parity` and `KIND_*` structured errors.
6. **Visual critique.** Gemini 3.1 Pro (or fallback) scores the
   rendered screen on the 5-dimension rubric (Layout / Consistency /
   Readability / Completeness / Aesthetics) with UICrit few-shot
   examples in the prompt.
7. **Iteration.** If critique scores below threshold, identify the
   two lowest dimensions, emit dimension-specific repair instructions,
   regenerate. Non-regressive acceptance (a regeneration is only
   accepted if it strictly exceeds the previous best score). Targeted
   edits to specific failing regions when possible, full regeneration
   only when needed.

Iteration loop terminates on score plateau, threshold crossed, or
iteration budget exhausted. Best-so-far is always returned.

## Inputs

Required:
- `prompt` — natural-language description of what to build.
- `db` — path to the IR database.
- `design_md` — path to the design.md style snapshot.

Optional:
- `plugin_port` — Figma Desktop bridge port. Default: 9231.
- `variants` — integer 1–5. Default: 1 (single output). Set to 5 for
  axis-variant exploration.
- `max_iterations` — iteration budget for the critique loop. Default: 3.
- `critique_threshold` — minimum average score to accept. Default: 7.5.
- `target_page` — Figma page name to render into. Default: "Generated Test".
- `out_dir` — directory to dump all artefacts (IR JSON, script, screenshots,
  RenderReport, critique scores, activity log). Default: temp directory.

## Behaviour at a glance

```
prompt
  → generation adapter        [5 variants on axes if --variants=5]
  → constraint solver          [Cassowary: soft intent → concrete positions]
  → existing lowering + render [Figma Plugin script via bridge]
  → existing structural verifier [is_parity, KIND_* errors]
  → vision critic              [Gemini 3.1 Pro, UICrit few-shot, 5-dim rubric]
  → loop with non-regressive acceptance
  → return best-of with full audit trail
```

Everything inside "existing lowering + render" is unchanged from the
round-trip foundation pipeline.

## Outputs

- Rendered Figma node(s) on the target page.
- IR JSON(s) per generated variant.
- Plugin script(s).
- `RenderReport` per render.
- Critique scores per render.
- Activity log of the iteration loop.
- Final summary:
  - Variants generated (if >1).
  - Iterations run.
  - Accepted output's critique scores.
  - `is_parity` status.
  - Any `KIND_*` fidelity losses (e.g. `KIND_COMPONENT_UNAVAILABLE`
    for a requested component the design system lacks).

## Error handling

Per the (egress-side) boundary contract: LLM refusals, schema
violations, missing components, render failures, critic disagreements
all produce structured entries. The caller receives a
`GenerationResult` with `summary.succeeded`, `summary.degraded`, or
`summary.failed` counts. Partial success with known fidelity loss is
a legitimate outcome.

## What this skill does NOT do

- Does not generate on-the-fly without a design.md. The skill refuses
  and recommends running `generate-design-md` first.
- Does not push generated tokens back to Figma. That's the existing
  `dd push` CLI, possibly surfaceable as a separate skill later.
- Does not modify the source design system. It reads; it doesn't
  write (except to the Generated Test page).
- Does not train or fine-tune anything. The iteration loop is
  inference-time only.

## Example usage

```
User: "Generate a paywall screen with three pricing tiers and a
       testimonial for my app."

Assistant runs:
  dd generate-screen
    --prompt "a paywall screen with three pricing tiers and a testimonial"
    --db my-app.declarative.db
    --design-md design.md
    --variants 1
    --max-iterations 3

Reports:
  ✓ IR generated (42 nodes).
  ✓ Constraint solver resolved positions (mean IoU-to-layout-intent 0.97).
  ✓ Rendered to Generated Test page (node id 5750:123456).
  ✓ Structural parity: True (42/42 nodes, 0 errors).
  ⚠ Critique: 6.8/10 avg. Weakest dimensions: Hierarchy (5), Aesthetics (6).
  ⇆ Iteration 2 with dimension-specific repair on hierarchy...
  ✓ Iteration 2 accepted: 7.9/10 avg. Weakest now: Aesthetics (7).
  ≈ Iteration 3 scored 7.6/10 — did not exceed prior best. Rejected.
  ✓ Returning iteration-2 output. Artefacts in /tmp/gen_a9f3/.
```

## Typical chain

1. `extract-figma` (if not already done).
2. `generate-design-md`, then designer edits TODO sections.
3. `generate-screen` (optionally looped or variant-expanded).
4. `verify-parity` (redundant with the pipeline's internal check, but
   useful as an independent audit).
