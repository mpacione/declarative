# What the plan got wrong

Index of audit corrections discovered during Stages 0–3
implementation. Every item here is captured in a stage-doc's "what
the plan got wrong" section with fuller context; this doc is the
cross-stage summary for the reader who wants the full correction
list in one place.

The plan (`docs/plan-authoring-loop.md`) was authored before Stage 0
began, and a lot of substrate work landed on the branch between
plan-authoring and Stage 0 kick-off (hidden-children-unification,
type/role split, slot-visibility grammar). Some of the plan's claims
were simply outdated by the time each stage started. Others were
aggressive "delete this" calls where audit showed the target was
load-bearing.

None of the corrections changed the plan's shape. The authoring loop
still has the four stages, still ships `frame` + flat plans + 7-verb
tool surface + NAME/DRILL/CLIMB + `dd design`, still closes the four
defects. The corrections are at the granularity of individual cleanup
items and line-number references.

## Stage 0 corrections

| Plan claim | Correction | Where |
|---|---|---|
| "Delete `_fetch_descendant_visibility_overrides` in `dd/compress_l3.py` — duplicates `build_override_tree`" | Not dead; handles H3 class override resolution that `override_tree` doesn't cover. Retained. | [`stage-0-contract.md` §3 Fork 3](stage-0-contract.md#3-design-forks) |
| "Depth-2 `.visible=false` bug is a compressor duplication bug" | Closed by hidden-children-unification PR series (`97f8220`–`1dcb446`) before Stage 0 touched the compose path. | [`stage-0-contract.md` §4 Correction 1](stage-0-contract.md#4-what-the-plan-got-wrong-audit-corrections) |
| Line-number references in `dd/composition/plan.py` | Line numbers drifted (cleanup work shifted the surrounding code). Use symbol names, not line numbers. | [`stage-0-contract.md` §4 Correction 3](stage-0-contract.md#4-what-the-plan-got-wrong-audit-corrections) |
| "Delete `figma.skipInvisibleInstanceChildren = true`" | Right about the symptom, wrong about the fix. Deletion would regress the perf win. Fix is a scoped try/finally toggle around every `findOne` call. | [`stage-0-contract.md` §6 The near-miss](stage-0-contract.md#6-the-skipinvisibleinstancechildren-near-miss) |

## Stage 1 corrections

| Plan claim | Correction | Where |
|---|---|---|
| "Delete `_fill_system` prompt at `dd/composition/plan.py:239`" | Line number drifted (HEAD has it at 670). Also, `_fill_system` is still load-bearing for `prompt_to_figma` SYNTHESIZE mode. Soft-deprecated, not deleted. | [`stage-1-propose-edits.md` §6 Soft-deprecation](stage-1-propose-edits.md#6-stage-16-soft-deprecation-of-_fill_system) |
| "Delete parsed-but-unused `SlotFill` traversal dead code" | NOT dead — load-bearing for the `{empty}` slot-visibility grammar (PR 2 of slot-visibility, same branch). Deletion would have been a serious regression. | [`stage-1-propose-edits.md` §4 Correction 2](stage-1-propose-edits.md#4-what-the-plan-got-wrong) |

## Stage 2 corrections

| Plan claim | Correction | Where |
|---|---|---|
| "Retrieve donor fragments using `corpus_retrieval` at subtree level — this is the hook that needs plumbing" | Already wired at [`dd/composition/providers/corpus_retrieval.py:151`](../../dd/composition/providers/corpus_retrieval.py). DRILL just passes the right context — one-line change, not a plumbing job. | [`stage-2-focus-primitives.md` §4 Correction 1](stage-2-focus-primitives.md#4-audit-findings-what-the-plan-got-wrong) |
| "Delete `TokenOnlyProvider`" | Phantom — doesn't exist anywhere in the codebase. ADR slot that never materialized. Skipped. | [`stage-2-focus-primitives.md` §4 Correction 2](stage-2-focus-primitives.md#4-audit-findings-what-the-plan-got-wrong) |

## Stage 3 corrections

| Plan claim | Correction | Where |
|---|---|---|
| "Delete `_composition` legacy field references" | Not dead — 5+ live readers across compose / templates / ir / renderer. Retained. | [`stage-3-session-loop.md` §4 Correction 1](stage-3-session-loop.md#4-what-the-plan-got-wrong) |
| "Delete `KIND_PLAN_INVALID`" | Not dead — actively emitted by `dd.composition.plan` at 5 sites + 2 test files. Retained. | [`stage-3-session-loop.md` §4 Correction 2](stage-3-session-loop.md#4-what-the-plan-got-wrong) |
| "Delete `TokenOnlyProvider`" | Same phantom as Stage 2's audit. Still doesn't exist. Still skipped. | [`stage-3-session-loop.md` §4 Correction 3](stage-3-session-loop.md#4-what-the-plan-got-wrong) |

## Patterns

Three meta-patterns surfaced across the corrections:

**Pattern 1 — Plan time ≠ implementation time.** Substrate work
shipped on the same branch between plan-authoring and each stage's
start. By the time Stage 0 touched compose, hidden-children-unification
had already closed the depth-2 visibility bug. By the time Stage 1
audited the plan prompts, slot-visibility had already added a consumer
for SlotFill. The lesson: re-audit the plan's claims at the start of
each stage, not at plan-authoring time.

**Pattern 2 — "Not wired" ≠ "not there."** Two different hooks
(`corpus_retrieval` context ranking; `ProjectCKRProvider` for Mode 3)
existed in code but weren't actually wired into the call sites the
plan expected. The hooks were 90% done; the plan's assessment
"build this" was wrong; the correct assessment was "wire the
existing thing up." Lesson: grep before you estimate.

**Pattern 3 — Aggressive deletions are often wrong.** Six of the
plan's cleanup items (across Stages 0–3) called for deletions that
audit showed were load-bearing or phantom. Two were genuinely dead
(`KIND_RATE_LIMITED` + four demo scripts). The signal-to-noise on
aggressive "delete this" prescriptions was roughly 1:3. Lesson: the
default for an aggressive delete call is "audit it first"; the prior
is that it'll turn out to be load-bearing.

---

*This doc is a reference index. For the full context of each
correction, read the stage-doc it's linked from.*