# Loom script — declarative-build for Anthropic + design staff

**Length target**: 5-7 minutes
**Audience**: Anthropic Claude Code + design staff
**Tone**: engineer-to-engineer. Show architecture, not magic.

## Pre-flight checklist

- [ ] Bridge listening on `localhost:9228` (test:
      `python3 -c "import socket; s=socket.create_connection(('localhost', 9228), timeout=0.5); print('OK'); s.close()"`)
- [ ] Dank Experimental open as the active Figma file
- [ ] Stale `design session *` pages cleaned up (so the demo
      page list is short)
- [ ] `.env` has `ANTHROPIC_API_KEY` set
- [ ] Pre-record demo runs to disk so the Loom doesn't
      depend on real-time bridge state. Two clean recordings:
      Demo A (hide-toolbar, ~14s) and Demo B (sign-out button,
      ~30-60s)
- [ ] Architecture diagram open in a tab for screen-share

---

## The framing principle

Anthropic-side viewers have seen plenty of "LLM does a thing
in Figma" demos. They are LEAST impressed by raw capability,
MOST impressed by architecture. A Loom that shows the demo
without the architecture reads as marketing. A Loom that shows
the architecture with the demo as proof-of-life reads as
engineering.

The most valuable 30 seconds of the video aren't the demo —
they're the framing of WHY the architecture is the way it is.

---

## One thing to be careful about

The diagram has Stage 5 split into EDIT / COMPOSE / SYNTHESIZE.
**EDIT works today. COMPOSE and SYNTHESIZE have known visible
gaps.** Don't oversell as "we have three modes." Frame as:

> EDIT is what's deployed in the loop today. COMPOSE and
> SYNTHESIZE are the active research questions the system is
> set up to answer.

This honesty will read well to this audience.

---

## Beat 1 — The premise (40s)

**Show**: title card or talking head. No diagram yet.

**Say** (in your words; this is a sketch):
- Most LLM-design tools either generate code from screenshots
  or scaffold from prompts. Both make the LLM do too much.
- Our bet: build a compiler for design systems. The LLM
  doesn't generate Figma. It writes a *source language* that
  compiles to Figma. And to anything else.

**Takeaway**: this is a compiler project, not a prompting
project.

---

## Beat 2 — The architecture (75s)

**Show**: your diagram, full-screen. Pan across stages 1-4
left to right.

**Say**:
- Stage 1 — ingest the user's actual Figma file. Real
  components. Real tokens. Real screens. ~87,000 nodes from
  one project (Dank Experimental).
- Stage 2 — classify what we're looking at. Five
  classification sources fuse into a 65-type catalog: buttons,
  headers, toolbars, cards. Real components from the user's
  library, not generic UI primitives.
- Stage 3 — build semantic intermediate representations.
  Three levels: identity, tokens, markup. The markup level
  (L3) is what the LLM sees and writes.
- Stage 4 — deterministic compile and render. This is the
  part that matters for the M×N problem. Same source
  language, render to Figma today, React tomorrow, SwiftUI
  after that. The LLM never has to know which target it's
  compiling to.

**Takeaway**: real compiler with a real intermediate
representation, not a prompt template.

---

## Beat 3 — Why dd-markup (45s)

**Show**: a small piece of dd-markup on screen. Pull from
`tests/fixtures/markup/01-login-welcome.dd`. Show maybe 10-15
lines.

**Say**:
- This is dd-markup. It looks small because it is. But it
  references the user's actual components by canonical type,
  binds to their actual tokens, preserves slot semantics.
- It's the LLM-friendly part of the compiler. Compressed,
  semantic, ready for an LLM to read or write.
- Critical: most LLM-design tools train on synthetic data.
  We extracted dd-markup from a real Figma file. We have
  ground truth.

**Takeaway**: dd-markup isn't a DSL we invented to make LLMs
look smart. It's the natural intermediate for a compiler that
targets multiple backends.

---

## Beat 4 — Demo (90-120s)

**Show**: ONE clean run of the hide-toolbar demo. Pre-recorded
ideally; speed up the heartbeat lines if needed; the visible
result is what matters.

**The command** (run this once before recording, screenshot or
record):

```bash
rm -f /tmp/demo.db
.venv/bin/python -m dd design \
  --brief "Hide the entire bottom toolbar. Keep everything else." \
  --starting-screen 333 \
  --project-db Dank-EXP-02.declarative.db \
  --db /tmp/demo.db \
  --max-iters 4 \
  --render-to-figma
```

**Say**:
- Here's what "LLM operates the compiler" looks like
  end-to-end. One natural-language brief. The agent runs
  against a real user screen — iPad Pro 11" from a real
  project.
- The agent has 7 edit verbs and three focus primitives
  (NAME, DRILL, CLIMB). It reasons about the tree. Picks
  targets. Runs multi-iteration sessions persisted to SQL —
  branchable, resumable.
- (show side-by-side render appearing in Figma)
  Original on the left, agent's variant on the right. Same
  Figma file. The compiler did everything past the LLM's
  edits.
- Total time, real session: ~14 seconds. Real Sonnet calls.
  Real Figma plugin bridge. Real components from the user's
  design system.

**Takeaway**: the loop runs end-to-end against real designs in
real time. Not staged.

**Optional second demo (if time)**: append-heavy brief
("Add a sign-out button at the top-right of the toolbar").
This one shows DRILL working — agent narrows scope to
`nav-top-nav` before editing, demonstrating the focus
primitive. ~30-60s. Use only if pacing allows.

---

## Beat 5 — What this unlocks (75s)

**Show**: back to architecture diagram, pointing at Stage 5.
OR a second slide with three boxes (current scope, near-term,
the bet).

**Say**:
- What's deployed today is the EDIT mode — the agent
  operates on existing screens. That's what you just saw.
- Next: COMPOSE — assembling new screens from the user's
  components when partial donor matches exist. SYNTHESIZE —
  generating screens from scratch when no donor exists. Both
  have working prototypes. Both have visible gaps. Active
  research.
- The bigger leverage: every screen we extract is
  ground-truth dd-markup. We can systematically benchmark
  which LLMs, prompts, and tool schemas actually work — using
  real designs as the loss signal. Most of this category
  builds on synthetic data and vibes. We can measure.

**Takeaway**: the system is set up to answer questions the
field can't currently answer rigorously.

---

## Beat 6 — Close (30s)

**Show**: title card again, or talking head.

**Say**:
- The thesis: LLMs can't draw Figma. But they can write a
  compiler's source language that does.
- The architecture is what makes the demo possible. The demo
  is the proof. The harness is what makes the next year of
  work measurable.

---

## Notes on length variance

- 5-minute version: cut the optional second demo, tighten
  Beat 2 to 60s, tighten Beat 5 to 60s.
- 7-minute version: keep both demos in Beat 4, expand Beat 5
  to talk about WHAT the harness measures (structural diff +
  VLM pixel diff + SoM component coverage).

## Things to NOT include

- Stages 0-3 implementation work. Too in-the-weeds for a
  Loom; reads as "we worked hard," not "we built something
  insightful."
- Bridge perf bug fight. Real engineering, but a Loom is the
  wrong format.
- Technical caveats on every claim. Loom isn't a paper. Honest
  framing in Beat 5 is enough.
- Multiple demo briefs. Pick ONE. Maybe TWO if pacing allows.
  Hand-picking is fine if the framing is honest.

## Things to BE READY FOR

If anyone watches and asks follow-up questions, the docs
they'll want next:

- `ENTRYPOINT.md` — the project's one-page status snapshot
- `docs/plan-v0.3.md` — the canonical plan
- `docs/rationale/README.md` — why decisions were made
- `docs/demo-vision.md` — the harness idea + the demo shapes
- `pitch.md` and `how-it-works.md` — long-form versions of
  the framing

The Loom shouldn't try to cover what those cover. It should
make someone WANT to read those.
