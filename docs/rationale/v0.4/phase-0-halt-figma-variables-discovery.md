# Phase 0 HALT — Figma Variables discovery (2026-04-25)

> Status: HALT-CLASS. Surfaced via W0.B probe execution. Plan
> assumed one token namespace; the reality has three. Need user
> decision before proceeding into Phase 1.

## What I found

While executing the W0.B probes through the live bridge against
the Dank Experimental Figma file, I ran a sanity check on
`figma.variables.getLocalVariableCollectionsAsync()`. Result:

**The source Figma file has 374 hand-authored Figma Variables
across 8 collections**, with intent-named, slash-separated
names that look exactly like the spec tokens v0.4 was designed
around.

| Collection | Variables | Modes | Sample names |
|---|---:|---:|---|
| Effects | 26 | 3 | (not sampled) |
| Opacity | 4 | 2 | (not sampled) |
| Radius | 23 | 3 | `radius/v9` |
| Typography | 164 | 3 | (not sampled) |
| Spacing | 27 | 3 | (not sampled) |
| **Colors** | **52** | **2** | **`color/border/accent`** |
| Component States | 12 | 3 | (not sampled) |
| Color Primitives | 66 | 3 | (not sampled) |

Total: **374 named variables**, with multi-mode support
(Default / Dark / Compact in most collections — meaning the
file already has dark-mode + compact-density theming wired in).

## Why this matters

There are now **three different token worlds** I have to
reconcile, and the plan only models one.

| World | Source | Naming scheme | Count | Authoritative? |
|---|---|---|---:|---|
| 1. Auto-clustered SQL `tokens` table | `dd cluster` populated this 30 min ago from observed colors/sizes | role + lightness rank (`color.border.tertiary`) | 327 | NO — derived, today. Reversible. |
| 2. **Hand-authored Figma Variables** in source file | Author of Dank Experimental file | intent + scope (`color/border/accent`) | 374 | **YES — this is the user's real DS** |
| 3. Per-node `boundVariables` map | live Figma file binding state | references into world #2 | (sparse on sampled nodes) | YES — derived from #2 |

**The plan v0.4 assumes one IR-resident "tokens" namespace,
loaded from the SQL DB.** That's world #1. But the ground-truth
DS lives in world #2, which:

- Has **intent names**, not auto-named role+lightness ranks.
  E.g. `color/border/accent` is the real "tap state accent" the
  Demo A brief actually meant. We don't need `color.action.primary`
  because the file already calls its real version `color/border/accent`.
- Has **multi-mode** support (Default/Dark/Compact) — the v0.4
  IR + resolver have no shape for variable modes.
- Is **what `boundVariables` references**, not what the SQL
  `tokens` table references. So `node.boundVariables.fill ==
  "VariableID:5438:33594"` resolves to `color/border/accent`
  through Figma's Plugin API, NOT through our SQL.
- Is what **token-mutation propagation actually mutates** when
  the operator changes a swatch in the Figma Variables panel
  (Demo B's kill-shot). My current Demo B brief assumes the
  cluster-named `color.border.tertiary` propagates; the *real*
  propagation token is whatever Figma Variable name underlies
  that color in world #2.

## Why I (and the plan author) missed this

- The SQL extraction (`dd extract`) populated `node_token_bindings`
  with `binding_status='unbound'` for every row. That looked
  like "no tokens authored" but actually meant "the extraction
  step doesn't read Figma Variables." Two different things.
- The plan's reference doc trail (`feedback_*.md`) doesn't
  mention Figma Variables at all. The whole memory layer
  modeled the SQL tokens world.
- I executed `dd cluster` to "populate the tokens table"
  because that's what `dd status` told me was empty. The
  pipeline was designed before Figma Variables were a thing
  (or before the file had them); cluster populates SQL state,
  not Figma Variables.

The user-given kickoff line "**The plan is wrong** — If your
consensus protocol surfaces that the architecture itself needs
revision (not just an open implementation choice), halt before
making structural plan changes" applies here.

## What I'm flagging — three architectural questions

### Q1. Which token world is the v0.4 resolver source of truth?

Three options:

- **A. Figma Variables (world #2) only.** The resolver loads
  the catalog by walking `figma.variables.*` through the bridge
  at session start. SQL `tokens` table is irrelevant to v0.4
  going forward. Demo briefs reference real intent names
  (`color/border/accent` etc.). `dd cluster` becomes a
  pre-extraction tool for files that don't have hand-authored
  variables; not part of the v0.4 critical path.
- **B. SQL `tokens` (world #1) only.** Stay the course.
  Auto-named tokens are what the agent sees. Demos use auto
  names. World #2 is ignored. Trade-off: "intent-token
  preservation" claim becomes a stretch when the file already
  has intent tokens we're not honoring.
- **C. Both, with a bridge layer.** Resolver catalog is union
  of the two; node bindings come from world #2 when present,
  fall through to inferred world-#1 mappings otherwise. Most
  faithful to file reality but doubles the resolver surface
  + blows up the catalog enum size.

My lean: **A**. World #2 is what the user actually authored.
World #1 was a workaround for the empty-tokens-table
appearance. v0.4's "design-system-aware compilation" claim is
much stronger when the DS is the user's real DS, not an
auto-derived one.

### Q2. Do the four demo briefs need another rewrite?

Yes, if Q1 = A. The auto-named tokens I just put in the v3.1
plan (`color.border.tertiary`, `radius.12`, `color.border.primary`)
all need to swap to whatever the corresponding Figma
Variables are (`color/border/accent` and friends). I'd need
to walk the file through the bridge to map them.

The intents are unchanged; the names change.

### Q3. Should `dd cluster` be reverted?

I ran `dd cluster` + `dd accept-all` 30 min ago. The DB
mutation is reversible (snapshot at
`archive/db-snapshots/Dank-EXP-02.declarative.pre-v0.4-cluster-20260425-005855.bak.db`).

If Q1 = A, the auto-named tokens are dead weight in the SQL
DB. Restoring the snapshot is clean; alternatively leave the
auto names in place as a fallback for files without
hand-authored variables.

My lean: **leave them**. They're not on the v0.4 critical path
and they're harmless for files without Figma Variables.

## What I will NOT do without your decision

- Plan-edit world #2 into the resolver catalog shape.
- Walk the bridge to extract all 374 Figma Variables + map
  them onto node bindings.
- Rewrite Demo briefs to reference real intent names.
- Revert `dd cluster`.

Each of those is a structural plan change.

## What I CAN do without your decision (low-blast pre-work)

- Walk the bridge to enumerate the full Figma Variables list
  + dump it to `tests/.fixtures/figma_variables_dump.json` so
  you have the data when you decide.
- Spot-check 3-5 anchor nodes (the ones in the demo audit) to
  confirm whether they actually have `boundVariables` set in
  the source file (the ones I sampled were empty, but those
  may not be representative).
- Continue with W0.C `Dank-Test-v0.4` skeleton authoring (no
  Figma writes; just script wiring).

If you're back briefly, the highest-leverage thing you can do
is answer Q1. The rest follows.

## Current commits

- `e1c6254` — plan v3.1 with auto-named tokens (commits the
  cluster-derived path; this halt note flags that the path may
  be wrong)
- `027d392` — Phase 0 follow-on (W0.B/W0.C scripts, baseline,
  dispatch template, recap)

Both are reversible. v3.1 is not yet load-bearing for any
implementation work.

## Cost so far

- Phase 0 day 1 total: ~$1 of LLM calls. No live-Sonnet runs.

---

*Halt author: v0.4 executor session, 2026-04-25 ~01:30 PT.*
*Awaiting user decision on Q1 (canonical token world) before
proceeding into Phase 1.*
