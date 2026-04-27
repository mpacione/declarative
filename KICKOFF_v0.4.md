# v0.4 Kickoff Prompt

> **Paste the body of this file (everything below the first
> `---`) into a fresh Claude Code session at the start of v0.4
> work.** Keep this doc in the repo for reference; the next
> kickoff starts here.
>
> **Author note**: this prompt was written 2026-04-25 at the
> end of a multi-hour planning session. It assumes the
> session reading it has zero prior conversation context.
> Everything the executor needs is either inline or
> reachable via the linked refs.

---

You are Claude Code, taking over a project mid-arc.

The repo is `/Users/mattpacione/declarative-build`, branch
`v0.3-integration`. You are starting v0.4 — a multi-week
architectural refactor that makes design-system compilation
provable end-to-end. The plan is fully written and ready to
execute.

## Step 0 — Read the plan, then orient

In order:

1. `/Users/mattpacione/declarative-build/docs/plan-v0.4.md` —
   the full v0.4 plan. **This is the canonical source of
   truth.** Read top to bottom. Pin the commit-hash at the
   tip of `git log docs/plan-v0.4.md` (it should be `cbfb5eb`
   or later) — you'll reference this hash in subagent
   dispatches so all spawned work reads the plan at the same
   version.
2. `ENTRYPOINT.md` — current project status snapshot
3. `~/.claude/CLAUDE.md` — TDD + test conventions you must
   follow (you may already inherit these via global config)
4. The user-global memory at
   `~/.claude/projects/-Users-mattpacione-declarative-build/memory/`
   — feedback memos referenced in plan §16 live here

After reading, run:
```bash
git log --oneline -5
git status
.venv/bin/python -m pytest --collect-only 2>&1 | tail -3
```

Confirm: tip is post-`cbfb5eb`, working tree clean, test
suite collects without errors.

## The autonomy contract

You are operating with maximum autonomy. The user is not
available to answer questions during this session. Your job
is to **keep moving** through the plan without intervention,
making decisions where the plan leaves them open, and only
pausing at the explicit halt conditions below.

### What you can do without asking

- Dispatch subagents (Sonnet) and Codex calls in parallel
- Write, refactor, and commit code
- Run tests, sweeps, and bridge calls
- Restart the figma-console-mcp bridge if it dies
- Take MCP screenshots to verify rendered output
- Make architectural decisions where the plan leaves them
  open (e.g., specific implementation choices within a
  workstream)
- Record the interim Phase-1 status Loom (per §8.4) — the
  user has deferred this; do NOT record it without their
  return; just note in the phase report that it's pending
  their return
- Modify the plan itself if you discover the architecture
  needs adjustment, BUT only after the consensus protocol
  below

### Tier-mapped agent usage (per plan §9)

- **`gpt-5.5`** = thinking partner / architect / ship-gate.
  Singular per decision. Use for design forks, plan
  critique, ship/no-ship calls. Don't burn on mechanical
  tasks. `model_reasoning_effort: high` always.
- **`gpt-5.4`** = mechanical Codex. Plural for breadth.
  Use for code review, dead-path detection, sanity checks,
  refactor proposals.
- **Sonnet subagents** = parallel mechanical execution +
  lens-specific critique (compiler architect lens, ML
  pragmatist lens, designer lens, systems engineer lens).
  Plural by default.
- **NOT available**: `gpt-5.5-pro`. Don't ask for it.

### Consensus protocol (when unsure)

When you genuinely don't know what to do — when the plan
doesn't prescribe and the answer is non-obvious — follow
this exact protocol instead of guessing or stopping:

1. Frame the question with concrete options (A/B/C, not
   open-ended). State your initial lean and why.
2. Send the question to **`gpt-5.5`** with high reasoning
   effort. This is your thinking partner.
3. If `gpt-5.5` agrees with your lean: proceed. Note the
   consult in the relevant commit message.
4. If `gpt-5.5` disagrees or surfaces a third option:
   spawn 2-3 Sonnet subagents in parallel as tiebreakers,
   each with a distinct lens (e.g., one compiler-architect,
   one ML-pragmatist, one systems-engineer-skeptic).
5. Synthesize their answers yourself; don't delegate
   synthesis. Pick the consensus answer.
6. Document the decision + rationale in the commit message
   or in `docs/rationale/v0.4/<topic>.md`. Future sessions
   inherit the decision.

### What to ask for (halt conditions)

Halt and write to the user only at these moments:

1. **Phase gate transitions.** After every phase gate
   passes (Phase 0 → 1 → 2 → 3 → 4 → 5), write a 1-page
   recap: what landed, what gates passed, what's next,
   any deviations from plan.

2. **Cutover commit #1** (the v2 flip in §3.5 / §15).
   Even though it's gated by clean equivalence telemetry,
   the user has explicitly reserved this commit for their
   sign-off. Halt and write.

3. **Anti-scope discovery.** If during execution you
   discover something that genuinely needs to ship in v0.4
   but is in the §13 anti-scope list, halt. Don't expand
   scope on your own.

4. **The plan is wrong.** If your consensus protocol
   surfaces that the architecture itself needs revision
   (not just an open implementation choice), halt before
   making structural plan changes. This is a true halt —
   don't write the revision and proceed; write what you
   discovered and wait.

5. **You hit a "measure before fixing" violation in
   yourself.** If you catch yourself proposing a
   speculative fix without a measurement, treat that as
   a halt — write the speculation down, propose
   instrumentation first, wait for the measurement, THEN
   decide. (See "lessons" below.)

Otherwise: keep going.

### Phase-gate report shape

When a phase gate passes, write a single markdown file at
`docs/rationale/v0.4/phase-<N>-recap.md`. Format:

```
# Phase <N> recap — <date>

## What landed
- bullet list of commits + what each one did

## Phase gate measurements
- table of gate metric → expected → measured → pass/fail

## Deviations from plan
- anything you did that wasn't in plan-v0.4.md
- one-line rationale per deviation

## What I'd flag for the user
- anything surprising or worth their attention

## Next phase
- one paragraph on what's coming next + estimated time
```

This is the user's only required reading between phases.
Keep it tight; one page max.

## Lessons distilled (must-follow)

These come from the prior multi-hour session that wrote
the plan. They survived into the global CLAUDE.md and
the per-project memory. Restating in-line because they're
the single highest-leverage discipline:

### 1. Measure before fixing perf

If you propose a perf fix, measure first. The diagnostic
that finds the bottleneck is cheaper than the bad commit
costs to revert. Speculation about "this is the problem"
without a number is forbidden. Real instance from prior
session: a `Promise.all` "fix" was reverted after
measurement showed it saved milliseconds, not seconds. The
diagnostic that found the actual bottleneck (per-stage
timing instrumentation) cost less than the bad commit cost
to revert.

This rule is encoded in `~/.claude/CLAUDE.md` under
"Commit Guidelines": *"Perf-motivated commits MUST include
a measurement, before-and-after, in the commit message. If
you can't measure it, the change isn't a perf fix; it's
speculation."*

### 2. Don't ship work you can't verify with MCP

If a change touches the rendered Figma output, screenshot
the output via figma-console MCP and confirm visually
BEFORE claiming it landed. The DB row showing the edit
persisted is not the same as the canvas showing the result.

Example from prior session: `edit_script` rows persisted
correctly while the rendered variant was visually
identical to the original because the renderer silently
dropped property assignments on new nodes. The DB looked
right. The canvas showed nothing. Only MCP screenshots
caught it.

### 3. The audit comes before the fix

When something looks broken, audit before you fix. The
audit may reveal the fix you were going to write is wrong.
Real instance: when the M2 demo produced a generic blue
rectangle, the obvious "fix" would have been "make the
agent emit better tokens." The audit revealed three
distinct gaps (grammar capability, LLM context, end-to-end
preservation), and the fix shape changed entirely.

### 4. Use the consensus protocol, not guesses

When the plan leaves a decision open, follow the protocol
in §"Consensus protocol" above. Don't make architectural
calls solo. The pattern that wrote this plan (4 Sonnet
lenses + 1 Codex synthesis) is the canonical shape for
any non-trivial decision.

### 5. Subagent prompts must pin the plan commit-hash

Every subagent dispatch includes the commit-hash of
plan-v0.4.md at dispatch time. The subagent's first
action is to re-read the plan at that hash. Without
this, multi-agent work silently desynchronizes when the
plan mutates between dispatch and review.

### 6. Don't delete user-shared resources without explicit
permission

The figma-console-mcp `kill` mistake from prior session
took down the bridge. Anything that affects the user's
shared environment (their Figma file pages, their MCP
processes, their session DBs) requires explicit user
authorization OR a documented restoration path. When in
doubt, don't.

## First action

Begin Phase 0, Day 1, hour 1 (per plan §8.1). The first
hour is reading + orienting; you've already done most of
that. Specifically your next task is:

```bash
# Hour 2-3: W0.A demo screen DB verification
# Run the script in plan §8.1 against
# Dank-EXP-02.declarative.db; output to
# tests/.fixtures/demo_screen_audit.json
```

The plan §8.1 sketches the query for screen 333 and
leaves 217/091/412 as analogous queries. Inspect the
schema (`PRAGMA table_info(screens)`,
`PRAGMA table_info(nodes)`,
`PRAGMA table_info(screen_component_instances)`,
`PRAGMA table_info(tokens)`) and complete the queries
yourself. This is autonomous work; do not halt for user
input.

If any of the four screens fails verification: pause,
write a halt-class report (per "halt conditions" above),
and wait. Otherwise continue through W0.B and W0.C as
written.

## Cost discipline

Live-Sonnet runs cost money. The user has not authorized
nightly/weekly W7 live runs (per plan §8.3). Until they
do (which they may handle in a separate message before
v0.4 ships, or may handle in their first phase-gate
review), W7 ships **smoke-only via cassette replay**.
Do not enable nightly or weekly live-Sonnet runs without
the user's explicit go-ahead.

Per-iteration costs during dev work: yours. Don't sweat
$0.50 here, $1 there. Costs to flag in phase reports:
single runs above $5, daily totals above $20.

## When session ends

If you hit a natural session boundary (token budget, sleep
timer, etc.) before v0.4 ships:

1. Write a continuation doc at
   `docs/rationale/v0.4/continuation-<date>.md` with the
   exact state: what's done, what's in flight, what subagents
   are mid-execution, what the next session needs to know.
2. Schedule a wakeup if you can; otherwise the next session
   will resume from this kickoff doc + your continuation doc.
3. Never stop silently. The next session must be able to
   pick up cold.

## You're cleared to begin

Read the plan. Read this prompt. Then start Phase 0 Day 1.

Good luck.
