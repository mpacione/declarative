# Composition notes — do the skill boundaries fight the CLI?

Walking through the three flows from README.md in more detail to
check whether the skill abstraction feels natural or forced.

## Flow 1 — "I want to reproduce my Figma file in React later"

Ideal conversational sequence with Claude Code:

> **User:** I want to get my Figma file into code. Start by pulling
> it into the local format.
>
> **Claude** (picks `extract-figma` from context): Running
> `dd extract ...` and then `dd extract-plugin ...`. ✓ Extracted
> 47K nodes across 186 screens.
>
> **User:** Confirm the round-trip works before I trust it further.
>
> **Claude** (picks `verify-parity`): Generated a representative
> screen and verified. `is_parity=True`, 91/91 nodes, 0 errors.

Both skills present. Both do a natural unit of work. Neither is a
subset of the other. ✅

## Flow 2 — "Generate a new screen in my design system's style"

> **User:** I want to generate new screens that look like they belong
> in my app.
>
> **Claude** (detects dep — `generate-design-md` depends on
> `extract-figma`): First I need to extract your file if it's not
> already in the DB.
>
> **User:** It's already extracted. Give me the style snapshot.
>
> **Claude** (picks `generate-design-md`): Wrote design.md. 143
> components, 89 tokens, 4 TODO sections for you to fill (voice,
> intent, exclusions, lineage).
>
> **User:** *(edits design.md)* OK now generate a settings page.
>
> **Claude** (picks `generate-screen`): IR generated, rendered, parity
> verified, critique 7.8/10. Done.

Clean three-skill chain. The edit-loop between `generate-design-md`
and `generate-screen` is where the human's design judgment enters the
pipeline. If we'd merged them, that judgment wouldn't have a place. ✅

## Flow 3 — "Starting fresh, iterating"

> **User:** Extract, then give me a dashboard.
>
> **Claude**: (extract-figma → generate-design-md → generate-screen)
> Done. Here's the result. Critique 6.9/10, weakest Hierarchy.
>
> **User:** Make me 5 variants.
>
> **Claude** (re-runs `generate-screen` with `--variants 5`): Done.
>
> **User:** I like variant 3's card layout but variant 1's header.
>
> **Claude** (re-runs `generate-screen` with a combined-constraint prompt):
> New variant combining the elements. Critique 8.1/10.
>
> **User:** Verify parity independently.
>
> **Claude** (picks `verify-parity`): 47/47 nodes, 0 errors.

Four-skill chain with an iteration loop. All four are used. The
variants + combination case is handled by re-invoking `generate-screen`
with different arguments — not a separate skill. ✅

## Edge cases I considered

**"A one-shot extract + generate skill"?** Tempting for demos, but
it would couple two things the user wants to control separately: the
extraction (rare, heavy) vs. the generation (frequent, light). The
DB is a reusable asset; bundling them makes the DB feel like a
generation implementation detail rather than a real artefact the
user can inspect.

**"A push-tokens skill"?** Not in the four here, but would be a
natural fifth. Defer to after v0.1.

**"An edit-generated-screen skill"?** For the iteration case. Arguably
folds into `generate-screen` with a "--continue from <previous>"
argument rather than a separate skill. Defer.

**"A critique-only skill"?** Runs the vision critic on an arbitrary
Figma frame the user points at. Would be useful as a design-review
tool even outside generation. Possible fifth skill; out of scope for
v0.1.

## Verdict

The four boundaries don't fight the CLI. Each skill is a unit of
user intent, each is a unit of implementation (thin wrapper over one
or two `dd` commands), each chains naturally with the others. The
abstraction survives realistic use.

One concrete recommendation: the skill versioning should track the
`dd` CLI version. Installing `extract-figma@0.2` should imply
`dd@0.2` behaviour. This matches how most skill marketplaces
version today.

## What this doesn't test

- Whether skill discovery (finding the right skill from a user's
  conversational phrasing) works reliably. That's empirical and
  only answerable after deploying to a marketplace.
- Whether the skills' conversational signatures compete with Figma's
  own skills (`figma-implement-design`, `figma-generate-library`,
  `figma-build-screens`). Probably fine — our angle is IR and
  round-trip, theirs is direct-to-Figma — but worth monitoring.
- Whether the installation experience is smooth (Python + Node + DB
  + env vars is a lot for a skill marketplace expecting
  zero-configuration). We may need a lightweight bootstrap skill
  that handles first-time setup.
