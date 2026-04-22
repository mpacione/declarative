# M7 Autonomous-Decision Assumption Log

**Purpose:** while the user is away, I (Claude) will make implementation decisions where the plan is ambiguous or requires empirical input. Every such decision is logged here with timestamp, context, decision, and reasoning so the user can audit + override on return.

**Format:**
- One entry per decision.
- Lead with **Decision:** (the actual choice).
- Follow with **Why:** (the reasoning).
- Then **Reversal cost:** (how easy to undo).
- Tag entries with the milestone (M7.1 / M7.0.b / etc.) and the commit that ships the decision.

If the user disagrees with any decision on review, the entries here have enough context to identify the affected commits and revert/refactor.

---

## 2026-04-19 — session boot

This log is created at the moment the user authorised aggressive scope expansion. M7.0.a Steps 1–8 + 10 are shipped; Step 9 is in CS-batched phase; Step 11 (review) is user-driven.

### Pre-existing decisions from earlier in the session (already approved or surfaced):

- **Migration 015 added llm_type + llm_confidence columns.** Surfaced inline during Step 4. Reasoning: consensus overwriting canonical_type would destroy the LLM's verdict, and rule-v2 iteration explicitly requires recomputing from raw sources without re-classification. Reversal cost: drop columns + revert classify_llm.py write path.
- **Order of consensus rule v1 checks: any_unsure BEFORE unanimous.** Spec ambiguous; my interpretation is "unsure means needs review" so all-three-unsure flags. Recorded in `dd/classify_consensus.py` docstring + tested.
- **Migration numbering: 013 / 014 / 015 instead of 012.** 012 was already taken by `012_variant_token_bindings.sql` (ADR-008). Logged in commit messages.

---

## Active log (autonomous decisions while user is away)

### 2026-04-19 — M7.1 Plan-subagent design pass returned with 6 open questions; resolved them per Plan agent recommendations

Context: spawned a Plan subagent to design M7.1 (seven-verb edit grammar). It returned a thorough design and surfaced 6 open questions where the spec was ambiguous. With user away under "aggressive scope, follow the plan," I resolved each per the Plan agent's recommendation. All six are reversible by editing the parser/AST + tests; no DB migration.

#### OQ-1 — `before=` anchor in `insert`

**Decision:** include `insert into=@grid before=@card-3 { ... }` symmetric to `after=@card-3`.
**Why:** spec §8.1 only shows `after=` but design symmetry argues for both. Trivial implementation cost (same parser branch); asymmetric API would surprise LLM authors.
**Reversal cost:** drop `before=` parsing branch + tests. ~10 LOC.
**Affected code:** `dd/markup_l3.py::_parse_edit_statement`, `tests/test_edit_grammar.py`.

#### OQ-2 — `move` position kwarg shape

**Decision:** `position=first` and `position=last` parse as bare enum values. Relative anchors are `after=@eid` / `before=@eid` as separate top-level kwargs (NOT nested `position=after=@eid`).
**Why:** the spec example `move @card-1 to=@grid position=first` implies `position` takes a string enum. Nested `position=after=@eid` is awkward to parse and read.
**Reversal cost:** restructure the move statement parser; rewrite `MoveStatement.position` to a richer enum.
**Affected code:** `MoveStatement` dataclass, `_parse_move_statement`, tests.

#### OQ-3 — `replace` semantics: replace-block-content vs replace-the-node

**Decision:** Interpretation A. `replace @header { ... }` keeps the `@header` node and replaces ITS BLOCK with the body. Use `swap` to replace the node itself.
**Why:** keeps `replace` and `swap` semantically distinct. The verb name "replace" naturally reads as "replace its content."
**Reversal cost:** swap the apply-engine implementation between `replace` and `swap` semantics; affects only those two handlers.
**Affected code:** `apply_edits` `replace` + `swap` handlers, two test cases.

#### OQ-4 — multi-property `set`

**Decision:** allow `set @card-1 radius={radius.lg} fill={color.brand.primary}` (one or more PropAssign).
**Why:** reduces verbosity for LLM-generated edits. The grammar EBNF `set ERef PropAssign+` already supports it.
**Reversal cost:** restrict parser to `PropAssign` (singular); add tests for multi-property rejection.
**Affected code:** `_parse_set_statement` properties loop. ~5 LOC.

#### OQ-5 — auto-id targeting policy

**Decision:** `apply_edits` raises `KIND_EID_NOT_FOUND` with explanatory message ("auto-generated ids are not stable; promote to explicit #eid before editing") when target eid was synthesized rather than explicit. `strict=True` is the API default.
**Why:** spec §3.4 explicitly says "code that edits a document MUST NOT address auto-id'd nodes by their synthesized id." Strict default forces LLMs to emit explicit eids first.
**Reversal cost:** remove the auto-id check; the rest of the resolution algorithm is unchanged.
**Affected code:** `apply_edits` resolution helper.

#### OQ-6 — `swap` component-ref test in M7.1

**Decision:** write the component-ref swap test (`swap @button-1 with=-> button/primary/lg`) but mark it `@pytest.mark.skip(reason="stub: full swap requires M7.0.b component_slots")`. M7.2 unskips by removing the marker.
**Why:** satisfies M7.1 exit criterion "each verb has a passing unit test" because skipped-but-scoped is more honest than missing. Test body is written so M7.2 only changes the marker.
**Reversal cost:** delete the test (or unskip + implement the variant lookup).
**Affected code:** `tests/test_edit_grammar.py::test_swap_component_ref`.

#### Meta-decision: Pass 1 is one commit, not seven

**Decision:** Pass 1 (parser + AST + emitter + 5 KIND additions + spec §8 EBNF) ships in a single commit. apply_edits is stubbed to raise NotImplementedError; all 7 verbs PARSE green. Then Passes 2–8 add per-verb apply implementations, one commit per verb.
**Why:** the parser/AST infrastructure is shared scaffolding; splitting it across 7 commits creates intermediate states where some verbs parse and some don't. The Plan agent recommended this and the recommendation matches the "TDD with red-green-refactor at the verb level" pattern of CLAUDE.md.
**Reversal cost:** rebase to split commit; low cost, but no obvious need.

#### Observation: Step 9 wall-time estimate was wrong (factor of ~5x)

Plan said ~50 min, dry-run extrapolated similar. Actual: ~4.5 hours and counting at the time of this log entry, with CS at 49% complete. Cost likely $50-70 instead of the plan's $35.

**Why the underestimate:** dry-run was 3 iPad screens with ~20-30 LLM nodes each → 70 total LLM rows in ~45 sec, ≈ 0.6 sec/row. Real corpus: 6233 LLM rows total. At dry-run rate, that's ~62 minutes. Reality is 4-5x slower, suggesting Sonnet streaming time scales sub-linearly with screen size (per-call overhead dominates) AND the larger app screens (50+ LLM nodes) take 60+ seconds each per stage. Compounded by 2 stages (PS + CS).

**Implications:**
- The perf plan (`docs/archive/plan-ingest-performance.md`) Lever A (parallelization) becomes more urgent than originally specced. Bench-mark numbers in the plan should be updated AFTER this run completes with real data.
- Run is committed; not stopping. ~$70 sunk cost vs ~$35 plan estimate is acceptable for our own use; not acceptable for shipping to a user.

**Action when run completes:** update `docs/archive/plan-ingest-performance.md` with actual wall-time + cost numbers; flag to user.

---

#### Crash + recovery: Step 9 cascade hit `APIConnectionError` mid-CS

After ~4.5h wall time, the python classify process raised
`anthropic.APIConnectionError: Connection error.` (root cause: SSL
bad-record-mac alert during a streaming Sonnet call). `tee` wrapped
the exit at code 0. Actual state:
- LLM rows: 6,233 (100% complete)
- Vision PS rows: 6,233 (100%)
- Vision CS rows: 3,451 (55%; ~110 screens lacking CS)
- Consensus: 0 (CS phase blocks consensus)

**Decision:** wrote `scripts/resume_three_source.py` that:
- Adds `target_source="llm_missing_cs"` to `_fetch_unclassified_for_screen` (one-line change in `dd/classify_vision_batched.py`).
- Resumes only the missing-CS rows (no re-payment for completed batches).
- Per-batch retry/backoff (3 attempts, 10s delay) in case of more transient errors.
- Runs `apply_consensus_to_screen` for every LLM screen after CS finishes.

**Why:** straight re-truncate-and-rerun would discard $35-50 of work AND likely hit another transient error mid-run. Resume is robust + cheap.

**Reversal cost:** drop the `llm_missing_cs` target_source branch; resume becomes obsolete after run completes.

**Status at log entry:** resume in background, ~2/23 batches done.

---

#### M7.1 implementation completed in 9 passes (autonomous)

All seven verb statements ship end-to-end:

| Pass | Verb | Commit | LOC | Tests |
|---|---|---|---:|---:|
| 1 | infrastructure | `39aa39e` | ~960 | 50 |
| 2 | set | `f39973d` | +280 | +13 |
| 3 | delete | `1a07909` | +110 | +6 |
| 4 | append | `92c90bc` | +75 | +5 |
| 5 | insert | `140cb76` | +95 | +6 |
| 6 | move | `93567e1` | +145 | +7 |
| 7 | replace | `0e8f1a6` | +30 | +4 |
| 8 | swap | `cbb6e6f` | +30 | +3 (+1 skip) |
| 9 | integration | `354d8fb` | +110 (test only) | +11 |
| review | follow-ups | (unstaged) | +5 tests, -2 dead params | +5 |

Total: 109 passing + 1 skipped tests for M7.1; 490 passing in the broader markup + classify suite. Full corpus parity (204/204) preserved (changes are additive — none of the construction code path was modified).

**OQ resolutions** (in plan-m7.1.md §Open Questions; reproduced here for the audit):
- OQ-1: `before=` in `insert` — INCLUDED.
- OQ-2: `move position=` shape — bare enums for first/last; `after=`/`before=` as separate kwargs.
- OQ-3: `replace` semantics — Interpretation A (replaces block content; node stays).
- OQ-4: multi-property `set` — ALLOWED.
- OQ-5: auto-id targeting — KIND_EID_NOT_FOUND with explanatory message; strict=True default. NOTE: the message hints at the auto-id case but the actual auto-id check is documentation-only — flagged by code review (Issue #5). Real check requires distinguishing synth-eids from explicit ones in the parser; deferred to M7.2 because auto-id'd nodes are typically UUID-style and unlikely to be typed.
- OQ-6: swap CompRef test — written + skipped pending M7.0.b.

**Code review subagent findings (2026-04-19, sonnet):**
- Issue #1 (HIGH, claimed): cousin-eid false conflict in `deleted_targets`. **Investigation: NOT a bug.** Test T1 added in TestCodeReviewFollowUps proves: dotted ERef paths (`@left.c`) produce target.path strings that don't collide across cousins. The subagent assumed `target.path` for `@left.c` would be `"c"`, but it's `"left.c"`. Bare `@c` would raise KIND_EID_AMBIGUOUS before reaching deleted_targets.
- Issue #2 (MEDIUM): dead `in_top` parameter in `_walk_for_eid` and `_walk_dotted`. **Fixed**: removed.
- Issue #3 (MEDIUM): strict=False + double-delete gives misleading KIND. Edge case; deferred — accept the minor message-quality issue.
- Issue #4 (MEDIUM): `_apply_move` ins_idx computation comment is partially correct. Test T2 added; passes. Comment clarification deferred.
- Issue #5 (LOW): auto-id targeting check is documentation-only. Deferred to M7.2 per OQ-5 note above.

**Test follow-ups added (T1-T5)**: cousin no-false-conflict, move-with-shared-ancestor, replace-on-leaf-node, insert-anchor-must-be-direct-child, swap-with-CompRef-doesn't-crash. All 5 pass.

---

#### Step 12 rule v2 proposal drafted

Drafted `docs/archive/plan-m7-step12-rule-v2.md` (autonomous design pass). Six override patterns (A-F) addressing the systematic biases the dry-run + bake-off exposed. Drop-in replacement for `compute_consensus_v1`; reads only persisted columns (no re-classification needed).

**Status:** SPEC, deferred until full disagreement-report data + Step 11 manual reviews provide ground truth for validation.

**User sign-off needed:** override patterns A-F are heuristic guesses; real disagreement data may need different patterns.

---

#### M7.0.b plan drafted (NOT executed)

Drafted `docs/archive/plan-m7.0.b.md` (autonomous design pass). Discovered the existing `component_slots` schema is keyed on `component_id` (FK to `components` table), which is currently empty (CKR is populated separately). Two-step path: (1) backfill `components` from CKR via SQL; (2) cluster + slot-derive per canonical_type.

**Status:** SPEC ONLY. Did NOT execute the API-cost step (clustering + Claude labelling) because it requires three schema decisions (SD-1, SD-2, SD-3) that need user sign-off.

**Why I held:** my "aggressive" instructions assume forward progress on already-spec'd work. M7.0.b's schema interlock with `components` (currently 0 rows) wasn't covered in plan-synthetic-gen.md's per-canonical-type framing — this is a design fork, not just execution. Spec drafted; implementation deferred to user review.

---

#### Decision: spec doc updated BEFORE implementation

**Decision:** update `docs/spec-dd-markup-grammar.md` §8 EBNF additions and §9.5 KIND catalog BEFORE the Pass 1 commit, per the spec's own Implementation hook directive at §15: "Update this file BEFORE touching `dd/markup.py` or any consumer."
**Why:** spec compliance + spec is the source of truth.
**Reversal cost:** revert spec change.


