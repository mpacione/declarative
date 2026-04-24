# Stage 1 — `propose_edits` as the LLM contract

> **TL;DR** — Stage 1 pivoted the composition contract from "emit a
> plan" to "emit one of seven edit verbs against current tree state."
> The apply side (all 7 verbs in `apply_edits`) was already complete
> from M7.1; the gap was three missing tool schemas + one unified
> orchestrator. Codex picked the per-verb tool surface (option B) over
> a discriminator-in-one-tool (option A). Real-Haiku capstone: Haiku
> picked `delete @rectangle-22280` with rationale in 2.58 s. Two plan
> §4.1 cleanup items were load-bearing and retained.

## 1. What Stage 1 was for

With Stage 0's flat named-node plans in place, the LLM can name
entities and the compose path preserves those names. Stage 1 pivots
what the LLM emits *per turn*:

- **Before:** emit a closed nested-children component array.
- **After:** emit exactly one of seven verbs
  (`set` / `delete` / `append` / `insert` / `move` / `swap` / `replace`)
  against the current tree state.

The benefit isn't just "edits instead of plans." It's that the LLM's
per-turn surface becomes small and addressable, which is a
prerequisite for Stages 2 (subtree focus) and 3 (session persistence
with per-turn granularity).

Three starting-IR modes all use the same contract; only the starting
`doc` differs:

- **SYNTHESIZE** — empty doc; LLM proposes appends to build from
  scratch.
- **EDIT** — donor screen's full extracted IR; LLM proposes targeted
  changes.
- **MID-SESSION** — session's current tree (Stage 3 caller owns the
  loop).

Per [`dd/propose_edits.py`](../../dd/propose_edits.py:7-19) docstring:
"the contract is satisfied by Stage 1.2's 'accept any doc' plus 1.4's
acceptance tests that exercise all three modes. Convenience helpers
(`load_doc_from_screen`, `new_empty_doc`, etc.) belong to whichever
Stage 2/3 caller actually needs them — building them now would lock
in a shape the session-aware caller will likely redesign."

## 2. Audit findings

The Stage 1 audit produced a discovery that substantially reshaped
the work: **most of what the plan asked for was already built.**

- `dd/markup_l3.py::apply_edits` had all seven verbs implemented
  end-to-end, per `project_m7_1_edit_grammar.md` — 109 tests, 9
  passes, shipped 2026-04-20.
- [`dd/structural_verbs.py`](../../dd/structural_verbs.py) had 4 of
  7 tool schemas (`append` / `delete` / `insert` / `move` / `swap`
  from M7.4). Three were missing: `set` / `swap` / `replace`.
  (Swap had a partial schema; insert/move had candidate collectors.)
- `dd/repair_agent.py` already implemented a generic Verifier /
  Proposer / Applier loop.
- `corpus_retrieval` already accepted a `context` dict and ranked on
  `expected_children` for subtree-level retrieval.

What was missing:

- Three tool schemas (set / swap / replace) completing the 7-verb
  surface.
- **One unified orchestrator** — a single entry point the LLM uses
  to emit *any* of the seven verbs, as opposed to seven separate
  call sites with ad-hoc glue.

So Stage 1's net-new work was narrower than the plan implied. Six
commits, ~970 LOC, 44 new tests:

| Commit | Substance |
|---|---|
| `8446769` | **Stage 1.1** — set / swap / replace tool schemas. Completes the 7-verb surface in [`dd/structural_verbs.py`](../../dd/structural_verbs.py). 18 tests, including 4 new pins for the previously-uncovered M7.4 schemas. |
| `3fef264` | **Stage 1.2** — [`dd/propose_edits.py`](../../dd/propose_edits.py), the unified orchestrator. 20 tests via mock client. |
| `83fe348` | **Stage 1.3+1.4** — starting-IR docstring (Codex: code-free) + 3 synthetic acceptance tests + 3 round-trip pins. |
| `0a02779` | **Stage 1.5** — real-Haiku capstone against Dank screen 333. |
| `ddd5866` | **Stage 1.6** — soft-deprecation of `_fill_system`. Full deletion deferred. |

## 3. Fork — per-verb tools (B) vs discriminator-in-one-tool (A)

The choice here was load-bearing. Either:

- **Option A — One `propose_edit` tool with a discriminator field.**
  The tool's `input_schema` would be a `oneOf` over the seven verb
  shapes, keyed on a `verb` property. Claude picks one tool; the
  orchestrator parses the discriminator.
- **Option B — Seven registered tools (`propose_set`,
  `propose_delete`, …, `propose_replace`).** Claude picks one tool
  from a registered list; the orchestrator dispatches on the tool
  name.

**Codex picked option B**, 2026-04-23. Reasoning:

1. **Match the model's native abstraction.** Anthropic's tool-use API
   supports "pick one of these tools." Verb selection *is* tool
   selection. Using the native mechanism gets us a calibrated model
   behavior (tool-use fine-tuning is extensive) rather than a
   discriminator pattern the model has to reason about.
2. **Better error modes.** In option A, if Claude picks the wrong
   nested oneOf shape (e.g. emits a `set` payload with a `delete`
   discriminator), the failure is schema-internal and hard to
   surface back to the caller. In option B, the tool name is the
   discriminator; mismatches can't happen.
3. **Defensive against multi-tool-call.** Option B lets us hard-error
   on `KIND_MULTIPLE_TOOL_CALLS` if Claude emits two tool calls in
   one turn. Option A would need a separate guard for "multiple
   discriminators in one tool call" — a different defect class.

The result is that [`dd/propose_edits.py::propose_edits`](../../dd/propose_edits.py)
returns a typed `ProposeEditsResult` with `ok` / `tool_name` /
`edit_source` / `rationale` / `applied_doc` / `error_kind`, where
`error_kind ∈ {KIND_NO_TOOLS, KIND_NO_TOOL_CALL, KIND_MULTIPLE_TOOL_CALLS,
KIND_PARSE_FAILED, KIND_APPLY_FAILED}`.

## 4. What the plan got wrong

Three corrections surfaced during the Stage 1 audit:

**Correction 1 — `_fill_system` line number drifted.** Plan §4.1 said
line 239 in `dd/composition/plan.py`. HEAD put it at line 670.
Cleanup work between plan-authoring and Stage 1 had shifted the
surrounding code. Use symbol names, not line numbers.

**Correction 2 — `SlotFill` traversal is NOT dead code.** Plan §4.1
Stage 1 cleanup prescribed: "delete parsed-but-unused `SlotFill`
traversal dead code in `dd/markup_l3.py`." Audit showed SlotFill is
load-bearing for the `{empty}` slot-visibility grammar (PR 2 of
slot-visibility work, shipped on the same branch). Deletion would
have been a serious regression. Skipped.

**Correction 3 — `corpus_retrieval` already does subtree-level
retrieval.** Plan Stage 2 said "this is the hook that needs
plumbing." The hook was already there at
[`dd/composition/providers/corpus_retrieval.py:151`](../../dd/composition/providers/corpus_retrieval.py),
accepting a `context` dict and ranking on `expected_children`. DRILL
just passes the right context. (This correction actually belongs to
Stage 2; calling it out here because the audit surfaced it in Stage 1's
sweep.)

## 5. Real-LLM capstone

`tests/test_propose_edits_capstone.py` (skipped without API key)
runs `propose_edits` against a real extraction of Dank screen 333.
Haiku was given the full extracted IR and asked to propose one edit.

**Result in 2.58 s:**

- Tool call: `propose_delete`.
- Target: `@rectangle-22280`.
- Rationale: *"decorative white vector rectangle that duplicates the
  image boundary and is marked as invisible, making it safely
  removable."*

Applied cleanly; round-trip pin held.

This is what "the LLM writes grammar, the compiler does the rest"
looks like at Stage 1 granularity — one verb per turn, typed tool
call, real tree as input, grounded rationale.

## 6. Stage 1.6 soft-deprecation of `_fill_system`

Plan §4.1 called for deletion of `_fill_system` /
`_extract_plan` / `_extract_fill` — the two-pass plan-then-fill
contract superseded by `propose_edits`.

Audit: `prompt_to_figma` (the existing one-shot CLI entrypoint)
still uses `_fill_system` for SYNTHESIZE mode. Deleting the symbol
would break that entrypoint without a migration.

**Decision (Codex option C — soft-deprecate, don't delete):**

- Mark `_fill_system` deprecated in the module docstring.
- Inline the removal gate in a docstring on the function itself:
  delete when EITHER `prompt_to_figma` migrates to a
  propose_edits-against-empty-doc loop, OR `dd design` (Stage 3)
  becomes the primary natural-language entry point.
- Keep all call sites functional; add no new call sites.

This is the "plumbing on a leash" principle from
[`feedback_plumbing_on_a_leash.md`](../../.claude/projects/-Users-mattpacione-declarative-build/memory/feedback_plumbing_on_a_leash.md):
delete user-visible surface at cutover; retain internal plumbing only
with a concrete trigger for eventual removal.

## 7. Where the work lives

- [`dd/structural_verbs.py`](../../dd/structural_verbs.py) — all 7
  per-verb tool-schema builders + candidate collectors
  (`collect_parent_candidates`, `collect_insert_candidates`,
  `collect_move_candidates`, `collect_removable_candidates`,
  `unique_eids`).
- [`dd/propose_edits.py`](../../dd/propose_edits.py) — unified
  orchestrator, the Stage 1 net-new module.
- [`dd/markup_l3.py::apply_edits`](../../dd/markup_l3.py) — the verb
  dispatch (already-shipped since M7.1).
- [`dd/repair_agent.py`](../../dd/repair_agent.py) — generic
  Verifier/Proposer loop; Stage 2 builds on top.
- Tests:
  - [`tests/test_structural_verbs_schemas.py`](../../tests/test_structural_verbs_schemas.py) — schema contracts.
  - [`tests/test_propose_edits.py`](../../tests/test_propose_edits.py) — orchestrator unit tests.
  - [`tests/test_propose_edits_acceptance.py`](../../tests/test_propose_edits_acceptance.py) — synthetic acceptance.
  - [`tests/test_propose_edits_capstone.py`](../../tests/test_propose_edits_capstone.py) — real-LLM capstone.

## 8. Acceptance

- pytest: 3263 pass, 13 skipped. Baseline-diff zero new regressions
  (41 FAILED + 7 ERROR all pre-existing optional-dep / DB-fixture
  failures unchanged).
- 204/204 PARITY sweep held (843 s).
- Real-LLM capstone passed in 2.58 s.

---

*Stage 1 set the contract for "one verb per LLM turn." Stage 2 builds
the subtree-focus mechanic on top. See
[`stage-2-focus-primitives.md`](stage-2-focus-primitives.md).*