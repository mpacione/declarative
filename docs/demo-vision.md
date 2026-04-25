# Demo vision — what "compelling" looks like

Written 2026-04-24 while M1+M2 just landed. Goal: help decide
what to build next for the demo-to-one-person, without
over-promising. Three research passes (repo inventory, prior-art
survey, independent Codex strategic read) converged on the same
shapes. This is the synthesis.

## The default if we ship nothing else

**One brief, one before/after on a new Figma page.** This works
today. Validated visually on:

- "Hide the entire bottom toolbar" — agent did 2 `set
  visible=false` edits, halt=done in 3 iters, bottom toolbar
  cleanly gone on variant.
- "Add a sign-out button at the top-right of the toolbar" —
  agent did append (frame+text) + 3 sets (layout, padding,
  fill). Red button rendered. Caveat: agent targeted bottom
  toolbar instead of top nav.

Audience reaction of "neat single-edit" is the failure mode to
dodge. That means either more edits per session, more visible
structural change, or more demonstrated intentionality.

## What we actually have to build on

- **7 edit verbs**: set, delete, append, insert, move, swap,
  replace — all working end-to-end post-M2.
- **Focus primitives**: NAME (annotate), DRILL (scope into),
  CLIMB (scope out). Persisted in move_log. Session loop
  exposes them as LLM tools.
- **Sessions + branching**: every iter persists to SQL.
  Branching falls out of resume-from-non-leaf — no separate
  verb needed. Never been demoed visually.
- **Component swap via CKR**: `swap @node with=-> button/primary`
  replaces a node with a library component. Validated
  structurally. Untested in a visible demo.
- **Token references**: `fill={color.surface.primary}` parses,
  the resolver passes refs through unchanged, rebind path
  exists in `dd/rebind_prompt.py`. **Never exercised in an
  agent-driven round-trip.** Biggest unknown.
- **Renderer parity**: 204/204 round-trip holds on Dank screens.
- **NOT shipped**: multi-screen reasoning, real fidelity
  scoring, sketch input, live UI.

## Four demo shapes

Ranked by (compellingness × buildability). Each has a one-line
description, what makes it land, what's required, and what could
go wrong.

### Shape 1 — Branch-and-Compare ("design IDE with time travel")

**What**: Run one session on screen 333. Halt, then use
`dd design resume <mid-variant-id>` to branch from a non-leaf
and explore 2-3 alternative directions. Render each variant to
its own Figma page. Show them side-by-side.

**Why it lands**: Single-brief demos read as "LLM did a thing."
Branch exploration reads as *design exploration* — "this tool
lets me try multiple directions from the same starting point,
with provenance." That's a structurally different story than
"LLM autocompletes."

**Required**: Existing SQL persistence + resume + render-to-figma.
~30 LOC wiring: auto-generate page names per branch
(`design session <ULID>/<branch-label>`), optionally emit
a simple "branch tree" printout in the CLI. No new primitives.

**Risk**: If the three branches look too similar, the time-travel
framing fails. Pick briefs that produce obviously-different
layouts or component choices. Good candidate: "Remove the bottom
toolbar" vs "Simplify the top nav" vs "Hide all decorative
chrome" — each against the same starting state.

### Shape 2 — Scope-Locked Editing ("I can control it")

**What**: Rerun a brief that previously missed — the sign-out
button went to the wrong toolbar — but this time the agent is
forced to NAME and DRILL into the correct subtree BEFORE editing.
Two runs, same brief, with and without focus. The controlled run
hits the right target.

**Why it lands**: The honest demo objection is "but LLM vibes,
can I control it?" This converts the failure we just hit into a
*demonstrated solution*. Shows the system isn't just prompting —
it has scope primitives. Engineer-friendly framing.

**Required**: Same 7 verbs + focus primitives. Small prompt-
template tightening so the agent uses DRILL when it sees an
ambiguous brief. No new code required; mostly prompt-work and
selecting the right pair of briefs.

**Risk**: If the CLI output doesn't visibly surface the focus
state, the audience might miss the control. Worth adding a
simple "focus: @top-nav" line to the per-iter heartbeat.

**Undervalued** per Codex #3. Directly answers the objection
that today's demo creates.

### Shape 3 — Component-Driven Refactor

**What**: Brief: "Replace the bottom toolbar with a search bar
instead." Agent uses `swap` verb + CKR to pivot a toolbar
instance to a search-bar component from the Dank library. Then
2-3 `set` edits to adjust padding/visibility. Big visual change
from a small instruction.

**Why it lands**: Demonstrates the system is *hooked into the
user's real design system*, not just drawing rectangles. Swaps
inside library components feel qualitatively different from
"append a frame and make it red."

**Required**: The swap verb works. CKR has 129 components in
Dank. Need to pick a starting node that IS componentized AND
has a plausible replacement in the same library.

**Risk**: If the CKR doesn't contain the right replacement
component, or the agent picks a wrong target, the demo fizzles.
Pre-scout the library to find a known-good swap pair before
the demo.

### Shape 4 — Multi-Verb Surgical Transformation

**What**: A brief that forces restructure (move + insert + swap)
PLUS cleanup (delete + set) in one session. Something like
"Consolidate the three bottom toolbars into a single simpler
one." Agent has to plan multiple ops.

**Why it lands**: Shows genuine design automation across many
edits. Feels least like "autocomplete."

**Required**: Mostly prompting + selecting a starting region that
CAN be consolidated cleanly. No new primitives.

**Risk**: **Highest chance of messy output.** Multi-verb
transforms stress the agent's planning harder than any other
shape. If the agent emits 8 edits and only 5 land cleanly, the
demo looks unsettled. Most likely to disappoint.

## Shapes I'd avoid for a short-window demo

- **Mode-3 from-scratch composition**: known visual gaps per
  `feedback_mode3_visual_gap_root_cause.md`. LLM emits props
  correctly but the renderer doesn't synthesize internal slots
  (a `button` renders as an empty frame). Big structural work
  before this looks good.
- **Token rebinding**: path exists but has NEVER been
  agent-driven. "Change the primary color" sounds compelling,
  but an unknown integration is exactly what breaks live.
- **"Score this design" / fidelity demos**: stub today. Would
  either need the full backend or the appearance of one —
  smoke-and-mirrors risk is high.
- **Multi-screen sequences**: not a thing the agent can reason
  about today. Would require net-new session architecture.

## My read

**The two safest shapes that distinguish from "single-edit
toy":**

1. **Branch-and-Compare (Shape 1)** — biggest narrative upgrade
   per unit of new code. Goes from "LLM made a change" to
   "designer iterates."
2. **Scope-Locked Editing (Shape 2)** — smallest new-work budget,
   directly addresses the objection the current demos create.

**If there's appetite for more**: stack Shape 1 + Shape 2 into
ONE demo. Start with the naive sign-out brief (goes to wrong
toolbar, imperfect), then show the fix via DRILL (right target,
right result), then branch from that variant to try two styling
directions. That's a 10-minute story with three visible
transitions.

**What to save for next demo**: Shape 3 (component swap) is
very compelling but one level of pre-demo scouting more than the
others. Worth a session on its own when there's time to pick the
right starting node + replacement pair.

## Things I'd want to fix before any of these

- **`focus=@None` heartbeat** (cosmetic). Says `@None` when the
  focus is the doc root; should say `@<root-eid>` or `(root)`.
- **Brief-phrasing doc update**: `docs/demo-m1.md` should note
  the sign-out demo taught us that "top-right of the toolbar"
  can mean the wrong toolbar. Suggest prefixing explicit-target
  briefs with the target subtree name.
- **Session-DB file location**: `/tmp/demo.db` gets clobbered
  between runs. Fine for ad-hoc; worth timestamping the path
  for demos we want to save.

None demo-blocking.

## Rough scope estimates

| Shape | New code | Prompt work | Pre-demo scouting |
|---|---|---|---|
| 1 — Branch-and-Compare | ~30 LOC | Light | 15 min |
| 2 — Scope-Locked | ~10 LOC | Medium | 30 min |
| 3 — Component Refactor | ~0 LOC | Light | 60 min |
| 4 — Multi-Verb | ~0 LOC | Heavy | 60 min |
| 1+2 stacked | ~40 LOC | Medium | 45 min |

Each shape can demo in under 5 minutes once the setup is right.

## Post-demo: the harness idea

Captured 2026-04-24 from a driving thought. Not an immediate
priority — the demo is the priority. But this is the bet that
makes v0.4 interesting.

**The thesis**: we have ~200 Dank screens encoded as dd-markup.
That's not a demo asset; it's a **ground-truth corpus**. Most
LLM-design tools don't have one. We do.

**What that unlocks**: systematic discovery of where the LLM
fails and where it succeeds, against real designs, without
human labeling. We can't backprop through Sonnet's weights,
but we can iterate on the SYSTEM around it (prompts, tool
schemas, model choice, in-context examples) using objective
scores.

**Three task shapes** to bench against:

1. **Reconstruct-after-mask** — take screen S, mask subtree T,
   brief is "complete the missing X." Score against ground
   truth S.
2. **Recreate-from-scratch** — generate a description of S
   (separate Sonnet call), then brief that description against
   empty doc. Score against S.
3. **Edit-from-instruction** — take screen pair (S, S') where
   we know what transformation produced S'. Synthesize a brief
   from the diff. Run agent. Score against S'. **Most
   scalable** — one screen yields dozens of test cases.

**Loss function**: multiple heads, weighted average, calibrated.
Structural diff (cheap) + VLM pixel diff (expensive, real
signal) + SoM component coverage (already in
`dd/classify_vision_som.py`). Don't find the One True Score.

**What it unlocks operationally**:

- Model bake-offs (Haiku vs Sonnet vs Sonnet-next)
- Systematic prompt iteration (DRILL prior was tested on ONE
  demo run today; harness would test on 50)
- Failure-mode clustering (find the M2-shape bugs without
  needing user-in-the-loop demos)
- Regression catch on renderer changes

**Hard parts that aren't solved**:

- Loss-function calibration (high score must mean "looks
  right"; the codebase has wrestled with this in the
  fidelity research cluster)
- Synthesizing briefs from screen pairs is itself an LLM task,
  brings noise
- Speed: ~30s per eval × thousands of evals = hours/days.
  Deliberate eval selection matters.

**Why post-demo, not pre-demo**: classic infrastructure-before-
product trap. Demo proves the basic premise lands. Harness
scales the answer to "can this really do design work?" — but
we need to demo the easy version first to get someone to care.

**Where this lives**: `dd design score` is a stub today. It's
the entry point. Building out the backend is the v0.4 work
this makes possible.
