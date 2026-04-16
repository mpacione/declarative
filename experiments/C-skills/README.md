# Experiment C — SKILL.md drafts

> **Status:** paper-only. Four SKILL.md drafts to evaluate whether
> the boundaries we'd propose for skill-first distribution feel like
> natural units of user intent.
>
> **The question we're answering:** does splitting our CLI surface
> into skills compose cleanly across realistic user flows, or does
> the abstraction fight the existing CLI?

## The four proposed skills

- **`declarative-build/extract-figma`** — ingest a Figma file into
  the local SQLite IR.
- **`declarative-build/verify-parity`** — check a rendered Figma
  subtree against its IR.
- **`declarative-build/generate-design-md`** — auto-generate a
  `design.md` style snapshot from the IR.
- **`declarative-build/generate-screen`** — prompt (+ optional
  context) → IR → rendered Figma screen.

Each is a thin SKILL.md wrapping existing Python binaries. The idea
is that a user with Claude Code (or Codex CLI, or ChatGPT
Desktop — SKILL.md is cross-vendor) installs what they need and
chains capabilities conversationally.

## Composition test — three realistic user flows

Walking through whether the four skills compose cleanly for
plausible user journeys before committing to the split.

### Flow 1 — "I want to reproduce my Figma file in React later"

User chains:
1. `extract-figma` → SQLite IR for their file
2. `verify-parity` → prove the round trip works against Figma
   first, before trusting the IR for cross-platform translation
3. (Future: `generate-react` skill) reads the IR, emits React

Clean chain. Each skill is a unit of intent. ✅

### Flow 2 — "Generate a new screen in my design system's style"

User chains:
1. `extract-figma` (if not already extracted) → IR for their file
2. `generate-design-md` → style snapshot (designer reviews, edits)
3. `generate-screen` "a settings page with privacy toggles" →
   renders into the Figma file

Again a clean chain. `generate-design-md` is a separate unit because
the designer reviews the output before the synthetic generator uses
it. If it were folded into `generate-screen`, the designer wouldn't
get a review step. ✅

### Flow 3 — "I have a Figma file, I want to start from scratch and iterate"

1. `extract-figma` → snapshot of current state
2. `generate-screen` "make me a dashboard for expenses"
3. `verify-parity` → confirm the rendered screen matches the
   generator's IR (catches generator-to-renderer drift)
4. User iterates: edits the rendered screen in Figma, re-extracts,
   re-generates variants based on the updated corpus

All four skills participate. Natural loop. ✅

**Verdict so far:** the skill boundaries map onto units of user
intent that would actually be exposed in conversational use. No
flow requires an "extract-and-generate" mega-skill; no flow asks
for a sub-skill of one of the four.

## Files in this directory

- `extract-figma.skill.md` — draft
- `verify-parity.skill.md` — draft
- `generate-design-md.skill.md` — draft
- `generate-screen.skill.md` — draft
- `composition-notes.md` — detailed walk-through of the three flows
  including specific conversational turns
